"""用户档案 ORM（对应 app.profile，数据库 v1.2）。

v1.2 字段口径：
- 新字段 gender / goal_code / cooking_equipment / religious_ethical / target_calories
- 旧字段 sex / activity_level / goal / taboos 仍在库中（迁移期兼容），业务只写新字段
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Profile(Base):
    __tablename__ = "profile"
    __table_args__ = {"schema": "app"}

    profile_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # ── v1.2 主字段 ─────────────────────────────────────────────
    name: Mapped[str | None] = mapped_column(Text)
    avatar: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)
    goal_code: Mapped[str | None] = mapped_column(Text)
    cooking_equipment: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    allergies: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    religious_ethical: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    target_calories: Mapped[Decimal | None] = mapped_column(Numeric)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    # ── 迁移期残留字段（业务不再写入，仅供旧接口兼容）─────────────
    sex: Mapped[str | None] = mapped_column(Text)
    activity_level: Mapped[str | None] = mapped_column(Text)
    goal: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[date | None] = mapped_column(Date)
    taboos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    extras: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
