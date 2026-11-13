"""营养核算（T11 / API-09）请求与响应模型。"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CalcItemInput(BaseModel):
    """核算条目：菜式口径 {dish_id, servings} 或食材口径 {ingredient_id, amount_g}。"""

    dish_id: str | None = None
    servings: float = 1.0
    ingredient_id: int | None = None
    amount_g: float | None = None

    @model_validator(mode="after")
    def _check_fields(self):
        if self.dish_id is None and self.ingredient_id is None:
            raise ValueError("dish_id 与 ingredient_id 必须二选一")
        return self


class CalcNutritionRequest(BaseModel):
    target_type: Literal["dish", "ingredient"]
    items: list[CalcItemInput] = Field(min_length=1, description="条目列表，至少 1 条")
    include_micro: bool = True


class CalcItemResult(BaseModel):
    """逐条目核算结果。"""

    name: str
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    calcium_mg: float | None = None
    magnesium_mg: float | None = None
    potassium_mg: float | None = None
    dish_id: str | None = None
    servings: float | None = None
    ingredient_id: int | None = None
    amount_g: float | None = None
    note: str | None = None
    # evidence 置信度标签待数据岗确认（D1：official/approx/check 是否入库），当前占位
    evidence: str | None = None


class CalcTotal(BaseModel):
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    calcium_mg: float | None = None
    magnesium_mg: float | None = None
    potassium_mg: float | None = None
    energy_complete: bool = True
    protein_complete: bool = True
    fat_complete: bool = True
    carb_complete: bool = True
    sodium_complete: bool = True


class NutritionResult(BaseModel):
    target_type: str
    method: str
    total: CalcTotal
    by_item: list[CalcItemResult]
    source: str
    source_id: str | None = None
