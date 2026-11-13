"""用户档案（API-01/02、T12 / API-20）请求与响应模型。"""
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    sex: str | None = None
    age: int | None = None
    birth_date: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity_level: str | None = None
    goal: str | None = None
    allergies: list[str] = []
    taboos: list[str] = []
    conditions: list[str] = []
    # app.profile 无独立 menstrual_status 列，取 extras.menstrual_status（可空）
    menstrual_status: str | None = None
    extras: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProfileUpsertRequest(BaseModel):
    """API-01 创建 / 更新用户档案。"""

    user_id: str
    sex: str | None = None
    age: int | None = None
    birth_date: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity_level: str | None = None
    goal: str | None = None
    allergies: list[str] = Field(default_factory=list)
    taboos: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    extras: dict | None = None
