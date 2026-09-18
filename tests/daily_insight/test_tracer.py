# -*- coding: utf-8 -*-
"""FIX-7: PipelineTracer 端到端追踪日志测试。"""
import os
import sys
import json
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

import build_daily_insight as B

B.NOW_BJ = B._now_bj()

# 测试隔离：PipelineTracer.flush() 会写真实 TRACKING_FILE（受版本控制），
# 重定向到临时目录避免污染工作区与 CI 提交
import tempfile as _tempfile
B.TRACKING_FILE = os.path.join(_tempfile.mkdtemp(prefix="tracer_test_"), "tracking.jsonl")


class TestPipelineTracer(unittest.TestCase):
    """PipelineTracer 应收集各阶段数据并输出结构化 JSONL。"""

    def test_basic_lifecycle(self):
        """创建 → set_meta → flush 应产出完整记录。"""
        tracer = B.PipelineTracer()
        tracer.set_meta(llm_available=True, mode="incremental")
        entry = tracer.flush()
        self.assertIn("ts", entry)
        self.assertIn("stages", entry)
        self.assertIn("llm_calls", entry)
        self.assertIn("meta", entry)
        self.assertTrue(entry["meta"]["llm_available"])

    def test_trace_queries(self):
        """trace_queries 应记录源计数。"""
        tracer = B.PipelineTracer()
        tracer.trace_queries(rss_count=100, hot_count=400, aihot_count=50,
                             agihunt_count=200, chunks_total=750,
                             queries_count=10, retrieved_top_k=80)
        self.assertIn("queries", tracer.stages)
        self.assertEqual(tracer.stages["queries"]["source_counts"]["rss"], 100)

    def test_trace_llm_call_truncates_prompt(self):
        """prompt 截断至 5000 字符。"""
        tracer = B.PipelineTracer()
        long_prompt = "x" * 10000
        tracer.trace_llm_call(
            phase="phase1", event_idx=None,
            prompt_text=long_prompt, model_name="test",
            temperature=0.3, max_tokens=3000,
            raw_response="response", parse_ok=True,
            parsed_result={"label": "test"})
        call = tracer.llm_calls[0]
        self.assertEqual(call["prompt_chars"], 10000)
        self.assertLessEqual(len(call["prompt_preview"]), 5000)

    def test_trace_llm_call_truncates_response(self):
        """response 截断至 3000 字符。"""
        tracer = B.PipelineTracer()
        long_response = "y" * 8000
        tracer.trace_llm_call(
            phase="phase2", event_idx=0,
            prompt_text="short", model_name="test",
            temperature=0.3, max_tokens=3000,
            raw_response=long_response, parse_ok=True,
            parsed_result={})
        call = tracer.llm_calls[0]
        self.assertLessEqual(len(call["raw_response_preview"]), 3000)

    def test_trace_clustering(self):
        """trace_clustering 应记录聚类方法和事件摘要。"""
        tracer = B.PipelineTracer()
        tracer.trace_clustering(method="semantic", threshold=0.75,
                                before_count=50, after_count=10,
                                events_summary=[{"label": "test"}])
        self.assertEqual(tracer.stages["clustering"]["method"], "semantic")
        self.assertEqual(tracer.stages["clustering"]["after_count"], 10)

    def test_exception_safety(self):
        """trace 方法异常不应影响主流程。"""
        tracer = B.PipelineTracer()
        # 传入不可序列化的对象不应崩溃
        try:
            tracer.trace_llm_call(
                phase="phase1", event_idx=None,
                prompt_text="test", model_name="test",
                temperature=0.3, max_tokens=3000,
                raw_response=None, parse_ok=True,
                parsed_result={"key": object()})
        except Exception:
            self.fail("trace_llm_call 不应抛出异常")

    def test_no_api_key_leak(self):
        """记录中不应包含 API key。"""
        tracer = B.PipelineTracer()
        tracer.trace_llm_call(
            phase="phase1", event_idx=None,
            prompt_text="test prompt", model_name="test",
            temperature=0.3, max_tokens=3000,
            raw_response="test response", parse_ok=True,
            parsed_result={"label": "test"})
        entry_json = json.dumps(tracer.flush(), ensure_ascii=False)
        for key_name in ["AGNES_API_KEY", "api_key", "API_KEY"]:
            self.assertNotIn(key_name, entry_json)


if __name__ == "__main__":
    unittest.main()
