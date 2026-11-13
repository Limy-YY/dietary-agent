"""菜式搜索接口（T2/T3 / API-12）。

数据库对象：app.v_dish_live_nutrition（菜式营养+完整性）、
app.screen_dishes_for_allergens（过敏原筛查，T3）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, PageData, api_success, page_data
from app.db import get_db
from app.schemas.dishes import DishItem

router = APIRouter(prefix="/dishes", tags=["dishes"])

_VIEW_COLS = (
    "dish_id, name, tags, method_text, cooking_rule_id, servings, default_oil_g, "
    "default_salt_g, ingredient_count, energy_kcal, protein_g, sodium_mg, calcium_mg, "
    "energy_complete, protein_complete, sodium_complete, calcium_complete, "
    "strict_allergens, unverified_food_ids, allergen_verification_complete, source, source_id"
)


@router.get("/search")
def search_dishes(
    q: str | None = Query(None, description="关键词（匹配菜名）"),
    goal: str | None = Query(None, description="营养目标（预留，当前不参与过滤）"),
    exclude_allergies: str | None = Query(None, description="需排除的过敏原，逗号分隔（T3）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[DishItem]]:
    """搜索菜式（名称/标签），可按过敏原过滤（T3），返回营养与完整性。"""
    where = []
    params: dict = {}

    if q:
        where.append("(name ILIKE :q OR tags::text ILIKE :q)")
        params["q"] = f"%{q}%"

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    total = db.execute(
        text(f"SELECT count(*) AS c FROM app.v_dish_live_nutrition {where_sql}"),
        params,
    ).scalar_one()

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT {_VIEW_COLS} FROM app.v_dish_live_nutrition {where_sql} "
            f"ORDER BY dish_id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    ).mappings().all()

    items = [DishItem(**{k: r[k] for k in r.keys()}) for r in rows]

    # T3 过敏原筛查：按决策过滤并附 decision/reason
    if exclude_allergies and items:
        allergen_list = [a.strip() for a in exclude_allergies.split(",") if a.strip()]
        if allergen_list:
            decisions = db.execute(
                text("SELECT * FROM app.screen_dishes_for_allergens(:allergens)"),
                {"allergens": allergen_list},
            ).mappings().all()
            decision_map = {d["dish_id"]: d for d in decisions}
            filtered: list[DishItem] = []
            for item in items:
                d = decision_map.get(item.dish_id)
                if d is None or d["decision"] in ("strict_exclude", "exclude_until_verified"):
                    continue  # 未核查先排除，明确命中禁止推荐
                item.decision = d["decision"]
                item.reason = d["reason"]
                filtered.append(item)
            items = filtered

    return api_success(page_data(items, total=total, page=page, page_size=page_size))
