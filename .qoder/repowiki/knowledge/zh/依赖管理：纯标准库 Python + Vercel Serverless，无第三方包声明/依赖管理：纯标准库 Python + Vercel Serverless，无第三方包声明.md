---
kind: dependency_management
name: 依赖管理：纯标准库 Python + Vercel Serverless，无第三方包声明
category: dependency_management
scope:
    - '**'
source_files:
    - fetch_and_build.py
    - .github/workflows/update.yml
    - vercel.json
    - api/refresh.js
    - .vercel/project.json
---

## 1. 使用的系统/方法

本项目采用**零第三方依赖**的极简策略：
- 构建脚本 `fetch_and_build.py`（GitHub Actions 中运行）仅使用 Python **标准库**（`json`、`urllib.request`、`re`、`datetime`、`os`、`sys`、`time`），注释明确声明“无需安装第三方包”。因此不存在 `requirements.txt`、`pyproject.toml`、`Pipfile` 等 Python 依赖清单。
- 前端为纯静态 HTML/CSS/JS（`index.html`、`template.html`），没有 `package.json`、`yarn.lock`、`pnpm-lock.yaml` 等 Node.js 依赖文件，也未使用任何前端框架或打包工具。
- Vercel Serverless 函数位于 `api/refresh.js`、`api/search.js`、`api/events.js`，同样未引入第三方模块，通过原生 `fetch` 调用 GitHub API。
- 部署阶段在 `.github/workflows/update.yml` 中直接执行 `python fetch_and_build.py`，并通过 `npx --yes vercel --prod --yes --token "$VERCEL_TOKEN"` 触发 Vercel CLI 部署，不缓存或复用 node_modules。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `fetch_and_build.py` | 唯一业务逻辑入口，抓取 GitHub starred repos / trending / events，渲染 `index.html` |
| `vercel.json` | Vercel 配置，声明三个 serverless function 及其超时限制 |
| `.github/workflows/update.yml` | GitHub Actions 定时任务（cron `10 * * * *`）+ `workflow_dispatch` 手动触发 |
| `api/refresh.js` | Vercel 中转函数，接收 POST 后调用 GitHub Actions workflow_dispatch API |
| `.vercel/project.json` | Vercel 项目标识（projectId、orgId） |
| `known_categories.json`、`descriptions_zh.json`、`trending_snapshot.json` | 运行时持久化的数据快照（分类映射、中文描述、Trending 基线），由脚本写入 |

## 3. 架构与约定

- **外部依赖即 HTTP API**：所有“依赖”均为对 GitHub REST API (`api.github.com`) 和公开网页 (`github.com/trending/*`) 的 HTTPS 请求，通过 `urllib.request` 直接发起，无 SDK 封装。
- **无版本锁定**：Python 环境由 `actions/setup-python@v5` 固定为 `3.11`；Node.js 通过 `npx --yes vercel` 拉取最新 CLI，无版本约束。
- **私有凭据通过环境变量注入**：`GITHUB_TOKEN`/`GH_TOKEN`（GitHub PAT）、`REFRESH_KEY`（Vercel 自定义密钥）、`VERCEL_TOKEN`（Vercel CLI 令牌）均在 CI/Vercel 平台 secrets 中配置，代码中通过 `os.environ.get` 读取，不硬编码。
- **数据快照作为“软依赖”**：`known_categories.json` 固化已知项目的分类，`descriptions_zh.json` 缓存已翻译的简介，`trending_snapshot.json` 保存昨日星标数用于涨星榜差值计算。这些 JSON 随仓库一起提交，构成可复现的数据基线。
- **降级策略替代外部服务依赖**：当 GitHub Trending 页面抓取失败时，回退到基于 `trending_snapshot.json` 的差值模式；当翻译 API 全部不可用时保留原文。这使系统在无网络/限流场景下仍可产出可用页面。

## 4. 约定与约束

- **禁止引入第三方包**：构建脚本注释“仅依赖 Python 标准库，无需安装第三方包”，CI 流程中也无任何 `pip install` 步骤，该约定被工作流强制执行。
- **API 调用必须带 User-Agent**：所有 GitHub API 请求均设置 `User-Agent: starhub-auto-update` 或 `starhub-refresh`，符合 GitHub API 要求。
- **速率限制内建节流**：相邻请求间 `time.sleep(0.5~1)`，遵循 GitHub 建议的 ≥1s 间隔，避免二级速率限制。
- **CORS 白名单防护**：`api/refresh.js` 仅允许 `https://starhub-refresh.vercel.app` 和 `https://kwei168.github.io` 两个 Origin，并校验 `X-Refresh-Key` 头，防止跨站滥用。
- **并发安全**：Workflow 使用 `concurrency.group: starhub-update` 且 `cancel-in-progress: false`，配合 `git pull --rebase` 避免并发推送冲突。
- **敏感信息隔离**：GitHub PAT、Vercel Token、刷新密钥全部通过平台 Secrets 注入，源码中仅引用环境变量名。