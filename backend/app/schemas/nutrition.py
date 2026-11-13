"""周度营养报告（T4+T5 / API-13）响应模型。"""
from pydantic import BaseModel


class ReferenceItem(BaseModel):
    """营养参考值匹配（T4）。"""

    nutrient_id: str
    nutrient_name: str
    unit: str
    reference_type: str
    reference_value: float | None = None
    ul_value: float | None = None
    sex: str | None = None
    age_group: str | None = None
    life_stage: str | None = None
    menstrual_status: str | None = None
    needs_clarification: bool = False


class UlAssessmentItem(BaseModel):
    """周度 UL 评估（T5）。"""

    nutrient_id: str
    nutrient_name: str | None = None
    unit: str | None = None
    days_recorded: int = 0
    weekly_total: float | None = None
    daily_average: float | None = None
    daily_max: float | None = None
    ul_value: float | None = None
    days_over_ul: int = 0
    evaluation_status: str


class WeeklyReport(BaseModel):
    user_id: str
    week_start: str
    age_months: int | None = None
    sex: str | None = None
    references: list[ReferenceItem]
    ul_assessment: list[UlAssessmentItem]
    intake_records: list[dict]
    notes: list[str]
