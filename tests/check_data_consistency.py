# -*- coding: utf-8 -*-
"""数据对照回归（窗口⑤ · check_catalog_sync 类）：校验活库口径与数据清洗收口。

只读，不写库。覆盖窗口③交付（`database/51_窗口③交付与后端交接说明.md`）定下的活数据口径：
  1) dish_meta 同步：每道基础菜（非 -LS）都有非空 `dish_meta.roles`（否则会被 `profile()` 判「未知」并排除出候选）；
  2) 菜式目录基线：221 = 178 基础 + 43 少盐变体；生成池 98 = 94 基础 + 4 少盐（A 裁剪）；
  3) 食材基线：132 总 = 103 活 + 29 死（软删）；
  4) 纤维归零：活食材 `fiber_g IS NULL` = 0（数据线补纤维收口）；
  5) 孤儿菜式归零：活菜式无一条没有 `dish_ingredient`；
  6) 少盐变体 base 回查：每条 -LS 变体的基础菜存在且 dish_meta 非空（repository 回填依赖）；
  7) 死食材不挂活菜：活菜式不得引用已软删的食材（否则 `_DISH_SQL` 聚合丢料 → 营养变 NULL）。

运行（任意目录，需本地 DB 已起）：
    python tests/check_data_consistency.py
退出码：0 = 全部通过；1 = 存在不通过项。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"

# 让 DATABASE_URL 不受 CWD 影响：优先读 backend/.env（diet_backend 账号），再交给 app.config。
_env = _BACKEND / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        if _key.strip() == "DATABASE_URL":
            os.environ.setdefault("DATABASE_URL", _val.strip().strip('"').strip("'"))
            break

sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text  # noqa: E402

from app.db import get_db  # noqa: E402


CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def _scalar(db, sql: str):
    return db.execute(text(sql)).scalar()


def main() -> int:
    gen = get_db()
    db = next(gen)
    try:
        # 1) dish_meta 同步（check_catalog_sync 的等价断言）
        base_total = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND dish_id NOT LIKE '%-LS'")
        base_no_meta = _scalar(
            db,
            "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND dish_id NOT LIKE '%-LS'"
            " AND (dish_meta IS NULL OR dish_meta->>'roles' IS NULL)",
        )
        check("dish_meta 同步（基础菜全有 roles）", base_no_meta == 0,
              f"{base_total - base_no_meta}/{base_total} 有，缺 {base_no_meta}")

        # 2) 菜式目录基线
        total = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted")
        base = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND dish_id NOT LIKE '%-LS'")
        ls = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND dish_id LIKE '%-LS'")
        check("菜式目录基线 221 = 178 基础 + 43 少盐", (total, base, ls) == (221, 178, 43),
              f"total={total} base={base} ls={ls}")

        gen_total = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND is_generation_enabled")
        gen_base = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND is_generation_enabled AND dish_id NOT LIKE '%-LS'")
        gen_ls = _scalar(db, "SELECT count(*) FROM core.dish WHERE NOT is_deleted AND is_generation_enabled AND dish_id LIKE '%-LS'")
        check("生成池 98 = 94 基础 + 4 少盐（A 裁剪）", (gen_total, gen_base, gen_ls) == (98, 94, 4),
              f"gen={gen_total} base={gen_base} ls={gen_ls}")

        # 3) 食材基线
        ing_total = _scalar(db, "SELECT count(*) FROM core.ingredient")
        ing_alive = _scalar(db, "SELECT count(*) FROM core.ingredient WHERE NOT is_deleted")
        ing_dead = _scalar(db, "SELECT count(*) FROM core.ingredient WHERE is_deleted")
        check("食材基线 132 = 103 活 + 29 死", (ing_total, ing_alive, ing_dead) == (132, 103, 29),
              f"total={ing_total} alive={ing_alive} dead={ing_dead}")

        # 4) 纤维归零
        fiber_null = _scalar(db, "SELECT count(*) FROM core.ingredient WHERE NOT is_deleted AND fiber_g IS NULL")
        check("纤维补全归零（活食材 fiber_g 无 NULL）", fiber_null == 0, f"fiber_null={fiber_null}")

        # 5) 孤儿菜式归零
        orphan = _scalar(
            db,
            "SELECT count(*) FROM core.dish d WHERE NOT d.is_deleted"
            " AND NOT EXISTS (SELECT 1 FROM core.dish_ingredient di WHERE di.dish_id = d.dish_id)",
        )
        check("孤儿菜式归零", orphan == 0, f"orphan={orphan}")

        # 6) 少盐变体 base 回查（repository 对 -LS 回填 dish_meta 依赖基础菜存在且有 meta）
        ls_broken = _scalar(
            db,
            "SELECT count(*) FROM core.dish v"
            " WHERE NOT v.is_deleted AND v.dish_id LIKE '%-LS'"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM core.dish b"
            "   WHERE NOT b.is_deleted AND b.dish_id = left(v.dish_id, -3)"
            "     AND b.dish_meta IS NOT NULL AND b.dish_meta->>'roles' IS NOT NULL"
            " )",
        )
        check("少盐变体 base 回查无断链", ls_broken == 0, f"ls_broken={ls_broken}")

        # 7) 死食材不挂活菜（软删的食材不得被活菜式引用，否则 _DISH_SQL 聚合丢料）
        dead_ref = _scalar(
            db,
            "SELECT count(*) FROM core.dish d"
            " JOIN core.dish_ingredient di ON di.dish_id = d.dish_id"
            " JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id"
            " WHERE NOT d.is_deleted AND i.is_deleted",
        )
        check("死食材不挂活菜", dead_ref == 0, f"dead_ref={dead_ref}")
    finally:
        db.rollback()
        db.close()

    width = max(len(n) for n, _, _ in CHECKS)
    failed = 0
    for name, ok, detail in CHECKS:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f"  —  {detail}" if detail else ""))
        if not ok:
            failed += 1

    print(f"\n数据对照：{len(CHECKS) - failed}/{len(CHECKS)} 通过")
    if failed:
        print(f"{failed} 项不通过：库表口径与窗口③交付基线不符，或清洗未收口。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
