# -*- coding: utf-8 -*-
"""spec 复核后确认的 7 处不合规，逐条先写红判据（本文件在实现前应全红）。

来源：独立 spec 合规审查（对提交 1738662）+ 我自己复跑确认。审查员的数字一律自己重验过：
1. `source_sha` 恒为空串 —— spec §5 顶层字段之一，测试只断"键存在"，键值全是 ""；
2. 429 退避没有 120s 封顶 —— spec §4 明写"退避封顶 120s"，一个大的 Retry-After 会让该 key 整夜报废；
3. CAS 协议第 2 步（幂等跳过）是死代码 —— night_run 调 publish 从不传 last_sha，
   当夜原地重试会重复提交同一份产物；
4. 超预算丢弃只记 url 不记理由 —— spec §3 要求 `dropped_articles` 带原因；
5. 内容优质判定"不由生成方自评"只做了形式 —— 全文件没有 source_quality/跨源同稿/AIHOT
   任何机械输入，`basis` 只查非空，等于模型想写什么写什么（现网"质量词 ≈0"会原样上线）；
6. 一批契约数字（因果字段 170 字与上限 6、预测 ≤80 字与上限 4、citations 区间、
   degraded 超 200 字）没有任何测试钉着，删掉不红；
7. 页面上的"命中状态"不可达 —— 结算只改账本行，产物里 forecasts 的 status 永不回填。
"""
import hashlib
import json
import os
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _para(n):
    body = "论证与数据推演" * max(1, n // 8)
    return body + "，但该判断仍受样本量与统计口径限制。"


def _event(**over):
    cites = [{"id": "c%d" % (i + 1), "url": "https://x.test/%d" % i, "source": "公众号:A",
              "chars_used": 4000, "full_len": 5706} for i in range(6)]
    ev = {
        "id": "evt1", "topic": "ai", "title": "一条足够具体的标题",
        "narrative": "\n\n".join(_para(500) for _ in range(7)),
        "claims": [{"text": "论断%d" % i, "kind": "causal", "evidence": ["c1", "c2"]}
                   for i in range(5)],
        "causal_chains": [{"trigger": "触发", "mechanism": "机制", "outcome": "结果",
                           "confidence": 0.6, "evidence": ["c1", "c2"]} for _ in range(3)],
        "forecasts": [{"claim": "预计三个月内出现跟随者", "horizon_days": 7,
                       "check_metric": "同类竞品发布数≥3", "status": "pending"}],
        "quality": {"verdict": "一手", "score": 82, "why": "依" * 60,
                    "basis": ["sig:c1"]},
        "citations": cites,
    }
    ev.update(over)
    return ev


def _ok(ev):
    """不带 valid_basis 的调用：这些判据的涨跌必须只归因于被测试的那一条数字。"""
    return D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]})


# ── 6. 契约数字必须逐条能红（这批先红，因为 validate_event 还没接 valid_basis） ──

def test_causal_field_over_170_chars_is_rejected():
    ev = _event()
    ev["causal_chains"][0]["mechanism"] = "长" * (D.CHAIN_FIELD_MAX + 1)
    ok, fails = _ok(ev)
    assert not ok and any("超长" in f for f in fails), fails


def test_causal_chains_above_six_is_rejected():
    ev = _event(causal_chains=[{"trigger": "t", "mechanism": "m", "outcome": "o",
                                "evidence": ["c1"]} for _ in range(7)])
    ok, fails = _ok(ev)
    assert not ok, "7 条因果链也算合格：上限 6 没生效"


def test_forecast_claim_over_80_chars_is_rejected():
    ev = _event()
    ev["forecasts"][0]["claim"] = "预" * (D.FORECAST_CLAIM_MAX + 1)
    ok, fails = _ok(ev)
    assert not ok and any("claim" in f for f in fails), fails


def test_forecasts_above_four_is_rejected():
    ev = _event(forecasts=[{"claim": "c", "horizon_days": 3, "check_metric": "条数≥1",
                            "evidence": ["c1"]} for _ in range(5)])
    ok, fails = _ok(ev)
    assert not ok, "5 条预测也算合格：上限 4 没生效"


@pytest.mark.parametrize("n", [4, 13])
def test_citations_must_stay_within_bounds(n):
    cites = [{"id": "c%d" % (i + 1), "url": "https://x.test/%d" % i, "source": "s",
              "chars_used": 4000} for i in range(n)]
    ev = _event(citations=cites)
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in cites},
                                valid_basis={"sig:c1"})
    assert not ok, "citations=%d 仍算合格：区间 [%d,%d] 没生效" % (n, D.CITE_MIN, D.CITE_MAX)


def test_degraded_narrative_over_cap_is_rejected():
    ev = _event(narrative="快" * (D.DEGRADED_NARR_MAX + 50), forecasts=[],
                degraded_reason="证据不足")
    ok, fails = _ok(ev)
    assert not ok, "快讯正文超 200 字仍算合格：degraded 上限没生效"


# ── 5. 优质判定必须有机械输入，不许模型自报 ────────────────────────────────

def test_quality_basis_must_reference_a_supplied_signal():
    """basis 只查非空 = 模型写"来源优质"三个字就过关。必须引用确实喂给它的信号 id。"""
    ev = _event()
    ev["quality"]["basis"] = ["我觉得这是一手报道"]
    ok, fails = D.validate_event(ev, valid_ids={c["id"] for c in ev["citations"]},
                                valid_basis={"sig:c1"})
    assert not ok, fails
    good = _event()
    ok2, f2 = D.validate_event(good, valid_ids={c["id"] for c in good["citations"]},
                              valid_basis={"sig:c1"})
    assert ok2, "引用了真实信号却仍被判不过：%s" % f2


def test_source_quality_signal_loader_distinguishes_404_from_corruption():
    import urllib.error

    def not_found(url, timeout=90):
        raise urllib.error.HTTPError(url, 404, "no", {}, None)

    assert D.load_source_quality(not_found) == {}, "第一夜没有 source_quality.json 必须能起"

    def corrupt(url, timeout=90):
        return b'{"tiers": [1,2'

    with pytest.raises(ValueError):
        D.load_source_quality(corrupt)


def test_quality_signals_are_computed_from_the_pool(tmp_path):
    """跨源同稿计数：同一事件被 N 个不同源搬运，是"通稿/转载"的机械证据，不能靠模型猜。"""
    arts = {}
    title = "某厂商开放权重引发许可与商业化争议"
    for i, s in enumerate(("srcA", "srcB", "srcC")):
        u = "https://%s.test/%d" % (s, i)
        arts[u] = {"url": u, "source": s, "title": title,
                   "text": "证据正文。" * 1500, "has_full": True}
    sig = D.quality_signals(list(arts.values()), {})
    assert sig, "没算出任何优质判定信号"
    dup = [v for v in sig.values() if v.get("dup_sources")]
    assert dup and max(v["dup_sources"] for v in dup) >= 2, sig


# ── 1/2/3/4/7 运行时与提交侧 ───────────────────────────────────────────────

def _pool(n_src=6, chars=6000):
    # 6 篇是"能合格"的最小规模：契约要 citations 5-12 条，
    # 而 id 是按篇编号的 —— 只给 3 篇的夹具结构上永远过不了契约，
    # 那样测到的是夹具尺寸而不是被判据。
    # （证据门仍按 3 个独立源计，6 篇里前 3 篇即满足，不影响本文件其它判据。）
    arts, links = {}, []
    for i in range(n_src):
        u = "https://s%d.test/a%d" % (i, i)
        arts[u] = {"url": u, "source": "s%d" % i, "title": "事件标题%d" % i,
                   "text": "长文证据。" * (chars // 5), "has_full": True}
        links.append(u)
    return arts, links


def _anchor(links, n=1):
    return json.dumps({"date": "2026-09-22", "events": [
        {"id": "e%d" % i, "title": "事件标题%d" % i, "topic": "ai", "summary": "摘",
         "key_links": links[i * 3:(i + 1) * 3]} for i in range(n)]}, ensure_ascii=False)


def _run(tmp_path, **kw):
    arts, links = _pool()
    kw.setdefault("anchor_raw", _anchor(links))
    kw.setdefault("pool", arts)
    # pred_raw 必须能被调用方覆盖：本文件的对账判据要喂一份"上一夜已结算"的账本，
    # 写死成关键字参数就会撞出 "multiple values for keyword argument"。
    return D.night_run(purpose=kw.pop("purpose", "test"), client=kw.pop("client", D.FakeClient()),
                       out_dir=str(tmp_path / "ns"), keys=["k1", "k2", "k3"],
                       date_str="2026-09-23", log=lambda s: None,
                       sleep=lambda s: None,
                       pred_raw=kw.pop("pred_raw", ""), quality_raw=kw.pop("quality_raw", {}), **kw)


def test_source_sha_records_the_anchor_bytes(tmp_path):
    """spec §5 要 source_sha —— 用来回答"夜场用的是哪一版白天锚点"。恒空串等于没记。"""
    arts, links = _pool()
    anchor = _anchor(links)
    out = _run(tmp_path, pool=arts, anchor_raw=anchor)
    sha = out["payload"]["budget"]["source_sha"]
    assert sha, "source_sha 是恒空字段"
    want = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
    assert want.startswith(sha) and 8 <= len(sha) <= len(want), \
        "source_sha 不是锚点字节的摘要前缀：%r" % sha


def test_429_backoff_is_capped_at_120s():
    """spec §4 退避封顶 120s：一个大 Retry-After 不该把一把 key 整夜废掉。"""
    cap = getattr(D, "BACKOFF_CAP_S", None)
    assert cap == 120, "缺退避封顶常数（实为 %r）" % cap
    clock = {"t": 0.0}
    p = D.KeyPool(["k1"], clock=lambda: clock["t"])
    applied = p.mark_429("k1", 3600)
    assert applied <= D.BACKOFF_CAP_S, applied
    clock["t"] = D.BACKOFF_CAP_S + 1
    assert p.acquire("generate") == "k1", "封顶之后 key 仍不可用"


def test_in_place_retry_does_not_commit_the_same_artifact_twice(tmp_path):
    """CAS 协议第 2 步（幂等跳过）必须是活代码：当夜原地重试不能重复提交同一份产物。"""
    calls = {"commit": 0, "ref": 0}

    class Api:
        def __init__(self):
            self.head = "h"
        def head_info(self): return self.head, "t_base"
        def create_blob(self, c): return "b" + hashlib.sha256(c).hexdigest()[:6]
        def create_tree(self, base, entries): return "t1"
        def create_commit(self, parent, tree, msg):
            calls["commit"] += 1; return "sha%d" % calls["commit"]
        def update_ref(self, sha, force=False):
            calls["ref"] += 1; self.head = sha; return True
        def is_ancestor(self, sha): return True

    class Realish:
        def complete(self, prompt, key=None, kind="generate"):
            return D.FakeClient().complete(prompt, key, kind)

    holder = {}
    def factory():
        holder.setdefault("api", Api())
        return holder["api"]

    _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory)
    assert calls["commit"] == 1, calls
    _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory)
    assert calls["commit"] == 1, "当夜重试又提交了一次（幂等跳过没生效）：%s" % calls


def test_dropped_articles_ship_with_their_reason(tmp_path):
    """spec §3：超预算要"丢整篇并记理由"。只记 url 不记理由，事后无法解释条目为何变短。"""
    arts, links = _pool(chars=6000)
    out = _run(tmp_path, pool=arts, anchor_raw=_anchor(links), budget_tokens=1200)
    ev = out["payload"]["events"][0]
    dropped = ev["context_stats"].get("dropped_articles")
    assert dropped, "超预算丢整篇却没落 dropped_articles"
    assert all((d.get("reason") or "").strip() for d in dropped), \
        "丢弃理由丢失：%s" % dropped
    assert all(d.get("url", "").startswith("https://") for d in dropped)


def test_forecast_status_is_visible_on_the_page(tmp_path):
    """spec §5：预测卡要含"到期与命中状态"。只把结算结果写进账本、产物里永远是 pending，
    页面上的"命中状态"就是一块永不翻牌的装饰。"""
    arts, links = _pool()
    c = D.FakeClient()
    _run(tmp_path, pool=arts, anchor_raw=_anchor(links), client=c)
    html = open(str(tmp_path / "ns" / "deep-insight.html"), encoding="utf-8").read()
    assert "到期" in html and ("2026-09" in html or "窗口" in html), \
        "预测卡上没有到期信息，无法核对"

    # 已结算的历史预测要在页面上露出来（拿一场带 hit 的账本跑一遍）
    hit_rows = "".join(json.dumps({"claim": "历史预测甲", "event_id": "e0", "horizon_days": 3,
                                  "check_metric": "条数≥1", "made_on": "2026-09-01",
                                  "status": "hit", "settled_on": "2026-09-20"},
                                 ensure_ascii=False) + "\n" for _ in range(1))
    _run(tmp_path / "b", pool=arts, anchor_raw=_anchor(links), pred_raw=hit_rows)
    html2 = open(str(tmp_path / "b" / "ns" / "deep-insight.html"), encoding="utf-8").read()
    assert "已命中" in html2, "账本里有已结算项，页面却仍只显示待验证"


def test_source_quality_tier_reaches_the_prompt(tmp_path):
    """白天的信源档位是 spec §2 点名的外证之一。night_run 把它读回来了，
    但若没传到 deepen_one，`tier` 这一路就永远是空的 —— 代码看着做了，实际空转，
    而且跨源同稿那一路还绿着，绿勾完全抓不到。"""
    seen = []

    class Spy(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            seen.append(prompt)
            return D.FakeClient.complete(self, prompt, key, kind)

    arts, links = _pool()
    _run(tmp_path, pool=arts, anchor_raw=_anchor(links), client=Spy(),
         quality_raw=json.dumps({"s0": {"tier": "T1"}, "s1": "T2"}, ensure_ascii=False))
    assert seen, "一条 prompt 都没发出去"
    assert any("白天档位" in p for p in seen), \
        "source_quality 的档位没进 prompt —— 外证被读回来了却死在参数表里"


def test_ancestor_check_rejects_diverged_and_behind():
    """spec §4 的"提交后终检"是防白天 auto-commit 吞提交的最后一道。
    compare 的 diverged/behind 恰恰就是"我们已被甩出主线"，收进来等于这道防线恒真。
    （变异体 R5 把四个状态全收回去，测试却全绿 —— 说明这条以前根本没测。）"""
    import urllib.error

    class Api(D.GithubDataApi):
        def __init__(self, status):
            self.status = status
            self.token = "t"
            self.repo = "o/r"
        def _req(self, method, path, payload=None):
            return {"status": self.status}

    for st, want in (("ahead", True), ("identical", True), ("diverged", False), ("behind", False)):
        assert Api(st).is_ancestor("sha1") is want, "status=%s 判成 %s" % (st, not want)

    class Gone(D.GithubDataApi):
        def __init__(self):
            self.token = "t"; self.repo = "o/r"
        def _req(self, method, path, payload=None):
            raise urllib.error.HTTPError("u", 409, "gone", {}, None)

    assert Gone().is_ancestor("sha1") is False, "compare 取不到就当作还在链上"


def test_no_key_run_is_refused_before_any_spending(tmp_path):
    """没有 key 时以前会 12 条 × 900s 空等到撞 job 上限，还留一个绿勾。
    必须一起床就抛 —— 变异体 R6 撤掉这个拒绝时，测试原来全绿。"""
    arts, links = _pool()
    with pytest.raises(RuntimeError):
        D.night_run(purpose="test", out_dir=str(tmp_path / "ns"), keys=[],
                    anchor_raw=_anchor(links), pool=arts, date_str="2026-09-23",
                    pred_raw="", log=lambda s: None, sleep=lambda s: None)


def test_changed_artifact_is_committed_again(tmp_path):
    """幂等跳过只许在"字节完全没变"时生效。
    只判断"有没有上次记录"就把内容不同的产物也跳过 = 新产物永远上不去。"""
    calls = {"commit": 0}

    class Api:
        def __init__(self): self.head = "h"
        def head_info(self): return self.head, "t_base"
        def create_blob(self, c): return hashlib.sha256(c).hexdigest()[:8]
        def create_tree(self, base, entries): return "t1"
        def create_commit(self, parent, tree, msg):
            calls["commit"] += 1
            return "sha%d" % calls["commit"]
        def update_ref(self, sha, force=False): self.head = sha; return True
        def is_ancestor(self, sha): return True

    class Realish:
        def complete(self, prompt, key=None, kind="generate"):
            return D.FakeClient().complete(prompt, key, kind)

    arts, links = _pool()
    holder = {}
    factory = lambda: holder.setdefault("a", Api())
    _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory,
         pool=arts, anchor_raw=_anchor(links))
    assert calls["commit"] == 1, calls
    # 第二夜：锚点多出一个事件 ⇒ 产物内容必然不同 ⇒ 必须再提交一次
    arts2, links2 = _pool()
    _run(tmp_path, purpose="publish", client=Realish(), api_factory=factory,
         pool=arts2, anchor_raw=_anchor(links2, n=2))
    assert calls["commit"] == 2, "内容变了却没再提交（幂等判断退化成有无记录）: %s" % calls


def test_pool_discovers_more_than_three_chunks():
    """分块数是白天按体积算的（`n_chunks = ceil(total/max_size)`），夜场写死 3 块
    等于"第 4 块一出现就静默少读三分之一全文池"。现网实测第 3 块只剩 2.4% 余量，
    而塌陷的表现是"全部证据不足→全降级"，不是报错。"""
    def get(url, timeout=90):
        key = url.split("?")[0]
        i = int(key.split("rss-data-")[-1].replace(".js", ""))
        if i > 3:
            raise urllib.error.HTTPError(url, 404, "no", {}, None)
        return ('(window.__CHUNKS=window.__CHUNKS||[])[%d]={"sources":[{"items":[{'
                '"title":"块%d标题","link":"https://s.test/%d","content":"证据正文。"'
                ',"pub_date":"2026-09-22T10:00:00Z"}]}]}' % (i, i, i)).encode("utf-8")

    pool, bad = D.load_rss_pool(get=get, log=lambda s: None)
    assert "https://s.test/3" in pool, "只读到前几块：分块数被写死了"
    assert bad == 0, bad


def test_pool_stops_on_404_but_fails_on_500():
    """404 是"到头了"，500 是"证据读不到"。把后者也当前头，
    就会拿着半套证据面跑完整场，产出一份看起来正常的降级报告。"""
    def get(url, timeout=90):
        key = url.split("?")[0]
        if key.endswith("rss-data-0.js"):
            return ('(window.__CHUNKS=window.__CHUNKS||[])[0]={"sources":[{"items":[{'
                    '"title":"甲","link":"https://s.test/a","content":"正文。"'
                    ',"pub_date":"2026-09-22T10:00:00Z"}]}]}').encode("utf-8")
        if key.endswith("rss-data-1.js"):
            raise urllib.error.HTTPError(url, 500, "boom", {}, None)
        raise urllib.error.HTTPError(url, 404, "no", {}, None)

    with pytest.raises(IOError):
        D.load_rss_pool(get=get, log=lambda s: None, retries=1)
