import os
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import AdsPowerProfile, ProxyConfig, UploadTask
from .serializers import (
    AdsPowerProfileSerializer,
    AdsPowerProfileWriteSerializer,
    ProxyConfigSerializer,
    UploadTaskCreateSerializer,
    UploadTaskPayloadSerializer,
    UploadTaskSerializer,
)
from . import services


class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 200


def _check_agent_token(request):
    """执行器接口鉴权：校验 header X-Agent-Token 与全局设置 UPLOADER_AGENT_TOKEN 一致。"""
    expected = services.get_setting("UPLOADER_AGENT_TOKEN", "")
    provided = request.headers.get("X-Agent-Token", "")
    # 未配置 token 时放行（开发便利）；配置了则必须匹配。
    return (not expected) or (provided == expected)


class AdsPowerProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    AdsPower 浏览器环境管理：列表 / 详情 / 同步 / 分组 / 打开浏览器 + 增删改 / 设置 IP。
    读数据来自本地缓存（AdsPowerProfile）；写操作直连 AdsPower 本地 API 后回灌缓存。lookup 用 user_id。
    """
    queryset = AdsPowerProfile.objects.all()
    serializer_class = AdsPowerProfileSerializer
    pagination_class = TenPerPagePagination
    lookup_field = "user_id"

    def _resolve_proxy(self, data):
        """
        解析请求里的代理来源，返回 AdsPower user_proxy_config。
        优先级：proxy_id（引用本地 IP 池）> proxy_config（直接传）> 无代理。
        未提供任何代理信息时返回 None（表示不改动代理 / 建环境时用无代理）。
        """
        proxy_id = data.get("proxy_id")
        if proxy_id:
            try:
                proxy = ProxyConfig.objects.get(pk=proxy_id)
            except ProxyConfig.DoesNotExist:
                raise ValueError("所选 IP 不存在，请先在 IP 管理中添加")
            return proxy.to_adspower_config()
        cfg = data.get("proxy_config")
        if isinstance(cfg, dict) and cfg:
            return cfg
        return None

    def create(self, request, *args, **kwargs):
        """新建 AdsPower 环境：调用 user/create，成功后同步缓存。"""
        ser = AdsPowerProfileWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        group_id = v.get("group_id") or "0"
        try:
            proxy_config = self._resolve_proxy(request.data) or {"proxy_soft": "no_proxy"}
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = services.create_profile(
                group_id=group_id,
                name=v.get("name", ""),
                domain_name=v.get("domain_name", ""),
                remark=v.get("remark", ""),
                proxy_config=proxy_config,
            )
            services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "环境已创建", "data": data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """编辑 AdsPower 环境（名称 / 平台 / 备注 / 分组 / IP）。"""
        return self._do_update(request, kwargs.get("user_id"))

    def partial_update(self, request, *args, **kwargs):
        return self._do_update(request, kwargs.get("user_id"))

    def _do_update(self, request, user_id):
        ser = AdsPowerProfileWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        try:
            proxy_config = self._resolve_proxy(request.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        kwargs = {}
        if "name" in v:
            kwargs["name"] = v["name"]
        if "domain_name" in v:
            kwargs["domain_name"] = v["domain_name"]
        if "remark" in v:
            kwargs["remark"] = v["remark"]
        if v.get("group_id"):
            kwargs["group_id"] = v["group_id"]
        if proxy_config is not None:
            kwargs["proxy_config"] = proxy_config
        try:
            services.update_profile(user_id, **kwargs)
            services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        try:
            obj = AdsPowerProfile.objects.get(user_id=user_id)
            return Response(AdsPowerProfileSerializer(obj).data)
        except AdsPowerProfile.DoesNotExist:
            return Response({"detail": "环境已更新"})

    def destroy(self, request, *args, **kwargs):
        """删除 AdsPower 环境：先拦截仍被进行中任务引用的环境，再调 user/delete。"""
        user_id = kwargs.get("user_id")
        active_tasks = UploadTask.objects.filter(
            profile__user_id=user_id,
            status__in=[UploadTask.STATUS_QUEUED, UploadTask.STATUS_LAUNCHING,
                        UploadTask.STATUS_UPLOADING, UploadTask.STATUS_PUBLISHING],
        ).count()
        if active_tasks:
            return Response(
                {"detail": f"该环境还有 {active_tasks} 个进行中的上传任务，无法删除"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            services.delete_profiles([user_id])
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        AdsPowerProfile.objects.filter(user_id=user_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-proxy")
    def set_proxy(self, request, user_id=None):
        """单独给某环境设置 / 更换 IP。"""
        try:
            proxy_config = self._resolve_proxy(request.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if proxy_config is None:
            proxy_config = {"proxy_soft": "no_proxy"}
        try:
            services.update_profile(user_id, proxy_config=proxy_config)
            services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "IP 已更新"})

    @action(detail=False, methods=["post"], url_path="create-group")
    def create_group(self, request):
        """新建分组。"""
        name = (request.data.get("group_name") or "").strip()
        if not name:
            return Response({"detail": "分组名称不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = services.create_group(name, request.data.get("remark", ""))
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "分组已创建", "data": data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="update-group")
    def update_group(self, request):
        """修改分组名 / 备注。"""
        group_id = request.data.get("group_id")
        name = (request.data.get("group_name") or "").strip()
        if not group_id or not name:
            return Response({"detail": "分组 ID 和名称必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            services.update_group(group_id, name, request.data.get("remark", ""))
            services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "分组已更新"})

    @action(detail=False, methods=["post"], url_path="regroup")
    def regroup(self, request):
        """把环境批量移动到目标分组。"""
        user_ids = request.data.get("user_ids") or ([request.data["user_id"]] if request.data.get("user_id") else [])
        group_id = request.data.get("group_id")
        if not user_ids or not group_id:
            return Response({"detail": "user_ids 和 group_id 必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            services.regroup_profiles(user_ids, group_id)
            services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "已移动分组"})

    def get_queryset(self):
        qs = super().get_queryset()
        group_id = self.request.query_params.get("group_id")
        search = self.request.query_params.get("search")
        if group_id:
            qs = qs.filter(group_id=group_id)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @action(detail=False, methods=["post"])
    def sync(self, request):
        """从 AdsPower 本地 API 全量拉取环境列表，更新缓存。"""
        try:
            result = services.sync_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)

    @action(detail=False, methods=["get"])
    def groups(self, request):
        """返回 AdsPower 分组列表（供前端筛选下拉）。"""
        try:
            data = services.list_groups()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(data.get("list") or [])

    @action(detail=False, methods=["get"])
    def api_status(self, request):
        """探测 AdsPower 本地 API 是否可用。"""
        return Response({"ok": services.check_status()})

    @action(detail=True, methods=["post"])
    def open(self, request, user_id=None):
        """在宿主拉起该环境的真实浏览器（懒得开客户端也能开浏览器）。"""
        try:
            data = services.start_browser(user_id)
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "浏览器已启动", "data": data})

    @action(detail=True, methods=["post"])
    def close(self, request, user_id=None):
        """关闭该环境浏览器。"""
        try:
            services.stop_browser(user_id)
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": "浏览器已关闭"})

    @action(detail=True, methods=["get"])
    def active(self, request, user_id=None):
        """查询该环境浏览器是否已打开。"""
        try:
            data = services.browser_active(user_id)
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(data)


class UploadTaskViewSet(viewsets.ModelViewSet):
    """
    自动化上传任务：增删改查 + from-run（从 flow3 成品创建）+ retry
    + 执行器专用接口（next / payload / callback / progress）。
    """
    queryset = UploadTask.objects.select_related("profile", "source_run").all()
    pagination_class = TenPerPagePagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == "create":
            return UploadTaskCreateSerializer
        return UploadTaskSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs

    def _recover_stale_claims(self):
        """把异常退出执行器遗留的领取中任务重新放回队列，避免永久卡在 launching/uploading。"""
        try:
            timeout_minutes = max(1, int(services.get_setting("UPLOADER_TASK_LOCK_TIMEOUT_MINUTES", "30") or 30))
        except (TypeError, ValueError):
            timeout_minutes = 30
        deadline = timezone.now() - timedelta(minutes=timeout_minutes)
        stale = UploadTask.objects.filter(
            status__in=[UploadTask.STATUS_LAUNCHING, UploadTask.STATUS_UPLOADING],
            locked_at__lt=deadline,
        )
        return stale.update(status=UploadTask.STATUS_QUEUED, locked_at=None)

    @action(detail=False, methods=["post"])
    def recover_stale(self, request):
        """人工触发超时任务回收。正常执行器领取 next 时也会自动执行一次。"""
        recovered = self._recover_stale_claims()
        return Response({"recovered": recovered})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        if not task.name:
            task.name = task.title or f"上传任务 #{task.pk}"
            task.save(update_fields=["name"])
        # 返回完整任务数据（而非 Create 序列化器的精简字段）
        return Response(UploadTaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="from-run")
    def from_run(self, request):
        """
        从 flow3 已完成任务创建上传任务：传 run_id + profile（user_id）+ publish_mode。
        后端自动填充 title / description / video_path / cover_path。
        """
        from flow3.models import Flow3Run

        run_id = request.data.get("run_id")
        profile_uid = request.data.get("profile")
        publish_mode = request.data.get("publish_mode", UploadTask.MODE_DRAFT)
        if not run_id or not profile_uid:
            return Response({"detail": "run_id 和 profile 必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            run = Flow3Run.objects.get(pk=run_id)
        except Flow3Run.DoesNotExist:
            return Response({"detail": "flow3 任务不存在"}, status=status.HTTP_404_NOT_FOUND)
        if run.status != Flow3Run.STATUS_COMPLETED:
            return Response({"detail": "只能上传已完成的任务"}, status=status.HTTP_400_BAD_REQUEST)
        if not run.rendered_file:
            return Response({"detail": "该任务没有成品视频"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = AdsPowerProfile.objects.get(user_id=profile_uid)
        except AdsPowerProfile.DoesNotExist:
            return Response({"detail": "目标浏览器不存在，请先同步"}, status=status.HTTP_404_NOT_FOUND)

        task = UploadTask.objects.create(
            name=run.title or run.keyword,
            source_run=run,
            profile=profile,
            video_path=run.rendered_file.name,
            title=run.title or "",
            description=run.description or "",
            cover_path=run.thumbnail_file.name if run.thumbnail_file else "",
            publish_mode=publish_mode,
        )
        return Response(UploadTaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """失败任务重试：重置为 queued。"""
        task = self.get_object()
        if task.status != UploadTask.STATUS_FAILED:
            return Response({"detail": "只有失败的任务可重试"}, status=status.HTTP_400_BAD_REQUEST)
        task.status = UploadTask.STATUS_QUEUED
        task.error_message = ""
        task.retry_count += 1
        task.locked_at = None
        task.save(update_fields=["status", "error_message", "retry_count", "locked_at"])
        return Response(UploadTaskSerializer(task).data)

    # ===================================================================
    # 执行器专用接口（宿主 Uploader Agent 调用，X-Agent-Token 鉴权）
    # ===================================================================
    @action(detail=False, methods=["get"])
    def next(self, request):
        """领取下一个 queued 任务，原子置为 launching（防并发重复领取）。"""
        if not _check_agent_token(request):
            return Response({"detail": "token 无效"}, status=status.HTTP_403_FORBIDDEN)
        # 先回收因执行器崩溃、网络中断等原因遗留的锁；不会影响仍在时限内的正常任务。
        self._recover_stale_claims()
        with transaction.atomic():
            task = (UploadTask.objects.select_for_update(skip_locked=True)
                    .filter(status=UploadTask.STATUS_QUEUED).order_by("created_at").first())
            if not task:
                return Response({}, status=status.HTTP_204_NO_CONTENT)
            task.status = UploadTask.STATUS_LAUNCHING
            task.locked_at = timezone.now()
            task.save(update_fields=["status", "locked_at"])
        return Response(UploadTaskPayloadSerializer(task, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def payload(self, request, pk=None):
        """返回结构化上传数据 + 文件下载直链（不走 zip）。"""
        if not _check_agent_token(request):
            return Response({"detail": "token 无效"}, status=status.HTTP_403_FORBIDDEN)
        task = self.get_object()
        return Response(UploadTaskPayloadSerializer(task, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def callback(self, request, pk=None):
        """执行器回调结果：{status, video_url, upload_log, error_message}。"""
        if not _check_agent_token(request):
            return Response({"detail": "token 无效"}, status=status.HTTP_403_FORBIDDEN)
        task = self.get_object()
        new_status = request.data.get("status")
        valid = dict(UploadTask.STATUS_CHOICES)
        if new_status not in valid:
            return Response({"detail": f"非法状态 {new_status}"}, status=status.HTTP_400_BAD_REQUEST)
        task.status = new_status
        if "video_url" in request.data:
            task.video_url = request.data.get("video_url") or ""
        if "error_message" in request.data:
            task.error_message = request.data.get("error_message") or ""
        if "upload_log" in request.data:
            task.upload_log = request.data.get("upload_log") or {}
        if new_status in (UploadTask.STATUS_DRAFT_SAVED, UploadTask.STATUS_COMPLETED, UploadTask.STATUS_FAILED):
            task.finished_at = timezone.now()
        task.save()
        # 回填到关联的 flow3 任务（可选，不阻断）
        if task.source_run and task.video_url:
            try:
                run = task.source_run
                log = run.run_log or {}
                log["youtube_upload"] = {"url": task.video_url, "status": new_status}
                run.run_log = log
                run.save(update_fields=["run_log"])
            except Exception:
                pass
        return Response(UploadTaskSerializer(task).data)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        """上报中间进度 / 截图路径（合并进 upload_log.steps）。"""
        if not _check_agent_token(request):
            return Response({"detail": "token 无效"}, status=status.HTTP_403_FORBIDDEN)
        task = self.get_object()
        log = task.upload_log or {}
        steps = log.get("steps") or []
        steps.append({
            "ts": timezone.now().isoformat(),
            "step": request.data.get("step", ""),
            "note": request.data.get("note", ""),
            "screenshot": request.data.get("screenshot", ""),
        })
        log["steps"] = steps
        task.upload_log = log
        task.save(update_fields=["upload_log"])
        return Response({"detail": "ok"})


class ProxyConfigViewSet(viewsets.ModelViewSet):
    """
    本地 IP / 代理池管理（IP 管理页）。纯本地 CRUD + 从环境同步 + IP 归属地验证。
    新建 / 编辑环境时从这里挑 IP 套用到环境的 user_proxy_config。
    """
    queryset = ProxyConfig.objects.all()
    serializer_class = ProxyConfigSerializer
    pagination_class = TenPerPagePagination

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # 注入"IP→使用它的环境"映射，供列表标注已分配/未分配（一次算好，避免 N 次查询）。
        ctx["usage_map"] = services.proxy_usage_map()
        return ctx

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=search) | Q(proxy_host__icontains=search))
        # 按分配状态筛选：assigned=已分配 / unassigned=未分配
        assigned = self.request.query_params.get("assigned")
        if assigned in ("assigned", "unassigned"):
            usage = services.proxy_usage_map()
            used_keys = set(usage.keys())
            ids = [p.id for p in qs if (f"{p.proxy_host}:{p.proxy_port}" in used_keys) == (assigned == "assigned")]
            qs = qs.filter(id__in=ids)
        return qs

    def update(self, request, *args, **kwargs):
        """编辑 IP：保存本地后，把新配置推送到所有使用该 IP 的 AdsPower 环境。"""
        instance = self.get_object()
        old_host, old_port = instance.proxy_host, instance.proxy_port
        resp = super().update(request, *args, **kwargs)
        instance.refresh_from_db()
        affected = 0
        try:
            affected = services.apply_proxy_to_profiles(
                old_host, old_port, instance.to_adspower_config())
        except services.AdsPowerError as e:
            # 本地已存，但推送 AdsPower 失败：回传提示，不吞错。
            resp.data["sync_warning"] = f"本地已保存，但同步到 AdsPower 失败：{e}"
            return resp
        resp.data["synced_profiles"] = affected
        return resp

    def destroy(self, request, *args, **kwargs):
        """删除前提示该 IP 是否仍被环境引用（仅提示，不阻断——环境侧代理是副本）。"""
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="import-from-adspower")
    def import_from_adspower(self, request):
        """把现有 AdsPower 环境里的代理同步进 IP 池（先 sync 环境，再提取去重）。"""
        try:
            services.sync_profiles()
            result = services.sync_proxies_from_profiles()
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="verify-geo")
    def verify_geo(self, request, pk=None):
        """用 IP2Location 验证该 IP 的归属地并保存。"""
        proxy = self.get_object()
        try:
            data = services.geolocate_ip(proxy.proxy_host)
        except services.AdsPowerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response({"detail": f"验证失败：{e}"}, status=status.HTTP_502_BAD_GATEWAY)
        proxy.geo_info = data
        proxy.verified_at = timezone.now()
        proxy.save(update_fields=["geo_info", "verified_at"])
        return Response(ProxyConfigSerializer(proxy, context=self.get_serializer_context()).data)
