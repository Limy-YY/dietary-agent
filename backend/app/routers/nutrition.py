"""方案级营养分析与报告（API-25 / API-26）。

口径（《后端接口契约 v1.2》§3.5 / §4.3）：
- 摄入取方案每个餐位「已选中候选」的 `macro_estimate / micro_estimate / oil_salt_estimate`；
- 参考值（`target`）是**每日**推荐量，因此汇总值统一按方案跨度天数折算为**日均**再比较，
  否则多日方案会被误判为大幅超标；
- 仅 7 种关键微量参与达标判断（与库内 `app.v_key_micronutrient` 一致）；
- `null ≠ 0`：某微量无数据时 `intake=null`、`status=参考提示`，不得判为不足或达标；
- `daily_trend` 给按 `slot_date` 分天的实际摄入序列（当日合计，不折日均），供报告页画趋势条；
  某天该指标有餐位缺值时同样为 `null`，`status` 按当日能量对目标能量的偏离判 `ok / over / low`；
- `achievement` 给达标率：7 项关键微量按「达标天数 ÷ 有效天数」算百分比，
  宏量按供能比是否落在合理区间判；有效天数为 0 时百分比为 `null`（不按 0% 论）；
- 铁按普通口径（未区分经期），需在 `reference_hints` 注明；
- `summary.reference_hints` 只放「口径/溯源说明」，`summary.insights` 放「结论/洞察」
  （缺口、超标、回溯补位、达标天数偏少），前端分两处渲染避免重复；
  达标率数值改由 `summary.achievement.micro_overall_pct` 在报告微区块头部呈现；
- 同时调 `app.recent_micro_balance(user_id, start, end)` 取窗口内已固定方案的累计值做回溯判断；
  落库固定 `report_type='plan'`，并写 `app.nutrition_report_plan` 关联表。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

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


class PeriodAnalysisRequest(BaseModel):
    """API-25b 入参：周/月/自定义维度跨方案报告。"""

    report_type: str
    window_days: int | None = Field(None, ge=1, le=366)
    period_start: date | None = None
    period_end: date | None = None


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
            "SELECT meal_plan_id, user_id, status, start_date, end_date, goal_energy_kcal "
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


def _load_selected_window(db: Session, user_id: str, start: date, end: date):
    """窗口内所有已固定方案的餐位 + 已选候选（跨方案，供周/月报告聚合）。

    去重口径：同一餐位 (slot_date, meal_type, display_order) 若被多份已固定方案
    覆盖，只取 fixed_at 最新的一份，避免用户在同一时间段重复确认/固定导致报告重复累计。
    """
    return db.execute(
        text(
            "SELECT DISTINCT ON (s.slot_date, s.meal_type, s.display_order) "
            "       s.meal_slot_id, s.slot_date, s.meal_type, "
            "       s.selected_candidate_id, "
            "       c.macro_estimate, c.micro_estimate, c.oil_salt_estimate "
            "FROM app.meal_slot s "
            "JOIN app.meal_plan p ON p.meal_plan_id = s.meal_plan_id AND NOT p.is_deleted "
            "LEFT JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id "
            "WHERE p.user_id = :uid AND p.status = 'fixed' "
            "  AND s.slot_date BETWEEN :ws AND :we "
            "ORDER BY s.slot_date, s.meal_type, s.display_order, "
            "         p.fixed_at DESC NULLS LAST, s.meal_slot_id DESC"
        ),
        {"uid": user_id, "ws": start, "we": end},
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


def _load_target_kcal(db: Session, user_id: str) -> float | None:
    """读用户能量目标（target_calories = BMR × 1.4），用于周/月趋势的偏离判定。"""
    return db.execute(
        text("SELECT target_calories FROM app.profile WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar()


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


def _data_quality_check_window(db: Session, user_id: str, start: date, end: date) -> tuple[int, int]:
    """窗口内近似食材关联条数统计，用于周/月报告的 data_quality_notes。"""
    row = db.execute(
        text(
            "SELECT count(*) AS total, "
            "       count(*) FILTER (WHERE COALESCE(i.data_quality, 'official') <> 'official') AS approx "
            "FROM app.meal_plan p "
            "JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id "
            "JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id "
            "JOIN app.meal_candidate_dish d ON d.candidate_id = c.candidate_id "
            "JOIN core.dish_ingredient di ON di.dish_id = d.dish_id "
            "JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id "
            "WHERE p.user_id = :uid AND p.status = 'fixed' "
            "  AND s.slot_date BETWEEN :ws AND :we AND NOT di.is_optional"
        ),
        {"uid": user_id, "ws": start, "we": end},
    ).mappings().first()
    if row is None:
        return 0, 0
    return int(row["approx"] or 0), int(row["total"] or 0)


def _window_plan_stats(db: Session, user_id: str, start: date, end: date) -> dict:
    """窗口内「已固定方案」数与「已标记执行」数，供报告标注覆盖口径。"""
    row = db.execute(
        text(
            "SELECT count(DISTINCT p.meal_plan_id) AS total, "
            "       count(DISTINCT p.meal_plan_id) FILTER (WHERE p.is_executed) AS executed "
            "FROM app.meal_plan p "
            "JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id "
            "WHERE p.user_id = :uid AND p.status = 'fixed' AND NOT p.is_deleted "
            "  AND s.slot_date BETWEEN :ws AND :we"
        ),
        {"uid": user_id, "ws": start, "we": end},
    ).mappings().first()
    return {
        "total_plans": int(row["total"] or 0) if row else 0,
        "executed_plans": int(row["executed"] or 0) if row else 0,
    }


# ---------------------------------------------------------------- 汇总计算


def _aggregate(db: Session, plan_id: int, days: int):
    """汇总单个方案；跨方案窗口聚合复用 `_aggregate_rows`。"""
    return _aggregate_rows(_load_selected(db, plan_id), days, "方案")


def _aggregate_rows(rows: list[dict], days: int, subject: str = "窗口") -> dict:
    """汇总餐位行序列；每项指标在「全餐位都有值」时才折算日均，否则为 None（null ≠ 0）。"""
    if not rows:
        raise BizError(
            BizCode.DATA_SOURCE_UNAVAILABLE, f"{subject}没有餐位数据，无法分析", http_status=400
        )

    meal_count = len(rows)
    selected_meals = sum(1 for r in rows if r["selected_candidate_id"] is not None)
    if selected_meals == 0:
        raise BizError(
            BizCode.DATA_SOURCE_UNAVAILABLE, f"{subject}没有已选中的候选，无法分析", http_status=400
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

    by_date: dict[str, dict] = {}

    def _bump(drow: dict, key: str, value: float) -> None:
        drow["sum"][key] = drow["sum"].get(key, 0.0) + value
        drow["count"][key] = drow["count"].get(key, 0) + 1

    for r in rows:
        # 按天分组的原始累计，供 daily_trend 使用（口径同日均：缺值不补 0）
        drow = by_date.setdefault(
            str(r["slot_date"]),
            {"sum": {}, "count": {}, "meals": 0, "selected": 0, "micro_meals": 0},
        )
        drow["meals"] += 1
        if r["selected_candidate_id"] is None:
            continue
        drow["selected"] += 1
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
                _bump(drow, key, v)
        ov = _num(os_est.get("oil_g"))
        if ov is not None:
            oil.append(ov)
            _bump(drow, "oil_g", ov)
        sv = _num(os_est.get("salt_g"))
        if sv is not None:
            salt.append(sv)
            _bump(drow, "salt_g", sv)

        has_micro = False
        for k in MICRO_IDS:
            v = _num(micro.get(k))
            if v is not None:
                micro_values[k].append(v)
                micro_count[k] += 1
                has_micro = True
                _bump(drow, "m:" + k, v)
        if has_micro:
            meals_with_micro += 1
            drow["micro_meals"] += 1

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
        # 内部结构（不对外）：按 slot_date 的原始累计，仅供 daily_trend / achievement 使用
        "_by_date": by_date,
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
        covered_meals = int(agg["micro_count"].get(k, 0) or 0)

        gap = None
        covered = None
        if intake is not None and target:
            gap = round(intake - target, 2)
            covered = round(intake / target * 100, 1)

        if intake is None or target is None:
            status = "参考提示"
        elif covered_meals < selected_meals:
            # 部分餐次缺该微量数据，不硬性判达标/不足
            status = "参考提示"
        elif covered > 100:
            status = "超标"
        elif covered >= 80:
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
            "covered_meals": covered_meals,
            "selected_meals": selected_meals,
            "coverage": round(covered_meals / selected_meals, 2) if selected_meals else None,
            "status": status,
        }
    return summary, shortfall


# 宏量供能比的合理区间（%），用于 achievement.macro 的区间判定
_MACRO_ENERGY_RANGE = {
    "protein_pct": (15.0, 25.0),
    "carb_pct": (45.0, 65.0),
    "fat_pct": (20.0, 30.0),
}


def _daily_value(drow: dict, key: str, digits: int = 1):
    """某天某指标的合计：该天全部选中餐位都有值时才算数，否则 None（缺值不补 0）。"""
    if drow["selected"] <= 0 or drow["count"].get(key, 0) < drow["selected"]:
        return None
    return round(drow["sum"][key], digits)


def _daily_trend(agg: dict, target_kcal) -> list[dict]:
    """按天序列（当日合计，不折日均）。status 依据当日能量对目标能量的偏离。"""
    target = _num(target_kcal)
    trend: list[dict] = []
    for d in sorted(agg["_by_date"]):
        drow = agg["_by_date"][d]
        calories = _daily_value(drow, "kcal", 1)
        if calories is None or not target:
            status = "参考提示"
        elif calories > target * 1.15:
            status = "over"
        elif calories < target * 0.6:
            status = "low"
        else:
            status = "ok"
        trend.append(
            {
                "date": d,
                "label": d[5:],
                "calories": calories,
                "protein_g": _daily_value(drow, "protein_g", 1),
                "fat_g": _daily_value(drow, "fat_g", 1),
                "carb_g": _daily_value(drow, "carb_g", 1),
                "fiber_g": _daily_value(drow, "fiber_g", 1),
                "oil_g": _daily_value(drow, "oil_g", 1),
                "salt_g": _daily_value(drow, "salt_g", 1),
                "micro": {k: _daily_value(drow, "m:" + k, 2) for k in MICRO_IDS},
                "meal_count": drow["meals"],
                "known_meal_count": drow["micro_meals"],
                "status": status,
            }
        )
    return trend


def _achievement(agg: dict, refs: dict, macro: dict) -> dict:
    """达标率：微量按「达标天数 ÷ 有效天数」，宏量按供能比是否落在合理区间。

    有效天数只统计当天该微量有值的日子；有效天数为 0 时百分比为 null（不按 0% 论）。
    """
    micro: dict[str, dict] = {}
    pct_list: list[float] = []

    for k in MICRO_IDS:
        ref = refs.get(k) or {}
        target = _num(ref.get("reference_value"))
        valid_days = 0
        achieved_days = 0
        for drow in agg["_by_date"].values():
            v = _daily_value(drow, "m:" + k, 2)
            if v is None or not target:
                continue
            valid_days += 1
            if v >= target:
                achieved_days += 1
        pct = round(achieved_days / valid_days * 100, 1) if valid_days else None
        if pct is None:
            level = "unknown"
        elif pct >= 80:
            level = "ok"
        elif pct >= 50:
            level = "warn"
        else:
            level = "danger"
        if pct is not None:
            pct_list.append(pct)
        micro[k] = {
            "name_zh": ref.get("nutrient_name") or k,
            "unit": ref.get("unit"),
            "target": _r(target, 2),
            "valid_days": valid_days,
            "achieved_days": achieved_days,
            "achieved_pct": pct,
            "level": level,
        }

    macro_items: dict[str, dict] = {}
    for key, (lo, hi) in _MACRO_ENERGY_RANGE.items():
        value = macro.get(key)
        if value is None:
            level = "unknown"
        elif lo <= value <= hi:
            level = "ok"
        else:
            level = "warn"
        macro_items[key] = {"value_pct": value, "range": [lo, hi], "level": level}

    return {
        "micro": micro,
        "micro_overall_pct": round(sum(pct_list) / len(pct_list), 1) if pct_list else None,
        "macro": macro_items,
    }


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

    summary = _j(row["summary"], {})
    return {
        "nutrition_report_id": row["nutrition_report_id"],
        "user_id": row["user_id"],
        "report_type": row["report_type"],
        "period_start": str(row["period_start"]),
        "period_end": str(row["period_end"]),
        "meal_plan_id": row["meal_plan_id"],
        "window_days": (summary or {}).get("window_days"),
        "macro_summary": _j(row["macro_summary"], {}),
        "key_micro_summary": _j(row["key_micro_summary"], {}),
        "summary": summary,
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

    reference_hints: list[str] = [
        f"以下为日均口径：方案 {days} 天（{plan['start_date']}~{plan['end_date']}）摄入按天数折算后"
        f"与每日参考量比较"
    ]
    reference_hints.append("铁按普通口径计算，未区分经期（本期口径）")
    if any(v.get("status") == "参考提示" for v in micro.values()):
        reference_hints.append(
            "部分微量存在数据缺口或不宜硬性补足，按参考提示处理，不作达标结论"
        )

    insights: list[str] = []
    if shortfall:
        names = "、".join(micro[k]["name_zh"] for k in shortfall)
        advices = "，".join(
            f"{micro[k]['name_zh']}补{_MICRO_ADVICE.get(k, '相关食材')}" for k in shortfall
        )
        insights.append(f"{names}距每日目标仍有缺口，建议下一次方案增加：{advices}")
    over = [k for k in MICRO_IDS if micro[k].get("status") == "超标"]
    if over:
        names = "、".join(micro[k]["name_zh"] for k in over)
        insights.append(f"{names}已超过每日参考值，长期超量需关注")
    insights.extend(
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

    trend = _daily_trend(agg, plan["goal_energy_kcal"])
    achievement = _achievement(agg, refs, macro)
    weak = [
        f"{v['name_zh']}（{v['achieved_pct']}%）"
        for v in achievement["micro"].values()
        if v["level"] in ("warn", "danger")
    ]
    if weak:
        insights.append("达标天数偏少：" + "、".join(weak))

    summary = {
        "reference_hints": reference_hints,
        "insights": insights,
        "data_quality_notes": quality_notes,
        "window_days": req.window_days,
        "basis": "daily_average",
        "daily_trend": trend,
        "achievement": achievement,
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


# ---------------------------------------------------------------- API-25b（周/月）


@router.post("/period-analysis")
def analyze_period(
    req: PeriodAnalysisRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """生成周/月/自定义维度膳食报告（跨方案聚合），落库并返回报告对象。

    口径：聚合窗口内所有 `status='fixed'` 方案的已选候选，按天折算日均后与每日参考量比较；
    与方案级报告共用 `_aggregate_rows / _macro_summary / _micro_summary / _daily_trend / _achievement`；
    并在 `summary.plan_stats` 标注窗口内覆盖的方案数与已执行数。
    """
    if req.report_type not in ("week", "month", "custom"):
        raise BizError(BizCode.PARAM_ERROR, "report_type 只支持 week/month/custom", http_status=400)

    if req.report_type == "custom":
        if req.period_start is None or req.period_end is None:
            raise BizError(
                BizCode.PARAM_ERROR, "custom 报告需提供 period_start 与 period_end", http_status=400
            )
        window_start = req.period_start
        window_end = req.period_end
        if window_end < window_start:
            raise BizError(BizCode.PARAM_ERROR, "period_end 不能早于 period_start", http_status=400)
        window_days = (window_end - window_start).days + 1
    else:
        window_days = req.window_days or (7 if req.report_type == "week" else 30)
        window_days = max(3, min(30, int(window_days)))
        today = date.today()
        window_end = today
        window_start = today - timedelta(days=window_days - 1)

    plan_stats = _window_plan_stats(db, user_id, window_start, window_end)
    rows = _load_selected_window(db, user_id, window_start, window_end)
    agg = _aggregate_rows(rows, window_days, "窗口")
    refs = _load_reference(db, user_id)

    macro = _macro_summary(agg)
    micro, shortfall = _micro_summary(agg, refs, agg["selected_meals"])

    reference_hints: list[str] = [
        f"以下为日均口径：{window_start}~{window_end} 内已固定方案的摄入按天数折算后"
        f"与每日参考量比较"
    ]
    if plan_stats["total_plans"]:
        reference_hints.append(
            f"统计口径：窗口内覆盖 {plan_stats['total_plans']} 份已固定方案，"
            f"其中 {plan_stats['executed_plans']} 份已标记执行"
        )
    reference_hints.append("铁按普通口径计算，未区分经期（本期口径）")
    if any(v.get("status") == "参考提示" for v in micro.values()):
        reference_hints.append(
            "部分微量存在数据缺口或不宜硬性补足，按参考提示处理，不作达标结论"
        )

    insights: list[str] = []
    if shortfall:
        names = "、".join(micro[k]["name_zh"] for k in shortfall)
        advices = "，".join(
            f"{micro[k]['name_zh']}补{_MICRO_ADVICE.get(k, '相关食材')}" for k in shortfall
        )
        insights.append(f"{names}距每日目标仍有缺口，建议下一次方案增加：{advices}")
    over = [k for k in MICRO_IDS if micro[k].get("status") == "超标"]
    if over:
        names = "、".join(micro[k]["name_zh"] for k in over)
        insights.append(f"{names}已超过每日参考值，长期超量需关注")

    approx, total = _data_quality_check_window(db, user_id, window_start, window_end)
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

    trend = _daily_trend(agg, _load_target_kcal(db, user_id))
    achievement = _achievement(agg, refs, macro)
    weak = [
        f"{v['name_zh']}（{v['achieved_pct']}%）"
        for v in achievement["micro"].values()
        if v["level"] in ("warn", "danger")
    ]
    if weak:
        insights.append("达标天数偏少：" + "、".join(weak))

    summary = {
        "reference_hints": reference_hints,
        "insights": insights,
        "data_quality_notes": quality_notes,
        "window_days": window_days,
        "basis": "daily_average",
        "daily_trend": trend,
        "achievement": achievement,
        "plan_stats": plan_stats,
    }
    completeness = {
        "meal_count": agg["meal_count"],
        "known_meal_count": agg["known_meal_count"],
        "missing_meal_count": agg["missing_meal_count"],
    }

    sources = [{"type": "nutrient_reference", "version": "v1.2r1"}]

    # 落库（meal_plan_id 为 NULL：周/月报告跨方案，无单一归属方案）
    report_id = db.execute(
        text(
            "INSERT INTO app.nutrition_report "
            "(user_id, report_type, period_start, period_end, meal_plan_id, "
            " summary, macro_summary, key_micro_summary, completeness, sources, agent_version) "
            "VALUES (:uid, :rt, :ps, :pe, NULL, "
            "        CAST(:summary AS jsonb), CAST(:macro AS jsonb), CAST(:micro AS jsonb), "
            "        CAST(:completeness AS jsonb), CAST(:sources AS jsonb), :ver) "
            "RETURNING nutrition_report_id"
        ),
        {
            "uid": user_id,
            "rt": req.report_type,
            "ps": window_start,
            "pe": window_end,
            "summary": json.dumps(summary, ensure_ascii=False),
            "macro": json.dumps(macro, ensure_ascii=False),
            "micro": json.dumps(micro, ensure_ascii=False),
            "completeness": json.dumps(completeness, ensure_ascii=False),
            "sources": json.dumps(sources, ensure_ascii=False),
            "ver": "backend-v1.2",
        },
    ).scalar_one()
    db.commit()

    return api_success(
        {
            "nutrition_report_id": report_id,
            "user_id": user_id,
            "report_type": req.report_type,
            "period_start": str(window_start),
            "period_end": str(window_end),
            "meal_plan_id": None,
            "window_days": window_days,
            "macro_summary": macro,
            "key_micro_summary": micro,
            "summary": summary,
            "completeness": completeness,
            "sources": sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


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


# ---------------------------------------------------------------- API-26b / 26c（存档）


@router.get("/report/list")
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """报告存档列表（API-26b）：week/month/custom 报告摘要，按生成时间倒序（不含方案级复盘）。"""
    total = db.execute(
        text(
            "SELECT count(*) FROM app.nutrition_report "
            "WHERE user_id = :uid AND report_type IN ('week','month','custom')"
        ),
        {"uid": user_id},
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT nutrition_report_id, report_type, period_start, period_end, "
            "       meal_plan_id, generated_at "
            "FROM app.nutrition_report "
            "WHERE user_id = :uid AND report_type IN ('week','month','custom') "
            "ORDER BY generated_at DESC, nutrition_report_id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"uid": user_id, "limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()

    items = [
        {
            "nutrition_report_id": r["nutrition_report_id"],
            "report_type": r["report_type"],
            "period_start": str(r["period_start"]),
            "period_end": str(r["period_end"]),
            "meal_plan_id": r["meal_plan_id"],
            "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
        }
        for r in rows
    ]
    return api_success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/report/{report_id}")
def get_report_by_id(
    report_id: int,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """按 id 读取报告详情（API-26c），供存档回看。"""
    row = db.execute(
        text(
            "SELECT nutrition_report_id, user_id, report_type, period_start, period_end, "
            "       meal_plan_id, summary, macro_summary, key_micro_summary, completeness, "
            "       sources, generated_at "
            "FROM app.nutrition_report "
            "WHERE nutrition_report_id = :rid AND user_id = :uid"
        ),
        {"rid": report_id, "uid": user_id},
    ).mappings().first()
    if row is None:
        raise BizError(BizCode.NOT_FOUND, f"报告不存在: {report_id}", http_status=404)
    return api_success(_serialize_report(row))
