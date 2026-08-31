---
kind: error_handling
name: Vercel Serverless 函数与 Python 构建脚本的错误处理模式
category: error_handling
scope:
    - '**'
source_files:
    - api/events.js
    - api/refresh.js
    - api/search.js
    - fetch_and_build.py
    - dev_render.py
---

## 1. 整体方法

本项目采用两套并行的错误处理策略：
- **Node.js 侧（Vercel Serverless 函数）**：基于原生 `fetch` + `try/catch`，通过显式设置 HTTP 状态码和 `{ error: '...' }` JSON 响应体向调用方传递错误；对上游 GitHub API 的失败进行降级/静默跳过。
- **Python 侧（构建/抓取脚本）**：使用 `except Exception` 宽泛捕获网络异常，打印到 `stderr` 后返回 `None` 或继续执行，以“部分失败不影响整体构建”为目标。

项目没有自定义错误类型、错误码枚举、中间件或 panic/recover 机制——所有错误均以语言原生方式就地处理。

## 2. 关键文件

| 文件 | 职责 | 错误处理要点 |
|---|---|---|
| `api/events.js` | 聚合关注用户近 24h 动态 | 单个用户事件拉取失败 `break` 静默跳过；外层 `try/catch` 统一返回 502；缺少 `GH_TOKEN` 返回 500 |
| `api/refresh.js` | 中转触发 GitHub Actions workflow_dispatch | 认证失败返回 403；GitHub API 非 204 时返回 502（不泄露上游细节）；超时/网络异常统一 502 |
| `api/search.js` | 中文→英文翻译 + GitHub 仓库搜索 | 翻译双端点（Google → MyMemory）失败回退原词；422 查询语法错误清洗后重试一次；403/429 限流返回 503；请求体验证失败返回 400 |
| `fetch_and_build.py` | 定时抓取 GitHub 数据并生成静态页 | 每个网络请求包裹 `except Exception`，打印到 stderr 后返回空结果，保证单步失败不中断流水线 |
| `dev_render.py` | 本地开发工具 | 缺失模板占位符直接 `raise SystemExit` 终止渲染 |

## 3. 架构与约定

### 3.1 Vercel Serverless 函数的统一错误契约
三个 handler 遵循相同结构：
1. **CORS 预检**：OPTIONS 请求按白名单返回 204 或 403。
2. **方法校验**：非允许方法返回 `405 Method Not Allowed`。
3. **来源校验**：非白名单 Origin 返回 `403 Forbidden`。
4. **鉴权校验**：`refresh.js` / `search.js` 要求 `X-Refresh-Key` / `X-Search-Key` 等于 `REFRESH_KEY` 环境变量，否则 403。
5. **配置校验**：缺少 `GH_TOKEN` 返回 `500` 并提示环境变量未配置。
6. **业务 try/catch**：外层 `try { ... } catch (e) { res.status(502).json({ error: '上游服务不可用' }) }`，将一切未预期异常归一为 502。
7. **上游错误屏蔽**：GitHub API 的非成功响应（如 403/429/422）被转换为面向调用方的友好错误消息，原始错误仅记录在 Vercel 日志中，避免信息泄露。

### 3.2 细粒度降级策略
- **events.js**：`Promise.allSettled` 并发拉取多个用户的事件，单个用户失败不影响其他用户；`fetchUserEvents` 内层 `try/catch` 在任一页面失败时 `break` 停止翻页。
- **search.js**：翻译优先 Google Translate，失败降级到 MyMemory，再失败退回原词；GitHub 搜索 422 时自动清洗查询（去引号、压缩空白）重试一次。
- **Python 脚本**：翻译、星标列表、AI 池、新秀榜等每个外部调用独立 `try/except`，失败仅打印 stderr 并返回空集合，确保最终仍能产出静态页面。

### 3.3 输入验证
`search.js` 对请求体做基础校验：JSON 解析失败返回 400；关键词少于 2 字符返回 400；`sort` 参数限定在白名单 `best-match/stars/updated`；`page` 限制在 `[1, 34]`。

## 4. 约定与约束

- **禁止向上游暴露内部错误细节**：refresh.js 和 search.js 明确注释“不向上游调用者回显 GitHub 错误细节（防信息泄露），细节由 Vercel 日志记录”。
- **上游失败一律映射为 5xx**：网络异常、超时、GitHub API 非 2xx 均返回 502（上游服务不可用）；限流（403/429）返回 503；配置缺失返回 500。
- **可恢复错误走降级而非抛错**：翻译失败降级、422 查询清洗重试、单个用户事件失败跳过，体现“部分失败不影响整体可用性”的设计。
- **Python 构建脚本采用“宽容失败”**：所有网络 I/O 使用 `except Exception` 吞掉异常并返回 None，因为该脚本运行在 CI 环境中，目标是尽可能产出可用产物。
- **无全局错误中间件**：每个 handler 自行实现 CORS、鉴权、try/catch，不存在统一的错误处理中间件或框架级异常处理器。
- **无自定义错误类型**：Node 侧直接使用字符串错误消息；Python 侧仅在 dev_render.py 中使用 `SystemExit` 作为致命错误退出码。