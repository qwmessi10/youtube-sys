from django.db import migrations

# 内置默认提示词（与 services.DEFAULT_BETTING_INTENT_PROMPT 保持一致）。
# 迁移里内联一份，避免依赖运行时代码；后续如改默认词，以 services.py 为准。
DEFAULT_BETTING_INTENT_PROMPT = """# 角色
你是一个YouTube专业的关键词分析与体育、娱乐游戏运营，有10年的运营经验

# 目标
通过批量获取到的搜索词，判断搜索词是否有博彩意向；如果有博彩意向，则以json格式全部输出

# 输入
[input]

# 输出
[output]"""

DEFAULTS = {
    ("2.0", "intent"): DEFAULT_BETTING_INTENT_PROMPT,
}


def fill_prompt(apps, schema_editor):
    """把空提示词的 Agent 回填为内置默认提示词，让管理页能直接看到并编辑。"""
    AgentPrompt = apps.get_model("keywords", "AgentPrompt")
    for agent in AgentPrompt.objects.all():
        if not (agent.prompt or "").strip():
            default = DEFAULTS.get((agent.scoring_model, agent.agent_type))
            if default:
                agent.prompt = default
                agent.save(update_fields=["prompt"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("keywords", "0007_agentprompt")]

    operations = [
        migrations.RunPython(fill_prompt, noop_reverse),
    ]
