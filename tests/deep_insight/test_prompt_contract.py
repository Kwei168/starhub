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
    for field in ("claims", "causal_chains"):
        # 按条目切，不按"往后 260 个字符"切：后者会把邻条写长一点就判红，
        # 钉的是"每条要求里带着编号取值范围"，不是"这条恰好离那个词够近"。
        m = re.search(r"^- %s：(.*?)(?=^- |\Z)" % field, p, re.M | re.S)
        assert m, "prompt 里没有 - %s： 这条要求" % field
        seg = m.group(1)
        assert "evidence" in seg and ("编号" in seg or "只能" in seg) and "c" in seg, \
            "%s 的 evidence 取值范围没写进 prompt：%r" % (field, seg[:120])


def test_the_writer_sees_the_same_rubric_the_judge_scores_against():
    """现网读数（台账 §10.42）：58 条里 35 条死在"判分没过线"，五维里
    `forecast` 中位 0.475、`quality`/`density` 0.55 —— 而**评审用的五条标准从来没给过写的人**：
    `build_judge_prompt` 里那份 dims 文案只有 judge 看得见。
    第一趟写作拿不到评分口径，只能等 judge 打完分、重写那一趟才收到"哪一维弱"，
    等于白白烧掉一趟预算（`MAX_REGEN=2`）。
    这条判据同时是防分叉：judge 自己抄一份改写过的标准，红。
    """
    ev = {"title": "某事件", "topic": "ai", "summary": "s", "links": []}
    ctx = _ctx()
    crit = D.JUDGE_DIM_CRITERIA
    for d in D.JUDGE_DIMS:
        assert d in crit, "共享的评审标准里没有 %s：那一维等于没告诉写的人" % d
    assert crit in D.build_prompt(ev, ctx), "单趟生成的 prompt 里没有评审五维"
    assert crit in D.build_structure_prompt(ev, ctx, "正文" * 3000), \
        "补结构字段那一趟看不到评审标准：forecast/quality 就是在那一趟写的"
    sec = {"title": "第1段", "focus": "论证机制", "evidence": ["c1"]}
    assert crit in D.build_section_prompt(ev, ctx, sec, 1, 6), \
        "逐段成文那一趟看不到评审标准：density 要在写的时候就管，不是写完再扣分"
    assert crit in D.build_judge_prompt({"narrative": "正文" * 3000, "claims": [],
                                         "citations": [], "forecasts": []}, ctx), \
        "judge 那份与共享常量不是同一份：两处各写一遍迟早分叉（本仓为这个改过三轮）"


def test_forecast_ask_states_baseline_source_and_window_coherence():
    """#74 第三步：`forecast` 是五维里最低的一维（现网去重八场中位 0.475，§10.42）。
    先说清楚**这不是结构性 bug**：我测过两个看起来像 bug 的假设，都被数据否了（§10.46）
    —— 窗口矛盾只有 1/19 条命中；"0 条预测"是降级时 clip 清空的结果而不是原因。
    所以这一步走"教"：把 judge 那三句话（可核验、窗口合理）翻译成写的时候能照做的要求。

    判据只断"这三件信息在不在"，不断措辞：措辞换了不该让门禁变红。
    """
    p = D._structure_rules("c1, c2, c3", 3)
    assert u"基线" in p, "check_metric 没要求给可比的当前基线：没有基线的命中无从核验"
    assert (u"去哪里查" in p) or (u"来源" in p), "没要求点名核验出处（judge 那句『可核验』就落不了地）"
    assert u"先导信号" in p, "没教怎么处理'长期判断与短窗口'的矛盾：只会把一年塞进 14 天"
    assert (u"%d 天" % max(D.HORIZONS)) in p, \
        "没把最长窗口写进那句话：模型不知道'窗口内见分晓'到底是多少天"
    # 反向对照：不许把 FORECAST_MIN/MAX 与枚举窗口从文案里丢掉（这些是既有硬要求）
    assert u"%d-%d 条" % (D.FORECAST_MIN, D.FORECAST_MAX) in p, p[:400]


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
    # 文件名从常量里取，不写死：外证来源这个常量已经换过一次（source_quality.json 恒 404
    # → analysis_snapshot.json 的 quality 字段），写死的话换完来源这条判据就会悄悄只剩一条，
    # 剩下的那条照样绿 —— 这就是"恒真守卫比没有守卫更糟"。
    bases = [u.rstrip("/").split("/")[-1].split("?")[0]
             for u in (D.PREDICTIONS_URL, D.SOURCE_QUALITY_URL)]
    own = [u for u in seen if any(b in u for b in bases)]
    assert own, "两条自写产物的读路径一次都没走到，判据空跑"
    for b in bases:
        assert any(b in u for u in own), "%s 的读路径没被走到，这条腿没判到" % b
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
    assert "%E4%B8%AD" in " ".join(urls), \
        "已编码的链接被二次编码成 %%25E4... —— 上游 404 就是这么造出来的：%s" % urls
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
    # 预测现在多了一道"单格违约摘除"（repair_forecasts），但"不许静默抹掉内容"这条不变量
    # 必须照样成立：要么留着，要么带着原因进 forecasts_dropped。
    survived = [f.get("claim") for f in out["forecasts"]] + \
               [d.get("claim") for d in (out.get("forecasts_dropped") or [])]
    assert "三个月内出现跟随者" in survived, \
        "字符串预测被丢弃且没留账：%r" % (out["forecasts"], out.get("forecasts_dropped"))
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


# ── 解析容错：我们一边要求"至少 6 段"，一边期望它给出合法 JSON ──────────────

def test_parser_survives_the_shapes_models_actually_return():
    """现网第三跑 3 条里 2 条 `narrative=0 字`，不是模型没写，是它写了但我们读不出来。

    实测四种真实形态：裸换行、内嵌裸引号、截断、围栏+尾注 —— 只有最后一种过得去。
    而 §2 要求"至少 6 段"，长中文正文分段最常见的写法就是在 JSON 里塞裸 `\\n`：
    等于我们的契约自己把深度要求变成了解析失败。
    """
    body = "第一段论述。\n\n第二段论述，但该判断受限于样本口径。"
    raw_nl = '{"narrative": "%s", "citations": [{"id": "c1"}]}' % body
    got = D.parse_model_json(raw_nl)
    assert got and got.get("narrative"), "JSON 字符串里的裸换行把整条回复判成没写"
    assert "第二段" in got["narrative"], got

    quoted = '{"narrative": "他说\\"不行\\"，但口径受限。", "citations": []}'
    assert D.parse_model_json(quoted), "转义引号形态必须能读"

    fence = "```json\n{\"narrative\": \"正文\", \"citations\": []}\n```\n以上即你要的 JSON。"
    got2 = D.parse_model_json(fence)
    assert got2 and got2.get("narrative") == "正文", "围栏加尾注是模型的常见写法"

    # 截断不许伪装成"写得太短"：读出来必须是 None，让上层记 truncated
    assert D.parse_model_json('{"narrative": "' + "字" * 3000) is None, "半截 JSON 不该被当合格"


def test_narrative_quota_is_pushed_down_to_the_paragraph_and_matches_the_contract():
    """现网 run 35749459676 三条读数 1748 / 2307 / 1902 字：段数它照做，总量它不接，
    重写两轮停在同一水平。所以字数配额必须下沉到"每段"，而且下沉后的数字要和契约同源 ——
    否则改了常量忘改文案，prompt 承诺的长度与 `validate_event` 判的长度就分叉了。
    """
    p = D.build_prompt({"title": "t", "topic": "ai", "summary": "s", "links": []}, _ctx())
    assert D.PARA_MIN > 0
    assert ("每段 %d-%d 字" % (D.PARA_MIN, D.PERA_MAX)) in p, "段配额没进 prompt：%s" % p[:300]
    assert ("%d-%d 字" % (D.NARR_MIN, D.NARR_MAX)) in p, "总区间不是从常量渲染的"
    assert D.PARAS_MIN * D.PARA_MIN >= D.NARR_MIN, \
        "段配额乘不出来 %d 字，模型照做也过不了契约" % D.NARR_MIN


def test_prompt_aims_inside_the_range_instead_of_at_its_edges():
    """只报硬区间，模型就贴着边界交付 —— 这是现网六个读数判出来的，不是猜的。

    run 35749459676（15:45Z）三条：narrative 1,748 / 1,902 / 2,307 全低于 2,500 下限，
    quality.why 149 / 154 / 162 全超 120 上限。区间端点被复述了两次（首版 + 重写反馈），
    模型仍然把"不超过 120"理解成"约 150"、把"2500 起"理解成"约 2000"。
    所以 prompt 必须给出**严格落在区间内**的目标数字；光把边界念一遍不算约束。
    """
    p = D.build_prompt({"title": "t", "topic": "ai", "summary": "s", "links": []}, _ctx())
    asked = [int(x.replace(",", "")) for x in re.findall(r"按\s*([\d,]+)(?:-\d+)?\s*字写", p)]
    narr_targets = [n for n in asked if D.NARR_MIN < n < D.NARR_MAX]
    assert narr_targets, "narrative 只复述了边界，没有区间内目标（模型会贴下限写）：%s / %s" % (
        asked, p[p.find("narrative"):p.find("narrative") + 200])
    i = p.find("quality：")
    assert i >= 0, "prompt 里没有 quality 那条要求"
    why_seg = p[i:i + 300]
    why_pairs = re.findall(r"(\d+)\s*-\s*(\d+)\s*字写", why_seg)
    assert why_pairs, "why 没给区间内目标：%s" % why_seg
    nums = [int(x) for pair in why_pairs for x in pair]
    assert D.WHY_MIN <= min(nums) and max(nums) <= D.WHY_MAX, \
        "why 的目标 %s 越出了硬区间 [%d,%d]，照做也不合格" % (
            nums, D.WHY_MIN, D.WHY_MAX)
    assert max(nums) < D.WHY_MAX, \
        "why 的目标贴着上限（实测模型写到 149–162 字）：%s" % nums


def test_horizon_days_states_the_enum_and_the_consequence():
    """`horizon_days 只能是 3、7 或 14` 这一句在现网没拦住 90。

    判据钉的是不变量而不是我的措辞：三个合法值都要出现，且必须写清越界的后果；
    只说"只能是"而不说后果，模型把它当建议。
    """
    p = D.build_prompt({"title": "t", "topic": "ai", "summary": "s", "links": []}, _ctx())
    i = p.find("horizon_days")
    assert i >= 0, "prompt 里没有 horizon_days"
    seg = p[i:i + 200]
    for v in ("3", "7", "14"):
        assert v in seg, "合法取值缺 %s：%s" % (v, seg)
    assert ("不合格" in seg or "判" in seg), "没写越界的后果，模型会当建议：%s" % seg
    # 光列合法值没拦住现网的 90：这一句的机制就是"把写错的样子点名回去"。
    assert any(x in seg for x in ("30", "90", "一年内")), \
        "没给反例，模型仍会把 horizon 写成 90（现网实测）：%s" % seg


def test_parser_recovers_embedded_straight_quotes():
    """现网 run 35756700221：三条回复各 5,095–6,031 字、JSON 结构完整，
    全部死在正文里的裸引号上 —— 深度不是没写出来，是我们读不出来。

    模型给中文术语加引号是默认写法，而 `"` 在 JSON 字符串里非法。
    只救"引号后面不是结构符"这一种；截断的仍然算失败，不许伪装成"模型写得太短"。
    """
    body = ('```json\n{"narrative": "第一段。所谓"AI 原生"就是这个意思。'
            '\n\n第二段：结论。", "citations": [{"id": "c1", "url": "https://a"}]}\n```')
    got = D.parse_model_json(body)
    assert got and "AI 原生" in got["narrative"], got
    assert got["citations"] == [{"id": "c1", "url": "https://a"}], got
    assert D.parse_model_json('{"a": "x", "b": 1}') == {"a": "x", "b": 1}, \
        "真结束的引号被误判成正文，普通 JSON 也会跟着坏"
    assert D.parse_model_json('{"narrative": "' + "字" * 3000) is None, "截断不该被蒙混"
