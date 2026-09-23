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
    assert ("%d-%d 字" % (D.PARA_MIN, D.PERA_MAX)) in p, "每段没给区间内目标（只报下限会被写成 1,100 字/段）"
    assert "不要 JSON" in p, "没约束返回形状，段正文会变成字典字面量上屏"


def test_section_quota_multiplies_into_the_hard_range():
    """每段的配额必须"乘得回"§2 的硬区间，否则两段式只是把超限从偶发变成必然。

    现网第一轮就是这样的：段数与每段下限都满足了，6 段 × 700~1,100 字 = 4.3k~7k，
    evt_008 写到 6,950 字被上限整条作废（run 35801635817）。
    """
    assert D.PARA_MIN < D.PERA_MAX, "每段下限不小于上限，配额无解"
    assert D.PARAS_MIN * D.PERA_TARGET >= D.NARR_MIN, \
        "照目标写完仍够不到下限：%d×%d" % (D.PARAS_MIN, D.PERA_TARGET)
    assert D.PARAS_MIN * D.PERA_MAX <= D.NARR_MAX, \
        "每段都顶到上限就必然超线：%d×%d > %d" % (D.PARAS_MIN, D.PERA_MAX, D.NARR_MAX)


def test_assembly_never_ships_more_than_the_ceiling(tmp_path):
    """组装必须守住上限，而且只能整段丢 —— 截半句等于把论述切成两截。

    夹具是 8 段 × ~600 字 = 4,800 字：不裁就超上限，裁完剩 6 段 3,600 字仍在硬区间内，
    这样"整段丢弃"与"降级截断"两种结局能分得开（6 段 × 1,200 字那种夹具只会掉进降级，
    截断后什么断言都测不到东西）。
    """
    verbose = "长。但该判断仍受样本量与统计口径限制。" + "句" * 580

    class Verbose(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                self.calls.append("outline")
                # 结构字段得给真的：留空会让这条因为 claims=0 不合格而降级，
                # 于是测到的是"结构契约"而不是"裁切"，两件事会互相掩护。
                base = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="generate"))
                base.pop("narrative", None)
                base["sections"] = [{"title": "第%d段" % (i + 1), "focus": "论证%d" % (i + 1),
                                     "evidence": ["c1"]} for i in range(D.PARAS_MIN + 2)]
                return json.dumps(base, ensure_ascii=False)
            if kind == "section":
                self.calls.append("section")
                return verbose
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    doc = _run(tmp_path, Verbose())
    ev = doc["events"][0]
    st = ev.get("staged") or {}
    n = D.count_chars(ev["narrative"])
    assert not ev.get("degraded_reason"), "这条本该合格，掉进降级就测不到裁切：%r" % ev["degraded_reason"]
    assert n <= D.NARR_MAX, "组装后仍超上限 %d > %d（trimmed 账=%r）" % (n, D.NARR_MAX, st)
    assert st.get("trimmed_sections"), "超了却没记账：%s" % st
    paras = ev["narrative"].split("\n\n")
    assert len(paras) == st["sections"] - st["trimmed_sections"], \
        "留下的段数与记账对不上：留 %d，账 %s" % (len(paras), st)
    assert all(p == verbose for p in paras), \
        "留下的段落不是整段原样（被截断或改写过）：%r" % [len(p) for p in paras]
    assert len(paras) >= D.PARAS_MIN, "裁完连段数下限都不够了：%d" % len(paras)


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
    """每条事件的调用数从 ~2 次涨到最坏 ~20 次，上限必须跟着改，且只能有一个真值。

    现网实测：3 条 50 次调用（run 35801635817）≈ 17 次/条，最坏情况还要加上每段补写一次。
    旧默认 80 只够 10 条，会在半夜把剩下的条目记成 not_run —— 那是"计划 12 条、线上 10 条"
    这种最容易伪装成正常的降级。以前 CLI / night_run / Budget 各写一份 80，
    改默认必然漏两处，所以这里判的是"只剩一处"。
    """
    src = open(os.path.join(ROOT, "build_deep_insight.py"), encoding="utf-8").read()
    per_event_worst = 1 + 2 * D.SECTIONS_MAX + 1        # 提纲 + 每段最多两次 + 判定
    assert D.CALL_CAP >= 12 * per_event_worst, \
        "上限 %d 撑不住 12 条 × 最坏 %d 次/条" % (D.CALL_CAP, per_event_worst)
    assert src.count("call_cap=80") + src.count("default=80") == 0, \
        "还有写死的 80：CLI 与函数默认会各说各话"
    for needle in ("call_cap=CALL_CAP, time_cap_s", "call_cap=CALL_CAP, keys=None",
                   "default=CALL_CAP", "call_cap=CALL_CAP, stopped_by_cap"):
        assert needle in src, "上限没收敛到一处，缺 %r" % needle
    i = src.find('"--cap-calls"')
    assert i > 0 and "default=CALL_CAP" in src[i:i + 120], "命令行默认没跟着常量"
    assert D.can_publish([{"id": "a"}, {"id": "b"}], [{"id": "a"}]) is False, \
        "未撞上限的半成品仍被放行：can_publish 的默认值不是这个常量"


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


def test_structure_contract_lives_in_one_place_and_not_in_the_outline():
    """结构契约只写一份，并且提纲那趟不许再背它。

    两段式拆完之后，"单趟"与"结构那趟"共用同一段要求文字。复制两份的后果本仓已经
    付过学费（改了常量忘改文案）：所以这里既判"两边都有"，也判"两边逐字一致"。
    """
    ctx = _ctx()
    ev = {"title": "t", "topic": "ai", "summary": "s", "links": []}
    full = D.build_prompt(ev, ctx)
    struct = D.build_structure_prompt(ev, ctx, "已经写好的正文若干字")
    outline = D.build_prompt(ev, ctx, mode="outline")
    for tok in ("claims：", "causal_chains：", "forecasts：", "quality：", "citations："):
        assert tok in full and tok in struct, "%s 从某一趟里消失了" % tok
        assert tok not in outline, "提纲那趟又背上了结构字段：%s" % tok
    a = full.split("claims：")[1][:200]
    b = struct.split("claims：")[1][:200]
    assert a == b, "两份结构契约开始漂移：改一处会漏另一处"
    assert "已经写好的正文若干字" in struct, "结构那趟看不到正文，机制链只能凭提纲猜"


def test_structure_call_happens_after_the_text_is_assembled(tmp_path, monkeypatch):
    """调用顺序必须是 提纲 → 逐段 → 结构，而且结构那趟要看得见外证清单。

    `basis` 只能引 `sig:cN`；这串编号是 `signals_note` 拼在提示尾部的。顺序反过来、
    或者结构那趟没带 signals，模型就只能在没见过的编号里猜 —— 而 FakeClient 会用
    正则兜底，本地照样绿，所以必须直接断结构提示里真有那份清单。
    """
    seen = {"kinds": [], "struct": ""}
    inner = D.FakeClient()

    class Spy:
        def complete(self, prompt, key=None, kind="generate"):
            seen["kinds"].append(kind)
            if kind == "structure":
                seen["struct"] = prompt
            return inner.complete(prompt, key=key, kind=kind)

    _run(tmp_path, Spy())
    kinds = seen["kinds"]
    assert "structure" in kinds, "结构字段那趟没发生：%s" % kinds[:12]
    assert kinds.index("structure") > kinds.index("section"), "结构先于正文：%s" % kinds[:12]
    assert kinds.count("outline") == 1 and kinds.count("structure") == 1, kinds[:14]
    # 断一个只可能来自"外证清单"的编号：契约文字里自带 sig:c1 当例子，
    # 只断 "sig:c" 会在清单被删掉时照样绿（S5 变异体就是这么骗过第一版的）。
    assert "sig:c5" in seen["struct"], \
        "结构那趟没带优质判定外证清单，basis 只能凭空编号：%r" % seen["struct"][-260:]


def test_missing_structure_fields_are_accounted_for(tmp_path):
    """结构那趟跑空时不许静默：`struct_missing` 要指名缺哪几项。

    记账点必须在归一之后：现网 evt_20260923_010 的 `staged.struct_missing` 是 []，
    而产物里 `quality` 是空的 —— 因为字段是被 `normalize_candidate` 掏空的，
    归一之前数当然"什么都不缺"。
    """
    class NoStruct(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "structure":
                self.calls.append("structure")
                return json.dumps({"notes": "我不想给字段"}, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    doc = _run(tmp_path, NoStruct())
    ev = doc["events"][0]
    assert set(ev.get("struct_missing") or []) >= {"claims", "causal_chains", "quality"}, \
        "结构跑空却没记账，事后只能看到一句 0 条：%s" % ev.get("struct_missing")


def _lumpy_quality_client():
    """结构那趟把 quality 写成数组 —— 现网 evt_20260923_010 的真实形状。"""
    class Lumpy(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "structure":
                doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind=kind))
                doc["quality"] = ["一手报道", "深度稿"]
                return json.dumps(doc, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    return Lumpy()


def test_quality_squeezed_out_by_normalizer_counts_as_missing(tmp_path):
    """"给了但形状不对"比"没给"更骗人：归一之前它明明在，归一之后是空的。

    现网 evt_20260923_010 的 `staged.struct_missing` 是 []，同一份产物里 `quality` 却是 {}，
    两处读数互相打脸 —— 记账点只有挪到归一之后才说得出真话。
    """
    ev = _run(tmp_path, _lumpy_quality_client())["events"][0]
    assert ev["quality"] == {}, "形状不对的 quality 不该原样上线：%r" % (ev["quality"],)
    assert "quality" in (ev.get("struct_missing") or []), \
        "被归一掏空的字段没记账，事后读起来像'模型给了是我们没用'：%s" % ev.get("struct_missing")
    assert ev.get("degraded_reason"), "quality 是空壳却过了契约：%s" % ev.get("contract_fails")


def test_dropped_quality_shape_is_echoed_into_the_artifact(tmp_path):
    """掏空之前留一份原样，否则"我们丢了"会被下一跑读成"模型没写"。"""
    ev = _run(tmp_path, _lumpy_quality_client())["events"][0]
    assert "一手报道" in (ev.get("quality_echo") or ""), \
        "quality 被丢弃却没留原样：%r" % ev.get("quality_echo")


def test_structure_feedback_reaches_the_structure_call(tmp_path):
    """重写轮的失败原因必须也进结构那趟。

    只把反馈拼给提纲，等于结构字段的所有违约（horizon_days=90、quality.why 超长）
    都要靠"再赌一次同样的形状"来修 —— 现网 run 35806236237 就是这样两轮白烧。
    """
    seen = {"struct": []}
    inner = D.FakeClient()

    class BadOnce:
        def complete(self, prompt, key=None, kind="generate"):
            if kind == "structure":
                seen["struct"].append(prompt)
                if len(seen["struct"]) == 1:
                    return json.dumps({
                        "claims": inner.complete(prompt, key, "structure") and [
                            {"text": "论断%d" % i, "kind": "causal", "evidence": ["c1"]}
                            for i in range(4)],
                        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                                           "confidence": 0.6, "evidence": ["c1"]} for _ in range(3)],
                        "forecasts": [{"claim": "预计下季度", "horizon_days": 90,
                                       "check_metric": "竞品发布数>=3"}],
                        "quality": {"verdict": "一手", "score": 85, "why": "合" * 150,
                                    "basis": ["sig:c1"]},
                        "citations": [{"id": "c%d" % (i + 1)} for i in range(6)]},
                        ensure_ascii=False)
            return inner.complete(prompt, key=key, kind=kind)

        def __getattr__(self, n):
            return getattr(inner, n)

    _run(tmp_path, BadOnce())
    assert len(seen["struct"]) >= 2, "结构那趟没被重跑：%d" % len(seen["struct"])
    assert "不合格原因" in seen["struct"][1], \
        "第二轮结构调用没带上失败原因：%r" % seen["struct"][1][-160:]
    assert "horizon_days" in seen["struct"][1], \
        "点名了原因却没提到违约字段：%r" % seen["struct"][1][-200:]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
