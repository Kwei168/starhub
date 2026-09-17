# 2026-09-13 RSS 聚合器源治理与扩展

## 一、分类合并（继承前次会话）
- `blog` → `dev`（开发者）
- `security` → `tech`（科技资讯）
- `research` → `ai`（AI 日报）
- 移除 `youtube` 分类（124 个 YouTube 源全部删除）
- 前后端 `CAT_LABELS` / `CAT_ORDER` 同步更新为 8 分类

## 二、失败源清理
| 源 | 原因 | 操作 |
|---|---|---|
| 德国之声 DW_18 | 8 次构建全部失败 | 移除 |
| V2EX_1 | 平均仅 2 篇/次，产出极低 | 移除 |
| Engadget_4 | 203 次构建全部失败 | 移除 |

## 三、T1 跳过机制审计与修复

### 问题
T1 源在增量构建中被 `skipped_t1` 跳过（96.1% 跳过率），导致"假性低产出"。实际失败数为 0，源完全健康。

### 修复
18 个 0 失败、稳定产出的 T1 源降为 T2，每次增量构建都实际抓取：

| 源 | 分类 | 平均产出 |
|---|---|---|
| AGI Hunt | ai | 30 篇 |
| Hacker News AI | ai | 20 篇 |
| AI Hot 7天公开池 | ai | 30 篇 |
| 虎嗅 | cn_tech | 20 篇 |
| IT之家 | cn_tech | 30 篇 |
| 钛媒体 | cn_tech | 19 篇 |
| cnBeta | cn_tech | 25 篇 |
| V2EX技术/全站/创意/好玩 | dev | 30 篇 |
| NodeSeek | dev | 20 篇 |
| Hacker News 最新 | dev | 20 篇 |
| 澎湃新闻 | news | 18 篇 |
| 人民网 | news | 26 篇 |
| CNN | news | 30 篇 |
| 新华社 | news | 30 篇 |
| NHK World | news | 30 篇 |

**保留 T1 的 6 个源**（有少量实际失败，保留 T1 合理）：arXiv AI/ML/NLP ×3、hackernews_6、v2ex_new_51、hn_show_58

## 四、国际主流媒体添加

### 来源
- awesome-rss-feeds 仓库调研（DW 有 RSS，半岛不在列表中）
- 用户指定添加国际主流知名媒体

### 新增 9 个国际源（T3，等数据出来再调 Tier）
| key | name | 分类 | URL |
|---|---|---|---|
| deutsche_welle_776 | Deutsche Welle | news | rss.dw.com/rdf/rss-en-all |
| dw_chinese_777 | DW 中文 | news | rss.dw.com/rdf/rss-chi-all |
| france24_778 | France 24 | news | france24.com/en/rss |
| france24_zh_779 | France 24 中文 | news | france24.com/zh/rss |
| ap_news_780 | AP News | news | apnews.com/hub/world-news/feed |
| cnn_intl_781 | CNN International | news | rss.cnn.com/rss/edition.rss |
| economist_782 | The Economist | news | economist.com/latest/rss.xml |
| der_spiegel_783 | Der Spiegel | news | spiegel.de/schlagzeilen/index.rss |
| le_monde_784 | Le Monde | news | lemonde.fr/rss/une.xml |

**翻译覆盖**：英文源自动翻译；德文（Der Spiegel）、法文（Le Monde）通过 Google `sl=auto` 自动检测翻译；中文源（DW 中文、France 24 中文）自动跳过翻译。

## 五、OPML 导入（feeds.opml）

### 来源
`c:\Users\40832\Downloads\feeds.opml` — Awesome RSSHub Routes 精选订阅源（100 条目）

### 结果
- 83 个已存在（去重跳过）
- **新增 17 个**（T3）

| 分类 | 新增数 | 源 |
|---|---|---|
| dev | 16 | Smashing Magazine, A List Apart, Codrops, CSS-Tricks, Astro, Svelte, Nuxt, Tailwind, Dev.to, Chrome Dev, Dribbble, Product Hunt, React, Vue, Go, Swift |
| tech | 1 | Google Security Blog |

## 六、当前状态

| 指标 | 数值 |
|---|---|
| 总源数 | 1014 |
| T1 | 6 |
| T2 | 207 |
| T3 | 801 |
| 分类数 | 8（wechat, ai, tech, cn_tech, dev, news, twitter, podcast） |
| 不可信信源（bad_date） | 344（主要为 wechat 公众号） |

## 七、待观察
- 新增 26 个源（9 国际 + 17 OPML）的抓取成功率和产出质量，后续根据数据调整 Tier
- 构建耗时：1014 源全量构建约 10+ 分钟，增量构建约 5-8 分钟
