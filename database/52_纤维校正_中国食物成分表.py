# -*- coding: utf-8 -*-
"""52 · 按《中国食物成分表（第6版·标准版）第一册·素食》校正膳食纤维值。

窗口③ 数据线（2026-11-23）。48 号补的 71 条纤维里，24 条动物性/油脂/纯糖 = 0 是确定事实不改；
本脚本只处理 47 个植物性食材，用显式映射（避开「面包鱼/柿子椒/核桃」这类子串错配）逐条对齐。

用法：
  python 52_纤维校正_中国食物成分表.py [xls路径]           # dry-run：只出对照表（默认）
  python 52_纤维校正_中国食物成分表.py [xls路径] --apply   # 生成并执行回填 SQL

依赖：xlrd（读 .xls）、psycopg（连库读当前值）。回填用 postgres 账号（core 写权限）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import xlrd
import psycopg

DB_URL = "host=localhost dbname=diet_agent user=postgres password=postgres_dev"
XLS_DEFAULT = str(
    Path(__file__).resolve().parents[2] / "数据" / "中国食物成分表2018年(标准版)第6版-第一册-素食.xls"
)

#: DB 食材名 → (xls 精确条目, 权威纤维值或 None=表缺/无匹配, 备注)
PLANT_MAP: dict[str, tuple[str | None, float | None, str]] = {
    "空心菜": ("蕹菜（空心菜）", None, "表缺纤维(-)"),
    "银耳":   ("银耳（白木耳）", 30.4, "干重"),
    "莲藕":   ("藕（莲藕）", 2.2, ""),
    "豆豉":   ("豆豉（五香）", 5.9, ""),
    "柿子":   (None, None, "表无真柿子"),
    "面包":   ("面包", 0.5, ""),
    "豆腐皮": ("豆腐皮", None, "表缺纤维(-)"),
    "年糕":   ("年糕", 0.8, ""),
    "莴笋":   (None, None, "表仅莴笋(酱)1.0，鲜缺"),
    "番茄酱": ("番茄酱（罐头）", 2.1, ""),
    "香菜":   ("香菜（芫荽，香荽）", 1.2, ""),
    "芝麻":   ("芝麻（白）", 9.8, ""),
    "杏仁":   ("杏仁", 8.0, ""),
    "豆腐干": ("豆腐干（香干）", 0.8, "香干"),
    "面条":   ("面条（生，代表值）", 0.8, ""),
    "橙子":   ("橙", 0.6, ""),
    "桃":     ("桃（代表值）", 1.0, ""),
    "馒头":   ("馒头（蒸，标粉）", 1.5, ""),
    "腐竹":   ("腐竹", 1.0, ""),
    "蒜苗":   ("蒜苗（青蒜）", 1.8, ""),
    "西瓜":   ("西瓜（代表值）", 0.2, ""),
    "枇杷":   ("枇杷", 0.8, ""),
    "荔枝":   ("荔枝（鲜）", 0.5, ""),
    "苹果":   ("苹果（代表值）", 1.7, ""),
    "红苋菜": ("苋菜（紫，红苋）", 1.8, "已并入苋菜"),
    "葡萄":   ("葡萄（代表值）", 1.0, ""),
    "木耳":   ("木耳（干，黑木耳，云耳）", 29.9, "干重"),
    "丝瓜":   ("丝瓜", None, "表缺纤维(-)"),
    "米粉":   ("籼米粉（排米粉）", 0.3, ""),
    "芋头":   ("芋头（芋艿，毛芋）", 1.0, ""),
    "核桃":   ("核桃（干，胡桃）", 9.5, ""),
    "苋菜":   ("苋菜（紫，红苋）", 1.8, "紫红苋"),
    "茼蒿":   ("茼蒿（蓬蒿菜，艾菜）", 1.2, ""),
    "龙眼":   (None, None, "表仅桂圆(干)2.0，鲜缺"),
    "黄豆芽": ("黄豆芽", 1.5, ""),
    "葵花子": ("葵花子（生）", 6.1, ""),
    "猕猴桃": ("猕猴桃（中华猕猴桃，羊桃）", 2.6, ""),
    "竹笋":   ("竹笋", 1.8, "鲜竹笋"),
    "米饭":   ("米饭（蒸，粳米）", 0.2, ""),
    "杨梅":   ("杨梅（树梅，山杨梅）", 1.0, ""),
    "梨":     ("梨（代表值）", 2.6, ""),
    "干辣椒": (None, None, "调味料不在素食册"),
    "山楂":   ("红果（山里红，大山楂）", 3.1, ""),
    "糯米":   ("糯米（江米）", 0.8, ""),
    "豆浆":   ("豆浆", None, "表缺纤维(-)"),
    "白菜薹": (None, None, "表无"),
    "生菜":   ("生菜（叶用莴苣）", None, "表缺纤维(-)"),
}


def load_xls(path: str) -> dict[str, float | None]:
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    table: dict[str, float | None] = {}

    def to_fiber(fb) -> float | None:
        if fb is None or fb == "":
            return None
        if isinstance(fb, str):
            s = fb.strip().lower()
            if s in ("-", "—", "－", "tr", "t", "trace", "微量"):
                return None  # 未定量/痕量 → 按缺失处理
            try:
                return round(float(fb), 2)
            except ValueError:
                return None
        try:
            return round(float(fb), 2)
        except (TypeError, ValueError):
            return None

    for r in range(1, sh.nrows):
        nm = str(sh.cell_value(r, 0)).strip()
        table[nm] = to_fiber(sh.cell_value(r, 7))
    return table


def main() -> int:
    apply = "--apply" in sys.argv
    xls = next((a for a in sys.argv[1:] if not a.startswith("--")), XLS_DEFAULT)
    table = load_xls(xls)

    # 取库当前值 + 是否软删
    rows: dict[str, dict] = {}
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, food_id, is_deleted, fiber_g FROM core.ingredient WHERE name = ANY(%s)",
                (list(PLANT_MAP.keys()),),
            )
            for name, food_id, is_deleted, fiber in cur.fetchall():
                rows[name] = {"food_id": food_id, "deleted": is_deleted, "fiber": fiber}

    lines: list[str] = []
    lines.append("# 纤维校正对照表（中国食物成分表 第6版·标准版·素食册）")
    lines.append("")
    lines.append("| 食材 | food_id | 状态 | 现值 | 权威值 | 匹配条目 | 动作 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")

    n_fix = n_confirm = n_miss = n_skip = 0
    updates: list[tuple[str, float, str]] = []  # (name, value, xls_entry)

    for name, (entry, aval, note) in PLANT_MAP.items():
        info = rows.get(name)
        if info is None:
            lines.append(f"| {name} | ? | 库无 | - | {aval if aval is not None else '—'} | {entry or '—'} | 库无此食材 | {note} |")
            continue
        cur = info["fiber"]
        deleted = info["deleted"]
        food_id = info["food_id"]
        if deleted:
            action = "跳过(软删)"
            n_skip += 1
        elif aval is None:
            action = "表缺/无匹配-保留估算"
            n_miss += 1
        elif cur is not None and abs(float(cur) - aval) < 0.001:
            action = "确认(改source)"
            n_confirm += 1
            updates.append((name, aval, entry or ""))
        else:
            action = "校正"
            n_fix += 1
            updates.append((name, aval, entry or ""))
        lines.append(
            f"| {name} | {food_id} | {'软删' if deleted else '活'} | "
            f"{cur if cur is not None else 'NULL'} | {aval if aval is not None else '—'} | "
            f"{entry or '—'} | {action} | {note} |"
        )

    lines.append("")
    lines.append(f"统计：校正 {n_fix} · 确认 {n_confirm} · 表缺/无匹配 {n_miss} · 软删跳过 {n_skip}")
    lines.append("")
    lines.append("> 24 条动物性/油脂/纯糖的 0 纤维为确定事实，不在本表、不回改。")
    lines.append("> 「确认」= 现值与权威值一致，仅把 source 从 check 升级为 official；「校正」= 现值改权威值并回填 source。")

    out_md = Path(__file__).with_name("52_纤维校正对照表.md")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[对照表已写入 {out_md.name}]")

    if apply and updates:
        sql_path = Path(__file__).with_name("52_纤维校正回填.sql")
        sql_lines = [
            "-- 52 · 纤维校正回填（中国食物成分表 第6版标准版，自动生成，2026-11-23）",
            "BEGIN;",
        ]
        for name, val, entry in updates:
            sql_lines.append(
                f"UPDATE core.ingredient i SET fiber_g = {val}, "
                f"source_row = COALESCE(source_row,'{{}}'::jsonb) || jsonb_build_object("
                f"'supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients','{{}}'::jsonb) || jsonb_build_object("
                f"'fiber_g', jsonb_build_object('value', {val}, 'unit', 'g/100g', "
                f"'source', '中国食物成分表（第6版标准版）·{entry}', 'data_quality', 'official'))) "
                f"WHERE name = '{name}';"
            )
        sql_lines.append("COMMIT;")
        sql_path.write_text("\n".join(sql_lines), encoding="utf-8")
        print(f"[回填 SQL 已生成 {sql_path.name}，共 {len(updates)} 条 UPDATE]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
