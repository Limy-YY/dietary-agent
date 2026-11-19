"""Deterministic engine regressions without DB/LLM."""
from dataclasses import replace
import unittest
from test_rule_engine_selftest import GOAL_ROW, MICRO_REFS, FakeDataSource, sample_dishes
from app.services.rule_engine import Profile, PlanRequest, generate_plan, compute_targets, build_candidates
from app.services.rule_engine.candidates import combo_totals, hard_budget_failures
from app.services.rule_engine.models import DishPortion
from app.services.rule_engine.quality import dish_roles, structure_penalty, repetition_cost, selected
from app.services.rule_engine.repository import _DISH_SQL


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.dishes = sample_dishes()
        self.profile = Profile(gender="女", age=20, height_cm=160, weight_kg=55,
                               allergies=["花生"], religious_ethical=["清真"], cooking_equipment=["炒锅", "蒸锅"])
        self.req = PlanRequest(start_date="2026-11-18", end_date="2026-11-20", meal_types=["早", "午", "晚"])

    def test_roles(self):
        self.assertIn("主食", dish_roles(self.dishes[0]))
        self.assertIn("蛋白质菜", dish_roles(self.dishes[3]))
        self.assertIn("蔬菜", dish_roles(self.dishes[7]))
        oat = replace(self.dishes[0], name="酸奶燕麦片", ingredient_names=["酸奶", "燕麦"])
        other = replace(self.dishes[3], name="燕麦香蕉酸奶碗", ingredient_names=["燕麦", "香蕉", "酸奶"])
        self.assertIn("奶类", dish_roles(oat))
        self.assertGreater(structure_penalty([oat, other], "早"), structure_penalty([oat, self.dishes[3]], "早"))

    def test_serving_scale_and_missing(self):
        d = self.dishes[0]
        portions = [DishPortion(facts=d, servings=.75)]
        self.assertAlmostEqual(combo_totals(portions)["kcal"], round(d.energy_kcal * .75,1))
        self.assertIsNone(combo_totals(portions)["fiber_g"])
        self.assertEqual(portions[0].as_dict(1)["portion_text"], "0.75 份")

    def test_generation_and_metrics(self):
        result = generate_plan(self.profile, self.req, FakeDataSource(self.dishes), skip_balance=True)
        self.assertEqual(len(result.slots), 9)
        self.assertEqual(len(result.diagnostics["role_mapping"]), len(self.dishes))
        self.assertGreater(result.diagnostics["diversity"]["unique_dishes"], 1)
        for s in result.slots:
            c = selected(s)
            self.assertIsNotNone(c)
            self.assertFalse(hard_budget_failures(s.target, c.portions))
            self.assertFalse(set(c.dish_ids) & {"DISH-S6", "DISH-S7"})
            self.assertEqual(len(c.dish_ids), len(set(c.dish_ids)))
            self.assertGreater(repetition_cost(c,[c]), repetition_cost(c, []))
        print("DIVERSITY", result.diagnostics["diversity"])

    def test_sql_aggregation_separation(self):
        # Structural check only: integration test must exercise real PostgreSQL.
        nutrient_agg = _DISH_SQL.split("), allergy_agg AS (")[0]
        self.assertNotIn("unnest(base.allergens)", nutrient_agg)
        self.assertIn("JOIN allergy_agg", _DISH_SQL)


if __name__ == "__main__":
    unittest.main()
