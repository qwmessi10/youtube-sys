# Generated migration for 数据分析系统
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("flow3", "0010_flow3agent_model"),
        ("uploader", "0004_alter_proxyconfig_unique_together"),
    ]

    operations = [
        migrations.CreateModel(
            name="VideoLibraryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("video_id", models.CharField(max_length=32, unique=True, verbose_name="YouTube 视频 ID")),
                ("video_url", models.CharField(max_length=500, verbose_name="视频链接")),
                ("title", models.CharField(blank=True, default="", max_length=500, verbose_name="标题")),
                ("channel_name", models.CharField(blank=True, default="", max_length=255, verbose_name="频道")),
                ("channel_id", models.CharField(blank=True, default="", max_length=100, verbose_name="频道 ID")),
                ("source", models.CharField(choices=[("auto", "自动关联"), ("manual", "手动添加")], default="manual", max_length=16, verbose_name="来源")),
                ("remark", models.CharField(blank=True, default="", max_length=255, verbose_name="备注")),
                ("view_count", models.BigIntegerField(blank=True, null=True, verbose_name="播放量")),
                ("like_count", models.BigIntegerField(blank=True, null=True, verbose_name="点赞")),
                ("comment_count", models.BigIntegerField(blank=True, null=True, verbose_name="评论")),
                ("published_at", models.DateTimeField(blank=True, null=True, verbose_name="发布时间")),
                ("duration", models.CharField(blank=True, default="", max_length=32, verbose_name="时长(ISO8601)")),
                ("snapshot_at", models.DateTimeField(blank=True, null=True, verbose_name="数据更新时间")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("upload_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="video_library_items", to="uploader.uploadtask")),
                ("flow3_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="video_library_items", to="flow3.flow3run")),
            ],
            options={
                "verbose_name": "视频库条目",
                "verbose_name_plural": "视频库条目",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="VideoMetricSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("view_count", models.BigIntegerField(blank=True, null=True)),
                ("like_count", models.BigIntegerField(blank=True, null=True)),
                ("comment_count", models.BigIntegerField(blank=True, null=True)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                ("video", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="analytics.videolibraryitem")),
            ],
            options={
                "verbose_name": "视频指标快照",
                "verbose_name_plural": "视频指标快照",
                "ordering": ["captured_at"],
            },
        ),
        migrations.CreateModel(
            name="CompetitorAnalysis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keyword", models.CharField(max_length=255, verbose_name="关键词")),
                ("country", models.CharField(default="US", max_length=8, verbose_name="国家")),
                ("language", models.CharField(default="en", max_length=16, verbose_name="语言")),
                ("top_n", models.PositiveSmallIntegerField(default=10, verbose_name="取前 N")),
                ("status", models.CharField(choices=[("pending", "待处理"), ("running", "分析中"), ("completed", "已完成"), ("failed", "失败")], default="pending", max_length=16, verbose_name="状态")),
                ("result", models.JSONField(blank=True, default=dict, verbose_name="分析结果")),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "竞品 SEO 分析",
                "verbose_name_plural": "竞品 SEO 分析",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="KeywordRankTracking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keyword", models.CharField(max_length=255, verbose_name="关键词")),
                ("country", models.CharField(default="US", max_length=8, verbose_name="国家")),
                ("language", models.CharField(default="en", max_length=16, verbose_name="语言")),
                ("top_n", models.PositiveSmallIntegerField(default=10, verbose_name="取前 N")),
                ("enabled", models.BooleanField(default=True, verbose_name="启用")),
                ("last_captured_at", models.DateTimeField(blank=True, null=True, verbose_name="最近抓取时间")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "排名追踪配置",
                "verbose_name_plural": "排名追踪配置",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="KeywordRankSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                ("videos", models.JSONField(blank=True, default=list, verbose_name="排名数据")),
                ("tracking", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="analytics.keywordranktracking")),
            ],
            options={
                "verbose_name": "排名快照",
                "verbose_name_plural": "排名快照",
                "ordering": ["captured_at"],
            },
        ),
    ]
