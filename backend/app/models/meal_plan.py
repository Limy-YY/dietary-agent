"""方案四级表 ORM（数据库 v1.2）。

层级：meal_plan → meal_slot → meal_candidate → meal_candidate_dish

关键约定：
- `meal_candidate.candidate_id` 是**全局自增主键**（IDENTITY），引擎内部的
  candidate_id 只是「餐内序号（rank）」，写入时必须重映射为全局 ID。
- `meal_slot.selected_candidate_id` 与 `meal_slot_id` 组成复合外键指向
  (meal_candidate.candidate_id, meal_candidate.meal_slot_id)，且 DEFERRABLE，
  因此插入顺序为：plan → slot（selected 先留空）→ candidate → 回填 selected。
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MealPlan(Base):
    """方案主表（一次生成 = 一条，一餐/一日/多日/周/自定义都落这里）。"""

    __tablename__ = "meal_plan"
    __table_args__ = {"schema": "app"}

    meal_plan_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app.profile.user_id"), nullable=False)

    plan_type: Mapped[str] = mapped_column(Text, nullable=False)  # 餐/日/多日/周/自定义
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    goal_energy_kcal: Mapped[Decimal | None] = mapped_column(Numeric)
    macro_ratio: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # meals 在库中 NOT NULL 且无默认值：必须由业务显式写入（v1.2 已改为四级表承载，此处保留快照）
    meals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sources: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    generation_request: Mapped[str | None] = mapped_column(Text)
    generation_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    micro_balance_window_start: Mapped[date | None] = mapped_column(Date)
    micro_balance_window_end: Mapped[date | None] = mapped_column(Date)

    agent_version: Mapped[str | None] = mapped_column(Text)
    data_version: Mapped[str] = mapped_column(Text, nullable=False)
    derived_from_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("app.meal_plan.meal_plan_id")
    )

    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    slots: Mapped[list["MealSlot"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="MealSlot.display_order"
    )


class MealSlot(Base):
    """餐位（一餐一行；slot_date + meal_type 定位）。"""

    __tablename__ = "meal_slot"
    __table_args__ = (
        UniqueConstraint("meal_plan_id", "slot_date", "meal_type", "display_order"),
        {"schema": "app"},
    )

    meal_slot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    meal_plan_id: Mapped[int] = mapped_column(
        ForeignKey("app.meal_plan.meal_plan_id", ondelete="CASCADE"), nullable=False
    )
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(Text, nullable=False)  # 早/午/晚/加餐
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    target_macro: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    # 复合外键见 __table_args__ 之后的说明：由 (selected_candidate_id, meal_slot_id)
    # 指向 meal_candidate(candidate_id, meal_slot_id)，DEFERRABLE INITIALLY DEFERRED。
    selected_candidate_id: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    plan: Mapped["MealPlan"] = relationship(back_populates="slots")
    candidates: Mapped[list["MealCandidate"]] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
        order_by="MealCandidate.rank",
        foreign_keys="MealCandidate.meal_slot_id",
    )


# 复合外键单独声明：依赖 candidate_id + meal_slot_id 两列
MealSlot.__table__.append_constraint(
    ForeignKeyConstraint(
        ["selected_candidate_id", "meal_slot_id"],
        ["app.meal_candidate.candidate_id", "app.meal_candidate.meal_slot_id"],
        deferrable=True,
        initially="DEFERRED",
    )
)


class MealCandidate(Base):
    """候选（同一餐位 2~3 个，rank 1..3）。"""

    __tablename__ = "meal_candidate"
    __table_args__ = (
        UniqueConstraint("meal_slot_id", "rank"),
        UniqueConstraint("candidate_id", "meal_slot_id"),
        {"schema": "app"},
    )

    candidate_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    meal_slot_id: Mapped[int] = mapped_column(
        ForeignKey("app.meal_slot.meal_slot_id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    reason_codes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    why_text: Mapped[str | None] = mapped_column(Text)
    macro_estimate: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    micro_estimate: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    oil_salt_estimate: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    eating_order_advice: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    agent_output_version: Mapped[str | None] = mapped_column(Text)
    explanation_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    slot: Mapped["MealSlot"] = relationship(back_populates="candidates", foreign_keys=[meal_slot_id])
    dishes: Mapped[list["MealCandidateDish"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="MealCandidateDish.display_order"
    )


class MealCandidateDish(Base):
    """候选内的具体菜（一候选 = 主食 1 + 菜 1~2）。"""

    __tablename__ = "meal_candidate_dish"
    __table_args__ = {"schema": "app"}

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("app.meal_candidate.candidate_id", ondelete="CASCADE"), primary_key=True
    )
    dish_id: Mapped[str] = mapped_column(Text, primary_key=True)  # 库侧 FK → core.dish，字典表不建 ORM

    role: Mapped[str] = mapped_column(Text, nullable=False)  # 主食 / 菜
    servings: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=1, server_default=text("1"))
    estimated_g: Mapped[Decimal | None] = mapped_column(Numeric)
    portion_text: Mapped[str | None] = mapped_column(Text)
    method_override: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    candidate: Mapped["MealCandidate"] = relationship(back_populates="dishes")
