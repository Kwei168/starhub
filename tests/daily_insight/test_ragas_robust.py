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


class TestAdoptionNoiseGuard:
    """01:12 期实证：复评基线漂移 0.05 内，'改善即采纳'会采纳劣化版。
    要求修正版超过 pre_score + 0.02 才采纳，且修正轮数回退 1。"""

    def test_adoption_margin_and_single_round(self):
        import os
        src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                                "build_daily_insight.py"), encoding="utf-8").read()
        assert "pre_score + 0.02" in src
        assert "RAGAS_MAX_CORRECTIONS = 1" in src


class TestFaithFinalGate:
    """R2: faith 终局防线——采纳须 faith 不劣化 + 修正环后二次核查 + 证据包跨事件禁令。"""

    def _src(self):
        import os
        return open(os.path.join(os.path.dirname(__file__), "..", "..",
                                 "build_daily_insight.py"), encoding="utf-8").read()

    def test_adoption_requires_faith_non_degrade(self):
        src = self._src()
        assert "pre_faith - 0.02" in src, "采纳闸必须含 faith 不劣化约束"

    def test_evidence_header_bans_cross_event(self):
        assert "严禁把其事实或数字嫁接到本事件主角" in self._src()

    def test_recheck_helper_behavior(self):
        import build_daily_insight as B
        calls = []
        bak = B._verify_faithfulness
        B._verify_faithfulness = lambda llm, clusters, ctx=None: calls.append(1)
        try:
            assert B._final_faith_recheck(None, [{"label": "x"}], []) is False
            assert calls == []
            assert B._final_faith_recheck(object(), [{"label": "x"}], []) is True
            assert len(calls) == 1
            assert B._final_faith_recheck(object(), [], []) is False

            def boom(llm, clusters, ctx=None):
                raise RuntimeError("llm down")
            B._verify_faithfulness = boom
            assert B._final_faith_recheck(object(), [{"label": "x"}], []) is False
        finally:
            B._verify_faithfulness = bak

    def test_recheck_wired_after_correction_dedup(self):
        src = self._src()
        i_dedup = src.find("去重必须在其后再跑一轮")
        i_recheck = src.find("_final_faith_recheck(llm, clusters, retrieved_for_ragas)")
        i_score = src.find("c[\"editor_score\"] = _quick_score_event(c, yesterday_labels=_yday_labels)", i_recheck)
        assert -1 < i_dedup < i_recheck < i_score, "终局核查须在修正后去重与分数刷新之间"


class TestAdoptionRollback:
    """P1-1 实证：_self_correct_events 原地写回 clusters，
    仅拒绝采纳不回滚文本 = 装饰品；拒绝分支必须快照还原。"""

    def _run(self, monkeypatch, faith_after):
        import build_daily_insight as B
        clusters = [{"label": "L1", "summary": "原摘要", "significance": "意义",
                     "category": "ai-models", "score": 5}]
        evals = [
            {"overall": 0.60, "context_coverage": 0.60, "faithfulness": 0.95,
             "relevance": 0.60, "feedback": "f", "weak_events": [1]},
            {"overall": 0.78, "context_coverage": 0.80, "faithfulness": faith_after,
             "relevance": 0.78, "feedback": "f", "weak_events": []},
            {"overall": 0.60, "context_coverage": 0.60, "faithfulness": 0.95,
             "relevance": 0.60, "feedback": "f", "weak_events": [1]},
        ]

        def fake_correct(llm, cls, ctx, ev):
            cls[0]["summary"] = "劣化摘要"
            return cls

        # T2 后非 CV 路径每组评估双采样：每群消费 2 次再前进
        state = {"i": 0, "r": 0}

        def fake_eval(llm, cls, theme, ctx, prompt_variant=None):
            d = dict(evals[min(state["i"], 2)])
            state["r"] += 1
            if state["r"] % 2 == 0:
                state["i"] += 1
            return d

        monkeypatch.setattr(B, "_self_correct_events", fake_correct)
        monkeypatch.setattr(B, "_evaluate_report_quality", fake_eval)
        chunks = [{"text": "素材内容" * 60, "title": "ctx", "source_type": "rss",
                   "retrieval_score": 1.0}]
        out_clusters, ev = B._ragas_evaluate_and_correct(
            object(), clusters, "主题", chunks, {})
        return out_clusters, ev

    def test_rejected_correction_restores_original_text(self, monkeypatch):
        out, ev = self._run(monkeypatch, faith_after=0.55)
        assert out[0]["summary"] == "原摘要", "拒绝采纳后必须回滚修正环的原文本"
        assert ev["faithfulness"] == 0.95

    def test_adopted_correction_keeps_new_text(self, monkeypatch):
        out, ev = self._run(monkeypatch, faith_after=0.96)
        assert out[0]["summary"] == "劣化摘要", "达标采纳时保留修正文本"


class TestRollbackNoNullInjection:
    """第7轮回归：回滚快照不得把「原本不存在的字段」写成 None
    （test_daily_insight 9i 实证：significance=None 让复评 prompt 构建 TypeError）。"""

    def test_missing_key_not_materialized_as_none(self, monkeypatch):
        import build_daily_insight as B
        clusters = [{"label": "L", "summary": "原摘要", "category": "research",
                     "score": 5}]  # 注意：无 significance 键
        groups = [
            {"overall": 0.60, "context_coverage": 0.60, "faithfulness": 0.95,
             "relevance": 0.60, "feedback": "f", "weak_events": [1]},
            {"overall": 0.78, "context_coverage": 0.80, "faithfulness": 0.55,
             "relevance": 0.78, "feedback": "f", "weak_events": []},
            {"overall": 0.60, "context_coverage": 0.60, "faithfulness": 0.95,
             "relevance": 0.60, "feedback": "f", "weak_events": [1]},
        ]
        state = {"i": 0, "r": 0}

        def fake_correct(llm, cls, ctx, ev):
            cls[0]["summary"] = "劣化"
            return cls

        def fake_eval(llm, cls, theme, ctx, prompt_variant=None):
            d = dict(groups[min(state["i"], 2)])
            state["r"] += 1
            if state["r"] % 2 == 0:
                state["i"] += 1
            return d

        monkeypatch.setattr(B, "_self_correct_events", fake_correct)
        monkeypatch.setattr(B, "_evaluate_report_quality", fake_eval)
        out, ev = B._ragas_evaluate_and_correct(
            object(), clusters, "t",
            [{"text": "素材" * 80, "title": "x", "source_type": "rss",
              "retrieval_score": 1.0}], {})
        assert out[0]["summary"] == "原摘要"
        assert "significance" not in out[0], \
            "回滚不能把缺失字段物化为 None——下游一律 get(k, \"\") 拿键存在即真"
