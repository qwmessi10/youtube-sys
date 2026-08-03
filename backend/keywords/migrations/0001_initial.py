from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GlobalSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=100, unique=True)),
                ("value", models.TextField(blank=True)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="KeywordRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("root_keyword", models.CharField(max_length=255)),
                ("country", models.CharField(default="US", max_length=8)),
                ("language", models.CharField(default="en", max_length=16)),
                ("max_keywords", models.PositiveSmallIntegerField(default=30)),
                ("status", models.CharField(choices=[("pending", "待处理"), ("running", "处理中"), ("completed", "已完成"), ("failed", "失败")], default="pending", max_length=16)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="KeywordResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keyword", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("pending", "待验证"), ("serpapi_error", "SerpApi 查询失败"), ("rule_scored", "规则打分完成")], default="pending", max_length=32)),
                ("elimination_stage", models.CharField(blank=True, max_length=64)),
                ("elimination_reason", models.TextField(blank=True)),
                ("serpapi_status", models.CharField(default="pending", max_length=32)),
                ("top5_video_data", models.JSONField(blank=True, default=list)),
                ("score_breakdown", models.JSONField(blank=True, default=dict)),
                ("rule_score", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("final_decision", models.CharField(default="待人工复核", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="results", to="keywords.keywordrun")),
            ],
            options={"ordering": ["-rule_score", "keyword"]},
        ),
        migrations.AddConstraint(
            model_name="keywordresult",
            constraint=models.UniqueConstraint(fields=("run", "keyword"), name="unique_keyword_per_run"),
        ),
    ]

