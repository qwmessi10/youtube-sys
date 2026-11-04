from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import SMMAccount, SMMTask
from .serializers import SMMAccountSerializer, SMMTaskSerializer
from .services import (
    LATEST_CHROME_UA,
    get_balance,
    map_panel_status,
    publish_telegram_auth,
    search_task_record,
    send_task,
)
from keywords.models import GlobalSetting

# 结束时间最小提前量（小时）。面板按印度时区（比北京时间晚 2.5h），下单是北京时间，
# 需留足时差与任务运行缓冲，避免任务窗口太短/已过期。
MIN_END_HOURS = 2


class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


def _set_setting(key, value, description=""):
    obj, _ = GlobalSetting.objects.get_or_create(key=key, defaults={"value": value, "description": description})
    obj.value = value
    if description and not obj.description:
        obj.description = description
    obj.save()
    return obj


def _apply_auth(account, auth_data):
    """把 publishTelegramAuth 返回值写入账号，返回是否成功。"""
    if auth_data.get("code") not in (0, None):
        return False
    d = auth_data.get("data") or {}
    account.token = d.get("token") or ""
    account.user_identifier = d.get("userIdentifier") or ""
    account.panel_user_name = d.get("userName") or ""
    return bool(account.token)


class SMMAccountViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """面板账号（个人中心）。create 时自动提取 token + 余额。"""
    queryset = SMMAccount.objects.all()
    serializer_class = SMMAccountSerializer
    pagination_class = TenPerPagePagination

    def create(self, request, *args, **kwargs):
        tg_user_id = (request.data.get("tg_user_id") or "").strip()
        if not tg_user_id:
            return Response({"detail": "请填写 Telegram 数字 ID"}, status=status.HTTP_400_BAD_REQUEST)
        if SMMAccount.objects.filter(tg_user_id=tg_user_id).exists():
            return Response({"detail": "该账号已存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 1) 换取 token（名字可空，只认 tgUserId）
        auth = publish_telegram_auth(
            tg_user_id,
            first_name=request.data.get("first_name", ""),
            last_name=request.data.get("last_name", ""),
            username=request.data.get("username", ""),
        )
        if auth.get("code") not in (0, None):
            return Response({"detail": "获取 token 失败：" + str(auth.get("msg", auth))},
                            status=status.HTTP_400_BAD_REQUEST)

        account = SMMAccount(
            tg_user_id=tg_user_id,
            username=(request.data.get("username") or "").strip(),
            first_name=(request.data.get("first_name") or "").strip(),
            last_name=(request.data.get("last_name") or "").strip(),
            remark=(request.data.get("remark") or "").strip(),
        )
        if not _apply_auth(account, auth):
            return Response({"detail": "获取 token 失败：返回为空"}, status=status.HTTP_400_BAD_REQUEST)
        account.save()

        # 2) 拉余额
        bal = get_balance(account.token, account.user_identifier, account.tg_user_id)
        if bal.get("code") in (0, None):
            account.balance = bal.get("data", {}).get("balance") or 0
            account.status = SMMAccount.STATUS_ACTIVE
        else:
            account.status = SMMAccount.STATUS_TOKEN_INVALID
        account.save()

        return Response(SMMAccountSerializer(account).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """重新提取 token + 刷新余额 + 校验有效性。"""
        account = self.get_object()
        auth = publish_telegram_auth(account.tg_user_id, account.first_name, account.last_name, account.username)
        if auth.get("code") not in (0, None):
            account.status = SMMAccount.STATUS_TOKEN_INVALID
            account.save()
            return Response({"detail": "token 提取失败：" + str(auth.get("msg", auth))},
                            status=status.HTTP_400_BAD_REQUEST)
        _apply_auth(account, auth)
        bal = get_balance(account.token, account.user_identifier, account.tg_user_id)
        if bal.get("code") in (0, None):
            account.balance = bal.get("data", {}).get("balance") or 0
            account.status = SMMAccount.STATUS_ACTIVE
        else:
            account.status = SMMAccount.STATUS_TOKEN_INVALID
        account.save()
        return Response(SMMAccountSerializer(account).data)

    @action(detail=False, methods=["post"])
    def refresh_ua(self, request):
        """一键更新 UA/Origin/Referer（应对 WAF 升级）。Origin/Referer 按当前域名，UA 用内置最新 Chrome UA。"""
        base = request.data.get("base") or "https://saircaf.autolak.in"
        origin = request.data.get("origin") or "https://saircaf.autolak.in"
        referer = request.data.get("referer") or "https://saircaf.autolak.in/"
        ua = request.data.get("ua") or LATEST_CHROME_UA
        _set_setting("AUTOLAK_API_BASE", base, "SMM 面板-后端 API 基址")
        _set_setting("AUTOLAK_UA", ua, "SMM 面板-请求 User-Agent（直连需带浏览器 UA）")
        _set_setting("AUTOLAK_ORIGIN", origin, "SMM 面板-请求 Origin")
        _set_setting("AUTOLAK_REFERER", referer, "SMM 面板-请求 Referer")
        return Response({
            "AUTOLAK_API_BASE": base, "AUTOLAK_UA": ua,
            "AUTOLAK_ORIGIN": origin, "AUTOLAK_REFERER": referer,
        })


class SMMTaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """刷量任务。create 时真实提交到面板；状态/进度用 sync_status 同步。增删改查齐全。"""
    queryset = SMMTask.objects.select_related("account").all()
    serializer_class = SMMTaskSerializer
    pagination_class = TenPerPagePagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(show_id__icontains=search)
                | Q(key_words__icontains=search)
                | Q(youtube_link__icontains=search)
                | Q(panel_task_id__icontains=search)
            )
        return qs

    def create(self, request, *args, **kwargs):
        account_id = request.data.get("account")
        youtube_link = (request.data.get("youtube_link") or "").strip()
        key_words = (request.data.get("key_words") or "").strip()
        total_user = request.data.get("total_user")
        if not account_id or not youtube_link or not key_words or not total_user:
            return Response({"detail": "账号、YouTube 链接、关键词、人数均为必填"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            account = SMMAccount.objects.get(pk=account_id)
        except SMMAccount.DoesNotExist:
            return Response({"detail": "账号不存在"}, status=status.HTTP_400_BAD_REQUEST)

        per_user = request.data.get("per_user", 2)
        end_hours = int(request.data.get("end_hours", 48) or 48)
        if end_hours < MIN_END_HOURS:
            return Response(
                {"detail": f"结束时间必须至少 {MIN_END_HOURS} 小时后（面板按印度时区，需留足时差缓冲）"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task_type = int(request.data.get("task_type", 42) or 42)
        plant_form = int(request.data.get("plant_form", 1) or 1)
        comment_num = int(request.data.get("comment_num", 1) or 1)

        res = send_task(
            account.token, account.user_identifier, account.tg_user_id,
            youtube_link, key_words, int(total_user),
            per_user=per_user, comment_num=comment_num,
            end_hours=end_hours, plant_form=plant_form, task_type=task_type,
        )
        if res.get("code") not in (0, None):
            return Response({"detail": "提交失败：" + str(res.get("msg", res))},
                            status=status.HTTP_400_BAD_REQUEST)

        d = res.get("data") or {}
        task = SMMTask.objects.create(
            account=account,
            panel_task_id=d.get("taskId") or "",
            show_id=d.get("showId") or "",
            youtube_link=youtube_link,
            key_words=key_words,
            total_user=int(total_user),
            per_user=per_user,
            task_type=task_type,
            plant_form=plant_form,
            comment_num=comment_num,
            end_time=d.get("endTime") or "",
            cost=float(total_user) * float(per_user),
            status=SMMTask.STATUS_PENDING,
            panel_status="",
        )
        return Response(SMMTaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def sync_status(self, request, pk=None):
        """拉面板最新状态/进度并回填。"""
        task = self.get_object()
        updated = sync_task_from_panel(task)
        if updated is None:
            return Response({"detail": "同步失败（面板接口异常）"}, status=status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        return Response(SMMTaskSerializer(task).data)


def sync_task_from_panel(task):
    """同步单个任务（供 view 与 Celery 复用）。成功返回 True，面板无此任务返回 False，异常返回 None。"""
    account = task.account
    res = search_task_record(account.token, account.user_identifier, account.tg_user_id)
    if res.get("code") not in (0, None):
        return None
    records = (res.get("data") or {}).get("result") or []
    for r in records:
        if r.get("taskId") == task.panel_task_id:
            task.panel_status = r.get("status") or ""
            task.show_id = r.get("showId") or task.show_id
            task.cost = r.get("cost") or task.cost
            task.progress = {
                "total_users": r.get("totalUsers"),
                "pending_users": r.get("pendingUsers"),
                "complete_size": r.get("completeSize"),
                "success_rate": r.get("successRate"),
                "fail_rate": r.get("failRate"),
                "fail_num": r.get("failNum"),
            }
            task.status = map_panel_status(task.panel_status)
            task.save()
            return True
    return False
