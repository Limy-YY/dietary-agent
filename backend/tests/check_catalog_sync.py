# -*- coding: utf-8 -*-
"""规则引擎菜式角色 ↔ DB dish_meta 同步校验（防回归，只读）。

§5.1 把角色单一来源从 `meal_templates._ROWS` 迁到 `core.dish.dish_meta`：
断言 core.dish 里每一道基础菜（非 -LS 少盐变体）都有非空 dish_meta，
否则 `profile()` 会把它判成「未知」角色，进而被候选生成排除。

运行（backend 目录下）：
    ..\\.venv\\Scripts\\python.exe tests\\check_catalog_sync.py
退出码：0 = 同步；1 = 存在 N 道会缺 dish_meta 的菜。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db
from app.services.rule_engine.repository import SqlDataSource


def main() -> int:
    gen = get_db()
    db = next(gen)
    try:
        dishes = SqlDataSource(db).get_dish_facts(generation_only=False)
    finally:
        db.rollback()
        gen.close()

    base = [d for d in dishes if not d.dish_id.endswith("-LS")]
    missing = []
    for d in base:
        meta = getattr(d, "dish_meta", None)
        if not meta or not meta.get("roles"):
            missing.append(d.dish_id)

    print(f"DB 基础菜 {len(base)} 道 | 有 dish_meta {len(base) - len(missing)} | 缺 {len(missing)}")
    if missing:
        print("\n[dish_meta 缺失]")
        for did in sorted(missing):
            print(f"  {did}")

    if not missing:
        print("\ndish_meta 与 DB 同步 OK")
    else:
        print(f"\n不同步 FAIL（{len(missing)} 道会被判「未知」并排除出候选生成）")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
