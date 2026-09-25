# -*- coding: utf-8 -*-
"""夜场质量为什么"比每场构建还差"——现网实测给出的四条修复。

来历（全部是 2026-09-23 现网 daily-deep-2026-09-23.json 的读数，不是我造的样本）：
  · evt_011 判合格、9,857 字，但素材池 12 篇 / 635,321 字它只引了 5 篇；
    11 段里 6 段在换句话复述同一批数据（66.4% 出现 4 段、5.98/3.26 出现 4 段、
    "降 40%" 出现 5 段）。旧的句级重复率对它读数 0.0 —— 那个指标看不见复述。
  · 覆盖判据 `need_cov = min(len(cited_ids), ceil(n/EVID_CHARS))` 把要求钳在
    "模型自己引了几篇"上：9,857 字要 7 篇，只引 5 篇时要求自动降到 5，
    于是这条判据在它唯一该出手的长文场景里必然通过。
  · evt_008 素材 115,487 字、7 段已成文，只因 quality.verdict 返回
    "一手/数据支撑"（枚举里两个合法值中间一个斜杠）重写 2 次后整条降成 200 字快讯。
所以这里的修复是：把复述量成能看的数、把覆盖要求从自引数上解绑、
把枚举复合值修好而不是烧掉一整条，以及让提纲阶段就没有"两段抢一篇源"的结构。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402

FIX = json.load(open(os.path.join(ROOT, "tests", "deep_insight", "fixtures",
                                  "live_evt011_number_sets.json"), encoding="utf-8"))


def _para(target, marker="但该判断仍受样本量与统计口径限制。"):
    body = "论证与数据推演"
    i = 0
    while D.count_chars(body + marker) < target:
        i += 1
        body += "证据%d显示投入与产出之间存在可核对的落差，需要结合口径差异来看。" % i
    return body + marker


def _narrative(total_target, paras=8):
    per = total_target // paras + 10
    return "\n\n".join(_para(per) for _ in range(paras))


def _cand(chars=9000, n_cites=8, verdict="一手"):
    nar = _narrative(chars)
    ids = ["c%d" % (i + 1) for i in range(n_cites)]
    claims = [{"text": "论断%d" % i, "kind": "causal",
               "evidence": [ids[i % len(ids)]]} for i in range(8)]
    return {
        "id": "e1", "title": "事件甲", "topic": "ai", "narrative": nar,
        "claims": claims,
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": "中高", "evidence": [ids[0]]} for _ in range(3)],
        "forecasts": [{"claim": "预计七天内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类竞品发布数>=3"}],
        "quality": {"verdict": verdict, "score": 82, "why": "依" * 60, "basis": ["sig:c1"]},
        "citations": [{"id": i, "url": "https://s.test/%s" % i} for i in ids],
    }


VALID = {"c%d" % (i + 1) for i in range(12)}


# ---------- 复述度量：阈值拿现网真样本校准 ----------

def test_live_qualified_item_scores_as_restated():
    """反直觉但必须成立：被判合格的那条在复述口径上必须显著不为 0。

    这条判据的全部意义在于"指标能看见旧指标看不见的东西"。旧 repeat_rate 对
    这份现网样本读 0.0（夹具里带着当时的读数），所以新口径必须读出复述。
    """
    sets = [set(x) for x in FIX["number_sets"]]
    r = D.restatement_from_sets(sets)
    assert r["rate"] >= 0.30, "现网这条 6/9 段在复述同一批数据，指标却读 %s" % r
    assert r["paras"] == len(sets), "段数对不上：说明分段口径和实测时不是一套"
    assert FIX["repeat_rate_field_shipped"] == 0.0, \
        "夹具前提变了：旧字段不再是'看不见复述'的证据，这条判据要重写理由"


def test_restatement_metric_can_say_clean():
    """每段数字互不相同的长文必须读 0：否则这个指标只是"长文就打分"。"""
    sets = [{"1.%d" % i, "%d%%" % (10 + i), "%d.3" % i} for i in range(11)]
    assert D.restatement_from_sets(sets)["rate"] == 0.0
    # 只有两段、且共享 1 个数值，也不该报复述（避免把正常承接当水分）
    assert D.restatement_from_sets([{"40%", "5.5"}, {"40%", "6.1"}])["rate"] == 0.0


def test_restatement_metric_still_catches_copy_paste():
    """新口径不许把旧口径的活儿丢了：整段照抄必须照样被抓到。"""
    p = {"66.4%", "57.9%", "5.98", "3.26"}
    r = D.restatement_from_sets([p, set(p), set(p), {"9%", "8", "7"}])
    assert r["rate"] > 0.30 and r["pairs"] >= 1, r


def test_rate_is_derived_from_paragraph_pairs_not_a_constant():
    """复述率的分母必须是段数，且段数不足时不许瞎报。"""
    assert D.restatement_from_sets([{"1", "2"}])["rate"] == 0.0
    assert D.restatement_from_sets([])["rate"] == 0.0
    half = [{"40%", "5.98", "66.4%", "3.26"} for _ in range(4)]
    tail = [{"7%"}, {"9%"}, {"11%"}, {"13%"}]
    r = D.restatement_from_sets(half + tail)
    assert 0.4 <= r["rate"] <= 0.6, "4/8 段互抄应当读到 0.5 附近，实为 %s" % r


# ---------- 修复A：覆盖要求从"自引数"上解绑 ----------

def test_long_item_must_cite_more_distinct_sources():
    """9,000 字只引 5 篇必须判不合格 —— 现网 evt_011 的形状就是这样被放行的。"""
    ev = _cand(9000, n_cites=5)
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert not ok, "5 篇支撑 9,000 字仍是合格：钳制的 min() 还在"
    assert any("篇" in f and ("不同来源" in f or "不同证据" in f) for f in fails), fails


def test_coverage_requirement_does_not_shrink_to_self_chosen_cites():
    """要求按字数派生，不许因为模型只引了 5 篇就把要求降到 5。"""
    assert D.required_sources(9000) == 6, D.required_sources(9000)
    assert D.required_sources(9857) == 7
    assert D.required_sources(4000) == 3


def test_long_item_with_enough_sources_still_passes():
    """反向控制：判据不是"长度即有罪"，引够 8 篇的 9,000 字必须过。"""
    ev = _cand(9000, n_cites=8)
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert ok, fails


def test_cite_min_still_binds_short_items():
    """下限侧不许新增负担：4,200 字要求 3 篇，但 CITE_MIN=5 本来就更高。"""
    assert D.required_sources(4200) <= D.CITE_MIN
    ev = _cand(4200, n_cites=5)
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert ok, fails


def test_per_source_quality_map_is_absorbed_not_burned():
    """第 37 场现网 `evt_20260925_r14`：模型把 quality 写成了**逐信源的表**
    （`{"c1": {verdict,score,why,basis}, "c2": …}` 共 12 家），于是四条硬判据同时违约
    （verdict None / score None / why 0 字 / basis 为空），一条写了 8,872 字的正文直接烧掉。
    吸收规则要可辩护：**取最差那一档**（证据链的质量不高于最差的那篇），
    basis 收齐它引用过的所有外证编号，折叠几块必须留痕。
    夹具三块照抄现网那张表的档位与分值（通稿 85 / 深度 62 / 一手 100），
    c1 的 why 用现网原文（`count_chars` 实测 24 字，过 WHY_MIN=20 那条线 —— 端上没写完的那格照样会烧）。
    """
    cand = {"quality": {
        "c1": {"verdict": "通稿", "score": 85, "why": "短新闻摘要，多次搬运，缺乏原始数据，但信息准确。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "深度", "score": 62, "why": "解读研究，但侧重信息整理，口径未覆盖原始数据。",
               "basis": ["sig:c2"]},
        "c3": {"verdict": "一手", "score": 100, "why": "直接来自官方发布，信息权威。", "basis": ["sig:c3"]}}}
    D.repair_quality_fields(cand)
    q = cand["quality"]
    # 取的是**最差那一档**（通稿 比 深度 差），不是模型自报数字最低的那一块：
    # 现网这张表里 通稿 拿到 85 分、深度 只有 62 分，按分值挑会把整条判得比最差环节还好。
    assert q["verdict"] == "通稿", \
        "吸收按自报分值挑了（%s）：证据链的质量不许高于它最差的那篇来源" % (q,)
    assert q["score"] == 85, \
        "分值不是这一块自己报的数（verdict 与 score 被拼成一对了）：%s" % q
    assert D.WHY_MIN <= D.count_chars(q["why"]) <= D.WHY_MAX, q
    assert sorted(q["basis"]) == ["sig:c1", "sig:c2", "sig:c3"], q
    assert q["absorbed_from"] == 3, "折叠了几块没留痕，读的人无法核对：%s" % q
    ok, fails = D.validate_event({"title": "t", "topic": "ai", "narrative": "论证。" * 900,
                                  "claims": [], "causal_chains": [], "forecasts": [],
                                  "citations": [], "quality": q}, valid_ids=None)
    assert not [f for f in fails if "quality" in f], fails
    # 形状本来对的（单个对象）不许被动过
    plain = {"quality": {"verdict": "深度", "score": 70, "why": "依" * 30, "basis": ["sig:c1"]}}
    D.repair_quality_fields(plain)
    assert plain["quality"].get("absorbed_from") is None, plain["quality"]
    # 逐源表里混进非法 verdict 时，不许把非法值当结果端上来
    mixed = {"quality": {"c1": {"verdict": "未知类型", "score": 40, "why": "依" * 30,
                                 "basis": ["sig:c1"]},
                          "c2": {"verdict": "深度", "score": 70, "why": "依" * 30,
                                 "basis": ["sig:c2"]}}}
    D.repair_quality_fields(mixed)
    assert mixed["quality"]["verdict"] in D.QUALITY_VERDICTS, mixed["quality"]
    # 非法那一块不许被"翻译"成任何一个合法档位再算进账：没读懂就是没参与
    assert mixed["quality"].get("absorbed_from") == 1, \
        "折叠数把读不懂的块也算进去了（那是替模型编了一次判断）：%s" % mixed["quality"]


def test_absorption_picks_the_worst_tier_not_the_lowest_score():
    """模型自报的分值不可用来排序：现网那张表里 通稿=85 分、深度=62 分。

    按分值挑最"弱"会挑出 深度 —— 于是整条被贴上一个比它最差那篇来源**更好**的标签，
    而这条判据的全部意义就是"证据链的质量不高于最差那一环"（审查 P1-3 的实证版）。
    三格必须同源：分值取**那一档自己**报的数，不跨档借（审查第二轮 P1-1）。
    """
    cand = {"quality": {
        "c1": {"verdict": "营销", "score": 95, "why": "全文围绕产品卖点展开，无第三方口径。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "一手", "score": 40, "why": "官方原话但信息量薄。", "basis": ["sig:c2"]}}}
    q = D._absorb_per_source_quality(cand["quality"])
    assert q["verdict"] == "营销", q
    assert q["score"] == 95, \
        "分值被另一档那块的 40 分拼走了（verdict/score 必须同源）：%s" % q
    assert sorted(q["basis"]) == ["sig:c1", "sig:c2"], q


def test_compound_verdicts_in_per_source_blocks_are_normalized_first():
    """逐源表里的复合 verdict（`"转载/通稿"`）不许把整块挤出局（审查 P1-2）。

    上一版 `legal` 只收逐字合法的块：一个斜杠就让那一块不参与，
    最弱那一环因此被漏掉；而 `repair_quality_verdict` 在平铺形状上是会拆的 —— 两处口径分叉。
    归一必须留痕（`verdict_repaired`），否则读产物的人看不出这个标签是拆出来的。
    """
    cand = {"quality": {
        "c1": {"verdict": "一手/数据支撑", "score": 90, "why": "官方发布并给出可核验数据。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "转载/通稿", "score": 55, "why": "整篇转自律媒，未见原始口径。",
               "basis": ["sig:c2"]}}}
    q = D._absorb_per_source_quality(cand["quality"])
    assert q["verdict"] == "转载", \
        "复合 verdict 那一块被挤出局了（挑出来的是 %s）：%s" % (q.get("verdict"), q)
    assert q.get("verdict_repaired") == "转载/通稿", q
    assert q["absorbed_from"] == 2, "被归一的块不许少算：%s" % q


def test_the_shipped_triple_is_one_real_block_not_a_spliced_pair():
    """verdict / score / why 必须来自同一块：不许拼出没来源断言过的配对（审查 P1-1）。

    场 37 的 `evt_20260925_r14` 实测：按"跨表取最低分"那版实现会把
    `verdict=通稿`（两块通稿自己报 85 与 65）配上 `score=62`（那是另一档 深度 那块的分数），
    页面上印出来就是"优质判定 通稿 62" —— 没有任何一篇来源这么断言过，
    而且比该档真实最低分还低。上一条判据断的是这个配对本身。
    """
    blocks = {
        "c1": {"verdict": "通稿", "score": 85, "why": "短新闻摘要，多次搬运，缺乏原始数据，但信息准确。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "深度", "score": 62, "why": "解读研究，但侧重信息整理，口径未覆盖原始数据。",
               "basis": ["sig:c2"]},
        "c3": {"verdict": "一手", "score": 100, "why": "直接来自官方发布，信息权威。", "basis": ["sig:c3"]}}
    q = D._absorb_per_source_quality(blocks)
    pairs = [(v["verdict"], v["score"], v["why"]) for v in blocks.values()]
    assert (q["verdict"], q["score"], q["why"]) in pairs, \
        "端上来的三元组没有任何一块来源断言过（那是拼出来的）：%s" % (q,)
    assert q["verdict"] == "通稿" and q["score"] == 85, \
        "该档只有这一块，它自己报 85：配成别的数就是拼的：%s" % (q,)


def test_within_one_tier_it_takes_the_lowest_scored_usable_block():
    """同档两块都写得完 why 时，取该档**分值最低**的那一块（既不是"最长 why"也不是字典序第一块）。

    这条与下一条分钉两个不同的退让：这条钉"同档取最低分"，下一条钉"最低分那块的 why
    写不完时才换块"。上一版夹具把两件事混在一起（最长那块恰好也是最低分那块），
    两条规则给出同一个答案 ⇒ 删掉任一项都不红（审查 P1-2：夹具没鉴别力）。
    """
    blocks = {
        "c1": {"verdict": "通稿", "score": 85, "why": "短新闻摘要，多次搬运，缺乏原始数据，但信息准确。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "通稿", "score": 65, "why": "日报式汇总，段落之间未见独立采访问证与后续跟进。",
               "basis": ["sig:c2"]},
        "c3": {"verdict": "一手", "score": 100, "why": "官方发布会实录。", "basis": ["sig:c3"]}}
    q = D._absorb_per_source_quality(blocks)
    assert (q["verdict"], q["score"]) == ("通稿", 65), q
    assert q["why"] == blocks["c2"]["why"], "why 没跟着分值走（拼配对的回归）：%s" % (q,)


def test_within_one_tier_a_block_with_an_unusable_why_is_not_taken():
    """最低分那一块若 why 短到不合格 ⇒ 退回同档写得完的那一块，而不是把整条再烧一次。

    这与上一条是两条不同的判据：上一条钉"配对不许拼"，这条钉"退让只在写不完时发生"。
    夹具刻意让**分值高**的那一块才是写得完的：两条规则（纯取最低分 / 只看 why 最长）
    在这里给出的答案不同，删掉任一项都会红（上一版夹具两条规则给同一个答案，测不到东西）。
    """
    blocks = {
        "c1": {"verdict": "通稿", "score": 90,
               "why": "整篇通稿口径，段落顺序与措辞与官方发布一致，未见独立采访问证。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "通稿", "score": 60, "why": "短。", "basis": ["sig:c2"]}}
    q = D._absorb_per_source_quality(blocks)
    assert D.count_chars(q["why"]) >= D.WHY_MIN, \
        "端上来的是那格没写完的 why（%d 字）：%s" % (D.count_chars(q["why"]), q)
    assert (q["verdict"], q["score"]) == ("通稿", 90), \
        "退让没发生（分值仍来自那格写不完的块）：%s" % (q,)


def test_an_out_of_range_score_does_not_take_the_item_down_with_it():
    """同档里"最低分"那颗自己越界（-5 / 150）时，取同档**在 0-100 之内**的最低那颗。

    批 3.13 第一轮把"跨表借分"禁了（对的），但顺手把唯一的救援也禁了：
    `min(按分值)` 会先挑中越界那颗 ⇒ `quality.score 必须在 0-100` 判死 ⇒ 整条还是烧。
    这仍然不是替模型编数：75 是 c2 自己报的，越界的 -5 也不是任何一篇的合格读数。
    """
    blocks = {
        "c1": {"verdict": "通稿", "score": -5, "why": "整篇照抄同一份发稿通，措辞与官方发布完全一致。",
               "basis": ["sig:c1"]},
        "c2": {"verdict": "通稿", "score": 75, "why": "转自律媒的同一篇通稿，未做独立问询与核验。",
               "basis": ["sig:c2"]},
        "c3": {"verdict": "一手", "score": 95, "why": "官方发布会实录。", "basis": ["sig:c3"]}}
    q = D._absorb_per_source_quality(blocks)
    assert (q["verdict"], q["score"]) == ("通稿", 75), \
        "越界那颗被当成'该档最低分'端上来了：整条会死在 score 判据上：%s" % (q,)
    assert q["why"] == blocks["c2"]["why"], "三格又不同源了：%s" % (q,)


def test_a_tier_whose_why_is_never_written_still_reports_the_worst_tier():
    """该档两块都写不完 why ⇒ 照实交最低分那块（判死是应该的），但档位不许偷偷变好。"""
    blocks = {
        "c1": {"verdict": "营销", "score": 40, "why": "短。", "basis": ["sig:c1"]},
        "c2": {"verdict": "一手", "score": 90, "why": "官方发布。", "basis": ["sig:c2"]},
        "c3": {"verdict": "一手", "score": 95, "why": "官方发布。", "basis": ["sig:c3"]}}
    q = D._absorb_per_source_quality(blocks)
    assert q["verdict"] == "营销", "该档没人写得完 why 就换档：那是往好处挑：%s" % (q,)
    assert q["score"] == 40 and D.count_chars(q["why"]) < D.WHY_MIN, q


def test_an_illegal_verdict_or_bool_score_never_reaches_the_page():
    """场 39 现网出厂过 "优质判定 深度报道 82"，而那条自己的 contract_fails 就写着不在枚举。

    判据对降级条目不查 quality 这一组（正文已裁成快讯，长度类判据会全响），
    于是模型自造的分类一路走到页面 —— 这既是"上屏的枚举"红线，也是页面替我们撒了谎。
    同一格的 `score: true` 也一路过关（bool 是 int 的子类），页面会印 "True"。
    """
    def _page(quality):
        ev = {"id": "x", "title": "某事件", "topic": "ai", "narrative": "快讯正文。",
              "degraded_reason": "重写 2 次仍不合格", "quality": quality, "claims": [],
              "causal_chains": [], "forecasts": [], "citations": [],
              "rubric": {"mean": 0.6, "judged": True}}
        return D.render_page({"date": "2026-09-25", "events": [ev], "budget": {},
                              "anchor_diff": []}), ev

    html_bad, ev_bad = _page({"verdict": "深度报道", "score": 82, "why": "依" * 25,
                              "basis": ["sig:c1"]})
    assert "深度报道" not in html_bad, "模型自造的分类直接上屏了"
    assert u"优质判定" not in html_bad, "没有合法取值时宁可整段不印"
    html_bool, ev_bool = _page({"verdict": "通稿", "score": True, "why": "依" * 25,
                                "basis": ["sig:c1"]})
    assert "True" not in html_bool, "bool 当成了分值印上屏"
    # 判据对降级条目不查 quality 这一组（那是上一条泄漏存在的原因），所以要拿**非降级**的形状验 bool 判据
    probe = {"title": "t", "topic": "ai", "narrative": "论证。" * 900, "claims": [],
             "causal_chains": [], "forecasts": [], "citations": [],
             "quality": {"verdict": "通稿", "score": True, "why": "依" * 25, "basis": ["sig:c1"]}}
    ok, fails = D.validate_event(probe)
    assert any(u"0-100" in f for f in fails), \
        "score: true 仍被判据接受（bool 是 int 的子类）：%s" % (fails,)
    html_ok, _ev_ok = _page({"verdict": "通稿", "score": 65, "why": "依" * 25,
                             "basis": ["sig:c1"]})
    assert "通稿 65" in html_ok, "合法配对被一起挡掉了：%s" % html_ok[-300:]


def test_prompts_state_the_derived_coverage_rule():
    """契约里写的篇数必须和判据用的是同一个派生，不许多套一份数字。"""
    p = D._structure_rules(", ".join(sorted(VALID)), len(VALID))
    assert ("每 %d 字换一篇" % D.EVID_CHARS) in p, p[:400]
    assert ("写到 %d 字就要引到 %d 篇" % (
        D.NARR_MAX, min(len(VALID), D.required_sources(D.NARR_MAX))) in p), \
        "prompt 没把'长文要多引'讲清，模型只会照 CITE_MIN 交 5 篇"


# ---------- 修复C：枚举复合值修好，不烧整条 ----------

def test_compound_quality_verdict_is_repaired():
    """现网 evt_008 的形状：两个合法值中间一个斜杠，不是内容问题。"""
    ev = _cand(9000, n_cites=8, verdict="一手/数据支撑")
    D.repair_quality_verdict(ev)
    assert ev["quality"]["verdict"] in D.QUALITY_VERDICTS, ev["quality"]
    assert ev["quality"]["verdict_repaired"] == "一手/数据支撑", "改判必须留痕"
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert ok, fails


def test_illegal_quality_verdict_stays_illegal():
    """ repairs 不许变成橡皮章：拆出来没有一个是合法值就照判不合格。"""
    ev = _cand(9000, n_cites=8, verdict="优质/原创")
    D.repair_quality_verdict(ev)
    assert ev["quality"]["verdict"] not in D.QUALITY_VERDICTS
    assert "verdict_repaired" not in ev["quality"]
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert not ok and any("verdict" in f for f in fails), fails


# ---------- 修复B：量出来的东西必须进 judge 的眼 ----------

def test_judge_prompt_carries_measured_restatement():
    """观测不接进评审就是装饰：judge 得看到"哪几个数被几段复述"。"""
    sets = FIX["number_sets"]
    cand = _cand(9000, n_cites=8)
    cand["narrative"] = _restated_text(sets)
    jp = D.build_judge_prompt(cand, {"articles": [{"text": "证据正文" * 50}], "ids": {}})
    assert "复述" in jp, "judge 仍然只凭感觉打 density"
    # 渲染出来的是"复述率: 0.636"，冒号在数字前面 —— 正则按数字后跟冒号写过一次，
    # 于是判据恒红，红得像是"没接线"，其实是断言本身写反。
    m = re.search(r"复述率[:：]\s*([\d.]+)", jp)
    assert m, jp[:600]
    assert float(m.group(1)) >= 0.30, jp[:600]


def test_restated_artifact_field_reaches_events_on_all_paths():
    """降级早退路径也要写这一格，否则产物里有的有有的没有。"""
    cand = _cand(9000, n_cites=8)
    assert "restate_rate" in D.annotate_observability(cand)
    short = D.clip_for_degrade(dict(cand))
    assert "restate_rate" in D.annotate_observability(short)


# ---------- 修复D：提纲不许两段抢同一篇主证据 ----------

def test_cite_floor_follows_supply_not_a_fixed_number_we_cannot_meet():
    """`CITE_MIN=5` 是硬下限，但池子只有 4 篇时它**满足不了**。

    现网跑出来的形状：`citations 4 条，须在 [5,12]` —— 扎实的小池子条目被一条
    给不出的要求判死，和刚拆掉的自愿钳制是同族缺陷。下限按供给收敛，
    供给充足时（≥5 篇）仍按 CITE_MIN 拦。
    """
    four = {"c%d" % (i + 1) for i in range(4)}
    ev = _cand(4200, n_cites=4)
    ok, fails = D.validate_event(ev, valid_ids=four, valid_basis={"sig:c1"})
    assert ok, "池子只有 4 篇、它已全引仍判死：%r" % (fails,)

    six = {"c%d" % (i + 1) for i in range(6)}
    ev2 = _cand(4200, n_cites=4)
    ok2, fails2 = D.validate_event(ev2, valid_ids=six, valid_basis={"sig:c1"})
    assert not ok2 and any("citations 4 条" in f for f in fails2), \
        "供给有 6 篇却只引 4 篇仍放行：下限被供给付了钱"


def test_supply_clamp_is_our_responsibility_not_its_escape_hatch():
    """上界按"我们供给了几篇来源"收敛，这条边界必须两头都钉住。

    旧钳制 `min(len(cited_ids), …)` 坏在它按"模型自愿引了几篇"收敛 —— 少引就连要求一起少。
    换成按供给收敛之后，如果不测反方向，它一样会变成自我放水的手柄。
    """
    six = {"c%d" % (i + 1) for i in range(6)}
    full = _cand(9000, n_cites=6)
    ok, fails = D.validate_event(full, valid_ids=six, valid_basis={"sig:c1"})
    assert ok, "池子只有 6 篇、它已引满 6 篇仍判不合格：这是我们的供给不足，不是它的错：%r" % (fails,)
    assert full.get("sources_short"), "供给少于派生要求却没记账，批 4 定档就没有依据"

    lazy = _cand(9000, n_cites=6)
    lazy["citations"] = lazy["citations"][:3]
    lazy["claims"] = [{"text": "论断%d" % i, "kind": "causal",
                       "evidence": ["c%d" % (i % 3 + 1)]} for i in range(8)]
    ok2, fails2 = D.validate_event(lazy, valid_ids=six, valid_basis={"sig:c1"})
    assert not ok2 and any("只引了 3 篇" in f for f in fails2), \
        "供给 6 篇只引 3 篇仍放行：上界又变回自愿钳制了"


def test_each_section_gets_its_own_evidence_not_the_same_first_three():
    """逐段成文必须各拿自己那份证据。

    现网成因不是模型偷懒：`ctx["ids"]` 是 {"c1": url}，而 build_section_prompt 按
    `for u, cid in ids.items()` 反着解包 ⇒ 每段查不到自己的证据 ⇒ 全部走兜底拿同样
    的前 3 篇。8 段共 3 源，写出来当然换句话复述，而产物里只看得见 restate_rate 高。
    """
    ctx = _ctx_like(6)
    a = {"title": "A", "focus": "f", "primary": "c1", "evidence": ["c1"]}
    b = {"title": "B", "focus": "f", "primary": "c2", "evidence": ["c2"]}
    pa = D.build_section_prompt({"title": "甲", "topic": "ai"}, ctx, a, 1, 2)
    pb = D.build_section_prompt({"title": "甲", "topic": "ai"}, ctx, b, 2, 2)
    t = [x["text"][:24] for x in ctx["articles"]]
    assert t[0] in pa and t[1] not in pa, "第一段没拿到自己的证据：%s" % pa[:200]
    assert t[1] in pb and t[0] not in pb, "第二段拿到了第一段的证据：%s" % pb[:200]
    assert a.get("_evidence_fallback") is None and b.get("_evidence_fallback") is None, \
        "查得到却仍走兜底：兜底把这类缺陷藏成'看起来正常'"


def _ctx_like(n):
    arts = [{"url": "https://k.test/%d" % i, "source": "s%d" % i, "title": "T%d" % i,
             "text": "独立来源%d的全文内容。" % i * 300, "has_full": True,
             "source_key": "s%d_%d" % (i, i)} for i in range(n)]
    return {"articles": arts,
            "ids": {"c%d" % (i + 1): a["url"] for i, a in enumerate(arts)},
            "signals": {}}


def test_fallback_is_counted_when_a_section_cites_nothing_resolvable():
    """兜底本身可以保留（无证据的段总比空段好），但必须记账 —— 无声兜底就是这次的病根。"""
    ctx = _ctx_like(4)
    sec = {"title": "X", "focus": "f", "evidence": ["c99"]}
    p = D.build_section_prompt({"title": "甲", "topic": "ai"}, ctx, sec, 1, 1)
    assert p.strip(), "兜底后什么都没有，这条判据就是空转"
    assert sec.get("_evidence_fallback") is True, "走了兜底却没留痕"


def test_outline_asks_for_distinct_primary_evidence():
    ev = {"title": "事件甲", "topic": "ai"}
    ctx = {"articles": [{"url": "https://a.test/%d" % i, "source": "s", "title": "t",
                         "text": "正文" * 400} for i in range(12)],
           "ids": {"c%d" % (i + 1): "https://a.test/%d" % i for i in range(12)},
           "signals": {}}
    op = D.build_prompt(ev, ctx, "outline")
    # 契约的字段清单本身要点名 primary：只断言"文里出现过这个词"是关键词判据，
    # 把字段从清单里删掉、别处再提一句就照样绿（变异体 N12 就是这么存活的）。
    assert "title/focus/primary/evidence" in op, op[:600]
    assert "不得重复" in op, op[:600]


def test_outline_section_cap_follows_available_sources():
    """只有 4 篇可用证据时不许排 6 段各要一个主证据 —— 那必然复述。"""
    assert D.outline_section_cap(12) == D.SECTIONS_MAX
    assert D.outline_section_cap(4) == 4
    assert D.outline_section_cap(0) == 0


def test_outline_rejects_duplicate_primaries():
    secs = [{"title": "A", "focus": "f", "primary": "c1", "evidence": ["c1"]},
            {"title": "B", "focus": "f", "primary": "c1", "evidence": ["c1"]}]
    assert D.outline_rejects(secs), "两段抢同一篇主证据必须被拒，而不是照样开写"
    ok = [{"title": "A", "focus": "f", "primary": "c1", "evidence": ["c1"]},
          {"title": "B", "focus": "f", "primary": "c2", "evidence": ["c2"]}]
    assert D.outline_rejects(ok) is None


def test_colliding_primaries_get_one_named_reask_not_a_fallback():
    """提纲主证据撞车 ⇒ 点名重问一次；不许整条退回单趟。

    退回单趟是把两段式废掉（现网证据：单趟的长度方差 2645/1618/685/363 字就是
    两段式要治的那个故障）。新字段没写对不该换来旧故障回归。
    """
    kinds = []

    class Cli(object):
        def complete(self, prompt, key=None, kind="generate"):
            kinds.append(kind)
            if kind == "outline":
                dup = "c1" if len([k for k in kinds if k == "outline"]) == 1 else None
                return json.dumps({"sections": [
                    {"title": "A%d" % i, "focus": "f",
                     "primary": dup or ("c%d" % (i + 1)),
                     "evidence": [dup or ("c%d" % (i + 1))]} for i in range(6)]})
            if kind == "structure":
                return json.dumps({})
            return "论证与数据推演" + "证据之间可核对，需结合口径差异来看。" * 30

    ctx = {"articles": [{"url": "https://a.test/%d" % i, "source": "s", "title": "t",
                         "text": "正文" * 400} for i in range(8)],
           "ids": {"c%d" % (i + 1): "https://a.test/%d" % i for i in range(8)},
           "signals": {}}
    out, note = D.staged_generate({"title": "甲", "topic": "ai"}, ctx, Cli(),
                                  D.KeyPool(["k"]), D.Budget(400000))
    assert out is not None, "撞车就退回单趟了：两段式被一个新字段废掉：%s" % (note,)
    assert kinds.count("outline") == 2, kinds
    assert note.get("primary_retried") is True, note
    assert "primary_collisions" not in note, "第二次已经改对了还记着冲突：%s" % note
    assert "正文" in "".join([k for k in kinds if k == "section"]) or kinds.count("section") >= 6, kinds


def test_still_colliding_outline_continues_and_says_so():
    """重问后仍然撞车：带着账继续写，而不是静默或彻底没有产物。"""
    kinds = []

    class Cli(object):
        def complete(self, prompt, key=None, kind="generate"):
            kinds.append(kind)
            if kind == "outline":
                return json.dumps({"sections": [
                    {"title": "A%d" % i, "focus": "f", "primary": "c1",
                     "evidence": ["c1"]} for i in range(6)]})
            if kind == "structure":
                return json.dumps({})
            return "论证与数据推演" + "证据之间可核对，需结合口径差异来看。" * 30

    ctx = {"articles": [{"url": "https://a.test/%d" % i, "source": "s", "title": "t",
                         "text": "正文" * 400} for i in range(8)],
           "ids": {"c%d" % (i + 1): "https://a.test/%d" % i for i in range(8)},
           "signals": {}}
    out, note = D.staged_generate({"title": "甲", "topic": "ai"}, ctx, Cli(),
                                  D.KeyPool(["k"]), D.Budget(400000))
    assert out is not None, note
    assert note.get("primary_collisions"), "还是撞车却没记账：读产物的人无从知道结构坏了"


def test_outline_cap_never_drops_below_the_minimum_section_count():
    """封顶不许制造一条满足不了的要求。

    池子只有 4 篇时把提纲削到 4 段，下一条"段数 < PARAS_MIN(6)"必然命中，
    等于任何小池子的条目都直接失去两段式 —— 这正是本批要拆掉的那类钳制。
    """
    assert D.outline_section_cap(4) == 4          # 纯谓词照旧可测
    kinds = []

    class Cli(object):
        def complete(self, prompt, key=None, kind="generate"):
            kinds.append(kind)
            if kind == "outline":
                return json.dumps({"sections": [
                    {"title": "A%d" % i, "focus": "f", "primary": "c%d" % ((i % 4) + 1),
                     "evidence": ["c%d" % ((i % 4) + 1)]} for i in range(6)]})
            if kind == "structure":
                return json.dumps({})
            return "论证与数据推演" + "证据之间可核对，需结合口径差异来看。" * 30

    ctx = {"articles": [{"url": "https://a.test/%d" % i, "source": "s", "title": "t",
                         "text": "正文" * 400} for i in range(4)],
           "ids": {"c%d" % (i + 1): "https://a.test/%d" % i for i in range(4)},
           "signals": {}}
    out, note = D.staged_generate({"title": "甲", "topic": "ai"}, ctx, Cli(),
                                  D.KeyPool(["k"]), D.Budget(400000))
    assert out is not None, "4 篇池子就被封顶打回单趟了：%s" % (note,)
    assert kinds.count("section") >= D.PARAS_MIN, kinds


def test_overlong_quality_why_is_trimmed_not_fatal():
    """09-24 现网 evt_20260924_001：8 引用 / 4 因果链齐全，死因只有
    `quality.why 170 字，须在 [20,120]`。与 verdict 斜杠同族：形状缺陷烧整条，
    而烧掉的代价是重写两轮的约 20 次调用。归一（裁到上界并留原长）才对得起代价。"""
    ev = _cand(9000, n_cites=8)
    ev["quality"]["why"] = "依" * 170
    D.repair_quality_fields(ev)
    assert D.count_chars(ev["quality"]["why"]) <= D.WHY_MAX
    assert ev["quality"]["why_chars_full"] == 170, "裁了却不留原长 = 下一轮还是读不出来"
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert ok, fails


def test_underlength_quality_why_stays_fatal():
    """归一只许往回收，不许往回填：太短的 why 是模型真没写理由，补字就是造假证据。"""
    ev = _cand(9000, n_cites=8)
    ev["quality"]["why"] = "依" * 5
    D.repair_quality_fields(ev)
    ok, fails = D.validate_event(ev, valid_ids=VALID)
    assert not ok and any("quality.why" in f for f in fails), fails


# ---------- helper ----------

def _restated_text(sets):
    """把现网实测的每段数值签名铺回文本形状（不抄正文，只复现复述形状）。"""
    ps = []
    for s in sets:
        ps.append("数据显示" + "、".join(x + "%" if not x.endswith("%") else x for x in s)
                  + "，该判断仍受样本量与统计口径限制。")
    return "\n\n".join(ps)
