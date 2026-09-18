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
| `build_config.json` | 22 | 构建配置外置文件。控制 insight_engine 开关、LLM provider、max_documents、top_keywords/topics；`daily_insight_enabled`、`daily_insight_judge_provider/model/timeout`（当前 mimo / mimo-v2.5-free / 60s）、`daily_insight_cross_validation`（当前 true，双 prompt 交叉验证）等每日洞察参数；缺失键自动填充默认值 |
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
| `rss_api_snapshot.json` (+`_1`...) | RSS API 分块快照（72h 累积历史 + meta.last_fetch 增量状态）。**已移出仓库**（单文件 82MB 导致 Actions checkout 超时），`.gitignore` 忽略，仅存于 CI 工作区并随 `vercel --prod` 上传供 `api/rss.js` 读取（见 §8.13） |
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
| `api/rss.js` | `/api/rss` | GET | CORS 允许所有来源（`*`） | 60s | RSS 聚合 API。**快照优先**：加载 `rss_api_snapshot.json` 并自动合并分块 `_1.._N`（1005 源 72h 累积）；`?refresh=1` 时仅实时抓取 T1 高频源（6 个），T2/T3 从快照读取；T1 英文源实时翻译 |
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
  1. 读取 rss_api_snapshot.json 的 meta.last_fetch
  2. 跳过所有 T1 源（由 api/rss.js 实时负责）
  3. 跳过 4h 内已成功抓取的源
  4. 抓取剩余 T2/T3 源，合并到历史
  5. 更新 meta.last_fetch，保存快照
```

**API 层分层抓取**（`api/rss.js`）：
- 快照优先：默认返回构建时生成的 72h 累积快照
- `?refresh=1` 时：仅实时抓取 6 个 T1 源（~3s），T2/T3 从快照读取
- T1 英文源实时翻译：Agnes → Zen → GTX → Bing → MyMemory 五端点降级

**卡片墙交织算法**（`tierInterleave`）：
- 双队列 4:1 交织：每 4 篇 T1/T2 文章穿插 1 篇 T3 文章
- 防止 T3 的 795 个低频源被 T1 的 6 个高频源完全淹没
- T1+T2 占 ~80% 卡片位，T3 占 ~20%

**源面板排序**：每个分类内按文章数降序排列，用户可快速定位活跃源。

**经验教训**：
- **源数量增长时必须引入分级** — 大规模源全量抓取不可行，T1 实时 + T2/T3 快照是合理分工
- **增量状态嵌入快照** — meta.last_fetch 放在 rss_api_snapshot.json 内，不引入额外存储
- **快照只增不减** — 不主动清理旧条目，72h 窗口自然过期

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
- 交叉验证已开启（`daily_insight_cross_validation: true`）：v1/v2 双 prompt 独立评分后加权平均，降低单 judge 抖动。
- 评分原始输出记录在 `daily-insight.json` 的 `quality` 字段，可回溯。

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
- **快照不进 GitHub 仓库，但仍随 `vercel --prod` 从 Actions 工作区上传**，线上 `/api/rss` 行为不变。
- 连带影响：**增量构建的 `meta.last_fetch` 状态不再能从 git 恢复**，每次全新 checkout 后第一场构建按 full 逻辑补偿；本地跑 `build_rss_aggregator.py` 时无快照属正常。

### 8.14 Agnes 多 key 轮询统一（2026-09-18）

- 新方案：`AGNES_API_KEY`（主）+ `AGNES_API_KEYS`（附加，逗号分隔），合并成 key 池；429 时轮转下一个 key，非 429 错误重试当前 key 2 次。当前账号侧共 4 个 key（**池大小以 Secret 内容为准，代码不写死数量**）。`AGNES_API_KEYS` 已覆盖全部 6 个调用点：`build_rss_aggregator.py`、`build_ai_daily.py`、`build_daily_insight.py`（`_LLM` 类）、`api/translate.js`、`insight_engine.py`、`fetch_and_build.py`（AI 态势摘要）。
- **主 key 逗号切分已全量统一（2026-09-18）**：6 个调用点（`build_rss_aggregator.py:152`、`build_ai_daily.py:531`、`insight_engine.py:247`、`build_daily_insight.py:_init_llm`、`fetch_and_build.py:generate_ai_summary`、`api/translate.js:AGNES_KEYS`）现在都是同一语义：主 key 与附加 key 各自逗号切分后合并成一个池。**多 key 放 `AGNES_API_KEY` 或 `AGNES_API_KEYS` 都安全**。`fetch_and_build.py` 顺带补上了换 key 重试（此前只发一次、失败即放弃）：**先建池再判空**（避免主 key 缺失时漏用附加 key、或主 key 全逗号时零输出静默返回），且只在 429/5xx/超时/JSON 失败时换 key，401/403 立即停止（换 key 也是白烧）。
- **注意 key 池不去重**：`AGNES_API_KEY=k1` + `AGNES_API_KEYS=k1,k1` 会得到 3 个相同 key，轮转只是在同一 key 上烧尝试次数。Secret 内容自己保证唯一。
- **已修复（2026-09-18）**：`insight_engine.py` 的 `configure_llm()` 此前仍读旧编号式 `AGNES_API_KEY_2/_3`，而 update.yml 已停发这两个变量，该引擎实际退化为单 key。现改为与 `build_rss_aggregator.py:152-155` 同语义的池化方案：主 key 逗号切分 + `AGNES_API_KEYS` 逗号切分合并，**主 key 缺失时附加 key 仍生效**（不会静默退回 MockLLM）。
- **回归测试**：`test_insight_engine.py` 新增 4 例覆盖 key 池（单 key→`extra_keys` 必须为 None、主 key 逗号展开、主+附加合并且空白/空段被清洗、仅附加 key 时仍建 AgnesLLM）。全套 86 例当前 **全绿**——此前长期红着的 2 例 RSS 时效测试是因为 `recent` 硬编码成 `2026-09-13`，72h 窗口一过必然失败；已改为 `_recent_bjt_iso()` 相对时间，勿再写死日期。
- 踩坑：`_AGNES_KEY_IDX` 等全局变量在函数内使用前必须先 `global` 声明（`1d2a93d` 修复过一处顺序 bug）。

---

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
| RSS 架构 | 1005 源三层分级（T1=6 实时/T2=204/T3=795 快照）+ 并行抓取（12 并发 + 域级熔断）+ 增量构建 + 卡片墙 4:1 交织 + AI 动态双形态侧栏 + 热榜 40 平台 + 媒体播放；快照已出仓（gitignore，仅随 Vercel 上传） |
| 洞察引擎 | insight_engine：LlamaIndex + RAGAS-inspired 自纠错 + 话题聚类 + 关键词生命周期 + 14 天趋势滚动；每日深度洞察：RAG 混合检索 + 多级 Phase（去重/核查/自审/硬过滤）+ RAGAS 四维阈值闭环 + 破茧栏 + 30 天跨天关联 |
