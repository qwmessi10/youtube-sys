import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("keywords", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="keywordrun",
            name="task_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AlterField(
            model_name="keywordrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待处理"), ("running", "处理中"), ("paused", "已暂停"),
                    ("stopped", "已停止"), ("completed", "已完成"), ("failed", "失败"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
