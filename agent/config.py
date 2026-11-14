# -*- coding: utf-8 -*-
"""Agent 服务配置：读取同目录 .env（不依赖第三方 dotenv 库，直接解析）。"""
import os
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _BASE_DIR.parent / "backend"


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：KEY=VALUE，忽略空行与 # 注释，不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(_BASE_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


# ---- 服务自身 ----
AGENT_HOST: str = _env("AGENT_HOST", "127.0.0.1")
AGENT_PORT: int = int(_env("AGENT_PORT", "8001"))

# ---- 后端 REST 服务（8000 端口）----
BACKEND_BASE_URL: str = _env("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# ---- 数据库（rule_engine 的 SqlDataSource 用）----
DATABASE_URL: str = _env(
    "DATABASE_URL", "postgresql+psycopg://diet_app:diet_app_dev@localhost:5432/diet_agent"
)

# ---- 大模型（DeepSeek，OpenAI 兼容）----
DEEPSEEK_API_KEY: str = _env("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL: str = _env("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL: str = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# ---- 后端代码路径（用于 import app.services.rule_engine）----
BACKEND_DIR: str = _env("BACKEND_DIR", str(_BACKEND_DIR))
