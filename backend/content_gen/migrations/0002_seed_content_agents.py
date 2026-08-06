from django.db import migrations

# 内置默认提示词（与 services.py 保持一致）。迁移里内联一份，避免依赖运行时代码。
DEFAULT_METADATA_PROMPT = """# 角色
你是一位资深的 YouTube 内容运营，擅长为博彩/娱乐类视频撰写高点击率的标题、描述与封面创意。

# 目标
根据给定的搜索关键词，生成一条 YouTube 视频的元数据：标题、描述、封面提示词。
标题要围绕关键词做自然搜索截流；描述为视频描述区文案；封面提示词用英文，描述一张吸引点击的缩略图画面。

# 输入
关键词：[input]

# 输出
[output]"""

DEFAULT_STORYBOARD_PROMPT = """# 角色
你是一位短视频分镜脚本师，擅长把一个主题拆成若干个连贯的短镜头，用于 AI 视频生成工具出片。

# 目标
根据给定的搜索关键词，生成一个短视频的分镜脚本，目的是推广 promo code。
分镜要求见下方输出格式，请严格按指定的分镜段数和每段时长来拆分。

# 输入
关键词：[input]

# 输出
[output]"""

AGENTS = [
    ("metadata", "元数据生成 Agent", "根据关键词生成 YouTube 标题、描述、封面提示词", DEFAULT_METADATA_PROMPT),
    ("storyboard", "脚本分镜生成 Agent", "根据关键词生成分镜脚本（默认 8+8 两段）", DEFAULT_STORYBOARD_PROMPT),
]


def seed_agents(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    for agent_type, name, description, prompt in AGENTS:
        ContentAgent.objects.get_or_create(
            agent_type=agent_type,
            defaults={"name": name, "description": description, "prompt": prompt, "enabled": True},
        )


def remove_agents(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    ContentAgent.objects.filter(agent_type__in=[a[0] for a in AGENTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("content_gen", "0001_initial")]

    operations = [
        migrations.RunPython(seed_agents, remove_agents),
    ]
