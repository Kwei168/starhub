# -*- coding: utf-8 -*-
"""T2.1-T2.5: COSTAR 提示词结构测试。"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

import build_daily_insight as B

B.NOW_BJ = B._now_bj()


class TestPhase1Prompt(unittest.TestCase):
    """Phase 1 提示词应包含 COSTAR 六要素 + 写法框架 + 正确示例。"""

    def test_system_prompt_has_context(self):
        self.assertIn("Context", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_objective(self):
        self.assertIn("Objective", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_style(self):
        self.assertIn("Style", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_tone(self):
        self.assertIn("Tone", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_audience(self):
        self.assertIn("Audience", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_response(self):
        self.assertIn("Response", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_writing_framework(self):
        self.assertIn("宏观主线", B._SYSTEM_PROMPT_P1)
        self.assertIn("微观佐证", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_fewshot_example(self):
        self.assertIn("正确示例", B._SYSTEM_PROMPT_P1)
        self.assertIn("summary", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_banned_phrases(self):
        self.assertIn("禁用", B._SYSTEM_PROMPT_P1)
        self.assertIn("值得关注", B._SYSTEM_PROMPT_P1)

    def test_system_prompt_has_platform_dna(self):
        dna_keywords = ["36氪", "虎嗅", "微博", "知乎", "Hacker News"]
        found = sum(1 for kw in dna_keywords if kw in B._SYSTEM_PROMPT_P1)
        self.assertGreaterEqual(found, 5,
                                "应包含至少 5 个平台 DNA，实际 %d" % found)


class TestPhase2Prompt(unittest.TestCase):
    """Phase 2 提示词应包含 COSTAR + 时间线叙事 + 影响分层。"""

    def test_p2_system_has_context(self):
        self.assertIn("Context", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_objective(self):
        self.assertIn("Objective", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_style(self):
        self.assertIn("Style", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_tone(self):
        self.assertIn("Tone", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_audience(self):
        self.assertIn("Audience", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_response(self):
        self.assertIn("Response", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_timeline_framework(self):
        self.assertIn("时间线", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_impact_layers(self):
        self.assertIn("短期", B._SYSTEM_PROMPT_P2)
        self.assertIn("中期", B._SYSTEM_PROMPT_P2)
        self.assertIn("长期", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_fewshot_example(self):
        self.assertIn("正确示例", B._SYSTEM_PROMPT_P2)
        self.assertIn("event_reconstruction", B._SYSTEM_PROMPT_P2)

    def test_p2_system_has_banned_phrases(self):
        self.assertIn("禁用", B._SYSTEM_PROMPT_P2)


if __name__ == "__main__":
    unittest.main()
