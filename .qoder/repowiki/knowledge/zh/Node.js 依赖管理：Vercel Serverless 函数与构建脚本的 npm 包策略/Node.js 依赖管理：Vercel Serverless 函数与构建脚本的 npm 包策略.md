---
kind: dependency_management
name: Node.js 依赖管理：Vercel Serverless 函数与构建脚本的 npm 包策略
category: dependency_management
scope:
    - '**'
source_files:
    - package.json
    - .deploy-tmp/package.json
    - vercel.json
    - .vercelignore
    - api/article.js
---

## 1. 使用的系统与方案

本项目采用 **npm + Node.js** 作为唯一的第三方依赖管理系统，用于两类运行环境：
- **Vercel Serverless API**（`api/` 下的函数）：运行时依赖 `jsdom` 和 `@mozilla/readability`，由根目录 `package.json` 声明。
- **本地构建/测试工具**（`.deploy-tmp/` 中的 Playwright 脚本、各类 `.cjs`/`.py` 辅助脚本）：通过 `.deploy-tmp/package.json` 单独声明 `playwright-core`。

项目没有使用 lockfile（仓库中不存在 `package-lock.json` 或 `yarn.lock`），也没有私有 npm registry 或 `GOPRIVATE` 等配置。部署到 Vercel 时，Vercel 会在构建阶段自动执行 `npm install`（基于根 `package.json`）并打包 `node_modules`。

## 2. 关键文件

- `package.json`：定义项目名 `starhub-refresh`、标记为 `private`，声明两个生产依赖 `@mozilla/readability ^0.5.0` 与 `jsdom ^25.0.0`。
- `.deploy-tmp/package.json`：仅包含 `playwright-core ^1.63.0`，供 `.deploy-tmp/` 下的 E2E/验证脚本使用。
- `vercel.json`：声明各 `api/*.js` 函数的 `maxDuration`，间接决定依赖加载与执行时的资源上限。
- `.vercelignore`：排除 `rss_history.json`、`rss_cache.json` 等运行时缓存文件，避免污染部署产物。
- `api/article.js`：唯一显式 `require('jsdom')` 与 `require('@mozilla/readability')` 的文件，是依赖的实际消费点。
- `api/rss.js`、`api/events.js`、`api/news.js`、`api/search.js`、`api/agihunt.js`、`api/refresh.js`：其他 API 函数仅使用 Node 内置模块（`fs`、`path`、`crypto`、`fetch` 等），不引入额外第三方库。

## 3. 架构与约定

- **最小化依赖原则**：除文章全文提取外，所有 API 函数均只依赖 Node 内置模块。RSS 抓取直接使用原生 `fetch`（Vercel Edge/Runtime 提供），无需 axios 等 HTTP 库。
- **运行时依赖与构建依赖分离**：`package.json` 仅包含运行时必需的 `jsdom` 与 `readability`；Playwright 作为本地测试/截图工具，隔离在 `.deploy-tmp/package.json` 中，不会进入生产部署。
- **无版本锁定**：依赖使用 `^` 语义化版本范围（如 `^25.0.0`、`^0.5.0`、`^1.63.0`），允许次版本升级，但仓库未提交 lockfile，因此每次安装可能解析出不同补丁版本。
- **无 vendoring**：未将 `node_modules` 提交至仓库，也未使用 `npm ci --production` 之外的特殊安装策略。
- **安全约束内联于代码**：`api/article.js` 中对 URL 进行白名单校验（禁止 `localhost`、`.local`、私有 IP 段），防止 SSRF 攻击，这是在不引入额外安全库的情况下自行实现的约束。

## 4. 约定与约束

- **依赖来源**：全部来自官方 npm registry，未发现私有源、镜像或代理配置。
- **版本策略**：使用 caret (`^`) 范围，便于获得非破坏性更新；但缺少 lockfile 意味着 CI/本地安装的确定性无法保证。
- **部署绑定**：`vercel.json` 中每个 API 函数都设置了 `maxDuration`（10–60 秒不等），这实际上是对依赖运行时行为（网络请求、HTML 解析）的隐式超时约束——例如 `article.js` 中自定义了 `FETCH_TIMEOUT = 8000` 毫秒的 AbortController 超时，与 Vercel 函数超时形成双重保护。
- **忽略运行时数据**：`.vercelignore` 明确排除 `rss_history.json`、`rss_cache.json`，确保这些由依赖运行产生的缓存文件不会被误推送到生产环境。
- **Python 侧无依赖管理**：大量 `.py` 脚本（如 `build_rss_aggregator.py`、`merge_sources.py` 等）直接调用标准库或假设系统已安装 Python 包，未使用 `requirements.txt`、`pyproject.toml` 或 `pipenv`，这部分不属于本项目的依赖管理体系范畴。