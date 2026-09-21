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
    # ── 线上实测的三种 link 形状（2026-09-21，JS 出口 3 个源 100% 畸形、Python 出口 9,067 条零畸形）
    # 这三条不是"顺手加固"：链接决定卡片点哪儿、决定抽屉合并能不能认出"同一篇"，
    # 两侧不一致就是同一篇文章两个身份。
    ("cdata_link", u'<item><link><![CDATA[https://toi.example/b/a?photostory=7507755]]></link>'
                   u'<title>t</title></item>', None),
    ("amp_entities", u'<item><link>https://bbc.example/n/cw4gm7l742dmo&amp;at_campaign=rss'
                     u'&amp;at_medium=rss</link><title>t</title></item>', None),
    # 实体解码只许走一趟：`&amp;amp;` 的正确结果是 `&amp;`，先把 &amp; 解掉就会得到 `&`。
    # 两侧实测一致（Python 与 JS 都吐 `...u=1&amp;keep=1`），所以这条能当判据；
    # 它专门用来挡"把 &amp; 放到最前面解"那种等价改写。
    ("double_encoded_amp", u'<item><link>https://x.example/a?u=1&amp;amp;keep=1</link>'
                           u'<title>t</title></item>', None),
    ("hash_fragment_kept", u'<item><link>https://spiegel.example/x/y.html#ref=rss</link>'
                           u'<title>t</title></item>', None),
    ("padded_link", u'<item><link>  https://ok.example/a  </link><title>t</title></item>', None),
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
    """两条解析路径**各自**必须走 helper —— 用整句源码锁，不用"附近出现过"。

    这条判据改过两次，前两版都是假的：
      v1 `text.count("linkOrPermaId(") >= 2` —— helper 定义自身占一次，
         变异体把 Atom 路径改回 extractTag 照样绿；
      v2 "从循环起点往后截 1200 字符，段内含 linkOrPermaId" —— 窗口会溢出到另一条
         路径的代码，同一个变异体**仍然绿**（我实测过两次才承认它无效）。
    现在锁具体语句：每条路径那一行必须原样存在，被改坏就立刻找不到；
    日期兜底则要求两条路径各出现一次（count==2，多了少了都说明接线动过）。
    """
    text = open(API_RSS, encoding="utf-8").read()
    assert "linkOrPermaId(item, 'link', 'guid')" in text, \
        "RSS2 路径没走 guid 回退：guid 即链接的源（如安全客）在运行时侧仍是空链接"
    assert "linkOrPermaId(entry, 'link', 'id')" in text, \
        "Atom 路径没走 guid/id 回退：只修一条等于没修（台账 §20 的原始事故形态）"
    assert text.count("const _dt = datedOrCapture(pubDate);") == 2, \
        "收录时刻兜底必须两条路径各一次，实际 %d 次" % text.count("const _dt = datedOrCapture(pubDate);")
    assert "pub_date: pubDate || ''" not in text, "还有路径把缺日期直接出厂成空串"
