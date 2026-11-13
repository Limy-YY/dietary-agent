"""膳食方案接口（API-03/04/05/06）。

meal-plan/generate 与 /weekly 为确定性配餐骨架：
- 硬约束：档案过敏原 → screen_dishes_for_allergens 过滤（strict_exclude / exclude_until_verified 剔除）
- 选菜：蛋白质来源优先、能量贪心凑近目标（±20%），份量 1
- 营养：与 T11 同口径（视图配料值 + 油盐分级估算）
- 生成逻辑与 Agent 岗联动，正式版本由 Agent 工作流生成后经本接口落库
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, PageData, api_success, page_data
from app.db import get_db

router = APIRouter(prefix="/meal-plan", tags=["meal-plan"])

_DISH_VIEW = (
    "dish_id, name, energy_kcal, protein_g, sodium_mg, default_oil_g, default_salt_g, tags"
)


class GenerateRequest(BaseModel):
    user_id: str
    plan_date: date
    override: dict | None = None


class WeeklyRequest(BaseModel):
    user_id: str
    week_start: date
    goal_energy_kcal: float | None = None
    hard_constraints: dict | None = None


def _goal_energy(db: Session, user_id: str, override: dict | None) -> float:
    if override and override.get("goal_energy_kcal"):
        return float(override["goal_energy_kcal"])
    row = db.execute(
        text("SELECT sex, age, height_cm, weight_kg, activity_level, goal FROM app.profile WHERE user_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    if row is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"用户档案不存在: {user_id}")
    # Mifflin-St Jeor 估算基础代谢 + PAL 系数（确定性，可复算）
    sex_factor = -161 if row["sex"] == "女" else 5
    weight = float(row["weight_kg"] or 60)
    height = float(row["height_cm"] or 165)
    age = int(row["age"] or 20)
    bmr = 10 * weight + 6.25 * height - 5 * age + sex_factor
    pal = {"久坐": 1.2, "轻度": 1.375, "中度": 1.55, "重度": 1.725}.get(row["activity_level"], 1.4)
    return round(bmr * pal, 1)


def _select_dishes(db: Session, user_id: str, goal: float) -> list[dict]:
    rows = db.execute(
        text(
            f"SELECT {_DISH_VIEW} FROM app.v_dish_live_nutrition ORDER BY dish_id"
        )
    ).mappings().all()

    # 过敏原过滤（档案硬约束）
    profile = db.execute(
        text("SELECT allergies FROM app.profile WHERE user_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    if profile is not None and profile["allergies"]:
        decisions = db.execute(
            text("SELECT * FROM app.screen_dishes_for_allergens(:allergens)"),
            {"allergens": list(profile["allergies"])},
        ).mappings().all()
        exclude = {d["dish_id"] for d in decisions if d["decision"] in ("strict_exclude", "exclude_until_verified")}
        rows = [r for r in rows if r["dish_id"] not in exclude]

    if not rows:
        raise BizError(code=BizCode.CALC_FAILED, message="候选菜式为空（过敏原过滤后无可用菜式）")

    # 贪心选菜：蛋白质来源优先，能量不超过目标 120%
    protein_first = [r for r in rows if "蛋白质来源" in (r["tags"] or [])]
    others = [r for r in rows if r not in protein_first]
    ordered = protein_first + others
    chosen: list[dict] = []
    total = 0.0
    for r in ordered:
        energy = float(r["energy_kcal"] or 0) + float(r["default_oil_g"] or 0) * 9.0
        if total + energy > goal * 1.2 and chosen:
            continue
        chosen.append(
            {
                "dish_id": r["dish_id"],
                "name": r["name"],
                "servings": 1,
                "energy_kcal": round(energy, 1),
                "protein_g": float(r["protein_g"]) if r["protein_g"] is not None else None,
                "default_oil_g": float(r["default_oil_g"] or 0),
                "default_salt_g": float(r["default_salt_g"] or 0),
            }
        )
        total += energy
        # 一餐最多 4 道菜；能量达到目标 80% 后停止
        if len(chosen) >= 4 and total >= goal * 0.8:
            break
    return chosen


def _build_meals_json(chosen: list[dict], goal: float) -> dict:
    total_energy = round(sum(i["energy_kcal"] for i in chosen), 1)
    total_protein = round(sum(i["protein_g"] for i in chosen if i["protein_g"] is not None), 1)
    return {
        "items": chosen,
        "total": {"energy_kcal": total_energy, "protein_g": total_protein},
        "goal_energy_kcal": goal,
        "note": "确定性配餐骨架：蛋白质来源优先 + 能量贪心；油盐按分级估算；正式版由 Agent 工作流生成",
    }


@router.post("/generate")
def generate_plan(
    req: GenerateRequest, db: Session = Depends(get_db)
) -> ApiResponse[dict]:
    """生成一日膳食方案（API-03，确定性骨架并落库）。"""
    goal = _goal_energy(db, req.user_id, req.override)
    chosen = _select_dishes(db, req.user_id, goal)
    meals = _build_meals_json(chosen, goal)
    plan_id = db.execute(
        text(
            "INSERT INTO app.meal_plan (user_id, plan_type, plan_date, goal_energy_kcal, "
            "macro_ratio, meals, sources) "
            "VALUES (:uid, '日', :d, :goal, '{}'::jsonb, cast(:meals AS jsonb), '[]'::jsonb) "
            "RETURNING meal_plan_id"
        ),
        {"uid": req.user_id, "d": req.plan_date, "goal": goal, "meals": __import__("json").dumps(meals)},
    ).scalar_one()
    db.commit()
    return api_success({"plan_id": plan_id, **meals})


@router.post("/weekly")
def generate_weekly(
    req: WeeklyRequest, db: Session = Depends(get_db)
) -> ApiResponse[dict]:
    """生成一周完整食谱（API-06，确定性骨架，7 天落库）。"""
    goal = req.goal_energy_kcal or _goal_energy(db, req.user_id, req.hard_constraints)
    plan_ids = []
    for i in range(7):
        day = req.week_start + timedelta(days=i)
        chosen = _select_dishes(db, req.user_id, goal)
        meals = _build_meals_json(chosen, goal)
        pid = db.execute(
            text(
                "INSERT INTO app.meal_plan (user_id, plan_type, plan_date, goal_energy_kcal, "
                "macro_ratio, meals, sources) "
                "VALUES (:uid, '周', :d, :goal, '{}'::jsonb, cast(:meals AS jsonb), '[]'::jsonb) "
                "RETURNING meal_plan_id"
            ),
            {"uid": req.user_id, "d": day, "goal": goal, "meals": __import__("json").dumps(meals)},
        ).scalar_one()
        plan_ids.append(pid)
    db.commit()
    return api_success({"plan_ids": plan_ids, "goal_energy_kcal": goal, "days": 7})


@router.get("/list")
def list_plans(
    user_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[dict]]:
    """获取历史膳食方案列表（API-05，摘要）。"""
    total = db.execute(
        text("SELECT count(*) FROM app.meal_plan WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar_one()
    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            "SELECT meal_plan_id, plan_type, plan_date, goal_energy_kcal "
            "FROM app.meal_plan WHERE user_id = :uid "
            "ORDER BY plan_date DESC, meal_plan_id DESC LIMIT :limit OFFSET :offset"
        ),
        {"uid": user_id, "limit": page_size, "offset": offset},
    ).mappings().all()
    items = [{k: r[k] for k in r.keys()} for r in rows]
    return api_success(page_data(items, total=total, page=page, page_size=page_size))


@router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)) -> ApiResponse[dict]:
    """获取单份历史膳食方案（API-04）。"""
    row = db.execute(
        text(
            "SELECT meal_plan_id, user_id, plan_type, plan_date, goal_energy_kcal, "
            "macro_ratio, meals, sources, created_at "
            "FROM app.meal_plan WHERE meal_plan_id = :pid"
        ),
        {"pid": plan_id},
    ).mappings().first()
    if row is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"方案不存在: {plan_id}")
    return api_success({k: row[k] for k in row.keys()})
