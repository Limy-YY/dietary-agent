"""膳食方案接口（v1.2：API-21 / API-22 / API-23 / API-24，另含 API-04/05）。

与 v1.1 的差别：
- 旧的 `/generate`、`/weekly` 已按契约删除，语义改为用户自定范围的 `/week/generate`；
- 数据落到四级表（meal_plan → meal_slot → meal_candidate → meal_candidate_dish），
  不再把整份餐食塞进 meal_plan.meals；
- 生成走模块 A 规则引擎（`app.services.rule_engine.generate_plan`），本层只做
  校验、落库、状态流转与留痕，不重复实现配餐算法。

两级状态流转由库触发器把关（`app.guard_meal_plan_update`）：
- draft → candidates 要求每个餐位已有 2~3 个候选；
- candidates → fixed 要求每个餐位已选中候选，并自动补 fixed_at。
"""
from __future__ import annotations

import json
import secrets
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, PageData, api_success, page_data
from app.core.security import CurrentUser
from app.db import get_db
from app.models import MealCandidate, MealCandidateDish, MealPlan, MealSlot
from app.services.rule_engine import (
    PlanRequest,
    Profile as EngineProfile,
    SqlDataSource,
    generate_plan,
)
from app.services.rule_engine.errors import RuleEngineError

router = APIRouter(prefix="/meal-plan", tags=["meal-plan"])

MAX_SPAN_DAYS = 31
VALID_PLAN_TYPES = ("餐", "日", "多日", "周", "自定义")
VALID_MEAL_TYPES = ("早", "午", "晚", "加餐")

# 查询参数/请求体里的英文餐次别名 → 内部中文口径。
# Agent 侧按 breakfast/lunch/dinner 传（agent/backend_client.py），契约口径仍是「早/午/晚」，
# 做一层归一，避免联调期整条生成链路因取值非法失败。
_MEAL_TYPE_ALIASES = {
    "breakfast": "早",
    "lunch": "午",
    "noon": "午",
    "dinner": "晚",
    "supper": "晚",
    "snack": "加餐",
    "加餐餐": "加餐",
}


def _normalize_meal_types(meal_types: list[str]) -> list[str]:
    """把英文/拼音别名归一为中文餐次，未命中的原样保留（交给后续校验报错）。"""
    return [_MEAL_TYPE_ALIASES.get(m.strip().lower(), m.strip()) if isinstance(m, str) else m
            for m in meal_types]



# ---------------------------------------------------------------- 请求模型


class GenerateRequest(BaseModel):
    """API-22 入参。"""

    start_date: date
    end_date: date
    plan_type: str | None = None
    meal_types: list[str] = Field(default_factory=lambda: ["早", "午", "晚"])
    candidates_per_slot: int = Field(3, ge=2, le=3)
    goal_code: str | None = None
    exclude_ingredients: list[str] = Field(default_factory=list)
    soft_avoid: list[str] = Field(default_factory=list)
    variation_seed: int | None = None


class SwapRequest(BaseModel):
    """API-23 入参。"""

    meal_plan_id: int
    meal_slot_id: int
    candidate_id: int | None = None
    reason: str | None = None


class Selection(BaseModel):
    meal_slot_id: int
    candidate_id: int


class FixRequest(BaseModel):
    """API-24 入参。"""

    meal_plan_id: int
    selections: list[Selection] | None = None
    replace: bool = False  # 若与已有 fixed 方案餐位重叠，是否取代旧方案


class ExecutedRequest(BaseModel):
    """API-26 入参：标记方案是否已执行。"""

    executed: bool


# ---------------------------------------------------------------- 工具函数


def _f(value: Decimal | float | None, digits: int = 1) -> float | None:
    """Decimal/float → float，保留 None 语义（None 不当 0）。"""
    if value is None:
        return None
    return round(float(value), digits)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _derived_plan_type(start: date, end: date, meal_types: list[str]) -> str:
    """缺省 plan_type：同日单餐=餐、同日=日、≤6 天=多日、整 7 天=周、更长=多日。"""
    days = (end - start).days + 1
    if days == 1:
        return "餐" if len(meal_types) == 1 else "日"
    if days == 7:
        return "周"
    return "多日"


def _load_engine_profile(db: Session, user_id: str) -> EngineProfile:
    """把 app.profile 映射成规则引擎的 Profile（v1.2 字段优先，回退旧列）。"""
    row = db.execute(
        text(
            "SELECT name, gender, sex, age, height_cm, weight_kg, goal_code, goal, "
            "conditions, allergies, religious_ethical, cooking_equipment "
            "FROM app.profile WHERE user_id = :uid"
        ),
        {"uid": user_id},
    ).mappings().first()
    if row is None:
        raise BizError(BizCode.NOT_FOUND, f"用户档案不存在: {user_id}", http_status=404)

    conditions = row["conditions"] if isinstance(row["conditions"], dict) else {}
    return EngineProfile(
        name=row["name"],
        gender=row["gender"] or row["sex"] or "女",
        age=int(row["age"] or 20),
        height_cm=float(row["height_cm"] or 165),
        weight_kg=float(row["weight_kg"] or 55),
        goal_code=row["goal_code"] or row["goal"] or "maintain",
        conditions=conditions,
        allergies=list(row["allergies"] or []),
        religious_ethical=list(row["religious_ethical"] or []),
        cooking_equipment=list(row["cooking_equipment"] or []),
    )


def _get_plan(db: Session, meal_plan_id: int, *, lock: bool = False) -> MealPlan:
    """按 id 取方案（含四级关系），不存在抛 404。"""
    stmt = (
        select(MealPlan)
        .where(MealPlan.meal_plan_id == meal_plan_id, MealPlan.is_deleted.is_(False))
        .options(
            selectinload(MealPlan.slots)
            .selectinload(MealSlot.candidates)
            .selectinload(MealCandidate.dishes)
        )
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    plan = db.execute(stmt).scalar_one_or_none()
    if plan is None:
        raise BizError(BizCode.NOT_FOUND, f"方案不存在: {meal_plan_id}", http_status=404)
    return plan


def _overlapping_fixed_plans(db: Session, user_id: str, plan: MealPlan) -> list[dict]:
    """与本方案存在「同一天同一餐次」餐位重叠的、仍为 fixed 未删除的方案。

    以餐位（slot_date + meal_type）粒度判冲突，而非整个日期区间：用户给某天
    单排一餐（如晚餐）不应误伤同天已固定的早/午餐。
    返回每个重叠方案的信息：overlap_start/end 为重叠日期区间，fully_covered 表示
    旧方案是否被新方案完全覆盖（只有完全覆盖才能无损失地整份取代）。
    """
    new_slots = db.execute(
        text("SELECT slot_date, meal_type FROM app.meal_slot WHERE meal_plan_id = :pid"),
        {"pid": plan.meal_plan_id},
    ).all()
    new_set = {(str(r[0]), r[1]) for r in new_slots}

    rows = db.execute(
        text(
            "SELECT p.meal_plan_id, p.fixed_at, s.slot_date, s.meal_type "
            "FROM app.meal_plan p "
            "JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id "
            "WHERE p.user_id = :uid AND p.status = 'fixed' AND NOT p.is_deleted "
            "  AND p.meal_plan_id <> :pid "
            "ORDER BY p.fixed_at ASC NULLS LAST, p.meal_plan_id ASC, s.slot_date, s.meal_type"
        ),
        {"uid": user_id, "pid": plan.meal_plan_id},
    ).all()

    by_plan: dict[int, list] = {}
    for r in rows:
        by_plan.setdefault(int(r[0]), []).append(r)

    result: list[dict] = []
    for pid, slots in by_plan.items():
        overlap_dates = sorted({str(r[2]) for r in slots if (str(r[2]), r[3]) in new_set})
        if not overlap_dates:
            continue
        covered = sum(1 for r in slots if (str(r[2]), r[3]) in new_set)
        result.append(
            {
                "meal_plan_id": pid,
                "overlap_start": overlap_dates[0],
                "overlap_end": overlap_dates[-1],
                "fully_covered": covered == len(slots),
            }
        )
    return result


def _g(value) -> str:
    """克数 → '150g'（整数值不显示小数点）。"""
    if value is None:
        return ""
    f = float(value)
    return f"{f:g}g"


def _dish_details(db: Session, dish_ids) -> dict[str, dict]:
    """按 dish_id 批量取菜名 / 做法 / 食材。菜名与做法在 core.dish，食材在 dish_ingredient 关联表。"""
    ids = sorted({str(x) for x in dish_ids if x})
    if not ids:
        return {}
    dish_rows = db.execute(
        text("SELECT dish_id, name, method_text FROM core.dish WHERE dish_id = ANY(:ids)"),
        {"ids": ids},
    ).mappings().all()
    ing_rows = db.execute(
        text(
            "SELECT di.dish_id, i.name, di.amount_g, di.role "
            "FROM core.dish_ingredient di "
            "JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id "
            "WHERE di.dish_id = ANY(:ids) "
            "ORDER BY di.dish_id, di.role, i.name"
        ),
        {"ids": ids},
    ).mappings().all()
    details: dict[str, dict] = {
        r["dish_id"]: {"name": r["name"], "method_text": r["method_text"], "ingredients": []}
        for r in dish_rows
    }
    for r in ing_rows:
        detail = details.get(r["dish_id"])
        if detail is None:
            continue
        role = r["role"] or ""
        detail["ingredients"].append(f"{r['name']} {_g(r['amount_g'])}" + (f"（{role}）" if role else ""))
    return details


def _serialize_candidate(c: MealCandidate, details: dict[str, dict]) -> dict:
    return {
        "candidate_id": c.candidate_id,
        "rank": c.rank,
        "reason_codes": c.reason_codes or [],
        "why_text": c.why_text,
        "macro_estimate": c.macro_estimate or {},
        "micro_estimate": c.micro_estimate or {},
        "oil_salt_estimate": c.oil_salt_estimate or {},
        "eating_order_advice": c.eating_order_advice,
        "sources": c.sources or [],
        "agent_output_version": c.agent_output_version,
        "dishes": [
            {
                "dish_id": d.dish_id,
                "name": (details.get(d.dish_id) or {}).get("name", ""),
                "method_text": (details.get(d.dish_id) or {}).get("method_text") or "",
                "ingredients": (details.get(d.dish_id) or {}).get("ingredients", []),
                "role": d.role,
                "servings": _f(d.servings, 2),
                "estimated_g": _f(d.estimated_g),
                "portion_text": d.portion_text,
                "method_override": d.method_override,
                "display_order": d.display_order,
            }
            for d in sorted(c.dishes, key=lambda x: x.display_order)
        ],
    }


def _selected_candidate(slot: MealSlot) -> MealCandidate | None:
    return next(
        (c for c in slot.candidates if c.candidate_id == slot.selected_candidate_id), None
    )


def _serialize_slot(slot: MealSlot, details: dict[str, dict]) -> dict:
    picked = _selected_candidate(slot)
    return {
        "meal_slot_id": slot.meal_slot_id,
        "slot_date": str(slot.slot_date),
        "meal_type": slot.meal_type,
        "display_order": slot.display_order,
        "target_macro": slot.target_macro or {},
        "selected_candidate_id": slot.selected_candidate_id,
        "selected_candidate": _serialize_candidate(picked, details) if picked else None,
        "candidates": [_serialize_candidate(c, details) for c in slot.candidates],
    }


def _serialize_plan(plan: MealPlan, db: Session) -> dict:
    _details = _dish_details(db, [d.dish_id for s in plan.slots for c in s.candidates for d in c.dishes])
    return {
        "meal_plan_id": plan.meal_plan_id,
        "user_id": plan.user_id,
        "plan_type": plan.plan_type,
        "status": plan.status,
        "is_executed": plan.is_executed,
        "plan_date": str(plan.plan_date),
        "start_date": str(plan.start_date),
        "end_date": str(plan.end_date),
        "goal_energy_kcal": _f(plan.goal_energy_kcal),
        "goal_code": (plan.generation_context or {}).get("goal_code"),
        "macro_ratio": plan.macro_ratio or {},
        "generation_context": plan.generation_context or {},
        "daily_summary": _daily_summary(plan),
        "why_summary": _summary_text(plan),
        "data_quality_notes": (plan.generation_context or {}).get("data_quality_notes", []),
        "reference_hints": (plan.generation_context or {}).get("reference_hints", []),
        "micro_balance_window_start": _iso(plan.micro_balance_window_start),
        "micro_balance_window_end": _iso(plan.micro_balance_window_end),
        "agent_version": plan.agent_version,
        "data_version": plan.data_version,
        "fixed_at": _iso(plan.fixed_at),
        "created_at": _iso(plan.created_at),
        "updated_at": _iso(plan.updated_at),
        "slots": [_serialize_slot(s, _details) for s in sorted(plan.slots, key=lambda x: (x.slot_date, x.display_order))],
    }


def _persist_plan(
    db: Session,
    user_id: str,
    request: GenerateRequest,
    plan_type: str,
    result,
    derived_from_plan_id: int | None = None,
) -> MealPlan:
    """把 PlanResult 落到四级表，并把候选序号重映射为全局 candidate_id。"""
    balance = result.balance
    plan = MealPlan(
        user_id=user_id,
        plan_type=plan_type,
        status="draft",  # 先落 draft，等子表齐了再转 candidates（触发器会把关）
        plan_date=request.start_date,
        start_date=request.start_date,
        end_date=request.end_date,
        goal_energy_kcal=Decimal(str(round(result.targets.energy_kcal, 1))),
        derived_from_plan_id=derived_from_plan_id,
        macro_ratio=result.targets.as_dict().get("macro_ratio") or {},
        meals={},
        sources={"rule_engine": "v1.2", "goal_code": result.targets.goal_code},
        generation_request=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
        generation_context={
            "goal_code": result.targets.goal_code,
            "diagnostics": result.diagnostics,
            "data_quality_notes": result.data_quality_notes,
            "reference_hints": result.reference_hints,
        },
        micro_balance_window_start=(
            date.fromisoformat(balance.window_start) if balance and balance.window_start else request.start_date
        ),
        micro_balance_window_end=(
            date.fromisoformat(balance.window_end) if balance and balance.window_end else request.end_date
        ),
        agent_version="rule-engine-v1.2",
        data_version="v1.2",
    )
    db.add(plan)
    db.flush()

    for slot_result in result.slots:
        slot = MealSlot(
            meal_plan_id=plan.meal_plan_id,
            slot_date=date.fromisoformat(slot_result.slot_date),
            meal_type=slot_result.meal_type,
            display_order=slot_result.display_order,
            target_macro=slot_result.as_dict()["target_macro"],
        )
        db.add(slot)
        db.flush()

        created: list[MealCandidate] = []
        for cand in slot_result.candidates:
            payload = cand.as_dict()
            row = MealCandidate(
                meal_slot_id=slot.meal_slot_id,
                rank=cand.rank,
                reason_codes=cand.reason_codes,
                why_text=cand.why_text,
                macro_estimate=payload["macro_estimate"],
                micro_estimate=payload["micro_estimate"],
                oil_salt_estimate=payload["oil_salt_estimate"],
                eating_order_advice=cand.eating_order_advice,
                sources=payload["sources"],
                agent_output_version="rule-engine-v1.2",
            )
            for dish in payload["dishes"]:
                row.dishes.append(
                    MealCandidateDish(
                        dish_id=dish["dish_id"],
                        role=dish["role"],
                        servings=Decimal(str(dish["servings"])),
                        estimated_g=None,  # 引擎不编造克重
                        portion_text=dish.get("portion_text"),
                        method_override=dish.get("method_override"),
                        display_order=int(dish["display_order"]),
                    )
                )
            db.add(row)
            created.append(row)
        db.flush()

        # 首选候选：引擎给的餐内序号 → 已落库的全局 candidate_id
        if created:
            first = slot_result.selected_candidate_id
            chosen = next((c for c in created if c.rank == first), created[0])
            slot.selected_candidate_id = chosen.candidate_id
    db.flush()

    if any(len(s.candidates) < 2 for s in result.slots):
        raise BizError(BizCode.PLAN_GENERATION_FAILED, "合法候选不足两个，未保存方案")
    plan.status = "candidates"
    db.flush()
    return plan



# ---------------------------------------------------------------- V2.1 local modification
from dataclasses import replace as dc_replace
from app.services.rule_engine.models import DishPortion, MacroRange, DEFAULT_MEAL_RATIOS
from app.services.rule_engine.targets import compute_targets
from app.services.rule_engine.candidates import build_candidates, diversify
from app.services.rule_engine.pipeline import _split_dishes
from app.services.rule_engine.local_edit import evaluate_portions, replace_dish_candidates
from app.services.rule_engine.quality import repetition_cost
from app.services.rule_engine.meal_templates import selection_key, staple_key


class LocalEditRequest(BaseModel):
    meal_plan_id: int = Field(gt=0)
    meal_slot_id: int = Field(gt=0)
    expected_candidate_id: int = Field(gt=0)
    exclude_ingredients: list[str] = Field(default_factory=list, max_length=30)
    soft_avoid: list[str] = Field(default_factory=list, max_length=30)


class SlotRegenerateRequest(LocalEditRequest):
    keep_dish_ids: list[str] = Field(default_factory=list, max_length=3)


class DishReplaceRequest(LocalEditRequest):
    dish_id: str = Field(min_length=1, max_length=100)
    replacement_dish_id: str | None = None
    replacement_query: str = Field(default='', max_length=80)
    # An explicitly authorized approximate result may be chosen; by default it is not persisted.
    allow_approximate: bool = False


def _daily_summary(plan):
    groups = {}
    for s in plan.slots:
        groups.setdefault(str(s.slot_date), []).append(s)
    def total(values):
        return round(sum(float(v) for v in values), 2) if values and all(v is not None for v in values) else None
    result = []
    for day, slots in sorted(groups.items()):
        chosen = [_selected_candidate(s) for s in slots]
        target = {k: total([(s.target_macro or {}).get(k) for s in slots]) for k in ('kcal','protein_g','fat_g','carb_g')}
        actual = {k: total([(c.macro_estimate or {}).get(k) if c else None for c in chosen]) for k in ('kcal','protein_g','fat_g','carb_g','fiber_g')}
        micro = {k: total([(c.micro_estimate or {}).get(k) if c else None for c in chosen]) for k in ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')}
        oil_salt = {k: total([(c.oil_salt_estimate or {}).get(k) if c else None for c in chosen])
                    for k in ('oil_g','salt_g','sodium_mg','total_salt_equivalent_g')}
        result.append({'date':day,'slot_count':len(slots),'daily_goal_kcal':_f(plan.goal_energy_kcal),
                       'planned_target':target,'actual':actual,'micro_estimate':micro,'oil_salt_estimate':oil_salt,
                       'macro_delta':_macro_delta(actual,target)})
    return result


def _summary_text(plan):
    return '已安排 %s 餐。各餐目标、实际营养及每日已安排合计见方案；未安排餐次不计入。' % len(plan.slots)


def _original_request(plan):
    try:
        raw = json.loads(plan.generation_request or '{}')
    except (ValueError, TypeError):
        raise BizError(BizCode.PARAM_ERROR, '原始生成约束无法读取，需重新生成方案')
    if not isinstance(raw, dict):
        raise BizError(BizCode.PARAM_ERROR, '原始生成约束无法读取')
    return raw


def _edit_context(db, plan, slot, exclude=(), soft=()):
    orig = _original_request(plan)
    extra = ((plan.generation_context or {}).get('slot_constraints') or {}).get(str(slot.meal_slot_id), {})
    ds = SqlDataSource(db)
    profile = _load_engine_profile(db, plan.user_id)
    goal = orig.get('goal_code') or (plan.generation_context or {}).get('goal_code') or profile.goal_code
    excluded = list(dict.fromkeys([*(orig.get('exclude_ingredients') or []), *(extra.get('exclude_ingredients') or []), *exclude]))
    soft_avoid = list(dict.fromkeys([*(orig.get('soft_avoid') or []), *(extra.get('soft_avoid') or []), *soft]))
    req = PlanRequest(start_date=str(slot.slot_date), end_date=str(slot.slot_date), meal_types=[slot.meal_type],
                      goal_code=goal, exclude_ingredients=excluded, soft_avoid=soft_avoid)
    targets = compute_targets(profile, ds.get_goal_row(goal), ds.get_micro_reference_rows(profile), req,
                              ds.get_goal_row('maintain') if goal != 'maintain' else None)
    target = targets.meal_targets.get(slot.meal_type)
    saved = slot.target_macro or {}
    if target is None or not all(saved.get(k) is not None for k in ('kcal','protein_g','fat_g','carb_g')):
        raise BizError(BizCode.PARAM_ERROR, '餐位原始目标不完整，需重新生成方案')
    # Preserve original slot's target; reject legacy partial-slot plans with incorrect full-day allocation.
    if plan.goal_energy_kcal and abs(float(saved['kcal']) - float(plan.goal_energy_kcal) * DEFAULT_MEAL_RATIOS.get(slot.meal_type,0)) > 1.0:
        raise BizError(BizCode.PARAM_ERROR, '旧方案餐位目标口径异常，请先重新生成整份方案')
    def rng(key):
        v = float(saved[key]); return MacroRange(key,v,round(v*(1-req.tolerance),1),round(v*(1+req.tolerance),1))
    target = dc_replace(target,kcal=float(saved['kcal']),protein=rng('protein_g'),fat=rng('fat_g'),carb=rng('carb_g'))
    return req, targets, target, ds.get_dish_facts()


def _row_portions(row, catalog):
    if row is None:
        raise BizError(BizCode.PARAM_ERROR, '餐位未选择候选')
    facts = {d.dish_id:d for d in catalog}
    if any(d.dish_id not in facts or d.method_override for d in row.dishes):
        raise BizError(BizCode.PARAM_ERROR, '旧候选含不可用菜式或未支持的做法覆盖')
    return [DishPortion(facts=facts[d.dish_id], servings=float(d.servings)) for d in sorted(row.dishes,key=lambda d:d.display_order)]


def _validate_saved(db, plan, slot, row):
    req, targets, target, catalog = _edit_context(db, plan, slot)
    try:
        return evaluate_portions(_row_portions(row,catalog),target,targets,req.soft_avoid)
    except RuleEngineError as exc:
        raise BizError(BizCode.PLAN_GENERATION_FAILED, f'候选不符合现有约束：{exc}') from exc


def _lock_edit(db, user_id, req):
    plan = _get_plan(db, req.meal_plan_id, lock=True)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, '无权操作他人方案', http_status=403)
    if plan.status != 'candidates':
        raise BizError(BizCode.PLAN_STATE_CONFLICT, '仅待确认方案可以修改', http_status=409)
    slot = next((s for s in plan.slots if s.meal_slot_id == req.meal_slot_id),None)
    if slot is None:
        raise BizError(BizCode.NOT_FOUND, '餐位不存在于该方案', http_status=404)
    old = _selected_candidate(slot)
    if old is None or old.candidate_id != req.expected_candidate_id:
        raise BizError(BizCode.PLAN_STATE_CONFLICT, '餐位已改变，请刷新方案再操作', http_status=409)
    return plan,slot,old


def _previous_candidates(plan, slot, catalog):
    from types import SimpleNamespace
    other = []
    for s in plan.slots:
        if s is slot: continue
        try:
            p = _row_portions(_selected_candidate(s),catalog)
        except BizError:
            continue
        other.append(SimpleNamespace(portions=p,dish_ids=[x.dish_id for x in p]))
    return other

def _update_candidate_row(db: Session, row: MealCandidate, candidate, rank: int) -> MealCandidate:
    """原地更新候选的菜品与营养估算，避免新增第 4 条记录触发 rank 1..3 检查约束。"""
    payload = candidate.as_dict()
    row.rank = rank
    row.reason_codes = payload['reason_codes']
    row.why_text = payload['why_text']
    row.macro_estimate = payload['macro_estimate']
    row.micro_estimate = payload['micro_estimate']
    row.oil_salt_estimate = payload['oil_salt_estimate']
    row.eating_order_advice = candidate.eating_order_advice
    row.sources = payload['sources']
    row.agent_output_version = 'rule-engine-v2.1'
    row.dishes.clear()
    db.flush()  # 先清空旧菜品再插入，防止保留菜品的 (candidate_id, dish_id) 主键冲突
    for dish in payload['dishes']:
        row.dishes.append(MealCandidateDish(
            dish_id=dish['dish_id'],
            role=dish['role'],
            servings=Decimal(str(dish['servings'])),
            portion_text=dish.get('portion_text'),
            display_order=dish['display_order'],
        ))
    db.flush()
    return row

def _insert_candidate(db, slot, candidate, rank):
    payload = candidate.as_dict()
    row = MealCandidate(meal_slot_id=slot.meal_slot_id,rank=rank,
        reason_codes=payload['reason_codes'],why_text=payload['why_text'],macro_estimate=payload['macro_estimate'],
        micro_estimate=payload['micro_estimate'],oil_salt_estimate=payload['oil_salt_estimate'],
        eating_order_advice=payload['eating_order_advice'],sources=payload['sources'],agent_output_version='rule-engine-v2.1')
    for dish in payload['dishes']:
        row.dishes.append(MealCandidateDish(dish_id=dish['dish_id'],role=dish['role'],
            servings=Decimal(str(dish['servings'])),portion_text=dish.get('portion_text'),display_order=dish['display_order']))
    db.add(row); db.flush()
    return row


def _record_edit(db, plan, slot, old, new, tool, instruction):
    delta = _macro_delta(new.macro_estimate, old.macro_estimate)
    prev_id = None if old.candidate_id == new.candidate_id else old.candidate_id
    try:
        with db.begin_nested():
            db.execute(
                text(
                    'INSERT INTO app.plan_adjustment '
                    '(meal_plan_id,meal_slot_id,previous_candidate_id,new_candidate_id,instruction,nutrition_change,tool_name,tool_version) '
                    'VALUES (:p,:s,:o,:n,:i,cast(:d AS jsonb),:t,:v)'
                ),
                {
                    'p': plan.meal_plan_id, 's': slot.meal_slot_id,
                    'o': prev_id, 'n': new.candidate_id,
                    'i': instruction, 'd': json.dumps(delta),
                    't': tool, 'v': 'v2.1',
                },
            )
    except Exception:
        pass
    slot.selected_candidate_id = new.candidate_id


def _finish_edit(db, plan, slot, req, context, tool, old, new, diagnostic):
    generation_context = dict(plan.generation_context or {})
    constraints = dict(generation_context.get('slot_constraints') or {})
    constraints[str(slot.meal_slot_id)] = {'exclude_ingredients':context.exclude_ingredients,'soft_avoid':context.soft_avoid}
    generation_context['slot_constraints'] = constraints
    generation_context['last_local_edit'] = {'meal_slot_id':slot.meal_slot_id,'operation':tool,**diagnostic}
    plan.generation_context = generation_context
    _record_edit(db,plan,slot,old,new,tool,tool)
    db.flush()
    pid = plan.meal_plan_id
    db.expire_all()
    # Serialize before commit so errors roll back rather than report a failed committed mutation.
    result = _serialize_plan(_get_plan(db,pid),db)
    db.commit()
    return api_success(result)


@router.post('/slot/regenerate')
def regenerate_slot(req: SlotRegenerateRequest, user_id: str = CurrentUser, db: Session = Depends(get_db)) -> ApiResponse[dict]:
    try:
        plan,slot,old = _lock_edit(db,user_id,req)
        context,targets,target,catalog = _edit_context(db,plan,slot,req.exclude_ingredients,req.soft_avoid)
        old_portions = _row_portions(old,catalog)
        if not set(req.keep_dish_ids).issubset({p.dish_id for p in old_portions}):
            raise BizError(BizCode.PARAM_ERROR,'保留菜式不属于当前餐位')
        staples,sides = _split_dishes(catalog)
        excluded = frozenset({tuple(sorted(p.dish_id for p in old_portions))})
        kwargs = dict(max_candidates=200,soft_avoid=context.soft_avoid,required_ids=frozenset(req.keep_dish_ids),excluded_combinations=excluded)
        strict = build_candidates(target,staples,sides,targets,**kwargs)
        previous = _previous_candidates(plan,slot,catalog)
        # Keep portions of explicitly retained dishes too, then recompute and revalidate.
        def adjust(pool):
            valid = []
            kept = {p.dish_id:p for p in old_portions if p.dish_id in req.keep_dish_ids}
            for c in pool:
                try:
                    valid.append(evaluate_portions([kept.get(p.dish_id,p) for p in c.portions],target,targets,context.soft_avoid))
                except RuleEngineError: continue
            return valid
        strict = [c for c in adjust(strict) if 'macro_range_relaxed' not in c.reason_codes]
        pool = strict
        from app.services.rule_engine.practical_quality import candidate_priority
        attempted = len({c.signature[0] for c in strict}) < 3 or sum(candidate_priority(c)[:2]==(False,0) for c in strict)<9
        if attempted:
            seen = {tuple(sorted(c.dish_ids)) for c in strict}
            pool = strict + [c for c in adjust(build_candidates(target,staples,sides,targets,relaxed=True,extend=True,**kwargs)) if tuple(sorted(c.dish_ids)) not in seen]
        pool.sort(key=lambda c: selection_key(c,target,previous,repetition_cost(c,previous)))
        picked = diversify(pool,3)
        if len(picked) < 2:
            raise BizError(BizCode.PLAN_GENERATION_FAILED,'合法新候选不足两个，原餐位保留')
        # Archive instead of deleting history-referenced rows; free ranks before INSERT.
        existing = sorted(slot.candidates, key=lambda c: c.rank)
        new = []
        for i, cand in enumerate(picked):
            if i < len(existing):
                new.append(_update_candidate_row(db, existing[i], cand, i + 1))
            else:
                new.append(_insert_candidate(db, slot, cand, i + 1))
        return _finish_edit(db, plan, slot, req, context, 'slot/regenerate', old, new[0],
                            {'relaxed_attempts': int(attempted), 'candidate_count': len(new)})
    except BizError:
        db.rollback(); raise
    except RuleEngineError as exc:
        db.rollback(); raise BizError(BizCode.PLAN_GENERATION_FAILED,str(exc)) from exc
    except Exception as exc:
        db.rollback(); raise BizError(BizCode.PLAN_GENERATION_FAILED,'餐位修改失败，原方案保留') from exc


@router.post('/dish/replace')
def replace_dish(req: DishReplaceRequest, user_id: str = CurrentUser, db: Session = Depends(get_db)) -> ApiResponse[dict]:
    try:
        plan,slot,old = _lock_edit(db,user_id,req)
        context,targets,target,catalog = _edit_context(db,plan,slot,req.exclude_ingredients,req.soft_avoid)
        portions = _row_portions(old,catalog)
        pool = replace_dish_candidates(portions,req.dish_id,catalog,target,targets,req.replacement_query,
                                       req.replacement_dish_id,context.soft_avoid,_previous_candidates(plan,slot,catalog))
        if not pool:
            raise BizError(BizCode.PLAN_GENERATION_FAILED,'没有符合安全约束及本餐推荐结构的替代菜，原方案保留；可尝试重生成本餐')
        best = pool[0]
        if 'macro_range_relaxed' in best.reason_codes and not req.allow_approximate:
            raise BizError(BizCode.PLAN_GENERATION_FAILED,'仅换一道菜无法满足营养目标；可明确同意近似结果后再试，或选择重新生成本餐')
        # Other active alternatives must also obey newly-added hard exclusions; otherwise reject
        # rather than leave unselectable alternatives or silently alter unrelated dishes.
        for row in slot.candidates:
            if row is not old:
                try: evaluate_portions(_row_portions(row,catalog),target,targets)
                except RuleEngineError as exc:
                    raise BizError(BizCode.PLAN_GENERATION_FAILED,'新增硬约束影响其他候选，请重新生成该餐') from exc
        new = _update_candidate_row(db, old, best, old.rank)
        return _finish_edit(db, plan, slot, req, context, 'dish/replace', old, new, {'replaced_dish_id': req.dish_id,
                                                                                     'approximate': 'macro_range_relaxed' in best.reason_codes})
    except BizError:
        db.rollback(); raise
    except RuleEngineError as exc:
        db.rollback(); raise BizError(BizCode.PLAN_GENERATION_FAILED,str(exc)) from exc
    except Exception as exc:
        db.rollback(); raise BizError(BizCode.PLAN_GENERATION_FAILED,'单菜替换失败，原方案保留') from exc


# ---------------------------------------------------------------- API-22 生成


def _generate_and_persist(
    db: Session,
    user_id: str,
    req: GenerateRequest,
    derived_from_plan_id: int | None = None,
) -> MealPlan:
    """校验 → 规则引擎生成 → 落库（API-22 与 API-27 共用）。"""
    if req.end_date < req.start_date:
        raise BizError(BizCode.PARAM_ERROR, "end_date 不能早于 start_date")
    span = (req.end_date - req.start_date).days + 1
    if span > MAX_SPAN_DAYS:
        raise BizError(BizCode.PARAM_ERROR, f"日期跨度上限 {MAX_SPAN_DAYS} 天，当前 {span} 天")
    if not req.meal_types:
        raise BizError(BizCode.PARAM_ERROR, "meal_types 不能为空")
    req.meal_types = _normalize_meal_types(req.meal_types)
    bad = [m for m in req.meal_types if m not in VALID_MEAL_TYPES]
    if bad:
        raise BizError(BizCode.PARAM_ERROR, f"meal_types 取值非法: {bad}")

    plan_type = req.plan_type or _derived_plan_type(req.start_date, req.end_date, req.meal_types)
    if plan_type not in VALID_PLAN_TYPES:
        raise BizError(BizCode.PARAM_ERROR, f"plan_type 取值非法: {plan_type}")

    profile = _load_engine_profile(db, user_id)
    if req.variation_seed is None:
        req.variation_seed = secrets.randbits(31)
    engine_request = PlanRequest(
        start_date=req.start_date.isoformat(),
        end_date=req.end_date.isoformat(),
        plan_type=plan_type,
        meal_types=req.meal_types,
        candidates_per_slot=req.candidates_per_slot,
        goal_code=req.goal_code,
        user_id=user_id,
        exclude_ingredients=req.exclude_ingredients,
        soft_avoid=req.soft_avoid,
        max_slots=span * len(req.meal_types),  # 引擎默认 21 餐位，按实际跨度放宽
        variation_seed=req.variation_seed,
    )

    try:
        result = generate_plan(profile, engine_request, SqlDataSource(db))
    except RuleEngineError as exc:
        raise BizError(BizCode.PLAN_GENERATION_FAILED, f"方案生成失败: {exc}") from exc
    except Exception as exc:  # 兜底：数据或算法异常统一归 2006，避免 500 裸抛
        raise BizError(BizCode.CALC_FAILED, f"方案生成异常: {exc}") from exc

    try:
        plan = _persist_plan(db, user_id, req, plan_type, result, derived_from_plan_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise BizError(BizCode.PLAN_GENERATION_FAILED, f"方案落库失败: {exc}") from exc

    return plan


@router.post("/week/generate")
def generate_week_plan(
    req: GenerateRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """生成用户自定范围的方案（API-22）。"""
    plan = _generate_and_persist(db, user_id, req)
    return api_success(_serialize_plan(_get_plan(db, plan.meal_plan_id), db))


# ---------------------------------------------------------------- API-23 换候选


def _macro_delta(new: dict, old: dict) -> dict:
    """相对原候选的宏量/微量变化（None 不参与相减）。"""
    out: dict = {}
    for key in ("kcal", "protein_g", "fat_g", "carb_g", "fiber_g"):
        a, b = new.get(key), old.get(key)
        out[key] = round(float(a) - float(b), 1) if a is not None and b is not None else None
    return out


def _next_swap_candidate(candidates, previous_id):
    """Cycle through every ranked alternative instead of toggling the first two."""
    ordered = sorted(
        candidates,
        key=lambda c: (c.rank is None, c.rank if c.rank is not None else 10**9, c.candidate_id),
    )
    if len(ordered) < 2:
        return None
    current_index = next(
        (i for i, candidate in enumerate(ordered) if candidate.candidate_id == previous_id),
        -1,
    )
    return ordered[(current_index + 1) % len(ordered)]


@router.post("/candidate/swap")
def swap_candidate(
    req: SwapRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """替换某个餐位的选中候选（API-23），并写一条 plan_adjustment 留痕。"""
    plan = _get_plan(db, req.meal_plan_id, lock=True)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权操作他人方案", http_status=403)
    if plan.status != "candidates":
        raise BizError(
            BizCode.PLAN_STATE_CONFLICT,
            f"当前状态 {plan.status} 不可换候选（仅 candidates 可换）",
        )

    slot = next((s for s in plan.slots if s.meal_slot_id == req.meal_slot_id), None)
    if slot is None:
        raise BizError(BizCode.NOT_FOUND, f"餐位不存在: {req.meal_slot_id}", http_status=404)

    previous_id = slot.selected_candidate_id
    if req.candidate_id is not None:
        target = next((c for c in slot.candidates if c.candidate_id == req.candidate_id), None)
        if target is None:
            raise BizError(
                BizCode.NOT_FOUND, f"候选不属于该餐位: {req.candidate_id}", http_status=404
            )
    else:
        target = _next_swap_candidate(slot.candidates, previous_id)
        if target is None:
            raise BizError(BizCode.PARAM_ERROR, "该餐位没有其他可选候选")

    if target.candidate_id == previous_id:
        raise BizError(BizCode.PARAM_ERROR, "该候选已是当前选中，无需替换")

    _validate_saved(db, plan, slot, target)
    previous = next((c for c in slot.candidates if c.candidate_id == previous_id), None)
    delta = _macro_delta(target.macro_estimate or {}, (previous.macro_estimate if previous else {}) or {})

    slot.selected_candidate_id = target.candidate_id
    db.execute(
        text(
            "INSERT INTO app.plan_adjustment "
            "(meal_plan_id, meal_slot_id, previous_candidate_id, new_candidate_id, "
            " instruction, nutrition_change, tool_name, tool_version) "
            "VALUES (:pid, :sid, :prev, :new, :ins, cast(:chg AS jsonb), :tool, :ver)"
        ),
        {
            "pid": plan.meal_plan_id,
            "sid": slot.meal_slot_id,
            "prev": previous_id,
            "new": target.candidate_id,
            "ins": req.reason or "用户换候选",
            "chg": json.dumps(delta, ensure_ascii=False),
            "tool": "meal-plan/candidate/swap",
            "ver": "v1.2",
        },
    )
    db.commit()

    return api_success(
        {
            "meal_plan_id": plan.meal_plan_id,
            "meal_slot_id": slot.meal_slot_id,
            "selected_candidate_id": target.candidate_id,
            "previous_candidate_id": previous_id,
            "candidate": _serialize_candidate(target, _dish_details(db, [d.dish_id for d in target.dishes])),
            "macro_delta": delta,
        }
    )


# ---------------------------------------------------------------- API-24 固定


def _shopping_items(db: Session, plan: MealPlan) -> list[dict]:
    """按选中候选展开到食材级，并保留「天」维度（库内平铺，分组留给返回层）。

    契约 §3.6：清单项是食材（`ingredient_id / name / estimated_quantity / unit`），
    不是菜品。数量为估算值：菜品每份用量 × 该菜在方案内累计份数。
    周/多日方案按 `slot_date` 分天累计，单项带 `day_date`，支撑前端按天分列与分批采购；
    单餐/单日方案同天归并，返回层会自动退化为纯类别分组。
    可选配料（`is_optional`）不计入采购。
    """
    # (dish_id, day) -> 累计份数；day 取 slot_date 的 ISO 日期，跨天不合并
    dish_day_servings: dict[tuple[str, str], float] = {}
    for slot in plan.slots:
        cand = _selected_candidate(slot)
        if cand is None:
            continue
        day = str(slot.slot_date) if slot.slot_date else ""
        for d in cand.dishes:
            key = (str(d.dish_id), day)
            dish_day_servings[key] = dish_day_servings.get(key, 0.0) + float(d.servings or 1)

    if not dish_day_servings:
        return []

    rows = db.execute(
        text(
            "SELECT di.dish_id, di.ingredient_id, di.amount_g, di.is_optional, "
            "       i.food_id, i.name, i.category "
            "FROM core.dish_ingredient di "
            "JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id "
            "WHERE di.dish_id = ANY(:ids)"
        ),
        {"ids": list({dish_id for dish_id, _ in dish_day_servings})},
    ).mappings().all()

    agg: dict[tuple[str, int], dict] = {}
    for r in rows:
        if r["is_optional"]:
            continue
        for (dish_id, day), servings in dish_day_servings.items():
            if str(dish_id) != str(r["dish_id"]):
                continue
            ingredient_id = r["ingredient_id"]
            key = (day, ingredient_id)
            item = agg.setdefault(
                key,
                {
                    "ingredient_id": r["food_id"] or str(ingredient_id),
                    "name": r["name"],
                    "category": r["category"] or "未分类",
                    "estimated_quantity": 0.0,
                    "unit": "g",
                    "day_date": day,
                },
            )
            item["estimated_quantity"] += float(r["amount_g"] or 0) * servings

    items = list(agg.values())
    for it in items:
        it["estimated_quantity"] = round(it["estimated_quantity"], 1)
    return sorted(items, key=lambda x: (x["day_date"], x["category"], x["name"]))


@router.post("/week/fix")
def fix_plan(
    req: FixRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """固定方案（API-24），成功后同步刷新食材清单。

    若本方案与用户已有的固定方案在「同一天同一餐次」上重叠，默认拒绝并提示用
    replace=true 取代旧方案，避免同一时间段多份 fixed 方案叠加进膳食报告。
    """
    plan = _get_plan(db, req.meal_plan_id, lock=True)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权操作他人方案", http_status=403)
    if plan.status == "fixed":
        raise BizError(BizCode.PLAN_STATE_CONFLICT, "方案已固定，不可重复固定")
    if plan.status != "candidates":
        raise BizError(BizCode.PLAN_STATE_CONFLICT, f"当前状态 {plan.status} 不可固定")

    overlaps = _overlapping_fixed_plans(db, user_id, plan)
    if overlaps and not req.replace:
        full = [o for o in overlaps if o["fully_covered"]]
        partial = [o for o in overlaps if not o["fully_covered"]]
        parts: list[str] = []
        if full:
            ids = ",".join(str(o["meal_plan_id"]) for o in full)
            parts.append(f"已有覆盖同期的已固定方案（id={ids}），替换会将其整份作废")
        for o in partial:
            parts.append(
                f"方案 {o['meal_plan_id']} 与本方案在 {o['overlap_start']}~{o['overlap_end']} "
                f"部分重叠，整份替换会让它其余日期一并失效"
            )
        raise BizError(
            BizCode.PLAN_STATE_CONFLICT,
            "；".join(parts) + "。",
            http_status=409,
        )

    slot_by_id = {s.meal_slot_id: s for s in plan.slots}
    for sel in req.selections or []:
        slot = slot_by_id.get(sel.meal_slot_id)
        if slot is None:
            raise BizError(BizCode.NOT_FOUND, f"餐位不存在: {sel.meal_slot_id}", http_status=404)
        if not any(c.candidate_id == sel.candidate_id for c in slot.candidates):
            raise BizError(
                BizCode.NOT_FOUND, f"候选不属于该餐位: {sel.candidate_id}", http_status=404
            )
        slot.selected_candidate_id = sel.candidate_id
    db.flush()

    missing = [s.meal_slot_id for s in plan.slots if s.selected_candidate_id is None]
    if missing:
        raise BizError(
            BizCode.PARAM_ERROR, f"存在未选候选的餐位，不能固定: {missing}"
        )

    for slot in plan.slots:
        _validate_saved(db, plan, slot, _selected_candidate(slot))
    plan.status = "fixed"
    try:
        db.flush()  # 触发器校验 + 自动补 fixed_at
    except Exception as exc:
        db.rollback()
        raise BizError(BizCode.PLAN_STATE_CONFLICT, f"固定失败: {exc}") from exc

    # 同步生成/刷新食材清单（一方案一清单）
    items = _shopping_items(db, plan)
    db.execute(
        text(
            "INSERT INTO app.shopping_list (meal_plan_id, items) "
            "VALUES (:pid, cast(:items AS jsonb)) "
            "ON CONFLICT (meal_plan_id) DO UPDATE "
            "SET items = EXCLUDED.items, updated_at = now()"
        ),
        {"pid": plan.meal_plan_id, "items": json.dumps(items, ensure_ascii=False)},
    )

    # 取代旧方案：把重叠的 fixed 方案标记为 superseded（fixed_at 清空以符合 check 约束）。
    # 完全覆盖与部分重叠统一整份取代——部分重叠时「其余日期一并失效」已在追问里如实告知。
    if overlaps:
        db.execute(
            text(
                "UPDATE app.meal_plan "
                "SET status = 'superseded', fixed_at = NULL, "
                "    superseded_at = now(), superseded_by_plan_id = :new_id "
                "WHERE meal_plan_id = ANY(:ids)"
            ),
            {"new_id": plan.meal_plan_id, "ids": [o["meal_plan_id"] for o in overlaps]},
        )

    db.commit()

    db.refresh(plan)
    return api_success(_serialize_plan(_get_plan(db, plan.meal_plan_id), db))


# ---------------------------------------------------------------- API-21 当前


@router.get("/current")
def current_plan(
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict | None]:
    """最近一个未删除方案（优先 fixed，其次 candidates）；无方案返回 null。"""
    for status in ("fixed", "candidates"):
        stmt = (
            select(MealPlan)
            .where(
                MealPlan.user_id == user_id,
                MealPlan.is_deleted.is_(False),
                MealPlan.status == status,
            )
            .order_by(MealPlan.created_at.desc(), MealPlan.meal_plan_id.desc())
            .limit(1)
            .options(
                selectinload(MealPlan.slots)
                .selectinload(MealSlot.candidates)
                .selectinload(MealCandidate.dishes)
            )
        )
        plan = db.execute(stmt).scalar_one_or_none()
        if plan is not None:
            return api_success(_serialize_plan(plan, db))
    return api_success(None)


# ---------------------------------------------------------------- API-05 列表


@router.get("/list")
def list_plans(
    user_id: str = CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[dict]]:
    """历史方案列表（API-05，摘要不含 slots）。"""
    if status is not None and status not in ("draft", "candidates", "fixed", "superseded"):
        raise BizError(BizCode.PARAM_ERROR, f"status 取值非法: {status}")

    where = "user_id = :uid AND is_deleted = false"
    params: dict = {"uid": user_id}
    if status:
        where += " AND status = :st"
        params["st"] = status

    total = db.execute(
        text(f"SELECT count(*) FROM app.meal_plan WHERE {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT meal_plan_id, plan_type, status, start_date, end_date, "
            "goal_energy_kcal, created_at, is_executed, "
            "generation_context->>'goal_code' AS goal_code FROM app.meal_plan "
            f"WHERE {where} ORDER BY created_at DESC, meal_plan_id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()

    items = [
        {
            "meal_plan_id": r["meal_plan_id"],
            "plan_type": r["plan_type"],
            "status": r["status"],
            "start_date": str(r["start_date"]),
            "end_date": str(r["end_date"]),
            "goal_energy_kcal": _f(r["goal_energy_kcal"]),
            "goal_code": r["goal_code"] or "",
            "is_executed": bool(r["is_executed"]),
            "created_at": _iso(r["created_at"]),
        }
        for r in rows
    ]
    return api_success(page_data(items, total=total, page=page, page_size=page_size))


# ---------------------------------------------------------------- API-04 详情


@router.get("/{plan_id}")
def get_plan(plan_id: int, user_id: str = CurrentUser, db: Session = Depends(get_db)) -> ApiResponse[dict]:
    """方案详情（API-04，含 slots / candidates / dishes）。"""
    plan = _get_plan(db, plan_id)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权查看他人方案", http_status=403)
    return api_success(_serialize_plan(plan, db))


# ---------------------------------------------------------------- API-26 执行标记


@router.post("/{plan_id}/executed")
def set_plan_executed(
    plan_id: int,
    req: ExecutedRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """标记方案「已执行 / 未执行」（历史回顾用，不改动方案状态机）。"""
    plan = _get_plan(db, plan_id)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权操作他人方案", http_status=403)
    plan.is_executed = req.executed
    db.commit()
    return api_success({"meal_plan_id": plan.meal_plan_id, "is_executed": plan.is_executed})


# ---------------------------------------------------------------- API-27 复用生成


@router.post("/{plan_id}/regenerate")
def regenerate_plan(
    plan_id: int,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """照某份历史方案「再排一个等长周期」（API-27）。

    复用原方案的 goal_code / 餐次 / 每餐候选数 / 排除食材，日期窗口顺延到
    原方案结束后下一个等长区间，并按当前档案重跑规则引擎，写 derived_from_plan_id。
    """
    source = _get_plan(db, plan_id)
    if source.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权操作他人方案", http_status=403)

    try:
        orig = json.loads(source.generation_request) if source.generation_request else {}
    except json.JSONDecodeError:
        orig = {}
    orig = orig or {}

    span = (source.end_date - source.start_date).days + 1
    new_start = source.end_date + timedelta(days=1)
    new_end = new_start + timedelta(days=span - 1)

    req = GenerateRequest(
        start_date=new_start,
        end_date=new_end,
        plan_type=orig.get("plan_type") or source.plan_type,
        meal_types=orig.get("meal_types") or ["早", "午", "晚"],
        candidates_per_slot=int(orig.get("candidates_per_slot") or 3),
        goal_code=orig.get("goal_code"),
        exclude_ingredients=orig.get("exclude_ingredients") or [],
    )

    plan = _generate_and_persist(db, user_id, req, derived_from_plan_id=plan_id)
    return api_success(_serialize_plan(_get_plan(db, plan.meal_plan_id), db))
