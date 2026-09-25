# -*- coding: utf-8 -*-
"""两路审查（规格合规 + 对抗性）结论的判据。每条对应一个被复现出来的失败形态。

来历：2026-09-23 两路 fresh-eyes 审查。P0 三条都是"CI 全绿但生产会出事"的形状：
judge 少回一个键就整夜归零、并把真因记成"模型写不长"；墙钟闸在 workers>1 下形同不存在；
段数上限与每段目标不匹配，丢段是结构必然。审查员的复现脚本在 `_scratch/adv_probe*.py`。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _arts(n=8):
    pool, links = {}, []
    for i in range(n):
        u = "https://s%d.test/a%d" % (i % 3, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "标题%d" % i,
                   "text": "证据正文%d。" % i * 1600, "has_full": True,
                   "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    return pool, links


def _anchor(links, n):
    return json.dumps({"date": "2026-09-23", "events": [
        {"id": "e%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "摘要",
         "key_links": list(links)} for i in range(n)]}, ensure_ascii=False)


def _run(tmp_path, sub, client=None, workers=1, n_events=2, log=None, staged=True, **kw):
    pool, links = _arts(8)
    out_dir = os.path.join(str(tmp_path), "ns-" + sub)
    res = D.night_run(purpose="test", client=client or D.FakeClient(), out_dir=out_dir,
                      keys=["k1", "k2", "k3", "k4"], anchor_raw=_anchor(links, n_events),
                      pool=pool, date_str="2026-09-23", pred_raw="", quality_raw={},
                      get=lambda url, timeout=90: b"", log=log or (lambda s: None),
                      sleep=lambda s: None, workers=workers, staged=staged,
                      call_cap=kw.pop("call_cap", 4000), wait_cap_s=5, **kw)
    return res, json.load(open(res["json"], encoding="utf-8"))


# ── P0-1：judge 少给一维 ─────────────────────────────────────────────────

def test_missing_judge_dimension_is_not_counted_as_zero_score():
    """缺失维度不许当 0 分：那会把均值摊薄、把单维地板踩破，一条好洞察被判死。"""
    four = D.rubric_of({"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9})
    assert four["missing_dims"] == ["density"], four
    assert four["density"] is None, "缺失被写成 0.0 就是把它当内容分数"
    assert four["mean"] == 0.9, "均值被缺失维度摊薄：%s" % four["mean"]
    assert D.judge_accepts(four) is False, "判据没跑通却放行"


def test_missing_judge_dimension_is_named_in_the_artifact(tmp_path):
    """产物必须说清"是判据协议没跑通"，不许留一句"重写 2 次仍不合格"让人去改 prompt。

    审查复现：四维 0.95、正文 4,350 字，只因为 judge 没回第五个键，
    日志与产物一致写成 `narrative=200 字 / 重写 2 次仍不合格` —— 误记账。
    """
    class NoDensity(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "judge":
                self.calls.append("judge")
                return json.dumps({"narrative": 0.95, "causal": 0.95,
                                   "forecast": 0.95, "quality": 0.95})
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    _res, doc = _run(tmp_path, "nodens", client=NoDensity(), n_events=1)
    ev = doc["events"][0]
    joined = " ".join(ev.get("contract_fails") or [])
    assert "judge 未给维度" in joined, \
        "缺维被当成内容不合格记账：fails=%r" % (ev.get("contract_fails"),)
    assert ev.get("degraded_reason"), "judge 协议没跑通却仍标合格"


def test_density_vetoes_even_when_the_other_four_are_high():
    """density 走单维否决：不许被另外四维的高分抬过去（那正是"长而空"的得分路径）。"""
    padded = D.rubric_of({"narrative": 0.95, "causal": 0.95, "forecast": 0.95,
                          "quality": 0.95, "density": 0.2})
    assert padded["mean"] == 0.95, padded
    assert D.judge_accepts(padded) is False, "密度 0.2 仍被均值抬过线"
    ok = D.rubric_of({"narrative": 0.95, "causal": 0.95, "forecast": 0.95,
                      "quality": 0.95, "density": 0.62})
    assert D.judge_accepts(ok) is True, "地板压进复评噪声带了"


# ── P0-2：墙钟闸在并发下失效 ─────────────────────────────────────────────

def test_wall_clock_gate_still_holds_with_multiple_workers(tmp_path):
    """workers>1 时闸必须照样拦：派单瞬时完成，闸坐在派单循环里等于没有闸。"""
    answers = [False, False, False] + [True] * 40

    def over_time(self):
        return answers.pop(0) if answers else True
    monkey_attr = D.Budget.over_time
    D.Budget.over_time = over_time
    try:
        _res, doc = _run(tmp_path, "wall3", workers=3, n_events=6)
    finally:
        D.Budget.over_time = monkey_attr
    done = [e["id"] for e in doc["events"]]
    assert len(done) == 3, "并发下墙钟没拦：做完了 %d 条 %s" % (len(done), done)
    reasons = {r["reason"] for r in doc.get("not_run") or []}
    assert reasons == {"not_run:wallclock"}, doc.get("not_run")


def test_wall_clock_gate_asks_once_per_item_serially(tmp_path):
    """串行分支不许问两遍墙钟：那条判据（test_night_run 的 answers 消费数）会漂。"""
    pops = {"n": 0}

    def over_time(self):
        pops["n"] += 1
        return False
    orig = D.Budget.over_time
    D.Budget.over_time = over_time
    try:
        _run(tmp_path, "wall1", workers=1, n_events=3)
    finally:
        D.Budget.over_time = orig
    assert pops["n"] == 3, "每条应当只问一次墙钟，实为 %d 次" % pops["n"]


# ── P0-3：段数 × 每段目标 必须容得下总上限 ───────────────────────────────

def test_section_budget_fits_inside_the_ceiling_at_max_sections():
    """按**最大**段数验不变式。原来用 PARAS_MIN 验，破口在 SECTIONS_MAX，永远不红。"""
    assert D.SECTIONS_MAX * D.PERA_TARGET <= D.NARR_MAX, \
        "段段写到位就必然超线被裁：%d×%d > %d" % (
            D.SECTIONS_MAX, D.PERA_TARGET, D.NARR_MAX)
    assert D.SECTIONS_MAX >= D.PARAS_MIN, "段数上限被压到下限以下"


def test_section_prompt_target_is_the_same_number_as_the_invariant(tmp_path):
    """进 prompt 的"每段目标"必须就是派生量本身，不能是第二处现算。"""
    pool, links = _arts(8)
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": list(links[:2])}
    arts = [pool[u] for u in list(links[:4])]
    ctx = {"articles": arts, "ids": {"c%d" % (i + 1): a["url"] for i, a in enumerate(arts)},
           "signals": {}}
    p = D.build_section_prompt(ev, ctx, {"title": "t", "focus": "f", "evidence": ["c1"]}, 1, 6)
    assert str(D.PERA_TARGET) in p, "prompt 里的每段目标与 PERA_TARGET 分叉"


# ── P1-4：覆盖判据只认这条引过的编号 ─────────────────────────────────────

def _cand(claim_ids, cites=8, chars=9000):
    one = "论证与数据推演"
    body = one
    while D.count_chars(body) < chars // 8:
        body += "证据之间可核对，需结合口径差异来看。"
    nar = "\n\n".join(body + "但该判断仍受样本量与统计口径限制。" for _ in range(8))
    return {
        "id": "e1", "title": "标题", "topic": "ai", "narrative": nar,
        "claims": [{"text": "论断%d" % i, "kind": "causal", "evidence": [c]}
                   for i, c in enumerate(claim_ids)],
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": 0.6, "evidence": ["c1"]} for _ in range(3)],
        "forecasts": [{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类发布数>=3"}],
        "quality": {"verdict": "一手", "score": 82, "why": "依" * 60, "basis": ["sig:c1"]},
        "citations": [{"id": "c%d" % (i + 1), "url": "https://x.test/%d" % i}
                      for i in range(cites)],
    }


def test_coverage_ignores_ids_the_item_never_cited():
    """claims 挂 citations 里没有的编号，不算覆盖。

    不求交的话，"多写几条 claim、各挂一个新编号"就能白拿覆盖数，正文照样是水
    （审查复现：9,598 字只引 5 篇，claims 铺满 c1..c10 被判合格）。
    """
    ev = _cand(["c1", "c2", "c3", "c9", "c10"], cites=8)
    ok, fails = D.validate_event(ev, valid_ids=set("c%d" % (i + 1) for i in range(12)),
                                valid_basis={"sig:c1"})
    assert not ok, "用没引过的编号刷覆盖数却判合格：%r" % (fails,)
    assert any("长而空" in f for f in fails), fails


def test_coverage_passes_when_genuinely_spread_over_cited_sources():
    ev = _cand(["c%d" % (i + 1) for i in range(7)], cites=8)
    ok, fails = D.validate_event(ev, valid_ids=set("c%d" % (i + 1) for i in range(12)),
                                 valid_basis={"sig:c1"})
    assert ok, fails


# ── P2-4：账本一行坏账不许烧掉整夜 ───────────────────────────────────────

def test_malformed_ledger_row_does_not_burn_the_night():
    """账本读自上一夜发布的 JSONL，而 settle/prune 在产物落盘**之前**执行。"""
    rows = [{"claim": "好", "horizon_days": 7, "made_on": "2026-09-22", "status": "pending"},
            {"claim": "坏日期", "horizon_days": 7, "made_on": "不是日期", "status": "hit"},
            # 未到期那行也必须带坏日期：`settle` 对非 pending 行根本不算到期，
            # 只放 hit 行的话，`_due_day` 里那层防护永远不会被走到（变异体 R8 存活过）。
            {"claim": "坏日期未到期", "horizon_days": 7, "made_on": "0000-00-00",
             "status": "pending"},
            {"claim": "坏窗口", "horizon_days": "很多", "made_on": "2026-09-22",
             "status": "pending"}]
    stats, out = D.settle(rows, today="2026-09-30", verdicts={})
    kept = D.prune_predictions(out, today="2026-09-30")
    assert any(r["claim"] == "好" for r in kept), kept
    assert any(r["claim"] == "坏日期未到期" for r in kept), \
        "坏日期的未到期行被算成到期或整场抛穿：%s" % [r["claim"] for r in kept]
    # 好行确实到期（09-22 + 7 天 = 09-29 ≤ 09-30）；两行坏数据既不炸也不被算成到期
    assert stats["due"] == 1 and stats["unknown"] == 1, stats


# ── P1-1：单趟路径的输出上限 ─────────────────────────────────────────────

class _CapClient(D.FakeClient):
    """带 max_tokens 的客户端：告警要坐在构造之外，显式传 client 的调用方也得听到。"""
    max_tokens = 12000


def test_single_pass_warns_before_spending_when_max_tokens_is_too_small(tmp_path):
    """`--single-pass` 一次要吐完整条：上限不够就是必然截断，必须开场喊，不要半夜产出 0 字。"""
    lines = []
    _run(tmp_path, "capwarn", client=_CapClient(), staged=False, n_events=1, log=lines.append)
    hit = [l for l in lines if "单趟输出上限不够" in l]
    assert hit, "没喊话；客户端 max_tokens=%d < 单趟最坏输出 %d" % (
        _CapClient.max_tokens, D.SINGLE_PASS_OUT_TOKENS)


def test_two_stage_does_not_emit_the_single_pass_warning(tmp_path):
    """两段式每段最多 PERA_MAX 字，撞不到这个上限 —— 不许把告警变成常驻噪音。"""
    lines = []
    _run(tmp_path, "capquiet", client=_CapClient(), staged=True, n_events=1, log=lines.append)
    assert not [l for l in lines if "单趟输出上限不够" in l], lines


# ── P2：观测字段必须真的被接线（不是纯写字段）─────────────────────────────

def _payload(all_degraded=True):
    ev = {"id": "evt1", "topic": "ai", "title": "某事件",
          "narrative": "证据不足，按快讯处理。" if all_degraded else "论证" * 400,
          "claims": [], "causal_chains": [], "forecasts": [], "citations": [],
          "quality": {}, "rubric": {"mean": 0.0}}
    if all_degraded:
        ev["degraded_reason"] = "重写 2 次仍不合格"
    return {"date": "2026-09-23", "generated_at": "2026-09-23T12:00:00+08:00",
            "engine": D.SCHEMA_VERSION,
            "budget": {"llm_calls": 63, "elapsed_s": 954, "qualified": 0 if all_degraded else 1,
                       "degraded": 1 if all_degraded else 0},
            "anchor_diff": [], "predictions_reconciled": {}, "events": [ev]}


def test_page_says_so_when_nothing_qualified():
    """全降级上线时页面必须自己讲清楚：不然读者以为今天有一篇深度报告。

    这是"沉默 vs 说话"的分界：政策从"不发"改成"发 + 横幅"，
    没有横幅就等于把失败伪装成正常。
    """
    html = D.render_page(_payload(True))
    assert "今日无合格深度条目" in html, "全降级的页面没有横幅"
    assert "按快讯" in html, html[:400]
    ok = D.render_page(_payload(False))
    assert "今日无合格深度条目" not in ok, "有合格条目也挂横幅：告警就废了"


def test_one_illegal_forecast_does_not_kill_the_whole_item():
    """一格违约的预测摘掉那一条，不废整篇。

    现网 run 35823028980：evt_008 正文 8,621 字、结构齐全，只因 `horizon_days 30`
    整条降级成 192 字 —— 代价与过错不成比例。摘除必须留账，静默删就是替模型改答案。
    """
    cand = {"forecasts": [
        {"claim": "三个月内出现跟随者", "horizon_days": 30, "check_metric": "同类发布数>=3"},
        {"claim": "两周内出现跟随者", "horizon_days": 14, "check_metric": "同类发布数>=3"}]}
    out = D.repair_forecasts(cand)
    assert [f["horizon_days"] for f in out["forecasts"]] == [14], out["forecasts"]
    assert out["forecasts_dropped"] and "horizon_days" in out["forecasts_dropped"][0]["reason"], \
        "摘了却没留账：%s" % out.get("forecasts_dropped")


def test_all_illegal_forecasts_still_fail_the_item():
    """全摘光就必须不合格：§2 要求至少一条可核验预测，这条不许被"宽容"掉。"""
    cand = {"forecasts": [{"claim": "长期看会普及", "horizon_days": 90, "check_metric": ""}]}
    assert D.repair_forecasts(cand)["forecasts"] == []
    ev = _cand(["c1", "c2", "c3"], cites=8)
    ev["forecasts"] = []
    ok, fails = D.validate_event(ev, valid_ids=set("c%d" % (i + 1) for i in range(12)),
                                 valid_basis={"sig:c1"})
    assert not ok and any("forecasts" in f for f in fails), fails


def test_observability_fields_reach_the_artifact_on_every_degrade_path(tmp_path):
    """审查复现：把 `repeat_rate` 的赋值整行删掉，208 条判据照样全绿 —— 那是没接线。

    这里走**证据门降级**那条早退路径：它曾经根本不写这两格。
    """
    pool, links = {}, []
    for i in range(4):
        u = "https://t.test/%d" % i
        pool[u] = {"url": u, "source": "s%d" % i, "title": "T%d" % i,
                   "text": "短" * 40, "has_full": True, "source_key": "s%d_%d" % (i, i)}
        links.append(u)
    out_dir = os.path.join(str(tmp_path), "ns-gate")
    res = D.night_run(purpose="test", client=D.FakeClient(), out_dir=out_dir,
                      keys=["k1"], anchor_raw=_anchor(links, 1), pool=pool,
                      date_str="2026-09-23", pred_raw="", quality_raw={},
                      get=lambda url, timeout=90: b"", log=lambda s: None,
                      sleep=lambda s: None, wait_cap_s=5, call_cap=4000)
    doc = json.load(open(res["json"], encoding="utf-8"))
    ev = doc["events"][0]
    assert "restate_rate" in ev and "narrative_chars_full" in ev, \
        "证据门降级条目没有观测字段，注释里那句『每场都在产物里』就是假话：%s" % sorted(ev)
    assert isinstance(ev["restate_rate"], float)
