# 深度洞察漏斗化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"选什么内容"的决策从 RAG 相似度主干上摘下来，改为源先验 + 事件归一 + 多目标并列打分；先在破茧栏落地漏斗形状，再回主报告。

**Architecture:** 三段式漏斗——源级 `cat` 定候选池、分批近邻连通分量做事件归一、独立信源数/新鲜度/momentum/深度并列加权排序；相似度从"被乘数"降级为打分表里权重最小的一项。唯一新增持久件是跨场事件信号账本 `insight_event_signals.jsonl`。

**Tech Stack:** Python 3.11、numpy、faiss-cpu（可选）、rank-bm25（可选）、pytest；GitHub Actions 构建 + Vercel serverless 产物。

**Spec:** `docs/superpowers/specs/2026-09-20-daily-insight-funnel-redesign-design.md`（实施者必须先读，本计划每一步都引用其中的实测编号 F1–F8 / B1–B6）

## Global Constraints

- 禁 `git add -A` / `git add .`，只按具体路径 add；`update.yml`、`build_rss_aggregator.py`、`rss_fetch_state` 属禁改禁提清单。
- 禁 `git rebase`、禁 `git commit --amend`、禁 `2>&1` 重定向、多条命令用 `;` 不用 `&&`。
- commit 默认留本地；推送必须走 `py -3.11 tools/data_api_push.py`，且推送前须 `--check-only` 确认无未完成 run，且**逐次征得用户同意**。
- 本地 pytest 必须 `-s` 且用 `--junitxml` 读结果；CI 里 `tests/daily_insight/` 跑的是 `python -m pytest tests/daily_insight/ -q`（update.yml:108，无 `-s`）——本地绿不等于 CI 绿，收尾必做 CI 同构复跑（照抄门禁 B 清空六个 API key 的环境）。
- 门禁 B 是 `continue-on-error: true` → 只认日志 `[0-9]+ failed` / `[0-9]+ passed` 汇总行，不认步骤结论。
- 新测试目录/文件必须与 `update.yml` 同一次提交落远端（A2 blocking + Deploy 无 `if` 耦合）。
- 依赖时序或场次数量的测试不得裸进 blocking 门禁（挪 advisory 或加压力复跑）。
- `TOPIC_TAXONOMY` 顺序敏感，`ai` 必须排第一；`MIN_DEEP_SCORE=55` 与 40/30/20/10 权重属既有不变量。
- 证据包全文不得作为 citations `[n]` 编号来源。
- 时间比较一律走 `_parse_iso`（返回 aware），naive/aware 混比曾在 CI 实炸 `_score_events`。
- 消费新增字段一律 `(x.get(k) or "")`——旧向量缓存 chunk 没有新字段，且 LLM 会输出 `null`。
- 统计口径数据一律拉远端 `daily_insight_tracking_history.jsonl`，本地副本陈旧。
- 本机构建产物（`daily_insight_chunks.json` 等）不得提交；根目录 `_*.py`/`_*.txt` 属临时探查件，收尾清理。
- 删除任何机制必须按符号清单全仓断言清除（`py_compile` 查不出 NameError），并离线冒烟跑一次入口。

---

## Phase 0 — 测量前提（不改产报，只加读数）

破茧栏**不在 RAGAS 三维评估面内**（`_evaluate_report_quality` 签名无 `bubble_breaker`，且 `:5523` 晚于 ragas_eval），所以改造前必须先有能观测破茧的读数，否则改完无从判断。

### Task 1: 远端口径统计器

**Files:**
- Create: `tools/insight_metrics.py`
- Test: `tests/daily_insight/test_insight_metrics.py`

**Interfaces:**
- Consumes: 远端 `daily_insight_tracking_history.jsonl`（HTTP raw，不落盘到仓库）
- Produces: `parse_tracking(text: str) -> list[dict]`；`split_by_passed_fix(rows: list[dict]) -> tuple[list[dict], list[dict]]`；`dim_stats(rows: list[dict]) -> dict[str, dict]`（键为 `overall/context_coverage/faithfulness/relevance`，值含 `n/mean/sd/min/max/pass_rate`）；`three_dim_all_pass(rows: list[dict]) -> int`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 1: 统计口径必须拉远端并按 passed 修复时刻分段。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.insight_metrics import parse_tracking, dim_stats, split_by_passed_fix

FIX_ISO = "2026-09-19T20:00:00+08:00"  # R14-9C 起效时刻，实际值由 Step 3 从 git log 取

def _row(ts, cov, faith, rel, overall):
    return ('{"ts":"%s","meta":{"mode":"full"},"stages":{},'
            '"quality":{"context_coverage":%s,"faithfulness":%s,"relevance":%s,'
            '"overall":%s,"passed":true}}' % (ts, cov, faith, rel, overall))

def test_parse_skips_blank_and_broken():
    text = _row(FIX_ISO, 0.75, 0.9, 0.7, 0.78) + "\n\nnot-json\n"
    assert len(parse_tracking(text)) == 1

def test_split_by_fix_time():
    rows = parse_tracking(_row("2026-09-17T13:18:00+08:00", 1, 1, 1, 1) + "\n"
                          + _row(FIX_ISO, 1, 1, 1, 1))
    before, after = split_by_passed_fix(rows, FIX_ISO)
    assert [len(before), len(after)] == [1, 1]

def test_dim_stats_reports_n_and_pass_rate():
    rows = parse_tracking("\n".join([
        _row(FIX_ISO, 0.80, 0.90, 0.80, 0.80), _row(FIX_ISO, 0.60, 0.90, 0.60, 0.65)]))
    s = dim_stats(rows)["context_coverage"]
    assert s["n"] == 2 and s["pass_rate"] == 0.5 and abs(s["mean"] - 0.70) < 1e-6
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/daily_insight/test_insight_metrics.py -q -s --junitxml=_j1.xml`
Expected: `ModuleNotFoundError` 或 `ImportError: cannot import name 'parse_tracking'`

- [ ] **Step 3: 最小实现**

```python
# -*- coding: utf-8 -*-
"""只读统计器：拉远端 tracking，按 passed 修复时刻分段输出四维统计。"""
import json, math, statistics, sys, urllib.request

RAW = ("https://raw.githubusercontent.com/Kwei168/github-star-hub/main/"
       "daily_insight_tracking_history.jsonl")
THRESH = {"context_coverage": 0.75, "faithfulness": 0.88, "relevance": 0.75, "overall": 0.70}

def fetch(url=RAW):
    req = urllib.request.Request(url, headers={"User-Agent": "starhub-metrics"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")

def parse_tracking(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows

def _q(r):
    return (r.get("quality") or {})

def split_by_passed_fix(rows, fix_iso):
    return ([r for r in rows if str(r.get("ts", "")) < fix_iso],
            [r for r in rows if str(r.get("ts", "")) >= fix_iso])

def dim_stats(rows):
    out = {}
    for k, floor in THRESH.items():
        vs = [_q(r).get(k) for r in rows]
        vs = [float(v) for v in vs if isinstance(v, (int, float))]
        out[k] = {"n": len(vs), "mean": statistics.fmean(vs) if vs else 0.0,
                  "sd": statistics.pstdev(vs) if len(vs) > 1 else 0.0,
                  "min": min(vs) if vs else 0.0, "max": max(vs) if vs else 0.0,
                  "pass_rate": (sum(1 for v in vs if v >= floor) / len(vs)) if vs else 0.0}
    return out

def three_dim_all_pass(rows):
    return sum(1 for r in rows if all(
        float(_q(r).get(k, -1)) >= THRESH[k] for k in
        ("context_coverage", "faithfulness", "relevance")))
```

同文件加 `if __name__ == "__main__":` 分支：`fetch()` → 分段 → 打印每段 `n / 四维 mean / 三维同时达标期数`。**打印只用 ASCII 与中文，禁生僻符号**（Windows GBK 控制台 + 宽 except 会把 UnicodeEncodeError 吞成静默降级）。

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/daily_insight/test_insight_metrics.py -q -s --junitxml=_j1.xml`
Expected: `4 passed`

- [ ] **Step 5: 提交**

```bash
git add tools/insight_metrics.py tests/daily_insight/test_insight_metrics.py
git commit -m "feat(insight): 加只读远端统计器 insight_metrics，passed 修复前后分段统计（漏斗化 Task1）"
```

### Task 2: 本地/远端口径对账（不新增测试，产出是结论）

**Files:**
- Modify: `docs/superpowers/specs/2026-09-20-daily-insight-funnel-redesign-design.md`（§6 数字校准）

**Interfaces:**
- Consumes: Task 1 的 `fetch/parse_tracking/split_by_passed_fix/dim_stats`
- Produces: 修好后的基线数字，供 Phase 1/2 验收对照

- [ ] **Step 1: 跑一次全量统计**

Run: `py -3.11 tools/insight_metrics.py > _metrics_remote.txt`
Expected: 输出修复前/后两段的 `n` 与四维 mean

- [ ] **Step 2: 与 spec 引用的本地数字逐条对账**

核对 `_track_stats.txt` 里 43 行 / 三维同时达标 1/7 / 24-of-43 是否与远端一致。不一致则以远端为准，改写 spec §6 与 §1 表 F 中的相关行；一致则在 spec 里把"本地派生物待重测"改成"已与远端核对一致（日期、run id）"。

- [ ] **Step 3: 记录破茧基线（人工抽 30 条）**

```python
# 临时脚本 _bubble_baseline.py，跑完删除；输出写 UTF-8 文件而非 stdout
import json, io, random, collections
import build_daily_insight as bdi
cs = json.load(io.open("daily_insight_chunks.json", encoding="utf-8"))
MAIN = {"ai", "programming"}
pool = [c for c in cs if c.get("cat") == "news" and c.get("topic_tag") not in MAIN]
random.seed(11)
with io.open("_bubble_baseline.txt", "w", encoding="utf-8") as f:
    f.write("cat=news 且非科技 tag: %d\n" % len(pool))
    for c in random.sample(pool, min(30, len(pool))):
        f.write("- [%s] %s | %s\n" % (c.get("topic_tag"), (c.get("title") or "")[:60],
                                      c.get("source")))
```

Run: `py -3.11 _bubble_baseline.py`
Expected: 30 条样本落盘，逐条人工判"是否非科技"，得到**池纯度基线**（写进 spec §6）。

- [ ] **Step 4: 提交 spec 校准**

```bash
git add docs/superpowers/specs/2026-09-20-daily-insight-funnel-redesign-design.md
git commit -m "docs(specs): 漏斗化方案 §6 基线与远端 tracking 对账，补破茧池纯度基线（Task2）"
```

### Task 3: 破茧观测埋点（纯读数，不改产报）

**Files:**
- Modify: `build_daily_insight.py`（`_select_bubble_events` 返回处，`:3225-3288`）
- Test: `tests/daily_insight/test_bubble_observability.py`

**Interfaces:**
- Consumes: `_select_bubble_events` 现有入参
- Produces: 每个破茧卡片 dict 增加 `meta: {"hot_nonzero": bool, "src": str, "topic_tag": str}`；顶层 `bubble_stats: {"pool_size": int, "hot_nonzero_rate": float, "tag_dist": dict}` 写入 `daily-insight.json` 的 `bubble_breaker_stats`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 3: 破茧必须可观测——B2 实测 hot>0 为 0 条，没有读数就只能人工挖日志。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

def _c(title, tag, hot=0):
    return {"title": title, "text": "正文" * 30, "topic_tag": tag, "hot": hot,
            "pub_date": bdi.NOW_BJ.isoformat(), "url": "https://u/" + title,
            "source": "n", "source_key": "news_x", "cat": "news", "source_type": "rss"}

def test_cards_carry_meta_and_stats():
    out, stats = bdi._select_bubble_events(
        [], {}, all_chunks=[_c("央行降准", "finance"), _c("大选开票", "geopolitics")],
        top_n=5, with_stats=True)
    assert all("meta" in c for c in out)
    assert stats["pool_size"] == 2 and stats["hot_nonzero_rate"] == 0.0

def test_backward_compatible_without_flag():
    out = bdi._select_bubble_events([], {}, all_chunks=[_c("央行降准", "finance")], top_n=5)
    assert isinstance(out, list) and "meta" not in out[0]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/daily_insight/test_bubble_observability.py -q -s --junitxml=_j3.xml`
Expected: `ValueError: not enough values to unpack`（函数仍返回 list）

- [ ] **Step 3: 实现**

在 `_select_bubble_events` 签名加 `with_stats=False`；三条路径的每个 result 项统一加 `"meta": {"hot_nonzero": bool(float(ch.get("hot",0) or 0) > 0), "src": ch.get("source_key",""), "topic_tag": ch.get("topic_tag","")}`；末尾：

```python
    stats = {"pool_size": len(pool),
             "hot_nonzero_rate": round(sum(1 for c in pool if float(c.get("hot", 0) or 0) > 0)
                                       / max(1, len(pool)), 4),
             "tag_dist": {}}
    for c in result:
        k = c["meta"]["topic_tag"]
        stats["tag_dist"][k] = stats["tag_dist"].get(k, 0) + 1
    return (result, stats) if with_stats else result
```

调用点 `:5523` 改 `bubble_breaker, _bstats = _select_bubble_events(..., with_stats=True)`，`_write_insight_json` 加形参 `bubble_stats=None` 并写 `"bubble_breaker_stats": bubble_stats or {}`。

- [ ] **Step 4: 跑全套确认无回归**

Run: `py -3.11 -m pytest tests/daily_insight/ -q -s --junitxml=_j3b.xml`
Expected: 全绿（既有 `test_bubble_v2.py` 未传 `with_stats`，靠默认值保兼容）

- [ ] **Step 5: 变异体验证测试真能红**

把 `hot_nonzero_rate` 的分子改成 `len(pool)`，重跑 Step 1 的 `test_cards_carry_meta_and_stats` 必须 FAIL，然后还原。Expected: FAIL → 还原后 PASS

- [ ] **Step 6: 提交**

```bash
git add build_daily_insight.py tests/daily_insight/test_bubble_observability.py
git commit -m "feat(insight): 破茧栏加只读埋点 pool_size/hot_nonzero_rate/tag_dist（漏斗化 Task3）"
```

### Task 4: CI 向量缓存维度假设的埋点验证

**Why:** 本地 `daily_insight_chunks.json` 是 `bge-small-zh-v1.5` / 512 维，而 `EMBED_MODEL=bge-m3`、`EMBED_DIM=1024`；`:864` 会因维度不符**整库清空重嵌**。CI 恢复了这三个文件（update.yml:125-127），所以生产每场是否整库重嵌**未证实**，不下结论——用读数判定。

**Files:**
- Modify: `build_daily_insight.py`（`_load_vector_cache` `:838-881`、tracking entry）
- Test: `tests/daily_insight/test_vector_cache_probe.py`

**Interfaces:**
- Produces: `_load_vector_cache()` 额外把 `{"kept": bool, "cached_dim": int, "cached_model": str, "expected_dim": int}` 写入模块级 `_VECTOR_CACHE_PROBE`，由 `_build_tracking_entry` 落到 `meta.vector_cache`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def test_probe_records_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    json.dump([{"chunk_id": "c0", "embed_model": "BAAI/bge-small-zh-v1.5"}],
              open(bdi.FAISS_META_FILE, "w", encoding="utf-8"))
    import numpy as np
    np.save(bdi.VECTOR_CACHE_FILE, np.zeros((1, 512), dtype="float32"))
    assert bdi._load_vector_cache()[:2] == ([], None)
    assert bdi._VECTOR_CACHE_PROBE["kept"] is False
    assert bdi._VECTOR_CACHE_PROBE["cached_dim"] == 512
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_vector_cache_probe.py -q -s --junitxml=_j4.xml` → Expected FAIL（`AttributeError: _VECTOR_CACHE_PROBE`）

- [ ] **Step 3:** 在 `_load_vector_cache` 顶部 `_VECTOR_CACHE_PROBE.update({"kept": False, "cached_dim": 0, "cached_model": "", "expected_dim": EMBED_DIM})`，三个 return 点前分别记录：维度不符记 `cached_dim=vectors.shape[1]`；成功加载记 `kept=True`。模块级 `_VECTOR_CACHE_PROBE = {}`，`_build_tracking_entry` 的 `meta` 里加 `"vector_cache": dict(_VECTOR_CACHE_PROBE)`。

- [ ] **Step 4:** 重跑 → Expected PASS；再 `py -3.11 -m pytest tests/daily_insight/ -q -s --junitxml=_j4b.xml` 全绿

- [ ] **Step 5:** `git add build_daily_insight.py tests/daily_insight/test_vector_cache_probe.py ; git commit -m "feat(insight): 向量缓存维度/模型落 tracking meta，判定 CI 是否每场整库重嵌（漏斗化 Task4）"`

---

## Phase 1 — 破茧排除式漏斗（B 线）

对应 spec §4.2 五段。刻意收窄：v1 基础池**只用 `cat == "news"`**，`wechat/twitter/podcast` 8581 条不进（漏标率无法实测）。

### Task 5: 源级 `cat` 接线

**Files:**
- Modify: `build_daily_insight.py:306-316`（`_load_rss_tiers`）
- Test: `tests/daily_insight/test_source_cat_map.py`

**Interfaces:**
- Produces: 模块级 `_RSS_CAT_MAP: dict[str, str]`（`source_key -> cat`），与 `_RSS_TIER_MAP` 同生命周期；`_source_cat(source_key) -> str`（缺失返回 `""`）

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""B1：_load_rss_tiers 现在只读 key/tier，把人工维护的 cat 丢了。"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def test_load_keeps_cat(tmp_path, monkeypatch):
    src = [{"key": "bbc_top_stories_592", "cat": "news", "tier": 1},
           {"key": "hn_ai_7", "cat": "ai", "tier": 2}]
    p = tmp_path / "rss_sources.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    bdi._RSS_CAT_MAP.clear()
    bdi._load_rss_tiers()
    assert bdi._RSS_CAT_MAP == {"bbc_top_stories_592": "news", "hn_ai_7": "ai"}
    assert bdi._source_cat("bbc_top_stories_592") == "news"
    assert bdi._source_cat("missing_key") == ""
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_source_cat_map.py -q -s --junitxml=_j5.xml` → Expected FAIL

- [ ] **Step 3:** 加 `_RSS_CAT_MAP = {}` 与：

```python
        for s in sources:
            if isinstance(s, dict) and s.get("key"):
                _RSS_TIER_MAP[s["key"]] = s.get("tier", 3)
                _RSS_CAT_MAP[s["key"]] = s.get("cat", "")

def _source_cat(source_key):
    """源级领域先验（rss_sources.json 人工维护，实测 603 源 cat 零多值）。"""
    return _RSS_CAT_MAP.get(source_key or "", "")
```

- [ ] **Step 4:** 重跑 → PASS；全套 → 全绿
- [ ] **Step 5:** `git add build_daily_insight.py tests/daily_insight/test_source_cat_map.py ; git commit -m "feat(insight): _load_rss_tiers 保留源级 cat，暴露 _source_cat（漏斗化 Task5）"`

### Task 6: 排除式召回池

**Files:**
- Modify: `build_daily_insight.py`（新函数，紧邻 `_select_bubble_events`）
- Test: `tests/daily_insight/test_bubble_pool_exclusion.py`

**Interfaces:**
- Consumes: `_source_cat`（Task 5）、`_parse_iso`、`_hours_ago`、`INSIGHT_RSS_HOURS`
- Produces: `_bubble_candidate_pool(chunks, main_keys, cat_allow=("news",), veto_tags=("ai","programming")) -> list[dict]`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""spec §3：词表当准入丢 70%，改当否决。v1 基础池只用 cat=news。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

def _c(key, tag, title="t", hours=1):
    return {"title": title, "text": "正文" * 30, "topic_tag": tag, "source_key": key,
            "url": "https://u/" + key + title, "source": "n", "source_type": "rss",
            "pub_date": (bdi.NOW_BJ - datetime.timedelta(hours=hours)).isoformat()}

def test_news_source_with_other_tag_enters(tmp_path, monkeypatch):
    monkeypatch.setattr(bdi, "_RSS_CAT_MAP", {"bbc_1": "news", "hn_1": "ai", "wx_1": "wechat"})
    pool = bdi._bubble_candidate_pool(
        [_c("bbc_1", "other", "瑞典大选开票"), _c("hn_1", "other", "某开源库"),
         _c("wx_1", "finance", "央行降准")], set())
    assert [p["title"] for p in pool] == ["瑞典大选开票"]   # 词表漏判 other 的新闻源进得来；非 news 源进不来

def test_veto_tag_kicks_tech_from_news_source(monkeypatch):
    monkeypatch.setattr(bdi, "_RSS_CAT_MAP", {"bbc_1": "news"})
    assert bdi._bubble_candidate_pool([_c("bbc_1", "ai", "新模型发布")], set()) == []

def test_stale_and_main_events_excluded(monkeypatch):
    monkeypatch.setattr(bdi, "_RSS_CAT_MAP", {"bbc_1": "news"})
    old = _c("bbc_1", "geopolitics", "旧闻", hours=bdi.INSIGHT_RSS_HOURS + 10)
    dup = _c("bbc_1", "society", "已在主报告")
    pool = bdi._bubble_candidate_pool([old, dup], {dup["url"]})
    assert [p["title"] for p in pool] == []
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_bubble_pool_exclusion.py -q -s --junitxml=_j6.xml` → Expected FAIL（未定义）

- [ ] **Step 3:**

```python
def _bubble_candidate_pool(chunks, main_keys, cat_allow=("news",),
                           veto_tags=("ai", "programming")):
    """破茧基础候选池：源先验定准入，词表只做否决（spec §3）。

    源先验用 rss_sources.json 的 cat（人工维护、跨场稳定），不用 chunk 自带字段——
    旧向量缓存 chunk 可能没有 cat。v1 收窄到 news 一类，wechat/twitter/podcast 待
    纯度实测后再扩（spec §4.2）。
    """
    out = []
    for ch in chunks or []:
        if _source_cat(ch.get("source_key", "")) not in cat_allow:
            continue
        if (ch.get("topic_tag") or "") in veto_tags:
            continue
        pub = _parse_iso(ch.get("pub_date", ""))
        if pub and _hours_ago(pub) > INSIGHT_RSS_HOURS:
            continue
        if (ch.get("url", "") or ch.get("link", "")) in main_keys:
            continue
        if (ch.get("title", "") or "").strip() in main_keys:
            continue
        out.append(ch)
    return out
```

- [ ] **Step 4:** 重跑 → PASS；全套 → 全绿
- [ ] **Step 5: 变异体**：把 `cat_allow` 判断改成 `ch.get("topic_tag") in cat_allow`（退回准入式），`test_news_source_with_other_tag_enters` 必须 FAIL。还原。
- [ ] **Step 6:** `git add build_daily_insight.py tests/daily_insight/test_bubble_pool_exclusion.py ; git commit -m "feat(insight): 破茧候选池改排除式（源先验准入+词表否决），v1 仅 cat=news（漏斗化 Task6）"`

### Task 7: 池内事件归一（分批近邻连通分量）

**Files:**
- Modify: `build_daily_insight.py`（新函数）
- Test: `tests/daily_insight/test_bubble_clustering.py`

**Interfaces:**
- Consumes: `_embed_chunks`、`_dedup_tokens`、`_jaccard`
- Produces: `_cluster_pool(pool, sim_threshold=0.80, batch=512) -> list[list[dict]]`（每组至少 1 条，按组内条数降序）；对 embed 失败降级为 `_same_topic` 标题贪心

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""B6 + spec §4.2②：破茧现在只有标题级贪心，主报告有 _semantic_merge 而它没有。
   万级不能直接跑 _semantic_merge（贪心 O(n²)，float32 Gram ≈ 444MB）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
import numpy as np

def _stub_embed(monkeypatch, vecs):
    monkeypatch.setattr(bdi, "_embed_chunks", lambda texts: (vecs, None))

def test_merges_same_event_across_sources(monkeypatch):
    # 两条归一化向量点积 = 1.0 → 同事件（15 家转同一稿）
    _stub_embed(monkeypatch, np.array([[1.0, 0.0], [1.0, 0.0]], dtype="float32"))
    g = bdi._cluster_pool([{"title": "A", "source_key": "s1"},
                           {"title": "B", "source_key": "s2"}])
    assert len(g) == 1 and len(g[0]) == 2

def test_keeps_distinct_events(monkeypatch):
    _stub_embed(monkeypatch, np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32"))
    assert len(bdi._cluster_pool([{"title": "A", "source_key": "s1"},
                                  {"title": "B", "source_key": "s2"}])) == 2

def test_degrades_to_title_tokens_when_embed_unavailable(monkeypatch):
    monkeypatch.setattr(bdi, "_embed_chunks", lambda texts: (None, None))
    g = bdi._cluster_pool([{"title": "央行宣布降准落地", "source_key": "s1"},
                           {"title": "央行宣布降准落地 释放流动性", "source_key": "s2"}])
    assert len(g) == 1

def test_singleton_for_empty_title(monkeypatch):
    _stub_embed(monkeypatch, np.array([[1.0, 0.0]], dtype="float32"))
    assert len(bdi._cluster_pool([{"title": "", "source_key": "s1"}])) == 1

def test_numpy_absent_degrades_not_crashes(monkeypatch):
    """numpy 是可选依赖（:28/:33 try-import）；CI 少装时 _np is None，必须降级。"""
    monkeypatch.setattr(bdi, "_np", None)
    g = bdi._cluster_pool([{"title": "央行宣布降准落地", "source_key": "s1"},
                           {"title": "央行宣布降准落地 释放流动性", "source_key": "s2"}])
    assert len(g) == 1
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_bubble_clustering.py -q -s --junitxml=_j7.xml` → Expected FAIL

- [ ] **Step 3:**

```python
def _cluster_pool(pool, sim_threshold=0.80, batch=512):
    """池内归一：分批算相似度 + 并查集，避免万级 Gram 爆内存（spec §4.2②）。"""
    items = [c for c in (pool or []) if (c.get("title") or "").strip()]
    n = len(items)
    if n == 0:
        return []
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    vecs = None
    try:
        v = _embed_chunks([(c.get("title") or "")[:500] for c in items])
        vecs = v[0] if isinstance(v, tuple) else v
    except Exception:
        vecs = None
    # 注意：本模块内 numpy 的既有别名是 `_np`（:28/:33），不是 `np`；且 numpy 是可选依赖，
    # 导入失败时 `_np is None`（CI 的 pip 步骤若未装 faiss/numpy 就是这条路），必须降级而非 NameError。
    if _np is not None and vecs is not None and len(vecs) == n:
        mat = _np.array(vecs, dtype="float32")
        norms = _np.linalg.norm(mat, axis=1, keepdims=True)
        norms = _np.where(norms == 0, 1, norms)
        mat = mat / norms
        for i in range(n):
            sims = mat[i + 1:] @ mat[i] if i + 1 < n else _np.array([], dtype="float32")
            for off in range(0, len(sims), batch):
                for j in _np.where(sims[off:off + batch] >= sim_threshold)[0]:
                    union(i, i + 1 + int(off) + int(j))
    else:
        for i in range(n):
            for j in range(i + 1, n):
                if _same_topic_titles(items[i].get("title", ""), items[j].get("title", "")):
                    union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return sorted(groups.values(), key=lambda g: len(g), reverse=True)
```

把 `_select_bubble_events` 内联的 `_same_topic` 提为模块级 `_same_topic_titles(a, b)`（保留原阈值 0.35/0.6 与注释），原处改调用它。

- [ ] **Step 4:** 重跑 → PASS；全套 → 全绿
- [ ] **Step 5: 规模冒烟（不进门禁，本地一次性）**

```bash
py -3.11 -c "
import time,json,numpy as np,build_daily_insight as b
cs=json.load(open('daily_insight_chunks.json',encoding='utf-8'))
pool=[c for c in cs if c.get('cat')=='news' and c.get('topic_tag') not in ('ai','programming')]
pool=pool[:1500]
b._embed_chunks=lambda ts:(np.random.RandomState(0).rand(len(ts),64).astype('float32'),None)
t=time.time(); g=b._cluster_pool(pool); print('n=%d groups=%d secs=%.1f'%(len(pool),len(g),time.time()-t))"
```
Expected: 1500 条在 30s 内跑完，`groups < n`（证明合并真的发生）。若超时则把 `batch` 降到 256 并记录，不得靠提高 `sim_threshold` 蒙混。

- [ ] **Step 6:** `git add build_daily_insight.py tests/daily_insight/test_bubble_clustering.py ; git commit -m "feat(insight): 破茧池内分批并查集归一，embed 失败降级标题贪心（漏斗化 Task7）"`

### Task 8: 簇级排序（删恒零 hot，补回丢失的跨源因子）

**Files:**
- Modify: `build_daily_insight.py`（新函数 + `_select_bubble_events` 路径 1）
- Test: `tests/daily_insight/test_bubble_cluster_score.py`

**Interfaces:**
- Consumes: `_RSS_TIER_MAP`、`_hours_ago`、`_parse_iso`
- Produces: `_bubble_cluster_score(group) -> dict`，键 `{"total","n_src","tier_w","freshness","news_domain"}`，`total ∈ [0,1]`；模块级 `_NEWS_DOMAIN_HINTS` 元组与 `BUBBLE_WEIGHTS` 字典。**只定义新闻域名表**：实测域名认不出科技（判科技的 16403 条仅 13.7% 带科技域名），所以不设 `_TECH_DOMAIN_HINTS`，避免留一个无人消费的常量。

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""B2/B3：hot>0 实测 0 条 → hot×0.5 恒零；9-18 的第三因子"跨平台次数"整项缺失。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

def _g(keys, hours=1, host="reuters.com"):
    return [{"source_key": k, "hot": 0,
             "url": "https://%s/%s" % (host, k), "text": "",
             "pub_date": (bdi.NOW_BJ - datetime.timedelta(hours=hours)).isoformat()}
            for k in keys]

def test_hot_alone_no_longer_dominates():
    """全零 hot 的簇仍应可排序，且独立信源数单调生效（B2 的回归位）。"""
    a = bdi._bubble_cluster_score(_g(["s1", "s2", "s3"]))
    b = bdi._bubble_cluster_score(_g(["s1"]))
    assert a["n_src"] == 3 and b["n_src"] == 1 and a["total"] > b["total"]

def test_duplicate_source_counts_once():
    """同一 source_key 转 5 次不等于 5 家独立信源（F4 的破茧版）。"""
    assert bdi._bubble_cluster_score(_g(["s1"] * 5))["n_src"] == 1

def test_fresher_scores_higher_at_equal_breadth():
    assert (bdi._bubble_cluster_score(_g(["s1"], hours=1))["total"]
            > bdi._bubble_cluster_score(_g(["s1"], hours=120))["total"])

def test_news_domain_confirmations_are_not_symmetric():
    """实测：域名只能确认新闻性(51.8%)，认不出科技(13.7%) → 只加确认分。"""
    assert bdi._bubble_cluster_score(_g(["s1"], host="reuters.com"))["news_domain"] \
        > bdi._bubble_cluster_score(_g(["s1"], host="arxiv.org"))["news_domain"]
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_bubble_cluster_score.py -q -s --junitxml=_j8.xml` → Expected FAIL

- [ ] **Step 3:**

```python
_NEWS_DOMAIN_HINTS = ("reuters", "bbc.", "bn.pt", "lemonde", "france24", "aljazeera",
                      "apnews", "theguardian", "nytimes", "wsj.", "ft.com", "bloomberg",
                      "spiegel", "xinhua", "people.com.cn", "thepaper", "cnn.com", "chinanews")
BUBBLE_WEIGHTS = {"n_src": 0.40, "tier_w": 0.20, "freshness": 0.30, "news_domain": 0.10}

def _bubble_cluster_score(group):
    """破茧簇分：独立信源数为主（hot 实测恒零，已从公式删除）。半衰期沿用 72h。"""
    keys = {c.get("source_key", "") or c.get("source", "") for c in group} - {""}
    n_src = len(keys) or 1
    tiers = [_RSS_TIER_MAP.get(k, 3) for k in keys]
    tier_w = sum({1: 1.5, 2: 1.0, 3: 0.5}.get(x, 0.5) for x in tiers) / (n_src * 1.5)
    ages = []
    for c in group:
        p = _parse_iso(c.get("pub_date", ""))
        ages.append(_hours_ago(p) if p else INSIGHT_RSS_HOURS)
    freshness = 0.5 ** (min(ages) / 72.0)
    doms = " ".join(((c.get("url") or "") + " " + (c.get("text") or "")[:800]) for c in group).lower()
    news_domain = 1.0 if any(d in doms for d in _NEWS_DOMAIN_HINTS) else 0.0
    total = (min(1.0, math.log2(n_src + 1) / math.log2(9)) * BUBBLE_WEIGHTS["n_src"]
             + min(1.0, tier_w) * BUBBLE_WEIGHTS["tier_w"]
             + freshness * BUBBLE_WEIGHTS["freshness"]
             + news_domain * BUBBLE_WEIGHTS["news_domain"])
    return {"total": round(total, 4), "n_src": n_src, "tier_w": round(min(1.0, tier_w), 4),
            "freshness": round(freshness, 4), "news_domain": news_domain}
```

`_select_bubble_events` 路径 1 改为：`pool = _bubble_candidate_pool(all_chunks or [], main_keys)` → `groups = _cluster_pool(pool)` → 每组算分并按 `total` 降序 → 取 Top N。`"score"` 字段填 `total`，并保留 `"hot_nonzero_rate"` 统计（Task 3）。

- [ ] **Step 4:** 全套 → 全绿（`test_bubble_v2.py::test_heat_ordering` 若因删 hot 失效，按 spec B2 判定该测试断言的是恒零字段排序，**改为断言 n_src 生效**并在测试文件头注明依据；不得为过测试把 hot 加回来）
- [ ] **Step 5:** `git add ... ; git commit -m "feat(insight): 破茧排序换成独立信源数/tier/新鲜度/新闻域名，删除恒零 hot 项（漏斗化 Task8）"`

### Task 9: 跨簇 Top5 + LLM 综合 + read_profile 退役

**Files:**
- Modify: `build_daily_insight.py`（`_select_bubble_events`、`_build_read_profile:3213`、调用点 `:5522-5523`、HTML `:4716`）
- Test: `tests/daily_insight/test_bubble_synthesis_and_retire.py`

**Interfaces:**
- Produces: `_select_bubble_events(clusters, residual_chunks=None, all_chunks=None, top_n=5, llm=None, with_stats=False)`——**签名去掉 `read_profile`**；卡片新增 `"reason"` 取客观形态文案

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""B4/B5：read_profile 统计的是本站近 7 天发过的 category，无用户行为数据，
   却在文案里说"与你常读的不同"；summary 是 text[:200] 截断，LLM 不参与。"""
import sys, os, datetime, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

def _c(key, tag, title):
    return {"title": title, "text": "正文" * 40, "topic_tag": tag, "source_key": key,
            "url": "https://reuters.com/" + key + title, "source": "n",
            "source_type": "rss", "cat": "news", "hot": 0,
            "pub_date": bdi.NOW_BJ.isoformat()}

class _LLM:
    def chat(self, *a, **k):
        return '{"summary": "综合后的破茧摘要"}'

def test_reason_is_objective_not_personalized():
    out = bdi._select_bubble_events([], all_chunks=[_c("s1", "geopolitics", "瑞典大选")],
                                    top_n=5)
    assert "你常读" not in out[0]["reason"] and "1 家独立信源" in out[0]["reason"]

def test_llm_summary_used_when_available():
    out = bdi._select_bubble_events([], all_chunks=[_c("s1", "geopolitics", "瑞典大选")],
                                    top_n=5, llm=_LLM())
    assert out[0]["summary"] == "综合后的破茧摘要"

def test_degrades_to_truncation_without_llm():
    out = bdi._select_bubble_events([], all_chunks=[_c("s1", "geopolitics", "瑞典大选")],
                                    top_n=5, llm=None)
    assert len(out[0]["summary"]) <= 200

def test_read_profile_symbol_fully_removed():
    """删机制要按符号清单全仓断言清除：py_compile 查不出 NameError。"""
    r = subprocess.run(["git", "grep", "-n", "read_profile", "--", "*.py"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "", r.stdout
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_bubble_synthesis_and_retire.py -q -s --junitxml=_j9.xml` → Expected FAIL（签名仍带 `read_profile`）

- [ ] **Step 3:**
1. `_select_bubble_events` 去 `read_profile` 形参与 `read_top` 变量；`reason` 改成 `"%d 家独立信源 · 簇内 %d 条佐证" % (n_src, len(group))`。
   **注意跨期依赖**：账本要 Task 11 才存在，而 Phase 1 在其之前——所以此处刻意只用当场可算的两个量，不引用 momentum/"近期第 N 起同类"。Task 15 落地账本后，若要升级为趋势文案，改在 Task 15 的收尾里做，不要在 Task 9 里预埋一个读不到的键。
2. 卡片 summary：`llm` 非空时对每组调一次（`json` 输出，失败 `try` 兜底回退 `text[:200]`）。
3. 删 `_build_read_profile`（`:3213-3222`）与 `:5522` 赋值；`trace_bubble`（`:4962`）形参同步去掉。
4. 全仓 `git grep -n read_profile -- "*.py"` 必须零命中，再 `py -3.11 -c "import build_daily_insight"` 冒烟。

- [ ] **Step 4:** 全套 → 全绿；`test_bubble_v2.py` 里所有 `_select_bubble_events(self.clusters, self.profile, ...)` 调用点去掉第二个实参
- [ ] **Step 5:** `git add build_daily_insight.py tests/daily_insight/*.py ; git commit -m "refactor(insight)!: 破茧去 read_profile（无用户行为数据支撑），跨簇 Top5 + LLM 综合摘要，文案改客观形态（漏斗化 Task9）"`

### Task 10: 破茧收尾——离线复跑 + 纯度复核

**Files:**
- Modify: `docs/superpowers/specs/2026-09-20-daily-insight-funnel-redesign-design.md`（§6 结果段）

- [ ] **Step 1:** 本地整脚本冒烟（用真实 chunk 语料，不提交产物）：`py -3.11 build_daily_insight.py --dry-run 2>_smoke.err; tail -5 _smoke.err`；Expected: 无 traceback，破茧卡片数 > 0
- [ ] **Step 2:** 重跑 Task 2 Step 3 抽样脚本，改用 `_bubble_candidate_pool` 的真实输出，人工判 30 条 → 得**改造后池纯度**，与 Task 2 基线并写入 spec §6。Expected: 纯度不低于基线，且池规模 ≥ 4000（spec §3 的 `cat=news` 4075）
- [ ] **Step 3:** `bubble_stats` 三项读数落盘核对：`pool_size`、`hot_nonzero_rate`（应仍有读数，证明字段确实恒零而非代码 bug）、`tag_dist`
- [ ] **Step 4:** CI 同构复跑门禁 B 环境（清空六个 key）：`py -3.11 -m pytest tests/daily_insight/ -q -s --junitxml=_j10.xml`，读 `_j10.xml` 汇总行；Expected: `0 failed`
- [ ] **Step 5:** 清理临时件（`_bubble_baseline.py`、`_probe*.txt`、`_field_probe.txt`、`_j*.xml`、`_smoke.err`），提交 spec 结果段

---

## Phase 2 — 主报告排序目标并列化（P 线）

对应 spec §4.1。默认权重即刻可用，收尾由 Task 15 的事后标注校准；**源先验直供通道排在 Task 16**，依赖 Phase 1 的纯度结论。

### Task 11: 跨场事件信号账本

**Files:**
- Modify: `build_daily_insight.py`（`:57` 附近常量、`main()` 收尾）
- Test: `tests/daily_insight/test_event_signals_ledger.py`

**Interfaces:**
- Produces: `EVENT_SIGNALS_FILE = "insight_event_signals.jsonl"`；`_append_event_signals(clusters) -> int`；`_load_event_signals(window_builds=24) -> dict[str, list[dict]]`；`_event_sig(title) -> str`（复用 `_dedup_tokens` 排序拼接，不引入新指纹）

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F8：momentum 算不出来——history 只 4 天/日粒度，sources 存类型不存信源。"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def _cl(title, keys):
    return {"label": title, "items": [{"source_key": k, "url": "https://u/" + k} for k in keys]}

def test_sig_stable_across_word_order_and_case():
    assert bdi._event_sig("OpenAI Releases Model") == bdi._event_sig("model releases openai")

def test_append_then_load_window(tmp_path, monkeypatch):
    """ts 必须显式传入：靠 _now_bj() 连写三次会因微秒相同而塌成一场，
    那就是"依赖时序的测试"，门禁 B 红一次会连坐部署。"""
    import datetime
    monkeypatch.setattr(bdi, "EVENT_SIGNALS_FILE", str(tmp_path / "sig.jsonl"))
    base = datetime.datetime(2026, 9, 20, 8, 0, tzinfo=datetime.timezone.utc)
    for i in range(3):
        ts = base + datetime.timedelta(hours=i)
        assert bdi._append_event_signals([_cl("央行降准", ["s1", "s2"])], now_bj=ts) == 1
    led = bdi._load_event_signals(window_builds=2)
    assert len(led[bdi._event_sig("央行降准")]) == 2      # 只回最近 2 场
    assert led[bdi._event_sig("央行降准")][0]["n_src"] == 2

def test_missing_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(bdi, "EVENT_SIGNALS_FILE", str(tmp_path / "nope.jsonl"))
    assert bdi._load_event_signals() == {}
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_event_signals_ledger.py -q -s --junitxml=_j11.xml` → Expected FAIL

- [ ] **Step 3:**

```python
def _event_sig(title):
    """跨场事件指纹：复用 _dedup_tokens，不新造指纹算法（spec §4.1）。"""
    return "|".join(sorted(_dedup_tokens((title or "").lower())))

def _append_event_signals(clusters, now_bj=None):
    """每场追加一行信号账本（只追加不覆盖），供 momentum 与事后趋势标注用。"""
    recs = []
    for c in clusters or []:
        keys = sorted({(it.get("source_key") or it.get("source") or "")
                       for it in c.get("items", [])} - {""})
        recs.append({"ts": (now_bj or _now_bj()).isoformat(),
                     "sig": _event_sig(c.get("label", "")),
                     "n_src": len(keys), "src_keys": keys})
    try:
        with open(EVENT_SIGNALS_FILE, "a", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as exc:
        print("[每日洞察] 信号账本写入失败（不阻断产报）: %s" % exc, file=sys.stderr)
    return len(recs)

def _load_event_signals(window_builds=24):
    """按"场次"而非小时取窗口：实测约 47 场/天且频率会变（spec §4.1）。"""
    out = {}
    try:
        rows = [json.loads(l) for l in open(EVENT_SIGNALS_FILE, encoding="utf-8") if l.strip()]
    except (OSError, ValueError):
        return {}
    ts_list = sorted({r.get("ts", "") for r in rows})
    keep = set(ts_list[-max(1, window_builds):])
    for r in rows:
        if r.get("ts") in keep and r.get("sig"):
            out.setdefault(r["sig"], []).append(r)
    return out
```

调用点放在 `main()` 写盘之后、`return` 之前。账本文件加入 `.gitignore` 需用户确认（spec §8 第 3 条待拍板），**本步不擅自忽略**。

- [ ] **Step 4:** 全套 → 全绿；**加 advisory 标注**：该测试依赖"场次"数量，不得进 blocking 门禁 → 文件头注明 `# advisory: 不依赖 CI 时序`，并确认它落在 `tests/daily_insight/`（门禁 B 是 continue-on-error，红不挡部署，仍需在计划勾记）
- [ ] **Step 5:** `git add build_daily_insight.py tests/daily_insight/test_event_signals_ledger.py ; git commit -m "feat(insight): 新增跨场事件信号账本 insight_event_signals.jsonl 与按场次读取（漏斗化 Task11）"`

### Task 12: momentum 计算

**Files:**
- Modify: `build_daily_insight.py`
- Test: `tests/daily_insight/test_momentum.py`

**Interfaces:**
- Consumes: `_load_event_signals`（Task 11）
- Produces: `_compute_momentum(sig, ledger) -> float ∈ [0,1]`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F6：accel 要求簇内带日期 chunk>2，从 0 爆发的新事件恰好拿不到加成。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def _led(hits):
    return {"S": [{"ts": "2026-09-20T%02d:00:00+08:00" % i} for i in range(hits)]}

def test_more_recent_appearances_score_higher():
    assert bdi._compute_momentum("S", _led(5)) > bdi._compute_momentum("S", _led(2))

def test_unknown_sig_is_zero_not_crash():
    assert bdi._compute_momentum("nope", _led(3)) == 0.0

def test_newcomer_gets_credit_without_cluster_history():
    """首次出现即有 n_src=1 也应非零——这是 accel 做不到的那类（F6）。"""
    assert bdi._compute_momentum("S", _led(1)) > 0.0
```

- [ ] **Step 2:** → Expected FAIL

- [ ] **Step 3:**

```python
def _compute_momentum(sig, ledger):
    """近 window 场次的出现次数 → [0,1]。log2 压顶，避免常青条目垄断。"""
    hits = len(ledger.get(sig or "", []))
    if hits <= 0:
        return 0.0
    return round(min(1.0, math.log2(hits + 1) / math.log2(MOMENTUM_CAP + 1)), 4)
```

常量 `MOMENTUM_CAP = 8`（≈ 半天窗口内出现 7 场封顶）。

- [ ] **Step 4:** 全套 → 全绿；**变异体**：`hits <= 0` 改 `return 1.0`，`test_unknown_sig_is_zero_not_crash` 必红，还原
- [ ] **Step 5:** `git add ... ; git commit -m "feat(insight): _compute_momentum 按账本场次计数，log2 压顶（漏斗化 Task12）"`

### Task 13: 独立信源数替换 `len(source_types)`

**Files:**
- Modify: `build_daily_insight.py:1343`（`_score_events`）
- Test: `tests/daily_insight/test_independent_sources.py`

**Interfaces:**
- Produces: `_event_independent_sources(cluster) -> int`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F4：共振数的是 source_type（只有 4 类），15 家转同一事件只 +1 → 共模拿不到加分。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def test_counts_source_keys_not_types():
    c = {"items": [{"source_key": "s%d" % i, "source_type": "rss"} for i in range(15)]}
    assert bdi._event_independent_sources(c) == 15
    assert len({i["source_type"] for i in c["items"]}) == 1   # 旧口径会是 1

def test_missing_keys_fall_back_to_source_then_zero():
    assert bdi._event_independent_sources({"items": [{"source": "bbc"}, {"source": "bbc"}]}) == 1
    assert bdi._event_independent_sources({"items": []}) == 0
```

- [ ] **Step 2:** → Expected FAIL

- [ ] **Step 3:**

```python
def _event_independent_sources(cluster):
    """独立信源数（source_key 去重），替代 len(source_types)（spec F4）。"""
    keys = {(it.get("source_key") or it.get("source") or "")
            for it in cluster.get("items", [])} - {""}
    return len(keys)
```

`_score_events` 内 `n_types = len(source_types)` → `n_types = max(1, _event_independent_sources(cluster))`；`breadth` 同步改用该值（`min(10, n_src * 1.2)`，使 9 家封顶）。

- [ ] **Step 4:** 全套 → 全绿（`test_pool_and_median.py` 若断言旧 breadth 值，按新口径改并在测试头注明依据）
- [ ] **Step 5:** `git commit -m "fix(insight): 跨源共振改数独立 source_key，不再被 4 类 source_type 抹平（漏斗化 Task13）"`

### Task 14: `best_score` 由 max 改簇内聚合

**Files:**
- Modify: `build_daily_insight.py:1126/1153/1242/1340`
- Test: `tests/daily_insight/test_best_score_aggregation.py`

**Interfaces:**
- Produces: `_aggregate_cluster_score(cluster) -> float` = `mean + 0.15 * sum`（mean 打底、sum 封顶）

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F3：best_score 取簇内单条最高 → 一条强相似即可带全簇上位，多方共振不加分。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

def test_many_moderate_beats_one_strong():
    one_strong = {"items": [{"final_score": 0.9}]}
    six_moderate = {"items": [{"final_score": 0.5}] * 6}
    assert (bdi._aggregate_cluster_score(six_moderate)
            > bdi._aggregate_cluster_score(one_strong))

def test_single_item_matches_its_score():
    assert abs(bdi._aggregate_cluster_score({"items": [{"final_score": 0.4}]}) - 0.4) < 1e-6

def test_empty_items_is_zero():
    assert bdi._aggregate_cluster_score({"items": []}) == 0.0
```

- [ ] **Step 2:** → Expected FAIL

- [ ] **Step 3:**

```python
def _aggregate_cluster_score(cluster):
    """簇内聚合分：mean 打底 × (1 + log2(n))，n 封顶 3.0 倍增益。

    为什么不用 `mean + λ·sum`：单条时会把该条分数放大（0.4 → 0.46），破坏
    `test_single_item_matches_its_score` 这条基线不变量；且线性 sum 直接奖励
    转载条数 —— 那正是 Task 13 要压下去的共模因子。log2 放大只承认"多方都提过"，
    不承认"被转了 15 次所以更重要"。
    """
    vals = [float(it.get("final_score", 0) or 0) for it in cluster.get("items", [])]
    if not vals:
        return 0.0
    n = len(vals)
    # 用 sum/len 而非 statistics.fmean —— 本模块未 import statistics（现有 import 见 :11-:23）
    return round((sum(vals) / n) * (1.0 + min(3.0, math.log2(n))), 4)
```

三处写入点（`:1153` `:1242`）的 `ei["best_score"] = max(...)` 改为在合并完成后统一由 `_aggregate_cluster_score` 重算；`:1340` 的 `base_score = cluster.get("best_score", 0)` → `base_score = _aggregate_cluster_score(cluster)`。

- [ ] **Step 4:** 全套 → 全绿；**变异体**：把公式退回 `max(vals)`，`test_many_moderate_beats_one_strong` 必红，还原
- [ ] **Step 5:** `git commit -m "fix(insight): 事件分由簇内单条最高改聚合，抑制单点强相似带全簇（漏斗化 Task14）"`

### Task 15: 排序目标并列化 + 权重校准

**Files:**
- Modify: `build_daily_insight.py:1333-1414`（`_score_events`）、`_quick_score_event:2202`
- Test: `tests/daily_insight/test_multi_objective_score.py`

**Interfaces:**
- Consumes: `_compute_momentum`（12）、`_event_independent_sources`（13）、`_aggregate_cluster_score`（14）、`_quick_score_event`（现成四维）
- Produces: `EVENT_SCORE_WEIGHTS = {"momentum":0.30,"n_src":0.20,"freshness":0.15,"depth":0.20,"quality":0.10,"similarity":0.05}`（和为 1.00）；`_event_score(cluster, ledger) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F1/F2/F5：所有时间/共振权重都乘在相似度上 → 相似度定生死。改并列相加。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi

W = bdi.EVENT_SCORE_WEIGHTS
LED = {"老梗": [{"ts": "2026-09-20T0%d:00:00+08:00" % i} for i in range(8)]}

def _cl(sig, sim, n=1, hours=100):
    import datetime
    return {"label": sig, "items": [{"source_key": "s%d" % i, "final_score": sim,
             "pub_date": (bdi.NOW_BJ - datetime.timedelta(hours=hours)).isoformat()}
            for i in range(n)]}

def test_weights_sum_to_one():
    assert abs(sum(W.values()) - 1.0) < 1e-9

def test_similarity_is_no_longer_the_multiplier():
    """相似度从 0 抬到 1 只应带来 w_c 量级的增益，不再决定生死。"""
    lo = bdi._event_score(_cl("新事件", 0.0, n=6, hours=1), LED)["total"]
    hi = bdi._event_score(_cl("新事件", 1.0, n=6, hours=1), LED)["total"]
    assert 0.04 < hi - lo < 0.06          # ≈ w_similarity
    assert hi > bdi._event_score(_cl("老梗", 1.0, n=1, hours=200), LED)["total"]

def test_all_components_present_and_bounded():
    s = bdi._event_score(_cl("新事件", 0.5, n=3), LED)
    assert set(s) >= {"momentum", "n_src", "freshness", "depth", "quality", "similarity", "total"}
    assert all(0.0 <= s[k] <= 1.0 for k in W)
```

- [ ] **Step 2:** `py -3.11 -m pytest tests/daily_insight/test_multi_objective_score.py -q -s --junitxml=_j15.xml` → Expected FAIL

- [ ] **Step 3:**

```python
def _event_score(cluster, ledger):
    """多目标并列打分：相似度退为权重最小的一项（spec §4.1）。"""
    src = _event_independent_sources(cluster)
    sig = _event_sig(cluster.get("label", ""))
    comps = {
        "momentum": _compute_momentum(sig, ledger),
        "n_src": min(1.0, math.log2(src + 1) / math.log2(9)),
        "freshness": _recency_decay(_latest_pubdate(cluster)),
        "depth": min(1.0, (_quick_score_event(cluster) or 0) / 100.0),
        "quality": min(1.0, len(cluster.get("items", [])) / 8.0),
        "similarity": min(1.0, _aggregate_cluster_score(cluster)),
    }
    comps = {k: (round(v, 4) if v == v else 0.0) for k, v in comps.items()}  # NaN 防（v==v 为 False）
    comps["total"] = round(sum(comps[k] * EVENT_SCORE_WEIGHTS[k] for k in EVENT_SCORE_WEIGHTS), 4)
    return comps
```

新增 `_latest_pubdate(cluster)`（内部统一 `_parse_iso`，无日期返回 `NOW_BJ - INSIGHT_RSS_HOURS` 小时）。`_score_events` 里 `final = base_score * cross_mult * recency * accel_mult` → `final = _event_score(cluster, _ledger)["total"] * 100`（沿用既有 `score` 量纲，避免下游 `editor_score`/槽位逻辑连带改动）；`clusters.sort(key=...)` 保持读 `cluster["score"]`。

- [ ] **Step 4:** 全套 → 全绿；**变异体**：把 `W["similarity"]` 改成 `W["momentum"]`（等价于换回相似度主干），`test_similarity_is_no_longer_the_multiplier` 必红，还原
- [ ] **Step 5: 权重校准（不进 CI，产出可核对记录）**

用 Task 1 的远端统计 + Task 11 账本，对 `W` 的三组候选（默认 / `momentum 0.40·n_src 0.10·similarity 0.05` / `depth 0.30·momentum 0.20·similarity 0.05`）各离线重放近 24 场排序，计算**事后标注命中率**（今场判 momentum 前 5 的 sig，24 场后是否仍在账本里出现），取最高的一组。三组数字与选择依据写进 spec §6。**不得以 RAGAS 三维作为本 Task 的验收依据**（spec §6 理由 2：扩面对 cov 不可见且放大分母）。

- [ ] **Step 6:** `git commit -m "feat(insight): 主报告事件打分改多目标并列相加，相似度降为最小权重项并按事后标注校准权重（漏斗化 Task15）"`

### Task 16: 候选多路化（momentum/fresh 直供，源先验待 B 线结论）

**Files:**
- Modify: `build_daily_insight.py:5303`（retrieve 调用点）、`_assemble_events`
- Test: `tests/daily_insight/test_multi_channel_recall.py`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""F1：候选集在 _hybrid_retrieve 的 top_k=200 就定死了，后面的权重只能微调。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

def _c(t, score, key="s1", hours=1):
    return {"title": t, "text": "x" * 50, "chunk_id": t, "final_score": score,
            "source_type": "rss", "source_key": key, "url": "https://u/" + t,
            "pub_date": (bdi.NOW_BJ - datetime.timedelta(hours=hours)).isoformat()}

def test_unretrieved_but_accelerating_event_enters(monkeypatch):
    """RRF 排不进 top200、但账本显示在涨的条目，必须经直供通道进候选。"""
    monkeypatch.setattr(bdi, "_load_event_signals",
                        lambda window_builds=24: {bdi._event_sig("突发地缘事件"): [{"ts": "t"}] * 5})
    rrf = [_c("老梗", 0.9)]
    direct = [_c("突发地缘事件", 0.01)]
    merged = bdi._merge_recall_channels(rrf, direct)
    assert any(c["title"] == "突发地缘事件" for c in merged)

def test_dedup_by_chunk_id():
    a = _c("同一件事", 0.5)
    assert len(bdi._merge_recall_channels([a], [a])) == 1
```

- [ ] **Step 2:** → Expected FAIL

- [ ] **Step 3:**

```python
def _merge_recall_channels(*channels):
    """多路召回并集，按 chunk_id 去重（先入优先，保持通道顺序即优先级）。"""
    seen, out = set(), []
    for ch in channels:
        for c in ch or []:
            cid = c.get("chunk_id") or (c.get("url") or "") + (c.get("title") or "")
            if cid in seen:
                continue
            seen.add(cid)
            out.append(c)
    return out
```

调用点：`_hybrid_retrieve` 之后加 `_fresh_channel`（`INSIGHT_RSS_HOURS` 内、账本命中 ≥1、未进 RRF 结果的前 30 条），`retrieved = _merge_recall_channels(retrieved, _fresh_channel)`。**本 Task 不含 `cat` 源先验直供**——待 Task 10 的池纯度达标后另开（spec §4.1 顺序依赖）。

- [ ] **Step 4:** 全套 → 全绿；**变异体**：`seen` 命中时不 `continue`（不去重），`test_dedup_by_chunk_id` 必红，还原
- [ ] **Step 5: 构建时长核算（blocking 前置门）**

对比改造前后各 3 场 CI 的洞察步骤耗时；增量 > 3 分钟则**本 Task 不得推送**，先做增量归因（账本读盘 / `_cluster_pool` / 多出的 LLM 调用）。Expected: 记录进 spec §6，含具体秒数。

- [ ] **Step 6:** `git commit -m "feat(insight): 候选入口多路化，新鲜+账本命中直供通道并入并集（漏斗化 Task16）"`

---

## 收尾（每个 Phase 各做一次）

- [ ] `py -3.11 -m pytest tests/daily_insight/ -q -s --junitxml=_final.xml`，读 XML 汇总行，不看步骤结论
- [ ] CI 同构复跑（照抄门禁 B 清空六个 API key 的环境），记录 `[0-9]+ passed / [0-9]+ failed` 原文
- [ ] fresh-eyes 对抗审查 subagent：只给它 spec + diff，不给本会话结论；重点审闸序完整性、`TOPIC_TAXONOMY` 不变量、证据包不进引用编号、新字段的 `(x.get(k) or "")` 双防
- [ ] 清理临时件；确认 `update.yml`/`build_rss_aggregator.py` 未被 staged
- [ ] 推送前 `py -3.11 tools/data_api_push.py --check-only`；**逐次征得用户同意**后才推；推完 `remote_drift_check.py` 逐文件复查 blob，下一场构建后再复查一次

## 依赖顺序

```
Task1 → Task2 → Task3 → Task4          （Phase 0：先能测）
Task5 → Task6 → Task7 → Task8 → Task9 → Task10   （Phase 1：破茧）
Task11 → Task12 → Task13 → Task14 → Task15 → Task16  （Phase 2：主报告）
Task10 的纯度结论 ─┘ 决定 Task16 是否追加源先验直供通道
```
