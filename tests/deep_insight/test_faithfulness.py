# -*- coding: utf-8 -*-
"""批 2：逐条事实核查（`validate_event` 只查引用编号**存在**，查不出"编号存在但这句话不在里面"）。

现网证据：09-23 那条合格条目（judge 给了 narrative 0.85）正文里写着
「2026 年第三季度企业 AI 服务采购数据显示，OpenAI 占约 58%、Anthropic 约 22%」，
而我方那 5 篇引源里没有这个口径 —— 这种句子在现有契约下不可能被抓到：
编号 c2 是真的、链接是真的、句子是模型自己加的。

白天线为此写过 `_verify_faithfulness:3036` + `_final_faith_recheck:3119`（faith≥0.88），
夜场没有对应物。这里补的是同一件事，但按夜场的政策做：**违约只摘那一条 claim，不废整篇**
（§10.16 已经定过"一格违约只摘那一条"，代价与过错要成比例）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _ctx(n=4):
    arts = [{"url": "https://s%d.test/a%d" % (i, i), "source": "src%d" % i,
             "title": "T%d" % i, "text": "来源%d的全文内容，含独家数字 %d。" % (i, 100 + i) * 300,
             "has_full": True, "source_key": "src%d_%d" % (i, i)} for i in range(n)]
    return {"articles": arts,
            "ids": {"c%d" % (i + 1): a["url"] for i, a in enumerate(arts)},
            "signals": {}, "quality_signals": {}}


def _cand(n_cites=8, n_claims=6):
    ids = ["c%d" % (i + 1) for i in range(n_cites)]
    nar = "\n\n".join("论证与数据推演%d，但该判断仍受样本量与统计口径限制。" % i
                      for i in range(n_cites))
    return {
        "id": "e1", "title": "事件甲", "topic": "ai", "narrative": nar,
        "claims": [{"text": "论断%d：%d%% 的份额在迁移" % (i, 40 + i), "kind": "causal",
                    "evidence": [ids[i % len(ids)]]} for i in range(n_claims)],
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": "中高", "evidence": [ids[0]]} for _ in range(3)],
        "forecasts": [{"claim": "七天内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类发布数>=3"}],
        "quality": {"verdict": "一手", "score": 82, "why": "依" * 60, "basis": ["sig:c1"]},
        "citations": [{"id": i, "url": "https://s.test/%s" % i} for i in ids],
    }


class Scripted(object):
    """按 claim 顺序喂判定：verdict 列表用完就回 supported。"""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.prompts = []
        self.kinds = []

    def complete(self, prompt, key=None, kind="generate"):
        self.prompts.append(prompt)
        self.kinds.append(kind)
        if kind == "faith":
            v = self.verdicts.pop(0) if self.verdicts else "supported"
            return json.dumps({"verdict": v, "reason": "该句在给定证据里没有对应数字",
                               "quote": "来源0的全文内容" if v == "supported" else ""})
        return json.dumps({})


def test_faith_prompt_carries_only_that_claims_own_evidence():
    """核查方看到的必须是**这条 claim 引的那几篇全文**，不是摘要也不是片段。

    白天在 `_verify_faithfulness` 上写过专门的注释：核查上下文与评估域不一致时，
    会出现"judge 看得见、核查编辑看不见"，结果是把真实报道判成无支撑而删掉。
    """
    ctx = _ctx(4)
    claim = {"text": "60% 的份额在迁移", "kind": "causal", "evidence": ["c2"]}
    p = D.build_faith_prompt({"title": "事件甲", "topic": "ai"}, ctx, claim)
    assert ctx["articles"][1]["text"][:40] in p, "没把 c2 的全文给核查方：它凭什么判有无支撑"
    assert ctx["articles"][3]["text"][:40] not in p, "把没引的 c4 也塞进去了：核查域被放大"
    assert "60%" in p and "原文原句" in p, "prompt 没要求给出支撑原句，判定方可以自己编"


def test_unsupported_claim_is_dropped_not_fatal():
    """无支撑 ⇒ 摘那一条并留原文与理由，整篇不废。"""
    cand = _cand()
    n0 = len(cand["claims"])
    kept = D.apply_faith(cand, [{"verdict": "unsupported", "reason": "查无此数",
                                 "quote": ""}] + [{"verdict": "supported", "reason": "在",
                                                   "quote": "原文"}] * (n0 - 1))
    assert len(kept) == n0 - 1, kept
    assert cand["faith_summary"]["kept"] == n0 - 1, cand["faith_summary"]
    d = cand["claims_dropped"][0]
    assert "40%" in d["claim"] or "论断0" in d["claim"], d
    assert d["reason"] == "查无此数", d


def test_inflated_claim_is_dropped_and_distinguished():
    """数字对不上（inflated）与完全无支撑（unsupported）要分开记 ——
    前者是模型改了数，后者是模型凭空加，修法不同。"""
    cand = _cand()
    D.apply_faith(cand, [None, {"verdict": "inflated", "reason": "证据里是 42% 不是 41%",
                                "quote": "42%"}])
    assert cand["claims_dropped"][0]["verdict"] == "inflated", cand["claims_dropped"]
    assert cand["faith_summary"]["inflated"] == 1, cand["faith_summary"]


def test_unparseable_verdict_is_never_silently_supported():
    """判定读不出来 ⇒ 保留该 claim 但记 unknown。
    静默当 supported 就是"核查过了"的假凭证；静默当 unsupported 会误删真话。"""
    cand = _cand(n_claims=3)
    ok_v = {"verdict": "supported", "reason": "在", "quote": "来源0全文"}
    D.apply_faith(cand, [{"verdict": "garbage"}, ok_v, ok_v])
    assert len(cand["claims"]) == 3, "读不懂就把 claim 删了：这是误删"
    assert cand["faith_summary"]["unknown"] == 1, cand["faith_summary"]


def test_faith_dropping_below_claim_minimum_is_reported_not_hidden():
    """摘到低于 CLAIM_MIN 必须显式说出来 —— 那才是该重写的信号，
    而不是让 validate_event 在别处报一个看起来无关的数。"""
    cand = _cand(n_claims=3)
    res = D.apply_faith(cand, [{"verdict": "unsupported", "reason": "无", "quote": ""}] * 2)
    assert len(res) == 1
    assert cand["faith_summary"]["below_minimum"] is True, cand["faith_summary"]


def test_deepen_one_calls_faith_after_the_text_is_final():
    """顺序要有保证：正文没定稿就核查，等于核掉一版马上就要被重写的文本。"""
    ctx = _ctx(4)
    pool, links = {}, []
    for i in range(4):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "T%d" % i,
                   "text": "来源%d全文，独家数字 %d。" % (i, 100 + i) * 900,
                   "has_full": True, "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    kinds = []

    class Faithful(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            kinds.append(kind)
            if kind == "faith":
                return json.dumps({"verdict": "supported", "reason": "在",
                                   "quote": "来源0全文"})
            if kind == "structure":
                # FakeClient 的样本发 6 条引用、编号从 c0 起；这个池子只有 4 篇。
                # 截成 c1..c4 且不重复：回绕会撞"citations id 有重复"，压成同一个又会出现
                # 没引过的编号 —— 两种都会让这条判据卡在契约上而不是卡在核查上。
                doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind=kind))
                doc["citations"] = [{"id": "c%d" % (i + 1),
                                     "url": "https://s%d.test/a%d" % (i, i)} for i in range(4)]
                for i, cl in enumerate(doc.get("claims") or []):
                    cl["evidence"] = ["c%d" % (i % 4 + 1)]
                return json.dumps(doc, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool_urls = list(links)
    rec = D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": pool_urls},
                       pool, Faithful(), D.Budget(400000), D.KeyPool(["k1"]),
                       source_quality={}, sleep=lambda s: None, wait_cap_s=5)
    assert "faith" in kinds, "核查根本没跑：字段是假的：%s" % kinds
    assert kinds.index("faith") > kinds.index("structure"), \
        "核查在正文定稿之前跑：%s" % kinds
    assert rec.get("faith_summary"), "产物里没有核查账：读的人无从知道它跑过"


# ---------- 任务 #69：核查摘过 claims 之后，必须在最终形态上复跑判据 ----------

def _coverage_break_client():
    """夹具：4 篇池子、7 条论断按 c1..c4 轮着挂证据。
    判据要 4 篇；核查看掉挂 c3/c4 的那几条后，剩下 4 条（≥CLAIM_MIN，所以
    `below_minimum` 不响）只压住 c1/c2 两篇 ⇒ **只有复跑判据才抓得住**。
    """
    class Breaker(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.faith_n = 0

        def complete(self, prompt, key=None, kind="generate"):
            self.calls.append(kind)
            if kind == "faith":
                i = self.faith_n % 7
                self.faith_n += 1
                bad = i in (2, 3, 6)          # 挂 c3/c4/c3 的那三条
                return json.dumps({"verdict": "unsupported" if bad else "supported",
                                   "reason": "查无对应数字" if bad else "在",
                                   "quote": "" if bad else "来源0全文"})
            if kind == "structure":
                doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind=kind))
                doc["citations"] = [{"id": "c%d" % (i + 1),
                                     "url": "https://s%d.test/a%d" % (i, i)} for i in range(4)]
                for i, cl in enumerate(doc.get("claims") or []):
                    cl["evidence"] = ["c%d" % (i % 4 + 1)]
                return json.dumps(doc, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)
    return Breaker()


def _four_article_env():
    pool, links = {}, []
    for i in range(4):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "T%d" % i,
                   "text": "来源%d全文，独家数字 %d。" % (i, 100 + i) * 900,
                   "has_full": True, "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    return pool, links


def test_a_faith_drop_that_breaks_coverage_is_not_shipped_as_qualified():
    """现网八场去重后 6 条合格里 **5 条**是这个形状：`verify_claims` 在 `validate_event`
    之后摘 claims，摘完"正文压在几篇证据上"跌破要求，却没有任何复判（`_scratch/replay_read.txt`）。
    含第 35 场那条 mean=0.8125 的稳定达标条目：9,142 字要 7 篇，出厂时只剩 6 篇。

    有重写预算时这一支必须**被记成一次拒绝**（`rejected=faith_coverage`）：
    只把它塞进降级路径的话，"复判挡下了"与"没预算只能降级"两种停在产物里长得一样（Q9 存活教训）。
    """
    pool, links = _four_article_env()
    rec = D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": list(links)},
                       pool, _coverage_break_client(), D.Budget(400000), D.KeyPool(["k1"]),
                       source_quality={}, sleep=lambda s: None, wait_cap_s=5)
    fs = rec.get("faith_summary") or {}
    assert fs.get("dropped"), "夹具没让核查摘掉任何 claim，这条判据就测不到东西：%s" % (fs,)
    assert not fs.get("below_minimum"), \
        "夹具退化成了'摘到不足 CLAIM_MIN'那条老路（%s）：本次要测的是只破覆盖的那一支" % (fs,)
    kept_ev = set()
    cited = {c.get("id") for c in (rec.get("citations") or [])}
    for cl in (rec.get("claims") or []):
        kept_ev |= set(cl.get("evidence") or [])
    assert len(kept_ev & cited) < D.required_sources(
        rec.get("narrative_chars_full") or len(rec.get("narrative") or "")), \
        "夹具没真把覆盖摘破：压了 %d 篇" % len(kept_ev & cited)
    traj = rec.get("regen_scores") or []
    assert any(t.get("rejected") == "faith_coverage" for t in traj), \
        "复判没被当成一次拒绝（要么根本没跑，要么直接兜成降级）：%s" % (traj,)
    assert rec.get("post_faith_contract_fails"), "复判结果没进产物，读者看不出它是复判挡下的"


def test_out_of_regen_budget_a_coverage_break_degrades_with_its_own_reason():
    """没有重写预算时：照 §10.16 降级不静默，而且理由要指名是"核查摘出来的锅"。

    这条专防两具变异体：把 `faith_coverage_broken` 旗标摘掉（降级根本不发生，Q11），
    与把 `_degrade_reason` 那一支短路（四笔账又混成一句"重写 N 次仍不合格"，Q12）。
    违约原文还要并进 `contract_fails`：页面与探针读的都是那一格，
    只放新字段的话这条账在现网读数里隐身。
    """
    pool, links = _four_article_env()
    rec = D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": list(links)},
                       pool, _coverage_break_client(), D.Budget(400000), D.KeyPool(["k1"]),
                       max_regen=0, source_quality={}, sleep=lambda s: None, wait_cap_s=5)
    reason = (rec.get("degraded_reason") or "").strip()
    assert reason, "摘破覆盖却没有降级理由：出厂那一版仍被当合格（%s）" % sorted(rec)
    assert u"核查" in reason and u"篇" in reason, \
        "理由没点名是核查摘除那一笔账：%s" % reason
    assert rec.get("faith_coverage_broken") is True, sorted(rec)
    assert any(u"只压在" in f or u"只引了" in f for f in (rec.get("contract_fails") or [])), \
        "违约原文没进 contract_fails，探针与页面读不到这一档：%s" % (rec.get("contract_fails"),)
    # 要求那一份要与判据同式：池内只有 4 篇时不许报出 5 篇以上这种给不出的数
    supply = (rec.get("context_stats") or {}).get("articles") or 0
    import re as _re
    m = _re.search(u"要 >=([0-9]+) 篇", reason)
    assert m and int(m.group(1)) <= max(supply, 1), \
        "降级理由报了供给给不出的要求（池内 %d 篇 / 理由里 %s）：%s" % (supply, m and m.group(1), reason)
    # 降级走的是既有快讯通道 ⇒ 正文被裁到上限，原长留在 `narrative_chars_full`。
    # 这一格把代价钉死：现网第 35 夜那条 mean=0.8125 的合格条目若当时有本判据，
    # 出厂形态就是 200 字快讯（原文 9,142 字）—— 保留正文还是照旧裁，是产品决定（任务 #71）。
    assert D.count_chars(rec.get("narrative") or "") <= D.DEGRADED_NARR_MAX, \
        "降级却没用降级通道（正文 %d 字）：上屏会撞'快讯超长'那一判据" % len(rec.get("narrative") or "")
    assert (rec.get("narrative_chars_full") or 0) > D.DEGRADED_NARR_MAX, \
        "原长没记进产物：裁掉多少字就没人能核对"


def test_the_post_faith_recheck_finds_only_new_breaks():
    """复判只在**核查真摘过**时跑：没摘过就别再算一遍，否则同一张判据被问两遍，
    停滞规则的"同批违约"比较会被我自己的重复计数带偏。
    摘过且摘破了覆盖 ⇒ 必须报出那一条违约原文（重写反馈与降级文案都要用它）。
    """
    ids = {"c1", "c2", "c3", "c4"}
    cand = _cand(n_cites=4, n_claims=3)
    # 正文必须真够长：短文本的派生要求只有 1 篇，"摘破覆盖"这个形状根本不会出现
    cand["narrative"] = "\n\n".join(
        "论证与数据推演%s，但该判断仍受样本量与统计口径限制。" % ("依" * 400)
        for _ in range(14))
    n = D.count_chars(cand["narrative"])
    assert D.required_sources(n) >= 3, "夹具字数不够：n=%d 时派生要求只有 %d 篇" % (
        n, D.required_sources(n))
    assert D.faith_broke_contract(cand, ids) == [], \
        "没摘过 claims 也跑复判：那是一笔没发生的账"
    # 摘到三条论断全挂 c1 ⇒ 覆盖从 4 篇塌成 1 篇，而 claims 数仍 ≥ CLAIM_MIN
    for cl in cand["claims"]:
        cl["evidence"] = ["c1"]
    cand["faith_summary"] = {"checked": 6, "kept": 3, "dropped": 3, "below_minimum": False}
    broke = D.faith_broke_contract(cand, ids)
    assert any(u"只压在" in f or u"只引了" in f for f in broke), \
        "摘破覆盖却没报出来，出厂的那一版仍然是没人检查过的：%r" % (broke,)


def test_the_coverage_block_count_reaches_the_aggregate():
    """复判挡下必须进聚合与播报，否则"合格 0"这一格读起来像"一夜没干活"。

    现网后果已数过（台账 §10.41）：#69 严格生效后，八场里有五场会从"1 条长文 + 7 条快讯"
    变成"全场快讯"。聚合里没有这一列，跨夜就只能看到 qualified 掉 0，
    分不清是"模型写不动"还是"核查摘破了下不了线" —— 那是两种要修在不同地方的病。
    """
    evs = [{"id": "a", "degraded_reason": "复判挡下", "faith_coverage_broken": True},
           {"id": "b", "degraded_reason": "本来就短"},
           {"id": "c"}]
    p = D.build_payload(evs, {}, D.Budget(100000), "2026-09-24")
    assert p["budget"]["coverage_blocked"] == 1, p["budget"]
    assert p["budget"]["qualified"] == 1 and p["budget"]["degraded"] == 2, p["budget"]


def test_the_generic_degrade_reason_names_the_weakest_dimension():
    """现网八场 58 条里 35 条死在"判分没过线"，其中 **34 条的理由是同一句
    "重写 N 次仍不合格"** —— 分数差在预测、差在密度、差在因果是三种不同的修法，
    印成一句话下一批挑靶子就只能靠猜（本仓为"四笔账不能混成一句"改过三轮）。
    五维分值本来就在 `rubric` 里，点名不花任何调用。
    """
    score = {"mean": 0.606, "narrative": 0.825, "causal": 0.685, "forecast": 0.475,
             "quality": 0.55, "density": 0.55, "judged": True}
    why = D._degrade_reason(2, 2, [], {}, last_score=score)
    assert u"forecast" in why, "最弱那一维没进理由：%s" % why
    assert u"0.475" in why and u"0.606" in why, "分数没带上，读的人没法判断差多少：%s" % why
    # 没有判定读数时不许编：宁可用旧文案，也不能印一个凭空点出来的维度名
    assert u"forecast" not in D._degrade_reason(2, 2, [], {}), "没读数却点名了维度：那是伪造"


def test_the_weakest_dimension_note_survives_the_real_call_path():
    """上一条判据直接调 `_degrade_reason(last_score=...)`，所以"调用处忘了传"它测不到
    （R2 存活就是这么来的：函数有读数、caller 没给 ⇒ 页面上永远是那句笼统理由）。
    这条走 `deepen_one` 真链路：契约能过、判定打低分 → 重写到头 → 降级理由带着最弱那一维。

    池子必须给到 6 篇：FakeClient 的 claims 会绕着编号铺 c1..c7，4 篇池子会先死在
    "citation id 不在检索池里"那一判据上（分数根本没跑，理由当然没有维度）——
    第一版我就是这么写错的，别把夹具错当成功能缺失。
    """
    pool, links = {}, []
    for i in range(6):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "T%d" % i,
                   "text": "来源%d全文，独家数字 %d。" % (i, 100 + i) * 900,
                   "has_full": True, "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    rec = D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": list(links)},
                       pool, D.FakeClient(judge_pass=False), D.Budget(400000),
                       D.KeyPool(["k1"]), max_regen=0, source_quality={},
                       sleep=lambda s: None, wait_cap_s=5)
    rub = rec.get("rubric") or {}
    assert rub.get("judged") is not False and rec.get("contract_fails") == [], \
        "夹具先死在契约上，测不到分数那一档：%s" % (rec.get("contract_fails"),)
    assert rub.get("mean", 1.0) < D.JUDGE_PASS, rub
    reason = (rec.get("degraded_reason") or "")
    assert u"最弱" in reason and u"判定中位" in reason, \
        "理由没点名最弱那一维（调用处漏传 last_score 就是这个形状）：%s" % reason


def test_faith_calls_are_bounded_by_claims():
    """成本要封顶：每条 claim 一次，不许顺带多问。"""
    kinds = []

    class Counting(Scripted):
        def complete(self, prompt, key=None, kind="generate"):
            kinds.append(kind)
            return Scripted.complete(self, prompt, key=key, kind=kind)

    c = Counting(["supported"] * 9)
    ctx = _ctx(4)
    cand = _cand(n_claims=6)
    D.verify_claims({"title": "甲", "topic": "ai"}, cand, ctx, c,
                    D.KeyPool(["k1"]), D.Budget(400000))
    assert kinds.count("faith") == 6, kinds


def test_dropped_claims_are_announced_on_the_page_without_model_text():
    """A5 的后半句：`claims_dropped` 非空时页面要标注摘了几条，否则"核查有牙"只在 JSON 里。

    同时钉一条红线：只报我们自己算出的条数 —— `reason` 是模型写的文本，
    里面可能带着假链接，跟着上屏就绕过 citations 的清洗。
    """
    ev = {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400,
          "claims": [{"text": "留下的论断", "kind": "causal", "evidence": ["c1"]}],
          "causal_chains": [], "forecasts": [], "citations": [],
          "quality": {"verdict": "一手", "score": 80, "why": "x", "basis": []},
          "rubric": {"mean": 0.8},
          "claims_dropped": [{"claim": "被摘的", "verdict": "unsupported",
                              "reason": "见 https://fabricated.example/never-existed"},
                             {"claim": "被摘的2", "verdict": "inflated", "reason": "数字对不上"}],
          "faith_summary": {"checked": 6, "kept": 4, "dropped": 2}}
    html = D.render_page({"date": "2026-09-24", "events": [ev], "budget": {}, "anchor_diff": []})
    assert "已摘除 2 条" in html, "页面没标注摘除条数：A5 只落在 JSON 里，读者看不见"
    assert "6" in html and "fabricated" not in html, \
        "核查理由里的模型文本跟着上屏了（假链接就是这么上线的）"
