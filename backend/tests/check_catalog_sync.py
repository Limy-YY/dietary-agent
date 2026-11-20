# -*- coding: utf-8 -*-
"""规则引擎目录 ↔ DB 菜式 同步校验（防回归，只读）。

断言：core.dish 里每一道基础菜（非 -LS 少盐变体）都能在
`rule_engine/meal_templates.CATALOG` 找到「同 id 且同名」的条目。

目录缺条目、或 id/名错位，都会让该菜被 `profile()` 判成「未知」角色，
进而被候选生成排除（`template_for` 对含「未知」的组合 return None、
`iter_template_combos` 直接滤掉「未知」菜）。——这正是「数据入库了、
生成的食谱却看不到新菜」的根因，见《菜式目录补录清单.md》。

运行（backend 目录下）：
    ..\\.venv\\Scripts\\python.exe tests\\check_catalog_sync.py
退出码：0 = 同步；1 = 存在 N 道会被判「未知」的菜。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db
from app.services.rule_engine.repository import SqlDataSource
from app.services.rule_engine.meal_templates import CATALOG


def main() -> int:
    gen = get_db()
    db = next(gen)
    try:
        dishes = SqlDataSource(db).get_dish_facts()
    finally:
        db.rollback()
        gen.close()

    base = [d for d in dishes if not d.dish_id.endswith("-LS")]
    missing, misname, ok = [], [], []
    for d in base:
        c = CATALOG.get(d.dish_id)
        if c is None:
            missing.append((d.dish_id, d.name))
        elif c.name != d.name:
            misname.append((d.dish_id, d.name, c.name))
        else:
            ok.append((d.dish_id, d.name))

    print(
        f"DB 基础菜 {len(base)} 道 | 目录命中 {len(ok)} | "
        f"缺目录 {len(missing)} | 名字错位 {len(misname)}"
    )
    if missing:
        print("\n[目录缺失]")
        for did, name in sorted(missing):
            print(f"  {did}  {name}")
    if misname:
        print("\n[目录 id/名错位]")
        for did, name, cname in sorted(misname):
            print(f"  {did}  DB={name}  目录却写={cname}")

    bad = len(missing) + len(misname)
    if bad == 0:
        print("\n目录与 DB 同步 OK")
    else:
        print(f"\n不同步 FAIL（{bad} 道会被判「未知」并排除出候选生成）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
