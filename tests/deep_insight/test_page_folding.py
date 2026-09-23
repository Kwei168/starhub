# -*- coding: utf-8 -*-
"""独立页呈现：正文折叠，不平铺全打开。

来历：方案一之后单条可以到 10,000 字，12 条最坏 12 万字。体积不是问题
（本站 rss-aggregator.html 现网就 3.46 MB），**滚动长度**才是问题。
折叠必须是"默认收起"而不是"内容不渲染"：所以用原生 details/summary，
不引 JS、不异步取数 —— 否则折叠就成了第二种丢内容。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402

# 站点上真在服务的页面（Pages 根目录）。导航只能指向这里，否则就是死链红线。
SERVED = {"index.html", "ai-daily.html", "rss-aggregator.html", "daily-insight-history.html"}


def _long_para(n=9):
    """造一条真"长"的正文：必须越过 FOLD_MIN_CHARS，不然测到的是夹具尺寸而不是折叠。"""
    one = ("投入与产出之间存在可核对的落差，把口径对齐之后仍然能看到结构性差异，"
           "同类玩家在两个季度内相继跟进，但该判断仍受样本量与统计口径限制。")
    one = one + "补充材料与推演过程。" * 9          # 每段 ~180 字
    return "\n\n".join(one + "第%d段。" % i for i in range(n))


def _payload(narr=None):
    return {
        "date": "2026-09-23", "generated_at": "2026-09-23T04:31:00+08:00",
        "engine": D.SCHEMA_VERSION,
        "budget": {"llm_calls": 58, "elapsed_s": 648, "key_count": 4},
        "anchor_diff": [], "predictions_reconciled": {"due": 0, "hit": 0, "miss": 0},
        "events": [{
            "id": "evt1", "topic": "ai", "title": "腾讯混元下调定价",
            "narrative": narr or _long_para(),
            "claims": [{"text": "论断", "kind": "causal", "evidence": ["c1"]}],
            "causal_chains": [{"trigger": "降价", "mechanism": "成本线", "outcome": "跟进",
                               "confidence": 0.6, "evidence": ["c1"]}],
            "forecasts": [{"claim": "三个月内出现跟随者", "horizon_days": 7,
                           "check_metric": "同类发布数>=3", "status": "pending"}],
            "quality": {"verdict": "一手", "score": 82, "why": "有原始参数", "basis": ["sig:c1"]},
            "citations": [{"id": "c1", "url": "https://a.test/x", "source": "A",
                           "title": "原文甲", "chars_used": 5706}],
            "rubric": {"mean": 0.83},
        }],
    }


def _span(html):
    """返回 (details 起, details 止)；没有折叠就返回 (-1, -1)。"""
    m = re.search(r"<details\b.*?>", html, re.S)
    if not m:
        return -1, -1
    end = html.find("</details>", m.end())
    return m.start(), end


def test_long_narrative_ships_folded():
    """正文必须落在折叠块里，且摘要要把体量告诉读者（不展开也知道这条多长）。"""
    html = D.render_page(_payload())
    a, b = _span(html)
    assert a >= 0, "长正文仍平铺全打开，12 条 12 万字没有折叠"
    assert b > a, "details 没有闭合"
    summary = html[a:b]
    assert "<summary" in summary, "折叠块没有摘要"
    assert re.search(r"\d[\d,]*\s*字", summary), "摘要没告诉读者这条多少字：%s" % summary[:200]
    first_para = html.find("投入与产出之间存在可核对的落差")
    assert a < first_para < b, "正文不在折叠块内，折叠的是别的东西"


def test_folding_keeps_every_paragraph_in_the_document():
    """折叠 = 收起，不是不渲染：不引 JS、不异步取数，正文必须还在 HTML 里。"""
    narr = _long_para(9)
    html = D.render_page(_payload(narr))
    for p in [x for x in narr.split("\n\n") if x.strip()]:
        assert p[:18] in html, "折叠把段落弄丢了：%s" % p[:18]
    assert "<script" not in html.lower(), "折叠不该引 JS（原生 details 就够）"
    assert "onclick" not in html.lower(), "折叠不该引 JS（原生 details 就够）"


def test_claims_forecasts_and_evidence_stay_outside_the_fold():
    """可核对的部分不能藏起来：预测卡、因果链、证据链接要展开前就看得见，
    否则"每条都给判据"退化成人人要点一下才有。"""
    html = D.render_page(_payload())
    a, b = _span(html)
    assert a >= 0
    for probe in ("预测", "因果", "证据"):
        i = html.find(probe)
        assert i >= 0 and not (a < i < b), "%s 区被折进正文里了" % probe


def test_no_heading_sits_over_an_empty_section():
    """真浏览器里抓到的：快讯条目下面挂着"因果""证据"两个空标题。

    标题在、内容空 —— 就是"名字里带内容却什么都不保证"的页面版，
    也是用户红线里的空壳。有内容时标题必须在，没内容时整块不出现。
    """
    p = _payload()
    e = dict(p["events"][0])
    e.update({"causal_chains": [], "citations": [], "forecasts": [],
              "degraded_reason": "重写 2 次仍不合格",
              "narrative": "证据不足，按快讯处理。"})
    p["events"] = [e]
    html = D.render_page(p)
    assert "<h3>因果</h3><ul></ul>" not in html, "空因果区留着标题装样子"
    assert "<h3>证据</h3><ul></ul>" not in html, "空证据区留着标题装样子"
    full = D.render_page(_payload())
    assert "<h3>因果</h3>" in full and "<h3>证据</h3>" in full, \
        "有内容时标题也不见了 —— 那是把板块悄悄删了"
    """导航/回链红线：站内 href 只能指向确实在服务的页面。

    `deep-insight.html` 现网实测 404 —— 在它真被 publish 出来之前，
    任何页面挂它都会立刻长出一条死链，这条判据就是拦这个的。
    """
    for html in (D.render_page(_payload()),):
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            assert href.strip(), "空 href 就是死链"
            assert href in SERVED, "站内链接指向未上线页面 %s（SERVED 里没有）" % href
