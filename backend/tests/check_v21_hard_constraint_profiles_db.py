"""硬约束画像回归（DB 只读）：素食 / 清真 / 海鲜过敏 三画像各跑一遍。

目的：验证 A 裁剪（生成池 213→98）后，硬约束画像下每餐仍能凑出 ≥2 个候选，
且所有候选不违反对应硬排除。对应「推进计划-多窗口」窗口⑤第 2 项。

运行：backend 目录下 `python tests/check_v21_hard_constraint_profiles_db.py`
"""
from __future__ import annotations

from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.services.rule_engine import Profile, PlanRequest, SqlDataSource, generate_plan
from app.services.rule_engine.candidates import hard_filter_reasons
from app.services.rule_engine.quality import selected

PROFILES: dict[str, Profile] = {
    "素食": Profile(
        gender="女", age=24, height_cm=162, weight_kg=52,
        goal_code="maintain", religious_ethical=["素食"],
    ),
    "清真": Profile(
        gender="男", age=24, height_cm=175, weight_kg=68,
        goal_code="maintain", religious_ethical=["清真"],
    ),
    "海鲜过敏": Profile(
        gender="女", age=24, height_cm=162, weight_kg=52,
        goal_code="maintain", allergies=["海鲜"],
    ),
}


def main() -> None:
    with SessionLocal() as db:
        ds = SqlDataSource(db)
        for name, who in PROFILES.items():
            req = PlanRequest(
                start_date="2026-11-23", end_date="2026-11-25",
                meal_types=["早", "午", "晚"], goal_code="maintain",
                candidates_per_slot=3,
            )
            started = perf_counter()
            result = generate_plan(who, req, ds, skip_balance=False)
            elapsed = perf_counter() - started

            problems: list[str] = []
            for slot in result.slots:
                if len(slot.candidates) < 2:
                    problems.append(
                        f"{slot.slot_date} {slot.meal_type} 候选数 {len(slot.candidates)} < 2"
                    )
                for cand in slot.candidates:
                    for p in cand.portions:
                        reasons = hard_filter_reasons(p.facts, result.targets)
                        if reasons:
                            problems.append(f"{cand.dish_ids} 命中硬排除 {reasons}")
            if problems:
                print(f"[FAIL] {name}（{elapsed:.1f}s）")
                for p in problems:
                    print("  -", p)
                raise SystemExit(1)

            picked = sum(1 for s in result.slots if selected(s) is not None)
            print(
                f"[PASS] {name}：{len(result.slots)} 餐每餐 ≥2 候选、零硬约束命中，"
                f"首选 {picked}，耗时 {elapsed:.1f}s"
            )


if __name__ == "__main__":
    main()
