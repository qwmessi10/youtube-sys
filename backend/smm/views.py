import re

from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import SMMAccount, SMMPollTask, SMMTask
from .serializers import SMMAccountSerializer, SMMPollTaskSerializer, SMMTaskSerializer
from .services import (
    LATEST_CHROME_UA,
    POLL_END_HOURS,
    extract_video_id,
    get_balance,
    get_video_stats,
    map_panel_status,
    next_slot_after,
    publish_telegram_auth,
    search_task_record,
    send_task,
)
from keywords.models import GlobalSetting

# 结束时间最小提前量（小时）。面板按印度时区（比北京时间晚 2.5h），下单是北京时间，
# 需留足时差与任务运行缓冲，避免任务窗口太短/已过期。
MIN_END_HOURS = 2

# 人数上限（防止误填超大值导致成本爆表）。
MAX_TOTAL_USER = 10000

# YouTube 链接格式（youtube.com / youtu.be，可带 http(s):// 与 www./m. 前缀）。
YOUTUBE_LINK_RE = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)


def clean_keywords(raw):
    """关键词按 ; 分隔：去首尾空格、去掉空项。返回 (清洗后字符串, 是否含空项)。"""
    parts = [p.strip() for p in (raw or "").split(";")]
    cleaned = [p for p in parts if p]
    return ";".join(cleaned), len(cleaned) != len(parts)


def _video_stats_response(youtube_link):
    """从任务链接查 YouTube 实时统计（浏览量/点赞/评论），返回统一 Response。纯读，不碰面板。"""
    video_id = extract_video_id(youtube_link)
    if not video_id:
        return Response({"detail": "无法从链接解析出视频 ID"}, status=status.HTTP_400_BAD_REQUEST)
    stats = get_video_stats(video_id)
    if stats is None:
        return Response(
            {"detail": "查询失败（未配置 YOUTUBE_API_KEY，或视频不存在 / 接口异常）"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"youtube_link": youtube_link, **stats})


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
                     mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """刷量任务。create 时真实提交到面板，下单后不可编辑（删除仅删本地记录）；状态/进度用 sync_status 同步。"""
    # 普通任务列表只展示 poll_task 为空的记录；轮询产生的子下单挂在父任务下展示。
    queryset = SMMTask.objects.select_related("account").filter(poll_task__isnull=True)
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

        if not YOUTUBE_LINK_RE.match(youtube_link):
            return Response({"detail": "YouTube 链接格式不正确（需 youtube.com 或 youtu.be）"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            total_user_int = int(total_user)
        except (TypeError, ValueError):
            return Response({"detail": "人数必须为数字"}, status=status.HTTP_400_BAD_REQUEST)
        if not (1 <= total_user_int <= MAX_TOTAL_USER):
            return Response({"detail": f"人数必须在 1~{MAX_TOTAL_USER} 之间"},
                            status=status.HTTP_400_BAD_REQUEST)

        key_words, has_empty = clean_keywords(key_words)
        if not key_words:
            return Response({"detail": "关键词不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if has_empty:
            return Response({"detail": "关键词格式有误：存在空项（多个关键词用 ; 分隔）"},
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
            youtube_link, key_words, total_user_int,
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
            total_user=total_user_int,
            per_user=per_user,
            task_type=task_type,
            plant_form=plant_form,
            comment_num=comment_num,
            end_time=d.get("endTime") or "",
            cost=total_user_int * float(per_user),
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

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """查任务视频的实时统计（浏览量/点赞/评论）。纯读接口。"""
        task = self.get_object()
        return _video_stats_response(task.youtube_link)


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


class SMMPollTaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """轮询刷量任务：创建后由调度器按窗口每小时自动下单，跨天直到刷满轮询次数。"""
    queryset = SMMPollTask.objects.select_related("account").prefetch_related("children").all()
    serializer_class = SMMPollTaskSerializer
    pagination_class = TenPerPagePagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(key_words__icontains=search) | Q(youtube_link__icontains=search)
            )
        return qs

    def create(self, request, *args, **kwargs):
        account_id = request.data.get("account")
        youtube_link = (request.data.get("youtube_link") or "").strip()
        key_words = (request.data.get("key_words") or "").strip()
        poll_total = request.data.get("poll_total")
        if not account_id or not youtube_link or not key_words or not poll_total:
            return Response({"detail": "账号、YouTube 链接、关键词、轮询次数均为必填"},
                            status=status.HTTP_400_BAD_REQUEST)

        if not YOUTUBE_LINK_RE.match(youtube_link):
            return Response({"detail": "YouTube 链接格式不正确（需 youtube.com 或 youtu.be）"},
                            status=status.HTTP_400_BAD_REQUEST)

        key_words, has_empty = clean_keywords(key_words)
        if not key_words:
            return Response({"detail": "关键词不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if has_empty:
            return Response({"detail": "关键词格式有误：存在空项（多个关键词用 ; 分隔）"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            account = SMMAccount.objects.get(pk=account_id)
        except SMMAccount.DoesNotExist:
            return Response({"detail": "账号不存在"}, status=status.HTTP_400_BAD_REQUEST)

        batch_min = int(request.data.get("batch_min", 1) or 1)
        batch_max = int(request.data.get("batch_max", 5) or 5)
        if batch_min < 1 or batch_max < batch_min:
            return Response({"detail": "每批人数区间非法（下限≥1 且上限≥下限）"}, status=status.HTTP_400_BAD_REQUEST)
        if batch_max > MAX_TOTAL_USER:
            return Response({"detail": f"每批人数上限不能超过 {MAX_TOTAL_USER}"}, status=status.HTTP_400_BAD_REQUEST)

        window_start = int(request.data.get("window_start_hour", 12) or 12)
        window_end = int(request.data.get("window_end_hour", 21) or 21)
        if not (0 <= window_start < 24) or not (0 <= window_end <= 24) or window_end <= window_start:
            return Response({"detail": "执行时间窗口非法（0-24 且结束>开始）"}, status=status.HTTP_400_BAD_REQUEST)

        initial_count = request.data.get("initial_count") or None
        if initial_count is not None:
            try:
                initial_count_int = int(initial_count)
            except (TypeError, ValueError):
                return Response({"detail": "首次刷量人数必须为数字"}, status=status.HTTP_400_BAD_REQUEST)
            if not (1 <= initial_count_int <= MAX_TOTAL_USER):
                return Response({"detail": f"首次刷量人数必须在 1~{MAX_TOTAL_USER} 之间"},
                                status=status.HTTP_400_BAD_REQUEST)
            initial_count = initial_count_int
        per_user = request.data.get("per_user", 2)

        # 先建父任务
        pt = SMMPollTask.objects.create(
            account=account,
            youtube_link=youtube_link,
            key_words=key_words,
            per_user=per_user,
            task_type=int(request.data.get("task_type", 42) or 42),
            plant_form=int(request.data.get("plant_form", 1) or 1),
            comment_num=int(request.data.get("comment_num", 1) or 1),
            initial_count=int(initial_count) if initial_count else None,
            poll_total=int(poll_total),
            batch_min=batch_min,
            batch_max=batch_max,
            window_start_hour=window_start,
            window_end_hour=window_end,
            status=SMMPollTask.STATUS_RUNNING,
        )

        # 首次刷量：立即下单
        if initial_count:
            res = send_task(
                account.token, account.user_identifier, account.tg_user_id,
                youtube_link, key_words, int(initial_count),
                per_user=per_user, comment_num=pt.comment_num,
                end_hours=POLL_END_HOURS, plant_form=pt.plant_form, task_type=pt.task_type,
            )
            if res.get("code") in (0, None):
                d = res.get("data") or {}
                SMMTask.objects.create(
                    account=account, poll_task=pt,
                    panel_task_id=d.get("taskId") or "", show_id=d.get("showId") or "",
                    youtube_link=youtube_link, key_words=key_words,
                    total_user=int(initial_count), per_user=per_user,
                    task_type=pt.task_type, plant_form=pt.plant_form, comment_num=pt.comment_num,
                    end_time=d.get("endTime") or "",
                    cost=int(initial_count) * float(per_user),
                    status=SMMTask.STATUS_PENDING,
                )

        # 计算下次执行时间（窗口内下一个整点，北京时间）
        now = timezone.localtime(timezone.now())
        pt.next_poll_at = next_slot_after(now, window_start, window_end)
        pt.save(update_fields=["next_poll_at"])

        return Response(SMMPollTaskSerializer(pt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """停止轮询任务（不撤回已下单）。"""
        pt = self.get_object()
        if pt.status != SMMPollTask.STATUS_RUNNING:
            return Response({"detail": "任务不在运行中"}, status=status.HTTP_400_BAD_REQUEST)
        pt.status = SMMPollTask.STATUS_STOPPED
        pt.save(update_fields=["status", "updated_at"])
        return Response(SMMPollTaskSerializer(pt).data)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        """重启轮询任务：从当前时间之后的下一个窗口内整点继续，停掉的时间跳过不补。"""
        pt = self.get_object()
        if pt.status not in (SMMPollTask.STATUS_STOPPED, SMMPollTask.STATUS_FAILED):
            return Response({"detail": "只有已停止/失败的任务才能重启"}, status=status.HTTP_400_BAD_REQUEST)
        if pt.poll_done >= pt.poll_total:
            return Response({"detail": "任务已刷满，无需重启"}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.localtime(timezone.now())
        pt.next_poll_at = next_slot_after(now, pt.window_start_hour, pt.window_end_hour)
        pt.status = SMMPollTask.STATUS_RUNNING
        pt.fail_count = 0
        pt.save()
        return Response(SMMPollTaskSerializer(pt).data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """查轮询任务视频的实时统计（浏览量/点赞/评论）。纯读接口，不影响调度。"""
        pt = self.get_object()
        return _video_stats_response(pt.youtube_link)
