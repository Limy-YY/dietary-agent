"""Read-only recipe audit against the same data source used by the engine."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.services.rule_engine import SqlDataSource
from app.services.rule_engine.portion_policy import ingredient_weights, serving_options, practical_text
from app.services.rule_engine.meal_templates import profile
with SessionLocal() as db:
    rows=SqlDataSource(db).get_dish_facts()
    print('CATALOG',len(rows));assert len(rows)>=110
    missing=[];unclear=[];sodium_review=[]
    for d in rows:
        w=ingredient_weights(d)
        if not w or d.energy_kcal is None:missing.append(d.dish_id)
        if not profile(d).reviewed:unclear.append(d.dish_id)
        sodium=d.sodium_mg
        # Total sodium (food + seasoning) is not the same metric as added table salt.
        equiv=None if sodium is None else round(sodium*2.54/1000,3)
        if equiv is None or (d.default_salt_g is not None and equiv>d.default_salt_g+.15):sodium_review.append((d.dish_id,d.name,equiv,d.default_salt_g))
        print(d.dish_id,d.name,'recipe ingredient grams=',w,'kcal=',d.energy_kcal,'sodium mg=',sodium,'total salt equivalent g=',equiv,'added salt g=',d.default_salt_g,'options=',serving_options(d),'display=',practical_text(d,1),flush=True)
    print('MISSING/INVALID RECIPE OR ENERGY',missing,'UNREVIEWED ROLE',unclear)
    print('REVIEW sodium vs added salt (not automatic errors)',sodium_review)
    by={d.dish_id:d for d in rows}
    for i in ('DISH-061','DISH-110','DISH-072','DISH-067','DISH-079'):
        d=by.get(i);assert d is not None
        print('FLAGGED CASE',i,d.name,ingredient_weights(d),d.energy_kcal,d.sodium_mg)
    assert not missing,'Source records incomplete; do not invent values'
    assert not unclear,'Review catalogue roles'
    db.rollback()
print('PASS read-only completeness audit; food composition accuracy and cooked yields require source review.')
