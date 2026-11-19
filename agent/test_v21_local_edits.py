import unittest
import local_edits as le
class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.p={'meal_plan_id':11,'slots':[{'meal_slot_id':1,'slot_date':'2026-11-20','meal_type':'早'},{'meal_slot_id':2,'slot_date':'2026-11-21','meal_type':'早'}]}
        self.s={};le.remember(self.s,self.p);le.remember(self.s,{'meal_plan_id':12,'slots':[]})
    def test_multi_plan(self):
        with self.assertRaises(ValueError): le.resolve_plan(self.s,{})
        self.assertEqual(le.resolve_plan(self.s,{'plan_index':1})['meal_plan_id'],11)
    def test_multi_day(self):
        with self.assertRaises(ValueError): le.resolve_slot(self.p,{'meal_type':'早餐'})
        self.assertEqual(le.resolve_slot(self.p,{'meal_type':'早餐','day_index':2})['meal_slot_id'],2)
    def test_explicit_target(self):
        self.assertEqual(le.explicit_target('第一份方案第二天早餐换掉鸡蛋',{'plan_index':2,'day_index':1})['plan_index'],1)
        self.assertIsNone(le.explicit_target('早餐换掉鸡蛋',{'plan_index':2})['plan_index'])
    def test_update_preserves_order(self):
        le.remember(self.s,{'meal_plan_id':11,'slots':[]})
        self.assertEqual([p['meal_plan_id'] for p in le.registry(self.s)],[11,12])
if __name__=='__main__': unittest.main()
