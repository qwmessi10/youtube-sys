from django.db import migrations

# 流程一·音频脚本 Agent 内置默认提示词（与 services.py 保持一致）。
DEFAULT_NARRATION_PROMPT = """# 角色
你是一位短视频口播文案师，擅长为推广类视频撰写自然、口语化、有号召力的旁白。

# 目标
根据给定的搜索关键词，撰写一段用于视频配音（TTS 朗读）的旁白文案，目的是推广 promo code、引导观众注册。
画面由固定模板呈现，你无需描述画面，只需产出要被朗读出来的旁白文字。
按下方输出格式，把旁白拆成若干段，每段对应视频的一个时间片段。

# 输入
关键词：[input]

# 输出
[output]"""

AGENT = ("narration", "音频脚本生成 Agent", "流程一：根据关键词生成旁白配音文案（分段）", DEFAULT_NARRATION_PROMPT)


def seed_agent(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    agent_type, name, description, prompt = AGENT
    ContentAgent.objects.get_or_create(
        agent_type=agent_type,
        defaults={"name": name, "description": description, "prompt": prompt, "enabled": True},
    )


def remove_agent(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    ContentAgent.objects.filter(agent_type=AGENT[0]).delete()


class Migration(migrations.Migration):
    dependencies = [("content_gen", "0005_videotemplate_alter_contentitem_options_and_more")]

    operations = [
        migrations.RunPython(seed_agent, remove_agent),
    ]
