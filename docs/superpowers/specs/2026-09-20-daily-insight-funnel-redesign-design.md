# 深度洞察漏斗化改造：主报告排序目标并列化 + 破茧栏排除式漏斗

日期：2026-09-20　状态：待用户复核
决策来源：用户判断"深度洞察不该用 RAG 架构跑"→ 选定改动层级为**换排序目标**（非整条重构、非只补通道）→ 追加指定**破茧栏走漏斗**。

---

## 1. 问题定位（逐条可核对，全部带代码或数据出处）

通用漏斗的六段职责里，本管线**不缺阶段实现，缺的是决策放在哪一层**。实测：

| # | 事实 | 出处 |
|---|---|---|
| F1 | 候选集在加权之前就被相似度定死：`_hybrid_retrieve` 按 query→RRF 截 `top_k=200`，之后所有时间/共振权重只乘在 `retrieval_score` 上 | `:5303` `:913-1021` `:1057` `:1373` |
| F2 | 时间维确实存在（`RECENCY_HALF_LIFE_H`、`ACCEL_*`、双热度），但位于截断之后 → 只在幸存者身上微调 | `:134-137` `:1258` `:1333` |
| F3 | `best_score = 簇内单条 chunk 最高检索分` → 一条强相似即可带全事件上位 | `:1340` `:1126` `:1153` `:1242` |
| F4 | 跨源共振 `n_types = len(source_types)`，而 source_type 仅 rss/hot/agihunt/aihot 四类 → 15 家转载同一事件只 +1，共模转载拿不到加分 | `:1343` |
| F5 | `_build_queries` 的 query 来自 AGI Hunt / AIHOT / 热榜 Top15 标题，而 `_compute_dual_heat` 又拿同样榜单当打分参照 → 检索自指，代码级坐实 | `:1074-1091` `:1274` |
| F6 | 加速度判定要求簇内带日期 chunk `> 2` → 从 0 爆发的新事件恰好拿不到 accel 加成 | `:1361` |
| F7 | 成题层不存在；`resonance` 只是单事件的源覆盖四象限，不是跨事件主题形态 | `:1319-1328` |
| F8 | momentum 无法计算：`daily_insight_history.json` 仅 4 天、日粒度，`sources` 存类型不存信源；`_aggregate_per_event` 的"跨样本"指同场内多个 RAGAS 评估样本，非跨构建 | `:3767` 实测文件 |

结论：**RAG 不该当主干，但该退回去的位置只有两格**——事件归一（已做对，F 表无一条指向它）与最后一层证据供给。

## 2. 破茧栏：唯一的低风险试验田

破茧 `:5523` 传 `all_chunks=chunks`，`:3266` 直接按 `topic_tag` 过滤全量池，**不经 query / FAISS / RRF**——它是全系统唯一已脱离 RAG 主干的模块。其实测缺陷：

| # | 事实 | 出处 |
|---|---|---|
| B1 | 破茧池仅 2659/26944 = **9.9%**；`other` 达 7882 = 29.3% 且按设计不进破茧 | 实测 chunks.json |
| B2 | `_bubble_heat = hot×0.5 + recency×0.3`，而破茧池 2659 条中 **hot>0 的为 0 条** → 实际等于纯按时间排序 | `:3246-3251` 实测 |
| B3 | 9-18 设计的第三因子"跨平台出现次数×2×0.3"在代码中**整项缺失**，权值和从 1.0 掉到 0.8 | `:3251` vs 记忆记录 |
| B4 | `read_profile` 路径 1 完全不参与筛选/打分，仅拼文案 `"与你常读的科技领域不同"`；且 `_build_read_profile` 统计的是**本站近 7 天自己发过的 category**，无任何用户行为数据 | `:3213-3222` `:3244` `:3281` |
| B5 | 破茧 `summary = text[:200]` 截断原文，LLM 不参与 | `:3278` |
| B6 | 归一仅标题级贪心 `_same_topic`，依赖 pool 顺序；主报告有 `_semantic_merge` 而破茧没有 | `:3273-3274` |

方向修正：用户 9-18 原话为"**按聚类分，在 AI/科技外的内容再做精选**"。v2 实现成"词表正向识别 + 热度排序"，两处偏离——该排除的改成了识别，该聚类的是没做。本方案是**回归原话**，不是新方向。

## 3. 关键度量：把词表从"准入器"改成"否决器"

`rss_sources.json` 的 `cat` 是人工维护的**源级**领域标签，实测 603 个源出现于 chunk 中，**cat 多值的源 = 0**（100% 稳定），chunk.cat 覆盖 98.1%。但 `_load_rss_tiers:312-314` 只读 `key`/`tier`，**把 cat 丢了**。

词表在通用新闻源上的失败率：`cat=news` 4561 条 → 3202 条（**70.2%**）被判 other；`cat=wechat` 8003 条 → 4037（50.4%）判 other。

`cat == topic_tag` 仅 **16.3%** → 源先验与词表是两个不同信号，不冗余。

词表性质是 precision 高、recall 低：
- 当准入器（现行 `tag ∈ BUBBLE_TOPICS` 才进池）→ 直接吃低 recall → 丢 70%。
- 当否决器（源先验进池，仅 `tag ∈ {ai,programming}` 才踢出）→ 用其高 precision，误踢少：`cat=news` 中仅 486 被判 ai → 否决后**剩 4075 条，单 news 一类即超现行全池 1.5 倍**。

排除式总池：`topic_tag ∉ {ai,programming}` = **10541 条 = 39.1%**（现行的 4 倍）。

### 域名信号：实测后降级
外链域名覆盖率 100%，但判别力**方向不对称**：
- 判 other 的 7882 条中带科技域名 **0.1%** → 科技漏进破茧的比率极低
- 判科技的 16403 条中带科技域名仅 **13.7%** → **域名认不出科技**
- `cat=news` 的 other 部分带新闻域名 **51.8%** → 域名只能**确认新闻性**

故域名降级为精排的"新闻性确认"特征，不作否决器。`wechat/twitter/podcast`（8581 条）的漏标率**无法用域名测出**（窄表对中文自媒体正文不适配）——这块不确定性用"收窄第一版范围"管理，不靠新增判定器去赌。

## 4. 设计

### 4.1 主报告：排序目标并列化（P 线）

```
现:  final_score = retrieval_score × recency × platform_w × rss_w × agihunt_w
     score       = best_score × cross_mult × recency × accel_mult
新:  score(event) = w_m·momentum + w_s·n_src + w_f·freshness
                           + w_d·depth + w_q·quality + w_c·similarity
```

四处语义变更，均为改语义而非新增逻辑：
1. `best_score` 的 `max` → 簇内聚合 `mean × (1 + min(3, log2(n)))`。用 log2 而非线性 sum：sum 会直接奖励转载条数，那正是第 2 点要压的共模因子；且 `mean + λ·sum` 在单条时会放大原分，破坏"单条簇分数等于该条分数"这条可核对基线。
2. `n_src` 数独立 `source_key`（现成字段），不数 `source_type`。挡住 F4。
3. `w_d`/`w_q` 直接吸收 `_quick_score_event` 现成四维（深度/科技相关性/事实密度/新颖度，40/30/20/10），把它从"55 分闸"升为"排序项"。
4. 候选入口从单一变多路：`RRF top200 ∪ momentum topK ∪ fresh topK ∪ 源先验直供`，解决 F1。

> **顺序依赖（勿读成同期）**：第 4 项的"源先验直供"在 P 线**第二期**才引入，前提是先由 B 线证明 `cat` 源先验可用（池纯度达标）。P 线第一期只做 1~3 项 + momentum/fresh 两路——这两路不依赖 `cat`，风险独立。把源先验同时压进两条线会让 B 线的纯度问题变成 P 线的回归故障。

**新建唯一持久件**：`insight_event_signals.jsonl`，每场追加 `{ts, sig, n_src, src_keys, first_seen}`；`sig` 复用 `_dedup_tokens`/`_norm_url`，不引入新指纹。momentum = 近 **N 个场次**（非 N 小时——实测约 47 场/天且频率会变）该 sig 出现次数做差分，N=24。该账本同时提供趋势维的事后自动标注。

### 4.2 破茧：排除式漏斗（B 线）

| 段 | 做法 |
|---|---|
| ① 召回 | 基础池 = `cat == "news"`（v1 仅此一类），168h 新鲜窗 + 排除主报告 URL/标题；词表降级为否决器（`tag ∈ {ai,programming}` 才踢） |
| ② 归一 | 分批 FAISS 局部索引 → top-K 近邻连通分量 → 簇内用现成 `_same_topic` 收边。**不得**直接对万级跑 `_semantic_merge`（贪心 O(n²)，float32 Gram ≈ 444MB） |
| ③ 精排 | 簇分 = 独立 `source_key` 数 + tier 加权 + 新鲜度 + 新闻域名确认；删除恒零 `hot` 项；补回 B3 丢失的跨源因子 |
| ④ 成题 | Top 5 卡跨簇取样保多样性；输出形态信息（跨 N 家独立信源 / 近期第 N 起同类） |
| ⑤ 综合 | summary 过 LLM，不再 `text[:200]` 截断 |

**v1 范围刻意收窄**：`wechat/twitter/podcast` 8581 条平台源**第一版不进池**（漏标率无法实测），单 `cat=news` 已有 4075 条候选、超现行全池 1.5 倍，足够验证漏斗形状。B4 的 `read_profile` 从破茧签名删除（按符号清单全仓断言清除，`py_compile` 查不出 NameError），并改掉误导文案。

## 5. 明确不做

- **不改 `TOPIC_TAXONOMY`**（顺序敏感、`ai` 必须第一的不变量；破茧单点验证更干净）。
- **不做 agent 全量二分类**：域名实测科技漏进 0.1%，且 judge 噪声带 ±0.05 不适合做全量数值判定。仅保留簇级抽样人工核。
- **不碰 claim 层 / 多路查询扩面 / rerank 扩面**：G1/G2 设计文档的"明确不做"理由仍成立。
- **不动 `MAX_EVENTS=12` 输出预算**。

## 6. 验收口径（本节是方案能否被判断的前提）

**现有 RAGAS 三维无法验收本次改造**，三条独立理由：

1. 破茧不在评估面内：`_evaluate_report_quality(llm, clusters, theme, context_text)` 签名无 `bubble_breaker`，且破茧在 `:5523` 晚于 ragas_eval 计算。
2. 召回扩面对 cov 不可见甚至有害：judge 的对照面就是那 200 条上下文，扩面等于放大分母（G1/G2 v2 文档已记"cov 提升是零和的"）。
3. 历史达标率不可直接继承：`passed=true` 但三维未达线的行 **24/43** 属**修复前**样本——R14-9C 已把 `:5072` 改为 `_verdict(ragas_eval, threshold)`（与同行分数同源）。因此 43 行里修复前/修复后必须**分段统计**，混算会同时高估基线、低估本次改造。另 n=7 终版与 n=37 全量相关系数差一个量级（`chunks_total↔overall` 分别 −0.80 / −0.24），且同批 `chunks_total~agihunt` 共线性 +0.97 → 幅度只认 n=37。

因此：
- **P0 前置**：口径对齐（`passed` 已由 R14-9C 修好，P0 不再修它，改为**按修复时刻分段**）。统计一律拉**远端** `daily_insight_tracking_history.jsonl`（CLAUDE.md 明令：CI 只写远端，本地副本陈旧——本方案 §1/§6 引用的 `_track_stats.txt` 属本地派生物，落实施前须用远端重测）。
- **破茧自建指标**：池纯度（人工抽 30 条判非科技比例）、簇数、独立信源数分布、Top5 跨簇度、hot 项替换前后的排序变化率。
- **主报告**：新增事件来源分布（扩面对指标不可见，只能这样观测）+ 趋势事后标注（今场判 momentum 高者，24 场后是否仍在涨）。

## 7. 约束与不变量

- `TOPIC_TAXONOMY` 顺序敏感、`ai` 必须第一（不破，见 §5）。
- 证据包全文不得作为 citations `[n]` 编号来源。
- `_norm_url` 归一化是唯一 URL 比较口径；`naive/aware` 时间必须走 `_parse_iso`。
- 消费新字段一律 `(x.get(k) or "")` 双防（旧缓存 chunk 无新字段）。
- 门禁 B `continue-on-error: true` 且清空六个 API key → 只认日志 `[0-9]+ failed/passed` 汇总行；本地同构复跑须照抄 CI 环境。
- 新测试目录必须与 `update.yml` 同一次提交落远端（A2 blocking + Deploy 无 if 耦合）。
- 依赖时序/场次的测试不得裸进 blocking 门禁。
- 推送走 `tools/data_api_push.py`，`update.yml` 列入禁推；禁止在有未完成 run 时推送。

## 8. 待用户拍板

1. P0 口径修复是否与 P/B 并行开工（我建议先行 1 期，否则改完无法归因）。
2. 破茧 v1 是否接受"只用 `cat=news`"这一收窄范围（代价：放弃 8581 条平台源，其中确有 finance/society/culture 好内容）。
3. `insight_event_signals.jsonl` 是否纳入 §11 守门与漂移核查流程。
4. momentum 按"场次"取窗口意味着构建频率变化时历史窗口需重新对齐——是否接受。
