# -*- coding: utf-8 -*-
"""Generate rss-aggregator.html — 多路 RSS 新闻源聚合阅读器。
构建时由 fetch_and_build.py 调用，Python 标准库抓取 RSS → 翻译 → 生成静态 HTML。

布局：卡片墙 + 抽屉阅读器（信源面板 | 卡片墙 | 阅读抽屉）
功能：信源分类筛选、全局搜索、标题/摘要翻译、响应式三端适配、主题切换。
"""
import collections
import functools
import concurrent.futures
import html as html_mod
import datetime
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import uuid
import build_logger
import urllib.error
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

# ── newsnow 热榜快照 ──
# API 格式: /api/s?id={platform}，每平台单独请求
NEWSNOW_API_TMPL = "https://newsnow.busiyi.world/api/s?id=%s"
NEWSNOW_TIMEOUT = 10
HOT_SNAPSHOT_FILE = "hot_snapshot.json"
HOT_HISTORY_FILE = "hot_history.json"  # 热榜轨迹历史（保留 7 天）
# 期望的热榜源（全量接入 newsnow 可用源，故障源 zhihu-daily/36kr/linuxdo/ghxi/kuaishou/smzdm/freebuf 不纳入）
NEWSNOW_PLATFORMS = [
    # ── 综合热搜 ──
    "weibo", "zhihu", "baidu", "bilibili", "douyin",
    # ── 科技/开发者/AI ──
    "ithome", "hackernews", "github", "solidot", "sspai",
    "juejin", "v2ex", "producthunt", "aihot",
    "chongbuluo", "pcbeta", "nowcoder", "coolapk",
    # ── 商业/财经 ──
    "xueqiu", "zaobao", "wallstreetcn", "cls", "jin10",
    "gelonghui", "fastbull",
    # ── 综合资讯 ──
    "toutiao", "tencent", "thepaper", "ifeng",
    "cankaoxiaoxi", "sputniknewscn", "kaopu", "mktnews",
    # ── 生活/娱乐/体育 ──
    "douban", "tieba", "hupu", "steam",
    "iqiyi", "qqvideo", "dongqiudi",
]

# ── 缓存数据 ──
_trans_cache = {}  # {text_hash: translated_text}
_rss_cache = {}    # {source_key: {"items": [...], "fetched_at": timestamp}}

# ── 智能分析配置 ──
ANALYSIS_SNAPSHOT_FILE = "analysis_snapshot.json"
SOURCE_QUALITY_FILE = "source_quality.json"
RSS_TREND_HISTORY_FILE = "rss_trend_history.json"  # RSS 内容趋势历史（保留 14 天）
TRENDING_SNAPSHOT_FILE = "trending_snapshot.json"  # GitHub Trending 数据
INSIGHT_TRACKING_FILE = "insight_tracking_history.jsonl"  # 洞察板块全量追踪日志
# 中英文停用词表（关键词提取时过滤）
_STOP_WORDS_ZH = set("的了是在我有和就不人都一个上也这到说们为你会对" +
    "他就是那要被她它自己什么没有可以已经还是或者虽然但是因此如果" +
    "而且并且或者以及不过然后所以因为于在与及等和而关于中从把被让给" +
    "向由按照根据为了因作为以更最非常再又还已经正在才刚各每全部" +
    "表示指出认为透露宣布发布推出上线下线升级更新修复" +  # 新闻动词（过于通用）
    "据悉据报道消息称知情人士透露" +  # 新闻套话
    "相关有关涉及方面部门机构组织" +  # 泛化名词
    "进行开展实施推进落实加强深化" +  # 公文动词
    "重要重大显著明显突出关键核心" +  # 泛化形容词
    "发展建设改革完善优化提升推动促进")  # 泛化动词
_STOP_WORDS_EN = set(("the a an is are was were be been being have has had do does did will would shall should may might can could " +
    "i me my we our you your he him his she her it its they them their " +
    "this that these those there here what which who whom whose when where why how " +
    "and or but not no nor so yet for to of in on at by with from as into about through during before after above below between under " +
    "again further then once also just than very too only same other some such all each every both few more most " +
    "new old first last long great little own right big high small next early young important public bad able " +
    # URL / HTML 残留噪声
    "https http ftp com org net edu gov io co www " +
    "id item html htm url href src png jpg gif css js xml json nbsp div span class " +
    "amp lt gt quot mdash ndash laquo raquo " +
    "aihot ycombinator").split())
_STOP_WORDS = _STOP_WORDS_ZH | _STOP_WORDS_EN

# ── 分析功能开关（从 build_config.json 读取） ──
# 配置路径按本文件位置解析，不用相对路径：相对路径依赖进程 CWD，
# 从别的目录导入本模块时会静默读到另一个同名 build_config.json
# （实测在诱饵 CWD 下读到 {enabled: False, window_minutes: 45}，而非回落默认值）。
_BUILD_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_config.json")


def _load_analysis_enabled():
    """从 build_config.json 读取 analysis_enabled 开关，文件缺失或损坏时默认开启。"""
    try:
        with open(_BUILD_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return bool(cfg.get("analysis_enabled", True))
    except Exception:
        return True

ANALYSIS_ENABLED = _load_analysis_enabled()


def _load_diverse_config():
    """从 build_config.json 读取 diverse 排序配置，文件缺失或损坏时返回默认值。"""
    try:
        with open(_BUILD_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {
            "enabled": bool(cfg.get("diverse_enabled", True)),
            "window_minutes": int(cfg.get("diverse_window_minutes", 120)),
        }
    except Exception:
        return {"enabled": True, "window_minutes": 120}


DIVERSE_CFG = _load_diverse_config()

# ── 72 小时内容累积 ──
RSS_HISTORY_FILE = "rss_history.json"
RSS_HISTORY_HOURS = 72
_rss_history = {}  # {link: {source, source_key, cat, color, title, title_zh, summary, summary_zh, pub_date, time_str}}
_LAST_UNRELIABLE_SRCS = set()  # D4：最近一场 bad_date 审计判定的不可信日期源（关键词降权消费）

# ── Fix 4: T4 长尾层常量 ──
# T4 源：低优先级/长尾源，使用更宽松的跳过阈值和更短的历史保留窗口
# 目的：给频繁失败的低优先级源更多恢复机会，同时避免它们占用过多历史空间
_TIER4_SKIP_THRESHOLD_SEC = 30 * 60   # T4 源增量跳过阈值：30 分钟（T2=1h, T3=2h）
_TIER4_HISTORY_HOURS = 48              # T4 源历史保留窗口：48h（默认 72h）
_TIER_PROMOTION_THRESHOLD = 3          # 连续 3 次成功抓取后自动升级到 T3
_tier4_success_streak = {}             # {source_key: 连续成功次数}

# ── 翻译统计 
_TRANS_STATS = {"agnes": 0, "zen": 0, "google": 0, "bing": 0, "mymemory": 0, "dict": 0, "skip": 0, "fail": 0, "cache_hit": 0}
# GA 免费翻译端点已被数据中心 IP 封锁（429/timeout），AGNES_API_KEY 存在时首选 Agnes AI。
_AGNES_KEY = os.environ.get("AGNES_API_KEY", "")
# Agnes 免费但限流：HTTP 错误与连续空响应都按连续违规指数退避（5→10→20→40 分钟，封顶 1h），
# 期间直接走后续端点，不浪费每次 0.4s 的撞墙（对齐 Zen Z1 账本语义）
_AGNES_BLOCK_UNTIL = 0.0
_AGNES_OFFENSES = 0
_AGNES_EMPTY_STREAK = 0
_AGNES_EMPTY_LIMIT = 3  # 连续空响应阈值（模型偶发拒绝 vs 端点异常的分界）
# OpenCode Zen 免费模型（https://opencode.ai/docs/zen/）：OpenAI 兼容端点，免费档需 OpenCode 客户端会话头。
# 实测（2026-09-13）：ling 2.4s / big-pickle 5.6s / mimo 13.1s 可用；muse-spark 稳定 500、nemotron 两款 88s+，不入轮询。
_ZEN_KEY = os.environ.get("ZEN_API_KEY", "") or os.environ.get("OPENCODE_KEY", "")
_ZEN_MODELS = ([m.strip() for m in os.environ["ZEN_TRANSLATE_MODEL"].split(",") if m.strip()]
               if os.environ.get("ZEN_TRANSLATE_MODEL")
               else ["ling-3.0-flash-fin-free", "big-pickle", "mimo-v2.5-free"])
_ZEN_URL = "https://opencode.ai/zen/v1/chat/completions"
_ZEN_MODEL_BLOCK = {}   # model → 自封截止时间戳
_ZEN_MODEL_OFFENSES = {}  # model → 连续自封次数（自封期翻倍：5→10→20→40 分钟，封顶 1h；成功清零）
_ZEN_MODEL_IDX = 0     # 轮询游标（翻译线程池共享，_TRANS_LOCK 保护）
_ZEN_AUTH_STICKY = None  # 本场构建实测可用的鉴权 token；key 撞 401/403 后粘性回退 "public"
_ZEN_TIMEOUT_STREAK = {}  # model → 连续超时/网络失败计数（≥2 自封；成功重置）
# 翻译熔断：连续 5 次全端点失败后暂停翻译请求 5 分钟（避免上游故障时的请求风暴与构建拖长）
_TRANS_FAIL_STREAK = 0
_TRANS_BLOCK_UNTIL = 0.0
_TRANS_LOCK = threading.Lock()  # 并行翻译线程池下的熔断状态保护


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


def _atomic_write_json(path, obj, **dump_kw):
    """原子写 JSON：先写 .tmp 再 os.replace，进程中断不会留下半截文件"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, **dump_kw)
    os.replace(tmp, path)


def _atomic_write_text(path, text):
    """原子写文本文件：先写 .tmp 再 os.replace"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _save_caches():
    """保存翻译和 RSS 缓存（RSS 缓存写盘前裁剪过期条目，防止文件无限膨胀）"""
    try:
        _atomic_write_json(TRANS_CACHE_FILE, _trans_cache, ensure_ascii=False, indent=2)
        print("[缓存] 保存翻译缓存: %d 条" % len(_trans_cache))
    except Exception as e:
        print("[缓存] 保存翻译缓存失败: %s" % e, file=sys.stderr)
    # RSS 缓存仅保留 TTL 内条目（跨 run 基本全过期，裁剪+紧凑序列化使文件从几十 MB 降至 MB 级）；
    # 该文件已移出 git 跟踪（见 .gitignore），仅服务单次运行内的抓取加速
    pruned = {k: v for k, v in _rss_cache.items()
              if time.time() - v.get("fetched_at", 0) < RSS_CACHE_TTL}
    dropped = len(_rss_cache) - len(pruned)
    try:
        _atomic_write_json(RSS_CACHE_FILE, pruned, ensure_ascii=False, separators=(",", ":"))
        print("[缓存] 保存 RSS 缓存: %d 个源%s" % (len(pruned), "（裁剪过期 %d 个）" % dropped if dropped else ""))
    except Exception as e:
        print("[缓存] 保存 RSS 缓存失败: %s" % e, file=sys.stderr)


def fetch_newsnow_snapshot():
    """构建时逐平台抓取 newsnow 热榜快照，失败返回空列表（不阻塞构建）。
    新 API: GET /api/s?id={platform} -> {status, id, items: [{id,title,url,mobileUrl,extra}]}
    """
    result = []
    for plat in NEWSNOW_PLATFORMS:
        url = NEWSNOW_API_TMPL % plat
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"], "Accept": "application/json"})
            resp = urllib.request.urlopen(req, timeout=NEWSNOW_TIMEOUT)
            ct = resp.headers.get("Content-Type", "")
            if "json" not in ct.lower():
                print("[热榜] %s 返回非JSON (%s)，跳过" % (plat, ct), file=sys.stderr)
                continue
            data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("[热榜] %s 拉取失败: %s" % (plat, e), file=sys.stderr)
            continue
        # 新格式: {status, id, updatedTime, items: [{id, title, url, mobileUrl, extra}], info}
        items = data.get("items") if isinstance(data, dict) else None
        if not items or not isinstance(items, list):
            print("[热榜] %s 无items，跳过" % plat, file=sys.stderr)
            continue
        entries = []
        for idx, it in enumerate(items[:10]):
            entries.append({
                "rank": idx + 1,
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "hot": "",
            })
        if entries:
            result.append({"platform": plat, "name": plat, "items": entries})
    print("[热榜] newsnow 快照: %d 个平台" % len(result))
    return result

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
        _atomic_write_json(RSS_HISTORY_FILE, _rss_history, ensure_ascii=False)
        print("[历史] 保存文章历史: %d 篇" % len(_rss_history))
    except Exception as e:
        print("[历史] 保存失败: %s" % e, file=sys.stderr)


def _accumulate_history(sources_with_items):
    """将新抓取的文章合并到 72 小时历史，裁剪过期内容，返回重组后的 sources_with_items"""
    now_bj = _now_bj()
    cutoff = now_bj.replace(tzinfo=None) - datetime.timedelta(hours=RSS_HISTORY_HOURS)

    # ── pub_date 时区校正（声明式）与同源系统性倒挂发现 ──
    # 校正量来自源配置的 pub_date_offset_min（见 _load_pub_date_offsets 里的取舍说明）；
    # 检测器只报告不落库，避免「猜出来的偏移」静默改写日期。
    # 后续合并 / 裁剪 / 审计 / 输出四处统一用 _effective_pub_dt，避免多套口径。
    _pd_offsets = _load_pub_date_offsets()
    if _pd_offsets:
        print("[pub_date] 已声明时区校正 %d 个源: %s" % (
            len(_pd_offsets),
            ", ".join("%s %+dmin" % (k, v) for k, v in list(_pd_offsets.items())[:8])))
    _anomalies = _detect_pub_date_anomalies(_rss_history, _pd_offsets)
    for _a in _anomalies:
        if _a["kind"] == "tz":
            print("[pub_date] 疑似时区误标 %s: n=%d 倒挂=%.0f%% 中位=%+.0fmin "
                  "→ 建议 pub_date_offset_min=%d（需人工确认后写入 rss_sources.json）" % (
                      _a["key"], _a["n"], _a["inverted_ratio"] * 100,
                      _a["median_delta_min"], _a["suggest_min"]), file=sys.stderr)
        else:
            print("[pub_date] 日期异常（非时区）%s: n=%d 倒挂=%.0f%% 中位=%+.0fmin "
                  "→ 需要前移 %.0fh，远超真实时区范围，不作时区校正" % (
                      _a["key"], _a["n"], _a["inverted_ratio"] * 100,
                      _a["median_delta_min"], _a["need_min"] / 60.0), file=sys.stderr)

    # 合并新文章（按 link 去重，新数据覆盖旧数据）
    new_count = 0
    genuinely_new = 0  # 真正新增的链接（非覆盖）
    for src in sources_with_items:
        for it in src.get("items", []):
            link = it.get("link", "")
            if not link:
                continue
            pd_str = it.get("pub_date", "")
            # 解析日期：优先 pub_date（按源声明的偏移做时区校正），无日期或不可解析时
            # 使用 first_seen（首次抓取时间），仅当 first_seen 也不可用时才回退当前时间。
            pd_bj = now_bj.replace(tzinfo=None)  # 默认当前时间
            _eff = _effective_pub_dt({"pub_date": pd_str, "source_key": src["key"]}, _pd_offsets)
            if _eff is not None:
                pd_bj = _eff.replace(tzinfo=None)
            else:
                # 无 pub_date 时使用 first_seen 作为时间基准
                fs_str = _rss_history.get(link, {}).get("first_seen", "")
                if fs_str:
                    try:
                        fs = datetime.datetime.fromisoformat(fs_str)
                        pd_bj = fs.replace(tzinfo=None) if fs.tzinfo else fs
                    except ValueError:
                        pass  # first_seen 也解析失败，保持当前时间
            if pd_bj < cutoff:
                # 已过期：若历史里已存在同链接条目（典型是「pub_date 为空、靠 first_seen
                # 续命」的陈旧条目），用本轮拿到的真实日期覆盖它，让紧随其后的裁剪循环
                # 按真实日期清掉 —— 否则它会被降级键渲染成「收录 X 前」长期留在页面上。
                _old = _rss_history.get(link)
                if _old is not None:
                    _old["pub_date"] = pd_str
                continue  # 过期文章跳过
            if link not in _rss_history:
                genuinely_new += 1
            _rss_history[link] = {
                "link": link,
                "source": src["name"], "source_key": src["key"],
                "cat": src.get("cat", "other"), "color": src.get("color", "#6366f1"),
                "title": it.get("title", ""), "title_zh": it.get("title_zh", ""),
                "summary": it.get("summary", ""), "summary_zh": it.get("summary_zh", ""),
                "full_content": it.get("full_content", ""),
                "image": it.get("image", ""),
                "media_url": it.get("media_url", ""),
                "media_type": it.get("media_type", ""),
                "pub_date": pd_str,
                "first_seen": _rss_history.get(link, {}).get("first_seen", now_bj.replace(tzinfo=None).isoformat()),
            }
            new_count += 1

    # 裁剪超过 72 小时的旧文章
    before = len(_rss_history)
    expired = []
    for link, item in _rss_history.items():
        pd_str = item.get("pub_date", "")
        pd_bj = now_bj.replace(tzinfo=None)  # 默认当前时间
        # 与合并阶段同一口径：用校正后的发布时间判定是否过期。
        # 不校正的话，被标成 +00:00 的源会「多活 8 小时」（其 pub_date 偏晚）。
        _eff = _effective_pub_dt(item, _pd_offsets)
        if _eff is not None:
            pd_bj = _eff.replace(tzinfo=None)
        else:
            # pub_date 缺失或不可解析，使用 first_seen
            fs_str = item.get("first_seen", "")
            if fs_str:
                try:
                    fs = datetime.datetime.fromisoformat(fs_str)
                    pd_bj = fs.replace(tzinfo=None) if fs.tzinfo else fs
                except ValueError:
                    pass
        if pd_bj < cutoff:
            expired.append(link)
    for link in expired:
        del _rss_history[link]

    # 按源重组，更新相对时间
    # 构建 source_key -> url 映射（用于识别 BestBlogs 源）
    _src_url_map = {s["key"]: s.get("url", "") for s in sources_with_items}
    # 补充：从 RSS_SOURCES 查找缺失的 URL（sources_with_items 可能不含 url）
    for _rs in RSS_SOURCES:
        if _rs["key"] not in _src_url_map or not _src_url_map[_rs["key"]]:
            _src_url_map[_rs["key"]] = _rs.get("url", "")
    src_map = {}
    # Fix 2: 保留当次抓取结果，避免被空壳替换
    # 先用当次抓取的 items 初始化 src_map，后续历史回填时按 link 去重补充
    _fetch_items_by_key = {}
    for src in sources_with_items:
        _items = src.get("items", [])
        if _items:
            _fetch_items_by_key[src["key"]] = {it.get("link", ""): it for it in _items if it.get("link")}
    for src in sources_with_items:
        _bb = 'bestblogs.dev' in (_src_url_map.get(src["key"]) or '')
        _fetched = src.get("items", [])
        src_map[src["key"]] = {
            "key": src["key"], "name": src["name"],
            "cat": src.get("cat", "other"), "color": src.get("color", "#6366f1"),
            "tier": src.get("tier", 3), "items": list(_fetched),
        }
        if _bb:
            src_map[src["key"]]["bb"] = True
    # --- 信源级 pub_date 质量自动审查 ---
    # 第一遍：按源统计 pub_date 异常比例
    #   异常模式 A: pub_date ≈ first_seen (|delta|<10min) → pub_date 大概率是抓取时间
    #   异常模式 B: pub_date > first_seen (delta<-10min) → 日期倒挂
    #   注：公众号源已不再硬编码为不可信——实测 wechat2rss 的 pub_date 均为真实发布时间，
    #       统一由异常率阈值判定（与其余类目一视同仁）
    _src_date_stats = {}  # source_key -> {total, anomaly_a, anomaly_b}
    for item in _rss_history.values():
        sk = item["source_key"]
        if sk not in src_map:
            continue
        if sk not in _src_date_stats:
            _src_date_stats[sk] = {"total": 0, "anomaly_a": 0, "anomaly_b": 0}
        _src_date_stats[sk]["total"] += 1
        # 审计必须跑在**校正后**的发布时间上：否则一个纯时区解析问题会被判成
        # 「日期不可信」，进而把该源的关键词按 0.3 倍降权（内容质量问题），
        # 并把卡片改成显示绝对日期 —— 两处都是误伤。
        pd = _effective_pub_dt(item, _pd_offsets)
        fs = _parse_hist_dt(item.get("first_seen"))
        if pd is not None and fs is not None:
            try:
                delta_sec = (fs - pd).total_seconds()
                if abs(delta_sec) < 600:      # 模式 A: < 10 分钟
                    _src_date_stats[sk]["anomaly_a"] += 1
                elif delta_sec < -600:         # 模式 B: 日期倒挂
                    _src_date_stats[sk]["anomaly_b"] += 1
            except (ValueError, TypeError):
                pass

    # 判定不可信源：异常率 > 30%
    _unreliable_srcs = set()
    BAD_DATE_ANOMALY_THRESHOLD = 0.3
    for sk, stats in _src_date_stats.items():
        if stats["total"] == 0:
            continue
        anomaly_ratio = (stats["anomaly_a"] + stats["anomaly_b"]) / stats["total"]
        if anomaly_ratio > BAD_DATE_ANOMALY_THRESHOLD:
            _unreliable_srcs.add(sk)  # 自动检测为不可信
    if _unreliable_srcs:
        names = [src_map[sk]["name"] for sk in _unreliable_srcs if sk in src_map][:10]
        print("[bad_date] 不可信信源 %d 个: %s%s" % (
            len(_unreliable_srcs), ", ".join(names),
            " ..." if len(_unreliable_srcs) > 10 else ""))
    # D4：暴露给趋势快照与关键词降权消费
    global _LAST_UNRELIABLE_SRCS
    _LAST_UNRELIABLE_SRCS = set(_unreliable_srcs)

    # 模式 C：同日期伪造检测（知乎日报/愆伏/梅之夏等）
    _uniform_flagged = _detect_uniform_dates(
        [_rss_history[k] for k in _rss_history],
        min_items=5, threshold=0.8
    )
    if _uniform_flagged:
        _unreliable_srcs |= _uniform_flagged
        _LAST_UNRELIABLE_SRCS = set(_unreliable_srcs)
        _names = [src_map[sk]["name"] for sk in _uniform_flagged if sk in src_map][:5]
        print("[bad_date-C] 同日期伪造源 %d 个: %s" % (
            len(_uniform_flagged), ", ".join(_names)))
        # 立即标记条目
        for item in _rss_history.values():
            if item.get("source_key") in _uniform_flagged:
                item["bad_date"] = True

    # 第二遍：时区校正 → 未来日期处置 → 标记 bad_date → 重组
    # 判伪条目的回拉位移先算好（按「源 + 抓取批次」分组，保序不折叠 —— 见 _plan_falsify_shifts）
    _cutoff_aware = cutoff.replace(tzinfo=_BJ_TZ)
    _falsify_shifts = _plan_falsify_shifts(
        _rss_history, _pd_offsets, src_keys=set(src_map.keys()))
    _n_tz_fixed = 0
    _n_falsified = 0
    _n_shifted = 0
    for item in _rss_history.values():
        sk = item["source_key"]
        if sk in src_map:
            entry = dict(item)   # 副本：下面的降级改写不得污染历史（历史只存原始 pub_date）
            entry["bad_date"] = sk in _unreliable_srcs
            # (1) 源级时区校正：把上游标错时区的时间还原成真实发布时间。
            #     这是根因层修复 —— 校正后条目不再「出生于未来」，
            #     也就不需要前端钳制介入（钳制会把多条折叠成同一时刻 → 整块钉首屏）。
            _off = _pd_offsets.get(sk)
            if _off and entry.get("pub_date"):
                _shifted = _shift_iso_minutes(entry["pub_date"], _off)
                if _shifted != entry["pub_date"]:
                    entry["pub_date"] = _shifted
                    _n_tz_fixed += 1
            # (2) 取不到 pub_date 时给一个可排序的降级键（= first_seen，我方首次收录该链接的真实时刻）。
            #     没有它，条目在默认排序里只能沉底 → 用户永远看不到（2026-09-14：201 条因此不可见）。
            _fb = _fallback_date_iso(entry)
            if not _fb and _pub_date_falsified(entry, _pd_offsets):
                # (3) 有 pub_date，但晚于 first_seen 超过容忍阈值 —— 我们「在文章发布前抓到了它」，
                #     物理不可能 ⇒ 该日期已被证伪，不能拿来排序。改用它自己的 first_seen：
                #     这是一个我方记录的真实时刻，既诚实（前端显示「收录」）又能参与排序。
                #     不选「钳到 now」：那会让多条条目获得同一时刻，正是首屏同刻扎堆的成因。
                #     也不能整批都写同一个 first_seen（first_seen 是批次戳，实测 8411 条只有
                #     122 个取值）—— 故按 _falsify_shifts 保序回拉，最新的一条锚在 first_seen，
                #     组内相对先后保留，且下限钳在 72h cutoff 上。
                _shift = _falsify_shifts.get(item.get("link"), 0)
                _fb = _shift_iso_minutes(_first_seen_iso(entry), _shift)
                _fbd = _parse_hist_dt(_fb)
                if _fbd is None or _fbd < _cutoff_aware:
                    _fb = _cutoff_aware.replace(microsecond=0).isoformat()
                if _fb:
                    _n_falsified += 1
                    if _shift:
                        _n_shifted += 1
            if _fb:
                entry["pub_date"] = _fb
                entry["date_fallback"] = True
            entry["time_str"] = _fmt_rel_time(entry.get("pub_date"))
            # Fix 2: 去重 — 跳过当次抓取已存在的同链接条目
            _link = entry.get("link", "")
            if _link and sk in _fetch_items_by_key and _link in _fetch_items_by_key[sk]:
                continue
            src_map[sk]["items"].append(entry)

    if _n_tz_fixed or _n_falsified:
        print("[pub_date] 口径修正：时区校正 %d 条 / 未来日期改用收录时刻 %d 条"
              "（其中 %d 条按批次保序回拉，未折叠为同一时刻）" % (
                  _n_tz_fixed, _n_falsified, _n_shifted))

    result = list(src_map.values())
    total = sum(len(s["items"]) for s in result)
    pruned = before - len(_rss_history)
    print("[历史] 合并 %d 篇新文（其中 %d 篇为新增链接，%d 篇为覆盖更新），裁剪 %d 篇过期，保留 %d 篇（%d 小时窗口）" % (
        new_count, genuinely_new, new_count - genuinely_new, pruned, len(_rss_history), RSS_HISTORY_HOURS))
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
    """生成 API 快照 JSON（分块），供 /api/rss 直接返回，避免实时抓取丢失历史累积数据。
    按 ~80MB 上限拆分为 rss_api_snapshot.json + rss_api_snapshot_1.json ...，
    避免超过 GitHub 100MB 单文件限制。"""
    MAX_SNAPSHOT_BYTES = 80 * 1024 * 1024

    # ── 快照级去重：清理历史累积中的残留重复 ──
    # 历史数据可能包含修复前抓取的重复条目（如 V2EX #replyN）
    for src in sources_with_items:
        src["items"] = _dedup_source_items(src.get("items", []), src.get("key", ""))

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
            if it.get("bad_date"):
                item["bad_date"] = True
            if it.get("date_fallback"):
                item["date_fallback"] = True
            _tags = it.get("tags")
            if _tags:
                item["tags"] = _tags
            fc = it.get("full_content", "")
            if fc:
                item["fc"] = fc[:50000]
            img = it.get("image", "")
            if img:
                item["img"] = img
            mu = it.get("media_url", "")
            if mu:
                item["mu"] = mu
                item["mt"] = it.get("media_type", "")
            items.append(item)
        snapshot_sources.append({
            "key": src["key"], "name": src["name"],
            "cat": src.get("cat", "other"), "color": src.get("color", "#6366f1"),
            "tier": src.get("tier", 3), "items": items,
        })

    # 估算每源体积，按体积均匀分桶
    src_sizes = []
    for s in snapshot_sources:
        try:
            sz = len(json.dumps(s, ensure_ascii=False).encode("utf-8"))
        except Exception:
            sz = 1024
        src_sizes.append(sz)
    total_bytes = sum(src_sizes)
    n_chunks = max(1, (total_bytes + MAX_SNAPSHOT_BYTES - 1) // MAX_SNAPSHOT_BYTES)

    buckets = [[] for _ in range(n_chunks)]
    bucket_sizes = [0] * n_chunks
    for i, (s, sz) in enumerate(zip(snapshot_sources, src_sizes)):
        min_idx = bucket_sizes.index(min(bucket_sizes))
        buckets[min_idx].append(s)
        bucket_sizes[min_idx] += sz

    total_items = sum(len(s["items"]) for s in snapshot_sources)
    try:
        for idx, bucket in enumerate(buckets):
            fname = "rss_api_snapshot.json" if idx == 0 else "rss_api_snapshot_%d.json" % idx
            chunk_data = {"t": _now_bj().isoformat(), "sources": bucket}
            if idx == 0 and meta:
                chunk_data["meta"] = meta
                chunk_data["_total_chunks"] = n_chunks
            _atomic_write_json(fname, chunk_data, ensure_ascii=False)
            size_mb = bucket_sizes[idx] / 1024 / 1024
            print("[快照] %s: %d 源 %.1f MB" % (fname, len(bucket), size_mb))

        # 清理旧的多余快照文件
        import glob
        for old_file in glob.glob("rss_api_snapshot_*.json"):
            try:
                num = int(old_file.replace("rss_api_snapshot_", "").replace(".json", ""))
                if num >= n_chunks:
                    os.remove(old_file)
                    print("[快照] 清理旧文件: %s" % old_file)
            except ValueError:
                pass

        print("[快照] 保存 API 快照: %d 源 %d 篇 (%d 块)" % (len(snapshot_sources), total_items, n_chunks))
    except Exception as e:
        print("[快照] 保存失败: %s" % e, file=sys.stderr)


# ── RSS 信源配置（从 rss_sources.json 读取，tier 分层） ─
_SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rss_sources.json")
try:
    with open(_SOURCES_FILE, "r", encoding="utf-8") as _f:
        RSS_SOURCES = json.load(_f)
    # 补全缺失 tier/color（兼容旧格式；前端与聚合代码直接读 color，缺失会 KeyError）
    # 丢弃缺 key/name/url 的坏条目：单条坏配置不应炸整场构建（对抗性审查 P3）
    _BAD = []
    _COLOR_PALETTE = ["#6366f1", "#10a37f", "#4285f4", "#e61919", "#ff6600", "#7c3aed", "#0891b2", "#d97706", "#d32f2f", "#24292e"]
    for _s in RSS_SOURCES:
        if not isinstance(_s, dict):
            _BAD.append(str(_s)[:30] + "(非dict)")
            continue
        if not _s.get("key") or not _s.get("name") or not _s.get("url"):
            _BAD.append(_s.get("key") or "(无key)")
    RSS_SOURCES = [s for s in RSS_SOURCES if isinstance(s, dict) and s.get("key") and s.get("name") and s.get("url")]
    for _s in RSS_SOURCES:
        _s.setdefault("tier", 3)
        _s.setdefault("cat", "other")
        if not _s.get("color"):
            _s["color"] = _COLOR_PALETTE[int(hashlib.md5(_s.get("key", "").encode("utf-8")).hexdigest(), 16) % len(_COLOR_PALETTE)]
    if _BAD:
        print("[RSS] 丢弃 %d 个缺 key/name/url 的坏配置: %s" % (len(_BAD), _BAD[:5]), file=sys.stderr)
    print("[RSS] 从 rss_sources.json 加载 %d 个源" % len(RSS_SOURCES))
except (FileNotFoundError, json.JSONDecodeError) as _e:
    print("[RSS] rss_sources.json 不可用 (%s)，RSS 聚合将跳过" % _e, file=sys.stderr)
    RSS_SOURCES = []


# 分类标签
CATEGORY_LABELS = {
    "wechat": "公众号",
    "ai":      "AI 日报",
    "tech":    "科技资讯",
    "cn_tech": "中文科技",
    "dev":     "开发者",
    "news":    "综合新闻",
    "podcast": "播客",
    "twitter": "Twitter/X",
}

# 分类排序（公众号置顶）
CATEGORY_ORDER = ["wechat", "ai", "tech", "cn_tech", "dev", "news", "twitter", "podcast"]

# ── 公众号信源自动归类：wechat2rss URL → cat=wechat ──
for _s in RSS_SOURCES:
    if "wechat2rss" in _s.get("url", ""):
        _s["cat"] = "wechat"

ITEMS_PER_SOURCE = 30
FETCH_TIMEOUT = 8
TRANSLATE_TIMEOUT = 3


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


_IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"'\s>]+)[\"']", re.IGNORECASE)

def _extract_img_from_html(text):
    """从 HTML 片段提取首个可外链的图片 URL（供卡片封面降级用）"""
    if not text:
        return ""
    m = _IMG_SRC_RE.search(text)
    if not m:
        return ""
    src = html_mod.unescape(m.group(1)).strip()
    if not re.match(r"^https?://", src, re.IGNORECASE):
        return ""
    return src


def _pick_item_image(it, desc_raw, content_raw):
    """RSS item 图片提取优先级：enclosure > media:content > media:thumbnail > 正文首图 > 描述首图"""
    try:
        enc = it.find("enclosure")
        if enc is not None:
            etype = (enc.get("type") or "").lower()
            eurl = (enc.get("url") or "").strip()
            if eurl and (etype.startswith("image") or re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", eurl, re.IGNORECASE)):
                return eurl
        mrss = "{http://search.yahoo.com/mrss/}"
        for tag in ("content", "thumbnail"):
            m_el = it.find(mrss + tag)
            if m_el is not None and (m_el.get("url") or "").strip():
                mtype = (m_el.get("type") or m_el.get("medium") or "").lower()
                if not mtype or mtype.startswith("image") or mtype == "photo":
                    return m_el.get("url").strip()
        img = _extract_img_from_html(content_raw) or _extract_img_from_html(desc_raw)
        return img
    except Exception:
        return ""


# ── XGO (Twitter/X) 信源内容清洗 ──────────────────────────────
_XGO_TWEET_TEXT_RE = re.compile(
    r"<div[^>]*\bwhite-space:\s*pre-wrap[^>]*>([\s\S]*?)</div>",
    re.IGNORECASE,
)
_XGO_ENGAGEMENT_RE = re.compile(
    r"💬|🔄|❤️|👀|📊|⚡\s*Powered\s+by\s+xgo\.ing|View\s+(?:Quoted\s+)?Tweet\s*🔗|🔗\s*View",
    re.IGNORECASE,
)


def _is_xgo_content(text):
    """检测是否为 xgo.ing Twitter/X 代理的推文 HTML"""
    if not text:
        return False
    return ("xgo.ing" in text or "Powered by xgo" in text) and "white-space: pre-wrap" in text


def _clean_xgo_content(text):
    """清洗 xgo.ing 推文 HTML：仅保留推文正文与引用推文文本，移除互动数据/头像/页脚"""
    if not text:
        return ""
    # 1. 提取所有推文文本块（white-space: pre-wrap 的 div）
    blocks = _XGO_TWEET_TEXT_RE.findall(text)
    if not blocks:
        return ""
    parts = []
    for block in blocks:
        # 移除 "View Quoted Tweet" / "View on Twitter" 链接
        block = re.sub(
            r"<a[^>]*>[^<]*View\s+(?:Quoted\s+)?Tweet[^<]*</a>",
            "",
            block,
            flags=re.IGNORECASE,
        )
        # 移除剩余 HTML 标签
        plain = re.sub(r"<[^>]+>", "", block)
        plain = html_mod.unescape(plain).strip()
        if plain:
            parts.append(plain)
    return "\n\n".join(parts)


def _extract_tweet_media(text):
    """从 xgo.ing 推文 HTML 中提取真实推文媒体图片（排除 profile_images 头像）"""
    if not text:
        return ""
    for m in _IMG_SRC_RE.finditer(text):
        src = html_mod.unescape(m.group(1)).strip()
        if not re.match(r"^https?://", src, re.IGNORECASE):
            continue
        # 跳过 profile_images（用户头像），仅保留 /media/ 和 tweet_video_thumb
        if "profile_images" in src:
            continue
        if "/media/" in src or "tweet_video_thumb" in src:
            return src
    return ""


# ── 图片质量自动升级系统 ──────────────────────────────────────
# 规则注册表：新增 CDN 只需在此追加一行
# 格式: (域名子串, 匹配正则, 替换模板)
_IMG_UPGRADE_RULES = [
    # Phys.org CDN: /tmb/ 是 90×90 缩略图，/800/ 是 800px 高清图
    ("scx1.b-cdn.net",     r"/tmb/",                              r"/800/"),
    # BBC ichef CDN: /240/ (6KB) → /624/ (30KB)，路径中数字即像素宽度
    ("ichef.bbci.co.uk",   r"/240/",                              r"/624/"),
    # Twitter/X 头像: _normal (48×48) → _400x400
    ("pbs.twimg.com",      r"_normal\.(jpg|png|gif)$",             r"_400x400.\1"),
]

# 需要回调函数的特殊规则（简单字符串替换无法正确处理）
def _bbc_aspect_upgrade(url):
    """BBC NxM → 624xH，保持原始宽高比"""
    def _replace(m):
        old_w, old_h = int(m.group(1)), int(m.group(2))
        new_h = round(old_h * 624 / old_w)
        return f"/{624}x{new_h}/"
    return re.sub(r"/(\d{2,4})x(\d{2,4})/", _replace, url)

def _query_width_upgrade(url):
    """保留原始查询参数分隔符（? 或 &），避免产生双 ?"""
    def _replace(m):
        sep = m.group(1)  # 保留原始 ? 或 &
        return f"{sep}width=640"
    return re.sub(r"([?&])width=\d+", _replace, url)

_IMG_UPGRADE_SPECIAL = [
    # BBC ichef: NxM 尺寸保持宽高比
    ("ichef.bbci.co.uk", _bbc_aspect_upgrade),
    # Reddit / Guardian: width=N 查询参数升级
    ("redd.it",          _query_width_upgrade),
    ("i.guim.co.uk",    _query_width_upgrade),
]

# 升级追踪（线程安全，供构建审计使用）
_img_upgrade_log = []
_img_upgrade_lock = threading.Lock()


def _upgrade_img_url(url):
    """升级已知低分辨率图片 URL 到高清版本，并记录升级事件"""
    if not url:
        return url
    original = url
    # 简单规则：正则替换
    for domain_match, pattern, replacement in _IMG_UPGRADE_RULES:
        if domain_match in url:
            new_url = re.sub(pattern, replacement, url)
            if new_url != url:
                url = new_url
    # 特殊规则：回调函数（保持宽高比/查询参数完整性）
    for domain_match, func in _IMG_UPGRADE_SPECIAL:
        if domain_match in url:
            new_url = func(url)
            if new_url != url:
                url = new_url
    if url != original:
        with _img_upgrade_lock:
            _img_upgrade_log.append({"from": original, "to": url})
    return url


# ── 通用缩略图检测器（发现未知 CDN 的低分辨率模式）──
# 策略：仅检测高置信度模式（查询参数小尺寸 + 缩略图关键词），
# 不做路径数字段匹配（日期 /15/、hash /25/ 等误报率极高）。
# 新 CDN 的缩略图由构建审计发现后，手动加入 _IMG_UPGRADE_RULES 即可。
_THUMB_QUERY_RE = re.compile(r"[?&](?:w|h|width|height|size)=(\d+)", re.IGNORECASE)
_THUMB_KEYWORD_RE = re.compile(
    r"/(?:thumb|thumbnail|tiny|mini|avatar)(?:[/.]|$)"
    r"|_normal\.(?:jpg|png|gif)",
    re.IGNORECASE,
)
# 排除误报：日期路径、商品图、emoji、大尺寸参数、/display/ 路径等
_THUMB_EXCLUDE_RE = re.compile(
    r"/(?:19|20)\d{2}/"       # 年份路径
    r"|s\d{3,4}x\d{3,4}"     # 商品图 s1440x1440
    r"|/emoji/"               # emoji 图标
    r"|width=\d{4,}"          # 大尺寸参数 width=800+
    r"|/display/",            # France24 等 /display/ 路径
    re.IGNORECASE,
)


def _detect_lowres_img(url):
    """通用检测：URL 是否疑似缩略图（用于审计告警，不修改 URL）"""
    if not url:
        return None
    if _THUMB_EXCLUDE_RE.search(url):
        return None
    # 查询参数中的小尺寸（≤300）
    m = _THUMB_QUERY_RE.search(url)
    if m:
        num = int(m.group(1))
        if num <= 300:
            return f"query ={num}"
    # 缩略图关键词
    if _THUMB_KEYWORD_RE.search(url):
        return "thumb keyword"
    return None


def _audit_image_quality(sources_with_items):
    """构建时图片质量审计：报告升级统计与未解决的疑似低分辨率图片"""
    total_imgs = 0
    upgraded_count = len(_img_upgrade_log)
    # 按域名统计升级分布
    upgrade_by_domain = collections.Counter()
    for ev in _img_upgrade_log:
        domain = ev["from"].split("/")[2] if ev["from"].startswith("http") else "unknown"
        upgrade_by_domain[domain] += 1
    # 扫描所有图片，检测未升级的疑似缩略图
    suspect = []  # (source_name, url, reason)
    suspect_by_source = collections.Counter()
    for src in sources_with_items:
        src_name = src.get("name", "")
        for it in src.get("items", []):
            img = it.get("image", "")
            if not img:
                continue
            total_imgs += 1
            reason = _detect_lowres_img(img)
            if reason:
                suspect.append((src_name, img, reason))
                suspect_by_source[src_name] += 1
    # 输出报告
    print(f"[图片审计] 总计 {total_imgs} 张, 已升级 {upgraded_count} 张")
    if upgrade_by_domain:
        for domain, count in upgrade_by_domain.most_common(10):
            print(f"  升级: {domain} ({count} 张)")
    if suspect:
        print(f"[图片审计] ⚠ {len(suspect)} 张疑似低分辨率（{len(suspect_by_source)} 个源）:")
        for src_name, count in suspect_by_source.most_common(20):
            sample = next(u for s, u, _ in suspect if s == src_name)
            print(f"  {src_name}: {count} 张 — {sample[:90]}")
    else:
        print("[图片审计] ✓ 无残留低分辨率图片")
    return {"total": total_imgs, "upgraded": upgraded_count, "suspect": len(suspect)}


_SAFE_TAGS = re.compile(
    r"^(/?(p|br|img|a|b|i|em|strong|h[1-6]|ul|ol|li|blockquote|pre|code"
    r"|figure|figcaption|table|tr|td|th|thead|tbody|span|div|hr|sup|sub|dl|dt|dd"
    r"|audio|video|source|iframe))$",
    re.IGNORECASE,
)
_EVT_ATTR = re.compile(r"^on[a-z]+$", re.IGNORECASE)
_TAG_NAME = re.compile(r"^</?(\w[\w-]*)")
# 仅保留渲染正文结构必需的属性：WeChat 段落带巨型内联 style，全量保留会撑爆快照
_KEPT_ATTRS = {
    "img": ("src", "alt"), "a": ("href",),
    "iframe": ("src", "width", "height", "frameborder", "allowfullscreen"),
    "audio": ("src", "controls", "preload"),
    "video": ("src", "controls", "preload", "poster", "width", "height"),
    "source": ("src", "type"),
}
_BOOL_ATTRS = {"controls"}
_URL_SCHEME = re.compile(r"^\s*(?:https?:|mailto:|/|#|data:image/)", re.IGNORECASE)
_SAFE_IFRAME_RE = re.compile(
    r'<iframe\s[^>]*src\s*=\s*"([^"]*(?:youtube\.com|youtu\.be|vimeo\.com)[^"]*)"[^>]*>\s*</iframe>',
    re.IGNORECASE | re.DOTALL,
)
_IFRAME_TAG_RE = re.compile(r'<iframe[^>]*>', re.IGNORECASE | re.DOTALL)
_MEDIA_ATTRS = re.compile(r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]+)')


def _pick_item_media(it):
    """提取 enclosure / media:content 中的音频视频 URL（跳过图片类型）"""
    try:
        enc = it.find("enclosure")
        if enc is not None:
            etype = (enc.get("type") or "").lower()
            eurl = (enc.get("url") or "").strip()
            if eurl and (etype.startswith("audio") or etype.startswith("video")):
                return eurl, etype
        mrss = "{http://search.yahoo.com/mrss/}"
        m_el = it.find(mrss + "content")
        if m_el is not None and (m_el.get("url") or "").strip():
            mtype = (m_el.get("type") or m_el.get("medium") or "").lower()
            if mtype in ("audio", "video") or mtype.startswith("audio") or mtype.startswith("video"):
                return m_el.get("url").strip(), mtype
    except Exception:
        pass
    return "", ""


def _sanitize_html(text):
    if not text:
        return ""
    text = html_mod.unescape(text)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    # 提取安全 iframe（仅 YouTube / Vimeo），替换为占位符，清洗后还原
    safe_iframes = []
    def _save_iframe(m):
        safe_iframes.append(m.group(0))
        return '\x00IFRAME%d\x00' % (len(safe_iframes) - 1)
    while _SAFE_IFRAME_RE.search(text):
        text = _SAFE_IFRAME_RE.sub(_save_iframe, text, count=1)
    # 移除剩余非安全 iframe
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
        kept = _KEPT_ATTRS.get(tag.lower(), ())
        safe_attrs = []
        if kept:
            for k, v in re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', full):
                if k.lower() not in kept or _EVT_ATTR.match(k):
                    continue
                # URL scheme 检查仅对 src/href/poster 等 URL 属性
                if k.lower() in ("src", "href", "poster") and not _URL_SCHEME.match(v):
                    continue
                safe_attrs.append('%s="%s"' % (k.lower(), v.replace("&", "&amp;")))
            # 布尔属性（如 controls）无 ="value"，单独检测
            for battr in ("controls",):
                if battr in kept and re.search(r'\b' + battr + r'(?:\s|>|/)', full, re.IGNORECASE):
                    safe_attrs.append(battr)
        if tag.lower() == "img" and not any(a.startswith("src=") for a in safe_attrs):
            return ""
        # iframe 二次校验：仅放行 YouTube / Vimeo 域名
        if tag.lower() == "iframe":
            src_val = ""
            for a in safe_attrs:
                if a.startswith("src="):
                    src_val = a[5:].replace("&amp;", "&")
                    break
            if not re.search(r'youtube\.com|youtu\.be|vimeo\.com', src_val, re.IGNORECASE):
                return ""
        if safe_attrs:
            return "<%s %s>" % (tag, " ".join(safe_attrs))
        if full.startswith("</"):
            return "</%s>" % tag
        return "<%s>" % tag

    text = re.sub(r"<[^>]+>", _clean_tag, text)
    text = re.sub(r"<[^>]*$", "", text)
    # 还原安全 iframe
    for i, iframe_tag in enumerate(safe_iframes):
        text = text.replace('\x00IFRAME%d\x00' % i, iframe_tag)
    return text.strip()


def _deep_clean_html(text):
    """深度清洗 RSS 正文：移除广告、推广、引导关注等噪音，保留正文结构"""
    if not text:
        return ""
    # 1. 移除广告/推广/订阅/评论相关 class 或 id 的整个元素
    text = re.sub(
        r'<(\w+)[^>]*\b(?:class|id)\s*=\s*"[^"]*\b(?:ads?[_-]?|advert|banner|sponsor|promo|newsletter|subscribe|social-share|share-buttons?|related-posts|recommend|widget|comments?|disqus|pagination|footer-links|follow-us|qrcode|qr-code)[^"]*"[^>]*>[\s\S]*?</\1>',
        '', text, flags=re.IGNORECASE)
    # 1.5 移除 wechat2rss / link-proxy 跳转链接（"跳转微信打开"等）
    text = re.sub(
        r'<a[^>]*href="[^"]*(?:link-proxy|wechat2rss|mp\.weixin\.qq\.com)[^"]*"[^>]*>[^<]*</a>',
        '', text, flags=re.IGNORECASE)
    text = re.sub(
        r'<a[^>]*>[^<]*跳转微信[^<]*</a>',
        '', text, flags=re.IGNORECASE)
    # 2. 逐块检测：剥离内联标签后匹配推广模式
    _promo_re = re.compile(
        r'代开关注|长按二维码|扫码关注|扫一扫关注|微信搜索.*关注|关注公众号|关注我们'
        r'|立即购买|点击领取|点击注册|限时优惠|秒杀活动|加入社群|加入我们'
        r'|勾选关注|长按关注|识别二维码|二维码|长按识别'
        r'|关注.*公众号|关注.*微信|点击.*订阅|订阅.*频道|订阅.*邮件|加入.*邮件列表'
        r'|微博.*关注|关注.*微博|分享.*好友|转发.*朋友'
        r'|转发.*关注|关注.*转发|点赞.*关注|关注.*点赞|点赞.*在看'
        r'|喜欢.*关注|喜欢.*点赞|觉得.*关注|觉得.*有用|精彩.*不错过'
        r'|请长按|请扫码|点击原文|点击.*原文|点击.*查看原文'
        r'|buy now|subscribe (?:now|today)|limited.?time|click here to'
        r'|sign up (?:now|today)|special offer|discount code|use code|free trial'
        r'|donate (?:now|today)|support us|follow us (?:on|for)|join our'
        r'|share this (?:article|post)',
        re.IGNORECASE)
    def _strip_and_check(m):
        block = m.group(0)
        plain = re.sub(r'<[^>]+>', '', block)
        return '' if _promo_re.search(plain) else block
    text = re.sub(r'<(p|div)\b[^>]*>[\s\S]*?</\1>', _strip_and_check, text, flags=re.IGNORECASE)
    # 3. 移除清洗后残留的空块元素
    text = re.sub(
        r'<(?:p|div|span)\b[^>]*>\s*(?:<br\s*/?>\s*)*</(?:p|div|span)>',
        '', text, flags=re.IGNORECASE)
    # 4. 压缩连续空行（保留段落间距）
    text = re.sub(r'(?:\s*\n){3,}', '\n\n', text)
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

# RFC 822 字母时区（小时偏移）。注意 CST 在 RFC 822 中定义为 -0600（美国中部）；
# 中国的 CST(+0800) 在真实 feed 里一律写作 +0800 / GMT+0800，不靠裸 "CST" 表达。
_RSS_TZ_NAMED = {"UT":0,"UTC":0,"GMT":0,"Z":0,
                 "EST":-5,"EDT":-4,"CST":-6,"CDT":-5,
                 "MST":-7,"MDT":-6,"PST":-8,"PDT":-7}

# 覆盖真实世界出现过的 RSS pubDate 写法（2026-09-14 实测样本见 tests/rss_date/）：
#   "Fri Oct 27 2023 15:13:00 GMT+0800 (China Standard Time)"   ← JS Date.toString()，月在前
#   "13 Sep 2026 07:28:00 EST"                                  ← 日在前 + 字母时区，无星期前缀
#   "Mon, 18 May 2020"                                          ← 仅日期
#   "Mon, 14 Sep 2026 01:18:00 GMT"                             ← 标准 RFC 822
_RSS_DATE_RE = re.compile(
    r"^(?:\w{3,9},?\s+)?"                                       # 可选星期前缀（Mon, / Monday ）
    r"(?:"
    r"(?P<d1>\d{1,2})\s+(?P<m1>[A-Za-z]{3,9})"                  # 词序 A：日 月
    r"|"
    r"(?P<m2>[A-Za-z]{3,9})\.?\s+(?P<d2>\d{1,2}),?"             # 词序 B：月 日（可带点/逗号）
    r")"
    r"\s+(?P<y>\d{4})"                                          # 年
    r"(?:\s+(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?"    # 可选时间（秒可省略）
    r"(?:\s*(?:GMT|UTC|UT)?\s*(?P<tz>[+-]\d{2}:?\d{2}|[A-Za-z]{2,4}))?"   # 可选时区（数字或字母）
    r"(?:\s*\(.*\))?$"                                          # 忽略 "(China Standard Time)"
)


def _rss_tz_offset(tz):
    """把时区串变成 timedelta。无法识别时保守返回 UTC（宁可靠近而非丢弃）。"""
    if not tz:
        return datetime.timedelta(0)
    if tz[0] in "+-":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        try:
            hh = int(digits[:2])
            mm = int(digits[2:4]) if len(digits) >= 4 else 0
        except ValueError:
            return datetime.timedelta(0)
        return datetime.timedelta(hours=sign * hh, minutes=sign * mm)
    hours = _RSS_TZ_NAMED.get(tz.upper())
    if hours is None:
        return datetime.timedelta(0)
    return datetime.timedelta(hours=hours)


def _parse_rss_date(s):
    s = (s or "").strip()
    if not s:
        return None
    m = _RSS_DATE_RE.match(s)
    if m:
        mon = _RSS_MONTHS.get((m.group("m1") or m.group("m2"))[:3].title())
        if mon:
            h, mi, sec = int(m.group("H") or 0), int(m.group("M") or 0), int(m.group("S") or 0)
            try:
                return datetime.datetime(int(m.group("y")), mon, int(m.group("d1") or m.group("d2")),
                                         h, mi, sec, tzinfo=datetime.timezone(_rss_tz_offset(m.group("tz"))))
            except ValueError:
                return None
    return _parse_iso(s)


_BJ_TZ = datetime.timezone(datetime.timedelta(hours=8))


def _detect_uniform_dates(items, min_items=5, threshold=0.8):
    """检测同日期伪造（bad_date 模式 C）。

    同一源 ≥min_items 条条目中，超过 threshold 比例共享完全相同的 pub_date 字符串
    → 判定为日期伪造，返回该源 key 集合。

    典型场景：知乎日报 anyfeeder feed 无 pubDate，_fallback_date_iso 用 first_seen
    填充 → 同批次所有条目获得完全相同的时间戳。
    """
    from collections import Counter, defaultdict
    src_dates = defaultdict(list)
    for item in items:
        sk = item.get("source_key", "")
        pd = item.get("pub_date", "")
        if sk and pd:
            src_dates[sk].append(pd)

    flagged = set()
    for sk, dates in src_dates.items():
        if len(dates) < min_items:
            continue
        cnt = Counter(dates)
        most_common_date, most_common_count = cnt.most_common(1)[0]
        ratio = most_common_count / len(dates)
        if ratio >= threshold:
            flagged.add(sk)
    return flagged


def _parse_hist_dt(s):
    """历史/输出里的时间串 → 北京时间 aware datetime（裸值按北京时间理解）。

    历史文件里 pub_date 可能是 aware（+08:00 / Z）也可能是裸值，
    历史上各处各写一份解析逻辑（至少 4 处），口径容易漂移 —— 统一到这里。
    """
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    return d.replace(tzinfo=_BJ_TZ) if d.tzinfo is None else d.astimezone(_BJ_TZ)


def _first_seen_iso(entry):
    """first_seen（我方首次收录该链接的时刻）的 ISO 形式，解析失败返回空串。"""
    d = _parse_hist_dt(entry.get("first_seen"))
    return d.isoformat() if d else ""


def _load_pub_date_offsets(sources=None):
    """读取源配置里**声明**的 pub_date 时区校正量（单位：分钟；负值 = 把 pub_date 往前挪）。

    为什么是声明式而非自动推断：物理约束（我们不可能在文章发布前抓到它）只能给出
    偏移的**下界** `need = max(first_seen - pub_date)`，而满足下界的合法时区偏移往往不止一个。
    实测超能网 need = 444.7min 时，480 / 525 / 570min 全都物理可行 —— 统计上无法唯一确定。
    按「最小候选」猜会静默改写日期，属于数据污染风险，故改由配置显式声明；
    自动检测降级为**发现器**（见 _detect_pub_date_anomalies），只报告不落库。
    """
    out = {}
    for s in (sources if sources is not None else RSS_SOURCES):
        if not isinstance(s, dict):
            continue
        try:
            v = int(s.get("pub_date_offset_min") or 0)
        except (TypeError, ValueError):
            continue
        if v:
            out[s.get("key")] = v
    return out


def _shift_iso_minutes(iso_str, minutes):
    """把 ISO 时间串按分钟平移（负值 = 往前）。解析失败原样返回（不制造新数据）。"""
    d = _parse_hist_dt(iso_str)
    if d is None:
        return iso_str
    return (d + datetime.timedelta(minutes=minutes)).isoformat()


def _effective_pub_dt(item, offsets=None):
    """条目**校正后**的发布时间（北京时间 aware）。声明了偏移的源按偏移平移。

    合并 / 72h 裁剪 / 审计 / 输出四处都必须用本函数，否则会出现多套口径
    （2026-09-14：构建期切块曾用字符串比较、审计用时区安全比较，导致选片错位）。
    """
    d = _parse_hist_dt(item.get("pub_date"))
    if d is None:
        return None
    off = (offsets if offsets is not None else _load_pub_date_offsets()).get(item.get("source_key"))
    if off:
        d = d + datetime.timedelta(minutes=off)
    return d


# pub_date 晚于 first_seen 超过该阈值 → 判为「已被证伪」。
# 容忍 1 小时两端时钟漂移；超过即说明我们「在文章发布之前抓到了它」，物理上不可能。
FUTURE_DATE_TOLERANCE_MIN = 60


def _pub_date_falsified(entry, offsets=None):
    """pub_date 是否已被物理事实证伪（晚于 first_seen 超过容忍阈值）。

    注意与「无 pub_date」区分：那是缺失，走既有降级路径；
    这里是**有一个明确错误的值**，不能拿来排序（否则条目「出生于未来」，
    前端钳制会把多条折叠成同一时刻 → 整块钉在首屏顶部）。
    """
    fs = _parse_hist_dt(entry.get("first_seen"))
    pd = _effective_pub_dt(entry, offsets)
    if fs is None or pd is None:
        return False
    return (pd - fs) > datetime.timedelta(minutes=FUTURE_DATE_TOLERANCE_MIN)


def _plan_falsify_shifts(history, offsets=None, src_keys=None):
    """为「将被证伪、须改用收录时刻」的条目规划保序回拉位移量（分钟，<=0），返回 {link: shift}。

    为什么不能统统写成同一个 first_seen：
      first_seen 是我方**按抓取批次**打的时间戳 —— 实测全量历史 8411 条只有 122 个取值，
      最大一个批次覆盖 1857 条。把一批被判伪的条目统统赋成同一个 first_seen，
      这一批就退化成「同一时刻」；前端按时间降序排完就是一大块同源同刻卡片，
      与 2026-09-14 用户报告的「同刻扎堆」是同一形态（只是源从超能网换成了 arxiv/product_hunt）。
      实测：60min 阈值下 101 条判伪里有 68 条落在「同批次多条」上，最大单组 27 条
      （arxiv_ai_4）、次大 24 条（product_hunt_797）——即一次修好、一次又造出来。

    对策（与前端 L3 钳制同一语义：**保序回拉**，不是折叠）：
      保留 feed 自身的相对先后（若干条目间的声称时间差是有信息的），整批后移，
      使**最新的一条**恰好落在 first_seen，其余按其原间隔往前排开。
    边界：
      · 只处理「有 pub_date 且被证伪」的条目；本来就无日期者没有相对信息，保持原行为；
      · 任何一条都不得早于 cutoff —— 72h 窗口是用户可见契约，不允许被位移越界。
    """
    groups = {}
    for link, item in history.items():
        sk = item.get("source_key")
        if src_keys is not None and sk not in src_keys:
            continue
        if not item.get("pub_date"):
            continue
        fs = _parse_hist_dt(item.get("first_seen"))
        if fs is None or not _pub_date_falsified(item, offsets):
            continue
        pd = _effective_pub_dt(item, offsets)
        groups.setdefault((sk, item.get("first_seen") or ""), []).append(
            (link, (pd - fs).total_seconds() / 60.0))

    shifts = {}
    for arr in groups.values():
        newest_adv = max(a for _l, a in arr)   # 组内最「未来」的那条 → 锚到 first_seen
        for link, adv in arr:
            shifts[link] = -int(round(newest_adv - adv))
    return shifts


def _detect_pub_date_anomalies(history, offsets=None):
    """发现器：找出「pub_date 系统性晚于 first_seen」的源，只报告不修改数据。

    返回 [{key, n, inverted_ratio, min_delta_min, median_delta_min, need_min, kind, suggest_min}]：
      kind='tz'    → 物理可行的最小前移量落在真实时区范围内 ⇒ 可能是时区标注错误，
                     suggest_min 给出最小的合法候选（供人工确认后写进源配置）
      kind='other' → 需要前移几十小时，远超任何真实时区 ⇒ 不是时区问题
                     （典型是播客/Newsletter 的「预约发布」，或源侧日期本身错乱），不给建议

    为什么只报告不落库：见 _load_pub_date_offsets 的说明（物理约束只给下界，可能多解）。
    """
    buckets = {}
    for item in history.values():
        sk = item.get("source_key")
        pd = _effective_pub_dt(item, offsets)
        fs = _parse_hist_dt(item.get("first_seen"))
        if not sk or pd is None or fs is None:
            continue
        buckets.setdefault(sk, []).append((fs - pd).total_seconds() / 60.0)

    out = []
    for sk, deltas in buckets.items():
        if sk in (offsets or {}) or len(deltas) < TZ_ANOMALY_MIN_ITEMS:
            continue
        inverted = sum(1 for d in deltas if d < -10)
        ratio = inverted / float(len(deltas))
        if ratio < TZ_ANOMALY_INVERT_RATIO:
            continue
        srt = sorted(deltas)
        need = -srt[0]
        kind, suggest = "other", None
        if need <= TZ_MAX_OFFSET_MIN:
            cands = [c for c in _TZ_LEGAL_OFFSETS_MIN if c >= need - 1e-9]
            if cands:
                kind, suggest = "tz", -cands[0]
        out.append({
            "key": sk, "n": len(deltas), "inverted_ratio": ratio,
            "min_delta_min": srt[0], "median_delta_min": srt[len(srt) // 2],
            "need_min": need, "kind": kind, "suggest_min": suggest,
        })
    out.sort(key=lambda x: -x["n"])
    return out


TZ_ANOMALY_MIN_ITEMS = 8       # 少于此条数不足以判断「系统性」
TZ_ANOMALY_INVERT_RATIO = 0.9  # 倒挂率门槛（arxiv 51.7% / product_hunt 80% 均被排除）
TZ_MAX_OFFSET_MIN = 840        # +14:00 是现实中最大的 UTC 偏移；超过即不可能是时区标注错误
# 现实在用的 UTC 偏移（分钟）。不能只取「任何 0.5h 倍数」：+7:30 已无地区使用，
# 若把它列进候选，「最小候选」规则会把 超能网 的 8h 误判成 7.5h。
_TZ_LEGAL_OFFSETS_MIN = tuple(sorted(set(
    [h * 60 for h in range(-12, 15)] + [330, 345, 390, 525, 570, 630, 765, -210, -570])))


def _fallback_date_iso(entry):
    """条目拿不到 pub_date 时的降级排序键 = first_seen（我方首次收录该链接的真实时刻）。

    为什么必须给一个键：空 pub_date 会让条目在默认排序里沉底 → 用户永远看不到
    （2026-09-14 实测：201 条因此不可见）。降级键只负责「让它按时间参与排序」，
    语义上不等于发布时间，因此调用方需用 date_fallback 标记，前端据此外显区分。
    """
    if entry.get("pub_date"):
        return ""
    return _first_seen_iso(entry)


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

def _detect_lang(text):
    """检测文本主要语言，返回 MyMemory langpair 代码。"""
    hiragana = sum(1 for c in text if '\u3040' <= c <= '\u309f')
    katakana = sum(1 for c in text if '\u30a0' <= c <= '\u30ff')
    hangul = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
    arabic = sum(1 for c in text if '\u0600' <= c <= '\u06ff')
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    total = max(len(text), 1)
    if (hiragana + katakana) / total > 0.1:
        return 'ja'
    if hangul / total > 0.1:
        return 'ko'
    if arabic / total > 0.1:
        return 'ar'
    if cyrillic / total > 0.1:
        return 'ru'
    if latin / total > 0.3:
        return 'en'
    return 'zh-CN'


def _agnes_translate(text, timeout=20):
    """Agnes AI 翻译（OpenAI 兼容接口，agnes-2.5-flash）。失败返回 None。"""
    global _AGNES_BLOCK_UNTIL, _AGNES_OFFENSES, _AGNES_EMPTY_STREAK
    payload = json.dumps({
        "model": "agnes-2.5-flash",
        "messages": [
            {"role": "system", "content": "你是翻译引擎。把用户输入翻译成简体中文，只输出译文，不要解释。"},
            {"role": "user", "content": text[:1500]},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
        # 思考型模型：关闭思考避免 token 被推理耗尽，也加速响应
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://apihub.agnes-ai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + _AGNES_KEY,
            "User-Agent": "starhub-auto-update",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or None
        with _TRANS_LOCK:
            if out:
                _AGNES_OFFENSES = 0
                _AGNES_EMPTY_STREAK = 0
            else:
                # 200 但空 content（模型对特定输入的拒绝/截断）：连续 3 次视为端点异常入罚期
                _AGNES_EMPTY_STREAK += 1
                empty_hit = _AGNES_EMPTY_STREAK >= _AGNES_EMPTY_LIMIT
                if empty_hit and _AGNES_BLOCK_UNTIL <= time.time():
                    block_s = min(300 * (2 ** _AGNES_OFFENSES), 3600)
                    _AGNES_BLOCK_UNTIL = time.time() + block_s
                    _AGNES_OFFENSES += 1
                    _AGNES_EMPTY_STREAK = 0
                    print("[翻译] Agnes 连续 %d 次空响应，暂停直连 %d 分钟" % (_AGNES_EMPTY_LIMIT, block_s // 60), file=sys.stderr)
        return out
    except urllib.error.HTTPError as e:
        # 对齐 Zen Z1 语义：任何 HTTP 错误都入账本（429 限流 / 401/403 key 问题 / 5xx 上游故障），
        # 锁内幂等——同波并发失败只记一次违规，罚期不被并发覆盖翻倍
        with _TRANS_LOCK:
            if _AGNES_BLOCK_UNTIL > time.time():
                return None
            block_s = min(300 * (2 ** _AGNES_OFFENSES), 3600)
            _AGNES_BLOCK_UNTIL = time.time() + block_s
            _AGNES_OFFENSES += 1
            print("[翻译] Agnes HTTP %d，暂停直连 %d 分钟" % (e.code, block_s // 60), file=sys.stderr)
        return None
    except Exception:
        return None


def _zen_call_model(text, model, timeout, auth):
    """单模型单鉴权调用。返回 (译文|None, 是否自封该模型, 是否鉴权类失败 401/403)。"""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是翻译引擎。把用户输入翻译成简体中文，只输出译文，不要解释。"},
            {"role": "user", "content": text[:1500]},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(_ZEN_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + auth,
        # 免费档要求 OpenCode 客户端身份，session/request 为每次调用生成的唯一 ID
        "User-Agent": "opencode/1.15.0 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
        "x-opencode-client": "cli",
        "x-opencode-project": "global",
        "x-opencode-request": "msg_" + uuid.uuid4().hex,
        "x-opencode-session": "ses_" + uuid.uuid4().hex,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or None
        if out:
            with _TRANS_LOCK:
                _ZEN_TIMEOUT_STREAK[model] = 0
                _ZEN_MODEL_OFFENSES[model] = 0
            return out, False, False
        # HTTP 200 但空 content：与超时同账本，连续 2 次自封（防恒空模型零成本占用全池轮询）
        with _TRANS_LOCK:
            _ZEN_TIMEOUT_STREAK[model] = _ZEN_TIMEOUT_STREAK.get(model, 0) + 1
            streak = _ZEN_TIMEOUT_STREAK[model]
        return None, streak >= 2, False
    except urllib.error.HTTPError as e:
        # 任何 HTTP 错误都自封该模型（401/403=key 不被接受，429=限流，5xx=故障），避免逐文本反复撞墙
        return None, True, e.code in (401, 403)
    except Exception:
        # 超时/网络故障不计 HTTP 错误，但连续挂起同样拖死管线：连续 2 次自封该模型
        with _TRANS_LOCK:
            _ZEN_TIMEOUT_STREAK[model] = _ZEN_TIMEOUT_STREAK.get(model, 0) + 1
            streak = _ZEN_TIMEOUT_STREAK[model]
        return None, streak >= 2, False


def _zen_translate(text, timeout=25):
    """OpenCode Zen 免费模型轮询翻译：游标挑一个未自封的模型，HTTP 错误/连续超时自封该模型
    （指数退避 5→10→20→40 分钟封顶 1h，成功清零）并切换下一个；个人 key 撞 401/403 时
    当场回退 Bearer public 并粘性记住。全部自封返回 None。"""
    global _ZEN_MODEL_IDX, _ZEN_AUTH_STICKY
    with _TRANS_LOCK:
        auth = _ZEN_AUTH_STICKY
    fallback_auth = None
    if not auth:
        auth = _ZEN_KEY or "public"
        fallback_auth = "public" if auth != "public" else None
    for _attempt in range(len(_ZEN_MODELS)):
        model = None
        with _TRANS_LOCK:
            for _k in range(len(_ZEN_MODELS)):
                cand = _ZEN_MODELS[_ZEN_MODEL_IDX % len(_ZEN_MODELS)]
                _ZEN_MODEL_IDX += 1
                if _ZEN_MODEL_BLOCK.get(cand, 0) <= time.time():
                    model = cand
                    break
        if model is None:
            return None
        out, to_block, auth_fail = _zen_call_model(text, model, timeout, auth)
        if auth_fail and fallback_auth and not out:
            out, to_block, auth_fail = _zen_call_model(text, model, timeout, fallback_auth)
            if out:
                with _TRANS_LOCK:
                    _ZEN_AUTH_STICKY = fallback_auth
                print("[翻译] Zen key 被拒，粘性回退 Bearer public", file=sys.stderr)
        if out:
            return out
        if to_block:
            with _TRANS_LOCK:
                if _ZEN_MODEL_BLOCK.get(model, 0) > time.time():
                    pass  # 已在罚期内：同波并发失败只记一次违规（P1 竞态修复）
                else:
                    offenses = _ZEN_MODEL_OFFENSES.get(model, 0)
                    block_s = min(300 * (2 ** offenses), 3600)
                    _ZEN_MODEL_BLOCK[model] = time.time() + block_s
                    _ZEN_TIMEOUT_STREAK[model] = 0
                    _ZEN_MODEL_OFFENSES[model] = offenses + 1
                    print("[翻译] Zen %s 限流/故障，自封 %d 分钟并切换下一模型" % (model, block_s // 60), file=sys.stderr)
    return None


def _translate_to_zh(text, timeout=TRANSLATE_TIMEOUT):
    """翻译降级链：Agnes → Google gtx → Zen 免费模型轮询 → MyMemory → dict-chrome（带缓存+熔断）。"""
    if not text:
        return ""
    # 先清理 HTML 标签
    text = _strip_html(text)
    if not text:
        return ""
    # 如果已经是中文为主，跳过（但需排除日文：含平假名/片假名的文本是日文而非中文）
    has_kana = any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text)
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if not has_kana and cn_chars > len(text) * 0.3:
        _TRANS_STATS["skip"] += 1
        return text

    # 查缓存（使用 MD5 确保跨进程一致性）
    text_hash = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
    if text_hash in _trans_cache:
        _TRANS_STATS["cache_hit"] += 1
        return _trans_cache[text_hash]

    # 熔断：连续多次全端点失败后暂停请求，期间未命中缓存的文本直接返回原文
    global _TRANS_FAIL_STREAK, _TRANS_BLOCK_UNTIL
    if time.time() < _TRANS_BLOCK_UNTIL:
        _TRANS_STATS["fail"] += 1
        return text

    encoded = urllib.parse.quote(text[:500])

    # 0) Agnes AI（首选，免费但限流：429 后暂停直连，期间直接走后续端点）
    if _AGNES_KEY and time.time() >= _AGNES_BLOCK_UNTIL:
        try:
            cand = _agnes_translate(text, timeout=timeout)
            if cand and len(cand) > len(text) * 0.2:
                _TRANS_STATS["agnes"] += 1
                _TRANS_FAIL_STREAK = 0
                _trans_cache[text_hash] = cand  # 写入缓存
                return cand
        except Exception:
            pass

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
                _TRANS_FAIL_STREAK = 0
                _trans_cache[text_hash] = result  # 写入缓存
                return result
    except Exception:
        pass

    # 1.5) OpenCode Zen 免费模型轮询（gtx 限流时的接力；单模型 429/5xx 自封 5 分钟并自动切换）
    try:
        cand = _zen_translate(text, timeout=25)
        if cand and len(cand) > len(text) * 0.2:
            _TRANS_STATS["zen"] += 1
            _TRANS_FAIL_STREAK = 0
            _trans_cache[text_hash] = cand  # 写入缓存
            return cand
    except Exception:
        pass

    # 2) MyMemory（自动检测源语言，避免硬编码 en 导致非英语源翻译质量差）
    try:
        src_lang = _detect_lang(text)
        url = "https://api.mymemory.translated.net/get?q=" + encoded + "&langpair=%s|zh-CN" % src_lang
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        result = data.get("responseData", {}).get("translatedText", "")
        if result and not result.startswith("MYMEMORY"):
            _TRANS_STATS["mymemory"] += 1
            _TRANS_FAIL_STREAK = 0
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
                _TRANS_FAIL_STREAK = 0
                _trans_cache[text_hash] = result  # 写入缓存
                return result
    except Exception:
        pass

    _TRANS_STATS["fail"] += 1
    with _TRANS_LOCK:
        _TRANS_FAIL_STREAK += 1
        if _TRANS_FAIL_STREAK >= 5:
            _TRANS_BLOCK_UNTIL = time.time() + 300
            print("[翻译熔断] 连续 %d 次全端点失败，暂停翻译请求 5 分钟" % _TRANS_FAIL_STREAK, file=sys.stderr)
    return text  # 翻译失败保留原文


def _translate_source_items(items):
    """翻译单个源的全部条目（在翻译线程池中执行）：仅翻译标题，摘要保留原文。附相对时间与 ISO 日期。"""
    for it in items:
        it["title_zh"] = _translate_to_zh(it["title"]) if it["title"] else it["title"]
        # 摘要不再构建时翻译，前端按需走浏览器 GTX
        it["time_str"] = _fmt_rel_time(it.get("pub_date"))
        # 保留 pub_date 用于前端时间线排序（转为 ISO 字符串）
        pd = it.get("pub_date")
        if pd and hasattr(pd, "isoformat"):
            it["pub_date"] = pd.isoformat()


# ──────────────────────────── RSS 抓取 ────────────────────────────

def _dedup_source_items(items, source_key):
    """单源内去重：URL 归一化 + 内容重复检测。

    处理三类重复：
    1. V2EX #replyN 锚点（同一帖子多回复）
    2. 微信公众号重复群发（同 __biz + 标题 + 摘要，不同 mid/sn）
    3. 通用 URL 变体（tracking 参数、fragment）

    微信公众号策略：标题+摘要都相同才视为重复（避免误删每日专栏）。
    其他源策略：标题归一化去重（48h 窗口保护每日专栏）。
    """
    if len(items) < 2:
        return items

    orig_count = len(items)

    # ── Pass 1: URL 归一化 ──
    for it in items:
        link = it.get("link", "")
        # V2EX: 剥离 #replyN
        if "v2ex" in source_key:
            link = re.sub(r"#reply\d+$", "", link)
        # 通用: 剥离尾部 fragment 和常见 tracking 参数
        link = re.sub(r"#(?!reply\d+$)[^#]*$", "", link)
        link = re.sub(r"[?&](utm_source|utm_medium|utm_campaign|utm_content|at_medium|at_campaign)=[^&]*", "", link)
        link = re.sub(r"[?&]$", "", link)
        it["link"] = link

    # ── Pass 2: 完全相同 URL 去重（保留首条）──
    seen_urls = {}
    url_deduped = []
    for it in items:
        link = it.get("link", "")
        if link and link in seen_urls:
            continue
        if link:
            seen_urls[link] = True
        url_deduped.append(it)
    items = url_deduped

    # ── Pass 3: 内容去重 ──
    # 检测是否微信源
    is_wechat = any("mp.weixin.qq.com" in (it.get("link", "") or "") for it in items[:5])

    def _norm_text(t):
        """归一化文本：去空白、小写、去标点"""
        t = re.sub(r"\s+", "", t).lower()
        t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
        return t[:80]

    def _wechat_biz(link):
        m = re.search(r"__biz=([A-Za-z0-9=]+)", link)
        return m.group(1) if m else ""

    if is_wechat:
        # 微信策略：标题+摘要都相同才视为重复
        seen_content = {}  # key → True
        content_deduped = []
        for it in items:
            title = (it.get("title") or "").strip()
            summary = (it.get("summary") or "").strip()
            link = it.get("link", "")

            if not title:
                content_deduped.append(it)
                continue

            # 去重键：__biz + 归一化标题 + 归一化摘要
            dedup_key = _wechat_biz(link) + "|" + _norm_text(title) + "|" + _norm_text(summary)

            if dedup_key in seen_content:
                continue  # 标题+摘要都相同，真重复

            seen_content[dedup_key] = True
            content_deduped.append(it)
        items = content_deduped
    else:
        # 其他源：标题归一化去重（48h 窗口保护）
        def _norm_title(t):
            t = re.sub(r"\s+", "", t).lower()
            t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
            return t[:50]

        seen_titles = {}  # key → pub_date
        title_deduped = []
        for it in items:
            title = (it.get("title") or "").strip()
            if not title:
                title_deduped.append(it)
                continue

            pub_date = it.get("pub_date", "")
            dedup_key = _norm_title(title)

            if dedup_key in seen_titles:
                prev_date = seen_titles[dedup_key]
                if pub_date and prev_date:
                    try:
                        pd_cur = datetime.datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        pd_prev = datetime.datetime.fromisoformat(prev_date.replace("Z", "+00:00"))
                        diff_hours = abs((pd_cur - pd_prev).total_seconds()) / 3600
                        if diff_hours > 48:
                            title_deduped.append(it)
                            seen_titles[dedup_key] = pub_date
                            continue
                    except (ValueError, AttributeError):
                        pass
                continue

            seen_titles[dedup_key] = pub_date
            title_deduped.append(it)
        items = title_deduped

    removed = orig_count - len(items)
    if removed > 0:
        print("[去重] %s: %d → %d 条（移除 %d 条重复）"
              % (source_key, orig_count, len(items), removed))

    return items


def _fetch_url(url, timeout=FETCH_TIMEOUT, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(5000000).decode("utf-8", errors="replace")


def _fetch_rss(source, timeout=None):
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
        raw = _fetch_url(url, timeout=timeout or FETCH_TIMEOUT, accept="application/rss+xml, application/xml, text/xml, application/atom+xml")
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
            summary_raw = e.findtext(ns + "summary") or ""
            desc = _strip_html(summary_raw)
            content_raw = e.findtext(ns + "content") or ""
            atom_content = _deep_clean_html(_sanitize_html(content_raw))
            full_content = atom_content if len(atom_content) > len(desc) else ""
            pub = e.findtext(ns + "updated") or e.findtext(ns + "published") or ""
            if not title or not link:
                continue
            media_url, media_type = _pick_item_media(e)
            items.append({
                "title": title, "link": link, "summary": _truncate(desc),
                "full_content": full_content, "image": _upgrade_img_url(_pick_item_image(e, summary_raw, content_raw)),
                "pub_date": _parse_iso(pub), "source": name, "source_key": source["key"],
                "cat": source["cat"],
                "media_url": media_url, "media_type": media_type,
            })
    else:
        ch = root.find("channel")
        rdf_ns = "{http://purl.org/rss/1.0/}"
        if ch is None and root.find(rdf_ns + "channel") is None:
            for it in root.findall(".//item"):
                _parse_rss_item(it, name, source["key"], source["cat"], items)
        elif ch is not None:
            for it in ch.findall("item"):
                _parse_rss_item(it, name, source["key"], source["cat"], items)
        else:
            # RSS 1.0 RDF format (e.g. DW)
            for it in root.findall(".//" + rdf_ns + "item"):
                _parse_rss_item(it, name, source["key"], source["cat"], items)

    # ── 通用去重阶段 ──
    items = _dedup_source_items(items, source["key"])

    # 写入缓存
    _rss_cache[key] = {
        "items": items[:ITEMS_PER_SOURCE],
        "fetched_at": time.time()
    }

    return items[:ITEMS_PER_SOURCE]


def _parse_rss_item(it, source_name, source_key, cat, items):
    title = _strip_html(it.findtext("title") or "")
    link = (it.findtext("link") or "").strip()
    # RSS 1.0 RDF: link is in rdf:about attribute
    if not link:
        link = (it.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or "").strip()
    desc_raw = it.findtext("description") or ""
    pub = (it.findtext("pubDate") or "").strip()
    # RSS 1.0 RDF: date is in dc:date
    if not pub:
        pub = (it.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
    dc_content = "{http://purl.org/rss/1.0/modules/content/}"
    content_raw = it.findtext(dc_content + "encoded") or ""
    if not title or not link:
        return
    media_url, media_type = _pick_item_media(it)
    # ── XGO (Twitter/X) 信源专门清洗 ──
    # xgo.ing 代理的 description 包含完整 HTML 卡片（推文正文 + 引用推文 +
    # 头像 + 互动数据 + 页脚），直接 _strip_html 会把所有噪音混入摘要。
    if _is_xgo_content(desc_raw):
        cleaned = _clean_xgo_content(desc_raw)
        desc = cleaned or _strip_html(desc_raw)
        full_content = ""  # 推文正文已在 desc 中，无需全文加载
        img = _extract_tweet_media(desc_raw)
    else:
        desc = _strip_html(desc_raw)
        content_encoded = _deep_clean_html(_sanitize_html(content_raw))
        full_content = content_encoded if len(content_encoded) > len(desc) else ""
        img = _upgrade_img_url(_pick_item_image(it, desc_raw, content_raw))
    items.append({
        "title": title, "link": link, "summary": _truncate(desc),
        "full_content": full_content, "image": img,
        "pub_date": _parse_rss_date(pub) or _parse_iso(pub), "source": source_name, "source_key": source_key,
        "cat": cat,
        "media_url": media_url, "media_type": media_type,
    })


# ──────────────────────────── HTML 生成 ────────────────────────────

def _build_css():
    return """
:root {
  --bg:#faf9f7; --card:#fffdf9; --card-2:#f3efe6; --card-3:#ebe6db;
  --ink:#1c1917; --muted:#5f594c; --faint:#6e685e; /* A4 修复：加深弱化灰至 ≥4.5:1 对比度 */
  --line:#ddd6c9; --line-strong:#b9b0a2;
  --brand:#2f5d8a; --brand-strong:#24496e; --brand-line:#b9cde0; --brand-weak:#e7eef4;
  --display:"Noto Serif SC","Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:"Noto Sans SC",-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"IBM Plex Mono","SF Mono","Fira Code","Consolas",monospace;
  --radius:8px;
  --shadow:0 1px 2px rgba(28,25,23,.05);
  --shadow-lift:0 10px 26px rgba(0,0,0,.10),0 2px 4px rgba(0,0,0,.06);
  --cat-tech:#2f5d8a; --cat-cn_tech:#c2434d; --cat-dev:#7052c9; --cat-ai:#b06a10; --cat-news:#8a6d1f; --cat-podcast:#2e7d5f; --cat-youtube:#e0245e;
  --unread:#177a37; --read-badge:#c0392b; /* A4 修复：未读绿加深至 ≥4.5:1 */
}
[data-theme="dark"] {
  --bg:#161412; --card:#1d1a17; --card-2:#262019; --card-3:#2f2820;
  --ink:#ece7df; --muted:#a59d90; --faint:#a8a090; /* A4 修复：暗色模式弱化灰加深 */
  --line:#37312a; --line-strong:#4a4339;
  --brand:#8fb3d9; --brand-strong:#b0cbe6; --brand-line:#3d5a78; --brand-weak:#22303f;
  --shadow:0 1px 2px rgba(0,0,0,.4);
  --shadow-lift:0 10px 26px rgba(0,0,0,.5),0 2px 4px rgba(0,0,0,.4);
  --cat-tech:#8fb3d9; --cat-cn_tech:#e08790; --cat-dev:#a894e8; --cat-ai:#d3a15c; --cat-news:#cbb26a; --cat-podcast:#6cba9c; --cat-youtube:#ff4d79;
  --unread:#3ddc78; --read-badge:#f87171; /* A4 修复：暗色未读绿微调 */
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
.back-top{position:fixed;bottom:24px;right:24px;width:40px;height:40px;border-radius:50%;background:var(--card);border:1px solid var(--line);color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:0;pointer-events:none;transition:all .2s;z-index:90;box-shadow:0 2px 8px rgba(0,0,0,.08);}
.back-top.show{opacity:1;pointer-events:auto;}
/* 抽屉面板打开时隐藏回到顶部按钮，避免浮在面板内容之上 */
body.ai-open .back-top{opacity:0;pointer-events:none;}
.back-top:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.back-top svg{width:18px;height:18px;}
.bm-btn{width:22px;height:22px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;color:var(--faint);border:1px solid transparent;transition:all .15s;cursor:pointer;background:none;padding:0;flex:none;position:relative;}
.bm-btn::after{content:'';position:absolute;inset:-5px;}
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
.chip.disc-chip{border-style:dashed;color:#0891b2;border-color:#0891b2;}
.chip.disc-chip.on{background:#ecfeff;border-color:#0891b2;color:#0e7490;}
@media(prefers-color-scheme:dark){.chip.disc-chip{color:#22d3ee;border-color:#22d3ee;}.chip.disc-chip.on{background:#164e63;border-color:#22d3ee;color:#67e8f9;}}
.chip .n { font-family:var(--mono); font-size:10px; opacity:.75; margin-left:3px; }
/* A2 修复：模态焦点可见环 */
[role="dialog"] :focus-visible,.share-modal :focus-visible{outline:2px solid var(--brand);outline-offset:2px;}
/* U6 修复：搜索信源匹配标签 */
.src-match-label{font-size:11px;color:var(--brand-strong);padding:2px 0 0 4px;font-weight:500;}
.fpill { display:inline-flex; align-items:center; gap:6px; padding:4px 6px 4px 12px; border-radius:999px; font-size:12px; font-weight:600; background:var(--ink); color:var(--bg); }
.fpill .x { width:16px; height:16px; border-radius:999px; background:rgba(255,255,255,.18); display:flex; align-items:center; justify-content:center; font-size:11px; cursor:pointer; }
.fpill .x:hover { background:rgba(255,255,255,.34); }
.tool-meta { margin-left:auto; font-family:var(--mono); font-size:11px; color:var(--faint); white-space:nowrap; }

/* ── Search row ── */
.search-row { max-width:1560px; margin:0 auto; padding:10px 20px 0; display:flex; align-items:center; gap:10px; }
.global-search { position:relative; flex:1; min-width:0; }
.global-search input { width:100%; padding:10px 36px 10px 16px; border-radius:12px; border:1.5px solid var(--line); background:var(--card); font-size:14px; color:var(--ink); font-family:var(--body); outline:none; transition:border-color .15s, box-shadow .15s; }
.global-search input:focus { border-color:var(--brand); box-shadow:0 0 0 3px var(--brand-weak); }
.global-search input:focus-visible { outline:2px solid var(--brand); outline-offset:1px; }
button:focus-visible, .chip:focus-visible, .card:focus-visible, a:focus-visible { outline:2px solid var(--brand); outline-offset:2px; border-radius:var(--radius); }
.global-search input::placeholder { color:var(--faint); font-size:13.5px; }
.global-search .sx { position:absolute; right:10px; top:50%; transform:translateY(-50%); width:22px; height:22px; border-radius:999px; background:var(--line); color:var(--muted); display:none; align-items:center; justify-content:center; font-size:11px; cursor:pointer; transition:all .15s; }
.global-search .sx:hover { background:var(--line-strong); color:var(--ink); }
.global-search.has-q .sx { display:flex; }
.global-search.has-q input { border-color:var(--brand-line); background:var(--brand-weak); }
.global-search.src-hit input { border-color:var(--brand-strong); background:var(--brand-weak); box-shadow:0 0 0 3px var(--brand-weak); }
.global-search.src-hit::after { content:'\u2316'; position:absolute; left:4px; top:50%; transform:translateY(-50%); font-size:14px; color:var(--brand-strong); pointer-events:none; }
.sort-select { padding:10px 32px 10px 14px; border-radius:12px; border:1.5px solid var(--line); background:var(--card); font-size:13px; font-weight:500; color:var(--muted); font-family:var(--body); outline:none; cursor:pointer; transition:border-color .15s; appearance:none; -webkit-appearance:none; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23857e74' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 10px center; flex:none; }
.sort-select:hover { border-color:var(--brand-line); }
.sort-select:focus { border-color:var(--brand); box-shadow:0 0 0 3px var(--brand-weak); }

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
.ext-btn { flex:none; width:22px; height:22px; border-radius:6px; display:flex; align-items:center; justify-content:center; color:var(--faint); border:1px solid transparent; transition:all .15s; position:relative; }
.ext-btn::after { content:''; position:absolute; inset:-5px; }
.ext-btn:hover { color:var(--brand-strong); border-color:var(--brand-line); background:var(--brand-weak); }
.ext-btn svg { width:11px; height:11px; }
.card-title { font-family:var(--display); font-size:15.5px; font-weight:700; line-height:1.45; margin-bottom:7px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; color:var(--unread); transition:color .15s; }
.card:hover .card-title { color:var(--brand-strong); }
.card-summary { font-size:12.5px; color:var(--muted); line-height:1.7; display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }
.card-tags { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
.ctag { font-size:10px; color:var(--brand); background:color-mix(in srgb, var(--brand) 10%, transparent); border-radius:4px; padding:1px 6px; line-height:1.6; white-space:nowrap; }
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

/* ── 封面卡：上图片 / 标题 / 内容介绍（无图降级为分类色渐变 + 首字） ── */
.card.cover-card { padding:0; overflow:hidden; }
.cover-card .cover { display:block; position:relative; height:var(--cover-h,150px); background:var(--card-2); border-bottom:1px solid var(--line); }
.cover-card .cover-img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; display:block; transition:transform .25s ease; }
.cover-card .cover-fallback { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-family:var(--display); font-size:40px; font-weight:700; color:#fff; background:linear-gradient(135deg, var(--cc), color-mix(in srgb, var(--cc) 45%, #191919)); }
@supports not (background:color-mix(in srgb, red, blue)) { .cover-card .cover-fallback { background:var(--cc); } }
.cover-card .card-top { margin:0; padding:10px 13px 0; }
.cover-card .card-title { margin:8px 13px 0; }
.cover-card .card-summary { margin:6px 13px 0; }
.cover-card .card-foot { margin:10px 13px 0; padding:9px 0 12px; }
.cover-card.visited { border-left:3px solid var(--line-strong); }
.cover-card.visited .cover-img, .cover-card.visited .cover-fallback { opacity:.55; }
@media (hover:hover) and (pointer:fine) { .cover-card:hover .cover-img { transform:scale(1.04); } }
[data-theme="dark"] .cover-card .cover-img { filter:brightness(.88) saturate(.92); }
@media (max-width:640px) { .cover-card .cover { height:118px; } }


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
.r2-close { display:flex; align-items:center; justify-content:center; width:30px; height:30px; border-radius:999px; border:1px solid transparent; color:var(--muted); transition:all .15s; flex:none; }
.r2-close:hover { color:var(--read-badge); border-color:var(--line); background:var(--bg); }
.r2-close svg { width:14px; height:14px; }
.r2-src { display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted); min-width:0; }
.r2-src .src-dot { width:9px; height:9px; }
.r2-src b { color:var(--ink); font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.r2-acts { margin-left:auto; display:flex; align-items:center; gap:8px; }
.r2-open { display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600; color:var(--brand-strong); background:var(--brand-weak); border:1px solid var(--brand-line); padding:4px 12px; border-radius:8px; white-space:nowrap; transition:all .15s; }
.r2-open:hover { background:var(--brand-strong); color:#fff; }
.r2-body { flex:1; min-height:0; overflow-y:auto; -webkit-overflow-scrolling:touch; }
.r2-body.fs-sm .r2-summary { font-size:13.5px; }
.r2-body.fs-md .r2-summary { font-size:15px; }
.r2-body.fs-lg .r2-summary { font-size:17.5px; }
.r2-body.fs-sm .r2-title { font-size:20px; }
.r2-body.fs-lg .r2-title { font-size:26px; }
.r2-body.fs-sm .r2-fulltext { font-size:13.5px; }
.r2-body.fs-lg .r2-fulltext { font-size:17.5px; }
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
  .search-row { padding:8px 14px 0; }
  .wall-wrap { padding:12px 14px 50px; }
  .wall { columns:2 260px; }
  .r2-inner { padding:22px 20px 70px; }
  .tool-meta { display:none; }
  .build-bar { padding:2px 14px 6px; }
}
@media (max-width:700px) {
  .hd .nav-links a { padding:5px 9px; font-size:12px; }
  .chips { overflow-x:auto; flex-wrap:nowrap; max-width:100%; padding-bottom:4px; scroll-snap-type:x proximity; -webkit-mask-image:linear-gradient(to right,#000 90%,transparent 100%); mask-image:linear-gradient(to right,#000 90%,transparent 100%); }
  .chip { white-space:nowrap; flex:none; scroll-snap-align:start; }
  .search-row { flex-wrap:wrap; }
  .sort-select { flex:0 0 auto; min-width:0; padding:6px 22px 6px 8px; font-size:12px; background-position:right 6px center; }
  .wall { columns:1 minmax(0,1fr); }
  .reader2 { width:96vw; max-height:92vh; border-radius:12px; }
  .r2-top { padding:8px 10px; gap:8px; }
  /* 移动端工具栏：统一控件高度 28px，防溢出挤压变形 */
  .r2-close, .r2-bm, .r2-open { height:28px; flex:none; align-items:center; }
  .r2-close { width:28px; height:28px; }
  .r2-fs-btn { width:28px; height:28px; }
  .r2-fs-btns { margin-right:0; }
  .r2-src { flex:1; min-width:0; }
  .r2-src b { max-width:none; flex:0 1 auto; }
  .r2-src span:not(.src-dot) { display:none; } /* 隐藏 · 与绝对时间（正文中可见），源名弹性收缩 */
  .r2-open { padding:0 9px; }
  .r2-inner { padding:18px 16px 60px; }
  .r2-title { font-size:19px; }
  .r2-summary { font-size:14px; line-height:1.8; }
  .r2-summary p { margin-bottom:1em; }
}

/* ── Share button (card wall) ── */
.share-btn{flex:none;width:20px;height:20px;border-radius:6px;display:flex;align-items:center;justify-content:center;color:var(--brand);border:1px solid transparent;transition:all .15s;background:none;cursor:pointer;padding:0;position:relative;}
.share-btn::after{content:'';position:absolute;inset:-6px;}
.share-btn:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.share-btn.loading{pointer-events:none;opacity:.5;}
.share-btn svg{width:13px;height:13px;}
.copy-btn{display:inline-flex;align-items:center;gap:4px;color:var(--faint);font-size:11px;background:none;border:none;cursor:pointer;padding:2px 4px;border-radius:4px;font-family:var(--mono);transition:all .15s;}
.copy-btn:hover{color:var(--brand-strong);background:var(--brand-weak);}
.copy-btn svg{width:12px;height:12px;}

/* ── Share action bar (reader body bottom) ── */
.r2-actions-bottom{display:flex;justify-content:center;padding:22px 0 4px;}
.r2-share-btn{display:inline-flex;align-items:center;gap:8px;padding:9px 20px;border-radius:999px;font-size:13px;font-weight:600;border:1px solid var(--brand-line);background:var(--brand-weak);color:var(--brand-strong);cursor:pointer;transition:all .15s;}
.r2-share-btn:hover{background:var(--brand-strong);color:#fff;border-color:var(--brand-strong);}
.r2-share-btn.loading{pointer-events:none;opacity:.6;}
.r2-share-btn svg{width:15px;height:15px;}

/* ── Share modal ── */
.share-modal{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;padding:16px;}
.share-modal.open{display:flex;}
.share-backdrop{position:absolute;inset:0;background:rgba(28,25,23,.55);}
/* 面板高度自适应内容且封顶视口（vh→dvh 双写兜底旧浏览器）：
   超出时图片区内部滚动（overflow-y:auto），头部/提示/按钮区 flex:none 恒定可见，长文分享不再截断操作按钮 */
.share-panel{position:relative;z-index:1;width:min(400px,90vw);max-height:calc(100vh - 32px);max-height:calc(100dvh - 32px);display:flex;flex-direction:column;overflow:hidden;background:var(--bg);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.25);padding:20px;text-align:center;}
.share-hd{flex:none;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}
.share-hd h3{font-family:var(--display);font-size:15px;font-weight:900;margin:0;}
.share-close{width:28px;height:28px;border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:16px;color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;}
.share-close:hover{border-color:var(--line-strong);color:var(--ink);}
.share-img-wrap{flex:0 1 auto;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch;border-radius:10px;border:1px solid var(--line);background:var(--card);}
.share-textcard{display:none;text-align:left;white-space:pre-wrap;word-break:break-word;background:var(--card);border:1px dashed var(--line-strong);border-radius:10px;padding:16px;font-size:13px;line-height:1.7;color:var(--ink);flex:0 1 auto;min-height:0;max-height:340px;overflow:auto;font-family:var(--body);}
.share-img-wrap img{width:100%;display:block;}
.share-hint{flex:none;font-size:12px;color:var(--faint);margin:12px 0 14px;}
.share-actions{flex:none;display:flex;flex-wrap:wrap;gap:10px;justify-content:center;}
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
.boot-loading{display:flex;align-items:center;justify-content:center;gap:10px;padding:72px 16px;color:var(--muted);font-size:13px;}
.boot-spin{width:18px;height:18px;border:2px solid var(--line);border-top-color:var(--brand);border-radius:50%;animation:bootspin .8s linear infinite;}
@keyframes bootspin{to{transform:rotate(360deg)}}

/* ── AI Feed button (toolbar) ── */
.ai-feed-btn{display:inline-flex;align-items:center;gap:5px;padding:4px 13px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--brand-line);background:var(--brand-weak);color:var(--brand-strong);transition:all .15s;cursor:pointer;}
.ai-feed-btn:hover{background:var(--brand-strong);color:#fff;}
.ai-feed-btn.on{background:var(--brand-strong);color:#fff;}
.ai-feed-btn svg{width:13px;height:13px;}

/* ── AI Feed panel (right side drawer) ── */
.ai-feed-panel{position:fixed;top:0;right:0;bottom:0;width:min(400px,92vw);z-index:95;background:var(--card);border-left:1px solid var(--line);transform:translateX(103%);transition:transform .28s cubic-bezier(.32,.72,.28,1);display:flex;flex-direction:column;box-shadow:-18px 0 50px rgba(0,0,0,.12);}
body.ai-open .ai-feed-panel{transform:none;}
body.ai-open .scrim{opacity:1;pointer-events:auto;}
.af-head{flex:none;padding:14px 16px 10px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;}
/* ── 面板主 Tab：AI 快讯 / 全网热榜（选中态用 --ink/--bg 反转对，明暗主题下文字均保证可读） ── */
.af-tabs{flex:1;display:flex;gap:5px;min-width:0;}
.af-tab{flex:1;max-width:132px;height:30px;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--muted);font-size:12.5px;font-weight:600;font-family:inherit;cursor:pointer;transition:all .15s;white-space:nowrap;}
.af-tab:hover{border-color:var(--line-strong);color:var(--ink);}
.af-tab.on{background:var(--ink);border-color:var(--ink);color:var(--bg);}
/* Tab 内容切换：默认显示 AI 快讯区；body.af-tab-hot 时热榜区接管面板。
   overflow:hidden 兜底：内容超出时由 hp-body 内部滚动，绝不溢出面板可视区 */
.hp-wrap{display:none;flex-direction:column;flex:1;min-height:0;overflow:hidden;}
body.af-tab-hot .hp-wrap{display:flex;}
body.af-tab-hot .af-sub,body.af-tab-hot .af-filter,body.af-tab-hot .af-body,body.af-tab-hot .af-more{display:none!important;}
.af-close{width:26px;height:26px;border-radius:999px;border:1px solid var(--line);display:flex;align-items:center;justify-content:center;color:var(--muted);transition:all .15s;flex:none;}
.af-close:hover{border-color:var(--line-strong);color:var(--ink);}
.af-close svg{width:12px;height:12px;}
.af-refresh{width:26px;height:26px;border-radius:999px;border:1px solid var(--line);display:flex;align-items:center;justify-content:center;color:var(--muted);transition:all .15s;flex:none;cursor:pointer;background:transparent;}
.af-refresh:hover{border-color:var(--line-strong);color:var(--ink);}
.af-refresh.loading{pointer-events:none;opacity:.7;}
.af-refresh.loading svg{animation:spin 1s linear infinite;}
.af-refresh svg{width:12px;height:12px;}
.af-sub{flex:none;padding:6px 16px;font-size:11px;color:var(--faint);font-family:var(--mono);border-bottom:1px solid var(--line);}
.af-filter{display:flex;flex-wrap:wrap;gap:5px;padding:8px 16px 4px;flex:none;}
.af-filter .fchip{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 8px;border:1px solid var(--line);border-radius:999px;background:transparent;font-size:11px;color:var(--muted);cursor:pointer;transition:all .15s;font-family:inherit;}
.af-filter .fchip:hover{border-color:var(--line-strong);color:var(--ink);}
.af-filter .fchip.on{background:var(--ink);border-color:var(--ink);color:var(--bg);font-weight:600;}
.af-filter .fchip .n{opacity:.6;font-family:var(--mono);font-size:10px;}
.af-body{flex:1;overflow-y:auto;padding:4px 16px 16px;-webkit-overflow-scrolling:touch;}
.af-item{display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px;min-width:0;}
.af-item:last-child{border-bottom:0;}
.af-item .cat{flex:none;margin-top:1px;height:16px;line-height:16px;padding:0 6px;border-radius:2px;font-size:10.5px;font-weight:600;white-space:nowrap;}
.af-item .body{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px;}
.af-item .t{color:var(--ink);font-weight:500;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.af-item .t:hover{color:var(--brand-strong);}
.af-item .meta{color:var(--faint);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:var(--mono);}
.af-share{flex:none;width:20px;height:20px;border-radius:6px;display:flex;align-items:center;justify-content:center;color:var(--faint);border:1px solid transparent;background:none;cursor:pointer;padding:0;margin-top:1px;transition:all .15s;}
.af-share:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.af-share.loading{pointer-events:none;opacity:.5;}
.af-share svg{width:12px;height:12px;}
.af-more{flex:none;margin:8px 16px;height:32px;border:1px dashed var(--line);border-radius:var(--radius);background:transparent;font-size:12px;color:var(--muted);cursor:pointer;transition:all .15s;font-family:var(--body);}
.af-more:hover{color:var(--brand-strong);border-color:var(--brand-line);background:var(--brand-weak);}
.af-more:disabled{opacity:.5;cursor:not-allowed;}
.af-empty{color:var(--faint);font-size:13px;text-align:center;padding:40px 16px;}
.af-loading{display:flex;align-items:center;justify-content:center;gap:8px;padding:40px 16px;color:var(--muted);font-size:13px;}
.af-spin{width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--brand);border-radius:50%;animation:bootspin .8s linear infinite;}

/* ── AI Feed 常驻侧栏（桌面 ≥1280px）：面板移入 .wall-wrap 左侧，sticky 常驻、独立滚动；<1280px 保持右侧抽屉 + 按钮切换 ── */
@media (min-width:1280px) {
  .wall-wrap { display:flex; align-items:flex-start; gap:14px; }
  .wall { flex:1; min-width:0; }
  .ai-feed-panel { position:sticky; top:58px; left:auto; right:auto; bottom:auto; transform:none; width:300px; flex:none; height:calc(100vh - 78px); z-index:auto; border-left:none; border-right:1px solid var(--line); box-shadow:none; }
  body.ai-open .ai-feed-panel { transform:none; }
  body.ai-open .scrim { opacity:0; pointer-events:none; }
  .af-close { display:none; }
  .ai-feed-btn { display:none; }
  .hot-btn { display:none; }
}

@media (max-width:700px) {
  .ai-feed-panel{width:100vw;}
  .af-head{padding:12px 14px 8px;}
  .af-body{padding:4px 14px 14px;}
}

/* ── Hot toolbar button（移动端快捷入口：打开 AI 面板并切到热榜 Tab；桌面端面板常驻后隐藏，直接点 Tab） ── */
.hot-btn{display:inline-flex;align-items:center;gap:5px;padding:4px 13px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid #f59e0b33;background:#f59e0b14;color:#b45309;transition:all .15s;cursor:pointer;}
.hot-btn:hover{background:#f59e0b;color:#fff;}
.hot-btn.on{background:#f59e0b;color:#fff;}
.hot-btn svg{width:13px;height:13px;}
.tb-divider{width:1px;height:16px;background:var(--line-strong);margin:0 4px;flex:none;}

/* ── 热榜内容区：维度分层（分类 + 平台）+ 卡片列表（WS-A） ── */
/* 维度行：行首标签 + 内容区 */
.dim-row{display:flex;align-items:flex-start;gap:8px;padding:10px 12px 0;}
.dim-label{flex:none;width:28px;font-size:10px;font-weight:700;color:var(--faint);letter-spacing:1px;padding-top:5px;user-select:none;}
.dim-body{flex:1;min-width:0;}
.dim-sep{border:none;border-top:1px solid var(--line);margin:10px 12px 0;}
/* 分类：分段控件（WS-A2） */
.hp-seg{display:inline-flex;flex-wrap:nowrap;overflow-x:auto;max-width:100%;background:var(--hover);border-radius:8px;padding:2px;gap:2px;scrollbar-width:none;}
.hp-seg::-webkit-scrollbar{display:none;}
.hp-seg-btn{flex:none;height:22px;padding:0 11px;border:none;border-radius:6px;background:transparent;color:var(--muted);font-size:11px;font-weight:600;transition:all .15s;white-space:nowrap;font-family:inherit;cursor:pointer;}
.hp-seg-btn:hover{color:var(--ink);}
.hp-seg-btn.on{background:var(--brand);color:#fff;box-shadow:0 1px 3px rgba(0,0,0,.15);}
/* 平台行：彩点 chips（WS-A3） */
.plat-wrap{display:flex;align-items:center;gap:6px;min-width:0;}
.plat-row{display:flex;flex-wrap:wrap;gap:5px;min-width:0;flex:1;}
.plat-chip{flex:none;height:24px;padding:0 10px;border:1px solid var(--line);border-radius:999px;background:var(--hover);color:var(--muted);font-size:11.5px;font-weight:600;display:inline-flex;align-items:center;gap:5px;transition:all .15s;white-space:nowrap;font-family:inherit;cursor:pointer;}
.plat-chip:hover{border-color:var(--line-strong);color:var(--ink);}
.plat-chip .dot{width:7px;height:7px;border-radius:50%;flex:none;}
.plat-chip.on{color:#fff;border-color:transparent;}
.plat-more{flex:none;height:24px;padding:0 10px;border:1px dashed var(--line-strong);border-radius:999px;background:transparent;color:var(--faint);font-size:11px;font-weight:600;display:none;align-items:center;gap:3px;white-space:nowrap;font-family:inherit;cursor:pointer;}
.plat-more:hover{color:var(--ink);border-color:var(--faint);}
.plat-more svg{width:10px;height:10px;transition:transform .2s;}
.plat-more.open svg{transform:rotate(180deg);}
/* 分类切换淡入动画（WS-A5） */
.hp-swap{animation:hpFade .18s ease;}
@keyframes hpFade{from{opacity:.2}to{opacity:1;}}
.hp-body{flex:1;overflow-y:auto;padding:8px 12px 16px;-webkit-overflow-scrolling:touch;}
.hp-item{display:flex;align-items:flex-start;gap:8px;padding:9px 10px;margin-bottom:6px;border:1px solid var(--line);border-radius:var(--radius);background:var(--bg);cursor:pointer;transition:all .12s;text-decoration:none;color:inherit;}
.hp-item:hover{border-color:var(--line-strong);background:var(--hover);}
.hp-rank{flex:none;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;font-family:var(--mono);background:var(--hover);color:var(--faint);}
.hp-rank.top3{background:var(--brand-weak);color:var(--brand-strong);}
.hp-title{flex:1;font-size:13px;line-height:1.5;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word;}
.hp-hot{flex:none;font-size:11px;color:var(--faint);font-family:var(--mono);margin-top:3px;}
.hp-empty{padding:40px 16px;text-align:center;color:var(--faint);font-size:13px;}
@media (max-width:900px){
  .plat-row.collapsed{flex-wrap:nowrap;overflow-x:auto;scroll-snap-type:x proximity;max-width:100%;-webkit-mask-image:linear-gradient(to right,#000 88%,transparent);mask-image:linear-gradient(to right,#000 88%,transparent);scrollbar-width:none;}
  .plat-row.collapsed::-webkit-scrollbar{display:none;}
  .plat-row.collapsed .plat-chip{scroll-snap-align:start;}
  .plat-wrap .plat-more{display:inline-flex;}
}
@media (max-width:700px) {
  .plat-row{padding:8px 0 2px;}
  .hp-body{padding:6px 10px 14px;}
  .dim-label{width:24px;}
}

/* ── Insight Panel（每日洞察面板 · WS-B 容器化） ── */
.insight-btn{display:inline-flex;align-items:center;gap:5px;padding:4px 13px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid #6366f133;background:#6366f114;color:#4338ca;transition:all .15s;cursor:pointer;}
.insight-btn:hover{background:#6366f1;color:#fff;}
.insight-btn.on{background:#6366f1;color:#fff;}
.insight-btn svg{width:13px;height:13px;}
/* 洞察面板：PC 右抽屉 / 移动底部 Sheet（同一组件） */
.insight-panel{position:fixed;z-index:70;background:var(--card);display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.14);visibility:hidden;}
@media (min-width:900px){
  .insight-panel{top:0;right:0;bottom:0;width:min(520px,92vw);border-left:1px solid var(--line);transform:translateX(100%);transition:transform .25s ease,visibility .25s;}
  .insight-panel.open{transform:none;visibility:visible;}
}
@media (max-width:899px){
  .insight-panel{left:0;right:0;bottom:0;max-height:88vh;border-radius:16px 16px 0 0;border-top:1px solid var(--line);transform:translateY(100%);transition:transform .25s ease,visibility .25s;}
  .insight-panel.open{transform:none;visibility:visible;}
}
.ip-head{display:flex;align-items:center;gap:8px;padding:14px 18px 10px;border-bottom:1px solid var(--line);flex:none;}
.ip-head h2{margin:0;font-size:15px;font-weight:800;display:flex;align-items:center;gap:7px;}
.ip-head h2 svg{width:16px;height:16px;color:var(--brand);}
.ip-gen{font-size:10.5px;color:var(--faint);font-family:var(--mono);}
.ip-close{margin-left:auto;background:none;border:none;color:var(--faint);padding:6px;border-radius:8px;cursor:pointer;transition:all .15s;}
.ip-close:hover{background:var(--hover);color:var(--ink);}
.ip-close svg{width:17px;height:17px;}
/* 锚点导航条（吸顶） */
.ip-nav{display:flex;gap:4px;padding:8px 18px;border-bottom:1px solid var(--line);overflow-x:auto;flex:none;background:var(--card);scrollbar-width:none;position:sticky;top:0;z-index:2;}
.ip-nav::-webkit-scrollbar{display:none;}
.ip-nav button{flex:none;height:24px;padding:0 11px;border:none;border-radius:999px;background:transparent;color:var(--muted);font-size:11.5px;font-weight:600;font-family:inherit;cursor:pointer;}
.ip-nav button.on{background:var(--brand-weak);color:var(--brand-strong);}
.ip-body{flex:1;overflow-y:auto;padding:14px 18px 24px;-webkit-overflow-scrolling:touch;}
.ip-sec{margin-bottom:22px;scroll-margin-top:44px;}
.ip-label{font-size:11px;font-weight:800;color:var(--brand-strong);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;display:flex;align-items:center;gap:6px;}
.ip-label svg{width:13px;height:13px;}
/* 统计行 */
.ip-stats{display:flex;gap:18px;flex-wrap:wrap;padding:2px 0 0;}
.ip-stats span{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;}
.ip-stats svg{width:13px;height:13px;color:var(--faint);}
/* 核心态势摘要 */
.ip-lede{font-size:13.5px;line-height:1.8;color:var(--ink);padding:10px 14px;background:var(--brand-weak);border-radius:8px;border-left:3px solid var(--brand);}
/* 情报子网格 */
.ip-sub-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.ip-sub{padding:10px 13px;border-radius:8px;border-left:3px solid var(--brand);background:color-mix(in srgb,var(--brand) 4%,transparent);font-size:12.5px;line-height:1.7;}
.ip-sub.full{grid-column:1/-1;}
.ip-sub b{display:block;font-size:10.5px;font-weight:800;letter-spacing:.5px;color:var(--brand-strong);margin-bottom:4px;}
/* 因果链 */
.ip-chain{padding:9px 13px;border-radius:8px;background:var(--bg);border:1px solid var(--line);font-size:12.5px;line-height:1.7;margin-bottom:8px;}
.ip-chain .arrow{color:var(--brand);font-weight:700;padding:0 2px;}
/* 信号看板 */
.ip-sig{padding:9px 13px;border-radius:8px;background:#f59e0b0a;border:1px solid #f59e0b30;margin-bottom:8px;}
.ip-sig-top{display:flex;align-items:center;gap:8px;margin-bottom:6px;}
.ip-sig-txt{flex:1;font-size:12.5px;font-weight:600;color:#b45309;}
.ip-sig-conf{flex:none;font-size:10.5px;font-family:var(--mono);color:var(--faint);font-variant-numeric:tabular-nums;}
.ip-sig-bar{height:3px;border-radius:2px;background:#f59e0b2e;overflow:hidden;}
.ip-sig-bar i{display:block;height:100%;border-radius:2px;background:#f59e0b;}
/* 关键词 */
.ip-kw-list{display:flex;flex-wrap:wrap;gap:6px;}
.ip-kw{padding:3px 11px;border-radius:999px;font-size:12px;border:1px solid var(--line);background:var(--bg);color:var(--muted);}
.ip-kw.rising{border-color:#f59e0b55;background:#f59e0b0e;color:#b45309;font-weight:600;}
.ip-kw.rising::after{content:"\u2191";margin-left:3px;font-size:10px;font-weight:800;}
/* 去重提示 */
.ip-dedup{margin-top:4px;padding:8px 12px;border-radius:8px;background:var(--hover);font-size:11px;color:var(--faint);display:flex;align-items:center;gap:6px;}
.ip-dedup svg{width:12px;height:12px;flex:none;color:#059669;}
.ip-empty{padding:24px;text-align:center;color:var(--faint);font-size:12.5px;}
/* 保留旧 ib-* 样式（话题聚类/关键词/趋势等仍由 renderInsight 使用） */
.ib-summary{font-size:13.5px;line-height:1.7;color:var(--ink);padding:8px 12px;background:var(--brand-weak);border-radius:8px;border-left:3px solid var(--brand);}
.ib-sub-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.ib-sub-section{padding:8px 12px;border-radius:8px;border-left:3px solid var(--brand);font-size:13px;line-height:1.65;}
.ib-sub-section.sub-core{background:#6366f10a;}
.ib-sub-section.sub-signal{background:#f59e0b0a;}
.ib-sub-section.sub-rss{background:#10b9810a;}
.ib-sub-section.sub-outlook{background:#ef44440a;}
.ib-sub-label{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;opacity:.7;color:var(--brand-strong);}
.ib-narrative{padding:10px 14px;border-radius:10px;background:linear-gradient(135deg,#6366f10a,#8b5cf60a);border-left:3px solid #7c3aed;font-size:13px;line-height:1.7;color:var(--ink);margin-bottom:10px;}
.ib-chain-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px;margin-bottom:10px;}
.ib-chain-card{padding:8px 12px;border-radius:8px;background:var(--card);border:1px solid var(--line);font-size:12px;line-height:1.6;}
.ib-chain-title{font-weight:600;color:var(--brand);margin-bottom:4px;font-size:11px;text-transform:uppercase;letter-spacing:.5px;}
.ib-chain-steps{color:var(--ink);}
.ib-signal-grid{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;}
.ib-signal-card{padding:6px 12px;border-radius:8px;background:#f59e0b0a;border:1px solid #f59e0b30;font-size:12px;color:#b45309;}
.ib-outlook{padding:10px 14px;border-radius:10px;background:#10b9810a;border-left:3px solid #10b981;font-size:13px;line-height:1.7;color:var(--ink);}
.ib-cluster-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;}
.ib-cluster-card{padding:10px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);cursor:pointer;transition:all .15s;}
.ib-cluster-card:hover{border-color:var(--brand);box-shadow:0 2px 8px #0001;}
.ib-cluster-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}
.ib-cluster-label{font-weight:600;font-size:13px;color:var(--ink);}
.ib-cluster-count{font-size:11px;color:var(--muted);background:var(--bg);padding:2px 8px;border-radius:999px;}
.ib-cluster-bar{height:4px;border-radius:2px;background:var(--line);overflow:hidden;}
.ib-cluster-bar-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--brand),#8b5cf6);transition:width .3s;}
.ib-sub-text{color:var(--ink);}
.ib-kw-list{display:flex;flex-wrap:wrap;gap:6px;}
.ib-kw{display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:500;border:1px solid var(--line);background:var(--bg);color:var(--muted);cursor:pointer;transition:all .12s;}
.ib-kw:hover{border-color:var(--brand);color:var(--brand);background:var(--brand-weak);}
.ib-kw.rising{border-color:#f59e0b55;background:#f59e0b0e;color:#b45309;}
.ib-kw.rising::after{content:"\u2191";margin-left:3px;font-size:10px;font-weight:700;}
.ib-topic-list{display:flex;flex-direction:column;gap:6px;}
.ib-topic{display:flex;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);cursor:pointer;transition:all .12s;}
.ib-topic:hover{border-color:var(--brand);background:var(--brand-weak);}
.ib-topic-rank{flex:none;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;font-family:var(--mono);background:var(--hover);color:var(--faint);}
.ib-topic-rank.top3{background:var(--brand-weak);color:var(--brand-strong);}
.ib-topic-title{flex:1;font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ib-topic-meta{flex:none;font-size:11px;color:var(--faint);font-family:var(--mono);}
.ib-stats{display:flex;gap:16px;padding:6px 0;font-size:12px;color:var(--faint);font-family:var(--mono);}
.ib-stats span{display:flex;align-items:center;gap:4px;}
.ib-no-data{padding:20px;text-align:center;color:var(--faint);font-size:13px;}
.ib-section{margin-bottom:14px;}
.ib-section:last-child{margin-bottom:0;}
.ib-label{font-size:11.5px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;}
@media (max-width:899px){
  .ip-sub-grid{grid-template-columns:1fr;}
}
@media (max-width:700px) {
  .ip-body{padding:10px 12px 14px;}
  .ip-kw-list{gap:4px;}
  .ip-kw{padding:2px 8px;font-size:11px;}
}

/* ── Source Quality Badge（信源质量指示器） ── */
.sq-badge{flex:none;display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:18px;padding:0 5px;border-radius:9px;font-size:10px;font-weight:700;font-family:var(--mono);line-height:1;}
.sq-badge.sq-high{background:#10b98118;color:#059669;border:1px solid #10b98133;}
.sq-badge.sq-mid{background:#f59e0b18;color:#b45309;border:1px solid #f59e0b33;}
.sq-badge.sq-low{background:#ef444418;color:#dc2626;border:1px solid #ef444433;}
.sp-health{display:flex;align-items:center;gap:8px;padding:8px 14px;font-size:11.5px;color:var(--muted);border-bottom:1px solid var(--line);}
.sp-health-dot{width:8px;height:8px;border-radius:50%;}
.sp-health-dot.good{background:#10b981;}
.sp-health-dot.warn{background:#f59e0b;}
.sp-health-dot.bad{background:#ef4444;}

/* ── Hot Trend Arrows（热榜趋势箭头） ── */
.hp-trend{flex:none;display:inline-flex;align-items:center;gap:2px;font-size:10px;font-weight:700;font-family:var(--mono);padding:1px 5px;border-radius:4px;line-height:1;}
.hp-trend.t-up{color:#dc2626;background:#dc26260e;}
.hp-trend.t-down{color:#6b7280;background:#6b72800e;}
.hp-trend.t-new{color:#059669;background:#0596690e;}
/* ── Cross Platform（跨平台共振） ── */
.ib-cross{margin-top:10px;}
.ib-cross-list{display:flex;flex-direction:column;gap:5px;}
.ib-cross-item{display:flex;align-items:center;gap:8px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);font-size:12.5px;}
.ib-cross-label{flex:1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ib-cross-plats{display:flex;gap:4px;}
.ib-cross-plat{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--hover);color:var(--faint);font-weight:600;}
.ib-trend{margin-top:12px;}
.ib-trend-title{font-size:12px;font-weight:600;color:var(--faint);margin-bottom:6px;}
.ib-trend-list{display:flex;flex-direction:column;gap:4px;}
.ib-trend-item{display:flex;align-items:center;gap:8px;padding:5px 10px;border:1px solid var(--line);border-radius:8px;font-size:12px;}
.ib-trend-label{flex:1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ib-trend-count{font-size:11px;color:var(--faint);min-width:40px;text-align:right;}
.ib-trend-arrow{font-weight:700;font-size:13px;}
.ib-trend-arrow.t-up{color:#e74c3c;}
.ib-trend-arrow.t-down{color:#95a5a6;}
.ib-trend-arrow.t-hot{color:#e67e22;}
.ib-trend-arrow.t-new{color:#27ae60;}
.ib-trend-lc{font-size:10px;padding:1px 6px;border-radius:4px;font-weight:600;}
.ib-trend-lc.lc-emerging{background:#eaf4fe;color:#2980b9;border:1px solid #b3d7f7;}
.ib-trend-lc.lc-hot{background:#fef5e7;color:#e67e22;border:1px solid #f5cba7;}
.ib-trend-lc.lc-cooling{background:#f4f6f7;color:#7f8c8d;border:1px solid #d5d8dc;}
.ib-trend-lc.lc-cold{background:#f9f9f9;color:#bdc3c7;border:1px solid #e5e8e8;}
.ib-ccat{margin-top:12px;}
.ib-ccat-list{display:flex;flex-wrap:wrap;gap:5px;}
.ib-ccat-item{display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid var(--line);border-radius:8px;font-size:12px;background:var(--bg);}
.ib-ccat-kw{font-weight:600;color:var(--fg);}
.ib-ccat-cats{display:flex;gap:3px;}
.ib-ccat-cat{font-size:10px;padding:1px 5px;border-radius:4px;background:var(--hover);color:var(--faint);}
.kw-tag{position:relative;cursor:default;}
.kw-tag.kw-emergent{border-color:#3498db !important;color:#2980b9 !important;}
.kw-tag.kw-rising{border-color:#e67e22 !important;color:#d35400 !important;}
.kw-tag.kw-peaking{border-color:#27ae60 !important;color:#1e8449 !important;}
.kw-tag.kw-declining{border-color:#95a5a6 !important;color:#7f8c8d !important;}
.kw-tag.kw-gone{border-color:#bdc3c7 !important;color:#bdc3c7 !important;text-decoration:line-through;}
.kw-tag::after{content:'';position:absolute;top:-2px;right:-2px;width:6px;height:6px;border-radius:50%;}
.kw-tag.kw-rising::after{background:#e67e22;}
.kw-tag.kw-emergent::after{background:#3498db;}
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


def _build_js(sources_with_items, build_ts_ms=0, analysis_json='', diverse_window_minutes=120):
    """Generate core JS for card wall + drawer reader."""
    cat_labels_json = json.dumps(CATEGORY_LABELS, ensure_ascii=False)
    # 内嵌 QR 生成库：国内移动端 jsdelivr/unpkg 常不可达且请求会长时间挂起，
    # 导致分享模态框数十秒不出现甚至永远无反应。构建时直接内嵌 vendor 库。
    qr_lib = ''
    try:
        _qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor_qrcode.min.js')
        with open(_qr_path, 'r', encoding='utf-8') as _f:
            qr_lib = _f.read().split('//# sourceMappingURL=')[0].strip()
    except Exception:
        qr_lib = ''
    return """
<script>
""" + qr_lib + """
;(function(){
  var BUILD_TS = """ + str(int(build_ts_ms)) + """;
  var DIVERSE_WINDOW = """ + str(int(diverse_window_minutes)) + """;
  var SOURCES = [];
  var CAT_LABELS = """ + cat_labels_json + """;
  var ANALYSIS_DATA = """ + (analysis_json if analysis_json else 'null') + """;

  /* ── Data ── */
  var CAT_ORDER = """ + json.dumps(CATEGORY_ORDER, ensure_ascii=False) + """;
  var ART = [];
  var now=new Date().toISOString();
  /* 全量数据按日期降序后由构建脚本切成 rss-data-0.js（首屏）与
     rss-data-1.js（后台合并）两块，页面不再内嵌数据（31MB→约0.15MB）。
     首屏严格时间排序；chunk1 合并后或刷新时应用 tier 交织。 */
  /* tags 归一化（issue M5）：只接受「非空数组」，其余（undefined / null / [] / 脏值）
     一律归一为 null。两条通道（构建期 chunk、刷新通道）共用同一函数，
     避免只修一条导致同一篇文章在不同通道下形状不一致。 */
  function _tagsOf(x){
    return (x && Object.prototype.toString.call(x.tags) === '[object Array]' && x.tags.length) ? x.tags : null;
  }
  function buildArt(){
    /* 渲染前全局去重：以 源key|链接 为唯一键，防止任何合并路径（chunk/快照/远程刷新）
       造成的同源同链文章重复渲染 */
    ART=[];var _seen={};
    SOURCES.forEach(function(s){
      s.items.forEach(function(it){
        var _u=it.link||'';
        var _k=(s.key||'')+'|'+(_u&&_u!=='#'?_u:(it.title_zh||it.title||''));
        if(_seen[_k])return; _seen[_k]=1;
        ART.push({t:it.title_zh||it.title, s:it.summary_zh||it.summary||'',
          src:s.name, sk:s.key, c:s.cat, sc:s.color, ti:s.tier||3,
          /* fc 兼容两条通道：chunk 通道字段名为 full_content，远程刷新通道为 fc */
          time:it.time_str, date:it.pub_date, u:it.link||'#', fc:it.fc||it.full_content||'',
          img:it.image||it.img||'', mu:it.mu||'', mt:it.mt||'',
          bad_date:!!it.bad_date, bb:!!s.bb, dfb:!!it.date_fallback, tags:_tagsOf(it)});
      });
    });
    /* 时区安全钳制（根因修复：旧实现用字符串比较判断未来日期，对 +08:00/Z 混合格式
       误判时区，把早间公众号文章改写成打开页面的时刻——09-14 08:15 事件）
       2026-09-14 二次修复：旧实现把**每一条**未来日期都改写成 now，N 条因此获得
       完全相同的时刻；默认降序排序下同刻并列，整块钉在首屏顶部
       （实测：超能网 6 条占据前 7 位中的 6 位）。
       改为「保序回拉」：最新的一条落到 now，其余按原始间距排在它之前 ——
       既不越界，也不制造人为并列；残留顺序信息一点不丢。
       注：构建期已对源级时区误标与「晚于 first_seen 的未来日期」做处置，
       本钳制是刷新通道（tier-1 由服务端 JS 重解析）的最后一道网。 */
    var nowMs=Date.now(), _fut=[];
    ART.forEach(function(a){
      if(!a.date) return;
      var _t=new Date(a.date).getTime();
      if(!isNaN(_t)&&_t>nowMs) _fut.push(a);
    });
    if(_fut.length){
      var _fmax=0;
      _fut.forEach(function(a){ var _t=new Date(a.date).getTime(); if(_t>_fmax) _fmax=_t; });
      _fut.forEach(function(a){
        a.date=new Date(nowMs-(_fmax-new Date(a.date).getTime())).toISOString();
      });
    }
    applySort();
    window.ART = ART;
  }
  /* ── Sort ── */
  /* sortMode 白名单：localStorage 里的脏值（旧版本写入 / 手工篡改）必须在此规范化。
     没有这一步，非法值会被默认分支一路吃下去，与 #sortSelect 的显示不一致，
     且未来新增的 else-if 分支可能被脏值意外命中。 */
  var SORT_MODES = ['newest','oldest','active','quality','diverse'];
  function _normSortMode(v){
    return (v && SORT_MODES.indexOf(v) >= 0) ? v : 'diverse';
  }
  var sortMode = _normSortMode(localStorage.getItem('rss_sort_mode'));
  /* 时区安全日期比较【仅用于升序】（D3 修复：+08:00/Z 混合格式的字符串比较是时区盲的）；
     无日期沉底，两个无日期视为相等。
     注意：本函数的 NaN 分支是为升序写的，降序调用会反转语义（无日期置顶）。
     任何降序排序一律使用 _dateCmpDesc，不要反向调用本函数。 */
  function _dateCmp(x,y){
    var tx=x?new Date(x).getTime():NaN, ty=y?new Date(y).getTime():NaN;
    if(isNaN(tx)&&isNaN(ty)) return 0;
    if(isNaN(tx)) return 1;
    if(isNaN(ty)) return -1;
    return tx-ty;
  }
  /* 时区安全日期比较【仅用于降序】：无日期一律沉底，语义与调用方向无关。
     修复前 newest/active 反向调用 _dateCmp，导致 201 条无日期条目被顶到首屏。 */
  function _dateCmpDesc(x,y){
    var tx=x?new Date(x).getTime():NaN, ty=y?new Date(y).getTime():NaN;
    if(isNaN(tx)&&isNaN(ty)) return 0;
    if(isNaN(tx)) return 1;      /* x 无日期 → x 靠后 */
    if(isNaN(ty)) return -1;
    if(tx===ty) return 0;
    return tx<ty?1:-1;           /* 新的在前 */
  }
  /* F1 修复：'active' 按信源最近更新时间排序 */
  function applySort(){
    if(sortMode==='oldest') ART.sort(function(a,b){ return _dateCmp(a.date,b.date); });
    else if(sortMode==='active'){
      var srcLatest={};
      ART.forEach(function(a){ if(a.date){ var cur=srcLatest[a.sk]; if(!cur||_dateCmp(a.date,cur)>0) srcLatest[a.sk]=a.date; }});
      ART.sort(function(a,b){
        var sa=srcLatest[a.sk]||'', sb=srcLatest[b.sk]||'';
        /* _dateCmpDesc 自身即为降序语义，参数不可再反转（反转会使无日期源置顶） */
        if(sa!==sb) return _dateCmpDesc(sa,sb);
        return _dateCmpDesc(a.date,b.date);
      });
      _applyRunCap(ART, 3, SOURCE_FAMILIES);
    }
    /* 集成契约（对齐 docs/superpowers/plans/2026-09-14-composite-sort-spec.md Phase 5）：
       - sortMode 单值 → diverse 与 topic 天然互斥，不可能同时触发
       - diverse 只重排窗口内次序；tierInterleave() 由合并/刷新路径在其之后调用，不受影响
       - topic 分支（由主题聚类方案实现）不得调用 weightedShuffle，主题视图自带分桶逻辑 */
    else if(sortMode==='diverse'){
      var _qMap = (ANALYSIS_DATA && ANALYSIS_DATA.quality) ? ANALYSIS_DATA.quality : {};
      var _win = (typeof DIVERSE_WINDOW !== 'undefined') ? DIVERSE_WINDOW : 120;
      /* 原地替换而非重新绑定 ART：window.ART / 各闭包持有的是同一个数组引用，
         若在此处整体替换引用，后续重排对持有旧引用的调用方不可见。 */
      var _sh = weightedShuffle(ART, _win, _qMap);
      ART.length = 0;
      for(var _i=0;_i<_sh.length;_i++) ART.push(_sh[_i]);
    }
    else if(sortMode==='quality' && ANALYSIS_DATA && ANALYSIS_DATA.quality){
      var qm=ANALYSIS_DATA.quality;
      ART.sort(function(a,b){ return (qm[b.sk]||0)-(qm[a.sk]||0); });
      _applyRunCap(ART, 5, SOURCE_FAMILIES);
    }
    else {
      ART.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });
      _applyRunCap(ART, 3, SOURCE_FAMILIES);
    }
  }
  var _sortEl = document.getElementById('sortSelect');
  if(_sortEl){ _sortEl.value=sortMode; _sortEl.addEventListener('change',function(){ sortMode=_normSortMode(this.value); localStorage.setItem('rss_sort_mode',sortMode); applySort(); wallLimit=WALL_STEP; curArt=null; renderWall(); }); }
  /* A6 修复：中文阅读速度约 400 字/分钟 */
  function estRead(a){ var mins=Math.max(1,Math.round((a.s||'').length/400)); return mins+' min'; }

  /* ── 信誉打散：时间窗口内加权采样 + 同源抑制，避免单源霸屏 ── */
  /* 同源抑制间隔（issue C1）：同一源在最近 SRC_GAP 位内出现过的，本轮不再选。
     缺陷背景：旧实现只有「窗口内按权重重排」，没有任何抑制同源相邻的项 ——
     「打散」（避免单源霸屏）等于没做。

     可证的界（精确表述，不要读成「最长连续恒 ≤ 2」）：
       · 池非空 ⇒ 同一源在最近 SRC_GAP 位内不会被再次选中 ⇒ 相邻必异源。
       · 池为空（组内剩余条目的源都恰好落在最近 SRC_GAP 位里）⇒ 退化为
         「最久未出现优先」；若此时只剩单一源，连出长度 = 该源剩余条目数，不可避。
     实测（2026-09-14 快照，9092 条 / 509 源）：
       前 200 位同源最长连续 9（纯时间降序）→ 1；前 20 位单源最多 13 → 4；
       前 200 位覆盖源数 36；平均时间位移与旧实现持平（103.1 vs 103.1）。
       残留：全长最长连出 11（人民网，第 7480 位 / 82% 深处），落在 g28 组内
       （该组 140 条 / 57 源 / 人民网 46 条，构成**可行**：46 ≤ floor(142/3)=47），
       根因是贪心消耗不均衡使组尾塌成单源，不是数据所迫。
       已实测的替代规则（池内改为「剩余量优先」）能把全程 maxRun 压到 1，
       但前 200 位单源占比 12%→25%、覆盖源数 36→13、前 20 位源质量均值 82.45→78.08，
       牺牲首屏多样性换深层不可见指标，净亏，故不改，如实记录为已知限制。

     报告建议的 seeded PRNG 解决不了它：随机化不提供「不相邻」的任何保证，
     而且按 quality 加权采样会把首屏推向纯降序（前轮读数：首屏均值 99.26 vs
     时间序 82.20，本轮未复测），与「保持时间可读性」冲突。
     只有位置约束能给出可证的界。 */

  /* 源族群定义：同族源共享打散配额，防止 V2EX 4 子源交替出现霸屏。
     key = source_key, value = family_key。未列出的源不参与族群 cap。 */
  var SOURCE_FAMILIES = {
    'v2ex_all_50': 'v2ex', 'v2ex技术_44': 'v2ex',
    'nodeseek_54': 'nodeseek'
  };
  /* 族群级 cap：family_key → 最大连续条数。未列出的族用单源 cap 值。 */
  var FAMILY_CAPS = { 'v2ex': 6, 'nodeseek': 4 };

  /* 同源连续抑制（run cap）：扫描已排序数组，将同源连续超过 cap 的
     多余条目与后续最近的异源条目交换。O(n) 典型 / O(n²) 最坏（3-pass 有界），
     不改变数组长度或元素集合。
     Level 1: 单源 cap（原有逻辑，用 _gk 替代直接 sk 比较）
     Level 2: 族群 cap（families[sk] 存在时，用 FAMILY_CAPS[gk] 作为上限）
     用于 active / newest / quality 模式，作为 weightedShuffle SRC_GAP
     之外的轻量补充（diverse 模式不需要，已有 SRC_GAP=2）。 */
  function _applyRunCap(arr, cap, families) {
    if (!arr || arr.length <= cap) return;
    families = families || {};
    var _gk = function(sk) { return families[sk] || sk; };
    var n = arr.length;
    for (var pass = 0; pass < 3; pass++) {
      var improved = false;
      for (var i = cap; i < n; i++) {
        var sk = arr[i].sk;
        var gk = _gk(sk);

        // ── Level 1: 单源 cap ──
        if (arr[i].sk === arr[i-1].sk) {
          var runStart = i - 1;
          while (runStart > 0 && arr[runStart-1].sk === sk) runStart--;
          var runLen = i - runStart + 1;
          if (runLen > cap) {
            var swapped = false;
            for (var j = i + 1; j < Math.min(i + 15, n); j++) {
              if (_gk(arr[j].sk) !== gk && (j === 0 || _gk(arr[j].sk) !== _gk(arr[j-1].sk))) {
                var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                swapped = true; improved = true; break;
              }
            }
            if (!swapped) {
              for (var j = i - 1; j >= 0; j--) {
                if (_gk(arr[j].sk) !== gk) {
                  var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                  improved = true; break;
                }
              }
            }
            continue;
          }
        }

        // ── Level 2: 族群 cap ──
        if (families[sk]) {
          var famCap = (typeof FAMILY_CAPS !== 'undefined' && FAMILY_CAPS[gk]) || cap;
          if (_gk(arr[i-1].sk) === gk) {
            var fStart = i - 1;
            while (fStart > 0 && _gk(arr[fStart-1].sk) === gk) fStart--;
            var fLen = i - fStart + 1;
            if (fLen > famCap) {
              var fSwapped = false;
              for (var j = i + 1; j < Math.min(i + 20, n); j++) {
                if (_gk(arr[j].sk) !== gk) {
                  var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                  fSwapped = true; improved = true; break;
                }
              }
              if (!fSwapped) {
                for (var j = i - 1; j >= 0; j--) {
                  if (_gk(arr[j].sk) !== gk) {
                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                    improved = true; break;
                  }
                }
              }
            }
          }
        }
      }
      if (!improved) break;
    }
  }

  var SRC_GAP = 2;

  /* 距末尾最近一次出现的距离；从未出现返回大值（恒可用）。
     用 lastAt 映射做到 O(1)，避免每次重扫输出数组。 */
  function _srcGap(lastAt, len, sk) {
    var at = lastAt[sk];
    return (at === undefined) ? 1e9 : (len - at);
  }

  var TIER_MULT = { 1: 1.5, 2: 1.2 };
  function _srcWeight(x, qm) {
    var q = (qm[x.sk] !== undefined && qm[x.sk] > 0) ? qm[x.sk] : 50;
    var tm = TIER_MULT[x.ti] || 1.0;
    return q * tm;
  }

  function weightedShuffle(articles, windowMinutes, qualityMap) {
    if (!articles || articles.length <= 1) return articles ? articles.slice() : [];
    if (!windowMinutes || windowMinutes <= 0) {
      // 窗口=0 → 纯时间降序（退化为现有行为）
      return articles.slice().sort(function(a,b){ return _dateCmpDesc(a.date, b.date); });
    }
    var qm = qualityMap || {};
    // 1. 先按时间降序排列（拷贝，不改原数组）
    var sorted = articles.slice().sort(function(a,b){ return _dateCmpDesc(a.date, b.date); });
    // 2. 锚定分段：组内每一条与组锚点（组内第一篇）的时间差 ≤ 窗口
    var groups = [], cur = [sorted[0]];
    for (var i = 1; i < sorted.length; i++) {
      var tBase = new Date(cur[0].date).getTime();
      var tCur  = new Date(sorted[i].date).getTime();
      if (!isNaN(tBase) && !isNaN(tCur) && (tBase - tCur) <= windowMinutes * 60000) {
        cur.push(sorted[i]);
      } else {
        groups.push(cur);
        cur = [sorted[i]];
      }
    }
    groups.push(cur);
    // 3. 窗口内加权采样（确定性 + 同源抑制）
    var result = [];
    var lastAt = {};   // sk → 上一次进入 result 的下标（跨组保留，防跨组边界处连出）
    for (var g = 0; g < groups.length; g++) {
      var remaining = groups[g].slice();
      while (remaining.length > 0) {
        // 3a 先取「最近 SRC_GAP 位内未出现」的条目作为可选池
        var pool = [], k, gk;
        for (k = 0; k < remaining.length; k++) {
          if (_srcGap(lastAt, result.length, remaining[k].sk) > SRC_GAP) pool.push(remaining[k]);
        }
        if (!pool.length) {
          // 3b 可选池为空：该源在本窗口占绝对多数，异源条目已用尽。
          //     退而取「最久未出现」的源（而不是接着选刚用过的源），
          //     否则会用 fallback 把刚压下去的连续段重新接起来。
          var maxGap = -1;
          for (k = 0; k < remaining.length; k++) {
            gk = _srcGap(lastAt, result.length, remaining[k].sk);
            if (gk > maxGap) maxGap = gk;
          }
          for (k = 0; k < remaining.length; k++) {
            if (_srcGap(lastAt, result.length, remaining[k].sk) === maxGap) pool.push(remaining[k]);
          }
        }
        // 3c 池内确定性加权选取
        var totalW = 0;
        for (k = 0; k < pool.length; k++) totalW += _srcWeight(pool[k], qm);
        var chosen;
        if (totalW <= 0) {
          chosen = pool[0];       // 所有权重为 0 → 按输入顺序取
        } else {
          /* 取「累计权重跨过总量一半」的那一个（池内顺序上的权重中位点）。
             注意这是确定性算法，不是随机采样：同一输入必然产出同一排列（D8 守卫）。
             本注释修正自旧的「使用确定性伪随机」—— 旧实现里没有任何 PRNG，注释与实现不符。 */
          var threshold = totalW * 0.5, cumW = 0, picked = -1;
          for (k = 0; k < pool.length; k++) {
            cumW += _srcWeight(pool[k], qm);
            if (cumW >= threshold && picked < 0) picked = k;
          }
          chosen = pool[picked < 0 ? 0 : picked];
        }
        result.push(chosen);
        lastAt[chosen.sk] = result.length - 1;
        for (k = 0; k < remaining.length; k++) {
          if (remaining[k] === chosen) { remaining.splice(k, 1); break; }
        }
      }
    }
    return result;
  }
  /* ── weightedShuffle end ── */

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
  window.curArt = null;
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
    // 收藏芯片置首：手机端 chips 横向滚动时保证入口始终可见
    var bmCnt=Object.keys(_bookmarks).length;
    if(bmCnt>0) h+='<button class="chip bm-chip'+(filter.filterBm?' on':'')+'" id="bmChip" onclick="toggleBmFilter()">\u2605 \u6536\u85cf <span class="n">'+bmCnt+'</span></button>';
    CAT_ORDER.forEach(function(c){
      if(!counts[c]) return;
      var label=CAT_LABELS[c]||c, on=filter.type==='cat'&&filter.cats[c];
      h+='<button class="chip'+(on?' on':'')+'" data-c="'+c+'">'+label+' <span class="n">'+counts[c]+'</span></button>';
    });
    /* ── 发现：长尾高质量源 ── */
    var _discKeys=_discoverKeys();
    var discCnt=0; ART.forEach(function(a){if(_discKeys[a.sk])discCnt++;});
    if(discCnt>0){
      var discOn=filter.type==='discover';
      h+='<button class="chip disc-chip'+(discOn?' on':'')+'" data-c="__disc">\U0001f50d \u53d1\u73b0 <span class="n">'+discCnt+'</span></button>';
    }
    document.getElementById('chips').innerHTML=h;
    document.querySelectorAll('.chip').forEach(function(el){
      if(!el.dataset.c) return; /* \u65e0 data-c \u7684\u82af\u7247\uff08\u5982\u6536\u85cf\uff09\u4fdd\u7559\u5185\u8054 onclick\uff0c\u907f\u514d\u8986\u76d6\u6210 c=undefined */
      el.onclick=function(){
        var c=this.dataset.c, uo=filter.unreadOnly, bm=filter.filterBm;
        /* 发现 chip：切换 discover 模式 */
        if(c==='__disc'){
          filter=filter.type==='discover'?{type:'all',cats:{},unreadOnly:uo,filterBm:bm}:{type:'discover',unreadOnly:uo,filterBm:bm};
          curArt=null; wallLimit=WALL_STEP; renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
          return;
        }
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
    else if(filter.type==='discover'){h1.textContent='\U0001f50d \u53d1\u73b0';}
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
  window.clearSrcF=function(e){e.stopPropagation();var uo=filter.unreadOnly,bm=filter.filterBm;filter={type:'all',unreadOnly:uo,filterBm:bm};curArt=null;window.curArt=null;wallLimit=WALL_STEP;renderChips();renderWall();renderPanel();updateTitle();updateHash();updateUnreadBtn();updateBmChip();};

  /* ── Source panel ── */
  var _srcBtnEl=null;
  function toggleSrcPanel(){
    var opening=!document.body.classList.contains('src-open');
    if(opening)_srcBtnEl=document.activeElement;
    document.body.classList.toggle('src-open');
    if(opening){var si=document.getElementById('spSearch');if(si)si.focus();}
    else{if(_srcBtnEl){try{_srcBtnEl.focus();}catch(e){}_srcBtnEl=null;}}
  }
  window.toggleSrcPanel=toggleSrcPanel;
  function selectSrc(key){
    var uo=filter.unreadOnly,bm=filter.filterBm;
    if(!key){filter={type:'all',unreadOnly:uo,filterBm:bm};} else {filter={type:'src',src:key,unreadOnly:uo,filterBm:bm};}
    curArt=null; wallLimit=WALL_STEP; document.body.classList.remove('src-open');
    renderChips(); renderWall(); renderPanel(); window.scrollTo({top:0}); updateTitle(); updateHash(); updateUnreadBtn(); updateBmChip();
    /* 单源实时刷新：后台静默拉取该源最新内容，成功则替换并重建，失败无感知 */
    if(key){
      fetch('https://starhub-refresh.vercel.app/api/rss?source='+encodeURIComponent(key),
        (function(){var c=window.AbortController?new AbortController():null;if(c)setTimeout(function(){c.abort();},8000);return c?{signal:c.signal}:{};}())
      )
      .then(function(r){return r.ok?r.json():null;})
      .then(function(data){
        if(!data||!data.items||!data.items.length) return;
        var src=SOURCES.find(function(s){return s.key===key;});
        if(!src) return;
        /* 映射 API 字段(t/s/u/d)到 buildArt 期望格式，按 link 去重 */
        var have={}; data.items.forEach(function(it){if(it.u&&it.u!=='#')have[it.u]=1;});
        var oldItems=src.items.filter(function(it){return !it.link||!have[it.link];});
        var newItems=data.items.map(function(it){
          return {title_zh:it.t_zh||it.t||'',summary_zh:it.s||'',link:it.u||'#',pub_date:it.d||'',fc:it.fc||'',image:it.img||'',mu:it.mu||'',mt:it.mt||''};
        });
        src.items=newItems.concat(oldItems);
        buildArt(); renderChips(); renderWall(); renderPanel();
        var n=data.items.length; toast('已更新 '+src.name+'（'+n+' 篇最新）');
      }).catch(function(){});
    }
  }
  window.selectSrc=selectSrc;
  function renderPanel(){
    var q=(document.getElementById('spSearch').value||'').trim().toLowerCase();
    // 信源健康度总览
    var healthHtml='';
    if(ANALYSIS_DATA&&ANALYSIS_DATA.quality){
      var qm=ANALYSIS_DATA.quality,vals=Object.values(qm),n=vals.length;
      if(n>0){
        var avg=vals.reduce(function(a,b){return a+b;},0)/n;
        var good=vals.filter(function(v){return v>=70;}).length;
        var warn=vals.filter(function(v){return v>=40&&v<70;}).length;
        var bad=vals.filter(function(v){return v<40;}).length;
        healthHtml='<div class="sp-health">';
        healthHtml+='<span class="sp-health-dot good"></span>'+good+' \u5065\u5eb7';
        healthHtml+='<span class="sp-health-dot warn"></span>'+warn+' \u8b66\u544a';
        healthHtml+='<span class="sp-health-dot bad"></span>'+bad+' \u5f02\u5e38';
        healthHtml+='<span style="margin-left:auto;color:var(--faint)">\u5747\u5206 '+Math.round(avg)+'</span>';
        healthHtml+='</div>';
      }
    }
    var h=healthHtml+'<div class="sp-all'+(filter.type!=='src'?' on':'')+'" onclick="selectSrc(null)">\u2630 \u5168\u90e8\u4fe1\u6e90<span class="n">'+ART.length+'</span></div>';
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
        h+='<div class="sp-src'+(on?' on':'')+'" data-k="'+s.key+'"><span class="src-dot" style="--sc:'+s.color+'"></span><span class="nm">'+esc(s.name)+'</span><span class="n">'+s.items.length+'</span>';
        if(ANALYSIS_DATA&&ANALYSIS_DATA.quality){var qs=ANALYSIS_DATA.quality[s.key];if(qs!=null){var qc=qs>=70?'sq-high':qs>=40?'sq-mid':'sq-low';h+='<span class="sq-badge '+qc+'">'+Math.round(qs)+'</span>';}}
        h+='</div>';
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
  var _searchSrcMatch = null; // 搜索匹配到的信源 key
  var _topicBigrams = null;   // 话题标签二元组（insightSearch 设置）
  /* 长尾高质量源 key 集合：条目 ≤5 且 quality ≥60 */
  function _discoverKeys(){
    var srcCnt={};
    ART.forEach(function(a){srcCnt[a.sk]=(srcCnt[a.sk]||0)+1;});
    var qm=(ANALYSIS_DATA&&ANALYSIS_DATA.quality)?ANALYSIS_DATA.quality:{};
    var ks={};
    for(var sk in srcCnt){
      if(srcCnt[sk]<=5 && (qm[sk]||0)>=60) ks[sk]=true;
    }
    return ks;
  }
  function visibleArts(){
    var q = globalSearch;
    var _dk=(filter.type==='discover')?_discoverKeys():null;
    return ART.filter(function(a){
      if(filter.type==='cat' && !filter.cats[a.c]) return false;
      if(filter.type==='src' && a.sk!==filter.src) return false;
      if(filter.type==='discover' && !_dk[a.sk]) return false;
      if(filter.filterBm && !_bookmarks[artKey(a)]) return false;
      if(filter.unreadOnly && visited[artKey(a)]) return false;
      if(q) {
        if(_searchSrcMatch) return a.sk === _searchSrcMatch;
        if(_topicBigrams&&_topicBigrams.length>=2){
          var tl=(a.t||'').toLowerCase(),hits=0;
          for(var i=0;i<_topicBigrams.length;i++){if(tl.indexOf(_topicBigrams[i])>=0)hits++;}
          return hits>=2&&hits/_topicBigrams.length>=0.15;
        }
        var ql=q.toLowerCase(); return (a.t||'').toLowerCase().indexOf(ql)>=0 || (a.s||'').toLowerCase().indexOf(ql)>=0 || (a.src||'').toLowerCase().indexOf(ql)>=0;
      }
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
  /* U1 修复：未读计数 */
  function _countUnread(){ var n=0; ART.forEach(function(a){ if(!visited[artKey(a)]) n++; }); return n; }
  function updateUnreadBtn(){
    var b=document.getElementById('unreadToggle');
    if(!b) return;
    b.classList.toggle('on',filter.unreadOnly);
    /* A5 修复：aria-pressed */
    b.setAttribute('aria-pressed', filter.unreadOnly?'true':'false');
    /* U1 修复：显示未读计数 */
    var cnt=_countUnread();
    var cntEl=b.querySelector('.unread-cnt');
    if(!cntEl){ cntEl=document.createElement('span'); cntEl.className='unread-cnt'; cntEl.style.cssText='font-family:var(--mono);font-size:10px;opacity:.8;margin-left:2px;'; b.appendChild(cntEl); }
    cntEl.textContent=cnt>0?' '+cnt:'';
    _updateMarkAllReadBtn();
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
  /* A8 修复：BM_MAX 死代码已移除 */
  var _bookmarks={}, BM_KEY='rss_bookmarks';
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
      var em=globalSearch?(_searchSrcMatch?'\u4fe1\u6e90 \u00ab'+esc(SRC_OBJ(_searchSrcMatch)?SRC_OBJ(_searchSrcMatch).name:globalSearch)+'\u00bb \u6682\u65e0\u6587\u7ae0':'\u672a\u627e\u5230\u4e0e\u300c'+esc(globalSearch)+'\u300d\u76f8\u5173\u7684\u6587\u7ae0'):(filter.filterBm?'\u6682\u65e0\u6536\u85cf\u6587\u7ae0':(filter.unreadOnly?'\u6240\u6709\u6587\u7ae0\u5df2\u8bfb':'\u8be5\u7b5b\u9009\u4e0b\u6ca1\u6709\u6587\u7ae0'));
      /* U8 修复：空态加 CTA 按钮 */
      var cta='';
      if(globalSearch) cta='<br><button onclick="document.getElementById(&quot;globalSearchClear&quot;).click()" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">清除搜索</button>';
      else if(filter.type==='cat'||filter.type==='src') cta='<br><button onclick="clearSrcF(event)" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">查看全部文章</button>';
      else if(filter.unreadOnly) cta='<br><button onclick="toggleUnread()" style="margin-top:8px;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;cursor:pointer;font-family:var(--body)">显示全部文章</button>';
      wall.innerHTML='<div class="empty-hint">'+em+cta+'</div>';
      wallLimit=0;
      return;
    }
    var end=Math.min(wallLimit, list.length);
    var h='';
    if(globalSearch) {
      var bannerTxt = _searchSrcMatch ? '\u4fe1\u6e90 \u00ab' + esc(SRC_OBJ(_searchSrcMatch)?SRC_OBJ(_searchSrcMatch).name:globalSearch) + '\u00bb \u2014 ' + list.length + ' \u7bc7' : '\u641c\u7d22 \u00ab' + esc(globalSearch) + '\u00bb \u2014 \u547d\u4e2d ' + list.length + ' \u7bc7';
      h += '<div class="search-banner">' + bannerTxt + '</div>';
    }
    for(var i=0;i<end;i++){
      var a=list[i], k=artKey(a), isVis=!!visited[k];
      var isOpen=curArt&&artKey(curArt)===k;
      var hasImg=!!a.img;
      /* 有封面图才走封面卡；无图回退纯文字紧凑卡，避免渐变占位浪费空间 */
      /* A1 修复：卡片加 tabindex 使键盘可达 */
      h+='<article class="card'+(hasImg?' cover-card':'')+(isVis?' visited':'')+(isOpen?' open':'')+'" data-k="'+esc(k)+'" tabindex="0" style="--cc:var(--cat-'+a.c+')">';
      if(hasImg){
        h+='<a class="cover" href="'+esc(a.u)+'" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" onclick="event.stopPropagation()">';
        h+='<span class="cover-fallback">'+esc((a.t||'#').charAt(0).toUpperCase())+'</span>';
        h+='<img class="cover-img" src="'+esc(a.img)+'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">';
        h+='</a>';
      }
      h+='<div class="card-top"><span class="cat-tag" style="color:var(--cat-'+a.c+')">'+(CAT_LABELS[a.c]||a.c)+'</span>';
      h+='<span class="card-time" title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span>';
      h+='<button class="bm-btn'+(isBookmarked(k)?' on':'')+'" data-k="'+esc(k)+'" title="\u6536\u85cf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></button>';
      h+='<a class="ext-btn" href="'+esc(a.u)+'" target="_blank" rel="noopener" title="\u539f\u7ad9" onclick="event.stopPropagation()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg></a></div>';
      h+='<h3 class="card-title">'+highlightEsc(a.t,globalSearch)+'</h3>';
      if(a.s) h+='<p class="card-summary">'+highlightEsc(a.s,globalSearch)+'</p>';
      if(a.tags && a.tags.length){
        h+='<div class="card-tags">';
        for(var _ti=0;_ti<Math.min(a.tags.length,3);_ti++){
          if(_ti>0) h+=' ';
          h+='<span class="ctag">'+esc(a.tags[_ti])+'</span>';
        }
        if(a.tags.length>3) h+='<span class="ctag">+' + (a.tags.length-3) + '</span>';
        h+='</div>';
      }
      h+='<div class="card-foot"><span class="src-dot" style="--sc:'+a.sc+'"></span><span class="src-name">'+esc(a.src)+'</span>';
      h+='<span class="foot-meta"><button class="copy-btn" data-k="'+esc(k)+'" title="\u590d\u5236\u6807\u9898\u4e0e\u94fe\u63a5"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>\u590d\u5236</button><button class="share-btn" data-k="'+esc(k)+'" title="\u5206\u4eab\u6587\u7ae0"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button><span>'+estRead(a)+'</span></span></div>';
      h+='</article>';
    }
    wall.innerHTML=h;
    wallLimit=end;
    _scheduleWallTranslate();
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
  /* 封面图加载失败：隐藏 img 让分类色 fallback 露出（error 不冒泡，捕获阶段拦截） */
  document.getElementById('wall').addEventListener('error',function(e){
    var t=e.target;
    if(t&&t.classList&&t.classList.contains('cover-img')){ t.style.display='none'; }
  },true);
  /* A1 修复：键盘 Enter/Space 打开卡片（仅当焦点在卡片本身时，不劫持子控件） */
  document.getElementById('wall').addEventListener('keydown',function(e){
    if(e.key==='Enter'||e.key===' '){
      var card=e.target.closest('.card'); if(!card||e.target!==card)return;
      e.preventDefault(); card.click();
    }
  });
  /* 事件委托：一次性绑定，无需重新绑定 */
  document.getElementById('wall').addEventListener('click',function(e){
    var card=e.target.closest('.card'); if(!card)return;
    var k=card.dataset.k;
    var a=ART.find(function(x){return artKey(x)===k;});
    if(!a) return;
    if(e.target.closest('.ext-btn')){markRead(a);updateCardStates();return;}
    if(e.target.closest('.bm-btn')){toggleBookmark(a);return;}
    if(e.target.closest('.copy-btn')){copyArticleInfo(k);return;}
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
      /* F3 修复：全文加载失败时显示行内提示与重试按钮 */
      if(!inner.querySelector('.r2-ft-error')){
        var err=document.createElement('div');err.className='r2-ft-error';
        err.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke-dasharray="30 70" stroke-linecap="round"/></svg> 全文加载失败 <button onclick="fetchFullArticle(curArt)" style="color:var(--brand-strong);background:none;border:1px solid var(--brand-line);border-radius:6px;padding:2px 10px;font-size:12px;cursor:pointer;font-family:var(--body)">重试</button>';
        var hint2=inner.querySelector('.r2-foot-hint');if(hint2)inner.insertBefore(err,hint2);else inner.appendChild(err);
      }
    });
  }
  /* ── 媒体嵌入：YouTube iframe + 播客/音频播放器 ── */
  function extractYouTubeId(url){
    if(!url) return null;
    var m=url.match(/(?:youtube\.com\/watch\?.*v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{6,})/);
    return m?m[1]:null;
  }
  function _renderMedia(a,container){
    if(!a||!container) return;
    var vid=extractYouTubeId(a.u);
    var hasIframe=container.querySelector('iframe[src*="youtube.com"],iframe[src*="youtu.be"]');
    if(vid&&!hasIframe){
      var ifr=document.createElement('iframe');
      ifr.src='https://www.youtube.com/embed/'+vid;
      ifr.setAttribute('loading','lazy');
      ifr.setAttribute('allowfullscreen','');
      ifr.setAttribute('allow','accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
      ifr.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups');
      ifr.setAttribute('title','YouTube video player');
      ifr.style.cssText='width:100%;aspect-ratio:16/9;border:0;border-radius:8px;margin-bottom:12px';
      container.insertBefore(ifr,container.firstChild);
    }
    if(a.mu){
      var hasAudio=container.querySelector('audio,video');
      if(!hasAudio){
        var isAudio=a.mt&&a.mt.indexOf('audio')===0;
        var el=document.createElement(isAudio?'audio':'video');
        el.controls=true;el.preload='none';el.src=a.mu;
        el.style.cssText='width:100%;margin-bottom:12px;border-radius:8px';
        el.addEventListener('error',function(){
          el.style.display='none';
          var fb=document.createElement('div');
          fb.className='r2-media-error';
          fb.innerHTML='<p style="color:var(--muted);font-size:13px;margin:8px 0">\u5a92\u4f53\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u76f4\u63a5\u8bbf\u95ee\u539f\u59cb\u94fe\u63a5</p><a href="'+a.u+'" target="_blank" rel="noopener" style="color:var(--brand-strong);font-size:13px">\u6253\u5f00\u539f\u59cb\u94fe\u63a5 \u2197</a>';
          container.insertBefore(fb,container.firstChild);
        });
        container.insertBefore(el,container.firstChild);
      }
    }
  }
  /* ── 媒体清理：关闭/切换文章时停止播放 ── */
  function _cleanupMedia(){
    var body=document.getElementById('r2Body');
    if(!body) return;
    var audios=body.querySelectorAll('audio,video');
    for(var i=0;i<audios.length;i++){try{audios[i].pause();audios[i].src='';audios[i].load();}catch(e){}}
    var iframes=body.querySelectorAll('iframe');
    for(var j=0;j<iframes.length;j++){try{iframes[j].src='about:blank';}catch(e){}}
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
    /* 正文翻译切换按钮：非中文内容时显示 */
    var ftText=div.textContent||'';
    if(ftText&&!isMostlyZh(ftText)){
      var tog=document.createElement('div');
      tog.className='r2-lang-toggle';
      tog.innerHTML='<button class="active" id="btnFtOrig">原文</button><button id="btnFtTrans">翻译</button>';
      if(hint) inner.insertBefore(tog,hint); else inner.appendChild(tog);
      document.getElementById('btnFtTrans').onclick=function(){_translateFulltext(div);};
      document.getElementById('btnFtOrig').onclick=function(){
        div.innerHTML=div._origHtml||div.innerHTML;
        var bs=tog.querySelectorAll('button');bs[0].classList.add('active');bs[1].classList.remove('active');
      };
    }
    /* 媒体嵌入：YouTube 视频 / 播客音频 */
    _renderMedia(curArt,div);
  }
  /* 正文翻译：提取文本→分块翻译→重建段落 */
  function _translateFulltext(ftDiv){
    if(!ftDiv) return;
    if(!ftDiv._origHtml) ftDiv._origHtml=ftDiv.innerHTML;
    var tog=ftDiv.nextElementSibling;
    if(tog&&tog.classList&&tog.classList.contains('r2-lang-toggle')){
      var bs=tog.querySelectorAll('button');bs[0].classList.remove('active');bs[1].classList.add('active');
    }
    ftDiv.innerHTML='<p>翻译中…</p>';
    var text=ftDiv._origText||(ftDiv._origText=(ftDiv._origHtml||ftDiv.innerHTML).replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim());
    _clientTranslate(text,function(tr){
      var cur=document.querySelector('.r2-fulltext');
      if(cur){
        var lines=tr.split(/。|！|？|\.\s+/).filter(function(s){return s.trim();});
        cur.innerHTML=lines.map(function(s){return '<p>'+esc(s.trim())+'</p>';}).join('')||'<p>'+esc(tr)+'</p>';
      }
    });
  }
  function markRead(a){visited[artKey(a)]=1;try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}}
  function markAllRead(){
    var list=visibleArts(),cnt=0;
    for(var i=0;i<list.length;i++){var k=artKey(list[i]);if(!visited[k]){visited[k]=1;cnt++;}}
    try{localStorage.setItem('rss_read_v2',JSON.stringify(visited));}catch(e){}
    updateCardStates();
    if(cnt>0) toast('\u5df2\u6807\u8bb0 '+cnt+' \u7bc7\u4e3a\u5df2\u8bfb');
    if(filter.unreadOnly){wallLimit=WALL_STEP;renderWall();}
    renderChips(); /* U1: 刷新未读计数 */
  }
  /* F4 修复：全部已读入口——在未读模式激活时显示按钮 */
  function _updateMarkAllReadBtn(){
    var btn=document.getElementById('markAllReadBtn');
    if(!btn) return;
    btn.style.display=filter.unreadOnly?'':'none';
  }
  /* A2 修复：焦点陷阱工具函数 */
  var _prevFocusEl=null;
  function _trapFocus(container,e){
    var foc=container.querySelectorAll('button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])');
    if(!foc.length)return;var first=foc[0],last=foc[foc.length-1];
    if(e.shiftKey){if(document.activeElement===first){e.preventDefault();last.focus();}}
    else{if(document.activeElement===last){e.preventDefault();first.focus();}}
  }
  function openReader(a){
    curArt=a; window.curArt=a; markRead(a);
    _prevFocusEl=document.activeElement;
    renderReader(); document.body.classList.add('reading');
    document.body.classList.remove('src-open');
    document.getElementById('r2Body').scrollTop=0; updateCardStates();
    var closeBtn=document.querySelector('.r2-close');if(closeBtn)closeBtn.focus();
  }
  function _navReader(dir){
    if(!curArt)return;
    var order=visibleArts();var pos=-1;
    for(var i=0;i<order.length;i++){if(artKey(order[i])===artKey(curArt)){pos=i;break;}}
    if(pos===-1)return;
    var np=pos+dir;
    if(np>=0&&np<order.length)openReader(order[np]);
  }
  window._navReader=_navReader;
  function renderReader(){
    var a=curArt; if(!a) return;
    _cleanupMedia();
    document.getElementById('r2Src').innerHTML='<span class="src-dot" style="--sc:'+a.sc+'"></span><b>'+esc(a.src)+'</b><span>\u00b7</span><span title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span>';
    var openEl=document.getElementById('r2Open'); openEl.href=a.u;
    var h='<h1 class="r2-title">'+esc(a.t)+'</h1>';
    h+='<div class="r2-meta" style="--cc:var(--cat-'+a.c+')"><span class="cat">'+(CAT_LABELS[a.c]||a.c)+'</span>';
    h+='<span class="src-dot" style="--sc:'+a.sc+'"></span><span>'+esc(a.src)+'</span>';
    h+='<span>\u00b7</span><span title="'+esc(a.date||'')+'">'+_dynTime(a)+'</span><span>\u00b7</span><span>'+estRead(a)+'</span></div>';
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
    h+='<div class="r2-actions-bottom">';
    h+='<button class="r2-nav-btn" onclick="_navReader(-1)" title="\u4e0a\u4e00\u7bc7 (K)" style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--body)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M19 12H5M11 18l-6-6 6-6"/></svg> \u4e0a\u4e00\u7bc7</button>';
    h+='<button class="r2-share-btn" onclick="r2ShareClick()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg><span>\u5206\u4eab\u672c\u6587</span></button>';
    h+='<button class="r2-nav-btn" onclick="_navReader(1)" title="\u4e0b\u4e00\u7bc7 (J)" style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--body)">\u4e0b\u4e00\u7bc7 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>';
    h+='</div>';
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
  /* 全文/摘要翻译：Agnes API 主力（服务端代理，密钥不落前端），失败块由服务端 GTX 兜底（mode:'full'），
     最终兜底原文。2026-09-08 实证修正：gtx 端点响应带 ACAO:*（浏览器可直连），当年「必遭 CORS」
     实为 GFW/网络因素误判；但全文按钮仍走服务端（质量优先 Agnes），浏览器直连仅用于批量补翻主力。 */
  function _clientTranslate(text,cb){
    if(!text||isMostlyZh(text)){cb(text);return;}
    var k=text.substring(0,100);
    if(_ctCache[k]){cb(_ctCache[k]);return;}
    if(_ctPend[k]){_ctPend[k].push(cb);return;}
    _ctPend[k]=[cb];
    /* 长文本分块翻译：每块 450 字，Agnes 每请求 ≤20 块，批间串行 */
    var chunks=[],pos=0;
    while(pos<text.length){var end=Math.min(pos+450,text.length);chunks.push(text.substring(pos,end));pos=end;}
    var _finished=0;
    function _finish(tr){ if(_finished) return; _finished=1; _ctCache[k]=tr; var p=_ctPend[k]||[]; delete _ctPend[k]; p.forEach(function(f){f(tr);}); }
    (function _agiBatch(bi){
      if(_finished) return;
      var start=bi*20,end=Math.min(start+20,chunks.length);
      if(start>=chunks.length){ _finish(chunks.join('')); return; }
      var ctrl=(typeof AbortController==='function')?new AbortController():null;
      /* 服务端 full 最坏路径（非 429 慢挂起情形）= Agnes 12s×2+400ms + GTX 6s×2+600ms ≈ 37s，
         前端 25s 超时只保证一轮 Agnes+GTX 在用户侧可见；429 快速失败路径 <10s 必然可见，
         慢路径的 GTX 兜底仍会在服务端完成并写缓存（下次点击命中） */
      var tmr=ctrl?setTimeout(function(){ctrl.abort();},25000):null;
      fetch(TR_API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:chunks.slice(start,end),mode:'full'}),signal:ctrl?ctrl.signal:undefined})
      .then(function(r){ if(tmr)clearTimeout(tmr); return r.ok?r.json():Promise.reject(new Error('http '+r.status)); })
      .then(function(j){
        if(!j||!j.ok||!j.translations||j.translations.length!==(end-start)) throw new Error('bad payload');
        for(var i=start;i<end;i++){ var t=(j.translations[i-start]||'').trim(); if(t)chunks[i]=t; }
        _agiBatch(bi+1);
      }).catch(function(){ if(tmr)clearTimeout(tmr); _agiBatch(bi+1); });
    })(0);
  }

  // ── OPML export ──
  /* 先从 rss_sources.json 获取 url 映射（chunk 数据可能不含 url），
     获取失败则回退到 SOURCES 自带的 url（下次构建后 chunk 含 url） */
  function exportOPML(){
    var _doExport=function(urlMap){
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
          var u=s.url||urlMap[s.key]||'';
          xml+='    <outline type="rss" text="'+esc(s.name)+'" title="'+esc(s.name)+'" xmlUrl="'+esc(u)+'"/>\\n';
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
      toast('\\u5df2\\u5bfc\\u51fa '+SOURCES.length+' \\u4e2a\\u4fe1\\u6e90');
    };
    /* 尝试从 rss_sources.json 获取 url 映射 */
    fetch('rss_sources.json').then(function(r){return r.ok?r.json():null;}).then(function(srcs){
      var m={}; if(srcs)srcs.forEach(function(s){if(s.key&&s.url)m[s.key]=s.url;});
      _doExport(m);
    }).catch(function(){ _doExport({}); });
  }

  // ── Keyboard help ──
  function toggleKbdHelp(){
    var m=document.getElementById('kbdHelp');
    if(!m){m=document.createElement('div');m.id='kbdHelp';m.className='kbd-help';
    m.innerHTML='<div class="kbd-help-backdrop" onclick="toggleKbdHelp()"></div><div class="kbd-help-panel"><div class="kbd-help-hd"><h3>\u5feb\u6377\u952e</h3><button class="share-close" onclick="toggleKbdHelp()">\u00d7</button></div><div class="kbd-help-body"><table><tr><td><kbd>j</kbd> / <kbd>\u2192</kbd></td><td>\u4e0b\u4e00\u7bc7\u6587\u7ae0</td></tr><tr><td><kbd>k</kbd> / <kbd>\u2190</kbd></td><td>\u4e0a\u4e00\u7bc7\u6587\u7ae0</td></tr><tr><td><kbd>/</kbd></td><td>\u805a\u7126\u641c\u7d22\u6846</td></tr><tr><td><kbd>d</kbd></td><td>\u5207\u6362\u4e3b\u9898</td></tr><tr><td><kbd>Esc</kbd></td><td>\u5173\u95ed\u9605\u8bfb\u5668/\u9762\u677f</td></tr><tr><td><kbd>?</kbd></td><td>\u663e\u793a\u5feb\u6377\u952e\u5e2e\u52a9</td></tr></table></div></div></div>';
    document.body.appendChild(m);}
    m.classList.toggle('open');
  }

  // ── Window exports ──
  window.ART = ART;
  window.closeReader = function(){ _cleanupMedia(); document.body.classList.remove('reading'); curArt=null; window.curArt=null; updateCardStates(); if(_prevFocusEl){try{_prevFocusEl.focus();}catch(e){}_prevFocusEl=null;} };
  window.closeOverlays = function(){ document.body.classList.remove('src-open'); window.closeReader(); closeInsight(); };
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
  var _searchTimer=0;
  if(gsInput) {
    gsInput.addEventListener('input', function(){
      globalSearch = this.value.trim();
      _searchSrcMatch = null;
      _topicBigrams = null;
      if(globalSearch.length >= 1) {
        var ql = globalSearch.toLowerCase();
        var matched = SOURCES.filter(function(s){ return s.name.toLowerCase().indexOf(ql) >= 0; });
        if(matched.length === 1) _searchSrcMatch = matched[0].key;
        else if(matched.length > 1 && matched.length <= 5) {
          var exact = matched.find(function(s){ return s.name.toLowerCase() === ql; });
          if(exact) _searchSrcMatch = exact.key;
        }
      }
      gsWrap.classList.toggle('has-q', globalSearch.length > 0);
      gsWrap.classList.toggle('src-hit', !!_searchSrcMatch);
      var _sml=document.getElementById('srcMatchLabel');
      if(_sml){if(_searchSrcMatch){var _sn=SRC_OBJ(_searchSrcMatch);_sml.textContent='\u4fe1\u6e90\u5339\u914d\uff1a'+(_sn?_sn.name:_searchSrcMatch);_sml.style.display='';}else{_sml.style.display='none';}}
      clearTimeout(_searchTimer);
      _searchTimer=setTimeout(function(){ curArt = null; wallLimit = WALL_STEP; renderWall(); updateMeta(); },300);
    });
  }
  if(gsClear) {
    gsClear.addEventListener('click', function(){
      gsInput.value = ''; globalSearch = '';
      _searchSrcMatch = null;
      _topicBigrams = null;
      gsWrap.classList.remove('has-q', 'src-hit');
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
    /* A2 修复：模态对话框焦点陷阱 */
    if(e.key==='Tab'){
      var sm=document.getElementById('shareModal');
      if(sm&&sm.classList.contains('open')){_trapFocus(sm,e);return;}
      var rd=document.getElementById('reader2');
      if(document.body.classList.contains('reading')&&rd){_trapFocus(rd,e);return;}
      var sp=document.getElementById('srcPanel');
      if(document.body.classList.contains('src-open')&&sp){_trapFocus(sp,e);return;}
    }
    if(e.target.tagName==='INPUT') return;
    if(e.key==='/'){var gs=document.getElementById('globalSearch');if(gs){gs.focus();}return;}
    if(e.key==='d'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){var bt=document.getElementById('btnTheme');if(bt)bt.click();return;}
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
    var p='#view='+(filter.type==='cat'?'cat&c='+Object.keys(filter.cats).join(','):filter.type==='src'?'src&s='+encodeURIComponent(filter.src):filter.type==='discover'?'discover':'all');
    try{history.replaceState(null,'',p);}catch(e){}
  }
  function restoreFromHash(){
    var h=(location.hash||'').replace(/^#/,'');if(!h)return false;
    var p={};h.split('&').forEach(function(kv){var s=kv.split('=');if(s[0])p[s[0]]=decodeURIComponent(s[1]||'');});
    if(p.view==='cat'&&p.c){var cats={};p.c.split(',').forEach(function(x){if(x)cats[x]=true;});filter={type:'cat',cats:cats};return true;}
    if(p.view==='src'&&p.s){filter={type:'src',src:p.s};return true;}
    if(p.view==='discover'){filter={type:'discover'};return true;}
    return false;
  }

  /* ── Init ── */
  var restored = restoreFromHash();
  /* 启动：chunk0 在 body 末尾同步加载（此时 DOM 已渲染，骨架可见不白屏）。
     不依赖数据的部分先行；数据到达后渲染首屏；chunk1 后台静默合并。 */
  loadBookmarks(); initFontSize(); updateHash();
  var _bootEl=document.getElementById('bootLoading');
  function _bootFinish(){ if(_bootEl&&_bootEl.parentNode)_bootEl.parentNode.removeChild(_bootEl); }
  function _bootWith(cs){
    SOURCES=cs||[];
    buildArt();
    renderChips(); renderWall(); renderPanel(); updateTitle(); updateUnreadBtn(); updateBmBtn();
    _bootFinish();
    /* 让首屏先稳定可交互，再在空闲时依次加载后台分块 chunk1/2/3...，避免一次性加载阻塞主线程 */
    var _loadRest=function(){
      var _loaded=0;
      var _loadNext=function(idx){
        loadChunk(idx).then(function(){
          if(window.__CHUNKS&&window.__CHUNKS[idx]){
            var n=_mergeChunk(window.__CHUNKS[idx]);
            _loaded+=n;
          }
          // 尝试加载下一个 chunk
          _loadNext(idx+1);
        }).catch(function(e){
          // chunk 不存在或加载失败
          if(idx===1){
            // chunk1 是必需的，缺失则警告
            if(!(window.__CHUNKS&&window.__CHUNKS[1])){
              console.warn('[starhub] chunk1 onload 但 __CHUNKS[1] 缺失（文件截断或内容异常）');
              toast('剩余内容数据异常，刷新页面可重试');
              return;
            }
          }
          // 所有 chunk 加载完成
          if(_loaded>0){
            toast('已加载全部 '+ART.length+' 篇内容（新增 '+_loaded+' 篇）');
          }
        });
      };
      _loadNext(1);
    };
    if(window.requestIdleCallback)window.requestIdleCallback(_loadRest,{timeout:5000});
    else setTimeout(_loadRest,1200);
  }
  /* chunk0 同款守卫（复审 P2）：onload 不等于数据完好，截断/损坏时显式报错而非静默空站 */
  function _bootFail(msg){_bootFinish();console.warn('[starhub]',msg);var w=document.getElementById('wall');if(w)w.innerHTML='<div class="empty-hint">'+msg+'</div>';}
  if(window.__CHUNKS&&window.__CHUNKS[0]&&window.__CHUNKS[0].sources&&window.__CHUNKS[0].sources.length){try{_bootWith(window.__CHUNKS[0].sources);}catch(e){console.warn('[starhub] boot 异常:',e);_bootFail('首屏渲染异常，请刷新重试');}}
  else if(window.__CHUNKS&&window.__CHUNKS[0]){_bootFail('首屏数据异常，请刷新重试');}
  else{loadChunk(0).then(function(){
        var _cs=window.__CHUNKS&&window.__CHUNKS[0]&&window.__CHUNKS[0].sources;
        if(!_cs||!_cs.length){_bootFail('首屏数据异常，请刷新重试');return;}
        try{_bootWith(_cs);}catch(e){console.warn('[starhub] boot 异常:',e);_bootFail('首屏渲染异常，请刷新重试');}}).catch(function(e){
    _bootFail('内容加载失败，请检查网络后刷新重试');
  });}
  /* 无限滚动：接近底部自动加载更多（带节流锁） */
  var _scrollLock=false;
  window.addEventListener('scroll',function(){
    if(_scrollLock)return;
    var list=visibleArts();
    if(wallLimit>=list.length)return;
    var wrap=document.querySelector('.wall-wrap');
    if(!wrap)return;
    if(wrap.getBoundingClientRect().bottom<window.innerHeight*3){
      _scrollLock=true;
      loadMore();
      setTimeout(function(){_scrollLock=false;},150);
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

  /* 旧“同域快照替换”机制已移除：chunk0+chunk1 已包含同一构建的全量数据，
     快照（约 30MB）冗余下载且与 chunk1 合并存在竞态——若快照先整体替换
     src.items、chunk1 后无去重 concat，同源同链文章会全部重复。 */

  /* ── Refresh: 后台增量更新 —— 不整页 reload，避免重新下载18MB 页面导致长时间白屏 ── */
  var _refreshing=false, _lastTotal=ART.length;
  /* ── Dynamic relative time: computed from a.date at render time, never frozen ─ */
  /* 日期缺失时 a.date 由 first_seen（首次收录时刻）降级而来，见 _fallback_date_iso；
     这类条目必须与「发布时间」区分显示，不能把收录时间冒充成发布时间。 */
  function _dynTime(a){
    var s=_dynTimeCore(a);
    return (a&&a.dfb&&s)?('\u6536\u5f55 '+s):s;
  }
  function _dynTimeCore(a) {
    if (!a || !a.date) return a && a.time ? a.time : '';
    // bad_date: pub_date 不可信（构建时自动检测：wechat类目/日期倒挂/抓取时间冒充），显示绝对日期
    if (a.bad_date) {
      var d = new Date(a.date);
      if (!isNaN(d.getTime())) {
        var mo = (d.getMonth()+1).toString().padStart(2,'0');
        var da = d.getDate().toString().padStart(2,'0');
        var hh = d.getHours().toString().padStart(2,'0');
        var mm = d.getMinutes().toString().padStart(2,'0');
        return mo + '-' + da + ' ' + hh + ':' + mm;
      }
      return a.time || '';
    }
    var d = new Date(a.date);
    if (isNaN(d.getTime())) return a.time || '';
    var diff = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (diff < 60) return '\u521a\u521a';
    if (diff < 3600) return Math.floor(diff / 60) + ' \u5206\u949f\u524d';
    if (diff < 86400) return Math.floor(diff / 3600) + ' \u5c0f\u65f6\u524d';
    if (diff < 172800) return '\u6628\u5929';
    return Math.floor(diff / 86400) + ' \u5929\u524d';
  }
  function _fmtRel(dstr){
    if(!dstr) return '';
    var d=new Date(dstr); if(isNaN(d.getTime())) return '';
    var diff=(Date.now()-d.getTime())/1000; if(diff<0) diff=0;
    if(diff<60) return '刚刚';
    if(diff<3600) return Math.floor(diff/60)+' 分钟前';
    if(diff<86400) return Math.floor(diff/3600)+' 小时前';
    if(diff<172800) return '昨天';
    return Math.floor(diff/86400)+' 天前';
  }
    /* ── 数据分块加载与合并（rss-data-0/1.js）── */
  function loadChunk(i){
    return new Promise(function(resolve,reject){
      try{
        if(window.__CHUNKS&&window.__CHUNKS[i])return resolve();
        var sc=document.createElement('script'),done=false;
        /* 大 chunk（37MB 级）在慢网络下下载可超 45s：超时只提示、绝不 reject——
           reject 会让 .catch 静默吞掉合并，数据到位也无人消费（线上实证 bug）；
           onload/onerror 才是脚本状态的唯一事实源 */
        var t=setTimeout(function(){if(!done){toast('内容仍在后台加载，完成后自动合并…');}},45000);
        sc.src='rss-data-'+i+'.js?v='+BUILD_TS;
        sc.onload=function(){if(!done){done=true;clearTimeout(t);resolve();}};
        sc.onerror=function(){if(!done){done=true;clearTimeout(t);reject(new Error('chunk '+i+' fail'));}};
        try{document.head.appendChild(sc);}catch(e){clearTimeout(t);throw e;}
      }catch(e){reject(e);}
    });
  }
  /* 富字段分块合并：chunk1 是构建时从 chunk0 切出的剩余项；
     按 link 去重后追加，正常路径零丢失，防御任何来源的数据重叠 */
  function _mergeChunk(pack){
    try{
      var cs=pack&&pack.sources;if(!cs||!cs.length)return 0;
      var idx={};SOURCES.forEach(function(s,i){idx[s.key]=i;});
      var added=0;
      cs.forEach(function(s){
        if(!s||!s.items||!s.items.length)return;
        var i=idx[s.key];
        var _have={};
        if(i!==undefined)SOURCES[i].items.forEach(function(_it){if(_it&&_it.link)_have[_it.link]=1;});
        /* 无 link 的 item 保留，只过滤已知重复 link，避免任何丢数据 */
        var fresh=s.items.filter(function(_it){return _it&&(!_it.link||!_have[_it.link]);});
        if(!fresh.length)return;
        if(i===undefined){s.items=fresh;SOURCES.push(s);idx[s.key]=SOURCES.length-1;added+=fresh.length;return;}
        SOURCES[i].items=SOURCES[i].items.concat(fresh);
        added+=fresh.length;
      });
      /* EV-16 修复：后台合并后仅对新增内容交织，首屏已见内容不换位 */
      if(added>0){buildArt();
        var _oldLimit=wallLimit;
        if(sortMode!=='diverse') tierInterleave();
        wallLimit=Math.min(ART.length,Math.max(wallLimit,120));
        renderChips();renderWall();renderPanel();
        /* 恢复用户已滚动到的位置，避免已见内容换位 */
        if(_oldLimit>WALL_STEP) wallLimit=Math.max(wallLimit,_oldLimit);
      }
      return added;
    }catch(e){console.warn('[starhub] chunk 合并失败（数据在 __CHUNKS，刷新可重试）:', e);return 0;}
  }
  function _mergeRemoteSources(j){
    try{
      if(!j||!j.sources||!j.sources.length) return 0;
      var known={}; for(var i=0;i<ART.length;i++) known[artKey(ART[i])]=1;
      var added=[];
      j.sources.forEach(function(s){
        if(!s||!s.items||!s.items.length) return;
        s.items.forEach(function(it){
          if(!it||!it.u||it.u==='#') return;
          var a={t:it.t_zh||it.t||'', s:it.s||'', src:s.name, sk:s.key, c:s.cat, sc:s.color, ti:s.tier||3,
                 time:_fmtRel(it.d), date:it.d||'', u:it.u, fc:it.fc||'', img:it.img||'', mu:it.mu||'', mt:it.mt||'', bad_date:!!it.bad_date, dfb:!!it.date_fallback, tags:_tagsOf(it)};
          // 远程通道日期钳制：未来日期回拉到 now
          if (a.date) {
            var _at = new Date(a.date).getTime();
            if (!isNaN(_at) && _at > Date.now()) {
              a.date = new Date(Date.now()).toISOString();
            }
          }
          if(!a.t) return;
          var k=artKey(a);
          if(known[k]) return;
          known[k]=1; added.push(a);
        });
      });
      if(!added.length){
        /* 无新增内容时也要纠错：若可见首屏混入无日期条目（NaN 置顶缺陷的指纹），
           重新规范化排序。健康状态下该分支不触发，因此不会造成可见跳变。
           例外：quality 模式按源质量重排，天然会把高质量源的无日期条目顶回首屏，
           谓词会恒真 → 每次刷新都重渲染，故排除该模式。 */
        var _head=Math.min(ART.length, wallLimit||0), _bad=0;
        for(var h=0;h<_head;h++){ var _d=ART[h].date; if(!_d||isNaN(new Date(_d).getTime())) _bad++; }
        if(sortMode!=='quality' && _head>0 && _bad*2>_head){ applySort(); renderChips(); renderWall(); renderPanel(); }
        return 0;
      }
      ART = added.concat(ART);
      /* 不再对 added 单独预排序：紧接着的 applySort() 会对整个 ART 重排，
         预排序对最终顺序无影响（原为 localeCompare，已随口径统一移除） */
      applySort();
      if(sortMode!=='diverse') tierInterleave();
      wallLimit=Math.min(ART.length, Math.max(wallLimit, WALL_STEP));
      window.ART = ART;
      return added.length;
    }catch(e){ return 0; }
  }
  function _applyRemote(j, manual){
    var n=_mergeRemoteSources(j);
    _lastTotal=ART.length;
    if(n>0){
      renderChips(); renderWall(); renderPanel();
    }
    return n;
  }
  /* Fix P2: 分批实时刷新 —— T1 实时 + T2/T3 分批抓取，逐批合并渲染 */
  var _API_BASE='https://starhub-refresh.vercel.app/api/rss';
  window.refreshRss=function(manual){
    if(manual===undefined) manual=true;
    if(_refreshing){ if(manual) toast('正在刷新中…'); return; }
    _refreshing=true;
    var btn=document.getElementById('refreshBtn');
    if(btn) btn.classList.add('loading');
    if(manual) toast('正在实时刷新…');
    var totalAdded=0, done=false;
    var ctrl=window.AbortController?new AbortController():null;
    /* 整体超时 3 分钟（T1 + 多批 T2/T3） */
    var timer=setTimeout(function(){
      if(done) return; done=true;
      if(ctrl) ctrl.abort(); _refreshing=false;
      if(btn) btn.classList.remove('loading');
      if(manual) toast(totalAdded>0?'已更新 '+totalAdded+' 篇（部分批次超时）':'刷新超时');
      if(totalAdded>0){ renderChips(); renderWall(); renderPanel(); }
    }, 180000);
    function fetchJson(url){
      return fetch(url, ctrl?{signal:ctrl.signal}:{}).then(function(r){
        if(!r.ok) throw new Error('HTTP '+r.status);
        return r.json();
      });
    }
    /* Step 1: T1 实时刷新 */
    fetchJson(_API_BASE+'?refresh=1').then(function(j){
      if(done) return;
      totalAdded+=_applyRemote(j, false);
      _lastTotal=ART.length;
      if(totalAdded>0){ renderChips(); renderWall(); renderPanel(); }
      /* Step 2: 获取批次信息 */
      return fetchJson(_API_BASE+'?batch_info=1');
    }).then(function(info){
      if(done) return;
      if(!info||!info.totalBatches) throw new Error('no batch info');
      if(manual) toast('T1 完成，正在抓取 T2/T3（0/'+info.totalBatches+' 批）…');
      /* Step 3: 逐批抓取 T2/T3 */
      var chain=Promise.resolve();
      for(var b=0;b<info.totalBatches;b++){
        (function(batchIdx){
          chain=chain.then(function(){
            if(done) return;
            return fetchJson(_API_BASE+'?batch='+batchIdx).then(function(bj){
              if(done) return;
              var n=_applyRemote(bj, false);
              totalAdded+=n;
              _lastTotal=ART.length;
              if(n>0){ renderChips(); renderWall(); renderPanel(); }
              if(manual) toast('实时刷新 '+((batchIdx+1)*100/info.totalBatches).toFixed(0)+'%…');
            });
          });
        })(b);
      }
      return chain;
    }).then(function(){
      if(done) return; done=true;
      clearTimeout(timer); _refreshing=false;
      if(btn) btn.classList.remove('loading');
      if(manual) toast(totalAdded>0?'已更新 '+totalAdded+' 篇新文章':'已是最新内容');
    }).catch(function(err){
      if(done) return; done=true;
      clearTimeout(timer); _refreshing=false;
      if(btn) btn.classList.remove('loading');
      console.warn('[refreshRss] error:', err);
      if(manual) toast(totalAdded>0?'已更新 '+totalAdded+' 篇（部分失败）':'刷新失败，请稍后重试');
      if(totalAdded>0){ renderChips(); renderWall(); renderPanel(); }
    });
  };
  /* 自动刷新：每 5 分钟用轻量 meta 接口探测新构建，仅当有新内容时才拉取合并（页面隐藏时跳过） */
  setInterval(function(){
    if(document.hidden || _refreshing) return;
    fetch(_API_BASE+'?meta=1').then(function(r){ return r.ok?r.json():null; }).then(function(m){
      if(!m || typeof m.total!=='number') return;
      if(m.total>_lastTotal) window.refreshRss(false);
    }).catch(function(){});
  }, 5*60*1000);

  /* ══════════════════════════════════════════
     Share module: Canvas card + QR code + modal
     ══════════════════════════════════════════ */
  var _qrLoaded=typeof qrcode==='function', _shareDataURL='', _toastTimer;
  function toast(msg){var t=document.getElementById('toast');if(!t)return;t.textContent=msg;t.classList.add('show');clearTimeout(_toastTimer);_toastTimer=setTimeout(function(){t.classList.remove('show');},2000);}
  function copyArticleInfo(k){
    var a=ART.find(function(x){return artKey(x)===k;});
    if(!a)return;
    var text=(a.t||'')+'\\n'+(a.u&&a.u!=='#'?a.u:'');
    function done(){toast('\u5df2\u590d\u5236\u6807\u9898\u4e0e\u94fe\u63a5');}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(done).catch(function(){
        try{var ta=document.createElement('textarea');ta.value=text;ta.style.cssText='position:fixed;left:-9999px';document.body.appendChild(ta);ta.select();if(document.execCommand('copy'))done();else toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236');document.body.removeChild(ta);}catch(e){toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236');}
      });
    } else {
      try{var ta2=document.createElement('textarea');ta2.value=text;ta2.style.cssText='position:fixed;left:-9999px';document.body.appendChild(ta2);ta2.select();if(document.execCommand('copy'))done();else toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236');document.body.removeChild(ta2);}catch(e){toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236');}
    }
  }

  /* QR 库已构建时内嵌（typeof qrcode==='function' 即同步可用）；
     此函数仅作为内嵌缺失时的 CDN 兜底，带 8s 超时防止 CDN 挂起 */
  function loadQRLib(){
    if(_qrLoaded) return Promise.resolve();
    return new Promise(function(resolve,reject){
      var settled=false;
      var timer=setTimeout(function(){ if(!settled){settled=true;reject(new Error('qr cdn timeout'));} },8000);
      var s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js';
      s.onload=function(){_qrLoaded=true;settled=true;clearTimeout(timer);resolve();};
      s.onerror=function(){
        if(settled)return;
        var s2=document.createElement('script');
        s2.src='https://unpkg.com/qrcode-generator@1.4.4/qrcode.min.js';
        s2.onload=function(){_qrLoaded=true;settled=true;clearTimeout(timer);resolve();};
        s2.onerror=function(){ if(!settled){settled=true;clearTimeout(timer);reject(new Error('qr cdn failed'));} };
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

  // Strip HTML tags → plain text, preserve paragraph breaks
  function stripHtmlForCanvas(html){
    if(!html) return '';
    var t = html;
    // Remove script/style
    t = t.replace(/<script[\s\S]*?<\/script>/gi, '');
    t = t.replace(/<style[\s\S]*?<\/style>/gi, '');
    // Block elements → double newline
    t = t.replace(/<\/?\s*(p|div|blockquote|pre|h[1-6]|li|tr|br)\s*[^>]*>/gi, '\\n');
    // Inline images → alt text or [image]
    t = t.replace(/<img[^>]*alt\s*=\s*"([^"]*)"[^>]*>/gi, ' $1 ');
    t = t.replace(/<img[^>]*>/gi, ' [\u56fe\u7247] ');
    // Links → keep text
    t = t.replace(/<a[^>]*>([\s\S]*?)<\/a>/gi, '$1');
    // Remaining tags
    t = t.replace(/<[^>]+>/g, '');
    // HTML entities
    t = t.replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
         .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
         .replace(/&#\d+;/g, '').replace(/&[a-z]+;/gi, '');
    // Collapse whitespace within lines, keep paragraph breaks
    t = t.split('\\n').map(function(l){ return l.replace(/\s+/g, ' ').trim(); }).filter(function(l){ return l.length > 0; }).join('\\n');
    return t.trim();
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

  function drawShareCard(a, fullText){
    var W=750, PAD=40, GAP_T=28, GAP_S=16, GAP_M=24;
    var c=document.createElement('canvas');
    var ctx=c.getContext('2d');
    var col=getThemeColors();
    var font=getComputedStyle(document.body).fontFamily;
    var catColor=a.sc||'#2f5d8a';
    if(document.documentElement.dataset.theme==='dark') catColor=adjColor(a.sc||'#8fb3d9');

    // ─ Resolve content: full text preferred, fallback to summary ──
    var BODY_FONT = 14;
    var BODY_LH = 1.7;
    var MAX_CONTENT_CHARS = 3000;
    var MAX_LINES = 78; /* 限制画布高度，超出移动端 canvas 尺寸上限会导致绘制空白 */
    var contentText = '';
    var useFull = false;
    if(fullText && fullText.length > 60){
      useFull = true;
      contentText = fullText;
      if(contentText.length > MAX_CONTENT_CHARS){
        contentText = contentText.slice(0, MAX_CONTENT_CHARS);
        var lastNl = contentText.lastIndexOf('\\n');
        if(lastNl > MAX_CONTENT_CHARS * 0.7) contentText = contentText.slice(0, lastNl);
        contentText += '\\n\\n\u2026\u2026 \u5168\u6587\u8bf7\u626b\u63cf\u4e8c\u7ef4\u7801\u9605\u8bfb';
      }
    }

    // ── Measure pass ──
    ctx.font='26px '+font;
    var titleLines=wrapText(ctx, a.t||'\u65e0\u6807\u9898\u6587\u7ae0', W-PAD*2);
    var titleH=titleLines.length*(26*1.45);
    var contentLines=[];
    var contentH=0;
    if(useFull){
      ctx.font=BODY_FONT+'px '+font;
      var paras = contentText.split('\\n');
      for(var pi=0;pi<paras.length;pi++){
        var pLines = wrapText(ctx, paras[pi], W-PAD*2);
        for(var li=0;li<pLines.length;li++) contentLines.push(pLines[li]);
        if(pi<paras.length-1) contentLines.push(''); // blank line between paragraphs
      }
      if(contentLines.length > MAX_LINES){
        contentLines = contentLines.slice(0, MAX_LINES);
        contentLines.push('');
        contentLines.push('\u2026\u2026 \u5168\u6587\u8bf7\u626b\u63cf\u4e8c\u7ef4\u7801\u9605\u8bfb');
      }
      contentH = contentLines.length * (BODY_FONT * BODY_LH);
    } else {
      ctx.font='15px '+font;
      if(a.s) contentLines=wrapText(ctx, a.s, W-PAD*2);
      contentH = contentLines.length*(15*1.7);
    }
    var H=PAD+50+GAP_T+titleH+GAP_S+contentH+(contentH>0?GAP_M:0)+1+GAP_M+110+36;

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

    // ── Content: full text or summary ──
    if(contentLines.length){
      if(useFull){
        ctx.font=BODY_FONT+'px '+font;
        ctx.fillStyle=col.summary;
        for(var i=0;i<contentLines.length;i++){
          if(contentLines[i]==='') { y+=BODY_FONT*BODY_LH*0.6; continue; }
          ctx.fillText(contentLines[i],PAD,y);
          y+=BODY_FONT*BODY_LH;
        }
      } else {
        ctx.font='15px '+font;
        ctx.fillStyle=col.summary;
        for(var i=0;i<contentLines.length;i++){
          ctx.fillText(contentLines[i],PAD,y);
          y+=15*1.7;
        }
      }
      y+=GAP_M;
    }

    // ── Separator ──
    ctx.strokeStyle=col.line;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PAD,y);ctx.lineTo(W-PAD,y);ctx.stroke();
    y+=GAP_M;

    // ── Bottom: source + QR ─
    ctx.fillStyle=a.sc||'#2f5d8a';
    ctx.beginPath();ctx.arc(PAD+4,y+6,4,0,Math.PI*2);ctx.fill();
    ctx.font='bold 12px '+font;
    ctx.fillStyle=col.title;
    var srcTxt=a.src||'';
    ctx.fillText(srcTxt,PAD+16,y+10);
    ctx.font='12px '+font;
    ctx.fillStyle=col.summary;
    ctx.fillText('\u00b7 '+_dynTime(a),PAD+16+ctx.measureText(srcTxt).width+6,y+10);

    ctx.font='11px '+font;
    ctx.fillStyle=col.brand;
    ctx.fillText('\u957f\u6309\u8bc6\u522b \u00b7 \u9605\u8bfb\u539f\u6587',PAD,y+40);

    var qrSize=90, qrX=W-PAD-qrSize, qrY=y;
    if(typeof qrcode==='function'){
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
    // Gather full text from available sources
    var fullText = '';
    var ftEl = document.querySelector('.r2-fulltext');
    if(ftEl && !a._af) fullText = stripHtmlForCanvas(ftEl.innerText || ftEl.textContent);
    if(!fullText && a.fc && a.fc.length > 100) fullText = stripHtmlForCanvas(a.fc);
    if(!fullText && _articleCache[a.u] && _articleCache[a.u].ok) fullText = stripHtmlForCanvas(_articleCache[a.u].content);

    function doShare(text){
      /* 内嵌 QR 后同步出图：模态框立即弹出，不再等待任何网络请求 */
      var url='';
      try{ url = drawShareCard(a, text); }catch(e){}
      if(btn) btn.classList.remove('loading');
      if(!url){
        /* Canvas 不可用（getContext null / toDataURL 异常）：降级纯文本信息卡 */
        toast('\u56fe\u7247\u751f\u6210\u5931\u8d25\uff0c\u5df2\u8f6c\u4e3a\u6587\u5b57\u5206\u4eab');
        showShareTextCard(a, text);
        return;
      }
      _shareDataURL = url;
      showShareModal(url);
      if(!_qrLoaded) loadQRLib().catch(function(){});
    }

    if(fullText){ doShare(fullText); return; }

    // Fetch full text from API — 3s 超时：vercel 域名国内移动端常不可达，快速降级为摘要分享
    if(a.u && a.u !== '#'){
      var apiBase = 'https://starhub-refresh.vercel.app/api/article';
      var settled=false;
      function once(text){ if(settled)return; settled=true; doShare(text); }
      var ctrl = (typeof AbortController==='function') ? new AbortController() : null;
      var timer = ctrl ? setTimeout(function(){ once(''); }, 3000) : null;
      fetch(apiBase + '?url=' + encodeURIComponent(a.u), ctrl?{signal:ctrl.signal}:{}).then(function(r){ return r.json(); }).then(function(d){
        if(timer) clearTimeout(timer);
        var text='';
        if(d.ok && d.content){
          text = stripHtmlForCanvas(d.content);
          if(_articleCache) _articleCache[a.u] = d;
        }
        once(text);
      }).catch(function(){ if(timer) clearTimeout(timer); once(''); });
    } else {
      doShare('');
    }
  }

  function showShareModal(url){
    var m=document.getElementById('shareModal');
    var img=document.getElementById('shareImg');
    img.src=url; img.style.display='';
    var tc=document.getElementById('shareTextCard');
    if(tc) tc.style.display='none';
    var bs=document.getElementById('btnShareSave'); if(bs) bs.style.display='';
    var bc=document.getElementById('btnShareCopy'); if(bc) bc.style.display='';
    var ct=document.getElementById('btnShareCopyText'); if(ct) ct.style.display='none';
    m.classList.add('open');
    var closeBtn=m.querySelector('.share-close');
    if(closeBtn) closeBtn.focus();
  }

  /* ── Canvas 不可用时的纯文本降级卡 ── */
  function _shareTextCard(a, text){
    var lines=[];
    lines.push('\u3010'+(CAT_LABELS[a.c]||a.c||'')+'\u3011'+(a.t||'\u65e0\u6807\u9898\u6587\u7ae0'));
    lines.push('');
    if(text&&text.length>60){ lines.push(text.slice(0,1500)); lines.push(''); }
    else if(a.s){ lines.push(a.s); lines.push(''); }
    lines.push('\u6765\u6e90\uff1a'+(a.src||'')+(a.time?(' \u00b7 '+a.time):''));
    lines.push('\u539f\u6587\uff1a'+((a.u&&a.u!=='#')?a.u:location.href));
    lines.push('\u2014\u2014 StarHub RSS \u805a\u5408');
    return lines.join('\\n');
  }

  function showShareTextCard(a, text){
    _shareDataURL='';
    var img=document.getElementById('shareImg');
    if(img) img.style.display='none';
    var tc=document.getElementById('shareTextCard');
    if(tc){ tc.textContent=_shareTextCard(a,text); tc.style.display='block'; }
    var bs=document.getElementById('btnShareSave'); if(bs) bs.style.display='none';
    var bc=document.getElementById('btnShareCopy'); if(bc) bc.style.display='none';
    var ct=document.getElementById('btnShareCopyText'); if(ct) ct.style.display='';
    document.getElementById('shareModal').classList.add('open');
  }

  function copyShareText(){
    var tc=document.getElementById('shareTextCard');
    if(!tc||!tc.textContent) return;
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(tc.textContent).then(function(){toast('\u6587\u5b57\u5df2\u590d\u5236');}).catch(function(){toast('\u590d\u5236\u5931\u8d25');});
    } else { toast('\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u590d\u5236'); }
  }

  function closeShareModal(){
    document.getElementById('shareModal').classList.remove('open');
    if(_prevFocusEl){try{_prevFocusEl.focus();}catch(e){}_prevFocusEl=null;}
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

  function copyFullHtml(){
    var a = curArt;
    if(!a){ toast('\u8bf7\u5148\u6253\u5f00\u6587\u7ae0'); return; }
    var ftEl = document.querySelector('.r2-fulltext');
    var contentHtml = '';
    if(ftEl){ contentHtml = ftEl.innerHTML; }
    else if(a.fc && a.fc.length > 100){ contentHtml = a.fc; }
    else if(_articleCache[a.u] && _articleCache[a.u].ok){ contentHtml = _articleCache[a.u].content; }
    var srcName = esc(a.src||'');
    var catLabel = CAT_LABELS[a.c]||a.c;
    var fullHtml = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
      + '<meta name="viewport" content="width=device-width,initial-scale=1">'
      + '<title>' + esc(a.t) + ' \u00b7 StarHub</title>'
      + '<style>'
      + 'body{max-width:720px;margin:40px auto;padding:0 20px;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans SC",sans-serif;line-height:1.8;color:#1c1917;background:#fafaf9;}'
      + '.meta{display:flex;align-items:center;gap:8px;font-size:13px;color:#78716c;margin-bottom:24px;flex-wrap:wrap;}'
      + '.meta .cat{color:#2563eb;font-weight:600;}'
      + '.meta .dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:' + (a.sc||'#78716c') + ';}'
      + 'h1{font-size:28px;font-weight:900;line-height:1.3;margin:0 0 16px;}'
      + 'img{max-width:100%;height:auto;border-radius:8px;margin:16px 0;}'
      + 'p{margin:0 0 16px;}a{color:#2563eb;}blockquote{border-left:3px solid #d6d3d1;padding-left:16px;color:#57534e;margin:16px 0;}'
      + 'pre{background:#f5f5f4;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;}'
      + 'code{background:#f5f5f4;padding:2px 6px;border-radius:4px;font-size:13px;}'
      + '.footer{margin-top:40px;padding-top:20px;border-top:1px solid #e7e5e4;font-size:12px;color:#a8a29e;}'
      + '.footer a{color:#78716c;text-decoration:none;}'
      + '</style></head><body>'
      + '<h1>' + esc(a.t) + '</h1>'
      + '<div class="meta"><span class="cat">' + catLabel + '</span>'
      + '<span class="dot"></span><span>' + srcName + '</span>'
      + '<span>\u00b7</span><span title="' + esc(a.date||'') + '">' + _dynTime(a) + '</span></div>';
    if(contentHtml){ fullHtml += '<div class="content">' + contentHtml + '</div>'; }
    else if(a.s){ fullHtml += '<div class="content"><p>' + esc(a.s) + '</p></div>'; }
    fullHtml += '<div class="footer">\u6765\u6e90\uff1a<a href="' + esc(a.u) + '" target="_blank">' + srcName + ' \u2197</a> \u00b7 StarHub RSS \u805a\u5408</div>'
      + '</body></html>';
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(fullHtml).then(function(){
        toast('\u5168\u6587 HTML \u5df2\u590d\u5236\u5230\u526a\u8d34\u677f');
      }).catch(function(){ _fallbackCopy(fullHtml); });
    } else { _fallbackCopy(fullHtml); }
  }
  function _fallbackCopy(text){
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta); ta.select();
    try{ document.execCommand('copy'); toast('\u5168\u6587 HTML \u5df2\u590d\u5236'); }
    catch(e){ toast('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236'); }
    document.body.removeChild(ta);
  }

  window.shareArticle=shareArticle;
  window.r2ShareClick=function(){ shareArticle(curArt,null,document.querySelector('.r2-share-btn')); };
  window.closeShareModal=closeShareModal;
  window.saveShareImage=saveShareImage;
  window.copyShareImage=copyShareImage;
  window.copyFullHtml=copyFullHtml;
  window.toast=toast;

  /* ══════ AI 动态流面板（AIHOT + AGI Hunt） ══════ */
  var AIHOT_API = 'https://aihot.virxact.com/api/v1/items?mode=all&window=24h&limit=40';
  var AGIHUNT_API = 'https://starhub-refresh.vercel.app/api/agihunt';
  var AIHOT_CATS = {'ai-models':['AI \u6a21\u578b','#2563eb'],'ai-products':['AI \u4ea7\u54c1','#7c3aed'],industry:['\u884c\u4e1a\u52a8\u6001','#0891b2'],paper:['\u8bba\u6587','#d97706'],tip:['\u6280\u5de7\u89c2\u70b9','#dc2626']};
  var afLoaded = false;
  var afItems = [], afCursor = '', afFilter = 'all';
  var afAgiSort = 'hot';  // hot | new
  var afRefreshing = false;
  var AGIHUNT_CHANNELS = [
    ['models','\u6a21\u578b','#2563eb'],['research','\u7814\u7a76','#7c3aed'],['coding-agents','\u7f16\u7a0b&Agent','#059669'],
    ['products','\u5e94\u7528','#b45309'],['multimodal','\u591a\u6a21\u6001','#db2777'],['infra','Infra','#475569'],
    ['hardware','\u5177\u8eab','#0891b2'],['funding','\u521b\u6295','#a16207'],['policy','\u5b89\u5168','#dc2626'],
    ['agi','\u6f2b\u8bddAGI','#c026d3'],['companies','\u516c\u53f8\u548c\u4eba','#4d7c0f'],['fun','Fun','#ea580c']
  ];

  function _escH(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function _normT(s){ return (s||'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,''); }
  // \u68c0\u6d4b\u6807\u9898\u662f\u5426\u4e3b\u8981\u4e3a\u975e\u4e2d\u6587\uff08\u9700\u8981\u7ffb\u8bd1\uff09
  function _needsTranslation(t){ if(!t) return false; var cjk=(t.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g)||[]).length; return cjk < t.replace(/[\s\d\p{P}]/gu,'').length * 0.3; }
  // 批量翻译 AI 动态流英文标题：主力 = 浏览器端 GTX 直连（用户本地 IP，端点响应带 ACAO:* 实证开放；
  // 服务端共享 DC 出口反而会被 Google 频率限流——线上实测 gtx 429）；失败条目再走服务端 API 兜底
  // （api/translate mode:'bulk'：GTX 尽力 → Agnes 限量）。引擎分流策略（用户定版）：Agnes 仅留
  // 给全文/摘要按钮（mode:'full'）与兜底，绝不作为批量主力。
  var TR_API = 'https://starhub-refresh.vercel.app/api/translate';
  // 浏览器 GTX 断路器：连续 2 批全败 → 判定 CORS 完全不可用，后续批次跳过直连，
  // 全部由调用方走服务端 API 兜底（避免每批 8s 超时无意义等待）
  var _bgtxDead=false, _bgtxFailStreak=0;
  // 客户端翻译缓存：localStorage 持久化，回访用户直接命中，不再发任何翻译请求
  var _trCache=(function(){
    try{return JSON.parse(localStorage.getItem('_trCache')||'{}');}catch(e){return {};}
  })();
  function _saveTrCache(){
    try{var s=JSON.stringify(_trCache);if(s.length<400000)localStorage.setItem('_trCache',s);}catch(e){}
  }
  /* 浏览器端 GTX 批量直译：并发 3，返回与 texts 等长的译文数组（失败为 ''，由调用方决定服务端兜底）
     + 客户端缓存命中直接返回 + 断路器触发后跳过直连 */
  function _browserGtx(texts){
    var out=[],uncached=[],uncachedIdx=[];
    // ① 客户端缓存命中：直接填入，不发请求
    for(var k=0;k<texts.length;k++){
      var key=String(texts[k]).slice(0,200),hit=_trCache[key];
      if(hit){out[k]=hit;}else{out[k]='';uncached.push(texts[k]);uncachedIdx.push(k);}
    }
    if(!uncached.length) return Promise.resolve(out);
    // ② 断路器已触发：直接返回空串，由调用方走服务端兜底
    if(_bgtxDead) return Promise.resolve(out);

    var i=0,done=0,batchFail=true;
    return new Promise(function(resolve){
      function one(){
        if(i>=uncached.length) return;
        var idx=i++;
        var ctrl=(typeof AbortController==='function')?new AbortController():null;
        var tmr=ctrl?setTimeout(function(){ctrl.abort();},8000):null;
        fetch('https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q='+encodeURIComponent(String(uncached[idx]).slice(0,500)),{signal:ctrl?ctrl.signal:undefined})
        .then(function(r){ if(tmr)clearTimeout(tmr); return r.ok?r.json():Promise.reject(new Error('gtx '+r.status)); })
        .then(function(j){
          var tr=((j[0]||[]).map(function(x){ return (x&&x[0])||''; }).join('')||'').trim();
          if(tr){ out[uncachedIdx[idx]]=tr; _trCache[String(uncached[idx]).slice(0,200)]=tr; batchFail=false; }
        }).catch(function(){ if(tmr)clearTimeout(tmr); })
        .then(function(){ done++; if(done>=uncached.length){
          if(batchFail){ _bgtxFailStreak++; if(_bgtxFailStreak>=2) _bgtxDead=true; }
          else{ _bgtxFailStreak=0; }
          _saveTrCache();
          resolve(out);
        } else { one(); } });
      }
      for(var w=0;w<Math.min(3,uncached.length);w++) one();
    });
  }
  function _translateAfItems(){
    var toTranslate = afItems.filter(function(it){ return !it._zh && _needsTranslation(it.title); });
    if(!toTranslate.length) return;
    // 每批 15 条（与服务端兜底上限匹配），最多 8 批（120 条，覆盖 AIHOT+AGI 全量）
    var batches = []; for(var i=0;i<toTranslate.length && batches.length<8;i+=15) batches.push(toTranslate.slice(i,i+15));
    var applied = 0;
    function _apply(trs, batch){
      batch.forEach(function(it, idx){
        var zh = (trs[idx]||'').trim();
        if(zh && !it._zh){ it._zh = zh; applied++; }
      });
    }
    /* 服务端兜底：仅浏览器端 GTX 失败的零星条目（TR_API bulk：GTX 尽力 → Agnes 限量） */
    function _serverFallback(texts){
      return new Promise(function(resolve){
        var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
        var tmr = ctrl ? setTimeout(function(){ ctrl.abort(); }, 12000) : null;
        fetch(TR_API, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ texts: texts, mode: 'bulk' }),
          signal: ctrl ? ctrl.signal : undefined
        }).then(function(r){
          if(tmr) clearTimeout(tmr);
          return r.ok ? r.json() : Promise.reject(new Error('http ' + r.status));
        }).then(function(j){
          if(!j || !j.ok || !j.translations || j.translations.length !== texts.length) throw new Error('bad payload');
          resolve(j.translations);
        }).catch(function(){
          if(tmr) clearTimeout(tmr);
          resolve(null);
        });
      });
    }
    // 逐批推进：浏览器直连主力，批间 300ms 温和节奏（服务端仅承接零星失败）
    (async function(){
      for(var b=0;b<batches.length;b++){
        var batch = batches[b];
        var trs = await _browserGtx(batch.map(function(it){ return it.title; }));
        _apply(trs, batch);
        var failed = [];
        trs.forEach(function(z, idx){ if(!z) failed.push(idx); });
        if(failed.length){
          var fb = await _serverFallback(failed.map(function(k){ return batch[k].title; }));
          if(fb) failed.forEach(function(k, fi){ var zh=(fb[fi]||'').trim(); if(zh && !batch[k]._zh){ batch[k]._zh = zh; applied++; } });
        }
        if(b+1<batches.length) await new Promise(function(rs){ setTimeout(rs,300); });
      }
      if(applied) _renderAll();
    })();
  }
  /* ── RSS 卡片墙运行时翻译兜底：构建期翻译熔断/漏网的英文条目，挂载于 renderWall 末尾；
     主力 = 浏览器端 GTX 直连，失败条目走服务端 API 兜底；_zhTried 标记防重复请求，
     完成后重渲染刷新卡片（终止条件：cands 耗尽）。 */
  var _wallTrBusy=0,_wallDirty=0;
  function _scheduleWallTranslate(){ setTimeout(_translateWallItems,120); }
  function _translateWallItems(){
    if(_wallTrBusy) return;
    var cands=ART.filter(function(a){ return !a._zhTried && (_needsTranslation(a.t)||(a.s&&_needsTranslation(a.s))); });
    if(!cands.length) return;
    var batch=cands.slice(0,10);
    batch.forEach(function(a){ a._zhTried=1; });
    _wallTrBusy=1;
    var texts=[],map=[];
    batch.forEach(function(a){
      if(_needsTranslation(a.t)){ texts.push(a.t); map.push({a:a,f:'t'}); }
      if(a.s&&_needsTranslation(a.s)){ texts.push(a.s); map.push({a:a,f:'s'}); }
    });
    if(!texts.length){ _wallTrBusy=0; return; }
    (async function(){
      var trs = await _browserGtx(texts);
      var failed=[];
      trs.forEach(function(zhRaw,idx){
        var m=map[idx]; if(!m) return;
        var zh=(zhRaw||'').trim(); if(!zh){ failed.push(idx); return; }
        if(m.f==='t'&&_needsTranslation(m.a.t)) m.a.t=zh;
        else if(m.f==='s'&&m.a.s&&_needsTranslation(m.a.s)) m.a.s=zh;
      });
      if(failed.length){
        var fbTexts=failed.map(function(k){ return texts[k]; });
        var ctrl=(typeof AbortController==='function')?new AbortController():null;
        var tmr=ctrl?setTimeout(function(){ctrl.abort();},12000):null;
        try{
          var resp=await fetch(TR_API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:fbTexts,mode:'bulk'}),signal:ctrl?ctrl.signal:undefined});
          if(tmr)clearTimeout(tmr);
          var j=(resp&&resp.ok)?(await resp.json().catch(function(){ return null; })):null;
          if(j&&j.ok&&j.translations&&j.translations.length===fbTexts.length){
            fbTexts.forEach(function(_,fi){
              var m=map[failed[fi]]; if(!m) return;
              var zh=(j.translations[fi]||'').trim(); if(!zh) return;
              if(m.f==='t'&&_needsTranslation(m.a.t)) m.a.t=zh;
              else if(m.f==='s'&&m.a.s&&_needsTranslation(m.a.s)) m.a.s=zh;
            });
          }
        }catch(e){ if(tmr)clearTimeout(tmr); }
      }
      _wallDirty=1;
      _wallTrBusy=0;
      if(_wallDirty){ _wallDirty=0; renderWall(); }
      // 批间节流：温和节奏防单 IP 突发高频（失败条目保留原文，下批继续）
      setTimeout(_translateWallItems,2500);
    })();
  }
  function _fmtRel(s){ if(!s) return ''; try{ var d=new Date(s),n=Date.now(),diff=n-d.getTime(); if(diff<0)return ''; var m=Math.floor(diff/60000); if(m<1)return '\u521a\u521a'; if(m<60)return m+' \u5206\u949f\u524d'; var h=Math.floor(m/60); if(h<24)return h+' \u5c0f\u65f6\u524d'; return Math.floor(h/24)+' \u5929\u524d'; }catch(e){return '';} }

  function toggleAiFeed(){
    var open = document.body.classList.toggle('ai-open');
    document.getElementById('btnAiFeed').classList.toggle('on', open);
    var hb=document.getElementById('btnHot'); if(hb) hb.classList.toggle('on', open && afTab==='hot');
    if(open && !afLoaded) _loadAll();
  }
  window.toggleAiFeed = toggleAiFeed;

  /* ── 刷新（参照主页 refreshRss 模式） ── */
  function refreshAiFeed(){
    /* D6: 热榜 Tab 下刷新热榜数据 */
    if(afTab==='hot'){
      _hotLoaded=false; _hotLoading=false;
      loadHotSnapshot();
      return;
    }
    if(afRefreshing) return;
    if(!afLoaded) { _loadAll(); return; }
    afRefreshing = true;
    var btn = document.getElementById('afRefreshBtn');
    if(btn) btn.classList.add('loading');
    var settled = false;
    var timer = setTimeout(function(){
      if(settled) return; settled = true; afRefreshing = false;
      if(btn) btn.classList.remove('loading');
    }, 30000);
    _loadAll(true).then(function(){
      if(settled) return; settled = true; afRefreshing = false;
      clearTimeout(timer);
      if(btn) btn.classList.remove('loading');
    }).catch(function(){
      if(settled) return; settled = true; afRefreshing = false;
      clearTimeout(timer);
      if(btn) btn.classList.remove('loading');
    });
  }
  window.refreshAiFeed = refreshAiFeed;



  /* ── 统一加载 AIHOT + AGI Hunt（渐进式渲染：先到先渲染，全部加超时兜底） ── */
  async function _loadAll(isRefresh){
    var list = document.getElementById('afList');
    var upd = document.getElementById('afUpdated');
    if(!isRefresh){
      list.innerHTML = '<div class="af-loading"><span class="af-spin"></span> \u52a0\u8f7d\u4e2d\u2026</div>';
      upd.textContent = '\u52a0\u8f7d\u4e2d\u2026';
    }
    var seen = new Set();
    var merged = [];
    var rendered = false;

    // \u2460 AIHOT \u8bf7\u6c42\uff1a\u8d85\u65f6 10s\uff08\u79fb\u52a8\u7aef\u5f31\u7f51\u5146\u5e95\uff09
    var aiCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var aiTimer = aiCtrl ? setTimeout(function(){ aiCtrl.abort(); }, 10000) : null;
    var aihotP = fetch(AIHOT_API, aiCtrl ? { signal: aiCtrl.signal } : {}).then(function(r){
      if(!r.ok) throw new Error('http '+r.status);
      return r.json();
    }).then(function(j){
      if(aiTimer) clearTimeout(aiTimer);
      afCursor = (j.page&&j.page.hasMore) ? (j.page.nextCursor||'') : '';
      (j.items||[]).forEach(function(it){
        var k=_normT(it.title);
        if(!seen.has(k)){seen.add(k); merged.push(Object.assign({},it,{_src:'aihot'}));}
      });
      // AIHOT \u5148\u5230\u5148\u6e32\u67d3\uff0c\u4e0d\u7b49 AGI Hunt
      if(!rendered && merged.length){
        rendered = true;
        afItems = merged.slice();
        afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
        _renderAll();
        _translateAfItems();
        upd.textContent = 'AI \u52a8\u6001\u6d41 \u00b7 ' + afItems.length + ' \u6761 \u00b7 \u66f4\u65b0\u4e8e ' + new Date().toLocaleTimeString('zh-CN',{hour12:false});
      }
    }).catch(function(){ if(aiTimer) clearTimeout(aiTimer); afCursor=''; });

    // \u2461 AGI Hunt \u8bf7\u6c42\uff08\u987a\u5e8f\u8bf7\u6c42\uff0c\u907f\u514d\u79fb\u52a8\u7aef\u5e76\u53d1\u8fde\u63a5\u69fd\u6392\u961f\uff09\uff1a\u5355\u8bf7\u6c42 5s \u8d85\u65f6 + \u603b\u8d85\u65f6 30s
    var agiCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var agiTimer = agiCtrl ? setTimeout(function(){ agiCtrl.abort(); }, 30000) : null;
    var today = new Date(Date.now()+8*3600000).toISOString().slice(0,10);
    var agihuntP = (async function(){
      for(var ci=0; ci<AGIHUNT_CHANNELS.length; ci++){
        if(agiCtrl && agiCtrl.signal.aborted) break;
        var ch = AGIHUNT_CHANNELS[ci];
        var chCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
        var chTimer = chCtrl ? setTimeout(function(){ chCtrl.abort(); }, 5000) : null;
        try{
          var r = await fetch(AGIHUNT_API+'?channel='+ch[0]+'&day='+today+'&sort='+afAgiSort,
            chCtrl ? { signal: chCtrl.signal } : (agiCtrl ? { signal: agiCtrl.signal } : {}));
          if(chTimer) clearTimeout(chTimer);
          if(!r.ok) continue;
          var j = await r.json();
          (j&&j.items||[]).forEach(function(it){
            var k=_normT(it.title);
            if(!seen.has(k)){seen.add(k); merged.push(Object.assign({},it,{_src:'agihunt',_ch:ch[0]}));}
          });
        }catch(e){ if(chTimer) clearTimeout(chTimer); }
      }
      if(agiTimer) clearTimeout(agiTimer);
    })();

    // \u7b49\u5f85 AIHOT + AGI Hunt \u5168\u90e8 settle\uff08\u5404\u81ea\u5df2\u6709\u8d85\u65f6\u4fdd\u62a4\uff09
    await Promise.allSettled([aihotP, agihuntP]);
    afItems = merged;
    afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
    afLoaded = true;
    _renderAll();
    _translateAfItems();
    if(!afItems.length){
      upd.textContent = 'AI \u52a8\u6001\u6d41';
      list.innerHTML = '<div class="af-empty">\u6682\u65e0\u52a8\u6001\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5</div>';
    } else {
      upd.textContent = 'AI \u52a8\u6001\u6d41 \u00b7 ' + afItems.length + ' \u6761 \u00b7 \u66f4\u65b0\u4e8e ' + new Date().toLocaleTimeString('zh-CN',{hour12:false});
    }

    // \u2462 \u5f02\u6b65\u8ffd\u52a0 /api/news\uff1a\u8d85\u65f6 12s
    var newsCtrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var newsTimer = newsCtrl ? setTimeout(function(){ newsCtrl.abort(); }, 12000) : null;
    fetch('https://starhub-refresh.vercel.app/api/news', newsCtrl ? { signal: newsCtrl.signal } : {}).then(function(r){
      if(newsTimer) clearTimeout(newsTimer);
      return r.ok?r.json():null;
    }).then(function(nj){
      if(!nj||!nj.items||!nj.items.length) return;
      var cutoff=Date.now()-24*3600000;
      var seen2=new Set(afItems.map(function(x){return _normT(x.title);}));
      nj.items.filter(function(it){return it.title&&it.link&&(!it.publishedAt||new Date(it.publishedAt).getTime()>=cutoff);})
        .slice(0,15).forEach(function(it){
          var k=_normT(it.title); if(!seen2.has(k)){seen2.add(k);
            afItems.push({title:it.title,category:'industry',source:{name:it.source||'36\u6c2a'},links:{original:it.link},publishedAt:it.publishedAt||'',selected:false,_src:'aihot'});
          }
        });
      afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
      _renderAll();
    }).catch(function(){ if(newsTimer) clearTimeout(newsTimer); });
  }

  /* ── AI 动态条目 → 分享卡片 ART 结构（复用卡片墙分享链路） ── */
  function _afToArt(it){
    if(!it) return null;
    if(it._src==='agihunt'){
      var chInfo = AGIHUNT_CHANNELS.filter(function(c){return c[0]===it._ch;})[0];
      return {t:it.title||'', s:'', c:chInfo?chInfo[1]:'AGI Hunt', sc:(chInfo&&chInfo[2])||'#6366f1',
        src:it.author||'AGI Hunt', u:it.url||'', time:_fmtRel(it.published_at), _af:true};
    }
    var ci = AIHOT_CATS[it.category] || ['\u52a8\u6001','#8b949e'];
    return {t:it.title||'', s:'', c:ci[0], sc:ci[1],
      src:(it.source&&it.source.name)||'AIHOT', u:(it.links&&(it.links.original||it.links.aihot))||'',
      time:_fmtRel(it.publishedAt), _af:true};
  }

  function _renderAll(){
    var list = document.getElementById('afList');
    var filterBox = document.getElementById('afFilter');
    var moreBtn = document.getElementById('afLoadMore');
    // 筛选条：全部 / AIHOT分类 / AGI Hunt频道
    var filtered = afItems;
    if(afFilter !== 'all'){
      if(afFilter.startsWith('ch:')){
        var ch = afFilter.slice(3);
        filtered = afItems.filter(function(it){return it._ch===ch;});
      } else {
        filtered = afItems.filter(function(it){return it._src==='aihot'&&it.category===afFilter;});
      }
    }
    if(afItems.length){
      filterBox.style.display = '';
      var chips = [['all','\u5168\u90e8',afItems.length]];
      // AIHOT 分类
      Object.keys(AIHOT_CATS).forEach(function(k){
        var n = afItems.filter(function(it){return it._src==='aihot'&&it.category===k;}).length;
        if(n) chips.push([k,AIHOT_CATS[k][0],n]);
      });
      // AGI Hunt 频道
      AGIHUNT_CHANNELS.forEach(function(c){
        var n = afItems.filter(function(it){return it._ch===c[0];}).length;
        if(n) chips.push(['ch:'+c[0],c[1],n]);
      });
      filterBox.innerHTML = chips.map(function(c){
        return '<button class="fchip'+(afFilter===c[0]?' on':'')+'" data-cat="'+c[0]+'">'+c[1]+' <span class="n">'+c[2]+'</span></button>';
      }).join('');
      // AGI Hunt 排序切换（仅选中频道时显示）
      if(afFilter.indexOf('ch:')===0){
        filterBox.innerHTML += '<button class="fchip" data-sort="'+(afAgiSort==='hot'?'new':'hot')+'" style="margin-left:auto">'+(afAgiSort==='hot'?'\u2192 \u6700\u65b0':'\u2192 \u6700\u70ed')+'</button>';
      }
      filterBox.querySelectorAll('.fchip').forEach(function(chip){
        chip.addEventListener('click', function(){
          var cat = chip.getAttribute('data-cat');
          if(cat){ afFilter=cat; _renderAll(); }
          var sort = chip.getAttribute('data-sort');
          if(sort){ afAgiSort=sort; _refetchAgiChannel(); }
        });
      });
    } else { filterBox.style.display = 'none'; }
    // 列表
    if(!filtered.length){ list.innerHTML = '<div class="af-empty">\u6682\u65e0\u52a8\u6001</div>'; moreBtn.style.display='none'; return; }
    list.innerHTML = filtered.map(function(it, i){
      var isAgi = it._src==='agihunt';
      var cat, url, src, tm;
      if(isAgi){
        var chInfo = AGIHUNT_CHANNELS.filter(function(c){return c[0]===it._ch;})[0];
        cat = [chInfo?chInfo[1]:'\u52a8\u6001',(chInfo&&chInfo[2])||'#6366f1'];
        url = it.url || '#';
        src = it.author || 'AGI Hunt';
        tm = _fmtRel(it.published_at);
      } else {
        cat = AIHOT_CATS[it.category] || ['\u52a8\u6001','#8b949e'];
        url = (it.links&&(it.links.original||it.links.aihot)) || '#';
        src = (it.source&&it.source.name)||'';
        tm = _fmtRel(it.publishedAt);
      }
      var title = it._zh || it.title || '';
      return '<div class="af-item"><span class="cat" style="color:'+cat[1]+';background:'+cat[1]+'1a">'+_escH(cat[0])+'</span>'
        +'<div class="body"><a class="t" href="'+_escH(url)+'" target="_blank" rel="noopener" title="'+_escH(it.title||'')+'">'+_escH(title)+'</a>'
        +'<span class="meta">'+_escH(src)+(src&&tm?' \u00b7 ':'')+_escH(tm)+(it.selected?' \u00b7 \u2605 \u7cbe\u9009':'')+'</span></div>'
        +'<button class="af-share" data-i="'+i+'" title="\u5206\u4eab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button></div>';
    }).join('');
    // 分享：转为 ART 结构后走统一分享链路（全文 API + 3s 超时降级摘要）
    list.querySelectorAll('.af-share').forEach(function(btn){
      btn.addEventListener('click', function(ev){
        ev.preventDefault(); ev.stopPropagation();
        var art = _afToArt(filtered[parseInt(btn.getAttribute('data-i'),10)]||null);
        if(art) shareArticle(art, null, btn);
      });
    });
    moreBtn.style.display = (afCursor && afFilter==='all') ? '' : 'none';
  }

  // 加载更多（仅 AIHOT 游标分页）
  document.getElementById('afLoadMore').addEventListener('click', async function(){
    var btn = this; if(!afCursor) return;
    btn.disabled = true; btn.textContent = '\u52a0\u8f7d\u4e2d\u2026';
    try{
      var r = await fetch(AIHOT_API + '&cursor=' + encodeURIComponent(afCursor));
      if(!r.ok) throw new Error('http '+r.status);
      var j = await r.json();
      afCursor = (j.page&&j.page.hasMore) ? (j.page.nextCursor||'') : '';
      var seen = new Set(afItems.map(function(x){return _normT(x.title);}));
      (j.items||[]).forEach(function(it){var k=_normT(it.title);if(!seen.has(k)){seen.add(k);afItems.push(Object.assign({},it,{_src:'aihot'}));}});
      _renderAll();
      _translateAfItems();
    }catch(e){ /* ignore */ }
    btn.disabled = false; btn.textContent = '\u52a0\u8f7d\u66f4\u591a';
  });

  /* ── 重取当前 AGI Hunt 频道（排序切换） ── */
  async function _refetchAgiChannel(){
    var ch = afFilter.slice(3);
    var today = new Date(Date.now()+8*3600000).toISOString().slice(0,10);
    try{
      var r = await fetch(AGIHUNT_API+'?channel='+ch+'&day='+today+'&sort='+afAgiSort);
      if(!r.ok) return;
      var j = await r.json();
      var newItems = (j&&j.items||[]).map(function(it){return Object.assign({},it,{_src:'agihunt',_ch:ch});});
      afItems = afItems.filter(function(it){return !(it._src==='agihunt'&&it._ch===ch);});
      var seen = new Set(afItems.map(function(x){return _normT(x.title);}));
      newItems.forEach(function(it){
        var k=_normT(it.title);
        if(!seen.has(k)){seen.add(k); afItems.push(it);}
      });
      afItems.sort(function(a,b){return (b.publishedAt||b.published_at||'').localeCompare(a.publishedAt||a.published_at||'');});
      _renderAll();
      _translateAfItems();
    }catch(e){ /* ignore */ }
  }

  /* ── 自动刷新：每 5 分钟（面板打开时；桌面端 ≥1280px 常驻侧栏始终视为打开） ── */
  function _aiDesktop(){ return window.matchMedia('(min-width:1280px)').matches; }
  setInterval(function(){
    if(document.hidden || afRefreshing) return;
    if(!document.body.classList.contains('ai-open') && !_aiDesktop()) return;
    refreshAiFeed();
  }, 5*60*1000);
  /* 桌面端常驻侧栏：进入页面即加载 AI 动态（移动端保持点击按钮后加载） */
  if(_aiDesktop() && !afLoaded) _loadAll();

  /* ══════════════════════════════════════════
     面板 Tab：AI 快讯 / 全网热榜
     ══════════════════════════════════════════ */
  var afTab='feed';
  var _hotLoaded=false,_hotLoading=false,_hotData=null;
  function switchAfTab(tab){
    afTab=tab;
    document.body.classList.toggle('af-tab-hot',tab==='hot');
    var tf=document.getElementById('afTabFeed'),th=document.getElementById('afTabHot');
    if(tf){tf.classList.toggle('on',tab==='feed');tf.setAttribute('aria-selected',tab==='feed'?'true':'false');}
    if(th){th.classList.toggle('on',tab==='hot');th.setAttribute('aria-selected',tab==='hot'?'true':'false');}
    var hw=document.getElementById('hpWrap');
    if(hw) hw.style.display=(tab==='hot')?'flex':'none';
    var rb=document.getElementById('afRefreshBtn'); if(rb) rb.style.display=''; /* D6: 双 Tab 均显示刷新按钮 */
    var hb=document.getElementById('btnHot'); if(hb) hb.classList.toggle('on',tab==='hot'&&document.body.classList.contains('ai-open'));
    if(tab==='hot'&&!_hotLoaded) loadHotSnapshot();
  }
  window.switchAfTab=switchAfTab;
  var _hotPlatformNames={weibo:'微博',zhihu:'知乎',baidu:'百度',bilibili:'B站',douyin:'抖音',ithome:'IT之家',hackernews:'Hacker News',github:'GitHub',solidot:'Solidot',sspai:'少数派',juejin:'掘金',v2ex:'V2EX',producthunt:'Product Hunt',aihot:'AIHOT',chongbuluo:'虫部落',pcbeta:'远景论坛',nowcoder:'牛客',coolapk:'酷安',xueqiu:'雪球',zaobao:'联合早报',wallstreetcn:'华尔街见闻',cls:'财联社',jin10:'金十数据',gelonghui:'格隆汇',fastbull:'法布财经',toutiao:'今日头条',tencent:'腾讯新闻',thepaper:'澎湃新闻',ifeng:'凤凰网',cankaoxiaoxi:'参考消息',sputniknewscn:'卫星通讯社',kaopu:'靠谱',mktnews:'市场资讯',douban:'豆瓣',tieba:'贴吧',hupu:'虎扑',steam:'Steam',iqiyi:'爱奇艺',qqvideo:'腾讯视频',dongqiudi:'懂球帝'};
  /* dot：平台品牌色（未选中态圆点，提供平台色差区分）；deep：选中态实底色（加深变体，白字对比 ≥4.4:1，明暗主题均可读） */
  var _hotPlatformColors={weibo:'#ff4400',zhihu:'#0066ff',baidu:'#2932e1',bilibili:'#fb7299',douyin:'#fe2c55',ithome:'#d32f2f',hackernews:'#ff6600',github:'#6e5491',solidot:'#4caf50',sspai:'#da3325',juejin:'#1e80ff',v2ex:'#778087',producthunt:'#da552f',aihot:'#0891b2',chongbuluo:'#558b2f',pcbeta:'#1565c0',nowcoder:'#0097a7',coolapk:'#10b981',xueqiu:'#1e88e5',zaobao:'#c62828',wallstreetcn:'#1565c0',cls:'#0277bd',jin10:'#ef6c00',gelonghui:'#00897b',fastbull:'#f57c00',toutiao:'#d32f2f',tencent:'#1976d2',thepaper:'#c62828',ifeng:'#e64a19',cankaoxiaoxi:'#ad1457',sputniknewscn:'#283593',kaopu:'#2e7d32',mktnews:'#4e342e',douban:'#007722',tieba:'#4caf50',hupu:'#d32f2f',steam:'#1b2838',iqiyi:'#00be07',qqvideo:'#ff6900',dongqiudi:'#2e7d32'};
  var _hotPlatformDeep={weibo:'#d5380f',zhihu:'#0052cc',baidu:'#1f28b8',bilibili:'#c73a6c',douyin:'#d9284a',ithome:'#b71c1c',hackernews:'#cc5200',github:'#4a3769',solidot:'#2e7d32',sspai:'#b71c1c',juejin:'#1565c0',v2ex:'#5a5f66',producthunt:'#b5441f',aihot:'#067090',chongbuluo:'#33691e',pcbeta:'#0d47a1',nowcoder:'#006064',coolapk:'#047857',xueqiu:'#1565c0',zaobao:'#8e0000',wallstreetcn:'#0d47a1',cls:'#01579b',jin10:'#e65100',gelonghui:'#00695c',fastbull:'#ef6c00',toutiao:'#b71c1c',tencent:'#0d47a1',thepaper:'#8e0000',ifeng:'#bf360c',cankaoxiaoxi:'#78002e',sputniknewscn:'#1a237e',kaopu:'#1b5e20',mktnews:'#3e2723',douban:'#004400',tieba:'#2e7d32',hupu:'#b71c1c',steam:'#0d1117',iqiyi:'#007a07',qqvideo:'#cc5400',dongqiudi:'#1b5e20'};
  /* 分类筛选：key→中文名，members 为平台 ID 数组 */
  var _hotCats=[
    {key:'all',name:'\u5168\u90e8',members:[]},
    {key:'hot',name:'\u70ed\u641c',members:['weibo','zhihu','baidu','bilibili','douyin']},
    {key:'tech',name:'\u79d1\u6280',members:['ithome','hackernews','github','solidot','sspai','juejin','v2ex','producthunt','aihot','chongbuluo','pcbeta','nowcoder','coolapk']},
    {key:'biz',name:'\u8d22\u7ecf',members:['xueqiu','zaobao','wallstreetcn','cls','jin10','gelonghui','fastbull']},
    {key:'news',name:'\u8d44\u8baf',members:['toutiao','tencent','thepaper','ifeng','cankaoxiaoxi','sputniknewscn','kaopu','mktnews']},
    {key:'life',name:'\u751f\u6d3b',members:['douban','tieba','hupu','steam','iqiyi','qqvideo','dongqiudi']}
  ];
  var _hotCatKey='all';
  window.toggleHotPanel=function(){
    var panelOpen=document.body.classList.contains('ai-open');
    if(panelOpen&&afTab==='hot'){toggleAiFeed();return;} /* 已在热榜 Tab→再次点击关闭抽屉（移动端习惯） */
    if(!panelOpen) toggleAiFeed();
    switchAfTab('hot');
  };
  var _platExpanded=false;
  function _applyPlatCollapse(){
    var row=document.getElementById('hpTabs');
    if(row) row.classList.toggle('collapsed',window.innerWidth<900&&!_platExpanded);
  }
  /* 平台→分类映射：根据平台 ID 返回所属分类 key */
  function _platCat(p){
    for(var i=0;i<_hotCats.length;i++){
      if(_hotCats[i].members&&_hotCats[i].members.indexOf(p)!==-1) return _hotCats[i].key;
    }
    return 'all';
  }
  function loadHotSnapshot(){
    if(_hotLoading || _hotLoaded) return;
    _hotLoading=true;
    var list=document.getElementById('hotList');
    if(!list) return;
    list.innerHTML=\'<div class="hp-empty">加载中…</div>\';
    fetch(\'hot_snapshot.json\',{cache:\'no-cache\'}).then(function(r){
      if(!r.ok) throw new Error(\'HTTP \'+r.status);
      return r.json();
    }).then(function(data){
      _hotLoaded=true;_hotLoading=false;
      _hotData=(data||[]).filter(function(s){return s.items&&s.items.length;});
      if(!_hotData.length){list.innerHTML=\'<div class="hp-empty">\u6682\u65e0\u70ed\u699c\u6570\u636e</div>\';return;}
      /* 分类筛选行 → 分段控件（WS-A2） */
      var segEl=document.getElementById(\'hpCats\');
      if(segEl){
        segEl.className=\'hp-seg\';
        segEl.setAttribute(\'role\',\'tablist\');
        segEl.innerHTML=_hotCats.map(function(c){
          return \'<button class="hp-seg-btn\'+(c.key===\'all\'?\' on\':\'\')+\'" role="tab" aria-selected="\'+(c.key===\'all\')+\'" data-cat="\'+c.key+\'">\'+c.name+\'</button>\';
        }).join(\'\');
        segEl.querySelectorAll(\'.hp-seg-btn\').forEach(function(b){
          b.addEventListener(\'click\',function(){_filterHotCat(b.getAttribute(\'data-cat\'));});
        });
      }
      /* 平台 chips（WS-A3） */
      var row=document.getElementById(\'hpTabs\');
      row.className=\'plat-row collapsed\';
      row.innerHTML=_hotData.map(function(s){
        var p=s.platform;
        return \'<button class="plat-chip" data-p="\'+p+\'" data-cat="\'+_platCat(p)+\'"><span class="dot" style="background:\'+(_hotPlatformColors[p]||\'#888\')+\'"></span>\'+(_hotPlatformNames[p]||p)+\'</button>\';
      }).join(\'\');
      /* 展开/收起按钮（WS-A4 移动端折叠） */
      var moreHtml=\'<button class="plat-more" id="btnPlatMore" aria-expanded="false"><span>全部 \'+_hotData.length+\' 个</span>\';
      moreHtml+=\'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg></button>\';
      var wrap=row.parentNode.querySelector(\'.plat-wrap\');
      if(wrap){var existing=document.getElementById(\'btnPlatMore\');if(!existing) row.insertAdjacentHTML(\'afterend\',moreHtml);}
      var moreBtn=document.getElementById(\'btnPlatMore\');
      if(moreBtn){
        moreBtn.onclick=function(){
          _platExpanded=!_platExpanded;
          row.classList.toggle(\'collapsed\',window.innerWidth<900&&!_platExpanded);
          moreBtn.querySelector(\'span\').textContent=_platExpanded?\'收起\':\'全部 \'+_visiblePlats().length+\' 个\';
          moreBtn.classList.toggle(\'open\',_platExpanded);
          moreBtn.setAttribute(\'aria-expanded\',_platExpanded);
        };
      }
      row.querySelectorAll(\'.plat-chip\').forEach(function(b){
        b.addEventListener(\'click\',function(){renderHotPlat(b.getAttribute(\'data-p\'),true);});
      });
      renderHotPlat(_hotData[0].platform);
      _applyPlatCollapse();
    }).catch(function(){
      _hotLoading=false;
      list.innerHTML=\'<div class="hp-empty">加载失败，请稍后重试</div>\';
    });
  }
  function _visiblePlats(){
    return _hotData.filter(function(s){return _hotCatKey===\'all\'||_platCat(s.platform)===_hotCatKey;});
  }
  /* 分类筛选：切换平台 chips 可见性（WS-A5 交互反馈） */
  function _filterHotCat(cat){
    _hotCatKey=cat;
    var segEl=document.getElementById(\'hpCats\');
    if(segEl) segEl.querySelectorAll(\'.hp-seg-btn\').forEach(function(b){
      var on=b.getAttribute(\'data-cat\')===cat;
      b.classList.toggle(\'on\',on);
      b.setAttribute(\'aria-selected\',on);
    });
    var chips=document.getElementById(\'hpTabs\');
    var firstVisible=null;
    chips.querySelectorAll(\'.plat-chip\').forEach(function(b){
      var show=(cat===\'all\'||b.getAttribute(\'data-cat\')===cat);
      b.style.display=show?\'\':\'none\';
      if(show&&!firstVisible) firstVisible=b;
    });
    /* 更新展开按钮计数 */
    var moreBtn=document.getElementById(\'btnPlatMore\');
    if(moreBtn&&!_platExpanded){
      var vis=_visiblePlats();
      moreBtn.querySelector(\'span\').textContent=\'全部 \'+vis.length+\' 个\';
    }
    /* 如果当前选中的平台被隐藏，自动切到第一个可见平台（带 fade 反馈） */
    var curChip=chips.querySelector(\'.plat-chip.on\');
    if(curChip&&curChip.style.display===\'none\'&&firstVisible){
      renderHotPlat(firstVisible.getAttribute(\'data-p\'),true);
    }
    /* 分类切换后平台行滚回起点 */
    chips.scrollLeft=0;
  }
  function renderHotPlat(p,swap){
    var chips=document.getElementById(\'hpTabs\');
    chips.querySelectorAll(\'.plat-chip\').forEach(function(b){
      var on=b.getAttribute(\'data-p\')===p;
      b.classList.toggle(\'on\',on);
      b.style.background=on?(_hotPlatformDeep[p]||\'#555\'):\'\';
    });
    var list=document.getElementById(\'hotList\');
    var src=null;
    for(var i=0;i<_hotData.length;i++){ if(_hotData[i].platform===p){src=_hotData[i];break;} }
    if(!src){list.innerHTML=\'<div class="hp-empty">暂无热榜数据</div>\';return;}
    var h=\'\';
    var platTrends=(ANALYSIS_DATA&&ANALYSIS_DATA.hot_trends&&ANALYSIS_DATA.hot_trends[p])||{};
    for(var j=0;j<src.items.length;j++){
      var it=src.items[j],rk=it.rank||(j+1),cls=rk<=3?\' top3\':\'\';
      var hotTxt=it.hot?(\'\'+it.hot).replace(/^(\d+)(\d{4,})$/,function(m,a,b){return a+\'\u4e07\';}):\'\';
      h+=\'<a class="hp-item" href="\'+_escH(it.url||\'#\')+\'" target="_blank" rel="noopener">\';
      h+=\'<span class="hp-rank\'+cls+\'">\'+rk+\'</span>\';
      h+=\'<span class="hp-title">\'+_escH(it.title||\'\')+\'</span>\';
      if(hotTxt) h+=\'<span class="hp-hot">\'+hotTxt+\'</span>\';
      var td=platTrends[it.title||\'\'];
      if(td&&td.trend===\'rising\') h+=\'<span class="hp-trend t-up">\u2191\'+td.rise+\'</span>\';
      else if(td&&td.trend===\'falling\') h+=\'<span class="hp-trend t-down">\u2193\'+Math.abs(td.rise)+\'</span>\';
      else if(td&&td.trend===\'new\') h+=\'<span class="hp-trend t-new">\u65b0</span>\';
      h+=\'</a>\';
    }
    list.innerHTML=h||\'<div class="hp-empty">暂无热榜数据</div>\';
    /* 分类切换 fade 动画（WS-A5） */
    if(swap&&!matchMedia(\'(prefers-reduced-motion:reduce)\').matches){
      list.classList.remove(\'hp-swap\');void list.offsetWidth;list.classList.add(\'hp-swap\');
    }
  }
  window.addEventListener('resize',function(){ _applyPlatCollapse(); });

  /* ── Insight Panel（每日洞察 · WS-B 容器化） ── */
  var _insightScrollY=0;
  function toggleInsight(){
    var panel=document.getElementById('insightPanel');
    var btn=document.getElementById('btnInsight');
    if(!panel)return;
    var opening=!panel.classList.contains('open');
    if(opening){ renderInsight(); }
    panel.classList.toggle('open',opening);
    if(btn){
      btn.classList.toggle('on',opening);
      btn.setAttribute('aria-expanded',opening);
    }
    /* 遮罩 + 滚动锁 */
    var scrim=document.getElementById('scrim');
    if(scrim) scrim.classList.toggle('on',opening);
    if(opening){
      _insightScrollY=window.scrollY;
      document.body.style.overflow='hidden';
      panel.querySelector('.ip-close').focus();
    } else {
      document.body.style.overflow='';
      window.scrollTo(0,_insightScrollY);
      if(btn) btn.focus();
    }
  }
  window.toggleInsight=toggleInsight;
  function closeInsight(){
    var p=document.getElementById('insightPanel');
    if(p&&p.classList.contains('open')) toggleInsight();
  }

  function renderInsight(){
    var el=document.getElementById('insightBody');
    if(!el||!ANALYSIS_DATA)return;
    var d=ANALYSIS_DATA, h='';
    /* D2: SVG 图标替代 emoji，与站内线性图标体系一致 */
    var _ico={chart:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-6"/></svg>',bell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',signal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/><path d="M22 4v16"/></svg>',clock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',search:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>',bolt:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',crystal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',tag:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>',flame:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:13px;height:13px"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>'};
    /* WS-C 前端去重兆底 */
    var _dedupSeen=new Set(), _dedupCount=0;
    function _dedup(text){ var t=String(text||'').trim(); if(!t) return ''; var key=t.slice(0,120); if(_dedupSeen.has(key)){_dedupCount++;return '';} _dedupSeen.add(key);return t; }
    /* signals 规范化 */
    function _normSignals(raw){
      return (Array.isArray(raw)?raw:[]).map(function(s){
        if(s&&typeof s==='object') return {signal:s.signal||s.label||s.name||s.text||'',conf:s.confidence};
        var m=String(s).match(/['"]?signal['"]?\s*:\s*['"]([^'"]+)['"]/);
        var c=String(s).match(/['"]?confidence['"]?\s*:\s*([\d.]+)/);
        return {signal:m?m[1]:String(s),conf:c?parseFloat(c[1]):null};
      }).filter(function(x){return x.signal;});
    }
    // 统计摘要
    if(d.stats||d.generated_at){
      h+='<div class="ib-stats">';
      if(d.stats){
        h+='<span>'+_ico.chart+' \u6587\u7ae0: '+d.stats.total_articles+'</span>';
        h+='<span>'+_ico.bell+' \u8fd124h: '+d.stats.recent_count+'</span>';
        h+='<span>'+_ico.signal+' \u4fe1\u6e90: '+d.stats.source_count+'</span>';
      }
      if(d.generated_at) h+='<span>'+_ico.clock+' '+(d.generated_at||'').slice(0,16).replace('T',' ')+'</span>';
      /* D3 轻量场：标注深度分析时间（generated_at 即为上次重分析时间） */
      if(d.stale) h+='<span style="color:var(--faint,#94a3b8)">\U0001f50d \u6df1\u5ea6\u5206\u6790: '+(d.generated_at||'').slice(11,16)+'</span>';
      h+='</div>';
      h+='<div style="font-size:10.5px;color:var(--faint);padding:0 0 6px;">\u6570\u636e\u8303\u56f4: \u8fd1 72 \u5c0f\u65f6\u6eda\u52a8\u7a97\u53e3</div>';
    }
    // AI 摘要（支持结构化 dict 和旧格式 string）
    if(d.summary){
      if(typeof d.summary==='object'&&!Array.isArray(d.summary)){
        h+='<div class="ib-section"><div class="ib-label">AI 情报分析</div>';
        h+='<div class="ib-sub-grid">';
        var sections=[
          {k:'core_trends',cls:'sub-core',l:'\u6838\u5fc3\u6001\u52bf'},
          {k:'signals',cls:'sub-signal',l:'\u5f02\u52a8\u4fe1\u53f7'},
          {k:'rss_insights',cls:'sub-rss',l:'RSS\u6d1e\u5bdf'},
          {k:'outlook',cls:'sub-outlook',l:'\u7814\u5224\u5efa\u8bae'}
        ];
        sections.forEach(function(s){
          if(d.summary[s.k]){
            h+='<div class="ib-sub-section '+s.cls+'">';
            h+='<div class="ib-sub-label">'+s.l+'</div>';
            h+='<div class="ib-sub-text">'+esc(d.summary[s.k])+'</div>';
            h+='</div>';
          }
        });
        h+='</div></div>';
      } else if(typeof d.summary==='string'){
        h+='<div class="ib-section"><div class="ib-label">AI \u6458\u8981</div>';
        h+='<div class="ib-summary">'+esc(d.summary)+'</div></div>';
      }
    }
    // \u6df1\u5ea6\u6d1e\u5bdf (deep_insights)
    if(d.deep_insights){
      var di=d.deep_insights;
      if(di.narrative){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.search+' \u53d9\u4e8b\u8109\u7edc</div>';
        h+='<div class="ib-narrative">'+esc(di.narrative)+'</div></div>';
      }
      if(di.causal_chains&&di.causal_chains.length){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.bolt+' \u56e0\u679c\u94fe</div><div class="ib-chain-grid">';
        di.causal_chains.forEach(function(c){
          h+='<div class="ib-chain-card">';
          if(typeof c==='string'){
            h+='<div class="ib-chain-steps">'+esc(c)+'</div>';
          } else {
            h+='<div class="ib-chain-title">'+esc(c.title||c.name||'\u56e0\u679c\u5173\u7cfb')+'</div>';
            h+='<div class="ib-chain-steps">'+esc(c.chain||c.description||'')+'</div>';
          }
          h+='</div>';
        });
        h+='</div></div>';
      }
      if(di.signals&&di.signals.length){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.signal+' \u4fe1\u53f7\u770b\u677f</div><div class="ib-signal-grid">';
        di.signals.forEach(function(s){
          h+='<div class="ib-signal-card">'+esc(s.label||s.name||s.text||s.signal||'')+'</div>';
        });
        h+='</div></div>';
      }
      if(di.outlook){
        h+='<div class="ib-section"><div class="ib-label">'+_ico.crystal+' \u8d8b\u52bf\u5c55\u671b</div>';
        h+='<div class="ib-outlook">'+esc(di.outlook)+'</div></div>';
      }
    }
    // \u8bdd\u9898\u805a\u7c7b (topic_clusters)
    if(d.topic_clusters&&d.topic_clusters.length){
      var maxCnt=0;
      d.topic_clusters.forEach(function(c){if(c.count>maxCnt)maxCnt=c.count;});
      h+='<div class="ib-section"><div class="ib-label">'+_ico.chart+' \u8bdd\u9898\u805a\u7c7b</div><div class="ib-cluster-list">';
      d.topic_clusters.slice(0,12).forEach(function(c){
        var pct=maxCnt>0?Math.round(c.count/maxCnt*100):0;
        h+='<div class="ib-cluster-card" data-kw="'+esc(c.label||'')+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<div class="ib-cluster-head"><span class="ib-cluster-label">'+esc(c.label||'\u672a\u547d\u540d')+'</span>';
        h+='<span class="ib-cluster-count">'+c.count+' \u7bc7</span></div>';
        h+='<div class="ib-cluster-bar"><div class="ib-cluster-bar-fill" style="width:'+pct+'%"></div></div>';
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 热门关键词（带生命周期标记）
    if(d.keywords&&d.keywords.global&&d.keywords.global.length){
      var risingSet={};
      if(d.rising) d.rising.forEach(function(r){risingSet[r.word]=r.rise;});
      var kwTraj=(d.rss_trajectories&&d.rss_trajectories.keywords)||{};
      h+='<div class="ib-section"><div class="ib-label">\u70ed\u95e8\u5173\u952e\u8bcd</div><div class="ib-kw-list">';
      d.keywords.global.slice(0,30).forEach(function(kw,idx){
        var w=kw[0],score=kw[1],isRising=risingSet[w];
        var traj=kwTraj[w]||{};
        var lc=traj.lifecycle||'';
        var tip='#'+(idx+1)+' \u5f97\u5206:'+score.toFixed(2);
        if(isRising) tip+=' (\u4e0a\u5347'+isRising+'\u4f4d)';
        if(lc) tip+=' | \u8f68\u8ff9:'+lc;
        if(traj.first_seen) tip+=' | \u9996\u6b21:'+traj.first_seen.slice(5,16).replace('T',' ');
        if(traj.duration) tip+=' | \u6301\u7eed:'+traj.duration+'\u5468\u671f';
        var cls='ib-kw';
        if(lc==='emergent') cls+=' kw-emergent kw-tag';
        else if(lc==='rising') cls+=' kw-rising kw-tag';
        else if(lc==='peaking') cls+=' kw-peaking kw-tag';
        else if(lc==='declining') cls+=' kw-declining kw-tag';
        else if(lc==='gone') cls+=' kw-gone kw-tag';
        else if(isRising) cls+=' rising';
        h+='<span class="'+cls+'" data-kw="'+esc(w)+'" title="'+tip+'" onclick="insightSearch(this.dataset.kw)">'+esc(w)+'</span>';
      });
      h+='</div></div>';
    }
    // 升温关键词
    if(d.rising&&d.rising.length){
      h+='<div class="ib-section"><div class="ib-label">\u2b06\ufe0f 升温词</div><div class="ib-kw-list">';
      d.rising.forEach(function(r){
        h+='<span class="ib-kw rising" data-kw="'+esc(r.word)+'" onclick="insightSearch(this.dataset.kw)" title="排名上升 '+r.rise+' 位">'+esc(r.word)+'</span>';
      });
      h+='</div></div>';
    }
    // 今日话题
    if(d.topics&&d.topics.length){
      h+='<div class="ib-section"><div class="ib-label">今日话题</div><div class="ib-topic-list">';
      d.topics.slice(0,12).forEach(function(t,i){
        var rk=i+1, cls=rk<=3?' top3':'';
        var tl=(t.label||(t.labels&&t.labels.length?t.labels.join(' '):''));
        var src=t.sources?(Array.isArray(t.sources)?t.sources.length:t.sources):0;
        h+='<div class="ib-topic" data-kw="'+esc(tl)+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<span class="ib-topic-rank'+cls+'">'+rk+'</span>';
        h+='<span class="ib-topic-title">'+esc(tl)+'</span>';
        h+='<span class="ib-topic-meta">'+t.count+' 篇 · '+src+' 源</span>';
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 话题趋势（跨周期轨迹）— 只展示有轨迹信号的话题，与「今日话题」差异化
    var topicTraj=(d.rss_trajectories&&d.rss_trajectories.topics)||{};
    if(d.topics&&d.topics.length&&Object.keys(topicTraj).length>0){
      var trendTopics=[];
      d.topics.forEach(function(t){
        var tl=(t.label||(t.labels&&t.labels.length?t.labels.join(' '):''));
        var traj=topicTraj[tl];
        if(traj&&(traj.lifecycle||traj.latest_count)) trendTopics.push({topic:t,label:tl,traj:traj});
      });
      trendTopics.sort(function(a,b){return (b.traj.latest_count||0)-(a.traj.latest_count||0);});
      if(trendTopics.length>0){
        h+='<div class="ib-section ib-trend"><div class="ib-trend-title">\U0001f4c8 \u8bdd\u9898\u8d8b\u52bf</div><div class="ib-trend-list">';
        trendTopics.slice(0,8).forEach(function(item){
          var t=item.topic,tl=item.label,traj=item.traj;
          var lc=traj.lifecycle||'emerging';
          var cnt=traj.latest_count||t.count||0;
          var arrow='', arrowCls='';
          if(lc==='hot'){arrow='\U0001f525';arrowCls='t-hot';}
          else if(lc==='emerging'){arrow='\u2b06';arrowCls='t-up';}
          else if(lc==='cooling'){arrow='\u2b07';arrowCls='t-down';}
          else if(lc==='cold'){arrow='\u2744';arrowCls='t-down';}
          var lcLabel={emerging:'\u65b0\u5174',hot:'\u706b\u7206',cooling:'\u964d\u6e29',cold:'\u51b7\u5374'}[lc]||lc;
          h+='<div class="ib-trend-item" data-kw="'+esc(tl)+'" onclick="insightSearch(this.dataset.kw)">';
          h+='<span class="ib-trend-label">'+esc(tl)+'</span>';
          h+='<span class="ib-trend-count">'+cnt+'\u7bc7</span>';
          if(arrow) h+='<span class="ib-trend-arrow '+arrowCls+'">'+arrow+'</span>';
          h+='<span class="ib-trend-lc lc-'+lc+'">'+lcLabel+'</span>';
          h+='</div>';
        });
        h+='</div></div>';
      }
    }
    // 跨平台共振
    if(d.cross_platform&&d.cross_platform.length){
      h+='<div class="ib-section ib-cross"><div class="ib-label">\u8de8\u5e73\u53f0\u5171\u632f</div><div class="ib-cross-list">';
      d.cross_platform.slice(0,8).forEach(function(m){
        h+='<div class="ib-cross-item">';
        if(m.platforms&&m.platforms.length){
          h+='<span class="ib-cross-label">'+esc(m.label)+'</span>';
          h+='<span class="ib-cross-plats">';
          m.platforms.forEach(function(p){
            h+='<span class="ib-cross-plat">'+esc(p.name)+'</span>';
          });
          h+='</span>';
        } else {
          h+='<span class="ib-cross-label">'+esc(m.title_a||m.label||'')+'</span>';
          h+='<span class="ib-cross-plats">';
          h+='<span class="ib-cross-plat">'+esc(m.platform_a||'')+'</span>';
          h+='<span class="ib-cross-plat">'+esc(m.platform_b||'')+'</span>';
          h+='</span>';
        }
        h+='</div>';
      });
      h+='</div></div>';
    }
    // 跨分类热点
    if(d.cross_category&&d.cross_category.length){
      h+='<div class="ib-section ib-ccat"><div class="ib-label">\U0001f310 \u8de8\u5206\u7c7b\u70ed\u70b9</div><div class="ib-ccat-list">';
      d.cross_category.slice(0,12).forEach(function(cc){
        h+='<div class="ib-ccat-item" data-kw="'+esc(cc.keyword)+'" onclick="insightSearch(this.dataset.kw)">';
        h+='<span class="ib-ccat-kw">'+esc(cc.keyword)+'</span>';
        h+='<span class="ib-ccat-cats">';
        cc.categories.forEach(function(c){
          h+='<span class="ib-ccat-cat">'+esc(c)+'</span>';
        });
        h+='</span></div>';
      });
      h+='</div></div>';
    }
    if(!h) h='<div class="ib-no-data">\u6682\u65e0\u5206\u6790\u6570\u636e</div>';
    /* WS-C 去重提示 */
    if(_dedupCount>0) h+='<div class="ip-dedup"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M20 6L9 17l-5-5"/></svg>\u5df2\u81ea\u52a8\u8df3\u8fc7 '+_dedupCount+' \u6bb5\u4e0e\u4e0a\u6587\u91cd\u590d\u7684\u5185\u5bb9</div>';
    el.innerHTML=h;
    /* 锚点导航（WS-B2） */
    var navEl=document.getElementById('ipNav');
    if(navEl){
      var secs=el.querySelectorAll('.ib-section, .ip-sec');
      var navHtml='';
      secs.forEach(function(s,i){
        var label=(s.querySelector('.ib-label, .ip-label')||{}).textContent||'';
        if(!label) return;
        if(!s.id) s.id='ip-sec-'+i;
        navHtml+='<button data-t="'+s.id+'" class="'+(i===0?'on':'')+'">'+label+'</button>';
      });
      navEl.innerHTML=navHtml;
      navEl.querySelectorAll('button').forEach(function(b){
        b.onclick=function(){
          navEl.querySelectorAll('button').forEach(function(x){x.classList.remove('on');});
          b.classList.add('on');
          var target=document.getElementById(b.dataset.t);
          if(target) target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
        };
      });
    }
  }

  function insightSearch(keyword){
    var bg=null;
    // 长标签（话题/趋势）→ 提取字符二元组做模糊匹配
    var clean=keyword.replace(/^\[RSS\/\w+\]\s*/,'');
    if(clean.length>15){
      var low=clean.toLowerCase(),arr=[];
      for(var i=0;i<low.length-1;i++){
        var c=low[i],n=low[i+1];
        if(c.trim()&&n.trim()&&c!==n) arr.push(c+n);
      }
      var seen={},uniq=[];
      arr.forEach(function(b){if(!seen[b]){seen[b]=1;uniq.push(b);}});
      if(uniq.length>=2) bg=uniq;
    }
    var si=document.getElementById('globalSearch');
    if(si){si.value=keyword;si.dispatchEvent(new Event('input'));}
    // input handler 会重置 _topicBigrams=null，所以在 dispatch 之后赋值
    _topicBigrams=bg;
    window.scrollTo({top:0,behavior:'smooth'});
    setTimeout(function(){
      var first=document.querySelector('.wall .card');
      if(first) first.scrollIntoView({behavior:'smooth',block:'center'});
    },150);
  }
  window.insightSearch=insightSearch;

})();
</script>
"""


# ──────────────────────────── 数据分块 ────────────────────────────

CHUNK0_SIZE = 360  # 首屏块文章数（复刻前端 ART 排序后取前 N 篇）

def _chrono_key(item):
    """切块排序键：按解析后的**绝对时间**降序（与前端 _dateCmpDesc 同口径）。

    不能直接比 pub_date 字符串：数据里 "+08:00" 与 "+00:00/Z" 混用，字符串比较是
    时区盲的（实测 "…T09:00:00+08:00" 会被判为比 "…T02:00:00+00:00" 更新，导致首屏
    选片选错）。无日期/非法日期返回 (0, 0) → 一律沉底进 chunk1。
    """
    s = item.get("pub_date") or ""
    try:
        d = datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return (0, 0.0)
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))  # 裸值按北京时间
    try:
        return (1, d.timestamp())
    except (OverflowError, OSError, ValueError):
        return (0, 0.0)


def _split_data_chunks(sources, chunk0_size=CHUNK0_SIZE):
    """把全量文章拆成两块：首屏 chunk0 按严格时间排序（不交织），
    后台 chunk1 包含剩余文章；前端合并 chunk1 后再应用 tier 交织。
    两块均保持 sources 富字段结构，前端可原样消费。"""
    flat = []
    for s in sources:
        for it in s.get("items", []):
            flat.append((s, it))
    flat.sort(key=lambda x: _chrono_key(x[1]), reverse=True)
    seen = set()
    c0_items = {}
    for s, it in flat[:chunk0_size]:
        seen.add(id(it))
        c0_items.setdefault(s.get("key"), []).append(it)
    chunk0, chunk1 = [], []
    for s in sources:
        k = s.get("key")
        # 标记 BestBlogs 源（URL 含 bestblogs.dev）
        _is_bb = 'bestblogs.dev' in (s.get('url') or '')
        if k in c0_items:
            c0 = dict(s); c0["items"] = c0_items[k]
            if _is_bb: c0["bb"] = True
            chunk0.append(c0)
            rest = [it for it in s.get("items", []) if id(it) not in seen]
            if rest:
                c1 = dict(s); c1["items"] = rest
                if _is_bb: c1["bb"] = True
                chunk1.append(c1)
        elif s.get("items"):
            if _is_bb: s = dict(s); s["bb"] = True
            chunk1.append(s)
    return chunk0, chunk1

def write_data_chunks(sources, chunk0_size=CHUNK0_SIZE):
    """写出 rss-data-0.js + rss-data-{1..N}.js（与 OUT 同目录），页面经 script 标签加载。
    chunk1 按 ~80MB 上限自动拆分，避免超过 GitHub 100MB 单文件限制。"""
    out_dir = os.path.dirname(os.path.abspath(OUT)) or "."
    chunk0, chunk1 = _split_data_chunks(sources, chunk0_size)

    def _dump(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    # chunk0: 首屏
    with open(os.path.join(out_dir, "rss-data-0.js"), "w", encoding="utf-8") as f:
        f.write("/* StarHub data chunk 0 (first screen) - auto generated, do not edit */\n")
        f.write("(window.__CHUNKS=window.__CHUNKS||[])[0]=" + _dump({"sources": chunk0}) + ";\n")
    n0 = sum(len(s.get("items", [])) for s in chunk0)

    # chunk1+: 按 ~80MB 上限拆分，避免 GitHub 100MB 限制
    MAX_CHUNK_BYTES = 80 * 1024 * 1024
    n1_total = sum(len(s.get("items", [])) for s in chunk1)
    if not chunk1:
        # 无剩余数据，写空 chunk1
        with open(os.path.join(out_dir, "rss-data-1.js"), "w", encoding="utf-8") as f:
            f.write("/* StarHub data chunk 1 - auto generated, do not edit */\n")
            f.write("(window.__CHUNKS=window.__CHUNKS||[])[1]={sources:[]};\n")
        print("[数据分块] chunk0 %d 篇 / chunk1 0 篇（共 %d）" % (n0, n0))
        return

    # 估算每源 JSON 体积，按体积均匀分桶
    src_sizes = []
    for s in chunk1:
        try:
            sz = len(json.dumps(s, ensure_ascii=False).encode("utf-8"))
        except Exception:
            sz = 1024
        src_sizes.append(sz)
    total_bytes = sum(src_sizes)
    n_chunks = max(1, (total_bytes + MAX_CHUNK_BYTES - 1) // MAX_CHUNK_BYTES)
    target_per_chunk = total_bytes / n_chunks

    buckets = [[] for _ in range(n_chunks)]
    bucket_sizes = [0] * n_chunks
    for i, (s, sz) in enumerate(zip(chunk1, src_sizes)):
        # 放入当前最小的桶
        min_idx = bucket_sizes.index(min(bucket_sizes))
        buckets[min_idx].append(s)
        bucket_sizes[min_idx] += sz

    for idx, bucket in enumerate(buckets):
        chunk_idx = idx + 1
        fname = "rss-data-%d.js" % chunk_idx
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            f.write("/* StarHub data chunk %d (background merge) - auto generated, do not edit */\n" % chunk_idx)
            f.write("(window.__CHUNKS=window.__CHUNKS||[])[%d]=" % chunk_idx + _dump({"sources": bucket}) + ";\n")
        n_items = sum(len(s.get("items", [])) for s in bucket)
        size_mb = bucket_sizes[idx] / 1024 / 1024
        print("[数据分块] %s: %d 源 %d 篇 %.1f MB" % (fname, len(bucket), n_items, size_mb))

    # 清理旧的多余 chunk 文件（如果上次构建分了更多块）
    import glob
    for old_file in glob.glob(os.path.join(out_dir, "rss-data-*.js")):
        basename = os.path.basename(old_file)
        try:
            num = int(basename.replace("rss-data-", "").replace(".js", ""))
            if num > n_chunks:
                os.remove(old_file)
                print("[数据分块] 清理旧文件: %s" % basename)
        except ValueError:
            pass

    print("[数据分块] chunk0 %d 篇 / %d 个后台块 %d 篇（共 %d）" % (n0, n_chunks, n1_total, n0 + n1_total))


def build_html(sources_with_items, build_time, total_items, build_ts_ms=0, analysis_data=None,
               diverse_window_minutes=120, diverse_enabled=True):
    """生成完整 HTML 页面 — 卡片墙 + 抽屉阅读器。"""
    # 构建洞察面板 HTML（仅当分析数据存在时显示按钮）
    insight_btn = ''
    insight_bar = ''
    if analysis_data:
        insight_btn = (
            '<button class="insight-btn" id="btnInsight" onclick="toggleInsight()" title="每日洞察">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">'
            '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>'
            '</svg> 洞察</button>\n'
        )
        insight_bar = (
            '<aside class="insight-panel" id="insightPanel" role="dialog" aria-modal="true" aria-label="\u6bcf\u65e5\u6d1e\u5bdf">\n'
            '<div class="ip-head">\n'
            '<h2><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">'
            '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>'
            ' \u6bcf\u65e5\u6d1e\u5bdf</h2>\n'
            '<span class="ip-gen" id="ipGen"></span>\n'
            '<button class="ip-close" onclick="toggleInsight()" aria-label="\u5173\u95ed\u6d1e\u5bdf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>\n'
            '</div>\n'
            '<nav class="ip-nav" id="ipNav" aria-label="\u6d1e\u5bdf\u7ae0\u8282\u5bfc\u822a"></nav>\n'
            '<div class="ip-body" id="insightBody"></div>\n'
            '</aside>\n'
        )
    # 分析数据 JSON 注入到 JS
    analysis_json = ''
    if analysis_data:
        analysis_json = json.dumps(analysis_data, ensure_ascii=False, separators=(',', ':'))
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700;900&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
        '<title>RSS 聚合阅读器 · StarHub</title>\n'
        '<style>' + _build_css() + '</style>\n'
        + '<link rel="preload" href="rss-data-0.js?v=' + str(int(build_ts_ms)) + '" as="script">\n'
        + '<link rel="preload" href="hot_snapshot.json" as="fetch" crossorigin>\n'
        '</head>\n<body>\n'
        + _build_header() +
        '<div class="toolbar">\n'
        '<h1>时间线</h1>\n'
        '<button class="src-btn" onclick="toggleSrcPanel()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h13M4 18h9"/></svg> 信源 <span class="cnt" id="srcCnt"></span></button>\n'
        '<button class="refresh-btn" id="refreshBtn" onclick="refreshRss()" title="后台检查更新，不刷新页面"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></button>\n'
        '<div class="chips" id="chips"></div>\n'
        '<button class="unread-toggle" id="unreadToggle" onclick="toggleUnread()" title="\u4ec5\u663e\u793a\u672a\u8bfb"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg> \u672a\u8bfb</button>\n'
                '<button class="unread-toggle" id="markAllReadBtn" onclick="markAllRead()" title="\u5168\u90e8\u6807\u8bb0\u5df2\u8bfb" style="display:none"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> \u5168\u90e8\u5df2\u8bfb</button>\n'
        '<button class="ai-feed-btn" id="btnAiFeed" onclick="toggleAiFeed()" title="AI \u52a8\u6001\u6d41"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg> AI \u52a8\u6001</button>\n'
        '<button class="hot-btn" id="btnHot" onclick="toggleHotPanel()" title="\u5168\u7f51\u70ed\u699c"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2c1 3-2 5-2 8a4 4 0 0 0 8 0c0-3-2-5-2-8"/><path d="M8.5 14.5A5 5 0 0 0 12 22a5 5 0 0 0 3.5-7.5"/></svg> \u70ed\u699c</button>\n'
        '<span class="tb-divider" aria-hidden="true"></span>\n'
        + insight_btn +
        
        '<span id="fpillWrap"></span>\n'
        '<span class="tool-meta" id="toolMeta"></span>\n'
        '</div>\n'
        '<div class="search-row">\n'
        '<span class="global-search" id="globalSearchWrap"><input id="globalSearch" placeholder="\u641c\u7d22\u6587\u7ae0\u6807\u9898\u3001\u6458\u8981\u6216\u4fe1\u606f\u6e90\u540d\u79f0\u2026" autocomplete="off"><span class="sx" id="globalSearchClear">\u2715</span></span>\n'
                '<span class="src-match-label" id="srcMatchLabel" style="display:none" aria-live="polite"></span>\n'
        '<select class="sort-select" id="sortSelect" title="\u6392\u5e8f\u65b9\u5f0f"><option value="newest">\u6700\u65b0\u53d1\u5e03</option><option value="oldest">\u6700\u65e9\u53d1\u5e03</option><option value="active">\u6700\u8fd1\u6d3b\u8dc3</option><option value="quality">\u4fe1\u6e90\u8d28\u91cf</option>'
        + ('<option value="diverse">\u591a\u6837\u63a8\u8350</option>' if diverse_enabled else '')
        + '</select>\n'
        '</div>\n'
        + insight_bar +
        '<div class="build-bar">\u81ea\u52a8\u751f\u6210\u4e8e ' + _esc(build_time) + '\uff08\u5317\u4eac\u65f6\u95f4\uff09\u00b7 \u5171 ' + str(total_items) + ' \u7bc7 \u00b7 <span id="buildRel"></span><span id="liveStatus"></span></div>\n'
        '<div class="wall-wrap">\n'
        '<aside class="ai-feed-panel" id="aiFeedPanel">\n'
        '<div class="af-head">\n'
        '<div class="af-tabs" role="tablist">\n'
        '<button class="af-tab on" id="afTabFeed" role="tab" aria-selected="true" onclick="switchAfTab(\'feed\')">AI \u5feb\u8baf</button>\n'
        '<button class="af-tab" id="afTabHot" role="tab" aria-selected="false" onclick="switchAfTab(\'hot\')">\u70ed\u699c</button>\n'
        '</div>\n'
        '<button class="af-refresh" id="afRefreshBtn" onclick="refreshAiFeed()" title="\u5237\u65b0"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></button>\n'
        '<button class="af-close" onclick="toggleAiFeed()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>\n'
        '<div class="hp-wrap" id="hpWrap">\n'
        '<div class="dim-row"><span class="dim-label">分类</span><div class="dim-body"><div class="hp-seg" id="hpCats" role="tablist" aria-label="热榜分类筛选"></div></div></div>\n'
        '<hr class="dim-sep">\n'
        '<div class="dim-row" style="padding-top:0"><span class="dim-label">平台</span><div class="dim-body plat-wrap"><div class="plat-row collapsed" id="hpTabs"></div></div></div>\n'
        '<div class="hp-body" id="hotList"><div class="hp-empty">点击加载热榜</div></div></div>\n'
        '<div class="af-sub" id="afUpdated"></div>\n'
        '<div class="af-filter" id="afFilter" style="display:none"></div>\n'
        '<div class="af-body" id="afList"><div class="af-empty">\u70b9\u51fb\u67e5\u770b AI \u52a8\u6001</div></div>\n'
        '<button class="af-more" id="afLoadMore" style="display:none">\u52a0\u8f7d\u66f4\u591a</button></aside>\n'
        '<div class="wall" id="wall" role="feed" aria-label="\u6587\u7ae0\u5217\u8868"><div class="boot-loading" id="bootLoading"><span class="boot-spin"></span>\u6b63\u5728\u52a0\u8f7d\u5185\u5bb9\u2026</div></div>\n'
        '</div>\n'
        '<div class="scrim" aria-hidden="true" onclick="closeOverlays()"></div>\n'
        '<aside class="src-panel" id="srcPanel" role="dialog" aria-modal="true" aria-label="\u4fe1\u6e90\u9762\u677f">\n'
        '<div class="sp-head"><div class="row"><h2>信源</h2>\n'
        '<button class="sp-export" onclick="exportOPML()" title="\u5bfc\u51fa OPML"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></button>\n'
        '<button class="sp-close" onclick="toggleSrcPanel()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>\n'
        '</div><label class="sp-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>\n'
        '<input id="spSearch" placeholder="搜索信源…" autocomplete="off"></label></div>\n'
        '<div class="sp-list" id="spList"></div></aside>\n'
        '<aside class="reader2" id="reader2" role="dialog" aria-modal="true" aria-label="\u6587\u7ae0\u9605\u8bfb\u5668">\n'
        '<div class="r2-top"><button class="r2-close" onclick="closeReader()" title="关闭阅读器" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>\n'
        '<span class="r2-src" id="r2Src"></span>\n'
        '<div class="r2-acts"><div class="r2-fs-btns"><button class="r2-fs-btn" onclick="setFontSize(\'sm\')" title="\u5c0f\u5b57\u53f7">A-</button><button class="r2-fs-btn" onclick="setFontSize(\'md\')" title="\u9ed8\u8ba4\u5b57\u53f7">A</button><button class="r2-fs-btn" onclick="setFontSize(\'lg\')" title="\u5927\u5b57\u53f7">A+</button></div><button class="r2-bm" id="r2Bm" onclick="if(curArt)toggleBookmark(curArt)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><span>\u6536\u85cf</span></button><a class="r2-open" id="r2Open" href="#" target="_blank" rel="noopener">\u539f\u7ad9 \u2197</a></div>\n'
        '<div class="r2-progress" id="r2Progress"></div></div>\n'
        '<div class="r2-body" id="r2Body"><div class="r2-inner" id="r2Inner"></div></div></aside>\n'
        '<div class="toast" id="toast" role="status" aria-live="polite"></div>\n'
        '<button class="back-top" id="backTop" onclick="window.scrollTo({top:0,behavior:\'smooth\'})" aria-label="\u8fd4\u56de\u9876\u90e8"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg></button>\n'
        '<div class="share-modal" id="shareModal" role="dialog" aria-modal="true" aria-label="分享文章">\n'
        '<div class="share-backdrop" onclick="closeShareModal()"></div>\n'
        '<div class="share-panel">\n'
        '<div class="share-hd"><h3>分享图片已生成</h3><button class="share-close" onclick="closeShareModal()" aria-label="关闭">×</button></div>\n'
        '<div class="share-img-wrap"><img id="shareImg" alt="分享图片"/></div>\n'
        '<div class="share-textcard" id="shareTextCard"></div>\n'
        '<p class="share-hint">长按图片保存，发送至微信好友或朋友圈</p>\n'
        '<div class="share-actions">\n'
        '<button class="btn-share-save" id="btnShareSave" onclick="saveShareImage()">保存图片</button>\n'
        '<button class="btn-share-copy" id="btnShareCopy" onclick="copyShareImage()">复制图片</button>\n'
        '<button class="btn-share-copy" id="btnShareCopyText" onclick="copyShareText()" style="display:none;">复制文字</button>\n'
        '<button class="btn-share-html" id="btnShareHtml" onclick="copyFullHtml()" style="margin-left:6px;padding:8px 22px;border-radius:8px;font-size:13px;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;transition:all .15s;font-family:var(--body);">复制全文HTML</button>\n'
        '</div>\n'
        '</div>\n'
        '</div>\n'
        + '<script src="rss-data-0.js?v=' + str(int(build_ts_ms)) + '"></' + 'script>\n'
+ _build_js(sources_with_items, build_ts_ms, analysis_json=analysis_json) +
        '</body>\n</html>'
    )


# ──────────────────────────── 智能分析模块 ────────────────────────────

# 科技/AI/热点领域术语词典（硬编码，按长度降序排列用于贪心最长匹配）
_TECH_DICT = sorted({
    # AI / 大模型
    '大模型', '人工智能', '机器学习', '深度学习', '自然语言处理', '神经网络',
    '多模态', '扩散模型', '生成式', 'Transformer', '注意力机制', '预训练',
    '微调', '提示词', 'Agent', '智能体', 'RAG', '检索增强', '向量数据库',
    '大语言模型', '通用人工智能', 'AGI', 'LLM', 'GPT',
    # 芯片 / 硬件
    '半导体', '芯片', '制程', '光刻机', '先进封装', 'HBM', '存储芯片',
    'GPU', 'CPU', 'NPU', '算力', '数据中心', '服务器',
    # 互联网 / 科技
    '自动驾驶', '机器人', '元宇宙', '数字孪生', '边缘计算', '云计算',
    '区块链', 'Web3', '去中心化', '开源', '操作系统', '浏览器',
    '智能手机', '折叠屏', '卫星通信', '低轨卫星', '6G', '5G',
    # 热点 / 社会
    '泥石流', '地震', '台风', '洪水', '应急响应', '救援',
    '高考', '考研', '就业', '裁员', 'IPO', '上市', '融资',
    '监管', '合规', '反垄断', '数据安全', '隐私保护',
    # 国际 / 政治
    '首相', '总统', '大选', '制裁', '关税', '贸易', '地缘政治',
    # 金融 / 经济
    '股市', 'A股', '港股', '美股', '比特币', '加密货币', '央行',
    '降息', '加息', '通胀', 'GDP', 'CPI',
    # 通用高频词（避免被切散）
    '审核', '一审', '二审', '判决', '法院', '检察院', '立案',
    '报道', '据悉', '表示', '指出', '认为', '透露', '宣布',
    '发布', '推出', '上线', '下线', '升级', '更新', '修复',
    '漏洞', '安全', '攻击', '黑客', '恶意软件', '病毒',
    '用户', '开发者', '程序员', '工程师', '科学家', '研究员',
    '公司', '企业', '机构', '政府', '部门', '组织',
    '中国', '美国', '日本', '欧洲', '全球', '国内', '海外',
    '科技', '技术', '创新', '突破', '进展', '成果',
    '产品', '服务', '平台', '应用', '软件', '硬件', '系统',
    '数据', '算法', '模型', '训练', '推理', '部署',
    '网络', '互联网', '移动', '无线', '通信', '信号',
    '能源', '电池', '电动车', '新能源', '光伏', '风电',
    '医疗', '健康', '生物', '基因', '疫苗', '药物',
    '教育', '学校', '大学', '研究', '学术', '论文',
    '文化', '娱乐', '电影', '音乐', '游戏', '电竞',
    '体育', '奥运', '足球', '篮球', '赛事',
    '环境', '气候', '碳排放', '绿色', '可持续',
    '军事', '国防', '武器', '导弹', '演习',
    '外交', '谈判', '协议', '条约', '峰会',
}, key=len, reverse=True)

# 已知无意义双字组合（滑动窗口回退时过滤）
_NOISE_BIGRAMS = {'军一', '核被', '审一', '已故', '人称', '据报',
                  '的的', '了了', '是是', '在在', '有有', '和和',
                  # 日期/时间碎片
                  '月日', '年月', '日年', '时分', '秒分',
                  # 无意义组合
                  '地址', '网址', '链接', '点击', '查看', '阅读', '原文'}


def _is_valid_ngram(word):
    """判断 n-gram 是否有意义（质量过滤）。"""
    if not word or len(word) < 2:
        return False
    # 排除连续相同字符（被被、一一、审审）
    if len(set(word)) == 1:
        return False
    # 排除停用词
    if word in _STOP_WORDS:
        return False
    # 排除已知无意义组合
    if word in _NOISE_BIGRAMS:
        return False
    # 含空格 → 拒绝（如 "月 日"、"址  "）
    if ' ' in word or '\u3000' in word:
        return False
    # 含特殊符号 → 拒绝（如 "文 ·"、"评论:"）
    if re.search(r'[·:：.,，;；!?！？()（）\[\]【】{}<>]', word):
        return False
    # 纯数字 → 拒绝
    if word.isdigit():
        return False
    return True


def _has_repeated_chars(text, min_repeats=2, min_run=2):
    """检测文本中是否有过多连续重复字符（OCR 错误 / 病句信号）。
    例如 '被被' '审审' '一一' 等。"""
    count = 0
    for i in range(len(text) - 1):
        if text[i] == text[i + 1] and '\u4e00' <= text[i] <= '\u9fff':
            count += 1
    return count >= min_repeats


def _tokenize(text):
    """分词：术语词典优先 + 贪心最长匹配 + 英文单词。返回小写 token 列表。"""
    if not text:
        return []
    text = text.lower()
    tokens = []

    # 1. 英文单词（保持原逻辑）
    en_words = re.findall(r'[a-z][a-z0-9_-]{1,}', text)
    tokens.extend(w for w in en_words if w not in _STOP_WORDS and len(w) > 1)

    # 2. 中文：术语词典优先匹配，剩余用改进的 n-gram
    cn_text = re.sub(r'[a-z0-9_\-\s]+', ' ', text)  # 去掉英文片段
    cn_text = re.sub(r'[\u3000-\u303f\uff00-\uffef]', ' ', cn_text)  # 去掉全角标点

    i = 0
    chars = list(cn_text)
    while i < len(chars):
        ch = chars[i]
        # 跳过非中文字符
        if not ('\u4e00' <= ch <= '\u9fff'):
            i += 1
            continue
        # 贪心最长匹配：从最长术语开始尝试
        matched = False
        for term in _TECH_DICT:
            if i + len(term) <= len(chars):
                candidate = ''.join(chars[i:i + len(term)])
                if candidate == term:
                    tokens.append(term)
                    i += len(term)
                    matched = True
                    break
        if not matched:
            # 未命中词典：尝试 2-3 字 n-gram（仅保留有意义的）
            found_ngram = False
            for span in [3, 2]:
                if i + span <= len(chars):
                    ngram = ''.join(chars[i:i + span])
                    if _is_valid_ngram(ngram):
                        tokens.append(ngram)
                        i += span
                        found_ngram = True
                        break
            if not found_ngram:
                i += 1  # 跳过单字
    return tokens


@functools.lru_cache(maxsize=65536)
def _tokenize_cached(text):
    """tokenize 结果缓存：D4 语料放大后同一文本多份复现，避免重复分词（rev8 P1-3）。"""
    return tuple(_tokenize(text))


def _tfidf_keywords(texts, top_n=50, per_doc_top=10):
    """从文本列表中提取全局 TF-IDF 关键词。返回 [(keyword, score), ...]。"""
    if not texts:
        return []
    # 每篇文章的 token 集合（缓存：重复语料只分词一次）
    doc_tokens = [list(_tokenize_cached(t)) for t in texts]
    n_docs = len(doc_tokens)
    # DF: 每个 token 出现在多少篇文档中
    df = collections.Counter()
    for tokens in doc_tokens:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    # TF: 全局词频
    tf = collections.Counter()
    for tokens in doc_tokens:
        tf.update(tokens)
    # TF-IDF 评分
    scores = {}
    for word, freq in tf.items():
        if len(word) < 2 or df[word] < 2:
            continue  # 过滤太短或只出现一次的词
        idf = math.log(1 + n_docs / (1 + df[word]))
        scores[word] = freq * idf
    # 过滤无意义关键词
    scores = {w: s for w, s in scores.items() if _is_valid_ngram(w)}
    return sorted(scores.items(), key=lambda x: -x[1])[:top_n]


def _extract_keywords(rss_history, now_bj, unreliable_srcs=None):
    """从 72h 历史中提取关键词。返回 {global: [...], by_cat: {cat: [...]}}。

    D4：bad_date 不可信源（unreliable_srcs）的条目按 0.3 权重精确降权——
    以 10 倍放大实现整数化配比（正常基线 10 份、不可信 3 份），
    tfidf 频次与文本份数线性映射，权重比逐字面成立。
    """
    _W_BASE, _W_RECENT, _UNRELIABLE_FACTOR = 10, 2, 3
    unreliable = unreliable_srcs or set()
    cutoff_24h = now_bj.replace(tzinfo=None) - datetime.timedelta(hours=24)
    # 近 24h 文章用于热点提取
    recent_texts = []
    recent_count = 0
    cat_texts = collections.defaultdict(list)
    for item in rss_history.values():
        pd_str = item.get('pub_date', '')
        if pd_str:
            try:
                pd = datetime.datetime.fromisoformat(pd_str)
                if pd.tzinfo:
                    pd = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
            except ValueError:
                pd = now_bj.replace(tzinfo=None)
        else:
            pd = now_bj.replace(tzinfo=None)
        title = item.get('title_zh', '') or item.get('title', '')
        summary = item.get('summary_zh', '') or item.get('summary', '')
        text = (title + ' ' + summary).strip()
        if not text:
            continue
        is_recent = pd >= cutoff_24h
        if is_recent:
            recent_count += 1  # 真实近24h条数（与语料复制解耦，rev8 P1-1）
        # D4 权重以语料份额计（精确 0.3）：正常 recent = W_BASE*W_RECENT 份 + W_BASE 份；
        # 不可信 = 正常 × UNRELIABLE_FACTOR/10（0.3 倍）
        if item.get('source_key', '') in unreliable:
            if is_recent:
                recent_texts.extend([text] * (_W_BASE * _W_RECENT * _UNRELIABLE_FACTOR // 10))
            cat_texts[item.get('cat', 'other')].extend([text] * (_W_BASE * _UNRELIABLE_FACTOR // 10))
        else:
            if is_recent:
                recent_texts.extend([text] * (_W_BASE * _W_RECENT))
            cat_texts[item.get('cat', 'other')].extend([text] * _W_BASE)
    # 全局关键词（近 24h 优先，但用全部 72h 数据）
    all_texts = recent_texts * 2 + [t for cat_ts in cat_texts.values() for t in cat_ts]  # 近 24h 权重 x2
    global_kw = _tfidf_keywords(all_texts, top_n=50)
    # 按分类关键词
    by_cat = {}
    for cat, texts in cat_texts.items():
        if len(texts) >= 3:
            by_cat[cat] = _tfidf_keywords(texts, top_n=20)
    return {"global": global_kw, "by_cat": by_cat, "recent_count": recent_count}


def _score_sources(sources_with_items, rss_history):
    """信源质量评分。返回 {source_key: {score, metrics}}。"""
    result = {}
    # 按源统计历史数据
    src_stats = collections.defaultdict(lambda: {
        'total': 0, 'has_summary': 0, 'has_fullcontent': 0,
        'bad_date_count': 0, 'total_with_date': 0,
    })
    for item in rss_history.values():
        sk = item.get('source_key', '')
        if not sk:
            continue
        s = src_stats[sk]
        s['total'] += 1
        summary = item.get('summary', '') or item.get('summary_zh', '')
        if len(summary) > 60:
            s['has_summary'] += 1
        fc = item.get('full_content', '')
        if fc and len(fc) > 100:
            s['has_fullcontent'] += 1
        if item.get('pub_date'):
            s['total_with_date'] += 1
        if item.get('bad_date'):
            s['bad_date_count'] += 1
    for src in sources_with_items:
        sk = src['key']
        s = src_stats.get(sk, {'total': 0, 'has_summary': 0, 'has_fullcontent': 0, 'bad_date_count': 0, 'total_with_date': 0})
        n = s['total']
        if n == 0:
            # 72h 历史无数据：用 tier 推断默认分（新增源/低频源/被跳过源）
            _tier = src.get('tier', 3)
            _default = {1: 60, 2: 40}.get(_tier, 25)
            result[sk] = {
                'score': _default,
                'metrics': {},
                'article_count': 0,
                'inferred': True,
            }
            continue
        freshness = min(1.0, n / 10.0)              # 72h 内文章数 / 10 篇满分
        coverage = s['has_summary'] / n if n > 0 else 0
        date_trust = 1.0 - (s['bad_date_count'] / s['total_with_date'] if s['total_with_date'] > 0 else 0)
        fulltext = s['has_fullcontent'] / n if n > 0 else 0
        # 抓取成功率从 sources_with_items 的 items 是否为空推断
        reliability = 1.0 if n > 0 else 0.0
        score = (freshness * 0.25 + coverage * 0.20 + date_trust * 0.20 +
                 fulltext * 0.15 + reliability * 0.20) * 100
        result[sk] = {
            'score': round(score, 1),
            'metrics': {
                'freshness': round(freshness * 100, 1),
                'coverage': round(coverage * 100, 1),
                'date_trust': round(date_trust * 100, 1),
                'fulltext': round(fulltext * 100, 1),
                'reliability': round(reliability * 100, 1),
            },
            'article_count': n,
        }
    return result


# ──────────────────── 话题标签提取（issue C2） ────────────────────
# 旧实现直接取 _tokenize 的词频 Top3。但 _tokenize 是「从位置 0 起逐位贪心吞 3 字」
# 的扫描器，词典术语会被前一位置的误吞切断，且切点落在词中间：
#     '苹果发布会'   → ['苹果发', '布会']
#     '关于人工智能' → ['关于人', '工智能']      （'工智能' 是 '人工智能' 的真子串）
#     '出席金砖国家' → ['出席金', '砖国家']
# 真实语料实测（27076 个标签）：16.7% 的标签首/尾是虚词功能字
# （'的星尘' / '或让' / '将瞄准' / '定 价' / '大  '），4.2% 含空白，
# 台标与栏目名（rfi / cnn / hn / 问与答）进入 Top 15 —— 与「出版社样板污染」同源。
#
# 新口径（顺序即优先级）：
#   P1 词典术语整词命中（绝不切碎）
#   P2 英文词：原文含大写（品牌/缩写）或命中词典，且非台标/样板
#   P3 长度 4..上界的边界对齐中文整段（'苹果发布会' 这类短段整取，不切）
#   P4 其余中文段（2~3 字、或超过上界）用过滤后的词频兜底
#   P5 按源样板抑制：某 token 出现在该源 ≥60% 篇目中 → 台标/栏目名，整源剔除
_TAG_MAX_LEN = 6                 # 中文标签长度上界；超过这个长度的整段是句子片段，不是标签
_TAG_BOILER_MIN_ITEMS = 10       # 源内至少这么多篇才做样板词统计（样本太少无统计意义）
_TAG_BOILER_RATIO = 0.6          # 出现在该源 ≥60% 篇目 → 判为台标/栏目名

# 首/尾出现这些字即为「切在词中间」的切片（'的星尘' / '或让' / '将瞄准'）
_TAG_EDGE_NOISE = set(
    "的了是在我有和就不都一个上也这到说们为你对被把让给用从向"
    "该此其本如与及或并等将已正未很更最又还只仅才再也都吗呢吧啊着过据称当以对"
)
# 样板/泛化词：命中词典也不作标签（否则 '发布'/'公司'/'技术' 会占领标签表）
_TAG_BLOCKLIST = set("""
报道 据悉 表示 指出 认为 透露 宣布 发布 推出 上线 下线 升级 更新 修复
完成 使用 进行 实现 相关 有关 目前 近日 今日 昨日 未来 正在 已经 可以 需要
公司 企业 机构 政府 部门 组织 用户 产品 服务 平台 应用 软件 硬件
系统 数据 技术 创新 突破 进展 成果 市场 行业 领域 情况 问题 方面 内容 方式
为什么 有没有 一个 做了 第一个 第二十 十周年 评论 询问 突发 分享 观点 消息
记者 编辑 来源 版权 转载 声明 观察 分析 解读 盘点 汇总 速览 早报 晚报
网址 链接 原文 全文 本文 本站 译者 校对 责编 发自 综合报道 文章来源
文章网址 评论网址 阅读全文 查看更多 推荐阅读 相关阅读 点击查看 详情
""".split())
# 英文样板词：多为栏目名/停用词，且不在 _TECH_DICT 内
_TAG_EN_BLOCKLIST = set("""
hn pro fix show duo flash ask news de le der web france fr en es
the and for with from that this new top best how why what when who
you your his her its our their all any can may not but
""".split())
_TAG_DICT_LOWER = set(t.lower() for t in _TECH_DICT)
_TAG_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_TAG_EN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9._+\-]{1,19}")
_TAG_WS = re.compile(r"\s")


def _tag_src_name_norm(name):
    """源名归一化：只留字母/数字/汉字（用于台标自指判断）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (name or "").lower())


def _is_tag_station(tok, src_norm):
    """台标判定：标签是源名的一部分，或源名是标签的一部分（'cnn' ⊂ 'CNN'）。"""
    if not src_norm or len(tok) < 2:
        return False
    tl = tok.lower()
    return tl in src_norm or (len(src_norm) >= 3 and src_norm in tl)


def _tag_edge_ok(tok):
    """标签首/尾不得是虚词功能字（'的星尘' / '或让' 这类切片的判据）。"""
    return len(tok) >= 2 and tok[0] not in _TAG_EDGE_NOISE and tok[-1] not in _TAG_EDGE_NOISE


def _tag_ok(tok, src_norm, low_text):
    """标签通用过滤：长度/空白/样板/边界/数值单位/台标/词典术语真子串。"""
    if len(tok) < 2 or _TAG_WS.search(tok):
        return False
    if tok in _TAG_BLOCKLIST or tok in _TAG_EN_BLOCKLIST:
        return False
    if not _tag_edge_ok(tok) or _is_numeric_unit_phrase(tok):
        return False
    if _is_tag_station(tok, src_norm):
        return False
    if not tok.isascii() and len(tok) > _TAG_MAX_LEN:
        return False
    # 词典术语的真子串：'工智能' ⊂ '人工智能'（同一文本里 '人工智能' 也在）
    if any(tok != d and tok in d and d in low_text for d in _TAG_DICT_LOWER):
        return False
    return True


def _tag_candidates(text, src_norm, allow_runs=True):
    """按优先级产出候选标签（可能超过 3 个，由调用方截断）。

    allow_runs=False 时只走 P1/P2（词典术语 + 英文词），不切中文段：
    摘要是一整段散文，长中文段里没有可用词典术语时只能靠 n-gram 硬切，
    实测切出来的是 '自微信' / '际广播' / '文章网址' 这类东西。
    标题本身短且是名词短语，才值得做边界对齐的整段取词。
    """
    text = text or ""
    if not text.strip():
        return []
    low = text.lower()
    picks = []

    # P1 词典术语：整词命中。按出现位置排，同位置取更长者（避免短词吃掉长词的位）
    hits = []
    for term in _TECH_DICT:
        k = low.find(term.lower())
        if k >= 0:
            hits.append((term.lower(), k, len(term)))
    hits.sort(key=lambda x: (x[1], -x[2]))
    for w, _k, _L in hits:
        if _tag_ok(w, src_norm, low):
            picks.append(w)

    # P2 英文词：原文含大写（品牌/缩写如 OpenAI/iPhone），或命中词典（ai/llm/gpt）
    for m in _TAG_EN_WORD.finditer(text):
        raw = m.group(0)
        w = raw.lower()
        if w in _TAG_EN_BLOCKLIST or w in _TAG_BLOCKLIST:
            continue
        if w not in _TAG_DICT_LOWER and not any(c.isupper() for c in raw):
            continue
        if _is_tag_station(w, src_norm):
            continue
        picks.append(w)

    # P3/P4 中文段：短段（4..上界）整取，其余用过滤后的词频兜底
    if allow_runs:
        for run in _TAG_CJK_RUN.findall(text):
            L = len(run)
            if L < 2:
                continue
            # 「本段有可用词典术语」时不再切段 —— 切碎只会产生碎片（'出席金'/'砖国家'）。
            # 两种情形交给 P1 整词发出：
            #   a) 段太长（>上界）：整段不可用，只能靠词典术语，切碎只会更差；
            #   b) 段内某个可用术语几乎占满整段（len ≥ L-1）：该段基本就是这个术语 + 杂字。
            # 反例（必须走整段）：'苹果发布会' 段内的 '发布' 是样板词、不可用，
            # 此时整段本身就是最好的短语，切碎才会得到 '苹果发'/'布会'。
            eff = [d for d in _TAG_DICT_LOWER if d in run and _tag_ok(d, src_norm, low)]
            has_any = any(d in run for d in _TAG_DICT_LOWER)
            if has_any and (L > _TAG_MAX_LEN or (eff and max(len(d) for d in eff) >= L - 1)):
                continue
            if 4 <= L <= _TAG_MAX_LEN and _tag_ok(run, src_norm, low):
                picks.append(run)
                continue
            toks = []
            for t in _tokenize_cached(run):
                t = t.strip()
                if _tag_ok(t, src_norm, low):
                    toks.append(t)
            for w, _ in collections.Counter(toks).most_common(3):
                picks.append(w)

    seen, out = set(), []
    for w in picks:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _tag_articles(sources_with_items):
    """为每篇文章提取 1-3 个话题标签。

    标签来源：标题（title_zh/title/t，构建期与刷新通道两种契约）优先，
    不足 3 个时用摘要前 200 字（summary_zh/summary/s）补齐。
    口径见上方常量区注释（C2 修复）。
    原地修改 item，新增 tags 字段。
    """
    for src in sources_with_items:
        items = src.get("items", [])
        if not items:
            continue
        sn = _tag_src_name_norm(src.get("name"))
        # 第一遍：逐条产出候选
        raw = []
        for it in items:
            title = it.get("title_zh") or it.get("title") or it.get("t") or ""
            summary = (it.get("summary_zh") or it.get("summary") or it.get("s") or "")[:200]
            if not (title or summary).strip():
                raw.append([])
                continue
            tags = []
            # 标题：完整管线（含边界对齐整段取词）；
            # 摘要：只取词典术语与英文词（散文长段硬切只会得到 '自微信'/'际网址' 这类碎片）
            for pool, allow_runs in ((title, True), (summary, False)):
                if len(tags) >= 3:
                    break
                for w in _tag_candidates(pool, sn, allow_runs=allow_runs):
                    if len(tags) >= 3:
                        break
                    if w not in tags:
                        tags.append(w)
            raw.append(tags)
        # 第二遍：按源统计样板词（台标/栏目名），整源剔除
        # 判据是「在这个源里几乎每篇都出现」——话题词不会这么均匀，栏目名会。
        boiler = set()
        if len(items) >= _TAG_BOILER_MIN_ITEMS:
            df = collections.Counter()
            for tags in raw:
                for t in set(tags):
                    df[t] += 1
            need = max(3, _TAG_BOILER_RATIO * len(items))
            boiler = set(t for t, c in df.items() if c >= need)
        for it, tags in zip(items, raw):
            it["tags"] = [t for t in tags if t not in boiler]


def _is_numeric_unit_phrase(s):
    """判断字符串是否为纯数值单位短语（如 '亿欧元'、'万美元'、'千亿元'）。
    这类短语不适合作为话题标签。
    """
    # 匹配模式：可选数字 + 单位词（亿/万/千/百）+ 货币/量词
    if re.match(r'^[\d零一二三四五六七八九十百千万]*[亿万万千百]?[元美元欧元英镑日元份项笔台架艘辆匹头只条块片张本座栋层等级场次局盘局]+$', s):
        return True
    # 纯数字 + 单位
    if re.match(r'^[\d零一二三四五六七八九十百千万]+[个只条台架艘辆匹头元美元欧元英镑日元份项笔]+$', s):
        return True
    return False


def _is_ascii_alpha(ch):
    """判断字符是否为 ASCII 字母（a-z, A-Z）。"""
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z'


def _find_cn_boundary(text, pos):
    """从 pos 位置开始，找到下一个中文语义边界的位置。

    边界定义：标点符号、空格、数字、ASCII 字母、或字符串末尾。
    用于确保截取的标签片段在语义上完整，不会在词组中间断开。
    返回边界位置的索引（即边界字符的位置），若 pos 已在边界则返回 pos。
    """
    if pos >= len(text):
        return pos
    ch = text[pos]
    # 当前字符本身就是边界
    if ch in '，。：！？、；""''（）()【】[]《》<>,. \t\n\r':
        return pos
    if ch.isdigit() or _is_ascii_alpha(ch):
        return pos
    # 从 pos 开始向后找第一个边界
    for i in range(pos, len(text)):
        c = text[i]
        if c in '，。：！？、；""''（）()【】[]《》<>,. \t\n\r':
            return i
        if c.isdigit() or _is_ascii_alpha(c):
            return i
    return len(text)


def _extract_meaningful_phrase(title, max_len=14):
    """从单个标题中提取一个语义完整的短语（不超过 max_len 字符）。

    优先在标点/空格/数字/拉丁字母处截断，确保不会出现半截词组。
    """
    if not title or len(title) <= max_len:
        return title
    # 在 max_len 附近找最近的语义边界
    # 先检查 max_len 位置是否已经是边界
    boundary = _find_cn_boundary(title, max_len)
    if boundary == max_len:
        return title[:max_len]
    # 如果边界在 max_len 之后不远（<= 3 字符），延伸到边界
    if boundary > max_len and boundary - max_len <= 3:
        return title[:boundary]
    # 否则在 max_len 之前找最近的边界（往回找最多 5 字符）
    for i in range(max_len - 1, max(0, max_len - 6), -1):
        c = title[i]
        if c in '，。：！？、；""''（）()【】[]《》<>,. \t\n\r':
            return title[:i]
        if c.isdigit() or _is_ascii_alpha(c):
            return title[:i]
    # 找不到好边界，就截取到 max_len
    return title[:max_len]


def _clean_topic_label(label, max_len=20):
    """清洗话题标签：截断过长标签、移除未完成引号、去除尾部标点。"""
    if not label:
        return ''
    # 限制最大长度
    if len(label) > max_len:
        label = label[:max_len].rstrip()
    # 移除未完成的引号（截断导致的）
    label = re.sub(r'["\'"\'「『【\(（]$', '', label)
    # 移除尾部标点
    label = re.sub(r'[，。：；！？,\.:;!?\s]+$', '', label)
    # 如果标签太短或为空，返回空
    if len(label) < 2:
        return ''
    return label


def _extract_topic_label_from_titles(cluster_articles):
    """从簇内文章标题中提取语义通顺的话题标签。

    优先级：
    1. 术语词典精确命中（标题中出现最多的 _TECH_DICT 词条）
    2. 最长公共子串 + 边界延伸（跨标题重复的连续中文片段，合并相邻 token 保留邻接关系）
    3. 标题内相邻 2-3 个高质量 token 拼接（分词错误检测 + 边界感知过滤）
    4. 兜底：从代表性标题中智能截取语义完整片段
    返回 (label_str, labels_list)。
    """
    _LABEL_NOISE_LOCAL = set('的了是在我有和就不都一个上也这到说们为你对被把让给用从向')

    # 收集合格标题（去重、去病句）
    good_titles = []
    seen_titles = set()
    for art in cluster_articles:
        t = art.get('title', '')
        if not t or len(t) < 4 or _has_repeated_chars(t, min_repeats=2, min_run=2):
            continue
        t_key = t[:30]  # 前 30 字去重
        if t_key in seen_titles:
            continue
        seen_titles.add(t_key)
        good_titles.append(t)

    if not good_titles:
        return '', []

    # ── 策略 1+2 联合决策：先算公共子串（带边界延伸），再与词典术语比较覆盖度 ──

    # 策略 2：最长公共子串 + 边界延伸
    best_substr = None
    best_substr_cnt = 0
    if len(good_titles) >= 2:
        # 预计算去空格标题：用于子串匹配和延伸，确保标签不含空格
        titles_stripped = [t.replace(' ', '').replace('\u3000', '') for t in good_titles]
        cn_fragments = []
        for ts in titles_stripped:
            # 逐 token 提取中文部分，再合并相邻 token 的中文片段
            # 这样 '多模态 发布全新' → 去空格 '多模态发布全新' → 单一片段
            # 保留跨空格的邻接关系，避免 '多模态' 和 '发布' 被拆成独立片段
            cn_only = re.sub(r'[^\u4e00-\u9fff]', '', ts)
            if len(cn_only) >= 3:
                cn_fragments.append(cn_only)
        substr_score = collections.Counter()
        for frag in cn_fragments:
            max_len = min(len(frag), 12)
            for slen in range(2, max_len + 1):
                for start in range(len(frag) - slen + 1):
                    sub = frag[start:start + slen]
                    if sub[0] in _LABEL_NOISE_LOCAL or sub[-1] in _LABEL_NOISE_LOCAL:
                        continue
                    cnt = sum(1 for ts in titles_stripped if sub in ts)
                    if cnt >= 2:
                        # 评分改为覆盖度优先：cnt × len，避免短子串因位置多而得分虚高
                        substr_score[sub] = cnt * slen
        if substr_score:
            # 覆盖度优先 + 同覆盖度选最长：先找最高覆盖度，再在同等覆盖度中选最长子串
            max_cnt = 0
            for sub in substr_score:
                cnt = sum(1 for ts in titles_stripped if sub in ts)
                if cnt > max_cnt:
                    max_cnt = cnt
            # 在最高覆盖度的子串中选最长的
            best_candidates = [(sub, len(sub)) for sub, score in substr_score.items()
                               if sum(1 for ts in titles_stripped if sub in ts) == max_cnt]
            best_candidates.sort(key=lambda x: x[1], reverse=True)
            # 对每个候选尝试边界延伸，然后选最优
            for candidate, cand_len in best_candidates[:20]:  # 最多处理前20个最长候选
                cand_cnt = max_cnt
                # 尝试延伸子串到语义边界
                extended = candidate
                extended_cnt = cand_cnt
                # 在去空格标题中找到 candidate，尝试向后延伸到边界
                for ts in titles_stripped:
                    idx = ts.find(candidate)
                    if idx < 0:
                        continue
                    end_pos = idx + len(candidate)
                    if end_pos >= len(ts):
                        continue  # 已在标题末尾
                    next_ch = ts[end_pos]
                    # 如果下一个字符是数字/拉丁字母，延伸到边界
                    if next_ch.isdigit() or _is_ascii_alpha(next_ch):
                        boundary_pos = _find_cn_boundary(ts, end_pos)
                        if boundary_pos > end_pos and boundary_pos - end_pos <= 4:
                            ext = ts[idx:boundary_pos]
                            ext_cnt = sum(1 for tt in titles_stripped if ext in tt)
                            if ext_cnt >= max(2, cand_cnt - 1) and len(ext) > len(extended):
                                extended = ext
                                extended_cnt = ext_cnt
                        break  # 只用第一个匹配标题来延伸
                    # 下一个是中文字符：尝试延伸 1-10 个字符
                    if '\u4e00' <= next_ch <= '\u9fff':
                        for ext_len in range(1, 11):
                            if end_pos + ext_len > len(ts):
                                break
                            ext = ts[idx:end_pos + ext_len]
                            ext_cnt = sum(1 for tt in titles_stripped if ext in tt)
                            # 延伸后覆盖度不能下降太多（允许降 1）
                            if ext_cnt >= max(2, cand_cnt - 1):
                                extended = ext
                                extended_cnt = ext_cnt
                                # 检查延伸后的末尾是否是边界
                                if end_pos + ext_len >= len(ts):
                                    break
                                next_ch2 = ts[end_pos + ext_len]
                                if next_ch2.isdigit() or _is_ascii_alpha(next_ch2):
                                    break
                                if not ('\u4e00' <= next_ch2 <= '\u9fff'):
                                    break
                            else:
                                break
                    else:
                        # 下一个是标点等，自然边界
                        pass
    
                # 用延伸后的结果与当前最优比较
                if extended_cnt > best_substr_cnt or (
                    extended_cnt == best_substr_cnt and len(extended) > len(best_substr or '')
                ):
                    best_substr = extended
                    best_substr_cnt = extended_cnt

    # 策略 2 纯中文结果优先：如果公共子串是纯中文且 >= 2 字，直接返回（避免策略 1 产生混合语言标签）
    if best_substr and len(best_substr) >= 2:
        cn_chars_in_substr = re.sub(r'[^\u4e00-\u9fff]', '', best_substr)
        if len(cn_chars_in_substr) == len(best_substr):
            # 纯中文子串，仅检查数值单位过滤
            if len(cn_chars_in_substr) <= 2 and _is_numeric_unit_phrase(best_substr):
                pass  # 纯数值单位（如 '美元'），跳过，进入策略 1
            else:
                return best_substr, [best_substr]

    # 策略 1：术语词典精确匹配
    dict_term_counter = collections.Counter()
    for title in good_titles:
        title_lower = title.lower()
        seen_in_doc = set()
        for term in _TECH_DICT:
            tl = term.lower()
            if tl in title_lower and len(term) >= 2 and tl not in seen_in_doc:
                dict_term_counter[term] += 1
                seen_in_doc.add(tl)
    if dict_term_counter:
        top_term, top_cnt = dict_term_counter.most_common(1)[0]
        # 仅当词典术语的标题覆盖度严格优于公共子串，或覆盖度相同但术语更长时才优先返回
        if top_cnt > best_substr_cnt or (top_cnt == best_substr_cnt and len(top_term) >= len(best_substr or '')):
            second = None
            for term, _ in dict_term_counter.most_common(5):
                if term != top_term:
                    second = term
                    break
            if second and len(second) >= 2:
                return '%s %s' % (top_term, second), [top_term, second]
            return top_term, [top_term]

    # 公共子串有效则返回（纯中文已在上方提前返回；此处处理含数字/拉丁的混合子串）
    if best_substr and len(best_substr) >= 2:
        cn_chars_in_substr = re.sub(r'[^\u4e00-\u9fff]', '', best_substr)
        if len(cn_chars_in_substr) <= 2 and _is_numeric_unit_phrase(best_substr):
            pass  # 纯数值单位，跳过，进入策略 3
        else:
            return best_substr, [best_substr]

    # ─ 策略 3：标题内相邻 token 高频组合（边界感知） ──
    ngram_counter = collections.Counter()
    for title in good_titles:
        tokens = _tokenize(title)
        quality_tokens = [t for t in tokens
                          if len(t) >= 2 and t not in _LABEL_NOISE_LOCAL and _is_valid_ngram(t)]
        # 连续 2-gram 和 3-gram
        for span in (2, 3):
            for j in range(len(quality_tokens) - span + 1):
                phrase = ' '.join(quality_tokens[j:j + span])
                # 至少有一个 token 长度 >= 3（避免两个短 token 拼出碎片）
                if any(len(quality_tokens[j + k]) >= 3 for k in range(span)):
                    # 额外检查：拼接后的总中文字符数 >= 4（避免 "多模态 发布" 这种松散组合）
                    cn_chars = re.sub(r'[^\u4e00-\u9fff]', '', phrase)
                    if len(cn_chars) >= 4:
                        # 质量过滤：含空格的短语需要额外验证
                        if ' ' in phrase:
                            no_space = phrase.replace(' ', '')
                            # 如果去空格后的组合在源标题中出现，说明空格是分词错误
                            if any(no_space in t for t in good_titles):
                                continue  # 跳过：分词错误，应为一个完整词组
                            # 所有 token 都是纯中文 → 松散拼接，跳过
                            parts_check = phrase.split()
                            if all(all('\u4e00' <= c <= '\u9fff' for c in part) for part in parts_check):
                                continue  # 跳过：纯中文 token 松散拼接
                        ngram_counter[phrase] += 1
    if ngram_counter:
        best_phrase = ngram_counter.most_common(1)[0][0]
        # 过滤数值单位短语
        cn_only = re.sub(r'[^\u4e00-\u9fff]', '', best_phrase)
        if len(cn_only) <= 4 and _is_numeric_unit_phrase(cn_only):
            pass  # 跳过，进入策略 4
        else:
            parts = best_phrase.split()
            return best_phrase, parts[:3]

    # ── 策略 4：兜底 — 从代表性标题中智能截取语义完整片段 ──
    # 选最长的合格标题作为代表性标题（信息量最大）
    representative = max(good_titles, key=len)
    phrase = _extract_meaningful_phrase(representative, max_len=14)
    if phrase and len(phrase) >= 4:
        return phrase, [phrase]

    # 最终兜底：直接取第一个合格标题的前 12 字
    for title in good_titles:
        if len(title) >= 6:
            truncated = title[:12].rstrip()
            for sep in ('，', '。', '：', '！', '？', ',', '.', ' ', ' '):
                idx = truncated.find(sep)
                if idx > 2:
                    truncated = truncated[:idx]
                    break
            return truncated, [truncated]

    return '', []


def _cluster_topics(rss_history, now_bj, max_topics=20, min_cluster=3):
    """基于标题+摘要关键词 Jaccard 相似度的话题聚类。返回话题列表。"""
    cutoff_24h = now_bj.replace(tzinfo=None) - datetime.timedelta(hours=24)
    # 通用单字过滤表（比 _STOP_WORDS 更严格，用于标签过滤）
    _LABEL_NOISE = set('的了是在我有和就不人都一个上也这到说们为你对被把让给用从向')
    # 收集近 24h 文章（标题 + 摘要关键词集合）
    articles = []
    for link, item in rss_history.items():
        pd_str = item.get('pub_date', '')
        if pd_str:
            try:
                pd = datetime.datetime.fromisoformat(pd_str)
                if pd.tzinfo:
                    pd = pd.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
            except ValueError:
                pd = now_bj.replace(tzinfo=None)
        else:
            pd = now_bj.replace(tzinfo=None)
        if pd < cutoff_24h:
            continue
        title = item.get('title_zh', '') or item.get('title', '')
        if not title:
            continue
        # 标题质量过滤：跳过明显病句（连续重复字 >= 2 处）
        if _has_repeated_chars(title, min_repeats=2, min_run=2):
            continue
        title_tokens = set(_tokenize(title))
        # 摘要 token 仅保留与标题有交集的（避免过长摘要稀释标题信号）
        summary = item.get('summary_zh', '') or item.get('summary', '')
        if summary and len(summary) > 30:
            summary_tokens = set(_tokenize(summary[:300]))  # 截断避免过长
            tokens = title_tokens | (summary_tokens & title_tokens)
        else:
            tokens = title_tokens
        if len(tokens) < 2:
            continue
        articles.append({
            'link': link,
            'title': title,
            'source': item.get('source', ''),
            'source_key': item.get('source_key', ''),
            'cat': item.get('cat', ''),
            'tokens': tokens,
            'title_tokens': title_tokens,
        })
    if len(articles) < min_cluster:
        return []
    # 贪心聚类
    clusters = []
    for art in articles:
        best_idx = -1
        best_sim = 0
        for i, cl in enumerate(clusters):
            # Jaccard 相似度: 文章 tokens 与簇质心（所有 tokens 的并集的高频子集）
            inter = len(art['tokens'] & cl['centroid'])
            union = len(art['tokens'] | cl['centroid'])
            sim = inter / union if union > 0 else 0
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_sim >= 0.25 and best_idx >= 0:
            clusters[best_idx]['articles'].append(art)
            # 更新质心：保留出现最多的 top 15 词
            all_tokens = collections.Counter()
            for a in clusters[best_idx]['articles']:
                all_tokens.update(a['tokens'])
            clusters[best_idx]['centroid'] = set(w for w, _ in all_tokens.most_common(15))
        else:
            clusters.append({
                'articles': [art],
                'centroid': set(art['tokens']),
            })
    # 过滤小簇，提取标签
    topics = []
    for cl in clusters:
        if len(cl['articles']) < min_cluster:
            continue
        # ── 标题召回机制：优先从标题中提取语义通顺的标签 ──
        label, labels = _extract_topic_label_from_titles(cl['articles'])
        # 清洗标签
        label = _clean_topic_label(label)
        labels = [_clean_topic_label(lb) for lb in labels if _clean_topic_label(lb)]
        # 如果标题召回失败，回退到原始 token 频率逻辑
        if not label:
            title_counter = collections.Counter()
            all_counter = collections.Counter()
            for a in cl['articles']:
                title_counter.update(a.get('title_tokens', a['tokens']))
                all_counter.update(a['tokens'])
            labels = [w for w, _ in title_counter.most_common(10)
                      if len(w) >= 2 and w not in _LABEL_NOISE and _is_valid_ngram(w)]
            if len(labels) < 2:
                labels = [w for w, _ in all_counter.most_common(10)
                          if len(w) >= 2 and w not in _LABEL_NOISE and _is_valid_ngram(w)]
            label = ' '.join(labels[:3]) if labels else ''
        # 去重源
        sources = list(set(a['source'] for a in cl['articles'] if a['source']))
        topics.append({
            'label': label,
            'labels': labels[:3],
            'count': len(cl['articles']),
            'sources': sources[:5],
            'links': [a['link'] for a in cl['articles'][:10]],
            'cats': list(set(a['cat'] for a in cl['articles'])),
        })
    # 按文章数排序，取前 max_topics 个
    topics.sort(key=lambda t: -t['count'])
    return topics[:max_topics]


def _generate_daily_summary(keywords, topics, stats, rising=None):
    """生成每日态势摘要。优先 Agnes AI 结构化 4 板块分析，降级为模板生成。
    返回 dict（结构化）或 str（降级兼容）。"""
    top_kw = [w for w, _ in keywords[:15]]
    top_topics = [t for t in topics[:8] if t.get('labels')]
    topic_desc = '; '.join(
        '%s(%d篇/%d源)' % (t['labels'][0], t['count'], len(t.get('sources', [])))
        for t in top_topics
    )
    rising_desc = ''
    if rising:
        rising_desc = ', '.join('%s(+%d)' % (r['word'], r['rise']) for r in rising[:8])
    # ── 降级方案：模板生成（返回 string，前端按旧格式渲染） ──
    def _template_summary():
        parts = []
        if top_kw:
            parts.append("今日关键词: " + "、".join(top_kw[:8]))
        if top_topics:
            parts.append("热点话题: " + "、".join(t['labels'][0] for t in top_topics if t['labels']))
        total = stats.get('total_articles', 0)
        recent = stats.get('recent_count', 0)
        parts.append("共 %d 篇文章，其中近 24 小时新增 %d 篇" % (total, recent))
        return "。".join(parts)
    # ── Agnes AI 结构化摘要 ──
    if not _AGNES_KEY:
        return _template_summary()
    system_prompt = (
        "你是一名高级科技情报分析师。你的核心能力是从海量碎片化信息中提炼核心逻辑，"
        "识别被大众忽略的弱信号。\n\n"
        "## 思维模型\n"
        "1. 见微知著：从散点关键词和话题中寻找底层共性叙事（如多个话题共同指向'AI应用落地'）。\n"
        "2. 交叉验证：RSS 专业视角与大众热榜的差异往往隐藏认知套利机会。\n"
        "3. 反直觉思考：当全网叫好时寻找风险，当全网恐慌时寻找机会。拒绝平庸共识。\n\n"
        "## 核心原则\n"
        "1. 直击要害：拒绝'综上所述'、'众所周知'等废话，直接输出结论。\n"
        "2. 逻辑闭环：不仅描述'发生了什么'，必须解释'为什么发生'以及'未来会怎样'。\n"
        "3. 去情绪化：可以分析舆论情绪，但你的分析必须冷静、客观。\n\n"
        "## 数据字段解读\n"
        "- 关键词：按 TF-IDF 评分排序，排名越靠前表示该词在近 24h 文章中越突出。\n"
        "- 升温词：括号内 +N 表示排名上升 N 位，数值越大表示升温越显著。\n"
        "- 话题簇：格式为 标签(文章数/信源数)，文章数越多表示该话题覆盖越广。\n\n"
        "## 输出格式（严格遵守 JSON）\n"
        "以 JSON 格式返回 4 个板块，所有值为纯文本字符串，禁止 Markdown/emoji：\n"
        '{"core_trends": "核心态势(100字内): 一句话定性 + 宏观主线 + 微观佐证",\n'
        ' "signals": "异动信号(80字内): 升温话题 + 异常波动",\n'
        ' "rss_insights": "RSS深度洞察(80字内): 专业视角补充的硬核信息",\n'
        ' "outlook": "研判建议(50字内): 具体建议，禁止空话"}\n\n'
        "## 正确示例\n"
        'core_trends: "Agent工程化进入系统化阶段。OpenAI、Google、Anthropic 同步推出企业级评估服务，'
        '标志从\'能用\'到\'可观测\'的拐点。"\n'
        'signals: "Agent评估服务升温(+15位)、LangSmith Trace Analytics 发布、CrewAI 集成 OpenTelemetry"\n'
        'outlook: "Agent基础设施竞争加剧，关注评估标准统一化进程"'
    )
    user_prompt = (
        "请分析以下 RSS 聚合数据：\n\n"
        "## 数据概览\n"
        "- 文章总数: %d, 近24h新增: %d\n"
        "- 信源数: %d\n\n"
        "## Top 关键词\n%s\n\n"
        "## 升温词\n%s\n\n"
        "## 热点话题\n%s\n\n"
        "请撰写分析报告，以 JSON 格式返回 4 个板块。"
        % (stats.get('total_articles', 0), stats.get('recent_count', 0),
           stats.get('source_count', 0),
           "、".join(top_kw[:12]),
           rising_desc or "暂无升温词数据",
           topic_desc or "暂无话题数据")
    )
    payload = json.dumps({
        "model": "agnes-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.3,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://apihub.agnes-ai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + _AGNES_KEY,
            "User-Agent": "starhub-auto-update",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
        cand = (data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        if cand and len(cand) > 30:
            # 尝试提取 JSON（AI 可能在 JSON 前后加文字）
            parsed = _extract_json_from_text(cand)
            if parsed and isinstance(parsed, dict):
                # 验证至少有一个板块非空
                valid_keys = ['core_trends', 'signals', 'rss_insights', 'outlook']
                if any(parsed.get(k) for k in valid_keys):
                    total_chars = sum(len(str(parsed.get(k, ''))) for k in valid_keys)
                    print("[分析] AI 结构化摘要生成成功 (%d 字, %d 板块)" % (
                        total_chars, sum(1 for k in valid_keys if parsed.get(k))))
                    return parsed
            # JSON 解析失败但文本有效，尝试作为单段摘要（旧格式兼容）
            print("[分析] AI 返回非 JSON，作为单段摘要 (%d 字)" % len(cand))
            return cand
    except Exception as e:
        print("[分析] AI 摘要失败: %s，降级为模板" % e, file=sys.stderr)
    return _template_summary()


def _extract_json_from_text(text):
    """从 AI 返回文本中提取 JSON 对象。支持 markdown 代码块包裹和纯 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # 尝试提取第一个 { ... } 块
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _load_prev_analysis():
    """加载前一天的分析快照。返回 dict；损坏/非 dict（rev9 P3①）返回 None。"""
    if not os.path.exists(ANALYSIS_SNAPSHOT_FILE):
        return None
    try:
        with open(ANALYSIS_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_analysis_snapshot(analysis_data):
    """保存分析快照到 analysis_snapshot.json。"""
    try:
        _atomic_write_json(ANALYSIS_SNAPSHOT_FILE, analysis_data, ensure_ascii=False, indent=1)
        print("[分析] 保存分析快照 → %s" % ANALYSIS_SNAPSHOT_FILE)
    except Exception as e:
        print("[分析] 保存失败: %s" % e, file=sys.stderr)


def _save_source_quality(quality_data):
    """保存信源质量评分到 source_quality.json。"""
    try:
        _atomic_write_json(SOURCE_QUALITY_FILE, quality_data, ensure_ascii=False, indent=1)
        print("[分析] 保存信源评分 → %s (%d 个源)" % (SOURCE_QUALITY_FILE, len(quality_data)))
    except Exception as e:
        print("[分析] 信源评分保存失败: %s" % e, file=sys.stderr)


def _log_insight_tracking(analysis_data, mode="incremental"):
    """将洞察板块全量追踪数据追加写入 insight_tracking_history.jsonl。

    覆盖 RAGAS 评分、洞察文本、关键词、话题、统计指标与构建元信息，
    确保「日志所见即用户所见」。14 天滚动窗口，原子写入，异常安全。
    """
    try:
        now_bj = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        ragas = analysis_data.get("_ragas_eval", {})
        summary = analysis_data.get("summary", {})
        stats = analysis_data.get("stats", {})
        meta = analysis_data.get("meta", {})
        topic_clusters = analysis_data.get("topic_clusters", [])
        kw_global = analysis_data.get("keywords", {}).get("global", [])

        entry = {
            "ts": now_bj.isoformat(),
            "mode": mode,
            "overall": ragas.get("overall"),
            "context_coverage": ragas.get("context_coverage"),
            "faithfulness": ragas.get("faithfulness"),
            "relevance": ragas.get("relevance"),
            "feedback": ragas.get("feedback", ""),
            "iterations": ragas.get("iterations"),
            "threshold": ragas.get("threshold"),
            "passed": (ragas.get("overall", 0) >= ragas.get("threshold", 0.6))
                      if ragas.get("overall") is not None else None,
            "top_keywords": [w for w, _ in kw_global[:10]],
            "topic_labels": [c.get("label", "") for c in topic_clusters[:15]],
            "narrative": (analysis_data.get("narrative") or "")[:500],
            "core_trends": (summary.get("core_trends") or "")[:500],
            "rss_insights": (summary.get("rss_insights") or "")[:500],
            "outlook": (summary.get("outlook") or "")[:500],
            "stats": {
                "total_articles": stats.get("total_articles", 0),
                "recent_count": stats.get("recent_count", 0),
                "source_count": stats.get("source_count", 0),
            },
            "meta": {
                "llm_provider": meta.get("llm_provider", ""),
                "embed_model": meta.get("embed_model", ""),
                "elapsed_seconds": meta.get("elapsed_seconds", 0),
            },
            "stale": analysis_data.get("stale", False),
        }

        # 加载现有记录
        lines = []
        if os.path.exists(INSIGHT_TRACKING_FILE):
            try:
                with open(INSIGHT_TRACKING_FILE, "r", encoding="utf-8") as f:
                    lines = [l for l in f.readlines() if l.strip()]
            except Exception:
                lines = []

        # 追加新记录
        lines.append(json.dumps(entry, ensure_ascii=False) + "\n")

        # 14 天滚动窗口：淘汰过期条目
        cutoff = (now_bj - datetime.timedelta(days=14)).isoformat()
        filtered = []
        for line in lines:
            try:
                rec = json.loads(line)
                if rec.get("ts", "") >= cutoff:
                    filtered.append(line)
            except json.JSONDecodeError:
                continue
        lines = filtered

        # 原子写入
        _atomic_write_text(INSIGHT_TRACKING_FILE, "".join(lines))
        print("[分析] 洞察追踪日志已记录 → %s (保留 %d 条)"
              % (INSIGHT_TRACKING_FILE, len(lines)))
    except Exception as e:
        print("[分析] 洞察追踪日志失败: %s" % e, file=sys.stderr)


# ── 热榜轨迹追踪 ──

def _accumulate_hot_history(hot_snapshot, now_bj):
    """追加热榜快照到历史轨迹文件。保留 7 天数据，自动清理过期条目。
    hot_snapshot 格式: [{platform, name, items: [{rank, title, url, hot}]}]"""
    # 加载已有历史
    history = {}
    if os.path.exists(HOT_HISTORY_FILE):
        try:
            with open(HOT_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}
    ts = now_bj.isoformat()
    cutoff_7d = (now_bj - datetime.timedelta(days=7)).isoformat()
    for plat_data in hot_snapshot:
        plat = plat_data.get("platform", "")
        if not plat:
            continue
        if plat not in history:
            history[plat] = []
        # 追加本次快照条目
        for item in plat_data.get("items", []):
            title = item.get("title", "")
            if not title:
                continue
            history[plat].append({
                "title": title,
                "rank": item.get("rank", 0),
                "ts": ts,
            })
        # 清理超过 7 天的旧数据
        history[plat] = [e for e in history[plat] if e["ts"] >= cutoff_7d]
    try:
        _atomic_write_json(HOT_HISTORY_FILE, history, ensure_ascii=False, separators=(",", ":"))
        total = sum(len(v) for v in history.values())
        print("[热榜] 轨迹累积: %d 平台, %d 条记录" % (len(history), total))
    except Exception as e:
        print("[热榜] 轨迹写入失败: %s" % e, file=sys.stderr)
    return history


def _compute_hot_trends(hot_history):
    """从热榜历史中计算趋势标记。
    返回 {platform: {title: {trend, prev_rank, curr_rank, rise, duration}}}"""
    if not hot_history:
        return {}
    result = {}
    for plat, entries in hot_history.items():
        if not entries:
            continue
        # 按时间戳分组（每次快照为一个周期）
        periods = collections.OrderedDict()
        for e in entries:
            ts = e["ts"][:13]  # 截断到小时精度（同一批次的 ts 相同）
            if ts not in periods:
                periods[ts] = {}
            periods[ts][e["title"]] = e["rank"]
        if len(periods) < 1:
            continue
        period_keys = sorted(periods.keys())  # 按时间升序排列
        latest = period_keys[-1]
        prev = period_keys[-2] if len(periods) >= 2 else None
        latest_items = periods[latest]
        prev_items = periods[prev] if prev else {}
        plat_trends = {}
        for title, rank in latest_items.items():
            prev_rank = prev_items.get(title)
            if prev_rank is None:
                trend = "new"
                rise = 0
            else:
                diff = prev_rank - rank  # 正数=上升，负数=下降
                if diff >= 5:
                    trend = "rising"
                elif diff <= -5:
                    trend = "falling"
                else:
                    trend = "stable"
                rise = diff
            # 计算在榜持续时长（周期数）
            duration = 0
            for pk in reversed(period_keys):
                if title in periods[pk]:
                    duration += 1
                else:
                    break
            plat_trends[title] = {
                "trend": trend,
                "curr_rank": rank,
                "prev_rank": prev_rank,
                "rise": rise,
                "duration": duration,
            }
        # 检测 "gone" 状态：任何非最新周期中存在、但最新周期中不存在、且脱榜超 2 个周期的条目
        all_prev_titles = {}
        for pk in period_keys[:-1]:  # 除最新周期外的所有周期
            for title, rank in periods[pk].items():
                if title not in latest_items:
                    all_prev_titles[title] = rank  # 保留最后出现的排名
        for gone_title, gone_rank in all_prev_titles.items():
            # 计算脱榜周期数（从最新周期往前数，不在榜的连续周期数）
            absent_count = 0
            for pk in reversed(period_keys):
                if gone_title not in periods[pk]:
                    absent_count += 1
                else:
                    break
            if absent_count > 2:
                plat_trends[gone_title] = {
                    "trend": "gone",
                    "curr_rank": None,
                    "prev_rank": gone_rank,
                    "rise": 0,
                    "duration": 0,
                }
        result[plat] = plat_trends
    return result


def _cross_platform_topics(hot_history, hot_snapshot):
    """检测跨平台共振话题：同一话题在 2+ 平台同时上榜。
    返回 [{label, platforms: [{name, rank}]}]"""
    if not hot_snapshot or len(hot_snapshot) < 2:
        return []
    # 收集各平台最新快照的标题集合
    plat_titles = {}
    for plat_data in hot_snapshot:
        plat = plat_data.get("platform", "")
        titles = []
        for item in plat_data.get("items", []):
            t = item.get("title", "")
            if t:
                titles.append({"title": t, "rank": item.get("rank", 99)})
        if titles:
            plat_titles[plat] = titles
    if len(plat_titles) < 2:
        return []
    # 两两比较平台间的标题相似度
    plat_names = list(plat_titles.keys())
    # 为每个标题建立 token 集合
    title_tokens = {}
    for plat, titles in plat_titles.items():
        for td in titles:
            key = plat + ":" + td["title"]
            title_tokens[key] = set(_tokenize(td["title"]))
    # 跨平台匹配
    matched = []  # [(label, [(plat, rank), ...])]
    used = set()  # 已匹配的标题 key
    for i in range(len(plat_names)):
        for j in range(i + 1, len(plat_names)):
            p1, p2 = plat_names[i], plat_names[j]
            for t1 in plat_titles[p1]:
                k1 = p1 + ":" + t1["title"]
                if k1 in used:
                    continue
                for t2 in plat_titles[p2]:
                    k2 = p2 + ":" + t2["title"]
                    if k2 in used:
                        continue
                    # Jaccard 相似度
                    tok1 = title_tokens.get(k1, set())
                    tok2 = title_tokens.get(k2, set())
                    if not tok1 or not tok2:
                        continue
                    inter = len(tok1 & tok2)
                    union = len(tok1 | tok2)
                    sim = inter / union if union > 0 else 0
                    if sim >= 0.3:
                        # 匹配成功，检查是否已有该话题
                        label = t1["title"] if len(t1["title"]) <= len(t2["title"]) else t2["title"]
                        found = False
                        for m in matched:
                            if m["label"] == label:
                                # 追加平台
                                existing_plats = {p["name"] for p in m["platforms"]}
                                if p1 not in existing_plats:
                                    m["platforms"].append({"name": p1, "rank": t1["rank"]})
                                if p2 not in existing_plats:
                                    m["platforms"].append({"name": p2, "rank": t2["rank"]})
                                found = True
                                break
                        if not found:
                            matched.append({
                                "label": label,
                                "platforms": [
                                    {"name": p1, "rank": t1["rank"]},
                                    {"name": p2, "rank": t2["rank"]},
                                ],
                            })
                        used.add(k1)
                        used.add(k2)
                        break  # t1 已匹配，跳出内层
    # 按平台数降序，过滤仅 1 个平台的
    matched = [m for m in matched if len(m["platforms"]) >= 2]
    matched.sort(key=lambda m: -len(m["platforms"]))
    # 添加 platform_count 字段
    for m in matched:
        m["platform_count"] = len(m["platforms"])
    return matched[:15]


# ── RSS 内容趋势轨迹追踪 ──

def _accumulate_rss_trend_history(analysis_data, now_bj):
    """追加当前构建的关键词/话题快照到 RSS 趋势历史。保留 14 天。"""
    history = {"snapshots": []}
    if os.path.exists(RSS_TREND_HISTORY_FILE):
        try:
            with open(RSS_TREND_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {"snapshots": []}
    # 提取当前快照的关键词排名 dict
    kw_rank = {}
    kw_data = analysis_data.get("keywords", {})
    for i, (w, _) in enumerate(kw_data.get("global", [])):
        kw_rank[w] = i + 1
    # 提取分类关键词
    by_cat = {}
    for cat, kws in kw_data.get("by_cat", {}).items():
        by_cat[cat] = [w for w, _ in kws[:20]]
    # 提取话题摘要
    topics_summary = []
    for t in analysis_data.get("topics", []):
        topics_summary.append({
            "label": t.get("label", ""),
            "count": t.get("count", 0),
            "sources": len(t.get("sources", [])),
        })
    # 追加新快照（D4：记录不可信日期源名单，供趋势/关键词降权消费）
    snapshot = {
        "ts": now_bj.isoformat(),
        "keywords": kw_rank,
        "topics": topics_summary,
        "by_cat": by_cat,
        "bad_date_sources": sorted(_LAST_UNRELIABLE_SRCS),
        # D3 轻量场：本快照的语义主题为沿用值，消费方可据此识别平台期
        "stale": bool(analysis_data.get("stale")),
    }
    history["snapshots"].append(snapshot)
    # 清理超过 14 天的旧快照
    cutoff_14d = (now_bj - datetime.timedelta(days=14)).isoformat()
    history["snapshots"] = [s for s in history["snapshots"] if s["ts"] >= cutoff_14d]
    try:
        _atomic_write_json(RSS_TREND_HISTORY_FILE, history, ensure_ascii=False, separators=(",", ":"))
        print("[分析] RSS 趋势历史累积: %d 个快照" % len(history["snapshots"]))
    except Exception as e:
        print("[分析] RSS 趋势历史写入失败: %s" % e, file=sys.stderr)
    return history


def _compute_rss_trajectories(trend_history):
    """从 RSS 趋势历史中计算关键词和话题的跨周期轨迹。
    返回 {keywords: {word: {lifecycle, first_seen, latest_rank, duration, rank_history}},
          topics: {label: {lifecycle, count_history, peak_count, duration}}}"""
    snapshots = trend_history.get("snapshots", [])
    if len(snapshots) < 2:
        return {"keywords": {}, "topics": {}}
    # ── 关键词轨迹 ──
    kw_trajectories = {}
    # 收集所有出现过的关键词
    all_keywords = set()
    for s in snapshots:
        all_keywords.update(s.get("keywords", {}).keys())
    for kw in all_keywords:
        # 构建排名序列（None = 未出现）
        rank_seq = []
        first_seen = None
        for s in snapshots:
            rank = s.get("keywords", {}).get(kw)
            rank_seq.append(rank)
            if rank is not None and first_seen is None:
                first_seen = s["ts"]
        latest_rank = rank_seq[-1]
        # 计算连续出现周期数
        duration = 0
        for r in reversed(rank_seq):
            if r is not None:
                duration += 1
            else:
                break
        # 计算消失周期数
        absent = 0
        for r in reversed(rank_seq):
            if r is None:
                absent += 1
            else:
                break
        # 生命周期标记
        if latest_rank is None and absent >= 3:
            lifecycle = "gone"
        elif duration <= 2 and first_seen == snapshots[-1].get("ts"):
            lifecycle = "emergent"
        else:
            # 检查排名趋势（仅看有值的周期）
            valid_ranks = [(i, r) for i, r in enumerate(rank_seq) if r is not None]
            if len(valid_ranks) >= 3:
                recent = valid_ranks[-3:]
                rises = sum(1 for j in range(1, len(recent)) if recent[j][1] < recent[j-1][1])
                falls = sum(1 for j in range(1, len(recent)) if recent[j][1] > recent[j-1][1])
                if rises >= 2:
                    lifecycle = "rising"
                elif falls >= 2:
                    lifecycle = "declining"
                elif latest_rank is not None and latest_rank <= 10:
                    lifecycle = "peaking"
                else:
                    lifecycle = "stable"
            elif len(valid_ranks) == 2:
                if valid_ranks[-1][1] < valid_ranks[-2][1]:
                    lifecycle = "rising"
                elif valid_ranks[-1][1] > valid_ranks[-2][1]:
                    lifecycle = "declining"
                else:
                    lifecycle = "stable"
            else:
                lifecycle = "stable"
        kw_trajectories[kw] = {
            "lifecycle": lifecycle,
            "first_seen": first_seen or "",
            "latest_rank": latest_rank,
            "duration": duration,
        }
    # ── 话题轨迹 ──
    topic_trajectories = {}
    # 用 Jaccard 相似度匹配跨快照的同一话题
    latest_topics = snapshots[-1].get("topics", [])
    if not latest_topics:
        return {"keywords": kw_trajectories, "topics": {}}
    latest_token_sets = {}
    for t in latest_topics:
        label = t.get("label", "")
        latest_token_sets[label] = set(_tokenize(label))
    for t in latest_topics:
        label = t.get("label", "")
        tok_set = latest_token_sets.get(label, set())
        count_seq = []
        matched_label = label
        for s in snapshots:
            best_count = 0
            best_match = ""
            for ht in s.get("topics", []):
                ht_label = ht.get("label", "")
                if not ht_label:
                    continue
                ht_tokens = set(_tokenize(ht_label))
                if not tok_set or not ht_tokens:
                    continue
                inter = len(tok_set & ht_tokens)
                union = len(tok_set | ht_tokens)
                sim = inter / union if union > 0 else 0
                if sim >= 0.3 and ht.get("count", 0) > best_count:
                    best_count = ht["count"]
                    best_match = ht_label
            count_seq.append(best_count if best_match else 0)
            if best_match:
                matched_label = best_match
        latest_count = count_seq[-1] if count_seq else 0
        # 话题生命周期
        valid_counts = [c for c in count_seq if c > 0]
        if not valid_counts:
            lifecycle = "cold"
        elif len(valid_counts) <= 1:
            lifecycle = "emerging"
        else:
            recent_counts = valid_counts[-3:] if len(valid_counts) >= 3 else valid_counts
            if latest_count > 10 and all(recent_counts[i] <= recent_counts[i+1] for i in range(len(recent_counts)-1)):
                lifecycle = "hot"
            elif len(recent_counts) >= 2 and all(recent_counts[i] >= recent_counts[i+1] for i in range(len(recent_counts)-1)):
                lifecycle = "cooling"
            elif latest_count < 3:
                lifecycle = "cold"
            else:
                lifecycle = "emerging"
        topic_trajectories[matched_label] = {
            "lifecycle": lifecycle,
            "latest_count": latest_count,
            "peak_count": max(valid_counts) if valid_counts else 0,
            "duration": len(valid_counts),
        }
    return {"keywords": kw_trajectories, "topics": topic_trajectories}


def _compute_cross_category_topics(kw_data):
    """检测同一关键词在多个 RSS 分类中同时热门。
    返回 [{keyword, categories: [cat, ...], category_count}]"""
    by_cat = kw_data.get("by_cat", {})
    if len(by_cat) < 2:
        return []
    # 收集每个分类的 Top 20 关键词
    cat_kw_sets = {}
    for cat, kws in by_cat.items():
        cat_kw_sets[cat] = set(w for w, _ in kws[:20])
    # 统计每个关键词出现在多少个分类中
    kw_cats = collections.defaultdict(list)
    for cat, kw_set in cat_kw_sets.items():
        for kw in kw_set:
            kw_cats[kw].append(cat)
    # 过滤仅出现在 1 个分类的，按分类数降序
    cross = []
    for kw, cats in kw_cats.items():
        if len(cats) >= 2:
            cross.append({
                "keyword": kw,
                "categories": sorted(cats),
                "category_count": len(cats),
            })
    cross.sort(key=lambda x: -x["category_count"])
    return cross[:20]


def _run_analysis(sources_with_items, now_bj, hot_snapshot=None, hot_history=None, mode="incremental"):
    """执行智能分析流水线。

    D3 轻/重分级：重分析（语义聚类/深度洞察/RAGAS）按 insight_heavy_interval_hours
    （默认 6h；full 模式无条件重跑）间隔运行，轻量场复用上次重字段并标注 stale=true；
    统计字段（关键词/趋势/质量/轨迹）每场照算。insight_engine 不可用时回退统计方法。
    """
    prev_analysis = _load_prev_analysis()
    ie_cfg = {}
    engine_on = False
    try:
        import insight_engine
        ie_cfg = insight_engine.load_config()
        engine_on = bool(ie_cfg.get("insight_engine_enabled", True))
    except Exception:
        engine_on = False
    heavy_due = True
    if engine_on:
        try:
            _interval = float(ie_cfg.get("insight_heavy_interval_hours", 6))
            if not math.isfinite(_interval) or _interval <= 0:
                _interval = 6.0  # NaN 比较恒 False 会锁死轻量模式（rev8 P2-3）
        except (TypeError, ValueError):
            _interval = 6.0
        _prev_gen = (prev_analysis or {}).get("generated_at", "")
        # P1-2 修复（对抗性审查 f168c43）：语义字段（deep_insights）缺失也触发重分析——
        # 重分析失败时统计路径会刷新 generated_at，仅看时间会把退化态锁定一整个间隔
        _semantics_missing = not (prev_analysis or {}).get("deep_insights")
        if not _prev_gen or mode == "full" or _interval <= 0 or _semantics_missing:
            heavy_due = True
        else:
            try:
                _pg = datetime.datetime.fromisoformat(_prev_gen)
                if _pg.tzinfo:
                    _pg = _pg.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
                heavy_due = (now_bj.replace(tzinfo=None) - _pg).total_seconds() >= _interval * 3600
            except (TypeError, ValueError):
                heavy_due = True
    if engine_on and heavy_due:
        # ── 重分析：insight_engine (LlamaIndex) ──
        try:
            import insight_engine
            prev_keywords = []
            if prev_analysis and prev_analysis.get("keywords", {}).get("global"):
                prev_keywords = [w for w, _ in prev_analysis["keywords"]["global"][:50]]
            # 读取 Trending 数据供 insight engine 使用
            trending_data = {}
            try:
                with open(TRENDING_SNAPSHOT_FILE, "r", encoding="utf-8") as _f:
                    trending_data = json.load(_f)
            except Exception:
                pass
            ie_result = insight_engine.run_analysis(
                hot_snapshot=hot_snapshot,
                rss_history=_rss_history,
                trending_data=trending_data,
                config=ie_cfg,
                prev_keywords=prev_keywords,
                hot_history=hot_history,
                bad_date_sources=set(_LAST_UNRELIABLE_SRCS),
            )
            if ie_result is not None:
                # 合并原有需要保留的字段（热榜趋势、RSS轨迹等仍由旧方法计算）
                ie_result["hot_trends"] = _compute_hot_trends(hot_history) if hot_history else {}
                trend_history = _accumulate_rss_trend_history(ie_result, now_bj)
                ie_result["rss_trajectories"] = _compute_rss_trajectories(trend_history)
                if not ie_result.get("cross_category"):
                    ie_result["cross_category"] = _compute_cross_category_topics(
                        ie_result.get("keywords", {}))
                quality = _score_sources(sources_with_items, _rss_history)
                _save_source_quality(quality)
                # 保存 RAGAS 评估数据（在 quality 被信源质量分覆盖前）
                _ragas_raw = ie_result.get("quality", {})
                if isinstance(_ragas_raw, dict) and "overall" in _ragas_raw:
                    ie_result["_ragas_eval"] = _ragas_raw
                ie_result["quality"] = {sk: v["score"] for sk, v in quality.items()}
                _save_analysis_snapshot(ie_result)
                _log_insight_tracking(ie_result, mode)
                print("[分析] insight_engine (LlamaIndex) 重分析完成")
                return ie_result
        except ImportError:
            print("[分析] insight_engine 未安装，回退统计方法")
        except Exception as e:
            print("[分析] insight_engine 失败: %s，回退统计方法" % e, file=sys.stderr)
            import traceback; traceback.print_exc()
    elif engine_on:
        print("[分析] 轻量模式：距上次重分析不足间隔，语义主题/深度洞察沿用旧值")
    # ── 统计路径（insight_engine 关闭/失败/轻量场共用）──
    t0 = time.time()
    print("[分析] 开始智能分析...")
    # 1. 信源质量评分
    quality = _score_sources(sources_with_items, _rss_history)
    _save_source_quality(quality)
    # 2. 关键词提取
    kw_data = _extract_keywords(_rss_history, now_bj, _LAST_UNRELIABLE_SRCS)
    global_kw = kw_data["global"]
    # 3. 趋势检测（与上次构建对比）
    prev_kw = prev_analysis.get("keywords", {}).get("global", []) if prev_analysis else []
    rising = []
    if prev_kw:
        prev_freq = {w: i + 1 for i, (w, _) in enumerate(prev_kw[:50])}
        curr_freq = {w: i + 1 for i, (w, _) in enumerate(global_kw[:50])}
        for w, rank in curr_freq.items():
            prev_rank = prev_freq.get(w, 999)
            if prev_rank > rank + 5:  # 排名上升超过 5 位
                rising.append({"word": w, "rise": prev_rank - rank, "current_rank": rank})
        rising.sort(key=lambda x: -x["rise"])
        rising = rising[:15]
    # 4. 话题聚类
    topics = _cluster_topics(_rss_history, now_bj)
    # 5. 统计摘要
    total_articles = len(_rss_history)
    stats = {
        'total_articles': total_articles,
        'recent_count': kw_data['recent_count'],
        'source_count': len(sources_with_items),
    }
    # 6. AI 摘要（传入升温词数据以增强分析深度）
    summary = _generate_daily_summary(global_kw, topics, stats, rising=rising)
    # 7. 热榜趋势标记
    hot_trends = _compute_hot_trends(hot_history) if hot_history else {}
    # 8. 跨平台共振检测
    cross_platform = _cross_platform_topics(hot_history, hot_snapshot) if hot_snapshot else []
    # 组装结果
    analysis = {
        'generated_at': now_bj.isoformat(),
        'keywords': {
            'global': [(w, round(s, 2)) for w, s in global_kw[:50]],
            'by_cat': {cat: [(w, round(s, 2)) for w, s in kws[:20]] for cat, kws in kw_data['by_cat'].items()},
        },
        'rising': rising,
        'topics': topics,
        'summary': summary,
        'stats': stats,
        'quality': {sk: v['score'] for sk, v in quality.items()},
        'hot_trends': hot_trends,
        'cross_platform': cross_platform,
    }
    # D3 轻量场：语义主题/深度洞察/RAGAS 等重字段沿用上次重分析，诚实标注 stale；
    # generated_at 保持上次重分析时间（前端据此展示真实新鲜度）
    # P1-2 修复：overlay 无条件复用——重分析失败（insight_engine 抛异常）时统计路径
    # 也要沿用上次的语义主题/深度洞察，并诚实标注 stale，防止退化态无痕。
    # rev8 P1-2：语义主题/簇结构/深度洞察/RAGAS 显式沿用 prev（统计聚类的 topics 键
    # 恒存在会顶掉语义主题——spec D3 承诺 light 场主题数据不回退）
    if prev_analysis:
        for _k in ("topics", "topic_clusters", "deep_insights", "ragas",
                   "narrative", "cross_platform_semantic"):
            if prev_analysis.get(_k) is not None:
                analysis[_k] = prev_analysis[_k]
        for _k, _v in prev_analysis.items():
            if _k not in analysis and _k != "bad_date_sources":
                analysis[_k] = _v
        analysis["stale"] = True
        analysis["generated_at"] = prev_analysis.get("generated_at") or analysis["generated_at"]
    _save_analysis_snapshot(analysis)
    # 9. RSS 内容趋势历史累积（在 analysis_snapshot 保存后，以便读取当前关键词数据）
    trend_history = _accumulate_rss_trend_history(analysis, now_bj)
    # 10. RSS 关键词/话题轨迹计算
    rss_trajectories = _compute_rss_trajectories(trend_history)
    analysis['rss_trajectories'] = rss_trajectories
    # 11. 跨分类话题检测
    cross_category = _compute_cross_category_topics(kw_data)
    analysis['cross_category'] = cross_category
    # 重新保存（含轨迹和跨分类数据）
    _save_analysis_snapshot(analysis)
    # 轻量模式：从旧分析中提取 RAGAS 评估数据
    if prev_analysis and "_ragas_eval" not in analysis:
        _prev_q = prev_analysis.get("quality", {})
        if isinstance(_prev_q, dict) and "overall" in _prev_q:
            analysis["_ragas_eval"] = _prev_q
    _log_insight_tracking(analysis, mode)
    elapsed = round(time.time() - t0, 1)
    n_kw_traj = len(rss_trajectories.get('keywords', {}))
    n_topic_traj = len(rss_trajectories.get('topics', {}))
    print("[分析] 完成: %d 个关键词, %d 个话题, %d 个升温词, %d 个跨平台话题, "
          "%d 个关键词轨迹, %d 个话题轨迹, %d 个跨分类话题, 耗时 %.1fs" % (
        len(global_kw), len(topics), len(rising), len(cross_platform),
        n_kw_traj, n_topic_traj, len(cross_category), elapsed))
    return analysis


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
    failed_count = 0
    _source_log = []  # 每源抓取结果
    _build_start = time.time()

    # 增量模式：预建历史索引（source_key → items），避免每源遍历全部历史
    _hist_by_key = {}
    if mode == "incremental":
        for _v in _rss_history.values():
            _sk = _v.get("source_key", "")
            if _sk not in _hist_by_key:
                _hist_by_key[_sk] = []
            _hist_by_key[_sk].append({
                "link": _v["link"], "pub_date": _v.get("pub_date", ""),
                "title": _v.get("title", ""), "title_zh": _v.get("title_zh", ""),
                "summary": _v.get("summary", ""), "summary_zh": _v.get("summary_zh", ""),
                "full_content": _v.get("full_content", ""), "image": _v.get("image", ""),
                "media_url": _v.get("media_url", ""), "media_type": _v.get("media_type", ""),
            })
        print("[增量模式] 历史索引: %d 源有历史数据" % len(_hist_by_key))

    # 并行抓取 RSS（短超时，失败快速跳过）
    # - 全局并发 12；同一域名并发 2（对单域行为接近串行，避免打爆 xgo.ing 等桥接服务）
    # - 域级熔断：同域名连续 3 次失败则本轮跳过该域剩余源，下轮增量再试
    # - 流水线：某源抓完即在主线程串行翻译，与其余源的网络 IO 重叠；翻译不进线程池（翻译服务有限流）
    _results = [None] * len(RSS_SOURCES)  # 按 RSS_SOURCES 顺序回填，保持产物顺序稳定

    # 主线程分流：增量跳过判断（含 T1/缓存命中回填）不涉及网络 IO，直接定结果
    _to_fetch = []
    for _i, src in enumerate(RSS_SOURCES):
        key = src["key"]
        tier = src.get("tier", 3)

        # 增量模式跳过规则（按 tier 分级阈值）：
        # 1. T1 源始终跳过（由 api/rss.js 实时抓取）
        # 2. T2 源：距上次抓取 < 1h 跳过
        # 3. T3 源：距上次抓取 < 2h 跳过
        if mode == "incremental":
            if tier == 1:
                skipped_count += 1
                # 从历史索引填充 T1 源（增量构建不抓取 T1，但不能传空 items 导致历史数据流失）
                _results[_i] = {
                    "key": key, "name": src["name"], "cat": src["cat"],
                    "color": src.get("color", "#6366f1"), "url": src.get("url", ""),
                    "items": _hist_by_key.get(key, []),
                    "tier": tier,
                }
                _source_log.append({"key": key, "name": src["name"], "cat": src["cat"], "tier": tier, "status": "skipped_t1", "items": len(_hist_by_key.get(key, []))})
                continue
            prev = last_fetch.get(key)
            if prev:
                try:
                    prev_time = datetime.datetime.fromisoformat(prev)
                    # Fix 4: T4 源使用更宽松的跳过阈值
                    if tier == 4:
                        threshold_sec = _TIER4_SKIP_THRESHOLD_SEC
                    elif tier <= 2:
                        threshold_sec = 1 * 3600
                    else:
                        threshold_sec = 2 * 3600
                    if (now - prev_time).total_seconds() < threshold_sec:
                        # Fix 1v2: 无历史数据的源强制重抓（无论是否有 prev 记录）
                        # 场景：源上次抓取返回 0 条 → prev 有值但 _hist_by_key 为空
                        # 旧版 `and not prev` 在 if prev: 块内永远 False → 死代码
                        if not _hist_by_key.get(key):
                            pass  # 强制重抓，不跳过
                        else:
                            skipped_count += 1
                            # 从历史索引填充跳过的 T2/T3 源（避免空 items 导致历史数据流失）
                            _results[_i] = {
                                "key": key, "name": src["name"], "cat": src["cat"],
                                "color": src.get("color", "#6366f1"), "url": src.get("url", ""),
                                "items": _hist_by_key.get(key, []),
                                "tier": tier,
                            }
                            _source_log.append({"key": key, "name": src["name"], "cat": src["cat"], "tier": tier, "status": "skipped_cached", "items": len(_hist_by_key.get(key, []))})
                            continue
                except (ValueError, TypeError):
                    pass
        _to_fetch.append((_i, src))

    # 域名信号量与熔断状态全部在提交任务前于主线程建好，规避运行期并发初始化竞争
    def _src_domain(url):
        m = re.match(r"https?://([^/]+)", url or "")
        return m.group(1) if m else ""

    _domain_sems = {}
    for src in RSS_SOURCES:
        _d = _src_domain(src.get("url", ""))
        if _d and _d not in _domain_sems:
            _domain_sems[_d] = threading.Semaphore(2)
    _domain_lock = threading.Lock()
    _domain_failstreak = collections.defaultdict(int)  # 域名 → 连续失败数
    _domain_broken = set()  # 本轮已熔断域名

    def _worker(i, src):
        """只做网络 IO 与域名熔断判定；计数、翻译、last_fetch 由主线程汇总"""
        dom = _src_domain(src.get("url", ""))
        with _domain_lock:
            if dom and dom in _domain_broken:
                return i, src, None, "domain_broken"
        try:
            if dom:
                with _domain_sems[dom]:
                    items = _fetch_rss(src, timeout=src.get("timeout"))
            else:
                items = _fetch_rss(src, timeout=src.get("timeout"))
        except Exception:
            items = []
        ok = len(items) > 0
        with _domain_lock:
            if ok:
                _domain_failstreak[dom] = 0
            elif dom:
                _domain_failstreak[dom] += 1
                if _domain_failstreak[dom] >= 3:
                    _domain_broken.add(dom)
        return i, src, items, ("ok" if ok else "empty")

    # 翻译线程池：有界并发（6 源并发），不拖住抓取主循环；Agnes 429/全链熔断时自动降级
    _trans_pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
    _trans_futs = []
    _pool = concurrent.futures.ThreadPoolExecutor(max_workers=12)
    try:
        _futs = {_pool.submit(_worker, i, src): (i, src) for i, src in _to_fetch}
        for _fut in concurrent.futures.as_completed(_futs):
            i, src = _futs[_fut]
            try:
                _, src, items, status = _fut.result()
            except Exception as _ex:
                # 单个 worker 意外异常不拖垮整场构建：该源按失败处理，其余继续
                print("[RSS聚合] %s worker 异常: %s" % (src["name"], _ex), file=sys.stderr)
                items, status = [], "empty"
            key = src["key"]
            tier = src.get("tier", 3)
            n = len(items) if items else 0
            if status == "ok":
                ok_count += 1
                last_fetch[key] = now.isoformat()
                # Fix 4: T4 源连续成功后自动升级到 T3
                if tier == 4:
                    _tier4_success_streak[key] = _tier4_success_streak.get(key, 0) + 1
                    if _tier4_success_streak[key] >= _TIER_PROMOTION_THRESHOLD:
                        src["tier"] = 3
                        print("[T4升级] %s 连续 %d 次成功 → 升级到 T3" % (src["name"], _tier4_success_streak[key]))
                        del _tier4_success_streak[key]
                else:
                    _tier4_success_streak[key] = 0  # 非 T4 源重置连续计数
                # 翻译交给独立线程池有界并发；完成顺序不影响最终产物顺序
                if items:
                    _trans_futs.append(_trans_pool.submit(_translate_source_items, items))
            else:
                failed_count += 1
                if items is None:
                    items = []
            _results[i] = {
                "key": key, "name": src["name"], "cat": src["cat"],
                "color": src.get("color", "#6366f1"), "url": src.get("url", ""),
                "items": items,
                "tier": tier,
            }
            total_items += n
            print("[RSS聚合] %s: %d 条%s" % (src["name"], n, "（域熔断跳过）" if status == "domain_broken" else ""))
            _source_log.append({"key": key, "name": src["name"], "cat": src["cat"], "tier": tier, "status": status, "items": n})
    except BaseException:
        # 中断（Ctrl+C/任务取消）时丢弃排队任务立即退出，避免 shutdown(wait=True) 等完上千个待抓源
        _pool.shutdown(wait=False, cancel_futures=True)
        _trans_pool.shutdown(wait=False, cancel_futures=True)
        raise
    _pool.shutdown(wait=True)
    # 等待全部源级翻译完成（下游历史累积/渲染依赖 title_zh）
    for _tf in _trans_futs:
        try:
            _tf.result()
        except Exception as _ex:
            print("[翻译] 条目翻译任务异常: %s" % _ex, file=sys.stderr)
    _trans_pool.shutdown(wait=True)

    sources_with_items.extend(r for r in _results if r is not None)

    if mode == "incremental":
        print("[增量模式] 跳过 %d 个源，抓取 %d 个源" % (skipped_count, len(RSS_SOURCES) - skipped_count))

    if total_items == 0 and mode == "full":
        print("[RSS聚合] 所有源均失败，尝试使用历史数据", file=sys.stderr)

    # 累积到 72 小时历史，用累积数据替换当次抓取
    _history_before = len(_rss_history)
    # Fix 3: 保存抓取阶段数字，避免被历史重组覆写导致日志口径不一致
    _items_fetched = total_items
    _sources_with_data_before = sum(1 for s in sources_with_items if s.get("items"))
    sources_with_items, total_items = _accumulate_history(sources_with_items)
    _history_after = len(_rss_history)

    # ── 历史回流图片补升级（历史缓存中的旧 URL 未经 _upgrade_img_url）──
    _hist_upgraded = 0
    for _src in sources_with_items:
        for _it in _src.get("items", []):
            _old_img = _it.get("image", "")
            if _old_img:
                _new_img = _upgrade_img_url(_old_img)
                if _new_img != _old_img:
                    _it["image"] = _new_img
                    _hist_upgraded += 1
    if _hist_upgraded:
        print("[图片升级] 历史缓存补升级 %d 张" % _hist_upgraded)

    # ── 图片质量审计（自动发现低分辨率缩略图）──
    try:
        _audit_image_quality(sources_with_items)
    except Exception as e:
        print("[图片审计] 审计失败，跳过: %s" % e, file=sys.stderr)

    # ── 智能分析流水线（关键词 / 话题 / AI 摘要 / 信源评分 / 热榜轨迹 / 跨平台） ──
    analysis_data = None
    hot_snapshot = None
    hot_history = {}
    if ANALYSIS_ENABLED:
        try:
            now_bj = _now_bj()
            # 抓取热榜快照（在分析前获取，以便轨迹累积和跨平台关联）
            try:
                hot_snapshot = fetch_newsnow_snapshot()
                try:
                    _atomic_write_json(HOT_SNAPSHOT_FILE, hot_snapshot, ensure_ascii=False, separators=(",", ":"))
                except Exception as e:
                    print("[热榜] 快照写入失败: %s" % e, file=sys.stderr)
            except Exception as e:
                print("[热榜] 快照抓取失败: %s" % e, file=sys.stderr)
                hot_snapshot = []
            # 累积热榜历史轨迹（始终执行，确保 hot_history.json 被创建）
            hot_history = _accumulate_hot_history(hot_snapshot or [], now_bj)
            analysis_data = _run_analysis(sources_with_items, now_bj,
                                          hot_snapshot=hot_snapshot, hot_history=hot_history,
                                          mode=mode)
        except Exception as e:
            print("[分析] 智能分析失败，跳过: %s" % e, file=sys.stderr)
            import traceback; traceback.print_exc()

    # 若分析未启用，仍需抓取热榜快照
    if not ANALYSIS_ENABLED:
        hot_snapshot = fetch_newsnow_snapshot()
        try:
            _atomic_write_json(HOT_SNAPSHOT_FILE, hot_snapshot, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print("[热榜] 快照写入失败: %s" % e, file=sys.stderr)

    # ── 为每篇文章提取话题标签（供前端 diverse/topic 模式消费）──
    try:
        _tag_articles(sources_with_items)
        _tagged = sum(1 for s in sources_with_items for it in s.get("items", []) if it.get("tags"))
        print("[标签] 已为 %d 篇文章提取话题标签" % _tagged)
    except Exception as e:
        print("[标签] 提取失败，跳过: %s" % e, file=sys.stderr)

    # 生成 API 快照（供 /api/rss 直接返回，避免实时抓取丢失历史累积数据）
    # 必须晚于 _tag_articles()：快照构造只搬用白名单字段，早于打标则 tags 恒为空。
    # 仍早于 build_html / write_data_chunks，保证产物写出异常时快照已落地。
    meta = {"last_fetch": last_fetch}
    _save_api_snapshot(sources_with_items, meta=meta)

    html_doc = build_html(sources_with_items, build_time, total_items, build_ts_ms, analysis_data=analysis_data,
                          diverse_window_minutes=DIVERSE_CFG["window_minutes"],
                          diverse_enabled=DIVERSE_CFG["enabled"])
    _atomic_write_text(OUT, html_doc)

    # 数据分块：rss-data-0.js（首屏）/ rss-data-1.js（全量，后台合并）
    try:
        write_data_chunks(sources_with_items)
    except Exception as e:
        print("[数据分块] 写出失败: %s" % e, file=sys.stderr)

    # 生成 rss_sources.json（供 /api/rss 使用）；整体回写保留 timeout 等扩展字段
    for s in RSS_SOURCES:
        s.setdefault("tier", 3)
    _atomic_write_json("rss_sources.json", RSS_SOURCES, ensure_ascii=False, separators=(",", ":"))

    _snapshot_items = sum(len(s.get("items", [])) for s in sources_with_items)
    print("[RSS聚合] 生成完成 → %s（%d 源成功，抓取 %d 篇，快照 %d 篇）" % (OUT, ok_count, _items_fetched, _snapshot_items))

    # 打印翻译统计
    print("[翻译统计] 缓存命中: %d, Agnes: %d, Zen: %d, Google: %d, MyMemory: %d, Dict: %d, 跳过: %d, 失败: %d" % (
        _TRANS_STATS["cache_hit"], _TRANS_STATS["agnes"], _TRANS_STATS["zen"], _TRANS_STATS["google"], _TRANS_STATS["mymemory"],
        _TRANS_STATS["dict"], _TRANS_STATS["skip"], _TRANS_STATS["fail"]
    ))

    # 保存缓存
    _save_caches()
    _save_history()

    # ── 写入构建日志 ──
    _build_duration = round(time.time() - _build_start, 1)
    build_logger.append({
        "type": "build",
        "mode": mode,
        "duration_s": _build_duration,
        "sources_total": len(RSS_SOURCES),
        "sources_fetched": ok_count,
        "sources_with_data": _sources_with_data_before,
        "sources_skipped": skipped_count,
        "sources_failed": failed_count,
        "items_fetched": _items_fetched,
        "items_snapshot": _snapshot_items,
        "history_before": _history_before,
        "history_after": _history_after,
        "history_expired": _history_before - _history_after,
        "trans_cache_hit": _TRANS_STATS.get("cache_hit", 0),
        "trans_google": _TRANS_STATS.get("google", 0),
        "trans_mymemory": _TRANS_STATS.get("mymemory", 0),
        "trans_dict": _TRANS_STATS.get("dict", 0),
        "trans_skip": _TRANS_STATS.get("skip", 0),
        "trans_fail": _TRANS_STATS.get("fail", 0),
        "per_source": _source_log,
    })
    print("[日志] 构建日志已写入 build_logs/")

    return True


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    ok = main(mode=mode)
    sys.exit(0 if ok else 1)
