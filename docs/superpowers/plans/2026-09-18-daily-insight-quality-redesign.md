# 每日洞察质量管线重设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复每日洞察管线的 5 个质量缺陷：主题分类层缺失、破茧栏选不出非科技内容、Phase 2 素材单薄致幻觉、[信息不足] 过滤失效、key_links 同质化。

**Architecture:** 在 chunk 构建处注入关键词主题分类（QWIS 优先级匹配法），破茧栏改为"正向识别非科技 topic → 热度排序"（QWIS cocoonFamiliar 二元排除式）；Phase 2 深度分析前构建 RSS 全文证据包（复用 rss_history.json 已有数据）；事件级 4 维快筛（BestBlogs v4 权重 40/30/20/10）作为深度分析门槛。RAGAS 闭环、Phase 1、检索、聚类、嵌入全部不动。

**Tech Stack:** Python 3.11（本地 `py -3.11`）、pytest（tests/daily_insight/ 已有 13 个测试文件、113 用例）、GitHub Actions（.github/workflows/update.yml）。

**Spec:** 本文件即方案；问题分析记录见 `docs/superpowers/specs/2026-09-17-daily-insight-problem-analysis.md`。

## 基线事实（2026-09-18 验证于 commit 6ed87e9+，勿凭记忆改动）

- 本地基线：`py -3.11 -m pytest tests/daily_insight/ -q -s` → **111 passed, 2 failed**。
  两个失败是"契约红测试"，本计划使其转绿：
  - `test_dedup.py::test_different_category_not_merged`（要求去重第一轮加类别守卫）
  - `test_integration.py::test_bubble_breaker_present`（要求破茧函数在无 residual 时按 category 新颖度兜底选卡）
- **Git Bash 下 pytest 必须带 `-s`**，否则捕获机制报 `OSError: Bad file descriptor`。
- CI 只跑根目录脚本测试（update.yml L97-100：`python test_daily_insight.py` 等 4 个），**tests/daily_insight/ 的 pytest 套件不在 CI 门禁内**。
- CI 依赖安装（update.yml L~71）：`pip install llama-index-core ... rank-bm25`，**无 pytest**。
- 本地 `rss_history.json`：18037 条，key=link，字段含 `full_content/summary/summary_zh/cat/source/title/title_zh/pub_date`。全文覆盖不均：x.com/reddit/v2ex 66-98%，ithome/bbc/36kr/澎湃/agihunt/aihot 0-2%。社媒长文恰是 Phase 2 最需要全文的部分，证据包对其收益最大。
- 已知构建时序差：CI 中 rss_history 由前一次构建提交，当日新事件 URL 可能不在库里，URL 匹配是 best-effort。

## Global Constraints

- 只改 `build_daily_insight.py`、`tests/daily_insight/`、`.github/workflows/update.yml`；不改 `insight_engine.py`、`build_rss_aggregator.py`、RAGAS/检索/聚类/嵌入逻辑。
- RAGAS 三件套（`_verify_faithfulness`/`_self_review_phase1`/`_ragas_evaluate_and_correct`）与 Phase 1/Phase 2 prompt 主体保持原样，只做本计划标注的插入。
- 每任务 TDD：先写失败测试 → 跑红 → 最小实现 → 跑绿 → 提交。**commit 留在本地，push 必须另行征得用户同意**（记忆约束）。
- 测试文件禁止打印非 GBK 字符（Windows 控制台），断言失败信息用中文即可。
- 新字段命名固定：chunk 级 `topic_tag`（str），事件级门槛分 `editor_score`（int 0-100）。
- 精准修改锚点行号基于 6ed87e9，执行时先 `git pull` 无关（本地即最新），但**若锚点附近代码已变动，以锚点代码文本而非行号定位**。

---


### Task 1: [信息不足] 前缀匹配修复 + key_links 多样性校验

两个独立小修，共用一个测试文件。

**Files:**
- Modify: `build_daily_insight.py:4019`（key_links 赋值处）、`build_daily_insight.py:4022`（过滤条件）
- Test: `tests/daily_insight/test_placeholder_and_links.py`（新建）

**Interfaces:**
- Produces: `_is_insufficient(text) -> bool`；`_validate_key_links(links, items) -> list[str]`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 1: [信息不足] 前缀匹配 + key_links 多样性校验。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi


class TestIsInsufficient:
    def test_exact_marker(self):
        assert bdi._is_insufficient("xx[信息不足]xx") is True

    def test_colon_variant(self):
        # LLM 实际输出 [信息不足：解释...]，旧 `'[]' in` 判断漏过（9/18 evt_004 实锤）
        assert bdi._is_insufficient("[信息不足：素材库中面板数据分属不同来源]") is True

    def test_normal_text(self):
        assert bdi._is_insufficient("OpenAI 发布了新模型") is False

    def test_none_safe(self):
        assert bdi._is_insufficient(None) is False


class TestValidateKeyLinks:
    def test_keeps_diverse_links(self):
        links = ["https://a.com/1", "https://b.com/2"]
        assert bdi._validate_key_links(links, []) == links

    def test_dedups_same_link(self):
        assert bdi._validate_key_links(["https://a.com/1", "https://a.com/1"], []) == ["https://a.com/1"]

    def test_all_identical_falls_back_to_item_urls(self):
        # 9/18 实锤：全事件 key_links 指向同一 AIHOT URL
        same = ["https://x.com/s"]
        items = [{"url": "https://r1.com/a"}, {"url": "https://r2.com/b"}, {"url": "https://x.com/s"}]
        out = bdi._validate_key_links(same, items)
        assert len(out) == 3 and "https://x.com/s" in out

    def test_empty_links_uses_items(self):
        out = bdi._validate_key_links([], [{"link": "https://i.com/1"}])
        assert out == ["https://i.com/1"]

    def test_capped_at_5(self):
        items = [{"url": "https://i.com/%d" % i} for i in range(10)]
        assert len(bdi._validate_key_links([], items)) == 5
```

- [ ] **Step 2: 跑红** — Run: `py -3.11 -m pytest tests/daily_insight/test_placeholder_and_links.py -q -s` → FAIL（函数不存在）
- [ ] **Step 3: 实现**（放在 `_deduplicate_after_phase1` 定义之前，即 L1942 空行区）

```python
_INSUFFICIENT_RE = re.compile(r'\[信息不足')


def _is_insufficient(text):
    """[信息不足] 占位判断：前缀匹配，覆盖 [信息不足] 与 [信息不足：...] 两种输出。"""
    return bool(_INSUFFICIENT_RE.search(text or ""))


def _validate_key_links(links, items):
    """key_links 去重保序；若多样性不足（≤1 个），用事件 items 的 URL 补足到 ≤3；上限 5。"""
    seen, out = set(), []
    for u in links or []:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    if len(out) <= 1:
        for it in items or []:
            u = it.get("url", "") or it.get("link", "")
            if u and u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= 3:
                break
    return out[:5]
```

- [ ] **Step 4: 接管线**（两处 Edit）
  - L4019 `c["key_links"] = pe.get("key_links", [])` → `c["key_links"] = _validate_key_links(pe.get("key_links", []), c.get("items", []))`
  - L4022 `_good = [c for c in clusters if '[信息不足]' not in (c.get('summary', '') or '')]` → `_good = [c for c in clusters if not _is_insufficient(c.get('summary'))]`
- [ ] **Step 5: 跑绿 + 全量回归** — `py -3.11 -m pytest tests/daily_insight/ -q -s` → 112+ passed（2 failed 为 Task 2/3 范围的既有红测试）
- [ ] **Step 6: Commit** `git commit -m "fix(insight): [信息不足] 前缀匹配修复 + key_links 多样性校验回退"`

---

### Task 2: 主题分类层（TOPIC_TAXONOMY + _classify_topic + chunk 注入）

借鉴 QWIS：8 类、优先级顺序匹配、首个命中即停、无命中 → "other"。分类只用于路由（Task 3 破茧候选池 + Task 5 相关性维度），**不改变主检索语料**。

**Files:**
- Modify: `build_daily_insight.py:94-97` 后新增常量；`_make_chunk`（L541-561）注入 topic_tag；RSS 调用处（L572-576 等 3 处 `_make_chunk` 调用）经 extra 传 `cat`
- Test: `tests/daily_insight/test_topic_classify.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `TOPIC_TAXONOMY: list[tuple[str, list[str]]]`（有序）、`MAIN_TOPICS: set[str]`、`BUBBLE_TOPICS: set[str]`、`_classify_topic(title, text, source, cat="") -> str`；所有 chunk 带 `topic_tag` 字段

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 2: 主题分类层。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi


class TestClassifyTopic:
    def test_ai_hits_main(self):
        assert bdi._classify_topic("OpenAI 发布 GPT-6 大模型", "", "") == "ai"

    def test_ai_covers_chip_vendor(self):
        assert bdi._classify_topic("英伟达发布新一代 GPU 训练芯片", "", "") == "ai"

    def test_programming_hits_main(self):
        assert bdi._classify_topic("GitHub 推出新开源框架", "", "") == "programming"

    def test_finance_hits_bubble(self):
        assert bdi._classify_topic("央行宣布降准 0.5 个百分点", "", "") == "finance"

    def test_geopolitics_hits_bubble(self):
        assert bdi._classify_topic("联合国安理会召开紧急会议讨论制裁", "", "") == "geopolitics"

    def test_society_hits_bubble(self):
        assert bdi._classify_topic("高考报名人数再创历史新高", "", "") == "society"

    def test_culture_hits_bubble(self):
        assert bdi._classify_topic("诺贝尔文学奖揭晓", "", "") == "culture"

    def test_no_hit_is_other(self):
        assert bdi._classify_topic("今天天气不错", "", "") == "other"

    def test_ai_priority_over_finance(self):
        # 优先级：ai 在 finance 前，"英伟达股价"归 ai（科技主战场事件不被破茧抢走）
        assert bdi._classify_topic("英伟达股价创历史新高", "", "") == "ai"

    def test_rss_cat_ai_hint(self):
        # 无关键词命中但 RSS cat=ai → ai
        assert bdi._classify_topic("某条短讯", "", "", cat="ai") == "ai"

    def test_bubble_and_main_topics_partitioned(self):
        assert bdi.MAIN_TOPICS.isdisjoint(bdi.BUBBLE_TOPICS)
        assert "finance" in bdi.BUBBLE_TOPICS and "ai" in bdi.MAIN_TOPICS


class TestChunkTopicTag:
    def test_chunk_documents_tags_all_chunks(self):
        rss = [{"title": "央行宣布降息", "link": "https://a/1", "source": "s",
                "summary": "", "full_content": "", "pub_date": "", "cat": "news", "source_key": "k"}]
        hot = [{"title": "OpenAI 发布新模型", "url": "https://b/2", "platform": "weibo"}]
        chunks = bdi._chunk_documents(rss, hot, [], [])
        assert chunks and chunks[0]["topic_tag"] == "finance"
        assert any(c.get("topic_tag") == "ai" for c in chunks[1:])
```

- [ ] **Step 2: 跑红** → FAIL（TOPIC_TAXONOMY 不存在）
- [ ] **Step 3: 实现**（常量加在 `VALID_CATEGORIES` 定义之后）

```python
# ── 主题分类层（借鉴 QWIS：优先级顺序匹配，首个命中即停） ──
# 顺序敏感：ai 在最前，确保"英伟达股价"类科技金融交叉事件留在主报告
TOPIC_TAXONOMY = [
    ("ai", ["大模型", "模型", "gpt", "claude", "gemini", "llm", "openai", "anthropic",
            "deepmind", "智能体", "agent", "芯片", "gpu", "nvidia", "英伟达", "算力",
            "训练", "推理", "机器人", "自动驾驶", "深度学习", "机器学习", "agi", "多模态"]),
    ("programming", ["github", "开源", "编程", "开发者", "框架", "sdk", "api", "编译器",
                     "rust", "python", "javascript", "代码", "漏洞", "安全研究", "插件"]),
    ("finance", ["央行", "利率", "股价", "股涨", "股跌", "指数涨", "基金", "债券", "汇率",
                 "通胀", "gdp", "a股", "美股", "港股", "期货", "黄金", "存款", "贷款", "楼市", "房价"]),
    ("geopolitics", ["联合国", "安理会", "制裁", "关税", "外交", "军事", "导弹", "停火",
                     "选举投票", "峰会", "北约", "俄乌", "中东", "台海", "法案通过", "禁令"]),
    ("society", ["高考", "报名", "就业", "医疗", "医保", "养老", "生育", "人口", "事故",
                 "警方", "法院", "判决", "教育", "校园", "疫情", "疫苗", "火车", "航班"]),
    ("culture", ["诺贝尔", "奥斯卡", "世界杯", "奥运", "联赛", "电影票房", "文学奖",
                 "博物馆", "考古", "演唱会", "夺冠", "运动员", "太空", "天文", "发射"]),
]
MAIN_TOPICS = {"ai", "programming"}
BUBBLE_TOPICS = {"finance", "geopolitics", "society", "culture"}
_CAT_HINTS = {"ai": "ai", "dev": "programming", "tech": "programming",
              "news": "other", "wechat": "other", "cn_tech": "programming"}


def _classify_topic(title, text, source, cat=""):
    """关键词优先级匹配。无命中时按 RSS cat 提示归类，最终回退 other。"""
    hay = ((title or "") + " " + (text or "")[:300] + " " + (source or "")).lower()
    for tag, kws in TOPIC_TAXONOMY:
        for kw in kws:
            if kw in hay:
                return tag
    return _CAT_HINTS.get(cat, "other")
```

- [ ] **Step 4: chunk 注入**。`_make_chunk` 内 `c = {...}` 字典增加一行：`"topic_tag": _classify_topic(title, text, source, (extra or {}).get("cat", "")),`。RSS 3 处 `_make_chunk` 调用补 `extra={"cat": item.get("cat", "")}`（若已有 extra 参数则 merge 进 cat 键）。
  注意：topic_tag 不参与 `content_hash` 计算，向量缓存不会失效。
- [ ] **Step 5: 跑绿 + 全量回归**（仍只允许 Task 3 范围那 1 个红测试失败）
- [ ] **Step 6: Commit** `git commit -m "feat(insight): 新增关键词优先级主题分类层，chunk 注入 topic_tag"`

---

### Task 3: 破茧栏重写（正向选非科技池 + 热度排序 + 类别兜底）

替换现有"从 residual 边角料按 source_type 打分"的设计。**同时使既有红测试 `test_bubble_breaker_present` 转绿**。

**Files:**
- Modify: `build_daily_insight.py:2473`（`_select_bubble_events`）、L4129（调用点）
- Test: `tests/daily_insight/test_bubble_v2.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `BUBBLE_TOPICS`、chunk `topic_tag`
- Produces: `_select_bubble_events(clusters, read_profile, residual_chunks=None, all_chunks=None, top_n=5) -> list[dict]`（卡片 dict 字段与现有输出 schema 完全一致：label/summary/category/score/reason/url/source）

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 3: 破茧栏 v2 — 非科技候选池 + 热度排序 + 类别兜底。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
if bdi.NOW_BJ is None:
    bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)


def _chunk(title, tag, hot=0, days_ago=0, url=None):
    pub = (bdi.NOW_BJ - datetime.timedelta(days=days_ago)).isoformat()
    return {"title": title, "text": "正文" * 30, "topic_tag": tag, "hot": hot,
            "pub_date": pub, "url": url or ("https://u/" + title), "source": "test",
            "source_type": "rss"}


class TestBubbleV2:
    def setup_method(self):
        self.clusters = [{"label": "AI大事件", "category": "ai-models", "summary": "s",
                          "items": [{"url": "https://u/ai1", "title": "AI大事件"}]}]
        self.profile = {"ai-models": 10}

    def test_selects_non_tech_only(self):
        pool = [_chunk("央行宣布降准", "finance", hot=8),
                _chunk("某模型发布", "ai", hot=9)]
        out = bdi._select_bubble_events(self.clusters, self.profile, all_chunks=pool, top_n=5)
        assert [c["category"] for c in out] == ["finance"]  # ai 内容被拒

    def test_heat_ordering(self):
        pool = [_chunk("台风登陆", "society", hot=2), _chunk("大选开票", "geopolitics", hot=9)]
        out = bdi._select_bubble_events(self.clusters, self.profile, all_chunks=pool, top_n=2)
        assert out[0]["category"] == "geopolitics"

    def test_excludes_main_event_urls(self):
        pool = [_chunk("央行降准", "finance", hot=5, url="https://u/ai1")]
        out = bdi._select_bubble_events(self.clusters, self.profile, all_chunks=pool, top_n=5)
        assert out == [] or all("ai1" not in c["url"] for c in out)

    def test_dedup_similar_titles(self):
        pool = [_chunk("央行宣布降准落地", "finance", hot=8),
                _chunk("央行宣布降准 释放流动性", "finance", hot=7)]
        out = bdi._select_bubble_events(self.clusters, self.profile, all_chunks=pool, top_n=5)
        assert len(out) == 1

    def test_card_schema(self):
        out = bdi._select_bubble_events(self.clusters, self.profile,
                                        all_chunks=[_chunk("诺贝尔文学奖揭晓", "culture")], top_n=1)
        assert set(out[0].keys()) >= {"label", "summary", "category", "score", "reason", "url", "source"}
        assert "科技" in out[0]["reason"] or "常读" in out[0]["reason"]

    def test_empty_pool_falls_back_to_cluster_categories(self):
        # 无 all_chunks 无 residual → 按 category 与 read_profile 新颖度从 clusters 兜底
        clusters = self.clusters + [{"label": "农业热点", "category": "agriculture",
                                     "summary": "s2", "items": []}]
        out = bdi._select_bubble_events(clusters, self.profile, top_n=1)
        assert len(out) == 1 and out[0]["category"] == "agriculture"
```

- [ ] **Step 2: 跑红** → 新测试 FAIL；确认 `test_integration.py::test_bubble_breaker_present` 也 FAIL
- [ ] **Step 3: 重写 `_select_bubble_events`**（整函数替换，保留旧 residual 评分段作为次级兜底）

```python
def _select_bubble_events(clusters, read_profile, residual_chunks=None, all_chunks=None, top_n=5):
    """破茧栏 v2：正向识别非科技主题候选池 → 热度排序（QWIS cocoonFamiliar 式）。

    候选优先级：
    1. all_chunks 中 topic_tag ∈ BUBBLE_TOPICS 的 chunk（主设计路径）
    2. residual_chunks 旧路径（过渡兼容，行为保留）
    3. clusters 中 category 与 read_profile 交集最低的兜底
    """
    main_keys = set()
    for c in clusters:
        for it in c.get("items", []):
            for k in (it.get("url", ""), (it.get("title", "") or "").strip()):
                if k:
                    main_keys.add(k)
        if c.get("label"):
            main_keys.add(c["label"])

    def _fresh(chunk):
        u = chunk.get("url", "") or chunk.get("link", "")
        t = (chunk.get("title", "") or "").strip()
        return u not in main_keys and t not in main_keys

    def _heat_key(ch):
        hot = min(10.0, float(ch.get("hot", 0) or 0))
        pub = _parse_iso(ch.get("pub_date", ""))
        age_h = _hours_ago(pub) if pub else 168
        recency = (0.5 ** (age_h / 72.0)) * 10  # 破茧 7 天窗口，半衰期 72h
        return hot * 0.5 + recency * 0.3

    read_top = ", ".join(k for k, v in sorted(read_profile.items(), key=lambda x: -x[1])[:2]) if read_profile else ""

    def _card(ch, score):
        url = ch.get("url", "") or ch.get("link", "")
        tag = ch.get("topic_tag", "")
        return {
            "label": (ch.get("title", "") or "").strip()[:80],
            "summary": ((ch.get("text", "") or "").strip() or ch.get("summary", ""))[:200],
            "category": tag,
            "score": round(score, 2),
            "reason": "与你常读的科技领域不同" if read_top else "非科技热点",
            "url": url,
            "source": ch.get("source", "") or ch.get("platform", ""),
        }

    # ── 路径 1：非科技候选池 ──
    pool = [c for c in (all_chunks or []) if c.get("topic_tag") in BUBBLE_TOPICS and _fresh(c)]
    pool.sort(key=_heat_key, reverse=True)
    result, used_tokens = [], []
    for ch in pool:
        toks = _tokenize_title(ch.get("title", ""))
        if any(_jaccard(toks, u) >= 0.5 for u in used_tokens):  # 同题合并（QWIS 阈值 0.5）
            continue
        used_tokens.append(toks)
        result.append(_card(ch, _heat_key(ch)))
        if len(result) >= top_n:
            return result

    # ── 路径 2：residual 旧逻辑（保留原评分实现，此处以 result 非空则直接返回） ──
    if result:
        return result
    # （原 residual 分组评分代码整体保留于此，行为不变）

    # ── 路径 3：clusters 类别新颖兜底 ──
    max_freq = max(read_profile.values()) if read_profile else 1
    cand = [c for c in clusters
            if c.get("category") and c.get("category") not in MAIN_TOPICS
            and c.get("category") not in ("ai-models", "ai-products", "developer")]
    cand.sort(key=lambda c: -(read_profile.get(c.get("category", ""), 0) / max_freq if max_freq else 0))
    for c in cand[:top_n]:
        result.append({
            "label": c.get("label", "")[:80],
            "summary": (c.get("summary", "") or "")[:200],
            "category": c.get("category", ""),
            "score": round(1.0 - (read_profile.get(c.get("category", ""), 0) / max_freq if max_freq else 0), 2),
            "reason": ("与你常读的 %s 领域不同" % read_top) if read_top else "信息增量",
            "url": (c.get("key_links") or [""])[0],
            "source": ",".join(sorted(c.get("source_types", []) or [])),
        })
    return result
```

实现说明（执行者注意）：
- 路径 2 保留方式：把现有 L2484-2547 的 residual 评分块原样剪切到"路径 1 无结果"之后，作为中间兜底；卡片生成逻辑不变。若担心复杂度，可将路径 2 简化为直接 `return []` 前的一次尝试——但**必须保证 `test_integration.py::test_bubble_breaker_present` 与既有破茧测试全绿**，以测试为准绳。
- 调用点 L4129 改为：`bubble_breaker = _select_bubble_events(clusters, read_profile, residual_chunks=retrieved_for_ragas, all_chunks=chunks)`（`chunks` 是 L3835 当日全量 chunk 列表，同函数作用域内可用）。
- `_parse_iso`/`_hours_ago`/`_tokenize_title`/`_jaccard` 均为既有函数，直接调用。

- [ ] **Step 4: 跑绿** — `py -3.11 -m pytest tests/daily_insight/test_bubble_v2.py tests/daily_insight/test_integration.py -q -s` 全绿
- [ ] **Step 5: 全量回归**（只允许 `test_different_category_not_merged` 1 红，若它在 Task 2 后被顺带变绿更好）
- [ ] **Step 6: Commit** `git commit -m "feat(insight): 破茧栏 v2 — 非科技 topic 候选池 + 热度排序 + 类别兜底"`

---

### Task 4: Phase 2 证据包（复用 rss_history 全文）

Phase 2 当前只见 `_build_event_material` 的 800 字截断（L1828）。用 URL 归一化反查 rss_history 全文，补一段 prompt。引用编号体系不变（citations 仍只能引用素材 [n]，证据包只作交叉核对，防止破坏 9/18 刚上线的 citations 校验）。

**Files:**
- Modify: `build_daily_insight.py:2275-2301`（`_llm_phase2` 加参注入）、L4080-4090（Phase 2 循环构建证据）
- Test: `tests/daily_insight/test_evidence_pack.py`（新建）

**Interfaces:**
- Consumes: `rss_history`（run() L3775 已加载）、`_strip_html`
- Produces: `_norm_url(u) -> str`；`_build_evidence_pack(cluster, rss_by_url, max_docs=3, doc_chars=2500) -> str`；`_llm_phase2(..., evidence="")`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 4: Phase 2 证据包 — URL 归一化反查 RSS 全文存档。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi


class TestNormUrl:
    def test_protocol_and_www_insensitive(self):
        assert bdi._norm_url("https://www.ithome.com/1/004.htm") == \
               bdi._norm_url("http://ithome.com/1/004.htm/")

    def test_case_insensitive(self):
        assert bdi._norm_url("https://A.COM/X") == "a.com/x"


def _hist(link, body, source="Reddit", title="帖标题"):
    return {link: {"link": link, "full_content": body, "source": source, "title": title}}


class TestEvidencePack:
    def test_hit_returns_fulltext(self):
        url = "https://www.reddit.com/r/ai/comments/1x/"
        cluster = {"items": [{"url": "https://reddit.com/r/ai/comments/1x"}]}
        by_url = {bdi._norm_url(k): v for k, v in _hist(url, "讨" * 500).items()}
        pack = bdi._build_evidence_pack(cluster, by_url)
        assert "讨" * 100 in pack and "[..." not in pack[:3]
        assert "Reddit" in pack

    def test_short_body_skipped(self):
        url = "https://a.com/1"
        cluster = {"items": [{"url": url}]}
        by_url = {bdi._norm_url(k): v for k, v in _hist(url, "太短了" * 10).items()}
        assert bdi._build_evidence_pack(cluster, by_url) == ""

    def test_no_match_returns_empty(self):
        assert bdi._build_evidence_pack({"items": [{"url": "https://no/1"}]}, {}) == ""

    def test_capped_by_doc_chars(self):
        url = "https://x.com/s/status/1"
        by_url = {bdi._norm_url(k): v for k, v in _hist(url, "字" * 9000).items()}
        pack = bdi._build_evidence_pack({"items": [{"url": url}]}, by_url, doc_chars=2500)
        assert pack.count("字") <= 2500

    def test_max_docs(self):
        cluster = {"items": [{"url": "https://m/%d" % i} for i in range(5)]}
        by_url = {}
        for i in range(5):
            by_url.update({bdi._norm_url(k): v for k, v in
                           _hist("https://m/%d" % i, "内" * 300).items()})
        pack = bdi._build_evidence_pack(cluster, by_url, max_docs=3)
        assert pack.count("内") <= 300 * 3


class TestPhase2PromptInjection:
    def test_evidence_block_in_prompt(self, monkeypatch):
        captured = {}
        class FakeLLM:
            def complete(self, messages, **kw):
                captured["prompt"] = messages[1]["content"]
                return '{"event_reconstruction":"r","impact_analysis":"i","source_divergence":"d","quote":"q","outlook":"o","confidence":"high","citations":{"quote":1}}'
        cluster = {"items": [{"title": "t", "text": "素材正文", "source_type": "agihunt",
                              "channel": "agi", "hot": 5, "url": "https://u/1"}]}
        bdi.NOW_BJ = bdi.NOW_BJ or bdi._now_bj()
        bdi._llm_phase2(FakeLLM(), cluster, {"label": "L", "summary": "S"},
                        evidence="【Reddit】帖标题\n全文证据段内容" * 10)
        assert "补充全文参考" in captured["prompt"]
        assert "全文证据段内容" in captured["prompt"]
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现 `_norm_url` + `_build_evidence_pack`**（放 `_build_event_material` 附近）

```python
def _norm_url(u):
    """URL 归一化：去协议/www/尾斜杠/小写，用于跨源反查 RSS 存档。"""
    u = (u or "").strip().lower()
    u = re.sub(r'^https?://', '', u)
    u = re.sub(r'^www\.', '', u)
    return u.rstrip('/')


def _build_evidence_pack(cluster, rss_by_url, max_docs=3, doc_chars=2500):
    """事件 URL 反查 rss_history 全文，拼为 Phase 2 交叉核对参考。"""
    docs, seen = [], set()
    for it in cluster.get("items", []):
        key = _norm_url(it.get("url") or it.get("link"))
        if not key or key in seen:
            continue
        rec = rss_by_url.get(key)
        if not rec:
            continue
        body = _strip_html((rec.get("full_content") or rec.get("summary_zh")
                            or rec.get("summary") or "").strip())
        if len(body) < 120:
            continue
        seen.add(key)
        docs.append("【%s】%s\n%s" % (rec.get("source", ""), rec.get("title", ""), body[:doc_chars]))
        if len(docs) >= max_docs:
            break
    return "\n\n".join(docs)
```

- [ ] **Step 4: `_llm_phase2` 注入**：签名加 `evidence=""`；在 `if prev_summary:` 之前插入：

```python
    if evidence:
        prompt += """
### 补充全文参考（同源 RSS 存档原文，用于交叉核对数据与信源观点分歧；不可作为引用编号来源，citations 仍只能引用上方素材 [n] 编号）
%s
""" % evidence[:8000]
```

- [ ] **Step 5: 调用点接线**（Phase 2 循环 L4080 区域）：循环前加 `rss_by_url = {_norm_url(k): v for k, v in rss_history.items() if isinstance(v, dict)}`；`deep = _llm_phase2(llm, c, {...}, prev_summary)` 改为追加 `evidence=_build_evidence_pack(c, rss_by_url)`。
- [ ] **Step 6: 跑绿 + 全量回归** → 仅剩 0-1 红（dedup 契约测试若未做）
- [ ] **Step 7: Commit** `git commit -m "feat(insight): Phase2 证据包 — URL 归一化复用 RSS 全文存档作交叉参考"`

---

### Task 5: 事件 4 维快筛门槛（BestBlogs v4 权重）

深度分析（Phase 2）只给 `editor_score >= 55` 的事件做，防止素材单薄事件产出占位垃圾。权重：信号深度 40 / 科技相关性 30 / 事实密度 20 / 新颖度 10，减分项最多 -20。

**Files:**
- Modify: `build_daily_insight.py:4080-4082`（Phase 2 循环加门槛）、cluster 写入 `editor_score`
- Test: `tests/daily_insight/test_quick_score.py`（新建）

**Interfaces:**
- Consumes: chunk `topic_tag`（Task 2）、cluster items
- Produces: `_quick_score_event(cluster, yesterday_labels=None) -> int`（0-100），`MIN_DEEP_SCORE = 55`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Task 5: 事件快筛评分（BestBlogs v4 权重 40/30/20/10）。"""
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi
if bdi.NOW_BJ is None:
    bdi.NOW_BJ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)


def _item(src_type, tag, text="发布了 3 款产品，融资 1.2 亿美元", hours=2, url=""):
    pub = (bdi.NOW_BJ - datetime.timedelta(hours=hours)).isoformat()
    return {"source_type": src_type, "topic_tag": tag, "text": text,
            "title": "某事件", "pub_date": pub, "url": url or ("https://u/" + src_type + str(hours))}


class TestQuickScore:
    def test_strong_event_above_gate(self):
        items = ([_item("rss", "ai", url="https://a/%d" % i) for i in range(4)]
                 + [_item("agihunt", "ai"), _item("hot", "ai"), _item("aihot", "ai")])
        cluster = {"label": "OpenAI 发布 GPT-6", "items": items}
        assert bdi._quick_score_event(cluster) >= bdi.MIN_DEEP_SCORE

    def test_single_item_event_below_gate(self):
        cluster = {"label": "小消息", "items": [_item("rss", "ai", text="一句话", hours=1)]}
        assert bdi._quick_score_event(cluster) < bdi.MIN_DEEP_SCORE

    def test_repeat_deducted(self):
        items = [_item("rss", "ai", url="https://a/%d" % i) for i in range(3)]
        cluster = {"label": "OpenAI 发布 GPT-6", "items": items}
        base = bdi._quick_score_event(cluster)
        repeat = bdi._quick_score_event(cluster, yesterday_labels={"OpenAI 发布 GPT-6"})
        assert repeat <= base - 10

    def test_identical_urls_deducted(self):
        items = [_item("rss", "ai", url="https://same/1") for _ in range(4)]
        cluster = {"label": "同质事件", "items": items}
        assert bdi._quick_score_event(cluster) <= 65

    def test_score_bounded(self):
        items = [_item(t, "ai", url="https://x/%s%d" % (t, i))
                 for t in ("rss", "hot", "aihot", "agihunt") for i in range(4)]
        cluster = {"label": "超级大事件，营收 30 亿美元，增长 150%", "items": items}
        assert 0 <= bdi._quick_score_event(cluster) <= 100
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**

```python
MIN_DEEP_SCORE = 55  # 快筛 ≥55 才进 Phase 2 深度分析（目标分布约 60% 事件）


def _quick_score_event(cluster, yesterday_labels=None):
    """4 维快筛（借鉴 BestBlogs v4）：深度40/相关性30/实用20/新颖10 + 减分。"""
    items = cluster.get("items", []) or []
    n = len(items)
    if n == 0:
        return 0
    # 1) 信号深度 0-40：素材量 + 跨源 + 时间跨度
    src_types = set(it.get("source_type") or it.get("_src") for it in items)
    depth = min(15, n * 2.5) + min(15, len(src_types) * 5) + min(10, n * 1.2)
    # 2) 科技相关性 0-30：topic_tag ∈ MAIN_TOPICS 占比
    main_hits = sum(1 for it in items if it.get("topic_tag") in MAIN_TOPICS)
    relevance = 30.0 * main_hits / n
    # 3) 事实密度 0-20：含具体数字的素材占比
    def _has_num(it):
        return bool(re.search(r'\d', (it.get("text") or "") + (it.get("title") or "")))
    density = 20.0 * sum(1 for it in items if _has_num(it)) / n
    # 4) 新颖度 0-10：24h 内素材占比
    fresh = sum(1 for it in items if _hours_ago(_parse_iso(it.get("pub_date", ""))) <= 24)
    novelty = 10.0 * fresh / n
    raw = depth + relevance + density + novelty
    # 减分（BestBlogs v4 风格，最多 -20）
    ded = 0
    if n == 1:
        ded += 5
    urls = [it.get("url") or it.get("link") for it in items if (it.get("url") or it.get("link"))]
    if urls and len(set(urls)) == 1 and len(urls) > 1:
        ded += 10
    if yesterday_labels and cluster.get("label", "").strip() in yesterday_labels:
        ded += 10
    return int(max(0, min(100, raw - ded)))
```

- [ ] **Step 4: 接线**（Phase 2 循环 L4080 区域）：

```python
            # Phase 2 LLM: Top N 深度解读（快筛门槛：editor_score ≥ MIN_DEEP_SCORE）
            _yday_labels = {e.get("label", "").strip()
                            for d in history.get("days", [])[-2:-1] for e in d.get("events", [])}
            for i, c in enumerate(clusters):
                c["editor_score"] = _quick_score_event(c, yesterday_labels=_yday_labels)
            top_n = min(DEEP_ANALYSIS_TOP_N, len(clusters))
            _deep_done = 0
            for i, c in enumerate(clusters):
                if _deep_done >= top_n or c["editor_score"] < MIN_DEEP_SCORE:
                    if c.get("deep_analysis"):
                        continue
                    c["deep_analysis"] = None
                    continue
```

（循环体内原有 `_filter_cluster_items`/`prev_summary`/`_llm_phase2(...)` 调用保持不动；`history` 变量在该作用域可用——若执行时不可用，从 `_build_read_profile` 的入参路径取同一对象。`_quick_score_event` 写入的 `editor_score` 会随 cluster 进入 `_write_insight_json` 的事件序列化——确认该函数按白名单字段拷贝，若是白名单需在事件 dict 增加 `"editor_score": c.get("editor_score")`。）
- [ ] **Step 5: 跑绿 + 全量回归**
- [ ] **Step 6: Commit** `git commit -m "feat(insight): BestBlogs 式 4 维快筛门槛，深度分析仅 ≥55 分事件"`

---

### Task 6: 去重类别守卫 + pytest 套件纳入 CI

**Files:**
- Modify: `build_daily_insight.py:1971-1973`（第一轮合并条件加类别守卫）
- Modify: `.github/workflows/update.yml`（依赖安装行 + 测试步骤）
- Test: 既有 `tests/daily_insight/test_dedup.py::test_different_category_not_merged`（红转绿）

- [ ] **Step 1: 确认红测试现状**：`py -3.11 -m pytest tests/daily_insight/test_dedup.py -q -s` → `test_different_category_not_merged` FAIL
- [ ] **Step 2: 第一轮合并条件加守卫**：L1971 的 `if (len(...&...) >= 2 and _jaccard(...) >= 0.2):` 增加 `and ci.get("category") == cj.get("category")`（第二轮 summary 去重不加守卫——其跨类别合并是 9/17 修复刻意为之，见 L2007-2013 注释，勿动）。
- [ ] **Step 3: 跑绿** → `test_dedup.py` 全绿；全量 `tests/daily_insight/` **0 failed**
- [ ] **Step 4: CI 纳入**：update.yml 依赖行（L~71）`pip install ... rank-bm25` 末尾追加 ` pytest`；测试步骤（L97-100）在 `python test_daily_insight.py` 后追加 `python -m pytest tests/daily_insight/ -q`
- [ ] **Step 5: 本地模拟 CI 命令**：`py -3.11 test_daily_insight.py` 与 `py -3.11 -m pytest tests/daily_insight/ -q -s` 均通过（注意脚本测试会写盘，跑完 `git checkout -- .` 还原 daily-insight.json 等受版本控制产物）
- [ ] **Step 6: Commit** `git commit -m "fix(insight): 去重第一轮加类别守卫；pytest 套件纳入 CI 门禁"`

---

### Task 7: 端到端真实构建验证（完成定义）

- [ ] **Step 1: 真实构建**：`py -3.11 build_daily_insight.py --offline`（若有 offline 开关；否则直接跑，LLM 走真实 API）。观察日志：主题分类命中统计、破茧候选池大小、证据包命中数、快筛分布、深度分析数量
- [ ] **Step 2: 产物断言**（读 daily-insight.json）：
  - `bubble_breaker` 中 `category ∈ BUBBLE_TOPICS` 的条目 ≥ 3（不足时检查是否走了兜底路径并在报告中说明）
  - 所有事件 `summary` 不含 `[信息不足`
  - 任一事件 `key_links` 无全量重复
  - `deep_analysis` 非 None 的事件均有 `editor_score ≥ 55`
  - `citations` 字段仍存在且 `cited_sources` 非空（防回归 9/18 新上线功能）
- [ ] **Step 3: 对比留档**：把新产物与 9/18 旧产物的事件-素材错位情况写进 commit message；如质量指标（RAGAS overall）显著下降，保留数据并向用户报告，不静默调阈值
- [ ] **Step 4: Commit + 向用户汇报，请求是否 push**（记忆约束：push 必须逐次同意）

---

## Self-Review 记录

1. **Spec 覆盖**：分类层(T2)、破茧(T3)、证据包(T4)、快筛阈值(T5)、[信息不足]bug(T1)、key_links bug(T1)、类别守卫红测试(T6)、CI 环境同构(全局约束+T6)。权重设计中的"减分项/两阶段/引用保护"均有对应。无遗漏。
2. **占位符扫描**：无 TBD；Task 3 路径 2 的"原代码保留"给出了明确行为准绳（旧测试全绿）。
3. **类型一致性**：`topic_tag`(str)/`BUBBLE_TOPICS`(set)/`_norm_url`/`_quick_score_event(cluster, yesterday_labels=None)`/`editor_score`(int) 在各 Task 的 Produces/Consumes 中已对齐。
