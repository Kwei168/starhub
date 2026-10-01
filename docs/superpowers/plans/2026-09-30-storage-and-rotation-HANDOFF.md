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

后果与口径：`build_logs/*.jsonl` 每场仍入 git，但它的运行时读者是空的（**每场的真实代价见
§10.18 实测：打包后 0.05 MiB/场，不是我先前估的 0.32 MiB**）；
现在真正消费它的只有 `build-log-summary.yml`（从 checkout 里的 build_logs 生成 summary 提交）
和人眼看 git。**这不是本次改动造成的回归**，是历史遗留的口径不一致。

三个选项（都算功能变更，等拍板，我不动手）：
- 让端点真能用：`.vercelignore` 去掉 `build_logs/` **且** prune 步不删它（会把 14 天日志发布上线，含内部错误文本，需先审内容）；
- 让它读远端：函数改走 GitHub Contents/raw API 读 main 上的 `build_logs/`（不发布数据，但有 API 配额与延迟）；
- 承认它是死的：删 `api/build_log.js` + `vercel.json` 声明 + 手册 §3 那一行，
  并考虑 `build_logs/` 是否还需要每场入 git（若只服务 summary，可让 summary 自己生成）。

### 10.18 外部审查逐条核实（10-01 07:5x 实测）：五条对、一条**被证伪**、两条口径错，另有两条它没查到

逐条用 GitHub API / 线上端点 / 工作树对过，不采信任何"看起来合理"：

| 审查的说法 | 实测 | 判定 |
|---|---|---|
| 远端 `build_logs/` = 30 文件 / 44.2 MiB | 46,369,566 B = **44.22 MiB**（15 个 jsonl 41.87 MiB + 15 个 summary 2.35 MiB） | ✅ |
| 单个最大 4.27 MiB | 最大是 `2026-09-19.jsonl` = 4,372,978 B = **4.17 MiB**（= 4.37 MB），两个口径都不是 4.27 | ⚠️ 单位混用 |
| `update.yml` 216/232/257/357、`Deploy to Vercel:361`、`.vercelignore:31`、`vercel.json:12` | 逐行对上：216 append、232/257 两条 add 清单都含 `build_logs/`、357 是 prune 步（346 起）里的 `rm -rf … build_logs docs`，361 才是 Vercel | ✅ |
| 09-30 起 25 次提交碰 `build_logs`，其中 24 次是主构建 | `commits?path=build_logs&since=2026-09-30T00:00:00Z` = 25 条 = 24 × `chore: auto update stars` + 1 × summary | ✅ |
| `?summary=1` 恒返回 `builds:0` | 线上实测 `{"total":0,"entries":[]}`、`{"date":"2026-09-30","builds":0,…}`；`api/build_log.js:14` 读 `process.cwd()/build_logs`，目录不在就 `[]` | ✅ |
| **"accumulating forever / 一直在叠加"** | **错。14 天轮转在跑。** 见下面三条硬证据 | ❌ 被证伪 |
| "~70 MiB/天" | 作为**未包**口径接近事实（实测未包 58 MiB/天），但落到仓库是**打包后 1.9 MiB/天** | ⚠️ 口径 |

`build_logger.cleanup(14)` 不是装饰，三条独立证据：
1. `update.yml:195` 每场构建都在调 `removed = build_logger.cleanup(14)`；
2. 远端 tip 最旧文件 = `2026-09-17` = 今天(10-01) − 14，且 `cleanup` 的判据是 `file_date < cutoff`
   （`cutoff` 按 **BJT** 算）⇒ 删除固定发生在北京零点后的第一场构建；
3. 删除提交本身可查：`e0c2e487`（2026-09-30T16:38:22Z = 北京 10-01 00:38）的 files 里
   `removed build_logs/2026-09-16.jsonl`、`removed build_logs/summary_2026-09-16.json`、
   `added build_logs/2026-10-01.jsonl`。远端 `contents/build_logs/2026-09-16.jsonl` 现在 404。

⇒ **tip 有界（~44 MiB 稳态），无界的只有"每场重写 jsonl 产生的历史 blob 版本"这一项**，
   而它的真实体积比审查说的小一个量级。

审查没查到的两条（这两条才决定要不要动功能）：
1. **`summary_*.json` 零读者**：`api/build_log.js` 的摘要模式（60–80 行）是**从 jsonl 现算**的，
   从不打开 `summary_*.json`；全仓也搜不到任何读取方 ⇒ 每小时写出来的摘要目前无人消费，
   而 `build-log-summary.yml` 仍为它 `git add build_logs/summary_*.json` + 提交。
2. **"hourly" 只是声明，实测被 GitHub 限流**：`event=schedule` 的 Build Log Summary 在 09-30 只有
   01:05 / 08:00 / 15:38 / 20:33 四场，20:33 之后到 23:50 连续三个整点没触发。
   update.yml 那 24 场全是 `workflow_dispatch`（cron-job.org 主力链在驱动，与已知结论一致）。

**增长率的实测口径**（这次不外推）：`git clone --depth=48` 拿到 48 场 ≈ 31.5 小时的窗口，
`git rev-list --objects HEAD -- build_logs` ⇒ **54 个 blob 版本 / 未包 76.2 MiB /
`%(objectsize:disk)` 合计 2.48 MiB** = **0.052 MiB/场 ≈ 1.9 MiB/天 ≈ 57 MiB/月**，delta 压缩比 31:1。

推论：`build_logs` 对"不再持续新增膨胀"的实际贡献比 §10.14 那几张状态族表还小，
**不值得为它单独改功能**；真要收口，就连"死端点 + 零读者的 summary 工作流"一起处理（选项见 §10.17），
而且必须一起动 —— 只把 `build_logs/` 从 add 清单摘掉会让 `update.yml:407` 的 `build_logger.summary(today)`
读不到历史 jsonl，摘要从"近 7 天"静默退化成"仅当场"，那正是我最不该再造的那类静默降级。

两条自我更正：
- §10.14 只留了一句"`build_logs` 那行按目录统计不准，忽略"，**具体数字没写进表**（全文搜不到）；
  根因是当时按**目录**路径查体积（目录不是 blob，查出来必然是 0）。审查给的 44.2 MiB 才是远端 tip 真实值。
- 我这次先写的"§10.14 表里 build_logs 记 0.00 MiB"是**没核对就下的引用**，实际表里没有那一行 ——
  已改成上面这句。教训：引用自己旧文档的具体数字之前必须 grep 到原文，不能凭"我大概是这么写的"。
- §10.17 原先写的"每场约 0.32 MiB 入 git"是估的，实测 0.052 MiB/场（打包后），已就地改掉。

测量陷阱备忘：隔离的老 `.git` **本身是浅仓**（有 `shallow` 文件，`rev-list --count HEAD` 只有 391），
所以从它算出的任何"全历史体积"都是截断下界，不能当结论引用 —— 要量历史就用远端 shallow clone 并显式写明窗口。
（该目录已于 2026-10-01 删除，见 §10.21；这条教训与它引用的读数仍有效。）

### 10.21 隔离的 8.7 GB 旧 `.git` 已删除（10-01 09:0x，核心任务收口）

用户授权口径是"**确定没有风险的前提下可以删**"，所以先做四道核验，再动手：

1. **本地库是否依赖它**：`.git/objects/info/alternates` 不存在、`.git/config` 里没有任何指向
   `_quarantine` 的引用、`git fsck --no-dangling` rc=0 ⇒ 新对象库自足，删它不会炸库。
2. **旧 index 里有没有"已 add 从未 commit"的唯一内容**：逐条比"旧 blob == 现 HEAD / == 工作树 /
   blob 本身在当前库里"，得 18 条 `ONLY`，但逐条回查它们**正是旧 HEAD 的树内容**
   （`template.html 3fb215a11e`、`index.html 472de96afc`、`rss-data-0.js db4ad1e73d` …），
   即已被远端后续版本取代的旧版本，不是未保存工作。
3. **`refs/stash`（两条 09-18 WIP）是不是独有功能**：先取"stash 相对自身父提交的增量"再逐行查现状。
   stash@{1} 增量为 0；stash@{0} 有 57 条实体新增行、其中 6 条在今天的文件里**找不到原句** ——
   但这 6 条的概念全都还在（`RETRIEVAL_TOP_K` 2 次、`_ragas_ctx` 2 次、`global_context` 7 次、
   余弦 6 次 / 相似度 8 次、`Top15` 3 次、`_llm_phase1` 3 次、`全局检索` 5 次）
   ⇒ 是**已落地功能的旧草稿**，不是丢失的能力。两条 WIP 的 diff（103 KB / 93 KB）连同 refs
   已导出到 `.deploy-tmp/_quarantine_forensics/`，删除后草稿仍可回读。
4. **分支**：`daily-insight-fix-v2` 与 PR#2 head 同 sha（此前已证），删它回收不了任何字节。

**一条必须记下的自纠错**：第 3 步我第一版用 shell 的 `if ! grep -q …` 判断，Git Bash 把 `!` 当命令执行，
57 次判断一次都没真跑，却打印出"今天已不存在 = 0"——**假绿**。换成 Python 逐行判定才拿到真实数字。
教训：核验脚本自己也要被核验；"跑完了且没报错"不等于"跑对了"，尤其当输出恰好符合预期时。

执行与结果：`rm -rf /e/_quarantine/starhub-old-git-20261001-072905`（8.7G）
⇒ E: 盘占用 71G → 62G、可用 242G → **251G**，回收约 9 GB。
删后新鲜验证：`git fsck` rc=0、`git status` 干净、`git show HEAD` 正常、
`pytest tests/rss_history tests/site_nav tests/rss_translate` = **215 passed**。

### 10.22 我把 blocking 闸接红了一场（10-01 09:00，head=bd96d24）——根因是"job 级 env 改变被测分支"

现象：`36798984025` 在 **Quality gate A2** 上 `INTERNALERROR … SystemExit: 1`，A2 是 blocking
⇒ 该场没提交也没部署，Pages/Vercel 自 08:19 那场之后停更（下一场自愈，前提是我把接线改对）。

两层原因，都要记住：

1. **我接错了对象**：`tests/rss_translate/test_translate_engines.py` 是**脚本风格**（模块末尾
   `if failures: sys.exit(1)`），被 pytest 当测试模块导入 ⇒ 一旦它有失败项就是 INTERNALERROR 而不是普通红。
   我在 §10.20 刚写下"rss_composite/rss_date/rss_sort 是脚本风格不能接"，却把同类的第四个目录接了进去 ——
   因为 `test_gate_wiring.py` 只问"目录里有没有 `test_*.py`"，没问"这些文件能不能被 pytest 收集"。
2. **本地全绿、ubuntu 红的确切原因**（已用复现证明，不是推测）：`update.yml:35-36` 的 env 是
   **job 级**，`AGNES_API_KEY/AGNES_API_KEYS` 会注入**每一个步骤**，包括 A2；
   `build_rss_aggregator.py:207` 的 `_AGNES_KEYS` 正是从这两个变量构建。而
   `_agnes_translate()` 在 `1919` 行按 `len(_AGNES_KEYS) > 1` 分叉：**多 key 时 429 只轮转 key 并返回 None，
   不进罚期**（`1928-1930` 才是罚期分支）。`A2b/A2c` 断言的恰是罚期 ⇒ 有 key 的 CI 必红、无 key 的本地必绿。
   复现命令（本机，注入两个假 key）：

```
AGNES_API_KEYS="fake1,fake2" python tests/rss_translate/test_translate_engines.py
  [翻译] Agnes 429，轮转到 key[1]
  [PASS] A2a / [FAIL] A2b / [FAIL] A2c   →  13 通过 / 2 失败
```

⇒ 判据写法本身也错了：它设的是 `B._AGNES_KEY`（单数），而生产代码读 `_AGNES_KEYS`（复数），
key 池由环境决定 ⇒ **任何依赖全局端点状态的判据，都必须自己把状态设成确定值**，不能靠"机器上恰好没有 key"。

顺带一条**真实缺陷**（不是这次造成，未动）：多 key 时 429 永远只轮转、`_AGNES_OFFENSES` 不涨、
不进罚期 ⇒ 若所有 key 同时被限流，构建每次调用都会继续打 Agnes，没有任何退避。
`A2b/A2c` 想守的就是这个性质。修它属于改逻辑，按用户暂停令未动。

### 10.23 `insight-pipeline-flow.md` 的 Trending 输入节点是误画，已删（10-01 09:5x）

`docs/insight-pipeline-flow.md` 泳道 1 里 `I5["GitHub Trending"] --> SUM` 是当时 agent 乱画的：
`build_daily_insight.py` 全文 **零次**出现 `trending`，其真实输入汇总打印（5364 行）只有
`RSS / 热榜 / AIHOT / AGI Hunt` 四路。误画大概源自两个同名词：`trending_snapshot.json` 的读者是
`fetch_and_build.py:432`（首页排行榜），而 `build_rss_aggregator.py:129` 又定义了同名常量
`TRENDING_SNAPSHOT_FILE` —— 照着常量名反推输入层就会把它接进洞察链。
现已删除 `I5` 节点与其入边（全文 `I5`/`Trending` 零残留，`SUM` 剩 4 条入边，与该节点自身文字一致），
并在 `2026-09-22-nightly-deep-insight-design.md` 的"已知挂起"处留痕改准。



### 10.19 RSS 页控制台的三类错误与四处孤儿（10-01 08:0x 取证并修）

控制台上（Pages 版，一轮加载）：**16 次 `translate.googleapis.com` 请求 / 8 条不同文本 / 0 次成功**，
Chrome 报成 CORS + `net::ERR_FAILED`；另有 `rss-data-10.js` 必 404、`hot_snapshot.json` 预载未被使用、
新华网 OSS 图 Mixed Content、BBC 图 `ERR_CONNECTION_CLOSED`。

修了四条，每条都是"判据先红→改→再绿→变异自证能红"：

1. **`_needsTranslation` 会被符号骗**。旧口径 `cjk < t.replace(/[\s\d\p{P}]/gu,'').length*0.3`
   没排 `\p{S}`（`+ = < ~`），ANSI 残片 `[1m` 也不算标点 ⇒ 线上那条**中文**垃圾文本
   （`💻基本信息` + 78 个 `+`）被判成"需要翻译"。新口径：剥 ANSI/URL/标点/符号后**必须有拉丁词**、
   中文不占多数、且不是 HN 元数据样板（`Article URL:/Points:/# Comments:`）。
2. **断路器阈值按"失败性质"分两条**，不是简单调小：连接层不可达（TypeError/Failed to fetch，
   本环境实测成功率 0）第一批就熔断并**按日期存 localStorage**；HTTP 4xx/5xx 仍要连续 2 批
   —— 否则一次抖动就把能连通的用户掐到 Agnes（用户定版：Agnes 是限量兜底，不是批量主力）。
   超时 8s→3.5s（`GTX_ABORT_MS` 提成常量，判据才读得到真实值）。
3. **`rss-data-N.js` 的 404 是设计出来的孤儿**：加载器写成"成功就 idx+1，失败才收口"，
   块之间没有终点 ⇒ 每个访客发一次注定 404 的请求，而且 toast 挂在错误分支上。
   现在 chunk0 的 payload 里带 `_total`（**写进 JSON，不追加语句** —— `test_chunk_budget._payload()`
   按"整文件=一个 JSON"解析），加载器按声明收口；**读不到 `_total`（用户还是旧 chunk0 缓存）
   必须退回探测式**，否则老缓存用户被砍成只剩首屏，那正是 09-30 "只有 61 个源"的形状。
4. **preload 与 `cache:'no-cache'` 不能同时存在**：热榜消费方写死 `fetch('hot_snapshot.json',{cache:'no-cache'})`
   ⇒ 预载那份**永远不会被复用**（且 preload 带 `crossorigin`、fetch 不带 credentials，键也对不上）。
   删预载、留 no-cache（那是数据新鲜度）。封面图补 `onerror="this.remove()"`，露出已有的
   `.cover-fallback` 首字占位，不再留破图。

一条**新的 bug 类别**（值得单独记）：`build_rss_aggregator.py` 里的 JS 活在**非 raw** 的 Python 三引号串中，
`var _META_STUB = /...\b/i` 里的 `\b` 会被 Python 变成**退格符**，词边界整个失效 —— 源码看着完全正常。
同族雷：`split(/\r?\n/)` 会变成真换行（正则里是语法错误）、`'\n'` 会变真换行。
判据落在**产物层**：`tests/site_nav/test_artifact_js_parses.py` 取生成页的内联脚本跑 `node --check`，
并断言 `_META_STUB` 那行里有 `\b` 且没有 `chr(8)`。

### 10.20 孤儿测试目录审计：六个目录写着判据但没有任何 workflow 跑过

`grep -rl "tests/<dir>" .github/workflows/` 全量对照（10-01 实测）：

```
daily_insight        34 个 test_*.py   → update.yml（B 闸）        已接
rss_history          25                → update.yml（A2）          已接
rss_source_coverage   5                → update.yml（A2）          已接
site_nav              5                → update.yml（A2）          已接
site_nav_drift        1                → update.yml（A3 advisory） 已接
rss_translate         3                → <none>  ← 本次接进 A2
rss_composite        10                → <none>  ← 未接，见原因
rss_date              4                → <none>  ← 未接
rss_sort              1                → <none>  ← 未接
tools                 2                → <none>  ← 未接
trim_guard            2                → <none>  ← 本次接进 repo-trim.yml
```

`rss_translate` 里躺着的正是运行时翻译与翻译引擎判据 —— **翻译链的回归本来可以完全静默落地**，
而我此前一直以为"有测试挡着"。已加 `tests/rss_history/test_gate_wiring.py`：
含 `test_*.py` 的目录要么被某个 workflow 引用、要么在 `UNWIRED` 里点名并写原因（新增目录忘了接线就红）。
接线本身也做了变异验证（把 A2 里的 `tests/rss_translate/` 摘掉 → 判据当场红）。

刻意**没接**的四条，原因写进 `UNWIRED`（判据要求每条理由自立，不许写"同上"—— 我自己被这条打死过一次）：
- `rss_composite` / `rss_date` / `rss_sort`：脚本风格，文件末尾 `sys.exit(0)`，被 pytest 当模块导入即
  `INTERNALERROR`（实测 `pytest tests/rss_date` 就是这个），要接得先改造成 test 函数；
- `tools`：判据对应的是本地推送工具（CI 不调用 `data_api_push`），本机 182s，不值得每场跑；
- `trim_guard` 没进 A2 而是进 `repo-trim.yml`：它那条排练判据会在合成仓里**真跑 `git-filter-repo`**，
  ubuntu 行为未验证 —— 放进每场构建的 blocking 闸，就是我上次"自己把整场冻掉"的形状。
  该步自带 `pip install pytest pyyaml`（这个 job 没有 setup-python，缺依赖会假红）。

两处"断链"的处置都**不是**我单方面补链：
- `docs/insight-pipeline-flow.md` 被 `2026-09-22-nightly-deep-insight-design.md:111` 引用为
  "已知挂起：里面误画的 Trending 输入节点，**用户明示"不要动"**" ⇒ 处置是**内容一字不改、仅入库补链**
  （远端 sha 2cf6e620a1 = 本地字节，`git diff` 为空）。"不要动"约束的是那张图画错了也不许我改，
  不是禁止它进仓库；那处误画的 Trending 输入节点已于 10:01 09:5x 经用户确认"本来就是画错"后删除
  （见 §10.23 与 `23bbb017bb`）。
- `tools/rss_coverage_prepush_check.py` **故意不入库**：它硬编码 `BASE = "bcc385c~1"`，而那个提交
  已被历史重写销毁（`git cat-file -t bcc385c` → Not a valid object），推上去就是一个永远只能报错的
  死工具，正是这次目标要清的"空转"。引用它的 `2026-09-20-rss-coverage-fix-pending-push.md` 是历史计划，不动。

### 10.24 【已更正】"闸内 7 个地雷"是我的误判：`__main__` 守卫里的 exit 是无害的

排查 09:00 那场 A2 的 INTERNALERROR 时，我用 AST 扫了一遍"被 pytest 当模块导入就会执行到的 exit"，
写下"全仓 25 个文件是这种形状，其中 7 个已在 blocking 闸的收集范围内"。**这个结论错了**：
扫描没排除 `if __name__ == "__main__": sys.exit(...)`，而那是标准写法 —— pytest 导入时**不执行**守卫体。
反例正是 `tests/rss_history/test_build_determinism.py`：它是正常的函数式判据，exit 只在直接运行时走。

排除该守卫后重扫（`.deploy-tmp/_rescan_real_landmines.py`，10-01 03:2x 实测）：

```
tests/rss_history        真地雷 0 个       tests/rss_source_coverage  真地雷 0 个
tests/site_nav           真地雷 0 个       tests/site_nav_drift       真地雷 0 个
tests/daily_insight      真地雷 0 个       tests/rss_translate        真地雷 2 个
                                                    ↑ test_translate_cache.py:64 / test_translate_engines.py:190
```

而 `rss_translate` 那 2 个**不在收集范围内** —— A2 对它是按文件点名的（§10.22 的教训）。
真实结论：**当前闸内没有"一红就冻部署"的地雷**；唯一真实存在过的就是 09:00 炸掉的
`test_translate_engines.py`，而它已经在闸外。

教训写死在这里：**扫描器的分类学错误会直接变成我的结论**。判据报"7 个"我就照着报，
没有先问"它们今天为什么没炸"——我给的解释（"因为正在通过"）其实是编出来圆场的，
真实原因简单得多：那种写法根本不在导入时执行。

判据本身保留、而且更严：`test_wired_paths_are_pytest_collectible` 对所有被 A2 点名的路径做
AST 检查（排除 `__main__` 守卫），名单外一律判红；`KNOWN_FRAGILE` 改成**空集**（不是删判据），
并保留"赖着不划掉也判红"的反向检查。变异验证：把 A2 改回接整个 `tests/rss_translate/`
⇒ 这条当场红（`.deploy-tmp/_mut_a2_dir_check.py`）。

留一条真实待办（无部署风险）：把 `tests/rss_translate/` 那两个脚本风格文件改成函数式判据，
之后 A2 可按目录收集，不必逐个点名。

### 10.28 多 key 退避 + 删死端点 + 线上复核实测（10-01 11:00 场之后）

**① Agnes 多 key 429 退避**（`_agnes_translate`）：轮完一整圈（`_AGNES_429_STREAK >= len(keys)`）
仍全 429 才记一次罚期，罚期内**函数入口自己返回 None**（旧写法只有调用方
`_translate_to_zh:2099` 记得查闸，函数照发请求）。任一 key 成功即清零连击。
判据 `tests/rss_translate/test_agnes_429_backoff.py` 4 条（含"单次 429 必须继续试下一个 key"、
"成功清零"、"全程不许 sleep"三条反向/方向护栏）；四路变异全杀
（`.deploy-tmp/_mut_429.py`）。**M4 第一次存活**：我"成功清零"那条只喂了 2 次 429，
3 个 key 时不清零也够不到阈值 ⇒ 补成"429/成功 交替 3 轮"才杀掉。
用户关心的"会不会拉长构建"：不会 —— 罚期是**少发请求**，代码里没有任何 sleep（判据专门钉了这点）。

**③ 死端点 `/api/build_log` 已删**：`api/build_log.js` 文件 + `vercel.json` 里的那条声明。
删之前先确认引用面：全仓只有 `vercel.json:12` 一处（其余命中是自动生成的 repowiki 元数据），
前端零调用。判据 `tests/site_nav/test_dead_api_routes.py` 钉三条：死路由登记（**禁止复活**，
删完清空名单就等于自我注销）、vercel.json 声明必须都有对应文件、页面引用的 `/api/*` 必须存在。
第二条 regex 第一版把 `https://aihot…/api/v1` 这类**外部** API 也算成本站引用，收紧为
"引号/反引号/左括号后紧跟 `/api/`"才对。

**线上复核（`36808494591`，head=`b2e84f`，11:00 场 completed/success 之后的真页面）**：

| 指标 | 改动前 | 现在（实测） |
|---|---|---|
| 控制台 error | 16 条必败 + `rss-data-10.js` 404 + preload 告警 | **0 条** |
| 一次访问的服务端翻译请求 | 12 秒内 8 次且仍在续跑（全库遍历 ≈41 分钟） | **14 次后停止**：最后一次在 t=28.0s，采样时 t=184.7s ⇒ 之后 **156 秒零请求** |
| 切排序（diverse→oldest）后 | 新首屏排在旧队列后面 | +3 次请求即收口（14→17，之后静默 30s），**新首屏 80/80 标题中文、摘要 70/70 中文**（切前是 85/102） |
| 浏览器直连 googleapis | 16 次全败 | **0 次**（当日熔断已跨访问记住） |

首屏 120 张卡标题 **120/120 含中文**（`_total=10`、6 个 chunk 正常合并）。

两条"防以后"的判据（10-01 03:4x 补，都不改行为，只钉住边界）：
- `test_request_volume_is_bounded_by_the_window`：一次访问发出的**去重文本数 ≤ 窗口 + 30**。
  这条钉的是本次改动的目的本身（旧写法无界）。变异 B（`WALL_SUMMARY_LIMIT=9999`）杀掉它。
- `test_browser_gtx_concurrency_stays_capped`：浏览器直连**峰值并发 ≤3**。
  窗口化后一次要发上百条，如果以后有人把 worker 数调大，这就是把"减负"变成"打爆 Google 端点"的入口。
  变异 A（`Math.min(3,...)` → 12）杀掉它。

顺带纠一个我自己先扣的帽子：我一度认为"一次调用把 150 条文本丢进 `_browserGtx`"是突发回归，
读码后撤回 —— 并发一直是 `Math.min(3, uncached.length)`（`build_rss_aggregator.py:5362`），
改动前后峰值并发相同，变的只是**总量从全库变成 ≤150**。为不存在的问题加分片逻辑，
只会带来新的复杂度和新的风险。

**②"改 7 个脚本风格文件"取消** —— 那是 §10.24 里我的误判，实际闸内 0 个，没有可改的东西。


### 10.25 运行时翻译队列的真实负担（减负设计的量化依据）

产物侧统计（`.deploy-tmp/_runtime_load.txt`，按 CJK/拉丁字母占比判"还需不需要翻"）：

```
rss-data-0.js   条目   360  title_zh 全覆盖  标题仍需翻  16 ( 4.4%)  摘要需翻 133 (36.9%)
rss-data-1.js   条目 15103  title_zh 全覆盖  标题仍需翻 750 ( 5.0%)  摘要需翻 4471 (29.6%)
rss-data-2.js   条目 10303  title_zh 全覆盖  标题仍需翻 644 ( 6.3%)  摘要需翻 3888 (37.7%)
合计            条目 25766                   标题仍需翻 1410 (5.5%)  摘要需翻 8492 (33.0%)
```

**构建期预翻没有被取消，也不该取消**：08:33 那场 `trans_cache_hit=8542`，真实外呼只有
`agnes 33 + google 10 + mymemory 1 = 44`，另有 `trans_skip=7714`（中文直接跳过）。

负担全在运行期的**队列形状**：`_translateWallItems` 遍历整条 `ART`（2.5 万条）而不是渲染窗口
（`visibleArts()[0..wallLimit]`，首屏 120 / 滚动 +80），每批 10 条、批间 2.5s
⇒ 走完 9902 条待翻文本要 ≈ **41 分钟不间断请求**；而 GTX 在大陆不可达时整批转 `/api/translate`
——**等于每个访客都在替全库消耗服务端翻译配额**。

按已批准的 ①窗口优先队列 ②摘要只翻窗口前 30 ③切排序打断在飞批次 ④不动构建期，
一次首屏降到 **≈6 条标题 + ≤30 条摘要 ≈ 36 个文本**，总量随浏览增长而非随全库增长。

### 10.26 运行时翻译队列改为"渲染窗口"排队（10-01 09:3x 用户批准并实施）

按 §10.25 的读数，用户定版四条口径，全部落在 `build_rss_aggregator.py` 的运行时 JS 里：

- **① 队列范围**：`_wallWindow()` = `visibleArts().slice(0, wallLimit)`，不再遍历整条 `ART`。
  窗口外不入队；滚动扩窗由 `renderWall → _scheduleWallTranslate` 重新武装 ⇒ "滚到才翻"。
- **② 摘要上限**：`WALL_SUMMARY_LIMIT = 30`，只翻窗口前 30 条的摘要（标题先全部排队、摘要殿后）。
  摘要才是长文本的大头；标题侧构建期已覆盖 100% `title_zh`。
- **③ 切排序/筛选打断在飞批次**：`_wallGen` 代数 + `_wallCtrls` 控制器表；窗口指纹变化时
  `_abortWallInflight()` 并换代，**旧批次回来的结果一律丢弃**（`_applyWallTr` 首行校验代数），
  否则会把上一个窗口的译文写进用户此刻看着的条目。`_browserGtx(texts, _ctrlSink)` 新增第二个
  参数，把每个 AbortController 交出来供打断。
- **④ 构建期一行未动**：`_translate_source_items` / `api/translate.js` 不在本次范围内。

**我自己发现并修掉的设计缺陷**（值得单独记）：第一版把 `wallLimit` 与窗口长度算进了
`_wallFingerprint` ⇒ 滚动扩窗被误判成"换窗口"，每滚一次 abort 一轮在飞批次，
**快速滚动的人一条都翻不完**。指纹改成只取
`[sortMode, filter.type, filter.src, artKey(win[0])]`：扩窗是追加（不打断），
切排序/换筛选是替换（必须打断）。判据
`test_growing_the_window_does_not_abort_the_inflight_batch` 就是这条的护栏，
变异 M5（把 `wallLimit` 塞回指纹）会被它当场杀掉。

判据与验证（`tests/rss_translate/test_wall_queue_window.py`，node 真跑 6 条）：

- 窗口刻意设在 `ART` **尾部**（350..399）：只要队列还在从 `ART` 头上遍历，第一批就越界，
  一条判据当场咬住。第一版把窗口放在头部，第一批恰好落在窗口内 ⇒ 判据空转（我自己踩的）。
- 兜底 `fetch` 必须带延迟（400ms）：瞬间 resolve 时"在飞被打断"永远测不到，
  我因此把一次**判据缺陷**误读成"实现没生效"。
- `dump` 之后必须 `process.exit(0)`：队列尾部有 `setTimeout` 自我续跑，node 不退出会让这套
  判据跑到 **402 秒** —— 放进 CI 就是每场构建多拖 6 分钟。
- 五路变异全部被杀（`.deploy-tmp/_mut_wall_window.py`，MUTSET_RC=0）：
  M1 队列退回遍历 ART、M2 摘要不设上限、M3 去掉代数校验、M4 去掉打断、M5 扩窗误判成换窗。
- 完整回归：新 A2 原命令 **258 passed（36s）**；A3 漂移 1 passed；`py_compile *.py` 与
  `compileall tests` 均通过。`test_wall_queue_window.py` 也一并接进 A2（按文件粒度），
  否则它自己就成了 §10.20 里那种"写着但从不跑"的孤儿。

### 10.27 构建期同一个洞（中文/纯 URL 被送进翻译）+ 我这段改动里自己引入的两个错

探针（`.deploy-tmp/_probe_buildtime_translate_skips.py`，把 `urlopen` 换成记录器）实测
`_translate_to_zh` 旧口径 `cn_chars > len(text) * 0.3` 的分母是**整串长度**，于是：

```
中文夹符号     送出=是   ← 78 个 `+` 与 ANSI 残片把中文占比稀释到阈值以下
HN 元数据样板  送出=是   ← Article URL / Points 这种投稿样板被当正文翻
纯 URL        送出=是   ← 整串只有一个链接也发出去
正常英文       送出=是   ✓ 该翻
正常中文       送出=否   ✓ 该跳过（改动不许把它弄反）
```

新增 `_needs_translation()`：剥 ANSI/URL/CJK 后**必须还存在非中文文字**、中文不占多数、
且不是元数据样板；含假名的日文一律早返回"要翻"（既有规则）。

**真实影响要说清，别把这次改动吹成减负主力**：拿真实首屏 360 条标题逐条比对
（`.deploy-tmp/_measure_skip_delta.py`），新口径相对旧口径**只多跳过 1 条**
（`开爪 2026.9.7`，跳过是对的），仍会去翻 62 条。构建期这个洞在实际数据上几乎是**休眠**的，
真正的负担是 §10.25/§10.26 那条"浏览器遍历全库"。改它为了口径一致 + 堵住纯 URL/ANSI 垃圾，
**不是为了省配额**。

我在这段改动里自己引入、又被判据当场抓到的两个错：

1. **门槛写成"必须有拉丁词"→ 顺手砍掉韩文/西里尔**。谚文标题一个拉丁字母都没有，
   `새로운 공개 프레임워크…` 被跳过，而旧口径照翻。这条在 360 条真实首屏标题上
   **完全看不出来**（样本里没有谚文），只有反向判据兜得住（`test_korean_still_sent`、
   `test_cyrillic_still_sent`）。门槛改为"剥掉中文之后是否还有 `isalpha()` 字符"。
2. **判据依赖"环境恰好干净"**：`test_buildtime_skip_guard` 单独跑 8 绿、放进全量 A2 就红 ——
   `load_build()` 复用同一模块实例，前面 `tests/rss_history` 的用例把构建期熔断
   `_TRANS_BLOCK_UNTIL` 打开了，探针于是发不出任何请求。fixture 现在自己清零并在 teardown 还原
   （`_TRANS_BLOCK_UNTIL/_TRANS_FAIL_STREAK/_AGNES_*`）。与 §10.19"门禁测试必须自带 git 身份"
   同一类教训：**判据不许依赖上一个用例留下的状态**。

变异四路全杀（`.deploy-tmp/_mut_btskip.py`）：M1 退回旧占比口径、M2 去掉元数据样板规则、
M3 门槛改回拉丁词、M4 去掉假名早返回。**M4 第一次是存活的** —— 我那条日文样本拉丁词太多，
去掉早返回也照样会被翻；补了"汉字占多数、假名很少"的样本（`当社の新技術発表会のご案内です`）
才把它杀掉。判据不 discriminating 时，"绿"没有意义。

最终：A2 原命令（含三个翻译判据文件，按文件粒度收集）**266 passed / 34s**；
`py_compile *.py` + `compileall tests` 通过。

部署恢复实测（`36803780256`，head=`ed1f6a08`）：A2 success ⇒ A3 success ⇒ Stage Pages success
⇒ Prune success ⇒ **Deploy to Vercel success** ⇒ Upload Pages success ⇒ **Deploy to GitHub Pages success**。
站点数据停更区间为 08:19→10:2x（约 2 小时），此后接上每小时。

### 10.29 我给 repo-trim.yml 加的"判据自测"那一步，把 repo-trim 自己的排练判据弄红了

排查新孤儿时顺手跑了 `tests/trim_guard/test_repo_trim_workflow_rehearsal.py`（本地 `py -3.11`，
**单文件 4 条，红 2**），两条都是我 390fc0d 那次提交造成的：

```
FAILED test_rehearsal_runs_every_step_green
FAILED test_rehearsal_catches_unknown_filter_repo_option
```

机理不是判据太严，是我撞上了自己写的规则：**排练判据会把 workflow 里每一个 shell 步骤真跑一遍，
并断言每步 rc==0**。我在 destructive 步骤前面插了"判据自测（trim_guard…）"，它的脚本是
`pytest tests/trim_guard/`；而排练用的合成仓里**根本没有 tests/ 目录**（它只搬了
`tools/trim_commit_guard.py` 进去），于是这一步必然以
`ERROR: file or directory not found: tests/trim_guard/` 收场。第二红是连带：那条变异判据
"把 --verbose 塞回去，排练必须当场红"是**遇到第一个非零退出就断言原因**，我新加的那步排在最前面，
于是它抓到的是"我的步骤红"而不是"filter-repo 不认开关"⇒ **它不再能证明变异被抓住**（假红掩盖真盲）。

影响面：站点**零影响**（repo-trim 是 workflow_dispatch-only，且这一步在任何写操作之前，
红 = 什么都不做）。但"下次点 repo-trim 会在第一道纸面检查上失败"是我推上去的真实回归。

处置：把它加进 `SKIP_STEP_NAMES`（与 `安装 git-filter-repo` 同类——沙箱里跑不了的步骤），
并补一条反向判据 `test_skip_list_cannot_absorb_a_real_step`，钉两件事：
排除表里每一项必须仍指向真实存在的步骤（步骤改名后不许留僵尸条目），
且被排除的步骤脚本里不许出现 `filter-repo --force` / `git push` / `update-ref` / `force-with-lease`
—— 否则"每步都绿"这句话可以靠把真步骤塞进排除表来伪造（这正是我这次差点踩的形状）。
变异验证：把 `剔除死数据族…`（真会动仓的那步）塞进排除表 ⇒ 新判据当场红，`MUTATION_RC=1`。
最终 `tests/trim_guard/` **22 passed / 17.6s**。

顺带更正我自己的一条误判：我一度以为 `tests/tools/test_data_api_push_delete.py` 是"新增孤儿"，
准备把它接进 repo-trim。实际不是——`test_gate_wiring.py` 的 `UNWIRED` 里
**早就按目录登记了 `tools` 并写了原因**（"本地推送工具判据，CI 不调用 data_api_push"）。
接它进任何 workflow 会让那条登记变成假登记，而"要不要改这条策略"属于用户的决定，不属于我顺手改。
已把 repo-trim.yml 的改动**回退**（`git status` 里该文件已无 diff），这次只留排练判据那一处修复。

待用户拍板（不擅自动）：`tests/tools/` 三个文件全都被 `monkeypatch(D.req, …)` 挡住了真实外呼，
AST 亦无模块级 exit ⇒ 技术上可以按**文件**粒度接进 repo-trim（dispatch-only，冻不了线上）；
代价是 `UNWIRED["tools"]` 那条登记要同步改成"仅 atomic/branch 两条未接"。

### 10.30 窗口队列里有一个恒真标志（`_wallDirty`）——审"空转"时扫出来的

`_translateWallItems` 一轮结束后的三行是：

```js
_wallDirty = 1;
_wallTrBusy = 0;
if(_wallDirty){ _wallDirty = 0; renderWall(); }
```

`_wallDirty` 全仓只有三处引用：**写 1 的下一行就把它读掉**，中间没有任何别的写者 ⇒ 那个 `if` 恒真，
变量纯属装饰。这类东西的危害不是跑错，而是**读代码的人以为"渲染是被脏标志调度的"**，
以后改调度时按这个假象下手。已删（行为等价）：`var _wallTrBusy=0,_wallDirty=0;` → `var _wallTrBusy=0;`，
末两行 → `_wallTrBusy = 0; renderWall();`。删后本地整跑 CI 原命令 **275 passed**，`py_compile` 通过。

顺手把两件事查清楚了，都是"看着像空转但其实接通了"的那类，记下来免得下次重新怀疑：

1. **扩窗确实会触发翻译**：`_scheduleWallTranslate()` 挂在 `renderWall()` 末尾，
   而 scroll → `loadMore()` → `renderWall()` ⇒ 新露出的条目会进队，不存在"窗口逻辑写了但不跑"。
2. **timer 链不会失控**：一轮成功结束会排下 120ms（来自 renderWall）与 2000ms 两个唤醒，
   但 `_wallTrBusy` 的早返回发生在**排新 timer 之前** ⇒ 忙时那一跳不产生后代；
   候选耗尽时 `if(!cands.length) return;` 同样不排 ⇒ 队列排空后只剩一次空唤醒，不会指数增长。

另外对今天新增的 20 个符号做了引用计数（定义 + 使用 ≥2 才算活着），最低 2、最高 9，
没有第二个 `_wallDirty` 这种"写了没人读"的形状。**口径提醒**：引用计数只能证明"被读过"，
不能证明"读的地方会执行到"——恒真标志就是引用计数抓不到、靠读控制流才抓到的。

### 10.31 本地 `.git` 是 15 个 commit 的浅取副本，别在本地读全历史

想把本地 main 对齐到刚推的 `531cdc2b` 时用了 `git fetch --depth=1 origin main`，它带来两个后果，
第二个是我自己造成的：

1. 目标没达到：新提交的父 `ff425364` 依旧不在本地，`update-ref` 直接拒绝（`nonexistent object`）。
   ⇒ **本地 `git push`/对齐都指望不上**，推送后"本地与远端两条并行历史"是本仓的常态（§工具 `data_api_push.py`
   每场都自己重读远端 head，所以不受影响）。
2. 副作用：`--depth=1` 会把 `390fc0d`、`b2e84fb3` 这些**父对象明明还在本地**的提交也写进 `.git/shallow`，
   于是 `git rev-list --count refs/heads/main` 从 **14 掉到 2**，此后任何 `git log` 类审计都失真。

处置（已做完并体检）：逐条判断每个边界的父对象能否 `git cat-file -e`，只保留父真缺失的两条
（`093eec06`←父 `820cce2b` 缺失、`531cdc2b`←父 `ff425364` 缺失），其余 8 条假边界从 `.git/shallow` 移除，
动前先 `cp .git/shallow .git/shallow.bak-20261001`。恢复后 `rev-list --count main` = **14**，
`git fsck --connectivity-only` 除 dangling 提示外**无缺失对象**。

由此定下测量口径：`git cat-file --batch-all-objects | awk '$2=="commit"' | wc -l` 本地 = **15**，
而远端是重写后的 2037 条量级 ⇒ **凡"全库体积/提交数/某路径全部历史"的读数，必须在 CI 里取**
（`repo-trim.yml` 用 `fetch-depth: 0`，实测 259 秒拉完整历史；本机线路 0.2~0.34 MB/s 且不可续传）。
本地只做对象级/工作树级核对。参见 §10.20 与手册开头的体积读数，那批数字全部来自 CI。

### 10.32 10-01 12:00 场的实测读数（下一次接手时，这些就是"当前真相"）

构建与部署（run `36813103502`，head=`6c7956f`，completed/success）：
A1 语法 → **A2 blocking success**（第 4 个翻译判据文件 `test_agnes_429_backoff.py` 首次上 ubuntu）
→ A3 → B → 构建 → Commit → Stage Pages → Prune → **Deploy to Vercel success** → **Deploy to GitHub Pages success**。

端点（Vercel 域，逐个 GET 无参）：`/api/build_log` **404**（推之前是 200，这半边真落地了）；
`/api/rss` 200、`/api/news` 200、`/api/translate` 405、`/api/search` 405、`/api/article` 400、
`/api/agihunt` 400、`/api/events` 403 ⇒ 现存 8 个函数都在且都在应答。
`/api/stars` 也是 404，但那是**正确的**：`api/` 里从来没有这个文件，部署的 index/rss 两份 HTML 与
三个生成脚本里它的引用数都是 0，只有 `2026-08-15-starhub-realtime` 那份计划稿写着"Create: api/stars.js"
⇒ 历史设计稿，不是空链，不要去"补一个实现"。

运行时翻译在**真能取到数据的域名（Pages）**上的实测：渲染窗口 120 张卡，标题 CJK 覆盖 **0.992**、
残留拉丁标题 **0 条**；摘要 94 条里 CJK **0.787**，未翻的恰好是超出"窗口前 30 条"口径的尾巴
（arXiv 长摘要 + 一条 `Comments` 占位）⇒ 与 §10.26 定的范围一致。整个窗口只发 **17 个 translate POST**
（全 200），对比改造前的全库 41 分钟队列。控制台 **0 报错**，1 条 warning 是信源自带的 `http://` 封面图
触发 Mixed Content（浏览器已自动升级，`onerror="this.remove()"` 会把坏图摘掉）。

缓存轮转实测（`actions/caches`）：**11 个键 / 1.21 GiB**，`emb-cache` 5 键 ×224 MiB、`rss-history` 6 键 ×~20 MiB，
键的 created_at 跨度只有 5 小时 ⇒ 与 `--keep emb-cache=4 --keep rss-history=5` 完全吻合
（"每族保留 N + 本场那一个"），改造前是 79 键 / 9.97 GB。**轮转在生效，不是在原地好看。**

构建时长与外呼（`build_logs/2026-10-01.jsonl` 的 13 条 build 记录，北京时 00:31→12:14）：
`duration_s` 落在 **298~615s**，12:14 那场（head=`6c7956f`，带 Agnes 退避与新跳过口径）= **349.4s**，
是当天中位偏下 ⇒ **多 key 退避没有把构建拖长**（用户当时点名关心这一条）。
`trans_agnes` 在此之前 12 场为 **32~96**（中位 72.5），12:14 场 = **9**；
`trans_google` 那 12 场为 **10~581**，11:13 场 581 → 12:14 场 149；`trans_fail` 全天 **0**。
（别把降幅全记在我这两笔改动头上：11:13→12:14 之间同时换了 head，`trans_cache_hit` 也从 8224 涨到 8641，
命中率上升本身就少发外呼。）

拿真判据函数跑线上 chunk0（360 条首屏标题）做的双向核对，这是 §10.27 那句"几乎是休眠的"的第一次量化：
· 判"不需要翻译" **109/360**；其中**纯假名标题 0 条**、**含较长拉丁且无汉字 0 条** ⇒ 没有把该翻的误跳掉。
· 反向：判"要翻"却已含汉字 **18 条（5%）** —— 都是"中文句子里夹两个英文专名"这类
  （`Google DeepMind 东京再招人…`：汉字 15、拉丁字母 17，`cjk >= other_letters` 差 2 就没跳过）。
  取回来看结果：**15 条 title_zh 与原文相同或为空（纯白烧、无害），3 条被改写**，
  且改写质量不差（`Google AI Overviews 冗余翻车` → `谷歌 AI 概览冗余故障：…`）。
  ⇒ 这不是回归，也不是新造的洞，是**既有阈值的残留**；要收紧就改成"汉字数 ≥ N 且汉字占比 ≥ 阈值即视为中文"，
  收益是每天少约 5% 的外呼，代价是可能把"中文夹专名但确实想翻"的那些不再翻 ⇒ **属于口径变更，等批准**。


死函数审计（本轮新做的两条）：
· Python 侧用 AST（不是 grep）数"定义后从未被引用"：124 个 def，**0 个死**。
· 产物侧我先写了个"去注释与字符串再数标识符"的扫描器，报出 7 个死函数 —— **其中 4 个是假阳性**
  （`adjColor`/`loadQRLib`/`stripHtmlForCanvas`/`wrapText` 都有真实调用点；状态机会被正则里的
  引号带偏，把真代码当字符串吞掉）。逐个 grep 复核后确认的死函数是 3 个：
  **`_dedup`、`_fmtRelTime`、`_normSignals`** —— 产物里各自只有定义那一次（`_dedup` 要按词边界数，
  否则 `_dedupSeen`/`_dedupCount` 会冒充成调用点），且 `b2e84fb3` 的词边界计数与现在同为 1
  ⇒ **既有孤儿，不是本次改动造成**；要删得单独批准（`_normSignals` 还被 repowiki 的"前端信号规范化"条目引用着）。
  结论：**这套扫描器不可信，没有把它固化成常驻判据。**

### 10.33 仓库里那两份 HTML 是冻结副本；而一条死链判据在真实调用形态上看到的是"空集"

这轮的两条都不是"改动引入的 bug"，而是**判据自身在骗人**，靠"不信自己的读数"才抓出来。

**① git 里的 `rss-aggregator.html` 是滞后的旧运行时。**
实测：线上 Pages 那份含 `_wallWindow`/`WALL_SUMMARY_LIMIT`/`GTX_ABORT_MS`/`_browserGtx`（各 2 处），
**仓库那份这 4 个符号全 0**，却仍有 `_wallDirty` 3 处（⇒ 它停在窗口队列改造之前）。
根因不在 batch①：CI 的提交清单是 `git add rss-data-0.js known_categories.json descriptions_zh.json
trending_snapshot.json translations.json rss_sources.json hot_snapshot.json …`，**从来不含这几个 HTML**。
部署用的是当场生成的新 HTML，所以**页面行为没问题**（我 12:0x 的线上实测有效）；
有问题的是"谁去读仓库副本，谁就读到旧运行时"（raw.githubusercontent / jsDelivr 的 gh 通道都会读到它）。

**② 更要紧：`tests/site_nav/test_dead_api_routes.py` 把那份滞后副本当地面真值。**
它原先硬编码 5 个页面文件名读磁盘。滞后文件里没有新引用 ⇒ 判据看的是旧世界。
已改为：`rss-aggregator.html` 用**生成端现跑**的产物（同 §10.30 那两条 `build_html([], …)` 口径），
其余页面按 `ROOT/*.html` **动态**收集（新增入口不会被名单漏掉）。
变异验证：只在生成端注入 `fetch('/api/ghost_probe')` ⇒ 判据当场红（MUTATION_RC=1）。
旧版抓不到有**两层**原因，都得记下来：一是它读的是滞后的仓库 HTML 副本（里面根本没有新代码），
二是它直接 `open(build_rss_aggregator.py)` 读**未经变异**的真源文件 —— 变异体是按 `RSS_BUILD_SRC`
放在副本目录里的。新版走 `load_build()`，认这个环境变量，所以变异才能抵达判据
（本仓产物级判据通用的约定：变异体指向副本目录，靠 `RSS_BUILD_SRC` / `STARHUB_UPDATE_YML` /
`STARHUB_TOOLS_DIR` 这类覆盖变量生效，绝不改工作树 —— 见 `tests/tools/test_data_api_push_delete.py` 开头那段）。

**③ 顺手抓到一条恒绿判据。**
旧正则 `['"`(]/api/…` 只认**同源**写法，而站点真调用全是绝对域名
（`var _API_BASE='https://starhub-refresh.vercel.app/api/rss'`、`fetch('…vercel.app/api/translate')`）
⇒ `_api_refs_in_pages()` 实测返回 **空集**，也就是"永不红"。
触发这次怀疑的是**"3 个测试 0.12s 跑完快得不合理"**，不是它红了。
口径改为"同源写法 或 自有域名写法"（外部 API 如 `aihot.example/api/v1/…` 仍不收，
否则会红在一堆与本题无关的路径上——这是我第一版犯过的）。改后它看到 **8 个** `/api/` 名字，
正好等于 `api/` 里的 8 个文件 ⇒ 1:1，既无悬空声明、也无缺失函数。

**④ 补了反方向的守卫**：`test_no_api_function_without_a_caller` —— `api/` 里每个函数都必须有调用方，
`ALLOWED_UNCALLED` 默认空集。理由就是 `/api/build_log.js`：文件、`vercel.json` 声明、部署产物三处都在，
全仓零调用方，**只有拿 curl 逐个打才会发现**（本轮就是这么撞见的）。
变异：把 `API_DIR` 指向临时副本并多塞 `orphan_probe.js` ⇒ 红。
注意**没有**在真 `api/` 下造文件——当时有构建在跑，真文件会被 Vercel 打包成一条真路由。

**⑤ 我自己的一条错读，记下来防再犯**：第一次查远端产物得到"`_wallDirty` = 0"，是假的：
`contents` API 对 >1 MB 的文件**不返回 `.content`**，`base64 -d` 解了个空串。
用 `Accept: application/vnd.github.raw` 重取（3,197,518 B）后真实值是 **3**。
凡是"读远端大文件"的核对，先打印**解码字节数**再判断言。

**存储侧当时的实测**（与 §10.32 相互印证）：远端 `.size` = 2,554,003 KiB = **2.44 GiB**（此前 2.43 ⇒ 持平）；
`trees/main?recursive=1` 未截断、440 条，**最大跟踪 blob 是 `hot_history.json` 7.9 MiB**；
`rss-data-1.js` / `rss-data-2.js` / `rss_history.json` 已不在 main 树里（contents 404）。

**待用户拍板（我没动）**：要不要用 `tools/data_api_push.py --delete` 把仓库里这两份冻结 HTML 删掉。
留着：任何人读仓库都会拿到旧运行时（今天已经骗过一次判据）；删了：raw/jsDelivr 上那条路径直接 404，
不再有"看着像站点、其实是旧代码"的入口。部署侧不受影响（Pages/Vercel 用的都是当场生成的产物）。

**⑥ 顺着 ① 往下查，发现 batch① 其实只做了一半（这条重要）。**
`tests/rss_history/test_pages_deploy_wiring.py::test_no_page_html_is_committed` 明令
4 个页面 HTML 不许再进任何 `git add`（当时它们在 update.yml 里占约 3.8 MB/场）。
提交清单确实不含它们了 —— 但 `trees/main?recursive=1` 实测**跟踪副本仍在树里**：

```
rss-aggregator.html          3.05 MiB
daily-insight-history.html   0.33 MiB
index.html                   0.27 MiB
ai-daily.html                0.08 MiB      合计 3.73 MiB（template.html 是源码，不算）
```

⇒ 历史不再增长（这点达标），但"退出 git"没做完；而那条守卫**只看 update.yml 的文本、看不见树**，
所以它一直绿。这就是"用 proxy signal 当完成"的教科书样子。

**⑦ 没做完的那一半把 A3 变成了定时炸弹。**
`tests/site_nav_drift/test_artifact_drift.py::test_index_header_matches_template`
读的是**库里那份 index.html**，断言它与 `template.html` 的 `<header>` 恒等。
它今天绿（我另取实测：库内 280,193 B / md5 8527448558，线上 282,697 B / md5 c1e34b1acc，
两份本来就不同 —— 绿的只是 header 那一块）。
问题在于产物已经不再入库 ⇒ 这个等式只能在"冻结快照"上成立：
谁下一次改 `template.html` 的 header，A3 就当场红，而且**没有任何正当修法**
（要么手改产物再入库 = 违反 batch① 并把 3.8 MB/场 请回来，要么改判据）。
A3 是 `continue-on-error` ⇒ 不会冻部署，但会留下一条永久噪声 + 一个诱导别人走回头路的陷阱。

**建议的收口顺序（要批准才动）**：
1. 先给 `test_no_page_html_is_committed` 补一条**看树**的判据（`git ls-files '*.html'` 减去白名单 `template.html`），
   让"有没有真退出"这件事变成可证的 —— 这条现在就该红，是好事。
2. 再处理 A3：把漂移检查的地面真值从"冻结副本"改成生成端现产物，或直接撤掉这一步
   （结构配平已由 A2 的 `test_header_structure.py` 在 `template.html` 上钉住，撤销不丢防线）。
3. 最后用 `--delete` 删掉这 4 个跟踪副本（工具已具备删除与"远端 404 复查"两半）。
顺序不能反：先删文件会让第 2 步的判据变成"文件不存在"的错误，而不是可读的红。

### 10.34 已备好但**未推**的收口改动：A3 换成"看树的再入库守卫"（本地四向验通）

`tests/site_nav_drift/test_artifact_drift.py` 已整文件重写（工作树里改好、**没有推送**）：
旧的 `test_index_header_matches_template`（模板 vs 冻结快照的恒等式）删掉，换成
`test_no_generated_page_html_is_tracked` —— 用 `git ls-files` **看树**，点名根目录那 4 个纯产物页面。
留在 A3（`continue-on-error`）而**不进 A2**：文件回来只是历史体积变大，不是站点坏掉；
为 3 MiB 的滞留去冻一次部署，正是本仓 10-01 实测过两小时代价的那种错。

**为什么不单独推**：现在推上去 A3 会当场红（4 个文件确实还在树里），而产物不删它就永远红
⇒ 变成一条永久噪声。所以必须与 `--delete` **同一个提交**落地，那场构建里它就自然绿。

预演把自己的两个缺陷抓出来了（这就是预演的价值，不是走过场）：
1. 守卫第一版按"所有 `.html` 不在白名单"判 ⇒ 误把 `docs/x.html`、`lib/y.html` 报成违规。
   已改成**只按根目录那 4 个文件名精确匹配**（`template.html` 是源码，必须留下）。
2. 我用 `mv` 模拟删除态跑 A2，`tests/rss_history/test_history_bounds.py:203` 抛
   `FileNotFoundError: ai-daily.html` —— 它遍历 `git ls-files` 之后逐个 `open`，
   对"**仍被跟踪但工作树缺失**"这种状态没有抵抗力。CI 的干净检出不存在该状态（跟踪=在场），
   所以**不是 CI 风险**；但真删之后本地会撞上 ⇒ 收口时必须同步 `git rm --cached` 那 4 条，
   让本地索引与远端一致（别顺手 `git rm` 掉文件本身：本地 HEAD 比远端旧，索引操作要单独做）。

四向验（全部实测，不是推理）：

```
真实清单(仍跟踪4个)   -> RED   点名 4 个文件
删除后清单            -> GREEN
含 docs/ 与子目录 html -> GREEN  （不误报非根目录、非那 4 个的名字）
拿不到清单            -> RED    拒绝"静默跳过 = 绿但什么都没查"
```

复跑 CI 原命令 **277 passed**（工作树已复原，4 个文件放回，`git status` 对 `*.html` 无 D 记录）。
待批准后的一次性推送。**推送状态分两段记清，别让人猜**：

已在远端（零功能风险，手册本身不被执行；登记串只改字典值，`test_unwired_entries_are_explained`
要求长度 ≥12 已核，本地 A2 原命令 277 passed）：
- 本手册 §10.32–§10.35
- `tests/rss_history/test_gate_wiring.py` —— `UNWIRED["tools"]` 的数字按实测改成 30 条 / 128.7s

**仍在本地、等你批准才动（必须同一提交，缺一就留谎或留永久红）**：
1. `--delete index.html --delete rss-aggregator.html --delete ai-daily.html --delete daily-insight-history.html`
2. `tests/site_nav_drift/test_artifact_drift.py` —— 看树的再入库守卫（四向已验）
3. `.github/workflows/update.yml` —— A3 步骤名 `artifact drift vs template` → `generated pages must stay out of git`，
   注释同步改写。不改这段，workflow 里就会留着"index.html 每场由 template 重写、漂移下一场自愈"这种**已经不存在**的语义。
   改名安全：全仓没有任何判据按 A3 步骤名匹配（`grep "Quality gate A3" tests/ tools/ *.py` = 0 命中），
   而 `_a2_cmd()` 只认 `Quality gate A2` 前缀，A2 那行未动。

校验现状：改完 update.yml 后 `yaml.safe_load` 仍是 28 步、A2 原命令 **277 passed**、
`tests/site_nav_drift/` **如实际红 1 条**（4 个文件仍在树里）—— 这正是第 1 项必须与第 2、3 项同一提交落地的原因。
落地后复查：`trees/main?recursive=1` 里这 4 个路径 404、下一场 A3 转绿、
`git ls-files '*.html'` 只剩 `template.html`（本地索引也要 `git rm --cached` 那 4 条，见上文）。

**落地记录（10-01 05:5xZ，用户批准 ①）**：`--delete` 那 4 个路径 + 本手册 +
`tests/site_nav_drift/test_artifact_drift.py` + `update.yml` 的 A3 名与注释，同一提交推上；
本地随后 `git rm --cached` 并删工作树副本，使 `git ls-files`/动态 glob 与远端一致。

> 实际状态更新（10-01 06:2xZ）：这条删除被权限层拦下，要求用户对"执行删除"本身给一次明确确认，
> **未绕过、未重试**。下面是被拦之前跑完的预排，批准后可直接执行，不必重新调查。

**预排结论：删这 4 个跟踪副本对上线是安全的，三条都是现取的证据**

1. `Stage Pages site`（update.yml:333-347）先按 `git ls-files` 拷，再**按名字从工作目录覆盖**这 4 个
   HTML，注释就写着"不信 git 里那份 / 它们已停止提交，main 上的副本是过期产物"
   ⇒ 发布用的是当场生成的新鲜副本，与"是否被跟踪"无关。
2. 同一步 349-354 行有 6 条 `test -s _pages/<文件>` 硬断言（含这 4 个 HTML + chunk0/1）
   ⇒ "生成器没跑出东西"会硬失败，不会把空站点发上线；这一步本身 `continue-on-error`，
   失败也只是 Pages 这场不发，Vercel 照常。
3. 全仓扫"断言这 4 个文件存在于磁盘/git"的位置：命中 3 处，**都在根级 `test_daily_insight.py`（advisory 的 B 闸）**，
   且都不依赖库里的副本：`daily-insight-history.html` 由测试自己调 `B._build_history_html()` 现生成（:194-196），
   `ai-daily.html` 不在磁盘时它**自造最小夹具并在断言后删掉**（:203-221，注释明确"宁可现造夹具，也不许静默空转"）。
   A2/A3 没有任何判据依赖它们存在 ⇒ 删除不会让 blocking 闸红。

**顺带一条体量实测（不是本轮改动造成，供你决定是否收紧）**：远端树未截断、383 个跟踪文件、
工作树内容合计 **72.99 MiB**，其中 `build_logs/` 一家就 **42.52 MiB = 58%**
（`build_logger.cleanup(14)` 保 14 天，实测 15 个 `.jsonl`，单日 2.6~2.8 MiB）；
其次是根目录 23.44 MiB（最大单项 `hot_history.json` 7.91 MiB）。
跨场状态族已确认全部不在树里：`rss_history.json` / `rss_cache.json` / `rss_api_snapshot.json` /
`rss-data-1.js` / `daily_insight_faiss.index` / `daily_insight_vectors.npy` / `emb_cache.json` 均 absent，
只有 `rss_trend_history.json` 还跟踪着（1.12 MiB）。另：`.qoder/` 有 91 个文件 2.27 MiB 被跟踪，
是工具生成的 wiki，改一次就多一份历史 —— 要不要一并出仓由你定，我没动。

### 10.37 两边翻译判据**并不"同规则"**：14 条语料实测分叉 5 条（假名/谚文/西里尔/阿拉伯）

起因是一句注释自己露的矛盾：构建期 Python `_needs_translation` 的 docstring 写着
"与运行时 JS 的 `_needsTranslation` 同规则"，可它紧接着又写
"门槛刻意不是'有没有拉丁词'：谚文/西里尔/阿拉伯文一个拉丁字母都没有，用拉丁词做门槛会把它们
一起跳过（我第一版就是这样，被 `test_korean_still_sent` 当场打死）"。
而运行时 JS 的门槛恰恰就是 `_LAT_WORD`（拉丁词）。于是把两边拉到同一批语料上实测
（`.deploy-tmp/_probe_parity_needs_translation.py`，JS **从生成的产物里取**，避开"源码对、产物被吃转义"的老坑）：

```
语料              PY    JS     判定
纯中文             skip  skip   ok
中英混(专名多)       send  send   ok
英文              send  send   ok
纯假名             send  skip   DIVERGE
假名夹汉字          send  skip   DIVERGE
纯谚文             send  skip   DIVERGE
西里尔             send  skip   DIVERGE
阿拉伯             send  skip   DIVERGE
纯URL/ANSI垃圾/HN样板/空/纯数字标点  skip skip ok
```
（14 条里分叉 **5** 条，全部是"非拉丁文字"这一类；"日文汉字夹假名短"两边都 skip，属中文占多数的正确判定。）

**责任归属先说清**：这段 JS 与 `b2e84fb3` 逐字相同 ⇒ **不是我这两跳改出来的**；
是**我把"同规则"写进 Python docstring 时没去核对 JS** —— 注释里一句未经证实的断言，
本手册第 N 次栽在同一类事上。

**影响面按路径拆，别夸大成"全站不翻"**：
· 标题多数在构建期已被 Python 判走并翻好 ⇒ 运行时这次跳过通常看不出来；
· **摘要是运行时专属**（09-16 起移出构建期，见 `_transDiag` 注释）⇒
  **日文/韩文/俄文/阿拉伯文的摘要在浏览器里永远不翻**，这是真实可感的缺口；
· 实时链路（`?source=` 与 `/api/rss` 合并进来的新条目）同样走运行时 ⇒ 这些非拉丁新条目也不翻。

**三个选项（未实施，等点单）**：
1. **改 JS 向 Python 对齐**（推荐）：含假名一律翻；字母门槛从 `_LAT_WORD` 换成
   `clean.match(/\\p{L}/gu)`（`clean` 已剥掉 CJK，所以它等价于 Python 的 `c.isalpha()`）。
   同时把这 14 条语料做成 A2 常驻**双向 parity 判据**（两边 verdict 逐条相等），
   让"同规则"这句话从此由机器证明而不是由注释声称。代价：非拉丁文本会真的开始发请求（正是该翻的那些）。
2. 反向把 Python 也收窄成拉丁门槛：更省，但等于宣布韩/俄/阿/日永不翻，与既有 `test_korean_still_sent` 的意图冲突。
3. 只把 docstring 那句"同规则"改成实话：零行为变化，缺口留着。

**为什么不能只加判据不改代码**：parity 判据装上就是红的（5 条分叉），
而它要在 `tests/rss_translate/` 里按文件被 A2 点名 ⇒ **红一场就冻结部署**（§10.24 实测冻两小时）。
所以必须"改 JS + 加判据"同一提交落地：先本地跑到绿，再推。

### 10.38 选项 1 已在本地做完并验通（**未推**）：同规则判据常驻 + 代价实测 +0/300

按"注释不该继续空头支票"的方向，本地实现并验证了 §10.37 的选项 1，**一个字节都没推**：

- JS 侧改动：`_LAT_WORD`/`_LAT_CH`（拉丁词门槛）整体换成剥 CJK 后的 `\\p{L}` 字母门槛，
  并补上"含假名一律翻"。**两个旧符号在全仓出现次数已归 0** —— 不留"定义了没人用"的尾巴，
  新常量 `_CJK_R/_KANA_R/_LETTER_R` 各自 ≥2 次引用（声明 + 使用）。
- 常驻判据：`tests/rss_translate/test_buildtime_skip_guard.py::test_runtime_and_buildtime_predicates_agree`
  —— 14 条语料两边逐条比 verdict；JS 从**生成的产物**里切（不是 .py 源码，避开吃转义的老坑）；
  带三条反向防空跑：该送的类不许少送、垃圾类不许被送、非拉丁类不许被跳过。
- 实测结果：**分叉 0/14**（改前 5/14）。
- 变异验证两个方向都杀得掉，且红因都是"分叉"这句：
  `M2_js_drop_kana RC=1`（纯假名/假名夹汉字 PY=True JS=False）、
  `M3_py_drop_kana RC=1`（同两条 PY=False JS=True）⇒ 判据是真双向，不是单向贴标签。
- **代价实测（用线上 chunk0 的真数据，360 标题 + 300 摘要）**：
  标题要翻数 176 → 176（**+0**），摘要 90 → 91（**+1 条 / +0.3%**）。
  ⇒ 这不是"加负担"的改动：之前担心它会多翻一批，数据说几乎不多。
- 整跑 CI 原命令 **278 passed**（原 277 + 新判据 1 条）。

**过程里我自己撞的一次（值得记，因为它本来会冻部署）**：
第一次整跑 **16 条红**。原因不是逻辑错，而是
`tests/rss_translate/test_runtime_translate_guards.py` 与 `test_wall_queue_window.py`
用 `START = "var _LAT_WORD = "` 当**切片锚点**去产物里取 JS ——
我改了符号名，锚点就断了，判据集体崩在"找不到锚点"。已把两个文件的锚点改成 `var _CJK_R = `。
教训：**用字面量锚点耦合符号名，等于把"改名"变成跨文件破坏性操作**。
所以新判据自己带了一句可诊断的断言消息
（"产物里找不到 %r（运行时判据被改名或删掉，同规则判据失去对象）"），
下次再断会直接说是哪一段没了，而不是抛 16 条莫名其妙的红。
更彻底的做法（锚点改用函数名 + 显式带上依赖声明）留作后续，本轮不扩大改动面。

推送注意：这条必须**自己一个提交**（或与 §10.34 那批合并），且不能在构建进行中推。
待推文件：`build_rss_aggregator.py`、`tests/rss_translate/test_buildtime_skip_guard.py`、
`tests/rss_translate/test_runtime_translate_guards.py`、`tests/rss_translate/test_wall_queue_window.py`（后两个只是改锚点）。

**§10.34 那批删除的预检已经做完（四条，全部非破坏式取证）**：
1. Pages 发布不受影响：`Stage Pages site` 在 `git ls-files` 之后**按名字从工作目录覆盖**这 4 个 HTML
   （update.yml:343-347，注释原话"不信 git 里那份"），且 349-354 行有 `test -s _pages/<文件>` 硬断言。
2. blocking 闸不依赖它们存在：全仓扫"断言文件存在"的位置只有 3 处，都在根级 `test_daily_insight.py`（advisory 的 B 闸），
   且它自己生成正文（`B._build_history_html()`）或缺失时自造夹具；A2/A3 无一处依赖。
3. `test_history_bounds.py:203` 的脆弱点是"**跟踪但工作树缺失**"这个只可能出现在本地的状态；
   真删之后跟踪与在场同时消失 ⇒ CI 干净检出不受影响（本地要同步 `git rm --cached` 对齐）。
4. 判据覆盖不缩水（本次内存内模拟，未动索引/文件）：把输入面换成"template.html + 现生成 rss 页 + 三个生成脚本"
   后，引用到的 `/api/` 名字仍是那 **8 个**（agihunt/article/events/news/refresh/rss/search/translate），
   与删除前**逐字相同、无损失**（`api/` 8 个文件、1:1 那条判据照样成立）。
⇒ 结论：批准后即可一次原子推送，不需要再补调查。
、
`tests/rss_translate/test_runtime_translate_guards.py`、`tests/rss_translate/test_wall_queue_window.py`（后两个只是改锚点）。

### 10.39 Agnes 多 key 退避在**真实限流日**的生产读数（这条终于不用靠单测）

14:00 场（run `36822533044`，head `6c0ec5f19b`）正好赶上 Agnes 被限流，job 日志里原文是：

```
[翻译] Agnes 429，轮转到 key[0]   ×3      key[1] ×6      key[2] ×4      key[3] ×2   （共 14 次轮转）
[翻译] Agnes 3 个 key 全限流，暂停直连 5 分钟   ×2
[翻译] Agnes 4 个 key 全限流，暂停直连 5 分钟   ×1
```
⇒ 我加的那条"**轮完一整圈才记罚期**"分支确实按设计触发了（3 次罚期、每次 300s），
且罚期内不再各条文本都去撞墙。

**关键对照（回答"会不会把构建拖长"这个点名问题）**：本场 `duration_s = 285.6s`，
是当天 **15 场构建里最短的一场**（当天区间 285.6~614.6s）。
`trans_fail=0`，`trans_agnes=13 / google=76 / mymemory=18 / cache_hit=8732`。
⇒ 退避不是"多等一会儿"，而是**少撞墙所以更快**——这与单测的预测一致，但这次是生产数据。

两句自我更正，别当成惯例相信：
1. 我一度写下"日志里出现 13 处 429"——**假的**，那是信源 key `ai_at_meta_blog_429`；
   另一次我用 `unzip` 解 `actions/jobs/<id>/logs` 的返回并据"没有 Agnes 行"下结论，
   实际那个 endpoint 返回的是**明文日志**（带 UTF-8 BOM），解压失败被我误读成"没有内容"。
   ⇒ 取 CI 日志请直接 `gh api … > file` 后 `sed 's/\x1b\[[0-9;]*m//g'` 再 grep，不要按 zip 处理。
2. 我说过"进罚期不留痕（观测缺口）"——**说重了**：罚期分支本来就有 stderr 播报，
   只是不进 `_TRANS_STATS` 结构化字段。因此**没有**为它新增计数器（避免造多余改动）。

顺带一条 CI 侧读数：本场 A2 = **277 passed / 24.43s**（与本地同命令同数，说明 ubuntu 上跑的确实是同一批判据），
A3 = `1 passed`，B 闸 = `391 passed`，全日志 `no tests ran` = 0 行（没有空套件冒充成绿）。
Pages 的 `upload-pages-artifact@v5` 内部有一条 `id=pages_upload.__run_2;outcome=skipped;duration_ms=0`，
而步骤结论是 success、线上产物也已带上新代码（`_wallDirty` 归 0、`_wallWindow` 存在）
⇒ 我没有把这条内部 skipped 当成故障，但记在这里，日后 Pages 真出问题时先来回查它。

### 10.40 "负担真的减了"终于有页面自证的口径：`tried=26 / untried=4906`

14:00 场部署后，在 Pages 域直接调产物自带的诊断函数（`transDiag()`，无需 `?transdiag=1`），
它跑在**整库已加载条目**上（4932 条）：

```
at 2026-10-01T06:58:03Z   total=4932
tried=26        untried=4906          ← 只对这 26 条发过翻译请求
title_cjk=4869  title_english=63
summary_cjk=2439 summary_english=1543
```

**读法很重要，别把全库口径误读成窗口口径**：
· `tried=26` 才是这次改造的成果 —— 队列**只碰了 26 条**（首屏窗口内的标题 + 前 30 条摘要里还需要翻的那些），
  改造前这里会是 4932 量级（41 分钟全库队列）；
· `summary_english=1543` / `title_english=63` 是**全库**里没翻的存量，绝大多数根本不在窗口内，
  这是"没在首屏就不加载"的设计结果，不是缺陷；
· 与运行时实测对得上：boot 后 22 个 translate POST、切排序新增 4 个（§10.32）。

**为什么先量错了一次（写下来防再犯）**：我原本想用"卡片顺序 × chunk0 原文"直接验
"摘要只翻窗口前 30 条"这条边界，结果 `matched=0` —— 卡片的链接不是裸 `a[href]`，
我的 join 压根没成立。那串 0 是**没有数据**，不是"规则被违反"；
如果按它下结论就会写出一条假发现。改用页面自带的诊断函数才是可信口径。
另外提醒：`sCJK` 这类"含汉字"判据分不清**译文**与**原本就是中文的源**（36氪/IT之家等中文源占大头），
所以拿它算"翻译覆盖率"会系统性高估，只能当上界看。

**边界规则（前 30 条摘要）目前的证据链**：单元判据 `test_wall_queue_window.py`
（量 ≤ 窗口+30、峰值并发 ≤3，各配过变异）+ 本节的 `tried=26` 实测。
DOM 侧的直接验证在这套自动化里不可靠（导航 30s 上限、卡片无稳定 link 锚点），别再拿它当证据。

### 10.41 全文翻译那条路径审过了：是按需的、有界；但它的缓存键在原理上不健全

`_clientTranslate`（build_rss_aggregator.py:4308 起，"翻译全文/摘要"按钮用）读数与判断：

- **不是后台负担**：只在点击时发；450 字/块、每请求 ≤20 块、批间**串行**、25s `AbortController` 中止；
  `isMostlyZh` 先跳过中文；某一批失败就 `_agiBatch(bi+1)` 保留原文继续（不整篇丢）。
  ⇒ 与 §10.40 的窗口队列是两条路，不冲突、不叠加后台量。
- **一个原理性缺陷**：缓存键是 `text.substring(0,100)` —— 前 100 字相同即命中，
  所以两篇**开头相同、后文不同**的文章会拿到别人的译文（静默串台）。
- **但在真数据上没发生**：拿线上 chunk0 的 235 条"非中文、会走该缓存"文本实测，
  按 `(link, field, 前100字)` 去重后**有害碰撞 0 组**。
  我第一次数出"15 组碰撞"是**误报** —— 那 15 组其实是同一 `link`+同一字段的**重复条目**
  （chunk0 360 条里只有 336 个唯一 link，24 条重复），全文本来就一模一样，谈不上串台。
  ⇒ 教训与 §10.33/§10.34 同类：计数之前先问"这个键唯一吗"，否则会把重复行读成碰撞。
- 顺带两个读数：首屏 120 张卡的 `data-k` **120 个全唯一**（数据里的重复行没被画成两张卡）；
  标题层面有 1 组"同一标题两条"（`推出 Gemini 3.8 实时版…`）但 link 不同 ——
  那是跨源转载，卡片带来源署名，**我不把它算作缺陷**，只记为可讨论项。

要不要把缓存键改成全量文本哈希（或长度+前缀+后缀组合），属于口径变更：
收益是消掉那个"原理上不健全"的串台面，代价是每次点击都要重算键、跨条目命中率下降。
本轮**没动**，等你定。

### 10.42 最大跟踪家族的逐日体积：是平的，不是在长（附我自己两次读数错法）

用远端历史提交的 `contents/<file>?ref=<sha>` 只取 `size` 字段（不下载内容，所以与文件大小无关），
对当天最大那几个跟踪家族取样：

| 家族 | 09-29 | 09-30 | main（07:13Z 复测） |
|---|---|---|---|
| `hot_history.json` | 7.98 MiB | 7.91 / 7.96 MiB | **7.90 MiB** |
| `translations.json` | 3.18 | 3.17–3.18 | **3.16 MiB** |
| `analysis_snapshot.json` | 3.61 | 3.55–3.56 | **3.53 MiB** |
| `rss_trend_history.json` | 1.12 | 1.11 | **1.11 MiB** |
| `trending_snapshot.json` / `known_categories.json` | ≈0.01 | ≈0.01 | ≈0.01 |

⇒ 这几族**两天里持平或微降**，与 §10.35 的 tip 合计 72.99 MiB、`.size` 2.44 GiB 稳定互相印证；
真正的量在 `build_logs/`（42.52 MiB = 58%，`cleanup(14)` 保 14 天），那是**唯一还值得压的**膨胀点，
压法就是缩保留天数（14 → 3~5），不动历史、不动站点行为。

**我在这次测量里犯的两个错法，写下来防再犯**（都已回读纠正）：
1. 脚本里写了 `(j or {}).get("size", 0)` —— 一次 API 失败就被默认值冒充成 `hot_history=0.00 MiB`，
   差点得出"+7.98 MiB/天 在暴涨"的假结论。⇒ 数值读数不许有默认值，取不到要报错，并**单独回读那一项**
   （复测：main 7.90 MiB、14:00 那次 auto-commit 7.91 MiB ⇒ 平的）。
2. `gh api …/commits` 返回是**新→旧**，我拿 `rows[0]` 当"首日"，增量号与跨度都会错（那次算出"跨度 1 天"）。
   ⇒ 用日期显式换算并打印跨度。
该场 A 语法、**A2 blocking**、A3、B 闸均已 success。
（链路备注：15:00 场 run `36827860970` 的 head 是 `8ff5cd3b60`，那是 **14:00 场 bot 自己的
auto-commit**、父就是我推的 `6c0ec5f19b`、只含数据文件 —— 不是有人并行改仓；
看到 head 变了先查作者与父，别以为丢提交。）

### 10.43 待决清单（一眼可批；每项都给"批准后我做什么"和代价，不需要你再翻前文）

| # | 事项 | 证据位置 | 批准后动作 | 代价 / 风险 |
|---|---|---|---|---|
| ① | 4 个页面 HTML 真正退出 git（3.73 MiB）+ A3 换看树守卫 + update.yml 名与注释 | §10.33–10.34（预检四条已齐） | 一次原子推送：`--delete` ×4 + 2 个本地文件；随后复查 `trees/main` 404、下一场 A3 绿、本地 `git rm --cached` 对齐 | Pages 发布不受影响（按名从工作目录取 + `test -s` 硬断言）；不批准则 A3 那颗雷留着（下次改模板 header 即成无法修复的红） |
| ② | Vercel 域 RSS 页空壳 | §10.32 | **已定案不动**（你平时用 Pages） | 无 |
| ③ | 封面图：按域名开关 `no-referrer` / 出厂判空 / weserv 兜底 / 实时链路补抽图 | 你的 `docs/排查记录.md` §9；我在 §10.36 更正过归因 | 按你点的编号做，配判据+变异 | #2 修的是"已证实的自我伤害"（财富中文网带 Referer 即 200）；#3 引入第三方公共实例配额与隐私依赖；#4 要改 `api/rss.js` |
| ④ | 两边翻译判据同规则对齐 + 常驻 parity 判据 | §10.37–10.38：本地分叉 0/14、双向变异可杀、代价实测标题 +0 / 摘要 +1/300、整跑 278 passed | 一次推送 4 个文件（含两处只改锚点） | 非拉丁文本开始被翻（正是该翻的）；不改则日韩俄阿摘要继续永不翻 |
| ⑤ | `_clientTranslate` 缓存键由"前 100 字"改全文哈希 | §10.41：原理不健全但真样本 217 组里有害碰撞 **0** | 换键 + 配一条"同前缀不同全文不许共用缓存"的判据 | 收益是消掉理论串台面；代价是跨条目命中率下降。可不做 |
| ⑥ | `build_logs` 保留 14 天 → 3~5 天 | §10.42：42.52 MiB = 跟踪内容 58%，且家族体积两天持平 | 改 `build_logger.cleanup(N)` 的 N + 一条钉住保留天数的判据；tip 直接瘦 ~28~34 MiB | 只影响诊断可回溯天数（历史里旧文件仍在，可随时回捞）；不动站点行为 |

我的建议顺序：**④ → ① → ⑥ → ③(#2→#1) → ⑤**。④①都已本地验通，推一场就能收口；⑥最便宜的体积收益；⑤可长期挂账。

**推送分组（组内拆开就会红，2026-10-01 按 blob 清点，未推共 7 个文件）**：
- **A 组（④，4 个文件，必须同批）**：`build_rss_aggregator.py`、
  `tests/rss_translate/test_buildtime_skip_guard.py`（新增 parity 判据）、
  `tests/rss_translate/test_runtime_translate_guards.py`、`tests/rss_translate/test_wall_queue_window.py`（仅改锚点）。
  ⇒ 只推构建脚本会**当场红 A2**：那两个 harness 用 `var _CJK_R = ` 作切片锚点，旧产物里只有 `_LAT_WORD`。
  A2 是 blocking 且后续步骤无 `if:` ⇒ 红了就是构建+Vercel+Pages 全部跳过（§10.24 实测冻两小时）。
- **B 组（①，2 个文件 + 4 个 `--delete`，必须同批）**：`.github/workflows/update.yml`（A3 名与注释）、
  `tests/site_nav_drift/test_artifact_drift.py`（看树守卫）。
  ⇒ 只推守卫不删文件 = A3 永久红（advisory，不冻部署，但是长期噪声）；只删文件不推守卫 =
  `test_index_header_matches_template` 读不到文件而报"文件不存在"，也不是可读的红。
- **C 组（手册）**：`docs/…/HANDOFF.md` 可随任一组走。
- 已一致、无需再推：`tests/rss_history/test_gate_wiring.py`（登记数字已在 `6c0ec5f19b`）。

### 10.44 第二次独立线上观测（15:00 场部署后）+ 一条关于 GTX 的口径更正

15:00 场（run `36827860970`，head 是 14:00 bot 的 auto-commit `8ff5cd3b60`）Commit/Prune/
**Deploy to Vercel**/**Deploy to GitHub Pages** 全 success。对新部署产物重取一次：

```
cards=120  titleCJK=0.992  translate POST=11   文档内含 `_wallDirty`？false
transDiag: total=7739  tried=35  untried=7704
           title_cjk=7617 / title_english=122   summary_cjk=2842 / summary_english=3340
控制台：1 条，且是 transDiag 自己的 log —— 0 error、0 warning
```
⇒ 与 06:58 那次（total 4932 / tried 26 / POST 22）构成两个独立观测点：**载入的库更大（7739）而发出去的翻译仍只碰 35 条**，
窗口队列的量不随库增长，`_wallDirty` 确实从线上产物消失了。

**该更正的一句**：`transDiag` 的通道探针这次报
`gtx_direct ok=true status=200 ms=801`、`vercel_bulk ok=true engine="gtx"` ——
也就是说**这台机器的浏览器（走系统代理、出口在境外）能直连浏览器端 GTX**。
所以"我这次加的 GTX 不可达分类 + 熔断"在今天的线上路径里**并没有被真正触发过**，
不能拿"今天站点翻译正常"当作那套分类已受检验的证据；它目前只有单测与变异证据
（[[browser-gtx-unreachable-in-cn]] 说的是**大陆直连**口径 0 成功，两者不矛盾，但引用时必须分清是哪条通道）。

### 10.45 补上 GTX 熔断"隔日复位"这一支的独占覆盖（本地，未推）

`_gtxDead` 是**按天**存的，代码写法没问题：
`_gtxDeadToday(){ var d=_gtxDayKey(); return !!d && d===new Date().toISOString().slice(0,10); }`。
但原有判据 `test_dead_verdict_survives_the_next_visit` 的**docstring 说"昨天"、代码写的是今天**，
所以它只钉住"同日不再重发"，**"隔日必须重新尝试"这一支无人覆盖**。
风险不是想象出来的：把它改成 `return !!_gtxDayKey()`（有值就算熔断）是一次极其自然的"简化"，
改完所有旧判据照样绿，而用户侧后果是**一次网络抖动 ⇒ 该浏览器永久不再试直连**，
全部量压到限量兜底 Agnes（代码注释明确 Agnes 不是主力）。

新增 `test_yesterdays_breaker_expires_and_gtx_is_tried_again`，写进
`tests/rss_translate/test_runtime_translate_guards.py` —— 该文件本来就在 §10.43 的 A 组里，
**推送分组不变、不新增文件**。变异验证证明它是**独占覆盖**而不是重复上锁：

```
把 _gtxDeadToday 改成 presence 判法后：
  yesterdays_breaker        -> RED    "昨天的熔断今天仍在拦直连（实发 0 次）"
  survives_the_next_visit   -> GREEN  （同日那条照常绿 ⇒ 它看不见这一支）
```

复跑：A2 原命令 **279 passed**；`test_artifact_js_parses.py + tests/trim_guard/` **26 passed**。
遗留同类小项（本轮**没**顺手改，避免扩大改动面）：那条旧判据的 docstring 与它实际写的日期不符
（测的是"同日"不是"次日"），下次动这个文件时把措辞对齐即可。

### 10.46 落地状态快照（2026-10-01 07:43Z，接手照此继续即可）

**已上远端**
- `d6b042d782`（A 组 / ④）：`build_rss_aggregator.py` 运行时判据与构建期对齐 +
  `tests/rss_translate/test_buildtime_skip_guard.py` 的 14 语料双向 parity 判据 +
  `test_runtime_translate_guards.py`（锚点 `_LAT_WORD→_CJK_R`、新增熔断隔日复位判据）+
  `test_wall_queue_window.py`（同锚点）。推送时工具复查 4 个 blob 一致。
  ⇒ 待 16:00 场（看守 `bcpwb3u8n`）看 A2 blocking 与部署，并在部署后用 `transDiag` 复核
  "非拉丁文本开始被翻"且窗口量仍有界（`tried` 应仍是几十条量级）。

**本地已验通、等 B 组一起推**（因为都动 `update.yml`）
- ⑥：`cleanup(14) → cleanup(5)` + 新判据 `tests/rss_history/test_log_retention_days.py`
  （上界 ≤7 天、下界 ≥1 天；变异 `14/0/删掉清理` 三组全 RED、正常 GREEN；YAML 28 步；A2 原命令 **281 passed**）。

**B 组待推（16:00 场绿之后）**
1. `--delete index.html --delete rss-aggregator.html --delete ai-daily.html --delete daily-insight-history.html`
2. `tests/site_nav_drift/test_artifact_drift.py`（看树守卫，四向已验）
3. `.github/workflows/update.yml`（A3 步骤名与注释 + ⑥ 的 cleanup 行）
4. `tests/rss_history/test_log_retention_days.py`（⑥ 的新判据，随 B 同批）
5. 本手册（把本节改写成"已落地"）
落完的复查清单：`trees/main?recursive=1` 里那 4 个路径消失、下一场 A3 绿、
`git ls-files '*.html'` 只剩 `template.html`、`git rm --cached` 那 4 条对齐本地索引、
两场构建后再量 `build_logs/` 的 tip 体积（预期从 42.52 MiB 降到约 16 MiB）。

**仍未点单**：③ 封面图（建议 `#2 → #1(域名表) → #4`；#3 需接受第三方或自建）；
⑤ 全文译文缓存键换全文哈希（可长期挂账）。
要拿生产证据，得在真实无代理的大陆浏览器会话里看 `gtx_direct` 是否 `ok=false` 且熔断是否落 localStorage。









### 10.36 封面图那件事：**以 `docs/排查记录.md` 为准，我那两条说法有一条半是错的**

用户让我看 `docs/排查记录.md` 再谈图。对照结果：

1. **我说"14 条 Mixed Content 全来自阅读器 `innerHTML` 注入远端正文"——不成立。**
   记录 §3 实测：新华社那 98 张封面里就有 **38 条 `http://` 明文**（`www.news.cn`），
   也就是说**卡片数据本身就带 http 封面**。我那次"`chunk0` 里 http 图 = 0"是对**当时那一份 chunk0**
   的取样，不是普遍结论 —— 把一次取样当成"数据里没有"，是我这轮第二次犯的老毛病
   （§10.35 才写过"引用计数只能证明被读过，不能证明会执行到"，同理：抽样只能证明这一份）。
2. **我说"归一 `http://→https://` 行为中性"——机制上没错，但优先级排错了。**
   记录已经给出更值钱的四条：出厂判空/已知坏域名表、`no-referrer` 改按域名开关
   （**财富中文网带 Referer 即 200，而卡片硬写 `referrerpolicy="no-referrer"` 等于一票否决**，
   记录 §3 末尾自己标的"已确认的一处自我伤害"）、`onerror` 回退 `images.weserv.nl`（BBC 原图实测能取回，
   但引入第三方配额与隐私依赖 ⇒ 要用户拍板是否自建）、实时链路 `api/rss.js` **0 抽图**的长期缺口。
   ⇒ 消警告只是化妆，前四条才是病。**没有实施任何一条，等用户点单。**
3. **记录还纠正了我另一处口径**：`take_screenshot` 在这套自动化会话里拿不到可见 surface
   （`visibilityState=hidden`），且隐藏页里 `loading=lazy` 的图可能根本不发请求
   ⇒ 我之前那句"滚动稳定性我没法测"是对的，但更准确的说法是：**视觉侧只能靠 DOM 读数，
   不要把"没观察到 display:none"读成"加载成功"**。
4. 记录 §2 的"昨天今天 10 条改动里含 `img/image/cover/_upgrade` 的行数 = 0"与我今天的实测并存：
   我确实在 10-01 给封面标签加过 `onerror="this.remove()"` 与 `referrerpolicy`，
   那是 `main@555bdaad`（00:49Z）那次；记录 §7 也已写明"部署版与 main 的封面差异，视觉结果相同"。
   ⇒ 两边的时间窗不同，别当成互相打脸；**接手时先比 blob 再比文件名**（记录 §6 第二条误判就是踩这个）。

**②的决定（用户 10-01："平时都用 github"）**：入口是 GitHub Pages 域，
Vercel 只当 API 主机 ⇒ **Vercel 域那份 `rss-aggregator.html` 空壳保持不动（选项 A）**，
不加 `/api/rss` boot 兜底、也不放行 chunk0。它仍会在有人直接访问 Vercel 根域时报
"内容加载失败"——这是**已知且被接受**的状态，别再当回归去修。




### 10.35 接线清点：今天动过的判据里未接线的 6 个，全部落在**已登记**的那两族

用 mtime 捞出今天改过的 `tests/**/test_*.py`，逐个对照 `.github/workflows/*`（目录级与文件级都算命中）：

```
UNWIRED tests/rss_composite/test_diverse_realdata.py   ← 登记在 UNWIRED["rss_composite"]
UNWIRED tests/rss_composite/test_refresh_tags_js.py    ← 同上
UNWIRED tests/rss_composite/test_snapshot_tags.py      ← 同上
UNWIRED tests/rss_composite/test_tag_semantics.py      ← 同上
UNWIRED tests/tools/test_data_api_push_atomic.py       ← 登记在 UNWIRED["tools"]
UNWIRED tests/tools/test_data_api_push_delete.py       ← 同上（今天新增的那条也在这族里）
```

⇒ **今天没有新增"写着但没人跑"的孤儿**；其余全部 WIRED，含我换掉 A3 之后的
`tests/site_nav_drift/test_artifact_drift.py`。为什么要按文件再数一遍：
`test_no_new_orphan_test_directory` 的粒度是**目录**，它挡得住"新增一个没人跑的目录"，
挡不住"往已登记的目录里再塞一条没人跑的判据"。

顺带核出登记表里一个**旧数字**：`UNWIRED["tools"]` 原写"本机 182s"，
实测 `pytest tests/tools/ -q` = **30 passed / 128.7s**（墙钟 129s），
慢在 3 条各 30~62s（都在临时仓里真跑 git，不是外呼）。方向不变（确实不值得每场跑），
但数字已按实测改过（改在 `test_gate_wiring.py` 的登记串里）。
该改动与 §10.34 同批推，**当前只在本地** —— 单独推会把 14:00 场看守的 head 锚点换掉，
那种"自己把自己等的那场换掉"的错本手册已经记过一次。




· 改钉一条可信的：`tests/site_nav/test_artifact_js_parses.py::test_wall_queue_symbols_are_actually_called_in_artifact`
  对窗口队列 12 个符号要求"在产物的代码行里出现 ≥2 次"，只跳过注释行。变异验证：删掉 `renderWall()` 末尾
  那次 `_scheduleWallTranslate()` 调用 ⇒ 当场红；正常态整跑 CI 原命令 **276 passed**。
  这条为什么值得存在：删掉一个调用点时页面只是"少翻几屏"，控制台不报错、语法照过，是纯粹静默的回归。









### 10.47 ③#2 已上线（08:11 场部署，线上读数见 §10.49）

用户拍板"按建议顺序做"，先落 **#2（封面 referrer 改按域名开关）**：

- 实现：`build_rss_aggregator.py` 新增 JS `_REF_HOSTS = ['caifuzhongwen.com']` 与 `_coverRefPolicy(url)`，
  卡片模板从硬写 `referrerpolicy="no-referrer"` 改成按主机名判。**后缀匹配，不是子串匹配**；
  非 http(s) / 相对路径一律保持 `no-referrer`。
- 判据 `tests/site_nav/test_orphan_requests.py::test_cover_referrer_policy_is_per_host`：6 样本逐条对
  （含两条冒充样本 `evil.com/?x=caifuzhongwen.com`、`caifuzhongwen.com.evil.net`），
  外加两条防空跑断言：白名单不许为空、条目必须是裸主机名。
- 变异两向可杀：后缀匹配换成 `indexOf` ⇒ RED；`_REF_HOSTS` 清空 ⇒ RED。
  `py_compile` OK；整跑 CI 原命令 **282 passed**。

**下一批要推（构建空闲时；组内不可拆）**
1. **B 组（①）**：`--delete` 那 4 个页面 HTML + `tests/site_nav_drift/test_artifact_drift.py`
   + `.github/workflows/update.yml`（A3 名与注释）。
2. **⑥**：同一个 `update.yml` 的 `cleanup(14) -> cleanup(5)` + 新判据
   `tests/rss_history/test_log_retention_days.py`（上界 ≤7、下界 ≥1；`14/0/删掉清理` 三组变异全 RED）
   ⇒ 与 B 共用一个文件，**必须一起推**。
3. **③#2**：`build_rss_aggregator.py` + `tests/site_nav/test_orphan_requests.py`（实现与判据同提交，单独推也不会红）。
4. 本手册（§10.46/§10.47 状态改写成"已落地"）。

**~~还没做~~（本节写法已过期，照下面这三条看现状）**：
#1 出厂判空已做（§10.48，判空表 + 死规则清理）；#4 实时补抽图已做（§10.51/§10.53，
`lib/rss_cover.js` + 渲染层二次过滤 + 键名链判据）；⑤ 全文译文缓存键仍是挂账（用户决定不动）。
上面那份"下一批要推"的清单也已全部落地：B 组 + ⑥ + ③#2 = `7c08d02cea`（08:11 场线上验收，§10.49）。

### 10.48 ③#1 封面"必挂域名"判空表已做完（本地验通，待推）

按用户拍板的顺序接 **#1（出厂判空，用域名表，不做构建期探活）**。

**实现（`build_rss_aggregator.py`）**
- `_BAD_COVER_HOSTS` 5 项，逐条对应 `docs/排查记录.md` 的实测：`ichef.bbci.co.uk`、`i.guim.co.uk`、
  `npr.brightspotcdn.com`、`external-preview.redd.it`、`ops.xhyun.news.cn`。
  只收**浏览器(带系统代理)与 Node 直连两条通道都取不到**的域名。
- `_cover_host()` 去 scheme/ userinfo /端口并小写；`_host_matched()` 精确或 `.子域`，**不是子串**。
- 接入点是 `_upgrade_img_url()` 的第一件事（三处产封面路径全走它），XGO 推文图那条路径**故意不接**：
  `_extract_tweet_media` 只认 `/media/` 与 `tweet_video_thumb`，host 恒为 `pbs.twimg.com`（不在表里），
  套上去就是永不触发的空转。
- `_purge_bad_covers_in_history()` 清历史缓存里已有的坏封面并返回条数。不清的话，未被再次抓取的旧条目
  **每一场**都被重新判空一次，播报数字会钉在与"本场新增"无关的常量上。
- 播报：命中 `[封面判空] 丢弃 N 张…（其中历史缓存清理 M 张）：host×n`；**0 命中也出声**（stderr），
  因为"表恒为 0"要么是上游换了域名要么是表已过期，两种都需要有人知道。

**顺带删掉的死配置/死函数**（判空先跑 ⇒ 这些规则永不触发）
`_IMG_UPGRADE_RULES` 的 `ichef.bbci.co.uk /240/→/624/`、`_IMG_UPGRADE_SPECIAL` 的
`("ichef.bbci.co.uk", _bbc_aspect_upgrade)` 与 `("i.guim.co.uk", _query_width_upgrade)`，以及
`_bbc_aspect_upgrade` 整个函数。`("redd.it", ...)` 保留 —— `preview.redd.it` 不在表里，规则仍有真目标。

**明确不收的域名**（误收即红，判据里逐条写了理由）
`pbs.twimg.com`/`cdn.hk01.com`/`cdn.prod.www.spiegel.de`/`static01.nyt.com`/`wechat2rss.xlab.app`
只在无代理直连口径挂；`preview.redd.it` 记录里没有它的实测；`vpsbbc.com`/`files.seeusercontent.com`
各 1 张且两条通道结论矛盾；`www.appinn.com` 是单张图过期不是域名不可达；
`images1.caifuzhongwen.com` 带 Referer 即 200 ⇒ 走 #2。

**判据与变异**：新增 `tests/rss_cover/test_bad_cover_domain_table.py`（27 条），已接进 **A2 blocking**
（`.github/workflows/update.yml` 步骤改名 "…site nav & cover domain table (blocking)" + 命令加目录 +
`MUST_BLOCK` 同步）。`tools/mut_cover_table.py` 10 组变异**全 RED**，无逃逸：
判空没接进 `_upgrade_img_url`／误收 twimg／表清空／把 Referer 域名也判空／卫报升级规则没删／
0 命中不出声／只判精确 host／改成子串匹配／历史清理调用点被删／host 解析不吃端口与 userinfo。
其中"表清空"杀出 10 条红，"误收 twimg"杀出 5 条。

**一处设计回退（对抗审查发现的）**：第一版在 `_drop_unloadable_cover` 里写了"Referer 白名单优先"的
运行时例外分支，并配了 Python 侧 `_REF_COVER_HOSTS`。变异 M8（删掉该分支）跑出 **GREEN** ——
两张表不相交时那个分支永不触发，是死代码；而名单存两份正是今天刚修过的 Py/JS 分叉形状。
⇒ 改成：Python 不再存副本，放行名单**只从现生成产物的 JS** 里读（`_js_ref_hosts()`），
两表相撞由 `test_referer_hosts_survive_the_bad_table` 直接红，不在运行时分优先级。

**读数**：新鲜首屏 chunk0（10-01，360 条 / 133 张封面）里 `ichef` 11 + `i.guim` 2 = **13 张（9.8%）**
会被写成空 ⇒ 首屏少 13 张"必挂的封面卡 + 首字母占位"。含 09-18 旧块的本地全量：368+108+62+61+12=611 张。

**本地状态**：`git rm --cached` 那 4 个页面 HTML 已做（远端 7c08d02cea 早没了，本地索引一直滞后），
`tests/site_nav_drift/` 由假红转 **1 passed**；CI 的 A2 原命令本地整跑 **309 passed / 38.7s**（原 282 + 27）。

**待线上复核**（推完后下一场）：日志里 `[封面判空]` 的 N 是否 >0；
产物 `rss-data-0.js` 里 `ichef.bbci.co.uk` 的封面数应从 11 变 0
（取样命令见 `docs/排查记录.md` §10 的"图片命中率基线对照"，把 SHA 换成新 head 即可）。


### 10.49 batch① 已线上验收（08:11 场，head 7c08d02cea）

`36834780866` 整场 **success**（29 步全绿，无 skipped）：A2 blocking、A3"产物页面不许进 git"、
`Stage Pages site for Actions deployment`、`Upload Pages artifact`、`Deploy to GitHub Pages`、`Deploy to Vercel` 全绿。
⇒ **删掉 git 里那 4 个页面 HTML 没有造成站点清空**：发布路径靠"按名从工作目录取现生成的那一份"，
与 git 跟踪状态无关，`test -s` 硬断言在场。

Pages 侧实测（`Last-Modified: Thu, 01 Oct 2026 08:32:13 GMT`，即这场部署）：

```
200 285192  index.html
200  81634  ai-daily.html
200 3163365 rss-aggregator.html
200 349509  daily-insight-history.html
200 599205  rss-data-0.js      200 6273522 rss-data-1.js
```

远端树 `trees/main?recursive=1` 里 `.html` 只剩 `template.html`（4 个产物页面已 404）。
本地索引同步动作：`git rm --cached` 那 4 个路径（只动索引、不动工作树文件），
`tests/site_nav_drift/` 从假红转 **1 passed**。

**⑥ 的体积收益已经吃到（08:11 场就清了，不用等两场）**：`build_logs/` 从 **42.52 MiB → 15.88 MiB**
（12 个文件、合计 16,655,828 字节）。现存跨度 `2026-09-26 … 2026-10-01`，即 **含今天共 6 天** ——
`build_logger.cleanup(n)` 删的是 `date < today - n`，所以 `cleanup(5)` = 留 6 天，不是留 5 天；
判据 `test_log_retention_days.py` 的上界因此钉的是 ≤7（给这个 off-by-one 留余地），别看名字理解错。
复测命令（一次给出条数与字节和）：

```bash
gh api "repos/Kwei168/starhub/git/trees/main?recursive=1" \
  --jq '[.tree[]|select(.path|startswith("build_logs/"))] | {files:length, bytes:([.[].size]|add)}'
```

### 10.50 我把 A2 冻了一次（09:00 场），根因是"判据读了只在本机存在的文件"

head `f2c1576b99`（③#1 那批）在 09:00 场 **A2 blocking 红**，2 条失败全是
`FileNotFoundError: /home/runner/work/starhub/starhub/docs/排查记录.md`。

- 直接原因：我为"表项必须有实测出处"写的判据去读 `docs/排查记录.md`，
  而**那份记录从未进 git**（`git ls-files docs/排查记录.md` 为空、远端 contents API 404）
  ⇒ 判据在本地永远绿、在 CI 的干净检出里永远红。A2 红 ⇒ 构建与两个部署整场冻住，
  最后一次成功部署停在 08:32:13Z。
- 修法：删掉 `DOC` 常量与两处文件读取，改成"表里每个域名必须自带一行实测理由（`#` 注释 ≥8 字）"，
  证据随代码走。`tools/mut_cover_table.py` 复跑：③#1 的 10 组变异仍全 RED。
- **可复用的规矩**：写判据前先问"CI 的输入集合里有没有这个东西"。
  凡是读仓库外/未入库文件（用户本地笔记、`.deploy-tmp/`、被 prune 的产物目录）的判据，
  要么改成读入库的那份，要么改成读生成端，不能靠"我本地跑过了"。

### 10.51 ③#4 实时链路补抽图（连同渲染层二次过滤一起推：0e8cf5dbf6）

实时那条路（`?source=` / `?batch=`）过去**从不抽图**：`parseFeed` 只取音视频，出口
`img: it.img || ''` 恒空 ⇒ 构建后新发布的条目从出生就没封面，`_apiMergeTo` 只能保住旧条目的图。

- 新文件 `lib/rss_cover.js`（可 require，沿用 `lib/rss_retention.js` 的做法）：
  `enclosure > media:content > media:thumbnail > 正文首图 > 描述首图`，与构建期同优先级；
  单次扫描解码（`&amp;lt;` 这类二次编码不许被提升成标签，与 `html.unescape` 对齐）。
- `api/rss.js`：两条分支各接一次 `COVER.pickItemImage(...)`；短键映射补
  `if (it.img) obj.img = it.img;`；require 失败只影响封面且打 `::warning`，不打断响应。
- **必挂域名表只做一份**：构建时把 `_BAD_COVER_HOSTS` 注入产物的 `_BAD_COVERS`，
  卡片渲染前统一过 `_dropBadCover`。不在 `api/rss.js` 里再抄一张表 —— 否则 #4 会把 BBC
  那类必挂封面从实时路径带回首屏，正好抵消 #1；两张表也必然分叉。

**写判据过程中逮到的两个真问题（都已修）**
1. **转义描述漏抽**：主流 feed 的 `description` 是 `&lt;img ...&gt;` 转义过的 HTML。
   Python 侧由 ElementTree 解好实体所以命中，JS 侧不命中 ⇒ "实时有封面、刷新后封面消失"。
   修：`firstImgSrc` 先 `decodeEntities` 再找 `<img>`。
2. **Py/JS 判空分叉**：`HTTPS://ICHEF.BBCI.CO.UK/A.JPG` 构建侧判空、渲染层因用原样大小写比
   scheme 而放行。修：`_coverHost` 改 `trim + 整体小写`（与 Python 的 `partition('//')[0].lower()` 同形）。
   这条是今天上午 `_needs_translation` 分叉的同一种形状，所以新增常驻判据
   `test_buildtime_and_render_cover_filters_agree`：同一批 URL 两层逐条对。

**判据与变异**
- `tests/rss_cover/test_realtime_cover_js.py`：node 用例集调用 + 注入名单一致 +
  出厂/渲染两层同答案 + **真 `parseFeed` vs 真 `_parse_rss_item` 逐条同答案** + 响应形状带 img。
- `tests/rss_js/test_realtime_cover.js`：14 个用例（含实体、双重编码、音频 enclosure、`m:` 前缀）。
- 三处既有切片跑法补 `COVER` 注入（`test_parse_parity_js.py`、`test_cleanlink_and_dedup_safety.py`）：
  `parseFeed` 现在引用 `COVER`，切片跑法没有它 ⇒ ReferenceError，会**红在不存在的问题上**。
- `tools/mut_realtime_cover.py`：N1-N6 全 RED、0 逃逸（只改副本，靠
  `STARHUB_API_RSS` / `STARHUB_COVER_LIB` / `RSS_BUILD_SRC` 注入；上一版就地改真实文件
  并按哈希还原，因换行符归一化自毁校验而中止 —— 已改成绝不碰真源）。
- 一次事故记录：`test_realtime_cover_is_carried_into_the_response_shape` 里我误删了
  下一条判据的 `def` 行，把它的方法体接进了上一个函数 ⇒ `NameError: tmp_path`。
  判据自己坏了也会被自己的 A2 全量跑逮住，这是保留"跑整条 CI 原命令"的价值。

**本地读数**：`tests/rss_cover` 32 passed；CI 的 A2 原命令 **313 passed / 39.3s**
（唯一红是 `test_gate_wiring::test_no_new_orphan_test_directory` 报 `tests/ai_daily/`，
那是**本地已 add 未推**的别的工作，远端 404，不在 CI 集合里，我没动它）。

**待 10:00Z 场验收**：① A2 绿；② 日志 `[封面判空]` 的 N>0；③ 产物 `_BAD_COVERS` 与表一致；
④ `curl 'https://starhub-refresh.vercel.app/api/rss?source=<某英文源>'` 看是否开始出现 `img`。

### 10.52 两条"绿着但没在管事"的判据补上了（73b1a3371a / 2791c079a9）

对抗审查时自查出来的两个覆盖缺口，都不是"实现坏了"，而是**判据恒绿**：

1. **渲染层过滤没人验**。`_dropBadCover` 与 `_BAD_COVERS` 在产物里存在 ≠ 卡片真的用它。
   把模板改回 `src="'+esc(a.img)+'"`（即绕过判空、让实时封面重新上屏）时，
   当时所有判据照绿 —— 我只有一次性探针 `.deploy-tmp/_probe_cover_page.py` 验过行为。
   ⇒ 新增 `test_render_site_uses_the_bad_cover_filter`：从产物里定位 `function renderWall(` 到
   `<img class="cover-img"` 那一段，要求 `_dropBadCover(a.img)`、`hasImg=!!_cv`、
   `src` 与 `referrerpolicy` 都取自 `_cv`，并且该段里**不许再出现** `esc(a.img)`。
   变异 M11（`_cv=a.img`）与 M12（只把 src 换回 a.img）各自被杀 ⇒ 这条不是摆设。
2. **`lib/rss_cover.js` 有死出口**。第一版导出了 `decodeBasic` 与两个正则，"以后也许用得上"，
   实际没有任何调用方 —— 与本项目反复清掉的"公共 API 空壳"同形状。
   ⇒ 只留 `{ pickItemImage, firstImgSrc }`，并加反向判据
   `test_lib_rss_cover_exports_all_have_callers`（每个导出都要在 `api/rss.js` 或 node 用例集里
   出现 `C.X` / `COVER.X`）。变异 N7（多导一个 `decodeEntities`）被杀。

**变异汇总（现在都是常驻脚本，可重跑）**
- `tools/mut_cover_table.py`：M1-M12，全 RED，0 逃逸。
- `tools/mut_realtime_cover.py`：N1-N7，全 RED，0 逃逸。只改副本，注入点
  `STARHUB_API_RSS` / `STARHUB_COVER_LIB` / `RSS_BUILD_SRC`（绝不就地改真源；
  早先那版就地改 + 按 sha256 还原，因换行归一化自毁校验而中止，已废弃该写法）。

**本地读数**：`tests/rss_cover` 34 passed；CI 的 A2 原命令 **314 passed / 41.1s**
（唯一红仍是本地未推的 `tests/ai_daily/` 孤儿目录，远端 404，不在 CI 集合里）。

**③#2 已线上生效的实证**（`curl` 08:32:13Z 那份产物，3,163,365 字节）：
`_coverRefPolicy` 出现 2 次、卡片上是 `referrerpolicy="'+esc(_coverRefPolicy` 的按域名写法、
硬编码 `no-referrer"` 形式 **0 次**、`this.remove()` 在场。
同一份产物里 `_BAD_COVERS` / `_dropBadCover` 均为 0 次 ⇒ ③#1/#4 确实还没上线，
必须等 10:00Z 那场部署，别把"已推"当"已生效"。

### 10.53 实时封面的键名链：两处接缝已钉住（别再靠读码确认）

`③#4` 的封面要经过**四次键名变换**，每一处都可能把值丢掉，而"API 有没有发 img"这条判据管不到下游：

```
api/rss.js parseFeed  -> result.img          （短名，实时抓取侧）
   ↓ dedupSourceItems / applyRetention        （原地改对象、不重建 ⇒ 字段不会掉，读码确认过）
api/rss.js 出口映射   -> obj.img（只在真值时写）
   ↓ HTTP JSON
页面 _apiMergeTo      -> image: it.img||''    （长名，与构建期快照对齐）
   ↓ src.items
页面 buildArt         -> img: it.image||it.img||''   （长名与短名都要认）
   ↓ ART
卡片渲染              -> _cv = _dropBadCover(a.img)  （必挂域名在这一步写空）
```

常驻判据 `tests/rss_cover/test_realtime_cover_js.py::test_realtime_cover_key_chain_is_complete`
按函数边界切出 `_apiMergeTo` 与 `buildArt` 两段，分别钉
`image:it.img||''` 与 `img:it.image||it.img||''`。
变异 N8（合并处写死 `image:''`）与 N9（`buildArt` 只认短名）都由它杀掉 —— 这两条在加判据之前**全绿**。

仍未端到端验证的部分（下一场部署后补）：
真 HTTP 调 `https://starhub-refresh.vercel.app/api/rss?source=<英文源>`，看响应里是否出现非空 `img`；
以及 `rss-data-0.js` 里 `ichef.bbci.co.uk` 的封面数是否归零（取样命令见 `docs/排查记录.md` §10）。

### 10.54 ③#1/#4 的部署前基线（红线留档，部署后同一脚本必须转绿）

**取证脚本**：`.deploy-tmp/_verify_cover_shipped.py`（只读；任一项不达标就非零退出）。
它现在报红，这是刻意的 —— 判据必须先在线上真数据上失败一次，之后变绿才算证明，
否则就是"恒绿空转"。

10:04–10:06Z 实测（Pages 与 Vercel 现取，走系统代理）：

| 观测点 | 部署前读数 | 部署后期望 |
|---|---|---|
| 页面 `rss-aggregator.html` | 3,163,365 字节，`_BAD_COVERS` / `_dropBadCover` / `_dropBadCover(a.img)` **各 0 次** | 三者都在场，且名单与 `_BAD_COVER_HOSTS` 完全一致（差集为空） |
| `rss-data-0.js` | items=360，covers=128，**必挂域名封面 21 张**（ichef 15 + i.guim 6） | 必挂域名封面 **0 张** |
| `rss-data-1..5.js` | 23 / 1 / 91 / 114 / 32 ⇒ 六块合计 **282 张 = 占封面 7.4%**（covers 共 3,795，items 共 6,663） | 归零；封面总数按同口径下降 |
| `/api/rss?source=arstechnica_60` | 20 条，键集合 `[d,fc,s,t,u]`，**非空 img = 0**；`X-Rss-Retention: on` | 键集合出现 `img`，非空条数 > 0 |

三点值得记下来的旁证：
- `X-Rss-Retention: on` 说明 Vercel 侧 `require('../lib/*.js')` 在生产是通的（`.vercelignore` 排了
  `tests/ docs/ *.py .deploy-tmp/`，**没排 `lib/`**）⇒ ③#4 新模块上线后不会静默降级。
- 7.4% 与用户 `docs/排查记录.md` 独立测得的 7.6%（9 个坏域名 / 494 张）同量级；
  我的表只有 5 个域名却覆盖到同样的比例，说明剩下的差距集中在 BBC（表内已含）。
- 猜 source key 会得到 404（我第一次用了 `bbc_top_stories`，真 key 是 `bbc_top_stories_592`）
  —— 端点没坏，**取证必须从 `rss_sources.json` 取真实 key**。

**残留引用与死配置自检（10:18Z）**：`grep` 全仓 `bbc_aspect|_REF_COVER_HOSTS|/240/` 为空；
`_IMG_UPGRADE_RULES=[scx1.b-cdn.net, pbs.twimg.com]`、`_IMG_UPGRADE_SPECIAL=[redd.it]`，
与判空表交集为空 ⇒ 删掉 BBC/卫报规则后没有留下永不触发的死配置，也没有引用已删符号。

### 10.55 ③#1/#4 已线上生效（10:00Z 场 run 36846375925，head 6963482515）

那场 14:00… 不，**10:00Z 场整场 success**（A/A2/A3/B + Fetch stars & build + Stage Pages +
Upload/Deploy to GitHub Pages + Deploy to Vercel 全绿，updated=10:19:41Z）。
`compare/2791c079a9...6963482515` = ahead 3 / behind 0，且该 ref 上三个关键 blob
（`tests/rss_cover/test_realtime_cover_js.py=23843baa16`、`lib/rss_cover.js=661bd83124`、
`update.yml=cfac922c44`）与我推的逐一同 ⇒ 绿的是**含改动的检出**。

**CI 侧**
- A2 **317 passed**（含新接进的 `tests/rss_cover/` 35 条）、A3 1 passed、B 闸 391 passed。
- 构建日志第 2464 行：
  `[封面判空] 丢弃 1047 张必挂封面（其中历史缓存清理 363 张）：ichef.bbci.co.uk×600、i.guim.co.uk×195、npr.brightspotcdn.com×158、external-preview.redd.it×50、bucket-cb-…ops.xhyun.news.cn×44`
  ⇒ 表真的在命中（不是恒 0 的空防线），且历史清理那 363 张确认 `ops.xhyun.news.cn` 这类
  旧 URL 已从缓存里被写空，下一场不会重复计数。
- 另有 9 行 `[封面判空] 0 张命中` 落在 10:02:51-52 的 **A2 步骤输出**里
  （前一行是 `[留存] 出口闸门：进 2 条…`，是合成 2 条语料的单测）
  ⇒ 这些是测试驱动同一段代码时打的，不是第二处调用点；也顺带证明播报确实在被跑。

**线上侧（`.deploy-tmp/_verify_cover_shipped.py` → 结论"全部达标"，rc=0）**

| 观测点 | 部署前（10:04Z） | 部署后（10:20Z） |
|---|---|---|
| 页面 `_BAD_COVERS` / `_dropBadCover` / `_dropBadCover(a.img)` | 各 0 次 | **三者都在场**，注入名单与 `_BAD_COVER_HOSTS` 差集为空 |
| `rss-data-0.js` 必挂域名封面 | 21 张（ichef 15 + i.guim 6，共 128 张封面） | **0 张**（封面总数 128 → 141，没把健康封面一起清掉） |
| `/api/rss?source=arstechnica_60` | 键集合 `[d,fc,s,t,u]`，非空 img **0** | 键集合含 `img`，非空 img **20/20** |
| 页面字节数 | 3,163,365 | 3,158,768（-4.6 KB，无体积回归） |

**死代码/悬空引用自检**：`grep -n "bbc_aspect|_REF_COVER_HOSTS|/240/"` 全仓为空；
升级规则现存 `[scx1.b-cdn.net, pbs.twimg.com]` + `[redd.it]`，与判空表交集为空。

**封面这一组（#1/#2/#4）到此闭环。** 仍挂账未动：⑤ 全文译文缓存键（用户决定）、
#3 weserv 封面代理兜底（用户决定不做）。

### 10.56 增长曲线：从"调保留天数"改成"每场变的不再入库"（批 1-4，TDD）

用户点破我前面几轮的共同问题：**`cleanup(N)`、`--keep N` 都是在改斜率，不是在压平曲线**。
git 的存储模型是"内容变一次就永久多一份副本"，所以只要一个文件每场都变且被提交，历史就单调增。
实测（相邻两个 bot 提交的递归 tree 差，`truncated=false`）：

```
一次构建新增 14 个 blob / 19.83 MiB，消失 0 个
  hot_history.json                8040 KB   ← 只有构建脚本读回
  analysis_snapshot.json          3555 KB
  translations.json               3239 KB
  build_logs/<今天>.jsonl         2093 KB
  rss_trend_history.json          1126 KB
  insight_tracking_history.jsonl   762 KB
  rss-data-0.js                    506 KB   ← Pages 要发，但 git 不必留副本
  daily_insight_*                  688 KB
  文档(HANDOFF)                    144 KB
```
⇒ 5.86 GiB/月、约 10 周撞 5 GiB。结论：**要平就必须让这些退出 git**，跨场传递换通路。

**两条既有通路正好够用**（不是新机制）：状态 → `actions/cache`（`rss_history`/`emb-cache` 早就这么走）；
产物 → `Stage Pages site` 的"按名字从工作目录拷 + `test -s`"（`rss-data-1.js` 与 4 个 HTML 已经这么退出）。

**按 TDD 分成四批，每批先红后绿 + 变异自证**

| 批 | 内容 | 判据 | 变异 |
|---|---|---|---|
| 1 | `starhub-state` 缓存族（7 文件 + `build_logs`）：Restore/Save/Diagnose + `--keep starhub-state=3`。**纯加法**，文件仍入库 ⇒ 无中间态 | `tests/rss_history/test_state_cache_wiring.py` 12 条 | `tools/mut_state_cache.py` S1-S12 |
| 2 | 7 个状态文件从**两条** `git add` 清单摘掉（主路径 + push 被拒的重试分支）+ `.gitignore` 逐名 7 行 | 同上（`test_state_family_files_are_not_committed_anymore` 等） | T1-T3 |
| 3 | `--delete` 那 7 个路径 + 本地 `git rm --cached` 对齐 | `test_state_files_are_not_tracked`（先红：7 个全部"仍被跟踪"） | 落地后把文件 add 回索引即可证红 |
| 4 | 日志每天一次：`tools/daily_commit_gate.sh`（读入库 marker，**不用** `git log`）+ 摘要搬到 Commit 之前 + 退役 `build-log-summary.yml` | `tests/rss_history/test_log_daily_commit_gate.py` 9 条（闸门被真跑：open/closed/跨天/坏 marker 必须 exit 0） | `tools/mut_log_gate.py` G1-G5 |

**本地读数**：批 1 后 CI 第一场 `41388122cd` 整场 success，缓存出现
`starhub-state-Linux-36858947240-1` = **4,489,082 B**，Diagnose 打印 7 个文件字节数 +
`build_logs/` 16,994,210 B；批 2 在 12:38 那场 A2/A3/B 全绿（head `2fbf8e4524` 含批 2，
`compare/07526b64f8...` ahead=2/behind=0）。本地 A2 原命令 **339 passed**，唯一红是批 3/4 故意留的
"仍被跟踪"类判据。

**这一轮我自己造又被变异逮出来的四个坑（下次直接照单查）**
1. **判据只断言"字符串存在"** ⇒ `Commit` 步里有两处清单，变异删掉其中一处仍然绿。改成**计数断言**
   （`闸门调用数 == add 次数`、`ls-files -d 次数 == add 次数`、`marker 写入次数 == add 次数`）才有牙。
2. **全文 `replace` 的变异会打偏**：`" build_logs/"` 在 yml 里最早出现在 Diagnose 的 echo 文案里，
   命中它之后"越序摘除清单"这个变异其实什么都没改，判据"合理地"绿 ⇒ 变异要按**清单行定位**。
3. **变异脚本把 SKIP 算成已挡住**：锚点写错就等于没测，却计入"0 逃逸"。改成 INVALID 单独计入未覆盖。
4. **改完判据留下的死函数/说谎注释**：`state_names`、`add_with`、`edit_add_lines`、`ADD_LOGS` 全部
   零调用；两条注释（"写方含 build-log-summary.yml"、"build_logs 留到批 4"）在动作落地后立刻变成谎话。

**批 5（下一批，需单独评审）**：`rss-data-0.js` 等 4 个产物退出 git —— 会撞上
`test_pages_deploy_wiring.py:108-125` 的**正向**断言与 `tools/trim_commit_guard.py:28-30` 的
`KEEP_ALWAYS=('rss-data-0.js',)`，还要先查出"哪个测试在读库里的 chunk0"并改成自造副本。
批 1+2+4 落地的预期：每场新增 19.83 → **约 1.7 MiB**（日志再被每日闸门管住后约 0.05 MiB/场 + 每天 2.2 MiB 快照）。

### 10.57 曲线压平的实际落地：批 3 / 批 5a / 批 5b+5c（2026-10-01 13:00–14:10Z）

**读数（相邻 bot 提交的递归 tree 差，`truncated=false` 已验）**

| 场次 | 每场新增字节 | tip | 备注 |
|---|---|---|---|
| 12:56 场（批 2 后） | 2.848 MiB / 5 条 | 40.97 MiB | 7 个状态文件已不再重写 |
| 13:38 场（批 3+批 4 后） | 3.323 MiB / 7 条 | **24.27 MiB** | 其中 build_logs 2.77 MiB = 当天那**一次** |
| 14:00 场（批 5a） | 见下 | | 每日闸门应当关：不再出现 build_logs/* |

仓库 `.size` 2.44 GiB（当日 10:2x 为 2.45，已开始往下走）；Actions 缓存 0.98 GiB / 11 键
（emb 0.878 + rss 0.094 + starhub-state 0.008，被 `--keep` 钉在稳态）。

**批 3 的验收不是"URL 404"就完事**，四件事都得到：
1. 远端 7 个 raw URL 全 404；
2. Pages 上 4 页 + `rss-data-0.js`(599,472 B) + `hot_snapshot.json` + `rss_sources.json` 全 200；
3. 下一场 Diagnose 打出 7 个文件**仍在盘上**（8,278,933 / 3,645,569 / 3,313,241 / 1,153,325 /
   778,323 / 410,065 / 263,570 B）⇒ 缓存接管，不是数据丢了；
4. A2 在 ubuntu 342 passed、整场 success ⇒ 部署解冻。

**批 5 的关联分析逼出一条硬教训（先通路，后摘名）**：`descriptions_zh.json` / `trending_snapshot.json` /
`hot_snapshot.json` 也是"读回上一次再写回"的跨场缓存，但它们**今天唯一的传递通道是 git checkout**
（`fetch_and_build.py:432` 读 trending_snapshot、`:486` 写回 = 星标增量基线；`:722/:813` = 描述译文缓存；
`build_rss_aggregator.py:8732` 兜底读 hot_snapshot）。若照原计划直接把四个名字一起摘掉，星标增量会永远对着
一份冻结基线重算、新仓库描述每场重译烧配额，**而构建全程绿、没有任何一处会报错**。
⇒ 批 5a 先把它们补进缓存 path + `.gitignore` + 诊断三处（纯加法），批 5b 才摘名字。
判据 `test_carry_files_have_a_cache_home_before_they_leave_git` + 变异 C1/C2/C3 钉住这个顺序。

**两处失实注释（挡住过一次真改动，必须一起修）**：`tools/trim_commit_guard.py:28` 的
`KEEP_ALWAYS = ('rss-data-0.js',)` 与 `repo-trim.yml:92` 的步名都写着"真实分块测试要读已入库副本"。
实测没有任何测试用 git 取库内那份 —— `tests/rss_composite/test_diverse_realdata.py:32` 是
`os.path.join(ROOT, "rss-data-0.js")` 的工作目录读，且 `tests/rss_composite/` 未接进任何门禁步；
`trim_commit_guard.py` 只做路径名分类、从不打开文件。白名单留着 = 永久挡住这批历史 blob 的回收。
⇒ 清空 `KEEP_ALWAYS`、订正步名、翻转 `tests/trim_guard/test_trim_commit_guard.py:88` 那条断言
（trim_guard 本地 22 passed，含真跑 filter-repo 的排练）。

**判据语义翻转的示范**：`test_no_big_chunk_is_committed` 原来**正向**要求 chunk 0 留在 add 清单，
批 5b 把它翻成"不许在清单、必须在发布名单、必须有 test -s"，并新增反向半句禁止纯跨场态上线
（`trending_snapshot`/`descriptions_zh` 无任何前端读方，上线只会扩大公开面）。
发布名单的匹配用 `fnmatch`：shell 的 `for f in rss-data-*.js` 会展开出 `rss-data-0.js`，
判据若只认字面名会把真实存在的覆盖读成漏项。

**我自己这轮的两个错，都被判据在推送前逮住**
1. 把 批 3 的 RED 判据提前写进被 A2 收集的文件 ⇒ 13:00 场 A2 一红冻整场部署（1 failed / 340 passed）。
   修法不是删判据，是把 批 3 做完让它转绿。**写 RED 判据前先确认它所在目录是否被 blocking 闸收集。**
2. 改诊断步的 `for` 循环时用 `[:-2]` 去尾巴，只切掉 `do` 留下 `;`，成非法 shell；
   `test_autocommit_no_rollback.py::test_every_run_step_is_shell_valid` 本地判红拦下。

**本地索引对齐**：本仓远端写入走 `tools/data_api_push.py`，本地 `.git` 从不随之前进 ⇒ 远端已删除的路径
在本地仍"被跟踪"，让 `test_state_files_are_not_tracked` 恒红；而一条恒红的判据会**污染整个变异电池**
（任何变异都"看起来被挡住"）。`tools/mut_state_cache.py` 的"基线不绿就拒绝自评"守卫正是为此存在。
对齐脚本 `tools/untrack_state.py`：只动索引（`--cached`）、`--dry-run` 可先看、
回滚命令自动落 `.deploy-tmp/restore_state_index.sh`（`--restore` 执行它）。


### 10.58 批5a 把整族缓存搞丢了（改 path 名单 = 换族），以及本地假红的根治

**现象**（14:00 场 run 36872974114，head=20193e4c17=批 5a）：Diagnose 打出 6 个 `MISSING`，日志原文

```
Cache not found for input keys: starhub-state-Linux-36872974114-1, starhub-state-Linux-
```

连前缀回退都没命中，而库里还躺着 12:20 / 12:56 / 13:38 三份同族 4.48 MB 缓存，且 13:38 那场前缀回退是成功的（7 个文件全 OK）。唯一变量就是 path 从 7 条变 10 条。

**机制**：`actions/cache` 把 path 清单算进缓存身份。改名单 = 换族 = 旧缓存瞬间不可达。

**当场代价**：那场把 `translations` 从零重建到 30,000 条上限（日志 `[缓存] 保存翻译缓存: 30000 条`）、撞 34 次 429；`analysis_snapshot` 缺失 ⇒ 重跑 LLM 重分析。`::warning title=跨场状态冷启动` 按设计出声了 1 次。append-only 的 `hot_history` / `insight_tracking` 重建不出来 ⇒ 7 天窗口要从头积（是否回捞等用户裁决）。

**制度化**：`test_state_path_list_has_a_frozen_record_copy` 把名单钉成登记副本，改名单必须同批 bump 并安排播种或写明接受冷启动；变异体 C6 自证能红。批 5 因此拆成 5a（补通路）/ 5b（摘名）/ 5c（退树）——以后往缓存里加成员都按这个形状走。

**本地假红的根治**：本仓远端写入走 Data API，本地 `.git` 从不随之前进 ⇒ 远端删除的路径在本地仍被跟踪，于是 `test_state_files_are_not_tracked`、`test_hourly_summary_workflow_is_not_tracked` 恒红；而恒红的判据会污染变异电池（任何变异都「看起来被挡住」）。所有电池都带「基线不绿就拒绝自评」的守卫，代价就是每次得先对齐索引。`tools/untrack_state.py --align-remote` 把它做成一次性：按远端递归 tree 求差、只 `git rm --cached`（不动磁盘）、先确认 HEAD 里取回得了、回滚命令自动落 `.deploy-tmp/restore_index_align.sh`。白名单只覆盖本工作主动退役的路径 —— 本地 HEAD 还带着另一条工作线（AI 日报）未推的提交，全量对齐会把别人在制品从索引里摘掉（实测跳过 89 个）。对齐后本地 A2 = **358 passed / 0 failed**，第一次做到完全干净。

**批 6 落地**：`tools/history_growth.py`（只读；口径 = 相邻两个提交的递归 tree 差里「新 (path,sha)」的字节和）+ advisory 步 `Monitor per-build git growth (advisory)`（必须 `continue-on-error`、必须排在 Commit 之后，否则量到上一场）。阈值 6 MiB 的理由写进判据：每天那一次日志合法带来 ~2.6 MiB，阈值低于它天天误报 = 没有告警；要抓的回退形态是 17–20 MiB/场。判据 7 条 + 变异 H1–H7 全抓，0 逃逸。

**计划 §3 的冷启动演练换了做法**：原写「本地跑一次 `fetch_and_build.py incremental`」，但本地裸跑会挂住烧翻译配额并写脏跟踪产物（见 gate-b-no-local-run）。改成 `tests/rss_history/test_cold_start_readers.py` 直接调真实读取函数（cwd 换空临时目录），6 条覆盖 `_load_caches` / `_load_prev_analysis` / `_load_history` / `_accumulate_hot_history` 的缺失与损坏分支，每条都带「正常文件必须真读回来」的反向半句防空转；配套 `tools/mut_cold_start.py` 用 K1–K4 破坏生产读取端自证能红， finally 里逐字节还原并校验 sha256。踩到的一条工程细节：锚点必须按目标文件自己的行尾拼（`build_rss_aggregator.py` 是 CRLF、`build_daily_insight.py` 是 LF），否则多行锚点一处也命中不了 = 静默 INVALID。

**另一处实测契约（写下来免得下次又按直觉写错判据）**：`_load_caches()` 在文件缺失时是「什么都不做」，不抛也不清空 —— 所以「冷启动 = 空缓存」成立的前提是 `_trans_cache` 的**模块初始值**必须是空 dict。第一版判据把它写成「缺失 ⇒ 清空」当场红给自己看了，随后补了 `test_module_initial_cache_is_empty`（AST 顶层赋值）钉住真正的前提。
