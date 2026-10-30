"""配置加载：从 .env（同目录）读取，回退环境变量与默认值。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


BACKEND_BASE = os.getenv("BACKEND_BASE", "http://127.0.0.1:8000").rstrip("/")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
ADSPOWER_API_BASE = os.getenv("ADSPOWER_API_BASE", "http://local.adspower.net:50325").rstrip("/")
ADSPOWER_API_KEY = os.getenv("ADSPOWER_API_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
DRAFT_ONLY = _bool(os.getenv("DRAFT_ONLY", "True"))
HEADLESS = _bool(os.getenv("HEADLESS", "False"))
WORK_DIR = (BASE_DIR / os.getenv("WORK_DIR", "./_work")).resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)
