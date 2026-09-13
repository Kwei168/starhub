# Insight Engine 数据时效性修复 Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 insight engine 分析链路中因零时间过滤和无日期条目永久累积导致的话题聚类被单一信源主导的问题。

**Architecture:** 在 `build_rss_aggregator.py` 的 `_accumulate_history()` 和 `insight_engine.py` 的 `load_documents()` / `_evaluate_and_correct()` 三处增加统一的时间过滤逻辑，无 `pub_date` 条目改用 `first_seen` 作为时间基准。同时将 GitHub Trending 数据接入分析链路。

**Tech Stack:** Python, LlamaIndex, GitHub Actions

---

## 问题根因

1. **`load_documents()` 零时间过滤**：接收 `_rss_history`（6646 条全量）后不做任何时间判断，直接截取前 N 条，导致 1292 条超 72h 的过期数据参与分析。
2. **无 `pub_date` 条目永久驻留**：`_accumulate_history()` 中无日期条目默认赋值为当前时间，永远不被 72h cutoff 过滤。Tiny Projects 的 15 条无日期条目永久累积，形成最大话题簇（count=15），主导 LLM narrative 输出。
3. **`trending_data` 恒为空**：`_run_analysis()` 硬编码 `trending_data=[]`，GitHub Trending 430 条数据完全缺失。
4. **`_evaluate_and_correct` 检索上下文无时间过滤**：RAGAS 修正闭环基于可能被污染的话题簇操作。

## 修复方案

### Fix 1: `_accumulate_history()` 无日期条目使用 `first_seen`

**文件**: `build_rss_aggregator.py` L233-246

当前逻辑：无 `pub_date` 时默认 `pd_bj = now_bj`（当前时间），导致条目永不过期。

修改为：无 `pub_date` 时使用 `first_seen` 字段作为时间基准。`first_seen` 是条目首次被抓取的时间，更合理地反映条目的"年龄"。

```python
# 修改前
pd_bj = now_bj.replace(tzinfo=None)  # 默认当前时间

# 修改后
pd_bj = now_bj.replace(tzinfo=None)
if pd_str:
    try:
        pd = datetime.datetime.fromisoformat(pd_str)
        if pd.tzinfo:
            pd_bj = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
        else:
            pd_bj = pd
    except ValueError:
        pass
else:
    # 无 pub_date 时使用 first_seen（首次抓取时间）作为时间基准
    fs_str = _rss_history.get(link, {}).get("first_seen", "")
    if fs_str:
        try:
            fs = datetime.datetime.fromisoformat(fs_str)
            pd_bj = fs
        except ValueError:
            pass  # first_seen 也解析失败，保持当前时间（仅首次出现的新条目）
```

裁剪逻辑（L267-280）也需同步修改，无 `pub_date` 条目使用 `first_seen` 判断是否过期。

### Fix 2: `load_documents()` 增加 72h 时间过滤

**文件**: `insight_engine.py` L226-295

当前逻辑：直接遍历 `rss_history.values()` 取前 N 条，无时间过滤。

修改为：在构建 `rss_docs` 时过滤超 72h 的条目。无 `pub_date` 条目使用 `first_seen`。

```python
from datetime import datetime, timezone, timedelta

_RSS_HISTORY_HOURS = 72

def _is_entry_recent(item, hours=_RSS_HISTORY_HOURS):
    """判断 RSS 条目是否在时间窗口内。无 pub_date 时使用 first_seen。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    cutoff = now - timedelta(hours=hours)
    
    pub_str = item.get("pub_date") or item.get("published") or item.get("date")
    fs_str = item.get("first_seen", "")
    
    for ts_str in [pub_str, fs_str]:
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
            if dt >= cutoff:
                return True
        except (ValueError, TypeError):
            continue
    return False  # 两个时间都无法解析，视为过期
```

在 `load_documents()` 的 RSS 遍历中应用：
```python
for item in rss_items:
    if isinstance(item, dict):
        if not _is_entry_recent(item):
            continue  # 跳过超 72h 的条目
        ...
```

### Fix 3: 传入实际 Trending 数据

**文件**: `build_rss_aggregator.py` L6265

当前：`trending_data=[]`

修改为：读取 `trending_snapshot.json` 并传入。

```python
# 在 _run_analysis 调用前读取
trending_data = {}
try:
    with open("trending_snapshot.json", "r", encoding="utf-8") as f:
        trending_data = json.load(f)
except:
    pass

ie_result = insight_engine.run_analysis(
    ...
    trending_data=trending_data,
    ...
)
```

### Fix 4: `_evaluate_and_correct` 检索上下文时间过滤

**文件**: `insight_engine.py` `_evaluate_and_correct()` 函数

在构建 `context_parts` 时，对 cluster items 应用 `_is_entry_recent()` 过滤。由于 topic_clusters 的 items 是纯文本字符串（非 dict），需要在 `run_analysis` 中保留原始 item 引用的映射，或在构建 topic_clusters 时附加时间戳。

**简化方案**：由于 topic_clusters 的 items 来自已过滤的 documents（Fix 2 已过滤），`_evaluate_and_correct` 的检索上下文会自动继承过滤结果，无需额外修改。

## 测试策略

- 更新 `test_insight_engine.py` 中 `TestDocuments` 相关测试，验证 `_is_entry_recent()` 对 pub_date / first_seen / 无日期三种情况的过滤行为
- 验证 `load_documents()` 在混合新旧数据时正确过滤
- 确保现有 72 个测试全部通过

## 验收标准

1. Tiny Projects 无日期条目不再永久累积（被 first_seen 时间基准正确过滤）
2. `load_documents()` 输入数据 100% 在 72h 窗口内
3. GitHub Trending 数据出现在分析输入中
4. 72/72 测试通过
5. 线上构建后 `narrative` 不再被单一信源主导
