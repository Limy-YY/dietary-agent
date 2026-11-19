"""规则引擎纯函数单测（pytest）—— 与后端组配合的模块 A 单测用例集。

定位：`test_rule_engine_selftest.py` 是给开发自测用的脚本（print 断言，无 pytest 集成、
缺 CSV 时静默 SKIP D/G 组）；本文件是**可进 CI 的 pytest 版本**，只测纯计算、零 DB 依赖，
补足边界与「null ≠ 0」「口径上限」这类容易被改坏的点。

覆盖：
1) bmr_mifflin           — Mifflin-St Jeor 公式与性别符号
2) parse_goal_policy     — 缺行回退、基线补齐、油盐糖上限覆盖、定性「收紧」标记
3) compute_targets       — 能量 = BMR×1.4、餐次子集分权重算、微量参考值缺失话术
4) hard_filter_reasons   — 过敏原 / 宗教忌口 / 显式排除 / 厨具 四类硬排除
5) sum_or_none & combo   — 缺失值不落 0（预算里最容易出错的地方）
6) status_of             — 微量四态判定（达标 / 不足 / 参考提示）
7) plan_dates            — 日期区间与上限截断

运行：
    pytest backend/tests/test_rule_engine_unit.py -q
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rule_engine import (  # noqa: E402
    DishFacts,
    DishPortion,
    PlanRequest,
    Profile,
    bmr_mifflin,
    compute_targets,
    hard_filter_reasons,
    parse_goal_policy,
    plan_dates,
)
from app.services.rule_engine.balance import status_of  # noqa: E402
from app.services.rule_engine.candidates import (  # noqa: E402
    combo_totals,
    sum_or_none,
)
from app.services.rule_engine.models import DEFAULT_ACTIVITY_FACTOR  # noqa: E402


# ---------------------------------------------------------------- 构造辅助


def make_profile(**kw) -> Profile:
    base = dict(gender="女", age=25, height_cm=160.0, weight_kg=60.0, goal_code="maintain")
    base.update(kw)
    return Profile(**base)


def make_request(**kw) -> PlanRequest:
    base = dict(start_date="2026-11-19", end_date="2026-11-19")
    base.update(kw)
    return PlanRequest(**base)


def make_dish(**kw) -> DishFacts:
    base = dict(
        dish_id="DISH-T01",
        name="清蒸鲈鱼",
        category="荤菜",
        method_text="清蒸",
        energy_kcal=320.0,
        protein_g=30.0,
        fat_g=8.0,
        carb_g=2.0,
        sodium_mg=420.0,
        ingredient_names=["鲈鱼"],
    )
    base.update(kw)
    return DishFacts(**base)


# ---------------------------------------------------------------- 1. BMR


def test_bmr_female_formula():
    # 10*60 + 6.25*160 - 5*25 - 161 = 600 + 1000 - 125 - 161 = 1314
    assert bmr_mifflin("女", 60, 160, 25) == pytest.approx(1314.0)


def test_bmr_male_formula():
    # 同参数男 +5 → 1480
    assert bmr_mifflin("男", 60, 160, 25) == pytest.approx(1480.0)


@pytest.mark.parametrize("gender", ["female", "F", "", None, "女"])
def test_bmr_non_male_uses_female_sign(gender):
    """只有「男」加 5，其余一律按女性 -161（口径写死，防误判性别字符串）。"""
    assert bmr_mifflin(gender, 60, 160, 25) == pytest.approx(1314.0)


def test_bmr_monotonic():
    """体重/身高升 → BMR 升；年龄升 → BMR 降。"""
    assert bmr_mifflin("女", 70, 160, 25) > bmr_mifflin("女", 60, 160, 25)
    assert bmr_mifflin("女", 60, 170, 25) > bmr_mifflin("女", 60, 160, 25)
    assert bmr_mifflin("女", 60, 160, 35) < bmr_mifflin("女", 60, 160, 25)


# ---------------------------------------------------------------- 2. 目标策略解析


def test_goal_policy_none_falls_back_to_defaults():
    policy = parse_goal_policy(None)
    assert (policy.protein_pct, policy.fat_pct, policy.carb_pct) == (0.20, 0.25, 0.55)
    assert policy.activity_factor == DEFAULT_ACTIVITY_FACTOR


def test_goal_policy_partial_row_filled_by_baseline():
    """减脂只给蛋白区间与「脂肪接近下限」，其余用 maintain 基线补齐，三项归一到 1。"""
    baseline = {"goal_code": "maintain", "macro_policy": {
        "fat_energy_pct": "20-30", "protein_energy_pct": "10-20",
        "carbohydrate_energy_pct": "50-65"}}
    row = {"goal_code": "fat_loss", "macro_policy": {
        "fat_policy": "接近20%下限", "protein_energy_pct": "18-25"}}
    policy = parse_goal_policy(row, baseline)
    assert policy.protein_pct + policy.fat_pct + policy.carb_pct == pytest.approx(1.0)
    assert policy.protein_pct == pytest.approx(0.215, abs=1e-3)   # 18-25 中值 21.5%
    assert policy.fat_pct == pytest.approx(0.20, abs=1e-3)        # 「接近 20% 下限」


def test_goal_policy_range_string_takes_midpoint():
    """库内区间字符串（如 10-20）取中值后归一，非取上限也非取 0。"""
    row = {"goal_code": "maintain", "macro_policy": {
        "fat_energy_pct": "20-30", "protein_energy_pct": "10-20",
        "carbohydrate_energy_pct": "50-65"}}
    policy = parse_goal_policy(row)
    assert policy.protein_pct == pytest.approx(0.154, abs=1e-3)
    assert policy.fat_pct == pytest.approx(0.256, abs=1e-3)


def test_goal_policy_oil_salt_limits_override_guide_values():
    row = {
        "goal_code": "lose",
        "oil_salt_sugar_policy": {"oil_g_daily": 20, "salt_g_max": 4.0, "added_sugar_g": 15},
    }
    policy = parse_goal_policy(row)
    assert policy.daily_limits["oil_g"] == 20.0
    assert policy.daily_limits["salt_g"] == 4.0
    assert policy.daily_limits["added_sugar_g"] == 15.0


def test_goal_policy_strict_without_numbers_keeps_guide_values():
    """定性「收紧」但没给数值：上限沿用指南值，并留下可解释备注。"""
    row = {"goal_code": "lose", "oil_salt_sugar_policy": {"level": "收紧", "added_sugar": "控制"}}
    policy = parse_goal_policy(row)
    assert policy.oil_salt_strict is True
    assert policy.daily_limits["oil_g"] == 25.0
    assert any("收紧" in n for n in policy.notes)


def test_goal_policy_invalid_activity_factor_resets():
    policy = parse_goal_policy({"goal_code": "lose", "activity_factor": 0})
    assert policy.activity_factor == DEFAULT_ACTIVITY_FACTOR


# ---------------------------------------------------------------- 3. 目标计算


def test_energy_equals_bmr_times_1_4():
    """v1.2 口径：能量 = BMR × 1.4，无活动系数、无缺口。"""
    t = compute_targets(make_profile(), None, None, make_request())
    assert t.bmr == pytest.approx(1314.0)
    assert t.energy_kcal == pytest.approx(1314.0 * 1.4)


def test_meal_ratios_split_25_40_35():
    """V2.1（fa7a4fe）：默认三餐比例 30/40/30 → 25/40/35。"""
    t = compute_targets(make_profile(), None, None, make_request())
    energy = t.energy_kcal
    assert t.meal_targets["早"].kcal == pytest.approx(energy * 0.25, rel=1e-6)
    assert t.meal_targets["午"].kcal == pytest.approx(energy * 0.40, rel=1e-6)
    assert t.meal_targets["晚"].kcal == pytest.approx(energy * 0.35, rel=1e-6)


def test_single_meal_request_gets_only_its_share():
    """V2.1 语义：分母恒为全天三餐默认比例之和，部分方案不吸收省略餐次的能量。

    只排午餐 → 午餐拿全天 40%（旧版曾独占 100%，会让一人一顿吃掉全天热量）。
    """
    t = compute_targets(make_profile(), None, None, make_request(meal_types=["午"]))
    assert list(t.meal_targets) == ["午"]
    assert t.meal_targets["午"].ratio == pytest.approx(0.4, rel=1e-6)
    assert t.meal_targets["午"].kcal == pytest.approx(t.energy_kcal * 0.4, rel=1e-6)


def test_custom_meal_ratios_partial_normalized_with_defaults():
    """V2.1 语义：自定义只覆盖给出的餐次，剩余餐次沿用默认值一并归一。

    早 0.5 / 午 0.5（晚缺省 0.35）→ sum=1.35 → 早占 0.5/1.35。
    """
    t = compute_targets(make_profile(), None, None,
                        make_request(meal_types=["早", "午"], meal_ratios={"早": 0.5, "午": 0.5}))
    assert t.meal_targets["早"].ratio == pytest.approx(0.5 / 1.35, rel=1e-6)
    assert t.meal_targets["午"].ratio == pytest.approx(0.5 / 1.35, rel=1e-6)


def test_custom_meal_ratios_full_day_exact():
    """三个餐次都显式给出且和为 1 时按给定比例精确分配。"""
    t = compute_targets(make_profile(), None, None,
                        make_request(meal_ratios={"早": 0.3, "午": 0.4, "晚": 0.3}))
    assert t.meal_targets["早"].ratio == pytest.approx(0.3, rel=1e-6)
    assert t.meal_targets["午"].ratio == pytest.approx(0.4, rel=1e-6)
    assert t.meal_targets["晚"].ratio == pytest.approx(0.3, rel=1e-6)


def test_micro_targets_all_seven_present_and_missing_flagged():
    """7 项微量键齐全；无参考值时记 note（参考提示），不判 0。"""
    t = compute_targets(make_profile(), None, None, make_request())
    assert set(t.micro_targets) == {"calcium", "iron", "zinc", "vitamin_a",
                                    "vitamin_b1", "vitamin_b2", "vitamin_c"}
    assert all(ref.value is None for ref in t.micro_targets.values())
    assert len(t.micro_note) == 7


def test_micro_reference_loaded_from_rows():
    rows = [{"nutrient_id": "calcium", "reference_value": 800, "unit": "mg", "reference_type": "RNI"}]
    t = compute_targets(make_profile(), None, rows, make_request())
    assert t.micro_targets["calcium"].value == pytest.approx(800.0)
    assert t.micro_targets["iron"].value is None


def test_hard_constraints_carried_into_targets():
    profile = make_profile(allergies=["花生"], religious_ethical=["清真"],
                           cooking_equipment=["电饭煲"])
    t = compute_targets(profile, None, None, make_request(exclude_ingredients=["香菜"]))
    assert t.hard_allergens == ["花生"]
    assert t.hard_religious == ["清真"]
    assert t.excluded_ingredients == ["香菜"]
    assert t.equipment == ["电饭煲"]


# ---------------------------------------------------------------- 4. 硬约束过滤


def _targets(**profile_kw):
    req_kw = profile_kw.pop("_req", {})
    return compute_targets(make_profile(**profile_kw), None, None, make_request(**req_kw))


def test_allergen_blocks_dish():
    tastes = _targets(allergies=["花生"])
    facts = make_dish(name="花生拌菠菜", ingredient_names=["花生", "菠菜"], strict_allergens=["花生"])
    assert "allergen:花生" in hard_filter_reasons(facts, tastes)


def test_allergen_hit_in_name_blocks_even_unverified():
    """V2.1 收紧（fa7a4fe）：菜名/配料名直接命中过敏原即硬过滤，不再要求「已确认含」。

    未确认（strict_allergens 为空）+ 名字含花生 → 仍排除（保守安全方向）。
    """
    tastes = _targets(allergies=["花生"])
    facts = make_dish(name="花生拌菠菜", ingredient_names=["花生"], unverified_food_ids=["F09"])
    reasons = hard_filter_reasons(facts, tastes)
    assert "allergen:花生" in reasons
    assert facts.allergen_unverified is True


def test_allergen_not_in_name_and_unconfirmed_passes():
    """名字与配料都不含过敏原、strict_allergens 为空 → 放行，仅留 unverified 标志。"""
    tastes = _targets(allergies=["花生"])
    facts = make_dish(name="菠菜豆腐煲", ingredient_names=["菠菜", "豆腐"], unverified_food_ids=["F09"])
    assert hard_filter_reasons(facts, tastes) == []
    assert facts.allergen_unverified is True


def test_allergen_alias_normalized():
    """V2.1 别名归一：用户写「蛋」，菜品标注「鸡蛋」也能匹配过滤；反之亦然。"""
    tastes = _targets(allergies=["蛋"])
    facts = make_dish(name="番茄炒蛋", ingredient_names=["鸡蛋"])
    assert "allergen:蛋" in hard_filter_reasons(facts, tastes)


def test_religious_taboo_blocks_pork():
    tastes = _targets(religious_ethical=["清真"])
    facts = make_dish(name="排骨汤", ingredient_names=["排骨"], category="汤羹")
    assert "religious:清真" in hard_filter_reasons(facts, tastes)


def test_religious_taboo_does_not_block_fish_for_halal():
    tastes = _targets(religious_ethical=["清真"])
    facts = make_dish(name="清蒸鲈鱼", ingredient_names=["鲈鱼"])
    assert hard_filter_reasons(facts, tastes) == []


def test_vegetarian_blocks_meat_but_not_tofu():
    tastes = _targets(religious_ethical=["素食"])
    meat = make_dish(name="照烧鸡腿饭", ingredient_names=["鸡腿", "米饭"])
    tofu = make_dish(name="家常豆腐", ingredient_names=["豆腐"], method_text="红烧")
    assert hard_filter_reasons(meat, tastes)
    assert hard_filter_reasons(tofu, tastes) == []


def test_exclude_ingredient_blocks_by_name_or_ingredient():
    tastes = _targets(_req={"exclude_ingredients": ["香菜"]})
    facts = make_dish(name="香菜拌豆腐", ingredient_names=["香菜"])
    assert "excluded:香菜" in hard_filter_reasons(facts, tastes)


def test_equipment_filter_only_when_profile_has_equipment():
    facts = make_dish(name="爆炒腰花", method_text="快炒")
    blocked = _targets(cooking_equipment=["电饭煲"])
    no_equip = _targets()
    assert "equipment:快炒" in hard_filter_reasons(facts, blocked)
    assert hard_filter_reasons(facts, no_equip) == []


def test_soft_avoid_recorded_but_not_blocking():
    tastes = _targets()
    facts = make_dish(name="炸鸡排", ingredient_names=["鸡胸肉"])
    reasons = hard_filter_reasons(facts, tastes, soft_avoid=["炸"])
    assert reasons == ["soft_avoid:炸"]  # 只记录，交打分降权


# ---------------------------------------------------------------- 5. 缺失值语义


def test_sum_or_none_propagates_none():
    assert sum_or_none([1.0, 2.0]) == pytest.approx(3.0)
    assert sum_or_none([1.0, None]) is None
    assert sum_or_none([]) == 0.0


def test_combo_totals_keeps_none_when_any_portion_missing():
    """组合里有菜缺脂肪 → 组合脂肪为 None，不得按 0 计。"""
    a = DishPortion(facts=DishFacts(dish_id="D1", name="饭", energy_kcal=200.0,
                                   protein_g=4.0, fat_g=None, carb_g=40.0), servings=1.0)
    b = DishPortion(facts=DishFacts(dish_id="D2", name="鱼", energy_kcal=300.0,
                                   protein_g=30.0, fat_g=8.0, carb_g=2.0), servings=1.0)
    totals = combo_totals([a, b])
    assert totals["kcal"] == pytest.approx(500.0)
    assert totals["fat_g"] is None
    assert totals["protein_g"] == pytest.approx(34.0)


def test_combo_totals_complete_data_sums():
    a = DishPortion(facts=DishFacts(dish_id="D1", name="饭", energy_kcal=200.0,
                                   protein_g=4.0, fat_g=1.0, carb_g=40.0), servings=1.0)
    b = DishPortion(facts=DishFacts(dish_id="D2", name="鱼", energy_kcal=300.0,
                                   protein_g=30.0, fat_g=8.0, carb_g=2.0), servings=1.0)
    totals = combo_totals([a, b])
    assert totals["fat_g"] == pytest.approx(9.0)
    assert totals["carb_g"] == pytest.approx(42.0)


# ---------------------------------------------------------------- 6. 微量状态判定


@pytest.mark.parametrize(
    "target,window_total,meals,remaining,expect",
    [
        (None, 500, 3, 100, "参考提示"),          # 参考值缺失
        (0, 500, 3, 100, "参考提示"),             # 参考值非正
        (800, None, 3, 100, "参考提示"),          # 窗口摄入未知
        (800, 300, 0, 500, "参考提示"),           # 窗口内无已记录餐次
        (800, 900, 3, 0, "达标"),                 # 已覆盖
        (800, 900, 3, -100, "达标"),              # 已超出
        (800, 300, 3, 500, "不足"),               # 有缺口
    ],
)
def test_status_of_four_states(target, window_total, meals, remaining, expect):
    status, _reason = status_of(target, window_total, meals, remaining)
    assert status == expect


# ---------------------------------------------------------------- 7. 日期规划


def test_plan_dates_inclusive_range():
    days = plan_dates("2026-11-19", "2026-11-21")
    assert days == ["2026-11-19", "2026-11-20", "2026-11-21"]


def test_plan_dates_single_day():
    assert plan_dates("2026-11-19", "2026-11-19") == ["2026-11-19"]


def test_plan_dates_truncated_by_max_slots():
    """21 个餐位 = 7 天 × 三餐，超出的日期必须截断而不是静默生成。"""
    days = plan_dates("2026-11-19", "2026-12-19", limit=7)
    assert days == ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22",
                    "2026-11-23", "2026-11-24", "2026-11-25"]
