import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from flow3.models import Flow3Material

# flow3/seed_media/ —— 随 git 分发的种子素材文件（结构与 MEDIA_ROOT 一致）。
SEED_MEDIA_DIR = Path(__file__).resolve().parents[2] / "seed_media"


class Command(BaseCommand):
    help = (
        "首次部署导入种子：Hook 分组 + 素材元数据 + keywords AgentPrompt，"
        "并把 seed_media/ 素材文件复制到 MEDIA_ROOT。"
        "幂等：数据库已有素材则整体跳过，不覆盖同事已有数据。"
        "Agent 提示词另由 sync_prompts 从 prompts/*.md 同步。"
    )

    def handle(self, *args, **options):
        if Flow3Material.objects.exists():
            self.stdout.write(self.style.WARNING("[load_seed] 已存在素材数据，跳过种子导入。"))
            return
        # 1) 先把种子素材文件铺到 MEDIA_ROOT（fixture 里的 file 路径才能对应到真实文件）。
        if SEED_MEDIA_DIR.is_dir():
            copied = 0
            for src in SEED_MEDIA_DIR.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(SEED_MEDIA_DIR)
                    dst = Path(settings.MEDIA_ROOT) / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied += 1
            self.stdout.write(self.style.SUCCESS(f"[load_seed] 复制种子素材文件 {copied} 个到 MEDIA_ROOT。"))
        # 2) 导入 fixture（分组/素材/keywords 提示词）。
        try:
            call_command("loaddata", "seed.json", verbosity=1)
            self.stdout.write(self.style.SUCCESS("[load_seed] 种子数据导入完成。"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"[load_seed] 导入失败：{exc}"))
