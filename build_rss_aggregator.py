# -*- coding: utf-8 -*-
"""Generate rss-aggregator.html — 多路 RSS 新闻源聚合阅读器。
构建时由 fetch_and_build.py 调用，Python 标准库抓取 RSS → 翻译 → 生成静态 HTML。

布局：三栏式阅读器（信源侧栏 | 文章列表 | 阅读区）
功能：信源分类筛选、全局搜索、标题/摘要翻译、响应式三端适配、主题切换。
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
UA = {"User-Agent": "Mozilla/5.0 (starhub-rss-aggregator)"}

# ── 翻译统计 ──
_TRANS_STATS = {"google": 0, "bing": 0, "mymemory": 0, "dict": 0, "skip": 0, "fail": 0}

# ── RSS 信源配置（按分类组织，73 个经验证可用源） ─
RSS_SOURCES = [
    # ── 科技资讯 (4) ──
    {"key": "verge",   "name": "The Verge AI",    "cat": "tech",    "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",     "color": "#e31937"},
    {"key": "tc",      "name": "TechCrunch AI",   "cat": "tech",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/",         "color": "#0a9e01"},
    {"key": "arxiv",   "name": "arXiv CS.AI",     "cat": "tech",    "url": "https://rss.arxiv.org/rss/cs.AI",                                       "color": "#b31b1b"},
    {"key": "wired",   "name": "WIRED",           "cat": "tech",    "url": "https://www.wired.com/feed/rss",                                        "color": "#000000"},

    # ── 中文科技 (28) ──
    {"key": "kr36",     "name": "36氪",            "cat": "cn_tech", "url": "https://rsshub.ktachibana.party/36kr/information/AI",                   "color": "#0066ff"},
    {"key": "ithome",   "name": "IT之家",           "cat": "cn_tech", "url": "https://www.ithome.com/rss/",                                          "color": "#0055ff"},
    {"key": "sspai",    "name": "少数派",           "cat": "cn_tech", "url": "https://sspai.com/feed",                                               "color": "#d7434e"},
    {"key": "solidot",  "name": "Solidot",         "cat": "cn_tech", "url": "https://www.solidot.org/index.rss",                                     "color": "#336699"},
    {"key": "coolshell","name": "酷壳",            "cat": "cn_tech", "url": "https://coolshell.cn/feed",                                             "color": "#333333"},
    {"key": "ruanyifeng","name": "阮一峰网络日志",  "cat": "cn_tech", "url": "https://www.ruanyifeng.com/blog/atom.xml",                             "color": "#4a90d9"},
    {"key": "geekpark", "name": "极客公园",        "cat": "cn_tech", "url": "https://plink.anyfeeder.com/geekpark",                                  "color": "#00aa55"},
    {"key": "huxiu",    "name": "虎嗅",            "cat": "cn_tech", "url": "https://rss.huxiu.com/",                                                "color": "#1a1a1a"},
    {"key": "tmtpost",  "name": "钛媒体",          "cat": "cn_tech", "url": "https://www.tmtpost.com/feed",                                          "color": "#0066cc"},
    {"key": "meituan",  "name": "美团技术团队",     "cat": "cn_tech", "url": "https://tech.meituan.com/feed",                                         "color": "#FFD43B"},
    {"key": "ifanr",    "name": "爱范儿",          "cat": "cn_tech", "url": "https://www.ifanr.com/feed",                                            "color": "#00bc74"},
    {"key": "gcores",   "name": "机核",            "cat": "cn_tech", "url": "https://www.gcores.com/rss",                                            "color": "#e2363e"},
    {"key": "iplaysoft", "name": "异次元软件世界", "cat": "cn_tech", "url": "https://feed.iplaysoft.com",                                            "color": "#3a85ff"},
    {"key": "appinn",   "name": "小众软件",         "cat": "cn_tech", "url": "https://www.appinn.com/feed/",                                         "color": "#3177cf"},
    {"key": "williamlong","name":"月光博客",        "cat": "cn_tech", "url": "http://www.williamlong.info/rss.xml",                                   "color": "#1e88e5"},
    {"key": "tw93",     "name": "潮流周刊",         "cat": "cn_tech", "url": "https://weekly.tw93.fun/rss.xml",                                       "color": "#000000"},
    {"key": "zhangxinxu","name":"张鑫旭",          "cat": "cn_tech", "url": "https://www.zhangxinxu.com/wordpress/feed/",                            "color": "#2c7fb8"},
    {"key": "yystv",    "name": "游戏研究社",       "cat": "cn_tech", "url": "https://www.yystv.cn/rss/feed",                                         "color": "#e53935"},
    {"key": "toodaylab", "name": "理想生活实验室",  "cat": "cn_tech", "url": "https://www.toodaylab.com/feed",                                        "color": "#ff6f00"},
    {"key": "kawabangga","name": "卡瓦邦噶",        "cat": "cn_tech", "url": "https://www.kawabangga.com/feed",                                       "color": "#e91e63"},
    {"key": "leavesongs","name": "离别歌",          "cat": "cn_tech", "url": "https://www.leavesongs.com/feed/",                                      "color": "#43a047"},
    {"key": "t9t",      "name": "透明创业实验",     "cat": "cn_tech", "url": "https://blog.t9t.io/atom.xml",                                          "color": "#333333"},
    {"key": "codingnow","name": "云风的BLOG",       "cat": "cn_tech", "url": "http://blog.codingnow.com/atom.xml",                                    "color": "#5c6bc0"},
    {"key": "bmpi",     "name": "构建我的被动收入", "cat": "cn_tech", "url": "https://www.bmpi.dev/index.xml",                                        "color": "#00897b"},
    {"key": "eryajf",   "name": "二丫讲梵",         "cat": "cn_tech", "url": "https://wiki.eryajf.net/rss.xml",                                       "color": "#ff5722"},
    {"key": "phodal",   "name": "全栈应用开发",     "cat": "cn_tech", "url": "https://www.phodal.com/blog/feeds/rss/",                                "color": "#1565c0"},
    {"key": "runningcheese","name":"奔跑中的奶酪",  "cat": "cn_tech", "url": "https://www.runningcheese.com/feed",                                   "color": "#ff9800"},
    {"key": "changhai","name": "卢昌海",           "cat": "cn_tech", "url": "https://www.changhai.org/feed.xml",                                     "color": "#795548"},
    {"key": "crazycap", "name": "疯投圈",          "cat": "cn_tech", "url": "https://crazy.capital/feed",                                           "color": "#6a1b9a"},
    {"key": "cnbeta",   "name": "cnBeta",          "cat": "cn_tech", "url": "https://plink.anyfeeder.com/cnbeta",                                    "color": "#d32f2f"},
    {"key": "expreview", "name": "超能网",          "cat": "cn_tech", "url": "https://plink.anyfeeder.com/expreview",                                 "color": "#0288d1"},
    {"key": "leiphone", "name": "雷峰网",          "cat": "cn_tech", "url": "https://plink.anyfeeder.com/leiphone",                                  "color": "#0097a7"},
    {"key": "mittr",    "name": "MIT科技评论",      "cat": "cn_tech", "url": "https://plink.anyfeeder.com/mittrchina/hot",                            "color": "#c62828"},
    {"key": "infoq",    "name": "InfoQ推荐",        "cat": "cn_tech", "url": "https://plink.anyfeeder.com/infoq/recommend",                           "color": "#e65100"},
    {"key": "woshipm",  "name": "人人都是产品经理", "cat": "cn_tech", "url": "https://www.woshipm.com/feed",                                         "color": "#0091ea"},

    # ── 开发者博客 (20) ──
    {"key": "redis",    "name": "Redis Blog",      "cat": "dev",     "url": "https://redis.io/feed/",                                               "color": "#dc382d"},
    {"key": "atlas",    "name": "AtlasNote",       "cat": "dev",     "url": "https://atlasnote.ai/rss.xml",                                          "color": "#6366f1"},
    {"key": "css",      "name": "CSS-Tricks",      "cat": "dev",     "url": "https://css-tricks.com/feed/",                                          "color": "#e34f26"},
    {"key": "overreacted","name":"Overreacted",    "cat": "dev",     "url": "https://overreacted.io/rss.xml",                                        "color": "#663399"},
    {"key": "antfu",    "name": "Anthony Fu",      "cat": "dev",     "url": "https://antfu.me/feed.xml",                                             "color": "#336699"},
    {"key": "hellogithub","name":"HelloGitHub",    "cat": "dev",     "url": "http://hellogithub.com/rss",                                            "color": "#4CAF50"},
    {"key": "jvns",     "name": "Julia Evans",     "cat": "dev",     "url": "https://jvns.ca/atom.xml",                                              "color": "#8e44ad"},
    {"key": "joshcomeau","name":"Josh Comeau",     "cat": "dev",     "url": "https://www.joshwcomeau.com/rss.xml",                                   "color": "#6c5ce7"},
    {"key": "tonybai",  "name": "Tony Bai",        "cat": "dev",     "url": "http://tonybai.com/feed/",                                              "color": "#2d3436"},
    {"key": "uisdc",    "name": "优设",            "cat": "dev",     "url": "http://www.uisdc.com/feed",                                             "color": "#e74c3c"},
    {"key": "anywayfm", "name": "Anyway.FM",       "cat": "dev",     "url": "https://anyway.fm/rss.xml",                                             "color": "#00b894"},
    {"key": "cnfeat",   "name": "笨方法学写作",     "cat": "dev",     "url": "https://www.cnfeat.com/feed.xml",                                       "color": "#2c3e50"},
    {"key": "barretlee","name": "小胡子哥",        "cat": "dev",     "url": "http://www.barretlee.com/rss2.xml",                                     "color": "#e67e22"},
    {"key": "devtang",  "name": "唐巧博客",         "cat": "dev",     "url": "http://blog.devtang.com/atom.xml",                                      "color": "#3498db"},
    {"key": "dongwm",   "name": "小明明s",         "cat": "dev",     "url": "https://www.dongwm.com/atom.xml",                                       "color": "#1abc9c"},
    {"key": "xiqin",    "name": "西秦公子",         "cat": "dev",     "url": "https://www.ixiqin.com/feed/",                                          "color": "#9b59b6"},
    {"key": "taoshu",   "name": "涛叔",            "cat": "dev",     "url": "https://taoshu.in/feed.xml",                                            "color": "#34495e"},
    {"key": "geekplux", "name": "GeekPlux",        "cat": "dev",     "url": "https://geekplux.com/feed.xml",                                         "color": "#16a085"},
    {"key": "ezindie",  "name": "ezindie",         "cat": "dev",     "url": "https://www.ezindie.com/feed/rss.xml",                                  "color": "#f39c12"},
    {"key": "v2extech", "name": "V2EX技术",         "cat": "dev",     "url": "https://www.v2ex.com/feed/tab/tech.xml",                                "color": "#4a90d9"},

    # ── 综合新闻 (9) ──
    {"key": "bbc",      "name": "BBC 中文",        "cat": "news",    "url": "https://plink.anyfeeder.com/bbc/cn",                                    "color": "#bb1919"},
    {"key": "rfi",      "name": "法广中文",        "cat": "news",    "url": "https://plink.anyfeeder.com/rfi/cn",                                    "color": "#0066b3"},
    {"key": "nyt",      "name": "纽约时报中文",    "cat": "news",    "url": "https://plink.anyfeeder.com/nytimes/cn",                                "color": "#1a1a1a"},
    {"key": "zaobao",   "name": "联合早报",        "cat": "news",    "url": "https://plink.anyfeeder.com/zaobao/realtime/china",                     "color": "#003399"},
    {"key": "chinadaily","name":"中国日报双语",    "cat": "news",    "url": "https://plink.anyfeeder.com/chinadaily/dual",                           "color": "#cc0000"},
    {"key": "thepaper", "name": "澎湃新闻",        "cat": "news",    "url": "https://plink.anyfeeder.com/thepaper",                                  "color": "#d32f2f"},
    {"key": "idaily",   "name": "iDaily",          "cat": "news",    "url": "https://plink.anyfeeder.com/idaily/today",                              "color": "#1565c0"},
    {"key": "abccn",    "name": "SBS澳洲中文",     "cat": "news",    "url": "https://plink.anyfeeder.com/abc/cn",                                    "color": "#0055a4"},
    {"key": "zhihudaily","name":"知乎日报",        "cat": "news",    "url": "https://plink.anyfeeder.com/zhihu/daily",                               "color": "#0084ff"},

    # ── 播客 (7) ──
    {"key": "sv101",    "name": "硅谷101",         "cat": "podcast", "url": "https://feeds.fireside.fm/sv101/rss",                                   "color": "#7c3aed"},
    {"key": "latetalk", "name": "晚点聊 LateTalk", "cat": "podcast", "url": "https://feeds.fireside.fm/latetalk/rss",                                "color": "#0891b2"},
    {"key": "42sec",    "name": "42章经",          "cat": "podcast", "url": "https://feed.xyzfm.space/evgg6xle9rdc",                                 "color": "#1e40af"},
    {"key": "econtalk", "name": "EconTalk",        "cat": "podcast", "url": "https://feeds.simplecast.com/wgl4xEgL",                                 "color": "#047857"},
    {"key": "tedradio", "name": "TED Radio Hour",  "cat": "podcast", "url": "https://feeds.npr.org/510298/podcast.xml",                              "color": "#e11d48"},
    {"key": "dewx",     "name": "得意忘形",         "cat": "podcast", "url": "https://feed.xyzfm.space/klaak6nmc3ux",                                 "color": "#7c3aed"},
    {"key": "zkjun",    "name": "张小珺商业访谈",   "cat": "podcast", "url": "https://feed.xyzfm.space/dk4yh3pkpjp3",                                "color": "#0369a1"},
]

# 分类标签
CATEGORY_LABELS = {
    "tech":    "科技资讯",
    "cn_tech": "中文科技",
    "dev":     "开发者",
    "news":    "综合新闻",
    "podcast": "播客",
}

ITEMS_PER_SOURCE = 8
FETCH_TIMEOUT = 8
TRANSLATE_TIMEOUT = 4


# ──────────────────────────── 工具函数 ────────────────────────────

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


def _truncate(s, maxlen=200):
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
    s = (s or "").strip()
    if not s:
        return None
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
        return "%d秒前" % seconds
    minutes = seconds // 60
    if minutes < 60:
        return "%d分钟前" % minutes
    hours = minutes // 60
    if hours < 24:
        return "%d小时前" % hours
    days = hours // 24
    if days < 30:
        return "%d天前" % days
    return bj_naive.strftime("%Y-%m-%d")


# ──────────────────────────── 翻译 ────────────────────────────

def _translate_to_zh(text, timeout=TRANSLATE_TIMEOUT):
    """四端点降级翻译链：Google → MyMemory → Google dict-chrome。"""
    if not text:
        return ""
    # 如果已经是中文为主，跳过
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cn_chars > len(text) * 0.3:
        _TRANS_STATS["skip"] += 1
        return text

    encoded = urllib.parse.quote(text[:500])

    # 1) Google gtx
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" + encoded
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        if data and data[0]:
            result = "".join(part[0] for part in data[0] if part[0])
            if result and len(result) > len(text) * 0.3:
                _TRANS_STATS["google"] += 1
                return result
    except Exception:
        pass

    # 2) MyMemory
    try:
        url = "https://api.mymemory.translated.net/get?q=" + encoded + "&langpair=en|zh-CN"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        result = data.get("responseData", {}).get("translatedText", "")
        if result and not result.startswith("MYMEMORY"):
            _TRANS_STATS["mymemory"] += 1
            return result
    except Exception:
        pass

    # 3) Google dict-chrome
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=dict-chrome&sl=auto&tl=zh-CN&q=" + encoded
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        if data and data.get("sentences"):
            result = "".join(s.get("trans", "") for s in data["sentences"])
            if result:
                _TRANS_STATS["dict"] += 1
                return result
    except Exception:
        pass

    _TRANS_STATS["fail"] += 1
    return text  # 翻译失败保留原文


# ──────────────────────────── RSS 抓取 ────────────────────────────

def _fetch_url(url, timeout=FETCH_TIMEOUT, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1000000).decode("utf-8", errors="replace")


def _fetch_rss(source):
    name = source["name"]
    url = source["url"]
    try:
        raw = _fetch_url(url, timeout=FETCH_TIMEOUT, accept="application/rss+xml, application/xml, text/xml, application/atom+xml")
    except Exception as ex:
        print("[RSS聚合] %s 拉取失败: %s" % (name, ex), file=sys.stderr)
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as ex:
        print("[RSS聚合] %s 解析失败: %s" % (name, ex), file=sys.stderr)
        return []
    except Exception as ex:
        print("[RSS聚合] %s 异常: %s" % (name, ex), file=sys.stderr)
        return []

    items = []
    ns = "{http://www.w3.org/2005/Atom}"

    if root.tag.endswith("feed"):
        for e in root.findall(ns + "entry"):
            title = _strip_html(e.findtext(ns + "title") or "")
            link_el = e.find(ns + "link")
            link = (link_el.get("href") if link_el is not None else (e.findtext(ns + "id") or "")).strip()
            desc = _strip_html(e.findtext(ns + "summary") or e.findtext(ns + "content") or "")
            pub = e.findtext(ns + "updated") or e.findtext(ns + "published") or ""
            if not title or not link:
                continue
            items.append({
                "title": title, "link": link, "summary": _truncate(desc),
                "pub_date": _parse_iso(pub), "source": name, "source_key": source["key"],
                "cat": source["cat"],
            })
    else:
        ch = root.find("channel")
        if ch is None:
            for it in root.findall(".//item"):
                _parse_rss_item(it, name, source["key"], source["cat"], items)
        else:
            for it in ch.findall("item"):
                _parse_rss_item(it, name, source["key"], source["cat"], items)

    return items[:ITEMS_PER_SOURCE]


def _parse_rss_item(it, source_name, source_key, cat, items):
    title = _strip_html(it.findtext("title") or "")
    link = (it.findtext("link") or "").strip()
    desc = _strip_html(it.findtext("description") or "")
    pub = (it.findtext("pubDate") or "").strip()
    if not title or not link:
        return
    items.append({
        "title": title, "link": link, "summary": _truncate(desc),
        "pub_date": _parse_rss_date(pub), "source": source_name, "source_key": source_key,
        "cat": cat,
    })


# ──────────────────────────── HTML 生成 ────────────────────────────

def _build_css():
    return """
:root {
  --bg:#faf8f4; --card:#fffdf9; --card-2:#f3efe6; --card-3:#ebe6db;
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
  --bg:#161412; --card:#1d1a17; --card-2:#262019; --card-3:#2f2820;
  --ink:#ece7df; --muted:#a59d90; --faint:#8a8275;
  --line:#37312a; --line-strong:#4a4339;
  --brand:#8fb3d9; --brand-strong:#b0cbe6; --brand-line:#3d5a78; --brand-weak:#22303f;
  --accent-solid:#9db8d4;
  --shadow:0 1px 2px rgba(0,0,0,.4);
  --shadow-lift:0 8px 22px rgba(0,0,0,.5),0 1px 3px rgba(0,0,0,.4);
}
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
html,body { height:100%; }
html { scroll-behavior:smooth; }
body {
  font-family:var(--body); background:var(--bg); color:var(--ink);
  line-height:1.55; -webkit-font-smoothing:antialiased; font-size:14px;
  display:flex; flex-direction:column; overflow:hidden;
}
a { color:inherit; text-decoration:none; }
button { font-family:inherit; cursor:pointer; border:none; background:none; }

/* ── Header ── */
header {
  position:relative; z-index:50; flex:none;
  background:rgba(250,248,244,.95);
  backdrop-filter:saturate(120%) blur(10px);
  -webkit-backdrop-filter:saturate(120%) blur(10px);
  border-bottom:1px solid var(--line);
}
[data-theme="dark"] header { background:rgba(22,20,18,.95); }
.hd {
  max-width:100%; margin:0 auto; padding:8px 16px;
  display:flex; align-items:center; gap:12px;
}
.hd .logo {
  display:flex; align-items:center; gap:8px; flex:none;
  font-family:var(--display); font-weight:900; font-size:16px;
}
.hd .logo .t b { color:var(--ink); }
.hd .logo .t span { font-size:11px; color:var(--muted); font-weight:400; margin-left:3px; font-family:var(--body); }
.hd .nav-links { display:flex; align-items:center; gap:2px; flex:1; }
.hd .nav-links a {
  display:inline-flex; align-items:center; gap:5px;
  padding:5px 12px; border-radius:999px; font-size:12.5px; font-weight:500;
  border:1px solid transparent; transition:all .15s;
}
.hd .nav-links a:hover { background:var(--card); border-color:var(--line); }
.hd .nav-links a.active {
  background:var(--brand-weak); border-color:var(--brand-line); color:var(--brand-strong); font-weight:600;
}
.hd .nav-links a .icon { width:13px; height:13px; }
.hd .acts { display:flex; align-items:center; gap:4px; flex:none; }
.hd .acts .btn {
  width:30px; height:30px; border-radius:999px; background:var(--card); border:1px solid var(--line);
  display:flex; align-items:center; justify-content:center; color:var(--ink); transition:all .15s;
}
.hd .acts .btn:hover { border-color:var(--brand-line); color:var(--brand-strong); }
.hd .acts .btn svg { width:14px; height:14px; }

/* ── Main Layout: 3 columns ── */
.app {
  display:flex; flex:1; overflow:hidden;
}

/* Left sidebar: source list */
.sidebar {
  width:240px; flex:none; border-right:1px solid var(--line);
  background:var(--card); overflow-y:auto; display:flex; flex-direction:column;
}
.sidebar-header {
  padding:12px 14px 8px; border-bottom:1px solid var(--line); flex:none;
}
.sidebar-header h2 {
  font-family:var(--display); font-size:14px; font-weight:700; margin-bottom:8px;
}
.sidebar-search {
  display:flex; align-items:center; gap:4px;
  padding:5px 10px; border-radius:8px; background:var(--card-2); border:1px solid var(--line);
}
.sidebar-search svg { width:13px; height:13px; color:var(--faint); flex:none; }
.sidebar-search input {
  border:0; background:transparent; outline:none; font-size:12px; color:var(--ink);
  font-family:var(--body); width:100%;
}
.sidebar-search input::placeholder { color:var(--faint); }

/* Category groups */
.cat-group { flex:none; }
.cat-title {
  padding:8px 14px 4px; font-size:11px; font-weight:700; color:var(--faint);
  text-transform:uppercase; letter-spacing:.05em; cursor:pointer;
  display:flex; align-items:center; gap:4px; user-select:none;
}
.cat-title .arrow { transition:transform .15s; font-size:10px; }
.cat-title.collapsed .arrow { transform:rotate(-90deg); }
.cat-sources { display:flex; flex-direction:column; }
.cat-sources.hidden { display:none; }

.source-item {
  display:flex; align-items:center; gap:8px;
  padding:7px 14px 7px 20px; font-size:13px; cursor:pointer;
  transition:background .1s; border-left:3px solid transparent;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.source-item:hover { background:var(--card-2); }
.source-item.active {
  background:var(--card-3); border-left-color:var(--brand-line); font-weight:600;
}
.source-dot {
  width:8px; height:8px; border-radius:50%; flex:none;
}
.source-name { overflow:hidden; text-overflow:ellipsis; }
.source-count {
  font-family:var(--mono); font-size:10px; color:var(--faint); margin-left:auto; flex:none;
}

/* Middle: article list */
.article-list {
  width:340px; flex:none; border-right:1px solid var(--line);
  background:var(--bg); overflow-y:auto; display:flex; flex-direction:column;
}
.article-list-header {
  padding:10px 14px; border-bottom:1px solid var(--line); flex:none;
  display:flex; align-items:center; gap:8px;
}
.article-list-header h3 {
  font-family:var(--display); font-size:14px; font-weight:700; flex:1;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.article-list-header .count {
  font-family:var(--mono); font-size:11px; color:var(--faint);
}
.article-list-header .view-all {
  font-size:11px; color:var(--brand-strong); cursor:pointer;
}

.article-item {
  padding:10px 14px; border-bottom:1px solid var(--line);
  cursor:pointer; transition:background .1s;
}
.article-item:hover { background:var(--card); }
.article-item.active { background:var(--card-3); border-left:3px solid var(--brand-line); }
.article-item .a-title {
  font-size:13px; font-weight:600; line-height:1.4;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  margin-bottom:4px;
}
.article-item .a-meta {
  display:flex; align-items:center; gap:6px; font-size:11px; color:var(--faint);
}
.article-item .a-meta .src-tag {
  display:inline-flex; align-items:center; gap:3px;
  padding:1px 6px; border-radius:999px; font-size:10px; font-weight:600; color:#fff;
}
.article-item .a-meta .time { font-family:var(--mono); margin-left:auto; }

/* Right: reading area */
.reader {
  flex:1; overflow-y:auto; background:var(--bg);
  display:flex; flex-direction:column;
}
.reader-empty {
  flex:1; display:flex; align-items:center; justify-content:center;
  color:var(--faint); font-size:14px; flex-direction:column; gap:8px;
}
.reader-empty svg { width:48px; height:48px; opacity:.3; }

.reader-content { padding:24px 32px; max-width:720px; margin:0 auto; width:100%; }
.reader-content .rc-title {
  font-family:var(--display); font-size:22px; font-weight:700; line-height:1.4;
  margin-bottom:12px;
}
.reader-content .rc-title a { color:var(--ink); }
.reader-content .rc-title a:hover { color:var(--brand-strong); }
.reader-content .rc-meta {
  display:flex; align-items:center; gap:8px; font-size:12px; color:var(--faint);
  margin-bottom:20px; padding-bottom:16px; border-bottom:1px solid var(--line);
}
.reader-content .rc-meta .src-tag {
  display:inline-flex; align-items:center; gap:3px;
  padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; color:#fff;
}
.reader-content .rc-summary {
  font-size:15px; line-height:1.8; color:var(--ink);
}
.reader-content .rc-link {
  display:inline-flex; align-items:center; gap:4px;
  margin-top:20px; padding:8px 18px; border-radius:8px;
  background:var(--brand-weak); color:var(--brand-strong);
  font-size:13px; font-weight:600; transition:all .15s;
}
.reader-content .rc-link:hover { background:var(--brand-line); color:#fff; }

/* ── Responsive ── */
@media (max-width:900px) {
  .sidebar { width:200px; }
  .article-list { width:280px; }
}
@media (max-width:700px) {
  body { overflow:auto; }
  .app { flex-direction:column; overflow:visible; }
  .sidebar {
    width:100%; max-height:200px; border-right:none; border-bottom:1px solid var(--line);
    flex-direction:row; overflow-x:auto; overflow-y:hidden;
  }
  .sidebar-header { display:none; }
  .cat-group { display:flex; flex-direction:row; flex:none; }
  .cat-title { display:none; }
  .cat-sources { flex-direction:row; }
  .cat-sources.hidden { display:flex; }
  .source-item {
    padding:6px 10px; border-left:none; border-bottom:3px solid transparent;
    white-space:nowrap; font-size:12px;
  }
  .source-item.active { border-left:none; border-bottom-color:var(--brand-line); }
  .source-count { display:none; }
  .article-list {
    width:100%; max-height:300px; border-right:none; border-bottom:1px solid var(--line);
  }
  .reader { min-height:400px; }
  .reader-content { padding:16px; }
}
"""


def _build_header():
    return """
<header>
  <div class="hd">
    <a class="logo" href="index.html">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a7 7 0 0 1 14 0"/><path d="M4 11v4a2 2 0 0 0 2 2h1a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H4"/><path d="M18 11v4a2 2 0 0 1-2 2h-1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h3"/></svg>
      <div class="t"><b>StarHub</b><span>GitHub 收藏台</span></div>
    </a>
    <nav class="nav-links">
      <a href="index.html"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> 收藏池</a>
      <a href="ai-daily.html"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11a7 7 0 0 1 14 0"/><path d="M4 11v4a2 2 0 0 0 2 2h1a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H4"/><path d="M18 11v4a2 2 0 0 1-2 2h-1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h3"/></svg> AI 晨报</a>
      <a href="rss-aggregator.html" class="active"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg> RSS 聚合</a>
    </nav>
    <div class="acts">
      <button class="btn" id="btnTheme" title="切换明暗主题" aria-label="切换主题">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      </button>
    </div>
  </div>
</header>
"""


def _build_js(sources_with_items):
    """sources_with_items: list of source dicts with items embedded."""
    data_json = json.dumps(sources_with_items, ensure_ascii=False)
    cat_labels_json = json.dumps(CATEGORY_LABELS, ensure_ascii=False)
    return """
<script>
(function(){
  // ── Theme ──
  var themeKey='wb_starhub_theme_v1';
  var t=localStorage.getItem(themeKey)||(window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.dataset.theme=t;
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){
    var nt=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{localStorage.setItem(themeKey,nt);}catch(e){}
    document.documentElement.dataset.theme=nt;
  };

  // ── Data ─
  var SOURCES = """ + data_json + """;
  var CAT_LABELS = """ + cat_labels_json + """;

  // ── State ──
  var activeSourceKey = null;
  var activeArticleIdx = -1;
  var searchQuery = '';

  // ── DOM refs ──
  var sidebarEl = document.getElementById('sidebar');
  var articleListEl = document.getElementById('articleList');
  var articleListHeaderEl = document.getElementById('articleListHeader');
  var readerEl = document.getElementById('reader');
  var searchInput = document.getElementById('sidebarSearch');

  // ── Render sidebar ──
  function renderSidebar() {
    var html = '';
    var cats = {};
    SOURCES.forEach(function(src) {
      if (!cats[src.cat]) cats[src.cat] = [];
      cats[src.cat].push(src);
    });
    var catOrder = ['tech','cn_tech','dev','news','podcast'];
    catOrder.forEach(function(catKey) {
      var srcs = cats[catKey];
      if (!srcs) return;
      var label = CAT_LABELS[catKey] || catKey;
      html += '<div class="cat-group">';
      html += '<div class="cat-title" data-cat="'+catKey+'"><span class="arrow">▼</span> '+esc(label)+'</div>';
      html += '<div class="cat-sources">';
      srcs.forEach(function(src) {
        var cls = 'source-item' + (src.key === activeSourceKey ? ' active' : '');
        html += '<div class="'+cls+'" data-key="'+esc(src.key)+'">';
        html += '<span class="source-dot" style="background:'+esc(src.color)+'"></span>';
        html += '<span class="source-name">'+esc(src.name)+'</span>';
        html += '<span class="source-count">'+src.items.length+'</span>';
        html += '</div>';
      });
      html += '</div></div>';
    });
    sidebarEl.innerHTML = html;

    // Category collapse
    sidebarEl.querySelectorAll('.cat-title').forEach(function(el) {
      el.addEventListener('click', function() {
        this.classList.toggle('collapsed');
        var panel = this.nextElementSibling;
        if (panel) panel.classList.toggle('hidden');
      });
    });

    // Source click
    sidebarEl.querySelectorAll('.source-item').forEach(function(el) {
      el.addEventListener('click', function() {
        selectSource(this.dataset.key);
      });
    });
  }

  // ── Select source ──
  function selectSource(key) {
    activeSourceKey = key;
    activeArticleIdx = -1;
    renderSidebar();
    renderArticleList();
    renderReader();
  }

  // ── Render article list ──
  function renderArticleList() {
    var src = SOURCES.find(function(s){ return s.key === activeSourceKey; });
    if (!src) {
      articleListHeaderEl.innerHTML = '<h3>选择一个信源</h3>';
      articleListEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">点击左侧信源查看文章</div>';
      return;
    }
    var items = filterItems(src.items);
    articleListHeaderEl.innerHTML = '<h3>'+esc(src.name)+'</h3><span class="count">'+items.length+' 篇</span>';

    if (items.length === 0) {
      articleListEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">暂无匹配文章</div>';
      return;
    }

    var html = '';
    items.forEach(function(item, idx) {
      var cls = 'article-item' + (idx === activeArticleIdx ? ' active' : '');
      html += '<div class="'+cls+'" data-idx="'+idx+'">';
      html += '<div class="a-title">'+esc(item.title_zh || item.title)+'</div>';
      html += '<div class="a-meta">';
      html += '<span class="src-tag" style="background:'+esc(src.color)+'">'+esc(src.name)+'</span>';
      html += '<span class="time">'+esc(item.time_str)+'</span>';
      html += '</div></div>';
    });
    articleListEl.innerHTML = html;

    articleListEl.querySelectorAll('.article-item').forEach(function(el) {
      el.addEventListener('click', function() {
        activeArticleIdx = parseInt(this.dataset.idx);
        renderArticleList();
        renderReader();
      });
    });
  }

  // ── Render reader ──
  function renderReader() {
    if (!activeSourceKey || activeArticleIdx < 0) {
      readerEl.innerHTML = '<div class="reader-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg><span>从左侧选择一篇文章开始阅读</span></div>';
      return;
    }
    var src = SOURCES.find(function(s){ return s.key === activeSourceKey; });
    if (!src) return;
    var items = filterItems(src.items);
    var item = items[activeArticleIdx];
    if (!item) return;

    var html = '<div class="reader-content">';
    html += '<h1 class="rc-title"><a href="'+esc(item.link)+'" target="_blank" rel="noopener">'+esc(item.title_zh || item.title)+'</a></h1>';
    html += '<div class="rc-meta">';
    html += '<span class="src-tag" style="background:'+esc(src.color)+'">'+esc(src.name)+'</span>';
    html += '<span>'+esc(item.time_str)+'</span>';
    if (item.title_zh && item.title_zh !== item.title) {
      html += '<span style="font-size:11px;color:var(--faint)">（已翻译）</span>';
    }
    html += '</div>';
    if (item.summary_zh || item.summary) {
      html += '<div class="rc-summary">'+esc(item.summary_zh || item.summary)+'</div>';
    }
    html += '<a class="rc-link" href="'+esc(item.link)+'" target="_blank" rel="noopener">阅读原文 →</a>';
    html += '</div>';
    readerEl.innerHTML = html;
  }

  // ── Filter ──
  function filterItems(items) {
    if (!searchQuery) return items;
    var q = searchQuery.toLowerCase();
    return items.filter(function(it) {
      var t = (it.title_zh || it.title).toLowerCase();
      var s = (it.summary_zh || it.summary || '').toLowerCase();
      return t.indexOf(q) >= 0 || s.indexOf(q) >= 0;
    });
  }

  // ── Search ──
  if (searchInput) {
    searchInput.addEventListener('input', function() {
      searchQuery = this.value.trim();
      renderArticleList();
      if (activeArticleIdx >= filterItems(SOURCES.find(function(s){return s.key===activeSourceKey;})?.items || []).length) {
        activeArticleIdx = -1;
      }
      renderReader();
    });
  }

  // ── Helpers ──
  function esc(s) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(s || ''));
    return d.innerHTML;
  }

  // ── Init ──
  renderSidebar();
  // Auto-select first source with items
  var firstSrc = SOURCES.find(function(s){ return s.items.length > 0; });
  if (firstSrc) selectSource(firstSrc.key);

  // ── Live RSS update ──
  setTimeout(function(){
    fetch('/api/rss').then(function(r){
      if(!r.ok) throw new Error('API '+r.status);
      return r.json();
    }).then(function(data){
      if(!data.sources) return;
      var updated = 0;
      data.sources.forEach(function(live){
        if(!live.items||!live.items.length) return;
        var src = SOURCES.find(function(s){ return s.key === live.key; });
        if(!src) return;
        live.items.forEach(function(it){
          it.title_zh = it.title;
          it.summary_zh = it.summary || '';
        });
        src.items = live.items;
        updated++;
      });
      if(updated > 0){
        renderSidebar();
        renderArticleList();
        renderReader();
        // Show live update time in sidebar header
        var sidebar = document.getElementById('sidebar');
        if(sidebar){
          var old = document.getElementById('rssLiveTime');
          if(old) old.remove();
          var span = document.createElement('span');
          span.id = 'rssLiveTime';
          span.style.cssText = 'font-size:10px;color:var(--faint);font-family:var(--mono);display:block;padding:4px 12px;';
          var now = new Date();
          span.textContent = '\u2713 \u5df2\u66f4\u65b0 ' + now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
          sidebar.appendChild(span);
        }
        console.log('[RSS] Live updated:', updated, 'sources');
      }
    }).catch(function(e){ console.warn('[RSS] Live update failed:', e.message); });
  }, 800);
})();
</script>
"""


def build_html(sources_with_items, build_time, total_items):
    """生成完整 HTML 页面。"""
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<title>RSS 聚合阅读器 · StarHub</title>\n'
        '<style>' + _build_css() + '</style>\n'
        '</head>\n<body>\n'
        + _build_header() +
        '<div class="app">\n'
        '<div class="sidebar" id="sidebar">'
        '<div class="sidebar-header">'
        '<h2>信源列表</h2>'
        '<div class="sidebar-search">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
        '<input id="sidebarSearch" type="search" placeholder="搜索文章…" autocomplete="off">'
        '</div></div></div>\n'
        '<div class="article-list" id="articleList">'
        '<div class="article-list-header" id="articleListHeader"><h3>选择一个信源</h3></div>'
        '<div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">点击左侧信源查看文章</div>'
        '</div>\n'
        '<div class="reader" id="reader">'
        '<div class="reader-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg><span>从左侧选择一篇文章开始阅读</span></div>'
        '</div>\n'
        '</div>\n'
        '<div style="text-align:center;padding:6px 0;font-size:11px;color:var(--faint);font-family:var(--mono);border-top:1px solid var(--line);flex:none;background:var(--bg);">'
        '自动生成于 ' + _esc(build_time) + '（北京时间）· 共 ' + str(total_items) + ' 篇 · StarHub RSS Aggregator'
        '</div>\n'
        + _build_js(sources_with_items) +
        '</body>\n</html>'
    )


# ──────────────────────────── Main ────────────────────────────

def main():
    now = _now_bj()
    build_time = now.strftime("%Y-%m-%d %H:%M")

    sources_with_items = []
    total_items = 0
    ok_count = 0

    # 串行抓取 RSS（短超时，失败快速跳过）
    for src in RSS_SOURCES:
        items = _fetch_rss(src)
        n = len(items)
        if n > 0:
            ok_count += 1

        # 暂不翻译（构建超时），标题和摘要直接使用原文
        for it in items:
            it["title_zh"] = it["title"]
            it["summary_zh"] = it.get("summary", "")
            it["time_str"] = _fmt_rel_time(it.get("pub_date"))
            it.pop("pub_date", None)

        src_data = {
            "key": src["key"], "name": src["name"], "cat": src["cat"],
            "color": src["color"], "items": items,
        }
        sources_with_items.append(src_data)
        total_items += n
        print("[RSS聚合] %s: %d 条" % (src["name"], n))

    if total_items == 0:
        print("[RSS聚合] 所有源均失败，生成空页面", file=sys.stderr)

    html_doc = build_html(sources_with_items, build_time, total_items)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)

    print("[RSS聚合] 生成完成 → %s（%d 源成功，共 %d 篇）" % (OUT, ok_count, total_items))
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
