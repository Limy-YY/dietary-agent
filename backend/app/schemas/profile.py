"""用户档案（API-01/02、API-20）请求与响应模型。

对应《后端接口契约 v1.2》§3.3：可写 11 项 + 只读 `target_calories / profile_version`，
`sex / goal / taboos / activity_level / birth_date / extras` 为 v1.1 兼容列（只读回显）。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConditionStatus = Literal["confirmed", "suspected", "unknown"]


class ProfileUpsertRequest(BaseModel):
    """API-01 写档案（upsert）。

    `target_calories` 由后端按 `BMR(Mifflin-St Jeor) × 1.4` 计算落库，请求体里的该字段被忽略；
    `user_id` 以鉴权身份为准，请求体里的同名值不参与写入。
    """

    model_config = ConfigDict(extra="ignore")

    user_id: str | None = None
    name: str | None = Field(default=None, max_length=64)
    avatar: str | None = None
    gender: Literal["男", "女"]
    age: int = Field(ge=10, le=100)
    height_cm: float = Field(ge=120, le=220)
    weight_kg: float = Field(ge=30, le=200)
    goal_code: str
    cooking_equipment: list[str] = Field(default_factory=list)
    # {"<condition_id>": {"status": "confirmed|suspected|unknown", ...}}
    conditions: dict[str, dict] = Field(default_factory=dict)
    allergies: list[str] = Field(default_factory=list)
    religious_ethical: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """Profile 出参：v1.2 可写 11 项 + 只读项 + v1.1 兼容列回显。"""

    user_id: str
    name: str | None = None
    avatar: str | None = None
    gender: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal_code: str | None = None
    goal_name: str | None = None
    cooking_equipment: list[str] = Field(default_factory=list)
    conditions: dict = Field(default_factory=dict)
    allergies: list[str] = Field(default_factory=list)
    religious_ethical: list[str] = Field(default_factory=list)
    target_calories: float | None = None
    profile_version: int | None = None
    # v1.1 兼容列（只读回显，新接口不再写入）
    sex: str | None = None
    goal: str | None = None
    taboos: list[str] = Field(default_factory=list)
    birth_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # 该行是否仍在用 v1.1 旧列（视图 computed 列）
    gender_from_legacy: bool = False
    goal_code_from_legacy: bool = False
