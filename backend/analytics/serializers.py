from rest_framework import serializers

from .models import (
    CompetitorAnalysis,
    KeywordRankSnapshot,
    KeywordRankTracking,
    VideoLibraryItem,
    VideoMetricSnapshot,
)


class VideoLibraryItemSerializer(serializers.ModelSerializer):
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = VideoLibraryItem
        fields = [
            "id", "video_id", "video_url", "title", "channel_name", "channel_id",
            "source", "source_label", "upload_task", "flow3_run", "remark",
            "view_count", "like_count", "comment_count", "published_at",
            "duration", "snapshot_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "video_id", "title", "channel_name", "channel_id",
            "view_count", "like_count", "comment_count", "published_at",
            "duration", "snapshot_at",
        ]


class VideoMetricSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoMetricSnapshot
        fields = ["id", "video", "view_count", "like_count", "comment_count", "captured_at"]


class CompetitorAnalysisSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CompetitorAnalysis
        fields = [
            "id", "keyword", "country", "language", "top_n",
            "status", "status_label", "result", "error_message",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "result", "error_message"]


class KeywordRankTrackingSerializer(serializers.ModelSerializer):
    snapshot_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = KeywordRankTracking
        fields = [
            "id", "keyword", "country", "language", "top_n", "enabled",
            "last_captured_at", "snapshot_count", "created_at", "updated_at",
        ]
        read_only_fields = ["last_captured_at", "snapshot_count"]


class KeywordRankSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeywordRankSnapshot
        fields = ["id", "tracking", "captured_at", "videos"]
