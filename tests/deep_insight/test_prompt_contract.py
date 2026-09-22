# tests/deep_insight/test_prompt_contract.py
# -*- coding: utf-8 -*-
"""prompt 与读取路径本身的判据。

为什么单开一个文件：这三条都是"代码写了、但没有任何东西钉着"的形态 ——
首夜真跑 0 合格里就有一条属于它（prompt 没说 evidence 取哪些编号，模型只能猜，
条条判死）。这类约束删掉不会让任何现有测试变红，所以必须先有判据再改提示词。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _ctx(n=6):
    arts = []
    for i in range(n):
        arts.append({"url": "https://s%d.test/a%d" % (i % 3, i), "source": "s%d" % (i % 3),
                     "title": "T%d" % i, "text": "证据正文" * 1200, "has_full": True})
    ctx = D.assemble_context(arts, budget_tokens=400000)
    ctx["ids"] = {"c%d" % (i + 1): a["url"] for i, a in enumerate(ctx["articles"])}
    ctx["signals"] = D.quality_signals(ctx["articles"], {})
    return ctx


def test_prompt_pins_the_evidence_id_range_for_claims_and_chains():
    """首夜 3/3 死在"claim 引用了不存在的 chunk"：prompt 只给 citations 规定了编号范围，
    claims[].evidence 与 causal_chains[].evidence 从没说过 —— 模型只能猜。
    这条判据保证以后谁删这句约束会立刻红，而不是等一晚真跑才发现。"""
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": []}
    p = D.build_prompt(ev, _ctx())
    idseg = re.search(r"只能从[^。]*?((?:c\d+，?,?\s*){3,}c\d+)", p)
    assert idseg, "prompt 里没有可引用的编号清单"
    low = p.lower()
    for field in ("claims", "causal_chains"):
        seg = low[low.find(field):low.find(field) + 260]
        assert seg and ("evidence" in seg) and ("编号" in seg or "只能" in seg or "c" in seg), \
            "%s 的 evidence 取值范围没写进 prompt" % field


def test_prompt_tells_the_model_which_ids_basis_may_use():
    """§2 第 4 行"不由生成方自评"要落地：喂给模型的完整提示里，既要有可引用的 sig 清单，
    又要把 basis 和这份清单绑起来。

    不要求它出现在某一段里 —— 外证清单本来就是拼在 prompt 末尾的，
    按段落位置断言只会得到一个假阳性。
    """
    ctx = _ctx()
    p = D.build_prompt({"title": "t", "topic": "ai", "summary": "s", "links": []}, ctx)
    full = p + D.signals_note(ctx)
    assert "sig:c1" in full, "prompt 里没有可引用的 sig 编号清单"
    assert ("basis" in full) and ("sig" in full[full.find("basis"):full.find("basis") + 300]
                                 or "外证" in full), "basis 与 sig 清单之间没有绑定说明"


def test_nightly_reads_of_its_own_artifacts_bypass_the_cdn_cache():
    """Pages 现测 max-age=600（404 也缓存）。夜场是"读自己上一夜提交的东西→整库写回"，
    读到旧内容就等于把历史覆盖掉。

    判在缝上，不判实现：只看夜场去取"自己写的三个远端文件"时，URL 有没有带上
    cache-buster；至于是在调用点包的还是在函数内部包的，随它去。
    """
    seen = []

    def get(url, timeout=90):
        seen.append(url)
        return b"{}"

    for fn, arg in ((D.load_prev_predictions, D.PREDICTIONS_URL),
                    (D.load_source_quality, None)):
        try:
            fn(get, arg) if arg is None else fn(get, arg)
        except Exception:
            pass
    own = [u for u in seen if "predictions.jsonl" in u or "source_quality.json" in u]
    assert own, "两条自写产物的读路径一次都没走到，判据空跑"
    for u in own:
        assert "cb=" in u, "读自己上一夜提交的东西却可能被 CDN 命中缓存：%s" % u


def test_citation_urls_reaching_the_artifact_are_browser_safe():
    """引用链接的不变量是"进产物的那条 URL 在浏览器里指向的就是它"，不是某个函数存在。

    现网实测 31/9628 条 rss url 带非 ASCII 或 mojibake；含空白的串会让链接断在空格处。
    白天两条链路各有清洗（`api/rss.js` 的 cleanLink、构建侧的 _clean_link），
    口径不一致时同一篇稿子会在两处显示成两个链接。
    """
    ids = {"c1": "https://a.test/%E4%B8%AD", "c2": "https://a.test/has space/x",
           "c3": "https://a.test/plain"}
    cand = {"citations": ["c1", "c2", "c3"]}
    out = D.normalize_candidate(dict(cand), ids)
    urls = [c["url"] for c in out["citations"]]
    assert all(not any(ch.isspace() for ch in u) for u in urls), \
        "含空白的 URL 进了产物：浏览器会在空格处截断，等于死链" % urls
    for u in urls:
        assert u.startswith("http://") or u.startswith("https://"), "相对链接上了屏：" + u
    assert all(ord(ch) < 128 for u in urls for ch in u), "非 ASCII 未经百分号编码：%s" % urls


def test_normalize_candidate_preserves_string_rows_as_objects():
    """归一必须"留下内容"，不是"扔掉算完"。

    变异体自证时 R1（把字符串行的分支关掉）存活了 —— 说明当时没有任何判据钉住这一步：
    丢掉字符串行同样不崩、同样降级，看起来等价。但它把模型的论断整条抹掉，
    事后 `contract_fails` 只会说"claims 0 条"，读日志的人以为模型没写，
    实际是我们没接住。所以直接钉函数契约。
    """
    ids = {"c1": "https://a.test/1"}
    out = D.normalize_candidate({"claims": ["论断一"], "causal_chains": ["因为A所以B"],
                                 "forecasts": ["三个月内出现跟随者"]}, ids)
    assert out["claims"] and isinstance(out["claims"][0], dict), out["claims"]
    assert out["claims"][0].get("text") == "论断一", "字符串论断被丢弃而不是归一"
    assert out["causal_chains"][0].get("mechanism") == "因为A所以B", out["causal_chains"]
    assert out["forecasts"][0].get("claim") == "三个月内出现跟随者", out["forecasts"]
    # 归一之后仍必须是"必然过不了契约"的形态：不许因为填了字段就蒙混合格
    ok, fails = D.validate_event(dict(out, id="e1", title="t", topic="ai",
                                       narrative="反证：口径受限。" * 900,
                                       citations=[{"id": "c1", "url": "https://a.test/1"}] * 5),
                                valid_ids=ids, valid_basis={"sig:c1"})
    assert not ok, "字符串行被填成对象后竟然算合格"
    """模型给不存在的编号时，不许回退去用它自带的 URL —— 那是把"假链接即硬失败"
    降级成只校验标签，实测会漏出编造域名进产物。"""
    ids = {"c1": "https://real.test/1", "c2": "https://real.test/2"}
    cand = {"citations": [{"id": "c1", "url": "https://evil.test/x"},
                          "c2", "https://fabricated.test/nope", {"id": "c9"}]}
    out = D.normalize_candidate(dict(cand), ids)
    assert [c["id"] for c in out["citations"]] == ["c1", "c2"], out["citations"]
    assert all(c["url"].startswith("https://real.test") for c in out["citations"]), \
        "模型自带 URL 被采信"
