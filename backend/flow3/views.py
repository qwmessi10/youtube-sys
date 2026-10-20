import io
import os
import random
import uuid
import zipfile

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Flow3Agent, Flow3Material, Flow3Run
from .serializers import (
    Flow3AgentSerializer,
    Flow3MaterialSerializer,
    Flow3RunCreateSerializer,
    Flow3RunSerializer,
)
from .services import get_default_agent_prompt, probe_duration
from .tasks import continue_flow3_run, process_flow3_run


class TenPerPagePagination(PageNumberPagination):
    """每页 10 条（flow3 自持，不依赖 keywords）。"""
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class Flow3AgentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """流程3 Agent 管理：列表 + 编辑 prompt/enabled（Agent 由迁移种子维护，不增删）。"""
    queryset = Flow3Agent.objects.all()
    serializer_class = Flow3AgentSerializer

    @action(detail=True, methods=["get"])
    def default_prompt(self, request, pk=None):
        agent = self.get_object()
        return Response({"prompt": get_default_agent_prompt(agent.agent_type)})


class Flow3MaterialViewSet(viewsets.ModelViewSet):
    """流程3 素材库：9:16 录屏 + BGM 的增删改查。上传时自动探测时长。"""
    queryset = Flow3Material.objects.all()
    serializer_class = Flow3MaterialSerializer
    pagination_class = TenPerPagePagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        mtype = self.request.query_params.get("type")
        if mtype:
            qs = qs.filter(material_type=mtype)
        return qs

    def perform_create(self, serializer):
        # 上传即默认启用（避免前端未显式传 enabled 时被存成停用）。
        obj = serializer.save(enabled=True)
        self._fill_duration(obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        self._fill_duration(obj)

    def _fill_duration(self, obj):
        """探测并回填素材时长（视频/音频）。"""
        if not obj.file:
            return
        abs_path = os.path.join(settings.MEDIA_ROOT, obj.file.name)
        dur = probe_duration(abs_path)
        if dur is not None and obj.duration != round(dur, 2):
            obj.duration = round(dur, 2)
            obj.save(update_fields=["duration", "updated_at"])


class Flow3RunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """流程3 任务：创建（出 Hook prompt）、列表、Hook 上传、继续、暂停/停止/重启、日志、打包。"""
    queryset = Flow3Run.objects.all()
    pagination_class = TenPerPagePagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return Flow3RunCreateSerializer if self.action == "create" else Flow3RunSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(keyword__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 随机种子：左右布局 + BGM 抽取，创建时定下并记录，便于复现。
        run = serializer.save(
            status=Flow3Run.STATUS_PENDING,
            layout_seed=random.randint(0, 2_000_000_000),
            bgm_seed=random.randint(0, 2_000_000_000),
        )
        process_flow3_run.delay(run.id, str(run.task_token))
        return Response(Flow3RunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_hook(self, request, pk=None):
        """上传 Hook 视频 mp4（单个）。仅在 awaiting_hook 态允许。"""
        run = self.get_object()
        if run.status != Flow3Run.STATUS_AWAITING_HOOK:
            return Response({"detail": "当前任务不在等待 Hook 上传状态。"}, status=status.HTTP_409_CONFLICT)
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "请选择要上传的 Hook 视频文件。"}, status=status.HTTP_400_BAD_REQUEST)
        allowed = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in allowed:
            return Response({"detail": f"只支持视频文件（{'/'.join(sorted(allowed))}）。"},
                            status=status.HTTP_400_BAD_REQUEST)
        run.hook_video.save(f"{run.id}_hook{ext}", upload, save=True)
        return Response(Flow3RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Hook 上传完成后点「继续」，触发 Step4~7。"""
        run = self.get_object()
        if run.status != Flow3Run.STATUS_AWAITING_HOOK:
            return Response({"detail": "当前任务不在等待 Hook 状态，无法继续。"}, status=status.HTTP_409_CONFLICT)
        if not run.hook_video:
            return Response({"detail": "请先上传 Hook 视频。"}, status=status.HTTP_400_BAD_REQUEST)
        run.task_token = uuid.uuid4()
        run.status = Flow3Run.STATUS_RUNNING
        run.save(update_fields=["task_token", "status", "updated_at"])
        continue_flow3_run.delay(run.id, str(run.task_token))
        return Response(Flow3RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        run = self.get_object()
        if run.status not in [Flow3Run.STATUS_PENDING, Flow3Run.STATUS_RUNNING]:
            return Response({"detail": "只有待处理或运行中的任务可暂停。"}, status=status.HTTP_409_CONFLICT)
        run.status = Flow3Run.STATUS_PAUSED
        run.task_token = uuid.uuid4()
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(Flow3RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        if run.status in [Flow3Run.STATUS_COMPLETED, Flow3Run.STATUS_STOPPED]:
            return Response({"detail": "任务已结束。"}, status=status.HTTP_409_CONFLICT)
        run.status = Flow3Run.STATUS_STOPPED
        run.task_token = uuid.uuid4()
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(Flow3RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        """重启：从头跑（重新出 Hook prompt，再次进入等待上传）。"""
        run = self.get_object()
        if run.status not in [Flow3Run.STATUS_PAUSED, Flow3Run.STATUS_STOPPED,
                              Flow3Run.STATUS_FAILED, Flow3Run.STATUS_COMPLETED]:
            return Response({"detail": "只有已暂停/停止/失败/完成的任务可重启。"}, status=status.HTTP_409_CONFLICT)
        run.task_token = uuid.uuid4()
        run.status = Flow3Run.STATUS_RUNNING
        run.error_message = ""
        run.save(update_fields=["task_token", "status", "error_message", "updated_at"])
        process_flow3_run.delay(run.id, str(run.task_token))
        return Response(Flow3RunSerializer(run).data)

    @action(detail=True, methods=["get"])
    def log(self, request, pk=None):
        run = self.get_object()
        return Response({"name": run.name, "run_log": run.run_log or {}})

    @action(detail=True, methods=["get"])
    def package(self, request, pk=None):
        """成品打包：元数据 txt + 成品视频 → zip（flow3 独立实现，不复用 content_gen）。"""
        run = self.get_object()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            meta_text = (
                f"关键词：{run.keyword}\n\n"
                f"【标题】\n{run.title}\n\n"
                f"【描述】\n{run.description}\n\n"
                f"【封面提示词】\n{run.thumbnail_prompt}\n\n"
                f"【优惠码】\n{run.promo_code}\n"
            )
            zf.writestr("metadata.txt", meta_text)
            # 封面图（按 thumbnail_prompt 生成）
            if run.thumbnail_file and os.path.exists(run.thumbnail_file.path):
                ext = os.path.splitext(run.thumbnail_file.name)[1] or ".jpg"
                zf.write(run.thumbnail_file.path, f"cover{ext}")
            if run.rendered_file and os.path.exists(run.rendered_file.path):
                zf.write(run.rendered_file.path, "final_video.mp4")
        buffer.seek(0)
        resp = HttpResponse(buffer.getvalue(), content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="flow3_{run.id}_{timezone.now():%Y%m%d}.zip"'
        return resp
