from rest_framework import serializers

from .models import AdsPowerProfile, ProxyConfig, UploadTask


class ProxyConfigSerializer(serializers.ModelSerializer):
    """IP / 代理池。账号密码明文返回（便于编辑核对，内部测试项目无脱敏需求）。"""
    proxy_user = serializers.CharField(required=False, allow_blank=True, default="")
    proxy_password = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(required=False, allow_blank=True, default="")
    password_set = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    geo_summary = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()   # 该 IP 被哪些环境使用
    assigned_count = serializers.SerializerMethodField()

    class Meta:
        model = ProxyConfig
        fields = [
            "id", "name", "proxy_type", "proxy_host", "proxy_port",
            "proxy_user", "proxy_password", "password_set", "label",
            "source", "geo_info", "geo_summary", "verified_at",
            "assigned_to", "assigned_count",
            "remark", "created_at", "updated_at",
        ]
        read_only_fields = ["source", "geo_info", "verified_at"]

    def get_password_set(self, obj):
        return bool(obj.proxy_password)

    def get_label(self, obj):
        return str(obj)

    def get_geo_summary(self, obj):
        g = obj.geo_info or {}
        if not g:
            return ""
        parts = [g.get("country_name") or g.get("country_code"), g.get("region_name"), g.get("city_name")]
        return " / ".join([p for p in parts if p])

    def get_assigned_to(self, obj):
        usage = (self.context or {}).get("usage_map") or {}
        return usage.get(f"{obj.proxy_host}:{obj.proxy_port}", [])

    def get_assigned_count(self, obj):
        return len(self.get_assigned_to(obj))

    def validate(self, attrs):
        host = attrs.get("proxy_host") or getattr(self.instance, "proxy_host", "")
        port = attrs.get("proxy_port") or getattr(self.instance, "proxy_port", "")
        if not host or not port:
            raise serializers.ValidationError("代理主机和端口不能为空")
        # 名称留空时默认用 IP 主机本身；仅在新建、或编辑时清空了名称的情况下回填。
        if not (attrs.get("name") or "").strip() and host:
            attrs["name"] = host
        return attrs


class AdsPowerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdsPowerProfile
        fields = [
            "user_id", "serial_number", "name", "group_id", "group_name",
            "domain_name", "username", "remark", "ip", "ip_country",
            "proxy_summary", "last_open_time", "raw", "synced_at",
        ]


class AdsPowerProfileWriteSerializer(serializers.Serializer):
    """
    新建 / 编辑环境的入参校验（不直接落库，由 view 调 AdsPower 写接口后再 sync）。
    代理来源二选一：proxy_id（引用本地 IP 池）或 proxy_config（直接传结构）；都不传=无代理。
    """
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    group_id = serializers.CharField(required=False, allow_blank=True)
    domain_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    remark = serializers.CharField(required=False, allow_blank=True)
    proxy_id = serializers.IntegerField(required=False, allow_null=True)


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
            "error_message", "upload_log", "locked_at", "created_at", "updated_at", "finished_at",
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
