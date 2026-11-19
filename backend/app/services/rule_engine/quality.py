"""Default culinary quality and cross-slot diversity; not medical safety rules."""
from collections import Counter
from itertools import combinations
from .meal_templates import profile, dish_roles, template_for

SEASONING = ('油','盐','糖','醋','酱','胡椒','葱','蒜','姜','料酒','味精','鸡精','香料','饮用水')


def main_ingredients(dish):
    return {str(n).strip() for n in dish.ingredient_names or []
            if str(n).strip() and not any(w in str(n) for w in SEASONING)}


def similarity(a,b):
    left,right=main_ingredients(a),main_ingredients(b)
    return len(left&right)/len(left|right) if left and right else 0.0


def breakfast_special(dish):
    return profile(dish).staple == 'sweet'


def structure_penalty(combo, meal_type):
    """Softly rank nutrition coverage and practicality; never impose a plate formula."""
    kinds=[profile(d) for d in combo]
    covered=set().union(*(p.roles for p in kinds))
    penalty=0.0 if template_for(combo,meal_type) else 2.0
    # Within the same nutrition/safety band, ordinary simple home dishes are the
    # default.  This is culinary preference metadata, never a medical override.
    penalty += .04 * sum(p.commonness for p in kinds)
    penalty += .03 * sum(p.complexity for p in kinds)
    # Specialty is not a separate priority class; commonness and complexity already contribute softly.
    staples=sum('主食' in p.roles for p in kinds)
    proteins=sum('蛋白质菜' in p.roles for p in kinds)
    soups=sum('汤羹' in p.roles for p in kinds)
    if meal_type=='早':
        penalty+=.10*max(0,len(combo)-2)
        penalty+=.38*max(0,staples-1)
        penalty+=.32*sum(p.breakfast=='-' for p in kinds)
        # A milk/soy drink with a cooked savory side is possible, but usually
        # less executable than pairing either one with an egg, fruit or staple.
        if any(p.breakfast=='M' for p in kinds):
            penalty+=.30*sum(p.breakfast=='L' or '汤羹' in p.roles for p in kinds)
        if not covered & {'蛋白质菜','奶类'}: penalty+=.18
        if any(p.staple=='sweet' for p in kinds):
            penalty += .22*sum(p.breakfast in ('L','-') or '汤羹' in p.roles for p in kinds if p.staple!='sweet')
    else:
        penalty+=.05*max(0,len(combo)-3)
        penalty+=.38*max(0,staples-1)
        penalty+=.10*max(0,proteins-2)
        penalty+=.14*max(0,soups-1)
        if '蔬菜' not in covered: penalty+=.10
        if '蛋白质菜' not in covered: penalty+=.10
    # Penalize unnecessary same-ingredient overlap, but keep staple + vegetable combinations.
    for a,b in combinations(combo,2):
        penalty+=.28*similarity(a,b)
        if breakfast_special(a) and breakfast_special(b): penalty+=1.0
    from .portion_policy import everyday_cost
    penalty += everyday_cost(combo)
    return penalty


def repetition_cost(candidate,previous):
    if not previous: return 0.0
    from .meal_templates import base_dish_id
    recent=previous[-6:]
    counts=Counter(base_dish_id(d) for c in previous for d in c.dish_ids)
    recent_counts=Counter(base_dish_id(d) for c in recent for d in c.dish_ids)
    adjacent={base_dish_id(d) for d in previous[-1].dish_ids}
    penalty=0.
    veg_families=Counter(profile(p.facts).family for c in previous for p in c.portions
                         if profile(p.facts).roles=={'蔬菜'})
    for p in candidate.portions:
        meta=profile(p.facts); key=base_dish_id(p.dish_id)
        if meta.roles=={'主食'}:continue
        if meta.roles in ({'奶类'},{'水果'}) or key in ('DISH-067','DISH-068','DISH-085'):
            weight=.035
        elif meta.roles=={'蔬菜'}:weight=.26
        else:weight=.15
        penalty+=weight*(.55*recent_counts[key]**1.25+.45*counts[key]**1.25)
        if key in adjacent:penalty+=weight*.65
        if meta.roles=={'蔬菜'}:penalty+=.045*veg_families[meta.family]
        if meta.staple=='sweet':
            penalty+=.12*sum(profile(q.facts).staple=='sweet' for c in previous for q in c.portions)
    keyset={base_dish_id(d) for d in candidate.dish_ids}
    penalty+=.65*sum(keyset=={base_dish_id(d) for d in c.dish_ids} for c in previous)
    return penalty


def selected(slot):
    return next((c for c in slot.candidates if c.candidate_id==slot.selected_candidate_id),None)
