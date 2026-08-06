import io
import os
import uuid
import zipfile

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from keywords.views import TenPerPagePagination

from .models import ContentAgent, ContentItem, ContentRun
from .serializers import (
    ContentAgentSerializer,
    ContentItemSerializer,
    ContentRunCreateSerializer,
    ContentRunSerializer,
)
from .services import get_default_agent_prompt
from .tasks import merge_content_item, process_content_run, regenerate_content_item


class ContentAgentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """内容生成 Agent 管理：列表 + 编辑（不开放增删，Agent 由迁移种子维护）。"""
    queryset = ContentAgent.objects.all()
    serializer_class = ContentAgentSerializer

    @action(detail=True, methods=["get"])
    def default_prompt(self, request, pk=None):
        """返回该 Agent 的系统内置默认提示词，供前端「恢复系统默认」使用。"""
        agent = self.get_object()
        return Response({"prompt": get_default_agent_prompt(agent.agent_type)})


class ContentRunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ContentRun.objects.prefetch_related("items").all()
    pagination_class = TenPerPagePagination

    def get_serializer_class(self):
        return ContentRunCreateSerializer if self.action == "create" else ContentRunSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(items__keyword__icontains=search)).distinct()
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        keywords = serializer.validated_data.pop("keywords")
        # 去重去空，保持顺序
        keywords = list(dict.fromkeys(kw.strip() for kw in keywords if kw.strip()))
        if not keywords:
            return Response({"detail": "请至少提供一个有效关键词。"}, status=status.HTTP_400_BAD_REQUEST)
        run = serializer.save(status=ContentRun.STATUS_RUNNING)
        ContentItem.objects.bulk_create([ContentItem(run=run, keyword=kw) for kw in keywords])
        process_content_run.delay(run.id, str(run.task_token))
        return Response(ContentRunSerializer(run).data, status=status.HTTP_201_CREATED)

    def _queue_restart(self, run):
        run.task_token = uuid.uuid4()
        run.status = ContentRun.STATUS_RUNNING
        run.error_message = ""
        run.save(update_fields=["task_token", "status", "error_message", "updated_at"])
        process_content_run.delay(run.id, str(run.task_token))

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        run = self.get_object()
        if run.status not in [ContentRun.STATUS_PENDING, ContentRun.STATUS_RUNNING]:
            return Response({"detail": "只有待处理或运行中的任务可以暂停。"}, status=status.HTTP_409_CONFLICT)
        run.status = ContentRun.STATUS_PAUSED
        run.task_token = uuid.uuid4()  # 让已排队/运行中的 worker 任务失效
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(ContentRunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        if run.status not in [ContentRun.STATUS_PENDING, ContentRun.STATUS_RUNNING, ContentRun.STATUS_PAUSED]:
            return Response({"detail": "只有未完成的任务可以停止。"}, status=status.HTTP_409_CONFLICT)
        run.status = ContentRun.STATUS_STOPPED
        run.task_token = uuid.uuid4()
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(ContentRunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        run = self.get_object()
        if run.status not in [ContentRun.STATUS_PAUSED, ContentRun.STATUS_STOPPED, ContentRun.STATUS_FAILED, ContentRun.STATUS_COMPLETED]:
            return Response({"detail": "只有已暂停、已停止、失败或已完成的任务可以重启。"}, status=status.HTTP_409_CONFLICT)
        self._queue_restart(run)
        return Response(ContentRunSerializer(run).data)

    @action(detail=True, methods=["get"])
    def log(self, request, pk=None):
        run = self.get_object()
        return Response({"name": run.name, "run_log": run.run_log or {}})


class ContentItemViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ContentItemSerializer
    pagination_class = TenPerPagePagination
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = ContentItem.objects.select_related("run").all()
        run_id = self.request.query_params.get("run")
        item_status = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if run_id:
            queryset = queryset.filter(run_id=run_id)
        if item_status:
            queryset = queryset.filter(status=item_status)
        if search:
            queryset = queryset.filter(keyword__icontains=search)
        return queryset

    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        """
        重新生成某条记录的 AI 内容（元数据/封面/分镜）。
        用于单条失败或部分失败（如封面 503）时的重试，不影响已上传的分镜视频。
        """
        item = self.get_object()
        if item.run.status == ContentRun.STATUS_RUNNING:
            return Response({"detail": "任务正在运行中，请稍候。"}, status=status.HTTP_409_CONFLICT)
        # 复位为待生成，交给单条生成任务；run 状态不变（不影响其它记录）。
        item.status = ContentItem.STATUS_PENDING
        item.error_message = ""
        item.save(update_fields=["status", "error_message", "updated_at"])
        regenerate_content_item.delay(item.id)
        return Response({"detail": "已重新开始生成，请稍候刷新。"})

    @action(detail=True, methods=["post"])
    def upload_clip(self, request, pk=None):
        """
        上传某条记录的一段分镜视频。
        参数：index（第几段，从 1 起）、file（视频文件）。只校验格式，不强制时长。
        """
        item = self.get_object()
        index = request.data.get("index")
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "请选择要上传的视频文件。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            index = int(index)
        except (TypeError, ValueError):
            return Response({"detail": "分镜序号 index 无效。"}, status=status.HTTP_400_BAD_REQUEST)
        # 只校验格式：按扩展名判断是否常见视频格式
        allowed = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in allowed:
            return Response({"detail": f"只支持视频文件（{'/'.join(sorted(allowed))}）。"}, status=status.HTTP_400_BAD_REQUEST)

        rel_dir = os.path.join("content", str(item.run_id), "clips")
        abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        filename = f"{item.id}_shot{index}{ext}"
        rel_path = os.path.join(rel_dir, filename).replace("\\", "/")
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        with open(abs_path, "wb") as dest:
            for chunk in upload.chunks():
                dest.write(chunk)

        # 更新 clip_files 列表：同一 index 覆盖，否则追加。
        clips = [c for c in (item.clip_files or []) if c.get("index") != index]
        clips.append({"index": index, "file": rel_path, "name": upload.name})
        item.clip_files = sorted(clips, key=lambda c: c.get("index", 0))
        item.save(update_fields=["clip_files", "updated_at"])
        return Response(ContentItemSerializer(item, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """触发合并该记录已上传的分镜视频为成品。"""
        item = self.get_object()
        expected = item.run.shot_count
        uploaded = len(item.clip_files or [])
        if uploaded < expected:
            return Response(
                {"detail": f"已上传 {uploaded} 段，需上传满 {expected} 段后再合并。"},
                status=status.HTTP_409_CONFLICT,
            )
        merge_content_item.delay(item.id)
        return Response({"detail": "已开始合并，请稍候刷新查看成品。"})

    @action(detail=True, methods=["get"])
    def package(self, request, pk=None):
        """
        成品打包下载（本期链路终点）：把成品视频 + 标题/描述/封面打成一个 zip。
        供人工在 AdsPower 手动上传。
        """
        item = self.get_object()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 元数据文本
            meta_text = (
                f"关键词：{item.keyword}\n\n"
                f"【标题】\n{item.title}\n\n"
                f"【描述】\n{item.description}\n\n"
                f"【封面提示词】\n{item.thumbnail_prompt}\n"
            )
            zf.writestr("metadata.txt", meta_text)
            # 封面
            if item.thumbnail_file and os.path.exists(item.thumbnail_file.path):
                zf.write(item.thumbnail_file.path, f"cover{os.path.splitext(item.thumbnail_file.name)[1]}")
            # 成品视频
            if item.merged_file and os.path.exists(item.merged_file.path):
                zf.write(item.merged_file.path, "final_video.mp4")
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="content_{item.id}_{timezone.now():%Y%m%d}.zip"'
        return response
