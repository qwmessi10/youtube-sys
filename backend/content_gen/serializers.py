from rest_framework import serializers

from keywords.serializers import COUNTRIES, LANGUAGES

from .models import ContentAgent, ContentItem, ContentRun


class ContentAgentSerializer(serializers.ModelSerializer):
    agent_type_label = serializers.CharField(source="get_agent_type_display", read_only=True)

    class Meta:
        model = ContentAgent
        # 名称/用途/类型是固定身份，只允许改 prompt 和 enabled（同关键词 Agent 管理）。
        fields = ["id", "agent_type", "agent_type_label", "name", "description", "prompt", "enabled", "updated_at"]
        read_only_fields = ["agent_type", "name", "description"]


class ContentRunSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="items.count", read_only=True)
    flow_label = serializers.CharField(source="get_flow_display", read_only=True)

    class Meta:
        model = ContentRun
        fields = [
            "id", "name", "flow", "flow_label", "country", "language",
            "shot_count", "shot_duration", "promo_code", "tts_provider",
            "status", "error_message", "item_count", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "error_message"]

    def validate_country(self, value):
        if value not in dict(COUNTRIES):
            raise serializers.ValidationError("请选择列表中的国家。")
        return value

    def validate_language(self, value):
        if value not in dict(LANGUAGES):
            raise serializers.ValidationError("请选择列表中的语言。")
        return value

    def validate_shot_count(self, value):
        if value < 1 or value > 10:
            raise serializers.ValidationError("分镜段数需在 1~10 之间。")
        return value


class ContentRunCreateSerializer(ContentRunSerializer):
    """创建任务用：额外接收 keywords 列表（每个关键词生成一条 ContentItem）。"""
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=255), write_only=True, allow_empty=False,
    )

    class Meta(ContentRunSerializer.Meta):
        fields = ContentRunSerializer.Meta.fields + ["keywords"]

    def validate(self, attrs):
        # 流程一（全自动）必须手填优惠码，渲染时注入视频模板。
        if attrs.get("flow") == ContentRun.FLOW_AUTO and not (attrs.get("promo_code") or "").strip():
            raise serializers.ValidationError({"promo_code": "流程一（全自动）需填写优惠码。"})
        return attrs


class ContentItemSerializer(serializers.ModelSerializer):
    run_name = serializers.CharField(source="run.name", read_only=True)
    run_flow = serializers.CharField(source="run.flow", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    merged_url = serializers.SerializerMethodField()
    rendered_url = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id", "run", "run_name", "run_flow", "keyword", "status", "status_label",
            "title", "description", "thumbnail_prompt", "thumbnail_url", "storyboard",
            "clip_files", "merged_url", "narration_audio", "rendered_url",
            "gen_log", "error_message", "created_at", "updated_at",
        ]

    def get_thumbnail_url(self, obj):
        return obj.thumbnail_file.url if obj.thumbnail_file else ""

    def get_merged_url(self, obj):
        return obj.merged_file.url if obj.merged_file else ""

    def get_rendered_url(self, obj):
        return obj.rendered_file.url if obj.rendered_file else ""
