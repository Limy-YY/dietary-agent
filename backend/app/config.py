"""应用配置：从 .env 读取。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库：不写死口令，密码由 .env / 环境变量 DATABASE_URL 或 PGPASSWORD 提供
    DATABASE_URL: str = "postgresql+psycopg://diet_app@localhost:5432/diet_agent"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
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
    # RRF 混合检索：融合常数与召回池写死，与 knowledge.search_documents 默认值对齐
    RAG_TOP_K: int = 5
    RAG_RRF_K: int = 60
    RAG_CANDIDATE_K: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
