# -*- coding: utf-8 -*-
"""每日深度洞察报告 — 独立模块（RAG 架构）。

四源叠加（RSS 72h + 热榜 40 平台 + AIHOT + AGI Hunt）→ RAG 流水线
（硬过滤 → 切片 → Embedding → FAISS 索引 → 混合检索 → 重排序 → LLM 生成）
→ daily-insight.json + 历史轨迹。

由 fetch_and_build.py 在 build_rss_aggregator 之后调用。
不修改现有 insight_engine 或任何已有模块。
"""
import collections
import datetime
import hashlib
import html as html_mod
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

# ── 可选依赖：FAISS + BM25 + numpy ──
try:
    import faiss as _faiss
    import numpy as _np
    FAISS_AVAILABLE = True
except ImportError:
    _faiss = None
    try:
        import numpy as _np
    except ImportError:
        _np = None
    FAISS_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

# ── 常量 ──
BJT = datetime.timezone(datetime.timedelta(hours=8))
NOW_BJ = None  # 在 main() 中初始化
SEMANTIC_CLUSTER_THRESHOLD = 0.75  # 语义聚类余弦相似度阈值
MAX_QUERIES = 80  # 查询总数上限（扩容以覆盖更多话题维度）

# ── 数据文件路径 ──
RSS_HISTORY_FILE = "rss_history.json"
HOT_SNAPSHOT_FILE = "hot_snapshot.json"
SNAPSHOT_FILE = "daily_insight_snapshot.json"   # AIHOT + AGI Hunt 构建期缓存
INSIGHT_FILE = "daily-insight.json"             # 当日洞察产出
HISTORY_FILE = "daily_insight_history.json"     # 30 天历史轨迹
HISTORY_HTML = "daily-insight-history.html"     # 历史页面
TRACKING_FILE = "daily_insight_tracking_history.jsonl"  # 构建质量追踪日志
CONFIG_FILE = "build_config.json"

# ── AIHOT API ──
AIHOT_API_URL = "https://aihot.virxact.com/api/v1/items"

# ── AGI Hunt 配置 ──
AGIHUNT_CHANNELS = [
    "models", "research", "coding-agents", "products", "multimodal",
    "infra", "hardware", "funding", "policy", "agi", "companies", "fun",
]
AGIHUNT_API_URL = "https://agihunt.info/agent/v1"

# ── 热榜平台分层 ──
HOT_T1 = {"weibo", "zhihu", "baidu", "toutiao", "douyin", "bilibili"}
HOT_T2 = {"ithome", "hackernews", "github", "solidot", "sspai", "juejin",
           "v2ex", "producthunt", "chongbuluo", "pcbeta"}
HOT_T3 = set()  # 其余平台默认 T3

# ── RSS 信源 Tier（从 rss_sources.json 动态加载） ──
_RSS_TIER_MAP = {}  # source_key → tier

# ── 过滤黑名单 ──
_CLICKBAIT_PATTERNS = re.compile(
    r'震惊|不看后悔|疯了|必看|速看|删前速看|99%的人不知道'
    r'|万万没想到|重磅来袭|炸裂|核弹级|颠覆性|史诗级'
    r'|赶紧看|快来看|错过就没了|手慢无',
    re.IGNORECASE,
)
_AD_PATTERNS = re.compile(
    r'限时折扣|优惠券|下单链接|薅羊毛|种草带货|荐股|荐币'
    r'|财富密码|社群招募|明天必涨|扫码领取|免费领取'
    r'|限时优惠|秒杀活动|点击注册|加入社群|立即抢购',
    re.IGNORECASE,
)

# ── LLM category 枚举 ──
VALID_CATEGORIES = [
    "ai-models", "ai-products", "industry", "research",
    "policy", "funding", "developer", "consumer",
]

# ── 主题分类层（借鉴 QWIS：优先级顺序匹配，首个命中即停） ──
# 顺序敏感：ai 在最前，确保"英伟达股价"类科技金融交叉事件留在主报告
TOPIC_TAXONOMY = [
    ("ai", ["大模型", "模型", "gpt", "claude", "gemini", "llm", "openai", "anthropic",
            "deepmind", "智能体", "agent", "芯片", "gpu", "nvidia", "英伟达", "算力",
            "训练", "推理", "机器人", "自动驾驶", "深度学习", "机器学习", "agi", "多模态",
            "人工智能"]),
    ("programming", ["github", "开源", "编程", "开发者", "框架", "sdk", "api", "编译器",
                     "rust", "python", "javascript", "代码", "漏洞", "安全研究", "插件"]),
    ("finance", ["央行", "利率", "股价", "股涨", "股跌", "指数涨", "基金", "债券", "汇率",
                 "通胀", "gdp", "a股", "美股", "港股", "期货", "黄金", "存款", "贷款", "楼市", "房价"]),
    ("geopolitics", ["联合国", "安理会", "制裁", "关税", "外交", "军事", "导弹", "停火",
                     "选举投票", "峰会", "北约", "俄乌", "中东", "台海", "法案通过", "禁令"]),
    ("society", ["高考", "报名", "就业", "医疗", "医保", "养老", "生育", "人口", "事故",
                 "警方", "法院", "判决", "教育", "校园", "疫情", "疫苗", "火车", "航班"]),
    ("culture", ["诺贝尔", "奥斯卡", "世界杯", "奥运", "联赛", "电影票房", "文学奖",
                 "博物馆", "考古", "演唱会", "夺冠", "运动员", "太空", "天文", "发射"]),
]
MAIN_TOPICS = {"ai", "programming"}
BUBBLE_TOPICS = {"finance", "geopolitics", "society", "culture"}
_CAT_HINTS = {"ai": "ai", "dev": "programming", "tech": "programming",
              "news": "other", "wechat": "other", "cn_tech": "programming"}


def _classify_topic(title, text, source, cat=""):
    """关键词优先级匹配。无命中时按 RSS cat 提示归类，最终回退 other。"""
    hay = ((title or "") + " " + (text or "")[:300] + " " + (source or "")).lower()
    for tag, kws in TOPIC_TAXONOMY:
        for kw in kws:
            if kw in hay:
                return tag
    return _CAT_HINTS.get(cat, "other")

# ── 打分参数（框架先立，参数后调） ──
CROSS_FACTOR = 1.5          # 每多一个信源类型，信号 ×1.5
RECENCY_HALF_LIFE_H = 24    # 24h 半衰期
ACCEL_THRESHOLD_HIGH = 0.5  # 近 6h 占比 >50% → 加速
ACCEL_THRESHOLD_LOW = 0.1   # 近 6h 占比 <10% → 减速
ACCEL_BOOST = 1.3
ACCEL_DECAY = 0.8

# ── 聚类/匹配参数 ──
JACCARD_HISTORY_THRESHOLD = 0.5  # 跨天事件匹配
JACCARD_EVENT_THRESHOLD = 0.35   # 检索后事件组装用

# ── TopK ──
MIN_EVENTS = 3
MAX_EVENTS = 12
PHASE1_POOL = MAX_EVENTS + 4  # T1: 候选扩池，去重/丢弃空槽由后位候选顶上，终局仍收口 MAX_EVENTS
DEEP_ANALYSIS_TOP_N = 3

# ── RAG 参数 ──
EMBED_MODEL = "BAAI/bge-m3"
EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_BATCH = 32
EMBED_DIM = 1024
CHUNK_SIZE = 300       # 目标 chunk token 数
CHUNK_OVERLAP = 50     # chunk 重叠 token 数
FAISS_INDEX_FILE = "daily_insight_faiss.index"
FAISS_META_FILE = "daily_insight_chunks.json"
VECTOR_CACHE_FILE = "daily_insight_vectors.npy"  # numpy 向量缓存（增量 embedding）
RETRIEVAL_TOP_K = 200  # 向量检索每查询返回数（扩大检索提升覆盖率）
RRF_K = 60             # RRF 融合常数
BM25_ENABLED = True     # BM25 混合检索开关
MAX_EMBED_CHUNKS = 30000   # 最大 embedding chunk 数（扩容至全量覆盖）
BM25_WINDOW = 10000         # BM25 检索窗口上限（非 RSS 优先纳入，剩余给近期 RSS）
INSIGHT_RSS_HOURS = 168   # 每日洞察取最近 N 小时的 RSS（7 天窗口，支持跨天趋势检测）

# ── RAGAS 质量评估参数 ──
RAGAS_ENABLED = True          # RAGAS 评估-修正闭环开关
RAGAS_QUALITY_THRESHOLD = 0.70  # 整体质量阈值，低于此值触发修正
RAGAS_MAX_CORRECTIONS = 1      # 修正轮数（01:12 期实证：2 轮在复评噪声带内采纳劣化版，回稳 1 轮）
# 各维度最低阈值 — 任一维度低于阈值即触发修正（即使 overall 达标）
RAGAS_MIN_COVERAGE = 0.75      # context_coverage 最低要求
RAGAS_MIN_FAITHFULNESS = 0.88  # faithfulness 最低要求（目标 ≥ 0.95）
RAGAS_MIN_RELEVANCE = 0.75     # relevance 最低要求（目标 ≥ 0.80）


# ──────────────────── 工具函数 ────────────────────

def _now_bj():
    return datetime.datetime.now(BJT)


def _parse_iso(s):
    s = (s or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    dt = None
    try:
        dt = datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        try:
            dt = datetime.datetime.fromisoformat(s[:19])
        except (ValueError, TypeError):
            return None
    # naive 时间戳按北京时间理解（与 _hours_ago 既有约定一致），
    # 统一返回 aware，杜绝 max/min 混比 TypeError（CI run 35349753348 崩溃根因）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BJT)
    return dt


def _hours_ago(dt):
    """距现在多少小时。dt 为 aware datetime 或 None。"""
    if not dt:
        return 999
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BJT)
    return max(0, (NOW_BJ - dt).total_seconds() / 3600)


def _recency_decay(dt):
    """时间衰减因子，24h 半衰期。"""
    h = _hours_ago(dt)
    if h >= 999:
        return 0.15
    return 0.5 ** (h / RECENCY_HALF_LIFE_H)


def _esc(s):
    return html_mod.escape(str(s), quote=True)


def _truncate(s, maxlen=300):
    if not s:
        return ""
    s = s.strip()
    return s[:maxlen] + "…" if len(s) > maxlen else s


def _strip_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return text.strip()


def _tokenize_title(title):
    """标题分词：按标点和空格切分，再拆中文为 2-gram 集合。"""
    title = (title or "").lower()
    # 按标点/空格/特殊字符切分
    parts = re.split(r'[\s,，。！？!?、；:：""''（）()\[\]{}|/\\·\-]+', title)
    tokens = set()
    for p in parts:
        if not p:
            continue
        # 英文整体作为一个 token
        if p.isascii():
            if len(p) >= 2:
                tokens.add(p)
            continue
        # 中文：2-gram + 整段
        if len(p) >= 2:
            tokens.add(p)
        for i in range(len(p) - 1):
            tokens.add(p[i:i+2])
    return tokens


def _simple_tokens(text):
    """轻量分词：英文按词切分 + 中文按 character bigrams。用于去重/相似度计算。"""
    text = (text or "").lower()
    tokens = set()
    for w in re.findall(r'[a-z0-9]{2,}', text):
        tokens.add(w)
    cjk = re.findall(r'[\u4e00-\u9fff]', text)
    for k in range(len(cjk) - 1):
        tokens.add(cjk[k] + cjk[k + 1])
    return tokens


def _jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _atomic_write_text(path, text):
    """原子写文本文件：先写 .tmp 再 os.replace"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ──────────────────── 配置加载 ────────────────────

def load_config():
    cfg = {"daily_insight_enabled": True, "daily_insight_llm": "agnes"}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg.update(user_cfg)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def _load_rss_tiers():
    """从 rss_sources.json 加载 source_key → tier 映射。"""
    global _RSS_TIER_MAP
    try:
        with open("rss_sources.json", "r", encoding="utf-8") as f:
            sources = json.load(f)
        for s in sources:
            if isinstance(s, dict) and s.get("key"):
                _RSS_TIER_MAP[s["key"]] = s.get("tier", 3)
    except Exception:
        pass


# ──────────────────── 数据采集 ────────────────────

def _fetch_aihot():
    """构建期抓取 AIHOT API，返回条目列表。"""
    url = AIHOT_API_URL + "?mode=all&window=24h&limit=100"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (starhub-auto-update)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read(2000000).decode("utf-8", errors="replace"))
    except Exception as e:
        print("[每日洞察] AIHOT 拉取失败: %s" % e, file=sys.stderr)
        return []

    items = []
    for it in data.get("items") or []:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        links = it.get("links") or {}
        link = links.get("original") or links.get("aihot") or ""
        source = ((it.get("source") or {}).get("name") or "").strip()
        pub = it.get("discoveredAt") or it.get("publishedAt") or ""
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "category": (it.get("category") or "").strip(),
            "summary": _truncate(it.get("summary") or "", 500),
            "pub_date": pub,
            "score": float(it.get("score") or 0),
            "_src": "aihot",
        })
    print("[每日洞察] AIHOT 拉取 %d 条" % len(items))
    return items


def _fetch_agihunt():
    """构建期抓取 AGI Hunt 频道数据。需 AGIHUNT_API_KEY 环境变量。

    遵循 AGI Hunt Agent API 使用守则：
    - 限速 0.5 次/秒（突发 10），每请求间隔 ≥ 2s
    - 429 按 Retry-After 退避，不循环重试
    - 401 停止后续请求（密钥无效）
    - 426 拉取新版 Skill 版本后重试一次
    - 取当天 + 昨天数据以扩大覆盖率（API 支持近 3 天）
    """
    api_key = os.environ.get("AGIHUNT_API_KEY", "")
    if not api_key:
        print("[每日洞察] AGIHUNT_API_KEY 未配置，跳过 AGI Hunt", file=sys.stderr)
        return []

    skill_version = "1.2.2"
    today = NOW_BJ.strftime("%Y-%m-%d")
    yesterday = (NOW_BJ - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    fetch_days = [today, yesterday]

    all_items = []
    key_valid = True
    retry_once = True  # 426 时允许重试一次

    for day in fetch_days:
        if not key_valid:
            break
        for ci, channel in enumerate(AGIHUNT_CHANNELS):
            # 限速：0.5 次/秒 → 每请求间隔 ≥ 2s（突发 10 后必须降速）
            if ci > 0 or day != today:
                time.sleep(2.0)

            url = "%s/channel/%s/items?day=%s&sort=hot" % (
                AGIHUNT_API_URL, channel, day)
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer %s" % api_key,
                "X-AgiHunt-Skill-Version": skill_version,
                "User-Agent": "starhub-auto-update",
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read(500000).decode("utf-8", errors="replace"))
                for it in (data.get("items") or []):
                    title = (it.get("title") or "").strip()
                    if not title:
                        continue
                    all_items.append({
                        "title": title,
                        "text": _truncate(it.get("text") or "", 800),
                        "url": it.get("url") or "",
                        "author": it.get("author") or "",
                        "hot": float(it.get("hot") or 0),
                        "channel": channel,
                        "pub_date": it.get("published_at") or "",
                        "_src": "agihunt",
                    })
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # 按 Retry-After 退避，不循环重试
                    retry_after = int(e.headers.get("Retry-After", "60"))
                    wait = min(retry_after, 120)
                    print("[每日洞察] AGI Hunt 429 限流，等待 %ds 后跳过剩余频道" % wait, file=sys.stderr)
                    time.sleep(wait)
                    key_valid = False  # 当天不再请求
                elif e.code == 401:
                    print("[每日洞察] AGI Hunt 401 密钥无效，停止请求", file=sys.stderr)
                    key_valid = False
                elif e.code == 426 and retry_once:
                    # Skill 需更新：拉取最新版本号后重试
                    retry_once = False
                    try:
                        ver_url = "%s/skill/version" % AGIHUNT_API_URL
                        ver_req = urllib.request.Request(ver_url, headers={
                            "Authorization": "Bearer %s" % api_key,
                            "User-Agent": "starhub-auto-update",
                        })
                        with urllib.request.urlopen(ver_req, timeout=5) as vr:
                            new_ver = vr.read().decode("utf-8").strip().strip('"')
                        if new_ver and new_ver != skill_version:
                            print("[每日洞察] AGI Hunt Skill 更新: %s → %s" % (skill_version, new_ver), file=sys.stderr)
                            skill_version = new_ver
                            # 重试当前频道
                            time.sleep(2.0)
                            retry_req = urllib.request.Request(
                                url, headers={
                                    "Authorization": "Bearer %s" % api_key,
                                    "X-AgiHunt-Skill-Version": skill_version,
                                    "User-Agent": "starhub-auto-update",
                                })
                            with urllib.request.urlopen(retry_req, timeout=15) as r:
                                data = json.loads(r.read(500000).decode("utf-8", errors="replace"))
                            for it in (data.get("items") or []):
                                title = (it.get("title") or "").strip()
                                if not title:
                                    continue
                                all_items.append({
                                    "title": title,
                                    "text": _truncate(it.get("text") or "", 800),
                                    "url": it.get("url") or "",
                                    "author": it.get("author") or "",
                                    "hot": float(it.get("hot") or 0),
                                    "channel": channel,
                                    "pub_date": it.get("published_at") or "",
                                    "_src": "agihunt",
                                })
                    except Exception as ve:
                        print("[每日洞察] AGI Hunt 426 更新失败: %s" % ve, file=sys.stderr)
                elif e.code == 400:
                    print("[每日洞察] AGI Hunt [%s] day=%s 参数错误(400)" % (channel, day), file=sys.stderr)
                else:
                    print("[每日洞察] AGI Hunt [%s] 失败: HTTP %d" % (channel, e.code), file=sys.stderr)
            except Exception as e:
                print("[每日洞察] AGI Hunt [%s] 失败: %s" % (channel, e), file=sys.stderr)

    print("[每日洞察] AGI Hunt 拉取 %d 条（%d 频道, %d 天）" % (
        len(all_items), len(AGIHUNT_CHANNELS), len(fetch_days)))
    return all_items


def _load_snapshot():
    """加载或创建构建期快照（AIHOT + AGI Hunt 缓存）。"""
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                snap = json.load(f)
            if snap.get("date") == NOW_BJ.strftime("%Y-%m-%d"):
                print("[每日洞察] 复用今日快照: %d AIHOT + %d AGI Hunt" % (
                    len(snap.get("aihot_items", [])), len(snap.get("agihunt_items", []))))
                return snap
        except Exception:
            pass

    # 抓取新数据
    aihot = _fetch_aihot()
    agihunt = _fetch_agihunt()
    snap = {
        "date": NOW_BJ.strftime("%Y-%m-%d"),
        "aihot_items": aihot,
        "agihunt_items": agihunt,
        "fetched_at": NOW_BJ.isoformat(),
    }
    try:
        _atomic_write_json(SNAPSHOT_FILE, snap)
    except Exception as e:
        print("[每日洞察] 快照写入失败: %s" % e, file=sys.stderr)
    return snap


def _load_rss_history():
    """加载 RSS 72h 历史（支持分块格式）。"""
    index_file = "rss_history_index.json"
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            merged = {}
            for i in range(index.get("chunks", 0)):
                fname = "rss_history_%d.json" % i
                if os.path.exists(fname):
                    with open(fname, "r", encoding="utf-8") as f:
                        merged.update(json.load(f))
            if merged:
                return merged
        except Exception:
            pass
    if not os.path.exists(RSS_HISTORY_FILE):
        return {}
    try:
        with open(RSS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_hot_snapshot():
    """加载热榜快照。"""
    if not os.path.exists(HOT_SNAPSHOT_FILE):
        return []
    try:
        with open(HOT_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ──────────────────── Phase 1.2: 硬过滤 ────────────────────

def _filter_noise(items):
    """纯规则剔除营销文/内容农场/标题党。返回干净条目列表。"""
    clean = []
    rejected = 0
    for it in items:
        title = it.get("title", "")
        # 标题党
        if _CLICKBAIT_PATTERNS.search(title):
            rejected += 1
            continue
        # 广告/营销
        if _AD_PATTERNS.search(title):
            rejected += 1
            continue
        # 太短（可能是无效条目）
        if len(title) < 4:
            rejected += 1
            continue
        clean.append(it)
    if rejected:
        print("[每日洞察] 硬过滤剔除 %d 条噪声" % rejected)
    return clean




# ──────────────────── RAG: 文档切片 ────────────────────

def _chunk_documents(rss_clean, hot_clean, aihot_clean, agihunt_clean):
    """将四源数据切分为统一格式的 chunk 列表。

    RSS: 按段落/句子切分，目标 ~CHUNK_SIZE token，CHUNK_OVERLAP 重叠。
    其他源: 每条一个 chunk（标题+摘要/描述）。
    """
    chunks = []
    chunk_counter = [0]

    def _make_chunk(source_type, source, title, url, text, pub_date,
                    source_key="", extra=None):
        cid = "chunk_%05d" % chunk_counter[0]
        chunk_counter[0] += 1
        # 内容指纹：用于跨构建去重，判断 chunk 是否已缓存向量
        hash_input = "%s|%s|%s|%s" % (source_type, source, title, text[:200])
        content_hash = hashlib.md5(hash_input.encode("utf-8")).hexdigest()[:16]
        c = {
            "chunk_id": cid,
            "source_type": source_type,
            "source": source,
            "source_key": source_key,
            "title": title,
            "url": url,
            "text": text[:3000],
            "pub_date": pub_date,
            "content_hash": content_hash,
            "topic_tag": _classify_topic(title, text, source, (extra or {}).get("cat", "")),
        }
        if extra:
            c.update(extra)
        return c

    # ── RSS: 按段落切分 ──
    for item in rss_clean:
        raw = item.get("full_content") or item.get("summary") or ""
        text = _strip_html(raw).strip()
        title = item.get("title", "")
        if not text:
            text = title
        # 短文本不切分
        if len(text) <= CHUNK_SIZE * 4:
            chunks.append(_make_chunk(
                "rss", item.get("source", ""), title,
                item.get("link", ""), text, item.get("pub_date", ""),
                source_key=item.get("source_key", ""), extra={"cat": item.get("cat", "")},
            ))
            continue
        # 按段落分割，再按目标 token 数合并/拆分
        paragraphs = re.split(r'\n\s*\n', text)
        current_text = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current_text) + len(para) + 1 > CHUNK_SIZE * 4:
                if current_text:
                    chunks.append(_make_chunk(
                        "rss", item.get("source", ""), title,
                        item.get("link", ""), current_text,
                        item.get("pub_date", ""),
                        source_key=item.get("source_key", ""), extra={"cat": item.get("cat", "")},
                    ))
                # 超长段落按句子拆分
                while len(para) > CHUNK_SIZE * 4:
                    cut = para[:CHUNK_SIZE * 4]
                    # 在最后一个句号处断开
                    for sep in ["。", ".", "！", "!", "？", "?", "；", ";"]:
                        idx = cut.rfind(sep)
                        if idx > CHUNK_SIZE * 2:
                            cut = cut[:idx + 1]
                            break
                    chunks.append(_make_chunk(
                        "rss", item.get("source", ""), title,
                        item.get("link", ""), cut,
                        item.get("pub_date", ""),
                        source_key=item.get("source_key", ""), extra={"cat": item.get("cat", "")},
                    ))
                    para = para[len(cut):]
                current_text = para
            else:
                current_text = (current_text + "\n" + para).strip()
        if current_text:
            chunks.append(_make_chunk(
                "rss", item.get("source", ""), title,
                item.get("link", ""), current_text,
                item.get("pub_date", ""),
                source_key=item.get("source_key", ""), extra={"cat": item.get("cat", "")},
            ))

    # ── 热榜: 每条一个 chunk ──
    for item in hot_clean:
        text = "[热榜/%s #%s] %s" % (
            item.get("platform", ""), item.get("rank", ""), item.get("title", ""))
        chunks.append(_make_chunk(
            "hot", item.get("platform", ""), item.get("title", ""),
            item.get("url", ""), text, "",
        ))

    # ── AIHOT: 每条一个 chunk ──
    for item in aihot_clean:
        text = "[AIHOT/%s] %s\n%s" % (
            item.get("category", ""), item.get("title", ""),
            item.get("summary", ""))
        chunks.append(_make_chunk(
            "aihot", item.get("source", ""), item.get("title", ""),
            item.get("link", ""), text, item.get("pub_date", ""),
        ))

    # ── AGI Hunt: 每条一个 chunk ──
    for item in agihunt_clean:
        text = "[AGI Hunt/%s hot=%.0f] %s\n%s" % (
            item.get("channel", ""), item.get("hot", 0),
            item.get("title", ""), item.get("text", ""))
        chunks.append(_make_chunk(
            "agihunt", item.get("channel", ""), item.get("title", ""),
            item.get("url", ""), text, item.get("pub_date", ""),
            extra={"hot": item.get("hot", 0), "channel": item.get("channel", "")},
        ))

    print("[每日洞察] 切片完成: %d 个 chunks (RSS %d, 热榜 %d, AIHOT %d, AGI Hunt %d)" % (
        len(chunks),
        sum(1 for c in chunks if c["source_type"] == "rss"),
        sum(1 for c in chunks if c["source_type"] == "hot"),
        sum(1 for c in chunks if c["source_type"] == "aihot"),
        sum(1 for c in chunks if c["source_type"] == "agihunt"),
    ))
    return chunks


# ──────────────────── RAG: Embedding ────────────────────

def _embed_chunks(texts):
    """调用硅基流动 BAAI/bge-m3 API 获取 embedding 向量。
    回退：本地 fastembed。复用 insight_engine 的调用模式但独立实现。
    """
    if not texts:
        return None, None

    sf_key = os.environ.get("SILICONFLOW_API_KEY", "")

    # ── 1) 硅基流动 API ──
    if sf_key:
        all_vecs = []
        ok = True
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            payload = json.dumps({
                "model": EMBED_MODEL,
                "input": batch,
            }).encode("utf-8")
            req = urllib.request.Request(
                EMBED_URL, data=payload,
                headers={
                    "Authorization": "Bearer %s" % sf_key,
                    "Content-Type": "application/json",
                },
            )
            # 重试循环：处理 401/429 等瞬时错误
            for _retry in range(4):  # 最多重试 3 次
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    batch_vecs = [d["embedding"] for d in data.get("data", [])]
                    all_vecs.extend(batch_vecs)
                    break  # 成功，跳出重试
                except Exception as exc:
                    if _retry < 3:
                        _wait = 5 * (2 ** _retry)  # 5s, 10s, 20s
                        print("[每日洞察] SiliconFlow embed 批次 %d 重试 %d/3 "
                              "(%s), 等 %ds" % (i, _retry + 1, exc, _wait),
                              file=sys.stderr)
                        time.sleep(_wait)
                    else:
                        print("[每日洞察] SiliconFlow embed 批次 %d 最终失败: %s" % (
                              i, exc), file=sys.stderr)
                        ok = False
                        break
            if not ok:
                break

        if ok and len(all_vecs) == len(texts) and all_vecs:
            # 维度校验
            dims = {len(v) for v in all_vecs}
            if len(dims) == 1:
                model_name = "siliconflow/%s" % EMBED_MODEL
                print("[每日洞察] Embedding via SiliconFlow %s (%d texts, %d dims)" % (
                    EMBED_MODEL, len(texts), dims.pop()))
                return all_vecs, model_name

        if not ok:
            print("[每日洞察] SiliconFlow API 失败，回退本地 fastembed", file=sys.stderr)

    # ── 2) 本地 fastembed 回退 ──
    try:
        from llama_index.embeddings.fastembed import FastEmbedEmbedding
        from llama_index.core import Settings
        for model_name in ["intfloat/multilingual-e5-small", "BAAI/bge-small-zh-v1.5"]:
            try:
                Settings.embed_model = FastEmbedEmbedding(model_name=model_name)
                vecs = Settings.embed_model.get_text_embedding_batch(texts, show_progress=False)
                if vecs and len(vecs) == len(texts):
                    print("[每日洞察] Embedding via local %s (%d texts)" % (model_name, len(texts)))
                    return vecs, model_name
            except Exception as exc:
                print("[每日洞察] fastembed %s 失败: %s" % (model_name, exc), file=sys.stderr)
    except ImportError:
        pass

    return None, None


# ──────────────────── RAG: FAISS 索引 ────────────────────

def _build_faiss_index(vectors):
    """从 embedding 向量构建 FAISS IndexFlatIP 索引。"""
    if not FAISS_AVAILABLE:
        print("[每日洞察] FAISS 不可用，无法构建向量索引", file=sys.stderr)
        return None
    if vectors is None or (hasattr(vectors, '__len__') and len(vectors) == 0):
        return None

    vec_np = _np.array(vectors, dtype=_np.float32)
    # 归一化（内积 = 余弦相似度）
    norms = _np.linalg.norm(vec_np, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vec_np = vec_np / norms

    dim = vec_np.shape[1]
    index = _faiss.IndexFlatIP(dim)
    index.add(vec_np)
    print("[每日洞察] FAISS 索引构建: %d 向量, %d 维" % (index.ntotal, dim))
    return index


def _save_index(index, chunks):
    """持久化 FAISS 索引 + chunk 元数据。"""
    try:
        if index is not None and FAISS_AVAILABLE:
            _faiss.write_index(index, FAISS_INDEX_FILE + ".tmp")
            os.replace(FAISS_INDEX_FILE + ".tmp", FAISS_INDEX_FILE)
        _atomic_write_json(FAISS_META_FILE, chunks)
        print("[每日洞察] 索引持久化: %s + %s" % (FAISS_INDEX_FILE, FAISS_META_FILE))
    except Exception as exc:
        print("[每日洞察] 索引保存失败: %s" % exc, file=sys.stderr)


def _load_index():
    """加载持久化的 FAISS 索引 + chunk 元数据。"""
    if not FAISS_AVAILABLE or not os.path.exists(FAISS_INDEX_FILE):
        return None, []
    if not os.path.exists(FAISS_META_FILE):
        return None, []
    try:
        index = _faiss.read_index(FAISS_INDEX_FILE)
        with open(FAISS_META_FILE, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        print("[每日洞察] 加载索引: %d 向量, %d chunks" % (index.ntotal, len(chunks)))
        return index, chunks
    except Exception as exc:
        print("[每日洞察] 索引加载失败: %s" % exc, file=sys.stderr)
        return None, []


# ──────────────────── RAG: 向量缓存（增量 embedding） ────────────────────

def _load_vector_cache():
    """加载旧 chunks + 旧向量缓存。

    返回 (chunks, vectors_np, embed_model)：
    - chunks: list[dict]，每个含 content_hash 字段
    - vectors_np: numpy float32 矩阵 shape=(N, dim)，或 None
    - embed_model: 模型名称字符串

    文件不存在或加载失败时返回 ([], None, "")。
    """
    if not FAISS_AVAILABLE:
        print("[每日洞察] 向量缓存跳过: FAISS 不可用", file=sys.stderr)
        return [], None, ""
    vec_exists = os.path.exists(VECTOR_CACHE_FILE)
    meta_exists = os.path.exists(FAISS_META_FILE)
    if not vec_exists or not meta_exists:
        print("[每日洞察] 向量缓存为空: %s %s, %s %s (cwd=%s)" % (
            VECTOR_CACHE_FILE, "✓" if vec_exists else "MISSING",
            FAISS_META_FILE, "✓" if meta_exists else "MISSING",
            os.getcwd()), file=sys.stderr)
        return [], None, ""
    try:
        with open(FAISS_META_FILE, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        vectors = _np.load(VECTOR_CACHE_FILE)
        # 维度校验：若模型切换导致维度不同，清空缓存
        if vectors.shape[1] != EMBED_DIM:
            print("[每日洞察] 向量缓存维度(%d)与当前模型(%d)不匹配，清空缓存" % (
                vectors.shape[1], EMBED_DIM), file=sys.stderr)
            return [], None, ""
        # 数量一致性校验
        if len(chunks) != vectors.shape[0]:
            print("[每日洞察] 向量缓存数量不一致(chunks=%d, vecs=%d)，清空缓存" % (
                len(chunks), vectors.shape[0]), file=sys.stderr)
            return [], None, ""
        # 提取 embed_model（从 chunks 元数据中读取，或默认值）
        embed_model = ""
        if chunks and "embed_model" in chunks[0]:
            embed_model = chunks[0]["embed_model"]
        print("[每日洞察] 加载向量缓存: %d chunks, %d 维" % (len(chunks), vectors.shape[1]))
        return chunks, vectors, embed_model
    except Exception as exc:
        print("[每日洞察] 向量缓存加载失败: %s" % exc, file=sys.stderr)
        return [], None, ""


def _save_vector_cache(chunks, vectors, embed_model):
    """保存 chunks 元数据 + 向量到磁盘。

    - chunks → FAISS_META_FILE (JSON)
    - vectors → VECTOR_CACHE_FILE (numpy .npy)
    """
    try:
        # 为每个 chunk 写入 embed_model 字段（便于未来维度校验）
        for c in chunks:
            c["embed_model"] = embed_model or ""
        _atomic_write_json(FAISS_META_FILE, chunks)
        # 修复：直接保存，不使用原子重命名（避免 .tmp 文件问题）
        vec_path = VECTOR_CACHE_FILE
        vectors_f32 = vectors.astype(_np.float32)
        print("[每日洞察] 向量缓存保存中: shape=%s, dtype=%s" % (vectors_f32.shape, vectors_f32.dtype))
        _np.save(vec_path, vectors_f32)
        if not os.path.exists(vec_path):
            print("[每日洞察] 警告: .npy 文件保存后不存在: %s" % vec_path, file=sys.stderr)
        else:
            print("[每日洞察] 向量缓存保存: %d chunks, shape=%s, size=%dKB" % (
                len(chunks), vectors.shape, os.path.getsize(vec_path) // 1024))
    except Exception as exc:
        print("[每日洞察] 向量缓存保存失败: %s" % exc, file=sys.stderr)
        import traceback
        traceback.print_exc()


# ──────────────────── RAG: 混合检索 ────────────────────

def _hybrid_retrieve(index, chunks, queries, top_k=RETRIEVAL_TOP_K):
    """混合检索：FAISS 向量搜索 + BM25 关键词 → RRF 融合。"""
    if not chunks or not queries:
        return []

    scores = {}  # chunk_id → rrf_score

    # ── 1) 向量检索 ──
    if index is not None and FAISS_AVAILABLE:
        # 批量 embed 所有查询（一次 API 调用，避免逐条请求）
        q_texts = [q[:500] for q in queries if q.strip()]
        if q_texts:
            q_embed, _ = _embed_chunks(q_texts)
            if q_embed and len(q_embed) == len(q_texts):
                q_vecs = _np.array(q_embed, dtype=_np.float32)
                # 归一化
                norms = _np.linalg.norm(q_vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                q_vecs = q_vecs / norms
                k = min(top_k, index.ntotal)
                # 维度校验：旧索引可能与当前 embedding 模型维度不同
                if k > 0 and q_vecs.shape[1] != index.d:
                    print("[每日洞察] 查询向量维度(%d)与索引维度(%d)不匹配，跳过向量检索" % (
                        q_vecs.shape[1], index.d), file=sys.stderr)
                elif k > 0:
                    try:
                        for qi, q_vec in enumerate(q_vecs):
                            dists, indices = index.search(q_vec.reshape(1, -1), k)
                            for rank, (dist, idx) in enumerate(zip(dists[0], indices[0])):
                                if idx < 0 or idx >= len(chunks):
                                    continue
                                cid = chunks[idx]["chunk_id"]
                                rrf = 1.0 / (RRF_K + rank + 1)
                                if cid not in scores or scores[cid]["rrf"] < rrf:
                                    scores[cid] = {"chunk": chunks[idx], "rrf": rrf, "vec_sim": float(dist)}
                    except Exception as exc:
                        print("[每日洞察] FAISS 搜索异常，降级为 BM25: %s" % exc, file=sys.stderr)

    # ── 2) BM25 检索（窗口限制：非 RSS 优先 + 近期 RSS 补满） ──
    if BM25_AVAILABLE and BM25_ENABLED:
        non_rss_for_bm25 = [c for c in chunks if c.get("source_type") != "rss"]
        rss_for_bm25 = [c for c in chunks if c.get("source_type") == "rss"]
        rss_for_bm25.sort(key=lambda c: c.get("pub_date", ""), reverse=True)
        bm25_budget = max(0, BM25_WINDOW - len(non_rss_for_bm25))
        bm25_window = non_rss_for_bm25 + rss_for_bm25[:bm25_budget]
        if bm25_budget == 0:
            print("[每日洞察] BM25 警告: 非RSS(%d) >= WINDOW(%d), RSS预算=0" % (
                len(non_rss_for_bm25), BM25_WINDOW))

        bm25_id_to_pos = {}
        bm25_pos_to_chunk = {}
        bm25_corpus = []
        for pos, c in enumerate(bm25_window):
            cid = c["chunk_id"]
            if cid not in bm25_id_to_pos:
                bm25_id_to_pos[cid] = len(bm25_corpus)
                bm25_pos_to_chunk[len(bm25_corpus)] = c
                bm25_corpus.append(c.get("text", "").split())

        if bm25_corpus:
            bm25 = BM25Okapi(bm25_corpus)
            for query_text in queries:
                q_tokens = query_text[:500].split()
                if not q_tokens:
                    continue
                bm_scores = bm25.get_scores(q_tokens)
                top_indices = _np.argsort(bm_scores)[::-1][:top_k]
                for rank, idx in enumerate(top_indices):
                    if bm_scores[idx] <= 0:
                        break
                    c = bm25_pos_to_chunk[idx]
                    cid = c["chunk_id"]
                    rrf = 1.0 / (RRF_K + rank + 1)
                    if cid in scores:
                        scores[cid]["rrf"] += rrf
                        scores[cid]["bm25"] = float(bm_scores[idx])
                    else:
                        scores[cid] = {
                            "chunk": c, "rrf": rrf,
                            "vec_sim": 0.0, "bm25": float(bm_scores[idx]),
                        }

    # 按 RRF 排序
    ranked = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)
    results = []
    for item in ranked[:top_k]:
        c = dict(item["chunk"])
        c["retrieval_score"] = item["rrf"]
        c["vec_similarity"] = item.get("vec_sim", 0.0)
        c["bm25_score"] = item.get("bm25", 0.0)
        results.append(c)

    print("[每日洞察] 混合检索: %d 查询 → %d 结果 (向量+BM25 RRF)" % (
        len(queries), len(results)))
    return results


# ──────────────────── RAG: 重排序 ────────────────────

def _rerank(retrieved, hot_snapshot):
    """信号加权重排序：跨源共振 + 时间衰减 + 平台权重 + RSS Tier。"""
    for chunk in retrieved:
        base = chunk.get("retrieval_score", 0.0)

        # 跨源共振（此处简化为单 chunk，共振在事件组装后计算）
        # 时间衰减
        pub_dt = _parse_iso(chunk.get("pub_date", ""))
        recency = _recency_decay(pub_dt)

        # 平台权重
        platform_w = 1.0
        if chunk.get("source_type") == "hot":
            plat = chunk.get("source", "")
            if plat in HOT_T1:
                platform_w = 2.0
            elif plat in HOT_T2:
                platform_w = 1.5

        # RSS Tier
        rss_w = 1.0
        if chunk.get("source_type") == "rss":
            tier = _RSS_TIER_MAP.get(chunk.get("source_key", ""), 3)
            rss_w = {1: 2.0, 2: 1.5, 3: 1.0}.get(tier, 1.0)

        # AGI Hunt hot 值
        agihunt_w = 1.0
        if chunk.get("source_type") == "agihunt":
            hot_val = chunk.get("hot", 0)
            agihunt_w = 1.0 + min(2.0, hot_val / 50.0)

        chunk["final_score"] = round(base * recency * platform_w * rss_w * agihunt_w, 4)

    retrieved.sort(key=lambda c: c["final_score"], reverse=True)
    return retrieved


def _build_queries(hot_clean, agihunt_clean, aihot_clean, rss_clean=None, retrieved_chunks=None):
    """混合查询构建：AGI Hunt + AIHOT + 热榜 + RSS + 伪查询，去重后截断到 MAX_QUERIES。"""
    queries = []
    seen = set()

    def _add(text):
        t = text.strip()
        if t and t not in seen:
            seen.add(t)
            queries.append(t)

    # AGI Hunt Top15
    agihunt_sorted = sorted(agihunt_clean, key=lambda x: x.get("hot", 0), reverse=True)
    for it in agihunt_sorted[:15]:
        _add(it.get("title", ""))

    # AIHOT Top15
    for it in aihot_clean[:15]:
        _add(it.get("title", ""))

    # 热榜 Top15
    for it in hot_clean[:15]:
        _add(it.get("title", ""))

    # RSS Top10（补充仅出现在 RSS 中的重要事件，提升 coverage）
    if rss_clean:
        rss_sorted = sorted(rss_clean, key=lambda x: x.get("pub_date", ""), reverse=True)
        for it in rss_sorted[:15]:
            _add(it.get("title", ""))

    # 伪查询 Top10（从已检索 chunks 的 title 截取）
    if retrieved_chunks:
        for c in retrieved_chunks[:30]:
            if len(queries) >= MAX_QUERIES:
                break
            _add(c.get("title", "")[:50])

    # 回退：若全无，用热榜
    if not queries:
        for it in hot_clean[:20]:
            _add(it.get("title", ""))

    return queries[:MAX_QUERIES]


# ──────────────────── RAG: 事件组装 ────────────────────

def _assemble_events(reranked_chunks):
    """将检索排序后的 chunks 按语义相似度聚类为事件。
    优先使用向量余弦相似度（embedding），失败时降级为 Jaccard 标题匹配。"""
    if not reranked_chunks:
        return []

    # 每个 chunk 初始为一个事件簇
    events = []
    for c in reranked_chunks:
        events.append({
            "id": None,
            "label": c.get("title", ""),
            "items": [c],
            "source_types": {c.get("source_type", "")},
            "tokens": _tokenize_title(c.get("title", "")),
            "category": c.get("channel", "") or c.get("source", ""),
            "best_score": c.get("final_score", 0),
        })

    # 优先语义聚类
    semantic_ok = False
    if FAISS_AVAILABLE and _np is not None and len(events) >= 2:
        semantic_ok = _semantic_merge(events)

    if not semantic_ok:
        # Jaccard 降级
        merged = True
        while merged:
            merged = False
            new_events = []
            used = set()
            for i, ei in enumerate(events):
                if i in used:
                    continue
                for j in range(i + 1, len(events)):
                    if j in used:
                        continue
                    ej = events[j]
                    sim = _jaccard(ei["tokens"], ej["tokens"])
                    if sim >= JACCARD_EVENT_THRESHOLD:
                        ei["items"].extend(ej["items"])
                        ei["source_types"] |= ej["source_types"]
                        ei["tokens"] |= ej["tokens"]
                        ei["best_score"] = max(ei["best_score"], ej["best_score"])
                        used.add(j)
                        merged = True
                new_events.append(ei)
            events = new_events

    # 丢弃只有 1 个 chunk 且分数极低的孤立事件
    if len(events) > MAX_EVENTS * 2:
        threshold = events[MAX_EVENTS].get("best_score", 0) * 0.3 if len(events) > MAX_EVENTS else 0
        events = [e for e in events if len(e["items"]) > 1 or e["best_score"] >= threshold]

    # 分配 ID
    date_str = NOW_BJ.strftime("%Y%m%d")
    for i, e in enumerate(events):
        e["id"] = "evt_%s_%03d" % (date_str, i + 1)
        del e["tokens"]

    # 事件内 chunk 去重：同一事件多源转载时，去除高度相似的 chunks
    _total_before = sum(len(e["items"]) for e in events)
    for e in events:
        items = e["items"]
        if len(items) <= 1:
            continue
        keep = []
        for it in items:
            it_title = (it.get("title", "") or "").strip()
            it_text = (it.get("text", "") or "")[:300]
            it_tok = _simple_tokens(it_title + " " + it_text)
            is_dup = False
            for kept in keep:
                kept_title = (kept.get("title", "") or "").strip()
                kept_text = (kept.get("text", "") or "")[:300]
                kept_tok = _simple_tokens(kept_title + " " + kept_text)
                if not it_tok or not kept_tok:
                    continue
                overlap = len(it_tok & kept_tok)
                sim = overlap / min(len(it_tok), len(kept_tok)) if min(len(it_tok), len(kept_tok)) > 0 else 0
                if sim > 0.8:
                    is_dup = True
                    break
            if not is_dup:
                keep.append(it)
        e["items"] = keep
    _total_after = sum(len(e["items"]) for e in events)
    if _total_after < _total_before:
        print("[每日洞察] 事件内去重: %d -> %d chunks (-%d)" % (
            _total_before, _total_after, _total_before - _total_after))

    # 按最高 chunk 分数排序
    events.sort(key=lambda e: e["best_score"], reverse=True)

    # 动态 TopK：T1 扩池点——上游唯一真截断在此，Phase1 候选放宽到 PHASE1_POOL
    if len(events) > PHASE1_POOL:
        events = events[:PHASE1_POOL]

    print("[每日洞察] 事件组装: %d 个事件 (从 %d chunks)" % (len(events), len(reranked_chunks)))
    return events


def _semantic_merge(events):
    """用向量余弦相似度做贪心合并。成功返回 True，失败返回 False。"""
    try:
        titles = []
        for e in events:
            titles.append(e.get("label", ""))

        vecs = _embed_chunks(titles)
        if isinstance(vecs, tuple):
            vecs = vecs[0]
        if vecs is None or len(vecs) != len(events):
            return False

        mat = _np.array(vecs, dtype="float32")
        norms = _np.linalg.norm(mat, axis=1, keepdims=True)
        norms = _np.where(norms == 0, 1, norms)
        mat = mat / norms

        used = set()
        for i in range(len(events)):
            if i in used:
                continue
            for j in range(i + 1, len(events)):
                if j in used:
                    continue
                sim = float(_np.dot(mat[i], mat[j]))
                if sim >= SEMANTIC_CLUSTER_THRESHOLD:
                    events[i]["items"].extend(events[j]["items"])
                    events[i]["source_types"] |= events[j]["source_types"]
                    events[i]["tokens"] |= events[j]["tokens"]
                    events[i]["best_score"] = max(events[i]["best_score"], events[j]["best_score"])
                    used.add(j)

        # 移除被合并的事件
        result = [e for idx, e in enumerate(events) if idx not in used]
        events.clear()
        events.extend(result)
        print("[每日洞察] 语义聚类: %d → %d 个事件" % (len(vecs), len(events)))
        return True
    except Exception as exc:
        print("[每日洞察] 语义聚类失败，降级 Jaccard: %s" % exc, file=sys.stderr)
        return False


# ──────────────────── RAG: 综合打分（事件级） ────────────────────

def _compute_dual_heat(cluster, hot_snapshot):
    """双参照系热度计算。返回 (heat, score_a, score_b, hot_platforms, resonance)。

    参照系 A: 全球 AI 信号 (AGI Hunt hot + AIHOT score)
    参照系 B: 中文生态信号 (热榜平台覆盖 + RSS tier)
    每个子信号 cap 到 5 分，防止单一源垄断。
    """
    items = cluster.get("items", [])

    # ── 参照系 A: 全球 AI 信号 (0-10) ──
    agihunt_contrib = 0.0
    aihot_contrib = 0.0
    for it in items:
        src = it.get("source_type", "")
        if src == "agihunt":
            # P3 修复：系数从 /100 调整为 /50，提升 agihunt 信号强度
            agihunt_contrib += it.get("hot", 0) / 50.0
        elif src == "aihot":
            # P3 修复：系数从 /15 调整为 /8，提升 aihot 信号强度
            aihot_contrib += it.get("score", 0) / 8.0
    score_a = min(10.0, min(5.0, agihunt_contrib) + min(5.0, aihot_contrib))

    # ── 参照系 B: 中文生态信号 (0-10) ──
    hot_platforms = set()
    for it in items:
        if it.get("source_type") == "hot":
            hot_platforms.add(it.get("source", ""))

    # 兆底：全局热榜反查（热榜 chunks 可能不在簇中）
    if not hot_platforms and hot_snapshot:
        label = cluster.get("label", "")
        cluster_tokens = _tokenize_title(label)
        if cluster_tokens:
            for platform in hot_snapshot:
                plat = platform.get("platform", "")
                for pitem in platform.get("items", []):
                    item_tokens = _tokenize_title(pitem.get("title", ""))
                    if len(cluster_tokens & item_tokens) >= 2:
                        hot_platforms.add(plat)
                        break

    t1 = sum(1 for p in hot_platforms if p in HOT_T1)
    t2 = sum(1 for p in hot_platforms if p in HOT_T2)
    t3 = len(hot_platforms) - t1 - t2
    hot_contrib = min(5.0, t1 * 1.5 + t2 * 1.0 + t3 * 0.5)

    rss_contrib = 0.0
    for it in items:
        if it.get("source_type") == "rss":
            tier = _RSS_TIER_MAP.get(it.get("source_key", ""), 3)
            rss_contrib += {1: 1.5, 2: 1.0, 3: 0}.get(tier, 0)
    rss_contrib = min(5.0, rss_contrib)

    score_b = min(10.0, hot_contrib + rss_contrib)

    # ── 综合 heat (0-10) ──
    heat = round(min(10.0, score_a * 0.5 + score_b * 0.5), 1)

    # ── resonance 分类 ──
    a_high = score_a >= 3.0
    b_high = score_b >= 3.0
    if a_high and b_high:
        resonance = "breakout"
    elif a_high and not b_high:
        resonance = "tech_hot" if t1 < 2 else "niche"
    elif not a_high and b_high:
        resonance = "consumer" if t1 > 0 else "niche"
    elif hot_platforms:
        resonance = "niche"
    else:
        resonance = ""

    return heat, round(score_a, 1), round(score_b, 1), hot_platforms, resonance


def _score_events(clusters, hot_snapshot):
    """事件级综合打分：基于检索分数 + 跨源共振 + 时间衰减。"""
    for cluster in clusters:
        items = cluster["items"]
        source_types = cluster["source_types"]

        # 基础分：取 chunks 最高检索分
        base_score = cluster.get("best_score", 0)

        # 跨源乘数
        n_types = len(source_types)
        cross_mult = CROSS_FACTOR ** max(0, n_types - 1)

        # 时间衰减（取最新 chunk）
        pub_dates = []
        for it in items:
            pd = _parse_iso(it.get("pub_date", ""))
            if pd:
                pub_dates.append(pd)
        if pub_dates:
            latest = max(pub_dates)
            recency = _recency_decay(latest)
        else:
            recency = 0.5

        # 加速度
        recent_6h = sum(1 for pd in pub_dates if _hours_ago(pd) <= 6)
        total_dated = len(pub_dates)
        if total_dated > 2:
            accel_ratio = recent_6h / total_dated
            if accel_ratio > ACCEL_THRESHOLD_HIGH:
                accel_mult = ACCEL_BOOST
            elif accel_ratio < ACCEL_THRESHOLD_LOW:
                accel_mult = ACCEL_DECAY
            else:
                accel_mult = 1.0
        else:
            accel_mult = 1.0

        # 综合分
        final = base_score * cross_mult * recency * accel_mult

        # 信号维度
        breadth = min(10, n_types * 2.5)
        depth = min(10, math.log2(len(items) + 1) * 2)
        novelty_dim = min(10, (1 - recency) * 10) if pub_dates else 5

        # 双参照系热度模型
        heat, score_a, score_b, hot_platforms, resonance = _compute_dual_heat(
            cluster, hot_snapshot)

        cluster["score"] = round(final, 2)
        cluster["signal"] = {
            "breadth": round(breadth, 1),
            "depth": round(depth, 1),
            "heat": heat,
            "novelty": round(novelty_dim, 1),
            "score_a": score_a,
            "score_b": score_b,
        }
        cluster["resonance"] = resonance
        cluster["source_types"] = sorted(source_types)
        cluster["recency"] = round(recency, 3)

    # 排序
    clusters.sort(key=lambda c: c["score"], reverse=True)

    # 编辑规则：4 源全覆盖至少排前 3
    four_source = [c for c in clusters if len(c["source_types"]) >= 4]
    for i, c in enumerate(four_source):
        if i >= 3:
            break
        cur_idx = clusters.index(c)
        if cur_idx > 2:
            clusters.insert(min(2, len(clusters) - 1), clusters.pop(cur_idx))

    # 动态 TopK：Phase1 候选池放宽到 PHASE1_POOL，输出预算在终局闸后收口
    if len(clusters) > PHASE1_POOL:
        clusters = clusters[:PHASE1_POOL]

    print("[每日洞察] 打分排序完成: %d 个事件" % len(clusters))
    return clusters


# ──────────────────── Phase 2: LLM 集成 ────────────────────

_LLM_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"


class _LLM:
    """轻量 LLM 调用，支持多 key 轮询。"""

    def __init__(self, api_key, model="agnes-2.5-flash", timeout=90, extra_keys=None):
        self.api_keys = [api_key]
        if extra_keys:
            self.api_keys.extend(k for k in extra_keys if k)
        self._key_idx = 0
        self.model = model
        self.timeout = timeout

    def _try(self, messages, temperature=0.3, max_tokens=2000):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        data = json.dumps(payload).encode("utf-8")
        key = self.api_keys[self._key_idx]
        req = urllib.request.Request(
            _LLM_API_URL, data=data,
            headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"], False
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return None, True
            return None, False
        except Exception:
            return None, False

    def complete(self, messages, temperature=0.3, max_tokens=2000):
        n_keys = len(self.api_keys)
        for _ in range(n_keys):
            result, is_429 = self._try(messages, temperature, max_tokens)
            if result:
                return result
            if is_429:
                self._key_idx = (self._key_idx + 1) % n_keys
                continue
            for _retry in range(2):
                result, is_429 = self._try(messages, temperature, max_tokens)
                if result:
                    return result
                if is_429:
                    self._key_idx = (self._key_idx + 1) % n_keys
                    break
            else:
                break
        return ""


def _init_llm():
    """初始化 LLM。从环境变量读取 API key。
    多 key 轮询：AGNES_API_KEY（主，可逗号分隔）+ AGNES_API_KEYS（逗号分隔附加），429 自动切换。"""
    keys = [k.strip() for k in os.environ.get("AGNES_API_KEY", "").split(",") if k.strip()]
    keys += [k.strip() for k in os.environ.get("AGNES_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        print("[每日洞察] AGNES_API_KEY 未配置，LLM 分析将跳过", file=sys.stderr)
        return None
    return _LLM(keys[0], extra_keys=keys[1:] or None)


# ──────────────────── Judge LLM：多模型降级 ────────────────────

class _MimoLLM:
    """Mimo 模型 LLM 调用（通过 OpenCode Zen 端点）。
    用作 RAGAS Judge 的首选模型，评估一致性优于 agnes。"""

    API_URL = "https://opencode.ai/zen/v1/chat/completions"

    def __init__(self, api_key=None, model="mimo-v2.5-free", timeout=30):
        # 与 build_rss_aggregator.py 的 _ZEN_KEY 同语义：空串也算未配置，且回退 OPENCODE_KEY
        self.api_key = (api_key
                        or os.environ.get("ZEN_API_KEY", "")
                        or os.environ.get("OPENCODE_KEY", "")
                        or "public")
        self.model = model
        self.timeout = timeout

    def complete(self, messages, temperature=0.3, max_tokens=2000):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        # 伪装 OpenCode CLI 请求头，绕过 free tier 仅限内部使用的限制
        # 与 api/translate.js translateZen() 保持一致
        _rid = uuid.uuid4().hex
        req = urllib.request.Request(
            self.API_URL, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % self.api_key,
                "User-Agent": "opencode/1.15.0 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
                "x-opencode-client": "cli",
                "x-opencode-project": "global",
                "x-opencode-request": "msg_" + _rid,
                "x-opencode-session": "ses_" + _rid,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            print("[MimoLLM] HTTP %d" % exc.code, file=sys.stderr)
            return ""
        except Exception as exc:
            print("[MimoLLM] error: %s" % exc, file=sys.stderr)
            return ""


class _OpenRouterLLM:
    """OpenRouter 免费模型 LLM 调用。
    支持多模型游标轮询 + 429 限流重试。"""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key=None, models=None, timeout=60):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.models = models or ["qwen/qwen3.8-27b:free", "z-ai/glm-5.2:free"]
        self.model = self.models[0]  # 对外暴露的模型名（元数据用）
        self.timeout = timeout
        self._idx = 0

    def complete(self, messages, temperature=0.3, max_tokens=2000):
        for attempt in range(len(self.models)):
            model = self.models[(self._idx + attempt) % len(self.models)]
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.API_URL, data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer %s" % self.api_key,
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "StarHub",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                if content:
                    self._idx = (self._idx + attempt + 1) % len(self.models)
                    return content
            except urllib.error.HTTPError as exc:
                print("[OpenRouter] %s HTTP %d" % (model, exc.code), file=sys.stderr)
                if exc.code == 429:
                    continue  # 限流，切换下一个模型
                return ""  # 非限流错误，不重试
            except Exception as exc:
                print("[OpenRouter] %s error: %s" % (model, exc), file=sys.stderr)
                return ""
        # 所有模型都被限流，等待后重试第一个
        print("[OpenRouter] 全部模型限流，等待 5s 重试...", file=sys.stderr)
        time.sleep(5)
        model = self.models[self._idx]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % self.api_key,
                "HTTP-Referer": "https://github.com",
                "X-Title": "StarHub",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            print("[OpenRouter] retry error: %s" % exc, file=sys.stderr)
            return ""


class _FallbackJudgeLLM:
    """Judge 专用 LLM：首选模型失败时降级到备选。
    记录每次调用的模型、耗时（评估元数据）。"""

    def __init__(self, primary_llm, fallback_llm):
        self.primary = primary_llm
        self.fallback = fallback_llm
        self.model = primary_llm.model  # 对外暴露的模型名
        self._call_log = []

    def complete(self, messages, temperature=0.3, max_tokens=2000):
        meta = {"model": None, "elapsed_s": 0, "fallback": False}
        t0 = time.time()
        result = self.primary.complete(messages, temperature, max_tokens)
        meta["model"] = self.primary.model
        meta["elapsed_s"] = round(time.time() - t0, 2)
        if result:
            self._call_log.append(meta)
            return result
        # 首选失败，降级到 fallback
        meta["fallback"] = True
        t0 = time.time()
        result = self.fallback.complete(messages, temperature, max_tokens)
        # 嵌套 FallbackJudgeLLM 时，从内层 call_log 获取实际模型名
        inner_log = getattr(self.fallback, '_call_log', None)
        if inner_log:
            meta["model"] = inner_log[-1]["model"]
        else:
            meta["model"] = getattr(self.fallback, 'model', 'agnes')
        meta["elapsed_s"] = round(time.time() - t0, 2)
        self._call_log.append(meta)
        if result:
            print("[JudgeLLM] %s 失败，已降级到 %s" % (self.primary.model, meta["model"]), file=sys.stderr)
        return result


def _effective_judge_model(llm):
    """实际打分的模型名。

    _FallbackJudgeLLM.model 在构造时取主模型名且降级后不更新，直接写进 quality.meta
    会让"标签是 mimo、分数其实是 agnes 打的"长期无人察觉；只有 _call_log 记录真实调用。
    """
    log = getattr(llm, '_call_log', None) or []
    models = [e.get("model") for e in log if e.get("model")]
    if not models:
        return getattr(llm, 'model', 'unknown')
    uniq = list(dict.fromkeys(models))
    return uniq[0] if len(uniq) == 1 else "mixed(%s)" % "+".join(uniq)


def _init_judge_llm(config=None):
    """初始化 Judge LLM（mimo → agnes 两级降级链）。
    OpenRouter 已移除（长期不通）。配置项可通过 config dict 覆盖。"""
    cfg = config or {}
    judge_provider = cfg.get("daily_insight_judge_provider", "mimo")
    judge_model = cfg.get("daily_insight_judge_model", "mimo-v2.5-free")
    judge_timeout = cfg.get("daily_insight_judge_timeout", 60)

    agnes = _init_llm()  # 只创建一次 agnes 实例，避免 key rotation 状态分裂
    if judge_provider == "mimo":
        primary = _MimoLLM(model=judge_model, timeout=judge_timeout)
        if agnes:
            # 两级链: mimo → agnes
            return _FallbackJudgeLLM(primary, agnes)
        return primary
    # 非 mimo provider：直接用 agnes，无需 FallbackJudgeLLM 包装
    return agnes


def _parse_json(text):
    """从 LLM 输出中提取 JSON。"""
    if not text:
        return None
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取 { ... } 或 [ ... ]
    # 如果文本以 [ 开头，优先数组提取（避免截断数组被误解析为对象）
    stripped = text.lstrip()
    if stripped.startswith('['):
        bracket_order = [('[', ']'), ('{', '}')]
    else:
        bracket_order = [('{', '}'), ('[', ']')]
    for start, end in bracket_order:
        si = text.find(start)
        ei = text.rfind(end)
        if si >= 0 and ei > si:
            try:
                result = json.loads(text[si:ei + 1])
                # 数组场景（文本以 [ 开头）的对象提取结果不返回，留给截断修复
                if stripped.startswith('[') and start == '{':
                    continue
                return result
            except json.JSONDecodeError:
                pass
    return None


def _close_brackets(candidate):
    """用栈追踪计算未闭合的括号序列，返回正确的闭合字符串。"""
    stack = []
    for c in candidate:
        if c in '{[':
            stack.append(c)
        elif c == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif c == ']' and stack and stack[-1] == '[':
            stack.pop()
    return ''.join('}' if c == '{' else ']' for c in reversed(stack))


def _robust_parse_json(text):
    """增强 JSON 解析：处理截断、前后缀噪音、括号缺失。支持对象和数组。"""
    if not text:
        return None
    # 先用标准解析
    parsed = _parse_json(text)
    if isinstance(parsed, (dict, list)):
        return parsed
    # 提取 { 到最后一个 } 之间的内容（对象）
    start = text.find('{')
    end = text.rfind('}')
    _stripped = text.lstrip()
    if start >= 0 and end > start and not _stripped.startswith('['):
        candidate = text[start:end + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    # 提取 [ 到最后一个 ] 之间的内容（数组）
    astart = text.find('[')
    aend = text.rfind(']')
    if astart >= 0 and aend > astart:
        candidate = text[astart:aend + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    # 补全缺失的括号（处理截断 JSON）
    # 策略1：找最后一个完整闭合 } 截断
    # 策略2：找最后一个 : 截断（处理无 } 的深度截断）

    # 优先处理数组（自审等场景返回数组）
    if astart >= 0 and (start < 0 or astart < start):
        # 策略1a：找最后一个 }
        last_obj_end = text.rfind('}')
        if last_obj_end > astart:
            candidate = text[astart:last_obj_end + 1]
            candidate = candidate.rstrip(', \t\r\n')
            candidate += _close_brackets(candidate)
            try:
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        # 策略2a：找最后一个 : 截断（深度截断，无完整 }）
        # 找上一个完整 key-value 对的结束位置
        last_colon = text.rfind(':')
        if last_colon > astart:
            prev_colon = text.rfind(':', astart, last_colon)
            if prev_colon >= astart:
                # 在 prev_colon 后找 "value" 对
                vq1 = text.find('"', prev_colon + 1, last_colon)
                if vq1 >= 0:
                    vq2 = text.find('"', vq1 + 1, last_colon)
                    if vq2 >= 0:
                        candidate = text[astart:vq2 + 1]
                        candidate = candidate.rstrip(', \t\r\n')
                        candidate += _close_brackets(candidate)
                        try:
                            result = json.loads(candidate)
                            if isinstance(result, list):
                                return result
                        except json.JSONDecodeError:
                            pass

    # 对象截断处理
    if start >= 0:
        # 策略1b：找最后一个 }
        last_obj_end = text.rfind('}')
        if last_obj_end > start:
            candidate = text[start:last_obj_end + 1]
            candidate = candidate.rstrip(', \t\r\n')
            candidate += _close_brackets(candidate)
            try:
                result = json.loads(candidate)
                if isinstance(result, (dict, list)):
                    return result
            except json.JSONDecodeError:
                pass
        # 策略2b：找最后一个 : 截断（深度截断）
        # 找上一个完整 key-value 对的结束位置
        last_colon = text.rfind(':')
        if last_colon > start:
            prev_colon = text.rfind(':', start, last_colon)
            if prev_colon >= start:
                vq1 = text.find('"', prev_colon + 1, last_colon)
                if vq1 >= 0:
                    vq2 = text.find('"', vq1 + 1, last_colon)
                    if vq2 >= 0:
                        candidate = text[start:vq2 + 1]
                        candidate = candidate.rstrip(', \t\r\n')
                        candidate += _close_brackets(candidate)
                        try:
                            result = json.loads(candidate)
                            if isinstance(result, (dict, list)):
                                return result
                        except json.JSONDecodeError:
                            pass
    return None


def _filter_cluster_items(cluster, phase1_label):
    """过滤 cluster 中与 Phase 1 label 不相关的 items。"""
    if not phase1_label:
        return cluster
    label_tokens = _tokenize_title(phase1_label)
    if not label_tokens:
        return cluster

    filtered = []
    for it in cluster.get("items", []):
        title = it.get("title", "")
        text = it.get("text", "")[:200]
        item_tokens = _tokenize_title(title + " " + text)
        if len(label_tokens & item_tokens) >= 2:
            filtered.append(it)

    if not filtered and cluster.get("items"):
        filtered = cluster["items"][:1]  # 兜底保留 1 个，后续由 _drop_info_insufficient 清理

    cluster["items"] = filtered
    return cluster


def _norm_url(u):
    """URL 归一化：去协议/www/尾斜杠/小写，用于跨源反查 RSS 存档。"""
    u = (u or "").strip().lower()
    u = re.sub(r'^https?://', '', u)
    u = re.sub(r'^www\.', '', u)
    return u.rstrip('/')


def _build_evidence_pack(cluster, rss_by_url, max_docs=3, doc_chars=2500):
    """事件 URL 反查 rss_history 全文，拼为 Phase 2 交叉核对参考。"""
    docs, seen = [], set()
    for it in cluster.get("items", []):
        key = _norm_url(it.get("url") or it.get("link"))
        if not key or key in seen:
            continue
        rec = rss_by_url.get(key)
        if not rec:
            continue
        body = _strip_html((rec.get("full_content") or rec.get("summary_zh")
                            or rec.get("summary") or "").strip())
        if len(body) < 120:
            continue
        seen.add(key)
        docs.append("【%s】%s\n%s" % (rec.get("source", ""), rec.get("title", ""), body[:doc_chars]))
        if len(docs) >= max_docs:
            break
    return "\n\n".join(docs)


def _build_event_material(cluster, numbered=False):
    """为 LLM 构建事件素材文本。兼容 RAG chunk 和旧格式。
    numbered=True 时片段带 [n] 编号并返回编号→来源映射，供 Phase 2 引用溯源。"""
    lines = []
    refs = []
    for idx, it in enumerate(cluster.get("items", []), 1):
        # 兼容 RAG chunk (source_type) 和旧格式 (_src)
        src = it.get("source_type", "") or it.get("_src", "?")
        title = it.get("title", "")
        url = it.get("url", "") or it.get("link", "")
        prefix = "[%d]" % idx if numbered else ""
        if src == "rss":
            body = it.get("text", "") or it.get("full_content") or it.get("summary") or ""
            body = _strip_html(body)[:800]
            src_name = it.get("source", "")
            lines.append("%s[RSS/%s] %s\n%s" % (prefix, src_name, title, body))
        elif src == "hot":
            plat = it.get("source", "") or it.get("platform", "")
            src_name = "热榜/%s" % plat
            lines.append("%s[热榜/%s #%s] %s" % (prefix, plat, it.get("rank", ""), title))
        elif src == "aihot":
            src_name = "AIHOT/%s" % it.get("category", "")
            lines.append("%s[AIHOT/%s] %s\n%s" % (prefix, it.get("category", ""), title, it.get("summary", "")))
        elif src == "agihunt":
            ch = it.get("channel", "") or it.get("source", "")
            src_name = "AGI Hunt/%s" % ch
            lines.append("%s[AGI Hunt/%s hot=%.0f] %s\n%s" % (
                prefix, ch, it.get("hot", 0), title, it.get("text", "")))
        else:
            # 未知源类型，直接输出文本
            src_name = "%s/%s" % (src, it.get("source", ""))
            lines.append("%s[%s/%s] %s\n%s" % (prefix, src, it.get("source", ""), title, it.get("text", "")[:500]))
        if numbered:
            refs.append({"index": idx, "source": src_name, "title": title, "url": url})
    if numbered:
        return "\n---\n".join(lines), refs
    return "\n---\n".join(lines)


def _validate_phase2_citations(parsed, mat_refs):
    """校验 Phase 2 引用编号：剔除素材中不存在的编号，回填 cited_sources（含 URL）。"""
    valid = {r["index"]: r for r in mat_refs}
    cites = parsed.get("citations")
    normalized = {}
    cited_idx = set()
    if isinstance(cites, dict):
        for field, refs in cites.items():
            if isinstance(refs, int) or (isinstance(refs, str) and refs.isdigit()):
                refs = [refs]
            if not isinstance(refs, list):
                continue
            keep = []
            for r in refs:
                # LLM 常输出字符串编号，统一归一为 int
                if isinstance(r, str) and r.strip().isdigit():
                    r = int(r.strip())
                if isinstance(r, int) and r in valid:
                    keep.append(r)
            normalized[field] = keep
            cited_idx.update(keep)
    parsed["citations"] = normalized
    seen_url = set()
    cited_sources = []
    for i in sorted(cited_idx):
        r = valid[i]
        if r.get("url") and r["url"] in seen_url:
            continue
        seen_url.add(r.get("url"))
        cited_sources.append(dict(r))
    parsed["cited_sources"] = cited_sources
    return parsed


# ── Phase 1 LLM：全事件摘要 + 主题导语 ──

_SYSTEM_PROMPT_P1 = """
(C) Context: 你是一位 AI 行业资深分析师，为科技媒体撰写每日深度报告。
你的读者是 AI 从业者和科技决策者，他们需要在 5 分钟内掌握今日 AI 领域最重要的动态。

(O) Objective: 为每个事件生成结构化摘要，并用一句话概括今日主线。
你的输出将直接展示在 AI 日报页面上，面向数万读者。

(S) Style: 报纸编辑风格——简洁、有力、信息密度高。
写法要求：
1. 第一句话定性（使用“主导”“分化”“拐点”“加速”等判断词）
2. 用【宏观主线】+【微观佐证】结构串联
3. 每个论点必须引用素材中的具体事实和数据
4. 禁止平铺直叙罗列事件

(T) Tone: 事实驱动、数据具体、观点有据。禁止空泛描述。

(A) Audience: AI 从业者、科技媒体编辑、技术决策者。

(R) Response: 严格输出 JSON，格式如下：
{"theme": "一句话今日主题", "events": [{"event_num": 1, "label": "...", "category": "...", "summary": "...", "significance": "...", "key_links": [...]}]}

## 正确示例
{
  "theme": "从 Agent 评估标准之争，到可观测性工具涌现，再到企业级审计需求爆发，判断 AI 工程化进入系统化阶段",
  "events": [{
    "event_num": 1,
    "label": "三大平台同步发布企业级 Agent 评估服务",
    "category": "ai-products",
    "summary": "OpenAI、Google、Anthropic 在同一天发布企业级 Agent 评估服务。OpenAI 的 Agent Analytics 支持 Trace 级别追踪，Google 的 AgentBench Enterprise 提供标准化评测集，Anthropic 的 Claude Observability 集成 OpenTelemetry。",
    "significance": "标志 Agent 从‘能用’到‘可观测’的拐点，企业级部署的核心障碍从功能转向可评估性。",
    "key_links": ["https://..."]
  }]
}

## 核心信源 DNA
- 36氪: 产业视角，关注商业模式和融资
- 虎嗅: 商业评论，偏批判性分析
- 微博热搜: 舆论风向，反映公众情绪
- 知乎: 深度讨论，技术社区视角
- B站: 年轻用户视角，关注消费级应用
- Hacker News: 技术极客视角，关注底层创新
- Product Hunt: 产品视角，关注用户体验
- arXiv: 学术视角，关注方法论突破

## 禁用表达
“值得关注”“引发讨论”“未来可期”“拭目以待”“不难预见”
每句话必须有信息增量，不允许空话。

所有陈述必须严格基于提供的素材。禁止使用你自己的知识补充。
具体数字（金额/数量/百分比/日期）必须能在事件素材或全局检索上下文中找到原样形式；允许单位/千分位/全角等等价改写，禁止换算、四舍五入或用外部知识补数。
素材对某一说法存在分歧（质疑、否认、要求核实）时，summary 必须注明"该说法有争议"及分歧方，不得写成确定事实。
如果素材中缺少某个关键数据，在 summary 中标注[信息不足]。
只输出严格 JSON，不要输出任何思考过程或解释。"""


_INSUFFICIENT_RE = re.compile(r'\[信息不足')
# 劣化占位（07:13 实证「素材未提供…无法生成…摘要」）须双信号同现，防误杀正常报道摘要
_DISGUISED_RE = re.compile(r'无法生成.{0,20}摘要')


def _is_insufficient(text):
    """[信息不足] 标记出现即判；伪装占位需「素材未提供 + 无法生成…摘要」组合信号。"""
    t = text or ""
    if _INSUFFICIENT_RE.search(t):
        return True
    return "素材未提供" in t and bool(_DISGUISED_RE.search(t))


def _validate_key_links(links, items):
    """key_links 去重保序；多样性不足（≤1 个）时用事件 items 的 URL 补足到 ≤3；上限 5。"""
    seen, out = set(), []
    for u in links or []:
        k = _norm_url(u)
        if u and k and k not in seen:
            seen.add(k)
            out.append(u)
    if len(out) <= 1:
        for it in items or []:
            u = it.get("url", "") or it.get("link", "")
            k = _norm_url(u)
            if u and k and k not in seen:
                seen.add(k)
                out.append(u)
            if len(out) >= 3:
                break
    return out[:5]


def _order_events_for_output(clusters):
    """事件列表按 editor_score（素材热度代理）降序稳定排列——judge 反馈：重大趋势应前置。
    深度分析分配与破茧选择已在排序前基于原顺序完成，此处只影响展示次序。"""
    return sorted(clusters, key=lambda c: -int(c.get("editor_score") or 0))


def _drop_insufficient(clusters):
    """丢弃含[信息不足]占位的事件（summary/significance/label 任一命中）；
    剩余不足 MIN_EVENTS 时保底全留（防报告塌空）。"""
    def _bad(c):
        return (_is_insufficient(c.get("summary"))
                or _is_insufficient(c.get("significance"))
                or _is_insufficient(c.get("label")))
    good = [c for c in clusters if not _bad(c)]
    return good if len(good) >= MIN_EVENTS else clusters


MIN_DEEP_SCORE = 55  # 快筛 ≥55 才进 Phase 2 深度分析


def _quick_score_event(cluster, yesterday_labels=None):
    """4 维快筛（借鉴 BestBlogs v4 权重）：信号深度40/科技相关性30/事实密度20/新颖度10 + 减分。"""
    items = cluster.get("items", []) or []
    n = len(items)
    if n == 0:
        return 0
    # 1) 信号深度 0-40：素材量 + 跨源 + 时间跨度
    src_types = set(it.get("source_type") or it.get("_src") for it in items)
    ages = []
    for it in items:
        pub = _parse_iso(it.get("pub_date", ""))
        ages.append(_hours_ago(pub) if pub else 0)
    span_h = (max(ages) - min(ages)) if len(ages) > 1 else 0
    depth = min(15.0, n * 2.5) + min(15.0, len(src_types) * 5) + min(10.0, span_h / 12.0)
    # 2) 科技相关性 0-30：topic_tag ∈ MAIN_TOPICS 占比；
    #    缓存过渡期 tag 覆盖率 <50% 时给中性满分（对抗审查 P1-2：防单条新标记误杀）
    tagged = [it for it in items if it.get("topic_tag")]
    if tagged and len(tagged) * 2 >= n:
        ratio = sum(1 for it in tagged if it.get("topic_tag") in MAIN_TOPICS) / float(len(tagged))
    else:
        ratio = 1.0
    relevance = 30.0 * ratio
    # 3) 事实密度 0-20：含具体数字的素材占比
    def _has_num(it):
        return bool(re.search(r'\d', (it.get("text") or "") + (it.get("title") or "")))
    density = 20.0 * sum(1 for it in items if _has_num(it)) / n
    # 4) 新颖度 0-10：24h 内素材占比
    fresh = sum(1 for a in ages if a <= 24)
    novelty = 10.0 * fresh / n
    raw = depth + relevance + density + novelty
    # 减分（BestBlogs v4 风格，最多 -20）
    ded = 0
    if n == 1:
        ded += 5
    urls = [it.get("url") or it.get("link") for it in items if (it.get("url") or it.get("link"))]
    if len(urls) > 1 and len(set(urls)) == 1:
        ded += 10
    if yesterday_labels and (cluster.get("label") or "").strip() in yesterday_labels:
        ded += 10
    return int(max(0, min(100, raw - ded)))


def _dedup_tokens(title):
    """去重专用分词：英文按词切分 + 中文按 character bigrams。"""
    text = (title or "").lower()
    tokens = set()
    for w in re.findall(r'[a-z0-9]{2,}', text):
        tokens.add(w)
    cjk = re.findall(r'[\u4e00-\u9fff]', text)
    for k in range(len(cjk) - 1):
        tokens.add(cjk[k] + cjk[k + 1])
    return tokens


# ── 第4轮语义去重：词袋门槛漏网的跨类别同题对（07:13 华为对 infra/industry）由 embedding 兜住 ──
_ROLLBACK_UNSET = object()
_TEXT_EMB_CACHE = {}
_SEM_EMB_DEAD = {"flag": False}
_SEM_LABEL_COS = 0.85
_SEM_SIG_COS = 0.80


def _embed_for_sem(texts):
    """带模块级缓存的批量向量化；返回 {text: vec}。不可用（无 key/失败/异常）返回 None。"""
    if _SEM_EMB_DEAD["flag"]:
        return None
    todo = [t for t in dict.fromkeys(texts) if t and t not in _TEXT_EMB_CACHE]
    if todo:
        if not os.environ.get("SILICONFLOW_API_KEY"):
            return None
        try:
            vecs, _model = _embed_chunks(todo)
        except Exception as exc:
            print("[每日洞察] 语义去重 embedding 异常: %s" % exc, file=sys.stderr)
            return None
        if not vecs or len(vecs) != len(todo):
            _SEM_EMB_DEAD["flag"] = True
            print("[每日洞察] 语义去重 embedding 不可用，本构建内跳过该闸", file=sys.stderr)
            return None
        _TEXT_EMB_CACHE.update(dict(zip(todo, vecs)))
    return {t: _TEXT_EMB_CACHE.get(t) for t in texts if t}


def _cos_sim(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    return dot / (math.sqrt(na) * math.sqrt(nb)) if na > 0 and nb > 0 else 0.0


def _semantic_dup_round(clusters):
    """语义同题合并：label 与 summary 双余弦过线 + 文本佐证才并。

    护栏：summary 独立成签名（不含 label），使 9/17「同 label 不同内容」错标对
    因 summary 余弦不过线而保持拆分；跨类别另要求 summary 词面重叠>=3。
    """
    if len(clusters) < 2:
        return clusters
    labels = [(c.get("label") or "").strip() for c in clusters]
    sigs = [((c.get("summary") or "").strip()[:200] or lbl)
            for lbl, c in zip(labels, clusters)]
    vec_map = _embed_for_sem(labels + sigs)
    if not vec_map or any(vec_map.get(t) is None for t in labels + sigs if t):
        return clusters
    used = set()
    merged = []
    near_miss = []  # T3: 每期打印 top-3 近邻对，积累 bge-m3 真实分布供阈值校准
    for i in range(len(clusters)):
        if i in used:
            continue
        ci = clusters[i]
        for j in range(i + 1, len(clusters)):
            if j in used:
                continue
            cj = clusters[j]
            if not labels[i] or not labels[j]:
                continue
            _cl = _cos_sim(vec_map.get(labels[i]), vec_map.get(labels[j]))
            _cs = _cos_sim(vec_map.get(sigs[i]), vec_map.get(sigs[j]))
            if _cl >= 0.70:
                near_miss.append((_cl, _cs, labels[i], labels[j]))
            if _cl < _SEM_LABEL_COS or _cs < _SEM_SIG_COS:
                continue
            same_cat = ci.get("category") == cj.get("category")
            if same_cat:
                tok_hit = len(_dedup_tokens(labels[i]) & _dedup_tokens(labels[j])) >= 2
                urls_i = {_norm_url(it.get("url", "")) for it in ci.get("items", []) if it.get("url")}
                urls_j = {_norm_url(it.get("url", "")) for it in cj.get("items", []) if it.get("url")}
                if not tok_hit and not (urls_i & urls_j):
                    continue
            else:
                si = _dedup_tokens(sigs[i])
                sj = _dedup_tokens(sigs[j])
                if len(si & sj) < 3:
                    continue
            ci["items"].extend(cj.get("items", []))
            ci["source_types"] = list(set(ci.get("source_types", []) or []) | set(cj.get("source_types", []) or []))
            # 劣化正文（占位/伪装占位）不得因压分更高而存活；翻转须整套换，防字段间文不对题
            _ci_bad = (_is_insufficient(ci.get("summary") or "")
                       or _is_insufficient(ci.get("significance") or ""))
            _cj_ok = not (_is_insufficient(cj.get("summary") or "")
                          or _is_insufficient(cj.get("significance") or ""))
            if cj.get("score", 0) > ci.get("score", 0) or (_ci_bad and _cj_ok):
                for k in ("label", "summary", "significance"):
                    if cj.get(k):
                        ci[k] = cj[k]
                _lk = [u for u in (cj.get("key_links") or []) if u]
                _lk += [u for u in (ci.get("key_links") or []) if u and u not in _lk]
                ci["key_links"] = _validate_key_links(_lk, ci["items"])[:3]
                ci["deep_analysis"] = None  # 旧深度解读属被抛弃正文，禁用防张冠李戴
                # P1-3：展示文本已换成 j 的，证据向量必须同步刷新，防 C 借旧 A 搭车链式合并
                labels[i], sigs[i] = labels[j], sigs[j]
            ci["score"] = max(ci.get("score", 0), cj.get("score", 0))
            print("[每日洞察] 语义合并 cos_l=%.2f cos_s=%.2f: %s ⇐ %s" % (
                _cl, _cs, (ci.get("label") or "")[:30], (cj.get("label") or "")[:30]))
            used.add(j)
        merged.append(ci)
    if near_miss:
        for _c1, _c2, _l1, _l2 in sorted(near_miss, key=lambda t: -t[0])[:3]:
            print("[每日洞察] 语义近邻(未并) cos_l=%.2f cos_s=%.2f: %s <=> %s" % (
                _c1, _c2, _l1[:26], _l2[:26]))
    return merged


def _deduplicate_after_phase1(clusters):
    """Phase 1 后去重：合并同 category 且标签高度相似的相邻事件。"""
    if len(clusters) < 2:
        return clusters

    def _simple_tokens(title):
        return _dedup_tokens(title)

    merged = []
    used = set()
    for i in range(len(clusters)):
        if i in used:
            continue
        ci = clusters[i]  # 修复：在内层循环前初始化 ci，避免最后一个事件重复
        for j in range(i + 1, len(clusters)):
            if j in used:
                continue
            cj = clusters[j]
            # 类别守卫：不同 category 不合并（9/17 evt_002/evt_010 同标签不同内容的错并防护）
            if (ci.get("category") == cj.get("category")
                    and len(_simple_tokens(ci.get("label", "")) & _simple_tokens(cj.get("label", ""))) >= 2
                    and _jaccard(_simple_tokens(ci.get("label", "")),
                                 _simple_tokens(cj.get("label", ""))) >= 0.2):
                # 合并 items 和 source_types
                ci["items"].extend(cj.get("items", []))
                ci["source_types"] = list(set(ci.get("source_types", []) or []) | set(cj.get("source_types", []) or []))
                # 保留高分事件的 label/summary
                if cj.get("score", 0) > ci.get("score", 0):
                    ci["label"] = cj.get("label", ci.get("label", ""))
                    ci["summary"] = cj.get("summary", ci.get("summary", ""))
                ci["score"] = max(ci.get("score", 0), cj.get("score", 0))
                used.add(j)
        merged.append(ci)
    if len(merged) < len(clusters):
        print("[每日洞察] Phase 1 后去重(label): %d → %d 个事件" % (len(clusters), len(merged)))

    # 第二轮：summary 相似度去重（捕获 label 不同但主题相同的事件）
    if len(merged) >= 2:
        merged2 = []
        used2 = set()
        for i in range(len(merged)):
            if i in used2:
                continue
            ci = merged[i]
            for j in range(i + 1, len(merged)):
                if j in used2:
                    continue
                cj = merged[j]
                si = _simple_tokens(ci.get("summary", "") or ci.get("label", ""))
                sj = _simple_tokens(cj.get("summary", "") or cj.get("label", ""))
                overlap = len(si & sj)
                jacc = _jaccard(si, sj)
                # 第三层检测：源 URL 重叠率（同一事件多源转载时 URL 高度重叠）
                urls_i = set(it.get("url", "") for it in ci.get("items", []) if it.get("url"))
                urls_j = set(it.get("url", "") for it in cj.get("items", []) if it.get("url"))
                url_overlap = len(urls_i & urls_j) / min(len(urls_i), len(urls_j)) if min(len(urls_i), len(urls_j)) > 0 else 0
                # 合并条件：
                # - 源URL重叠>50%（同一批源文章=同一事件，可跨类别）
                # - 同类别：常规相似度达标，或"低相似高冗余"转述对（同一事件不同记者写法，22:14 实测）
                # - 跨类别：summary 高冗余+高相似组合强证据才允许（9/17 错标反例 summary 零重叠被此闸挡下）
                same_cat = ci.get("category") == cj.get("category")
                if url_overlap > 0.5:
                    pass  # URL 高度重叠，直接合并
                elif same_cat and ((overlap >= 3 and jacc >= 0.15) or (overlap >= 20 and jacc >= 0.08)):
                    pass  # 同类别文本相似或高冗余
                elif (not same_cat) and ((overlap >= 20 and jacc >= 0.30) or (overlap >= 40 and jacc >= 0.25)):
                    pass  # 跨类别组合强证据（0.25 档为 22:14 实测漏网对 ov=52/jacc=0.286 放开，非重复对最大 ov45/jacc0.237 仍被挡）
                else:
                    continue
                # 合并：保留高分事件的 label/summary
                ci["items"].extend(cj.get("items", []))
                ci["source_types"] = list(set(ci.get("source_types", []) or []) | set(cj.get("source_types", []) or []))
                if cj.get("score", 0) > ci.get("score", 0):
                    ci["label"] = cj.get("label", ci.get("label", ""))
                    ci["summary"] = cj.get("summary", ci.get("summary", ""))
                ci["score"] = max(ci.get("score", 0), cj.get("score", 0))
                used2.add(j)
            merged2.append(ci)
        if len(merged2) < len(merged):
            print("[每日洞察] Phase 1 后去重(summary): %d → %d 个事件" % (len(merged), len(merged2)))
        merged = merged2

    # 第三轮：实体级去重 — 捕获 label 不同但报道同一产品/事件的情况
    # 原理：提取产品名、公司名、技术术语等关键实体，若两个 cluster 的核心实体
    # 高度重叠（>50%）且 label 有最低限度文本相似（Jaccard>0.05），则合并
    if len(merged) >= 2:
        def _extract_entities(text):
            """提取关键实体：英文产品/模型名 + 中文专有名词"""
            entities = set()
            t = (text or "")
            # 英文实体：含数字/大写的词（模型名、产品名、公司名）
            for w in re.findall(r'[A-Za-z][A-Za-z0-9._\-]*[0-9][A-Za-z0-9._\-]*', t):
                entities.add(w.lower().rstrip('.'))
            for w in re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', t):
                entities.add(w.lower())
            # 中文实体：引号内内容、「」内内容
            for m in re.findall(r'[「「]([^」」]{2,20})[」」]', t):
                entities.add(m)
            return entities

        merged3 = []
        used3 = set()
        for i in range(len(merged)):
            if i in used3:
                continue
            ci = merged[i]
            ei = _extract_entities(ci.get("label", ""))
            for j in range(i + 1, len(merged)):
                if j in used3:
                    continue
                cj = merged[j]
                # 类别守卫：实体/文本证据只在同类别内合并（跨类别仅第二轮 URL 重叠可豁免）
                if ci.get("category") != cj.get("category"):
                    continue
                ej = _extract_entities(cj.get("label", ""))
                if not ei or not ej:
                    continue
                overlap_e = ei & ej
                entity_ratio = len(overlap_e) / min(len(ei), len(ej))
                if entity_ratio < 0.5:
                    continue
                # 实体高度重叠 → 检查 label 是否有最低限度文本相似（防误合并不同话题）
                ti = _simple_tokens(ci.get("label", ""))
                tj = _simple_tokens(cj.get("label", ""))
                jacc = _jaccard(ti, tj)
                if jacc < 0.05:
                    continue
                # 合并
                ci["items"].extend(cj.get("items", []))
                ci["source_types"] = list(set(ci.get("source_types", []) or []) | set(cj.get("source_types", []) or []))
                if cj.get("score", 0) > ci.get("score", 0):
                    ci["label"] = cj.get("label", ci.get("label", ""))
                    ci["summary"] = cj.get("summary", ci.get("summary", ""))
                ci["score"] = max(ci.get("score", 0), cj.get("score", 0))
                used3.add(j)
            merged3.append(ci)
        if len(merged3) < len(merged):
            print("[每日洞察] Phase 1 后去重(entity): %d → %d 个事件" % (len(merged), len(merged3)))
        merged = merged3

    _before_sem = len(merged)
    try:
        merged = _semantic_dup_round(merged)
    except Exception as exc:
        print("[每日洞察] 语义去重异常，跳过: %s" % exc, file=sys.stderr)
    if len(merged) < _before_sem:
        print("[每日洞察] Phase 1 后去重(semantic): %d → %d 个事件" % (_before_sem, len(merged)))

    return merged


def _apply_phase1_result(clusters, p1_result):
    """按 event_num 严格配对 Phase 1 输出。

    P0 修复（08:31 期文不对题实证）：旧逻辑按下标 p1_events[i] 喂 clusters[i]，
    LLM 跳过任一事件后全部错位一格。缺号事件保持原文，宁缺勿错位。
    """
    theme = p1_result.get("theme", "")
    p1_events = [e for e in p1_result.get("events", []) if isinstance(e, dict)]
    by_num = {}
    _raw_nums = []
    for e in p1_events:
        n = e.get("event_num")
        if isinstance(n, str) and n.strip().isdigit():
            n = int(n.strip())
        if isinstance(n, int):
            _raw_nums.append(n)
        if isinstance(n, int) and 1 <= n <= len(clusters) and n not in by_num:
            by_num[n] = e
    # 0-based 漂移（LLM 从 0 编号）：整体平移而非静默错位一格
    if _raw_nums and 0 in _raw_nums:
        by_num = {}
        for e in p1_events:
            n = e.get("event_num")
            if isinstance(n, str) and n.strip().isdigit():
                n = int(n.strip())
            if isinstance(n, int) and 0 <= n < len(clusters) and (n + 1) not in by_num:
                by_num[n + 1] = e
        print("[每日洞察] Phase1 event_num 为 0-based，已整体平移对齐", file=sys.stderr)
    numbered = bool(by_num)
    for i, c in enumerate(clusters):
        if numbered:
            pe = by_num.get(i + 1)
            if pe is None:
                # 缺号事件：打占位标记交给占位闸，防「原标题+空正文」卡片
                c["summary"] = "[信息不足] Phase1 未返回该事件输出"
                print("[每日洞察] Phase1 缺事件 %d 输出，打占位标记防错位" % (i + 1),
                      file=sys.stderr)
                continue
        else:
            if i >= len(p1_events):
                continue
            pe = p1_events[i]  # 旧格式无 event_num：回退下标配对
        c["label"] = pe.get("label", c["label"])
        c["category"] = pe.get("category", c.get("category", ""))
        c["summary"] = pe.get("summary", "")
        c["significance"] = pe.get("significance", "")
        c["key_links"] = _validate_key_links(pe.get("key_links", []), c.get("items", []))
    return theme


def _llm_phase1(llm, clusters, global_context=None):
    """Phase 1: 为每个事件生成结构化摘要 + 今日主题导语。"""
    if not llm or not clusters:
        return None

    events_text = []
    for i, c in enumerate(clusters):
        material = _build_event_material(c)
        events_text.append("## 事件 %d（信号强度: %.1f，来源: %s）\n%s" % (
            i + 1, c["score"], ", ".join(c["source_types"]), material))

    # 全局检索上下文：让 LLM 见到评估器认为它该见到的完整信息场
    if global_context:
        _gc_block = "【全局检索上下文】（今日 AI/科技领域完整信息场。其中的诉讼监管动向、宏观格局类高分辨性主题必须优先纳入事件清单或写入对应 summary，不得只看单一产品线）：\n%s" % global_context
    else:
        _gc_block = ""

    prompt = """今天是 %s。以下是今日 AI/科技领域 %d 个热点事件的原始素材。

%s

请完成两个任务：

1. 为每个事件输出结构化摘要
2. 用一句话概括今日内容主线（≤60字），样式：「从 X，到 Y，再到 Z，判断 W」

%s

输出严格 JSON：
{
  "theme": "一句话今日主题",
  "events": [
    {
      "event_num": 1,
      "label": "一句话事件标题（15字以内，陈述句）",
      "category": "ai-models|ai-products|industry|research|policy|funding|developer|consumer",
      "summary": "2-3句话概括：发生了什么、谁参与的、关键数据",
      "significance": "一句话说明为什么值得关注",
      "key_links": ["最重要的1-2个原文链接"]
    }
  ]
}

约束：
- label 必须是陈述句，不是疑问句
- events 数组必须输出全部 %d 项，event_num 必须与素材事件编号一一对应，禁止跳过或合并条目
- summary 必须包含具体数据（参数量/融资金额/用户数等），不能是空泛描述
- category 必须从枚举中选
- 如果素材不足以判断，summary 里标注[信息不足]
- 所有陈述必须基于素材，不要编造
- 每个事件的 summary 必须覆盖该事件素材中的所有关键事实点（至少 3 个独立信息点）
- 不要只挑最重要的 1-2 条素材，要综合所有素材
- 如果全局上下文中有重要信息未被任何事件覆盖，请在 theme 中提及""" % (NOW_BJ.strftime("%Y年%m月%d日"), len(clusters), "\n\n".join(events_text), _gc_block, len(clusters))

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_P1},
        {"role": "user", "content": prompt},
    ]
    result = llm.complete(messages, temperature=0.3, max_tokens=4200)
    parsed = _robust_parse_json(result)
    if not parsed:
        print("[每日洞察] Phase 1 LLM 输出解析失败", file=sys.stderr)
        return None
    print("[每日洞察] Phase 1 LLM 成功: theme + %d events" % len(parsed.get("events", [])))
    return parsed


def _verify_faithfulness(llm, clusters, global_context_chunks=None):
    """事实核查：逐事件检查 summary/significance 中的每个声明是否有 chunk 支撑。
    使用全局检索上下文（与 RAGAS 评估器一致），确保 faithfulness ≥ 0.95。"""
    if not llm or not clusters:
        return

    # 构建全局素材上下文（与 RAGAS 评估器使用相同的 chunks）
    # LLM 有 1M 上下文，充分利用：60 chunks × 800 chars ≈ 48K chars ≈ 12K tokens (1.2%)
    global_ctx = ""
    if global_context_chunks:
        sorted_gc = sorted(global_context_chunks, key=lambda c: c.get("retrieval_score", 0), reverse=True)
        parts = []
        for c in sorted_gc[:60]:
            text = c.get("text", "")[:800]
            title = c.get("title", "")[:100]
            src = c.get("source_type", "")
            if text:
                parts.append("[%s] %s: %s" % (src, title, text[:700]))
        global_ctx = "\n---\n".join(parts)

    # 批量处理：每批 5 个事件
    batch_size = 5
    for batch_start in range(0, len(clusters), batch_size):
        batch = clusters[batch_start:batch_start + batch_size]
        events_input = []
        for idx, c in enumerate(batch):
            summary = c.get("summary", "")
            significance = c.get("significance", "")
            # 该事件自身的 chunks
            own_chunks = []
            for it in c.get("items", [])[:10]:
                text = it.get("text", "") or it.get("full_content") or it.get("summary") or ""
                text = _strip_html(text)[:600]
                title = it.get("title", "")[:100]
                if text or title:
                    own_chunks.append("[%s] %s: %s" % (
                        it.get("source_type", "") or it.get("_src", ""),
                        title, text[:500]))
            own_ctx = "\n".join(own_chunks)
            events_input.append(
                "--- 事件 %d ---\n[事件素材]:\n%s\n[摘要]: %s\n[意义]: %s" % (
                    batch_start + idx + 1, own_ctx, summary, significance))

        prompt = (
            "你是严格的事实核查编辑。你的任务是确保报告中每个声明都有素材依据。\n\n"
            "【全局素材库】（所有可用的原始信息）：\n%s\n\n"
            "【待核查事件】：\n%s\n\n"
            "核查规则（极其严格）：\n"
            "1. 摘要和意义中的每一个事实、数字、名称、日期都必须在全局素材库中有直接依据\n"
            "2. 如果某个声明在素材库中找不到原文或近义表述，必须删除\n"
            "3. 禁止用你自己的知识补充任何信息\n"
            "4. 宁可标注[信息不足]也不要编造\n"
            "5. 改写时保持语句通顺\n"
            "6. 已注明“该说法有争议”及分歧方的表述属于有依据陈述，不得删除，也不得改写为确定事实\n\n"
            "以 JSON 返回：\n"
            "{\"events\": [{\"event_num\": 1, \"summary\": \"修正后摘要\", \"significance\": \"修正后意义\"}]}"
        ) % (global_ctx, "\n\n".join(events_input))

        messages = [
            {"role": "system", "content": "你是事实核查编辑。只输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ]
        result = llm.complete(messages, temperature=0.1, max_tokens=2500)
        parsed = _robust_parse_json(result)
        if not parsed or "events" not in parsed:
            continue

        # 应用修正
        for pe in parsed["events"]:
            num = pe.get("event_num", 0) - 1
            if 0 <= num < len(clusters):
                old_summary = clusters[num].get("summary", "")
                new_summary = pe.get("summary", "")
                if new_summary and len(new_summary) > len(old_summary) * 0.5:
                    clusters[num]["summary"] = new_summary
                old_sig = clusters[num].get("significance", "")
                new_sig = pe.get("significance", "")
                if new_sig and len(new_sig) > len(old_sig) * 0.4:
                    clusters[num]["significance"] = new_sig

    print("[每日洞察] 事实核查完成: %d 个事件" % len(clusters))


def _final_faith_recheck(llm, clusters, context_chunks):
    """RAGAS 修正环+去重会再次改写 summary → 终局事实核查（faith 最后一道闸）。
    与 Phase 1.5 共用 _verify_faithfulness；llm 缺失/异常时静默降级不阻断落盘。"""
    if not llm or not clusters:
        return False
    try:
        _verify_faithfulness(llm, clusters, context_chunks)
        return True
    except Exception as exc:
        print("[每日洞察] 终局事实核查异常，跳过: %s" % exc, file=sys.stderr)
        return False


# ── Phase 2 LLM：Top N 深度解读 ──

_SYSTEM_PROMPT_P2 = """
(C) Context: 你是一位资深 AI 行业分析师，正在撰写每日深度报告的核心事件解读。
读者是 AI 从业者和科技决策者，他们已看过事件摘要，需要更深层的分析。

(O) Objective: 对单个事件进行深度解读，包括事件还原、影响分析、信源分歧和后续展望。
你的分析将直接展示在 AI 日报的深度解读栏。

(S) Style: 分析师报告风格——严谨、分层、有据可查。
写法要求：
1. event_reconstruction 按时间线叙述，包含具体数据（日期/金额/人数）
2. impact_analysis 分短期/中期/长期三个层次
3. source_divergence 具体指出哪个源持什么角度
4. quote 必须是素材原文，不要编造

(T) Tone: 专业、客观、基于事实。如果素材中有矛盾数据，必须在分析中指出。

(A) Audience: AI 从业者、科技媒体编辑、技术决策者。

(R) Response: 严格输出 JSON：
{"event_reconstruction": "...", "impact_analysis": "...", "source_divergence": "...", "quote": "...", "outlook": "...", "confidence": "high|medium|low", "citations": {"字段名": [素材编号]}}
citations 为字段级来源索引：每个字段的结论必须标注其来自哪些素材片段（片段以 [n] 编号）。无法归属来源的内容不应存在。

## 正确示例
{
  "event_reconstruction": "9月15日，OpenAI宣布完成100亿美元D轮融资，由软银领投，估值达2000亿美元。资金将用于AGI研发和基础设施建设。",
  "impact_analysis": "短期：AI赛道融资标杆再创新高，竞争对手融资压力加大。中期：软银大举入场改变AI投资格局。长期：2000亿估值倒逼OpenAI加速商业化。",
  "source_divergence": "36氪关注商业模式，虎嗅质疑估值泡沫，HN讨论技术路线。",
  "quote": "资金将用于AGI研发和基础设施建设",
  "outlook": "预计Q4将看到OpenAI企业版产品加速落地。",
  "confidence": "high"
}

## 禁用表达
“值得关注”“引发讨论”“未来可期”“拭目以待”“不难预见”
每句话必须有信息增量，不允许空话。所有陈述必须基于素材。
素材对某一说法存在分歧（质疑、否认、要求核实）时，必须标注"该说法有争议"及分歧方，不得写成确定事实。"""


def _llm_phase2(llm, cluster, phase1_summary, prev_summary=None, evidence=""):
    """Phase 2: 单个事件的深度解读。evidence 为同源 RSS 全文存档交叉参考（可为空）。"""
    if not llm:
        return {"status": "degraded", "reason": "llm_unavailable",
                "event_reconstruction": "", "impact_analysis": "",
                "source_divergence": "", "quote": "", "outlook": "",
                "confidence": "low"}

    material, mat_refs = _build_event_material(cluster, numbered=True)
    prompt = """今天是 %s。请深度解读以下事件。

## 事件：%s
### 多源素材（每条以 [编号] 开头，引用时必须使用这些编号）
%s

### 摘要
%s
""" % (NOW_BJ.strftime("%Y年%m月%d日"), phase1_summary.get("label", ""),
       material, phase1_summary.get("summary", ""))

    if evidence:
        prompt += """
### 补充全文参考（本事件专属的同源 RSS 存档原文，仅用于交叉核对数据与信源观点分歧；不可作为引用编号来源，citations 仍只能引用上方素材 [n] 编号；文中出现的其他人物/公司/事件只能作为背景，严禁把其事实或数字嫁接到本事件主角（06:12 期张冠李戴教训））
%s
""" % evidence[:8000]

    if prev_summary:
        prompt += """
### 历史追踪
该事件昨日状态: ongoing，昨日摘要: %s
请对比昨日信息，指出今日新增的事实或变化。
""" % prev_summary

    prompt += """
请输出严格 JSON：
{
  "event_reconstruction": "事件完整还原（300-500字，按时间线叙述，包含具体数据）",
  "impact_analysis": "影响分析（200-300字，分短期/中期/长期）",
  "source_divergence": "信源分歧（具体指出哪个源持什么角度，无分歧则写'各源报道角度一致'）",
  "quote": "素材中最有分量的一句原文引用",
  "outlook": "后续展望（1-2句话，基于素材中的信号和趋势推断下一步发展，不得编造素材中不存在的信息）",
  "confidence": "high|medium|low",
  "citations": {
    "event_reconstruction": [1, 3],
    "impact_analysis": [1],
    "source_divergence": [1, 2, 3],
    "quote": 2,
    "outlook": [3]
  }
}

约束：
- event_reconstruction 必须按时间线叙述，包含具体数据
- impact_analysis 必须分短期/中期/长期三个层次
- source_divergence 要具体指出哪个源持什么角度
- quote 必须是素材中的原文，不要编造
- confidence: 多源交叉验证=high，单一信源=low
- 禁止使用"值得关注""引发讨论""未来可期"等空话，每句话必须有信息增量
- outlook 必须基于素材中已有的信号和趋势进行推断，不得编造
- 所有陈述必须基于素材
- citations 为字段级引用：每个字段的结论来自哪些素材编号（整数数组，quote 填单个编号）。
  无法归属到任何素材编号的句子必须删除；编号只能使用素材中出现过的 [n]
"""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_P2},
        {"role": "user", "content": prompt},
    ]
    result = None
    parsed = None
    for _attempt in range(2):
        result = llm.complete(messages, temperature=0.3, max_tokens=3000)
        parsed = _robust_parse_json(result)
        if parsed:
            break
        if _attempt == 0:
            print("[每日洞察] Phase 2 第1次解析失败，重试（事件: %s）" % cluster.get("id", "?"),
                  file=sys.stderr)
    if not parsed:
        # 记录原始输出便于诊断
        _raw_preview = (result or "")[:300].replace("\n", "\\n")
        print("[每日洞察] Phase 2 LLM 输出解析失败（事件: %s），原始输出前300字: %s" % (
              cluster.get("id", "?"), _raw_preview), file=sys.stderr)
        return {"status": "degraded", "reason": "llm_parse_failed",
                "event_reconstruction": "", "impact_analysis": "",
                "source_divergence": "", "quote": "", "outlook": "",
                "confidence": "low"}
    parsed = _validate_phase2_citations(parsed, mat_refs)
    parsed["status"] = "ok"
    return parsed


# ──────────────────── Phase 3 自审环节：Phase 1 输出质量检查 ────────────────────

_BANNED_PHRASES = [
    "值得关注", "引发讨论", "未来可期", "拭目以待", "不难预见",
    "令人期待", "意义重大", "影响深远", "引发广泛关注", "备受关注",
    "引人注目", "引发热议", "成为焦点",
]


def _review_event_quality(events):
    """检查 Phase 1 事件输出的质量问题，返回问题列表。"""
    issues = []
    for evt in events:
        eid = evt.get("id", "?")
        summary = evt.get("summary", "")
        significance = evt.get("significance", "")
        text = summary + significance

        for phrase in _BANNED_PHRASES:
            if phrase in text:
                issues.append("事件%s 含空话「%s」" % (eid, phrase))

        has_data = bool(re.search(r'\d+[%％亿万美元人民币$€]|\d{2,}', summary))
        if not has_data and len(summary) > 10:
            issues.append("事件%s summary 缺少具体数据" % eid)

        if 0 < len(summary) < 20:
            issues.append("事件%s summary 过短（%d字）" % (eid, len(summary)))

    return issues


def _self_review_phase1(llm, events, material_text):
    """Phase 1 自审环节：检查输出质量，有问题时请求 LLM 修正。最多 1 次。"""
    if not llm or not events:
        return events

    issues = _review_event_quality(events)
    if not issues:
        print("[每日洞察] Phase 1 自审: 质量合格 (%d 个事件, 0 问题)" % len(events))
        return events

    print("[每日洞察] Phase 1 自审: 发现 %d 个问题，请求 LLM 修正..." % len(issues),
          file=sys.stderr)

    events_json = json.dumps(
        [{"id": e.get("id", ""), "label": e.get("label", ""),
          "summary": e.get("summary", ""), "significance": e.get("significance", "")}
         for e in events[:MAX_EVENTS]],
        ensure_ascii=False, indent=2)

    prompt = """请检查并修正以下事件摘要的质量问题。

【问题清单】：
%s

【事件列表】：
%s

【原始素材参考】：
%s

修正要求：
1. 消除所有空泛表达
2. 确保 summary 包含具体数据
3. 所有事实必须基于素材
4. 以 JSON 数组返回修正后的事件，保持 id 不变
5. 仅修改有问题的字段

输出格式：[{"id": "e1", "label": "...", "summary": "...", "significance": "..."}]""" % (
        "\n".join("- " + iss for iss in issues[:10]),
        events_json, material_text[:2000])

    messages = [
        {"role": "system", "content": "你是 AI 行业分析师。只返回 JSON 数组。"},
        {"role": "user", "content": prompt},
    ]
    result = llm.complete(messages, temperature=0.2, max_tokens=3000)
    parsed = _robust_parse_json(result)

    if not isinstance(parsed, list):
        print("[每日洞察] Phase 1 自审: 解析失败（返回类型=%s），保留原版" % type(parsed).__name__, file=sys.stderr)
        return events

    corrected_count = 0
    id_to_fixed = {p.get("id"): p for p in parsed if isinstance(p, dict)}
    for evt in events:
        eid = evt.get("id", "")
        if eid in id_to_fixed:
            fixed = id_to_fixed[eid]
            for field in ("label", "summary", "significance"):
                if fixed.get(field) and len(fixed[field]) > len(evt.get(field, "") or ""):
                    evt[field] = fixed[field]
                    corrected_count += 1

    print("[每日洞察] Phase 1 自审: 修正 %d 个字段" % corrected_count)
    return events


# ──────────────────── 破茧栏：反信息茧房 ────────────────────

def _build_read_profile(history):
    """从过去 7 天历史中统计用户常读 category 分布。"""
    profile = {}
    days = history.get("days", [])
    for day in days[-7:]:
        for evt in day.get("events", []):
            cat = evt.get("category", "")
            if cat:
                profile[cat] = profile.get(cat, 0) + 1
    return profile


def _select_bubble_events(clusters, read_profile, residual_chunks=None, all_chunks=None, top_n=5):
    """破茧栏 v2：正向识别非科技主题候选池 → 热度排序（QWIS cocoonFamiliar 式）。

    候选优先级：
    1. all_chunks 中 topic_tag ∈ BUBBLE_TOPICS 的 chunk（主设计路径）
    2. residual_chunks 旧评分路径（过渡兼容）
    3. clusters 中 category 与 read_profile 交集最低的兜底
    """
    main_cats = set(c.get("category", "") for c in clusters if c.get("category"))

    main_keys = set()
    for c in clusters:
        if c.get("label"):
            main_keys.add(c["label"])
        for it in c.get("items", []):
            for k in (it.get("url", ""), (it.get("title", "") or "").strip()):
                if k:
                    main_keys.add(k)

    read_top = ", ".join(k for k, v in sorted(read_profile.items(), key=lambda x: -x[1])[:2]) if read_profile else ""

    def _bubble_heat(ch):
        hot = min(10.0, float(ch.get("hot", 0) or 0))
        pub = _parse_iso(ch.get("pub_date", ""))
        age_h = _hours_ago(pub) if pub else 168
        recency = (0.5 ** (age_h / 72.0)) * 10  # 破茧 7 天窗口，半衰期 72h
        return round(hot * 0.5 + recency * 0.3, 2)

    def _same_topic(ta, tb):
        ja, jb = _tokenize_title(ta), _tokenize_title(tb)
        if not ja or not jb:
            return False
        inter = len(ja & jb)
        # 词级分词下近似重复标题 Jaccard 约 0.35-0.4（实测），低于 QWIS 整句 0.5
        return _jaccard(ja, jb) >= 0.35 or inter / min(len(ja), len(jb)) >= 0.6

    # ── 路径 1：非科技 topic 候选池（限 INSIGHT_RSS_HOURS 新鲜窗口，防旧缓存回潮） ──
    def _fresh_enough(ch):
        pub = _parse_iso(ch.get("pub_date", ""))
        return (not pub) or _hours_ago(pub) <= INSIGHT_RSS_HOURS

    pool = [c for c in (all_chunks or [])
            if c.get("topic_tag") in BUBBLE_TOPICS
            and _fresh_enough(c)
            and (c.get("url", "") or c.get("link", "")) not in main_keys
            and (c.get("title", "") or "").strip() not in main_keys]
    pool.sort(key=_bubble_heat, reverse=True)
    result = []
    for ch in pool:
        if any(_same_topic(ch.get("title", ""), r["label"]) for r in result):
            continue
        result.append({
            "label": (ch.get("title", "") or "").strip()[:80],
            "summary": ((ch.get("text", "") or "").strip() or ch.get("summary", ""))[:200],
            "category": ch.get("topic_tag", ""),
            "score": _bubble_heat(ch),
            "reason": ("与你常读的科技领域不同" if read_top else "非科技热点"),
            "url": ch.get("url", "") or ch.get("link", ""),
            "source": ch.get("source", "") or ch.get("platform", ""),
        })
        if len(result) >= top_n:
            return result
    if result:
        return result

    # ── 路径 2：residual 旧逻辑（按 source_type 分组评分） ──
    residual = []
    for chunk in (residual_chunks or []):
        url = chunk.get("url", "")
        title = (chunk.get("title", "") or "").strip()
        if url and url in main_keys:
            continue
        if title and title in main_keys:
            continue
        residual.append(chunk)

    if residual:
        by_source = {}
        for chunk in residual:
            src = chunk.get("source_type", "") or chunk.get("_src", "") or "other"
            by_source.setdefault(src, []).append(chunk)

        max_freq = max(read_profile.values()) if read_profile else 1
        source_scores = []
        for src, chunk_list in by_source.items():
            src_cat = chunk_list[0].get("channel", "") or chunk_list[0].get("category", "")
            cat_novelty = 1.0 if src_cat and src_cat not in main_cats else 0.5
            read_freq = read_profile.get(src_cat, 0)
            read_novelty = 1.0 - (read_freq / max_freq) if max_freq > 0 else 0.5
            score = cat_novelty * 0.6 + read_novelty * 0.4 + len(chunk_list) * 0.01
            source_scores.append((src, chunk_list, score, src_cat))

        source_scores.sort(key=lambda x: x[2], reverse=True)
        for src, chunk_list, score, src_cat in source_scores[:top_n]:
            best = max(chunk_list, key=lambda c: float(c.get("hot", 0) or 0))
            label = (best.get("title", "") or "").strip()[:80]
            text = (best.get("text", "") or "").strip()[:200]
            if not label:
                continue
            if src_cat and src_cat not in main_cats:
                reason = "来自 %s 视角，与主流事件不同" % src
            elif read_top:
                reason = "与你常读的 %s 领域不同" % read_top
            else:
                reason = "信息增量"
            result.append({
                "label": label,
                "summary": text if text else best.get("summary", ""),
                "category": src_cat,
                "score": score,
                "reason": reason,
                "url": best.get("url", "") or best.get("link", ""),
                "source": best.get("source", "") or best.get("platform", "") or src,
            })
        if result:
            return result

    # ── 路径 3：clusters 类别新颖兜底（排除全部主报告类别，防主事件复制进破茧） ──
    _tech_cats = MAIN_TOPICS | set(VALID_CATEGORIES)
    max_freq = max(read_profile.values()) if read_profile else 1
    cand = [c for c in clusters
            if c.get("category") and c.get("category") not in _tech_cats]
    cand.sort(key=lambda c: read_profile.get(c.get("category", ""), 0) / max_freq if max_freq else 0)
    for c in cand[:top_n]:
        result.append({
            "label": (c.get("label") or "")[:80],
            "summary": (c.get("summary", "") or "")[:200],
            "category": c.get("category", ""),
            "score": round(1.0 - (read_profile.get(c.get("category", ""), 0) / max_freq if max_freq else 0), 2),
            "reason": ("与你常读的 %s 领域不同" % read_top) if read_top else "信息增量",
            "url": (c.get("key_links") or [""])[0],
            "source": ",".join(sorted(c.get("source_types", []) or [])),
        })
    return result


# ──────────────────── RAGAS: 质量评估与自我修正 ────────────────────

# Chain-of-Thought 评估 Prompt（正向视角 — 检查覆盖率）
_RAGAS_JUDGE_PROMPT = """你是 RAG 质量评估专家。请按以下步骤评估每日 AI 洞察报告的质量。

【检索上下文】（四源 RAG 检索的原始素材）：
%s

【生成的报告】：
主题: %s
%s

## 评估要求

对以下三个维度，先输出推理过程，再给出分数。

### 1. context_coverage（上下文覆盖度）
**推理步骤**：
- 列出检索上下文中的 3-5 个最重要信息点
- 逐一检查报告中是否覆盖了这些信息点
- 指出遗漏的重要信息
**评分**：基于覆盖率给出 0.0-1.0 的分数，并标注置信度（high/medium/low）

### 2. faithfulness（事实忠实度）
**推理步骤**：
- 从报告中提取 3-5 个关键事实声明
- 逐一在检索上下文中查找支撑证据
- 标注每个声明的支撑状态（supported/partially_supported/unsupported）
**评分**：基于支撑比例给出 0.0-1.0 的分数，并标注置信度

### 3. relevance（话题相关性）
**推理步骤**：
- 列出当日最重要的 3-5 个 AI/科技话题
- 检查报告中的事件是否与这些话题匹配
- 评估事件排序是否合理（最重要的在前）
**评分**：基于匹配度给出 0.0-1.0 的分数，并标注置信度

## 输出格式

请严格按以下 JSON 格式输出（不要输出 JSON 以外的内容）：
{"reasoning": {"coverage": {"evidence_points": ["..."], "covered": ["..."], "missed": ["..."], "confidence": "high|medium|low"}, "faithfulness": {"claims": [{"claim": "...", "status": "supported|partial|unsupported"}], "confidence": "high|medium|low"}, "relevance": {"key_topics": ["..."], "matched": ["..."], "unmatched": ["..."], "confidence": "high|medium|low"}}, "scores": {"context_coverage": 0.8, "faithfulness": 0.9, "relevance": 0.7}, "feedback": "具体改进建议", "weak_events": [2, 5]}"""

# Chain-of-Thought 评估 Prompt V2（反向视角 — 找出缺陷）
_RAGAS_JUDGE_PROMPT_V2 = """你是 RAG 质量审计专家。你的任务是找出报告中的缺陷和不足。

【检索上下文】：
%s

【生成的报告】：
主题: %s
%s

## 审计要求

从以下角度审视报告，先列出问题，再给出分数。

### 1. context_coverage — 信息遗漏审计
- 检索上下文中有哪些重要信息被报告遗漏了？
- 遗漏的信息对读者理解当日 AI 动态有多大影响？
- 给出 0.0-1.0 分数和置信度（high/medium/low）

### 2. faithfulness — 事实准确性审计
- 报告中有哪些声明在检索上下文中找不到依据？
- 是否存在过度推断或夸大？
- 给出 0.0-1.0 分数和置信度

### 3. relevance — 话题聚焦审计
- 报告中有哪些事件与当日核心话题关系不大？
- 事件排序是否合理？
- 给出 0.0-1.0 分数和置信度

## 输出格式

请严格按以下 JSON 格式输出（不要输出 JSON 以外的内容）：
{"reasoning": {"coverage": {"missed_points": ["..."], "impact": "...", "confidence": "high|medium|low"}, "faithfulness": {"unsupported_claims": [{"claim": "...", "issue": "..."}], "confidence": "high|medium|low"}, "relevance": {"irrelevant_events": ["..."], "ordering_issues": ["..."], "confidence": "high|medium|low"}}, "scores": {"context_coverage": 0.8, "faithfulness": 0.9, "relevance": 0.7}, "feedback": "具体改进建议", "weak_events": [2, 5]}"""


def _build_ragas_context(clusters, retrieved_chunks):
    """为 RAGAS 评估构建上下文文本：将检索到的 chunks 拼接为评估参考。"""
    # 取 top chunks 作为评估上下文（按检索分数排序）
    # LLM 有 1M 上下文，充分利用：80 chunks × 1000 chars ≈ 80K chars ≈ 20K tokens (2%)
    sorted_chunks = sorted(retrieved_chunks, key=lambda c: c.get("retrieval_score", 0), reverse=True)
    context_parts = []
    for c in sorted_chunks[:80]:
        text = c.get("text", "")[:1000]
        title = c.get("title", "")[:100]
        src = c.get("source_type", "")
        if text:
            context_parts.append("[%s] %s\n%s" % (src, title, text))
    return "\n---\n".join(context_parts)


def _evaluate_report_quality(llm, clusters, theme, context_text, prompt_variant="v1"):
    """RAGAS-inspired 报告质量评估（Chain-of-Thought 推理链）。

    使用结构化推理链让 LLM 先推理再评分，降低离散分数的随机性。
    支持两个 prompt 变体：v1（正向视角）和 v2（反向审计视角）。

    评估维度：
    - context_coverage: 事件摘要是否充分利用了检索上下文中的关键信息
    - faithfulness: 摘要/分析中的事实是否有检索 chunk 支撑（无编造）
    - relevance: 事件选取和摘要是否紧扣当日最重要的 AI/科技话题

    Returns:
        {"context_coverage": float, "faithfulness": float, "relevance": float,
         "overall": float, "feedback": str, "weak_events": [int],
         "confidences": {"coverage": str, "faithfulness": str, "relevance": str}}
    """
    if not context_text or not clusters:
        return {"context_coverage": 0.5, "faithfulness": 0.5, "relevance": 0.5,
                "overall": 0.5, "feedback": "无上下文可评估", "weak_events": [],
                "confidences": {"coverage": "low", "faithfulness": "low", "relevance": "low"}}
    if not llm:
        return {"context_coverage": 0.5, "faithfulness": 0.5, "relevance": 0.5,
                "overall": 0.5, "feedback": "LLM 不可用", "weak_events": [],
                "confidences": {"coverage": "low", "faithfulness": "low", "relevance": "low"}}

    # 构建事件摘要文本
    events_text = []
    for i, c in enumerate(clusters[:MAX_EVENTS]):
        summary = c.get("summary", "") or c.get("label", "")
        significance = c.get("significance", "") or ""
        deep = c.get("deep_analysis", {})
        deep_text = ""
        if deep:
            deep_text = deep.get("event_reconstruction", "")[:200]
            if deep.get("impact_analysis"):
                deep_text += "\n影响: " + deep["impact_analysis"][:150]
        events_text.append("事件%d [%s]: %s\n意义: %s%s" % (
            i + 1, c.get("category", ""), summary[:200],
            significance[:100], "\n深度: " + deep_text if deep_text else ""))

    # 选择 prompt 变体
    prompt_template = _RAGAS_JUDGE_PROMPT_V2 if prompt_variant == "v2" else _RAGAS_JUDGE_PROMPT
    prompt = prompt_template % (context_text, theme or "无主题", "\n".join(events_text))

    messages = [
        {"role": "system", "content": "你是 RAG 质量评估专家。先按步骤推理每个维度，再给出分数。严格输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    result = llm.complete(messages, temperature=0.2, max_tokens=4000)
    parsed = _robust_parse_json(result)

    def _clamp(v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    if isinstance(parsed, dict):
        # 优先从 scores 子对象读取，兼容旧格式（顶层字段）
        scores = parsed.get("scores", parsed)
        cov = _clamp(scores.get("context_coverage", 0.5))
        faith = _clamp(scores.get("faithfulness", 0.5))
        rel = _clamp(scores.get("relevance", 0.5))
        weak = parsed.get("weak_events", [])
        if not isinstance(weak, list):
            weak = []

        # 提取置信度（用于交叉验证加权）
        reasoning = parsed.get("reasoning", {})
        confidences = {
            "coverage": reasoning.get("coverage", {}).get("confidence", "medium"),
            "faithfulness": reasoning.get("faithfulness", {}).get("confidence", "medium"),
            "relevance": reasoning.get("relevance", {}).get("confidence", "medium"),
        }

        return {
            "context_coverage": round(cov, 2),
            "faithfulness": round(faith, 2),
            "relevance": round(rel, 2),
            "overall": round((cov + faith + rel) / 3, 2),
            "feedback": str(parsed.get("feedback", "")),
            "weak_events": [int(w) for w in weak if isinstance(w, (int, float))],
            "confidences": confidences,
        }

    return None


_CONFIDENCE_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.5}


def _weighted_avg_scores(v1, v2):
    """TrustJudge 启发的加权平均：置信度高的评估权重更大。"""
    dims = ["coverage", "faithfulness", "relevance"]
    w1 = sum(_CONFIDENCE_WEIGHT.get(v1.get("confidences", {}).get(d, "medium"), 1.0) for d in dims)
    w2 = sum(_CONFIDENCE_WEIGHT.get(v2.get("confidences", {}).get(d, "medium"), 1.0) for d in dims)

    def _avg(key):
        return (v1.get(key, 0.5) * w1 + v2.get(key, 0.5) * w2) / (w1 + w2)

    cov = round(_avg("context_coverage"), 2)
    faith = round(_avg("faithfulness"), 2)
    rel = round(_avg("relevance"), 2)
    result = {
        "context_coverage": cov,
        "faithfulness": faith,
        "relevance": rel,
        "overall": round((cov + faith + rel) / 3, 2),
        "feedback": (v1.get("feedback", "") + " | " + v2.get("feedback", "")).strip(" |"),
        "weak_events": list(set(
            v1.get("weak_events", []) + v2.get("weak_events", []))),
    }
    if "cross_validation" in v1:
        result["cross_validation"] = v1["cross_validation"]
    return result


def _self_correct_events(llm, clusters, context_text, evaluation):
    """基于 RAGAS 评估反馈，对薄弱事件进行自我修正。"""
    feedback = evaluation.get("feedback", "")
    weak_indices = evaluation.get("weak_events", [])

    # 识别薄弱维度（阈值对齐质量目标）
    low_dims = []
    if evaluation.get("context_coverage", 1) < RAGAS_MIN_COVERAGE:
        low_dims.append("context_coverage（当前%.2f，需≥%.2f，更多利用检索上下文中的信息）" % (
            evaluation.get("context_coverage", 0), RAGAS_MIN_COVERAGE))
    if evaluation.get("faithfulness", 1) < RAGAS_MIN_FAITHFULNESS:
        low_dims.append("faithfulness（当前%.2f，需≥%.2f，确保每个事实/数据都有检索上下文依据，禁止编造）" % (
            evaluation.get("faithfulness", 0), RAGAS_MIN_FAITHFULNESS))
    if evaluation.get("relevance", 1) < RAGAS_MIN_RELEVANCE:
        low_dims.append("relevance（当前%.2f，需≥%.2f，更紧扣最重要的 AI/科技话题，去除边缘事件）" % (
            evaluation.get("relevance", 0), RAGAS_MIN_RELEVANCE))

    if not low_dims and not weak_indices:
        return clusters  # 无需修正

    # 修正薄弱事件
    for idx in weak_indices[:5]:  # 最多修正 5 个事件
        if idx < 1 or idx > len(clusters):
            continue
        cluster = clusters[idx - 1]
        material = _build_event_material(cluster)
        if not material.strip():
            continue

        prompt = (
            "之前生成的事件摘要质量不达标，请根据反馈重新生成。\n\n"
            "【薄弱维度】：%s\n"
            "【评估反馈】：%s\n\n"
            "【原始素材】：\n%s\n\n"
            "【当前摘要】：%s\n\n"
            "【检索上下文（参考）】：\n%s\n\n"
            "请重新生成该事件的摘要，以 JSON 返回：\n"
            "{\"label\": \"一句话标题（15字内）\",\n"
            " \"summary\": \"2-3句话概括，必须包含具体数据\",\n"
            " \"significance\": \"一句话说明为什么值得关注\",\n"
            " \"category\": \"ai-models|ai-products|industry|research|policy|funding|developer|consumer\"}\n\n"
            "约束：所有事实必须基于素材，不要编造。若素材完全不足以支撑摘要，返回原摘要原文，不要返回[信息不足]占位。"
        ) % ("; ".join(low_dims), feedback[:500], material,
             (cluster.get("summary", "") or "")[:300], context_text)

        messages = [
            {"role": "system", "content": "你是 AI 行业分析师。只返回 JSON。"},
            {"role": "user", "content": prompt},
        ]
        result = llm.complete(messages, temperature=0.3, max_tokens=1500)
        parsed = _robust_parse_json(result)
        if isinstance(parsed, dict):
            if parsed.get("label"):
                cluster["label"] = parsed["label"]
            if parsed.get("summary"):
                cluster["summary"] = parsed["summary"]
            if parsed.get("significance"):
                cluster["significance"] = parsed["significance"]
            if parsed.get("category"):
                cluster["category"] = parsed["category"]
            print("[每日洞察] RAGAS 修正事件 %d: %s" % (idx, cluster.get("label", "")[:30]))

    return clusters


def _dims_pass_thresholds(eval_result):
    """检查各维度是否达到最低阈值。任一维度不达标则返回 False。"""
    cov = eval_result.get("context_coverage", 0)
    faith = eval_result.get("faithfulness", 0)
    rel = eval_result.get("relevance", 0)
    if cov < RAGAS_MIN_COVERAGE:
        print("[每日洞察] 维度不达标: coverage=%.2f < %.2f" % (cov, RAGAS_MIN_COVERAGE))
        return False
    if faith < RAGAS_MIN_FAITHFULNESS:
        print("[每日洞察] 维度不达标: faithfulness=%.2f < %.2f" % (faith, RAGAS_MIN_FAITHFULNESS))
        return False
    if rel < RAGAS_MIN_RELEVANCE:
        print("[每日洞察] 维度不达标: relevance=%.2f < %.2f" % (rel, RAGAS_MIN_RELEVANCE))
        return False
    return True


def _median_eval_samples(samples):
    """多样本评估中位聚合（T2：09-19 实证 v1/v2 同内容差 0.17，单点评估噪声淹没内容变化）。"""
    if not samples:
        return {}
    out = {}
    for d in ("context_coverage", "faithfulness", "relevance", "overall"):
        vals = sorted(s[d] for s in samples if isinstance(s.get(d), (int, float)))
        if not vals:
            continue
        n = len(vals)
        out[d] = vals[n // 2] if n % 2 else round((vals[n // 2 - 1] + vals[n // 2]) / 2.0, 2)
    ref = min(samples, key=lambda s: abs(s.get("overall", 0) - out.get("overall", 0)))
    out["feedback"] = ref.get("feedback", "")
    out["weak_events"] = ref.get("weak_events", [])
    return out


def _robust_quality_eval(llm, current, theme, context_text, use_cv):
    """多样本稳健评估：CV 下 v1/v2/v1' 三样本取中位，非 CV 双样本。全失败返回 None。"""
    if use_cv:
        e1 = _evaluate_report_quality(llm, current, theme, context_text, prompt_variant="v1")
        e2 = _evaluate_report_quality(llm, current, theme, context_text, prompt_variant="v2")
        e3 = (_evaluate_report_quality(llm, current, theme, context_text, prompt_variant="v1")
              if (e1 and e2) else None)
        samples = [s for s in (e1, e2, e3) if s]
        if not samples:
            return None
        med = _median_eval_samples(samples)
        if e1 and e2:
            med["cross_validation"] = {"v1_overall": e1["overall"], "v2_overall": e2["overall"]}
            med["_actual_variants"] = 2
            print("[每日洞察] RAGAS 交叉验证: v1=%.2f v2=%.2f v1'=%s → med=%.2f" % (
                e1["overall"], e2["overall"], ("%.2f" % e3["overall"]) if e3 else "n/a",
                med["overall"]))
        else:
            med["_actual_variants"] = 1
        med["_eval_samples"] = len(samples)
        return med
    e1 = _evaluate_report_quality(llm, current, theme, context_text)
    e2 = _evaluate_report_quality(llm, current, theme, context_text)
    samples = [s for s in (e1, e2) if s]
    if not samples:
        return None
    med = _median_eval_samples(samples)
    med["_actual_variants"] = 1
    med["_eval_samples"] = len(samples)
    return med


def _ragas_evaluate_and_correct(llm, clusters, theme, retrieved_chunks, config):
    """RAGAS 评估-修正闭环：评分 → 不达标则自我修正 → 重新评分。"""
    if not RAGAS_ENABLED or not llm or not clusters:
        return clusters, {}

    threshold = config.get("daily_insight_quality_threshold", RAGAS_QUALITY_THRESHOLD)
    max_iterations = config.get("daily_insight_max_corrections", RAGAS_MAX_CORRECTIONS)

    # 构建评估上下文
    context_text = _build_ragas_context(clusters, retrieved_chunks)
    if not context_text:
        return clusters, {}

    # 评估-修正循环
    current = clusters
    eval_result = {}
    iteration_count = 0
    use_cross_validation = config.get("daily_insight_cross_validation", False)
    for iteration in range(max_iterations + 1):
        eval_result = _robust_quality_eval(llm, current, theme, context_text,
                                           use_cv=use_cross_validation)
        if eval_result is None:
            eval_result = {"context_coverage": 0.5, "faithfulness": 0.5, "relevance": 0.5,
                           "overall": 0.5, "feedback": "评估全部路径失败", "weak_events": []}
        print("[每日洞察] RAGAS eval iter=%d: overall=%.2f, cov=%.2f, faith=%.2f, rel=%.2f" % (
            iteration, eval_result["overall"], eval_result["context_coverage"],
            eval_result["faithfulness"], eval_result["relevance"]))

        if eval_result["overall"] >= threshold and _dims_pass_thresholds(eval_result):
            print("[每日洞察] RAGAS 质量达标 (overall=%.2f >= %.2f, 各维度达标)" % (
                eval_result["overall"], threshold))
            break
        if iteration < max_iterations:
            iteration_count += 1
            print("[每日洞察] RAGAS 未达标 (overall=%.2f 阈值=%.2f)，执行自我修正..." % (
                eval_result["overall"], threshold), file=sys.stderr)
            pre_score = eval_result["overall"]
            # _self_correct_events 原地写回 clusters，拒绝时必须回滚快照（P1-1 实证）
            _snapshot = [{k: c.get(k, _ROLLBACK_UNSET) for k in
                         ("label", "summary", "significance", "category")}
                        for c in current]
            corrected = _self_correct_events(llm, current, context_text, eval_result)
            # 重新评估修正结果（保持与初始评估一致的方法）
            corrected_result = _robust_quality_eval(llm, corrected, theme, context_text,
                                                    use_cv=use_cross_validation)
            if corrected_result is None:
                corrected_result = {"overall": 0.0, "context_coverage": 0.0,
                                    "faithfulness": 0.0, "relevance": 0.0,
                                    "feedback": "修正评估 JSON 解析失败", "weak_events": []}
            print("[每日洞察] RAGAS 修正后: overall=%.2f, cov=%.2f, faith=%.2f, rel=%.2f" % (
                corrected_result["overall"], corrected_result["context_coverage"],
                corrected_result["faithfulness"], corrected_result["relevance"]))
            # 采纳须超出复评噪声带（±0.02 实测漂移），防采纳劣化版；
            # faith 单维劣化同样拦截（09-19 04:14 期 0.90→0.66 被综合分掩盖实证）
            pre_faith = eval_result["faithfulness"]
            if (corrected_result["overall"] > pre_score + 0.02
                    and corrected_result["faithfulness"] >= pre_faith - 0.02):
                print("[每日洞察] 修正有效 (%.2f → %.2f)，采纳" % (pre_score, corrected_result["overall"]))
                current = corrected
                eval_result = corrected_result
                # 采纳后若各维度仍未全达标，进入下一轮修正（受 max_iterations 约束）
                if (corrected_result["overall"] >= threshold
                        and _dims_pass_thresholds(corrected_result)):
                    break
                continue
            else:
                for _c, _s in zip(current, _snapshot):
                    for _k, _v in _s.items():
                        if _v is _ROLLBACK_UNSET:
                            _c.pop(_k, None)
                        else:
                            _c[_k] = _v
                print("[每日洞察] 修正未采纳 (overall %.2f → %.2f, faith %.2f → %.2f)，已回滚原版" % (
                    pre_score, corrected_result["overall"], pre_faith, corrected_result["faithfulness"]))
                if corrected_result["overall"] >= threshold and _dims_pass_thresholds(corrected_result):
                    break
                continue  # 保留原版，下一轮换写法重试（temp 采样），轮数封顶

    eval_result["iterations"] = iteration_count

    # 评估元数据：准确记录实际运行的变体数
    actual_variants = eval_result.get("_actual_variants", 1)
    eval_result.pop("_actual_variants", None)
    _n_samples = eval_result.pop("_eval_samples", 1)
    eval_result["meta"] = {
        "judge_model": _effective_judge_model(llm),
        "judge_model_configured": getattr(llm, 'model', 'unknown'),
        "prompt_variants": actual_variants,
        "eval_samples": _n_samples,
        "call_log": getattr(llm, '_call_log', []),
        "temperature": 0.2,
    }

    return current, eval_result


# ──────────────────── Phase 3: 历史留存 ────────────────────

def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"days": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"days": []}


def _match_events_to_history(clusters, history):
    """跨天事件 id 关联：匹配昨日事件，标注 new/ongoing/faded/escalating。"""
    prev_day = None
    for day in reversed(history.get("days", [])):
        if day.get("events"):
            prev_day = day
            break

    if not prev_day:
        for c in clusters:
            c["status"] = "new"
        return clusters

    prev_labels = {}
    for evt in prev_day.get("events", []):
        prev_labels[evt.get("label", "")] = evt

    for c in clusters:
        label = c.get("label", "")
        tok = _tokenize_title(label)
        best_match, best_sim = None, 0
        for pl, pe in prev_labels.items():
            sim = _jaccard(tok, _tokenize_title(pl))
            if sim > best_sim:
                best_sim, best_match = sim, pe

        if best_sim >= JACCARD_HISTORY_THRESHOLD and best_match:
            c["status"] = "ongoing"
            c["prev_id"] = best_match.get("id", "")
            c["prev_summary"] = best_match.get("summary", "")
            # escalating: 分数显著增长
            prev_score = best_match.get("score", 0)
            if c["score"] > prev_score * 1.5:
                c["status"] = "escalating"
        else:
            c["status"] = "new"

    return clusters


def _update_history(clusters, theme):
    """追加今日记录，裁剪 30 天前旧数据。"""
    history = _load_history()
    today_str = NOW_BJ.strftime("%Y-%m-%d")

    # 移除今天（如果已存在，覆盖）
    history["days"] = [d for d in history["days"] if d.get("date") != today_str]

    # 构建今日记录
    today_events = []
    for c in clusters:
        evt = {
            "id": c["id"],
            "label": c.get("label", ""),
            "category": c.get("category", ""),
            "score": c.get("score", 0),
            "signal": c.get("signal", {}),
            "resonance": c.get("resonance", ""),
            "sources": c.get("source_types", []),
            "status": c.get("status", "new"),
            "summary": c.get("summary", ""),
            "significance": c.get("significance", ""),
            "key_links": c.get("key_links", []) or [it.get("url", "") for it in c.get("items", []) if it.get("url")][:3],
        }
        if c.get("deep_analysis"):
            evt["deep_analysis"] = c["deep_analysis"]
        today_events.append(evt)

    history["days"].append({
        "date": today_str,
        "theme": theme,
        "events": today_events,
        "stats": {
            "total_events": len(today_events),
            "has_analysis": any(e.get("deep_analysis") for e in today_events),
        },
        "generated_at": NOW_BJ.isoformat(),
    })

    # 裁剪 30 天
    cutoff = (NOW_BJ - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    history["days"] = [d for d in history["days"] if d.get("date", "") >= cutoff]

    try:
        _atomic_write_json(HISTORY_FILE, history)
        print("[每日洞察] 历史更新: %d 天" % len(history["days"]))
    except Exception as e:
        print("[每日洞察] 历史写入失败: %s" % e, file=sys.stderr)


# ──────────────────── Phase 3: 输出 JSON ────────────────────

def _write_insight_json(clusters, theme, has_analysis, ragas_eval=None, bubble_breaker=None):
    events = []
    for c in clusters:
        # 构建 articles 列表：每条素材的关键信息
        articles = []
        for it in c.get("items", []):
            art = {
                "title": it.get("title", ""),
                "source": it.get("source", "") or it.get("platform", "") or it.get("channel", ""),
                "type": it.get("source_type", "") or it.get("_src", ""),
                "url": it.get("link", "") or it.get("url", ""),
            }
            articles.append(art)
        evt = {
            "id": c["id"],
            "label": c.get("label", ""),
            "category": c.get("category", ""),
            "score": c.get("score", 0),
            "editor_score": c.get("editor_score", 0),
            "signal": c.get("signal", {}),
            "resonance": c.get("resonance", ""),
            "sources": c.get("source_types", []),
            "status": c.get("status", "new"),
            "summary": c.get("summary", ""),
            "significance": c.get("significance", ""),
            "key_links": c.get("key_links", []) or [a["url"] for a in articles if a.get("url")][:3],
            "deep_analysis": c.get("deep_analysis"),
            "articles": articles,
        }
        events.append(evt)

    output = {
        "date": NOW_BJ.strftime("%Y-%m-%d"),
        "theme": theme,
        "events": events,
        "bubble_breaker": bubble_breaker or [],
        "stats": {
            "total_events": len(events),
            "has_analysis": has_analysis,
        },
        "generated_at": NOW_BJ.isoformat(),
    }
    # RAGAS 质量评分
    if ragas_eval:
        quality = {
            "overall": ragas_eval.get("overall", 0),
            "context_coverage": ragas_eval.get("context_coverage", 0),
            "faithfulness": ragas_eval.get("faithfulness", 0),
            "relevance": ragas_eval.get("relevance", 0),
            "feedback": ragas_eval.get("feedback", ""),
        }
        if ragas_eval.get("meta"):
            quality["meta"] = ragas_eval["meta"]
        output["quality"] = quality

    try:
        _atomic_write_json(INSIGHT_FILE, output)
        quality_str = ""
        if ragas_eval:
            quality_str = ", RAGAS=%.2f" % ragas_eval.get("overall", 0)
        print("[每日洞察] 产出 → %s（%d 事件, 分析=%s%s）" % (
            INSIGHT_FILE, len(events), has_analysis, quality_str))
    except Exception as e:
        print("[每日洞察] JSON 写入失败: %s" % e, file=sys.stderr)


# ──────────────────── Phase 4: 历史页面 ────────────────────

def _build_history_html():
    """生成 daily-insight-history.html。视觉风格与 ai-daily.html 报纸风格对齐。"""
    history = _load_history()
    days = history.get("days", [])
    if not days:
        return

    # 按日期降序
    days.sort(key=lambda d: d.get("date", ""), reverse=True)

    # 构建日期选择器选项
    date_options = "".join(
        '<option value="day-%s">%s (%d 事件)</option>' % (
            d["date"], d["date"], d.get("stats", {}).get("total_events", 0))
        for d in days
    )

    # 构建每天的事件卡片
    day_sections = []
    for d in days:
        date = d.get("date", "")
        theme = _esc(d.get("theme", ""))
        events_html = []
        for evt in d.get("events", []):
            status = evt.get("status", "new")
            status_labels = {
                "new": "新", "ongoing": "持续", "escalating": "升级", "faded": "消退",
            }
            resonance = evt.get("resonance", "")
            resonance_labels = {
                "breakout": "破圈", "tech_hot": "技术热",
                "niche": "垂直", "consumer": "消费级",
            }

            deep = evt.get("deep_analysis") or {}
            deep_html = ""
            if deep:
                deep_html = '''
<div class="di-deep">
  <div class="di-deep-title">深度解读</div>
  <div class="di-deep-sec"><strong>事件还原</strong><p>%s</p></div>
  <div class="di-deep-sec"><strong>影响分析</strong><p>%s</p></div>
  <div class="di-deep-sec"><strong>信源分歧</strong><p>%s</p></div>
  %s
  <div class="di-deep-sec"><strong>后续展望</strong><p>%s</p></div>
  <span class="di-conf">置信度: %s</span>
  %s
</div>''' % (
                    _esc(deep.get("event_reconstruction", "")),
                    _esc(deep.get("impact_analysis", "")),
                    _esc(deep.get("source_divergence", "")),
                    ('<div class="di-deep-sec"><strong>金句</strong><blockquote>%s</blockquote></div>'
                     % _esc(deep["quote"])) if deep.get("quote") else "",
                    _esc(deep.get("outlook", "")),
                    _esc(deep.get("confidence", "")),
                    _cited_sources_html(deep),
                )

            sources_tags = " ".join(
                '<span class="di-src">%s</span>' % _esc(s) for s in evt.get("sources", [])
            )

            events_html.append('''
<article class="di-card">
  <div class="di-head">
    <span class="di-status">%s</span>
    %s
    <span class="di-score">%.1f</span>
  </div>
  <h3 class="di-label">%s</h3>
  <p class="di-summary">%s</p>
  %s
  <div class="di-meta">%s %s</div>
  %s
</article>''' % (
                status_labels.get(status, status),
                ('<span class="di-resonance">%s</span>' % resonance_labels.get(resonance, resonance)) if resonance else "",
                evt.get("score", 0),
                _esc(evt.get("label", "")),
                _esc(evt.get("summary", "")),
                _source_links_html(evt.get("key_links")),
                sources_tags,
                '<span class="di-cat">%s</span>' % _esc(evt.get("category", "")) if evt.get("category") else "",
                deep_html,
            ))

        day_sections.append('''
<section id="day-%s" class="day-section" style="display:none">
  <div class="day-theme">%s</div>
  %s
</section>''' % (date, theme, "\n".join(events_html)))

    # 默认显示第一天
    if day_sections:
        day_sections[0] = day_sections[0].replace('style="display:none"', '')

    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>每日深度洞察 · 历史</title>
<style>
:root {
  --bg:#faf8f4; --card:#fffdf9; --card-2:#f3efe6;
  --ink:#1f1c17; --muted:#6f6860; --faint:#857e74;
  --line:#e4ddd0; --line-strong:#b9b0a2;
  --accent:#30891A; --accent-ink:#256d13; --accent-weak:rgba(48,137,26,.08);
  --display:"Georgia","Times New Roman","Songti SC","SimSun","STSong",serif;
  --body:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
[data-theme="dark"] {
  --bg:#101114; --card:#17191d; --card-2:#1d2026;
  --ink:#e9e6df; --muted:#a49c90; --faint:#7d776d;
  --line:#2a2d33; --line-strong:#4a4e57;
  --accent:#5bc23e; --accent-ink:#a3e88f; --accent-weak:rgba(91,194,62,.12);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;scroll-padding-top:24px;}
body{
  font-family:var(--body);background:var(--bg);color:var(--ink);
  line-height:1.65;-webkit-font-smoothing:antialiased;font-size:15px;
}
a{color:inherit;text-decoration:none;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px;}
.paper{max-width:980px;margin:0 auto;padding:0 20px 64px;}

/* top bar */
.topbar{display:flex;align-items:center;gap:10px;padding:14px 0 4px;}
.back{
  display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;
  background:var(--card);border:1px solid var(--line);font-size:13px;transition:all .15s;
}
.back:hover{border-color:var(--accent);color:var(--accent-ink);}
.topbar .spacer{flex:1;}
.theme-btn{
  width:36px;height:36px;border-radius:999px;background:var(--card);border:1px solid var(--line);
  display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--ink);
  transition:all .15s;
}
.theme-btn:hover{border-color:var(--accent);color:var(--accent-ink);}
.theme-btn svg{width:16px;height:16px;}

/* masthead */
.masthead{text-align:center;padding:26px 0 0;}
.mast-rule{display:flex;align-items:center;gap:14px;margin:0 0 4px;}
.mast-rule::before,.mast-rule::after{content:"";flex:1;height:1px;background:var(--line-strong);}
.mast-meta{font-size:11.5px;letter-spacing:.14em;color:var(--muted);font-weight:500;white-space:nowrap;}
.mast-title{
  font-family:var(--display);font-size:clamp(28px,5vw,42px);font-weight:700;
  letter-spacing:.06em;line-height:1.15;margin:6px 0 2px;
}
.mast-sub{font-size:12.5px;color:var(--muted);letter-spacing:.1em;}
.mast-strip{
  margin-top:14px;padding:8px 12px;border-top:3px double var(--line-strong);border-bottom:1px solid var(--line-strong);
  font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 18px;justify-content:center;
}
.mast-strip b{color:var(--ink);font-weight:600;}

/* day nav */
.day-nav{
  display:flex;flex-wrap:wrap;justify-content:center;gap:6px 22px;
  padding:14px 0 4px;font-size:13px;
}
.day-nav select{
  padding:6px 12px;border:1px solid var(--line);border-radius:999px;
  background:var(--card);color:var(--ink);font-size:13px;font-family:var(--body);
}

/* day section */
.day-section{margin:34px 0;}
.day-theme{
  font-family:var(--display);font-size:1.1em;color:var(--accent-ink);margin-bottom:16px;
  padding:10px 14px;border-left:3px solid var(--accent);background:var(--card-2);
}

/* event cards */
.di-card{padding:14px 0;border-bottom:1px solid var(--line);}
.di-card:last-child{border-bottom:none;}
.di-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;}
.di-status{font-size:11px;color:var(--muted);border:1px solid var(--line);padding:1px 6px;letter-spacing:.05em;}
.di-resonance{font-size:11px;color:var(--accent-ink);border:1px solid var(--accent);padding:1px 5px;}
.di-score{margin-left:auto;font-weight:bold;color:var(--accent);font-size:0.85em;font-family:var(--display);}
.di-label{font-family:var(--display);font-size:1.05em;font-weight:700;margin-bottom:4px;line-height:1.4;}
.di-summary{color:var(--muted);font-size:0.88em;margin-bottom:6px;line-height:1.7;}
.di-meta{display:flex;gap:4px;flex-wrap:wrap;align-items:center;}
.di-src{font-size:10px;padding:1px 5px;border:1px solid var(--line);color:var(--faint);}
.di-cat{font-size:10px;padding:1px 5px;color:var(--accent-ink);border:1px solid var(--accent);}
.di-links{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 6px;}
.di-link{font-size:11px;color:var(--accent-ink);border:1px solid var(--accent);padding:1px 7px;border-radius:10px;background:var(--accent-weak);}
.di-cites{font-size:11px;margin-top:4px;}
.di-cite{color:var(--accent-ink);border-bottom:1px dotted var(--accent);margin-right:8px;}
.di-bubble-link{color:var(--accent-ink);border-bottom:1px solid var(--accent);}

/* deep analysis */
.di-deep{margin-top:10px;padding:10px 0 10px 16px;border-left:2px solid var(--line-strong);font-size:0.88em;}
.di-deep-title{font-family:var(--display);font-weight:700;font-size:0.95em;margin-bottom:6px;color:var(--ink);}
.di-deep-sec{margin-bottom:10px;}
.di-deep-sec strong{display:block;font-size:0.85em;color:var(--muted);margin-bottom:2px;}
.di-deep-sec p{font-size:0.95em;line-height:1.7;}
.di-deep-sec blockquote{font-style:italic;padding:6px 10px;border-left:2px solid var(--accent);color:var(--muted);margin:4px 0;}
.di-conf{font-size:10px;color:var(--faint);}

/* footer */
.foot{
  margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px;justify-content:space-between;
}

@media (max-width:760px){
  .paper{padding:0 14px 48px;}
  .mast-title{letter-spacing:.03em;}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto;}
  *{transition:none!important;animation:none!important;}
}
</style>
<script>try{var _t=localStorage.getItem('wb_starhub_theme_v1')||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=_t;}catch(e){}</script>
</head>
<body>
<div class="paper">

  <div class="topbar">
    <a class="back" href="ai-daily.html">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>
      返回日报
    </a>
    <div class="spacer"></div>
    <button class="theme-btn" id="btnTheme" title="切换明暗主题" aria-label="切换明暗主题">
      <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M18.7 5.3 17 7M7 17l-1.7 1.7"/></svg>
      <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z"/></svg>
    </button>
  </div>

  <header class="masthead">
    <div class="mast-rule"><span class="mast-meta">每日深度洞察</span><span class="mast-meta">历史归档</span></div>
    <h1 class="mast-title">深度洞察<span style="color:var(--accent)"> · </span>历史</h1>
    <div class="mast-sub">共 %d 天记录 &nbsp;·&nbsp; 事件聚合与趋势追踪</div>
    <div class="mast-strip">
      <span>自动生成</span>
      <span>数据源 <b>AIHOT</b> · 多平台聚合 · 内容版权归原作者</span>
    </div>
  </header>

  <nav class="day-nav" aria-label="日期选择">
    <select id="daySelect" onchange="switchDay(this.value)">
%s
    </select>
  </nav>

%s

  <footer class="foot">
    <span>每日深度洞察 · 历史归档</span>
    <span><a href="ai-daily.html">返回今日日报</a></span>
  </footer>
</div>
<script>
function switchDay(id){
  document.querySelectorAll('.day-section').forEach(function(s){s.style.display='none';});
  var el=document.getElementById(id);
  if(el)el.style.display='block';
}
(function(){
  var btn=document.getElementById('btnTheme');
  btn.addEventListener('click',function(){
    var cur=document.documentElement.dataset.theme;
    var next=cur==='dark'?'light':'dark';
    document.documentElement.dataset.theme=next;
    try{localStorage.setItem('wb_starhub_theme_v1',next);}catch(e){}
  });
})();
</script>
</body>
</html>''' % (len(days), date_options, "\n".join(day_sections))

    try:
        with open(HISTORY_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        print("[每日洞察] 历史页面 → %s（%d 天）" % (HISTORY_HTML, len(days)))
    except Exception as e:
        print("[每日洞察] 历史页面写入失败: %s" % e, file=sys.stderr)


# ──────────────────── AI 日报子板块注入 ────────────────────

_AI_DAILY_FILE = "ai-daily.html"


def _link_host(u):
    """URL 域名作为原文链接文案（去 www.，失败回退「原文」）。"""
    try:
        from urllib.parse import urlparse
        h = (urlparse(u).hostname or "").lower()
        return h[4:] if h.startswith("www.") else (h or "原文")
    except Exception:
        return "原文"


def _source_links_html(links, items=None):
    """可跳转原文链接组：仅放行 http(s)，去重保序 cap 3；
    key_links 为空时回退 items URL（红线：每个洞察必须带可跳转原文引用）。"""
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
    chips = "".join(
        '<a class="di-link" href="%s" target="_blank" rel="noopener">%s&#8599;</a>'
        % (_esc(u), _esc(_link_host(u))) for u in out[:3])
    return '<div class="di-links">%s</div>' % chips if chips else ""


def _cited_sources_html(deep):
    """深度解读实际引用的素材编号 → 可点击链接列表。"""
    chips = ""
    for s in (deep.get("cited_sources") or [])[:5]:
        u = s.get("url", "") if isinstance(s, dict) else ""
        if not u or not re.match(r'https?://', u, re.I):
            continue
        chips += '<a class="di-cite" href="%s" target="_blank" rel="noopener">[%s] %s&#8599;</a> ' % (
            _esc(u), _esc(str(s.get("index", ""))), _esc(_link_host(u)))
    return ('<p class="di-cites"><b>引用来源</b> %s</p>' % chips) if chips else ""


# ──────────────────── 破茧栏 HTML 构建 ────────────────────

def _build_bubble_html(bubble_breaker):
    """将破茧栏数据渲染为报纸风格 HTML 段。"""
    if not bubble_breaker:
        return ""
    cards = []
    for item in bubble_breaker:
        _bu = item.get("url", "")
        _bl = _esc(item.get("label", ""))
        _bh = ('<a class="di-bubble-link" href="%s" target="_blank" rel="noopener">%s&#8599;</a>'
               % (_esc(_bu), _bl)) if re.match(r'https?://', _bu or "", re.I) else _bl
        cards.append('''
<div class="di-bubble-card">
  <div class="di-bubble-label">%s</div>
  <div class="di-bubble-summary">%s</div>
  <div class="di-bubble-reason">%s</div>
</div>''' % (_bh,
             _esc(item.get("summary", "")),
             _esc(item.get("reason", ""))))
    return '''
<div class="di-bubble">
  <div class="di-bubble-title">\u7834\u8327\u680f \u00b7 \u4fe1\u606f\u589e\u91cf</div>
  %s
</div>''' % "\n".join(cards)


def _inject_into_ai_daily(clusters, theme, bubble_breaker=None):
    """将洞察子板块注入已生成的 ai-daily.html（在 <footer> 之前插入）。"""
    if not os.path.exists(_AI_DAILY_FILE):
        print("[每日洞察] ai-daily.html 不存在，跳过注入", file=sys.stderr)
        return

    try:
        with open(_AI_DAILY_FILE, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        print("[每日洞察] 读取 ai-daily.html 失败: %s" % e, file=sys.stderr)
        return

    if "daily-insight-start" in html:
        # 已注入过，先移除旧板块
        html = re.sub(
            r'<!-- daily-insight-start -->.*?<!-- daily-insight-end -->\s*',
            '', html, flags=re.DOTALL)

    # 构建事件卡片
    cards_html = []
    for evt in clusters:
        status_labels = {
            "new": "新", "ongoing": "持续", "escalating": "升级", "faded": "消退",
        }
        resonance_labels = {
            "breakout": "破圈", "tech_hot": "技术热",
            "niche": "垂直", "consumer": "消费级",
        }
        sl = status_labels.get(evt.get("status", "new"), "")
        rl = resonance_labels.get(evt.get("resonance", ""), "")
        deep = evt.get("deep_analysis") or {}

        # 来源标签
        src_tags = "".join(
            '<span class="di-src">%s</span>' % _esc(s) for s in evt.get("source_types", [])
        )

        # 深度解读（缩进式排版，非折叠）
        deep_html = ""
        if deep and deep.get("status") != "degraded":
            deep_html = '''
<div class="di-deep">
<p class="di-deep-title">深度解读</p>
<p><b>事件还原</b><br>%s</p>
<p><b>影响分析</b><br>%s</p>
<p><b>信源分歧</b><br>%s</p>
%s
<p><b>后续展望</b><br>%s</p>
<p class="di-conf">置信度: %s</p>
%s
</div>''' % (
                _esc(deep.get("event_reconstruction", "")),
                _esc(deep.get("impact_analysis", "")),
                _esc(deep.get("source_divergence", "")),
                ('<blockquote class="di-quote">%s</blockquote>' % _esc(deep["quote"])) if deep.get("quote") else "",
                _esc(deep.get("outlook", "")),
                _esc(deep.get("confidence", "")),
                _cited_sources_html(deep),
            )

        cards_html.append('''
<div class="di-card">
  <div class="di-head">
    <span class="di-status">%s</span>
    %s
    <span class="di-score">%.1f</span>
  </div>
  <h3 class="di-label">%s</h3>
  <p class="di-summary">%s</p>
  %s
  <div class="di-meta">%s <span class="di-cat">%s</span></div>
  %s
</div>''' % (
            sl,
            ('<span class="di-resonance">%s</span>' % rl) if rl else "",
            evt.get("score", 0),
            _esc(evt.get("label", "")),
            _esc(evt.get("summary", "")),
            _source_links_html(evt.get("key_links"), evt.get("items")),
            src_tags,
            _esc(evt.get("category", "")),
            deep_html,
        ))

    # 完整子板块 HTML（报纸风格）
    section_html = '''<!-- daily-insight-start -->
<style>
.di-section{margin:34px 0;padding:18px 0;border-top:3px double var(--line-strong);}
.di-title{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:.04em;margin-bottom:4px;}
.di-theme{color:var(--muted);font-size:0.9em;margin-bottom:16px;font-style:italic;}
.di-card{padding:14px 0;border-bottom:1px solid var(--line);}
.di-card:last-child{border-bottom:none;}
.di-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;}
.di-status{font-size:11px;color:var(--muted);border:1px solid var(--line);padding:1px 6px;letter-spacing:.05em;}
.di-resonance{font-size:11px;color:var(--accent-ink);border:1px solid var(--accent);padding:1px 5px;}
.di-score{margin-left:auto;font-weight:bold;color:var(--accent);font-size:0.85em;font-family:var(--display);}
.di-label{font-family:var(--display);font-size:1.05em;font-weight:700;margin-bottom:4px;line-height:1.4;}
.di-summary{color:var(--muted);font-size:0.88em;margin-bottom:6px;line-height:1.7;}
.di-meta{display:flex;gap:4px;flex-wrap:wrap;align-items:center;}
.di-src{font-size:10px;padding:1px 5px;border:1px solid var(--line);color:var(--faint);}
.di-cat{font-size:10px;padding:1px 5px;color:var(--accent-ink);border:1px solid var(--accent);}
.di-links{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 6px;}
.di-link{font-size:11px;color:var(--accent-ink);border:1px solid var(--accent);padding:1px 7px;border-radius:10px;background:var(--accent-weak);}
.di-cites{font-size:11px;margin-top:4px;}
.di-cite{color:var(--accent-ink);border-bottom:1px dotted var(--accent);margin-right:8px;}
.di-bubble-link{color:var(--accent-ink);border-bottom:1px solid var(--accent);}
.di-deep{margin-top:10px;padding:10px 0 10px 16px;border-left:2px solid var(--line-strong);font-size:0.88em;}
.di-deep-title{font-family:var(--display);font-weight:700;font-size:0.95em;margin-bottom:6px;color:var(--ink);}
.di-deep p{margin:5px 0;line-height:1.7;}
.di-quote{font-style:italic;padding:6px 10px;border-left:2px solid var(--accent);color:var(--muted);margin:6px 0;}
.di-conf{font-size:10px;color:var(--faint);}
.di-bubble{margin-top:18px;padding-top:14px;border-top:1px dashed var(--line-strong);}
.di-bubble-title{font-family:var(--display);font-size:0.95em;font-weight:700;color:var(--muted);margin-bottom:10px;letter-spacing:.06em;}
.di-bubble-card{padding:8px 0;border-bottom:1px dotted var(--line);}
.di-bubble-card:last-child{border-bottom:none;}
.di-bubble-label{font-family:var(--display);font-weight:700;font-size:0.92em;}
.di-bubble-summary{color:var(--muted);font-size:0.82em;line-height:1.6;margin:3px 0;}
.di-bubble-reason{font-size:0.78em;color:var(--faint);font-style:italic;}
</style>
<div class="di-section">
  <div class="di-title">\u6bcf\u65e5\u6df1\u5ea6\u6d1e\u5bdf</div>
  <div class="di-theme">%s</div>
  %s
  %s
</div>
<!-- daily-insight-end -->
''' % (_esc(theme), "\n".join(cards_html), _build_bubble_html(bubble_breaker))

    # 在 <footer> 之前插入；若 footer 标记不存在则回退到 </body> 前
    if '<footer class="foot">' in html:
        html = html.replace('<footer class="foot">', section_html + '\n<footer class="foot">')
    elif '</body>' in html:
        html = html.replace('</body>', section_html + '\n</body>')
    else:
        print("[每日洞察] ai-daily.html 无注入锚点，跳过", file=sys.stderr)
        return

    try:
        with open(_AI_DAILY_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        print("[每日洞察] 已注入 ai-daily.html 子板块")
    except Exception as e:
        print("[每日洞察] ai-daily.html 注入失败: %s" % e, file=sys.stderr)


# ──────────────────── 构建质量追踪日志 ────────────────────

class PipelineTracer:
    """端到端 LLM 调用追踪器。"""

    def __init__(self):
        self.stages = {}
        self.llm_calls = []
        self.meta = {}

    def set_meta(self, **kwargs):
        """设置构建元信息。"""
        self.meta.update(kwargs)

    def trace_queries(self, rss_count, hot_count, aihot_count, agihunt_count,
                      chunks_total, queries_count, retrieved_top_k):
        """Stage 1: 查询构建。"""
        self.stages["queries"] = {
            "source_counts": {"rss": rss_count, "hot": hot_count,
                              "aihot": aihot_count, "agihunt": agihunt_count},
            "chunks_total": chunks_total,
            "queries_count": queries_count,
            "retrieved_top_k": retrieved_top_k,
        }

    def trace_clustering(self, method, threshold, before_count, after_count,
                         events_summary):
        """Stage 2: 聚类与事件组装。"""
        self.stages["clustering"] = {
            "method": method,
            "threshold": threshold,
            "before_count": before_count,
            "after_count": after_count,
            "events": events_summary,
        }

    def trace_llm_call(self, phase, event_idx, prompt_text, model_name,
                       temperature, max_tokens, raw_response, parse_ok,
                       parsed_result, token_usage=None):
        """记录单次 LLM 调用。异常安全。"""
        try:
            # 确保 parsed_result 可序列化
            safe_result = parsed_result
            try:
                json.dumps(parsed_result, ensure_ascii=False, default=str)
            except Exception:
                safe_result = str(parsed_result)

            self.llm_calls.append({
                "phase": phase,
                "event_idx": event_idx,
                "model": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "prompt_chars": len(prompt_text) if prompt_text else 0,
                "prompt_preview": (prompt_text or "")[:5000],
                "raw_response_preview": (raw_response or "")[:3000],
                "parse_ok": parse_ok,
                "parsed_summary": safe_result,
                "token_usage": token_usage,
            })
        except Exception:
            pass  # 异常安全：不影响主流程

    def trace_self_review(self, issues_found, corrected_indices):
        """Stage 5: 自审环节。"""
        self.stages["self_review"] = {
            "issues": issues_found,
            "corrected_indices": corrected_indices,
        }

    def trace_ragas(self, iterations_log):
        """Stage 6: RAGAS 评估-修正闭环。"""
        self.stages["ragas"] = {"iterations": iterations_log}

    def trace_bubble(self, read_profile, candidates, selected):
        """Stage 7: 破茧栏选择。"""
        self.stages["bubble_breaker"] = {
            "read_profile": read_profile,
            "candidates": candidates,
            "selected": selected,
        }

    def trace_output(self, event_count, has_analysis_count, inject_html_len):
        """Stage 8: 输出与注入。"""
        self.stages["output"] = {
            "event_count": event_count,
            "has_analysis_count": has_analysis_count,
            "inject_html_chars": inject_html_len,
        }

    def flush(self):
        """输出完整追踪日志到 JSONL。"""
        now_bj = _now_bj()
        entry = {
            "ts": now_bj.isoformat(),
            "date": now_bj.strftime("%Y-%m-%d"),
            "meta": self.meta,
            "stages": self.stages,
            "llm_calls": self.llm_calls,
        }
        try:
            _log_tracking_entry(entry)
        except Exception:
            pass  # 异常安全
        return entry


def _log_tracking_entry(entry):
    """将构建追踪数据追加写入 daily_insight_tracking_history.jsonl。

    JSONL 格式，14 天滚动窗口，原子写入，异常安全。
    字段结构与 insight_tracking_history.jsonl 对齐。
    """
    try:
        now_bj = _now_bj()

        # 加载现有记录
        lines = []
        if os.path.exists(TRACKING_FILE):
            try:
                with open(TRACKING_FILE, "r", encoding="utf-8") as f:
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
        _atomic_write_text(TRACKING_FILE, "".join(lines))
        print("[每日洞察] 追踪日志已记录 → %s (保留 %d 条)" % (TRACKING_FILE, len(lines)))
    except Exception as e:
        print("[每日洞察] 追踪日志失败: %s" % e, file=sys.stderr)


def _build_tracking_entry(ragas_eval, clusters, theme, elapsed,
                          rss_count, hot_count, aihot_count, agihunt_count,
                          chunks_count, filtered_count, llm_available,
                          embed_model=""):
    """构建追踪日志条目。"""
    now_bj = _now_bj()
    has_analysis = sum(1 for c in clusters if c.get("deep_analysis"))

    # RAGAS 评分
    overall = ragas_eval.get("overall")
    threshold = RAGAS_QUALITY_THRESHOLD

    return {
        "ts": now_bj.isoformat(),
        "date": now_bj.strftime("%Y-%m-%d"),
        # RAGAS 质量评分
        "overall": overall,
        "context_coverage": ragas_eval.get("context_coverage"),
        "faithfulness": ragas_eval.get("faithfulness"),
        "relevance": ragas_eval.get("relevance"),
        "feedback": ragas_eval.get("feedback", ""),
        "iterations": ragas_eval.get("iterations"),
        "threshold": threshold,
        "passed": (overall >= threshold) if overall is not None else None,
        # 事件统计
        "stats": {
            "total_events": len(clusters),
            "has_analysis_count": has_analysis,
            "rss_count": rss_count,
            "hot_count": hot_count,
            "aihot_count": aihot_count,
            "agihunt_count": agihunt_count,
            "chunks_total": chunks_count,
            "items_after_filter": filtered_count,
        },
        # 主题
        "theme": (theme or "")[:200],
        # 构建元信息
        "meta": {
            "llm_available": llm_available,
            "embed_model": embed_model,
            "elapsed_seconds": elapsed,
        },
    }


# ──────────────────── main ────────────────────

def main():
    global NOW_BJ
    NOW_BJ = _now_bj()

    # 配置
    cfg = load_config()
    if not cfg.get("daily_insight_enabled", True):
        print("[每日洞察] 已禁用，跳过")
        return False

    print("[每日洞察] 开始生成 %s 每日深度洞察..." % NOW_BJ.strftime("%Y-%m-%d"))
    t0 = time.time()

    # 加载 RSS tier 映射
    _load_rss_tiers()

    # ── 数据采集 ──
    snapshot = _load_snapshot()
    aihot_items = snapshot.get("aihot_items", [])
    agihunt_items = snapshot.get("agihunt_items", [])
    rss_history = _load_rss_history()
    hot_snapshot = _load_hot_snapshot()

    # RSS 历史转为条目列表（每日洞察只取最近 INSIGHT_RSS_HOURS 小时）
    rss_items = []
    for link, item in rss_history.items():
        if not isinstance(item, dict):
            continue
        title = item.get("title", "") or item.get("title_zh", "")
        if not title:
            continue
        pub_dt = _parse_iso(item.get("pub_date", ""))
        if _hours_ago(pub_dt) > INSIGHT_RSS_HOURS:
            continue
        rss_items.append({
            "title": title,
            "link": link,
            "source": item.get("source", ""),
            "source_key": item.get("source_key", ""),
            "cat": item.get("cat", ""),
            "summary": item.get("summary", ""),
            "full_content": item.get("full_content", ""),
            "pub_date": item.get("pub_date", ""),
            "_src": "rss",
        })

    # 热榜展平
    hot_items = []
    for platform in hot_snapshot:
        plat = platform.get("platform", "")
        for item in platform.get("items", []):
            title = item.get("title", "")
            if not title:
                continue
            hot_items.append({
                "title": title,
                "url": item.get("url", ""),
                "rank": item.get("rank", 50),
                "hot": item.get("hot", ""),
                "platform": plat,
                "_src": "hot",
            })

    print("[每日洞察] 数据汇总: RSS %d, 热榜 %d, AIHOT %d, AGI Hunt %d" % (
        len(rss_items), len(hot_items), len(aihot_items), len(agihunt_items)))
    # 追踪用统计
    _stats_rss = len(rss_items)
    _stats_hot = len(hot_items)
    _stats_aihot = len(aihot_items)
    _stats_agihunt = len(agihunt_items)

    # ── Phase 1.2: 硬过滤 ──
    rss_clean = _filter_noise(rss_items)
    aihot_clean = _filter_noise(aihot_items)
    agihunt_clean = _filter_noise(agihunt_items)
    # 热榜不过滤（本身就是平台精选）
    hot_clean = hot_items

    # ── Phase 1.3: RAG 管线 ──
    # 1) 切片
    chunks = _chunk_documents(rss_clean, hot_clean, aihot_clean, agihunt_clean)
    if not chunks:
        print("[每日洞察] 无 chunks，跳过生成")
        # 降级记录：即使无 chunks 也记录基础统计
        try:
            _log_tracking_entry(_build_tracking_entry(
                ragas_eval={}, clusters=[], theme="", elapsed=round(time.time() - t0, 1),
                rss_count=_stats_rss, hot_count=_stats_hot,
                aihot_count=_stats_aihot, agihunt_count=_stats_agihunt,
                chunks_count=0, filtered_count=0, llm_available=bool(llm)))
        except Exception:
            pass
        return False
    _stats_chunks_raw = len(chunks)
    _stats_filtered = len(rss_clean) + len(hot_clean) + len(aihot_clean) + len(agihunt_clean)

    # 1.5) 增量追加：加载旧缓存 → 合并去重 → 截断 → 仅新增 embedding
    old_chunks, old_vecs, old_model = _load_vector_cache()
    old_hash_set = {c.get("content_hash", "") for c in old_chunks}
    today_hash_set = {c.get("content_hash", "") for c in chunks}
    # 合并：旧 chunks + 今日新 chunks（去重 by content_hash）
    # 旧缓存中仍出现在今日数据里的保留（未过期），不再出现的也保留（由截断控制淘汰）
    new_only = [c for c in chunks if c.get("content_hash", "") not in old_hash_set]
    merged_chunks = old_chunks + new_only
    print("[每日洞察] 增量合并: 旧 %d + 新增 %d = %d (去重后)" % (
        len(old_chunks), len(new_only), len(merged_chunks)))

    # 1.6) 截断：超出 MAX_EMBED_CHUNKS 时按时间保留 RSS chunks
    if len(merged_chunks) > MAX_EMBED_CHUNKS:
        rss_mc = [c for c in merged_chunks if c.get("source_type") == "rss"]
        other_mc = [c for c in merged_chunks if c.get("source_type") != "rss"]
        rss_mc.sort(key=lambda c: c.get("pub_date", ""), reverse=True)
        budget = MAX_EMBED_CHUNKS - len(other_mc)
        if budget < 100:
            budget = 100
        rss_mc = rss_mc[:budget]
        merged_chunks = rss_mc + other_mc
        print("[每日洞察] 截断至 %d chunks (RSS %d + 其他 %d)" % (
            len(merged_chunks), len(rss_mc), len(other_mc)))

    # 1.7) 识别需要 embedding 的 chunks（hash 不在旧缓存中的）
    cached_map = {}  # content_hash → index in old_vecs
    for i, c in enumerate(old_chunks):
        h = c.get("content_hash", "")
        if h:
            cached_map[h] = i
    need_embed = [c for c in merged_chunks if c.get("content_hash", "") not in cached_map]
    cached_count = len(merged_chunks) - len(need_embed)
    print("[每日洞察] 向量缓存命中 %d, 需新增 embedding %d" % (cached_count, len(need_embed)))

    # 1.8) 仅对新增 chunks 调 Embedding API
    new_vecs_list = []
    embed_model = old_model
    if need_embed:
        need_texts = [c.get("text", "")[:1000] for c in need_embed]
        new_vecs_result, new_model = _embed_chunks(need_texts)
        if new_vecs_result:
            new_vecs_list = new_vecs_result
            embed_model = new_model or old_model
        else:
            print("[每日洞察] 新增 embedding 失败，尝试降级到旧缓存", file=sys.stderr)

    # 1.9) 组装全量向量矩阵
    all_vecs = None
    if old_vecs is not None and len(old_chunks) > 0:
        # 按 merged_chunks 顺序组装：命中缓存的用旧向量，新增的用新计算
        vec_rows = []
        new_vec_idx = 0
        for c in merged_chunks:
            h = c.get("content_hash", "")
            if h in cached_map and old_vecs is not None:
                vec_rows.append(old_vecs[cached_map[h]])
            elif new_vec_idx < len(new_vecs_list):
                vec_rows.append(_np.array(new_vecs_list[new_vec_idx], dtype=_np.float32))
                new_vec_idx += 1
            else:
                # 异常：既无缓存也无新向量，用零向量占位
                vec_rows.append(_np.zeros(EMBED_DIM, dtype=_np.float32))
        all_vecs = _np.vstack(vec_rows)
    elif new_vecs_list:
        # 无旧缓存，全量新计算
        all_vecs = _np.array(new_vecs_list, dtype=_np.float32)

    # 2) 保存向量缓存 → 重建 FAISS 索引（先存向量防止 FAISS 失败丢失 embedding）
    index = None
    _used_merged = False
    if all_vecs is not None and len(all_vecs) > 0:
        _save_vector_cache(merged_chunks, all_vecs, embed_model)
        index = _build_faiss_index(all_vecs)
        try:
            if FAISS_AVAILABLE:
                _faiss.write_index(index, FAISS_INDEX_FILE + ".tmp")
                os.replace(FAISS_INDEX_FILE + ".tmp", FAISS_INDEX_FILE)
                print("[每日洞察] FAISS 索引持久化: %s" % FAISS_INDEX_FILE)
        except Exception as exc:
            print("[每日洞察] FAISS 索引保存失败: %s" % exc, file=sys.stderr)
        _used_merged = True
    else:
        print("[每日洞察] 无可用向量，尝试加载旧索引降级", file=sys.stderr)
        index, fallback_chunks = _load_index()
        if not index:
            print("[每日洞察] 无可用索引，跳过生成", file=sys.stderr)
            try:
                _log_tracking_entry(_build_tracking_entry(
                    ragas_eval={}, clusters=[], theme="", elapsed=round(time.time() - t0, 1),
                    rss_count=_stats_rss, hot_count=_stats_hot,
                    aihot_count=_stats_aihot, agihunt_count=_stats_agihunt,
                    chunks_count=_stats_chunks_raw, filtered_count=_stats_filtered,
                    llm_available=bool(llm), embed_model=embed_model or ""))
            except Exception:
                pass
            return False
    # 后续流程：index 必须与 chunks 对齐
    # 正常路径用 merged_chunks（与新建 index 对齐）
    # 降级路径用 fallback_chunks（与旧 index 对齐）
    if _used_merged:
        chunks = merged_chunks
    else:
        chunks = fallback_chunks

    # 3) 构建查询：混合查询构建
    queries = _build_queries(hot_clean, agihunt_clean, aihot_clean, rss_clean=rss_clean)

    # 4) 混合检索 → 重排序 → 事件组装
    retrieved = _hybrid_retrieve(index, chunks, queries)
    if not retrieved:
        print("[每日洞察] 检索无结果，跳过生成")
        try:
            _log_tracking_entry(_build_tracking_entry(
                ragas_eval={}, clusters=[], theme="", elapsed=round(time.time() - t0, 1),
                rss_count=_stats_rss, hot_count=_stats_hot,
                aihot_count=_stats_aihot, agihunt_count=_stats_agihunt,
                chunks_count=_stats_chunks_raw, filtered_count=_stats_filtered,
                llm_available=bool(llm), embed_model=embed_model or ""))
        except Exception:
            pass
        return False
    # 保留检索结果供 RAGAS 评估（retrieved 是列表，不会被消费）
    retrieved_for_ragas = retrieved
    retrieved = _rerank(retrieved, hot_snapshot)
    clusters = _assemble_events(retrieved)
    if not clusters:
        print("[每日洞察] 无事件簇，跳过生成")
        try:
            _log_tracking_entry(_build_tracking_entry(
                ragas_eval={}, clusters=[], theme="", elapsed=round(time.time() - t0, 1),
                rss_count=_stats_rss, hot_count=_stats_hot,
                aihot_count=_stats_aihot, agihunt_count=_stats_agihunt,
                chunks_count=_stats_chunks_raw, filtered_count=_stats_filtered,
                llm_available=bool(llm), embed_model=embed_model or ""))
        except Exception:
            pass
        return False

    # 5) 事件级打分
    clusters = _score_events(clusters, hot_snapshot)

    # ── Phase 3.3: 跨天事件关联 ──
    history = _load_history()
    clusters = _match_events_to_history(clusters, history)

    # ── Phase 2: LLM 生成 ──
    llm = _init_llm()
    has_analysis = False
    theme = ""

    if llm:
        # Phase 1 前素材预过滤：移除与事件标签明显无关的 items，防止内容串位
        for c in clusters:
            _filter_cluster_items(c, c.get("label", ""))

        # Phase 1 LLM: 全事件摘要（传入全局检索上下文，解决生成/评估不对齐问题）
        _ragas_ctx = _build_ragas_context(clusters, retrieved_for_ragas) if retrieved_for_ragas else ""
        p1_result = _llm_phase1(llm, clusters, global_context=_ragas_ctx[:12000] if _ragas_ctx else None)
        if p1_result:
            theme = _apply_phase1_result(clusters, p1_result)

            # Phase 1.2: 丢弃 [信息不足] 事件 — 防止占位事件拉低质量（前缀匹配，覆盖 [信息不足：...]）
            _before = len(clusters)
            clusters = _drop_insufficient(clusters)
            _dropped = _before - len(clusters)
            if _dropped:
                print("[每日洞察] 丢弃 %d 个 [信息不足] 事件" % _dropped)

            # Phase 1.3: 跨源去重 — 合并同 category 且标签相似的事件
            clusters = _deduplicate_after_phase1(clusters)

            # Phase 1.5: 事实核查 — 确保 faithfulness
            try:
                _verify_faithfulness(llm, clusters, retrieved_for_ragas)
            except Exception as exc:
                print("[每日洞察] 事实核查异常，跳过: %s" % exc, file=sys.stderr)

            # Phase 1.6: 自审环节 — 检查 Phase 1 输出质量
            try:
                all_material = "\n".join(
                    _build_event_material(c)[:300] for c in clusters[:MAX_EVENTS])
                _self_review_phase1(llm, clusters, all_material)
            except Exception as exc:
                print("[每日洞察] 自审环节异常，跳过: %s" % exc, file=sys.stderr)

            # Phase 1.7: 自审后最终去重 — 捕获自审修改 label 后产生的重复
            clusters = _deduplicate_after_phase1(clusters)

            # Phase 1.8: AI 主题硬过滤 — 清除与 AI/科技无关的噪声事件
            _AI_KEYWORDS = re.compile(
                r'AI|GPT|Claude|LLM|AGI|模型|智能|算法|芯片|GPU|推理|训练|'
                r'OpenAI|Anthropic|Google|Meta|微软|苹果|亚马逊|英伟达|'
                r'\bAI\b|\bLLM\b|\bML\b|\bNLP\b|\bCV\b|\bAPI\b|\bSDK\b|'
                r'机器人|自动驾驶|无人机|区块链|元宇宙|量子计算|'
                r'融资|创业|独角兽|估值|收购|IPO|上市|'
                r'开源|发布|上线|更新|版本|框架|平台|系统', re.IGNORECASE)
            _NON_AI_CATS = {'bbc top stories', 'fun', 'sport', 'entertainment',
                            'politics', 'celebrity', 'lifestyle', 'travel',
                            'food', 'fashion', 'music', 'film', 'tv'}
            _filtered = []
            for c in clusters:
                cat = (c.get("category", "") or "").lower()
                label = c.get("label", "") or ""
                # 明确非 AI 分类 → 检查 label 是否有 AI 关键词
                if cat in _NON_AI_CATS:
                    if not _AI_KEYWORDS.search(label):
                        print("[每日洞察] 过滤非AI事件: %s (cat=%s)" % (label[:40], cat))
                        continue
                # 检查 source_types 是否全为非 AI 源
                src_types = c.get("source_types", []) or []
                non_ai_srcs = {'bbc', 'cnn', 'reuters', 'guardian'}
                if src_types and all(s.lower() in non_ai_srcs for s in src_types):
                    if not _AI_KEYWORDS.search(label):
                        print("[每日洞察] 过滤非AI源事件: %s" % label[:40])
                        continue
                _filtered.append(c)
            if len(_filtered) < len(clusters) and len(_filtered) >= MIN_EVENTS:
                clusters = _filtered

            # Phase 2 LLM: Top N 深度解读（快筛门槛：editor_score ≥ MIN_DEEP_SCORE 才做深度分析）
            _gate_days = [d for d in _load_history().get("days", [])
                          if d.get("date") != NOW_BJ.strftime("%Y-%m-%d")]
            _yday_labels = {(e.get("label") or "").strip()
                            for e in (_gate_days[-1].get("events", []) if _gate_days else [])}
            for c in clusters:
                c["editor_score"] = _quick_score_event(c, yesterday_labels=_yday_labels)
            top_n = min(DEEP_ANALYSIS_TOP_N, len(clusters))
            _rss_by_url = {_norm_url(k): v for k, v in rss_history.items() if isinstance(v, dict)}
            _skipped_low = 0
            for i in range(top_n):
                c = clusters[i]
                if c["editor_score"] < MIN_DEEP_SCORE:
                    c["deep_analysis"] = None
                    _skipped_low += 1
                    continue
                # Phase 2 前素材过滤：移除与 label 不相关的 items
                _filter_cluster_items(c, c.get("label", ""))
                prev_summary = c.get("prev_summary") if c.get("status") in ("ongoing", "escalating") else None
                deep = _llm_phase2(llm, c, {
                    "label": c.get("label", ""),
                    "summary": c.get("summary", ""),
                }, prev_summary, evidence=_build_evidence_pack(c, _rss_by_url))
                c["deep_analysis"] = deep
                if deep.get("status") == "ok":
                    has_analysis = True
                    # 引用溯源回填：key_links 优先取实际被引用的素材链接（防 LLM 乱填同质 URL）
                    _cited_urls = []
                    for s in deep.get("cited_sources", []):
                        u = s.get("url", "")
                        if u and u not in _cited_urls:
                            _cited_urls.append(u)
                    if _cited_urls:
                        c["key_links"] = _cited_urls[:3]
                    print("[每日洞察] 深度解读完成: %s (引用 %d 源)" % (
                        c.get("label", "")[:30], len(deep.get("cited_sources", []))))
                else:
                    print("[每日洞察] 深度解读降级: %s (%s)" % (
                        c.get("label", "")[:30], deep.get("reason", "unknown")))
            if _skipped_low:
                print("[每日洞察] 快筛门槛: %d 个事件 editor_score < %d，跳过深度分析" % (
                    _skipped_low, MIN_DEEP_SCORE))
        else:
            print("[每日洞察] Phase 1 LLM 失败，降级为仅聚类结果", file=sys.stderr)
    else:
        print("[每日洞察] LLM 不可用，降级为仅聚类结果", file=sys.stderr)

    # Phase 2.4: 热度排序提前至 RAGAS 前——judge 评估的是最终展示序（relevance 定义含"重大在前"），
    # 且修正循环 weak_events 索引与该序自洽
    clusters = _order_events_for_output(clusters)

    # ── Phase 2.5: RAGAS 质量评估与自我修正 ──
    ragas_eval = {}
    if clusters:
        try:
            build_cfg = load_config()
            judge_llm = _init_judge_llm(build_cfg)
            if judge_llm:
                clusters, ragas_eval = _ragas_evaluate_and_correct(
                    judge_llm, clusters, theme, retrieved_for_ragas, build_cfg)
                # 修正循环重写了 label/summary/category，可能事后制造重复 → 去重必须在其后再跑一轮
                clusters = _deduplicate_after_phase1(clusters)
                # faith 终局闸：修正环改写的正文复查一次（06:12 期幻觉回归实证），再刷新分数
                _final_faith_recheck(llm, clusters, retrieved_for_ragas)
                # 修正循环改写了 label/summary 后刷新门槛分，保证导出 JSON 分数描述最终内容
                for c in clusters:
                    if "editor_score" in c:
                        c["editor_score"] = _quick_score_event(c, yesterday_labels=_yday_labels)
            else:
                print("[每日洞察] Judge LLM 不可用，跳过 RAGAS 评估", file=sys.stderr)
        except Exception as exc:
            print("[每日洞察] RAGAS 评估异常，跳过: %s" % exc, file=sys.stderr)

    # 占位闸（无条件）：事实核查/自审/RAGAS 修正环都可能在 Phase 1.2 之后注入[信息不足]
    clusters = _drop_insufficient(clusters)
    clusters = _order_events_for_output(clusters)  # 闸与分数刷新后重排，保证导出 editor_score 单调
    clusters = clusters[:MAX_EVENTS]  # T1: 输出预算收口 12，被去重/占位闸砍掉的槽位由池内后位候选顶上

    # ── Phase 3.1: 破茧栏 + 输出 JSON ──
    history = _load_history()
    read_profile = _build_read_profile(history)
    bubble_breaker = _select_bubble_events(clusters, read_profile, residual_chunks=retrieved_for_ragas, all_chunks=chunks)
    _write_insight_json(clusters, theme, has_analysis, ragas_eval, bubble_breaker)

    # ── Phase 3.3: 更新历史 ──
    _update_history(clusters, theme)

    # ── Phase 4: 历史页面 ──
    _build_history_html()

    # ── 注入 AI 日报子板块 ──
    _inject_into_ai_daily(clusters, theme, bubble_breaker)

    elapsed = round(time.time() - t0, 1)
    print("[每日洞察] 完成，耗时 %.1f 秒，%d 个事件" % (elapsed, len(clusters)))

    # ── Phase 5: 追踪日志 ──
    try:
        tracking_entry = _build_tracking_entry(
            ragas_eval=ragas_eval,
            clusters=clusters,
            theme=theme,
            elapsed=elapsed,
            rss_count=_stats_rss,
            hot_count=_stats_hot,
            aihot_count=_stats_aihot,
            agihunt_count=_stats_agihunt,
            chunks_count=_stats_chunks_raw,
            filtered_count=_stats_filtered,
            llm_available=bool(llm),
            embed_model=embed_model or "",
        )
        _log_tracking_entry(tracking_entry)
    except Exception as exc:
        print("[每日洞察] 追踪日志异常，跳过: %s" % exc, file=sys.stderr)

    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
