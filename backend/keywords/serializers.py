from rest_framework import serializers

from .models import GlobalSetting, KeywordResult, KeywordRun

COUNTRIES = [
    ("US", "美国"), ("GB", "英国"), ("CA", "加拿大"), ("AU", "澳大利亚"),
    ("NZ", "新西兰"), ("DE", "德国"), ("FR", "法国"), ("ES", "西班牙"),
    ("IT", "意大利"), ("BR", "巴西"), ("MX", "墨西哥"), ("JP", "日本"),
    ("KR", "韩国"), ("IN", "印度"), ("SG", "新加坡"), ("AE", "阿联酋"),
]
LANGUAGES = [
    ("en", "英语"), ("zh-CN", "简体中文"), ("zh-TW", "繁体中文"), ("es", "西班牙语"),
    ("pt", "葡萄牙语"), ("de", "德语"), ("fr", "法语"), ("it", "意大利语"),
    ("ja", "日语"), ("ko", "韩语"), ("hi", "印地语"), ("ar", "阿拉伯语"),
]


class GlobalSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSetting
        fields = ["id", "key", "value", "description", "updated_at"]


class KeywordRunSerializer(serializers.ModelSerializer):
    result_count = serializers.IntegerField(source="results.count", read_only=True)

    class Meta:
        model = KeywordRun
        fields = ["id", "root_keyword", "country", "language", "max_keywords", "status", "error_message", "result_count", "created_at", "updated_at"]

    def validate_country(self, value):
        if value not in dict(COUNTRIES):
            raise serializers.ValidationError("请选择列表中的国家。")
        return value

    def validate_language(self, value):
        if value not in dict(LANGUAGES):
            raise serializers.ValidationError("请选择列表中的语言。")
        return value


class KeywordResultSerializer(serializers.ModelSerializer):
    root_keyword = serializers.CharField(source="run.root_keyword", read_only=True)

    class Meta:
        model = KeywordResult
        fields = ["id", "run", "root_keyword", "keyword", "status", "elimination_stage", "elimination_reason", "serpapi_status", "top5_video_data", "score_breakdown", "rule_score", "final_decision", "created_at", "updated_at"]
