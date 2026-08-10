import io
import json
import math
import os
import uuid
import zipfile

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from keywords.views import TenPerPagePagination

from .models import ContentAgent, ContentItem, ContentRun, VideoTemplate
from .serializers import (
    ContentAgentSerializer,
    ContentItemSerializer,
    ContentRunCreateSerializer,
    ContentRunSerializer,
    VideoTemplateSerializer,
)
from .services import (
    analyze_reference_video,
    detect_scene_changes,
    extract_keyframes,
    get_default_agent_prompt,
    probe_video_duration,
)
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


class VideoTemplateViewSet(viewsets.ModelViewSet):
    """视频模板库：增删改查 + 上传参考视频分析 + 上传素材。"""
    queryset = VideoTemplate.objects.all()
    serializer_class = VideoTemplateSerializer
    pagination_class = TenPerPagePagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def analyze(self, request, pk=None):
        """
        上传参考视频并用 Gemini 分析，把分析规格存进 template.analysis。
        参数：file（视频文件）。分析较慢（几十秒到几分钟），同步返回结果。
        """
        template = self.get_object()
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "请选择要分析的视频文件。"}, status=status.HTTP_400_BAD_REQUEST)
        allowed = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in allowed:
            return Response({"detail": f"只支持视频文件（{'/'.join(sorted(allowed))}）。"}, status=status.HTTP_400_BAD_REQUEST)

        # 存参考视频到 media，再用绝对路径喂给 Gemini。
        template.source_video.save(f"{template.id}_{upload.name}", upload, save=True)
        video_abs = os.path.join(settings.MEDIA_ROOT, template.source_video.name)
        try:
            result = analyze_reference_video(video_abs)
        except Exception as exc:
            return Response({"detail": f"视频分析失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        # 关键帧抽取：合并「Gemini 认为重要的时间点」+「ffmpeg 客观检测的画面切换点」，
        # 去重后用 ffmpeg 各截一张图存盘（backend 容器有 ffmpeg）。这些图供开发/AI 对照复刻画面。
        gemini_kf = result.get("keyframes") or []
        scene_kf = detect_scene_changes(video_abs)
        merged_kf = sorted(set(round(float(t), 2) for t in (gemini_kf + scene_kf) if isinstance(t, (int, float))))
        kf_rel_dir = os.path.join("content", "templates", str(template.id), "keyframes")
        kf_abs_dir = os.path.join(settings.MEDIA_ROOT, kf_rel_dir)
        frames = extract_keyframes(video_abs, merged_kf, kf_abs_dir)
        # 存相对路径（media 下），前端可据此拼 URL 预览。
        keyframe_records = [
            {"time": f["time"], "file": os.path.join(kf_rel_dir, f["name"]).replace("\\", "/")}
            for f in frames
        ]

        template.analysis = {
            "model": result.get("model"),
            "text": result.get("text"),
            "spec": result.get("spec") or {},                 # 结构化规格（canvas/regions/shots）
            "keyframes": keyframe_records,                     # 抽好的关键帧图（时间+相对路径）
            "keyframe_times": merged_kf,                        # 合并后的关键帧时间点（供追溯）
            "scene_change_times": scene_kf,                    # ffmpeg 客观检测到的切换点
            "analyzed_at": timezone.now().isoformat(),
            "source_name": upload.name,
            "suggested_variables": result.get("suggested_variables") or [],
        }
        update_fields = ["analysis", "updated_at"]
        # AI 给出建议段数/时长则回填到模板（运营之后可在编辑里微调）。
        if result.get("shot_count"):
            template.shot_count = result["shot_count"]
            update_fields.append("shot_count")
        if result.get("shot_duration"):
            template.shot_duration = result["shot_duration"]
            update_fields.append("shot_duration")
        # 模板还没声明变量时，用 AI 建议的变量预填，省去运营手敲。
        if not template.variables_schema and result.get("suggested_variables"):
            template.variables_schema = [
                {
                    "key": (v.get("key") or "").strip(),
                    "label": (v.get("label") or v.get("key") or "").strip(),
                    "required": True,
                    "ai_editable": bool(v.get("ai_editable", False)),
                }
                for v in result["suggested_variables"]
                if isinstance(v, dict) and (v.get("key") or "").strip()
            ]
            update_fields.append("variables_schema")
        template.save(update_fields=update_fields)
        return Response(VideoTemplateSerializer(template, context={"request": request}).data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_asset(self, request, pk=None):
        """
        上传模板素材（录屏/logo 等）。参数：key（素材标识）、file。
        - 若上传的是视频素材：用 ffprobe 读时长存进 asset.duration，并按其时长自动设定
          模板总时长（段数 = ceil((素材时长 + 缓冲) / 每段时长)），保证模板时长 > 素材时长，
          素材播完后画面冻结在最后一帧（由 Remotion 组件处理）。
        """
        template = self.get_object()
        key = (request.data.get("key") or "").strip()
        upload = request.FILES.get("file")
        if not key or not upload:
            return Response({"detail": "请提供素材标识 key 和文件。"}, status=status.HTTP_400_BAD_REQUEST)
        rel_dir = os.path.join("content", "templates", str(template.id), "assets")
        abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        rel_path = os.path.join(rel_dir, upload.name).replace("\\", "/")
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        with open(abs_path, "wb") as dest:
            for chunk in upload.chunks():
                dest.write(chunk)

        # 视频素材读时长（图片/字体等读不到会返回 None，忽略）。
        duration = None
        ext = os.path.splitext(upload.name)[1].lower()
        if ext in {".mp4", ".mov", ".webm", ".mkv", ".m4v"}:
            duration = probe_video_duration(abs_path)

        # 覆盖同 key 素材，但保留原来的 source（AI/upload）等声明字段，避免丢失。
        prev = next((a for a in (template.assets or []) if a.get("key") == key), {})
        assets = [a for a in (template.assets or []) if a.get("key") != key]
        # 素材显示名优先用槽位声明里的 name（如“手机操作录屏”），没有再退回文件名。
        slot = next((s for s in (template.assets_schema or []) if s.get("key") == key), {})
        display_name = slot.get("name") or upload.name
        new_asset = {**prev, "key": key, "file": rel_path, "name": display_name, "filename": upload.name}
        if duration is not None:
            new_asset["duration"] = round(duration, 2)
        assets.append(new_asset)
        template.assets = assets
        update_fields = ["assets", "updated_at"]

        # 按素材时长自动设定模板总时长（仅当读到时长时）：
        # 段数 = ceil((素材时长 + 2秒缓冲) / 每段时长)，保证 段数×每段 > 素材时长。
        if duration is not None:
            per = template.shot_duration or 8
            new_count = max(1, math.ceil((duration + 2) / per))
            if new_count != template.shot_count:
                template.shot_count = new_count
                update_fields.append("shot_count")

        template.save(update_fields=update_fields)
        return Response(VideoTemplateSerializer(template, context={"request": request}).data)


class ContentRunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ContentRun.objects.prefetch_related("items").all()
    pagination_class = TenPerPagePagination
    # 支持 JSON（普通创建）与 multipart（流程一带变量 CSV 文件）两种提交。
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return ContentRunCreateSerializer if self.action == "create" else ContentRunSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(items__keyword__icontains=search)).distinct()
        return queryset

    def _normalize_create_data(self, request):
        """
        兼容 multipart 提交：keywords 可能是 JSON 字符串或多值字段，统一成列表。
        返回一个普通 dict 供序列化器使用。
        """
        data = request.data
        payload = {k: v for k, v in data.items()}
        # keywords：multipart 下前端传 JSON 字符串；DRF 列表字段需要真正的列表
        kws = data.getlist("keywords") if hasattr(data, "getlist") else data.get("keywords")
        if isinstance(kws, list) and len(kws) == 1 and isinstance(kws[0], str) and kws[0].strip().startswith("["):
            try:
                kws = json.loads(kws[0])
            except Exception:
                pass
        elif isinstance(kws, str):
            try:
                kws = json.loads(kws)
            except Exception:
                kws = [kws]
        payload["keywords"] = kws
        return payload

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=self._normalize_create_data(request))
        serializer.is_valid(raise_exception=True)
        keywords = serializer.validated_data.pop("keywords")
        # 流程一的模板变量取值（所有视频共用一组），从校验数据里取出，不进 run 模型。
        shared_vars = serializer.validated_data.pop("variables", None) or {}
        # 去重去空，保持顺序
        keywords = list(dict.fromkeys(kw.strip() for kw in keywords if kw.strip()))
        if not keywords:
            return Response({"detail": "请至少提供一个有效关键词。"}, status=status.HTTP_400_BAD_REQUEST)

        run = serializer.save(status=ContentRun.STATUS_RUNNING)

        if run.flow == ContentRun.FLOW_AUTO:
            # 流程一：一个关键词 + 一个模板 + N 组变量 → N 条 item。
            # 一个关键词一个任务，按 video_count 复制 N 条，每条共用同一组模板变量。
            keyword = keywords[0]  # 流程一只取第一个关键词
            # 变量取值统一放进 item.variables（promo_code 等都在这里，不再特殊处理）。
            shared = {k: str(v).strip() for k, v in shared_vars.items() if str(v).strip()}
            groups = [dict(shared) for _ in range(max(1, run.video_count))]
            ContentItem.objects.bulk_create([
                ContentItem(run=run, keyword=keyword, variables=g) for g in groups
            ])
        else:
            # 流程二：每个关键词一条 item
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
            # 成品视频：流程二取合并成品，流程一取 Remotion 渲染成品。
            final_file = item.merged_file or item.rendered_file
            if final_file and os.path.exists(final_file.path):
                zf.write(final_file.path, "final_video.mp4")
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="content_{item.id}_{timezone.now():%Y%m%d}.zip"'
        return response
