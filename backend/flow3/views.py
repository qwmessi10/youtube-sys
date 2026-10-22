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

from .models import Flow3Agent, Flow3Material, Flow3MaterialGroup, Flow3Run
from .serializers import (
    Flow3AgentSerializer,
    Flow3MaterialGroupSerializer,
    Flow3MaterialSerializer,
    Flow3RunCreateSerializer,
    Flow3RunSerializer,
)
from .prompt_store import export_one
from .services import (
    _generate_image_prompt,
    generate_hook_prompt,
    generate_image,
    generate_metadata,
    generate_narration_script,
    get_default_agent_prompt,
    probe_duration,
)
from .tasks import SEGB_TARGET_SHOT_COUNT, SEGB_TARGET_SHOT_DURATION, continue_flow3_run, process_flow3_run


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

    def perform_update(self, serializer):
        # 保存即写文件：提示词同步导出到 flow3/prompts/<agent_type>.md（文件为真相源，便于提交 git）。
        agent = serializer.save()
        try:
            export_one(agent.agent_type, agent.prompt)
        except Exception:
            pass

    @action(detail=True, methods=["get"])
    def default_prompt(self, request, pk=None):
        agent = self.get_object()
        return Response({"prompt": get_default_agent_prompt(agent.agent_type)})

    @action(detail=True, methods=["post"])
    def run_once(self, request, pk=None):
        """
        单独试运行某个 Agent（调试提示词用）。不创建任务、不消耗素材、不产视频。
        入参：keyword（必填）、promo_code、country、repeat（仅 hook，默认1，运行多次得多条 prompt）。
        返回该 Agent 的产出；hook 返回 prompts 列表，其余返回对应结构。
        """
        agent = self.get_object()
        keyword = (request.data.get("keyword") or "").strip()
        if not keyword:
            return Response({"detail": "请填写关键词。"}, status=status.HTTP_400_BAD_REQUEST)
        # 构造临时 Run（不保存到库），仅承载生成函数所需上下文。
        tmp = Flow3Run(
            keyword=keyword,
            promo_code=(request.data.get("promo_code") or "").strip(),
            country=(request.data.get("country") or "IN").strip(),
            language=(request.data.get("language") or "en-IN").strip(),
        )
        try:
            if agent.agent_type == Flow3Agent.AGENT_HOOK:
                repeat = int(request.data.get("repeat") or 1)
                repeat = max(1, min(repeat, 20))
                prompts = []
                for _ in range(repeat):
                    text, _log = generate_hook_prompt(tmp)
                    prompts.append(text)
                return Response({"agent_type": agent.agent_type, "prompts": prompts})
            if agent.agent_type == Flow3Agent.AGENT_NARRATION:
                data, _log = generate_narration_script(tmp, SEGB_TARGET_SHOT_COUNT, SEGB_TARGET_SHOT_DURATION)
                return Response({"agent_type": agent.agent_type, "narration": data})
            if agent.agent_type == Flow3Agent.AGENT_METADATA:
                data, _log = generate_metadata(tmp)
                # 试运行也直接按 thumbnail_prompt 生成封面图并返回预览 url。
                thumb_url = ""
                tp = (data.get("thumbnail_prompt") or "").strip()
                if tp:
                    try:
                        tn_file, tn_ext = generate_image(tp)
                        from django.core.files.storage import default_storage
                        name = default_storage.save(f"flow3/agent_test/thumb_{uuid.uuid4().hex}.{tn_ext}", tn_file)
                        thumb_url = default_storage.url(name)
                    except Exception as exc:
                        data["thumbnail_error"] = f"封面生成失败：{exc}"
                return Response({"agent_type": agent.agent_type, "metadata": data, "thumbnail_url": thumb_url})
            if agent.agent_type in (Flow3Agent.AGENT_BLUR_BG, Flow3Agent.AGENT_TAIL_IMAGE):
                text, _log = _generate_image_prompt(tmp, agent.agent_type)
                return Response({"agent_type": agent.agent_type, "image_prompt": text})
            return Response({"detail": "该 Agent 不支持试运行。"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"运行失败：{exc}"}, status=status.HTTP_400_BAD_REQUEST)


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
        group = self.request.query_params.get("group")
        if group:
            qs = qs.filter(group_id=group)
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

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def batch_upload(self, request):
        """批量上传素材（主要用于 Hook 视频）。参数：material_type + files（多文件）。新素材默认标签「未使用」。"""
        mtype = (request.data.get("material_type") or "").strip()
        if mtype not in dict(Flow3Material.TYPE_CHOICES):
            return Response({"detail": "material_type 无效。"}, status=status.HTTP_400_BAD_REQUEST)
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            return Response({"detail": "请选择要上传的文件。"}, status=status.HTTP_400_BAD_REQUEST)
        # hook 素材归属分组：传了 group 用之，否则落到默认分组（仅 hook 分组）。
        group = None
        if mtype == Flow3Material.TYPE_HOOK:
            gid = request.data.get("group")
            if gid:
                group = Flow3MaterialGroup.objects.filter(id=gid).first()
            if group is None:
                group = Flow3MaterialGroup.objects.filter(is_default=True).first()
        created = []
        for f in files:
            obj = Flow3Material.objects.create(
                material_type=mtype, name=f.name, file=f,
                tag=Flow3Material.TAG_UNUSED, enabled=True, group=group,
            )
            self._fill_duration(obj)
            created.append(obj)
        data = Flow3MaterialSerializer(created, many=True, context={"request": request}).data
        return Response({"detail": f"已上传 {len(created)} 个素材。", "items": data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request):
        """批量删除素材。参数：ids=[1,2,3]。一并删除磁盘文件。"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "请提供要删除的素材 id 列表。"}, status=status.HTTP_400_BAD_REQUEST)
        qs = Flow3Material.objects.filter(id__in=ids)
        count = qs.count()
        for m in qs:
            try:
                if m.file:
                    m.file.delete(save=False)
            except Exception:
                pass
        qs.delete()
        return Response({"detail": f"已删除 {count} 个素材。", "deleted": count})


class Flow3RunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
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
        data = dict(serializer.validated_data)
        count = data.pop("count", 1) or 1
        hook_group = data.get("hook_group")
        hook_material = data.get("hook_material")

        # 校验所选 hook 分组内「未使用 + 启用」素材数量（批量/随机都在该分组内取）。
        avail_qs = Flow3Material.objects.filter(
            material_type=Flow3Material.TYPE_HOOK, tag=Flow3Material.TAG_UNUSED, enabled=True,
        )
        if hook_group is not None:
            avail_qs = avail_qs.filter(group=hook_group)
        avail = list(avail_qs)

        if count > 1:
            # —— 批量模式：强制随机、不吃手动指定的 hook_material；数量不超过分组可用数 —— 
            data["hook_material"] = None
            if count > len(avail):
                gname = hook_group.name if hook_group else "（全部）"
                return Response(
                    {"detail": f"所选分组「{gname}」可用未使用 Hook 素材仅 {len(avail)} 个，无法批量生成 {count} 个任务。"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # 预分配不重复素材：打乱后依次分配并标记已使用。
            picks = random.sample(avail, count)
            runs = []
            for m in picks:
                r = Flow3Run.objects.create(
                    status=Flow3Run.STATUS_PENDING,
                    layout_seed=random.randint(0, 2_000_000_000),
                    bgm_seed=random.randint(0, 2_000_000_000),
                    promo_seed=random.randint(0, 2_000_000_000),
                    hook_material=m, **data,
                )
                m.tag = Flow3Material.TAG_USED
                m.save(update_fields=["tag", "updated_at"])
                runs.append(r)
                process_flow3_run.delay(r.id, str(r.task_token))
            return Response(Flow3RunSerializer(runs, many=True).data, status=status.HTTP_201_CREATED)

        # —— 单个模式 —— 
        # 若未手动指定素材、且选了分组却无可用素材 → 直接报错阻止创建。
        if hook_material is None and hook_group is not None and not avail:
            return Response(
                {"detail": f"所选分组「{hook_group.name}」无可用未使用的 Hook 素材，无法创建任务。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        run = Flow3Run.objects.create(
            status=Flow3Run.STATUS_PENDING,
            layout_seed=random.randint(0, 2_000_000_000),
            bgm_seed=random.randint(0, 2_000_000_000),
            promo_seed=random.randint(0, 2_000_000_000),
            **data,
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

    def _dispatch_retry(self, run):
        """重试失败任务：从失败步骤继续（各步幂等跳过已完成部分）。"""
        run.task_token = uuid.uuid4()
        run.status = Flow3Run.STATUS_RUNNING
        run.error_message = ""
        run.save(update_fields=["task_token", "status", "error_message", "updated_at"])
        # 已有 hook 视频（素材或已上传）→ 从 Step4~7 继续；否则从头（重新出 prompt）。
        if run.hook_video:
            continue_flow3_run.delay(run.id, str(run.task_token))
        else:
            process_flow3_run.delay(run.id, str(run.task_token))

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """手动重试：仅失败任务，从失败点继续。"""
        run = self.get_object()
        if run.status != Flow3Run.STATUS_FAILED:
            return Response({"detail": "只有失败的任务可以重试。"}, status=status.HTTP_409_CONFLICT)
        self._dispatch_retry(run)
        return Response(Flow3RunSerializer(run).data)

    @action(detail=False, methods=["post"])
    def bulk_retry(self, request):
        """批量重试：对 ids 里处于 failed 的任务逐个重试。参数：ids=[...]。"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "请提供要重试的任务 id 列表。"}, status=status.HTTP_400_BAD_REQUEST)
        runs = Flow3Run.objects.filter(id__in=ids, status=Flow3Run.STATUS_FAILED)
        n = 0
        for run in runs:
            self._dispatch_retry(run)
            n += 1
        return Response({"detail": f"已重试 {n} 个失败任务。", "retried": n})

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

    def _delete_run_files(self, run):
        """删除任务关联的所有媒体文件（成品/中间产物/上传/生图/音频），避免残留占空间。"""
        for f in (run.hook_video, run.blur_bg_file, run.tail_image_file,
                  run.segb_file, run.segc_file, run.rendered_file, run.thumbnail_file):
            try:
                if f:
                    f.delete(save=False)
            except Exception:
                pass
        # 旁白音频（JSON 里存相对路径）
        for a in (run.narration_audio or []):
            try:
                p = os.path.join(settings.MEDIA_ROOT, a.get("file", ""))
                if a.get("file") and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    def perform_destroy(self, instance):
        self._delete_run_files(instance)
        instance.delete()

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request):
        """批量删除任务。参数：ids=[1,2,3]。逐个清理媒体文件后删除记录。"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "请提供要删除的任务 id 列表。"}, status=status.HTTP_400_BAD_REQUEST)
        runs = Flow3Run.objects.filter(id__in=ids)
        count = runs.count()
        for run in runs:
            self._delete_run_files(run)
        runs.delete()
        return Response({"detail": f"已删除 {count} 个任务。", "deleted": count})

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


class Flow3MaterialGroupViewSet(viewsets.ModelViewSet):
    """Hook 素材分组的增删改查。默认分组不可删；删除分组时组内素材转入默认分组。"""
    queryset = Flow3MaterialGroup.objects.all()
    serializer_class = Flow3MaterialGroupSerializer
    pagination_class = None  # 分组数量少，不分页

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        if group.is_default:
            return Response({"detail": "默认分组不可删除。"}, status=status.HTTP_409_CONFLICT)
        default = Flow3MaterialGroup.objects.filter(is_default=True).first()
        # 组内素材转入默认分组（不连带删素材）。
        group.materials.update(group=default)
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
