from django.apps import AppConfig


class ContentGenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "content_gen"
    verbose_name = "内容生成系统"
