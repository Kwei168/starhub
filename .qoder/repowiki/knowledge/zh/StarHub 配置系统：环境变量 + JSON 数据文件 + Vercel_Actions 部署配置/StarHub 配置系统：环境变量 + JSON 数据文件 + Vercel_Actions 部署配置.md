---
kind: configuration_system
name: StarHub 配置系统：环境变量 + JSON 数据文件 + Vercel/Actions 部署配置
category: configuration_system
scope:
    - '**'
source_files:
    - fetch_and_build.py
    - api/refresh.js
    - .github/workflows/update.yml
    - vercel.json
    - .vercel/project.json
    - known_categories.json
    - descriptions_zh.json
    - trending_snapshot.json
    - dev_render.py
---

## 1. 使用的系统与方式

该项目没有使用专门的配置框架（如 dotenv、pydantic-settings、configparser），而是采用**纯代码常量 + 环境变量 + JSON 数据文件 + 平台配置文件**的组合方式，分别覆盖三类配置：

- **运行时凭据与开关**：通过环境变量注入，由 Python 脚本和 Vercel Serverless Function 直接读取。
- **业务数据/分类/快照**：以仓库内 JSON 文件形式持久化，构建时读写。
- **部署与平台行为**：通过 `vercel.json`、`.github/workflows/update.yml`、`.vercel/project.json` 声明式配置。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `fetch_and_build.py` | 主构建脚本；硬编码分类、颜色、阈值等常量，并读取环境变量 `GITHUB_TOKEN` / `GH_TOKEN` |
| `api/refresh.js` | Vercel Serverless 函数；从 `process.env` 读取 `REFRESH_KEY`、`GH_TOKEN` |
| `.github/workflows/update.yml` | GitHub Actions 定时任务与手动触发入口，定义运行环境、Python 版本、并发策略 |
| `vercel.json` | Vercel 函数路由与超时限制（`maxDuration`） |
| `.vercel/project.json` | Vercel 项目标识（projectId/orgId） |
| `known_categories.json` | 已知仓库 → 分类映射（构建时读/写） |
| `descriptions_zh.json` | 中文描述缓存（构建时读/写） |
| `trending_snapshot.json` | AI 排行榜基线快照（构建时读/写） |
| `template.html` / `index.html` | 模板与渲染产物；`dev_render.py` 用于本地重新渲染 |

## 3. 架构与约定

### 3.1 环境变量（运行时配置）

| 变量 | 来源 | 用途 | 读取位置 |
|---|---|---|---|
| `GITHUB_TOKEN` 或 `GH_TOKEN` | GitHub Actions 的 secrets 或本地环境 | 调用 GitHub API 的鉴权令牌 | `fetch_and_build.py` 第 583 行：`os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")` |
| `GH_TOKEN` | Vercel 环境变量（fine-grained PAT） | `api/refresh.js` 调用 GitHub Actions workflow_dispatch API | `api/refresh.js` 第 32 行 |
| `REFRESH_KEY` | Vercel 环境变量 | 请求头 `X-Refresh-Key` 的校验密钥，防无头扫描器 | `api/refresh.js` 第 26–30 行 |
| `VERCEL_TOKEN` | GitHub Actions secrets | 触发 `npx vercel --prod` 部署 | `.github/workflows/update.yml` 第 47–49 行 |

约定：GitHub Token 支持双键名兼容（`GITHUB_TOKEN` 优先，回退到 `GH_TOKEN`），便于在 Actions 和 Vercel 两种环境中复用同一变量名。

### 3.2 硬编码常量（代码内配置）

`fetch_and_build.py` 顶部集中定义所有业务常量：
- `USER = "Kwei168"`：抓取目标用户。
- `CATS`：分类列表（key/label/color/dark），共 11 类。
- `LANG_COLORS`：语言 → 颜色映射。
- `DEFAULT_FAVS`：默认收藏仓库列表。
- `FALLBACK_DESC`：空描述项目的兜底中文说明。
- `AI_TOPICS`、`AI_MIN_STARS`、`NEW_MIN_STARS`、`TREND_TOP`、`TREND_MAX_STARS`：排行榜阈值。
- `TREND_LANG_PAGES`：Trending 多语言页列表。

这些常量不通过外部配置加载，修改需改代码后提交。

### 3.3 JSON 数据文件（持久化状态）

构建过程中读写三个 JSON 文件，作为“可编辑的业务配置”：
- `known_categories.json`：已知仓库的分类映射。首次缺失则忽略，每次构建后回写。
- `descriptions_zh.json`：中文描述缓存。翻译结果写入，避免重复调用翻译 API。
- `trending_snapshot.json`：AI 项目星标快照，用作涨星榜差值计算的基线。

这三个文件是构建产物的一部分，随 `index.html` 一起被 Git 追踪并在 Actions 中 commit/push。

### 3.4 部署与平台配置

- `vercel.json`：声明函数路由 `api/refresh.js`、`api/search.js`、`api/events.js` 及各自最大执行时长（10s / 30s / 60s）。
- `.github/workflows/update.yml`：
  - 触发源：`cron: "10 * * * *"`（每小时 UTC :10 兜底刷新）+ `workflow_dispatch`（手动触发）。
  - 并发：`concurrency.group: starhub-update`，且 `cancel-in-progress: false`，禁止取消正在运行的更新。
  - 权限：`contents: write`，允许推送生成的 HTML 与 JSON。
  - 运行环境：`ubuntu-latest` + Python 3.11。
  - 步骤：checkout → setup-python → 运行 `python fetch_and_build.py` → diff 检测 → commit/pull-rebase/push → `npx vercel --prod` 部署。
- `.vercel/project.json`：绑定 Vercel 团队项目 ID，使 `vercel deploy` 能定位到正确项目。

### 3.5 安全边界

- `api/refresh.js` 实现双重防护：① CORS Origin 白名单（`https://starhub-refresh.vercel.app`、`https://kwei168.github.io`）；② `X-Refresh-Key` 请求头必须匹配 `REFRESH_KEY` 环境变量。
- 非白名单来源直接返回 403 且不附带 CORS 头，浏览器侧无法读取响应体。
- GitHub API 错误细节不向上游回显，仅记录到 Vercel 日志，防止信息泄露。

## 4. 约定与约束

- **Token 来源**：GitHub API 调用必须通过环境变量传入 token；未配置时 `api/refresh.js` 返回 500，`fetch_and_build.py` 降级为无认证访问（受 GitHub 未登录速率限制）。
- **本地开发**：`dev_render.py` 仅用于本地预览模板改动，不参与 GitHub Actions 构建流程。
- **数据一致性**：Actions 推送前执行 `git pull --rebase`，避免并发提交冲突。
- **构建幂等性**：若 `git diff --cached --quiet` 检测到无变更，跳过 commit/push。
- **Trending 降级**：当 Trending 抓取失败时，自动回退到基于 `trending_snapshot.json` 的差值模式；若 AI 池为空则保留旧快照，避免清空基线导致无法自愈。
- **时间基准**：所有日期计算统一使用北京时间（UTC+8），通过 `datetime.now(timezone(timedelta(hours=8)))` 获取。
- **JSON 注入安全**：输出到 `<script>` 块的数据会转义 `<` 为 `\u003c`，防止 `</script>` 注入攻击（见 `_safe_json` 注释）。