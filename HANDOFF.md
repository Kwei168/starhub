# StarHub 项目移交文档

> 最后更新：2026-09-18（同步每日深度洞察管线 build_daily_insight.py、RAGAS 评估-修正闭环、Agnes 多 key 轮询、RSS 快照出仓等重大变更；手册基线为 `e3c0313`，其后 25 个实质提交已全部核对。同日另完成一轮修复：Phase 2 prompt 语法与接地约束、6 个 Agnes 调用点 key 池统一、`update.yml` 两级质量门禁、被 SyntaxError 掩盖的 4 处失效测试，详见 §8.12 修改守则与 §8.14）

## 一、项目一句话

**Kwei168 的 GitHub Star 收藏台**——自动拉取 starred repos，智能分类、翻译描述、生成静态单页站；LlamaIndex 语义洞察引擎 + 每日深度洞察 RAG 管线（FAISS+BM25 混合检索、RAGAS 评估-修正闭环、破茧栏）驱动主题聚类与深度洞察；1005 RSS 源三层分级 + 多引擎翻译分流链（Agnes → Zen → GTX）+ Agnes 多 key 轮询；GitHub Pages 是 RSS 用户实际访问入口，Vercel 承载 Serverless API 与部署产物。

- 用户访问地址：https://kwei168.github.io/starhub/（GitHub Pages，国内可达的静态入口）
- Vercel 项目：https://starhub-refresh.vercel.app（静态产物 + Serverless API）
- RSS 页面：https://kwei168.github.io/starhub/rss-aggregator.html
- 每日深度洞察：AI 晨报内「每日深度洞察」子板块 + 历史页 https://kwei168.github.io/starhub/daily-insight-history.html
- 仓库：https://github.com/Kwei168/starhub

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     数据更新触发层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ cron-job.org │  │ GitHub       │  │ 用户手动          │  │
│  │ 每小时 POST  │  │ Actions      │  │ /api/refresh      │  │
│  │ → /api/refresh│  │ schedule     │  │ (前端按钮)        │  │
│  └──────┬───────  └──────┬───────  └────────┬──────────┘  │
│         │                 │                    │             │
│         ▼                 ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Vercel Serverless: /api/refresh.js           │    │
│  │   校验 X-Refresh-Key → 调用 GitHub workflow_dispatch │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │       GitHub Actions: .github/workflows/update.yml   │    │
│  │   checkout → python fetch_and_build.py → commit →   │    │
│  │   git push → npx vercel --prod                       │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Python: fetch_and_build.py              │    │
│  │   拉取 starred repos → 智能分类 → 翻译描述 →         │    │
│  │   生成 index.html + ai-daily.html +                  │    │
│  │   rss-aggregator.html（1005 源三层分级构建）→         │    │
│  │   build_daily_insight 每日深度洞察注入 ai-daily       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     前端实时数据层                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/events.js                   │    │
│  │  拉取关注用户 24h 动态 → 10min 缓存 → 前端 30min 轮询 │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/search.js                   │    │
│  │  中文→英文翻译 → GitHub 搜索 API → 10min 缓存         │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/news.js                     │    │
│  │  36氪(RSSHub镜像链) + Redis博客 → 干净JSON → 10min缓存│    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 双数据系统

| 区域 | 数据源 | 更新机制 | 文件 |
|---|---|---|---|
| **主数据区**（Star 项目列表） | GitHub API: `/users/Kwei168/starred` | workflow 触发 `fetch_and_build.py` 静态构建 | `index.html` |
| **关注动态区**（右侧 Feed） | GitHub API: `/users/{user}/events/public` | `/api/events.js` 实时查询，前端 30min 轮询 | 运行时 API |
| **AI 晨报** | AIHOT 公开 API v1（降级回退 RSS）+ HN / The Verge / TechCrunch / arXiv / 36氪(RSSHub镜像) / Redis / AtlasNote 多渠道 | `build_ai_daily.py` 每次构建时云端拉取生成 | `ai-daily.html` |
| **RSS 聚合** | 1005 源（AI/科技/开发/新闻/公众号/播客/Twitter），T1/T2/T3 三层分级 | `build_rss_aggregator.py` 构建 72h 快照 + `api/rss.js` T1 实时抓取；并行抓取（12 并发 + 域级熔断） | `rss-aggregator.html` + `rss-data-0.js`~`rss-data-N.js` + `rss_api_snapshot*.json`（快照已出仓，见 §8.13） |
| **每日深度洞察** | RSS 7 天 + 热榜 40 平台 + AIHOT + AGI Hunt 四源叠加 | `build_daily_insight.py` RAG 管线（FAISS+BM25 混合检索 → 多级 LLM Phase → RAGAS 评估-修正），由 `fetch_and_build.py` 在 RSS 构建后调用 | `daily-insight.json` + `daily-insight-history.html` + 注入 `ai-daily.html` 的「每日深度洞察」子板块 |
| **语义洞察** | LlamaIndex 向量索引 + Agnes LLM + SiliconFlow embedding | `insight_engine.py` 构建时运行；嵌入缓存 `emb_cache.json` 跨 run 持久化 | `analysis_snapshot.json`（含 deep_insights / topic_clusters / cross_platform） |
| **热榜态势** | newsnow 40 平台热榜快照 | `build_rss_aggregator.py` 的 `fetch_newsnow_snapshot()`；`hot_snapshot.json` + `hot_history.json` | AI 动态面板「热榜」Tab + 分类筛选 |

---

## 三、核心文件清单

### 构建与数据

| 文件 | 行数 | 作用 |
|---|---|---|
| `fetch_and_build.py` | 825 | **核心入口**。拉取 starred repos、智能分类、翻译描述、生成 `index.html`。末尾依次调用 `build_ai_daily.main()`、`build_rss_aggregator.main(mode)` 与 `build_daily_insight.main()` |
| `build_ai_daily.py` | ~1250 | AI 晨报生成器。主源 AIHOT 公开 API v1（匿名 `/api/v1/items`，失败降级 RSS → 本地 JSON）→ 筛选 36h 条目；多渠道快讯：Hacker News / The Verge / TechCrunch / arXiv / 36氪(RSSHub镜像) / Redis博客 / AtlasNote → 英译中 → 跨源四层去重（精确/子串/同URL/摘要互含）→ 头条评分制（跨源报道数+编辑分+信源权重+新鲜度）→ 生成报纸风格 `ai-daily.html`，页脚显示信源成败状态栏 |
| `template.html` | ~2110 | **页面模板**。包含全部 CSS + HTML 结构 + JS 交互逻辑。`fetch_and_build.py` 读取此文件，替换占位符生成 `index.html`。2026-08-29 重设计为纸感编辑风（暖纸底+衬线标题+等宽数字），搜索置顶通栏+340px粘性侧栏 |
| `index.html` | 自动生成 | 最终部署页面。**不要直接编辑**，每次 workflow 会从 template 重新生成 |
| `build_rss_aggregator.py` | ~8047 | **RSS 聚合页生成器**。1005 源三层分级（T1=6/T2=204/T3=795），支持 full/incremental 两种构建模式；并行抓取（全局 12 并发 + 每域名 2 + 域级熔断）；多引擎翻译分流链（Agnes 多 key → Zen → GTX → Bing → MyMemory）；数据切成 `rss-data-0.js`（首屏）+ `rss-data-1..N.js`（后台合并）；同时生成卡片墙、AI 动态双形态面板（含热榜 Tab）、信源面板、reader2 阅读器、筛选/搜索/分享/主题切换/实时刷新、媒体播放（YouTube/播客） |
| `build_daily_insight.py` | ~4082 | **每日深度洞察 RAG 管线**（详见 §8.12）。四源叠加（RSS 7 天 + 热榜 + AIHOT + AGI Hunt）→ 硬过滤 → 切片 embedding → FAISS+BM25 混合检索 → 多级 LLM Phase 生成 → RAGAS 评估-修正 → 破茧栏；产出 `daily-insight.json` + `daily-insight-history.html`，并注入 `ai-daily.html` |
| `rss-aggregator.html` | 自动生成 | RSS 聚合页面。**不要直接编辑**；由 `build_rss_aggregator.py` 生成，包含卡片墙、AI 动态双形态面板（桌面左侧常驻/移动抽屉）、热榜分类筛选、信源面板、reader2 阅读器（内嵌媒体播放）、筛选/搜索/分享/主题切换/实时刷新 |
| `ai-daily.html` | 自动生成 | AI 晨报页面。**不要直接编辑**；正文含 `<!-- daily-insight-start/end -->` 标记包裹的「每日深度洞察」子板块，由 `build_daily_insight._inject_into_ai_daily()` 幂等替换 |
| `daily-insight-history.html` | 自动生成 | 每日洞察 30 天历史轨迹独立页面，报纸风格，与 `ai-daily.html` 视觉一致 |
| `bestblogs_sources.json` | 559 条 | BestBlogs 项目导出的 RSS 源列表（375 公众号 + 60 播客 + 124 YouTube），构建时自动合并 |

### 语义洞察引擎

| 文件 | 行数 | 作用 |
|---|---|---|
| `insight_engine.py` | ~1984 | **LlamaIndex 语义分析引擎**（服务于 RSS 聚合页 AI 动态面板的 `analysis_snapshot.json`，与 build_daily_insight 是两条独立管线）。AgnesLLM 多 key 轮询 + 429 自动切换（2026-09-18 起统一为 `AGNES_API_KEYS` 逗号方案，与其余模块一致，见 §8.14）；SiliconFlow bge-m3 API embedding（本地 fastembed 回退）；层级索引 + 手动余弦相似度检索（避向量维度不匹配）；RAGAS-inspired 评估 + 自纠错循环；话题聚类（embedding + TF-IDF 加权）；关键词提取（LLM + 分源关键词池）；深度洞察三视角独立生成（core_trends / rss_insights / narrative）；嵌入缓存 `emb_cache.json` 跨 run 持久化（5000 条上限） |
| `build_config.json` | 21 | 构建配置外置文件。控制 insight_engine 开关、LLM provider、max_documents、top_keywords/topics；`daily_insight_enabled`、`daily_insight_judge_provider/model/timeout`（当前 agnes / agnes-2.5-flash / 60s；2026-09-19 起主判正式改为实际在打分的 agnes，见 §8.7）、`daily_insight_cross_validation`（当前 true，双 prompt 交叉验证）等每日洞察参数；缺失键自动填充默认值。`daily_insight_judge_fallback` 与 `daily_insight_openrouter_models` 是从无代码读取的死键，已删除 |
| `build_logger.py` | ~120 | **构建日志系统**。JSONL 格式每日追加，14 天滚动清理；提供 `append()` / `cleanup()` / `summary()` API；供 workflow 与 `api/build_log.js` 消费 |

### 测试文件

| 文件 | 作用 |
|---|---|
| `test_frontend_tz_regression.py` | 前端时区盲日期比较回归测试（P0 修复验证） |
| `test_insight_engine.py` | 洞察引擎单元测试 |
| `test_insight_schedule.py` | 洞察调度与轻量场/重场分级测试 |
| `test_insight_bad_date.py` | bad_date 降权与 stale 标注测试 |
| `test_insight_guard_v3.py` | 维度护栏 v3 + 漂移自愈失效缓存测试 |
| `test_insight_embeddings.py` | 嵌入缓存值类型过滤 + NaN/TypeError 防御测试 |
| `test_insight_query_batch.py` | 查询批化与检索偏移修复测试 |
| `test_daily_insight.py` | 每日洞察 RAG 管线本地测试（675 行，跳过网络的核心逻辑冒烟：聚类/去重/RAGAS 解析/注入标记等） |
| `tests/daily_insight/*.py` | 每日洞察 pytest 套件（12 个文件：去重、双热度、历史分块、素材过滤、prompt 结构、查询与热度、RAGAS 解析/鲁棒、自审、语义聚类、tracer、集成） |
| `test_translation_endpoints.py` | 翻译端点分流与降级链测试 |
| `test_frontend_tz_regression.py` | 前端时区漂移回归测试 |

### 数据文件（workflow 自动维护）

| 文件 | 作用 |
|---|---|
| `known_categories.json` | 项目→分类映射缓存（避免每次重新分类） |
| `descriptions_zh.json` | 项目→中文描述缓存（避免重复翻译） |
| `trending_snapshot.json` | 趋势分析快照数据 |
| `rss_api_snapshot.json` (+`_1`...) | RSS API 分块快照（72h 累积历史 + meta.last_fetch 增量状态）。**已移出仓库**（单文件 82MB 导致 Actions checkout 超时），`.gitignore` 忽略，且被部署前的 prune 删掉，线上读不到（见 §8.13） |
| `rss_sources.json` | RSS 源元数据（1005 条，含 tier/cat/color 字段；8 分类：wechat 386 / dev 178 / twitter 160 / podcast 70 / tech 66 / ai 61 / news 61 / cn_tech 23） |
| `rss_history.json` | RSS 文章历史累积（跨构建持久化） |
| `translations.json` | 翻译缓存（MD5 hash → 中文，供构建和 API 共享） |
| `hot_snapshot.json` | 热榜快照数据（40 平台，列表格式） |
| `hot_history.json` | 热榜历史累积（跨构建持久化） |
| `analysis_snapshot.json` | 洞察分析快照（含 keywords / topics / deep_insights / topic_clusters / cross_platform / hot_trends / stale 标注） |
| `daily-insight.json` | 每日深度洞察当日产出（date / theme / events（含 score、status、deep_analysis、key_links）/ bubble_breaker / stats / quality(RAGAS 评分)） |
| `daily_insight_history.json` | 每日洞察 30 天事件轨迹（跨天 Jaccard≥0.5 匹配 ongoing/escalating 状态） |
| `daily_insight_tracking_history.jsonl` | 每日洞察构建质量追踪（各 Stage 计数 + RAGAS 分数，按日追加） |
| `diagnose_coverage.py` | 本地诊断脚本：取 `daily_insight_chunks.json`（跨构建累积嵌入缓存）**前 80 条**近似当日评估上下文，与 events 对比给出覆盖率缺口的**方向性**线索；因 `retrieval_score` 未持久化，不能还原真实评估上下文，结论不可当判据（读 `daily_insight_chunks.json` + `daily-insight.json`） |
| `rss_trend_history.json` | RSS 趋势追踪（14 天滚动快照；关键词 5 种生命周期 + 话题 4 种生命周期） |
| `emb_cache.json` | 嵌入向量缓存（~8MB/5000 条，CI 用 actions/cache 持久化，gitignore） |
| `daily_insight_vectors.npy` / `daily_insight_chunks.json` / `daily_insight_faiss.index` | 每日洞察向量缓存 / chunk 元数据 / FAISS 索引（CI 用 actions/cache 持久化，gitignore） |
| `daily_insight_snapshot.json` | 每日洞察的 AIHOT + AGI Hunt 构建期缓存（gitignore） |

### Vercel Serverless 函数

| 文件 | 路由 | 方法 | 认证 | 超时 | 作用 |
|---|---|---|---|---|---|
| `api/refresh.js` | `/api/refresh` | POST | X-Refresh-Key + Origin 白名单 | 10s | 触发 GitHub Actions workflow_dispatch |
| `api/events.js` | `/api/events` | GET | Origin 白名单（无 key） | 60s | 关注用户 24h 动态聚合，10min 缓存，前端相对时间显示+分类筛选+游标分页 |
| `api/search.js` | `/api/search` | POST | X-Search-Key (= REFRESH_KEY) + Origin 白名单 | 30s | 全网 GitHub 仓库搜索，中文翻译，10min 缓存 |
| `api/news.js` | `/api/news` | GET | Origin 白名单（放行无 Origin 同源请求） | 30s | 36 氪 (RSSHub 镜像链)+Redis 博客 RSS 代理，输出干净 JSON，10min 缓存 |
| `api/rss.js` | `/api/rss` | GET | CORS 允许所有来源（`*`） | 60s | RSS 聚合 API。`?refresh=1` 实时抓 T1（6 源）；`?batch_info=1` / `?batch=N` 供前端逐批实时抓 T2/T3（每批 200 源）。快照分支代码仍在但生产恒不生效（文件被 prune，见 §8.13）；T1 英文源实时翻译 |
| `api/article.js` | `/api/article` | GET/OPTIONS | CORS 允许所有来源（`*`） | 15s（函数配置） | 阅读器全文兜底：快照全文 map → 特殊源提取/GitHub/YouTube → Readability 通用提取；OPTIONS 返回 204 |
| `api/agihunt.js` | `/api/agihunt` | GET | 公开读取 | 15s | AI 动态侧栏的 AGI Hunt 频道代理 |
| `api/translate.js` | `/api/translate` | POST | Origin 白名单 | 30s | **翻译代理**。两种 mode **共用同一条服务端降级链** GTX → MyMemory → Agnes → Zen（`translateWithFallback`）；mode 只改并发与配额：`full`（全文/摘要按钮）并发 4、Agnes 不限额；`bulk`（缺省，批量补翻）并发 2、**Agnes 兜底上限 30 条**（`AGNES_FALLBACK_MAX`），另有浏览器端直连 GTX 分担。实测 GTX 在 Vercel 出口 IP 长期 429，大量落 MyMemory |
| `api/build_log.js` | `/api/build_log` | GET | CORS 宽松 | 10s | **构建日志查询**。读 `build_logs/*.jsonl`，支持日期/类型过滤、分页、摘要模式（`?summary=1`） |

### 配置

| 文件 | 作用 |
|---|---|
| `vercel.json` | Vercel 项目配置，声明 9 个 Serverless 函数及超时（refresh/search/events/news/rss/article/agihunt/translate/build_log） |
| `.github/workflows/update.yml` | GitHub Actions 主工作流。**分层调度**：UTC 21:00（北京 05:00）全量构建，UTC 2/6/10/14（北京 10/14/18/22）增量构建；安装 LlamaIndex + fastembed + **faiss-cpu + rank-bm25**；恢复嵌入缓存与每日洞察 FAISS/向量缓存（actions/cache 路径含 `daily_insight_vectors.npy`/`daily_insight_chunks.json`/`daily_insight_faiss.index`）；**git add 不再包含 rss_api_snapshot**（已 gitignore）；env 提升到 job 级防 push 重试丢 key |
| `.github/workflows/zen-check.yml` | Zen 翻译链路 CI 验证（手动触发），实测 6 条文本的 Zen 轮询翻译 |
| `.github/workflows/build-log-summary.yml` | 每小时整点生成构建日志摘要并提交 |
| `.github/workflows/sync-agnes-env.yml` | Agnes 环境变量同步到 Vercel（一次性工具） |
| `.gitignore` | 忽略 `__pycache__/`、`.deploy-tmp/`、`rss_cache.json`（构建期缓存）、`emb_cache.json`（嵌入向量缓存）、`rss_api_snapshot*.json`（RSS 快照，82MB 出仓）、`daily_insight_snapshot.json`/`source_quality.json`/`daily_insight_faiss.index`/`daily_insight_chunks.json`/`daily_insight_vectors.npy`（每日洞察构建中间产物）、`*.tmp`（原子写临时文件）、`_rev*`/`_adv*`（对抗性审查临时脚本）等 |

### 辅助目录

| 目录 | 作用 |
|---|---|
| `.deploy-tmp/` | 部署/调试脚本集合（trigger-workflow.cjs、verify-*.cjs 等），不参与构建 |
| `docs/superpowers/` | 历史设计文档和实施计划 |
| `.qoder/repowiki/` | Qoder 知识卡片（模块级技术文档） |

---

## 四、关键配置

### Vercel 环境变量（Project: starhub-refresh）

| 变量名 | 用途 | 类型 |
|---|---|---|
| `GH_TOKEN` | GitHub PAT（fine-grained），需 `contents:write` + `actions:write` 权限 | Secret |
| `REFRESH_KEY` | 弱防护密钥，用于 `/api/refresh` 和 `/api/search` 的 header 校验 | Secret |
| `VERCEL_TOKEN` | Vercel 部署令牌（GitHub Actions 中使用） | Secret（workflow secrets） |
| `AGNES_API_KEY` | Agnes AI 主 API key（洞察引擎 LLM + 翻译主力）。**6 个调用点均已支持逗号分隔多 key**（2026-09-18 补齐 `build_daily_insight.py`、`fetch_and_build.py`、`api/translate.js`），与 `AGNES_API_KEYS` 合并成同一个池 | Secret |
| `AGNES_API_KEYS` | Agnes 附加 key（**逗号分隔**，与主 key 合并成池轮转抗 429；供 build_rss_aggregator / build_ai_daily / build_daily_insight / insight_engine / fetch_and_build / api/translate.js 共 6 个调用点，取代已废弃的 `AGNES_API_KEY_2/_3`） | Secret |
| `SILICONFLOW_API_KEY` | 硅基流动 API key（bge-m3 embedding 主力） | Secret |
| `ZEN_API_KEY` / `OPENCODE_KEY` | OpenCode Zen 免费模型 key（翻译链 gtx 之后接力 + 每日洞察 Judge 首选 mimo-v2.5-free）。**⚠ 实测该端点当前整体不可用：构建期翻译 `Zen: 0`、三个模型逐个自封，Judge 侧 mimo 0/6 命中并全部降级 agnes（见 §8.7 / §8.12）——按"已配置但不可依赖"对待** | Secret |
| `AGIHUNT_API_KEY` | AGI Hunt Agent API 密钥（每日洞察第四源；Bearer 认证，见 §8.12） | Secret |
| `OPENROUTER_API_KEY` | 已在 update.yml 声明但 Judge 降级链已移除 OpenRouter（长期不通），当前闲置 | Secret |

**当前状态**（2026-09-14）：
- `REFRESH_KEY`：仅在 Vercel 环境变量、GitHub Actions Secret 与受控触发配置中维护；手册不记录实际值。
- `GH_TOKEN`：仅在受控 Secret 中维护；不得读取、打印或回显实际值。

### 外部服务

| 服务 | 用途 | 配置 |
|---|---|---|
| **cron-job.org** | 每小时 POST 到 `/api/refresh` 触发构建 | URL: `https://starhub-refresh.vercel.app/api/refresh`，Header: `X-Refresh-Key: $REFRESH_KEY`（实际值由受控配置注入） |
| **AIHOT API v1** | AI 晨报主数据源（公开匿名） | `https://aihot.virxact.com/api/v1/items` |
| **AIHOT RSS** | AI 晨报降级数据源 | `https://aihot.virxact.com/feed.xml` |
| **RSSHub 镜像链** | 36氪 AI 资讯流中转（官方 RSS 有人机验证） | 4 个镜像按可用性排序，依次尝试 |
| **Redis Blog** | Redis 官方博客 RSS | `https://redis.io/feed/` |
| **AtlasNote** | AI 深度文章（架构/创业/研究方法论），中英双语同文各发一条，按 slug 归并偏好中文版；周更 2-4 篇，36h 窗口未命中属正常 | `https://atlasnote.ai/rss.xml` |
| **HN / Verge / TechCrunch / arXiv** | AI 晨报多渠道快讯 | 见 `build_ai_daily.py` 常量配置 |

### 分类体系（11 类）

| key | 标签 | 颜色 |
|---|---|---|
| `agent` | AI Agent & Skills | 蓝 |
| `distill` | 思维蒸馏 & 认知 | 紫 |
| `video` | AI 视频创作 | 红 |
| `coding` | AI 编程 & 工具链 | 绿 |
| `content` | 内容创作 & 排版 | 粉 |
| `learning` | AI 学习 & 教程 | 黄 |
| `assistant` | AI 助手 & 应用 | 青 |
| `tools` | 实用工具 & 资源 | 灰 |
| `finance` | 金融 & 交易 | 金 |
| `business` | 商业 · 一人公司与知产 | 橙 |
| `frontend` | 前端 & 设计系统 | 蓝绿 |

### 晨报分类体系（6 类，2026-08-29 新增「海外热点」）

| 分类 | 来源 |
|---|---|
| AI 模型 | AIHOT API/RSS |
| AI 产品 | AIHOT API/RSS |
| 行业动态 | AIHOT API/RSS + 36氪 |
| 海外热点 | Hacker News / The Verge / TechCrunch / arXiv / Redis |
| 论文 | arXiv + AIHOT + AtlasNote（论文解读类） |
| 技巧观点 | AIHOT API/RSS + AtlasNote |

### 导航栏结构

1. ** AI 晨报** — 高亮入口，链接到 `ai-daily.html`
2. **📡 RSS 聚合** — 高亮入口，链接到 `rss-aggregator.html`
3. **📚 学习资源 ▾** — 小林笔记、KamaCoder、Agents Course、Vibe Coding、AGI Hunt、FDE Learning、All-in-RAG
4. **📡 资讯平台 ▾** — NewsNow、今日热榜、赋范空间、V2EX、Linux Do
5. **🤖 AI 工具 ▾** — CodeFather、CodeFather AI

---

## 五、常见操作手册

### 5.1 手动触发构建/部署

```bash
# 方式 1：通过 API（推荐）
node .deploy-tmp/trigger-workflow.cjs

# 方式 2：GitHub 页面手动触发
# 进入仓库 → Actions → Update Star Hub → Run workflow

# 方式 3：推送代码到 main（workflow 无 on:push，不会自动触发！）
# 推送后必须手动触发 workflow_dispatch
```

### 5.2 添加导航链接

1. 编辑 `template.html`，在对应 `.nav-drop-panel` 内添加 `<a>` 标签
2. 运行 `python fetch_and_build.py` 重新生成 `index.html`
3. 提交 `template.html` + `index.html`
4. 推送后手动触发 workflow 部署

**注意**：必须同时改 `template.html` 和 `index.html`，否则 workflow 会用旧 template 覆盖 `index.html`。

### 5.3 修改分类

编辑 `fetch_and_build.py` 中的 `CATS` 列表。已有项目的分类缓存在 `known_categories.json`，修改分类 key 后需要清理该文件中对应条目才能重新分类。

### 5.4 修改 REFRESH_KEY

1. 修改 `template.html` 中的 `REFRESH_KEY` 常量
2. 在 Vercel → Environment Variables 中更新 `REFRESH_KEY` 值
3. **点击 Redeploy**（Vercel 环境变量变更不会自动生效，必须重新部署）
4. 提交推送 `template.html`，触发 workflow

### 5.5 本地预览

```bash
python dev_render.py   # 本地渲染预览（不拉取真实数据）
python fetch_and_build.py  # 完整构建（需要 GitHub API 访问）
```

### 5.6 Vercel 部署认证（关键）

- 部署依赖 GitHub Actions Secret `VERCEL_TOKEN`；令牌只应保存在 GitHub/Vercel Secret 中，**不得写入 HANDOFF.md、脚本或聊天记录**。
- `update.yml` 通过 `VERCEL_PROJECT_ID=prj_7gK5d3EOJYTC8AmUxR2cNuHi7arB` 与 `VERCEL_ORG_ID=team_iovvEy0us9KkCNkuMRLQrIeA` 绑定 `starhub-refresh` 项目。
- 若出现 token 无效或权限错误，应在 GitHub Actions/Vercel 控制台核对 Secret 的项目权限；不要读取、打印或提交令牌值。
- 部署验证以 Actions 的 Deploy to Vercel 步骤成功、线上响应头/API 行为和页面浏览器验证为准。

```bash
# 查看某次 workflow 的公开日志（不要输出 Secret）
gh run view <run_id> --log
```

---

## 六、部署流程详解

```
push code → (不会自动触发！)
                ↓
手动触发 workflow_dispatch (或 cron 定时触发)
                ↓
GitHub Actions: update.yml
  1. checkout main (fetch-depth: 0, 完整历史)
  2. setup Python 3.11
  3. 判断构建模式：UTC 21:00 → full，其余 → incremental
  4. pip install llama-index-core llama-index-embeddings-fastembed fastembed faiss-cpu rank-bm25
  5. 恢复嵌入缓存 + 每日洞察 FAISS/向量缓存（actions/cache）
  6. python fetch_and_build.py $MODE
     - 拉取 Kwei168 的 starred repos（分页，每页 100）
     - 智能分类（关键词匹配 + known_categories.json 缓存）
     - 翻译英文描述为中文（多引擎分流：Agnes 多 key → Zen → GTX → Bing → MyMemory）
     - 生成 index.html（从 template.html 替换占位符）
     - 调用 build_ai_daily.main() 生成 ai-daily.html
     - 调用 build_rss_aggregator.main(mode) 生成 RSS 聚合页
       · full 模式：并行抓取全部 1005 源（12 并发 + 域级熔断）
       · incremental 模式：跳过 T1 源 + 4h 内已抓源；跳过的源从历史数据填充
       · 运行 insight_engine 语义分析（LlamaIndex + Agnes LLM）
       · 生成热榜快照 + 趋势追踪
     - 调用 build_daily_insight.main() 生成每日深度洞察
       · RAG 管线 + RAGAS 评估-修正 + 破茧栏
       · 产出 daily-insight.json / daily-insight-history.html 并注入 ai-daily.html
  5. git add + commit + push（仅当有变更时；**不含 rss_api_snapshot**，已 gitignore）
  6. npx vercel --prod --yes --token $VERCEL_TOKEN
                ↓
Vercel 部署完成（约 2-3 分钟；rss_api_snapshot*.json 虽不入 git，
但存在于 Actions 工作区，随 vercel 上传供 /api/rss 读取）
```

### 关键约束

- **workflow 没有 `on: push` 触发器**，push 代码后必须手动触发 `workflow_dispatch`
- **`index.html` 是自动生成文件**，直接编辑会被 workflow 覆盖
- **Vercel 环境变量变更后必须 Redeploy**，否则新值不生效
- **concurrency: cancel-in-progress: true**，新触发取消旧排队，永远只跑最新一次，从根本上消除并发冲突
- **env 提升到 job 级**，确保 push 冲突重试时重新构建仍能拿到翻译 key 与 GitHub API 配额
- **分层调度预算**：全量 ~15min × 30天 + 增量 ~5min × 4次 × 30天 + star数据 ~30min × 30天 ≈ 1950 min/月（安全线内）

---

## 七、踩过的坑

### 7.1 GitHub Actions schedule 不可靠
免费账户的 cron 任务经常被延迟或直接跳过（实测出现 11h、10h 空白期）。
**解决**：引入 cron-job.org 每小时 POST 触发作为主力，GitHub schedule 降级为兜底。

### 7.2 workflow 覆盖手动修改
`fetch_and_build.py` 从 `template.html` 重新生成 `index.html`。如果 workflow 在手动修改 `index.html` 之后运行，会覆盖手动修改。
**解决**：修改导航栏等模板内容时，必须同时改 `template.html` 和 `index.html`，并在 workflow 运行前提交。

### 7.3 git push 被拒绝（远端有新提交）
workflow 自动构建后会 push 新 commit，导致本地 push 被拒。
**解决**：`git fetch origin` → `git merge origin/main` → `git push origin main`。

> **禁止 `git pull --rebase`、禁止 `git rebase`、禁止 `git commit --amend`、禁止裸 `git stash`**（`CLAUDE.md` 硬性规定）：CI 每小时并发 auto-commit，rebase 易产生悬挂对象并损坏 pack 文件，amend 在并发分支上不可恢复。自动生成文件冲突用 `git checkout --theirs <file>`。
> 若本地未推送提交含真实工作，**不要**照 `CLAUDE.md` 的 `git reset --hard origin/main` 流程做（那条前提是"未推送提交可丢弃"，仅适用于纯数据改动）；此时用 merge，零重叠时必然无冲突。

### 7.4 Vercel 环境变量更新后不生效
修改 Environment Variables 后，Vercel 提示 "A new deployment is needed"。但如果有更新的部署已存在，Redeploy 旧部署会失败。
**解决**：通过触发新的 workflow 来部署（workflow 的 vercel --prod 会使用最新环境变量）。

### 7.5 refresh.js 的 Origin 白名单拦截服务端调用
cron-job.org 的请求没有浏览器 Origin header，被 403 拒绝。
**解决**：修改 `refresh.js`，携带正确 `X-Refresh-Key` 的请求跳过 Origin 检查。

### 7.6 RSS 日期解析 Windows 兼容
`datetime.strptime` 的 `%z` 在 Windows 下不识别 `GMT`。
**解决**：`_parse_rss_date()` 中先 `s.replace(" GMT", " +0000")`。

### 7.7 search.js 和 refresh.js 共用 REFRESH_KEY
两个 API 使用同一个 `REFRESH_KEY` 环境变量。修改 key 时需同步更新前端代码和 Vercel 环境变量。

### 7.8 36氪 RSS 有人机验证反爬
36氪官方 RSS（36kr.com/feed*）有人机验证，浏览器/服务器直连均被拦截；RSSHub 公共镜像 CORS 头不合法，前端无法直连。
**解决**：由 `/api/news.js` 在服务端中转，RSSHub 镜像链按可用性排序依次尝试（部分镜像封数据中心 IP）。

### 7.9 AI 晨报多源去重
多渠道抓取后同一事件可能出现在多个源（如 AIHOT + 36氪 + Verge 报道同一件事）。
**解决**：跨源四层去重——①规范化标题精确匹配 → ②标题子串包含 → ③规范化 URL 相同（去协议/www/utm 参数，覆盖同文被改写标题后的跨源收录）→ ④规范化摘要互为包含（覆盖标题与 URL 全异的同文转录）。
**注意**：不要用「同域名+同一天」判重——同一信源当天会发布多篇不同文章，早期版本该规则曾把 Verge/36氪 当天第 2 篇起全部误杀（每天最多存活 1 条），2026-08-29 已修复。

### 7.10 news.js 放行无 Origin 请求
部分环境同源请求不携带 Origin header，严格白名单会导致误拦。
**解决**：`origin === ''` 时也放行（只读公开数据无敏感信息），但仅对白名单内源回显 ACAO 头。

### 7.11 RSS 聚合器 API-First 架构（2026-09-02）
RSS 聚合页面从纯静态构建升级为 API-First 实时架构：
- 页面加载时立即调用 `https://starhub-refresh.vercel.app/api/rss` 获取实时数据
- 失败时回退到静态构建数据（显示"· 静态构建数据"）
- **CORS 配置**：`api/rss.js` 添加 `Access-Control-Allow-Origin: *`，允许 GitHub Pages 跨域访问
- **字段映射**：API 返回缩写字段（`t`=title, `u`=url, `s`=summary, `d`=date），前端需转换
- **已读标记 CSS**：Python 字符串中 unicode 转义需双反斜杠（`\\5df2 \\8bfb`），否则被解释为八进制

### 7.12 GitHub Pages 与 Vercel 双域名部署
- 主站：`https://starhub-refresh.vercel.app`（Vercel，支持 Serverless API）
- 镜像：`https://kwei168.github.io/starhub/`（GitHub Pages，静态托管）
- **关键**：GitHub Pages 无法执行 Serverless 函数，API 调用必须使用 Vercel 完整 URL
- **缓存差异**：Vercel CDN 缓存约 5 分钟，GitHub Pages 缓存 10 分钟（`max-age=600`）

### 7.13 翻译缓存架构（2026-09-02）
**问题**：API 层（Node.js）无法调用 Python 翻译服务，导致实时数据无翻译

**解决方案**：构建时翻译 + 缓存共享
```
构建时（Python）：抓取 RSS → 翻译 → 保存 translations.json（MD5 hash → 中文）
                                    ↓
API 实时（Node.js）：抓取 RSS → 查 translations.json → 返回（有翻译用翻译，无翻译用原文）
```

**关键文件**：
- `translations.json`：翻译缓存，14000+ 条，MD5 hash 作为 key
- `api/rss.js`：加载翻译缓存，应用翻译到返回数据
- `build_rss_aggregator.py`：构建时翻译标题和摘要，保存缓存

**优势**：
- 翻译只在构建时进行（利用 Python 四端点降级链）
- API 实时性不受影响（查缓存很快）
- 下次构建时，已翻译的内容不重复翻译（缓存命中）

### 7.14 RSS 刷新机制演进（2026-09-04）

**问题背景**：
- Vercel Serverless 是无状态的，服务端维护的增量更新状态（`sourceLastFetch` Map）在冷启动后丢失
- 153 个 RSS 源全量抓取耗时过长（理论最大 145 秒），前端超时设置过短会导致请求被 abort
- 静默失败设计让用户看不到任何反馈，不知道刷新是否成功

**第一次尝试（失败）**：
- 在服务端实现基于 `If-Modified-Since` 头的增量更新
- 维护 `sourceLastFetch` Map 记录每个源的最后抓取时间
- **失败原因**：Vercel Serverless 冷启动后 Map 为空，增量逻辑失效；且全量抓取仍需要超过 90 秒

**最终方案**：**前端增量更新 + 性能优化**

#### API 端优化（`api/rss.js`）
```javascript
// 性能参数调整
const FETCH_TIMEOUT = 5000;     // 从 8s 降低到 5s（加快失败速度）
const CONCURRENCY = 20;         // 从 10 提高到 20（翻倍并发数）
```
- 移除不可靠的服务端增量逻辑（`sourceLastFetch`、`_unchanged` 标记等）
- 保持简单可靠的全量抓取，但通过提高并发数加快速度
- 理论耗时：153 源 ÷ 20 并发 × 5s ≈ 38 秒（留有余量）

#### 前端增量更新（`rss-aggregator.html` / `build_rss_aggregator.py`）
```javascript
// localStorage 维护已读文章唯一键（当前 key 为 `rss_read_v2`）
var READ_ARTICLES_KEY = 'rss_read_v2';

function _getReadUrls() {
  var stored = localStorage.getItem(READ_ARTICLES_KEY);
  return stored ? JSON.parse(stored) : [];
}

function _saveReadUrls(urls) {
  var limited = urls.slice(-5000);  // 最多保留 5000 条
  localStorage.setItem(READ_ARTICLES_KEY, JSON.stringify(limited));
}

function _mergeLiveSources(liveData, silent) {
  var readUrls = _getReadUrls();
  var readSet = {};
  readUrls.forEach(function(url) { readSet[url] = true; });

  // ... 遍历 API 返回的文章 ...
  // 跳过已在 ART 数组或 localStorage 中的文章
  if(existingKeys[key]) return;
  if(readSet[url]) return;  // ← 真正的增量判断

  newUrls.push(url);
  // ... 添加到 ART 数组 ...

  // 保存新 URL 到 localStorage
  if(newUrls.length > 0) {
    _saveReadUrls(readUrls.concat(newUrls));
  }
}
```

**关键改进**：
1. **超时延长**：从 90 秒增加到 120 秒（适应 20 并发×5s 的理论值）
2. **明确的 toast 提示**：
   - 有新文章：`"已更新 N 篇新文章"`
   - 无新内容：`"已刷新，暂无新内容"`
   - 刷新失败：`"刷新失败：网络错误"`
3. **移除静默失败**：catch 块显示错误信息
4. **按钮状态管理**：在所有情况下（成功/失败/无新内容）都正确移除 loading 状态

**测试结果**（2026-09-04 实测）：
- ✅ API 请求从 `[pending]` 变为 HTTP 200 成功
- ✅ Toast 提示正常显示，用户能看到明确反馈
- ✅ 第二次刷新正确识别"暂无新内容"
- ✅ localStorage 正确维护已读 URL 列表

**经验教训**：
- **不要在无状态 Serverless 上依赖内存状态做增量** — 应该用持久化存储（Redis/KV）或前端状态
- **性能优化优先于架构复杂化** — 提高并发数比实现复杂的增量协议更简单有效
- **用户反馈必须可见** — 静默失败是最差的用户体验

### 7.15 RSS 聚合器三层分级架构（2026-09-05）

**背景**：集成 BestBlogs 559 源后，源清单一度达到 1014（含 160 个 X/Twitter 源）；全量抓取超出 GitHub Actions 分钟预算。2026-09 下旬经死源清理后为 **1005**。

**三层分级**：

| Tier | 定义 | 源数量 | 刷新方式 |
|------|------|--------|--------|
| T1 | 日均产出极高（头部高频源） | 6 | 用户刷新时 api/rss.js 实时抓取 |
| T2 | 日均产出 10+ 篇 | 204 | Actions 增量构建 |
| T3 | 日均产出 < 10 篇 | 795 | Actions 增量构建 |

**1005 源分类分布**（2026-09-18 实测）：
- wechat（公众号）: 386
- dev（开发）: 178
- twitter（X/Twitter）: 160
- podcast（播客）: 70
- tech（科技）: 66
- news（新闻）: 61
- ai: 61
- cn_tech（中国科技）: 23

**增量构建逻辑**（`build_rss_aggregator.py`）：
```
incremental 模式：
  1. 抓取全部 1005 个源（含 T1；2026-09-19 起不再有按时间的跳过）
  2. 合并进 72h 历史（分块存储，跨构建由 actions/cache 承载）
  3. 翻译 / 打标 / 生成 HTML 与数据分块
```

**API 层抓取**（`api/rss.js`，2026-09-19 实测校正）：
- ~~快照优先~~ 不成立：`update.yml` 在 `vercel --prod` 前 `rm -f rss_api_snapshot*.json`，函数工作区没有快照，`loadSnapshot()` 恒为 null（线上 `/api/rss?meta=1` 实测返回 `{"total":0}`）
- 实际路径：`?refresh=1` 实时抓 6 个 T1；前端再按 `?batch_info=1` → `?batch=N`（每批 200 源、共 5 批）逐批实时抓 T2/T3 并合并渲染
- T1 英文源实时翻译：Agnes → Zen → GTX → Bing → MyMemory 五端点降级

**卡片墙交织算法**（`tierInterleave`）：
- 双队列 4:1 交织：每 4 篇 T1/T2 文章穿插 1 篇 T3 文章
- 防止 T3 的 795 个低频源被 T1 的 6 个高频源完全淹没
- T1+T2 占 ~80% 卡片位，T3 占 ~20%

**源面板排序**：每个分类内按文章数降序排列，用户可快速定位活跃源。

**经验教训**：
- **跨构建状态不能寄生在大产物里** — last_fetch 放在 42.6MB 快照内，快照一出仓增量就静默退化成全量，两天无人察觉；72h 历史放在未提交的 chunk 里同理
- **持久化落点要与体积约束一起设计** — 主文件 64MB 提交进 git 会撑爆仓库与 checkout；改走 actions/cache 分块后，状态与存档都必须保留读不到就老实全抓的降级路径
- **抓取策略已定为每场全量** — 跳过省的是请求数，代价是把页面内容押在存档存活上（2026-09-19 决策，守卫测试见 tests/rss_history/test_source_selection.py）

---

## 八、最近架构变更与维护指南

本节是当前代码状态的权威补充。若本手册前文与本节冲突，以代码和本节为准。

### 8.1 RSS 页面布局：AI 动态双形态

入口和生成器：`build_rss_aggregator.py` 的 `_build_css()`、`build_html()` 与 `_build_js()`；产物 `rss-aggregator.html` 不要直接编辑。

```text
桌面 ≥1280px
.wall-wrap (flex)
├── aside.ai-feed-panel  ← 左侧 sticky 常驻栏，width:300px，top:58px
│   └── .af-body         ← 独立 overflow-y:auto，可持续滚动
└── #wall                 ← 卡片墙，自适应剩余宽度

窄屏 <1280px
.wall-wrap
└── #wall                 ← 单列/多列卡片墙

aside.ai-feed-panel      ← fixed 右侧抽屉，默认 translateX(103%)
                           body.ai-open 控制打开；#btnAiFeed 控制显隐
```

- 桌面端面板在 `.wall-wrap` 内、卡片墙之前；`position:sticky`、`top:58px`、`height:calc(100vh - 78px)`、宽 300px，面板内容独立滚动。
- 桌面端 `#btnAiFeed` 与 `.af-close` 隐藏，进入页面后通过 `_aiDesktop()` 自动调用 `_loadAll()`；每 5 分钟自动刷新时桌面端视为常驻打开。
- `<1280px` 保持右侧 fixed 抽屉；`<=700px` 宽度为 `100vw`。移动端默认隐藏，顶部 `#btnAiFeed` 点击后加载并显示，`scrim` 负责遮罩。
- `#view=ai` 是页面分类视图，不等于 AI 动态面板；验证面板必须查询 `.ai-feed-panel` 作用域，不要用全页 `.cat` 统计。
- 面板 API 必须使用绝对 Vercel URL：`https://aihot.virxact.com/...`、`https://starhub-refresh.vercel.app/api/agihunt`、`https://starhub-refresh.vercel.app/api/news`；GitHub Pages 上的相对 `/api/...` 会变成 Pages 404。

### 8.2 RSS 数据分块、去重与无图降级

构建链：`fetch_and_build.py` → `build_rss_aggregator.py` → `rss-data-0.js`~`rss-data-N.js`（当前 N=2）→ 前端 `SOURCES` → `buildArt()` → `renderWall()`。

- `rss-data-0.js` 是首屏块，`rss-data-1..N.js` 是剩余文章后台块（块数随数据量自适应切分）；页面不再下载/替换约 30MB 的冗余同域快照。
- `buildArt()` 在渲染前按 `sourceKey|link` 建 `_seen`，唯一键重复时跳过；无 link 时用标题作为兜底键。
- `_mergeChunk()` 追加块数据前按 link 过滤已有文章，同时保留无 link item；`_mergeRemoteSources()` 兼容远程刷新字段并保留 `img`。
- `renderWall()` 用 `hasImg=!!a.img` 分流：有图才输出 `.cover-card` 与封面区域；`a.img` 为空时输出原有紧凑纯文字卡，不生成渐变占位。
- 历史层 `_accumulate_history()` 以 link 维护 72 小时窗口；发现重复时先检查 chunk/远程合并和构建产物，不要直接假设 Python 历史重建是根因。
- 重要回归根因：旧快照替换 IIFE 与 chunk1 concat 形成竞态；已移除快照替换 IIFE，并保留 buildArt/_mergeChunk 两层防线。

### 8.3 阅读器全文链路与字段契约

全文显示有三个前端来源层级；`api/article.js` 内部还包含快照和实时提取分支：

```text
文章 item
  ├─ 1. 构建/刷新内嵌全文：chunk 用 full_content，远程快照/刷新可能用 fc
  │     buildArt(): fc = it.fc || it.full_content || ''
  │     a.fc > 100 → fetchFullArticle() 立即插入 .r2-fulltext
  ├─ 2. 当前页面 _articleCache[url]
  │     同一页面再次打开直接复用 API 返回结果
  └─ 3. Vercel https://starhub-refresh.vercel.app/api/article?url=...
        ├─ 快照 map：rss_api_snapshot.json 的 item.u + item.fc
        └─ 实时抓取：安全 URL 校验 → JSDOM → GitHub/YouTube 特殊提取
                          → Readability 通用提取 → meta description 兜底
```

- `openReader()` 负责设置 `curArt`、标记已读、渲染 reader2；`renderReader()` 输出标题/摘要并调用 `fetchFullArticle()`。
- `_insertFulltext()` 将 HTML 直接插入 `.r2-fulltext`；无 `<p>` 的纯文本会按空行拆段并自动包裹 `<p>`。
- `api/article.js` 必须保留：`Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods: GET, OPTIONS`、`Access-Control-Allow-Headers: Content-Type`；OPTIONS 必须返回 204，否则 GitHub Pages 跨域兜底会被浏览器拦截。
- API 常量当前为 `FETCH_TIMEOUT=8000ms`、内存缓存最多 500 条、TTL 4 小时；Vercel 函数超时在 `vercel.json` 为 15 秒。
- 排查全文时必须区分“内嵌全文字段为空”和“跨域/API 提取失败”；不能只在 Vercel 域名上 curl，至少要从真实 GitHub Pages origin 做浏览器 fetch，并检查 `#r2Inner .r2-fulltext`。

### 8.4 部署与验证闭环

代码 push 不会触发 `update.yml`（仅 schedule + `workflow_dispatch`）。涉及 RSS 页面或 `api/` 的改动按以下顺序执行：

1. 修改源文件：页面改 `build_rss_aggregator.py`，API 改 `api/*.js`；不要编辑自动生成的 HTML/chunk。
2. 本地验证：`python -m py_compile build_rss_aggregator.py`、生成本地产物、`node --check` 主 JS；运行对应 `.deploy-tmp/verify_*.cjs`。
3. `git fetch origin` 后 **merge** 最新 `origin/main`（禁 rebase/amend，见 §7.3），只提交源文件和必要文档，避免把本地 VERIFY 产物提交。
4. push 后执行 `node .deploy-tmp/trigger-workflow.cjs`；轮询 `.deploy-tmp/poll-run-dedup.cjs`，注意构建提交可能产生第二个 `dynamic` run。
5. 必须确认两类 run 都 success：源码 workflow run 与构建提交触发的连锁 run；最近布局改动对应 `34025327944`、`34025453474`，提交 `44b2d60`。
6. 线上静态验证：`node .deploy-tmp/verify_online_sidebar.cjs`，当前证据为 HTTP 200、13/13 PASS。
7. 浏览器 E2E：`node .deploy-tmp/verify_ai_sidebar_e2e.cjs`，使用 Playwright 1440×900 与 390×844 两个 context；当前证据为 20/20 PASS、两端无 JS 错误。
8. 页面交互回归至少覆盖：桌面 AI 左侧 sticky/独立滚动、移动 AI 按钮抽屉、reader2、src-panel、ART 唯一数、全文插入、无图卡片不带 `.cover-card`。

最近相关提交：

| 提交 | 变更 | 关键证据 |
|---|---|---|
| `27232cf` | P0 前端时区盲日期比较修复——08:15 时间漂移根因 | `test_frontend_tz_regression.py` 回归测试 |
| `8d8933e` | 维度护栏 v3（全文件取维+漂移自愈失效缓存）+ 嵌入缓存值类型过滤 | `test_insight_guard_v3.py` + `test_insight_embeddings.py` |
| `eba5d2f` | 洞察模块优化 D1-D4（嵌入缓存/查询批化/轻重分级/bad_date 降权） | TDD spec: `docs/superpowers/specs/2026-09-14-insight-optimization-spec.md` |
| `521604d` | RSS 源配置外置到 rss_sources.json，新增单源实时刷新与 Twitter/X 分类 | 1014 源，8 分类 |
| `f7eaa87` | RSS 抓取并行化（全局 12 并发 + 每域名 2 + 域级熔断）与 JSON 原子写 | 构建时间显著缩短 |
| `d5da7a9` | Zen 免费模型轮询使用，单模型限流自封并自动切换 | 指数退避 5→10→20→40 分钟 |
| `c6d1f8d` | RSS 全信源内容趋势追踪增强（14 天滚动快照 + 关键词生命周期） | `rss_trend_history.json` |
| `44b2d60` | AI 动态流改为桌面端左侧常驻侧栏（≥1280px） | 静态 13/13、双视口 E2E 20/20 |
| `a16b13a` | 去除快照替换竞态；ART/_mergeChunk 去重；无图文章回退纯文字卡 | 去重与卡片墙 E2E：DUP=0 |

2026-09-17 之后（本手册基线 `e3c0313` 起）的 25 个实质提交全部集中在**每日深度洞察管线**与 **Agnes 多 key**，详见 §8.12–§8.14。

### 8.5 维护禁忌与快速定位

- 不要直接编辑 `rss-aggregator.html`、`rss-data-*.js`；workflow 会重新生成并覆盖。
- 不要直接编辑 `daily-insight-history.html` 与 `ai-daily.html` 中 `daily-insight-start/end` 标记内的板块；由 `build_daily_insight.py` 生成/注入。
- 修改 `buildArt()` 字段时，必须同时检查 Python item 字段、chunk JSON、`api/rss.js` 远程 item 和 `api/article.js` 快照字段。
- 修改 AI 面板 DOM/CSS 时，同时验证 `reader2`（z-index 70）、`src-panel`（80）、`share-modal`（100）及 `scrim`，不要把桌面常驻栏误当成 `body.ai-open` 浮层。
- 线上验证不要只看静态字符串；布局必须用真实浏览器 computed style + 双视口交互验证。
- 任何令牌、密钥、Cookie、GitHub/Vercel Secret 都不写入手册、临时脚本或提交。
- 不要直接编辑 `analysis_snapshot.json`；由 `insight_engine.py` 构建时生成。
- 修改 `insight_engine.py` 后必须运行 `test_insight_*.py` 全套测试，确认维度护栏、缓存防御、嵌入类型过滤均通过。

### 8.6 洞察引擎集成（2026-09-08 ~ 09-14）

**核心模块**：`insight_engine.py`（~1984 行），替代原纯统计 `_run_analysis()` 管线。

**架构概览**：
```
构建时数据流：
  hot_snapshot.json + rss_history.json + trending_data
       ↓
  load_documents() 配额制（RSS 70% + 热榜 20% + Trending 10%）
       ↓
  build_index() 层级索引（子块 ~150 token）
       ↓
  SiliconFlow bge-m3 API embedding（本地 fastembed 回退）
       ↓
  手动余弦相似度检索（避 VectorStoreIndex 维度不匹配）
       ↓
  extract_keywords_llm() → cluster_topics_embedding()
       ↓
  generate_deep_insights() 三视角独立生成
       ↓
  RAGAS-inspired 评估 + 自纠错循环
       ↓
  analysis_snapshot.json（含 deep_insights / topic_clusters / cross_platform / hot_trends）
```

**关键设计决策**：
- **AgnesLLM 多 key 轮询**：遇到 429 自动切换下一个 key；非 429 错误重试当前 key 2 次
- **嵌入缓存**：`emb_cache.json` 按模型名隔离，5000 条上限，原子写；CI 用 `actions/cache` 持久化
- **三视角独立 LLM 调用**：core_trends / rss_insights / narrative 分别调用，避免 fallback 复制导致内容相同
- **维度护栏 v3**：全文件取维 + 漂移自愈失效缓存 + 值类型过滤 + NaN/TypeError 防御
- **轻量场/重场分级**：数据不足时走轻量路径（不携带旧 bad_date 名单）
- **趋势快照 stale 标注**：过期数据标记 stale 而非丢弃

**环境变量**：`AGNES_API_KEY`（必需，本模块支持逗号分隔多 key）、`AGNES_API_KEYS`（逗号分隔附加 key，与主 key 合并成池）、`SILICONFLOW_API_KEY`（embedding）

**配置**：`build_config.json` 控制开关、provider、max_documents 等参数

### 8.7 翻译引擎分流 v2（2026-09-08 定版）

**背景**：旧版批量补翻全打 Agnes，首屏几十条打爆上游限额（实测分钟级仅 1~2 次，agnes 429），反把全文翻译拖死。

**最终方案**：按场景分流

| 场景 | 服务端降级链 | 并发/限额 | 说明 |
|------|------|------|------|
| 全文/摘要按钮（mode='full'） | **统一一条链：GTX → MyMemory → Agnes → Zen**（`translateWithFallback`） | 并发 4，Agnes 不限额 | 低频高价值，用户主动点击 |
| 批量补翻（mode='bulk'，缺省） | 同一条链（浏览器端另有直连 GTX） | 并发 2，**Agnes 兜底上限 30 条**（`AGNES_FALLBACK_MAX`） | 防浏览器 GTX CORS 全灭时 bulk 流量打爆 Agnes 配额 |
| 构建期翻译 | Agnes → Zen → GTX → Bing → MyMemory | 翻译熔断（连续 5 次全失败暂停 5min） | 有界并发池（6 源并发） |

> 注意：运行时两种 mode **共用同一条降级链**，mode 只改并发数与 Agnes 条数上限，不存在"全文优先走 Agnes"。线上实测（2026-09-18，Vercel）：GTX 因出口 IP 被 Google 频率限流长期 429，实际大量落在 MyMemory，配额打满后才轮到 Agnes（`engine=agnes` 已实测拿到有效译文）。

**Zen 免费模型轮询**：

> ⚠ **实际可用性（2026-09-18 核）**：Zen 在文档里仍是降级链的一个层级，但**当天 CI 构建日志中三个模型逐个"限流/故障，自封 5 分钟并切换下一模型"，构建期翻译统计 `Zen: 0`**（同场 Agnes 40 次成功）。即 Zen 目前实际贡献为零，不要把它当作可依赖的容量层。注：本轮仅证实到"自封/切换"这一层，未证实具体 HTTP 状态码与起始日期。
- 默认模型：`ling-3.0-flash-fin-free`、`big-pickle`、`mimo-v2.5-free`
- 指数退避自封：5→10→20→40 分钟封顶 1h，成功清零
- 连续 2 次超时/网络故障自封模型 5 分钟
- 粘性鉴权：实测可用的 token 保持，401/403 后回退 "public"

**Agnes 指数退避**：HTTP 错误或连续 3 次空响应 → 自封 5→10→20→40 分钟，成功清零

### 8.8 RSS 并行抓取与原子写（2026-09-07）

- **全局 12 并发** + 每域名 2 并发 + 域级熔断（连续失败暂停该域）
- **JSON 原子写**：`_atomic_write_json()` / `_atomic_write_text()` 先写 `.tmp` 再 `os.replace()`，防止进程中断导致数据损坏
- **增量构建历史填充**：跳过的源从 `rss_history.json` 填充历史 items，确保 72h 滚动窗口数据不因增量构建而丢失

### 8.9 热榜 40 平台与 AI 动态面板增强

- 热榜从 14 平台扩展至 40 平台（+26 商业/资讯/生活/娱乐）
- 热榜分类筛选行：全部/热搜/科技/财经/资讯/生活
- 热榜并入 AI 动态面板双 Tab（AI 动态 + 热榜）
- `hot_snapshot.json` 加入版本控制，CI 构建后提交部署
- `hot_history.json` 跨构建持久化

### 8.10 RSS 阅读器媒体播放系统

- 阅读器内嵌 YouTube 视频 / 播客音频播放
- 媒体嵌入代码移入构建模板（防止被构建覆盖）
- iframe 安全加固（sandbox 属性）+ 错误降级 UI
- 关闭后不再后台播放

### 8.11 前端关键修复（2026-09-07 ~ 09-14）

| 修复 | 根因 | 方案 |
|------|------|------|
| P0 时区盲日期比较 | 前端用 `new Date()` 当前时间做日期比较，08:15 时间漂移 | 改用源数据 pub_date 静态比较 |
| chunk1 加载超时拒绝合并 | 37MB 大块慢网络下必现信源丢失 | 超时不再拒绝，改为接受已加载部分 |
| chunk0 假成功守卫 | 截断/损坏 JSON 显示误导性空态 | 显式报错 toast 替代空态 |
| KeyError 'color' | RSS 源缺 color 字段导致静默失败 | 缺省颜色兜底 |
| Agnes 思考型模型耗尽 max_tokens | AI 摘要为空 | `enable_thinking: false` 关闭思考 |
| AGI Hunt 移动端超时 | 12 频道并行触发移动端 6 连接槽排队 | 改为顺序请求，5s 单请求 + 30s 总超时 |

### 8.12 每日深度洞察管线 build_daily_insight.py（2026-09-15 ~ 09-18，当前 4082 行）

与 `insight_engine.py`（服务于 RSS 页 AI 动态面板）**完全独立**的第二条洞察管线，产出 `ai-daily.html` 内嵌的「每日深度洞察」子板块 + `daily-insight-history.html` 独立历史页。由 `fetch_and_build.py` 在 `build_rss_aggregator.main()` 之后调用。

**数据流**：
```
四源叠加：rss_history.json(近168h=7天) + hot_snapshot.json(40平台) + AIHOT API + AGI Hunt(12频道×2天)
     ↓ Phase 1.2 硬过滤（标题党/广告正则黑名单 + 质量过滤）
     ↓ 切片：CHUNK_SIZE=300 token / overlap=50，上限 MAX_EMBED_CHUNKS=30000
     ↓ Embedding：SiliconFlow bge-m3（1024 维，批 32）→ numpy 向量缓存增量
     ↓ FAISS 索引 + 混合检索：向量(每查询 TOP_K=200) + BM25(窗口10000，
       非RSS优先+近期RSS补满) → RRF 融合(K=60)
     ↓ 查询构建：MAX_QUERIES=80（热榜+AIHOT+AGI Hunt+RSS 标题）
     ↓ 重排序(双热度) → 事件组装(Jaccard 0.35) → 语义聚类(余弦 0.75)
     ↓ MIN_EVENTS=3 / MAX_EVENTS=12 / 深度解读 Top3
LLM 生成（Agnes agnes-2.5-flash，enable_thinking:false，多 key 轮询）：
     Phase 1   全事件摘要+主题导语（携带全局检索上下文前 12000 字符）
     Phase 1.2 丢弃 [信息不足] 占位事件
     Phase 1.3 跨源去重（label 相似 → summary 互含 → 聚类级实体去重）
     Phase 1.5 事实核查 _verify_faithfulness（对照检索原文）
     Phase 1.6 自审（质量问题清单 → LLM 修正，最多 1 轮）
     Phase 1.7 自审后最终去重
     Phase 1.8 AI 主题硬过滤（非 AI 分类 + label 无 AI 关键词 + 全非 AI 源
                → 丢弃；清除 BBC 驾考类噪声，但保留给破茧栏的残差素材）
     Phase 2   Top3 深度解读（COASR prompt：事件还原/影响分析/信源分歧/
                金句/展望 outlook/置信度）
     Phase 2.5 RAGAS 评估-修正闭环（见下）
     Phase 3.1 破茧栏 + daily-insight.json
     Phase 3.3 跨天事件关联（Jaccard 0.5 匹配 30 天历史 → new/ongoing/escalating）
     Phase 4   daily-insight-history.html + 注入 ai-daily.html
     Phase 5   质量追踪 daily_insight_tracking_history.jsonl
```

**RAGAS 质量闭环（2026-09-18 定版）**：
- Judge LLM：**mimo → agnes 两级降级链**（`_FallbackJudgeLLM`）。mimo-v2.5-free 经 OpenCode Zen 端点调用（`_MimoLLM.API_URL = https://opencode.ai/zen/v1/chat/completions`，伪装 OpenCode CLI 请求头，与 `api/translate.js` 的 translateZen 同一端点）。OpenRouter 免费模型中转层已移除（长期不通，`_OpenRouterLLM` 类仍残留但不在链路上）。
- ⚠ **主力 mimo 实际从未生效（2026-09-18 实证）**：因为 mimo 走的就是上面那个已被封的 Zen 端点，**它与 Zen 是同一个故障源**。当日线上产物 `daily-insight.json → quality.meta.call_log` 6 条全部为 `{"model": "agnes-2.5-flash", "fallback": true}`，即 **0/6 命中 mimo，三个分数一直由 agnes 打**。"mimo 评估一致性优于 agnes 故做主力"是配置意图，不是运行事实。
- ⚠ **`judge_model` 标签历史缺陷（已修）**：`_FallbackJudgeLLM.model` 在构造时取主模型名且降级后不更新，而 `quality.meta.judge_model` 直接读它，导致标签长期谎报 `mimo-v2.5-free`。现改为 `_effective_judge_model()` 从 `_call_log` 取实际模型（单一模型直接报名名，混合报 `mixed(a+b)`，无记录才回退配置值），并新增 `judge_model_configured` 保留配置值以便对照。**读历史产物时注意：2026-09-18 之前的 `judge_model` 不可信，要看 `call_log`。**
- 触发修正的条件（任一即触发，最多 1 轮）：overall < 0.70，**或**任一维度低于最低线：coverage ≥ 0.75 / faithfulness ≥ 0.88 / relevance ≥ 0.75。
- 交叉验证已开启（`daily_insight_cross_validation: true`）：v1/v2 + v1' 三样本**逐维取中位**（`_median_eval_samples`），不是加权平均；同内容复评漂移实测可达 ±0.05，所以采纳阈值要求 `overall > 原分 + 0.02` 且 faith 不明显劣化，否则回滚快照并立即收尾（回滚后重评=纯噪声）。
- **2026-09-19 起主判正式为 agnes**：`build_config.json` 的 judge_provider/model 改成 agnes/agnes-2.5-flash，代码默认值同步（配置缺失也不会回到从未打通的 mimo 403 路径），每期少一次无效 403 探测。`_FallbackJudgeLLM` 仅在显式配 `mimo` 时才包装。
- ⚠ **`quality` 现在描述 shipped 报告**（`_confirm_shipped_report_eval`）：预算收口后对最终 12 条再复评一次，草稿分（回收/去重/收口前）保存在 `quality.meta.draft_eval`，`meta.eval_stage` = `shipped_report` / `draft_only`。此前 `quality` 描述的是回收前草稿——07:14 期指标写着"漏了霍奇猜想"，而当天报告第 4 条就是它。
- ⚠ **合成分必须自证降级**：三样本全挂时写出的 0.5 带 `meta.degraded=true` + `eval_samples=0` + `prompt_variants=0`，并在 CI 打 `::warning::`；否则与真实 1 样本 0.5 完全无法区分（04:00 期假崩分就是这样静默覆盖了一次真实评估）。
- 评分原始输出记录在 `daily-insight.json` 的 `quality` 字段，可回溯。
- **现行路线（2026-09-19 起）**：终版口径观察期 + 候选方案与决策树见 `docs/superpowers/plans/2026-09-19-daily-insight-shipped-baseline.md`；
  其上游设计依据（G1/G2 与四条分歧判断）已从浏览器下载目录搬入仓库：
  `docs/superpowers/specs/2026-09-19-daily-insight-g1g2-design.md`、`docs/superpowers/specs/2026-09-19-daily-insight-g1g2-v2-judgment.md`。
  讨论 relevance、claim/实体中间层、rerank、12→16 预算之前先读这三份，避免重复立项。

**R13 观察期收口 + R14 批1（2026-09-19 22:40 北京时间，远端 `1703e4dafe`）—— 四条易被无声破坏的事实**：
1. **观察期已收口，结论是"没达标"**：终版口径窗口**冻结在 9 期**，三维同时达标 **1/9**（rel 2/9、cov 4/9、faith 8/9）。
   原计划里的**阶段 B（对照面蒸馏清单）已撤回**：它的"池子构成漂移=共模因子"前提只在 n=7（全挤在同一天 5 小时内，
   `chunks_total~agihunt_count` r=+0.97 的时间趋势）成立，**在 36 期草稿口径上 r 从 −0.73 塌到 −0.24 不复现**。
   教训写死在这里：**7 个连续时间点的相关系数量到的是时间趋势，不是因果；提方案前先拿大样本复现。**
2. **唯一跨样本复现的输入侧变量是 `deep_share`**（`has_analysis_count/total_events`）：cov r=+0.28(n=29)/+0.33(n=37)，
   rel r=+0.29/+0.30。根因是 `DEEP_ANALYSIS_TOP_N=3` 对 12 槽 → 9 条结构上没有"意义/影响"字段，**cov 的天花板是深度预算不是检索**。
   另：`MAIN_TOPICS = {"ai","programming"}` 让运维/工具类条目白拿 30 分相关性满分 → 主榜一半槽位并列在 62 分地板（rel 失分的直接成因）。
3. **台账 `passed` 的口径已变，且聚合必须过滤 `eval_stage`**：新 `passed = overall≥threshold ∧ 三维达线`，
   缺维/NaN/bool → `None`（未知不得冒充达标）。历史 45 行里 `passed=true` 而三维未达线的有 25 行（旧判据只看 overall）。
   ⚠ `draft_only` 行的 `passed` 说的是草稿 —— 不做 `eval_stage` 过滤会把窗口的 1/9 读成 4/45。
4. **三条会静默失效的陷阱**（都已加钉）：
   ① `json.loads` 接受裸 `NaN`，而 `min(1.0, nan) == 1.0` → judge 吐 NaN 会被 `_clamp` 洗成满分并记 `passed=true`；
      凡把模型返回数值夹进区间处必须先 `math.isfinite`。
   ② 统计口径数据一律拉**远端** `daily_insight_tracking_history.jsonl`：CI 只写远端，本地副本停在 09-17（45 行 vs 本地 7 行）。
   ③ 阶段 C 的逐事件归因第一期为 0/3（全落 `unmatched_irrelevant`）：judge 写「事件12（…）」带序号，
      且长理由 vs 短标签用 Jaccard 永远过不了门槛 —— 现改为序号前缀优先 + 包含度且要求重合词元 ≥2（**误挂比归不上更坏**）。
      ⚠ 归因域必须按 `MAX_EVENTS` 收口（序号与文本兜底**两条路径同闸**）：草稿口径下 `clusters` 有 16 条，
      越界序号会挂到 judge 根本没评过的尾条上。

**R14 批2（2026-09-19 23:54 北京时间，远端 `f4f7a52e91`）—— 深度名额与两个口径修正**：
- **Phase 2 名额从"Phase 1 输出序前 3"改成"`editor_score` 前 3"**（并列保序）。旧写法与更晚执行的
  `_order_events_for_output` 是两套序：第 9 期实测榜首 68 分没有 `deep_analysis`，三条 62 分的反而有。
  ⚠ 这只修了**分配**，没动 `DEEP_ANALYSIS_TOP_N=3` 这个**预算** —— "67 分已过门槛但排第 4 拿不到名额"那类仍需拍板。
- **素材剪枝 `_filter_cluster_items` 必须在打分之前对全部簇执行**：原先只对入选深挖的簇补剪，而后段又用剪过的
  items 重算 `editor_score` 再排序 —— 等于**只给入选者降分**，会造出"榜首仍无深挖"的新变体（审查实测 75→62 被反超）。
- **`status=="degraded"` 的深挖不再计作 `has_analysis`**（前端也不再渲染五个空字段的壳）。
  ⚠ 这让 `deep_share` 的历史口径整体偏高，跨期比较要从批2 之后重算。
- **本地危险动作**：`test_daily_insight.py` 会把 fixture 直接写进真实路径
  （`daily-insight.json` / `daily_insight_history.json` / `daily-insight-history.html` / `ai-daily.html`）。
  CI 有 "Restore worktree after insight tests" 兜住，**本地没有**。跑完根脚本别提交这些产物，
  也别拿被注过的本地 `ai-daily.html` 量红线 —— 要量就拉线上 `https://Kwei168.github.io/starhub/ai-daily.html`。

**推送 docs 的时机（09-20 06:20 北京，第二次实测坐实）**：
- 22:06:06Z 的 `39a48b20cd`（含 §10/§11 全部新内容）被 **22:00:28Z 起跑、22:16:00Z 提交**的整点构建
  `5b070527f0` 按文件名回滚成旧 blob（计划文档 51869B→40986B、HANDOFF 76838B→75129B，blob 逐提交核过）。
- **规则**：Data API 推 docs 之前必须列 run 并确认
  ① 没有 `status!=completed` 的 run，② 没有"`created_at` 早于本次推送"的 completed run（它的 Commit 步骤可能还没走）；
  整点 `HH:00:2xZ` 那场约 15 分钟后才提交 → **安全窗口只有"上一场 Commit 落地之后 ~ 下一个整点检出之前"**。
- **推完必须复查** `tools/remote_drift_check.py HANDOFF.md <plan.md>` 报 `内容不同=0`；
  只信 `gh api …/commits/<sha>` 返回成功不够，工作树里的旧 docs 会回头覆盖它。
- ⚠ 我那次吞档的直接原因是**守门 jq 表达式本身写错**（`.[]|"\(.databaseId@…)"` 非法 → 变量空 → 误判"无在跑构建"）。
  守门命令要和判据一起被验证过才算存在；照抄上面两条判据，别再自创表达式。

- **四条容易被无声破坏的设计不变量**（原先只写在 09-18 计划里，代码只有半句注释）：
  1. `TOPIC_TAXONOMY`（`:100`）**顺序敏感**：`ai` 必须排第一，否则"英伟达股价"这类科技金融交叉事件会被判去非科技类、掉出主报告；改顺序=改产品口径。
  2. Phase 2 证据包铁律（`:3001`）：同源 RSS 全文**只能用来交叉核对数字与信源分歧，不得作为引用编号来源**，`citations` 只许引上方素材 `[n]`；且别的事件里出现的人物/公司/数字严禁嫁接本事件主角（06:12 期张冠李戴实证）。这条是"每条洞察都能跳到原文"红线的技术支点。
  3. 深度分析门槛：事件级 4 维快筛权重 40/30/20/10（借 BestBlogs v4），`MIN_DEEP_SCORE = 55`（`:2163`）以上才进 Phase 2；`DEEP_ANALYSIS_TOP_N = 3`。
  4. 破茧栏选取必须**排除全部主类别**后正向选非科技 topic，不是拿主事件筛剩的边角料兜底。

**破茧栏（反信息茧房）**：
- 设计意图：展示 AI/科技**之外**的世界大事，不是主事件筛剩的边角料。
- `_select_bubble_events` 从主事件之外的残差素材（retrieved 未入选 chunks）中选取，与 30 天阅读画像（`_build_read_profile`）交集最小的优先，每源取代表条目，约 5 条；卡片含 label/summary/选取理由。
- 09-18 重构（`07b9add`）：旧版从聚类候选选，与主事件重复率高；现改为残差池选取并补链接。

**关键参数速查**（均在文件头部常量区，部分可被 build_config.json 覆盖）：

| 常量 | 当前值 | 调参历史教训 |
|---|---|---|
| `MAX_QUERIES` | 80 | 40→50→80，提升话题覆盖 |
| `RETRIEVAL_TOP_K` | 200 | 100→200 扩覆盖 |
| 全局上下文截断 | 12000 字符 | **曾扩到 16K 导致 LLM 幻觉、faithfulness 暴跌至 0.64，已回退 12K（`747b556`），不要盲目再扩** |
| `MAX_EVENTS` | 12 | 12→15→12 回调，15 时尾部事件质量崩 |
| `BM25_WINDOW` | 10000 | 非 RSS 优先入窗，剩余预算给近期 RSS |
| `INSIGHT_RSS_HOURS` | 168 | 7 天窗口支持跨天趋势检测 |

**AGI Hunt Agent API 合规守则**（`_fetch_agihunt`，09-18 落地）：限速 0.5 次/秒（每请求间隔 ≥2s）；429 按 Retry-After 退避且当天停拉；401 立即停止（密钥无效）；426 拉取 `/skill/version` 更新版本号后重试一次；取当天+昨天两天数据扩覆盖。

**本地诊断**：`python diagnose_coverage.py` 取 `daily_insight_chunks.json` 前 80 条近似评估上下文，与当日 events 对比给出覆盖率缺口的方向性线索（分母为近似，勿当判据；要精确归因需先在 `_build_ragas_context` 里把入选 chunk_id 写进 `daily-insight.json → quality`）；历史规格文档在 `docs/superpowers/specs/2026-09-17-daily-insight-*.md`。

**修改守则**：
- **CI 质量门禁分两级**（`update.yml` 第 6/7 步，位于恢复缓存与任何构建之前）：
  - **A 语法（blocking）**：`py_compile *.py` + `compileall -q tests` + 逐个 `node --check api/*.js`。纯静态、无网络无副作用，失败即中断——这正是 `4819686` 那个未闭合 `"""` 能连续数天静默失败的原因。
  - **B 洞察测试（advisory，`continue-on-error: true`）**：跑 `test_insight_engine / test_insight_guard_v3 / test_insight_bad_date / test_daily_insight`。之所以不阻塞：本 job 是 stars/RSS/ai-daily/每日洞察的唯一产出者且负责 Vercel 部署，任何环境相关断言翻红会冻结每天 5 个定时档、连一行热修都发不出去。**在 CI 里连续观察稳定后再摘掉 `continue-on-error` 收紧。**
  - B 步骤用 step 级 `env` 把 6 个上游 key 全部置空：测试不需要凭证，而 `test_insight_engine.py` 有 10 处 `run_analysis` 会经 `insight_engine.py:43` 拿真 key 打真实嵌入 API。
- **新增门禁测试必须离线自洽**，且不得依赖环境变量的存在与否。已踩过的三个坑（都是"本地绿、CI 红"）：
  - `insight_engine.py:664` 的 fastembed 回退分支**不受 `_SF_KEY` 门控**，CI 装了 fastembed 就会改变 `_get_embeddings` 返回值 → `test_insight_guard_v3.py` 必须显式 `ie.FASTEMBED_AVAILABLE = False`。
  - `_MimoLLM.api_key` 取 `ZEN_API_KEY` → `OPENCODE_KEY` → `"public"`（2026-09-18 前是 `os.environ.get("ZEN_API_KEY", "public")`：空串不回退、也不读 OPENCODE_KEY，与 `build_rss_aggregator._ZEN_KEY` 语义不一致，已统一）。测试断言默认值前必须把**两个**变量都 pop 掉，否则 CI 里必红。
  - `rank_bm25` 用**无平滑** Okapi IDF `log(N-df+0.5)-log(df+0.5)`，**df 恰为窗口一半时 IDF=0、全部得分归零**。构造 BM25 测试语料时关键词不能铺满半数文档（旧 fixture 是 5000/10000，正好中招）。
- 任何生成/评估参数改动后，跑 `python test_daily_insight.py` + `pytest tests/daily_insight/`（**注意：当前 CI 环境未装 pytest，`tests/daily_insight/` 实际从未被执行过**）。
- ⚠ `test_daily_insight.py` 会**真实写盘** `daily-insight.json`、`daily_insight_history.json`、`daily-insight-history.html`、`ai-daily.html` 四个受版本控制的产物（用测试桩数据覆盖当日真实内容）。跑完必须 `git checkout HEAD --` 这四个文件再提交，否则测试数据会上线。
- Faithfulness 相关改动必须看下一构建的 `daily-insight.json → quality`，不能只看构建成功。
- FAISS 重建前必须先 `_save_vector_cache`（`8fcb97d`），否则崩溃丢 embedding 导致下次全量重嵌。

### 8.13 RSS 快照出仓（2026-09-17/18）

`rss_api_snapshot.json` 已达 **82MB** 并拆分为 `_1.._N` 多文件，提交进 git 导致 Actions checkout/fetch 超时。处理：
- 从版本控制移除并 gitignore（`ee0e4fd` + `e400660` 从 git add 列表剔除）。
- `api/rss.js` 的 `loadSnapshot()` 自动合并主文件 + 分块；本地文件缺失时回退实时抓取。
- **快照同时被 `update.yml` 的 prune 步骤在部署前 rm -f 删掉**：线上 `loadSnapshot()` 恒为 null，`?meta=1` 实测恒返回 total=0。所谓「快照优先」在生产里从未生效，API 实际走 refresh + 前端分批实时抓取。
- 连带影响：**增量构建的 `meta.last_fetch` 状态不再能从 git 恢复**，每次全新 checkout 后第一场构建按 full 逻辑补偿；本地跑 `build_rss_aggregator.py` 时无快照属正常。

### 8.14 Agnes 多 key 轮询统一（2026-09-18）

- 新方案：`AGNES_API_KEY`（主）+ `AGNES_API_KEYS`（附加，逗号分隔），合并成 key 池；429 时轮转下一个 key，非 429 错误重试当前 key 2 次。当前账号侧共 4 个 key（**池大小以 Secret 内容为准，代码不写死数量**）。`AGNES_API_KEYS` 已覆盖全部 6 个调用点：`build_rss_aggregator.py`、`build_ai_daily.py`、`build_daily_insight.py`（`_LLM` 类）、`api/translate.js`、`insight_engine.py`、`fetch_and_build.py`（AI 态势摘要）。
- **主 key 逗号切分已全量统一（2026-09-18）**：6 个调用点（`build_rss_aggregator.py:152`、`build_ai_daily.py:531`、`insight_engine.py:247`、`build_daily_insight.py:_init_llm`、`fetch_and_build.py:generate_ai_summary`、`api/translate.js:AGNES_KEYS`）现在都是同一语义：主 key 与附加 key 各自逗号切分后合并成一个池。**多 key 放 `AGNES_API_KEY` 或 `AGNES_API_KEYS` 都安全**。`fetch_and_build.py` 顺带补上了换 key 重试（此前只发一次、失败即放弃）：**先建池再判空**（避免主 key 缺失时漏用附加 key、或主 key 全逗号时零输出静默返回），且只在 429/5xx/超时/JSON 失败时换 key，401/403 立即停止（换 key 也是白烧）。
- **注意 key 池不去重**：`AGNES_API_KEY=k1` + `AGNES_API_KEYS=k1,k1` 会得到 3 个相同 key，轮转只是在同一 key 上烧尝试次数。Secret 内容自己保证唯一。
- **已修复（2026-09-18）**：`insight_engine.py` 的 `configure_llm()` 此前仍读旧编号式 `AGNES_API_KEY_2/_3`，而 update.yml 已停发这两个变量，该引擎实际退化为单 key。现改为与 `build_rss_aggregator.py:152-155` 同语义的池化方案：主 key 逗号切分 + `AGNES_API_KEYS` 逗号切分合并，**主 key 缺失时附加 key 仍生效**（不会静默退回 MockLLM）。
- **回归测试**：`test_insight_engine.py` 新增 4 例覆盖 key 池（单 key→`extra_keys` 必须为 None、主 key 逗号展开、主+附加合并且空白/空段被清洗、仅附加 key 时仍建 AgnesLLM）。全套 86 例当前 **全绿**——此前长期红着的 2 例 RSS 时效测试是因为 `recent` 硬编码成 `2026-09-13`，72h 窗口一过必然失败；已改为 `_recent_bjt_iso()` 相对时间，勿再写死日期。
- 踩坑：`_AGNES_KEY_IDX` 等全局变量在函数内使用前必须先 `global` 声明（`1d2a93d` 修复过一处顺序 bug）。

---
### 8.15 大产物第二次出仓：Pages 改由 workflow 发布（2026-09-30）

**这是 §8.13「快照出仓」的同一类问题第二次发生**，不是新发明。机制：`rss-data-1.js` 每场 55.4MB 被
`update.yml` 的 `git add` 提交进 main，git 只在内容变化时新增对象且**永不回收**，于是远端全量历史涨到
**5.23 GiB**（实测：完整克隆 2028 提交、`size-pack` 5,480,050 KiB）。全仓 15,183 个 blob 解包 105.21 GB，
按家族：`rss-data-*` 45.71GB / `rss_history.json` 18.15GB / `rss_api_snapshot*` 17.62GB / `rss_cache.json` 7.12GB
/ `translations.json` 5.72GB / `hot_history.json` 3.75GB / `rss-aggregator.html` 3.37GB；其中约 **50.8GB 是已停产
仍挂在历史里的死量**（`data-2` 自 09-21 僵尸块修复后是 128B 空壳、每场 blob 恒定）。
详见 `docs/superpowers/specs/2026-09-20-git-repo-size-and-normal-flow-recovery.md` §7/§13。

**改法**：Pages 源从 `legacy/branch main` 改为 **workflow 发布 artifact**。依据是三个实测事实——
① 前端取分块是相对路径（`build_rss_aggregator.py:4579` `sc.src='rss-data-'+i+'.js?v='+BUILD_TS`），换通道不改任何 URL；
② 分块只写不读（`:6266/:6276/:6305` 全是 `"w"`），服务端不读仓库文件（Vercel 由 CI 用 CLI 部署，
`update.yml` 的 prune 在部署前 `rm -f rss-data-*.js`）；③ Pages 限额里 **10 builds/hour 对 workflow 发布不适用**
（我们每小时一场，legacy 源下这条软限一直在逼近）。

**范围刻意收窄**（都是实测，不是想当然）：
- 只有 `rss-data-1.js` 及以后的块退出提交；**`rss-data-0.js` 继续提交**，因为
  `tests/rss_composite/test_diverse_realdata.py:32` 拿"已入库的真实分块"当数据源。
- 其余 JSON/HTML **全部留在 git**：`trending_snapshot.json:432`、`known_categories.json:716`、
  `descriptions_zh.json:722`、`rss_sources.json:310` 都是 `open()` 读回来的**跨场输入**，不提交就等于削功能。
- `test_stale_chunk_guard.py` 的"旧块清空不删除"**行为保留、依据更换**：原来防的是 `git add` glob 表达不了删除，
  切换后那条依据不再成立，现在的依据是"页面按索引取块，删文件即 404"。别拿旧理由改回 `os.remove`。

**对抗审查抓出两条由本次改动引进的 P0**（都已修，记录在此以防回退）：
1. staging 若照**工作目录**整拷，会把 `.gitignore` 排除、却由 cache `restore-keys` 放回磁盘的原始语料第一次公开发布
   —— 实测本地合计 **398M**（`rss_cache.json` 110M / `rss_history.json` 62M / `rss_api_snapshot.json` 41M /
   `daily_insight_*` 向量 146M）。legacy 发的是 **git 树**，所以当时 staging 按 `git ls-files` 取清单，
   并保留 Jekyll 的 `.`/`_` 排除（实测今天 `/_bra.py`、`/.gitignore` 就是 404）。
   **2026-10-02 更新（§8.16）**：`git ls-files` − 排除表这套已被**白名单**取代（用户裁决 18:12）——
   排除表挡不住"没想到的那一类"（18:12 全量枚举：公开集仍有 15 项／0.48 MiB，含 4 张调试截图与根级
   构建期 json）。这条 P0 的**理由不变、且被白名单更严格地满足**：正文里已经没有任何"按目录取文件"的写法，
   `.`/`_` 项也在 A2 `test_staging_publishes_only_the_site_allowlist` 里被显式禁止。
   ⇒ 别把它改回"整拷"或"再补一行排除"，要公开新文件就改 `STAGE_ALLOWLIST` 那份名单（A2/A3 会逼你确认前端真的 fetch 它）。
2. `upload-pages-artifact` 的 `if-no-files-found` **默认是 warn**，空制品会被"绿发布"= 抹平站点。
   须显式 `error` + staging 里对**白名单每一项**做非空 `-s` 守卫（当前 8 项：4 个 HTML + `rss-data-0/1.js` +
   `hot_snapshot.json` + `rss_sources.json`）+ `deploy-pages` 的 `if` 依赖 upload 结果。

**cutover 顺序（错了就全站红，且窗口极窄）**：① 先按 §8.12 两条判据确认窗口 → ② `PUT /pages {"build_type":"workflow"}`
（**注意是 PUT，`PATCH /pages` 路由不存在，会回 404**；token scopes `repo/workflow` 够用）→ ③ 按具体路径推
`update.yml`/`.vercelignore`/两个 tests/spec → ④ 让下一场整点构建当验收载体。**没有先例时不要"先推再切"**：
legacy 源下 `deploy-pages` 直接失败。回滚 = `PUT build_type=legacy` + `source[branch]=main&source[path]=/`。
判据不许用"步骤绿"：看远端 `rss-data-1.js` 的 blob 是否停止每场变化 + 线上 `rss-aggregator.html` 能否加载新分块。

**cutover 已执行（2026-09-30 10:00Z，北京 18:00 那场）**，读数：

- 推送集落地 `328ea74786`（末行 `内容不同=0`），Pages `build_type=workflow`。
- `#1517` 起于 10:00:29、止于 10:26:32（**26 分钟**），`conclusion=success`；
  `Stage Pages site` / `Upload Pages artifact` / `Deploy to GitHub Pages` 三步全 `success`。
- **分块停止提交的直接证据**：该场的提交 `4ba4c70667`（10:24:56Z）带的文件清单里只有 `rss-data-0.js`，
  **没有 `rss-data-1.js`**；main 上那个块自此停在旧流程最后一场（`#1516`）的 `2051f899f3dc` / 55,710,750 B。
- **Pages 由 artifact 供数的直接证据**：同一时刻线上 `rss-data-1.js` = `60a18d6da7a3` / 57,259,873 B，
  与 main 的 blob **分叉**（线上比 main 新 = 分支源已不再是数据来源）。
- 每场进 git 的产物从 55.4MB 降到约 0.65MB（chunk0 仍提交）。**存量一分未减**：本地 `.git` 仍 8.7G
  （loose 7.1G + pack 1.6G），远端可达历史仍 5.23 GiB；那是 N4 与 G2 两次独立动作，需分别批。
- 我自己引进的连坐（staging 排在 Vercel 之前）已由 `5f213e4` 修掉并于 10:3xZ 推上（`02c53bad47`），11:00Z 那场起生效。


**同一天的构建时长恶化（与上面无关，但会影响推送窗口）**：`Fetch stars & build` 从 00:00 的 783s
涨到 08:00 的 **2966s**（1515 侥幸在 60 分钟内挤过；1513 跑到 51 分钟被 `cancel-in-progress` 顶掉，
1513/1514 两小时零产出，站点最后一次成功提交是 06:31Z）。实测特征：**RSS 抓取阶段 14→30 分钟，而日志行数
1110→1109（工作量没变）、错误构成也没变**（Bridge 116、429 各 5、403 各 3、timed out 各 5），GitHub 侧步骤
（Checkout 259s / Vercel 32s / 缓存）全程稳定 → 是**出网往返变慢**，不是 GitHub 配额、也不是活儿变多。
叠加翻译侧：15:00 那场 `Google-gtx HTTP 429` ×42、`Agnes TimeoutError` ×42、`Bing 401` —— 但 §8.7 早就记录
GTX 在出口 IP **长期 429**、Zen 构建期贡献为零，所以这是**慢性故障加重**，不是新缺陷。
可落地的最小改动有手册依据：**构建期翻译熔断（连续 5 次全失败暂停 5min）目前只在 RSS 侧有，
`build_ai_daily.py` 的 `_translate_to_zh` 这条五端点链上没有**，所以单条文本最坏要把整条链等满
（Agnes 20s → gtx 2×10s+退避 → Bing 10s → MyMemory 3×10s+退避 ≈ 60–90s），42 条就是约 28 分钟。




### 8.16 发布面收口：制品只发站点文件 + ② 的落痕活下来 + gate B 归零（2026-10-02）

**提交链**：`1dd35983d0fa`（批 10：tests/tools/build_logs/根级 .py/template.html 关出 Pages 制品）
→ `7eec12d6f7`（② 的常设判据 + 定序判据 + gate B 根因修复）→ `1cd6f91e22`（批 11：`api/` 与根级 `.md`
关出；② 的落痕挪到 Save cache 之前；新增未发布标红步）。

**制品面（现取 GET，含字节数）**
- 收窄前（15:00 场 head `f156bbff16` 之后线上实测）：`build_logs/2026-10-01.jsonl` 200／2,819,872 B、
  `tools/data_api_push.py` 200／24,232 B、`fetch_and_build.py` 200／38,898 B、
  `tests/rss_history/test_pages_deploy_wiring.py` 200／25,880 B。
- 批 10 后（15:26 复测）：上述全部 404，但 **`HANDOFF.md` 仍 200／84,323 B、`api/rss.js` 仍 200／42,671 B**
  ⇒ 批 10 只挡了 `docs/` 目录、没挡根级 `.md`；批 11 一起关掉（`grep -zvE '(^|/)(…|api)/'` + `grep -zv '\.md$'`）。
- 关 `api/` 的前提（13:16 点单时核过、15:2x 重取）：4 个入口共 13 处 `api/` 引用**全是绝对域名**
  `starhub-refresh.vercel.app`（同源 0 处），`.md` 只有卡片正文里 `<code>CLAUDE.md` 这类描述性提及、无 fetch。
- 消费者侧审计（`.deploy-tmp/_consumer_audit.py`，从页面正文抽同源可请求项逐个 GET）：
  4 个入口共 22 项（含 JS 拼接出的 `rss-data-0..11.js`）全 200。探针两处口径要记住：
  `about:blank`（iframe sandbox）不是请求；多 MB 文件 30s 超时会报 `000`（≠ 不存在，调到 120s 后 200／3.1 MB、6.5 MB）。

**② 的两半只有一半是真的（本轮最该记住的一条）**
`::error::Pages 缺件：<file>` 的点名已上线，但"跨场可查"不成立：按真实步序复演一遍才发现
Stage（第 27 步）写 `build_logs/<日>.jsonl` 的 `pages_missing` → `Save cross-build state cache` 是第 26 步
（**先跑完**）→ 第 28 步 Prune `rm -rf build_logs` 删掉 ⇒ 记录既不进缓存也不进 git。
只跑 Stage 正文的判据看不见它——那测的是"这段 shell 会写"，不是"写了还活着"。
另有一条我自己说错的：**Stage 带 `continue-on-error: true`（刻意不连坐 Vercel），所以缺件那场的 job 结论
仍是 success**，界面上只多一条 error 注解。
修完的形状：`Stage(26) → Save state cache(27) → Prune(28) → Vercel(29) → Log(30) → Upload(31) → Deploy(32)
→ Mark the run red(33)`，末步 `if: always() && steps.stage.outcome == 'failure'` + `exit 1`。
复演读数：`rc=1` 且点名 → 缓存快照含 1 条 `pages_missing` → Prune 之后快照仍有。

**gate B 从每场 1 failed 到 0 failed**：根因不是外因，是 `tests/daily_insight/test_tracer.py` 在 import 期
（= pytest 收集阶段）把 `build_daily_insight.TRACKING_FILE` 改成绝对临时路径，泄漏给同 session
"必须是根目录相对名"的守卫。改成 autouse fixture 里 `monkeypatch.chdir(tmp_path)` 即可——
写入点照样隔离，全局不再被污染。本地复现与 CI 同数（1 failed／424 passed）→ 修后整目录 415 passed
（`--ignore=tests/daily_insight/test_integration.py`：该文件本地单跑会挂，CI 里 5.25s 跑完）。

**体积读数**：`[growth] new blobs=1  0.011 MiB verdict=ok`（14:00 与 15:00 两场都是），
起点是 0.023~0.036 MiB/场；批 6~11 之后每场新增只剩 1 个 blob。

**新登记的判据与电池**（`tests/site_nav_drift/` 归 A3，A3 是 advisory 不冻部署）：
`test_pages_artifact_scope.py`（制品面双向 + 同源 api 前提）、`test_pages_missing_report.py`（② 正文三条）、
`test_pages_missing_lifecycle.py`（**步序**：落痕早于 Save、中间不许删 build_logs；标红步必须存在且不早于 Deploy）、
`test_pages_vercel_ordering.py`（Pages/Vercel 定序现状与被否掉的提案理由）；
电池 `tools/mut_artifact_scope.py`（S1/S2/S2b/S3/S4 + C1/C2）、`tools/mut_pages_missing_report.py`（A1~A4）。
动过 workflow 步骤要补跑被排除在每场构建外的 `tests/trim_guard/`（22 passed／20.3s）。

**仍未做、等点头**：#27 给 `Deploy to Vercel` 封顶（`timeout-minutes` + `continue-on-error` + 事后标红）。
"把 Pages 两步挪到 Vercel 之前"已被既有 A2 不变量否掉——它把"Pages 被 Vercel 拖慢"换成"Vercel 被 Pages 挡掉"。

**提交链补完（18:12–18:40）**：`01996af8e6` 拆掉 A2 里的日期定时炸弹 → `e519419ebc` 增长读数带"归属" →
`7c9c9d2332` 制品面关 `lib/` → `cee84b1666` **Stage 翻成白名单**（用户裁决 18:12）。

**两场连续绿（17:00 场 head `7c9c9d2332`／18:00 场 head `2c6ad48fa3`）的读数**：
A2 `392 passed`、A3 `27→29 passed`、gate B `425 passed / 0 failed`（此前每场 1 failed）、
`Created deployment for 7c9c9d2332…` + `Reported success!`；线上 GET：`api/*`、`HANDOFF.md`、`README.md`、
`CLAUDE.md`、`tools/*.py`、`tests/*`、`build_logs`、`fetch_and_build.py`、`template.html` **全 404**，
站点件全 200；Vercel 侧 `api/rss` 200、`api/news` 200、`api/translate` 405 ⇒ 关 Pages 制品没伤 API 主机。
17:00 场 `growth = new blobs=7 3.141 MiB verdict=ok` —— 逐个文件核过是批 4 的"日志每日一次提交"
（`build_logs/2026-10-02.jsonl` + `2026-10-03.jsonl` + 两个 summary + `.committed_date` + `.state_seed.done` + `known_categories.json`），
设计内、阈值 6 MiB 之下。

**日期炸弹（本轮最贵的一条教训）**：`test_summarize_consumes_what_the_writer_emits` 把日期写死成
`"2026-10-02"`，而写端 ts 来自 `datetime.now(_BJT)` ⇒ 北京跨 00:00 起每天必红；它在 blocking 的 A2 里，
16:03 那场因此 `completed failure`（部署整场冻住）。修法是把写端时钟钉住，另加一条"按记录自身日期分组"的控制。
⇒ **凡是断言里带"今天"的判据，都要问它 24 小时后/月末/跨年还成不成立。**
普查口径已跑：其余带日期的断言用的都是测试自造的固定输入或显式传参 ⇒ 无第二颗。

**归属这一层是电池教我补的**：`mut_history_growth.py` 的 H16（把 `bool(attributed)` 改成写死 `False`）
第一次跑出 **GREEN** —— 判据只验了 False 与"未知时缺席"，**没验 True**。补上 True 侧断言后 H16 转红，
H1~H16 共 16 个变异 0 逃逸。⇒ "0 逃逸"在补上这一条之前是假的。

**白名单化的证据与做法**（`cee84b1666`）：排除式名单在 18:12 的全量枚举前已经连漏三次
（`.md` 15:26、`lib/` 15:58、根级 junk 18:12），因为"只挡想得到的一类"。现在 Stage 只发
`STAGE_ALLOWLIST` = 4 个 HTML + `rss-data-*.js` + `hot_snapshot.json` + `rss_sources.json`；
A2 的 `test_staging_publishes_only_the_site_allowlist` 钉集合（多一项/少一项/出现 `.` 开头项都红），
并断言 A2 与 A3 两份名单逐个相同（名单只许一份）；A3 的 `test_published_set_is_exactly_the_allowlist`
在合成树上真跑正文。`test_frontend_fetched_names_are_served` 同时**收紧**：白名单之后"被跟踪"不再算来源。

**仍挂着的一条（本轮查出、未处置）**：`known_categories.json` 是**新的每场重写者** —— 最近 8 个自动提交里
4 个只有它一个文件（约 11 KB/场）。白名单已经让它不再公开，但它仍在 git 历史里每场新增 blob。
处置方向与批 2/批 3 同：出 `git add` 清单 → 进 `starhub-state` 缓存族 → 退出 git 树 + 反空转守卫。

**2026-10-02 20:26 把这条的代价量准了（`.deploy-tmp/_why_kc_churn.py` + `_measure_category_drift.py`）**：
① 每场重写**不是键序抖动**：远端 8 个触及该文件的提交、相邻 7 对逐对分类 = **7/7 content**（每次新增 1~11 个仓库，
删除 0），`order_only` 与 `same_bytes` 各 0 ⇒ "加 `sort_keys=True` 就能免掉重写"这个猜想被证据否掉，别再去改落盘顺序。
② 冷启动重算的真实代价**是可见的**：按 `fetch_and_build.py:738` 同一行口径复算（输入取自同一份
`users/Kwei168/starred` 响应，实测该响应 **175/283 条带 topics**，所以不能假设没有 topics），
**283 条可比对里 39 条会改判 = 漂移率 13.8%**。样例：`jerrywu001/cc-sessions-viewer` agent→coding、
`zhongerxin/Cowart` video→agent、`getopenscreen/openscreen` tools→video。
⇒ 结论：这条**不是"零成本清掉"的一笔**。文件的作用就是把首次判定的分类冻住（规则后来变了也不重判），
所以"缓存里改判 0"按构造必然为 0，不能当成"规则稳定"的证据。若要把 11.3 KB/场 换成缓存族，
**必须同批带播种**（从当前 git blob 回灌），并知道族一旦失效（改 path 清单 / 7 天到期 / 冷启动）就是首页 14% 分类跳动。
顺带测出：现 294 条里只有 283 条还在星标列表 ⇒ 有 11 个已取消星标的键永久滞留，文件只增不减。

**别学我犯的兩個错**：① 用 Edit 时把 `trending_snapshot.json` 连同换行一起挤进注释吃掉（靠"改完就与远端逐行 diff"才发现）；
② 新增判据里嵌 ASCII 引号 + U+2212 导致语法非法（靠 `py_compile` 才发现）。⇒ 改完判据先 compile、再与远端 diff，两步都不能省。

### 8.17 白名单的第二道闸：浏览器请求的名字必须出现在**跑出来的制品**里（2026-10-02 19:40）

**为什么白名单还缺一半**：`test_published_set_is_exactly_the_allowlist` 比的是"两份手抄名单相等"
（A2 的 `STAGE_ALLOWLIST` ↔ A3 的 `PUBLISH`）。页面真去请求一个名单外的名字时，那一项会**两边一起缺**，
相等照样成立 ⇒ 这类坏它天生看不见。补的判据把对账对象换成"合成树上真跑 Stage 正文得到的产物清单"
（复用已有 `staged` fixture，不再写第三份名单解析器）：`test_every_browser_referenced_name_is_published`。

抽取器 `_browser_refs` 认五种真形状、拒三类假形状（控制测试 `test_browser_ref_extractor_sees_every_request_shape`）：

| 形状 | 例 | 归一结果 |
|---|---|---|
| 标签属性 | `<a href="rss-aggregator.html">`、`<link rel=preload href="hot_snapshot.json">`、`sc.src='x.js'` | 原样（允许相对子目录） |
| `fetch('x.json')` | 含子目录时保留相对路径，不剥末段 | `sub/x.json` |
| 转义引号 | 生成端把 JS 塞进 Python 字符串时的 `fetch(\'hot_snapshot.json\')` | 同上（A2 第一版没吃反斜杠，漏过一次） |
| 参数化拼接 | `sc.src='rss-data-'+i+'.js?v='+BUILD_TS` | `rss-data-*.js`，对账方向是"制品名 匹配 引用模式" |
| **CSS `url()`** | `background:url(lib/cover.css)` | `lib/cover.css`（样式/字体走同一只手套） |
| **拒**：绝对 URL | `fetch("https://aihot.virxact.com/api/v1/items")` | 空（`:` 落不进名字字符类） |
| **拒**：data URI | `url("data:image/png;base64,iVBOR")` | 空 |
| **拒**：构建期文件名 | `open("known_categories.json","w")`、`OUT = "ai-daily.html"` | 空（没有请求语境） |

语境是按"现取四份生成端里真实出现的写法"定的，还**没**覆盖 `import('x.js')`、`new Worker()`、
`xhr.open('GET', ...)`、`navigator.sendBeacon()`（今天零命中）—— 边界写在判据注释里，将来出现就在那里加语境，
而不是现在就为设想中的形状加规则（加了也没证据）。
**注释会被喂假读数**（`_needs_rsync` 那次的同类账）：`_browser_refs` 现在先 `_strip_comments`
（`<!-- -->`、`/* */`、行首 `//`/`#`/`*`）再抽。今天这条不改判读数 —— 实测含注释与去注释抽出的是同一批 6 个名字，
是把"不改"从巧合变成性质；电池 **R6**（注释里写 `href="secret_state.json"` ⇒ 必须绿）与
**R1**（同样内容写成真代码 ⇒ 必须红）是同一行文本的两面。控制测试里也配了这对（带 `//` 前缀算空、不带算有）。

**线上那半用脚本对账，不进闸门**（`.deploy-tmp/_audit_live_refs.py`，20:18 现取）：判据读的是生成端源码
（CI 里 A2/A3 跑在构建之前，产物还不存在），而**出厂 HTML 里由数据带进来的引用**（条目摘要含 `<a href=...>`）
静态扫看不见 ⇒ 用同一个 `_browser_refs`（从判据文件 import，不留第二份正则）扫线上四个页面：
`index.html` 291,559 B/2 个引用、`ai-daily.html` 52,993 B 级 1 个、`rss-aggregator.html` 2,366,110 B/6 个、
`daily-insight-history.html` 206,495 B/1 个，**白名单外 0 个**；脚本对"某一页一个引用都没抽到"也当问题报
（抽取器在产物上失明不能算"没问题"），取数失败同样不作读数。


现取读数：四个生成端共抽出 6 个名字（`ai-daily.html` / `rss-aggregator.html` / `index.html` /
`hot_snapshot.json` / `rss_sources.json` / `rss-data-*.js`），全部发得出 ⇒ 白名单化没有砍掉任何浏览器请求。
顺带把 `CLIENT_SOURCES` 从 2 份扩到 4 份（补 `build_ai_daily.py`、`build_daily_insight.py`）：
那两份里的 `/api/v1`、`/api/query` 全是 aihot/algolia/arxiv/openrouter 的绝对 URL，分类器两类都不计 ⇒ 扩名单不判红，
只是让"以后有人往日报页加同源调用"能被看见。`_client_sources()` 现在会先断言四份文件都取得到（缺件时不许空跑）。

**变异电池**（`tools/mut_artifact_scope.py`）加了 R1–R5 五例并保留反向那半：
R1 合成源里加 `fetch('secret_state.json')` ⇒ 必须红且**红在自己身上**（`-k` 只选新判据，
四份真生成端一起喂，否则先红的会是"模式退化"那条控制）；R2 拼接形状 `rss-data-`+i+`.js` ⇒ 必须绿；
R3 外部域名 `.json` ⇒ 必须绿；R4 `url(lib/cover.css)` ⇒ 必须红（只按 src/href/fetch 抽的窄版会绿，
那个"绿"是漏，不是好消息）；R5 `data:` URI 与外部字体 ⇒ 必须绿。实测：基线 32 passed，
W1/W2/W3/C1–C2/R1–R5 全按期望，问题条目 0。
另外 W1（白名单少 `hot_snapshot.json`）现在会**同时**打中新判据 —— 那正是它存在的理由：旧判据只说"名单少一项"，
新判据说"浏览器在要它"。

**两处电池锚点的账**（同类错误第二次，写死以免再犯）：
① `mut_site_artifacts` 的 B4 一直报 INVALID，因为锚写成 `! -s("_pages/$must"` —— 漏了 `-s` 与 `[` 之间那个空格，
变异从没落到字节上；现按"操作符 + `$must` + `; then`"三要素定位，缩进与空格宽度不参与匹配。
② 按名发布那行的锚必须把 `index.html` 写进模式本身：正文里还有别的 `for f in …; do`（嵌入缓存那三个 `.npy/.index`），
只按形状 `search` 会先抓错行 —— 抓错行比抓不到更危险，因为变异会打在无关步骤上还"看起来红了"。
⇒ 电池报 INVALID 时先怀疑锚，不要怀疑判据。

**Vercel 步的真实代价（#27 的读数，未处置）**：近 12 场里正常场 `Deploy to Vercel` 用 **0.5–0.7 分钟**，
而 1578（head `f156bbff16`）跑了 **38.8 分钟被 cancelled**、1585（head `77147ed9a0`）19:18:02 起跑、到 20:00 被并发掐掉，
`Upload Pages artifact` 全程排在它后面 ⇒ 这两场的 Pages 更新被同一步扣住。这是"顺序不能改、只能给 Vercel 步封顶"
那条提议的量化依据，仍等点单。

**1585 的验收读数（20:04 现取，白名单化第一次上线）**：整场 `completed / cancelled`（就是上面那一步被掐），
但 `Upload Pages artifact` 与 `Deploy to GitHub Pages` 都是 **success**（`Reported success!`，deployment 绑 `77147ed9a0`）
⇒ **站点按白名单发出去了**，代价是 **Vercel 那一次部署整体丢失**（API 主机停在上一版；`api/rss`/`api/news`/`api/translate`
现取仍有响应，说明旧版活着）。门禁：A2 **392 passed**、A3 **29 passed**、gate B **425 passed / 0 failed**；
`[growth] new blobs=2 0.126 MiB verdict=ok`（那 2 个里一个是设计的每日 `build_logs` 提交）。
制品清单 **15 项、白名单外 0 项**（集合对账，不是抽样）。线上：7 个站点件全 **200**
（`index.html` 262,590 B、`rss-aggregator.html` 2,366,110 B、`ai-daily.html` 52,993 B、`daily-insight-history.html` 206,495 B、
`rss-data-0.js` 362,113 B、`hot_snapshot.json` 51,346 B、`rss_sources.json` 153,081 B），
30 个内部路径全 **404**（源码/日志/文档/lib/api/截图/依赖清单），
`daily-insight.json`/`trending_snapshot.json`/`descriptions_zh.json`/`rss_history.json`/`build_logs/2026-10-03.jsonl` 也全 **404**。
⇒ 第 23/26 两条挂账可以销；`_verify_build.py` 里那条 `known_categories.json` "该 200" 的旧期望已删（白名单之后它是"该 404"，
留着会把正确地不发报成站点件异常）。

**电池总体状态（17 支，20:04 全跑一遍）**：15 支 0 逃逸；两处修复 ——

**顺带查出的一条（20:13 现场定位，未处置，需用户裁决）**：`##[warning title=RSS 留存超硬上限]` 近 3 场
（17:00/18:00/19:00）**每场稳定 1 条**出厂外显龄期 >168h。条目实名核过：
`blog.jetbrains.com/blog/2026-09-22/introducing-jetbrains-air/`（IntelliJ Blog 源，出厂
`pub_date=2026-09-22T09:00:34+00:00`，20:11 读时 251.2h），落在 `rss-data-6.js`；
同场另一条 `notebooklm` 的 168.4h 是**读数随时间漂**（建场时 168.0h，落在 72-168 桶），不是第二条逃逸。

机制用 `_retention_ref_dt` 双输入模拟确定（不是推断）：
| 历史里的状态 | 判龄基准 | 判龄 | 结果 |
|---|---|---|---|
| 不在历史（本轮新抓） | 原始 pub_date | 251.2h | 丢弃 ✓ |
| 历史有 pub_date（9-22）| first_seen（证伪分支）| 258.7h | 丢弃 ✓ |
| **历史无 pub_date、first_seen=今天** | first_seen | **0.0h** | **放行 ⇒ 外显 251h** |
| 历史无 pub_date、first_seen=9-22 | first_seen | 258.7h | 丢弃 ✓ |

⇒ 破口是 `build_rss_aggregator.py:539-540`（历史条目缺 pub_date ⇒ 直接取 `first_seen`）与 `:549-551`
（`d - first_seen` 超容忍 ⇒ 也取 `first_seen`）这两条回退：**"旧文今天才第一次收录"会被判成 0 小时新**，
闸门放行，而分项按出厂串算 ⇒ 不变量必然被破。两个解析器（`_parse_hist_dt` 与 `_effective_pub_dt`）
在带 `+00:00` / `-05:00` 的串上实测逐位相同，所以不是解析器分叉 —— 这个怀疑先证伪再换方向。
三个处置方向（都不动，等点单）：① 判龄取 `min(pub_date, first_seen)` 里更旧的那个（硬上限真为 0，
代价是"旧文重见天日"这类内容会被丢）；② 放行但外显按 `date_fallback` 标「收录」（不变量改成"外显超龄必须带收录标记"）；
③ 认了，把 warning 的口径改成"未被标记的超龄条数"，与分项解耦。


`mut_site_artifacts` 的 B4 锚（少一个空格，长期 INVALID）与 `mut_daily_insight_retire` 的 D2 锚
（抄了白名单化之前的整行字面量 ⇒ INVALID，现按"行要素 + 必须含 index.html"定位，并断言只命中一处）；
`mut_untrack_gates.py` 需要 `gates`/`push` 参数，裸跑只会打印用法（不是失败）。

### 8.18 第二个主机：Vercel 的部署包仍在公开源码与文档（2026-10-02 20:34，判据与改法已就绪待推）

**为什么 Pages 关了还不算关**：Pages 走 `_pages` 白名单，而 Vercel 是 `npx vercel --prod` **直接从工作目录打包**，
只吃 `.vercelignore`（排除式）。20:29 现取 41 个仓库根跟踪文件：**16 个在 `starhub-refresh.vercel.app` 上 200**
——`HANDOFF.md` 84,323 B、`CLAUDE.md` 4,895 B、`REFRESH_VERIFICATION_REPORT.md`、`template.html` 116,509 B、`LICENSE`、
`vendor_qrcode.min.js`、`ai_daily.json`、`build_config.json`、`predictions.jsonl`、三张 `failed-run-364-*.png`、
`actions-step5-expanded.png`、两个 `daily-deep-*.json`、`rss_sources.json`、`index.html`。
（`.gitignore`/`.vercelignore`/`README.md` 实测 404 —— Vercel 自己就没上传，别把这条当成"我们已经挡住了"。）

**判据**：`tests/site_nav_drift/test_vercel_ignore_scope.py`（3 条，接进 A3；本地跑真实的 A2 全量命令 + A3 目录 = **428 passed**）。
三条口径都是本仓付过学费的地方：
1. **"运行时需要什么"从 `api/*.js` 源码推**（`join(process.cwd(),'x')` 与 `require('../lib/y')` 两种形状都抽），
   不另抄名单 —— 实测推出 `{rss_sources.json, rss_api_snapshot.json, lib/…}`。
   `api/rss.js:239 loadSources()` 直接 `readFileSync` 且**没有 try/catch** ⇒ 把 `rss_sources.json` 排除就是当场把 `/api/rss` 打成 500。
2. **gitignore 语义交给 git**：在临时仓里把 `.vercelignore` 当唯一 `.gitignore`，并把 `core.excludesFile` 指到空文件。
   两个坑当场踩过：`git check-ignore` **没有 `--exclude-from`**（那是 status/ls-files 的选项，第一版直接 129）；
   Windows 上 text 模式会把喂进 stdin 的 `\n` 翻成 `\r\n` ⇒ git 拿 `"HANDOFF.md\r"` 去判，**一个都不命中 = 假绿**。
   第三条控制专门验隔离性：`ai_daily.json` 在主仓 `.gitignore` 里、不在合成那份里，若被判"已覆盖"说明临时仓串吃了主仓规则。
3. **keep 用点名不用后缀**：根级唯一被跟踪的 `.html` 恰好是**源码模板** `template.html`（四个页面 HTML 已停止提交），
   "根级 `*.html` 保留"这种后缀规则等于专门替它开门。与 `test_pages_artifact_scope.py` 的 `PUBLISH` 只验**子集**
   不验相等（那边是站点运行时全集，含 `hot_snapshot.json`；这边是"Vercel 上刻意保留的页面"）。

**变异自证**（去掉某一行必须红且点名）：去 `*.md` ⇒ `['CLAUDE.md','HANDOFF.md','README.md','REFRESH_VERIFICATION_REPORT.md']`；
去 `template.html` ⇒ `['template.html']`；去 `vendor_qrcode.min.js` ⇒ `['vendor_qrcode.min.js']`。三条都 rc=1 且只报自己那一类。

**改法**（已落在本地 `.vercelignore`，与判据同批）：新增一段点名排除 `*.md` / `LICENSE` / `template.html` /
`vendor_qrcode.min.js` / `ai_daily.json` / `build_config.json` / `predictions.jsonl` / `daily-deep-*.json` /
`failed-run-*.png` / `actions-step5-*.png` / `.gitignore` / `.vercelignore` / `.github/`，并把**不许排除**的几样写进注释
（`vercel.json`、四个站点页面、`api/`+`lib/`+`rss_sources.json`+`rss_api_snapshot*.json`、`.vercel/`）。

**自查出来的一处判据缺陷（同类账，必须记）**：第一版判据只数**仓库根的文件**，于是漏掉
`.github/workflows/*.yml` —— 现取 `starhub-refresh.vercel.app/.github/workflows/update.yml` 是 **200 / 36,632 B**、
`repo-trim.yml` 200 / 8,021 B ⇒ **整条部署管线公开**。这就是本仓在排除式名单上连漏三次（`.md`/`lib/`/根级 junk）的
同款毛病：**按"先想到的那一层"枚举等于没枚举**。判据已改成对**每一条跟踪路径**要求覆盖，keep 只留三半且有实测理由：
`api/`+`lib/`（函数与它 require 的东西）、`VERCEL_KEEP`（四个页面 + `vercel.json`）、`.vercel/`
（CLI 自己的 linkage，且实测 `.vercel/project.json` 404 不发 ⇒ 既不需要收窄也承担不起被排除）。
顺带一条容易被直觉带偏的实测：**根级点文件不上传（`.gitignore`/`.vercelignore` 404）≠ 点目录不上传（`.github/` 200）**，
别把两者合并处理。去掉 `.github/` 那行的变异会点名 4 个 workflow 文件（rc=1）。

⇒ 生效要等下一场 Vercel 部署；验收口径 = 那 16 个根级名字 + `.github/workflows/update.yml` 重新 GET 应变 404，
而 `/api/rss`、`/api/news`、`/api/translate` 必须仍 200。本地读数：判据 3 条先红后绿、变异四处各点名自己那一类，
**真实 A2 全量命令 + A3 目录 = 428 passed**。

**`git check-ignore` 探路的两个坑（都是当场被变异抓出来的，别再踩）**：
1. **别问裸目录名**。gitignore 里 `lib/` 这类目录规则匹配的是 `lib/x.js`，问 `lib` 不命中 ⇒
   反向断言第一版问 `api/`、`lib/`，"把 `lib/` 加进 `.vercelignore`"这个变异当场**绿**（漏检）。
   现在问的是 `_tracked_paths()` 里真实存在的路径（`lib/rel_time.js`、`api/rss.js`、`rss_sources.json`）。
2. **带结尾斜杠的查询会被"空行"误命中**。`api/` 被解析成"目录 api + 空文件名"，
   而 gitignore 的空行恰好匹配空成分 ⇒ git 回一条 `.gitignore:47:`（空模式）的假读数，
   表现为"运行时依赖全被判成已排除"。已在 `_covered_by_ignore` 里 `rstrip('/')`，注释写明实测两边读数。
3. 附带一条口径判断：运行时读到的名字要分**三档**并按调用点定档 ——
   `rss_sources.json`（`loadSources()` 无 try/catch ⇒ 排除即 500）、
   `lib/rss_retention.js` 与 `lib/rss_cover.js`（在 try/catch 里但缺了掉留存闸门/实时封面 ⇒ 同权重不许排除）、
   `rss_api_snapshot.json`（有 try/catch 且 `.vercelignore:5` 本来就排它，实测线上 404 ⇒ **不发是设计**）。
   判据里有"分类不许烂掉"的守卫：抽取器新认出一个读取点而这三档没归档，当场红。
4. 我的 Edit 把整个 `.vercelignore`（75 行）写成了 CRLF，与远端 LF 不一致 ⇒ 已归一；
   与远端对账确认**删行 0**。这类"行尾被工具换掉"会让一次本该三行的改动变成 75 行 diff。

补完这些后的读数：判据 4 条全绿，`加 lib/`、`加 api/`、`加 rss_sources.json`、`去掉 .github/` 四个变异各红且点名，
基线（不改内容）必须绿；**真实 A2 全量命令 + A3 目录 = 429 passed**。


### 8.19 待点单的一批：13 个路径（21:54 封账，等待授权；结论在前，清单与证据在下文）

- **待推 13 路径**：见本节末尾"这批包含"与"命令"两段；提交说明 `.deploy-tmp/_msg.txt`（1,371 B）；
  回退基线 `.deploy-tmp/_rollback_baseline.json`（推送当下的**远端 blob sha**：11 已有 / 3 新增 `ABSENT`）。
- **最后一次的现跑读数**：14 个磁盘路径 CRLF 命中 0；真实 A2 全量命令 + A3 + 推送器判据 = **433 passed**；
  六节打 `update.yml` 的电池问题条目全 0；#27 两条判据的 M1/M2/M3 变异各红在自己的靶（基线 5 passed）。
- **下一轮开工先查三件事**：① `gh api repos/Kwei168/starhub/actions/runs?per_page=1` 看有没有 run 在飞
  （有则 `--wait-window`，别用 `--allow-running`）；② `1587` 之后 Vercel 是否还挂（若整场超时/取消，
  正好用 §8.19 第 3/4 条证据核"步骤超时后末步会不会执行"这件**仍未证**的事）；③ 与远端逐路径对账要用
  **默认** `git hash-object`，不要 `--no-filters`（`core.autocrlf=true` 下会把每个 CRLF 工作树文件报成 DIFF）。
- **仍未取得授权的四件**：推这批 13 路径；#32（建议 ②，①≈砍 4% 内容）；#30（建议不动）；#10（挂账）。



**这批包含**：① 白名单第二道闸（浏览器请求名必须出现在跑出来的制品里，含注释剥离，R1–R6 变异）；
② 第二台主机 Vercel 的公开面判据 + `.vercelignore` 补 12 项与 `tools/`、`.github/`；
③ 推送器 CRLF 归一的判据（此前只有代码没有测试）；④ 两处电池锚修复 + 新电池 `mut_vercel_ignore.py`；
⑤ **#27 的封顶与标红**：`Deploy to Vercel` 加 `id: vercel` + `timeout-minutes: 12`，末步扩成
`Mark the run red when Pages was not published or Vercel did not deploy`（引用 `failure` 与 `cancelled`，
刻意不用 `!= 'success'` 以免把 `skipped` 判红）。**`continue-on-error` 已放弃** —— 同文件的
`test_vercel_step_is_not_silenced` 禁止把失败遮成 success，先读判据再改方案，别推一个与判据互斥的改动。

**步级 `timeout-minutes` 是不是合法键**（这条决定 ⑤ 的可行性）：文档确认 steps 支持；
本仓另有**生产先例** —— `update.yml:403` 早就有步级 `timeout-minutes: 5`，而该 workflow 这几天整场跑通
（1584 = success）⇒ 不是拿"看起来对"当证据。
**仍未证的一件事**：步骤因超时结束时，同一 job 的**后续步骤是否继续执行**（1585/1586 是
`cancel-in-progress` 取消，不能当成步骤超时的证据）。两种结果都可接受：继续 ⇒ 末步把 Vercel 标红；
不继续 ⇒ 整场本身已经是非绿，可见性照样成立。第一次真实超时时按下面第 3/4 条证据核对，别提前下结论。

**#27 两条新判据的变异自证（2026-10-02 21:50，副本上跑 `STARHUB_UPDATE_YML`，不动生产文件）**：
`M1 timeout-minutes 12→99` ⇒ 只红 `test_vercel_step_has_a_timeout_cap_and_id`；
`M2 去掉 Vercel 的 id` ⇒ 两条一起红（末步引用不到 outcome，封顶那条也缺 id）；
`M3 把末步的 if 退回 `always() && steps.stage.outcome == 'failure'` ⇒ 只红 `test_unsuccessful_vercel_is_marked_red_at_the_end`；
基线（真 `update.yml`）= 5 passed rc=0。⇒ 这两条不是"写了就绿"的装饰，各自能分辨自己那半边。

**命令**（逐路径点名，别用目录展开）：
`py -3.11 tools/data_api_push.py --wait-window --msg-file .deploy-tmp/_msg.txt` + 上面 **13** 个路径
（含 `.github/workflows/update.yml` 与 `tests/site_nav_drift/test_pages_vercel_ordering.py`）。
`--wait-window` 当时被当成必需项：本仓每小时 `:00:29` 触发且 `cancel-in-progress: true`，
旧守门判的是"有没有 run 没跑完"，而 Vercel 步连场挂 40+ 分钟 ⇒ 它恒拒（2026-10-02 实测四轮 × 30 分钟白等，4 小时推不出去）。
**现已按"这一场还会不会写 main"判**（`tools/data_api_push.py:will_write_main()`，看 `Commit & push if changed` 那一步的步级状态，
判不了就拒）⇒ 真实空档只剩开场那几分钟，不再需要外部重试循环；`--wait-window` 保留但通常几十秒就满足。

**推完缺一条就不算验收**（"改前值"一律现取 CI 日志，不写推算 —— 我第一版把 A2 写成"≥429"就是推算留下的错）：
1. A2 计数 392 → **393** 且 0 failed（+1 只来自 `tests/rss_history/test_pages_deploy_wiring.py`，其余新增都在 A3 或未接闸的 `tests/tools/`）、
   A3 计数 29 → **38**、gate B 保持 **425 / 0 failed**（B 只收 `tests/daily_insight/`）；
2. `[growth]`：**落地首场会是 14 blobs ≈0.28 MiB 的一次性成本**（= 本批 14 个路径合计 295,354 B，每个改动永久多一份副本），
   之后回落到 ~1 blob/场；把上一场的 `2 blobs / 0.126 MiB` 当预期读数，就会把正常一次性成本报成"斜率反弹"；
3. `Deploy to GitHub Pages` = `Reported success!`；
4. 线上二次 GET：16 个根级名字 + `.github/workflows/update.yml` + `tools/daily_commit_gate.sh` **转 404**，
   四页与 `/api/rss`、`/api/news`、`/api/translate` **仍 200**
   （第 4 项要等一场**成功的** Vercel 部署才生效 —— 该步连场挂起时部署会整场丢失）；
5. `mut_vercel_ignore` 与 `mut_artifact_scope` 问题条目仍为 0（防止判据被"绕过"而不是被"修好"）。

**这次修掉的一处自伤**：两次"看着是空操作"的 Edit 中有一次真的把 `## 九、技术栈总结` 与下一行的表头 `| 层 | 技术 |`
并成了一行 —— 正是记忆里那条"少个换行会把下一行挤进来"。⇒ 手册这类长文档改完必须**结构化复核**：
本次做法是 `grep -n '^## '` 数一遍节名，并做与远端的删行对账（`HANDOFF.md` 应为 0 删行）。

**#27 的读数修正（2026-10-02 23:12 现取，两次自我否定的全过程记在这里）**：
- 挂起点**不在我们这侧**：Vercel 步的日志显示上传 4.3 MB 只花 1.5 秒（22:19:59→22:20:00），
  随后 `Building…` 独占 22:20:00→23:01:44（41.7 分钟）才被下一场并发取消 ⇒ 是 **Vercel 服务端构建**。
  本地无可解释诱因：`vercel.json` 没有 build/install 命令；函数现网响应 0.83–0.89 秒且 `api/article.js`
  的 jsdom/readability 正常（"`.vercelignore` 排了 `package.json` 会断依赖"这个怀疑被实测否掉）；
  同一 head 的 1578 挂 38.8 分钟、1579 只花 0.7 分钟 ⇒ 间歇性，现在变成常发。
- **"部署有没有丢"必须用每场必变的东西判**：我第一次拿 `rss_sources.json` 对 hash，三方全等 ⇒ 差点得出
  "部署没丢"的**错误撤回**——它只在信源变化时才改写，相同是必然的，属代理信号冒充证据。
  换成 `index.html`（每场新生成、从不入库，天然场次指纹）才看清：
  Vercel 内嵌 `2026-10-03 02:07`（=1584，18:00 UTC）而 Pages 是 `06:07`（=1588）⇒ **Vercel 连 1585–1588 四场都没部署成功**。
- **由此两条口径要分开**：① Pages 没停更，只是每场被推迟 ~30–55 分钟；② Vercel 侧从 18:00 起停在旧版，
  所以那之后合入的 `api/*.js`、`lib/*.js` 改动**未生效**（现网函数仍是 1584 那一版）。
- `timeout-minutes: 12` 只解决 ①（让 Pages 早半小时到一小时上线、并把"Vercel 未成功"变成 run 级红），
  **解决不了 ②**：CLI 被掐后 Vercel 的构建有没有继续/是否被连带取消，从外面判不了（部署 URL 302 跳 SSO，
  无权限）。②要查得进 Vercel 项目面板看那 40 分钟卡在哪。
- 一条操作层面的连带后果：**每场挂 40 分钟 ⇒ 一天里只有 xx:43→xx:59 那十几分钟没有 run 在飞**，
  而 `data_api_push.py --wait-window` 只等 30 分钟 ⇒ 在这个状态下推送会反复白等。封顶落地后这个空档才恢复正常。

## 九、技术栈总结

| 层 | 技术 |
|---|---|
| 构建脚本 | Python 3.11（`fetch_and_build.py` 纯标准库；`build_rss_aggregator.py` 加 threading/LlamaIndex；`insight_engine.py` 加 llama-index-core/fastembed；`build_daily_insight.py` 加可选 faiss-cpu/rank-bm25/numpy，缺失时降级） |
| 语义引擎 | 双管线：`insight_engine.py`（LlamaIndex 层级索引 + 手动余弦检索，服务 RSS 页 AI 面板）；`build_daily_insight.py`（FAISS 向量 + BM25 窗口检索 RRF 混合 + SiliconFlow bge-m3 + numpy 向量缓存）；AgnesLLM 多 key 轮询；Judge 链 mimo→agnes 两级 |
| Serverless | Vercel Functions（Node.js，原生 fetch）；9 个函数 |
| 托管 | Vercel（主）+ GitHub Pages（备） |
| CI/CD | GitHub Actions（4 个 workflow：update/zen-check/build-log-summary/sync-agnes-env） |
| 定时触发 | cron-job.org 每小时 POST（主力）+ GitHub cron（5 次/天，兜底） |
| 前端 | 原生 HTML/CSS/JS，无框架 |
| 数据源 | GitHub REST API v3、AIHOT API v1 + RSS、RSSHub 镜像、HN/Verge/TechCrunch/arXiv/Redis RSS、BestBlogs（559 源）、X/Twitter（160 源 via xgo.ing）、newsnow 40 平台热榜、AGI Hunt Agent API（12 频道，密钥 + 限速合规） |
| 翻译 | 构建期五端点降级链：Agnes AI（多 key 轮询）→ OpenCode Zen（免费模型轮询）→ Google GTX → Bing → MyMemory；构建期有界并发池（6 源）；运行时 Vercel 网关统一链 GTX → MyMemory → Agnes → Zen，mode 只改并发（full 4 / bulk 2）与 Agnes 条数上限（bulk 30） |
| RSS 架构 | 1005 源三层分级（T1=6 实时/T2=204/T3=795 快照）+ 并行抓取（12 并发 + 域级熔断）+ 增量构建 + 卡片墙 4:1 交织 + AI 动态双形态侧栏 + 热榜 40 平台 + 媒体播放；快照已出仓（gitignore；**也不随 Vercel 上传** —— `.vercelignore:5` 排除 `rss_api_snapshot*.json`，2026-10-02 20:46 实测 `starhub-refresh.vercel.app/rss_api_snapshot.json` 404，`loadSnapshot()` 有 try/catch 走"实时抓取"降级） |
| 洞察引擎 | insight_engine：LlamaIndex + RAGAS-inspired 自纠错 + 话题聚类 + 关键词生命周期 + 14 天趋势滚动；每日深度洞察：RAG 混合检索 + 多级 Phase（去重/核查/自审/硬过滤）+ RAGAS 四维阈值闭环 + 破茧栏 + 30 天跨天关联 |
