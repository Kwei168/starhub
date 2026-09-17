# -*- coding: utf-8 -*-
"""FIX-2: RAGAS JSON 解析容错测试。"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

import build_daily_insight as B

B.NOW_BJ = B._now_bj()


class TestRobustParseJson(unittest.TestCase):
    """_robust_parse_json 应处理截断、前后缀噪音。"""

    def test_valid_json(self):
        text = ('{"context_coverage": 0.8, "faithfulness": 0.9,'
                ' "relevance": 0.7, "feedback": "good", "weak_events": []}')
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["context_coverage"], 0.8)

    def test_json_with_prefix_text(self):
        text = ('好的，以下是评估结果：\n'
                '{"context_coverage": 0.8, "faithfulness": 0.9,'
                ' "relevance": 0.7, "feedback": "ok", "weak_events": []}')
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["faithfulness"], 0.9)

    def test_truncated_json_missing_braces(self):
        text = ('{"context_coverage": 0.8, "faithfulness": 0.9,'
                ' "relevance": 0.7, "feedback": "needs improvement",'
                ' "weak_events": [2')
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["context_coverage"], 0.8)

    def test_empty_input(self):
        self.assertIsNone(B._robust_parse_json(""))
        self.assertIsNone(B._robust_parse_json(None))

    def test_no_json_at_all(self):
        self.assertIsNone(B._robust_parse_json("just plain text"))

    def test_json_with_suffix(self):
        text = ('{"context_coverage": 0.7, "faithfulness": 0.8,'
                ' "relevance": 0.6, "feedback": "ok", "weak_events": []}'
                '\n以上是评估结果。')
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["context_coverage"], 0.7)


if __name__ == "__main__":
    unittest.main()
