# -*- coding: utf-8 -*-
"""Generate rss-aggregator.html — 多路 RSS 新闻源聚合阅读器。
构建时由 fetch_and_build.py 调用，Python 标准库抓取 RSS → 翻译 → 生成静态 HTML。

布局：卡片墙 + 抽屉阅读器（信源面板 | 卡片墙 | 阅读抽屉）
功能：信源分类筛选、全局搜索、标题/摘要翻译、响应式三端适配、主题切换。
"""
import html as html_mod
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

OUT = "rss-aggregator.html"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Accept": "application/rss+xml, application/xml, text/xml, */*"}

# ── 缓存配置 ──
TRANS_CACHE_FILE = "translations.json"
RSS_CACHE_FILE = "rss_cache.json"
RSS_CACHE_TTL = 1800  # RSS 缓存有效期：30 分钟

# ── 缓存数据 ──
_trans_cache = {}  # {text_hash: translated_text}
_rss_cache = {}    # {source_key: {"items": [...], "fetched_at": timestamp}}

# ── 72 小时内容累积 ──
RSS_HISTORY_FILE = "rss_history.json"
RSS_HISTORY_HOURS = 72
_rss_history = {}  # {link: {source, source_key, cat, color, title, title_zh, summary, summary_zh, pub_date, time_str}}

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

def _load_history():
    """加载 72 小时文章历史"""
    global _rss_history
    if os.path.exists(RSS_HISTORY_FILE):
        try:
            with open(RSS_HISTORY_FILE, "r", encoding="utf-8") as f:
                _rss_history = json.load(f)
            print("[历史] 加载文章历史: %d 篇" % len(_rss_history))
        except Exception as e:
            print("[历史] 加载失败: %s" % e, file=sys.stderr)
            _rss_history = {}


def _save_history():
    """保存 72 小时文章历史"""
    try:
        with open(RSS_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_rss_history, f, ensure_ascii=False)
        print("[历史] 保存文章历史: %d 篇" % len(_rss_history))
    except Exception as e:
        print("[历史] 保存失败: %s" % e, file=sys.stderr)


def _accumulate_history(sources_with_items):
    """将新抓取的文章合并到 72 小时历史，裁剪过期内容，返回重组后的 sources_with_items"""
    now_bj = _now_bj()
    cutoff = now_bj.replace(tzinfo=None) - datetime.timedelta(hours=RSS_HISTORY_HOURS)

    # 合并新文章（按 link 去重，新数据覆盖旧数据）
    new_count = 0
    for src in sources_with_items:
        for it in src.get("items", []):
            link = it.get("link", "")
            if not link:
                continue
            pd_str = it.get("pub_date", "")
            # 解析日期：无日期或解析失败时使用当前时间作为回退
            pd_bj = now_bj.replace(tzinfo=None)  # 默认当前时间
            if pd_str:
                try:
                    pd = datetime.datetime.fromisoformat(pd_str)
                    if pd.tzinfo:
                        pd_bj = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
                    else:
                        pd_bj = pd
                except ValueError:
                    pass  # 保持默认当前时间
            if pd_bj < cutoff:
                continue  # 过期文章跳过
            _rss_history[link] = {
                "link": link,
                "source": src["name"], "source_key": src["key"],
                "cat": src["cat"], "color": src["color"],
                "title": it.get("title", ""), "title_zh": it.get("title_zh", ""),
                "summary": it.get("summary", ""), "summary_zh": it.get("summary_zh", ""),
                "full_content": it.get("full_content", ""),
                "pub_date": pd_str,
            }
            new_count += 1

    # 裁剪超过 72 小时的旧文章
    before = len(_rss_history)
    expired = []
    for link, item in _rss_history.items():
        pd_str = item.get("pub_date", "")
        pd_bj = now_bj.replace(tzinfo=None)  # 默认当前时间
        if pd_str:
            try:
                pd = datetime.datetime.fromisoformat(pd_str)
                if pd.tzinfo:
                    pd_bj = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
                else:
                    pd_bj = pd
            except ValueError:
                pass  # 保持默认当前时间
        if pd_bj < cutoff:
            expired.append(link)
    for link in expired:
        del _rss_history[link]

    # 按源重组，更新相对时间
    src_map = {}
    for src in sources_with_items:
        src_map[src["key"]] = {
            "key": src["key"], "name": src["name"],
            "cat": src["cat"], "color": src["color"],
            "tier": src.get("tier", 3), "items": [],
        }
    for item in _rss_history.values():
        sk = item["source_key"]
        if sk in src_map:
            entry = dict(item)
            entry["time_str"] = _fmt_rel_time(entry.get("pub_date"))
            src_map[sk]["items"].append(entry)

    result = list(src_map.values())
    total = sum(len(s["items"]) for s in result)
    pruned = before - len(_rss_history)
    print("[历史] 合并 %d 篇新文，裁剪 %d 篇过期，保留 %d 篇（%d 小时窗口）" % (
        new_count, pruned, len(_rss_history), RSS_HISTORY_HOURS))
    return result, total


def _load_snapshot_meta():
    """从现有快照读取 meta.last_fetch（各源上次抓取时间）"""
    try:
        with open("rss_api_snapshot.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("meta", {}).get("last_fetch", {})
    except Exception:
        return {}


def _save_api_snapshot(sources_with_items, meta=None):
    """生成 API 快照 JSON，供 /api/rss 直接返回，避免实时抓取丢失历史累积数据"""
    snapshot_sources = []
    for src in sources_with_items:
        items = []
        for it in src.get("items", []):
            item = {
                "t": it.get("title_zh", "") or it.get("title", ""),
                "u": it.get("link", "#"),
                "s": it.get("summary_zh", "") or it.get("summary", ""),
                "d": it.get("pub_date", ""),
            }
            fc = it.get("full_content", "")
            if fc:
                item["fc"] = fc[:50000]
            items.append(item)
        snapshot_sources.append({
            "key": src["key"], "name": src["name"],
            "cat": src["cat"], "color": src["color"],
            "tier": src.get("tier", 3), "items": items,
        })
    snapshot = {
        "t": _now_bj().isoformat(),
        "sources": snapshot_sources,
    }
    if meta:
        snapshot["meta"] = meta
    try:
        with open("rss_api_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        total_items = sum(len(s["items"]) for s in snapshot_sources)
        print("[快照] 保存 API 快照: %d 源, %d 篇" % (len(snapshot_sources), total_items))
    except Exception as e:
        print("[快照] 保存失败: %s" % e, file=sys.stderr)


# ── RSS 信源配置（按分类组织，含 BestBlogs 559 源，tier 分层） ─
RSS_SOURCES = [
    # ── AI 日报 (26) ──
    {"key": "agihunt_0", "name": "AGI Hunt", "cat": "ai", "url": "https://agihunt.info/feed.xml", "color": "#6366f1", "tier": 1},
    {"key": "openai_blog_1", "name": "OpenAI 博客", "cat": "ai", "url": "https://openai.com/news/rss.xml", "color": "#10a37f"},
    {"key": "google_deepmind_2", "name": "Google DeepMind", "cat": "ai", "url": "https://deepmind.google/blog/rss.xml", "color": "#4285f4"},
    {"key": "google_ai_blog_3", "name": "Google AI Blog", "cat": "ai", "url": "https://blog.google/technology/ai/rss/", "color": "#34a853"},
    {"key": "arxiv_ai_4", "name": "arXiv AI", "cat": "ai", "url": "https://rss.arxiv.org/rss/cs.AI", "color": "#b31b1b", "tier": 1},
    {"key": "arxiv_ml_5", "name": "arXiv 机器学习", "cat": "ai", "url": "https://rss.arxiv.org/rss/cs.LG", "color": "#c62828", "tier": 1},
    {"key": "arxiv_nlp_6", "name": "arXiv NLP", "cat": "ai", "url": "https://rss.arxiv.org/rss/cs.CL", "color": "#d84315", "tier": 1},
    {"key": "hn_ai_7", "name": "Hacker News AI", "cat": "ai", "url": "https://hnrss.org/newest?q=AI", "color": "#ff6600", "tier": 1},
    {"key": "hn_llm_8", "name": "Hacker News LLM", "cat": "ai", "url": "https://hnrss.org/newest?q=LLM", "color": "#ef6c00", "tier": 2},
    {"key": "hn_openclaw_9", "name": "Hacker News OpenClaw", "cat": "ai", "url": "https://hnrss.org/newest?q=OpenClaw", "color": "#f57c00"},
    {"key": "google_research_10", "name": "Google Research Blog", "cat": "ai", "url": "https://research.google/blog/rss/", "color": "#4285f4"},
    {"key": "huggingface_11", "name": "Hugging Face 博客", "cat": "ai", "url": "https://huggingface.co/blog/feed.xml", "color": "#ffd21e"},
    {"key": "simonwillison_12", "name": "Simon Willison's Blog", "cat": "ai", "url": "https://simonwillison.net/atom/everything/", "color": "#5c6bc0"},
    {"key": "openclaw_rel_13", "name": "OpenClaw Releases", "cat": "ai", "url": "https://github.com/openclaw/openclaw/releases.atom", "color": "#7e57c2"},
    {"key": "openclaw_commits_14", "name": "OpenClaw Commits", "cat": "ai", "url": "https://github.com/openclaw/openclaw/commits/main.atom", "color": "#9575cd", "tier": 1},
    {"key": "codex_rel_15", "name": "OpenAI Codex Releases", "cat": "ai", "url": "https://github.com/openai/codex/releases.atom", "color": "#10a37f"},
    {"key": "claude_code_rel_16", "name": "Claude Code Releases", "cat": "ai", "url": "https://github.com/anthropics/claude-code/releases.atom", "color": "#d4a574"},
    {"key": "gemini_cli_rel_17", "name": "Gemini CLI Releases", "cat": "ai", "url": "https://github.com/google-gemini/gemini-cli/releases.atom", "color": "#4285f4"},
    {"key": "mcp_spec_rel_18", "name": "MCP Specification Releases", "cat": "ai", "url": "https://github.com/modelcontextprotocol/specification/releases.atom", "color": "#7c3aed"},
    {"key": "mcp_servers_rel_19", "name": "MCP Servers Releases", "cat": "ai", "url": "https://github.com/modelcontextprotocol/servers/releases.atom", "color": "#6d28d9"},
    {"key": "aihot_summary_20", "name": "AI Hot 精选摘要", "cat": "ai", "url": "https://aihot.virxact.com/feed.xml?aihot_actor=0e9cbfcd-db8f-47d6-8c0a-3113a26f3f9c", "color": "#f97316"},
    {"key": "aihot_full_21", "name": "AI Hot 精选全文", "cat": "ai", "url": "https://aihot.virxact.com/feed/full.xml?aihot_actor=0e9cbfcd-db8f-47d6-8c0a-3113a26f3f9c", "color": "#ea580c", "tier": 2},
    {"key": "aihot_pool_22", "name": "AI Hot 7天公开池", "cat": "ai", "url": "https://aihot.virxact.com/feed/all.xml?aihot_actor=0e9cbfcd-db8f-47d6-8c0a-3113a26f3f9c", "color": "#dc2626", "tier": 1},
    {"key": "reddit_ml_103", "name": "r/MachineLearning", "cat": "ai", "url": "https://www.reddit.com/r/MachineLearning/top.rss?t=day", "color": "#d32f2f"},
    {"key": "reddit_localllama_104", "name": "r/LocalLLaMA", "cat": "ai", "url": "https://www.reddit.com/r/LocalLLaMA/top.rss?t=day", "color": "#f59e0b"},
    {"key": "reddit_artificial_105", "name": "r/artificial", "cat": "ai", "url": "https://www.reddit.com/r/artificial/top.rss?t=day", "color": "#7c3aed"},

    # ── 科技资讯 (31) ──
    {"key": "juliaevans_0", "name": "Julia Evans", "cat": "tech", "url": "https://jvns.ca/atom.xml", "color": "#e31937"},
    {"key": "overreacted_2", "name": "Overreacted", "cat": "tech", "url": "https://overreacted.io/rss.xml", "color": "#b31b1b"},
    {"key": "webdev_3", "name": "web.dev", "cat": "tech", "url": "https://web.dev/feed.xml", "color": "#000000"},
    {"key": "engadget_4", "name": "Engadget", "cat": "tech", "url": "http://www.engadget.com/rss.xml", "color": "#2563eb", "tier": 2},
    {"key": "joshcomeau_5", "name": "Josh Comeau", "cat": "tech", "url": "https://www.joshwcomeau.com/rss.xml", "color": "#7c3aed"},
    {"key": "hackernews_6", "name": "Hacker News", "cat": "tech", "url": "https://hnrss.org/frontpage", "color": "#ff6600", "tier": 1},
    {"key": "techcrunch_7", "name": "TechCrunch", "cat": "tech", "url": "https://techcrunch.com/feed/", "color": "#0a9e01", "tier": 2},
    {"key": "techcrunchai_7b", "name": "TechCrunch AI", "cat": "tech", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "color": "#d97706", "tier": 2},
    {"key": "theverge_8", "name": "The Verge", "cat": "tech", "url": "https://www.theverge.com/rss/index.xml", "color": "#e61919", "tier": 2},
    {"key": "thevergeai_8b", "name": "The Verge AI", "cat": "tech", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "color": "#dc2626"},
    {"key": "wired_10", "name": "WIRED", "cat": "tech", "url": "https://www.wired.com/feed/rss", "color": "#4f46e5", "tier": 2},
    {"key": "atlasnote_11", "name": "AtlasNote", "cat": "tech", "url": "https://atlasnote.ai/rss.xml", "color": "#ca8a04"},
    {"key": "redisblog_12", "name": "Redis Blog", "cat": "tech", "url": "https://redis.io/feed/", "color": "#0891b2"},
    {"key": "arxiv_cs_14", "name": "arXiv CS", "cat": "tech", "url": "https://export.arxiv.org/rss/cs", "color": "#b31b1b"},
    {"key": "arstechnica_60", "name": "Ars Technica", "cat": "tech", "url": "https://feeds.arstechnica.com/arstechnica/index", "color": "#ff6600", "tier": 2},
    {"key": "mit_tech_review_61", "name": "MIT Technology Review", "cat": "tech", "url": "https://www.technologyreview.com/feed/", "color": "#a50034"},
    {"key": "krebs_62", "name": "Krebs on Security", "cat": "tech", "url": "https://krebsonsecurity.com/feed/", "color": "#1a1a1a"},
    {"key": "thehackernews_63", "name": "The Hacker News", "cat": "tech", "url": "https://feeds.feedburner.com/TheHackersNews", "color": "#e53935", "tier": 2},
    {"key": "schneier_64", "name": "Schneier on Security", "cat": "tech", "url": "https://www.schneier.com/feed/", "color": "#37474f"},
    {"key": "github_blog_70", "name": "GitHub Blog", "cat": "tech", "url": "https://github.blog/feed/", "color": "#24292e"},
    {"key": "github_changelog_71", "name": "GitHub Changelog", "cat": "tech", "url": "https://github.blog/changelog/feed/", "color": "#2d333b"},
    {"key": "github_copilot_72", "name": "GitHub Copilot Changelog", "cat": "tech", "url": "https://github.blog/changelog/label/copilot/feed/", "color": "#6e40c9"},
    {"key": "netflix_tech_73", "name": "Netflix Tech Blog", "cat": "tech", "url": "https://netflixtechblog.com/feed", "color": "#e50914"},
    {"key": "aws_blog_74", "name": "AWS Blog", "cat": "tech", "url": "https://aws.amazon.com/blogs/aws/feed/", "color": "#ff9900"},
    {"key": "cloudflare_blog_75", "name": "Cloudflare Blog", "cat": "tech", "url": "https://blog.cloudflare.com/rss/", "color": "#f38020"},
    {"key": "google_dev_76", "name": "Google Developers", "cat": "tech", "url": "https://developers.googleblog.com/feeds/posts/default/", "color": "#4285f4"},
    {"key": "mozilla_hacks_77", "name": "Mozilla Hacks", "cat": "tech", "url": "https://hacks.mozilla.org/feed/", "color": "#000000"},
    {"key": "vercel_blog_78", "name": "Vercel Blog", "cat": "tech", "url": "https://vercel.com/atom", "color": "#000000"},
    {"key": "supabase_blog_79", "name": "Supabase Blog", "cat": "tech", "url": "https://supabase.com/rss.xml", "color": "#3ecf8e"},
    {"key": "stripe_blog_80", "name": "Stripe Blog", "cat": "tech", "url": "https://stripe.com/blog/feed.rss", "color": "#635bff"},
    {"key": "meta_eng_81", "name": "Meta Engineering", "cat": "tech", "url": "https://engineering.fb.com/feed/", "color": "#0668E1"},

    # ── 中文科技 (21) ──
    {"key": "美团技术团队_0", "name": "美团技术团队", "cat": "cn_tech", "url": "https://tech.meituan.com/feed", "color": "#0055ff"},
    {"key": "v2ex_1", "name": "V2EX", "cat": "cn_tech", "url": "https://v2ex.com/index.xml", "color": "#d7434e", "tier": 1},
    {"key": "solidot_3", "name": "Solidot", "cat": "cn_tech", "url": "https://www.solidot.org/index.rss", "color": "#0066ff", "tier": 2},
    {"key": "少数派_4", "name": "少数派", "cat": "cn_tech", "url": "https://sspai.com/feed", "color": "#336699"},
    {"key": "爱范儿_5", "name": "爱范儿", "cat": "cn_tech", "url": "https://www.ifanr.com/feed", "color": "#333333"},
    {"key": "小众软件_8", "name": "小众软件", "cat": "cn_tech", "url": "https://www.appinn.com/feed/", "color": "#FFD43B"},
    {"key": "构建被动收入_9", "name": "构建被动收入", "cat": "cn_tech", "url": "https://www.bmpi.dev/index.xml", "color": "#00bc74"},
    {"key": "虎嗅_11", "name": "虎嗅", "cat": "cn_tech", "url": "https://rsshub.bestblogs.dev/huxiu/article", "color": "#3a85ff", "tier": 1},
    {"key": "it之家_13", "name": "IT之家", "cat": "cn_tech", "url": "https://www.ithome.com/rss/", "color": "#1e88e5", "tier": 1},
    {"key": "月光博客_15", "name": "月光博客", "cat": "cn_tech", "url": "http://www.williamlong.info/rss.xml", "color": "#e53935"},
    {"key": "理想生活实验室_18", "name": "理想生活实验室", "cat": "cn_tech", "url": "https://www.toodaylab.com/feed", "color": "#43a047"},
    {"key": "潮流周刊_21", "name": "潮流周刊", "cat": "cn_tech", "url": "https://weekly.tw93.fun/rss.xml", "color": "#ff5722"},
    {"key": "扯氮集_25", "name": "扯氮集", "cat": "cn_tech", "url": "http://weiwuhui.com/feed", "color": "#6a1b9a"},
    {"key": "deepzz_26", "name": "Deepzz", "cat": "cn_tech", "url": "https://deepzz.com/feed", "color": "#d32f2f"},
    {"key": "mit科技评论_28", "name": "MIT科技评论", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/mittrchina/hot", "color": "#0097a7"},
    {"key": "疯投圈_29", "name": "疯投圈", "cat": "cn_tech", "url": "https://crazy.capital/feed", "color": "#c62828"},
    {"key": "超能网_31", "name": "超能网", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/expreview", "color": "#0091ea", "tier": 2},
    {"key": "钛媒体_38", "name": "钛媒体", "cat": "cn_tech", "url": "https://www.tmtpost.com/feed", "color": "#4a90d9", "tier": 1},
    {"key": "人人都是产品经理_39", "name": "人人都是产品经理", "cat": "cn_tech", "url": "https://www.woshipm.com/feed", "color": "#00aa55", "tier": 2},
    {"key": "cnbeta_41", "name": "cnBeta", "cat": "cn_tech", "url": "https://plink.anyfeeder.com/cnbeta", "color": "#00bc74", "tier": 1},
    {"key": "v2ex技术_44", "name": "V2EX技术", "cat": "cn_tech", "url": "https://www.v2ex.com/feed/tab/tech.xml", "color": "#3177cf", "tier": 1},

    # ── 开发者 (53) ──
    {"key": "阮一峰的网络日志_0", "name": "阮一峰的网络日志", "cat": "dev", "url": "https://www.ruanyifeng.com/blog/atom.xml", "color": "#dc382d"},
    {"key": "太隐_4", "name": "太隐", "cat": "dev", "url": "https://wangyurui.com/feed.xml", "color": "#336699"},
    {"key": "云风的blog_5", "name": "云风的BLOG", "cat": "dev", "url": "http://blog.codingnow.com/atom.xml", "color": "#4CAF50"},
    {"key": "胡涂说_6", "name": "胡涂说", "cat": "dev", "url": "https://hutusi.com/feed.xml", "color": "#8e44ad"},
    {"key": "程序员的喵_7", "name": "程序员的喵", "cat": "dev", "url": "https://catcoding.me/atom.xml", "color": "#6c5ce7"},
    {"key": "oldjblog_8", "name": "oldj blog", "cat": "dev", "url": "https://oldj.net/feed", "color": "#2d3436"},
    {"key": "randy'sblog_12", "name": "Randy's Blog", "cat": "dev", "url": "https://lutaonan.com/rss.xml", "color": "#e67e22"},
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
    {"key": "infoq推荐_26", "name": "InfoQ推荐", "cat": "dev", "url": "https://plink.anyfeeder.com/infoq/recommend", "color": "#6c5ce7", "tier": 2},
    {"key": "二丫讲梵_27", "name": "二丫讲梵", "cat": "dev", "url": "https://wiki.eryajf.net/rss.xml", "color": "#2d3436"},
    {"key": "唐巧博客_28", "name": "唐巧博客", "cat": "dev", "url": "http://blog.devtang.com/atom.xml", "color": "#e74c3c"},
    {"key": "baiyun_30", "name": "BAI YUN", "cat": "dev", "url": "https://baiyun.me/feed", "color": "#2c3e50"},
    {"key": "elmagnifico_31", "name": "elmagnifico", "cat": "dev", "url": "http://elmagnifico.tech/feed.xml", "color": "#e67e22"},
    {"key": "tonybai_33", "name": "Tony Bai", "cat": "dev", "url": "http://tonybai.com/feed/", "color": "#1abc9c"},
    {"key": "全栈应用开发_36", "name": "全栈应用开发", "cat": "dev", "url": "https://www.phodal.com/blog/feeds/rss/", "color": "#16a085"},
    {"key": "tinyprojects_37", "name": "Tiny Projects", "cat": "dev", "url": "https://tinyprojects.dev/feed.xml", "color": "#f39c12"},
    {"key": "笨方法学写作_38", "name": "笨方法学写作", "cat": "dev", "url": "https://www.cnfeat.com/feed.xml", "color": "#dc382d"},
    {"key": "西秦公子_39", "name": "西秦公子", "cat": "dev", "url": "https://www.ixiqin.com/feed/", "color": "#6366f1"},
    {"key": "涛叔_41", "name": "涛叔", "cat": "dev", "url": "https://taoshu.in/feed.xml", "color": "#663399"},
    {"key": "小球飞鱼_42", "name": "小球飞鱼", "cat": "dev", "url": "https://mantyke.icu/index.xml", "color": "#336699"},
    {"key": "王登科dk_43", "name": "王登科DK", "cat": "dev", "url": "https://greatdk.com/feed", "color": "#4CAF50"},
    {"key": "小胡子哥_44", "name": "小胡子哥", "cat": "dev", "url": "http://www.barretlee.com/rss2.xml", "color": "#8e44ad", "tier": 2},
    {"key": "dbanotes_45", "name": "DBA Notes", "cat": "dev", "url": "http://dbanotes.net/feed", "color": "#6c5ce7"},
    {"key": "v2ex_all_50", "name": "V2EX 全站最新", "cat": "dev", "url": "https://www.v2ex.com/index.xml", "color": "#d7434e", "tier": 1},
    {"key": "v2ex_new_51", "name": "V2EX 最新", "cat": "dev", "url": "https://www.v2ex.com/feed/tab/all.xml", "color": "#e53935", "tier": 1},
    {"key": "v2ex_creative_52", "name": "V2EX 创意", "cat": "dev", "url": "https://www.v2ex.com/feed/tab/creative.xml", "color": "#8e24aa", "tier": 1},
    {"key": "v2ex_play_53", "name": "V2EX 好玩", "cat": "dev", "url": "https://www.v2ex.com/feed/tab/play.xml", "color": "#43a047", "tier": 1},
    {"key": "nodeseek_54", "name": "NodeSeek", "cat": "dev", "url": "https://rss.nodeseek.com/", "color": "#1e88e5", "tier": 1},
    {"key": "naixi_55", "name": "奶昔论坛", "cat": "dev", "url": "https://forum.naixi.net/forum.php?mod=rss", "color": "#f06292", "tier": 2},
    {"key": "hn_newest_56", "name": "Hacker News 最新", "cat": "dev", "url": "https://hnrss.org/newest", "color": "#ff6600", "tier": 1},
    {"key": "hn_ask_57", "name": "Hacker News Ask", "cat": "dev", "url": "https://hnrss.org/ask", "color": "#ef6c00", "tier": 2},
    {"key": "hn_show_58", "name": "Hacker News Show", "cat": "dev", "url": "https://hnrss.org/show", "color": "#f57c00", "tier": 1},
    {"key": "linuxdo_latest_59", "name": "LinuxDo 最新话题", "cat": "dev", "url": "https://linux.do/latest.rss", "color": "#2d8cff"},
    {"key": "linuxdo_top_60", "name": "LinuxDo 热门话题", "cat": "dev", "url": "https://linux.do/top.rss", "color": "#1a73e8"},
    {"key": "linuxdo_posts_61", "name": "LinuxDo 最新帖子", "cat": "dev", "url": "https://linux.do/posts.rss", "color": "#4a90d9"},
    {"key": "js_weekly_90", "name": "JavaScript Weekly", "cat": "dev", "url": "https://javascriptweekly.com/rss/", "color": "#f7df1e"},
    {"key": "rust_weekly_91", "name": "This Week in Rust", "cat": "dev", "url": "https://this-week-in-rust.org/atom.xml", "color": "#dea584"},
    {"key": "golang_weekly_92", "name": "Golang Weekly", "cat": "dev", "url": "https://golangweekly.com/rss/", "color": "#00add8"},
    {"key": "bytebytego_93", "name": "ByteByteGo", "cat": "dev", "url": "https://blog.bytebytego.com/feed", "color": "#e53935"},
    {"key": "reddit_programming_100", "name": "r/programming", "cat": "dev", "url": "https://www.reddit.com/r/programming/top.rss?t=day", "color": "#ff4500"},
    {"key": "reddit_webdev_101", "name": "r/webdev", "cat": "dev", "url": "https://www.reddit.com/r/webdev/top.rss?t=day", "color": "#0079d4"},
    {"key": "reddit_selfhosted_102", "name": "r/selfhosted", "cat": "dev", "url": "https://www.reddit.com/r/selfhosted/top.rss?t=day", "color": "#4caf50"},

    # ── 综合新闻 (14) ──
    {"key": "idaily_1", "name": "iDaily", "cat": "news", "url": "https://plink.anyfeeder.com/idaily/today", "color": "#003399"},
    {"key": "中国日报双语_2", "name": "中国日报双语", "cat": "news", "url": "https://plink.anyfeeder.com/chinadaily/dual", "color": "#cc0000"},
    {"key": "知乎日报anyfeeder_3", "name": "知乎日报anyfeeder", "cat": "news", "url": "https://plink.anyfeeder.com/zhihu/daily", "color": "#d32f2f", "tier": 2},
    {"key": "法广中文_4", "name": "法广中文", "cat": "news", "url": "https://plink.anyfeeder.com/rfi/cn", "color": "#1a1a1a", "tier": 2},
    {"key": "bbc中文_5", "name": "BBC中文", "cat": "news", "url": "https://plink.anyfeeder.com/bbc/cn", "color": "#cc0000"},
    {"key": "财富中文网_6", "name": "财富中文网", "cat": "news", "url": "https://plink.anyfeeder.com/fortunechina", "color": "#d32f2f"},
    {"key": "澎湃新闻_7", "name": "澎湃新闻", "cat": "news", "url": "https://plink.anyfeeder.com/thepaper", "color": "#43a047", "tier": 1},
    {"key": "人民网_8", "name": "人民网", "cat": "news", "url": "https://plink.anyfeeder.com/people", "color": "#1565c0", "tier": 1},
    {"key": "南方周末anyfeeder_9", "name": "南方周末anyfeeder", "cat": "news", "url": "https://plink.anyfeeder.com/infzm/news", "color": "#0097a7"},
    {"key": "纽约时报中文网_10", "name": "纽约时报中文网", "cat": "news", "url": "http://cn.nytimes.com/rss/news.xml", "color": "#1a1a1a"},
    {"key": "喷嚏网铂程斋_11", "name": "喷嚏网铂程斋", "cat": "news", "url": "https://plink.anyfeeder.com/dapenti/xilei", "color": "#1565c0", "tier": 2},
    {"key": "雪球热帖_12", "name": "雪球热帖", "cat": "news", "url": "https://xueqiu.com/hots/topic/rss", "color": "#0097a7"},
    {"key": "bbc英语教学_13", "name": "BBC英语教学", "cat": "news", "url": "https://plink.anyfeeder.com/bbc/learningenglish", "color": "#bb1919"},
    {"key": "求是网_14", "name": "求是网", "cat": "news", "url": "https://plink.anyfeeder.com/qstheory", "color": "#6a1b9a"},

    # ── 播客 (6) ──
    {"key": "42章经_1", "name": "42章经", "cat": "podcast", "url": "https://feed.xyzfm.space/evgg6xle9rdc", "color": "#0891b2"},
    {"key": "三点下班_4", "name": "三点下班", "cat": "podcast", "url": "https://feed.xyzfm.space/tlel9j4tg3eu", "color": "#e11d48"},
    {"key": "卫诗婕商业漫谈_6", "name": "卫诗婕商业漫谈", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6627fda4b56459544087d86a", "color": "#7c3aed"},
    {"key": "得意忘形_7", "name": "得意忘形", "cat": "podcast", "url": "https://feed.xyzfm.space/klaak6nmc3ux", "color": "#0891b2"},
    {"key": "起朱楼宴宾客_8", "name": "起朱楼宴宾客", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65253bf350cf691d245b29aa", "color": "#1e40af"},
    {"key": "tedradiohour_10", "name": "TED Radio Hour", "cat": "podcast", "url": "https://feeds.npr.org/510298/podcast.xml", "color": "#e11d48"},

    # ── BestBlogs 公众号 (375) ──
    {"key": "人人都是产品经理_0", "name": "人人都是产品经理", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2d790e38f8af54c5af77fa5fed687a7c66d34c22.xml", "color": "#ff6b6b"},
    {"key": "腾讯技术工程_1", "name": "腾讯技术工程", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1e0ac39f8952b2e7f0807313cf2633d25078a171.xml", "color": "#ff6b6b"},
    {"key": "阿里技术_2", "name": "阿里技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6535a444e9651fecae3383363be7589acdebe2b6.xml", "color": "#ff6b6b"},
    {"key": "阿里云开发者_3", "name": "阿里云开发者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/39fc51b0b1316137e608c45da5dbbca4f9eb9538.xml", "color": "#ff6b6b"},
    {"key": "大淘宝技术_4", "name": "大淘宝技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/26fef2307bebc8673703f7e726982d8f56c9a219.xml", "color": "#ff6b6b"},
    {"key": "新智元_5", "name": "新智元", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e531a18b21c34cf787b83ab444eef659d7a980de.xml", "color": "#ff6b6b"},
    {"key": "腾讯云开发者_6", "name": "腾讯云开发者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6cec2c211479a5502896375860009782cf10c2ba.xml", "color": "#ff6b6b"},
    {"key": "前端早读课_7", "name": "前端早读课", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ce2456e157156d42259c1198f05a33e27b1ed959.xml", "color": "#ff6b6b"},
    {"key": "founder_park_8", "name": "Founder Park", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f940695505f2be1399d23cc98182297cadf6f90d.xml", "color": "#ff6b6b"},
    {"key": "歸藏的ai工具箱_9", "name": "歸藏的AI工具箱", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1c3e3571b1627d23ee9c64521a0b0a41d3fe2987.xml", "color": "#ff6b6b"},
    {"key": "腾讯科技_10", "name": "腾讯科技", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a81bdfcbb9eefe870d285e81510ffa1af26e4520.xml", "color": "#ff6b6b"},
    {"key": "infoq_11", "name": "InfoQ", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/13da94d7eb314b49fa251cb7e8399cae29d772db.xml", "color": "#ff6b6b"},
    {"key": "赛博禅心_12", "name": "赛博禅心", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/752c31ca0446b837339463fc5440539e20267d2f.xml", "color": "#ff6b6b"},
    {"key": "数字生命卡兹克_13", "name": "数字生命卡兹克", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ff621c3e98d6ae6fceb3397e57441ffc6ea3c17f.xml", "color": "#ff6b6b"},
    {"key": "十字路口crossing_14", "name": "十字路口Crossing", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/20492a5f2d3637c178c01ab0bab7ed86a4a0995b.xml", "color": "#ff6b6b"},
    {"key": "极客公园_15", "name": "极客公园", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/11ea7163fbea99e2ab9fa2812ac3d179574886cc.xml", "color": "#ff6b6b"},
    {"key": "京东技术_16", "name": "京东技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fa0be550682410cc187c0d1eab1a0fc4e073b949.xml", "color": "#ff6b6b"},
    {"key": "web3天空之城_17", "name": "Web3天空之城", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6aac3cc6d4c6df6fb3f77dea4ea4ba4a2053d6e7.xml", "color": "#ff6b6b"},
    {"key": "ai前线_18", "name": "AI前线", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/25185b01482da0f485418ecb92e208b4416712fb.xml", "color": "#ff6b6b"},
    {"key": "51cto技术栈_19", "name": "51CTO技术栈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d1fabe6c569ffc44979075dde2f57c65e07c3045.xml", "color": "#ff6b6b"},
    {"key": "稀土掘金技术社区_20", "name": "稀土掘金技术社区", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/33ecd2122ae788ea02dfcf1df857a54b9ae1338d.xml", "color": "#ff6b6b"},
    {"key": "dbaplus社群_21", "name": "dbaplus社群", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a92cc44a756e2b9165fed5572aa7337843a73eee.xml", "color": "#ff6b6b"},
    {"key": "深思圈_22", "name": "深思圈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3e6fcb56a39b2e18f1036113655d4ff8fe726b62.xml", "color": "#ff6b6b"},
    {"key": "海外独角兽_23", "name": "海外独角兽", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7200d3a5e976d231deb1e40ad33745c0e649b029.xml", "color": "#ff6b6b"},
    {"key": "谷歌开发者_24", "name": "谷歌开发者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9c65b8470acb8a5400199616536995d5ba90f52e.xml", "color": "#ff6b6b"},
    {"key": "笔记侠_25", "name": "笔记侠", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4c5d9bcc2fbfcd1dc81fb67559653f8957ef4760.xml", "color": "#ff6b6b"},
    {"key": "月之暗面_kimi_26", "name": "月之暗面 Kimi", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c5c43d4bc17bae656763859ed0903bb6314ec6fe.xml", "color": "#ff6b6b"},
    {"key": "腾讯研究院_27", "name": "腾讯研究院", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6152301e0978bffb0a8284cab339262b9764dcfb.xml", "color": "#ff6b6b"},
    {"key": "浮之静_28", "name": "浮之静", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/abb0de0c0cb8f684a1606a4b20121b245547adce.xml", "color": "#ff6b6b"},
    {"key": "甲子光年_29", "name": "甲子光年", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1c4008936645d5c17239d99bba91522cf2bdfa26.xml", "color": "#ff6b6b"},
    {"key": "z_potentials_30", "name": "Z Potentials", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c47f4bc00ea912c37b6e23b22b146db0e85b3e19.xml", "color": "#ff6b6b"},
    {"key": "deepseek_31", "name": "DeepSeek", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1709da4f538d4ce4fb6d7a8ba1a5a1c297919601.xml", "color": "#ff6b6b"},
    {"key": "jina_ai_32", "name": "Jina AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ff2c5468828ebe7236afd6c1d128e219774487c2.xml", "color": "#ff6b6b"},
    {"key": "datawhale_33", "name": "Datawhale", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ea0dd8bddfe4fbfb32eaa81a1e1b628d45e97a80.xml", "color": "#ff6b6b"},
    {"key": "向阳乔木推荐看_34", "name": "向阳乔木推荐看", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3e50f11753a7c5ed689565fbf5abf96cb4541c57.xml", "color": "#ff6b6b"},
    {"key": "语言即世界language_is_world_35", "name": "语言即世界language is world", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e1ed0d3edd93f90aef602105eb7ca51b35b7060a.xml", "color": "#ff6b6b"},
    {"key": "dify_36", "name": "Dify", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e46c03a4cb65509e22ab9a8507888a2096319d65.xml", "color": "#ff6b6b"},
    {"key": "智谱_37", "name": "智谱", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/433d2134dca54d80804daf32e8be546155be3300.xml", "color": "#ff6b6b"},
    {"key": "通义实验室_38", "name": "通义实验室", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4ebee6222ae08705b8aabc9116f0defbcb6b17c6.xml", "color": "#ff6b6b"},
    {"key": "百度文心_39", "name": "百度文心", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d0767d885e6ba213344fb0c0408c51331e23a994.xml", "color": "#ff6b6b"},
    {"key": "腾讯混元_40", "name": "腾讯混元", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/306ce19a1ca590c9c2df781789e828d1acfa1356.xml", "color": "#ff6b6b"},
    {"key": "智东西_41", "name": "智东西", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/cfd52b4245ca6119b2fda4ef934832c689028927.xml", "color": "#ff6b6b"},
    {"key": "agent橘_42", "name": "AGENT橘", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6cef434b771dd75a91864b2e699a622cb4e3eb33.xml", "color": "#ff6b6b"},
    {"key": "大模型智能_43", "name": "大模型智能", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bfc6440c1a2443fab9a6bf607137d41db5cd5c93.xml", "color": "#ff6b6b"},
    {"key": "ai炼金术_44", "name": "AI炼金术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4915f3747653bbb9c7975323c11b768d2b9cd6c9.xml", "color": "#ff6b6b"},
    {"key": "ai科技评论_45", "name": "AI科技评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/789e5fefb9cc2646ba7b680cb7a88378a34eb7a4.xml", "color": "#ff6b6b"},
    {"key": "山行ai_46", "name": "山行AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/98bc16b6f53902a2ab511b4faa3499e0a1c78eb1.xml", "color": "#ff6b6b"},
    {"key": "土猛的员外_47", "name": "土猛的员外", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3ee671d065adc460bc20bbd269115987098c54a0.xml", "color": "#ff6b6b"},
    {"key": "deeplearningai_48", "name": "DeeplearningAI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9d094d066a5faacff0eb0a6b95efbba20d4f1fc9.xml", "color": "#ff6b6b"},
    {"key": "机器之心sota模型_49", "name": "机器之心SOTA模型", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2f520471856d56c7b3a95cd09eb777149b32828a.xml", "color": "#ff6b6b"},
    {"key": "阶跃星辰_50", "name": "阶跃星辰", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3e2714d06aa36142e8ed6b3f4e5cf9090a069dd2.xml", "color": "#ff6b6b"},
    {"key": "字节跳动seed_51", "name": "字节跳动Seed", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6efd40bb335d2037f365d284cb5e00f0843e737e.xml", "color": "#ff6b6b"},
    {"key": "ai寒武纪_52", "name": "AI寒武纪", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5903009f48a5e4aa44d8ac941a54fe3aafc3e03c.xml", "color": "#ff6b6b"},
    {"key": "minimax_稀宇科技_53", "name": "MiniMax 稀宇科技", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/00306b171f754d463b28cf83f3ba086ad009b430.xml", "color": "#ff6b6b"},
    {"key": "花叔_54", "name": "花叔", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ed3e181242a4622709081439d802523ecf7b78f2.xml", "color": "#ff6b6b"},
    {"key": "ainlp_55", "name": "AINLP", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/875df1d1a991bf9250ba9813e3148f58ef2240d4.xml", "color": "#ff6b6b"},
    {"key": "硅基观察pro_56", "name": "硅基观察Pro", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f21c3e34df9b5fecfda57e2e53512864255ed4cd.xml", "color": "#ff6b6b"},
    {"key": "李继刚_57", "name": "李继刚", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9645a69180041ff935c458753174fa8bc2061295.xml", "color": "#ff6b6b"},
    {"key": "沃垠ai_58", "name": "沃垠AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/339818dbd5154cecdf5f4161f3391c7038a72bae.xml", "color": "#ff6b6b"},
    {"key": "袋鼠帝ai客栈_59", "name": "袋鼠帝AI客栈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/24d0930cc9f4f0c708182dc1c087d41e1f4cbd33.xml", "color": "#ff6b6b"},
    {"key": "ai科技大本营_60", "name": "AI科技大本营", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/dfd3b5e742e32d8032a445832373191957202bf3.xml", "color": "#ff6b6b"},
    {"key": "卡尔的ai沃茨_61", "name": "卡尔的AI沃茨", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8a1fc997e5c742e91ad7c253836c28ca3a69ccb1.xml", "color": "#ff6b6b"},
    {"key": "阿真irene_62", "name": "阿真Irene", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d5ead392b0cf117d0ba4070e2261111fdde49711.xml", "color": "#ff6b6b"},
    {"key": "优设_63", "name": "优设", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8fee9d33e883a769a59a5a3e27d249cf8567b55a.xml", "color": "#ff6b6b"},
    {"key": "体验进阶_64", "name": "体验进阶", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/083c360a74b36b2c33820a995d21cbf60c813c0a.xml", "color": "#ff6b6b"},
    {"key": "超人的电话亭_65", "name": "超人的电话亭", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4be15abcd5621887bb7c1e2efd2d1cd8c68a16f0.xml", "color": "#ff6b6b"},
    {"key": "clip设计夹_66", "name": "Clip设计夹", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ebd5f5bd705dd531066eeca5ee500a1e6a269e17.xml", "color": "#ff6b6b"},
    {"key": "ai产品黄叔_67", "name": "AI产品黄叔", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1f1030491e15e5349aae42367513d6b3f70a8f8b.xml", "color": "#ff6b6b"},
    {"key": "强少来了_68", "name": "强少来了", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3c36fe804f63a7b936e372a37929d81fa0ad948a.xml", "color": "#ff6b6b"},
    {"key": "小米技术_69", "name": "小米技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8bbc1ba1d363e70cd42d1ce89fb9070cb075c3b3.xml", "color": "#ff6b6b"},
    {"key": "哔哩哔哩技术_70", "name": "哔哩哔哩技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3a12ae4fde5bb74aab2fddc9f710a3c057eab82f.xml", "color": "#ff6b6b"},
    {"key": "字节跳动技术团队_71", "name": "字节跳动技术团队", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d3a9e4d6f125cc98d1691dbc30cd97fec7ae2d03.xml", "color": "#ff6b6b"},
    {"key": "滴滴技术_72", "name": "滴滴技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b9a02e7d9e35178ef44fc560fcb5ec4995613af2.xml", "color": "#ff6b6b"},
    {"key": "奇舞精选_73", "name": "奇舞精选", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/156a64fe3e95eebe4b85bf981d6ebb85441897bf.xml", "color": "#ff6b6b"},
    {"key": "得物技术_74", "name": "得物技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1cde72c9129b1f79cbb150166e7fed9a7568ee10.xml", "color": "#ff6b6b"},
    {"key": "百度geek说_75", "name": "百度Geek说", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6cc437d76f9dc4f7c35011c72e471e33e7bdd384.xml", "color": "#ff6b6b"},
    {"key": "前端充电宝_76", "name": "前端充电宝", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/efed19b684285ee14f88b3f234b350fba9376d7a.xml", "color": "#ff6b6b"},
    {"key": "qunar技术沙龙_77", "name": "Qunar技术沙龙", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/84c072f8d34d1690f2783d7dda6013cf6d892b7f.xml", "color": "#ff6b6b"},
    {"key": "vivo互联网技术_78", "name": "vivo互联网技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b3ceb5cb1e4602ca55704650a157ec9c5b2f0d31.xml", "color": "#ff6b6b"},
    {"key": "小红书技术redtech_79", "name": "小红书技术REDtech", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0f8c47df6fd304112518544776e0bbf1d98ba0b9.xml", "color": "#ff6b6b"},
    {"key": "hellogithub_80", "name": "HelloGitHub", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e6cc80b97bf64eeef61cc5927c78ba6ce3356422.xml", "color": "#ff6b6b"},
    {"key": "印记中文_81", "name": "印记中文", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2b038bb5307a75a603405f7191b5030576d3e8bd.xml", "color": "#ff6b6b"},
    {"key": "快手技术_82", "name": "快手技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c4cc10d2e32a5fa12927581ae581a336f399fe75.xml", "color": "#ff6b6b"},
    {"key": "逛逛github_83", "name": "逛逛GitHub", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/38be32e5376d852c13d3383e4d7a757fd9a55ff6.xml", "color": "#ff6b6b"},
    {"key": "架构师之路_84", "name": "架构师之路", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f6dec1c3ad16e43532dd427c85eaeb3a7b7b084e.xml", "color": "#ff6b6b"},
    {"key": "硅谷科技评论_85", "name": "硅谷科技评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4515ee058133ff68570ad586abdd81f54f2b6ee3.xml", "color": "#ff6b6b"},
    {"key": "42章经_86", "name": "42章经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f6694726ced4ba3d7c7cd65c6edf2160c5978387.xml", "color": "#ff6b6b"},
    {"key": "随机小分队_87", "name": "随机小分队", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/115e814e7b12d373a55459cb2aea3223152f2af2.xml", "color": "#ff6b6b"},
    {"key": "阿里研究院_88", "name": "阿里研究院", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e2f1190c120f7f3d74b630bfcfe9e58296bd535c.xml", "color": "#ff6b6b"},
    {"key": "创业邦_89", "name": "创业邦", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f5e0d8e342d9e2ec5b2942f08522cfaec17acc8d.xml", "color": "#ff6b6b"},
    {"key": "csdn_90", "name": "CSDN", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b0b7f2852aecdcc5a0eb08d33afc1c08b855d98b.xml", "color": "#ff6b6b"},
    {"key": "吴晓波频道_91", "name": "吴晓波频道", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/604fd0bfbb0214958f7fd2718509e4ea038c6afc.xml", "color": "#ff6b6b"},
    {"key": "投资实习所_92", "name": "投资实习所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1324caa248157b73a64412393f5612931368dd52.xml", "color": "#ff6b6b"},
    {"key": "经纬创投_93", "name": "经纬创投", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/05efb1c4cf91e5a37443cc323150ea38a838e9fd.xml", "color": "#ff6b6b"},
    {"key": "少数派_94", "name": "少数派", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f0e37a7d597231efed4bf6dd05b5d904de6dbcc1.xml", "color": "#ff6b6b"},
    {"key": "网易科技_95", "name": "网易科技", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/028fbc21062e744c7b606880ebca01e22cb4b7b7.xml", "color": "#ff6b6b"},
    {"key": "硅谷101_96", "name": "硅谷101", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8f8fe34034f6123b168ed7847c51d50ff47cd7ee.xml", "color": "#ff6b6b"},
    {"key": "真格基金_97", "name": "真格基金", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/47798a14d51da72e68fae4f7a259f096750cf03e.xml", "color": "#ff6b6b"},
    {"key": "深网腾讯新闻_98", "name": "深网腾讯新闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/396591aa7d3ef15fa3b5b17ec4b1aa840ebde335.xml", "color": "#ff6b6b"},
    {"key": "白鲸出海_99", "name": "白鲸出海", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2b8f03a73a0f2ac92a8ca69c124e5be6f442dbdc.xml", "color": "#ff6b6b"},
    {"key": "硅星人pro_100", "name": "硅星人Pro", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c62ceda9eed269d851802bdbc5f33c4fabbf7462.xml", "color": "#ff6b6b"},
    {"key": "暗涌waves_101", "name": "暗涌Waves", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bd586c1499b56aaec02dfefa87126232d234b010.xml", "color": "#ff6b6b"},
    {"key": "夕小瑶科技说_102", "name": "夕小瑶科技说", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/64b57d666259aee6bd097e76164e4a8371f0ad04.xml", "color": "#ff6b6b"},
    {"key": "l先生说_103", "name": "L先生说", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/31c7fb6f7959a5ff90ae997b536e78b8b3f23321.xml", "color": "#ff6b6b"},
    {"key": "有新newin_104", "name": "有新Newin", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/74554dcb3da8982083426b871bc8c314a9de9729.xml", "color": "#ff6b6b"},
    {"key": "晚点latepost_105", "name": "晚点LatePost", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c442206ec9957f3c52f2f40300ca532079538b31.xml", "color": "#ff6b6b"},
    {"key": "刘润_106", "name": "刘润", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c1354f67c314d25d6e236a58724043bdc46d6079.xml", "color": "#ff6b6b"},
    {"key": "刘小排r_107", "name": "刘小排r", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/484d4199ae6c0b72ea01e7e0597a1f74933dfb62.xml", "color": "#ff6b6b"},
    {"key": "机器之心_108", "name": "机器之心", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8d97af31b0de9e48da74558af128a4673d78c9a3.xml", "color": "#ff6b6b"},
    {"key": "魔搭modelscope社区_109", "name": "魔搭ModelScope社区", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d993a885260f96057b9a4c96212cb2c95bb5054b.xml", "color": "#ff6b6b"},
    {"key": "43_talks_110", "name": "43 Talks", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4efe7ec6970afd4a050d6f10b9e8131a9d5e6816.xml", "color": "#ff6b6b"},
    {"key": "言午_111", "name": "言午", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/138de227ebfbee6ea26564564f7bcd6c0c27af60.xml", "color": "#ff6b6b"},
    {"key": "思特沃克洞见_112", "name": "思特沃克洞见", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6c6865b59e528f6f86d80b9a2071052416ef561f.xml", "color": "#ff6b6b"},
    {"key": "数据可视化_antv_113", "name": "数据可视化 AntV", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c1a09e8847fbaea14eaa89db218d783fe176c5a6.xml", "color": "#ff6b6b"},
    {"key": "晚点再听latercast_114", "name": "晚点再听LaterCast", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1193affe8f8ed7a64281054cb022a7176054fa38.xml", "color": "#ff6b6b"},
    {"key": "古典古少侠_115", "name": "古典古少侠", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/63554903d26c4e94ba031e9c8a93492b7ebcfbb9.xml", "color": "#ff6b6b"},
    {"key": "ai异类弗兰克_116", "name": "AI异类弗兰克", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e0415653cbf6f41e25fa266d010b3238b91a65e3.xml", "color": "#ff6b6b"},
    {"key": "ai产品阿颖_117", "name": "AI产品阿颖", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5000fe62390006b10eef8a737d89c478611994a7.xml", "color": "#ff6b6b"},
    {"key": "阑夕_118", "name": "阑夕", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fe0fc82458663820d6e91f6331dea05f3db223d4.xml", "color": "#ff6b6b"},
    {"key": "pm圈子_119", "name": "PM圈子", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bf07a12ef2909114f17c6734d6c7ad166221c5e7.xml", "color": "#ff6b6b"},
    {"key": "哈佛商业评论_120", "name": "哈佛商业评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/205f074dd6b962e0f4de876e9ebfe70a33bd8f66.xml", "color": "#ff6b6b"},
    {"key": "paperagent_121", "name": "PaperAgent", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/54001ca616dbc4b55d2b25d79d68a70191a0ddf4.xml", "color": "#ff6b6b"},
    {"key": "有赞coder_122", "name": "有赞coder", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/75ad69f1c1d0d1f289f7702cf5eb553287441fdc.xml", "color": "#ff6b6b"},
    {"key": "draco正在vibecoding_123", "name": "Draco正在VibeCoding", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/54dd1b1511fd066dfea2b4acde3e62787e8a687b.xml", "color": "#ff6b6b"},
    {"key": "36氪_124", "name": "36氪", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c68b58fb17ac7ae4b23c2af276cdd61c9eca1a48.xml", "color": "#ff6b6b"},
    {"key": "playwright实战教程_125", "name": "Playwright实战教程", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bd8be44d64fa249f76615867dfb89e1d9f905d3e.xml", "color": "#ff6b6b"},
    {"key": "华尔街见闻_126", "name": "华尔街见闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4162e7fc1ecdeca20d88e9ce3fa0d9070af3eaff.xml", "color": "#ff6b6b"},
    {"key": "青稞ai_127", "name": "青稞AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b22be100fcd702f02cd6574b5aecb8a08d48438f.xml", "color": "#ff6b6b"},
    {"key": "ai闲谈_128", "name": "AI闲谈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/baa2c36e1ead8e94c51c504ebddcc1ed682dc0b8.xml", "color": "#ff6b6b"},
    {"key": "罗西的思考_129", "name": "罗西的思考", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7dbc05b457a855d5cdee726ee78730b6e3a103f4.xml", "color": "#ff6b6b"},
    {"key": "武志红_130", "name": "武志红", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7f1dc0e04603db8e1ddadfc4beea4a190af49cf6.xml", "color": "#ff6b6b"},
    {"key": "槽边往事_131", "name": "槽边往事", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0e8853d7a9fba6a4ed3556806c0ee832539a703e.xml", "color": "#ff6b6b"},
    {"key": "人物_132", "name": "人物", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ffd27daeb694ea7d39b113aa143deb3669d4a4a4.xml", "color": "#ff6b6b"},
    {"key": "猫笔刀_133", "name": "猫笔刀", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/21762bfa023b817580db467d80c446ec0dd752fe.xml", "color": "#ff6b6b"},
    {"key": "周国平_134", "name": "周国平", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/50a452615d3b1f0054662056aa25c666a12a37de.xml", "color": "#ff6b6b"},
    {"key": "南方周末_135", "name": "南方周末", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/eeb58b367f5515e9e3b56a8517aac4f7a71ce821.xml", "color": "#ff6b6b"},
    {"key": "财新_136", "name": "财新", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/871af46d93b7b7370c4ab65330e5d9599f7f540c.xml", "color": "#ff6b6b"},
    {"key": "三联生活周刊_137", "name": "三联生活周刊", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/29d9e4b80072d04e39dc5a25735733853496390d.xml", "color": "#ff6b6b"},
    {"key": "一席_138", "name": "一席", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4f8c07cc1c9eee6998b27eb99d7f134778871f0f.xml", "color": "#ff6b6b"},
    {"key": "xiaomi_mimo_139", "name": "Xiaomi MiMo", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/19c2af88005704d49ea397c203dcb45339532946.xml", "color": "#ff6b6b"},
    {"key": "钉钉_140", "name": "钉钉", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3291b88d0dc81c3c094752f756256c715d038a7b.xml", "color": "#ff6b6b"},
    {"key": "飞书_141", "name": "飞书", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/acae39126a4fe47d9c99714708d606f5c3ab0169.xml", "color": "#ff6b6b"},
    {"key": "携程技术_142", "name": "携程技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b5d5237d609fe96d74ae9d0241ffa8daad2f147b.xml", "color": "#ff6b6b"},
    {"key": "蚂蚁技术anttech_143", "name": "蚂蚁技术AntTech", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/15738401f49466ad01b324b69f779f9bef0cb3e7.xml", "color": "#ff6b6b"},
    {"key": "爱奇艺技术产品团队_144", "name": "爱奇艺技术产品团队", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8fbf4e8a45332ee325cf68cb15733c5d67e1dca4.xml", "color": "#ff6b6b"},
    {"key": "丁香医生_145", "name": "丁香医生", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/88a040c0813d22de5d8ffa62131ae40fa70f765f.xml", "color": "#ff6b6b"},
    {"key": "saas白夜行_146", "name": "SaaS白夜行", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a0f20f6277c356668a2567632a67e15b0413f395.xml", "color": "#ff6b6b"},
    {"key": "世界银行_147", "name": "世界银行", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8914290fa6b113568831e7e8ae52a3c9cbd061e4.xml", "color": "#ff6b6b"},
    {"key": "老俞闲话_148", "name": "老俞闲话", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3af3c0ee7e1a66619e1ca08c56c2147b790102b7.xml", "color": "#ff6b6b"},
    {"key": "小林coding_149", "name": "小林coding", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/63357dd728b2d9de9bc4b0cc9fac6fedbab64dc2.xml", "color": "#ff6b6b"},
    {"key": "斯坦福社会创新评论_150", "name": "斯坦福社会创新评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/176467712d648b3d629e9a5c229630883cd16eb7.xml", "color": "#ff6b6b"},
    {"key": "谷雨实验室_151", "name": "谷雨实验室", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/32a2be6b236d2d781cc673bfb7dc2e4ad90916b3.xml", "color": "#ff6b6b"},
    {"key": "每日豆瓣_152", "name": "每日豆瓣", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/446ef0aa21444f0f1fa2a7f9065df62e1316b029.xml", "color": "#ff6b6b"},
    {"key": "新周刊_153", "name": "新周刊", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/caded2232a667e519168abd292ed0784d1442c69.xml", "color": "#ff6b6b"},
    {"key": "果壳_154", "name": "果壳", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f6110e1e1dd6986dacc3aa77cc3ea15dbe00ebdc.xml", "color": "#ff6b6b"},
    {"key": "knowyourself_155", "name": "KnowYourself", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bacffc35c016c560bb0bb4964dd817716ce87ce0.xml", "color": "#ff6b6b"},
    {"key": "凤凰网财经_156", "name": "凤凰网财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/404573560480142fd2322430f3c1efe696cc89af.xml", "color": "#ff6b6b"},
    {"key": "凤凰网_157", "name": "凤凰网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/884b4351f91518b48d4e763d4afe94eee728966b.xml", "color": "#ff6b6b"},
    {"key": "雪球_158", "name": "雪球", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9d5320cc173fb50df6aadf7e7756d30e5fefa1c3.xml", "color": "#ff6b6b"},
    {"key": "财联社_159", "name": "财联社", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8e9c7dfaf07013f4da379dd0f87c3a298f2ed501.xml", "color": "#ff6b6b"},
    {"key": "张佳玮写字的地方_160", "name": "张佳玮写字的地方", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5019ddf8938007d443a07a12874aa10d3a5bdfb5.xml", "color": "#ff6b6b"},
    {"key": "投资界_161", "name": "投资界", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/94251955e48961a24956ccb721652d02c75a75d0.xml", "color": "#ff6b6b"},
    {"key": "央视财经_162", "name": "央视财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f53a1ab575594fbfdcb65815157c1eccf2de048a.xml", "color": "#ff6b6b"},
    {"key": "支付宝体验科技_163", "name": "支付宝体验科技", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/666d6e30c773dd35ecc593866bab680db95b27f2.xml", "color": "#ff6b6b"},
    {"key": "秋芝2046_164", "name": "秋芝2046", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d1a81ccce98b8faae6018498fa743eaca5db68c0.xml", "color": "#ff6b6b"},
    {"key": "吴鲁加_165", "name": "吴鲁加", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/657f15577e56c95966cd81e48129ff9abf33ab97.xml", "color": "#ff6b6b"},
    {"key": "香帅的金融江湖_166", "name": "香帅的金融江湖", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/14cb1167539ceb3e3b235e1fb01e478056244e23.xml", "color": "#ff6b6b"},
    {"key": "效率火箭_167", "name": "效率火箭", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/86d7291e830e7503595cb126a6d225fb80d7c1ae.xml", "color": "#ff6b6b"},
    {"key": "高可用架构_168", "name": "高可用架构", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ee1046514840272a85fe7f67731bc322a0a2c18d.xml", "color": "#ff6b6b"},
    {"key": "腾讯云中间件_169", "name": "腾讯云中间件", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bf602c1e692b10b8f0192f2379d0f64dee58eba0.xml", "color": "#ff6b6b"},
    {"key": "虎嗅app_170", "name": "虎嗅APP", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/804d04874a3bbfce3cdc4ad0a0b5520943b9f551.xml", "color": "#ff6b6b"},
    {"key": "雷峰网_171", "name": "雷峰网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5e4d00adff41e5f5b2bd823215c9949e7e678bd5.xml", "color": "#ff6b6b"},
    {"key": "钛媒体_172", "name": "钛媒体", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3d5672d87be7aba570671c8cb2fdbda36a5dfd9e.xml", "color": "#ff6b6b"},
    {"key": "paperweekly_173", "name": "PaperWeekly", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0120e999fc95e098c74bd5482a2a4c8407c42c38.xml", "color": "#ff6b6b"},
    {"key": "智能涌现_174", "name": "智能涌现", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/049f4d78f94b31ab6afda95b1a65f0e562c8d5c2.xml", "color": "#ff6b6b"},
    {"key": "飞哥说ai_175", "name": "飞哥说AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/31c318a7a9660e5b2391115b0f83839f486570eb.xml", "color": "#ff6b6b"},
    {"key": "水木人工智能学堂_176", "name": "水木人工智能学堂", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/87c921eb79326f3c51b4bc6a1704e8dc0420807e.xml", "color": "#ff6b6b"},
    {"key": "从码农到工匠_177", "name": "从码农到工匠", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/62cea86161773d55ff6ce9227ab38f0a7c6051c0.xml", "color": "#ff6b6b"},
    {"key": "快刀青衣_178", "name": "快刀青衣", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b528adeff7b27026e7a69163ad77f262d99b33a4.xml", "color": "#ff6b6b"},
    {"key": "hellosreagent_179", "name": "HelloSREAgent", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e0e96fb81b9b94067a27f8027462bea49cde20c3.xml", "color": "#ff6b6b"},
    {"key": "mactalk_180", "name": "MacTalk", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a657b0a3a865418b8ed7c619214cd4b8c7a28218.xml", "color": "#ff6b6b"},
    {"key": "刘言飞语_181", "name": "刘言飞语", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0bbf4e1271c70b60721eb2ce4126f11943d14558.xml", "color": "#ff6b6b"},
    {"key": "产品二姐_182", "name": "产品二姐", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/55de4108d258a231633eafd1810377e2bd674c8c.xml", "color": "#ff6b6b"},
    {"key": "ai大模型应用实践_183", "name": "AI大模型应用实践", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ab58feca07412e57049e5d8561439c3fb35783c2.xml", "color": "#ff6b6b"},
    {"key": "王吉伟_184", "name": "王吉伟", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9ebca45070e74a337b19ca8ff87490194a2b4060.xml", "color": "#ff6b6b"},
    {"key": "风叔云_185", "name": "风叔云", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c02b5c42c685455f9fbe1da955d87567ea08d63f.xml", "color": "#ff6b6b"},
    {"key": "脑极体_186", "name": "脑极体", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5044161439fe8773e9d906a04d6df8f711e770ea.xml", "color": "#ff6b6b"},
    {"key": "麦肯锡_187", "name": "麦肯锡", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6e3fe51cfebc623cfe8ac3cd8b4eed63c851c777.xml", "color": "#ff6b6b"},
    {"key": "麻省理工科技评论app_188", "name": "麻省理工科技评论APP", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b776c2d89a99c852e9eb17d0d46f7f6d79febde4.xml", "color": "#ff6b6b"},
    {"key": "砺石商业评论_189", "name": "砺石商业评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5cdd765d3973322da7992e0c919a99246fbcd0fc.xml", "color": "#ff6b6b"},
    {"key": "通往agi之路_190", "name": "通往AGI之路", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ddc8d4d93c8ab3faa82675c2797aed5069cbc6f0.xml", "color": "#ff6b6b"},
    {"key": "小互ai_191", "name": "小互AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d87570ae13ab1ce240cd538181c131a8baebce4b.xml", "color": "#ff6b6b"},
    {"key": "喔家archiself_192", "name": "喔家ArchiSelf", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a68a06d7c803848f0b6fb9604fd68b3ba65e148f.xml", "color": "#ff6b6b"},
    {"key": "乱翻书_193", "name": "乱翻书", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/43e3aa5cabe4ae49ec50410ecefc859d4501aedf.xml", "color": "#ff6b6b"},
    {"key": "见实_194", "name": "见实", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/194b072227430108e54f40a67c9a514aff599a2f.xml", "color": "#ff6b6b"},
    {"key": "zartbot_195", "name": "zartbot", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/12557a2985e797b6cf8dc5079016dbb58bc8664d.xml", "color": "#ff6b6b"},
    {"key": "产品犬舍_196", "name": "产品犬舍", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/39221421bad19cf3c0041ba27b11618dc1123e75.xml", "color": "#ff6b6b"},
    {"key": "字节跳动开源_197", "name": "字节跳动开源", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bbe26264379897525e0803213c617b4c3c205f5f.xml", "color": "#ff6b6b"},
    {"key": "二一的笔记_198", "name": "二一的笔记", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/be5a304ec616b24307b08e9b8d509f7db9be9b24.xml", "color": "#ff6b6b"},
    {"key": "一泽eze_199", "name": "一泽Eze", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e0f763bed9b986b261814acd3f0afa0200db4645.xml", "color": "#ff6b6b"},
    {"key": "前端开发爱好者_200", "name": "前端开发爱好者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e208f73e985a4e9fe0af8ff46e3748af8764871d.xml", "color": "#ff6b6b"},
    {"key": "南京发布_201", "name": "南京发布", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/681f69fea8433abc28c5c7c7a03b6b7b51b66690.xml", "color": "#ff6b6b"},
    {"key": "网信中国_202", "name": "网信中国", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c41dc7a4e9417519b0158564ad71474f6f8bd296.xml", "color": "#ff6b6b"},
    {"key": "网信北京_203", "name": "网信北京", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/252b77943894dfaa846848b155ba4a576759981e.xml", "color": "#ff6b6b"},
    {"key": "公安部网安局_204", "name": "公安部网安局", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/10920f6c84277afcd319a28689d91892c837189c.xml", "color": "#ff6b6b"},
    {"key": "方伟看十年_205", "name": "方伟看十年", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/eaf95898f79359a2e689481c249e4009cde21bd6.xml", "color": "#ff6b6b"},
    {"key": "写代码的宝哥_206", "name": "写代码的宝哥", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/39407ad821c78811f088d038d4c33d07696f2122.xml", "color": "#ff6b6b"},
    {"key": "phodal_207", "name": "phodal", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1ee069bd83f544b3973ed86e75b3c3126ddeb173.xml", "color": "#ff6b6b"},
    {"key": "毛有话说_208", "name": "毛有话说", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4d8e24304b901d974a773c00c12bc87f1c7eaf4d.xml", "color": "#ff6b6b"},
    {"key": "nov心理_209", "name": "NOV心理", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/360c6d90937821e93a076066b7f72401680491bd.xml", "color": "#ff6b6b"},
    {"key": "泽平宏观_210", "name": "泽平宏观", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4457d527901114d399a081ba4cf74688617a0ff4.xml", "color": "#ff6b6b"},
    {"key": "峰瑞资本_211", "name": "峰瑞资本", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/add0d6261e87b188e868179f1dc5afc0a5d06c3f.xml", "color": "#ff6b6b"},
    {"key": "高瓴时间_212", "name": "高瓴时间", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/48cf51f4ce98b1a44be820caf6bec3f7e40fae0c.xml", "color": "#ff6b6b"},
    {"key": "高瓴创投_213", "name": "高瓴创投", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c678fe78920139132d57163ee5612dc880566ce4.xml", "color": "#ff6b6b"},
    {"key": "聪明投资者_214", "name": "聪明投资者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d141c2a7c08d56f573b32c7e2f09b6ee779dc51d.xml", "color": "#ff6b6b"},
    {"key": "中金点睛_215", "name": "中金点睛", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5d4eef298108dd63ce77f40257436e0585bab425.xml", "color": "#ff6b6b"},
    {"key": "也谈钱_216", "name": "也谈钱", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c89b83a7d10ad638414aed3a3524e2a32566a8fa.xml", "color": "#ff6b6b"},
    {"key": "山行资本_217", "name": "山行资本", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/76787a745daab4bbc83fe3155aa74aaa1d54c7a0.xml", "color": "#ff6b6b"},
    {"key": "格隆汇app_218", "name": "格隆汇APP", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/379ce45e27b2c096121d11c0eccdda4cc15511de.xml", "color": "#ff6b6b"},
    {"key": "棱镜_219", "name": "棱镜", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ebf208faff5c5ad865ab5e5a30548633f3b51da7.xml", "color": "#ff6b6b"},
    {"key": "海豚研究_220", "name": "海豚研究", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/60b1f9007c87ab75cd83314bf5cfede30addd40a.xml", "color": "#ff6b6b"},
    {"key": "经济观察报_221", "name": "经济观察报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d930069e140c08f249e636f46a2c1f03182b3d0f.xml", "color": "#ff6b6b"},
    {"key": "21世纪经济报道_222", "name": "21世纪经济报道", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c6a39cae0e7e0979ed9f2eece16695c5f664f147.xml", "color": "#ff6b6b"},
    {"key": "老钱说钱_223", "name": "老钱说钱", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/88fb06f77c904a2a8b2077ed5bf2b62817b2c59f.xml", "color": "#ff6b6b"},
    {"key": "老钱日日谈_224", "name": "老钱日日谈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6e8528014a81863ccd43207355399c224314e405.xml", "color": "#ff6b6b"},
    {"key": "东方财富网_225", "name": "东方财富网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/704303062c285fa1417079b9c95c5c143378bbd8.xml", "color": "#ff6b6b"},
    {"key": "郑立涛_226", "name": "郑立涛", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/14fb6a008b286103e05bc153c9dc37d7f5d42c36.xml", "color": "#ff6b6b"},
    {"key": "佳芮的创业笔记_227", "name": "佳芮的创业笔记", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5aa6b8e04fc2fbf62166365c6b87cea2ecf3d44a.xml", "color": "#ff6b6b"},
    {"key": "财经早餐_228", "name": "财经早餐", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fa79da40977d8741fa9ec8a24989718f0707cfcf.xml", "color": "#ff6b6b"},
    {"key": "中国新闻周刊_229", "name": "中国新闻周刊", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d54b08f4e62345d5516c26fbff3de9e499f18cfb.xml", "color": "#ff6b6b"},
    {"key": "第一财经_230", "name": "第一财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e2cc4ff2ae914ebfd4150420ece80dd93be7a6d9.xml", "color": "#ff6b6b"},
    {"key": "券商中国_231", "name": "券商中国", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/eb2d4afb6b3f89a5dda9f796a95ca5372bd83621.xml", "color": "#ff6b6b"},
    {"key": "单读_232", "name": "单读", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/62c32960749b3c7ec9e2619525df1f2f009aaa86.xml", "color": "#ff6b6b"},
    {"key": "艾逗笔_233", "name": "艾逗笔", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/31cf8adcf5ad2bfe8cbd8409c6d84c08784d2ca5.xml", "color": "#ff6b6b"},
    {"key": "腾讯nba_234", "name": "腾讯NBA", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b8cdac6015dab300f2468038221dfd297dceacc1.xml", "color": "#ff6b6b"},
    {"key": "苏群_235", "name": "苏群", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/297ed052ab6f3726d9933df0961f025beb36542c.xml", "color": "#ff6b6b"},
    {"key": "篮球先锋报_236", "name": "篮球先锋报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f076b25e8c5358880e9f7c8ceec58992feb5562f.xml", "color": "#ff6b6b"},
    {"key": "杨毅侃球_237", "name": "杨毅侃球", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/265c3ebcfe26f9455a4f650a806483c9950a3958.xml", "color": "#ff6b6b"},
    {"key": "懂球娘娘_238", "name": "懂球娘娘", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/67246a8ef8bfcc82ae693fbb5ebd5567f6ae139e.xml", "color": "#ff6b6b"},
    {"key": "足球报_239", "name": "足球报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6f55a87674766367be332b6d463021613c2b8630.xml", "color": "#ff6b6b"},
    {"key": "体坛周报_240", "name": "体坛周报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/43e3b2bdf6d571e6b0cb02441d4046509ce61a38.xml", "color": "#ff6b6b"},
    {"key": "澎湃运动家_241", "name": "澎湃运动家", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c27cf2dba8368d4cf9f93d9d85ee63fafc69fa0e.xml", "color": "#ff6b6b"},
    {"key": "五星体育_242", "name": "五星体育", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/560bc0b98b3535e6e74ce318eb215a7a5301b1db.xml", "color": "#ff6b6b"},
    {"key": "天下足球_243", "name": "天下足球", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8b16711ae36ee21d44e7c2c12329ed56ffe64ae2.xml", "color": "#ff6b6b"},
    {"key": "央视网体育_244", "name": "央视网体育", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/adf8efe8a3e3ba537ad768152f8458112486131e.xml", "color": "#ff6b6b"},
    {"key": "央视新闻_245", "name": "央视新闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3ab1b6ca312f460cef0a80a0e2dd757c6104dd46.xml", "color": "#ff6b6b"},
    {"key": "环球时报_246", "name": "环球时报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9a99611016a68f3d04407bbbd5f6ace3d00fda11.xml", "color": "#ff6b6b"},
    {"key": "新华社_247", "name": "新华社", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6671f30c6010d2efdd1338836e6063748b5f1e0e.xml", "color": "#ff6b6b"},
    {"key": "每日经济新闻_248", "name": "每日经济新闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2a223faf5b8fdf7b95e2ad2f7ab8bfb8e21e5075.xml", "color": "#ff6b6b"},
    {"key": "腾讯财经_249", "name": "腾讯财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2bbef5993740fcd6ed968d19203962f24db7b442.xml", "color": "#ff6b6b"},
    {"key": "乒乓世界_250", "name": "乒乓世界", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3b6a03a990ff85053770442121052b9c769306ca.xml", "color": "#ff6b6b"},
    {"key": "南风窗_251", "name": "南风窗", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ae718c0cb66cf853eb83a435dc99341942948878.xml", "color": "#ff6b6b"},
    {"key": "央广网_252", "name": "央广网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/2d579b20439bc8e6bb94a3cac7877425a10c85f3.xml", "color": "#ff6b6b"},
    {"key": "科普中国_253", "name": "科普中国", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/54afcdd9db381d5e4a9469d08479b34b8a59d78c.xml", "color": "#ff6b6b"},
    {"key": "网球之家_254", "name": "网球之家", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/64a019a1e45694a099bfb865ef40ffe944f47cb4.xml", "color": "#ff6b6b"},
    {"key": "晚点对话_255", "name": "晚点对话", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7d94425ba74a9342a26b19cade3dcf4208038a43.xml", "color": "#ff6b6b"},
    {"key": "aibase基地_256", "name": "AIBase基地", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/27b06b577fc8f39566b7653621a376479ef3e3a8.xml", "color": "#ff6b6b"},
    {"key": "非凡产研_257", "name": "非凡产研", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fb99bd76d9b9a99155d2f9e03868d29eb43ea3fb.xml", "color": "#ff6b6b"},
    {"key": "晚点ai_258", "name": "晚点AI", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/316def62ee3a6d499bf3981ffe22a09bf7256265.xml", "color": "#ff6b6b"},
    {"key": "洞见_259", "name": "洞见", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/726da95f547b13ddd0d973689951e662c7ef18c6.xml", "color": "#ff6b6b"},
    {"key": "十点读书_260", "name": "十点读书", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ab06f5f1e4d78417466bd4ff3330d36284ba0503.xml", "color": "#ff6b6b"},
    {"key": "人民日报_261", "name": "人民日报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/492cbcab81fba00ffe2d16199c2170f8c1830bb3.xml", "color": "#ff6b6b"},
    {"key": "央视网_262", "name": "央视网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d2731f73d40fb0b4bac0536080ba43203d96134e.xml", "color": "#ff6b6b"},
    {"key": "跑步指南_263", "name": "跑步指南", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d130728bb7a2615be7894053b86e9c0918e64be5.xml", "color": "#ff6b6b"},
    {"key": "生命时报_264", "name": "生命时报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1e168442323bbd9dc309ecdcb6172ad80f4e2bad.xml", "color": "#ff6b6b"},
    {"key": "梅斯医学_265", "name": "梅斯医学", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f062c077bc14545b7c8ebc429fc9883a73d50f36.xml", "color": "#ff6b6b"},
    {"key": "cctv生活圈_266", "name": "CCTV生活圈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f0b0023f42c51e9ebe2ea63c514403098675802e.xml", "color": "#ff6b6b"},
    {"key": "每晚一卷书_267", "name": "每晚一卷书", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0d967f0498349ffa915e9bef7b51c7d0db0dff47.xml", "color": "#ff6b6b"},
    {"key": "看理想_268", "name": "看理想", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8e89bd4921808bd78b1a6a1310c1f333588aea32.xml", "color": "#ff6b6b"},
    {"key": "罗辑思维_269", "name": "罗辑思维", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/63deef75fd7e51c6717d17d9215d1969f99f401c.xml", "color": "#ff6b6b"},
    {"key": "叶檀财经_270", "name": "叶檀财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6c0b8961f68734b500af357c85e31bd77b9107e9.xml", "color": "#ff6b6b"},
    {"key": "张湧说财经_271", "name": "张湧说财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ca54330be89d40f35f8ec253a253d32fdb9d5549.xml", "color": "#ff6b6b"},
    {"key": "wind万得_272", "name": "Wind万得", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/db72a8e611d59e9184668bbdf5089fb298cde97d.xml", "color": "#ff6b6b"},
    {"key": "功夫财经_273", "name": "功夫财经", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6471fce0de540deb1b8b977824aab1c86487fcfd.xml", "color": "#ff6b6b"},
    {"key": "混知_274", "name": "混知", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b9b0a09ada656c4064bce64776131a8495870ea2.xml", "color": "#ff6b6b"},
    {"key": "科技美学_275", "name": "科技美学", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/72a33b2505db2ae3feebe81d72508f1915b96f3d.xml", "color": "#ff6b6b"},
    {"key": "心智工具箱_276", "name": "心智工具箱", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f6dd3f7a5ed195c85e62c52a41f95defcd560588.xml", "color": "#ff6b6b"},
    {"key": "iamsujie_277", "name": "iamsujie", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/d4a1f467bf0d41f72ed827ed0ff2f8e93695828a.xml", "color": "#ff6b6b"},
    {"key": "一条_278", "name": "一条", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8b41f783bf37ab39171e6da45730047e0e65e660.xml", "color": "#ff6b6b"},
    {"key": "中国国家地理_279", "name": "中国国家地理", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7bd19c521ac941dc14c425a562c80b6db2914e0d.xml", "color": "#ff6b6b"},
    {"key": "混沌学园_280", "name": "混沌学园", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/320f3eb9bb5d025eff72a56c920e1a85a6418363.xml", "color": "#ff6b6b"},
    {"key": "携隐melody_281", "name": "携隐Melody", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/42992fc03cdcee9ef03dfc4623b538b18dd923ce.xml", "color": "#ff6b6b"},
    {"key": "集智俱乐部_282", "name": "集智俱乐部", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bb50f406adb7c85720fcbf0882dc84887f81b67a.xml", "color": "#ff6b6b"},
    {"key": "格兰投研_283", "name": "格兰投研", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fdb968fa04c741aee954dc36c25d3dee8063ecee.xml", "color": "#ff6b6b"},
    {"key": "区块链头条_284", "name": "区块链头条", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f071affb5e43886a3ad54df80568942d645558af.xml", "color": "#ff6b6b"},
    {"key": "转转技术_285", "name": "转转技术", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/321ca7771cad36a3875e232d2a7bec9049dd2ed3.xml", "color": "#ff6b6b"},
    {"key": "陈鲁豫的电影沙发_286", "name": "陈鲁豫的电影沙发", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fee950422254d8f05a80a91d254017b0c2821ddd.xml", "color": "#ff6b6b"},
    {"key": "半导体行业观察_287", "name": "半导体行业观察", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/39f625822b35f7573a7e70d3b27a735a3c0d24a4.xml", "color": "#ff6b6b"},
    {"key": "饭统戴老板_288", "name": "饭统戴老板", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5f4c620560bd63023df9fb7d330aeee524e41676.xml", "color": "#ff6b6b"},
    {"key": "远川研究所_289", "name": "远川研究所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fae262a71b2c0f867011d3c40e02bff3272d90df.xml", "color": "#ff6b6b"},
    {"key": "caoz的梦呓_290", "name": "caoz的梦呓", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8e2047ef236238b91abf91562b79ef4a1e7ba39d.xml", "color": "#ff6b6b"},
    {"key": "孤独大脑_291", "name": "孤独大脑", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/700f40ffc993431fec55d910ceee880fb4e4eec3.xml", "color": "#ff6b6b"},
    {"key": "孟岩_292", "name": "孟岩", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/625e18375243cf380f7f1bcec4b0b3d79e5a3dea.xml", "color": "#ff6b6b"},
    {"key": "appso_293", "name": "APPSO", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4ae111e5b509609a5ee96c9894f1868fbafd793e.xml", "color": "#ff6b6b"},
    {"key": "i食色摇闲情_294", "name": "i食色摇闲情", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ac6aa8f5f74483ec103b07458e0525413fee037f.xml", "color": "#ff6b6b"},
    {"key": "地球知识局_295", "name": "地球知识局", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c8500fccbf17324e8e865ef13e1fe972c946ee7c.xml", "color": "#ff6b6b"},
    {"key": "星球研究所_296", "name": "星球研究所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1626938486da8a55e24292d98188a33aa4a6050b.xml", "color": "#ff6b6b"},
    {"key": "利维坦_297", "name": "利维坦", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/46777e07507a7009d645c1ec89917c39ba65334a.xml", "color": "#ff6b6b"},
    {"key": "小众消息_298", "name": "小众消息", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/317e436475d34a5cfdfa094e1b2cc7085413903d.xml", "color": "#ff6b6b"},
    {"key": "互联网怪盗团_299", "name": "互联网怪盗团", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/59d988bead1c70401df2a3a11544e2c5d4df6dc3.xml", "color": "#ff6b6b"},
    {"key": "九边_300", "name": "九边", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b85be415c6565525bb31dffeceb24109bc5dfc77.xml", "color": "#ff6b6b"},
    {"key": "知识分子_301", "name": "知识分子", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e32f65752d69e5ddab37891db2849a93bde4447b.xml", "color": "#ff6b6b"},
    {"key": "deeptech深科技_302", "name": "DeepTech深科技", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7229d3e3e0c59e13fb0b8b3626881488bab76156.xml", "color": "#ff6b6b"},
    {"key": "warfalcon_303", "name": "warfalcon", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/effd0ca5c05e1a8aa6937c07abff3e11266b501c.xml", "color": "#ff6b6b"},
    {"key": "investguru_304", "name": "investguru", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4fb41730a2fa1140fef4d0c1e8e8e70780c7a2c8.xml", "color": "#ff6b6b"},
    {"key": "环球科学_305", "name": "环球科学", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8cbe556234151dbfd436797112383282f3fd3b1c.xml", "color": "#ff6b6b"},
    {"key": "廖信忠_306", "name": "廖信忠", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/349317d9f6208ffd0f0e370b297ed6120b17159b.xml", "color": "#ff6b6b"},
    {"key": "大力如山_307", "name": "大力如山", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e725f176952cae77a5af36a3384eceb4db9b8450.xml", "color": "#ff6b6b"},
    {"key": "新京报书评周刊_308", "name": "新京报书评周刊", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/24adc53cf876f285c77e78254ccb8832ee14dc1c.xml", "color": "#ff6b6b"},
    {"key": "老张投研_309", "name": "老张投研", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/90d66a1550113ac5ee878490529a3bf9f3da8c74.xml", "color": "#ff6b6b"},
    {"key": "心木微笔_310", "name": "心木微笔", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c4be152d8568cb0de06dbf97f164579b80fe614f.xml", "color": "#ff6b6b"},
    {"key": "知乎日报_311", "name": "知乎日报", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/66409f5474b55660063087a3aa0cee09949c60e6.xml", "color": "#ff6b6b"},
    {"key": "真实故事计划_312", "name": "真实故事计划", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/537095dea689bedcd7bf7418cebe0a0aa57ddf4b.xml", "color": "#ff6b6b"},
    {"key": "刘备教授_313", "name": "刘备教授", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1491cf7d5d9179503e809e6e9ffb1da27fed027d.xml", "color": "#ff6b6b"},
    {"key": "理想国imaginist_314", "name": "理想国imaginist", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/cecf220bb3ee02e582839f1f70df4160a8485ecf.xml", "color": "#ff6b6b"},
    {"key": "智族life_315", "name": "智族Life", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ff3731e552a75ee48046d2266887f76671872d4f.xml", "color": "#ff6b6b"},
    {"key": "神经现实_316", "name": "神经现实", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/66c8815235aa2853fb61e2f08d5bd930b4156cef.xml", "color": "#ff6b6b"},
    {"key": "中科院物理所_317", "name": "中科院物理所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ac81c77745a3add18aaaae0bc5832b2f3fb81ccc.xml", "color": "#ff6b6b"},
    {"key": "六神磊磊读金庸_318", "name": "六神磊磊读金庸", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6bb185f6cc614c9ba70fa56b83bb785969665324.xml", "color": "#ff6b6b"},
    {"key": "思想钢印_319", "name": "思想钢印", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9c25c03fc6a13471a096f0737d1cdfe62a7e95bc.xml", "color": "#ff6b6b"},
    {"key": "智族lab_320", "name": "智族Lab", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c29d01cd51dea963eb0a207501e2ee8eaf4f3d8c.xml", "color": "#ff6b6b"},
    {"key": "原理_321", "name": "原理", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6277fa743e14d652186218225a5cff02d437d76e.xml", "color": "#ff6b6b"},
    {"key": "标志情报局_322", "name": "标志情报局", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5704232ef2273a7a9b40754782f61d88fdeaf902.xml", "color": "#ff6b6b"},
    {"key": "游戏研究社_323", "name": "游戏研究社", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c522d602bc999594b7d99aa1199593b8540e4c5c.xml", "color": "#ff6b6b"},
    {"key": "王建硕_324", "name": "王建硕", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/98bc4f50442b51ab17e9e07ff42799377abeabe2.xml", "color": "#ff6b6b"},
    {"key": "返朴_325", "name": "返朴", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/950508da45d4ca1be856422f6fcc6c9822ea0439.xml", "color": "#ff6b6b"},
    {"key": "澎湃新闻_326", "name": "澎湃新闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ed85189b22405227e975c12f106949b0b6b6e0a6.xml", "color": "#ff6b6b"},
    {"key": "读者_327", "name": "读者", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b16a256d8b865ffcae1bd0dda1abc584417dcbb3.xml", "color": "#ff6b6b"},
    {"key": "半月谈_328", "name": "半月谈", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bdc990934c9cc6339857f74131ef82bd32434f31.xml", "color": "#ff6b6b"},
    {"key": "国家人文历史_329", "name": "国家人文历史", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/be3f8c28433331ae342e0c3dd77da3a4b29a1f0a.xml", "color": "#ff6b6b"},
    {"key": "人民日报评论_330", "name": "人民日报评论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3f9af2e0fa36e1305f82f6c7e482dff731e17de9.xml", "color": "#ff6b6b"},
    {"key": "人民网_331", "name": "人民网", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5fd28dd56817044bc6bca1fda2babf1aab34c2ea.xml", "color": "#ff6b6b"},
    {"key": "范冰的二次学习_332", "name": "范冰的二次学习", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/f76c4c4bac53814b2d95010ddfd75305320b5931.xml", "color": "#ff6b6b"},
    {"key": "南方人物周刊_333", "name": "南方人物周刊", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/aad290f27f2806789b2831faacee8b1d05efe1fd.xml", "color": "#ff6b6b"},
    {"key": "正和岛_334", "name": "正和岛", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/1c03ed468f442bd1c16633c05cc39225884f468a.xml", "color": "#ff6b6b"},
    {"key": "界面新闻_335", "name": "界面新闻", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8fb942f54d4395888e787210c710e58631d2dacc.xml", "color": "#ff6b6b"},
    {"key": "浪潮工作室_336", "name": "浪潮工作室", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4badc49b90ce718fb6f4b9e80393463916eaca77.xml", "color": "#ff6b6b"},
    {"key": "pricetag发现好应用_337", "name": "PriceTag发现好应用", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/06ce06c7735de89c7c29df15c64328a034f7c25b.xml", "color": "#ff6b6b"},
    {"key": "红杉汇_338", "name": "红杉汇", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fb9c7a3ba3666dc1b0956b0dac916cd5c56ecf9f.xml", "color": "#ff6b6b"},
    {"key": "银行螺丝钉_339", "name": "银行螺丝钉", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/06bb878110fe389ca828db3bacaec38630c7ddc7.xml", "color": "#ff6b6b"},
    {"key": "集思录_340", "name": "集思录", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bfc272e0503b84b5f0283ff9042ba105990655ed.xml", "color": "#ff6b6b"},
    {"key": "etf进化论_341", "name": "ETF进化论", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0f497c4aabdb12a8831aaa266d595e971962bb68.xml", "color": "#ff6b6b"},
    {"key": "阿虚同学_342", "name": "阿虚同学", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8ca0eb543698f95bc5395520db5ae668949af82d.xml", "color": "#ff6b6b"},
    {"key": "虹膜_343", "name": "虹膜", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/19ea74661aa76e0386193b971962d4a614021109.xml", "color": "#ff6b6b"},
    {"key": "环球设计_344", "name": "环球设计", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/df56a06654519bbce26497d23d868f87fa7c06d4.xml", "color": "#ff6b6b"},
    {"key": "日本设计小站_345", "name": "日本设计小站", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/a88e67882b9c95bb1678b5aac90e630cd5f22c19.xml", "color": "#ff6b6b"},
    {"key": "memm设计知识分享_346", "name": "Memm设计知识分享", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/c0bcc1f9b617d41b978d5d49c1452b3395fec216.xml", "color": "#ff6b6b"},
    {"key": "设计癖_347", "name": "设计癖", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/98a2bf21444bea3b58a241ffc864a23fbaecb36f.xml", "color": "#ff6b6b"},
    {"key": "淘宝设计_348", "name": "淘宝设计", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6d515611c75b76de8e766e08f0beca8c491a8e82.xml", "color": "#ff6b6b"},
    {"key": "独立鱼电影_349", "name": "独立鱼电影", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/826179f766e2376c59c01184bca683a42d0e30f9.xml", "color": "#ff6b6b"},
    {"key": "澎湃思想市场_350", "name": "澎湃思想市场", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/96795edb72b7a9580b24e6662c46be99dd9a905a.xml", "color": "#ff6b6b"},
    {"key": "游戏葡萄_351", "name": "游戏葡萄", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/6aadbb03d02c59093f48afa5723fa2c44d1a81dc.xml", "color": "#ff6b6b"},
    {"key": "后浪研究所_352", "name": "后浪研究所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/7abc9d02f335cf08a49a4957041e5a51da5883d1.xml", "color": "#ff6b6b"},
    {"key": "太阳照常升起_353", "name": "太阳照常升起", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/ddca396fc887ac5006719b240d232ef517bca30e.xml", "color": "#ff6b6b"},
    {"key": "githubdaily_354", "name": "GitHubDaily", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/5b195b2d021f8151ac4f81ceae54cd48f08b0632.xml", "color": "#ff6b6b"},
    {"key": "githubstore_355", "name": "GitHubStore", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bbc6b268b1723fa06b2d2ac382c484cb71ea90fa.xml", "color": "#ff6b6b"},
    {"key": "一天一篇经济学人_356", "name": "一天一篇经济学人", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/fc75f34053a2d04d099e2e797b88df189f0cd76a.xml", "color": "#ff6b6b"},
    {"key": "财经杂志_357", "name": "财经杂志", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/746c29d98c0bec3969f2613b04c4755fd4786f53.xml", "color": "#ff6b6b"},
    {"key": "得到_358", "name": "得到", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/4284c317590bdeedcddf0cf9fccb4b1fc377c97b.xml", "color": "#ff6b6b"},
    {"key": "帆书樊登讲书_359", "name": "帆书樊登讲书", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/eac9a519fee8d8e7c998286758a337c6daaccbae.xml", "color": "#ff6b6b"},
    {"key": "中国金融四十人论坛_360", "name": "中国金融四十人论坛", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/effdfffc5993e7260f3766aaafafc5536b685a54.xml", "color": "#ff6b6b"},
    {"key": "barrons巴伦_361", "name": "Barrons巴伦", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/707728196d05deab425a8dfa96f0084b6946f8cf.xml", "color": "#ff6b6b"},
    {"key": "新榜_362", "name": "新榜", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/16647c855b3c08c6406fb029f3cd9bb826e70d0c.xml", "color": "#ff6b6b"},
    {"key": "运营研究社_363", "name": "运营研究社", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/bc7bf2a738eebe7ef9728f407721300ac884ad74.xml", "color": "#ff6b6b"},
    {"key": "窄播_364", "name": "窄播", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/61bdf2799e5208df45c8bbbd96ba81dd088d2483.xml", "color": "#ff6b6b"},
    {"key": "界面文化_365", "name": "界面文化", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/b51b75b1b2696c32d91ddf300492f2678ba77a0b.xml", "color": "#ff6b6b"},
    {"key": "design360_366", "name": "Design360", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/0caba9bee40b0d980821bc9e8d5959aa75e6c0c7.xml", "color": "#ff6b6b"},
    {"key": "brand的好奇心_367", "name": "BranD的好奇心", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/34d96e92ccf01ddc902863a94dc390794050edd7.xml", "color": "#ff6b6b"},
    {"key": "企鹅吃喝指南_368", "name": "企鹅吃喝指南", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/00271ca16aecf74e8bdf412d761aa9761373e85e.xml", "color": "#ff6b6b"},
    {"key": "wallpaper中文版_369", "name": "Wallpaper中文版", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/3865e1eb71366ebddfc6d292da83fde9162e7b01.xml", "color": "#ff6b6b"},
    {"key": "工业设计_370", "name": "工业设计", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/8d9a13f8abd8e51811fbc1df3c7b0fed7b4b2b68.xml", "color": "#ff6b6b"},
    {"key": "点拾投资_371", "name": "点拾投资", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/e460ce1e8b48d9c4baa4fb762e93e4409c7a14fd.xml", "color": "#ff6b6b"},
    {"key": "三折人生_372", "name": "三折人生", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/70169da59e7e342ec7b63c90351b224b50cf7cb7.xml", "color": "#ff6b6b"},
    {"key": "小lin说的公众号_373", "name": "小Lin说的公众号", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/57bdb3ca8c26dd738f78e44985b1030c4d38ddbf.xml", "color": "#ff6b6b"},
    {"key": "刀法研究所_374", "name": "刀法研究所", "cat": "cn_tech", "url": "https://wechat2rss.bestblogs.dev/feed/9a650290a6093330e410549cea75251cb5a3249c.xml", "color": "#ff6b6b"},

    # ── BestBlogs 播客 (60) ──
    {"key": "张小珺jùn｜商业访谈录_0", "name": "张小珺Jùn｜商业访谈录", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/626b46ea9cbbf0451cf5a962", "color": "#4ecdc4"},
    {"key": "罗永浩的十字路口_1", "name": "罗永浩的十字路口", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/68981df29e7bcd326eb91d88", "color": "#4ecdc4"},
    {"key": "屠龙之术_2", "name": "屠龙之术", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6507bc165c88d2412626b401", "color": "#4ecdc4"},
    {"key": "42章经_3", "name": "42章经", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/648b0b641c48983391a63f98", "color": "#4ecdc4"},
    {"key": "硬地骇客_4", "name": "硬地骇客", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/640ee2438be5d40013fe4a87", "color": "#4ecdc4"},
    {"key": "硅谷101_5", "name": "硅谷101", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e5c52c9418a84a04625e6cc", "color": "#4ecdc4"},
    {"key": "半拿铁_|_商业沉浮录_6", "name": "半拿铁 | 商业沉浮录", "cat": "podcast", "url": "http://rsshub.bestblogs.dev/xiaoyuzhou/podcast/62382c1103bea1ebfffa1c00", "color": "#4ecdc4"},
    {"key": "开始连接_linkstart_7", "name": "开始连接 LinkStart", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/63ff0da51b1faf8a0b70b337", "color": "#4ecdc4"},
    {"key": "高能量_8", "name": "高能量", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/62c6ae08c4eaa82b112b9c84", "color": "#4ecdc4"},
    {"key": "此话当真_9", "name": "此话当真", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/646f194853a5e5ea1408d97c", "color": "#4ecdc4"},
    {"key": "牛油果烤面包_10", "name": "牛油果烤面包", "cat": "podcast", "url": "http://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e7c8b2b418a84a046e3ecbc", "color": "#4ecdc4"},
    {"key": "晚点聊_latetalk_11", "name": "晚点聊 LateTalk", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/61933ace1b4320461e91fd55", "color": "#4ecdc4"},
    {"key": "乱翻书_12", "name": "乱翻书", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/61358d971c5d56efe5bcb5d2", "color": "#4ecdc4"},
    {"key": "tianyu2fm_—_对谈未知领域_13", "name": "TIANYU2FM — 对谈未知领域", "cat": "podcast", "url": "https://rsshub.xiaowuaiblog.com/xiaoyuzhou/podcast/5f22729f9504bbdb77253e46", "color": "#4ecdc4"},
    {"key": "声动早咖啡_14", "name": "声动早咖啡", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/60de7c003dd577b40d5a40f3", "color": "#4ecdc4"},
    {"key": "科技乱炖_15", "name": "科技乱炖", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e4243cd418a84a0469573fb", "color": "#4ecdc4"},
    {"key": "what's_next｜科技早知道_16", "name": "What's Next｜科技早知道", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e74b52c418a84a046ecaceb", "color": "#4ecdc4"},
    {"key": "声东击西_17", "name": "声东击西", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e2831ed418a84a046231c00", "color": "#4ecdc4"},
    {"key": "疯投圈_18", "name": "疯投圈", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e280faf418a84a0461fbd39", "color": "#4ecdc4"},
    {"key": "商业就是这样_19", "name": "商业就是这样", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6022a180ef5fdaddc30bb101", "color": "#4ecdc4"},
    {"key": "枫言枫语_20", "name": "枫言枫语", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e2864f5418a84a04628e249", "color": "#4ecdc4"},
    {"key": "保持偏见_21", "name": "保持偏见", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/663e3c95af1e22bb157dcee3", "color": "#4ecdc4"},
    {"key": "三五环_22", "name": "三五环", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e280fab418a84a0461faa3c", "color": "#4ecdc4"},
    {"key": "皮蛋漫游记_23", "name": "皮蛋漫游记", "cat": "podcast", "url": "http://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6281264ad22bcf3950c80b56", "color": "#4ecdc4"},
    {"key": "ai炼金术_24", "name": "AI炼金术", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/63e9ef4de99bdef7d39944c8", "color": "#4ecdc4"},
    {"key": "十字路口crossing_25", "name": "十字路口Crossing", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/60502e253c92d4f62c2a9577", "color": "#4ecdc4"},
    {"key": "信号与噪声_26", "name": "信号与噪声", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6819d5a7e37664602a344e0e", "color": "#4ecdc4"},
    {"key": "人民公园说ai_27", "name": "人民公园说AI", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65257ff6e8ce9deaf70a65e9", "color": "#4ecdc4"},
    {"key": "跨国串门儿计划_28", "name": "跨国串门儿计划", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/670f3da40d2f24f28978736f", "color": "#4ecdc4"},
    {"key": "知行小酒馆_29", "name": "知行小酒馆", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6013f9f58e2f7ee375cf4216", "color": "#4ecdc4"},
    {"key": "搞钱女孩_30", "name": "搞钱女孩", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/63d945ece725b5378a158d29", "color": "#4ecdc4"},
    {"key": "起朱楼宴宾客_31", "name": "起朱楼宴宾客", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/61dd99a47b29652ff572257b", "color": "#4ecdc4"},
    {"key": "面基_32", "name": "面基", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6388760f22567e8ea6ad070f", "color": "#4ecdc4"},
    {"key": "第一财经_33", "name": "第一财经", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/64c75555e8176c3ff81de98c", "color": "#4ecdc4"},
    {"key": "无人知晓_34", "name": "无人知晓", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/611719d3cb0b82e1df0ad29e", "color": "#4ecdc4"},
    {"key": "纵横四海_35", "name": "纵横四海", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/62694abdb221dd5908417d1e", "color": "#4ecdc4"},
    {"key": "自我进化论_36", "name": "自我进化论", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e5de5cb418a84a0467beb90", "color": "#4ecdc4"},
    {"key": "自习室_study_room_37", "name": "自习室 STUDY ROOM", "cat": "podcast", "url": "http://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65a5fb7540d4ef949c0140ac", "color": "#4ecdc4"},
    {"key": "慢速生长_38", "name": "慢速生长", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/668d00c38fcadceb90158ac1", "color": "#4ecdc4"},
    {"key": "诗梳风_39", "name": "诗梳风", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/696496f4db4738160d5fabde", "color": "#4ecdc4"},
    {"key": "谭立人_40", "name": "谭立人", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65a2d0f07242f9fc1c1df60a", "color": "#4ecdc4"},
    {"key": "李诞_41", "name": "李诞", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65bb55f6513a776b57dedb32", "color": "#4ecdc4"},
    {"key": "岩中花述_42", "name": "岩中花述", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/625635587bfca4e73e990703", "color": "#4ecdc4"},
    {"key": "蒋方舟·一寸_43", "name": "蒋方舟·一寸", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/67c7eeb07ac3e30992e75a2f", "color": "#4ecdc4"},
    {"key": "游荡集_44", "name": "游荡集", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6163ca67c8c1d14e83366b31", "color": "#4ecdc4"},
    {"key": "一席_45", "name": "一席", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e285326418a84a04627343f", "color": "#4ecdc4"},
    {"key": "独树不成林_46", "name": "独树不成林", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/64acd33c7a3d479103fbd32d", "color": "#4ecdc4"},
    {"key": "文化有限_47", "name": "文化有限", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e4515bd418a84a046e2b11a", "color": "#4ecdc4"},
    {"key": "忽左忽右_48", "name": "忽左忽右", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e4ee557418a84a0466737b7", "color": "#4ecdc4"},
    {"key": "梁永安的播客_49", "name": "梁永安的播客", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/61bc1762e5fdeb81a8db115c", "color": "#4ecdc4"},
    {"key": "看理想圆桌_50", "name": "看理想圆桌", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e4ff4c7418a84a046977618", "color": "#4ecdc4"},
    {"key": "不合时宜_51", "name": "不合时宜", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e280fb8418a84a0461fd076", "color": "#4ecdc4"},
    {"key": "天真不天真_52", "name": "天真不天真", "cat": "podcast", "url": "http://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65cef9e3cace72dff8d98de3", "color": "#4ecdc4"},
    {"key": "凹凸电波_53", "name": "凹凸电波", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e2839ca418a84a0462431b7", "color": "#4ecdc4"},
    {"key": "随机波动stochasticvolatility_54", "name": "随机波动StochasticVolatility", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e7cc741418a84a046b0c2bd", "color": "#4ecdc4"},
    {"key": "东腔西调_55", "name": "东腔西调", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5f72b66083c34e85dd14fde9", "color": "#4ecdc4"},
    {"key": "东亚观察局_56", "name": "东亚观察局", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e9a4e25418a84a046bc6156", "color": "#4ecdc4"},
    {"key": "肥话连篇_57", "name": "肥话连篇", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/61d50d72ee197a3aac3dac42", "color": "#4ecdc4"},
    {"key": "捕蛇者说_58", "name": "捕蛇者说", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e2864f7418a84a04628f2da", "color": "#4ecdc4"},
    {"key": "卫诗婕｜漫谈light_the_star_59", "name": "卫诗婕｜漫谈Light the Star", "cat": "podcast", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6627fda4b56459544087d86a", "color": "#4ecdc4"},

    # ── YouTube (124) ──
    {"key": "ai_engineer_0", "name": "AI Engineer", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA", "color": "#4ecdc4"},
    {"key": "ai_explained_1", "name": "AI Explained", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw", "color": "#4ecdc4"},
    {"key": "ai_master_2", "name": "AI Master", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0yHbz4OxdQFwmVX2BBQqLg", "color": "#4ecdc4"},
    {"key": "ai_search_3", "name": "AI Search", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCIgnGlGkVRhd4qNFcEwLL4A", "color": "#4ecdc4"},
    {"key": "ai_video_school_4", "name": "AI Video School", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUb7KwmlVSSCnPu5KEhym8A", "color": "#4ecdc4"},
    {"key": "aicodeking_5", "name": "AICodeKing", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0m81bQuthaQZmFbXEY9QSw", "color": "#4ecdc4"},
    {"key": "andrej_karpathy_6", "name": "Andrej Karpathy", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXUPKJO5MZQN11PqgIvyuvQ", "color": "#4ecdc4"},
    {"key": "anthropic_7", "name": "Anthropic", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCrDwWp7EBBv4NwvScIpBDOA", "color": "#4ecdc4"},
    {"key": "assemblyai_8", "name": "AssemblyAI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCtatfZMf-8EkIwASXM4ts0A", "color": "#4ecdc4"},
    {"key": "claude_9", "name": "Claude", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCV03SRZXJEz-hchIAogeJOg", "color": "#4ecdc4"},
    {"key": "cognitive_revolution_10", "name": "Cognitive Revolution", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCjNRVMBVI30Sak_p6HRWhIA", "color": "#4ecdc4"},
    {"key": "deeplearningai_11", "name": "DeepLearningAI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcIXc5mJsHVYTZR1maL5l9w", "color": "#4ecdc4"},
    {"key": "every_12", "name": "Every", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCjIMtrzxYc0lblGhmOgC_CA", "color": "#4ecdc4"},
    {"key": "futurepedia_13", "name": "Futurepedia", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_RovKmk0OCbuZjA8f08opw", "color": "#4ecdc4"},
    {"key": "google_deepmind_14", "name": "Google DeepMind", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP7jMXSY2xbc3KCAE0MHQ-A", "color": "#4ecdc4"},
    {"key": "how_i_ai_15", "name": "How I AI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCRYY7IEbkHLH_ScJCu9eWDQ", "color": "#4ecdc4"},
    {"key": "hung-yi_lee_16", "name": "Hung-yi Lee", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2ggjtuuWvxrHHHiaDH1dlQ", "color": "#4ecdc4"},
    {"key": "langchain_17", "name": "LangChain", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCC-lyoTfSrcJzA1ab3APAgw", "color": "#4ecdc4"},
    {"key": "last_week_in_ai_18", "name": "Last Week in AI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCKARTq-t5SPMzwtft8FWwnA", "color": "#4ecdc4"},
    {"key": "liam_ottley_19", "name": "Liam Ottley", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCui4jxDaMb53Gdh-AZUTPAg", "color": "#4ecdc4"},
    {"key": "machine_learning_street_talk_20", "name": "Machine Learning Street Talk", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCMLtBahI5DMrt0NPvDSoIRQ", "color": "#4ecdc4"},
    {"key": "matt_wolfe_21", "name": "Matt Wolfe", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UChpleBmo18P08aKCIgti38g", "color": "#4ecdc4"},
    {"key": "mattvidpro_ai_22", "name": "MattVidPro AI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC5Wz4fFacYuON6IKbhSa7Zw", "color": "#4ecdc4"},
    {"key": "matthew_berman_23", "name": "Matthew Berman", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCawZsQWqfGSbCI5yjkdVkTA", "color": "#4ecdc4"},
    {"key": "networkchuck_24", "name": "NetworkChuck", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC9x0AN7BWHpCDHSm9NiJFJQ", "color": "#4ecdc4"},
    {"key": "nick_saraev_25", "name": "Nick Saraev", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbo-KbSjJDG6JWQ_MTZ_rNA", "color": "#4ecdc4"},
    {"key": "no_priors_26", "name": "No Priors", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCSI7h9hydQ40K5MJHnCrQvw", "color": "#4ecdc4"},
    {"key": "openai_27", "name": "OpenAI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXZCJLdBC09xxGZ6gcdrc6A", "color": "#4ecdc4"},
    {"key": "pika_labs_28", "name": "Pika Labs", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0SclYU4iiQRihtmDnak-gQ", "color": "#4ecdc4"},
    {"key": "riley_brown_29", "name": "Riley Brown", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCMcoud_ZW7cfxeIugBflSBw", "color": "#4ecdc4"},
    {"key": "runway_30", "name": "Runway", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUBqu_z5uP0AZhYtuyFZB3g", "color": "#4ecdc4"},
    {"key": "siraj_raval_31", "name": "Siraj Raval", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCWN3xxRkmTPmbKwht9FuE5A", "color": "#4ecdc4"},
    {"key": "tao_prompts_32", "name": "Tao Prompts", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCc1qMq2UBJD9cSKbeBwGoZQ", "color": "#4ecdc4"},
    {"key": "the_ai_advantage_33", "name": "The AI Advantage", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCHhYXsLBEVVnbvsq57n1MTQ", "color": "#4ecdc4"},
    {"key": "tina_huang_34", "name": "Tina Huang", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2UXDak6o7rBm23k3Vv5dww", "color": "#4ecdc4"},
    {"key": "two_minute_papers_35", "name": "Two Minute Papers", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg", "color": "#4ecdc4"},
    {"key": "unsupervised_learning:_redpoin_36", "name": "Unsupervised Learning: Redpoint's AI Podcast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUl-s_Vp-Kkk_XVyDylNwLA", "color": "#4ecdc4"},
    {"key": "wes_roth_37", "name": "Wes Roth", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCqcbQf6yw5KzRoDDcZ_wBSw", "color": "#4ecdc4"},
    {"key": "yannic_kilcher_38", "name": "Yannic Kilcher", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew", "color": "#4ecdc4"},
    {"key": "leerob_39", "name": "leerob", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZMli3czZnd1uoc1ShTouQw", "color": "#4ecdc4"},
    {"key": "跟李沐学ai_40", "name": "跟李沐学AI", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC8WCW6C3BWLKSZ5cMzD8Gyw", "color": "#4ecdc4"},
    {"key": "acquired_41", "name": "Acquired", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCyFqFYfTW2VoIQKylJ04Rtw", "color": "#4ecdc4"},
    {"key": "alex_kantrowitz_42", "name": "Alex Kantrowitz", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCye1YedIypHffYb8k6Gp9wg", "color": "#4ecdc4"},
    {"key": "all-in_podcast_43", "name": "All-In Podcast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCESLZhusAkFfsNsApnjF_Cg", "color": "#4ecdc4"},
    {"key": "better_ideas_44", "name": "Better Ideas", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCtUId5WFnN82GdDy7DgaQ7w", "color": "#4ecdc4"},
    {"key": "branch_education_45", "name": "Branch Education", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCdp4_l1vPmpN-gDbUwhaRUQ", "color": "#4ecdc4"},
    {"key": "business_insider_46", "name": "Business Insider", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcyq283he07B7_KUX07mmtA", "color": "#4ecdc4"},
    {"key": "coldfusion_47", "name": "ColdFusion", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC4QZ_LsYcvcq7qOsOhpAX4A", "color": "#4ecdc4"},
    {"key": "core_memory_podcast_48", "name": "Core Memory Podcast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2ohDbbkpfngjaeV7TBHRcg", "color": "#4ecdc4"},
    {"key": "crashcourse_49", "name": "CrashCourse", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCX6b17PVsYBQ0ip5gyeme-Q", "color": "#4ecdc4"},
    {"key": "curious_refuge_50", "name": "Curious Refuge", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UClnFtyUEaxQOCd1s5NKYGFA", "color": "#4ecdc4"},
    {"key": "dwarkesh_patel_51", "name": "Dwarkesh Patel", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXl4i9dYBrFOabk0xGmbkRA", "color": "#4ecdc4"},
    {"key": "eo_52", "name": "EO", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UClWTCPVi-AU9TeCN6FkGARg", "color": "#4ecdc4"},
    {"key": "google_53", "name": "Google", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCK8sQmJBp8GCxrOtXWBpyEA", "color": "#4ecdc4"},
    {"key": "greg_isenberg_54", "name": "Greg Isenberg", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCPjNBjflYl0-HQtUvOx0Ibw", "color": "#4ecdc4"},
    {"key": "invest_like_the_best_55", "name": "Invest Like The Best", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCpQBb0fToph3jrDulwz1iUQ", "color": "#4ecdc4"},
    {"key": "kurzgesagt_-_in_a_nutshell_56", "name": "Kurzgesagt - In a Nutshell", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q", "color": "#4ecdc4"},
    {"key": "lex_fridman_57", "name": "Lex Fridman", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCSHZKyawb77ixDdsGog4iWA", "color": "#4ecdc4"},
    {"key": "luma_58", "name": "Luma", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC45T0I4p7A3dI0XvhivafZQ", "color": "#4ecdc4"},
    {"key": "my_first_million_59", "name": "My First Million", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCyaN6mg5u8Cjy2ZI4ikWaug", "color": "#4ecdc4"},
    {"key": "naval_60", "name": "Naval", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCh_dVD10YuSghle8g6yjePg", "color": "#4ecdc4"},
    {"key": "nikhil_kamath_61", "name": "Nikhil Kamath", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCnC8SAZzQiBGYVSKZ_S3y4Q", "color": "#4ecdc4"},
    {"key": "sabin_civil_engineering_62", "name": "Sabin Civil Engineering", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCqZQJ4600a9wIfMPbYc60OQ", "color": "#4ecdc4"},
    {"key": "silicon_valley_girl_63", "name": "Silicon Valley Girl", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiq1FIgtEK7LRAOB1JXTPig", "color": "#4ecdc4"},
    {"key": "statquest_with_josh_starmer_64", "name": "StatQuest with Josh Starmer", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCtYLUTtgS3k1Fg4y5tAhLbw", "color": "#4ecdc4"},
    {"key": "stripe_65", "name": "Stripe", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCM1guA1E-RHLO2OyfQPOkEQ", "color": "#4ecdc4"},
    {"key": "the_diary_of_a_ceo_66", "name": "The Diary Of A CEO", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCGq-a57w-aPwyi3pW7XLiHw", "color": "#4ecdc4"},
    {"key": "the_knowledge_project_podcast_67", "name": "The Knowledge Project Podcast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLtTf_uKt0Itd0NG7txrwXA", "color": "#4ecdc4"},
    {"key": "the_primetime_68", "name": "The PrimeTime", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUyeluBRhGPCW4rPe_UvBZQ", "color": "#4ecdc4"},
    {"key": "theoretically_media_69", "name": "Theoretically Media", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC9Ryt3XOGYBoAJVsBHNGDzA", "color": "#4ecdc4"},
    {"key": "this_week_in_startups_70", "name": "This Week in Startups", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCkkhmBWfS7pILYIk0izkc3A", "color": "#4ecdc4"},
    {"key": "thomas_frank_71", "name": "Thomas Frank", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCG-KntY7aVnIGXYEBQvmBAQ", "color": "#4ecdc4"},
    {"key": "y_combinator_72", "name": "Y Combinator", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcefcZRL2oaA_uBNeo5UOWg", "color": "#4ecdc4"},
    {"key": "a16z_73", "name": "a16z", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC9cn0TuPq4dnbTY-CBsm8XA", "color": "#4ecdc4"},
    {"key": "companyman_74", "name": "companyman", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCb4xHi3i7upzKMaLrauVFtg", "color": "#4ecdc4"},
    {"key": "mrblock_區塊先生_75", "name": "mrblock 區塊先生", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCN2hSM8fBcvZBa8OOKc24eg", "color": "#4ecdc4"},
    {"key": "struthless_76", "name": "struthless", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCvcEBQ0K3UsQ8bzWKHKQmbw", "color": "#4ecdc4"},
    {"key": "patrick_boyle_77", "name": "Patrick Boyle", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCASM0cgfkJxQ1ICmRilfHLw", "color": "#4ecdc4"},
    {"key": "sequoia_capital_78", "name": "Sequoia Capital", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCWrF0oN6unbXrWsTN7RctTw", "color": "#4ecdc4"},
    {"key": "andrew_huberman_79", "name": "Andrew Huberman", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2D2CMWXMOVWx7giW1n3LIg", "color": "#4ecdc4"},
    {"key": "chris_williamson_80", "name": "Chris Williamson", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCIaH-gZIVC432YRjNVvnyCA", "color": "#4ecdc4"},
    {"key": "mrbeast_81", "name": "MrBeast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA", "color": "#4ecdc4"},
    {"key": "national_geographic_82", "name": "National Geographic", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCpVm7bg6pXKo1Pr6k5kxG9A", "color": "#4ecdc4"},
    {"key": "powerfuljre_83", "name": "PowerfulJRE", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCzQUP1qoWDoEbmsQxvdjxgQ", "color": "#4ecdc4"},
    {"key": "smartereveryday_84", "name": "SmarterEveryDay", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6107grRI4m0o2-emgoDnAA", "color": "#4ecdc4"},
    {"key": "white_cube_youtube_85", "name": "White Cube YouTube", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC488ANgGUANDqqhlr_eF9JQ", "color": "#4ecdc4"},
    {"key": "一席_86", "name": "一席", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCKFB_rVEFEF3l-onQGvGx1A", "color": "#4ecdc4"},
    {"key": "一条_87", "name": "一条", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCulFhrW_YCwkq_BP16C82mA", "color": "#4ecdc4"},
    {"key": "ted_88", "name": "TED", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCAuUUnT6oDeKwE6v1NGQxug", "color": "#4ecdc4"},
    {"key": "aj&smart_89", "name": "AJ&Smart", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCeB_OpLspKJGiKv1CYkWFFw", "color": "#4ecdc4"},
    {"key": "designcourse_90", "name": "DesignCourse", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCVyRiMvfUNMA1UPlDPzG5Ow", "color": "#4ecdc4"},
    {"key": "designerup_91", "name": "DesignerUp", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCw2R8kz3aotYtV9utqf0uaw", "color": "#4ecdc4"},
    {"key": "figma_92", "name": "Figma", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCQsVmhSa4X-G3lHlUtejzLA", "color": "#4ecdc4"},
    {"key": "first_of_kind_93", "name": "First of Kind", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCSuJzNoyNb6ICi8punp3mCg", "color": "#4ecdc4"},
    {"key": "flux_academy_94", "name": "Flux Academy", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCN7dywl5wDxTu1RM3eJ_h9Q", "color": "#4ecdc4"},
    {"key": "lenny's_podcast_95", "name": "Lenny's Podcast", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6t1O76G0jYXOAoYCm153dA", "color": "#4ecdc4"},
    {"key": "mind_the_product_96", "name": "Mind the Product", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiT1BmYvOBsEvU9iw0076Sw", "color": "#4ecdc4"},
    {"key": "nngroup_97", "name": "NNgroup", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2oCugzU6W8-h95W7eBTUEg", "color": "#4ecdc4"},
    {"key": "product_school_98", "name": "Product School", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6hlQ0x6kPbAGjYkoz53cvA", "color": "#4ecdc4"},
    {"key": "the_futur_99", "name": "The Futur", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC-b3c7kxa5vU-bnmaROgvog", "color": "#4ecdc4"},
    {"key": "yobi321_100", "name": "yobi321", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCB_DbqNN9w30tnyWJSrIwyA", "color": "#4ecdc4"},
    {"key": "3blue1brown_101", "name": "3Blue1Brown", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCYO_jab_esuFRV4b17AJtAw", "color": "#4ecdc4"},
    {"key": "ali_abdaal_102", "name": "Ali Abdaal", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCoOae5nYA7VqaXzerajD0lg", "color": "#4ecdc4"},
    {"key": "anthony_vicino_103", "name": "Anthony Vicino", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCpTupIxGdmt3sTpOHjegwxQ", "color": "#4ecdc4"},
    {"key": "justin_sung_104", "name": "Justin Sung", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2Zs9v2hL2qZZ7vsAENsg4w", "color": "#4ecdc4"},
    {"key": "matt_d'avella_105", "name": "Matt D'Avella", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJ24N4O0bP7LGLBDvye7oCA", "color": "#4ecdc4"},
    {"key": "minutephysics_106", "name": "minutephysics", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUHW94eEFW7hkUMVaZz4eDg", "color": "#4ecdc4"},
    {"key": "李永乐老师_107", "name": "李永乐老师", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCvNxfitQbWkmLuCd44UfrYQ", "color": "#4ecdc4"},
    {"key": "amigoscode_108", "name": "Amigoscode", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2KfmYEM4KCuA1ZurravgYw", "color": "#4ecdc4"},
    {"key": "beyond_coding_109", "name": "Beyond Coding", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCdMz6KKEDW_1Qqas-ya7S6w", "color": "#4ecdc4"},
    {"key": "bytebytego_110", "name": "ByteByteGo", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZgt6AzoyjslHTC9dz0UoTw", "color": "#4ecdc4"},
    {"key": "computerphile_111", "name": "Computerphile", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC9-y-6csu5WGm29I7JiwpnA", "color": "#4ecdc4"},
    {"key": "fireship_112", "name": "Fireship", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA", "color": "#4ecdc4"},
    {"key": "github_113", "name": "GitHub", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC7c3Kb6jYCRj4JOHHZTxKsQ", "color": "#4ecdc4"},
    {"key": "hussein_nasser_114", "name": "Hussein Nasser", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_ML5xP23TOWKUcc-oAE_Eg", "color": "#4ecdc4"},
    {"key": "modern_software_engineering_115", "name": "Modern Software Engineering", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCCfqyGl3nq_V0bo64CjZh8g", "color": "#4ecdc4"},
    {"key": "real_engineering_116", "name": "Real Engineering", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCR1IuLEqb6UEA_zQ81kwXfg", "color": "#4ecdc4"},
    {"key": "ryan_peterman_117", "name": "Ryan Peterman", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCzB7YGrrxDC_POenf86H3_Q", "color": "#4ecdc4"},
    {"key": "spring_i_o_118", "name": "Spring I/O", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLMPXsvSrhNPN3i9h-u8PYg", "color": "#4ecdc4"},
    {"key": "the_pragmatic_engineer_119", "name": "The Pragmatic Engineer", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCPbwhExawYrn9xxI21TFfyw", "color": "#4ecdc4"},
    {"key": "theo_-_t3․gg_120", "name": "Theo - t3․gg", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbRP3c757lWg9M-U7TyEkXA", "color": "#4ecdc4"},
    {"key": "traversy_media_121", "name": "Traversy Media", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC29ju8bIPH5as8OGnQzwJyA", "color": "#4ecdc4"},
    {"key": "web_dev_simplified_122", "name": "Web Dev Simplified", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCFbNIlppjAuEX4znoulh0Cw", "color": "#4ecdc4"},
    {"key": "freecodecamp.org_123", "name": "freeCodeCamp.org", "cat": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC8butISFwT-Wl7EV0hUK0BQ", "color": "#4ecdc4"},

]

# 分类标签
CATEGORY_LABELS = {
    "ai":      "AI 日报",
    "tech":    "科技资讯",
    "cn_tech": "中文科技",
    "dev":     "开发者",
    "news":    "综合新闻",
    "podcast": "播客",
    "youtube": "YouTube",
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
    text = html_mod.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"<[^>]*$", "", text)  # 移除末尾未闭合的标签片段
    return text.strip()


_SAFE_TAGS = re.compile(
    r"^(/?(p|br|img|a|b|i|em|strong|h[1-6]|ul|ol|li|blockquote|pre|code"
    r"|figure|figcaption|table|tr|td|th|thead|tbody|span|div|hr|sup|sub|dl|dt|dd))$",
    re.IGNORECASE,
)
_EVT_ATTR = re.compile(r"^on[a-z]+$", re.IGNORECASE)
_TAG_NAME = re.compile(r"^/?(\w[\w-]*)")


def _sanitize_html(text):
    if not text:
        return ""
    text = html_mod.unescape(text)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<iframe[^>]*>[\s\S]*?</iframe>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<form[^>]*>[\s\S]*?</form>", "", text, flags=re.IGNORECASE)

    def _clean_tag(m):
        full = m.group(0)
        m_name = _TAG_NAME.match(full)
        if not m_name:
            return ""
        tag = m_name.group(1)
        if not _SAFE_TAGS.match(tag):
            return ""
        attrs = re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', full)
        safe_attrs = []
        for k, v in attrs:
            if _EVT_ATTR.match(k):
                continue
            if k.lower() == "href" and v.strip().lower().startswith("javascript:"):
                continue
            safe_attrs.append('%s="%s"' % (k, v))
        if safe_attrs:
            return "<%s %s>" % (tag, " ".join(safe_attrs))
        if full.startswith("</"):
            return "</%s>" % tag
        return "<%s>" % tag

    text = re.sub(r"<[^>]+>", _clean_tag, text)
    text = re.sub(r"<[^>]*$", "", text)
    return text.strip()


def _truncate(s, maxlen=500):
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
    # 缓存命中时 pub_date 已是 ISO 字符串（主流程会将其序列化），先反序列化
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except ValueError:
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
    # 先清理 HTML 标签
    text = _strip_html(text)
    if not text:
        return ""
    # 如果已经是中文为主，跳过
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cn_chars > len(text) * 0.3:
        _TRANS_STATS["skip"] += 1
        return text

    # 查缓存（使用 MD5 确保跨进程一致性）
    text_hash = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
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
            desc = _strip_html(e.findtext(ns + "summary") or "")
            atom_content = _sanitize_html(e.findtext(ns + "content") or "")
            full_content = atom_content if len(atom_content) > len(desc) else ""
            pub = e.findtext(ns + "updated") or e.findtext(ns + "published") or ""
            if not title or not link:
                continue
            items.append({
                "title": title, "link": link, "summary": _truncate(desc),
                "full_content": full_content,
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
    dc_content = "{http://purl.org/rss/1.0/modules/content/}"
    content_encoded = _sanitize_html(it.findtext(dc_content + "encoded") or "")
    full_content = content_encoded if len(content_encoded) > len(desc) else ""
    if not title or not link:
        return
    items.append({
        "title": title, "link": link, "summary": _truncate(desc),
        "full_content": full_content,
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
  --display:"Noto Serif SC","Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:"Noto Sans SC",-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"IBM Plex Mono","SF Mono","Fira Code","Consolas",monospace;
  --radius:8px;
  --shadow:0 1px 2px rgba(28,25,23,.05);
  --shadow-lift:0 10px 26px rgba(0,0,0,.10),0 2px 4px rgba(0,0,0,.06);
  --cat-tech:#2f5d8a; --cat-cn_tech:#c2434d; --cat-dev:#7052c9; --cat-ai:#b06a10; --cat-news:#8a6d1f; --cat-podcast:#2e7d5f; --cat-youtube:#e0245e;
  --unread:#1a8a3f; --read-badge:#c0392b;
}
[data-theme="dark"] {
  --bg:#161412; --card:#1d1a17; --card-2:#262019; --card-3:#2f2820;
  --ink:#ece7df; --muted:#a59d90; --faint:#98907f;
  --line:#37312a; --line-strong:#4a4339;
  --brand:#8fb3d9; --brand-strong:#b0cbe6; --brand-line:#3d5a78; --brand-weak:#22303f;
  --shadow:0 1px 2px rgba(0,0,0,.4);
  --shadow-lift:0 10px 26px rgba(0,0,0,.5),0 2px 4px rgba(0,0,0,.4);
  --cat-tech:#8fb3d9; --cat-cn_tech:#e08790; --cat-dev:#a894e8; --cat-ai:#d3a15c; --cat-news:#cbb26a; --cat-podcast:#6cba9c; --cat-youtube:#ff4d79;
  --unread:#4ade80; --read-badge:#f87171;
}
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
html { scroll-behavior:smooth; }
body { font-family:var(--body); background:var(--bg); color:var(--ink); line-height:1.55; font-size:14px; -webkit-font-smoothing:antialiased; }
a { color:inherit; text-decoration:none; }
button { font-family:inherit; cursor:pointer; border:none; background:none; color:inherit; }

/* ── Header ── */
header { position:sticky; top:0; z-index:40; background:rgba(250,249,247,.94); backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }
[data-theme="dark"] header { background:rgba(22,20,18,.94); }
.hd { max-width:1560px; margin:0 auto; padding:9px 20px; display:flex; align-items:center; gap:12px; }
.hd .logo { display:flex; align-items:center; gap:8px; flex:none; font-family:var(--display); font-weight:900; font-size:16px; }
.hd .logo .sub { font-size:11px; color:var(--muted); font-weight:400; margin-left:2px; font-family:var(--body); }
.hd .nav-links { display:flex; align-items:center; gap:2px; flex:1; }
.hd .nav-links a { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; padding:5px 12px; border-radius:999px; font-size:12.5px; font-weight:500; border:1px solid transparent; transition:all .15s; }
.hd .nav-links a:hover { background:var(--card); border-color:var(--line); }
.hd .nav-links a.active { background:var(--brand-weak); border-color:var(--brand-line); color:var(--brand-strong); font-weight:600; }
.hd .nav-links a .icon { width:13px; height:13px; }
.theme-btn { width:30px; height:30px; border-radius:999px; background:var(--card); border:1px solid var(--line); display:flex; align-items:center; justify-content:center; flex:none; transition:all .15s; }
.theme-btn:hover { border-color:var(--brand-line); }
.theme-btn svg { width:14px; height:14px; }

/* ── Toolbar ── */
.toolbar { max-width:1560px; margin:0 auto; padding:14px 20px 4px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.toolbar h1 { font-family:var(--display); font-size:19px; font-weight:900; margin-right:2px; }
.src-btn { display:inline-flex; align-items:center; gap:6px; padding:5px 13px; border-radius:999px; font-size:12.5px; font-weight:600; border:1px solid var(--brand-line); background:var(--brand-weak); color:var(--brand-strong); transition:all .15s; }
.src-btn:hover { background:var(--brand-strong); color:#fff; }
.src-btn svg { width:13px; height:13px; }
.src-btn .cnt { font-family:var(--mono); font-size:10px; opacity:.8; }
.chips { display:flex; gap:6px; flex-wrap:wrap; }
.chip { padding:4px 12px; border-radius:999px; font-size:12px; font-weight:500; border:1px solid var(--line); background:var(--card); color:var(--muted); transition:all .15s; white-space:nowrap; }
.chip:hover { border-color:var(--line-strong); color:var(--ink); }
.chip.on { background:var(--brand-weak); border-color:var(--brand-line); color:var(--brand-strong); font-weight:600; }
.refresh-btn{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--muted);transition:all .15s;cursor:pointer;}
.refresh-btn:hover{border-color:var(--brand-line);color:var(--brand-strong);background:var(--brand-weak);}
.refresh-btn.loading{pointer-events:none;opacity:.7;}
.refresh-btn.loading svg{animation:spin 1s linear infinite;}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.refresh-btn svg{width:13px;height:13px;}
.unread-toggle{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--muted);transition:all .15s;cursor:pointer;}
.unread-toggle:hover{border-color:var(--brand-line);color:var(--brand-strong);background:var(--brand-weak);}
.unread-toggle.on{background:var(--brand-weak);border-color:var(--brand-line);color:var(--brand-strong);}
.unread-toggle svg{width:13px;height:13px;}
.mark-all-btn{width:28px;height:28px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;color:var(--faint);border:1px solid var(--line);background:var(--card);cursor:pointer;transition:all .15s;padding:0;flex:none;}
.mark-all-btn:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.mark-all-btn svg{width:14px;height:14px;}
.back-top{position:fixed;bottom:24px;right:24px;width:40px;height:40px;border-radius:50%;background:var(--card);border:1px solid var(--line);color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:0;pointer-events:none;transition:all .2s;z-index:90;box-shadow:0 2px 8px rgba(0,0,0,.08);}
.back-top.show{opacity:1;pointer-events:auto;}
.back-top:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.back-top svg{width:18px;height:18px;}
.bm-btn{width:22px;height:22px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;color:var(--faint);border:1px solid transparent;transition:all .15s;cursor:pointer;background:none;padding:0;flex:none;}
.bm-btn:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.bm-btn.on{color:var(--brand-strong);}
.bm-btn svg{width:12px;height:12px;}
.bm-btn.on svg{fill:currentColor;}
.r2-bm{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;color:var(--muted);background:none;border:1px solid var(--line);padding:3px 10px;border-radius:8px;cursor:pointer;transition:all .15s;}
.r2-bm:hover{border-color:var(--brand-line);color:var(--brand-strong);background:var(--brand-weak);}
.r2-bm.on{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.r2-bm svg{width:13px;height:13px;}
.r2-bm.on svg{fill:currentColor;}
.chip.bm-chip{color:var(--muted);border-color:var(--line);}
.chip.bm-chip.on{background:var(--brand-weak);border-color:var(--brand-line);color:var(--brand-strong);}
.chip .n { font-family:var(--mono); font-size:10px; opacity:.75; margin-left:3px; }
.fpill { display:inline-flex; align-items:center; gap:6px; padding:4px 6px 4px 12px; border-radius:999px; font-size:12px; font-weight:600; background:var(--ink); color:var(--bg); }
.fpill .x { width:16px; height:16px; border-radius:999px; background:rgba(255,255,255,.18); display:flex; align-items:center; justify-content:center; font-size:11px; cursor:pointer; }
.fpill .x:hover { background:rgba(255,255,255,.34); }
.tool-meta { margin-left:auto; font-family:var(--mono); font-size:11px; color:var(--faint); white-space:nowrap; }

/* ── Global search ── */
.global-search { position:relative; flex:0 1 260px; min-width:140px; }
.global-search input { width:100%; padding:5px 28px 5px 10px; border-radius:999px; border:1px solid var(--line); background:var(--card); font-size:12.5px; color:var(--ink); font-family:var(--body); outline:none; transition:border-color .15s, box-shadow .15s; }
.global-search input:focus { border-color:var(--brand-line); box-shadow:0 0 0 2px var(--brand-weak); }
.global-search input:focus-visible { outline:2px solid var(--brand); outline-offset:1px; }
button:focus-visible, .chip:focus-visible, .card:focus-visible, a:focus-visible { outline:2px solid var(--brand); outline-offset:2px; border-radius:var(--radius); }
.global-search input::placeholder { color:var(--faint); }
.global-search .sx { position:absolute; right:6px; top:50%; transform:translateY(-50%); width:18px; height:18px; border-radius:999px; background:var(--line); color:var(--muted); display:none; align-items:center; justify-content:center; font-size:10px; cursor:pointer; transition:all .15s; }
.global-search .sx:hover { background:var(--line-strong); color:var(--ink); }
.global-search.has-q .sx { display:flex; }
.global-search.has-q input { border-color:var(--brand-line); background:var(--brand-weak); }

/* ── Card wall ── */
.wall-wrap { max-width:1560px; margin:0 auto; padding:14px 20px 60px; }
.wall { columns:4 300px; column-gap:14px; }
.card { break-inside:avoid; margin-bottom:14px; background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:15px 17px 12px; cursor:pointer; position:relative; transition:box-shadow .18s, border-color .18s, transform .18s; }
.card:hover { border-color:var(--brand-line); box-shadow:var(--shadow-lift); transform:translateY(-2px); }
.card.open { border-color:var(--brand); box-shadow:0 0 0 1px var(--brand-line); }
.card-top { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.cat-tag { font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
.cat-tag::before { content:""; display:inline-block; width:7px; height:7px; border-radius:2px; margin-right:5px; vertical-align:1px; background:var(--cc); }
.card-time { font-family:var(--mono); font-size:10.5px; color:var(--faint); margin-left:auto; }
.ext-btn { flex:none; width:22px; height:22px; border-radius:6px; display:flex; align-items:center; justify-content:center; color:var(--faint); border:1px solid transparent; transition:all .15s; }
.ext-btn:hover { color:var(--brand-strong); border-color:var(--brand-line); background:var(--brand-weak); }
.ext-btn svg { width:11px; height:11px; }
.card-title { font-family:var(--display); font-size:15.5px; font-weight:700; line-height:1.45; margin-bottom:7px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; color:var(--unread); transition:color .15s; }
.card:hover .card-title { color:var(--brand-strong); }
.card-summary { font-size:12.5px; color:var(--muted); line-height:1.7; display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }
.card-foot { display:flex; align-items:center; gap:6px; margin-top:11px; padding-top:9px; border-top:1px solid var(--line); font-size:11px; color:var(--faint); }
.src-dot { width:8px; height:8px; border-radius:999px; flex:none; background:var(--sc); }
[data-theme="dark"] .src-dot { filter:brightness(1.7) saturate(.85); }
.src-name { font-weight:600; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.foot-meta { margin-left:auto; font-family:var(--mono); font-size:10.5px; display:flex; gap:8px; align-items:center; white-space:nowrap; }
.no-ft { font-size:10px; color:var(--faint); border:1px dashed var(--line-strong); border-radius:4px; padding:0 5px; }
.card.visited { border-left:3px solid var(--line-strong); background:color-mix(in srgb, var(--card-2) 50%, var(--card)); }
.card.visited .card-title { color:var(--faint); opacity:.72; }
.card.visited .card-title::after { content:"\\5df2 \\8bfb"; font-family:var(--body); font-size:9px; font-weight:600; color:#fff; background:var(--read-badge); border-radius:4px; padding:0 5px; margin-left:6px; vertical-align:2px; }
.card.visited .card-summary { opacity:.65; }
.pod-chip { display:inline-flex; align-items:center; gap:4px; font-size:10.5px; color:var(--cat-podcast); background:color-mix(in srgb, var(--cat-podcast) 10%, transparent); border-radius:4px; padding:1px 6px; font-weight:600; }
.empty-hint { text-align:center; color:var(--faint); font-size:13px; padding:60px 0; line-height:2; }
mark{background:var(--brand-weak);color:var(--brand-strong);padding:0 2px;border-radius:3px;}
.search-banner{padding:8px 16px;font-size:13px;color:var(--muted);background:var(--brand-weak);border:1px solid var(--brand-line);border-radius:10px;margin-bottom:8px;}


/* ── Source panel (left drawer) ── */
.src-panel { position:fixed; top:0; left:0; bottom:0; width:min(340px,90vw); z-index:80; background:var(--card); border-right:1px solid var(--line); transform:translateX(-103%); transition:transform .28s cubic-bezier(.32,.72,.28,1); display:flex; flex-direction:column; box-shadow:18px 0 50px rgba(0,0,0,.12); }
body.src-open .src-panel { transform:none; }
.sp-head { flex:none; padding:14px 14px 10px; border-bottom:1px solid var(--line); }
.sp-head .row { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
.sp-head h2 { font-family:var(--display); font-size:15px; font-weight:900; flex:1; }
.sp-close { width:26px; height:26px; border-radius:999px; border:1px solid var(--line); display:flex; align-items:center; justify-content:center; color:var(--muted); transition:all .15s; }
.sp-close:hover { border-color:var(--line-strong); color:var(--ink); }
.sp-close svg { width:12px; height:12px; }
.sp-search { display:flex; align-items:center; gap:6px; padding:6px 10px; border-radius:8px; background:var(--bg); border:1px solid var(--line); }
.sp-search svg { width:12px; height:12px; color:var(--faint); flex:none; }
.sp-search input { border:0; background:transparent; outline:none; font-size:12px; color:var(--ink); font-family:var(--body); width:100%; }
.sp-search input::placeholder { color:var(--faint); }
.sp-list { flex:1; overflow-y:auto; padding-bottom:20px; }
.sp-all { display:flex; align-items:center; gap:8px; padding:9px 16px; font-size:13px; font-weight:600; cursor:pointer; color:var(--muted); border-left:3px solid transparent; transition:all .1s; }
.sp-all:hover { background:var(--bg); color:var(--ink); }
.sp-all.on { color:var(--brand-strong); background:var(--brand-weak); border-left-color:var(--brand); }
.sp-all .n { margin-left:auto; font-family:var(--mono); font-size:10.5px; color:var(--faint); }
.sp-cat { position:sticky; top:0; background:var(--card); padding:10px 16px 4px; font-size:10.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--cc); display:flex; align-items:center; gap:5px; cursor:pointer; user-select:none; }
.sp-cat .arrow { font-size:9px; color:var(--faint); transition:transform .15s; }
.sp-cat.folded .arrow { transform:rotate(-90deg); }
.sp-cat .n { margin-left:auto; font-family:var(--mono); font-size:10px; color:var(--faint); }
.sp-cat-body { }
.sp-src { display:flex; align-items:center; gap:8px; padding:7px 16px; font-size:12.5px; cursor:pointer; color:var(--muted); border-left:3px solid transparent; transition:all .1s; }
.sp-src:hover { background:var(--bg); color:var(--ink); }
.sp-src.on { color:var(--brand-strong); background:var(--brand-weak); border-left-color:var(--brand); font-weight:600; }
.sp-src .nm { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sp-src .n { margin-left:auto; font-family:var(--mono); font-size:10.5px; color:var(--faint); flex:none; }
.sp-src .src-dot { width:9px; height:9px; }
.sp-none { padding:14px 16px; font-size:12px; color:var(--faint); }

/* ── Scrim ── */
.scrim { position:fixed; inset:0; background:rgba(28,25,23,.45); opacity:0; pointer-events:none; transition:opacity .25s; z-index:60; }
body.reading .scrim, body.src-open .scrim { opacity:1; pointer-events:auto; }

/* ── Reader modal (centered) ─ */
.reader2 { position:fixed; top:50%; left:50%; width:min(640px,92vw); max-height:88vh; z-index:70; background:var(--bg); border-radius:14px; box-shadow:0 24px 80px rgba(0,0,0,.22); transform:translate(-50%,-50%) scale(.96); opacity:0; pointer-events:none; transition:transform .25s cubic-bezier(.32,.72,.28,1), opacity .2s; display:flex; flex-direction:column; overflow:hidden; }
body.reading .reader2 { transform:translate(-50%,-50%) scale(1); opacity:1; pointer-events:auto; }
.r2-top { flex:none; display:flex; align-items:center; gap:10px; padding:10px 18px; border-bottom:1px solid var(--line); background:var(--card); position:relative; }
.r2-progress { position:absolute; left:0; bottom:-1px; height:2px; background:var(--brand); width:0%; transition:width .1s linear; }
.r2-back { display:flex; align-items:center; gap:5px; font-size:12.5px; font-weight:600; color:var(--muted); padding:5px 10px 5px 6px; border-radius:999px; border:1px solid transparent; white-space:nowrap; transition:all .15s; }
.r2-back:hover { color:var(--ink); border-color:var(--line); background:var(--bg); }
.r2-back svg { width:14px; height:14px; }
.r2-src { display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted); min-width:0; }
.r2-src .src-dot { width:9px; height:9px; }
.r2-src b { color:var(--ink); font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.r2-acts { margin-left:auto; display:flex; align-items:center; gap:8px; }
.r2-open { display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600; color:var(--brand-strong); background:var(--brand-weak); border:1px solid var(--brand-line); padding:4px 12px; border-radius:8px; white-space:nowrap; transition:all .15s; }
.r2-open:hover { background:var(--brand-strong); color:#fff; }
.r2-body { flex:1; overflow-y:auto; }
.r2-body.fs-sm .r2-summary { font-size:13.5px; }
.r2-body.fs-md .r2-summary { font-size:15px; }
.r2-body.fs-lg .r2-summary { font-size:17.5px; }
.r2-fs-btns { display:inline-flex; align-items:center; gap:2px; margin-right:4px; }
.r2-fs-btn { width:26px; height:26px; border-radius:6px; display:inline-flex; align-items:center; justify-content:center; font-weight:700; font-size:11px; border:1px solid var(--line); background:var(--card); color:var(--muted); cursor:pointer; transition:all .15s; font-family:var(--body); }
.r2-fs-btn:hover { border-color:var(--brand-line); color:var(--brand-strong); background:var(--brand-weak); }
.r2-fs-btn.active { background:var(--brand-weak); border-color:var(--brand-line); color:var(--brand-strong); }
.r2-inner { max-width:680px; margin:0 auto; padding:30px 34px 80px; }
.r2-title { font-family:var(--display); font-size:23px; font-weight:900; line-height:1.42; margin-bottom:12px; }
.r2-title a { color:var(--ink); }
.r2-title a:hover { color:var(--brand-strong); }
.r2-meta { display:flex; align-items:center; gap:10px; font-size:12px; color:var(--faint); padding-bottom:16px; margin-bottom:22px; border-bottom:1px solid var(--line); flex-wrap:wrap; }
.r2-meta .src-dot { width:9px; height:9px; }
.r2-meta .cat { font-weight:700; letter-spacing:.06em; font-size:10.5px; text-transform:uppercase; color:var(--cc); }
.r2-summary { font-size:15px; line-height:1.9; color:var(--ink); }
.r2-summary p { margin:0 0 1.2em 0; }
.r2-summary p:last-child { margin-bottom:0; }
.r2-fulltext { margin-top:20px; padding-top:20px; border-top:1px solid var(--line); font-size:15px; line-height:1.9; color:var(--ink); }
.r2-fulltext p { margin:0 0 1.2em 0; }
.r2-fulltext p:last-child { margin-bottom:0; }
.r2-fulltext img { max-width:100%; height:auto; border-radius:var(--radius); margin:1em 0; }
.r2-fulltext pre { background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:14px 16px; overflow-x:auto; font-size:13px; line-height:1.6; margin:1em 0; }
.r2-fulltext code { font-family:var(--mono); font-size:0.9em; background:var(--bg); padding:1px 5px; border-radius:4px; }
.r2-fulltext pre code { background:none; padding:0; }
.r2-fulltext blockquote { border-left:3px solid var(--brand-line); margin:1em 0; padding:4px 16px; color:var(--muted); background:var(--brand-weak); border-radius:0 8px 8px 0; }
.r2-fulltext h1,.r2-fulltext h2,.r2-fulltext h3 { font-family:var(--display); margin:1.5em 0 0.6em; }
.r2-fulltext h1 { font-size:20px; } .r2-fulltext h2 { font-size:18px; } .r2-fulltext h3 { font-size:16px; }
.r2-fulltext a { color:var(--brand-strong); text-decoration:underline; text-underline-offset:2px; }
.r2-fulltext ul,.r2-fulltext ol { margin:0.8em 0; padding-left:1.5em; }
.r2-fulltext li { margin-bottom:0.4em; }
.r2-fulltext table { border-collapse:collapse; width:100%; margin:1em 0; font-size:14px; }
.r2-fulltext th,.r2-fulltext td { border:1px solid var(--line); padding:6px 10px; text-align:left; }
.r2-fulltext th { background:var(--bg); font-weight:600; }
.r2-ft-loading { display:flex; align-items:center; gap:8px; padding:16px 0; color:var(--faint); font-size:13px; }
.r2-ft-loading svg { width:16px; height:16px; animation:spin 1s linear infinite; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
.r2-summary .lead { font-size:16.5px; line-height:1.85; font-weight:500; margin-bottom:1em; }
.r2-lang-toggle { display:inline-flex; align-items:center; gap:0; margin-top:16px; border-radius:var(--radius); overflow:hidden; border:1px solid var(--line); font-size:12px; }
.r2-lang-toggle button { padding:4px 12px; border:none; background:transparent; color:var(--muted); cursor:pointer; transition:all .15s; font-family:var(--body); font-size:12px; }
.r2-lang-toggle button.active { background:var(--brand); color:#fff; }
.r2-lang-toggle button:hover:not(.active) { background:var(--brand-weak); }
.fallback-card { border:1px dashed var(--line-strong); border-radius:10px; padding:22px; text-align:center; background:var(--card); margin-top:6px; }
.fallback-card .fb-ico { font-size:22px; margin-bottom:8px; }
.fallback-card p { font-size:13px; color:var(--muted); margin-bottom:16px; line-height:1.7; }
.fb-btn { display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600; padding:9px 20px; border-radius:8px; background:var(--brand-weak); color:var(--brand-strong); border:1px solid var(--brand-line); transition:all .15s; }
.fb-btn:hover { background:var(--brand-line); color:#fff; }
.r2-foot-hint { text-align:center; font-family:var(--mono); font-size:10.5px; color:var(--faint); padding:26px 0 6px; border-top:1px solid var(--line); margin-top:34px; }

/* ── Footer ── */
.footer { text-align:center; padding:6px 0; font-size:11px; color:var(--faint); font-family:var(--mono); border-top:1px solid var(--line); background:var(--bg); }

/* ── Build bar ── */
.build-bar { background:var(--bg); max-width:1560px; margin:0 auto; padding:2px 20px 8px; display:flex; align-items:center; gap:10px; font-family:var(--mono); font-size:11px; color:var(--faint); border-bottom:1px solid var(--line); }

/* ── Reduced motion ── */
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition-duration:0s!important; animation-duration:0s!important; } }

/* ── Responsive ── */
@media (max-width:1100px) { .wall { columns:3 280px; } }
@media (max-width:900px) {
  .hd .logo .sub { display:none; }
  .toolbar { padding:12px 14px 2px; }
  .wall-wrap { padding:12px 14px 50px; }
  .wall { columns:2 260px; }
  .r2-inner { padding:22px 20px 70px; }
  .tool-meta { display:none; }
  .global-search { flex:1 1 100%; order:10; margin-top:6px; }
  .build-bar { padding:2px 14px 6px; }
}
@media (max-width:700px) {
  .hd .nav-links a { padding:5px 9px; font-size:12px; }
  .chips { overflow-x:auto; flex-wrap:nowrap; max-width:100%; padding-bottom:4px; }
  .chip { white-space:nowrap; flex:none; }
  .wall { columns:1 minmax(0,1fr); }
  .reader2 { width:96vw; max-height:92vh; border-radius:12px; }
  .r2-top { padding:8px 12px; }
  .r2-back span { display:none; }
  .r2-src b { max-width:110px; }
  .r2-open { padding:4px 9px; }
  .r2-inner { padding:18px 16px 60px; }
  .r2-title { font-size:19px; }
  .r2-summary { font-size:14px; line-height:1.8; }
  .r2-summary p { margin-bottom:1em; }
}

/* ── Share button (card wall) ── */
.share-btn{flex:none;width:20px;height:20px;border-radius:6px;display:flex;align-items:center;justify-content:center;color:var(--brand);border:1px solid transparent;transition:all .15s;background:none;cursor:pointer;padding:0;}
.share-btn:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.share-btn.loading{pointer-events:none;opacity:.5;}
.share-btn svg{width:13px;height:13px;}

/* ── Share action bar (reader body bottom) ── */
.r2-actions-bottom{display:flex;justify-content:center;padding:22px 0 4px;}
.r2-share-btn{display:inline-flex;align-items:center;gap:8px;padding:9px 20px;border-radius:999px;font-size:13px;font-weight:600;border:1px solid var(--brand-line);background:var(--brand-weak);color:var(--brand-strong);cursor:pointer;transition:all .15s;}
.r2-share-btn:hover{background:var(--brand-strong);color:#fff;border-color:var(--brand-strong);}
.r2-share-btn.loading{pointer-events:none;opacity:.6;}
.r2-share-btn svg{width:15px;height:15px;}

/* ── Share modal ── */
.share-modal{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;}
.share-modal.open{display:flex;}
.share-backdrop{position:absolute;inset:0;background:rgba(28,25,23,.55);}
.share-panel{position:relative;z-index:1;width:min(400px,90vw);background:var(--bg);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.25);padding:20px;text-align:center;}
.share-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}
.share-hd h3{font-family:var(--display);font-size:15px;font-weight:900;margin:0;}
.share-close{width:28px;height:28px;border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:16px;color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;}
.share-close:hover{border-color:var(--line-strong);color:var(--ink);}
.share-img-wrap{border-radius:10px;overflow:hidden;border:1px solid var(--line);background:var(--card);}
.share-img-wrap img{width:100%;display:block;}
.share-hint{font-size:12px;color:var(--faint);margin:12px 0 14px;}
.share-actions{display:flex;gap:10px;justify-content:center;}
.btn-share-save,.btn-share-copy{padding:8px 22px;border-radius:8px;font-size:13px;font-weight:600;border:1px solid var(--brand-line);transition:all .15s;cursor:pointer;font-family:var(--body);}
.btn-share-save{background:var(--brand-strong);color:#fff;}
.btn-share-save:hover{opacity:.9;}
.btn-share-copy{background:var(--brand-weak);color:var(--brand-strong);}
.btn-share-copy:hover{background:var(--brand-line);color:#fff;}

/* ── Toast ── */
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(20px);background:var(--ink);color:var(--bg);font-size:13px;padding:8px 20px;border-radius:8px;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:200;white-space:nowrap;}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}

/* ── Source panel export ── */
.sp-export{width:28px;height:28px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;}
.sp-export:hover{border-color:var(--brand-line);color:var(--brand-strong);}
.sp-export svg{width:15px;height:15px;}

/* ── Keyboard help ── */
.kbd-help{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;}
.kbd-help.open{display:flex;}
.kbd-help-backdrop{position:absolute;inset:0;background:rgba(28,25,23,.55);}
.kbd-help-panel{position:relative;z-index:1;width:min(360px,88vw);background:var(--bg);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.25);padding:20px;}
.kbd-help-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;}
.kbd-help-hd h3{font-family:var(--display);font-size:15px;font-weight:900;margin:0;}
.kbd-help-body table{width:100%;border-collapse:collapse;}
.kbd-help-body td{padding:6px 0;font-size:13px;color:var(--muted);vertical-align:middle;}
.kbd-help-body td:first-child{width:120px;}
.kbd-help-body kbd{display:inline-block;min-width:22px;text-align:center;padding:2px 6px;border-radius:5px;border:1px solid var(--line);background:var(--card);font-family:var(--mono);font-size:12px;color:var(--ink);line-height:1.5;}
"""


def _build_header():
    return """
<header>
  <div class="hd">
    <a class="logo" href="index.html">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 11a7 7 0 0 1 14 0"/><path d="M4 11v4a2 2 0 0 0 2 2h1a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H4"/><path d="M18 11v4a2 2 0 0 1-2 2h-1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h3"/></svg>
      <span>StarHub<span class="sub">GitHub 收藏台</span></span>
    </a>
    <nav class="nav-links">
      <a href="index.html">收藏池</a>
      <a href="ai-daily.html">AI 晨报</a>
      <a href="rss-aggregator.html" class="active">RSS 聚合</a>
    </nav>
    <button class="theme-btn" id="btnTheme" title="切换主题">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    </button>
  </div>
</header>
"""


def _build_js(sources_with_items, build_ts_ms=0):
    """Generate core JS for card wall + drawer reader."""
    data_json = json.dumps(sources_with_items, ensure_ascii=False)
    cat_labels_json = json.dumps(CATEGORY_LABELS, ensure_ascii=False)
    return """
<script>
(function(){
  var BUILD_TS = """ + str(int(build_ts_ms)) + """;
  var SOURCES = """ + data_json + """;
  var CAT_LABELS = """ + cat_labels_json + """;

  /* ── Data ── */
  var CAT_ORDER = ['ai','tech','cn_tech','dev','news','podcast','youtube'];
  var ART = [];
  SOURCES.forEach(function(s){
    s.items.forEach(function(it){
      ART.push({t:it.title_zh||it.title, s:it.summary_zh||it.summary||'',
        src:s.name, sk:s.key, c:s.cat, sc:s.color, ti:s.tier||3,
        time:it.time_str, date:it.pub_date, u:it.link||'#', fc:it.fc||''});
    });
  });
  var now=new Date().toISOString();
  ART.forEach(function(a){ if(a.date&&a.date>now) a.date=now; });
  ART.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
  tierInterleave();
  function estRead(a){ return Math.max(1,Math.round((a.s||'').length/90))+' min'; }

  /* ── 分层交织：每 4 篇高频文章穿插 1 篇低频文章 ─ */
  function tierInterleave(){
    var hi=[], lo=[];
    ART.forEach(function(a){ (a.ti<=2 ? hi : lo).push(a); });
    var result=[], i=0, j=0;
    while(i<hi.length || j<lo.length){
      var he=Math.min(4, hi.length-i);
      for(var k=0;k<he;k++) result.push(hi[i++]);
      if(j<lo.length) result.push(lo[j++]);
    }
    ART=result;
  }

  /* ── State ── */
  var visited = {};
  try { visited = JSON.parse(localStorage.getItem('rss_read_v2')||'{}'); } catch(e){}
  var filter = {type:'all', cats:{}, src:null, unreadOnly:false, filterBm:false};
  var curArt = null;
  var wallLimit = 120, WALL_STEP = 80;

  /* ── Theme ── */
  var themeKey='wb_starhub_theme_v1';
  var t=localStorage.getItem(themeKey)||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.dataset.theme=t;
  var btn=document.getElementById('btnTheme');
  if(btn) btn.onclick=function(){
    var nt=document.documentElement.dataset.theme==='dark'?'light':'dark';
    try{localStorage.setItem(themeKey,nt);}catch(e){}
    document.documentElement.dataset.theme=nt;
  };

  /* ── Toolbar ── */
  function renderChips(){
    var counts={}; ART.forEach(function(a){counts[a.c]=(counts[a.c]||0)+1;});
    var h='';
    CAT_ORDER.forEach(function(c){
      if(!counts[c]) return;
      var label=CAT_LABELS[c]||c, on=filter.type==='cat'&&filter.cats[c];
      h+='<button class="chip'+(on?' on':'')+'" data-c="'+c+'">'+label+' <span class="n">'+counts[c]+'</span></button>';
    });
    var bmCnt=Object.keys(_bookmarks).length;
    if(bmCnt>0) h+='<button class="chip bm-chip'+(filter.filterBm?' on':'')+'" id="bmChip" onclick="toggleBmFilter()">\u2605 \u6536\u85cf <span class="n">'+bmCnt+'</span></button>';
    document.getElementById('chips').innerHTML=h;
    document.querySelectorAll('.chip').forEach(function(el){
      el.onclick=function(){
        var c=this.dataset.c, uo=filter.unreadOnly, bm=filter.filterBm;
        var cats=filter.type==='cat'?Object.assign({},filter.cats):{};
        if(cats[c]) delete cats[c]; else cats[c]=true;
        var keys=Object.keys(cats);
        if(keys.length===0) filter={type:'all',cats:{},unreadOnly:uo,filterBm:bm};
        else filter={type:'cat',cats:cats,src:null,unreadOnly:uo,filterBm:bm};
        curArt=null; wallLimit=WALL_STEP; renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
      };
    });
    var pw=document.getElementById('fpillWrap');
    if(filter.type==='src'){
      var s=SRC_OBJ(filter.src);
      pw.innerHTML=s?'<button class="fpill"><span class="src-dot" style="--sc:'+s.color+'"></span>'+esc(s.name)+'<span class="x" onclick="clearSrcF(event)">\u2715</span></button>':'';
    } else pw.innerHTML='';
    document.getElementById('srcCnt').textContent=SOURCES.length;
    var ftN=ART.filter(function(a){return (a.s||'').length>60;}).length;
    document.getElementById('toolMeta').textContent=ART.length+' \u7bc7 \u00b7 \u5168\u6587\u8986\u76d6 '+ftN+'/'+ART.length;
  }
  function updateTitle(){
    var h1=document.querySelector('.toolbar h1');
    if(!h1)return;
    if(filter.type==='cat'){var labels=Object.keys(filter.cats).map(function(c){return CAT_LABELS[c]||c;});h1.textContent=labels.join(' + ');}
    else if(filter.type==='src'){var s=SRC_OBJ(filter.src);h1.textContent=s?s.name:'\u4fe1\u6e90';}
    else h1.textContent='\u65f6\u95f4\u7ebf';
  }
  function updateMeta(){
    var el=document.getElementById('toolMeta');if(!el)return;
    if(globalSearch){
      var list=visibleArts();
      el.textContent='\u547d\u4e2d '+list.length+' \u7bc7';return;
    }
    var ftN=ART.filter(function(a){return(a.s||'').length>60;}).length;
    el.textContent=ART.length+' \u7bc7 \u00b7 \u5168\u6587\u8986\u76d6 '+ftN+'/'+ART.length;
  }
  function SRC_OBJ(k){ return SOURCES.find(function(s){return s.key===k}); }
  window.clearSrcF=function(e){e.stopPropagation();var uo=filter.unreadOnly,bm=filter.filterBm;filter={type:'all',unreadOnly:uo,filterBm:bm};curArt=null;wallLimit=WALL_STEP;renderChips();renderWall();renderPanel();updateTitle();updateHash();updateUnreadBtn();updateBmChip();};

  /* ── Source panel ── */
  function toggleSrcPanel(){ document.body.classList.toggle('src-open'); }
  window.toggleSrcPanel=toggleSrcPanel;
  function selectSrc(key){
    var uo=filter.unreadOnly,bm=filter.filterBm;
    if(!key){filter={type:'all',unreadOnly:uo,filterBm:bm};} else {filter={type:'src',src:key,unreadOnly:uo,filterBm:bm};}
    curArt=null; wallLimit=WALL_STEP; document.body.classList.remove('src-open');
    renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
  }
  window.selectSrc=selectSrc;
  function renderPanel(){
    var q=(document.getElementById('spSearch').value||'').trim().toLowerCase();
    var h='<div class="sp-all'+(filter.type!=='src'?' on':'')+'" onclick="selectSrc(null)">\u2630 \u5168\u90e8\u4fe1\u6e90<span class="n">'+ART.length+'</span></div>';
    var byCat={};
    SOURCES.forEach(function(s){
      if(!q||s.name.toLowerCase().indexOf(q)>=0){
        var cnt=s.items.length;
        if(cnt>0)(byCat[s.cat]=byCat[s.cat]||[]).push(s);
      }
    });
    Object.keys(byCat).forEach(function(c){
      byCat[c].sort(function(a,b){ return b.items.length - a.items.length; });
    });
    var any=false;
    CAT_ORDER.forEach(function(c){
      var arr=byCat[c]; if(!arr||!arr.length) return; any=true;
      var label=CAT_LABELS[c]||c;
      h+='<div class="sp-cat" data-cat="'+c+'"><span class="arrow">\u25bc</span>'+label+'<span class="n">'+arr.length+'</span></div>';
      h+='<div class="sp-cat-body" data-body="'+c+'">';
      arr.forEach(function(s){
        var on=filter.type==='src'&&filter.src===s.key;
        h+='<div class="sp-src'+(on?' on':'')+'" data-k="'+s.key+'"><span class="src-dot" style="--sc:'+s.color+'"></span><span class="nm">'+esc(s.name)+'</span><span class="n">'+s.items.length+'</span></div>';
      });
      h+='</div>';
    });
    if(!any) h+='<div class="sp-none">\u6ca1\u6709\u5339\u914d\u300c'+esc(q)+'\u300d\u7684\u4fe1\u6e90</div>';
    document.getElementById('spList').innerHTML=h;
    document.getElementById('spSearch').oninput=function(){ renderPanel(); };
    document.querySelectorAll('.sp-cat').forEach(function(el){
      el.onclick=function(){
        this.classList.toggle('folded');
        var body=document.querySelector('.sp-cat-body[data-body="'+this.dataset.cat+'"]');
        if(body) body.style.display=this.classList.contains('folded')?'none':'';
      };
    });
    document.querySelectorAll('.sp-src').forEach(function(el){
      el.onclick=function(){ selectSrc(this.dataset.k); };
    });
  }

  /* ── Card wall ── */
  var globalSearch = '';
  function visibleArts(){
    var q = globalSearch;
    return ART.filter(function(a){
      if(filter.type==='cat' && !filter.cats[a.c]) return false;
      if(filter.type==='src' && a.sk!==filter.src) return false;
      if(filter.filterBm && !_bookmarks[artKey(a)]) return false;
      if(filter.unreadOnly && visited[artKey(a)]) return false;
      if(q) { var ql=q.toLowerCase(); return (a.t||'').toLowerCase().indexOf(ql)>=0 || (a.s||'').toLowerCase().indexOf(ql)>=0; }
      return true;
    });
  }
  function toggleUnread(){
    filter.unreadOnly=!filter.unreadOnly;
    wallLimit=WALL_STEP; curArt=null;
    renderWall(); renderPanel(); updateUnreadBtn();
    var em=document.getElementById('wall').querySelector('.empty-hint');
    if(filter.unreadOnly && em) em.textContent='\u6240\u6709\u6587\u7ae0\u5df2\u8bfb';
  }
  function updateUnreadBtn(){
    var b=document.getElementById('unreadToggle');
    if(b) b.classList.toggle('on',filter.unreadOnly);
  }
  var FS_KEY='rss_reader_fontsize', FS_SIZES=['sm','md','lg'];
  function setFontSize(sz){
    var body=document.getElementById('r2Body');
    if(!body) return;
    body.classList.remove('fs-sm','fs-md','fs-lg');
    body.classList.add('fs-'+sz);
    try{localStorage.setItem(FS_KEY,sz);}catch(e){}
    var btns=document.querySelectorAll('.r2-fs-btn');
    for(var i=0;i<btns.length;i++) btns[i].classList.toggle('active',FS_SIZES[i]===sz);
  }
  function initFontSize(){
    var sz='md';
    try{var s=localStorage.getItem(FS_KEY);if(s&&FS_SIZES.indexOf(s)>=0)sz=s;}catch(e){}
    var body=document.getElementById('r2Body');
    if(body) body.classList.add('fs-'+sz);
    var btns=document.querySelectorAll('.r2-fs-btn');
    for(var i=0;i<btns.length;i++) btns[i].classList.toggle('active',FS_SIZES[i]===sz);
  }
  var _bookmarks={}, BM_KEY='rss_bookmarks', BM_MAX=500;
  function loadBookmarks(){try{_bookmarks=JSON.parse(localStorage.getItem(BM_KEY)||'{}');}catch(e){_bookmarks={};}}
  function saveBookmarks(){try{localStorage.setItem(BM_KEY,JSON.stringify(_bookmarks));}catch(e){}}
  function isBookmarked(k){return !!_bookmarks[k];}
  function toggleBookmark(a){
    var k=artKey(a);
    if(_bookmarks[k]){delete _bookmarks[k];}
    else{_bookmarks[k]={t:a.t,u:a.u,src:a.src,sk:a.sk,c:a.c,sc:a.sc,time:a.time};}
    saveBookmarks();
    var cards=document.querySelectorAll('#wall .card');
    for(var i=0;i<cards.length;i++){
      var b=cards[i].querySelector('.bm-btn');
      if(b&&cards[i].dataset.k===k) b.classList.toggle('on',!!_bookmarks[k]);
    }
    updateBmBtn();
    renderChips();
    if(filter.filterBm){wallLimit=WALL_STEP;renderWall();renderPanel();}
  }
  function toggleBmFilter(){
    filter.filterBm=!filter.filterBm;
    wallLimit=WALL_STEP; curArt=null;
    renderWall(); renderPanel(); updateBmChip();
  }
  function updateBmBtn(){
    var b=document.getElementById('r2Bm');
    if(!b||!curArt) return;
    var on=isBookmarked(artKey(curArt));
    b.classList.toggle('on',on);
    var sp=b.querySelector('span');
    if(sp) sp.textContent=on?'\u5df2\u6536\u85cf':'\u6536\u85cf';
  }
  function updateBmChip(){
    var b=document.getElementById('bmChip');
    if(b) b.classList.toggle('on',filter.filterBm);
  }
  function highlightEsc(text,q){
    var e=esc(text);if(!q)return e;
    var re=new RegExp('('+q.replace(/[.*+?^${}()|[\\\\]/g,'\\\\$&')+')','gi');
    return e.replace(re,'<mark>$1</mark>');
  }
  function artKey(a){ return a.sk+'|'+(a.u&&a.u!=='#'?a.u:a.t); }
  function renderWall(){
    var list=visibleArts(), wall=document.getElementById('wall');
    if(!list.length){
      var em=globalSearch?'\u672a\u627e\u5230\u4e0e\u300c'+esc(globalSearch)+'\u300d\u76f8\u5173\u7684\u6587\u7ae0':(filter.filterBm?'\u6682\u65e0\u6536\u85cf\u6587\u7ae0':(filter.unreadOnly?'\u6240\u6709\u6587\u7ae0\u5df2\u8bfb':'\u8be5\u7b5b\u9009\u4e0b\u6ca1\u6709\u6587\u7ae0'));
      wall.innerHTML='<div class="empty-hint">'+em+'</div>';
      wallLimit=0;
      return;
    }
    var end=Math.min(wallLimit, list.length);
    var h='';
    if(globalSearch) h+='<div class="search-banner">\u641c\u7d22 \u00ab'+esc(globalSearch)+'\u00bb \u2014 \u547d\u4e2d '+list.length+' \u7bc7</div>';
    for(var i=0;i<end;i++){
      var a=list[i], k=artKey(a), isVis=!!visited[k];
      var isOpen=curArt&&artKey(curArt)===k;
      h+='<article class="card'+(isVis?' visited':'')+(isOpen?' open':'')+'" data-k="'+esc(k)+'" style="--cc:var(--cat-'+a.c+')">';
      h+='<div class="card-top"><span class="cat-tag" style="color:var(--cat-'+a.c+')">'+(CAT_LABELS[a.c]||a.c)+'</span>';
      h+='<span class="card-time">'+esc(a.time)+'</span>';
      h+='<button class="bm-btn'+(isBookmarked(k)?' on':'')+'" data-k="'+esc(k)+'" title="\u6536\u85cf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></button>';
      h+='<a class="ext-btn" href="'+esc(a.u)+'" target="_blank" rel="noopener" title="\u539f\u7ad9" onclick="event.stopPropagation()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg></a></div>';
      h+='<h3 class="card-title">'+highlightEsc(a.t,globalSearch)+'</h3>';
      if(a.s) h+='<p class="card-summary">'+highlightEsc(a.s,globalSearch)+'</p>';
      h+='<div class="card-foot"><span class="src-dot" style="--sc:'+a.sc+'"></span><span class="src-name">'+esc(a.src)+'</span>';
      h+='<span class="foot-meta"><button class="share-btn" data-k="'+esc(k)+'" title="\u5206\u4eab\u6587\u7ae0"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button><span>'+estRead(a)+'</span></span></div>';
      h+='</article>';
    }
    wall.innerHTML=h;
    wallLimit=end;
  }
  /* 轻量更新：仅更新卡片已读/打开状态的 CSS 类，不重建 DOM */
  function updateCardStates(){
    var cards=document.querySelectorAll('#wall .card');
    for(var i=0;i<cards.length;i++){
      var k=cards[i].dataset.k;
      var isVis=!!visited[k];
      var isOpen=curArt&&artKey(curArt)===k;
      cards[i].classList.toggle('visited',isVis);
      cards[i].classList.toggle('open',isOpen);
    }
  }
  /* 事件委托：一次性绑定，无需重新绑定 */
  document.getElementById('wall').addEventListener('click',function(e){
    var card=e.target.closest('.card'); if(!card)return;
    var k=card.dataset.k;
    var a=ART.find(function(x){return artKey(x)===k;});
    if(!a) return;
    if(e.target.closest('.ext-btn')){markRead(a);updateCardStates();return;}
    if(e.target.closest('.bm-btn')){toggleBookmark(a);return;}
    if(e.target.closest('.share-btn')){shareArticle(a,null,e.target.closest('.share-btn'));return;}
    openReader(a);
  });
  function loadMore(){
    var list=visibleArts();
    if(wallLimit>=list.length)return;
    var old=wallLimit; wallLimit=Math.min(wallLimit+WALL_STEP,list.length);
    renderWall();
  }
  window.loadMore=loadMore;

  /* ── Reader ── */
  var _articleCache={};
  function fetchFullArticle(a){
    if(!a.u||a.u==='#') return;
    var inner=document.getElementById('r2Inner');
    if(!inner) return;
    if(a.fc&&a.fc.length>100){
      _insertFulltext(a.fc);
      return;
    }
    if(_articleCache[a.u]){
      var d=_articleCache[a.u];
      if(d.ok) _insertFulltext(d.content);
      return;
    }
    var old=inner.querySelector('.r2-ft-loading');
    if(old) old.remove();
    var ld=document.createElement('div');
    ld.className='r2-ft-loading';
    ld.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="30 70" stroke-linecap="round"/></svg> \u6b63\u5728\u52a0\u8f7d\u5168\u6587\u2026';
    var hint=inner.querySelector('.r2-foot-hint');
    if(hint) inner.insertBefore(ld,hint); else inner.appendChild(ld);
    var apiBase='https://starhub-refresh.vercel.app/api/article';
    fetch(apiBase+'?url='+encodeURIComponent(a.u)).then(function(r){return r.json();}).then(function(d){
      _articleCache[a.u]=d;
      var cur=inner.querySelector('.r2-ft-loading'); if(cur) cur.remove();
      if(d.ok&&d.content) _insertFulltext(d.content);
    }).catch(function(){
      var cur=inner.querySelector('.r2-ft-loading'); if(cur) cur.remove();
    });
  }
  function _insertFulltext(html){
    var inner=document.getElementById('r2Inner');
    if(!inner||inner.querySelector('.r2-fulltext')) return;
    var div=document.createElement('div');
    div.className='r2-fulltext';
    
    // Auto-format: detect if content lacks paragraph structure
    var hasParagraphs=/<p[\s>]/i.test(html);
    if(!hasParagraphs){
      // Plain text or minimal HTML - split into paragraphs
      var blocks=html.split(/\\n\\s*\\n/);
      var formatted=blocks.map(function(block){
        block=block.trim();
        if(!block) return '';
        // Check if block contains only an image
        if(/^<img\s/i.test(block)&&block.match(/^<img\s[^>]*>$/i)){
          return block;
        }
        // Wrap text blocks in <p> tags
        return '<p>'+block.replace(/\\n/g,'<br>')+'</p>';
      }).filter(function(b){return b;}).join('\\n');
      div.innerHTML=formatted;
    } else {
      // Already has proper HTML structure
      div.innerHTML=html;
    }
    
    var hint=inner.querySelector('.r2-foot-hint');
    if(hint) inner.insertBefore(div,hint); else inner.appendChild(div);
  }
  function markRead(a){visited[artKey(a)]=1;try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}}
  function markAllRead(){
    var list=visibleArtes(),cnt=0;
    for(var i=0;i<list.length;i++){var k=artKey(list[i]);if(!visited[k]){visited[k]=1;cnt++;}}
    try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}
    updateCardStates();
    if(cnt>0) toast('\u5df2\u6807\u8bb0 '+cnt+' \u7bc7\u4e3a\u5df2\u8bfb');
    if(filter.unreadOnly){wallLimit=WALL_STEP;renderWall();}
  }
  function openReader(a){
    curArt=a; markRead(a);
    renderReader(); document.body.classList.add('reading');
    document.body.classList.remove('src-open');
    document.getElementById('r2Body').scrollTop=0; updateCardStates();
  }
  function renderReader(){
    var a=curArt; if(!a) return;
    document.getElementById('r2Src').innerHTML='<span class="src-dot" style="--sc:'+a.sc+'"></span><b>'+esc(a.src)+'</b><span>\u00b7</span><span>'+esc(a.time)+'</span>';
    var openEl=document.getElementById('r2Open'); openEl.href=a.u;
    var h='<h1 class="r2-title">'+esc(a.t)+'</h1>';
    h+='<div class="r2-meta" style="--cc:var(--cat-'+a.c+')"><span class="cat">'+(CAT_LABELS[a.c]||a.c)+'</span>';
    h+='<span class="src-dot" style="--sc:'+a.sc+'"></span><span>'+esc(a.src)+'</span>';
    h+='<span>\u00b7</span><span>'+esc(a.time)+'</span><span>\u00b7</span><span>'+estRead(a)+'</span></div>';
    if(a.s){
      // Auto-format summary into paragraphs
      var formattedSummary = formatSummary(a.s);
      h+='<div class="r2-summary">'+formattedSummary+'</div>';
      if(!isMostlyZh(a.s)){
        h+='<div class="r2-lang-toggle">';
        h+='<button class="active" id="btnOrig">\u539f\u6587</button>';
        h+='<button id="btnTrans">\u7ffb\u8bd1</button></div>';
      }
    } else {
      h+='<div class="fallback-card"><div class="fb-ico">🔗</div>';
      h+='<p>\u8be5\u6587\u7ae0\u6682\u65e0\u6458\u8981<br>\u53ef\u524d\u5f80\u539f\u7ad9\u7ee7\u7eed\u9605\u8bfb</p>';
      h+='<a class="fb-btn" href="'+esc(a.u)+'" target="_blank" rel="noopener">\u539f\u7ad9 \u2197</a></div>';
    }
    h+='<div class="r2-foot-hint">J / K \u6216 \u2190 \u2192 \u5207\u6362\u6587\u7ae0 \u00b7 ESC \u8fd4\u56de</div>';
    h+='<div class="r2-actions-bottom"><button class="r2-share-btn" onclick="r2ShareClick()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg><span>\u5206\u4eab\u672c\u6587</span></button></div>';
    document.getElementById('r2Inner').innerHTML=h;
    var btnT=document.getElementById('btnTrans');
    if(btnT) btnT.onclick=function(){
      var el=document.querySelector('.r2-summary');
      if(!el) return; el.innerHTML='<p>\u7ffb\u8bd1\u4e2d\u2026</p>';
      _clientTranslate(a.s,function(tr){
        var cur=document.querySelector('.r2-summary');
        if(cur) cur.innerHTML=formatSummary(tr);
      });
    };
    updateBmBtn();
    fetchFullArticle(a);
  }

  // Format summary text into readable paragraphs
  function formatSummary(text){
    if(!text) return '';
    // Step 1: Normalize line endings
    var normalized = text.replace(/\\r\\n/g, '\\n').replace(/\\r/g, '\\n');
    
    // Step 2: If no newlines exist, split by sentence-ending punctuation (Chinese + English)
    if(normalized.indexOf('\\n') === -1){
      // Chinese punctuation: always split after 。！？
      normalized = normalized.replace(/([。！？])/g, '$1\\n');
      
      // English punctuation: only split after .!? when followed by space+uppercase or end of string
      // Avoid splitting decimals (129.3), versions (3.7), domains (example.com), abbreviations
      normalized = normalized.replace(/(\\.)(\\s+[A-Z\\u4e00-\\u9fff])/g, '$1\\n$2')  // Period before uppercase/Chinese
        .replace(/([!?])(\\s+)/g, '$1\\n$2');  // !? before space
    }
    
    // Step 3: Split by newlines and wrap each non-empty line in <p>
    var lines = normalized.split('\\n');
    var html = lines.filter(function(line){ return line.trim().length > 0; })
      .map(function(line){ return '<p>' + esc(line.trim()) + '</p>'; })
      .join('');
    return html || '<p>' + esc(text) + '</p>';
  }
  document.getElementById('r2Body').addEventListener('scroll',function(){
    var el=this,max=el.scrollHeight-el.clientHeight;
    document.getElementById('r2Progress').style.width=(max>0?el.scrollTop/max*100:0)+'%';
  });

  /* ── Client translate ── */
  var _ctCache={},_ctPend={};
  function _clientTranslate(text,cb){
    if(!text||isMostlyZh(text)){cb(text);return;}
    var k=text.substring(0,100);
    if(_ctCache[k]){cb(_ctCache[k]);return;}
    if(_ctPend[k]){_ctPend[k].push(cb);return;}
    _ctPend[k]=[cb];
    var url='https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q='+encodeURIComponent(text.substring(0,500));
    fetch(url).then(function(r){return r.json();}).then(function(d){
      var res='';if(d&&d[0])for(var i=0;i<d[0].length;i++)if(d[0][i]&&d[0][i][0])res+=d[0][i][0];
      var tr=(res&&res.length>text.length*0.3)?res:text;
      _ctCache[k]=tr;var p=_ctPend[k]||[];delete _ctPend[k];p.forEach(function(f){f(tr);});
    }).catch(function(){
      _ctCache[k]=text;var p=_ctPend[k]||[];delete _ctPend[k];p.forEach(function(f){f(text);});
    });
  }

  // ── OPML export ──
  function exportOPML(){
    var groups={};
    SOURCES.forEach(function(s){
      var cat=s.cat||'other';
      if(!groups[cat]) groups[cat]=[];
      groups[cat].push(s);
    });
    var xml='<?xml version="1.0" encoding="UTF-8"?>\\n';
    xml+='<opml version="2.0">\\n<head><title>StarHub RSS \\u4fe1\\u6e90</title><dateCreated>'+new Date().toUTCString()+'</dateCreated></head>\\n<body>\\n';
    CAT_ORDER.forEach(function(c){
      if(!groups[c]||!groups[c].length) return;
      var label=CAT_LABELS[c]||c;
      xml+='  <outline text="'+esc(label)+'" title="'+esc(label)+'">\\n';
      groups[c].forEach(function(s){
        xml+='    <outline type="rss" text="'+esc(s.name)+'" title="'+esc(s.name)+'" xmlUrl="'+esc(s.url)+'"/>\\n';
      });
      xml+='  </outline>\\n';
    });
    xml+='</body>\\n</opml>';
    var blob=new Blob([xml],{type:'text/xml;charset=utf-8'});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='starhub-rss-sources.opml';
    a.click();
    URL.revokeObjectURL(a.href);
    toast('\u5df2\u5bfc\u51fa '+SOURCES.length+' \u4e2a\u4fe1\u6e90');
  }

  // ── Keyboard help ──
  function toggleKbdHelp(){
    var m=document.getElementById('kbdHelp');
    if(!m){m=document.createElement('div');m.id='kbdHelp';m.className='kbd-help';
    m.innerHTML='<div class="kbd-help-backdrop" onclick="toggleKbdHelp()"></div><div class="kbd-help-panel"><div class="kbd-help-hd"><h3>\u5feb\u6377\u952e</h3><button class="share-close" onclick="toggleKbdHelp()">\u00d7</button></div><div class="kbd-help-body"><table><tr><td><kbd>j</kbd> / <kbd>\u2192</kbd></td><td>\u4e0b\u4e00\u7bc7\u6587\u7ae0</td></tr><tr><td><kbd>k</kbd> / <kbd>\u2190</kbd></td><td>\u4e0a\u4e00\u7bc7\u6587\u7ae0</td></tr><tr><td><kbd>Esc</kbd></td><td>\u5173\u95ed\u9605\u8bfb\u5668/\u9762\u677f</td></tr><tr><td><kbd>?</kbd></td><td>\u663e\u793a\u5feb\u6377\u952e\u5e2e\u52a9</td></tr></table></div></div></div>';
    document.body.appendChild(m);}
    m.classList.toggle('open');
  }

  // ── Window exports ──
  window.ART = ART;
  window.closeReader = function(){ document.body.classList.remove('reading'); curArt=null; updateCardStates(); };
  window.closeOverlays = function(){ document.body.classList.remove('src-open'); window.closeReader(); };
  window.clearSrcF = function(e){ e.stopPropagation(); var uo=filter.unreadOnly,bm=filter.filterBm; filter={type:'all',unreadOnly:uo,filterBm:bm}; curArt=null; wallLimit=WALL_STEP; renderChips(); renderWall(); renderPanel(); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip(); };
  window.toggleSrcPanel = toggleSrcPanel;
  window.selectSrc = selectSrc;
  window.toggleUnread = toggleUnread;
  window.setFontSize = setFontSize;
  window.toggleBookmark = toggleBookmark;
  window.toggleBmFilter = toggleBmFilter;
  window.markAllRead = markAllRead;
  window.exportOPML = exportOPML;
  window.toggleKbdHelp = toggleKbdHelp;

  /* ── Global search ── */
  var gsInput = document.getElementById('globalSearch');
  var gsWrap = document.getElementById('globalSearchWrap');
  var gsClear = document.getElementById('globalSearchClear');
  if(gsInput) {
    gsInput.addEventListener('input', function(){
      globalSearch = this.value.trim();
      gsWrap.classList.toggle('has-q', globalSearch.length > 0);
      curArt = null; wallLimit = WALL_STEP;
      renderWall(); updateMeta();
    });
  }
  if(gsClear) {
    gsClear.addEventListener('click', function(){
      gsInput.value = ''; globalSearch = '';
      gsWrap.classList.remove('has-q');
      curArt = null; wallLimit = WALL_STEP;
      renderWall(); updateMeta(); gsInput.focus();
    });
  }

  /* ── Keyboard nav ── */
  document.addEventListener('keydown', function(e){
    if(e.key==='Escape'){
      var kh=document.getElementById('kbdHelp');
      if(kh&&kh.classList.contains('open')){toggleKbdHelp();return;}
      var sm=document.getElementById('shareModal');
      if(sm&&sm.classList.contains('open')){closeShareModal();return;}
      window.closeOverlays();return;
    }
    if(e.target.tagName==='INPUT') return;
    if(e.key==='?'){toggleKbdHelp();return;}
    var order=visibleArts();
    if(!curArt){if(e.key==='j'||e.key==='ArrowRight'){if(order[0])openReader(order[0]);}return;}
    var pos=-1;
    for(var i=0;i<order.length;i++){if(artKey(order[i])===artKey(curArt)){pos=i;break;}}
    if(e.key==='j'||e.key==='ArrowRight'){if(pos<order.length-1)openReader(order[pos+1]);}
    if(e.key==='k'||e.key==='ArrowLeft'){if(pos>0)openReader(order[pos-1]);}
  });

  /* ── Helpers ── */
  function esc(s){var d=document.createElement('div');d.appendChild(document.createTextNode(s||''));return d.innerHTML;}
  function adjColor(hex){
    if(document.documentElement.dataset.theme!=='dark')return hex;
    var m=/^#?([0-9a-fA-F]{6})$/.exec(hex||'');if(!m)return hex;
    var n=parseInt(m[1],16),r=(n>>16)&255,g=(n>>8)&255,b=n&255;
    var lum=(0.299*r+0.587*g+0.114*b)/255;
    if(lum>=0.35)return hex;
    r=Math.round(r+(255-r)*0.45);g=Math.round(g+(255-g)*0.45);b=Math.round(b+(255-b)*0.45);
    return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);
  }
  function isMostlyZh(s){
    if(!s)return true;var c=0,n=0;
    for(var i=0;i<s.length;i++){var ch=s.charCodeAt(i);if(ch>=0x4e00&&ch<=0x9fff)c++;if(ch>32)n++;}
    return n===0||c/n>0.2;
  }

  /* ── URL hash ── */
  function updateHash(){
    var p='#view='+(filter.type==='cat'?'cat&c='+Object.keys(filter.cats).join(','):filter.type==='src'?'src&s='+encodeURIComponent(filter.src):'all');
    try{history.replaceState(null,'',p);}catch(e){}
  }
  function restoreFromHash(){
    var h=(location.hash||'').replace(/^#/,'');if(!h)return false;
    var p={};h.split('&').forEach(function(kv){var s=kv.split('=');if(s[0])p[s[0]]=decodeURIComponent(s[1]||'');});
    if(p.view==='cat'&&p.c){var cats={};p.c.split(',').forEach(function(x){if(x)cats[x]=true;});filter={type:'cat',cats:cats};return true;}
    if(p.view==='src'&&p.s){filter={type:'src',src:p.s};return true;}
    return false;
  }

  /* ── Init ── */
  var restored = restoreFromHash();
  renderChips(); renderWall(); renderPanel(); updateTitle(); updateHash(); updateUnreadBtn(); initFontSize(); loadBookmarks(); renderChips(); updateBmBtn();
  /* 无限滚动：接近底部自动加载更多 */
  window.addEventListener('scroll',function(){
    var list=visibleArts();
    if(wallLimit>=list.length)return;
    var wrap=document.querySelector('.wall-wrap');
    if(!wrap)return;
    if(wrap.getBoundingClientRect().bottom<window.innerHeight*3){
      loadMore();
    }
  },{passive:true});
  /* 返回顶部按钮 */
  window.addEventListener('scroll',function(){
    var bt=document.getElementById('backTop');
    if(bt) bt.classList.toggle('show',window.scrollY>window.innerHeight*3);
  },{passive:true});
  var relEl = document.getElementById('buildRel');
  if(relEl && BUILD_TS){
    var mins=Math.max(0,Math.round((Date.now()-BUILD_TS)/60000));
    relEl.textContent=(mins<60?mins+' \u5206\u949f\u524d':mins<1440?Math.round(mins/60)+' \u5c0f\u65f6\u524d':Math.round(mins/1440)+' \u5929\u524d');
  }

  /* ── Relative time formatter ── */
  function _fmtRelTime(dt) {
    if (!dt) return '';
    var d = new Date(dt);
    if (isNaN(d.getTime())) return dt;
    var mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
    return mins < 60 ? mins + ' 分钟前' : mins < 1440 ? Math.round(mins/60) + ' 小时前' : Math.round(mins/1440) + ' 天前';
  }

  /* ── Load RSS snapshot (from same origin, no Vercel dependency) ── */
  var liveEl = document.getElementById('liveStatus');
  if(liveEl) liveEl.textContent='\u00b7 \u52a0\u8f7d\u4e2d\u2026';
  (function(){
    var ctrl=new AbortController();
    var tid=setTimeout(function(){ctrl.abort();},15000);
    fetch('rss_api_snapshot.json',{signal:ctrl.signal}).then(function(r){
      clearTimeout(tid);if(!r.ok)throw new Error('Snapshot '+r.status);return r.json();
    }).then(function(data){
      if(!data.sources)return;
      data.sources.forEach(function(live){
        if(!live.items||!live.items.length)return;
        var src=SOURCES.find(function(s){return s.key===live.key;});
        if(src){
          live.items.forEach(function(it){
            it.title = it.t || it.title;
            it.link = it.u || it.link;
            it.summary = it.s || it.summary;
            it.pub_date = it.d || it.pub_date;
            it.title_zh = it.title;
            it.summary_zh = it.summary || '';
            it.time_str = _fmtRelTime(it.pub_date);
          });
          src.items = live.items;
        }
      });
      ART=[];
      SOURCES.forEach(function(s){s.items.forEach(function(it){
        ART.push({t:it.title_zh||it.title,s:it.summary_zh||it.summary||'',
          src:s.name,sk:s.key,c:s.cat,sc:s.color,
          time:it.time_str,date:it.pub_date,u:it.link||'#',fc:it.fc||''});
      });});
      ART.sort(function(a,b){return(b.date||'').localeCompare(a.date||'');});
      interleaveArts();
      wallLimit=WALL_STEP;renderChips();renderWall();renderPanel();
      if(liveEl){var now=new Date();liveEl.textContent='\u2713 '+now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');}
    }).catch(function(e){
      if(liveEl)liveEl.textContent='';
    });
  })();

  /* ── Refresh: 数据由 GitHub Actions 定时构建生成，点击按钮重新加载页面 ── */
  window.refreshRss = function(){ location.reload(); };

  /* ══════════════════════════════════════════
     Share module: Canvas card + QR code + modal
     ══════════════════════════════════════════ */
  var _qrLoaded=false, _shareDataURL='', _toastTimer;
  function toast(msg){var t=document.getElementById('toast');if(!t)return;t.textContent=msg;t.classList.add('show');clearTimeout(_toastTimer);_toastTimer=setTimeout(function(){t.classList.remove('show');},2000);}

  function loadQRLib(){
    if(_qrLoaded) return Promise.resolve();
    return new Promise(function(resolve,reject){
      var s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js';
      s.onload=function(){_qrLoaded=true;resolve();};
      s.onerror=function(){
        var s2=document.createElement('script');
        s2.src='https://unpkg.com/qrcode-generator@1.4.4/qrcode.min.js';
        s2.onload=function(){_qrLoaded=true;resolve();};
        s2.onerror=reject;
        document.head.appendChild(s2);
      };
      document.head.appendChild(s);
    });
  }

  function wrapText(ctx,text,maxWidth){
    var lines=[],line='';
    for(var i=0;i<text.length;i++){
      var test=line+text[i];
      if(ctx.measureText(test).width>maxWidth&&line){lines.push(line);line=text[i];}
      else{line=test;}
    }
    if(line) lines.push(line);
    return lines;
  }

  function getThemeColors(){
    var dark=document.documentElement.dataset.theme==='dark';
    return {
      bg:      dark?'#161412':'#faf9f7',
      title:   dark?'#ece7df':'#1c1917',
      summary: dark?'#a59d90':'#5f594c',
      line:    dark?'#37312a':'#ddd6c9',
      qrFg:    dark?'#ece7df':'#1c1917',
      qrBg:    dark?'#1d1a17':'#fffdf9',
      brand:   dark?'#98907f':'#857e74'
    };
  }

  function drawShareCard(a){
    var W=750, PAD=40, GAP_T=28, GAP_S=16, GAP_M=24;
    var c=document.createElement('canvas');
    var ctx=c.getContext('2d');
    var col=getThemeColors();
    var font=getComputedStyle(document.body).fontFamily;
    var catColor=a.sc||'#2f5d8a';
    if(document.documentElement.dataset.theme==='dark') catColor=adjColor(a.sc||'#8fb3d9');

    // ── Measure pass ──
    ctx.font='26px '+font;
    var titleLines=wrapText(ctx, a.t||'\u65e0\u6807\u9898\u6587\u7ae0', W-PAD*2);
    var summaryLines=[];
    if(a.s){
      ctx.font='15px '+font;
      summaryLines=wrapText(ctx, a.s, W-PAD*2);
    }
    var titleH=titleLines.length*(26*1.45);
    var summaryH=summaryLines.length*(15*1.7);
    var H=PAD+50+GAP_T+titleH+GAP_S+summaryH+(a.s?GAP_M:0)+1+GAP_M+110+36;

    // ── Create canvas at 2x ──
    c.width=W*2; c.height=H*2;
    ctx.scale(2,2);

    // ── Background with rounded corners ──
    var R=16;
    ctx.beginPath();
    ctx.moveTo(R,0);ctx.lineTo(W-R,0);ctx.quadraticCurveTo(W,0,W,R);
    ctx.lineTo(W,H-R);ctx.quadraticCurveTo(W,H,W-R,H);
    ctx.lineTo(R,H);ctx.quadraticCurveTo(0,H,0,H-R);
    ctx.lineTo(0,R);ctx.quadraticCurveTo(0,0,R,0);
    ctx.closePath();ctx.fillStyle=col.bg;ctx.fill();

    var y=PAD;
    // ── Top bar ──
    ctx.fillStyle=catColor;
    ctx.beginPath();ctx.arc(PAD+3.5,y+6,3.5,0,Math.PI*2);ctx.fill();
    ctx.font='bold 12px '+font;
    ctx.fillStyle=catColor;
    ctx.fillText((CAT_LABELS[a.c]||a.c).toUpperCase(),PAD+14,y+10);
    ctx.font='12px '+font;
    ctx.fillStyle=col.brand;
    ctx.textAlign='right';
    ctx.fillText('StarHub RSS \u805a\u5408',W-PAD,y+10);
    ctx.textAlign='left';
    y+=50+GAP_T;

    // ── Title (never truncated) ──
    ctx.font='bold 26px '+font;
    ctx.fillStyle=col.title;
    for(var i=0;i<titleLines.length;i++){
      ctx.fillText(titleLines[i],PAD,y);
      y+=26*1.45;
    }
    y+=GAP_S;

    // ── Summary (never truncated) ──
    if(a.s&&summaryLines.length){
      ctx.font='15px '+font;
      ctx.fillStyle=col.summary;
      for(var i=0;i<summaryLines.length;i++){
        ctx.fillText(summaryLines[i],PAD,y);
        y+=15*1.7;
      }
      y+=GAP_M;
    }

    // ── Separator ──
    ctx.strokeStyle=col.line;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PAD,y);ctx.lineTo(W-PAD,y);ctx.stroke();
    y+=GAP_M;

    // ── Bottom: source + QR ──
    ctx.fillStyle=a.sc||'#2f5d8a';
    ctx.beginPath();ctx.arc(PAD+4,y+6,4,0,Math.PI*2);ctx.fill();
    ctx.font='bold 12px '+font;
    ctx.fillStyle=col.title;
    var srcTxt=a.src||'';
    ctx.fillText(srcTxt,PAD+16,y+10);
    ctx.font='12px '+font;
    ctx.fillStyle=col.summary;
    ctx.fillText('\u00b7 '+(a.time||''),PAD+16+ctx.measureText(srcTxt).width+6,y+10);

    ctx.font='11px '+font;
    ctx.fillStyle=col.brand;
    ctx.fillText('\u957f\u6309\u8bc6\u522b \u00b7 \u9605\u8bfb\u539f\u6587',PAD,y+40);

    var qrSize=90, qrX=W-PAD-qrSize, qrY=y;
    if(_qrLoaded){
      try{
        var qrUrl=(a.u&&a.u!=='#')?a.u:location.href;
        var qr=qrcode(0,'M');
        qr.addData(qrUrl);qr.make();
        var cnt=qr.getModuleCount();
        var cell=qrSize/cnt;
        ctx.fillStyle=col.qrBg;
        ctx.fillRect(qrX-4,qrY-4,qrSize+8,qrSize+8);
        ctx.fillStyle=col.qrFg;
        for(var r=0;r<cnt;r++)for(var c2=0;c2<cnt;c2++){
          if(qr.isDark(r,c2)) ctx.fillRect(qrX+c2*cell,qrY+r*cell,Math.ceil(cell),Math.ceil(cell));
        }
      }catch(e){
        ctx.fillStyle=col.summary;ctx.font='11px '+font;
        ctx.textAlign='center';ctx.fillText('\u4e8c\u7ef4\u7801\u6682\u4e0d\u53ef\u7528',qrX+qrSize/2,qrY+qrSize/2);
        ctx.textAlign='left';
      }
    } else {
      ctx.fillStyle=col.summary;ctx.font='11px '+font;
      ctx.textAlign='center';ctx.fillText('\u4e8c\u7ef4\u7801\u6682\u4e0d\u53ef\u7528',qrX+qrSize/2,qrY+qrSize/2);
      ctx.textAlign='left';
    }

    return c.toDataURL('image/png');
  }

  function shareArticle(a,platform,btn){
    if(!a) return;
    if(btn) btn.classList.add('loading');
    loadQRLib().catch(function(){/* QR load failed, continue without */}).then(function(){
      var url;
      try{url=drawShareCard(a);}catch(e){url='';}
      if(btn) btn.classList.remove('loading');
      if(!url){toast('\u5206\u4eab\u56fe\u7247\u751f\u6210\u5931\u8d25');return;}
      _shareDataURL=url;
      showShareModal(url);
    });
  }

  function showShareModal(url){
    var m=document.getElementById('shareModal');
    document.getElementById('shareImg').src=url;
    m.classList.add('open');
    var closeBtn=m.querySelector('.share-close');
    if(closeBtn) closeBtn.focus();
  }

  function closeShareModal(){
    document.getElementById('shareModal').classList.remove('open');
  }

  function saveShareImage(){
    if(!_shareDataURL) return;
    var a=document.createElement('a');
    a.href=_shareDataURL;a.download='starhub-share.png';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
    toast('\u56fe\u7247\u5df2\u4e0b\u8f7d');
  }

  function copyShareImage(){
    if(!_shareDataURL) return;
    fetch(_shareDataURL).then(function(r){return r.blob();}).then(function(blob){
      if(navigator.clipboard&&window.ClipboardItem){
        navigator.clipboard.write([new ClipboardItem({'image/png':blob})]).then(function(){
          toast('\u56fe\u7247\u5df2\u590d\u5236\u5230\u526a\u8d34\u677f');
        }).catch(function(){toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u957f\u6309\u56fe\u7247\u624b\u52a8\u4fdd\u5b58');});
      } else {toast('\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u590d\u5236\u56fe\u7247');}
    }).catch(function(){toast('\u590d\u5236\u5931\u8d25');});
  }

  window.shareArticle=shareArticle;
  window.r2ShareClick=function(){ shareArticle(curArt,null,document.querySelector('.r2-share-btn')); };
  window.closeShareModal=closeShareModal;
  window.saveShareImage=saveShareImage;
  window.copyShareImage=copyShareImage;
  window.toast=toast;

})();
</script>
"""


def build_html(sources_with_items, build_time, total_items, build_ts_ms=0):
    """生成完整 HTML 页面 — 卡片墙 + 抽屉阅读器。"""
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700;900&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
        '<title>RSS 聚合阅读器 · StarHub</title>\n'
        '<style>' + _build_css() + '</style>\n'
        '</head>\n<body>\n'
        + _build_header() +
        '<div class="toolbar">\n'
        '<h1>时间线</h1>\n'
        '<button class="src-btn" onclick="toggleSrcPanel()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h13M4 18h9"/></svg> 信源 <span class="cnt" id="srcCnt"></span></button>\n'
        '<div class="chips" id="chips"></div>\n'
        '<button class="refresh-btn" id="refreshBtn" onclick="refreshRss()" title="重新加载页面以获取最新构建数据"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></button>\n'
        '<button class="unread-toggle" id="unreadToggle" onclick="toggleUnread()" title="\u4ec5\u663e\u793a\u672a\u8bfb"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg> \u672a\u8bfb</button>\n'
        '<button class="mark-all-btn" onclick="markAllRead()" title="\u6807\u8bb0\u5168\u90e8\u5df2\u8bfb"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></button>\n'
        '<span class="global-search" id="globalSearchWrap"><input id="globalSearch" placeholder="\u641c\u7d22\u6587\u7ae0\u2026" autocomplete="off"><span class="sx" id="globalSearchClear">\u2715</span></span>\n'
        '<span id="fpillWrap"></span>\n'
        '<span class="tool-meta" id="toolMeta"></span>\n'
        '</div>\n'
        '<div class="build-bar">\u81ea\u52a8\u751f\u6210\u4e8e ' + _esc(build_time) + '\uff08\u5317\u4eac\u65f6\u95f4\uff09\u00b7 \u5171 ' + str(total_items) + ' \u7bc7 \u00b7 <span id="buildRel"></span><span id="liveStatus"></span></div>\n'
        '<div class="wall-wrap"><div class="wall" id="wall" role="feed" aria-label="\u6587\u7ae0\u5217\u8868"></div></div>\n'
        '<div class="scrim" aria-hidden="true" onclick="closeOverlays()"></div>\n'
        '<aside class="src-panel" id="srcPanel" role="dialog" aria-modal="true" aria-label="\u4fe1\u6e90\u9762\u677f">\n'
        '<div class="sp-head"><div class="row"><h2>信源</h2>\n'
        '<button class="sp-export" onclick="exportOPML()" title="\u5bfc\u51fa OPML"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></button>\n'
        '<button class="sp-close" onclick="toggleSrcPanel()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>\n'
        '</div><label class="sp-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>\n'
        '<input id="spSearch" placeholder="搜索信源…" autocomplete="off"></label></div>\n'
        '<div class="sp-list" id="spList"></div></aside>\n'
        '<aside class="reader2" id="reader2" role="dialog" aria-modal="true" aria-label="\u6587\u7ae0\u9605\u8bfb\u5668">\n'
        '<div class="r2-top"><button class="r2-back" onclick="closeReader()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 12H5M11 18l-6-6 6-6"/></svg><span>返回</span></button>\n'
        '<span class="r2-src" id="r2Src"></span>\n'
        '<div class="r2-acts"><div class="r2-fs-btns"><button class="r2-fs-btn" onclick="setFontSize(\'sm\')" title="\u5c0f\u5b57\u53f7">A-</button><button class="r2-fs-btn" onclick="setFontSize(\'md\')" title="\u9ed8\u8ba4\u5b57\u53f7">A</button><button class="r2-fs-btn" onclick="setFontSize(\'lg\')" title="\u5927\u5b57\u53f7">A+</button></div><button class="r2-bm" id="r2Bm" onclick="if(curArt)toggleBookmark(curArt)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><span>\u6536\u85cf</span></button><a class="r2-open" id="r2Open" href="#" target="_blank" rel="noopener">\u539f\u7ad9 \u2197</a></div>\n'
        '<div class="r2-progress" id="r2Progress"></div></div>\n'
        '<div class="r2-body" id="r2Body"><div class="r2-inner" id="r2Inner"></div></div></aside>\n'
        '<div class="toast" id="toast"></div>\n'
        '<button class="back-top" id="backTop" onclick="window.scrollTo({top:0,behavior:\'smooth\'})" aria-label="\u8fd4\u56de\u9876\u90e8"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg></button>\n'
        '<div class="share-modal" id="shareModal" role="dialog" aria-modal="true" aria-label="分享文章">\n'
        '<div class="share-backdrop" onclick="closeShareModal()"></div>\n'
        '<div class="share-panel">\n'
        '<div class="share-hd"><h3>分享图片已生成</h3><button class="share-close" onclick="closeShareModal()" aria-label="关闭">×</button></div>\n'
        '<div class="share-img-wrap"><img id="shareImg" alt="分享图片"/></div>\n'
        '<p class="share-hint">长按图片保存，发送至微信好友或朋友圈</p>\n'
        '<div class="share-actions">\n'
        '<button class="btn-share-save" id="btnShareSave" onclick="saveShareImage()">保存图片</button>\n'
        '<button class="btn-share-copy" id="btnShareCopy" onclick="copyShareImage()">复制图片</button>\n'
        '</div>\n'
        '</div>\n'
        '</div>\n'
        + _build_js(sources_with_items, build_ts_ms) +
        '</body>\n</html>'
    )


# ──────────────────────────── Main ────────────────────────────

def main(mode="full"):
    now = _now_bj()
    build_time = now.strftime("%Y-%m-%d %H:%M")
    # 构建时间 UTC 毫秒时间戳（供页脚相对时间）
    build_ts_ms = now.timestamp() * 1000

    # 加载缓存
    _load_caches()
    _load_history()

    # 增量模式：加载各源上次抓取时间
    last_fetch = {}
    if mode == "incremental":
        last_fetch = _load_snapshot_meta()
        print("[增量模式] 已加载 %d 个源的上次抓取记录" % len(last_fetch))

    sources_with_items = []
    total_items = 0
    ok_count = 0
    skipped_count = 0

    # 串行抓取 RSS（短超时，失败快速跳过）
    for src in RSS_SOURCES:
        key = src["key"]
        tier = src.get("tier", 3)

        # 增量模式跳过规则：
        # 1. T1 源始终跳过（由 api/rss.js 实时抓取）
        # 2. 距上次抓取 < 4h 的源跳过
        if mode == "incremental":
            if tier == 1:
                skipped_count += 1
                # 用历史数据填充 T1 源（避免快照中丢失）
                sources_with_items.append({
                    "key": key, "name": src["name"], "cat": src["cat"],
                    "color": src["color"], "items": [],
                    "tier": tier,
                })
                continue
            prev = last_fetch.get(key)
            if prev:
                try:
                    prev_time = datetime.datetime.fromisoformat(prev)
                    if (now - prev_time).total_seconds() < 4 * 3600:
                        skipped_count += 1
                        sources_with_items.append({
                            "key": key, "name": src["name"], "cat": src["cat"],
                            "color": src["color"], "items": [],
                            "tier": tier,
                        })
                        continue
                except (ValueError, TypeError):
                    pass

        items = _fetch_rss(src)
        n = len(items)
        if n > 0:
            ok_count += 1
            last_fetch[key] = now.isoformat()

        # 翻译标题和摘要
        for it in items:
            it["title_zh"] = _translate_to_zh(it["title"]) if it["title"] else it["title"]
            it["summary_zh"] = _translate_to_zh(it.get("summary", "")) if it.get("summary") else ""
            it["time_str"] = _fmt_rel_time(it.get("pub_date"))
            # 保留 pub_date 用于前端时间线排序（转为 ISO 字符串）
            pd = it.get("pub_date")
            if pd and hasattr(pd, 'isoformat'):
                it["pub_date"] = pd.isoformat()

        src_data = {
            "key": src["key"], "name": src["name"], "cat": src["cat"],
            "color": src["color"], "items": items,
            "tier": tier,
        }
        sources_with_items.append(src_data)
        total_items += n
        print("[RSS聚合] %s: %d 条" % (src["name"], n))

    if mode == "incremental":
        print("[增量模式] 跳过 %d 个源，抓取 %d 个源" % (skipped_count, len(RSS_SOURCES) - skipped_count))

    if total_items == 0 and mode == "full":
        print("[RSS聚合] 所有源均失败，尝试使用历史数据", file=sys.stderr)

    # 累积到 72 小时历史，用累积数据替换当次抓取
    sources_with_items, total_items = _accumulate_history(sources_with_items)

    # 生成 API 快照（供 /api/rss 直接返回，避免实时抓取丢失历史累积数据）
    meta = {"last_fetch": last_fetch}
    _save_api_snapshot(sources_with_items, meta=meta)

    html_doc = build_html(sources_with_items, build_time, total_items, build_ts_ms)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)

    # 生成 rss_sources.json（供 /api/rss 使用）
    sources_json = json.dumps([{"key": s["key"], "name": s["name"], "cat": s["cat"],
        "color": s["color"], "url": s["url"], "tier": s.get("tier", 3)} for s in RSS_SOURCES], ensure_ascii=False)
    with open("rss_sources.json", "w", encoding="utf-8") as f:
        f.write(sources_json)

    print("[RSS聚合] 生成完成 → %s（%d 源成功，共 %d 篇）" % (OUT, ok_count, total_items))

    # 打印翻译统计
    print("[翻译统计] 缓存命中: %d, Google: %d, MyMemory: %d, Dict: %d, 跳过: %d, 失败: %d" % (
        _TRANS_STATS["cache_hit"], _TRANS_STATS["google"], _TRANS_STATS["mymemory"],
        _TRANS_STATS["dict"], _TRANS_STATS["skip"], _TRANS_STATS["fail"]
    ))

    # 保存缓存
    _save_caches()
    _save_history()

    return True


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    ok = main(mode=mode)
    sys.exit(0 if ok else 1)
