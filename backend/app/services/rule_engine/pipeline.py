"""五步算法编排：算目标 → 构造候选 → 差异化 → 跨日微量平衡 → 输出。

调用方式（API 层 / Agent 工具层）：
```python
from app.services.rule_engine import generate_plan, SqlDataSource

result = generate_plan(profile, request, SqlDataSource(db))
payload = result.as_dict()          # 直接映射 MealCard payload
```

设计要点：
- 只做计算，不写库；写库（meal_plan / meal_slot / meal_candidate）由接口层负责；
- 同一餐次的候选池只枚举一次，多日方案复用同一池（避免重复组合爆炸）；
- 硬约束（过敏原/宗教/忌口/厨具）永不放开；放宽只针对宏量区间，并且必须记入 notes；
- 每餐候选数目标 2~3，不足时说明原因（不静默降级）。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from .balance import apply_balance, build_micro_hints, compute_balance
from .candidates import build_candidates, diversify
from .errors import HardConstraintUnsatisfiable, InsufficientData
from .explain import build_why_summary, make_eating_order_advice, make_why_text
from .models import (
    Candidate,
    DishFacts,
    PlanRequest,
    PlanResult,
    Profile,
    SlotResult,
    Targets,
)
from .repository import RuleEngineDataSource
from .targets import compute_targets

__all__ = ["generate_plan", "plan_dates", "clone_candidate"]


# ---------------------------------------------------------------- 工具


def plan_dates(start: str, end: str, limit: int = 14) -> list[str]:
    """展开方案日期（最多 limit 天，超出的部分由上层说明）。"""
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except ValueError as exc:
        raise InsufficientData(f"日期格式非法：{start} ~ {end}") from exc
    if end_d < start_d:
        raise InsufficientData(f"结束日期早于开始日期：{start} ~ {end}")
    days = (end_d - start_d).days + 1
    if days > limit:
        days = limit
    return [(start_d + timedelta(days=i)).isoformat() for i in range(days)]


def clone_candidate(source: Candidate) -> Candidate:
    """复制候选（多日复用同一池时不共享可变状态）。"""
    return Candidate(
        candidate_id=0,
        rank=0,
        portions=list(source.portions),
        totals=dict(source.totals),
        oil_salt=dict(source.oil_salt),
        micro_estimate=dict(source.micro_estimate),
        score=source.score,
        reason_codes=list(source.reason_codes),
        notes=list(source.notes),
        signature=source.signature,
    )


def _split_dishes(dishes: Sequence[DishFacts]) -> tuple[list[DishFacts], list[DishFacts]]:
    staples = [d for d in dishes if d.is_staple]
    sides = [d for d in dishes if not d.is_staple]
    return staples, sides


def _template_pool(
    meal_type: str,
    target,
    staples: Sequence[DishFacts],
    sides: Sequence[DishFacts],
    targets: Targets,
    request: PlanRequest,
    diagnostics: dict,
) -> list[Candidate]:
    """为一餐枚举候选池；正常区间失败时逐级放宽（硬约束不放开）。"""
    pool = build_candidates(
        target,
        staples,
        sides,
        targets,
        max_candidates=60,
        soft_avoid=request.soft_avoid,
    )
    if pool:
        diagnostics.setdefault("relaxe_attempts", {})[meal_type] = "strict"
        return pool

    pool = build_candidates(
        target,
        staples,
        sides,
        targets,
        max_candidates=60,
        soft_avoid=request.soft_avoid,
        relaxed=True,
    )
    if not pool:
        raise HardConstraintUnsatisfiable(
            f"{meal_type}餐在现有菜式与硬约束下无可行候选",
            detail={
                "meal_type": meal_type,
                "dish_total": len(staples) + len(sides),
                "staples": len(staples),
                "sides": len(sides),
                "hint": "请检查过敏原/宗教忌口/排除食材/厨具过滤是否过严，或菜式库是否缺少该类菜品",
            },
        )
    diagnostics.setdefault("relaxe_attempts", {})[meal_type] = "macro_range_relaxed"
    diagnostics.setdefault("relaxe_notes", []).append(
        f"{meal_type}餐无候选严格落在宏量区间，已放宽区间取最接近组合（硬约束仍生效）"
    )
    return pool


def _fill_copy(candidate: Candidate, target, targets: Targets) -> Candidate:
    """补齐文案字段（确定性模板，不调 LLM）。"""
    if not candidate.why_text:
        candidate.why_text = make_why_text(candidate, target, targets)
    if not candidate.eating_order_advice:
        candidate.eating_order_advice = make_eating_order_advice(candidate)
    return candidate


# ---------------------------------------------------------------- 主流程


def generate_plan(
    profile: Profile,
    request: PlanRequest,
    data_source: RuleEngineDataSource,
    *,
    skip_balance: bool = False,
) -> PlanResult:
    """执行五步算法，返回可直接序列化为 MealCard 的结果对象。"""
    diagnostics: dict = {"relaxe_attempts": {}, "relaxe_notes": [], "slots": 0}

    # 1) 算目标
    goal_code = request.goal_code or profile.goal_code
    goal_row = data_source.get_goal_row(goal_code)
    # maintain 是库里唯一给全三项宏量占比的目标，用作结构基线给减脂/控糖/增肌补缺
    baseline_row = data_source.get_goal_row("maintain") if goal_code != "maintain" else None
    micro_rows = data_source.get_micro_reference_rows(profile)
    targets = compute_targets(profile, goal_row, micro_rows, request, baseline_row)

    # 2) 构造候选（按餐次建池）
    dishes = data_source.get_dish_facts()
    if not dishes:
        raise InsufficientData("菜式事实表为空，无法生成候选")
    staples, sides = _split_dishes(dishes)
    if not staples:
        raise InsufficientData(
            "未识别到主食类菜品（core.dish.category='主食' 或 tags 含「主食」），无法组餐",
            detail={"dish_total": len(dishes)},
        )
    if not sides:
        raise InsufficientData("除主食外没有可用菜品，无法组餐", detail={"dish_total": len(dishes)})

    diagnostics["catalog"] = {
        "dish_total": len(dishes),
        "staple_total": len(staples),
        "side_total": len(sides),
    }

    dates = plan_dates(request.start_date, request.end_date)
    if request.max_slots and len(dates) * len(request.meal_types) > request.max_slots:
        raise InsufficientData(
            f"餐位数超过上限 {request.max_slots}，请缩小日期范围或减少餐次",
            detail={"dates": len(dates), "meal_types": request.meal_types},
        )

    meal_order = [mt for mt in request.meal_types if mt in targets.meal_targets]
    if not meal_order:
        raise InsufficientData(
            "请求的餐次不在目标表中",
            detail={"requested": request.meal_types, "available": list(targets.meal_targets)},
        )

    templates: dict[str, list[Candidate]] = {}
    for meal_type in meal_order:
        templates[meal_type] = _template_pool(
            meal_type,
            targets.meal_targets[meal_type],
            staples,
            sides,
            targets,
            request,
            diagnostics,
        )

    # 3) 差异化：每餐挑 2~3 个候选
    slots: list[SlotResult] = []
    slot_notes: list[str] = []
    for slot_date in dates:
        # 同一天内跨餐去重：晚餐不重复用早餐的主菜（主食重复是可接受的）
        used_mains: set[str] = set()
        for index, meal_type in enumerate(meal_order):
            target = targets.meal_targets[meal_type]
            pool = [clone_candidate(c) for c in templates[meal_type]]
            fresh = [c for c in pool if c.signature[0] not in used_mains]
            fresh_mains = {c.signature[0] for c in fresh}
            need = max(2, int(request.candidates_per_slot))
            if len(fresh_mains) >= need:
                # 未重复的主菜种类足够，整餐都用新主菜
                pool = fresh
            else:
                # 主菜种类不够：保留未重复主菜优先，再补已用主菜，并如实记一条说明
                if fresh_mains:
                    slot_notes.append(
                        f"{slot_date} {meal_type}餐当天未重复的主菜只有 {len(fresh_mains)} 种"
                        f"（目标 {need} 种），跨餐存在主菜重复"
                    )
                pool = fresh + [c for c in pool if c.signature[0] in used_mains]
            picked = diversify(pool, request.candidates_per_slot, start_id=1)
            used_mains |= {c.signature[0] for c in picked}
            for cand in picked:
                _fill_copy(cand, target, targets)
            if len(picked) < 2:
                slot_notes.append(
                    f"{slot_date} {meal_type}餐仅生成 {len(picked)} 个差异化候选（目标 2~3），"
                    "原因为通过区间与硬约束的组合不足"
                )
            slots.append(
                SlotResult(
                    meal_type=meal_type,
                    slot_date=slot_date,
                    display_order=index + 1,
                    target=target,
                    candidates=picked,
                    selected_candidate_id=picked[0].candidate_id if picked else None,
                )
            )
            diagnostics["slots"] += 1

    # 4) 跨日微量平衡
    balance = None
    hints: list[str] = []
    if not skip_balance and request.user_id:
        window_rows = data_source.get_micro_window(
            request.user_id, request.start_date, request.end_date
        )
        balance = compute_balance(
            targets,
            window_rows,
            window_days=request.window_days,
            window_start=request.start_date,
            window_end=request.end_date,
        )
        improvements = apply_balance(slots, balance)
        balance.improvements.extend(improvements)
        hints = build_micro_hints(balance)

        # 重排说明写进被调整候选的 notes，便于前端解释「为什么换了首选」
        for slot in slots:
            note = next(
                (i for i in improvements if i.startswith(f"{slot.meal_type}：")), None
            )
            if not note:
                continue
            for cand in slot.candidates:
                if cand.candidate_id == slot.selected_candidate_id:
                    cand.reason_codes = sorted(set(cand.reason_codes) | {"micro_balance_adjusted"})
                    cand.notes.append(note)

    # 5) 输出
    data_notes: list[str] = []
    missing_fat = sum(1 for d in dishes if d.fat_g is None)
    missing_carb = sum(1 for d in dishes if d.carb_g is None)
    missing_fiber = sum(1 for d in dishes if d.fiber_g is None)
    missing_ca = sum(1 for d in dishes if d.calcium_mg is None)
    if missing_fat or missing_carb:
        data_notes.append(
            f"{max(missing_fat, missing_carb)}/{len(dishes)} 道菜的脂肪或碳水聚合值为空，"
            "相关宏量按「缺失」处理，未按 0 计"
        )
    if missing_fiber:
        data_notes.append(
            f"{missing_fiber}/{len(dishes)} 道菜的膳食纤维聚合值为空，纤维覆盖进度不可判定"
        )
    if missing_ca:
        data_notes.append(f"{missing_ca}/{len(dishes)} 道菜缺钙数据，钙的覆盖进度不可判定")
    unverified = [d.name for d in dishes if d.allergen_unverified]
    if unverified:
        data_notes.append(
            f"{len(unverified)} 道菜含 allergen_status=未核查 的食材，候选卡片需保留提示"
            f"（示例：{'、'.join(unverified[:3])}）"
        )
    data_notes.extend(slot_notes)
    data_notes.extend(diagnostics["relaxe_notes"])

    status = "candidates" if all(s.candidates for s in slots) else "draft"
    if status != "candidates":
        data_notes.append("存在餐位无候选，方案停留在 draft，需放宽条件后重试")

    notes_for_summary = hints or []
    result = PlanResult(
        plan_type=request.plan_type,
        start_date=request.start_date,
        end_date=request.end_date,
        status=status,
        targets=targets,
        slots=slots,
        balance=balance,
        why_summary=build_why_summary(slots, notes_for_summary),
        reference_hints=hints,
        data_quality_notes=data_notes,
        diagnostics={**diagnostics, "dates": dates},
    )
    return result
