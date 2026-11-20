"""五步算法编排：算目标 → 构造候选 → 差异化 → 跨日微量平衡 → 输出。

调用方式（API 层 / Agent 工具层）：
```python
from app.services.rule_engine import generate_plan, SqlDataSource

result = generate_plan(profile, request, SqlDataSource(db))
payload = result.as_dict()          # 直接映射 MealCard payload
```

设计要点：
- 只做计算，不写库；写库（meal_plan / meal_slot / meal_candidate）由接口层负责；
- 同一餐次的候选池只枚举一次，多日方案复用同一池（避免重复组合爆炸），
  但第 3 步对主菜做「当天跨餐 + 同餐跨日」两级去重，让多日方案一周不重样；
- 硬约束（过敏原/宗教/忌口/厨具）永不放开；放宽只针对宏量区间，并且必须记入 notes；
- 每餐候选数目标 2~3，不足时说明原因（不静默降级）。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
import hashlib
import random

from .balance import apply_balance, build_micro_hints, compute_balance
from .candidates import build_candidates, diversify, hard_filter_reasons, hard_budget_failures
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
from .quality import dish_roles, repetition_cost, selected
from .meal_templates import (
    non_staple_base_ids,
    profile as culinary_profile,
    template_for,
    selection_key,
)

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
        score_breakdown=dict(source.score_breakdown),
        reason_codes=list(source.reason_codes),
        notes=list(source.notes),
        signature=source.signature,
    )


def _split_dishes(dishes: Sequence[DishFacts]) -> tuple[list[DishFacts], list[DishFacts]]:
    staples = [d for d in dishes if "主食" in dish_roles(d)]
    sides = [d for d in dishes if "主食" not in dish_roles(d)]
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
    """为一餐枚举候选池；正常区间失败仅额外尝试一次。"""
    filter_counts = {}
    for dish in [*staples, *sides]:
        for reason in hard_filter_reasons(dish, targets):
            filter_counts[reason] = filter_counts.get(reason, 0) + 1
    diagnostics.setdefault("dish_filter_reasons", {})[meal_type] = filter_counts
    from collections import Counter
    from .practical_quality import candidate_priority
    real=any(getattr(d,'ingredient_amounts',None) for d in [*staples,*sides])
    strict_stats=Counter(); relaxed_stats=Counter()
    diagnostics.setdefault('candidate_search',{})[meal_type]={'strict':strict_stats,'expanded':relaxed_stats}
    pool = build_candidates(
        target,
        staples,
        sides,
        targets,
        max_candidates=120,
        soft_avoid=request.soft_avoid, diagnostics=strict_stats,
    )
    need = max(1, min(3, request.candidates_per_slot))
    strict_pool = pool

    # A narrow strict pool can satisfy count yet lack genuinely different meals.
    if (len({c.signature[0] for c in strict_pool}) >= need
            and len(strict_pool) >= need * 3
            and (not real or sum(candidate_priority(c)[:2]==(False,0) for c in strict_pool)>=need*8)):
        diagnostics.setdefault("relax_attempts", {})[meal_type] = "strict"
        return strict_pool

    relaxed_pool = build_candidates(
        target,
        staples,
        sides,
        targets,
        max_candidates=120,
        soft_avoid=request.soft_avoid,
        relaxed=True, diagnostics=relaxed_stats,extend=real,
    )

    if not strict_pool and not relaxed_pool:
        raise HardConstraintUnsatisfiable(
            f"{meal_type}餐无合法候选",
            detail={
                "meal_type": meal_type,
                "dish_filter_reasons": filter_counts,
                "relaxed_attempts": 1,
            },
        )

    seen = {tuple(sorted(c.dish_ids)) for c in strict_pool}
    combined = list(strict_pool)

    for candidate in relaxed_pool:
        key = tuple(sorted(candidate.dish_ids))
        if key not in seen:
            combined.append(candidate)
            seen.add(key)

    diagnostics.setdefault("relax_attempts", {})[meal_type] = (
        "strict_with_supplement" if strict_pool else "macro_range_relaxed"
    )
    diagnostics.setdefault("relax_notes", []).append(
        f"{meal_type}餐严格候选不足，额外尝试一次补充候选；硬约束不放宽"
    )
    return combined


def _fill_copy(candidate: Candidate, target, targets: Targets) -> Candidate:
    """补齐文案字段（确定性模板，不调 LLM）。"""
    if not candidate.why_text:
        candidate.why_text = make_why_text(candidate, target, targets)
    if not candidate.eating_order_advice:
        candidate.eating_order_advice = make_eating_order_advice(candidate)
    return candidate


def _vary_equivalent_pool(pool, target, same_day, seed, slot_date, meal_type):
    """Shuffle only a near-best equivalent band, never the whole candidate pool."""
    if seed is None or len(pool) < 2:
        return pool
    from .practical_quality import candidate_priority
    best = pool[0]
    best_priority = candidate_priority(best)[:3]
    best_deviation = abs(best.totals['kcal']-target.kcal)/max(target.kcal,1)
    best_band = 0 if best_deviation<=.15 else 1 if best_deviation<=.25 else 2 if best_deviation<=.40 else 3
    used = set().union(*(non_staple_base_ids(c) for c in same_day)) if same_day else set()
    best_overlap = bool(non_staple_base_ids(best)&used)
    equivalent=[]
    for candidate in pool[:24]:
        deviation=abs(candidate.totals['kcal']-target.kcal)/max(target.kcal,1)
        band=0 if deviation<=.15 else 1 if deviation<=.25 else 2 if deviation<=.40 else 3
        if (candidate_priority(candidate)[:3]==best_priority and band==best_band
                and bool(non_staple_base_ids(candidate)&used)==best_overlap
                and candidate.score<=best.score+.30):
            equivalent.append(candidate)
    if len(equivalent)<2:
        return pool
    material=f'{seed}:{slot_date}:{meal_type}'.encode()
    slot_seed=int.from_bytes(hashlib.sha256(material).digest()[:8],'big')
    random.Random(slot_seed).shuffle(equivalent)
    chosen={id(c) for c in equivalent}
    return [*equivalent,*(c for c in pool if id(c) not in chosen)]


# ---------------------------------------------------------------- 主流程


def generate_plan(
    profile: Profile,
    request: PlanRequest,
    data_source: RuleEngineDataSource,
    *,
    skip_balance: bool = False,
) -> PlanResult:
    """执行五步算法，返回可直接序列化为 MealCard 的结果对象。"""
    diagnostics: dict = {"relax_attempts": {}, "relax_notes": [], "slots": 0}

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

    from time import perf_counter
    _quality_started = perf_counter()
    diagnostics["role_mapping"] = {d.dish_id: sorted(dish_roles(d)) for d in dishes}
    diagnostics["catalog_review_pending"] = [d.dish_id for d in dishes if not culinary_profile(d).reviewed]
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

    # 3) 差异化：每餐挑 2~3 个候选；主菜做两级去重——
    # ① 当天跨餐：晚餐不重复当天早餐/午餐的主菜（主食重复是可接受的）；
    # ② 同餐跨日：同一餐次在窗口内尽量不重复「首选」主菜，让多日方案一周不重样。
    slots: list[SlotResult] = []
    slot_notes: list[str] = []
    for slot_date in dates:
        for index, meal_type in enumerate(meal_order):
            target = targets.meal_targets[meal_type]
            pool = [clone_candidate(c) for c in templates[meal_type]]
            previous = [c for s in slots if (c := selected(s)) is not None]
            today = [c for s in slots if s.slot_date == slot_date and (c := selected(s)) is not None]
            today_slots = [s for s in slots if s.slot_date == slot_date and selected(s) is not None]
            daily_energy_carry = sum(s.target.kcal-selected(s).totals['kcal'] for s in today_slots
                                     if selected(s).totals.get('kcal') is not None)
            # Breakfast protein must influence lunch/dinner rotation as well;
            # otherwise egg can become the main protein in all three meals.
            # Keep earlier lunch/dinner history for multi-day rotation too.
            protein_previous = [c for s in slots
                                if (s.slot_date == slot_date or s.meal_type in ("午", "晚"))
                                and (c := selected(s)) is not None]
            pool.sort(key=lambda c: selection_key(c, target, previous,
                repetition_cost(c, previous),
                protein_previous=protein_previous,daily_energy_carry=daily_energy_carry,
                same_day=today))
            pool = _vary_equivalent_pool(
                pool, target, today, request.variation_seed, slot_date, meal_type
            )
            picked = diversify(pool, request.candidates_per_slot, start_id=1)
            from .practical_quality import protein_rotation, purchase_credit, candidate_priority
            for c in picked:
                used_today = set().union(*(non_staple_base_ids(x) for x in today)) if today else set()
                c.score_breakdown['context']={'repetition':round(repetition_cost(c,previous),4),
                    'protein_rotation':round(protein_rotation(c,protein_previous),4) if meal_type in ('午','晚') else 0.,
                    'purchase_credit':round(purchase_credit(c,previous),4),
                    'daily_energy_carry_kcal':round(daily_energy_carry,2),
                    'same_day_non_staple_overlap':sorted(non_staple_base_ids(c)&used_today),
                    'structure_tier':candidate_priority(c)[1]}
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
                (i for i in improvements if i.startswith(f"{slot.slot_date} {slot.meal_type}：")), None
            )
            if not note:
                continue
            for cand in slot.candidates:
                if cand.candidate_id == slot.selected_candidate_id:
                    cand.reason_codes = sorted(set(cand.reason_codes) | {"micro_balance_adjusted"})
                    cand.notes.append(note)

    # Final selected results cannot bypass the same safety checks used during generation.
    chosen = []
    for slot in slots:
        for candidate in slot.candidates:
            from .portion_policy import breakfast_shape
            from .practical_quality import meal_options
            if (not template_for([p.facts for p in candidate.portions], slot.meal_type)
                    or not breakfast_shape(candidate.portions, slot.meal_type)
                    or any(p.servings not in meal_options(p.facts,slot.target) for p in candidate.portions)):
                raise HardConstraintUnsatisfiable("候选未通过餐次组合质量检查")
            if any(hard_filter_reasons(p.facts, targets) for p in candidate.portions) or hard_budget_failures(slot.target, candidate.portions):
                raise HardConstraintUnsatisfiable("候选未通过硬约束校验")
        cand = selected(slot)
        if cand is None:
            raise HardConstraintUnsatisfiable("餐位无合法首选")
        if any(hard_filter_reasons(p.facts, targets) for p in cand.portions) or hard_budget_failures(slot.target, cand.portions):
            raise HardConstraintUnsatisfiable("最终候选未通过硬约束校验")
        if cand.totals.get("kcal") is None:
            raise InsufficientData("最终候选缺失能量数据")
        chosen.append(cand)
    from collections import Counter
    counts = Counter(d for c in chosen for d in c.dish_ids)
    meal_counts = Counter(tuple(sorted(c.dish_ids)) for c in chosen)
    diagnostics["diversity"] = {"unique_dishes": len(counts),
                                 "max_dish_occurrences": max(counts.values(), default=0),
                                 "repeated_meals": sum(n - 1 for n in meal_counts.values()),
                                 "dish_counts": dict(counts)}
    from .practical_quality import plan_quality_diagnostics
    diagnostics["practical_quality"] = plan_quality_diagnostics(slots)
    diagnostics["practical_quality"]["engine_seconds_after_catalog"] = round(perf_counter()-_quality_started,3)
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
    data_notes.extend(diagnostics["relax_notes"])

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
