# -*- coding: utf-8 -*-
"""/api/rss 与 /api/article 的正文出口必须真的过 `lib/body_rules` 这道闸。

为什么读源码 + 本地跑切出来的函数，而不是发 HTTP：CI 上没有可用的 Vercel 凭证，
`/api/article` 的真实响应要等线上场；而"忘了接"这件事在源码层就能钉死
（同形状先例：`tests/site_nav/test_orphan_requests.py`、
`tests/rss_history/test_parse_parity_js.py` 都是读源文本 + 用 node 跑切片）。
线上读数由 §验收清单 用浏览器通道补，两层都要有。

**硬约束：本判据不许 require npm 依赖。** CI 没跑 `npm ci`、runner 上没有 `node_modules`，
而 `api/article.js` 顶部就是 `require('jsdom')` ⇒ 任何 import 它的测试在 CI 上必崩
（红了还查不到原因）。所以：
  · `/api/article` 的返回契约走**源码级断言**（形状照 test_orphan_requests.py）；
  · 行为判定走 `lib/body_rules.js` 的 node 用例（tests/rss_js/test_body_rules.js）；
  · `api/rss.js` 的**产物**走 node 切片实跑 —— 切出来的 `extractTag..fetchOne` 区段
    只依赖 fs/path + `lib/*.js`，零 npm 依赖，因此能在 CI 上跑。
"接线不是断链"的直接证据在下面 `test_realtime_parse_feed_*` 两条：它们拿的是**真产物**。
"""
import io
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 变异体注入点：与本仓 STARHUB_BODY_RULES / RSS_BUILD_SRC / STARHUB_UPDATE_YML 同一约定。
API_RSS = os.environ.get("STARHUB_API_RSS") or os.path.join(ROOT, "api", "rss.js")
API_ARTICLE = os.environ.get("STARHUB_API_ARTICLE") or os.path.join(ROOT, "api", "article.js")
LIB_BODY = os.environ.get("STARHUB_BODY_RULES") or os.path.join(ROOT, "lib", "body_rules.js")
LIB_COVER = os.path.join(ROOT, "lib", "rss_cover.js")


def _read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def _code(text):
    """只留代码行。注释里提一句被禁字面量不该把判据打红
    （口径照 tests/site_nav/test_body_rules_parity.py:678 `test_js_lib_has_zero_requires...`）。
    真把 `.slice(0, 50000)` 写回代码行仍然红 —— 见报告里的变异①。
    """
    keep, block = [], False
    for ln in text.split("\n"):
        t = ln.strip()
        if block:
            if t.endswith("*/") or "*/" in t:
                block = False
            continue
        if t.startswith("/*"):
            if "*/" not in t:
                block = True
            continue
        if t.startswith("//") or t.startswith("*"):
            continue
        keep.append(ln)
    return "\n".join(keep)


def _node():
    n = shutil.which("node")
    if not n:
        pytest.skip("本机没有 node（CI 的 ubuntu runner 一定有）")
    return n


# ---------------------------------------------------------------- Task 4：接线在不在
def test_both_runtimes_share_the_one_body_rules_module():
    for p in (API_RSS, API_ARTICLE):
        assert re.search(r"""require\(['"]\.\./lib/body_rules\.js['"]\)""", _read(p)), \
            "%s 没接 lib/body_rules.js ⇒ 正文规范只剩构建期一份" % os.path.basename(p)


def test_no_bare_slice_of_50000_left_in_rss_exit():
    """`.slice(0, 50000)` 是裸切片，会截出半个标签 —— 必须换成 capBody。"""
    assert "slice(0, 50000)" not in _code(_read(API_RSS)), "api/rss.js 还在裸截断"


def test_article_output_is_normalized_and_capped(tmp_path):
    """派工 F1：规范化与截断必须**落到出口**，判据量的不能是"函数名出现过"。

    原判据只有两条 grep ⇒ 在 %TEMP% 副本里把出口改成"算了但丢弃结果"
    （`_normalized = BODY.normalizeBodyHtml(result.content, url)` 之后
    `content = BODY.capBody(result.content)`）它照样 26 passed，`:113` 数出现次数也绿。
    根因是结构性的：`api/article.js` 在 `tools/mut_reader.py` 里属 ONCE（只读）、不在
    COPIES ⇒ 电池压根没法给它登记靶。这里两半一起补：判据改走**实跑切片**（问
    `out.content` 的去向），`api/article.js` 进 COPIES 并登记 F01/F02/F03 三条靶。
    原有那两条 grep 一个字没删（只加不减），新增的两段行为才是有牙的那半。
    """
    src = _read(API_ARTICLE)
    assert re.search(r"normalizeBodyHtml\(", src), "article.js 没做正文规范化"
    assert re.search(r"capBody\(", src), "article.js 没做安全截断"

    # ── 去向一（规范化）：算过不等于出厂。相对地址必须在产物里已经绝对化。──
    c = _article_exit_product(tmp_path, _NORM_BODY)["content"]
    assert 'src="https://blog.example.com/imgs/a.png"' in c, (
        "规范化算了但没落到出口（产物仍是未绝对化的懒加载形状）⇒ 阅读器里就是丢图：%s" % c)
    assert "/tag/go" not in c, "规范化那半被摘掉时，脱链也不在出口上：%s" % c

    # ── 去向二（截断）：capBody 必须是**出口值的最后一道**，不是中途的一次计算。──
    pad = 49990
    long_body = u"<p>" + u"y" * pad + u"</p><img src=\"https://e.test/x.png\">"
    assert 50000 < len(long_body) < 50100, "fixture 本身要刚好跨过上限，实际 %d" % len(long_body)
    t = _article_exit_product(tmp_path, long_body)["content"]
    assert len(t) <= 50000, "没截断：%d 字符出厂" % len(t)
    assert not re.search(r"<[^>]*$", t), "尾巴挂着半个标签（还是裸切片）：%r" % t[-40:]
    assert not re.search(r"&[#A-Za-z0-9]*$", t), "尾巴挂着残缺实体：%r" % t[-40:]
    assert t.endswith("</p>"), "截断点没收敛到干净边界：%r" % t[-24:]
    assert len(t) > 49000, "截得太狠（正文被整段丢了）：%d" % len(t)


# ── /api/article 现抓通道"出口整形"的**实跑**底座（审查 ⑤ + 派工 F1）────────────
# 为什么必须实跑：`api/article.js` 顶部就是 `require('jsdom')`，CI 上没有 node_modules ⇒
# 整份文件 require 不进来（一 import 就 MODULE_NOT_FOUND，红了还查不到原因，本文件 §硬约束
# 就是这么写的）。但成功返回前那一段（`const content = …` 到 `cacheSet(url, out);` 之前）
# 只认三个名字：BODY（真 lib，零 npm 依赖）、result、url ⇒ 注入这三个就能把**出厂那几行
# 原样跑一遍**。量的是 `out.content` 的**去向**而不是"源码里出现过 BODY.xxx"：
# 规范化算了但没落到出口 ⇒ 产物里仍是相对地址/未脱导航 href，当场红（F1 的根因形状）。
# 锚点找不到 ⇒ assert 红并说清是出口形状变了，绝不静默 skip（静默 skip 就是第二条假绿）。
_ARTICLE_URL = u"https://blog.example.com/post/one/"
_EXIT_START = re.compile(r"^[ \t]*const content = ", re.M)
_EXIT_END = re.compile(r"^[ \t]*cacheSet\(url, out\);", re.M)

# 现抓通道的样本正文：Readability 出来的形状就是"站内相对链接 + 懒加载属性 + 外部正文链接"。
_NAV_BODY = (u'<p>我们用 <a href="/tag/kubernetes">Kubernetes</a> 部署，'
             u'<a href="https://blog.example.com/category/engineering">分类</a> 页与'
             u'<a href="#sec-2">见下节</a>，'
             u'参考 <a href="https://openai.com/blog/x">原始公告</a></p>'
             u'<img data-src="/imgs/a.png" alt="a">')

# F1 的样本：只留"规范化在产物上看得见"的那一格（懒加载提升 + 绝对化）。
# 现抓通道没有 sanitize（Readability 的产物形状与 feed 不同），所以 data-src 会留着，
# 判据盯的是**提升出来的绝对 src** —— "算了但丢弃"那一版产物里它压根不存在。
_NORM_BODY = (u'<p>正文</p><img data-src="/imgs/a.png" alt="a">'
              u'<a href="/tag/go">Go</a>')


def _article_exit_src():
    """切出 article.js 里"出口整形 → 成功载荷"那几行的**原文**。"""
    text = _read(API_ARTICLE)
    a = _EXIT_START.search(text)
    assert a, ("api/article.js 里找不到出口段起点（行首 `const content = `）⇒ "
               "出口整形的形状变了，本判据失去着力点")
    b = _EXIT_END.search(text, a.end())
    assert b, ("api/article.js 里找不到出口段终点（行首 `cacheSet(url, out);`）⇒ "
               "成功返回前多/少了步骤，本判据失去着力点")
    seg = text[a.start():b.start()]
    assert "const out = {" in seg, "切到的区间里没有成功载荷构造行 ⇒ 切错了地方"
    return seg


def _article_exit_product(tmp_path, content, url=_ARTICLE_URL):
    """拿**真** lib 跑**真**出口那几行，返回出厂的成功载荷（dict）。"""
    runner = tmp_path / "article_exit_product.js"
    runner.write_text(
        "const BODY = require(%s);\n"
        "const url = %s;\n"
        "const result = {title: 'T', content: %s, source: 'readability', degraded: 'short'};\n"
        "%s\n"
        "process.stdout.write(JSON.stringify(out));\n"
        % (json.dumps(LIB_BODY.replace("\\", "/")), json.dumps(url), json.dumps(content),
           _article_exit_src()),
        encoding="utf-8", newline="\n")
    r = subprocess.run([_node(), str(runner)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    assert r.returncode == 0, "article.js 出口切片实跑崩了：\n%s\n%s" % (
        (r.stdout or "")[-400:], (r.stderr or "")[-1200:])
    return json.loads(r.stdout)


def test_article_live_channel_delinks_insite_nav_links(tmp_path):
    """审查 ⑤：现抓通道与快照通道必须**同一把脱链刀**，产物里不许留站内导航 href。

    判据是**行为**：把 Readability 形状的正文喂给真出口切片，断言产出的 HTML 里
    站内导航（`/tag/`、`/category/`）已脱成纯文字，而三类"不许动"的一条没被吃掉 ——
    外部正文链接、页内锚点、正文词。走快照 fc 的条目在构建期已过这把刀，
    这里补齐的是**多数文章**走的那条现抓通道。
    """
    out = _article_exit_product(tmp_path, _NAV_BODY)
    c = out["content"]
    assert out.get("ok") is True and out.get("source") == "readability", out
    assert out.get("degraded") == "short", "degraded 那一格被出口整形改掉了（契约外）：%s" % out
    for word in (u"Kubernetes", u"分类", u"见下节", u"原始公告"):
        assert word in c, "脱链把链接文字一起吃掉了：%r" % c
    assert "/tag/kubernetes" not in c, \
        "现抓通道没接 delinkNavLinks ⇒ 正文里仍是站内导航链接：%r" % c
    assert "/category/engineering" not in c, \
        "同站绝对形状的导航链接也没脱（normalize 之后才看得见的那一半）：%r" % c
    assert 'href="https://openai.com/blog/x"' in c, "外部正文链接被脱了：%r" % c
    assert 'href="#sec-2"' in c, "页内锚点被脱了（构建期同名反例）：%r" % c


def test_rss_exit_keeps_the_buildtime_order_normalize_sanitize_deepclean_cap():
    """顺序必须与构建期 `_normalize → _sanitize → _deep_clean → _cap` 一致。

    不是洁癖：`sanitizeHtml` 的 `ALLOWED_ATTRS["img"] = ['src','alt']` 会把 `data-src`
    整条剥掉。normalize 挪到 sanitize 之后就永远看不见懒加载属性 ⇒ 图片在出口前就没了
    （用户报的"正文丢图"就是这个形状）。所以既钉字面嵌套顺序，也钉真产物（下面那条）。
    """
    src = _read(API_RSS)
    m = re.search(r"BODY\.capBody\(\s*deepCleanHtml\(\s*sanitizeHtml\(\s*BODY\.normalizeBodyHtml\(", src)
    assert m, "api/rss.js 的 fullContent 出口顺序不是 normalize→sanitize→deepClean→cap"
    # base 用的是条目自己的 link（局部变量），不是被 `|| '#'` 兜过的那份
    assert re.search(r"normalizeBodyHtml\(\s*fullContent\s*,\s*link\s*\)", src), \
        "base 不该取 result.link（它已被写成 link || '#'，'#' 不是 base）"


def test_article_snapshot_channel_is_capped_but_not_normalized_again():
    """快照通道的 `fc` 在构建期已过规范 ⇒ 运行时只补 cap，重复 normalize 会二次改写。

    `normalizeBodyHtml` 幂等的前提是"输入已规范"，但二次绝对化会把已经绝对化的值再喂给
    urlJoin 一次（`https://a/x` 这种在 base 同域时结果相同，但 `data:`/`#` 之外仍有形态会动），
    而最坏的是排查时分不清是哪一层改写的。所以这里数次数，不数"有没有"。
    """
    src = _read(API_ARTICLE)
    assert re.search(r"BODY\.capBody\(\s*entry\.content\s*\)", src), \
        "快照通道没走 capBody（构建期的 fc 也要在运行时出口裁一次）"
    n = len(re.findall(r"BODY\.normalizeBodyHtml\(", src))
    assert n == 1, "normalizeBodyHtml 在 article.js 里出现 %d 次，应当只有实时抽取那一次" % n


# ---------------------------------------------------------------- Task 4：真产物（接线不是断链的直接证据）
def _rss_pipeline_src():
    """切 api/rss.js 里 extractTag..fetchOne 之间的纯函数（含 parseFeed），与既有判据同一手法。"""
    text = _read(API_RSS)
    a = text.find("function extractTag(")
    b = text.find("async function fetchOne(")
    assert 0 < a < b, "api/rss.js 里找不到 extractTag..fetchOne 区段，helper 结构变了"
    seg = text[a:b]
    assert "function parseFeed(" in seg and "function sanitizeHtml(" in seg, "区段缺 parseFeed 或 sanitizeHtml"
    return seg


def _parse_feed_product(tmp_path, xml):
    """用 node 跑**真** parseFeed，返回 items（不发任何外网请求，输入是本地字符串）。"""
    runner = tmp_path / "parse_feed_product.js"
    runner.write_text(
        # COVER/BODY 必须先注进同一作用域：parseFeed 会调它们，而切片切不到文件顶部的 require
        # （漏了就是 ReferenceError 式假红，与 test_parse_parity_js.py:60 那条教训同形）。
        "const COVER = require(%s);\n"
        "const BODY = require(%s);\n"
        "const src = %s;\n"
        "eval(src);\n"
        "const items = parseFeed(%s, 'probe', 50);\n"
        "process.stdout.write(JSON.stringify(items));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB_BODY.replace("\\", "/")),
           json.dumps(_rss_pipeline_src()), json.dumps(xml)),
        encoding="utf-8", newline="\n")
    r = subprocess.run([_node(), str(runner)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    assert r.returncode == 0, "本地 parseFeed 跑崩：\n%s\n%s" % ((r.stdout or "")[-400:], (r.stderr or "")[-1200:])
    return json.loads(r.stdout)


LAZY_XML = (u'<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            u'<channel><item><title>t</title>'
            u'<link>https://example.com/post/one/</link>'
            u'<description>摘要</description>'
            u'<content:encoded><![CDATA[<p>正文</p>'
            u'<img data-src="/imgs/a.png" alt="a">]]></content:encoded>'
            u'<pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>')


def test_realtime_parse_feed_promotes_lazy_src_and_absolutizes_it(tmp_path):
    """真产物三件事：data-src 被提升、相对路径被绝对化、尾巴没有半个标签。

    这一条是"接线不是断链"的直接证据 —— 源码里写了 `BODY.` 但产物里图还是没了，
    同样是白接（Task 2 的实测就是栽在顺序上：整枚 <img> 被 sanitize 删掉只剩 <p>）。
    """
    items = _parse_feed_product(tmp_path, LAZY_XML)
    assert len(items) == 1, "fixture 应该解析出 1 条，实际 %d" % len(items)
    fc = items[0].get("fullContent") or ""
    assert fc, "content:encoded 没进 fullContent（运行时入口形状变了）"
    assert 'src="https://example.com/imgs/a.png"' in fc, \
        "懒加载没被提升+绝对化（规范层没接上，或接在 sanitize 之后）：%s" % fc
    assert "<img" in fc, "整枚 <img> 又不见了：%s" % fc
    assert "data-src" not in fc, "data-src 该被 sanitize 剥掉，留着说明 sanitize 没跑：%s" % fc


def test_realtime_parse_feed_cap_leaves_no_dangling_tag(tmp_path):
    """超长正文必须过 capBody：截断点落在标签里时，半个标签要抹掉。

    fixture 是算出来的：让第 50000 个码点正好落在 `<img ...>` 内部 ⇒ 裸切片一定留下
    `<img src="https://e` 这种残骸（阅读器 innerHTML 一插就是整段渲染崩）。
    """
    pad = 49990
    body = u"<p>" + u"y" * pad + u"</p><img src=\"https://e.test/x.png\">"
    assert 50000 < len(body) < 50100, "fixture 本身要刚好跨过上限，实际 %d" % len(body)
    xml = (u'<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/">'
           u'<channel><item><title>t</title><link>https://example.com/post/two/</link>'
           u'<description>d</description><content:encoded><![CDATA[' + body + u']]></content:encoded>'
           u'<pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>')
    fc = _parse_feed_product(tmp_path, xml)[0]["fullContent"]
    assert len(fc) <= 50000, "没截断：%d 字符出厂" % len(fc)
    assert not re.search(r"<[^>]*$", fc), "尾巴挂着半个标签（还是裸切片）：%r" % fc[-40:]
    assert not re.search(r"&[#A-Za-z0-9]*$", fc), "尾巴挂着残缺实体：%r" % fc[-40:]
    assert fc.endswith("</p>"), "截断点没收敛到干净边界：%r" % fc[-24:]
    assert len(fc) > 49000, "截得太狠（正文被整段丢了）：%d" % len(fc)


# ================================================================ 对抗审查 ①：Atom 实时出口也产 fc
# `parseFeed` 的 Atom 分支与 RSS 分支是**两段代码**（台账 §20 的原始事故形态就是"只修一条"）。
# 审查实测：同一份 Atom 文档，构建期 Python 出 `full_content=<p>转义正文
# <img src="https://y.example/img/a.png"></p>`（提 src、绝对化、capBody、deepClean 四把刀全开火），
# 而 `api/rss.js` 的 Atom 分支只造 `{t,u,s,d}` ⇒ 四把刀在这条出口集体缺席，卡片根本没有 `fc`。
# 下面三条按"四把刀逐个可见 + 两条出口同口径 + 出厂卡片有 fc"写，全部本地现造 XML，零网络。
ATOM_LINK = u"https://example.com/post/one/"


def _atom_feed(body, link=ATOM_LINK, summary=u"摘要"):
    return (u'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            u'<entry><title>t</title><link href="' + link + u'"/>'
            u'<summary>' + summary + u'</summary>'
            u'<content type="html"><![CDATA[' + body + u']]></content>'
            u'<published>Tue, 01 Sep 2026 10:00:00 GMT</published></entry></feed>')


def _rss_item(body, link=ATOM_LINK, summary=u"摘要"):
    return (u'<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            u'<channel><item><title>t</title><link>' + link + u'</link>'
            u'<description>' + summary + u'</description>'
            u'<content:encoded><![CDATA[' + body + u']]></content:encoded>'
            u'<pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>')


def test_realtime_atom_entry_produces_full_content(tmp_path):
    """Atom 出口的四把刀逐个可见：提升 data-src、绝对化、sanitize 掉懒加载属性、脱站内导航。"""
    body = (u'<p>转义正文 <img data-src="/imgs/a.png" alt="a"></p>'
            u'<p>我们用 <a href="/tag/kubernetes">Kubernetes</a> 部署</p>')
    items = _parse_feed_product(tmp_path, _atom_feed(body))
    assert len(items) == 1, "fixture 应解析出 1 条 Atom entry，实际 %d" % len(items)
    fc = items[0].get("fullContent") or ""
    assert fc, ("Atom 分支没产 fullContent —— 提 src / 绝对化 / capBody / deepClean 四把刀"
                "在这条出口集体缺席（审查实测：Python 有 full_content，JS 无 fc）")
    assert 'src="https://example.com/imgs/a.png"' in fc, "懒加载没提升+绝对化：%r" % fc
    assert "data-src" not in fc, "sanitize 没跑（data-src 留在出厂正文里）：%r" % fc
    assert "/tag/kubernetes" not in fc and "Kubernetes" in fc, "deepClean 没跑：%r" % fc
    # 出厂卡片：没有 fc 就没有"有全文"这件事，阅读器只会退回摘要
    card = _card_product(tmp_path, _atom_feed(body))[0]
    assert card.get("fc"), "toCardItem 没把 Atom 的 fullContent 带进出厂字段 fc"


def test_realtime_atom_and_rss_exits_agree_on_the_same_body(tmp_path):
    """同口径判据：同一段正文走 Atom 与走 RSS 必须给出**逐字节相同**的 fc。

    两条出口各写一份清洗链就是下一个分叉源（构建期 `_fetch_rss` 的 Atom 分支与
    `_parse_rss_item` 吃的就是同一条链），所以这里不比"都有 fc"，比相等。
    """
    body = (u'<p>正文 <img data-src="/i/x.png"></p>'
            u'<p><a href="https://blog.example/author/anna">anna</a> 与 '
            u'<a href="https://openai.com/blog/x">原始公告</a></p>')
    atom = _parse_feed_product(tmp_path, _atom_feed(body))
    rss = _parse_feed_product(tmp_path, _rss_item(body))
    assert atom and rss, "两条出口都该解析出 1 条"
    fc_a = atom[0].get("fullContent") or ""
    fc_r = rss[0].get("fullContent") or ""
    assert fc_a, "Atom 出口没有 fc（①的原始形状）"
    assert fc_a == fc_r, "Atom 与 RSS 两条实时出口给出不同正文：\n atom: %r\n  rss: %r" % (fc_a, fc_r)
    assert "https://example.com/i/x.png" in fc_a, "绝对化没开火：%r" % fc_a
    assert 'href="https://openai.com/blog/x"' in fc_a, "外部正文链接被脱了：%r" % fc_a


def test_realtime_atom_cap_leaves_no_dangling_tag(tmp_path):
    """cap 这把刀也必须在 Atom 出口开火：截断点落在标签里时不许留残骸。"""
    pad = 49990
    body = u"<p>" + u"y" * pad + u"</p><img src=\"https://e.test/x.png\">"
    assert 50000 < len(body) < 50100, "fixture 本身要刚好跨过上限，实际 %d" % len(body)
    fc = _parse_feed_product(tmp_path, _atom_feed(body))[0].get("fullContent") or ""
    assert fc, "Atom 出口没有 fc，cap 无从谈起"
    assert len(fc) <= 50000, "没截断：%d 字符出厂" % len(fc)
    assert not re.search(r"<[^>]*$", fc), "尾巴挂着半个标签：%r" % fc[-40:]
    assert fc.endswith("</p>"), "截断点没收敛到干净边界：%r" % fc[-24:]


# ================================================================ 对抗审查 ④：构建期规则 2.6 接上实时出口
# 构建期 `_deep_clean_html` 的**规则 2.6**（空锚点 `href="#"` / 站点根链接 `href="/"` **整枚**删，
# 连文字一起）原本只长在 `build_rss_aggregator.py` 一份，实时出口的 `fc` 没有它 ⇒
# 同一份 `content:encoded` 两侧产物不同：Python 出厂 `<p>正文一</p><p>阅读更多</p>…`
# （壳被删空后由规则 3 收尾），JS 的 fc 里还留着 `<p><a href="#"></a>阅读更多</p>`。
#
# 判据按**行为对账**写，不 grep 函数名：同一批样本分别喂
#   · 构建期真函数 `build_rss_aggregator._deep_clean_html`
#   · 运行时真函数 `api/rss.js` 的 `deepCleanHtml`（切片进 node 跑，零网络、零 npm 依赖）
# 逐条比输出的**字节**。三种坏形状各自咬得住：整条刀没接（两侧不同 ⇒ 对账红）、
# 接错一格（挪到规则 3 之后 ⇒ 空 `<p></p>` 壳留在出厂正文，对账与出口判据都红）、
# 放宽成任意 href（正文里的"见下节" `#sec-2` 被吃 ⇒ 反例判据红）。
EMPTY_ANCHOR_SAMPLES = [
    (u"空锚点壳在正文之后", u'<p>正文一</p><p><a href="#">阅读更多</a></p>'),
    (u"根链接壳在正文之前", u'<p><a href="/">返回首页</a></p><p>正文二</p>'),
    (u"页内锚点不是空锚点", u'<p>见 <a href="#sec-2">第二节</a> 的讨论</p>'),
    (u"大写标签与大写属性名", u'<P><A HREF="#">壳</A></P>正文'),
    (u"壳带额外属性", u'<p><a href="#" title="更多">壳</a>正文</p>'),
    (u"空串 href 不在刀形里", u'<p><a href="">空值</a>正文</p>'),
    (u"根路径带内容", u'<p><a href="/x">真链接</a>正文</p>'),
    (u"未闭合的壳删不掉", u'<p>尾巴 <a href="#">未闭合'),
    (u"壳内套标签与换行", u'<p><a href="#"><span>套</span><br>壳</a></p>正文'),
    (u"两枚壳连着排", u'<p><a href="/">甲</a></p><p><a href="#">乙</a></p><p>正文</p>'),
    (u"壳跨行", u'<p>前 <a href="#">跨\n行\n壳</a></p>'),
    (u"一枚 a 上两个 href", u'<p><a href="/x" href="#">双 href</a>正文</p>'),
    (u"空文本的壳", u'<p><a href="#"></a>阅读更多</p>'),
    (u"href 无引号（两侧同盲区）", u'<p><a href=#>壳</a>正文</p>'),
    (u"div 里的壳", u'<div><a href="/">回首页</a></div><p>正文</p>'),
]

EMPTY_ANCHOR_EXIT_BODY = (u'<p>正文一</p><p><a href="#"></a>阅读更多</p>'
                          u'<p><a href="#">阅读全文</a></p>'
                          u'<p>见 <a href="#sec-2">第二节</a> 的讨论</p>')

_BUILD_MOD = {}


def _build_module():
    """构建期那个模块（对账的另一侧就在里面）。

    先认 `sys.modules` 再决定要不要 exec：`build_rss_aggregator` 顶层会把 `sys.stdout`
    重挂一次，同一进程里第二次 exec 会在关闭旧流时把解释器硬崩
    （口径抄 tests/rss_history/_loader.py 的 docstring；手法抄 test_reader_body_images.py）。
    """
    if "mod" not in _BUILD_MOD:
        import sys
        mod = sys.modules.get("build_rss_aggregator")
        if mod is None:
            sys.path.insert(0, os.path.join(ROOT, "tests", "rss_composite"))
            from _loader import load_build
            mod = load_build()
        _BUILD_MOD["mod"] = mod
    return _BUILD_MOD["mod"]


def _deep_clean_products(tmp_path, samples):
    """用 node 跑**真** `api/rss.js` 的 deepCleanHtml，逐条给返回值。

    样本走 JSON 文件中转、不进 JS 源码：带引号的样本如果能改写被测脚本，
    那"判据跑的是真产物"这件事本身就不可信（Task 1 的 C1 同一类）。
    """
    spec_p = tmp_path / "deep_clean_spec.json"
    out_p = tmp_path / "deep_clean_out.json"
    spec_p.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8", newline="\n")
    runner = tmp_path / "deep_clean_product.js"
    runner.write_text(
        "const fs = require('fs');\n"
        "const COVER = require(%s);\n"
        "const BODY = require(%s);\n"
        "const src = %s;\n"
        "eval(src);\n"
        "const samples = JSON.parse(fs.readFileSync(%s, 'utf8'));\n"
        "fs.writeFileSync(%s, JSON.stringify(samples.map(function (s) { return deepCleanHtml(s); })));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB_BODY.replace("\\", "/")),
           json.dumps(_rss_pipeline_src()),
           json.dumps(str(spec_p).replace("\\", "/")),
           json.dumps(str(out_p).replace("\\", "/"))),
        encoding="utf-8", newline="\n")
    r = subprocess.run([_node(), str(runner)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    assert r.returncode == 0, "本地 deepCleanHtml 跑崩：\n%s\n%s" % (
        (r.stdout or "")[-400:], (r.stderr or "")[-1200:])
    return json.loads(out_p.read_text(encoding="utf-8"))


def _sample_outputs(tmp_path):
    raw = [s for _name, s in EMPTY_ANCHOR_SAMPLES]
    out = _deep_clean_products(tmp_path, raw)
    assert len(out) == len(raw), "样本条数与产物条数不符（node 侧吃了注入？）"
    return raw, out


def test_realtime_deep_clean_matches_buildtime_on_empty_anchor_shapes(tmp_path):
    """行为对账（审查 ④ 的主判据）：同一份输入两侧逐条给同一个答案。"""
    deep_clean_py = _build_module()._deep_clean_html
    raw, js = _sample_outputs(tmp_path)
    diff = []
    for (name, src), got in zip(EMPTY_ANCHOR_SAMPLES, js):
        want = deep_clean_py(src)
        if want != got:
            diff.append(u"【%s】\n  输入   %r\n  构建期 %r\n  运行时 %r" % (name, src, want, got))
    assert not diff, ("空锚点/根链接整枚删这一格两侧行为不同 —— 构建期有、实时出口没接"
                      "（或接错格/形状不一致）：\n%s" % "\n".join(diff))
    # 对账本身不许空转：这条刀必须在运行时真的动过手（两侧都"什么都不删"也能对上，那不算）。
    fired = [n for (n, s), g in zip(EMPTY_ANCHOR_SAMPLES, js) if g != s]
    assert len(fired) >= 6, "刀没开火，只改了 0 条样本：%s" % fired
    assert u"页内锚点不是空锚点" not in fired, "放宽了：页内锚点被一起吃掉"


def test_realtime_deep_clean_empty_anchor_shapes(tmp_path):
    """运行时侧的绝对行为：删什么、留什么，逐条给死（对账红了要能指到是哪一半坏）。"""
    from_name = dict(zip([n for n, _s in EMPTY_ANCHOR_SAMPLES], _sample_outputs(tmp_path)[1]))
    assert from_name[u"空锚点壳在正文之后"] == u"<p>正文一</p>", from_name[u"空锚点壳在正文之后"]
    assert from_name[u"根链接壳在正文之前"] == u"<p>正文二</p>", from_name[u"根链接壳在正文之前"]
    assert from_name[u"两枚壳连着排"] == u"<p>正文</p>", from_name[u"两枚壳连着排"]
    assert from_name[u"空文本的壳"] == u"<p>阅读更多</p>", from_name[u"空文本的壳"]
    assert from_name[u"大写标签与大写属性名"] == u"正文", from_name[u"大写标签与大写属性名"]
    assert from_name[u"一枚 a 上两个 href"] == u"<p>正文</p>", \
        "贪婪 `[^>]*` 改 lazy 就锚在第一个 href 上（两侧分叉的形状）"
    assert from_name[u"div 里的壳"] == u"<p>正文</p>", from_name[u"div 里的壳"]
    # 反例：一刀都不许动
    for n in (u"页内锚点不是空锚点", u"空串 href 不在刀形里", u"根路径带内容",
              u"未闭合的壳删不掉", u"href 无引号（两侧同盲区）"):
        src = dict(EMPTY_ANCHOR_SAMPLES)[n]
        assert from_name[n] == src, "反例被吃了【%s】：%r → %r" % (n, src, from_name[n])


def test_realtime_fulltext_exit_has_no_empty_anchor_shell(tmp_path):
    """端到端：两条实时出口（RSS 与 Atom）出厂的 fc 里空锚点壳整枚消失、页内锚点活着。

    这一格只钉 `href="#"`：`href="/"` 那半在**出口链**上到不了本刀 —— normalize 在
    deepClean 之前，`/` 先被绝对化成 `https://host/` 了（构建期同一条链、同一个顺序，
    所以两侧同形）。`/` 那一半的行为对账在上一批判据（deepClean 层逐条比输出）里钉。
    """
    for kind, xml in ((u"RSS", _rss_item(EMPTY_ANCHOR_EXIT_BODY)),
                      (u"Atom", _atom_feed(EMPTY_ANCHOR_EXIT_BODY))):
        fc = _parse_feed_product(tmp_path, xml)[0].get("fullContent") or ""
        assert fc, "%s 出口没产 fc，正文一刀都没接上" % kind
        assert 'href="#"' not in fc, "%s 出口的 fc 里空锚点还在（审查 ④ 的原始形状）：%r" % (kind, fc)
        assert "阅读全文" not in fc, "%s 出口没整枚删（文字留在正文里）：%r" % (kind, fc)
        assert "阅读更多" in fc and "正文一" in fc, "%s 出口把正文一起吃了：%r" % (kind, fc)
        assert "<p></p>" not in fc, "%s 出口壳删空后没被规则 3 收尾（接错一格）：%r" % (kind, fc)
        assert 'href="#sec-2"' in fc and "第二节" in fc, "%s 出口吃了页内锚点：%r" % (kind, fc)


# ================================================================ Task 5：/api/article 返回契约
# 契约表（Task 6 的前端 _FT_NOTES 必须与这里同集合，一个字段名都不许改）：
#   成功 {ok:true, url, title, content, source:'rss_fulltext'|'readability'|'youtube'|'github',
#         degraded?:'paywall'|'short'}
#   失败 {ok:false, error:'missing_url'|'invalid_url'|'timeout'|'fetch_failed'|'challenge_page'
#         |'no_body'|'extraction_failed'}
SUCCESS_SOURCES = ["rss_fulltext", "readability", "youtube", "github"]
FAILURE_CODES = ["missing_url", "invalid_url", "timeout", "fetch_failed",
                 "challenge_page", "no_body", "extraction_failed"]
DEGRADED_VALUES = ["paywall", "short"]


def _func_src(name, text):
    """按大括号配平切出某个函数的源码（判据要按函数体看，不按"文件里出现过"看）。"""
    a = text.find("function " + name + "(")
    assert a > 0, "api/article.js 里找不到 %s，函数名或形状变了" % name
    i = text.index("{", a)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[a:j + 1]
    raise AssertionError("%s 的大括号没配平" % name)


def test_no_meta_pseudo_fulltext_any_more():
    """把 og:description 包成 <p> 当全文返回，与阅读器上方摘要重复（用户报的"全文=摘要"）。
    取消它，改成明确的 no_body 失败 —— 不许再"好歹返回点东西"。

    只钉 extractGeneric：`extractYouTube`/`extractGitHub` 里的 desc 兜底**必须保留**，
    那是这两类站点的正当呈现（视频页/仓库页本来就没有正文），一刀切会把它俩打回抓不到。
    """
    src = _read(API_ARTICLE)
    assert "'meta'" not in src and '"meta"' not in src, "article.js 还在返回 source:'meta'"
    body = _func_src("extractGeneric", src)
    assert "og:description" not in body and 'name="description"' not in body, \
        "extractGeneric 里还在用 og:description 兜正文"
    assert "'youtube'" in src and "'github'" in src, "youtube/github 两个抽取器被一起删掉了"
    assert "og:description" in _func_src("extractYouTube", src), "youtube 的 desc 兜底被误删"


def test_failure_codes_are_the_documented_set():
    """码表一致性：契约里声明的每个 error 码都必须**真的被返回**（只看代码行）。

    双向都钉 —— 只钉"在册的都在源码里"，将来加个不在册的码就等于给前端留了空文案；
    只钉"源码里的都在册"，删码就发现不了（挑战页那条被删时，前端的"这个页面要人工验证"
    会静默变成"未知错误"，正是本项目点名的自欺形状）。

    只看代码行不只看"文件里出现过"：本文件顶部的契约注释块里逐字写着全部 7 个码，
    拿 `code in src` 做正向判据时，变异⑥（把 challenge_page 改成 fetch_failed）**照样绿**
    —— 码只活在注释里 = 前端文案被架空。这是我在红→绿之间自己撞到的一条假绿。
    """
    src = _code(_read(API_ARTICLE))
    returned = set(re.findall(r"\berror:\s*'([a-z_]+)'", src))
    for stmt in re.findall(r"const errType = [^;]+;", src):
        returned |= set(re.findall(r"'([a-z_]+)'", stmt))
    assert returned, "判据读不到任何错误码，返回形状变了（本判据正在空跑）"
    missing = [c for c in FAILURE_CODES if c not in returned]
    assert not missing, "这些契约里的错误码不再真的被返回：%s ⇒ 前端 _FT_NOTES 拿不到文案" % missing
    extra = sorted(returned - set(FAILURE_CODES))
    assert not extra, "源码在返回契约外的错误码 %s：前端没有对应文案，用户看到未知错误" % extra


def test_challenge_page_and_degraded_are_wired():
    src = _code(_read(API_ARTICLE))   # 同下：注释里写一句函数名不算接上了
    assert re.search(r"isChallengePage\(", src), "没接挑战页判定 ⇒ WAF 壳页仍会被当正文"
    assert re.search(r"classifyBody\(", src), "没接付费墙/短正文判定"
    assert re.search(r"degraded", src), "degraded 字段没落到返回值"


def test_challenge_gate_runs_before_dom_construction():
    """WAF 壳页返回 HTTP 200，`resp.ok` 挡不住 ⇒ 必须在 new JSDOM 之前拦。

    放在 JSDOM 之后也能判，但 Readability 已经先抽出过一版导航垃圾；
    而且挑战页正文抽出来就是问题 1 的原始症状（阅读器里一屏"正在验证您的浏览器"）。
    """
    src = _code(_read(API_ARTICLE))
    a = src.find("isChallengePage(")
    b = src.find("new JSDOM(")
    assert 0 < a < b, "挑战页判定没排在 new JSDOM 之前（a=%d b=%d）" % (a, b)
    assert re.search(r"return res\.json\(\{\s*ok:\s*false,\s*error:\s*'challenge_page'\s*\}\)", src), \
        "命中挑战页没有明确报 challenge_page"


def test_extraction_failure_now_says_no_body_not_extraction_failed():
    """抽不出正文 = no_body（"这篇没有可显示的正文"）；extraction_failed 只留给真的抛异常。

    两者混用一个码，前端就没法区分"这站本来没正文"和"我抓挂了"（该重试/该换源）。
    """
    src = _code(_read(API_ARTICLE))   # 只扫代码行：闸门里那段解释注释不该把判据读断
    m = re.search(r"if \(\s*!result \|\| !result\.content[^)]*\)\s*\{\s*return res\.json\(\{\s*ok:\s*false,\s*error:\s*'([a-z_]+)'\s*\}\)", src)
    assert m, "内容长度闸门形状变了，判据读不到它"
    assert m.group(1) == "no_body", "抽不出正文仍报 %r —— 与'抓挂了'混成一个码" % m.group(1)
    assert re.search(r"}\s*catch \(e\) \{\s*return res\.json\(\{\s*ok:\s*false,\s*error:\s*'extraction_failed'\s*\}\)", src), \
        "异常分支没报 extraction_failed"


def test_readability_acceptance_gate_is_still_100_chars():
    """100 字这道**接受门槛**保持不动。

    提到 1200 会把短小真实文章整批变成"抓不到"—— 那是用一个新故障换旧故障（已裁定）。
    短正文的正确出口是 degraded:'short'（照给内容，只是不再暗示"这就是全文"），
    1200 这个数只住在 lib/body_rules.js 的 SHORT_BODY_CHARS 里，不许在 article.js 再写一份。
    """
    body = _func_src("extractGeneric", _read(API_ARTICLE))
    assert re.search(r"len\s*<\s*100\b", body) or re.search(r"textContent\.length\s*>\s*100\b", body), \
        "接受门槛不再是 100 字：%s" % body[-400:]
    assert "1200" not in _read(API_ARTICLE), "1200 被抄进 article.js：短正文阈值只许住在 body_rules 里"


def test_degraded_vocabulary_is_not_invented_here():
    """degraded 的值只许来自 classifyBody，且只可能是 paywall/short（另一个是 null=不标注）。

    在 article.js 里自己写 'paywall'/'short' 就是第二套词表：Task 6 的前端按一套写文案，
    运行时可能给出第三种值，落到"未知错误"。返回域本身由 node 用例钉
    （tests/rss_js/test_body_rules.js 的 classifyBody 返回域那条）。
    """
    src = _read(API_ARTICLE)
    assert not re.search(r"degraded\s*[:=]\s*['\"]", src), "degraded 被硬编码成字面量，绕开了 classifyBody"
    assert re.search(r"BODY\.classifyBody\(\s*len\s*,\s*rawHtml\s*\)", _code(src)), \
        "classifyBody 没按 (抽取正文长度, 原始 HTML) 调用"
    assert re.search(r"if \(result\.degraded\)\s*out\.degraded\s*=\s*result\.degraded", src), \
        "degraded 没落到成功返回值（或缺了就硬塞 null，前端要判两种'没有'）"


def test_no_retry_and_timeout_untouched():
    """不许给 /api/article 加重试（已裁定）：重试对 WAF/付费墙零收益，只把 8s 变 16s，
    而 vercel.json 的 `maxDuration: 15` 正是线上 FUNCTION_INVOCATION_TIMEOUT 的来源。
    """
    src = _read(API_ARTICLE)
    assert re.search(r"const FETCH_TIMEOUT = 8000;", src), "FETCH_TIMEOUT 被动过：超时预算是 15s 闸门的一部分"
    assert src.count("await fetch(") == 1, "fetch 出现 %d 次 ⇒ 给这个端点加了重试" % src.count("await fetch(")
    assert "retry" not in src.lower() and "attempt" not in src.lower(), "引入了重试逻辑（明确裁定不做）"


def test_success_payload_shape_and_source_values():
    src = _read(API_ARTICLE)
    m = re.search(r"const out = \{ ok: true[^}]*\}", _code(src))
    assert m, "读不到成功返回的构造行，返回形状变了"
    for key in ("url", "title:", "content", "source"):
        assert key in m.group(0), "成功返回缺字段 %s：%s" % (key, m.group(0))
    for s in SUCCESS_SOURCES:
        assert re.search(r"'%s'" % s, src), "契约里的 source 值 %s 在源码里不存在" % s
    extra = set(re.findall(r"source:\s*'([a-z_]+)'", src)) - set(SUCCESS_SOURCES)
    assert not extra, "出现了契约外的 source 值 %s：前端按 source 决定提示，多出来的值没人认得" % sorted(extra)


# ---------------------------------------------------------------- 导出审计（不许留孤儿接口）
def test_body_rules_exports_all_have_callers():
    """`lib/body_rules.js` 的每个导出都必须有调用方，否则就是"已导出没人调"的接口。

    本仓点名的自欺形状之一：为了让判据看起来全绿而留一个没人用的导出，
    或编一个假调用方。调用方只算 `api/`、`lib/`、`tests/` 三处（node 用例集与对账判据都算），
    排除 lib/body_rules.js 自身。宁可删导出，也不许留孤儿。
    """
    body = _read(LIB_BODY)
    m = re.search(r"module\.exports = \{(.*?)\n\};", body, re.S)
    assert m, "读不到 module.exports 块，导出面形状变了"
    names = [x for x in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", m.group(1))]
    assert names, "导出面为空"
    callers = {}
    for base in ("api", "lib", "tests", "tools"):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith((".js", ".py")):
                    continue
                p = os.path.join(dirpath, fn)
                if os.path.abspath(p) == os.path.abspath(LIB_BODY):
                    continue
                t = _read(p)
                for n in names:
                    if re.search(r"(BODY|R)\." + n + r"\b|['\"]" + n + r"['\"]", t):
                        callers.setdefault(n, []).append(os.path.relpath(p, ROOT))
    orphans = sorted(n for n in names if n not in callers)
    assert not orphans, (
        "这些导出谁都不调用：%s ⇒ 删掉导出（函数本体可以留着被内部调用）。"
        "报告里要逐条给 导出→调用方 清单" % orphans)


# ================================================================ R43：三把刀的运行时出口
# 这三把刀（HN 模板重写 / 粘连裸链接 / 站内导航去链接）原本只接在构建期，实时通道
# `?source=`/`?batch=` 自己抓 RSS 却没有它们 ⇒ 线上走实时出口的用户照旧看到四行模板。
# 下面几条是"接上了、而且接在对的那一格"的直接证据：拿**真 parseFeed 的产物**说话，
# 而不是"源码里出现过 BODY.xxx"（那种静态判据在子匹配变异下不红，Task 8/9 §4.2 栽过）。

_HN_DESC = (u"Article URL: https://ex.test/a\n"
            u"Comments URL: https://news.ycombinator.com/item?id=1\n"
            u"Points: 254\n# Comments: 162")
# 全角冒号一律写转义：它与半角 ':' 在编辑器里看不出区别（Task 8 的实测教训）
_HN_DESC_ZH = (u"文章网址：https://ex.test/a\n"
               u"评论网址：https://news.ycombinator.com/item?id=2\n"
               u"积分：7\n# 评论数：9")
_GLUED = u"https://www.nodeseek.com/post-957723-1看了大佬的IX文章必须有行动力"
_SEPARATED = u"https://ex.test/a 看了大佬的文章"


def _rss_xml(desc, body=u"", link=u"https://ex.test/a"):
    return (u'<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            u'<channel><item><title>t</title><link>' + link + u'</link>'
            u'<description>' + desc + u'</description>'
            + (u'<content:encoded><![CDATA[' + body + u']]></content:encoded>' if body else u"")
            + u'<pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>')


def _atom_xml(summary):
    return (u'<?xml version="1.0"?><feed><entry><title>t</title>'
            u'<link href="https://ex.test/a"/>'
            u'<summary>' + summary + u'</summary>'
            u'<published>Tue, 01 Sep 2026 10:00:00 GMT</published></entry></feed>')


def _card_product(tmp_path, xml):
    """真 parseFeed 的产物再过**真出口函数** `toCardItem` ⇒ 出厂 `s` 字段的真值。

    R43 的摘要刀接在 `toCardItem`（fetchOne 用的那张映射），不接在 parseFeed 里：
    parseFeed 的 `summary` 形状一个字节都不许变（去重键与两份既有 harness 都指着它），
    而用户看的、以及被写进滚动缓存的是 `s`。
    """
    runner = tmp_path / "card_product.js"
    runner.write_text(
        "const COVER = require(%s);\n"
        "const BODY = require(%s);\n"
        "const src = %s;\n"
        "eval(src);\n"
        "const its = parseFeed(%s, 'probe', 50);\n"
        "process.stdout.write(JSON.stringify(its.map(toCardItem)));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB_BODY.replace("\\", "/")),
           json.dumps(_rss_pipeline_src()), json.dumps(xml)),
        encoding="utf-8", newline="\n")
    r = subprocess.run([_node(), str(runner)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    assert r.returncode == 0, "真出口 toCardItem 跑崩：\n%s\n%s" % (
        (r.stdout or "")[-400:], (r.stderr or "")[-1200:])
    return json.loads(r.stdout)


def _summary(tmp_path, xml):
    cards = _card_product(tmp_path, xml)
    assert cards, "解析+映射后一条都没有，fixture 与生产不同形"
    return cards[0]["s"]


def _card(tmp_path, xml):
    cards = _card_product(tmp_path, xml)
    assert cards, "解析+映射后一条都没有，fixture 与生产不同形"
    return cards[0]


def test_realtime_rss_summary_rewrites_the_hn_template(tmp_path):
    """实时 RSS 出口：四行模板出厂时压成一行，裸链接一条不留。"""
    s = _summary(tmp_path, _rss_xml(_HN_DESC))
    assert "Article URL" not in s and "Comments URL" not in s, "模板行还在（刀没接上）：%r" % s
    assert "news.ycombinator.com" not in s, "Comments URL 裸链没剥：%r" % s
    assert "254" in s and "162" in s and "Hacker News" in s, \
        "分数/评论数/来源被一起吃掉了：%r" % s


def test_realtime_rss_summary_rewrites_the_zh_template(tmp_path):
    """中文版（文章网址/评论网址/积分/评论数，全角冒号）也要命中：判形状不判语言。"""
    s = _summary(tmp_path, _rss_xml(_HN_DESC_ZH))
    assert "文章网址" not in s and "评论网址" not in s, "中文模板没命中：%r" % s
    assert "7" in s and "9" in s and "Hacker News" in s, s


def test_realtime_atom_summary_rewrites_the_hn_template(tmp_path):
    """Atom 分支是**另一段代码**：只接 RSS 那一半就是半个断链（Task 8 的 ②b 同形）。"""
    s = _summary(tmp_path, _atom_xml(_HN_DESC))
    assert "Article URL" not in s and "Points:" not in s, s
    assert "254" in s and "Hacker News" in s, s


def test_realtime_rss_summary_strips_the_glued_url(tmp_path):
    """NodeSeek 实测形状：粘连裸链接剥掉，正文一个字不少。"""
    s = _summary(tmp_path, _rss_xml(_GLUED, link=u"https://www.nodeseek.com/post-957723-1"))
    assert "nodeseek.com" not in s, "粘连的裸链接还在：%r" % s
    assert s.startswith(u"看了大佬"), "正文被吃掉了一部分：%r" % s


def test_realtime_summary_does_not_strip_a_separated_url(tmp_path):
    """反例：空格分隔的"链接 + 正文"不许动（剥多了就是把摘要改坏）。"""
    s = _summary(tmp_path, _rss_xml(_SEPARATED))
    assert "ex.test/a" in s, "空格分隔的链接被误剥：%r" % s


def test_realtime_body_delinks_nav_links_and_keeps_external(tmp_path):
    """正文出口：站内 /tag/ 脱链接留文字，外部正文链接的 href 一路活到出厂。"""
    body = (u'<p>我们用 <a href="/tag/kubernetes">Kubernetes</a> 部署，'
            u'参考 <a href="https://openai.com/blog/x">原始公告</a></p>')
    fc = _parse_feed_product(tmp_path, _rss_xml(u"d", body=body))[0]["fullContent"]
    assert "Kubernetes" in fc and "原始公告" in fc, "正文词被吃了：%r" % fc
    assert "/tag/kubernetes" not in fc, \
        "导航链接没被脱（去链接那半没接进 deepCleanHtml）：%r" % fc
    assert 'href="https://openai.com/blog/x"' in fc, "外部正文链接被脱了：%r" % fc


def test_realtime_summary_knives_run_in_the_buildtime_order():
    """链形判据：先 HN 刀、再粘连刀（倒序会先改掉 HN 要看的行首形状），两个入口都接。"""
    seg = _rss_pipeline_src()
    code = _code(seg)      # 注释里提"cleanSummary/truncate"不算接线，也不算断链
    assert re.search(r"return\s+collapseRuns\(\s*BODY\.stripGluedUrl\(\s*BODY\.rewriteHnSummary\(",
                     code), ("cleanSummary 不再是「先 HN 后粘连」的嵌套顺序，"
                             "与构建期 _strip_glued_url(_rewrite_hn_summary(...)) 分叉了")
    assert code.count("cleanSummary(") == 2, (
        "cleanSummary 应该定义 1 次 + 出厂出口 toCardItem 1 次，实际 %d 次"
        % code.count("cleanSummary("))
    assert code.count("summaryRaw:") == 2, (
        "Atom 与 RSS 两个分支都要把**未剥标签的原始描述**留给出口（%d 处）"
        % code.count("summaryRaw:"))
    assert "s: truncate(cleanSummary(it.summaryRaw" in code, "出厂 s 没走带刀出口"
    assert "truncate(stripHtml(" in code, "parseFeed 的 summary 形状变了（去重键与既有 harness 指着它）"
    assert "s: it.summary," not in code, "旧出口（直接抄 parseFeed.summary）又回来了"
    # HN 刀必须看得见换行：先 stripHtmlKeepLines，压空白放回最后一步。
    # 这里用正则而不是子串：`stripHtml(` 是 `stripHtmlKeepLines(` 的前缀，
    # 子串判据会把"接对了"的写法也当成"接错了"（本仓踩过的子匹配口径）。
    assert not re.search(r"rewriteHnSummary\(\s*stripHtml\(", code.replace("\n", "")), (
        "摘要刀接在了压完空白的 stripHtml 之后 ⇒ HN 那四行按行锚定，永不命中（又一把空转刀）")


def test_runtime_deep_clean_has_no_class_or_id_knife():
    """R42 的运行时对称：deepCleanHtml 里不许再有按 class/id 找容器的刀。

    `api/rss.js` 的 sanitizeHtml 与构建期同款（ALLOWED_ATTRS 不保留 class/id），
    而 deepCleanHtml 的唯一调用点就在 sanitizeHtml 之后 ⇒ 那条刀命中恒为 0。
    """
    src = _read(API_RSS)
    a = src.find("function deepCleanHtml(")
    assert a >= 0, "找不到 deepCleanHtml（运行时清洗入口改名了？）"
    end = src.find("\nfunction ", a + 10)
    assert end > a, "deepCleanHtml 之后找不到下一个顶层函数，切片没有结束边界"
    code = _code(src[a:end])
    assert not re.search(r"\(\?:class\|id\)|class\s*=|id\s*=", code), (
        "运行时 deepCleanHtml 里又出现了按 class/id 匹配的规则，它接不到出口")
    assert "BODY.delinkNavLinks(text)" in code, "去链接那半没接进 deepCleanHtml"


def test_strip_html_split_keeps_the_old_output_shape(tmp_path):
    """stripHtml 拆成两层后，**出厂形状不许变**：卡片与去重键还指着单行文本。

    拆层只是为了让 HN 那把刀看得见换行；`stripHtml` 自己必须仍然压空白 + trim，
    否则标题/摘要会带着换行进卡片 —— 那是一条没被派工的行为变更。
    """
    runner = tmp_path / "strip_html_shape.js"
    probe = [u"  a\n\nb\tc" + chr(0x00a0), u"a\n\nb"]
    runner.write_text(
        # COVER/BODY 注入与本文件 `_parse_feed_product` 同一条理由：切片切不到文件顶部的
        # require，而审查 ③ 之后 `stripHtmlKeepLines` 的实体那一格要走 BODY。
        "const COVER = require(%s);\n"
        "const BODY = require(%s);\n"
        "const src = %s;\neval(src);\n"
        "const items = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify([stripHtml(items[0]), stripHtmlKeepLines(items[1])]));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB_BODY.replace("\\", "/")),
           json.dumps(_rss_pipeline_src())), encoding="utf-8", newline="\n")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(probe, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([_node(), str(runner), str(spec)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    assert r.returncode == 0, "node 跑 stripHtml 崩了：\n%s" % (r.stderr or "")[-800:]
    got, kept = json.loads(r.stdout)
    # NBSP 在 JS 的 `\s` 里 ⇒ 被压成空格再 trim 掉（**改动前就是这个形状**，
    # 这里要钉的是"没变"，不是"等于 Python _strip_html"——后者保留换行、不做空白折叠）
    assert got == u"a b c", "stripHtml 的出厂形状变了：%r" % got
    assert kept == u"a\n\nb", "stripHtmlKeepLines 不该压换行（HN 刀靠它看行）：%r" % kept
