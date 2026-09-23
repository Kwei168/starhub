# tests/deep_insight/test_staged_generation.py
# -*- coding: utf-8 -*-
"""两段式生成（提纲 → 逐段成文）的判据。

来历：§2 要求每条洞察 2,500–4,000 字，现网单趟稳定停在 1,748 / 2,307 / 1,902 字
（run 35749459676），重写两轮不动 —— 总量配额模型不接，段配额它接。用户拍板走 A：
把"写够长"这件事拆成每段一次调用。这里钉的是新流程本身，不是"有个函数叫 staged_generate"。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _arts(n=6):
    pool, links = {}, []
    for i in range(n):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "标题%d" % i,
                   "text": "证据正文%d。" % i * 1600, "has_full": True,
                   "source_key": "src%d_%d" % (i, i)}
        links.append(u)
    return pool, links


def _anchor(links, n=1):
    return json.dumps({"date": "2026-09-23", "events": [
        {"id": "e%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "摘要",
         "key_links": list(links)} for i in range(n)]}, ensure_ascii=False)


def _run(tmp_path, client, staged=True, n_events=1):
    pool, links = _arts()
    D.night_run(purpose="test", client=client, out_dir=str(os.path.join(str(tmp_path), "ns")),
                keys=["k1"], anchor_raw=_anchor(links, n_events), pool=pool,
                date_str="2026-09-23", pred_raw="", quality_raw={},
                get=lambda url, timeout=90: b"", log=lambda s: None,
                sleep=lambda s: None, staged=staged, call_cap=500, events_limit=n_events)
    p = os.path.join(str(tmp_path), "ns", "daily-deep-2026-09-23.json")
    return json.load(open(p, encoding="utf-8"))


def _doc(client_cls=D.FakeClient, **kw):
    return json.loads(client_cls().complete("证据编号里选：c1, c2, c3", kind="generate"))


# ── 流程本身 ──────────────────────────────────────────────────────────────

def test_narrative_is_written_one_section_at_a_time(tmp_path):
    """正文必须来自"一段一次调用"，而不是又一次单趟：这是 A 方案的全部要点。"""
    c = D.FakeClient()
    doc = _run(tmp_path, c)
    kinds = [k for k in c.calls]
    assert kinds.count("outline") >= 1, "没走提纲这一步：%s" % kinds[:8]
    assert kinds.count("section") >= D.PARAS_MIN, \
        "逐段成文只发了 %d 次，段数没真的一段落：" % kinds.count("section")
    assert kinds.count("judge") >= 1, "两段式之后判定被绕过了：%s" % kinds
    ev = doc["events"][0]
    paras = [p for p in (ev["narrative"] or "").split("\n\n") if p.strip()]
    assert len(paras) >= D.PARAS_MIN, "拼出来的正文只有 %d 段" % len(paras)
    assert all(D.count_chars(p) >= D.PARA_MIN for p in paras), \
        "有段落低于每段下限：%s" % [D.count_chars(p) for p in paras]
    assert D.count_chars(ev["narrative"]) >= D.NARR_MIN, \
        "两段式之后字数仍够不到 §2 下限：%d" % D.count_chars(ev["narrative"])


def test_single_pass_flag_reaches_the_old_path(tmp_path):
    """成本要能一键退回：`--single-pass` 之后不许再出现 outline/section 调用。"""
    c = D.FakeClient()
    doc = _run(tmp_path, c, staged=False)
    assert "outline" not in c.calls and "section" not in c.calls, c.calls[:8]
    assert c.calls.count("generate") >= 1
    assert D.count_chars(doc["events"][0]["narrative"]) > 0


def test_short_section_gets_one_more_shot_and_keeps_the_longer_one(tmp_path):
    """短段必须**在本趟内**补一次，且留长的那版。

    不能只看"section 调用总数 > 段数"：整篇重写也会加调用数，那样这条判据会被
    无关机制满足（第一版我就是这么被骗过去的）。所以数的是"第二次提纲之前"的段调用数 ——
    只有段内重试会抬高它。
    """
    class Shy(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.section_n = 0

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "section":
                self.section_n += 1
                if self.section_n == 1:      # 本趟第一段先写短，之后都写够
                    # 自己 return 就绕过了父类的 calls.append —— 那就变成"数漏了自己的桩"，
                    # 判据会从"没补写"错报成"补写了 6 次"。记账必须跟正常路径一致。
                    self.calls.append("section")
                    return "这一段先写短。但该判断仍受样本量与统计口径限制。"
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    c = Shy()
    doc = _run(tmp_path, c)
    kinds = c.calls
    assert "outline" in kinds, kinds[:8]
    second = [i for i, k in enumerate(kinds) if k == "outline"]
    upto = second[1] if len(second) > 1 else len(kinds)
    in_pass1 = kinds[:upto].count("section")
    assert in_pass1 >= D.PARAS_MIN + 1, \
        "本趟内没给短段补写（第 1 趟只有 %d 次段调用，短段 1 个）：%s" % (in_pass1, kinds[:14])
    ev = doc["events"][0]
    assert all(D.count_chars(p) >= D.PARA_MIN for p in ev["narrative"].split("\n\n") if p.strip()), \
        "补写后仍有段落低于下限：%s" % [D.count_chars(p) for p in ev["narrative"].split("\n\n")]
    assert (ev.get("staged") or {}).get("sections"), ev.get("staged")
    assert not (ev.get("staged") or {}).get("short_sections"), \
        "补写之后仍被记为短段：%s" % ev.get("staged")


def test_outline_without_sections_falls_back_instead_of_emptying(tmp_path):
    """提纲没给够 sections 时不许把整条打成 0 字。

    sections 是新流程里唯一没有契约兜底的中间产物（validate 只看最终字段），
    所以"提纲跑出一坨没有 sections 的 JSON"必须显式退回单趟，而不是静默空转。
    """
    class NoSections(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                return json.dumps({"claims": [], "sections": []}, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    c = NoSections()
    doc = _run(tmp_path, c)
    ev = doc["events"][0]
    assert c.calls.count("generate") >= 1, "退回单趟的那次调用没发生：%s" % c.calls[:8]
    assert D.count_chars(ev["narrative"]) > 0, "提纲空转把正文打成了 0 字"
    assert (ev.get("staged") or {}).get("fell_back") is True, ev.get("staged")


# ── 提示词形状 ────────────────────────────────────────────────────────────

def _ctx():
    arts, links = _arts()
    lst = list(arts.values())
    return {"articles": lst, "ids": {u: "c%d" % (i + 1) for i, u in enumerate(links)},
            "dropped": [], "total_tokens": 0, "total_chars": 0, "quality_signals": {}}


def test_outline_prompt_asks_for_sections_not_prose():
    ctx = _ctx()
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": []}
    o = D.build_prompt(ev, ctx, mode="outline")
    f = D.build_prompt(ev, ctx)
    assert "- sections：" in o, "提纲那趟没要 sections"
    assert "成文论述" not in o, "提纲那趟还在要求写正文，等于没拆"
    assert "不要写正文" in o
    assert '"sections"' not in f and "- narrative：" in f, "full 模式被顺手改坏了"
    for fld in D.OUTLINE_FIELDS:
        assert fld in o, "字段清单漏了 %s" % fld
    assert "narrative" not in o.split("字段必须是")[1].split("\n")[0], \
        "提纲那趟的字段清单里仍有 narrative，模型会照旧一次写完"


def test_section_prompt_carries_only_the_cited_evidence():
    """逐段调用如果每次都重发整包证据，成本就是段数倍（实测单趟输入 ~52k token/事件）。

    这条判据钉的是"本段只用它引用的那几条"，不是某个过滤函数存在。
    """
    ctx = _ctx()
    sec = {"title": "供给端", "focus": "论证供给约束", "evidence": ["c3"]}
    p = D.build_section_prompt({"title": "t", "topic": "ai"}, ctx, sec, 3, 6)
    assert "证据 c3" in p, "本段引用的证据没进去：%s" % p[:200]
    assert "证据 c1" not in p and "证据 c5" not in p, "整包证据被原样重发，成本按段数放大"
    assert "第 3/6 段" in p
    assert ("不少于 %d 字" % D.PARA_MIN) in p, "每段下限没写进段提示"
    assert "不要 JSON" in p, "没约束返回形状，段正文会变成字典字面量上屏"


def test_regeneration_feedback_reaches_the_outline_call(tmp_path):
    """重写那轮的"不合格原因"必须跟着进提纲那趟调用。

    两段式里生成入口换成了 staged_generate；反馈如果只拼在旧的 full prompt 上，
    重写就是原样再跑一遍 —— §2 的"按薄弱维度重生成"会静默失效。
    """
    class FailOnce(D.FakeClient):
        """第一轮把每段都写短（总长掉到下限以下），第二轮才写够。

        要测的正是"第二轮那趟提纲有没有带上失败原因" —— 如果反馈只拼在旧的 full
        prompt 上，两段式的重写就是原样再跑一遍。
        """

        def __init__(self):
            D.FakeClient.__init__(self)
            self.outline_prompts = []
            self.short = True

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.outline_prompts.append(prompt)
                if len(self.outline_prompts) > 1:
                    self.short = False
                return json.dumps({
                    "sections": [{"title": "第%d段" % (i + 1),
                                  "focus": "论证第%d个环节，并给出反证与口径限制" % (i + 1),
                                  "evidence": ["c1"]} for i in range(D.PARAS_MIN)],
                    "claims": [], "causal_chains": [], "forecasts": [],
                    "quality": {}, "citations": []}, ensure_ascii=False)
            if kind == "section" and self.short:
                return "这一段先写短。但该判断仍受样本量与统计口径限制。"
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    c = FailOnce()
    _run(tmp_path, c)
    assert len(c.outline_prompts) >= 2, "提纲没被重跑：%d" % len(c.outline_prompts)
    assert "不合格原因" in c.outline_prompts[1], \
        "第二轮提纲调用没带上失败原因：%s" % c.outline_prompts[1][-160:]


# ── 成本形状 ──────────────────────────────────────────────────────────────

def test_default_call_cap_fits_the_two_stage_cost(tmp_path):
    """每条事件的调用数从 2 次涨到 ~8 次，旧的 80 次上限只够 10 条。

    默认上限如果没跟着改，夜场会在半夜把剩余条目记 not_run —— 那是"计划里 12 条、
    线上 10 条"这种最容易伪装成正常的降级。
    """
    per_event = 1 + D.PARAS_MIN + 1
    import argparse
    ap_src = open(os.path.join(ROOT, "build_deep_insight.py"), encoding="utf-8").read()
    i = ap_src.find('"--cap-calls"')
    assert i > 0
    default = int(ap_src[i:i + 120].split("default=")[1].split(",")[0].split(")")[0])
    assert default >= 12 * per_event, \
        "--cap-calls 默认 %d，撑不住 12 条 × %d 次/条 = %d" % (default, per_event, 12 * per_event)


def test_cli_defaults_to_two_stage(tmp_path, monkeypatch):
    """命令行默认必须带两段式：CI 跑的就是这条命令，默认若是 False，上线的还是旧单趟。

    变异自检发现：`night_run(staged=True)` 改成 False 时全套原本都是绿的 —— 因为测试
    与 main() 都显式传参，没有任何一处验证"默认"。
    """
    seen = {}

    class Stop(Exception):
        pass

    def spy(*a, **kw):
        # 只关心命令行往 night_run 传了什么；真跑一趟要联网读锚点，与这条判据无关
        seen["staged"] = kw.get("staged", "MISSING")
        raise Stop()

    monkeypatch.setattr(D, "night_run", spy)
    monkeypatch.setattr(D, "env_keys", lambda: ["k1"])
    with pytest.raises(Stop):
        D.main(["--purpose", "test", "--events-limit", "1", "--out",
                os.path.join(str(tmp_path), "cli"), "--fake-client"])
    assert seen.get("staged") is True, \
        "命令行默认没把两段式带上：%s" % seen.get("staged")


def test_night_run_default_is_two_stage(tmp_path):
    """`night_run` 省略 staged 时必须走提纲（默认值本身要活着，不是装饰）。"""
    pool, links = _arts()
    c = D.FakeClient()
    D.night_run(purpose="test", client=c, out_dir=str(os.path.join(str(tmp_path), "dflt")),
                keys=["k1"], anchor_raw=_anchor(links), pool=pool, date_str="2026-09-23",
                pred_raw="", quality_raw={}, get=lambda url, timeout=90: b"",
                log=lambda s: None, sleep=lambda s: None, call_cap=500, events_limit=1)
    assert "outline" in c.calls, "省略 staged 时走了单趟：%s" % c.calls[:6]


def test_single_pass_cli_switch_reaches_the_generator(tmp_path, monkeypatch):
    """`--single-pass` 是成本阀门，它必须真能把提纲关掉（否则是个装饰）。"""
    seen = {}

    class Stop(Exception):
        pass

    def spy(*a, **kw):
        seen["staged"] = kw.get("staged", "MISSING")
        raise Stop()

    monkeypatch.setattr(D, "night_run", spy)
    monkeypatch.setattr(D, "env_keys", lambda: ["k1"])
    with pytest.raises(Stop):
        D.main(["--purpose", "test", "--events-limit", "1", "--out",
                os.path.join(str(tmp_path), "off"), "--fake-client", "--single-pass"])
    assert seen.get("staged") is False, "--single-pass 没传到 night_run：%s" % seen


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
