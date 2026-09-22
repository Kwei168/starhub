# -*- coding: utf-8 -*-
"""build_deep_insight.py — 夜间独立深度洞察管线（阶段 1）· 纯逻辑核心。

spec: docs/superpowers/specs/2026-09-22-nightly-deep-insight-design.md

本文件是**离线可判定**的核心 + 夜场运行时：输出契约、证据充分性门、上下文组装、
账号池调度、checkpoint、预测落盘与到期对账、并发提交（CAS）、独立页渲染。
判据先行是刻意的：先有契约再有生成，否则生成完没人说过得去。

判据的存在理由来自现网读数：9 个事件里 6 个正文 162-301 字、内容优质判断 ≈0，
而"信号深度 0-40"（build_daily_insight.py:2366）其实只是素材量代理且不进 prompt。

夜场刻意 **不 import 白天洞察模块**：那一串 import 会把 5000 行模块级副作用与
llama-index/faiss 依赖引上夜路，与 §4 的隔离要求冲突（判据见
tests/deep_insight/test_workflow_isolation.py::test_nightly_does_not_borrow_daytime_modules）。
"""
import html as html_mod
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

SCHEMA_VERSION = "deep-insight/v1"

NARR_MIN, NARR_MAX = 2500, 4000
PARAS_MIN = 6
# 单说"2500-4000 字"模型交回来的是 1748/2307/1902（run 35749459676 三条实测），
# 重写两轮也停在同一水平：总量它不接，段数它接。所以把配额下沉到段，
# 并按 PARAS_MIN*PARA_MIN >= NARR_MIN 留出余量（字数口径含标点，实测略偏小）。
PARA_MIN = NARR_MIN // PARAS_MIN + 50
CLAIM_MIN, CLAIM_MAX = 3, 10
CHAINS_MIN, CHAINS_MAX = 2, 6
FORECAST_MIN, FORECAST_MAX = 1, 4
CITE_MIN, CITE_MAX = 5, 12
HORIZONS = (3, 7, 14)
FORECAST_CLAIM_MAX = 80
CHAIN_FIELD_MAX = 170
WHY_MIN, WHY_MAX = 20, 120
QUALITY_VERDICTS = ("一手", "深度", "数据支撑", "转载", "通稿", "营销")

GATE_MIN_SOURCES = 3
GATE_MIN_TOTAL_CHARS = 12000
GATE_LONG_CHARS = 3000
GATE_MIN_LONG = 2

DEFAULT_BUDGET_TOKENS = 400000
MAX_BUDGET_TOKENS = 800000

# 预测账本：夜场自己的持久化产物。未到期全留，已结算只留 PRED_KEEP_DAYS 天 ——
# 无界追加就是第二个 rss_history，那条链的教训已经付过一次。
PREDICTIONS_NAME = "predictions.jsonl"
PRED_KEEP_DAYS = 90
# 并发档上限：spec §4 `worker = min(len(api_keys), 6)`。免费 Agnes 池被 6 把以上
# 并发推，换来的不是吞吐是 429 墙；档位最终值等首夜读数，但不许越过这个天花板。
WORKERS_MAX = 6
# 429 退避封顶（spec §4）。上游偶尔给 `Retry-After: 3600`，照单全收等于一把 key
# 整夜报废；池子本来只有几把，剩下的会被"每条 ≤3 次生成 + 1 次判定"挤爆。
# 封顶不是忽略限流信号：仍然按封顶值冷却。
BACKOFF_CAP_S = 120

DEGRADED_NARR_MAX = 200
CAVEAT_MARKS = ("但", "不过", "限制", "风险", "尚未", "存疑", "未证实", "口径", "样本")
_BULLET = re.compile(r"^\s*(?:[-•·*]|\d+[.)、])\s*")
_CHECKABLE = re.compile(r"(>=|<=|≥|≤|>|<|不低于|不超过|至少|少于)")


def count_chars(text):
    """中文字数口径：去掉所有空白后的字符数。混用"含空格长度"会把下限虚抬三成。"""
    return len(re.sub(r"\s+", "", text or ""))


def estimate_tokens(text):
    """CJK 1 字≈1 token，其余 4 字符≈1 token。

    预算按 ASCII 口径估会把中文上下文虚高一倍，直接顶穿模型窗口 —— 现网
    `_ragas_ctx[:12000]` 那类"按字符当 token"的写法就是这个坑。
    """
    text = text or ""
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return cjk + -(-other // 4)


def _is_cjk(ch):
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
            or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF
            or 0xF900 <= o <= 0xFAFF)


def _paragraphs(text):
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]


def validate_event(ev, valid_ids=None, valid_basis=None):
    """按 spec §2 逐条判一个洞察条目合不合格。返回 (是否合格, 失败原因列表)。"""
    fails = []
    degraded_reason = (ev.get("degraded_reason") or "").strip()
    narrative = ev.get("narrative") or ""
    n = count_chars(narrative)

    if degraded_reason:
        if n > DEGRADED_NARR_MAX:
            fails.append("degraded 条目正文 %d 字，超过快讯上限 %d" % (n, DEGRADED_NARR_MAX))
        if ev.get("forecasts"):
            fails.append("degraded 条目不许产预测：证据不足没资格做断言")
        return (not fails), fails

    if n < NARR_MIN:
        fails.append("narrative 字数 %d < 下限 %d" % (n, NARR_MIN))
    if n > NARR_MAX:
        fails.append("narrative 字数 %d > 上限 %d（overlen，不得当合格）" % (n, NARR_MAX))

    paras = _paragraphs(narrative)
    if len(paras) < PARAS_MIN:
        fails.append("段落数 %d < %d 段" % (len(paras), PARAS_MIN))
    bullets = sum(1 for p in paras if _BULLET.match(p))
    if paras and bullets * 1.0 / len(paras) >= 0.6:
        fails.append("narrative 是条目体（分点罗列 %d/%d 段），不算成文论述" % (bullets, len(paras)))
    if narrative and not any(m in narrative for m in CAVEAT_MARKS):
        fails.append("narrative 未出现任何反证/限制条件表述")

    cites = ev.get("citations") or []
    ids = [c.get("id") for c in cites]
    if not CITE_MIN <= len(cites) <= CITE_MAX:
        fails.append("citations %d 条，须在 [%d,%d]" % (len(cites), CITE_MIN, CITE_MAX))
    if len(set(ids)) != len(ids):
        fails.append("citations id 有重复")
    if valid_ids is not None:
        fake = [i for i in ids if i not in valid_ids]
        if fake:
            fails.append("citation id 不在检索池里（假链接）：%s" % fake[:4])
    for c in cites:
        u = c.get("url") or ""
        if not u.startswith("http://") and not u.startswith("https://"):
            fails.append("citation url 不是绝对链接（死链）：%s" % (u or "<空>")[:60])
            break

    claims = ev.get("claims") or []
    if not CLAIM_MIN <= len(claims) <= CLAIM_MAX:
        fails.append("claims %d 条，须在 [%d,%d]" % (len(claims), CLAIM_MIN, CLAIM_MAX))
    for cl in claims:
        for e in (cl.get("evidence") or []):
            if valid_ids is not None and e not in valid_ids:
                fails.append("claim 引用了不存在的 chunk：%s" % e)
                break

    chains = ev.get("causal_chains") or []
    if not CHAINS_MIN <= len(chains) <= CHAINS_MAX:
        fails.append("causal_chains %d 条，须在 [%d,%d]" % (len(chains), CHAINS_MIN, CHAINS_MAX))
    for ch in chains:
        over = [k for k in ("trigger", "mechanism", "outcome")
                if count_chars(ch.get(k) or "") > CHAIN_FIELD_MAX]
        if over:
            fails.append("causal 字段超长：%s" % over)
            break
        if not (ch.get("evidence") or []):
            fails.append("causal_chain 没有 evidence 支撑")
            break

    fcs = ev.get("forecasts") or []
    if not FORECAST_MIN <= len(fcs) <= FORECAST_MAX:
        fails.append("forecasts %d 条，须在 [%d,%d]" % (len(fcs), FORECAST_MIN, FORECAST_MAX))
    for f in fcs:
        if f.get("horizon_days") not in HORIZONS:
            fails.append("horizon_days %r 不在 %s（永不到期的预测不算预测）" % (f.get("horizon_days"), HORIZONS))
            break
        if not (f.get("check_metric") or "").strip():
            fails.append("forecast 缺 check_metric：不可核验的预测就是空话")
            break
        if count_chars(f.get("claim") or "") > FORECAST_CLAIM_MAX:
            fails.append("forecast claim %d 字 > %d" % (count_chars(f.get("claim") or ""), FORECAST_CLAIM_MAX))
            break

    q = ev.get("quality") or {}
    if q.get("verdict") not in QUALITY_VERDICTS:
        fails.append("quality.verdict %r 不在枚举 %s" % (q.get("verdict"), QUALITY_VERDICTS))
    score = q.get("score")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        fails.append("quality.score 必须在 0-100，实为 %r" % (score,))
    w = count_chars(q.get("why") or "")
    if not WHY_MIN <= w <= WHY_MAX:
        fails.append("quality.why %d 字，须在 [%d,%d]" % (w, WHY_MIN, WHY_MAX))
    if not (q.get("basis") or []):
        fails.append("quality.basis 为空：优质判断不许由生成方自评")
    elif valid_basis is not None:
        # 只查"非空"等于没查：模型写"这是一手报道"也算非空。必须引用确实喂给它的外证。
        bogus = [str(b).strip() for b in (q.get("basis") or [])
                 if str(b).strip() not in set(valid_basis)]
        if bogus:
            fails.append("quality.basis 没引用任何给定的外证信号（自评）：%s" % bogus[:3])

    if not (ev.get("title") or "").strip() or not (ev.get("topic") or "").strip():
        fails.append("条目缺 title/topic")
    return (not fails), fails


def evidence_gate(articles):
    """证据充分性门。不过 ⇒ 整条降级为快讯，不硬写深度。"""
    arts = [a for a in (articles or []) if count_chars(a.get("text") or "") > 0]
    sources = set()
    for a in arts:
        s = (a.get("source") or "").strip()
        if not s:
            s = re.sub(r"^www\.", "", (a.get("url") or "/").split("//")[-1].split("/")[0])
        sources.add(s or "<未知>")
    total = sum(count_chars(a.get("text") or "") for a in arts)
    longs = sum(1 for a in arts if count_chars(a.get("text") or "") >= GATE_LONG_CHARS)
    if len(sources) < GATE_MIN_SOURCES:
        return False, "独立源 %d 个 < %d 源" % (len(sources), GATE_MIN_SOURCES)
    if total < GATE_MIN_TOTAL_CHARS:
        return False, "素材合计 %d 字 < %d 字" % (total, GATE_MIN_TOTAL_CHARS)
    if longs < GATE_MIN_LONG:
        return False, "≥%d 字的长文只有 %d 篇，不足 %d 篇：短文撑不起论证" % (
            GATE_LONG_CHARS, longs, GATE_MIN_LONG)
    return True, "ok"


def assemble_context(articles, budget_tokens=DEFAULT_BUDGET_TOKENS):
    """预算内整篇给；装不下就丢整篇并记原因，绝不塞半篇。

    白天侧 `body[:800]` / `_truncate_at_paragraph(full, 2500)` 把 5706 字的公众号长文
    切剩零头，是"每条太短"的直接来源之一。夜间线从入口就按整篇装配。
    """
    budget = min(int(budget_tokens or 0), MAX_BUDGET_TOKENS)
    keep, dropped, tok, chars = [], [], 0, 0
    for a in articles or []:
        text = a.get("text") or ""
        t = estimate_tokens(text)
        if tok + t > budget:
            dropped.append({"url": a.get("url", ""), "tokens": t,
                            "reason": "超上下文预算（%d/%d token），整篇放弃" % (tok + t, budget)})
            continue
        keep.append(a)
        tok += t
        chars += count_chars(text)
    return {"articles": keep, "dropped": dropped, "total_tokens": tok, "total_chars": chars}


def load_done(path):
    return {r.get("id") for r in load_records(path) if r.get("id")}


def load_records(path):
    """读 checkpoint 里的完整记录。

    只有 id 集合是不够的：续跑时若产物只装"本场新做的"，
    `can_publish` 按 done+recs 放行、发布写的却是 payload，
    于是"失败后原地重试"那一夜上线的就是半套 —— 所以已完成的正文也要回到产物里。
    """
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in parse_jsonl(f.read()) if isinstance(r, dict)]


def append_jsonl(path, rows):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows or []:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def can_publish(events, done, budget_used_calls=0, call_cap=80, stopped_by_cap=False):
    """半套产物不上线；只有"撞预算/撞墙钟主动收口"允许带 not_run 上线。

    `stopped_by_cap` 必须单独进来：墙钟到点时 `llm_calls` 往往远低于 `call_cap`，
    只看调用数的话，§4"已经做完的照样发布"就成了假话 —— 实测那种夜里
    `published={'status':'blocked'}`、提交 0、退出码 0，钱花完而线上一片空白。
    """
    total = len(events or [])
    got = len(done or [])
    if total == 0 or got == 0:
        return False
    if got >= total:
        return True
    return bool(stopped_by_cap) or budget_used_calls >= call_cap


def missing(events, done, stop=""):
    """done 可传条目列表或 id 列表 —— 两处调用方本来就拿的是不同形态。

    收口原因要分账：`budget` 是调用预算用完（下一步是加条目预算），
    `wallclock` 是窗口不够（下一步是提并发/加 key）。写成同一个名字，
    读日志的人就会拿错下一步。
    """
    got = set()
    for d in (done or []):
        got.add(d.get("id") if isinstance(d, dict) else d)
    reason = "not_run:%s" % stop if stop else "not_run:incomplete"
    return [{"id": e.get("id"), "reason": reason} for e in (events or []) if e.get("id") not in got]


def parse_jsonl(text):
    """逐行 JSONL；只收 dict 行。

    整份数组写成一行、或行是字符串/数字，都不算账本行 —— 让 `settle` 收到
    一个 list 会在后面 `r.get` 上炸，而炸在结算里比炸在读文件更难归因。
    """
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _pred_row(claim, event_id, horizon, metric, made_on, status="pending"):
    return {"claim": claim or "", "event_id": event_id or "", "horizon_days": horizon,
            "check_metric": metric or "", "made_on": made_on or "", "status": status}


def append_predictions(path, rows):
    keep = [_pred_row(r.get("claim"), r.get("event_id"), r.get("horizon_days"),
                      r.get("check_metric"), r.get("made_on")) for r in (rows or [])]
    append_jsonl(path, keep)


def pred_rows(events, made_on):
    """合格条目的 forecasts 进账本。degraded 本来就不许产预测（§2 第 3 行），这里再兜一道：
    落进账本的每一条都得是可到期核对的，不然命中率统计会被自造的空预测污染。"""
    rows = []
    for e in events or []:
        if (e.get("degraded_reason") or "").strip():
            continue
        for f in (e.get("forecasts") or []):
            if not (f.get("claim") or "").strip():
                continue
            rows.append(_pred_row(f.get("claim"), e.get("id"), f.get("horizon_days"),
                                  f.get("check_metric"), made_on))
    return rows


def _to_day(s):
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def _due_day(r):
    made, hor = r.get("made_on"), r.get("horizon_days")
    if not made or not hor:
        return None
    return _to_day(made) + timedelta(days=int(hor))


def _due(made_on, horizon):
    """预测卡上要能算给读者到期日：没有到期日的预测无法核对（§2 第 3 行）。"""
    try:
        return (_to_day(made_on) + timedelta(days=int(horizon))).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def ship_digest(payload, ledger):
    """当夜提交内容的摘要 —— 幂等跳过的键。

    只盖"内容"：日期、条目、锚点审计、账本、未做清单。故意不盖 generated_at
    与耗时/调用数，否则重试夜永远算出不同摘要，spec §4 的幂等跳过就是死分支。
    """
    core = {"date": payload.get("date"),
            "events": payload.get("events"),
            "anchor_diff": payload.get("anchor_diff"),
            "not_run": payload.get("not_run"),
            "predictions": ledger}
    return hashlib.sha256(
        json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def settle(rows, today, verdicts=None):
    """把到期的 pending 行结算掉，返回 (本场结算统计, 全量新行)。

    自动判不了的一律进 unknown —— 不许折算成 miss 或 hit：现网"信号深度"就是把
    代理指标当结论，最后什么都没保证。统计只数本场新结算的，已结算的旧行不重复计数。
    """
    stats = {"due": 0, "hit": 0, "miss": 0, "unknown": 0, "auto_checkable_share": 0.0}
    verdicts = verdicts or {}
    auto_ok = 0
    out = []
    for raw in rows or []:
        r = dict(raw)
        if (r.get("status") or "pending") != "pending":
            out.append(r)
            continue
        due = _due_day(r)
        if due is None or due > _to_day(today):
            out.append(r)
            continue
        stats["due"] += 1
        if _CHECKABLE.search(r.get("check_metric") or ""):
            auto_ok += 1
        v = verdicts.get(r.get("claim"))
        r["status"] = "hit" if v == "hit" else ("miss" if v == "miss" else "unknown")
        r["settled_on"] = today
        stats[r["status"]] += 1
        out.append(r)
    if stats["due"]:
        stats["auto_checkable_share"] = round(auto_ok / stats["due"], 4)
    return stats, out


def stamp_forecast_status(events, ledger):
    """把账本里已结算的状态回填进条目的 forecasts，返回回填条数。

    页面有 待验证/已命中/未命中/无法自动判定 四档文案，但 `settle` 只改账本行。
    不回填的话那三档永远走"待验证"分支 —— 一条不可达的 UI 分支和空函数同罪。
    """
    done = {(r.get("event_id"), r.get("claim")): r for r in (ledger or [])
            if (r.get("status") or "pending") != "pending"}
    n = 0
    for e in events or []:
        for f in (e.get("forecasts") or []):
            r = done.get((e.get("id"), f.get("claim")))
            if r:
                f["status"] = r.get("status")
                f["settled_on"] = r.get("settled_on", "")
                n += 1
    return n


def prune_predictions(rows, today):
    """未到期全留，已结算只留 PRED_KEEP_DAYS 天。"""
    cut = _to_day(today) - timedelta(days=PRED_KEEP_DAYS)
    out = []
    for r in rows or []:
        if (r.get("status") or "pending") == "pending":
            out.append(r)
            continue
        if r.get("made_on") and _to_day(r["made_on"]) >= cut:
            out.append(r)
    return out


def load_prev_predictions(get, url, log=None):
    """读上一夜入库的账本。只有 404（第一夜）算"还没有账本"。

    其它失败一律往上抛：把 500/超时当成空账本，再让本场把整库写回去，
    等于一次网络抖动毁掉全部对账历史 —— 那比不跑一场严重得多。
    """
    log = log or (lambda s: None)
    try:
        # cache-bust 放在函数内部而不是调用方：这条读出来是要**整库写回**的，
        # 读到 CDN 里的旧副本就等于把上一夜之后的所有结算覆盖掉。放在调用方
        # 迟早会有新的调用点漏掉。
        raw = get(_bust(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log("[夜场] 预测账本不存在（%s 404），本场从空账本起" % url)
            return []
        raise
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    rows = parse_jsonl(raw)
    if raw.strip() and not rows:
        # 有内容却解析不出一行 = 账本坏了或被截断。这时当"空账本"处理，
        # 本场就会把整份历史写成只剩自己几行 —— 宁可红一晚。
        raise ValueError("预测账本非空却解析不出任何行（%s），拒绝在坏账本上续写" % url)
    return rows


def load_source_quality(get, url=None, log=None):
    """读白天的信源质量表（spec §2 第 4 行点名的外证之一）。

    取的是 `analysis_snapshot.json` 的 `quality` 字段，不是 `source_quality.json`：
    后者由 `build_rss_aggregator._save_source_quality` 写出来却从不发布 ——
    `update.yml` 的 `git add` 清单里没有它，提交前那步还 `rm -f` 掉它，现网实测恒 404。
    挂一个恒 404 的地址等于给"优质判定"接了一条永久断链：外证永远为空，
    而"无外证"在判据里和"低质"是两个结论。同一份评分的前半就在已发布的快照里。

    404 得起（第一夜、或白天从没写过它）；坏 JSON 必须抛 —— 把它当空表会让所有源
    都退化成"无外证"。默认值写 None 而不是 `url=SOURCE_QUALITY_URL`：那个常量在
    文件后半段才定义，当默认值用会让整个模块 import 不进来（默认参数在 def 时求值）。
    """
    log = log or (lambda s: None)
    url = url or SOURCE_QUALITY_URL
    try:
        raw = get(_bust(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log("[夜场] 质量快照不存在（404），优质判定只剩跨源同稿一路外证")
            return {}
        raise
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not raw.strip():
        return {}
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise ValueError("质量快照解析失败：%s" % e)
    quality = doc.get("quality") if isinstance(doc, dict) else None
    if not isinstance(quality, dict):
        # 读得动但没有 quality 字段 = 白天产物换了形状。当空表返回会让外证静默恒缺，
        # 这正是上一版的故障形态，所以这里宁可不跑。
        raise ValueError("质量快照里没有 quality 表（白天的产物形状变了），拒绝当'无外证'续跑")
    return quality


def _source_key_of(article):
    """信源标识：先取分块自带的源键（质量表就是按它索引的），再退到显示名/域名。

    质量表的键形如 `agihunt_0`，条目自己的 `source` 是显示名 "AGI Hunt" ——
    拿显示名去查表命中恒为 0，外证就永久为空。
    """
    key = (article.get("source_key") or "").strip()
    if key:
        return key
    src = (article.get("source") or "").strip()
    if src:
        tail = src.split("：")[-1].strip() or src
        return tail
    u = article.get("url") or ""
    try:
        return (urllib.parse.urlparse(u).hostname or "").lower()
    except ValueError:
        return ""


def _quality_tier(source_quality, key):
    if not key:
        return None
    v = (source_quality or {}).get(key)
    if isinstance(v, dict):
        for k in ("tier", "quality_tier", "grade", "score", "weight"):
            if v.get(k) is not None:
                return v[k]
        return None
    return v


def quality_signals(articles, source_quality):
    """给"内容优质判断"造机械输入 —— spec §2 明写这条不许由生成方自评。

    两路外证，都是模型自己猜不出来的东西：
    1. `dup_sources`：同一篇稿子被几个独立源搬运（标题词/二元组重叠即算同题）。
       被 N 家同搬就是通稿/转载的信号，比任何形容词都可核对。
    2. `tier`：白天质量快照（`analysis_snapshot.json` 的 `quality`）已经给过这个源的分数，直接引用。
    返回 {"sig:cN": {...}}；这些 id 既进 prompt，也是 `quality.basis` 唯一允许引用的集合。
    """
    sig = {}
    # 用 _keywords（中文二元组 + 拉丁词），不是草稿里的 _bigrams：
    # 名字留在注释里没关系，留在代码里就是每条事件必炸的 NameError。
    titles = [(a, _keywords(a.get("title") or "")) for a in articles or []]
    for i, (a, bg) in enumerate(titles):
        key = _source_key_of(a)
        dup = {key} if key else set()
        for j, (b, bg2) in enumerate(titles):
            if i == j or not bg or not bg2:
                continue
            if len(bg & bg2) >= 2:
                k2 = _source_key_of(b)
                if k2:
                    dup.add(k2)
        row = {"id": "sig:c%d" % (i + 1), "url": a.get("url", ""), "source": key,
               "dup_sources": len(dup), "has_full": bool(a.get("has_full")),
               "chars": count_chars(a.get("text") or "")}
        tier = _quality_tier(source_quality or {}, key)
        if tier is not None:
            row["tier"] = tier
        sig[row["id"]] = row
    return sig


def signals_note(ctx):
    """把信号写成 prompt 末尾的一段可引用清单。"""
    sig = ctx.get("quality_signals") or {}
    if not sig:
        return ""
    lines = ["", "===== 优质判定外证（basis 只能引用这里的 sig id）====="]
    for sid in sorted(sig, key=lambda s: [int(x) for x in re.findall(r"\d+", s)]):
        r = sig[sid]
        lines.append("%s 源=%s 全文=%s 字数=%d 同题搬运源数=%d%s" % (
            sid, r.get("source") or "?", "有" if r.get("has_full") else "无",
            r.get("chars", 0), r.get("dup_sources", 0),
            " 白天档位=%s" % r["tier"] if r.get("tier") is not None else ""))
    return "\n".join(lines) + "\n"


def reconcile(path, today, verdicts=None):
    """按文件读入的兼容入口（统计口径与 settle 同一份实现）。"""
    rows = []
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = parse_jsonl(f.read())
    stats, _ = settle(rows, today, verdicts)
    return stats


# ────────────────────────── 运行时：账号池与预算 ──────────────────────────

class Budget:
    """调用数、token、等待、429 各记各的账。

    等待不计失败是刻意的：白天的 `_LLM_429_POLL_SEC=180` 一到就"返回空由上层降级"
    （build_daily_insight.py:1656），把"在等限流窗口"和"真失败"混成一个数，
    读日志的人分不清是没跑成还是跑砸了。
    """

    def __init__(self, call_cap=80, time_cap_s=150 * 60, budget_tokens=DEFAULT_BUDGET_TOKENS):
        self.call_cap = int(call_cap)
        self.time_cap_s = int(time_cap_s)
        self.budget_tokens = int(budget_tokens)
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.wait_s = 0.0
        self.c429 = 0
        self.truncated = 0
        self.t0 = None

    def start(self):
        self.t0 = _now()

    def note_call(self, tokens_in=0, tokens_out=0):
        self.llm_calls += 1
        self.tokens_in += int(tokens_in or 0)
        self.tokens_out += int(tokens_out or 0)

    def note_wait(self, seconds):
        self.wait_s += float(seconds or 0)

    def note_truncated(self):
        """回复撞到输出上限（finish_reason=length）的独立一笔账。

        截断在产物里长得和"模型写得太短"一模一样：不记这一步，spec §3 那条
        `max_tokens` 待验假设就永远验不了，重写两轮也是在要求模型做不到的事。
        """
        self.truncated += 1

    def note_429(self, retry_after=0):
        self.c429 += 1
        self.note_wait(retry_after)

    def elapsed_s(self):
        # 必须是 `is not None`：写成 `if self.t0` 会把"起点正好是 0"当成"还没开始"，
        # 于是墙钟永远读 0、150 分钟的收口闸形同不存在（测试拿假钟一喂就现形）。
        return round(_now() - self.t0, 1) if self.t0 is not None else 0.0

    def over_time(self):
        """墙钟预算是否用尽。

        `time_cap_s` 不能只是个摆设：job 有 timeout-minutes 180，而产物是在循环
        之后才落盘的 —— 撞墙被平台掐死等于整晚既无产物也无红。主动在 150 分钟收口，
        剩下的条目记 not_run，已经做完的照样发布。
        """
        return self.time_cap_s > 0 and self.elapsed_s() >= self.time_cap_s

    def over_cap(self):
        return self.llm_calls > self.call_cap

    def snapshot(self):
        return {"llm_calls": self.llm_calls, "input_tokens": self.tokens_in,
                "output_tokens": self.tokens_out, "wait_s": round(self.wait_s, 1),
                "c429": self.c429, "truncated": self.truncated,
                "elapsed_s": self.elapsed_s(), "call_cap": self.call_cap}


def _now():
    return time.monotonic()


def clamp_workers(n, key_count):
    """并发档 = min(请求值, key 数, WORKERS_MAX)，且至少 1。

    超过 key 数的并发只会排队；超过 6 是把免费池往 429 墙上推。
    最终档位按首夜读数定（spec §4），但天花板钉死在这儿。
    """
    return max(1, min(int(n or 1), max(1, int(key_count or 1)), WORKERS_MAX))


class KeyPool:
    """多账号池当显式资源用：每 key 一槽、429 进冷却、并发>1 时 judge 让位给生成。

    免费 Agnes 池的弱点是并发与限流；旧写法是"轮到哪个 key 就用哪个"，
    被限流的 key 会立刻被再次派发。这里把冷却变成硬约束。
    "judge 需空余 ≥2"只在真并发时才有意义：并发 1 时没有任何生成任务会被 judge 抢走，
    那条保留反而会把单 key 部署锁死（永远凑不到 2 → 每条等满 wait_cap → 整场零合格）。
    """

    def __init__(self, keys, clock=None, workers=1):
        self._keys = list(keys or [])
        self._clock = clock or _now
        self._busy = set()
        self._cooling = {}
        self.workers = clamp_workers(workers, len(self._keys))

    def _is_free(self, k):
        return k not in self._busy and self._cooling.get(k, 0.0) <= self._clock()

    def idle(self):
        return sum(1 for k in self._keys if self._is_free(k))

    def total(self):
        return len(self._keys)

    def acquire(self, kind="generate"):
        if not self._keys:
            return None
        if kind == "judge" and self.workers > 1 and self.idle() < 2:
            return None
        for k in self._keys:
            if self._is_free(k):
                self._busy.add(k)
                return k
        return None

    def release(self, key):
        self._busy.discard(key)

    def mark_429(self, key, retry_after=0):
        self._busy.discard(key)
        ra = min(float(retry_after or 0) or 30.0, BACKOFF_CAP_S)
        self._cooling[key] = self._clock() + ra
        return ra

    def snapshot(self):
        t = self._clock()
        return {"keys_total": len(self._keys), "busy": len(self._busy),
                "idle": self.idle(),
                "cooling": sum(1 for k, until in self._cooling.items() if until > t)}


# ─────────────────────────── 锚点装载与提示词 ──────────────────────────────

def load_anchor_events(raw, source_sha=""):
    """读白天 daily-insight.json 作锚点。0 事件必须抛错，不许静默出空报告。"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        doc = json.loads(raw or "{}")
    except ValueError as e:
        raise ValueError("锚点 JSON 解析失败: %s" % e)
    events = doc.get("events") or []
    if not events:
        raise ValueError("锚点里没有事件（daily-insight.json events 为空）—— 拒绝产出空报告")
    out = []
    for i, e in enumerate(events):
        # 字段名以**现网产物**为准：白天写的是 label/category/articles[].url，
        # 事件里根本没有 title。按 title 读会让 12 个事件标题全空 → 每条过不了契约
        # → 每晚 100% 降级，而且降级发生在生成之后，每条还白烧 max_regen+1 次调用。
        links = list(e.get("key_links") or e.get("links") or [])
        links += [a.get("url") for a in (e.get("articles") or []) if isinstance(a, dict)]
        links += [c.get("url") for c in (e.get("citations") or []) if isinstance(c, dict)]
        seen, uniq = set(), []
        for l in links:
            if l and l not in seen:
                seen.add(l)
                uniq.append(l)
        out.append({
            "id": e.get("id") or ("evt%d" % (i + 1)),
            "title": e.get("label") or e.get("title") or e.get("theme") or "",
            "topic": e.get("category") or e.get("topic") or "",
            "summary": e.get("summary") or e.get("summary_zh") or "",
            "links": uniq,
        })
    return {"events": out, "date": doc.get("date", ""), "source_sha": source_sha}


PROMPT_FIELDS = ("narrative", "claims", "causal_chains", "forecasts", "quality", "citations")


def build_prompt(event, ctx):
    arts = ctx.get("articles") or []
    ids = ctx.get("ids") or {}
    blocks = []
    for i, a in enumerate(arts):
        cid = ids.get(a.get("url")) or ("c%d" % (i + 1))
        blocks.append("【证据 %s｜%s｜%s｜%d 字】\n%s" % (
            cid, a.get("source", ""), a.get("title", ""), count_chars(a.get("text") or ""),
            a.get("text") or ""))
    id_list = ", ".join("c%d" % (i + 1) for i in range(len(arts)))
    return (
        "你是深度分析员。只依据下面给出的证据写一条洞察，不得补充证据之外的事实或数字。\n"
        "事件：%s（主题 %s）\n\n"
        "输出一个 JSON 对象，字段必须是：%s。\n"
        "硬性要求（不满足会被判不合格并重写）：\n"
        "- narrative：成文论述，%d-%d 字（**按 %d 字写，别贴下限**），"
        "至少 %d 段且**每段不少于 %d 字**，段落式行文，"
        "禁止分点罗列的条目体；必须包含反证或限制条件（如“但该判断受限于…”“样本口径未覆盖…”）。"
        "段数够、每段短，仍判不合格。\n"
        "- claims：3-10 条，每条含 text/kind/evidence。evidence 是数组，元素只能从这批编号里选：%s；"
        "写别的编号等于引用不存在的内容，整条判不合格。\n"
        "- causal_chains：2-6 条，每条含 trigger/mechanism/outcome/confidence/evidence"
        "（evidence 同样只能取上面那批编号），写清为什么发生而不是只说发生了什么。\n"
        "- forecasts：1-4 条，每条含 claim(≤80字)/horizon_days(只能是 3、7 或 14，"
        "写成 30、90 一律判不合格 —— 永不到期的预测不算预测)/"
        "check_metric（到期用什么可核验指标判命中，不许写“未来如何”这类空话）。\n"
        "- quality：对证据本身下判断，verdict 只能取 一手/深度/数据支撑/转载/通稿/营销，"
        "score 0-100，why 20-120 字（**按 60-90 字写**，超 120 判不合格），"
        "basis 是数组且必须逐条引用下方「优质判定外证」里的 sig 编号"
        "（形如 sig:c1）；自由文本的理由一律判不合格。\n"
        "- citations：5-12 条，id 只能从下面的证据编号里选：%s；不得编造编号或链接。\n"
        "\n===== 证据（每篇均为全文，未截断）=====\n%s\n"
    ) % (event.get("title", ""), event.get("topic", ""), ", ".join(PROMPT_FIELDS),
         NARR_MIN, NARR_MAX, (NARR_MIN + NARR_MAX) // 2, PARAS_MIN, PARA_MIN,
         id_list or "（无）", id_list or "（无）", "\n\n".join(blocks))


# ─────────────────────────── 并发提交协议 ─────────────────────────────────

def publish(api, files, msg, last_sha=None, max_attempts=6, log=None):
    """只覆盖自己的路径 + CAS 更新 ref + 祖先链终检；冲突就重读 head 重试，永不 force。

    白天场在跑时必须照样提交成功 —— 所以不能沿用"有 in_progress 就拒绝推送"那套。
    并发安全来自三件事：tree 只含夜场路径（结构上不可能回滚别人的产物）、
    update_ref 用 CAS、提交后校验自己仍在 main 祖先链（白天 auto-commit 的
    push 重试含 reset --soft，真出过吞提交的前科）。
    """
    log = log or (lambda s: None)
    if not files:
        return {"status": "noop", "attempts": 0}
    if last_sha and api.is_ancestor(last_sha):
        return {"status": "skipped", "attempts": 0, "sha": last_sha}
    blobs = {}
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        head, base_tree = api.head_info()
        entries = []
        for path in sorted(files):
            if path not in blobs:
                blobs[path] = api.create_blob(files[path])
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blobs[path]})
        tree = api.create_tree(base_tree, entries)
        sha = api.create_commit(head, tree, msg)
        if api.update_ref(sha, force=False):
            if api.is_ancestor(sha):
                return {"status": "published", "sha": sha, "attempts": attempt}
            log("::warning title=夜场提交被回退|sha %s 不在 main 祖先链上，下夜重投" % sha)
            return {"status": "reverted", "sha": sha, "attempts": attempt}
    return {"status": "failed", "attempts": max_attempts}


# ───────────────────────────── 独立页渲染 ─────────────────────────────────

_ABS = ("http://", "https://")


def _esc(s):
    return html_mod.escape("" if s is None else str(s), quote=True)


def render_page(payload):
    """夜场自出的静态页。三条底线：转义、相对链接不上屏、空正文不长空卡片。"""
    events = []
    for e in (payload.get("events") or []):
        narrative = (e.get("narrative") or "").strip()
        if not narrative and not (e.get("degraded_reason") or "").strip():
            continue
        events.append(e)
    body = [render_event(e, made_on=payload.get("date", "")) for e in events]
    # 已结算的旧预测单独列出来：不然页面上"命中状态"这一列永远只会显示"待验证"，
    # 而账本里其实已经有 hit/miss —— 那就是把可核对的东西藏起来了。
    settled = [r for r in (payload.get("settled_predictions") or [])
               if (r.get("status") or "pending") != "pending"]
    if settled:
        rows = "".join("<li>%s（%s 到期）→ <b>%s</b>%s</li>" % (
            _esc(r.get("claim")), _esc(_due_label(r.get("made_on"), r.get("horizon_days"))),
            _esc(_FORECAST_STATE.get(r.get("status"), r.get("status"))),
            "｜判据 %s" % _esc(r.get("check_metric")) if (r.get("check_metric") or "").strip() else "")
            for r in settled[:40])
        body.append("<h3>已结算预测（近 %d 条）</h3><ul>%s</ul>" % (len(settled), rows))
    meta = "深度报告 · %s · 生成于 %s" % (_esc(payload.get("date", "")), _esc(payload.get("generated_at", "")))
    degraded_n = sum(1 for e in events if (e.get("degraded_reason") or "").strip())
    foot = "合格 %d 条 / 快讯 %d 条 / LLM 调用 %s 次 / 耗时 %s 秒" % (
        len(events) - degraded_n, degraded_n,
        _esc((payload.get("budget") or {}).get("llm_calls", "?")),
        _esc((payload.get("budget") or {}).get("elapsed_s", "?")))
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>深度报告 %s</title><style>%s</style></head><body>"
            "<header><h1>%s</h1><p>%s</p></header>%s<footer>%s</footer>"
            "</body></html>") % (_esc(payload.get("date", "")), _PAGE_CSS, meta,
                                 _esc(payload.get("generated_at", "")),
                                 "".join(body), foot)


_PAGE_CSS = ("body{font:16px/1.9 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
             "max-width:820px;margin:0 auto;padding:24px;color:#1b1f24;background:#fbfbfd}"
             "h1{font-size:22px}h2{font-size:19px;margin:0 0 6px}"
             "article{border-top:1px solid #e3e5ea;padding:18px 0;margin:0}"
             ".tag{display:inline-block;font-size:12px;color:#5a6472;margin-right:8px}"
             ".cap{background:#fff;border:1px solid #e3e5ea;border-radius:10px;padding:10px 12px;margin:12px 0}"
             ".warn{background:#fff7e6;border-color:#f0c36d}"
             "a{color:#1a56c4;word-break:break-all}footer{color:#5a6472;font-size:13px;padding:16px 0}"
             "p{margin:0 0 12px}")


def _due_label(made_on, horizon):
    """预测的到期日。没有到期日的预测无法核对，所以取不到时如实写"未标"，不编一个日期。"""
    try:
        return (_to_day(made_on) + timedelta(days=int(horizon))).isoformat()
    except (TypeError, ValueError, IndexError):
        return "未标"


def render_event(e, made_on=""):
    narrative = (e.get("narrative") or "").strip()
    degraded = (e.get("degraded_reason") or "").strip()
    paras = "".join("<p>%s</p>" % _esc(p) for p in re.split(r"\n{2,}", narrative) if p.strip())
    cites = []
    for c in (e.get("citations") or []):
        u = (c.get("url") or "").strip()
        if not u.startswith(_ABS):
            continue
        cites.append('<li><a href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
                     '<span class="tag">%s 字</span></li>' % (
                         _esc(u), _esc(c.get("title") or c.get("source") or u),
                         _esc(c.get("chars_used", "?"))))
    chains = "".join("<li>%s → %s → %s</li>" % (_esc(c.get("trigger")), _esc(c.get("mechanism")),
                                                 _esc(c.get("outcome")))
                   for c in (e.get("causal_chains") or []))
    cards = ""
    if not degraded:
        cards = "".join(
            '<div class="cap"><b>预测</b> %s<span class="tag">窗口 %s 天</span>'
            '<span class="tag">到期 %s</span><span class="tag">%s</span><br>判据：%s</div>' % (
                _esc(f.get("claim")), _esc(f.get("horizon_days")),
                _esc(_due_label(made_on, f.get("horizon_days"))),
                _esc(_FORECAST_STATE.get(f.get("status"), "待验证")),
                _esc(f.get("check_metric")))
            for f in (e.get("forecasts") or []))
    q = e.get("quality") or {}
    warn = ('<div class="cap warn">证据不足，按快讯处理：%s</div>' % _esc(degraded)) if degraded else ""
    return ("<article><h2>%s</h2><p class='tag'>%s · rubric %s · 优质判定 %s %s</p>%s%s"
            "<h3>因果</h3><ul>%s</ul>%s<h3>证据</h3><ul>%s</ul></article>") % (
        _esc(e.get("title")), _esc(e.get("topic")),
        _esc((e.get("rubric") or {}).get("mean", "?")),
        _esc(q.get("verdict")), _esc(q.get("score")),
        warn, paras, chains, cards, "".join(cites))


_FORECAST_STATE = {"pending": "待验证", "hit": "已命中", "miss": "未命中", "unknown": "无法自动判定"}


# ─────────────────────── I/O：锚点与全文池（只读现网产物） ───────────────────

PAGES_BASE = "https://kwei168.github.io/starhub/"
ANCHOR_URL = PAGES_BASE + "daily-insight.json"
CHUNK_URL_BASE = PAGES_BASE + "rss-data-%d.js"
# 分块数是白天按体积算的（build_rss_aggregator.py:373 `n_chunks = ceil(total/max_size)`），
# 夜场写死块数 = 第 4 块一出现就静默少读约三分之一全文池，而且表现是"全降级"不是报错。
# 现网实测第 3 块只剩 2.4% 余量，所以这里必须探测：探到 404 为止，上限只是防跑飞。
CHUNK_MAX = 16
CHUNK_URLS = [CHUNK_URL_BASE % i for i in range(3)]
# 预测账本走"读现网 → 结算 → 整库写回"，所以它必须是入库产物而不是 _night_state 里的临时文件：
# 只在当夜存在的账本 = 永远对不上账（到期核对发生在下一夜之后的运行里）。
PREDICTIONS_URL = PAGES_BASE + PREDICTIONS_NAME
# 优质判定的外证之一：白天已经算过一次的信源质量表（spec §2 第 4 行点名）。
SOURCE_QUALITY_URL = PAGES_BASE + "analysis_snapshot.json"


class RateLimited(Exception):
    def __init__(self, retry_after=0, reason=""):
        Exception.__init__(self, "429 retry_after=%s %s" % (retry_after, reason))
        try:
            self.retry_after = float(retry_after or 0)
        except (TypeError, ValueError):
            self.retry_after = 0.0
        self.reason = reason or str(retry_after)


def http_get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "starhub-deep-insight"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        code = r.status
        body = r.read()
    if code != 200:
        raise IOError("HTTP %s for %s" % (code, url))
    return body


_ASSIGN = re.compile(r"=\s*([\{\[])")


_BUST_SEQ = [0]


def _bust(url):
    """Pages 现测 `Cache-Control: max-age=600`，404 同样被缓存（见过 Age 481）。

    夜场是"读自己上一夜提交的东西再整库写回"的循环：锚点、账本、信源质量表都必须
    绕开缓存，否则人工补跑会读到旧内容并把旧账本原样覆盖回去 —— 静默丢一整夜。
    只用时间戳会在同一毫秒内撞出同一个值（现网两次连读就复现过），所以再叠一个自增序号。
    """
    _BUST_SEQ[0] += 1
    return url + ("&" if "?" in url else "?") + "cb=%d%d" % (
        int(time.time() * 1000) % 1000000, _BUST_SEQ[0] % 1000)


def parse_chunk(text):
    """从 rss-data-N.js 里取条目并归一成文章形态（两处调用方只认这一种形态）。

    现网真实形态是 `(window.__CHUNKS=window.__CHUNKS||[])[0]={"sources":[...]}`，
    开头的注释里也带等号 —— 用"第一个 ="会切错位置（本地 smoke 实测整池解析失败）。
    正确做法是找最后一个紧跟 `{`/`[` 的赋值等号，再用 raw_decode 取那段 JSON。
    """
    head = text[:400]
    hits = list(_ASSIGN.finditer(head))
    if not hits:
        raise ValueError("分块开头找不到赋值语句")
    start = hits[-1].start(1)
    doc, _end = json.JSONDecoder().raw_decode(text[start:])
    raw = []
    if isinstance(doc, dict):
        for s in doc.get("sources") or []:
            for it in s.get("items") or []:
                it = dict(it)
                it.setdefault("source_key", s.get("key") or s.get("name") or "")
                raw.append(it)
    else:
        raw = list(doc or [])
    return [_article_from(it) for it in raw]


def _article_from(it):
    url = (it.get("link") or it.get("u") or "").strip()
    body = (it.get("full_content") or it.get("fc") or "") or (it.get("summary") or it.get("s") or "")
    return {"url": url, "source": it.get("source") or it.get("source_key") or "",
            "source_key": it.get("source_key") or "",
            "title": it.get("title") or it.get("t") or it.get("title_zh") or "",
            "text": body, "has_full": bool(it.get("full_content") or it.get("fc"))}


def _fetch_chunk(get, url, log, retries, sleep=None, backoff_s=3.0):
    """返回 (raw, None) 或 (None, "gone") 或 (None, 错误摘要)。

    重试之间必须退避：现网 run 35735624747 第一趟就是死在 `ssl.SSLEOFError` 这种
    瞬时抖动上，而一块 56MB 的抓取紧挨着再试一次，等于在同一个坏窗口里撞两次。
    """
    sleep = sleep or time.sleep
    last = ""
    for attempt in range(max(1, int(retries))):
        try:
            return get(url + ("&" if "?" in url else "?") + "cb=%d"
                       % (int(time.time()) + attempt)), None
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None, "gone"
            last = "HTTP %s" % e.code
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:80])
        log("[全文池] 第 %d 次读取失败 %s: %s" % (attempt + 1, url, last))
        if attempt + 1 < max(1, int(retries)):
            nap = min(backoff_s * (2 ** attempt), 30.0)
            log("[全文池] %0.fs 后重试 %s" % (nap, url))
            sleep(nap)
    return None, last or "unknown"


def load_rss_pool(urls=None, get=http_get, log=None, retries=2, base=None, sleep=None):
    """全文池只读 GitHub Pages 上的分块：不碰白天的 Actions cache，也不写任何共享键。

    块数默认**探测**（`rss-data-0..N.js` 直到 404）：白天按体积切块，写死数字会在
    某次数据增长后静默少读一整块。分块里有一块 56MB，偶发抓取失败 —— 失败必须重试
    并最终**硬失败**：只 warning 就继续跑，会让证据面塌陷成"全部降级"的假成功产物。
    """
    log = log or (lambda s: None)
    pool, bad = {}, 0
    fetched = 0
    if urls is not None:
        seq = [(u, _fetch_chunk(get, u, log, retries, sleep=sleep)) for u in urls]
    else:
        base = base or CHUNK_URL_BASE
        seq = []
        for i in range(CHUNK_MAX):
            u = base % i
            got = _fetch_chunk(get, u, log, retries, sleep=sleep)
            if got[1] == "gone":
                break
            seq.append((u, got))
    for u, (raw, err) in seq:
        if err == "gone":
            continue
        if raw is None:
            bad += 1
            log("[全文池] 放弃读取 %s：%s" % (u, err))
            continue
        fetched += 1
        try:
            for a in parse_chunk(raw.decode("utf-8", "replace")):
                if a["url"]:
                    pool.setdefault(a["url"], a)
        except Exception as e:
            bad += 1
            log("[全文池] 解析失败 %s: %s" % (u, str(e)[:120]))
    if not pool:
        raise IOError("一个条目都没读到 —— 拒绝在空池上跑深度分析")
    if bad:
        raise IOError("有 %d 个分块没读到，证据面不完整；拒绝产出全降级报告" % bad)
    log("[全文池] 读到 %d 块、%d 条" % (fetched, len(pool)))
    return pool, bad


def _keywords(s):
    """中文二元组 + 长度≥3 的拉丁词。

    只按中文二元组匹配不够：事件标题常是翻译过的，与池里的英文原文标题对不上
    （现网实测 12/12 因此凑不满证据门）。
    """
    s = (s or "").lower()
    out = set(m.group(0) for m in re.finditer(r"[a-z0-9][a-z0-9.\-+]{2,}", s))
    for part in re.sub(r"[^一-鿿]", " ", s).split():
        for i in range(len(part) - 1):
            out.add(part[i:i + 2])
    return out


def title_overlap(a, b):
    """标题词/二元组重叠 ≥2 视为同题。阶段 1 不引向量检索，先用这个可测的粗筛。"""
    return len(_keywords(a) & _keywords(b)) >= 2


def _link_keys(links):
    """链接本身常带原文标题 slug（reddit/HN 尤其明显），是未被翻译过的强线索。"""
    out = set()
    for u in links or []:
        tail = (u or "").split("?")[0].rstrip("/").split("/")[-1]
        tail = re.sub(r"%[0-9a-fA-F]{2}", " ", urllib.parse.unquote(tail))
        if len(tail) < 8:
            continue
        out |= _keywords(tail.replace("_", " ").replace("-", " "))
    return out


def select_articles(event, pool, max_articles=12):
    """事件链接优先，再**跨源**补同题长文。

    只按同源补是错的：一个事件常只有 1 个源被引到，同源补文永远凑不出
    证据门要求的 ≥3 独立源（现网实测 12/12 因此全部降级）。
    取词也不能只用事件标题：标题是翻译过的，池里是英文原文 —— 所以并用
    标题 + 摘要 + 链接 slug（reddit/HN 的 slug 就是英文原标题）。
    """
    picked, seen = [], set()

    def take(a):
        if a and a["url"] not in seen and count_chars(a["text"]) > 0:
            seen.add(a["url"])
            picked.append(a)

    for u in (event.get("links") or []):
        take(pool.get((u or "").split("#")[0]))
    srcs = {a["source"] for a in picked if a["source"]}
    keys = set(_keywords(event.get("title") or ""))
    keys |= _keywords(event.get("summary") or "")
    keys |= _link_keys(event.get("links"))
    for a in list(picked):
        keys |= _keywords(a.get("title") or "")
    cands = []
    for url, a in pool.items():
        if url in seen or not a.get("has_full"):
            continue
        if count_chars(a["text"]) < GATE_LONG_CHARS:
            continue
        ov = len(keys & _keywords(a.get("title") or ""))
        if ov < 2:
            continue
        # 跨源优先补：同源的其它文章补不出"独立源"这一维，只能排后面
        cands.append((a["source"] in srcs, -ov, -count_chars(a["text"]), url, a))
    cands.sort()
    for _, _, _, _, a in cands:
        if len(picked) >= max_articles:
            break
        take(a)
    return picked[:max_articles]


# ────────────────────────── LLM 调用与判定回环 ─────────────────────────────

def call_llm(client, prompt, pool, budget, kind="generate", wait_cap_s=900,
             sleep=None, step_s=5.0):
    """借 key 才发请求：429 让该 key 进冷却并换 key，等待计入预算不计失败。

    `wait_cap_s` 是单条目等待上限 —— 白天侧是 180s 就"返回空由上层降级"
    （build_daily_insight.py:1656），对动辄几十秒的单次长上下文调用根本不够。
    """
    sleep = sleep or time.sleep
    waited = 0.0
    while True:
        key = pool.acquire(kind)
        if key is None:
            if waited >= wait_cap_s:
                raise RateLimited(0, "wait_cap_exceeded")
            sleep(step_s)
            waited += step_s
            budget.note_wait(step_s)
            continue
        try:
            out = client.complete(prompt, key=key, kind=kind)
        except RateLimited as e:
            # 429 这一支也必须推进 waited：否则"每次都能拿到 key、每次都 429"
            # 就是无限热循环（key 冷却被瞬时视为到期时最容易触发），
            # 单条目等待预算形同虚设，夜场会一路转到 job 的 180 分钟上限。
            cooldown = pool.mark_429(key, getattr(e, "retry_after", 0))
            budget.note_429(cooldown)
            waited += cooldown
            if waited >= wait_cap_s:
                raise RateLimited(0, "wait_cap_exceeded:429")
            continue
        except Exception:
            pool.release(key)
            raise
        pool.release(key)
        if getattr(client, "last_finish_reason", "") == "length":
            budget.note_truncated()
        budget.note_call(estimate_tokens(prompt), estimate_tokens(out or ""))
        return out


def _escape_raw_control(s):
    r"""把 JSON 字符串字面量里的裸换行/制表转义掉，其余一律不猜。

    §2 要求"至少 6 段"，而模型写长中文正文时最常见的就是把 `\n\n` 直接放进字符串里 ——
    这在 JSON 里非法，于是整条回复被读成"什么都没写"（现网第三跑 3 条里 2 条
    `narrative=0 字`、`citations=0 条` 就是这个）。等于我们自己的契约把深度要求
    变成了解析失败。

    刻意只做这一件事：内嵌裸引号不去猜（猜错会篡改正文），截断的也照样解析失败 ——
    截断必须走 `finish_reason` 记成 truncated，不许被"修好了"蒙混成"模型写得太短"。
    """
    out = []
    in_str = False
    esc = False
    for ch in s:
        if not in_str:
            if ch == '"':
                in_str = True
            out.append(ch)
            continue
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = False
            out.append(ch)
            continue
        if ch == "\n":
            out.append("\\n")
            continue
        if ch == "\r":
            continue
        if ch == "\t":
            out.append("\\t")
            continue
        out.append(ch)
    return "".join(out)


def parse_model_json(text):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else ""
    s, e = t.find("{"), t.rfind("}")
    if s < 0 or e <= s:
        return None
    body = t[s:e + 1]
    try:
        return json.loads(body)
    except ValueError:
        pass
    try:
        return json.loads(_escape_raw_control(body))
    except ValueError:
        return None


_UNSAFE_SCHEME = re.compile(r"^\s*(?:javascript|data|vbscript|file):", re.I)


def _clean_url(u):
    """引用链接的出口清洗：非绝对链接一律不要，路径里的裸中文要编码，
    但**已经编码过的 `%20` 不许再编一次**（双重编码会把现网好链接变成死链 ——
    这条在白天侧 cleanLink 上踩过两轮）。"""
    u = (u or "").strip()
    if not u or u == "#" or _UNSAFE_SCHEME.match(u):
        return ""
    if not u.startswith(("http://", "https://")):
        return ""
    if re.search(r"%[0-9a-fA-F]{2}", u):
        # 已经编码过的就原样放过：再编一次 `%20` 会变成 `%2520`，
        # 好链接当场变死链 —— 白天侧 cleanLink 就在这上面翻过两轮。
        return u
    try:
        parts = urllib.parse.urlsplit(u)
        safe = "%:/?#[]@!$&'()*+,;=~-._"
        path = urllib.parse.quote(parts.path, safe=safe)
        query = urllib.parse.quote(parts.query, safe=safe)
        frag = urllib.parse.quote(parts.fragment, safe=safe)
        net = parts.netloc
        if any(ord(c) > 127 for c in net):
            net = urllib.parse.quote(net, safe="@:[]~._-")
        return urllib.parse.urlunsplit((parts.scheme, net, path, query, frag))
    except (ValueError, UnicodeError):
        return ""


def normalize_candidate(cand, ids_map):
    """把模型返回的形状归一成契约认识的对象形态。

    动机是现网第一跑的真实崩溃（run 35735624747）：模型把 citations 返回成
    `["c1", "https://…"]` 这种字符串数组，实现按 dict 取 `.get()` 直接 AttributeError，
    整场无产物。归一只管形状、不管内容 —— 形状不对的行会被填成"必然过不了契约"的对象，
    于是降级而不是崩，也不会把空壳当合格。
    引用只认我们自己发的 chunk id：模型自带 URL 一律不采信（否则"假链接即硬失败"
    只剩校验标签，实测会漏出编造域名上屏）。
    """
    def rows(key, extra=()):
        primary = {"claims": "text", "causal_chains": "mechanism", "forecasts": "claim"}[key]
        out = []
        for r in (cand.get(key) or []):
            if isinstance(r, dict):
                out.append(r)
            elif isinstance(r, str) and r.strip():
                row = {k: "" for k in extra}
                row[primary] = r.strip()
                out.append(row)
        cand[key] = out

    cites = []
    for c in (cand.get("citations") or []):
        cid = c.get("id") if isinstance(c, dict) else (c.strip() if isinstance(c, str) else None)
        if cid in ids_map:
            cites.append({"id": cid, "url": _clean_url(ids_map[cid])})
    cand["citations"] = cites
    for key in ("claims", "causal_chains"):
        for r in (cand.get(key) or []):
            if not isinstance(r, dict):
                continue   # 整条是字符串的行交给下面的 rows() 统一成形
            ev = r.get("evidence")
            if isinstance(ev, str):
                # 模型常把 evidence 写成 "c1" 或 "c2, c3"：直接迭代字符串会把
                # "c1" 炸成 'c' 和 '1'，于是好引用被判成假链接（现网实测）。
                r["evidence"] = [x for x in re.split(r"[,，;；\s]+", ev.strip()) if x]
            elif ev is None:
                r["evidence"] = []
    rows("claims", ("kind", "evidence"))
    rows("causal_chains", ("trigger", "mechanism", "outcome", "evidence"))
    rows("forecasts", ("claim", "horizon_days", "check_metric"))
    for f in cand["forecasts"]:
        f.setdefault("claim", "")
        f.setdefault("check_metric", "")
    q = cand.get("quality")
    if isinstance(q, str) and q.strip():
        # 整段字符串当 quality：把原文塞进 why，其余留空，让契约去判它不合格
        cand["quality"] = {"verdict": "", "score": 0, "why": q.strip(), "basis": []}
    elif not isinstance(q, dict):
        cand["quality"] = {}
    return cand


def rubric_of(raw):
    out = {}
    for k in ("narrative", "causal", "forecast", "quality"):
        try:
            out[k] = max(0.0, min(1.0, float((raw or {}).get(k, 0.0))))
        except (TypeError, ValueError):
            out[k] = 0.0
    out["mean"] = round(sum(out[k] for k in ("narrative", "causal", "forecast", "quality")) / 4.0, 4)
    return out


JUDGE_PASS = 0.75


def build_judge_prompt(cand, ctx):
    """judge 必须看到完整正文与完整证据：只喂片段就打"论述深度"分是自相矛盾的。"""
    arts = ctx.get("articles") or []
    return (
        "你是评审。只依据下面给出的材料，为这篇洞察按四项各打 0-1 分："
        "narrative（是否成文论述、≥2500字、≥6段、含反证或限制条件、不是分点罗列）、"
        "causal（是否给出机制链条而非复述现象）、forecast（预测是否可核验、窗口是否合理）、"
        "quality（对信源优质与否的判断有无依据、是否只是自评）。\n"
        '只输出 JSON：{"narrative":0.0,"causal":0.0,"forecast":0.0,"quality":0.0,"notes":"≤80字"}\n'
        "任一项不达标就必须给低于 0.75 的分；不要因为它写得长就给高分。\n\n"
        "===== 待评正文（全文）=====\n%s\n\n===== 证据（%d 篇，均为全文）=====\n%s\n"
    ) % ((cand.get("narrative") or ""), len(arts),
         "\n\n".join((a.get("text") or "") for a in arts))


def judge_event(client, cand, ctx, key_pool, budget, wait_cap_s=900, sleep=None):
    raw = parse_model_json(call_llm(client, build_judge_prompt(cand, ctx), key_pool, budget,
                                    "judge", wait_cap_s=wait_cap_s, sleep=sleep))
    return rubric_of(raw)


def deepen_one(event, pool, client, budget, key_pool, max_regen=2, wait_cap_s=900, sleep=None,
               source_quality=None):
    """一个事件：装证据 → 过证据门 → 生成 → 契约判定 + judge 独立打分 → 不过就重写。"""
    arts = select_articles(event, pool)
    gate_ok, gate_why = evidence_gate(arts)
    ctx = assemble_context(arts, budget_tokens=budget.budget_tokens)
    ctx["ids"] = {"c%d" % (i + 1): a["url"] for i, a in enumerate(ctx["articles"])}
    ids = set(ctx["ids"])
    # 优质判定的外证：跨源同稿计数 + 白天给过的源档位。没有这一步，`basis` 只能靠模型编。
    ctx["quality_signals"] = quality_signals(ctx["articles"], source_quality)
    basis_ids = set(ctx["quality_signals"])
    rec = dict(event)
    rec["context_stats"] = {"articles": len(ctx["articles"]), "dropped": len(ctx["dropped"]),
                            "total_tokens": ctx["total_tokens"], "total_chars": ctx["total_chars"],
                            # spec §3 要"丢整篇并记理由"。只留 url 列表的话，事后读产物的人
                            # 分不开"素材本来就这么点"与"预算把证据挤掉了"这两种完全不同的结论。
                            "dropped_articles": [
                                {"url": d.get("url", ""), "tokens": d.get("tokens", 0),
                                 "reason": d.get("reason", "")} for d in ctx["dropped"]],
                            "dropped_urls": [d["url"] for d in ctx["dropped"]]}
    if not gate_ok:
        rec.update({"narrative": (event.get("summary") or "")[:DEGRADED_NARR_MAX],
                    "degraded_reason": gate_why, "claims": [], "causal_chains": [],
                    "forecasts": [], "citations": [],
                    "quality": {"verdict": "转载", "score": 0, "why": "证据不足未做优质判定",
                                "basis": ["evidence_gate"]},
                    "rubric": {"mean": 0.0}})
        return rec
    prompt = (build_prompt(event, ctx) + signals_note(ctx))
    cand, last_fails, score = {}, [], {"mean": 0.0}
    parse_echo = None
    for attempt in range(max_regen + 1):
        raw = call_llm(client, prompt, key_pool, budget, "generate",
                       wait_cap_s=wait_cap_s, sleep=sleep)
        cand = dict(parse_model_json(raw) or {})
        if not cand and raw:
            # 解析不出来时，日志里只剩"narrative 0 字"，与"模型真的没写"长得一模一样。
            # 现网 evt_20260923_008 就是这样：十个字段全空、truncated=0，谁也不知道它返回了什么。
            # 留头尾各 200 字进产物，下一跑才谈得上修解析。
            parse_echo = {"chars": len(raw), "head": raw[:200], "tail": raw[-200:]}
        cand.setdefault("id", event["id"])
        cand.setdefault("title", event.get("title", ""))
        cand.setdefault("topic", event.get("topic", ""))
        cand = normalize_candidate(cand, ctx["ids"])
        ok, fails = validate_event(cand, valid_ids=ids, valid_basis=basis_ids)
        last_fails = fails
        if ok:
            score = judge_event(client, cand, ctx, key_pool, budget,
                                wait_cap_s=wait_cap_s, sleep=sleep)
            if score["mean"] >= JUDGE_PASS:
                cand["rubric"] = score
                cand["contract_fails"] = []
                cand["regen_used"] = attempt
                cand["context_stats"] = rec["context_stats"]
                return cand
        else:
            score = {"mean": 0.0}
        if attempt < max_regen:
            prompt = (build_prompt(event, ctx) + signals_note(ctx)) + "\n上一版不合格原因（必须逐条修掉）：%s\n" % "; ".join(
                fails or ["judge 均分 %.2f 低于 %.2f" % (score["mean"], JUDGE_PASS)])
    cand["degraded_reason"] = "重写 %d 次仍不合格" % max_regen
    if parse_echo:
        cand["parse_echo"] = parse_echo
    cand["narrative"] = (cand.get("narrative") or "")[:DEGRADED_NARR_MAX]
    cand["forecasts"] = []
    cand["rubric"] = score
    cand["contract_fails"] = last_fails
    cand["regen_used"] = max_regen
    cand["context_stats"] = rec["context_stats"]
    return cand


def build_anchor_diff(anchor_events, records):
    """夜场对每个锚点事件做了什么，必须逐条留痕（spec §5）。

    恒空的 anchor_diff 与"名字里带深度却什么都不保证"是同一个病：
    读产物的人需要一个能核对的地方，看"白天的 12 个事件"到夜里变成了什么。
    """
    by_id = {r.get("id"): r for r in records or [] if isinstance(r, dict)}
    diff = []
    for ev in anchor_events or []:
        eid = ev.get("id")
        r = by_id.get(eid)
        before = len(ev.get("key_links") or ev.get("links") or [])
        if r is None:
            diff.append({"op": "drop", "id": eid, "reason": "not_run:incomplete",
                         "evidence_before": before, "evidence_after": 0})
            continue
        why = (r.get("degraded_reason") or "").strip()
        after = len(r.get("citations") or [])
        if why:
            diff.append({"op": "drop", "id": eid, "reason": why,
                         "evidence_before": before, "evidence_after": after})
        else:
            diff.append({"op": "keep", "id": eid,
                         "reason": "过证据门与四条判据（judge 均分 %s）" % (
                             (r.get("rubric") or {}).get("mean")),
                         "evidence_before": before, "evidence_after": after})
    return diff


def build_payload(events, anchor_meta, budget, date_str, key_count=0, workers=1,
                  anchor_diff=None, predictions_reconciled=None):
    good = [e for e in events if not (e.get("degraded_reason") or "").strip()]
    b = dict(budget.snapshot(), budget_tokens=budget.budget_tokens,
             source_sha=anchor_meta.get("source_sha", ""),
             anchor_date=anchor_meta.get("date", ""),
             degraded=len(events) - len(good), qualified=len(good),
             key_count=int(key_count), workers=int(workers))
    return {"date": date_str, "generated_at": now_bj_iso(), "engine": SCHEMA_VERSION,
            "budget": b,
            "anchor_diff": anchor_diff or [],
            "predictions_reconciled": predictions_reconciled or
            {"due": 0, "hit": 0, "miss": 0, "unknown": 0, "auto_checkable_share": 0.0},
            "events": events}


_BJ_TZ = timezone(timedelta(hours=8))


def now_bj_iso():
    """北京时间的 ISO 串。偏移量只能有一个：`datetime.now(timezone.utc) + 8h` 的 tzinfo
    仍是 UTC，`isoformat()` 会自己写 `+00:00`，再手拼 `+08:00` 就得到
    `2026-09-22T23:52:05+00:00+08:00` —— `fromisoformat` 直接解析不了，
    而 spec §5 把这个字段交给页面"更新于"与历史归档读。
    """
    return datetime.now(_BJ_TZ).replace(microsecond=0).isoformat()


# ───────────────────────────── 模型客户端与真 API ──────────────────────────

AGNES_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("DEEP_MODEL", "agnes-2.5-flash")


def env_keys():
    """AGNES_API_KEY（可逗号分隔）+ AGNES_API_KEYS 汇成池；只返回数量与掩码。"""
    ks = []
    for name in ("AGNES_API_KEY", "AGNES_API_KEYS"):
        for k in (os.environ.get(name, "") or "").split(","):
            k = k.strip()
            if k and k not in ks:
                ks.append(k)
    return ks


class AgnesClient:
    """一次调用一个 key：轮换与冷却归 KeyPool 管，这里只负责发与如实报错。"""

    def __init__(self, model=DEFAULT_MODEL, max_tokens=12000, temperature=0.3, post=None):
        self.model = model
        self.max_tokens = int(max_tokens)
        self.last_finish_reason = ""
        self.temperature = temperature
        self._send = post or self._http_post

    def _http_post(self, payload, key):
        req = urllib.request.Request(
            AGNES_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited(e.headers.get("Retry-After", 30))
            raise RuntimeError("Agnes HTTP %s" % e.code)

    def complete(self, prompt, key=None, kind="generate"):
        if not key:
            raise RuntimeError("没拿到 key 就发请求 = 绕过账号池调度")
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        doc = self._send(body, key)
        # 记下 finish_reason：被 max_tokens 截断的回复看起来就是"JSON 解析不出来 / 正文太短"，
        # 不记就会把截断当成模型能力问题重写两轮再降级（现网第一跑正是这样分不清的）。
        try:
            self.last_finish_reason = (doc.get("choices") or [{}])[0].get("finish_reason") or ""
        except (AttributeError, IndexError, TypeError):
            self.last_finish_reason = ""
        try:
            return doc["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("模型返回结构异常：%s" % str(doc)[:160])


class FakeClient:
    """仅用于本地/CI 管道自检：产一份刚好合规的样本，证明装配与判定链通。

    它不是模型 —— 任何 publish 路径都必须拒绝它（main 里有硬闸），
    否则会把假内容当深度洞察发上线。
    """

    def __init__(self, judge_pass=True, rate_limit_first=False):
        self.judge_pass = judge_pass
        self.rate_limit_first = rate_limit_first
        self.calls = []

    def complete(self, prompt, key=None, kind="generate"):
        self.calls.append(kind)
        if self.rate_limit_first and kind == "generate" and self.calls.count("generate") == 1:
            raise RateLimited(30)
        if kind == "judge":
            v = 0.9 if self.judge_pass else 0.4
            return json.dumps({"narrative": v, "causal": v, "forecast": v, "quality": v})
        ids = re.findall(r"c\d+", prompt.split("证据编号里选")[-1][:200]) or ["c%d" % i for i in range(1, 7)]
        return json.dumps({
            "narrative": "\n\n".join("论证与数据推演%s，但该判断仍受样本量与统计口径限制。" % ("依" * 380)
                                     for _ in range(7)),
            "claims": [{"text": "论断%d" % i, "kind": "causal", "evidence": [ids[0] if ids else "c1"]}
                       for i in range(4)],
            "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                               "confidence": 0.6, "evidence": [ids[0] if ids else "c1"]} for _ in range(3)],
            "forecasts": [{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                           "check_metric": "同类竞品发布数>=3", "status": "pending"}],
            "quality": {"verdict": "一手", "score": 82,
                        "why": "依据来源分布与是否一手材料判定，未采用生成方自评",
                        "basis": (re.findall(r"sig:c\d+", prompt or "") or ["sig:c1"])[:3]},
            "citations": [{"id": (ids[i] if i < len(ids) else "c%d" % (i + 1))} for i in range(6)],
        }, ensure_ascii=False)


class GithubDataApi:
    """真 Data API 通道：head/blob/tree/commit/ref。夜场只写自己的路径。"""

    def __init__(self, repo="Kwei168/starhub", token=None):
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise RuntimeError("缺 GITHUB_TOKEN，无法提交夜场产物")

    def _req(self, method, path, payload=None):
        req = urllib.request.Request(
            "https://api.github.com" + path,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            method=method,
            headers={"Authorization": "token " + self.token,
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    def head_info(self):
        ref = self._req("GET", "/repos/%s/git/ref/heads/main" % self.repo)
        sha = ref["object"]["sha"]
        tree = self._req("GET", "/repos/%s/git/commits/%s" % (self.repo, sha))["tree"]["sha"]
        return sha, tree

    def create_blob(self, content):
        import base64
        doc = self._req("POST", "/repos/%s/git/blobs" % self.repo,
                        {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})
        return doc["sha"]

    def create_tree(self, base_tree, entries):
        doc = self._req("POST", "/repos/%s/git/trees" % self.repo,
                        {"base_tree": base_tree, "tree": entries})
        return doc["sha"]

    def create_commit(self, parent, tree, msg):
        doc = self._req("POST", "/repos/%s/git/commits" % self.repo,
                        {"message": msg, "tree": tree, "parents": [parent]})
        return doc["sha"]

    def update_ref(self, sha, force=False):
        try:
            self._req("PATCH", "/repos/%s/git/refs/heads/main" % self.repo,
                      {"sha": sha, "force": bool(force)})
            return True
        except urllib.error.HTTPError as e:
            if e.code == 422 and not force:
                return False      # 父不符 = CAS 失败，交回上层重读 head 重试
            raise

    def is_ancestor(self, sha):
        """只认 ahead/identical —— 我方 sha 真在 main 历史里。

        `diverged`/`behind` 恰恰是"提交已被白天的 auto-commit 甩出主线"的形态
        （compare/<sha>...main 在主线另起一线时返回 diverged）。以前把四个状态全收，
        等于 spec §4 那条"前科终检"恒真：被吞掉也会报告 published、退出码 0。
        """
        try:
            doc = self._req("GET", "/repos/%s/compare/%s...main" % (self.repo, sha))
        except urllib.error.HTTPError as e:
            if e.code in (404, 409, 410):
                return False
            raise
        return doc.get("status") in ("ahead", "identical")


# ───────────────────────────── 编排与入口 ──────────────────────────────────

def night_run(purpose="test", events_limit=12, client=None, budget_tokens=DEFAULT_BUDGET_TOKENS,
              call_cap=80, keys=None, get=http_get, anchor_raw=None, pool=None, out_dir="_night_state",
              date_str=None, log=None, sleep=None, wait_cap_s=900, urls=None,
              api_factory=None, max_regen=2, workers=1, pred_raw=None,
              pred_url=PREDICTIONS_URL, verdicts=None, quality_raw=None,
              quality_url=SOURCE_QUALITY_URL):
    """跑一整夜。purpose=test 只落盘不提交；publish 才走 CAS 提交。"""
    log = log or (lambda s: None)
    keys = list(keys if keys is not None else env_keys())
    if client is None and not keys:
        # 这道拒绝必须在任何出网之前：下面锚点、分块池、质量快照三连读是几十 MB，
        # 而"没有 key"的场这些字节一条也用不上 —— 先读再抛等于把钱花光才报告没钱。
        raise RuntimeError(
            "没有 AGNES_API_KEY/AGNES_API_KEYS，夜场拒绝空跑：无 key 时每条都会等满 "
            "wait_cap（12 条 × 900s = 3h）才收场，整场只留下 checkpoint 和一个绿勾。")
    os.makedirs(out_dir, exist_ok=True)
    date_str = date_str or (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")
    anchor_raw = anchor_raw if anchor_raw is not None else get(_bust(ANCHOR_URL))
    blob = anchor_raw if isinstance(anchor_raw, bytes) else str(anchor_raw).encode("utf-8")
    anchor = load_anchor_events(anchor_raw, source_sha=hashlib.sha256(blob).hexdigest()[:12])
    events = anchor["events"][:max(1, int(events_limit))]
    if pool is None:
        pool, _bad = load_rss_pool(urls=urls, get=get, log=log, sleep=sleep)
    # 优质判定的外证之一：白天的信源质量表。读不到只少一路外证（404 得起），
    # 但坏文件必须炸 —— 当空表用会让所有源都变成"无外证"，与"低质"是两回事。
    if quality_raw is None:
        source_quality = load_source_quality(get, quality_url, log=log)
    else:
        raw_q = quality_raw
        if isinstance(raw_q, (bytes, bytearray)):
            raw_q = raw_q.decode("utf-8", "replace")
        source_quality = json.loads(raw_q) if isinstance(raw_q, str) and raw_q.strip() else raw_q
        if not isinstance(source_quality, dict):
            raise ValueError("quality_raw 必须是 dict 或 JSON 对象文本")
        # 注入路径也要收成同一种形状：调用方十有八九传的是"那份现网产物"整份
        # （`{"generated_at":…, "quality":{…}}`），而 HTTP 路径取的是 quality 子表。
        # 两边形状不一致时，注入方拿到的是外层文档，查表命中恒 0 且不报错 ——
        # 和这次在线上踩到的"外证恒缺"是同一个形态。
        if isinstance(source_quality.get("quality"), dict):
            source_quality = source_quality["quality"]
    budget = Budget(call_cap=call_cap, budget_tokens=budget_tokens)
    budget.start()
    kp = KeyPool(keys, workers=workers)
    log("[夜场] 并发档 workers=%d（key %d 把，天花板 %d）" % (
        kp.workers, kp.total(), WORKERS_MAX))
    if client is None:
        # 这里原来是 `client or FakeClient()`：主入口一旦忘传 client，夜场就悄悄拿假正文
        # 跑完整场，产出的东西与真洞察长得一样，还能走完判定与渲染。发布路径另有硬闸，
        # 但"test 模式下没人看得出产物是假的"同样不可接受，所以默认必须是真客户端。
        # （无 key 的拒绝已经提到函数开头，在出网之前就抛了。）
        client = AgnesClient()
    ck = os.path.join(out_dir, "deep-%s.jsonl" % date_str)
    prev_recs = load_records(ck)
    done = {r.get("id") for r in prev_recs if r.get("id")}
    recs = []
    stopped_by_cap = False
    stop_reason = ""
    failed = []
    for ev in events:
        if ev["id"] in done:
            log("[夜场] %s 已在 checkpoint 里，跳过" % ev["id"])
            continue
        if budget.over_time():
            stopped_by_cap = True
            stop_reason = "wallclock"
            log("::warning title=夜场窗口将尽|已用 %.0fs ≥ 墙钟预算 %ds，剩余条目记 not_run"
                "（产物照写，不等平台掐）" % (budget.elapsed_s(), budget.time_cap_s))
            break
        if budget.llm_calls >= call_cap:
            stopped_by_cap = True
            stop_reason = "budget"
            log("[夜场] 调用预算 %d 已用完，剩余条目记 not_run" % call_cap)
            break
        # 单条的等待预算要按"离墙钟还剩多少"缩水再传进去。`wait_cap_s` 原来是每次调用
        # 各领 900s：一条事件最多 generate×3 + judge×1 = 4 次，最坏 6×900s 全花在等上，
        # 于是"每条 ≤900s"的约定形同虚设，而循环顶那道墙钟闸根本来不及问。
        item_wait = wait_cap_s
        if budget.time_cap_s > 0:
            item_wait = max(1.0, min(wait_cap_s, budget.time_cap_s - budget.elapsed_s()))
        try:
            r = deepen_one(ev, pool, client, budget, kp, wait_cap_s=item_wait, sleep=sleep,
                           max_regen=max_regen, source_quality=source_quality)
        except RateLimited as e:
            log("[夜场] %s 等待超上限(%s)：记 not_run，不阻断全场" % (ev["id"], e))
            continue
        except Exception as e:
            # 一次瞬时错误（Agnes 5xx、上游分块抖动）不能把整晚换掉：产物在循环之后才落盘，
            # 异常穿出去就是"钱花完了、JSON/HTML 一个都没有、还看不出为什么"。
            failed.append("%s:%s" % (ev.get("id"), type(e).__name__))
            log("::warning title=条目失败但继续|%s 抛 %s（%s），本场其余条目照做" % (
                ev.get("id"), type(e).__name__, str(e)[:120]))
            continue
        recs.append(r)
        append_jsonl(ck, [r])
        # 只报"完成"与字数不够看：现网那场就是 3 条全降级，必须当场看到为什么。
        why = (r.get("degraded_reason") or "").strip()
        fails = "; ".join((r.get("contract_fails") or [])[:3])
        log("[夜场] %s %s narrative=%d 字 rubric=%s%s%s" % (
            ev["id"], "降级" if why else "合格",
            count_chars(r.get("narrative") or ""),
            (r.get("rubric") or {}).get("mean"),
            " 原因=%s" % why if why else "",
            " 判据=%s" % fails if fails else ""))
    # 产物 = 本场新做的 + checkpoint 里已做完的，按锚点顺序排；
    # 少了后半截就是"重试夜上线半套产物"那个坑。
    by_id = {r.get("id"): r for r in (prev_recs + recs)}
    ship = [by_id[e["id"]] for e in events if e.get("id") in by_id]
    all_degraded = bool(ship) and all((r.get("degraded_reason") or "").strip() for r in ship)
    if all_degraded:
        log("::warning title=本场全部降级|所有条目证据不足，产物只含快讯，不发布")
    # 预测账本：先结算上一夜的到期项，再把本场合格条目 appended，最后按窗口淘汰。
    ledger = load_prev_predictions(get, _bust(pred_url), log=log) if pred_raw is None \
        else parse_jsonl(pred_raw)
    stats, ledger = settle(ledger, date_str, verdicts)
    # 先把已结算的历史状态回填进本场条目，再追加本场新预测（新预测必然是 pending）。
    settled_rows = [r for r in ledger if (r.get("status") or "pending") != "pending"]
    stamp_forecast_status(ship, settled_rows)
    ledger = prune_predictions(ledger + pred_rows(ship, date_str), date_str)
    payload = build_payload(ship, anchor, budget, date_str, key_count=kp.total(),
                            workers=kp.workers,
                            anchor_diff=build_anchor_diff(events, ship),
                            predictions_reconciled=stats)
    # 账本里已结算的行随产物发布：页面上的"已结算预测"区靠它，只写 predictions.jsonl
    # 的话读者在页面上永远只看到"待验证"（§5 要预测卡含到期与命中状态）。
    payload["settled_predictions"] = settled_rows
    payload["not_run"] = missing(events, [x.get("id") for x in ship],
                                  stop=stop_reason)
    # 逐条异常不再穿毁全场，但也不能 invisible：跑了几条挂了几条要进产物，
    # 否则"三条全挂 + 页面空白"和"三条都没做"读起来一模一样。
    payload["failed_items"] = failed
    jpath = os.path.join(out_dir, "daily-deep-%s.json" % date_str)
    hpath = os.path.join(out_dir, "deep-insight.html")
    ppath = os.path.join(out_dir, PREDICTIONS_NAME)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(hpath, "w", encoding="utf-8") as f:
        f.write(render_page(payload))
    with open(ppath, "w", encoding="utf-8") as f:
        for r in ledger:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {"payload": payload, "json": jpath, "html": hpath, "predictions": ppath,
           "budget": budget.snapshot(), "published": None}
    if purpose != "publish":
        log("[夜场] purpose=%s，不提交（产物只在 %s）" % (purpose, out_dir))
        return out
    want = [e["id"] for e in events]
    if all_degraded or not can_publish([{"id": i} for i in want],
                        [x.get("id") for x in ship],
                        budget_used_calls=budget.llm_calls, call_cap=call_cap,
                        stopped_by_cap=stopped_by_cap):
        log("::warning title=本场不发布|完成 %d/%d（全降级或未撞预算的半成品），本场不提交" % (
            len(ship), len(want)))
        out["published"] = {"status": "blocked", "attempts": 0}
        return out
    if isinstance(client, FakeClient):
        raise RuntimeError("purpose=publish 禁止用 FakeClient：那会把自检样本当洞察发上线")
    files = {"daily-deep-%s.json" % date_str: open(jpath, "rb").read(),
             "deep-insight.html": open(hpath, "rb").read(),
             PREDICTIONS_NAME: open(ppath, "rb").read()}
    out["published_files"] = sorted(files)
    # CAS 协议第 2 步"幂等跳过"必须真活着：当夜原地重试那趟如果产物一字未改，
    # 不该再花一次提交（历史上这里传的是默认 last_sha=None，整条分支是死代码）。
    sha_path = os.path.join(out_dir, "published-%s.json" % date_str)
    # 幂等键只盖"内容"，不盖时间戳：generated_at / elapsed_s / wait_s 每跑一趟都不同，
    # 用整份文件字节做摘要时，这条跳过分支在生产里永远进不去 —— 重试夜必然双提交。
    digests = {"ship": ship_digest(payload, ledger)}
    last_sha = ""
    if os.path.exists(sha_path):
        try:
            with open(sha_path, encoding="utf-8") as f:
                prev = json.load(f)
            if prev.get("digests") == digests:
                last_sha = prev.get("sha") or ""
                log("[夜场] 与上次提交内容一致，走幂等跳过（sha %s）" % last_sha[:8])
        except ValueError:
            log("::warning title=上次提交记录不可读|幂等跳过失效，本场可能重复提交同一份产物")
    api = (api_factory or GithubDataApi)()
    out["published"] = publish(api, files,
                               msg="ci(deep-insight): %s 夜场产物 %d 条" % (date_str, len(ship)),
                               last_sha=last_sha, log=log)
    if isinstance(out["published"], dict) and out["published"].get("sha"):
        with open(sha_path, "w", encoding="utf-8") as f:
            json.dump({"sha": out["published"]["sha"], "digests": digests,
                       "at": now_bj_iso()}, f, ensure_ascii=False)
    log("[夜场] 提交结果 %s" % out["published"])
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="夜间独立深度洞察管线（阶段 1）")
    ap.add_argument("--purpose", choices=("test", "publish"), default="test")
    ap.add_argument("--events-limit", type=int, default=12)
    ap.add_argument("--out", default="_night_state")
    ap.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS)
    ap.add_argument("--cap-calls", type=int, default=80)
    ap.add_argument("--wait-cap", type=int, default=900)
    ap.add_argument("--workers", type=int, default=1,
                    help="并发档；实际取 min(此值, key 数, %d)，首夜读数定档后不要凭感觉调大" % WORKERS_MAX)
    ap.add_argument("--date", default=None)
    ap.add_argument("--fake-client", action="store_true",
                    help="只验装配与判定链，不产真洞察；purpose=publish 时会被拒绝")
    a = ap.parse_args(argv)
    lines = []

    def log_live(s):
        # 以前是 `log=lines.append` 再只打最后 6 行：现网那场三条全降级（narrative 0/196/199 字），
        # 而逐条降级理由与 contract_fails 全部被截在 tail 之外 —— 失败原因根本读不出来。
        lines.append(s)
        try:
            print(s, flush=True)
        except UnicodeEncodeError:
            print(str(s).encode("ascii", "replace").decode(), flush=True)

    out = night_run(purpose=a.purpose, events_limit=a.events_limit, out_dir=a.out,
                    budget_tokens=a.budget_tokens, call_cap=a.cap_calls,
                    wait_cap_s=a.wait_cap, date_str=a.date,
                    client=FakeClient() if a.fake_client else None,
                    keys=env_keys(), log=log_live,
                    get=http_get)
    b = out["budget"]
    pb = out["payload"]["budget"]
    print("[夜场] 条目 %d（合格 %d / 快讯 %d / 未做 %d）LLM 调用 %d 次、等待 %.0fs、429 %d 次、耗时 %.0fs" % (
        len(out["payload"]["events"]), pb.get("qualified", 0), pb.get("degraded", 0),
        len(out["payload"].get("not_run") or []), b["llm_calls"], b["wait_s"], b["c429"],
        b["elapsed_s"]))
    pr = out["payload"].get("predictions_reconciled") or {}
    if b.get("truncated"):
        print("::warning title=输出被截断|本场 %d 次回复撞到 max_tokens："
              "长论述产不出来时先查输出上限，别判模型能力" % b["truncated"])
    print("[夜场] 账号池 %d 把 / 并发档 %s｜到期预测 %d（命中 %d 未中 %d 判不了 %d）｜锚点审计 %d 条" % (
        pb.get("key_count", 0), pb.get("workers"), pr.get("due", 0), pr.get("hit", 0),
        pr.get("miss", 0), pr.get("unknown", 0), len(out["payload"].get("anchor_diff") or [])))
    if a.fake_client:
        print("[夜场] 注意：本次为 FakeClient 管道自检，正文不是真洞察")
    for l in lines[-6:]:
        print(l)
    # 退出码必须能区分"没上线"和"上线了"：Actions 只看退出码，
    # 全降级/半成品是数据条件（只 ::warning），而提交被回退/CAS 用尽是本场的失败。
    pub = out.get("published")
    if isinstance(pub, dict) and pub.get("status") in ("reverted", "failed"):
        print("::error title=夜场未上线|提交状态 %s（attempts=%s）" % (
            pub.get("status"), pub.get("attempts")))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
