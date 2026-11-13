"""连库验证：用 v1.2 真实数据跑模块 A 五步算法（不写库）。

用法：
    python tests/check_rule_engine_db.py [DSN]
默认 DSN 指向临时校验库 diet_agent_v12_check。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.services.rule_engine import PlanRequest, Profile, SqlDataSource, generate_plan  # noqa: E402
from app.services.rule_engine.targets import parse_goal_policy  # noqa: E402

DEFAULT_DSN = "postgresql+psycopg://diet_app:diet_app_dev@localhost:5432/diet_agent_v12_check"


def main() -> int:
    dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CHECK_DSN", DEFAULT_DSN)
    engine = create_engine(dsn)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as session:
        ds = SqlDataSource(session)

        # 1) 菜式事实聚合
        dishes = ds.get_dish_facts()
        staples = [d for d in dishes if d.is_staple]
        missing_fat = [d.dish_id for d in dishes if d.fat_g is None]
        missing_ca = [d.dish_id for d in dishes if d.calcium_mg is None]
        micro_ok = [d.dish_id for d in dishes if d.micro.get("iron") is not None]
        print(f"[DB-1] 菜式={len(dishes)} 主食={len(staples)} fat缺失={len(missing_fat)} "
              f"钙缺失={len(missing_ca)} 铁有值={len(micro_ok)}")
        for d in dishes[:3]:
            print(f"    {d.dish_id} {d.name} kcal={d.energy_kcal} P={d.protein_g} "
                  f"F={d.fat_g} C={d.carb_g} 油={d.default_oil_g} 盐={d.default_salt_g} "
                  f"Ca={d.calcium_mg} Fe={d.micro.get('iron')} 过敏原={d.strict_allergens}")

        # 2) 五个目标的结构解析（macro_policy 真值）
        rows = session.execute(
            text("SELECT goal_code, goal_name, macro_policy, oil_salt_sugar_policy, "
                 "activity_factor, energy_policy FROM core.goal_structure_map "
                 "WHERE is_active ORDER BY goal_code")
        ).mappings().all()
        baseline = next((dict(r) for r in rows if r["goal_code"] == "maintain"), None)
        print("[DB-2] goal_structure_map 解析：")
        for row in rows:
            policy = parse_goal_policy(dict(row), baseline if row["goal_code"] != "maintain" else None)
            total = policy.protein_pct + policy.fat_pct + policy.carb_pct
            print(f"    {policy.goal_code:<16} P={policy.protein_pct:.3f} F={policy.fat_pct:.3f} "
                  f"C={policy.carb_pct:.3f} 合计={total:.3f} strict={policy.oil_salt_strict} "
                  f"油盐糖={policy.daily_limits}")

        # 3) 7 微量参考值
        profile = Profile(gender="女", age=20, height_cm=160, weight_kg=55, goal_code="fat_loss",
                          cooking_equipment=["炒锅", "蒸锅", "电饭煲"])
        refs = ds.get_micro_reference_rows(profile)
        print(f"[DB-3] 微量参考行={len(refs)}")
        for r in refs:
            print(f"    {r['nutrient_id']:<12} {r['reference_value']} {r['unit']} "
                  f"({r['reference_type']}, {r['sex']}, {r['age_group']})")

        # 4) 三餐生成
        request = PlanRequest(
            start_date="2026-11-13", end_date="2026-11-13", plan_type="日",
            meal_types=["早", "午", "晚"], candidates_per_slot=3,
            user_id="U-DB-CHECK", window_days=7,
        )
        result = generate_plan(profile, request, ds)
        payload = result.as_dict()
        print(f"[DB-4] status={payload['status']} 目标能量={payload['goal_energy_kcal']} "
              f"比例={payload['macro_ratio']}")
        for slot in payload["slots"]:
            print(f"    {slot['meal_type']} 目标={slot['target_macro']} 候选={len(slot['candidates'])}")
            for cand in slot["candidates"]:
                names = " + ".join(d["name"] for d in cand["dishes"])
                print(f"      [{cand['rank']}] {names} | {cand['macro_estimate']} | "
                      f"油盐={cand['oil_salt_estimate']} | {cand['why_text']}")
        print("[DB-5] 微量平衡：")
        if payload["balance"]:
            for nid, item in payload["balance"]["items"].items():
                print(f"    {nid:<12} {item['status']:<6} 目标={item['target']} 已有={item['window_total']} "
                      f"覆盖={item['covered_pct']}%")
            for imp in payload["balance"]["improvements"]:
                print(f"      · {imp}")
        print("[DB-6] 数据质量说明：")
        for note in payload["data_quality_notes"]:
            print(f"    - {note}")
        print(f"[DB-7] why_summary: {payload['why_summary']}")

        # 5) 库函数窗口余额结构
        rows2 = session.execute(
            text("SELECT nutrient_id, total_value, known_meal_count, missing_meal_count "
                 "FROM app.recent_micro_balance('U-DB-CHECK', DATE '2026-11-06', DATE '2026-11-13')")
        ).mappings().all()
        print(f"[DB-8] recent_micro_balance 行={len(rows2)} 示例={dict(rows2[0]) if rows2 else '空'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
