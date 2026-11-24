# -*- coding: utf-8 -*-
"""52 · 按《中国食物成分表·完整版》校正膳食纤维值（窗口③ 数据线，2026-11-23）。

数据源：`数据/中国食物成分表-完整版.xls`（1284 条，纤维 0 缺失，全类别）。
对照后逐条定为显式映射（避开子串错配），并含 3 处团队口径：
  - 莲藕 1.2（完整版「藕（莲藕）」）
  - 豆腐干 1.8（完整版「豆腐干（香干）」）
  - 杏仁 12.0（团队口径 ≈12g，巴旦木；完整版裸「杏仁」为苦杏仁 19.2，不取）

用法：
  python 52_纤维校正_中国食物成分表.py            # dry-run：只出对照表（默认）
  python 52_纤维校正_中国食物成分表.py --apply    # 生成并执行回填 SQL
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

DB_URL = "host=localhost dbname=diet_agent user=postgres password=postgres_dev"

#: 动物性/油脂/纯糖/酱油 —— 确定不含膳食纤维（完整版全类别均为 0）
ZERO_FIBER: list[str] = [
    "鸭肉", "黄花鱼", "牡蛎", "五花肉", "火腿", "羊肉", "鱿鱼", "腊肠", "猪肝",
    "牛奶", "草鱼", "带鱼", "鸭蛋", "鲫鱼", "河蟹", "鲤鱼", "鸡腿",
    "花生油", "椰子油", "黄油", "白糖", "冰糖", "蜂蜜", "酱油",
]

#: 植物性食材 → (最终纤维值 or None=表无保留估算, 完整版条目, 备注)
PLANT_MAP: dict[str, tuple[float | None, str, str]] = {
    "空心菜": (1.4, "蕹菜（空心菜）", ""),
    "银耳":   (30.4, "银耳（白木耳）", "干重"),
    "莲藕":   (1.2, "藕（莲藕）", "团队口径"),
    "豆豉":   (5.9, "豆豉（五香）", ""),
    "柿子":   (None, "", "完整版无真柿子"),
    "面包":   (0.5, "面包", ""),
    "豆腐皮": (0.2, "豆腐皮", ""),
    "年糕":   (0.8, "年糕", ""),
    "莴笋":   (0.6, "莴苣笋（莴苣）", "鲜茎"),
    "番茄酱": (2.1, "番茄酱（罐头）", ""),
    "香菜":   (1.2, "芫荽（香菜，香荽）", ""),
    "芝麻":   (9.8, "芝麻（白）", ""),
    "杏仁":   (12.0, "杏仁（巴旦木，团队口径≈12g）", "团队口径"),
    "豆腐干": (1.8, "豆腐干（香干）", "香干·团队口径"),
    "面条":   (0.8, "面条（生，代表值）", "完整版无统一代表值，取代表值0.8"),
    "橙子":   (0.6, "橙", "完整版无匹配，取0.6"),
    "桃":     (1.3, "桃", ""),
    "馒头":   (1.5, "馒头（蒸，标粉）", ""),
    "腐竹":   (1.0, "腐竹", ""),
    "蒜苗":   (1.8, "蒜苗（蒜苔）", ""),
    "西瓜":   (0.2, "西瓜（京欣1号/郑州3号）", ""),
    "枇杷":   (0.8, "枇杷", ""),
    "荔枝":   (0.5, "荔枝（鲜）", ""),
    "苹果":   (1.2, "苹果", ""),
    "红苋菜": (1.8, "苋菜（紫，紫苋菜红苋）", "已并入苋菜"),
    "葡萄":   (0.4, "葡萄", ""),
    "木耳":   (29.9, "木耳（黑木耳，云耳）", "干重"),
    "丝瓜":   (0.6, "丝瓜", ""),
    "米粉":   (0.3, "米粉（排米粉）", ""),
    "芋头":   (1.0, "芋头（芋艿，毛芋）", ""),
    "核桃":   (9.5, "核桃（干，胡桃）", ""),
    "苋菜":   (1.8, "苋菜（紫，紫苋菜红苋）", "紫红苋"),
    "茼蒿":   (1.2, "茼蒿（蓬蒿菜艾菜）", ""),
    "龙眼":   (None, "", "完整版仅桂圆(干)2.0，鲜缺"),
    "黄豆芽": (1.5, "黄豆芽", ""),
    "葵花子": (6.1, "葵花子（生）", ""),
    "猕猴桃": (2.6, "猕猴桃（中华猕猴桃，羊桃）", ""),
    "竹笋":   (1.8, "竹笋", "鲜竹笋"),
    "米饭":   (0.2, "米饭（蒸，粳米）", ""),
    "杨梅":   (1.0, "杨梅（树梅，山杨梅）", ""),
    "梨":     (2.0, "梨", ""),
    "干辣椒": (None, "", "调味料不在两表"),
    "山楂":   (3.1, "红果（山里红，大山楂）", ""),
    "糯米":   (0.8, "糯米（江米）", ""),
    "豆浆":   (1.1, "豆浆", ""),
    "白菜薹": (1.7, "白菜苔（菜苔菜心）", "白菜薹/菜苔/菜心同物"),
    "生菜":   (0.7, "生菜", ""),
}


def main() -> int:
    apply = "--apply" in sys.argv

    names = ZERO_FIBER + list(PLANT_MAP.keys())
    rows: dict[str, dict] = {}
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, food_id, is_deleted, fiber_g FROM core.ingredient WHERE name = ANY(%s)",
                (names,),
            )
            for name, food_id, is_deleted, fiber in cur.fetchall():
                rows[name] = {"food_id": food_id, "deleted": is_deleted, "fiber": fiber}

    def src_of(value: float) -> str:
        return "中国食物成分表（完整版）"

    lines = ["# 纤维校正对照表（中国食物成分表·完整版）", ""]
    lines.append("| 食材 | food_id | 状态 | 现值 | 定值 | 依据/条目 | 动作 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")

    n_fix = n_confirm = n_miss = n_skip = 0
    updates: list[tuple[str, float, str]] = []

    def handle(name: str, target: float | None, basis: str, note: str) -> None:
        nonlocal n_fix, n_confirm, n_miss, n_skip
        info = rows.get(name)
        if info is None:
            lines.append(f"| {name} | ? | 库无 | - | - | - | 库无此食材 | {note} |")
            return
        cur = info["fiber"]; deleted = info["deleted"]; fid = info["food_id"]
        if deleted:
            action, n_skip = "跳过(软删)", n_skip + 1
        elif target is None:
            action, n_miss = "表缺/无匹配-保留估算", n_miss + 1
        elif cur is not None and abs(float(cur) - target) < 0.001:
            action, n_confirm = "确认(改source)", n_confirm + 1
            updates.append((name, target, basis))
        else:
            action, n_fix = "校正", n_fix + 1
            updates.append((name, target, basis))
        lines.append(
            f"| {name} | {fid} | {'软删' if deleted else '活'} | "
            f"{cur if cur is not None else 'NULL'} | {target if target is not None else '—'} | "
            f"{basis or '—'} | {action} | {note} |"
        )

    for name in ZERO_FIBER:
        handle(name, 0.0, "动物性/油脂/纯糖不含纤维", "")
    for name, (val, entry, note) in PLANT_MAP.items():
        handle(name, val, entry or "", note)

    lines.append("")
    lines.append(f"统计：校正 {n_fix} · 确认 {n_confirm} · 表缺/无匹配 {n_miss} · 软删跳过 {n_skip}")
    lines.append("")
    lines.append("> 「确认」= 现值与定值一致，仅把 source 从 check 升 official；「校正」= 现值改定值并回填 source。")

    out_md = Path(__file__).with_name("52_纤维校正对照表.md")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[对照表已写入 {out_md.name}]")

    if apply and updates:
        sql_path = Path(__file__).with_name("52_纤维校正回填.sql")
        sql_lines = [
            "-- 52 · 纤维校正回填（中国食物成分表·完整版，自动生成，2026-11-23）",
            "BEGIN;",
        ]
        for name, val, basis in updates:
            src = f"中国食物成分表（完整版）·{basis}" if basis else "中国食物成分表（完整版）"
            sql_lines.append(
                f"UPDATE core.ingredient SET fiber_g = {val}, "
                f"source_row = COALESCE(source_row,'{{}}'::jsonb) || jsonb_build_object("
                f"'supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients','{{}}'::jsonb) || jsonb_build_object("
                f"'fiber_g', jsonb_build_object('value', {val}, 'unit', 'g/100g', "
                f"'source', '{src}', 'data_quality', 'official'))) "
                f"WHERE name = '{name}';"
            )
        sql_lines.append("COMMIT;")
        sql_path.write_text("\n".join(sql_lines), encoding="utf-8")
        print(f"[回填 SQL 已生成 {sql_path.name}，共 {len(updates)} 条 UPDATE]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
