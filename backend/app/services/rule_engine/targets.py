"""第 1 步：算目标（档案 + goal_structure_map + 微量参考值 → Targets）。

口径（任务书 v1.2 模块 A / 契约 §0.2）：
- 能量 = BMR(Mifflin-St Jeor) × 1.4（activity_factor 从 goal_structure_map 读，默认 1.4）；
  热量只由档案决定，goal 只改结构比例，不改热量；
- 每餐能量占比默认早 30% / 午 40% / 晚 30%，可被请求覆盖；
- 宏量目标按 macro_policy 的占比换算为克数，区间 = 目标 ± 容差；
- 油盐糖：库内 `oil_salt_sugar_policy` 是**定性策略**（level=常规/收紧、added_sugar=控制），
  没有数值时不编造收紧幅度：数值沿用膳食指南上限，把「收紧」转成打分层的从严（oil_salt_strict）；
- 7 关键微量目标来自 `app.match_nutrient_reference`（缺失时保持 None，不补 0）；
- 只把 `conditions.status == 'confirmed'` 的疾病带入规则。

macro_policy 的真实形态（v1.2 种子，已连库核对）：
- maintain        → {fat_energy_pct:"20-30", protein_energy_pct:"10-20", carbohydrate_energy_pct:"50-65"}
- fat_loss        → {fat_policy:"接近20%下限", protein_energy_pct:"18-25"}
- muscle_gain     → {quality_protein:"提高占比", protein_energy_pct:"20-25"}
- glucose_control → {carbohydrate_policy:"接近50%下限"}
- digestive_health→ {fiber_policy:"提高", fermented_food:"提高"}
因此解析器必须支持「区间字符串 / 百分数 / 中文本占比」，并对未给出的项按剩余热量分摊。
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .models import (
    DEFAULT_ACTIVITY_FACTOR,
    DEFAULT_DAILY_LIMITS,
    DEFAULT_MEAL_RATIOS,
    KEY_MICRONUTRIENTS,
    KCAL_PER_G,
    MICRO_IDS,
    MICRO_UNIT,
    GoalPolicy,
    MacroRange,
    MealTarget,
    MicroReference,
    PlanRequest,
    Profile,
    Targets,
)

__all__ = [
    "bmr_mifflin",
    "parse_goal_policy",
    "compute_targets",
    "build_micro_references",
]

#: macro_policy 里三大宏量可能的键名。库内真实键名见模块 docstring。
_PROTEIN_KEYS = (
    "protein_energy_pct", "protein_pct", "protein_ratio", "protein_energy_ratio", "protein",
)
_FAT_KEYS = (
    "fat_energy_pct", "fat_pct", "fat_ratio", "fat_energy_ratio", "fat", "fat_policy",
)
_CARB_KEYS = (
    "carbohydrate_energy_pct", "carbohydrate_pct", "carb_pct", "carb_ratio",
    "carbohydrate_ratio", "carbohydrate", "carb", "carbohydrate_policy",
)

#: oil_salt_sugar_policy 若给了数值则直接用，否则退回指南上限
_OIL_KEYS = ("oil_g_daily", "oil_g_max", "oil_daily_g", "oil_g", "oil_limit_g")
_SALT_KEYS = ("salt_g_daily", "salt_g_max", "salt_daily_g", "salt_g", "salt_equiv_g", "salt_limit_g")
_SUGAR_KEYS = ("added_sugar_g_daily", "added_sugar_g_max", "sugar_g_daily", "added_sugar_g")

#: 定性「收紧」信号词（命中时只加强打分，不改数值上限）
_STRICT_WORDS = ("收紧", "降低", "严格", "控制")

_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|~|～|至|—)\s*(\d+(?:\.\d+)?)")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


# ---------------------------------------------------------------- 解析工具


def _first_raw(payload: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _as_ratio(value: float | None) -> float | None:
    """百分数（>1）转小数；<=0 视为缺失（避免把占比清零）。"""
    if value is None or value <= 0:
        return None
    return value / 100.0 if value > 1 else value


def _ratio_from_any(raw: Any) -> float | None:
    """把库里的占比取值解析成小数：'20-30' → 0.25，'接近20%下限' → 0.20，20 → 0.20。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return _as_ratio(float(raw))

    text = str(raw).strip()
    if not text:
        return None

    range_match = _RANGE_RE.search(text)
    if range_match:
        low, high = float(range_match.group(1)), float(range_match.group(2))
        return _as_ratio((low + high) / 2.0)

    pct_match = _PCT_RE.search(text)
    if pct_match:
        return _as_ratio(float(pct_match.group(1)))

    try:
        return _as_ratio(float(text))
    except ValueError:
        return None


def _raw_ratios(row: dict[str, Any] | None) -> tuple[float | None, float | None, float | None]:
    """取一行 goal 的三大宏量原始占比（未补缺、未归一）。"""
    if not row:
        return (None, None, None)
    macro = row.get("macro_policy") or {}
    if not isinstance(macro, dict):
        return (None, None, None)
    return (
        _ratio_from_any(_first_raw(macro, _PROTEIN_KEYS)),
        _ratio_from_any(_first_raw(macro, _FAT_KEYS)),
        _ratio_from_any(_first_raw(macro, _CARB_KEYS)),
    )


def _resolve_ratios(
    p: float | None,
    f: float | None,
    c: float | None,
    bp: float = 0.20,
    bf: float = 0.25,
    bc: float = 0.55,
) -> tuple[float, float, float]:
    """补缺 + 归一：显式给出的项固定，缺失项按剩余热量并结合基线比例分摊。

    这样 `glucose_control` 的「碳水接近 50%」不会被归一化稀释。
    """
    given = {"p": p, "f": f, "c": c}
    base = {"p": bp, "f": bf, "c": bc}
    missing = [k for k, v in given.items() if v is None]
    known = sum(v for v in given.values() if v is not None)

    out = dict(given)
    if missing:
        remain = 1.0 - known
        if remain <= 0:
            remain = 0.05 * len(missing)
        base_sum = sum(base[k] for k in missing)
        if base_sum <= 0:
            for k in missing:
                out[k] = remain / len(missing)
        else:
            for k in missing:
                out[k] = remain * base[k] / base_sum

    total = sum(out.values())
    if total <= 0:
        return (0.20, 0.25, 0.55)
    if not missing and abs(total - 1.0) > 1e-9:
        out = {k: v / total for k, v in out.items()}
    return (out["p"], out["f"], out["c"])


def _oil_salt_strict(policy_payload: dict[str, Any] | None) -> bool:
    """库内定性策略是否要求「收紧」。只用于加强打分，不改数值上限。"""
    if not isinstance(policy_payload, dict):
        return False
    for value in policy_payload.values():
        if isinstance(value, str) and any(word in value for word in _STRICT_WORDS):
            return True
    return False


def _as_grams(value: Any) -> float | None:
    try:
        grams = float(value)
    except (TypeError, ValueError):
        return None
    return grams if grams > 0 else None


def bmr_mifflin(gender: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor 基础代谢：男 +5，女 -161。"""
    base = 10.0 * float(weight_kg) + 6.25 * float(height_cm) - 5.0 * float(age)
    return base + (5.0 if str(gender).strip() == "男" else -161.0)


def parse_goal_policy(
    row: dict[str, Any] | None,
    baseline_row: dict[str, Any] | None = None,
) -> GoalPolicy:
    """把 core.goal_structure_map 的一行解析成 GoalPolicy。

    baseline_row 通常是 `maintain`（库里唯一给出完整三项占比的目标），
    用于给只写了部分宏量策略的目标（减脂/控糖/增肌）补结构基线。
    """
    if not row:
        policy = GoalPolicy()
        policy.protein_pct, policy.fat_pct, policy.carb_pct = 0.20, 0.25, 0.55
        return policy

    p, f, c = _raw_ratios(row)
    bp, bf, bc = _raw_ratios(baseline_row)
    bp = bp if bp is not None else 0.20
    bf = bf if bf is not None else 0.25
    bc = bc if bc is not None else 0.55
    p, f, c = _resolve_ratios(p, f, c, bp, bf, bc)

    policy = GoalPolicy(
        goal_code=str(row.get("goal_code") or "maintain"),
        goal_name=row.get("goal_name"),
        activity_factor=float(row.get("activity_factor") or DEFAULT_ACTIVITY_FACTOR),
        protein_pct=p,
        fat_pct=f,
        carb_pct=c,
        daily_limits=dict(DEFAULT_DAILY_LIMITS),
        oil_salt_strict=False,
    )

    oil_salt = row.get("oil_salt_sugar_policy") or {}
    if isinstance(oil_salt, dict):
        oil = _as_grams(_first_raw(oil_salt, _OIL_KEYS))
        salt = _as_grams(_first_raw(oil_salt, _SALT_KEYS))
        sugar = _as_grams(_first_raw(oil_salt, _SUGAR_KEYS))
        if oil is not None:
            policy.daily_limits["oil_g"] = oil
        if salt is not None:
            policy.daily_limits["salt_g"] = salt
        if sugar is not None:
            policy.daily_limits["added_sugar_g"] = sugar
        policy.oil_salt_strict = _oil_salt_strict(oil_salt)
        if policy.oil_salt_strict and oil is None and salt is None:
            policy.notes.append(
                "oil_salt_sugar_policy 为定性「收紧」且未给数值：油盐上限沿用指南值，"
                "在候选打分中对超限加倍扣分"
            )

    if policy.activity_factor <= 0:
        policy.activity_factor = DEFAULT_ACTIVITY_FACTOR

    energy_policy = row.get("energy_policy")
    if isinstance(energy_policy, str) and energy_policy.strip():
        policy.notes.append(f"energy_policy: {energy_policy.strip()}")

    macro = row.get("macro_policy") or {}
    if isinstance(macro, dict):
        qualitative = [
            f"{k}={v}" for k, v in macro.items()
            if isinstance(v, str) and _ratio_from_any(v) is None
        ]
        if qualitative:
            policy.notes.append("库内定性结构策略（未参与数值计算，仅记录）：" + "、".join(qualitative))

    return policy


def build_micro_references(rows: Iterable[dict[str, Any]]) -> dict[str, MicroReference]:
    """把 match_nutrient_reference 的返回行整理成 nutrient_id → MicroReference。

    列名注意：该函数的参考值列是 `reference_value`（不是 value）。
    """
    refs: dict[str, MicroReference] = {}
    for row in rows or []:
        nutrient_id = str(
            row.get("nutrient_id") or row.get("nutrient_code") or row.get("code") or ""
        ).strip()
        if not nutrient_id:
            continue
        raw_value = row.get("value")
        if raw_value is None:
            raw_value = row.get("reference_value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        refs[nutrient_id] = MicroReference(
            nutrient_id=nutrient_id,
            value=value,
            unit=str(row.get("unit") or MICRO_UNIT.get(nutrient_id, "")),
            reference_type=str(row.get("reference_type") or row.get("type") or "RNI"),
            age_band=row.get("age_group") or row.get("age_band"),
            note=row.get("note"),
        )

    for nutrient_id in MICRO_IDS:
        refs.setdefault(
            nutrient_id,
            MicroReference(
                nutrient_id=nutrient_id,
                value=None,
                unit=MICRO_UNIT.get(nutrient_id, ""),
                reference_type="RNI",
                note="参考值缺失：match_nutrient_reference 未返回该项",
            ),
        )
    return refs


def _macro_range(name: str, target: float | None, tolerance: float) -> MacroRange:
    if target is None:
        return MacroRange(name=name, target=None, low=None, high=None)
    return MacroRange(
        name=name,
        target=target,
        low=round(target * (1 - tolerance), 1),
        high=round(target * (1 + tolerance), 1),
    )


def compute_targets(
    profile: Profile,
    goal_row: dict[str, Any] | None,
    micro_rows: Iterable[dict[str, Any]] | None,
    request: PlanRequest,
    baseline_row: dict[str, Any] | None = None,
) -> Targets:
    """第 1 步：把档案与库内策略转成可计算目标。"""
    policy = parse_goal_policy(goal_row, baseline_row)
    bmr = bmr_mifflin(profile.gender, profile.weight_kg, profile.height_cm, profile.age)
    energy = max(bmr * policy.activity_factor, 0.0)

    ratios = dict(DEFAULT_MEAL_RATIOS)
    if request.meal_ratios:
        ratios.update({k: float(v) for k, v in request.meal_ratios.items() if float(v) > 0})
    selected = [mt for mt in request.meal_types if mt in ratios]
    if not selected:
        selected = list(ratios.keys())
    ratio_sum = sum(ratios[mt] for mt in selected) or 1.0

    refs = build_micro_references(micro_rows or [])
    micro_targets: dict[str, MicroReference] = {}
    micro_note: list[str] = []
    for nutrient_id, zh, unit in KEY_MICRONUTRIENTS:
        ref = refs.get(nutrient_id) or MicroReference(nutrient_id, None, unit)
        micro_targets[nutrient_id] = ref
        if ref.value is None:
            micro_note.append(f"{zh} 参考值缺失，按参考提示处理（不判达标/不足）")

    meal_targets: dict[str, MealTarget] = {}
    for meal_type in selected:
        ratio = ratios[meal_type] / ratio_sum
        kcal = energy * ratio
        meal_targets[meal_type] = MealTarget(
            meal_type=meal_type,
            ratio=ratio,
            kcal=kcal,
            protein=_macro_range(
                "protein_g", kcal * policy.protein_pct / KCAL_PER_G["protein_g"], request.tolerance
            ),
            fat=_macro_range("fat_g", kcal * policy.fat_pct / KCAL_PER_G["fat_g"], request.tolerance),
            carb=_macro_range("carb_g", kcal * policy.carb_pct / KCAL_PER_G["carb_g"], request.tolerance),
            oil_limit_g=policy.daily_limits["oil_g"] * ratio,
            salt_limit_g=policy.daily_limits["salt_g"] * ratio,
            added_sugar_limit_g=policy.daily_limits["added_sugar_g"] * ratio,
            micro={nid: refs[nid].value for nid in MICRO_IDS},
        )

    condition_note: list[str] = []
    confirmed = profile.confirmed_conditions
    if confirmed:
        condition_note.append(
            f"参与规则的已确诊疾病：{', '.join(confirmed)}（上限约束由库函数给出，未给出时不收紧）"
        )

    return Targets(
        bmr=bmr,
        activity_factor=policy.activity_factor,
        energy_kcal=energy,
        goal_code=request.goal_code or policy.goal_code,
        goal_name=policy.goal_name,
        goal_policy=policy,
        meal_targets=meal_targets,
        micro_targets=micro_targets,
        oil_salt_strict=policy.oil_salt_strict,
        hard_allergens=[a for a in (profile.allergies or []) if a],
        hard_religious=[r for r in (profile.religious_ethical or []) if r],
        excluded_ingredients=[e for e in (request.exclude_ingredients or []) if e],
        equipment=list(profile.cooking_equipment or []),
        confirmed_conditions=confirmed,
        condition_note=condition_note + list(policy.notes),
        micro_note=micro_note,
    )
