import csv
import os
import uuid

from django.http import HttpResponse
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AgentPrompt, GlobalSetting, KeywordResult, KeywordRun, SuggestExpansionRun
from .serializers import (
    COUNTRIES, LANGUAGES,
    AgentPromptSerializer, GlobalSettingSerializer, KeywordResultSerializer, KeywordRunSerializer,
    SuggestExpansionDetailSerializer, SuggestExpansionRunSerializer,
)
from .services import get_default_agent_prompt
from .tasks import process_keyword_run, process_suggest_expansion

DEFAULT_SETTINGS = [
    ("SERPAPI_API_KEY", "SerpApi YouTube Search API Key"),
    ("YOUTUBE_API_KEY", "YouTube Data API V3 Key"),
    ("SERPAPI_QPS", "SerpApi 每秒最大请求数，控制限流，默认 1"),
    ("SERPAPI_MAX_RETRIES", "SerpApi/YouTube 遇 429 或 5xx 时的重试次数，默认 2"),
    ("AI_BASE_URL", "AI 接口地址（OpenAI 兼容中转，如 moretokens）"),
    ("AI_API_KEY", "AI API Key（打分模型 2.0 博彩意图筛选 / 文案 Agent 默认 Key）"),
    ("AI_MODEL", "AI 模型名（全局默认文案模型），默认 gemini-3.8-flash-high"),
    ("AI_MODELS", "文案 Agent 可选模型清单（逗号分隔）。在此新增模型，内容生成 Agent 管理的模型下拉会自动出现该选项"),
    ("AI_MODEL_KEYS", '按模型指定专属 API Key 的映射（JSON：{"模型名":"apikey"}）。未列出的模型回退 AI_API_KEY。用于不同模型走不同 Key，如 Claude 用独立 Key'),
    ("GEMINI_IMAGE_API_KEY", "内容生成-封面出图 API Key（留空则复用 AI_API_KEY）"),
    ("GEMINI_IMAGE_MODEL", "内容生成-封面图片模型名，默认 gemini-3.1-flash-image"),
    ("TTS_PROVIDER", "内容生成流程一-旁白 TTS 引擎，edge（默认免费）/ elevenlabs"),
    ("TTS_VOICE", "内容生成流程一-旁白音色，留空按语言自动选（edge 如 en-US-GuyNeural）"),
    ("ELEVENLABS_API_KEY", "内容生成流程一-ElevenLabs API Key（选 elevenlabs 时用）"),
    ("ELEVENLABS_VOICE_ID", "内容生成流程一-ElevenLabs 音色 ID（留空用默认）"),
    ("REMOTION_RENDER_URL", "内容生成流程一-Remotion 渲染服务地址（走 HTTP 调用时用）"),
]

SCORE_LABELS = {
    "title_mismatch": "标题未完全匹配", "low_subscriber": "低订阅频道", "low_view": "低播放视频", "published_over_24h": "发布超过 24 小时",
}
VIDEO_CSV_FIELDS = [
    ("title", "视频标题"), ("video_url", "YouTube 视频链接"), ("channel_name", "频道名称"),
    ("channel_id", "频道 ID"), ("subscriber_count", "频道订阅数"), ("view_count", "播放量"),
    ("like_count", "点赞数"), ("comment_count", "评论数"), ("published_at", "发布时间"),
]


class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = None


@api_view(["GET"])
def keyword_options(request):
    return Response({
        "countries": [{"value": value, "label": label} for value, label in COUNTRIES],
        "languages": [{"value": value, "label": label} for value, label in LANGUAGES],
    })


def ensure_default_settings():
    for key, description in DEFAULT_SETTINGS:
        GlobalSetting.objects.get_or_create(
            key=key,
            defaults={"value": os.getenv(key, ""), "description": description},
        )


class GlobalSettingViewSet(viewsets.ModelViewSet):
    queryset = GlobalSetting.objects.all()
    serializer_class = GlobalSettingSerializer

    def list(self, request, *args, **kwargs):
        ensure_default_settings()
        return super().list(request, *args, **kwargs)


class KeywordRunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = KeywordRun.objects.prefetch_related("results").all()
    serializer_class = KeywordRunSerializer
    pagination_class = TenPerPagePagination

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(root_keyword__icontains=search)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save(status=KeywordRun.STATUS_RUNNING)
        process_keyword_run.delay(run.id, str(run.task_token))
        return Response(self.get_serializer(run).data, status=status.HTTP_201_CREATED)

    def _queue_restart(self, run):
        run.task_token = uuid.uuid4()
        run.status = KeywordRun.STATUS_RUNNING
        run.error_message = ""
        run.save(update_fields=["task_token", "status", "error_message", "updated_at"])
        process_keyword_run.delay(run.id, str(run.task_token))

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        run = self.get_object()
        if run.status not in [KeywordRun.STATUS_PENDING, KeywordRun.STATUS_RUNNING]:
            return Response({"detail": "只有待处理或运行中的任务可以暂停。"}, status=status.HTTP_409_CONFLICT)
        run.status = KeywordRun.STATUS_PAUSED
        run.task_token = uuid.uuid4()  # Invalidate an already queued/running worker task.
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        if run.status not in [KeywordRun.STATUS_PENDING, KeywordRun.STATUS_RUNNING, KeywordRun.STATUS_PAUSED]:
            return Response({"detail": "只有未完成的任务可以停止。"}, status=status.HTTP_409_CONFLICT)
        run.status = KeywordRun.STATUS_STOPPED
        run.task_token = uuid.uuid4()
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        run = self.get_object()
        if run.status not in [KeywordRun.STATUS_PAUSED, KeywordRun.STATUS_STOPPED, KeywordRun.STATUS_FAILED]:
            return Response({"detail": "只有已暂停、已停止或失败的任务可以重启。"}, status=status.HTTP_409_CONFLICT)
        self._queue_restart(run)
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["get"])
    def log(self, request, pk=None):
        """返回任务的工作日志（Suggest 全部词、AI 输入/输出）。单独端点，避免列表接口拖大字段。"""
        run = self.get_object()
        return Response({
            "scoring_model": run.scoring_model,
            "root_keyword": run.root_keyword,
            "run_log": run.run_log or {},
        })

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request):
        """批量删除任务（结果经外键 CASCADE 一并删除）。参数：ids=[1,2,3]。"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "请提供要删除的任务 id 列表。"}, status=status.HTTP_400_BAD_REQUEST)
        count, _ = KeywordRun.objects.filter(id__in=ids).delete()
        return Response({"detail": "已删除选中任务。", "deleted": count})


class KeywordResultViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = KeywordResultSerializer
    pagination_class = TenPerPagePagination

    def get_queryset(self):
        queryset = KeywordResult.objects.select_related("run").all()
        run_id = self.request.query_params.get("run")
        result_status = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if run_id:
            queryset = queryset.filter(run_id=run_id)
        if result_status:
            queryset = queryset.filter(status=result_status)
        if search:
            queryset = queryset.filter(Q(keyword__icontains=search) | Q(run__root_keyword__icontains=search))
        return queryset

    @action(detail=False, methods=["get"])
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="keyword-results.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        headers = [
            "基础关键词", "长尾关键词", "打分模型", "任务状态", "淘汰阶段", "淘汰原因", "规则总分", "最终处理结果",
            "AI博彩意向", "AI判定理由",
            *SCORE_LABELS.values(),
        ]
        for position in range(1, 6):
            headers.extend([f"视频{position}-{label}" for _, label in VIDEO_CSV_FIELDS])
        writer.writerow(headers)
        for item in queryset:
            agent = item.agent_result or {}
            row = [
                item.run.root_keyword, item.keyword, item.run.scoring_model, item.status, item.elimination_stage,
                item.elimination_reason, item.rule_score, item.final_decision,
                agent.get("intent", ""), agent.get("reason", ""),
                *[item.score_breakdown.get(key, 0) for key in SCORE_LABELS],
            ]
            videos = item.top5_video_data or []
            for position in range(5):
                video = videos[position] if position < len(videos) else {}
                row.extend([video.get(key, "") for key, _ in VIDEO_CSV_FIELDS])
            writer.writerow(row)
        return response


class AgentPromptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """打分模型里各 Agent 的提示词管理：列表 + 编辑（不开放增删，Agent 由迁移种子维护）。"""
    queryset = AgentPrompt.objects.all()
    serializer_class = AgentPromptSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        scoring_model = self.request.query_params.get("scoring_model")
        if scoring_model:
            queryset = queryset.filter(scoring_model=scoring_model)
        return queryset

    @action(detail=True, methods=["get"])
    def default_prompt(self, request, pk=None):
        """返回该 Agent 的系统内置默认提示词，供前端「恢复系统默认」使用。"""
        agent = self.get_object()
        return Response({"prompt": get_default_agent_prompt(agent.scoring_model, agent.agent_type)})


class SuggestExpansionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """实用工具「获取 Suggest API 长尾词」：创建任务、查列表/详情、停止、导出 CSV。"""
    queryset = SuggestExpansionRun.objects.all()
    pagination_class = TenPerPagePagination

    def get_serializer_class(self):
        # 列表用轻量序列化器（不含 keywords 大字段），详情用完整的
        if self.action == "retrieve":
            return SuggestExpansionDetailSerializer
        return SuggestExpansionRunSerializer

    def _reap_stale_runs(self):
        """
        兜底清理僵尸任务：running 任务正常每几秒就更新一次，若超过 3 分钟没更新，
        说明 worker 已被杀（如硬超时 SIGKILL、worker 重启），无法自我标记状态。
        这里把它们标记为失败，避免前端永远卡在「处理中」。
        """
        import datetime
        from django.utils import timezone
        threshold = timezone.now() - datetime.timedelta(minutes=3)
        stale = SuggestExpansionRun.objects.filter(status=SuggestExpansionRun.STATUS_RUNNING, updated_at__lt=threshold)
        for run in stale:
            run.status = SuggestExpansionRun.STATUS_FAILED
            run.error_message = "任务超过 3 分钟无进度，可能已被系统中断（已保留此前拓展的词）"
            run.save(update_fields=["status", "error_message", "updated_at"])

    def list(self, request, *args, **kwargs):
        self._reap_stale_runs()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save(status=SuggestExpansionRun.STATUS_RUNNING)
        process_suggest_expansion.delay(run.id, str(run.task_token))
        return Response(self.get_serializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        if run.status not in [SuggestExpansionRun.STATUS_PENDING, SuggestExpansionRun.STATUS_RUNNING]:
            return Response({"detail": "只有处理中的任务可以停止。"}, status=status.HTTP_409_CONFLICT)
        run.status = SuggestExpansionRun.STATUS_STOPPED
        run.task_token = uuid.uuid4()  # 让正在跑的 worker 任务失效
        run.save(update_fields=["status", "task_token", "updated_at"])
        return Response(SuggestExpansionRunSerializer(run).data)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        run = self.get_object()
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="suggest-{run.id}.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["序号", "长尾关键词"])
        for i, kw in enumerate(run.keywords or [], 1):
            writer.writerow([i, kw])
        return response
