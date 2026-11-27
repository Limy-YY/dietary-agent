"""应用配置：从 .env 读取。"""
import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# B6/#28：JWT 密钥强度基线。占位串或不足 32 字节一律视为弱密钥
PLACEHOLDER_JWT_SECRET = "dev-only-placeholder-change-me-32bytes"
MIN_JWT_SECRET_LEN = 32
PRODUCTION_ENVS = {"prod", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 运行环境：dev（默认）/ production。production 下弱密钥直接拒绝启动（#28）
    APP_ENV: str = "dev"

    # 数据库：不写死口令，密码由 .env / 环境变量 DATABASE_URL 或 PGPASSWORD 提供
    DATABASE_URL: str = "postgresql+psycopg://diet_app@localhost:5432/diet_agent"

    # JWT（B6/#28：必须 ≥32 字节；.env 里配真实随机串，默认值仅占位，缺配置时启动即报弱密钥告警）
    JWT_SECRET: str = PLACEHOLDER_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = 1440

    # 服务
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    # Embedding / RAG（依据 Agent 岗 2026-11-14 定稿：bge-m3 / 1024 维，维度定后不改）
    # 方案 A 云端（默认）：EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1, EMBEDDING_MODEL=BAAI/bge-m3
    # 方案 B 本地：EMBEDDING_BASE_URL=http://127.0.0.1:11434, EMBEDDING_MODEL=bge-m3, EMBEDDING_API_KEY=ollama
    EMBEDDING_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_DIM: int = 1024
    EMBEDDING_TIMEOUT_S: int = 30
    # RRF 混合检索的融合常数：写入 SQL 调用参数，与 knowledge.search_documents 默认值对齐
    RAG_RRF_K: int = 60
    # B5 召回参数（2026-11-25 用 tests/eval_recall.py 的 24 条问句评测定值）：
    # min_similarity 0.3/0.4/0.5 均为 recall@5=100%，0.6 掉到 91.67% → 取 0.5 兼顾召回与噪声；
    # rrf_k 用 RRF 标准值 60；top_k 默认 5 与契约一致。
    # 候选池大小（函数内 p_limit*4）与两路权重（1:1）写在 knowledge.search_documents 里，改动需走变更评审。
    RAG_MIN_SIMILARITY: float = 0.5
    RAG_TOP_K_DEFAULT: int = 5
    RAG_POOL_MULTIPLIER: int = 4  # 仅用于文档记录后端对池大小的预期，实际池由 SQL 函数决定

    # Agent 服务（agent/ 目录的 FastAPI，默认 8001）：/agent/chat 代理目标
    AGENT_BASE_URL: str = "http://127.0.0.1:8001"
    AGENT_TIMEOUT_S: float = 60.0

    @property
    def jwt_secret_is_weak(self) -> bool:
        """占位串（含 .env.example 的 <random-secret>）或长度不足 32 字节，视为弱密钥。"""
        secret = (self.JWT_SECRET or "").strip()
        return (
            secret.startswith("dev-only-placeholder")
            or secret == "change-me-in-production"
            or len(secret) < MIN_JWT_SECRET_LEN
        )

    @model_validator(mode="after")
    def _guard_jwt_secret(self) -> "Settings":
        """#28：服务端弱密钥防护。dev 告警不阻断，production 直接拒绝启动。"""
        if not self.jwt_secret_is_weak:
            return self
        message = (
            f"[SECURITY] JWT_SECRET 为占位/弱密钥（{len(self.JWT_SECRET or '')} 字节，"
            f"要求 ≥{MIN_JWT_SECRET_LEN}），仅限本地开发；"
            '生成方式：python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
        if (self.APP_ENV or "").strip().lower() in PRODUCTION_ENVS:
            raise ValueError(f"{message}；APP_ENV={self.APP_ENV} 下拒绝启动")
        logger.warning(message)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
