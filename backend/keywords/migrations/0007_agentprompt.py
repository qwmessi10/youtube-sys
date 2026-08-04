from django.db import migrations, models


def seed_intent_agent(apps, schema_editor):
    """
    初始化 2.0 的「博彩意图识别」Agent。
    如果用户之前在全局设置里填过 AI_BETTING_INTENT_PROMPT，把它迁移过来；
    否则 prompt 留空，运行时回退到代码内默认提示词。
    """
    AgentPrompt = apps.get_model("keywords", "AgentPrompt")
    GlobalSetting = apps.get_model("keywords", "GlobalSetting")
    old = GlobalSetting.objects.filter(key="AI_BETTING_INTENT_PROMPT").values_list("value", flat=True).first()
    AgentPrompt.objects.get_or_create(
        scoring_model="2.0",
        agent_type="intent",
        defaults={
            "name": "博彩意图识别",
            "description": "判断 Suggest 长尾词是否具备博彩投注意向，只放行高意向词进入打分。",
            "prompt": old or "",
            "enabled": True,
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("keywords", "0006_keywordrun_run_log")]

    operations = [
        migrations.CreateModel(
            name="AgentPrompt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scoring_model", models.CharField(max_length=8)),
                ("agent_type", models.CharField(choices=[("intent", "关键词意图识别")], max_length=32)),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("prompt", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["scoring_model", "agent_type"]},
        ),
        migrations.AddConstraint(
            model_name="agentprompt",
            constraint=models.UniqueConstraint(fields=["scoring_model", "agent_type"], name="unique_agent_per_model"),
        ),
        migrations.RunPython(seed_intent_agent, noop_reverse),
    ]
