# -*- coding: utf-8 -*-
"""Generate ai-daily.html from AIHOT RSS feed (https://aihot.virxact.com/feed.xml).
仅依赖 Python 标准库。由 fetch_and_build.py 调用或独立运行。
每次构建自动拉取最新 RSS，筛选近 36 小时条目生成晨报。
页面风格：晨报编辑部（报纸式刊头 + 今日要闻头条区 + 双栏新闻流，冷绿强调色）。
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

# RSS 分类 → 配色
CAT_COLOR = {
    "AI 模型": "#2563eb",
    "AI 产品": "#7c3aed",
    "行业动态": "#0891b2",
    "论文": "#d97706",
    "技巧观点": "#dc2626",
}
# 分类排序权重（按此顺序展示）
CAT_ORDER = ["AI 模型", "AI 产品", "行业动态", "论文", "技巧观点"]

_ROMAN = ["", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
          "xi", "xii"]


def _now_bj():
    """北京时间 now。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def _roman(n):
    """分类编号：小写罗马数字（超出预置表用阿拉伯数字）。"""
    return _ROMAN[n] if 0 < n < len(_ROMAN) else str(n)


def _parse_rss_date(s):
    """解析 RSS pubDate（RFC 2822 格式）→ UTC datetime。"""
    s = s.strip()
    # 先处理 GMT → +0000（Windows 下 %z 不一定识别 GMT）
    s = s.replace(" GMT", " +0000")
    try:
        return datetime.datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        pass
    # 回退：无时区信息
    try:
        return datetime.datetime.strptime(s, "%a, %d %b %Y %H:%M:%S")
    except ValueError:
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


def _filter_today(items):
    """筛选今日日报条目：往前回溯 36 小时窗口。"""
    now = _now_bj()
    cutoff = now - datetime.timedelta(hours=36)
    out = []
    for it in items:
        if it["pub_date"] is None:
            continue  # 无法确定日期，跳过
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


def _item_html(it, top=False):
    """单条报道 HTML（晨报编辑部样式）。"""
    src = _esc(it["source"])
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


def build_html(grouped, date_human, window_human):
    """生成晨报编辑部风格 HTML 页面。"""
    total = sum(len(its) for _, its in grouped)

    # ---- 今日索引（报纸式编号导航条）----
    idx_items = ""
    for i, (cat, its) in enumerate(grouped, 1):
        color = CAT_COLOR.get(cat, "#57606a")
        idx_items += (
            f'<a href="#sec-{i}">'
            f'<span class="idx-n" style="color:{color}">{_roman(i)}</span>'
            f'{_esc(cat)}<span class="idx-cnt">{len(its)}</span>'
            f'</a>'
        )

    # ---- 分栏内容 ----
    sections_html = ""
    for i, (cat, its) in enumerate(grouped, 1):
        color = CAT_COLOR.get(cat, "#57606a")
        anchor = f"sec-{i}"
        # 列表项：每类第一条为"类内头条"（top 样式）
        items_html = ""
        for j, it in enumerate(its):
            items_html += _item_html(it, top=(j == 0))

        sections_html += (
            f'<section id="{anchor}" class="sec">'
            f'<div class="sec-head">'
            f'<span class="sec-num" style="color:{color}">{i:02d}</span>'
            f'<h2 class="sec-name">{_esc(cat)}</h2>'
            f'<span class="sec-cnt">{len(its)} 篇</span>'
            f'</div>'
            f'<div class="cols">{items_html}</div>'
            f'</section>'
        )

    # ---- 今日要闻头条区：行业动态第一条为大头条，其它类各取一条为次头条 ----
    gdict = dict(grouped)
    lead_main = gdict["行业动态"][0] if gdict.get("行业动态") else None
    lead_sides = []
    seen_links = set()
    if lead_main:
        seen_links.add(lead_main["link"])
    for cat in ("AI 模型", "AI 产品", "技巧观点", "论文"):
        if len(lead_sides) >= 2:
            break
        cand = gdict.get(cat) or []
        for c in cand:
            if c["link"] not in seen_links:
                lead_sides.append(c)
                seen_links.add(c["link"])
                break

    front_html = ""
    if lead_main:
        src = _esc(lead_main["source"])
        title = _esc(lead_main["title"])
        link = _esc(lead_main["link"])
        summary = _esc(lead_main["summary"])
        side_html = ""
        for it in lead_sides:
            side_html += (
                f'<article class="side-item">'
                f'<span class="side-src">{_esc(it["source"])}</span>'
                f'<h3><a href="{_esc(it["link"])}" target="_blank" rel="noopener">{_esc(it["title"])}</a></h3>'
                f'</article>'
            )
        front_html = (
            f'<section class="front" aria-label="今日要闻">'
            f'<div class="front-kicker">今日要闻 · TOP STORIES</div>'
            f'<div class="lead-row">'
            f'<article class="lead-main">'
            f'<span class="lead-src">{src}</span>'
            f'<h2><a href="{link}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<p>{summary}</p>'
            f'</article>'
            f'<div class="lead-side">{side_html}</div>'
            f'</div>'
            f'</section>'
        )

    date_vol = date_human.replace("年", ".").replace("月", ".").replace("日", "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>AIHOT 日报 · {date_human}</title>
<!-- font-stack: 中文衬线走系统 Songti/SimSun，数字走 Georgia（离线单文件，不引外部字体） -->
<style>
:root {{
  --bg:#faf8f4; --card:#fffdf9; --card-2:#f3efe6;
  --ink:#1f1c17; --muted:#6f6860; --faint:#857e74;
  --line:#e4ddd0; --line-strong:#b9b0a2;
  --accent:#30891A; --accent-ink:#256d13; --accent-weak:rgba(48,137,26,.08);
  --display:"Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}}
[data-theme="dark"] {{
  --bg:#101114; --card:#17191d; --card-2:#1d2026;
  --ink:#e9e6df; --muted:#a49c90; --faint:#7d776d;
  --line:#2a2d33; --line-strong:#4a4e57;
  --accent:#5bc23e; --accent-ink:#a3e88f; --accent-weak:rgba(91,194,62,.12);
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;scroll-padding-top:24px;}}
body{{
  font-family:var(--body);background:var(--bg);color:var(--ink);
  line-height:1.65;-webkit-font-smoothing:antialiased;font-size:15px;
}}
a{{color:inherit;text-decoration:none;}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px;}}
.paper{{max-width:980px;margin:0 auto;padding:0 20px 64px;}}

/* top bar */
.topbar{{display:flex;align-items:center;gap:10px;padding:14px 0 4px;}}
.back{{
  display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;
  background:var(--card);border:1px solid var(--line);font-size:13px;transition:all .15s;
}}
.back:hover{{border-color:var(--accent);color:var(--accent-ink);}}
.topbar .spacer{{flex:1;}}
.theme-btn{{
  width:36px;height:36px;border-radius:999px;background:var(--card);border:1px solid var(--line);
  display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--ink);
  transition:all .15s;
}}
.theme-btn:hover{{border-color:var(--accent);color:var(--accent-ink);}}
.theme-btn svg{{width:16px;height:16px;}}

/* masthead */
.masthead{{text-align:center;padding:26px 0 0;}}
.mast-rule{{display:flex;align-items:center;gap:14px;margin:0 0 4px;}}
.mast-rule::before,.mast-rule::after{{content:"";flex:1;height:1px;background:var(--line-strong);}}
.mast-meta{{font-size:11.5px;letter-spacing:.14em;color:var(--muted);font-weight:500;white-space:nowrap;}}
.mast-title{{
  font-family:var(--display);font-size:clamp(40px,7vw,58px);font-weight:700;
  letter-spacing:.06em;line-height:1.15;margin:6px 0 2px;
}}
.mast-title .tick{{color:var(--accent);}}
.mast-sub{{font-size:12.5px;color:var(--muted);letter-spacing:.1em;}}
.mast-strip{{
  margin-top:14px;padding:8px 12px;border-top:3px double var(--line-strong);border-bottom:1px solid var(--line-strong);
  font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 18px;justify-content:center;
}}
.mast-strip b{{color:var(--ink);font-weight:600;}}

/* index strip */
.index{{
  display:flex;flex-wrap:wrap;justify-content:center;gap:6px 22px;
  padding:14px 0 4px;font-size:13px;
}}
.index a{{color:var(--muted);transition:color .15s;display:inline-flex;gap:6px;align-items:baseline;}}
.index a:hover{{color:var(--accent-ink);}}
.index .idx-n{{font-family:var(--display);font-style:italic;font-size:12px;}}
.index .idx-cnt{{font-size:11px;color:var(--faint);}}

/* front page lead */
.front{{margin:22px 0 8px;border-top:4px solid var(--ink);border-bottom:1px solid var(--line-strong);padding:18px 0 20px;}}
.front-kicker{{
  font-size:11.5px;letter-spacing:.18em;color:var(--accent-ink);font-weight:700;margin-bottom:10px;
  display:flex;align-items:center;gap:10px;
}}
.front-kicker::after{{content:"";flex:1;height:1px;background:var(--line);}}
.lead-row{{display:grid;grid-template-columns:1.6fr 1fr;gap:26px;}}
.lead-main .lead-src{{font-size:11px;color:var(--muted);background:var(--card);border:1px solid var(--line);padding:2px 8px;border-radius:3px;display:inline-block;margin-bottom:10px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom;}}
.lead-main h2{{
  font-family:var(--display);font-size:clamp(24px,3.4vw,34px);font-weight:700;line-height:1.28;margin-bottom:10px;
}}
.lead-main h2 a:hover{{color:var(--accent-ink);}}
.lead-main p{{font-size:14px;color:var(--muted);}}
.lead-side{{display:flex;flex-direction:column;gap:14px;border-left:1px solid var(--line);padding-left:22px;}}
.lead-side .side-item{{padding-bottom:12px;border-bottom:1px solid var(--line);}}
.lead-side .side-item:last-child{{border-bottom:none;padding-bottom:0;}}
.side-item .side-src{{font-size:10.5px;color:var(--faint);display:block;margin-bottom:5px;letter-spacing:.04em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.side-item h3{{font-family:var(--display);font-size:17px;font-weight:700;line-height:1.4;}}
.side-item h3 a:hover{{color:var(--accent-ink);}}

/* sections */
.sec{{margin:34px 0 0;}}
.sec-head{{
  display:flex;align-items:baseline;gap:14px;padding-bottom:8px;
  border-bottom:3px double var(--line-strong);margin-bottom:16px;
}}
.sec-num{{font-size:18px;font-weight:800;flex:none;}}
.sec-name{{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:.04em;margin:0;line-height:1.3;}}
.sec-cnt{{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap;}}
.cols{{display:grid;grid-template-columns:1fr 1fr;column-gap:34px;row-gap:0;}}
.item{{
  padding:13px 0;border-bottom:1px solid var(--line);
  break-inside:avoid;
}}
.item-src{{
  font-size:10.5px;color:var(--faint);letter-spacing:.05em;display:block;margin-bottom:5px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}}
.item-title{{font-size:15px;font-weight:700;line-height:1.5;margin:0 0 4px;}}
.item-title a:hover{{color:var(--accent-ink);}}
.item-desc{{font-size:12.5px;color:var(--muted);line-height:1.6;}}
.item.top{{background:var(--card-2);border:1px solid var(--line);padding:12px 14px;}}
.item.top .item-title{{font-size:16px;}}

/* footer */
.foot{{
  margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px;justify-content:space-between;
}}
.foot a{{color:var(--accent-ink);font-weight:500;}}
.foot a:hover{{text-decoration:underline;}}

@media (max-width:760px){{
  .paper{{padding:0 14px 48px;}}
  .lead-row{{grid-template-columns:1fr;gap:16px;}}
  .lead-side{{border-left:none;padding-left:0;border-top:1px solid var(--line);padding-top:12px;}}
  .cols{{grid-template-columns:1fr;}}
  .mast-title{{letter-spacing:.03em;}}
  .index{{gap:6px 14px;}}
}}
@media (prefers-reduced-motion:reduce){{
  html{{scroll-behavior:auto;}}
  *{{transition:none!important;animation:none!important;}}
}}
</style>
<script>try{{var _t=localStorage.getItem('wb_starhub_theme_v1')||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=_t;}}catch(e){{}}</script>
</head>
<body>
<div class="paper">

  <div class="topbar">
    <a class="back" href="index.html">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>
      StarHub
    </a>
    <div class="spacer"></div>
    <button class="theme-btn" id="btnTheme" title="切换明暗主题" aria-label="切换明暗主题">
      <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M18.7 5.3 17 7M7 17l-1.7 1.7"/></svg>
      <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z"/></svg>
    </button>
  </div>

  <header class="masthead">
    <div class="mast-rule"><span class="mast-meta">{date_human}</span><span class="mast-meta">每早八时 · DAILY</span></div>
    <h1 class="mast-title">AIHOT<span class="tick"> · </span>日报</h1>
    <div class="mast-sub">VOL.{date_vol} &nbsp;·&nbsp; 今日 {total} 篇报道</div>
    <div class="mast-strip">
      <span>{window_human}</span>
      <span>数据源 <b>AIHOT</b> · 内容版权归原作者</span>
    </div>
  </header>

  <nav class="index" aria-label="今日分类索引">
    {idx_items}
  </nav>

  {front_html}

  <main>
    {sections_html}
  </main>

  <footer class="foot">
    <span>共 <strong>{total}</strong> 条 · 数据源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener">AIHOT</a></span>
    <span>{date_human} · 内容版权归原作者</span>
  </footer>
</div>

<script>
  var btn=document.getElementById('btnTheme');
  function syncIcons(){{
    var d=document.documentElement.dataset.theme==='dark';
    var sun=document.querySelector('.icon-sun'),moon=document.querySelector('.icon-moon');
    if(sun)sun.style.display=d?'none':'block';
    if(moon)moon.style.display=d?'block':'none';
  }}
  if(btn) btn.onclick=function(){{
    var t=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{{localStorage.setItem('wb_starhub_theme_v1',t);}}catch(e){{}}
    document.documentElement.dataset.theme=t;
    syncIcons();
  }};
  syncIcons();
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
        items = _filter_today(items)
        print("[AI晨报] 今日筛选后 %d 条" % len(items))
        if not items:
            # 今日无内容时回退展示全部（RSS 可能是前一天晚上更新的）
            print("[AI晨报] 今日无条目，回退展示全部精选", file=sys.stderr)
            items = fetch_rss()
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
