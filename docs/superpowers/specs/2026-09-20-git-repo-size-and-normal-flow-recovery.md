# 仓库体积与"恢复常规 git 流程"——核实与处置规格

日期：2026-09-20（北京时间 06:00–07:30 一段实测）
状态：**分析与分阶段待批**，本文件自身不改变仓库状态；已执行的部分只限 §4 的 P-原子（工具修复）与只读测量。
上游输入：另一会话写的《StarHub 仓库体积（.git 7.4G / 远端 3.86G）处置方案》（**该文件没有落盘，只活在对话里** —— 本规格因此把它的每条主张连同我的核实结果一起固化）。

---

## 0. 这份规格要回答的三个问题

1. 那些体积数字**是不是真的**（我独立重测，不引用对方口径）；
2. 按原方案执行**会不会失败**（有 2 处直接决定成败）；
3. 用户提的目标——**"能走常规 git 流程推送 + 把存储降下来"**——**顺序应该是什么**。

## 1. 实测数字（与对方方案的差异逐条标注）

| 项 | 对方方案 | 我的实测 | 判定 |
|---|---|---|---|
| `.git` 体积 | 7.4G | **8.0G**（两小时涨 0.6G，两个会话都在提交） | 同量级，在涨 |
| 远端仓库 | 3.86G | `.size=4,629,635 KB ≈ 4.41 GiB` | 同上 |
| loose 对象 | 2777 个 | `count-objects`：**3127 个 / 6,540,273 KiB** | 略被低估 |
| 可回收垃圾 | "约 4.8G" | 对象总体积 **34.82 GiB(未压缩)**；`--all` 可达 **13.83 GiB**、**不可达 20.99 GiB（60%）** → 折磁盘 ≈ **4.8 GiB** | **核心主张成立**，独立算法吻合 |
| gc 配置 | 三项被关闭 | `gc.auto 0 / gc.geometricrepack 0 / gc.autodetach false`（另 `gc.writecommitgraph false`） | 属实 |
| `git replace` 遮罩 | 存在 | `refs/replace/28f33177… → 484e35e`，且 `79dd247` 确实缺失 | 属实，断链只在陈旧分支可达路径上 |
| 主线提交数 | 99 | `git rev-list --count HEAD` = **141** | 低估 42% |
| rss_history 出仓 | 已取消跟踪 | 已取消跟踪 ✓（工作树仍有 61MB 文件，历史里 11 版） | 属实 |
| HEAD 巨型产物 | 约 210MB | `rss-data-1.js 89.8 + rss-data-2.js 66.4 + translations 18.9 + hot_history 9.5 + analysis 3.6 + rss-aggregator.html 3.1 + rss-data-0 0.7` ≈ **192MB** | 量级对 |

**不可达对象到底是谁（按内容签名归类，体积前 60 个）**：`rss-data-1.js` 旧版 27 个 / 1.84 GiB、`rss-data-2.js` 9 个 / 0.65 GiB、`translations.json`（键是文章 URL）13 个 / 0.76 GiB，另有 **4 个 blob 的内容开头就是 `<<<<<<< Updated upstream`**（0.36 GiB）—— 说明历史上确有"带冲突标记的产物"被提交/暂存过。
⚠ 这里说的分块是 **Pages 用 `<script src="rss-data-N.js">` 加载的那一套**，不是 72h 存档那套，也不是洞察向量那套（三套同名"分块"要分开谈）。

## 2A. "我们是不是一直在分支上没合并？"——分叉的真实形状（09-20 07:2x 实测）

先给结论：**不是"在 feature 分支上忘了合并"，而是同一个分支名 `main` 被两条独立提交线各写了一遍。**

| 事实 | 实测值 |
|---|---|
| 本地与远端的分支名 | 都是 `main`（`git branch --show-current` = main；远端 `refs/heads/main`） |
| 共同祖先 | `bf1b57132e`，时间 **2026-09-18 21:57 +0800** —— 分叉点就在这一刻 |
| 只在本地的提交 | **58 条** |
| 只在远端的提交 | **87 条**（含每小时 `chore: auto update stars`） |
| 双胞胎证据 | 同一条信息、不同 SHA：本地 `5610485` ↔ 远端 `b866ee7`（RSS 覆盖率修复）、本地 `f5b80ca` ↔ 远端 `5061601`（§11 第7期）、本地 `2a144b0` ↔ 远端 `6f7948f`（CLAUDE 硬规则） |
| **两个 tip 的内容差** | `git diff --name-status main origin/main` = **24 个文件，全部是构建产物**（`*.html`/`*.json`/`rss-data-*.js`/`*_tracking_history.jsonl`/`build_logs/`），**源码零差异** |

也就是说：**没有任何"写了却没合并"的代码** —— 每条工作都以"双胞胎提交"的形式同时存在于两条线上；
远端那条之所以更靠前，只是因为 CI 每小时把产物提交在远端线上，本地这条线从 09-18 起就没再同步过产物。

成因有两条，都已在别处固化为规则：
1. Data API 推送的提交父节点取**远端 head**，永不回写本地 → 每推一次，远端线多一条、本地线原地不动；
2. 本地 `origin/main` 因为"以为 fetch 也是死的"而从未更新（实测停在 22:16 的 `5b07052`）→ 分叉点一路无人收拾。

**修法不是 merge**（merge 会把 09-18 之后的产物与双胞胎改动重新对撞，制造几千行无意义冲突），
而是**以远端为主干做单线归一**：确认"本地独有内容=0"（上表已证：源码零差异）→
先推掉本地在途的三份未提交内容 → `git tag pre-normalize main` 留退路 → 本地指针对齐 `origin/main` →
之后所有提交走单条线，`git push` 才有意义（= 验收清单第 4 条，"常规 git 流程恢复"的唯一定义）。

## 2B. 传输到底死没死（09-20 07:2x 实测，直接改写本规格的前提）

```
$ git fetch origin main
From https://github.com/Kwei168/starhub
 * branch            main       -> FETCH_HEAD
   5b07052..b866ee7  main       -> origin/main
real 0m23.320s     exit=0
```

**`git fetch` 可用，23 秒**（代价：loose 对象 +56 个 / +110MB，本地 `.git` 从 8.0G 微涨）。
所以"传输全灭"这句必须降级为：**`ls-remote` 与 `fetch` 实测可用；`push` 仍未实测**（历史上失败的场景是"带断链对象做 upload-pack 谈判"）。
`CLAUDE.md` 第 0 节现在写的是"push/fetch 直连是死的"，**这条按实测要改成"push 需先实测、fetch 可用"** —— 待批准后修订。

## 2C. 真正的根因（本轮实测推翻原方案的前提）

**原方案说"断链对象 + gc 被关导致 git 全灭"；实测：让 `git fsck` 报出 12,285 行错误的是一个陈旧的 `multi-pack-index`，与断链无关。**

| 步骤 | 命令 | 结果 |
|---|---|---|
| 清理前 | `git fsck --connectivity-only`（**不带管道**取真实退出码） | **exit=34**，12,285 行；其中 **12,208 行是 `failed to load pack entry for oid`**、3 行 `failed to load pack in position` |
| 逐个验包 | `git verify-pack -s <每个 .idx>` | **8 个 pack 全部 exit=0** ⇒ pack 本体没坏 |
| 找元凶 | `ls .git/objects/pack/` | `multi-pack-index` **mtime 09-14 16:11**，而 `pack-94442…`(506MB, 09-20 06:10)、`pack-b5cab…`(09-19) 都比它新 ⇒ MIDX 早就对不上现实 |
| 隔离（可逆） | `mv multi-pack-index → %TEMP%/starhub-git-garbage-20260920/` | `git fsck --connectivity-only` 从 12,285 行降到 **74 行**，**只剩 1 个真缺陷**：`missing commit 79dd247`／`broken link from commit 28f33177` |
| 复验传输 | `git fetch origin main` | **exit=0**，`origin/main=b866ee7` 不变 ⇒ 隔离垃圾与 MIDX 后传输照常 |

**为什么这能解释"传输全灭"**：MIDX 是"跨包对象查找表"。一旦有包被**手工删除**（证据：`count-objects` 报的两个 `no corresponding .pack` 孤儿 `.idx`，以及两个 160~187MB 的 `tmp_pack_*` 半成品），MIDX 里就会留下上万条指向不存在位置的条目；
任何按 MIDX 查对象的操作都会拿到"读不到"，表现就是 `Could not read <oid>` / `could not parse commit`，于是历史上我们把 `fetch/push` 判成"协议死了"。
→ **教训写进规则：不要手删 `.git/objects/pack/*`；要清就删整套派生文件（`.midx`/`.rev`/孤儿 `.idx`）或走 `git gc`。**

**断链的确切位置（比原方案精确）**：`28f33177` **只**从 `refs/remotes/origin/daily-insight-tdd-fix`（`a2ea918`）可达；
逐条核过：`main`、`origin/main`、`refs/heads/daily-insight-fix-v2`、`refs/remotes/origin/daily-insight-fix-v2`、`refs/stash` **全部不含它**（各 0 命中），reflog 也 0 命中。
而 `origin/daily-insight-tdd-fix` **在远端分支列表里不存在**（远端只有 `main` 与 `daily-insight-fix-v2`）⇒ `git remote prune origin` 就会把它删掉，
断链随之失去唯一的根，`refs/replace` 遮罩也就没用了。**主线与全部在途工作都不在那条链上。**

## 2D. 本轮已执行的处置（全部可逆，隔离件在 `%TEMP%/starhub-git-garbage-20260920/`）

1. `count-objects` 自标的 5 个 garbage 移出：`tmp_pack_i3pIYW`(178MB)、`tmp_pack_W3pa18`(155MB)、
   孤儿 `.idx` `pack-d946bec2…`(242KB)/`pack-f6ff87bf…`(68KB)、`objects/5c/tmp_obj_aMnyd8`(8.2MB)
   → `.git` 从 **8.1G → 7.8G**，`count-objects` 现在报 **`garbage: 0 / size-garbage: 0`**；`git status`/`rev-parse HEAD`/`fetch` 复验均正常。
2. 陈旧 `multi-pack-index` 移出（见 §2C）。
3. **未做**（仍待批，含破坏性动作）：`git replace -d`、删陈旧 ref、stash 导出后 drop、`git gc --prune=now`、本地指针归一、`git push` 实测。

## 2. 决定成败的两处更正

1. **`git bundle create --all` 这步可以去掉，反而应删。** `git ls-remote origin` **实测可用**（返回 `refs/heads/main=6f7948f90d`、`refs/heads/daily-insight-fix-v2=e806aad`），
   而且 **`daily-insight-fix-v2` 在远端就存在** → 本地真独有内容只剩两条 stash。bundle 要遍历 13.83 GiB 可达对象（几十分钟 + 3~4GB 文件），却备份不到真正稀缺的东西。
   替代（10 秒、覆盖 100% 独有内容）：`git stash show -p stash@{i} > _archive/stash-i.patch` ×2，加 `git log --all --pretty=fuller > _archive/git-log.txt`。
2. **`refs/remotes/origin/daily-insight-fix-v2` 会把那些对象继续钉住。** 分支在远端还在 → `git remote prune origin` **不会**删这条跟踪 ref → `git branch -D daily-insight-fix-v2` 白做，这部分垃圾收不回。
   要么显式 `git update-ref -d refs/remotes/origin/daily-insight-fix-v2`（只是跟踪 ref，安全），要么承认这块不回收。
   （对比：`origin/daily-insight-tdd-fix`=a2ea918 **不在**远端分支列表里，prune 能删 ✓。）

另外三处需要修口径：

3. **验收目标"`.git` ≤2G"写错了**：`gc` 是 repack 不是删除，可达内容 13.83 GiB(未压缩)，落点估算 **2.5~4 GiB**。要 <1G 只能靠 §6 的产物落点改造。
4. **"`git push`/`fetch` 传输全灭"这句要降级**：协议层活着（ls-remote），确定死的是历史上带断链的 push。**fetch 未测**（本规格正在测，见 §5）。
5. **`daily-insight-history.html` 不是源码**，别塞进竞态守卫：`build_daily_insight.py` 每场重新生成它，
   `checkout origin/main -- <该文件>` 会先用远端旧版覆盖本场新产物再提交 → 历史页冻死。（`test_daily_insight.py` 也会覆写它，见 HANDOFF 的"本地危险动作"。）

## 3. 本轮已完成的修复：原子推送（用户指令"原子推送修复一下"）

**问题（实测坐实，非假想）**：远端 `update.yml` 的门禁 A2 是 `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`，
**没有 `continue-on-error`（blocking）**；而 `Deploy to Vercel` 步骤**没有 `if:`** → 默认 `success()`。
所以"workflow 上去了、新测试目录没上去"＝ pytest 退出码 4 ＝ **提交与部署一起被跳过**，站点冻住至少一小时。

**修在 `tools/data_api_push.py`**：
- `ci_atomic_deps(push_paths, wf=WF)` —— 推 workflow 时，逐条解析它引用的测试路径，要求每条**要么随本次推送、要么远端已有**；
  本地根本不存在的路径单独报"推上去 A2 必红"。
- `expand_paths()` —— 目录参数自动展开成文件（漏项的根源就是要手数文件），排除 `__pycache__`/`.pyc`。
- `--dry-run` —— 只跑守门 + 原子性检查并列出待推路径，不写远端。
- 两处为可测性必须修的缺陷：**模块级 `sys.exit(main())`**（导入即退出，pytest 收集阶段就崩）与**导入时重挂载 `sys.stdout`**
  （会吞掉 pytest 捕获输出）→ 都收进 `if __name__ == "__main__":`。

**测试**：`tests/tools/test_data_api_push_atomic.py`，7 例，`py -3.11 -m pytest tests/tools/ -q -s --junitxml=…` → **7 passed / 5.8s**。

**变异体逐个验证**（`_mut_atomic.py`，就地改+逐字节还原证明）：

| 变异 | 期望 | 实际 |
|---|---|---|
| M1 检查整体失效（永远返回空） | 必须红 | 红 2/7 ✓ |
| M2 只改提示文案（保留分支） | **必须绿**（防脆） | 红 0/7 ✓ |
| M2b 去掉"本地不存在"整支 | 必须红 | 红 1/7 ✓ |
| M3 取消"同批推送即满足" | 必须红 | 红 1/7 ✓ |
| M4 不再排除 pycache/pyc | 必须红 | 红 1/7 ✓ |
| M5 退回模块级 `sys.exit` | 必须红 | 收集期崩，红 1/1 ✓ |

> M2 一开始是红的 —— 因为测试在断言**中文措辞**而不是行为。已改成只锁"报的是哪条路径"，重跑后 M2 转绿、其余仍红。
> 这就是变异验证的价值：它抓到的是测试的脆，不是实现的错。

## 4. 观察：另一会话的提交会不会被吞/被淹没

方法（可复跑）：逐路径拉远端 blob sha，与"上次已知推送值 / 本地 `git rev-parse <ref>:<path>`"比对。
**23:2x 首次普查结果：9 个关键路径全部在位，无人被吞**：
`build_daily_insight.py 97a08b8389`（R14 批2）、`HANDOFF 2a237c7de6`、`CLAUDE a35cbb7edf`、
`tools/data_api_push 0bf0116d9c`、计划文档 `3c2265d832`、两个 R14 测试 `e11a4d2da2`/`9ba71d00f3`、
`build_rss_aggregator 5015500761`（与本地提交 `5610485` 同 blob ⇒ **RSS 修复已在远端**）、
`tests/rss_source_coverage/test_source_coverage.py ee0dffa084`（远端目录已存在 ⇒ 对方的推送是原子的 ✓）。
历史链线性无冲突：`5610485` 的 parent 就是我的 `f5b80ca`，我那 6 个文档/规则提交仍在主线上。

仍要盯的点：`build_rss_aggregator.py` **在 CI 的 add 清单里却不在守卫行里**（守卫只同步洞察那 3 个文件）
→ 那份修复暴露在"旧检出构建回滚"下。**每次整点构建结束后跑一次普查**（§3 的工具或 `tools/remote_drift_check.py`）。

## 5. 恢复常规 git 流程的路径（按依赖排序，不按"看起来安全"排序）

**用户目标拆开是两件事**：(a) 能走 `git push`；(b) 存储降下来。它们有硬依赖：**谈判式 push 要遍历本地对象图**，
断链 + 6.5G loose 正是历史失败的原因，所以顺序只能是：

| 阶段 | 动作 | 风险 | 收益 | 状态 |
|---|---|---|---|---|
| P0 | 删 `count-objects` 报的 5 个 garbage（`tmp_pack_*` ×2、无 `.pack` 的孤儿 `.idx` ×2、`tmp_obj_*`），**342MB** | 零（git 自己标注的垃圾；先确认 mtime 早于 24h） | 消掉 `Could not read` 的一类来源 | **未执行，待批** |
| P1 | `git fetch origin main` 实测传输 | 低（只写新 pack + 更新跟踪 ref，不碰主线与工作树） | 决定 (a) 能不能要；顺带刷新本地 `origin/main`（现停在 22:16 的 `5b07052`，远端实际已 5 次之后） | **已完成：23.3 秒成功，`5b07052..b866ee7`** |
| P2 | 归档 stash×2 为 patch → `git replace -d 28f33177…` → 删陈旧 ref（**含 §2.2 那条跟踪 ref**）→ `git gc --prune=now` → 恢复 `gc.auto` | 中（长时间独占 `.git/objects`，两会话必须都空闲） | **约 4.8G** | 待批 |
| P3 | 历史归一：本地 main 与远端 main 是**两条并行历史**（Data API 不回写），用 tree-level 方式对齐成一条，之后才谈 `git push` | 中（先 `git tag pre-normalize main` 保可回滚） | 让"推"重新有意义的唯一办法 | 待批 |
| P4 | 产物落点改造（`rss-data-*.js`/`translations.json`/`hot_history.json` 三路 81~82 版是远端 4.41G 的全部来源） | 高（Pages 靠 `rss-data-N.js` 取数，前提未满足不能动） | 止住增长 | **挂起，等"落点"决策** |
| P5 | 远端瘦身（新建干净仓 / `filter-repo`） | 高 | 4.41G→<300MB | 待 P4；另注意换仓有 3 个连带项：`api/refresh.js:42` **把 `repos/Kwei168/starhub/...` 硬编码在代码里**、Pages 是 `legacy/main`（域名要重指）、Vercel 的 `GITHUB_TOKEN` 是按旧仓授权的 PAT（必须重签） |

**明确不做**：不先处理 `refs/replace` 与陈旧 ref 就 `git gc`（把断链带进 repack）；上 git-lfs（免费额度 1GB 存储 / 1GB 月带宽，对每场 192MB 产物不够）。

## 6. 验收清单（含更正后的目标值）

1. `du -sh .git` ≤ **4G**（P2 后），loose 数 < 100 —— **不是原方案的 ≤2G**。
2. `git fsck --connectivity-only` exit 0 且无 `missing`/`broken link`；`for-each-ref refs/replace` 为空。
3. P1 通过标准：`git fetch origin main` 成功且 `refs/remotes/origin/main` 与 `gh api .../commits/main` 一致。
4. P3 之后：`git push origin main` 一次成功（这是"常规 git 流程恢复"的唯一定义，别的都不算）。
5. 每场整点构建后跑一次 §4 的跨会话普查，9 个路径全在位。
6. 若动 P4/P5：浏览器实测 `rss-aggregator.html` 能加载 `rss-data-0/1/2.js`，且 `Deploy to Vercel` 成功（不看步骤绿，看产物时间戳）。

## 7. 回滚

- P0/P2 前：`git tag pre-shrink-<date>` + stash patch 存档；`.git` 整体是目录级复制得动的（E 盘剩 243G，够放一份 8G）。
- P3：`git tag` 记住归一前的本地 main；必要时 `git reset --hard <tag>`（**这一步必须由人确认后再做**）。
- P5：`git clone --mirror` 留旧仓 + 记录 `origin/main` 旧 SHA；旧仓改名只读即天然回滚。

## 8. 待拍板

1. 批 P0（342MB 零风险清理）与 P2（约 4.8G）吗？P2 需要两个会话同时停 5~15 分钟。
2. P1 结果出来后：如果 fetch 可用，是否把 CLAUDE.md 里"传输是死的"降级为"push 需实测、优先仍走 Data API"？
3. P4 的产物落点三选一（孤儿分支覆盖 / 分片且 main 只留最新 / 与 Cloudflare R2 合并决策）——不定这个，P2/P5 清完几周内长回。
