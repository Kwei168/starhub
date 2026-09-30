# 任务移交手册｜存储膨胀与轮转（2026-09-30 单日）

> **范围**：只针对"清除 `.git` 8.7G 存量 + 实现以后能轮转"这一件事。全局规范看 `HANDOFF.md` 与 `CLAUDE.md`，本文件不重复。
> **移交触发点**：北京时间 2026-09-30 23:59（= UTC 15:59）。过点即换人，写这份文件的人届时已无上下文。
> **写于**：2026-09-30 12:05 UTC（北京 20:05）。

---

## 0. 用户原话（需求锁定，别漂）

1. 「你要解决这个存储无限膨胀的问题 要实现轮转，之前我们就花大力气处理过」——只补以前做漏的一环，**既有逻辑与功能不变**。
2. 「我就是要解决这个问题」（指 8.7G 存量）。
3. 「我的需求除了清除 8.7g 还要以后能实现轮转」。
4. 「你这么蠢 如果把 git 历史清了 你更不知道咋回事了」——**否决"砍历史换速度"**。这条把方案 B 判死，见 §5。
5. 「你不要把问题扩大化…在功能上东砍西砍」；「不是让你去掉全文」——**不许用削功能换指标**。

## 1. 判定标准（可复跑，别用"步骤绿"）

| 要回答的问题 | 唯一有效判据 | 命令 |
|---|---|---|
| 增量清干净了吗 | **一场构建写进 git 的字节数 = 0**（人工提交除外） | 见下 `per-build-bytes` |
| 存量减了吗 | 本地 `du -sh .git` + 远端 `repos/.size` | 现在 8.7G / 5.21 GiB |
| 轮转还在不在 | 老文件是否停止被永久攒副本 | 见 §4 表 |

`per-build-bytes`（**注意两个坑：commit API 的 `files[]` 没有 `size`；`git ls-tree` 加 `--name-only` 会吞掉体积**）：

```bash
gh api repos/Kwei168/starhub/commits?per_page=8   # 找 chore: auto update stars 的 sha
gh api repos/Kwei168/starhub/commits/<sha>       # 取 changed files
gh api "repos/Kwei168/starhub/contents/<path>?ref=<sha>" --jq .size   # 逐个取真实体积后相加
```

## 2. 已完成并已上线（全部有读数，勿重做）

| # | 做了什么 | 证据 |
|---|---|---|
| 1 | 派生字段 `time_str` 移出条目，时间标签由页面现算（唯一事实源 `lib/rel_time.js`） | 相邻两场共同条目逐字节相同率 **44.5% → 96.4%**；产物出厂 `time_str` 0 次。提交 `c13c8b1a43`/`89e28acd24` |
| 2 | **Pages 改由 workflow 发布 artifact**，`rss-data-1.js`（55MB/场）退出 git | 每场入仓 **75.5MB → 23.5MB（−69%）**；main 上该块停在 `2051f899f3dc`，线上是 `60a18d6da7a3`，**两边分叉**。远端 `update.yml` blob `78348d03ae` |
| 3 | 分块与"是否被 git 跟踪"**解耦**（staging 按模式补入 `rss-data-*.js`） | 这是"剔历史不会让页面缺块"的前置，已验证。提交 `528206c` |
| 4 | 防复发判据 10 条 + **19 个变异各由指定断言打死、errors=0**；A2 同构 214 tests/0 fail | `tests/rss_history/test_pages_deploy_wiring.py`；harness `.deploy-tmp/_mut_pages.py` |
| 5 | Pages 源切成 workflow | `gh api repos/Kwei168/starhub/pages` → `build_type=workflow`。**用 `PUT`，`PATCH /pages` 路由不存在会回 404** |
| 6 | 全局手册补 §8.15、spec 补 §13 | `HANDOFF.md:887+`、`docs/superpowers/specs/2026-09-20-git-repo-size-and-normal-flow-recovery.md` |
| 7 | 本地垃圾清理：5.4G 克隆、`.deploy-tmp` 内两个 09-17 旧推送克隆、3 个孤儿 `__pycache__` | E 盘可用 236G → 242G |

## 3. 当前正在发生的状态（换人后第一件事就是查这个）

**⚠ 2026-09-30 21:1x 更新：本地克隆路线已放弃，改在 GitHub Actions 内做重写（方案 C）。**

- 依据：CI `Checkout`（`fetch-depth: 0`，`update.yml:44`）拉完整 5.23 GiB 历史只用 **259 秒 ≈ 20 MB/s**；本机线路实测 **0.21~0.34 MB/s** 且 `git clone` 不可续传（重试循环把 688MB 进度丢回 31MB 重来）。站内快约 100 倍。
- 已推：`.github/workflows/repo-trim.yml`（远端 blob `dac549a279`，main → `467015c689`）。三道闸：① `dry_run` 默认 true；② `confirm` 必须等于 `TRIM`；③ compare-and-swap（检出后 main 若前进则中止，不强推）。另含"除被剔族外任何路径消失即判失败"的自测。
- **已改为自动跑**（用户 21:0x 原话："自动跑"）：`.deploy-tmp/_auto_trim.py` 后台守候 `bb0agtn6v`，日志 `E:/_trim_auto.log`。链路 = 等 dry-run 结束 → 三门校验（conclusion=success、日志无 `::error::`、"重写后 .git" < "重写前 .git"）→ 任一不过就**什么都不推**并把原因写日志 → 全过则自动 `dispatches inputs[dry_run]=false inputs[confirm]=TRIM` 起第二趟 → 等它结束回读体积/提交数/"已强推"。
- **断链已核（21:1x 实测，不是推断）**：远端 tip `467015c689` 的根树里被剔族只剩 `rss-data-1.js` **55,710,750 B**（就是那具僵尸：11,486 条旧数据、5,060 条 >168h）与 `rss-data-2.js` 128 B 空壳；`rss_history*` / `rss_api_snapshot*` / `rss_cache.json` **都不在 tip 树里**（早已出仓），所以重写不会让任何构建期 `open()` 读到"原本在、现在没了"的文件。强推顺带把僵尸块从 tip 摘掉，是额外收益。
- `update.yml:322` 的 `test -s _pages/rss-data-1.js` **不会因重写而恒红**：staging 的清单来自 `git ls-files` + 磁盘 `for f in rss-data-*.js` 兜块，块 1 是当场比赛写在磁盘上的，不进 git 照样存在。
- **换人后要做的第一件事**：读 `E:/_trim_auto.log` 尾部。若第二趟已"强推"，剩下的全是人工：本地换新克隆、旧 `.git` **mv 进隔离区**（不 rm）、用 `gh api repos/Kwei168/starhub --jq .size` 连测几天（GitHub GC 滞后，别把"推完了"讲成"降下来了"）。若日志显示三门之一没过或 CAS 中止，照日志原因重跑 dry-run=false 即可。
- 本机当前**没有任何克隆在跑**；`E:/starhub-base`、`E:/starhub-shrink`、`E:/starhub-b2` 均已清除。
- **已预置的一个风险（未证实，等 dry-run 读数定性）**：`repo-trim.yml` 的安装步骤是裸 `pip install --quiet git-filter-repo`，
  而 `update.yml` 之所以能用 `pip`，是它在 `:48` 先跑了 `actions/setup-python@v6`（把 PATH 指向 tool-cache 的 python）。
  我的 workflow **没有** setup-python ⇒ 走的是 runner 系统 python；ubuntu-24.04 带 `/usr/lib/python3.12/EXTERNALLY-MANAGED`，
  裸 `pip install` 有可能直接报 `externally-managed-environment`。**若 dry-run 卡在这一步**，把该 step 换成下面这行再重跑（幂等、三条兜底、不装系统依赖）：
  ```yaml
  - name: 安装 git-filter-repo
    run: |
      command -v git-filter-repo >/dev/null 2>&1 \
        || python3 -m pip install --user --quiet --break-system-packages git-filter-repo \
        || pip install --user --quiet git-filter-repo
      export PATH="$HOME/.local/bin:$PATH"
      git filter-repo --version || python3 "$HOME/.local/bin/git-filter-repo" --version
  ```
  注意这只是**候选**，不是结论：今天 13:0x 尚未取到该步骤的实际读数，别在别人没复跑前当既成事实。
- `git-filter-repo 2.47.0` 本机也装了（备用），但真重写不需要它——在 runner 里 `pip install`。

（下略的原计划保留供参考：本地全量克隆 + 本地 filter-repo 因线路太慢作废。）

- `git-filter-repo 2.47.0` **已装**（`py -3.11 -m pip install`，`git filter-repo --version` rc=0）。这是用户批准的例外，不算静默装依赖。
- 远端 `main = 8742dae5d5`（11:23:19Z，CI 自动提交）；本地 `HEAD = 528206c`；本地 `main` 与远端是两条线（Data API 不回写），比对一律按 blob。
- 站点健康：`#1517`（北京 18:00）全绿、Pages 由 artifact 发布；`#1518` 起带解耦改动。

## 4. 还剩什么（这就是"轮转"没做完的部分）

**当前每场仍在进 git 的 16 个文件 = 23.5 MB/场 ≈ 0.4~0.6 GB/天**（11:23 那场实测）：

```
hot_history.json 8.1MB  analysis_snapshot.json 3.6MB  translations.json 3.2MB
rss-aggregator.html 3.1MB  build_logs/*.jsonl 2.2MB  rss_trend_history.json 1.1MB
insight_tracking_history.jsonl 0.77MB  rss-data-0.js 0.42MB
daily_insight_tracking_history.jsonl 0.37MB  daily-insight-history.html 0.31MB
index.html 0.28MB  daily_insight_history.json 0.24MB  ai-daily.html 0.08MB
hot_snapshot.json 0.06MB  daily-insight.json 0.03MB  trending_snapshot.json 0.01MB
```

**三档归属（已核，但见下面的警告）**：

- **确认被生产代码读回 → 必须留 git**：`trending_snapshot.json`←`fetch_and_build.py:432`、`rss_sources.json`←`build_daily_insight.py:310`、`known_categories.json`←`:716`、`descriptions_zh.json`←`:722`。
- **只被测试/根目录 scratch 读**：`ai-daily.html`←`test_daily_insight.py:203`（有 exists 守卫）、`daily-insight*.json`/`daily-insight-history.html`←同脚本 assert（同进程先生成再断言）、`rss-aggregator.html`←`_adversarial_*`/`_verify_*` 旧脚本。
- **探测显示"无读取"，但结论不可信**：`translations.json`（手册 §7.13 明说是构建与 API 共用的翻译缓存，几乎肯定读回）、`hot_history.json`、`analysis_snapshot.json`、`rss_trend_history.json`、两个 `*_tracking_history.jsonl`、`index.html`、`rss-data-0.js`。

> ⚠ **下一步动手前必做**：把路径常量（`TRANS_FILE`、`HOT_HISTORY`、`INSIGHT_FILE` 之类）解析出来，确认每个文件真正的读点。我的探测要求"文件名与 `open(` 同行"，**走常量的读取会漏**——拿这个漏判去退跟踪，就是"把跨场输入砍掉"的功能事故（手册 §7.15 有先例：`meta.last_fetch` 寄生在大产物里，快照一出仓增量静默退化成全量，两天没人发现）。

**待办批次（按此顺序，一批一刀，每批带判据+变异体）**：

1. **批次①** 纯产物走制品：4 个 HTML（`rss-aggregator.html`/`index.html`/`ai-daily.html`/`daily-insight-history.html`）→ 扩展 staging 的模式补入，再退出 add 清单。约 −3.8MB/场。做法与 §2 第 2、3 行完全同型，判据模板现成。
2. **批次②** 状态迁 `actions/cache`：`hot_history`/`analysis_snapshot`/`translations`/`rss_trend_history`/两个 tracking jsonl。约 −19.7MB/场。**这一批才是"版本轮转"的闭环**——状态需要的是最新值，不是历史。参照 §8.13 对 `rss_history` 的处理，且**必须保留"读不到就老实重算"的降级路径**。
3. **批次③（存量）** `filter-repo` 剔死数据 → force-push → 本地换小仓 + 旧 `.git` **mv 进隔离区（不许 rm）**。GitHub 侧空间回收滞后（等它的 GC，可能几天），别把"推完了"说成"降下来了"。

   **⚠ 21:2x 实测：GitHub `.size` 大概率不会降，且原因不是 GC 滞后。** 远端引用普查（`git/refs`）：`heads` 2 个 + `pull` 2 个，其中
   `refs/pull/2/head = e806aadb7b6f`（＝ `daily-insight-fix-v2` 的 tip，PR 已 closed 未 merged），`refs/pull/1/head = a2ea918ea6a2`
   （PR#1 的头，那条分支我早先已 prune，**这个引用是它在这世上唯一的锚**）。force-push 只重写 `refs/heads/main`，
   而 `refs/pull/*` 是 GitHub 内部引用、用户侧无删除 API ⇒ 老历史仍被可达 ⇒ `.size` 继续算着那 45GB 死块。
   **所以本批的诚实读数应当是**：① 新克隆/CI `Checkout` 立刻变小变快（clone 只协商 heads+tags，不取 `refs/pull/*`）——这条能量化；
   ② GitHub 网页上的 `.size` 不动，要真回收得开工单或重建仓库（用户决定）。**不要把 ①说成 ②。**
   可顺手做的（需用户点头）：删 `daily-insight-fix-v2`（compare 实测 `behind_by=0 ahead_by=580` ⇒ **零独有提交**，删它不丢任何代码）。

> **顺序不可反**：先砍历史再清增量 = 每天 +0.5GB 长回来，手册 §12.3 原话"不定落点，新仓也会在几周内长回 4G"。

## 5. 已定死的决策（不要重开）

- **不砍 git 历史换速度**（用户 §0 第 4 条）。今天两次差点走这条路，都被"历史是唯一非我书写的证据"否掉：今天每次自我纠错都是靠 `git log` 做到的（例如我差点把上一会话的 `code-only-fix` 当成今天的动作汇报，是逐条比对远端提交才发现）。
- **时间分槽轮转已判死**（spec §7：`time_str` 移出后相同率 96.4%，槽宽 6/12/24h 下"整块不变"仍 0/12、0/6、0/3；0.964^767≈1e-12）。别再试块粒度。
- **不上 git-lfs**（免费额度对每场量级不够）；**不手删 `.git/objects/pack/*`**；**不在旧仓跑 `git gc --prune=now`**。
- **"原地 gc/repack 能救 8.7G"是错的**：本仓是 shallow clone 且被前人手删 `.pack` 抹掉约 11k 对象（spec §0/§4），gc 治不了浅、补不回对象。
- `rss-data-2.js` 已是 128B 空壳、每场 blob 恒定，增量早停；它的 7.94GB 是纯死历史。

## 6. 今天踩过的坑（换人后最容易再踩的）

| 坑 | 教训 |
|---|---|
| 把 `rss-data-2.js` 说成"远端不存在" | `git ls-tree` 输出漏读一行就下判断 → **宣布前必须把输出读完** |
| 自创 jq 表达式三次静默返回空（`git status --porcelain --cached` 无此选项、`start_time` 应为 `started_at`、`// "-)"` 语法错） | 手册 §8.12 明写"**照抄两条判据，别再自创表达式**"；检查命令非零/空 = **停止条件** |
| `git commit` 漏 `-m` 前缀 → 参数被当 pathspec → 提交没成而 Data API 照推 | 提交后必须看 `commit_rc` 与 `git log -1`，不能假设 |
| `git commit -m "…"` 里放了 ASCII 双引号 → 消息被截断、尾巴变 pathspec | 长消息一律走 `-F 文件` |
| commit API 的 `files[]` 无 `size`；`ls-tree -l --name-only` 吞体积 | 取体积只能 `contents/<path>?ref=<sha>` |
| staging 整拷工作目录 | 会把 `.gitignore` 排除、由 cache 放回磁盘的 **398M 语料**第一次公开发布。**换通道要先比两条通道的输入集合差** |
| `upload-pages-artifact` 默认 `if-no-files-found=warn` | 空制品会被"绿发布"=抹平站点；须 `error` + `test -s` |
| staging 排在 Vercel 之前 | 它一失败会连坐 Vercel → `continue-on-error` + `id: stage` + upload 依赖其 outcome |
| 先切 Pages 源再确认无在跑构建 | 切源后旧流程仍提交进 main 但无人发布，站点内容静止。已回退过一次 |
| 删掉当轮创建的克隆底本 | 它是下一步的交付物。**大文件底本没用完不许删**（已重复下载一次，5.4GB 白跑） |
| Auto 模式拦截 PUT/推送 | 只有换权限模式能解，**不换措辞规避** |

## 7. 换人后的前三个动作

1. 查底本与线况：`test -f /e/starhub-base/.git/FETCH_HEAD`、`du -sh /e/starhub-base/.git`、`gh api repos/Kwei168/starhub/pages --jq .build_type`、远端 `main` 与本地 `HEAD`。
2. 若底本已完成 → 直接进 §4 批次①（不必等它，批次①不依赖底本，可以立刻开工）。
3. 任何推送前：`py -3.11 tools/data_api_push.py --check-only` → 按具体路径推 → 立即自查（`remote_drift_check.py` 看 `内容不同=0`）。**推送需要用户逐次批准，commit 默认留本地。**

## 8. 相关文档

- `HANDOFF.md` §8.15（本次出仓与执行读数）、§8.13（快照出仓先例）、§8.12（**推送窗口两条判据**）、§8.7（翻译链现状与熔断缺口）
- `docs/superpowers/specs/2026-09-20-git-repo-size-and-normal-flow-recovery.md` §7（G1/N1~N4/G2）、§13（本次定案与执行读数）、§4（断链分层与"别再修这个 .git"）
- `docs/superpowers/plans/warm-wood-mole.md`（本轮 Task 0~6 计划）
- `CLAUDE.md` §禁止事项 / 推送四步
- 判据与变异：`tests/rss_history/test_pages_deploy_wiring.py`、`.deploy-tmp/_mut_pages.py`
- 记忆条目：`starhub-pages-artifact-cutover-20260930`、`starhub-git-size-reclaim-options`、`starhub-build-time-inflation-cancel-spiral`、`starhub-rss-stale-chunk-zombie`（依据已变更）、`iron-rules-from-20260930-error-chain`、`feedback-git-history-is-the-audit-trail`

## 9. 未完成事项一句话总结

**存量 8.7G（本地）/ 5.21 GiB（远端）一分未减；增量从 75.5MB/场降到 23.5MB/场，还剩 16 个文件没处理，所以"轮转"只完成了最大的一项。**

### 3.1 第二趟执行中（21:56 北京时间追加，取代上面 §3 里"换人后第一件事"那条）

- **第二趟已起**：run `36725348747`，`dry_run=false confirm=TRIM`，13:56:35Z 起跑（正好卡在 14:00 整点场之前的空档，没排队）。
  推送与 dispatch 都经用户逐次同意（原话："你现在不推等着请客啊"）。
- **推送落点**：远端 main `fdb6e16f4e` -> **`a3f329f7a0`**；三个 blob 推完即时复查一致，独立漂移核对
  `内容不同=0 仅本地有=0 仅远端有=0`。推的是闸零三件套：
  `.github/workflows/repo-trim.yml`(`d75b4ffbcd`)、`tools/trim_commit_guard.py`(`5f98ee90d1`)、
  `tests/trim_guard/test_trim_commit_guard.py`(`2dafc8f94b`)。本地对应提交 `d6abd4c`。
- **dry-run（`36718697019`，success）实测读数**：站内 `.git` **5.3G -> 368M**；
  待剔四族 `rss-data-[1-9]*` 880 版 44.67GB、`rss_history*` 526 版 18.15GB、
  `rss_api_snapshot*` 565 版 17.62GB、`rss_cache.json` 222 版 7.12GB；runner 磁盘 145G 用 64G；
  **提交数 2039 -> 2037，少 2 条** —— 这 2 条就是闸零要逐个自证下落的对象。
- **第一趟差点没起第二趟，原因不是 CI 红**：守候脚本拿日志里搜 `::error::` 当判据，而 GitHub 会把 `run:` 脚本原文整段打进日志，
  workflow 里那四句守卫 `echo "::error::..."` 即使从未执行也照样出现 => 干净的 dry-run 被判成**假红**。
  **规矩**：判红只认 `jobs[].conclusion` / `steps[].conclusion` / annotations，绝不搜日志字符串。
- **闸零有测试且能跑红**：`tests/trim_guard/` 共 10 条，含一条真 git + 真 filter-repo 端到端（钉 `%cI`/`%p`/`--name-only` 的格式假设）。
  变异验证：把 `verdict` 改成恒 `OK-纯数据` 后 **4 条转红（含端到端那条）**，恢复后 10 条全绿。
- **⚠ 本地工作树现在是脏的，别当成自己的垃圾扫掉**：`template.html`、`index.html`、`daily-insight-history.html`、
  `docs/superpowers/specs/2026-09-22-nightly-deep-insight-design.md`、`_scratch/*` 都有改动，
  这些**一条都不在** `d6abd4c`/`a3f329f7a0` 里；其中几个疑似本地跑根脚本污染出来的产物（见 §4 批2"本地危险动作"）。
- **换人后的第一件事**：读 `E:/_trim_pass2.txt` 与 `E:/_trim_report.txt`（守候任务 `bb9yrr8jb` 负责落盘）。
  若见"已强推"：剩下全是人工——本地换新克隆、旧 `.git` **mv 进隔离区（不许 rm）**、量 CI `Checkout` 秒数与新克隆体积。
  若见 `BAD-*` 或 CAS 中止：照日志点名是哪几条提交、哪场构建，别猜也别重推第二次而不看原因。
---

## 十、交接给下一位：闸零已修 + 一条线上回归（2026-10-01 00:2x 北京时间追加）

### 10.1 闸零那次红，红在判据自己身上（已修，远端 `437a06ec94`）

`36729340505` 报 `基线 2043 != 重写后 2041 + 消失 7`。算术上这只可能是两种世界之一，
我先证明了**重写本身没问题**：

- 在真实历史上逐条核（blobless 克隆只拉 commit+tree，20 秒 1.1 MiB）：
  **只改被剔族的提交恰好 2 条** —— `8d7c81e2e9`（仅 `rss_history.json`）、
  `bc50bee761`（仅 `rss_cache.json`），与 CI 的 2043→2041 完全对上。
- CI 的基线文件也没被动过：我用同一条命令重放，`2043 头 + 15501 文件行 + 空行`，
  `wc -l` 正好 **19565**，与 CI 一字不差。
- 再用真实 2043 条消息/作者/原始日期（`--date=raw`）复刻一条同构历史，跑**真** filter-repo：
  消失恰好 2 条、凭空多出 0，`.git/filter-repo/commit-map` 标删的也正是那 2 条。
  ⇒ "键会漂"这条假设被证伪，**gpgsig 签名提交（真历史里 6 条）过一遍重写键也完好**。

所以病在判据自己：它拿 `rev-list` 的计数与**另一条** git 调用解析出的多重集相减，两者从不互校；
而 `git()` 只取 stdout、**把 rc 与 stderr 全丢了** —— "读到一半失败"和"提交真的没了"
在代码里长得一模一样。这正是手册 §8.12「守门命令要和判据一起被验证过才算存在」的同一类病。

**改法**：以 filter-repo 自己按 sha 逐条写的 `.git/filter-repo/commit-map` 为唯一事实源
（被删的写全零 sha），不再靠 (提交时间, 标题) 猜身份；map 判删数与 HEAD 实际可达数互校；
缺 map / map 没覆盖基线 / git 非零退出一律红。基线抓取另加 `--no-renames`
（重命名检测会把一次 delete+add 并成一条改名、只报目标名，"带走源码"的提交能被读成"只改数据"= 假绿）。

验证：`tests/trim_guard` 21 条全绿；6 个变异各打死指定那条（含把 `raise` 拆掉、
把 `--no-renames` 删掉、缺 map 当通过）；端到端反向断言改用真实事故形状
（把 `final.py` 也纳入剔除名单 → 必须点名 `BAD-含非数据文件`）。

### 10.2 第三趟被整点构建取消（**这不是闸零的锅，是并发组的锅**）

`36740181139` 在 16:01:33Z 被 `cancelled`，位置就在 filter-repo 那一步。原因：
`repo-trim.yml` 与 `update.yml` 共用并发组 `starhub-update`，而 **`update.yml` 是
`cancel-in-progress: true`** ⇒ 只要有一场新构建进组，正在跑的重写就被当场取消。
重写一趟要 6~8 分钟，所以只能挑"上一场 Commit 落地之后 ~ 下一场检出之前"的空档起，
**并且起完之后不要让任何构建挤进来**。第二趟（`36725348747`）赶在 13:56Z 就是这么躲过的。
存量仍未减：远端 main 还是 `437a06ec94`，`.git` 5.21 GiB 一分未动。

### 10.3 线上一条真实回归：分块退化成 60MB 巨石（已修，待构建携带上线）

用户报"只有 61 个源"。取证：

- 浏览器控制台：`[starhub] chunk1 onload 但 __CHUNKS[1] 缺失（文件截断或内容异常）`，
  `window.__CHUNKS` 只有 `[61]`（chunk0 的 61 源）。
- `HEAD rss-data-1.js` → `Content-Length: 60,378,325`（60MB），`x-origin-cache: HIT`。
- 15:00 那场构建日志：`[数据分块] rss-data-1.js: 699 源 10293 篇 50.6 MB`、
  `chunk0 360 篇 / 1 个后台块`。

根因**不在加载器**：`MAX_CHUNK_BYTES = 80MB`，而后台数据实测 50.6MB ⇒ `n_chunks = 1`，
"分块"其实只有一块。慢网络整块取不到时 script 的 onload 照样触发、数据从未赋值，
页面就只剩首屏。已改为每块 6MB + 24 块硬顶（`dc2e948`）。

新判据 `tests/rss_history/test_chunk_budget.py` 4 条：必须多块、单块体积上限、
**拆分零丢条目**、每块以分号收尾且写对 `__CHUNKS[i]` 槽位。变异（把上限改回 80MB）
⇒ "必须多块"那条转红，还原后全绿。

### 10.4 batch① 已做（`9f2eca0`，未推）与 batch② 的硬约束（别照着原计划做）

4 个页面 HTML 退出两处 add 清单，staging 按名字取新鲜产物 + 每块 `test -s` 硬守卫；
判据 13 条 + 变异 V1~V5 全部钉住。**顺带堵掉两个洞**：行首判据看不见
`if [ -f x ]; then git add x; fi` 这种条件式；`cp -rf . _pages` 这种递归整拷会把
被 gitignore 的语料（实测 398M）第一次公开发布。

⚠ **batch② 不迁进 `actions/cache` 的理由已按 22:45 实测更正（见 §10.15）**：
`update.yml:260` 记的 **9.97 / 10 GB、79 个键** 是 09-20 的读数，现在淘汰工具已把它降到
**11 个键 / 约 1.24 GiB**——**配额不是障碍了**。不迁的真实理由换成另一条（缓存未命中会让
7 天热榜轨迹静默变空），见 §10.15。
而且已经需要 `tools/trim_actions_cache.py --keep emb-cache=4 --keep rss-history=5`
按族淘汰最旧键才挤得下。再塞 6 族状态进去 = 把 emb-cache / rss-history 的键挤掉 =
§7.15 那种"静默退化成全量"的事故重演一遍，只是换了个通道。**配额是硬约束，先量它再谈迁通道。**

同理，`insight_tracking_history.jsonl` / `daily_insight_tracking_history.jsonl` 是
**人工统计要从远端拉**的台账（CLAUDE.md 明写"统计口径数据一律拉远端"），
它们出仓等于把分析入口拆掉。这两条留在 git。

### 10.5 验收读数（2026-10-01 01:3x 北京时间，全部是实测量，不是推断）

| 要回答的问题 | 实测 | 怎么量的 |
|---|---|---|
| 存量清掉了吗 | 重写后 `.git` **368M**（重写前 5.3G）；`rss-data-1.js` 在 main 历史里**零版本** | repo-trim `36746250645` 日志 + `commits?path=rss-data-1.js` 返回空 |
| 新克隆真的小吗 | `--depth 3` 克隆 `.git` = **9.3 MB**（旧本地库 8.7 GB） | 本机 `du -sk` |
| CI 检出变快了吗 | `fetch-depth: 0` 全历史 **259s → 135s** | run `36748326046` 步骤时间戳 17:00:39→17:02:54 |
| 增量止血生效了吗 | 那场提交入仓文件 **18 个 → 12 个**，4 个页面 HTML 全部不再入仓 | `commits/e0c2e4879a` vs `commits/22b29963f7` 的 files[] 逐个对比 |
| 分块修好了吗 | 线上 `rss-data-1..9.js` 各 **6.6–7.3 MB**，chunk10 起 404（加载器按序停住）；原来是**一块 60,378,325 B** | 逐文件 `HEAD` 取 Content-Length |
| 前端真合并了吗 | `window.__CHUNKS` 逐槽填充，页面自报 **"已加载全部 7295 篇内容（新增 6935 篇）"**；修复前只有 chunk0 的 61 源 | 浏览器 evaluate + 控制台 |
| 轮转窗口还在工作吗 | 那场里 `build_logs/2026-09-16.jsonl` 与 `summary_2026-09-16.json` **被删**（14 天清理在提交侧留下删除记录） | 同一 commits files[] 对比 |

### 10.6 新装的体积闸（远端 `efedc7dbfa`）

`tools/size_tripwire.py` 接在 update.yml **两处** add 分支的 `git commit` 之前：
单文件 >16 MiB 判红（挡住提交与部署），本场入仓合计 >25 MiB 只 `::warning::`。
它防的是这次的根病：**四族产物没有体积上限，静静长了一年多，没有任何检查会红。**

写它自己抓到两个真 bug，都值得记：
1. `git cat-file -s ':(path)'` 的路径魔法把括号当字面量，实测 `fatal` —— 改走
   `ls-files --stage -z` + `cat-file --batch-check`；
2. git 调用失败被静默当成"本场没文件"= 放行。**这条变异第一版没被打死**，
   因为测试只断言 main 的退出码；改成直接打在 `staged_blobs()` 边界上（要求抛 RuntimeError）
   才抓住。⇒ 又一次印证手册 §8.12：判据必须自己可被证伪，否则是装饰。

### 10.7 还剩两个**只有你能决定**的口子（我没动，理由写清楚）

1. **GitHub 网页显示的 `.size` 仍是 5.48 GB**，且不是 GC 滞后：`refs/pull/1/head`、
   `refs/pull/2/head` 是用户侧无删除 API 的内部引用，仍锚着旧对象 ⇒ 强推只重写了
   `refs/heads/main`。要让那个数字真降，只能开工单或重建仓库。**"推完了"不等于"降下来了"，
   这句别在汇报里糊过去。**
2. **本地那个 8.7 GB 的 `.git` 我没动**。它带着 293 条未推提交，而你说过
   "如果把 git 历史清了 你更不知道咋回事了"。安全部分已做：新克隆在 `E:/starhub-new`
   （depth 3，9.3 MB）。要收尾就跑
   `mv .git /e/_quarantine/starhub-old-git-$(date +%s)` 再用新克隆接手，**不许 rm**。

### 10.8 我自己引进的一次真实事故（A2 blocking 冻结整场构建）与修复读数

**18:00 那场（head `87b3bae53d`）整场零产出**：`Quality gate A2 (blocking)` 红，
连带 `Fetch stars / Commit / Stage Pages / Deploy Vercel / Deploy Pages` 全部 skipped，
站点从 18:00 起停止更新约 45 分钟。日志原文：
`tests/rss_history/test_size_tripwire.py` 6 条 FAILED，
`AssertionError: ('commit','-q','-m','seed') rc=128 —— Please tell me who you are`。

根因**是我踩了 CLAUDE.md 明写的坑**：新增门禁测试不得依赖环境变量的存在与否。
CI 的 git 全局配置没有 `user.name/user.email`（workflow 只在 Commit 步里现设），
而我的夹具要 `git commit` 造基线提交；本机配了身份 ⇒ **本地绿、CI 红**。
修法：夹具用 `-c user.name=T -c user.email=t@e` 只作用于那一条命令，不碰全局配置。

**验收口径也跟着改了**（这是这次最该记住的一条）：以后凡是自己造 git 仓的门禁测试，
必须用 `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null` 复现 CI 的无身份环境再跑一遍。
按这个口径回扫：`tests/rss_history/test_size_tripwire.py` 8 条全绿、
`tests/trim_guard` 21 条全绿（那批本来就用 `GIT_AUTHOR_*`/`GIT_COMMITTER_*` 显式给身份，未受影响）。

修复后实测（run `36757604994`，18:18 起跑，构建提交 `f1568ca56e`）：
- `Quality gate A / A2 / A3` 全部 success，站点恢复更新；
- 体积闸在 CI 的第一份真实读数：**12 个文件合计 17.91 MiB**
  （hot_history 7.91 / analysis_snapshot 3.56 / translations 3.17 / rss_trend 1.11 /
  insight 台账 0.76 / daily_insight 台账 0.37 / rss-data-0.js 0.35 / build_logs 0.32 …），
  离 16 MiB 单文件上限有余量 ⇒ **没有误拦**；
- 入仓文件数稳定在 12（batch① 前是 16-17），4 个页面 HTML 不再入仓。

### 10.9 剩下的 12 个文件为什么必须留在 git（别再来一遍"迁进 cache"）

每一个都有**跨场读回**且**各自已有轮转窗口**，实测都在工作：
`hot_history.json` 7 天、`rss_trend_history.json` 14 天、`build_logs/*.jsonl` 14 天
（18:00 前那场就看见 `build_logs/2026-09-16.jsonl` 与 `summary_2026-09-16.json` 被删并提交了删除记录）、
两个 `*_tracking_history.jsonl` 台账（日志自报"保留 322 条"，且人工统计要拉远端）、
`analysis_snapshot.json`（`_load_prev_analysis()` 把上一场字段承接过来）、
`translations.json`（自带条数上限）、`trending_snapshot.json`（`fetch_and_build.py:432` 读回）。
所以"持续新增膨胀"的根因从来不是这些有上限的状态，而是**四族没有上限的产物** ——
它们已经出仓，而体积闸负责在任何人下次不设上限时当场判红。

### 10.10 五小时后的复测：体积确实在降，但**降停了的原因和我先前写的不一样**

| 时点 | GitHub 显示 `.size` | 说明 |
|---|---|---|
| 重写前（手册 §4 记的） | 5.21 GiB | 5,480,050 KB |
| 17:0x（强推后约 15 分钟） | 5.23 GiB | 还没回收 |
| **22:30（强推后约 5.8 小时）** | **2.43 GiB** | 2,552,780 KB —— **确实在降**，我 §10.7 里"大概率不会降"那句按实测作废 |

还剩的 2.43 GiB 是谁：**`refs/heads/daily-insight-fix-v2` = `e806aadb7b6f40d51cdfe311e197f79ac194b82e`**，
它仍指着重写**前**的旧血统（旧 55MB 分块都挂在那条线上）；另有 `refs/pull/1/head`、`refs/pull/2/head`
（用户侧无删除 API）。

⚠ **手册 §4 那句"删 daily-insight-fix-v2 零独有提交"现在已经不能作为依据**：
22:31 实测 `compare main...daily-insight-fix-v2` = `ahead_by=895 behind_by=1493 diverged`，
而这条分叉**是我这次重写造出来的**（重写后 main 的提交 sha 全变，旧提交自然变成"分支独有"）。
要判"删了不丢代码"必须做**内容级**核对（比对 tree，或对那 895 条跑 `git patch-id` 与 main 的
重写后提交逐条配对），**数提交条数在这种时候是错的**。我没删，也没让任何人凭旧笔记去删。
好消息：这些旧对象在你本地 8.7G 的 `.git` 里**全都在**，真要回溯也有底本。

### 10.11 稳态已成立（六场连续实测，不是外推）

每场写进 git 的字节（按 Contents API 逐文件真实体积求和）：

```
14:22  17 文件  24.1 MiB   ← batch① 前，一路在上爬
16:38  16 文件  21.5 MiB
17:18  12 文件  17.8 MiB   ← batch① 生效
18:44  12 文件  17.9 MiB
19:19  11 文件  18.1 MiB
20:19  12 文件  18.4 MiB
21:20  12 文件  18.2 MiB
22:18  12 文件  18.4 MiB   ← 六场平线
```

- 19/20/21/22 四场整点构建全部 `success`（18:00 那场是我引进的 A2 假红，15 分钟内修好）；
- 体积闸在 CI 连续报数、零误拦：22:18 那场 `12 个文件合计 18.38 MiB（单文件上限 16 MiB）`；
- 线上 `rss-data-0..9.js` 存在（各约 6.7–6.9 MB），`chunk10/11/12` 全 404 ⇒ 前端按序加载后正常终止；
  四个页面 200 且体积新鲜；
- 剩下这 18.4 MiB/场是**有上限的跨场状态**（§10.9），不是无界增长。

### 10.12 收口：剩下 2.43 GiB 的**唯一**锚是 `refs/pull/*`，所以删分支是无用功（22:36 实测）

| 引用 | 指向 | 与 main 的关系 |
|---|---|---|
| `refs/heads/main` | `e4ad2acc8e` | 重写后血统 |
| `refs/heads/daily-insight-fix-v2` | `e806aadb7b…` | `compare main…此sha` = **diverged, ahead=895** |
| `refs/pull/2/head` | **`e806aadb7b…`（同一个）** | 同上 |
| `refs/pull/1/head` | `a2ea918ea6…` | **diverged, ahead=886** |

- `refs/pull/2/head` 与那条分支是**同一个 commit** ⇒ **删掉 `daily-insight-fix-v2` 一个字节都回收不了**，
  旧血统仍被 PR 引用钉住。手册 §4 里"可顺手删分支"那条按实测作废（它当时针对的是重写前）。
- 分支相对 main 那 32 个 `removed` 文件全是 `.qoder/repowiki/**` 旧结构路径，
  main 在 `f350e8029e 2026-09-13 chore: 更新 qoder wiki 结构…` 里重构过目录名 ⇒ 是被取代的旧路径，
  不是没合进来的工作。**但这条已无关紧要**，因为删不删都省不出来。
- 真要回收这 2.43 GiB 只有两条路：**开 GitHub 工单请侧方清理 `refs/pull/*`**，或**重建仓库**。
  两者都是你的决定级动作（重建会换 remote URL，牵动 Pages/Vercel/cron-job.org 三处配置）。
  好在 GitHub 已自行回收了 2.8 GiB（5.23 → 2.43 GiB，5.8 小时内），可以继续观察是否还会降。

### 10.13 batch① 的产物级验收（不用"步骤绿"当判据）

线上 `rss-aggregator.html` 的 `BUILD_TS = 1790806080041` = **2026-09-30T22:08:00Z**，
正是 22:00 那场（`e4ad2acc8e` 22:18 提交）构建时刻；上一轮 17:0x 取样时页面 `BUILD_TS` =
`2026-09-30T15:10:28Z`，同样等于当时最新一场。⇒ **Pages 发的是每场新鲜产物，
不是 git 里那份停更的副本** —— 这才算 batch① "退出提交清单但不丢发布"的真正证据。

### 10.14 测量结论：**不要再做第二次历史重写**，剩余膨胀已经不在 git 侧

22:40 逐族实测（重写后的 main 历史里每族版本数 × 当前体积 = 未包体积；`build_logs` 那行按目录统计不准，忽略）：

```
hot_history.json              606 版   7.96 MiB/版   未包 4821 MiB
translations.json             868 版   3.17 MiB/版   未包 2753 MiB
analysis_snapshot.json        632 版   3.57 MiB/版   未包 2258 MiB
rss-aggregator.html          1036 版   3.05 MiB/版   未包 3159 MiB
rss_trend_history.json        627 版   1.11 MiB/版   未包  699 MiB
index.html / ai-daily.html / daily-insight-history.html  合计未包  583 MiB
其余（台账 / 快照 / chunk0）                              合计未包  ≈ 813 MiB
                                             16 族合计未包 ≈ 14.7 GiB
```

而这 14.7 GiB **打包后总共 368 MB**（runner 里 `du -sh .git` 实测）⇒ delta 压缩比约 40:1。
推论三条，都别再用直觉反驳：

1. **再剔"已停更的 4 个 HTML 的历史版本"没意义**：它未包 3.7 GiB，但打包后只占约 30–40 MB，
   代价是又一次破坏性重写 + 一次强推窗口。不做。
2. **剩下的 14.7 GiB 未包主体是跨场状态**，删不得（§10.9：它们全是下一场要读回来的输入）。
3. **今后的自然增长有界且慢**：按 368 MB / 2047 条 ≈ **0.18 MiB/场** 推，约 4 MiB/天、1.6 GiB/年；
   而"无上限产物"这一类已经被体积闸当场拦住。真要再降一个量级，只有
   **收紧窗口口径**（hot_history 7 天 / analysis_snapshot 承接范围 / translations 条数上限）
   这一条路 —— 那是**产品口径变更**，不是清理动作，必须由你拍板，我不会顺手改。

远端 `refs/heads/main` 已达 368 MB 量级；GitHub 面板还显示的 2.43 GiB 全部来自
`refs/pull/1|2/head` 钉住的重写前血统（§10.12），**与 main 无关，也不是再剔几个文件能解决的**。

### 10.15 更正两条 + 状态族是否"在涨"的实测答案（22:4x）

**(a) 缓存配额已不是障碍。** 实测 `actions/caches`：**11 个键、约 1.24 GiB**
（`emb-cache` 5 × 224 MiB + `rss-history` 6 × 20 MiB）。`trim_actions_cache.py --keep` 生效了。
所以 §10.9 里"缓存在满负荷所以不能迁"这句依据作废。不迁的理由改为：**per-run 键 + 未命中即静默失忆**
（hot_history 一旦没恢复回来，7 天轨迹直接变空、要几天才重新攒起来 —— 就是 §7.15 那个事故换通道重演）。
git 反而是这里更可靠的家。

**(b) 三个状态族的"当前体积"轨迹实测（每族取 5 个历史版本的真实 blob 大小）：**

```
hot_history.json      09-09 0.00 → 09-14 4.06 → 09-19 9.64 → 09-24 8.92 → 09-30 7.96 MiB   ← 峰值后回落
translations.json     09-01 0.00 → 09-07 3.54 → 09-14 10.44 → 09-22 4.55 → 09-30 3.17 MiB   ← 被上限裁过
analysis_snapshot     09-08 0.05 → 09-13 1.14 → 09-18 3.66 → 09-24 3.92 → 09-30 3.57 MiB   ← 平台期
rss_trend_history     09-08 0.00 → 09-13 0.32 → 09-18 0.78 → 09-24 1.04 → 09-30 1.11 MiB   ← 14 天窗口，趋平
```

⇒ **轮转是在工作的**，文件本身没有无限叠加。§10.14 那个"未包 4.8 GiB"是
**版本数 × 体积**（606 / 868 / 632 个版本），不是当前数据在涨。

真正还在累加的只有一件事：**每场都给这些文件存一个新副本进 git**，这三族占每场入仓
14.7 / 18.4 MiB ≈ **80%**；delta 压缩后 ≈ 0.18 MiB/场 ≈ 1.6 GiB/年 —— 有界但确实非零。
要再降一个量级只有两条路，且**都改行为，需拍板**：
- **降频入仓**：三族只在每天 UTC21:00 全量场提交，中间场读上一次已提交版本（最多滞后 24h）
  ⇒ 每场 18.4 → 约 3.7 MiB，pack 增速降约 5 倍；代价是热榜轨迹/洞察承接的新鲜度。
- **收紧窗口**：hot_history 7 天→72h、analysis_snapshot 承接字段收口、translations 上限下调
  ⇒ 直接砍当前 7.96 / 3.57 / 3.17 MiB 的体积；代价是趋势检测视野变短。

### 10.16 `pages-build-deployment` 不再运行是**切换的必然结果**，不是坏了

- `gh api repos/.../pages` → **`build_type=workflow`**（09-30 18:00 北京那场切的，§8.15）。
  legacy 分支源才会触发内置的 `pages-build-deployment`；改成 workflow 发布后它天然不再运行。
- 实测它最后一次跑：**2026-09-30T09:19:13Z**（`event=dynamic`，success）—— 正好停在切源那场（10:00Z）之前。
- 新通道逐场可核：`Stage Pages site` / `Upload Pages artifact` / **`Deploy to GitHub Pages` = success**
  （19:00 场与最新一场都是），`Deploy to Vercel` 也 success。
- **产物级证据**：线上 `rss-aggregator.html` 里 `BUILD_TS = 22:08:00Z`，等于 22:00 那场的构建时刻
  （17:0x 取样时同理等于当时最新场）⇒ 发的是新鲜产物，功能无残缺。
- 代价说清楚：workflow 发布下，**一场构建失败 = 这场不发布 Pages**（18:00 我那次 A2 假红就是这个形状），
  站点不会坏、但会停在上一版。这比 legacy 多一层耦合，是当初切源换取"大产物不入 git"的已知对价。

### 10.17 顺手查到一条已存在的死端点：`/api/build_log` 结构上永远读不到数据

三条独立证据（22:49 实测）：
1. `api/build_log.js:14` 读 `join(process.cwd(), 'build_logs')`，`existsSync` 不命中就返回空
   —— 线上 `?summary=1` 实测 `{"builds":0,"triggers":0,...,"total_items_latest":0}`；
2. **两道排除同时生效**：`.vercelignore:31` 写着 `build_logs/`，而 `update.yml` 的 prune 步
   又 `rm -rf ... build_logs docs`（在 `vercel --prod` 之前）⇒ 就算撤掉一道，另一道仍然拦着；
3. 全仓搜前端调用：**template.html / build_rss_aggregator.py 里没有任何 `/api/build_log` 引用**，
   只有写入侧 `build_logger.append()`。`vercel.json:12` 却仍为它声明 `maxDuration: 10`。

后果与口径：`build_logs/*.jsonl` 每场仍占约 0.32 MiB 入 git，但它的运行时读者是空的；
现在真正消费它的只有 `build-log-summary.yml`（从 checkout 里的 build_logs 生成 summary 提交）
和人眼看 git。**这不是本次改动造成的回归**，是历史遗留的口径不一致。

三个选项（都算功能变更，等拍板，我不动手）：
- 让端点真能用：`.vercelignore` 去掉 `build_logs/` **且** prune 步不删它（会把 14 天日志发布上线，含内部错误文本，需先审内容）；
- 让它读远端：函数改走 GitHub Contents/raw API 读 main 上的 `build_logs/`（不发布数据，但有 API 配额与延迟）；
- 承认它是死的：删 `api/build_log.js` + `vercel.json` 声明 + 手册 §3 那一行，
  并考虑 `build_logs/` 是否还需要每场入 git（若只服务 summary，可让 summary 自己生成）。
