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
   保 `age <= window_h` → 不足 `floor=3` 条则取该源最新 3 条兜底（**兜底同样受 168h 硬上限约束**，
   否则保底就成了第二条永生通道，见 §5.2）→ 最多 `cap=120` 条（每源，不是全站）。
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
① 离线：新用例全绿 + `tests/rss_history/`、`tests/rss_source_coverage/`、`tests/daily_insight/`、`tests/tools/` 无回归（CI 同构 `-s --junitxml`）；
② 线上：构建日志 `[留存] 出厂龄期分项` 行里 **>168h 必须为 0**；>72h 占比从 59% 降到 **约 7%**
   （这 7% 就是 7 天自适应窗口放宽的产物，不是漏裁 —— 见下方 §5.1 对旧验收线的更正），
   条目总数落在 7,000±500；
   体积只按条数比折算（**不是实测**）：线上 `rss-data-*.js` 三个文件实为 136.5 MB，
   按 7,012/20,904 折算约 **46 MB**（与设计 §3 的 47 MB 一致）。
   早期草稿写的"条目本体 ≤1.5 MB"是拿只序列化了 3 个字段的探针算的，作废；
③ 页面实测卡片与链接；④ `[留存] 无内容可出厂的源` 名单进台账并分档（见 §5.2）。

### 5.1 更正：原验收线「>72h 降到 <1%」自相矛盾，作废

C 策略本身就含「慢源放宽到 7 天」，所以窗口内必然存在 72–168h 的内容，<1% 是写错了的口径，
不是实现没做到。终版实现的真实产物实测见 §5.2 末段：出厂 7,012 条、>72h 7.2%、**>168h 0 条**。

### 5.2 与 §3 预测的差异，全部是「保底不限龄」造成的

§3 那张表是**另一套独立模拟器**算的，它的 floor 不限龄：预测留 8,212 条、变空源 5。
不限龄版实现在真实产物上跑出 8,090 条（与模拟器差 1.5%，来自按 key 还是按 name 聚合、
以及模拟器只取非负间隔）—— 数字对上了，但那 8,090 里有 **1,012 条 >168h**
（最老 41,791h ≈ 4.7 年前的 CNN 旧文，散在 426 个源上）：
「保底」成了第二条永生通道，与用户「过期的用不上也没用」直接冲突，故给保底补了龄限
`RETENTION_FLOOR_MAX_H = RETENTION_MAX_WINDOW_H`（拍板人：用户，选项「钳 7 天」，2026-09-20）。

补完龄限、并修掉 prune 侧的 now 兜底之后，最终实现的真实产物复跑结果（以此为准）：
进 20,904 → 出 **7,012** 条；>72h **59.5% → 7.2%**（504 条全在 7 天放宽窗内）；
**>168h 0 条**；p99 35,593h → 137h；出厂 0 条的源 **247 个**。
下表是龄限取值对比（同一份产物、同一实现，只差那个常数）：

| | 出厂条数 | >168h | 出厂 0 条的源 |
|---|---|---|---|
| 保底不限龄 | 8,090 | 1,012 | 5 |
| **保底钳 168h（已采）** | **7,077** | **0** | **246** |
| 保底钳 30 天（折中，未采） | 7,621 | 0（7–30 天仍有 ~550 条） | 104 |

> 表里三行是 prune 修复**之前**测的，绝对值与终版差约 60 条 / 1 个源；
> 取值之间的相对关系（越紧越少、越紧空源越多）不变，终版单一口径见上面末段。

247 个空白源（终版口径；下表测的是 246）按「最新一条多久没更新」分档，**名单已落盘入库**：
`docs/data/rss_retention_empty_sources.json`（逐场构建由 `[留存] 无内容可出厂的源` 播报可复核）：

- **142 个**最新一条在 7–30 天 —— 真慢源（月更博客），不是坏源。是否给前端「最近 7 天无更新」空态待产品拍板；
- **99 个**超 30 天 —— 停更候选，交换源/删源那条线处理。最老的五台：
  老钱说钱 1,542 天、Tiny Projects 1,503 天、CNN International 1,251 天、CNN 1,244 天、小胡子哥 1,059 天；
- **5 个**全部判不了龄（`pub_date` 与 `first_seen` 都不可用，属数据缺陷而非窗口选择）：
  Google Developers、Google Developers Blog、美团技术团队、中国日报双语、BBC英语教学。

覆盖率门禁不受影响：`sources_with_data`(`:8037`) 与 `per_source`(`:8012`) 都取闸门**之前**的抓取阶段数字（已核实）。
余下的产品问题（那 142 个慢源要不要显示空态而非整块消失）**属另一条线，待拍**。

### 5.3 「总有一天会撑爆」的另一半：仓库体积（已量化，非推断）

`gh api repos/Kwei168/starhub` → `size=4,857,478 KB` = **4.63 GiB**（09-20 10:20Z）。
设计初稿记录的远端是 4.43 GiB（09-19），两点差分约 **+0.2 GiB/天** —— 只有两个数据点，
只能当量级看，不能当速率定律。

增量的主体不是代码而是**每小时重写的巨型产物**：`rss-data-1.js` + `rss-data-2.js`
实测量级 68 MB × 2，每次构建都作为新 blob 落进历史。本闸门把出厂条目从 20,904 砍到 7,012（−66%），
按条数比折算这三个文件约 136 MB → **46 MB**，也就是把每小时提交体积砍掉约三分之二；
但**增长不会停**，只是变慢 —— 真正的解法是给巨型产物换落点（孤儿分支 / 分片 / R2），
那条决策仍挂在 `docs/superpowers/specs/2026-09-20-git-repo-size-and-normal-flow-recovery.md` 待拍。

验证方法（不要只看"这次构建绿了"）：推送生效满 24h 后，再取一次 `repos/.size` 做同样两点差分；
若日增量没从 ~0.2 GiB 降到 ~0.07 GiB 量级，说明产物落点才是主因，本闸门只是止痛。



## 6. 与本设计同源的第二个"撑爆"风险 —— 已落地并生产验证（2026-09-20）

当初测得 `gh api repos/Kwei168/starhub/actions/cache/usage` → **9.97 GiB / 10 GB 配额已用满，79 个键**。
其中 `emb-cache` 45 键 **9.64 GB**（每键 ~230 MB），`rss-history` 34 键仅 0.33 GB。
键格式是 `…-${{ github.run_id }}-${{ github.run_attempt }}` ⇒ **每场新增一键、从不覆盖**，写满后 `cache/save` 失败
（该步是 `continue-on-error: true`，所以只会静默退化）→ 72h 历史其实已经在退化。

处置（用户授权改 update.yml 后另做的一批）：`tools/trim_actions_cache.py` +
`update.yml` 里 Save 之前的 `Trim Actions cache keys` 步（`if: always()`、`timeout-minutes: 5`、
顶层补 `actions: write`），按族保留 emb-cache=4 / rss-history=5，且本场 run_id 的键永不入选。
生产实测：06:00 那场构建后缓存 **79 键 / 9.98 GiB → 11 键 / 1.12 GiB**（emb 5、rss 6）。
配套断言在 `tests/rss_history/test_cache_quota.py`（含 Trim 位置/两 Save 的 best-effort/权限/真实路径可解析）
与 `tests/rss_history/test_history_cache.py`（缓存路径与 Save 顺序）。

## 7. 协调与执行前提

- 另一会话正在改 `build_rss_aggregator.py`（本地 `5610485` / 远端 `b866ee7`，之后又提交了 `bbb18a1`）⇒
  实施前必须 `git fetch` + 比对远端 `build_rss_aggregator.py` blob，**在其最新版本上改**，并按 `tools/data_api_push.py`
  的守门窗口原子推送（`update.yml` 若同批则要带 `tests/`）。
- 精准修改：本设计只新增 3 个函数 + 1 处调用 + 1 个测试文件；不改常量名、不动抓取策略、不动 `_save_history_chunked`。
- 实施完成后：fresh-eyes 子代理对抗审查（按用户流程硬要求），审查范围含本文件每条主张是否被代码与线上普查兑现。

## 8. 决策记录与实施后更正（2026-09-20 实施轮）

已拍板并落地：
- 策略 **C**；系数 2.0 / 基线 72h / 硬上限 168h / 每源上限 120 条 / 判不了龄一律丢。
- **保底必须限龄**（用户选项「钳 7 天」）：`RETENTION_FLOOR_MAX_H = RETENTION_MAX_WINDOW_H = 168`。
  起因就是 §5.2 那次真实产物试跑 —— 不限龄的保底往产物里放进了 4.7 年前的旧文。

本文件与最终代码的三处不一致（以代码为准，此处只做更正记录，免得下次照文档读错）：
1. §7 写「新增 3 个函数」，实际是 4 个：`_retention_ref_dt` / `_retention_age_h` / `_source_window_h` / `_apply_retention`；
   另外多了一个 §2 没提的常量族 `RETENTION_*`（含 `RETENTION_EPOCH_YEAR`、`RETENTION_MIN_SAMPLES`）。
2. §2 规则 3 的 `cap=120` 是**每源**上限，不是全站；§6 的缓存那条已经落地并生产验证
   （`update.yml` 的 `Trim Actions cache keys` 步 + `tools/trim_actions_cache.py`，
   实测缓存 **79 键 / 9.98 GiB → 11 键 / 1.12 GiB**，emb 留 5、rss 留 6）。
3. §1 的行号是实施前抄的，另一会话同期改了 `MAX_FEED_BYTES` 与按源 UA，整体下移约 12 行；
   现状以 `build_rss_aggregator.py` 里的符号名检索为准。

## 9. 对抗审查轮记录（2026-09-20，fresh-eyes 子代理两轮）

**本批只覆盖了构建期产物出口，运行时出口没修 —— 别把 §4 那句"三个消费者同口径"读成全站。**
审查 P0-2 实测确认（我逐行复核过 `api/rss.js`）：

| 出口 | 位置 | 现状 |
|---|---|---|
| `?batch=N` | `api/rss.js:610` `fetchAllBatched` → `:627 formattedSources` | **无任何日期过滤**，前端"加载更多/后台合并"走它（`rss-aggregator.html:2258,2269`） |
| `?source=KEY` | `api/rss.js:668-684` `fetchOne` 原样返回 | 无过滤，点开信源抽屉即见老内容 |
| `refresh=1` 合并路径 | `api/rss.js` 的 `filterItems` | 有 72h 闸，但 `if (!item.d) return true` 保留无日期条目 |
| 快照路径 | `loadSnapshot()` | 已过闸 ✅ |

且 `:331/:354` 用 `pub_date: pubDate || new Date().toISOString()` —— Python 侧刚废掉的
"无日期=now 永生"在 JS 侧仍在造。所以**用户点刷新时老内容整批回流**，本改动目标未真正达成；
修法（下一批）：把窗口口径由构建期写进一个策略产物（如 `rss_retention_policy.json`：
per-source window 小时数 + 版本），`api/rss.js` 读它并对三条实时出口统一过闸，避免 JS 再实现一套
规则形成第二口径。

审查其余各条的处置：
- **P0-1 观测面**（246 源出厂 0 条而构建日志取的是闸前数）：已修 ——
  `build_logger` 增 `sources_after_gate` / `sources_empty_after_gate` / `items_after_gate`
  与出厂龄期三段 `items_le_base_h` / `items_base_to_hard_h` / `items_over_hard_h`
  （经模块级 `_LAST_RETENTION_STATS` 传递，与既有 `_LAST_UNRELIABLE_SRCS` 同一模式），
  并有 `test_build_log_carries_post_gate_counts` 锁住六个键；
- **P1-3 二次平移**：`_retention_ref_dt` 不再在 `in_hist` 为真时回落到 `item["pub_date"]`
  （那串可能是降级键），并把"晚于 first_seen ⇒ 已证伪"的检查保留，改为与 `_raw` 的收录时刻比对；
  实测 A1/A2/A3 类反例全部转绿，R6 变异体被打死。
- **P1-4 恒真分项**：分项改为按**出厂 pub_date** 独立计算，`>168h` 桶从此可证伪；
  R16（写死 0）/R17（改回按判定龄取数）均被打死；分项文案放宽为"按行取数"，改单位不再假红。
- **P1-5 纪元保护无人守**：新增 `test_epoch_items_count_as_undatable`（统计口径断言），R4 打死。
  审查提的"补一条纪元污染窗口用例"经复算**做不出可判别性**：纪元日期算出的龄是天文数字，
  窗口只放宽分支用不到它；真正可观测的是统计口径，故按后者钉。
- **P1-6 自放宽棘轮**：系数与基线不变，但 §5 的 <1% 验收线已作废并更正（§5.1）。
  实测放宽影响 382 源、出厂 72-168h 共 504 条 —— 这是策略 C 的设计后果，不是漏裁。
- **P2 工具与实现脱节**：变异工具的锚点在我改代码后有 7 条命中 0 次（等同没测），
  已全部重锚并加 `[BAD-ANCHOR]` 显式失败；`R20`（快照绕开闸门自己读历史）第一次活着，
  因为测试里 `_rss_history` 是空的 —— 补了一条 ghost 链接后才打死。
  等价变异 `R7`（窗口不吃 src key：同源偏移是常量平移，不改变任何间隔）显式标注为
  `[EQUIVALENT]`，不写假测试去凑通过率。
- 修后基线：`tests/rss_history/ tests/rss_source_coverage/ tests/tools/` **106 passed**，
  `tests/daily_insight/`（六键置空，CI 同构）**355 passed**，变异体 20/20 打死 + 1 等价，
  真实产物复跑出厂 7,012 条 / >168h 0 条 / 247 个源出厂 0 条。

仍待决（本轮不动手）：
- 那 142 个「最新一条 7–30 天」的慢源，前端要不要显示「最近 7 天无更新」空态，而不是整块从信源面板消失；
- 99 个超 30 天的停更源走 `tools/rss_source_list_patch` 换源还是删源；
- 5 个全源判不了龄的数据缺陷（名单见 §5.2）。

## 10. 生产验收台账（逐条给判据与命令，别只写"已上线"）

### 已实测（构建侧闸门，远端 a34375ea72 + a7abffa180）
- `build_logs/2026-09-20.jsonl` 18:13 与 19:16 两场：`items_after_gate` 8,351 / 8,431，
  `items_le_base_h` 7,683 / 7,763，`items_base_to_hard_h` 502 / 512，**`items_over_hard_h` 0 / 0**；
  `sources_after_gate` 729 / 730，`sources_empty_after_gate` 236；`items_snapshot` 由 22,247 → 8,341 / 8,417。
- 浏览器实测 `https://kwei168.github.io/starhub/rss-aggregator.html`（12:06Z）：
  墙头部 **8431 篇**，与 `items_after_gate` 一致（两侧同口径，不是"页面裁了 API 没裁"）；
  抽样的 99 个时间节点里没有任何「X 天前 / 个月前 / 年前」；185 个 `<a>` 中 180 个是真实 http 链接、
  `href="#"` 只有 1 个（模板固有，非本次引入）；点开卡片 `.reader2` 抽屉正常，内含原站真实链接。

### 待验（部署后跑，命令写死在这里）
1. 运行时闸门（远端 5be06a877d，11:31Z 推，Vercel 部署在构建末尾）：
   `curl -sI https://starhub-refresh.vercel.app/api/rss?source=hackernews_6`
   期望出现 `X-Rss-Retention: on`。**12:13Z 实测仍是只有 `X-Rss-Single`，即尚未部署**；
   这一条同时回答唯一没法本地确定的一件事：`require('../lib/rss_retention.js')` 在 Vercel 装载下是否可用
   —— 若它加载失败，头会是 `unavailable`（fail-open 且留痕，不会 500）。
2. 页面上那条 toast「已加载全部 16141 篇（新增 15781 篇）」：16,141 > 8,431 的差额就是后台 `?batch=N`
   实时抓取合并进来的**未过闸**内容。部署后该数应回落到 8–9k 量级；不回落到说明运行时出口没生效。
3. 缓存侧每源上限（本地 6531efd，待审后推）：推送部署后看同一日志的
   `history_evicted_per_source > 0`，并看 `history_after` 是否停止单调爬升
   （现状 9,622 → 10,048 → 10,766 → 11,017，5 场 +14%）。

### 已知残留（量化了，未修，等拍板）
无 `pub_date` 的条目在「被 72h prune 删掉 → 下一场又被上游 feed 抓到」时会重新拿到 `first_seen=now`，
于是以「刚收录」的面目长期留在页面上 —— 这是刚堵掉的两条永生通道之外的**第三条**，但只在"条目本身没有日期"时成立。
规模实测：本地历史 68 / 18,037（0.4%），线上产物 180 / 20,904（0.9%）。
候选修法：(a) prune 时**不删**无 pub_date 的条目（保留其真实 first_seen，约 68 条，几 KB），
让闸门按 first_seen 正常淘汰它 —— 代价是这批条目永久驻留历史，且与 §5 的每源上限相互冲突（上限会把它们淘汰掉，漏洞复开）；
(b) 建一个小的"已见过"墓碑集（新状态，历史上这类持久化断过两次）；
(c) 接受 0.9% 残留并在前端把 `dfb`（收录时间）显示得更明确。
我倾向 (a) + 让每源上限把无日期条目排在**最后被淘汰**（现在已经是排最后，但淘汰仍会发生），
即"上限优先淘汰有日期的老条目"。这条改动很小，但需要先定方向。

### 运行时出口：12:34Z 起已在生产生效（实测）
- `curl -sI https://starhub-refresh.vercel.app/api/rss?source=hackernews_6` → **`X-Rss-Retention: on`**。
  这同时回答了唯一没法本地确定的一件事：@vercel/node 把 ESM 语法的 `api/rss.js` 转成 CJS 执行，
  `require('../lib/rss_retention.js')` 可用、`lib/` 被正确打包，没有 500。
- 同一条 6 年前旧文的出口（`?source=tinyprojects_37`）：**部署前 15 条（日期是 `Mon, 18 May 2020`
  这类不可解析值，照常出口）→ 部署后 0 条**。
- `?batch=0`：1,089 条，**>168h 0**，>72h 1 条（104.6h，在该源放宽窗内）；
  `?batch=4`：901 条，**>168h 0**，>72h 22 条，最老 167.9h（贴线，构建时刻在窗内）。
  ⇒ 点刷新不再回流超龄内容，P0-2 闭合。

### 顺带查清的两件事（都不是留存缺陷，别混进这批）
1. 页面 toast「已加载全部 16371 篇（新增 16011 篇）」不是老内容：分块 8,560 + 五批实时 ~10k 条
   **新内容**，而"新增"数几乎等于全部 ⇒ 前端把分块内容也当新数据计了一遍（去重键不匹配）。
   部署前就是 16141/15781 同形态，**不是本改动引入的回归**，但确实是重复计数。
2. 线上产物 8,188 条里有 191 种重复链接（多 205 条，2.5%）：**162 种是跨源转载**
   （BBC 的 Top Stories / World / Business 发同一篇；HN 与 Hacker News AI），
   去重本来就是按源做的，这属信源清单重叠；**29 种是同源重复**，那才是
   `write_data_chunks` 没走 `_dedup_source_items` 的缺陷（快照走了，分块没走 ⇒ 两者条数还会差十几条）。
   修法很小：把去重提到 `_save_api_snapshot`/`write_data_chunks` 之前做一次；另配一条
   "同一源内 link 不许重复"的用例。排在缓存上限那批之后单独做。

### 构建期产物的独立复核（含一次我自己踩到的验证陷阱）
用 git 对象直接统计 `rss-data-1.js`（origin/main = 5ff379f，12:21Z 那场提交的产物）：
条目 8,047｜**>72h 6.5%**｜**>168h 3 条（0.04%）**｜最老 7.00 天。策略兑现，不是靠我自己打的日志行。

- **陷阱（记下来，别再犯）**：我先用 `raw.githubusercontent.com/.../rss-data-1.js` 抓，得到的是
  **上一场的旧副本**（10,063 条、62.3% >72h、最老 6.6 年），一度看起来像"闸门漏了分块出口"。
  大文件的 CDN 会滞后于 commit。**验收线上产物必须用 `git show origin/main:<文件>`（或带 commit SHA 的 URL）**，
  不要信分支名的 raw 链接。
- 那 3 条不是越限：168.11h / 168.07h，是**贴着 168h 线**——构建在 12:17Z，我在 12:32Z 测量，
  中间 15 分钟把 167.98h 推过了整点。构建时刻它们都在窗内（日志 `items_over_hard_h: 0` 与此一致）。
- 顺手发现一个真缺陷（与留存无关但同一批数据里可见）：那 3 条里有**两条是同一个 link**
  （思考于印 mp.weixin 文章，pub_date 相同）—— `_dedup_source_items` 只在 `_save_api_snapshot` 里调，
  `write_data_chunks` 这条路没去重 ⇒ 快照与分块会出现"同一条出现两次 / 条数不一致"的双标。
  修法是把去重提到 `write_data_chunks` 之前做一次（或让两者共用同一份去重后的列表），
  配一条"分块内 link 不许重复"的用例。这条排在每源上限那批之后单独做，别混进留存批次放大风险。



## 11. 缓存侧每源上限：两路独立对抗审查的结论与复修（2026-09-20 第三批）

`6531efd` 那一版**没通过审查**，两路 fresh-eyes 各自独立报了同一批缺陷（互为佐证，不是复述）。
逐条自验后全部成立，本批复修如下。

| # | 审查结论（我都复现过） | 复修 | 证据 |
|---|---|---|---|
| P0-1 | 唯一的"反向锚点"是空跑：造数最老 300h，72h 裁剪先把尾部删光，上限一场没动手（实测 `evicted=0`）；变异体"上限永不生效"照样绿 | 造数全部压进 72h 窗内 + 自证 `evicted > 0` + 比对**完整 payload**（link/pub_date/bad_date/date_fallback/time_str）而非只比 link | `test_bound_does_not_change_shipped_payload`；变异体 B1 被 6 条打死 |
| P0-2 | 上限跑在 `bad_date` 统计与 src_map 回填**之前** ⇒ 改了审计样本：真实快照重放实测 120 条出厂条目凭空多出 `bad_date`、21 条出厂 `pub_date` 被回拉、"不可信源"集合多出 `nodeseek_54` | 调用点移到回填与审计**之后**（`result = list(src_map.values())` 之前）⇒ 本步作用域只剩"下一场读到多少历史" | 位置 AST 锁 + 行为锁 `test_eviction_cannot_change_date_audit`（异常率 40%↔0% 翻转的判别造数）；变异体 B11 红 |
| P0-3 | "对出厂不可见"不是结构保证：上限按 `first_seen`（到达序）裁、闸门按 `pub_date`（发布序）发，两套序反向时 120 个槽位有 50 个被换掉 | 排序键改用 `_retention_ref_dt`（与判龄同一只表），并加 `(有龄期, 龄期, link)` 三元组 | `test_eviction_follows_publish_age_not_arrival_order`；变异体 B3（退回 first_seen）红 |
| P1-1 | 平票真实存在：10 个超限源每一个的第 400/401 名 `first_seen` 逐字节相同（并列 12–30 条），去留由 dict 插入序决定 ⇒ 同一批链接逐场抖动 | 排序键末位加 `link` | `test_eviction_tie_is_deterministic`；变异体 B4 红 |
| P1-2 | 淘汰数用 `0` 兜底，与 `fc41136` 刚立的规矩自相矛盾；且生产单场单源最多抓 30 条 ⇒ 上线头几场真是 0，"没跑到"与"没东西可淘汰"不可区分 | 日志改 `.get("evicted")`（无默认）；播报改为无条件一行（含超限源数与历史余量） | `test_eviction_count_reaches_build_log`（key 一致性 + 禁 0 兜底）、`test_report_prints_even_when_nothing_evicted`；变异体 B5/B8/B9 红 |
| P1-3 | 淘汰被计进"裁剪 N 篇过期"与 `history_expired` ⇒ 体积约束冒充过期清理，§待验 读的正是这个数 | `pruned_expired` 在裁剪循环处当场结清；`history_expired` 减去本场淘汰数 | `test_expired_log_excludes_cap_evictions`；变异体 B14 红 |
| P1-4 | 接线只有 AST 锁：`if False:` 包住调用、不写回 `_LAST_HISTORY_BOUND`、日志读错 key 三种变异体 CI 全绿 | 补行为级集成用例（真跑 `_accumulate_history`，断言历史被压到上限 + 状态写回 + 播报） | `test_bound_wired_and_state_written_in_accumulate`；变异体 B6/B7 红 |

### 复修后的实测（不是"看着对"）
- 变异自检 `_mut_bounds.py`：**15 个变异体全部被红，survived=0**，每轮跑完 `sha256` 断言字节级还原。
  每个变异体都对应上面一条审查结论（B1..B15），基线 `tests/rss_history` 91 passed。
- CI 同构集本地全绿：`tests/rss_history + tests/rss_source_coverage` **110 passed / 0 failed**。
- **真实历史重放**（`_scratch/_replay_bounds.py`，18,037 条 / 613 源，时间轴整体前移 74h 使其次窗内、
  并冻结时钟消除两遍之间的秒级漂移）：
  10 个超限源淘汰 **1,984** 条、历史 15,680 → 13,696；出厂 613 源 / **9,497** 条逐字段比对
  **差异 0 源**；"不可信源"集合 22 ↔ 22 全等；`evicted=1,984 > 0` 自证不是空跑。
  - 同一条重放第一次跑得出 `shipped_total=2`：快照比真实墙上时钟老 3 天，prune 把所有内容删光，
    "0 差异"恒成立 —— 这正是 P0-1 那类空跑，判据里必须钉 `evicted > 0`。

### 仍未闭合的一条（量化了，单独一批做）
淘汰/裁剪掉的条目若下一场被上游 feed 重新列出，合并循环会给它写**新的 `first_seen`**，
等于把刚删的条目重新计时（第三条永生通道，`git diff 6531efd~1 6531efd --numstat` 证明
本批零删除 ⇒ 该通道是既有的，本批不引入）。本批的复修把它压到最小：
排序键与判龄同源后，被优先淘汰的是**发布最老**的条目，而 `pub_date` 为空的条目
按自己的 `first_seen` 排位（`test_first_seen_only_entries_rank_by_their_own_clock`），
不再一律沉底。真实暴露量：超限源里靠 `first_seen` 存活的 12 条（全库 660 条无 pub_date，
其中 253 条 pub_date 为 JSON null）；生产单场单源最多抓 30 条 ⇒ 每场被重置的量有限。
彻底闭合要留 `link → first_seen` 墓碑（§5 选项 b），会改到出厂内容（那些条目真的消失），
故单列一批，等拍板后按同一套流程做。

### 配额 400 的代价已量化：高频源的缓存深度会短于 72h（`_scratch/_measure_cut_depth.py`）
本机真实历史（平移到"最新条目 = 1h 前"后按新排序键取第 400 名）：

| 源 | 历史条数 | 第 400 名龄期 | 被淘汰且仍在 72h 窗内 |
|---|---|---|---|
| agihunt_0 | 1,366 | **32.0h** | 787 |
| aihot_pool_22 | 844 | 41.2h | 365 |
| nodeseek_54 | 881 | 45.1h | 361 |
| it之家_13 | 676 | 52.5h | 175 |
| v2ex_all_50 | 658 | 53.5h | 153 |
| hn_newest_56 | 617 | 57.5h | 136 |
| 其余 4 源 | 405–473 | 71.8–78.5h | 0–1 |
| **合计** | | | **1,978 / 2,764 = 71.6%** |

含义要说白：**上限切掉的条目里 71.6% 还在 72h 窗内**，也就是说对最重的那几个源，
缓存实际只保住了"最近 32 小时"而不是 72 小时。这不违反出厂契约（每源只发最新 120 条，
上面重放证明逐字段零差异），但它是"抓取失败场能回填多深"的代价 —— 72h 窗与体积上限
对超高频源本质冲突（该源 24h 就 455 条 > 400），只能选一个。
**触发条件写在这里**：生产实测单场单源最多抓 30 条且当前无源超 400 ⇒ 上线初期这一刀不落地
（日志会打印"0 个源超限，淘汰 0 条"）。等 `history_evicted_per_source > 0` 真出现，
再按当时的实际深度决定是否把配额抬到 1,500（体积 ×3.75）或改成"按字节预算"。别提前优化。

### 顺带查出：三个源覆盖率测试文件从未落地远端，CI 因此少收 8 条用例
在 CI 同构树（`git archive origin/main` + 本次三个文件）上跑门禁 A2 得 **102 passed**，
本地同一集是 **110 passed** —— 差的 8 条在 `tests/rss_source_coverage/` 的
`test_fetch_size.py` / `test_per_source_ua.py` / `test_source_list_health.py`，
它们随 `f03a1d2`/`42809b8`/`bcc385c` 提交在本地，但从没进远端（Data API 按路径推，漏了这三个）。
把这三个文件搬到远端树里实测：前两个全绿，`test_source_list_health.py::test_no_duplicate_keys_or_urls` **红**，
原因是远端 `rss_sources.json` 里有两条重复 URL：`blog.devtang.com/atom.xml`、
`rsshub.bestblogs.dev/xiaoyuzhou/podcast/6627fda4b56459544087d86a`。
⇒ 单独推测试会把 blocking 门禁 A2 弄红、连带不提交不部署（这坑今天已经踩过一次）。
修法必须先走 `tools/rss_source_list_patch.py`（7f66e29 立的新规矩：源清单改动只推可重放补丁，
不推最终文件）把两条重复消掉，再随同一次提交推这三个测试文件。**不在本批做**，
避免把留存批次和源清单批次混在一起放大风险。
