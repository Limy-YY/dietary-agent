import sys, unittest
from pathlib import Path
from types import SimpleNamespace as N
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.rule_engine.portion_policy import (serving_options, everyday_cost, practical_text, combo_portion_options, breakfast_shape, portion_cost)

def dish(id,name,weights,tags=()):return N(dish_id=id,name=name,servings=1.,ingredient_amounts=weights,tags=list(tags))
class Practical(unittest.TestCase):
    def test_eggs(self):
        e=dish('DISH-127','水煮鸡蛋',[['鸡蛋',50]])
        self.assertEqual(serving_options(e),(1.,2.));self.assertIn('约2个蛋',practical_text(e,2.))
        self.assertEqual(serving_options(dish('DISH-089','洋葱炒蛋',[['鸡蛋',100],['洋葱',50]])),(.5,1.))
        self.assertEqual(serving_options(dish('DISH-127','水煮鸡蛋',[])),(1.,))
    def test_actual_amounts(self):
        d=dish('DISH-132','香蕉',[['香蕉',200]])
        self.assertEqual(serving_options(d),(.5,1.));self.assertIn('香蕉100g',practical_text(d,.5))
        self.assertIsNone(practical_text(dish('DISH-132','香蕉',[]),1.))
    def test_soft_preference(self):
        a=dish('DISH-127','水煮鸡蛋',[['鸡蛋',50]],['基础家常菜'])
        b=dish('DISH-029','糙米鹰嘴豆拌饭',[['糙米',60]])
        self.assertLess(everyday_cost([a]),everyday_cost([b]));self.assertLessEqual(everyday_cost([b]),.06)
        self.assertTrue(serving_options(b));self.assertGreater(everyday_cost([a,b]),0)
    def test_breakfast(self):
        porridge=dish('DISH-049','小米粥',[['小米',25]])
        tuber=dish('DISH-056','蒸红薯',[['红薯',100]])
        rice=dish('DISH-058','二米饭',[['大米',50]])
        p=lambda d,v:N(facts=d,servings=v)
        self.assertTrue(breakfast_shape([p(porridge,1),p(tuber,1)],'早'))
        self.assertTrue(breakfast_shape([p(porridge,1),p(tuber,.5)],'早'))
        self.assertFalse(breakfast_shape([p(porridge,1),p(tuber,1),p(rice,1),p(tuber,.5)],'早'))
        self.assertTrue(combo_portion_options([rice,tuber],'早'))
        options=combo_portion_options([porridge,tuber],'早');self.assertTrue(options)
        self.assertGreater(portion_cost([rice,tuber],[1,1],'早'),portion_cost([rice],[1],'早'))
    def test_breakfast_rejects_full_rice_and_soup(self):
        rice=dish('DISH-121','白米饭',[['大米',50]])
        soup=dish('DISH-016','小白菜豆腐汤',[['小白菜',100],['豆腐',100]])
        fruit=dish('DISH-138','猕猴桃',[['猕猴桃',100]])
        egg=dish('DISH-127','水煮鸡蛋',[['鸡蛋',50]])
        p=lambda d:N(facts=d,servings=1.)
        self.assertFalse(breakfast_shape([p(rice),p(egg),p(fruit)],'早'))
        self.assertFalse(breakfast_shape([p(soup),p(fruit)],'早'))
    def test_main_starch(self):
        d=dish('DISH-121','白米饭',[['大米',50]])
        self.assertIn(2.,serving_options(d));self.assertIn('大米100g',practical_text(d,2.))
if __name__=='__main__':unittest.main()
