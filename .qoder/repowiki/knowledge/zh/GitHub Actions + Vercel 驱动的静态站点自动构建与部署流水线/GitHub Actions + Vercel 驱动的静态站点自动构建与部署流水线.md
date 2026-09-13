---
kind: build_system
name: GitHub Actions + Vercel 驱动的静态站点自动构建与部署流水线
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/update.yml
    - fetch_and_build.py
    - build_rss_aggregator.py
    - build_ai_daily.py
    - vercel.json
    - package.json
    - .vercelignore
---

## 1. 构建系统概览

本项目采用「Python 脚本生成静态 HTML + GitHub Actions 定时触发 + Vercel Serverless 部署」的无服务器（serverless）架构。整个构建链路不依赖传统编译工具链，而是通过 Python 标准库抓取外部数据（GitHub Star 列表、RSS 源、AIHOT API），渲染为纯静态 HTML/JSON 文件后提交到仓库，再由 Vercel CLI 发布到生产环境。

核心流程：
- `.github/workflows/update.yml` 定义调度策略：UTC 21:00（北京时间 05:00）执行全量构建，其余时段（UTC 2/6/10/14）执行增量构建；支持 `workflow_dispatch` 手动触发。
- 使用 `concurrency: group: starhub-update, cancel-in-progress: true` 保证同一时刻只运行一次，新触发取消旧任务，避免并发冲突。
- 构建阶段调用 `python fetch_and_build.py $MODE`，根据 MODE 决定 full/incremental 模式。
- 构建产物包括 `index.html`、`ai-daily.html`、`rss-aggregator.html`、`rss-data-0.js`、`rss-data-1.js`、`known_categories.json`、`descriptions_zh.json`、`trending_snapshot.json`、`translations.json`、`rss_cache.json`、`rss_history.json`、`rss_sources.json`、`rss_api_snapshot.json`。
- 仅当 `git diff --cached` 有变更时才 commit 并 push，使用 `--force-with-lease` 作为安全网，若 lease 失败则重新 fetch/reset/rebuild/push。
- 部署阶段通过 `npx --yes vercel --prod --yes --token "$VERCEL_TOKEN"` 发布，内置 5 次退避重试（间隔递增）以应对网络瞬时故障。

## 2. 关键构建脚本与职责

- `fetch_and_build.py`：总入口，负责拉取 Kwei168 的 GitHub Star 收藏列表，按关键词规则分类（agent/distill/video/coding/content/learning/assistant/tools/finance/business/frontend），翻译英文描述为中文，生成 `index.html` 及 `known_categories.json`、`descriptions_zh.json`、`trending_snapshot.json`。
- `build_rss_aggregator.py`：多路 RSS 聚合器构建脚本，从 `rss_sources.json` 读取信源配置，抓取 RSS → 翻译 → 合并到 72 小时历史（`rss_history.json`，按 link 去重，过期裁剪）→ 生成 `rss-aggregator.html`。内置 RSS 缓存（`rss_cache.json`，TTL 1800s）和翻译缓存（`translations.json`）。
- `build_ai_daily.py`：AI 晨报构建脚本，优先拉取 AIHOT 公开 API v1，失败回退到 RSS（`aihot.virxact.com/feed.xml`），再失败回退到本地 `ai_daily.json`；筛选近 36 小时条目生成 `ai-daily.html`。
- `merge_sources.py`、`rss_sources_merged.py`：用于合并/维护 RSS 源清单。
- `dev_render.py`：本地开发渲染脚本。

## 3. 运行时与部署配置

- `vercel.json`：声明 Vercel Serverless Functions 路由，并为每个函数设置最大执行时长（`maxDuration`）：`refresh` 10s、`search` 30s、`events` 60s、`news` 30s、`rss` 60s、`article` 15s、`agihunt` 15s。
- `package.json`：仅声明两个 Node.js 依赖 `@mozilla/readability` 和 `jsdom`，供 API 层解析网页内容。
- `.vercelignore`：排除 `rss_history.json` 和 `rss_cache.json` 这两个大体积缓存文件，避免污染部署包。
- CI 中通过环境变量注入 `VERCEL_TOKEN`、`VERCEL_PROJECT_ID`、`VERCEL_ORG_ID` 完成认证与项目绑定。

## 4. 构建约定与约束

- **语言与环境**：构建脚本仅依赖 Python 标准库（`urllib`、`xml.etree.ElementTree`、`json`、`datetime` 等），CI 固定使用 Python 3.11，无需 `pip install`。
- **时区约定**：所有时间计算统一使用北京时间（UTC+8），通过 `_now_bj()` 或 `datetime.timezone(timedelta(hours=8))` 实现。
- **增量 vs 全量**：由 `update.yml` 中的 UTC 小时判断决定 MODE——21 点为 full，其他为 incremental；增量模式下利用 `rss_cache.json` 和 `rss_history.json` 跳过已抓取源。
- **幂等性**：每次构建先 `git reset --hard origin/main` 同步最新远程状态，确保基于最新数据构建；push 前检测 diff，无变更不提交。
- **容错设计**：API/RSS 拉取失败时逐级降级（AIHOT API → RSS → 本地 JSON）；Vercel 部署失败最多重试 5 次；GitHub Actions 使用 `cancel-in-progress` 避免重复构建。
- **产物管理**：构建产物直接提交到 git 仓库（而非 .gitignore），由 CI 自动更新；`.vercelignore` 显式排除运行时缓存文件。
- **并发控制**：通过 `concurrency.group` 和 `cancel-in-progress: true` 保证全局唯一运行实例，从根本上消除并发冲突。
- **安全边界**：GitHub Token 通过 `Authorization: Bearer` 头传入（可选），Vercel 凭据通过 GitHub Secrets 注入，不硬编码在代码中。