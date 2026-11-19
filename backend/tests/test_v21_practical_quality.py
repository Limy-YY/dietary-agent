import unittest,sys
from pathlib import Path
from types import SimpleNamespace as N
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.rule_engine.practical_quality import (meal_options,portion_size_cost,main_family,protein_rotation,purchase_credit,diverse_choices,nutrition_report,energy_cost)

def dish(id,name,rows):
    return N(dish_id='DISH-'+id,name=name,ingredient_amounts=list(rows.items()),servings=1.,tags=[],method_text='',ingredient_names=list(rows))
def cand(*dishes,score=.3,approx=False):
    return N(portions=[N(facts=d,servings=1.,dish_id=d.dish_id) for d in dishes],dish_ids=[d.dish_id for d in dishes],score=score,reason_codes=['macro_range_relaxed'] if approx else [],totals={'kcal':800.,'protein_g':None,'sodium_mg':353.},micro_estimate={'calcium':None},notes=[])
class Quality(unittest.TestCase):
    def setUp(self):
        self.bf=N(meal_type='早',kcal=596.8)
        self.lunch=N(meal_type='午',kcal=954.8)
        self.r=dish('061','白米饭',{'大米':50})
        self.p=dish('110','白粥',{'大米':50})
        self.v=dish('026','番茄黄瓜沙拉',{'番茄':200,'黄瓜':200})
        self.ch=dish('079','卤鸡腿',{'鸡腿':100,'姜':5})
        self.ch2=dish('080','白切鸡腿',{'鸡腿':100})
        self.beef=dish('019','芹菜炒牛肉',{'牛肉':120,'芹菜':200})
        self.egg=dish('067','水煮鸡蛋',{'鸡蛋':50})
    def test_practical_portions(self):
        self.assertNotIn(2.,meal_options(self.p,self.bf));self.assertIn(1.,meal_options(self.p,self.bf))
        self.assertEqual(meal_options(self.v,self.bf),(.5,));self.assertEqual(meal_options(self.egg,self.bf),(1.,2.))
        self.assertGreater(portion_size_cost([self.p],[2.],self.bf),portion_size_cost([self.p],[1.],self.bf))
        self.assertIn(2.,meal_options(self.r,self.lunch))
    def test_rotation_is_soft_and_food_based(self):
        a=cand(self.r,self.ch,self.v);b=cand(self.r,self.ch2,self.v);c=cand(self.r,self.beef,self.v)
        self.assertEqual(main_family(a),main_family(b));self.assertEqual(main_family(c),'牛肉')
        self.assertGreater(protein_rotation(b,[a,a]),protein_rotation(c,[a,a]));self.assertEqual(protein_rotation(a,[]),0.)
        self.assertGreater(purchase_credit(c,[a]),0.);self.assertLessEqual(purchase_credit(c,[a]),.09)
        self.assertGreater(purchase_credit(b,[a]),0.)
    def test_alternatives(self):
        a=cand(self.r,self.ch,self.v);b=cand(self.r,self.ch2,self.v,score=.31);c=cand(self.r,self.beef,score=.33);d=cand(self.p,self.egg,score=.01,approx=True)
        out=diverse_choices([a,b,c,d],3);self.assertIs(out[0],a);self.assertIs(out[1],c);self.assertIs(out[2],b)
        self.assertEqual(diverse_choices([a,b],3),[a,b])
    def test_diagnostics_unknown(self):
        rng=N(target=30.,low=25.,high=35.)
        t=N(kcal=950.,protein=rng,fat=rng,carb=rng,oil_limit_g=10.,salt_limit_g=2.)
        row=nutrition_report(cand(self.r,self.ch),t)
        self.assertEqual(row['fields']['protein_g']['status'],'unknown');self.assertIsNone(row['fields']['protein_g']['delta'])
        self.assertEqual(row['fields']['kcal']['status'],'below');self.assertEqual(row['total_salt_equivalent_g'],.897)
        self.assertEqual(row['salt_limit_basis'],'total_sodium_salt_equivalent; added salt reported separately and not added twice')
        self.assertGreater(energy_cost({'kcal':850},t),energy_cost({'kcal':1050},t))
    def test_specialty_is_only_soft(self):
        from app.services.rule_engine.meal_templates import selection_key, template_for
        special=dish('029','糙米鹰嘴豆拌饭',{'糙米饭':180,'鹰嘴豆':100})
        self.assertIsNotNone(template_for([special,self.ch],'午'))
        self.assertEqual(main_family(cand(special)), '豆制品')
        a=cand(self.r,self.ch,score=.5); b=cand(special,self.ch,score=.2)
        self.assertLess(selection_key(b,self.lunch,[],0),selection_key(a,self.lunch,[],0))
    def test_high_energy_and_known_portion_options(self):
        bigger=N(meal_type='午',kcal=1350.)
        rice=dish('058','二米饭',{'大米':50,'小米':20})
        beans=dish('028','四季豆炒胡萝卜',{'四季豆':200,'胡萝卜':100})
        self.assertNotIn(2.,meal_options(rice,self.lunch))
        self.assertIn(2., meal_options(rice,bigger))
        self.assertNotIn(1.5,meal_options(beans,self.lunch))
        self.assertTrue(meal_options(beans,bigger))
    def test_context_protein_rotation_uses_normal_meal_history(self):
        from app.services.rule_engine.meal_templates import selection_key
        ch=cand(self.r,self.ch); ch2=cand(self.r,self.ch2); beef=cand(self.r,self.beef)
        breakfast=cand(self.egg)
        history=[ch,ch,breakfast]
        self.assertLess(selection_key(beef,self.lunch,history,0,protein_previous=[ch,ch]),
                        selection_key(ch2,self.lunch,history,0,protein_previous=[ch,ch]))
if __name__=='__main__':unittest.main()
