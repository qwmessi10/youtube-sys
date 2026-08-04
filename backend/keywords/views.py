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

from .models import GlobalSetting, KeywordResult, KeywordRun
from .serializers import COUNTRIES, LANGUAGES, GlobalSettingSerializer, KeywordResultSerializer, KeywordRunSerializer
from .tasks import process_keyword_run

DEFAULT_SETTINGS = [
    ("SERPAPI_API_KEY", "SerpApi YouTube Search API Key"),
    ("YOUTUBE_API_KEY", "YouTube Data API V3 Key"),
    ("SERPAPI_QPS", "SerpApi 每秒最大请求数，控制限流，默认 1"),
    ("SERPAPI_MAX_RETRIES", "SerpApi/YouTube 遇 429 或 5xx 时的重试次数，默认 2"),
    ("AI_BASE_URL", "AI 接口地址（OpenAI 兼容中转，如 moretokens）"),
    ("AI_API_KEY", "AI API Key（打分模型 2.0 博彩意图筛选使用）"),
    ("AI_MODEL", "AI 模型名，2.0 默认 gemini-3.6-flash-medium"),
    ("AI_BETTING_INTENT_PROMPT", "打分模型 2.0 博彩意图筛选提示词；留空则用系统默认提示词"),
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


class KeywordRunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
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
