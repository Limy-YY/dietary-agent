"""菜式搜索（T2/T3 / API-12）请求与响应模型。"""
from pydantic import BaseModel


class DishItem(BaseModel):
    dish_id: str
    name: str
    tags: list[str] | None = None
    method_text: str | None = None
    cooking_rule_id: str | None = None
    servings: float | None = None
    default_oil_g: float | None = None
    default_salt_g: float | None = None
    ingredient_count: int | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    sodium_mg: float | None = None
    calcium_mg: float | None = None
    energy_complete: bool | None = None
    protein_complete: bool | None = None
    sodium_complete: bool | None = None
    calcium_complete: bool | None = None
    strict_allergens: list[str] | None = None
    unverified_food_ids: list[str] | None = None
    allergen_verification_complete: bool | None = None
    source: str | None = None
    source_id: str | None = None
    # 过敏原筛查决策（T3，仅传 exclude_allergies 时返回）
    decision: str | None = None
    reason: str | None = None
