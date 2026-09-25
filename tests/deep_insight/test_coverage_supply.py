# -*- coding: utf-8 -*-
"""覆盖判据的"来源"口径观测（任务 #67）。

现网四场回读时我想算"池子里有几个不同来源"，好判断那条"每 1,500 字换一篇独立来源"
的要求到底可不可满足 —— 结果产物里只有**文章数**：`context_stats.articles=12`
既可能是 12 家媒体，也可能是同一家公众号的 12 篇。
而 `supply = len(valid_ids)`（编号数）与文案说的"不同来源"根本不是一回事：
六篇同源文章照样能过覆盖线。这个分叉不记下来、不算清，S1 与覆盖线两条都只能靠猜
（我这两小时里已经猜错两次：先说"写不到 4,000 字"，再说"池子给不出来源"）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402

CITE_ASK_RE = re.compile(u"citations：([0-9]+)-([0-9]+) 条")
CLAIMS_ASK_RE = re.compile(u"合计至少要覆盖 ([0-9]+) 篇")


def _pool(n_src=3, per_src=4):
    pool, links = {}, []
    for i in range(n_src):
        for j in range(per_src):
            u = "https://s%d.test/a%d_%d" % (i, i, j)
            pool[u] = {"url": u, "source": "src%d" % i, "title": "t",
                       "text": "来源%d第%d篇的独家数字 %d。" % (i, j, 100 + i * 10 + j) * 400,
                       "has_full": True, "source_key": "src%d_%d" % (i, j)}
            links.append(u)
    return pool, links


def test_assemble_context_reports_how_many_distinct_sources():
    """装配器必须同时给"几篇"和"几家"：只有篇数就没法判断覆盖要求可不可满足。"""
    pool, links = _pool(n_src=3, per_src=4)
    arts = D.select_articles({"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘",
                              "links": list(links[:6])}, pool)
    ctx = D.assemble_context(arts, budget_tokens=D.MAX_BUDGET_TOKENS)
    # 夹具给的是 src0 的四篇 + src1 的两篇：六篇文章、两家来源
    assert len(ctx["articles"]) == 6, len(ctx["articles"])
    assert ctx.get("sources") == 2, \
        "只记篇数不记家数，覆盖线要 6 家时看不出这是不可能完成的任务：%s" % sorted(ctx)


def test_context_stats_in_the_artifact_carries_the_source_count(tmp_path):
    """这个数要进产物：只停在装配器里，下一场回读还是算不出来。"""
    pool, links = _pool(n_src=3, per_src=4)
    rec = D.deepen_one({"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": list(links)},
                       pool, D.FakeClient(), D.Budget(400000), D.KeyPool(["k1"]),
                       max_regen=0, source_quality={},
                       sleep=lambda s: None, wait_cap_s=5, staged=True)
    st = (rec.get("context_stats") or {})
    assert st.get("articles"), st
    assert st.get("sources") == len({a.get("source_key", "").split("_")[0]
                                    for a in D.select_articles(
                                        {"id": "e1", "title": "事件甲", "topic": "ai",
                                         "summary": "摘", "links": list(links)}, pool)}), \
        "产物里的 context_stats 没带家数：%s" % sorted(st)


def test_selection_spreads_across_sources_before_taking_extras():
    """一家再贴题也不许占满坑：`srcs` 在补开始前算一次就冻结，同家第 2 篇与别家第 1 篇同权。

    夹具：src1 有 8 篇 5 个共同词的高贴题文章，src2..src7 各 1 篇只有 3 个共同词，
    事件自己的链接来自 src9（⇒ src1 不在 srcs 快照里，与 src2..7 同权，只比重合度）。
    今天按重合度排 ⇒ 先取光 src1，家数塌成个位数。
    """
    def art(src, idx, words):
        u = "https://%s.test/%s_%d" % (src, src, idx)
        return u, {"url": u, "source": src, "title": "%s %s" % (src, words),
                   "text": "内容 %s %s。" % (src, idx) * 400, "has_full": True,
                   "source_key": "%s_%d" % (src, idx)}

    pool = {}
    for i in range(8):
        u, a = art("src1", i, "alpha beta gamma delta epsilon")
        pool[u] = a
    for j in range(2, 8):
        u, a = art("src%d" % j, 0, "alpha beta gamma")
        pool[u] = a
    u9, a9 = art("src9", 0, "alpha beta gamma")
    pool[u9] = a9

    picked = D.select_articles({"id": "e1", "title": "alpha beta gamma roll",
                                "topic": "ai", "summary": "alpha beta",
                                "links": [u9]}, pool)
    by = {}
    for a in picked:
        by[a["source"]] = by.get(a["source"], 0) + 1
    assert len(picked) >= 8, "池里明明有 15 篇可用：%d" % len(picked)
    # 一家不许占过半（第二遍补同家后续篇是设计要的：池子还得凑够量）
    assert by.get("src1", 0) <= len(picked) // 2,         "一家占了 %d/%d 个坑（跨源装配没起作用）：%s" % (
            by.get("src1", 0), len(picked), sorted(by.items()))
    assert len(by) >= 7, "池子里有 8 家，只凑出 %d 家：%s" % (len(by), sorted(by))


# ---------- 覆盖要求的"前置口径"：判据查的是长文，prompt 教的却是短文 ----------

def test_the_prompt_asks_for_the_spread_the_contract_will_check():
    """现网八场 58 条里 11 条死于覆盖，`sources_short` **一条都没亮过**（供给从头到尾够），
    池内中位 12 篇而实际只引 2~6 篇 —— 因为 prompt 写的是"citations：5-12 条"
    与"每 7,500 字要引到 6 篇"，模型照下限交 5 篇，写到 8,848 字就被自己的长度判死。
    要求必须动笔前说清，不能等写完再告。
    """
    p = D._structure_rules(", ".join("c%d" % i for i in range(1, 13)), 12)
    lo, hi = (int(x) for x in CITE_ASK_RE.search(p).groups())
    assert hi == D.CITE_MAX, p[:600]
    assert lo >= D.required_sources(D.NARR_MAX), \
        "引的篇数下界 %d 低于最长正文的派生要求 %d，模型按界交卷必死" % (
            lo, D.required_sources(D.NARR_MAX))
    # claims 那一格的口径必须与 citations 同一个数：两套数字就是两处真相
    assert int(CLAIMS_ASK_RE.search(p).group(1)) == lo, p[:600]


def test_the_ask_never_asks_for_more_than_the_pool_can_supply():
    """反方向同罪：池子只有 4 篇却要模型备 7 篇，就是造一条满足不了的要求 ——
    与刚拆掉的那道"被自引数钳制"的钳制同族，只会把扎实的小条目一律判死。
    池子空（supply=0）时按判据同形取 `max(supply,1)=1`，不许回退成 7（审查 P0-2）。
    """
    for supply, want in ((0, 1), (1, 1), (3, 3), (4, 4), (6, 6), (12, 7), (20, 7)):
        p = D._structure_rules(", ".join("c%d" % i for i in range(1, supply + 1)) or "（无）",
                              supply)
        lo = int(CITE_ASK_RE.search(p).group(1))
        assert lo == want, "池内 %d 篇时要求应为 %d，实为 %d" % (supply, want, lo)
        assert lo <= max(supply, 1) and lo <= D.CITE_MAX, (supply, lo)


def test_the_citation_ask_reaches_the_real_prompt():
    """`_structure_rules` 自己算对了不算数：装配给几篇必须真的传到它手上。

    夹具**故意用 4 家小池子**（审查 P0）：大池子（12 篇）时 `ask=7` 与"漏转发走
    `supply=0` 那一支"同为 7，判据就杀不掉漏转发。小池子下 ask=4，任何一种漏转发都红。
    """
    pool, links = _pool(n_src=4, per_src=1)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    ctx = D.assemble_context(D.select_articles(ev, pool), budget_tokens=D.MAX_BUDGET_TOKENS)
    supply = len(ctx["articles"])
    assert 1 <= supply < D.required_sources(D.NARR_MAX), \
        "夹具失效：池内 %d 篇已够 ask=7，漏转发就测不出来" % supply
    p = D.build_prompt(ev, ctx)
    lo = int(CITE_ASK_RE.search(p).group(1))
    assert lo == min(max(supply, 1), D.required_sources(D.NARR_MAX)), \
        "装配 %d 篇，prompt 却要求 %d 篇（supply 没转发或被写死）" % (supply, lo)
    sp = D.build_structure_prompt(ev, ctx, "正文" * 400)
    assert int(CITE_ASK_RE.search(sp).group(1)) == lo, "补结构字段那趟口径又分叉了"


def test_the_rewrite_feedback_names_the_recycled_facts_for_density():
    """任务 #74 第二步：`density` 中位 0.55（§10.42），而"哪些数被多段复用"我们**本来就算得出**
    —— `restatement_rate` 的 `recycled` 清单已经在喂 judge，重写反馈里却只有一句
    "删掉换句话说的重复段"。模型拿到的是形容词，不是可下手的清单。
    这条判据同时钉两处用同一份渲染：judge 与重写反馈分叉就是第二份真相。
    """
    # 每段必须 >=60 字：`_para_number_sets` 把短于 60 字的碎片直接丢掉，
    # 段落被过滤光的话这条判据测的是夹具尺寸而不是流程（前两版分别因此空转：
    # 一段 50 多字被当成碎片，"60%" 只出现在两段里，recycled 一直是空）。
    def para(head):
        return head + "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 3
    paras = [
        para("该季度收入增长 60%，机制上来自渠道下沉与提价两条线"),
        para("换个说法再看这 60% 的增长，它同样反映在毛利改善上"),
        para("第三方口径下的 60% 也被反复引用，反证是季节性备货"),
        para("第四段讲竞争格局变化，头部两家把产能转向中低端"),
        para("第五段给监管窗口与可核验指标，看备案数量与投诉率"),
    ]
    cand = {"id": "e1", "title": "事件甲", "topic": "ai",
            "narrative": "\n\n".join(paras), "claims": [], "causal_chains": [],
            "forecasts": [], "citations": [],
            "quality": {"verdict": "一手", "score": 70, "why": "依" * 40, "basis": ["sig:c1"]}}
    listed = D.restate_fact_list_text(cand)
    assert listed != "（无）", "夹具没造出被 ≥3 段复用的数：这条判据会空转"
    score = {"mean": 0.60, "judged": True, "narrative": 0.8, "causal": 0.7,
             "forecast": 0.6, "quality": 0.6, "density": 0.4}
    out = D.judge_weak_spots(score, cand=cand)
    fact = listed.split(u"（")[0]
    assert any(fact in s for s in out), \
        "重写反馈没点名被复用的数（%s），只给了形容词：%s" % (listed, out)
    assert any(u"密度" in s or u"density" in s for s in out), out
    # 不传 cand 时不许崩，也不许凭空造清单
    assert not any(fact in s for s in D.judge_weak_spots(score)), "没给正文却印出了清单：那是伪造"


def test_the_recycled_fact_list_reaches_the_real_rewrite_prompt():
    """只单测 `judge_weak_spots(cand=...)` 测不到"调用处忘了传 cand"——
    R2 那次就是这么存活的（同一个教训：每条出口都要有自己那条真链路判据）。
    这条跑 `deepen_one`：判定给 density 0.4 ⇒ 触发重写，抓**重写那一趟真正收到的 prompt**。
    """
    def para(head):
        # 每段必须落在 [PARA_MIN, PERA_MAX] = [716, 1666] 字里，
        # 短了会先死在"每段太短"那条契约上，测的就不是密度了。
        return head + "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 28
    narr = "\n\n".join(para("第%d个角度看这 60%% 的增长来自渠道下沉与提价" % i) for i in range(6))

    class Rec(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.gen = []

        def complete(self, prompt, key=None, kind="generate"):
            self.calls.append(kind)
            if kind == "judge":
                return json.dumps({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                                   "quality": 0.9, "density": 0.4})
            if kind == "generate":
                self.gen.append(prompt)
                doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="structure"))
                doc["narrative"] = narr
                return json.dumps(doc, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool, links = _pool(n_src=12, per_src=2)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    c = Rec()
    rec = D.deepen_one(ev, pool, c, D.Budget(400000), D.KeyPool(["k1"]),
                       max_regen=1, source_quality={}, sleep=lambda s: None,
                       wait_cap_s=5, staged=False)
    assert len(c.gen) == 2, "没触发重写（generate 只跑了 %d 趟），这条判据测不到反馈" % len(c.gen)
    assert u"被多段复用的数" in c.gen[1], \
        "重写那一趟收到的还是形容词，没带清单：%r" % c.gen[1][-320:]
    assert u"60%（" in c.gen[1], "清单里没点名 60%：那是伪造或漏传 cand"
    assert (rec.get("rubric") or {}).get("density") == 0.4, rec.get("rubric")


def test_the_section_pass_only_gets_what_a_paragraph_can_act_on():
    """逐段那一趟只收"本段改得动"的那几条（审查 P2-5），结构字段的账仍发给补结构那一趟。

    把"预测窗口不对""优质判断依据不足"这类整条级要求塞给只写一段的人，它既做不到、
    又要在一趟里为它们重写本段；而这些原文里还嵌着模型自报的字符串（verdict 原值、
    编造的 basis 编号），等于新开一条把模型散文送回正文的通道（P2-4）。
    所以这里两头都断：段落那趟**收得到**密度那条，**收不到**预测与优质那两条；
    结构那趟照旧收得到全部（账不能因为分流而丢掉）。
    """
    def para(i):
        return ("第%d个角度看这 60%% 的增长来自渠道下沉与提价" % i +
                "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 28)

    class Rec(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.outline_n = 0
            self.sec, self.st = [], []

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.outline_n += 1
            if kind == "section":
                self.sec.append((self.outline_n, prompt))
                return para(len(self.sec))
            if kind == "structure":
                self.st.append((self.outline_n, prompt))
            if kind == "judge":
                return json.dumps({"narrative": 0.9, "causal": 0.9, "forecast": 0.4,
                                   "quality": 0.4, "density": 0.4})
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool, links = _pool(n_src=12, per_src=2)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    c = Rec()
    D.deepen_one(ev, pool, c, D.Budget(400000), D.KeyPool(["k1"]),
                 max_regen=1, source_quality={}, sleep=lambda s: None,
                 wait_cap_s=5, staged=True)
    second = [p for (n, p) in c.sec if n == 2]
    assert second, "第二趟没逐段成文：%s" % (c.outline_n,)
    assert all(u"信息密度偏弱" in p for p in second), \
        "段落那趟收不到它改得动的那条（分流分掉了正事）：%r" % second[0][:200]
    for p in second:
        assert u"趋势预测偏弱" not in p and u"内容优质判断偏弱" not in p, \
            "整条级的要求又被塞给只写一段的人了：%r" % p[:200]
    st2 = [p for (n, p) in c.st if n == 2]
    assert st2 and all(u"趋势预测偏弱" in p and u"内容优质判断偏弱" in p for p in st2), \
        "补结构那一趟没收到全部分项建议（账在分流里丢了）：%r" % [(n, p[:120]) for n, p in c.st]


def test_a_contract_failure_never_claims_a_judge_score():
    """契约没过 ⇒ 判定根本没跑 ⇒ 段落那趟不许收到"judge 均分 0.00 低于 0.75"。

    批 3.13 第一轮的分流在这里露出了一个谎：`judge_weak_spots` 无条件先放一行均分，
    于是 `sec` 永远非空，"没跑判定"的那一轮也给写字的人印一句"上一版判分偏弱"。
    这正是 `rubric_display` 为页面修过的同一个错（任务 #61：没送判定 != 判了 0 分），
    而它顺着新开的通道爬进了 prompt。
    """
    def para(i):
        return ("第%d个角度看这 60%% 的增长来自渠道下沉与提价" % i +
                "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 28)

    class Rec(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.outline_n = 0
            self.sec = []

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.outline_n += 1
            if kind == "section":
                self.sec.append((self.outline_n, prompt))
                # 第一趟整条写得太短 ⇒ 契约没过 ⇒ 判定根本没跑
                return "只写了一句。" if self.outline_n == 1 else para(len(self.sec))
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool, links = _pool(n_src=12, per_src=2)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    c = Rec()
    rec = D.deepen_one(ev, pool, c, D.Budget(400000), D.KeyPool(["k1"]),
                       max_regen=1, source_quality={}, sleep=lambda s: None,
                       wait_cap_s=5, staged=True)
    assert c.outline_n == 2, "第一趟没死在契约上（提纲跑了 %d 趟）" % c.outline_n
    second = [p for (n, p) in c.sec if n == 2]
    assert second, "第二趟没逐段成文"
    for p in second:
        assert u"judge 均分" not in p and u"判分偏弱" not in p, \
            "判定根本没跑，却对写字的人说上一版判分偏弱：%r" % p[:260]


def test_the_ask_is_never_looser_than_the_contract_itself():
    """把"prompt 会不会要求得过松"变成一条不等式，而不是两边的口头判断。

    判据在任意长度 n 处的要求是 `need_cov = min(required_sources(n), max(supply,1))`；
    前置要求取 `min(max(supply,1), required_sources(NARR_MAX))`。因为 n ≤ NARR_MAX 时
    `required_sources(n) ≤ required_sources(NARR_MAX)`，所以对**任何合法长度与任何池子**
    前置要求都不低于当场判据；同时它永不高于 `CITE_MAX`，否则 prompt 会教出一条
    必然落在 `[cite_floor, CITE_MAX]` 之外的区间（审查 P2）。
    """
    for supply in range(0, 21):
        p = D._structure_rules(", ".join("c%d" % i for i in range(1, supply + 1)) or "（无）",
                              supply)
        ask = int(CITE_ASK_RE.search(p).group(1))
        claims_ask = int(CLAIMS_ASK_RE.search(p).group(1))
        assert ask <= D.CITE_MAX, (supply, ask)
        # claims 那一格是 `ask` 本体（citations 那格还被 cite_low 的 max 托着）：
        # 只断 citations 的话，"丢掉 max(supply,1) 钳"这种变异体改的就是它却测不出来（Q1 存活）。
        assert claims_ask <= D.CITE_MAX, (supply, claims_ask)
        for n in range(D.NARR_MIN, D.NARR_MAX + 1, 500):
            need_cov = min(D.required_sources(n), max(supply, 1))
            assert claims_ask >= need_cov, \
                "池内 %d 篇 / 正文 %d 字：判据要 %d 篇，prompt 的 claims 只要 %d 篇" % (
                    supply, n, need_cov, claims_ask)
            assert ask >= need_cov, (supply, n, need_cov, ask)


def test_the_rewrite_feedback_reaches_the_section_pass():
    """重写反馈必须落到**真正写字的那一趟**（审查 P1-1）。

    staged 是生产默认（只有 `--single-pass` 才关），而上一版 `extra` 只进了提纲与结构
    两趟：逐段成文那一趟收不到清单，于是 #74 第二步（把"被多段复用的数"点名给模型）
    在现网等于从没生效过 —— 单测只跑 `staged=False` 时全套照样绿。
    """
    def para(i):
        # 每段必须落在 [PARA_MIN, PERA_MAX] 里，且同一个数在多段复用：
        # 短了会先死在"每段太短"那条契约上，测的就不是密度反馈了。
        return ("第%d个角度看这 60%% 的增长来自渠道下沉与提价" % i +
                "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 28)

    class Rec(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.outline_n = 0
            self.sec = []              # [(第几趟, prompt)]

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.outline_n += 1
            if kind == "section":
                self.sec.append((self.outline_n, prompt))
                return para(len(self.sec))
            if kind == "judge":
                return json.dumps({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                                   "quality": 0.9, "density": 0.4})
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool, links = _pool(n_src=12, per_src=2)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    c = Rec()
    rec = D.deepen_one(ev, pool, c, D.Budget(400000), D.KeyPool(["k1"]),
                       max_regen=1, source_quality={}, sleep=lambda s: None,
                       wait_cap_s=5, staged=True)
    assert c.outline_n == 2, \
        "没触发重写（提纲只跑了 %d 趟），这条判据测不到反馈：%s" % (c.outline_n, rec.get("contract_fails"))
    second = [p for (n, p) in c.sec if n == 2]
    assert len(second) >= D.PARAS_MIN, \
        "第二趟没逐段成文（section 只收到 %d 次调用）：%s" % (len(second), sorted(rec))
    assert all(u"被多段复用的数" in p for p in second), \
        "重写反馈没进逐段成文那一趟，写字的人收到的还是形容词：%r" % second[0][-320:]
    assert all(u"60%（" in p for p in second), \
        "清单没点名 60%：那是伪造或漏传 cand：%r" % second[0][-320:]


def test_the_short_section_retry_carries_the_feedback_too():
    """写太短那一趟重问（`again = ...`）是**第二个调用点**：只给第一处补上反馈，
    这条出口照旧收不到清单 —— 一个函数两个出口只测一个，是本仓 R2/Q9 那轮的教训。
    """
    def para(i):
        return ("第%d个角度看这 60%% 的增长来自渠道下沉与提价" % i +
                "，这条判断仍受样本量与统计口径限制，需要到期复核口径。" * 28)

    class Rec(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.outline_n = 0
            self.in_attempt = 0
            self.sec = []

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.outline_n += 1
                self.in_attempt = 0
            if kind == "section":
                self.in_attempt += 1
                # 每趟第一段第一次写都太短 ⇒ 逼出重试那一趟
                if self.in_attempt == 1:
                    self.sec.append((self.outline_n, prompt))
                    return "这一版只写了一句。"
                self.sec.append((self.outline_n, prompt))
                return para(self.in_attempt)
            if kind == "judge":
                return json.dumps({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                                   "quality": 0.9, "density": 0.4})
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    pool, links = _pool(n_src=12, per_src=2)
    ev = {"id": "e1", "title": "事件甲", "topic": "ai", "summary": "摘", "links": list(links)}
    c = Rec()
    D.deepen_one(ev, pool, c, D.Budget(400000), D.KeyPool(["k1"]),
                 max_regen=1, source_quality={}, sleep=lambda s: None,
                 wait_cap_s=5, staged=True)
    second = [(n, p) for (n, p) in c.sec if n == 2]
    retried = [p for (n, p) in second if u"接着写第 1/%d 段" % D.PARAS_MIN in p]
    assert len(retried) == 2, \
        "没造出'写太短→重问'那一路（第 1 段被调用 %d 次）：%s" % (len(retried), c.outline_n)
    assert all(u"被多段复用的数" in p for p in retried), \
        "重问那一趟的 prompt 没带清单：改第一个调用点就以为两处都修了"

