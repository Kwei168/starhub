# 每日洞察 CI 构建修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 CI 构建中发现的 6 项问题（热度归零、RAGAS 降级、事件重复、内容串位、resonance 空、历史文件过大）。

**Architecture:** 修改 `build_daily_insight.py` 中的热度计算（双参照系模型）、RAGAS 评估容错、Phase 1 后去重、Phase 2 前素材过滤；修改 `build_rss_aggregator.py` 中的历史分块存储。所有修改向后兼容。

**Tech Stack:** Python 3.11, unittest, hashlib, json

**Spec:** `docs/superpowers/specs/2026-09-17-daily-insight-ci-fix-spec.md`

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| Modify | `build_daily_insight.py` | FIX-1/3/4/5: 热度模型、去重、素材过滤 |
| Modify | `build_rss_aggregator.py` | FIX-6: 历史分块存储 |
| Create | `tests/daily_insight/test_dual_heat.py` | FIX-1: 双参照系热度测试 |
| Create | `tests/daily_insight/test_ragas_robust.py` | FIX-2: RAGAS JSON 容错测试 |
| Create | `tests/daily_insight/test_dedup.py` | FIX-3: 去重测试 |
| Create | `tests/daily_insight/test_material_filter.py` | FIX-4: 素材过滤测试 |
| Modify | `.gitignore` | FIX-6: 分块文件忽略规则 |
| Modify | `.github/workflows/update.yml` | FIX-6: Prune 步骤清理分块文件 |

---

### Task 1: FIX-2 — RAGAS JSON 容错

**Files:**
- Modify: `build_daily_insight.py:1700-1781`
- Test: `tests/daily_insight/test_ragas_robust.py`

- [ ] **Step 1: 写测试**

```python
# tests/daily_insight/test_ragas_robust.py
# -*- coding: utf-8 -*-
"""FIX-2: RAGAS JSON 解析容错测试。"""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import build_daily_insight as B
B.NOW_BJ = B._now_bj()

class TestRobustParseJson(unittest.TestCase):
    """_robust_parse_json 应处理截断、前后缀噪音。"""

    def test_valid_json(self):
        text = '{"context_coverage": 0.8, "faithfulness": 0.9, "relevance": 0.7, "feedback": "good", "weak_events": []}'
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["context_coverage"], 0.8)

    def test_json_with_prefix(self):
        text = '好的，以下是评估结果：\n{"context_coverage": 0.8, "faithfulness": 0.9, "relevance": 0.7, "feedback": "ok", "weak_events": []}'
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)

    def test_truncated_json(self):
        text = '{"context_coverage": 0.8, "faithfulness": 0.9, "relevance": 0.7, "feedback": "needs improvement in...", "weak_events": [2'
        result = B._robust_parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["context_coverage"], 0.8)

    def test_empty_input(self):
        self.assertIsNone(B._robust_parse_json(""))
        self.assertIsNone(B._robust_parse_json(None))

    def test_no_json_at_all(self):
        self.assertIsNone(B._robust_parse_json("just plain text"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_ragas_robust.py -v`
Expected: FAIL — `_robust_parse_json` 不存在

- [ ] **Step 3: 实现 `_robust_parse_json`**

在 `build_daily_insight.py` 的 `_parse_json` 函数后添加：

```python
def _robust_parse_json(text):
    """增强 JSON 解析：处理截断、前后缀噪音。"""
    if not text:
        return None
    parsed = _parse_json(text)
    if isinstance(parsed, dict):
        return parsed
    # 提取 { 到最后一个 } 之间的内容
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        parsed = _parse_json(candidate)
        if isinstance(parsed, dict):
            return parsed
    # 补全缺失的括号
    if start >= 0:
        candidate = text[start:]
        opens = candidate.count('{') - candidate.count('}')
        if opens > 0:
            candidate = candidate.rstrip(',').rstrip() + '}' * opens
        parsed = _parse_json(candidate)
        if isinstance(parsed, dict):
            return parsed
    return None
```

- [ ] **Step 4: 修改 `_evaluate_report_quality` 使用新函数 + max_tokens**

替换 L1755-1756:
```python
    result = llm.complete(messages, temperature=0.2, max_tokens=3000)
    parsed = _robust_parse_json(result)
```

修改 L1752 system prompt:
```python
        {"role": "system", "content": "你是 RAG 质量评估专家。只输出严格 JSON，不要任何解释、前言或后记。"},
```

修改 L1780 fallback:
```python
    return None  # 调用方检查 None 并降级
```

- [ ] **Step 5: 修改调用方处理 None 返回**

在 `_evaluate_report_quality` 返回 None 时，调用方降级：

L1862 处修改:
```python
        eval_result = _evaluate_report_quality(llm, current, theme, context_text)
        if eval_result is None:
            eval_result = {"context_coverage": 0.5, "faithfulness": 0.5, "relevance": 0.5,
                           "overall": 0.5, "feedback": "JSON 解析最终失败", "weak_events": []}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_ragas_robust.py -v`
Expected: 5/5 PASS

- [ ] **Step 7: 运行全量 TDD 测试确认无回归**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/ -v`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add build_daily_insight.py tests/daily_insight/test_ragas_robust.py
git commit -m "fix(insight): RAGAS JSON 解析容错 + max_tokens 500→3000"
```

---

### Task 2: FIX-1 + FIX-5 — 双参照系热度模型

**Files:**
- Modify: `build_daily_insight.py:1040-1098` (_score_clusters)
- Test: `tests/daily_insight/test_dual_heat.py`

- [ ] **Step 1: 写测试**

```python
# tests/daily_insight/test_dual_heat.py
# -*- coding: utf-8 -*-
"""FIX-1: 双参照系热度模型测试。"""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import build_daily_insight as B
B.NOW_BJ = B._now_bj()

class TestDualHeat(unittest.TestCase):
    """_compute_dual_heat 应聚合三层信号并归一化。"""

    def test_agihunt_heat(self):
        """AGI Hunt hot 值应贡献 score_a。"""
        cluster = {"label": "GPT-6 发布", "items": [
            {"source_type": "agihunt", "hot": 200, "title": "GPT-6"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertGreater(sa, 0, "AGI Hunt hot 应贡献 score_a")
        self.assertGreater(heat, 0)

    def test_aihot_heat(self):
        """AIHOT score 应贡献 score_a。"""
        cluster = {"label": "AI 新闻", "items": [
            {"source_type": "aihot", "score": 60, "title": "AI news"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertGreater(sa, 0)

    def test_hot_platform_heat(self):
        """热榜平台应贡献 score_b。"""
        cluster = {"label": "AI 热搜", "items": [
            {"source_type": "hot", "source": "weibo", "title": "AI"},
            {"source_type": "hot", "source": "zhihu", "title": "AI"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertGreater(sb, 0, "热榜平台应贡献 score_b")
        self.assertIn("weibo", plats)

    def test_breakout_resonance(self):
        """双高 → breakout。"""
        cluster = {"label": "AI 大事件", "items": [
            {"source_type": "agihunt", "hot": 300, "title": "AI big"},
            {"source_type": "hot", "source": "weibo", "title": "AI"},
            {"source_type": "hot", "source": "zhihu", "title": "AI"},
            {"source_type": "hot", "source": "baidu", "title": "AI"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertEqual(res, "breakout")

    def test_cap_prevents_domination(self):
        """单个子信号 cap 到 5 分，防止垄断。"""
        cluster = {"label": "test", "items": [
            {"source_type": "agihunt", "hot": 1000, "title": "x"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertLessEqual(sa, 10.0, "score_a 应 cap 到 10")

    def test_snapshot_reverse_lookup(self):
        """热榜 chunks 不在簇中时，应反查 hot_snapshot。"""
        hot_snapshot = [
            {"platform": "weibo", "items": [
                {"title": "GPT-6 发布震撼全球", "rank": 1, "hot": 999},
            ]},
        ]
        cluster = {"label": "GPT-6 发布引发讨论", "items": [
            {"source_type": "rss", "title": "GPT-6 发布了", "text": "GPT-6 发布", "source_key": "test"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, hot_snapshot)
        self.assertIn("weibo", plats, "应通过反查发现 weibo 热榜")

    def test_no_signals(self):
        """无任何信号源 → heat=0, resonance=""。"""
        cluster = {"label": "冷门事件", "items": [
            {"source_type": "rss", "title": "小更新", "source_key": "obscure"},
        ]}
        heat, sa, sb, plats, res = B._compute_dual_heat(cluster, [])
        self.assertEqual(heat, 0.0)
        self.assertEqual(res, "")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_dual_heat.py -v`
Expected: FAIL — `_compute_dual_heat` 不存在

- [ ] **Step 3: 实现 `_compute_dual_heat`**

在 `build_daily_insight.py` 的 `_score_clusters` 函数前添加（spec 中的完整代码）。

- [ ] **Step 4: 修改 `_score_clusters` 签名和调用**

签名改为 `_score_clusters(clusters, hot_snapshot)`。

替换 L1070-1095 的 hot_platforms/heat/resonance 计算为调用 `_compute_dual_heat`。

signal 字段新增 `score_a`, `score_b`。

- [ ] **Step 5: 修改调用处传入 hot_snapshot**

在主管线中找到 `_score_clusters(clusters)` 调用处，改为 `_score_clusters(clusters, hot_snapshot)`。

- [ ] **Step 6: 运行测试确认通过**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_dual_heat.py tests/daily_insight/test_query_and_heat.py -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add build_daily_insight.py tests/daily_insight/test_dual_heat.py
git commit -m "feat(insight): 双参照系热度模型 — AGI Hunt+AIHOT vs 热榜+RSS"
```

---

### Task 3: FIX-3 — Phase 1 后跨源去重

**Files:**
- Modify: `build_daily_insight.py` (新增 `_deduplicate_after_phase1`)
- Test: `tests/daily_insight/test_dedup.py`

- [ ] **Step 1: 写测试**

```python
# tests/daily_insight/test_dedup.py
# -*- coding: utf-8 -*-
"""FIX-3: Phase 1 后跨源去重测试。"""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import build_daily_insight as B
B.NOW_BJ = B._now_bj()

class TestDedup(unittest.TestCase):
    def test_merge_same_category_similar_labels(self):
        clusters = [
            {"label": "Anthropic用Claude Code从零重写Claude Design",
             "category": "ai-products", "score": 0.1, "items": [{"a": 1}],
             "source_types": {"rss"}, "summary": "v1"},
            {"label": "Anthropic用自研工具重写Claude Design",
             "category": "ai-products", "score": 0.08, "items": [{"b": 2}],
             "source_types": {"aihot"}, "summary": "v2"},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 1, "同类相似标签应合并")
        self.assertEqual(len(result[0]["items"]), 2)

    def test_no_merge_different_category(self):
        clusters = [
            {"label": "OpenAI 发布 GPT-6", "category": "ai-models",
             "score": 0.1, "items": [{}], "source_types": set(), "summary": ""},
            {"label": "OpenAI 发布 GPT-6", "category": "industry",
             "score": 0.1, "items": [{}], "source_types": set(), "summary": ""},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 2, "不同 category 不合并")

    def test_no_merge_dissimilar_labels(self):
        clusters = [
            {"label": "Claude 发布 Docs", "category": "ai-products",
             "score": 0.1, "items": [{}], "source_types": set(), "summary": ""},
            {"label": "英伟达 AI 能源联盟", "category": "industry",
             "score": 0.1, "items": [{}], "source_types": set(), "summary": ""},
        ]
        result = B._deduplicate_after_phase1(clusters)
        self.assertEqual(len(result), 2)
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 `_deduplicate_after_phase1`**（spec 中代码）

- [ ] **Step 4: 在主管线 L2853 后插入调用**

```python
clusters = _deduplicate_after_phase1(clusters)
```

- [ ] **Step 5: 运行测试 → Commit**

```bash
git add build_daily_insight.py tests/daily_insight/test_dedup.py
git commit -m "fix(insight): Phase 1 后跨源去重 — 同 category + Jaccard≥0.5 合并"
```

---

### Task 4: FIX-4 — Phase 2 前素材相关性过滤

**Files:**
- Modify: `build_daily_insight.py` (新增 `_filter_cluster_items`)
- Test: `tests/daily_insight/test_material_filter.py`

- [ ] **Step 1: 写测试**

```python
# tests/daily_insight/test_material_filter.py
# -*- coding: utf-8 -*-
"""FIX-4: Phase 2 前素材相关性过滤测试。"""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import build_daily_insight as B
B.NOW_BJ = B._now_bj()

class TestMaterialFilter(unittest.TestCase):
    def test_filter_keeps_related(self):
        cluster = {"items": [
            {"title": "Claude Code 重写 Design", "text": "Claude Design 重写"},
            {"title": "OpenAI 吹哨人法案", "text": "Lawfare 长文 AI 吹哨人"},
        ]}
        result = B._filter_cluster_items(cluster, "Claude Code 重写 Claude Design")
        self.assertEqual(len(result["items"]), 1, "应过滤无关 items")
        self.assertIn("Claude", result["items"][0]["title"])

    def test_filter_keeps_at_least_one(self):
        cluster = {"items": [
            {"title": "完全不相关的标题", "text": "也完全不相关的内容"},
        ]
        }
        result = B._filter_cluster_items(cluster, "Claude Design")
        self.assertGreaterEqual(len(result["items"]), 1, "至少保留 1 个")

    def test_filter_empty_label(self):
        cluster = {"items": [{"title": "x", "text": "y"}]}
        result = B._filter_cluster_items(cluster, "")
        self.assertEqual(len(result["items"]), 1, "空 label 不过滤")
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 `_filter_cluster_items`**（spec 中代码）

- [ ] **Step 4: 在 Phase 2 循环中调用**

L2874 前插入:
```python
c = _filter_cluster_items(c, c.get("label", ""))
```

- [ ] **Step 5: 运行测试 → Commit**

```bash
git add build_daily_insight.py tests/daily_insight/test_material_filter.py
git commit -m "fix(insight): Phase 2 前素材相关性过滤 — 防止内容串位"
```

---

### Task 5: FIX-6 — rss_history.json 分块存储

**Files:**
- Modify: `build_rss_aggregator.py` (新增 `_save_history_chunked` / `_load_history_chunked`)
- Modify: `.gitignore`
- Modify: `.github/workflows/update.yml`

- [ ] **Step 1: 实现分块函数**

在 `build_rss_aggregator.py` 中 `_save_history()` 后添加（spec 中代码）。

- [ ] **Step 2: 修改调用点**

`_save_history()` 内部改为调用 `_save_history_chunked()`。
加载处（L290-297）改为调用 `_load_history_chunked()`。

- [ ] **Step 3: 更新 .gitignore**

添加:
```
rss_history_*.json
rss_history_index.json
```

- [ ] **Step 4: 更新 Prune 步骤**

`.github/workflows/update.yml` Prune 步骤 添加:
```bash
rm -f rss_history_*.json rss_history_index.json
```

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/ -v`

- [ ] **Step 6: Commit**

```bash
git add build_rss_aggregator.py .gitignore .github/workflows/update.yml
git commit -m "fix(rss): rss_history.json 分块存储 — 避免单文件超 50MB"
```

---

### Task 6: FIX-7 — 端到端 LLM 追踪日志

**Files:**
- Modify: `build_daily_insight.py` (新增 `PipelineTracer` 类 + 主管线集成)
- Test: `tests/daily_insight/test_tracer.py`

- [ ] **Step 1: 写测试**

```python
# tests/daily_insight/test_tracer.py
# -*- coding: utf-8 -*-
"""FIX-7: PipelineTracer 追踪日志测试。"""
import os, sys, unittest, json, tempfile
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import build_daily_insight as B
B.NOW_BJ = B._now_bj()

class TestPipelineTracer(unittest.TestCase):
    def test_basic_lifecycle(self):
        tracer = B.PipelineTracer()
        tracer.set_meta(llm_available=True, embed_model="test", mode="incremental")
        tracer.trace_queries(100, 50, 20, 30, 200, 15, 80)
        tracer.trace_clustering("semantic", 0.75, 80, 10, [
            {"label": "test", "category": "ai", "score": 0.5,
             "resonance": "", "status": "new", "items": []}
        ])
        tracer.trace_llm_call("phase1", None, "prompt text", "agnes",
                              0.3, 3000, '{"theme":"ok"}', True,
                              {"theme": "ok"})
        tracer.trace_self_review(["事件1 含空话"], [0])
        tracer.trace_ragas([{"iter": 0, "overall": 0.75}])
        tracer.trace_bubble({"ai": 5}, [{"label": "x", "intersection": 0}], ["x"])
        tracer.trace_output(10, 3, 5000)
        entry = tracer.flush()
        self.assertIn("stages", entry)
        self.assertIn("llm_calls", entry)
        self.assertEqual(len(entry["llm_calls"]), 1)
        self.assertEqual(entry["stages"]["queries"]["chunks_total"], 200)

    def test_prompt_truncation(self):
        tracer = B.PipelineTracer()
        long_prompt = "x" * 10000
        tracer.trace_llm_call("phase2", 0, long_prompt, "agnes",
                              0.3, 3000, "ok", True, {})
        self.assertEqual(len(tracer.llm_calls[0]["prompt_preview"]), 5000)

    def test_no_sensitive_data(self):
        tracer = B.PipelineTracer()
        tracer.trace_llm_call("phase1", None, "no keys here", "agnes",
                              0.3, 3000, "ok", True, {})
        entry_json = json.dumps(tracer.llm_calls[0])
        self.assertNotIn("API_KEY", entry_json)
        self.assertNotIn("AGNES", entry_json)

    def test_exception_safe(self):
        """trace 方法不应抛出异常。"""
        tracer = B.PipelineTracer()
        tracer.trace_queries(None, None, None, None, None, None, None)
        tracer.trace_clustering(None, None, None, None, None)
        tracer.trace_output(None, None, None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_tracer.py -v`
Expected: FAIL — `PipelineTracer` 不存在

- [ ] **Step 3: 实现 `PipelineTracer` 类**

在 `build_daily_insight.py` 的 `_log_tracking_entry` 函数前添加（spec 中完整代码）。

所有 trace 方法用 try/except 包裹，异常时 print stderr 但不中断。

- [ ] **Step 4: 在主管线中集成 tracer**

在 `main()` 中：
- L2836 后创建 `tracer = PipelineTracer()`
- 检索后调用 `tracer.trace_queries(...)`
- 聚类后调用 `tracer.trace_clustering(...)`
- Phase 1 LLM 调用处添加 `tracer.trace_llm_call("phase1", ...)`
- Phase 2 循环中添加 `tracer.trace_llm_call("phase2", i, ...)`
- 自审后调用 `tracer.trace_self_review(...)`
- RAGAS 后调用 `tracer.trace_ragas(...)`
- 破茧栏后调用 `tracer.trace_bubble(...)`
- 输出后调用 `tracer.trace_output(...)`
- 最终 `tracer.flush()`

- [ ] **Step 5: 运行测试确认通过**

Run: `C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/test_tracer.py -v`
Expected: 4/4 PASS

- [ ] **Step 6: Commit**

```bash
git add build_daily_insight.py tests/daily_insight/test_tracer.py
git commit -m "feat(insight): 端到端 LLM 调用追踪日志 — PipelineTracer"
```

---

### Task 7: 全量验证 + 推送

- [ ] **Step 1: 运行全量测试**

```bash
C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest tests/daily_insight/ -v
C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest test_daily_insight.py -v
C:\Users\40832\AppData\Local\Programs\Python\Python311\python.exe -m pytest test_insight_engine.py -v
```

- [ ] **Step 2: 推送并触发 CI**

```bash
git push origin main
gh workflow run update.yml --ref main
```

- [ ] **Step 3: 观察下一次 CI 构建**

验证:
- `daily-insight.json` 中至少 3 个事件 `heat > 0`
- 至少 1 个事件 `resonance` 非空
- RAGAS eval 不再全 0.50
- 无重复事件
- 无 `rss_history.json` 超 50MB 警告
- `daily_insight_tracking_history.jsonl` 包含 `stages` + `llm_calls` 字段
