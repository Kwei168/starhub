"""
insight_engine.py — LlamaIndex-powered semantic analysis engine for StarHub.

Replaces the statistical _run_analysis() pipeline with LLM + embedding-based
semantic analysis.  Fully optional: works (with reduced functionality) even
when llama-index / fastembed are not installed.
"""

import json
import math
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ────────────────── Optional LlamaIndex imports ──────────────────
LLAMA_INDEX_AVAILABLE = False
FASTEMBED_AVAILABLE = False

try:
    from llama_index.core import Document, VectorStoreIndex, Settings
    from llama_index.core.node_parser import SentenceSplitter
    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    pass

try:
    from llama_index.embeddings.fastembed import FastEmbedEmbedding  # noqa: F401
    FASTEMBED_AVAILABLE = True
except ImportError:
    pass

BJT = timezone(timedelta(hours=8))

# ────────────────── Embedding model ──────────────────
# 硅基流动 BAAI/bge-m3 API（主力）：8192 token 上下文，1024 维，中英双语
# 本地 fastembed 作为无 API key 时的回退
_SF_EMBED_MODEL = "BAAI/bge-m3"
_SF_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
_SF_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
_SF_BATCH = 32  # 每批最多处理文本数

# 本地回退模型（bge-small-en-v1.5 仅英文，bge-small-zh-en-v1.5 中英双语）
_EMBED_MODEL = "BAAI/bge-small-zh-en-v1.5"
_EMBED_MODEL_FALLBACK = "BAAI/bge-small-en-v1.5"

# ────────────────── Task 2: Defaults / Config ──────────────────
_DEFAULTS = {
    "insight_engine_enabled": True,
    "insight_llm_provider": "agnes",
    "insight_max_documents": 200,
    "insight_top_keywords": 30,
    "insight_top_topics": 15,
}


def load_config(build_config_path="build_config.json"):
    """Read build_config.json and fill missing keys with _DEFAULTS."""
    cfg = dict(_DEFAULTS)
    try:
        with open(build_config_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg.update(user_cfg)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    # ensure all default keys present
    for k, v in _DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


# ────────────────── Task 1: AgnesLLM ──────────────────────────
class AgnesLLM:
    """Thin wrapper around the Agnes AI chat-completions API."""

    API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"

    def __init__(self, api_key, model="agnes-2.5-flash", timeout=30):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    # -- core completion --
    def complete(self, prompt, system_prompt=None, temperature=0.3, max_tokens=600):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[AgnesLLM] complete error: {exc}", file=sys.stderr)
            return ""

    def stream_complete(self, prompt, **kwargs):
        """Yield the full result (non-streaming fallback)."""
        yield self.complete(prompt, **kwargs)

    @property
    def metadata(self):
        return {"model_name": self.model, "context_window": 8192}


# ────────────────── Task 1: MockLLM ──────────────────────────
class MockLLM:
    """Deterministic mock LLM for offline / no-key scenarios."""

    def __init__(self, model="mock"):
        self.model = model

    def complete(self, prompt, system_prompt=None, temperature=0.3, max_tokens=600):
        prompt_lower = prompt.lower()
        # keyword extraction prompt → return JSON array
        if "keyword" in prompt_lower or "关键词" in prompt_lower:
            return json.dumps(["ai", "llm", "openai", "agent", "模型", "发布"])
        # narrative / insight prompt → return structured JSON
        if "insight" in prompt_lower or "洞察" in prompt_lower or "narrative" in prompt_lower:
            return json.dumps({
                "narrative": "当前科技领域以AI和大模型为核心叙事。",
                "causal_chains": ["AI发展→算力需求增长→芯片产业升温"],
                "signals": [{"signal": "AI终端化加速", "confidence": 0.8}],
                "outlook": "短期内AI仍将是信息场主旋律。",
            })
        # default
        return "这是一个模拟响应。"

    def stream_complete(self, prompt, **kwargs):
        yield self.complete(prompt, **kwargs)

    @property
    def metadata(self):
        return {"model_name": self.model, "context_window": 8192}


# ────────────────── Task 2: configure_llm ────────────────────
def configure_llm(config):
    """Create an LLM instance based on config. Falls back to MockLLM."""
    provider = config.get("insight_llm_provider", "agnes")
    if provider == "agnes":
        api_key = os.environ.get("AGNES_API_KEY", "")
        if api_key:
            return AgnesLLM(api_key=api_key)
        print("[insight_engine] AGNES_API_KEY not set, using MockLLM", file=sys.stderr)
    elif provider != "mock":
        print(f"[insight_engine] Unknown provider '{provider}', using MockLLM", file=sys.stderr)
    return MockLLM()


# ────────────────── Task 3: load_documents ───────────────────
def load_documents(hot_snapshot, rss_history, trending_data, max_documents=200):
    """Convert raw data dicts into a list of LlamaIndex Document objects."""
    docs = []
    # --- Hot items (highest priority) ---
    if hot_snapshot:
        for platform in hot_snapshot:
            plat = platform.get("platform", platform.get("name", "unknown"))
            for item in platform.get("items", []):
                title = item.get("title", "")
                if title:
                    text = f"[热榜/{plat}] {title}"
                    docs.append({"text": text, "priority": 0})

    # --- Trending (second priority) ---
    if trending_data:
        items = trending_data.items() if isinstance(trending_data, dict) else []
        for repo, stars in items:
            desc = repo  # repo name as description fallback
            text = f"[Trending] {repo} (+{stars} stars): {desc}"
            docs.append({"text": text, "priority": 1})

    # --- RSS items (lowest priority) ---
    if rss_history:
        rss_items = rss_history.values() if isinstance(rss_history, dict) else rss_history
        for item in rss_items:
            if isinstance(item, dict):
                title = item.get("title", "")
                summary = item.get("summary", "")[:300]
                cat = item.get("cat", item.get("category", "rss"))
                text = f"[RSS/{cat}] {title} {summary}".strip()[:500]
                if text.strip():
                    docs.append({"text": text, "priority": 2})

    # Sort by priority (lower = higher priority), then truncate
    docs.sort(key=lambda d: d["priority"])
    docs = docs[:max_documents]

    if not LLAMA_INDEX_AVAILABLE:
        # Return lightweight stand-in objects
        return [_SimpleDoc(d["text"]) for d in docs]

    from llama_index.core import Document as LiDocument
    return [LiDocument(text=d["text"]) for d in docs]


class _SimpleDoc:
    """Minimal Document stand-in when llama-index is not installed."""
    def __init__(self, text):
        self.text = text


# ────────────────── Task 3: build_index ──────────────────────
def build_index(documents):
    """Build an in-memory VectorStoreIndex. Returns None if deps missing."""
    if not LLAMA_INDEX_AVAILABLE or not FASTEMBED_AVAILABLE:
        return None
    try:
        model_name = _EMBED_MODEL
        if _SF_KEY:
            # SiliconFlow API 可用时仍用本地模型建索引（API 向量由调用方单独获取）
            model_name = _EMBED_MODEL
        Settings.embed_model = FastEmbedEmbedding(model_name=model_name)
        index = VectorStoreIndex.from_documents(documents, show_progress=False)
        return index
    except Exception as exc:
        print(f"[insight_engine] build_index error: {exc}", file=sys.stderr)
        return None


def _get_embeddings(texts):
    """获取 embedding 向量：硅基流动 API → 本地 fastembed → None。
    返回 (vectors, model_name) 元组。
    """
    if not texts:
        return None, None

    # 1) 硅基流动 BAAI/bge-m3 API（8192 token，1024 维，中英双语）
    if _SF_KEY:
        all_vecs = []
        ok = True
        for i in range(0, len(texts), _SF_BATCH):
            batch = texts[i:i + _SF_BATCH]
            payload = json.dumps({
                "model": _SF_EMBED_MODEL,
                "input": batch,
            }).encode("utf-8")
            req = urllib.request.Request(
                _SF_EMBED_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {_SF_KEY}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                batch_vecs = [d["embedding"] for d in data.get("data", [])]
                all_vecs.extend(batch_vecs)
            except Exception as exc:
                print(f"[insight_engine] SiliconFlow embed batch error: {exc}", file=sys.stderr)
                ok = False
                break
        if ok and len(all_vecs) == len(texts):
            print(f"[insight_engine] embeddings via SiliconFlow {_SF_EMBED_MODEL} ({len(texts)} texts)", file=sys.stderr)
            return all_vecs, f"siliconflow/{_SF_EMBED_MODEL}"
        if not ok:
            print(f"[insight_engine] SiliconFlow API failed, falling back to local fastembed", file=sys.stderr)

    # 2) 本地 fastembed 回退
    if FASTEMBED_AVAILABLE:
        try:
            Settings.embed_model = FastEmbedEmbedding(model_name=_EMBED_MODEL)
            vecs = Settings.embed_model.get_text_embedding_batch(texts)
            if vecs and len(vecs) == len(texts):
                print(f"[insight_engine] embeddings via local {_EMBED_MODEL} ({len(texts)} texts)", file=sys.stderr)
                return vecs, _EMBED_MODEL
        except Exception as exc:
            print(f"[insight_engine] local embed error: {exc}", file=sys.stderr)

    return None, None


# ────────────────── Task 4: Helpers ──────────────────────────
def _try_parse_json(text):
    """Try to parse JSON from text; return None on failure."""
    if not text:
        return None
    # strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _cosine_similarity(a, b):
    """Cosine similarity between two vectors (lists of floats)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _average_vector(vecs):
    """Element-wise average of a list of vectors."""
    if not vecs:
        return []
    n = len(vecs)
    dim = len(vecs[0])
    return [sum(v[i] for v in vecs) / n for i in range(dim)]


def _extract_cluster_label(texts, all_doc_texts=None):
    """从簇内文本中提取语义标签。
    策略：去前缀 → 中文高频 2-gram（用全局 IDF 加权）/ 英文高频词。
    all_doc_texts: 所有文档文本列表，用于计算全局 IDF。若为 None 则仅用簇内频率。
    """
    # 去 [RSS/xxx] / [热榜/xxx] 前缀 + 常见 RSS 模板尾部
    cleaned = []
    for t in texts:
        t = t.strip()
        t = re.sub(r'^\[(?:RSS|\u70ed\u699c|Trending)/[^\]]*\]\s*', '', t)
        # 去常见 RSS 模板尾部（"点击查看知乎原文" 等）
        t = re.sub(r'[\u67e5\u770b\u70b9\u51fb]?\u77e5\u4e4e[\u539f\u6587]?\u00b7?\s*$', '', t)
        t = re.sub(r'\u9605\u8bfb[\u539f\u6587]+.*$', '', t)
        if len(t) >= 4:
            cleaned.append(t)
    if not cleaned:
        return max(texts, key=len)[:60] if texts else ''
    n = len(cleaned)
    # ── 中文：高频 2 字子串（最简洁的有意义标签） ──
    _STOP_CHARS = set('\u7684\u4e86\u662f\u5728\u6211\u6709\u548c\u5c31\u4e0d\u90fd\u4e00\u4e2a\u4e5f\u4e0a\u8fd9\u5230\u8bf4\u4eec\u4e3a\u5bf9\u88ab\u628a\u8ba9\u7ed9\u7528\u4ece\u5411\u5982\u53ef\u4ee5\u80fd\u4f1a\u5df2\u7ecf\u8fd8\u5f88\u592a\u90a3\u4ed6\u5979\u5b83\u4e48\u5427\u5417\u5462\u554a\u54c8\u54df\u5566\u5457\u561b\u563f\u561f\u561c\u5616\u5618\u561a\u5619\u561b\u55d2\u55d3\u55d4\u55d5\u55d6\u55d7\u55d8\u55d9\u55da\u55db\u55dc\u55dd\u55de\u55df\u55e0\u55e1\u55e2\u55e3\u55e4\u55e5\u55e6\u55e7\u55e8\u55e9\u55ea\u55eb\u55ec\u55ed\u55ee\u55ef\u55f0\u55f1\u55f2\u55f3\u55f4\u55f5\u55f6\u55f7\u55f8\u55f9\u55fa\u55fb\u55fc\u55fd\u55fe\u55ff')
    # 常见无意义 2 字词（高频但无话题意义）
    _STOP_2GRAMS = {
        '需要','应该','可能','可以','这个','那个','什么','怎么','为什么',
        '因为','所以','但是','虽然','如果','已经','还是','或者','而且',
        '不是','没有','一个','知道','觉得','感觉','希望','想要','开始',
        '进行','通过','使用','实现','问题','情况','方面','部分','结果',
        '分钟','时间','时候','地方','东西','样子','方法','方式','系统',
        '技术','世界','国家','社会','公司','学校','企业','市场','用户',
        '数据','网络','平台','工作','生活','文化','历史','未来','现在',
        '今天','昨天','明天','今年','去年','自己','别人','人们','社会',
        # RSS/网页常见导航短语（无话题意义）
        '查看','知乎','阅读','原文','点击','链接','分享','关注',
        '订阅','评论','回复','转载','编辑','推荐','更多','相关',
        '搜索','登录','注册','首页','频道','专栏','话题','标签',
        '看知','乎原','事情','音频','声音','内容','感觉','意思',
    }
    cn_items = [re.sub(r'[^\u4e00-\u9fff]', '', t) for t in cleaned]
    cn_items = [c for c in cn_items if len(c) >= 2]
    if cn_items:
        # 计算全局 2-gram DF（用于 IDF 加权）
        global_df = {}
        if all_doc_texts:
            for doc in all_doc_texts:
                doc_cn = re.sub(r'[^\u4e00-\u9fff]', '', doc)
                seen = set()
                for start in range(len(doc_cn) - 1):
                    bg = doc_cn[start:start + 2]
                    if bg not in seen:
                        global_df[bg] = global_df.get(bg, 0) + 1
                        seen.add(bg)
        total_docs = max(len(all_doc_texts), n) if all_doc_texts else n
        best_label = ''
        best_score = 0.0
        for t in cn_items:
            for start in range(len(t) - 1):
                sub = t[start:start + 2]
                if sub[0] in _STOP_CHARS or sub[1] in _STOP_CHARS:
                    continue
                if sub in _STOP_2GRAMS:
                    continue
                cnt = sum(1 for ct in cn_items if sub in ct)
                if cnt >= max(2, n * 0.2):
                    # TF-IDF: 簇内频率 * 全局 IDF
                    tf = cnt / n
                    df = global_df.get(sub, 0)
                    idf = math.log((total_docs + 1) / (df + 1)) + 1  # smoothed IDF
                    score = tf * idf
                    if score > best_score:
                        best_label, best_score = sub, score
        if best_label:
            return best_label
    # ── 英文/混合：高频词 ──
    _STOP_WORDS = {'the','a','an','is','are','was','were','be','been','being',
                   'have','has','had','do','does','did','will','would','could',
                   'should','may','might','can','shall','to','of','in','for',
                   'on','with','at','by','from','as','into','through','during',
                   'before','after','above','below','between','out','off','over',
                   'under','again','further','then','once','here','there','when',
                   'where','why','how','all','both','each','few','more','most',
                   'other','some','such','no','nor','not','only','own','same',
                   'so','than','too','very','just','because','but','and','or',
                   'if','while','about','up','it','its','i','me','my','we','our',
                   'you','your','he','him','his','she','her','they','them','this','that','these'}
    words_list = [re.findall(r'[a-zA-Z]{3,}', t) for t in cleaned]
    if words_list and any(words_list):
        word_score = {}
        for wl in words_list:
            seen = set()
            for w in wl:
                wl_lower = w.lower()
                if wl_lower in _STOP_WORDS or wl_lower in seen:
                    continue
                seen.add(wl_lower)
                word_score[wl_lower] = word_score.get(wl_lower, 0) + 1
        if word_score:
            best_word = max(word_score, key=lambda w: (word_score[w], len(w)))
            if word_score[best_word] >= max(2, n * 0.2):
                return best_word
    # ── 回退：最长文本截断 ──
    return max(cleaned, key=len)[:40]


def _fallback_cluster(texts, max_topics=15, threshold=0.5, all_doc_texts=None):
    """Character-overlap based clustering when embeddings are unavailable.
    阈值从 0.3 提升到 0.5，避免中文常用字导致误聚类。
    使用锚点比较（而非贪婪链接）防止链式聚类。
    """
    _MAX_CLUSTER = max(5, len(texts) // 8)  # 单簇上限，防止巨型簇
    clusters = []
    used = set()
    for i, t in enumerate(texts):
        if i in used:
            continue
        cluster = [t]
        used.add(i)
        anchor_chars = set(t.lower())  # 锚点：种子文本的字符集
        for j in range(i + 1, len(texts)):
            if j in used:
                continue
            if len(cluster) >= _MAX_CLUSTER:
                break
            tj = set(texts[j].lower())
            # 与锚点比较（而非最后一个簇成员），防止链式聚类
            overlap = len(anchor_chars & tj) / max(len(anchor_chars | tj), 1)
            if overlap >= threshold:
                cluster.append(texts[j])
                used.add(j)
        if len(cluster) >= 2:
            label = _extract_cluster_label(cluster, all_doc_texts)
            clusters.append({"label": label, "count": len(cluster), "items": cluster})
    clusters.sort(key=lambda c: -c["count"])
    return clusters[:max_topics]


# ────────────────── Task 4: extract_keywords_llm ─────────────
def extract_keywords_llm(llm, texts, top_n=30):
    """Use LLM to extract keywords from a combined text sample."""
    if not texts:
        return []
    combined = "\n".join(texts[:100])
    prompt = (
        f"请从以下文本中提取最重要的 {top_n} 个关键词，"
        "以 JSON 数组格式返回（只返回数组，不要其他文字）：\n\n"
        f"{combined[:4000]}"
    )
    result = llm.complete(prompt)
    parsed = _try_parse_json(result)
    if isinstance(parsed, list) and len(parsed) > 0:
        return [str(k) for k in parsed[:top_n]]
    # fallback: line-split
    lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
    keywords = []
    for line in lines:
        clean = line.strip("-•· ").strip()
        if clean and len(clean) < 50:
            keywords.append(clean)
    return keywords[:top_n] if keywords else []


# ────────────────── Task 4: cluster_topics_embedding ─────────
def cluster_topics_embedding(articles, max_topics=15, similarity_threshold=0.7, all_doc_texts=None):
    """Embedding-based greedy clustering. Falls back to char-overlap."""
    if not articles:
        return []
    texts = [a if isinstance(a, str) else a.get("text", str(a)) for a in articles]
    embeddings, embed_model_name = _get_embeddings(texts)

    if embeddings and len(embeddings) == len(articles):
        print(f"[insight_engine] clustering with embeddings: {embed_model_name}", file=sys.stderr)
        return _cluster_with_embeddings(articles, embeddings, max_topics, similarity_threshold, all_doc_texts)
    # fallback
    print(f"[insight_engine] clustering with char-overlap fallback (embeddings unavailable)", file=sys.stderr)
    return _fallback_cluster(texts, max_topics, all_doc_texts=all_doc_texts)


def _cluster_with_embeddings(articles, embeddings, max_topics, threshold, all_doc_texts=None):
    """Greedy clustering by cosine similarity on embeddings.
    使用锚点比较 + 单簇上限防止巨型簇。
    """
    n = len(articles)
    used = [False] * n
    _MAX_CLUSTER = max(5, n // 8)  # 单簇上限
    clusters = []
    for i in range(n):
        if used[i]:
            continue
        cluster_indices = [i]
        used[i] = True
        vec_i = embeddings[i]  # 锚点向量
        for j in range(i + 1, n):
            if used[j]:
                continue
            if len(cluster_indices) >= _MAX_CLUSTER:
                break
            sim = _cosine_similarity(vec_i, embeddings[j])
            if sim >= threshold:
                cluster_indices.append(j)
                used[j] = True
        if len(cluster_indices) >= 2:
            texts = [articles[k] if isinstance(articles[k], str) else articles[k].get("text", "") for k in cluster_indices]
            label = _extract_cluster_label(texts, all_doc_texts)
            clusters.append({"label": label, "count": len(texts), "items": texts})
    clusters.sort(key=lambda c: -c["count"])
    return clusters[:max_topics]


# ────────────────── Task 4: cross_platform_semantic ──────────
def cross_platform_semantic(hot_snapshot, similarity_threshold=0.75):
    """Embedding-based cross-platform topic matching.
    Returns [] if embeddings unavailable (caller falls back to Jaccard).
    """
    if not hot_snapshot:
        return []
    try:
        # Collect titles per platform
        platform_titles = {}
        for platform in hot_snapshot:
            plat = platform.get("platform", platform.get("name", "unknown"))
            titles = [item.get("title", "") for item in platform.get("items", []) if item.get("title")]
            if titles:
                platform_titles[plat] = titles

        platforms = list(platform_titles.keys())
        if len(platforms) < 2:
            return []

        # Get all embeddings via unified helper
        all_titles = []
        title_platform = []
        for plat in platforms:
            for t in platform_titles[plat]:
                all_titles.append(t)
                title_platform.append(plat)

        vecs, _ = _get_embeddings(all_titles)
        if not vecs or len(vecs) != len(all_titles):
            return []

        # Find cross-platform matches
        matches = []
        seen = set()
        for i in range(len(all_titles)):
            for j in range(i + 1, len(all_titles)):
                if title_platform[i] == title_platform[j]:
                    continue
                sim = _cosine_similarity(vecs[i], vecs[j])
                if sim >= similarity_threshold:
                    key = (all_titles[i][:30], all_titles[j][:30])
                    if key not in seen:
                        seen.add(key)
                        matches.append({
                            "title_a": all_titles[i],
                            "title_b": all_titles[j],
                            "platform_a": title_platform[i],
                            "platform_b": title_platform[j],
                            "similarity": round(sim, 3),
                        })
        return matches[:20]
    except Exception as exc:
        print(f"[insight_engine] cross_platform_semantic error: {exc}", file=sys.stderr)
        return []


# ────────────────── Task 5: _is_recent ───────────────────────
def _is_recent(item, hours=24):
    """Check if an item is recent based on pub_date or timestamp."""
    now = datetime.now(BJT)
    for key in ("pub_date", "published", "date", "timestamp"):
        val = item.get(key) if isinstance(item, dict) else None
        if not val:
            continue
        try:
            if isinstance(val, str):
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            elif isinstance(val, (int, float)):
                dt = datetime.fromtimestamp(val, tz=BJT)
            else:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BJT)
            return (now - dt).total_seconds() < hours * 3600
        except (ValueError, TypeError, OSError):
            continue
    return True  # assume recent if no date field


# ────────────────── Task 5: generate_deep_insights ───────────
def generate_deep_insights(llm, context):
    """Use LLM to generate narrative insights from analysis context."""
    prompt = (
        "基于以下分析上下文，生成深度洞察。请以 JSON 格式返回，包含以下字段：\n"
        "- narrative: 一段200字以内的核心叙事分析\n"
        "- causal_chains: 因果链条数组，如 [\"A→B→C\"]\n"
        "- signals: 异动信号数组，每项含 signal 和 confidence\n"
        "- outlook: 一段100字以内的前瞻研判\n\n"
        f"分析上下文：\n{json.dumps(context, ensure_ascii=False)[:3000]}"
    )
    system_prompt = "你是科技情报分析师，擅长从多源数据中提取深层洞察。只返回 JSON，不要其他文字。"
    result = llm.complete(prompt, system_prompt=system_prompt, temperature=0.4, max_tokens=800)
    parsed = _try_parse_json(result)
    if isinstance(parsed, dict) and "narrative" in parsed:
        return parsed
    # fallback: simple keyword-based narrative
    keywords = context.get("keywords", [])
    kw_str = "、".join(keywords[:10]) if keywords else "无"
    return {
        "narrative": f"当前信息场核心关键词为：{kw_str}。",
        "causal_chains": [],
        "signals": [],
        "outlook": "建议持续关注上述领域的发展动态。",
    }


# ────────────────── Topic metadata builder ──────────────────
def _build_topics_with_meta(topic_clusters, rss_history):
    """从 topic_clusters 构建带 sources/links/cats 的话题列表。
    通过匹配 rss_history 中的文章元数据填充话题属性。
    """
    if not rss_history or not isinstance(rss_history, dict):
        return [{"label": c["label"], "count": c["count"],
                 "sources": [], "links": [], "cats": []}
                for c in topic_clusters]
    # 建立标题→元数据索引（用前30字做key）
    title_meta = {}
    for link, item in rss_history.items():
        title = item.get("title", "") or item.get("title_zh", "")
        if title:
            title_meta[title[:30]] = {
                "link": link,
                "source": item.get("source", ""),
                "cat": item.get("cat", item.get("category", "rss")),
            }
    topics = []
    for c in topic_clusters:
        sources_set = set()
        links_list = []
        cats_set = set()
        items = c.get("items", [])
        for item_text in items:
            # 去前缀后取前30字匹配
            clean = re.sub(r'^\[(?:RSS|\u70ed\u699c|Trending)/[^\]]*\]\s*', '', item_text)
            key = clean[:30]
            meta = title_meta.get(key)
            if meta:
                if meta["source"]:
                    sources_set.add(meta["source"])
                links_list.append(meta["link"])
                if meta["cat"]:
                    cats_set.add(meta["cat"])
        topics.append({
            "label": c["label"],
            "count": c["count"],
            "sources": sorted(sources_set)[:5],
            "links": links_list[:10],
            "cats": sorted(cats_set),
        })
    return topics


# ────────────────── Task 5: run_analysis (main entry) ────────
def run_analysis(hot_snapshot, rss_history, trending_data, config,
                 prev_keywords=None, hot_history=None):
    """Main entry point. Returns analysis dict or None if disabled."""
    if not config.get("insight_engine_enabled", True):
        return None

    t0 = datetime.now(BJT)
    llm = configure_llm(config)
    max_docs = config.get("insight_max_documents", 200)
    top_kw = config.get("insight_top_keywords", 30)
    top_topics = config.get("insight_top_topics", 15)

    # 1. Load documents
    documents = load_documents(hot_snapshot, rss_history, trending_data, max_docs)

    # 2. Build index (may be None)
    index = build_index(documents)

    # 3. Extract keywords
    doc_texts = [d.text for d in documents] if documents else []
    keywords = extract_keywords_llm(llm, doc_texts, top_n=top_kw)

    # 4. Cluster topics — 分离热榜和RSS，仅对RSS文章聚类
    rss_texts = [t for t in doc_texts if t.startswith('[RSS/')]
    topic_clusters = cluster_topics_embedding(rss_texts, max_topics=top_topics, all_doc_texts=doc_texts) if rss_texts else []

    # 5. Cross-platform semantic
    cross_platform = cross_platform_semantic(hot_snapshot)

    # 6. Rising detection
    rising = []
    if prev_keywords:
        prev_freq = {w: i + 1 for i, w in enumerate(prev_keywords[:50])}
        curr_freq = {w: i + 1 for i, w in enumerate(keywords[:50])}
        for w, rank in curr_freq.items():
            prev_rank = prev_freq.get(w, 999)
            if prev_rank > rank + 5:
                rising.append({"word": w, "rise": prev_rank - rank, "current_rank": rank})
        rising.sort(key=lambda x: -x["rise"])
        rising = rising[:15]

    # 7. Deep insights
    context = {
        "keywords": keywords,
        "topic_count": len(topic_clusters),
        "doc_count": len(documents),
        "cross_platform_count": len(cross_platform),
    }
    deep_insights = generate_deep_insights(llm, context)

    # 8. Stats
    rss_items = list((rss_history or {}).values()) if isinstance(rss_history, dict) else []
    recent_count = sum(1 for item in rss_items if _is_recent(item))
    source_count = len(set(item.get("source_key", "") for item in rss_items if item.get("source_key")))
    stats = {
        "total_articles": len(documents) if documents else 0,
        "recent_count": recent_count if rss_items else len(doc_texts),
        "source_count": source_count if source_count else (len(hot_snapshot) if hot_snapshot else 0),
    }

    # 9. Build old-format summary for frontend compatibility
    summary = {
        "core_trends": deep_insights.get("narrative", ""),
        "signals": deep_insights.get("outlook", ""),
        "rss_insights": f"共分析 {len(doc_texts)} 条内容，提取 {len(keywords)} 个关键词。",
        "outlook": deep_insights.get("outlook", ""),
    }

    # 10. Assemble output — old format + new fields
    now_bj = datetime.now(BJT)
    analysis = {
        "generated_at": now_bj.isoformat(),
        "keywords": {
            "global": [(w, round(top_kw - i, 2)) for i, w in enumerate(keywords[:50])],
            "by_cat": {},
        },
        "rising": rising,
        "topics": _build_topics_with_meta(topic_clusters, rss_history),
        "summary": summary,
        "stats": stats,
        "quality": {},
        "hot_trends": {},  # filled by integration layer in build_rss_aggregator.py
        "cross_platform": cross_platform if cross_platform else [],
        "cross_category": [],  # filled by integration layer in build_rss_aggregator.py
        # New fields
        "deep_insights": deep_insights,
        "topic_clusters": topic_clusters,
        "meta": {
            "engine": "insight_engine",
            "llm_provider": config.get("insight_llm_provider", "agnes"),
            "llm_available": not isinstance(llm, MockLLM),
            "index_built": index is not None,
            "elapsed_seconds": round((datetime.now(BJT) - t0).total_seconds(), 2),
        },
    }
    return analysis
