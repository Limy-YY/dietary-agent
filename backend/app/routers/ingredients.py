"""食材搜索接口（T1 / API-11）。

数据库对象：app.search_ingredients（名称/别名匹配）、app.v_ingredient_search（营养明细补全）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, PageData, api_success, page_data
from app.db import get_db
from app.schemas.ingredients import IngredientItem

router = APIRouter(prefix="/ingredients", tags=["ingredients"])

_FUNC_COLS = (
    "food_id, name, aliases, category, state, energy_kcal, protein_g, fat_g, "
    "carbohydrate_g, allergens, allergen_status, match_type, "
    "purine_level, sfa_g, iodine_ug, data_quality, source_note"
)
_VIEW_COLS = (
    "food_id, edible_portion_pct, fiber_g, sodium_mg, potassium_mg, calcium_mg, "
    "magnesium_mg, purine_level, source_url, has_missing_macro"
)


def _row_to_dict(row) -> dict:
    """把 SQLAlchemy 行转 dict（兼容函数/视图两种列集）。"""
    return {key: value for key, value in row._mapping.items()}


@router.get("/search")
def search_ingredients(
    q: str = Query(..., description="查询词，匹配名称与别名"),
    limit: int = Query(20, ge=1, le=100, description="返回条数，默认 20，最大 100"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[IngredientItem]]:
    """按名称/别名搜索食材，并补全营养明细（v_ingredient_search）。"""
    rows = db.execute(
        text(f"SELECT {_FUNC_COLS} FROM app.search_ingredients(:q, :limit)"),
        {"q": q, "limit": limit},
    ).mappings().all()

    items: list[IngredientItem] = []
    if rows:
        food_ids = [r["food_id"] for r in rows]
        details = {
            r["food_id"]: r
            for r in db.execute(
                text(f"SELECT {_VIEW_COLS} FROM app.v_ingredient_search WHERE food_id = ANY(:ids)"),
                {"ids": food_ids},
            ).mappings().all()
        }
        for r in rows:
            item = IngredientItem(**{k: r[k] for k in r.keys()})
            extra = details.get(r["food_id"])
            if extra:
                for key in extra.keys():
                    setattr(item, key, extra[key])
            items.append(item)

    return api_success(page_data(items, total=len(items), page=1, page_size=limit))
