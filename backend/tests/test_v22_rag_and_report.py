import unittest
from unittest.mock import patch

from app.routers.agent import _search_hybrid, _search_knowledge
from app.routers.mealplan import _reviewed_tip
from app.routers.nutrition import MICRO_IDS, _achievement, _aggregate_rows, _macro_summary


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return _Rows(self.rows)


class RagAndReportTests(unittest.TestCase):
    def test_chinese_question_uses_document_aliases(self):
        db = _Db([{
            "knowledge_doc_id": 1,
            "title": "高血压人群膳食要点",
            "content": "控盐是第一位的。",
            "category": "病种",
            "source": "成人高血压食养指南（2023年版）",
            "source_id": "NHC-HTN-2023",
            "source_url": "https://example.test/htn",
            "boost": 1.0,
        }])
        items = _search_knowledge("高血压人群平时应该怎么控制盐的摄入？", 1, db)
        self.assertEqual(items[0].source_id, "NHC-HTN-2023")
        self.assertIn("jsonb_array_elements_text", db.sql)
        self.assertEqual(db.params["query"], "高血压人群平时应该怎么控制盐的摄入？")

    def test_hybrid_preserves_the_official_source_link(self):
        url = "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"
        db = _Db([{
            "knowledge_doc_id": 2,
            "title": "铁",
            "content": "促进吸收或利用：维生素C",
            "source": "NIH ODS",
            "source_id": None,
            "source_url": url,
            "category": "矿物质",
            "score": 0.03,
        }])
        with patch("app.routers.agent.embed_text", return_value=[0.1]):
            items, method = _search_hybrid("铁的吸收", 1, db)
        self.assertEqual(method, "hybrid_rrf")
        self.assertEqual(items[0].source_url, url)
        self.assertEqual(items[0].source, "NIH ODS")

    def test_nutrition_tip_requires_review_record(self):
        tip = {"function": ["样本文案"], "review_status": "pending"}
        self.assertEqual(_reviewed_tip({"nutrition_tip": tip}), {})
        tip["review_status"] = "approved"
        self.assertEqual(_reviewed_tip({"nutrition_tip": tip}), {})
        tip.update(reviewer="test-only", reviewed_at="2026-11-27T00:00:00Z")
        self.assertEqual(_reviewed_tip({"nutrition_tip": tip}), tip)

    def test_micro_overall_reports_its_real_denominator(self):
        agg = {
            # 达标天数只统计「三餐齐全」的完整天，这里给 1 个完整天的钙全天摄入
            "full_day_micro": {"calcium": [800.0]}
        }
        refs = {
            "calcium": {
                "reference_value": 800,
                "ul_value": 2000,
                "nutrient_name": "钙",
                "unit": "mg",
            }
        }
        result = _achievement(agg, refs, {})
        self.assertEqual(result["micro_overall_pct"], 100.0)
        self.assertEqual(result["micro_evaluable_count"], 1)
        self.assertEqual(result["micro_total_count"], len(MICRO_IDS))

    def test_full_day_ignores_snack_missing_micro(self):
        # 早/午/晚齐全 + 加餐：加餐缺某微量不应把整天从「完整天」里踢掉（旧实现
        # d["count"]["m:k"] >= d["selected"] 会把加餐也算进 selected，导致整天被误排除）。
        micro_full = {
            "calcium": 300.0, "iron": 5.0, "zinc": 3.0, "vitamin_a": 200.0,
            "vitamin_b1": 0.5, "vitamin_b2": 0.5, "vitamin_c": 60.0,
        }
        macro = {"kcal": 500.0, "protein_g": 20.0, "fat_g": 15.0, "carb_g": 70.0, "fiber_g": 5.0}
        oil_salt = {"oil_g": 5.0, "salt_g": 1.0, "sodium_mg": 400.0, "total_salt_equivalent_g": 1.0}
        rows = [
            {"slot_date": "2026-11-20", "meal_type": "早", "selected_candidate_id": 1,
             "macro_estimate": dict(macro), "micro_estimate": dict(micro_full), "oil_salt_estimate": dict(oil_salt)},
            {"slot_date": "2026-11-20", "meal_type": "午", "selected_candidate_id": 2,
             "macro_estimate": dict(macro), "micro_estimate": dict(micro_full), "oil_salt_estimate": dict(oil_salt)},
            {"slot_date": "2026-11-20", "meal_type": "晚", "selected_candidate_id": 3,
             "macro_estimate": dict(macro), "micro_estimate": dict(micro_full), "oil_salt_estimate": dict(oil_salt)},
            # 加餐：只有部分微量有值（缺 zinc/vitamin_a/b1/b2），不应导致整天被判「缺数据」
            {"slot_date": "2026-11-20", "meal_type": "加餐", "selected_candidate_id": 4,
             "macro_estimate": dict(macro),
             "micro_estimate": {"calcium": 50.0, "iron": 1.0, "vitamin_c": 20.0},
             "oil_salt_estimate": dict(oil_salt)},
        ]
        agg = _aggregate_rows(rows, days=1, subject="测试")
        self.assertEqual(agg["coverage"]["full_days"], 1)
        for k in MICRO_IDS:
            self.assertEqual(len(agg["full_day_micro"][k]), 1, f"{k} 应计入完整天")
        # 锌：早/午/晚各 3.0，加餐无值（null≠0 不加）→ 全天 9.0
        self.assertEqual(agg["full_day_micro"]["zinc"][0], 9.0)
        # 钙：早/午/晚各 300 + 加餐 50（加餐有值则并入）→ 950.0
        self.assertEqual(agg["full_day_micro"]["calcium"][0], 950.0)

    def test_sodium_reference_uses_2000mg_ceiling_not_ai_1500(self):
        agg = {
            "energy_kcal": 1800.0,
            "protein_g": 70.0,
            "fat_g": 60.0,
            "carb_g": 250.0,
            "fiber_g": 20.0,
            "oil_g": 10.0,
            "salt_g": 3.0,
            "sodium_mg": 1800.0,
            "total_salt_equivalent_g": 4.5,
        }
        # 数据字典里钠的 AI=1500mg 是「适宜摄入量」，不应被当作超标上限
        refs = {
            "sodium": {"reference_value": 1500.0},
            "dietary_fiber": {"reference_value": 25.0},
        }
        macro = _macro_summary(agg, refs)
        self.assertEqual(macro["sodium_reference"], 2000.0)
        self.assertEqual(macro["sodium_status"], "ok")  # 1800 < 2000，未超上限
        self.assertAlmostEqual(macro["sodium_pct"], 90.0)


if __name__ == "__main__":
    unittest.main()
