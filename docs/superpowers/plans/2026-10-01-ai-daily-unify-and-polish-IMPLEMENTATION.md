# AI 日报视觉统一与全页打磨 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec《2026-10-01-ai-daily-unify-insight-and-polish-SPEC.md》：洞察版块重排为日报同款报纸语言（Part A）+ 全页 13 项打磨（Part B 的 P0/P1 与 P2 中 B-10/B-13），经对抗性审查后按 CLAUDE.md 护栏推送。

**Architecture:** 所有改动落在两个生成端脚本（`build_ai_daily.py` 页面骨架与文本管线、`build_daily_insight.py` 洞察注入与历史归档页）。洞察 CSS 从"两处拷贝"收敛为模块级常量 `_DI_CSS`，注入块与历史页共用，消除漂移。文本清洗（截断/HN 元信息/中文排版）全部收口为可单测的纯函数。

**Tech Stack:** Python 3.11 标准库（无新依赖）；pytest；推送走 `tools/data_api_push.py`（Data API 四步）。

**Spec:** `docs/superpowers/plans/2026-10-01-ai-daily-unify-insight-and-polish-SPEC.md`（本计划逐条对应其 §3/§4/§6，Phase 4（B-11/B-12）不在本计划内）

## Global Constraints（每个任务隐含遵守）

- **产物不入库、不本地重建**：根目录 `ai-daily.html`/`index.html` 等已被另一条清理线**暂存删除**。禁止运行 `build_ai_daily.py:main()` / `build_daily_insight.py` 的全量入口（会把产物写回根目录，破坏对方暂存区）。视觉验证只允许沙箱渲染到 `_scratch/preview/`。
- **禁改清单**：`.github/workflows/update.yml`、`build_rss_aggregator.py`、`rss_fetch_state`——一个字符都不碰。
- **git 纪律**（CLAUDE.md）：只按具体路径 add；提交必须用显式 pathspec（`git commit -m "…" -- <paths>`），否则会把别人暂存的产物删除一起提交；禁 rebase/amend；禁 `2>&1`；不用 `&&`。
- **类名/锚点钩子**：`di-card`、`di-link`、`di-cite`、`di-bubble-link`、`di-bubble`、"破茧栏"、`<!-- daily-insight-start/end -->` 必须保留（`tests/daily_insight/test_html_links.py`、`test_integration.py`、`test_dedup.py` 钉住）。
- **红线**：每个洞察卡片必须带可跳转原文引用（di-link 或 di-cite）；`javascript:` 永不放行。
- **绿色语义**：绿色（var(--accent)）只出现在版块编号、kicker、引用链接、评分；其余一律墨/灰阶。
- **TDD**：每个任务先写失败测试再实现；每任务一个提交（本地提交，推送统一在 Task 9）。
- 测试命令统一 `py -3.11 -m pytest … -q`。

---

### Task 1: `_truncate` 句末收口重写（B-1 核心）

**Files:**
- Create: `tests/ai_daily/test_ai_daily_build.py`
- Modify: `build_ai_daily.py:118-130`（`_truncate`）

**Interfaces:**
- Produces: `build_ai_daily._truncate(s, maxlen=120)` —— 新契约：①≤maxlen 原样；②窗口内有句末标点（。！？；…!?;）且位置 ≥30 → 在句末收口，**不加省略号**；③句末点 <30 或无句末点 → 回退最近软标点（，、：:,）≥30 处 + `…`；④再不行 → 硬切 maxlen + `…`；⑤入口处清掉源文本自带的残尾省略号（`……`/`...`）与多余空白。

- [ ] **Step 1: 写失败测试**

创建 `tests/ai_daily/test_ai_daily_build.py`：

```python
# -*- coding: utf-8 -*-
"""build_ai_daily 文本管线与模板的单元测试（不联网、不写根目录产物）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_ai_daily as A


class TestTruncate:
    def test_short_unchanged(self):
        assert A._truncate("短摘要", 120) == "短摘要"

    def test_sentence_cut_no_ellipsis(self):
        s = "长" * 60 + "。" + "x" * 200
        out = A._truncate(s, 120)
        assert out.endswith("。")
        assert len(out) <= 121
        assert "…" not in out

    def test_soft_cut_adds_ellipsis(self):
        s = "z" * 40 + "，" + "z" * 130
        out = A._truncate(s, 120)
        assert out == "z" * 41 + "…"

    def test_hard_cut(self):
        assert A._truncate("y" * 300, 120) == "y" * 120 + "…"

    def test_trailing_ellipsis_stripped(self):
        assert A._truncate("正常的句子。……", 120) == "正常的句子。"
        assert A._truncate("短标题...", 120) == "短标题"

    def test_early_sentence_end_not_used(self):
        s = "短。" + "z" * 130
        out = A._truncate(s, 120)
        assert out != "短。"          # <30 的句号不做收口
        assert out.endswith("…")

    def test_whitespace_collapsed(self):
        assert A._truncate("  句一。\n句二  ", 120) == "句一。 句二"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py -q`
Expected: FAIL（`test_soft_cut_adds_ellipsis`/`test_trailing_ellipsis_stripped` 等，现实现按字符硬切）

- [ ] **Step 3: 实现**

替换 `build_ai_daily.py:118-130`：

```python
_SENT_END = "。！？；…!?;"
_SOFT_END = "，、：:,"


def _truncate(s, maxlen=120):
    """摘要截断：优先句末标点收口（句子完整，不加省略号）；其次软标点；最后硬切。
    入口顺带清掉源文本自带的机翻残尾省略号（Verge/TechCrunch 描述以"……"结尾的病灶）。"""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?:[…⋯]+|\.{2,}|。{2,})$", "", s).strip()
    if not s:
        return ""
    if len(s) <= maxlen:
        return s
    window = s[: maxlen + 1]
    cut = max((i for i, ch in enumerate(window) if ch in _SENT_END), default=-1)
    if cut >= 30:
        return s[: cut + 1]
    soft = max((i for i, ch in enumerate(window) if ch in _SOFT_END), default=-1)
    if soft >= 30:
        return s[: soft + 1] + "…"
    return s[:maxlen].rstrip() + "…"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py -q`
Expected: PASS（6 passed + 1 passed）

- [ ] **Step 5: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
git commit -m "feat(ai-daily): 摘要截断改为句末收口，清机翻残尾省略号（spec B-1）" -- tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
```

---

### Task 2: HN 元信息中文化（B-2）

**Files:**
- Modify: `tests/ai_daily/test_ai_daily_build.py`（追加）
- Modify: `build_ai_daily.py:293-324`（`_hn_items`）、`:750-776`（`translate_extra_items` 跳过条件）

**Interfaces:**
- Produces: `build_ai_daily._hn_summary(points, author)` —— `points>3` → `"273 分 · 用户 allisdust"`；`≤3` → `"用户 tim333"`。HN item dict 新增 `"points"`（int），`_hn_items` 排序改用 `x.get("points", 0)`（不再从 summary 正则抽数字）。翻译跳过条件从 `startswith("▲")` 改为 `it["source"] != "Hacker News"`。

- [ ] **Step 1: 写失败测试**（追加到 `tests/ai_daily/test_ai_daily_build.py`）

```python
class TestHnSummary:
    def test_high_score(self):
        assert A._hn_summary(273, "allisdust") == "273 分 · 用户 allisdust"

    def test_low_score_no_points(self):
        assert A._hn_summary(1, "tim333") == "用户 tim333"
        assert A._hn_summary(3, "x") == "用户 x"

    def test_missing_author(self):
        assert A._hn_summary(10, "") == "10 分 · 用户 ?"

    def test_summary_no_longer_has_triangle(self):
        s = A._hn_summary(72, "allisdust")
        assert "▲" not in s and "points" not in s
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py -q`
Expected: FAIL（`_hn_summary` 不存在 → AttributeError）

- [ ] **Step 3: 实现**

`build_ai_daily.py` 在 `_hn_items` 上方新增：

```python
def _hn_summary(points, author):
    """HN 条目元信息中文渲染：≤3 分不显分（对读者无信息量）。"""
    pts = int(points or 0)
    who = "用户 %s" % (author or "?")
    return "%d 分 · %s" % (pts, who) if pts > 3 else who
```

`_hn_items` 内（原 :313-323）：

```python
                out.append({
                    "title": title,
                    "link": link,
                    "category": "海外热点",
                    "source": "Hacker News",
                    "summary": _hn_summary(h.get("points"), h.get("author")),
                    "points": int(h.get("points") or 0),
                    "pub_date": _parse_iso(h.get("created_at") or ""),
                })
        except Exception as ex:
            print("[AI晨报] HN 拉取失败 (%s): %s" % (q, ex), file=sys.stderr)
    out.sort(key=lambda x: x.get("points", 0), reverse=True)
    return out[:10]
```

`translate_extra_items` 内（原 :768）：`if it.get("summary") and not it["summary"].startswith("▲"):` 改为
`if it.get("summary") and it["source"] != "Hacker News":`（docstring 同步：HN 点数摘要为元信息不翻译）。

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py tests/daily_insight -q`
Expected: PASS（HN 改动不影响 insight 套件）

- [ ] **Step 5: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
git commit -m "feat(ai-daily): HN 元信息中文化，低分不显分（spec B-2）" -- tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
```

---

### Task 3: arXiv 分类前缀移到信源行（B-6）

**Files:**
- Modify: `tests/ai_daily/test_ai_daily_build.py`（追加）
- Modify: `build_ai_daily.py:437-480`（`_arxiv_items`）、`:894-907`（`_item_html`）、`:750-776`（`translate_extra_items` 删 arXiv 特例）

**Interfaces:**
- Produces: arXiv item dict 新增 `"tag": "cs.CV"`（主分类），`title` 不再带 `[cs.XX]` 前缀；`_item_html` 信源行渲染 `arXiv · cs.CV`。

- [ ] **Step 1: 写失败测试**（追加）

```python
class TestArxivTag:
    def test_item_html_src_line_carries_tag(self):
        it = {"title": "Point2Part：统一3D分割", "link": "http://arxiv.org/abs/1",
              "category": "论文", "source": "arXiv", "summary": "摘要",
              "pub_date": None, "tag": "cs.CV"}
        html = A._item_html(it)
        assert "arXiv · cs.CV" in html
        assert "[cs.CV]" not in html

    def test_item_html_without_tag_unchanged(self):
        it = {"title": "普通条目", "link": "https://a.com", "category": "AI 模型",
              "source": "AIHOT", "summary": "s", "pub_date": None}
        html = A._item_html(it)
        assert "<span class=\"item-src\">AIHOT</span>" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py -q`
Expected: FAIL（tag 未渲染）

- [ ] **Step 3: 实现**

`_arxiv_items` 内（原 :472-479）：

```python
        items.append({
            "title": title,
            "link": link,
            "category": "论文",
            "source": "arXiv",
            "tag": cat,
            "summary": _truncate(_strip_html(e.findtext(ns + "summary") or "")),
            "pub_date": _parse_iso(e.findtext(ns + "published") or ""),
        })
```

`_item_html`（原 :894-907）首行改：

```python
def _item_html(it, top=False):
    """单条报道 HTML（晨报编辑部样式）。arXiv 的分类标签渲染进信源行。"""
    src = _esc(it["source"] + (" · " + it["tag"] if it.get("tag") else ""))
    title = _esc(it["title"])
    link = _esc(it["link"])
    summary = _esc(it["summary"])
    cls = ' class="item top"' if top else ' class="item"'
    return (
        f'<article{cls}>'
        f'<span class="item-src">{src}</span>'
        f'<h3 class="item-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>'
        f'<p class="item-desc">{summary}</p>'
        f'</article>'
    )
```

`translate_extra_items`：删除 arXiv 特例分支（原 :755-762），循环体只剩通用标题翻译 + summary 翻译（Task 2 已改 skip 条件）；docstring 改为「arXiv 标题不带分类前缀（前缀由 _arxiv_items 存 tag、_item_html 渲染到信源行）；HN 点数摘要为元信息不翻译」。

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py tests/daily_insight -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
git commit -m "feat(ai-daily): arXiv 分类前缀从标题移到信源行（spec B-6）" -- tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
```

---

### Task 4: 页面模板整改（B-3 / B-4 / B-7 / B-8 / B-9）

**Files:**
- Modify: `tests/ai_daily/test_ai_daily_build.py`（追加）
- Modify: `build_ai_daily.py:48-56`（删 `CAT_COLOR`）、`:915-945`（索引与 sec-head 颜色）、`:995-1197`（模板：口号/页脚/CSS）、`:1250-1252`（window_human 文案、`build_html` 调用去 status_line）、`:910`（`build_html` 签名去 status_line 形参）

**Interfaces:**
- Produces: `build_html(grouped, date_human, window_human, sources_note="")`（status_line 形参删除；无外部调用方，已核实全仓只有 `main()` 调用）。页脚只留「共 N 条 / 日期」；信源清单只在页首 mast-strip。编号与索引罗马数字全部 `style="color:var(--accent)"`。

- [ ] **Step 1: 写失败测试**（追加）

```python
def _fixture_grouped():
    def _it():
        return {"title": "测试标题", "link": "https://a.com/1", "category": "AI 模型",
                "source": "AIHOT", "summary": "摘要。", "pub_date": None}
    return [("AI 模型", [_it(), _it()]), ("论文", [_it()])]


class TestBuildHtmlTemplate:
    def test_numbers_use_accent_green_only(self):
        html = A.build_html(_fixture_grouped(), "2026年10月1日 星期四",
                            "数据截至 2026-10-01 08:00（北京时间）")
        assert html.count('style="color:var(--accent)"') >= 3
        for hex_ in ("#2563eb", "#7c3aed", "#0891b2", "#0d9488", "#d97706", "#dc2626"):
            assert hex_ not in html

    def test_slogan_and_window_wording(self):
        html = A.build_html(_fixture_grouped(), "d", "数据截至 t")
        assert "AI 资讯 · DAILY" in html
        assert "每早八时" not in html

    def test_footer_deduped(self):
        html = A.build_html(_fixture_grouped(), "2026年10月1日 星期四", "w",
                            sources_note=" · Hacker News")
        assert "今日信源" not in html
        assert "共 <strong>3</strong> 条" in html
        assert html.count("内容版权归原作者") == 1  # 只在 mast-strip

    def test_item_desc_clamped_and_src_readable(self):
        html = A.build_html(_fixture_grouped(), "d", "w")
        assert "-webkit-line-clamp:3" in html
        assert ".item-src{\n  font-size:11px;color:var(--muted);" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py -q`
Expected: FAIL（六色 hex 存在、口号/页脚/钳制未改）

- [ ] **Step 3: 实现（五处）**

1. 删除 `CAT_COLOR` dict（:48-56，`CAT_ORDER` 保留）。
2. 索引循环（:917-924）删 `color = CAT_COLOR.get(...)` 行，模板串改 `style="color:var(--accent)"`；sec 循环（:928-945）同样处理 `sec-num`。
3. mast-rule（:1154）：`<span class="mast-meta">每早八时 · DAILY</span>` → `<span class="mast-meta">AI 资讯 · DAILY</span>`。
4. 页脚（:1173-1177）改：

```html
  <footer class="foot">
    <span>共 <strong>{total}</strong> 条</span>
    <span>{date_human}</span>
  </footer>
```

5. CSS：`.item-src` 与 `.side-src` 的 `font-size:10.5px;color:var(--faint)` → `font-size:11px;color:var(--muted)`；`.idx-cnt` 的 `color:var(--faint)` → `color:var(--muted)`；`.item-desc` 追加 `display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;`；`@media (max-width:760px)` 块追加 `.item-desc{{-webkit-line-clamp:4;}}`。
6. `build_html` 签名去 `status_line=""`，docstring 同步；`main()`：`window_human` 改 `f"数据截至 {now.strftime('%Y-%m-%d %H:%M')}（北京时间）"`；`build_html(...)` 调用去实参；`status_line` 变量保留并改为仅 `print("[AI晨报] 信源状态: %s" % status_line)`（诊断进 GA 日志，不再进 HTML）。

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py tests/daily_insight tests/site_nav tests/site_nav_drift -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
git commit -m "feat(ai-daily): 编号收敛绿色系+口号/页脚去重+摘要钳制+元信息可读性（spec B-3/4/7/8/9）" -- tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
```

---

### Task 5: 洞察注入块重排（Part A 核心 + B-5）

**Files:**
- Modify: `tests/daily_insight/test_html_links.py:47`（正则放宽为 div|article；:51 断言放宽为 di-link **或** di-cite——feat 卡的引用由 cites 承载，红线不变）并追加新断言
- Modify: `build_daily_insight.py:4867-5087`（注入区整体：新常量 + `_allowed_links` 重构 + `_evt_card_html` + `_insight_section_html` + `_DI_CSS` + `_build_bubble_html` 重写 + `_inject_into_ai_daily` 接线 + `_cited_sources_html` 去掉 `<b>引用来源</b>` 标签）

**Interfaces:**
- Produces:
  - `build_daily_insight._DI_CSS`（str）：注入块与历史页共用的洞察 CSS（§3.4 规格，kicker/srcs 11px + --muted）。
  - `build_daily_insight._allowed_links(links, items=None) -> list[str]`（cap 3、http(s) 白名单、key_links 空回退 items——`test_dedup.py:348` 的行为保持）。
  - `build_daily_insight._strip_corpus_tags(s) -> str`（剥 `[agihunt][aihot][rss]`）。
  - `build_daily_insight._evt_card_html(evt, feat) -> str`（`<article class="di-card">`）。
  - `_inject_into_ai_daily(clusters, theme, bubble_breaker)` 输出新 section（`sec-7` + `di-feat` + `.cols` + `di-bubble` aside），并向日报索引 `</nav>` 前插入 `vii 深度洞察` 链接。

- [ ] **Step 1: 先改测试（红）**

`test_html_links.py:47` 正则改 `r'<(?:div|article) class="di-card">.*?(?=<(?:div|article) class="di-card">|<!-- daily-insight-end)'`；
`:51` 改 `assert 'class="di-link"' in c or 'class="di-cite"' in c, "洞察卡片缺失可跳转原文引用"`。
追加：

```python
    def test_newspaper_anatomy(self):
        clusters = [
            {"label": "特稿事件", "summary": "特稿摘要[agihunt]", "category": "ai-models",
             "score": 0.3, "status": "new", "resonance": "niche",
             "source_types": ["rss"], "key_links": ["https://a.com/x"],
             "deep_analysis": {"status": "ok", "event_reconstruction": "r",
                               "impact_analysis": "i", "source_divergence": "d",
                               "quote": "金句", "outlook": "o", "confidence": "high",
                               "cited_sources": [{"index": 1, "url": "https://src.io/a"}]}},
            {"label": "简报事件", "summary": "简报摘要", "category": "policy",
             "score": 0.1, "status": "new", "source_types": ["rss"],
             "items": [{"url": "https://c.com/z"}], "key_links": []},
        ]
        html = _inject(self.tmp, clusters)
        assert '<section id="sec-7" class="sec di-sec">' in html
        assert "深度洞察" in html and "1 条 · 1 篇深读" in html
        assert '<div class="di-feat">' in html
        assert "评分 0.3" in html and "新 · 垂直 · AI 模型" in html
        assert "评分 0.1" in html and "新 · 政策" in html
        assert "[agihunt]" not in html and "特稿摘要" in html   # 语料标记剥除
        feat = html.split('<div class="di-feat">')[1].split('<div class="cols">')[0]
        assert "特稿事件" in feat and "简报事件" not in feat
        assert 'class="di-deep"' in feat and "置信度 high" in feat
        assert 'class="di-quote"' in feat
        # 索引补 vii
        assert "vii</span>深度洞察" in html

    def test_bubble_newspaper_shell(self):
        bubble = [{"label": "破界", "summary": "s", "reason": "r", "url": "https://b.org/x"}]
        html = _inject(self.tmp, [], bubble=bubble)
        assert 'class="di-bubble-head"' in html
        assert "破茧栏 · 信息增量" in html
        assert 'class="di-bubble-grid"' in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/daily_insight/test_html_links.py -q`
Expected: FAIL（现实现无 sec-7/di-feat/kicker，语料标记未剥）

- [ ] **Step 3: 实现**

`build_daily_insight.py` 注入区（:4867 起）重构——常量区（`_AI_DAILY_FILE` 之后）：

```python
_DI_STATUS_LABELS = {"new": "新", "ongoing": "持续", "escalating": "升级", "faded": "消退"}
_DI_RESONANCE_LABELS = {"breakout": "破圈", "tech_hot": "技术热",
                        "niche": "垂直", "consumer": "消费级"}
# 洞察 category 码 → 报纸眉线中文（缺失回退原码）
_DI_CAT_CN = {"ai-models": "AI 模型", "ai-products": "AI 产品", "industry": "行业",
              "policy": "政策", "developer": "工程实践", "research": "论文",
              "consumer": "消费"}
_CORPUS_TAG_RE = re.compile(r"\s*\[(?:agihunt|aihot|rss)\]", re.I)


def _strip_corpus_tags(s):
    """摘要里的语料来源标记是机器内部记号，阅读层剥除（正文 [1][3] 引用序号保留）。"""
    return _CORPUS_TAG_RE.sub("", s or "").replace("  ", " ").strip()
```

`_source_links_html` 拆出白名单（行为与 `test_dedup.py:348` 兼容——非字符串跳过、javascript: 拒绝、回退 items）：

```python
def _allowed_links(links, items=None):
    seen, out = set(), []

    def _add(u):
        if isinstance(u, str) and re.match(r'https?://', u, re.I):
            k = _norm_url(u)
            if k and k not in seen:
                seen.add(k)
                out.append(u)

    for u in links or []:
        _add(u)
    if not out:
        for it in items or []:
            _add(it.get("url") or it.get("link") if isinstance(it, dict) else "")
    return out[:3]


def _source_links_html(links, items=None):
    chips = "".join(
        '<a class="di-link" href="%s" target="_blank" rel="noopener">%s&#8599;</a>'
        % (_esc(u), _esc(_link_host(u))) for u in _allowed_links(links, items))
    return '<div class="di-links">%s</div>' % chips if chips else ""
```

`_cited_sources_html` 尾行改 `return ('<p class="di-cites">%s</p>' % chips) if chips else ""`（去 `<b>引用来源</b>`，脚注行里冗余）。

卡片构建器（新函数）：

```python
def _evt_card_html(evt, feat):
    """洞察卡片：与日报 .item 同一语法（眉线/衬线标题/摘要/点线引用）。
    feat=True 渲染深读面板（card-2 底，对应日报 .item.top 语汇）。"""
    sl = _DI_STATUS_LABELS.get(evt.get("status", "new"), "")
    rl = _DI_RESONANCE_LABELS.get(evt.get("resonance", ""), "")
    cat = evt.get("category", "")
    kicker = " · ".join(p for p in (sl, rl, _DI_CAT_CN.get(cat, cat)) if p)
    deep = evt.get("deep_analysis") or {}
    has_deep = bool(deep) and deep.get("status") != "degraded"
    links = _allowed_links(evt.get("key_links"), evt.get("items"))
    head = _esc(evt.get("label", ""))
    label = ('<h3 class="di-label"><a href="%s" target="_blank" rel="noopener">%s</a></h3>'
             % (_esc(links[0]), head)) if links else '<h3 class="di-label">%s</h3>' % head
    out = ['<article class="di-card%s">' % (" has-deep" if feat else ""),
           '<div class="di-kicker"><span>%s</span>'
           '<span class="di-score" title="综合评分">评分 %.1f</span></div>'
           % (_esc(kicker), evt.get("score", 0)),
           label,
           '<p class="di-summary">%s</p>' % _esc(_strip_corpus_tags(evt.get("summary", "")))]
    if has_deep:
        cites = _cited_sources_html(deep)
        if not cites:
            # 红线兜底：深读无引用清单时回退原文链接组
            cites = _source_links_html(evt.get("key_links"), evt.get("items"))
        out.append('''<div class="di-deep">
<div class="di-deep-kicker">深度解读 · ANALYSIS</div>
<div class="di-deep-sec"><strong>事件还原</strong><p>%s</p></div>
<div class="di-deep-sec"><strong>影响分析</strong><p>%s</p></div>
<div class="di-deep-sec"><strong>信源分歧</strong><p>%s</p></div>
%s
<div class="di-deep-sec"><strong>后续展望</strong><p>%s</p></div>
<div class="di-deep-foot"><span class="di-conf">置信度 %s</span>%s</div>
</div>''' % (_esc(deep.get("event_reconstruction", "")),
             _esc(deep.get("impact_analysis", "")),
             _esc(deep.get("source_divergence", "")),
             ('<blockquote class="di-quote">%s</blockquote>' % _esc(deep["quote"]))
             if deep.get("quote") else "",
             _esc(deep.get("outlook", "")),
             _esc(deep.get("confidence", "")),
             cites))
    else:
        srcs = " · ".join(_esc(s) for s in evt.get("source_types", []))
        foot = ('<span class="di-srcs">信源 %s</span>' % srcs) if srcs else ""
        foot += _source_links_html(evt.get("key_links"), evt.get("items"))
        if foot:
            out.append('<div class="di-foot">%s</div>' % foot)
    out.append('</article>')
    return "\n".join(out)
```

`_build_bubble_html` 整体替换（保住 `test_integration.py::test_inject_html_valid` 与 `test_html_links.py::test_bubble_card_link` 钩子）：

```python
def _build_bubble_html(bubble_breaker):
    """破茧栏：上下双细线夹住的报纸边栏（信息增量）。"""
    if not bubble_breaker:
        return ""
    cards = []
    for item in bubble_breaker:
        _bu = item.get("url", "")
        _bl = _esc(item.get("label", ""))
        _bh = ('<a class="di-bubble-link" href="%s" target="_blank" rel="noopener">%s&#8599;</a>'
               % (_esc(_bu), _bl)) if re.match(r'https?://', _bu or "", re.I) else _bl
        cards.append(
            '<article class="di-bubble-card">'
            '<h4 class="di-bubble-label">%s</h4>'
            '<p class="di-bubble-summary">%s</p>'
            '<div class="di-bubble-reason">%s</div>'
            '</article>' % (_bh, _esc(item.get("summary", "")),
                            _esc(item.get("reason", ""))))
    return ('<aside class="di-bubble">\n'
            '  <div class="di-bubble-head">'
            '<span class="di-bubble-head-t">破茧栏 · 信息增量</span></div>\n'
            '  <div class="di-bubble-grid">\n%s\n  </div>\n</aside>'
            % "\n".join(cards))
```

`_DI_CSS` 模块级常量（spec §3.4 全文，demo 像素基准；kicker/srcs 按 B-8 用 11px + --muted）：

```python
_DI_CSS = """/* ---- 每日深度洞察 · 与日报同一套报纸语法 ---- */
.di-sec .di-theme{font-family:var(--display);font-style:italic;font-size:14.5px;color:var(--muted);margin:-4px 0 6px;line-height:1.7;}
.di-card{padding:14px 0;border-bottom:1px solid var(--line);break-inside:avoid;}
.di-feat .di-card{padding:16px 0;}
.di-kicker{display:flex;align-items:baseline;gap:8px;font-size:11px;color:var(--muted);letter-spacing:.08em;margin-bottom:6px;}
.di-kicker .di-score{margin-left:auto;font-family:var(--display);font-style:italic;font-size:12px;color:var(--accent-ink);letter-spacing:.02em;white-space:nowrap;}
.di-label{font-family:var(--display);font-size:17px;font-weight:700;line-height:1.42;margin:0 0 6px;}
.di-label a:hover{color:var(--accent-ink);}
.di-feat .di-label{font-size:20px;}
.di-summary{font-size:13px;color:var(--muted);line-height:1.7;margin:0 0 8px;}
.di-foot{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;}
.di-srcs{font-size:11px;color:var(--muted);letter-spacing:.05em;}
.di-links{display:flex;gap:12px;flex-wrap:wrap;margin-left:auto;}
.di-links a,.di-cites a{font-size:11.5px;color:var(--accent-ink);border-bottom:1px dotted var(--accent);white-space:nowrap;}
.di-links a:hover,.di-cites a:hover{color:var(--accent);}
.di-deep{margin-top:12px;background:var(--card-2);border:1px solid var(--line);padding:14px 18px 12px;}
.di-deep-kicker{font-size:11px;letter-spacing:.18em;color:var(--accent-ink);font-weight:700;display:flex;align-items:center;gap:10px;margin-bottom:10px;}
.di-deep-kicker::after{content:"";flex:1;height:1px;background:var(--line);}
.di-deep-sec{margin-bottom:9px;}
.di-deep-sec strong{display:block;font-size:11.5px;letter-spacing:.1em;color:var(--ink);margin-bottom:3px;}
.di-deep-sec p{font-size:12.5px;color:var(--muted);line-height:1.75;margin:0;}
.di-quote{font-family:var(--display);font-style:italic;font-size:14px;line-height:1.7;color:var(--ink);border-left:2px solid var(--accent);padding:1px 0 1px 12px;margin:10px 0;}
.di-deep-foot{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;margin-top:2px;padding-top:8px;border-top:1px solid var(--line);}
.di-conf{font-size:11px;color:var(--muted);letter-spacing:.08em;}
.di-cites{display:flex;gap:12px;flex-wrap:wrap;}
.di-bubble{margin-top:30px;border-top:3px double var(--line-strong);border-bottom:3px double var(--line-strong);padding:14px 0 4px;}
.di-bubble-head{display:flex;align-items:center;gap:14px;margin-bottom:6px;}
.di-bubble-head::before,.di-bubble-head::after{content:"";flex:1;height:1px;background:var(--line-strong);}
.di-bubble-head-t{font-family:var(--display);font-size:15px;font-weight:700;letter-spacing:.14em;white-space:nowrap;}
.di-bubble-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:34px;}
.di-bubble-card{padding:10px 0;border-bottom:1px solid var(--line);}
.di-bubble-card:nth-last-child(-n+2){border-bottom:none;}
.di-bubble-card h4{font-family:var(--display);font-size:15px;font-weight:700;line-height:1.45;margin:0 0 4px;}
.di-bubble-card h4 a:hover{color:var(--accent-ink);}
.di-bubble-card p{font-size:12px;color:var(--muted);line-height:1.65;margin:0 0 4px;display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden;}
.di-bubble-reason{font-size:11px;color:var(--muted);font-style:italic;}
@media (max-width:760px){
.di-feat .di-label{font-size:18px;}
.di-links{margin-left:0;}
.di-bubble-grid{grid-template-columns:1fr;}
.di-bubble-card:nth-last-child(-n+2){border-bottom:1px solid var(--line);}
.di-bubble-card:last-child{border-bottom:none;}
}
"""
```

`_inject_into_ai_daily` 的卡片循环与 `section_html` 模板整体替换：

```python
    feats, briefs = [], []
    for evt in clusters:
        deep = evt.get("deep_analysis") or {}
        (feats if (deep and deep.get("status") != "degraded") else briefs).append(evt)
    feat_html = "\n".join(_evt_card_html(e, True) for e in feats)
    brief_html = "\n".join(_evt_card_html(e, False) for e in briefs)
    n_total, n_deep = len(clusters), len(feats)
    vii_link = ('<a href="#sec-7"><span class="idx-n" style="color:var(--accent)">vii</span>'
                '深度洞察<span class="idx-cnt">%d</span></a>' % n_total)

    section_html = '''<!-- daily-insight-start -->
<style>
%s</style>
<section id="sec-7" class="sec di-sec">
  <div class="sec-head"><span class="sec-num" style="color:var(--accent)">07</span><h2 class="sec-name">深度洞察</h2><span class="sec-cnt">%d 条 · %d 篇深读</span></div>
  <p class="di-theme">%s</p>
  <div class="di-feat">
%s
  </div>
  <div class="cols">
%s
  </div>
%s
</section>
<!-- daily-insight-end -->
''' % (_DI_CSS, n_total, n_deep, _esc(theme), feat_html, brief_html,
       _build_bubble_html(bubble_breaker))
```

注入完成后（写文件前）补索引：

```python
    if 'class="index"' in html:
        html = html.replace('</nav>', vii_link + '\n  </nav>', 1)
```

（`</nav>` 全页唯一——已核实现模板只有索引一个 nav。）

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/daily_insight -q`
Expected: PASS（含 test_dedup/test_integration 既有断言）

- [ ] **Step 5: 提交**

```bash
git add tests/daily_insight/test_html_links.py build_daily_insight.py
git commit -m "feat(insight): 洞察版块重排为日报报纸语法，CSS收敛为_DI_CSS，剥语料标记（spec PartA+B-5）" -- tests/daily_insight/test_html_links.py build_daily_insight.py
```

---

### Task 6: 历史归档页同步（防"第三个产品"）

**Files:**
- Modify: `build_daily_insight.py:4582-4864`（`_build_history_html`：卡片模板换 `_evt_card_html(e, feat=有deep)` 同构 + CSS 块换 `_DI_CSS` + 归档页自有规则）

**Interfaces:**
- Consumes: Task 5 的 `_DI_CSS` / `_evt_card_html` / `_DI_CAT_CN` / `_strip_corpus_tags`。
- Produces: 归档页卡片与日报洞察卡同构；`test_history_chunked.py` 等既有断言不受破坏（执行时先 grep 该文件对 `di-`/`day-` 的引用，如有钉住旧结构的断言按 Task 5 同样的"保留钩子"原则同步）。

- [ ] **Step 1: 检查既有测试引用**

Run: `grep -n "di-\|day-theme\|day-section" tests/daily_insight/test_history_chunked.py tests/daily_insight/test_history*.py 2>/dev/null`
记录所有对旧结构的断言（预期只有 `day-section`/`day-theme`/`daySelect` 这类与卡片无关的选择器；若有 di-card 结构断言，同步放宽为 div|article）。

- [ ] **Step 2: 写失败测试**（追加到 `tests/ai_daily/test_ai_daily_build.py`，monkeypatch `_load_history`）

```python
class TestHistoryPageUnified:
    def test_history_cards_use_same_anatomy(self, monkeypatch, tmp_path):
        import build_daily_insight as B
        day = {"date": "2026-10-01", "theme": "主题",
               "stats": {"total_events": 1},
               "events": [{"label": "历史事件", "summary": "摘[aihot]", "category": "industry",
                           "score": 0.2, "status": "new", "resonance": "niche",
                           "sources": ["rss"], "key_links": ["https://h.io/1"],
                           "deep_analysis": None}]}
        monkeypatch.setattr(B, "_load_history", lambda: {"days": [day]})
        monkeypatch.setattr(B, "HISTORY_HTML", str(tmp_path / "h.html"))
        B._build_history_html()
        html = open(B.HISTORY_HTML, encoding="utf-8").read()
        assert '<article class="di-card">' in html
        assert "新 · 垂直 · 行业" in html
        assert "[aihot]" not in html
        assert "深度解读 · ANALYSIS" not in html  # 无 deep 不渲染面板
```

（若 `_build_history_html` 还依赖其他全局（如 `NOW_BJ`），按 `test_integration.py` 的 `_init_now_bj` fixture 方式补。）

- [ ] **Step 3: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py::TestHistoryPageUnified -q`
Expected: FAIL（现实现是 div.di-card + di-head 徽章）

- [ ] **Step 4: 实现**

`_build_history_html`：
1. 事件卡循环改用 `_evt_card_html(evt, feat=bool(deep and deep.get("status") != "degraded"))`（history 的 evt 字段与注入块一致：`status/resonance/category/score/label/summary/key_links/deep_analysis`；`source_types` 缺失时 kicker 无信源段，`sources` 列表映射为 `evt.setdefault("source_types", evt.get("sources", []))` 后再传入）。
2. 深读渲染：`_evt_card_html` 已覆盖（history 原"金句"独立 sec 并入 quote 位置）。
3. CSS：模板 `<style>` 内 event-cards/deep 段（:4759-4783）整段替换为 `%s` 占位引用 `_DI_CSS`，保留 day-nav/day-theme 规则；`%` 格式化参数补 `_DI_CSS`。
4. `.di-card:last-child{border-bottom:none}` 等旧规则由 `_DI_CSS` 接管，删除重复。

- [ ] **Step 5: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/daily_insight tests/ai_daily -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_daily_insight.py
git commit -m "feat(insight-history): 归档页复用_DI_CSS与同构卡片，消除两处样式漂移（spec PartA.3.5）" -- tests/ai_daily/test_ai_daily_build.py build_daily_insight.py
```

---

### Task 7: 中文排版归一（B-10 + B-13）

**Files:**
- Modify: `tests/ai_daily/test_ai_daily_build.py`（追加）
- Modify: `build_ai_daily.py`（新工具 `_zh_typo` + `_item_html`/`build_html` 头条区渲染出口套用）

**Interfaces:**
- Produces: `build_ai_daily._zh_typo(s)` —— ①CJK↔拉丁/数字边界补空格（已有空格不重复）；②成对直引号 `"` → 中文 `“”`（不成对保持原样）。仅用于标题/摘要渲染出口，URL 与信源名不经过它。

- [ ] **Step 1: 写失败测试**（追加）

```python
class TestZhTypo:
    def test_cjk_latin_boundary(self):
        assert A._zh_typo("Google宣布11月17日以Skills取代Gems") == \
            "Google 宣布 11 月 17 日以 Skills 取代 Gems"

    def test_existing_space_not_doubled(self):
        assert A._zh_typo("OpenAI 发布 GPT-6") == "OpenAI 发布 GPT-6"

    def test_percent_boundary(self):
        assert A._zh_typo("毛利率80%的护城河") == "毛利率 80% 的护城河"

    def test_paired_quotes_converted(self):
        assert A._zh_typo('称为"超级智能"的时代') == "称为“超级智能”的时代"

    def test_unbalanced_quotes_untouched(self):
        assert A._zh_typo('他说"然后') == '他说"然后'

    def test_empty(self):
        assert A._zh_typo("") == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.11 -m pytest tests/ai_daily/test_ai_daily_build.py::TestZhTypo -q`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现**

`build_ai_daily.py`（`_esc` 之后）新增：

```python
def _zh_typo(s):
    """中文排版归一：CJK 与拉丁/数字边界补空格；成对直引号转中文引号。
    只处理纯文本（标题/摘要），不用于 URL。"""
    if not s:
        return s
    out = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)
    out = re.sub(r"([A-Za-z0-9%)\\]])([\u4e00-\u9fff])", r"\1 \2", out)
    out = re.sub(r" {2,}", " ", out).strip()
    if out.count('"') >= 2 and out.count('"') % 2 == 0:
        res, opening = [], True
        for ch in out:
            if ch == '"':
                res.append("“" if opening else "”")
                opening = not opening
            else:
                res.append(ch)
        out = "".join(res)
    return out
```

应用点：`_item_html` 的 `title = _esc(_zh_typo(it["title"]))`、`summary = _esc(_zh_typo(it["summary"]))`；`build_html` 头条区（lead_main/lead_sides 的 title、summary 同样包一层）。

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.11 -m pytest tests/ai_daily tests/daily_insight -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
git commit -m "feat(ai-daily): 中西文混排空格与中文引号归一（spec B-10/B-13）" -- tests/ai_daily/test_ai_daily_build.py build_ai_daily.py
```

---

### Task 8: 全量回归 + 沙箱视觉验证 + 对抗性审查

**Files:**
- Create: `_scratch/render_preview.py`（沙箱渲染，**绝不写根目录产物**）

- [ ] **Step 1: 全量测试**

Run: `py -3.11 -m pytest tests/ai_daily tests/daily_insight tests/site_nav tests/site_nav_drift tests/rss_history -q`
Expected: 全绿（rss_history 是翻译窗口判据所在地，确认未受波及）

- [ ] **Step 2: 沙箱渲染**

`_scratch/render_preview.py`：import 两个构建脚本，用 fixture 数据（含 deep/无 deep/破茧栏/36氪长摘要/HN 条目/arXiv tag 条目）调 `build_html()` + monkeypatch `_AI_DAILY_FILE` 后调 `_inject_into_ai_daily()`，写 `_scratch/preview/ai-daily-preview.html`；再 monkeypatch `_load_history`/`HISTORY_HTML` 写 `_scratch/preview/history-preview.html`。用浏览器过四关：桌面 1440 亮/暗、移动 390 亮色；检查点=spec §7（06→07 衔接、深读面板/双栏/破茧栏三态、暗色 card-2、vii 锚点）。

- [ ] **Step 3: 对抗性审查（用户点名要求）**

并行派两个 general-purpose 子代理（给完整 diff + spec + 本计划）：
- R1 回归猎手：专攻"改坏什么"——六源 `_truncate` 共用语义、`_dedupe`/`_summ_key` 对新 HN summary 的依赖、`test_dedup.py:348` 行为保持、注入锚点/类名钩子、翻译窗口判据（`窗口总量 ≤ 窗口+30` 的测试是否仍绿）、历史页与注入块是否真的同 CSS。
- R2 spec 符合力：逐条核对 spec §3/§4 是否落地、有无计划外改动（`git diff --stat` 不得出现禁改清单文件）。
两个审查者的发现逐条修复并补测试后重跑 Step 1。

- [ ] **Step 4: 提交审查修复（如有）**

```bash
git add <修复涉及的具体文件>
git commit -m "fix(ai-daily): 对抗性审查修复 <摘要>" -- <具体文件>
```

---

### Task 9: 推送（CLAUDE.md 四步 + 防吞护栏）

- [ ] **Step 1: 盘点暂存区（防卷入他人改动）**

Run: `git status --short`
确认：本计划涉及的 5 个文件之外，**已暂存的产物删除（index.html 等 D 项）不属于本次提交**。提交必须用显式 pathspec（见 Step 2），绝不裸 `git commit -m`。

- [ ] **Step 2: 按路径提交（全部任务已各自提交过，这里只兜底遗漏）**

```bash
git add docs/superpowers/plans/2026-10-01-ai-daily-unify-insight-and-polish-SPEC.md docs/superpowers/plans/2026-10-01-ai-daily-unify-and-polish-IMPLEMENTATION.md
git commit -m "docs: AI 日报视觉统一 spec 与实施计划" -- docs/superpowers/plans/2026-10-01-ai-daily-unify-insight-and-polish-SPEC.md docs/superpowers/plans/2026-10-01-ai-daily-unify-and-polish-IMPLEMENTATION.md
```

- [ ] **Step 3: 守门（防吞核心）**

Run: `py -3.11 tools/data_api_push.py --check-only`
Expected: 无未完成的 CI run。若报"有构建进行中"：等待至 run 结束再重试（判据是"当前无未完成 run"，不是"离整点还早"）。

- [ ] **Step 4: 推送**

Run: `py -3.11 tools/data_api_push.py`（按该工具实际 CLI；写前自动 CRLF→LF，ref force:false，他人抢先提交会安全报错而非覆盖——报错则重跑 Step 3-4）
Expected: blob 写入 → tree → commit → ref 移动成功，输出含提交哈希。

- [ ] **Step 5: 推后核验**

Run: `py -3.11 -m pytest tests/site_nav tests/site_nav_drift -q`（本地仍绿）；在下一场 CI 构建完成后核对线上 `ai-daily.html` 的 07 版块与页脚（人工/浏览器），确认 Data API 改动未被构建回滚（对照 CLAUDE.md 记载的吞档模式：推后 15 分钟内的整点场提交）。

---

## Self-Review 记录

- Spec 覆盖：§3.1-3.6→Task 5/6；§4 B-1/2/3/4/6/7/8/9/10/13→Task 1/2/4/3/4/4/4/4/7/7；B-5→Task 5；B-11/12（Phase 4 可选）**不在本计划**，已在 header 声明。
- 类型一致性：`_allowed_links`/`_evt_card_html`/`_DI_CSS` 在 Task 5 定义、Task 6 消费，签名一致；`_hn_summary`/`_zh_typo`/`_truncate` 均有测试钉住。
- 占位符扫描：无 TBD/TODO；所有代码步含真实代码。
