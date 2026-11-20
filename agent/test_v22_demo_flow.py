import unittest
from unittest.mock import patch

import agent
import blocks
import conversation_state as cs


def plan(status="candidates"):
    candidate = {
        "candidate_id": 11,
        "sources": [{"title": "中国居民膳食指南"}],
        "macro_estimate": {"kcal": 600},
        "dishes": [{"dish_id": "DISH-001", "name": "米饭"}],
    }
    return {
        "meal_plan_id": 1,
        "status": status,
        "plan_type": "日",
        "slots": [{
            "meal_slot_id": 10,
            "slot_date": "2026-11-23",
            "meal_type": "午",
            "selected_candidate_id": 11,
            "selected_candidate": candidate,
            "candidates": [candidate],
        }],
    }


class DemoFlowTests(unittest.TestCase):
    def setUp(self):
        cs.clear_for_tests()

    def test_confirm_then_analyze_uses_fixed_plan(self):
        fixed = plan("fixed")
        report = {"nutrition_report_id": 8, "report_type": "plan", "meal_plan_id": 1}
        with cs.locked("u", "c") as state:
            agent.le.remember(state, plan())
        with patch.object(agent, "_load_profile", return_value={}), \
             patch.object(agent, "classify", return_value={"intent": "confirm"}), \
             patch.object(agent.bc, "fix_meal_plan", return_value=fixed) as confirm, \
             patch.object(agent.bc, "nutrition_analysis", return_value=report) as analyze:
            result = agent.run(
                "u", "确认这份方案，并帮我分析一下营养结构",
                conversation_id="c",
            )
        confirm.assert_called_once_with(meal_plan_id=1, replace=False)
        analyze.assert_called_once_with(1)
        self.assertEqual([b["type"] for b in result["blocks"]], ["meal_card", "report"])
        self.assertEqual(result["blocks"][0]["status"], "fixed")

    def test_rag_sources_are_numbered_from_real_fields(self):
        material, footer = agent._rag_material([{
            "doc_id": "12",
            "title": "钙摄入建议",
            "content": "一段检索内容",
            "source": "中国居民膳食营养素参考摄入量",
            "source_id": "DRI-2023",
            "source_url": "https://example.test/dri",
        }])
        self.assertIn("[1] 标题：钙摄入建议", material)
        self.assertIn("来源编号：DRI-2023", material)
        self.assertIn("[1] [中国居民膳食营养素参考摄入量（DRI-2023）](https://example.test/dri)", footer)

    def test_meal_card_preserves_candidate_sources(self):
        card = blocks.meal_card_block(plan())
        sources = card["slots"][0]["candidates"][0]["sources"]
        self.assertEqual(sources, [{"title": "中国居民膳食指南"}])


if __name__ == "__main__":
    unittest.main()
