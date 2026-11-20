import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.mealplan import _next_swap_candidate
from app.services.rule_engine.pipeline import _vary_equivalent_pool


class SwapVarietyTests(unittest.TestCase):
    def test_swap_cycles_all_ranked_candidates(self):
        candidates = [
            N(candidate_id=103, rank=3),
            N(candidate_id=101, rank=1),
            N(candidate_id=102, rank=2),
        ]
        self.assertEqual(_next_swap_candidate(candidates, 101).candidate_id, 102)
        self.assertEqual(_next_swap_candidate(candidates, 102).candidate_id, 103)
        self.assertEqual(_next_swap_candidate(candidates, 103).candidate_id, 101)

    def test_generation_seed_varies_only_equivalent_candidates(self):
        def candidate(i):
            return N(
                dish_ids=[f'DISH-X{i}'], totals={'kcal': 700.0}, score=.1,
                reason_codes=[], score_breakdown={'attributes': {'full_staples': 1,
                    'vegetable_g': 100}, 'meal_type': '午', 'energy_gap': 0},
            )
        pool = [candidate(i) for i in range(5)]
        target = N(kcal=700.0)
        firsts = {
            _vary_equivalent_pool(pool, target, [], seed, '2026-11-20', '午')[0].dish_ids[0]
            for seed in range(12)
        }
        self.assertGreater(len(firsts), 1)
        for seed in range(3):
            varied = _vary_equivalent_pool(pool, target, [], seed, '2026-11-20', '午')
            self.assertEqual({id(c) for c in varied}, {id(c) for c in pool})


if __name__ == '__main__':
    unittest.main()
