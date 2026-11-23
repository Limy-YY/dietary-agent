# -*- coding: utf-8 -*-
"""配餐执行新路径回归：C 快路径 / 富意图映射 / 覆盖度反馈 / 多工具守卫。"""
import unittest
from datetime import date
from unittest.mock import patch

import agent


def _plan():
    cand = {
        "candidate_id": 11,
        "macro_estimate": {"kcal": 600},
        "micro_estimate": {"calcium": 0.5},
        "dishes": [{"name": "米饭"}],
    }
    return {
        "meal_plan_id": 1,
        "status": "candidates",
        "plan_type": "日",
        "start_date": "2026-11-23",
        "end_date": "2026-11-23",
        "goal_energy_kcal": 1800.0,
        "goal_code": "maintain",
        "why_summary": "主食打底",
        "reference_hints": ["蔬菜偏低"],
        "data_quality_notes": [],
        "slots": [{
            "meal_slot_id": 10, "slot_date": "2026-11-23", "meal_type": "午",
            "target_macro": {"kcal": 600},
            "selected_candidate_id": 11,
            "selected_candidate": cand,
            "candidates": [cand],
        }],
    }


class MapIntentTests(unittest.TestCase):
    def test_map_rich_intent_full(self):
        rich = {
            "scope": {"start_date": "2026-11-24", "end_date": "2026-11-30",
                      "meal_types": ["早", "午", "晚"]},
            "hard_constraints": {"exclude_ingredients": ["牛肉"]},
            "soft_preferences": {"theme": "清淡中式", "soft_avoid": ["油炸"],
                                 "priority": ["控糖 > 少油"]},
            "day_overrides": [{"date": "2026-11-26", "meal_types": ["晚"], "hint": "有应酬"}],
            "user_explicits": {"want": ["清蒸鱼"], "avoid": ["香菜"]},
        }
        p = agent._map_plan_intent(rich, "这周清淡点，不要香菜")
        self.assertEqual(p["start_date"], "2026-11-24")
        self.assertEqual(p["end_date"], "2026-11-30")
        self.assertEqual(p["meal_types"], ["breakfast", "lunch", "dinner"])
        self.assertIn("牛肉", p["exclude_ingredients"])
        self.assertIn("香菜", p["exclude_ingredients"])  # user_explicits.avoid → 硬排除
        self.assertIn("油炸", p["soft_avoid"])
        self.assertIn("炒", p["soft_avoid"])  # theme 清淡 → 高油做法关键词
        self.assertEqual(p["day_overrides"], rich["day_overrides"])
        self.assertEqual(p["priority"], ["控糖 > 少油"])
        self.assertEqual(p["user_explicits"], rich["user_explicits"])

    def test_map_rich_intent_deterministic_exclude(self):
        rich = {"scope": {"meal_types": ["午"]}, "hard_constraints": {},
                "soft_preferences": {}, "user_explicits": {}}
        p = agent._map_plan_intent(rich, "午餐不要牛肉")
        self.assertIn("牛肉", p["exclude_ingredients"])

    def test_map_rich_intent_defaults_today(self):
        rich = {"scope": {}, "hard_constraints": {}, "soft_preferences": {}, "user_explicits": {}}
        p = agent._map_plan_intent(rich, "配个餐")
        self.assertEqual(p["start_date"], date.today().isoformat())
        self.assertEqual(p["meal_types"], ["breakfast", "lunch", "dinner"])

    def test_map_rich_intent_week_fallback(self):
        # 「这周清淡点」富意图若没抽到日期，靠 kind=plan_week 兜底成 7 天，不能塌成单日
        rich = {"scope": {}, "hard_constraints": {}, "soft_preferences": {}, "user_explicits": {}}
        p = agent._map_plan_intent(rich, "这周清淡点", kind="plan_week")
        from datetime import timedelta
        self.assertEqual(p["end_date"], (date.today() + timedelta(days=6)).isoformat())


class CoverageFeedbackTests(unittest.TestCase):
    def test_feedback_extracts_all(self):
        fb = agent._plan_coverage_feedback({
            "why_summary": "主食打底",
            "reference_hints": ["蔬菜偏低"],
            "data_quality_notes": ["部分数据待核查"],
        })
        self.assertIn("主食打底", fb)
        self.assertIn("蔬菜偏低", fb)
        self.assertIn("部分数据待核查", fb)


class ExtraToolTests(unittest.TestCase):
    def test_wants_extra_tool(self):
        self.assertTrue(agent._wants_extra_tool("排三天午餐顺便列清单"))
        self.assertTrue(agent._wants_extra_tool("生成一周食谱，然后给我食材清单"))
        self.assertFalse(agent._wants_extra_tool("生成一日三餐"))


class RunPlanTests(unittest.TestCase):
    def test_fast_path_generates_once(self):
        with patch.object(agent, "_llm", return_value=object()), \
             patch.object(agent.bc, "generate_meal_plan", return_value=_plan()) as gen, \
             patch.object(agent, "_narrate", return_value={"messages": [], "temperature": 0.6, "fallback": "x"}):
            result = agent._run_plan("u", {"user_id": "u"}, "生成一日三餐", "plan_day",
                                     {"intent": "plan_day"}, None, None, {}, {})
        gen.assert_called_once()
        self.assertEqual(result["blocks"][0]["type"], "meal_card")
        self.assertIsNotNone(result["narration"])

    def test_rich_path_generates_and_reviews(self):
        rich = {"scope": {"start_date": "2026-11-24", "end_date": "2026-11-30",
                          "meal_types": ["早", "午", "晚"]}, "needs_clarification": False}
        with patch.object(agent, "_llm", return_value=object()), \
             patch.object(agent, "_extract_plan_intent", return_value=rich), \
             patch.object(agent.bc, "generate_meal_plan", return_value=_plan()) as gen, \
             patch.object(agent, "_review_plan", return_value={"messages": [], "temperature": 0.6, "fallback": "x"}):
            result = agent._run_plan("u", {"user_id": "u"}, "这周清淡点，周三晚有应酬", "plan_week",
                                     {"intent": "plan_week"}, None, None, {}, {})
        gen.assert_called_once()
        self.assertEqual(result["blocks"][0]["type"], "meal_card")
        self.assertIsNotNone(result["narration"])

    def test_rich_path_clarifies(self):
        with patch.object(agent, "_llm", return_value=object()), \
             patch.object(agent, "_extract_plan_intent",
                          return_value={"needs_clarification": True, "clarify_question": "你想排哪几天？"}):
            result = agent._run_plan("u", {"user_id": "u"}, "帮我排个餐", "plan_custom",
                                     {"intent": "plan_custom"}, None, None, {}, {})
        self.assertEqual(result, {"text": "你想排哪几天？", "blocks": []})


if __name__ == "__main__":
    unittest.main()
