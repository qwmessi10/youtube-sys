# 轮询刷量任务
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("smm", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SMMPollTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("youtube_link", models.CharField(max_length=500)),
                ("key_words", models.CharField(blank=True, default="", max_length=500, verbose_name="关键词")),
                ("per_user", models.DecimalField(decimal_places=2, default=2, max_digits=10, verbose_name="每人奖励(₹)")),
                ("task_type", models.IntegerField(default=42, verbose_name="服务类型")),
                ("plant_form", models.IntegerField(default=1, verbose_name="平台")),
                ("comment_num", models.IntegerField(default=1, verbose_name="评论数")),
                ("initial_count", models.IntegerField(blank=True, null=True, verbose_name="首次刷量人数")),
                ("poll_total", models.IntegerField(verbose_name="轮询次数")),
                ("poll_done", models.IntegerField(default=0, verbose_name="已刷次数")),
                ("batch_min", models.IntegerField(default=1, verbose_name="每批人数下限")),
                ("batch_max", models.IntegerField(default=5, verbose_name="每批人数上限")),
                ("window_start_hour", models.IntegerField(default=12, verbose_name="窗口开始小时(北京)")),
                ("window_end_hour", models.IntegerField(default=21, verbose_name="窗口结束小时(北京)")),
                ("status", models.CharField(choices=[("running", "运行中"), ("completed", "已完成"), ("stopped", "已停止"), ("failed", "失败")], default="running", max_length=20, verbose_name="状态")),
                ("next_poll_at", models.DateTimeField(blank=True, null=True, verbose_name="下次执行时间")),
                ("fail_count", models.IntegerField(default=0, verbose_name="连续失败次数")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="poll_tasks", to="smm.smmaccount")),
            ],
            options={
                "verbose_name": "轮询刷量任务",
                "verbose_name_plural": "轮询刷量任务",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="smmtask",
            name="poll_task",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="smm.smmpolltask"),
        ),
    ]
