"""Test catalogue coverage and flexible, bounded combination enumeration."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.rule_engine.meal_templates import (CATALOG,profile,template_for,iter_template_combos,staple_key,selection_key,retain_pool,non_staple_base_ids)

def mock(key):
    p=CATALOG['DISH-'+key]
    return SimpleNamespace(dish_id='DISH-'+key,name=p.name)

def combo(*keys): return [mock(k) for k in keys]

class TemplateTests(unittest.TestCase):
    def test_catalog(self):
        self.assertEqual(set(CATALOG),{f'DISH-{i:03}' for i in range(1,171)})
        for k,d in CATALOG.items(): self.assertTrue(profile(SimpleNamespace(dish_id=k,name=d.name)).reviewed)
        self.assertFalse(profile(SimpleNamespace(dish_id='DISH-001',name='changed')).reviewed)
        self.assertEqual(profile(mock('121')).commonness,0)
        self.assertEqual(profile(mock('127')).complexity,0)
    def test_only_practical_shape_is_hard(self):
        self.assertIsNone(template_for([], '早'))
        self.assertIsNone(template_for(combo('121','121'), '早'))
        self.assertIsNone(template_for(combo('121','127','129','131'), '早'))
        self.assertIsNone(template_for(combo('121','127','146','129','131'), '午'))
        changed=SimpleNamespace(dish_id='DISH-001',name='changed')
        self.assertIsNone(template_for([changed], '早'))
    def test_valid(self):
        for keys,mt in [(('030',),'早'),(('059','014'),'早'),(('049','014'),'早'),(('049','013'),'早'),(('122','127','129'),'早'),(('121','139','146'),'午'),(('058','019','023','045'),'午'),(('046','006','043'),'晚'),(('029','010'),'午'),(('055','005'),'午')]:
            with self.subTest(keys=keys,mt=mt): self.assertIsNotNone(template_for(combo(*keys),mt))
        for keys,mt in [(('030','056'),'早'),(('049','056','014'),'早'),(('121','129','148'),'午'),(('121','131','148'),'晚')]:
            with self.subTest(keys=keys,mt=mt): self.assertIsNotNone(template_for(combo(*keys),mt))

    def test_full_rice_meals_are_not_breakfast_eligible(self):
        rows=list(iter_template_combos([mock('121'),mock('127'),mock('138')],'早'))
        self.assertFalse(any('DISH-061' in {d.dish_id for d in row} for row in rows))
    def test_full_catalog_enumeration(self):
        ds=[mock(f'{i:03}') for i in range(1,171)]
        for mt in ('早','午','晚'):
            rows=list(iter_template_combos(ds,mt)); keys=[tuple(sorted(d.dish_id for d in c)) for c in rows]
            self.assertGreater(len(rows),10); self.assertEqual(len(keys),len(set(keys)))
            self.assertTrue(all(template_for(c,mt) for c in rows))
            if mt=='早':
                self.assertTrue(all(len(c)<=3 for c in rows))
                self.assertTrue(any(sum('主食' in profile(d).roles for d in c)==0 for c in rows))
                self.assertTrue(any(sum('主食' in profile(d).roles for d in c)>1 for c in rows))
            else:
                self.assertTrue(all(len(c)<=3 for c in rows))
            self.assertTrue(any(len(c)==2 for c in rows))
            if mt!='早': self.assertFalse(any(d.dish_id in ('DISH-030','DISH-059') for c in rows for d in c))
            print(mt,'template sets',len(rows))
    def test_rank_prefers_unique_in_energy_band(self):
        def c(ids,kcal,score=0,codes=()): return SimpleNamespace(dish_ids=ids,totals={'kcal':kcal},score=score,reason_codes=codes)
        target=SimpleNamespace(kcal=700); prev=[c(['A','B'],700)]
        self.assertLess(selection_key(c(['A','C'],650,.2),target,prev,.2),selection_key(c(['A','B'],700),target,prev,0))
        self.assertGreater(selection_key(c(['A','C'],350),target,prev,0),selection_key(c(['A','B'],700),target,prev,0))

    def test_same_day_avoids_exact_non_staple_and_low_salt_variant(self):
        def c(ids,kcal=700,score=0):
            return SimpleNamespace(dish_ids=ids,totals={'kcal':kcal},score=score,
                                   reason_codes=[],score_breakdown={})
        target=SimpleNamespace(kcal=700,meal_type='晚')
        breakfast=c(['DISH-169','DISH-014'])
        repeated=c(['DISH-122','DISH-014-LS'])
        fresh=c(['DISH-122','DISH-167'])
        self.assertEqual(non_staple_base_ids(breakfast),{'DISH-014'})
        self.assertLess(selection_key(fresh,target,[],0,same_day=[breakfast]),
                        selection_key(repeated,target,[],0,same_day=[breakfast]))

if __name__=='__main__': unittest.main()
