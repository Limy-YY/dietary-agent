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
from datetime import date
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


def _get_plan(db: Session, meal_plan_id: int) -> MealPlan:
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
    plan = db.execute(stmt).scalar_one_or_none()
    if plan is None:
        raise BizError(BizCode.NOT_FOUND, f"方案不存在: {meal_plan_id}", http_status=404)
    return plan


def _serialize_candidate(c: MealCandidate) -> dict:
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


def _serialize_slot(slot: MealSlot) -> dict:
    picked = _selected_candidate(slot)
    return {
        "meal_slot_id": slot.meal_slot_id,
        "slot_date": str(slot.slot_date),
        "meal_type": slot.meal_type,
        "display_order": slot.display_order,
        "target_macro": slot.target_macro or {},
        "selected_candidate_id": slot.selected_candidate_id,
        "selected_candidate": _serialize_candidate(picked) if picked else None,
        "candidates": [_serialize_candidate(c) for c in slot.candidates],
    }


def _serialize_plan(plan: MealPlan) -> dict:
    return {
        "meal_plan_id": plan.meal_plan_id,
        "user_id": plan.user_id,
        "plan_type": plan.plan_type,
        "status": plan.status,
        "plan_date": str(plan.plan_date),
        "start_date": str(plan.start_date),
        "end_date": str(plan.end_date),
        "goal_energy_kcal": _f(plan.goal_energy_kcal),
        "macro_ratio": plan.macro_ratio or {},
        "generation_context": plan.generation_context or {},
        "micro_balance_window_start": _iso(plan.micro_balance_window_start),
        "micro_balance_window_end": _iso(plan.micro_balance_window_end),
        "agent_version": plan.agent_version,
        "data_version": plan.data_version,
        "fixed_at": _iso(plan.fixed_at),
        "created_at": _iso(plan.created_at),
        "updated_at": _iso(plan.updated_at),
        "slots": [_serialize_slot(s) for s in sorted(plan.slots, key=lambda x: (x.slot_date, x.display_order))],
    }


def _persist_plan(
    db: Session,
    user_id: str,
    request: GenerateRequest,
    plan_type: str,
    result,
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
        macro_ratio=result.targets.as_dict().get("macro_ratio") or {},
        meals={},
        sources={"rule_engine": "v1.2", "goal_code": result.targets.goal_code},
        generation_request=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
        generation_context={
            "goal_code": result.targets.goal_code,
            "diagnostics": result.diagnostics,
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

    plan.status = "candidates"
    db.flush()
    return plan


# ---------------------------------------------------------------- API-22 生成


@router.post("/week/generate")
def generate_week_plan(
    req: GenerateRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """生成用户自定范围的方案（API-22）。"""
    if req.end_date < req.start_date:
        raise BizError(BizCode.PARAM_ERROR, "end_date 不能早于 start_date")
    span = (req.end_date - req.start_date).days + 1
    if span > MAX_SPAN_DAYS:
        raise BizError(BizCode.PARAM_ERROR, f"日期跨度上限 {MAX_SPAN_DAYS} 天，当前 {span} 天")
    if not req.meal_types:
        raise BizError(BizCode.PARAM_ERROR, "meal_types 不能为空")
    bad = [m for m in req.meal_types if m not in VALID_MEAL_TYPES]
    if bad:
        raise BizError(BizCode.PARAM_ERROR, f"meal_types 取值非法: {bad}")

    plan_type = req.plan_type or _derived_plan_type(req.start_date, req.end_date, req.meal_types)
    if plan_type not in VALID_PLAN_TYPES:
        raise BizError(BizCode.PARAM_ERROR, f"plan_type 取值非法: {plan_type}")

    profile = _load_engine_profile(db, user_id)
    engine_request = PlanRequest(
        start_date=req.start_date.isoformat(),
        end_date=req.end_date.isoformat(),
        plan_type=plan_type,
        meal_types=req.meal_types,
        candidates_per_slot=req.candidates_per_slot,
        goal_code=req.goal_code,
        user_id=user_id,
        exclude_ingredients=req.exclude_ingredients,
        max_slots=span * len(req.meal_types),  # 引擎默认 21 餐位，按实际跨度放宽
    )

    try:
        result = generate_plan(profile, engine_request, SqlDataSource(db))
    except RuleEngineError as exc:
        raise BizError(BizCode.PLAN_GENERATION_FAILED, f"方案生成失败: {exc}") from exc
    except Exception as exc:  # 兜底：数据或算法异常统一归 2006，避免 500 裸抛
        raise BizError(BizCode.CALC_FAILED, f"方案生成异常: {exc}") from exc

    try:
        plan = _persist_plan(db, user_id, req, plan_type, result)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise BizError(BizCode.PLAN_GENERATION_FAILED, f"方案落库失败: {exc}") from exc

    return api_success(_serialize_plan(_get_plan(db, plan.meal_plan_id)))


# ---------------------------------------------------------------- API-23 换候选


def _macro_delta(new: dict, old: dict) -> dict:
    """相对原候选的宏量/微量变化（None 不参与相减）。"""
    out: dict = {}
    for key in ("kcal", "protein_g", "fat_g", "carb_g", "fiber_g"):
        a, b = new.get(key), old.get(key)
        out[key] = round(float(a) - float(b), 1) if a is not None and b is not None else None
    return out


@router.post("/candidate/swap")
def swap_candidate(
    req: SwapRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """替换某个餐位的选中候选（API-23），并写一条 plan_adjustment 留痕。"""
    plan = _get_plan(db, req.meal_plan_id)
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
        others = [c for c in slot.candidates if c.candidate_id != previous_id]
        if not others:
            raise BizError(BizCode.PARAM_ERROR, "该餐位没有其他可选候选")
        target = others[0]

    if target.candidate_id == previous_id:
        raise BizError(BizCode.PARAM_ERROR, "该候选已是当前选中，无需替换")

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
            "candidate": _serialize_candidate(target),
            "macro_delta": delta,
        }
    )


# ---------------------------------------------------------------- API-24 固定


def _shopping_items(db: Session, plan: MealPlan) -> list[dict]:
    """按选中候选汇总食材（库内平铺，分组留给返回层）。"""
    agg: dict[str, dict] = {}
    for slot in plan.slots:
        cand = _selected_candidate(slot)
        if cand is None:
            continue
        for d in cand.dishes:
            item = agg.setdefault(
                d.dish_id,
                {"dish_id": d.dish_id, "servings": 0.0, "meal_types": set()},
            )
            item["servings"] += float(d.servings or 0)
            item["meal_types"].add(slot.meal_type)

    rows = db.execute(
        text("SELECT dish_id, name, category FROM core.dish WHERE dish_id = ANY(:ids)"),
        {"ids": list(agg)},
    ).mappings().all()
    meta = {r["dish_id"]: r for r in rows}

    items = []
    for dish_id, item in agg.items():
        info = meta.get(dish_id, {})
        items.append(
            {
                "dish_id": dish_id,
                "name": info.get("name") or dish_id,
                "category": info.get("category") or "未分类",
                "servings": round(item["servings"], 2),
                "meal_types": sorted(item["meal_types"]),
            }
        )
    return sorted(items, key=lambda x: (x["category"], x["dish_id"]))


@router.post("/week/fix")
def fix_plan(
    req: FixRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """固定方案（API-24），成功后同步刷新食材清单。"""
    plan = _get_plan(db, req.meal_plan_id)
    if plan.user_id != user_id:
        raise BizError(BizCode.FORBIDDEN, "无权操作他人方案", http_status=403)
    if plan.status == "fixed":
        raise BizError(BizCode.PLAN_STATE_CONFLICT, "方案已固定，不可重复固定")
    if plan.status != "candidates":
        raise BizError(BizCode.PLAN_STATE_CONFLICT, f"当前状态 {plan.status} 不可固定")

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
    db.commit()

    db.refresh(plan)
    return api_success(_serialize_plan(_get_plan(db, plan.meal_plan_id)))


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
            return api_success(_serialize_plan(plan))
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
    if status is not None and status not in ("draft", "candidates", "fixed"):
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
            "goal_energy_kcal, created_at FROM app.meal_plan "
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
    return api_success(_serialize_plan(plan))
