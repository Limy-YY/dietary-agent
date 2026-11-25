"""Read-only real-catalogue audit, run from backend with project virtualenv."""
from pathlib import Path
import sys
from collections import Counter
from math import isclose
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.services.rule_engine import Profile,PlanRequest,SqlDataSource,generate_plan
from app.services.rule_engine.candidates import hard_budget_failures,hard_filter_reasons
from app.services.rule_engine.meal_templates import CATALOG,profile as dish_profile,template_for,base_dish_id
from app.services.rule_engine.quality import selected
from app.services.rule_engine.portion_policy import breakfast_shape
from app.services.rule_engine.practical_quality import meal_options
from time import perf_counter
import json

cases=[('三天全餐','2026-11-20','2026-11-22',['早','午','晚'],9),('两天早晚餐','2026-11-20','2026-11-21',['早','晚'],4),('一天午餐','2026-11-20','2026-11-20',['午'],1)]

def check_case(ds,who,case):
    name,start,end,meals,n=case
    req=PlanRequest(start_date=start,end_date=end,meal_types=meals,goal_code='maintain',candidates_per_slot=3)
    started=perf_counter()
    result=generate_plan(who,req,ds,skip_balance=False)
    print("ELAPSED_SECONDS",round(perf_counter()-started,3),flush=True)
    print('\nCASE',name,'targets',round(result.targets.energy_kcal,1),'slots',len(result.slots),flush=True)
    assert len(result.slots)==n
    counts=Counter(); signatures=[]; days=Counter(); gaps=[]
    for slot in result.slots:
        assert 2<=len(slot.candidates)<=3,(slot.slot_date,slot.meal_type,'not enough candidates')
        assert isclose(slot.target.kcal,result.targets.energy_kcal*{'早':.25,'午':.4,'晚':.35}[slot.meal_type],abs_tol=.2)
        picked=selected(slot); assert picked is not None
        for c in slot.candidates:
            tpl=template_for([p.facts for p in c.portions],slot.meal_type)
            assert tpl,(slot.slot_date,slot.meal_type,c.dish_ids)
            assert not hard_budget_failures(slot.target,c.portions)
            assert not any(hard_filter_reasons(p.facts,result.targets) for p in c.portions)
            assert len(c.dish_ids)==len(set(c.dish_ids))
            assert all(p.servings in meal_options(p.facts,slot.target) for p in c.portions)
            assert breakfast_shape(c.portions,slot.meal_type)
            gap=abs(c.totals['kcal']-slot.target.kcal)/slot.target.kcal
            if gap>.151: assert 'macro_range_relaxed' in c.reason_codes
            print(str(slot.slot_date),slot.meal_type,'SELECTED' if c is picked else 'alternate',tpl,'target',round(slot.target.kcal,1),'actual',c.totals['kcal'],'approx','macro_range_relaxed' in c.reason_codes, '|', ' + '.join(f'{p.name}({p.as_dict(1)["portion_text"]})' for p in c.portions),flush=True)
        counts.update(picked.dish_ids); signatures.append(tuple(sorted(picked.dish_ids)))
        days[str(slot.slot_date)]+=picked.totals['kcal']; gaps.append(abs(picked.totals['kcal']-slot.target.kcal)/slot.target.kcal)
    repeated=len(signatures)-len(set(signatures))
    print('DAILY ACTUAL',dict(days),'DIVERSITY',{'unique_dishes':len(counts),'max_occurrences':max(counts.values()),'exact_repeats':repeated,'counts':counts.most_common()},'MAX ENERGY GAP',round(max(gaps)*100,1),'%')
    print('DIAGNOSTICS',result.diagnostics.get('relax_notes'))
    print('SEARCH',json.dumps(result.diagnostics.get('candidate_search'),ensure_ascii=False))
    print('PRACTICAL QUALITY',json.dumps(result.diagnostics.get('practical_quality'),ensure_ascii=False),flush=True)
    if repeated: print('REVIEW: repeated exact meal; inspect whether suitable alternative existed')
    if max(gaps)>.25: print('REVIEW: selected energy deviation >25%; expand reviewed breakfast/staple catalogue if necessary')

with SessionLocal() as db:
    ds=SqlDataSource(db); dishes=ds.get_dish_facts()
    pending=[(d.dish_id,d.name) for d in dishes if not dish_profile(d).reviewed]
    print('CATALOG',len(dishes),'review pending',pending,flush=True)
    assert not pending,'Unreviewed dishes: review actual names/roles before accepting'
    assert set(CATALOG)=={base_dish_id(d.dish_id) for d in dishes},'Catalogue differs from the observed 110 dishes'
    base=Profile(gender='男',age=20,height_cm=176,weight_kg=70,goal_code='maintain')
    for case in cases: check_case(ds,base,case)
    constrained=Profile(gender='男',age=20,height_cm=176,weight_kg=70,goal_code='maintain',allergies=['花生'])
    check_case(ds,constrained,('过敏与忌口','2026-11-20','2026-11-20',['早','午','晚'],3))
    db.rollback()
print('PASS all candidate template and safety checks; inspect REVIEW and menu quality before acceptance.')
