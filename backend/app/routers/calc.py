"""营养核算接口（T11 / API-09）。

口径说明（确定性计算，Agent 不得自行推算）：
- 菜式口径：能量/蛋白/钠/钙取 app.v_dish_live_nutrition（配料合计）；脂肪/碳水/纤维/镁/钾
  按同口径现算（Σ amount_g × per100g / 100）；食用油按分级估算（default_oil_g × 9 kcal/g
  计入能量与脂肪，符合契约「1g 油脂≈9kcal，不得输出伪精确克数」）。
- 食材口径：core.ingredient 生重值 × 可食部换算（amount_g/100 × edible_portion_pct/100）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.calc import (
    CalcItemInput,
    CalcItemResult,
    CalcNutritionRequest,
    CalcTotal,
    NutritionResult,
)

router = APIRouter(prefix="/calc", tags=["calc"])

_SOURCE = "中国食物成分表（第6版·标准版口径）"

# 菜式视图字段（配料合计，权威）
_DISH_VIEW = (
    "dish_id, name, servings, default_oil_g, default_salt_g, energy_kcal, protein_g, sodium_mg, "
    "calcium_mg, source_id"
)
# 配料现算字段（视图缺失项）：每 100g 口径 × 用量
_DISH_MACRO_SQL = """
SELECT di.dish_id,
    CASE WHEN count(*) FILTER (WHERE i.fat_g IS NULL) > 0 THEN NULL::numeric
         ELSE round(sum(di.amount_g * i.fat_g / 100::numeric), 1) END AS fat_g,
    CASE WHEN count(*) FILTER (WHERE i.carbohydrate_g IS NULL) > 0 THEN NULL::numeric
         ELSE round(sum(di.amount_g * i.carbohydrate_g / 100::numeric), 1) END AS carb_g,
    CASE WHEN count(*) FILTER (WHERE i.fiber_g IS NULL) > 0 THEN NULL::numeric
         ELSE round(sum(di.amount_g * i.fiber_g / 100::numeric), 1) END AS fiber_g,
    CASE WHEN count(*) FILTER (WHERE i.magnesium_mg IS NULL) > 0 THEN NULL::numeric
         ELSE round(sum(di.amount_g * i.magnesium_mg / 100::numeric), 1) END AS magnesium_mg,
    CASE WHEN count(*) FILTER (WHERE i.potassium_mg IS NULL) > 0 THEN NULL::numeric
         ELSE round(sum(di.amount_g * i.potassium_mg / 100::numeric), 1) END AS potassium_mg
FROM core.dish_ingredient di
JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
WHERE di.dish_id = ANY(:ids) AND NOT i.is_deleted
GROUP BY di.dish_id
"""


def _calc_dishes(items: list[CalcItemInput], db: Session) -> list[CalcItemResult]:
    dish_ids = [it.dish_id for it in items]
    views = {
        r["dish_id"]: r
        for r in db.execute(
            text(f"SELECT {_DISH_VIEW} FROM app.v_dish_live_nutrition WHERE dish_id = ANY(:ids)"),
            {"ids": dish_ids},
        ).mappings().all()
    }
    macros = {
        r["dish_id"]: r
        for r in db.execute(text(_DISH_MACRO_SQL), {"ids": dish_ids}).mappings().all()
    }

    results: list[CalcItemResult] = []
    for it in items:
        v = views.get(it.dish_id)
        if v is None:
            raise BizError(code=BizCode.NOT_FOUND, message=f"菜式不存在: {it.dish_id}")
        m = macros.get(it.dish_id, {})
        oil_g = float(v["default_oil_g"] or 0)
        oil_kcal = round(oil_g * 9.0, 1)
        base_energy = float(v["energy_kcal"]) if v["energy_kcal"] is not None else None
        energy = round(base_energy + oil_kcal, 1) if base_energy is not None else None
        fat = float(m["fat_g"]) if m.get("fat_g") is not None else None
        fat_with_oil = round(fat + oil_g, 1) if fat is not None else None
        protein = float(v["protein_g"]) if v["protein_g"] is not None else None
        sodium = float(v["sodium_mg"]) if v["sodium_mg"] is not None else None
        calcium = float(v["calcium_mg"]) if v["calcium_mg"] is not None else None
        carb = float(m["carb_g"]) if m.get("carb_g") is not None else None
        fiber = float(m["fiber_g"]) if m.get("fiber_g") is not None else None
        magnesium = float(m["magnesium_mg"]) if m.get("magnesium_mg") is not None else None
        potassium = float(m["potassium_mg"]) if m.get("potassium_mg") is not None else None
        results.append(
            CalcItemResult(
                name=v["name"],
                dish_id=it.dish_id,
                servings=it.servings,
                energy_kcal=round(energy * it.servings, 1) if energy is not None else None,
                protein_g=round(protein * it.servings, 1) if protein is not None else None,
                fat_g=round(fat_with_oil * it.servings, 1) if fat_with_oil is not None else None,
                carb_g=round(carb * it.servings, 1) if carb is not None else None,
                fiber_g=round(fiber * it.servings, 1) if fiber is not None else None,
                sodium_mg=round(sodium * it.servings, 1) if sodium is not None else None,
                calcium_mg=round(calcium * it.servings, 1) if calcium is not None else None,
                magnesium_mg=round(magnesium * it.servings, 1) if magnesium is not None else None,
                potassium_mg=round(potassium * it.servings, 1) if potassium is not None else None,
                note=(
                    f"油盐按分级估算：默认油 {oil_g:g}g ×9kcal 计入能量与脂肪，默认盐 {float(v['default_salt_g'] or 0):g}g"
                    if oil_g or (v["default_salt_g"] or 0)
                    else "无额外油盐"
                ),
            )
        )
    return results


def _calc_ingredients(items: list[CalcItemInput], db: Session) -> list[CalcItemResult]:
    ids = [it.ingredient_id for it in items]
    rows = {
        r["ingredient_id"]: r
        for r in db.execute(
            text(
                "SELECT ingredient_id, name, edible_portion_pct, energy_kcal, protein_g, fat_g, "
                "carbohydrate_g, fiber_g, sodium_mg, calcium_mg, magnesium_mg, potassium_mg "
                "FROM core.ingredient WHERE ingredient_id = ANY(:ids) AND NOT is_deleted"
            ),
            {"ids": ids},
        ).mappings().all()
    }

    results: list[CalcItemResult] = []
    for it in items:
        r = rows.get(it.ingredient_id)
        if r is None:
            raise BizError(code=BizCode.NOT_FOUND, message=f"食材不存在: {it.ingredient_id}")
        factor = float(it.amount_g) / 100.0 * float(r["edible_portion_pct"] or 100) / 100.0
        results.append(
            CalcItemResult(
                name=r["name"],
                ingredient_id=it.ingredient_id,
                amount_g=it.amount_g,
                energy_kcal=round(float(r["energy_kcal"]) * factor, 1) if r["energy_kcal"] is not None else None,
                protein_g=round(float(r["protein_g"]) * factor, 1) if r["protein_g"] is not None else None,
                fat_g=round(float(r["fat_g"]) * factor, 1) if r["fat_g"] is not None else None,
                carb_g=round(float(r["carbohydrate_g"]) * factor, 1) if r["carbohydrate_g"] is not None else None,
                fiber_g=round(float(r["fiber_g"]) * factor, 1) if r["fiber_g"] is not None else None,
                sodium_mg=round(float(r["sodium_mg"]) * factor, 1) if r["sodium_mg"] is not None else None,
                calcium_mg=round(float(r["calcium_mg"]) * factor, 1) if r["calcium_mg"] is not None else None,
                magnesium_mg=round(float(r["magnesium_mg"]) * factor, 1) if r["magnesium_mg"] is not None else None,
                potassium_mg=round(float(r["potassium_mg"]) * factor, 1) if r["potassium_mg"] is not None else None,
                note=f"生重 {it.amount_g:g}g × 可食部 {float(r['edible_portion_pct'] or 100):g}%",
            )
        )
    return results


def _aggregate(results: list[CalcItemResult]) -> CalcTotal:
    keys = (
        "energy_kcal", "protein_g", "fat_g", "carb_g", "fiber_g",
        "sodium_mg", "calcium_mg", "magnesium_mg", "potassium_mg",
    )
    total = CalcTotal()
    for key in keys:
        vals = [getattr(it, key) for it in results if getattr(it, key) is not None]
        setattr(total, key, round(sum(vals), 1) if vals else None)
        complete_key = {
            "energy_kcal": "energy_complete",
            "protein_g": "protein_complete",
            "fat_g": "fat_complete",
            "carb_g": "carb_complete",
            "sodium_mg": "sodium_complete",
        }.get(key)
        if complete_key:
            setattr(total, complete_key, all(getattr(it, key) is not None for it in results))
    return total


@router.post("/nutrition")
def calc_nutrition(
    req: CalcNutritionRequest, db: Session = Depends(get_db)
) -> ApiResponse[NutritionResult]:
    """核算整餐/整日营养（菜式或食材口径，确定性计算）。"""
    if req.target_type == "dish":
        results = _calc_dishes(req.items, db)
        method = "成品（菜式 × 份量，油盐分级估算）"
    else:
        for it in req.items:
            if it.ingredient_id is None or it.amount_g is None:
                raise BizError(code=BizCode.PARAM_ERROR, message="食材口径需 ingredient_id 与 amount_g")
        results = _calc_ingredients(req.items, db)
        method = "生重（可食部换算）"

    return api_success(
        NutritionResult(
            target_type=req.target_type,
            method=method,
            total=_aggregate(results),
            by_item=results,
            source=_SOURCE,
        )
    )
