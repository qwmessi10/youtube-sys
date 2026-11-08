from rest_framework import serializers

from .models import SMMAccount, SMMPollTask, SMMTask


class SMMAccountSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    locked_total = serializers.SerializerMethodField()
    locked_remaining = serializers.SerializerMethodField()

    class Meta:
        model = SMMAccount
        fields = [
            "id", "tg_user_id", "username", "first_name", "last_name",
            "panel_user_name", "token", "user_identifier", "balance",
            "locked_total", "locked_remaining",
            "status", "status_label", "remark", "created_at", "updated_at",
        ]
        read_only_fields = [
            "first_name", "last_name", "panel_user_name", "token",
            "user_identifier", "balance", "status",
        ]

    def get_locked_total(self, obj):
        total = sum(pt.locked_amount for pt in obj.poll_tasks.filter(status="running"))
        return round(total, 2)

    def get_locked_remaining(self, obj):
        return round(float(obj.balance) - self.get_locked_total(obj), 2)


class SMMTaskSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.panel_user_name", read_only=True, default="")
    account_tg_user_id = serializers.CharField(source="account.tg_user_id", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SMMTask
        fields = [
            "id", "account", "account_name", "account_tg_user_id",
            "panel_task_id", "show_id", "youtube_link", "key_words",
            "total_user", "per_user", "task_type", "plant_form",
            "comment_num", "end_time", "cost", "status", "status_label",
            "panel_status", "progress", "created_at", "updated_at",
        ]
        read_only_fields = [
            "panel_task_id", "show_id", "cost", "status", "panel_status",
            "progress", "end_time",
        ]


class SMMPollTaskSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.panel_user_name", read_only=True, default="")
    account_tg_user_id = serializers.CharField(source="account.tg_user_id", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    children = SMMTaskSerializer(many=True, read_only=True)

    class Meta:
        model = SMMPollTask
        fields = [
            "id", "account", "account_name", "account_tg_user_id",
            "youtube_link", "key_words", "per_user", "task_type", "plant_form", "comment_num",
            "initial_count", "poll_total", "poll_done", "batch_min", "batch_max",
            "window_start_hour", "window_end_hour", "status", "status_label",
            "next_poll_at", "fail_count", "last_error", "children", "created_at", "updated_at",
        ]
        read_only_fields = [
            "poll_done", "status", "next_poll_at", "fail_count", "last_error", "children",
        ]
