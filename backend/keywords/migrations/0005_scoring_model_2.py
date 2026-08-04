from django.db import migrations, models


def set_existing_runs_to_v1(apps, schema_editor):
    """已存在的旧任务在 2.0 上线前创建，统一回填为 1.0 模型。"""
    KeywordRun = apps.get_model("keywords", "KeywordRun")
    KeywordRun.objects.update(scoring_model="1.0")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("keywords", "0004_keywordresult_needs_review")]

    operations = [
        migrations.AddField(
            model_name="keywordrun",
            name="scoring_model",
            field=models.CharField(
                choices=[
                    ("1.0", "打分模型 1.0（前 5 视频规则打分）"),
                    ("2.0", "打分模型 2.0（AI 博彩意图筛选 + 全量视频打分）"),
                ],
                default="2.0",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="keywordresult",
            name="agent_result",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="keywordresult",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待验证"),
                    ("serpapi_error", "SerpApi 查询失败"),
                    ("rule_scored", "规则打分完成"),
                    ("needs_review", "数据不全，需人工复核"),
                    ("eliminated", "已淘汰"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
        migrations.RunPython(set_existing_runs_to_v1, noop_reverse),
    ]
