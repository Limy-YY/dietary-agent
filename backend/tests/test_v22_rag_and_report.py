import unittest

from app.routers.agent import _search_knowledge
from app.routers.nutrition import MICRO_IDS, _achievement, _macro_summary


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
            "score": 1.0,
        }])
        items = _search_knowledge("高血压人群平时应该怎么控制盐的摄入？", 1, db)
        self.assertEqual(items[0].source_id, "NHC-HTN-2023")
        self.assertIn("jsonb_array_elements_text", db.sql)
        self.assertEqual(db.params["query"], "高血压人群平时应该怎么控制盐的摄入？")

    def test_micro_overall_reports_its_real_denominator(self):
        agg = {
            "_by_date": {
                "2026-11-20": {
                    "selected": 1,
                    "count": {"m:calcium": 1},
                    "sum": {"m:calcium": 800.0},
                }
            }
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
