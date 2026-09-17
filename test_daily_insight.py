# -*- coding: utf-8 -*-
"""本地测试 build_daily_insight RAG 管线核心逻辑（跳过网络请求）。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import build_daily_insight as B

# 初始化时间
B.NOW_BJ = B._now_bj()
print("=== 测试时间: %s ===" % B.NOW_BJ.strftime("%Y-%m-%d %H:%M"))
print("FAISS available: %s" % B.FAISS_AVAILABLE)
print("BM25 available: %s" % B.BM25_AVAILABLE)

# ── 测试 1: 硬过滤 ──
print("\n=== 测试 1: 硬过滤 ===")
test_items = [
    {"title": "OpenAI 发布 GPT-5 模型", "link": "https://a.com/1"},
    {"title": "震惊！这个 AI 工具太疯了必看", "link": "https://a.com/2"},
    {"title": "限时折扣！优惠券免费领取", "link": "https://a.com/3"},
    {"title": "Anthropic Claude 4 发布", "link": "https://a.com/4"},
    {"title": "ab", "link": "https://a.com/5"},  # 太短
    {"title": "Google Gemini 3 多模态能力评测", "link": "https://a.com/6"},
]
clean = B._filter_noise(test_items)
print("输入 %d 条, 过滤后 %d 条" % (len(test_items), len(clean)))
assert len(clean) == 3, "期望 3 条干净条目，实际 %d" % len(clean)
print("[PASS] 硬过滤正确剔除 3 条噪声")

# ── 测试 2: Jaccard 相似度 ──
print("\n=== 测试 2: Jaccard 相似度 ===")
t1 = B._tokenize_title("OpenAI 发布 GPT-5 模型")
t2 = B._tokenize_title("GPT-5 正式发布 OpenAI 新模型")
t3 = B._tokenize_title("苹果发布新款 iPhone")
sim_same = B._jaccard(t1, t2)
sim_diff = B._jaccard(t1, t3)
print("相似标题 Jaccard: %.3f" % sim_same)
print("不同标题 Jaccard: %.3f" % sim_diff)
assert sim_same > sim_diff, "相似标题应比不同标题 Jaccard 更高"
print("[PASS] Jaccard 相似度符合预期")

# ── 测试 3: 数据加载 ──
print("\n=== 测试 3: 数据加载 ===")
B._load_rss_tiers()
print("RSS Tier 映射: %d 个源" % len(B._RSS_TIER_MAP))

rss_history = B._load_rss_history()
print("RSS 历史: %d 篇" % len(rss_history))

hot_snapshot = B._load_hot_snapshot()
print("热榜快照: %d 个平台" % len(hot_snapshot))

# ── 测试 4: RSS 条目展平 ──
print("\n=== 测试 4: RSS 条目展平 ===")
rss_items = []
for link, item in list(rss_history.items())[:500]:
    if not isinstance(item, dict):
        continue
    title = item.get("title", "") or item.get("title_zh", "")
    if not title:
        continue
    pub_dt = B._parse_iso(item.get("pub_date", ""))
    if B._hours_ago(pub_dt) > 72:
        continue
    rss_items.append({
        "title": title,
        "link": link,
        "source": item.get("source", ""),
        "source_key": item.get("source_key", ""),
        "cat": item.get("cat", ""),
        "summary": item.get("summary", ""),
        "full_content": item.get("full_content", ""),
        "pub_date": item.get("pub_date", ""),
        "_src": "rss",
    })
print("72h 内 RSS 条目: %d 篇" % len(rss_items))

# 热榜展平
hot_items = []
for platform in hot_snapshot:
    plat = platform.get("platform", "")
    for item in platform.get("items", []):
        title = item.get("title", "")
        if not title:
            continue
        hot_items.append({
            "title": title, "url": item.get("url", ""),
            "rank": item.get("rank", 50), "hot": item.get("hot", ""),
            "platform": plat, "_src": "hot",
        })
print("热榜条目: %d 条" % len(hot_items))

# ── 测试 5: 文档切片 ──
print("\n=== 测试 5: 文档切片 ===")
rss_clean = B._filter_noise(rss_items)
hot_clean = hot_items
aihot_clean = []  # 跳过网络
agihunt_clean = []  # 跳过网络

chunks = B._chunk_documents(rss_clean[:100], hot_clean[:50], aihot_clean, agihunt_clean)
print("Chunks: %d 个" % len(chunks))
assert len(chunks) > 0, "应至少有 1 个 chunk"
# 验证 chunk 格式
c0 = chunks[0]
assert "chunk_id" in c0, "chunk 应有 chunk_id"
assert "source_type" in c0, "chunk 应有 source_type"
assert "text" in c0, "chunk 应有 text"
print("首个 chunk: type=%s, title=%s" % (c0["source_type"], c0.get("title", "")[:40]))
print("[PASS] 文档切片产出 %d 个 chunks" % len(chunks))

# ── 测试 6: FAISS 索引构建 ──
print("\n=== 测试 6: FAISS 索引构建 ===")
if B.FAISS_AVAILABLE:
    # 用简单假向量测试索引构建
    import numpy as np
    test_vecs = np.random.randn(20, 128).astype(np.float32)
    test_vecs /= np.linalg.norm(test_vecs, axis=1, keepdims=True)
    idx = B._build_faiss_index(test_vecs.tolist())
    assert idx is not None, "FAISS 索引应成功构建"
    assert idx.ntotal == 20, "索引应有 20 个向量"
    print("FAISS 索引: %d 向量, %d 维" % (idx.ntotal, idx.d))
    print("[PASS] FAISS 索引构建成功")
else:
    print("[SKIP] FAISS 不可用")

# ── 测试 7: 事件组装 ──
print("\n=== 测试 7: 事件组装 ===")
# 构造模拟检索结果
mock_retrieved = []
for i in range(15):
    mock_retrieved.append({
        "chunk_id": "chunk_%05d" % i,
        "source_type": "hot" if i < 5 else "rss",
        "source": "weibo" if i < 3 else "test_source",
        "title": "OpenAI GPT-5 发布" if i % 3 == 0 else "不同事件 %d" % i,
        "url": "https://example.com/%d" % i,
        "text": "测试文本 %d" % i,
        "pub_date": B.NOW_BJ.isoformat(),
        "retrieval_score": 1.0 / (i + 1),
        "final_score": 0,
        "vec_similarity": 0.8 - i * 0.02,
    })
events = B._assemble_events(mock_retrieved)
print("事件: %d 个" % len(events))
assert len(events) > 0, "应至少有 1 个事件"
for i, e in enumerate(events[:5]):
    print("  事件 %d: %s (%d chunks, 源: %s)" % (
        i + 1, e["label"][:40], len(e["items"]), ", ".join(e["source_types"])))
print("[PASS] 事件组装产出 %d 个事件" % len(events))

# ── 测试 8: 打分排序 ──
print("\n=== 测试 8: 综合打分 ===")
events = B._score_events(events, hot_snapshot)
print("排序后事件:")
for i, e in enumerate(events[:5]):
    print("  %d. [%.1f分] %s (共振: %s, 源: %s)" % (
        i + 1, e["score"], e["label"][:40],
        e.get("resonance", ""), ", ".join(e["source_types"])))
assert all(events[i]["score"] >= events[i+1]["score"]
           for i in range(len(events)-1)), "应按分数降序排列"
print("[PASS] 打分排序正确")

# ── 测试 9: JSON 输出 ──
print("\n=== 测试 9: JSON 输出 ===")
B._write_insight_json(events, "测试主题导语", False)
assert os.path.exists(B.INSIGHT_FILE), "daily-insight.json 应已生成"
with open(B.INSIGHT_FILE, "r", encoding="utf-8") as f:
    insight = json.load(f)
print("日期: %s" % insight.get("date"))
print("主题: %s" % insight.get("theme"))
print("事件数: %d" % len(insight.get("events", [])))
assert insight.get("date") == B.NOW_BJ.strftime("%Y-%m-%d")
assert insight.get("theme") == "测试主题导语"
assert len(insight.get("events", [])) > 0
# 验证 articles 字段
evt0 = insight["events"][0]
assert "articles" in evt0, "事件应包含 articles 字段"
print("articles 字段: %d 条" % len(evt0.get("articles", [])))
print("[PASS] JSON 输出格式正确")

# ── 测试 10: 历史留存 + 页面 ──
print("\n=== 测试 10: 历史留存 + 页面 ===")
B._update_history(events, "测试主题")
assert os.path.exists(B.HISTORY_FILE), "daily_insight_history.json 应已生成"
with open(B.HISTORY_FILE, "r", encoding="utf-8") as f:
    history = json.load(f)
print("历史天数: %d" % len(history.get("days", [])))
assert len(history.get("days", [])) >= 1

B._build_history_html()
assert os.path.exists(B.HISTORY_HTML), "daily-insight-history.html 应已生成"
size = os.path.getsize(B.HISTORY_HTML)
print("历史页面大小: %d bytes" % size)
assert size > 100
print("[PASS] 历史留存 + 页面正确")

# ── 测试 11: AI 日报注入 ──
print("\n=== 测试 11: AI 日报注入 ===")
if os.path.exists("ai-daily.html"):
    B._inject_into_ai_daily(events, "测试主题")
    with open("ai-daily.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert "daily-insight-start" in html, "应包含注入标记"
    assert "每日深度洞察" in html, "应包含板块标题"
    print("[PASS] AI 日报注入成功")
else:
    print("[SKIP] ai-daily.html 不存在")

# ── 测试 12: RAGAS 质量评估 ──
print("\n=== 测试 12: RAGAS 质量评估 ===")
# 测试 _build_ragas_context
mock_retrieved_ragas = []
for i in range(10):
    mock_retrieved_ragas.append({
        "chunk_id": "chunk_%05d" % i,
        "source_type": "rss" if i < 5 else "hot",
        "source": "test_source",
        "title": "测试标题 %d" % i,
        "text": "这是测试文本 %d，用于验证 RAGAS 上下文构建。" % i,
        "retrieval_score": 1.0 / (i + 1),
    })
context = B._build_ragas_context(events, mock_retrieved_ragas)
assert len(context) > 0, "RAGAS 上下文应非空"
assert "测试标题" in context, "RAGAS 上下文应包含 chunk 标题"
print("RAGAS 上下文: %d 字符" % len(context))

# 测试 _evaluate_report_quality 无 LLM 时的降级
result_no_llm = B._evaluate_report_quality(None, events, "测试", context)
assert result_no_llm["overall"] == 0.5, "无 LLM 时应返回默认分"
print("无 LLM 降级评分: overall=%.2f" % result_no_llm["overall"])

# 测试 _ragas_evaluate_and_correct 无 LLM 时跳过
clusters_ragas, eval_ragas = B._ragas_evaluate_and_correct(
    None, events, "测试", mock_retrieved_ragas, {})
assert eval_ragas == {}, "无 LLM 时 eval_result 应为空"
assert clusters_ragas == events, "无 LLM 时 clusters 不应改变"
print("无 LLM 降级: 跳过 RAGAS 评估")

# 测试 _write_insight_json 带 RAGAS 评分
B._write_insight_json(events, "测试主题", False, {
    "overall": 0.82, "context_coverage": 0.78,
    "faithfulness": 0.85, "relevance": 0.83,
    "feedback": "测试反馈",
})
with open(B.INSIGHT_FILE, "r", encoding="utf-8") as f:
    insight_ragas = json.load(f)
assert "quality" in insight_ragas, "输出 JSON 应包含 quality 字段"
assert insight_ragas["quality"]["overall"] == 0.82, "quality.overall 应为 0.82"
print("RAGAS 评分写入 JSON: overall=%.2f" % insight_ragas["quality"]["overall"])
print("[PASS] RAGAS 质量评估功能正确")

# ── 测试 7: 增量向量缓存 ──
print("\n=== 测试 7: 增量向量缓存 ===")

# 7a) content_hash 稳定性：相同输入产生相同 hash
B.NOW_BJ = B._now_bj()
test_chunks_fn = B._chunk_documents
rss_item = [{"title": "测试标题", "link": "https://a.com/1", "source": "测试源",
             "source_key": "test_src", "summary": "这是测试内容。", "full_content": "",
             "pub_date": "2026-09-17T10:00:00+08:00", "cat": "tech"}]
chunks_a = B._chunk_documents(rss_item, [], [], [])
chunks_b = B._chunk_documents(rss_item, [], [], [])
assert len(chunks_a) > 0, "应产生至少一个 chunk"
assert chunks_a[0]["content_hash"] == chunks_b[0]["content_hash"], \
    "相同输入应产生相同 content_hash"
print("content_hash 稳定性: %s" % chunks_a[0]["content_hash"])

# 7b) content_hash 区分性：不同输入产生不同 hash
rss_item_diff = [{"title": "完全不同的标题", "link": "https://b.com/2",
                  "source": "其他源", "source_key": "other",
                  "summary": "这是不同的内容。", "full_content": "",
                  "pub_date": "2026-09-17T11:00:00+08:00", "cat": "tech"}]
chunks_diff = B._chunk_documents(rss_item_diff, [], [], [])
assert chunks_a[0]["content_hash"] != chunks_diff[0]["content_hash"], \
    "不同输入应产生不同 content_hash"
print("content_hash 区分性: %s vs %s" % (chunks_a[0]["content_hash"], chunks_diff[0]["content_hash"]))
print("[PASS] content_hash 计算正确")

# 7c) 向量缓存 round-trip（save → load 数据一致）
if B.FAISS_AVAILABLE:
    import numpy as np
    import tempfile
    import shutil
    # 创建临时目录测试
    orig_meta = B.FAISS_META_FILE
    orig_vec = B.VECTOR_CACHE_FILE
    tmp_dir = tempfile.mkdtemp()
    try:
        B.FAISS_META_FILE = os.path.join(tmp_dir, "test_chunks.json")
        B.VECTOR_CACHE_FILE = os.path.join(tmp_dir, "test_vectors.npy")
        # 构造测试数据
        test_chunks = [
            {"chunk_id": "c0", "source_type": "rss", "source": "s",
             "title": "t1", "url": "", "text": "hello world",
             "pub_date": "2026-09-17T10:00:00+08:00",
             "content_hash": "abc123def456"},
            {"chunk_id": "c1", "source_type": "hot", "source": "s2",
             "title": "t2", "url": "", "text": "test data",
             "pub_date": "", "content_hash": "xyz789abc012"},
        ]
        test_vecs = np.random.rand(2, B.EMBED_DIM).astype(np.float32)
        test_model = "test/model"
        # 保存
        B._save_vector_cache(test_chunks, test_vecs, test_model)
        # 加载
        loaded_chunks, loaded_vecs, loaded_model = B._load_vector_cache()
        assert len(loaded_chunks) == 2, "加载 chunks 数量应为 2"
        assert loaded_vecs.shape == (2, B.EMBED_DIM), "加载向量 shape 应为 (2, %d)" % B.EMBED_DIM
        assert loaded_model == test_model, "加载模型名应为 %s" % test_model
        assert loaded_chunks[0]["content_hash"] == "abc123def456", "content_hash 应保留"
        np.testing.assert_array_almost_equal(loaded_vecs, test_vecs, decimal=5)
        print("向量缓存 round-trip: chunks=%d, shape=%s, model=%s" % (
            len(loaded_chunks), loaded_vecs.shape, loaded_model))
        print("[PASS] 向量缓存 round-trip 正确")
    finally:
        B.FAISS_META_FILE = orig_meta
        B.VECTOR_CACHE_FILE = orig_vec
        shutil.rmtree(tmp_dir, ignore_errors=True)
else:
    print("[SKIP] FAISS 不可用，跳过向量缓存 round-trip 测试")

# 7d) 常量验证
assert B.INSIGHT_RSS_HOURS == 168, "INSIGHT_RSS_HOURS 应为 168 (7天)"
assert B.MAX_EMBED_CHUNKS == 30000, "MAX_EMBED_CHUNKS 应为 30000"
assert B.BM25_WINDOW == 10000, "BM25_WINDOW 应为 10000"
print("常量检查: INSIGHT_RSS_HOURS=%d, MAX_EMBED_CHUNKS=%d, BM25_WINDOW=%d" % (
    B.INSIGHT_RSS_HOURS, B.MAX_EMBED_CHUNKS, B.BM25_WINDOW))
print("[PASS] 常量配置正确")

# ── 测试 12: BM25 窗口化 ──
print("\n=== 测试 12: BM25 窗口化 ===")
if B.FAISS_AVAILABLE and B.BM25_AVAILABLE:
    import numpy as np

    mock_chunks = []
    mock_vecs = []
    for i in range(5000):
        mock_chunks.append({
            "chunk_id": "hot_%05d" % i,
            "source_type": "hot",
            "source": "weibo",
            "title": "热榜条目 %d" % i,
            "url": "", "text": "热榜测试文本 关键词Alpha %d" % i,
            "pub_date": "",
            "content_hash": "h_%016d" % i,
        })
        mock_vecs.append(np.random.rand(B.EMBED_DIM).astype(np.float32))
    for i in range(10000):
        mock_chunks.append({
            "chunk_id": "rss_%05d" % i,
            "source_type": "rss",
            "source": "test_feed",
            "title": "RSS条目 %d" % i,
            "url": "", "text": "RSS测试文本 关键词Beta %d" % i,
            "pub_date": "2026-09-%02dT10:00:00+08:00" % (1 + i % 7),
            "content_hash": "r_%016d" % i,
        })
        mock_vecs.append(np.random.rand(B.EMBED_DIM).astype(np.float32))

    all_vecs = np.vstack(mock_vecs)
    norms = np.linalg.norm(all_vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    all_vecs = all_vecs / norms
    index = B._build_faiss_index(all_vecs)

    queries = ["关键词Alpha 热榜搜索"]
    results = B._hybrid_retrieve(index, mock_chunks, queries, top_k=80)

    hot_hits = [r for r in results if r["source_type"] == "hot"]
    print("总检索结果: %d, 其中 hot: %d, rss: %d" % (
        len(results), len(hot_hits), len(results) - len(hot_hits)))
    assert len(results) > 0, "应有检索结果"
    assert len(hot_hits) > 0, "BM25 应能匹配 hot chunks 的关键词Alpha"
    print("BM25_WINDOW=%d, 总 chunks=%d" % (B.BM25_WINDOW, len(mock_chunks)))
    print("[PASS] BM25 窗口化检索正确")
else:
    print("[SKIP] FAISS/BM25 不可用，跳过窗口化测试")

print("\n" + "=" * 50)
print("全部测试通过！(RAG 管线 + RAGAS + 增量向量缓存)")
