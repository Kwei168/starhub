# 每日洞察系统 CI 构建修复 Spec（v2）

> 日期: 2026-09-17
> 触发: Run #35180280842 构建评估发现 6 项问题
> 范围: `build_daily_insight.py` + `build_rss_aggregator.py`
> 约束: `insight_engine.py` 零修改

---

## 问题总览

| ID | 优先级 | 问题 | 根因 | 影响 |
|----|--------|------|------|------|
| FIX-1 | P0 | 热度信号全为零 | heat 仅看 cluster 内 hot chunks，但热榜 chunks 不进簇 | heat=0 → 排序失真 |
| FIX-2 | P0 | RAGAS 评估降级 0.50 | LLM 输出 JSON 解析失败（max_tokens 不足） | 自我修正闭环断裂 |
| FIX-3 | P1 | 跨源事件重复 | 语义阈值 0.75 对跨源标题不够包容 | 用户看到重复内容 |
| FIX-4 | P1 | 深度解读内容串位 | cluster items 混入无关 chunks | faithfulness 暴跌 |
| FIX-5 | P1 | resonance 字段全空 | 与 FIX-1 同源：无 hot chunks 则无共振 | 前端共振标签缺失 |
| FIX-6 | P2 | rss_history.json 超 50MB | 72h 累积无分块 | GitHub 警告、仓库膨胀 |

---

## FIX-1 + FIX-5: 双参照系热度模型 (P0)

### 根因

`_score_clusters()` L1070-1092 通过检查 cluster items 中 `source_type == "hot"` 计算热度。但热榜 chunks 是短标题，embedding 与长文章差异大，0.75 语义阈值无法合并 → 热榜 chunks 不进簇 → `hot_platforms` 空集 → heat=0, resonance=""。

### 数据源盘点

| 数据源 | 条数 | 热度字段 | 分类字段 | 信号特征 |
|--------|------|----------|----------|----------|
| AGI Hunt | ~1024（12 频道） | `hot` 0-500+（Reddit 互动） | `channel` 12 个 | 全球 AI 社区信号，天然数值大 |
| AIHOT | 100 | `score` 10-75（编辑评分） | `category` 63% 为空 | 全球编辑信号，天然数值大 |
| 热榜快照 | 400（40 平台×10） | `rank` 1-10 | `platform` 匹配 T1/T2 | 中文生态跨平台覆盖 |
| RSS | ~18000 | tier 权重 1.0-2.0 | `source_key` → tier | 中文生态信源深度 |

### 设计：双参照系模型

不是简单累加所有热度，而是构建**两个坐标系**对比：

```
参照系 A: 全球 AI 信号 = f(AGI Hunt hot, AIHOT score)
参照系 B: 中文生态信号 = f(热榜平台覆盖, RSS tier)
对比 → 事件定位 + heat + resonance
```

**对比产生的洞察方向**：

| 模式 | A 高 + B 高 | A 高 + B 低 | A 低 + B 高 |
|------|-------------|-------------|-------------|
| 含义 | 全球+中文双热 | 国际热点中文未跟进 | 中文热议国际无信号 |
| 洞察价值 | 今日主线候选 | 破茧栏候选（信息增量） | 本土议题 |
| resonance | `breakout` | `tech_hot` / `niche` | `consumer` / `niche` |

### 归一化：子信号 cap 到 5 分

AGI Hunt/AIHOT 天然数值大，必须归一化防止垄断：

```python
def _compute_dual_heat(cluster, hot_snapshot):
    """双参照系热度计算。返回 (heat, score_a, score_b, hot_platforms, resonance)。"""
    
    # ── 参照系 A: 全球 AI 信号 (0-10) ──
    agihunt_contrib = 0.0
    aihot_contrib = 0.0
    for it in cluster.get("items", []):
        src = it.get("source_type", "")
        if src == "agihunt":
            agihunt_contrib += it.get("hot", 0) / 100.0   # hot=500→5.0
        elif src == "aihot":
            aihot_contrib += it.get("score", 0) / 15.0    # score=75→5.0
    score_a = min(10.0, min(5.0, agihunt_contrib) + min(5.0, aihot_contrib))
    
    # ── 参照系 B: 中文生态信号 (0-10) ──
    hot_platforms = set()
    for it in cluster.get("items", []):
        if it.get("source_type") == "hot":
            hot_platforms.add(it.get("source", ""))
    
    # 兜底：全局热榜反查（热榜 chunks 可能不在簇中）
    if not hot_platforms and hot_snapshot:
        cluster_tokens = _tokenize_title(cluster.get("label", ""))
        for platform in hot_snapshot:
            plat = platform.get("platform", "")
            for item in platform.get("items", []):
                item_tokens = _tokenize_title(item.get("title", ""))
                if len(cluster_tokens & item_tokens) >= 2:
                    hot_platforms.add(plat)
                    break
    
    t1 = sum(1 for p in hot_platforms if p in HOT_T1)
    t2 = sum(1 for p in hot_platforms if p in HOT_T2)
    t3 = len(hot_platforms) - t1 - t2
    hot_contrib = min(5.0, t1 * 1.5 + t2 * 1.0 + t3 * 0.5)
    
    rss_contrib = 0.0
    for it in cluster.get("items", []):
        if it.get("source_type") == "rss":
            tier = _RSS_TIER_MAP.get(it.get("source_key", ""), 3)
            rss_contrib += {1: 1.5, 2: 1.0, 3: 0.5}.get(tier, 0.5)
    rss_contrib = min(5.0, rss_contrib)
    
    score_b = min(10.0, hot_contrib + rss_contrib)
    
    # ── 综合 heat (0-10) ──
    heat = round(min(10.0, score_a * 0.5 + score_b * 0.5), 1)
    
    # ── resonance 分类 ──
    a_high = score_a >= 3.0
    b_high = score_b >= 3.0
    if a_high and b_high:
        resonance = "breakout"
    elif a_high and not b_high:
        resonance = "tech_hot" if t1 < 2 else "niche"
    elif not a_high and b_high:
        resonance = "consumer" if t1 > 0 else "niche"
    elif hot_platforms:
        resonance = "niche"
    else:
        resonance = ""
    
    return heat, score_a, score_b, hot_platforms, resonance
```

### 修改点

1. `_score_clusters()` 签名改为 `_score_clusters(clusters, hot_snapshot)`
2. 替换 L1070-1095 的 hot_platforms/heat/resonance 计算
3. 调用处 L2830 附近传入 `hot_snapshot`
4. signal 字段新增 `score_a`, `score_b`（供前端/调试用）

### 验证标准

- 至少 3 个事件 `heat > 0`
- 至少 1 个事件 `resonance` 非空
- `score_a` 和 `score_b` 均在 0-10 范围

---

## FIX-2: RAGAS 评估 JSON 解析容错 (P0)

### 根因

`_evaluate_report_quality()` L1755 使用 `max_tokens=500`。LLM 在 JSON 前输出推理文本或 feedback 字段过长 → 输出截断 → `_parse_json()` 返回 None → 降级 0.50。

模型支持 1M 上下文（Agnes/Mimo），prompt 体积不是问题。

### 修复方案

| 措施 | 说明 |
|------|------|
| prompt 体积 | **保持不动**（10K 上下文 + 8 事件） |
| max_tokens | 500 → **3000** |
| 系统提示 | 追加 **"直接输出 JSON，不要任何解释、前言或后记"** |
| JSON 容错 | `_parse_json` 失败后：提取 `{...}` 段 → 补全括号 → 再解析 |

### 修改点

1. L1755: `max_tokens=500` → `max_tokens=3000`
2. L1752: system prompt 追加 JSON-only 约束
3. L1756 后: 增加 JSON 截断修复逻辑

```python
def _robust_parse_json(text):
    """增强 JSON 解析：处理截断、前后缀噪音。"""
    parsed = _parse_json(text)
    if isinstance(parsed, dict):
        return parsed
    
    # 提取 { 到最后一个 } 之间的内容
    if text:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            candidate = text[start:end+1]
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

### 验证标准

- RAGAS eval 不再返回全 0.50（除非 LLM 真的不可用）
- 日志中不出现 "评估解析失败"

---

## FIX-3: Phase 1 后跨源去重 (P1)

### 根因

语义聚类阈值 0.75 对跨源标题措辞差异不够包容：
- "Anthropic用Claude Code从零重写Claude Design" (RSS)
- "Anthropic用自研工具重写Claude Design" (AIHOT)

### 修复方案

Phase 1 LLM 已为每个事件赋值 `label` + `category`。利用这些结构化信息做二次去重：

```python
def _deduplicate_after_phase1(clusters):
    """Phase 1 后去重：合并同 category 且标签高度相似的相邻事件。"""
    if len(clusters) < 2:
        return clusters
    merged = []
    used = set()
    for i in range(len(clusters)):
        if i in used:
            continue
        for j in range(i + 1, len(clusters)):
            if j in used:
                continue
            ci, cj = clusters[i], clusters[j]
            if (ci.get("category") == cj.get("category")
                and _jaccard(_tokenize_title(ci.get("label", "")),
                             _tokenize_title(cj.get("label", ""))) >= 0.5):
                ci["items"].extend(cj["items"])
                ci["source_types"] |= cj.get("source_types", set())
                ci["score"] = max(ci.get("score", 0), cj.get("score", 0))
                if cj.get("score", 0) > ci.get("score", 0):
                    ci["label"] = cj.get("label", ci.get("label", ""))
                    ci["summary"] = cj.get("summary", ci.get("summary", ""))
                used.add(j)
        merged.append(ci)
    return merged
```

### 修改点

主管线 L2853 后（Phase 1 字段赋值后）插入调用。

### 验证标准

- 不再出现同 category 下标签高度相似的重复事件

---

## FIX-4: Phase 2 前素材相关性过滤 (P1)

### 根因

cluster 中混入无关 chunks → LLM 基于无关素材生成 deep_analysis → 内容串位。

### 修复方案

Phase 2 前，按 Phase 1 label 的 tokens 过滤 cluster items：

```python
def _filter_cluster_items(cluster, phase1_label):
    """过滤 cluster 中与 Phase 1 label 不相关的 items。"""
    if not phase1_label:
        return cluster
    label_tokens = _tokenize_title(phase1_label)
    if not label_tokens:
        return cluster
    
    filtered = []
    for it in cluster.get("items", []):
        title = it.get("title", "")
        text = it.get("text", "")[:200]
        item_tokens = _tokenize_title(title + " " + text)
        if len(label_tokens & item_tokens) >= 1:
            filtered.append(it)
    
    if not filtered and cluster.get("items"):
        filtered = cluster["items"][:1]  # 至少保留 1 个
    
    cluster["items"] = filtered
    return cluster
```

### 修改点

Phase 2 循环中（L2874 前）调用过滤。

### 验证标准

- deep_analysis 内容与事件 label 主题一致
- RAGAS faithfulness 分数提升

---

## FIX-6: rss_history.json 分块存储 (P2)

### 根因

72h 累积文章历史 61.41 MB，超过 GitHub 50MB 建议上限。主因是 `full_content` 字段。

### 修复方案

复用 `build_rss_aggregator.py` 中 `_split_data_chunks()` 的分块思路：

```python
def _save_history_chunked():
    """分块保存文章历史，避免单文件超 40MB。"""
    MAX_SIZE = 40 * 1024 * 1024
    data = json.dumps(_rss_history, ensure_ascii=False, separators=(",", ":"))
    total_bytes = len(data.encode("utf-8"))
    
    if total_bytes <= MAX_SIZE:
        _atomic_write_json(RSS_HISTORY_FILE, _rss_history, ensure_ascii=False)
        return
    
    n_chunks = (total_bytes // MAX_SIZE) + 1
    buckets = [{} for _ in range(n_chunks)]
    for link, record in _rss_history.items():
        bucket_idx = int(hashlib.md5(link.encode()).hexdigest()[:8], 16) % n_chunks
        buckets[bucket_idx][link] = record
    
    for i, bucket in enumerate(buckets):
        _atomic_write_json("rss_history_%d.json" % i, bucket, ensure_ascii=False)
    
    _atomic_write_json("rss_history_index.json",
                       {"chunks": n_chunks, "total": len(_rss_history)},
                       ensure_ascii=False)

def _load_history_chunked():
    """加载分块的文章历史，向后兼容旧格式。"""
    index_file = "rss_history_index.json"
    if os.path.exists(index_file):
        index = json.load(open(index_file, "r", encoding="utf-8"))
        merged = {}
        for i in range(index.get("chunks", 0)):
            fname = "rss_history_%d.json" % i
            if os.path.exists(fname):
                merged.update(json.load(open(fname, "r", encoding="utf-8")))
        return merged
    if os.path.exists(RSS_HISTORY_FILE):
        return json.load(open(RSS_HISTORY_FILE, "r", encoding="utf-8"))
    return {}
```

### 修改点

1. `_save_history()` → 调用 `_save_history_chunked()`
2. 加载处（L290-297）→ 调用 `_load_history_chunked()`
3. `.gitignore` 添加 `rss_history_*.json` + `rss_history_index.json`
4. Prune 步骤添加 `rss_history_*.json` 清理

### 验证标准

- 无单文件超过 50MB
- 向后兼容旧 `rss_history.json` 格式

---

## FIX-7: 端到端 LLM 调用追踪日志

### 现状

现有 `_build_tracking_entry()` 仅记录汇总级统计（RAGAS 分数 + 源计数 + 元信息），无法用于提示词调参、质量回溯或管线迭代。

### 设计：PipelineTracer 类

在 `build_daily_insight.py` 中新增 `PipelineTracer` 类，贯穿主管线各阶段收集追踪数据，最终输出为结构化 JSONL。

```python
class PipelineTracer:
    """端到端 LLM 调用追踪器。"""
    
    def __init__(self):
        self.stages = {}       # stage_name -> stage_data
        self.llm_calls = []    # 每次 LLM 调用的完整记录
        self.meta = {}         # 构建元信息
    
    def set_meta(self, **kwargs):
        """设置构建元信息。"""
        self.meta.update(kwargs)
    
    def trace_queries(self, rss_count, hot_count, aihot_count, agihunt_count,
                      chunks_total, queries_count, retrieved_top_k):
        """Stage 1: 查询构建。"""
        self.stages["queries"] = {
            "source_counts": {"rss": rss_count, "hot": hot_count,
                              "aihot": aihot_count, "agihunt": agihunt_count},
            "chunks_total": chunks_total,
            "queries_count": queries_count,
            "retrieved_top_k": retrieved_top_k,
        }
    
    def trace_clustering(self, method, threshold, before_count, after_count,
                         events_summary):
        """Stage 2: 聚类与事件组装。"""
        self.stages["clustering"] = {
            "method": method,  # "semantic" | "jaccard"
            "threshold": threshold,
            "before_count": before_count,
            "after_count": after_count,
            "events": events_summary,  # [{label, category, score, resonance,
                                        #   status, items: [{source_type, title}]}]
        }
    
    def trace_llm_call(self, phase, event_idx, prompt_text, model_name,
                       temperature, max_tokens, raw_response, parse_ok,
                       parsed_result, token_usage=None):
        """记录单次 LLM 调用。"""
        self.llm_calls.append({
            "phase": phase,           # "phase1" | "phase2" | "self_review" | "ragas_eval"
            "event_idx": event_idx,   # Phase 2 的事件索引，其他为 None
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_chars": len(prompt_text),
            "prompt_preview": prompt_text[:5000],  # 截断至 5000 字符
            "raw_response_preview": (raw_response or "")[:3000],
            "parse_ok": parse_ok,
            "parsed_summary": parsed_result,  # 精简后的解析结果
            "token_usage": token_usage,
        })
    
    def trace_self_review(self, issues_found, corrected_indices):
        """Stage 5: 自审环节。"""
        self.stages["self_review"] = {
            "issues": issues_found,         # ["事件1 含空话「值得关注」", ...]
            "corrected_indices": corrected_indices,
        }
    
    def trace_ragas(self, iterations_log):
        """Stage 6: RAGAS 评估-修正闭环。"""
        self.stages["ragas"] = {
            "iterations": iterations_log,
            # [{iter, overall, cov, faith, rel, feedback, weak_events,
            #   pre_score, post_score, adopted}]
        }
    
    def trace_bubble(self, read_profile, candidates, selected):
        """Stage 7: 破茧栏选择。"""
        self.stages["bubble_breaker"] = {
            "read_profile": read_profile,    # {category: count}
            "candidates": candidates,        # [{label, intersection_size}]
            "selected": selected,            # [label, ...]
        }
    
    def trace_output(self, event_count, has_analysis_count, inject_html_len):
        """Stage 8: 输出与注入。"""
        self.stages["output"] = {
            "event_count": event_count,
            "has_analysis_count": has_analysis_count,
            "inject_html_chars": inject_html_len,
        }
    
    def flush(self):
        """输出完整追踪日志到 JSONL。"""
        now_bj = _now_bj()
        entry = {
            "ts": now_bj.isoformat(),
            "date": now_bj.strftime("%Y-%m-%d"),
            "meta": self.meta,
            "stages": self.stages,
            "llm_calls": self.llm_calls,
        }
        _log_tracking_entry(entry)
        return entry
```

### 集成点

在 `main()` 中创建 tracer 实例，各阶段调用 trace 方法：

```python
tracer = PipelineTracer()
tracer.set_meta(llm_available=bool(llm), embed_model=embed_model,
                mode=mode, elapsed=0)

# Stage 1: 查询构建后
tracer.trace_queries(...)

# Stage 2: 聚类后
tracer.trace_clustering(...)

# Phase 1 LLM 调用时
tracer.trace_llm_call("phase1", None, prompt, model_name, ...)

# Phase 2 每个事件
tracer.trace_llm_call("phase2", i, prompt, model_name, ...)

# 自审后
tracer.trace_self_review(...)

# RAGAS 评估后
tracer.trace_ragas(...)

# 破茧栏后
tracer.trace_bubble(...)

# 输出后
tracer.trace_output(...)

# 最终写入
tracer.flush()
```

### 安全约束

- prompt 截断至 5000 字符，response 截断至 3000 字符
- 不记录 API key 或任何敏感信息
- 保留最近 500 条追踪记录（在 `_log_tracking_entry` 的 14 天窗口基础上额外限制条数）
- 异常安全：任何 trace 方法失败不影响主流程

### 与现有追踪的关系

- 保留现有 `_build_tracking_entry()` 作为**汇总层**（前端/快速查询用）
- 新增 tracer 输出作为**详情层**（调试/调参用）
- 两者写入同一个 `daily_insight_tracking_history.jsonl`
- tracer 条目通过 `"stages"` 字段存在来区分

### 验证标准

- JSONL 中每条记录包含 `stages` 和 `llm_calls` 字段
- prompt 不超过 5000 字符
- 无 API key 泄露
- 主流程不受 tracer 异常影响

---

## 实施顺序

1. **FIX-1 + FIX-5** — 双参照系热度模型（联动修复）
2. **FIX-2** — RAGAS JSON 容错
3. **FIX-3** — Phase 1 后去重
4. **FIX-4** — Phase 2 前素材过滤
5. **FIX-6** — 历史分块（独立）
6. **FIX-7** — 端到端 LLM 追踪日志（独立）

## 测试计划

- 每个 FIX 对应单元测试
- 集成测试：完整构建流程端到端
- CI 验证：推送后观察下一次定时构建输出
