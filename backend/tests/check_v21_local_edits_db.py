"""Real PostgreSQL transaction/savepoint smoke test. All data writes roll back; sequences may advance."""
from pathlib import Path
import sys
from datetime import date
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.models.profile import Profile
from app.core.errors import BizError, BizCode
from app.routers.mealplan import (GenerateRequest, SlotRegenerateRequest, DishReplaceRequest, SwapRequest, FixRequest,
    generate_week_plan, regenerate_slot, replace_dish, swap_candidate, fix_plan, _get_plan, _serialize_plan)

def signature(slot):
    return [(d['dish_id'],d['servings']) for d in slot['selected_candidate']['dishes']]

def reject(fn, code=None):
    try: fn()
    except BizError as exc:
        if code is not None: assert exc.code == code, (exc.code,code,str(exc))
        print('PASS expected rejection:',exc)
    else: raise AssertionError('Operation unexpectedly succeeded')

with engine.connect() as conn:
    outer=conn.begin()
    try:
        with Session(bind=conn,join_transaction_mode='create_savepoint') as db:
            uid='v21-test-'+uuid4().hex[:12]
            db.add(Profile(user_id=uid,name='V21 test fixture',gender='男',sex='男',age=20,height_cm=176,weight_kg=70,goal_code='maintain',allergies=['花生']))
            db.commit()
            p=generate_week_plan(GenerateRequest(start_date=date(2026,11,20),end_date=date(2026,11,21),meal_types=['早','午','晚']),user_id=uid,db=db).data
            pid=p['meal_plan_id']; before={s['meal_slot_id']:s for s in p['slots']}; target=p['slots'][4]; sid=target['meal_slot_id']; old=target['selected_candidate_id']
            req=SlotRegenerateRequest(meal_plan_id=pid,meal_slot_id=sid,expected_candidate_id=old)
            reject(lambda:regenerate_slot(req,user_id='not-owner',db=db),BizCode.FORBIDDEN)
            changed=regenerate_slot(req,user_id=uid,db=db).data
            after={s['meal_slot_id']:s for s in changed['slots']}
            assert set(before)==set(after)
            assert all(before[k]==after[k] for k in before if k!=sid)
            assert signature(before[sid])!=signature(after[sid])
            assert 2<=len(after[sid]['candidates'])<=3
            assert old not in [c['candidate_id'] for c in after[sid]['candidates']]
            assert db.execute(text('SELECT rank FROM app.meal_candidate WHERE candidate_id=:id'),{'id':old}).one()[0] is None
            print('PASS regenerate only one slot, archived old candidate')
            reject(lambda:regenerate_slot(req,user_id=uid,db=db),BizCode.PLAN_STATE_CONFLICT)
            before_replace=after[sid]; picked=before_replace['selected_candidate_id']; success=False
            for dish in before_replace['selected_candidate']['dishes']:
                try:
                    replacement=replace_dish(DishReplaceRequest(meal_plan_id=pid,meal_slot_id=sid,expected_candidate_id=picked,dish_id=dish['dish_id'],allow_approximate=True),user_id=uid,db=db).data
                except BizError as exc:
                    print('Replacement trial:',exc); continue
                slots={s['meal_slot_id']:s for s in replacement['slots']}
                assert all(after[k]==slots[k] for k in after if k!=sid)
                assert all(item in signature(slots[sid]) for item in signature(before_replace) if item[0]!=dish['dish_id'])
                assert dish['dish_id'] not in [x[0] for x in signature(slots[sid])]
                print('PASS replace exactly one dish, preserves other servings'); success=True; break
            assert success,'No replacement succeeded in fixture'
            current=slots[sid]['selected_candidate_id']; dish=slots[sid]['selected_candidate']['dishes'][0]['dish_id']
            reject(lambda:replace_dish(DishReplaceRequest(meal_plan_id=pid,meal_slot_id=sid,expected_candidate_id=current,dish_id=dish,replacement_query='花生',allow_approximate=True),user_id=uid,db=db))
            assert _serialize_plan(_get_plan(db,pid),db)['slots']==replacement['slots']
            print('PASS illegal replacement rolled back')
            fixed=fix_plan(FixRequest(meal_plan_id=pid),user_id=uid,db=db).data
            assert fixed['status']=='fixed'
            reject(lambda:regenerate_slot(SlotRegenerateRequest(meal_plan_id=pid,meal_slot_id=sid,expected_candidate_id=current),user_id=uid,db=db),BizCode.PLAN_STATE_CONFLICT)
            print('PASS fixed plan protected')
            print('PASS DB smoke; not HTTP/auth or actual LLM integration')
    finally:
        outer.rollback()
        print('Test transaction rolled back (identity sequences may advance).')
