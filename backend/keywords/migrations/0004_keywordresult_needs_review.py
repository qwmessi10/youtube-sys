from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("keywords", "0003_alter_keywordrun_max_keywords")]

    operations = [
        migrations.AlterField(
            model_name="keywordresult",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待验证"),
                    ("serpapi_error", "SerpApi 查询失败"),
                    ("rule_scored", "规则打分完成"),
                    ("needs_review", "数据不全，需人工复核"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
    ]
