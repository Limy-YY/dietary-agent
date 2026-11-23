"""V2.1 foundation regression (no DB or LLM). Run directly with Python."""
from dataclasses import replace
import unittest
from test_rule_engine_selftest import GOAL_ROW, MICRO_REFS, sample_dishes
from app.services.rule_engine import Profile, PlanRequest, compute_targets, build_candidates


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(gender="男", age=20, height_cm=180, weight_kg=68,
                               allergies=["花生"], religious_ethical=["清真"],
                               cooking_equipment=["炒锅", "蒸锅"])
        self.request = PlanRequest(start_date="2026-11-18", end_date="2026-11-18", meal_types=["午"])

    def targets(self, meals):
        return compute_targets(self.profile, GOAL_ROW, MICRO_REFS, replace(self.request, meal_types=meals))

    def test_partial_targets(self):
        for meals, ratio in ((["午"], .4), (["早", "晚"], .6), (["早", "午"], .7), (["早", "午", "晚"], 1.0)):
            with self.subTest(meals=meals):
                t = self.targets(meals)
                self.assertEqual(set(t.meal_targets), set(meals))
                self.assertAlmostEqual(sum(m.kcal for m in t.meal_targets.values()), t.energy_kcal * ratio)
                self.assertAlmostEqual(sum(m.oil_limit_g for m in t.meal_targets.values()), 25 * ratio)
                self.assertAlmostEqual(sum(m.salt_limit_g for m in t.meal_targets.values()), 5 * ratio)
                self.assertAlmostEqual(sum(m.protein.target for m in t.meal_targets.values()), t.energy_kcal * t.goal_policy.protein_pct / 4 * ratio)

    def test_relax_does_not_override_known_budget(self):
        t = self.targets(["午"])
        target = t.meal_targets["午"]
        dishes = sample_dishes()
        staple = dishes[0]
        side = replace(dishes[3], default_oil_g=target.oil_limit_g + 10)
        self.assertEqual(build_candidates(target, [staple], [side], t, relaxed=True), [])
        side = replace(dishes[3], default_salt_g=target.salt_limit_g + 2)
        self.assertEqual(build_candidates(target, [staple], [side], t, relaxed=True), [])
        side = replace(dishes[3], default_salt_g=0, sodium_mg=(target.salt_limit_g+1)*1000/2.54)
        self.assertEqual(build_candidates(target, [staple], [side], t, relaxed=True), [])
        unknown = replace(staple, default_oil_g=None)
        side = replace(dishes[3], default_oil_g=target.oil_limit_g / .75 + 1)
        self.assertEqual(build_candidates(target, [unknown], [side], t, relaxed=True), [])

    def test_unknown_and_hard_filters(self):
        t = self.targets(["午"])
        target = t.meal_targets["午"]
        dishes = sample_dishes()
        staple = dishes[0]
        side = replace(dishes[3], default_oil_g=None)
        pool = build_candidates(target, [staple], [side], t, relaxed=True)
        self.assertTrue(pool)
        self.assertIsNone(pool[0].totals["oil_g"])
        self.assertIn("oil_salt_unknown", pool[0].reason_codes)
        side = replace(dishes[3], sodium_mg=None)
        pool = build_candidates(target, [staple], [side], t, relaxed=True)
        self.assertTrue(pool)
        self.assertIsNone(pool[0].totals["sodium_mg"])
        self.assertIn("oil_salt_unknown", pool[0].reason_codes)
        for excluded in [dishes[-1], dishes[-2]]:
            self.assertEqual(build_candidates(target, [staple], [excluded], t, relaxed=True), [])
        self.assertEqual(build_candidates(target, [staple], [replace(side, energy_kcal=None)], t, relaxed=True), [])


if __name__ == "__main__":
    unittest.main()
