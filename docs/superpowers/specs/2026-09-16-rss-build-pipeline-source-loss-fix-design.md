# Spec: RSS 构建管线信源丢失修复 + 低频源长尾保留机制

**日期**: 2026-09-16
**状态**: Pending Review
**影响文件**: `build_rss_aggregator.py`、`rss_sources.json`
**关联诊断**: 1000+ 信源配置 → 构建日志显示 800+ 成功 → 实际上线仅 584

---

## 1. 问题陈述

RSS 聚合器配置了 1000+ 个信源，但前端仅展示 584 个有内容的信源，416+ 个信源 items 为空。
经诊断，根因不在 RSS 源本身（抽样 30 个空源 URL，28 个完全可达且有内容），而在构建管线存在三个缺陷。
此外，72h 统一窗口对低频优质源（周报、月刊、播客等）过于激进，需要建立独立的长尾保留机制。

## 2. 根因分析

### Bug 1: 增量模式跳过陷阱

**位置**: `build_rss_aggregator.py` 第 7241–7256 行

**机制**:
1. 增量模式下，T2 源距上次抓取 < 1h / T3 源 < 2h 时跳过抓取
2. 跳过的源从 `_hist_by_key.get(key, [])` 填充 items
3. 若该源**从未成功抓取过**（历史为空），填充结果为 `[]`
4. 失败源不更新 `last_fetch`（仅 `status == "ok"` 时写入，第 7318 行）
5. 但一旦 `last_fetch` 存在（曾成功过一次），后续增量构建持续跳过
6. 若该源后来因域名熔断等原因失败 → 历史过期 → 永远为空

### Bug 2: `_accumulate_history` 数据替换效应

**位置**: `build_rss_aggregator.py` 第 389–396 行

**机制**:
1. 抓取阶段收集 `sources_with_items`（800+ 源有内容）
2. `_accumulate_history` 入口：先将新文章合并进 `_rss_history`（72h 窗口过滤）
3. 第 395 行：创建 `src_map` 时 `items: []`——**刚抓取的数据全部丢弃**
4. 第 508 行：仅从 `_rss_history` 回填 items
5. 返回的 `sources_with_items` 完全由 `_rss_history` 决定

**后果**: 抓取 800+ → 历史中只有 622 个源 → 快照 584 个源有内容

### Bug 3: 构建日志口径不一致

**位置**: `build_rss_aggregator.py` 第 7432 行

`ok_count` 取自抓取阶段（大数字），`total_items` 被历史重组覆写（小数字），日志混用两个口径。

### 设计缺陷: 72h 统一窗口对低频源过于激进

低频优质源（周报、月刊、播客、GitHub Releases 等）发布周期 > 72h，
其文章在下次构建前就已过期裁剪，导致这些源反复「抓取成功 → 文章进历史 → 72h 过期 → 下次构建时历史为空 → 源变空」。
这类源不应被丢弃，而应有独立的长尾保留机制。

## 3. 修复方案

### Fix 1: 增量跳过前检查历史可用性

**文件**: `build_rss_aggregator.py` 第 7241–7256 行

跳过前增加条件——若历史中无该源数据，不跳过，强制重新抓取：

```python
if (now - prev_time).total_seconds() < threshold:
    # 新增：历史为空时不跳过，强制重新抓取以恢复数据
    if not _hist_by_key.get(key):
        _to_fetch.append((_i, src))
        continue
    skipped_count += 1
    ...
```

### Fix 2: `_accumulate_history` 保留抓取结果，历史做补充

**文件**: `build_rss_aggregator.py` 第 389–396 行 + 第 508 行

重组时保留当次抓取结果，历史数据按 link 去重后补充：

```python
# 先建索引：当次抓取的 items
_fetch_items_by_key = {}
for src in sources_with_items:
    seen_links = set()
    items = []
    for it in src.get("items", []):
        link = it.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            items.append(it)
    _fetch_items_by_key[src["key"]] = items

src_map = {}
for src in sources_with_items:
    src_map[src["key"]] = {
        ...,
        "items": list(_fetch_items_by_key.get(src["key"], [])),  # 保留抓取结果
    }
```

回填时按 link 去重（预建索引避免 O(n²)）：

```python
_existing_links_map = {}
for _sk, _src_data in src_map.items():
    _existing_links_map[_sk] = set(it.get("link", "") for it in _src_data["items"])

# 回填循环中：
if entry.get("link", "") not in _existing_links_map.get(sk, set()):
    src_map[sk]["items"].append(entry)
    _existing_links_map.setdefault(sk, set()).add(entry.get("link", ""))
```

### Fix 3: 构建日志口径统一

**文件**: `build_rss_aggregator.py` 第 7359 行之后

```python
sources_with_items, total_items = _accumulate_history(sources_with_items)
ok_count = sum(1 for s in sources_with_items if s.get("items"))  # 重新统计
```

### Fix 4: T4 长尾层——低频优质源独立保留机制

#### 4a. 新增 T4 tier 定义

| Tier | 含义 | 增量跳过阈值 | 历史保留窗口 |
|------|------|-------------|-------------|
| T1 | 实时源（api/rss.js 抓取） | 始终跳过 | 72h |
| T2 | 高频源 | 1h | 72h |
| T3 | 常规源 | 2h | 72h |
| **T4** | **低频长尾源** | **4h** | **7 天** |

#### 4b. 自动识别与晋升机制

在 `_accumulate_history` 完成后、快照保存前，扫描所有源的文章日期分布：

```python
# 自动晋升：连续 3 次构建中，源的所有文章 pub_date 均 > 72h → 晋升 T4
# 判定条件：源有 ≥1 篇文章，且最早文章 > 72h，且源 quality ≥ 40
for src in sources_with_items:
    if src.get("tier", 3) >= 4:
        continue  # 已是 T4
    items = src.get("items", [])
    if not items:
        continue
    # 检查是否所有文章都超过 72h（低频源特征）
    all_old = all(_is_older_than_72h(it) for it in items if it.get("pub_date"))
    if all_old and len(items) >= 1:
        _promote_to_t4(src["key"])
```

晋升结果写入 `rss_sources.json` 的 `tier` 字段，持久化。

#### 4c. T4 源的 tier 级历史保留窗口

修改 `_accumulate_history` 中的 cutoff 计算，从全局 72h 改为按 tier 分级：

```python
# 现有：统一 72h
cutoff = now_bj.replace(tzinfo=None) - datetime.timedelta(hours=RSS_HISTORY_HOURS)

# 修改后：按源 tier 分级
# 在合并阶段，每篇文章的过期判定基于其源 tier
_TIER_HISTORY_HOURS = {1: 72, 2: 72, 3: 72, 4: 168}  # T4 = 7 天

# 合并时：
tier = _src_tier_map.get(src["key"], 3)
tier_cutoff = now_bj.replace(tzinfo=None) - datetime.timedelta(
    hours=_TIER_HISTORY_HOURS.get(tier, 72))
if pd_bj < tier_cutoff:
    continue  # 该 tier 的窗口外，跳过

# 裁剪时同理：
tier = _src_tier_map.get(item.get("source_key", ""), 3)
tier_cutoff = ...
if pd_bj < tier_cutoff:
    expired.append(link)
```

#### 4d. 发现页推荐：T4 源优先置顶

修改前端 `_discoverKeys()` 函数，T4 源自动进入发现页并置顶：

```javascript
function _discoverKeys(){
    var srcCnt={};
    ART.forEach(function(a){srcCnt[a.sk]=(srcCnt[a.sk]||0)+1;});
    var qm=(ANALYSIS_DATA&&ANALYSIS_DATA.quality)?ANALYSIS_DATA.quality:{};
    var ks={};
    // T4 源优先进入发现页（长尾推荐）
    SOURCES.forEach(function(s){
        if(s.tier===4 && srcCnt[s.key]>0) ks[s.key]=true;
    });
    // 原有逻辑：低量高质量源
    for(var sk in srcCnt){
        if(srcCnt[sk]<=5 && (qm[sk]||0)>=60) ks[sk]=true;
    }
    return ks;
}
```

同时修改 `renderChips` 中的发现页标题，标注 T4 长尾源数量：

```javascript
// 发现 chip 中展示 T4 源数量标识
if(discCnt>0){
    var t4Cnt = SOURCES.filter(function(s){return s.tier===4 && srcCnt[s.key]>0;}).length;
    var label = '\U0001f50d 发现';
    if(t4Cnt > 0) label += ' <span class="t4-badge">'+t4Cnt+' 长尾</span>';
    ...
}
```

## 4. 不变量约束

以下行为**不应被修改**：

1. T1/T2/T3 的 72h 窗口保持不变
2. 域名级熔断机制保持不变
3. T1 源始终由 api/rss.js 实时抓取
4. 前端 `if(cnt > 0)` 过滤逻辑不变
5. `_rss_history` 的裁剪逻辑对 T1-T3 不变

## 5. 验收标准

1. **信源恢复**: 修复后构建，有内容信源数应从 584 显著提升（预期 700+）
2. **日志一致**: 构建日志 "N 源成功" 与快照中实际有内容源数一致
3. **无回归**: 现有 584 个有内容信源的数据不丢失
4. **增量恢复**: 空历史源在增量构建中能被重新抓取
5. **去重正确**: 同一篇文章不出现两次
6. **T4 保留**: T4 源的文章在 72h 后仍可见（7 天窗口）
7. **T4 发现页**: T4 源在发现页中优先展示
8. **自动晋升**: 低频源在连续构建后被自动识别并晋升 T4

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Fix 2 内存增大 | 低 | 低 | 增量构建抓取结果通常不大 |
| Fix 1 增量变慢 | 中 | 低 | 仅影响历史为空的源 |
| T4 自动晋升误判 | 低 | 中 | 需连续 3 次构建满足条件才晋升 |
| T4 7 天窗口导致历史膨胀 | 低 | 低 | T4 源数量预期 < 100，影响可控 |
| Fix 2 去重遗漏 | 低 | 中 | 对抗性审查重点测试 |
