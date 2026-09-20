# 仓库体积与"恢复常规 git 流程"——核实、审查与处置规格

日期：2026-09-20（北京时间 06:00–08:30 一段实测 + 一次对抗审查）
状态：**已执行的部分全部可逆**（只做了隔离与只读测量）；`git gc` / 改指针 / drop stash **一律未做并已叫停**。
上游输入：另一会话的《StarHub 仓库体积（.git 7.4G / 远端 3.86G）处置方案》—— **该文件从未落盘，只活在对话里**，
所以本文件把它的每条主张连同核实结果一起固化，并注明哪些主张已被推翻。

---

## 0. 要回答的三个问题

1. 那些体积数字是不是真的（独立重测，不引用对方口径）；
2. 按原方案执行会不会失败；
3. 用户目标——"**能走常规 git 流程推送 + 把存储降下来**"——的正确顺序是什么。

一句话答案：**体积数字大体属实（4.8G 可回收独立复现），但原方案的因果诊断是错的**：
这个 `.git` 是 **shallow clone** 且**曾被手工删包抹掉约 11k 个对象**，所以"修断链再 gc"没有对象可修；
而传输其实是健康的。要达成目标只有一条路：**重新做一次完整克隆，把本地独有的 60 条提交搬过去**（§7）。

## 1. 实测数字

| 项 | 对方方案 | 我的实测 | 判定 |
|---|---|---|---|
| `.git` 体积 | 7.4G | 清理前 **8.1G** → 隔离垃圾后 **7.8G** | 在涨 |
| 远端仓库 | 3.86G | `.size = 4,644,339 KiB ≈ 4.43 GiB` | 在涨 |
| loose 对象 | 2777 个 | `count-objects`：3127 个 / 6,540,273 KiB（清理后 3194 / 6,652,836） | 略被低估 |
| 可回收垃圾 | "约 4.8G" | 对象总体积 **34.82 GiB(未压缩)**；`--all` 可达 13.83 GiB、**不可达 20.99 GiB（60%）** → 折磁盘 ≈ 4.8 GiB（审查代理独立重算也是 20.99 GiB） | **核心主张成立** |
| gc 相关配置 | 三项被关闭 | `gc.auto 0`、`gc.autodetach false`、`gc.geometricrepack 0`、`core.commitgraph false`、`gc.writecommitgraph false`；`core.autocrlf=true` 来自**系统级**而非仓库级 | 属实 |
| 主线提交数 | 99 | `rev-list --count main` = **143**（会话期间在涨） | 低估 |
| HEAD 巨型产物 | ~210MB | `rss-data-1.js 68.2MB + rss-data-2.js 67.8MB + translations 18.9 + hot_history 9.5 + analysis 3.6 + rss-aggregator.html 3.1 + rss-data-0 0.7`（审查代理按远端 tip 树复核） | 量级对 |
| `rss_history.json` | 已取消跟踪 | 已取消跟踪 ✓（工作树仍有 61MB，历史里 11 版） | 属实 |
| **浅克隆** | **未察觉** | `git rev-parse --is-shallow-repository` → **true**；`.git/shallow` 有 **7** 条，含 `e806aadb`（连 `daily-insight-fix-v2` 的 tip 都是浅边界） | **原方案漏掉的前提** |
| 分块产物是哪一套 | 混用 | 本文件谈的都是 **Pages 用 `<script src="rss-data-N.js">` 加载的那一套**（`rss-aggregator.html:2136` 动态拼 `rss-data-'+i+'.js`，0/1/2 三块都在用，chunk 2 不是死重）；不是 72h 存档那套，也不是洞察向量那套 | 口径已固定 |

不可达对象归类（体积前 60 个，按内容签名）：`rss-data-1.js` 旧版 27 个 / 1.84 GiB、`rss-data-2.js` 9 个 / 0.65 GiB、
`translations.json` 13 个 / 0.76 GiB；另有 **4 个 blob 内容以 `<<<<<<< Updated upstream` 开头**（0.36 GiB）——历史上确实提交/暂存过带冲突标记的产物。

## 2. "我们是不是一直在分支上没合并？"——分叉的真实形状

**不是"在 feature 分支忘了合并"，而是同一个分支名 `main` 被两条独立提交线各写了一遍。**

| 事实 | 实测 |
|---|---|
| 两边分支名 | 都叫 `main` |
| 共同祖先 | `bf1b57132e`，**2026-09-18 21:57** ← 分叉点 |
| 只在本地的提交 | **58 → 60 条**（审查期间另一会话又提交了 `bbb18a1`） |
| 只在远端的提交 | **87 条**（含每小时 `chore: auto update stars`） |
| 双胞胎 | 同信息不同 SHA：本地 `5610485` ↔ 远端 `b866ee7`（RSS 覆盖率修复）、本地 `f5b80ca` ↔ 远端 `5061601`（第7期）、本地 `2a144b0` ↔ 远端 `6f7948f`（CLAUDE 硬规则） |
| **两个 tip 的内容差** | 当时 `git diff --name-status main origin/main` = 24 个文件，全是构建产物 ⇒ **没有"写了没合并的代码"** |

成因两条：① Data API 推送的提交父节点取远端 head、**永不回写本地**；② 本地 `origin/main` 因"以为 fetch 也死了"长期不更新。
⚠ 后来审查指出：只比 tip 会漏判——那一刻我的 spec/tests 尚未落地，`reset --hard` 就会删掉它们；
**所以"内容差=0"必须在推送落地并复查之后才算数**。
另外那 60 条本地独有提交的**提交信息与逐提交 diff 在远端不存在**，指针一动就随 reflog 消失 → §7 的 N2 必须先 `format-patch` 归档。

## 3. 传输健康度：`fetch` 可用，`push` 只是被正常拒绝

```
$ git ls-remote --heads origin      → main=6f7948f90d…, daily-insight-fix-v2=e806aad…   （协议层活着）
$ git fetch origin main             → 5b07052..b866ee7   real 0m23.320s   exit=0
$ git push --dry-run origin main    → ! [rejected] … (fetch first)   （审查代理实测：普通的非快进拒绝）
```
⇒ **历史上"git 传输全灭"的判断不成立**；真正发生的是"本地落后 + 对象查找失败"两件事叠在一起，被误读成协议问题。
`CLAUDE.md` 第 0 节现在写的是"`push`/`fetch` 直连是死的"，**这句必须修订**（待批准，见 §12）。
仍要保留 Data API 的理由只剩一条：**它能绕过"检出早于推送的整点构建"这个回滚风险**（§9）。

## 4. 根因分层（三件事被原方案混成了"断链损坏"）

| 层 | 现象 | 真实原因 | 证据 |
|---|---|---|---|
| 噪音 | `fsck` 刷 12,285 行 | **`.git/objects/pack/multi-pack-index` 陈旧**（mtime 09-14 16:11，而 `pack-94442…` 506MB 是 09-20、`pack-b5cab…` 是 09-19） | 移走 MIDX 后同一命令降到 **74 行**、只剩 1 个真缺陷；8 个 pack 全部 `verify-pack -s` exit 0 |
| 真损失 | `Could not read <oid>` | **有人手工删 `.pack` 留 `.idx`**（孤儿 `.idx` 就是墓碑）：`pack-d946bec2…idx` 记 8,818 个 OID，其中 **8,768 个本地已取不到**；`pack-f6ff87bf…idx` 记 2,451 个，**2,375 个取不到** | 仓库现在总共只剩 **5,937 个对象**（清理前 6,497） |
| 假缺陷 | `missing commit 79dd247` / `broken link from 28f33177` | **浅克隆的切割面**。`git cat-file -p 484e35e`（replace 目标）**没有 parent 行** ⇒ `refs/replace/28f3317→484e35e` 是前人手工打的 graft，用来让 git 别在浅边界上报错；`79dd247` 从未存在于本地任何位置 | `grep -c 28f331770 .git/shallow` = 0（边界清单本身就不全）；`28f33177` 只从 `refs/remotes/origin/daily-insight-tdd-fix` 可达，而 `git remote prune origin --dry-run` 实测就会删掉它 |

⇒ **原方案 L1 的"先修断链才能 gc"没有对象可修**；`gc` 在这份仓库上只能得到"浅历史 + 缺对象"的自洽状态。
⇒ 新增硬规则：**永远不要手删 `.git/objects/pack/*`**；要清就整包走 `git gc`，或删派生文件（`.midx`/`.rev`/孤儿 `.idx`）。
`git fsck` 现在退出码 **2**（唯一缺陷就是上面那条 graft），预计 `prune` + `replace -d` 后归 0，
但会出现 **约 60 条 `dangling commit` + 10 条 `dangling tree` + 1 条 `dangling blob`**（其中有旧 stash：`WIP on main: 1d2a93d…`、`On main: qoder wiki 改动暂存`）—— **那是正常的，不是新故障**。

## 5. 对抗审查（fresh-eyes 子代理）：接受、修正、驳回

审查结论是 **STOP**。逐条重测后：

**接受（改变本文件性质）**
1. 仓库是 shallow clone（§4 第三层）——我此前完全没查，导致 §2C 我写的"MIDX 解释了传输全灭"证据不足；已改成 §3/§4 的分层表述。
2. 手工删包已造成约 11k 对象永久丢失（§4 第二层）——严重性高于体积问题，也是"别再修这个 `.git`"的决定性理由。
3. `reset --hard` 类操作的强制预检四条（§7 末尾），以及"备份要靠 `format-patch`，光 `git tag` 不够"（§2 末）。
4. 隔离件放在 `%LOCALAPPDATA%\Temp`（C 盘，会被清理工具抹掉）等于没备份 → 已搬到 `E:/_git-quarantine-20260920/` 并写 `MANIFEST.txt`。
5. 我的工具里 4 个真 bug（下表），以及 `_mut_atomic.py` 第一版"永远不会失败"（只有 1 个 assert、没有最终裁决与退出码）。

**修正**：`update-ref -d refs/remotes/origin/daily-insight-fix-v2` 该不该做——审查说"删错 ref、什么也释放不了"。
事实是 `refs/heads/daily-insight-fix-v2` 与 `refs/remotes/origin/daily-insight-fix-v2` 都指 `e806aad`，
所以**只删其中一个确实不释放**；而正确动作是 `git remote prune origin` 删掉 tdd-fix 那条（远端已无此分支）。

**驳回（已复核）**：审查说"`reset --hard origin/main` 会删掉我这次新提交的 spec 与 `tests/tools`"。
复查时远端 `main = 37aa23fa` 已含 `tests/tools/test_data_api_push_atomic.py`（blob `81d858d98c`）与规格文件 ⇒ 该具体风险已消。
但其规则成立：**归一前必须先确认推送落地**；且另一会话脏工作树里 `daily-insight.json` 26,776 → 1,333 字节，`reset --hard` 会直接抹掉——这是真危险。

**审查抓到并已修的 4 个工具缺陷**

| # | 缺陷 | 后果 | 修法 | 证明它的变异体 |
|---|---|---|---|---|
| 1 | 顶层出现**两个同名 `def ci_atomic_deps`**（前一个只有 docstring） | 死函数遮蔽、语义误导 | 合并成一个，`wf` 改成必填参数 | M1 |
| 2 | 上传前**无条件 CRLF→LF**，而仓库有 4 个被跟踪 `.png` | 目录展开遇二进制即**静默毁档** | `is_binary_bytes()` 嗅 NUL，二进制原样上传 | M7 |
| 3 | `os.path.exists` 按 **CWD** 解析 | 从别的目录调用就误判"本地不存在" | 一律 `_abs()` 相对仓库根；跨盘符 `relpath` 抛 `ValueError` 时退回绝对路径 | M9 |
| 4 | 远端只判"目录存在" | 远端放一份**过期测试**照样放行 → 门禁仍红 | `remote_matches_local()` 逐文件 `git hash-object` 与远端 blob 比对 | M8 |
| 5 | `--ignore=tests/slow` 的值被当要求项 | **误判红**（本工具自己制造停摆） | 解析前先剥 `--opt=value` | M6 |
| 6 | 通配 / matrix 模板路径无判据 | 要么误红要么漏判 | 不判红，单列 `[?] 需人工确认` 清单 | （反向：M6 同批） |
| 7 | 只认 `update.yml` 一个字符串 | 其他 workflow 引用测试同样会红 | 推送集里**任何** `.github/workflows/*.yml` 都过检查 | — |

## 6. 本轮已执行的处置（全部可逆）

1. 隔离 `count-objects` 自标的 5 个 garbage：`tmp_pack_i3pIYW`(178MB)、`tmp_pack_W3pa18`(155MB)、
   孤儿 `.idx` `pack-d946bec2…`(242KB)、`pack-f6ff87bf…`(68KB)、`objects/5c/tmp_obj_aMnyd8`(8.2MB)
   → `.git` **8.1G → 7.8G**，`count-objects` 报 `garbage: 0 / size-garbage: 0`。
   审查代理另把这 5 个文件**复制**出去跑了校验：两个 `tmp_pack` 都 `pack is corrupted (SHA1 mismatch)`、`tmp_obj` 是 `pack signature mismatch`
   ⇒ **里面没有任何独有价值的数据**，"只是半成品垃圾"这一判断由第三方复核过。
2. 隔离陈旧 `multi-pack-index`（fsck 12,285 → 74 行）。
3. 隔离件搬到 `E:/_git-quarantine-20260920/` + `MANIFEST.txt`（来源、操作、恢复方法）。
4. 全程未动 ref、未动 index、未动工作树；`git status` 与 `rev-parse HEAD` 与操作前一致；`fetch` 复验正常。
5. **叫停**：`git gc --prune=now`、`git replace -d`、删 ref、drop stash、`reset --hard`。

## 7. 达成"常规 git 流程 + 降存储"的路径（替换原方案的 L1/L2/L3）

| 阶段 | 动作 | 风险 | 收益 | 状态 |
|---|---|---|---|---|
| N1 | **完整克隆**：`git clone`（不加 `--depth`）到 `E:/starhub-fresh`；验 `is-shallow-repository=false`、`fsck` exit 0、`rev-list --count` 与远端一致 | 低（纯新增，约 1~2G；E 盘余量 240G+） | 得到可信、非浅、能 push 的仓库 | **下一步，待批** |
| N2 | 搬独有内容：`git format-patch --stdout origin/main..main > E:/_git-quarantine-20260920/local-commits.patch` + `git log --all --pretty=fuller` + 两条 stash 导 patch；在新克隆里 `git am` 只挑远端没有 twin 的那些 | 低（只读旧仓、只写新仓） | 保住 60 条提交的信息与逐提交 diff | 待批 |
| N3 | 切目录：两会话都无未提交内容时，旧目录改名保留、改用新目录；此后 `fetch/push` 全程正常 | 中（要同时停手） | 目标 (a) 达成 | 待 N1/N2 |
| N4 | 旧 `.git` 确认无用后释放（**mv 进隔离区，不 rm**） | 中 | 目标 (b)：本地 −7.8G 量级 | 待 N3 稳定数日 |
| G1 | **远端增长治理**：`rss-data-1.js` 68MB + `rss-data-2.js` 68MB 每小时重写一次，是远端体积唯一来源（历史版本 81~82 版） | 高（Pages 靠这些 script 取数，落点未定不能动） | 止住增长 | **挂起，等你定"产物落点"** |
| G2 | （可选）远端历史重写或换干净仓 | 高 | 4.43G→<300MB | G1 之后才有意义。换仓还有 3 个连带项：`api/refresh.js:42` **把 `repos/Kwei168/starhub/...` 硬编码在代码里**、Pages 是 `legacy/main`（域名要重指）、Vercel 的 `GITHUB_TOKEN` 是按旧仓授权的 PAT（必须重签） |

**任何触碰 `.git` 内部或改指针的动作之前，四条预检全过才动**（审查给的判据）：
① `git status --porcelain` 为空；② `git rev-parse HEAD` 连续 120 秒不变；③ 无 `.git/index.lock` / `.git/gc.lock`；④ Actions 无未完成 run。
任一不满足就中止——`--prune=now` 没有宽限期，它会删掉并发 `git add`/`stash` 刚写下的对象。

**明确不做**：不在旧仓上跑 `git gc --prune=now`；不上 git-lfs（免费额度 1GB 存储 / 1GB 月带宽，对每场 192MB 产物不够）；不再手删 `.git/objects/pack/*`。

## 8. 原子推送（用户指令"原子推送修复一下"）

**要堵的洞（实测）**：远端 `update.yml` 的门禁 A2 = `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`，
**没有 `continue-on-error`（blocking）**；`Deploy to Vercel` 步骤**没有 `if:`** → 默认 `success()`。
⇒ "workflow 上去了、新测试目录没上去" = pytest 退出码 4 = **提交与部署一起被跳过**，站点冻至少一小时。

**落在 `tools/data_api_push.py`**：`ci_atomic_deps(push_paths, wf)`（解析 workflow 里每条 `pytest` 引用的路径，要求同批推送或远端逐文件一致）、
`expand_paths()`（目录自动展开）、`remote_matches_local()`、`is_binary_bytes()`、`--dry-run`，
并把模块级 `sys.exit(main())` 与 `sys.stdout` 重挂载收进 `if __name__ == "__main__":`（否则 pytest 收集阶段就崩 / 吞捕获输出）。

**测试与变异验证**：`tests/tools/test_data_api_push_atomic.py` **12 passed / 49.6s**（CI 同构 `-s --junitxml`，本地 3.11.9 对 CI `python-version: "3.11"`）。
`_mut_atomic.py` 跑 **10 个变异体，0 个不符合期望，每个都逐字节还原证明 True**，且 harness 现在会在不符时返回非 0：

| 变异 | 期望 | 实际 |
|---|---|---|
| M1 检查整体失效 | 红 | 红 4/12 ✓ |
| M2 只改提示文案 | **绿**（防脆） | 红 0/12 ✓ |
| M2b 去掉"本地不存在"支 | 红 | 红 1/12 ✓ |
| M3 取消"同批即满足" | 红 | 红 1/12 ✓ |
| M4 不排除 pycache/pyc | 红 | 红 1/12 ✓ |
| M5 退回模块级 `sys.exit` | 红 | 收集期崩 ✓ |
| M6 不再剥离 `--ignore=` | 红 | 红 1/12 ✓ |
| M7 二进制识别恒假 | 红 | 红 1/12 ✓ |
| M8 远端只判存在 | 红 | 红 1/12 ✓ |
| M9 路径退回 CWD 相对 | 红 | 红 1/12 ✓ |

> M6 是这一轮唯一"我自己写的修复反噬"：`--ignore=tests/slow` 的值被当要求项 → **守门工具自己制造停摆**。
> 它是我自己的新用例抓到的，不是审查抓的——落盘价值在这里。

## 9. 观察：另一会话的提交会不会被吞 / 淹没

方法（可复跑）：逐路径取远端 blob sha，与"上次已知推送值 / 本地 `git rev-parse <ref>:<path>`"比对。
**23:2x 首次普查：9 个关键路径全在位，无人被吞** ——
`build_daily_insight.py 97a08b8389`(R14 批2)、`HANDOFF 2a237c7de6`、`CLAUDE a35cbb7edf`、`tools/data_api_push 0bf0116d9c`、
计划文档 `3c2265d832`、两个 R14 测试 `e11a4d2da2`/`9ba71d00f3`、`build_rss_aggregator 5015500761`(=本地 `5610485` 同 blob ⇒ RSS 修复已在远端)、
`tests/rss_source_coverage/test_source_coverage.py ee0dffa084`(⇒ 对方推送是原子的 ✓)。

结构性漏口仍在：CI 的竞态守卫只同步洞察那 3 个文件，**`build_rss_aggregator.py` 在 add 清单里却不在守卫里**，
且吞并入口是 `push 失败 → reset --soft 留着旧 index`（**泄漏范围是整棵树，不是清单内源码**）—— 详见计划文档 §11.3/§11.4。
**每场整点构建结束后跑一次上面的普查**，这是目前唯一能证明"没被回滚"的手段。

## 10. 验收清单

1. N1 后：新克隆 `is-shallow-repository=false`、`git fsck` **exit 0**、`rev-list --count main` 与远端一致。
2. N2 后：`local-commits.patch` 里的每条提交都能在新仓 `git log` 找到，或明确判定"远端已有 twin 不必搬"。
3. N3 后：`git push origin main` **一次成功**（这是"常规 git 流程恢复"的唯一定义）。
4. 旧 `.git` 释放后：`du -sh` 合计 ≤ 2G（**新仓 1~2G + 旧目录改名保留**；不要在旧仓上追求 ≤2G——审查也确认原方案的 ≤2G 目标写错了，`gc` 是 repack 不是删除，可达内容 13.83 GiB 未压缩）。
5. 每场整点构建后 §9 普查全在位。
6. 若做 G1/G2：浏览器实测 `rss-aggregator.html` 能加载 `rss-data-0/1/2.js` 且 `Deploy to Vercel` 成功（看产物时间戳，不看步骤绿）。

## 11. 回滚

- 隔离件：`E:/_git-quarantine-20260920/`（含 MANIFEST），移回原路径即完全还原。
- N1/N2 全程不动旧仓 ⇒ 天然可回退。
- N3：旧目录改名保留；N4 之前不发生任何删除。
- 若将来做任何指针操作：先 `git tag pre-normalize main` **且** `format-patch` 归档（tag 挡不住 reflog 过期导致的对象回收）。

## 12. 待拍板

1. **N1**：批不批我现在跑一次完整克隆到 `E:/starhub-fresh`（纯新增目录，约 1~2G，风险最低、收益最大的一步）。
2. **CLAUDE.md 修订**：把"push/fetch 直连是死的"改成"`fetch/push` 实测可用；Data API 仍用于规避整点构建回滚；**禁止手删 `.git/objects/pack/*`**"。
3. **G1 产物落点**三选一（孤儿分支覆盖 / 分片且 main 只留最新 / 与 Cloudflare R2 合并决策）——不定这个，新仓也会在几周内长回 4G。
4. 另一会话的 `tests/rss_source_coverage/` 是 **blocking 门禁 + 依赖时序**的新用例，是否要按审查建议先压力复跑或挪到 advisory（避免偶发红连带冻部署）。
