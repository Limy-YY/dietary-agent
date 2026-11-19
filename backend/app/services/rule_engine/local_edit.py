"""Pure candidate construction/validation for exact local edits; no DB writes."""
from math import isfinite
from collections.abc import Sequence
from .models import Candidate, DishPortion
from .candidates import (combo_totals, hard_filter_reasons, hard_budget_failures,
                         _within, _micro_totals, _score, _soft_avoid_hits)
from .quality import dish_roles, structure_penalty, repetition_cost
from .meal_templates import template_for, main_dish, selection_key
from .explain import make_why_text, make_eating_order_advice
from .errors import HardConstraintUnsatisfiable, InsufficientData


def evaluate_portions(portions, target, targets, soft_avoid=(), *, allow_approximate=True):
    if not portions or len({p.dish_id for p in portions}) != len(portions):
        raise HardConstraintUnsatisfiable('菜式为空或重复')
    if any(not isfinite(p.servings) or p.servings <= 0 for p in portions):
        raise HardConstraintUnsatisfiable('份量非法')
    facts = [p.facts for p in portions]
    reasons = [r for f in facts for r in hard_filter_reasons(f, targets)]
    reasons += hard_budget_failures(target, portions)
    if reasons:
        raise HardConstraintUnsatisfiable('；'.join(reasons))
    template = template_for(facts, target.meal_type)
    from .portion_policy import breakfast_shape
    if not template or not breakfast_shape(portions, target.meal_type):
        raise HardConstraintUnsatisfiable('不符合本餐推荐组合：请重新生成本餐')
    totals = combo_totals(portions)
    if totals.get('kcal') is None:
        raise InsufficientData('能量数据缺失')
    passed, failures = _within(target, totals)
    if any(x.startswith(('oil_over:', 'salt_over:', 'total_salt_equivalent_over:', 'total_sodium_unknown')) for x in failures):
        raise HardConstraintUnsatisfiable('；'.join(failures))
    if not passed and not allow_approximate:
        raise HardConstraintUnsatisfiable('营养目标不满足：' + '；'.join(failures))
    micro = _micro_totals(portions)
    score, codes, notes, breakdown = _score(target, totals, micro, targets,
                                            sum(_soft_avoid_hits(f, soft_avoid) for f in facts), facts)
    from .portion_policy import portion_cost
    from .practical_quality import energy_cost, composition_cost
    # Existing unchanged dishes retain their saved portion. New replacements use meal_options.
    structure_score=structure_penalty(facts,target.meal_type)
    portion_score=portion_cost(facts,[p.servings for p in portions],target.meal_type,target)
    energy_score=energy_cost(totals,target)
    composition_score,attributes=composition_cost(facts,[p.servings for p in portions],target.meal_type)
    score += structure_score+portion_score+energy_score+composition_score
    breakdown.update({'structure':round(structure_score+composition_score,4),'portion':round(portion_score,4),
                      'energy_direction':round(energy_score,4),'final':round(score,4),'attributes':attributes if all(getattr(d,'ingredient_amounts',None) for d in facts) else {},'meal_type':target.meal_type,'energy_gap':abs(totals['kcal']-target.kcal)/max(target.kcal,1)})
    codes.append("meal_template_valid")
    notes.append("推荐结构：" + template)
    if not passed:
        codes.append('macro_range_relaxed')
        notes.append('营养近似结果：' + '、'.join(failures))
    if any(totals.get(k) is None for k in ('oil_g', 'salt_g', 'sodium_mg')):
        codes.append('oil_salt_unknown')
    if any(f.allergen_unverified for f in facts):
        codes.append('allergen_unverified')
    if any(p.servings != 1 for p in portions):
        codes.append('portion_optimized')
    main = main_dish(facts)
    c = Candidate(candidate_id=0, rank=0, portions=list(portions), totals=totals,
                  oil_salt={k: totals.get(k) for k in ('oil_g','salt_g','sodium_mg','total_salt_equivalent_g')},
                  micro_estimate=micro, score=score, score_breakdown=breakdown,
                  reason_codes=sorted(set(codes)), notes=notes,
                  signature=(main.dish_id, main.method_text or '', tuple(sorted(p.dish_id for p in portions))))
    c.why_text = make_why_text(c, target, targets)
    c.eating_order_advice = make_eating_order_advice(c)
    return c


def replace_dish_candidates(portions, dish_id, dishes, target, targets,
                            query='', replacement_id=None, soft_avoid=(), previous=()):
    old = next((p for p in portions if p.dish_id == dish_id), None)
    if old is None:
        raise InsufficientData('指定菜式不在当前候选')
    from .meal_templates import base_dish_id
    used = {p.dish_id for p in portions}
    role = dish_roles(old.facts) - {'复合菜', '未知'}
    results = []
    for f in dishes:
        if f.dish_id in used or (replacement_id and f.dish_id != replacement_id):
            continue
        if not query and not replacement_id and base_dish_id(f.dish_id)==base_dish_id(dish_id):continue
        if query and query.casefold() not in ' '.join([f.name, *f.ingredient_names]).casefold():
            continue
        if not query and not replacement_id and role and not (role & dish_roles(f)):
            continue
        # Only the replacement's portion may change. Other portions are exactly preserved.
        from .practical_quality import meal_options
        for amount in meal_options(f,target):
            new = [DishPortion(facts=f, servings=amount) if p.dish_id == dish_id else p for p in portions]
            try:
                c = evaluate_portions(new, target, targets, soft_avoid)
            except (HardConstraintUnsatisfiable, InsufficientData):
                continue
            results.append(c)
    return sorted(results, key=lambda c: selection_key(c,target,previous,repetition_cost(c,previous)))
