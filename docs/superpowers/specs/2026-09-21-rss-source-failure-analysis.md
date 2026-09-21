# RSS 信源失效分析（2026-09-21，基于生产构建日志）

## 0. 证据来源与口径（先说清能证什么、不能证什么）

| 项 | 值 |
|---|---|
| 数据源 | `origin/main:build_logs/2026-09-15.jsonl` … `2026-09-21.jsonl` |
| 覆盖构建 | **195 场**（含 mode=full / mode=incremental） |
| 统计到的源 | 1020 个 key（清单 998 + 窗口内被删/改名的旧 key） |
| 逐场引用 | `per_source[] = {key, name, cat, tier, status, items}`，最新一条完整记录 ts=2026-09-21T11:13:48+08:00（run 35556022105） |
| 状态码来源 | `gh run view 35558326597 --log` 的 stdout/stderr 文本（2930 行） |
| 分析脚本 | `_scratch/_analyze_failures.py`（窗口天数可传参），明细 `_scratch/_source_failure_report.txt` |

三条限制，避免把这份报告读成它能说而它不能说的东西：

1. **jsonl 不记 HTTP 状态码、不记重试次数、不记排队时长**。`status` 只有 `ok / error / empty` 三值
   （`build_rss_aggregator.py:8092-8096`）。所以下面所有 403/429/404/500/410/405/超时的归属，
   来自 run 文本日志的 `[RSS聚合] <源名> 拉取失败: HTTP Error <code>` 这类行；
   文本日志只保留**单场**，跨场统计不足，标注为「未命中」的并不等于没问题，只是这一场没捞到。
2. **`error` 计数在多数源上恰好是 30/195**，且 28 个无数据源全都精确等于 30 —— 这个整齐的程度
   说明它是**代码分界**（`error` 与 `empty` 拆开记是较近才加的口径），不是这些源的行为突变。
   本报告按「30 场里有多少比例是 error」而不是「30」来读。
3. 「长期无数据」用的是 `items>0` 的构建数为 0，`items` 是**当场原始抓取条数**，
   与 72h 闸门后的出厂条数无关，因此这一类里不含「抓到了但全被时间窗清掉」的源。

## 1. 结论摘要

| 类别 | 源数 | 占比（998 源） |
|---|---|---|
| 一、长期无数据（195 场 items 恒为 0） | **28** | 2.8% |
| 二、有 error 记录（拿到过数据但本场失败） | 83 | 8.3% |
| 三、整窗口未被尝试（缺席 per_source） | **0** | 0% |
| 四、清单内但已随 09-21 批次删除/改址 | 7 + 2 | —— |

第 3 类为 0 是本次最重要的否证：**没有源因并发或熔断被跳过**。域熔断只在
`hard_fail/crashed` 时计数（`build_rss_aggregator.py:8085-8090` 的注释即为此前修的坑），
且当次抓取全部源都进 `_to_fetch`，所以「排到一半被丢掉」这种失效当前不存在。

## 2. 一、长期无数据源（28 个，全量列出）

「最近一次尝试时间」= 该源最后一次出现在 per_source 的构建 ts（= 11:13:48 +08:00，全场都被尝试过）。
建议列里 D = 删除，U = 换地址，P = 降 T4/摘出抓取。

| Key | 名称 | 细分原因（证据） | 建议 |
|---|---|---|---|
| halfrost_25 | Halfrost | error 30/195 + empty 165；文本日志未命中 | 现场重抓判定，倾向 P |
| linuxdo_latest_59 | LinuxDo 最新话题 | **HTTP 403**（反爬） | U（换官方/镜像）或 D |
| linuxdo_top_60 | LinuxDo 热门话题 | **HTTP 403** | 同上 |
| linuxdo_posts_61 | LinuxDo 最新帖子 | **HTTP 403** | 同上 |
| tianyu2fm_—_对谈未知领域_13 | TIANYU2FM | error 30/195，未命中 | 现场重抓，倾向 P |
| grafana_labs_382 | Grafana Labs | **HTTP 404**（旧址失效） | U（已在 09-20 补丁 URL_FIX 里，未推远端） |
| langchain_blog_378 | LangChain Blog | error，未命中；09-20 补丁已给新址 | U（同上，待推） |
| showmeai研究中心_412 | ShowMeAI研究中心 | **HTTP 500**（wechat2rss 桥故障） | D |
| llamaindex_blog_416 | LlamaIndex Blog | **HTTP 404**（官方 RSS 已下线） | D |
| 青哥谈ai_420 | 青哥谈AI | error 13/195（桥接不稳定） | D |
| ai_musings_by_mu_421 | AI Musings by Mu | **HTTP 403** | P |
| groq_423 | Groq | empty 195/195，从未出过条目 | D |
| elevate_430 | Elevate | **HTTP 403** | P |
| firecrawl_blog_425 | FireCrawl Blog | empty 195/195（桥接恒 0 条） | D |
| reuters_world_595 | Reuters World | **HTTP 404**（reutersagency.com 已废弃） | D |
| 开源服务指南_413 | 开源服务指南 | **HTTP 500**（wechat2rss） | D |
| hugging_face_414 | Hugging Face | **HTTP 500**（桥接 feed not found） | D |
| thoughtworks洞见_419 | Thoughtworks洞见 | error 19/195（桥接不稳定） | D |
| yikai_的摸鱼笔记_427 | yikai 的摸鱼笔记 | 最近状态 **domain_broken**（wechat2rss 域被熔断） | D |
| cisa_659 | CISA | **HTTP 403**（Akamai 拒 .xml） | D |
| engadget_667 | Engadget | **HTTP 403**（CloudFront 按 UA 拦；09-20 补丁给过 curl UA） | U 或 P |
| freebuf_网络安全行业门户_660 | FreeBuf | **HTTP 405**（WAF 滑块） | D |
| 拾月的博客_693 | 拾月的博客 | empty 195/195 | P |
| 安全客_664 | 安全客 | empty 195/195 | P |
| ap_news_780 | AP News | **HTTP 403**（Cloudflare 全站挑战） | D |
| france24_zh_779 | France 24 中文 | **HTTP 404**（feed 不存在） | D（09-20 补丁以 RFI 中文顶替） |
| washington_post_world_768 | Washington Post World | **超时** ×N | P |
| 謝懿shine_759 | 謝懿Shine | 超时；域名停放页 | D |

**这一类的构成很重要**：28 个里有 **16 个已经写在 `tools/rss_source_list_patch.py` 的删除声明里**
（Codrops/Reuters/謝懿/FreeBuf/AP News/CISA/LlamaIndex/MongoDB/FireCrawl/Groq/HuggingFace/
ShowMeAI/Thoughtworks/yikai/开源服务指南/青哥谈AI），外加 grafana、langchain、engadget、france24
四条改址/改 UA 声明 —— 但那个补丁**从未推到远端**（远端清单 11:00 前仍是未打补丁的 1005 条，
`tools/` 目录在远端根本不存在）。所以这不是"没诊断出来"，是**诊断结论没落地**。
本次日志分析是一条独立的、比当初判定更新（09-15..09-21，195 场）的复证。

## 3. 二、上游限流类（429，与"长期无数据"不重叠的那批）

reddit 全家：`reddit_artificial_105`、`reddit_selfhosted_102`、`reddit_webdev_101`、
`reddit_programming_100`、`reddit_locallama_104` —— 文本日志均为 **HTTP 429**，
error 场数 24~30 / 195。**这就是用户点名的"上游速率限制"，且是唯一成规模的一类。**
特征：不是全死，是**间歇失败**（error 占约 13%~15% 的场），其余场正常出条目，
所以它们不在第 2 节里。

建议（不改架构的最小改）：
- 对 `www.reddit.com` 单独收紧域级并发（现为全局 2）并对 429 走**指数退避 + 本域冷却**，
  而不是按普通 error 立即重试；
- 或者把这 5 个源改用 `old.reddit.com/.rss`（同一份内容，限流阈值不同）——
  需要现场实测后才写进补丁，本报告不预判。

## 4. 三、其他系统性瓶颈（逐条可核）

| 现象 | 证据 | 判断 |
|---|---|---|
| 翻译服务降级 | 每场 `trans_fail` / `trans_google` / `trans_mymemory` / `trans_cache_hit` 字段（11:13 那场有值） | 翻译池 max_workers=6，与抓取池分离，**不阻塞抓取**；未见因翻译导致源失败 |
| 网络超时 | washington_post_world_768、謝懿shine_759、microsoft_azure_blog_380 文本日志「timed out」 | 属单源问题，非全局；`FETCH_TIMEOUT` 为单请求超时，不放大 |
| 域名熔断 | yikai_的摸鱼笔记_427 最近状态 `domain_broken` | 熔断只影响同域（wechat2rss）未成功过的源；已在 8085-8090 注释里改成语义收窄版 |
| 并发排队 | 全局池 12（`:8102`）、域级信号量 2（`:8054`） | **无丢请求证据**：per_source 缺席源数 = 0；998 源 / 12 worker 的排队只影响总时长（实测 duration_s 274.9~333.0 s） |
| HF Daily Papers / 日经等 RSSHub 路由 | hf_daily_papers_803 error 9/149；nikkei_rsshub_802 error 13/147 | 实例不稳定；日经已随 09-21 批次删除，HF 保留但建议换 bestblogs 实例（补丁里已有） |

## 5. 建议的落地顺序

1. **把 09-20 的源清单补丁重放落地**（scope=all）：一次清掉 16 个已复证的死源 + 4 个改址，
   预计抓取耗时下降、"有数据源"数上升。前置：远端清单里那条重复 URL（xiaoyuzhou）会打红
   `test_no_duplicate_keys_or_urls`，必须与三个未落地的覆盖率测试同批推，或不推那个文件。
2. **reddit 5 源加 429 退避**（第 3 节），这是唯一成规模的限流类。
3. 剩 4 个未命中原因的无数据源（halfrost_25、tianyu2fm、langchain_blog_378、虹线_697 等）
   做一次现场重抓，把结论补进本报告，不猜。
4. jsonl 建议加一层可归因字段（每源最后一次失败的状态码与异常摘要）。当前所有状态码都只活在
   会被清理的 run 文本日志里，**这次分析能做的归因，下次就做不了了**。

## 6. 落地后的更正与追补（2026-09-21 复盘同步）

本文第 2 节的 28 条清单是按 195 场窗口（截至 11:13:48）出的快照，**作为当时的证据仍然成立**，
但落地后状态已变，按行号逐项交代，避免下一个人照表再删一遍：

| 本文的建议 | 实际处置 | 依据 |
|---|---|---|
| `linuxdo_latest_59` / `top_60` / `posts_61`（403）U 或 D | **已删**（走 `DEAD_DELETE_KEYS`，998→972 那一批） | 全站 403 现场重测复现 |
| `halfrost_25` / `tianyu2fm_—_对谈未知领域_13` "现场重抓，倾向 P" | **已删**（重抓实测为证书硬失败，不是不稳定） | 同上批次 |
| `拾月的博客_693` | **已删**（上游空 feed） | 同上批次 |
| `grafana_labs_382` / `langchain_blog_378` "U，未推远端" | **已推远端**（改址随覆盖率批一起落地，不再有"待推"状态） | blob 核对，见留存台账 §23 |
| `cisa_659` / `engadget_667` / `freebuf_网络安全行业门户_660` / `ap_news_780` / `france24_zh_779` | 已删/已换址（`france24_zh_779` 由 `rfi_cn_779` 顶替） | 09-21 四批清单重放 |
| `cnn_intl_781` / `CNN_16`（本文未列，窗口内 items 早为 0） | **已删**（2023-04 起停更），972→970 | commit `7f4a80d` |

### 6.1 新增第五种成因：上游证书过期（本文第 2 节把它记成了"日志未命中"）

`轶哥博客_20`（`https://www.wyr.me/rss.xml`）与 `虹线_697`（`https://1q43.blog/feed`）
在生产日志里的失败是 `SSL: CERTIFICATE_VERIFY_FAILED: certificate has expired`。
本机复核与 CI 完全一致：**默认信任库握手失败，跳过校验后两者都 HTTP 200 且含条目**。

所以它们既不是"上游死了"也不是"我方解析缺口"，而是第三种：内容活着、TLS 链过期。
删除会少两个入口，放宽校验等于开 MITM 面 —— **两类处置都未执行，等用户定夺**（任务 #31）。
本文原有的四桶（长期无数据 / 限流 / 域熔断 / 系统性瓶颈）装不下这一类，故单列。

### 6.2 生产实况（15:13:49 场，run 35570914414）

```
sources_total=970  sources_fetched=951  sources_with_data=951  sources_failed=19
per_source 状态 = {ok:951, rate_limited:6, error:12, empty:1}
items_over_hard_h=0  history_expired=62  duration_s=332.5
```

第 1 节那条最重要的否证**仍然成立**：清单内未被尝试的源数 = 0，
即没有任何源因并发度（全局 12 / 单域 2）或域熔断被跳过。
`rate_limited` 这一态是 09-21 之后才有的第四态（reddit 系 429 走它，见 §21/§22），
本文第 3 节写的"429 记为 error"已过期。
