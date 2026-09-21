# RSS 源覆盖率修复 —— 已完成内容与待推送状态

> **状态已变更（2026-09-21 复盘同步）**：本文原写"全部落在本地提交、尚未推送"，
> **现已全部推达远端**，本文其余部分按历史记录保留，读数以本段为准。
>
> - 第 2 节列的 7 个文件都已在远端：`build_rss_aggregator.py` blob `db7bbaac0b`、
>   `api/rss.js` `1d92912893`、`rss_sources.json` `4fc7b70abf`、
>   `test_history_bounds.py` `ef20f2e8b6`、`test_source_coverage.py` `745d0e8413`，
>   以及当时"从未落地"的三个覆盖率测试 `test_fetch_size.py` `c13a114122` /
>   `test_per_source_ua.py` `6e5fa864ed` / `test_source_list_health.py` `cb16582330`。
>   推远端前重复 URL 已归零，第 4 节担心的"单推测试会打红 A2"没有发生。
> - 第 4 节的合并纪律（**谁后推谁负责合并、清单只推可重放补丁不推整文件**）是本轮真正
>   救命的两条，已另存进项目记忆，不随本文过期。
> - 源数量：本文写 985/1005，生产实况 **970**（15:13:49 场 `sources_total=970`）。
> - **第 6 节的三处 JS 缺口只补了一半，仍开着**：`api/rss.js` 的 per-source UA 与体积上限
>   未动；`date_fallback` 虽在 `:255-259` 算出来了，却在五处出网压缩映射
>   （`:572-579`、`:735-742`、`:815-818`、`:867-871`、`:878-881`）被丢掉 ——
>   线上 `/api/rss` 条目键实测只有 `{d,s,t,t_zh,u}`。详见留存台账 §23.3。

记录时间：2026-09-20 09:55（北京时间）。
用途：修复内容已全部落在**本地提交**、**尚未推送**。等并行的「72 小时外 RSS 留存」改造完成后，
按本文第 4 节的顺序复验再推。

## 1. 查清的四条根因（"有数据源"从 968 掉到 776）

| # | 根因 | 位置 | 影响 |
|---|---|---|---|
| 1 | 标题去重把 `datetime` 当字符串调 `.replace("Z",…)` → `TypeError`，`except (ValueError, AttributeError)` 抓不到，逃到 `_worker` 的裸 `except` 被静默吞成「0 条」 | `build_rss_aggregator.py` `_dedup_source_items` | 84 个源归零、日志零痕迹 |
| 2 | 域名熔断把「HTTP 200 但 feed 0 条」计为域名失败，3 次即连坐同域剩余源；提交顺序固定 ⇒ 尾部源永远轮不到 | 同上 `_worker` | 51 个 `api.xgo.ing` 源被尝试 0.00 次/场 × 18 场 |
| 3 | RSS 1.0/RDF 用默认命名空间，`findtext("title")` 取不到 → `if not title` 丢光每条 | `_parse_rss_item` | DW/Nature/Science 等 8 源（上游 37~137 条 → 我方 0） |
| 4 | `_fetch_url` 的 `r.read(5000000)` 把大 feed 切在 CDATA 中间 → 报「解析失败」 | `_fetch_url` | 4 个源（真实 5.5/7.4/7.8/10.5MB）被判成上游坏源 |

时间线：第 1 条由 2026-09-16 05:17~05:25 UTC 的三个「卡片去重」提交引入，9-16 14:36（北京）那场构建起生效。
线上验证（run 35474899902，head `b866ee73c5`）：**有数据源 776 → 950**，域熔断连坐 144 → 4，新增 `error` 状态 39 个。

## 2. 本地已提交、待推送的两个提交

- `bcc385c` 第 4 条根因（5MB→32MB）+ per-source `ua` 覆盖 + 换源删死源（1005→986）
- `42809b8` 按对抗审查收紧：**上限 32MB 收到 12MB**、MongoDB 由换址改为删除（985）、新增源清单数量护栏

待推送文件（7 个）：

```
build_rss_aggregator.py
rss_sources.json                                        1005 -> 985
tests/rss_history/test_source_selection.py              仅去掉写死的「1005」
tests/rss_source_coverage/test_source_coverage.py       stub 跟随 _fetch_url 新签名
tests/rss_source_coverage/test_fetch_size.py            新
tests/rss_source_coverage/test_per_source_ua.py         新
tests/rss_source_coverage/test_source_list_health.py    新
```

## 3. 本地验证结论（推送前状态）

- 门禁 A2 等价命令 `pytest tests/rss_history/ tests/rss_source_coverage/ -q -s` 全绿（本次改动 33 项）
- 变异体：13 个全部变红（含「上限压回 5MB」「去掉命名空间回退」「空 feed 重新计入熔断」
  「恢复静默吞异常」「naive→UTC 归一被删」「无日期一律保留」「抽掉 wechat2rss 整组」等）
- 换进去的地址逐条实取得到条目数：Grafana 10、LangChain 30、RFI 中文 30、
  HF Daily Papers 24、日经 28、TIANYU2FM 15、Engadget（curl UA）20
- `rss_sources.json` 改动面核对：976 条逐字段未动、顺序不变、JSON 重序列化与磁盘字节一致
- **一处存疑保留**：审查报 Medium 镜像 6/6 返回 404，我本机 12/12 成功（200/10 条）。
  因不是 MongoDB 官方域、且保留 `mongodb_blog_403` 这个 key 会让按 link 去重的存档混域，
  已改为删除而非换址。

## 4. 推送时的复验顺序（不可跳）

**基线归属**：并行会话以「已推远端的我的版本」为基线改 `build_rss_aggregator.py` 与清单，
所以我必须反向以他的版本为基线重贴我的改动 —— 谁后推谁负责合并，绝不能整文件覆盖。

1. 确认他已完成并推达：`git fetch` 后比对 `origin/main` 的 blob 是否已不等于我的基线
   （`python tools/rss_coverage_prepush_check.py`，它逐文件比「远端 == 我的基线」；
   **报不一致就是他已经推了**，走第 2 步；全 OK 则可直接推）。
2. 取**远端版本**的 `build_rss_aggregator.py` 落到工作区（前提：他本地对该文件无未提交改动，
   先 `git status` 确认），再把我的 4 处改动重贴上去 —— 增量只有 46 行 diff，
   即 `git diff bcc385c~1 42809b8 -- build_rss_aggregator.py`：
   `MAX_FEED_BYTES = 12MB` 常量、`r.read(MAX_FEED_BYTES)`、`_fetch_url(..., ua=None)`
   与 UA 覆盖、`_fetch_rss` 传 `ua=source.get("ua")`。
3. 清单**不推文件、重放补丁**：`python tools/rss_source_list_patch.py --apply`。
   它只声明「删哪些 key / 改哪些 url / 补哪条」，在任何版本的清单上都能重放；
   已验证对原始 1005 清单重放的输出与我当前文件逐字节相同（155269 字节），
   对已打过的清单幂等（0 动作）。若他增删过源，重放会照常保留他的改动。
4. 跑门禁：`python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`，
   并重跑变异体确认 13 项仍全部变红。
5. `python tools/data_api_push.py --wait-window --msg-file <文件> <7 个路径>`
6. `python tools/remote_drift_check.py <同 7 路径>`，要求「内容不同=0」
7. 等下一场构建，读远端 `build_logs/YYYY-MM-DD.jsonl` 统计有数据源、`duration_s`、
   `error/empty/domain_broken` 分布。


## 5. 第二批对抗审查的处置（逐条复验，不照单全收）

| 审查意见 | 我的复验 | 处置 |
|---|---|---|
| P0 `test_source_coverage.py:104` 的 `boom()` 没跟 `ua` 参数 → 该测试实际在验"我们自己签名对不上"，网络路径全坏也照样绿 | 确认，同一文件 `:134` 改了、`:104` 漏了 | **已修**：补 `ua=None`，并新增"日志里必须出现注入的错误串"断言，让签名漂移无法假绿 |
| P1 `_fetch_url` 默认 `timeout` 由 `FETCH_TIMEOUT` 变 `None` = 永久阻塞，零收益留坑 | 确认 | **已还原**为 `timeout=FETCH_TIMEOUT` |
| P1 `MAX_FEED_BYTES` 无守卫（调成 6MB 全绿）；且我注释里的内存因果讲错了（内存由并发度决定，不由源数决定） | 确认；实测 12.2MB feed 峰值 ≈71MB（原文 5.8 倍），并发 12 ≈850MB，我原估的 144MB 低了一个量级 | **已补** `test_cap_clears_the_largest_feed_we_know_is_live`（6MB 变异体下确实变红）；注释按实测改写 |
| P1 第 4 条根因表述不完整：`:2036` 早有 unclosed CDATA 回退，"截断→0 条"只在回退也失败时成立 | 认同，回退对含裸 `<`/`&` 的正文无效 | **改述**为"截断 + 回退失效"双条件；回退本身的加固列为后续项 |
| P1 建议撤回 `yikai 的摸鱼笔记`（CI 里 2/5 是 `domain_broken`，非 feed not found） | 直连探针 5/5 `HTTP 500 feed not found`，与另外五条完全一致；审查用的是间接证据 | **不撤回**，删除保留 |
| P1 CISA/AP News/FreeBuf 的删除"证据类型不对"：旧日志里是 `empty`，而 `empty` 分不清真没条目与解析不出 | 认同证据类型偏弱；但旧日志的 `empty` 也否证不了上游不可用 | **暂保留删除**，推送后以新 `error/empty` 口径复测；若 CI 侧确认是解析缺口则回补 |
| P2 `bb:True`（`'bestblogs.dev' in url`）会随 HF Daily Papers / 日经 / TIANYU2FM 换址而新命中，进而进前端 | 未复核其前端后果 | 记为**待查**，推送后单独验 |
| P2 源数量下限 300/140/50 把单一供应商依赖写成不可改的地板 | 认同这是"防整组误删"的探测器、不是质量目标 | 保留但在注释里点明用途 |

## 6. 尚未处理的已知分歧（需决策，不悄悄留着）

`api/rss.js` 是 `/api/rss` 实时回退路径，自己有一份抓取与去重实现，本轮 Python 侧的修复**不会自动同步过去**：

1. `api/rss.js:13` UA 写死 `starhub-rss-aggregator/1.0`，无 per-source 覆盖 → 按 UA 拦的源在这里仍 403；
2. 无 feed 体积上限（`res.text()` 全量读）；
3. `api/rss.js:427` 起的标题去重在**日期取不到时直接丢条目**，而 Python 侧现已改成"标题+摘要都相同才折叠" —— 两边口径不一致。

缓解事实：按既定快照机制，`/api/rss` 实时抓取只覆盖 T1 源，本轮受影响的多为 t2/t3。
是否要把这三处也同步到 JS，属跨运行时的独立改动，且并行会话正开着这个仓库，建议由用户定优先级。


## 7. 提醒并行会话的一件事

`tests/rss_history/test_cache_quota.py` 目前是**未跟踪的 RED 测试**（尚未推远端）。
`tests/rss_history/` 是**门禁 A2（blocking，无 `continue-on-error`）**的目录，而
`Deploy to Vercel` 步骤没有 `if:`（默认 `success()`）。也就是说：这个 RED 测试一旦被推进
远端 main，A2 会红 → 不提交、不部署 → 站点每小时冻一次。若要先落测试再补实现，
需要把该文件临时移出 A2 目录，或给那次提交配实现。
