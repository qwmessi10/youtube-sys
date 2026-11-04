"""数据分析系统定时任务：按全局设置频率刷视频库指标 + 抓排名追踪。"""
from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import KeywordRankSnapshot, KeywordRankTracking, VideoLibraryItem, VideoMetricSnapshot
from .services import capture_ranking, fetch_video_details
from keywords.models import GlobalSetting
from keywords.services import get_setting


def _refresh_interval_minutes():
    """读取刷新频率（分钟），非法值回退 60。"""
    try:
        value = int(float(get_setting("ANALYTICS_REFRESH_INTERVAL_MINUTES", "60") or 60))
        return value if value > 0 else 60
    except (TypeError, ValueError):
        return 60


def _due_for_refresh():
    """判断是否到刷新时机：距上次刷新超过配置的间隔。"""
    interval = _refresh_interval_minutes()
    last = get_setting("ANALYTICS_LAST_REFRESH_AT", "")
    if last:
        last_dt = parse_datetime(last)
        if last_dt and (timezone.now() - last_dt).total_seconds() < interval * 60:
            return False
    return True


@shared_task
def analytics_scheduled_refresh():
    """定时刷新：刷视频库所有视频指标 + 抓所有启用排名追踪。频率由全局设置控制。"""
    if not _due_for_refresh():
        return 0

    # 1) 刷视频库指标（批量 V3，写快照）
    videos = list(VideoLibraryItem.objects.all())
    refreshed = 0
    if videos:
        try:
            details = fetch_video_details([v.video_id for v in videos])
        except Exception:
            details = {}
        for v in videos:
            d = details.get(v.video_id)
            if not d:
                continue
            v.title = d.get("title") or v.title
            v.channel_name = d.get("channel_name") or v.channel_name
            v.channel_id = d.get("channel_id") or v.channel_id
            v.view_count = d.get("view_count")
            v.like_count = d.get("like_count")
            v.comment_count = d.get("comment_count")
            published = d.get("published_at")
            if published:
                parsed = parse_datetime(published)
                if parsed:
                    v.published_at = parsed
            v.snapshot_at = timezone.now()
            v.save()
            VideoMetricSnapshot.objects.create(
                video=v, view_count=v.view_count,
                like_count=v.like_count, comment_count=v.comment_count,
            )
            refreshed += 1

    # 2) 抓排名追踪（写快照）
    captured = 0
    for tracking in KeywordRankTracking.objects.filter(enabled=True):
        try:
            videos_data = capture_ranking(tracking)
        except Exception:
            continue
        KeywordRankSnapshot.objects.create(tracking=tracking, videos=videos_data)
        tracking.last_captured_at = timezone.now()
        tracking.save(update_fields=["last_captured_at"])
        captured += 1

    # 记录刷新时间（供下次 _due_for_refresh 判断）
    GlobalSetting.objects.update_or_create(
        key="ANALYTICS_LAST_REFRESH_AT",
        defaults={"value": timezone.now().isoformat(), "description": "数据分析-上次刷新时间（内部，勿改）"},
    )
    return refreshed + captured
