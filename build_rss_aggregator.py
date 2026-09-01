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

# ── 缓存配置 ──
TRANS_CACHE_FILE = "translations.json"
RSS_CACHE_FILE = "rss_cache.json"
RSS_CACHE_TTL = 1800  # RSS 缓存有效期：30 分钟

# ── 缓存数据 ──
_trans_cache = {}  # {text_hash: translated_text}
_rss_cache = {}    # {source_key: {"items": [...], "fetched_at": timestamp}}

# ── 翻译统计 
_TRANS_STATS = {"google": 0, "bing": 0, "mymemory": 0, "dict": 0, "skip": 0, "fail": 0, "cache_hit": 0}


def _load_caches():
    """加载翻译和 RSS 缓存"""
    global _trans_cache, _rss_cache
    # 加载翻译缓存
    if os.path.exists(TRANS_CACHE_FILE):
        try:
            with open(TRANS_CACHE_FILE, "r", encoding="utf-8") as f:
                _trans_cache = json.load(f)
            print("[缓存] 加载翻译缓存: %d 条" % len(_trans_cache))
        except Exception as e:
            print("[缓存] 加载翻译缓存失败: %s" % e, file=sys.stderr)
    # 加载 RSS 缓存
    if os.path.exists(RSS_CACHE_FILE):
        try:
            with open(RSS_CACHE_FILE, "r", encoding="utf-8") as f:
                _rss_cache = json.load(f)
            print("[缓存] 加载 RSS 缓存: %d 个源" % len(_rss_cache))
        except Exception as e:
            print("[缓存] 加载 RSS 缓存失败: %s" % e, file=sys.stderr)


def _save_caches():
    """保存翻译和 RSS 缓存"""
    try:
        with open(TRANS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_trans_cache, f, ensure_ascii=False, indent=2)
        print("[缓存] 保存翻译缓存: %d 条" % len(_trans_cache))
    except Exception as e:
        print("[缓存] 保存翻译缓存失败: %s" % e, file=sys.stderr)
    try:
        with open(RSS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_rss_cache, f, ensure_ascii=False, indent=2)
        print("[缓存] 保存 RSS 缓存: %d 个源" % len(_rss_cache))
    except Exception as e:
        print("[缓存] 保存 RSS 缓存失败: %s" % e, file=sys.stderr)

# ── RSS 信源配置（按分类组织，107 个精选源，已去除公众号/失效/重复/停更源） ─
RSS_SOURCES = [
    # ── 科技资讯 (10) ──
    {"key": "juliaevans_0", "name": "Julia Evans", "cat": "tech", "url": "https://jvns.ca/atom.xml", "color": "#e31937"},
    {"key": "overreacted_2", "name": "Overreacted", "cat": "tech", "url": "https://overreacted.io/rss.xml", "color": "#b31b1b"},
    {"key": "webdev_3", "name": "web.dev", "cat": "tech", "url": "https://web.dev/feed.xml", "color": "#000000"},
    {"key": "engadget_4", "name": "Engadget", "cat": "tech", "url": "http://www.engadget.com/rss.xml", "color": "#2563eb"},
    {"key": "joshcomeau_5", "name": "Josh Comeau", "cat": "tech", "url": "https://www.joshwcomeau.com/rss.xml", "color": "#7c3aed"},
    {"key": "techcrunchai_7", "name": "TechCrunch AI", "cat": "tech", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "color": "#d97706"},
    {"key": "thevergeai_8", "name": "The Verge AI", "cat": "tech", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "color": "#dc2626"},
    {"key": "wired_10", "name": "WIRED", "cat": "tech", "url": "https://www.wired.com/feed/rss", "color": "#4f46e5"},
    {"key": "atlasnote_11", "name": "AtlasNote", "cat": "tech", "url": "https://atlasnote.ai/rss.xml", "color": "#ca8a04"},
    {"key": "redisblog_12", "name": "Redis Blog", "cat": "tech", "url": "https://redis.io/feed/", "color": "#0891b2"},

    # ── 中文科技 (23) ──
    {"key": "美团技术团队_0", "name": "美团技术团队", "cat": "cn_tech", "url": "https://tech.meituan.com/feed", "color": "#0055ff"},
    {"key": "v2ex_1", "name": "V2EX", "cat": "cn_tech", "url": "https://v2ex.com/index.xml", "color": "#d7434e"},
    {"key": "机核_2", "name": "机核", "cat": "cn_tech", "url": "https://www.gcores.com/rss", "color": "#1a1a1a"},
    {"key": "solidot_3", "name": "Solidot", "cat": "cn_tech", "url": "https://www.solidot.org/index.rss", "color": "#0066ff"},
    {"key": "少数派_4", "name": "少数派", "cat": "cn_tech", "url": "https://sspai.com/feed", "color": "#336699"},
    {"key": "爱范儿_5", "name": "爱范儿", "cat": "cn_tech", "url": "https://www.ifanr.com/feed", "color": "#333333"},
    {"key": "小众软件_8", "name": "小众软件", "cat": "cn_tech", "url": "https://www.appinn.com/feed/", "color": "#FFD43B"},
    {"key": "构建被动收入_9", "name": "构建被动收入", "cat": "cn_tech", "url": "https://www.bmpi.dev/index.xml", "color": "#00bc74"},
    {"key": "虎嗅_11", "name": "虎嗅", "cat": "cn_tech", "url": "https://rsshub.bestblogs.dev/huxiu/article", "color": "#3a85ff"},
    {"key": "it之家_13", "name": "IT之家", "cat": "cn_tech", "url": "https://www.ithome.com/rss/", "color": "#1e88e5"},
    {"key": "月光博客_15", "name": "月光博客", "cat": "cn_tech", "url": "http://www.williamlong.info/rss.xml", "color": "#e53935"},
    {"key": "理想生活实验室_18", "name": "理想生活实验室", "cat": "cn_tech", "url": "https://www.toodaylab.com/feed", "color": "#43a047"},
    {"key": "游戏研究社_19", "name": "游戏研究社", "cat": "cn_tech", "url": "https://www.yystv.cn/rss/feed", "color": "#5c6bc0"},
    {"key": "潮流周刊_21", "name": "潮流周刊", "cat": "cn_tech", "url": "https://weekly.tw93.fun/rss.xml", "color": "#ff5722"},
    {"key": "扯氮集_25", "name": "扯氮集", "cat": "cn_tech", "url": "http://weiwuhui.com/feed", "color": "#6a1b9a"},
    {"key": "deepzz_26", "name": "Deepzz", "cat": "cn_tech", "url": "https://deepzz.com/feed", "color": "#d32f2f"},
    {"key": "mit科技评论_28", "name": "MIT科技评论", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/mittrchina/hot", "color": "#0097a7"},
    {"key": "疯投圈_29", "name": "疯投圈", "cat": "cn_tech", "url": "https://crazy.capital/feed", "color": "#c62828"},
    {"key": "超能网_31", "name": "超能网", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/expreview", "color": "#0091ea"},
    {"key": "钛媒体_38", "name": "钛媒体", "cat": "cn_tech", "url": "https://www.tmtpost.com/feed", "color": "#4a90d9"},
    {"key": "人人都是产品经理_39", "name": "人人都是产品经理", "cat": "cn_tech", "url": "https://www.woshipm.com/feed", "color": "#00aa55"},
    {"key": "cnbeta_41", "name": "cnBeta", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/cnbeta", "color": "#00bc74"},
    {"key": "v2ex技术_44", "name": "V2EX技术", "cat": "cn_tech", "url": "https://www.v2ex.com/feed/tab/tech.xml", "color": "#3177cf"},

    # ── 开发者博客 (40) ──
    {"key": "阮一峰的网络日志_0", "name": "阮一峰的网络日志", "cat": "dev", "url": "https://www.ruanyifeng.com/blog/atom.xml", "color": "#dc382d"},
    {"key": "编程随想_2", "name": "编程随想", "cat": "dev", "url": "https://feeds2.feedburner.com/programthink", "color": "#e34f26"},
    {"key": "酷壳_3", "name": "酷壳", "cat": "dev", "url": "http://coolshell.cn/feed", "color": "#663399"},
    {"key": "太隐_4", "name": "太隐", "cat": "dev", "url": "https://wangyurui.com/feed.xml", "color": "#336699"},
    {"key": "云风的blog_5", "name": "云风的BLOG", "cat": "dev", "url": "http://blog.codingnow.com/atom.xml", "color": "#4CAF50"},
    {"key": "胡涂说_6", "name": "胡涂说", "cat": "dev", "url": "https://hutusi.com/feed.xml", "color": "#8e44ad"},
    {"key": "程序员的喵_7", "name": "程序员的喵", "cat": "dev", "url": "https://catcoding.me/atom.xml", "color": "#6c5ce7"},
    {"key": "oldjblog_8", "name": "oldj blog", "cat": "dev", "url": "https://oldj.net/feed", "color": "#2d3436"},
    {"key": "晚晴幽草轩_9", "name": "晚晴幽草轩", "cat": "dev", "url": "https://www.jeffjade.com/atom.xml", "color": "#e74c3c"},
    {"key": "ezindie_10", "name": "ezindie", "cat": "dev", "url": "https://www.ezindie.com/feed/rss.xml", "color": "#00b894"},
    {"key": "dravenss_11", "name": "dravenss", "cat": "dev", "url": "https://draveness.me/feed.xml", "color": "#2c3e50"},
    {"key": "randy'sblog_12", "name": "Randy\'s Blog", "cat": "dev", "url": "https://lutaonan.com/rss.xml", "color": "#e67e22"},
    {"key": "卡瓦邦噶_13", "name": "卡瓦邦噶", "cat": "dev", "url": "https://www.kawabangga.com/feed", "color": "#3498db"},
    {"key": "风雪之隅_14", "name": "风雪之隅", "cat": "dev", "url": "http://www.laruence.com/feed", "color": "#1abc9c"},
    {"key": "离别歌_15", "name": "离别歌", "cat": "dev", "url": "https://www.leavesongs.com/feed/", "color": "#9b59b6"},
    {"key": "hellogithub_17", "name": "HelloGitHub", "cat": "dev", "url": "http://hellogithub.com/rss", "color": "#16a085"},
    {"key": "张鑫旭_18", "name": "张鑫旭", "cat": "dev", "url": "https://www.zhangxinxu.com/wordpress/feed/", "color": "#f39c12"},
    {"key": "maxos_19", "name": "maxOS", "cat": "dev", "url": "https://maxoxo.me/rss/", "color": "#dc382d"},
    {"key": "轶哥博客_20", "name": "轶哥博客", "cat": "dev", "url": "https://www.wyr.me/rss.xml", "color": "#6366f1"},
    {"key": "geekplux_21", "name": "GeekPlux", "cat": "dev", "url": "https://geekplux.com/feed.xml", "color": "#e34f26"},
    {"key": "mactalk池建强_22", "name": "MacTalk池建强", "cat": "dev", "url": "http://macshuo.com/?feed=rss2", "color": "#663399"},
    {"key": "xuanwo_23", "name": "Xuanwo", "cat": "dev", "url": "https://xuanwo.io/index.xml", "color": "#336699"},
    {"key": "反斗限免_24", "name": "反斗限免", "cat": "dev", "url": "http://free.apprcn.com/feed/", "color": "#4CAF50"},
    {"key": "halfrost_25", "name": "Halfrost", "cat": "dev", "url": "http://halfrost.com/rss/", "color": "#8e44ad"},
    {"key": "infoq推荐_26", "name": "InfoQ推荐", "cat": "dev", "url": "https://plink.anyfeeder.com/infoq/recommend", "color": "#6c5ce7"},
    {"key": "二丫讲梵_27", "name": "二丫讲梵", "cat": "dev", "url": "https://wiki.eryajf.net/rss.xml", "color": "#2d3436"},
    {"key": "唐巧博客_28", "name": "唐巧博客", "cat": "dev", "url": "http://blog.devtang.com/atom.xml", "color": "#e74c3c"},
    {"key": "baiyun_30", "name": "BAI YUN", "cat": "dev", "url": "https://baiyun.me/feed", "color": "#2c3e50"},
    {"key": "elmagnifico_31", "name": "elmagnifico", "cat": "dev", "url": "http://elmagnifico.tech/feed.xml", "color": "#e67e22"},
    {"key": "tonybai_33", "name": "Tony Bai", "cat": "dev", "url": "http://tonybai.com/feed/", "color": "#1abc9c"},
    {"key": "phoenixisland_35", "name": "Phoenix island", "cat": "dev", "url": "https://blog.phoenixlzx.com/atom.xml", "color": "#34495e"},
    {"key": "全栈应用开发_36", "name": "全栈应用开发", "cat": "dev", "url": "https://www.phodal.com/blog/feeds/rss/", "color": "#16a085"},
    {"key": "tinyprojects_37", "name": "Tiny Projects", "cat": "dev", "url": "https://tinyprojects.dev/feed.xml", "color": "#f39c12"},
    {"key": "笨方法学写作_38", "name": "笨方法学写作", "cat": "dev", "url": "https://www.cnfeat.com/feed.xml", "color": "#dc382d"},
    {"key": "西秦公子_39", "name": "西秦公子", "cat": "dev", "url": "https://www.ixiqin.com/feed/", "color": "#6366f1"},
    {"key": "小明明s_40", "name": "小明明s", "cat": "dev", "url": "https://www.dongwm.com/atom.xml", "color": "#e34f26"},
    {"key": "涛叔_41", "name": "涛叔", "cat": "dev", "url": "https://taoshu.in/feed.xml", "color": "#663399"},
    {"key": "小球飞鱼_42", "name": "小球飞鱼", "cat": "dev", "url": "https://mantyke.icu/index.xml", "color": "#336699"},
    {"key": "王登科dk_43", "name": "王登科DK", "cat": "dev", "url": "https://greatdk.com/feed", "color": "#4CAF50"},
    {"key": "小胡子哥_44", "name": "小胡子哥", "cat": "dev", "url": "http://www.barretlee.com/rss2.xml", "color": "#8e44ad"},
    {"key": "dbanotes_45", "name": "DBA Notes", "cat": "dev", "url": "http://dbanotes.net/feed", "color": "#6c5ce7"},

    # ── 综合新闻 (28) ──
    {"key": "联合早报中港台_0", "name": "联合早报-中港台", "cat": "news", "url": "https://plink.anyfeeder.com/zaobao/realtime/china", "color": "#bb1919"},
    {"key": "联合早报国际_1", "name": "联合早报-国际", "cat": "news", "url": "https://plink.anyfeeder.com/zaobao/realtime/world", "color": "#0066b3"},
    {"key": "idaily_3", "name": "iDaily", "cat": "news", "url": "https://plink.anyfeeder.com/idaily/today", "color": "#003399"},
    {"key": "中国日报双语_4", "name": "中国日报双语", "cat": "news", "url": "https://plink.anyfeeder.com/chinadaily/dual", "color": "#cc0000"},
    {"key": "知乎日报anyfeeder_5", "name": "知乎日报anyfeeder", "cat": "news", "url": "https://plink.anyfeeder.com/zhihu/daily", "color": "#d32f2f"},
    {"key": "法广中文_18", "name": "法广中文", "cat": "news", "url": "https://plink.anyfeeder.com/rfi/cn", "color": "#1a1a1a"},
    {"key": "bbc中文_20", "name": "BBC中文", "cat": "news", "url": "https://plink.anyfeeder.com/bbc/cn", "color": "#cc0000"},
    {"key": "财富中文网_21", "name": "财富中文网", "cat": "news", "url": "https://plink.anyfeeder.com/fortunechina", "color": "#d32f2f"},
    {"key": "华尔街日报anyfeeder_23", "name": "华尔街日报anyfeeder", "cat": "news", "url": "https://plink.anyfeeder.com/wsj/cn", "color": "#0055a4"},
    {"key": "光明日报_26", "name": "光明日报", "cat": "news", "url": "https://plink.anyfeeder.com/guangmingribao", "color": "#5c6bc0"},
    {"key": "澎湃新闻_41", "name": "澎湃新闻", "cat": "news", "url": "https://plink.anyfeeder.com/thepaper", "color": "#43a047"},
    {"key": "sbs澳洲中文_49", "name": "SBS澳洲中文", "cat": "news", "url": "https://plink.anyfeeder.com/abc/cn", "color": "#0066b3"},
    {"key": "人民网_54", "name": "人民网", "cat": "news", "url": "https://plink.anyfeeder.com/people", "color": "#1565c0"},
    {"key": "人民网英语_58", "name": "人民网英语", "cat": "news", "url": "https://plink.anyfeeder.com/people/english", "color": "#5c6bc0"},
    {"key": "南方周末anyfeeder_61", "name": "南方周末anyfeeder", "cat": "news", "url": "https://plink.anyfeeder.com/infzm/news", "color": "#0097a7"},
    {"key": "纽约时报中文网_66", "name": "纽约时报中文网", "cat": "news", "url": "http://cn.nytimes.com/rss/news.xml", "color": "#1a1a1a"},
    {"key": "解放军报_67", "name": "解放军报", "cat": "news", "url": "https://plink.anyfeeder.com/jiefangjunbao", "color": "#003399"},
    {"key": "喷嚏网铂程斋_70", "name": "喷嚏网铂程斋", "cat": "news", "url": "https://plink.anyfeeder.com/dapenti/xilei", "color": "#1565c0"},
    {"key": "观止_73", "name": "观止", "cat": "news", "url": "https://plink.anyfeeder.com/meiriyiwen", "color": "#43a047"},
    {"key": "雪球热帖_77", "name": "雪球热帖", "cat": "news", "url": "https://xueqiu.com/hots/topic/rss", "color": "#0097a7"},
    {"key": "bbc英语教学_80", "name": "BBC英语教学", "cat": "news", "url": "https://plink.anyfeeder.com/bbc/learningenglish", "color": "#bb1919"},
    {"key": "求是网_92", "name": "求是网", "cat": "news", "url": "https://plink.anyfeeder.com/qstheory", "color": "#6a1b9a"},
    {"key": "半岛网_118", "name": "半岛网", "cat": "news", "url": "https://plink.anyfeeder.com/aljazeera/news", "color": "#1565c0"},
    {"key": "界面新闻_121", "name": "界面新闻", "cat": "news", "url": "https://plink.anyfeeder.com/jiemian/news", "color": "#43a047"},
    {"key": "经济日报_124", "name": "经济日报", "cat": "news", "url": "https://plink.anyfeeder.com/jingjiribao", "color": "#6a1b9a"},
    {"key": "果壳科学人_125", "name": "果壳科学人", "cat": "news", "url": "https://plink.anyfeeder.com/guokr/scientific", "color": "#0097a7"},
    {"key": "豆瓣书评_135", "name": "豆瓣书评", "cat": "news", "url": "https://www.douban.com/feed/review/book", "color": "#0055a4"},
    {"key": "界面财经_143", "name": "界面财经", "cat": "news", "url": "https://plink.anyfeeder.com/jiemian/finance", "color": "#e65100"},

    # ── 播客 (6) ──
    {"key": "42章经_1", "name": "42章经", "cat": "podcast", "url": "https://feed.xyzfm.space/evgg6xle9rdc", "color": "#0891b2"},
    {"key": "三点下班_4", "name": "三点下班", "cat": "podcast", "url": "https://feed.xyzfm.space/tlel9j4tg3eu", "color": "#e11d48"},
    {"key": "卫诗婕商业漫谈_6", "name": "卫诗婕商业漫谈", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6627fda4b56459544087d86a", "color": "#7c3aed"},
    {"key": "得意忘形_7", "name": "得意忘形", "cat": "podcast", "url": "https://feed.xyzfm.space/klaak6nmc3ux", "color": "#0891b2"},
    {"key": "起朱楼宴宾客_8", "name": "起朱楼宴宾客", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65253bf350cf691d245b29aa", "color": "#1e40af"},
    {"key": "tedradiohour_10", "name": "TED Radio Hour", "cat": "podcast", "url": "https://feeds.npr.org/510298/podcast.xml", "color": "#e11d48"},

]

# 分类标签
CATEGORY_LABELS = {
    "tech":    "科技资讯",
    "cn_tech": "中文科技",
    "dev":     "开发者",
    "news":    "综合新闻",
    "podcast": "播客",
}

ITEMS_PER_SOURCE = 30
FETCH_TIMEOUT = 8
TRANSLATE_TIMEOUT = 4


# ──────────────────────────── 工具函数 ────────────────────────────

def _now_bj():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def _esc(s):
    return html_mod.escape(str(s), quote=True)


def _strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    # Use html.unescape to decode all HTML entities (&rsquo; &mdash; &hellip; etc.)
    text = html_mod.unescape(text)
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
    # Convert to Beijing time, handling both aware and naive datetimes
    if dt.tzinfo:
        bj = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        bj_naive = bj.replace(tzinfo=None)
    else:
        bj_naive = dt
    now = _now_bj().replace(tzinfo=None)
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
    """四端点降级翻译链：Google → MyMemory → Google dict-chrome（带缓存）。"""
    if not text:
        return ""
    # 如果已经是中文为主，跳过
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cn_chars > len(text) * 0.3:
        _TRANS_STATS["skip"] += 1
        return text

    # 查缓存
    text_hash = str(hash(text))
    if text_hash in _trans_cache:
        _TRANS_STATS["cache_hit"] += 1
        return _trans_cache[text_hash]

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
                _trans_cache[text_hash] = result  # 写入缓存
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
            _trans_cache[text_hash] = result  # 写入缓存
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
                _trans_cache[text_hash] = result  # 写入缓存
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
    key = source["key"]

    # 检查缓存
    if key in _rss_cache:
        cached = _rss_cache[key]
        age = time.time() - cached.get("fetched_at", 0)
        if age < RSS_CACHE_TTL:
            print("[RSS聚合] %s 使用缓存 (%.0f秒前)" % (name, age))
            return cached.get("items", [])

    try:
        raw = _fetch_url(url, timeout=FETCH_TIMEOUT, accept="application/rss+xml, application/xml, text/xml, application/atom+xml")
    except Exception as ex:
        print("[RSS聚合] %s 拉取失败: %s" % (name, ex), file=sys.stderr)
        return []

    root = None
    raw_str = None
    # 尝试直接解析
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as ex:
        orig_err = ex
        # 仅在检测到未闭合 CDATA 时尝试回退
        raw_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if "unclosed CDATA" in str(orig_err):
            try:
                text = raw_str.replace("<![CDATA[", "").replace("]]>", "")
                root = ET.fromstring(text)
            except ET.ParseError:
                pass  # 回退也失败，使用原始错误
        if root is None:
            print("[RSS聚合] %s 解析失败: %s" % (name, orig_err), file=sys.stderr)
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

    # 写入缓存
    _rss_cache[key] = {
        "items": items[:ITEMS_PER_SOURCE],
        "fetched_at": time.time()
    }

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
  --bg:#faf9f7; --card:#fffdf9; --card-2:#f3efe6; --card-3:#ebe6db;
  --ink:#1c1917; --muted:#5f594c; --faint:#857e74;
  --line:#ddd6c9; --line-strong:#b9b0a2;
  --brand:#2f5d8a; --brand-strong:#24496e; --brand-line:#b9cde0; --brand-weak:#e7eef4;
  --accent-solid:#9db8d4;
  --display:"Noto Serif SC","Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:"Noto Sans SC",-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"IBM Plex Mono","SF Mono","Fira Code","Fira Mono","Roboto Mono","Consolas",monospace;
  --radius:4px;
  --shadow:0 1px 2px rgba(28,25,23,.05);
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
.article-list-header .view-toggle {
  font-size:11px; color:var(--brand-strong); cursor:pointer;
  padding:2px 8px; border-radius:4px; border:1px solid var(--brand-line);
  background:var(--brand-weak); font-weight:600; white-space:nowrap;
  transition:all .15s;
}
.article-list-header .view-toggle:hover {
  background:var(--brand-line); color:#fff;
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
  padding:2px 8px; border-radius:var(--radius); font-size:11px; font-weight:600;
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
.reader-content .rc-lang-toggle {
  display:inline-flex; align-items:center; gap:0;
  margin-top:16px; border-radius:var(--radius); overflow:hidden;
  border:1px solid var(--line); font-size:12px;
}
.reader-content .rc-lang-toggle button {
  padding:4px 12px; border:none; background:transparent;
  color:var(--muted); cursor:pointer; transition:all .15s;
  font-family:var(--body); font-size:12px;
}
.reader-content .rc-lang-toggle button.active {
  background:var(--brand); color:#fff;
}
.reader-content .rc-lang-toggle button:hover:not(.active) {
  background:var(--brand-weak);
}
/* ── 阅读原文 iframe 模式 ── */
.reader-content .rc-mode-toggle {
  display:inline-flex; align-items:center; gap:0;
  margin-bottom:16px; border-radius:var(--radius); overflow:hidden;
  border:1px solid var(--line); font-size:12px;
}
.reader-content .rc-mode-toggle button {
  padding:5px 14px; border:none; background:transparent;
  color:var(--muted); cursor:pointer; transition:all .15s;
  font-family:var(--body); font-size:12px; font-weight:600;
}
.reader-content .rc-mode-toggle button.active {
  background:var(--brand); color:#fff;
}
.reader-content .rc-mode-toggle button:hover:not(.active) {
  background:var(--brand-weak);
}
.reader-content .rc-iframe-wrap {
  position:relative; margin-top:8px;
  border:1px solid var(--line); border-radius:var(--radius);
  background:#fff; overflow:hidden;
}
.reader-content .rc-iframe-bar {
  display:flex; align-items:center; justify-content:space-between;
  gap:8px; padding:6px 10px;
  background:var(--brand-weak); border-bottom:1px solid var(--line);
  font-size:12px; color:var(--muted);
}
.reader-content .rc-iframe-bar a {
  color:var(--brand-strong); font-weight:600; text-decoration:none;
}
.reader-content .rc-iframe-bar a:hover { text-decoration:underline; }
.reader-content .rc-iframe {
  display:block; width:100%; height:70vh; border:none; background:#fff;
}

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
  .sidebar-header { display:flex; flex-direction:column; padding:8px 10px 6px; }
  .sidebar-header h2 { font-size:12px; margin-bottom:4px; }
  .sidebar-search { padding:4px 8px; }
  .sidebar-search input { font-size:11px; }
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
  var viewMode = 'source'; // 'source' | 'timeline'
  var timelineItems = [];  // merged + sorted items for timeline view
  var summaryLang = 'original'; // 'original' | 'translated'
  var readerMode = 'summary'; // 'summary' | 'original'

  // ── DOM refs ──
  var sidebarEl = document.getElementById('sidebarSources');
  var articleListEl = document.getElementById('articleListItems');
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

  // ── Build timeline (merge all sources, sort by pub_date desc) ──
  function buildTimeline() {
    var all = [];
    SOURCES.forEach(function(src) {
      src.items.forEach(function(it) {
        all.push({ src: src, item: it });
      });
    });
    all.sort(function(a, b) {
      var da = new Date(a.item.pub_date || 0).getTime();
      var db = new Date(b.item.pub_date || 0).getTime();
      return db - da;
    });
    timelineItems = all;
  }

  // ── Render article list ──
  function renderArticleList() {
    if (viewMode === 'timeline') {
      renderTimelineList();
      return;
    }
    var src = SOURCES.find(function(s){ return s.key === activeSourceKey; });
    if (!src) {
      articleListHeaderEl.innerHTML = '<h3>选择一个信源</h3>';
      articleListEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">点击左侧信源查看文章</div>';
      return;
    }
    var items = filterItems(src.items);
    articleListHeaderEl.innerHTML = '<h3>'+esc(src.name)+'</h3><span class="count">'+items.length+' 篇</span><span class="view-toggle" data-mode="timeline">时间线</span>';

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
      html += '<span class="src-tag" style="background:'+esc(src.color)+'1f;color:'+esc(src.color)+'">'+esc(src.name)+'</span>';
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
    bindViewToggle();
  }

  // ── Render timeline list ──
  function renderTimelineList() {
    var filtered = timelineItems;
    if (searchQuery) {
      var q = searchQuery.toLowerCase();
      filtered = timelineItems.filter(function(o) {
        var t = (o.item.title_zh || o.item.title).toLowerCase();
        var s = (o.item.summary_zh || o.item.summary || '').toLowerCase();
        return t.indexOf(q) >= 0 || s.indexOf(q) >= 0;
      });
    }
    articleListHeaderEl.innerHTML = '<h3>时间线</h3><span class="count">'+filtered.length+' 篇</span><span class="view-toggle" data-mode="source">信源</span>';

    if (filtered.length === 0) {
      articleListEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">暂无匹配文章</div>';
      return;
    }

    var html = '';
    filtered.forEach(function(o, idx) {
      var cls = 'article-item' + (idx === activeArticleIdx ? ' active' : '');
      html += '<div class="'+cls+'" data-tidx="'+idx+'">';
      html += '<div class="a-title">'+esc(o.item.title_zh || o.item.title)+'</div>';
      html += '<div class="a-meta">';
      html += '<span class="src-tag" style="background:'+esc(o.src.color)+'1f;color:'+esc(o.src.color)+'">'+esc(o.src.name)+'</span>';
      html += '<span class="time">'+esc(o.item.time_str)+'</span>';
      html += '</div></div>';
    });
    articleListEl.innerHTML = html;

    articleListEl.querySelectorAll('.article-item').forEach(function(el) {
      el.addEventListener('click', function() {
        activeArticleIdx = parseInt(this.dataset.tidx);
        renderTimelineList();
        renderTimelineReader();
      });
    });
    bindViewToggle();
  }

  // ── Render reader for timeline ──
  function renderTimelineReader() {
    if (activeArticleIdx < 0 || activeArticleIdx >= timelineItems.length) {
      readerEl.innerHTML = '<div class="reader-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg><span>从列表选择一篇文章开始阅读</span></div>';
      return;
    }
    var o = timelineItems[activeArticleIdx];
    if (!o) return;
    var html = buildReaderContent(o.item, o.src, false);
    readerEl.innerHTML = html;
  }

  // ── View toggle ──
  function bindViewToggle() {
    var toggle = articleListHeaderEl.querySelector('.view-toggle');
    if (toggle) {
      toggle.addEventListener('click', function() {
        viewMode = this.dataset.mode;
        activeArticleIdx = -1;
        if (viewMode === 'timeline') buildTimeline();
        renderArticleList();
        if (viewMode === 'timeline') renderTimelineReader();
        else renderReader();
      });
    }
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

    var html = buildReaderContent(item, src, true);
    readerEl.innerHTML = html;
  }

  // ── 共享：构建阅读区内容（摘要/原文双模式） ─
  function buildReaderContent(item, src, showTransTag) {
    var html = '<div class="reader-content">';
    // 模式切换：摘要 | 阅读原文
    html += '<div class="rc-mode-toggle">';
    html += '<button class="'+(readerMode==='summary'?'active':'')+'" onclick="setReaderMode(&quot;summary&quot;)">摘要</button>';
    html += '<button class="'+(readerMode==='original'?'active':'')+'" onclick="setReaderMode(&quot;original&quot;)">阅读原文</button>';
    html += '</div>';
    // 标题
    html += '<h1 class="rc-title"><a href="'+esc(item.link)+'" target="_blank" rel="noopener">'+esc(item.title_zh || item.title)+'</a></h1>';
    // 元信息
    html += '<div class="rc-meta">';
    html += '<span class="src-tag" style="background:'+esc(src.color)+'1f;color:'+esc(src.color)+'">'+esc(src.name)+'</span>';
    html += '<span>'+esc(item.time_str)+'</span>';
    if (showTransTag && item.title_zh && item.title_zh !== item.title) {
      html += '<span style="font-size:11px;color:var(--faint)">（已翻译）</span>';
    }
    html += '</div>';

    if (readerMode === 'original') {
      // 原文模式：iframe 内嵌 + 降级提示
      html += '<div class="rc-iframe-wrap">';
      html += '<div class="rc-iframe-bar"><span>原文页面（若显示空白，该网站禁止内嵌）</span><a href="'+esc(item.link)+'" target="_blank" rel="noopener">新标签页打开 ↗</a></div>';
      html += '<iframe class="rc-iframe" src="'+esc(item.link)+'" sandbox="allow-scripts allow-same-origin allow-popups allow-forms" referrerpolicy="no-referrer"></iframe>';
      html += '</div>';
    } else {
      // 摘要模式：原有逻辑
      if (item.summary_zh || item.summary) {
        var summaryText = item.summary_zh || item.summary;
        html += '<div class="rc-summary" id="rcSummary"';
        if (summaryLang === 'translated') {
          html += ' lang="en" translate="yes"';
        }
        html += '>'+esc(summaryText)+'</div>';
        html += '<div class="rc-lang-toggle">';
        html += '<button class="'+(summaryLang==='original'?'active':'')+'" onclick="setSummaryLang(&quot;original&quot;)">原文</button>';
        html += '<button class="'+(summaryLang==='translated'?'active':'')+'" onclick="setSummaryLang(&quot;translated&quot;)">翻译</button>';
        html += '</div>';
      }
      html += '<a class="rc-link" href="'+esc(item.link)+'" target="_blank" rel="noopener">阅读原文 →</a>';
    }
    html += '</div>';
    return html;
  }

  // ── 阅读模式切换 ─
  function setReaderMode(mode) {
    readerMode = mode;
    if (viewMode === 'timeline') renderTimelineReader();
    else renderReader();
  }

  // ── 摘要语言切换 ─
  function setSummaryLang(lang) {
    summaryLang = lang;
    var summaryEl = document.getElementById('rcSummary');
    if (summaryEl) {
      if (lang === 'translated') {
        summaryEl.setAttribute('lang', 'en');
        summaryEl.setAttribute('translate', 'yes');
      } else {
        summaryEl.removeAttribute('lang');
        summaryEl.removeAttribute('translate');
      }
    }
    // 重新渲染以更新按钮状态
    renderReader();
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
  // Show loading indicator
  var sidebar = document.getElementById('sidebar');
  if(sidebar){
    var loading = document.createElement('span');
    loading.id = 'rssLiveTime';
    loading.style.cssText = 'font-size:10px;color:var(--faint);font-family:var(--mono);display:block;padding:4px 12px;';
    loading.textContent = '\u27f3 \u6b63\u5728\u83b7\u53d6\u6700\u65b0\u5185\u5bb9...';
    sidebar.appendChild(loading);
  }
  setTimeout(function(){
    var controller = new AbortController();
    var timeoutId = setTimeout(function(){ controller.abort(); }, 12000); // 12s timeout
    fetch('/api/rss', { signal: controller.signal }).then(function(r){
      clearTimeout(timeoutId);
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
        if(viewMode === 'timeline') buildTimeline();
        renderArticleList();
        renderReader();
        // Show live update time in sidebar header
        var sb = document.getElementById('sidebar');
        if(sb){
          var old = document.getElementById('rssLiveTime');
          if(old) old.remove();
          var span = document.createElement('span');
          span.id = 'rssLiveTime';
          span.style.cssText = 'font-size:10px;color:var(--faint);font-family:var(--mono);display:block;padding:4px 12px;';
          var now = new Date();
          span.textContent = '\u2713 \u5b9e\u65f6\u5df2\u66f4\u65b0 ' + now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
          sb.appendChild(span);
        }
        console.log('[RSS] Live updated:', updated, 'sources');
      }
    }).catch(function(e){
      // Update loading indicator on failure
      var sb = document.getElementById('sidebar');
      if(sb){
        var old = document.getElementById('rssLiveTime');
        if(old) old.remove();
        var span = document.createElement('span');
        span.id = 'rssLiveTime';
        span.style.cssText = 'font-size:10px;color:var(--faint);font-family:var(--mono);display:block;padding:4px 12px;';
        span.textContent = '\u00b7 \u663e\u793a\u9759\u6001\u6570\u636e\uff08\u5b9e\u65f6\u83b7\u53d6\u8d85\u65f6\uff09';
        sb.appendChild(span);
      }
      console.warn('[RSS] Live update failed:', e.message);
    });
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
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700;900&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
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
        '</div></div>'
        '<div id="sidebarSources"></div></div>\n'
        '<div class="article-list" id="articleList">'
        '<div class="article-list-header" id="articleListHeader"><h3>选择一个信源</h3></div>'
        '<div id="articleListItems"><div style="padding:20px;text-align:center;color:var(--faint);font-size:13px">点击左侧信源查看文章</div></div>'
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

    # 加载缓存
    _load_caches()

    sources_with_items = []
    total_items = 0
    ok_count = 0

    # 串行抓取 RSS（短超时，失败快速跳过）
    for src in RSS_SOURCES:
        items = _fetch_rss(src)
        n = len(items)
        if n > 0:
            ok_count += 1

        # 只翻译标题（摘要保留原文，用户可用浏览器翻译）
        for it in items:
            it["title_zh"] = _translate_to_zh(it["title"]) if it["title"] else it["title"]
            it["summary_zh"] = it.get("summary", "")  # 摘要不翻译，保留原文
            it["time_str"] = _fmt_rel_time(it.get("pub_date"))
            # 保留 pub_date 用于前端时间线排序（转为 ISO 字符串）
            pd = it.get("pub_date")
            if pd and hasattr(pd, 'isoformat'):
                it["pub_date"] = pd.isoformat()

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

    # 打印翻译统计
    print("[翻译统计] 缓存命中: %d, Google: %d, MyMemory: %d, Dict: %d, 跳过: %d, 失败: %d" % (
        _TRANS_STATS["cache_hit"], _TRANS_STATS["google"], _TRANS_STATS["mymemory"],
        _TRANS_STATS["dict"], _TRANS_STATS["skip"], _TRANS_STATS["fail"]
    ))

    # 保存缓存
    _save_caches()

    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
