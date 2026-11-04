# Generated migration for SMM 面板系统
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SMMAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tg_user_id", models.CharField(max_length=32, unique=True, verbose_name="Telegram 数字 ID")),
                ("username", models.CharField(blank=True, default="", max_length=100, verbose_name="@用户名(展示用)")),
                ("first_name", models.CharField(blank=True, default="", max_length=100)),
                ("last_name", models.CharField(blank=True, default="", max_length=100)),
                ("panel_user_name", models.CharField(blank=True, default="", max_length=100, verbose_name="面板昵称")),
                ("token", models.CharField(blank=True, default="", max_length=200)),
                ("user_identifier", models.CharField(blank=True, default="", max_length=100)),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="余额(₹)")),
                ("status", models.CharField(choices=[("active", "有效"), ("token_invalid", "token 失效")], default="active", max_length=20)),
                ("remark", models.CharField(blank=True, default="", max_length=255, verbose_name="备注")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "面板账号",
                "verbose_name_plural": "面板账号",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SMMTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("panel_task_id", models.CharField(blank=True, default="", max_length=64, verbose_name="面板任务ID")),
                ("show_id", models.CharField(blank=True, default="", max_length=100, verbose_name="任务号")),
                ("youtube_link", models.CharField(max_length=500)),
                ("key_words", models.CharField(blank=True, default="", max_length=500, verbose_name="关键词")),
                ("total_user", models.IntegerField(default=0, verbose_name="人数")),
                ("per_user", models.DecimalField(decimal_places=2, default=2, max_digits=10, verbose_name="每人奖励(₹)")),
                ("task_type", models.IntegerField(default=42, verbose_name="服务类型")),
                ("plant_form", models.IntegerField(default=1, verbose_name="平台")),
                ("comment_num", models.IntegerField(default=1, verbose_name="评论数")),
                ("end_time", models.CharField(blank=True, default="", max_length=32, verbose_name="结束时间")),
                ("cost", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="成本(₹)")),
                ("status", models.CharField(choices=[("pending", "进行中"), ("running", "进行中"), ("completed", "已完成"), ("failed", "失败")], default="pending", max_length=20, verbose_name="状态")),
                ("panel_status", models.CharField(blank=True, default="", max_length=50, verbose_name="面板原始状态")),
                ("progress", models.JSONField(blank=True, default=dict, verbose_name="进度")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="smm.smmaccount")),
            ],
            options={
                "verbose_name": "刷量任务",
                "verbose_name_plural": "刷量任务",
                "ordering": ["-created_at"],
            },
        ),
    ]
