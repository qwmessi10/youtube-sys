"""
Agent 提示词「文件 ↔ 数据库」同步。

设计：**文件（backend/flow3/prompts/<agent_type>.md）是唯一真相源**。
- 用户在界面保存某 Agent → 写 DB 的同时导出该 Agent 到对应 .md（export_one）。
- 把 .md 提交 git → 同事拉代码后，容器启动执行 sync_prompts → 读 .md 覆盖写回 DB。
这样提示词作为可读、可 diff、可 review 的代码资产随仓库分发，不会只存在某台机器的 DB 里。
"""
import os

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _path(agent_type):
    return os.path.join(PROMPTS_DIR, f"{agent_type}.md")


def export_one(agent_type, prompt):
    """把单个 Agent 的提示词写到 prompts/<agent_type>.md。"""
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    with open(_path(agent_type), "w", encoding="utf-8", newline="\n") as f:
        f.write(prompt or "")


def export_all():
    """把 DB 里所有 Agent 的提示词导出到文件。返回导出的 agent_type 列表。"""
    from .models import Flow3Agent
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    done = []
    for a in Flow3Agent.objects.all():
        export_one(a.agent_type, a.prompt)
        done.append(a.agent_type)
    return done


def sync_from_files():
    """读 prompts/*.md 覆盖写回 DB（文件为准）。返回 (更新数, 缺文件的 agent_type 列表)。"""
    from .models import Flow3Agent
    updated, missing = 0, []
    for a in Flow3Agent.objects.all():
        p = _path(a.agent_type)
        if not os.path.exists(p):
            missing.append(a.agent_type)
            continue
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        if content != a.prompt:
            a.prompt = content
            a.save(update_fields=["prompt", "updated_at"])
            updated += 1
    return updated, missing
