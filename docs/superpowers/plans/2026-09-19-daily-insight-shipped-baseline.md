# 每日洞察 · 终版口径观察期与候选方案（第13轮 R13）

**制定时间**：2026-09-19 16:50（北京时间）｜**远端基线**：`6f1736ac`（第12轮，终版复评上线）
**依据文档**：`docs/superpowers/specs/2026-09-19-daily-insight-g1g2-design.md`、`...-v2-judgment.md`（G1/G2 与四条分歧的原始判断，**仍是现行依据**）
**为什么需要这份文件**：上一版计划（`docs/superpowers/plans/2026-09-18-daily-insight-quality-redesign.md`）落地后 41 个步骤框一个没勾、且"RAGAS/检索/聚类全部不动"的范围声明已被第 6-12 轮超越 —— 那是"计划未随实现更新"的反面教材。本文件的每个勾都必须对应一条可核对的证据。

---

## 0. 一句话现状

每日洞察的**内容管线已经能用**（12 事件、每条带可跳转原文链接、faith 0.95、重复事件与文不对题消除）；
卡住的是**测量**：过去两周所有 cov/rel/faith 都打在"missed 回收与终局去重**之前**的草稿"上。第12轮修好了这件事，
于是本阶段的靶子从"再改内容"变成"**用干净的尺子重新认识这台机器的波动**"。

## 1. 基线事实（全部可指到日志/产物，勿凭记忆改动）

| 事实 | 数值 | 出处 |
|---|---|---|
| 首场终版口径构建三维全绿 | overall 0.83 / cov 0.75 / faith 0.95 / **rel 0.80** | run `35431790984` 日志 `终版复评:` + `daily-insight.json → quality` |
| 同一场的草稿分（对比） | overall 0.80 / cov 0.75 / faith 0.95 / **rel 0.70** | 同上 `quality.meta.draft_eval` |
| 审计台账恢复 | `meta.call_log` 3 条 `{model, status, elapsed_s}`（此前为 `[]`） | 同上 |
| 红线保持 | 12 事件 / **12 条带 key_links**；线上页 12 张卡片均含 `di-link` | `daily-insight.json` + https://Kwei168.github.io/starhub/ai-daily.html |
| 判定域护栏今日未咬 | `context_chunks=200 cited_extra=0 truncated=false` | `quality.meta` |
| 字符预算实测（26944 块全量库） | 随机 200 块：median 10.5 万字符、p90 11.1 万；整库最长 200 块才 22.2 万 → 14 万预算在真实选取下咬不到 | 本地脚本测于 `daily_insight_chunks.json` |
| 36 期草稿口径统计 | 三维同时达标仅 3 期；sd：cov 0.078 / faith 0.133 / rel 0.067 | `daily_insight_tracking_history.jsonl` |
| 共模因子证据 | 三维彼此 r=0.53~0.63、与 overall r=0.81~0.87；`agihunt_count` 与 rel/faith **r=-0.25/-0.23** | 同上 |
| **已撤回的假设** | "为凑满 12 槽塞边缘条目拉低 relevance"：`total_events` 与 rel 的 r=**-0.02**，按事件数分桶 rel 为 0.711(9-11)/0.683(≤8)/0.680(≥12) | 同上（30 期有效样本） |

## 2. 阶段 A（现在就做）：终版口径观察期，不动产报逻辑

目标：攒 2-3 期**同一口径（`meta.eval_stage=shipped_report`）**的连续数据，看清真实波动幅度，再决定要不要动内容。

### 2.1 逐期台账（终版口径，每行都来自 run 日志 + 产物字段）

| # | 期次(UTC) | run | 事件/带链接 | shipped cov/faith/rel | draft cov/faith/rel | eval_stage | warning | 回收环 | 评审 agent |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 08:40Z | `35431790984` | 12 / 12 | 0.75 / 0.95 / **0.80** ✅ | 0.75 / 0.95 / 0.70 | shipped_report | 0 | 回收 2 条候选 | 二审否决 1 组 |
| 2 | 09:17Z | `35433508066` | 10 / 10 | 0.75 / 0.90 / **0.70** ❌ | 0.75 / 0.95 / 0.80 | shipped_report | 0 | 17→2 组、3→2 组、14→2 组，末次"无合格新事件" | 二审否决 **3 组** |

**第 2 期读出来的东西（本期人工挖日志，正是阶段 C 要自动化的部分）**：
- 方向第一次反过来：终版分**低于**草稿分（rel 0.80→0.70、faith 0.95→0.90）。第 1 期是终版更高，说明终版分不是"更宽松"，是真在量另一份产物。
- 修正环被采纳后（0.78→0.83）改写了 5 条事件，其中 10、11 号被写成两条阿里 Qwen 报道（`阿里发布全模态Agent模型Qwen3.8-Omni-Flash` 与 `阿里发布Qwen3.8-Omni-Flash全模态模型`），终局去重 15→14 才收掉 —— **修正环仍在制造重复**，靠去重擦地。
- rel 失分对应的内容构成可点名：10 条里有 2 条硬件/产业（`AMD 256核 EPYC 跑分`、`国产算力集群时代`editor 52）+ 1 条榜单（`Grok Imagine 跃升第四`）+ 1 条存疑（`GPT-6破译一战密码引质疑`）；
  judge 同期报的 missed 里第一名是 `Neuralink 失语患者原声说话`。**"凑槽"与"漏头条"同时发生，但事件总数与 rel 无关（r=-0.02 仍在）—— 起作用的是构成，不是数量。**
- 采纳判定本身用的是草稿刻度：0.83 采纳、终版 0.78。修正环优化的是"将被改写的中间产物"，终版分却无人守护 —— 这是观察期发现的**新架构问题**，登记在此，不动产报逻辑（§6）。


每期核验清单（缺一项不算完成该期）—— **第 1、2 期六项全部核过**（见 §2.1 台账；`context_truncated=false`、`cited_extra=0`、`call_log` 各 3 条、`degraded=false` 亦已确认）：
- [x] `quality.meta.eval_stage == "shipped_report"`（若为 `draft_only` 或 `degraded=true`，该期**不计入**趋势，只记原因）
- [x] 三维数值 + `meta.draft_eval` 一并抄进追踪记录（两列口径都要留）
- [x] `events` 数与 `with_links` 数相等（红线：一条不落）
- [x] 日志出现 `missed 回收` 或 `无合格新事件`（回收环活着）
- [x] 日志出现 `二审否决` 或合并实际生效（评审 agent 活着）
- [x] `::warning` 数量（终版复评降级、上下文截断都该是 0；出现即排查）

**收单口径（待用户二选一，默认按 ①）**
- ① 连续两期终版口径 `cov≥0.75 ∧ faith≥0.88 ∧ rel≥0.75`；
- ② 5 期里 3 期达标且无退化趋势（草稿口径下单期达标率约 10%，①可能要等 10 期以上）。

## 3. 阶段 B（与观察期并行，只写设计不上线）：对照面蒸馏清单（分歧2 的 (b) 支）

**问题**：judge 的对照面是"当期检索到的 200 条原始 chunk"。每期池子构成不同 → 分母在漂 → cov/rel 一起被抬或压，
这就是第 1 节测到的共模因子最可能的解释（`agihunt_count` 负相关是唯一有意义的输入耦合，指向"二手摘要素材占比高→读分低"）。

**方案**：评估前先让模型从池内提炼一份**当日要点清单**（top 信息点，条数固定，如 15±3），
再把 cov/rel 的对照面从"200 原始块"换成"这份清单"；原始块继续留给 faith 当证据域（faith 的判定域必须 ⊇ 引用域，这条不变）。

**可检验预测（做之前先写下，防止事后找理由）**：
1. 三维两两相关系数从 0.53~0.63 明显下降（共模被拆掉）；
2. rel/cov 的标准差下降（同期之间更可比），而**均值不因口径变松而上抬**（若上抬说明清单比原池更容易满足 = 自我打分，方案作废）；
3. 事件内容与换口径前无可观察差异（纯测量层改动）。

**硬约束**：口径一变，历史序列断裂 —— 必须在 `quality.meta` 写 `comparison_surface: "raw_pool_200" | "distilled_list"`，
且 HANDOFF 与本文件同步登记切换时点；禁止用混合口径做趋势图。
**启用条件**：阶段 A 收满 ≥3 期终版口径数据，且 cov 或 rel 仍未稳定达线。

## 4. 阶段 C（后备方案，观察期后才考虑实施）：逐事件归因埋点

**动机**：现在每期只有一个笼统的 rel/cov 标量，无法回答"是哪两条事件把分拖下来的"。
judge 其实已返回 `weak_events`（1-based 索引）与 `reasoning.relevance.irrelevant_events`，但没落盘。

**最小实现**（纯观测，不改产报）：
1. `_evaluate_report_quality` 解析处把 `irrelevant_events` 随 `weak_events` 一起返回；
2. `_median_eval_samples` 对两者做与 missed_points 同样的共现归并（防三样本措辞漂移）；
3. `quality.meta.per_event` = 每条事件 `{index, label 摘要, flagged_by: n/3, reason_class}`；
4. 事件级"证据来源构成"：`{primary_rss_fulltext, feed_snippet, hot_list_title, digest_secondary}` 四类占比（回收事件尤其要看这一列，它决定 judge 是否有原文可核）；
5. 只写 JSON，不接任何阈值闸；连续 2-3 期后统计"被点名的事件"是否稳定集中在某类来源，再决定内容改动打哪里。

**为什么排后备**：它不改产物；而阶段 B 若成立，会先解释掉大部分波动 —— 先做 B 的判断成本更低。

## 5. 决策树（触发条件 → 动作，别提前动）

| 观察期结果（终版口径，≥2 期） | 动作 |
|---|---|
| cov≥0.75 ∧ rel≥0.75 ∧ faith≥0.88 持续 | 收单，转去做产品侧（③多路查询扩面：以"新增事件来源分布"单独观测，**不许拿 cov 自证**） |
| 只有 cov 不达标 | 阶段 B 对照面蒸馏上线（先小流验证预测 1/2/3） |
| B 之后 cov 仍不达标 | 才提分歧2(a)：`MAX_EVENTS` 12→16（页面变长，**产品决策，需用户拍板**） |
| 只有 rel 不达标 | 阶段 C 埋点，先定位是哪类来源/哪类事件，再谈选题 agent |
| faith 跌回 <0.88 | 查 `call_log` 与 `degraded`，其次复查证据包归属标注；claim/实体中间层重新立项 |
| 出现无链接事件 | 立即热修（红线优先级高于本文件一切排期） |

## 6. 明确不做（沿用 G1/G2 文档，理由仍在）

- **rerank**：候选池未扩面前重排无意义（原判断仍成立）。
- **claim/实体中间层**：faith 已 0.95，降级为后备；仅在第 5 节"faith 跌回"分支重启。
- **`build_rss_aggregator.py` 全文抓取扩面**：另一会话在途，不并行碰。
- **动 12 事件预算 / 改评分口径**：均需用户显式拍板，且必须先有终版口径 ≥3 期数据。

## 7. 执行纪律（每轮照旧）

复现原因 → TDD（新测试必须用变异体证明能失败）→ 精准修改 → fresh-eyes subagent 对抗审查（**前台派发，用户要过程可见**）→
`py -3.11 -m pytest tests/daily_insight -q -s` + 根测试四件与 CI 同构 → 读 CLAUDE.md → pathspec-only 提交（他人在途文件不入库）→
Data API 推送（LF 归一）→ 触发/等整点构建 → 按第 2 节清单核验产物。

**CI 同构检查（不可跳过，2026-09-19 因跳过而把红测试推上线两次）**：门禁 B 会把
`AGNES_API_KEY / AGNES_API_KEYS / SILICONFLOW_API_KEY / ZEN_API_KEY / OPENROUTER_API_KEY / AGIHUNT_API_KEY` 全部置空
（`.github/workflows/update.yml` 的 Quality gate B env 段），任何依赖真实 key 的断言在本地绿、CI 红。
推送前必须原样复跑一次：

```
export AGNES_API_KEY= AGNES_API_KEYS= SILICONFLOW_API_KEY= ZEN_API_KEY= OPENROUTER_API_KEY= AGIHUNT_API_KEY=
py -3.11 -m pytest tests/daily_insight/ -q
for f in test_insight_engine.py test_insight_guard_v3.py test_insight_bad_date.py test_daily_insight.py; do py -3.11 "$f" >/dev/null; echo "$f exit=$?"; done
```

另：`tests/daily_insight/` 里的测试文件改完必须**确认已推到远端**——本地提交 91d4de5 只改了测试未推送，
导致 CI 仍在跑被退役的旧契约断言（`test_small_history_single_file`），报的错与被改的东西毫无关系，极易误诊。

## 8. 进度

- [x] 第12轮终版复评上线并在生产验证（`6f1736ac` / run `35431790984`）
- [x] G1/G2 设计文档从 `~/Downloads` 搬入 `docs/superpowers/specs/` 并加落地状态横幅
- [x] 撤回"凑 12 槽拉低 rel"假设，改用 36 期统计（相关系数 -0.02）
- [x] 阶段 A：终版口径第 2 期数据到手（`35433508066` / 09:17Z：rel 0.70 未达线，cov/faith 达线 → 命中 §5"只有 rel 不达标"分支）
- [ ] 阶段 A：第 3 期数据到手（run `35436215090`，10:00Z 进行中）→ 与第 2 期合并判定阶段 B 是否启用
- [ ] 阶段 C：**触发条件已满足**（终版口径 ≥2 期 + 只有 rel 失分 + 人工挖日志才能点名失分事件）—— 待用户点头即实施
- [ ] 阶段 B：蒸馏清单设计定稿 + 三项可检验预测写清验收方式
- [ ] HANDOFF.md 登记观察期结论与口径切换时点（若 B 上线）
- [ ] 收单口径 ①/② 由用户确认

> **暂停点 / 下次开工接续（2026-09-19 17:05 北京时间，用户下令下班）**
> - 远端 HEAD：`4658f109`（终版复评 + 审查复修 + 计划落盘 + CI 同构测试修复，均已推达远端）。
> - 正在跑：run `35433508066`（09:00:27Z 触发），它是**观察期第 2 期**候选样本。
>   下一件事只有这一条：跑完按第 2 节 6 项清单核 `daily-insight.json → quality`（重点 `meta.eval_stage` 是否为 `shipped_report`、
>   `with_links` 是否等于事件数、`::warning` 是否为 0），把 cov/faith/rel 与 `meta.draft_eval` 一并记进本文件第 1 节表格。
> - 那场构建的门禁 B **实际为绿**（测试修复推在其 checkout 之前，比预期快一步）。原预测"红一次"作废；
>   今后若门禁 B 变红，先比远端 `tests/daily_insight/` blob 与本地是否一致，再怀疑代码。
> - 本会话未动 `build_rss_aggregator.py` / `update.yml` / `rss_fetch_state`（他人在途）。
