"""食材搜索（T1 / API-11）请求与响应模型。"""
from pydantic import BaseModel


class IngredientItem(BaseModel):
    food_id: str
    name: str
    aliases: list[str] | None = None
    category: str | None = None
    state: str | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbohydrate_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    calcium_mg: float | None = None
    magnesium_mg: float | None = None
    potassium_mg: float | None = None
    purine_level: str | None = None
    sfa_g: float | None = None
    iodine_ug: float | None = None
    data_quality: str | None = None
    source_note: str | None = None
    edible_portion_pct: float | None = None
    allergens: list[str] | None = None
    allergen_status: str | None = None
    has_missing_macro: bool | None = None
    source_url: str | None = None
    match_type: str | None = None
