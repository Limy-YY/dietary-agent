"""食材清单接口（API-27）。

清单在 `fix` 时由 mealplan 侧生成并写入 `app.shopping_list`（一方案一清单，
`meal_plan_id` 唯一），本接口只负责读取与按 `category` 聚合展示分组。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.core.security import CurrentUser
from app.db import get_db

router = APIRouter(prefix="/shopping-list", tags=["shopping"])


@router.get("")
def get_shopping_list(
    meal_plan_id: int = Query(...),
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """取方案食材清单（API-27）：仅 fixed 方案可取，未固定返回 2005。"""
    plan = db.execute(
        text(
            "SELECT meal_plan_id, user_id, status FROM app.meal_plan "
            "WHERE meal_plan_id = :pid AND NOT is_deleted"
        ),
        {"pid": meal_plan_id},
    ).mappings().first()
    if plan is None:
        raise BizError(BizCode.NOT_FOUND, f"方案不存在: {meal_plan_id}", http_status=404)
    if plan["user_id"] != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权访问该方案", http_status=403)
    if plan["status"] != "fixed":
        raise BizError(
            BizCode.PLAN_STATE_CONFLICT,
            f"方案状态为 {plan['status']}，未固定不可取食材清单（请先确认方案）",
            http_status=400,
        )

    row = db.execute(
        text(
            "SELECT shopping_list_id, meal_plan_id, items, generated_at "
            "FROM app.shopping_list WHERE meal_plan_id = :pid"
        ),
        {"pid": meal_plan_id},
    ).mappings().first()
    if row is None:
        raise BizError(
            BizCode.NOT_FOUND, f"方案 {meal_plan_id} 尚未生成食材清单", http_status=404
        )

    items = row["items"] if isinstance(row["items"], list) else []
    groups: dict[str, list[dict]] = {}
    for it in items:
        category = (it.get("category") or "未分类") if isinstance(it, dict) else "未分类"
        if not isinstance(it, dict):
            continue
        groups.setdefault(category, []).append(
            {
                "ingredient_id": it.get("ingredient_id"),
                "name": it.get("name"),
                "estimated_quantity": it.get("estimated_quantity"),
                "unit": it.get("unit") or "g",
            }
        )

    return api_success(
        {
            "shopping_list_id": row["shopping_list_id"],
            "meal_plan_id": row["meal_plan_id"],
            "total_items": len(items),
            "groups": [
                {"category": k, "items": v} for k, v in sorted(groups.items())
            ],
            "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        }
    )
