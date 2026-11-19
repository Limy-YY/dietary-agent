import unittest
from types import SimpleNamespace as N
from dataclasses import replace
from test_v21_practical_quality import dish, cand
from app.services.rule_engine.meal_templates import base_dish_id, profile, selection_key, template_for, extension_combos
from app.services.rule_engine.practical_quality import dietary_attributes, structure_tier, candidate_priority, diverse_choices, composition_cost
from app.services.rule_engine.quality import repetition_cost
from app.services.rule_engine.portion_policy import practical_text
from app.services.rule_engine.candidates import build_candidates, hard_budget_failures
from app.services.rule_engine import Profile, PlanRequest, compute_targets
from test_rule_engine_selftest import GOAL_ROW, MICRO_REFS, sample_dishes
from collections import Counter

class CulinaryFirst(unittest.TestCase):
    def setUp(self):
        self.r=dish('061','白米饭',{'大米':50}); self.n=dish('065','清汤面',{'面条':75})
        self.ch=dish('080','白切鸡腿',{'鸡腿':100}); self.v=dish('088','清炒生菜',{'生菜':200,'精盐':.8})
        self.vls=dish('088-LS','清炒生菜（少盐）',{'生菜':200,'精盐':.4}); self.f=dish('060','醋溜土豆丝',{'土豆':100,'甜椒':50})
        self.b=dish('094','清炒油菜',{'油菜':150}); self.t=N(meal_type='午',kcal=950.)
    def test_staple_repeat_is_neutral(self):
        meal=cand(self.r,self.ch,self.v)
        repeated=cand(self.r,self.n)
        self.assertEqual(repetition_cost(repeated,[meal]*6),0)
        self.assertGreater(repetition_cost(cand(self.r,self.v),[meal]*6),repetition_cost(cand(self.r,self.b),[meal]*6))
    def test_structure_not_role_count(self):
        a=dietary_attributes([self.r,self.ch,self.v],[1,1,1])
        b=dietary_attributes([self.r,self.n,self.ch],[1,1,1])
        self.assertEqual(structure_tier(a,'午'),0);self.assertEqual(structure_tier(b,'午'),2)
        self.assertEqual(dietary_attributes([self.r,self.f],[1,1])['full_staples'],1)
        self.assertEqual(dietary_attributes([self.r,self.n],[1,.25])['full_staples'],1)
        self.assertEqual(dietary_attributes([dish('029','糙米鹰嘴豆拌饭',{'糙米饭':180,'鹰嘴豆':100})],[1])['full_staples'],1)
    def test_structure_ahead_of_strict_looking_meal(self):
        a=cand(self.r,self.ch,self.v,score=.7,approx=True);a.totals['kcal']=800
        b=cand(self.r,self.ch,self.n,score=.1);b.totals['kcal']=950
        for c in (a,b):c.score_breakdown={'attributes':dietary_attributes([p.facts for p in c.portions],[1]*len(c.portions)), 'meal_type':'午','energy_gap':abs(c.totals['kcal']-950)/950}
        self.assertLess(selection_key(a,self.t,[],0),selection_key(b,self.t,[],0))
        self.assertLess(candidate_priority(a),candidate_priority(b))
        a.totals['kcal']=600;a.score_breakdown['energy_gap']=350/950
        self.assertGreater(selection_key(a,self.t,[],0),selection_key(b,self.t,[],0))
    def test_variant_is_same_culinary_identity(self):
        self.assertEqual(base_dish_id(self.vls.dish_id),self.v.dish_id)
        self.assertTrue(profile(self.vls).reviewed);self.assertIsNone(template_for([self.r,self.v,self.vls],'午'))
        self.assertIn('添加食盐0.4g',practical_text(self.vls,1))
        first=cand(self.r,self.ch,self.v);same=cand(self.r,self.ch,self.vls);other=cand(self.r,self.ch,self.b)
        self.assertEqual(diverse_choices([first,same,other],3),[first,other])
        self.assertGreater(repetition_cost(same,[first]),0)
    def test_expansion_and_safety_diagnostics(self):
        extra=[dish('089','蒜炒空心菜',{'空心菜':100}),self.b,self.v]
        rows=list(extension_combos([self.r,self.ch,*extra],'午'))
        self.assertTrue(rows);self.assertTrue(all(len(c)==4 and template_for(c,'午') for c in rows))
        who=Profile(gender='男',age=20,height_cm=176,weight_kg=70)
        req=PlanRequest(start_date='2026-11-19',end_date='2026-11-19',meal_types=['午'])
        t=compute_targets(who,GOAL_ROW,MICRO_REFS,req);target=t.meal_targets['午'];d=sample_dishes()
        bad=replace(d[3],sodium_mg=10000);stats=Counter()
        self.assertFalse(build_candidates(target,[d[0]],[bad],t,relaxed=True,diagnostics=stats))
        self.assertGreater(stats['sodium_bounds_rejected'],0)
    def test_nuts_are_not_a_free_energy_filler(self):
        nuts=dish('054','芹菜拌花生',{'芹菜':100,'花生仁':30})
        self.assertGreater(composition_cost([self.r,self.ch,nuts],[1,1,1.5],'午')[0],composition_cost([self.r,self.ch,nuts],[1,1,1],'午')[0])

if __name__=='__main__':unittest.main()
