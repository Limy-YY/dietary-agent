"""方案级营养分析与报告（API-25 / API-26）。

口径（《后端接口契约 v1.2》§3.5 / §4.3）：
- 摄入取方案每个餐位「已选中候选」的 `macro_estimate / micro_estimate / oil_salt_estimate`；
- 参考值（`target`）是**每日**推荐量，因此汇总值统一按方案跨度天数折算为**日均**再比较，
  否则多日方案会被误判为大幅超标；
- 仅 7 种关键微量参与达标判断（与库内 `app.v_key_micronutrient` 一致）；
- `null ≠ 0`：某微量无数据时 `intake=null`、`status=参考提示`，不得判为不足或达标；
- 铁按普通口径（未区分经期），需在 `reference_hints` 注明；
- 同时调 `app.recent_micro_balance(user_id, start, end)` 取窗口内已固定方案的累计值做回溯判断；
  落库固定 `report_type='plan'`，并写 `app.nutrition_report_plan` 关联表。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.core.security import CurrentUser
from app.db import get_db

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

MICRO_IDS = (
    "calcium",
    "iron",
    "zinc",
    "vitamin_a",
    "vitamin_b1",
    "vitamin_b2",
    "vitamin_c",
)

# 缺口时的补位建议（按 nutrient_id）
_MICRO_ADVICE = {
    "calcium": "奶制品、豆制品、深色蔬菜",
    "iron": "红肉、动物肝脏、深色蔬菜",
    "zinc": "贝类、坚果、瘦肉",
    "vitamin_a": "动物肝脏、胡萝卜、深色蔬菜",
    "vitamin_b1": "全谷物、豆类、瘦肉",
    "vitamin_b2": "奶类、蛋类、动物内脏",
    "vitamin_c": "新鲜蔬果（青椒、猕猴桃、柑橘）",
}

_SEX_MAP = {
    "女": "female", "female": "female", "f": "female", "F": "female",
    "男": "male", "male": "male", "m": "male", "M": "male",
    "both": "both",
}


class AnalysisRequest(BaseModel):
    """API-25 入参。"""

    meal_plan_id: int
    window_days: int = Field(7, ge=3, le=30)


def _normalize_sex(raw: str | None) -> str:
    if not raw:
        return "both"
    return _SEX_MAP.get(str(raw).strip().lower(), "both")


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(v, digits: int = 1):
    return None if v is None else round(v, digits)


# ---------------------------------------------------------------- 数据装载


def _load_plan(db: Session, plan_id: int, user_id: str):
    plan = db.execute(
        text(
            "SELECT meal_plan_id, user_id, status, start_date, end_date "
            "FROM app.meal_plan WHERE meal_plan_id = :pid AND NOT is_deleted"
        ),
        {"pid": plan_id},
    ).mappings().first()
    if plan is None:
        raise BizError(BizCode.NOT_FOUND, f"方案不存在: {plan_id}", http_status=404)
    if plan["user_id"] != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权访问该方案", http_status=403)
    return plan


def _load_selected(db: Session, plan_id: int):
    return db.execute(
        text(
            "SELECT s.meal_slot_id, s.slot_date, s.meal_type, "
            "       s.selected_candidate_id, "
            "       c.macro_estimate, c.micro_estimate, c.oil_salt_estimate "
            "FROM app.meal_slot s "
            "LEFT JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id "
            "WHERE s.meal_plan_id = :pid "
            "ORDER BY s.slot_date, s.display_order"
        ),
        {"pid": plan_id},
    ).mappings().all()


def _load_reference(db: Session, user_id: str):
    profile = db.execute(
        text(
            "SELECT COALESCE(gender, sex) AS gender, age, birth_date "
            "FROM app.profile WHERE user_id = :uid"
        ),
        {"uid": user_id},
    ).mappings().first()
    if profile is None:
        raise BizError(BizCode.NOT_FOUND, f"用户档案不存在: {user_id}", http_status=404)

    age_months = None
    if profile["birth_date"] is not None:
        age_months = db.execute(
            text("SELECT app.age_in_months(:bd, CURRENT_DATE)"),
            {"bd": profile["birth_date"]},
        ).scalar()
    if age_months is None and profile["age"] is not None:
        age_months = int(profile["age"]) * 12

    refs = db.execute(
        text(
            "SELECT nutrient_id, nutrient_name, unit, reference_value, "
            "       needs_clarification, menstrual_status "
            "FROM app.match_nutrient_reference(:sex, :am, '普通', NULL)"
        ),
        {"sex": _normalize_sex(profile["gender"]), "am": age_months},
    ).mappings().all()
    return {r["nutrient_id"]: r for r in refs}


def _data_quality_check(db: Session, plan_id: int) -> tuple[int, int]:
    """返回 (近似的食材关联条数, 总关联条数)，用于 data_quality_notes。"""
    row = db.execute(
        text(
            "SELECT count(*) AS total, "
            "       count(*) FILTER (WHERE COALESCE(i.data_quality, 'official') <> 'official') AS approx "
            "FROM app.meal_slot s "
            "JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id "
            "JOIN app.meal_candidate_dish d ON d.candidate_id = c.candidate_id "
            "JOIN core.dish_ingredient di ON di.dish_id = d.dish_id "
            "JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id "
            "WHERE s.meal_plan_id = :pid AND NOT di.is_optional"
        ),
        {"pid": plan_id},
    ).mappings().first()
    if row is None:
        return 0, 0
    return int(row["approx"] or 0), int(row["total"] or 0)


# ---------------------------------------------------------------- 汇总计算


def _aggregate(db: Session, plan_id: int, days: int):
    """汇总方案自身摄入；每项指标在「全餐位都有值」时才折算日均，否则为 None。"""
    rows = _load_selected(db, plan_id)
    if not rows:
        raise BizError(
            BizCode.DATA_SOURCE_UNAVAILABLE, "方案没有餐位数据，无法分析", http_status=400
        )

    meal_count = len(rows)
    selected_meals = sum(1 for r in rows if r["selected_candidate_id"] is not None)
    if selected_meals == 0:
        raise BizError(
            BizCode.DATA_SOURCE_UNAVAILABLE, "方案没有已选中的候选，无法分析", http_status=400
        )

    kcal: list[float] = []
    protein: list[float] = []
    fat: list[float] = []
    carb: list[float] = []
    fiber: list[float] = []
    oil: list[float] = []
    salt: list[float] = []
    micro_values: dict[str, list[float]] = {k: [] for k in MICRO_IDS}
    micro_count: dict[str, int] = {k: 0 for k in MICRO_IDS}
    meals_with_micro = 0

    for r in rows:
        if r["selected_candidate_id"] is None:
            continue
        macro = r["macro_estimate"] if isinstance(r["macro_estimate"], dict) else {}
        micro = r["micro_estimate"] if isinstance(r["micro_estimate"], dict) else {}
        os_est = r["oil_salt_estimate"] if isinstance(r["oil_salt_estimate"], dict) else {}

        for key, bucket in (
            ("kcal", kcal),
            ("protein_g", protein),
            ("fat_g", fat),
            ("carb_g", carb),
            ("fiber_g", fiber),
        ):
            v = _num(macro.get(key))
            if v is not None:
                bucket.append(v)
        ov = _num(os_est.get("oil_g"))
        if ov is not None:
            oil.append(ov)
        sv = _num(os_est.get("salt_g"))
        if sv is not None:
            salt.append(sv)

        has_micro = False
        for k in MICRO_IDS:
            v = _num(micro.get(k))
            if v is not None:
                micro_values[k].append(v)
                micro_count[k] += 1
                has_micro = True
        if has_micro:
            meals_with_micro += 1

    def _daily(values: list[float], digits: int) -> float | None:
        # 任一餐位缺该指标时不做「缺值当 0」的合计，直接返回 None（null ≠ 0）
        if not values or len(values) < selected_meals or days <= 0:
            return None
        return round(sum(values) / days, digits)

    return {
        "days": days,
        "meal_count": meal_count,
        "selected_meals": selected_meals,
        "known_meal_count": meals_with_micro,
        "missing_meal_count": meal_count - meals_with_micro,
        "energy_kcal": _daily(kcal, 1),
        "protein_g": _daily(protein, 1),
        "fat_g": _daily(fat, 1),
        "carb_g": _daily(carb, 1),
        "fiber_g": _daily(fiber, 1),
        "oil_g": _daily(oil, 1),
        "salt_g": _daily(salt, 1),
        "micro_daily": {
            k: (round(sum(micro_values[k]) / days, 2) if micro_count[k] else None)
            for k in MICRO_IDS
        },
        "micro_count": micro_count,
    }


def _macro_summary(agg: dict) -> dict:
    energy = agg["energy_kcal"]
    protein = agg["protein_g"]
    fat = agg["fat_g"]
    carb = agg["carb_g"]
    if energy and protein is not None and fat is not None and carb is not None:
        protein_pct = protein * 4.0 / energy * 100
        fat_pct = fat * 9.0 / energy * 100
        carb_pct = carb * 4.0 / energy * 100
    else:
        protein_pct = fat_pct = carb_pct = None
    return {
        "energy_kcal": _r(energy, 1),
        "protein_pct": _r(protein_pct, 1),
        "fat_pct": _r(fat_pct, 1),
        "carb_pct": _r(carb_pct, 1),
        "oil_g": _r(agg["oil_g"], 1),
        "salt_g": _r(agg["salt_g"], 1),
        "fiber_g": _r(agg["fiber_g"], 1),
    }


def _micro_summary(agg: dict, refs: dict, selected_meals: int) -> tuple[dict, list[str]]:
    """返回 (key_micro_summary, 不足项清单)。intake 为日均值，target 为每日参考量。"""
    summary: dict[str, dict] = {}
    shortfall: list[str] = []

    for k in MICRO_IDS:
        ref = refs.get(k) or {}
        target = _num(ref.get("reference_value"))
        intake = agg["micro_daily"][k]

        gap = None
        covered = None
        if intake is not None and target:
            gap = round(intake - target, 2)
            covered = round(intake / target * 100, 1)

        if intake is None or target is None:
            status = "参考提示"
        elif agg["micro_count"][k] < selected_meals:
            # 部分餐次缺该微量数据，不硬性判达标/不足
            status = "参考提示"
        elif covered >= 100:
            status = "达标"
        else:
            status = "不足"
            shortfall.append(k)

        summary[k] = {
            "name_zh": ref.get("nutrient_name") or k,
            "unit": ref.get("unit"),
            "target": _r(target, 2),
            "intake": intake,
            "gap": gap,
            "covered_pct": covered,
            "status": status,
        }
    return summary, shortfall


def _rebuild_hints(
    db: Session,
    user_id: str,
    plan,
    window_days: int,
    micro: dict,
    meals_per_day: float,
) -> list[str]:
    """回溯判断：窗口内已固定方案的累计摄入（`app.recent_micro_balance`）。

    窗口里只有部分日期有已固定方案，直接按 `window_days` 折算会低估日均，
    因此按「覆盖餐数 ÷ 每日餐数」折算成实际有数据的天数。
    """
    window_start = plan["start_date"] - timedelta(days=window_days - 1)
    rows = db.execute(
        text(
            "SELECT nutrient_id, nutrient_name, unit, total_value, "
            "       selected_meal_count, known_meal_count, missing_meal_count "
            "FROM app.recent_micro_balance(:uid, :ws, :we)"
        ),
        {"uid": user_id, "ws": window_start, "we": plan["end_date"]},
    ).mappings().all()

    hints: list[str] = []
    for r in rows:
        if int(r["selected_meal_count"] or 0) == 0:
            continue
        item = micro.get(r["nutrient_id"]) or {}
        target = _num(item.get("target"))
        total = _num(r["total_value"])
        if target is None or total is None or total <= 0:
            continue
        covered_days = (
            int(r["selected_meal_count"]) / meals_per_day if meals_per_day > 0 else window_days
        )
        daily = total / covered_days if covered_days > 0 else total
        remain = round(target - daily, 2)
        if remain > 0:
            hints.append(
                f"近 {window_days} 天窗口内已固定方案对{item.get('name_zh') or r['nutrient_name']}"
                f"日均约 {round(daily, 1)}{item.get('unit') or ''}（覆盖 "
                f"{int(r['selected_meal_count'])} 餐），距每日目标仍差 {remain}{item.get('unit') or ''}"
            )
    return hints


def _serialize_report(row) -> dict:
    def _j(v, default):
        if isinstance(v, (list, dict)):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return default
        return default

    return {
        "nutrition_report_id": row["nutrition_report_id"],
        "user_id": row["user_id"],
        "report_type": row["report_type"],
        "period_start": str(row["period_start"]),
        "period_end": str(row["period_end"]),
        "meal_plan_id": row["meal_plan_id"],
        "window_days": (row["summary"] or {}).get("window_days")
        if isinstance(row["summary"], dict)
        else None,
        "macro_summary": _j(row["macro_summary"], {}),
        "key_micro_summary": _j(row["key_micro_summary"], {}),
        "summary": _j(row["summary"], {}),
        "completeness": _j(row["completeness"], {}),
        "sources": _j(row["sources"], []),
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
    }


# ---------------------------------------------------------------- API-25


@router.post("/analysis")
def analyze_plan(
    req: AnalysisRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """生成方案级营养报告（API-25），落库并返回 nutrition_report_id。"""
    plan = _load_plan(db, req.meal_plan_id, user_id)
    days = (plan["end_date"] - plan["start_date"]).days + 1
    agg = _aggregate(db, req.meal_plan_id, days)
    refs = _load_reference(db, user_id)

    macro = _macro_summary(agg)
    micro, shortfall = _micro_summary(agg, refs, agg["selected_meals"])

    hints: list[str] = [
        f"以下为日均口径：方案 {days} 天（{plan['start_date']}~{plan['end_date']}）摄入按天数折算后"
        f"与每日参考量比较"
    ]
    if shortfall:
        names = "、".join(micro[k]["name_zh"] for k in shortfall)
        advices = "，".join(
            f"{micro[k]['name_zh']}补{_MICRO_ADVICE.get(k, '相关食材')}" for k in shortfall
        )
        hints.append(f"{names}距每日目标仍有缺口，建议下一次方案增加：{advices}")
    hints.append("铁按普通口径计算，未区分经期（本期口径）")
    if any(v.get("status") == "参考提示" for v in micro.values()):
        hints.append("部分微量存在数据缺口或不宜硬性补足，按参考提示处理，不作达标结论")
    hints.extend(
        _rebuild_hints(
            db, user_id, plan, req.window_days, micro, agg["meal_count"] / max(days, 1)
        )
    )

    approx, total = _data_quality_check(db, req.meal_plan_id)
    quality_notes = []
    if total and approx:
        quality_notes.append(
            f"{approx}/{total} 条食材营养为近似值（approx/check），不作为官方实测结论"
        )
    if agg["missing_meal_count"] > 0:
        quality_notes.append(
            f"{agg['meal_count']} 个餐位中 {agg['missing_meal_count']} 个缺微量数据，已按参考提示处理"
        )
    if macro["energy_kcal"] is None or macro["fiber_g"] is None:
        quality_notes.append("部分宏量（能量或膳食纤维）存在缺值，聚合项返回 null，不当 0 处理")

    summary = {
        "reference_hints": hints,
        "data_quality_notes": quality_notes,
        "window_days": req.window_days,
        "basis": "daily_average",
    }
    completeness = {
        "meal_count": agg["meal_count"],
        "known_meal_count": agg["known_meal_count"],
        "missing_meal_count": agg["missing_meal_count"],
    }
    sources = [{"type": "nutrient_reference", "version": "v1.2r1"}]

    report_id = db.execute(
        text(
            "INSERT INTO app.nutrition_report "
            "(user_id, report_type, period_start, period_end, meal_plan_id, "
            " summary, macro_summary, key_micro_summary, completeness, sources, agent_version) "
            "VALUES (:uid, 'plan', :ps, :pe, :pid, "
            "        CAST(:summary AS jsonb), CAST(:macro AS jsonb), CAST(:micro AS jsonb), "
            "        CAST(:completeness AS jsonb), CAST(:sources AS jsonb), :ver) "
            "RETURNING nutrition_report_id"
        ),
        {
            "uid": user_id,
            "ps": plan["start_date"],
            "pe": plan["end_date"],
            "pid": req.meal_plan_id,
            "summary": json.dumps(summary, ensure_ascii=False),
            "macro": json.dumps(macro, ensure_ascii=False),
            "micro": json.dumps(micro, ensure_ascii=False),
            "completeness": json.dumps(completeness, ensure_ascii=False),
            "sources": json.dumps(sources, ensure_ascii=False),
            "ver": "backend-v1.2",
        },
    ).scalar_one()

    db.execute(
        text(
            "INSERT INTO app.nutrition_report_plan (nutrition_report_id, meal_plan_id) "
            "VALUES (:rid, :pid)"
        ),
        {"rid": report_id, "pid": req.meal_plan_id},
    )
    db.commit()

    row = db.execute(
        text(
            "SELECT nutrition_report_id, user_id, report_type, period_start, period_end, "
            "       meal_plan_id, summary, macro_summary, key_micro_summary, completeness, "
            "       sources, generated_at "
            "FROM app.nutrition_report WHERE nutrition_report_id = :rid"
        ),
        {"rid": report_id},
    ).mappings().first()

    return api_success(_serialize_report(row))


# ---------------------------------------------------------------- API-26


@router.get("/report")
def get_plan_report(
    meal_plan_id: int = Query(...),
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """读取已落库的方案营养报告（API-26）：未分析过返回 404/1004。"""
    plan = _load_plan(db, meal_plan_id, user_id)
    row = db.execute(
        text(
            "SELECT nutrition_report_id, user_id, report_type, period_start, period_end, "
            "       meal_plan_id, summary, macro_summary, key_micro_summary, completeness, "
            "       sources, generated_at "
            "FROM app.nutrition_report "
            "WHERE meal_plan_id = :pid AND report_type = 'plan' "
            "ORDER BY generated_at DESC, nutrition_report_id DESC LIMIT 1"
        ),
        {"pid": plan["meal_plan_id"]},
    ).mappings().first()
    if row is None:
        raise BizError(
            BizCode.NOT_FOUND,
            f"方案 {meal_plan_id} 尚无营养报告（请先调用 /nutrition/analysis）",
            http_status=404,
        )
    return api_success(_serialize_report(row))
