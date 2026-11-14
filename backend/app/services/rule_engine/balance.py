"""第 4 步：跨日微量平衡。

口径（任务书 v1.2 模块 A 第 4 步 / 契约 API-25）：
- 窗口余额来自库函数 `app.recent_micro_balance(p_user_id, p_window_start, p_window_end)`，
  返回 7 微量的 `total_value` 与 `selected_meal_count / known_meal_count / missing_meal_count`；
- 仅 7 种关键微量参与判断，钠归油盐糖、膳食纤维归宏量；
- 缺口 = 日目标 × 窗口天数 − 窗口已有摄入；缺口 > 0 时在候选池内回溯补位（把贡献更高的候选提为首选）；
- 补不齐、或目标缺失、或窗口内没有已记录餐次 → 落「参考提示」，**不得判为不足或超标**。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .models import (
    BalanceReport,
    Candidate,
    KEY_MICRONUTRIENTS,
    MICRO_IDS,
    MicroStatus,
    SlotResult,
    Targets,
)

__all__ = [
    "status_of",
    "compute_balance",
    "apply_balance",
    "match_window_rows",
]

#: 单餐补位需求的分摊系数（把窗口缺口摊到本方案餐次时留 10% 余量）
_ALLOC_FACTOR = 0.9


def match_window_rows(rows: Sequence[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """把 recent_micro_balance 的返回行按 nutrient_id 建索引。"""
    index: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        nutrient_id = str(row.get("nutrient_id") or row.get("nutrient_code") or "").strip()
        if nutrient_id:
            index[nutrient_id] = dict(row)
    return index


def status_of(
    target: float | None,
    window_total: float | None,
    known_meal_count: int,
    remaining: float | None,
) -> tuple[str, str | None]:
    """判定单条微量的状态：达标 / 不足 / 参考提示。"""
    if target is None or target <= 0:
        return "参考提示", "参考值缺失"
    if window_total is None:
        return "参考提示", "窗口摄入未知"
    if known_meal_count <= 0:
        return "参考提示", "窗口内无已记录餐次，无法判断"
    if remaining is not None and remaining <= 0:
        return "达标", None
    return "不足", None


def compute_balance(
    targets: Targets,
    window_rows: Sequence[dict[str, Any]] | None,
    window_days: int,
    window_start: str | None = None,
    window_end: str | None = None,
) -> BalanceReport:
    """汇总 7 微量的窗口缺口，产出 BalanceReport。"""
    index = match_window_rows(window_rows)
    days = max(int(window_days), 1)

    items: dict[str, MicroStatus] = {}
    data_notes: list[str] = []

    for nutrient_id, name_zh, unit in KEY_MICRONUTRIENTS:
        ref = targets.micro_targets.get(nutrient_id)
        daily_target = ref.value if ref else None

        row = index.get(nutrient_id, {})
        raw_total = row.get("total_value")
        try:
            window_total: float | None = float(raw_total) if raw_total is not None else None
        except (TypeError, ValueError):
            window_total = None

        known = int(row.get("known_meal_count") or 0)
        missing = int(row.get("missing_meal_count") or 0)
        if missing > 0:
            data_notes.append(f"{name_zh}：窗口内 {missing} 餐缺数据，结论仅作参考")

        if daily_target is None:
            target_total: float | None = None
        else:
            target_total = daily_target * days

        remaining: float | None = None
        covered_pct: float | None = None
        if target_total is not None and target_total > 0:
            if window_total is not None:
                remaining = round(target_total - window_total, 2)
                # 窗口内没有已记录餐次时，total_value 恒为 0，覆盖率不可解释 → 保持 None
                if known > 0:
                    covered_pct = round(window_total / target_total * 100, 1)

        status, note = status_of(target_total, window_total, known, remaining)
        items[nutrient_id] = MicroStatus(
            nutrient_id=nutrient_id,
            name_zh=name_zh,
            unit=unit,
            target=target_total,
            window_total=window_total,
            window_days=days,
            remaining=remaining,
            covered_pct=covered_pct,
            status=status,
            note=note,
        )

    return BalanceReport(
        window_start=window_start,
        window_end=window_end,
        window_days=days,
        items=items,
        data_notes=data_notes,
    )


def _needed_per_slot(report: BalanceReport, slot_count: int) -> dict[str, float]:
    """把窗口缺口摊到本次方案的餐次，得到每餐大致需要补的量。"""
    slots = max(int(slot_count), 1)
    needed: dict[str, float] = {}
    for nutrient_id, item in report.items.items():
        if item.status != "不足" or item.remaining is None or item.remaining <= 0:
            continue
        needed[nutrient_id] = item.remaining * _ALLOC_FACTOR / slots
    return needed


def apply_balance(
    slots: Sequence[SlotResult],
    report: BalanceReport,
    pools: dict[str, Sequence[Candidate]] | None = None,
) -> list[str]:
    """在候选池内回溯补位：把对缺口贡献更高的候选提为该餐首选。

    只在已通过区间判定的候选之间调整（不破坏宏量结构），返回调整说明。
    默认使用每个餐位自身的候选列表（`SlotResult.candidates`）。
    """
    needed = _needed_per_slot(report, len(slots))
    if not needed:
        return []

    improvements: list[str] = []
    for slot in slots:
        pool = list((pools or {}).get(slot.meal_type) or slot.candidates)
        if len(pool) < 2:
            continue

        current = next(
            (c for c in pool if c.candidate_id == (slot.selected_candidate_id or pool[0].candidate_id)),
            pool[0],
        )
        best = current
        best_gain = 0.0
        target_nutrient: str | None = None

        for cand in pool:
            if cand is current:
                continue
            for nutrient_id, need in needed.items():
                now = current.micro_estimate.get(nutrient_id)
                alt = cand.micro_estimate.get(nutrient_id)
                # null ≠ 0：任一侧缺该微量数据就跳过，不当作 0 参与增益比较
                if now is None or alt is None:
                    continue
                gain = alt - now
                if gain <= 0:
                    continue
                # 收益按「补齐需求的比例」归一，避免某一微量数值量级压过其他
                ratio = min(gain / need, 1.0) if need > 0 else 0.0
                if ratio > best_gain:
                    best_gain = ratio
                    best = cand
                    target_nutrient = nutrient_id

        if best is not current and target_nutrient is not None and best_gain > 0.05:
            slot.selected_candidate_id = best.candidate_id
            name_zh = report.items.get(target_nutrient).name_zh if target_nutrient in report.items else target_nutrient
            main_dish = next((d.name for d in best.portions), "候选")
            improvements.append(
                f"{slot.meal_type}：把「{main_dish}」（候选 {best.candidate_id}）提为首选，用于补{name_zh}"
            )

    return improvements


def build_micro_hints(report: BalanceReport, limit: int = 4) -> list[str]:
    """把平衡结论整理成给用户看的提示句（不含夸大结论）。"""
    hints: list[str] = []
    lacks = [i for i in report.items.values() if i.status == "不足"]
    lacks.sort(key=lambda x: (x.covered_pct if x.covered_pct is not None else 999))

    for item in lacks[:limit]:
        if item.covered_pct is None or item.remaining is None:
            hints.append(f"{item.name_zh}：窗口内摄入数据不足，建议后续方案留意")
            continue
        gap_ratio = 100 - item.covered_pct
        if gap_ratio >= 30:
            hints.append(
                f"{item.name_zh}低于目标的 {gap_ratio:.0f}%，建议后续方案增加富含{item.name_zh}的食材"
            )
        elif gap_ratio >= 10:
            hints.append(f"{item.name_zh}略有缺口（覆盖 {item.covered_pct:.0f}%），可在下一餐补一点")

    for nutrient_id in MICRO_IDS:
        item = report.items.get(nutrient_id)
        if item and item.status == "参考提示" and item.note:
            hints.append(f"{item.name_zh}：{item.note}")

    return hints
