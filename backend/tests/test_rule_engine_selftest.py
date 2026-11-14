"""模块 A 自测：五步算法的确定性断言（不依赖数据库，可直接 python 运行）。

覆盖：
A 目标计算（BMR / 每餐能量 / 宏量区间）
B 硬约束（过敏原、宗教忌口、排除食材）
C 差异化（2~3 候选、主菜不同）
D 缺失值语义（null ≠ 0，落 partial_data 与说明）
E 跨日微量平衡（无记录 → 参考提示；有缺口 → 不足 + 补位）
F 输出结构（MealCard payload 字段齐全）
G 主食识别（category 空时 tags/名称兜底）
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rule_engine import (  # noqa: E402
    CsvDishSource,
    DishFacts,
    PlanRequest,
    Profile,
    compute_balance,
    compute_targets,
    generate_plan,
    hard_filter_reasons,
    parse_goal_policy,
)

def _resolve_csv_path() -> str | None:
    """菜式明细 CSV 路径：优先环境变量 DISH_CSV，其次仓库内 tests/fixtures；都没有返回 None。"""
    env = os.environ.get("DISH_CSV")
    if env and os.path.exists(env):
        return env
    local = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "菜式数据明细_60道.csv"
    )
    if os.path.exists(local):
        return local
    return None


def dish(
    dish_id: str,
    name: str,
    category: str | None,
    energy: float,
    protein: float,
    fat: float,
    carb: float,
    sodium: float,
    oil: float,
    salt: float,
    micro: dict[str, float | None] | None = None,
    allergens: list[str] | None = None,
    tags: list[str] | None = None,
    method: str = "清蒸",
    ingredients: list[str] | None = None,
    unverified: list[str] | None = None,
) -> DishFacts:
    return DishFacts(
        dish_id=dish_id,
        name=name,
        category=category,
        tags=tags or [],
        method_text=method,
        cooking_rule_id="CR002",
        servings=1.0,
        default_oil_g=oil,
        default_salt_g=salt,
        energy_kcal=energy,
        protein_g=protein,
        fat_g=fat,
        carb_g=carb,
        fiber_g=None,
        sodium_mg=sodium,
        calcium_mg=(micro or {}).get("calcium"),
        micro=micro or {},
        strict_allergens=allergens or [],
        unverified_food_ids=unverified or [],
        ingredient_names=ingredients or [name],
    )


def sample_dishes() -> list[DishFacts]:
    """3 道主食 + 7 道菜，构造上刻意让「主食 + 蛋白 + 蔬菜」可落区间。"""
    micro_rice = {
        "calcium": 10.0, "iron": 0.4, "zinc": 0.6,
        "vitamin_a": 0.0, "vitamin_b1": 0.05, "vitamin_b2": 0.02, "vitamin_c": 0.0,
    }
    micro_meat = {
        "calcium": 6.0, "iron": 0.8, "zinc": 1.2,
        "vitamin_a": 8.0, "vitamin_b1": 0.10, "vitamin_b2": 0.12, "vitamin_c": 0.0,
    }
    micro_veg = {
        "calcium": 60.0, "iron": 1.0, "zinc": 0.8,
        "vitamin_a": 120.0, "vitamin_b1": 0.06, "vitamin_b2": 0.10, "vitamin_c": 51.0,
    }
    return [
        # 主食
        dish("DISH-ST1", "米饭", "主食", 232, 4.4, 0.6, 51.5, 2, 0, 0, micro_rice),
        dish("DISH-ST2", "二米饭", "主食", 210, 5.0, 0.8, 46.0, 3, 0, 0, micro_rice),
        dish("DISH-ST3", "小米粥", None, 90, 2.5, 0.5, 19.0, 2, 0, 0, micro_rice, tags=["主食"]),
        # 菜（蛋白）
        dish("DISH-S1", "蒜香清蒸鸡胸肉", None, 206, 29.3, 5.0, 2.0, 445, 0, 1, micro_meat,
             ingredients=["鸡胸肉", "大蒜", "精盐"]),
        dish("DISH-S2", "西兰花鸡胸肉快炒", None, 322, 37.5, 10.0, 8.0, 483, 5, 1, micro_veg,
             ingredients=["鸡胸肉", "西兰花", "橄榄油", "精盐"], method="快炒", tags=["低盐"]),
        # 菜（水产 / 汤羹）
        dish("DISH-S3", "番茄鳕鱼汤", "汤羹", 150, 20.0, 5.0, 6.0, 300, 3, 1, micro_meat,
             allergens=["鱼"], ingredients=["鳕鱼", "番茄", "橄榄油"]),
        dish("DISH-S4", "清蒸三文鱼", "水产类", 280, 25.0, 18.0, 0.0, 200, 0, 1, micro_meat,
             allergens=["鱼"], ingredients=["三文鱼", "精盐"]),
        # 菜（蔬菜）
        dish("DISH-S5", "清炒西兰花", "蔬菜类", 90, 5.0, 5.0, 8.0, 150, 5, 1, micro_veg,
             ingredients=["西兰花", "橄榄油", "精盐"], method="快炒"),
        # 硬排除样本：猪肉（清真忌口）
        dish("DISH-S6", "冬瓜排骨汤", "汤羹", 120, 10.0, 8.0, 3.0, 350, 2, 1, micro_meat,
             ingredients=["猪排骨", "冬瓜", "精盐"], method="炖"),
        # 硬排除样本：花生过敏
        dish("DISH-S7", "花生拌菠菜", "蔬菜类", 180, 8.0, 12.0, 8.0, 200, 3, 1, micro_veg,
             allergens=["花生"], ingredients=["菠菜", "花生", "橄榄油"], method="凉拌"),
    ]


GOAL_ROW = {
    "goal_code": "fat_loss",
    "goal_name": "减脂",
    "macro_policy": {"protein_pct": 20, "fat_pct": 25, "carb_pct": 55},
    "oil_salt_sugar_policy": {"oil_g_daily": 25, "salt_g_daily": 5, "added_sugar_g_daily": 25},
    "activity_factor": 1.4,
    "energy_policy": "BMR×1.4",
}

MICRO_REFS = [
    {"nutrient_id": "calcium", "nutrient_name": "钙", "unit": "mg", "reference_type": "RNI",
     "reference_value": 800, "age_group": "18-49"},
    {"nutrient_id": "iron", "nutrient_name": "铁", "unit": "mg", "reference_type": "RNI",
     "reference_value": 18, "age_group": "18-49"},
    {"nutrient_id": "zinc", "nutrient_name": "锌", "unit": "mg", "reference_type": "RNI",
     "reference_value": 7.5, "age_group": "18-49"},
    {"nutrient_id": "vitamin_a", "nutrient_name": "维生素A", "unit": "μgRAE", "reference_type": "RNI",
     "reference_value": 660, "age_group": "18-49"},
    {"nutrient_id": "vitamin_b1", "nutrient_name": "维生素B1", "unit": "mg", "reference_type": "RNI",
     "reference_value": 1.2, "age_group": "18-49"},
    {"nutrient_id": "vitamin_b2", "nutrient_name": "维生素B2", "unit": "mg", "reference_type": "RNI",
     "reference_value": 1.2, "age_group": "18-49"},
    {"nutrient_id": "vitamin_c", "nutrient_name": "维生素C", "unit": "mg", "reference_type": "RNI",
     "reference_value": 100, "age_group": "18-49"},
]


class FakeDataSource:
    def __init__(self, dishes: list[DishFacts], window_rows: list[dict] | None = None) -> None:
        self.dishes = dishes
        self.window_rows = window_rows or []

    def get_goal_row(self, goal_code: str):
        return GOAL_ROW

    def get_micro_reference_rows(self, profile):
        return MICRO_REFS

    def get_dish_facts(self):
        return self.dishes

    def get_micro_window(self, user_id, window_start, window_end):
        return self.window_rows


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        global FAILED
        FAILED += 1


FAILED = 0


def main() -> int:
    profile = Profile(
        gender="女", age=20, height_cm=160, weight_kg=55,
        goal_code="fat_loss",
        allergies=["花生"],
        religious_ethical=["清真"],
        cooking_equipment=["炒锅", "蒸锅"],
    )
    request = PlanRequest(
        start_date="2026-11-13", end_date="2026-11-13",
        plan_type="日", meal_types=["早", "午", "晚"], candidates_per_slot=3,
        user_id="U-TEST", tolerance=0.25, window_days=7,
    )

    # A 目标计算
    targets = compute_targets(profile, GOAL_ROW, MICRO_REFS, request)
    bmr = 10 * 55 + 6.25 * 160 - 5 * 20 - 161
    check("A1 BMR = 1289", abs(targets.bmr - bmr) < 0.01, f"{targets.bmr:.2f}")
    check("A2 总能量 = BMR×1.4", abs(targets.energy_kcal - bmr * 1.4) < 0.01, f"{targets.energy_kcal:.1f}")
    breakfast = targets.meal_targets["早"]
    check(
        "A3 早餐能量 = 30%",
        abs(breakfast.kcal - bmr * 1.4 * 0.3) < 0.01,
        f"{breakfast.kcal:.1f}kcal",
    )
    check(
        "A4 早餐蛋白区间 = 目标±25%",
        abs(breakfast.protein.low - breakfast.protein.target * 0.75) < 0.05,
        f"{breakfast.protein.low}~{breakfast.protein.high}g",
    )
    check(
        "A5 油限额 = 25×30%",
        abs(breakfast.oil_limit_g - 7.5) < 0.01,
        f"{breakfast.oil_limit_g:g}g",
    )
    policy = parse_goal_policy(GOAL_ROW)
    check("A6 macro_policy 解析（百分数转小数）", abs(policy.protein_pct - 0.2) < 1e-9, f"{policy.protein_pct}")

    # 全流程
    ds = FakeDataSource(sample_dishes())
    result = generate_plan(profile, request, ds, skip_balance=True)
    payload = result.as_dict()

    # B 硬约束
    all_dish_ids = [d for s in result.slots for c in s.candidates for d in c.dish_ids]
    check("B1 花生过敏 → 花生拌菠菜排除", "DISH-S7" not in all_dish_ids)
    check("B2 清真 → 排骨汤排除", "DISH-S6" not in all_dish_ids)
    for slot in result.slots:
        for cand in slot.candidates:
            ok = cand.totals["kcal"] is None or True
            _ = ok
    check("B3 每餐都有候选", all(s.candidates for s in result.slots), f"餐位数={len(result.slots)}")

    # B4/B5 厨具硬过滤（回归修复后必须真的生效，不能是摆设）
    stir_facts = next(d for d in sample_dishes() if d.dish_id == "DISH-S2")
    kettle_targets = compute_targets(
        replace(profile, cooking_equipment=["电饭煲"]), GOAL_ROW, MICRO_REFS, request
    )
    kettle_reasons = hard_filter_reasons(stir_facts, kettle_targets)
    check(
        "B4 只有电饭煲 → 快炒菜被硬排除",
        any(r.startswith("equipment:") for r in kettle_reasons),
        str(kettle_reasons),
    )
    no_equip_targets = compute_targets(
        replace(profile, cooking_equipment=[]), GOAL_ROW, MICRO_REFS, request
    )
    no_equip_reasons = hard_filter_reasons(stir_facts, no_equip_targets)
    check(
        "B5 未填厨具 → 不做厨具过滤",
        no_equip_reasons == [],
        str(no_equip_reasons),
    )

    # C 差异化
    for slot in result.slots:
        mains = {c.signature[0] for c in slot.candidates}
        check(
            f"C {slot.meal_type}餐候选={len(slot.candidates)} 且主菜不同",
            len(slot.candidates) >= 2 and len(mains) == len(slot.candidates),
            f"mains={sorted(mains)}",
        )
    ranks = [c.rank for s in result.slots for c in s.candidates]
    check("C3 rank 从 1 连续", ranks and min(ranks) == 1)

    # D 缺失值语义（CSV 源缺 fat/carb）；CSV 不在仓库内时跳过，不判失败
    csv_dishes = None
    csv_path = _resolve_csv_path()
    if csv_path is None:
        print("SKIP D1-D4：未找到菜式明细 CSV，可用环境变量 DISH_CSV 指定路径")
    else:
        csv_source = CsvDishSource(csv_path)
        csv_dishes = csv_source.load()
        check("D1 CSV 加载 60 道菜", len(csv_dishes) == 60, f"{len(csv_dishes)}")
        check("D2 CSV 源 fat 全为 None", all(d.fat_g is None for d in csv_dishes))
        csv_result = generate_plan(
            profile,
            PlanRequest(start_date="2026-11-13", end_date="2026-11-13", user_id=None),
            FakeDataSource(csv_dishes),
            skip_balance=True,
        )
        check(
            "D3 缺失宏量 → 记 partial_data",
            any("partial_data" in c.reason_codes for s in csv_result.slots for c in s.candidates)
            or any("未按 0 计" in n for n in csv_result.data_quality_notes),
            csv_result.data_quality_notes[0] if csv_result.data_quality_notes else "无说明",
        )
        check("D4 输出未把 None 变 0", any(
            c.totals["fat_g"] is None for s in csv_result.slots for c in s.candidates
        ))

    # E 跨日平衡
    empty_window = compute_balance(targets, [], 7)
    check(
        "E1 无已记录餐次 → 全部参考提示",
        all(i.status == "参考提示" for i in empty_window.items.values()),
    )
    low_window = [{"nutrient_id": "calcium", "total_value": 900, "known_meal_count": 6,
                   "missing_meal_count": 0}]
    report = compute_balance(targets, low_window, 7)
    ca = report.items["calcium"]
    check("E2 钙窗口 900/5600 → 不足", ca.status == "不足", f"覆盖 {ca.covered_pct}%")
    check("E3 缺口 = 5600-900", abs((ca.remaining or 0) - 4700) < 0.01, f"{ca.remaining}")

    balance_result = generate_plan(
        profile,
        PlanRequest(start_date="2026-11-13", end_date="2026-11-13", user_id="U-TEST", window_days=7),
        FakeDataSource(sample_dishes(), window_rows=low_window),
        skip_balance=False,
    )
    check("E4 平衡结果已写入输出", balance_result.balance is not None)
    if balance_result.balance:
        check("E5 improvements 可解释", isinstance(balance_result.balance.improvements, list))

    # F 输出结构
    required = {
        "plan_type", "status", "start_date", "end_date", "goal_code", "goal_energy_kcal",
        "macro_ratio", "slots", "why_summary", "reference_hints", "data_quality_notes", "balance",
    }
    check("F1 顶层字段齐全", required <= set(payload.keys()), str(sorted(required - set(payload.keys()))))
    cand0 = payload["slots"][0]["candidates"][0]
    cand_required = {
        "candidate_id", "rank", "why_text", "reason_codes", "macro_estimate", "micro_estimate",
        "oil_salt_estimate", "eating_order_advice", "sources", "dishes",
    }
    check("F2 候选字段齐全", cand_required <= set(cand0.keys()), str(sorted(cand_required - set(cand0.keys()))))
    check("F3 7 微量键齐全", set(cand0["micro_estimate"].keys()) == {
        "calcium", "iron", "zinc", "vitamin_a", "vitamin_b1", "vitamin_b2", "vitamin_c",
    })
    check("F4 dish_id 为 text 且非空", all(
        d["dish_id"].startswith("DISH-") for d in cand0["dishes"]
    ))
    check("F5 JSON 可序列化", isinstance(json.dumps(payload, ensure_ascii=False), str))

    # G 主食识别（依赖同一份 CSV，缺失时跳过）
    if csv_dishes is None:
        print("SKIP G1-G3：未找到菜式明细 CSV")
    else:
        csv_staples = [d.dish_id for d in csv_dishes if d.is_staple]
        declared = {d.dish_id for d in csv_dishes if (d.category or "").strip() == "主食"}
        check("G1 category=主食 的 6 道全部识别", declared <= set(csv_staples), f"{len(declared)} 道")
        check(
            "G2 category 空时按名称兜底（DISH-029 糙米鹰嘴豆拌饭）",
            "DISH-029" in csv_staples and "DISH-029" not in declared,
        )
        check(
            "G3 名称兜底不误伤（土豆/玉米/汤类不入主食）",
            all(
                x not in csv_staples
                for x in ("DISH-040", "DISH-048", "DISH-052", "DISH-053", "DISH-060")
            ),
        )

    print()
    if FAILED:
        print(f"{FAILED} 项断言失败")
        return 1
    print("全部断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
