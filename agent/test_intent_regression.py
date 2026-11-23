# -*- coding: utf-8 -*-
"""意图回归表（Agent 侧，锁正则 canonical/gray 边界）。

收敛原则：_regex_intent 当「高精度」分类器——canonical 话术命中，语义灰区返回 None 交 LLM。
灰区样例是 P0 收敛的回归锚点（「推荐补钙食物」「贫血吃什么」曾因正则高召回被误判成配餐）。
"""
import unittest

import agent


class IntentRegressionTests(unittest.TestCase):
    def _intent(self, msg):
        return agent._regex_intent(msg)

    # ── canonical 话术必须命中 ──
    def test_swap_with_meal(self):
        self.assertEqual(self._intent("换一换午餐"), {"intent": "swap_candidate", "meal_type": "午餐"})

    def test_choose_with_meal(self):
        r = self._intent("选这个晚餐")
        self.assertEqual(r["intent"], "choose_candidate")
        self.assertEqual(r["meal_type"], "晚餐")

    def test_confirm_and_fix(self):
        for msg in ("确认", "固定", "就这个方案"):
            self.assertEqual(self._intent(msg)["intent"], "confirm", msg)

    def test_replace_is_confirm(self):
        r = self._intent("替换")
        self.assertEqual(r["intent"], "confirm")
        self.assertTrue(r["replace"])

    def test_cancel(self):
        for msg in ("取消", "算了", "不用了"):
            self.assertEqual(self._intent(msg)["intent"], "cancel", msg)

    def test_plan_day(self):
        for msg in ("生成一日三餐", "今天吃什么", "三餐"):
            self.assertEqual(self._intent(msg)["intent"], "plan_day", msg)

    def test_plan_week(self):
        for msg in ("生成一周食谱", "一周", "七天"):
            self.assertEqual(self._intent(msg)["intent"], "plan_week", msg)

    def test_plan_meal(self):
        self.assertEqual(self._intent("推荐一餐")["intent"], "plan_meal")
        self.assertEqual(self._intent("推荐午餐"), {"intent": "plan_meal", "meal_type": "午餐"})

    def test_report_week_and_month(self):
        self.assertEqual(self._intent("生成周膳食报告"), {"intent": "report", "scope": "week"})
        self.assertEqual(self._intent("生成月膳食报告"), {"intent": "report", "scope": "month"})

    def test_aux_card_actions(self):
        self.assertEqual(self._intent("完整食谱")["intent"], "recipe_detail")
        self.assertEqual(self._intent("食材清单")["intent"], "shopping_list")
        self.assertEqual(self._intent("为什么这样搭")["intent"], "explain")

    # ── 语义灰区必须返回 None（交 LLM）──
    def test_gray_qa_not_plan(self):
        for msg in ("推荐补钙食物", "贫血吃什么", "高血压食谱", "吃什么补铁"):
            self.assertIsNone(self._intent(msg), msg)

    def test_gray_soft_pref_not_plan(self):
        self.assertIsNone(self._intent("这周清淡点"))

    def test_gray_meal_question_deferred(self):
        # 「午餐吃什么」这类模糊餐次提问交 LLM（不再正则抢占）
        self.assertIsNone(self._intent("午餐吃什么"))

    def test_gray_custom_span_deferred(self):
        for msg in ("出差三天", "三天", "下周一到周三", "只排午餐"):
            self.assertIsNone(self._intent(msg), msg)


if __name__ == "__main__":
    unittest.main()
