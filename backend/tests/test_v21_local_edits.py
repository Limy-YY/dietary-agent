import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_rule_engine_selftest import sample_dishes, GOAL_ROW, MICRO_REFS
from app.services.rule_engine import Profile,PlanRequest,compute_targets
from app.services.rule_engine.models import DishPortion
from app.services.rule_engine.local_edit import evaluate_portions,replace_dish_candidates
from app.services.rule_engine.errors import RuleEngineError

class LocalTests(unittest.TestCase):
    def setUp(self):
        self.dishes=sample_dishes()
        self.targets=compute_targets(Profile(allergies=['花生'],religious_ethical=['清真']),GOAL_ROW,MICRO_REFS,PlanRequest(start_date='2026-11-20',end_date='2026-11-20'))
        self.target=self.targets.meal_targets['午']
    def test_replace_preserves_other_portions(self):
        old=[DishPortion(self.dishes[0],1.25),DishPortion(self.dishes[3],1)]
        pool=replace_dish_candidates(old,old[1].dish_id,self.dishes,self.target,self.targets,query='三文鱼')
        self.assertTrue(pool)
        self.assertEqual(pool[0].portions[0],old[0])
        self.assertNotIn(old[1].dish_id,pool[0].dish_ids)
    def test_allergy_never_relaxed(self):
        with self.assertRaises(RuleEngineError):
            evaluate_portions([DishPortion(self.dishes[0]),DishPortion(self.dishes[-1])],self.target,self.targets)
    def test_forbidden_replacement(self):
        old=[DishPortion(self.dishes[0]),DishPortion(self.dishes[3])]
        self.assertEqual(replace_dish_candidates(old,old[1].dish_id,self.dishes,self.target,self.targets,query='花生'),[])
if __name__=='__main__': unittest.main()
