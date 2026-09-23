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


def test_coverage_requirement_is_capped_by_what_the_item_cited():
    """要它覆盖的篇数不许超过它自己引过的篇数。

    否则等于要求条目去引用自己没引的东西 —— 9,000 字配 5 篇证据本来可以是扎实的，
    却被一条派生不出来的要求判死。这一条界是"min(已引篇数, 字数/1500)"里的 min。
    """
    ev = _cand(9000)
    ev["citations"] = ev["citations"][:5]
    ev["claims"] = [{"text": "论断%d" % i, "kind": "causal",
                     "evidence": ["c%d" % (i + 1)]} for i in range(5)]
    ok, fails = D.validate_event(ev, valid_ids=VALID, valid_basis={"sig:c1"})
    assert ok, fails


def test_judge_density_dimension_really_counts():
    """反水分第二道（agent 主判）：密度必须进均值，而且单维塌陷要能否决。

    只看均值时，"密度 0.2 + 另外四维 0.9" 的均值是 0.76 —— 照样过线，
    那这一维就是装饰。地板按实测复评噪声（极差 0.17）定在 0.5，
    0.62 这种"差一点点"不许被拦，否则闸就在噪声上翻脸。
    """
    jp = D.build_judge_prompt(_cand(9000), {"articles": [], "ids": {}, "signals": {}})
    assert "密度" in jp or "重复" in jp, "judge 没有反水分这一维"
    thin = D.rubric_of({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                        "quality": 0.9, "density": 0.2})
    assert "density" in thin, thin
    assert thin["mean"] == round((0.9 * 4 + 0.2) / 5.0, 4), "density 没进均值"
    assert thin["mean"] > D.JUDGE_PASS, "反证前提不成立：均值本来就不过线，测不出单维闸的作用"
    assert D.judge_accepts(thin) is False, "均值过线就放行：密度这一维是装饰"
    ok = D.rubric_of({"narrative": 0.9, "causal": 0.9, "forecast": 0.9,
                      "quality": 0.9, "density": 0.62})
    assert D.judge_accepts(ok) is True, "0.62 也被拦：地板压进复评噪声带里了"


def test_repeat_rate_is_recorded_without_gating_yet():
    """机械重复率先只落观测：手上没有任何 4k 字以上的真样本，
    现在定阈值就是把猜测当判据（等 2~3 场真读数后再升成门）。"""
    cand = _cand(9000)
    r = D.repetition_rate(cand["narrative"])
    assert isinstance(r, float) and 0.0 <= r <= 1.0, r
    padded = cand["narrative"] + "\n\n" + cand["narrative"]
    assert D.repetition_rate(padded) > r, "重复率对复制粘贴不敏感，这个数没用"


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
