# -*- coding: utf-8 -*-
"""Generate ai-daily.html from AIHOT RSS feed (https://aihot.virxact.com/feed.xml).
仅依赖 Python 标准库。由 fetch_and_build.py 调用或独立运行。
每次构建自动拉取最新 RSS，筛选近 24 小时条目生成晨报。
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

# RSS 分类 → 图标 & 配色
CAT_STYLE = {
    "AI 模型":   ("🧠", "#2563eb"),
    "AI 产品":   ("🚀", "#7c3aed"),
    "行业动态":   ("🌐", "#0891b2"),
    "论文":      ("📄", "#d97706"),
    "技巧观点":   ("💡", "#dc2626"),
}
# 分类排序权重（按此顺序展示）
CAT_ORDER = ["AI 模型", "AI 产品", "行业动态", "论文", "技巧观点"]


def _now_bj():
    """北京时间 now。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def _parse_rss_date(s):
    """解析 RSS pubDate（RFC 2822 格式）→ UTC datetime。"""
    # 例: "Thu, 27 Aug 2026 00:20:11 GMT"
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 手动处理 GMT
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
    """从 RSS author 字段提取来源名。
    格式: 'noreply@aihot.virxact.com (IT之家（RSS）)' → 'IT之家（RSS）'"""
    m = re.search(r"\(([^)]+)\)", author_text or "")
    return m.group(1) if m else ""


def _truncate(s, maxlen=80):
    if not s:
        return "（暂无摘要）"
    s = s.strip()
    if len(s) <= maxlen:
        return s
    cut = -1
    for i, ch in enumerate(s[:maxlen]):
        if ch in "。！？；":
            cut = i
    if cut >= 20:
        return s[:cut + 1] + "…"
    return s[:maxlen] + "…"


def _esc(s):
    return html_mod.escape(str(s), quote=True)


def fetch_rss():
    """拉取 AIHOT RSS feed，返回 (items, pub_dates) 或 None。
    items: list of dict {title, link, category, source, summary, pub_date}
    """
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
        # 安全解析：禁止外部实体，限制大小
        # Python 3.8+ ET 默认不展开外部实体，此处额外限制读取量防止资源耗尽
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
            # JSON 分类映射到 RSS 分类名
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
    cutoff = now - datetime.timedelta(hours=28)  # 宽松 28h 覆盖跨日
    out = []
    for it in items:
        if it["pub_date"] is None:
            out.append(it)  # 无日期信息的全部保留
            continue
        # 统一为北京时间
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
    # 剩余未映射分类
    for cat, its in groups.items():
        result.append((cat, its))
    return result


def build_html(grouped, date_human, window_human):
    """生成完整 HTML 页面。"""
    total = sum(len(its) for _, its in grouped)

    # 统计条
    stat_chips = ""
    for cat, its in grouped:
        icon, color = CAT_STYLE.get(cat, ("📌", "#57606a"))
        stat_chips += (
            f'<div class="stat" style="--c:{color}">'
            f'<div class="stat-num">{len(its)}</div>'
            f'<div class="stat-label">{_esc(cat)}</div></div>'
        )

    # 导航
    nav_links = ""
    sections_html = ""
    for i, (cat, its) in enumerate(grouped, 1):
        icon, color = CAT_STYLE.get(cat, ("📌", "#57606a"))
        anchor = f"sec-{i}"
        nav_links += (
            f'<a class="nav-item" href="#{anchor}" style="--c:{color}">'
            f'<span class="nav-ico">{icon}</span>'
            f'<span class="nav-label">{_esc(cat)}</span>'
            f'<span class="nav-badge">{len(its)}</span></a>'
        )
        cards_html = ""
        for j, it in enumerate(its, 1):
            cards_html += f"""
        <article class="card" style="--c:{color}">
          <div class="card-top">
            <span class="num">{j:02d}</span>
            <span class="chip">{_esc(it['source'])}</span>
          </div>
          <h3 class="card-title"><a href="{_esc(it['link'])}" target="_blank" rel="noopener noreferrer">{_esc(it['title'])}</a></h3>
          <p class="card-sum">{_esc(it['summary'])}</p>
          <a class="card-link" href="{_esc(it['link'])}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a>
        </article>"""
        sections_html += f"""
    <section id="{anchor}" class="sec">
      <h2 class="sec-title"><span class="sec-ico" style="background:{color}">{icon}</span>{_esc(cat)}<span class="sec-count">{len(its)} 条</span></h2>
      <div class="grid">{cards_html}</div>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>AI 晨报 · {date_human}</title>
<style>
:root {{
  --bg:#f6f7fb; --panel:#ffffff; --ink:#0f172a; --muted:#64748b;
  --line:#e6e8ef; --accent:#2563eb;
}}
[data-theme="dark"] {{
  --bg:#0d1117; --panel:#161b22; --ink:#e6edf3; --muted:#9198a1;
  --line:#30363d; --accent:#3b82f6;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:linear-gradient(180deg,#eef2ff 0%,#f6f7fb 240px); color:var(--ink); line-height:1.6; -webkit-font-smoothing:antialiased;
}}
[data-theme="dark"] body {{ background:linear-gradient(180deg,#0d1117 0%,#0d1117 240px); }}
a {{ color:inherit; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:0 20px 64px; }}

/* Header bar */
.topbar {{
  display:flex; align-items:center; gap:10px; padding:12px 0; margin-bottom:8px;
}}
.topbar .back {{
  display:inline-flex; align-items:center; gap:6px; padding:6px 14px;
  border-radius:8px; background:var(--panel); border:1px solid var(--line);
  font-size:13px; color:var(--ink); text-decoration:none; transition:.15s;
}}
.topbar .back:hover {{ border-color:var(--accent); color:var(--accent); }}
.topbar .spacer {{ flex:1; }}
.topbar .theme-btn {{
  width:36px; height:36px; border-radius:8px; background:var(--panel);
  border:1px solid var(--line); display:flex; align-items:center; justify-content:center;
  cursor:pointer; font-size:16px; transition:.15s;
}}
.topbar .theme-btn:hover {{ border-color:var(--accent); }}

/* Hero */
.hero {{ padding:10px 0 26px; }}
.kicker {{ display:inline-flex; align-items:center; gap:8px; font-size:13px; color:var(--accent); font-weight:700; letter-spacing:.04em; }}
.kicker .dot {{ width:8px; height:8px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 4px rgba(37,99,235,.15); }}
.hero h1 {{ font-size:clamp(28px,5vw,44px); margin:10px 0 6px; letter-spacing:-.02em; }}
.hero .date {{ font-size:clamp(17px,3vw,22px); font-weight:700; color:var(--ink); }}
.hero .window {{ color:var(--muted); font-size:14px; margin-top:4px; }}
.stats {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-top:24px; }}
.stat {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:14px 10px; text-align:center; border-top:3px solid var(--c); }}
.stat:first-child {{ grid-column:span 2; }}
.stat-num {{ font-size:26px; font-weight:800; color:var(--c); line-height:1; }}
.stat-label {{ font-size:12.5px; color:var(--muted); margin-top:6px; white-space:nowrap; }}

/* Nav */
.nav {{ position:sticky; top:0; z-index:20; background:rgba(246,247,251,.85); backdrop-filter:blur(10px);
       border-bottom:1px solid var(--line); margin:0 -20px 28px; padding:10px 20px; display:flex; gap:8px; flex-wrap:wrap; }}
[data-theme="dark"] .nav {{ background:rgba(13,17,23,.85); }}
.nav-item {{ display:inline-flex; align-items:center; gap:7px; text-decoration:none; padding:7px 12px; border-radius:999px;
             background:var(--panel); border:1px solid var(--line); font-size:13.5px; color:var(--ink); transition:.15s; }}
.nav-item:hover {{ border-color:var(--c); transform:translateY(-1px); }}
.nav-ico {{ font-size:14px; }}
.nav-badge {{ background:var(--c); color:#fff; border-radius:999px; font-size:11px; font-weight:700; padding:1px 7px; }}

/* Sections & cards */
.sec {{ margin-bottom:40px; scroll-margin-top:64px; }}
.sec-title {{ display:flex; align-items:center; gap:12px; font-size:21px; margin:0 0 16px; }}
.sec-ico {{ width:34px; height:34px; border-radius:10px; display:inline-flex; align-items:center; justify-content:center; font-size:17px; }}
.sec-count {{ margin-left:auto; font-size:13px; color:var(--muted); font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px; display:flex; flex-direction:column; gap:10px;
         transition:.18s; border-left:4px solid var(--c); }}
.card:hover {{ box-shadow:0 10px 30px rgba(15,23,42,.08); transform:translateY(-2px); }}
[data-theme="dark"] .card:hover {{ box-shadow:0 10px 30px rgba(0,0,0,.3); }}
.card-top {{ display:flex; align-items:center; gap:10px; }}
.num {{ font-size:13px; font-weight:800; color:var(--c); background:color-mix(in srgb,var(--c) 12%,transparent); border-radius:8px; padding:2px 8px; min-width:30px; text-align:center; }}
.chip {{ font-size:12px; color:var(--muted); background:var(--line); border-radius:999px; padding:3px 10px; margin-left:auto; max-width:70%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.card-title {{ font-size:16.5px; margin:0; font-weight:700; line-height:1.4; }}
.card-title a {{ text-decoration:none; }}
.card-title a:hover {{ color:var(--c); }}
.card-sum {{ font-size:14px; color:var(--muted); margin:0; flex:1; }}
.card-link {{ align-self:flex-start; font-size:13px; font-weight:600; color:var(--c); text-decoration:none; border:1px solid var(--c); border-radius:8px; padding:5px 12px; transition:.15s; }}
.card-link:hover {{ background:var(--c); color:#fff; }}

/* Footer */
.foot {{ margin-top:30px; padding-top:20px; border-top:1px solid var(--line); color:var(--muted); font-size:13.5px; display:flex; flex-wrap:wrap; gap:8px 18px; justify-content:space-between; }}
.foot a {{ color:var(--accent); text-decoration:none; }}

/* Responsive */
@media (max-width:720px) {{
  .stats {{ grid-template-columns:repeat(3,1fr); }}
  .stat:first-child {{ grid-column:span 3; }}
  .grid {{ grid-template-columns:1fr; }}
  .wrap {{ padding:0 14px 48px; }}
  .nav {{ margin:0 -14px 20px; padding:8px 14px; gap:6px; }}
  .nav-item {{ padding:6px 10px; font-size:12.5px; }}
  .sec-title {{ font-size:18px; }}
  .card {{ padding:14px; }}
  .card-title {{ font-size:15px; }}
  .hero h1 {{ font-size:clamp(24px,6vw,36px); }}
}}
@media (max-width:400px) {{
  .stats {{ grid-template-columns:repeat(2,1fr); }}
  .stat:first-child {{ grid-column:span 2; }}
  .nav-item .nav-label {{ display:none; }}
}}
</style>
<script>try{{var _t=localStorage.getItem('wb_starhub_theme_v1')||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=_t;}}catch(e){{}}</script>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <a class="back" href="index.html">← 返回 StarHub</a>
    <div class="spacer"></div>
    <button class="theme-btn" id="btnTheme" title="切换明暗主题" aria-label="切换主题">🌓</button>
  </div>

  <header class="hero">
    <span class="kicker"><span class="dot"></span>AIHOT 每日精选 · AI 晨报</span>
    <h1>AI 晨报</h1>
    <div class="date">{date_human}</div>
    <div class="window">{window_human}</div>
    <div class="stats">
      <div class="stat" style="--c:var(--accent)"><div class="stat-num">{total}</div><div class="stat-label">今日总条数</div></div>
      {stat_chips}
    </div>
  </header>

  <nav class="nav">{nav_links}</nav>

  <main>{sections_html}</main>

  <footer class="foot">
    <span>共 <strong>{total}</strong> 条 · 数据源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener noreferrer">AIHOT</a></span>
    <span>本期：{date_human} · 内容版权归原作者</span>
  </footer>
</div>
<script>
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){{
    var t=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{{localStorage.setItem('wb_starhub_theme_v1',t);}}catch(e){{}}
    document.documentElement.dataset.theme=t;
  }};
  var navItems=[...document.querySelectorAll('.nav-item')];
  var secs=[...document.querySelectorAll('.sec')];
  var obs=new IntersectionObserver(function(entries){{
    entries.forEach(function(e){{
      if(e.isIntersecting){{
        var id=e.target.id;
        navItems.forEach(function(n){{n.style.fontWeight=n.getAttribute('href')==='#'+id?'800':'400';}});
      }}
    }});
  }},{{rootMargin:'-40% 0px -55% 0px'}});
  secs.forEach(function(s){{obs.observe(s);}});
</script>
</body>
</html>"""


def main():
    now = _now_bj()
    date_human = f"{now.year}年{now.month}月{now.day}日 " + \
        ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    # 1. 拉取 RSS
    items = fetch_rss()
    if items:
        print("[AI晨报] RSS 拉取成功，共 %d 条" % len(items))
        # 筛选近 24h
        items = _filter_24h(items)
        print("[AI晨报] 近 24h 筛选后 %d 条" % len(items))
    else:
        # 2. 回退到本地 JSON
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

    # 分组
    grouped = _group_by_cat(items)

    # 时间窗口
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
