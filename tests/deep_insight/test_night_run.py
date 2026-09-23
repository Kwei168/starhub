# tests/deep_insight/test_night_run.py
# -*- coding: utf-8 -*-
"""夜场编排：全文池、429 重试、判定回环、checkpoint、发布闸。

替身纪律同 test_runtime：FakeGet/FakeApi 都按真 API 的语义报错（404 就抛、
CAS 父不符就返回 False），不给任何"宽松通过"。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D


def _ok_get(url, timeout=90):
    body = json.dumps({"sources": [{"key": "s1", "items": [
        {"title": "t", "link": "https://a.test/1", "source": "src0", "full_content": "内" * 6000},
        {"title": "t2", "link": "https://b.test/2", "source": "src1", "full_content": "内" * 6000},
        {"title": "t3", "link": "https://c.test/3", "source": "src2", "full_content": "内" * 6000}]}]})
    return ("window.x = " + body + ";").encode("utf-8")


def _chunk_js(items):
    return "window.rssData = " + json.dumps({"sources": [{"key": "s1", "items": items}]}) + ";"


def _art_item(url, src, body):
    return {"title": "T " + url, "link": url, "source": src, "summary": "摘要",
            "full_content": body, "pub_date": "2026-09-22T10:00:00Z"}


def _anchor(links):
    return json.dumps({"date": "2026-09-22", "events": [
        {"id": "evt1", "title": "事件一", "topic": "ai", "summary": "概述",
         "key_links": links}]}, ensure_ascii=False)


def _pool_articles(n_src=3, long_each=6000):
    pool, links = {}, []
    for i in range(n_src):
        u = "https://s%d.test/a%d" % (i, i)
        pool[u] = {"url": u, "source": "src%d" % i, "title": "t", "text": "内" * long_each,
                   "has_full": True}
        links.append(u)
    return pool, links


def test_parse_chunk_handles_dict_and_list_shapes():
    doc = D.parse_chunk(_chunk_js([_art_item("https://a.test/1", "公众号:A", "正" * 200)]))
    assert doc[0]["url"] == "https://a.test/1" and len(doc[0]["text"]) >= 200
    plain = D.parse_chunk("window.x = " + json.dumps([{"link": "https://b.test/1",
                                                       "title": "t", "s": "摘要"}]) + ";")
    assert plain[0]["url"] == "https://b.test/1", "两种分块形态必须归一成同一种条目形态"
    assert plain[0]["text"] == "摘要" and plain[0]["has_full"] is False


def test_slug_keywords_rescue_translated_titles():
    """事件标题是翻译过的中文，英文原标题藏在 reddit/HN 的 URL slug 里。

    只用事件标题取词时，现网 12 个事件全部门槛不过（实测）—— 这条判据就是钉住
    "从链接 slug 与摘要取词"这件事，不许退回只看标题。
    """
    pool = {"https://s9.test/x": {"url": "https://s9.test/x", "source": "src9",
                                 "title": "OpenAI solved 100 open problems", "text": "内" * 6000,
                                 "has_full": True}}
    ev = {"title": "OpenAI 攻克百个开放难题", "summary": "",
          "links": ["https://www.reddit.com/r/singularity/comments/1wml775/"
                    "openai_solved_100_open_problems/"]}
    got = D.select_articles(ev, pool)
    assert got and got[0]["url"] == "https://s9.test/x", "slug 里的英文原标题没被用来取词"


def test_cross_source_article_ranks_above_same_source_one():
    """补文必须跨源优先：同源再多也凑不出"≥3 独立源"这一维。"""
    links = ["https://s0.test/a", "https://s0.test/b"]
    pool = {links[0]: {"url": links[0], "source": "src0", "title": "混元定价下调",
                       "text": "内" * 6000, "has_full": True},
            links[1]: {"url": links[1], "source": "src0", "title": "混元定价下调续篇",
                       "text": "内" * 9000, "has_full": True},
            "https://s1.test/c": {"url": "https://s1.test/c", "source": "src1",
                                 "title": "混元定价下调的细节", "text": "内" * 6000,
                                 "has_full": True}}
    got = D.select_articles({"title": "混元定价下调", "links": [links[0]]}, pool)
    assert [a["url"] for a in got[:2]] == [links[0], "https://s1.test/c"], \
        "同源长文排在跨源文前面 ⇒ 独立源数永远补不满"


def test_top_up_uses_title_overlap_not_only_same_source():
    """补证据不能只认同源：事件常只引到 1-2 个源，同源补文永远凑不出第 3 源。"""
    links = ["https://s%d.test/a%d" % (i, i) for i in (0, 1)]
    pool = {links[0]: {"url": links[0], "source": "src0", "title": "腾讯混元下调定价",
                       "text": "内" * 6000, "has_full": True},
            links[1]: {"url": links[1], "source": "src1", "title": "混元定价说明",
                       "text": "内" * 6000, "has_full": True},
            "https://s2.test/a2": {"url": "https://s2.test/a2", "source": "src2",
                                   "title": "腾讯混元模型的定价调整", "text": "内" * 6000,
                                   "has_full": True},
            "https://s3.test/a3": {"url": "https://s3.test/a3", "source": "src3",
                                   "title": "无关的菜谱", "text": "内" * 6000, "has_full": True}}
    got = D.select_articles({"title": "腾讯混元下调定价", "links": links[:1]}, pool)
    urls = [a["url"] for a in got]
    assert "https://s2.test/a2" in urls, "同题长文没被补进来 ⇒ 证据门永远凑不满"
    assert "https://s3.test/a3" not in urls, "无关长文被当证据（会把结论带偏）"


def test_parse_chunk_accepts_real_production_shape():
    """现网真实形态：注释里有等号 + `(window.__CHUNKS=...)[0]={...}`。

    第一版实现用 `text.find("=")` 命中注释里那个等号，整池解析失败 ——
    本地拿真产物 smoke 才发现（离线 fixture 全用 `window.x = ` 是躲得过测试的假绿）。
    """
    real = ('/* StarHub data chunk 0 (first screen) - auto generated, do not edit */\n'
            '(window.__CHUNKS=window.__CHUNKS||[])[0]='
            + json.dumps({"sources": [{"key": "agihunt_0", "name": "AGI Hunt",
                                       "items": [{"title": "t", "link": "https://a.test/1",
                                                  "full_content": "正" * 4000}]}]}) + ';\n')
    arts = D.parse_chunk(real)
    assert len(arts) == 1 and arts[0]["url"] == "https://a.test/1"
    assert arts[0]["has_full"] and len(arts[0]["text"]) == 4000
    assert arts[0]["source"] == "agihunt_0"


def test_missing_chunk_is_a_hard_failure_not_a_warning():
    """56MB 大分块偶发失败。只 warning 就继续 ⇒ 证据面塌陷成"全是快讯"的假成功。"""
    def flaky(url, timeout=90):
        if "rss-data-1.js" in url:
            raise IOError("timeout")
        return _ok_get(url)
    with pytest.raises(IOError):
        D.load_rss_pool(urls=D.CHUNK_URLS, get=flaky, log=lambda s: None)


def test_all_degraded_run_is_blocked_from_publishing(tmp_path):
    """一场跑下来全是快讯 ⇒ 不发。这等于什么都没分析，发出去只会伪装成成功。"""
    pool = {u: {"url": u, "source": "src%d" % i, "title": "t%d" % i, "text": "短" * 400,
                "has_full": True}
            for i, u in enumerate(["https://a.test/1", "https://b.test/2"])}
    logs = []
    out = D.night_run(purpose="publish", client=D.FakeClient(), out_dir=str(tmp_path / "ns"),
                      keys=["k1", "k2", "k3"], anchor_raw=_anchor(list(pool)), pool=pool,
                      api_factory=lambda: pytest.fail("全降级不该提交"), pred_raw="", quality_raw={},
                      date_str="2026-09-23", log=logs.append, sleep=lambda s: None)
    assert out["published"]["status"] == "blocked", out["published"]
    assert any("全降级" in l or "不发布" in l for l in logs), logs


def test_empty_pool_is_a_hard_stop():
    def boom(url, timeout=90):
        raise IOError("404")
    with pytest.raises(IOError):
        D.load_rss_pool(urls=["u1", "u2"], get=boom, log=lambda s: None)


def test_select_articles_dedupes_and_caps():
    pool, links = _pool_articles(6)
    ev = {"links": links[:2] + [links[0]]}
    got = D.select_articles(ev, pool, max_articles=3)
    urls = [a["url"] for a in got]
    assert len(urls) == len(set(urls)), "同一篇被取两次，证据面虚高"
    assert len(urls) <= 3


def test_429_rotates_key_and_accumulates_wait_but_not_failure():
    used = []

    class C:
        def complete(self, prompt, key=None, kind="generate"):
            used.append(key)
            if len(used) == 1:
                raise D.RateLimited(30)
            return '{"ok":1}'

    b = D.Budget(call_cap=80)
    p = D.KeyPool(["k1", "k2"])
    out = D.call_llm(C(), "p", p, b, "generate", sleep=lambda s: None)
    assert out == '{"ok":1}'
    assert used[1] != used[0], "被限流的 key 立刻又被使用"
    assert b.snapshot()["c429"] == 1 and b.snapshot()["wait_s"] == 30
    assert b.over_cap() is False, "429 被算成失败预算"


def test_wait_cap_exceeded_raises_instead_of_hanging():
    class C:
        def complete(self, prompt, key=None, kind="generate"):
            raise D.RateLimited(60)

    b = D.Budget(call_cap=80)
    p = D.KeyPool(["k1"])
    with pytest.raises(D.RateLimited):
        D.call_llm(C(), "p", p, b, "generate", wait_cap_s=20, sleep=lambda s: None)


def test_429_alone_cannot_spin_past_the_wait_budget():
    """每次都拿得到 key、每次都 429 ⇒ 必须按等待预算收口，不许热循环。

    这条判据是被"429 冷却不生效"那个变异体逼出来的：它在真实环境里的等价形态是
    上游不给 Retry-After 且冷却被判到期，于是 `waited` 永远不涨、夜场一路转到
    job 的 180 分钟上限 —— 白等两小时还不报错。
    """
    calls = []

    class Always429:
        def complete(self, prompt, key=None, kind="generate"):
            calls.append(key)
            raise D.RateLimited(0)

    class SpinningClock:
        """每次问时间都往前走一大步：冷却立刻算到期，key 又可派发。"""

        def __init__(self):
            self.t = 0.0

        def __call__(self):
            self.t += 1000.0
            return self.t

    p = D.KeyPool(["k1", "k2"], clock=SpinningClock())
    b = D.Budget(call_cap=80)
    with pytest.raises(D.RateLimited):
        D.call_llm(Always429(), "p", p, b, "generate", wait_cap_s=120, sleep=lambda s: None)
    assert len(calls) <= 8, "429 热循环：烧了 %d 次调用才收口" % len(calls)
    assert b.snapshot()["c429"] == len(calls)


def test_client_refuses_keyless_call():
    """没 key 就发请求等于绕过账号池，必须报错而不是随便用一个默认值。"""
    c = D.AgnesClient(post=lambda payload, key: {"choices": [{"message": {"content": "x"}}]})
    with pytest.raises(RuntimeError):
        c.complete("p", key=None)


def _run(tmp_path, client=None, purpose="test", api_factory=None, call_cap=80, pool=None,
         anchor=None, out_dir=None, max_regen=2, pred_raw="", quality_raw={}):
    pool = pool or _pool_articles(6)[0]
    anchor = anchor or _anchor(list(pool)[:6])
    # sleep/wait_cap 必须注入：默认走 time.sleep(5s) 等满 900s，一旦哪天 KeyPool
    # 被改出"拿不到 key"的分支，这套测试会挂着不动（夜场 CI 预检也在半夜挂着）。
    return D.night_run(purpose=purpose, client=client or D.FakeClient(), out_dir=str(
        out_dir or (tmp_path / "ns")), keys=["k1", "k2", "k3"], anchor_raw=anchor,
        pool=pool, api_factory=api_factory, call_cap=call_cap, max_regen=max_regen,
        date_str="2026-09-23", log=lambda s: None, pred_raw=pred_raw, quality_raw={},
        sleep=lambda s: None, wait_cap_s=5)


def test_night_run_produces_both_artifacts_without_publishing(tmp_path):
    out = _run(tmp_path)
    assert os.path.exists(out["json"]) and os.path.exists(out["html"])
    assert out["published"] is None, "purpose=test 不许提交"
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert doc["engine"] == D.SCHEMA_VERSION
    ev = doc["events"][0]
    assert ev["context_stats"]["total_chars"] >= 18000, "三篇 6000 字长文没整篇进上下文"
    assert ev["citations"] and all(c["url"].startswith("https://") for c in ev["citations"])
    assert ev["rubric"]["mean"] >= 0.75


def test_publish_blocked_for_fake_client(tmp_path):
    with pytest.raises(RuntimeError):
        _run(tmp_path, purpose="publish")


def test_publish_touches_only_own_paths(tmp_path):
    class Api:
        def __init__(self):
            self.head = "h"; self.tree = "t_base"; self.n = 0
            self.paths = []
        def head_info(self): return self.head, self.tree
        def create_blob(self, c): self.n += 1; return "b%d" % self.n
        def create_tree(self, base, entries):
            self.paths = [e["path"] for e in entries]; return "t1"
        def create_commit(self, parent, tree, msg): return "c1"
        def update_ref(self, sha, force=False): self.head = sha; return True
        def is_ancestor(self, sha): return True
    made = {}

    def factory():
        made["api"] = Api(); return made["api"]

    # 真发布路径要一个"不是 FakeClient"的客户端：全降级/半成品会被闸门挡住，
    # 所以这里让它产合格内容（否则测到的是闸门，不是提交路径）。
    class Realish:
        def __init__(self):
            self._f = D.FakeClient()
        def complete(self, prompt, key=None, kind="generate"):
            return self._f.complete(prompt, key, kind)

    out = _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory)
    assert out["published"]["status"] == "published", out["published"]
    assert sorted(made["api"].paths) == ["daily-deep-2026-09-23.json", "deep-insight.html",
                                         "predictions.jsonl"]


def test_checkpoint_makes_second_run_do_no_work(tmp_path):
    d = tmp_path / "ns"
    c1 = D.FakeClient()
    _run(tmp_path, client=c1, out_dir=d)
    first = len(c1.calls)
    assert first >= 2, "第一次就该生成+judge，实为 %d" % first
    c2 = D.FakeClient()
    out2 = _run(tmp_path, client=c2, out_dir=d)
    assert c2.calls == [], "checkpoint 没起作用，同一事件被重跑"


def test_resumed_run_ships_the_whole_set_not_just_tonights_slice(tmp_path):
    """续跑时产物必须含上一段已完成的条目。can_publish 按 done+recs 放行，
    发布写的却是 payload —— 两处口径不一致时，"失败后原地重试"那一夜上线的就是半套。"""
    d = tmp_path / "ns"
    pool, links = _pool_articles(6)
    anchor = _anchor(links[:6])
    _run(tmp_path, out_dir=d, pool=pool, anchor=anchor)
    first = json.load(open(os.path.join(str(d), "daily-deep-2026-09-23.json"), encoding="utf-8"))
    ids1 = [e["id"] for e in first["events"]]
    assert ids1
    # 第二夜：锚点扩到两个事件，第一个已在 checkpoint 里
    anchor2 = _anchor(links[:6])
    doc2 = json.loads(anchor2)
    out2 = _run(tmp_path, out_dir=d, pool=pool, anchor=anchor2)
    second = json.load(open(out2["json"], encoding="utf-8"))
    got = [e["id"] for e in second["events"]]
    assert set(ids1) <= set(got), "上一夜已完成的条目从产物里消失了：%s -> %s" % (got, ids1)
    assert second["budget"]["qualified"] == len([e for e in second["events"]
                                                 if not e.get("degraded_reason")])


def test_call_cap_records_not_run(tmp_path):
    out = _run(tmp_path, call_cap=0)
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert doc["not_run"] and doc["not_run"][0]["reason"] == "not_run:budget", doc["not_run"]


def test_judge_reject_regrades_after_max_regen(tmp_path):
    out = _run(tmp_path, client=D.FakeClient(judge_pass=False))
    doc = json.load(open(out["json"], encoding="utf-8"))
    ev = doc["events"][0]
    assert "重写" in (ev.get("degraded_reason") or ""), ev.get("degraded_reason")
    assert ev["regen_used"] == 2
    assert ev["forecasts"] == [] and len(ev["narrative"]) <= D.DEGRADED_NARR_MAX
    assert doc["budget"]["degraded"] == 1


def test_judge_is_called_separately_from_generator(tmp_path):
    """spec 要求 judge 独立打分：把生成方自报的分当判定分就是自评。

    钉的是"判定与生成是两类调用、判定恰好一次"，不是 `kind=="generate"` 这个字面量 ——
    两段式之后生成侧变成 outline + section，按 kind 名钉会把一条还在成立的不变量判红。
    """
    c = D.FakeClient()
    _run(tmp_path, client=c)
    gen = [k for k in c.calls if k != "judge"]
    assert gen, c.calls
    assert set(gen) <= {"generate", "outline", "section", "structure"}, \
        "冒出了没预期的生成侧调用：%s" % set(gen)
    assert c.calls.count("judge") == 1, "判定次数不是 1：%s" % c.calls
    assert "judge" not in set(gen), "判定与生成共用了 kind，等于让生成方自评"


def test_half_finished_run_is_blocked_from_publishing(tmp_path):
    """一条做完、另一条因限流没做 ⇒ 半套产物不发布（除非是主动撞预算收口）。"""
    pool, links = _pool_articles(6)
    anchor = json.dumps({"date": "2026-09-22", "events": [
        {"id": "e1", "title": "一", "topic": "ai", "summary": "s", "key_links": links[:3]},
        {"id": "e2", "title": "二", "topic": "ai", "summary": "s", "key_links": links[3:6]}]},
        ensure_ascii=False)

    class Flaky(D.FakeClient):
        def __init__(self):
            D.FakeClient.__init__(self)
            self.n = 0

        def complete(self, prompt, key=None, kind="generate"):
            self.n += 1
            if self.n > 2:
                raise D.RateLimited(600)
            return D.FakeClient.complete(self, prompt, key, kind)

    logs = []
    out = D.night_run(purpose="publish", client=Flaky(), out_dir=str(tmp_path / "ns"),
                      keys=["k1", "k2", "k3"], anchor_raw=anchor, pool=pool,
                      api_factory=lambda: pytest.fail("不该发起提交"), pred_raw="", quality_raw={},
                      date_str="2026-09-23", log=logs.append, sleep=lambda s: None,
                      wait_cap_s=1)
    assert out["published"]["status"] == "blocked", out["published"]
    assert any(("不发布" in l) or ("不提交" in l) for l in logs), logs


def test_gate_failure_skips_llm_entirely(tmp_path):
    """证据门不过的条目不花钱：直接降级。"""
    pool, links = _pool_articles(2, long_each=6000)
    c = D.FakeClient()
    out = _run(tmp_path, client=c, pool=pool, anchor=_anchor(links))
    assert c.calls == [], "证据不足却仍然调了模型"
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert "源" in doc["events"][0]["degraded_reason"]


# ── 退出码：绿勾不等于发布成功 ──────────────────────────────────────────────

def _fake_night(monkeypatch, published):
    def fake(**kw):
        return {"payload": {"events": [], "budget": {}}, "budget": _budget_snapshot(),
                "json": "x", "html": "y", "published": published}
    monkeypatch.setattr(D, "night_run", fake)


def _budget_snapshot():
    return {"llm_calls": 3, "wait_s": 1.0, "c429": 0, "elapsed_s": 10.0}


@pytest.mark.parametrize("status,fatal", [
    ("published", False),
    ("skipped", False),
    ("blocked", False),      # 全降级/半成品是数据条件，只告警；真失败见下
    ("reverted", True),      # 提交被白天场回退 = 本场没上线
    ("failed", True),        # CAS 重试用尽
])
def test_main_exit_code_reflects_publish_outcome(monkeypatch, status, fatal):
    _fake_night(monkeypatch, {"status": status, "attempts": 1})
    rc = D.main(["--purpose", "publish"])
    assert (rc != 0) is fatal, "status=%s 时 rc=%d，绿勾会把没上线说成已上线" % (status, rc)


def test_main_exit_code_ignores_publish_state_in_test_mode(monkeypatch):
    """purpose=test 的产物本就不提交，不许因 published=None 而报失败。"""
    _fake_night(monkeypatch, None)
    assert D.main(["--purpose", "test"]) == 0


# ── spec §2 第 3 行 / §5：预测必须落账并可到期对账 ──────────────────────────

def test_prediction_ledger_is_written_and_shipped(tmp_path):
    """"写了预测却没人回头对账"＝ §2 里那条"永不到期的预测不算预测"的另一种写法。
    账本必须 ① 生成 ② 随产物入库（否则次夜读不到，对账链在第一夜就断）。"""
    made = {}

    class Api:
        def __init__(self):
            self.head = "h"; self.n = 0; self.paths = []
        def head_info(self): return self.head, "t_base"
        def create_blob(self, c): self.n += 1; return "b%d" % self.n
        def create_tree(self, base, entries):
            self.paths = [e["path"] for e in entries]; return "t1"
        def create_commit(self, parent, tree, msg): return "c1"
        def update_ref(self, sha, force=False): self.head = sha; return True
        def is_ancestor(self, sha): return True

    def factory():
        made["api"] = Api(); return made["api"]

    class Realish:
        def complete(self, prompt, key=None, kind="generate"):
            return D.FakeClient().complete(prompt, key, kind)

    out = _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory)
    rows = [json.loads(l) for l in
            open(os.path.join(str(tmp_path / "ns"), "predictions.jsonl"), encoding="utf-8")]
    assert rows, "合格条目有 forecasts，却没写出预测账本"
    r = rows[0]
    assert r["status"] == "pending" and r["horizon_days"] in D.HORIZONS
    assert r["made_on"] == "2026-09-23" and r["check_metric"].strip() and r["claim"].strip()
    assert "predictions.jsonl" in made["api"].paths, "账本没入库 ⇒ 对账链第一夜就断"
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert "predictions_reconciled" in doc["budget"] or "predictions_reconciled" in doc


def _jsonl(rows):
    """账本真实形状：一行一个对象（append_jsonl 写出来的就是这个），不是一整份数组。"""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def test_previous_ledger_is_reconciled_not_overwritten(tmp_path):
    """上一夜的到期项必须被结算并保留在账本里：直接写本场行等于每晚把历史清库。"""
    prev = _jsonl([
        {"claim": "三个月内出现跟随者", "event_id": "old1", "horizon_days": 3,
         "check_metric": "同类报道条数", "made_on": "2026-09-20", "status": "pending"},
        {"claim": "未到期项", "event_id": "old2", "horizon_days": 14,
         "check_metric": "星数增量", "made_on": "2026-09-21", "status": "pending"},
    ])
    out = _run(tmp_path, pred_raw=prev)
    rec = out["payload"]["predictions_reconciled"]
    assert rec["due"] >= 1 and rec["unknown"] >= 1, rec
    rows = [json.loads(l) for l in
            open(os.path.join(str(tmp_path / "ns"), "predictions.jsonl"), encoding="utf-8")]
    old = [r for r in rows if r["event_id"] == "old1"]
    assert old and old[0]["status"] != "pending", "到期项没被结算"
    assert any(r["event_id"] == "old2" and r["status"] == "pending" for r in rows), \
        "未到期项被误结算或丢失"


def test_prediction_ledger_stays_bounded(tmp_path):
    """账本无界增长就是另一个 rss_history：留未到期 + 近 90 天已结算。"""
    def row(eid, made, hor, status="pending"):
        return {"claim": "c-" + eid, "event_id": eid, "horizon_days": hor,
                "check_metric": "同类报道条数", "made_on": made, "status": status}
    prev = _jsonl([row("old%d" % i, "2026-01-0%d" % (i % 9 + 1), 3) for i in range(20)]
                  + [row("near%d" % i, "2026-09-05", 3) for i in range(3)]
                  + [row("future", "2026-09-22", 14)]
                  # 坏行：horizon 丢了 → 永远算不出到期日，settle 会一直留在 pending。
                  # 淘汰规则若只看 made_on，这条老账会被"顺手删掉"，而它其实还没结过。
                  + [row("broken", "2026-01-05", None)])
    _run(tmp_path, pred_raw=prev)
    rows = [json.loads(l) for l in
            open(os.path.join(str(tmp_path / "ns"), "predictions.jsonl"), encoding="utf-8")]
    assert all(not r["event_id"].startswith("old") for r in rows), \
        "超 90 天的已结算项没淘汰（账本会长成第二个无界存档）"
    near = [r for r in rows if r["event_id"].startswith("near")]
    assert near and all(r["status"] != "pending" for r in near), "窗口内的到期项没被结算/保留"
    fut = [r for r in rows if r["event_id"] == "future"]
    assert fut and fut[0]["status"] == "pending", "未到期的预测被误删"
    broken = [r for r in rows if r["event_id"] == "broken"]
    assert broken and broken[0]["status"] == "pending", \
        "算不出到期日的行被按 made_on 淘汰了 —— 那是没结过的账，删了就永远补不回来"
    assert len(rows) < 24, len(rows)


def test_transient_ledger_failure_is_fatal_not_empty(tmp_path):
    """把 500/超时当"没有账本"再整库覆盖 = 一次网络抖动毁掉全部对账历史。"""
    def get(url, timeout=90):
        if "predictions" in url:
            raise IOError("500 backend boom")
        return _run_get(url)

    _run_get = D.http_get
    with pytest.raises(IOError):
        D.night_run(purpose="test", client=D.FakeClient(), out_dir=str(tmp_path / "ns"),
                    keys=["k1"], anchor_raw=_anchor(["https://a.test/1"]),
                    pool=_pool_articles(6)[0], get=get, date_str="2026-09-23",
                    quality_raw={},
                    log=lambda s: None, sleep=lambda s: None)


def test_pred_rows_skips_degraded_and_claimless(tmp_path):
    """账本里每行都得能到期核对。degraded 条目本来不许产预测（§2），空 claim 更不是预测：
    放它们进账本，命中率就变成可以用空行凑出来的数。"""
    rows = D.pred_rows([
        {"id": "ok", "forecasts": [{"claim": "三个月内出现跟随者", "horizon_days": 3,
                                    "check_metric": "同类报道条数 >= 5"}]},
        {"id": "deg", "degraded_reason": "证据不足", "forecasts": [
            {"claim": "不该在的预测", "horizon_days": 7, "check_metric": "条数"}]},
        {"id": "empty", "forecasts": [{"claim": "  ", "horizon_days": 14, "check_metric": "x"}]},
    ], "2026-09-23")
    assert [r["event_id"] for r in rows] == ["ok"], rows
    assert rows[0]["made_on"] == "2026-09-23" and rows[0]["status"] == "pending"


def test_first_night_404_is_an_empty_ledger_not_a_crash():
    """第一夜本来就没有账本：404 必须当空，不然这条管线永远起不来。"""
    import urllib.error

    def get(url, timeout=90):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert D.load_prev_predictions(get, "https://x/starhub/predictions.jsonl") == []


def test_corrupt_ledger_is_refused_not_forgotten():
    """有字节却解析不出一行（截断/编码坏了）⇒ 拒绝续写。
    当空账本处理会让本场把整份历史只剩自己几行，这比不跑一晚严重。"""
    def get(url, timeout=90):
        return b'{"claim": "\xe4\xb8\xad\xe6\x96\x87\n'

    with pytest.raises(ValueError):
        D.load_prev_predictions(get, "https://x/starhub/predictions.jsonl")


# ── spec §5：anchor_diff 不能是恒空字段 ────────────────────────────────────

def test_anchor_diff_accounts_for_every_anchor_event(tmp_path):
    """恒空的 anchor_diff 与"名字里带深度却什么都不保证"是同一个病。
    夜场对锚点做的每件事（保留/降级/没做）都要留痕，且证据数前后对照可读。"""
    pool, links = _pool_articles(6)
    anchor = _anchor(links[:6])
    out = _run(tmp_path, pool=pool, anchor=anchor)
    doc = json.load(open(out["json"], encoding="utf-8"))
    diff = doc["anchor_diff"]
    assert diff, "anchor_diff 是恒空字段"
    for row in diff:
        assert row["op"] in ("keep", "drop"), row
        assert row["reason"] and row["id"]
        assert "evidence_before" in row and "evidence_after" in row
    ids = {r["id"] for r in diff}
    assert ids == {e["id"] for e in json.loads(anchor)["events"]}


# ── spec §5：budget 字段名与账号池读数 ─────────────────────────────────────

def test_budget_snapshot_uses_spec_field_names(tmp_path):
    out = _run(tmp_path)
    b = out["payload"]["budget"]
    for k in ("llm_calls", "elapsed_s", "input_tokens", "key_count", "wait_s", "c429",
              "source_sha", "workers"):
        assert k in b, "budget 缺 spec §5 字段 %s：%s" % (k, sorted(b))
    assert b["key_count"] == 3


# ── spec §4：账号池在单 key 下不许把 judge 饿死 ────────────────────────────

def test_judge_not_starved_when_only_one_key(tmp_path):
    """并发 1 起步时"judge 需要空余 ≥2"是死锁：唯一那把 key 一释放就永远凑不到 2，
    每条都会等满 wait_cap 后转 degraded —— 单 key 部署会整场零合格。"""
    c = D.FakeClient()
    out = D.night_run(purpose="test", client=c, out_dir=str(tmp_path / "k1"),
                      keys=["only-one"], anchor_raw=_anchor(list(_pool_articles(6)[0])[:6]),
                      pool=_pool_articles(6)[0], date_str="2026-09-23", pred_raw="", quality_raw={},
                      log=lambda s: None, sleep=lambda s: None, wait_cap_s=5)
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert doc["budget"]["qualified"] == len(doc["events"]) == 1, \
        doc["events"][0].get("degraded_reason")
    assert c.calls.count("judge") == 1, "单 key 下 judge 一次都不该被卡住：%s" % c.calls


def test_workers_cap_never_exceeds_key_pool():
    """并发档超了 key 数只会排队，超了 spec 的 6 就是把免费池推到限流墙下。"""
    assert D.clamp_workers(99, 3) == 2, "并发档必须给 judge 留一把 key"
    assert D.clamp_workers(99, 20) == 6
    assert D.clamp_workers(2, 20) == 2
    assert D.clamp_workers(0, 20) == 1
    assert D.clamp_workers(5, 2) == 1, "两把 key 时并发只能是 1，否则 judge 永远等不到空余"
    assert D.clamp_workers(5, 1) == 1, "单 key 也不能被减成 0 条泳道"
    # --workers 是 dispatch 输入，负数手滑不能变成"0 个 worker ⇒ 永远拿不到 key"
    assert D.clamp_workers(-1, 20) == 1
    assert D.clamp_workers(3, 0) == 1


# ── 锚点必须按现网真实形状读（审查 P0：现网是 label，没有 title） ──────────

def _live_anchor(links):
    """照现测 `daily-insight.json` 的形状造：键是 label/category/articles[].url，
    事件里根本没有 title。测试若顺着实现的假设造数，就永远看不见这个 P0。"""
    return json.dumps({"date": "2026-09-22", "theme": "T", "events": [
        {"id": "evt_live_1", "label": "某厂商牵头为前沿 AI 定安全标准", "category": "policy",
         "summary": "摘要", "status": "new", "score": 0.14,
         "sources": ["aihot", "rss"], "key_links": links[:2],
         "articles": [{"title": "报道%d" % i, "source": "IT之家", "type": "rss", "url": links[i]}
                      for i in range(2, 6)]}]}, ensure_ascii=False)


def test_anchor_maps_the_live_field_names():
    got = D.load_anchor_events(_live_anchor(["https://s%d.test/a%d" % (i, i) for i in range(6)]))
    e = got["events"][0]
    assert e["title"] == "某厂商牵头为前沿 AI 定安全标准", "label 没被当成标题：现网每条都会空"
    assert e["topic"] == "policy"
    assert len(e["links"]) >= 6, "白天已经选好的 articles[].url 没并进证据面"


def test_live_shaped_anchor_is_not_degraded_for_missing_title(tmp_path):
    """端到端：现网形状的锚点跑一场，不许以"条目缺 title/topic"为由全降级。

    这个形态在生产里是每晚 100% 发生 —— 而且因为契约失败发生在生成之后，
    每条还要白烧 max_regen+1 次调用。
    """
    pool, links = _pool_articles(6)
    out = _run(tmp_path, pool=pool, anchor=_live_anchor(links))
    doc = json.load(open(out["json"], encoding="utf-8"))
    ev = doc["events"][0]
    assert "title" not in " ".join(ev.get("contract_fails") or []), ev.get("contract_fails")
    assert doc["budget"]["qualified"] == 1, ev.get("degraded_reason")


def test_wall_clock_cap_stops_the_loop_before_the_platform_kills_it(tmp_path, monkeypatch):
    """`Budget.time_cap_s` 不能只是个摆设：job 有 timeout-minutes 180，而产物在循环
    之后才落盘。撞墙时被掐死 = 整晚既无产物也无红。

    时间从 `over_time` 的脚本里来，不从假 `_now` 的调用次数里来。时钟的读取点是实现的
    自由度（KeyPool 探空闲、snapshot 报 elapsed_s 都在这条链上），按"第几次调用翻面"
    写出来的判据会随无关改动漂移：CI 上两条全跑完就是这个原因，本地却因为读取点少而绿。
    真正的时钟算术单独由 test_budget_wall_clock_arithmetic 钉住。
    """
    answers = [False, True] + [True] * 20
    monkeypatch.setattr(D.Budget, "over_time", lambda self: answers.pop(0))
    pool, links = _pool_articles(6)
    anchor = json.dumps({"date": "2026-09-22", "events": [
        {"id": "e1", "title": "一", "topic": "ai", "summary": "s", "key_links": links[:3]},
        {"id": "e2", "title": "二", "topic": "ai", "summary": "s", "key_links": links[3:6]}]},
        ensure_ascii=False)
    out = _run(tmp_path, pool=pool, anchor=anchor)
    doc = json.load(open(out["json"], encoding="utf-8"))
    done = [e["id"] for e in doc["events"]]
    assert done == ["e1"], "墙钟预算没生效或生效太早：%s" % done
    assert answers == [True] * 20, "每条只该问一次墙钟（实际消费 %d 次）" % (22 - len(answers))
    assert doc["not_run"] and doc["not_run"][0]["reason"] == "not_run:wallclock", doc["not_run"]
    assert os.path.exists(out["html"]), "收口时必须仍然落盘，否则页面是空的"


def test_budget_wall_clock_arithmetic(monkeypatch):
    """上一条把"闸门被问到就答应"钉住了，这条钉住闸门本身：真的 monotonic 算术。

    三个分支都得有判据，因为每一个都曾在实现里以"永远不成立"的形态出现过：
    start() 之前 t0 是 None（`if self.t0` 会把起点正好为 0 当成没开始）、恰好等于
    预算的边界、以及 time_cap_s<=0 表示不设墙钟。
    """
    box = {"v": 0.0}
    monkeypatch.setattr(D, "_now", lambda: box["v"])
    cap = 150 * 60
    b = D.Budget(call_cap=10, time_cap_s=cap)
    assert not b.over_time(), "还没 start() 就报超时 = 一开场就收工"
    assert b.elapsed_s() == 0.0
    b.start()
    box["v"] += cap - 1
    assert not b.over_time(), "预算内就该继续跑"
    box["v"] += 1
    assert b.over_time(), "到点必须收口（边界含等于）"
    assert b.elapsed_s() == float(cap)
    off = D.Budget(call_cap=10, time_cap_s=0)
    off.start()
    box["v"] += 10 ** 6
    assert not off.over_time(), "time_cap_s=0 表示不设墙钟，不是永远超时"


# ── 现网第一跑真撞出来的形状问题：模型可以给字符串，不是只给 dict ──────────

def test_model_may_return_string_shaped_rows_without_crashing(tmp_path):
    """run 35735624747 就是死在这里：真模型把 citations 返回成 ["c1","https://…"]，
    实现按 dict 处理 → `AttributeError: 'str' object has no attribute 'get'` 崩在主循环，
    整场无产物。FakeClient 永远返回 dict，所以本地一百多条测试对这个形状全盲。

    要求的不是"容忍"，是"按形状归一 + 编造链接不进产物"。
    """
    class Shaped:
        def __init__(self):
            self.calls = []

        def complete(self, prompt, key=None, kind="generate"):
            self.calls.append(kind)
            if kind == "judge":
                return json.dumps({"narrative": 0.9, "causal": 0.9,
                                   "forecast": 0.9, "quality": 0.9})
            body = "论证与数据推演" + "依" * 380 + "，但该判断仍受样本量与统计口径限制。"
            return json.dumps({
                "narrative": "\n\n".join(body for _ in range(7)),
                "claims": ["论断一", "论断二", "论断三"],
                "causal_chains": ["因为 A 所以 B"],
                "forecasts": ["预计三个月内出现跟随者"],
                "quality": "这是一手报道",
                "citations": ["c1", "c2", "c3", "c4", "c5",
                              "https://fabricated.example/neighbour-never-existed"],
            }, ensure_ascii=False)

    pool, links = _pool_articles(6)
    out = _run(tmp_path, client=Shaped(), pool=pool, anchor=_anchor(links[:6]))
    doc = json.load(open(out["json"], encoding="utf-8"))
    ev = doc["events"][0]
    cites = ev.get("citations") or []
    assert all(isinstance(c, dict) and (c.get("id") or "").startswith("c") for c in cites), cites
    assert all((c.get("url") or "").startswith("https://s") for c in cites), \
        "模型自带的 URL 被原样采信：假链接就这么上屏"
    # 编造的链接不许成为引用、更不许上屏；但它要作为"违了什么约"的证据留在产物里
    # （否则 §2 的"假链接＝硬失败"又变回静默丢弃，读产物的人根本不知道发生过）。
    assert "fabricated" not in json.dumps(cites, ensure_ascii=False), cites
    assert "fabricated" not in open(out["html"], encoding="utf-8").read(), \
        "编造域名上屏了"
    assert ev.get("invented_citations") or any(
        "假链接" in f for f in (ev.get("contract_fails") or [])), ev
    # 字符串形态的 claims/chains/forecasts/quality 不算合格内容，必须降级而不是当合格
    assert (ev.get("degraded_reason") or "").strip() or doc["budget"]["qualified"] == 0, ev


def test_truncated_replies_are_counted_separately(tmp_path):
    """`finish_reason=length` 必须单独记一笔。

    截断在产物里长得和"模型写得太短"一模一样：不分开，spec §3 那条 `max_tokens`
    待验假设就永远验不了，还会把输出上限的问题误判成模型能力问题。
    """
    class Truncating:
        last_finish_reason = ""

        def complete(self, prompt, key=None, kind="generate"):
            self.last_finish_reason = "length" if kind == "generate" else "stop"
            return "{}"

    b = D.Budget(call_cap=80)
    b.start()
    c = Truncating()
    D.call_llm(c, "p", D.KeyPool(["k1"]), b, "generate", sleep=lambda s: None)
    assert b.snapshot()["truncated"] == 1, b.snapshot()
    D.call_llm(c, "p", D.KeyPool(["k1"]), b, "judge", sleep=lambda s: None)
    assert b.snapshot()["truncated"] == 1, "judge 正常收尾也被记成截断"
