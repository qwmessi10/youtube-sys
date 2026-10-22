from django.core.management.base import BaseCommand

from flow3.prompt_store import sync_from_files


class Command(BaseCommand):
    help = "读 flow3/prompts/<agent_type>.md 覆盖写回数据库（文件为准）。容器启动时自动执行。"

    def handle(self, *args, **options):
        updated, missing = sync_from_files()
        self.stdout.write(self.style.SUCCESS(f"[sync_prompts] 已更新 {updated} 个 Agent 提示词。"))
        if missing:
            self.stdout.write(self.style.WARNING(f"[sync_prompts] 无对应文件（保持 DB 原值）：{missing}"))
