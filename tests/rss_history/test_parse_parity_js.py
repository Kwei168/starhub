# tests/rss_history/test_parse_parity_js.py
# -*- coding: utf-8 -*-
"""`api/rss.js` 的解析 helper 必须与 Python 侧 `_parse_rss_item` 判得一模一样。

为什么单独一条判据（而不是"看起来一样"）：72h 契约与"日期不许伪装"这两件事各有两个执行点 ——
构建期写产物、运行时 `api/rss.js` 自己抓上游。2026-09-21 同一天里，
"guid 即链接"和"无日期条目降级收录时刻"两处修复都只落在 Python 侧，
JS 侧靠人记得同步是不可靠的（台账 §20 记的就是这次差点漏掉）。

做法：从 api/rss.js 里切出 helper 源码，用 node 跑同一组 fixture，
再与生产代码 mod._parse_rss_item 的判决逐条比对。
不用 require('api/rss.js')：那是 Vercel 入口模块，加载即带网络与 env 依赖。
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _loader import load_build  # noqa: E402

mod = load_build()
API_RSS = os.path.join(ROOT, "api", "rss.js")

FIXTURES = [
    # (名字, RSS2 item 片段, 期望：link 是否取到 guid)
    ("guid_only", u'<item><guid>https://www.anquanke.com/post/id/316124</guid>'
                  u'<title>t</title><pubDate>2026-09-19 10:57:40</pubDate></item>', True),
    ("numeric_guid", u'<item><guid>12345</guid><title>t</title></item>', False),
    ("permalink_false", u'<item><guid isPermaLink="false">https://x.example/a</guid>'
                        u'<title>t</title></item>', False),
    ("plain_link", u'<item><link>https://ok.example/a</link><guid>https://other.example/b</guid>'
                   u'<title>t</title></item>', None),
    ("no_date", u'<item><link>https://ok.example/a</link><title>t</title></item>', None),
]


def _node():
    for c in ("node", "node.exe"):
        try:
            r = subprocess.run([c, "-v"], capture_output=True)
        except Exception:
            continue
        if r.returncode == 0:
            return c
    return None


def _js_helper_src():
    text = open(API_RSS, encoding="utf-8").read()
    a = text.find("function extractTag(")
    b = text.find("function stripHtml(")
    assert a > 0 and b > a, "api/rss.js 里找不到 extractTag..stripHtml 区间，helper 结构变了"
    return text[a:b]


@pytest.mark.parametrize("name,frag,expect_guid", [tuple(f) for f in FIXTURES])
def test_js_matches_python_link_verdict(name, frag, expect_guid):
    node = _node()
    if not node:
        pytest.skip("本机没有 node（CI 的 ubuntu runner 一定有）")
    script = (
        "const s=%r;\n" % _js_helper_src() +
        "eval(s);\n"
        "const f=%s;\n" % json.dumps([f[1] for f in FIXTURES], ensure_ascii=False) +
        "const r=f.map(x=>linkOrPermaId(x,'link','guid'));\n"
        "process.stdout.write(JSON.stringify(r));\n")
    out = subprocess.run([node, "-e", script], capture_output=True)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[:300]
    js_links = json.loads(out.stdout.decode("utf-8"))
    i = [f[0] for f in FIXTURES].index(name)
    js = js_links[i]

    py_out = []
    mod._parse_rss_item(ET.fromstring(frag), "S", "s_1", "security", py_out)
    py = (py_out[0]["link"] if py_out else "")
    assert js == py, "%s：JS 判成 %r，Python 判成 %r —— 两侧口径又分叉了" % (name, js, py)
    if expect_guid is True:
        assert py.startswith("https://"), "%s 应当从 guid 取到链接" % name
    if expect_guid is False:
        assert py == "", "%s 不该把非永久链接的 guid 当链接用" % name


def test_js_undated_item_is_marked_not_blank():
    """JS 侧缺日期时必须给收录时刻并打标；空串会让卡片没有时间，不打标就是伪装发布时间。"""
    node = _node()
    if not node:
        pytest.skip("本机没有 node")
    script = ("const s=%r;\n" % _js_helper_src() + "eval(s);\n"
              "const a=datedOrCapture(''),b=datedOrCapture('2026-09-19 10:57:40');\n"
              "process.stdout.write(JSON.stringify([a.pub_date,a.date_fallback,b.pub_date,b.date_fallback]));\n")
    out = subprocess.run([node, "-e", script], capture_output=True)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[:300]
    pd_a, fb_a, pd_b, fb_b = json.loads(out.stdout.decode("utf-8"))
    assert pd_a and fb_a is True, "无日期条目没拿到降级值或没打标：%r" % (pd_a, fb_a)
    assert pd_b == "2026-09-19 10:57:40" and not fb_b, "有日期条目被改写了：%r" % (pd_b, fb_b)


def test_both_rss_paths_use_the_helpers():
    """两条解析路径**各自**必须走 helper，不是"全文出现次数够"。

    为什么写成这样：上一版用 `text.count("linkOrPermaId(") >= 2` —— 变异体只把 Atom 那处
    改回 extractTag 也照样绿（定义自身就占一次计数），这条判据等于没写。
    现在按循环体定位：RSS 的 for 与 Atom 的 for 各自内部必须出现对应调用。
    """
    text = open(API_RSS, encoding="utf-8").read()
    for marker, what in (("for (const item of rssItems", "RSS2 路径"),
                         ("for (const entry of atomEntries", "Atom 路径")):
        i = text.find(marker)
        assert i > 0, "找不到 %s 的循环起点，api/rss.js 结构变了" % what
        seg = text[i:i + 1200]
        assert "linkOrPermaId(" in seg, "%s 没走 guid/id 回退，guid 即链接的源在这条路上仍是空链接" % what
        assert "datedOrCapture(" in seg, "%s 没走收录时刻兜底，缺日期条目仍出厂空时间" % what
    assert "pub_date: pubDate || ''" not in text, "还有路径把缺日期直接出厂成空串"
