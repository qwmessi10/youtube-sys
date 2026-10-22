from django.core.management.base import BaseCommand

from flow3.prompt_store import export_all


class Command(BaseCommand):
    help = "把数据库里所有 Agent 的提示词导出到 flow3/prompts/<agent_type>.md。"

    def handle(self, *args, **options):
        done = export_all()
        self.stdout.write(self.style.SUCCESS(f"[export_prompts] 已导出 {len(done)} 个：{done}"))
