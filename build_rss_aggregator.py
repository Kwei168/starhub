# -*- coding: utf-8 -*-
"""Generate rss-aggregator.html — 多路 RSS 新闻源聚合页面。
构建时由 fetch_and_build.py 调用，Python 标准库抓取 RSS → 生成静态 HTML。
页面风格与 StarHub 主站一致（暖纸底 + 衬线标题 + 等宽数字）。
功能：按信源分组展示、信源筛选标签、全局搜索、响应式三端适配。
"""
import html as html_mod
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OUT = "rss-aggregator.html"

UA = {"User-Agent": "Mozilla/5.0 (starhub-auto-update)"}

# RSS 源配置
RSS_SOURCES = [
    {"key": "hn",       "name": "Hacker News",  "url": "https://hnrss.org/frontpage",                                    "color": "#ff6600", "icon": "Y"},
    {"key": "verge",    "name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "color": "#e31937", "icon": "V"},
    {"key": "tc",       "name": "TechCrunch AI","url": "https://techcrunch.com/category/artificial-intelligence/feed/",   "color": "#0a9e01", "icon": "T"},
    {"key": "arxiv",    "name": "arXiv",        "url": "https://rss.arxiv.org/rss/cs.AI",                                 "color": "#b31b1b", "icon": "X"},
    {"key": "kr36",     "name": "36\u6c2a",       "url": "https://rsshub.ktachibana.party/36kr/information/AI",             "color": "#0066ff", "icon": "36"},
    {"key": "redis",    "name": "Redis Blog",   "url": "https://redis.io/feed/",                                          "color": "#dc382d", "icon": "R"},
    {"key": "atlas",    "name": "AtlasNote",    "url": "https://atlasnote.ai/rss.xml",                                    "color": "#6366f1", "icon": "A"},
]

ITEMS_PER_SOURCE = 20


# ---------------------------- 工具函数 ----------------------------

def _now_bj():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def _esc(s):
    return html_mod.escape(str(s), quote=True)


def _strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


def _truncate(s, maxlen=150):
    if not s:
        return ""
    s = s.strip()
    if len(s) <= maxlen:
        return s
    cut = -1
    for i, ch in enumerate(s[:maxlen]):
        if ch in "\u3002\uff01\uff1f\uff1b":
            cut = i
    if cut >= 30:
        return s[:cut + 1]
    return s[:maxlen] + "\u2026"


def _parse_iso(s):
    s = (s or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(s[:19])
        except ValueError:
            return None


_RSS_MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
               "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

def _parse_rss_date(s):
    """RFC 822 日期 → datetime，失败返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    # "Mon, 01 Jan 2024 12:00:00 +0000"
    m = re.match(r"\w+,\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{2}:\d{2}:\d{2})\s*([+-]\d{4})?", s)
    if m:
        day, mon, year, timestr, tz = int(m.group(1)), _RSS_MONTHS.get(m.group(2), 1), int(m.group(3)), m.group(4), m.group(5) or "+0000"
        h, mi, sec = map(int, timestr.split(":"))
        tz_sign = 1 if tz[0] == "+" else -1
        tz_h, tz_m = int(tz[1:3]), int(tz[3:5])
        tz_offset = datetime.timedelta(hours=tz_sign * tz_h, minutes=tz_sign * tz_m)
        try:
            return datetime.datetime(year, mon, day, h, mi, sec, tzinfo=datetime.timezone(tz_offset))
        except ValueError:
            return None
    return _parse_iso(s)


def _fmt_rel_time(dt):
    """datetime → 相对时间字符串（北京时间）。"""
    if dt is None:
        return ""
    bj = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8))) if dt.tzinfo else dt
    now = _now_bj().replace(tzinfo=None) if bj.tzinfo else _now_bj()
    bj_naive = bj.replace(tzinfo=None)
    diff = now - bj_naive
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return bj_naive.strftime("%m-%d %H:%M")
    if seconds < 60:
        return "%d\u79d2\u524d" % seconds
    minutes = seconds // 60
    if minutes < 60:
        return "%d\u5206\u949f\u524d" % minutes
    hours = minutes // 60
    if hours < 24:
        return "%d\u5c0f\u65f6\u524d" % hours
    days = hours // 24
    if days < 30:
        return "%d\u5929\u524d" % days
    return bj_naive.strftime("%Y-%m-%d")


# ---------------------------- RSS 抓取 ----------------------------

def _fetch_url(url, timeout=15, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1000000).decode("utf-8", errors="replace")


def _fetch_rss(source):
    """抓取并解析单个 RSS 源，返回 items 列表。"""
    name = source["name"]
    url = source["url"]
    try:
        raw = _fetch_url(url, timeout=15, accept="application/rss+xml, application/xml, text/xml, application/atom+xml")
    except Exception as ex:
        print("[RSS\u805a\u5408] %s \u62c9\u53d6\u5931\u8d25: %s" % (name, ex), file=sys.stderr)
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as ex:
        print("[RSS\u805a\u5408] %s \u89e3\u6790\u5931\u8d25: %s" % (name, ex), file=sys.stderr)
        return []
    except Exception as ex:
        print("[RSS\u805a\u5408] %s \u5f02\u5e38: %s" % (name, ex), file=sys.stderr)
        return []

    items = []
    ns = "{http://www.w3.org/2005/Atom}"

    if root.tag.endswith("feed"):
        # Atom 格式
        for e in root.findall(ns + "entry"):
            title = _strip_html(e.findtext(ns + "title") or "")
            link_el = e.find(ns + "link")
            link = (link_el.get("href") if link_el is not None else (e.findtext(ns + "id") or "")).strip()
            desc = _truncate(_strip_html(e.findtext(ns + "summary") or e.findtext(ns + "content") or ""))
            pub = e.findtext(ns + "updated") or e.findtext(ns + "published") or ""
            if not title or not link:
                continue
            items.append({
                "title": title, "link": link, "summary": desc,
                "pub_date": _parse_iso(pub), "source": name, "source_key": source["key"],
            })
    else:
        # RSS 2.0 格式
        ch = root.find("channel")
        if ch is None:
            # 可能是 RSS 但无 channel 包裹
            for it in root.findall(".//item"):
                _parse_rss_item(it, name, source["key"], items)
        else:
            for it in ch.findall("item"):
                _parse_rss_item(it, name, source["key"], items)

    return items[:ITEMS_PER_SOURCE]


def _parse_rss_item(it, source_name, source_key, items):
    title = _strip_html(it.findtext("title") or "")
    link = (it.findtext("link") or "").strip()
    desc = _truncate(_strip_html(it.findtext("description") or ""))
    pub = (it.findtext("pubDate") or "").strip()
    if not title or not link:
        return
    items.append({
        "title": title, "link": link, "summary": desc,
        "pub_date": _parse_rss_date(pub), "source": source_name, "source_key": source_key,
    })


# ---------------------------- HTML 生成 ----------------------------

def _build_css():
    return """
:root {
  --bg:#faf8f4; --card:#fffdf9; --card-2:#f3efe6;
  --ink:#1f1c17; --muted:#6f6860; --faint:#857e74;
  --line:#e4ddd0; --line-strong:#b9b0a2;
  --brand:#8fb3d9; --brand-strong:#b0cbe6; --brand-line:#3d5a78; --brand-weak:#22303f;
  --accent-solid:#9db8d4;
  --display:"Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"SF Mono","Fira Code","Fira Mono","Roboto Mono","Consolas",monospace;
  --radius:10px;
  --shadow:0 1px 2px rgba(0,0,0,.06);
  --shadow-lift:0 8px 22px rgba(0,0,0,.1),0 1px 3px rgba(0,0,0,.06);
}
[data-theme="dark"] {
  --bg:#161412; --card:#1d1a17; --card-2:#262019;
  --ink:#ece7df; --muted:#a59d90; --faint:#8a8275;
  --line:#37312a; --line-strong:#4a4339;
  --brand:#8fb3d9; --brand-strong:#b0cbe6; --brand-line:#3d5a78; --brand-weak:#22303f;
  --accent-solid:#9db8d4;
  --shadow:0 1px 2px rgba(0,0,0,.4);
  --shadow-lift:0 8px 22px rgba(0,0,0,.5),0 1px 3px rgba(0,0,0,.4);
}
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
html { scroll-behavior:smooth; }
body {
  font-family:var(--body); background:var(--bg); color:var(--ink);
  line-height:1.55; -webkit-font-smoothing:antialiased; font-size:14px;
}
a { color:inherit; text-decoration:none; }
button { font-family:inherit; cursor:pointer; }

/* header */
header {
  position:sticky; top:0; z-index:50;
  background:rgba(250,248,244,.92);
  backdrop-filter:saturate(120%) blur(10px);
  -webkit-backdrop-filter:saturate(120%) blur(10px);
  border-bottom:1px solid var(--line);
}
[data-theme="dark"] header { background:rgba(22,20,18,.92); }
.hd {
  max-width:1200px; margin:0 auto; padding:10px 20px;
  display:flex; align-items:center; gap:16px;
}
.hd .logo {
  display:flex; align-items:center; gap:10px; flex:none;
  font-family:var(--display); font-weight:900; font-size:17px;
}
.hd .logo .t b { color:var(--ink); }
.hd .logo .t span { font-size:11px; color:var(--muted); font-weight:400; margin-left:4px; font-family:var(--body); }
.hd .nav-links { display:flex; align-items:center; gap:4px; flex:1; }
.hd .nav-links a {
  display:inline-flex; align-items:center; gap:6px;
  padding:6px 14px; border-radius:999px; font-size:13px; font-weight:500;
  border:1px solid transparent; transition:all .15s;
}
.hd .nav-links a:hover { background:var(--card); border-color:var(--line); }
.hd .nav-links a.active {
  background:var(--brand-weak); border-color:var(--brand-line); color:var(--brand-strong); font-weight:600;
}
.hd .nav-links a .icon { width:14px; height:14px; }
.hd .acts { display:flex; align-items:center; gap:6px; flex:none; }
.hd .acts .btn {
  width:34px; height:34px; border-radius:999px; background:var(--card); border:1px solid var(--line);
  display:flex; align-items:center; justify-content:center; color:var(--ink); transition:all .15s;
}
.hd .acts .btn:hover { border-color:var(--brand-line); color:var(--brand-strong); }
.hd .acts .btn svg { width:15px; height:15px; }

/* main layout */
.wrap { max-width:1200px; margin:0 auto; padding:20px 20px 64px; }

/* toolbar: source filters + search */
.toolbar {
  display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  margin-bottom:20px; padding-bottom:16px; border-bottom:1px solid var(--line);
}
.source-filters { display:flex; align-items:center; gap:6px; flex-wrap:wrap; flex:1; }
.source-tag {
  display:inline-flex; align-items:center; gap:5px;
  padding:5px 12px; border-radius:999px; font-size:12.5px; font-weight:500;
  border:1px solid var(--line); background:var(--card); color:var(--muted);
  transition:all .15s; cursor:pointer; user-select:none;
}
.source-tag:hover { border-color:var(--line-strong); color:var(--ink); }
.source-tag.on { color:#fff; border-color:transparent; }
.source-tag .dot { width:8px; height:8px; border-radius:50%; flex:none; }
.source-tag .cnt { font-family:var(--mono); font-size:11px; opacity:.7; }
.search-box {
  display:flex; align-items:center; gap:6px;
  padding:6px 14px; border-radius:999px; background:var(--card); border:1px solid var(--line);
  min-width:220px; transition:border-color .15s;
}
.search-box:focus-within { border-color:var(--brand-line); }
.search-box svg { width:14px; height:14px; color:var(--faint); flex:none; }
.search-box input {
  border:0; background:transparent; outline:none; font-size:13px; color:var(--ink);
  font-family:var(--body); width:160px;
}
.search-box input::placeholder { color:var(--faint); }

/* source sections */
.source-section { margin-bottom:28px; }
.source-header {
  display:flex; align-items:center; gap:10px; margin-bottom:12px;
  padding-bottom:8px; border-bottom:2px solid var(--line);
}
.source-icon {
  width:28px; height:28px; border-radius:6px; display:flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:12px; font-weight:700; color:#fff; flex:none;
}
.source-name {
  font-family:var(--display); font-size:18px; font-weight:700; letter-spacing:.02em;
}
.source-count { font-family:var(--mono); font-size:12px; color:var(--faint); margin-left:auto; }

/* item grid */
.item-grid {
  display:grid; grid-template-columns:repeat(3,1fr); gap:12px;
}
.item-card {
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 16px; transition:border-color .15s, box-shadow .2s;
  display:flex; flex-direction:column; gap:6px;
}
.item-card:hover { border-color:var(--brand-line); box-shadow:var(--shadow-lift); }
.item-title {
  font-size:14px; font-weight:600; line-height:1.4;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
}
.item-title a:hover { color:var(--brand-strong); }
.item-summary {
  font-size:12.5px; color:var(--muted); line-height:1.5;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
}
.item-meta {
  display:flex; align-items:center; gap:8px; margin-top:auto; padding-top:6px;
  border-top:1px solid var(--line); font-size:11.5px; color:var(--faint);
}
.item-meta .src-badge {
  display:inline-flex; align-items:center; gap:3px;
  padding:1px 7px; border-radius:999px; font-size:10.5px; font-weight:600; color:#fff;
}
.item-meta .time { font-family:var(--mono); margin-left:auto; white-space:nowrap; }

/* empty state */
.empty-state {
  text-align:center; padding:48px 20px; color:var(--faint);
}
.empty-state svg { width:40px; height:40px; margin-bottom:12px; opacity:.4; }
.empty-state b { display:block; font-size:15px; color:var(--muted); margin-bottom:4px; }

/* footer */
.footer {
  text-align:center; padding:24px 0; border-top:1px solid var(--line);
  font-size:12px; color:var(--faint); font-family:var(--mono);
}

/* responsive */
@media (max-width:1100px) {
  .item-grid { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:640px) {
  .hd { padding:10px 14px; flex-wrap:wrap; }
  .hd .nav-links { order:3; flex:1 1 100%; overflow-x:auto; padding:2px 0; }
  .wrap { padding:14px 12px 48px; }
  .item-grid { grid-template-columns:1fr; }
  .toolbar { flex-direction:column; align-items:stretch; }
  .search-box { min-width:auto; }
  .search-box input { width:100%; }
}
"""


def _build_header():
    return """
<header>
  <div class="hd">
    <a class="logo" href="index.html">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a7 7 0 0 1 14 0"/><path d="M4 11v4a2 2 0 0 0 2 2h1a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H4"/><path d="M18 11v4a2 2 0 0 1-2 2h-1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h3"/></svg>
      <div class="t"><b>StarHub</b><span>GitHub \u6536\u85cf\u53f0</span></div>
    </a>
    <nav class="nav-links">
      <a href="index.html"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> \u6536\u85cf\u6c60</a>
      <a href="ai-daily.html"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11a7 7 0 0 1 14 0"/><path d="M4 11v4a2 2 0 0 0 2 2h1a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H4"/><path d="M18 11v4a2 2 0 0 1-2 2h-1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h3"/></svg> AI \u6668\u62a5</a>
      <a href="rss-aggregator.html" class="active"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg> RSS \u805a\u5408</a>
    </nav>
    <div class="acts">
      <button class="btn" id="btnTheme" title="\u5207\u6362\u660e\u6697\u4e3b\u9898" aria-label="\u5207\u6362\u4e3b\u9898">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      </button>
    </div>
  </div>
</header>
"""


def _build_js(sources_data):
    """sources_data: list of {"key":..., "name":..., "color":...}"""
    src_json = json.dumps(sources_data, ensure_ascii=False)
    return """
<script>
// Theme toggle
(function(){
  var key='wb_starhub_theme_v1';
  var t=localStorage.getItem(key)||(window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.dataset.theme=t;
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){
    var nt=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{localStorage.setItem(key,nt);}catch(e){}
    document.documentElement.dataset.theme=nt;
  };
})();

// Source filter + search
(function(){
  var SOURCES = """ + src_json + """;
  var allCards = document.querySelectorAll('.item-card');
  var activeSources = new Set(SOURCES.map(function(s){return s.key;}));

  // Source tag click
  document.querySelectorAll('.source-tag').forEach(function(tag){
    tag.addEventListener('click', function(){
      var key = this.dataset.key;
      if(activeSources.has(key)){
        if(activeSources.size <= 1) return; // keep at least one
        activeSources.delete(key);
        this.classList.remove('on');
      } else {
        activeSources.add(key);
        this.classList.add('on');
      }
      applyFilters();
    });
  });

  // Search input
  var searchInput = document.getElementById('rssSearch');
  if(searchInput){
    searchInput.addEventListener('input', function(){ applyFilters(); });
  }

  function applyFilters(){
    var query = (searchInput ? searchInput.value : '').toLowerCase().trim();
    var anyVisible = false;
    allCards.forEach(function(card){
      var srcKey = card.dataset.source;
      var title = (card.dataset.title || '').toLowerCase();
      var summary = (card.dataset.summary || '').toLowerCase();
      var srcMatch = activeSources.has(srcKey);
      var searchMatch = !query || title.indexOf(query) >= 0 || summary.indexOf(query) >= 0;
      var show = srcMatch && searchMatch;
      card.style.display = show ? '' : 'none';
      if(show) anyVisible = true;
    });
    // Show/hide source sections
    document.querySelectorAll('.source-section').forEach(function(sec){
      var hasVisible = sec.querySelector('.item-card[style=""], .item-card:not([style])');
      // Check if any card in this section is visible
      var cards = sec.querySelectorAll('.item-card');
      var secVisible = false;
      cards.forEach(function(c){ if(c.style.display !== 'none') secVisible = true; });
      sec.style.display = secVisible ? '' : 'none';
    });
    // Empty state
    var empty = document.getElementById('rssEmpty');
    if(empty) empty.style.display = anyVisible ? 'none' : 'block';
  }
})();
</script>
"""


def build_html(all_items_by_source, build_time):
    """生成完整 HTML 页面。
    all_items_by_source: {source_key: [items]}
    """
    # Source metadata for JS
    sources_meta = []
    for src in RSS_SOURCES:
        items = all_items_by_source.get(src["key"], [])
        sources_meta.append({"key": src["key"], "name": src["name"], "color": src["color"], "count": len(items)})

    # Source filter tags
    tags_html = ""
    for src in RSS_SOURCES:
        items = all_items_by_source.get(src["key"], [])
        tags_html += (
            '<button class="source-tag on" data-key="%s" style="--tag-color:%s">'
            '<span class="dot" style="background:%s"></span>%s'
            '<span class="cnt">%d</span></button>'
            % (_esc(src["key"]), src["color"], src["color"], _esc(src["name"]), len(items))
        )

    # Source sections with items
    sections_html = ""
    total_items = 0
    for src in RSS_SOURCES:
        items = all_items_by_source.get(src["key"], [])
        if not items:
            continue
        total_items += len(items)
        items_html = ""
        for it in items:
            title = _esc(it["title"])
            link = _esc(it["link"])
            summary = _esc(it.get("summary", ""))
            time_str = _fmt_rel_time(it.get("pub_date"))
            items_html += (
                '<article class="item-card" data-source="%s" data-title="%s" data-summary="%s">'
                '<div class="item-title"><a href="%s" target="_blank" rel="noopener">%s</a></div>'
                '%s'
                '<div class="item-meta">'
                '<span class="src-badge" style="background:%s">%s</span>'
                '<span class="time">%s</span>'
                '</div></article>'
                % (
                    _esc(src["key"]),
                    title, summary,
                    link, title,
                    ('<div class="item-summary">%s</div>' % summary) if summary else '',
                    src["color"], _esc(src["name"]),
                    time_str,
                )
            )

        sections_html += (
            '<section class="source-section" data-source="%s">'
            '<div class="source-header">'
            '<span class="source-icon" style="background:%s">%s</span>'
            '<h2 class="source-name">%s</h2>'
            '<span class="source-count">%d \u7bc7</span>'
            '</div>'
            '<div class="item-grid">%s</div>'
            '</section>'
            % (_esc(src["key"]), src["color"], _esc(src["icon"]), _esc(src["name"]), len(items), items_html)
        )

    if not sections_html:
        sections_html = (
            '<div class="empty-state" id="rssEmpty">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>'
            '<b>\u6682\u65e0 RSS \u5185\u5bb9</b>'
            '<span>\u4fe1\u6e90\u62c9\u53d6\u5931\u8d25\u6216\u6682\u65e0\u66f4\u65b0\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5</span>'
            '</div>'
        )
    else:
        sections_html += '<div class="empty-state" id="rssEmpty" style="display:none"><b>\u6ca1\u6709\u5339\u914d\u7684\u5185\u5bb9</b><span>\u8bd5\u8bd5\u6362\u4e00\u4e2a\u5173\u952e\u8bcd\u6216\u4fe1\u6e90</span></div>'

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<title>RSS \u805a\u5408 \u00b7 StarHub</title>\n'
        '<style>' + _build_css() + '</style>\n'
        '</head>\n<body>\n'
        + _build_header() +
        '<div class="wrap">\n'
        '<div class="toolbar">\n'
        '<div class="source-filters">' + tags_html + '</div>\n'
        '<div class="search-box">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
        '<input id="rssSearch" type="search" placeholder="\u641c\u7d22\u6807\u9898\u548c\u6458\u8981\u2026" autocomplete="off">'
        '</div>\n'
        '</div>\n'
        + sections_html +
        '<div class="footer">\u81ea\u52a8\u751f\u6210\u4e8e ' + _esc(build_time) + ' \uff08\u5317\u4eac\u65f6\u95f4\uff09\u00b7 \u5171 ' + str(total_items) + ' \u7bc7\u00b7 StarHub RSS Aggregator</div>\n'
        '</div>\n'
        + _build_js(sources_meta) +
        '</body>\n</html>'
    )


# ---------------------------- Main ----------------------------

def main():
    now = _now_bj()
    build_time = now.strftime("%Y-%m-%d %H:%M")

    all_items = {}
    total = 0
    ok_count = 0

    for src in RSS_SOURCES:
        items = _fetch_rss(src)
        all_items[src["key"]] = items
        n = len(items)
        total += n
        if n > 0:
            ok_count += 1
        print("[RSS\u805a\u5408] %s: %d \u6761" % (src["name"], n))

    if total == 0:
        print("[RSS\u805a\u5408] \u6240\u6709\u6e90\u5747\u5931\u8d25\uff0c\u751f\u6210\u7a7a\u9875\u9762", file=sys.stderr)

    html_doc = build_html(all_items, build_time)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)

    print("[RSS\u805a\u5408] \u751f\u6210\u5b8c\u6210 \u2192 %s\uff08%d \u6e90\u6210\u529f\uff0c\u5171 %d \u7bc7\uff09" % (OUT, ok_count, total))
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
