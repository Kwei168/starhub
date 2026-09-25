# -*- coding: utf-8 -*-
"""批 3：判定去噪 —— 单遍 LLM 打分不可复现，重写也不该"抖一下就算改进"。

现网证据（两场）：
  · 09-23 evt_011 均值 **0.7500**，正好压在 JUDGE_PASS=0.75 这条线上；
  · 09-24 evt_015 均值 0.65 / evt_003 0.55 —— 都在"差一点点"的带里。
而我自己量过同一内容复评极差 **0.17**（9-19 那次事故记在台账里）。
也就是说：**单遍均值过线 = 抛硬币**，而重写两轮里"哪一轮该被采纳"目前没有规则，
只看最后一轮 —— 完全可能把一版只是抖高了的劣化版发出去。

白天线为此写了 `_robust_quality_eval:4030`（多样本取中位）+ 采纳须超 ±0.02 否则回滚快照
（`:4194-4231`，那条 ±0.02 是它自己同内容双样本的方差，不是我们的 0.17）。
这里按我们的噪声定我们的带，并按"只摘那一条"的既有政策记账。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _cand(n_cites=8, n_claims=6):
    ids = ["c%d" % (i + 1) for i in range(n_cites)]
    nar = "\n\n".join("论证与数据推演%d，但该判断仍受样本量与统计口径限制。" % i
                      for i in range(10))
    return {
        "id": "e1", "title": "事件甲", "topic": "ai", "narrative": nar,
        "claims": [{"text": "论断%d" % i, "kind": "causal",
                    "evidence": [ids[i % len(ids)]]} for i in range(n_claims)],
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": "中高", "evidence": [ids[0]]} for _ in range(3)],
        "forecasts": [{"claim": "七天内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类发布数>=3"}],
        "quality": {"verdict": "一手", "score": 82, "why": "依" * 60, "basis": ["sig:c1"]},
        "citations": [{"id": i, "url": "https://s.test/%s" % i} for i in ids],
    }


class JudgeScript:
    """按顺序吐 judge 分数；其它 kind 交给 FakeClient。"""

    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = []
        self.inner = D.FakeClient()

    def complete(self, prompt, key=None, kind="generate"):
        self.calls.append(kind)
        if kind == "judge":
            s = self.scores.pop(0) if self.scores else {"narrative": 0.9, "causal": 0.9,
                                                       "forecast": 0.9, "quality": 0.9,
                                                       "density": 0.9}
            return json.dumps(s)
        return self.inner.complete(prompt, key=key, kind=kind)


def _judge(cand, scores):
    ctx = {"articles": [{"text": "证据" * 50}], "ids": {}, "signals": {}, "quality_signals": {}}
    return D.judge_event_multi(JudgeScript(scores), cand, ctx,
                               D.KeyPool(["k1"]), D.Budget(400000))


def test_judge_sample_count_is_two_and_it_is_one_place():
    """单遍打分已被证明落在自己的噪声带里 —— 采样数必须是个显式常量。"""
    assert D.JUDGE_SAMPLES >= 2, "还在单遍判：均值 0.7500 压线过就是抛硬币"
    assert D.ADOPT_MARGIN > 0.0, "没有采纳边界的重写等于随机采纳"


def test_median_of_two_samples_not_the_last_one():
    """两样本 [0.70, 0.95] 的中位是 0.825，取"最后一次"会读成 0.95。"""
    dims = [{"narrative": 0.7, "causal": 0.7, "forecast": 0.7, "quality": 0.7, "density": 0.7},
            {"narrative": 0.95, "causal": 0.95, "forecast": 0.95, "quality": 0.95, "density": 0.95}]
    r = _judge(_cand(), dims)
    assert abs(r["mean"] - 0.825) < 1e-6, r
    assert r["judge_spread"] == 0.25, r
    assert len(r["judge_samples"]) == 2, r


def test_spread_wider_than_the_noise_band_is_visible_in_the_artifact():
    """抖得比噪声带还宽的判定不许被当成功利结论 —— 至少要读得出来。"""
    dims = [{"narrative": 0.5, "causal": 0.5, "forecast": 0.5, "quality": 0.5, "density": 0.5},
            {"narrative": 0.95, "causal": 0.95, "forecast": 0.95, "quality": 0.95, "density": 0.95}]
    r = _judge(_cand(), dims)
    assert r["judge_spread"] > D.ADOPT_MARGIN, r
    assert r.get("unstable") is True, "极差超过噪声带却没标记：下一轮还会拿它当依据"


def test_within_noise_rewrite_is_not_an_improvement():
    """0.75 → 0.79 是 0.04 的变化，落在 0.17 极差的带内：不算改进（停滞判据用）。"""
    assert D.beat_by_margin({"mean": 0.79}, {"mean": 0.75}) is False


def test_real_improvement_beats_the_band():
    """反向控制：0.75 → 0.90 必须算变好，否则这条闸就是把重写冻死。"""
    assert D.beat_by_margin({"mean": 0.90, "density": 0.8}, {"mean": 0.75, "density": 0.7}) is True


def test_veto_dimension_regression_blocks_progress_even_if_mean_rises():
    """均值涨出噪声带、density 塌：正是『长而空被高分抬过去』那条得分路径，必须不算变好。

    白天在 faith 上有一条同族教训（09-19 04:14 期 0.90→0.66 被综合分掩盖）。
    这里均值差特意给到 0.15（大于噪声带 0.09），否则报红的其实是边界那条判据。
    """
    assert D.beat_by_margin({"mean": 0.95, "density": 0.55},
                            {"mean": 0.80, "density": 0.75}) is False


def test_small_veto_wobble_does_not_block_progress():
    """否决维抖在噪声带以内不该一票否定：那会把真实改进也冻住。"""
    assert D.beat_by_margin({"mean": 0.95, "density": 0.70},
                            {"mean": 0.80, "density": 0.75}) is True


# ---------- 停滞判据：哪一版该停止重写 ----------

def test_changed_contract_failures_are_not_a_stall():
    """违约清单变了 = 上一轮的反馈被消化了：下一轮真可能翻盘，不许收手。"""
    cur = ({"mean": 0.0}, ["正文 3000 字，须在 >=4000"])
    prev = ({"mean": 0.0}, ["正文 1800 字，须在 >=4000"])
    assert D.no_progress(cur[0], cur[1], prev[0], prev[1]) is False, \
        "两趟均值都是 0.0 就判停滞：契约没过时 0.0 是『没测到分』，不是『抖不动』"


def test_identical_contract_failures_are_a_stall():
    """同一批违约重写两轮没修掉：模型不接这个形状，第三轮还是同一份。"""
    fails = ["正文 1800 字，须在 >=4000"]
    assert D.no_progress({"mean": 0.0}, fails, {"mean": 0.0}, fails) is True


def test_repeated_protocol_failure_stalls_even_at_a_high_mean():
    """judge 少给维度时均值可以很高（现网四维 0.95），但那是协议没跑通。

    不许被『近线豁免』救活：漏键不是模型写得差，重写三轮也修不好它，
    只会把整夜预算烧在同一个错误归因上（09-23 审查 P0-1 的误记账形状）。
    """
    fails = ["judge 未给维度 density：判据不可用，不许当合格"]
    assert D.no_progress({"mean": 0.95}, fails, {"mean": 0.95}, fails) is True


def test_near_the_pass_line_keeps_rewriting():
    """离合格线一步之遥（线 0.75，读到 0.6375/0.72）时不许停手：那才是真有机会的带。

    带宽不是拍的：批 2 验证场 run 35940113012 两条降级条目终判 **0.6375**
    （evt_002 四维 0.55~0.85、evt_003 0.5~0.8），一条按一个噪声带豁免（0.66）就会被掐在
    第二轮 —— 而那正是"差一点点"的形状。现按两个带（0.57）豁免，
    并把每趟均值记进 `regen_scores`，六场之后再决定要不要挪这条线。
    """
    assert D.no_progress({"mean": 0.72}, [], {"mean": 0.70}, []) is False
    assert D.no_progress({"mean": 0.6375}, [], {"mean": 0.6375}, []) is False
    assert D.near_pass_line({"mean": 0.6375}) is True, \
        "0.6375 是本批唯一有两条现网读数的降级形态，落在豁免带外就是拿规则杀掉最该救的条目"


def test_hopeless_judged_means_stall():
    """0.40 → 0.42：两个带之外、又没好出噪声带 —— 第三趟是重掷骰子。"""
    assert D.no_progress({"mean": 0.42}, [], {"mean": 0.40}, []) is True
    assert D.near_pass_line({"mean": 0.42}) is False


def test_every_attempt_score_is_kept_in_the_artifact():
    """轨迹必须可读：只留最后一版的分，停滞规则对不对永远没有依据。"""
    rec = _deepen(JudgeSeq([0.70, 0.72, 0.71]))
    traj = rec.get("regen_scores")
    assert traj and len(traj) == 3, "三趟判定只留下一趟：%r" % (traj,)
    assert [t["attempt"] for t in traj] == [0, 1, 2], traj
    assert abs(traj[0]["mean"] - 0.70) < 1e-6 and abs(traj[-1]["mean"] - 0.71) < 1e-6, traj
    assert len(traj[0]["samples"]) == D.JUDGE_SAMPLES, \
        "样本没留下：只有中位数的话，极差 0.17 那条依据下次还是靠嘴说"


def test_improving_judged_means_keep_rewriting():
    """0.40 → 0.60 好出了噪声带：即使还没过线，也不许按停滞收手。"""
    assert D.no_progress({"mean": 0.60}, [], {"mean": 0.40}, []) is False


# ---------- 停滞必须落到产物里（否则它就是一条没人调用的规则） ----------

def _pool(n=6):
    pool, links = {}, []
    for i in range(n):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "T%d" % i,
                   "text": "来源%d全文，独家数字 %d。" % (i, 100 + i) * 900,
                   "has_full": True, "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    return pool, links


def _deepen(client, staged=False, max_regen=None):
    # 默认跟着模块常量走：把 2 写死在夹具里，改 MAX_REGEN 时这套判据一条都不会报红
    max_regen = D.MAX_REGEN if max_regen is None else max_regen
    pool, links = _pool()
    return D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                         "links": list(links)},
                        pool, client, D.Budget(400000), D.KeyPool(["k1"]),
                        max_regen=max_regen, source_quality={},
                        sleep=lambda s: None, wait_cap_s=5, staged=staged)


class ShortNarrative(D.FakeClient):
    """每一趟都给同一份短正文：契约违约清单恒定，正是停滞规则的靶子。"""

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "generate":
            self.calls.append("generate")
            doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="structure"))
            doc["narrative"] = "论证很短。" * 30
            return json.dumps(doc, ensure_ascii=False)
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


class JudgeSeq(D.FakeClient):
    """按趟吐判定均值（同一趟两样本给同值，中位数就等于它）。"""

    def __init__(self, means):
        D.FakeClient.__init__(self)
        self.means = list(means)
        self.n_judge = 0

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "judge":
            self.calls.append("judge")
            i = self.n_judge // D.JUDGE_SAMPLES
            self.n_judge += 1
            v = self.means[i] if i < len(self.means) else self.means[-1]
            return json.dumps({d: v for d in D.JUDGE_DIMS})
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


def test_stall_reaches_the_artifact_with_honest_math():
    """停滞要能在产物里核对：重写了几轮、为什么收手、原来那笔『重写 2 次』的假账不许留。"""
    c = ShortNarrative()
    rec = _deepen(c)
    n_gen = c.calls.count("generate")
    assert n_gen == 2, "只该重写 1 轮就收手，实发 %d 趟" % n_gen
    assert rec.get("regen_stalled"), "停滞只打在日志上：下一跑没人能核对它发生过"
    assert rec["regen_stalled"][-1]["kind"] == "contract", rec["regen_stalled"]
    assert rec["regen_used"] == 1, rec.get("regen_used")
    reason = rec.get("degraded_reason") or ""
    assert "未修掉" in reason, \
        "契约违约的停滞要写成『没修掉』，写成『无改善』会把人引去调判定而不是调形状：%r" % reason
    assert "重写 2 次" not in reason, "明明只重写了 1 轮，账上却写 2 次：%r" % reason


class NoDensity(D.FakeClient):
    """契约全过、judge 少回一个维度：现网 09-23 审查 P0-1 的形状。"""

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "judge":
            self.calls.append("judge")
            return json.dumps({"narrative": 0.95, "causal": 0.95,
                               "forecast": 0.95, "quality": 0.95})
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


def test_protocol_stall_reaches_the_artifact():
    """协议违约那一档也要在产物里可核对，并且不许被高分均值续命。"""
    c = NoDensity()
    rec = _deepen(c)
    assert c.calls.count("generate") == 2, c.calls.count("generate")
    assert (rec.get("regen_stalled") or [{}])[-1].get("kind") == "judge_proto", \
        rec.get("regen_stalled")
    assert "未给维度" in " ".join((rec.get("regen_stalled") or [{}])[-1].get("fails") or []), \
        "停滞那笔账没带上违约原文：光看 kind 分不开是哪一条卡住了"
    assert "未修掉" not in rec.get("degraded_reason", ""), \
        "协议没跑通不许记成『违约未修掉』：" + rec.get("degraded_reason", "")
    assert "未给维度" not in rec.get("degraded_reason", ""), \
        "理由格不许拼违约原文：degraded_reason 会上屏，原文里可能带着模型自报的假链接"
    assert "未给维度" in " ".join(rec.get("contract_fails") or []), rec.get("contract_fails")


def test_control_near_line_uses_the_full_regen_budget():
    """反向控制：近线抖动必须跑满 max_regen，否则停滞闸就是把重写冻死。"""
    c = JudgeSeq([0.70, 0.72, 0.71])
    rec = _deepen(c)
    assert c.calls.count("generate") == 3, c.calls.count("generate")
    assert not rec.get("regen_stalled"), rec.get("regen_stalled")
    assert rec["regen_used"] == 2, rec["regen_used"]
    assert "无改善" not in (rec.get("degraded_reason") or ""), rec.get("degraded_reason")


def test_accepted_item_keeps_its_score_trajectory():
    """合格那条也要带轨迹：只给降级条目记的话，"三轮里哪一轮该采纳"还是读不出来。"""
    rec = _deepen(JudgeSeq([0.86, 0.90]))
    assert not rec.get("degraded_reason"), rec.get("degraded_reason")
    traj = rec.get("regen_scores") or []
    assert [t["attempt"] for t in traj] == [0], traj
    assert len(traj[0]["samples"]) == D.JUDGE_SAMPLES, traj


def test_hopeless_judge_reject_stops_after_one_rewrite():
    """0.40 那种判定：契约过了但离线远，重写两轮纯属烧钱 —— 现网 09-24 就是 0.55/0.65。"""
    rec = _deepen(JudgeSeq([0.40, 0.40, 0.40]))
    assert rec.get("regen_stalled"), "判定停滞没进产物：下一轮还是照烧三轮"
    assert rec["regen_stalled"][-1]["kind"] == "judge", rec["regen_stalled"]
    assert rec["regen_used"] == 1
    assert "无改善" in (rec.get("degraded_reason") or ""), rec.get("degraded_reason")


def test_judge_samples_are_bounded_per_attempt():
    """每趟采 JUDGE_SAMPLES 次，不是每条 claim 采一遍（那会把成本乘没）。

    用"整趟 + 不超两趟"的界钉，而不是 `== JUDGE_SAMPLES` 恒等：
    恒等式在 JUDGE_SAMPLES=3 时照样绿，等于没钉住"每趟几遍"这件事。
    """
    c = JudgeScript([{"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9,
                      "density": 0.9}] * 9)
    ctx = {"articles": [{"text": "证据" * 50}], "ids": {}, "signals": {}, "quality_signals": {}}
    D.judge_event_multi(c, _cand(n_claims=6), ctx, D.KeyPool(["k1"]), D.Budget(400000))
    n = c.calls.count("judge")
    assert n % D.JUDGE_SAMPLES == 0 and 0 < n <= 2 * D.JUDGE_SAMPLES, c.calls


def test_missing_dimension_still_blocks_under_median():
    """少给维度是判据协议没跑通，中位数不许把它平均掉。"""
    dims = [{"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9},
            {"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9}]
    r = _judge(_cand(), dims)
    assert r["missing_dims"], "少给 density 却没记缺失维度"
    assert D.judge_accepts(r) is False


# ══════════════ 批 3.5：对抗审查第二轮（六条自证过的指控） ══════════════
# 每条判据都对应一次真复现，见 _scratch/verify_findings.txt（同一台机、同一份代码）。

def _samples(vals):
    """给 `Seq` 用：一串均值 → 每趟两样本（同值，中位就等于它）。"""
    out = []
    for v in vals:
        out.append({d: v for d in D.JUDGE_DIMS})
        out.append({d: v for d in D.JUDGE_DIMS})
    return out


def _uneven(a, b):
    return [{d: a for d in D.JUDGE_DIMS}, {d: b for d in D.JUDGE_DIMS}]


class Seq(D.FakeClient):
    """按 judge 调用序号吐维度分；其它 kind 走 FakeClient。"""

    def __init__(self, per_sample):
        D.FakeClient.__init__(self)
        self.per_sample = list(per_sample)
        self.n = 0

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "judge":
            self.calls.append("judge")
            i = min(self.n, len(self.per_sample) - 1)
            self.n += 1
            return json.dumps(self.per_sample[i])
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


def test_coin_flip_acceptance_earns_another_attempt():
    """P0-1 复现：两样本 0.66/0.84 → 中位正好 0.75 压线、极差 0.18。

    这一档就是本批的靶子（09-23 evt_011 均值 0.7500）。合格版必须继续重判一轮，
    而不是"抖过线就收工"—— 那等于把本批唯一新增的观测字段留在原地没人消费。
    """
    c = Seq(_uneven(0.66, 0.84) + _samples([0.80]))
    rec = _deepen(c)
    assert c.calls.count("generate") == 2, \
        "压线那一版直接被采纳了：unstable 仍然没有消费方（实发 %d 趟）" % c.calls.count("generate")
    assert c.calls.count("judge") == 2 * D.JUDGE_SAMPLES, \
        "判定次数 %d 不等于『两趟 × 每趟 %d』：judge 跑到每条 claim 上去了" % (
            c.calls.count("judge"), D.JUDGE_SAMPLES)
    assert rec["regen_used"] == 1, rec.get("regen_used")
    assert not rec.get("judge_borderline"), "后面那版是稳的，不该还挂抖动旗标"


def test_all_flaky_versions_still_publish_but_say_so():
    """三轮全压在线上是常态（现网均值 0.75/0.7525 两条都这样）：照发布，但必须标出来。

    政策依据是 §10.16"停更比快讯更糟"，所以这里不许把抖动版降级成快讯；
    要付的代价是说清楚"这一版的合格线读数被噪声主导"，并且不记成功。
    """
    c = Seq(_uneven(0.66, 0.84) + _uneven(0.67, 0.83) + _uneven(0.66, 0.84))
    rec = _deepen(c)
    assert not rec.get("degraded_reason"), rec.get("degraded_reason")
    assert rec.get("judge_borderline") is True, "抖到采纳的版本没留痕：下一夜还是没人知道它发生过"
    assert rec["rubric"]["judge_spread"] > D.ADOPT_MARGIN, rec["rubric"]


def test_borderline_marker_reaches_the_page_and_the_summary():
    """旗标必须有读者：页面与播报都要吃到它，否则它又是一个只有测试看的字段。"""
    ev = {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400,
          "claims": [], "causal_chains": [], "forecasts": [], "citations": [],
          "quality": {"verdict": "一手", "score": 80, "why": "x", "basis": []},
          "judge_borderline": True,
          "rubric": {"mean": 0.75, "judge_spread": 0.18, "unstable": True}}
    html = D.render_page({"date": "2026-09-24", "events": [ev], "budget": {},
                          "anchor_diff": []})
    assert "判分极差" in html, "抖动的合格版上屏后与稳的长得一模一样"
    assert "0.18" in html, html[:600]


class JudgeEverySecondGarbage(D.FakeClient):
    """每趟双样本的第二样本吐空对象：used 恒为 1，去噪根本没做成。

    不在 judge_event_multi 那层造（那里已有 _Judge429 夹具）：这条要钉的是
    deepen_one 采纳时的取舍，必须走完整的两趟判定。
    """

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "judge" and (self.calls.count("judge") + 1) % 2 == 0:
            self.calls.append("judge")
            return "{}"
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


def _single_sample_event():
    return {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400,
            "claims": [], "causal_chains": [], "forecasts": [], "citations": [],
            "quality": {"verdict": "一手", "score": 80, "why": "x", "basis": []},
            "judge_borderline": True, "judge_single_sample": True,
            "rubric": {"mean": 0.83, "judge_samples_used": 1, "judge_spread": 0.0,
                       "unstable": False}}


def test_a_pass_judged_only_once_is_not_a_stable_pass():
    """只判成一遍时极差算不出来 ⇒ unstable 恒 False ⇒ 它曾从压线规则的缝里整个绕过。

    现网 evt_20260924_002 就是这个形状（rubric 整块为 None）。单遍读数正是批 3 要治的
    东西（同内容复评极差实测 0.17），不许因为"没有第二趟可比"就成了达标数。
    """
    c = _deepen(JudgeEverySecondGarbage())
    assert c["rubric"]["judge_samples_used"] == 1, c["rubric"]
    assert c.get("judge_borderline") is True, "单遍合格被当成稳的：压线规则只认极差"
    assert c.get("judge_single_sample") is True, c.keys()
    assert not c.get("degraded_reason"), c.get("degraded_reason")
    # 反向对照：两遍都判成的同一套夹具不许挂旗标
    ok = _deepen(D.FakeClient())
    assert ok["rubric"]["judge_samples_used"] == D.JUDGE_SAMPLES, ok["rubric"]
    assert not ok.get("judge_single_sample"), "旗标见谁挂谁"


def test_single_sample_pass_is_read_on_the_page_and_in_the_aggregate():
    """A6 的后半：达标数里剔掉它还不够，页面与聚合要说清是"哪一因"把它压线的。"""
    payload = D.build_payload([_single_sample_event()],
                              {"source_sha": "", "date": "2026-09-24"},
                              D.Budget(1000), "2026-09-24")
    b = payload["budget"]
    assert b["qualified"] == 1 and b["single_sample"] == 1, b
    assert b["qualified_stable"] == 0, "只判一遍被记成达标"
    html = D.render_page(payload)
    assert "只判成 1/2 遍" in html, html[:800]
    assert "1 条只判了一遍" in html, html[:800]
    # 反向对照：判成两遍的同一条不许出现这句话，也不许被从达标数里剔掉
    # （压线旗标本身就是单遍那因挂上的，两遍都成时它必须整个不在）
    ev = _single_sample_event()
    ev.pop("judge_single_sample")
    ev.pop("judge_borderline")
    ev["rubric"] = dict(ev["rubric"], judge_samples_used=D.JUDGE_SAMPLES)
    p2 = D.build_payload([ev], {"source_sha": "", "date": "2026-09-24"},
                         D.Budget(1000), "2026-09-24")
    assert p2["budget"]["single_sample"] == 0, p2["budget"]
    assert p2["budget"]["qualified_stable"] == 1, p2["budget"]
    h2 = D.render_page(p2)
    assert "只判成" not in h2 and "只判了一遍" not in h2, h2[:800]


def test_one_sample_losing_a_dimension_is_a_partial_not_a_kill():
    """P0-2 复现：判两遍以后，"任一趟漏维度就判死"把协议误杀从 p 抬到 1-(1-p)²。

    有一趟给到的维度就是可用的（不许当 0 分这条不变量照旧守），
    但"整条判据没跑通"只能按**所有趟都缺**来记 —— 现网 09-23 的教训是不误杀好条目。
    """
    dims = [{"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9, "density": 0.9},
            {"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9}]
    r = _judge(_cand(), dims)
    assert not r["missing_dims"], "只有一趟漏 density 就判协议失败：那是把去噪做成了加倍误杀"
    assert r["density"] == 0.9, r
    assert r.get("partial_dims") == ["density"], "缺过一趟要留痕，不然极差 0 是假稳：%r" % (r,)
    assert D.judge_accepts(r) is True


def test_every_sample_losing_a_dimension_is_still_a_kill():
    """反向控制：两趟都漏同一维 = 判据协议真的没跑通，不许放行。"""
    dims = [{"narrative": 0.9, "causal": 0.9, "forecast": 0.9, "quality": 0.9}] * 2
    r = _judge(_cand(), dims)
    assert r["missing_dims"] == ["density"], r
    assert D.judge_accepts(r) is False
    assert not r.get("partial_dims"), r


def test_stall_reason_counts_the_real_number_of_violations():
    """P0-3 复现：真违约 3 条，上屏理由写 2 条 —— 它自己指的字段就跟它矛盾。"""
    c = ShortNarrative3()
    rec = _deepen(c)
    real = len(rec.get("contract_fails") or [])
    assert real > len((rec.get("regen_stalled") or [{}])[0].get("fails") or []), \
        "夹具没造出多于截断上限的违约：这条判据就是空转"
    assert ("%d 条" % real) in (rec.get("degraded_reason") or ""), rec.get("degraded_reason")


class ShortNarrative3(D.FakeClient):
    """同一份短正文，但短到同时踩字数/段数/反证三条 —— P0-3 的形状。"""

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "generate":
            self.calls.append("generate")
            doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="structure"))
            doc["narrative"] = "论证很短。"
            doc["claims"] = [{"text": "论断%d" % i, "kind": "causal", "evidence": ["c1"]}
                             for i in range(5)]
            return json.dumps(doc, ensure_ascii=False)
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


def test_protocol_stall_is_not_reported_as_a_model_failure():
    """P1-7 复现：judge 两轮都没给维度，理由却写"违约未修掉"。

    这正是 09-23 审查 P0-1 刚修掉的误记账形状 —— 上屏那句话会把人引去改 prompt，
    而该修的是判据协议。
    """
    c = NoDensity()
    rec = _deepen(c)
    stalled = (rec.get("regen_stalled") or [{}])[0]
    assert stalled.get("kind") == "judge_proto", stalled
    reason = rec.get("degraded_reason") or ""
    assert "判据协议" in reason, reason
    assert "违约未修掉" not in reason, "把协议没跑通记成模型不接：" + reason


def test_stall_is_only_recorded_when_a_round_was_saved():
    """P1-8：最后一趟之后的"收手"没省任何东西，那笔账不许记。"""
    per = _samples([0.40, 0.50, 0.51])
    c = Seq(per)
    rec = _deepen(c)
    assert c.calls.count("generate") == 3, c.calls.count("generate")
    assert not rec.get("regen_stalled"), \
        "跑满 max_regen 还写『按预算收手』：停滞字段不再是省钱的凭据"
    assert "仍不合格" in (rec.get("degraded_reason") or ""), rec.get("degraded_reason")


def test_actionable_single_weak_dimension_is_saved_by_the_mean_band_not_a_second_rule():
    """P0-2 复核结论：单维塌到地板以下的豁免**结构性不可达**，函数已删。

    MEAN_DIMS 有四维，任何一维掉到 0.30，均值都还有 (3*0.75+0.30)/4 = 0.6375 ≥ 0.57，
    永远先被 `near_pass_line` 救走 —— 再写一条"单维可改"的豁免就是死支。
    这条判据钉的是**那个算术事实**：逐维穷举一遍，不许出现"单维塌但均值豁免不到"的形状。
    """
    for k in D.JUDGE_DIMS:
        s = {d: 0.75 for d in D.JUDGE_DIMS}
        s[k] = 0.30
        core = [s[d] for d in D.MEAN_DIMS]
        s["mean"] = sum(core) / float(len(core))
        assert D.near_pass_line(s) is True, "单维塌 %s 时均值 %s 竟然够不到豁免带：%r" % (
            k, s["mean"], s)
        assert D.no_progress(dict(s), [], dict(s), []) is False, k
    assert not hasattr(D, "_one_dimension_fixable"), "死支又被人加回来了"


def test_faith_wipeout_spends_the_remaining_rewrites():
    """P1-5 复现：核查摘空后 regen_used=0，手里还剩两轮却直接降级。

    批 2 原本会把这当"该重写的信号"，我批 3 重构时把这条路吃掉了 ——
    摘空是"论断查无支撑"，下一版按证据重写就是对症的，不该白扔正文预算。
    """
    c = AllUnsupported()
    rec = _deepen(c, staged=True)
    assert c.calls.count("faith") > D.CLAIM_MIN + 1, \
        "核查只跑了一版就收手：剩下的重写预算没花出去（faith=%d）" % c.calls.count("faith")
    assert rec.get("regen_used"), rec.get("regen_used")
    assert "核查" in (rec.get("degraded_reason") or ""), rec.get("degraded_reason")


class AllUnsupported(D.FakeClient):
    def complete(self, prompt, key=None, kind="generate"):
        self.calls.append(kind)
        if kind == "faith":
            return json.dumps({"verdict": "unsupported", "reason": "证据里没有", "quote": ""})
        return D.FakeClient.complete(self, prompt, key=key, kind=kind)


class _Judge429(object):
    """第 N 次 judge 调用抛 RateLimited 的夹具（直接在 judge_event_multi 那层测）。

    不在 deepen_one 那层造：`call_llm` 自己会按等待预算重试同一趟调用，
    客户端计数器与"第几趟"对不上，测到的就是重试策略而不是这里要钉的取舍。
    """

    def __init__(self, raise_on):
        self.raise_on = set(raise_on)
        self.n = 0

    def complete(self, prompt, key=None, kind="generate"):
        self.n += 1
        if self.n in self.raise_on:
            raise D.RateLimited(30)
        return json.dumps({d: 0.9 for d in D.JUDGE_DIMS})


def _multi(client):
    ctx = {"articles": [{"text": "证据" * 50}], "ids": {}, "signals": {}, "quality_signals": {}}
    return D.judge_event_multi(client, _cand(), ctx, D.KeyPool(["k1"]), D.Budget(400000),
                              wait_cap_s=5, sleep=lambda s: None)


def test_second_judge_sample_hitting_429_does_not_lose_the_item():
    """P1-11 复现：第二趟 judge 撞 429，整条抛出去 ⇒ 八千字正文白写、条目记 not_run。

    双采样是**本批新引入的敞口**（原来是 1 次）：去噪多问那一句不能反过来
    把已经判成的那一版一起烧掉。
    """
    r = _multi(_Judge429([2]))
    assert r["judge_samples_used"] == 1, r
    assert r["mean"] == 0.9, r
    assert r["judge_spread"] in (0, 0.0), "只有一趟作数却还算极差：那是拿一个数算方差"
    assert r["unstable"] is False, r


def test_first_judge_sample_hitting_429_still_propagates():
    """反向控制：第一趟就没 key ⇒ 照旧抛，别把饥饿咽成"这版没判"。"""
    try:
        _multi(_Judge429([1]))
        assert False, "首样本 429 被咽掉了：等待预算白设，饥饿读不出来"
    except D.RateLimited:
        pass


def test_per_attempt_cost_formula_covers_judge_and_faith():
    """P1-10：每趟成本必须等于现在真发生的调用数（提纲重问+逐段+结构+双判+逐条核查）。

    成本常量写在 SECTIONS_MAX / CLAIM_* / JUDGE_SAMPLES 之后 —— 写在它们之前就是
    导入期 NameError（批 3.5 真炸过一次，整包 15 个模块收集失败）。
    段那一档必须按 **2*SECTIONS_MAX** 算：`staged_generate` 对太短的段落补写一次，
    只算一遍就把最坏成本低估 8 次，`_cutoff` 的预留跟着形同不存在。
    """
    assert D.PER_ATTEMPT_CALLS == (D.OUTLINE_MAX_CALLS + 2 * D.SECTIONS_MAX
                                   + D.STRUCT_MAX_CALLS + D.JUDGE_SAMPLES
                                   + D.CLAIM_MAX), D.PER_ATTEMPT_CALLS
    assert D.STRUCT_MAX_CALLS == 2, (
        "结构那一趟自批 3.16 起最坏是两趟（五格全空重问一次），常量必须跟着点名；"
        "写回 1 就是每趟少留一次预留，_cutoff 照样形同不存在")
    assert D.ITEM_CALLS_MAX == (D.MAX_REGEN + 1) * D.PER_ATTEMPT_CALLS, D.ITEM_CALLS_MAX
    assert D.ITEM_CALLS_MAX <= D.CALL_CAP, \
        "一条的最坏成本比总闸还大：call_cap 就是装饰"
    assert D.CALL_CAP == 684, \
        "CALL_CAP 是 spec §7 有意不抬的档位（真实约束是墙钟），要改必须先有现网分布"
    assert D.PARAS_MIN <= D.SECTIONS_MAX, "每段下限乘段数会顶破正文上限"


def test_run_summary_counts_what_the_new_rules_saved_and_flagged():
    """停滞省了几条、抖动采纳了几条必须跨夜可比，否则"收手省钱"读出来像"这轮没干活"。"""
    bud = D.Budget(budget_tokens=400000)
    p = D.build_payload([
        {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文", "claims": [],
         "causal_chains": [], "forecasts": [], "citations": [],
         "quality": {}, "rubric": {"mean": 0.75, "judge_spread": 0.18},
         "judge_borderline": True},
        {"id": "e2", "title": "乙", "topic": "ai", "narrative": "正文", "claims": [],
         "causal_chains": [], "forecasts": [], "citations": [], "quality": {},
         "rubric": {"mean": 0.4}, "degraded_reason": "重写 1 轮后无改善",
         "regen_stalled": [{"attempt": 1, "kind": "judge"}]}],
        {"source_sha": "", "date": "2026-09-24"}, bud, "2026-09-24")
    b = p["budget"]
    assert b.get("borderline") == 1, b
    assert b.get("stalled") == 1, b


def test_garbage_judge_sample_is_never_counted_as_a_zero_score():
    """P0-2 复现：某趟 judge 返回空对象/散文被摊成 mean=0.0，极差立刻 0.9、条目挂 borderline。

    "没给任何维度"与"给了 0 分"是两码事 —— 上一批刚在维度级删掉这条不变量的误用，
    它在样本级又长回来了。编造的 0.0 还会多烧一整趟生成。
    """
    full = {d: 0.9 for d in D.JUDGE_DIMS}
    o = _judge_multi(_Judge429([]), [json.dumps(full), "{}"])
    assert o["judge_samples_used"] == 1, o
    assert o["judge_samples_garbage"] == 1, o
    assert 0.0 not in o["judge_samples"], "空样本被当成 0 分写进极差：%r" % (o["judge_samples"],)
    assert o["judge_spread"] == 0.0 and o["unstable"] is False, o
    assert D.judge_accepts(o) is True, o


def test_all_samples_garbage_is_a_protocol_failure_not_a_raise():
    """两趟都没判出东西：记"判据协议没跑通"，不许抛出去把正文扔掉，也不许记成 0 分合格。"""
    o = _judge_multi(_Judge429([]), ["{}", "{}"])
    assert o["judge_samples_used"] == 0, o
    assert sorted(o["missing_dims"]) == sorted(D.JUDGE_DIMS), o
    assert D.judge_accepts(o) is False, o


def test_single_dimension_at_zero_still_gets_a_rewrite():
    """P1-1：坏维=0.0 时均值 0.5625 落在带外 —— 上一轮我按 0.30 的穷举把这条豁免当死支删了。

    一维塌、其余过线 ⇒ `JUDGE_FIX_HINT` 点名得很具体，这一档重写有方向，不许收手。
    """
    for bad in (0.30, 0.10, 0.0):
        s = {d: 0.75 for d in D.JUDGE_DIMS}
        s["narrative"] = bad
        s["mean"] = sum(s[d] for d in D.MEAN_DIMS) / float(len(D.MEAN_DIMS))
        assert D.no_progress(dict(s), [], dict(s), []) is False, \
            "坏维 %s（mean=%s）被判成没方向，单维豁免没接回来" % (bad, s["mean"])
    # 反向控制：两维一起塌就没有单一可指的方向了
    two = {d: 0.75 for d in D.JUDGE_DIMS}
    two["narrative"] = 0.0
    two["causal"] = 0.30
    two["mean"] = sum(two[d] for d in D.MEAN_DIMS) / float(len(D.MEAN_DIMS))
    assert D.no_progress(dict(two), [], dict(two), []) is True, two


def test_hope_band_is_the_number_the_docs_promise():
    """带下沿必须等于台账写的那个 0.57，而不是 0.5700000000000001。"""
    assert D.HOPE_BAND == 0.57, repr(D.HOPE_BAND)
    assert D.near_pass_line({"mean": 0.57}) is True, "恰在带沿被挡在外面：浮点把规则削窄了一档"


def test_regen_attempts_are_counted_whether_or_not_we_stalled():
    """P1-5：采纳了兜底版又继续跑的那些趟必须在产物里能核对，不能只留 regen_used。"""
    rec = _deepen(Seq(_uneven(0.66, 0.84) + _uneven(0.66, 0.84) + _samples([0.40])
                      + _samples([0.40])), max_regen=3)
    assert rec.get("regen_attempts"), "跑了 4 趟、账上只有 regen_used=1：多烧的两趟没人知道"
    assert rec["regen_attempts"] >= 3, rec["regen_attempts"]


def _judge_multi(client, raws):
    ctx = {"articles": [{"text": "证据" * 50}], "ids": {}, "signals": {}, "quality_signals": {}}
    it = iter(raws)

    def comp(prompt, key=None, kind="generate"):
        return next(it)

    client.complete = comp
    return D.judge_event_multi(client, _cand(), ctx, D.KeyPool(["k1"]), D.Budget(400000),
                              wait_cap_s=5, sleep=lambda s: None)


def test_faith_stall_needs_the_same_claims_not_just_the_same_count():
    """P1-3：两版被摘的论断毫无关系，只报条数会撞上"同一批违约"而提前收手。

    夹具故意让每版论断内容不同（attempt 计数进 claim 文本），必须跑满 3 趟；
    反向控制在"模型每版都交同一批论断"时收手 —— 那才是真没新信息。
    """
    diff = FaithVarying()
    rec = _deepen(diff, staged=True)
    assert diff.faith_rounds >= 3, \
        "只跑了 %d 版核查就被判停滞：违约串只比条数，没比内容" % diff.faith_rounds
    assert not rec.get("regen_stalled"), rec.get("regen_stalled")


class FaithVarying(D.FakeClient):
    # 每趟交一批**内容不同**的论断（核查一律判无支撑）：违约串只比条数就会误判停滞。
    def __init__(self):
        D.FakeClient.__init__(self)
        self.round = 0
        self.faith_rounds = 0

    def complete(self, prompt, key=None, kind="generate"):
        self.calls.append(kind)
        if kind == "faith":
            self.faith_rounds += 1
            return json.dumps({"verdict": "unsupported", "reason": "查无", "quote": ""})
        if kind in ("outline", "section", "judge"):
            # 提纲/逐段/判定原样走 FakeClient：正文必须真够长，否则测到的是契约不是核查
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)
        doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="structure"))
        if kind == "structure":
            self.round += 1
            doc["claims"] = [{"text": "F%d 论断%d：%d%% 的份额在迁移" % (self.round, i, 40 + i),
                              "kind": "causal", "evidence": ["c%d" % (i % 6 + 1)]}
                             for i in range(7)]
        return json.dumps(doc, ensure_ascii=False)

def test_borderline_items_do_not_count_as_achievement():
    """A6 的后半：压线版照样发布，但不能算"这条判据救回来的功"。

    只打旗标不扣账 = 页面上"合格 8 条"里 8 条都是抖过来的（第四轮审查 P1-4）。
    """
    ev = {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400, "claims": [],
          "causal_chains": [], "forecasts": [], "citations": [], "quality": {},
          "judge_borderline": True, "rubric": {"mean": 0.75, "judge_spread": 0.18}}
    p = D.build_payload([ev], {"source_sha": "", "date": "x"}, D.Budget(400000), "d")
    assert p["budget"]["qualified"] == 1, p["budget"]
    assert p["budget"]["qualified_stable"] == 0, \
        "压线版被记成达标：A6 只做到了一半 %r" % (p["budget"],)
    html = D.render_page(p)
    assert "压线" in html, "页面写着合格 1 条，却看不出这 1 条是抖过来的"


def test_cap_overshoot_is_readable_in_the_artifact():
    """超顶不能只存在于 stdout：产物并排放 llm_calls 与 call_cap 而没人说超了。"""
    b = D.Budget(call_cap=5)
    for _ in range(9):
        b.note_call(10, 5)
    snap = b.snapshot()
    assert snap["cap_exceeded"] == 4, snap
    assert snap["llm_calls"] == 9, snap


def test_rewrite_stops_when_the_next_attempt_is_unaffordable():
    """每趟之前问一次预算：一条最坏连跑 3 趟、实测把 CALL_CAP 顶穿 72 次的形状必须被拦住。"""
    p, links = _pool()
    c = JudgeSeq([0.40, 0.40, 0.40])
    bud = D.Budget(call_cap=10, budget_tokens=400000)
    rec = D.deepen_one({"id": "x1", "title": "事件甲", "topic": "ai", "summary": "摘",
                        "links": list(links)}, p, c, bud, D.KeyPool(["k1"]),
                       max_regen=2, source_quality={}, sleep=lambda s: None,
                       wait_cap_s=5, staged=False, call_cap=10)
    assert rec.get("regen_cut_by_budget") is True, rec.get("regen_cut_by_budget")
    assert rec.get("regen_cut_reason"), rec
    assert c.calls.count("generate") < 3, \
        "付不起下一趟还在写：%d 趟" % c.calls.count("generate")


def test_stall_and_accepted_are_never_both_true():
    """钉住一条互斥：合格条目不带 regen_stalled，播报因此不需要"合格但收手"这一格。

    这条不变量不显然（压线兜底版会继续跑下一趟），而它一旦被改动，日志与页面都要跟着改；
    留个测试比留个注释可靠。
    """
    for per in (_uneven(0.66, 0.84) + _samples([0.80]),
                _uneven(0.66, 0.84) + _uneven(0.67, 0.83) + _uneven(0.66, 0.84),
                _samples([0.72, 0.73, 0.71])):
        rec = _deepen(Seq(per))
        assert not (rec.get("regen_stalled") and not rec.get("degraded_reason")), \
            "合格条目带了停滞账：regen_stalled 与 degraded_reason 的互斥被打破，%r" % (rec.get("regen_stalled"),)


def test_an_item_the_judge_never_saw_is_marked_not_judged():
    """契约没过 ⇒ 判定没跑，`rubric` 必须带 `judged=False`，不能只留一个 0.0。

    "什么都没判"与"判了 0 分"是两码事：批 3.9 刚在**样本级**修掉同一个谎（空对象被摊成
    mean 0.0），这是它在**条目级**的另一半（现网 evt_20260924_002 / evt_20260924_008）。
    """
    c = _deepen(ShortNarrative())
    assert (c.get("degraded_reason") or "").strip(), c.keys()
    assert c["rubric"].get("judged") is False, \
        "没送判定被记成 mean=0.0：读产物的人分不开这两种形状：%r" % (c["rubric"],)
    # 反向对照：判定真跑过的条目不许带这个标记
    ok = _deepen(D.FakeClient())
    assert ok["rubric"].get("judged") is not False, ok["rubric"]


def test_not_judged_item_says_so_on_the_page_instead_of_rubric_zero():
    """页面读者：`rubric 0.0` 会被读成"模型判了零分"，得印成"未送判定（契约没过）"。"""
    ev = {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400,
          "claims": [], "causal_chains": [], "forecasts": [], "citations": [],
          "quality": {"verdict": "一手", "score": 80, "why": "x", "basis": []},
          "degraded_reason": "重写 2 次仍不合格",
          "rubric": {"mean": 0.0, "judged": False}}
    html = D.render_page({"date": "2026-09-24", "events": [ev], "budget": {},
                          "anchor_diff": []})
    assert "未送判定" in html, html[:900]
    assert "rubric 0.0" not in html, "还在把'没判'印成'判了 0 分'"


def test_a_real_score_still_reaches_the_page_and_the_log():
    """反向对照：真判定值必须照样上屏，否则 `rubric_display` 改成无条件"未送判定"也没人红。

    第五轮审查 P1-3 就是这么抓到判据缺对照的：三条新判据全在断"该说什么"，
    没有一条断"该报分数时还在报分数"。
    """
    ev = {"id": "e1", "title": "甲", "topic": "ai", "narrative": "正文" * 400,
          "claims": [], "causal_chains": [], "forecasts": [], "citations": [],
          "quality": {"verdict": "一手", "score": 80, "why": "x", "basis": []},
          "rubric": {"mean": 0.8123, "judge_samples_used": 2}}
    html = D.render_page({"date": "2026-09-24", "events": [ev], "budget": {},
                          "anchor_diff": []})
    assert "0.8123" in html, html[:900]
    assert u"未送判定" not in html, "真判过的分被盖成了没判"


def test_protocol_failure_rubric_is_marked_not_judged_too():
    """所有趟都判不出东西 = 协议没跑通，同样不许印成"判了 0 分"（第五轮 P1-2 第二支）。"""
    full = {d_: 0.9 for d_ in D.JUDGE_DIMS}
    o = _judge_multi(_Judge429([]), ["{}", "{}"])
    assert o["judge_samples_used"] == 0, o
    assert o.get("judged") is False and o.get("judge_skip") == "protocol", o
    assert u"判据协议没跑通" in D.rubric_display(o), D.rubric_display(o)


def test_anchor_diff_reason_uses_the_same_not_judged_display():
    """第三个读者（锚点差集的理由串）走同一口径 —— 直接测纯函数，不靠整场跑。

    第五轮 P2-4：`keep` 那一支把 `rubric.mean` 拼进上屏理由。今天走不到
    （能 keep 的必然有真分），所以这既是防回归也是把 W5 那次改动变成**可杀**的：
    没有这条判据的话，改与不改没有任何测试会红（那叫死防御）。
    """
    anchor_events = [{"id": "e1", "title": "甲", "topic": "ai", "summary": "概述",
                      "key_links": ["https://a.test/1"]}]
    ship = [{"id": "e1", "title": "甲", "topic": "ai",
             "citations": [{"id": "c1", "url": "https://a.test/1", "source": "s"}] * 6,
             "narrative": "正文" * 4000,
             "rubric": {"mean": 0.0, "judged": False, "judge_skip": "contract"}}]
    diff = D.build_anchor_diff(anchor_events, ship, scheduled={"e1"})
    reason = " ".join(str(x.get("reason")) for x in diff)
    assert u"未送判定" in reason, reason[:300]
    assert "0.0" not in reason, "把'没判'拼进上屏理由串了：%s" % reason[:300]


class _JudgeBoom(object):
    """第 N 次判定调用抛 RuntimeError 的夹具（与 `_Judge429` 同形，只是错误种类不同）。

    不在 `deepen_one` 那层造：`call_llm` 自己会补试一次，客户端计数器与"第几趟"对不上，
    测到的会是补试策略而不是这里要钉的取舍。
    """

    def __init__(self, raise_on):
        self.raise_on = set(raise_on)
        self.n = 0

    def complete(self, prompt, key=None, kind="generate"):
        self.n += 1
        if self.n in self.raise_on:
            raise RuntimeError("Agnes HTTP 520")
        return json.dumps({d: 0.9 for d in D.JUDGE_DIMS})


def test_a_judge_sample_dying_on_5xx_does_not_lose_the_item():
    """判定第二趟撞 5xx：这一趟没判成，不许把已经写完的正文整条扔出去。

    与批 3.9 给 429 定的规矩同形（`test_second_judge_sample_hitting_429_does_not_lose_the_item`）。
    """
    o = _multi(_JudgeBoom([2]))
    assert o["judge_samples_used"] == 1, o
    assert o["judge_samples_failed"] == 1, o
    assert o["unstable"] is False, o          # 只有一趟可比，不假称抖动
    assert D.judge_accepts(o) is True, o      # 判到的那一趟照常可用，不当 0 分


def test_every_judge_sample_dying_on_5xx_still_raises():
    """但**所有趟都没判成**时必须抛出去：那是上游不可用的饥饿信号，不许咽下来当"没判"。

    咽下来的话，整夜会在"判定全挂但每条都记成快讯"的状态里静默跑完 ——
    最难发现的失败形态就是这种看起来正常收工的。
    """
    with pytest.raises(RuntimeError):
        _multi(_JudgeBoom([1, 2]))
