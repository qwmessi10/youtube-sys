from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import (
    CompetitorAnalysis,
    KeywordRankSnapshot,
    KeywordRankTracking,
    VideoLibraryItem,
    VideoMetricSnapshot,
)
from .serializers import (
    CompetitorAnalysisSerializer,
    KeywordRankSnapshotSerializer,
    KeywordRankTrackingSerializer,
    VideoLibraryItemSerializer,
    VideoMetricSnapshotSerializer,
)
from .services import (
    capture_ranking,
    extract_video_id,
    fetch_video_details,
    search_and_analyze,
)


class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


def _parse_dt(value):
    """ISO 字符串 → datetime；解析失败返回 None。"""
    if not value:
        return None
    try:
        return parse_datetime(value)
    except (TypeError, ValueError):
        return None


class VideoLibraryItemViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                              mixins.CreateModelMixin, mixins.UpdateModelMixin,
                              mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """视频库（我的视频）。手动添加时解析 video_id 并拉 V3 数据；自动关联走 sync。"""
    queryset = VideoLibraryItem.objects.all()
    serializer_class = VideoLibraryItemSerializer
    pagination_class = TenPerPagePagination

    def create(self, request, *args, **kwargs):
        video_url = (request.data.get("video_url") or "").strip()
        if not video_url:
            return Response({"detail": "请填写视频链接"}, status=status.HTTP_400_BAD_REQUEST)
        video_id = extract_video_id(video_url)
        if not video_id:
            return Response({"detail": "无法从链接解析视频 ID（需 youtube.com 或 youtu.be）"},
                            status=status.HTTP_400_BAD_REQUEST)
        if VideoLibraryItem.objects.filter(video_id=video_id).exists():
            return Response({"detail": "该视频已存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 拉 V3 详情（失败不阻塞，只存链接和 ID，数据留待后续刷新）
        detail = {}
        try:
            detail = fetch_video_details([video_id]).get(video_id, {})
        except Exception:
            detail = {}

        item = VideoLibraryItem(
            video_id=video_id,
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            title=detail.get("title", ""),
            channel_name=detail.get("channel_name", ""),
            channel_id=detail.get("channel_id", ""),
            source=VideoLibraryItem.SOURCE_MANUAL,
            remark=(request.data.get("remark") or "").strip(),
            view_count=detail.get("view_count"),
            like_count=detail.get("like_count"),
            comment_count=detail.get("comment_count"),
            published_at=_parse_dt(detail.get("published_at")),
            snapshot_at=timezone.now() if detail else None,
        )
        item.save()
        if detail:
            VideoMetricSnapshot.objects.create(
                video=item, view_count=item.view_count,
                like_count=item.like_count, comment_count=item.comment_count,
            )
        return Response(VideoLibraryItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        """从 AdsPower 上传任务自动关联（video_url 非空、去重）。"""
        from uploader.models import UploadTask

        created = skipped = 0
        tasks = UploadTask.objects.filter(video_url__isnull=False).exclude(video_url="").select_related("source_run")
        for t in tasks:
            video_id = extract_video_id(t.video_url)
            if not video_id:
                continue
            if VideoLibraryItem.objects.filter(video_id=video_id).exists():
                skipped += 1
                continue
            VideoLibraryItem.objects.create(
                video_id=video_id,
                video_url=t.video_url,
                title=t.title or "",
                source=VideoLibraryItem.SOURCE_AUTO,
                upload_task=t,
                flow3_run=t.source_run,
            )
            created += 1
        return Response({"created": created, "skipped": skipped})

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """单条实时刷新指标（写快照）。"""
        item = self.get_object()
        try:
            detail = fetch_video_details([item.video_id]).get(item.video_id, {})
        except Exception as exc:
            return Response({"detail": "刷新失败：" + str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not detail:
            return Response({"detail": "视频不存在或已删除"}, status=status.HTTP_400_BAD_REQUEST)

        item.title = detail.get("title") or item.title
        item.channel_name = detail.get("channel_name") or item.channel_name
        item.channel_id = detail.get("channel_id") or item.channel_id
        item.view_count = detail.get("view_count")
        item.like_count = detail.get("like_count")
        item.comment_count = detail.get("comment_count")
        published = _parse_dt(detail.get("published_at"))
        if published:
            item.published_at = published
        item.snapshot_at = timezone.now()
        item.save()
        VideoMetricSnapshot.objects.create(
            video=item, view_count=item.view_count,
            like_count=item.like_count, comment_count=item.comment_count,
        )
        return Response(VideoLibraryItemSerializer(item).data)

    @action(detail=True, methods=["get"])
    def snapshots(self, request, pk=None):
        """单视频指标趋势（历史快照）。"""
        item = self.get_object()
        snaps = item.snapshots.all()[:200]
        return Response(VideoMetricSnapshotSerializer(snaps, many=True).data)


class CompetitorAnalysisViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """竞品 SEO 分析。analyze 实时抓取 + 分析；历史记录只读 + 可删。"""
    queryset = CompetitorAnalysis.objects.all()
    serializer_class = CompetitorAnalysisSerializer
    pagination_class = TenPerPagePagination

    @action(detail=False, methods=["post"])
    def analyze(self, request):
        keyword = (request.data.get("keyword") or "").strip()
        if not keyword:
            return Response({"detail": "请填写关键词"}, status=status.HTTP_400_BAD_REQUEST)
        country = request.data.get("country", "US")
        language = request.data.get("language", "en")
        try:
            top_n = int(request.data.get("top_n", 10) or 10)
        except (TypeError, ValueError):
            return Response({"detail": "top N 必须为数字"}, status=status.HTTP_400_BAD_REQUEST)
        if not (1 <= top_n <= 50):
            return Response({"detail": "top N 需在 1~50 之间"}, status=status.HTTP_400_BAD_REQUEST)

        analysis = CompetitorAnalysis.objects.create(
            keyword=keyword, country=country, language=language, top_n=top_n,
            status=CompetitorAnalysis.STATUS_RUNNING,
        )
        try:
            analysis.result = search_and_analyze(keyword, country, language, top_n)
            analysis.status = CompetitorAnalysis.STATUS_COMPLETED
        except Exception as exc:
            analysis.status = CompetitorAnalysis.STATUS_FAILED
            analysis.error_message = str(exc)
        analysis.save()
        return Response(CompetitorAnalysisSerializer(analysis).data)


class KeywordRankTrackingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                 mixins.CreateModelMixin, mixins.UpdateModelMixin,
                                 mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """关键词排名追踪。capture 手动抓一次；snapshots 取趋势数据。"""
    queryset = KeywordRankTracking.objects.all()
    serializer_class = KeywordRankTrackingSerializer
    pagination_class = TenPerPagePagination

    def get_queryset(self):
        qs = super().get_queryset()
        # 附带快照数，供列表展示
        return qs.prefetch_related("snapshots")

    def create(self, request, *args, **kwargs):
        keyword = (request.data.get("keyword") or "").strip()
        if not keyword:
            return Response({"detail": "请填写关键词"}, status=status.HTTP_400_BAD_REQUEST)
        if KeywordRankTracking.objects.filter(keyword=keyword).exists():
            return Response({"detail": "该关键词已在追踪中"}, status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def capture(self, request, pk=None):
        """手动立即抓一次排名快照。"""
        tracking = self.get_object()
        try:
            videos = capture_ranking(tracking)
        except Exception as exc:
            return Response({"detail": "抓取失败：" + str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        snapshot = KeywordRankSnapshot.objects.create(tracking=tracking, videos=videos)
        tracking.last_captured_at = timezone.now()
        tracking.save(update_fields=["last_captured_at"])
        return Response(KeywordRankSnapshotSerializer(snapshot).data)

    @action(detail=True, methods=["get"])
    def snapshots(self, request, pk=None):
        """排名趋势数据（历史快照）。"""
        tracking = self.get_object()
        snaps = tracking.snapshots.all()[:200]
        return Response(KeywordRankSnapshotSerializer(snaps, many=True).data)


# ============================ 首页总览聚合 ============================

# 各系统状态 → 统一中文文案（首页最近动态用）
_STATUS_LABEL = {
    "pending": "进行中", "running": "进行中", "completed": "已完成", "failed": "失败",
    "awaiting_hook": "等上传", "paused": "已暂停", "stopped": "已停止",
    "queued": "排队中", "launching": "启动中", "uploading": "上传中",
    "draft_saved": "待核对", "publishing": "发布中",
}


def _build_recent(limit=10):
    """合并 5 个系统的最近记录，按时间倒序取前 N 条。"""
    from flow3.models import Flow3Run
    from keywords.models import KeywordRun, SuggestExpansionRun
    from smm.models import SMMPollTask, SMMTask
    from uploader.models import UploadTask

    entries = []
    for r in KeywordRun.objects.all()[:limit]:
        entries.append({"system": "keywords", "type": "关键词分析", "title": r.root_keyword,
                        "status": r.status, "time": r.created_at.isoformat()})
    for r in SuggestExpansionRun.objects.all()[:limit]:
        entries.append({"system": "suggest", "type": "长尾词拓展", "title": r.root_keyword,
                        "status": r.status, "time": r.created_at.isoformat()})
    for r in Flow3Run.objects.all()[:limit]:
        entries.append({"system": "flow3", "type": "视频生成", "title": r.keyword,
                        "status": r.status, "time": r.created_at.isoformat()})
    for r in UploadTask.objects.all()[:limit]:
        entries.append({"system": "uploader", "type": "上传", "title": r.title or r.name or "上传任务",
                        "status": r.status, "time": r.created_at.isoformat()})
    for r in SMMTask.objects.filter(poll_task__isnull=True)[:limit]:
        entries.append({"system": "smm", "type": "刷量任务", "title": r.show_id or r.key_words or r.youtube_link,
                        "status": r.status, "time": r.created_at.isoformat()})
    for r in SMMPollTask.objects.all()[:limit]:
        entries.append({"system": "smm", "type": "轮询刷量", "title": r.key_words or r.youtube_link,
                        "status": r.status, "time": r.created_at.isoformat()})

    entries.sort(key=lambda e: e["time"], reverse=True)
    recent = entries[:limit]
    for e in recent:
        e["status_label"] = _STATUS_LABEL.get(e["status"], e["status"])
    return recent


@api_view(["GET"])
def dashboard_summary(request):
    """首页总览聚合：指标卡 4 + 系统概况 5 + 最近动态 10，一次请求返回。"""
    from flow3.models import Flow3Run
    from keywords.models import KeywordRun, SuggestExpansionRun
    from smm.models import SMMAccount, SMMPollTask, SMMTask
    from uploader.models import UploadTask

    today = timezone.localdate()

    # 1) SMM 余额（锁定后剩余可用）
    total_remaining = 0.0
    for acc in SMMAccount.objects.all():
        locked = sum(pt.locked_amount for pt in acc.poll_tasks.filter(status="running"))
        total_remaining += float(acc.balance) - locked
    total_remaining = round(total_remaining, 2)

    # 2) 今日出片（flow3 completed 且 updated_at 为今天）
    today_videos = Flow3Run.objects.filter(status="completed", updated_at__date=today).count()

    # 3) 待核对草稿
    draft_count = UploadTask.objects.filter(status="draft_saved").count()

    # 4) 进行中任务合计
    running_count = (
        KeywordRun.objects.filter(status__in=["pending", "running"]).count()
        + Flow3Run.objects.filter(status__in=["pending", "running", "awaiting_hook"]).count()
        + UploadTask.objects.filter(status__in=["queued", "launching", "uploading"]).count()
        + SMMTask.objects.filter(poll_task__isnull=True, status__in=["pending", "running"]).count()
        + SMMPollTask.objects.filter(status="running").count()
        + SuggestExpansionRun.objects.filter(status__in=["pending", "running"]).count()
    )

    systems = [
        {
            "key": "keywords", "name": "关键词系统",
            "total": KeywordRun.objects.count(),
            "running": KeywordRun.objects.filter(status__in=["pending", "running"]).count(),
            "completed": KeywordRun.objects.filter(status="completed").count(),
            "failed": KeywordRun.objects.filter(status="failed").count(),
        },
        {
            "key": "flow3", "name": "内容生成",
            "total": Flow3Run.objects.count(),
            "running": Flow3Run.objects.filter(status__in=["pending", "running"]).count(),
            "awaiting_hook": Flow3Run.objects.filter(status="awaiting_hook").count(),
            "completed": Flow3Run.objects.filter(status="completed").count(),
            "failed": Flow3Run.objects.filter(status="failed").count(),
        },
        {
            "key": "uploader", "name": "AdsPower",
            "total": UploadTask.objects.count(),
            "running": UploadTask.objects.filter(status__in=["queued", "launching", "uploading"]).count(),
            "draft": UploadTask.objects.filter(status="draft_saved").count(),
            "failed": UploadTask.objects.filter(status="failed").count(),
        },
        {
            "key": "smm", "name": "SMM 面板",
            "accounts": SMMAccount.objects.count(),
            "tasks_running": SMMTask.objects.filter(poll_task__isnull=True, status__in=["pending", "running"]).count(),
            "polls_running": SMMPollTask.objects.filter(status="running").count(),
            "failed": SMMTask.objects.filter(poll_task__isnull=True, status="failed").count(),
        },
        {
            "key": "suggest", "name": "实用工具",
            "total": SuggestExpansionRun.objects.count(),
            "running": SuggestExpansionRun.objects.filter(status__in=["pending", "running"]).count(),
            "completed": SuggestExpansionRun.objects.filter(status="completed").count(),
        },
    ]

    return Response({
        "metrics": {
            "smm_remaining": total_remaining,
            "today_videos": today_videos,
            "draft_count": draft_count,
            "running_count": running_count,
        },
        "systems": systems,
        "recent": _build_recent(),
    })
