"""Focused seven-day acceptance check from the supplied meal-plan report."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.services.rule_engine import Profile,PlanRequest,SqlDataSource,generate_plan
from app.services.rule_engine.candidates import hard_budget_failures
from app.services.rule_engine.quality import selected
from app.services.rule_engine.meal_templates import base_dish_id,profile as culinary_profile
from app.services.rule_engine.practical_quality import structure_tier
from time import perf_counter

with SessionLocal() as db:
    who=Profile(gender='男',age=20,height_cm=176,weight_kg=70,goal_code='maintain')
    req=PlanRequest(start_date='2026-11-19',end_date='2026-11-25',meal_types=['早','午','晚'],
                    goal_code='maintain',candidates_per_slot=3)
    started=perf_counter()
    result=generate_plan(who,req,SqlDataSource(db),skip_balance=False)
    assert len(result.slots)==21
    dishes=Counter();meals=Counter();days=defaultdict(lambda:{'target':0.,'actual':0.,'salt_eq':0.})
    double_staples=0;unknown_sodium=[];poor_structure=0;side_counts=Counter();sides_by_family=Counter();no_veg=0
    for slot in result.slots:
        c=selected(slot);assert c is not None
        assert not hard_budget_failures(slot.target,c.portions)
        assert c.score_breakdown and 'attributes' in c.score_breakdown
        eq=c.totals.get('total_salt_equivalent_g')
        if eq is None:unknown_sodium.append((slot.slot_date,slot.meal_type))
        else:days[str(slot.slot_date)]['salt_eq']+=eq
        days[str(slot.slot_date)]['target']+=slot.target.kcal
        days[str(slot.slot_date)]['actual']+=c.totals['kcal']
        dishes.update(base_dish_id(p.dish_id) for p in c.portions)
        a=c.score_breakdown['attributes'];tier=structure_tier(a,slot.meal_type)
        poor_structure+=tier==2
        no_veg+=slot.meal_type in ('午','晚') and a['vegetable_g']<45
        for p in c.portions:
            if culinary_profile(p.facts).roles=={'蔬菜'}:
                side_counts[base_dish_id(p.dish_id)]+=1
                sides_by_family[culinary_profile(p.facts).family]+=1
        print(slot.slot_date,slot.meal_type, ' | '.join(p.name+' '+str(p.as_dict(1)['portion_text']) for p in c.portions), 'kcal',c.totals['kcal'],'salt_eq',eq,'vegetable_g',a['vegetable_g'],'full_staples',a['full_staples'],'tier',tier,'approx', 'macro_range_relaxed' in c.reason_codes)
        meals[tuple(sorted(base_dish_id(d) for d in c.dish_ids))]+=1
        double_staples+=c.score_breakdown['attributes']['full_staples']>1
    assert not unknown_sodium
    assert all(v['salt_eq']<=5.01 for v in days.values())
    # Repetition is an evaluation metric, not a medical constraint.
    avg_dev=sum((v['actual']-v['target'])/v['target'] for v in days.values())/len(days)
    print('SLOTS',len(result.slots),'AVG_DAILY_ENERGY_DEVIATION',round(avg_dev*100,1),'%')
    print('DISH_COUNTS',dishes.most_common(),'DOUBLE_FULL_STAPLES',double_staples)
    print('DAILY', {d:{k:round(x,2) for k,x in v.items()} for d,v in days.items()})
    print('DIVERSITY',result.diagnostics['diversity'])
    print('QUALITY',{'poor_structure':poor_structure,'no_veg_regular':no_veg,'unique_sides':len(side_counts),'side_counts':side_counts.most_common(),'side_families':sides_by_family.most_common(),'exact_repeats':sum(v-1 for v in meals.values())})
    print('SEARCH',result.diagnostics.get('candidate_search'),'elapsed',round(perf_counter()-started,3))
    # Fixture-specific quality gate, not a rule enforced on every user.
    if poor_structure or double_staples>2 or len(sides_by_family)<5 or max(side_counts.values(),default=0)>5:
        print('QUALITY REVIEW FAILED: inspect candidate diagnostics and actual meal contents')
    else:print('QUALITY REVIEW PASS: fixture thresholds met; still inspect taste and portions')
    db.rollback()
print('PASS seven-day report acceptance and total-sodium safety checks')
