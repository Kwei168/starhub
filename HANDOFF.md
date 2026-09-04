# StarHub 项目移交文档

> 最后更新：2026-09-04

## 一、项目一句话

**Kwei168 的 GitHub Star 收藏台**——自动拉取用户 starred repos，智能分类、翻译描述、生成静态单页站，托管在 Vercel + GitHub Pages 双端。

- 线上地址：https://starhub-refresh.vercel.app （Vercel，主站）
- 镜像地址：https://kwei168.github.io/starhub/ （GitHub Pages，备用）
- 仓库：https://github.com/Kwei168/starhub

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     数据更新触发层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ cron-job.org │  │ GitHub       │  │ 用户手动          │  │
│  │ 每小时 POST  │  │ Actions      │  │ /api/refresh      │  │
│  │ → /api/refresh│  │ schedule     │  │ (前端按钮)        │  │
│  └──────┬───────  └──────┬───────  └────────┬──────────┘  │
│         │                 │                    │             │
│         ▼                 ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Vercel Serverless: /api/refresh.js           │    │
│  │   校验 X-Refresh-Key → 调用 GitHub workflow_dispatch │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │       GitHub Actions: .github/workflows/update.yml   │    │
│  │   checkout → python fetch_and_build.py → commit →   │    │
│  │   git push → npx vercel --prod                       │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Python: fetch_and_build.py              │    │
│  │   拉取 starred repos → 智能分类 → 翻译描述 →         │    │
│  │   生成 index.html + ai-daily.html                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     前端实时数据层                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/events.js                   │    │
│  │  拉取关注用户 24h 动态 → 10min 缓存 → 前端 30min 轮询 │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/search.js                   │    │
│  │  中文→英文翻译 → GitHub 搜索 API → 10min 缓存         │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Vercel Serverless: /api/news.js                     │    │
│  │  36氪(RSSHub镜像链) + Redis博客 → 干净JSON → 10min缓存│    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 双数据系统

| 区域 | 数据源 | 更新机制 | 文件 |
|---|---|---|---|
| **主数据区**（Star 项目列表） | GitHub API: `/users/Kwei168/starred` | workflow 触发 `fetch_and_build.py` 静态构建 | `index.html` |
| **关注动态区**（右侧 Feed） | GitHub API: `/users/{user}/events/public` | `/api/events.js` 实时查询，前端 30min 轮询 | 运行时 API |
| **AI 晨报** | AIHOT 公开 API v1（降级回退 RSS）+ HN / The Verge / TechCrunch / arXiv / 36氪(RSSHub镜像) / Redis / AtlasNote 多渠道 | `build_ai_daily.py` 每次构建时云端拉取生成 | `ai-daily.html` |

---

## 三、核心文件清单

### 构建与数据

| 文件 | 行数 | 作用 |
|---|---|---|
| `fetch_and_build.py` | 666 | **核心入口**。拉取 starred repos、智能分类、翻译描述、生成 `index.html`。末尾调用 `build_ai_daily.main()` |
| `build_ai_daily.py` | ~1042 | AI 晨报生成器。主源 AIHOT 公开 API v1（匿名 `/api/v1/items`，失败降级 RSS → 本地 JSON）→ 筛选 36h 条目；多渠道快讯：Hacker News / The Verge / TechCrunch / arXiv / 36氪(RSSHub镜像) / Redis博客 / AtlasNote → 英译中 → 跨源四层去重（精确/子串/同URL/摘要互含）→ 头条评分制（跨源报道数+编辑分+信源权重+新鲜度）→ 生成报纸风格 `ai-daily.html`，页脚显示信源成败状态栏 |
| `template.html` | ~1905 | **页面模板**。包含全部 CSS + HTML 结构 + JS 交互逻辑。`fetch_and_build.py` 读取此文件，替换占位符生成 `index.html`。2026-08-29 重设计为纸感编辑风（暖纸底+衬线标题+等宽数字），搜索置顶通栏+340px粘性侧栏 |
| `index.html` | 自动生成 | 最终部署页面。**不要直接编辑**，每次 workflow 会从 template 重新生成 |
| `ai-daily.html` | 自动生成 | AI 晨报页面。**不要直接编辑**，每次构建重新生成 |

### 数据文件（workflow 自动维护）

| 文件 | 作用 |
|---|---|
| `known_categories.json` | 项目→分类映射缓存（避免每次重新分类） |
| `descriptions_zh.json` | 项目→中文描述缓存（避免重复翻译） |
| `trending_snapshot.json` | 趋势分析快照数据 |

### Vercel Serverless 函数

| 文件 | 路由 | 方法 | 认证 | 超时 | 作用 |
|---|---|---|---|---|---|
| `api/refresh.js` | `/api/refresh` | POST | X-Refresh-Key + Origin 白名单 | 10s | 触发 GitHub Actions workflow_dispatch |
| `api/events.js` | `/api/events` | GET | Origin 白名单（无 key） | 60s | 关注用户 24h 动态聚合，10min 缓存，前端相对时间显示+分类筛选+游标分页 |
| `api/search.js` | `/api/search` | POST | X-Search-Key (= REFRESH_KEY) + Origin 白名单 | 30s | 全网 GitHub 仓库搜索，中文翻译，10min 缓存 |
| `api/news.js` | `/api/news` | GET | Origin 白名单（放行无 Origin 同源请求） | 30s | 36 氪 (RSSHub 镜像链)+Redis 博客 RSS 代理，输出干净 JSON，10min 缓存 |
| `api/rss.js` | `/api/rss` | GET | CORS 允许所有来源（`*`） | 60s | RSS 聚合实时 API，153 源全量抓取，**20 路并发**，**5s 超时**，滚动缓存，5min 服务端缓存 |

### 配置

| 文件 | 作用 |
|---|---|
| `vercel.json` | Vercel 项目配置，声明 4 个 serverless 函数及超时 |
| `.github/workflows/update.yml` | GitHub Actions 工作流定义 |
| `.gitignore` | 忽略 `__pycache__/`、`.deploy-tmp/` 等 |

### 辅助目录

| 目录 | 作用 |
|---|---|
| `.deploy-tmp/` | 部署/调试脚本集合（trigger-workflow.cjs、verify-*.cjs 等），不参与构建 |
| `docs/superpowers/` | 历史设计文档和实施计划 |
| `.qoder/repowiki/` | Qoder 知识卡片（模块级技术文档） |

---

## 四、关键配置

### Vercel 环境变量（Project: starhub-refresh）

| 变量名 | 用途 | 类型 |
|---|---|---|
| `GH_TOKEN` | GitHub PAT（fine-grained），需 `contents:write` + `actions:write` 权限 | Secret |
| `REFRESH_KEY` | 弱防护密钥，用于 `/api/refresh` 和 `/api/search` 的 header 校验 | Secret |
| `VERCEL_TOKEN` | Vercel 部署令牌（GitHub Actions 中使用） | Secret（workflow secrets） |

**当前值**（2026-08-28 更新）：
- `REFRESH_KEY` = `sk_starhub_refresh_20260828`
- `GH_TOKEN` = 见 Vercel 控制台（Secret，不可查看）

### 外部服务

| 服务 | 用途 | 配置 |
|---|---|---|
| **cron-job.org** | 每小时 POST 到 `/api/refresh` 触发构建 | URL: `https://starhub-refresh.vercel.app/api/refresh`，Header: `X-Refresh-Key: sk_starhub_refresh_20260828` |
| **AIHOT API v1** | AI 晨报主数据源（公开匿名） | `https://aihot.virxact.com/api/v1/items` |
| **AIHOT RSS** | AI 晨报降级数据源 | `https://aihot.virxact.com/feed.xml` |
| **RSSHub 镜像链** | 36氪 AI 资讯流中转（官方 RSS 有人机验证） | 4 个镜像按可用性排序，依次尝试 |
| **Redis Blog** | Redis 官方博客 RSS | `https://redis.io/feed/` |
| **AtlasNote** | AI 深度文章（架构/创业/研究方法论），中英双语同文各发一条，按 slug 归并偏好中文版；周更 2-4 篇，36h 窗口未命中属正常 | `https://atlasnote.ai/rss.xml` |
| **HN / Verge / TechCrunch / arXiv** | AI 晨报多渠道快讯 | 见 `build_ai_daily.py` 常量配置 |

### 分类体系（11 类）

| key | 标签 | 颜色 |
|---|---|---|
| `agent` | AI Agent & Skills | 蓝 |
| `distill` | 思维蒸馏 & 认知 | 紫 |
| `video` | AI 视频创作 | 红 |
| `coding` | AI 编程 & 工具链 | 绿 |
| `content` | 内容创作 & 排版 | 粉 |
| `learning` | AI 学习 & 教程 | 黄 |
| `assistant` | AI 助手 & 应用 | 青 |
| `tools` | 实用工具 & 资源 | 灰 |
| `finance` | 金融 & 交易 | 金 |
| `business` | 商业 · 一人公司与知产 | 橙 |
| `frontend` | 前端 & 设计系统 | 蓝绿 |

### 晨报分类体系（6 类，2026-08-29 新增「海外热点」）

| 分类 | 来源 |
|---|---|
| AI 模型 | AIHOT API/RSS |
| AI 产品 | AIHOT API/RSS |
| 行业动态 | AIHOT API/RSS + 36氪 |
| 海外热点 | Hacker News / The Verge / TechCrunch / arXiv / Redis |
| 论文 | arXiv + AIHOT + AtlasNote（论文解读类） |
| 技巧观点 | AIHOT API/RSS + AtlasNote |

### 导航栏结构

1. ** AI 晨报** — 高亮入口，链接到 `ai-daily.html`
2. **📚 学习资源 ** — 小林笔记、KamaCoder、Agents Course、Vibe Coding、AGI Hunt
3. **📡 资讯平台 ▾** — NewsNow、今日热榜、赋范空间、V2EX、Linux Do
4. **🤖 AI 工具 ▾** — CodeFather、CodeFather AI

---

## 五、常见操作手册

### 5.1 手动触发构建/部署

```bash
# 方式 1：通过 API（推荐）
node .deploy-tmp/trigger-workflow.cjs

# 方式 2：GitHub 页面手动触发
# 进入仓库 → Actions → Update Star Hub → Run workflow

# 方式 3：推送代码到 main（workflow 无 on:push，不会自动触发！）
# 推送后必须手动触发 workflow_dispatch
```

### 5.2 添加导航链接

1. 编辑 `template.html`，在对应 `.nav-drop-panel` 内添加 `<a>` 标签
2. 运行 `python fetch_and_build.py` 重新生成 `index.html`
3. 提交 `template.html` + `index.html`
4. 推送后手动触发 workflow 部署

**注意**：必须同时改 `template.html` 和 `index.html`，否则 workflow 会用旧 template 覆盖 `index.html`。

### 5.3 修改分类

编辑 `fetch_and_build.py` 中的 `CATS` 列表。已有项目的分类缓存在 `known_categories.json`，修改分类 key 后需要清理该文件中对应条目才能重新分类。

### 5.4 修改 REFRESH_KEY

1. 修改 `template.html` 中的 `REFRESH_KEY` 常量
2. 在 Vercel → Environment Variables 中更新 `REFRESH_KEY` 值
3. **点击 Redeploy**（Vercel 环境变量变更不会自动生效，必须重新部署）
4. 提交推送 `template.html`，触发 workflow

### 5.5 本地预览

```bash
python dev_render.py   # 本地渲染预览（不拉取真实数据）
python fetch_and_build.py  # 完整构建（需要 GitHub API 访问）
```

---

## 六、部署流程详解

```
push code → (不会自动触发！)
                ↓
手动触发 workflow_dispatch (或 cron-job.org 每小时触发)
                ↓
GitHub Actions: update.yml
  1. checkout main
  2. setup Python 3.11
  3. python fetch_and_build.py
     - 拉取 Kwei168 的 starred repos（分页，每页 100）
     - 智能分类（关键词匹配 + known_categories.json 缓存）
     - 翻译英文描述为中文（Google 翻译 → 保留原文）
     - 生成 index.html（从 template.html 替换占位符）
     - 调用 build_ai_daily.main() 生成 ai-daily.html
  4. git add + commit + push（仅当有变更时）
  5. npx vercel --prod --yes --token $VERCEL_TOKEN
                ↓
Vercel 部署完成（约 2-3 分钟）
```

### 关键约束

- **workflow 没有 `on: push` 触发器**，push 代码后必须手动触发 `workflow_dispatch`
- **`index.html` 是自动生成文件**，直接编辑会被 workflow 覆盖
- **Vercel 环境变量变更后必须 Redeploy**，否则新值不生效
- **concurrency: cancel-in-progress: false**，防止并发构建互相覆盖

---

## 七、踩过的坑

### 7.1 GitHub Actions schedule 不可靠
免费账户的 cron 任务经常被延迟或直接跳过（实测出现 11h、10h 空白期）。
**解决**：引入 cron-job.org 每小时 POST 触发作为主力，GitHub schedule 降级为兜底。

### 7.2 workflow 覆盖手动修改
`fetch_and_build.py` 从 `template.html` 重新生成 `index.html`。如果 workflow 在手动修改 `index.html` 之后运行，会覆盖手动修改。
**解决**：修改导航栏等模板内容时，必须同时改 `template.html` 和 `index.html`，并在 workflow 运行前提交。

### 7.3 git push 被拒绝（远端有新提交）
workflow 自动构建后会 push 新 commit，导致本地 push 被拒。
**解决**：`git stash && git pull --rebase && git push && git stash drop`。自动生成文件冲突用 `git checkout --theirs <file>`。

### 7.4 Vercel 环境变量更新后不生效
修改 Environment Variables 后，Vercel 提示 "A new deployment is needed"。但如果有更新的部署已存在，Redeploy 旧部署会失败。
**解决**：通过触发新的 workflow 来部署（workflow 的 vercel --prod 会使用最新环境变量）。

### 7.5 refresh.js 的 Origin 白名单拦截服务端调用
cron-job.org 的请求没有浏览器 Origin header，被 403 拒绝。
**解决**：修改 `refresh.js`，携带正确 `X-Refresh-Key` 的请求跳过 Origin 检查。

### 7.6 RSS 日期解析 Windows 兼容
`datetime.strptime` 的 `%z` 在 Windows 下不识别 `GMT`。
**解决**：`_parse_rss_date()` 中先 `s.replace(" GMT", " +0000")`。

### 7.7 search.js 和 refresh.js 共用 REFRESH_KEY
两个 API 使用同一个 `REFRESH_KEY` 环境变量。修改 key 时需同步更新前端代码和 Vercel 环境变量。

### 7.8 36氪 RSS 有人机验证反爬
36氪官方 RSS（36kr.com/feed*）有人机验证，浏览器/服务器直连均被拦截；RSSHub 公共镜像 CORS 头不合法，前端无法直连。
**解决**：由 `/api/news.js` 在服务端中转，RSSHub 镜像链按可用性排序依次尝试（部分镜像封数据中心 IP）。

### 7.9 AI 晨报多源去重
多渠道抓取后同一事件可能出现在多个源（如 AIHOT + 36氪 + Verge 报道同一件事）。
**解决**：跨源四层去重——①规范化标题精确匹配 → ②标题子串包含 → ③规范化 URL 相同（去协议/www/utm 参数，覆盖同文被改写标题后的跨源收录）→ ④规范化摘要互为包含（覆盖标题与 URL 全异的同文转录）。
**注意**：不要用「同域名+同一天」判重——同一信源当天会发布多篇不同文章，早期版本该规则曾把 Verge/36氪 当天第 2 篇起全部误杀（每天最多存活 1 条），2026-08-29 已修复。

### 7.10 news.js 放行无 Origin 请求
部分环境同源请求不携带 Origin header，严格白名单会导致误拦。
**解决**：`origin === ''` 时也放行（只读公开数据无敏感信息），但仅对白名单内源回显 ACAO 头。

### 7.11 RSS 聚合器 API-First 架构（2026-09-02）
RSS 聚合页面从纯静态构建升级为 API-First 实时架构：
- 页面加载时立即调用 `https://starhub-refresh.vercel.app/api/rss` 获取实时数据
- 失败时回退到静态构建数据（显示"· 静态构建数据"）
- **CORS 配置**：`api/rss.js` 添加 `Access-Control-Allow-Origin: *`，允许 GitHub Pages 跨域访问
- **字段映射**：API 返回缩写字段（`t`=title, `u`=url, `s`=summary, `d`=date），前端需转换
- **已读标记 CSS**：Python 字符串中 unicode 转义需双反斜杠（`\\5df2 \\8bfb`），否则被解释为八进制

### 7.12 GitHub Pages 与 Vercel 双域名部署
- 主站：`https://starhub-refresh.vercel.app`（Vercel，支持 Serverless API）
- 镜像：`https://kwei168.github.io/starhub/`（GitHub Pages，静态托管）
- **关键**：GitHub Pages 无法执行 Serverless 函数，API 调用必须使用 Vercel 完整 URL
- **缓存差异**：Vercel CDN 缓存约 5 分钟，GitHub Pages 缓存 10 分钟（`max-age=600`）

### 7.13 翻译缓存架构（2026-09-02）
**问题**：API 层（Node.js）无法调用 Python 翻译服务，导致实时数据无翻译

**解决方案**：构建时翻译 + 缓存共享
```
构建时（Python）：抓取 RSS → 翻译 → 保存 translations.json（MD5 hash → 中文）
                                    ↓
API 实时（Node.js）：抓取 RSS → 查 translations.json → 返回（有翻译用翻译，无翻译用原文）
```

**关键文件**：
- `translations.json`：翻译缓存，14000+ 条，MD5 hash 作为 key
- `api/rss.js`：加载翻译缓存，应用翻译到返回数据
- `build_rss_aggregator.py`：构建时翻译标题和摘要，保存缓存

**优势**：
- 翻译只在构建时进行（利用 Python 四端点降级链）
- API 实时性不受影响（查缓存很快）
- 下次构建时，已翻译的内容不重复翻译（缓存命中）

### 7.14 RSS 刷新机制演进（2026-09-04）

**问题背景**：
- Vercel Serverless 是无状态的，服务端维护的增量更新状态（`sourceLastFetch` Map）在冷启动后丢失
- 153 个 RSS 源全量抓取耗时过长（理论最大 145 秒），前端超时设置过短会导致请求被 abort
- 静默失败设计让用户看不到任何反馈，不知道刷新是否成功

**第一次尝试（失败）**：
- 在服务端实现基于 `If-Modified-Since` 头的增量更新
- 维护 `sourceLastFetch` Map 记录每个源的最后抓取时间
- **失败原因**：Vercel Serverless 冷启动后 Map 为空，增量逻辑失效；且全量抓取仍需要超过 90 秒

**最终方案**：**前端增量更新 + 性能优化**

#### API 端优化（`api/rss.js`）
```javascript
// 性能参数调整
const FETCH_TIMEOUT = 5000;     // 从 8s 降低到 5s（加快失败速度）
const CONCURRENCY = 20;         // 从 10 提高到 20（翻倍并发数）
```
- 移除不可靠的服务端增量逻辑（`sourceLastFetch`、`_unchanged` 标记等）
- 保持简单可靠的全量抓取，但通过提高并发数加快速度
- 理论耗时：153 源 ÷ 20 并发 × 5s ≈ 38 秒（留有余量）

#### 前端增量更新（`rss-aggregator.html` / `build_rss_aggregator.py`）
```javascript
// localStorage 维护已读文章 URL 列表
var READ_ARTICLES_KEY = 'starhub_rss_read_urls';

function _getReadUrls() {
  var stored = localStorage.getItem(READ_ARTICLES_KEY);
  return stored ? JSON.parse(stored) : [];
}

function _saveReadUrls(urls) {
  var limited = urls.slice(-5000);  // 最多保留 5000 条
  localStorage.setItem(READ_ARTICLES_KEY, JSON.stringify(limited));
}

function _mergeLiveSources(liveData, silent) {
  var readUrls = _getReadUrls();
  var readSet = {};
  readUrls.forEach(function(url) { readSet[url] = true; });
  
  // ... 遍历 API 返回的文章 ...
  // 跳过已在 ART 数组或 localStorage 中的文章
  if(existingKeys[key]) return;
  if(readSet[url]) return;  // ← 真正的增量判断
  
  newUrls.push(url);
  // ... 添加到 ART 数组 ...
  
  // 保存新 URL 到 localStorage
  if(newUrls.length > 0) {
    _saveReadUrls(readUrls.concat(newUrls));
  }
}
```

**关键改进**：
1. **超时延长**：从 90 秒增加到 120 秒（适应 20 并发×5s 的理论值）
2. **明确的 toast 提示**：
   - 有新文章：`"已更新 N 篇新文章"`
   - 无新内容：`"已刷新，暂无新内容"`
   - 刷新失败：`"刷新失败：网络错误"`
3. **移除静默失败**：catch 块显示错误信息
4. **按钮状态管理**：在所有情况下（成功/失败/无新内容）都正确移除 loading 状态

**测试结果**（2026-09-04 实测）：
- ✅ API 请求从 `[pending]` 变为 HTTP 200 成功
- ✅ Toast 提示正常显示，用户能看到明确反馈
- ✅ 第二次刷新正确识别"暂无新内容"
- ✅ localStorage 正确维护已读 URL 列表

**经验教训**：
- **不要在无状态 Serverless 上依赖内存状态做增量** — 应该用持久化存储（Redis/KV）或前端状态
- **性能优化优先于架构复杂化** — 提高并发数比实现复杂的增量协议更简单有效
- **用户反馈必须可见** — 静默失败是最差的用户体验

---

## 八、技术栈总结

| 层 | 技术 |
|---|---|
| 构建脚本 | Python 3.11（纯标准库，无第三方依赖） |
| Serverless | Vercel Functions（Node.js，原生 fetch） |
| 托管 | Vercel（主）+ GitHub Pages（备） |
| CI/CD | GitHub Actions |
| 定时触发 | cron-job.org（主力）+ GitHub schedule（兜底） |
| 前端 | 原生 HTML/CSS/JS，无框架 |
| 数据源 | GitHub REST API v3、AIHOT API v1 + RSS、RSSHub 镜像、HN/Verge/TechCrunch/arXiv/Redis RSS |
| 翻译 | Google 翻译非官方端点 → MyMemory 降级 |
