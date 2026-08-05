import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("keywords", "0008_seed_agent_prompt_text")]

    operations = [
        migrations.CreateModel(
            name="SuggestExpansionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("root_keyword", models.CharField(max_length=255)),
                ("country", models.CharField(default="US", max_length=8)),
                ("language", models.CharField(default="en", max_length=16)),
                ("max_keywords", models.PositiveIntegerField(default=5000)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "待处理"), ("running", "处理中"),
                        ("completed", "已完成"), ("stopped", "已停止"), ("failed", "失败"),
                    ],
                    default="pending", max_length=16,
                )),
                ("task_token", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("error_message", models.TextField(blank=True)),
                ("keywords", models.JSONField(blank=True, default=list)),
                ("keyword_count", models.PositiveIntegerField(default=0)),
                ("processed_seeds", models.PositiveIntegerField(default=0)),
                ("current_round", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
