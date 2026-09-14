# 复合排序方案 · 实施完成 + 对抗性审查

> 对象：`docs/superpowers/plans/2026-09-14-composite-sort-spec.md`
> 流程：Superpowers TDD（RED → GREEN → 提交），完成后红队对抗性审查
> 日期：2026-09-14
> 代码改动：`build_rss_aggregator.py` / `build_config.json`；新增 `tests/rss_composite/`

---

## 一、交付状态

### 提交序列（6 个，每步 RED 已验证）

| Commit | 内容 | 测试状态 |
|---|---|---|
| `18ae3f0` | test: RED `_tag_articles()` | AttributeError，RED 确认 |
| `b5e0d76` | feat: 实现 `_tag_articles()` | 9 passed |
| `988fca1` | test: RED `weightedShuffle()` | 抽取失败，RED 确认 |
| `2afdb2a` | feat: `weightedShuffle()` + diverse 模式 | 14 passed |
| `f4f6214` | feat: 打标先于分块接入 `main()` | 8 passed |
| `3b7670f` | feat: 配置接入 + 回归套件 | 16 passed |
| `2607ef9` | feat: 集成契约测试 D15/D16 | 19 passed |

### 测试总量

| 套件 | 断言数 | 状态 |
|---|---|---|
| `tests/rss_composite/test_tag_articles.py` | 9 | 全绿 |
| `tests/rss_composite/test_diverse_js.py` | 19 | 全绿 |
| `tests/rss_composite/test_composite_sort.py` | 8 | 全绿 |
| `tests/rss_composite/regression_composite.py` | 16 | 全绿 |
| `tests/rss_sort/test_rss_sort.py`（回归） | 26 | 全绿，零破坏 |
| `tests/rss_date/test_split_chunks.py`（回归） | 8 | 全绿，零破坏 |
| **合计** | **86** | |

### 改动清单

| 文件 | 位置 | 改动 |
|---|---|---|
| `build_rss_aggregator.py` | `:5227` 前 | 新增 `_tag_articles()`（27 行） |
| | `:2354` 前 | 新增 `weightedShuffle()`（50 行） |
| | `:2354` applySort | 新增 diverse 分支（11 行） |
| | `:2309` | sortMode 非法值回落白名单 |
| | `:2270` | `DIVERSE_WINDOW` 注入 |
| | `:2253` `_build_js` | 新增 `diverse_window_minutes` 参数 |
| | `:4923` `build_html` | 新增 `diverse_window_minutes` / `diverse_enabled` 参数 |
| | `:4982` | sort-select 新增「多样推荐」option（条件渲染） |
| | `:109` | `_load_diverse_config()` + `DIVERSE_CFG` |
| | `main()` | `_tag_articles()` 调用 + 传参 |
| `build_config.json` | | `diverse_enabled: true` / `diverse_window_minutes: 120` |

---

## 二、对抗性审查 · 第一关：变异测试（8/8）

方法：把源码改坏，用 `RSS_BUILD_SRC` 指向副本跑测试。测试不变红 = 没有守卫力。

| # | 变异 | 结果 |
|---|---|---|
| M1 | `threshold = totalW*0.5` → `*1.5` | KILLED |
| M2 | 窗口=0 分支失效 | KILLED |
| M3 | 标签改为摘要优先 | KILLED |
| M4 | `main()` 不再调用 `_tag_articles` | KILLED |
| M5 | applySort diverse 分支失效 | KILLED |
| M6 | sort-select option 条件反转 | KILLED |
| M7 | `DIVERSE_WINDOW` 注入值写死 | KILLED |
| M8 | 打标不过滤数值单位短语 | KILLED |

**第一轮只捕获 6/8，两个盲区已修复**：

1. **M4 存活** → `test_composite_sort.py` 的 C2 断言读死了 `ROOT/build_rss_aggregator.py`，对变异副本免疫。改为读 `RSS_BUILD_SRC`。
2. **M8 存活** → 没有任何用例含数值单位短语。补 A6（`3 亿美元` 不得成为标签）。

修复后重跑：**8/8 全部捕获**。

---

## 三、对抗性审查 · 第二关：真实数据量测

数据：`rss_api_snapshot.json` 8788 条有日期条目，quality map 1014 个源。

| 指标 | baseline（时间降序） | win30 | win120（默认） |
|---|---|---|---|
| 窗口内逆序对 | 0 | 171,500 | **645,774** |
| 前 150 位最大原始 rank | 150 | 150 | **215** |
| 前 150 位平均原始 rank | 75 | 75 | **136** |
| 前 150 位来自最新 5% | 150/150 | 150/150 | **150/150** |
| 前 50 位来自最新 2% | 50/50 | 50/50 | **50/50** |
| 前 200 位同源最长连续 | 11 | 11 | **11** |
| 确定性（两次调用一致） | — | — | **True** |

窗口结构：38 个窗口，最大窗口 674 篇。

**结论分两面**：

- **宏观时间序守住了**。前 150 位全部来自最新 5%，最大原始 rank 215（baseline 150）——diverse 不会把几小时前的旧闻顶到首屏。spec 的 Goal「保持时间维度可读性」在首屏粒度上成立。
- **微观时间序被打碎**。674 篇的大窗口内部被完全重排，645,774 个逆序对。窗口内相邻卡片的时间不再单调。

---

## 四、对抗性审查 · 第三关：端到端 smoke

用真实快照（518 源 / 8986 条）走完整链路，不联网、不落盘：

- 打标覆盖 **8983/8986 = 100.0%**
- HTML 231.4 KB，含 `DIVERSE_WINDOW=120`、`value="diverse"`、`weightedShuffle`、白名单
- chunk0 360 条 / chunk1 8626 条，序列化后含 `tags`
- **tags 载荷增量 +256.2 KB（全量 5234.9 KB 的 4.9%）**

标签抽样（英文术语质量好，中文存在碎片）：

```
Elvis Saravia：模型不会自己搞定 harness…   ['harness', 'elvis', 'saravia']
快速扩展在线存储以服务超过 10 亿 ChatGPT 用户  ['chatgpt', '快速扩', '展在线']
LLMjacking：人工智能模型劫持达到黑市规模      ['llmjacking', '人工智能', '模型']
活态类型论计算公共空间中的可信人机协作        ['活态类', '型论计', '算公共']
```

---

## 五、发现的缺陷（分级）

### P1-1 `quality = 0` 被当作「最低质量」，实际语义是「未评分」

`weightedShuffle` 用 `qm[sk] !== undefined ? qm[sk] : 50`，`0` 是 defined → 取 0。

实测 **1014 个源中 496 个（48.9%）quality 为 0**，包括 `google_deepmind`（0）、`google_ai_blog`（0）—— 这两家不可能是 0 分。权重 0 的条目在累积权重扫描中永远最后被选中，等于把近一半源系统性压到每个窗口末尾。

建议：`var w = qm[sk]; w = (typeof w === 'number' && w > 0) ? w : 50;`
**未改**：属算法语义变更，超出 spec 授权，需你确认。

### P1-2 同源连续没有改善（11 → 11）

spec 声称的收益是「同源最长连续 30 → 3」。实测前 200 位同源最长连续 baseline = 11，diverse（win120）= 11，**零改善**。

根因：算法按 quality 权重选取，没有任何「避免同源相邻」的机制。高信誉源权重大 → 在窗口内被反复优先选中 → 反而更容易连续出现。要真正打散需要按源配额（同源在窗口内出现 > k 次则延后）。

### P2-1 `tags[]` 目前没有消费者

`buildArt()`（`:2265-2281`）用显式字段白名单重建文章对象，不含 `tags`；diverse 模式也不用 tags，只用 `ANALYSIS_DATA.quality`。

即 Phase 1/3 产出的 **+256.2 KB（4.9%）是死数据**，直到主题聚类（Phase 5）落地才有消费者。建议：要么现在就让 diverse 消费 tags，要么等 topic 模式落地再写入 chunk。

### P2-2 `tierInterleave()` 会二次重排 diverse 输出

刷新路径 `_mergeRemoteSources()` 的顺序是 `applySort()` → `tierInterleave()`。后者把 ART 重排成「4 高频 + 1 低频」，会覆盖 `weightedShuffle` 的窗口内次序。spec Phase 5 约束 4 只写「仍执行」，未分析这个覆盖关系。

### P2-3 中文标签碎片

`快速扩`/`展在线`、`活态类`/`型论计`、`迈克·`。这是现有 `_tokenize()` n-gram 的固有行为（3 字优先贪心），不是本次引入。**未改分词器**——它同时服务 TF-IDF 关键词、洞察面板、主题聚类，改动是全链路影响。

### P2-4 窗口内时间序

645,774 逆序对（见第三节）。这是「信誉打散」的定义性代价，不是 bug。若不可接受，唯一出路是缩小窗口（win30 降到 171,500）或改用同源配额（不破坏时间序）。

---

## 六、实施中对 spec 的四处偏离（必须知会）

| # | spec 原文 | 实际做法 | 原因 |
|---|---|---|---|
| 1 | `ART = weightedShuffle(ART, _win, _qMap)` | 原地替换（`ART.length=0` 后 push） | 重新绑定会让 `window.ART` 及持有旧引用的闭包失效 |
| 2 | `_tag_articles` 读 `title_zh`/`title`、`summary_zh`/`summary` | 追加兼容 `t`/`s` | 刷新通道与快照契约是 `t/u/s/d`，只读 title 会让 V1 覆盖率 = 0% |
| 3 | 只改 `build_html()` 签名 | 同时给 `_build_js()` 加参数 | `DIVERSE_WINDOW` 在 `_build_js()` 内注入，不加参数会 `NameError` |
| 4 | D8 标题「quality 全相等时保持输入顺序」 | 改为「同输入同输出」 | 实测 n=3 等权输出 `[b,a,c]`，不保持输入顺序；断言逻辑未改，仅标题更准确 |

另外补了 6 条 spec 没有的用例：D12（diverse 条目守恒）、D13（窗口=0 与纯时间降序逐条一致，V2 的可执行形态）、D14（任意窗口条目集合守恒）、D15（topic 不走打散）、D16（非法 sortMode 回落）、A6（数值单位短语过滤）。

---

## 七、可复现

```bash
python tests/rss_composite/test_tag_articles.py      # 9
python tests/rss_composite/test_diverse_js.py        # 19
python tests/rss_composite/test_composite_sort.py    # 8
python tests/rss_composite/regression_composite.py   # 16
python tests/rss_sort/test_rss_sort.py               # 26 回归
python tests/rss_date/test_split_chunks.py           # 8  回归

python .workbuddy/_mutate.py      # 变异测试 8/8
python .workbuddy/_adv_real.py    # 真实数据量测
python .workbuddy/_adv_smoke.py   # 端到端 smoke
```

输出落在 `.workbuddy/_mutate.txt`、`_adv_real.txt`、`_adv_smoke.txt`。

## 八、未做的事

- **未跑完整构建**（需联网抓 1014 个源）。所有验证走离线路径，产物等价性由 `_split_data_chunks` + `build_html` 直调保证。
- **未改算法语义**（P1-1 / P1-2）。这两条需要你拍板，改了会让 D5 等既有断言的含义变化。
- **Phase 5 主题聚类**按 spec 只落集成契约（D15/D16 + 代码注释），功能实现引用 `2026-09-14-rss-topic-clustering.md`，本次不动。
