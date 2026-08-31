---
kind: build_system
name: GitHub Actions + Vercel Serverless 驱动的静态站点构建与部署流水线
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/update.yml
    - fetch_and_build.py
    - dev_render.py
    - vercel.json
    - api/refresh.js
    - template.html
---

## 1. 构建系统总览

本项目是一个**纯静态单页应用**（`index.html` + `template.html`），没有传统意义上的编译步骤。构建的本质是：通过 Python 脚本 `fetch_and_build.py` 从 GitHub API 抓取数据、分类、翻译简介，再注入到 HTML 模板中生成最终的 `index.html`；然后通过 GitHub Actions 定时任务提交产物并触发 Vercel 部署。

- **运行时环境**：Python 3.11（仅标准库，无第三方依赖）
- **CI/CD**：GitHub Actions (`update.yml`) + Vercel CLI
- **实时刷新入口**：Vercel Serverless 函数 (`api/refresh.js`) 调用 GitHub Actions workflow_dispatch API 触发重新构建

## 2. 关键文件与职责

| 文件 | 角色 |
|---|---|
| `.github/workflows/update.yml` | CI 流水线定义：cron 每小时 :10 触发，checkout → setup-python 3.11 → 执行构建 → 条件提交 → vercel deploy |
| `fetch_and_build.py` | 核心构建脚本：拉取 starred repos / trending / events，分类、翻译、渲染 `index.html` |
| `dev_render.py` | 本地开发工具：从已生成的 `index.html` 提取常量，重新渲染 `template.html` 用于预览模板改动 |
| `vercel.json` | Vercel 配置：声明 `api/refresh.js`、`api/search.js`、`api/events.js` 为 serverless function 及最大执行时长 |
| `api/refresh.js` | 中转函数：校验 CORS + `X-Refresh-Key` 后调用 GitHub Actions dispatch API 触发本仓库 update.yml |
| `template.html` | HTML 模板，包含 `__DATA__`、`__CATS__`、`__LANGS__`、`__FAVS__`、`__TRENDING__`、`__FEED__`、`__UPDATED__` 占位符 |
| `known_categories.json` / `descriptions_zh.json` / `trending_snapshot.json` | 构建产物缓存：分类映射、中文描述缓存、Trending 基线快照 |

## 3. 构建流程与架构决策

### 3.1 定时构建（兜底）
`update.yml` 使用 cron `10 * * * *`（UTC 整点后 10 分钟）触发，避免整点高峰被 GitHub 跳过。Job 顺序：
1. `actions/checkout@v4`
2. `actions/setup-python@v5` (python-version: "3.11")
3. `python fetch_and_build.py` — 抓取数据并写入 `index.html`、`known_categories.json`、`descriptions_zh.json`、`trending_snapshot.json`
4. 条件提交：`git add` 上述四个文件，若 `git diff --cached --quiet` 则跳过 commit
5. `git pull --rebase` 后再 push，避免并发冲突
6. `npx --yes vercel --prod --yes --token $VERCEL_TOKEN` 部署到 Vercel

### 3.2 手动触发（实时刷新）
前端轮询 `api/events` 获取关注账号动态；当需要主动刷新全站时，调用 `api/refresh.js`，该函数验证来源白名单和 `REFRESH_KEY` 后，向 GitHub API 发起 `POST /repos/Kwei168/starhub/actions/workflows/update.yml/dispatches`，从而触发 `workflow_dispatch` 分支的更新流程。

### 3.3 构建产物与版本策略
- **版本号**：无显式版本号，以 Git commit 作为版本标识
- **增量提交**：仅当 `index.html` 等文件有变更时才 commit & push，减少无效推送
- **并发控制**：`concurrency.group: starhub-update` 且 `cancel-in-progress: false`，保证同一时间只有一个更新 job 运行
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
- **Vercel 函数超时**：refresh 10s、search 30s、events 60s，由 `vercel.json` 显式声明