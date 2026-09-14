# 审查：`2026-09-14-composite-sort-spec.md`（复合排序）对照 `2026-09-14-rss-topic-clustering.md`（主题聚类）

审查日期：2026-09-14
审查对象：`docs/superpowers/plans/2026-09-14-composite-sort-spec.md`
对照方案：`docs/superpowers/plans/2026-09-14-rss-topic-clustering.md` + `docs/superpowers/specs/2026-09-14-rss-topic-clustering-design.md`
数据基线：`rss_api_snapshot.json`（1014 源 / 8986 条）、`analysis_snapshot.json`（quality 1014 条）

## 证据等级约定

| 等级 | 含义 |
|---|---|
| T0 | 一手实测：本次亲手跑出的命令输出，可复现 |
| T1 | 源码直读：确定性结论，行号可核对 |
| T2 | 方案自述：文档自己写的，未独立验证 |
| T3 | 本人推断：可能有错 |

---

## 0. 一句话结论

复合排序方案里**「信誉打散」这一半不成立，必须重做**（算法目标与实现相反、时间维度被打碎、测试大面积空心）；**「主题聚类」那一半没有自己的实现**，只是引用我的方案。
但它提出的**新增 `diverse` 排序模式**这个产品方向值得保留——只是当前实现要换、`_tag_articles` 那一段要整段砍掉。

---

## 1. 两份方案不是竞品，是「依赖 + 冲突」

- 复合排序方案 Task 8 原文：*「本阶段完全复用 `2026-09-14-rss-topic-clustering.md`（任务 0-13）」*（T2）。
- 它的 Phase 1/3 另建了一套 `tags[]` 字段，但 Task 8 的集成契约写的是 `cl` / `g`——**这是我这边的字段名**（T1：本方案 `assign_topic_clusters()` 产出 `cl`/`g`）。
- 结论：`tags[]` 与 `cl`/`g` 是两套并行的话题表示，前者在全链路里**没有任何消费者**（见 D6）。

### 1.1 两方案会撞在同一批代码行上

| 位置 | 我的方案 | 复合排序方案 | 后果 |
|---|---|---|---|
| `build_rss_aggregator.py:2308` `var sortMode = …` 非法值回落 | 任务 8 追加 `['newest','oldest','active','quality','topic']` | Task 5 Step 5 追加 `['…','topic','diverse']` | 同一行两处编辑，必须串行 |
| `:4899` `#sortSelect` 的 option 串 | 任务 8 在 `quality` 后加 `topic` | Task 5 Step 4 在 `quality` 后加 `diverse` | 同一条字符串字面量，后落地方需 rebase |
| `build_html()` 签名 `:4841` | 任务 5 加 `topic_clusters=None` | Task 7 加 `diverse_window_minutes=120` | 同一函数签名，需协调参数顺序 |
| `tests/rss_*/_loader.py` | `tests/rss_topic/_loader.py` | `tests/rss_composite/_loader.py` | 两份重复加载器，可合并 |

**必须串行落地，不能并行派单。** 建议顺序：主题聚类先行（结构性改动大、定义 `cl`/`g` 契约），复合排序的 `diverse` 在其之上 rebase。

---

## 2. 逐项核对：方案主张 vs 实测

| # | 方案主张 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | Goal：「增加信誉打散（Weighted Shuffle）」 | 实现完全无随机性，是**固定置换**：同一输入 100 次试验只产出 1 种排列 | 不成立（T0） |
| 2 | 注释：「避免高信誉源霸屏」 | 高信誉源**必定**排首位（100/100），低信誉 0 次；方向与目标相反 | 不成立（T0） |
| 3 | 「低信誉源也有机会在窗口内靠前（权重非零即有概率）」 | 2 条 fixture 下低信誉 0/100 次靠前，无任何概率性 | 结论错误（T0） |
| 4 | Goal：「保持原有的时间维度可读性」 | 38/38 个窗口全部被重排；窗口内时间逆序对 **645,773**；最大窗口输出首位是「第 334 新」 | 不成立（T0） |
| 5 | `D5` 自述为「统计测试：100 次中 ≥60 次」 | 实测 100/100，测试通过但结论不可外推；权重**非单调**（w=[10,50,50,90] 时最高权重排第 2 位） | 测试与实现矛盾（T0） |
| 6 | `D8` 标题「quality 全相等时保持输入顺序」 | n=3 → `[1,0,2]`、n=6 → `[2,3,1,4,0,5]`，**被重排**；断言只比较两次调用是否一致，从未比较输入顺序 | 标题所述与实现不符（T0） |
| 7 | 「目标：`_tag_articles` 每篇 2-3 个话题标签」 | 真实语料下标签含空格碎片占 **10.7%**（`址  `、`月 日`、`苹果发`/`布会前`）；**86.8% 的标签组合是单条独有，无法成组** | 不满足「话题」语义（T0） |
| 8 | 「摘要前 200 字」作为标签信号 | 引入 `fetcherror` / `error` / `mhttps`；`址  ` 跃升为第 3 高频标签 | 与既有 T0 实测一致：摘要并入使最大簇 9→31（样板串味） |
| 9 | Task 9 预期「V1/V5 全部 PASS」 | `rss_api_snapshot.json` 的 item 字段是 `t/u/s/d`，`_tag_articles` 读 `title_zh`/`title` → 全部为空 → 覆盖率 **0%**，`rate>=0.5` 必然 FAIL | 预期错误（T0） |
| 10 | Task 5 Step 6 预期「D1-D11 全部 PASS」 | harness 只抽取 `weightedShuffle`；D11 引用 `ART`/`applySort`/`ANALYSIS_DATA`/`DIVERSE_WINDOW` 全不存在 → `ART is not defined`，实测 exit 1 | 预期错误（T0） |
| 11 | Task 6 预期 RED | `_split_data_chunks()` 在 `:4809` 用 `c0["items"] = c0_items[k]` 传原对象引用，`tags` 自动穿透 → A1/A2 一开始就是 GREEN | RED 是假的（T1） |
| 12 | V5「`diverse_enabled=false` 时 sort-select 不含 diverse option」 | `_load_diverse_config()` 返回 `enabled` 但**无任何任务使用它**；Task 7 Step 4 只传 `window_minutes` | 验收标准悬空（T1） |
| 13 | Phase 1/3 产出的 `tags[]` 供前端消费 | `buildArt()`（`:2274-2279`）用显式字段白名单重建文章对象，**不含 `tags`**；方案未改 `buildArt()` | 数据无消费者（T1） |

---

## 3. 具体缺陷清单（按严重度）

### Critical

**C1 — `weightedShuffle()` 的算法与它自己的目标相反。**（T0）
`threshold = totalW * 0.5` 的确定性累积扫描，等价于「每轮取累积权重中位处的元素」。它既不是加权采样，也不是质量排序，而是一个**从中位数向两侧扩散的固定走位**。
实测（窗口 674 篇 / 72 源）：输出前 150 位的原始位置 = `334,335,336,333,337,332,331,338,339,330,…`——**全部取自窗口中部，最新的 260 篇一篇未出现**。
`n=4, w=[10,50,50,90]` → 输出 `[w50, w90, w50, w10]`：权重最高的排**第 2 位**。算法在权重上不单调，"高信誉靠前"只在 2 条 fixture 下偶然成立。

**C2 — 唯一真实收益是「减少同源扎堆」，而非「信誉打散」。**（T0）
最大窗口同源最长连续：打散前 30 → 打散后 3。这个收益是真的，但归因错了：它是「窗口内重排」的副产品。
而项目里**已有同类机制** `tierInterleave()`（`:2355-2365`，4 高频 + 1 低频），在 `applySort()` 之后执行（`:3345` / `:3385`）。方案 Task 8 只写「仍执行」，**未分析它会如何重排 weightedShuffle 的输出**——我的方案把这一条列为隐藏坑，这里被漏掉。

**C3 — `_tag_articles()` 的 TF 定义在单篇文档上无意义。**（T0）
一篇标题内的 token 频次几乎全是 1，`Counter.most_common(3)` 的并列项按首次出现顺序破平 → 实际语义退化为「标题里前 3 个长度 ≥2 的 token」。
实测：`IT早报 0914：苹果发布会前瞻、特斯拉新车型` → `["早报 ", "苹果发", "布会前"]`；`【公告】关于调整部分服务费率的通知` → `["公告 ", "关于调", "整部分"]`；`埃博拉疫情在刚果（金）再度暴发 - RFI - 法国国际广播电台` → `["rfi", "埃博拉", "疫情在"]`——**出版社样板 `rfi` 直接成了标签**，正是我的 spec 第 1 节列为阻断项的那个污染。

**C4 — Phase 1/3 是死数据，代价 332 KB。**（T0/T1）
8986 条写入 `tags` 实测新增 **332 KB**（对照：主题聚类只写一个整数 `cl` 约 79 KB）。
而 `buildArt()` 的白名单不含 `tags`，前端拿不到；Phase 5 的契约又改用 `cl`/`g`。**产出即废弃。**

### Major

**M1 — 测试套件大面积空心。**（T0/T1）
- `A3`（确定性）、`A5`（只加 tags）：对纯函数必然通过，无法因错误实现而失败。
- `A4`（标签数 ≤3）：`most_common(3)` 在 `len(t)>=2` 过滤**之前**已封顶 3，断言恒真。
- `A2`（空标题 → `[]`）：实现里 `if not text` 分支直接命中，恒真。
- `D8`：断言「两次调用一致」，标题写「保持输入顺序」，**断言与标题不同**。
- `D10`（条目守恒）：`while remaining` 循环结构性保证，恒真。
唯一有真实失败面的是 `A1a`。所以 Phase 1 的 RED 只因「函数不存在」，**不约束行为**——按 superpowers 的 TDD 纪律，这属于「无法因正确原因失败」的测试。

**M2 — 两处预期结果写错，会误导执行者。**（T0）
`regression_composite.py` 的 V1 与 `test_diverse_js.py` 的 D11 都必然失败（见核对表 #9 #10）。若按「两阶段评审」派子代理执行，子代理会卡在无法变绿的测试上，且大概率会**改测试去迁就实现**。

**M3 — quality 有 48.9% 的源是 0 分。**（T0）
1014 源中 496 源 `quality == 0`。权重 0 的条目在窗口内会被整体推到后面（零权重不推进累积量，仅当 `totalW<=0` 时才按原序追加）。这不是「打散」，是**未声明的质量重排**，且方案没有任何一处分析这个 case。

**M4 — `DIVERSE_WINDOW` 注入点与配置读取。**（T1）
`_load_diverse_config()` 用相对路径 `"build_config.json"`——与 `_load_analysis_enabled()`（`:100-107`）同风格，**这一点没问题**，我最初怀疑有误，实测一致。
真正的问题是 `enabled` 读了不用（核对表 #12）。

### Minor

- `Task 5 Step 5` 的回落列表在 `topic` 尚未实现时把 `topic` 列为合法值，若单独上线会产生「选中 topic 但无对应渲染分支」的空状态。
- `tests/rss_composite/_loader.py` 与 `tests/rss_topic/_loader.py` 内容重复。
- 方案的「工作量合计 ~250 行新增」未计入 `buildArt()` 白名单、`diverse_enabled` 分支、以及修 C1 所需的重写。

---

## 4. 它比我方案强的地方（公平记录）

1. **复用了既有 `quality` 信号。**（T0）`analysis_snapshot.json` 的 `quality` 覆盖 1014/1014 源、8986/8986 条目，100% 覆盖。我的方案完全没有用它，这是我的缺口。
2. **明确写了跨方案的集成契约**（Task 8 的 5 条约束），包括「diverse 与 topic 互斥」「topic 模式下 weightedShuffle 不执行」。我的方案没有考虑第二个排序模式的存在。
3. **文件结构与任务粒度与既有约定一致**（`_loader.py` / `_harness.js` / `cases_*.js` / `regression_*.py`），可以直接接入现有 `tests/rss_sort`、`tests/rss_date` 的跑法。
4. **回滚策略写得更细**（按「代码/功能/数据/测试」四维拆开），我的方案只有一段。

**产品方向本身也值得保留**：现有 `quality` 排序（`:2344-2347`）是纯源质量排序，**完全没有时间 tiebreak**，会把时间维度整个丢掉。在这个页面里加一个「兼顾时间与信源多样性」的模式，是有价值的。

---

## 5. 修正建议

### 5.1 砍掉 `_tag_articles()` 与 `tags[]`（推荐）

理由：TF 语义不成立（C3）、无消费者（C4）、332 KB 代价、与 `cl`/`g` 重复。
若确实需要话题标签，**换成我方案任务 2 的 `_topic_domain()`**——17 域词典法，实测覆盖 50.2%、抽检精度 70-80%、零 API、确定性。同一份数据，一个有意义。

### 5.2 重写 `weightedShuffle()`：改用「同源窗口配额」

保留目标（减少同源扎堆、给低信誉源曝光），换机制：

- 主序仍是**时间降序**，不做全局重排。
- 遍历时维护 `(window, srcKey) -> count`。当某源在**当前 120 分钟窗口**内已出现 `k` 次（建议 `k=2`），把该条**延后**到下一个可用位置，而不是把它丢掉或整体打乱。
- 效果：时间序在绝大多数位置保持单调；被延后的条目数可量化、可断言；确定性天然成立（无随机）；同源连续被打断。

这样验收标准就从「打散」变成可证的三个数：

| 指标 | 现行实现（实测） | 配额法目标 |
|---|---|---|
| 窗口内时间逆序对 | 645,773 | ≤ 被延后条目数（k=2 时预计数百量级） |
| 同源最长连续（最大窗口） | 30 → 3 | ≤ k |
| 前 150 位中来自最新 20% 的比例 | 0%（实测全取自中部） | ≥ 80% |

如果一定要随机性：用 **seeded PRNG**（`mulberry32(build_ts)` 之类），保证构建可复现。但要先想清楚代价——墙序每次构建都变，会破坏用户的空间记忆，而这个代码库此前专门修过「并列导致整块钉在顶部」的确定性 tiebreak 问题（`:2282-2290`）。

### 5.3 修测试

- 删掉 `A3`/`A4`/`A5`/`A2`/`D10` 这类恒真断言，或改写成能因错误实现而失败的形式。
- `D8` 改成真正断言输入顺序，并承认在等权重 n≥3 时实现会重排——**这正是 C1 的证据，不该被测试掩盖**。
- `D11` 的 harness 需要一并抽取 `applySort`，并声明 `ART` / `sortMode` / `ANALYSIS_DATA` / `DIVERSE_WINDOW`。
- `V1` 改用 `t/u/s/d` 字段，或改在 build 侧的 `sources_with_items` 形状上跑。
- 新增真正的验收指标：窗口内逆序对上限、同源窗口配额上限、越界条目不丢失。

### 5.4 补 Task 8 缺的交互分析

`tierInterleave()` 在 `applySort()` 之后执行（`:3385`），会把 `weightedShuffle()` 的窗口内顺序在**全局**层面按 tier 重排（组内相对序保留，跨 tier 相邻关系被打断）。这条必须写进方案，否则「diverse 模式的实际观感」无法预测。

---

## 6. 复现方式

本轮所有 T0 数字的原始出处（**未删除任何文件**）:

| 脚本 | 验证内容 |
|---|---|
| `.workbuddy/_cmp_probe.py` → `_cmp_probe.txt` | quality 结构/覆盖、`_tag_articles` 标签样例、等权重置换 |
| `.workbuddy/_cmp_probe2.py` → `_cmp_probe2.txt` | snapshot 字段名、quality 分布、38 窗口逆序对统计、同源连续对比 |
| `.workbuddy/_cmp_probe3.py` → `_cmp_probe3.txt` | V1 覆盖率 0%、标签质量、跨源扩散、载荷 332 KB、可分组性 86.8% 孤点 |
| `.workbuddy/_cmp_weighted.js` | D5/D8/D11 重放（D11 实测 `ART is not defined`，exit 1） |
| `.workbuddy/_cmp_series.py` → `_cmp_series.json` | 窗口位次映射序列（上图数据源） |

重跑：

```bash
PY="C:/Users/40832/.workbuddy/binaries/python/versions/3.13.12/python.exe"
NODE="C:/Users/40832/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
cd "E:/github收藏和热点"
"$PY" .workbuddy/_cmp_probe.py && "$PY" .workbuddy/_cmp_probe2.py && "$PY" .workbuddy/_cmp_probe3.py && "$NODE" .workbuddy/_cmp_weighted.js
```
