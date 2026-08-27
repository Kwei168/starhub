# -*- coding: utf-8 -*-
"""Generate ai-daily.html from AIHOT RSS feed (https://aihot.virxact.com/feed.xml).
仅依赖 Python 标准库。由 fetch_and_build.py 调用或独立运行。
每次构建自动拉取最新 RSS，筛选近 24 小时条目生成晨报。
页面风格参照 AIHOT 日报：杂志式排版，目录索引 + 编号分区 + 列表式内容。
"""
import html as html_mod
import datetime
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

RSS_URL = "https://aihot.virxact.com/feed.xml"
OUT = "ai-daily.html"
FALLBACK_SRC = "ai_daily.json"  # RSS 失败时回退到本地 JSON

# RSS 分类 → 图标 & 配色 & 英文副标题
CAT_STYLE = {
    "AI 模型":   ("🧠", "#2563eb", "MODEL RELEASES"),
    "AI 产品":   ("🚀", "#7c3aed", "PRODUCT LAUNCHES"),
    "行业动态":   ("🌐", "#0891b2", "INDUSTRY NEWS"),
    "论文":      ("📄", "#d97706", "RESEARCH PAPERS"),
    "技巧观点":   ("💡", "#dc2626", "TIPS & TAKES"),
}
# 分类排序权重（按此顺序展示）
CAT_ORDER = ["AI 模型", "AI 产品", "行业动态", "论文", "技巧观点"]


def _now_bj():
    """北京时间 now。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def _parse_rss_date(s):
    """解析 RSS pubDate（RFC 2822 格式）→ UTC datetime。"""
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        s2 = s.replace(" GMT", " +0000")
        return datetime.datetime.strptime(s2, "%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return None


def _strip_html(text):
    """从 HTML 片段中提取纯文本。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


def _extract_source(author_text):
    """从 RSS author 字段提取来源名。"""
    m = re.search(r"\(([^)]+)\)", author_text or "")
    return m.group(1) if m else ""


def _truncate(s, maxlen=120):
    if not s:
        return ""
    s = s.strip()
    if len(s) <= maxlen:
        return s
    cut = -1
    for i, ch in enumerate(s[:maxlen]):
        if ch in "。！？；":
            cut = i
    if cut >= 30:
        return s[:cut + 1]
    return s[:maxlen] + "…"


def _esc(s):
    return html_mod.escape(str(s), quote=True)


def fetch_rss():
    """拉取 AIHOT RSS feed，返回 items 列表或 None。"""
    req = urllib.request.Request(RSS_URL, headers={
        "User-Agent": "Mozilla/5.0 (starhub-auto-update)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(500000).decode("utf-8", errors="replace")
    except Exception as e:
        print("[AI晨报] RSS 拉取失败: %s" % e, file=sys.stderr)
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print("[AI晨报] RSS 解析失败: %s" % e, file=sys.stderr)
        return None
    except Exception as e:
        print("[AI晨报] RSS 处理异常: %s" % e, file=sys.stderr)
        return None

    channel = root.find("channel")
    if channel is None:
        print("[AI晨报] RSS 格式异常: 无 channel", file=sys.stderr)
        return None

    items = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        category = (item.findtext("category") or "").strip()
        source = _extract_source(item.findtext("author") or "")
        desc_raw = item.findtext("description") or ""
        summary = _truncate(_strip_html(desc_raw))
        pub_date_str = (item.findtext("pubDate") or "").strip()
        pub_date = _parse_rss_date(pub_date_str)
        if title:
            items.append({
                "title": title,
                "link": link,
                "category": category or "其他",
                "source": source,
                "summary": summary,
                "pub_date": pub_date,
            })
    return items


def _fallback_json():
    """RSS 失败时从本地 ai_daily.json 加载。"""
    if not os.path.exists(FALLBACK_SRC):
        return None
    try:
        with open(FALLBACK_SRC, encoding="utf-8") as f:
            data = json.load(f)
        report = data.get("report") or data
        items = []
        for sec in report.get("sections", []):
            label = sec.get("label", "")
            cat_map = {
                "模型发布/更新": "AI 模型",
                "产品发布/更新": "AI 产品",
                "行业动态": "行业动态",
                "论文研究": "论文",
                "技巧与观点": "技巧观点",
            }
            cat = cat_map.get(label, label)
            for it in sec.get("items") or []:
                links = it.get("links") or {}
                items.append({
                    "title": (it.get("title") or "").strip(),
                    "link": links.get("aihot") or links.get("original") or "#",
                    "category": cat,
                    "source": (it.get("source") or {}).get("name", ""),
                    "summary": _truncate(it.get("summary") or ""),
                    "pub_date": None,
                })
        return items
    except Exception as e:
        print("[AI晨报] JSON 回退失败: %s" % e, file=sys.stderr)
        return None


def _filter_24h(items):
    """筛选最近 24 小时的条目（按北京时间）。"""
    now = _now_bj()
    cutoff = now - datetime.timedelta(hours=28)
    out = []
    for it in items:
        if it["pub_date"] is None:
            out.append(it)
            continue
        pd = it["pub_date"]
        if pd.tzinfo is not None:
            pd = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        else:
            pd = pd.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        if pd >= cutoff:
            out.append(it)
    return out


def _group_by_cat(items):
    """按分类分组，返回 [(cat, [items])] 按 CAT_ORDER 排序。"""
    groups = {}
    for it in items:
        cat = it["category"]
        groups.setdefault(cat, []).append(it)
    result = []
    for cat in CAT_ORDER:
        if cat in groups:
            result.append((cat, groups.pop(cat)))
    for cat, its in groups.items():
        result.append((cat, its))
    return result


def build_html(grouped, date_human, window_human):
    """生成 AIHOT 日报风格 HTML 页面。"""
    total = sum(len(its) for _, its in grouped)

    # ---- 目录索引 ----
    toc_items = ""
    for i, (cat, its) in enumerate(grouped, 1):
        icon, color, en = CAT_STYLE.get(cat, ("📌", "#57606a", "OTHER"))
        first_title = its[0]["title"] if its else ""
        toc_items += (
            f'<div class="toc-row">'
            f'<span class="toc-num" style="color:{color}">{i:02d}</span>'
            f'<span class="toc-name">{_esc(cat)}</span>'
            f'<span class="toc-en">{en}</span>'
            f'<span class="toc-cnt">{len(its)}</span>'
            f'<div class="toc-sub">{_esc(first_title[:40])}</div>'
            f'</div>'
        )

    # ---- 分类导航 tabs ----
    nav_tabs = ""
    sections_html = ""
    for i, (cat, its) in enumerate(grouped, 1):
        icon, color, en = CAT_STYLE.get(cat, ("📌", "#57606a", "OTHER"))
        anchor = f"sec-{i}"
        nav_tabs += (
            f'<a class="tab" href="#{anchor}" data-target="{anchor}" style="--c:{color}">'
            f'{_esc(cat)}<span class="tab-n">{len(its)}</span></a>'
        )

        # 列表项
        items_html = ""
        for j, it in enumerate(its, 1):
            src = _esc(it["source"])
            title = _esc(it["title"])
            link = _esc(it["link"])
            summary = _esc(it["summary"])
            items_html += (
                f'<div class="item">'
                f'<div class="item-head">'
                f'<span class="item-src">{src}</span>'
                f'</div>'
                f'<h3 class="item-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>'
                f'<p class="item-desc">{summary}</p>'
                f'</div>'
            )

        sections_html += (
            f'<section id="{anchor}" class="sec">'
            f'<div class="sec-head">'
            f'<span class="sec-num" style="color:{color}">{i:02d}</span>'
            f'<div class="sec-info">'
            f'<h2 class="sec-name">{_esc(cat)}</h2>'
            f'<span class="sec-en">{en}</span>'
            f'</div>'
            f'<span class="sec-cnt">{len(its)} 篇</span>'
            f'</div>'
            f'<div class="item-list">{items_html}</div>'
            f'</section>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>AI 晨报 · {date_human}</title>
<style>
:root {{
  --bg:#f5f5f5; --card:#fff; --ink:#1a1a1a; --muted:#666;
  --line:#e8e8e8; --border2:#f0f0f0;
  --accent:#1a6b6b; --accent-weak:rgba(26,107,107,.06);
}}
[data-theme="dark"] {{
  --bg:#0d1117; --card:#161b22; --ink:#e6edf3; --muted:#8b949e;
  --line:#30363d; --border2:#21262d;
  --accent:#58a6ff; --accent-weak:rgba(88,166,255,.08);
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; scroll-padding-top:60px; }}
body {{
  margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
    "Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.6;
  -webkit-font-smoothing:antialiased;
}}
a {{ color:inherit; text-decoration:none; }}
.wrap {{ max-width:860px; margin:0 auto; padding:0 16px 60px; }}

/* ---- Top bar ---- */
.topbar {{
  display:flex; align-items:center; gap:10px; padding:12px 0;
}}
.back {{
  display:inline-flex; align-items:center; gap:5px; padding:6px 14px;
  border-radius:8px; background:var(--card); border:1px solid var(--line);
  font-size:13px; color:var(--ink); transition:all .15s;
}}
.back:hover {{ border-color:var(--accent); color:var(--accent); }}
.topbar .spacer {{ flex:1; }}
.theme-btn {{
  width:34px; height:34px; border-radius:8px; background:var(--card);
  border:1px solid var(--line); display:flex; align-items:center; justify-content:center;
  cursor:pointer; font-size:15px; transition:all .15s; color:var(--ink);
}}
.theme-btn:hover {{ border-color:var(--accent); }}

/* ---- Hero ---- */
.hero {{ padding:16px 0 20px; text-align:center; }}
.hero-vol {{
  font-size:11px; letter-spacing:.12em; color:var(--muted);
  font-weight:500; margin-bottom:8px;
}}
.hero h1 {{
  font-size:clamp(28px,5vw,42px); font-weight:800; margin:0 0 6px;
  letter-spacing:-.01em; line-height:1.2;
}}
.hero-date {{
  font-size:14px; color:var(--muted); margin-bottom:4px;
}}
.hero-sub {{ font-size:12px; color:var(--muted); opacity:.7; }}

/* ---- TOC ---- */
.toc {{
  background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:16px 20px; margin:20px 0 28px;
}}
.toc-title {{
  display:flex; align-items:center; justify-content:space-between;
  font-size:14px; font-weight:700; margin-bottom:12px;
  padding-bottom:10px; border-bottom:1px solid var(--line);
}}
.toc-title .tc {{ font-size:12px; color:var(--muted); font-weight:400; }}
.toc-row {{
  display:flex; align-items:baseline; gap:8px;
  padding:7px 0; border-bottom:1px solid var(--border2);
}}
.toc-row:last-child {{ border-bottom:none; }}
.toc-num {{ font-size:15px; font-weight:800; flex:none; min-width:24px; }}
.toc-name {{ font-size:14px; font-weight:600; flex:none; }}
.toc-en {{ font-size:10px; color:var(--muted); letter-spacing:.06em; flex:none; }}
.toc-cnt {{ margin-left:auto; font-size:12px; color:var(--muted); flex:none; }}
.toc-sub {{
  font-size:12.5px; color:var(--muted); margin-left:32px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}}

/* ---- Category tabs ---- */
.tabs {{
  display:flex; gap:6px; overflow-x:auto; padding-bottom:2px;
  margin-bottom:24px; -webkit-overflow-scrolling:touch;
}}
.tabs::-webkit-scrollbar {{ height:0; }}
.tab {{
  flex:none; padding:6px 14px; border-radius:8px; font-size:13px;
  font-weight:500; color:var(--muted); background:var(--card);
  border:1px solid var(--line); transition:all .15s; white-space:nowrap;
  display:inline-flex; align-items:center; gap:5px;
}}
.tab:hover {{ color:var(--ink); border-color:var(--c); }}
.tab.active {{ color:#fff; background:var(--c); border-color:var(--c); font-weight:600; }}
.tab-n {{
  font-size:11px; font-weight:700; background:rgba(255,255,255,.2);
  border-radius:6px; padding:1px 6px; min-width:18px; text-align:center;
}}
.tab:not(.active) .tab-n {{ background:var(--line); color:var(--muted); }}

/* ---- Sections ---- */
.sec {{ margin-bottom:36px; }}
.sec-head {{
  display:flex; align-items:center; gap:10px;
  padding-bottom:10px; margin-bottom:14px;
  border-bottom:2px solid var(--line);
}}
.sec-num {{ font-size:18px; font-weight:800; flex:none; }}
.sec-info {{ flex:1; min-width:0; }}
.sec-name {{ font-size:17px; font-weight:700; margin:0; line-height:1.3; }}
.sec-en {{ font-size:10px; color:var(--muted); letter-spacing:.08em; font-weight:500; }}
.sec-cnt {{ font-size:12px; color:var(--muted); flex:none; white-space:nowrap; }}

/* ---- Item list ---- */
.item-list {{ }}
.item {{
  padding:14px 0; border-bottom:1px solid var(--border2);
}}
.item:last-child {{ border-bottom:none; }}
.item-head {{
  display:flex; align-items:center; gap:6px; margin-bottom:5px;
}}
.item-src {{
  font-size:11.5px; color:var(--muted); background:var(--border2);
  border-radius:4px; padding:2px 8px; font-weight:500;
}}
.item-title {{
  font-size:15.5px; font-weight:700; line-height:1.45; margin:0 0 5px;
}}
.item-title a {{ color:var(--ink); transition:color .15s; }}
.item-title a:hover {{ color:var(--accent); }}
.item-desc {{
  font-size:13.5px; color:var(--muted); margin:0; line-height:1.65;
}}

/* ---- Footer ---- */
.foot {{
  margin-top:36px; padding-top:16px; border-top:1px solid var(--line);
  color:var(--muted); font-size:12.5px;
  display:flex; flex-wrap:wrap; gap:6px 16px; justify-content:space-between;
}}
.foot a {{ color:var(--accent); font-weight:500; }}
.foot a:hover {{ text-decoration:underline; }}

/* ---- Responsive ---- */
@media (max-width:720px) {{
  .wrap {{ padding:0 12px 48px; }}
  .hero h1 {{ font-size:clamp(24px,7vw,32px); }}
  .toc {{ padding:12px 14px; }}
  .toc-sub {{ display:none; }}
  .tabs {{ gap:5px; margin-bottom:18px; }}
  .tab {{ padding:5px 11px; font-size:12.5px; }}
  .sec-head {{ gap:8px; padding-bottom:8px; margin-bottom:10px; }}
  .sec-name {{ font-size:15px; }}
  .sec-num {{ font-size:16px; }}
  .item {{ padding:11px 0; }}
  .item-title {{ font-size:14.5px; }}
  .item-desc {{ font-size:13px; }}
}}
@media (max-width:400px) {{
  .hero h1 {{ font-size:22px; }}
  .tab .tab-label-text {{ display:none; }}
  .toc-en {{ display:none; }}
}}
</style>
<script>try{{var _t=localStorage.getItem('wb_starhub_theme_v1')||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=_t;}}catch(e){{}}</script>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <a class="back" href="index.html">&larr; StarHub</a>
    <div class="spacer"></div>
    <button class="theme-btn" id="btnTheme" title="切换明暗主题" aria-label="切换主题">&#x1F313;</button>
  </div>

  <header class="hero">
    <div class="hero-vol">VOL.{date_human.replace("年",".").replace("月",".").replace("日","")} &middot; {total} STORIES &middot; AIHOT DAILY</div>
    <h1>AIHOT 日报</h1>
    <div class="hero-date">{date_human} &middot; DAILY &middot; 每早八时</div>
    <div class="hero-sub">{window_human}</div>
  </header>

  <div class="toc">
    <div class="toc-title">今日看点 <span class="tc">{total} 篇报道</span></div>
    {toc_items}
  </div>

  <nav class="tabs">{nav_tabs}</nav>

  <main>{sections_html}</main>

  <footer class="foot">
    <span>共 <strong>{total}</strong> 条 &middot; 数据源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener">AIHOT</a></span>
    <span>{date_human} &middot; 内容版权归原作者</span>
  </footer>
</div>
<script>
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){{
    var t=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{{localStorage.setItem('wb_starhub_theme_v1',t);}}catch(e){{}}
    document.documentElement.dataset.theme=t;
  }};
  var tabs=[...document.querySelectorAll('.tab')];
  var secs=[...document.querySelectorAll('.sec')];
  var obs=new IntersectionObserver(function(entries){{
    entries.forEach(function(e){{
      if(e.isIntersecting){{
        var id=e.target.id;
        tabs.forEach(function(t){{t.classList.toggle('active',t.getAttribute('data-target')===id);}});
      }}
    }});
  }},{{rootMargin:'-20% 0px -70% 0px'}});
  secs.forEach(function(s){{obs.observe(s);}});
  if(tabs.length) tabs[0].classList.add('active');
</script>
</body>
</html>"""


def main():
    now = _now_bj()
    date_human = f"{now.year}年{now.month}月{now.day}日 " + \
        ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    items = fetch_rss()
    if items:
        print("[AI晨报] RSS 拉取成功，共 %d 条" % len(items))
        items = _filter_24h(items)
        print("[AI晨报] 近 24h 筛选后 %d 条" % len(items))
    else:
        print("[AI晨报] RSS 失败，尝试本地 JSON 回退", file=sys.stderr)
        items = _fallback_json()
        if items:
            print("[AI晨报] JSON 回退成功，共 %d 条" % len(items))
        else:
            print("[AI晨报] 无可用数据源，跳过生成", file=sys.stderr)
            return False

    if not items:
        print("[AI晨报] 条目为空，跳过生成", file=sys.stderr)
        return False

    grouped = _group_by_cat(items)
    window_human = f"自动生成于 {now.strftime('%Y-%m-%d %H:%M')}（北京时间）"

    html_doc = build_html(grouped, date_human, window_human)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)

    total = sum(len(its) for _, its in grouped)
    print("[AI晨报] 生成完成 → %s（%d 条，%d 个分类）" % (OUT, total, len(grouped)))
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
