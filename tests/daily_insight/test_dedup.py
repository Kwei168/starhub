# -*- coding: utf-8 -*-
"""FIX-3: Phase 1 后跨源去重测试。"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

import build_daily_insight as B

B.NOW_BJ = B._now_bj()


class TestDeduplicateAfterPhase1(unittest.TestCase):
    """_deduplicate_after_phase1 应合并同 category 且标签相似的事件。"""

    def test_same_category_high_jaccard_merged(self):
        """同 category + Jaccard>=0.5 → 合并。"""
        clusters = [
            {"label": "Anthropic 用 Claude Code 从零重写 Claude Design",
             "category": "product", "items": [{"title": "a"}],
             "source_types": {"rss"}, "score": 5},
            {"label": "Anthropic 用自研工具重写 Claude Design",
             "category": "product", "items": [{"title": "b"}],
             "source_types": {"aihot"}, "score": 3},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 1, "应合并为 1 个事件")
        self.assertEqual(len(result[0]["items"]), 2)

    def test_different_category_not_merged(self):
        """不同 category → 不合并。"""
        clusters = [
            {"label": "OpenAI 发布 GPT-6", "category": "model",
             "items": [{"title": "a"}], "source_types": {"rss"}, "score": 5},
            {"label": "OpenAI 发布 GPT-6 引发讨论", "category": "policy",
             "items": [{"title": "b"}], "source_types": {"aihot"}, "score": 3},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 2, "不同 category 不应合并")

    def test_low_jaccard_not_merged(self):
        """同 category 但 Jaccard<0.5 → 不合并。"""
        clusters = [
            {"label": "Claude Design 重写", "category": "product",
             "items": [{"title": "a"}], "source_types": {"rss"}, "score": 5},
            {"label": "量子计算重大突破", "category": "product",
             "items": [{"title": "b"}], "source_types": {"aihot"}, "score": 3},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 2, "Jaccard 过低不应合并")

    def test_higher_score_label_wins(self):
        """合并时保留高分事件的 label。"""
        clusters = [
            {"label": "低分 OpenAI 模型 报道", "category": "tech",
             "items": [{"title": "a"}], "source_types": {"rss"}, "score": 2},
            {"label": "高分 OpenAI 模型 深度分析", "category": "tech",
             "items": [{"title": "b"}], "source_types": {"aihot"}, "score": 8},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "高分 OpenAI 模型 深度分析")

    def test_source_types_merged(self):
        """合并后 source_types 应包含双方。"""
        clusters = [
            {"label": "AI 新闻 事件报道", "category": "news",
             "items": [{"title": "a"}], "source_types": {"rss", "hot"}, "score": 5},
            {"label": "AI 新闻 事件深度分析", "category": "news",
             "items": [{"title": "b"}], "source_types": {"agihunt"}, "score": 3},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 1)
        self.assertIn("rss", result[0]["source_types"])
        self.assertIn("agihunt", result[0]["source_types"])

    def test_empty_and_single(self):
        """空和单元素不崩溃。"""
        self.assertEqual(B._deduplicate_after_phase1([]), [])
        single = [{"label": "x", "category": "y", "items": [], "source_types": set(), "score": 1}]
        self.assertEqual(len(B._deduplicate_after_phase1(single)), 1)

    def test_chain_merge(self):
        """三个事件两两相似 → 全部合并。"""
        clusters = [
            {"label": "Claude Design 重写更新", "category": "product",
             "items": [{"title": "a"}], "source_types": {"rss"}, "score": 5},
            {"label": "Claude Design 用新工具重写", "category": "product",
             "items": [{"title": "b"}], "source_types": {"aihot"}, "score": 3},
            {"label": "Claude Design 完全重写版本", "category": "product",
             "items": [{"title": "c"}], "source_types": {"agihunt"}, "score": 4},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 1, "三个相似事件应全部合并")
        self.assertEqual(len(result[0]["items"]), 3)


if __name__ == "__main__":
    unittest.main()
