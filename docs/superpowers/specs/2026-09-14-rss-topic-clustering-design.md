# RSS 聚合页主题聚类（Topic Clustering）Spec

> 日期：2026-09-14
> 状态：待实施（设计已确认，等待执行授权）
> 唯一改动文件：`build_rss_aggregator.py`、`build_config.json`；新增 `tests/rss_topic/`
> 关联：`docs/superpowers/specs/2026-09-02-rss-cardwall-redesign.md`（卡片墙形态）、`2026-09-14-rss-default-sort-fix.md`（排序口径）

---

## 1. 目标

当前卡片墙是**单层扁平时序**（`sortMode` = newest/oldest/active/quality）。本spec 增加**外层主题聚类、内层时间倒序**的两层结构，并保持原有时间维度的可读性。

用户在 2026-09-14 确认的两个决策：

| 决策点 | 选择 |
|---|---|
| 外层组织方式 | **事件簇 + 主题域 混合**，单一外层 |
| 跨源同题冗余 | **折叠成一条主卡 + 「另有 N 源报道」**（仅主题视图生效） |

---

## 2. 实测基线（T0：一手实测，2026-09-14 快照，8986 条）

数据源：`rss_api_snapshot.json`（1014 声明源 / 518 源有 items；日期跨度 09-11 ~ 09-14；8788/8986 有日期；中文标题 7799、非中文 1187）。

| 路线 | 覆盖率 | 质量 | 计算成本 |
|---|---|---|---|
| 复用现有 `analysis_snapshot.json` 的 `topic_clusters` | **0.82%**（74/8986） | 标签为 n-gram 碎片（`Find what ` / `building`） | 已花 103s + LLM/embedding |
| 发现式聚类（标题 token Jaccard = 0.20） | 4.3%（354/8248） | 105 簇中 71 个为真跨源事件；最大簇 9 篇 | 0.2s，零 API |
| 发现式聚类（阈值 0.12） | 13.4% | 313 簇，开始混入样板噪声 | 0.3s |
| 发现式聚类（标题+摘要联合信号） | 12.1% @0.12 | **更差**：最大簇 31（人民网 `FetchError` 聚成 23 篇） | 1.0s |
| 关键词主题域分类（17 域词典） | 50.2%（4512/8986） | 抽检精度约 70-80% | 秒级，零 API |

**结论：本语料无法用廉价确定性方法做到全覆盖主题分区。** 因此「未归类」是结构性产物而非缺陷，它的正确形态是**原时间线**（时间倒序），这也满足「保持原有时间维度的可读性」。

**关键判断：不复用 `analysis_snapshot.json` 的 `topic_clusters`。** 覆盖率 0.82%、标签不可读，根因是 `insight_max_documents=200` + `_build_topics_with_meta()` 靠 `title[:30]` 精确查表回填（有损）。它继续服务洞察面板，与本次墙体聚类互不耦合。

**性能预算**：8986 条分词 1.4s + 聚类 0.2~0.3s → 构建期执行，零 API 调用。

---

## 3. 必须前置修复的阻断项

不修这两项，聚类会产出**伪簇**：

1. **出版社样板污染**。快照标题含 `- RFI - 法国国际广播电台`、`IT早报 0914：`、`FetchError: [GET] "http://..."`、`源：https://t.co/...`。实测：法广中文 5 组无关新闻（埃博拉、对华防务对话、澳门国安法审判）会被并进同一簇。
2. **题名重复**。归一化后完全同题 428 组、冗余 681 条（跨源 512 + 同源 227）。不归一化则单条 V2EX 帖自聚成 10 篇的「主题」。

顺带记录（回归基线）：前端 `buildArt()` 的 `sk|link` 去重**实际去重 0 条**，墙内就是 8986 条。

---

## 4. 数据契约

### 4.1 item 新增字段

构建期在每条 item 上写两个整数字段（`rss_api_snapshot.json` 与 `rss-data-*.js` 同步获得）：

| 字段 | 含义 | 取值 |
|---|---|---|
| `cl` | 外层聚类 id | `>=0` 有效；`-1` = 未归类；缺省按 `-1` 处理 |
| `g` | 折叠组 id（仅同题组 ≥2 时写入） | `>=0` 有效；缺省按 `-2`（无组）处理 |

透传链路已核实无需改：`api/rss.js:429` 用 `...item` 展开 → `cl`/`g` 自动透传；前端 `_mergeChunk()` 整体 concat items → 自动保留。

体积影响：8986 × 约 12 字节 ≈ 108KB（快照 +0.3%）。

### 4.2 内联元数据

HTML 内联两个全局（估计 <30KB）：

```js
window.CLUSTERS = [
  { id: 0, label: '英伟达 RTX PRO 5500 发布', kind: 'event', n: 4,
    t0: '2026-09-14T09:12:00+08:00', t1: '2026-09-14T11:40:00+08:00',
    cats: ['ai','tech'], titles: ['归一化题名1','归一化题名2'], kb: ['英伟','伟达','rtx'] },
  ...
]
```

| 字段 | 用途 |
|---|---|
| `label` | 组头标签 |
| `kind` | `'event'` 事件簇 / `'domain'` 主题域；组头前缀区分两种粒度 |
| `n` / `t0` / `t1` | 篇数、时间跨度（组头展示） |
| `titles` | 归一化代表题名（top 5），供刷新通道精确归簇 |
| `kb` | 质心字符二元组（top ~40），保留给 P2 的运行时模糊归簇 |

### 4.3 id 分配

`0 .. E-1` = 事件簇（E ≤ `topic_event_max`）；`E .. E+16` = 主题域；`-1` = 未归类。**分配必须确定性**（禁止依赖 `set` 迭代顺序），否则每次构建结果漂移，无法写回归测试。

---

## 5. 后端算法

新增函数统一放在 `_cluster_topics()`（`:5518`）之后、`_generate_daily_summary()` 之前的分析函数区。

### 5.1 主入口

```python
assign_topic_clusters(sources_with_items, config) -> list[dict]
```

调用点：`main()` 组装完 `sources_with_items` 之后、`_save_api_snapshot()`（`:6581`）**之前**——必须在快照写入前，才能让快照与 chunk 同时带上 `cl`/`g`。

### 5.2 步骤

1. **质量闸门**
   - `_strip_boilerplate(t)` 后长度 ≥ 4
   - 未命中 `_TITLE_REJECT`：`^\s*(源|来源)[:：]`、`^https?://`、`^FetchError`、纯标点/纯 emoji、连续重复字 ≥2（复用 `_has_repeated_chars`）
2. **题名归一化** `_norm_title(t)`：剥离出版社后缀/前缀 → 去 `[..]`（≤10 字）题前缀 → 去空白标点 → 小写 → 截断 48
3. **折叠组**：`_norm_title` 相同者归一组；组内 ≥2 时给组内每条写 `g`（组 id 按首次出现顺序，确定性）
4. **主题域分类** `_topic_domain()`：17 域词典打分（标题 + 摘要前 120 字），命中数 × 域权重取最大；0 分 → `None`
5. **事件簇** `_cluster_events()`：语料 = 每个折叠组的代表（组内题名最长者）
   - tokens = `_tokenize_cached(_strip_boilerplate(title))`；丢弃 DF > 5% 的 token（实测 9k 语料仅 `ai` 一个，保留逻辑以备语料变化）
   - 倒排索引（token → cluster ids）取命中数 top 12 候选；与质心算 Jaccard，≥ `topic_event_threshold` 则并入
   - 质心 = 成员 token 的 top 20；规模 ≥ `topic_event_min_size` 的簇入选
   - 按规模降序取前 `topic_event_max`，**同规模按代表题名 `localeCompare` 兜底**（保证确定性）
6. **落位**：每条 item 的 `cl` 优先级 = 其折叠组代表所属事件簇 > 主题域 > `-1`。
   **折叠组内所有条目共享同一 `cl`**（同题不得跨组）
7. **标签** `_topic_label()`
   - 事件簇：与质心 Jaccard 最高的**题名**作为 medoid，`_strip_boilerplate` 后按标点截断到 ≤18 字；空则回退 `_tfidf_keywords()` top 3（实测纯 TF-IDF 出 `出席金/砖国家` 碎片，故仅作回退）
   - 主题域：词典名
8. **元数据**：组按「组内最新一篇时间」降序；`kind='unclustered'`（`cl=-1`）**强制末位**

### 5.3 确定性硬约束

- 所有 dict/set 遍历不得决定输出顺序
- 所有排序必须有全序 tie-break（`(链接, 源key)`）
- 同一份 `sources_with_items` 连续两次调用必须产出**逐字节相同**的结果（回归测试断言）

---

## 6. 前端渲染

### 6.1 布局模式切换（必须）

现状 `.wall { columns:4 300px; column-gap:14px; }`（`:1663`）是 **CSS 多列**。多列容器内块级子元素会跨列断开，且 `position: sticky` 在多列中行为不可靠 → 主题视图必须换布局：

```css
.wall.topic { columns: unset; }
.wall.topic .tgroup { break-inside: avoid; margin-bottom: 26px; }
.wall.topic .tgroup .tg-body { columns: 4 300px; column-gap: 14px; }
.tg-head { position: sticky; top: var(--hdr-h, 0px); z-index: 3; }
```

组内仍用多列卡片（保持原观感），组间走块级流（保证顺序与吸顶可用）。`--hdr-h` 由 JS 在 `load`/`resize` 时实测 `header.getBoundingClientRect().height` 写入（header 是 `top:0` 的 sticky，`:1579`）。

### 6.2 分桶与排序（纯函数）

```
renderTopicWall(list):
  buckets = groupBy(list, a => a.cl)
  for each bucket:
      inner = expandFold(bucket)            // 折叠组 → 主卡 + foldN
      inner.sort(_dateCmpDesc(a.date, b.date))
      latest = max(inner.date)              // 无日期不计入，全无日期则沉底
  groups.sort(by latest desc)               // cl === -1 强制末位
```

**必须在渲染时现算组内顺序，不可依赖 `ART` 的全局顺序。** 原因：`tierInterleave()` 在 `_mergeChunk()`（`:3345`）与 `_mergeRemoteSources()`（`:3385`）后会把 `ART` 重排成「4 高频 + 1 低频」，ART 早已不是严格时间序。

### 6.3 折叠

- 同组内 `g >= 0` 的条目按 `g` 再分桶；主卡 = 组内时间最新的一条
- 主卡底部追加 `<button class="fold-btn">另有 N 源报道</button>`，`N` = 组内条目数 − 1
- 点击 → 组内插入其余成员的 `.mini-row`（同源同题只保留一行），用 `hidden` 切换，**不重建整墙**
- 折叠组内条目数为 1 时不渲染按钮

### 6.4 分页

| 变量 | 默认 | 平铺模式 | 主题模式 |
|---|---|---|---|
| `wallLimit` / `WALL_STEP` | 120 / 80 | 沿用 | 不参与 |
| `groupLimit` / `TOPIC_GROUP_STEP` | 8 / 8 | 不参与 | 组数预算 |
| `GROUP_CAP` | 20 | — | 每组首屏卡片上限 |

- 每组底部「展开本组」按钮：`shown += GROUP_CAP`
- `loadMore()` 在主题模式改为 `groupLimit += TOPIC_GROUP_STEP`
- 未归类组同样受 `GROUP_CAP` 约束（该组可达 4000+ 条）

### 6.5 入口与状态

- `#sortSelect`（`:4899`）增 `<option value="topic">主题聚类</option>`
- `localStorage.rss_sort_mode` 新增合法值 `'topic'`；非法值回落 `'newest'`
- 切换时 `renderWall()` 自动分流；`renderChips`/`renderPanel`/`updateMeta` 无需改动

### 6.6 刷新通道

`_mergeRemoteSources()`（`:3354`）构造 `a` 时：

```
a.cl = (typeof it.cl === 'number') ? it.cl : _runtimeCluster(a.t)
a.g  = (typeof it.g  === 'number') ? it.g  : -2
```

`_runtimeCluster(t)`：归一化题名后与 `window.CLUSTERS[*].titles` 精确比对，命中即返回该簇 id，否则 `-1`。
**已知限制**：T1 实时源的新事件在下次构建前落「未归类」（构建每 4 小时一轮）。字符二元组模糊归簇列为 P2，本期不做。

### 6.7 复用约束（不得违反）

- **`visibleArts()`（`:2540`）一行不改**——它被 `renderChips`/`updateMeta`/`loadMore`/键盘导航/`insightSearch` 共用。分组逻辑全部封装在 `renderWall()` 内。
- **`.tg-head` 不得含 `.card` class**——`#wall` 事件委托用 `closest('.card')`（`:2712`），误命中会打开阅读器。
- `.tgroup` 加 `role="presentation"`：`#wall` 是 `role="feed"`，其直接子元素应为 `article`，插入 `section` 会破坏 ARIA 契约。
- `updateCardStates()` 的 `#wall .card` 选择器、`document.getElementById('wall').addEventListener` 委托、`ART.find(artKey===k)` 查找在分组后均成立，无需改。

---

## 7. 配置

`build_config.json` 新增：

```json
{
  "topic_cluster_enabled": true,
  "topic_cluster_view_default": false,
  "topic_event_threshold": 0.20,
  "topic_event_min_size": 3,
  "topic_event_max": 12,
  "topic_domain_enabled": true,
  "topic_label_llm": false
}
```

缺失键自动填默认（沿用现有 `config.get(k, default)` 约定）。

`topic_label_llm=true` 时用 Agnes 批量命名（1 次调用，每簇 ≤8 条样例题名），失败静默降级到 medoid。默认关闭。

---

## 8. 验收标准

| 编号 | 指标 | 阈值 |
|---|---|---|
| A1 | 外层组数 | 15 – 40 |
| A2 | 「未归类」占比 | ≤ 55% |
| A3 | 组内时间序 | 全组零违例（`date[i] >= date[i+1]`，无日期条目不计入断言） |
| A4 | 组头不得误触发阅读器 | 点击组头 0 次打开 |
| A5 | 构建耗时增量 | ≤ 5s |
| A6 | 开关关闭时产物 | 与基线**逐字节一致**（`topic_cluster_enabled=false` 不写 `cl`/`g`） |
| A7 | 聚类确定性 | 同一输入连续两次调用结果逐字节相同 |
| A8 | 折叠覆盖 | 428 个同题组全部落同一折叠组；主题视图卡片数 ≤ 8320 |
| A9 | 过滤器 × 视图交叉矩阵 | 12 组合（cat / src / 未读 / 收藏 / 搜索 × 平铺 / 主题）全通过 |
| A10 | 平铺模式回归 | 卡片数、顺序、`sortMode` 四模式行为与基线一致 |

---

## 9. 不做的事

- 不引入运行时 embedding / LLM 调用
- 不改 `visibleArts()`、不改 `api/rss.js` 的返回结构（仅随 item 透传 `cl`/`g`）
- **折叠仅在主题视图生效**——平铺模式卡片数保持不变。理由：`visited`/`_bookmarks` 以 `artKey(a) = sk|u` 为键，平铺折叠会让已收藏条目的卡片消失但 localStorage 记录残留，属回归。平铺折叠列为独立后续项。
- 不替换现有 8 类 `cat` 分类芯片（主题域与 cat 是两个正交维度，前者只用于聚类分组，不加筛选芯片）
- 不改 `insight_engine.py` 与 `analysis_snapshot.json` 的结构

---

## 10. 回滚

改动集中在 `build_rss_aggregator.py` + `build_config.json`（新增键）+ 新增测试目录。

- 代码回滚：`git checkout -- build_rss_aggregator.py build_config.json`
- 功能回滚（不回滚代码）：`topic_cluster_enabled=false` → 产物与基线一致（A6 已定义该行为）
- 数据回滚：`cl`/`g` 为增量字段，旧产物解析时按缺省值处理，无需迁移
