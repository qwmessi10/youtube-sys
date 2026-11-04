from django.contrib import admin

from .models import SMMAccount, SMMPollTask, SMMTask


@admin.register(SMMAccount)
class SMMAccountAdmin(admin.ModelAdmin):
    list_display = ["tg_user_id", "panel_user_name", "username", "balance", "status", "updated_at"]
    search_fields = ["tg_user_id", "panel_user_name", "username"]
    list_filter = ["status"]


@admin.register(SMMTask)
class SMMTaskAdmin(admin.ModelAdmin):
    list_display = ["show_id", "account", "key_words", "total_user", "cost", "status", "created_at"]
    search_fields = ["show_id", "panel_task_id", "key_words", "youtube_link"]
    list_filter = ["status"]


@admin.register(SMMPollTask)
class SMMPollTaskAdmin(admin.ModelAdmin):
    list_display = ["id", "account", "key_words", "poll_done", "poll_total", "status", "next_poll_at", "created_at"]
    search_fields = ["key_words", "youtube_link"]
    list_filter = ["status"]
