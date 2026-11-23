# -*- coding: utf-8 -*-
"""硬约束画像回归（窗口⑤）：素食 / 清真 / 海鲜过敏 三种画像的端到端硬地板。

不测 `hard_filter_reasons` 的单元边界（那在 backend/tests），这里测**画像级端到端**：
给定一份档案，跑完整 `generate_plan`（第 1~3 步：算目标 → 构造候选 → 差异化），断言
  1) 每餐候选数 ≥ 2（差异化的下限）；
  2) 该画像的**禁用菜**从未出现在任何候选里（硬约束真正生效，不是摆设）；
  3) 该画像的**安全菜**确实可进入候选（过滤没有把可吃的一锅端）。

离线可跑：`FakeDataSource` 只实现 `RuleEngineDataSource` 协议，纯内存，不碰 DB/LLM。
运行：`pytest tests/test_hard_constraint_profiles.py -q`
"""
from __future__ import annotations

import pytest

from app.services.rule_engine import (
    DishFacts,
    PlanRequest,
    Profile,
    compute_targets,
    generate_plan,
    hard_filter_reasons,
)


# ---------------------------------------------------------------- 合成菜式目录（内存）

# 角色由 `meal_templates.profile()` 的「名称/配料关键词」兜底判定（与 backend/tests 的
# sample_dishes 同源）；dish_id 用 PROF- 前缀刻意避开 `DISH-\d+` 的目录匹配，走名称启发式。


def _dish(dish_id, name, *, category=None, method="清蒸", energy, protein, fat, carb,
          sodium, oil=0.0, salt=0.0, ingredients=None, allergens=None) -> DishFacts:
    return DishFacts(
        dish_id=dish_id,
        name=name,
        category=category,
        tags=[],
        method_text=method,
        servings=1.0,
        default_oil_g=oil,
        default_salt_g=salt,
        energy_kcal=energy,
        protein_g=protein,
        fat_g=fat,
        carb_g=carb,
        fiber_g=None,
        sodium_mg=sodium,
        calcium_mg=None,
        micro={},
        strict_allergens=allergens or [],
        unverified_food_ids=[],
        ingredient_names=ingredients or [name],
    )


def _catalog() -> list[DishFacts]:
    return [
        # 主食（category=主食 → 主食角色）
        _dish("PROF-ST1", "米饭", category="主食", method="蒸", energy=232, protein=4.4, fat=0.6, carb=51.5, sodium=2, ingredients=["大米"]),
        _dish("PROF-ST2", "二米饭", category="主食", method="蒸", energy=210, protein=5.0, fat=0.8, carb=46.0, sodium=3, ingredients=["大米", "小米"]),
        _dish("PROF-ST3", "白馒头", category="主食", method="蒸", energy=223, protein=7.0, fat=1.1, carb=47.0, sodium=2, ingredients=["小麦粉"]),
        _dish("PROF-ST4", "蒸红薯", category="主食", method="蒸", energy=90, protein=1.5, fat=0.2, carb=21.0, sodium=2, ingredients=["红薯"]),
        # 蛋白质菜（素食安全：豆腐 / 鸡蛋）
        _dish("PROF-P1", "家常豆腐", method="红烧", energy=180, protein=15, fat=10, carb=8, sodium=400, oil=2, ingredients=["豆腐", "青椒"]),
        _dish("PROF-P2", "清蒸豆腐", method="清蒸", energy=120, protein=10, fat=7, carb=5, sodium=300, ingredients=["豆腐"]),
        _dish("PROF-P3", "番茄炒蛋", method="炒", energy=150, protein=10, fat=9, carb=7, sodium=350, oil=2, ingredients=["鸡蛋", "番茄"]),
        _dish("PROF-P4", "鸡蛋羹", method="蒸", energy=90, protein=8, fat=5, carb=2, sodium=250, ingredients=["鸡蛋"]),
        # 蛋白质菜（禽 / 畜 / 水产）
        _dish("PROF-P5", "蒜香清蒸鸡胸肉", method="清蒸", energy=206, protein=29, fat=5, carb=2, sodium=445, salt=1, ingredients=["鸡胸肉", "大蒜"]),
        _dish("PROF-P6", "芹菜炒牛肉", method="炒", energy=260, protein=28, fat=15, carb=6, sodium=480, oil=3, ingredients=["牛肉", "芹菜"]),
        _dish("PROF-P7", "清蒸鲈鱼", method="清蒸", energy=280, protein=25, fat=18, carb=0, sodium=200, ingredients=["鲈鱼"], allergens=["鱼类"]),
        _dish("PROF-P8", "白灼虾仁", method="白灼", energy=120, protein=22, fat=2, carb=2, sodium=350, ingredients=["虾仁"], allergens=["甲壳类水产"]),
        _dish("PROF-P9", "青椒炒猪肉", method="炒", energy=300, protein=24, fat=20, carb=5, sodium=480, oil=3, ingredients=["猪肉", "青椒"]),
        _dish("PROF-P10", "冬瓜排骨汤", category="汤羹", method="炖", energy=120, protein=10, fat=8, carb=3, sodium=350, oil=2, salt=1, ingredients=["猪排骨", "冬瓜"]),
        # 蔬菜
        _dish("PROF-V1", "蒜蓉西兰花", method="快炒", energy=90, protein=5, fat=5, carb=8, sodium=150, oil=3, ingredients=["西兰花"]),
        _dish("PROF-V2", "清炒生菜", method="炒", energy=60, protein=2, fat=3, carb=5, sodium=120, oil=2, ingredients=["生菜"]),
        _dish("PROF-V3", "蒜蓉菠菜", method="炒", energy=70, protein=4, fat=3, carb=6, sodium=140, oil=2, ingredients=["菠菜"]),
        _dish("PROF-V4", "凉拌黄瓜", method="凉拌", energy=50, protein=2, fat=2, carb=6, sodium=130, oil=1, ingredients=["黄瓜"]),
        _dish("PROF-V5", "清炒油菜", method="炒", energy=65, protein=3, fat=3, carb=6, sodium=130, oil=2, ingredients=["油菜"]),
    ]


class FakeDataSource:
    """只读内存数据源，实现 RuleEngineDataSource 协议（goal 走默认、微量空、跳过平衡）。"""

    def __init__(self, dishes: list[DishFacts]) -> None:
        self.dishes = dishes

    def get_goal_row(self, goal_code: str):
        return None  # 默认 20/25/55 结构

    def get_micro_reference_rows(self, profile):
        return []

    def get_dish_facts(self, generation_only: bool = False):
        return self.dishes

    def get_micro_window(self, user_id, window_start, window_end):
        return []


# ---------------------------------------------------------------- 三种画像


BASE_PROFILE = dict(gender="女", age=25, height_cm=160.0, weight_kg=60.0, goal_code="maintain")

PROFILES = {
    # (画像名, Profile 额外字段, 该画像必须被硬排除的 dish_id)
    "素食": (
        dict(religious_ethical=["素食"]),
        {"PROF-P5", "PROF-P6", "PROF-P7", "PROF-P8", "PROF-P9", "PROF-P10"},
    ),
    "清真": (
        dict(religious_ethical=["清真"]),
        {"PROF-P9", "PROF-P10"},  # 只禁猪；鱼/鸡/牛/蛋/豆腐安全
    ),
    "海鲜过敏": (
        dict(allergies=["海鲜"]),
        {"PROF-P7", "PROF-P8"},  # 鱼 / 甲壳类
    ),
}


@pytest.mark.parametrize("profile_name", list(PROFILES))
def test_hard_constraint_profile(profile_name):
    extra, forbidden = PROFILES[profile_name]
    profile = Profile(**{**BASE_PROFILE, **extra})
    request = PlanRequest(
        start_date="2026-11-23", end_date="2026-11-25",  # 3 天 × 3 餐 = 9 餐位
        meal_types=["早", "午", "晚"],
        candidates_per_slot=3,
    )
    dishes = _catalog()
    result = generate_plan(profile, request, FakeDataSource(dishes), skip_balance=True)

    # 1) 每餐 ≥ 2 候选
    for slot in result.slots:
        tag = f"{slot.slot_date} {slot.meal_type}"
        assert len(slot.candidates) >= 2, (
            f"[{profile_name}] {tag} 候选不足（{len(slot.candidates)}），"
            f"硬约束过滤后应仍能差异化 ≥2 个"
        )

    # 2) 禁用菜从未出现（硬约束真正生效）
    for slot in result.slots:
        for cand in slot.candidates:
            hits = set(cand.dish_ids) & forbidden
            assert not hits, (
                f"[{profile_name}] {slot.slot_date} {slot.meal_type} 出现禁用菜 {sorted(hits)}"
            )

    # 3) 每个最终候选都通过硬约束复核（双保险：引擎内部已过滤，这里再对画像复验一遍）
    for slot in result.slots:
        for cand in slot.candidates:
            for portion in cand.portions:
                reasons = hard_filter_reasons(portion.facts, result.targets)
                assert not [r for r in reasons if not r.startswith("soft_avoid:")], (
                    f"[{profile_name}] 候选含硬违规 {portion.dish_id}: {reasons}"
                )


# ---------------------------------------------------------------- 安全菜正向兜底


@pytest.mark.parametrize(
    "profile_name,safe_dish",
    [
        ("素食", "PROF-P1"),   # 豆腐应可通过
        ("清真", "PROF-P5"),   # 鸡胸肉（非猪）应可通过
        ("海鲜过敏", "PROF-P9"),  # 猪肉（非海鲜）应可通过
    ],
)
def test_safe_dish_is_not_over_filtered(profile_name, safe_dish):
    """防止把「该画像能吃」的菜也一并滤掉（过敏/宗教过滤不能一刀切过头）。

    注意：不能用「safe_dish 出现在某份具体方案」来断言——差异化会在同族安全菜里挑不同主菜，
    具体谁被选中取决于多样性排序，而非过滤。这里直接断言「过滤层不拦它」。
    """
    extra, _ = PROFILES[profile_name]
    profile = Profile(**{**BASE_PROFILE, **extra})
    request = PlanRequest(start_date="2026-11-23", end_date="2026-11-23", meal_types=["午"])
    targets = compute_targets(profile, None, None, request)
    facts = next(d for d in _catalog() if d.dish_id == safe_dish)
    reasons = hard_filter_reasons(facts, targets)
    assert not [r for r in reasons if not r.startswith("soft_avoid:")], (
        f"[{profile_name}] 安全菜 {safe_dish} 被硬过滤：{reasons}"
    )
