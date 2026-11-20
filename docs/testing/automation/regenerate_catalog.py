# -*- coding: utf-8 -*-
"""重写 meal_templates._ROWS 目录，对齐 DB 当前 170 道基础菜。

修复 IMP-045：旧目录只覆盖 110 道（001~110），DB 已扩到 170 道并重排编号，
导致 110 道被判「未知」、排除出候选生成。

策略：
- DISH-001~060：保留旧目录（与 DB 一致）。
- DISH-061~120（陈媛版 60 道）：新增，按 category + 食材初判。
- DISH-121~170（白米饭…白粥 50 道）：旧目录 061~110 重排 key（撞名补「家常版」后缀）。

输出：把新 _ROWS 写到 `_new_rows.txt`（供人工核对），不直接改源码。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import get_db  # noqa: E402
from app.services.rule_engine.repository import SqlDataSource  # noqa: E402

SRC = ROOT / "backend/app/services/rule_engine/meal_templates.py"
OUT = ROOT / "_new_rows.txt"

ORDER = ["S", "P", "V", "T", "D", "F"]

VEG_KEYWORDS = ("白菜", "生菜", "菠菜", "苋菜", "茼蒿", "空心菜", "油菜", "西兰花", "菜花",
                "花椰菜", "黄瓜", "番茄", "西红柿", "胡萝卜", "白萝卜", "萝卜", "芹菜", "茄子",
                "丝瓜", "西葫芦", "四季豆", "苦瓜", "甜椒", "青椒", "洋葱", "韭菜", "豆芽",
                "蘑菇", "香菇", "金针菇", "海带", "莴笋", "莲藕", "竹笋", "冬瓜", "南瓜",
                "土豆", "红薯", "玉米", "山药", "木耳", "青豌豆", "鹰嘴豆", "菜心", "大白菜",
                "小白菜", "青菜", "菜薹", "笋")

FRUIT_KEYWORDS = ("苹果", "香蕉", "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃")

FAMILY_RULES = [
    ("鸡蛋", ("蛋",)),
    ("牛奶", ("牛奶",)),
    ("鸡肉", ("鸡",)),
    ("鸭肉", ("鸭",)),
    ("水产", ("鱿鱼", "蟹")),
    ("内脏", ("肝",)),
    ("猪肉", ("猪", "里脊", "五花肉", "排骨")),
    ("牛肉", ("牛",)),
    ("羊肉", ("羊",)),
    ("鱼", ("鱼", "黄花鱼", "带鱼", "鲈鱼", "鲤鱼", "草鱼", "鲫鱼", "三文鱼", "鳕鱼")),
    ("虾", ("虾",)),
    ("贝类", ("蛤蜊", "牡蛎", "扇贝", "蛏")),
    ("豆腐", ("豆腐", "豆干", "腐竹", "豆皮")),
    ("豆制品", ("豆浆", "黄豆", "鹰嘴豆")),
]


def family_of(blob: str) -> str:
    for fam, kws in FAMILY_RULES:
        if any(k in blob for k in kws):
            return fam
    return "-"


def staple_of(name: str, roles: set) -> str:
    if "S" not in roles:
        return "-"
    if "粥" in name:
        return "porridge"
    if any(k in name for k in ("燕麦", "酸奶")):
        return "sweet"
    if any(k in name for k in ("红薯", "南瓜", "土豆", "山药", "糯米")):
        return "tuber"
    if any(k in name for k in ("饭", "面", "馒头", "面包", "米粉", "杂粮", "玉米")):
        return "grain"
    return "-"


def breakfast_of(name: str, roles: set) -> str:
    if any(k in name for k in ("燕麦", "酸奶碗", "牛奶粥")):
        return "B"
    if any(k in name for k in ("苹果", "香蕉", "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃")):
        return "F"
    if any(k in name for k in ("豆浆", "牛奶", "酸奶")):
        return "M"
    if "蛋" in name and "汤" not in name and "羹" not in name:
        return "E"
    if any(k in name for k in ("粥", "面", "馒头", "米粉", "米线")):
        return "C"
    if "S" in roles and any(k in name for k in ("玉米", "红薯", "南瓜", "土豆", "面包", "山药")):
        return "N"
    if any(k in name for k in ("拌", "白灼", "盐水", "凉拌", "豆腐")):
        return "L"
    return "-"


def commonness_of(name: str) -> int:
    if any(k in name for k in ("饭", "粥", "馒头", "面包", "玉米", "苹果", "香蕉",
                               "橙子", "梨", "葡萄", "西瓜", "桃", "猕猴桃", "牛奶", "豆浆")):
        return 0
    if any(k in name for k in ("炖", "烧", "烩", "卤", "蛤蜊", "牡蛎", "鱿鱼", "猪肝", "肝")):
        return 2
    return 1


def complexity_of(name: str) -> int:
    if any(k in name for k in ("炖", "烧", "烩", "卤", "焖", "糯米饭")):
        return 2
    if any(k in name for k in ("炒", "拌", "沙拉", "汤")):
        return 1
    return 0


def classify(d) -> tuple[str, str, str, str, int, int]:
    """返回 (roles, family, staple, breakfast, commonness, complexity)。"""
    cat = (d.category or "").strip()
    name = d.name or ""
    blob = " ".join(d.ingredient_names or [])
    family = family_of(blob)
    if "豆芽" in name or "豆芽" in blob:
        family = "-"  # 豆芽是蔬菜不是豆制品蛋白
    is_protein = family not in ("-", "牛奶")

    roles: set[str] = set()
    if cat == "主食":
        roles.add("S")
    if cat == "汤羹":
        roles.add("T")
    if cat in ("畜禽肉类", "水产类", "蛋豆类") or is_protein:
        roles.add("P")
    if cat == "饮品" or any(k in blob for k in ("牛奶", "酸奶")):
        roles.add("P" if "豆浆" in name else "D")
    if cat == "水果" or any(k in blob for k in FRUIT_KEYWORDS):
        roles.add("F")
    if cat == "主食":
        # 主食里的菜只认非淀粉类（番茄/青菜等）；土豆/玉米/南瓜是主食本身
        if any(k in name for k in ("番茄", "青菜", "蔬菜", "白菜", "鸡丝")):
            roles.add("V")
    else:
        # 非主食：淀粉类（土豆/玉米/南瓜/山药）也算 V，如「土豆炖鸡」里的土豆
        if cat == "蔬菜类" or any(k in blob for k in VEG_KEYWORDS):
            roles.add("V")

    roles_str = "".join(c for c in ORDER if c in roles)
    if not roles_str:
        roles_str = "V"  # 兜底：无类别信息默认蔬菜

    family = family if "P" in roles_str else "-"
    staple = staple_of(name, roles)
    breakfast = breakfast_of(name, roles)
    return roles_str, family, staple, breakfast, commonness_of(name), complexity_of(name)


def parse_old_rows(src_text: str) -> dict[str, tuple]:
    m = re.search(r"_ROWS = '''(.*?)'''", src_text, re.S)
    assert m, "未找到 _ROWS 定义"
    out: dict[str, tuple] = {}
    for line in m.group(1).splitlines():
        parts = line.split("|")
        key, name, roles, bf, staple, family = parts[:6]
        pri = parts[6:] if len(parts) > 6 else []
        common = int(pri[0]) if pri else (2 if key in {"029", "030", "053", "054", "059"} else 1)
        complex_ = int(pri[1]) if len(pri) > 1 else (2 if key in {"029", "030", "048", "051", "052", "053", "055"} else 1)
        out[key] = (name, roles, bf, staple, family, common, complex_)
    return out


def main() -> None:
    src_text = SRC.read_text(encoding="utf-8")
    old = parse_old_rows(src_text)
    by_name = {v[0]: (k, v) for k, v in old.items()}

    gen = get_db()
    db = next(gen)
    try:
        dishes = SqlDataSource(db).get_dish_facts()
    finally:
        db.rollback()
        gen.close()

    base = [d for d in dishes if not d.dish_id.endswith("-LS")]
    base.sort(key=lambda d: d.dish_id)

    lines: list[str] = []
    new_cnt = rekey_cnt = keep_cnt = 0
    for d in base:
        num = d.dish_id[len("DISH-"):]
        if num in old and old[num][0] == d.name:
            # 001~060 保留
            _, roles, bf, staple, family, common, complex_ = old[num]
            lines.append(f"{num}|{d.name}|{roles}|{bf}|{staple}|{family}|{common}|{complex_}")
            keep_cnt += 1
        elif d.name in by_name:
            # 重排 key（白米饭…白粥；含 清蒸带鱼/洋葱炒蛋 撞名）
            old_key, (_, roles, bf, staple, family, common, complex_) = by_name[d.name]
            lines.append(f"{num}|{d.name}|{roles}|{bf}|{staple}|{family}|{common}|{complex_}")
            rekey_cnt += 1
        else:
            roles, family, staple, bf, common, complex_ = classify(d)
            lines.append(f"{num}|{d.name}|{roles}|{bf}|{staple}|{family}|{common}|{complex_}")
            new_cnt += 1

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"基础菜 {len(base)} 道 -> 保留 {keep_cnt} / 重排 {rekey_cnt} / 新增 {new_cnt}")
    print(f"新 _ROWS 已写到 {OUT}")


if __name__ == "__main__":
    main()
