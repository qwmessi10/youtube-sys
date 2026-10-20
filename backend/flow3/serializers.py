from rest_framework import serializers

from .models import Flow3Agent, Flow3Material, Flow3Run


class Flow3AgentSerializer(serializers.ModelSerializer):
    agent_type_label = serializers.CharField(source="get_agent_type_display", read_only=True)

    class Meta:
        model = Flow3Agent
        # 类型/名称/用途固定，只允许改 prompt 和 enabled。
        fields = ["id", "agent_type", "agent_type_label", "name", "description", "prompt", "enabled", "updated_at"]
        read_only_fields = ["agent_type", "name", "description"]


class Flow3MaterialSerializer(serializers.ModelSerializer):
    material_type_label = serializers.CharField(source="get_material_type_display", read_only=True)
    tag_label = serializers.CharField(source="get_tag_display", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Flow3Material
        fields = ["id", "material_type", "material_type_label", "name", "file", "file_url",
                  "duration", "tag", "tag_label", "enabled", "created_at", "updated_at"]
        read_only_fields = ["duration"]

    def get_file_url(self, obj):
        return obj.file.url if obj.file else ""


class Flow3RunSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    hook_video_url = serializers.SerializerMethodField()
    blur_bg_url = serializers.SerializerMethodField()
    tail_image_url = serializers.SerializerMethodField()
    rendered_url = serializers.SerializerMethodField()

    class Meta:
        model = Flow3Run
        fields = [
            "id", "name", "keyword", "total_duration", "promo_code", "country",
            "event_name", "language", "status", "status_label", "error_message",
            "hook_prompt", "hook_video_url", "narration", "narration_audio",
            "blur_bg_url", "tail_image_url", "rendered_url",
            "title", "description", "thumbnail_prompt",
            "layout_seed", "bgm_seed", "bgm_file",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "error_message", "hook_prompt", "narration", "narration_audio",
            "title", "description", "thumbnail_prompt", "layout_seed", "bgm_seed", "bgm_file",
        ]

    def _url(self, f):
        return f.url if f else ""

    def get_hook_video_url(self, obj):
        return self._url(obj.hook_video)

    def get_blur_bg_url(self, obj):
        return self._url(obj.blur_bg_file)

    def get_tail_image_url(self, obj):
        return self._url(obj.tail_image_file)

    def get_rendered_url(self, obj):
        return self._url(obj.rendered_file)


class Flow3RunCreateSerializer(serializers.ModelSerializer):
    """创建流程3 任务：单关键词、总时长、促销码等。可选从 hook 素材库指定素材。"""
    # 指定 hook 素材（可空）。不传=随机取未使用素材；传了=用指定素材并跳过人工上传。
    hook_material = serializers.PrimaryKeyRelatedField(
        queryset=Flow3Material.objects.filter(material_type=Flow3Material.TYPE_HOOK),
        required=False, allow_null=True,
    )

    class Meta:
        model = Flow3Run
        fields = ["id", "name", "keyword", "total_duration", "promo_code",
                  "country", "event_name", "language", "hook_material"]

    def validate_keyword(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("请填写一个关键词。")
        return value

    def validate_total_duration(self, value):
        # Hook 7s + 旁白若干 + 尾图，至少给到 30s 才有意义。
        if value < 30:
            raise serializers.ValidationError("总时长至少 30 秒。")
        if value > 600:
            raise serializers.ValidationError("总时长最多 600 秒。")
        return value
