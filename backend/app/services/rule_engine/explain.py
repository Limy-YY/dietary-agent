"""第 5 步（文案部分）：为什么这样搭 / 饮食顺序建议 / 微量覆盖进度。

原则：
- 文案由规则拼装，不调用 LLM，保证同一候选每次输出一致；
- 不出现「安全」「放心吃」等绝对化表述，过敏原未核查的菜一律带提示；
- 不编造数据：营养值缺失时只说明「部分营养数据缺失」。
"""
from __future__ import annotations

from collections.abc import Sequence

from .models import (
    Candidate,
    KEY_MICRONUTRIENTS,
    MealTarget,
    Targets,
)

__all__ = [
    "make_why_text",
    "make_eating_order_advice",
    "micro_coverage",
    "build_why_summary",
]

#: 顺序建议的固定句式（不做医疗承诺，只描述进食顺序）
_ORDER_WITH_SOUP = "先少量喝汤，再吃蔬菜和蛋白，主食留到最后"
_ORDER_DEFAULT = "先吃蔬菜和蛋白，主食留到最后"
_ORDER_ONLY_STAPLE = "先吃菜再吃主食"


def _fmt(value: float | None, unit: str = "g", digits: int = 0) -> str:
    if value is None:
        return ""
    if digits == 0:
        return f"{value:.0f}{unit}"
    return f"{value:.{digits}f}{unit}"


def make_why_text(candidate: Candidate, target: MealTarget, targets: Targets) -> str:
    """生成「为什么这样搭」的一句话说明（≤60 字，按句累加，不截断半句）。"""
    parts: list[str] = []
    staples = [p for p in candidate.portions if p.role == "主食"]
    sides = [p for p in candidate.portions if p.role != "主食"]

    if staples and sides:
        parts.append(f"{staples[0].name}打底、{len(sides)} 道菜配搭")
    elif staples:
        parts.append(f"以{staples[0].name}为主")

    kcal = candidate.totals.get("kcal")
    if kcal is not None and target.kcal > 0:
        gap_ratio = (kcal - target.kcal) / target.kcal
        if abs(gap_ratio) <= 0.05:
            parts.append(f"能量 {kcal:.0f}kcal 贴近本餐目标")
        elif gap_ratio < 0:
            parts.append(f"能量 {kcal:.0f}kcal，低于目标 {abs(gap_ratio) * 100:.0f}%")
        else:
            parts.append(f"能量 {kcal:.0f}kcal，高于目标 {gap_ratio * 100:.0f}%")
    elif kcal is None:
        parts.append("部分营养数据缺失，未做定量比较")

    protein = candidate.totals.get("protein_g")
    if protein is not None and target.protein.target is not None and target.protein.target > 0:
        ratio = protein / target.protein.target
        if 0.85 <= ratio <= 1.15:
            parts.append(f"蛋白 {protein:.0f}g 达本餐目标")

    if "low_oil_method" in candidate.reason_codes:
        parts.append("做法以蒸/拌为主，用油少")
    oil = candidate.oil_salt.get("oil_g")
    if oil is not None and target.oil_limit_g > 0 and oil <= target.oil_limit_g:
        parts.append(f"用油 {oil:.0f}g 在本餐限额内")

    text = ""
    for sentence in parts:
        merged = f"{text}，{sentence}" if text else sentence
        if len(merged) > 60:
            break
        text = merged
    return text or "按目标比例搭配的一餐"


def make_eating_order_advice(candidate: Candidate) -> str:
    """生成饮食顺序建议。"""
    has_soup = any(p.facts.is_soup for p in candidate.portions)
    side_count = sum(1 for p in candidate.portions if p.role != "主食")
    if has_soup:
        return _ORDER_WITH_SOUP
    if side_count >= 1:
        return _ORDER_DEFAULT
    return _ORDER_ONLY_STAPLE


def micro_coverage(
    candidate: Candidate,
    targets: Targets,
) -> list[dict[str, object]]:
    """本候选对 7 关键微量的覆盖进度（目标缺失时为 None）。"""
    out: list[dict[str, object]] = []
    for nutrient_id, name_zh, unit in KEY_MICRONUTRIENTS:
        ref = targets.micro_targets.get(nutrient_id)
        daily_target = ref.value if ref else None
        # 本餐目标按该餐能量占比折算
        ratio = 1.0
        value = candidate.micro_estimate.get(nutrient_id)
        if daily_target is not None and daily_target > 0 and value is not None:
            covered = round(value / daily_target * 100, 1)
            out.append(
                {
                    "nutrient_id": nutrient_id,
                    "name_zh": name_zh,
                    "value": round(value, 2),
                    "unit": unit,
                    "daily_target": daily_target,
                    "covered_pct": covered,
                }
            )
        else:
            out.append(
                {
                    "nutrient_id": nutrient_id,
                    "name_zh": name_zh,
                    "value": None if value is None else round(value, 2),
                    "unit": unit,
                    "daily_target": daily_target,
                    "covered_pct": None,
                }
            )
    return out


def build_why_summary(slot_results: Sequence, balance_hints: Sequence[str]) -> str:
    """整份方案的总体说明（一句到两句）。"""
    if not slot_results:
        return "未生成有效餐次"

    total_kcal = 0.0
    counted = 0
    for slot in slot_results:
        chosen = next(
            (c for c in getattr(slot, "candidates", []) if c.candidate_id == slot.selected_candidate_id),
            None,
        )
        if chosen is None:
            continue
        kcal = chosen.totals.get("kcal")
        if kcal is None:
            continue
        total_kcal += kcal
        counted += 1

    head = f"按目标能量与三餐配比分餐，共 {len(slot_results)} 餐"
    if counted:
        head += f"，其中 {counted} 餐可定量，合计约 {total_kcal:.0f}kcal"
        if counted < len(slot_results):
            head += "（其余餐次营养数据缺失）"
    if balance_hints:
        head += "。" + balance_hints[0]
    return head
