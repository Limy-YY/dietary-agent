import unittest

from app.routers.agent import _search_knowledge
from app.routers.nutrition import MICRO_IDS, _achievement


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


if __name__ == "__main__":
    unittest.main()
