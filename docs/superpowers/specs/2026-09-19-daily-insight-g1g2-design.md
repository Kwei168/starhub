# 深度洞察地基改造：missed 驱动的二次召回闭环（G1）+ 证据升级（G2）

> **落地状态（2026-09-19 16:40 北京时间复核）**：G1 与 G2 均已上线并生产生效——
> G1 回收环在 07:14Z 期回收 2 条、08:14Z 期回收 1 条，新事件均带可跳转链接；
> G2 的近似转述去重在 `build_daily_insight.py:1983`（`_jaccard > 0.7`）、full_content 直填正文在 `_build_event_material`。
> 本文的「明确不做」清单与触发条件**仍是现行依据**，勿当已废弃；
> 后续观察期与候选方案见 `docs/superpowers/plans/2026-09-19-daily-insight-shipped-baseline.md`。
> ⚠ 本文写下的所有 cov/rel/faith 数字都是**草稿口径**（RAGAS 在 missed 回收前打分）。
> 自远端 `6f1736ac`（第12轮）起 `quality` 改为描述 shipped 终版报告，跨期比较必须分段读。


> **前置状态（09-19 01:59Z）**：第7轮 `eedd7cbc`（文不对题 P0 + 扩池修正 + 中位评分）已推送，尚无构建携带——02:00 整点 dispatch 即将开始，需先确认该轮生产验证通过（事件标题/正文一致、事件数回升、med= 日志出现），再叠加本计划 G1，避免归因纠缠。

## Context

外部分析指出每日洞察的结构性缺陷：**要求的索取量（300-500字时间线+影响+引用）超过给到的证据量**。我已逐条对照代码核实，四条主张全部成立：

| 主张 | 核实结果 | 证据 |
|---|---|---|
| 深度解读只喂 800 字 feed 片段+纯标题 | ✓ | `_build_event_material`:1895 RSS `[:800]`；:1903 热榜只有标题行；DEEP_ANALYSIS_TOP_N=3 (:148) |
| 检索自指：查询全是榜单标题 | ✓（基本） | `_build_queries`:1047 四路 Top15 标题 + 伪查询取自已检索 chunk 标题；未被标题提及的主题无召回入口 |
| judge 输出 missed 清单被丢弃 | ✓ **字面成立** | prompt 要求 `coverage.missed`(:3020)/`missed_points`(:3054)/`unmatched`，但 grep 全文 "missed" 只命中 prompt 两行——解析处从不读取 |
| 修正环无法新增事件 | ✓ | `_self_correct_events` 只遍历 weak_indices 重写既有 cluster |

**对分析的一处优先级修正**：①「喂正文」受限于 rss_history 全文覆盖率（实测部分源 0–2%，URL 精确匹配才命中），对未命中素材无增益；而 ④+②（missed→定向召回→新增事件）从 19k chunk 语料补证据，是无前提的主杠杆。且 ① 依赖的 build_rss_aggregator 全文抓取正被另一会话在途修改，不宜并行碰。**④ 与 ② 本质是同一闭环的两半**（judge 告诉你缺什么 → 以它 query 定向召回 → 补成新事件），合并做收益最大。

## 实施（TDD→对抗审查→推送，CLAUDE.md 规范照旧）

### G1 missed 驱动的二次召回 + 事件新增（cov 主杠杆）
1. **解析回收**：`_evaluate_report_quality` 解析处新增提取 `reasoning.coverage.missed`（v1）/`missed_points`（v2），并入返回 dict 的 `missed_points` 字段（两变体取并集去重，经 `_median_eval_samples` 透传）。
2. **定向召回**：RAGAS 修正环内，当 cov<0.75 且有 missed 时：missed 短语 → `_hybrid_retrieve(index, chunks, missed_queries, top_k=30)` → 相似度闸（chunk 检索分≥当期池内中位数，防 judge 幻觉造事件）→ 聚 1-2 个新事件（复用 `_assemble_events` 的组件事件逻辑简化版）。
3. **摘要生成**：新事件走 `_llm_phase1`（单批复用，含 event_num 配对与 key_links 校验）→ append 到 clusters。
4. **闸序不变量**：新增事件在终局 dedup/占位/faith recheck/cap 之前进入（现有 :4666-4690 闸序天然覆盖），链接红线由 `_validate_key_links` 保证。
5. 预算：`len(clusters) < MAX_EVENTS` 才补；每次构建最多 +2 事件；+1~2 次 LLM 调用（构建时长 +2~3min，小时窗口充裕）。
- 测试：missed 解析回收（v1/v2 两格式）；相似度闸挡幻觉短语；新事件带 key_links 且过占位闸；MAX 预算不越界；embed/检索失败静默降级。

### G2 证据包升级为事件上下文（faith 副杠杆，Phase2 3 事件专用）
- `_build_evidence_pack` 与 `_build_event_material` 合并去重：URL 反查命中 full_content 的 item，素材直接用正文（段落边界截断 2500 字），证据块不再重复注入同 URL；未命中行为不变。
- 注入前对素材做近似转述去重（`_dedup_tokens` jaccard>0.7 只留 heat 最高一条）——即分析里的 MMR 简化版，token 花在新增事实而非重复。
- 测试：命中 URL 时 material 含正文且证据无重复段；近似转述 3 条留 1；未命中回退旧行为。

### 明确不做（本轮）
- ③ 多路查询扩面：G1 上线后若 cov 仍 <0.75 再上（否则一次改太多无法归因）。
- claim/实体中间层：架构级改动，单独立项。
- rerank：同意分析结论——候选池没扩大前重排无意义。
- build_rss_aggregator 全文抓取扩面：他人在途，避开。

## 关键文件
- build_daily_insight.py（:1047 queries、:912 hybrid_retrieve、:1863 evidence、:1884 material、:3020/:3054 judge prompts、:3069+ 解析、:3211+ ragas 环、:4666-4690 终局闸序）
- tests/daily_insight/（新增 test_missed_recall.py；扩展 test_evidence_pack.py、test_ragas_robust.py）

## 验证
1. 本地 `py -3.11 -m pytest tests/daily_insight/ -q -s` 全绿 + 根测试 4 件（同 CI 门禁 B）
2. fresh-eyes subagent 对抗审查（重点：新事件闸序完整性、judge 幻觉防御、构建时长回归）
3. pathspec-only 提交（他人在途文件不入库）→ Data API 推送（LF 归一）→ 整点构建
4. 生产核验：日志出现「missed 补事件 N 条」；事件数回升；tracking cov≥0.75；faith≥0.88；di-link 红线保持；关单仍按连续两期中位达标
5. 前提：第7轮（eedd7cbc，文不对题 P0 修复）构建验证通过后才叠加 G1，避免归因纠缠