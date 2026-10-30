import os

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import AdsPowerProfile, UploadTask
from .serializers import (
    AdsPowerProfileSerializer,
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
    AdsPower 浏览器环境管理：列表 / 详情 / 同步 / 分组 / 打开浏览器。
    数据来自本地 API 缓存（AdsPowerProfile）。lookup 用 user_id。
    """
    queryset = AdsPowerProfile.objects.all()
    serializer_class = AdsPowerProfileSerializer
    pagination_class = TenPerPagePagination
    lookup_field = "user_id"

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
