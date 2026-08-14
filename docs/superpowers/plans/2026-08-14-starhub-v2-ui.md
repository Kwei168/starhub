# StarHub v2 UI 改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 StarHub 页面重构为「左主右辅」双栏布局 + 青蓝渐变品牌视觉，全部功能保持不变。

**Architecture:** 所有改动集中在 `template.html`（CSS + DOM + 内联 JS）；数据层零改动。由于 `fetch_and_build.py` 的 `main()` 会先拉取 GitHub API（本地网络抖动且慢、失败即退出），本地开发用一个新增工具 `dev_render.py` 从现有 `index.html` 提取已注入的数据常量，重新渲染 `template.html` 生成 `index.html`，实现「改模板 → 秒级预览」的循环。项目无测试框架，验证方式 = 结构断言（python 单行命令）+ 浏览器人工检查（http://localhost:8923 已启动预览）。

**Tech Stack:** 纯 HTML/CSS/JS（零依赖、零构建），Python 标准库（dev 工具），GitHub Actions 每日构建流程不变。

**Spec:** `docs/superpowers/specs/2026-08-14-starhub-v2-ui-design.md`（已提交 d9cee33）

**关键事实（实施前必读）：**
- `template.html` 共 883 行：CSS 在 `<style>`（7-319 行），DOM 在 `<body>`（322-429 行），JS 在 `<script>`（430-880 行）。
- 占位符注入顺序（`fetch_and_build.py` 440-449 行）：`__DATA__/__CATS__/__LANGS__/__FAVS__/__UPDATED__/__TRENDING__/__FEED__`，对应 JS 常量 `DATA/CATS/LANG_COLORS/DEFAULT_FAVS/UPDATED/TRENDING/FEED`。
- 每个任务提交时同时提交 `template.html` 和渲染后的 `index.html`（index.html 是 Pages 入口，必须跟随模板更新）。
- 提交信息示例：`feat(ui): ...`（改动无独立测试文件，遵循项目「模板+生成」既有模式）。

---

### Task 1: 本地渲染工具 dev_render.py

**Files:**
- Create: `dev_render.py`（项目根目录，本地开发工具，不参与 Actions 构建）

- [ ] **Step 1: 创建 dev_render.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地开发工具：从现有 index.html 提取已注入的数据，重新渲染 template.html 生成 index.html。
仅用于本地预览模板改动；不参与 GitHub Actions 构建。"""
import json
import re

SRC = "index.html"
TPL = "template.html"

# (常量名, 后继常量名)：用后继常量名作截取边界，避免 JSON 内部分号误伤
PAIRS = [
    ("DATA", "CATS"),
    ("CATS", "LANG_COLORS"),
    ("LANG_COLORS", "DEFAULT_FAVS"),
    ("DEFAULT_FAVS", "UPDATED"),
    ("UPDATED", "TRENDING"),
    ("TRENDING", "FEED"),
    ("FEED", None),
]


def main():
    src = open(SRC, encoding="utf-8").read()
    tpl = open(TPL, encoding="utf-8").read()
    for name, nxt in PAIRS:
        pat = r"const %s = (.*?);\nconst %s" % (name, nxt) if nxt else r"const %s = (.*?);\n\S" % name
        m = re.search(pat, src, re.S)
        if not m:
            raise SystemExit("index.html 中未找到常量 %s" % name)
        raw = m.group(1)
        if name != "UPDATED":
            json.loads(raw)  # 校验数据完整（UPDATED 是带引号的字符串，跳过）
        if "__%s__" % name not in tpl:
            raise SystemExit("template.html 中缺少占位符 __%s__" % name)
        tpl = tpl.replace("__%s__" % name, raw)
    open(SRC, "w", encoding="utf-8").write(tpl)
    print("渲染完成：index.html 已由 template.html 重新生成")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行验证**

Run: `python dev_render.py`
Expected: 输出「渲染完成：index.html 已由 template.html 重新生成」，无报错。

Run: `python -c "import re; h=open('index.html',encoding='utf-8').read(); assert '__DATA__' not in h and '__FEED__' not in h, '占位符残留'; print('无占位符残留')"`
Expected: `无占位符残留`

- [ ] **Step 3: 提交**

```bash
git add dev_render.py
git commit -m "chore: 新增本地渲染工具 dev_render.py（模板改动秒级预览）"
```

---

### Task 2: CSS 变量品牌化（品牌色 + 顶栏渐变）

**Files:**
- Modify: `template.html:8-25`（`:root` 变量块）与 `template.html:26-43`（`[data-theme="dark"]` 变量块）

- [ ] **Step 1: 替换 `:root` 变量块**

将 template.html 中第 8-25 行的 `:root{...}` 整体替换为：

```css
:root{
  --bg:#f6f8fa; --card:#ffffff; --border:#d0d7de; --border2:#eaeef2;
  --text:#1f2328; --muted:#59636e; --faint:#6e7781;
  --brand:#0ea5e9; --brand-strong:#0284c7; --brand-line:#38bdf8; --brand-weak:#0ea5e91f;
  --accent:var(--brand); --accent-line:var(--brand-line); --accent-weak:var(--brand-weak);
  --star:#e3a008; --star-bg:#fff8c5;
  --header-bg:linear-gradient(120deg,#082f49 0%,#0e7490 55%,#0891b2 100%);
  --hover:#f3f4f6; --hover-line:#afb8c1;
  --track:#d0d7de; --track-hover:#afb8c1;
  --mark:#fff3bf;
  --logo:#ffffff; --logo-sub:rgba(255,255,255,.72);
  --on-strong:#ffffff;
  --on-brand:#ffffff;
  --toast-bg:#1f2328; --toast-text:#ffffff;
  --faved-border:#e3b341; --faved-bg:linear-gradient(180deg,#fffdf2,#ffffff);
  --t-rising:#0ea5e9; --t-total:#2563eb; --t-new:#10b981;
  --gold:#e3a008; --silver:#8b949e; --bronze:#c96f3b;
  --upd-color:#1a7f37; --upd-bg:#dafbe1;
  --radius:12px; --shadow:0 1px 2px rgba(31,35,40,.06),0 1px 0 rgba(31,35,40,.03);
  --shadow-card:0 1px 2px rgba(31,35,40,.06),0 1px 0 rgba(31,35,40,.03);
  --shadow-lift:0 6px 20px rgba(8,47,73,.14),0 1px 0 rgba(31,35,40,.05);
}
```

- [ ] **Step 2: 替换 `[data-theme="dark"]` 变量块**

将第 26-43 行整体替换为：

```css
[data-theme="dark"]{
  --bg:#0d1117; --card:#161b22; --border:#30363d; --border2:#21262d;
  --text:#e6edf3; --muted:#9198a1; --faint:#8b949e;
  --brand:#38bdf8; --brand-strong:#0ea5e9; --brand-line:#7dd3fc; --brand-weak:#38bdf81f;
  --accent:var(--brand); --accent-line:var(--brand-line); --accent-weak:var(--brand-weak);
  --star:#e3b341; --star-bg:#3b2f00;
  --header-bg:linear-gradient(120deg,#020617 0%,#082f49 55%,#075985 100%);
  --hover:#21262d; --hover-line:#3d444d;
  --track:#3d444d; --track-hover:#525860;
  --mark:#4a3a00;
  --logo:#ffffff; --logo-sub:rgba(255,255,255,.72);
  --on-strong:#1f2328;
  --on-brand:#082f49;
  --toast-bg:#e6edf3; --toast-text:#0d1117;
  --faved-border:#9e6a03; --faved-bg:linear-gradient(180deg,#2a2308,#161b22);
  --t-rising:#38bdf8; --t-total:#60a5fa; --t-new:#34d399;
  --gold:#e3b341; --silver:#9198a1; --bronze:#f0883e;
  --upd-color:#3fb950; --upd-bg:#12261e;
  --shadow:0 1px 2px rgba(1,4,9,.5),0 1px 0 rgba(1,4,9,.35);
  --shadow-card:0 1px 2px rgba(1,4,9,.5),0 1px 0 rgba(1,4,9,.35);
  --shadow-lift:0 6px 24px rgba(0,0,0,.45),0 1px 0 rgba(1,4,9,.35);
}
```

- [ ] **Step 3: 渲染 + 结构断言**

Run: `python dev_render.py`
Expected: 渲染成功。

Run: `python -c "h=open('template.html',encoding='utf-8').read(); assert '--brand:#0ea5e9' in h and '--header-bg:linear-gradient(120deg,#082f49' in h; print('品牌变量已就位')"`
Expected: `品牌变量已就位`

- [ ] **Step 4: 浏览器检查**

打开 http://localhost:8923/index.html（亮色），确认：页面无视觉异常（此任务只改变量，链接/选中态应显示为青蓝 #0ea5e9）；切换暗色主题（header 月亮按钮），确认按钮/链接仍为可读的亮青蓝。若出现某处颜色异常属预期——后续任务逐个修复。

- [ ] **Step 5: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 品牌色系统——青蓝主色 + 深青蓝渐变顶栏变量（亮暗双主题）"
```

---

### Task 3: Header 品牌化（渐变顶栏 + 更新时间徽章 + 数据概览）

**Files:**
- Modify: `template.html`（`header` 结构 323-343 行、`.hd/.logo/.btn` 样式 57-76 行、JS `renderList` 与 init 区）

- [ ] **Step 1: 替换 header 相关 CSS**

将 57-76 行区块（`.icon` 定义 53-54 行保留不动）整体替换为：

```css
/* ---------- header ---------- */
header{
  position:sticky;top:0;z-index:50;background:var(--header-bg);
  backdrop-filter:saturate(160%) blur(10px);border-bottom:1px solid rgba(255,255,255,.12);
}
.hd{max-width:1440px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:12px}
.logo{display:flex;align-items:center;gap:10px;min-width:0}
.logo svg{width:30px;height:30px;fill:var(--logo);flex:none;filter:drop-shadow(0 1px 2px rgba(2,6,23,.4))}
.logo .t{display:flex;flex-direction:column;line-height:1.2;color:#fff}
.logo .t b{font-size:16px;font-weight:700;text-shadow:0 1px 2px rgba(2,6,23,.35)}
.logo .t span{font-size:12px;color:var(--logo-sub)}
.hd .sp{flex:1}
.hd .ov{display:flex;align-items:center;gap:10px;font-size:12px;color:rgba(255,255,255,.85)}
.hd .ov .badge{
  display:inline-flex;align-items:center;gap:5px;height:24px;padding:0 10px;border-radius:999px;
  background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);color:#fff;font-weight:600;
  white-space:nowrap;
}
.hd .ov .badge .icon{width:12px;height:12px;color:#86efac}
.hd .ov .sep{width:1px;height:16px;background:rgba(255,255,255,.25)}
.hd .ov b{color:#fff;font-weight:700}
.hd .acts{display:flex;gap:8px}
.btn{
  display:inline-flex;align-items:center;gap:6px;height:38px;padding:0 14px;
  border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--text);
  font-size:13px;font-weight:500;transition:background .15s,border-color .15s;
}
.btn:hover{background:var(--hover);border-color:var(--hover-line)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--on-strong)}
.btn.primary:hover{background:var(--accent-line)}
.hd .btn{
  background:rgba(255,255,255,.10);border-color:rgba(255,255,255,.25);color:#fff;
  backdrop-filter:blur(4px);
}
.hd .btn:hover{background:rgba(255,255,255,.22);border-color:rgba(255,255,255,.45)}
```

- [ ] **Step 2: 修改 header DOM**

将 323-343 行的 `<header>...</header>` 整体替换为：

```html
<header>
  <div class="hd">
    <div class="logo">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
      <div class="t"><b>GitHub Star 收藏台</b><span id="sub">Kwei168</span></div>
    </div>
    <div class="sp"></div>
    <div class="ov">
      <span class="badge" id="hdUpd" title="数据更新时间"><svg class="icon" viewBox="0 0 24 24"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg><span id="hdUpdTxt">更新于 …</span></span>
      <span class="sep"></span>
      <span><b id="hdTotal">0</b> 项目</span>
      <span><b id="hdCats">0</b> 分类</span>
    </div>
    <div class="acts">
      <button class="btn" id="btnView" title="切换列表/卡片视图" aria-label="切换视图"><svg class="icon" id="viewIcon" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></button>
      <button class="btn" id="btnTheme" title="切换明暗主题" aria-label="切换主题"><svg class="icon" id="themeIcon" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
      <button class="btn" id="btnExport" title="导出备份">
        <svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <span>导出</span>
      </button>
      <button class="btn" id="btnImport" title="导入恢复">
        <svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <span>导入</span>
      </button>
    </div>
  </div>
</header>
```

- [ ] **Step 3: 新增 renderHeader() 并接入 init**

在 `renderList` 函数（634 行 `function renderList(){` 之前）插入新函数：

```js
// ---- header 概览 ----
function renderHeader(){
  $('#hdUpdTxt').textContent = '更新于 ' + UPDATED;
  $('#hdTotal').textContent = DATA.length;
  $('#hdCats').textContent = CATS.length;
}
```

在 init 区（871-879 行）`applyTheme(getTheme());` 之后加一行 `renderHeader();`，并删除 `renderList` 末尾的 `$('#sub').textContent = 'Kwei168 · '+DATA.length+' 个项目 · 更新于 '+UPDATED;`（该行 673 行，副标题已由 header 概览承担；若保留则与 header 信息重复）。

- [ ] **Step 4: 移动端适配**

在 `@media (max-width:640px)` 块（299-318 行）内追加：

```css
.hd .ov .sep{display:none}
.hd .ov span:not(.badge){display:none}
```

- [ ] **Step 5: 渲染 + 浏览器检查**

Run: `python dev_render.py`
Expected: 渲染成功。

浏览器检查（亮/暗两主题）：顶栏为深青蓝渐变、白字；按钮为半透明白；右上显示「更新于 …」徽章与「114 项目 / 11 分类」；副标题区无重复信息；窗口缩至 390px 时徽章仍在、项目/分类数字隐藏。

- [ ] **Step 6: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 品牌化顶栏——渐变背景、更新时间徽章、数据概览"
```

---

### Task 4: 双栏布局骨架（主区 + sticky 侧栏 + 断点）

**Files:**
- Modify: `template.html`（`.wrap/.layout/.main/.trending/.feed` 样式与 `<body>` DOM 重排）

- [ ] **Step 1: 替换布局相关 CSS**

将 78-85 行区块替换为：

```css
/* ---------- layout ---------- */
.wrap{max-width:1440px;margin:0 auto;padding:18px 20px 40px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;align-items:start}
.side{position:sticky;top:76px;display:flex;flex-direction:column;gap:20px;min-width:0}
.main{
  width:100%;min-width:0;
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px;box-shadow:var(--shadow);
}
@media (max-width:1100px){
  .layout{grid-template-columns:minmax(0,1fr)}
  .side{position:static}
}
```

- [ ] **Step 2: 重排 body DOM**

将 345-425 行的 `.wrap.layout` 内部整体重排为（trending/feed 移入 `.side`，`.main` 提到最前）：

```html
<div class="wrap layout">
  <div class="main">
  <h2 class="main-title">我的收藏</h2>
  <div class="stats">
    <div class="stat"><div class="v" id="stTotal">0</div><div class="l">收藏项目总数</div></div>
    <div class="stat"><div class="v" id="stCats">0</div><div class="l">分类</div></div>
    <div class="stat"><div class="v" id="stLangs">0</div><div class="l">编程语言</div></div>
    <div class="stat"><div class="v" id="stFav">0</div><div class="l">我的收藏（置顶）</div></div>
  </div>

  <div class="langbar">
    <div class="cap"><b>语言分布</b><span id="lbCount"></span></div>
    <div class="bar" id="langBar"></div>
    <div class="legend" id="langLegend"></div>
  </div>

  <div class="toolbar">
    <div class="search">
      <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input id="q" type="search" placeholder="模糊搜索：项目名 / 描述 / 语言 / 分类 / 标签…" autocomplete="off">
      <button class="clear" id="btnClear" aria-label="清空">×</button>
    </div>
    <div class="sel">
      <select id="langSel"><option value="">全部语言</option></select>
    </div>
    <div class="sel">
      <select id="sortSel">
        <option value="stars-desc">⭐ 星标从高到低</option>
        <option value="stars-asc">⭐ 星标从低到高</option>
        <option value="recent">最近更新</option>
        <option value="name">名称 A-Z</option>
      </select>
    </div>
    <div class="starsel" id="starSel">
      <button data-v="all" class="on">全部星标</button>
      <button data-v="lt1k">&lt;1k</button>
      <button data-v="1k10k">1k-10k</button>
      <button data-v="10k100k">10k-100k</button>
      <button data-v="gt100k">&gt;100k</button>
    </div>
  </div>

  <nav class="cats" id="cats"></nav>

  <div id="pinnedWrap" style="display:none">
    <div class="sec-title">
      <svg class="icon filled" viewBox="0 0 24 24"><path d="M12 2l2.9 6.3 6.9.6-5.2 4.6 1.6 6.8L12 16.9 5.8 20.3l1.6-6.8L2.2 8.9l6.9-.6L12 2z"/></svg>
      我的收藏 · 置顶
      <span class="n" style="color:var(--muted);font-weight:400" id="pinnedCount"></span>
    </div>
    <div class="pinned" id="pinned"></div>
  </div>

  <div class="sec-title" id="listTitle" style="margin-top:20px">全部项目 <span class="n" style="color:var(--muted);font-weight:400" id="listCount"></span></div>
  <main class="grid" id="grid"></main>

  <div class="empty" id="empty">
    <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <b>没有找到匹配的项目</b>
    <span id="emptyHint">试试换一个关键词</span>
    <button class="btn" id="btnResetAll" style="margin-top:16px;display:none">清除所有筛选</button>
  </div>
  </div><!-- /main -->

  <aside class="side">
    <div class="trending">
      <h2>每日 AI 排行榜</h2>
      <div class="trend-sub" id="trendUpdated"></div>
      <div class="trend-tabs" id="trendTabs">
        <button class="trend-tab on" data-tab="rising">涨星榜</button>
        <button class="trend-tab" data-tab="total">总星标榜</button>
        <button class="trend-tab" data-tab="new">新秀榜</button>
      </div>
      <div class="trend-list" id="trendList"></div>
      <button class="trend-more" id="btnTrendMore">查看完整 Top20 →</button>
    </div>
    <section class="feed" id="feedWrap">
      <h2>今日关注动态</h2>
      <div class="feed-sub" id="feedUpdated"></div>
      <div class="feed-list" id="feedList"></div>
    </section>
  </aside>
</div>
```

注：本步已将「星标分段按钮」并入第一个 toolbar（原第二个 `.toolbar` 删除，Task 5 再调整细节样式）。

- [ ] **Step 3: 侧栏内样式适配**

在 `/* ---------- trending ---------- */` 区块（221 行起）的 `.trending{...}` 规则后追加：

```css
.side .trending,.side .feed{width:100%}
.side .trend-list{grid-template-columns:1fr}
.trend-more{
  width:100%;height:34px;margin-top:10px;border:1px dashed var(--border);border-radius:8px;
  background:transparent;color:var(--accent);font-size:12px;font-weight:600;transition:all .15s;
}
.trend-more:hover{border-color:var(--accent-line);background:var(--accent-weak)}
```

删除原 `@media (max-width:1100px){ .trend-list{grid-template-columns:repeat(2,1fr)} }`（292-294 行）——双栏断点已接管（<1100px 时 `.side` 变为全宽静态，该规则改为在 640px 媒体查询内用单列）。

在 `@media (max-width:640px)` 块追加：`.trend-list{grid-template-columns:1fr}`（640px 下全宽单列，覆盖 `.side .trend-list` 之外的场景）。

- [ ] **Step 4: 渲染 + 浏览器检查**

Run: `python dev_render.py` → 渲染成功。

浏览器检查：
- 1440px：左侧收藏主区 + 右侧 340px sticky 侧栏（排行榜在上、动态在下）；滚动时侧栏跟随，主区内容可完整浏览；
- 1024px：单列堆叠，顺序为 收藏 → 排行榜 → 动态；
- 390px：单列正常。
- 排行榜侧栏内为单列条目（原 3 列网格已收窄）。

- [ ] **Step 5: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 双栏布局——收藏主区 + sticky 侧栏（排行榜/动态），<1100px 单列降级"
```

---

### Task 5: 主区重构（统计卡图标 + 语言分布折叠 + 工具栏整合）

**Files:**
- Modify: `template.html`（`.stat/.langbar/.toolbar/.starsel/.search` 样式、主区 DOM、JS 折叠逻辑）

- [ ] **Step 1: 替换统计卡与语言分布 CSS**

将 86-105 行区块（`.stats` 到 `.legend .dot`）替换为：

```css
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat{
  display:flex;flex-direction:column;gap:4px;background:var(--card);
  border:1px solid var(--border2);border-radius:var(--radius);padding:12px 14px;
}
.stat .ic{
  width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
  background:var(--accent-weak);color:var(--accent);margin-bottom:6px;
}
.stat .ic .icon{width:16px;height:16px}
.stat .v{font-size:26px;font-weight:700;letter-spacing:-.5px;line-height:1.1}
.stat .v small{font-size:13px;font-weight:500;color:var(--muted)}
.stat .l{font-size:12px;color:var(--muted);margin-top:2px}
.langbar{
  background:var(--card);border:1px solid var(--border2);border-radius:var(--radius);
  padding:12px 14px;margin-bottom:14px;
}
.langbar .cap{
  display:flex;align-items:center;gap:8px;width:100%;border:0;background:none;padding:0;
  font-family:inherit;color:inherit;cursor:pointer;text-align:left;
}
.langbar .cap b{font-size:13px;flex:none}
.langbar .cap span{font-size:12px;color:var(--muted);flex:1}
.langbar .cap .chev{width:16px;height:16px;color:var(--faint);transition:transform .2s}
.langbar .cap[aria-expanded="false"] .chev{transform:rotate(-90deg)}
.bar{display:flex;height:10px;border-radius:6px;overflow:hidden;background:var(--border2);margin-top:10px}
.bar i{height:100%}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px}
.legend .li{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.legend .dot{width:9px;height:9px;border-radius:50%}
```

- [ ] **Step 2: 替换统计卡 DOM（带图标）**

将 363-368 行的 `.stats` 块替换为：

```html
<div class="stats">
  <div class="stat"><div class="ic"><svg class="icon" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div class="v" id="stTotal">0</div><div class="l">收藏项目总数</div></div>
  <div class="stat"><div class="ic"><svg class="icon" viewBox="0 0 24 24"><path d="M3 6l9-4 9 4"/><path d="M3 6v14l9 4 9-4V6"/><path d="M3 6l9 4 9-4"/><path d="M12 10v14"/></svg></div><div class="v" id="stCats">0</div><div class="l">分类</div></div>
  <div class="stat"><div class="ic"><svg class="icon" viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg></div><div class="v" id="stLangs">0</div><div class="l">编程语言</div></div>
  <div class="stat"><div class="ic"><svg class="icon" viewBox="0 0 24 24"><path d="M12 2l2.9 6.3 6.9.6-5.2 4.6 1.6 6.8L12 16.9 5.8 20.3l1.6-6.8L2.2 8.9l6.9-.6L12 2z"/></svg></div><div class="v" id="stFav">0</div><div class="l">我的收藏（置顶）</div></div>
</div>
```

- [ ] **Step 3: 语言分布改为可折叠面板**

将 370-374 行 `.langbar` DOM 替换为：

```html
<div class="langbar">
  <button class="cap" id="langToggle" aria-expanded="true">
    <b>语言分布</b><span id="lbCount"></span>
    <svg class="icon chev" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
  </button>
  <div id="langBody">
    <div class="bar" id="langBar"></div>
    <div class="legend" id="langLegend"></div>
  </div>
</div>
```

在 `bindEvents()` 函数内（`$('#q').addEventListener` 之前）插入折叠事件：

```js
$('#langToggle').addEventListener('click', () => {
  const open = $('#langToggle').getAttribute('aria-expanded') === 'true';
  $('#langToggle').setAttribute('aria-expanded', String(!open));
  $('#langBody').hidden = open;
});
```

- [ ] **Step 4: 工具栏整合 CSS**

将 108-131 行区块（`.toolbar` 到 `.starsel button.on`）替换为：

```css
/* ---------- toolbar ---------- */
.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.search{
  flex:1 1 260px;display:flex;align-items:center;gap:8px;height:40px;
  background:var(--card);border:1px solid var(--border);border-radius:10px;padding:0 12px;
  box-shadow:var(--shadow);
}
.search:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-weak)}
.search .icon{color:var(--faint);width:18px;height:18px}
.search input{flex:1;border:0;outline:0;font-size:14px;background:transparent;color:var(--text);min-width:0}
.search input::placeholder{color:var(--faint)}
.search .clear{color:var(--faint);font-size:18px;padding:0 2px;border:0;background:none;display:none}
.sel{position:relative;flex:none}
.sel select{
  height:40px;min-width:110px;padding:0 30px 0 12px;font-size:13px;appearance:none;
  border:1px solid var(--border);border-radius:10px;background:var(--card) url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%239198a1' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>") no-repeat right 10px center;
  color:var(--text);cursor:pointer;box-shadow:var(--shadow);
}
.starsel{display:flex;height:40px;background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;box-shadow:var(--shadow);flex:none}
.starsel button{
  height:100%;padding:0 11px;border:0;background:transparent;font-size:12px;color:var(--muted);
  border-right:1px solid var(--border2);white-space:nowrap;
}
.starsel button:last-child{border-right:0}
.starsel button.on{background:var(--accent);color:var(--on-strong)}
```

- [ ] **Step 5: 删除旧 DOM 结构**

删除原 394-402 行第二个 `<div class="toolbar" style="margin-bottom:6px">…</div>`（星标分段按钮已并入第一个 toolbar，Task 4 Step 2 的 DOM 已包含）。

- [ ] **Step 6: 渲染 + 浏览器检查**

Run: `python dev_render.py` → 渲染成功。

浏览器检查：
- 统计卡带青蓝图标；「语言分布」标题行点击可折叠/展开（箭头旋转），默认展开；
- 工具栏一行排布：搜索框 + 2 下拉 + 5 星标按钮；390px 时换行、搜索框占满；
- 全部筛选交互正常（语言/排序/星标切换、分类 tab、搜索清空）。

- [ ] **Step 7: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 主区重构——统计卡图标化、语言分布折叠、工具栏单行整合"
```

---

### Task 6: 侧栏排行榜 Top10 紧凑化 + 关注动态紧凑样式

**Files:**
- Modify: `template.html`（`.trend-item` 紧凑样式、JS `renderTrending` 改为 Top10 精简渲染、`buildTrendItem` 重构）

- [ ] **Step 1: 替换排行榜条目样式**

将 238-258 行（`.trend-list` 到 `.trend-item .stars`）替换为：

```css
.side .trend-list{display:flex;flex-direction:column;gap:6px}
.trend-item{display:flex;align-items:center;gap:8px;padding:7px 8px;border:1px solid var(--border2);border-radius:8px;transition:border-color .15s}
.trend-item:hover{border-color:var(--hover-line)}
.trend-item .rank{flex:none;width:20px;height:20px;border-radius:6px;background:var(--hover);color:var(--muted);font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
.trend-item:nth-child(1) .rank{background:var(--gold);color:#fff}
.trend-item:nth-child(2) .rank{background:var(--silver);color:#fff}
.trend-item:nth-child(3) .rank{background:var(--bronze);color:#fff}
.trend-item .ti{flex:1;min-width:0}
.trend-item .tn{font-size:12px;font-weight:600;color:var(--accent);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.trend-item .tn:hover{text-decoration:underline}
.trend-item .sub{display:flex;align-items:center;gap:5px;margin-top:2px;min-width:0}
.trend-item .lg{display:inline-flex;align-items:center;gap:5px;font-size:10px;color:var(--muted);flex:none}
.trend-item .lg .c{width:8px;height:8px;border-radius:50%;flex:none}
.trend-item .reason{font-size:10px;color:var(--muted);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.trending[data-tab="rising"] .reason{color:var(--t-rising)}
.trending[data-tab="total"] .reason{color:var(--t-total)}
.trending[data-tab="new"] .reason{color:var(--t-new)}
.trend-item .tm{flex:none;display:flex;flex-direction:column;align-items:flex-end;gap:1px;font-size:10px}
.trend-item .delta{color:var(--t-rising);font-weight:700;font-size:12px}
.trend-item .delta.neg{color:var(--muted)}
.trend-item .stars{color:var(--muted);display:inline-flex;align-items:center;gap:3px}
/* 浮层内完整条目（含描述） */
.trend-item.full{padding:10px;align-items:flex-start}
.trend-item.full .tn{font-size:13px}
.trend-item.full .td{font-size:11px;color:var(--muted);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.trend-item.full .reason{margin-top:4px;display:block;white-space:normal;font-size:11px}
```

- [ ] **Step 2: 重构 JS 渲染（Top10 精简 + full 模式）**

将 677-713 行 `renderTrending` 函数整体替换为：

```js
// ---- 每日 AI 排行榜 ----
function buildTrendItem(p, i, full){
  const row = document.createElement('div');
  row.className = 'trend-item' + (full ? ' full' : '');
  const hasDelta = p.delta !== null && p.delta !== undefined;
  const deltaHtml = state.trendTab === 'rising'
    ? (hasDelta
        ? '<span class="delta' + (p.delta < 0 ? ' neg':'') + '">' + (p.delta > 0 ? '+':'') + p.delta + '</span>'
        : '<span class="delta" style="color:var(--faint)">新</span>')
    : '';
  row.innerHTML =
    '<span class="rank">' + (i+1) + '</span>' +
    '<div class="ti">' +
      '<a class="tn" href="' + escHtml(p.html_url) + '" target="_blank" rel="noopener">' + escHtml(p.owner) + '/' + escHtml(p.name) + '</a>' +
      '<div class="sub">' +
        (p.language ? '<span class="lg"><span class="c" style="background:' + (LANG_COLORS[p.language] || '#8b949e') + '"></span>' + escHtml(p.language) + '</span>' : '') +
        '<span class="reason">' + escHtml(p.reason || '') + '</span>' +
      '</div>' +
      (full ? '<span class="td">' + escHtml(p.desc || '暂无简介') + '</span>' : '') +
    '</div>' +
    '<div class="tm">' + deltaHtml + '<span class="stars">★ ' + fmtStars(p.stars) + '</span>' + '</div>';
  return row;
}

function renderTrending(){
  const list = $('#trendList');
  const items = (TRENDING && TRENDING[state.trendTab]) || [];
  const box = $('.trending'); if(box) box.setAttribute('data-tab', state.trendTab);
  $('#trendUpdated').textContent = '更新于 ' + UPDATED;
  list.innerHTML = '';
  if(!items.length){
    const msg = state.trendTab === 'rising'
      ? '首次运行正在建立基线，明天起显示每日涨星变化'
      : '暂无数据';
    list.innerHTML = '<div style="color:var(--muted);font-size:12px;text-align:center;padding:20px 0">'+msg+'</div>';
    $('#btnTrendMore').style.display = 'none';
    return;
  }
  $('#btnTrendMore').style.display = '';
  items.slice(0, 10).forEach((p, i) => list.appendChild(buildTrendItem(p, i, false)));
}
```

- [ ] **Step 3: 关注动态紧凑样式**

将 266-275 行 `.feed-list`/`.feed-item` 相关规则替换为：

```css
.feed .feed-sub{font-size:11px;color:var(--faint);margin-bottom:10px}
.feed-list{display:flex;flex-direction:column}
.feed-item{display:flex;align-items:center;gap:7px;padding:7px 2px;border-bottom:1px solid var(--border2);font-size:12px}
.feed-item:last-child{border-bottom:0}
.feed-item .fd{flex:none;width:8px;height:8px;border-radius:50%}
.feed-item .fa{font-weight:600;color:var(--text);white-space:nowrap}
.feed-item .fv{color:var(--muted);flex:none}
.feed-item .ft{color:var(--accent);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46%;min-width:0}
.feed-item .ft:hover{text-decoration:underline}
.feed-item .tm{margin-left:auto;color:var(--faint);font-size:11px;flex:none}
```

- [ ] **Step 4: 渲染 + 浏览器检查**

Run: `python dev_render.py` → 渲染成功。

浏览器检查：
- 侧栏排行榜每条为紧凑单行（排名徽章 + 名称 + 语言圆点 + 理由 + 星星），无描述、无红色双重「新」标；共 10 条；底部「查看完整 Top20 →」按钮显示；
- 切三个 tab 均正常，理由颜色跟随 tab 主题色；
- 关注动态条目更紧凑，时间右对齐。

- [ ] **Step 5: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 侧栏排行榜 Top10 紧凑化（四要素）+ 关注动态紧凑样式"
```

---

### Task 7: 完整榜浮层（Top20 全屏面板）

**Files:**
- Modify: `template.html`（模态层 CSS、`.modal` DOM、JS `renderTrendingFull/open/close`、tab 联动、Esc 关闭）

- [ ] **Step 1: 添加模态层 CSS**

在 `/* ---------- toast ---------- */` 区块（283-289 行）之前插入：

```css
/* ---------- modal 完整榜浮层 ---------- */
.modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;padding:20px}
.modal[hidden]{display:none}
.modal-mask{position:absolute;inset:0;background:rgba(2,6,23,.55);backdrop-filter:blur(4px);opacity:0;transition:opacity .3s}
.modal.open .modal-mask{opacity:1}
.modal-panel{
  position:relative;width:min(880px,100%);max-height:82vh;overflow:auto;
  background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px 20px;
  box-shadow:0 24px 64px rgba(2,6,23,.4);opacity:0;transform:translateY(16px);
  transition:opacity .3s,transform .3s;
}
.modal.open .modal-panel{opacity:1;transform:none}
.modal-hd{display:flex;align-items:center;gap:10px;margin-bottom:2px}
.modal-hd h2{display:flex;align-items:center;gap:8px;margin:0;font-size:15px;font-weight:700}
.modal-hd .modal-sub{font-size:11px;color:var(--faint);flex:1}
.modal-x{
  width:30px;height:30px;border:0;border-radius:8px;background:var(--hover);color:var(--muted);
  font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center;transition:all .15s;
}
.modal-x:hover{background:var(--border2);color:var(--text)}
.trend-list.full{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:4px}
@media (max-width:640px){
  .trend-list.full{grid-template-columns:1fr}
  .modal{padding:10px}
  .modal-panel{padding:14px;max-height:90vh}
}
```

- [ ] **Step 2: 添加浮层 DOM**

在 `<div class="toast" id="toast"></div>`（427 行）之前插入：

```html
<div class="modal" id="trendModal" hidden>
  <div class="modal-mask" data-close="modal"></div>
  <div class="modal-panel" role="dialog" aria-modal="true" aria-label="每日 AI 排行榜完整榜单">
    <div class="modal-hd">
      <h2>每日 AI 排行榜</h2>
      <span class="modal-sub" id="trendModalSub"></span>
      <button class="modal-x" data-close="modal" aria-label="关闭">×</button>
    </div>
    <div class="trend-tabs" id="trendTabsFull">
      <button class="trend-tab on" data-tab="rising">涨星榜</button>
      <button class="trend-tab" data-tab="total">总星标榜</button>
      <button class="trend-tab" data-tab="new">新秀榜</button>
    </div>
    <div class="trend-list full" id="trendListFull"></div>
  </div>
</div>
```

- [ ] **Step 3: 添加浮层 JS**

在 `renderTrending` 函数之后插入：

```js
function renderTrendingFull(){
  const list = $('#trendListFull');
  const items = (TRENDING && TRENDING[state.trendTab]) || [];
  list.innerHTML = '';
  items.forEach((p, i) => list.appendChild(buildTrendItem(p, i, true)));
  $('#trendModalSub').textContent = '更新于 ' + UPDATED + ' · 每榜 Top20';
  document.querySelectorAll('#trendTabsFull .trend-tab').forEach(x =>
    x.classList.toggle('on', x.dataset.tab === state.trendTab));
}
function openTrendModal(){
  const m = $('#trendModal');
  m.hidden = false;
  renderTrendingFull();
  requestAnimationFrame(() => requestAnimationFrame(() => m.classList.add('open')));
}
function closeTrendModal(){
  const m = $('#trendModal');
  m.classList.remove('open');
  setTimeout(() => { m.hidden = true; }, 300);
}
```

- [ ] **Step 4: 绑定事件（打开/关闭/tab 联动/Esc）**

在 `bindEvents()` 中追加（`$('#trendTabs').addEventListener` 附近）：

```js
$('#btnTrendMore').addEventListener('click', openTrendModal);
document.addEventListener('click', e => {
  const c = e.target.closest('[data-close]');
  if(c) closeTrendModal();
});
$('#trendTabsFull').addEventListener('click', e => {
  const b = e.target.closest('[data-tab]'); if(!b) return;
  switchTrendTab(b.dataset.tab);
});
```

将现有 `$('#trendTabs').addEventListener('click', ...)`（800-805 行）替换为调用共享函数：

```js
function switchTrendTab(tab){
  state.trendTab = tab;
  document.querySelectorAll('#trendTabs .trend-tab').forEach(x => x.classList.toggle('on', x.dataset.tab === tab));
  renderTrending();
  if(!$('#trendModal').hidden) renderTrendingFull();
}
$('#trendTabs').addEventListener('click', e => {
  const b = e.target.closest('[data-tab]'); if(!b) return;
  switchTrendTab(b.dataset.tab);
});
```

在现有 `document.addEventListener('keydown', ...)` 处理器（806-815 行）内追加（`if(e.key === 'Escape' ...)` 分支之后）：

```js
if(e.key === 'Escape' && !$('#trendModal').hidden){
  closeTrendModal();
}
```

- [ ] **Step 5: 渲染 + 浏览器检查**

Run: `python dev_render.py` → 渲染成功。

浏览器检查：
- 点击「查看完整 Top20 →」：浮层淡入上滑，显示三 tab + 完整条目（含描述，2 列网格）；
- 浮层内切 tab 与侧栏切 tab 双向联动；
- Esc、点遮罩、点 × 均能关闭（300ms 淡出后 hidden）；
- 390px 下浮层单列、可滚动。

- [ ] **Step 6: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 完整榜浮层——Top20 全屏面板、tab 联动、Esc/遮罩关闭"
```

---

### Task 8: 动效打磨（count-up + 卡片 hover + 空状态）

**Files:**
- Modify: `template.html`（`.card` hover 样式、JS count-up）

- [ ] **Step 1: 卡片 hover 与阴影升级**

将 158-163 行 `.card{...}` 与 `.card:hover{...}` 替换为：

```css
.card{
  position:relative;display:flex;flex-direction:column;gap:8px;background:var(--card);
  border:1px solid var(--border);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow-card);
  transition:border-color .15s,transform .12s,box-shadow .15s;
}
.card:hover{border-color:var(--accent-line);transform:translateY(-2px);box-shadow:var(--shadow-lift)}
```

同时将 `.row`（199-204 行）的 `border-radius:10px` 保持、hover 描边改为品牌线（现有 `border-color:var(--accent-line)` 已随变量生效，无需改动）。

- [ ] **Step 2: count-up 动效**

在 `renderHeader` 函数后插入：

```js
// ---- 数字滚动动效 ----
let counted = false;
function countUp(el, target, dur){
  dur = dur || 600;
  const start = performance.now();
  function tick(t){
    const p = Math.min((t - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * eased);
    if(p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
```

将 `renderList` 中 669-672 行的统计赋值替换为：

```js
if(!counted){
  counted = true;
  countUp($('#stTotal'), DATA.length);
  countUp($('#stCats'), CATS.length);
  countUp($('#stLangs'), langSorted.length);
  countUp($('#stFav'), favs.size);
} else {
  $('#stTotal').textContent = DATA.length;
  $('#stCats').textContent = CATS.length;
  $('#stLangs').textContent = langSorted.length;
  $('#stFav').textContent = favs.size;
}
```

- [ ] **Step 3: 渲染 + 浏览器检查**

Run: `python dev_render.py` → 渲染成功。

浏览器检查：
- 刷新页面：4 个统计数字从 0 滚动到目标值（600ms ease-out），仅首次；
- 筛选/切分类时数字直接更新（不再滚动）；主题切换不重复滚动；
- 卡片 hover 上浮 2px + 青蓝描边 + 阴影加深。

- [ ] **Step 4: 提交**

```bash
git add template.html index.html
git commit -m "feat(ui): 动效打磨——统计数字 count-up、卡片 hover 上浮阴影"
```

---

### Task 9: 全量回归验证 + 收尾提交

**Files:**
- Verify: `template.html`、`index.html`、`dev_render.py`

- [ ] **Step 1: 结构断言（占位符/关键类名）**

Run: `python -c "import re; h=open('index.html',encoding='utf-8').read(); t=open('template.html',encoding='utf-8').read(); assert '__DATA__' not in h and '__FEED__' not in h, 'index 占位符残留'; assert all(x in t for x in ['class=\"side\"','trendModal','langToggle','hdUpd','btnTrendMore','trend-list full']), '模板缺失关键结构'; print('结构断言通过')"`
Expected: `结构断言通过`

- [ ] **Step 2: 功能回归（浏览器逐项）**

在 http://localhost:8923/index.html 逐项检查（亮/暗主题各一遍）：

- [ ] 搜索：输入关键词有高亮 `mark`；输入时自动清空其他筛选（历史 bug 防回归）；
- [ ] 语言下拉 / 排序下拉 / 星标分段按钮：各自筛选与排序生效；
- [ ] 分类 tab：点击切换、再点取消；`全部` 生效；
- [ ] 收藏：星标按钮收藏/取消，置顶区实时刷新；localStorage 持久化（刷新保留）；
- [ ] 导出/导入：导出下载 JSON；导入恢复后置顶更新；
- [ ] 视图切换：卡片 ↔ 列表，localStorage 记忆；
- [ ] 快捷键：`/` 聚焦搜索、`Esc` 清空搜索/关闭浮层；
- [ ] 语言分布折叠、排行榜三 tab、浮层打开/关闭/联动；
- [ ] 空状态：搜索无结果 → 显示「清除所有筛选」并可一键恢复；
- [ ] 移动端 390px：单列顺序 收藏→排行榜→动态，无横向滚动条。

- [ ] **Step 3: 提交最终产物**

```bash
git add template.html index.html dev_render.py docs/
git commit -m "feat(ui): StarHub v2 品牌化改版完成（双栏布局 + 青蓝渐变 + 完整榜浮层）"
```

- [ ] **Step 4: 部署说明**

告知用户：改动已就绪，可在 GitHub Actions 手动触发一次 workflow（或等每日 09:00 自动运行）让线上生效；`fetch_and_build.py` 未改动，自动更新链路不受影响。若本地已用 `dev_render.py` 生成的 `index.html` 直接推送，Pages 也会立即生效（Actions 下次运行时会用同一模板重新生成，结果一致）。

---

## Self-Review 记录

- **Spec 覆盖**：§3 双栏布局→Task 4；§4.1 顶栏→Task 2/3；§4.2 品牌色→Task 2；§4.3 组件（统计卡/语言折叠/工具栏/卡片/排行榜四要素/浮层/动态/空状态）→Task 5/6/7（空状态为既有逻辑保留）；§5 动效（count-up/hover/浮层动画/快捷键）→Task 7/8；§6 技术约束（数据层零改动、dev_render 不参与 Actions）→Task 1；§8 验证清单→Task 9。
- **类型一致性**：`buildTrendItem(p,i,full)` 在 Task 6 定义、Task 7 复用；`switchTrendTab(tab)` 在 Task 7 定义并被 `#trendTabs`/`#trendTabsFull` 共用；`renderHeader()` 在 Task 3 定义并接入 init；`counted` 标志在 Task 8 定义、`renderList` 消费。全部前后一致。
- **已知边界**：Task 4 Step 3 删除 1100px 媒体查询中的 `.trend-list{grid-template-columns:repeat(2,1fr)}`（双栏断点接管后，<1100px 时侧栏全宽、640px 下再降单列），与 Task 6 的 `.side .trend-list` 单列规则不冲突（作用域不同）。
