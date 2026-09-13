# Insight Engine 数据时效性修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 insight engine 分析链路中因零时间过滤和无日期条目永久累积导致的话题聚类被单一信源主导的问题。

**Architecture:** 在 `build_rss_aggregator.py` 的 `_accumulate_history()` 和 `insight_engine.py` 的 `load_documents()` 两处增加时间过滤逻辑，无 `pub_date` 条目改用 `first_seen` 作为时间基准。同时将 GitHub Trending 数据接入分析链路。

**Tech Stack:** Python, LlamaIndex, GitHub Actions

---

### Task 1: `insight_engine.py` — 新增 `_is_entry_recent()` + `load_documents()` 时间过滤

**Files:**
- Modify: `insight_engine.py`

- [ ] **Step 1: 添加 `_is_entry_recent()` 辅助函数**

在 `insight_engine.py` 的 `load_documents()` 函数之前（约 L225）添加：

```python
_RSS_HISTORY_HOURS = 72

def _is_entry_recent(item, hours=_RSS_HISTORY_HOURS):
    """判断 RSS 条目是否在时间窗口内。优先 pub_date，回退 first_seen。"""
    now = datetime.now(BJT)
    cutoff = now - timedelta(hours=hours)
    pub_str = item.get("pub_date") or item.get("published") or item.get("date")
    fs_str = item.get("first_seen", "")
    for ts_str in [pub_str, fs_str]:
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BJT)
            if dt >= cutoff:
                return True
        except (ValueError, TypeError):
            continue
    return False
```

- [ ] **Step 2: 修改 `load_documents()` RSS 遍历逻辑**

在 `load_documents()` 的 RSS items 遍历中（约 L253），在 `if isinstance(item, dict):` 之后添加时间过滤：

```python
if isinstance(item, dict):
    if not _is_entry_recent(item):
        continue  # 跳过超 72h 的条目
    title = item.get("title", "")
    ...
```

- [ ] **Step 3: 添加测试**

在 `test_insight_engine.py` 的 `TestDocuments` 类中添加：

```python
def test_is_entry_recent_pub_date(self):
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    self.assertTrue(_is_entry_recent({"pub_date": recent}))

def test_is_entry_recent_first_seen_fallback(self):
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    self.assertTrue(_is_entry_recent({"first_seen": recent}))

def test_is_entry_recent_expired(self):
    from datetime import datetime, timezone, timedelta
    old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    self.assertFalse(_is_entry_recent({"pub_date": old, "first_seen": old}))

def test_is_entry_recent_no_dates(self):
    self.assertFalse(_is_entry_recent({}))

def test_load_documents_filters_old_rss(self):
    old = "2026-01-01T00:00:00+08:00"
    recent = "2026-09-13T10:00:00+08:00"
    rss = {"a": {"title": "old", "pub_date": old}, "b": {"title": "new", "pub_date": recent}}
    docs = load_documents([], rss, [], max_documents=100)
    texts = [d.text for d in docs]
    self.assertTrue(any("new" in t for t in texts))
    self.assertFalse(any("old" in t for t in texts))
```

- [ ] **Step 4: 运行测试**

Run: `pytest test_insight_engine.py -v --tb=short`
Expected: 77/77 PASSED (72 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add insight_engine.py test_insight_engine.py
git commit -m "fix: load_documents() 增加72h时间过滤，无pub_date条目使用first_seen基准"
```

---

### Task 2: `build_rss_aggregator.py` — 无日期条目使用 `first_seen` + 传入 Trending 数据

**Files:**
- Modify: `build_rss_aggregator.py`

- [ ] **Step 1: 修改 `_accumulate_history()` 合并逻辑（L233-246）**

将无 `pub_date` 时的默认时间从 `now_bj` 改为 `first_seen`：

```python
# 在 pd_str 解析失败或为空时
else:
    # 无 pub_date 时使用 first_seen（首次抓取时间）作为时间基准
    fs_str = _rss_history.get(link, {}).get("first_seen", "")
    if fs_str:
        try:
            fs = datetime.datetime.fromisoformat(fs_str)
            pd_bj = fs.replace(tzinfo=None) if fs.tzinfo else fs
        except ValueError:
            pass  # first_seen 也解析失败，保持当前时间（仅首次出现的新条目）
```

- [ ] **Step 2: 修改 `_accumulate_history()` 裁剪逻辑（L267-280）**

同步修改裁剪逻辑，无 `pub_date` 条目使用 `first_seen` 判断是否过期：

```python
for link, item in _rss_history.items():
    pd_str = item.get("pub_date", "")
    pd_bj = now_bj.replace(tzinfo=None)
    if pd_str:
        try:
            pd = datetime.datetime.fromisoformat(pd_str)
            if pd.tzinfo:
                pd_bj = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
            else:
                pd_bj = pd
        except ValueError:
            # pub_date 解析失败，使用 first_seen
            fs_str = item.get("first_seen", "")
            if fs_str:
                try:
                    fs = datetime.datetime.fromisoformat(fs_str)
                    pd_bj = fs.replace(tzinfo=None) if fs.tzinfo else fs
                except ValueError:
                    pass
    if pd_bj < cutoff:
        expired.append(link)
```

- [ ] **Step 3: 传入 Trending 数据（L6251-6269）**

在 `_run_analysis()` 函数内，读取 `trending_snapshot.json` 并传入：

```python
# 在 insight_engine.run_analysis() 调用前
trending_data = {}
try:
    with open("trending_snapshot.json", "r", encoding="utf-8") as _f:
        trending_data = json.load(_f)
except Exception:
    pass
```

然后将 `trending_data=[]` 改为 `trending_data=trending_data`。

- [ ] **Step 4: Commit**

```bash
git add build_rss_aggregator.py
git commit -m "fix: _accumulate_history无日期条目用first_seen基准 + 传入trending数据"
```

---

### Task 3: 推送并触发线上构建验证

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: Trigger build**

```bash
gh workflow run update.yml
```

- [ ] **Step 3: Wait for build and verify**

Pull latest snapshot and verify:
1. `narrative` 不再被 Tiny Projects 主导
2. `topic_clusters` 中无过期话题簇
3. `core_trends` / `rss_insights` / `narrative` 内容不同且基于新鲜数据
