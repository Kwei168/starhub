# 夜间独立深度洞察管线（deep-insight）· 设计规格

- 日期：2026-09-22　状态：已批准，阶段 1 实施中
- 决策链：本文每节都注明"被哪一轮证据逼出来"，避免后来人看不出约束的来由
- 批准记录：`.qoder/plans/infinite-mesa-cod.md`（同一内容，经五轮质疑修订）

## 1. 为什么做（全部为现测读数）

**太重**：`fetch_and_build.py:836-837` 无条件调 `build_daily_insight.main()`，不传 mode、无 `if`，唯一闸是 `daily_insight_enabled`（`build_daily_insight.py:5307`，默认 true）。09-21 21:00→09-22 03:00 **连续 7 场全跑**，单场 304–424s（均值 **351.8s**）＝构建步 38.7%、整 job 28.3%；按 24h 内 27 场完成算 **≈2.6–3.0 小时/天**，其中约 24 场非夜间。`2026-09-16-rss-timeliness-enhancement-design.md:102` 已记"免费 2,000 分钟/月 已超额"。

**太浅**：09-22 现网 `daily-insight.json` 9 个事件里仅 **3** 个有 `deep_analysis`（1739/2103/1954 字），另 6 个正文 **162–301 字**；近 6 天深挖名额恒 2–3（`DEEP_ANALYSIS_TOP_N=3` `:148` + `MIN_DEEP_SCORE=55` `:2328`）。千字密度：因果 0.4–1.1、预测 1.4–3.5（下滑中）、内容优质判断 ≈0（全文 8137 字里质量词 1 次）。

**浅的机制定位（推翻了我最初的判断两次）**：
1. 长文进检索池保留率实测 **100%**（3000→3000、20000→20000），`:596` 的 `text[:3000]` 是 no-op —— 切片层无罪；
2. 深度名额被 `TOP_N=3` 卡死，且四维里"信号深度 0-40"实为**素材量代理**（`:2366`）且**不进 prompt**；
3. `insight_engine.load_documents:314-316` **只读 `summary[:300]` 再压 `[:500]`、不读 `full_content`**，`max_documents=500`（RSS 配额 350）；`Trending:302` 是 `desc = repo` 自指垃圾；
4. 素材进模型前再切：`body[:800]`（`:2146`，有全文时 2500）、`evidence[:8000]`（`:3196`）、`_ragas_ctx[:12000]`（`:5558`），且 **judge 自己只看到 `[:200]+[:150]`**（`:3683-3685`）—— 判定方被截断却要给"论述深度"打分。

**素材可得性分层（决定谁能当内容源）**：公众号 380 源 / 168h 内 2604 条 / 全文覆盖 **100%** / 中位 **5706 字** ✅ 支柱；行业媒体·博客 277 / 2496 / **27.7%** / 3699 ✅ 次选；学术 9 源 445 条、arxiv 系 **0% 全文** ⚠ 只当信号；传统媒体 50 / 2405 / **5.2%** / p50 243 字 ⚠ 只当信号；X 动态 160 / 791 / **0%** ⚠；AIHOT 无全文（摘要 med 137 / p90 196）、AGI Hunt items 是快讯且无 key 时 401（其深度在未调用的 `/report` 端点）。

**需求侧如实记录**：仓库里没有任何文档规定每日洞察须"只在夜间/跟全量一起"。该约定确实存在过但主语是 `insight_engine` 的重分析（`2026-09-14-insight-optimization-spec.md:12/82-96`，默认 6h），而 `HANDOFF.md:757` 写明两条洞察线"完全独立"。本 spec 是**新增契约**，不是恢复原设计。

## 2. 四条深度判据（用户定义，逐条可测）

| 判据 | 合格线（每一条目各自计） | 判定方 |
|---|---|---|
| 成文论述 | `narrative` **2500–4000 字**、**≥6 段**、必须含反证或限制条件；条目体（分点罗列）直接判不过 | judge 按 rubric 主判 |
| 因果分析 | `causal_chains` **2–6 条**，每条 trigger/mechanism/outcome ≤170 字 | judge 主判 |
| 趋势预测 | `forecasts` **1–4 条**，每条 ≤80 字 + `horizon_days∈{3,7,14}` + 非空 `check_metric`；**落 `predictions.jsonl` 供到期对账** | 结构校验 + 次日对账命中率 |
| 内容优质判断 | `quality.verdict∈{一手,深度,数据支撑,转载,通稿,营销}`、`score 0-100`、`why 20–120 字` | **不由生成方自评**：`source_quality.json`（`build_rss_aggregator.py:6603→7441`）+ AIHOT `score/selected` + 跨源同稿计数 |

阈值：rubric 均值 <0.75 → 按薄弱维度重生成，上限 2 次；仍不过 → 整条转 `degraded`（≤200 字快讯、**不许产预测**、不计入"合格洞察数"）。`citations` 5–12 条且 id 必须指向真实存在的 chunk —— 假链接＝硬失败。结构指标（字数/条数/枚举）只做硬门与告警，**不当质量代理**：现网因果密度 1.0/千字已证明关键词计数会被模板骗过。

## 3. 阶段 1 边界：纯新增，定时任务零影响

- 新增：`build_deep_insight.py`、`.github/workflows/deep-insight.yml`、`tests/deep_insight/`、产物 `daily-deep-<date>.json` / `deep-insight.html` / `predictions.jsonl`。
- **不改**：`update.yml`、`fetch_and_build.py`、`build_daily_insight.py`、`build_rss_aggregator.py`、`insight_engine.py` 的任何行为。
- **改判（原写"后三者只 import 复用 `_SYS_ANALYST_PROMPT:1280`、`_evaluate_insight_quality:1516`、`_self_correct_insights:1576`、`_PLATFORM_DNA:1299`、推脱语清洗 `:1265`"，实施时作废）**：引一条 import 就把 5000 行白天模块的模块级副作用与 llama-index/faiss 依赖带上夜路，与 §4 的隔离承诺和"夜场不装重依赖"直接冲突；而且白天那套系统提示是为 300 字快讯写的，与 §2 的 2500–4000 字契约相互抵消。夜场自带 prompt。判据：`test_nightly_does_not_borrow_daytime_modules`（只看 import 语句，注释里引白天行号是有意留的证据链）。
- 夜间**自带上下文组装**：读 `daily-insight.json`（只读）+ RSS 分块 `full_content` **整篇**，因此绕开 §1 列的全部白天截断点 —— "读得全"不等白天改造。
- 上下文预算：默认 **≤400k token/条目**、材料厚时 ≤800k（1M 的 40–80%）；预算内整篇给，超预算**丢整篇不丢半篇**并记 `dropped_articles` 与理由。
- 待验假设（不许当结论）：`max_tokens=3000`（`:3242`）疑似输出天花板。第一步用真模型跑 2500–4000 字看是否被截；确认前不动白天常数。区分：**1M 是上下文窗口，不是输出长度**（风险⑥）。

## 4. 并发与隔离（用户点名的硬要求）

**跑**：`concurrency.group: deep-insight` + `cancel-in-progress: false`，与 `starhub-update` 不同组 ⇒ 白天整点场砍不到夜场、夜场也砍不到白天；`timeout-minutes: 180`。

**写 —— 并发提交协议**（不是"等没人的窗口"）：`tools/data_api_push.py` 现有默认"有 in_progress 构建即拒绝推送"对夜场是错的（本会话被挡两次，日志原文："加 --allow-running 可强行推，但大概率几分钟后被回滚"）。协议：

```
for attempt in 1..6:
  head = GET git/ref/heads/main            # 每次重读，不缓存
  若 上次已投 sha 仍在 main 祖先链 → 幂等跳过
  blobs = 上传（仅夜场自己的文件名）
  tree  = create_tree(base_tree=head.tree) # 只覆盖夜场路径，其余继承 ⇒ 不可能回滚白天产物
  commit= create_commit(head, tree, msg)
  PATCH git/ref/heads/main (force=false)   # CAS：失败＝有人推进过 → 重读 head 重试
终检：夜场 sha 仍在祖先链？ 否 → ::warning + 下夜自动重投
```

禁 `git push`、禁 `gh workflow run`（防自触发循环）；白天提交行为完全照旧，并发安全由"路径不相交 + CAS + 祖先链终检"三件事保证。前科依据：auto-commit 的 push 重试含 `reset --soft`（记忆 `starhub-autocommit-source-revert-race`），故终检不可省。

**资源**：Actions cache 独立前缀 `deep-<date>`，不读写白天的向量/历史缓存 key；夜场只读白天产物并把其 sha 记进 `budget.source_sha`。

**调度（多账号池当显式资源）**：现状 `_LLM:1577-1660` 多 key 轮询 + 429 换 key，但全池被限流只退避到 `_LLM_429_POLL_SEC=180`（`:1573`）就"返回空由上层降级"（`:1656`）。夜场改为：每 key 一租约槽（并发 1 起步）、429 按 `Retry-After` 进 cooldown 不派发、全 key 冷却才阻塞；**等待与失败分账**（单条目等待 ≤900s、退避封顶 120s，等待不计失败）；`workers = clamp(请求值, key 数, 6)` 且 ≥1（`clamp_workers`），**档位由首夜压测读数定**（`purpose=test --events-limit 3`，未拿读数不许写死）；优先级 生成 > 判定 > 复看（防"judge 抢光 key 饿死生成"）。

> **判定的适用条件（实施期改判）**：原写"judge 需空余 key ≥2"是按并发场景立的。`workers=1`（阶段 1 默认，也是"单工作流串行"那条已批决策）时没有任何生成任务会被 judge 抢走，那条保留反而把**单 key 部署锁死**：唯一一把 key 一释放就永远凑不到 2 ⇒ 每条等满 `wait_cap` ⇒ 整场零合格、还全程记成"限流"。现规则：保留位只在 `workers>1` 时生效。判据 `test_judge_not_starved_when_only_one_key` + `test_judge_reservation_only_applies_under_concurrency`。

**失败策略**：夜场失败只在当夜窗口内原地重试 1 次（YAML 步骤 `if: failure()`，靠 checkpoint 跳过已完成条目，故重试不重复烧钱），**不做白天自动补跑**；错过当晚 → 次夜 `::warning` 提示人工 `purpose=publish`。半套产物不上线。

## 5. 触发与产物

- `deep-insight.yml` 唯一自动档：`cron: 0 20 * * *`（UTC 20:00＝北京 04:00），避开北京 05:00 全量场与整点刷新。实测近 250 场 schedule 仅 20 场且全错过 21 点 ⇒ cron 准点性不可信，后果靠"本夜应跑标记 + 次夜告警"控住。
- `workflow_dispatch` 必选 `purpose`：`test`（跑完整流程、只上传 artifact、**不提交不部署**）／`publish`（才入库）。本地同入口：`py -3.11 build_deep_insight.py --purpose test --events-limit 3 --out _scratch/deep-test/`，CI 与本地同一条代码路径。
- 事件锚点：白天为锚，夜间可合并/拆分/丢弃，必写审计 `anchor_diff:[{op,id,reason,evidence_before,evidence_after}]`。
- 顶层产物：`{date, generated_at, engine, budget{llm_calls,elapsed_s,input_tokens,key_count,wait_s,c429,source_sha}, anchor_diff, predictions_reconciled{due,hit,miss,auto_checkable_share}, events[]}`。
- 前端：夜场自出独立页 `deep-insight.html`（长论述 + 引用跳原文 + 预测卡含到期与命中状态 + "深度自昨夜 04:xx"新鲜度），白天模板不参与。
- **预测账本必须是入库产物，不是 `_night_state/` 里的临时文件**：到期核对发生在之后某夜的运行里，只在当夜存在的账本等于永远对不上账。所以 `predictions.jsonl` 走"读现网 → 结算到期项 → 整库写回"，与另两个产物同一次 CAS 提交。三条硬规矩：① 只有 404（第一夜）算空账本，其它读取失败一律炸（把 500 当空账本再写回 = 一次抖动毁掉全部历史）；② 非空却解析不出一行 → 拒写（同样理由）；③ 无界追加不许要：未到期全留、已结算只留 90 天（`PRED_KEEP_DAYS`），但算不出到期日的坏行留在账本里而不是按 `made_on` 顺手删。
- `anchor_diff` 不许恒空：阶段 1 不做合并/拆分，但每个锚点事件的 keep/drop 与前后证据数都要留痕（`build_anchor_diff`）。恒空字段与"名字里带深度却什么都不保证"是同一个病。

## 6. 验证（阶段 1）

1. TDD 先红：`tests/deep_insight/` 覆盖 —— 证据门（<3 源必 degraded）、夜间组装含整篇 `full_content`（5706 字 fixture 断言不是 500 字碎片）、输出契约全套（字数/段数/条数/枚举/引用真实/`degraded` 不产预测/`not_run`）、checkpoint 续跑不重复调 LLM、半套不上线、上下文利用率自报、**白天零影响守卫**（三份白天产物逐字节不变）。
2. 变异体：每条判据逐分支红，并**并列未变异基线读数**（防"全红但环境跑不起来"的假阳性，本会话踩过）。
3. 回归：`tests/rss_history/`+`tests/rss_source_coverage/`+`tests/daily_insight/`+`tests/deep_insight/` 全绿 0 跳过；CI Gate A2 仍绿。
4. 现网：`daily-deep-<date>.json` 时间戳为当夜、非 degraded 条目 `narrative` 中位 ≥2500、`degraded` 占比与上下文利用率可读、浏览器实测 `deep-insight.html` 与引用跳转、夜场 sha 次日仍在祖先链。
5. 隔离：dispatch 白天场时 `gh run list` 不出现 `deep-insight.yml`；`purpose=test` 后远端 ref 未动；夜场跑一半触发整点场，双向都不 cancel；**白天场 in_progress 时夜场照样提交成功**（反向亦然）；同一分钟双提交 ⇒ 两个 sha 都在、两份产物同时新、无回退；CAS 用"提交前先推进 ref"模拟并有重试用例。
6. 三夜观察期：命中率、`degraded` 占比、成本读数出齐后才谈扩量。
7. **绿勾守卫（阶段 1 实施期补，因这四条都属于"只在凌晨 4 点暴露"的错）**：`purpose=publish` 且提交状态为 `reverted`/`failed` 时进程退出码非 0（`blocked` 是数据条件，只 `::warning`）；夜场每个跑主脚本的 YAML 步骤都要 `set -o pipefail`（Actions 默认 `bash -e {0}`，`python … | tee` 的退出码来自 tee）；`permissions.contents: write`（read 令牌下 Data API 建 commit 必 403）；判据预检跑在花钱之前且不带 `continue-on-error`。判据见 `tests/deep_insight/test_workflow_isolation.py`。

## 8. 阶段 1 自检改判记录（2026-09-22，按 spec 复核时发现）

复核方式是逐条拿 spec 的句子去对代码，而不是对着代码读 spec。四条原设计在实施期被证据改掉，全部留下判据：

| # | 原设计 | 发现 | 现状 |
|---|---|---|---|
| 1 | §3 "只 import 复用白天 prompt" | 引一条 import 把重依赖与模块级副作用带上夜路，与 §4 隔离冲突 | 夜场自带 prompt + 不许 import 的判据 |
| 2 | §4 "judge 需空余 key ≥2" | `workers=1` 下这条保留把单 key 部署锁死（整场零合格且全记成限流） | 保留位只在 `workers>1` 生效 |
| 3 | §2 "落 `predictions.jsonl` 供到期对账" | 函数写了但**没人调用** —— 空函数，对账链第一夜就断 | 账本入库、每夜读回结算、90 天淘汰 |
| 4 | §5 `anchor_diff` | 硬编码 `[]` —— 恒空字段 | 逐锚点 keep/drop 留痕 |

另外三处 spec 没写、但同属"不修就会假成功"的缺口一并补了：续跑时产物只装本场新做的条目（`can_publish` 按 done+recs 放行、发布写的却是 payload ⇒ 重试夜会上线半套）、缺夜哨兵按 UTC 减 20 小时检的是前天（恒绿哨兵）、`workers` 没有天花板（`--workers -1` 会变成 0 个 worker 而永远拿不到 key）。

变异体自证分两张表：`_scratch/_mut_deep.py`（第 1–2 片契约与调度）与 `_scratch/_mut_deep3.py`（第 3 片运行时 + 工作流，含只撤"重试那一步" pipefail 这类部分覆盖变异）。两张表都必须并列未变异基线读数。

## 7. 未决与阶段 2

- **待你拍板（风险⑤）**：两段式生成让调用翻倍，撞预算时保条目数（A）还是保单条长度（B）。倾向 B —— 这次要治的就是"每条太短"。
- 阶段 2（另批）：白天瘦身 —— `TOP_N→0`、§1 那 7 处截断拆除、`insight_engine` 白天 6h 重分析退役、白天热点条目 300 字下限、信号层"先量后删"（分段计时 → 候选冗余逐条证伪 → 产物逐字段等值对照）、前端合并呈现。理由：这些会改现有时钟链的产物与时长，与"新增独立管线"同批会让回归无法归因。
- 非目标：不改抓取层"每场抓全部 968 源"（`build_rss_aggregator.py:8148-8150`，09-19 决策）；不动 `api/rss.js`；不做主题报告制。
- 已知挂起：`docs/insight-pipeline-flow.md` 里误画的 Trending 输入节点，用户明示"不要动"，故不改（在此留痕，避免被当成遗忘）。
