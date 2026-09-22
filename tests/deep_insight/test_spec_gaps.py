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
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
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

    assert D.load_source_quality(not_found) == {}, "读不到外证表（第一夜/白天没写）必须能起"

    def corrupt(url, timeout=90):
        return b'{"tiers": [1,2'

    with pytest.raises(ValueError):
        D.load_source_quality(corrupt)


# ── 优质判定的"机械外证"在现网是恒缺的：来源是断链，键形还不对 ──────────────

def test_quality_loader_reads_a_published_snapshot_shape():
    """白天的质量表必须落在**真的会发布**的产物上。

    `source_quality.json` 由 `build_rss_aggregator._save_source_quality` 写出来，
    但从不在 `update.yml` 的 `git add` 清单里（Pages 实测恒 404），夜场引用它等于
    挂一条永久断链。同一份评分的另一半在 `analysis_snapshot.json` 的 `quality` 字段
    （现网实测 968 个源、0–100 分）， loader 要把它取出来而不是整份返回。
    """
    body = json.dumps({"generated_at": "2026-09-22T00:00:00+08:00",
                       "quality": {"agihunt_0": 84.9, "openai_blog_1": 72.5}})
    got = D.load_source_quality(lambda url, timeout=90: body.encode("utf-8"))
    assert got == {"agihunt_0": 84.9, "openai_blog_1": 72.5}, got

    # 解析得动但没有 quality 字段 = 白天的产物形状变了，必须炸：
    # 当成空表会让所有源静默退化成"无外证"，而"无外证"与"低质"是两个结论。
    with pytest.raises(ValueError):
        D.load_source_quality(lambda url, timeout=90: b'{"keywords": {}}')


def test_nightly_quality_input_is_something_the_daytime_publishes():
    """把"外证来源必须是已发布产物"写成跨文件判据，而不是钉一个字符串。

    只断 URL 常量的话，哪天白天把 `analysis_snapshot.json` 从提交清单里摘掉，夜场又会
    悄悄变回恒 404（这次的故障形态）。所以直接读 `update.yml` 的 `git add` 行来判。
    """
    yml = open(os.path.join(ROOT, ".github", "workflows", "update.yml"),
               encoding="utf-8").read()
    published = " ".join(re.findall(r"git add ([^\n]+)", yml))
    for url in (D.ANCHOR_URL, D.SOURCE_QUALITY_URL):
        base = url.rstrip("/").split("/")[-1].split("?")[0]
        assert base in published, \
            "夜场要读 %s，但白天的提交清单里没有它 —— 现网只会 404" % base


def test_source_key_survives_normalization_into_the_quality_join():
    """键形也要对得上：质量表按 `agihunt_0` 这种源键索引，而条目自己的 `source` 是显示名。

    `parse_chunk` 把分块组的 `key` 塞进 `source_key`，但 `_article_from` 只保留
    url/source/title/text/has_full 五个字段，归一这一步就把它丢了；于是
    `_source_key_of` 退回显示名去查表，命中恒为 0。
    """
    chunk = ('// chunk 0\n(window.__CHUNKS=window.__CHUNKS||[])[0]=' + json.dumps(
        {"sources": [{"key": "agihunt_0", "name": "AGI Hunt", "items": [
            {"title": "某模型开放权重引发许可争议", "link": "https://a.test/1",
             "source": "AGI Hunt", "full_content": "正文" * 3000}]}]},
        ensure_ascii=False))
    arts = D.parse_chunk(chunk)
    assert arts[0].get("source_key") == "agihunt_0", \
        "归一后源键被丢弃，只剩显示名：%s" % sorted(arts[0])
    assert D._source_key_of(arts[0]) == "agihunt_0"
    q = {"agihunt_0": 84.9}
    assert D._quality_tier(q, D._source_key_of(arts[0])) == 84.9, "拿显示名查表：外证恒缺"
    sig = D.quality_signals(arts, q)
    tiers = [v.get("tier") for v in sig.values()]
    assert 84.9 in tiers, "信源质量分没进信号，优质判定又回到模型自评：%s" % sig


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


def test_injected_quality_document_shape_matches_the_http_loader(tmp_path):
    """注入路径与 HTTP 路径必须收成同一种形状，否则"传了产物"仍等于"没有外证"。

    现网那份是 `{"generated_at": …, "quality": {…}}`：loader 取的是 `quality` 子表，
    而 `quality_raw` 这条路原本直接用整份文档 —— 于是键全对不上、查表命中恒 0，
    而且一声不响。线上"外证恒缺"踩过的形态，注入这条路会原样复现。
    """
    seen = []

    class Spy(D.FakeClient):
        def complete(self, prompt, key=None, kind="generate"):
            seen.append(prompt)
            return D.FakeClient.complete(self, prompt, key, kind)

    arts, links = _pool()
    doc = json.dumps({"generated_at": "2026-09-22T00:00:00+08:00",
                      "quality": {"s0": {"tier": "T1"}, "s1": "T2"}}, ensure_ascii=False)
    _run(tmp_path, pool=arts, anchor_raw=_anchor(links), client=Spy(), quality_raw=doc)
    assert any("白天档位" in p for p in seen), \
        "传整份快照时分数没进 prompt：注入形状与 HTTP 形状分叉了"


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
    必须一起床就抛 —— 变异体 R6 撤掉这个拒绝时，测试原来全绿。

    "一起床"要用出网次数来判，不是用异常类型：锚点/分块池/质量快照三连读是几十 MB，
    先读满再抛等于把钱花完才报告没钱，而那种顺序同样会抛 RuntimeError。
    """
    arts, links = _pool()
    reads = []

    def tripwire(url, timeout=90):
        reads.append(url)
        raise AssertionError("无 key 的场不许出网：%s" % url)

    with pytest.raises(RuntimeError):
        D.night_run(purpose="test", out_dir=str(tmp_path / "ns"), keys=[],
                    anchor_raw=_anchor(links), pool=arts, date_str="2026-09-23",
                    pred_raw="", get=tripwire, log=lambda s: None, sleep=lambda s: None)
    assert not reads, "抛之前已经读了 %d 个远端产物：%s" % (len(reads), reads[:3])


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


def test_chunk_retry_waits_between_attempts():
    """现网 run 35735624747 的第一趟死在 `ssl.SSLEOFError` 这种瞬时抖动上。
    重试若紧挨着再试一次，等于在同一个坏窗口里撞两次 —— 4m51s 就这么红掉的。"""
    n = {"i": 0}
    body = ('(window.__CHUNKS=window.__CHUNKS||[])[0]={"sources":[{"items":[{'
            '"title":"甲","link":"https://s.test/a","content":"正文。"'
            ',"pub_date":"2026-09-22T10:00:00Z"}]}]}').encode("utf-8")

    def get(url, timeout=90):
        base = url.split("?")[0]
        if base.endswith("rss-data-0.js"):
            if n["i"] == 0:
                n["i"] += 1
                raise urllib.error.URLError("EOF occurred in violation of protocol")
            return body
        raise urllib.error.HTTPError(url, 404, "no", {}, None)

    slept = []
    pool, bad = D.load_rss_pool(get=get, log=lambda s: None, retries=2, sleep=slept.append)
    assert slept, "两次重试之间没有退避：瞬时超时会被连撞两次后直接判整场失败"
    assert min(slept) >= 1.0, "退避小到等于没有：%s" % slept
    assert "https://s.test/a" in pool and bad == 0, (sorted(pool), bad)


def test_string_shaped_evidence_is_not_iterated_character_wise():
    """现网 evt_20260922_014 的产物里写着 `claim 引用了不存在的 chunk：c`。
    合法编号只有 c1..c12 —— 冒出单字母 `c` 只有一种解释：模型把 evidence 给成字符串
    "c1"，实现里 `for e in evidence` 就逐字符炸成 c、1。上一轮只修了 citations 的形状，
    漏了 evidence，于是把好引用判成假引用，白烧两轮重写。"""
    ids = {"c%d" % (i + 1): "https://x.test/%d" % i for i in range(6)}
    cand = {
        "id": "e1", "topic": "ai", "title": "标题",
        "narrative": "\n\n".join(_para(500) for _ in range(7)),
        "claims": [{"text": "甲", "kind": "causal", "evidence": "c1"},
                   {"text": "乙", "kind": "causal", "evidence": "c2, c3"},
                   {"text": "丙", "kind": "trend", "evidence": ["c3"]}],
        "causal_chains": [{"trigger": "t", "mechanism": "m", "outcome": "o",
                           "evidence": "c4 c5"},
                          {"trigger": "t2", "mechanism": "m2", "outcome": "o2",
                           "evidence": ["c5", "c6"]}],
        "forecasts": [{"claim": "三个月内出现跟随者", "horizon_days": 3,
                       "check_metric": "同类发布数≥3"}],
        "quality": {"verdict": "一手", "score": 80, "why": "依" * 40, "basis": ["sig:c1"]},
        "citations": [{"id": "c%d" % (i + 1), "url": "https://x.test/%d" % i} for i in range(6)],
    }
    fixed = D.normalize_candidate(cand, ids)
    assert fixed["claims"][0]["evidence"] == ["c1"], fixed["claims"][0]
    assert set(fixed["claims"][1]["evidence"]) == {"c2", "c3"}, fixed["claims"][1]
    assert fixed["causal_chains"][0]["evidence"] == ["c4", "c5"], fixed["causal_chains"][0]
    ok, fails = D.validate_event(fixed, valid_ids=set(ids), valid_basis={"sig:c1"})
    assert ok, fails


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


def test_generated_at_carries_exactly_one_valid_offset():
    """现网产物 run 35749459676 的 `generated_at` 实测是
    `2026-09-22T23:52:05+00:00+08:00` —— 两个偏移量被拼在一起。

    根因是 `now_bj_iso()` 拿的是**带 tzinfo 的** UTC 时刻，加 8 小时后 tzinfo 仍是 UTC，
    `isoformat()` 于是自己写了 `+00:00`，代码再手拼一个 `+08:00`。
    这不是排版小事：spec §5 把这个字段交给下游读（页面"更新于"、历史归档、
    以及任何 `fromisoformat` 的消费方），双偏移既解析不了、也容易被按 UTC 误读成 8 小时。
    """
    s = D.now_bj_iso()
    assert s.count("+") == 1 and s.endswith("+08:00"), "偏移量被拼了两次：%s" % s
    dt = datetime.fromisoformat(s)          # 解析不了就是红：字段必须可被标准库读
    assert dt.utcoffset() == timedelta(hours=8), dt.utcoffset()
    # 数值本身也得是"北京墙上时间"，不能只挂个 +08:00 标签却填 UTC 的数字
    skew = (dt - datetime.now(timezone.utc)).total_seconds()
    assert abs(skew) < 120, "挂 +08:00 却写着别的时刻：%s 与真实时刻差 %.0fs" % (s, skew)
    assert dt.strftime("%Y-%m-%d") == (
        datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


# ── 对抗审查 P0：一次瞬时错误毁整晚 / 撞墙钟时"做完的照样发布" ──────────────

class _Flaky:
    """第二条事件的 generate 抛 5xx。真跑一夜里这属于最常见的瞬时错误。"""

    def __init__(self):
        self.inner = D.FakeClient()
        self.n = 0

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "generate":
            self.n += 1
            if self.n == 2:
                raise RuntimeError("Agnes HTTP 502")
        return self.inner.complete(prompt, key=key, kind=kind)


def test_one_transient_error_does_not_destroy_the_whole_night(tmp_path):
    """产物在循环之后才落盘，所以异常穿出循环 = 钱花完、JSON/HTML 一个都没有。

    要求的不是"容忍"，是"记账着容忍"：挂了几条必须能在产物里读到，
    否则"三条全挂"与"三条都没排上"长得一模一样。
    """
    arts, links = _pool()
    out = _run(tmp_path, client=_Flaky(), pool=arts, anchor_raw=_anchor(links, 2))
    doc = json.load(open(out["json"], encoding="utf-8"))
    done = [e["id"] for e in doc["events"]]
    assert len(done) >= 1, "一条 5xx 把已经做完的条目也带走了：%s" % done
    assert doc.get("failed_items"), "吞了异常却不记账：%s" % sorted(doc)
    assert os.path.exists(out["html"]) and os.path.exists(out["json"])


def test_wallclock_stop_publishes_what_it_finished_and_says_why():
    """§4 明写"撞墙钟主动收口时，已做完的照样发布"。

    旧实现只把 `llm_calls >= call_cap` 当作主动收口，于是墙钟到点那一夜
    `published={'status':'blocked'}`、提交 0、退出码 0 —— 一份成果都上不了线还全绿。
    另外两个原因也不能共用一个名字：调用预算不够要加条目预算，窗口不够要提并发，
    下一步动作相反。
    """
    r = D.missing([{"id": "e1"}, {"id": "e2"}], [{"id": "e1"}], stop="wallclock")
    assert [x["reason"] for x in r] == ["not_run:wallclock"], r
    assert D.missing([{"id": "e1"}], [])[0]["reason"] == "not_run:incomplete"
    assert D.can_publish([{"id": "e1"}, {"id": "e2"}], [{"id": "e1"}],
                         budget_used_calls=3, call_cap=80, stopped_by_cap=True) is True
    assert D.can_publish([{"id": "e1"}, {"id": "e2"}], [{"id": "e1"}],
                         budget_used_calls=3, call_cap=80, stopped_by_cap=False) is False, \
        "没撞任何预算的半成品也能上线"


def test_remaining_window_shrinks_the_per_item_wait_budget(tmp_path, monkeypatch):
    """§4 的"单条目等待 ≤900s"必须是**条目级**预算，不是每次调用各领 900s。

    一条事件最多 generate×3 + judge×1，四次 900s 就是 60 分钟，而墙钟闸只在循环顶问 ——
    单条就能把整晚余量吃穿（对抗审查 P0-1）。所以传进 `deepen_one` 的 `wait_cap_s`
    必须随剩余窗口缩水。
    """
    seen = []
    real = D.deepen_one

    def spy(ev, pool, client, budget, kp, **kw):
        seen.append(kw.get("wait_cap_s"))
        kw["wait_cap_s"] = 1
        return real(ev, pool, client, budget, kp, **kw)

    monkeypatch.setattr(D, "deepen_one", spy)
    arts, links = _pool()
    _run(tmp_path, pool=arts, anchor_raw=_anchor(links), wait_cap_s=900)
    assert seen and seen[0] == 900, "窗口充裕时不该缩：%s" % seen
    seen.clear()
    monkeypatch.setattr(D.Budget, "elapsed_s", lambda self: self.time_cap_s - 30)
    _run(tmp_path / "b", pool=arts, anchor_raw=_anchor(links), wait_cap_s=900)
    assert seen and 29.0 <= seen[0] <= 31.0, "只剩 30s 却仍按 900s 派发：%s" % seen


def test_wallclock_cutoff_in_publish_mode_actually_ships_what_it_finished(tmp_path, monkeypatch):
    """上一条只证明 `can_publish` 认这次收口；这条证明 night_run 真的把信号传给它。

    接线断掉的形态很隐蔽：夜场跑完 1/2 条、`not_run` 记满、产物写好、
    然后 `published={'status':'blocked'}`、提交 0、退出码 0 —— 一整晚的成果一个字节都上不了线，
    而 Actions 全绿。变异体 `stopped_by_cap=False` 就是这条要抓的。
    """
    answers = [False] + [True] * 20
    monkeypatch.setattr(D.Budget, "over_time", lambda self: answers.pop(0))
    calls = {"commit": 0}

    class Api:
        head = "h0"

        def head_info(self):
            return self.head, "b0"

        def create_blob(self, content):
            return "bl%d" % len(content)

        def create_tree(self, base, entries):
            return "t1"

        def create_commit(self, parent, tree, msg):
            calls["commit"] += 1
            return "sha%d" % calls["commit"]

        def update_ref(self, sha, force=False):
            self.head = sha
            return True

        def is_ancestor(self, sha):
            return True

    class Realish:
        def complete(self, prompt, key=None, kind="generate"):
            return D.FakeClient().complete(prompt, key, kind)

    arts, links = _pool()
    holder = {}
    out = _run(tmp_path, purpose="publish", client=Realish(),
               api_factory=lambda: holder.setdefault("a", Api()),
               pool=arts, anchor_raw=_anchor(links, 2))
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert len(doc["events"]) == 1 and len(doc["not_run"]) == 1, (
        len(doc["events"]), doc["not_run"])
    assert calls["commit"] == 1, "撞墙钟收口却没提交：%s / published=%s" % (
        calls, out.get("published"))
    assert (out.get("published") or {}).get("status") != "blocked", out.get("published")


class _Garbage:
    """返回一段永远解析不出来的文本（不是空串 —— 空串是另一种故障）。"""

    def complete(self, prompt, key=None, kind="generate"):
        if kind == "judge":
            return json.dumps({"narrative": 0.9, "causal": 0.9,
                               "forecast": 0.9, "quality": 0.9})
        return "{" + "模型返回的不是合法 JSON：" * 60


def test_unparseable_reply_leaves_the_original_text_in_the_artifact(tmp_path):
    """现网 evt_20260923_008：十个字段全空、`truncated=0`，日志只说"narrative 0 字"。

    那等于把"我们读不出来"记成了"模型没写"。修解析之前先得能诊断，
    所以失败原文的头尾必须进产物（也解释了为什么这条判据断的是"有没有留证据"
    而不是"能不能解析"）。
    """
    arts, links = _pool()
    out = _run(tmp_path, client=_Garbage(), pool=arts, anchor_raw=_anchor(links))
    ev = json.load(open(out["json"], encoding="utf-8"))["events"][0]
    echo = ev.get("parse_echo") or {}
    assert echo.get("chars", 0) > 200, "解析失败却没留原文长度：%s" % echo
    assert echo.get("head") and echo.get("tail"), "只留长度等于什么都没留：%s" % sorted(echo)
    assert ev.get("degraded_reason"), echo


def test_workers_actually_run_events_concurrently_on_distinct_keys(tmp_path):
    """`KeyPool.workers` 以前只是个数字：全模块一处线程都没有，于是"每 key 一槽 /
    429 进冷却 / judge 让位生成"三条设计永远不可能被触发 —— 用户点名的多账号池优势
    只剩注释。这条判据断的是**真的重叠**，顺带抓"同一时刻两个线程拿同一个 key"
    （免费池按 key 限流，那样等于自己给自己造 429）。
    """
    import threading as _th
    import time as _t
    inner = D.FakeClient()
    st = {"live": {}, "peak": 0, "same_key": 0}
    lk = _th.Lock()

    class Concurrent:
        def complete(self, prompt, key=None, kind="generate"):
            with lk:
                st["live"][key] = st["live"].get(key, 0) + 1
                if st["live"][key] > 1:
                    st["same_key"] += 1
                st["peak"] = max(st["peak"], sum(st["live"].values()))
            _t.sleep(0.05)
            r = inner.complete(prompt, key=key, kind=kind)
            with lk:
                st["live"][key] -= 1
            return r

    arts, links = _pool(12)
    anchor = _anchor(links, 3)
    n_ev = len(json.loads(anchor)["events"])
    assert n_ev >= 2, "夹具只给出一条事件，重叠无从判起"
    out = _run(tmp_path, client=Concurrent(), pool=arts,
               anchor_raw=anchor, workers=3)
    doc = json.load(open(out["json"], encoding="utf-8"))
    assert len(doc["events"]) == n_ev, "并发路径把条目跑丢了：%s" % [e["id"] for e in doc["events"]]
    assert st["peak"] >= 2, "声明 workers=3 却从未重叠（peak=%d）—— 并发是假的" % st["peak"]
    assert st["same_key"] == 0, "同一时刻有两条任务共用一个 key"
    assert not doc.get("not_run"), "并发把 judge 饿死了（所有 key 都被生成占满）：%s" % doc["not_run"]


def test_every_declared_cli_flag_is_consumed():
    """死 flag 是这轮审查抓到的真实缺陷形态：`--workers` 声明了却没传进 `night_run`，
    于是 yml 里改档位完全无效，而 `--help` 看着一切正常。

    判据按"声明过就必须被读到"来写，不逐个点名 —— 新加 flag 忘了接线会直接红。
    """
    src = open(os.path.join(ROOT, "build_deep_insight.py"), encoding="utf-8").read()
    body = src[src.index("def main("):]
    declared = re.findall(r'ap\.add_argument\("--([a-z0-9-]+)"', body)
    assert declared, "解析不到 flag 清单，判据本身失效了"
    for name in declared:
        attr = "a." + name.replace("-", "_")
        assert attr in body, "声明了 --%s 却在 main 里没人读（死配置）" % name
