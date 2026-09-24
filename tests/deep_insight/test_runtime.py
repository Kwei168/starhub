# tests/deep_insight/test_runtime.py
# -*- coding: utf-8 -*-
"""运行时核心：KeyPool 调度、等待预算、锚点装载、上下文提示词。

替身纪律（本会话被咬过两次）：替身不许比生产宽松。
- FakeClock 只替时间，不替语义；
- 429 必须带 retry_after 语义；
- 断言 snapshot 里不出现 key 值本身（防把密钥印进日志）。
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def _pool(n=3, clock=None, workers=1):
    return D.KeyPool(["k%d" % i for i in range(n)], clock=clock or FakeClock(), workers=workers)


# ── KeyPool ───────────────────────────────────────────────────────────────

def test_each_key_is_handed_out_once_until_released():
    p = _pool(3)
    k1 = p.acquire("generate")
    k2 = p.acquire("generate")
    assert k1 and k2 and k1 != k2, "同一 key 被并发派发两次（免费池并发上限正是脆弱点）"
    assert p.acquire("generate") and p.acquire("generate") is None


def test_429_puts_key_in_cooldown_and_it_is_not_dispatched():
    clock = FakeClock()
    p = _pool(2, clock)
    k = p.acquire("generate")
    p.release(k)
    p.mark_429(k, retry_after=45)
    got = p.acquire("generate")
    assert got and got != k, "刚被限流的 key 立刻又被派发 —— 冷却等于没做"
    clock.advance(30)
    assert p.acquire("generate") is None or p.snapshot()["cooling"] >= 0
    clock.advance(20)
    assert p.acquire("generate") == k or p.acquire("generate")


def test_all_keys_cooling_returns_none_so_caller_waits():
    p = _pool(2)
    a = p.acquire("generate")
    b = p.acquire("generate")
    p.mark_429(a, retry_after=60)
    p.mark_429(b, retry_after=60)
    assert p.acquire("generate") is None, "全池限流时不该继续发任务"


def test_release_makes_key_reusable():
    p = _pool(1)
    k = p.acquire("generate")
    assert p.acquire("generate") is None
    p.release(k)
    assert p.acquire("generate") == k


def test_judge_waits_for_spare_capacity():
    """并发>1 时优先级 生成 > 判定：只剩 1 个空 key 时 judge 不许把它抢走，否则生成饿死。

    夹具从"2 key + workers=2"改成"3 key + workers=3"：`clamp_workers` 现在会把
    并发档钉在 key 数 - 1（给 judge 留一把），2 key 的配置已经构造不出" lanes>1 且
    只剩 1 空"的状态了。
    """
    p = _pool(3, workers=3)
    assert p.workers == 2
    a = p.acquire("generate")
    b = p.acquire("generate")
    assert p.acquire("judge") is None, "只剩一个空 key 就让 judge 抢占"
    p.release(a)
    p.release(b)
    assert p.acquire("judge"), "两个 key 都空时 judge 应能拿到"


def test_judge_reservation_only_applies_under_concurrency():
    """并发 1 时没有任何生成任务会被 judge 抢走，那条保留反而把单 key 部署锁死：
    永远凑不到 2 个空 key ⇒ 每条等满 wait_cap ⇒ 整场零合格。"""
    p = _pool(1)
    assert p.workers == 1
    a = p.acquire("generate")
    p.release(a)
    assert p.acquire("judge") is not None, "并发 1 时 judge 不该被保留位挡住"


def test_snapshot_never_leaks_key_values():
    p = _pool(3, FakeClock())
    p.acquire("generate")
    snap = p.snapshot()
    dumped = json.dumps(snap, ensure_ascii=False)
    assert "k0" not in dumped and "k1" not in dumped, "snapshot 把 key 原值带出去了"
    assert snap["keys_total"] == 3 and snap["busy"] == 1


# ── Budget：等待与失败分账 ────────────────────────────────────────────────

def test_wait_time_is_not_counted_as_failure():
    """等待与失败分账。记账规则：note_429(retry_after) 已把冷却窗口计入 wait，
    调用方 sleep 后**不再**重复 note_wait，否则同一秒会被算两次。"""
    b = D.Budget(call_cap=80)
    b.note_wait(300)
    b.note_429(retry_after=30)
    assert b.over_cap() is False, "等待/限流被算成失败预算 ⇒ 会误报 not_run"
    snap = b.snapshot()
    assert snap["wait_s"] == 330 and snap["c429"] == 1, snap


def test_call_cap_only_trips_above_the_cap():
    b = D.Budget(call_cap=3)
    for _ in range(3):
        b.note_call(100, 50)
    assert b.over_cap() is False
    b.note_call(100, 50)
    assert b.over_cap() is True
    assert b.snapshot()["llm_calls"] == 4
    assert b.snapshot()["input_tokens"] == 400 and b.snapshot()["output_tokens"] == 200


# ── 锚点装载 ──────────────────────────────────────────────────────────────

def _anchor_json(n=3):
    return json.dumps({"date": "2026-09-22", "events": [
        {"id": "evt%d" % i, "title": "标题%d" % i, "topic": "ai",
         "summary": "s", "key_links": ["https://a.test/%d" % i, "https://b.test/%d" % i]}
        for i in range(n)]}, ensure_ascii=False)


def test_anchor_events_are_loaded_with_stable_ids():
    got = D.load_anchor_events(_anchor_json(3), source_sha="deadbeef")
    assert [e["id"] for e in got["events"]] == ["evt0", "evt1", "evt2"]
    assert got["source_sha"] == "deadbeef"
    assert got["events"][0]["links"][0].startswith("https://")


def test_empty_anchor_is_a_hard_error_not_a_quiet_run():
    """0 个事件必须抛错：静默跑完会发出一个空报告页，比不发布更糟。"""
    with pytest.raises(ValueError):
        D.load_anchor_events('{"events": []}')


def test_anchor_tolerates_missing_fields():
    got = D.load_anchor_events('{"events": [{"id": "e1", "title": "只有标题"}]}')
    assert got["events"][0]["links"] == []
    assert got["events"][0]["topic"] == ""


# ── 提示词与上下文：整篇给，不许再切一刀 ──────────────────────────────────

def _ctx():
    arts = [{"url": "https://a.test/1", "source": "公众号:A", "title": "长文一",
             "text": "甲" * 5706},
            {"url": "https://b.test/2", "source": "行业媒体:B", "title": "长文二",
             "text": "乙" * 4200}]
    c = D.assemble_context(arts, budget_tokens=D.DEFAULT_BUDGET_TOKENS)
    c["ids"] = {"c1": arts[0]["url"], "c2": arts[1]["url"]}
    return c


def test_prompt_carries_whole_articles():
    """白天 body[:800] 那一刀不能在这里复活：整篇必须在 prompt 里。"""
    ev = {"id": "evt1", "title": "标题", "topic": "ai", "links": ["https://a.test/1"]}
    p = D.build_prompt(ev, _ctx())
    assert p.count("甲") >= 5706, "长文一被截断"
    assert p.count("乙") >= 4200, "长文二被截断"


def test_prompt_demands_the_four_depth_criteria_and_json_shape():
    ev = {"id": "evt1", "title": "标题", "topic": "ai", "links": []}
    p = D.build_prompt(ev, _ctx())
    for token in ("narrative", "claims", "causal_chains", "forecasts", "horizon_days",
                  "check_metric", "quality", "citations"):
        assert token in p, "提示词没要求字段 %s" % token
    assert str(D.NARR_MIN) in p and str(D.NARR_MAX) in p, "提示词没写每条目字数区间（应当从常量渲染）"
    assert "至少 %d 段" % D.PARAS_MIN in p, "提示词没写段数下限"
    # 只写字段名不够：枚举值必须写出来，否则模型永远可以给出永不到期的预测
    assert "3、7 或 14" in p, "提示词没限定 horizon_days 只能是 3/7/14"
    # 引用条数区间必须写出来，但**下界不再写死 "5-12"**：它按池子能给出的篇数与最长正文
    # 派生（写死就是把"模型照下界交卷、长文却被自己的长度判死"当成正确形状钉住）。
    # 本夹具只有 2 篇证据 ⇒ 合法下界只能是 2：`cite_floor = min(CITE_MIN, supply)`，
    # 要求超出池子供给就是造一条满足不了的要求（判据自己也不查）。
    _ctx_ = _ctx()
    _m = re.search(u"citations：([0-9]+)-([0-9]+) 条", D.build_prompt(ev, _ctx_))
    assert _m, "提示词没写引用条数区间"
    _sup = len(_ctx_.get("articles") or [])
    assert min(D.CITE_MIN, _sup) <= int(_m.group(1)) <= D.CITE_MAX, _m.groups()
    assert int(_m.group(2)) == D.CITE_MAX, _m.groups()
    assert "但" in p and "限制" in p, "提示词没要求反证或限制条件"
    assert "不得补充证据之外" in p, "提示词没约束模型只依据给定证据"


def test_prompt_lists_evidence_ids_the_contract_will_check():
    """引用 id 必须由提示词给出，否则模型只能瞎编，validate 就会全判假链接。"""
    ev = {"id": "evt1", "title": "标题", "topic": "ai", "links": []}
    p = D.build_prompt(ev, _ctx())
    assert "c1" in p and "c2" in p
