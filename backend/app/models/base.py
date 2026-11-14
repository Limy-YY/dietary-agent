"""ORM 基类（SQLAlchemy 2.0 Declarative）。

所有模型显式声明 `schema="app"`，与数据库 v1.2 的 app / core 分 schema 保持一致。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """全局声明基类。"""
