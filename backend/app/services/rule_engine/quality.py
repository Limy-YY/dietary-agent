"""Deterministic role, meal fit and diversity scoring; not a safety classifier.

Provisional keyword mapping: review the real catalogue with the data team.
Unknown role does not exclude a dish. Never infer allergy safety from these roles.
"""
from collections import Counter
from itertools import combinations

ROLE_HINTS = {
    "蛋白质菜": ("鸡", "鸭", "猪", "牛肉", "羊肉", "鱼", "虾", "蛋", "豆腐", "豆干", "水产", "肉类", "畜禽"),
    "蔬菜": ("蔬菜", "青菜", "菠菜", "西兰花", "白菜", "生菜", "芹菜", "胡萝卜", "番茄", "黄瓜", "冬瓜", "菌菇", "木耳", "芦笋", "油麦菜", "紫甘蓝", "莴笋", "菜花", "香菇"),
    "奶类": ("酸奶", "牛奶", "奶酪", "乳制品", "奶类"),
    "水果": ("水果", "香蕉", "苹果", "草莓", "蓝莓", "猕猴桃", "橙子", "梨", "芒果"),
}
BREAKFAST_HINTS = ("燕麦", "粥", "馒头", "包子", "全麦面包", "酸奶", "牛奶", "鸡蛋", "水果", "豆浆")
SEASONING = ("油", "盐", "糖", "醋", "酱", "胡椒", "葱", "蒜", "姜", "水", "料酒", "味精", "鸡精", "香料")


def dish_roles(dish):
    # Keep the persisted role enum unchanged. These are internal multi-role tags.
    # Use the category and dish name first, with ingredient names as fallback/evidence.
    label = " ".join([dish.name or "", dish.category or "", *(dish.tags or [])])
    blob = " ".join([label, *map(str, dish.ingredient_names or [])])
    roles = set()
    if dish.is_staple or any(h in label for h in ("燕麦", "面包", "馒头", "杂粮", "米粉")):
        roles.add("主食")
    if dish.is_soup or "汤" in label or "羹" in label:
        roles.add("汤羹")
    for role, hints in ROLE_HINTS.items():
        if any(h in blob for h in hints):
            roles.add(role)
    if not roles:
        roles.add("未知")
    if len(roles - {"汤羹", "未知"}) > 1:
        roles.add("复合菜")
    return frozenset(roles)


def main_ingredients(dish):
    return {str(n).strip() for n in dish.ingredient_names or []
            if str(n).strip() and not any(w in str(n) for w in SEASONING)}


def similarity(a,b):
    left, right = main_ingredients(a), main_ingredients(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def breakfast_special(dish):
    return any(h in dish.name for h in ("酸奶", "燕麦", "牛奶"))


def structure_penalty(combo, meal_type):
    role_sets = [dish_roles(d) for d in combo]
    covered = set().union(*role_sets)
    penalty = 0.0
    if "主食" not in covered:
        penalty += .25
    if meal_type == "早":
        if not covered.intersection({"蛋白质菜", "奶类"}):
            penalty += .35
    elif "蛋白质菜" not in covered:
        penalty += .45
    if meal_type == "早":
        # Western and Chinese breakfast options remain legal for other meals.
        for dish, roles in zip(combo, role_sets):
            if not (any(h in dish.name for h in BREAKFAST_HINTS) or roles & {"奶类", "水果"}):
                penalty += .07
        if "汤羹" in covered:
            penalty += .10
    else:
        if "蔬菜" not in covered:
            penalty += .18
        for dish, roles in zip(combo, role_sets):
            if breakfast_special(dish):
                penalty += .45
    for a,b in combinations(combo,2):
        # Ingredient and role overlap are soft quality costs, not taboo rules.
        sim = similarity(a,b)
        if dish_roles(a) & dish_roles(b) - {"未知", "复合菜"}:
            penalty += .5 * sim
        if "燕麦" in a.name and "燕麦" in b.name:
            penalty += .45
    return penalty


def repetition_cost(candidate, previous):
    """All chosen dishes, ingredients and exact meal combinations; common staples cost less."""
    if not previous:
        return 0.0
    counts = Counter(d for other in previous for d in other.dish_ids)
    own = set(candidate.dish_ids)
    penalty = sum((.035 if "主食" in dish_roles(p.facts) and not breakfast_special(p.facts) else .20) * counts[p.dish_id]
                  for p in candidate.portions)
    for other in previous:
        if own == set(other.dish_ids):
            penalty += .75
        for p in candidate.portions:
            if p.facts.is_staple:
                continue
            penalty += .07 * max((similarity(p.facts, q.facts) for q in other.portions), default=0)
    return penalty


def selected(slot):
    return next((c for c in slot.candidates if c.candidate_id == slot.selected_candidate_id), None)
