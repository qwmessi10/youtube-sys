from django.contrib import admin

from .models import (
    CompetitorAnalysis,
    KeywordRankSnapshot,
    KeywordRankTracking,
    VideoLibraryItem,
    VideoMetricSnapshot,
)


@admin.register(VideoLibraryItem)
class VideoLibraryItemAdmin(admin.ModelAdmin):
    list_display = ["title", "video_id", "channel_name", "source", "view_count", "snapshot_at"]
    search_fields = ["title", "video_id", "channel_name"]
    list_filter = ["source"]


@admin.register(CompetitorAnalysis)
class CompetitorAnalysisAdmin(admin.ModelAdmin):
    list_display = ["keyword", "country", "top_n", "status", "created_at"]
    search_fields = ["keyword"]
    list_filter = ["status"]


@admin.register(KeywordRankTracking)
class KeywordRankTrackingAdmin(admin.ModelAdmin):
    list_display = ["keyword", "country", "top_n", "enabled", "last_captured_at"]
    search_fields = ["keyword"]
    list_filter = ["enabled"]


admin.site.register(VideoMetricSnapshot)
admin.site.register(KeywordRankSnapshot)
