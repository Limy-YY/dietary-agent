# -*- coding: utf-8 -*-
"""生成《菜式目录补录清单》：DB 里被规则引擎目录漏掉/错位的菜。

背景：rule_engine/meal_templates.py 的 `_ROWS` 目录硬编码了 110 道菜
（DISH-001~110）。数据岗后来把菜式扩到 213 道（170 基础 + 43 少盐）并重排了
编号，目录没跟着更新，导致 DISH-061~170 共 110 道被判「未知」、生成候选时
被排除。

本脚本只读 DB，输出 Markdown 清单，含「自动初判」的烹饪元数据（角色/家族/
主食类型/早餐用途/常见度/复杂度），供数据岗复核后回填 `_ROWS`。

运行（backend 目录下，需 DB 可达）：
    ..\\.venv\\Scripts\\python.exe docs\\testing\\automation\\gen_catalog_backfill.py
输出：docs/testing/菜式目录补录清单.md
"""
from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # github仓库/
sys.path.insert(0, str(ROOT / "backend"))

from app.db import get_db  # noqa: E402
from app.services.rule_engine.repository import SqlDataSource  # noqa: E402
from app.services.rule_engine.meal_templates import CATALOG  # noqa: E402


# ---- 自动初判的启发式关键词（只做建议，最终以数据岗复核为准）----
STAPLE_WORDS = ("饭", "粥", "面", "馒头", "面包", "米粉", "燕麦", "杂粮", "糯米饭",
                "土豆", "红薯", "南瓜", "玉米", "山药")
DAIRY_WORDS = ("牛奶", "酸奶")
FRUIT_WORDS = ("苹果", "香蕉", "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃")
SOUP_WORDS = ("汤", "羹", "粥")
VEG_WORDS = ("白菜", "生菜", "菠菜", "苋菜", "茼蒿", "空心菜", "油菜", "西兰花", "菜花",
             "花椰菜", "黄瓜", "番茄", "西红柿", "胡萝卜", "白萝卜", "萝卜", "芹菜", "茄子",
             "丝瓜", "西葫芦", "四季豆", "苦瓜", "甜椒", "青椒", "洋葱", "韭菜", "豆芽",
             "蘑菇", "香菇", "金针菇", "海带", "莴笋", "莲藕", "竹笋", "冬瓜", "南瓜",
             "土豆", "红薯", "玉米", "山药", "木耳", "青豌豆", "鹰嘴豆", "菜心", "大白菜",
             "小白菜", "油菜", "莲藕", "青菜")

FAMILY_RULES = [
    ("鸡蛋", ("蛋",)),                 # 先于「鸡」，避免鸡蛋羹/炒蛋被归到鸡肉
    ("牛奶", ("牛奶",)),               # 先于「牛」，避免牛奶被归到牛肉
    ("鸡肉", ("鸡",)),
    ("鸭肉", ("鸭",)),
    ("水产", ("鱿鱼", "蟹")),          # 先于「鱼」，避免鱿鱼被归到鱼
    ("内脏", ("肝",)),                 # 先于「猪/牛」，猪肝等
    ("猪肉", ("猪", "里脊", "五花肉", "排骨")),
    ("牛肉", ("牛",)),
    ("羊肉", ("羊",)),
    ("鱼", ("鱼", "黄花鱼", "带鱼", "鲈鱼", "鲤鱼", "草鱼", "鲫鱼", "三文鱼", "鳕鱼")),
    ("虾", ("虾",)),
    ("贝类", ("蛤蜊", "牡蛎", "扇贝", "蛏")),
    ("豆腐", ("豆腐", "豆干", "腐竹", "豆皮")),
    ("豆制品", ("豆浆", "黄豆", "鹰嘴豆")),
]


def _family(blob: str) -> str:
    for fam, kws in FAMILY_RULES:
        if any(k in blob for k in kws):
            return fam
    return ""


def suggest_roles(dish) -> str:
    """返回 roles 编码串（S主食/P蛋白质菜/V蔬菜/T汤羹/D奶类/F水果）。"""
    name = dish.name or ""
    blob = " ".join([name, *(dish.tags or []), *(dish.ingredient_names or [])])
    codes = []
    if dish.is_staple or any(k in blob for k in STAPLE_WORDS):
        codes.append("S")
    if any(k in blob for k in DAIRY_WORDS):
        codes.append("D")
    if any(k in blob for k in FRUIT_WORDS):
        codes.append("F")
    if _family(blob):
        codes.append("P")
    if any(k in blob for k in VEG_WORDS):
        codes.append("V")
    if any(k in name for k in SOUP_WORDS) or dish.is_soup:
        codes.append("T")
    return "".join(codes) or "?"


def suggest_staple(dish) -> str:
    name = dish.name or ""
    blob = " ".join([name, *(dish.ingredient_names or [])])
    if any(k in name for k in ("粥",)):
        return "porridge"
    if any(k in name for k in ("燕麦", "酸奶")):
        return "sweet"
    if any(k in name for k in ("土豆", "红薯", "南瓜", "玉米", "山药")):
        return "tuber"
    if any(k in blob for k in ("饭", "面", "馒头", "面包", "米粉", "杂粮", "糯米饭")):
        return "grain"
    return "-"


def suggest_breakfast(dish) -> str:
    name = dish.name or ""
    if any(k in name for k in ("燕麦", "酸奶碗", "牛奶粥")):
        return "B"
    if any(k in name for k in ("苹果", "香蕉", "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃")):
        return "F"
    if any(k in name for k in ("豆浆", "牛奶", "酸奶")):
        return "M"
    if any(k in name for k in ("蛋",)):
        return "E"
    if any(k in name for k in ("馒头", "面包", "玉米", "面", "粥", "土豆", "红薯", "南瓜")):
        return "C" if any(k in name for k in ("粥", "面", "馒头")) else "N"
    return "-"


def suggest_complexity(name: str) -> int:
    if any(k in name for k in ("炖", "烧", "烩", "卤", "焖", "糯米饭")):
        return 2
    if any(k in name for k in ("炒", "拌", "沙拉", "汤")):
        return 1
    return 0  # 蒸/煮/白灼/清蒸/凉拌/水煮


def suggest_commonness(name: str) -> int:
    # 主食/水果/基本蒸煮菜为 0；带复合做法或小众菜为 1~2
    if any(k in name for k in ("饭", "粥", "馒头", "面包", "玉米", "苹果", "香蕉",
                               "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃", "牛奶", "豆浆")):
        return 0
    if any(k in name for k in ("炖", "烧", "烩", "卤", "蛤蜊", "牡蛎", "鱿鱼", "猪肝", "肝")):
        return 2
    return 1


def main() -> None:
    gen = get_db()
    db = next(gen)
    try:
        dishes = SqlDataSource(db).get_dish_facts()
    finally:
        db.rollback()
        gen.close()

    base = [d for d in dishes if not d.dish_id.endswith("-LS")]

    # 目录按「菜名」反查，用于识别「id 错位但名字还在」的 50 道（白米饭…白粥）。
    by_name: OrderedDict[str, tuple] = OrderedDict()
    for did, p in sorted(CATALOG.items()):
        by_name.setdefault(p.name, (did, p))

    need_new = []  # 目录里完全没有名字 → 需新增
    need_rekey = []  # 目录里有同名但 id 不同 → 需重排 key
    for d in base:
        c = CATALOG.get(d.dish_id)
        if c is not None and c.name == d.name:
            continue  # 已正确
        if d.name in by_name:
            need_rekey.append((d, by_name[d.name]))
        else:
            need_new.append(d)

    need_new.sort(key=lambda d: d.dish_id)
    need_rekey.sort(key=lambda x: x[0].dish_id)

    out = []
    out.append("# 菜式目录补录清单（规则引擎 meal_templates._ROWS 缺口）\n")
    out.append("> 自动生成，供数据岗复核后回填 `backend/app/services/rule_engine/meal_templates.py` 的 `_ROWS`。\n")
    out.append("> roles 编码：S=主食 P=蛋白质菜 V=蔬菜 T=汤羹 D=奶类 F=水果；"
               "breakfast：B甜粥碗 N中性主食 E温和蛋 M奶/豆浆 F水果 C咸味早餐主食 -午晚。\n")
    out.append("> commonness/complexity：0 常见/简单，1 常规，2 特色/复杂。\n")
    out.append(f"> 统计：DB 基础菜 {len(base)} 道；需新增 {len(need_new)} 道；需重排 key {len(need_rekey)} 道。\n")

    out.append("\n## 一、需新增（目录里完全没有，共 {} 道）\n".format(len(need_new)))
    out.append("| dish_id | 菜名 | 建议roles | 建议family | 建议staple | 建议breakfast | 常见度 | 复杂度 | 食材（供复核） |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for d in need_new:
        blob = " ".join([d.name or "", *(d.ingredient_names or [])])
        ing = "、".join(d.ingredient_names or [])
        out.append(
            f"| {d.dish_id} | {d.name} | {suggest_roles(d)} | {_family(blob) or '-'} | "
            f"{suggest_staple(d)} | {suggest_breakfast(d)} | {suggest_commonness(d.name)} | "
            f"{suggest_complexity(d.name)} | {ing or '-'} |"
        )

    out.append("\n## 二、需重排 key（目录里有同名菜但编号错位，共 {} 道）\n".format(len(need_rekey)))
    out.append("> 这 50 道的元数据在目录里已存在，只是 key 从 061~110 错成了 121~170，把 key 改对即可，元数据照抄。\n")
    out.append("| DB dish_id | 菜名 | 目录里现在的 key | 目录元数据（roles/family/staple/breakfast/常见/复杂） |")
    out.append("|---|---|---|---|")
    for d, (old_key, p) in need_rekey:
        roles = "".join(sorted({
            "主食": "S", "蛋白质菜": "P", "蔬菜": "V", "汤羹": "T", "奶类": "D", "水果": "F", "复合菜": "?"
        }.get(r, "?") for r in p.roles if r != "复合菜"))
        out.append(
            f"| {d.dish_id} | {d.name} | {old_key} | {roles}/{p.family}/{p.staple}/{p.breakfast}/{p.commonness}/{p.complexity} |"
        )

    dest = ROOT / "docs/testing/菜式目录补录清单.md"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"已写出 {len(need_new) + len(need_rekey)} 道的补录清单 -> {dest}")
    print(f"  需新增 {len(need_new)} 道，需重排 key {len(need_rekey)} 道")


if __name__ == "__main__":
    main()
