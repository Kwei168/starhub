---
kind: error_handling
name: Vercel Serverless API 错误处理与降级策略
category: error_handling
scope:
    - '**'
source_files:
    - api/rss.js
    - api/search.js
    - api/events.js
    - api/refresh.js
    - api/article.js
    - api/agihunt.js
    - build_rss_aggregator.py
    - build_ai_daily.py
---

## 1. 整体方法

本项目采用 **轻量级 Vercel Serverless Functions**（Node.js）作为后端，没有统一的错误框架或中间件。每个 API 文件（`api/*.js`）自包含请求校验、CORS 白名单、上游调用、缓存与错误返回逻辑，通过 `try/catch` + `res.status().json()` 直接返回 JSON 错误体。

前端页面（`rss-aggregator.html`、`ai-daily.html`）由 Python 构建脚本生成，内嵌大量 `try/catch` 包裹 `localStorage` 读写、`fetch` 调用和 DOM 操作，失败时静默降级（空对象/默认值），保证页面在禁用存储或网络异常时仍可渲染。

## 2. 关键文件与位置

- `api/rss.js` — RSS 聚合主入口，含滚动缓存、快照回退、HTML 清洗、翻译降级
- `api/search.js` — GitHub 仓库搜索，含中文→英文翻译双端点降级、422 查询重试
- `api/events.js` — 关注账号动态聚合，按用户并发抓取并静默跳过失败用户
- `api/refresh.js` — 触发 GitHub Actions workflow_dispatch，带 Origin 白名单 + `X-Refresh-Key` 鉴权
- `api/article.js`、`api/agihunt.js` — 其他辅助 API（结构类似）
- `build_rss_aggregator.py` / `build_ai_daily.py` — 生成前端 HTML，内嵌容错 JS

## 3. 架构与约定

### 3.1 统一错误响应格式
所有 API 错误均以 `{ error: string }` 的 JSON 形式返回，HTTP 状态码区分语义：
- `400` — 请求体格式错误、参数校验失败（如关键词过短）
- `403` — CORS 白名单未命中或缺少 `X-Search-Key` / `X-Refresh-Key`
- `405` — 不支持的 HTTP Method
- `500` — 服务端配置缺失（如 `GH_TOKEN` 未设置）
- `502` — 上游服务不可用（GitHub API、RSS 源等）
- `503` — 上游限流（GitHub 搜索 429/403）

### 3.2 分层降级策略（rss.js 为核心示例）
`fetchOne` 对单个 RSS 源的抓取实现三层回退：
1. **成功** → 更新内存中的 `rollingCache`，返回新鲜数据
2. **失败但有缓存** → 返回 `_stale: true` 标记的旧数据
3. **失败且无缓存** → 返回空 `items` 数组 + `_error: err.message`

完整响应层还有快照优先策略：优先返回构建时生成的 `rss_api_snapshot.json`（72h 累积数据），不存在时才实时抓取；`meta=1` 探测端点仅返回总条数用于增量检测。

### 3.3 外部依赖容错
- **翻译服务**：`rss.js` 中 T1 英文源标题/摘要翻译使用三个端点（Google gtx → MyMemory → Google dict-chrome），任一成功即返回，全部失败则跳过翻译保留原文；`search.js` 同样使用 Google → MyMemory 双端点降级。
- **GitHub API**：`events.js` 对每个用户的 events 抓取使用 `Promise.allSettled`，失败用户静默跳过；`search.js` 遇到 422 查询语法错误时自动去引号重试一次。
- **超时控制**：所有 `fetch` 调用均配合 `AbortSignal.timeout()`（5s~15s 不等），避免单源拖垮整个请求。

### 3.4 安全边界
- CORS 严格白名单：仅允许 `https://starhub-refresh.vercel.app` 与 `https://kwei168.github.io`（比较时统一小写）
- 敏感操作（refresh、search）需额外 `X-Refresh-Key` / `X-Search-Key` 头匹配环境变量 `REFRESH_KEY`
- 上游错误细节不向客户端暴露（如 GitHub 错误仅记录日志，返回通用 `上游服务不可用`）

### 3.5 前端容错
构建脚本注入的 JS 代码对 `localStorage`、`history.replaceState`、DOM focus 等操作全部包裹 `try/catch`，捕获后忽略错误，确保极端环境（Iframe、无痕模式、移动端限制）下页面仍可运行。

## 4. 约定与约束

- **无全局错误类型定义**：错误以字符串消息传递（`err.message`），没有自定义 Error 子类或错误码枚举
- **日志即诊断**：所有异常通过 `console.error('[模块] 原因')` 输出，依赖 Vercel 日志而非结构化日志系统
- **幂等性**：`rss.js` 的 `fullCache` 与 `events.js` 的 `cache` 基于时间戳 TTL 失效，冷启动丢失可接受（Serverless 特性）
- **禁止 panic/rethrow**：未发现 `throw` 冒泡到顶层的模式，所有异步路径均在函数内部 catch 并转为 HTTP 响应
- **测试覆盖**：`__pycache__` 及根目录存在若干 `test_*.py`、`check_*.py` 脚本，但未见针对 API 错误的单元测试文件
- **文档约束**：各 API 文件顶部注释明确标注了认证方式、CORS 策略、缓存 TTL 与降级行为，构成事实上的契约文档