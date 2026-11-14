"""疾病规则（T6/T7/T8 / API-17/18/19）请求与响应模型。"""
from datetime import date
from typing import Any

from pydantic import BaseModel


class ConditionItem(BaseModel):
    """病种字典项（档案三态选择用，取自 core.health_condition）。"""

    condition_id: str
    name_zh: str
    category: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    activation_status: str | None = None


class RuleItem(BaseModel):
    """规则目录项（T6/T7，取自 v_condition_rule_catalog / v_production_condition_rules）。"""

    rule_id: str
    condition_id: str | None = None
    condition_name_zh: str | None = None
    rule_name_zh: str | None = None
    rule_kind: str | None = None
    nutrient_id: str | None = None
    nutrient_name_zh: str | None = None
    action: str | None = None
    comparator: str | None = None
    target_value: float | None = None
    target_unit: str | None = None
    time_basis: str | None = None
    population: Any = None
    selector: Any = None
    message_zh: str | None = None
    safety_note_zh: str | None = None
    review_status: str | None = None
    medical_review_required: bool | None = None
    is_active: bool | None = None
    production_ready: bool | None = None
    sources: list | None = None


class EvaluateRuleRequest(BaseModel):
    user_id: str
    intake_date: date
    rule_id: str


class EvaluateRuleResult(BaseModel):
    """规则评估结果（T8）。"""

    user_id: str
    intake_date: str
    rule_id: str
    condition_id: str | None = None
    condition_status: str | None = None
    review_status: str | None = None
    production_ready: bool | None = None
    comparator: str | None = None
    applied_target: float | None = None
    target_unit: str | None = None
    known_total: float | None = None
    record_count: int | None = None
    missing_value_count: int | None = None
    full_day_scope: bool | None = None
    evaluation_status: str | None = None
    explanation_zh: str | None = None
