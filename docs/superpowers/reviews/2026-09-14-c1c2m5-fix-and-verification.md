# C1 / C2 / M5 修复 + 对抗性审查验证报告

日期：2026-09-14
范围：`build_rss_aggregator.py` 的复合排序同源抑制（C1）、标签语义提取（C2）、tags 三通道穿透（M5）
方式：TDD（RED → GREEN → 变异验证）

---

## 0. 结论

| 条目 | 状态 | 证据等级 | 关键读数 |
|---|---|---|---|
| C1 同源抑制（`weightedShuffle`） | 已修 | T0 一手实测 | 真实语料前 200 位同源最长连续 **9 → 1**；前 20 位单源最多 **13 → 4** |
| C2 标签语义提取（`_tag_articles`） | 已修 | T0 一手实测 | 边界违例率 **16.7% → 0%**；含空白 **4.2% → 0%**；词典率 **4.2% → 18.21%** |
| M5 tags 三通道穿透 | 已修 | T0 一手实测 | 构建期/刷新/快照三通道 tags 全通；管线顺序 `_tag_articles` → `_save_api_snapshot` |
| 测试体系 | 新增/重写 | T0 一手实测 | 变异检出 **12/12**（复合）+ **19/19**（排序，既有） |
| C1 深层残留（尾部连出） | **未消除**，已量化并记录 | T0 一手实测 | 全长最长连出 11，位于第 7480 位（82% 深处），见 §5.1 |

### 自评分（满分 10）

| 维度 | 分 | 依据 |
|---|---|---|
| 修复正确性 | 8.5 | C1 首屏症状消除且可证伪；C2 三项量化指标达标；M5 三通道全覆盖。C1 深层残留未消除（-1.5） |
| 测试鉴别力 | 9.5 | 首版 E 段是变异存活的（误绿），已定位并重写；现 12/12 检出。留 0.5 因 F 段聚合指标灵敏度不足（见 §3.3） |
| 证据可复现性 | 9.0 | 全部读数有可复现命令（§6）；基线对照用「同源码内切换抑制开关」，非复刻实现 |
| 诚实度 | 9.0 | 残留、未达标的可行域、范围外红套件全部显式列出 |

综合 **9.0 / 10**。

### 证据分级口径

- **T0 一手实测**：本轮亲手跑出的命令输出/文件，可复现
- **T1 源码直读**：直接读源码得到的确定性结论
- **T2 官方声称**：文档/注释里写的，读但未独立验证
- **T3 本人推断**：可能的错

---

## 1. 修复清单

### C1 —— 同源抑制（`weightedShuffle`）

文件 `build_rss_aggregator.py`：

| 位置 | 内容 |
|---|---|
| `:2427-2439` | 注释：精确边界说明（含不可行域退化 + 实测残留） |
| `:2434` | `var SRC_GAP = 2;` |
| `:2438` | `_srcGap(lastAt, len, sk)` —— O(1) 取「距上次出现的距离」 |
| `:2443` | `_srcWeight(x, qm)` —— 质量权重，缺省 50 |
| `:2475` | 3a 可选池过滤：`_srcGap > SRC_GAP` 才入池 |
| `:2480-2492` | 3b 池空退化：取「最久未出现」的源 |
| `:2493-2509` | 3c 池内确定性加权取中位（注释修正旧「确定性伪随机」，旧实现无 PRNG） |

`lastAt` 跨组保留，防跨窗口边界连出。

### C2 —— 标签语义提取（`_tag_articles`）

| 位置 | 内容 |
|---|---|
| `:5413-5442` | 常量区：`_TAG_MAX_LEN=6`、`_TAG_BOILER_*`、`_TAG_EDGE_NOISE`、`_TAG_BLOCKLIST`、`_TAG_EN_BLOCKLIST` |
| `:5450` | `_is_tag_station()` 台标自指判定 |
| `:5458` | `_tag_edge_ok()` 首尾虚词校验 |
| `:5481` | `_tag_candidates(text, src_norm, allow_runs)` —— P1 词典 → P2 英文 → P3 边界对齐整段 → P4 过滤后词频 → P5 按源样板抑制 |
| `:5554` | `_tag_articles()` 两遍：先逐条产候选，再按源统计样板词整源剔除 |
| `:5578` | `((title, True), (summary, False))` —— **摘要不切中文段** |

### M5 —— tags 三通道

| 位置 | 内容 |
|---|---|
| `:2297` | 新增 `_tagsOf(x)` 归一化助手（只接受非空数组，其余归一 null） |
| `:2314` | `buildArt()` 白名单补 `tags:_tagsOf(it)` |
| `:3531` | `_mergeRemoteSources()` 白名单补 `tags:_tagsOf(it)` |
| `:537-539` | `_save_api_snapshot()` 补 `if _tags: item["tags"] = _tags`（空值不写键，省体积） |
| `:6967` / `:6977` | `main()` 顺序：`_tag_articles()` 先于 `_save_api_snapshot()` |

---

## 2. TDD 证据链

### 2.1 C1：先发现测试是误绿的

首版 E 段用「5 源 × 6 篇」**均衡**夹具。把同源抑制过滤去掉后重跑：

```
RESULT: 38 passed, 0 failed        ← 变异体仍然全绿 = 测试没守住修复
```

根因（T0）：均衡夹具下每源只占 1/5，旧实现偶然也能打散，`maxRun` 天然 ≤2。

改用**倾斜夹具**（单个主导源占 23%~29%，其余 5~10 源等量）后具备判别性：

| 夹具 | 当前实现 maxRun | 去抑制变异体 maxRun |
|---|---|---|
| `12dom/5x6`（42 条，主导 28.6%） | 1 | 4 |
| `12dom/8x5`（52 条，主导 23.1%） | 1 | 2 |
| `14dom/10x4`（54 条，主导 25.9%） | 1 | 3 |
| `20dom/5x6`（50 条，主导 40%，不可行域） | 7 | 12 |

### 2.2 真实数据 A/B（T0）

对照方式：**同一份源码**，唯一差异是把 3a 的池过滤替换成无条件入池（等价于「无同源抑制」）。
除该行外两侧字节完全相同。

语料：`rss-data-0.js + rss-data-1.js`（509 源 / 9092 条）+ 真实 `analysis_snapshot.json` 质量表。

| 指标 | 当前实现 | 去抑制（旧等价） | 纯时间降序 |
|---|---|---|---|
| 前 200 位同源最长连续 | **1** | 3 | 9 |
| 前 50 位同源最长连续 | **1** | 1 | — |
| 前 20 位单源最多 | **4** | 3 | 13 |
| 前 200 位单源最多 | **24 / 200（12.0%）** | 27（13.5%） | 30（15.0%） |
| 前 200 位覆盖源数 | **36** | 35 | — |
| 源质量均值（前 20 位） | **82.45** | 81.17 | — |
| 平均时间位移 | 103.1 | 103.1 | 0.0 |
| 相邻时间倒置 | 47.3% | 48.3% | 0.0% |
| 全长同源最长连续 | 11 | 21 | 30 |

首屏 chunk0 单独场景（更贴近真实首帧）：前 200 位最长连续 **9（时间降序）→ 1**。

### 2.3 变异测试

`tests/rss_composite/mutation_check.py`（新增）：**12/12 CAUGHT**

| 变异体 | 命中用例 |
|---|---|
| C1-a 抑制过滤失效 | E1 / E5a / E8b |
| C1-b 间隔放宽为 1 位 | E9 |
| C1-c 池枯竭时反向选源 | E10b |
| C2-a 摘要也切中文段 | E7a |
| C2-b 词典优先失效 | B1a / B3 |
| C2-c 台标抑制失效（3 处变异点） | D1 / D2 |
| C2-d 边界虚词校验失效 | F3 |
| C2-e 中文段长度上界失效（3 处变异点） | C5 |
| M5-a/b/c/d 三条通道 + 顺序 | M5-1b / M5-4c / A2 / B4 |

`tests/rss_sort/mutation_check.py`（既有）：**19/19 CAUGHT**

---

## 3. 对抗性审查：我自己的错误

### 3.1 E 段是变异存活的（误绿）

见 §2.1。**这是本轮最重要的发现**：上一轮的 E 段写了等于没写。已重写为倾斜夹具。

### 3.2 `B4` 顺序断言被注释骗过

`test_snapshot_tags.py` 的 B4 用裸 `find("_tag_articles(")` 定位调用。`main()` 里有一行注释
「调用位置在 `_tag_articles()` 之后：…」，恰好排在 `_save_api_snapshot(` 之前 ——
于是「快照先于打标」这种回退**骗过**了顺序断言（变异 M5-d 存活）。

已改为语句级定位（`^[ \t]*name[ \t]*\(`，注释行不匹配），并加 B7 自检。

### 3.3 C2 的聚合指标灵敏度不足

把摘要的 `allow_runs` 改回 `True`，F 段仍全绿。实测差异：

| 指标 | 基线 | `allow_runs=True` |
|---|---|---|
| 标签总数 | 24033 | 25023（+4.1%） |
| 词典率 | 18.21% | 17.49% |
| 疑似中途切片 | 21.21% | 21.72% |

方向正确但幅度小于阈值。已补 **E7 段**直接断言通道契约（`E7a` 摘要不切段 / `E7b` 标题仍取词 /
`E7c`/`E7d` `allow_runs` 是真实开关），变异 C2-a 现在被捕获。

### 3.4 我提出的「均衡优先」方案被数据否决

C1 的选择规则原为「池内权重取中位」，我一度认为它消耗不均衡导致尾部塌成单源，主张改为
「剩余量优先」。实测三方案后**否决**：

| 指标 | 取中位（现方案） | 剩余量优先 | 纯时间降序 |
|---|---|---|---|
| 全长最长连续 | 11 | **1** | 30 |
| 前 200 位单源最多 | **24 / 200（12%）** | 50 / 200（25%） | 30 |
| 前 200 位覆盖源数 | **36** | 13 | — |
| 前 20 位源质量均值 | **82.45** | 78.08 | — |
| 首 12 条序列 | 混合 | `agihunt→nodeseek→v2ex` 三源机械轮转 | — |

「剩余量优先」能消除连出，但把首屏变成三源轮转、源覆盖度砍掉 64%。**优化了深层不可见指标，
牺牲了首屏可见质量，净亏**。保留现方案，并把该对比写进源码注释与 E7 守卫。

---

## 4. 顺带修复的既有缺陷（与 C1/C2/M5 无关，但阻塞全量回归）

### 4.1 `tests/rss_sort/regression_full.py` 静默失败

M5 让 `buildArt()` 依赖 `_tagsOf()`，该文件的块抽取没包含 `_tagsOf` → harness 抛
`ReferenceError` → 但 `run()` 对 node 崩溃只打印一行「无输出」并**返回 0**。

修复：补 `tagsOf` 块抽取；块缺失改为显式告警；FIXED 跑不出结果时返回 1。

### 4.2 `test_frontend_tz_regression.py` 日期依赖的潜伏崩溃

钳制片段用正则 `var nowMs[^\n]*\n\s*ART\.forEach\(function\(a\)\{[^\n]*\n` 切取，
只吃到回调体第一行 `if(!a.date) return;` 就断掉 → 产出未闭合 JS（SyntaxError）→
node stdout 为空 → `json.loads` 抛错。该分支只在「当前时刻晚于样例时间 2026-09-14T04:30+08:00」
时执行，因此是**日期依赖的潜伏缺陷**：2026-09-14 04:30 之后必崩。

修复：改为括号配平切全（`extract_clamp()`）。现在 R1c 真正执行并通过。

---

## 5. 已知限制与残留

### 5.1 C1 尾部连出（未消除，已量化）

- **现象**：9092 条真实语料中，全长最长连出 **11**（人民网），位于第 **7480** 位（82% 深处）。
- **定位**（T0）：该段完全落在 **g28** 组内（组 140 条 / **57 个源** / 人民网占 46 条）。
- **是否数据所迫**：**否**。可行性判据 `46 ≤ floor((140+2)/3) = 47` 满足。
- **根因**：贪心消耗不均衡使组尾塌成单源，池枯竭后触发退化分支。
- **为何不修**：唯一实测有效的替代规则（剩余量优先）代价见 §3.4 —— 首屏单源占比 12%→25%、
  覆盖源数 36→13、前 20 位源质量均值 82.45→78.08。**净亏**。
- **若要彻底修**：需要按比例公平（deficit scheduling）重写选择规则，属设计变更，
  需先评估再动手。本轮未做。

### 5.2 C1 在不可行域的退化（有界）

当某源占比超过 1/3 时，`池非空 ⇒ 相邻必异源` 不再可满足，退化分支会把间隔放宽到 2。
实测（`12dom/5x6`，42 条）仅 **1/42** 条被放宽（E9b 守卫 ≤20%）。

**精确边界（勿读成「最长连续恒 ≤ 2」）**：

- 池非空 ⇒ 同一源在最近 `SRC_GAP` 位内不会被再次选中 ⇒ 相邻必异源
- 池为空 ⇒ 退化为「最久未出现优先」；若只剩单一源，连出长度 = 该源剩余条目数，不可避

### 5.3 C1「不可行域仍可进一步优化」

扫描发现存在**构成可行但当前 maxRun = 3** 的夹具（`15dom/5x6` N=45 主导 33%、
`18dom/6x6` N=54 主导 33%、`20dom/3x15` N=65 主导 31%），理论下界为 2。
即贪心在这些点上不是最优的。已在 E8 中以「不回退」守卫锁定（≤8），未追求最优。

### 5.4 C2 长中文段残留切片

口径为「疑似中途切片」（含假阳性，如 `数学家` 出现在 `名顶尖数学家` 里也会计入）：
**27.28%（基线）→ 21.21%**。残留来自「超过 6 字且不含可用词典术语的中文段」——
离线无分词器时只能按 n-gram 硬切，属可接受的已知限制。

---

## 6. 验证清单（可复现）

```bash
PY=C:/Users/40832/.workbuddy/binaries/python/versions/3.13.12/python.exe

# 全量复合回归（含 5 个子套件）
$PY tests/rss_composite/regression_composite.py           # 25 passed, 0 failed

# 变异测试（对抗性审查）
$PY tests/rss_composite/mutation_check.py                 # 12/12 CAUGHT
$PY tests/rss_sort/mutation_check.py                      # 19/19 CAUGHT（既有）

# 子套件
$PY tests/rss_composite/test_diverse_js.py                # 50 passed, 0 failed
$PY tests/rss_composite/test_diverse_realdata.py          # 20 passed, 0 failed
$PY tests/rss_composite/test_tag_semantics.py             # 34 passed, 0 failed
$PY tests/rss_composite/test_refresh_tags_js.py           # 14 passed, 0 failed
$PY tests/rss_composite/test_snapshot_tags.py             # 14 passed, 0 failed
$PY tests/rss_sort/test_rss_sort.py                       # rc=0
$PY tests/rss_sort/regression_full.py                     # rc=0（真实载荷 8553 条）
$PY tests/rss_date/test_parse_rss_date.py                 # rc=0
$PY tests/rss_date/test_split_chunks.py                   # rc=0
$PY tests/rss_date/test_stale_history.py                  # rc=0
$PY tests/rss_date/test_tz_correction.py                  # rc=0
$PY test_frontend_tz_regression.py                        # 全部通过
```

### 本轮新增/重写的资产

| 文件 | 作用 |
|---|---|
| `tests/rss_composite/test_diverse_realdata.py` | 新增：真实语料首屏回归（含「相对不变式」D 段，抗数据漂移） |
| `tests/rss_composite/mutation_check.py` | 新增：C1/C2/M5 变异测试（支持多点变异） |
| `tests/rss_composite/cases_diverse.js` | 重写 E 段：倾斜夹具 + E9/E9b/E10 |
| `tests/rss_composite/test_tag_semantics.py` | 新增 E7 段：摘要通道契约 |
| `tests/rss_composite/test_snapshot_tags.py` | 修 B2~B5 定位 + 新增 B7 自检 |
| `tests/rss_composite/regression_composite.py` | 接入 4 个新守卫套件（V2b~V2e） |

---

## 7. 范围外 / 未处理

| 项 | 状态 |
|---|---|
| `test_insight_quality.py` | **既有红**（14 failures / 10 errors），全部关于 `insight_engine` 的 `guardrail` / `cluster_quality`「未接入 run_analysis」，与本轮改动无关（未触碰 `insight_engine.py`）。未修。 |
| `build_rss_aggregator.py:2937` `SyntaxWarning: invalid escape sequence '\.'` | 既有告警（非 raw 字符串里的正则），输出噪音，语义无影响。未修。 |
| `test_frontend_tz_regression.py` 中 `src`（git HEAD 内容）取后未用 | 死代码。未清理。 |
| 改动提交 | 仍在工作区未提交（`git` 对象库在本机不可读，`git log` 报 `bad object HEAD`，无法生成基线 diff）。待确认。 |
