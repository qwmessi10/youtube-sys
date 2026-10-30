from rest_framework import serializers

from .models import AdsPowerProfile, UploadTask


class AdsPowerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdsPowerProfile
        fields = [
            "user_id", "serial_number", "name", "group_id", "group_name",
            "domain_name", "username", "remark", "ip", "ip_country",
            "proxy_summary", "last_open_time", "raw", "synced_at",
        ]


class UploadTaskSerializer(serializers.ModelSerializer):
    """列表 / 详情用：带只读的展示字段。"""
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    publish_mode_label = serializers.CharField(source="get_publish_mode_display", read_only=True)
    profile = serializers.SlugRelatedField(slug_field="user_id", read_only=True)
    profile_name = serializers.CharField(source="profile.name", read_only=True, default="")
    profile_serial = serializers.CharField(source="profile.serial_number", read_only=True, default="")
    source_run_keyword = serializers.CharField(source="source_run.keyword", read_only=True, default="")

    class Meta:
        model = UploadTask
        fields = [
            "id", "name", "source_run", "source_run_keyword",
            "profile", "profile_name", "profile_serial",
            "video_file", "video_path", "title", "description",
            "cover_file", "cover_path", "publish_mode", "publish_mode_label",
            "status", "status_label", "video_url", "retry_count",
            "error_message", "upload_log", "created_at", "updated_at", "finished_at",
        ]
        read_only_fields = [
            "status", "video_url", "retry_count", "error_message",
            "upload_log", "finished_at",
        ]


class UploadTaskCreateSerializer(serializers.ModelSerializer):
    """手动创建任务：填 profile + 内容（视频/标题/描述/封面）。profile 用 user_id 关联。"""
    profile = serializers.SlugRelatedField(
        slug_field="user_id", queryset=AdsPowerProfile.objects.all()
    )

    class Meta:
        model = UploadTask
        fields = [
            "name", "profile", "video_file", "video_path",
            "title", "description", "cover_file", "cover_path", "publish_mode",
        ]

    def validate(self, attrs):
        if not attrs.get("video_file") and not attrs.get("video_path"):
            raise serializers.ValidationError("请上传视频文件或提供视频路径")
        if not attrs.get("title"):
            raise serializers.ValidationError("标题不能为空")
        return attrs


class UploadTaskPayloadSerializer(serializers.ModelSerializer):
    """
    执行器专用 payload：返回结构化上传数据 + 文件下载直链（不走 zip）。
    video_url / cover_url 为完整可下载 URL，由 view 注入 request 域名拼接。
    """
    video_download_url = serializers.SerializerMethodField()
    cover_download_url = serializers.SerializerMethodField()
    profile_user_id = serializers.CharField(source="profile.user_id", read_only=True)

    class Meta:
        model = UploadTask
        fields = [
            "id", "profile_user_id", "title", "description",
            "publish_mode", "video_download_url", "cover_download_url",
        ]

    def _abs_url(self, path):
        request = self.context.get("request")
        if not path:
            return ""
        return request.build_absolute_uri(path) if request else path

    def get_video_download_url(self, obj):
        if obj.video_file:
            return self._abs_url(obj.video_file.url)
        if obj.video_path:
            return self._abs_url(f"/media/{obj.video_path.lstrip('/')}")
        return ""

    def get_cover_download_url(self, obj):
        if obj.cover_file:
            return self._abs_url(obj.cover_file.url)
        if obj.cover_path:
            return self._abs_url(f"/media/{obj.cover_path.lstrip('/')}")
        return ""
