# 2026-10-01 · AI 日报视觉统一与全页打磨 SPEC

状态：**待实施**（本文档只是计划，未改任何代码）
参考物：
- 洞察版块重排已做出可运行 demo：`_scratch/ai-daily-demo-unified.html`（亮/暗/移动端截图在 `_scratch/shots/`，自检通过）
- 全页审查证据：同目录 `orig_d_fold.png` / `orig_d_dark.png` / `orig_m_fold.png` / `orig_m_papers.png`
- 生成脚本：demo 由 `_scratch/make_insight_demo.py` 从线上版 HTML 解析重排生成，可当排版的第二参照

## 0. 一句话结论

页面骨架（报纸双细线系统、纸/墨/绿三色语言、`.item.top` 米色面板、明暗双主题映射）已经立住，**不要动**；
要做的全部是减法：把"每日深度洞察"版块从 SaaS 卡片语言翻译回报纸语言（Part A，已有 demo），
以及清理泄漏到阅读层的机器痕迹（Part B：机翻残尾、直译元信息、六色编号、语料标记、时间口径矛盾）。

## 1. 关键仓库事实（动手前必读）

1. **产物不入库**：根目录 `ai-daily.html`、`daily-insight-history.html` 是冻结快照，每场 CI 构建重新生成。
   一切改动落在生成端：`build_ai_daily.py`（页面骨架 + 六个分类版块）与 `build_daily_insight.py`（洞察注入）。
   `tests/site_nav_drift/test_artifact_drift.py`（A3）盯的是"生成页不许再回 git"，手改产物没有意义。
2. **洞察 CSS 是两处共用**：注入块样式（`build_daily_insight.py:5032` 附近的 `<style>`）与历史归档页样式（同文件 `:4684` 附近的 `<style>`）。
   Part A 必须两处同步，否则归档页和日报割裂。
3. **推送纪律**见 `CLAUDE.md`（Data API 四步、避开 update.yml 构建窗口、按路径 add）。本文档不涉及推送。
4. **守护测试现状**：
   - `tests/daily_insight/test_html_links.py:47` 用正则 `<div class="di-card">.*?(?=<div class="di-card">|<!-- daily-insight-end)` 切卡片，
     `:51` 断言每卡含 `class="di-link"`，`:73` 断言含 `class="di-cite"` → 新排版**保留这三个类名钩子**（见 §3.6）。
   - `tests/site_nav/*`、`tests/daily_insight/test_integration.py`：改模板后跑一遍即可发现连带断言。

## 2. 范围

**做**：A 洞察版块统一重排（日报注入块 + 历史归档页）；B 全页打磨（3×P0、6×P1、4×P2，见 §4）。
**不做**：报头/双细线/卡片底色等既有设计语言的重设计；任何后端数据管线重构；rss-aggregator/index 等其他页面。

## 3. Part A：每日深度洞察 → 报纸语言（已有 demo，按此落地）

### 3.1 割裂点诊断（为什么现在像两个产品）

原版块是圆角胶囊标签、绿框彩底链接块、悬空大号绿分数、虚线分隔——仪表盘语言；
页面其余部分靠规则线、留白、衬线标题表达层级。逐项翻译映射：

| 原元素 | 新元素 | 出处（页面既有语法） |
|---|---|---|
| 独立版块头 + 双线上边框 | `sec-head` 同构：绿 07 + 衬线"深度洞察" + 右侧"N 条 · M 篇深读" | `.sec-head`（01–06 同款） |
| 胶囊标签 新/垂直/消费级 + 裸分类码 | 一行眉线 `新 · 垂直 · AI 产品`（10.5px、字距 .08em、`--faint`） | `.item-src` |
| 悬空大号绿色分数 | 眉线右端 Georgia 斜体 `评分 0.3`（`--accent-ink`） | `.idx-n` 的衬线斜体语汇 |
| 绿框圆角链接块 `di-link` | 正文点线下划线链接（去边框/底色/圆角） | 原 `.di-cite` 的点线样式，升格为全版块统一链接语言 |
| 单列满宽 12 卡 | 有深读的卡 = `.di-feat` 通栏特稿行；无深读 = `.cols` 双栏 | `.front` 主次结构 + `.cols` |
| 深读左竖线块 | card-2 米色面板 + 内部眉线"深度解读 · ANALYSIS" | `.item.top` 面板 + `.front-kicker` 眉线 |
| `<b>事件还原</b><br>` 行内粗体 | `di-deep-sec`：小标题 11.5px 字距 + 12.5px 正文 | 新规格（对齐生成器已有 `di-deep-sec` 结构） |
| `di-quote` 斜体引文 | 衬线斜体 + accent 左细线（保留，微调字号/行高） | 报纸引文惯例 |
| 破茧栏虚线框 + 彩色下划线 | 上下双细线夹住、居中衬线栏名（两侧规则线）、双栏、摘要 5 行截断 | `mast-strip` / `mast-rule` |

### 3.2 DOM 契约（注入块，`_inject_into_ai_daily`，build_daily_insight.py:4944）

```html
<!-- daily-insight-start -->（注释锚点保留，test_html_links.py 依赖）
<style> …新 .di-* 样式… </style>
<section id="sec-7" class="sec di-sec">
  <div class="sec-head"><span class="sec-num" style="color:var(--accent)">07</span>
    <h2 class="sec-name">深度洞察</h2><span class="sec-cnt">N 条 · M 篇深读</span></div>
  <p class="di-theme">{theme}</p>
  <div class="di-feat">   <!-- 有 signal 深读的事件，通栏 -->
    <article class="di-card has-deep">…</article>
  </div>
  <div class="cols">      <!-- 无深读事件，双栏，直接复用页面 .cols（移动端自动 1 栏） -->
    <article class="di-card">…</article>
  </div>
  <aside class="di-bubble">
    <div class="di-bubble-head"><span class="di-bubble-head-t">破茧栏 · 信息增量</span></div>
    <div class="di-bubble-grid">…</div>
  </aside>
</section>
<!-- daily-insight-end -->
```

卡片内部两态：

- **简报卡**：`di-kicker`（状态 · 共鸣 · 中文分类 + 右侧 `di-score`）→ `di-label`（衬线 17px 粗体，链接到首条 key_link）→ `di-summary`（13px `--muted`）→ `di-foot`（`di-srcs`"信源 a · b" + `di-links` 点线链接）。
- **特稿卡**：同上前半 + `di-deep` 面板（card-2 底、1px `--line` 边框）：`di-deep-kicker`"深度解读 · ANALYSIS" → `di-deep-sec`×4（事件还原/影响分析/信源分歧/后续展望，按 signal 内原始顺序）→ `di-quote` → `di-deep-foot`（置信度 + `di-cites`）。

### 3.3 数据映射（不新增数据需求）

字段全部来自现有 `_write_insight_json`（:4513）产出的 clusters 结构：
`label / summary / score / resonance / status / category / key_links / sources / signal{深读各段, quote, confidence}`；bubble 用 `bubble_breaker{label, summary, reason, url}`。
分类中文映射（新增常量）：ai-models→AI 模型，ai-products→AI 产品，industry→行业，policy→政策，developer→工程实践，research→论文，consumer→消费；映射表缺失时回退原码。
语料标记（`[agihunt][aihot]`）在摘要渲染时**剥除**（并入 §4 B-5，同一处实现）。

### 3.4 CSS 规格（新 `<style>` 全量替换旧 `.di-*`，vars 全部复用现有）

```
.di-theme        衬线斜体 14.5px --muted
.di-kicker       flex baseline；10.5px --faint 字距 .08em
.di-score        右推 margin-left:auto；衬线斜体 12px --accent-ink
.di-label        衬线 17px/1.42 粗体；feat 态 20px；hover --accent-ink
.di-summary      13px --muted lh1.7
.di-links a, .di-cites a   11.5px --accent-ink，border-bottom:1px dotted --accent
.di-deep         card-2 底 + 1px --line；内衬 14/18px
.di-deep-sec strong  11.5px 字距 .1em --ink；p 12.5px --muted lh1.75
.di-quote        衬线斜体 14px --ink；border-left:2px --accent
.di-deep-foot    上细线，置信度 10.5px --faint + cites 右侧
.di-bubble       上下 3px double --line-strong；head 两侧 1px 规则线 + 衬线 15px 字距 .14em
.di-bubble-grid  双栏 34px gutter；card 摘要 -webkit-line-clamp:5
@media 760px     feat 标题 18px；links 取消右推；bubble 单栏
```

### 3.5 历史归档页同步

`_build_history_html`（:4582）内嵌的旧 `.di-*` 样式（:4684 起的 `<style>`）替换为 §3.4 同一套；
卡片 DOM 改成与注入块同构（生成器本就输出 `di-deep-sec` 结构，改动集中在容器与头部）。

### 3.6 守护测试兼容策略（故意为之，不是顺手改）

- 保留类名钩子：链接锚点继续带 `class="di-link"` / `class="di-cite"`（样式层去胶囊化，钩子不动）→ `test_html_links.py:51/73` 不用改。
- 卡片容器从 `<div class="di-card">` 换成 `<article class="di-card">` → **同步修改** `test_html_links.py:47` 的正则为 `<(?:div|article) class="di-card"`（一行，语义不变）。
- `sec-7` 新锚点加进日报页首索引（vii 深度洞察，罗马数字继续序列、绿色 `--accent`）——该改动在 `build_ai_daily.py` 的索引渲染处（:921 一带），若 site_nav 测试断言索引条目数需同步。

## 4. Part B：全页打磨清单（每条：现象 → 改法 → 落点）

### P0（信任/看懂）

| # | 现象 | 改法 | 落点 |
|---|---|---|---|
| B-1 | 机翻残尾：Verge/TechCrunch 描述以"……"结尾；36氪摘要在句中掐断 | `_truncate`（build_ai_daily.py:118）从"按字符硬切"改为"句末标点收口"：在 maxlen 内回退到最近的 。！？；切不出完整句才允许省略号。翻译后的中文同样走该函数，顺带清掉模板里既有的"……"尾 | `_truncate` + 各 fetch 项的 summary 赋值处（:169/:215/:256/:344/:382/:477） |
| B-2 | HN 元信息直译："▲ 1 points · by tim333"，1 分也挂分数 | 改为"%s 分 · 用户 %s"；分数 ≤3 时只显示"用户 xxx"（低分无信息量）。注意 :752 注明 HN 摘要"是元信息不翻译"，所以在生成源头改，不进翻译管线 | build_ai_daily.py:318 |
| B-3 | 时间口径矛盾：报头"每早八时 · DAILY" vs "自动生成于 … 00:21" | mast-rule 口号改为"AI 资讯 · DAILY"（或与实际排程一致的可信表述）；`自动生成于` 改为"数据截至" | 模板 :1154、window_human :1250 |

### P1（质感/一致性）

| # | 现象 | 改法 | 落点 |
|---|---|---|---|
| B-4 | 六色编号系统（索引 i–vi 与 sec-num 01–06 蓝紫青青绿琥珀红）与全页双色语言打架 | 分区色 dict（:50 起的 hex 表）收敛：编号与索引罗马数字统一 `--ink`，或全部 `--accent` 绿（推荐后者：保住"分区可扫读"，色彩语义并入绿色系统） | build_ai_daily.py:50 色表、:921、:939 |
| B-5 | 语料标记暴露：`[agihunt][aihot][rss]` 散在摘要里 | 渲染层剥除/转上标（与 §3.3 同一处实现，日报正文六个版块的摘要若有同类标记一并处理） | build_daily_insight.py 注入渲染 + build_ai_daily.py 摘要出口 |
| B-6 | arXiv 标题 "[cs.CV] …" 分类前缀占标题位 | 前缀抽到信源行："arXiv · cs.CV"。翻译函数现保留前缀（:752 注释），拆分动作放在渲染前 | build_ai_daily.py:752-755、`_item_html` :894 |
| B-7 | 双栏底边参差：36氪长摘要与一句话摘要混排 | `.item-desc` 加 `-webkit-line-clamp:3`（移动端 4）；与 B-1 句末截断配合后视觉自然收齐 | build_ai_daily.py CSS :1111 |
| B-8 | 10.5px 信源行过小；`--faint` 对比 ~3.4:1 低于小字线；px 定字号无法缩放 | 信源行/元信息行最小 11px 并用 `--muted`；`html` 根字号改 rem 可作为后续独立小步（本阶段只做字号+颜色两个常量级改动） | 两个脚本的 CSS 块 |
| B-9 | 页首 mast-strip 与页脚 status_line 重复列信源（页脚 8 个 ✓） | 页脚只留"共 N 条 · 建档时间 · 版权"；信源清单保留页首一处 | build_ai_daily.py:1247 一带、foot 模板 |

### P2（细节）

| # | 现象 | 改法 | 落点 |
|---|---|---|---|
| B-10 | 中西文混排空格不一致（"Google宣布" vs "OpenAI 发布"） | 构建时在 CJK/Latin 边界规范化插空格（标题与摘要出口统一过一遍；正则一处工具函数） | build_ai_daily.py 新工具函数 + 渲染出口 |
| B-11 | 11200px 长页无返回顶部；索引无滚动高亮 | 模板尾部加 ~10 行 scroll-spy + 返回顶部（现有主题按钮同款内联 JS 风格） | build_ai_daily.py 模板 |
| B-12 | 无前后日导航，复访动线断 | 链接 daily-insight-history.html 的对应日期锚点（该页已有 day 锚点）；"前一天/后一天"需要日期索引，数据源 `daily_insight_history.json` 里已有日期列表 | build_ai_daily.py 模板 + build_daily_insight.py 归档锚点核对 |
| B-13 | 引号实体混用（`&quot;` 与中文引号） | 生成端统一中文引号 | build_ai_daily.py 渲染出口 |

## 5. Tokens（把现有碎值归档成体系，随 B 项顺手落地）

- **Spacing**：`4 / 8 / 12 / 16 / 24 / 32 / 48`；现有 14→16、22→24、26→24、34→32、40→48。
- **Type**：`11 / 13 / 15 / 17 / 20 / 24 / 32 / 48`；摘要 13px、信源行 11px、洞察简报标题 17px、特稿标题 20px。
- **Color**：沿用现有 `--bg/--card/--card-2/--ink/--muted/--faint/--line/--line-strong/--accent/--accent-ink/--accent-weak` 及暗色映射；
  约定"**绿色只出现在：编号、kicker、引用链接、评分**"，其余一律墨/灰阶（B-4 是这条约定的执行）。
- **Radius/Shadow**：统一 3px（仅既有小徽标）；**不引入阴影**——无影是报纸风辨识度的一部分。

## 6. 实施顺序（四个 Phase，互相独立可分场推送）

1. **Phase 1 · 全页 Quick wins**（纯 build_ai_daily.py 模板/CSS，一小时内量级）：B-3、B-4、B-6、B-7、B-8、B-9、B-13。
2. **Phase 2 · 洞察重排落地**（build_daily_insight.py 两处模板 + test_html_links.py:47 一行）：按 §3 规格，以 `_scratch/ai-daily-demo-unified.html` 为像素基准；B-5 一并做。
3. **Phase 3 · 文本管线**：B-1、B-2（含 `_truncate` 重写与 fetch 出口清理）、B-10。
4. **Phase 4 · 导航增强（可选）**：B-11、B-12。

## 7. 验证清单

- 构建：本地跑 `python build_ai_daily.py` 与 `python build_daily_insight.py`（如需网络抓取，可用既有 mock/缓存路径；CI 全量构建 ~15 分钟）。
- 测试：`pytest tests/daily_insight tests/site_nav tests/site_nav_drift -q`；预期唯一需要同步的断言是 `test_html_links.py:47` 的容器标签正则。
- 视觉：构建产物开浏览器过四关——桌面 1440 亮/暗、移动 390 亮色；检查点：① 06→07 版块衔接与 01→02 观感一致；② 深读面板/简报双栏/破茧栏三态；③ 暗色下深读面板 card-2 与正文字色；④ 索引 vii 锚点跳转。
- 文本：抽查 Verge/TechCrunch/36氪/HN 各 2 条，确认句末收口、无"……"尾、HN 元信息中文且低分不显分。
- 回归红线：`<!-- daily-insight-start/end -->` 锚点仍在；`di-link`/`di-cite` 类名仍在；产物 html 不进 git（A3 测试保持绿）。

## 8. 风险与注意

- **两处样式漂移**：洞察注入块与历史页样式是拷贝关系，Phase 2 必须同场改，否则归档页变成第三个产品。
- **`_truncate` 是共用函数**：六个数据源都走它，句末收口改坏会同时影响全部版块——先加单测（给定中英文长句、无标点长串、刚好卡 maxlen 三类用例）再动。
- **翻译窗口**：B-1 的截断改动发生在翻译之后（现流程先截断再翻译），句末收口后送翻的文本变长，注意翻译量窗口判据（近期提交已钉住"窗口总量 ≤ 窗口+30"的测试）不被打破。
- **并发 auto-commit**：仓库有每日常规自动提交，Phase 间推送遵守 CLAUDE.md 四步与"无未完成 run"守门。
