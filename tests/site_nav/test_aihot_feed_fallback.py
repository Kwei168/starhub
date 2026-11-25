# -*- coding: utf-8 -*-
"""AI 动态流取数判据：浏览器直连域名 + 主源空不许短路第二源。

2026-11-26 事故：上游把 aihot.virxact.com 迁到 aihot.news，旧域名只留一个**不带 CORS 头**
的 301。服务端请求跟跳转无感，浏览器跨域 fetch 在跳转那一跳就被拦死（线上控制台实锤
"No 'Access-Control-Allow-Origin' header"）。首页面板因此全空、RSS 页面板只剩 AGI Hunt
一半（825 个链接里 0 条 AIHOT）。日报页走构建期服务端请求，不受影响。

两条不变量：
  ① 浏览器直连的 AIHOT 端点必须是新域名（首页 template.html + RSS 页生成端内嵌 JS）。
     构建期脚本（build_ai_daily.py / build_daily_insight.py）走服务端、跟 301 正常，不在本判据面内。
  ② loadAihot 里主源空/挂时不许提前 return 短路 /api/news 兜底。旧写法的空数据分支
     `if(!items.length){ ...; return; }` 让"任一源失败静默降级"的设计实际失效。
每条都带反向变异：判据必须能抓住事故当时的代码形状，否则绿话只是判据失明。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "template.html")

OLD_HOST = "aihot.virxact.com"
NEW_HOST = "aihot.news"


def _read(path):
    return io.open(path, encoding="utf-8").read()


def _generated_rss_html():
    """现生成的 RSS 页（同 test_dead_api_routes 口径：空数据只取静态代码部分）。

    不读库里的 rss-aggregator.html 副本：CI 提交清单不含这些 HTML，库副本是冻结的旧运行时。
    """
    sys.path.insert(0, os.path.join(ROOT, "tests", "rss_composite"))
    sys.path.insert(0, ROOT)
    from _loader import load_build
    return load_build().build_html([], "2026-11-26 07:01", 0, 0, analysis_data=None,
                                   diverse_window_minutes=120, diverse_enabled=True)


def _browser_aihot_urls(text):
    """源里浏览器直连的 AIHOT items 端点（const/var AIHOT_API = '…'）。"""
    return re.findall(r"(?:const|var)\s+AIHOT_API\s*=\s*'([^']+)'", text)


def _old_domain_offenders(text):
    return [u for u in _browser_aihot_urls(text) if OLD_HOST in u]


def test_browser_aihot_endpoint_is_new_domain():
    """① 首页与 RSS 页（现生成）的浏览器直连端点都必须是新域名，且认得到端点（非空集）。"""
    sources = [("template.html", _read(TEMPLATE)),
               ("rss-aggregator.html（现生成）", _generated_rss_html())]
    for name, text in sources:
        urls = _browser_aihot_urls(text)
        assert urls, "%s 里找不到 AIHOT_API 端点声明——判据输入为空等于恒绿" % name
        assert not _old_domain_offenders(text), (
            "%s 的浏览器直连端点还在旧域名（301 不带 CORS 头，浏览器 fetch 必挂）：%s"
            % (name, _old_domain_offenders(text)))
        assert all(NEW_HOST in u for u in urls), (
            "%s 的 AIHOT_API 不是新域名：%s" % (name, urls))
    # 反向：事故当时的旧域名形状必须被判红
    mutant = "const AIHOT_API = 'https://%s/api/v1/items?mode=all&window=24h&limit=40';" % OLD_HOST
    assert _old_domain_offenders(mutant), "变异体（旧域名）没被抓住，判据失明"


def _loadaihot_body(text):
    m = re.search(r"async function loadAihot\(\)\{.*?\n\}", text, re.S)
    assert m, "template.html 里找不到 loadAihot 函数体"
    return m.group(0)


def _shortcircuit_before_news(body):
    """try{ 到 fetchNewsItems( 之间出现 return 语句 ⇒ 主源空/挂会短路第二源。

    先剥注释再找 return：本判据第一版就被自己注释里的"旧写法提前 return"字样骗红过
    （同 _needs_rsync 被注释骗的那次账）。`(?<!:)` 保住 URL 里的 `://` 不被当注释剥掉。
    """
    stripped = re.sub(r"(?<!:)//[^\n]*", "", body)
    try_idx = stripped.index("try{")
    news_idx = stripped.index("fetchNewsItems(")
    return re.search(r"\breturn\b", stripped[try_idx:news_idx]) is not None


def test_empty_main_source_does_not_shortcircuit_news():
    """② loadAihot 主源空/挂时仍须走到 /api/news 兜底（try 与 news 调用之间不许 return）。"""
    body = _loadaihot_body(_read(TEMPLATE))
    assert not _shortcircuit_before_news(body), (
        "loadAihot 在 fetchNewsItems 之前有 return：主源空/挂时第二源被短路，面板全空")
    # 反向：事故当时的空数据提前 return 形状必须被判红
    mutant = body.replace(
        "    let items = (aiRes && aiRes.items) ? aiRes.items.slice() : [];",
        "    let items = (aiRes && aiRes.items) ? aiRes.items.slice() : [];\n"
        "    if(!items.length){ aihotLoaded = true; return; }")
    assert mutant != body, "变异体没插进去，锚点已漂移"
    assert _shortcircuit_before_news(mutant), "变异体（空数据提前 return）没被抓住，判据失明"


def test_friendly_empty_state_survives():
    """修短路不许顺手删掉两源皆空时的友好空态文案。"""
    body = _loadaihot_body(_read(TEMPLATE))
    assert "近 24 小时暂无新动态" in body, "两源皆空的友好空态文案丢了"