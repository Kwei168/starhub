# 2026-09-15 GitHub 仓库型 RSS 源审计

> 触发：用户发现聚合页出现 `Recent Commits to openclaw:main`，要求扫描同类「GitHub 仓库源、无实际内容」的信源并给出清单。

## 一、扫描范围与方法

| 项 | 说明 |
|---|---|
| 源配置 | `rss_sources.json`，共 **1014** 个源 |
| 实际产出 | `rss-data-0.js` + `rss-data-1.js`，共 **509** 个源 / **9092** 条条目（两块 **互不重叠**，已验证：41 个源全部同名，link 交集 = 0） |
| 判定口径 | 内容长度 = `max(len(summary), len(summary_zh), len(full_content))`。**注意**：仅看 `summary` 会误判——大量源 `summary` 为空但 `full_content` 有正文 |
| 线上验证 | 直连 `curl` / 抓取各 feed 的 atom 原文，逐 entry 检查 `<content>` 实际文本 |

## 二、结论

全库 GitHub **仓库型** feed 共 **8** 个（`commits.atom` / `releases.atom`），其中 **4 个内容为空或接近为空**、1 个半噪声、3 个内容正常。

GitHub 仓库型源合计产出 171 条，占总条目 1.9%；但单看 AI 分类，仅 `recent_commits_to_openclaw_main_741` 一个就占 **10.8%**，在 AI 分类里排第 3 大源。

## 三、A 类：确认无实际内容（建议移除）— 4 个

### A1. `recent_commits_to_openclaw_main_741` — 严重，优先级最高

| 项 | 值 |
|---|---|
| 名称 | Recent Commits to openclaw:main |
| URL | `https://github.com/openclaw/openclaw/commits/main.atom` |
| 分类 / Tier | ai / T3 |
| 产出条目 | **160** 条（首屏 14 + 后台 146） |
| 内容实测 | **全部为空** |

线上原文（T0 实测，curl 下载 18314 字节）：

```xml
<title>Recent Commits to openclaw:main</title>
...
<entry>
  <title>improve: speed up UTC inbound history formatting (#148648)</title>
  <content>&lt;pre&gt;improve: speed up UTC inbound history formatting (#148648)&lt;/pre&gt;</content>
</entry>
```

- feed 一次只发 **20** 条；聚合器存了 **160** 条 → 说明它跨多次构建持续累积，是稳定的高频噪声注入器。
- `<content>` 就是 `<title>` 的 `<pre>` 包裹，**同一句话重复两遍**；无 `<summary>` 字段。
- 部分条目带 `Co-authored-by` 签名行，构成"看起来有内容"的假象。
- 页面表现：条目只有 commit 一行标题、摘要空白，点开是原始 git 提交正文。

### A2. `codex_rel_15` — OpenAI Codex Releases

| 项 | 值 |
|---|---|
| URL | `https://github.com/openai/codex/releases.atom` |
| 分类 / Tier | ai / T3 |
| 产出条目 | 4 条 |
| 内容实测 | **全部为空**（平均 32 字符） |

线上原文（T0 实测）：

```xml
<entry>
  <title>0.155.0-alpha.4</title>
  <content type="html"><p>Release 0.155.0-alpha.4</p></content>
  <author><name>github-actions[bot]</name></author>
</entry>
```

10 条 entry 全部是 `<p>Release <版本号></p>` —— 正文只是把标题抄了一遍。发版人是 `github-actions[bot]` / `celia-oai`，属 npm alpha 自动发包，无人工发布说明。

### A3. `mcp_servers_rel_19` — MCP Servers Releases

| 项 | 值 |
|---|---|
| URL | `https://github.com/modelcontextprotocol/servers/releases.atom` |
| 分类 / Tier | ai / T3 |
| 产出条目 | **0** 条（本次全量构建无产出） |
| 内容实测 | 有内容但零信息价值 |

线上原文（T0 实测）——内容形态是纯 bot 生成的包版本 bump 清单：

```xml
<title>Release 2026.8.31</title>
<content><h1>Release : v2026.8.31</h1><h2>Updated packages</h2>
<ul><li>@modelcontextprotocol/server-filesystem@2026.8.31</li>
    <li>@modelcontextprotocol/server-memory@2026.8.31</li>...</ul></content>
```

10 条 entry 中 3 条甚至只写 `<p>Release 2026.6.16</p>`。零新增发布间隔约 2 周至 2 个月。

### A4. `mcp_spec_rel_18` — MCP Specification Releases

| 项 | 值 |
|---|---|
| URL | `https://github.com/modelcontextprotocol/specification/releases.atom` |
| 分类 / Tier | ai / T3 |
| 产出条目 | **0** 条 |
| 内容实测 | 稀疏，且 **URL 已失效指向旧仓库名** |

线上实测发现该仓库已改名：feed 的 `<id>` 与 `rel="self"` 现在指向
`https://github.com/modelcontextprotocol/modelcontextprotocol/releases`，
即 `specification` → `modelcontextprotocol`。当前靠 GitHub 301 重定向兜底。

内容本身是规格版本公告（`2026-07-28` / `2026-07-28 RC` / `2025-11-25` …），
最新一条 `<updated>` = **2026-07-28**，距今约 7 周无更新。属"真实但近乎不更新"，产出为 0 是合理结果。

## 四、B 类：半噪声（建议降权或改造）— 1 个

### `gemini_cli_rel_17` — Gemini CLI Releases

| 项 | 值 |
|---|---|
| URL | `https://github.com/google-gemini/gemini-cli/releases.atom` |
| 分类 / Tier | ai / T3 |
| 产出条目 | 3 条（平均 502 字符） |
| 内容实测 | **6/10 空，4/10 有真实说明** |

线上逐条核查结果：

| entry | 内容性质 |
|---|---|
| `v0.61.0-nightly.20260914` / `.20260913` / `.20260911` / `.20260910` / `.20260908` / `.20260907` | **空** —— 正文只有 `<p><strong>Full Changelog</strong>: <a>compare 链接</a></p>` |
| `v0.61.0-nightly.20260912` / `.20260909` | 真实 —— 含 What's Changed + New Contributors 列表 |
| `v0.60.0-preview.0` | 真实 —— 详尽变更列表 |
| `v0.59.0` | 真实 —— 含安全修复条目 |

即 **每天一次的 nightly 自动发版占满 feed，其中 60% 只有 diff 链接**，稳定版/preview 才有实质内容。

## 五、C 类：内容正常（建议保留）— 3 个

| key | 名称 | URL | 产出 | 实测 |
|---|---|---|---|---|
| `claude_code_rel_16` | Claude Code Releases | `github.com/anthropics/claude-code/releases.atom` | 2 | **9/10 条为详尽 changelog**（单条最长 15999 字符，含 80+ 条变更），仅 `v2.1.263` 为一句占位 |
| `release_notes_from_openclaw_743` | Release notes from openclaw | `github.com/openclaw/openclaw/releases.atom` | 1 | 真实发布说明，`openclaw 2026.9.4` 单条 15608 字符（含 contributor 列表） |
| `release_notes_from_langchain_742` | Release notes from langchain | `github.com/langchain-ai/langchain/releases.atom` | 1 | 真实，但是 monorepo 包版本日志（`langchain-core==1.6.3` 之类），机器生成、信息密度低 |

> 注：`release_notes_from_*` 与 `recent_commits_to_*` 三个源的名字是**抓取时从 feed `<title>` 自动派生**的，不是人工命名——这是 OPML 导入留下的痕迹，也正是命名风格突兀的原因。

## 六、非仓库类 GitHub 相关源（正常，勿误删）— 5 个

| key | 名称 | URL | 说明 |
|---|---|---|---|
| `github_blog_70` | GitHub Blog | `github.blog/feed/` | 官方博客，均长 15309 字符 |
| `github_changelog_71` | GitHub Changelog | `github.blog/changelog/feed/` | 官方 changelog，本次 0 产出 |
| `github_copilot_72` | GitHub Copilot Changelog | `github.blog/changelog/label/copilot/feed/` | 2 条，均长 2916 字符 |
| `hellogithub_17` | HelloGitHub | `hellogithub.com/rss` | 社区站点（域名含 github.com 但非仓库 feed） |
| `yiran_s_blog_635` | Yiran's Blog | `zdyxry.github.io/atom.xml` | GitHub Pages 个人博客，本次 0 产出 |

## 七、附：全库"全空内容源"横向对比

用统一口径（所有条目内容均 < 30 字符）扫描全部 509 个有产出的源，命中仅 **5** 个：

| key | 分类 | 条目 | 平均内容长度 | URL | 性质 |
|---|---|---|---|---|---|
| `hacker_news_723` | dev | 67 | 8 | `news.ycombinator.com/rss` | HN 官方 RSS 无 body，summary 恒为 "Comments"，正常现象 |
| `cnn_intl_781` | news | 4 | 0 | `rss.cnn.com/rss/edition.rss` | 本次抓取的 4 条均无摘要，可能源端异常 |
| `卢昌海个人主页_712` | dev | 2 | 24 | `changhai.org/feed.xml` | 个人博客短摘要，正常 |
| `fengc_s_blog_747` | dev | 1 | 16 | `rssweball.top/feed/...xml` | 单条，样本不足 |
| `维基萌_652` | dev | 1 | 8 | `wikimoe.com/rss.php` | 单条，样本不足 |

**该表未命中 A 类 4 个源**——因为它们的 `<content>` 并非空字符串，而是"把标题抄一遍"或"包版本清单"。
这说明**单靠长度阈值筛不出这类噪声源**，必须人工看内容形态。这是本次扫描最重要的方法论结论。

## 八、建议动作

| 优先级 | 操作 | 对象 |
|---|---|---|
| P0 | 移除 | `recent_commits_to_openclaw_main_741`（160 条纯噪声） |
| P0 | 移除 | `codex_rel_15`（10 条全空） |
| P1 | 移除 | `mcp_servers_rel_19`（0 产出 + 纯 bot bump） |
| P1 | 移除或修正 URL | `mcp_spec_rel_18`（0 产出 + 仓库已改名，7 周未更新） |
| P2 | 改造后保留 | `gemini_cli_rel_17`——过滤 title 含 `nightly` 的条目，可保留 40% 有效内容 |
| P3 | 保留 | `claude_code_rel_16` / `release_notes_from_openclaw_743` / `release_notes_from_langchain_742` |

若只想发版动态，正确做法不是订阅 `releases.atom`，而是对少数关键仓库走带正文抓取的路线（如 GitHub Releases API 取 `body` 字段），或直接订阅对应项目的官方博客/changelog。

---

## 九、证据分级

| 结论 | 等级 | 说明 |
|---|---|---|
| openclaw commits feed 20 条 entry 的 XML 结构、content=重复标题 | **T0** | curl 下载 18314 字节本地文件，逐 entry 解析 |
| codex / claude-code / gemini-cli / mcp-spec / mcp-servers / openclaw / langchain 各 feed 的 entry 内容形态 | **T0** | 线上抓取 atom 原文逐条核查 |
| mcp-spec 仓库已改名（`specification` → `modelcontextprotocol`） | **T0** | 直接读 feed 的 `<id>` / `rel="self"` |
| 各源在聚合器中的产出条目数与内容长度 | **T1** | 本地解析 `rss-data-*.js`，可复现 |
| 1014 源总数、8 分类、Tier 分布 | **T1** | 本地解析 `rss_sources.json` |
| "commits feed 跨多次构建累积至 160 条" | **T2** | 由"feed 每次仅 20 条 vs 库内 160 条"推断，未读构建代码验证 |
| "`mcp_spec_rel_18` 产出 0 是因为 7 周未更新" | **T3** | 本人推断；未排除抓取失败等其他原因 |

复现脚本：`_gh_scan2.py`（输出 `_gh_scan2_out.txt`）、`_gh_scan.py`（输出 `_gh_scan_out.txt`）；
线上样本：`.deploy-tmp/_gh_verify/commits_openclaw.xml`。
