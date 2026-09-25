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
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

SCHEMA_VERSION = "deep-insight/v1"

NARR_MIN, NARR_MAX = 4000, 10000
# 2500→4000 / 4000→10000 的理由不是"模型能写更多"这么简单，而是旧上限只造成过损失：
#   · 现网单趟写出过 6,950 / 4,338 字（run 35801635817），两条都被"超上限"判死；
#   · 最近一场两段式 8 段里被组装裁掉 2 段（run 35806236237），token 全付了正文丢掉；
#   · 证据侧实测每条 12 篇全文、9.4k~855k 字，长度根本不受证据约束。
# 上限不再兼管"防水分"：防水分交给 EVID_CHARS（结构判据）与 judge 的 density 维度（agent 主判）。
# 下限必须一起抬：只抬上限等于把"写多少看模型心情"的老路重新打开 —— A 方案存在的全部理由
# 就是单趟稳定停在 1,748/2,307/1,902 字。
EVID_CHARS = 1500   # 正文每 1,500 字至少要换一篇不同证据支撑，长而空在这里判死


def required_sources(n_chars):
    """写 n 字至少要引几篇不同来源 —— 派生自 EVID_CHARS，判据与 prompt 共用这一份。

    以前两处的数字各算各的（prompt 里写死"至少 3 篇"），改了常量行为不变。
    """
    return -(-int(n_chars or 0) // EVID_CHARS)
PARAS_MIN = 6
# 单说"2500-4000 字"模型交回来的是 1748/2307/1902（run 35749459676 三条实测），
# 重写两轮也停在同一水平：总量它不接，段数它接。所以把配额下沉到段，
# 并按 PARAS_MIN*PARA_MIN >= NARR_MIN 留出余量（字数口径含标点，实测略偏小）。
PARA_MIN = NARR_MIN // PARAS_MIN + 50
# 逐段成文把"写不够"解决了（现网 run 35801635817：6,950 / 4,338 字），紧接着撞上的是
# 另一头 —— 每段实测落在 700~1,100 字，6 段就是 4.3k~7k，超出 §2 上限被整条作废。
# 所以每段既给下限也给上限与目标值，让"6 段 × 每段"乘出来正好落在硬区间内。
PERA_MAX = NARR_MAX // PARAS_MIN
# 每段目标只留一个数：以前 PERA_TARGET(1166) 生产里没人用，进 prompt 的是
# 现算的 (PARA_MIN+PERA_MAX)//2(1191) —— 两个"目标值"并存且不同，改了常量也改不动行为。
PERA_TARGET = (PARA_MIN + PERA_MAX) // 2
# 段数上限必须被"段数 × 每段目标 ≤ 总上限"约束住，否则丢段是结构必然而不是偶发：
# 原来 SECTIONS_MAX=9 而 9×1191=10,719 > 10,000，每段都写到位就一定超线被裁
# （这正是方案一要消灭的"付了 8 段的钱丢 2 段"）。
SECTIONS_MIN = PARAS_MIN
SECTIONS_MAX = min(PARAS_MIN + 3, NARR_MAX // PERA_TARGET)


def outline_section_cap(n_sources):
    """段数上限还要受"有几篇不同证据可分"约束。

    每段要一个不重复的主证据 ⇒ 只有 4 篇时排 6 段必然是两段抢同一篇，
    而抢来的那一段除了复述没有别的内容可写。这是结构，不是风格问题。
    """
    return max(0, min(SECTIONS_MAX, int(n_sources or 0)))


def outline_rejects(secs):
    """提纲层面的结构缺陷检查。返回拒因，没问题返回 None。

    `primary` 缺失**不当拒因**：模型没写过这个新字段时整批退回单趟，等于用新字段
    把两段式废掉（而两段式正是压住长度方差的那一步）。没声明就取该段第一条证据顶上，
    只拦真正的"两段抢同一篇"。
    """
    prim = []
    for s in secs or []:
        p = (s.get("primary") or "").strip()
        if not p:
            evs = [e for e in (s.get("evidence") or []) if isinstance(e, str) and e.strip()]
            p = evs[0].strip() if evs else ""
        prim.append(p)
    prim = [p for p in prim if p]
    if not prim:
        return None
    dup = sorted(set(p for p in prim if prim.count(p) > 1))
    if dup:
        return "%s —— 两段抢同一篇主证据，多出来的那段只能复述" % dup[:4]
    return None
EVENTS_DEFAULT = 12
MAX_REGEN = 2
# 单趟路径一次要吐完整条：正文上限 + 满额结构字段。按模块自己的口径
# （CJK 1 字≈1 token）实测 10,000 字 + 满额结构 ≈ 13.5k token，
# 客户端默认 12,000 必然截断 —— 而截断在产物里长得和"模型写不长"一模一样。
SINGLE_PASS_OUT_TOKENS = NARR_MAX + 3600
CLAIM_MIN, CLAIM_MAX = 3, 10
CHAINS_MIN, CHAINS_MAX = 2, 6
FORECAST_MIN, FORECAST_MAX = 1, 4
CITE_MIN, CITE_MAX = 5, 12
HORIZONS = (3, 7, 14)
FORECAST_CLAIM_MAX = 80
CHAIN_FIELD_MAX = 170
WHY_MIN, WHY_MAX = 20, 120
QUALITY_VERDICTS = ("一手", "深度", "数据支撑", "转载", "通稿", "营销")

# ── 判定去噪的三个数 + 每趟成本（都放在各自依赖之后：CALL_CAP 由它们算出来）──
JUDGE_SAMPLES = 2
# 采纳/停滞边界取实测复评极差 0.17 的一半。白天那条 ±0.02 是它自己"改前/改后同一版配对"
# 的方差，与我们"两个被改写过的版本比中位均值"不是同一个量 —— 这里不引它当依据。
ADOPT_MARGIN = 0.09
# 距合格线几个噪声带以内算"差一点点"（继续重写），之外的判定当"救不回来"。
# 现网两条 0.6375 的降级形态落在这个带里，一条 0.425 的落在外面。
HOPEFUL_BANDS = 2
# 一次尝试的调用数（逐项点名，别再用"判定 1"那种旧账）：
#   提纲 2（首问 + 主证据撞车那一次重问）
# + 逐段 2*SECTIONS_MAX（每段太短会补写一次，`staged_generate` 里那趟 `again`）
# + 结构 1 + 判定 JUDGE_SAMPLES（批 3 的去噪双采样）+ 逐条核查 CLAIM_MAX（批 2 的 faith，满额）
# 现网实测：run 35940113012 三条事件 71 次调用（其中 faith 8 次），
# 与本式的差在 regen 没跑满 —— 这个数拿来当"开一条之前要留多少"的预留，不拿来当成绩。
OUTLINE_MAX_CALLS = 2
# 这是**标称**成本（按我们要求它写的段数上限 SECTIONS_MAX 算）。真实成本随模型给的段数走：
# 第四轮审查用 12 段提纲复现到一趟 37 次（outline 2 + section 24 + structure 2 + judge 2 + faith 7）。
# 所以别把 `PER_ATTEMPT_CALLS * (MAX_REGEN+1)` 当成一条的上界 —— 上界没人保证，
# 闸只能"每趟问一次"（见 deepen_one 里的 regen_cut_by_budget），并把超顶记成可读的一格。
PER_ATTEMPT_CALLS = OUTLINE_MAX_CALLS + 2 * SECTIONS_MAX + 1 + JUDGE_SAMPLES + CLAIM_MAX
# CALL_CAP 按 spec §7 的决定**不跟着最坏值抬**（12×3×31=1140 是纸面数）：
# 真实约束是墙钟不是次数，先把 S6/S7 跑成一场 test 实测"每合格条目调用数"再定档。
# 撞顶就按已批的风险⑤口径处理：保单条完整，砍没开写的（`_cutoff` 的预留就是为此存在）。
CALL_CAP = 684          # 与批 3 之前同档：12 条 × 3 趟 × 旧 19 次/趟
# 一条最坏要花多少：跑满 MAX_REGEN+1 趟。开一条之前按这个数预留，而不是按单趟 ——
# faith 现在每趟合格版都可能跑，用单趟数预留会照样超发。
ITEM_CALLS_MAX = (MAX_REGEN + 1) * PER_ATTEMPT_CALLS
# 段数与每段目标是乘出来的：PARAS_MIN >= SECTIONS_MAX 时"每段够长"与"总长不超线"
# 互斥（批 3 的变异表差点把这条不变量弄丢，这里钉死而不是靠注释提醒）。
assert PARAS_MIN <= SECTIONS_MAX, "每段下限乘段数会顶破正文上限"

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
# 主干 ref 只许有这一个名字。以前 `heads/main` 硬编码在 head_info/update_ref 里，
# 于是"验证走分支"根本走不了 —— 三场手动验证全部打在主干上，把白天构建唯一一发
# push 重试撞光（2026-09-23 14:00 北京场红）。ref 现在必须由调用方显式给。
MAIN_REF = "main"
# 并发档上限：spec §4 `worker = min(len(api_keys), 6)`。免费 Agnes 池被 6 把以上
# 并发推，换来的不是吞吐是 429 墙；档位最终值等首夜读数，但不许越过这个天花板。
WORKERS_MAX = 6
# 429 退避封顶（spec §4）。上游偶尔给 `Retry-After: 3600`，照单全收等于一把 key
# 整夜报废；池子本来只有几把，剩下的会被"每条 ≤3 次生成 + 1 次判定"挤爆。
# 封顶不是忽略限流信号：仍然按封顶值冷却。
BACKOFF_CAP_S = 120

DEGRADED_NARR_MAX = 200
FOLD_MIN_CHARS = 600    # 短到不像"一条洞察"的（快讯）不必折叠，折叠是给长文用的
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


def _para_number_sets(text):
    """每段的数值签名。段按空行/换行切，短于 60 字的碎片不算一段。"""
    ps = [p.strip() for p in re.split(r"\n+", text or "") if len(p.strip()) >= 60]
    return [set(_NUM_TOKEN.findall(p)) for p in ps]


_NUM_TOKEN = re.compile(r"\d+(?:\.\d+)?%?")


def restatement_from_sets(sets, min_shared=3, pair_floor=0.30):
    """段落级复述率：同一批硬数据被几段反复消费。**这是"长而空"唯一的机械依据。**

    为什么不是字面重复：现网两条合格长文（09-23 的 9,857 字、09-24 的 8,754 字）
    的句级重复率都读 0.0、12 字 n-gram 只有 0.015，而按"段落共享数值集合"量分别是
    0.636 与 0.46 —— 毛病是"换句话再说一遍"，字面口径结构上看不见它。

    不做"版本号/模型名打折"那类旋钮：加了之后整段照抄（4 段里 3 段同一批数）
    反而被折扣抹平。Jaccard 的分母天然吸收它 —— 全文都在提"5.5"时，
    共享 3 个 / 并集 20 个 = 0.15 过不了 0.30 的线，不需要额外折扣。
    """
    n = len(sets or [])
    if n < 2:
        return {"rate": 0.0, "paras": n, "restated_paras": 0, "pairs": 0, "recycled": []}
    cnt = {}
    for s in sets:
        for x in s:
            cnt[x] = cnt.get(x, 0) + 1
    S = [set(s) for s in sets]
    live = [i for i, s in enumerate(S) if s]
    if len(live) < 2:
        return {"rate": 0.0, "paras": len(live), "restated_paras": 0, "pairs": 0,
                "recycled": []}
    bad, pairs = set(), 0
    for a in range(len(live)):
        for b in range(a + 1, len(live)):
            i, j = live[a], live[b]
            sh = S[i] & S[j]
            union = len(S[i] | S[j]) or 1
            if len(sh) >= min_shared and len(sh) / float(union) >= pair_floor:
                bad.add(i)
                bad.add(j)
                pairs += 1
    recycled = sorted(((c, k) for k, c in cnt.items() if c >= 3), reverse=True)[:8]
    return {"rate": round(len(bad) / float(len(live)), 4), "paras": len(live),
            "restated_paras": len(bad), "pairs": pairs,
            "recycled": [{"fact": k, "paras": c} for c, k in recycled]}


def restatement_rate(text):
    return restatement_from_sets(_para_number_sets(text))


def restate_fact_list_text(cand):
    """"被 ≥3 段反复消费的数"清单，一处渲染两处用（judge 的输入、重写反馈的点名）。

    以前只有 judge 看得见这份清单，重写反馈给的是"删掉换句话说的重复段"这种形容词 ——
    模型拿到形容词没法下手，而清单是我们自己数出来的，不花任何调用。
    """
    m = restatement_rate((cand or {}).get("narrative") or "")
    return "、".join("%s（%d 段）" % (x["fact"], x["paras"]) for x in m["recycled"][:6]) or "（无）"


def annotate_observability(cand):
    """把"长而空"的量写进候选。**每条路径都要走这里** —— 证据门早退那条曾经根本不写，
    于是产物里有的条目有、有的没有，读的人无法区分"没测"与"测了是 0"。
    """
    m = restatement_rate(cand.get("narrative") or "")
    cand["restate_rate"] = m["rate"]
    cand["restate_pairs"] = m["pairs"]
    if m["recycled"]:
        cand["restate_top"] = m["recycled"]
    return cand


def clip_for_degrade(cand):
    """降级只裁正文，但"本来写了多长"必须留在产物里。

    本轮为了回答"4,000 上限是不是削掉了内容"，只能从 `trimmed_sections` 反推 ——
    那是观测缺口：裁完再问长度，问到的只是裁后的碎片。
    预测照旧清空：证据不足没资格做断言（§2 第 3 行）。
    """
    cand["narrative_chars_full"] = count_chars(cand.get("narrative") or "")
    cand["narrative"] = (cand.get("narrative") or "")[:DEGRADED_NARR_MAX]
    cand["forecasts"] = []
    return cand


_VERDICT_SPLIT = re.compile(r"[/、,，;；]")


def repair_quality_verdict(cand):
    """枚举被写成复合值时归一，而不是烧掉整条。

    现网 evt_20260923_008：素材 115,487 字、7 段已成文、8 claims / 5 chains 齐全，
    `contract_fails` 只有一条 "quality.verdict '一手/数据支撑' 不在枚举" ——
    枚举里两个合法值中间一个斜杠，重写两轮（约 20 次调用）后整条降成 200 字快讯。
    这是序列化缺陷不是内容缺陷，代价与过错不成比例。
    """
    q = cand.get("quality")
    if not isinstance(q, dict):
        return cand
    v = q.get("verdict")
    if not isinstance(v, str) or v in QUALITY_VERDICTS:
        return cand
    parts = [p.strip() for p in _VERDICT_SPLIT.split(v) if p.strip()]
    legal = [p for p in parts if p in QUALITY_VERDICTS]
    if not legal:
        return cand          # 拆不出任何合法值：照判不合格，归一不是橡皮章
    q["verdict"] = legal[0]
    q["verdict_repaired"] = v
    return cand


# 阶梯次序是**从"证据链不高于最差那一环"推出来的**，不是 spec §2 给的（那一行只列枚举与分数/字数
# 边界，不谈次序，也不谈整条与逐源的关系）。次序反过来用会静默改变吸收结果，改动要过 #79 那条讨论。
VERDICT_RANK = {v: i for i, v in enumerate(QUALITY_VERDICTS)}


def _verdict_of(raw):
    """一块的 verdict 归一：逐字合法就用，复合值按平铺那套拆，拆不出就算非法。

    与 `repair_quality_verdict` 同一把尺（`_VERDICT_SPLIT`）：两处口径分叉的话，
    斜杠值在整条上能被救回来、在逐源表里却把整块挤出局（审查 P1-2）。
    """
    if raw in QUALITY_VERDICTS:
        return raw, None
    if isinstance(raw, str):
        parts = [p.strip() for p in _VERDICT_SPLIT.split(raw) if p.strip()]
        hit = [p for p in parts if p in QUALITY_VERDICTS]
        if hit:
            return hit[0], raw
    return None, None


def _absorb_per_source_quality(q):
    """模型把 `quality` 写成"逐信源的表"（`{"c1": {...}, "c2": {...}}`）时的形状吸收。

    第 37 场现网 `evt_20260925_r14` 就是这个形状：12 家各一个对象（数的是该场产物里
    `quality` 那一格的 12 个键，见 `_scratch/dl37/_night_state/daily-deep-2026-09-25.json`），
    结果 verdict/score/why/basis 四条硬判据同时违约，8,872 字的正文直接烧掉。
    出现率按现测口径讲（`_scratch/qshape_census2.txt`：本地 13 份产物、去重 26 条、
    长文 22 条里 **1 条**是表形状；`quality.verdict None + score` 那组死因指纹另有 2 条，
    但那两条不是表形状）—— 是"值得兜住"而不是"到处都在发生"。
    三条规则，都为的是不替模型编话：
    1) 取**最差那一档**（`VERDICT_RANK`）：一条证据链的质量不高于它最差的那篇来源；
    2) `verdict/score/why` 三格只能转述**同一块**的断言 —— 上一版把"跨表取最低分"与
       "同档取最长 why"混着用，场 37 那条会印成"通稿 62"，而 62 是另一档（深度）那块的分数，
       这个配对没有任何来源断言过（审查 P1-1）。同档里挑分值最低且 why 写完了的那一块；
       该档全都写不完时照实交最低分那块，让 why 那格判不合格 —— 退让不等于补话；
    3) 非法 verdict 的块不参与（不能把没读懂的值端上来），复合值按平铺那套归一并留痕。
    """
    if not isinstance(q, dict) or not q:
        return None
    blocks = [v for v in q.values() if isinstance(v, dict) and "verdict" in v]
    if len(blocks) < 2 or len(blocks) != len(q):
        return None                       # 不是"每篇一个"的形状：别乱猜
    legal = []
    for v in blocks:
        verdict, repaired = _verdict_of(v.get("verdict"))
        if verdict is None:
            continue
        blk = dict(v, verdict=verdict)
        if repaired:
            blk["verdict_repaired"] = repaired
        legal.append(blk)
    if not legal:
        return None                       # 全是非法 verdict：那是内容问题，交回判据判死
    worst = max(VERDICT_RANK[v["verdict"]] for v in legal)
    tier = [v for v in legal if VERDICT_RANK[v["verdict"]] == worst]

    def _why_written(v):
        w = v.get("why")
        return isinstance(w, str) and count_chars(w) >= WHY_MIN

    def _rank(v):
        # 缺分或越界（0-100 之外）的那颗排在后面：它自己会死在 score 判据上，
        # 但同档还有一颗合法的数时没理由拖着整条一起烧（审查第二轮 P1-b）。
        s = v.get("score")
        if not isinstance(s, (int, float)) or isinstance(s, bool):
            return (2, 10 ** 9)
        return (0 if 0 <= s <= 100 else 1, s)

    # 三格同源：挑中的这一块报什么就发什么，不再从别的块借分数、借理由。
    pickable = [v for v in tier if _why_written(v)] or tier
    chosen = min(pickable, key=_rank)
    out = {"verdict": chosen.get("verdict"), "score": chosen.get("score"),
           "why": chosen.get("why") or "",
           # basis 是"整条用了哪些外证"，不是"最差那篇的证据"：判定看的正是这批来源，
           # 只收那一块的会把读者指向一篇而不是整条的证据面。
           "basis": sorted({b for v in legal for b in (v.get("basis") or [])}),
           "absorbed_from": len(legal)}
    if chosen.get("verdict_repaired"):
        out["verdict_repaired"] = chosen["verdict_repaired"]
    return out


def repair_quality_fields(cand):
    """quality 这一组的形状归一：verdict 复合值 + `why` 超上界。

    `why` 超上界是 09-24 现网 evt_20260924_001 的死因（170 字 > 120），与 verdict
    同族。只往回收不往回填：太短的 why 是模型真没写理由，补字等于伪造证据。
    裁掉的部分不留原长就等于什么都没发生 —— 下一跑还是读不出它写了多长。
    """
    absorbed = _absorb_per_source_quality(cand.get("quality"))
    if absorbed:
        cand["quality"] = absorbed
    repair_quality_verdict(cand)
    q = cand.get("quality")
    if not isinstance(q, dict):
        return cand
    why = q.get("why")
    if isinstance(why, str):
        w = count_chars(why)
        if w > WHY_MAX:
            q["why_chars_full"] = w
            while count_chars(why) > WHY_MAX and len(why) > WHY_MIN:
                why = why[:-1]
            q["why"] = why.strip()
    return cand


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
    # 池子里只有 4 篇时，"至少引 5 篇"是一条**满足不了**的要求 —— 与刚拆掉的那类钳制同族：
    # 造一个供给给不出的下限，只会把扎实的小条目一律判死，而不会逼出更多来源。
    supply = len(valid_ids) if valid_ids is not None else None
    cite_floor = min(CITE_MIN, supply) if supply else CITE_MIN
    if not cite_floor <= len(cites) <= CITE_MAX:
        fails.append("citations %d 条，须在 [%d,%d]" % (len(cites), cite_floor, CITE_MAX))
    if len(set(ids)) != len(ids):
        fails.append("citations id 有重复")
    if valid_ids is not None:
        fake = [i for i in ids if i not in valid_ids]
        if fake:
            fails.append("citation id 不在检索池里（假链接）：%s" % fake[:4])
    inv = ev.get("invented_citations") or []
    if inv:
        fails.append("引用了我们没发过的编号 %d 条（假链接硬失败）：%s" % (len(inv), inv[:4]))
    for c in cites:
        u = c.get("url") or ""
        if not u.startswith("http://") and not u.startswith("https://"):
            fails.append("citation url 不是绝对链接（死链）：%s" % (u or "<空>")[:60])
            break

    # 反水分第一道（结构判据）：正文每 EVID_CHARS 字至少要换一篇不同证据支撑。
    # 界按字数派生，不是拍的阈值 —— 9,000 字只压在 2 篇上就是复述，不是分析。
    #
    # 这里以前写成 `min(len(cited_ids), ceil(n/EVID_CHARS))`：要求被"模型自己引了几篇"
    # 钳住 —— 9,857 字要 7 篇，只引 5 篇时要求自动降到 5，而 CITE_MIN=5 让 5 篇合法。
    # 于是这条判据在它唯一该出手的长文场景里**必然通过**，等于没有判据
    # （现网 evt_20260923_011 素材池 12 篇 / 635,321 字，只引 5 篇写 9,857 字照样合格）。
    cited_ids = {c.get("id") for c in cites}
    # 要求按字数派生，但**上界只能是"我们供给了几篇不同来源"**。
    # 这与刚拆掉的那道钳制不是一回事：旧的 `min(len(cited_ids), …)` 按"模型自愿引了几篇"
    # 收敛，它可以少引再少要求；这里按上游装配给出的来源数收敛，是**我们的**责任边界 ——
    # 池子只有 6 篇时，9,900 字的东西无论如何引不出 7 篇，那不该判模型不合格。
    # 供给不足本身要看得见：note 里记 sources_short，批 4（证据门按长度派生）拿它定档。
    supply = supply if supply is not None else len(cited_ids)
    need_cov = min(required_sources(n), max(supply, 1))
    ev["sources_short"] = (n, required_sources(n), supply) if supply < required_sources(n) else None
    used_cov = set()
    for cl in (ev.get("claims") or []):
        used_cov |= set(cl.get("evidence") or [])
    # 只认这条自己引过的编号：claims 挂一个 citations 里没有的编号不算覆盖。
    # 不求交的话，"多写几条 claim、各挂一个不同编号"就能白拿覆盖数，正文照样是水
    # （对抗审查 P1-4 复现：9,598 字只引 5 篇，claims 铺满 c1..c10 被判合格）。
    used_cov &= cited_ids
    if need_cov and len(cited_ids) < need_cov:
        fails.append("正文 %d 字只引了 %d 篇不同来源（要 >=%d 篇，每 %d 字换一篇）："
                     "素材在池子里，多引不额外花钱" % (n, len(cited_ids), need_cov, EVID_CHARS))
    elif need_cov and len(used_cov) < need_cov:
        fails.append("正文 %d 字只压在 %d 篇不同证据上（要 >=%d 篇）：长而空不算深度" % (
            n, len(used_cov), need_cov))

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
    # bool 是 int 的子类：`score: true` 过去一路过关，页面印成 "优质判定 通稿 True"（审查第三轮 D）
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
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
    # "几篇"之外还要记"几家"：`source_key` 常带篇号后缀（src3_1），按 `source` 归一家，
    # 没有 source 的退回 source_key 前缀、再退回 url。覆盖契约说的是"每 1,500 字换一篇
    # 独立来源"，只记文章数就没法判断这条要求到底可不可满足（任务 #67）。
    srcs = set()
    for a in keep:
        srcs.add(a.get("source") or (a.get("source_key") or "").split("_")[0]
                 or a.get("url") or "")
    srcs.discard("")
    return {"articles": keep, "dropped": dropped, "total_tokens": tok, "total_chars": chars,
            "sources": len(srcs)}


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


def can_publish(events, done, budget_used_calls=0, call_cap=CALL_CAP, stopped_by_cap=False):
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


def _day_or_none(s):
    """账本里的日期来自上一夜发布的 JSONL：一行坏账不许把整晚烧掉。

    `settle`/`prune_predictions` 在产物落盘**之前**执行，`_to_day` 直接抛
    ValueError 就是"钱花完了、JSON/HTML 一个都没有"（审查 P2-4 复现）。
    """
    try:
        return _to_day(s)
    except (TypeError, ValueError, IndexError):
        return None


def _due_day(r):
    made, hor = r.get("made_on"), r.get("horizon_days")
    if not made or not hor:
        return None
    d = _day_or_none(made)
    if d is None:
        return None
    try:
        return d + timedelta(days=int(hor))
    except (TypeError, ValueError):
        return None


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
        made = _day_or_none(r.get("made_on"))
        if made is not None and made >= cut:
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


# ────────────────────────── 运行时：账号池与预算 ──────────────────────────

class Budget:
    """调用数、token、等待、429 各记各的账。

    等待不计失败是刻意的：白天的 `_LLM_429_POLL_SEC=180` 一到就"返回空由上层降级"
    （build_daily_insight.py:1656），把"在等限流窗口"和"真失败"混成一个数，
    读日志的人分不清是没跑成还是跑砸了。
    """

    def __init__(self, call_cap=CALL_CAP, time_cap_s=150 * 60, budget_tokens=DEFAULT_BUDGET_TOKENS):
        self.call_cap = int(call_cap)
        self.time_cap_s = int(time_cap_s)
        self.budget_tokens = int(budget_tokens)
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.wait_s = 0.0
        self.c429 = 0
        self.truncated = 0
        self.truncated_by = {}
        # 上游非 429 故障（Agnes HTTP 520 这类）的两笔账：打断的请求数 / 补试救回的调用数
        self.upstream_errors = 0
        self.upstream_recovered = 0
        self.t0 = None
        # 每条各花多少必须**按归属计**，不能拿"本条起止之间的全局增量"糊弄：
        # workers=3 的现网验证场（run 35957864648）量到六条的窗口增量之和 594 > 总数 207，
        # 正好是并发倍率 —— 那种数拿去定 CALL_CAP 会把成本估高近三倍。
        self._owner = threading.local()
        self._own_lock = threading.Lock()
        self.by_owner = {}

    def set_owner(self, name):
        self._owner.name = name

    def close_owner(self, name):
        """交回这一条**实际**消耗的调用数（按归属计；并发下各条之和仍等于总数）。"""
        self._owner.name = None
        with self._own_lock:
            return int(self.by_owner.pop(name, 0) or 0)

    def start(self):
        self.t0 = _now()

    def raw_elapsed_s(self):
        """不做 0.1s 量化的耗时。单条账必须用它：里层量化过，外面取几位小数都救不回来。"""
        return 0.0 if self.t0 is None else (_now() - self.t0)

    def note_call(self, tokens_in=0, tokens_out=0):
        self.llm_calls += 1
        who = getattr(self._owner, "name", None)
        if who:
            with self._own_lock:
                self.by_owner[who] = int(self.by_owner.get(who) or 0) + 1
        self.tokens_in += int(tokens_in or 0)
        self.tokens_out += int(tokens_out or 0)

    def note_upstream_error(self):
        self.upstream_errors += 1

    def note_upstream_recovered(self):
        self.upstream_recovered += 1

    def note_wait(self, seconds):
        self.wait_s += float(seconds or 0)

    def note_truncated(self, kind=""):
        """回复撞到输出上限（finish_reason=length）的独立一笔账。

        截断在产物里长得和"模型写得太短"一模一样：不记这一步，spec §3 那条
        `max_tokens` 待验假设就永远验不了，重写两轮也是在要求模型做不到的事。
        `kind` 也必须记：现网第一次 truncated=1 时，逐段/提纲/结构/判定四趟里
        到底是哪一趟撑破了上限查不出来，而下一步（提上限还是拆段）全看这个答案。
        """
        self.truncated += 1
        if kind:
            self.truncated_by[kind] = self.truncated_by.get(kind, 0) + 1

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

    def cap_exceeded(self):
        # 超顶多少：>0 就是这一夜花得比允许多，必须让产物与播报都读得到。
        return max(0, self.llm_calls - self.call_cap)

    def snapshot(self):
        return {"llm_calls": self.llm_calls,
                "cap_exceeded": max(0, self.llm_calls - self.call_cap),
                "input_tokens": self.tokens_in,
                "output_tokens": self.tokens_out, "wait_s": round(self.wait_s, 1),
                "c429": self.c429, "truncated": self.truncated,
                "truncated_by": dict(self.truncated_by),
                "elapsed_s": self.elapsed_s(), "call_cap": self.call_cap,
                "upstream_errors": self.upstream_errors,
                "upstream_recovered": self.upstream_recovered}


def _now():
    return time.monotonic()


def clamp_workers(n, key_count):
    """并发档 = min(请求值, key 数 - 1, WORKERS_MAX)，且至少 1。

    超过 key 数的并发只会排队；超过 6 是把免费池往 429 墙上推。

    **为什么是 key 数减一**：judge 的保留条件是"空余 ≥2"（上面 `KeyPool.acquire`）。
    并发档一旦等于 key 数，所有 key 同时被生成任务占住，judge 永远凑不到空余，
    每条都要等满等待预算再抛 RateLimited —— 条目看起来"跑了"，实际全记 not_run。
    真起线程之后这个坑才会显形（并发 1 时 judge 用得上被占的 key，因为没人在抢）。
    """
    lanes = max(1, int(key_count or 1) - 1) if int(key_count or 1) > 1 else 1
    return max(1, min(int(n or 1), lanes, WORKERS_MAX))


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
        # 并发档一旦真起线程，"两个任务拿同一个 key"就是必然事故（免费池的
        # 429 是按 key 算的）。acquire 的整个扫描必须在同一把锁里完成。
        self._lock = threading.RLock()
        self.workers = clamp_workers(workers, len(self._keys))

    def _is_free(self, k):
        return k not in self._busy and self._cooling.get(k, 0.0) <= self._clock()

    def idle(self):
        return sum(1 for k in self._keys if self._is_free(k))

    def total(self):
        return len(self._keys)

    def acquire(self, kind="generate", exclude=None):
        """`exclude` 是给上游故障补试用的：刚报错那把 key 不该原地再问一遍。"""
        with self._lock:
            if not self._keys:
                return None
            if kind == "judge" and self.workers > 1 and self.idle() < 2:
                return None
            for k in self._keys:
                if exclude is not None and k == exclude:
                    continue
                if self._is_free(k):
                    self._busy.add(k)
                    return k
            return None

    def mark_dead(self, key):
        """把刚报 5xx 的 key 挪到队尾（**不冷却**）。

        上游按 key 拉黑某一把时，`acquire` 恒从队首扫就等于每次调用都先撞它、
        再白补一发（现网红判据的形状就是 k1,k2,k1,k2）。
        刻意不冷却：整池都是 5xx 时冷却会把每条都拖满 `wait_cap_s`，
        那比白补一次糟得多（第六轮审查 P1-3 的取舍）。
        """
        with self._lock:
            try:
                i = self._keys.index(key)
            except ValueError:
                return
            if i != len(self._keys) - 1:
                self._keys.append(self._keys.pop(i))

    def release(self, key):
        with self._lock:
            self._busy.discard(key)

    def mark_429(self, key, retry_after=0):
        with self._lock:
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
# 提纲那趟只要 sections。把结构字段也塞进"不要写正文"的那一趟，是我自己造出来的 0.3 分：
# 现网 run 35803569061 的 evt_003 契约全过，rubric 却是
# {narrative 0.6, causal 0.3, forecast 0.3, quality 0.3} —— 机制链与预测都按提纲的认真度答。
OUTLINE_FIELDS = ("sections",)
STRUCT_FIELDS = ("claims", "causal_chains", "forecasts", "quality", "citations")


def _evidence_block(a, cid=""):
    return "【证据 %s｜%s｜%s｜%d 字】\n%s" % (
        cid, a.get("source", ""), a.get("title", ""), count_chars(a.get("text") or ""),
        a.get("text") or "")


def _structure_rules(id_list, supply):
    """结构字段的契约，只写一份。

    单趟路径与"正文写完后补结构字段"那趟都要同一套数字；抄两遍就等于
    改了常量忘改第二处 —— 那正是这批修复一路在拆的问题。

    覆盖要求按**最长正文**派生，且上界只能是池子给得出的篇数。原来这里写的是
    `required_sources(NARR_MIN)`（3 篇）与"每 7,500 字要引到 6 篇"，而判据查的是
    这条实际写了多长 ⇒ 模型照 prompt 的下界交 5 篇，写到 8,848 字就被自己的长度判死
    （现网八场 58 条里 11 条死于覆盖，`sources_short` 一条没亮、池内中位 12 篇）。
    `max(supply, 1)` 与判据里 `need_cov = min(required_sources(n), max(supply, 1))`
    同形：池子空的时候判据自己也只要求 1 篇，prompt 不许喊出 7 篇这种给不出的下界
    （对抗审查 P0-2：那是 §10.34 刚拆掉的那类"满足不了的下限"）。
    """
    need_top = required_sources(NARR_MAX)
    ask = min(max(supply, 1), need_top)
    cite_low = max(min(CITE_MIN, max(supply, 1)), ask)
    return (
        "- claims：%d-%d 条，每条含 text/kind/evidence。evidence 是数组，元素只能从这批编号里选：%s；"
        "写别的编号等于引用不存在的内容，整条判不合格。"
        "全部 claims 的 evidence 合计至少要覆盖 %d 篇**不同证据**（正文每 %d 字换一篇，"
        "写到 %d 字就要引到 %d 篇），"
        "整条只压在两三篇上会被判“长而空”而不合格。\n"
        "- causal_chains：%d-%d 条，每条含 trigger/mechanism/outcome/confidence/evidence"
        "（evidence 同样只能取上面那批编号），每个字段 ≤%d 字，写清为什么发生而不是只说发生了什么。\n"
        "- forecasts：%d-%d 条，每条含 claim(≤%d字)/horizon_days(只能是 %s，"
        "写成 30、90 一律判不合格 —— 永不到期的预测不算预测)/"
        "check_metric（到期**去哪里查**、拿什么**当前基线**比，"
        "不许写“未来如何”这类空话）。\n"
        "  claim 只能写**这个窗口内就会见分晓**的事：想说“一年内/长期”的趋势，"
        "就改写成窗口内会先发生的先导信号（首个公告、文档更新、试点签约），"
        "别把长期判断塞进 %d 天的窗口里。\n"
        "- quality：**整条只给一个对象**（对这篇所用证据链的整体判断，不是每篇各给一份；"
        "要分源就写进 basis 引用），verdict 只能取 %s，"
        "score 0-100，why %d-%d 字（**按 %d-%d 字写**，超出判不合格），"
        "basis 是数组且必须逐条引用下方「优质判定外证」里的 sig 编号"
        "（形如 sig:c1）；自由文本的理由一律判不合格。\n"
        "- citations：%d-%d 条，id 只能从下面的证据编号里选：%s；不得编造编号或链接。\n"
    ) % (CLAIM_MIN, CLAIM_MAX, id_list, ask, EVID_CHARS,
         NARR_MAX, ask,
         CHAINS_MIN, CHAINS_MAX, CHAIN_FIELD_MAX,
         FORECAST_MIN, FORECAST_MAX, FORECAST_CLAIM_MAX,
         "、".join(str(h) for h in HORIZONS[:-1]) + " 或 " + str(HORIZONS[-1]),
         max(HORIZONS),
         "/".join(QUALITY_VERDICTS), WHY_MIN, WHY_MAX, (WHY_MIN + WHY_MAX) // 2,
         (WHY_MIN + WHY_MAX) // 2 + 10,
         cite_low, CITE_MAX, id_list)


def _cid_by_url(ctx):
    """url → 证据编号。`ctx["ids"]` 的生产形状是 {"c1": url}（deepen_one 里就这么建的），
    但历史上有两处消费者按反方向读它，于是一处靠位置兜底"看起来正常"、另一处静默失效。
    这里两种方向都吸收，取值冲突时以生产形状为准。
    """
    ids = ctx.get("ids") or {}
    out = {}
    for k, v in ids.items():
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            out[v] = k                      # {"c1": url}
        elif isinstance(k, str) and k.startswith(("http://", "https://")) and isinstance(v, str):
            out.setdefault(k, v)            # {url: "c1"}：只作补充，不覆盖上面那种
    return out


JUDGE_DIM_CRITERIA = (
    "narrative（是否成文论述、≥%d字、≥%d段、含反证或限制条件、不是分点罗列）、" % (NARR_MIN, PARAS_MIN)
    + "causal（是否给出机制链条而非复述现象）、forecast（预测是否可核验、窗口是否合理）、"
    + "quality（对信源优质与否的判断有无依据、是否只是自评）、"
    + "density（信息密度：有没有把同一件事换句话再说一遍来充字数；"
      "把重复表述删掉之后是否仍然成文、仍然够长）"
)


def _rubric_brief():
    """给写的人看的评分口径：与 judge 用的是同一份字符串，不是"另一套解释"。

    现网读数（台账 §10.42）：58 条里 35 条死在"判分没过线"，`forecast` 中位 0.475、
    `quality`/`density` 0.55 —— 而这份五维标准以前只有 judge 看得见，写的人第一趟拿不到，
    只能等打完分才在重写那一趟收到"哪一维弱"，白烧一趟 `MAX_REGEN` 预算。
    """
    return ("评审按这五项各打 0-1 分，**任一项不达标就得低于 %.2f**（均值过 %.2f 才算合格）：\n%s\n"
            % (JUDGE_PASS, JUDGE_PASS, JUDGE_DIM_CRITERIA))


def _evidence_blocks(ctx):
    arts = ctx.get("articles") or []
    by_url = _cid_by_url(ctx)
    return [_evidence_block(a, by_url.get(a.get("url")) or ("c%d" % (i + 1)))
            for i, a in enumerate(arts)]


def build_prompt(event, ctx, mode="full"):
    """mode="full" 一趟出全部（`--single-pass` 的旧路径）；mode="outline" 只要提纲。

    提纲那趟提前 return：它不该再看见结构字段的契约，否则又是"边写正文边排 6 类字段"，
    模型只能牺牲一头。
    """
    arts = ctx.get("articles") or []
    ids = ctx.get("ids") or {}
    blocks = _evidence_blocks(ctx)
    id_list = ", ".join("c%d" % (i + 1) for i in range(len(arts)))
    if mode == "outline":
        cap = outline_section_cap(len(arts))
        return (
            "你是深度分析员。只依据下面给出的证据，先出一份提纲，**不要写正文**。\n"
            "事件：%s（主题 %s）\n\n"
            "输出一个 JSON 对象，字段必须是：%s。\n"
            "硬性要求（不满足会被判不合格并重写）：\n"
            "- sections：%d-%d 条（下面只给了 %d 篇证据，所以最多 %d 段），每条含 "
            "title/focus/primary/evidence。primary 是这一段**主要靠哪一篇**立论，"
            "只能是一个编号，且各段的 primary **不得重复**；"
            "两段抢同一篇，多出来的那段就只能复述。\n"
            "- evidence 只能从这批编号里选：%s；focus 一句话说清这一段论证什么、"
            "用什么数据或反证收口。\n"
            "\n===== 证据（每篇均为全文，未截断）=====\n%s\n"
        ) % (event.get("title", ""), event.get("topic", ""), ", ".join(OUTLINE_FIELDS),
             SECTIONS_MIN, cap, len(arts), cap, id_list or "（无）", "\n\n".join(blocks))
    return (
        "你是深度分析员。只依据下面给出的证据写一条洞察，不得补充证据之外的事实或数字。\n"
        "事件：%s（主题 %s）\n\n"
        "输出一个 JSON 对象，字段必须是：%s。\n"
        "硬性要求（不满足会被判不合格并重写）：\n"
        "- narrative：成文论述，%d-%d 字（**按 %d 字写，别贴下限**），"
        "至少 %d 段且**每段 %d-%d 字**，段落式行文，"
        "禁止分点罗列的条目体；必须包含反证或限制条件（如“但该判断受限于…”“样本口径未覆盖…”）。"
        "段数够、每段短，仍判不合格；总长超上限同样判不合格。\n"
        "%s"
        "%s"
        "\n===== 证据（每篇均为全文，未截断）=====\n%s\n"
    ) % (event.get("title", ""), event.get("topic", ""), ", ".join(PROMPT_FIELDS),
         NARR_MIN, NARR_MAX, (NARR_MIN + NARR_MAX) // 2, PARAS_MIN, PARA_MIN, PERA_MAX,
         _rubric_brief(),
         _structure_rules(id_list or "（无）", len(arts)), "\n\n".join(blocks))


def build_structure_prompt(event, ctx, narrative):
    """正文已经写好，单独补结构字段：机制链/预测/优质判断都是"对这篇成文的判断"。"""
    arts = ctx.get("articles") or []
    ids = ctx.get("ids") or {}
    id_list = ", ".join("c%d" % (i + 1) for i in range(len(arts)))
    return (
        "下面是已经写好的一条洞察正文。只依据随后给出的证据，为它补齐结构字段。\n"
        "事件：%s（主题 %s）\n\n"
        "===== 正文 =====\n%s\n\n"
        "输出一个 JSON 对象，字段必须是：%s。\n"
        "硬性要求（不满足会被判不合格并重写）：\n"
        "%s"
        "%s"
        "\n===== 证据（每篇均为全文，未截断）=====\n%s\n"
    ) % (event.get("title", ""), event.get("topic", ""), narrative,
         ", ".join(STRUCT_FIELDS), _rubric_brief(),
         _structure_rules(id_list or "（无）", len(arts)),
         "\n\n".join(_evidence_blocks(ctx)))


def build_section_prompt(event, ctx, sec, idx, total, extra=""):
    """第二段：一次只写一段，且只带这一段引用的证据。

    逐段成文如果每段都重发整包证据，就是把输入放大 6 倍（现网单趟输入实测 ~52k token/事件），
    成本上不接受，所以按 sections[].evidence 过滤。
    `extra` 是上一版的不合格原因：写字的正是这一趟，只发给提纲与结构两趟等于 feedback
    永远到不了动手的人（审查 P1-1，staged 是生产默认）。
    """
    ids = ctx.get("ids") or {}
    # ctx["ids"] 的形状是 {"c1": url, ...}。这里以前写 `for u, cid in ids.items()`，
    # 方向反了 ⇒ by_cid 的键变成 url ⇒ 任何一段都查不到自己的证据 ⇒ **每段都走下面那条
    # 兜底拿同样的前 3 篇**。这就是"8 段抢同一批富源、通篇换句话复述"的结构成因，
    # 而兜底把它藏得严严实实：产物里只看得见 restate_rate 高，看不见原因。
    by_cid = dict(ids)
    picked = []
    for cid in (sec.get("evidence") or []):
        u = by_cid.get(cid)
        a = next((x for x in (ctx.get("articles") or []) if x.get("url") == u), None)
        if a is not None:
            picked.append(_evidence_block(a, cid))
    if not picked:
        # 兜底要留痕：无声退回"整段共用前 3 篇"就是上面那个 bug 能活这么久的原因。
        sec["_evidence_fallback"] = True
        picked = [_evidence_block(a, "c%d" % (i + 1))
                  for i, a in enumerate((ctx.get("articles") or [])[:3])]
    return (
        "接着写第 %d/%d 段正文，只写这一段，输出纯文本、不要 JSON、不要小标题。\n"
        "事件：%s（主题 %s）\n"
        "本段题目：%s\n本段论点：%s\n"
        "要求：成文论述，**%d-%d 字（按 %d 字写）**，段落式行文，禁止分点罗列；"
        "必须包含反证或限制条件（如“但该判断受限于…”“样本口径未覆盖…”）；"
        "不要重复其它段已经写过的内容。\n"
        "%s"
        "%s"
        "===== 本段可用证据 =====\n%s\n"
    ) % (idx, total, event.get("title", ""), event.get("topic", ""),
         (sec.get("title") or "第%d段" % idx), sec.get("focus") or "",
         PARA_MIN, PERA_MAX, PERA_TARGET,
         extra,
         _rubric_brief(),
         "\n\n".join(picked))


def _section_text(raw):
    """段正文取回。模型很爱给 JSON，这里把它折回纯文本，别让一段话变成字典字面量上屏。"""
    t = (raw or "").strip()
    if t.startswith("{"):
        doc = parse_model_json(t) or {}
        for k in ("text", "narrative", "body", "section"):
            if isinstance(doc.get(k), str) and doc[k].strip():
                return doc[k].strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    return t.strip()


def staged_generate(event, ctx, client, key_pool, budget, wait_cap_s=900, sleep=None, extra="",
                    section_extra=None):
    """两段式：先提纲与结构字段，再逐段成文。返回 (cand, note)。

    `cand is None` 表示这趟没给出可用 sections —— 交回上层退单趟，而不是让整条空转：
    提纲这一步是新流程里唯一没有契约兜底的环节（validate 只看最终 narrative/结构字段）。
    `extra` 给提纲与补结构那两趟（整条级的账它们改得动）；`section_extra` 单独给逐段成文那一趟，
    不给就退回共用 `extra`。分流的目的见 `judge_weak_spots` 的 `dims`。
    """
    sec_extra = extra if section_extra is None else section_extra
    def ask_outline(defect=""):
        raw = call_llm(client, build_prompt(event, ctx, "outline") + signals_note(ctx)
                       + extra + defect, key_pool, budget, "outline",
                       wait_cap_s=wait_cap_s, sleep=sleep)
        doc = dict(parse_model_json(raw) or {})
        doc.pop("narrative", None)
        return doc, [s for s in (doc.get("sections") or []) if isinstance(s, dict)]

    doc, secs = ask_outline()
    collisions = outline_rejects(secs)
    note = {}
    if collisions:
        # 点名缺陷重问一次提纲，而不是整条退回单趟：两段式是压住长度方差那一步，
        # 因为一个新字段没写对就废掉它，等于用一个新约束把旧故障请回来。
        doc2, secs2 = ask_outline(
            "\n【上一版提纲的缺陷】各段 primary 不得重复 —— %s\n" % collisions)
        note["primary_retried"] = True
        if outline_rejects(secs2):
            # 还是重复：带着账继续写。硬拦会让这条彻底没有产物，
            # 而"复述"最终由覆盖判据与 judge 的 density 去判，不只靠提纲形状。
            note["primary_collisions"] = collisions
        else:
            doc, secs = doc2, secs2
    # 段数与源数的关系**只做 prompt 约束与记账，不做硬截断**：
    # 砍段会直接把总长削回上限以内，于是"组装守上限"那道守卫自己失效
    # （现网夹具 8 段 × 1,400 字被砍成 6 段后 trimmed_sections 恒为 0）。
    # 源数不够还硬要深挖，是 S1/S2（值得写与证据门）该管的事，不在提纲这一步偷偷改长度。
    cap = outline_section_cap(len(ctx.get("articles") or []))
    if len(secs) > cap:
        note["sections_over_sources"] = "%d 段 / %d 篇可用源" % (len(secs), cap)
    if len(secs) < PARAS_MIN:
        return None, dict(note, reason="提纲只给了 %d 段，少于 %d" % (len(secs), PARAS_MIN))
    note["sections"] = len(secs)
    parts, shorts = [], []
    for i, s in enumerate(secs):
        body = _section_text(call_llm(client, build_section_prompt(
            event, ctx, s, i + 1, len(secs), sec_extra),
            key_pool, budget, "section",
            wait_cap_s=wait_cap_s, sleep=sleep))
        if count_chars(body) < PARA_MIN:
            again = _section_text(call_llm(client, build_section_prompt(
                event, ctx, s, i + 1, len(secs), sec_extra),
                key_pool, budget, "section",
                wait_cap_s=wait_cap_s, sleep=sleep))
            if count_chars(again) > count_chars(body):
                body = again
            if count_chars(body) < PARA_MIN:
                shorts.append(i + 1)
        parts.append(body)
    # 组装时守住上限：现网逐段写出来的每段是 700~1,100 字，6 段直接 4.3k~7k，
    # 超 §2 上限会被整条作废（run 35801635817 的 evt_008 = 6,950 字）。
    # 这里按"整段"丢，不截半句：宁可少一段并记账，也不把论述切成两截。
    body, dropped = [], 0
    for p in parts:
        if not p:
            continue
        if body and count_chars("\n\n".join(body + [p])) > NARR_MAX:
            dropped += 1
            continue
        body.append(p)
    doc["narrative"] = "\n\n".join(body)
    doc.pop("sections", None)
    # 结构字段单独一趟，而且看得到已经写好的正文。把它们塞进提纲那趟是我自己造出来的
    # 0.3 分：现网 run 35803569061 的 evt_003 契约全过，rubric 却是
    # {narrative 0.6, causal 0.3, forecast 0.3, quality 0.3} —— 机制链与预测都按提纲的认真度答。
    struct = dict(parse_model_json(call_llm(
        client, build_structure_prompt(event, ctx, doc["narrative"]) + signals_note(ctx) + extra,
        key_pool, budget, "structure", wait_cap_s=wait_cap_s, sleep=sleep)) or {})
    for k in STRUCT_FIELDS:
        if struct.get(k):
            doc[k] = struct[k]
    # `struct_missing` 不在这里算：结构字段还要过 normalize_candidate，形状不对的会被掏空，
    # 在这里记账只能得出"什么都没缺"（现网 evt_20260923_010 就是这么骗过去的）。
    return doc, dict(note, sections=len(secs), short_sections=shorts,
                     trimmed_sections=dropped,
                     evidence_fallback=sum(1 for s in secs if s.get("_evidence_fallback")))


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


def publish_ref_guard(purpose, ref, event="workflow_dispatch"):
    """打哪条 ref 的准入判断。返回 (可以跑, 说明)。

    这里只拦"手滑"，不拦"并发"：
      · purpose=test 本来就不入库，给它一条"其实会提交"的旁路等于让注释骗人；
      · 手动 publish 不点名 ref ⇒ 拒绝。这次三场验证本意是走分支，
        却因为通道里写死主干而直接改线上，"忘了传"必须是异常。
    夜场**不查有无在途构建**：白天场每小时都有，查了就等于夜场永远等不到窗口，
    而"停更比快讯更糟"已经定过一次（spec §10.16）。撞车由 CAS 重试吸收。
    """
    if purpose != "publish":
        return False, "purpose=%s 不该走到提交：test 的语义就是不入库" % purpose
    if not (ref or "").strip():
        return False, (
            "purpose=publish 必须显式点名 ref（主干请传 %s；验证请传你的分支名）。"
            "不给默认是因为默认一旦是主干，'验证走分支'就是一句空话。" % MAIN_REF)
    return True, "ok"


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
    _bd = int((payload.get("budget") or {}).get("borderline") or 0)
    _ss = int((payload.get("budget") or {}).get("single_sample") or 0)
    foot = "合格 %d 条%s / 快讯 %d 条 / LLM 调用 %s 次 / 耗时 %s 秒" % (
        len(events) - degraded_n,
        "（其中 %d 条压线重判%s，不计达标）" % (
            _bd, "、%d 条只判了一遍" % _ss if _ss else "") if _bd else "", degraded_n,
        _esc((payload.get("budget") or {}).get("llm_calls", "?")),
        _esc((payload.get("budget") or {}).get("elapsed_s", "?")))
    nav = ('<nav class="site"><a href="index.html">收藏池</a>'
           '<a href="ai-daily.html">AI 晨报</a>'
           '<a href="rss-aggregator.html">RSS 聚合</a>'
           '<span class="on">深度洞察</span></nav>')
    # 全场降级也要上线，但要在页面上说清楚：读者看到的不该是"莫名安静的旧页面"，
    # 也不该是"看起来像正常深度报告其实一条合格都没有"。
    banner = ""
    if events and degraded_n == len(events):
        banner = ('<div class="cap warn">今日无合格深度条目：%d 条均按快讯呈现，'
                  '每条已标注具体原因。页面照常更新，不是管线静默跳过。</div>' % degraded_n)
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>深度报告 %s</title><style>%s</style></head><body>"
            "<header><h1>%s</h1><p>%s</p></header>%s%s%s<footer>%s</footer>"
            "</body></html>") % (_esc(payload.get("date", "")), _PAGE_CSS, meta,
                                 _esc(payload.get("generated_at", "")), nav, banner,
                                 "".join(body), foot)


_PAGE_CSS = ("body{font:16px/1.9 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
             "max-width:820px;margin:0 auto;padding:24px;color:#1b1f24;background:#fbfbfd}"
             "h1{font-size:22px}h2{font-size:19px;margin:0 0 6px}"
             "article{border-top:1px solid #e3e5ea;padding:18px 0;margin:0}"
             ".tag{display:inline-block;font-size:12px;color:#5a6472;margin-right:8px}"
             ".cap{background:#fff;border:1px solid #e3e5ea;border-radius:10px;padding:10px 12px;margin:12px 0}"
             ".warn{background:#fff7e6;border-color:#f0c36d}"
             "a{color:#1a56c4;word-break:break-all}footer{color:#5a6472;font-size:13px;padding:16px 0}"
             "p{margin:0 0 12px}"
             "nav.site{display:flex;gap:14px;flex-wrap:wrap;padding:10px 0;"
             "border-bottom:1px solid #e3e5ea;font-size:14px}"
             "nav.site .on{color:#1a56c4;font-weight:600}"
             "details{margin:0 0 12px}summary{cursor:pointer;color:#1a56c4;"
             "font-size:14px;user-select:none}")


def _due_label(made_on, horizon):
    """预测的到期日。没有到期日的预测无法核对，所以取不到时如实写"未标"，不编一个日期。"""
    try:
        return (_to_day(made_on) + timedelta(days=int(horizon))).isoformat()
    except (TypeError, ValueError, IndexError):
        return "未标"


def render_event(e, made_on=""):
    narrative = (e.get("narrative") or "").strip()
    degraded = (e.get("degraded_reason") or "").strip()
    plist = [p for p in re.split(r"\n{2,}", narrative) if p.strip()]
    body = "".join("<p>%s</p>" % _esc(p) for p in plist)
    nchars = count_chars(narrative)
    # 方案一之后一条可以到 1 万字，12 条就是 12 万字；体积不是问题（本站
    # rss-aggregator.html 现网就 3.46 MB），滚动长度才是。折叠只改呈现不改内容：
    # 原生 details、正文逐段仍在 HTML 里，不引 JS、不异步取数 ——
    # 折叠必须是"收起"，不能变成第二次丢内容。
    folded = (('<details><summary>展开全文（%s 字 · %d 段）</summary>%s</details>'
               % ("{:,}".format(nchars), len(plist), body))
              if len(plist) >= 2 and nchars > FOLD_MIN_CHARS else body)
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
    # 压线抖动的合格版必须跟稳的区分开：这句话是我们自己生成的（极差是数出来的），
    # 不引模型文本，所以没有 citations 那套清洗要绕。
    rub = e.get("rubric") or {}
    if e.get("judge_single_sample"):
        brd = " · 只判成 %d/%d 遍（去噪没做成，不给记达标）" % (
            int(rub.get("judge_samples_used") or 0), JUDGE_SAMPLES)
    elif e.get("judge_borderline"):
        brd = (" · 判分极差 %s（≥采纳边界 %s，这一版抖过合格线）" % (
            _esc(rub.get("judge_spread")), _esc(ADOPT_MARGIN)))
    else:
        brd = ""
    # A5：核查摘除过的条数必须让读者看得见，否则"逐条核查有牙"只存在于 JSON 里。
    # 只报条数与核查数：`claims_dropped[].reason` 是模型写的文本，不许跟着上屏。
    dropped = e.get("claims_dropped") or []
    cut = (" · 已摘除 %d 条无支撑论断（共核查 %d 条）" % (
        len(dropped), (e.get("faith_summary") or {}).get("checked", len(dropped)))) \
        if dropped else ""
    # 空区不留标题：浏览器里实测快讯条目下面挂着"因果""证据"两个光杆标题，
    # 名字里带内容却什么都不保证 —— 那是"空壳"的页面版。
    sec_chains = ("<h3>因果</h3><ul>%s</ul>" % chains) if chains else ""
    sec_cites = ("<h3>证据</h3><ul>%s</ul>" % "".join(cites)) if cites else ""
    # 页面上"优质判定 X"只能是**我们自己枚举里**的值：场 39 现网出厂过 "优质判定 深度报道 82"，
    # 而那条自己的 contract_fails 就写着 "quality.verdict '深度报道' 不在枚举" —— 判据对降级条目
    # 不查 quality 这一组，于是模型自造的分类直接上屏（审查第三轮 P1-B）。分值同理只印 0-100 的数字
    # （`score: true` 现在会一路过关，页面印出 "True"）。
    _v, _s = q.get("verdict"), q.get("score")
    qual = ("优质判定 %s %s" % (_esc(_v), _esc(_s))
            if _v in QUALITY_VERDICTS and isinstance(_s, (int, float))
            and not isinstance(_s, bool) and 0 <= _s <= 100 else "")
    return ("<article><h2>%s</h2><p class='tag'>%s · rubric %s · %s%s%s</p>%s%s"
            "%s%s%s</article>") % (
        _esc(e.get("title")), _esc(e.get("topic")),
        _esc(rubric_display(e.get("rubric"))),
        qual,
        brd, cut, warn, folded, sec_chains, cards, sec_cites)


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
    picked, seen, srcs = [], set(), set()

    def take(a):
        if a and a["url"] not in seen and count_chars(a["text"]) > 0:
            seen.add(a["url"])
            picked.append(a)
            # 取一篇就记一家：`cands` 的排序键是建表时算的，只有把 srcs 变成活的，
            # 第二遍循环才知道"这家已经来过了"（红判据里 src1 一口气占 8 个坑就是这么来的）。
            if a.get("source"):
                srcs.add(a["source"])

    for u in (event.get("links") or []):
        take(pool.get((u or "").split("#")[0]))
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
    # 两遍取：先把"还没来过的家"各取一篇，再回头补同家的后续篇。
    # 一遍取会输给关键词重合度：一家高贴题的媒体能把坑占满，池子家数塌成个位数，
    # 而覆盖契约要的是"每 1,500 字换一篇**独立来源**"（任务 #67）。
    for fresh_only in (True, False):
        for _, _, _, _, a in cands:
            if len(picked) >= max_articles:
                break
            if fresh_only and a["source"] in srcs:
                continue
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
            # 一过性上游故障（现网 run 35966811294 一波 Agnes HTTP 520 吃掉 12 条里的 3 条，
            # 而同场另外 9 条正常跑完 ⇒ 当时其它 key 是好的）。换一把**别的**空闲 key 补试一次：
            # 不进等待预算（那是 429 的语义），至多补一次（持续故障不该把请求翻倍）。
            pool.release(key)
            pool.mark_dead(key)          # 下次别又从这把开始问
            budget.note_upstream_error()
            alt = pool.acquire(kind, exclude=key)
            if alt is None:
                raise          # 没有别的空闲 key 就快速失败；计数已经记过一笔，读者在播报里看
            try:
                out = client.complete(prompt, key=alt, kind=kind)
            except RateLimited as e2:
                # 补试撞 429 是**限流**不是上游故障：冷却那把 key、记 c429、推进 waited，
                # 再回外层换 key 重问。并到 5xx 那一档会让播报说"等过窗口"而其实一秒没等，
                # 而那把被限流的 key 还会立刻被下一条继续踩（第五轮审查 P1-2）。
                cooldown = pool.mark_429(alt, getattr(e2, "retry_after", 0))
                budget.note_429(cooldown)
                waited += cooldown
                if waited >= wait_cap_s:
                    raise RateLimited(0, "wait_cap_exceeded:429")
                continue
            except Exception:
                pool.release(alt)
                pool.mark_dead(alt)
                budget.note_upstream_error()
                raise
            pool.release(alt)
            budget.note_upstream_recovered()
            if getattr(client, "last_finish_reason", "") == "length":
                budget.note_truncated(kind)
            budget.note_call(estimate_tokens(prompt), estimate_tokens(out or ""))
            return out
        pool.release(key)
        if getattr(client, "last_finish_reason", "") == "length":
            budget.note_truncated(kind)
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
    n = len(s)
    for i in range(n):
        ch = s[i]
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
            # 引号到底是"字符串结束"还是"正文里的裸引号"，看它后面第一个非空白字符：
            # 结构符（, : } ]）才算结束，否则是模型在中文正文里直接打了引号。
            # 现网 run 35756700221 三条回复各 5,095–6,031 字、JSON 结构完整，
            # 全部因为这种裸引号被 json.loads 判成非法 —— 深度不是没写出来，是我们读不出来。
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j < n and s[j] in ",:}]":
                in_str = False
                out.append(ch)
            else:
                out.append('\\"')
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


def _quality_richness(x):
    """多个 quality 变体时按"信息量"挑：why 长度 → basis 条数 → score。

    score 放最后：分数是结论，不是信息量；先按它挑会偏向"敢打分"的那条。
    """
    try:
        score = float(x.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return (count_chars(x.get("why") or ""), len(x.get("basis") or []), score)


def repair_forecasts(cand):
    """单格违约的预测**摘掉那一条**，不许把整篇 8,000 字论述打成 200 字快讯。

    现网 run 35823028980：evt_20260923_008 正文 8,621 字、结构字段齐全，
    只因 `horizon_days 30` 一格被判不合格，重写两轮后整条降级成 192 字 —— 
    代价与过错不成比例，而且 validate 每条规则都 `break` 在第一格，
    连"其余几条是好的"都读不出来。
    摘除必须留账（`forecasts_dropped`）：静默删掉就是替模型改答案。
    摘完仍要过 §2：至少 1 条、且每条都有可核验判据 —— 全坏照样不合格。
    """
    keep, dropped = [], []
    for f in (cand.get("forecasts") or []):
        if not isinstance(f, dict):
            # 摘除也要留正文：字符串行归一后是 {"claim": 原文}，
            # 只记 raw 会把模型的论断抹掉（test_normalize_candidate_preserves_string_rows 钉这条）。
            dropped.append({"reason": "不是对象", "claim": str(f)[:80]})
            continue
        if f.get("horizon_days") not in HORIZONS:
            dropped.append({"reason": "horizon_days %r 不在 %s" % (f.get("horizon_days"), HORIZONS),
                            "claim": (f.get("claim") or "")[:60]})
            continue
        if not (f.get("check_metric") or "").strip():
            dropped.append({"reason": "缺 check_metric（不可核验就是空话）",
                            "claim": (f.get("claim") or "")[:60]})
            continue
        if count_chars(f.get("claim") or "") > FORECAST_CLAIM_MAX:
            dropped.append({"reason": "claim %d 字 > %d" % (
                count_chars(f.get("claim") or ""), FORECAST_CLAIM_MAX),
                "claim": (f.get("claim") or "")[:60]})
            continue
        keep.append(f)
    cand["forecasts"] = keep
    if dropped:
        cand["forecasts_dropped"] = dropped
    return cand


def normalize_candidate(cand, ids_map, arts_by_id=None):
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

    cites, invented = [], []
    for c in (cand.get("citations") or []):
        cid = c.get("id") if isinstance(c, dict) else (c.strip() if isinstance(c, str) else None)
        if cid in ids_map:
            a = (arts_by_id or {}).get(cid) or {}
            # 引用行的来源/标题/字数一律取**我们自己的池**：模型给的这些字段既不可核对，
            # 又会被渲染层原样上屏（现网页面因此显示 "? 字"，而 test_publish 手工补了
            # 这些字段，所以渲染判据一直对着一个生产发不出的形状绿着）。
            cites.append({"id": cid, "url": _clean_url(ids_map[cid]),
                          "source": a.get("source") or "", "title": a.get("title") or "",
                          "chars_used": count_chars(a.get("text") or "")})
        else:
            invented.append(str(cid if cid else c)[:40])
    cand["citations"] = cites
    if invented:
        # 丢掉的引用必须留痕：归一先删、校验后看的话，`validate_event` 里
        # "假链接即硬失败"那一支永远拿不到输入，编造引用就成了静默通过（对抗审查 C3）。
        cand["invented_citations"] = invented
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
    if isinstance(q, list):
        # 现网 run 35816287694：模型对每篇证据各写一个 quality 对象，契约要单对象，
        # 于是两条合格候选被归一掏空成不合格。取信息最全的那条，其余留计数不许静默丢。
        objs = [x for x in q if isinstance(x, dict)]
        if objs:
            cand["quality"] = max(objs, key=_quality_richness)
            cand["quality_variants"] = len(objs)
        else:
            # 数组里一个对象都没有：回到"留原样"那条路，不许把形状丢了当"模型没写"。
            cand["quality_echo"] = str(q)[:400]
            cand["quality"] = {}
    elif isinstance(q, str) and q.strip():
        # 整段字符串当 quality：把原文塞进 why，其余留空，让契约去判它不合格
        cand["quality"] = {"verdict": "", "score": 0, "why": q.strip(), "basis": []}
    elif not isinstance(q, dict):
        if q not in (None, "", [], {}):
            # 留一份原样：否则"我们把它丢了"会被读成"模型没写"。
            # 现网 evt_20260923_010 就是这样 —— struct_missing 报"什么都没缺"，
            # 产物里的 quality 却是空的，缺口正在这一步。
            cand["quality_echo"] = str(q)[:400]
        cand["quality"] = {}
    repair_forecasts(cand)
    repair_quality_fields(cand)
    return cand


def rubric_of(raw):
    """judge 分项分数归一。**"没给这一维"与"给了 0 分"必须是两件事。**

    旧写法对缺失键取 0.0：judge 少回一个 `density`，均值被摊薄、单维地板又必然踩破，
    整夜从"均值略低"变成"必判死"，而产物里只留 `density: 0.0` 一种形状 ——
    读日志的人会以为模型写得不好，实际是判据协议没跑通（对抗审查 P0-1 复现）。
    缺失的维度不进均值分母，另记 `missing_dims` 交给 `judge_accepts` 单独处理。
    """
    raw = raw or {}
    out = {}
    scored = []
    for k in JUDGE_DIMS:
        try:
            v = float(raw.get(k))
        except (TypeError, ValueError):
            v = None
        if v is None:
            out[k] = None
        else:
            out[k] = max(0.0, min(1.0, v))
            scored.append(k)
    core = [k for k in scored if k in MEAN_DIMS]
    out["mean"] = round(sum(out[k] for k in core) / float(len(core)), 4) if core else 0.0
    out["scored_dims"] = len(scored)
    out["missing_dims"] = [k for k in JUDGE_DIMS if k not in scored]
    return out


JUDGE_PASS = 0.75
# 第五维 density 管的是"长而空"：方案一之后一条可以到 1 万字，字数上限不再兼管防水分，
# 这一维就是主判口。机械侧只提供输入（restate_rate 与它数出来的复述段），不当硬门；
# 已退役的句级 repetition_rate 对现网两条真长文都读 0.0，别再往回加。
JUDGE_DIMS = ("narrative", "causal", "forecast", "quality", "density")
# 均值只按四维实质分算。五维平均会把有效合格线从 0.75 挪到 0.6875 ——
# judge 只要在 density 上慷慨，四维 0.7125 的东西就放行了，方向和"反水分"相反。
MEAN_DIMS = ("narrative", "causal", "forecast", "quality")
# density 走单维否决：它不许被另外四维的高分抬过去（那正是"长而空"的得分路径）。
VETO_DIMS = ("density",)
# 地板按噪声定，不是拍的：同一条重评的极差实测 0.17，
# 0.75 - 2*0.17 ≈ 0.41，取 0.5 保证这一闸不会在复评噪声上翻脸。
JUDGE_FLOOR = 0.5


def judge_accepts(score):
    """合格 = 四维均值达标 + 没有任何一维塌到地板以下 + judge 把维度给全了。

    `missing_dims` 非空时判不过**并且必须点名**：这是判据协议没跑通，
    不是模型写得差。两者混在同一个 `degraded_reason` 里，下一轮就会去改错的地方
    （对抗审查 P0-1 复现的正是这种误记账）。
    """
    s = score or {}
    if s.get("mean", 0.0) < JUDGE_PASS:
        return False
    if s.get("missing_dims"):
        return False
    for k in VETO_DIMS:
        v = s.get(k)
        if isinstance(v, (int, float)) and v < JUDGE_FLOOR:
            return False
    return True
# 每一维"该怎么修"必须写进重写消息：只说"均分 0.71 低于 0.75"，模型收到的是
# "再写一遍"，两轮重写就停在同一水平（现网 evt_003 rubric=0.7125 就是这么废的）。
JUDGE_FIX_HINT = {
    "narrative": "成文论述偏弱（%s）：补机制、数据与反证，不要堆形容词",
    "causal": "因果分析偏弱（%s）：trigger/mechanism/outcome 每段都要有材料支撑",
    "forecast": "趋势预测偏弱（%s）：给到期的可核验指标，窗口只能是 3/7/14 天",
    "quality": "内容优质判断偏弱（%s）：why 说清报道形态，basis 逐条引外证编号",
    "density": "信息密度偏弱（%s）：删掉换句话说的重复段，把省下的篇幅补进机制与反证",
}

# 逐段成文那一趟改得动的只有这两条（正文论述与本段复述）；
# causal/forecast/quality 是结构字段的账，发给补结构那一趟 —— 分流是为了不逼一段话去修整条，
# 也为了不把嵌在违约原文里的模型自报字符串送进正文通道（审查 P2-4/P2-5）。
SECTION_FIX_DIMS = ("narrative", "density")


def judge_weak_spots(score, bar=JUDGE_PASS, cand=None, dims=None):
    """judge 分项分数 → "哪一维薄弱 + 该改什么"（spec §2"按薄弱维度重生成"）。

    `dims` 给定时只出这些维的建议：逐段成文那一趟改不动"预测窗口""优质依据"这类整条级的账，
    把它们塞给只写一段的人既做不到、又顺带把模型自报的原文送回正文通道（审查 P2-4/P2-5）。
    分流不是删账 —— 补结构那一趟照旧收到全部。

    分项以前被 `rubric_of` 平均掉就没人看了：均值不合格时，重写消息里连
    "是哪一维拉低的"都没有，等于让 judge 主判却只消费它的一个标量。
    `density` 这一维额外点名"被多段复用的是哪些数"（`cand` 给了才算，不给不许凭空造清单）：
    只说"删掉重复段"是形容词，模型没法下手；清单是我们数出来的，零新增调用。
    """
    if (score or {}).get("judged") is False or (score or {}).get("judge_skip"):
        # 判定根本没跑 ⇒ 不许报均分、也不许给分项建议：那正是任务 #61 为页面修掉的错
        # （"没送判定"讲成"判了 0 分"），而它一直顺着 extra 发给提纲与补结构那两趟。
        return []
    out = ["judge 均分 %.2f 低于 %.2f" % ((score or {}).get("mean", 0.0), bar)]
    for k in JUDGE_DIMS:
        if dims is not None and k not in dims:
            continue
        v = (score or {}).get(k)
        if isinstance(v, (int, float)) and v < bar:
            hint = JUDGE_FIX_HINT[k] % ("%.2f" % v)
            if k == "density" and cand:
                listed = restate_fact_list_text(cand)
                if listed != "（无）":
                    # 没清单就别印"（无）"：那句形容词本身就是全部信息，加一行空话
                    # 只会让重写 prompt 变长而不带任何新信息。
                    hint += "（被多段复用的数：%s）" % listed
            if v < JUDGE_FLOOR:
                hint += "（单这一条就低于地板 %.2f，均值再高也不过）" % JUDGE_FLOOR
            out.append(hint)
    return out


def build_judge_prompt(cand, ctx):
    """judge 必须看到完整正文与完整证据：只喂片段就打"论述深度"分是自相矛盾的。

    字数口径从 `NARR_MIN/PARAS_MIN` 渲染，不写死：写死过一次，结果是契约已经抬到 4,000
    而评审还按 2,500 判 —— 两个数不一致时，被纵容的是评审那一侧。
    """
    arts = ctx.get("articles") or []
    m = restatement_rate(cand.get("narrative") or "")
    facts = restate_fact_list_text(cand)      # 与重写反馈同一份渲染，两处不各写一遍
    measured = (
        "机械实测（不是你判断出来的，是数出来的）：复述率: %s —— %d 段里有 %d 段在"
        "换句话复述同一批数据，共 %d 对高重叠段。被 ≥3 段反复消费的数：%s。\n"
        "打 density 时以此为输入：把这些复述段删掉之后还剩下多少有效论述？\n\n"
    ) % (m["rate"], m["paras"], m["restated_paras"], m["pairs"], facts or "（无）")
    dims = JUDGE_DIM_CRITERIA      # 与写的人看到的同一份：两处各写一遍迟早分叉
    return (
        "你是评审。只依据下面给出的材料，为这篇洞察按五项各打 0-1 分：" + dims + "。\n"
        '只输出 JSON：{"narrative":0.0,"causal":0.0,"forecast":0.0,"quality":0.0,'
        '"density":0.0,"notes":"≤80字"}\n'
        "任一项不达标就必须给低于 %.2f 的分；不要因为它写得长就给高分 —— 长而空要在 density 上扣分。\n\n"
        "%s"
        "===== 待评正文（全文）=====\n%s\n\n===== 证据（%d 篇，均为全文）=====\n%s\n"
    ) % (JUDGE_PASS, measured, (cand.get("narrative") or ""), len(arts),
         "\n\n".join((a.get("text") or "") for a in arts))


def judge_event(client, cand, ctx, key_pool, budget, wait_cap_s=900, sleep=None):
    raw = parse_model_json(call_llm(client, build_judge_prompt(cand, ctx), key_pool, budget,
                                    "judge", wait_cap_s=wait_cap_s, sleep=sleep))
    return rubric_of(raw)


def rubric_display(rubric):
    """给读者看的分：契约没过时那不是"判了 0 分"，是"根本没送判定"。

    现网两次印错（`evt_20260924_002`、`evt_20260924_008` 顶层 mean=0.0，而它们自己的
    `regen_scores` 里有真判定值）；页面和播报共用这一个口径，免得只修了半个读者。
    """
    r = rubric or {}
    if r.get("judged") is False:
        # 三种"没判"要去修三个不同的地方，所以因由必须上屏，不能糊成一句
        label = {"evidence_gate": u"证据门挡下", "protocol": u"判据协议没跑通"}.get(
            r.get("judge_skip") or "", u"契约没过")
        return u"未送判定（%s）" % label
    return r.get("mean", "?")


def _median(vals):
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def judge_event_multi(client, cand, ctx, key_pool, budget, wait_cap_s=900, sleep=None):
    """同一版正文判 `JUDGE_SAMPLES` 次，逐维取中位。

    单遍不可用的直接证据：现网 evt_011 均值 0.7500 正好压在合格线上，
    而同一内容复评极差实测 0.17 —— 这个"合格"重跑一次就可能翻。

    两趟之间的取舍有两条，都是被现网形状逼出来的：
    · **某趟少给一维 ≠ 协议没跑通**。给到的那一趟的值照用（不许当 0 分这条不变量不动），
      只记 `partial_dims`。按"任一趟缺就判死"，双采样会把协议误杀从 p 抬到 1-(1-p)²
      —— 去噪做成了加倍误杀（对抗审查 P0-2 复现）。
    · **后面几趟撞 429 不许把整条扔出去**。正文是花掉十几次调用换来的，第二趟只是去噪用的；
      第一趟就没 key 才照旧抛（那是饥饿信号，不能咽）。
    """
    scores, failed, garbage = [], 0, 0
    for i in range(JUDGE_SAMPLES):
        try:
            s = judge_event(client, cand, ctx, key_pool, budget,
                            wait_cap_s=wait_cap_s, sleep=sleep)
        except RateLimited:
            if not scores:
                # 一趟都没判成：这不是"去噪少一个样本"，是没 key。抛出去记 wait_exhausted。
                raise
            failed += 1
            continue
        except Exception:
            # 判定趟撞 5xx（Agnes HTTP 520 这类，批 3.11 补试之后仍然可能全打不通）：
            # 那是"这一趟没判成"，不是"这条不合格"。正文是 24~40 次调用换来的（现网真值），
            # 批 3.9 已经给 429 定过同一条规矩，错误码不该决定要不要把钱扔掉（任务 #66）。
            # 但**一趟都没判成**时照旧抛：上游不可用是饥饿信号，咽下来会变成
            # "判定全挂、每条都记成快讯、CI 还是绿的"那种最难发现的失败形态。
            if not scores:
                raise
            failed += 1
            continue
        if not any(isinstance(s.get(k), (int, float)) for k in JUDGE_DIMS):
            # 空对象/散文被 `rubric_of` 摊成 mean=0.0：那是**什么都没判**，不是"给了 0 分"。
            # 留在样本里会让极差立刻变 0.9、条目挂上 borderline 并再烧一整趟生成，
            # 页面上还印"判分极差 0.9" —— 拿编造的数当去噪证据（第四轮审查 P0-2 复现）。
            garbage += 1
            continue
        scores.append(s)
    if not scores:
        # 所有趟都没判出东西：按判据协议没跑通记（缺全部维度），不 raise ——
        # 正文是花钱写的，扔了它才是真事故。
        # 全 garbage = 判据协议没跑通，同样是"什么都没判"，不许被印成"判了 0 分"（第五轮 P1-2）
        return {"mean": 0.0, "judged": False, "judge_skip": "protocol",
                "scored_dims": 0, "missing_dims": list(JUDGE_DIMS),
                "partial_dims": [], "judge_samples": [], "judge_samples_used": 0,
                "judge_samples_failed": failed + garbage, "judge_samples_garbage": garbage,
                "judge_spread": 0.0, "unstable": False}
    out = {}
    n_real = len(scores)
    for k in JUDGE_DIMS:
        vals = [s[k] for s in scores if isinstance(s.get(k), (int, float))]
        missing = n_real - len(vals)
        out[k] = round(_median(vals), 4) if vals else None
        if not vals:
            # 所有会跑的都缺这一维：判据协议没跑通，不许当内容分数
            out.setdefault("missing_dims", []).append(k)
        elif missing:
            # 有趟给了、有趟没给：值照用，但极差是基于部分样本算的，必须留痕
            out.setdefault("partial_dims", []).append(k)
    core = [out[k] for k in MEAN_DIMS if isinstance(out.get(k), (int, float))]
    out["mean"] = round(sum(core) / float(len(core)), 4) if core else 0.0
    out["scored_dims"] = len([k for k in JUDGE_DIMS if out.get(k) is not None])
    out.setdefault("missing_dims", [])
    out.setdefault("partial_dims", [])
    out["judge_samples_used"] = n_real
    out["judge_samples_failed"] = failed + garbage
    out["judge_samples_garbage"] = garbage
    means = [s.get("mean", 0.0) for s in scores]
    out["judge_samples"] = [round(m, 4) for m in means]
    # 只有一趟作数时极差没有意义：一个数算不出方差，硬算出来的 0 会被读成"很稳"。
    out["judge_spread"] = round(max(means) - min(means), 4) if len(means) > 1 else 0.0
    out["unstable"] = bool(len(means) > 1 and out["judge_spread"] > ADOPT_MARGIN)
    return out


def beat_by_margin(new, old):
    """新版比旧版**好出噪声带**才算好。

    现网两场都在说明单遍判分不能信：evt_011 均值正好 0.7500 压线，evt_015 0.65、
    evt_003 0.55 都在"差一点点"的带里，而同一内容复评极差实测 0.17。
    所以重写不只要"过了"，还要"比上一版好得出来"，否则就是在重掷骰子。
    否决维（density）回退单独判一次：均值涨、密度塌正是"长而空被综合分抬过去"的路径
    （白天在 faith 上有同族事故：0.90→0.66 被综合分掩盖）。
    """
    new, old = new or {}, old or {}
    nm, om = new.get("mean", 0.0), old.get("mean", 0.0)
    if nm <= om + ADOPT_MARGIN:
        return False
    for k in VETO_DIMS:
        a, b = new.get(k), old.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a < b - ADOPT_MARGIN:
            return False
    return True


# 带下沿归一到 4 位小数：`0.75 - 2*0.09` 的真值是 0.5700000000000001，
# 拿它当界会把"均值恰好 0.57"这一档挡在外面（第四轮审查 P1-1 复现）。
HOPE_BAND = round(JUDGE_PASS - HOPEFUL_BANDS * ADOPT_MARGIN, 4)


def single_dimension_gap(score):
    """恰好一维低于合格线、其余都过线 ⇒ 重写有明确方向（`JUDGE_FIX_HINT` 就点名那一维）。

    上一轮我按"坏维=0.30 时均值还剩 0.6375"判定这条豁免不可达，就把它删了；
    第四轮审查给的形状是**坏维=0.0**：均值 0.5625 落在带外，于是真会误收手。
    我那句"结构性不可达"是穷举做半截（只试了 0.30）下的结论 —— 形状按原样回来，
    判据这次逐档试 0.30 / 0.10 / 0.0，外加"两维塌才算没方向"。
    """
    s = score or {}
    bad = [k for k in JUDGE_DIMS
           if isinstance(s.get(k), (int, float)) and s.get(k) < JUDGE_PASS]
    return len(bad) == 1


def near_pass_line(score):
    """判定均值离合格线不到 `HOPEFUL_BANDS` 个噪声带 —— 这一档继续重写才真有机会翻盘。

    带宽取两个噪声带（0.57 起豁免）而不是一个：批 2 验证场 run 35940113012 两条降级
    终判 0.6375，按一个带（0.66）会被掐在第二轮，而"差一点点"恰恰是最该再给一次的机会。
    每趟均值都记进 `regen_scores`，六场之后用真轨迹决定这条线要不要挪 —— 现在 n=3，
    只有"0.40 那种救不回来"是有依据的。
    """
    return (score or {}).get("mean", 0.0) >= HOPE_BAND


def no_progress(score, fails, prev_score, prev_fails):
    """连续两趟的"失败信号"一模一样 ⇒ 重写没带来新信息，该收手。

    覆盖面要说清楚，别拿规则救不了的那一档当战绩（对抗审查 P0-4 复现）：
    违约串里带字数，所以"正文 1,748 → 2,307 → 1,902 字"那种**长度漂移**
    走的是"清单变了"这一支，本规则**不收手** —— 它可能正在收敛。
    现在真正收手的是两种：违约串逐字重复（含判据协议漏维），以及 mean<0.57 且没涨出噪声带。
    长度漂移那档要先看 `regen_scores` 的真轨迹再定改法（批 4）。

    只比均值也不够：契约没过时 `score` 恒为 `{"mean": 0.0}`，0.0 对 0.0 是
    "压根没测到分"，不是"抖不动" —— 那种情况按违约清单变没变来判。
    两趟都判过分时给两条豁免：均值离合格线不到 HOPEFUL_BANDS 个噪声带（`HOPE_BAND`=0.57），
    或者只剩一维低于合格线（`single_dimension_gap`）—— 这两种都还有明确可改的方向。
    反过来"多维一起塌、均值又在带外"才是该收手的那一档。
    """
    fails = list(fails or [])
    if fails != list(prev_fails or []):
        return False
    if fails:
        return True
    if near_pass_line(score) or near_pass_line(prev_score):
        return False
    if single_dimension_gap(score) or single_dimension_gap(prev_score):
        return False
    return not beat_by_margin(score, prev_score)


def _dropped_digest(cand):
    """被摘论断的内容指纹：让"同一批违约"按内容比，而不是按条数撞车。

    只进 `contract_fails` 与重写反馈；`degraded_reason`（要上屏的那格）只报条数。
    """
    parts = sorted(hashlib.sha1((d.get("claim") or "").encode("utf-8")).hexdigest()[:6]
                   for d in (cand.get("claims_dropped") or []))
    return ",".join(parts[:3]) or "无"


def _degrade_reason(max_regen, last_attempt, stalled, cand, last_score=None):
    """降级理由必须对得上实际发生的事 —— 四笔账不能混成一句"重写 2 次仍不合格"。

    现网 09-24 那份产物里三条都写"重写 2 次仍不合格"，其中一条其实只因为
    `quality.why 170 字` 这一格形状违约；提前收手的、形状违约的、判据协议没跑通的、
    判分不够的长得一模一样，等于把归因又推回给人猜。
    这里**只给条数与维度名，不拼违约原文**：这一格要渲染上屏，而违约原文里可能带着
    模型自报的假链接（审查变异体 G17 复现过）。原文留在 contract_fails 里。
    """
    fs = cand.get("faith_summary") or {}
    if cand.get("faith_coverage_broken"):
        # 复判挡下的那一版：理由要说清是"摘完没人撑了"，不是"生成写得短"。
        # 要求那一份必须与判据同式（`need_cov = min(required_sources(n), max(supply,1))`）：
        # 报一个池子给不出的数，就是 §10.34 拆掉的那类"满足不了的下限"换了个出口。
        cited = {c.get("id") for c in (cand.get("citations") or [])}
        used = set()
        for cl in (cand.get("claims") or []):
            used |= set(cl.get("evidence") or [])
        n = count_chars(cand.get("narrative") or "")
        supply = (cand.get("context_stats") or {}).get("articles") or 0
        # 同一趟里论断数也跌破 CLAIM_MIN 时要一并说出来：只讲覆盖的话，
        # "摘到剩 2 条"这笔更重的账就又隐身了（审查 P1-5）。
        tail = ""
        if fs.get("below_minimum"):
            tail = "，且只剩 %d 条论断（<%d）" % (fs.get("kept", 0), CLAIM_MIN)
        return "逐条核查摘掉 %d 条后，正文只剩 %d 篇证据支撑（要 >=%d 篇）%s：被摘的论断补不回来就撑不起这篇" % (
            fs.get("dropped", 0), len(used & cited),
            min(required_sources(n), max(supply, 1)), tail)
    if cand.get("faith_degraded"):
        return "逐条核查摘除无支撑论断后只剩 %d 条（<%d）：撑不起一条洞察" % (
            fs.get("kept", 0), CLAIM_MIN)
    if stalled:
        s = stalled[-1]
        n = s.get("fails_total") or len(s.get("fails") or [])
        kind = s.get("kind")
        if kind == "judge_proto":
            return "重写 %d 轮后判据协议仍未跑通（缺维见 contract_fails），停止重掷" % last_attempt
        if kind == "faith":
            return "重写 %d 轮后逐条核查仍查无支撑（见 contract_fails），停止重掷" % last_attempt
        if kind == "faith_coverage":
            return "重写 %d 轮后仍是核查一摘就跌破覆盖判据（见 post_faith_contract_fails），停止重掷" % last_attempt
        if kind == "contract":
            return "重写 %d 轮后同一批违约未修掉（%d 条，见 contract_fails），停止重掷" % (
                last_attempt, n)
        return "重写 %d 轮后无改善（判定均值 %s→%s，没好出噪声带 %s），按预算收手" % (
            last_attempt, s.get("prev_mean"), s.get("mean"), ADOPT_MARGIN)
    return "重写 %d 次仍不合格%s" % (max_regen, _weakest_dim_note(last_score))


def _weakest_dim_note(last_score):
    """把"最弱哪一维、差多少"补进降级理由：五维分值本来就在 `rubric` 里，不点名才是浪费。

    没给判定读数时返回空串 —— 宁可留那句笼统的"仍不合格"，也不能凭空点一个维度名。
    """
    s = last_score or {}
    dims = {k: float(s[k]) for k in JUDGE_DIMS
            if isinstance(s.get(k), (int, float))}
    if not dims or not isinstance(s.get("mean"), (int, float)):
        return ""
    weak = min(dims, key=dims.get)
    return "（判定中位 %.3f，最弱 %s %.3f，其余分项见 rubric）" % (
        float(s["mean"]), weak, dims[weak])


def build_faith_prompt(event, ctx, claim):
    """逐条核查的 prompt：只给**这条 claim 自己引用的那几篇全文**。

    白天在 `_verify_faithfulness` 上留过一条同族教训：核查域与判定域不一致时，
    会出现"judge 看得见、核查编辑看不见"，结果是把真实报道判成无支撑删掉。
    所以这里既不许截断（截断会把支撑句切没了 → 假阳性误删），
    也不许把没引的源塞进来（放大核查域 → 什么都能"找到支撑"）。
    """
    ids = ctx.get("ids") or {}
    by_cid = dict(ids)          # 形状同 build_section_prompt：{"c1": url}，别再写反
    blocks = []
    for cid in (claim.get("evidence") or []):
        u = by_cid.get(cid)
        a = next((x for x in (ctx.get("articles") or []) if x.get("url") == u), None)
        if a is not None:
            blocks.append(_evidence_block(a, cid))
    return (
        "你是事实核查员。下面是一条洞察里的**单条论断**，以及这条论断自己引用的证据全文。\n"
        "只判断一件事：这句话里的每个实体与数字，能否在下面这些证据里找到对应原文。\n"
        "事件：%s（主题 %s）\n"
        "论断：%s\n\n"
        "判定口径：\n"
        "- supported：证据里有这句话依赖的事实与数字；\n"
        "- inflated：事情在证据里，但**数字对不上**（证据写 42%%，论断写 41%% 之类）；\n"
        "- unsupported：证据里根本没有这件事 —— 包括那种『看起来很像行内常识』的市场份额数。\n"
        "必须给**原文原句**（quote，从下面证据里逐字摘，不许改写、不许凭记忆），"
        "unsupported 时 quote 留空。\n"
        '只输出 JSON：{"verdict":"supported|inflated|unsupported","reason":"≤60字","quote":"原文原句"}\n'
        "\n===== 本条论断的证据（全文，未截断）=====\n%s\n"
    ) % ((event or {}).get("title", ""), (event or {}).get("topic", ""),
         claim.get("text") or "", "\n\n".join(blocks) or "（这条论断没有可核对的证据编号）")


def apply_faith(cand, verdicts):
    """按 claim 顺序应用核查结论。返回留下的 claims。

    摘除而不是废整条：§10.16 定过"一格违约只摘那一条"，代价要与过错成比例。
    读不懂的结论一律保留并记 unknown —— 静默当 supported 等于伪造"核查过了"，
    静默当 unsupported 会误删真话。
    """
    claims = list(cand.get("claims") or [])
    dropped, keep = [], []
    counts = {"supported": 0, "inflated": 0, "unsupported": 0, "unknown": 0}
    for i, cl in enumerate(claims):
        v = verdicts[i] if i < len(verdicts) else None
        verdict = (v or {}).get("verdict") if isinstance(v, dict) else None
        if verdict in ("supported", "inflated", "unsupported"):
            counts[verdict] += 1
        else:
            verdict = None
            counts["unknown"] += 1
        if verdict in ("inflated", "unsupported"):
            dropped.append({"claim": (cl.get("text") or "")[:200], "verdict": verdict,
                            "reason": ((v or {}).get("reason") or "")[:120]})
            continue
        keep.append(cl)
    cand["claims"] = keep
    if dropped:
        prev = cand.get("claims_dropped") or []
        cand["claims_dropped"] = prev + dropped
    cand["faith_summary"] = {
        "checked": len(claims), "kept": len(keep), "dropped": len(dropped),
        "below_minimum": len(keep) < CLAIM_MIN,
        "unsupported": counts["unsupported"], "inflated": counts["inflated"],
        "unknown": counts["unknown"]}
    return keep


def verify_claims(event, cand, ctx, client, key_pool, budget, wait_cap_s=900, sleep=None):
    """逐条核查：每条 claim 一次调用，成本上限就是 claims 数（3–10）。"""
    verdicts = []
    for cl in (cand.get("claims") or []):
        raw = call_llm(client, build_faith_prompt(event, ctx, cl), key_pool, budget, "faith",
                       wait_cap_s=wait_cap_s, sleep=sleep)
        verdicts.append(parse_model_json(raw))
    return apply_faith(cand, verdicts)


def faith_broke_contract(cand, valid_ids=None, valid_basis=None):
    """核查摘过 claims ⇒ 判据必须在**最终形态**上重跑一遍，返回新违约列表。

    `validate_event` 跑在 `verify_claims` 之前，而覆盖那一判据数的是
    "claims 实际压住几篇不同证据"（`used_cov`）—— 摘掉一条挂着独有证据的 claim 就直接
    把它摘小。现网八场去重后 6 条合格里 **5 条**出厂时已经不满足自己那条判据
    （`_scratch/replay_read.txt`，含第 35 场 mean=0.8125 那条：9,142 字要 7 篇、只剩 6 篇）。
    没摘过就别重跑：同一张判据问两遍会把停滞规则的"同批违约"比较带偏。
    """
    if not (cand.get("faith_summary") or {}).get("dropped"):
        return []
    ok, fails = validate_event(cand, valid_ids=valid_ids, valid_basis=valid_basis)
    return [] if ok else list(fails)


def deepen_one(event, pool, client, budget, key_pool, max_regen=MAX_REGEN, wait_cap_s=900, sleep=None,
               source_quality=None, staged=True, call_cap=CALL_CAP):
    """一个事件：装证据 → 过证据门 → 生成 → 契约判定 + judge 独立打分 → 不过就重写。

    `staged=True` 走两段式（提纲 → 逐段成文）。现网单趟的长度方差压不住
    （1,748 / 2,307 / 1,902 字，重写两轮停在同一水平），把"写够长"单独交给每段一次调用。
    """
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
                            "sources": ctx.get("sources", 0),
                            # spec §3 要"丢整篇并记理由"。只留 url 列表的话，事后读产物的人
                            # 分不开"素材本来就这么点"与"预算把证据挤掉了"这两种完全不同的结论。
                            "dropped_articles": [
                                {"url": d.get("url", ""), "tokens": d.get("tokens", 0),
                                 "reason": d.get("reason", "")} for d in ctx["dropped"]],
                            "dropped_urls": [d["url"] for d in ctx["dropped"]]}
    if not gate_ok:
        short = (event.get("summary") or "")[:DEGRADED_NARR_MAX]
        rec.update({"narrative": short,
                    # 证据门降级也要留这些观测格：注释说"每场都在产物里"，
                    # 早退路径不写就是假话（对抗审查 P2 复现：门降级条目根本没有复述观测字段）。
                    "narrative_chars_full": count_chars(event.get("summary") or ""),
                    "degraded_reason": gate_why, "claims": [], "causal_chains": [],
                    "forecasts": [], "citations": [],
                    "quality": {"verdict": "转载", "score": 0, "why": "证据不足未做优质判定",
                                "basis": ["evidence_gate"]},
                    "rubric": {"mean": 0.0, "judged": False,
                                                 "judge_skip": "evidence_gate"}})
        return annotate_observability(rec)
    prompt = (build_prompt(event, ctx) + signals_note(ctx))
    cand, last_fails, score = {}, [], {"mean": 0.0}
    parse_echo, staged_note, extra, section_extra = None, None, "", ""
    # traj = 每趟的判定轨迹（attempt / 中位均值 / 两趟原始样本）。只留最后一版的分，
    # "该不该再重写一次"就永远没有依据 —— 停滞阈值的下一次改档要靠它。
    best, stalled, prev_score, prev_fails = None, [], None, None
    traj = []
    last_attempt = 0
    for attempt in range(max_regen + 1):
        last_attempt = attempt
        raw = ""
        if staged:
            doc, note = staged_generate(event, ctx, client, key_pool, budget,
                                        wait_cap_s=wait_cap_s, sleep=sleep, extra=extra,
                                        section_extra=section_extra)
            cand = dict(doc or {})
            if cand:
                staged_note = note
            else:
                # 提纲没给够段数：这条退回单趟生成。新流程的唯一入口不设契约兜底
                # （validate 只看最终 narrative 与结构字段），不退回就等于把整条打成 0 字。
                staged_note = dict(note or {})
                staged_note["fell_back"] = True
                raw = call_llm(client, build_prompt(event, ctx) + signals_note(ctx) + extra,
                               key_pool, budget, "generate",
                               wait_cap_s=wait_cap_s, sleep=sleep)
                cand = dict(parse_model_json(raw) or {})
        else:
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
        cand = normalize_candidate(cand, ctx["ids"],
                                   {"c%d" % (i + 1): art for i, art in enumerate(ctx["articles"])})
        # 缺哪些结构字段，必须在归一**之后**数：形状不对的会被掏空，归一之前数只会报"什么都不缺"。
        cand["struct_missing"] = [k for k in STRUCT_FIELDS if not cand.get(k)]
        # 水分先量一遍再判：这一格是观测 + judge 的输入，不当硬门（理由见 restatement_from_sets）；
        # 但必须每场都在产物里，否则"什么时候可以升成门"永远没有依据。
        annotate_observability(cand)
        ok, fails = validate_event(cand, valid_ids=ids, valid_basis=basis_ids)
        last_fails = fails
        fail_kind = "contract"
        if ok:
            score = judge_event_multi(client, cand, ctx, key_pool, budget,
                                      wait_cap_s=wait_cap_s, sleep=sleep)
            traj.append({"attempt": attempt, "mean": score.get("mean", 0.0),
                         "samples": score.get("judge_samples") or []})
            # judge 少给维度是**判据协议没跑通**，不是模型写得差：单独记一笔进产物，
            # 但不许顶掉"哪一维薄弱"的重写反馈（那是这条判据存在的意义）。
            proto = (["judge 未给维度 %s：判据不可用，不许当合格" % "/".join(score["missing_dims"])]
                     if score.get("missing_dims") else [])
            last_fails = fails + proto
            if fails:
                fail_kind = "contract"
            elif proto:
                fail_kind = "judge_proto"
            if judge_accepts(score):
                # 核查紧跟判定：合格版如果论断查无支撑，那它根本不配当"最终入选的那一版"。
                # 摘到不足 CLAIM_MIN 就当一次拒绝，把"按证据重写"写进反馈 ——
                # 上一批这里是"先采纳再降级"，白扔了手里剩下的重写预算（审查 P1-5）。
                verify_claims(event, cand, ctx, client, key_pool, budget,
                              wait_cap_s=wait_cap_s, sleep=sleep)
                fs = cand.get("faith_summary") or {}
                # 核查会摘 claims，摘完"正文压在几篇证据上"就变了：判据必须在这一版的
                # **最终形态**上再跑一遍，否则出厂那一版从来没被检查过（任务 #69，现网 5/6）。
                broke = faith_broke_contract(cand, valid_ids=ids, valid_basis=basis_ids)
                if broke:
                    cand["post_faith_contract_fails"] = broke
                if fs.get("below_minimum") and attempt < max_regen:
                    traj[-1]["rejected"] = "faith"
                    fail_kind = "faith"
                    # 串里必须带上**被摘的是哪些**：只报条数的话，两版毫无重叠的论断
                    # 会因为"都剩 0 条"被判成同一批违约而提前收手（P1-3 实测只跑 2 趟）。
                    last_fails = ["逐条核查后只剩 %d 条（<%d）：论断查无支撑，按证据重写（本版被摘 %s）" % (
                        fs.get("kept", 0), CLAIM_MIN, _dropped_digest(cand))]
                    # `score` 不清零：均值与分项是重写反馈的输入，
                    # 把判定过的版本记成 {"mean": 0.0} 会让下一轮只收到"原样再写一遍"。
                elif broke and attempt < max_regen:
                    traj[-1]["rejected"] = "faith_coverage"
                    fail_kind = "faith_coverage"
                    last_fails = ["逐条核查摘掉 %d 条后判据不过（要补的是被摘掉的论断所缺的证据，"
                                  "不是重写一遍）：%s" % (fs.get("dropped", 0), "；".join(broke))]
                else:
                    cand["rubric"] = score
                    best = (cand, score, attempt)
                    if fs.get("below_minimum"):
                        # 重写到头还是摘不够：照 §10.16 只降级不静默
                        cand["faith_degraded"] = True
                        # 同一趟里"摘到不足条数"与"摘破覆盖"是两笔账：先前这里直接
                        # break，后者永远走不到 ⇒ coverage_blocked 少计、contract_fails
                        # 空着，那条账在现网读数里隐身（审查 P1-5）。
                        if broke:
                            cand["faith_coverage_broken"] = True
                            last_fails = list(broke)
                        break
                    if broke:
                        # 摘破了覆盖又没有重写预算：同一套规矩，降级而不是当合格出厂。
                        # 违约原文要并进 `contract_fails`（页面与探针都读那一格），
                        # 只放 `post_faith_contract_fails` 的话这条账在现网读数里是隐身的。
                        cand["faith_coverage_broken"] = True
                        last_fails = list(broke)
                        break
                    if not score.get("unstable"):
                        break                   # 稳的合格版：收工
                    # 压线抖动版：先兜住当 fallback，再花一轮重判 —— 本批新增的 unstable
                    # 若没有这里做消费方，就又是一个"只写不读"的字段（审查 P0-1）。
                    if attempt >= max_regen:
                        break
        else:
            # 契约没过 ⇒ 判定根本没跑。`mean` 这个键要留着给 no_progress() 做可比值，
            # 但 `judged=False` 是给读者的：0.0 与"没判"必须是两种形状（任务 #61）。
            score = {"mean": 0.0, "judged": False, "judge_skip": "contract"}
        # 重写只在"下一轮还带得来新信息"时继续；提前收手才叫省钱，
        # 跑满 max_regen 那趟之后再记"按预算收手"是一笔没发生的账（审查 P1-8）。
        if attempt > 0 and attempt < max_regen and prev_score is not None and \
                no_progress(score, last_fails, prev_score, prev_fails):
            # kind 分档：契约违约没修掉、判据协议没跑通、核查摘空、判定抖不动 ——
            # 这四种"停"要去修四个不同的地方，混成一句就等于把归因推回给人猜。
            stalled.append({"attempt": attempt, "kind": fail_kind if last_fails else "judge",
                            "fails": [f[:80] for f in (last_fails or [])[:2]],
                            "fails_total": len(last_fails or []),
                            "mean": score.get("mean", 0.0),
                            "prev_mean": prev_score.get("mean", 0.0)})
            break
        prev_score, prev_fails = score, list(last_fails)
        # 每趟之前问一次预算：原来整条只在开头问一遍，一条最坏连着跑 3 趟，
        # 实测把 CALL_CAP 顶穿 72 次而产物里没人说超了（第四轮审查 P0-1）。
        if attempt < max_regen and budget.llm_calls + PER_ATTEMPT_CALLS > call_cap:
            cand["regen_cut_by_budget"] = True
            cand["regen_cut_reason"] = "budget:剩余 %d/%d" % (
                max(0, call_cap - budget.llm_calls), call_cap)
            break
        if attempt < max_regen:
            # 契约条目与薄弱维度**都要**带上：上一版这里写成 `A or B`，于是协议缺维时
            # 分项建议被挤掉，重写又变成"原样再写一遍"（本仓为这个踩过两轮）。
            # `proto` 已经进了 last_fails，这里去重而不是再拼一遍。
            reasons = list(last_fails)
            reasons += [w for w in judge_weak_spots(score, cand=cand) if w not in reasons]
            extra = "\n上一版不合格原因（必须逐条修掉）：%s\n" % "; ".join(reasons)
            # 逐段那一趟另给一份窄的：只带本段改得动的分项建议，不带契约违约原文
            # （整条级的账与嵌在里面的模型自报字符串，见 `SECTION_FIX_DIMS` 那条注释）。
            # 守卫只放在 `judge_weak_spots` 一处：判定没跑时它自己返回空清单。
            # 这里曾另有一份同款判断，变异体 U11 复跑时存活 ⇒ 证明它已经是死代码（一处真相）。
            sec = judge_weak_spots(score, cand=cand, dims=SECTION_FIX_DIMS)
            section_extra = ("\n上一版判分偏弱、本段能改的地方：%s\n" % "; ".join(sec)) if sec else ""
            prompt = build_prompt(event, ctx) + signals_note(ctx) + extra
    if best:
        cand, score, adopted_attempt = best
        # 核查已经在"这一版被判合格"的当趟跑过了（见上面的 acceptance 分支）：
        # 放到循环之后再跑一遍，就等于把摘空的信号晚了一整轮预算才说。
        if staged_note:
            cand["staged"] = staged_note
        cand["rubric"] = score
        cand["contract_fails"] = []
        cand["regen_used"] = adopted_attempt
        # 采纳的是第几趟 ≠ 一共跑了几趟：抖动兜底版确立后还会再跑（第四轮审查 P1-5
        # 实测"跑 4 趟、账上只写 1"）。没有这一格，多烧的预算在产物里查不到。
        cand["regen_attempts"] = last_attempt + 1
        cand["regen_scores"] = traj
        cand["context_stats"] = rec["context_stats"]
        if score.get("unstable"):
            # 抖到线上也要发（§10.16：停更比快讯更糟），但它不是"这条判据救回来的功"：
            # 页面与播报都得能把它跟稳的合格版分开看。
            cand["judge_borderline"] = True
        elif int(score.get("judge_samples_used") or 0) < JUDGE_SAMPLES:
            # 规则缺口（不是现网实锤）：只判成一遍时极差算不出来 ⇒ unstable 恒 False，
            # 单遍读数必然从压线规则的缝里绕过被记成 stable。现网两场里合格条目都判满了两遍，
            # 所以这一档至今对 qualified_stable 的实际影响是 0（台账 §10.20 第 3 条）；
            # 那条 used=None 的条目是**降级**条目且 rubric 整块缺失，属另一形状（任务 #61）。
            cand["judge_borderline"] = True
            cand["judge_single_sample"] = True
        # 采纳路径上**不**记 regen_stalled：合格那趟之后 prev_score 必在线上（近线豁免），
        # 而 last_fails 是空表，两趟同违约那条也走不到 ⇒ 停滞在采纳之后不可达（第四轮审查
        # P1-5 的账其实是"跑了没记"，由下面的 regen_attempts 兜住，不是"停滞被扔掉"）。
        if not (cand.get("faith_degraded") or cand.get("faith_coverage_broken")):
            return cand
    # 停滞要落到产物里：只打在日志上的话，下一跑没人能核对这条规则真动过手。
    # 合格路径上面已经记过一次，这里是给降级路径（没有 best，或 faith 摘空/摘破覆盖）兜底。
    if stalled:
        cand["regen_stalled"] = stalled
    if traj:
        cand["regen_scores"] = traj
    if not best or cand.get("faith_degraded") or cand.get("faith_coverage_broken"):
        if not cand.get("degraded_reason"):
            cand["degraded_reason"] = _degrade_reason(max_regen, last_attempt, stalled, cand,
                                                      last_score=score)
    if not best:
        # 真重写了几轮就记几轮：原来这里恒写 max_regen，提前收手时是一笔假账。
        cand["regen_used"] = last_attempt
    if parse_echo:
        cand["parse_echo"] = parse_echo
    if staged_note:
        cand["staged"] = staged_note
    clip_for_degrade(cand)
    cand["rubric"] = score
    cand["contract_fails"] = last_fails
    cand["context_stats"] = rec["context_stats"]
    return cand


def build_anchor_diff(anchor_events, records, scheduled=None):
    """夜场对每个锚点事件做了什么，必须逐条留痕（spec §5）。

    恒空的 anchor_diff 与"名字里带深度却什么都不保证"是同一个病：
    读产物的人需要一个能核对的地方，看"白天的 12 个事件"到夜里变成了什么。

    `scheduled` 是本场真正排进队列的 id 集合。不传它的话，被 `--events-limit`
    切掉的锚点会**同时不在 keep/drop/not_run 里** —— 审计只覆盖切片，
    而发布闸门读的就是这份审计，"半套不上线"于是恒真（对抗审查 I6）。
    """
    by_id = {r.get("id"): r for r in records or [] if isinstance(r, dict)}
    diff = []
    for ev in anchor_events or []:
        eid = ev.get("id")
        r = by_id.get(eid)
        before = len(ev.get("key_links") or ev.get("links") or [])
        if r is None:
            if scheduled is not None and eid not in scheduled:
                diff.append({"op": "skip", "id": eid, "reason": "not_scheduled:events_limit",
                             "evidence_before": before, "evidence_after": 0})
            else:
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
                         "reason": "过证据门与五维判据（judge 均分 %s）" % (
                             rubric_display(r.get("rubric"))),
                         "evidence_before": before, "evidence_after": after})
    return diff


def _calls_per_item(good):
    # §7 定档看的是分布，不是"整场总除条数"：71 次/3 条什么都定不了。
    used = [int(e.get("llm_calls_used") or 0) for e in good or []]
    used = [u for u in used if u > 0]
    return {"items": len(used), "max": max(used) if used else 0,
            "mean": round(sum(used) / float(len(used)), 1) if used else 0}


def build_payload(events, anchor_meta, budget, date_str, key_count=0, workers=1,
                  anchor_diff=None, predictions_reconciled=None):
    good = [e for e in events if not (e.get("degraded_reason") or "").strip()]
    b = dict(budget.snapshot(), budget_tokens=budget.budget_tokens,
             source_sha=anchor_meta.get("source_sha", ""),
             anchor_date=anchor_meta.get("date", ""),
             degraded=len(events) - len(good), qualified=len(good),
             # A6：压线重判的合格版不算"这条判据救回来的功"，达标数是 qualified_stable。
             qualified_stable=len([e for e in good if not e.get("judge_borderline")]),
             calls_per_qualified=_calls_per_item(good),
             # 合格里"抖过线才过的那部分"与提前收手的那部分：跨夜比的是这两列，
             # 只报 qualified 的话，停滞省下的调用会被读成"这轮没干活"。
             borderline=len([e for e in good if e.get("judge_borderline")]),
             # 压线里有两种因：抖过线、以及只判成一遍。没有这一列，跨夜只看到"压线 N 条"，
             # 不知道有几条根本没去噪（去噪本身没做成是另一码事，不是模型抖）。
             single_sample=len([e for e in good if e.get("judge_single_sample")]),
             # 复判挡下的那一档要单独一列：没有它，"合格 0"读起来像"一夜没干活"，
             # 而真相可能是"写了长文但核查一摘就撑不住"（台账 §10.41：八场里五场会这样）。
             coverage_blocked=len([e for e in events if e.get("faith_coverage_broken")]),
             stalled=len([e for e in events if e.get("regen_stalled")]),
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
            return json.dumps({"narrative": v, "causal": v, "forecast": v,
                               "quality": v, "density": v})
        ids = re.findall(r"c\d+", prompt.split("证据编号里选")[-1][:200]) or ["c%d" % i for i in range(1, 7)]
        if kind == "section":
            # 段正文必须真够长（越过每段下限）：给短了，测到的就是夹具尺寸而不是流程
            return "论证与数据推演%s，但该判断仍受样本量与统计口径限制。" % ("依" * 700)
        doc = {
            "claims": [{"text": "论断%d" % i, "kind": "causal",
                        "evidence": [ids[i % len(ids)] if ids else "c1"]}
                       for i in range(7)],
            "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                               "confidence": 0.6, "evidence": [ids[0] if ids else "c1"]} for _ in range(3)],
            "forecasts": [{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                           "check_metric": "同类竞品发布数>=3", "status": "pending"}],
            "quality": {"verdict": "一手", "score": 82,
                        "why": "依据来源分布与是否一手材料判定，未采用生成方自评",
                        "basis": (re.findall(r"sig:c\d+", prompt or "") or ["sig:c1"])[:3]},
            "citations": [{"id": (ids[i] if i < len(ids) else "c%d" % (i + 1))} for i in range(6)],
        }
        if kind == "outline":
            # 提纲那趟只给 sections：连结构字段一起给，就等于测不到"结构单独一趟"这条新路径
            return json.dumps({"sections": [
                {"title": "第%d段" % (i + 1),
                 "focus": "论证第%d个环节，并给出反证与口径限制" % (i + 1),
                 "evidence": [ids[i % len(ids)] if ids else "c1"]}
                for i in range(PARAS_MIN)]}, ensure_ascii=False)
        doc.pop("sections", None)
        if kind != "structure":
            doc["narrative"] = "\n\n".join(
                "论证与数据推演%s，但该判断仍受样本量与统计口径限制。" % ("依" * 700)
                for _ in range(8))
        return json.dumps(doc, ensure_ascii=False)


class GithubDataApi:
    """真 Data API 通道：head/blob/tree/commit/ref。夜场只写自己的路径。"""

    def __init__(self, repo="Kwei168/starhub", token=None, ref=None):
        self.repo = repo
        # ref 没有默认值：漏传时"打到主干"必须报错，而不是悄悄发生。
        # 2026-09-23 的形态就是这里写死 main —— 我说"验证走分支"，三场却全打在主干上。
        if not (ref or "").strip():
            raise ValueError("GithubDataApi 必须显式给 ref（主干请传 MAIN_REF）")
        self.ref = ref.strip()
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
        ref = self._req("GET", "/repos/%s/git/ref/heads/%s" % (self.repo, self.ref))
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
            self._req("PATCH", "/repos/%s/git/refs/heads/%s" % (self.repo, self.ref),
                      {"sha": sha, "force": bool(force)})
            return True
        except urllib.error.HTTPError as e:
            if e.code == 422 and not force:
                return False      # 父不符 = CAS 失败，交回上层重读 head 重试
            raise

    def is_ancestor(self, sha):
        """只认 ahead/identical —— 我方 sha 真在这条 ref 的历史里。

        `diverged`/`behind` 恰恰是"提交已被白天的 auto-commit 甩出主线"的形态
        （compare/<sha>...<ref> 在主线另起一线时返回 diverged）。以前把四个状态全收，
        等于 spec §4 那条"前科终检"恒真：被吞掉也会报告 published、退出码 0。
        """
        try:
            doc = self._req("GET", "/repos/%s/compare/%s...%s" % (self.repo, sha, self.ref))
        except urllib.error.HTTPError as e:
            if e.code in (404, 409, 410):
                return False
            raise
        return doc.get("status") in ("ahead", "identical")


# ───────────────────────────── 编排与入口 ──────────────────────────────────

def night_run(purpose="test", events_limit=EVENTS_DEFAULT, client=None,
              budget_tokens=DEFAULT_BUDGET_TOKENS,
              call_cap=CALL_CAP, keys=None, get=http_get, anchor_raw=None, pool=None, out_dir="_night_state",
              date_str=None, log=None, sleep=None, wait_cap_s=900, urls=None,
              api_factory=None, max_regen=MAX_REGEN, workers=1, pred_raw=None, staged=True,
              max_tokens=None,
              pred_url=PREDICTIONS_URL, verdicts=None, quality_raw=None,
              ref=MAIN_REF,
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
        client = AgnesClient(**({"max_tokens": max_tokens} if max_tokens else {}))
    # 告警要坐在构造之外：显式传 client 的调用方（含 CI 与本地复跑）同样会撞这个上限。
    cap = getattr(client, "max_tokens", 0)
    if not staged and cap and cap < SINGLE_PASS_OUT_TOKENS:
        # 单趟一次吐完整条：上限不够就是必然截断。宁可开场喊话，
        # 也不要半夜产出一堆"看起来是模型写不长"的 0 字条目。
        log("::warning title=单趟输出上限不够|max_tokens=%d < 单趟最坏输出约 %d token，"
            "正文必然被截；要么 --max-tokens 提上去，要么别用 --single-pass" % (cap, SINGLE_PASS_OUT_TOKENS))
    ck = os.path.join(out_dir, "deep-%s.jsonl" % date_str)
    prev_recs = load_records(ck)
    done = {r.get("id") for r in prev_recs if r.get("id")}
    recs = []
    stopped_by_cap = False
    stop_reason = ""
    failed = []
    # 每条实际花掉的调用按**锚点 id** 结算（成功 / 429 / 异常三条路径都结一次）：
    # 不结算的话死掉那条的钱整个从产物里消失，“各条之和 == 总数”对不上。
    spent_by_id = {}
    recs_lock = threading.Lock()

    def _settle_owner(ev_id):
        """交回归属、按锚点 id 记下这条实际花掉的次数，并返回次数。

        键必须是锚点里的 id，不能是 `r["id"]`：模型回来的 id 覆盖过锚点 id 时
        （`cand.setdefault("id", ...)`）那条记录既进不了 `ship` 也进不了 `recs`，
        钱就彻底查不到（第五轮审查 P1-3）。
        """
        spent = int(budget.close_owner(ev_id) or 0)
        with recs_lock:
            spent_by_id[ev_id] = spent
        return spent

    def _emit(r, ev_id):
        """做完一条立刻落 checkpoint 并播报。

        checkpoint 与产物列表是共享状态，并发下必须有唯一的写入点；
        播报放在锁外，免得一条 log 卡住整条池。
        """
        with recs_lock:
            recs.append(r)
            append_jsonl(ck, [r])
        why = (r.get("degraded_reason") or "").strip()
        fails = "; ".join((r.get("contract_fails") or [])[:3])
        log("[夜场] %s %s narrative=%d 字 rubric=%s%s%s" % (
            ev_id, "降级" if why else "合格",
            count_chars(r.get("narrative") or ""),
            rubric_display(r.get("rubric")),
            " 原因=%s" % why if why else "",
            " 判据=%s" % fails if fails else ""))

    def _cutoff():
        """主动收口两道闸：返回 "" 继续，否则返回原因（wallclock / budget）。"""
        if budget.over_time():
            log("::warning title=夜场窗口将尽|已用 %.0fs ≥ 墙钟预算 %ds，剩余条目记 not_run"
                "（产物照写，不等平台掐）" % (budget.elapsed_s(), budget.time_cap_s))
            return "wallclock"
        need = ITEM_CALLS_MAX if budget.llm_calls else PER_ATTEMPT_CALLS
        if budget.llm_calls + need > call_cap:
            # 开一条之前先问"还剩不够写完一趟"。原来只问 `llm_calls >= call_cap`：
            # 剩 1 次也照开，而一条最坏要 93 次（3 趟 × 每趟 31，含每趟都可能跑的核查）。
            # 预留只按**一趟**而不按 ITEM_CALLS_MAX：按 93 预留会让"总闸小于一条的最坏值"时
            # 整夜空跑（测试档 80 就撞上），而超发的上界已经由每趟预留压住。
            log("[夜场] 剩余调用 %d/%d 不够开下一条（要 %d 次；还没做过时按一趟 %d 次放行）" % (
                max(0, call_cap - budget.llm_calls), call_cap, ITEM_CALLS_MAX,
                PER_ATTEMPT_CALLS))
            return "budget"
        return ""

    def _do(ev):
        nonlocal stopped_by_cap, stop_reason
        # 收口闸必须坐进任务体里。原来只在 `ex.submit()` 之间问一次：submit 瞬时返回，
        # 12 条在几微秒内全部派完，之后一路等到底 —— 对抗审查用假钟复现：
        # workers=1 拦下 7 条并记 not_run:wallclock，workers=3 一条不拦、耗时 21,600s
        # 超掉 job 的 180 分钟上限，那时既没产物也没重试。
        why = _cutoff()
        if why:
            with recs_lock:
                if not stop_reason:
                    stopped_by_cap, stop_reason = True, why
            log("[夜场] %s 未开始：窗口已收口（%s），记 not_run" % (ev["id"], why))
            return
        # 本条自己的账按**归属**计（thread-local）：并发下各条之和仍等于总数。
        # 早先写法是取窗口增量，workers=3 的现网场（run 35957864648）量到六条之和 594 > 总数 207，
        # 正好是并发倍率 —— 拿那种数定 CALL_CAP 会把成本估高近三倍。耗时是这一条的延迟，不相加。
        t_item = budget.raw_elapsed_s()
        budget.set_owner(ev["id"])
        item_wait = wait_cap_s
        if budget.time_cap_s > 0:
            item_wait = max(1.0, min(wait_cap_s, budget.time_cap_s - budget.elapsed_s()))
        try:
            r = deepen_one(ev, pool, client, budget, kp, wait_cap_s=item_wait, sleep=sleep,
                           max_regen=max_regen, source_quality=source_quality, staged=staged)
        except RateLimited as e:
            _settle_owner(ev["id"])
            log("[夜场] %s 等待超上限(%s)：记 not_run，不阻断全场" % (ev["id"], e))
            return
        except Exception as e:
            # 一次瞬时错误（Agnes 5xx、上游分块抖动）不能把整晚换掉：产物在循环之后才落盘，
            # 异常穿出去就是"钱花完了、JSON/HTML 一个都没有、还看不出为什么"。
            _settle_owner(ev["id"])
            with recs_lock:
                failed.append("%s:%s" % (ev.get("id"), type(e).__name__))
            log("::warning title=条目失败但继续|%s 抛 %s（%s），本场其余条目照做" % (
                ev.get("id"), type(e).__name__, str(e)[:120]))
            return
        r["llm_calls_used"] = _settle_owner(ev["id"])
        # 3 位小数且走 raw 时钟：CI 实测单条落在 0.05~0.1s 档，量到 0.1 的时钟会把快条目
        # 全塌成 0.0，"max < sum"的并发自证必假红（run 35966373547 预检就是这么红的）。
        r["elapsed_item_s"] = round(budget.raw_elapsed_s() - t_item, 3)
        _emit(r, ev["id"])

    todo = []
    for ev in events:
        if ev["id"] in done:
            log("[夜场] %s 已在 checkpoint 里，跳过" % ev["id"])
        else:
            todo.append(ev)
    # 并发档 >1 时才起线程：`KeyPool.workers` 以前只是个数字，全模块没有一处线程，
    # 于是"多账号池"的所有设计（每 key 一槽、429 冷却、judge 让位生成）永远不可能被触发。
    # 收口闸只坐在 `_do` 里问一次。原来并发分支在 `ex.submit()` 之间问：submit 瞬时返回，
    # 12 条在几微秒内全部派完，闸此后再没机会拦（对抗审查 P0-2 假钟复现：
    # workers=1 拦下 7 条，workers=3 一条不拦、耗时 21,600s 超掉 job 的 180 分钟）。
    # 串行分支直接调 `_do`，语义与"派单前问一次"相同，也不会多问第二遍。
    if kp.workers > 1:
        with ThreadPoolExecutor(max_workers=kp.workers) as ex:
            for f in [ex.submit(_do, ev) for ev in todo]:
                f.result()
    else:
        for ev in todo:
            _do(ev)
    # 产物 = 本场新做的 + checkpoint 里已做完的，按锚点顺序排；
    # 少了后半截就是"重试夜上线半套产物"那个坑。
    by_id = {r.get("id"): r for r in (prev_recs + recs)}
    ship = [by_id[e["id"]] for e in events if e.get("id") in by_id]
    # 口径（第五轮审查 P0-1，写死在这里而不是加字段）：`prev_recs` 是上一趟做完的条目，
    # 它们带着**上一趟**的 `llm_calls_used`，而本场 `budget.llm_calls` 只数本场发的请求。
    # ⇒ "各条之和 == 本场总数"只对**本场做过的条目**成立。刻意不给产物加 carried 元数据：
    #   加了就等于每趟重试都改产物字节，会把"同一夜不重复提交"那条幂等守卫打回
    #   （`test_in_place_retry_does_not_commit_the_same_artifact_twice` 实测红过一次）。
    all_degraded = bool(ship) and all((r.get("degraded_reason") or "").strip() for r in ship)
    if all_degraded:
        # 全场降级**不挡发布**：挡了就是"质量一抖、页面几天没更新甚至永远没更新"。
        # 半套不上线管的是"有的条目根本没做"，不是"做了但只够快讯" —— 后者照上线，
        # 并在页面上写清楚今天没有合格深度条目（见 render_page 的横幅）。
        log("::warning title=本场全部降级|今日无合格深度条目，产物按快讯发布并逐条标注原因（页面照常更新）")
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
                            anchor_diff=build_anchor_diff(anchor["events"], ship,
                                                          scheduled={e.get("id") for e in events}),
                            predictions_reconciled=stats)
    # 账本里已结算的行随产物发布：页面上的"已结算预测"区靠它，只写 predictions.jsonl
    # 的话读者在页面上永远只看到"待验证"（§5 要预测卡含到期与命中状态）。
    payload["settled_predictions"] = settled_rows
    payload["not_run"] = missing(events, [x.get("id") for x in ship],
                                  stop=stop_reason)
    # 死掉那几条的调用数钉到对应的 not_run 行上：光有 not_run:incomplete 一个名字，
    # 读的人分不开"没排上"（0 次）与"跑到一半被掐了"（几十次）。
    for _row in payload["not_run"]:
        # pop 而不是 get：锚点 id 重了时 missing() 会出两行同 id，get 会把同一笔钱记两遍。
        _row["llm_calls_used"] = int(spent_by_id.pop(_row.get("id"), 0) or 0)
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
    if failed and not ship:
        # 逐条吞异常是为了"一条抖动不换整晚"，但全军覆没必须当场喊红：
        # 否则"每条都抛错"与"每条都没排上"在 CI 上都是同一个绿勾。
        log("::error title=夜场全军覆没|%d 条全部抛错（%s），本场没有任何成果" % (
            len(failed), "; ".join(str(x) for x in failed[:3])))
    out = {"payload": payload, "json": jpath, "html": hpath, "predictions": ppath,
           "budget": budget.snapshot(), "published": None}
    if purpose != "publish":
        log("[夜场] purpose=%s，不提交（产物只在 %s）" % (purpose, out_dir))
        return out
    want = [e["id"] for e in events]
    if not can_publish([{"id": i} for i in want],
                       [x.get("id") for x in ship],
                       budget_used_calls=budget.llm_calls, call_cap=call_cap,
                       stopped_by_cap=stopped_by_cap):
        # 只拦"半套"：有锚点条目根本没落地就上线，页面会静默少几块。
        # 全部降级不是半套 —— 曾因这条闸让站点连着几天没新内容甚至永远没有。
        log("::warning title=本场不发布|完成 %d/%d（未撞预算的半成品），本场不提交" % (
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
    api = (api_factory or (lambda: GithubDataApi(ref=ref)))()
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
    ap.add_argument("--events-limit", type=int, default=EVENTS_DEFAULT)
    ap.add_argument("--out", default="_night_state")
    ap.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS)
    ap.add_argument("--cap-calls", type=int, default=CALL_CAP,
                    help="整夜 LLM 调用上限。每趟最坏 %d 次（提纲 2 + 逐段 2*%d 含补写 + 结构 1 + "
                         "双判 %d + 逐条核查 %d），一条最多 %d 趟 ⇒ 最坏 %d 次；"
                         "现网实测 3 条 71 次（≈24/条，run 35940113012）。"
                         "spec §7：本档先不抬，等分布再定" % (
                             PER_ATTEMPT_CALLS, SECTIONS_MAX, JUDGE_SAMPLES, CLAIM_MAX,
                             MAX_REGEN + 1, ITEM_CALLS_MAX))
    ap.add_argument("--single-pass", action="store_true",
                    help="退回单趟生成（省成本时用这条，代价是 §2 的字数下限再次靠模型自觉）")
    ap.add_argument("--wait-cap", type=int, default=900)
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="单次回复输出上限；不传用客户端默认。单趟路径一次要吐完整条，"
                         "上限低于 %d 时正文会被截断（截断在产物里长得和\"模型写不长\"一样）"
                         % SINGLE_PASS_OUT_TOKENS)
    ap.add_argument("--workers", type=int, default=1,
                    help="并发档；实际取 min(此值, key 数-1, %d) —— 减一是给 judge 留位，"
                         "不留的话满池会把判定饿死" % WORKERS_MAX)
    ap.add_argument("--verdicts", default=None,
                    help="到期判定表 JSON（{\"<forecast claim>\": \"hit|miss|unknown\"}）。"
                         "不传则 predictions_reconciled 全记 unknown —— 宁可读到 unknown，"
                         "也不要把\"没判过\"当成\"都没命中\"")
    ap.add_argument("--date", default=None)
    ap.add_argument("--fake-client", action="store_true",
                    help="只验装配与判定链，不产真洞察；purpose=publish 时会被拒绝")
    ap.add_argument("--ref", default="",
                    help="提交目标分支。purpose=publish 必须显式给（主干=%s）；"
                         "留空即拒绝 —— 上次通道里写死主干，三场验证直接改到了线上" % MAIN_REF)
    a = ap.parse_args(argv)
    event = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    if a.purpose == "publish":
        ok, why = publish_ref_guard(a.purpose, a.ref, event)
        if not ok:
            # 拒绝在任何出网之前：下面一跑就是几十 MB 的锚点/分块池/质量快照与真金白银的调用。
            raise SystemExit("--ref: %s" % why)
    lines = []

    def log_live(s):
        # 以前是 `log=lines.append` 再只打最后 6 行：现网那场三条全降级（narrative 0/196/199 字），
        # 而逐条降级理由与 contract_fails 全部被截在 tail 之外 —— 失败原因根本读不出来。
        lines.append(s)
        try:
            print(s, flush=True)
        except UnicodeEncodeError:
            print(str(s).encode("ascii", "replace").decode(), flush=True)

    verdicts = None
    if a.verdicts:
        with open(a.verdicts, encoding="utf-8") as f:
            verdicts = json.load(f)
        if not isinstance(verdicts, dict):
            raise ValueError("--verdicts 必须是 {claim: hit|miss|unknown} 的 JSON 对象")
    out = night_run(purpose=a.purpose, events_limit=a.events_limit, out_dir=a.out,
                    ref=a.ref,
                    budget_tokens=a.budget_tokens, call_cap=a.cap_calls,
                    wait_cap_s=a.wait_cap, date_str=a.date, max_tokens=a.max_tokens,
                    workers=a.workers, verdicts=verdicts, staged=not a.single_pass,
                    client=FakeClient() if a.fake_client else None,
                    keys=env_keys(), log=log_live,
                    get=http_get)
    b = out["budget"]
    pb = out["payload"]["budget"]
    print("[夜场] 条目 %d（合格 %d / 快讯 %d / 未做 %d）LLM 调用 %d 次、等待 %.0fs、429 %d 次、耗时 %.0fs" % (
        len(out["payload"]["events"]), pb.get("qualified", 0), pb.get("degraded", 0),
        len(out["payload"].get("not_run") or []), b["llm_calls"], b["wait_s"], b["c429"],
        b["elapsed_s"]))
    if pb.get("borderline"):
        # 压线抖动的合格版不算"这条判据救回来的功"：播报里先点名，台账才不会拿它记达标。
        print("::warning title=合格线抖动|本场 %d 条合格是压线版（极差 > %s，"
              "或只判成一遍；其中 %d 条只判了一遍）：按噪声规则不给记功，页面每条已标注原因" % (
                  pb["borderline"], ADOPT_MARGIN, pb.get("single_sample") or 0))
    if pb.get("cap_exceeded"):
        print("::warning title=顶穿调用预算|本场多花 %d 次（cap=%d）：『每趟问一次』的闸在超顶前没拦住，"
              "定档前别拿这条当合格读数" % (pb["cap_exceeded"], b["call_cap"]))
    if b.get("upstream_errors"):
        print("::warning title=上游非限流故障|本场 %d 次请求被 5xx/网络异常打断，"
              "换空闲 key 补试救回 %d 次调用（没救回的照旧进 failed_items/not_run）" % (
                  b["upstream_errors"], b.get("upstream_recovered") or 0))
    if pb.get("coverage_blocked"):
        # 这一档单独报：不然页面"合格 0 / 快讯 N"会被读成"一夜没干活"，
        # 而真相是写了长文、核查一摘就撑不住那条判据（修法在补证据，不在换模型）。
        print("::warning title=核查后复判挡下|本场 %d 条长文因逐条核查摘除后跌破覆盖判据，"
              "按快讯发布并逐条标注原因（正文原长见 narrative_chars_full）" % pb["coverage_blocked"])
    if pb.get("stalled"):
        print("[夜场] 提前收手 %d 条（原因见各条 regen_stalled）：省下的调用留给后续条目"
              % pb["stalled"])
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
