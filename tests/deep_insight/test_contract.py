# tests/deep_insight/test_contract.py
# -*- coding: utf-8 -*-
"""夜间深度管线的纯逻辑核心：输出契约、证据门、上下文组装、checkpoint、半套不上线。

全部离线可测（不碰网络、不碰 LLM）—— 这是阶段 1 的第一片，理由是：
把"合格/不合格"的判定写成可执行契约，比先接模型更重要。
现网的教训摆在这里：`信号深度 0-40` 其实只是素材量代理（build_daily_insight.py:2366），
一个名字里带"深度"的指标最后什么都没保证。所以这里每条判据都必须能挡一个具体失败形态。

spec: docs/superpowers/specs/2026-09-22-nightly-deep-insight-design.md §2 §3
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _art(url, source, body):
    return {"url": url, "source": source, "title": "T-" + source, "text": body}


def _long(n, seed="数"):
    return (seed * n)


def _para(n):
    """一段正常成文论述：长度可控，且含反证/限制措辞。"""
    body = "论证与数据推演" * max(1, n // 8)
    return body + "，但该判断仍受样本量与统计口径限制。"


def _event(narr_chars=3000, paras=7, chains=3, forecasts=1, cites=6, quality_why=60, **over):
    ev = {
        "id": "evt1",
        "topic": "ai",
        "title": "一条足够具体的标题",
        "narrative": "\n\n".join(_para(narr_chars // max(paras, 1)) for _ in range(paras)),
        "claims": [{"text": "论断" + str(i), "kind": "causal", "evidence": ["c1", "c2"]}
                   for i in range(5)],
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": 0.6, "evidence": ["c1", "c2"]} for _ in range(chains)],
        "forecasts": ([{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                        "check_metric": "同类竞品发布数≥3", "status": "pending"}]
                       if forecasts else []),
        "quality": {"verdict": "一手", "score": 82, "why": "依" * quality_why,
                    "basis": ["source_quality.json", "cross_dup=1"]},
        "citations": [{"id": "c%d" % (i + 1), "url": "https://x.test/%d" % i,
                       "source": "公众号:A", "chars_used": 4000, "full_len": 5706}
                      for i in range(cites)],
    }
    ev.update(over)
    return ev


# ── 1. 字数/段数：逐条作用于每个条目，不是整页总额 ─────────────────────────

def test_narrative_below_floor_is_rejected():
    """短于 2500 字必须判不过 —— 现网 9 事件里 6 个只有 162-301 字，那就是要治的东西。"""
    ev = _event(narr_chars=800)
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "800 字的正文被判合格：字数下限没生效"
    assert any("narrative" in f for f in fails), fails


def test_narrative_above_ceiling_is_flagged_not_inflated():
    """超上限要记 overlen（而不是悄悄截完当合格）—— 否则"更长=更深"会重新长回来。"""
    ev = _event(narr_chars=6000)
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert any("overlen" in f for f in fails), fails


def test_item_body_format_rejected_even_when_long_enough():
    """够长、段数也够，但仍是分点罗列 ⇒ 不算论述。这条挡"条目体冒充深度"。

    段数故意做够（7 段），否则这条会被段落数判据顺带挡住 —— 那等于没测格式检测。
    """
    ev = _event()
    ev["narrative"] = "\n\n".join("- 要点%d：%s" % (i, "证据与论证" * 30) for i in range(7))
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "7 段分点清单被当成成文论述"
    assert any("条目体" in f for f in fails), fails


# ── 2. 因果 / 预测 / 优质判断 / 引用真实性 ────────────────────────────────

def test_single_causal_chain_is_rejected():
    ev = _event(chains=1)
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "只有 1 条因果链也放行 —— 因果判据是空的"
    assert any("causal" in f for f in fails), fails


def test_forecast_without_check_metric_is_rejected():
    """缺 check_metric 的"预测"就是空话，必须挡住（防以后会怎样式表述）。"""
    ev = _event()
    ev["forecasts"] = [{"claim": "以后会更普及", "horizon_days": 7, "check_metric": "", "status": "pending"}]
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "没有可核验判据的预测被接受"
    assert any("check_metric" in f for f in fails), fails


def test_forecast_horizon_must_be_in_enum():
    ev = _event()
    ev["forecasts"] = [{"claim": "六个月内落地", "horizon_days": 200,
                        "check_metric": "是否 GA", "status": "pending"}]
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "horizon 可填任意值 ⇒ 永远不会到期，对账形同虚设"
    assert any("horizon" in f for f in fails), fails


def test_quality_verdict_must_be_from_enum():
    ev = _event()
    ev["quality"]["verdict"] = "还行"
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok and any("verdict" in f for f in fails), fails


def test_fake_citation_is_hard_failure():
    """引用 id 必须指向真实存在的 chunk —— 假链接是硬失败，整条降级。"""
    ev = _event()
    ok, fails = D.validate_event(ev, valid_ids={"c1"})
    assert not ok, "引用指向不存在的 chunk 仍算合格"
    assert any("citation" in f for f in fails), fails


def test_quality_basis_must_not_be_empty():
    """优质判断的依据不许空着 —— 空 basis 等于生成方自己拍了个分。"""
    ev = _event()
    ev["quality"]["basis"] = []
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "basis 为空也算合格"
    assert any("basis" in f for f in fails), fails


def test_a_happy_path_actually_passes():
    """反向对照：契约不能只会红。全字段合规时必须过。"""
    ev = _event()
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert ok, "合规样本被拒：%s" % fails


def test_two_paragraphs_of_equal_length_is_rejected_by_para_count():
    """段落数判据必须能被单独触发：给足字数，只把段数压到 2。

    不写这条的话 PARAS_MIN 是死常数 —— 别的判据会顺带把不合格样本挡住，
    看起来"有测试"，实际删掉段落数检查也不会红。
    """
    ev = _event()
    ev["narrative"] = _para(1600) + "\n\n" + _para(1600)
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "两段 1600 字的长文被当成合格论述"
    assert any("段落数" in f for f in fails), fails


def test_missing_caveat_statement_is_rejected():
    """无反证/限制条件 ⇒ 只是断言堆叠。这条挡"全程一边倒"的稿子。"""
    ev = _event()
    ev["narrative"] = "\n\n".join("论证与数据推演" * 55 for _ in range(7))
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "没有任何限制条件的稿子也算合格"
    assert any("反证" in f or "限制" in f for f in fails), fails


def test_relative_citation_url_is_dead_link():
    """引用必须是绝对链接：相对链接在 Pages 上点开就是 404（死链）。"""
    ev = _event()
    ev["citations"][0]["url"] = "/starhub/x.html"
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "相对链接被当成有效引用"
    assert any("死链" in f for f in fails), fails


def test_degraded_event_must_not_carry_forecasts():
    ev = _event()
    ev["degraded_reason"] = "去重后仅 1 独立源"
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})
    assert not ok, "降级条目还带着预测 —— 证据不足不许预测"
    assert any("degraded" in f for f in fails), fails


# ── 3. 证据充分性门 ────────────────────────────────────────────────────────

def test_evidence_gate_needs_three_independent_sources():
    arts = [_art("https://a.test/1", "src-a", _long(6000)),
            _art("https://b.test/1", "src-b", _long(6000))]
    ok, why = D.evidence_gate(arts)
    assert not ok and "源" in why, why


def test_evidence_gate_rejects_low_total_chars():
    """源数与长文数都够、总量不够 ⇒ 仍不过。少这条测试，总字数那一支就是死代码。"""
    arts = [_art("https://a.test/1", "src-a", _long(5706)),
            _art("https://b.test/1", "src-b", _long(4200)),
            _art("https://c.test/1", "src-c", _long(100))]
    ok, why = D.evidence_gate(arts)
    assert not ok and "字" in why, why


def test_evidence_gate_passes_on_real_shapes():
    arts = [_art("https://a.test/1", "src-a", _long(5706)),
            _art("https://b.test/1", "src-b", _long(4200)),
            _art("https://c.test/1", "src-c", _long(2500))]
    ok, why = D.evidence_gate(arts)
    assert ok, "公众号支柱形态（5706+4200+2500、3 源、2 篇长文）被误拒：%s" % why


def test_evidence_gate_rejects_many_short_pieces():
    """总量够但没有 ≥3000 字的长文 ⇒ 撑不起论证。"""
    arts = [_art("https://s.test/%d" % i, "src-%d" % i, _long(2000)) for i in range(7)]
    ok, why = D.evidence_gate(arts)
    assert not ok and "长文" in why, why


# ── 4. 上下文组装：整篇给，超预算丢整篇 ──────────────────────────────────

def test_context_keeps_whole_articles_and_drops_whole_ones():
    """预算内整篇给；不够时丢整篇不留半篇 —— 白天那种 body[:800] 就是这里要结束的。"""
    arts = [_art("https://a.test/1", "src-a", _long(5000)),
            _art("https://b.test/1", "src-b", _long(5000)),
            _art("https://c.test/1", "src-c", _long(5000))]
    got = D.assemble_context(arts, budget_tokens=12000)
    assert len(got["articles"]) == 2, [len(a["text"]) for a in got["articles"]]
    assert all(len(a["text"]) == 5000 for a in got["articles"]), "被截断了：整篇原则失效"
    assert len(got["dropped"]) == 1 and got["dropped"][0]["url"] == "https://c.test/1"
    assert got["dropped"][0]["reason"], "丢整篇必须写原因"
    assert got["total_tokens"] <= 12000


def test_token_estimate_is_cjk_honest_not_ascii_under():
    """中文按 1 字≈1 token 估；拿 ASCII 口径糊过去会把预算虚高一倍。"""
    zh = D.estimate_tokens(_long(1000))
    en = D.estimate_tokens("a" * 1000)
    assert zh >= 900, zh
    assert en <= 300, en
    assert zh > en * 2, (zh, en)


def test_empty_assembly_is_not_silently_fine():
    got = D.assemble_context([], budget_tokens=400000)
    assert got["articles"] == [] and got["total_chars"] == 0


# ── 5. checkpoint 续跑与半套不上线 ────────────────────────────────────────

def test_checkpoint_resume_skips_done_items(tmp_path):
    p = tmp_path / "deep-x.jsonl"
    p.write_text(json.dumps({"id": "evt1"}) + "\n", encoding="utf-8")
    done = D.load_done(str(p))
    assert done == {"evt1"}, done
    todo = [e for e in [{"id": "evt1"}, {"id": "evt2"}] if e["id"] not in done]
    assert [e["id"] for e in todo] == ["evt2"]


def test_partial_run_does_not_publish(tmp_path):
    """任一目标条目未落地就不合成产物 —— 半套上线会直接让页面开天窗。"""
    events = [{"id": "evt1"}, {"id": "evt2"}]
    done = [{"id": "evt1"}]
    assert D.can_publish(events, done, budget_used_calls=10, call_cap=80) is False


def test_budget_exhaustion_records_not_run_and_still_publishes(tmp_path):
    """超预算：未做的显式记 not_run，已完成的仍可上线（否则永远发不出去）。"""
    events = [{"id": "evt%d" % i} for i in range(12)]
    done = [{"id": "evt%d" % i} for i in range(8)]
    assert D.can_publish(events, done, budget_used_calls=81, call_cap=80) is True
    assert D.missing(events, done, stop="budget") == [{"id": "evt8", "reason": "not_run:budget"},
                                                        {"id": "evt9", "reason": "not_run:budget"},
                                                        {"id": "evt10", "reason": "not_run:budget"},
                                                        {"id": "evt11", "reason": "not_run:budget"}]


def test_nothing_done_never_publishes_even_over_budget(tmp_path):
    """一条都没做成时，"撞预算"不能变成放行理由 —— 那会发出一个空报告页。"""
    events = [{"id": "evt%d" % i} for i in range(12)]
    assert D.can_publish(events, [], budget_used_calls=200, call_cap=80) is False


def test_crash_middle_is_not_disguised_as_budget_stop(tmp_path):
    """没撞预算却少了一半条目 ⇒ 这是失败，不许冒充 not_run 蒙混上线。"""
    events = [{"id": "evt%d" % i} for i in range(12)]
    done = [{"id": "evt%d" % i} for i in range(6)]
    assert D.can_publish(events, done, budget_used_calls=10, call_cap=80) is False


# ── 6. 预测落盘与对账 ─────────────────────────────────────────────────────

def test_predictions_are_dated_and_reconcilable(tmp_path):
    p = tmp_path / "pred.jsonl"
    rows = [{"event_id": "evt1", "claim": "三个月内出现跟随者", "horizon_days": 7,
             "check_metric": "同类发布数>=3", "made_on": "2026-09-22"}]
    D.append_predictions(str(p), rows)
    st = D.reconcile(str(p), today="2026-09-30", verdicts={"三个月内出现跟随者": "hit"})
    assert st["due"] == 1 and st["hit"] == 1, st
    assert 0.0 <= st["auto_checkable_share"] <= 1.0, st


def test_unexpired_predictions_are_not_counted_as_miss(tmp_path):
    p = tmp_path / "pred.jsonl"
    D.append_predictions(str(p), [{"event_id": "e", "claim": "c", "horizon_days": 14,
                                   "check_metric": "m", "made_on": "2026-09-22"}])
    st = D.reconcile(str(p), today="2026-09-25", verdicts={})
    assert st["due"] == 0 and st["miss"] == 0, st


# ── spec §3 上下文预算：丢整篇要记原因、不许越顶、丢了不能又留 ──────────────

def test_over_budget_drops_whole_articles_with_a_cause():
    """三条各挡一种失败形态：只记 url 不记原因 = 事后没人知道为什么少一篇；
    丢了又留在 keep 里 = 同一篇进两次、证据数虚高；
    total_chars 把被丢的也算上 = 上下文利用率自报读数造假。"""
    arts = [_art("https://a.test/%d" % i, "src%d" % i, "字" * 6000) for i in range(6)]
    ctx = D.assemble_context(arts, budget_tokens=20000)
    assert ctx["articles"] and ctx["dropped"], (len(ctx["articles"]), len(ctx["dropped"]))
    kept = {a["url"] for a in ctx["articles"]}
    for d in ctx["dropped"]:
        assert d["url"] not in kept, "同一篇既算进上下文又记成被丢"
        assert "预算" in d["reason"] and "/" in d["reason"], d["reason"]
        assert d["tokens"] > 0
    assert ctx["total_chars"] == sum(D.count_chars(a["text"]) for a in ctx["articles"]), \
        "total_chars 把被丢的也算进去了"
    assert ctx["total_tokens"] <= 20000


def test_budget_ceiling_holds_even_if_caller_asks_for_the_moon():
    """`--budget-tokens 999999999` 手滑不能把 1M 窗口当预算。
    上限 ≤800k 是 spec §3 定的：余量要留给系统提示、judge 同文复看与一次重生成。"""
    arts = [_art("https://b.test/%d" % i, "src%d" % i, "字" * 120000) for i in range(9)]
    ctx = D.assemble_context(arts, budget_tokens=10 ** 9)
    assert ctx["total_tokens"] <= D.MAX_BUDGET_TOKENS, ctx["total_tokens"]
    assert ctx["dropped"], "900k token 全塞进去了 —— 上限根本没生效"
