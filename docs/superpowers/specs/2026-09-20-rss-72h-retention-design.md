# RSS 72 小时留存：出口闸门设计（源自适应窗口 + 每源保底）

日期：2026-09-20
状态：**待批准**（规则与系数已量化；批准后按 TDD 实施，实施后必须过对抗性审查）
目标（用户原话）："rss 应该是保留 72 小时的，你没做截断，超过的应该要丢弃，就跟日志一样……不能这么无限增长下去：
1 过期的用不上也没用 2 总有一天会撑爆。该删的要删，该重新设计的要重新设计，但必须按 TDD 流程、精准修改、
完成后对抗性审查，不影响其他功能，不能回归，不能形成死链/断链/空函数/空转。"

---

## 1. 根因（实测，不是推断）

线上产物 `rss-data-0/1/2.js`（= 用户实际看到的数据，从 raw.githubusercontent 拉取）：
**938 个源 / 20,904 条 / 130 MB，其中 12,136 条（59%）超过 72 小时**；年龄中位数 137h、p75=1,073h（45 天）、
p99=35,585h（4 年）；**1,002 条超过 1 年、12 条 `pub_date` 是 `0001-01-01`**。

代码里**有** 72h 裁剪，但它只管历史：

| 位置 | 现状 |
|---|---|
| `build_rss_aggregator.py:398-497` `_accumulate_history` | 有 `cutoff = now - RSS_HISTORY_HOURS(72)`；`:449-456` 合并时跳过过期；`:474-497` 遍历 `_rss_history` 删过期 |
| `:510-521` | `src_map[key]["items"] = list(_fetched)` —— **当次抓取的条目原样进输出，从未与 cutoff 比较** |
| `:595-637` | 只把**历史**条目回填进 `src_map` |
| `:436-448` | 合并阶段 `pub_date` 缺失/不可解析时**回退成"当前时间"** ⇒ 这类条目永不过期（永生通道） |

⇒ 用户看到的 59% 老条目主要来自上游 feed 自己挂着的老文章（低频博客/播客一期 30 条是常态），
它们走的是"当次抓取"这条路，绕过了唯一的裁剪循环。**所以修法不是调历史裁剪参数，而是补一道输出侧的统一闸门。**

## 2. 规则（用户已选 C：72h 为主 + 窗口按源自适应，慢源放宽到 7 天）

新增两个纯函数 + 一处调用点，不改现有历史裁剪：

1. `_retention_age_h(item, offsets)` → 用 `_effective_pub_dt`（时区校正后）算龄；
   `pub_date` 缺失/不可解析/纪元值（`year <= 1971`）→ 改用 `first_seen`；两者都不可得 → 返回 `None`（**判不了龄就丢，不再按 now 造永生条目**）。
2. `_source_window_h(items)` → `min(168, max(72, coef × 该源中位发布间隔))`；样本 <3 条时不放宽（走 72h 基线）。
   **系数经实测几乎不敏感**（见 §3），取 **2.0**；上限 168h=7 天是硬边界，不允许更长。
3. `_apply_retention(sources, offsets)` —— 在 `_accumulate_history` **返回之前**对每个源的最终 items 统一过闸：
   保 `age <= window_h` → 不足 `floor=3` 条则取该源最新 3 条兜底 → 最多 `cap=120` 条。
   顺序固定为"窗口 → 保底 → 上限"，且**保留既有的同链接去重**（`:633-636` 的逻辑不得被绕过，否则会出现重复卡）。

设计要点：闸门放在 `_accumulate_history` 的返回值上，因此
`_save_api_snapshot`（`:7985`）、`build_html`（`:7987`）、`write_data_chunks`（`:7994`）**三个消费者自动继承同一口径**，
不会出现"页面裁了、API 没裁"的双标；也无需新增任何持久化状态（间隔从本场 items 现算）。

## 3. 量化（模拟器 `_scratch/_retention_sim.py`，跑的是线上真实产物；该脚本是一次性核查工具，不入库）

| 口径 | 留条数 | 降幅 | 变空源 | 触 7 天上限的源 |
|---|---|---|---|---|
| 系数 1.5 / 保底 3 / 上限 120 | 8,209 | −61% | **5** | 234 |
| **系数 2.0 / 保底 3 / 上限 120（拟采）** | **8,212** | **−61%** | **5** | **279** |
| 系数 3.0 / 保底 3 / 上限 120 | 8,220 | −61% | 5 | 318 |
| 系数 2.0 / 保底 3 / 上限 60 | 7,318 | −65% | 5 | 279 |
| 系数 2.0 / 保底 3 / 上限 200 | 8,739 | −58% | 5 | 279 |
| **对照：去掉保底 3** | 6,940 | −67% | **286** ❗ | 279 |
| 对照：全体固定 7 天 + 保底 3 | 9,553 | −54% | 5 | 819 |

读出来的三件事：
- **自适应放宽的增益很小**（系数 1.5→3.0 只差 11 条），因为它只影响 279 个本就慢的源；主要收益全部来自"当次抓取也要过窗"本身。
- **保底 3 是防回归的关键**：没有它会有 **286/938 个源变空** —— 那正是另一会话用 blocking 门禁
  `tests/rss_source_coverage/` 死守的"有数据源"断崖（968→776 的历史故障形态），必须留。
- 剩下 5 个变空源是**全源都判不了龄**的（`pub_date` 与 `first_seen` 都拿不到），属于数据缺陷而非窗口选择，实施时要单独打印源名以便跟进。
- 体积：条目本体 130 MB → **47 MB**（含 JS 容器约 ×1.15）。

> 更正记录：我在 §问答阶段口头估的是"−44%/留 11,690 条"，那是只按 72h 一刀切、未叠加上限与纪元值处理的数；
> 按本模拟器完整跑下来是 **−61%/8,212 条**。以本表为准。

## 4. 影响面与"不能回归"的检查项

| 消费方 | 影响 | 必须验的东西 |
|---|---|---|
| `rss-aggregator.html` 前端 | 后台合并的条目变少；首屏 `CHUNK0_SIZE=360` 不受影响 | 浏览器实测：卡片数、`di-link`/`rss` 链接可跳、无空态、chunk 合并仍生效 |
| `api/rss.js` 快照服务 | 走同一份 `sources_with_items` → 自动同口径 | 线上 `/api/rss` 返回条数与页面一致（不能出现 API 有老条目而页面没有） |
| `analysis_snapshot` / `rss_trend_history` | 关键词与趋势的输入条数下降 ~60% | 趋势快照仍生成、`stale` 语义不变；对比前后关键词 Top 榜，确认没有整块变空 |
| 每日洞察管线 | RSS 素材份额下降（记忆里 `rss_crowded_out`/`retrieval_mix` 就是这个维度） | 一场真实构建后核 `retrieval_mix.rss` 与 `bm25_window`，并确认三维分数变化能归因（噪声带 ±0.05） |
| `tests/rss_history/`、`tests/rss_source_coverage/`（另一会话维护） | 现有断言只覆盖缓存存活/抓取策略，**没有断言"老条目必须保留"** ⇒ 不冲突 | 新用例只**新增文件**，不改他们的文件；两目录必须一起绿 |
| Actions 缓存 | `rss-history` 键仅 0.33 GB，**不是压力来源**；真正的 10 GB 配额已被 `emb-cache` 45 键 / 9.64 GB 吃满 | 见 §6，独立于本设计 |

死链/断链防护：本改动只**减少条目**，不改 `link` 生成、不改 `rss_sources.json`、不删任何文件路径 ⇒ 不产生新死链；
但会**移除旧条目**，因此必须验 `rss_history` 缓存的写读仍自洽（`:114` 那条"半套历史按无历史处理"的守卫不能被新逻辑绕过）。
空函数/空转防护：闸门必须**被调用且在返回值上生效**——测试里除了"该丢的丢了"，还要有一条正向断言
"该留的还留着 + 调用链上确实调了它"（用 AST 锁调用点，同 R14 批2 的做法），避免实现成没人调的死代码。

## 5. TDD 计划（先红后绿；新增 `tests/rss_history/test_retention_window.py`）

必须先红（复现根因）：
1. `test_stale_fetched_item_must_not_ship` —— 当次抓取里 100h 前的条目出现在返回值 ⇒ 现状红。
2. `test_undatable_item_is_dropped_not_kept_alive` —— `pub_date` 与 `first_seen` 都缺 ⇒ 现状按 now 留在窗口内（红）。
3. `test_epoch_pub_date_not_trusted` —— `0001-01-01T00:00:00+00:00` 现状被当"极老"或"最新"两种口径都可能，需钉死为丢弃（红/不稳定）。
4. `test_window_uses_tz_corrected_pub_date` —— `+08:00` 源不得比校正前多活 8 小时。
5. `test_floor_three_keeps_slow_source` 与 `test_no_source_becomes_empty_when_floor_set` —— 反向"必须绿"锚点（防我把保底写没）。
6. `test_cap_per_source` —— 高频源留 120 条封顶。
7. `test_history_and_fetch_same_link_not_duplicated` —— 去重仍生效。
8. `test_gate_is_wired_into_accumulate_return`（AST：`_accumulate_history` 返回前必须调用 `_apply_retention`，且其结果被 return）。
9. `test_all_consumers_share_one_window` —— `rss_api_snapshot*.json` 与 `rss-data-*.js` 的条目集合一致（离线构造，不联网）。

变异体验证（每条都要让对应用例转红，否则测试是装饰）：反判据 `age >= window`、去掉 floor、去掉 cap、
纪元值不视为异常、把 `_effective_pub_dt` 换成裸 `pub_date`、把 `_apply_retention` 调用挪到 return 之后。

验收（不能只看步骤绿）：
① 离线：新用例全绿 + `tests/rss_history/`、`tests/rss_source_coverage/`、`tests/daily_insight/` 无回归（CI 同构 `-s --junitxml`）；
② 线上：一场构建后重跑年龄普查，**>72h 占比从 59% 降到 <1%**（剩下的是保底 3 与 7 天放宽的窗口内条目，需分项说明），
   条目总数落在 8,000±1,000，产物 ≤60 MB；
③ 页面实测卡片与链接；④ 5 个"全源判不了龄"的名字打印出来供后续跟进。

## 6. 与本设计同源的第二个"撑爆"风险（不同文件，需单独授权）

`gh api repos/Kwei168/starhub/actions/cache/usage` → **9.97 GiB / 10 GB 配额已用满，79 个键**。
其中 `emb-cache` 45 键 **9.64 GB**（每键 ~230 MB），`rss-history` 34 键仅 0.33 GB。
键格式是 `…-${{ github.run_id }}-${{ github.run_attempt }}` ⇒ **每场新增一键、从不覆盖**，写满后 `cache/save` 失败
（该步是 `continue-on-error: true`，所以只会静默退化）→ 72h 历史其实已经在退化。
修法是把键改成稳定值（覆盖式）或限制保留代数，**但这要改 `.github/workflows/update.yml`，属另一会话在途文件且是我禁改清单**，
因此单列：需要授权后另做一批，且必须与 `tests/rss_history/test_history_cache.py:121-132`（断言缓存路径与 Save 顺序）一起过。

## 7. 协调与执行前提

- 另一会话正在改 `build_rss_aggregator.py`（本地 `5610485` / 远端 `b866ee7`，之后又提交了 `bbb18a1`）⇒
  实施前必须 `git fetch` + 比对远端 `build_rss_aggregator.py` blob，**在其最新版本上改**，并按 `tools/data_api_push.py`
  的守门窗口原子推送（`update.yml` 若同批则要带 `tests/`）。
- 精准修改：本设计只新增 3 个函数 + 1 处调用 + 1 个测试文件；不改常量名、不动抓取策略、不动 `_save_history_chunked`。
- 实施完成后：fresh-eyes 子代理对抗审查（按用户流程硬要求），审查范围含本文件每条主张是否被代码与线上普查兑现。
