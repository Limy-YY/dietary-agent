"""应用配置：从 .env 读取。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库
    DATABASE_URL: str = "postgresql+psycopg://diet_app:diet_app_dev@localhost:5432/diet_agent"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = 1440

    # 服务
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
