# tests/deep_insight/test_night_run.py
# -*- coding: utf-8 -*-
"""夜场编排：全文池、429 重试、判定回环、checkpoint、发布闸。

替身纪律同 test_runtime：FakeGet/FakeApi 都按真 API 的语义报错（404 就抛、
CAS 父不符就返回 False），不给任何"宽松通过"。
"""
import json
import os
import sys
import time

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


def test_all_degraded_run_still_publishes(tmp_path):
    """全场降级**照发布**。这条推翻我自己写过的 `..._is_blocked_from_publishing`。

    旧政策的后果是用户 2026-09-23 指出的那句：质量一抖，站点"几天都没信息或者永久没信息"。
    沉默对读者和"管线坏了"长得一模一样；"半套不上线"管的是**有条目根本没做**，
    不是"做了但只够快讯"。伪装成功的正确解法是把话说清楚（页面横幅 + 每条标原因），
    不是不发。
    """
    pool = {u: {"url": u, "source": "src%d" % i, "title": "t%d" % i, "text": "短" * 400,
                "has_full": True, "source_key": "s%d_%d" % (i, i)}
            for i, u in enumerate(["https://a.test/1", "https://b.test/2"])}
    logs = []

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

    class Realish:
        """组合而非继承：发布路径硬拒 `isinstance(client, FakeClient)`，
        这里要测的是"全降级也发布"，不是那道假客户端闸。"""
        def __init__(self):
            self._f = D.FakeClient()
        def complete(self, prompt, key=None, kind="generate"):
            return self._f.complete(prompt, key, kind)

    out = D.night_run(purpose="publish", client=Realish(), out_dir=str(tmp_path / "ns"),
                      keys=["k1", "k2", "k3"], anchor_raw=_anchor(list(pool)), pool=pool,
                      api_factory=lambda: made.setdefault("api", Api()) or made["api"],
                      pred_raw="", quality_raw={},
                      date_str="2026-09-23", log=logs.append, sleep=lambda s: None)
    assert out["published"] != {"status": "blocked", "attempts": 0}, \
        "全降级仍被挡：站点会连续多日无更新 %s" % (out["published"],)
    assert "deep-insight.html" in made["api"].paths, made["api"].paths
    assert any("无合格深度条目" in l or "按快讯发布" in l for l in logs), logs


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
         anchor=None, out_dir=None, max_regen=2, pred_raw="", quality_raw={}, workers=1):
    pool = pool or _pool_articles(6)[0]
    anchor = anchor or _anchor(list(pool)[:6])
    # sleep/wait_cap 必须注入：默认走 time.sleep(5s) 等满 900s，一旦哪天 KeyPool
    # 被改出"拿不到 key"的分支，这套测试会挂着不动（夜场 CI 预检也在半夜挂着）。
    return D.night_run(purpose=purpose, client=client or D.FakeClient(), out_dir=str(
        out_dir or (tmp_path / "ns")), keys=["k1", "k2", "k3"], anchor_raw=anchor,
        pool=pool, api_factory=api_factory, call_cap=call_cap, max_regen=max_regen,
        date_str="2026-09-23", log=lambda s: None, pred_raw=pred_raw, quality_raw={},
        workers=workers,
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


def test_every_item_carries_its_own_call_and_time_account(tmp_path):
    """spec §7 要"每合格条目调用数"来定 CALL_CAP —— 这个数必须在产物里。

    第四轮审查量到的真实形状：整场只有 `llm_calls=756` 一个总数，摊到 7 条什么也定不了；
    定档要看分布。`llm_calls_used` 自批 3.9 起按**归属**计（不是"本条起止之间的全局新增数"，
    那种窗口增量在 workers=3 下会把同一段调用重复计给每条），所以这里断言严格相等。
    """
    pool, links = _pool_articles(6)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)
    out = _run(tmp_path, pool=pool, anchor=anchor, call_cap=4000)
    doc = json.load(open(out["json"], encoding="utf-8"))
    evs = doc["events"]
    assert len(evs) == 3, [e.get("id") for e in evs]
    used = [e.get("llm_calls_used") for e in evs]
    assert all(isinstance(u, int) and u > 0 for u in used), used
    assert all(isinstance(e.get("elapsed_item_s"), float) for e in evs), \
        [e.get("elapsed_item_s") for e in evs]
    # 相加必须**恰好**等于总数。早先写法取窗口增量，并发下会重复计：
    # 现网 run 35957864648（workers=3）量到六条之和 594 > 总数 207，正好是并发倍率。
    assert sum(used) == doc["budget"]["llm_calls"], \
        "各条之和 %d != 总数 %d：归属计账没生效" % (sum(used), doc["budget"]["llm_calls"])
    cpq = doc["budget"]["calls_per_qualified"]
    assert cpq["items"] and cpq["max"] >= cpq["mean"] > 0, cpq


def test_per_item_accounts_are_exact_under_real_concurrency(tmp_path):
    """真并发（workers=3）下各条归属计数仍要相加等于总数，并且要证明确实重叠了。

    只测串行等于没测 —— 这条判据红过一次的原因就是"窗口增量"在并发下重复计数，
    而并发档才是生产值（deep-insight.yml 里 workers=3）。
    """
    pool, links = _pool_articles(6)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)
    class SlowFirst(D.FakeClient):
        """每条第一次提纲调用真睡 0.12s：并发时三条同睡，串行时排队睡。

        信号必须自己造：`_run` 把预算的 sleep 钩子换成了 no-op，正常跑三条各 ~30ms，
        量出来的耗时分辨不出重叠不重叠。
        """

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "outline":
                time.sleep(0.12)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    out = _run(tmp_path, client=SlowFirst(), pool=pool, anchor=anchor,
               call_cap=4000, workers=3)
    doc = json.load(open(out["json"], encoding="utf-8"))
    evs = doc["events"]
    assert len(evs) == 3, [e.get("id") for e in evs]
    used = [int(e.get("llm_calls_used") or 0) for e in evs]
    assert all(u > 0 for u in used), used
    assert sum(used) == doc["budget"]["llm_calls"], \
        "并发下各条之和 %d != 总数 %d" % (sum(used), doc["budget"]["llm_calls"])
    secs = [float(e.get("elapsed_item_s") or 0) for e in evs]
    total = float(doc["budget"]["elapsed_s"] or 0)
    assert max(secs) < sum(secs), "三条各跑 %s 秒：根本没重叠，这条测不到并发" % (secs,)
    # 结构性自证：排队时"各条之和 == 全场耗时"，真并发时之和≈3×单条 > 全场。
    assert sum(secs) > total, "各条之和 %s <= 全场 %s：三条是排队的，这条测不到并发" % (
        sum(secs), total)


def test_an_item_that_crashes_still_returns_its_call_account(tmp_path):
    """走 `except Exception` 那条早退路径（Agnes 5xx 的形状）时同样要交回自己的账。

    与下一条判据成对：早退有两条路径，只钉一条的话另一条删了照样绿（第五轮审查 P1-5）。
    """
    pool, links = _pool_articles(3)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)

    class Crashes(D.FakeClient):
        n = 0

        def complete(self, prompt, key=None, kind="generate"):
            self.n += 1
            if self.n in (2, 3):
                raise ValueError("upstream 5xx")
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    out = _run(tmp_path, client=Crashes(), pool=pool, anchor=anchor, call_cap=4000)
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert doc.get("failed_items"), doc.keys()
    alive = sum(int(e.get("llm_calls_used") or 0) for e in doc["events"])
    dead = [int(r.get("llm_calls_used") or 0) for r in doc.get("not_run") or []]
    assert alive + sum(dead) == doc["budget"]["llm_calls"], (alive, dead)


def test_a_resumed_run_counts_only_this_attempt_money(tmp_path):
    """续跑场：本场总数只该等于"本场做过的条目 + 本场死掉的条目"。

    `prev_recs` 里的条目带着上一趟的 `llm_calls_used`，而 `budget.llm_calls` 只数本场。
    这条判据**从 checkpoint 文件自己算出哪些条是带回来的**，不靠产物里的元数据字段：
    加那种字段会让每趟重试都改产物字节，把幂等守卫打回（现网判据实测过一次红）。
    """
    pool, links = _pool_articles(3)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)
    nd = tmp_path / "ns"
    out1 = _run(tmp_path, pool=pool, anchor=anchor, out_dir=nd,
                call_cap=D.PER_ATTEMPT_CALLS + 5)
    d1 = json.load(open(out1["json"], encoding="utf-8"))
    assert len(d1["events"]) == 1, [e["id"] for e in d1["events"]]
    carried = {json.loads(l)["id"] for l in
               open(os.path.join(str(nd), "deep-2026-09-23.jsonl"), encoding="utf-8")
               if l.strip()}
    assert carried == {d1["events"][0]["id"]}, carried

    out2 = _run(tmp_path, pool=pool, anchor=anchor, out_dir=nd, call_cap=4000)
    d2 = json.load(open(out2["json"], encoding="utf-8"))
    this = [e for e in d2["events"] if e["id"] not in carried]
    assert this and len(this) + len(carried) == len(d2["events"]), (
        [e["id"] for e in d2["events"]], carried)
    dead = sum(int(r.get("llm_calls_used") or 0) for r in d2.get("not_run") or [])
    assert sum(int(e.get("llm_calls_used") or 0) for e in this) + dead == \
        d2["budget"]["llm_calls"], (this, dead, d2["budget"]["llm_calls"])
    # 上一趟的钱不许被算进本场：混起来的话 §7 会把两趟的成本当一趟定档
    assert int(d2["budget"]["llm_calls"]) < \
        sum(int(e.get("llm_calls_used") or 0) for e in d2["events"]), d2["budget"]


def test_an_item_that_dies_still_returns_its_call_account(tmp_path):
    """条目中途被 429 掐出去：已花掉的调用要钉在自己的 not_run 行上。

    两条早退路径（429 等不到 key、瞬时异常）以前只 log 就 return —— 钱花在死掉那条身上，
    产物里却只剩 not_run:incomplete 一个名字，读的人分不开"没排上"（0 次）与
    "跑到一半被掐了"（几十次）。异常那条由 test_an_item_that_crashes_... 钉，成对。
    """
    pool, links = _pool_articles(3)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)

    class Dies(D.FakeClient):
        n = 0

        def complete(self, prompt, key=None, kind="generate"):
            self.n += 1
            if self.n in (2, 3):
                # 首发与补试都抛 ⇒ 条目真的死掉（批 3.11 之后只抛一次会被换 key 救回来）。
                # 第一次已经记过一笔账，正是要钉的形状。
                raise D.RateLimited(30)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    out = _run(tmp_path, client=Dies(), pool=pool, anchor=anchor, call_cap=4000)
    doc = json.load(open(out["json"], encoding="utf-8"))
    rows = doc.get("not_run") or []
    assert rows, [e.get("id") for e in doc["events"]]
    alive = sum(int(e.get("llm_calls_used") or 0) for e in doc["events"])
    dead = [int(r.get("llm_calls_used") or 0) for r in rows]
    assert max(dead) > 0, "死掉那条的调用没进产物：not_run 只写着没做，看不出已经花了多少"
    assert alive + sum(dead) == doc["budget"]["llm_calls"], (
        "活着 %d + 死了 %s != 总数 %d" % (alive, dead, doc["budget"]["llm_calls"]))


def test_a_run_may_not_start_an_item_it_cannot_finish(tmp_path):
    """预算不够写完一条就不许开这条：旧闸只问 `llm_calls >= call_cap`，剩 1 次也照开。

    一条最坏 3 趟 × 每趟 PER_ATTEMPT_CALLS 次 —— 那是整夜最大的一笔超发，
    而且事后从 `not_run` 上读不出来（它看起来只是"没排上"）。
    """
    cap = D.PER_ATTEMPT_CALLS + 5          # 只够开一条，第二条必超发
    pool, links = _pool_articles(3)
    anchor = json.dumps({"date": "2026-09-22", "events": [
        {"id": "evt%d" % i, "title": "事件%d" % i, "topic": "ai", "summary": "概述",
         "key_links": list(links)} for i in range(3)]}, ensure_ascii=False)
    out = _run(tmp_path, call_cap=cap, pool=pool, anchor=anchor)
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert len(doc["events"]) == 1, [e["id"] for e in doc["events"]]
    reasons = [r["reason"] for r in doc.get("not_run") or []]
    assert reasons and all(x == "not_run:budget" for x in reasons), reasons
    assert doc["budget"]["llm_calls"] <= cap, \
        "超发 %d 次：开条前的预留没起作用" % (doc["budget"]["llm_calls"] - cap)


def test_judge_reject_degrades_without_burning_the_whole_regen_budget(tmp_path):
    """判定不过线且离合格线远（0.40）：降级 + 只重写 1 轮就收手。

    原来这条钉的是"跑满 max_regen 后降级"。批 3 之后账变了：0.40→0.40 的第三趟
    是重掷骰子（同一内容复评极差实测 0.17），预算要留给下一条洞察。
    近线那档（0.70/0.72）仍跑满三轮，判据在 test_judge_denoise 里成对钉着。
    """
    out = _run(tmp_path, client=D.FakeClient(judge_pass=False))
    doc = json.load(open(out["json"], encoding="utf-8"))
    ev = doc["events"][0]
    assert "重写" in (ev.get("degraded_reason") or ""), ev.get("degraded_reason")
    assert ev["regen_used"] == 1, ev["regen_used"]
    assert ev.get("regen_stalled"), "收手没留痕：读产物的人分不开'没预算'与'判定停滞'"
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
    # faith 是批 2 新增的独立核查阶段：既不是生成也不是判定，白名单要显式承认它。
    assert set(gen) <= {"generate", "outline", "section", "structure", "faith"}, \
        "冒出了没预期的生成侧调用：%s" % set(gen)
    # 判定的次数由采样数决定（批 3：单遍均值落在复评噪声带里，不可复现）。
    # 这条判据真正钉的是"判定与生成不共用 kind"，不是次数等于 1。
    assert c.calls.count("judge") == D.JUDGE_SAMPLES, \
        "判定次数不等于采样数 %d：%s" % (D.JUDGE_SAMPLES, c.calls)
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
    # ref 必须点名：批 0 之后 purpose=publish 不给 ref 会在出网前就被拒，
    # 那样这条判据测的就不是退出码而是守卫了。打主干在这里是显式决定。
    rc = D.main(["--purpose", "publish", "--ref", D.MAIN_REF])
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
    # 这条钉的是"单 key 部署下判定不被预留位饿死"，次数按采样数走，不是 1。
    assert c.calls.count("judge") >= D.JUDGE_SAMPLES, \
        "单 key 下 judge 没被叫满采样数：%s" % c.calls


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
    # `degraded_reason` 是要渲染上屏的那一格：把违约原文（内含模型自报的假链接）
    # 原样拼进理由，等于绕开 citations 的清洗把假域名送上线。原文只许留在 JSON 账里。
    assert "fabricated" not in (ev.get("degraded_reason") or ""), ev.get("degraded_reason")
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


def test_the_broadcast_says_not_judged_rather_than_rubric_zero(tmp_path, monkeypatch):
    """播报读者：CI 日志里那行 `rubric=0.0` 是运维唯一看得见的分，也得改口。

    页面改了而日志没改，等于只修了半个读者（"观测字段必须连读者一起交付"）。
    """
    pool, links = _pool_articles(6)
    anchor = json.dumps({"date": "2026-09-23", "events": [
        {"id": "evt1", "title": "事件甲", "topic": "ai", "summary": "概述",
         "key_links": list(links)}]}, ensure_ascii=False)
    logs = []

    class AlwaysShort(D.FakeClient):
        """每一趟都交一份注定过不了契约的短正文（走单趟模式，判定没机会跑）。"""

        def complete(self, prompt, key=None, kind="generate"):
            if kind == "generate":
                self.calls.append("generate")
                doc = json.loads(D.FakeClient.complete(self, prompt, key=key, kind="structure"))
                doc["narrative"] = "论证很短。" * 30
                return json.dumps(doc, ensure_ascii=False)
            return D.FakeClient.complete(self, prompt, key=key, kind=kind)

    def _no_network(*a, **kw):
        raise AssertionError("判据不许真出网：漏传 pred_raw/quality_raw 就会走到这里"
                             "（第五轮审查 P0-1：那次未复现的红就是这个）")

    monkeypatch.setattr(D, "http_get", _no_network)
    out = D.night_run(purpose="test", client=AlwaysShort(), out_dir=str(tmp_path / "ns"),
                      keys=["k1", "k2", "k3"], anchor_raw=anchor, pool=pool,
                      api_factory=None, call_cap=4000, max_regen=2, date_str="2026-09-23",
                      log=logs.append, sleep=lambda s: None, wait_cap_s=5, staged=False,
                      pred_raw="", quality_raw={})
    lines = [l for l in logs if "rubric" in l]
    assert lines, logs[-6:]
    assert any("未送判定" in l for l in lines), lines
    assert not any("rubric=0.0" in l for l in lines), lines


def test_transient_upstream_error_retries_on_another_key():
    """一过性 5xx 换一把 key 立刻再问一次；不许吃掉整条洞察。

    与 429 的分工要守住：5xx 不带 Retry-After、**不进等待预算**，
    所以它不能复用 429 那条冷却-等待路径，只是"换人再问一次"。
    """
    used = []

    class Flaky:
        def complete(self, prompt, key=None, kind="generate"):
            used.append(key)
            if len(used) == 1:
                raise RuntimeError("Agnes HTTP 520")
            return '{"ok":1}'

    b = D.Budget(call_cap=80)
    p = D.KeyPool(["k1", "k2"])
    assert D.call_llm(Flaky(), "p", p, b, "generate", sleep=lambda s: None) == '{"ok":1}'
    assert len(used) == 2, used
    assert used[1] != used[0], "重试还用了刚报错那把 key"
    snap = b.snapshot()
    assert snap["upstream_errors"] == 1 and snap["upstream_recovered"] == 1, snap
    assert snap["c429"] == 0 and snap["wait_s"] == 0, "5xx 被记成了限流等待"
    # 补试用过的那把 key 必须交还：漏 release 会让池子越跑越小（第五轮 P1-5，原先无人钉）
    assert p.snapshot()["busy"] == 0, "补试的 key 没 release，留在 busy 里：%s" % p.snapshot()


def test_sustained_upstream_error_costs_at_most_one_extra_attempt():
    """持续故障要快速失败：每次调用最多补试一次，不叠加、不退避重试。

    最坏情况的账写死在这里：整场都是 5xx 时请求数至多翻倍
    （现网第 30 场三条死条目共 54 次成功调用 ⇒ 上限也就多 ~54 次请求），
    换 key 再问一次救不回持续故障，但也不会把预算拖没。
    """
    used = []

    class AlwaysDown:
        def complete(self, prompt, key=None, kind="generate"):
            used.append(key)
            raise RuntimeError("Agnes HTTP 520")

    b = D.Budget(call_cap=80)
    p = D.KeyPool(["k1", "k2"])
    for _ in range(5):
        with pytest.raises(RuntimeError):
            D.call_llm(AlwaysDown(), "p", p, b, "generate", sleep=lambda s: None)
    assert len(used) == 10, "5 次调用各应试两把 key，实际 %d 次" % len(used)
    snap = b.snapshot()
    assert snap["upstream_errors"] == 10 and snap["upstream_recovered"] == 0, snap


def test_no_other_free_key_means_no_retry():
    """只有一把 key 时**不**原地再问：那把刚报错，补试只会多烧一次请求。

    这条钉的是"换 key"而不是"重试"这个措辞 —— 实现要是写成同一个 key 循环，
    单 key 场景就会白烧一倍请求还照样失败。
    """
    used = []

    class AlwaysDown:
        def complete(self, prompt, key=None, kind="generate"):
            used.append(key)
            raise RuntimeError("Agnes HTTP 520")

    b = D.Budget(call_cap=80)
    p = D.KeyPool(["k1"])
    with pytest.raises(RuntimeError):
        D.call_llm(AlwaysDown(), "p", p, b, "generate", sleep=lambda s: None)
    assert len(used) == 1, "没有别的空闲 key 还补试：%s" % used


def test_an_evidence_gate_item_is_not_printed_as_a_zero_score(tmp_path):
    """证据门挡下的条目同样"没送判定"，而且文案要说得出是哪一道门（第五轮 P1-2）。

    这条判据的靶子是"修了一个写点漏了另两个"：契约、证据门、判据协议三支都写 0.0，
    只补契约那一支的话，页面上另外两类条目还在被印成"判了 0 分"。
    """
    pool, links = _pool_articles(1)
    ev = {"id": "e9", "title": "只有短摘要", "topic": "ai", "summary": "概述",
          "key_links": list(links)}
    anchor = json.dumps({"date": "2026-09-23", "events": [ev]}, ensure_ascii=False)
    out = _run(tmp_path, anchor=anchor, pool=pool, call_cap=4000)
    doc = json.load(open(out["json"], encoding="utf-8"))
    hit = [e for e in doc["events"] if (e.get("rubric") or {}).get("judge_skip") == "evidence_gate"]
    html = D.render_page(doc)
    if hit:
        assert u"证据门挡下" in html, html[:900]
        assert "rubric 0.0" not in html
    else:
        # 这个夹具没造出门挡下的形状时也必须说得出为什么，否则判据是空的
        assert u"证据门挡下" not in html, "页面出现了没有产物对应的标注"


def test_total_requests_are_derivable_from_the_three_counters():
    """恒等式：实际发出的请求数 == 成功调用 + 被限流 + 上游故障打断。

    这是"表征判据"而不是修 bug：批 3.11 之后调用数与请求数第一次不等价，
    现在不钉住，等下一次拿 `llm_calls` 去定 `CALL_CAP` 时就会在故障场里低估真实开销。
    三个计数器各自都已有变异体守着，这里钉的是**它们之间**的关系。
    """
    sent = []

    class Mixed:
        """第 1 次 429、第 2 次 5xx、第 3 次（补试）成功 ⇒ 3 个请求、1 次成功调用。"""

        def complete(self, prompt, key=None, kind="generate"):
            sent.append(key)
            n = len(sent)
            if n == 1:
                raise D.RateLimited(10)
            if n == 2:
                raise RuntimeError("Agnes HTTP 520")
            return '{"ok":1}'

    b = D.Budget(call_cap=80)
    b.start()
    p = D.KeyPool(["k1", "k2", "k3"])
    # 1) 三种故障各来一次后成功：请求 3 个、账上 1+1+1
    assert D.call_llm(Mixed(), "p", p, b, "generate", sleep=lambda s: None) == '{"ok":1}'
    snap = b.snapshot()
    assert snap["llm_calls"] == 1 and snap["c429"] == 1 and snap["upstream_errors"] == 1, snap
    assert len(sent) == snap["llm_calls"] + snap["c429"] + snap["upstream_errors"], (
        "三种计数器凑不齐：发了 %d 个请求，账上是 %s" % (len(sent), snap))

    # 2) 首发 5xx、补试成功：请求 2、成功 1、打断 1（至多补试一次，第二次 5xx 就该抛）
    sent2 = []

    class DownThenUp:
        def complete(self, prompt, key=None, kind="generate"):
            sent2.append(key)
            if len(sent2) == 1:
                raise RuntimeError("Agnes HTTP 502")
            return '{"ok":1}'

    b2 = D.Budget(call_cap=80)
    b2.start()
    assert D.call_llm(DownThenUp(), "p", D.KeyPool(["k1", "k2", "k3"]), b2, "generate",
                      sleep=lambda s: None) == '{"ok":1}'
    snap2 = b2.snapshot()
    assert snap2["llm_calls"] == 1 and snap2["upstream_errors"] == 1, snap2
    assert len(sent2) == snap2["llm_calls"] + snap2["c429"] + snap2["upstream_errors"], (
        "补试过的请求没进恒等式：发了 %d 个，账上 %s" % (len(sent2), snap2))


def test_a_retry_that_hits_429_is_still_treated_as_429():
    """补试撞 429 必须走限流那一档：冷却那把 key、记 c429、推进 waited，而不是当上游故障抛出去。

    429 与 5xx 的下一步不同（一个等窗口、一个换人），归因合并成同一个计数器，
    读日志的人就会去查错的地方；而没被 mark 的 key 会立刻被下一条继续踩。
    """
    sent = []

    class Mixed:
        def complete(self, prompt, key=None, kind="generate"):
            sent.append(key)
            n = len(sent)
            if n == 1:
                raise RuntimeError("Agnes HTTP 520")     # 首发：上游故障
            if n == 2:
                raise D.RateLimited(45)                   # 补试：其实是被限流
            return '{"ok":1}'                             # 再换一把就成功

    p = D.KeyPool(["k1", "k2", "k3"])
    b = D.Budget(call_cap=80)
    b.start()
    assert D.call_llm(Mixed(), "p", p, b, "generate", sleep=lambda s: None) == '{"ok":1}'
    snap = b.snapshot()
    assert snap["llm_calls"] == 1, snap
    assert snap["c429"] == 1, "补试那次 429 没进限流账：%s" % snap
    assert snap["upstream_errors"] == 1, "429 被误记成上游故障：%s" % snap
    assert snap["wait_s"] >= 45, "429 该推进等待预算，却一秒都没等：%s" % snap
    assert p.snapshot()["cooling"] >= 1, "那把 429 的 key 没被冷却，下一条会继续踩"
    assert len(sent) == snap["llm_calls"] + snap["c429"] + snap["upstream_errors"], (
        "请求数恒等式破了：发了 %d 个，账上 %s" % (len(sent), snap))


def test_a_key_that_just_5xxed_is_not_the_next_one_picked():
    """上游按 key 拉黑时，每次都先撞那把坏 key = 每次白补一发请求。

    只做"挪队尾"，**不冷却**：全池都是 5xx 时冷却会把每条都拖满 `wait_cap_s`，
    那比白补一次糟得多（第六轮审查 P1-3 的取舍）。
    """
    picked = []

    class FirstKeyIsBad:
        def complete(self, prompt, key=None, kind="generate"):
            picked.append(key)
            if key == "k1":
                raise RuntimeError("Agnes HTTP 520")
            return '{"ok":1}'

    p = D.KeyPool(["k1", "k2", "k3"])
    b = D.Budget(call_cap=80)
    b.start()
    assert D.call_llm(FirstKeyIsBad(), "p", p, b, "generate", sleep=lambda s: None) == '{"ok":1}'
    assert picked == ["k1", "k2"], "补试没换人：%s" % picked
    assert p.snapshot()["cooling"] == 0, "5xx 被当成限流去冷却了"

    assert D.call_llm(FirstKeyIsBad(), "p", p, b, "generate", sleep=lambda s: None) == '{"ok":1}'
    assert picked[2] != "k1", "刚 5xx 的 key 还是第一个被拿到，每趟都白补一发：%s" % picked
    assert b.snapshot()["upstream_errors"] == 1, "第二次不该再算一次上游故障：%s" % b.snapshot()
