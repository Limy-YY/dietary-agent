"""第 2、3 步：构造候选 + 候选差异化。

构造规则（任务书 v1.2 模块 A 第 2 步）：
- 一餐 = 1 道主食 + 1~2 道菜（汤羹最多 1 道）；
- 硬排除：过敏原（strict_allergens 与用户过敏交集）、宗教/伦理忌口、本次显式排除的食材；
- 软排除：偏好类食材命中只扣分不排除；
- 做法过滤：做法需要指定厨具而档案里没有该厨具时排除（档案未填厨具则不做该过滤）；
- 油盐限额：合计 `default_oil_g` / `default_salt_g` 不得超出该餐限额；
- 宏量区间：能量必须有值且落在 kcal 区间（±容差），蛋白/脂肪/碳水落在各自区间；
- 缺失值：任一宏量为 None 时不判「符合」，扣分并打 `partial_data` 标记（null ≠ 0）。

差异化（第 3 步）：同餐 2~3 个候选，以「换主食材 / 换做法」区分——
用 signature = (主菜 dish_id, 主菜做法) 去重，再退化到「整组 dish_id 不重复」，保证候选间主菜不同。
"""
from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from typing import Any

from .models import (
    DEFAULT_MACRO_TOLERANCE,
    KEY_MICRONUTRIENTS,
    METHOD_EQUIPMENT,
    MICRO_IDS,
    RELIGIOUS_KEYWORDS,
    Candidate,
    DishFacts,
    DishPortion,
    MealTarget,
    Targets,
)

__all__ = [
    "hard_filter_reasons",
    "build_candidates",
    "diversify",
    "sum_or_none",
    "combo_totals",
]

#: 能量预筛的宽松系数（先粗筛再精算，避免组合爆炸）
_KCAL_PRECHECK_LOW = 0.55
_KCAL_PRECHECK_HIGH = 1.65

#: 打分权重
_W_DEVIATION = 1.0
_W_MICRO_BONUS = 0.35
_W_OIL_SALT = 2.0
#: 收紧目标下用油贴近上限的附加扣分（只影响排序，不判淘汰）
_W_OIL_TIGHTENED = 0.15
_W_INCOMPLETE = 0.6
_W_SOFT_AVOID = 0.4


def sum_or_none(values: Iterable[float | None]) -> float | None:
    """求和；任一为 None 则整体为 None（避免把缺失当 0）。"""
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += float(value)
    return total


def hard_filter_reasons(
    facts: DishFacts,
    targets: Targets,
    soft_avoid: Sequence[str] = (),
) -> list[str]:
    """返回硬排除原因列表；空列表表示放行。"""
    reasons: list[str] = []
    name_blob = " ".join([facts.name or "", *[str(n) for n in facts.ingredient_names]])

    # 1) 过敏原（strict_allergens 为「已确认含」）
    for allergen in targets.hard_allergens:
        if allergen and allergen in (facts.strict_allergens or []):
            reasons.append(f"allergen:{allergen}")

    # 2) 宗教 / 伦理忌口
    for taboo in targets.hard_religious:
        keywords = _match_religious_keywords(taboo)
        if not keywords:
            continue
        if any(kw in name_blob for kw in keywords):
            reasons.append(f"religious:{taboo}")

    # 3) 本次显式排除的食材
    for excluded in targets.excluded_ingredients:
        if not excluded:
            continue
        if excluded in name_blob:
            reasons.append(f"excluded:{excluded}")

    # 4) 做法所需厨具：档案填了厨具但无一满足该做法 → 硬排除
    equipment = [str(e) for e in (targets.equipment or [])]
    if equipment:
        required = _required_equipment(facts.method_text)
        if required and not any(req in equipment for req in required):
            reasons.append(f"equipment:{facts.method_text}")

    # 5) 软排除只记录、不排除（由打分处理）
    for avoid in soft_avoid:
        if avoid and avoid in name_blob:
            reasons.append(f"soft_avoid:{avoid}")

    return reasons


def _match_religious_keywords(taboo: str) -> tuple[str, ...]:
    taboo_text = str(taboo or "").strip()
    if not taboo_text:
        return ()
    for key, keywords in RELIGIOUS_KEYWORDS.items():
        if key in taboo_text:
            return keywords
    return ()


def _required_equipment(method_text: str | None) -> tuple[str, ...]:
    """按做法文本推断所需厨具；无法判断时返回空（不做过滤）。"""
    if not method_text:
        return ()
    text = str(method_text)
    for key, equipment in METHOD_EQUIPMENT.items():
        if key in text:
            return equipment
    return ()


def combo_totals(portions: Sequence[DishPortion]) -> dict[str, float | None]:
    """按份量汇总一道候选的宏量与油盐糖（None 传播）。"""
    totals: dict[str, float | None] = {}
    for key in ("kcal", "protein_g", "fat_g", "carb_g", "fiber_g", "sodium_mg", "calcium_mg"):
        source_attr = "energy_kcal" if key == "kcal" else key
        values = []
        for p in portions:
            raw = getattr(p.facts, source_attr)
            values.append(None if raw is None else float(raw) * p.servings)
        totals[key] = round(v, 1) if (v := sum_or_none(values)) is not None else None

    for key in ("oil_g", "salt_g"):
        attr = "default_oil_g" if key == "oil_g" else "default_salt_g"
        values = []
        for p in portions:
            raw = getattr(p.facts, attr)
            values.append(None if raw is None else float(raw) * p.servings)
        totals[key] = round(v, 2) if (v := sum_or_none(values)) is not None else None

    return totals


def _micro_totals(portions: Sequence[DishPortion]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for nutrient_id in MICRO_IDS:
        values = []
        for p in portions:
            raw = (p.facts.micro or {}).get(nutrient_id)
            values.append(None if raw is None else float(raw) * p.servings)
        total = sum_or_none(values)
        out[nutrient_id] = round(total, 2) if total is not None else None
    return out


def _within(target: MealTarget, totals: dict[str, float | None]) -> tuple[bool, list[str]]:
    """判定是否落在该餐区间；返回 (是否通过, 失败原因)。"""
    failures: list[str] = []

    kcal = totals.get("kcal")
    if kcal is None:
        failures.append("kcal_missing")
    else:
        # 能量用 ±容差区间（kcal 目标即 target），容差取全局常量
        low = target.kcal * (1 - DEFAULT_MACRO_TOLERANCE)
        high = target.kcal * (1 + DEFAULT_MACRO_TOLERANCE)
        if not (low <= kcal <= high):
            failures.append(f"kcal_out:{kcal:g}")

    for key, rng in (("protein_g", target.protein), ("fat_g", target.fat), ("carb_g", target.carb)):
        verdict = rng.contains(totals.get(key))
        if verdict is False:
            failures.append(f"{key}_out:{totals.get(key):g}")
        elif verdict is None:
            failures.append(f"{key}_missing")

    oil = totals.get("oil_g")
    if oil is not None and oil > target.oil_limit_g + 0.01:
        failures.append(f"oil_over:{oil:g}>{target.oil_limit_g:g}")
    salt = totals.get("salt_g")
    if salt is not None and salt > target.salt_limit_g + 0.01:
        failures.append(f"salt_over:{salt:g}>{target.salt_limit_g:g}")

    return (not failures, failures)


def _score(
    target: MealTarget,
    totals: dict[str, float | None],
    micro: dict[str, float | None],
    targets: Targets,
    soft_hits: int,
    facts_list: Sequence[DishFacts],
) -> tuple[float, list[str], list[str]]:
    """打分：越小越好；同时返回 reason_codes 与 notes。"""
    reason_codes: list[str] = []
    notes: list[str] = []

    deviations: list[float] = []
    kcal_dev = None
    if totals.get("kcal") is not None and target.kcal > 0:
        kcal_dev = abs(totals["kcal"] - target.kcal) / target.kcal
        deviations.append(kcal_dev)
    for key, rng in (("protein_g", target.protein), ("fat_g", target.fat), ("carb_g", target.carb)):
        dev = rng.deviation(totals.get(key))
        if dev is not None:
            deviations.append(dev)
    deviation = sum(deviations) / len(deviations) if deviations else 1.0

    # 微量覆盖加分（目标缺失的项不计入）
    coverage_values: list[float] = []
    for nutrient_id, _, _ in KEY_MICRONUTRIENTS:
        ref = targets.micro_targets.get(nutrient_id)
        if ref is None or ref.value is None or ref.value <= 0:
            continue
        intake = micro.get(nutrient_id)
        if intake is None:
            continue
        coverage_values.append(min(1.0, intake / ref.value))
    coverage = sum(coverage_values) / len(coverage_values) if coverage_values else 0.0
    if coverage >= 0.12:
        reason_codes.append("micro_coverage_high")

    # 油盐惩罚（库内策略为「收紧」时加倍，但不改数值上限）
    penalty = 0.0
    strict_weight = _W_OIL_SALT * (2.0 if targets.oil_salt_strict else 1.0)
    oil = totals.get("oil_g")
    if oil is not None and target.oil_limit_g > 0:
        penalty += max(0.0, (oil - target.oil_limit_g) / target.oil_limit_g) * strict_weight
    salt = totals.get("salt_g")
    if salt is not None and target.salt_limit_g > 0:
        penalty += max(0.0, (salt - target.salt_limit_g) / target.salt_limit_g) * strict_weight
    if targets.oil_salt_strict and oil is not None and target.oil_limit_g > 0:
        # 收紧目标下，用油越接近上限扣分越明显（只影响排序，不判淘汰）
        penalty += _W_OIL_TIGHTENED * (oil / target.oil_limit_g)
        reason_codes.append("oil_salt_tightened")

    incomplete = any(totals.get(k) is None for k in ("protein_g", "fat_g", "carb_g"))
    incomplete_penalty = _W_INCOMPLETE if incomplete else 0.0
    if incomplete:
        reason_codes.append("partial_data")

    # 结构特征码（供 why_text 与前端标签使用）
    staples = [f for f in facts_list if f.is_staple]
    sides = [f for f in facts_list if not f.is_staple]
    if sides and all((s.method_text or "").strip() in {"清蒸", "蒸", "凉拌"} for s in sides):
        reason_codes.append("low_oil_method")
    if len(sides) == 2:
        reason_codes.append("veg_plus_protein")
    for f in facts_list:
        if "低盐" in (f.tags or []):
            reason_codes.append("low_salt")
            break
    if staples and staples[0].category == "主食":
        reason_codes.append("staple_anchored")

    # 过敏原未核查提示（不排除，必须保留提示）
    if any(f.allergen_unverified for f in facts_list):
        notes.append("含 allergen_status=未核查 的食材，不能表述为「安全」")

    if any(totals.get(k) is None for k in ("kcal", "protein_g", "fat_g", "carb_g")):
        notes.append("部分营养值缺失，未按 0 处理")

    score = (
        deviation * _W_DEVIATION
        + penalty
        + incomplete_penalty
        + soft_hits * _W_SOFT_AVOID
        - coverage * _W_MICRO_BONUS
    )
    return score, reason_codes, notes


def _soft_avoid_hits(facts: DishFacts, soft_avoid: Sequence[str]) -> int:
    if not soft_avoid:
        return 0
    blob = " ".join([facts.name or "", *map(str, facts.ingredient_names)])
    return sum(1 for item in soft_avoid if item and item in blob)


def _prefilter(
    staples: Sequence[DishFacts],
    sides: Sequence[DishFacts],
    target: MealTarget,
) -> tuple[list[DishFacts], list[DishFacts]]:
    """按单道菜能量做宽松预筛，缩小组合空间（不影响最终区间判定）。"""
    low = target.kcal * _KCAL_PRECHECK_LOW
    high = target.kcal * _KCAL_PRECHECK_HIGH

    def ok_kcal(f: DishFacts, share: float) -> bool:
        if f.energy_kcal is None:
            return True  # 缺失值不预筛，交给精算阶段判定
        return f.energy_kcal * share <= high

    keep_staples = [f for f in staples if ok_kcal(f, 1.0)]
    keep_sides = [f for f in sides if ok_kcal(f, 1.0)]
    if not keep_staples:
        keep_staples = list(staples)
    if not keep_sides:
        keep_sides = list(sides)
    return keep_staples, keep_sides


def build_candidates(
    target: MealTarget,
    staples: Sequence[DishFacts],
    sides: Sequence[DishFacts],
    targets: Targets,
    max_candidates: int = 40,
    soft_avoid: Sequence[str] = (),
    servings: float = 1.0,
    relaxed: bool = False,
) -> list[Candidate]:
    """枚举「主食 + 1~2 道菜」组合，返回通过硬约束的候选（已打分排序）。

    relaxed=True 时跳过宏量/油盐区间判定（只保留硬排除），用于硬约束下取最接近的兜底候选。
    """
    allowed_staples = [f for f in staples if not hard_filter_reasons(f, targets)]
    allowed_sides = [f for f in sides if not hard_filter_reasons(f, targets)]

    keep_staples, keep_sides = _prefilter(allowed_staples, allowed_sides, target)

    pool: list[Candidate] = []
    soft_hits_by_dish = {f.dish_id: _soft_avoid_hits(f, soft_avoid) for f in list(keep_staples) + list(keep_sides)}

    combos: list[tuple[DishFacts, ...]] = []
    for staple in keep_staples:
        for side in keep_sides:
            combos.append((staple, side))
        for side_a, side_b in itertools.combinations(keep_sides, 2):
            if side_a.is_soup and side_b.is_soup:
                continue
            combos.append((staple, side_a, side_b))

    for combo in combos:
        portions = [DishPortion(facts=f, servings=servings) for f in combo]
        totals = combo_totals(portions)
        passed, failures = _within(target, totals)
        if not passed and not relaxed:
            continue
        micro = _micro_totals(portions)
        soft_hits = sum(soft_hits_by_dish.get(f.dish_id, 0) for f in combo)
        score, reason_codes, notes = _score(target, totals, micro, targets, soft_hits, combo)

        main_side = next((f for f in combo if not f.is_staple), combo[0])
        signature = (
            main_side.dish_id,
            (main_side.method_text or "").strip(),
            tuple(sorted(f.dish_id for f in combo)),
        )
        pool.append(
            Candidate(
                candidate_id=0,
                rank=0,
                portions=portions,
                totals=totals,
                oil_salt={"oil_g": totals.get("oil_g"), "salt_g": totals.get("salt_g")},
                micro_estimate=micro,
                score=round(score, 4),
                reason_codes=sorted(set(reason_codes)),
                notes=notes,
                signature=signature,
            )
        )

    pool.sort(key=lambda c: (c.score, c.totals.get("kcal") or 0.0))
    return pool[: max(max_candidates, 1)]


def diversify(
    candidates: Sequence[Candidate],
    count: int = 3,
    start_id: int = 1,
) -> list[Candidate]:
    """第 3 步：挑出 2~3 个差异化候选（优先换主食材，其次换做法），并分配 candidate_id 与 rank。"""
    want = max(1, min(int(count), 3))
    picked: list[Candidate] = []
    used_mains: set[str] = set()
    used_dish_sets: set[tuple[str, ...]] = set()

    # 第一轮：主菜（主食材）互不相同——这是「换主食材」的核心
    for cand in candidates:
        if len(picked) >= want:
            break
        main_dish = cand.signature[0] if cand.signature else ""
        if main_dish in used_mains:
            continue
        used_mains.add(main_dish)
        used_dish_sets.add(tuple(sorted(cand.dish_ids)))
        picked.append(cand)

    # 第二轮：主菜不够时，放宽到「做法或整组菜不同」
    if len(picked) < want:
        for cand in candidates:
            if len(picked) >= want:
                break
            dish_key = tuple(sorted(cand.dish_ids))
            if dish_key in used_dish_sets:
                continue
            used_dish_sets.add(dish_key)
            picked.append(cand)

    for index, cand in enumerate(picked, start=1):
        cand.candidate_id = start_id + index - 1
        cand.rank = index
    return picked
