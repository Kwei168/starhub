# -*- coding: utf-8 -*-
"""方案一：逐条长度预算 4,000–10,000 字，反水分的活儿从"字数盖帽"换到可核对的判据上。

来历：4,000 这个上限到目前为止只造成过损失 —— 现网单趟写出过 6,950 / 4,338 字两条，
都因"超上限"被我们自己判死；最近一场两段式 8 段里丢掉 2 段（token 全付了）。
而证据侧实测每条 12 篇全文、汉字量 9.4k~855k，长度根本不受证据约束。
上限抬到 1 万之后，"长而空"必须换人守：
  · agent 主判：judge 增加"信息密度/不重复"维度，且真的进均值（不是装饰）；
  · 结构判据：正文越长，claims 必须覆盖越多篇不同证据（按字数派生，不拍阈值）；
  · 机械重复率只记不门：手上没有任何 4k 字以上的真样本，造一个阈值就是把猜测当判据。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _para(target, marker="但该判断仍受样本量与统计口径限制。"):
    """按 count_chars 造一段够长的正文：不猜计数口径，直接量到够为止。"""
    body = "论证与数据推演"
    i = 0
    while D.count_chars(body + marker) < target:
        i += 1
        body += "证据%d显示投入与产出之间存在可核对的落差，需要结合口径差异来看。" % i
    return body + marker


def _narrative(total_target, paras=8):
    per = total_target // paras + 10
    return "\n\n".join(_para(per) for _ in range(paras))


def _cand(chars=9000, claim_ids=("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8")):
    nar = _narrative(chars)
    claims = [{"text": "论断%d" % i, "kind": "causal",
               "evidence": [claim_ids[i % len(claim_ids)]]} for i in range(8)]
    return {
        "id": "e1", "title": "事件甲", "topic": "ai", "narrative": nar,
        "claims": claims,
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": 0.6, "evidence": ["c1"]} for _ in range(3)],
        "forecasts": [{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类竞品发布数>=3"}],
        "quality": {"verdict": "一手", "score": 82, "why": "依" * 60, "basis": ["sig:c1"]},
        "citations": [{"id": "c%d" % (i + 1),
                       "url": "https://s%d.test/a%d" % (i, i)} for i in range(8)],
    }


VALID = {"c%d" % (i + 1) for i in range(12)}


def test_item_budget_is_four_to_ten_thousand():
    """预算换档必须能在常量与两处文案上同时看到 —— 只改常量就是"改了数没改话"。"""
    assert (D.NARR_MIN, D.NARR_MAX) == (4000, 10000), (D.NARR_MIN, D.NARR_MAX)
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": []}
    arts = [{"url": "https://s0.test/a0", "source": "s0", "title": "T0",
             "text": "证据正文" * 300, "has_full": True}]
    ctx = {"articles": arts, "ids": {"c1": arts[0]["url"]}, "signals": {}}
    gen = D.build_prompt(ev, ctx)
    assert "4000" in gen and "10000" in gen, "生成侧还在按旧区间要字数"
    jp = D.build_judge_prompt({"narrative": "x"}, ctx)
    assert "4000" in jp, "judge 仍按 2500 判，合格线与评审口径分叉"


def test_nine_thousand_chars_passes_the_contract():
    """9,000 字、8 段、段段够长 —— 现网它会被判 overlen，那是我们自己把内容丢掉的。"""
    ok, fails = D.validate_event(_cand(9000), valid_ids=VALID, valid_basis={"sig:c1"})
    assert ok, fails


def test_three_thousand_chars_is_no_longer_enough():
    """下限从 2,500 抬到 4,000：只抬上限等于把"写多少看模型心情"的老路重新打开
    —— A 方案存在的全部理由就是单趟稳定停在 1,748/2,307/1,902 字。"""
    ok, fails = D.validate_event(_cand(3000), valid_ids=VALID, valid_basis={"sig:c1"})
    assert not ok and any("4000" in f or "下限" in f for f in fails), fails


def test_longer_text_must_cite_more_evidence():
    """反水分第一道（结构判据）：9,000 字只压在 2 篇证据上，就是复述而不是分析。

    界按字数派生，不是拍的阈值 —— 每 1,500 字至少要换一篇证据支撑。
    """
    thin = _cand(9000, claim_ids=("c1", "c2"))
    ok, fails = D.validate_event(thin, valid_ids=VALID, valid_basis={"sig:c1"})
    assert not ok, "9,000 字只引用 2 篇证据却判合格"
    assert any("覆盖" in f or "证据" in f for f in fails), fails
    thick = _cand(9000, claim_ids=tuple("c%d" % (i + 1) for i in range(7)))
    assert D.validate_event(thick, valid_ids=VALID, valid_basis={"sig:c1"})[0]


def test_long_item_may_not_dilute_the_requirement_by_citing_fewer():
    """这条**推翻**原来的"覆盖要求封顶在已引篇数"。

    旧理由写在判据里："9,000 字配 5 篇证据本来可以是扎实的"。现网把它证伪了：
    evt_20260923_011 素材池 12 篇 / 635,321 字，只引 5 篇写 9,857 字，
    段落复述实测 0.636 —— 那 5 篇不"扎实"，它们被摊到每篇 ~2,000 字，只能反复消费。
    所以 `min(已引篇数, 字数/1500)` 里的 min 必须拆掉：要求按字数派生，
    引不够就是不合格，而不是把要求降到它引够为止。
    """
    ev = _cand(9000)
    ev["citations"] = ev["citations"][:5]
    ev["claims"] = [{"text": "论断%d" % i, "kind": "causal",
                     "evidence": ["c%d" % (i + 1)]} for i in range(5)]
    ok, fails = D.validate_event(ev, valid_ids=VALID, valid_basis={"sig:c1"})
    assert not ok, "5 篇撑 9,000 字仍判合格：钳制还在，长文就还能靠复述凑"
    assert any("只引了 5 篇" in f for f in fails), fails
    # 反向控制：引够就不许再拿这条拦人
    ev2 = _cand(9000)
    ok2, fails2 = D.validate_event(ev2, valid_ids=VALID, valid_basis={"sig:c1"})
    assert ok2, fails2


def test_judge_density_dimension_really_counts():
    """反水分第二道（agent 主判）：density 走单维否决，不进均值。

    为什么不让它进均值：五维平均会把有效合格线从 0.75 挪到 0.6875 ——
    judge 只要在 density 上慷慨，四维 0.7125 的东西就放行了，方向和"反水分"相反
    （对抗审查 P1-3 的矩阵复现）。所以均值只看四维实质分，density 单独否决。
    地板按实测复评噪声（极差 0.17）定在 0.5，0.62 这种"差一点点"不许被拦。
    """
    jp = D.build_judge_prompt(_cand(9000), {"articles": [], "ids": {}, "signals": {}})
    assert "密度" in jp or "重复" in jp, "judge 没有反水分这一维"
    thin = D.rubric_of({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                        "quality": 0.9, "density": 0.2})
    assert "density" in thin, thin
    assert thin["mean"] == 0.9, "均值不许被 density 摊薄：%s" % thin["mean"]
    assert D.judge_accepts(thin) is False, "密度 0.2 仍被放行：这一维是装饰"
    ok = D.rubric_of({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                      "quality": 0.9, "density": 0.62})
    assert D.judge_accepts(ok) is True, "0.62 也被拦：地板压进复评噪声带里了"


def test_restate_rate_is_recorded_but_still_not_a_hard_gate():
    """观测口径换到"段落复述"，但**仍不当硬门** —— 理由换了，结论没换。

    旧理由"手上没有 4k 字以上真样本"已经不成立：现网两条合格长文实测 0.636 与 0.46。
    现在拦它的理由是 n=2 不足以定阈值。旧的句级 `repetition_rate` 对这两条都读 0.0，
    字段已退役，别再往回加。
    """
    cand = _cand(9000)
    m = D.restatement_rate(cand["narrative"])
    assert isinstance(m["rate"], float) and 0.0 <= m["rate"] <= 1.0, m
    assert "repetition_rate" not in dir(D), "旧指标被悄悄加回来了：它对现网真样本恒读 0.0，是假数据"
    # 这套夹具本身就是 8 段同文，复述率必须读满 —— 读不满就是指标失灵
    assert m["rate"] == 1.0 and m["pairs"] >= 1, \
        "8 段完全相同的正文读到 %s：复述率失灵" % m
    varied = "\n\n".join("第%d组数据显示投入与产出落差为 %d%%，口径差异另计，但该判断仍受样本量限制。"
                         % (i, 10 + i * 7) for i in range(8))
    assert D.restatement_rate(varied)["rate"] == 0.0, "各段数据互不相同却报复述：这数不可用"


def _ctx(n=8):
    arts = [{"url": "https://s%d.test/a%d" % (i % 3, i), "source": "src%d" % i,
             "title": "T%d" % i, "text": "证据正文" * 400, "has_full": True}
            for i in range(n)]
    return {"articles": arts, "ids": {"c%d" % (i + 1): a["url"] for i, a in enumerate(arts)},
            "signals": {}}


def test_prompt_states_the_evidence_coverage_rule():
    """判据会判死条目，就必须先写进 prompt —— 否则那是隐性拒绝。

    现网 evt_20260923_r06：8,950 字压在 3 篇证据上被 EVID_CHARS 判死，
    而生成方从头到尾没被告知这条要求；补结构字段那一趟也必须带同一份契约。
    """
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": []}
    ctx = _ctx()
    for name, p in (("生成", D.build_prompt(ev, ctx)),
                    ("结构", D.build_structure_prompt(ev, ctx, "已成文正文"))):
        assert str(D.EVID_CHARS) in p, "%s那趟没写每多少字要换一篇证据" % name
        assert ("不同证据" in p) or ("不同篇" in p), "%s那趟写了数字但没说按篇数" % name


def test_quality_given_as_a_list_keeps_the_richest_variant():
    """现网 run 35816287694：模型把 quality 写成"每篇一个对象"的数组，归一直接清空。

    两条合格候选就是这么被打成不合格的。契约要单对象，那就取信息最全的那条，
    其余留一笔计数进产物 —— 静默丢弃是最坏的处理方式。
    """
    cand = {"quality": [
        {"verdict": "转载", "score": 40, "why": "短", "basis": ["sig:c1"]},
        {"verdict": "一手", "score": 82,
         "why": "正文本身像社交媒体信息源记录，贴近一手视角，未见于官方口径" * 2,
         "basis": ["sig:c1", "sig:c2"]},
    ]}
    out = D.normalize_candidate(cand, {}, None)
    q = out.get("quality")
    assert isinstance(q, dict) and q.get("verdict"), "数组形状仍被掏空：%r" % (q,)
    assert q["verdict"] == "一手", "没取信息最全的那条：%r" % q
    assert out.get("quality_variants") == 2, out


def test_truncation_is_attributed_to_a_kind():
    """只记"本场截断 1 次"修不了东西：要知道是哪一趟撞的 max_tokens。

    现网第一次出现 truncated=1 时，逐段/提纲/结构/判定四趟里到底是哪一趟
    撑破了输出上限，日志里查不出来 —— 而下一步动作（提 max_tokens 还是拆段）
    完全取决于这个答案。
    """
    b = D.Budget()
    b.note_truncated("structure")
    b.note_truncated("structure")
    b.note_truncated("outline")
    assert b.truncated == 3
    assert b.snapshot().get("truncated_by") == {"structure": 2, "outline": 1}, b.snapshot()


def test_degraded_item_still_records_how_long_it_actually_wrote():
    """降级把正文裁到 200 字之后，"本来写了多长"必须在产物里查得到。

    本轮为了回答"4000 是不是削掉了内容"，只能从 trimmed_sections 反推 —— 那是观测缺口。
    """
    cand = _cand(9000)
    cand["degraded_reason"] = "重写 2 次仍不合格"
    full = D.count_chars(cand["narrative"])
    out = D.clip_for_degrade(cand)
    assert out is cand, "就地裁剪可以，但别让人以为返回的是另一份"
    assert D.count_chars(out["narrative"]) <= D.DEGRADED_NARR_MAX, out
    assert out.get("narrative_chars_full") == full, out
    assert out["forecasts"] == [], "降级条目不许留预测"
