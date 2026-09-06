---
kind: build_system
name: GitHub Actions + Vercel Serverless 驱动的静态站点构建与部署流水线
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/update.yml
    - fetch_and_build.py
    - build_rss_aggregator.py
    - dev_render.py
    - vercel.json
    - api/refresh.js
    - api/rss.js
    - api/article.js
    - template.html
    - rss-aggregator.html
---

## 1. 构建系统总览

本项目由 Star 收藏主线和 RSS 聚合主线组成，均以原生 HTML/CSS/JS 产物为主，没有传统意义上的打包编译步骤。Star 主线通过 `fetch_and_build.py` 拉取 starred repos、关注动态和 Trending 数据，分类、翻译后生成 `index.html`；RSS 主线通过 `build_rss_aggregator.py` 维护 711 个 T1/T2/T3 信源、72 小时历史和数据 chunk，生成 `rss-aggregator.html`。GitHub Actions 提交产物并部署到 Vercel，GitHub Pages 提供静态访问入口。

- **运行时环境**：Python 3.11（仅标准库，无第三方依赖）
- **CI/CD**：GitHub Actions (`update.yml`) + Vercel CLI
- **实时刷新入口**：Vercel Serverless 函数 (`api/refresh.js`) 调用 GitHub Actions workflow_dispatch API 触发重新构建

## 2. 关键文件与职责

| 文件 | 角色 |
|---|---|
| `.github/workflows/update.yml` | CI 流水线定义：UTC 21:00 full、UTC 2/6/10/14 incremental，支持手动触发、条件提交和 Vercel deploy |
| `fetch_and_build.py` | Star 主线构建脚本：拉取 starred repos / following events / Trending，分类、翻译并渲染 `index.html` |
| `build_rss_aggregator.py` | RSS 主线构建脚本：维护 711 源、72 小时历史、快照、chunk、AI 侧栏和 reader2 |
| `dev_render.py` | 本地开发工具：从已生成的 `index.html` 提取常量，重新渲染 `template.html` 用于预览模板改动 |
| `vercel.json` | Vercel 配置：声明 refresh/search/events/news/rss/article/agihunt 共 7 个函数及最大执行时长 |
| `api/refresh.js` | 中转函数：校验 CORS + `X-Refresh-Key` 后调用 GitHub Actions dispatch API 触发本仓库 update.yml |
| `api/rss.js` / `api/article.js` | RSS 快照/T1 实时接口与全文兜底接口；全文接口允许 GET/OPTIONS 跨域访问 |
| `template.html` / `rss-aggregator.html` | Star 主站模板与 RSS 生成产物；RSS HTML 不应直接编辑 |
| `known_categories.json` / `descriptions_zh.json` / `trending_snapshot.json` | Star 主线构建缓存：分类映射、中文描述缓存、Trending 基线快照 |
| `rss_sources.json` / `rss_history.json` / `rss_api_snapshot.json` | RSS 信源、72 小时历史和 API 快照状态 |

## 3. 构建流程与架构决策

### 3.1 分层定时构建
`update.yml` 当前由两组 schedule 和 `workflow_dispatch` 触发：UTC 21:00 执行 `full`，UTC 2/6/10/14 执行 `incremental`，普通 push 不会自动触发。Job 顺序：
1. `actions/checkout@v5`（完整历史）
2. `actions/setup-python@v6`（Python 3.11）
3. 同步 `origin/main`，按 UTC 小时确定模式
4. `python fetch_and_build.py $MODE` — 同时生成 Star 与 RSS 产物
5. 条件提交并 push；`concurrency.cancel-in-progress: true` 保留最新触发
6. `npx --yes vercel --prod --yes --token $VERCEL_TOKEN` 部署到 Vercel

`full` 抓取全部 711 个 RSS 源；`incremental` 跳过 T1 和 4 小时内成功抓取的源，只更新 T2/T3。构建提交可能形成第二个 dynamic run，发布验证必须同时检查两个 run。

### 3.2 手动触发（实时刷新）
前端轮询 `api/events` 获取关注账号动态；当需要主动刷新全站时，调用 `api/refresh.js`，该函数验证来源白名单和 `REFRESH_KEY` 后，向 GitHub API 发起 `POST /repos/Kwei168/starhub/actions/workflows/update.yml/dispatches`，从而触发 `workflow_dispatch` 分支的更新流程。

### 3.3 构建产物与版本策略
- **版本号**：无显式版本号，以 Git commit 作为版本标识
- **双主线产物**：Star 主线提交 `index.html` 与分类/描述/趋势缓存；RSS 主线提交 `rss-aggregator.html`、`rss-data-0.js`、`rss-data-1.js`、历史与快照文件
- **增量提交**：仅当产物或状态文件有变更时才 commit & push，减少无效推送
- **并发控制**：`concurrency.group: starhub-update` 且 `cancel-in-progress: true`，新触发取消旧排队任务
- **权限最小化**：仅授予 `contents: write`，Serverless 函数通过独立 `GH_TOKEN`（fine-grained PAT，Actions:write 权限）调用 dispatch API

### 3.4 降级与容错
- Trending 抓取失败时回退到 `trending_snapshot.json` 差值模式
- AI 池为空时保留旧快照，避免清空基线导致无法自愈
- README 简介提取失败或翻译失败时保留原文
- 所有外部 API 调用均包裹 try/except，失败时打印 stderr 并继续

## 4. 约定与约束

- **构建脚本仅依赖 Python 标准库**（注释明确声明），无需 `requirements.txt` 或虚拟环境
- **模板占位符必须成对存在**：`dev_render.py` 在本地渲染时会校验 `template.html` 是否包含所有占位符，缺失则 `SystemExit`
- **JSON 安全注入**：`_safe_json()` 将 `<` 转义为 `\u003c` 防止 `</script>` 注入攻击，同时保持 JSON 可被 `json.loads` 还原
- **CORS 白名单**：`api/refresh.js` 仅允许 `https://starhub-refresh.vercel.app` 和 `https://kwei168.github.io` 两个域名
- **请求鉴权**：refresh 接口要求 `X-Refresh-Key` 头与 `REFRESH_KEY` 环境变量一致
- **GitHub API 限流**：相邻请求间隔 ≥1s（事件翻页）或 0.5s（starred/trending），避免触发二级速率限制
- **时区处理**：统一使用 UTC 时间，北京时间通过 `timezone(timedelta(hours=8))` 转换
- **Vercel 函数超时**：refresh 10s、search 30s、events 60s、news 30s、rss 60s、article 15s、agihunt 15s，由 `vercel.json` 显式声明
- **页面边界**：GitHub Pages 仅托管静态页面；页面调用 Serverless 必须使用 Vercel 绝对 URL，`/api/article` 保留 GET/OPTIONS 与 `Access-Control-Allow-Origin: *`