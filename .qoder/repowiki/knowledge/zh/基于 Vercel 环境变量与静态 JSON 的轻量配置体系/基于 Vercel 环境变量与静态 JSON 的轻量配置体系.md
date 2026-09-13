---
kind: configuration_system
name: 基于 Vercel 环境变量与静态 JSON 的轻量配置体系
category: configuration_system
scope:
    - '**'
source_files:
    - vercel.json
    - api/refresh.js
    - api/search.js
    - api/events.js
    - api/agihunt.js
    - fetch_and_build.py
    - build_ai_daily.py
    - build_rss_aggregator.py
    - rss_sources.json
    - known_categories.json
    - descriptions_zh.json
    - translations.json
    - ai_daily.json
    - template.html
---

## 1. 系统/方案概述

本项目没有使用专门的配置框架（如 dotenv、config.js、yaml 等），而是采用**“Vercel Serverless 环境变量 + 根级静态 JSON 数据文件”**的组合方式，将运行时密钥、构建期数据与前端展示文案分层管理：
- **运行时敏感配置**（GitHub Token、刷新密钥、第三方 API Key）通过 Vercel 平台注入到 Node.js 函数的 `process.env`。
- **非敏感运行参数**（CORS 白名单域名、API 超时、缓存 TTL、分页上限等）以模块内常量硬编码在函数源码中。
- **构建期/展示数据**（RSS 源列表、分类、翻译描述、语言颜色、默认收藏等）以 `.json` 文件形式存放在仓库根目录，由 Python 构建脚本在 CI 中拉取并合并进最终 HTML。

## 2. 关键文件与位置

| 类别 | 文件 | 作用 |
|---|---|---|
| Vercel 部署配置 | `vercel.json` | 声明各 Serverless Function 的 `maxDuration`（超时限制），是唯一的部署级配置入口 |
| 敏感环境变量读取 | `api/refresh.js`、`api/search.js`、`api/events.js`、`api/agihunt.js` | 从 `process.env.GH_TOKEN`、`process.env.REFRESH_KEY`、`process.env.AGIHUNT_API_KEY` 读取密钥 |
| 构建期数据源 | `rss_sources.json`、`known_categories.json`、`descriptions_zh.json`、`ai_daily.json`、`translations.json`、`bestblogs_sources.json`、`trending_snapshot.json`、`rss_cache.json`、`rss_history.json` | 被 `fetch_and_build.py`、`build_ai_daily.py`、`build_rss_aggregator.py` 读取并生成页面 |
| 构建脚本 | `fetch_and_build.py`、`build_ai_daily.py`、`build_rss_aggregator.py` | 聚合 GitHub / RSS / AI 数据，渲染为 `index.html`、`ai-daily.html`、`rss-aggregator.html` |
| 前端静态数据 | `rss-data-0.js`、`rss-data-1.js` | 由构建脚本生成的前端可直接加载的数据块 |
| 模板 | `template.html` | 被 `fetch_and_build.py` 用 `__DATA__`、`__CATS__`、`__LANGS__`、`__FAVS__`、`__TRENDING__`、`__FEED__`、`__UPDATED__` 占位符替换 |

## 3. 架构与设计约定

### 3.1 环境变量（Secrets）
- `GH_TOKEN` / `GITHUB_TOKEN`：GitHub API 鉴权。`events.js`、`search.js`、`refresh.js` 直接读 `process.env.GH_TOKEN`；`fetch_and_build.py` 兼容两者（`os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")`）。
- `REFRESH_KEY`：用于 `X-Refresh-Key` / `X-Search-Key` 请求头校验，配合 CORS 白名单实现弱认证，防止无头扫描器滥用刷新接口。
- `AGIHUNT_API_KEY`：AGI Hunt 资讯代理专用，仅在 `api/agihunt.js` 中使用。
- 所有密钥均**不写入代码**，仅通过 Vercel 环境变量注入；缺失时函数返回明确的 500 错误消息（如 `"GH_TOKEN 未配置（Vercel 环境变量）"`）。

### 3.2 CORS 白名单（硬编码常量）
每个 API 函数顶部定义 `ALLOWED_ORIGINS = new Set(['https://starhub-refresh.vercel.app', 'https://kwei168.github.io'])`，比较前统一转小写。新增发布域名需同步修改所有 `api/*.js` 中的该常量——这是当前唯一需要跨文件同步的配置项。

### 3.3 构建期数据层（JSON 文件）
- `rss_sources.json`：RSS 源清单，被 `build_rss_aggregator.py` 解析后生成前端 JS 数据块。
- `known_categories.json`：GitHub 仓库 → 分类映射，增量更新避免重复分类。
- `descriptions_zh.json`：仓库中文简介缓存，首次抓取 README 后用翻译结果回填，避免重复调用翻译 API。
- `translations.json`：前端 UI 文案的多语言键值对。
- `ai_daily.json`：AI 晨报数据源，被 `build_ai_daily.py` 渲染为独立页面。
- `rss_cache.json`、`rss_history.json`、`trending_snapshot.json`：构建过程中的中间状态快照。

构建流程（`fetch_and_build.py.main`）按顺序：读取 `known_categories.json` → 拉取 Star 列表 → 分类/翻译 → 生成 `index.html` → 持久化 `known_categories.json`、`descriptions_zh.json` → 调用 `build_ai_daily.py`、`build_rss_aggregator.py` 生成另外两个页面。

### 3.4 内存缓存作为“软配置”
各 API 函数用模块级 `Map` 实现进程内缓存，TTL 作为常量定义在源码中：搜索 10 分钟、翻译 1 小时、事件 10 分钟、AGI Hunt 10 分钟（最多 20 条）。这些 TTL 本质上是可调参数，但当前以硬编码常量形式存在。

## 4. 约定与约束

- **密钥来源约束**：所有敏感凭据必须来自 Vercel 环境变量，禁止硬编码或提交至版本库。违反此约定的行为会在运行时立即返回 500 错误。
- **CORS 约束**：仅允许 `starhub-refresh.vercel.app` 与 `kwei168.github.io` 两个域名跨域访问 API；其他 Origin 一律返回 403。
- **请求头认证约束**：`/api/refresh` 要求 `X-Refresh-Key` 等于 `REFRESH_KEY`；`/api/search` 要求 `X-Search-Key` 等于同一 `REFRESH_KEY`；`/api/events` 和 `/api/agihunt` 无需额外密钥（仅依赖 CORS 白名单）。
- **构建数据只增不改**：`known_categories.json`、`descriptions_zh.json` 由构建脚本自动维护，不应手动编辑；`rss_sources.json` 由上游数据管道生成。
- **部署配置集中**：所有 Serverless Function 的超时时间集中在 `vercel.json` 的 `functions.*.maxDuration` 字段声明，新增 API 路由需在此注册。
- **前端数据不可变**：`index.html`、`ai-daily.html`、`rss-aggregator.html` 由构建脚本一次性生成，运行时不再重新渲染；前端通过 `rss-data-*.js` 加载已构建好的数据。

## 5. 评价

该配置体系非常轻量：没有引入任何配置库，全部依赖 Vercel 原生能力与 JSON 文件。优点是简单透明、易于调试；缺点是跨文件共享常量（如 CORS 白名单、TTL、分页上限）分散在各函数源码中，缺乏集中配置文件，新增 API 时需人工复制粘贴这些常量。对于本项目的规模而言，这种“环境变量 + JSON 数据 + 源码常量”的组合足以满足需求。