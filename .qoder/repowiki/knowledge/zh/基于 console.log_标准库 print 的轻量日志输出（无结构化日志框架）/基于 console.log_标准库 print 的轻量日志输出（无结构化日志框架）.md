---
kind: logging_system
name: 基于 console.log/标准库 print 的轻量日志输出（无结构化日志框架）
category: logging_system
scope:
    - '**'
source_files:
    - api/rss.js
    - api/article.js
    - api/search.js
    - build_ai_daily.py
---

## 1. 使用的系统/方法

仓库没有引入任何第三方日志框架。后端 Vercel Serverless API（`api/*.js`）统一使用 Node.js 内置的 `console.log` / `console.error`；构建与数据管道脚本（如 `build_ai_daily.py`、各类 `check_*.py`、`verify_*.py`）使用 Python 标准库的 `print(..., file=sys.stderr)` 将错误信息输出到标准错误流，正常进度则通过 `console.log` 或 `print` 输出到 stdout。

## 2. 关键文件

- `api/rss.js`：RSS 聚合 API，集中了 `[rss]` 前缀的日志，包括快照加载、翻译缓存加载、单源抓取失败、合并结果统计等。
- `api/article.js`：全文提取 API，记录快照内容映射加载成功/失败。
- `api/search.js`：搜索 API，对 Google Translate / MyMemory 翻译端点的 HTTP 状态、响应体片段、异常进行 `console.error('[translate] ...')` 记录。
- `build_ai_daily.py`：AI 晨报构建脚本，大量使用 `print("[AI晨报] ...", file=sys.stderr)` 报告各渠道拉取/解析失败。
- 其他 `check_*.py` / `verify_*.py` / `_fix_*.py`：调试与校验脚本，使用 `print` 打印中间状态。

## 3. 架构与约定

- **按模块加前缀**：每条日志以方括号包裹的模块名作为前缀，如 `[rss]`、`[article]`、`[translate]`、`[AI晨报]`，便于在 Vercel Functions 日志中快速过滤。
- **成功/降级路径用 `console.log`**：例如“Loaded snapshot”“Loaded translation cache”“Serving snapshot”等仅用于记录运行态指标（sources/items 数量），不表示异常。
- **错误/异常路径用 `console.error` 或 `file=sys.stderr`**：网络超时、HTTP 非 2xx、XML 解析失败、JSON 回退失败等均走 stderr，以便 CI 或运行时平台捕获。
- **无 log level 管理**：没有 debug/info/warn/error 分级，也没有开关控制是否输出日志；所有 `console.log` 在生产环境中都会输出。
- **无结构化字段**：日志是拼接后的字符串，不是 JSON 对象；虽然包含 key/value 语义（如 `zh=...`、`status=...`），但并非机器可读的结构化格式。
- **无统一 logger 初始化**：每个文件各自调用 `console.log`/`print`，不存在共享的 logger 实例、格式化器或 sink 配置。
- **敏感信息处理**：`search.js` 中对上游错误做了脱敏——对外返回通用错误码（502/503），而详细错误仅写入 stderr，避免泄露给前端。

## 4. 约定与约束

- **Vercel Serverless 环境依赖平台日志收集**：API 层完全依赖 Vercel 控制台收集的 stdout/stderr 日志，没有落盘文件或外部日志服务集成。
- **构建脚本错误必须写 stderr**：`build_ai_daily.py` 中所有失败分支都显式指定 `file=sys.stderr`，确保 CI 能正确识别失败。
- **日志前缀需保持模块一致性**：同一模块内所有日志使用相同前缀（如 `rss.js` 全部为 `[rss]`），这是代码中体现的约定而非强制规则。
- **无日志采样/限流**：高频路径（如每次请求都打印快照大小）直接输出，未做节流或采样。
- **无日志持久化/轮转**：日志仅在进程生命周期内存在，随函数实例销毁而消失。

总体而言，该仓库采用最轻量的“console.log + stderr print”方式实现日志输出，依靠模块前缀和人类阅读来定位问题，没有结构化日志、级别控制、采集聚合或持久化机制。