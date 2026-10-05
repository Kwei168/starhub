# -*- coding: utf-8 -*-
"""正文规范：构建期 Python 与运行时 Node 两份实现必须给逐字相同的答案。

为什么这条比"两边各自测自己的用例"更强：Task 1/3 是同一套规则的两次实现，
各自绿而彼此分叉是完全可能的（Python 用 `urljoin`、JS 用 `new URL`，
`..` 折叠与百分号编码就有历史差异）。本仓的同形状事故：
  ① `_needs_translation` —— Python 剥 ANSI/URL、JS 没剥，分叉 5/14 条；
  ② 封面判空 —— `HTTPS://…` 在 Python 侧判空、JS 侧因大小写比 scheme 而放行。
两次都是"把两边放在同一批样本上逐条对"才发现的，所以这次直接按对账写判据。

**样本清单只有这一份**（`tests/rss_js/test_body_rules.js` 里的只是它自己的本地子集，
不做对账用）—— 两边各抄一份样本就是第 5 个分叉源。

对账只比**输出与判定值**，不比正则字面或函数名（账本 R28）。另外单独钉五件
容易各走各路的事实：懒加载属性清单同序、cap 默认上限相同、空白码位表等于
Python `isspace()`、词字符类覆盖 Python `\\w`、占位词干表同值。

非 ASCII 样本的比较口径（账本 R20/R26）：
    ASCII 样本 → 比字节相等；含非 ASCII 的样本 → 允许 `unquote(js) == py`。
这条放宽**为什么存在**由 `test_absolutization_relaxation_is_explained_not_hidden`
自己演一遍（`new URL()` 把 `/图/a.png` 编成 `/%E5%9B%BE/a.png`，而 Python
`urljoin` 保留原始字节）。看懂之后仍然不许去"修 Python 侧"——
构建期其余环节（`_strip_oss_signature`、sanitizer 的 `&`→`&amp;`）都按原始字节走，
改成百分号编码会引入二次编码，那才是把分叉坐实。
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from urllib.parse import unquote

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.environ.get("STARHUB_BODY_RULES") or os.path.join(ROOT, "lib", "body_rules.js")
# 审查 ③ 的接线判据要跑 `api/rss.js` 的真出口函数，注入点与本仓约定同名（变异体走环境变量）
API_RSS = os.environ.get("STARHUB_API_RSS") or os.path.join(ROOT, "api", "rss.js")
LIB_COVER = os.environ.get("STARHUB_RSS_COVER") or os.path.join(ROOT, "lib", "rss_cover.js")
JS_TEST = os.path.join(ROOT, "tests", "rss_js", "test_body_rules.js")
sys.path.insert(0, os.path.join(ROOT, "tests", "rss_composite"))
from _loader import load_build  # noqa: E402

mod = load_build()

BASE = "https://mp.weixin.qq.com/s/AbC123"
DIRBASE = "https://blog.example/dir/post.html"

# 反斜杠/制表/控制字符一律程序化构造：上一批金标准样本里 `"\\u0026"` 被 shell 与字符串层
# 各解一次，"测了但没真测"（Task 1 的 C1 就是这么漏掉的）。
BS = chr(92)
TAB = chr(9)
NEL = chr(0x85)
NBSP = chr(0xa0)
FS = chr(0x1c)
BOM = chr(0xfeff)
ZWSP = chr(0x200b)
SOH = chr(1)
ARABIC_3 = chr(0x0663)

# ---------------------------------------------------------------- 样本清单
# (输入 HTML, base_url)。前 23 条 = task-3-golden.json 的 normalize 行（同序同输入），
# 其余是本轮扩面：模板注入类（`\u0026`/`\1`/`$&`/`$1`/`` $` ``）、大小写、属性名周围空白、
# 同名属性重复、占位词干、懒加载优先级、Python `\w` 的 Unicode 口径、无 base、
# base 带裸引号、urljoin 的 `.`/`..`/`;params`/`?query`/`#frag` 分支。
NORM_SAMPLES = [
    ['<p>x</p><img data-src="https://mmbiz.qpic.cn/a.jpg">', BASE],
    ['<img src="data:image/gif;base64,R0" data-src="https://mmbiz.qpic.cn/b.jpg">', BASE],
    ['<img src="https://cdn.example/real.png" data-src="https://cdn.example/o.png">', BASE],
    ['<img src="/i/a.png" data-src="/i/lazy.png">', BASE],
    ['<img data-original="A.png" data-src="B.png">', BASE],
    ['<img data-croporisrc="C.png" data-lazy-src="D.png">', BASE],
    ['<img src="/x/lazy_cat_pic.png" data-src="/y/640.jpg">', BASE],
    ['<img src="https://mmbiz.qpic.cn/mmbiz_jpg/abc1x1def/960.jpg" '
     'data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc1x1def/640.jpg">', BASE],
    ['<img src="https://e.com/0x0.jpeg?v=2" data-src="https://e.com/real.jpg">', BASE],
    ['<img src="https://e.com/blank2.gif" data-src="https://e.com/real.jpg">', BASE],
    ['<img src="https://e.com/a.blank" data-src="https://e.com/real.jpg">', BASE],
    ['<img src="https://e.com/lazy/640x" data-src="https://e.com/real.jpg">', BASE],
    ['<img src="//cdn.example/c.png"><a href="#sec">s</a>', BASE],
    ['<a href="../up/../b?q=1">t</a>', DIRBASE],
    ['<a href="HTTPS://EX.COM/A">t</a>', BASE],
    ['<img src="&#47;i/a.png">', BASE],
    ['<img data-src="https://a&b.jpg" src="data:,">', BASE],
    ['<img data-src="https://a' + SOH + 'b.jpg">', BASE],
    ["<p title='q'>x</p><img data-src='r.jpg'>", BASE],
    ['<img data-src="https://e.com/a>b.jpg" alt="x">', BASE],
    ['<img src="/i/a.png">', ""],
    ["", BASE],
    ["<p>正常正文，无图</p>", BASE],
    # ---- 扩面 ----
    ['<img src="/i/a b.png">', BASE],                                # 空格：new URL 编成 %20
    ['<a href="' + BS + 'a.png">', BASE],                            # 反斜杠是普通路径字符
    ['<img data-src="https://a' + BS + 'u0026b.jpg">', BASE],        # Python re.sub 模板炸点
    ['<img data-src="https://a' + BS + '1b.jpg">', BASE],            # 同上（invalid group ref）
    ['<img data-src="https://a$&b.jpg">', BASE],                     # JS 替换串炸点：`$&`
    ['<img data-src="https://a$1b.jpg" src="data:,">', BASE],        # JS：`$1` 注捕获组
    ['<img data-src="https://a$`b.jpg">', BASE],                     # JS：`` $` `` 注前缀
    ['<img data-src="https://a$&quot;b.jpg" src="data:,">', BASE],
    ['<IMG SRC="/a.png" DATA-SRC="x">', BASE],                       # 大写标签/属性名保形
    ['<img src = "/a.png">', BASE],                                  # 属性名与 = 之间的空白
    ['<img src' + FS + '= "/a.png">', BASE],                          # FS：Python 的空白类认、JS 的 \\s 不认
    ['<img src' + BOM + ' = "/a.png">', BASE],                        # FEFF：反过来，JS 的空白类多认一个
    ['<img src="/a' + TAB + 'b.png">', BASE],                        # urlsplit 吃掉制表符
    ['<img src="/a.png">', 'https://e.com/d"q/x'],                   # M4：base 带裸引号
    ['<img src="/a.png">', "ftp://e.com/x"],                         # 非 http(s) 的 base
    ['<img src="/a.png">', FS + BASE],                               # base 前导 FS（Python strip 认它）
    ['<img data-src="a.png"><img src="b.gif" data-lazy-src="c.png">', BASE],
    ['<img __proto__="p" data-src="y.png">', BASE],                  # 不可信属性名
    ['<img toString="t" constructor="c" data-croporisrc="z.png">', BASE],
    ['<img data-src="" data-original="real.png">', BASE],            # 空值即跳过
    ['<img data-src="   " data-original="r.png">', BASE],            # strip 后为空即跳过
    ['<img data-src="' + NBSP + '" data-original="r.png">', BASE],
    ['<img data-src="' + FS + '" data-original="r.png">', BASE],     # JS 的 trim() 不认 FS ⇒ 必分叉
    ['<img src="DATA:image/gif;base64,x" data-src="r.png">', BASE],
    ['<img src="https://e.com/spacer_1x1.png" data-src="r.jpg">', BASE],
    ['<img src="https://e.com/1x1.png?v=2" data-src="r.jpg">', BASE],
    ['<img src="https://e.com/0X0.png" data-src="r.jpg">', BASE],
    ['<video poster="/p.mp4" src="/v.mp4"></video>', BASE],
    ['<a href="tel:123">t</a><a href="mailto:a@b">t</a><a href="data:text/plain,x">t</a>', BASE],
    ['<a href="javascript:void(0)">t</a>', BASE],                    # 其他 scheme 原样返回
    ['<a href="&#44;x">t</a>', BASE],
    ['<a href="?q=1">t</a>', BASE],                                  # 空 path ⇒ 继承 base path
    ['<a href=".">t</a>', "https://blog.example/dir/x.html"],        # 尾斜杠后处理
    ['<a href="..">t</a>', "https://blog.example/dir/x.html"],
    ['<a href="/">t</a>', BASE],
    ['<a href="a/../b">t</a>', BASE],
    ['<a href="%2e%2e/b">t</a>', BASE],                              # new URL 会折叠 %2e%2e
    ['<a href="b/c;p=1?q=2#f">t</a>', BASE],                         # ;params 留在 path 里
    ['<a href="' + SOH + 'a.png">t</a>', BASE],                      # 前导 C0 被 lstrip 吃掉
    ['<img src="/a.png" srcset="/b.png 2x">', BASE],
    ['<img src="data:,x" src="/b.png" data-src="L.png">', BASE],     # 只改第一个 src
    ['<img src="x&#47;a.png" data-src="L.png">', BASE],
    ['<img图片="1" src="/a.png">', BASE],                     # Python 的 \\b 认汉字为词字符
    ['<img图片="1" data-src="q.jpg">', BASE],
    ['<img 图data-src="q.jpg">', BASE],                       # Python 的 [\\w-]+ 含汉字
    ['<img data-src="L.png"图片-src="q">', BASE],
    ['<a href="图/a.png">t</a>', BASE],                               # 非 ASCII：放宽通道候选
    ['<a href="a' + BS + 'b/../c.png">t</a>', BASE],
    ['<img data-src="https://e.com/x?q=a&amp;b.jpg">', BASE],
    ['<a href="&#47;/evil.com/x">t</a>', BASE],
    ['<a href="/a#frag">t</a>', BASE],
    ['<a href="sub/./b/../c/">t</a>', BASE],
    # I8 分层：`_normalize_body_html` 自己**不**解转义（Python 侧同样不解，解转义是调用点
    # `_unescape_escaped_body` 那一步）。两边必须一样"看不见标签"。
    ['&lt;img data-src=&quot;https://e.com/a.png&quot;&gt;', BASE],
]

# (正文, limit)。前 26 条 = task-3-golden.json 的 cap 行（同序同输入；`<long N>` 那种摘要行
# 按摘要复现，GOLDEN_OUT 里 len/head/tail 三项都相等才算覆盖）。
CAP_SAMPLES = [
    ("", None),
    ("短正文", None),
    ("\U0001f42a" * 403 + "<p>x</p>", 400),
    ("<p>" + "z" * 49990 + "</p>" + '<img src="https://e.com/x.jpg">', 50000),
    ("<p>" + "y" * 49992 + "</p>&zz", 50000),
    ("<p>" + "y" * 49991 + "</p>&&z", 50000),
    ("<p>" + "y" * 49996 + "<img", 50000),
    ("& &m", 3),
    ("ab  &mz", 6),
    ("A&B &am ", 7),
    ("AT&T &am", 8),
    ("a&&b&am", 7),
    ("价格" + NBSP + "&nbspz", 7),
    ("x&  &ab", 7),
    ("&#" + NBSP + "nbsp", 6),
    ("A&" + NBSP + "nbsp", 7),
    ("Tom&Jerryzz", 7),
    ("x&#12&am", 8),
    ("x&#xab&am", 9),
    ("a&#000000000z", 11),
    ("ends with <span", 50),
    ("Tom&Jerry", 50),
    ("trailing   ", 50),
    ("y" * 50001, 50000),
    ("y" * 49999 + "&", 50000),
    ("<p>x</p>" + "y" * 49998, 50000),
    # ---- 扩面：空白码位（FS/NEL/BOM/ZWSP/NBSP）、无界数字与十六进制实体、名段不级联、
    # 恰好等于上限、代理对、退化连排、扫描器三条分支各自到位。
    ("ab&am" + FS, 5),
    ("ab&am" + FS, 6),
    ("ab&am" + BOM + "q", 6),
    ("ab&am" + ZWSP + "q", 6),
    ("ab&am" + NEL, 5),
    ("ab&am" + NEL + "x", 6),
    ("a&#123456789012z", 15),
    ("a&#x00000000fq", 13),
    ("x&xab&am", 8),
    ("a&#x12z", 6),
    ("x&#" + ARABIC_3 + "z", 4),
    ("<p>" + "z" * 60 + '</p><img src="a"', 70),
    ("<p>" + "z" * 60 + "</p>&am", 69),
    ("<p>" + "z" * 60 + "</p>&am", 68),
    ("<div>" + "多" * 200, 205),
    ("&" * 50001, 50000),
    ("<p>aaa</p><im", 9),
    ("\U0001f42a" * 399 + "<p>x</p>", 400),
    ("zzzz&mz" + NBSP, 8),
    ("zz&nbsp" + FS + "x", 6),
    ("&#xABCDEF0123456789z", 19),
    ("a&&&&&b", 6),
    ("x&#;&#x0;zz", 11),
    ("<b>&#38;&#x26;&nbsp&nbsp", 18),
    ("r&#x1&#x2&#x3", 13),
    ("R&Dnbspz", 7),
    ("x&#8;zz", 6),
    ("&#38&#x26&#x", 14),
    ('<img src="https://e.com/a.jpg" alt="x">', 21),
    ("a&nbsp" + NBSP + "b", 6),
    ("&#x00000000000000000001z", 23),
    ("a&#x;" + ARABIC_3 + "z", 6),
    ("尾部&nbsp" + NEL + "x", 7),
    ("<span>x&#1", 9),
    ("&#1&#2&#3x", 9),
    ("abc", 0),                      # `limit || CAP` 那种写法在这里就分叉（0 被当成"没给上限"）
]

# `_is_placeholder_src` 的判定语料（对账只比 True/False）。含能区分
# 「词干精确相等」与「子串 includes()」两口径的样本，以及 1x1/0x0 成对形态。
PLACEHOLDER_SAMPLES = [
    "", "data:x", "DATA:image/gif;base64,x", "blank", "blank.png", "blank2.gif", "a.blank",
    "https://e.com/blank.gif", "lazy", "lazy_cat_pic.png", "placeholder.png", "spacer.png",
    "spacer_1x1.png", "1x1.png", "0x0.jpeg?v=2", "0x0", "1x1", "0X0.png", "1X1",
    "/0x0/", "https://e.com/f/1024p0/0x0/100/New_Project_76__0.jpg",
    "https://mmbiz.qpic.cn/mmbiz_jpg/abc1x1def/960.jpg", "lazy/640x",
    "PLACEHOLDER.png", "x1x1", "1x0", "1x1 ", " 1x1", "0x0.0", "_1x1_", "-0x0-",
    "https://img.example/x?name=blank.png", "https://img.example/blank.png#lazy",
    "https://s.example/a.jpg?w=1x1", "not-a-url-with-no-slash-blank", "0x0#blank",
    "http://", "https://e.com/", "https://e.com/lazy/", "1x1.png?v=1x1",
]

# 懒加载优先级语料：同一标签里放多个镜像属性，取值顺序只许按 LAZY_SRC_ATTRS 的元组序。
LAZY_PRIORITY_SAMPLES = [
    '<img data-original="o.png" data-src="s.png">',
    '<img data-lazy-src="l.png" data-original="o.png">',
    '<img data-croporisrc="c.png" data-lazy-src="l.png">',
    '<img data-src="" data-original="o.png">',
    '<img data-src="  " data-croporisrc="c.png">',
    '<img data-src="s.png" data-original="o.png" data-lazy-src="l.png" data-croporisrc="c.png">',
]

# 绝对化 fuzz 字母表。含 `"`/`'`/`<`/`>`/反斜杠/`;`/`%`/`:`/制表/前导控制字符，
# 也含一个非 ASCII 字符（é）专门走"放宽通道"那一条比较分支。
FUZZ_CHARS = list("ab.-/;:[]%?#&=_'<>~!$@()+,*019é") + [BS, TAB, " ", SOH]
FUZZ_BASES = [BASE, DIRBASE, "https://blog.example/dir/", "https://h", "https://h/",
              "http://example.com/a/b?q=1#z", "https://h/x;p=1"]
FUZZ_CASES = 700

# ---------------------------------------------------------------- 金标准快照
# task-3-golden.json（2026-10-04 由当时的 Python 实现现算，49 条）的 out 侧逐字快照。
# 这条判据同时钉两侧：JS 不许分叉，Python 侧若要改契约也必须显式改这张表并说明理由。
GOLDEN_NORM = 23
GOLDEN_OUT = [
    '<p>x</p><img src="https://mmbiz.qpic.cn/a.jpg" data-src="https://mmbiz.qpic.cn/a.jpg">',
    '<img src="https://mmbiz.qpic.cn/b.jpg" data-src="https://mmbiz.qpic.cn/b.jpg">',
    '<img src="https://cdn.example/real.png" data-src="https://cdn.example/o.png">',
    '<img src="https://mp.weixin.qq.com/i/a.png" data-src="/i/lazy.png">',
    '<img src="https://mp.weixin.qq.com/s/B.png" data-original="A.png" data-src="B.png">',
    '<img src="https://mp.weixin.qq.com/s/D.png" data-croporisrc="C.png" data-lazy-src="D.png">',
    '<img src="https://mp.weixin.qq.com/x/lazy_cat_pic.png" data-src="/y/640.jpg">',
    ('<img src="https://mmbiz.qpic.cn/mmbiz_jpg/abc1x1def/960.jpg" '
     'data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc1x1def/640.jpg">'),
    '<img src="https://e.com/real.jpg" data-src="https://e.com/real.jpg">',
    '<img src="https://e.com/blank2.gif" data-src="https://e.com/real.jpg">',
    '<img src="https://e.com/a.blank" data-src="https://e.com/real.jpg">',
    '<img src="https://e.com/lazy/640x" data-src="https://e.com/real.jpg">',
    '<img src="//cdn.example/c.png"><a href="#sec">s</a>',
    '<a href="https://blog.example/b?q=1">t</a>',
    '<a href="HTTPS://EX.COM/A">t</a>',
    '<img src="https://mp.weixin.qq.com/s/&#47;i/a.png">',
    '<img data-src="https://a&b.jpg" src="https://a&b.jpg">',
    '<img src="https://a\x01b.jpg" data-src="https://a\x01b.jpg">',
    "<p title='q'>x</p><img data-src='r.jpg'>",
    '<img data-src="https://e.com/a>b.jpg" alt="x">',
    '<img src="/i/a.png">',
    '',
    '<p>正常正文，无图</p>',
    '',
    '短正文',
    {'len': 400, 'head': '🐪' * 24, 'tail': '🐪' * 24},
    {'len': 49997, 'head': '<p>' + 'z' * 21, 'tail': 'z' * 20 + '</p>'},
    {'len': 49999, 'head': '<p>' + 'y' * 21, 'tail': 'y' * 20 + '</p>'},
    {'len': 49998, 'head': '<p>' + 'y' * 21, 'tail': 'y' * 20 + '</p>'},
    {'len': 49999, 'head': '<p>' + 'y' * 21, 'tail': 'y' * 24},
    '', 'ab', 'A&B', 'AT&T &am', 'a&&b&am', '价格', 'x&  &ab', '&#\xa0nbs', 'A&\xa0nbsp',
    'Tom', 'x&#12&am', 'x&#xab&am', 'a', 'ends with <span', 'Tom&Jerry', 'trailing   ',
    {'len': 50000, 'head': 'y' * 24, 'tail': 'y' * 24},
    {'len': 50000, 'head': 'y' * 24, 'tail': 'y' * 23 + '&'},
    {'len': 50000, 'head': '<p>x</p>' + 'y' * 16, 'tail': 'y' * 24},
]


# ---------------------------------------------------------------- 工具
def _node():
    n = shutil.which("node")
    if not n:
        pytest.skip("本机没有 node，跑不了运行时规范层")
    return n


# 一次 node 进程跑一批：spec = {kind, fn|name, items}，结果写回文件再读。
# 路径全部走 argv + 文件中转，不把样本拼进 JS 源码 —— 一是 Windows 引号地狱，
# 二是"样本里带个引号就能改写被测脚本"本身就是注入面（与 Task 1 的 C1 同类）。
_PROBE = 'const fs=require("fs");\n' \
         'const R=require(process.argv[2]);\n' \
         'const spec=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));\n' \
         'let out;\n' \
         'if (spec.kind==="call") out=spec.items.map((a)=>R[spec.fn].apply(null,a));\n' \
         'else if (spec.kind==="exports") out=R[spec.name];\n' \
         'else throw new Error("unknown spec kind "+spec.kind);\n' \
         'fs.writeFileSync(process.argv[4],JSON.stringify(out));\n'

# 单独一个探针跑 `new URL()`：表达式写死在模板里，样本走 argv。
_PROBE_NEWURL = 'const fs=require("fs");\n' \
                'const items=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));\n' \
                'const out=items.map((p)=>{try{return new URL(p[1],p[0]).href}catch(e){return null}});\n' \
                'fs.writeFileSync(process.argv[3],JSON.stringify(out));\n'


def _run_js(tmp_path, src, args):
    probe = tmp_path / "_probe.js"
    probe.write_text(src, encoding="utf-8")
    r = subprocess.run([_node(), str(probe)] + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    assert r.returncode == 0, "node 侧规范层跑崩：\n%s\n%s" % ((r.stdout or "")[-400:],
                                                              (r.stderr or "")[-1200:])
    return r


def _js(tmp_path, spec):
    spec_p = tmp_path / "_spec.json"
    out_p = tmp_path / "_out.json"
    spec_p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    _run_js(tmp_path, _PROBE, [LIB.replace("\\", "/"), spec_p, out_p])
    return json.loads(out_p.read_text(encoding="utf-8"))


def _js_newurl(tmp_path, pairs):
    spec_p = tmp_path / "_nu_spec.json"
    out_p = tmp_path / "_nu_out.json"
    spec_p.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8")
    _run_js(tmp_path, _PROBE_NEWURL, [spec_p, out_p])
    return json.loads(out_p.read_text(encoding="utf-8"))


def _is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False


def _short(s):
    """金标准摘要口径：短的原样，长的取 len/head/tail。"""
    return s if len(s) <= 24 else {"len": len(s), "head": s[:24], "tail": s[-24:]}


# 放宽通道记录：跑一轮对账后由测试自己读，用来证明"今天一条都没用上"。
_RELAX = []


def _compare_norm(py, js, where):
    """账本 R20/R26 的口径：ASCII 比字节相等；含非 ASCII 才允许 `unquote(js) == py`。"""
    if py == js:
        return
    if not _is_ascii(py) and unquote(js) == py:
        _RELAX.append(where)
        return
    raise AssertionError("%s 分叉：\n  py: %r\n js: %r" % (where, py, js))


# ---------------------------------------------------------------- 判据
def test_normalize_body_html_matches_python(tmp_path):
    got = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml", "items": NORM_SAMPLES})
    assert len(got) == len(NORM_SAMPLES), "JS 返回条数与样本不等，判据没逐条对齐"
    del _RELAX[:]
    for i, ((h, b), g) in enumerate(zip(NORM_SAMPLES, got)):
        w = mod._normalize_body_html(h, b)
        _compare_norm(w, g, "normalize #%d 输入 %r base %r" % (i, h, b))
    # 出厂实现是手写 join（保留原始字节），所以放宽通道用量必须是 0；
    # 一旦这里 >0，说明有人把 join 换成了会百分号编码的写法，只是恰好被非 ASCII 样本掩住。
    assert _RELAX == [], "放宽通道竟被用到 %d 条：出厂值不得来自百分号编码 %s" % (len(_RELAX), _RELAX[:4])


def test_cap_body_matches_python(tmp_path):
    items = [[t, lim] for t, lim in CAP_SAMPLES]
    got = _js(tmp_path, {"kind": "call", "fn": "capBody", "items": items})
    assert len(got) == len(CAP_SAMPLES), "JS 返回条数与样本不等"
    for i, ((t, lim), g) in enumerate(zip(CAP_SAMPLES, got)):
        w = mod._cap_body(t, lim) if lim is not None else mod._cap_body(t)
        assert w == g, ("截断分叉 #%d（limit=%r 输入长度=%d 尾部 %r）\n  py: %r\n js: %r"
                        % (i, lim, len(t), _short(t[-24:]), _short(w), _short(g)))


def test_golden_snapshot_is_covered_by_this_corpus(tmp_path):
    """49 条金标准必须由这份语料的前 49 条逐字复现（两侧都钉）。

    金标准是"当时的 Python 现算值"，所以这条同时在钉 Python：Task 1 的契约若要改，
    必须显式改这张表并说明理由，不许悄悄把参照物挪走再让 JS 跟着挪。
    """
    assert len(GOLDEN_OUT) == 49, len(GOLDEN_OUT)
    n_cap = 49 - GOLDEN_NORM
    assert len(NORM_SAMPLES) >= GOLDEN_NORM and len(CAP_SAMPLES) >= n_cap
    want_norm = GOLDEN_OUT[:GOLDEN_NORM]
    want_cap = GOLDEN_OUT[GOLDEN_NORM:]
    js_norm = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml",
                             "items": NORM_SAMPLES[:GOLDEN_NORM]})
    for i, want in enumerate(want_norm):
        py = mod._normalize_body_html(*NORM_SAMPLES[i])
        assert py == want, "金标准 normalize #%d 在 Python 侧不再成立：%r ≠ %r" % (i, _short(py), want)
        _compare_norm(want, js_norm[i], "金标准 normalize #%d（JS 侧）" % i)
    js_cap = _js(tmp_path, {"kind": "call", "fn": "capBody",
                            "items": [[t, l] for t, l in CAP_SAMPLES[:n_cap]]})
    for j, want in enumerate(want_cap):
        t, lim = CAP_SAMPLES[j]
        py = mod._cap_body(t, lim) if lim is not None else mod._cap_body(t)
        assert _short(py) == want, "金标准 cap #%d 在 Python 侧不再成立：%r ≠ %r" % (
            GOLDEN_NORM + j, _short(py), want)
        assert _short(js_cap[j]) == want, "金标准 cap #%d 在 JS 侧不等：%r ≠ %r" % (
            GOLDEN_NORM + j, _short(js_cap[j]), want)


def test_lazy_attr_lists_are_the_same_ordered_list(tmp_path):
    """元组顺序**就是**优先级（账本 R22：这条现在是判据，不是注释）。"""
    got = tuple(_js(tmp_path, {"kind": "exports", "name": "LAZY_SRC_ATTRS"}))
    assert got == mod._LAZY_SRC_ATTRS, \
        "懒加载属性优先级被单边改了：py=%r js=%r" % (mod._LAZY_SRC_ATTRS, got)
    items = [[tag, BASE] for tag in LAZY_PRIORITY_SAMPLES]
    js = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml", "items": items})
    for tag, g in zip(LAZY_PRIORITY_SAMPLES, js):
        w = mod._normalize_body_html(tag, BASE)
        _compare_norm(w, g, "懒加载优先级 %r" % tag)
        m = re.search(r'(?<![\w-])src="([^"]*)"', g)
        assert m, "镜像提升没落地：%r" % g


def test_cap_default_limit_is_shared(tmp_path):
    got = _js(tmp_path, {"kind": "exports", "name": "BODY_CAP"})
    assert got == mod._BODY_CAP, "两边默认截断上限不一致：%r vs %r" % (mod._BODY_CAP, got)


def test_entity_window_and_placeholder_name_table_are_shared(tmp_path):
    """窗口 = 1 + 名段量词上界；词干表逐个同值。改一边必须改另一边（账本 R23 的 V15 靶）。"""
    assert _js(tmp_path, {"kind": "exports", "name": "ENTITY_TAIL_WINDOW"}) == mod._ENTITY_TAIL_WINDOW
    names = tuple(_js(tmp_path, {"kind": "exports", "name": "PLACEHOLDER_SRC_NAMES"}))
    assert names == mod._PLACEHOLDER_SRC_NAMES, "占位词干表分叉：py=%r js=%r" % (
        mod._PLACEHOLDER_SRC_NAMES, names)


def test_placeholder_src_behavior_matches_python(tmp_path):
    """词干**精确相等**、先剥 ?query/#fragment、1x1 与 0x0 都要有（账本 R22 四陷阱）。

    两侧各写一套 `includes()`/子串口径都能在自己的单测里绿，只有同批样本逐条对才看得见。
    """
    js = _js(tmp_path, {"kind": "call", "fn": "isPlaceholderSrc",
                        "items": [[v] for v in PLACEHOLDER_SAMPLES]})
    assert len(js) == len(PLACEHOLDER_SAMPLES)
    for v, g in zip(PLACEHOLDER_SAMPLES, js):
        w = mod._is_placeholder_src(v)
        assert isinstance(w, bool) and isinstance(g, bool), "占位判定必须返回布尔：%r -> %r/%r" % (v, w, g)
        assert w == g, "占位 src 判定分叉 %r：py=%r js=%r" % (v, w, g)
    # 反空转：这批语料里必须真有"两口径会给不同答案"的形态，否则整条判据只是走过场。
    assert any(mod._is_placeholder_src(v) is False for v in PLACEHOLDER_SAMPLES)
    assert any(mod._is_placeholder_src(v) is True for v in PLACEHOLDER_SAMPLES)
    assert "lazy_cat_pic.png" in PLACEHOLDER_SAMPLES and "0x0.jpeg?v=2" in PLACEHOLDER_SAMPLES
    assert "/0x0/" in PLACEHOLDER_SAMPLES and "blank2.gif" in PLACEHOLDER_SAMPLES
    assert "a.blank" in PLACEHOLDER_SAMPLES


def test_js_whitespace_table_equals_python_isspace(tmp_path):
    r"""刀二回溯游标与出口 trim 共用的那张空白表，必须等于 Python `str.isspace()`（账本 R24）。

    JS 的 `\s`/`trimEnd()` 与 Python 差 6 个码位（少 `1C-1F` 与 `85`、多 `FEFF`），
    所以这里比的是**码位表本身**，不是某条样例 —— 样例只能证明"这批没炸"。
    """
    js = set(_js(tmp_path, {"kind": "exports", "name": "WHITESPACE_CODE_POINTS"}))
    py = [cp for cp in range(0x0, 0x3400) if chr(cp).isspace()]
    assert sorted(js) == py, "空白码位表分叉：只在 js=%s 只在 py=%s" % (
        [hex(c) for c in sorted(js - set(py))], [hex(c) for c in sorted(set(py) - js)])
    assert 0xFEFF not in js, "U+FEFF 不许进空白表（JS \\s 认它、Python 不认）"
    for cp in (0x1C, 0x1D, 0x1E, 0x1F, 0x85):
        assert cp in js, "U+%04X 是 Python 空白，JS 表里必须有" % cp


def test_js_word_class_covers_python_word_chars(tmp_path):
    r"""Python 的 `\w` 是 Unicode 口径，JS 侧必须覆盖它（汉字算词字符 ⇒ `\b`/`(?<![\w-])` 同判）。

    方向性判据：只要求 `⊇`。JS 的 `\p{L}`/`\p{N}` 比 Python 3.11 的 UnicodeDB 多 161 个码位
    （Unicode 15/16 新分配的字母与数字），方向是"JS 少剥/少改"，登记为可接受余量。
    窄回去（比如退回 ASCII `\w`）一定红 —— 那会让 `<img图片=…>`、`图data-src="…"` 两类
    输入在运行时被当成真标签/真懒加载属性，凭空改写出厂 HTML。
    """
    cps = list(range(0x0, 0x3000)) + [0x4e00, 0x4e2d, 0x1f600, 0x200b, 0x301, 0xb2, 0xbc, 0x16ee]
    js = _js(tmp_path, {"kind": "call", "fn": "isWordChar", "items": [[cp] for cp in cps]})
    missing = [hex(cp) for cp, g in zip(cps, js) if not g and re.match(r"\w", chr(cp))]
    assert not missing, "JS 词字符类漏掉 Python 认的码位：%s" % missing[:20]
    extra = [hex(cp) for cp, g in zip(cps, js) if g and not re.match(r"\w", chr(cp))]
    assert len(extra) < 40, "JS 词字符类比 Python 宽出异常多（%d 个）：%s" % (len(extra), extra[:20])


def test_backslash_and_dollar_samples_survive_verbatim(tmp_path):
    """C1 回归门：不可信属性值里的 `\u0026`/`\1`/`$&` 不许炸、不许被展开（两侧同一构造）。

    Python 侧坏在 `re.sub` 的 replacement 模板，JS 侧坏在 `String.replace` 的 `$` 模式 ——
    两个引擎的"模板注入"形状不同，所以必须各拿同一批 token 打一遍。
    """
    toks = [BS + "u0026", BS + "1", BS + BS, BS + "0", "$&", "$1", "$`", "$'", "$$", "&amp;"]
    items = []
    for tk in toks:
        items.append(['<img data-src="https://e.com/a%sb.jpg">' % tk, BASE])
        items.append(['<img src="data:," data-src="https://e.com/a%sb.jpg">' % tk, BASE])
        items.append(['<a href="/x%sy.png">t</a>' % tk, BASE])
    js = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml", "items": items})
    for (h, b), g in zip(items, js):
        w = mod._normalize_body_html(h, b)
        assert w == g, "模板注入类样本分叉 %r\n  py: %r\n js: %r" % (h, w, g)
        for tk in toks:
            if tk in h:
                assert tk in g or not _is_ascii(h), "%r 里的 %r 被改写：js=%r" % (h, tk, g)


def test_absolutization_relaxation_is_explained_not_hidden(tmp_path):
    r"""这条解释"非 ASCII 比 unquote"为什么存在 —— 不许靠改 Python 侧消灭它（账本 R20/R26）。

    三段都要成立：
      ① `new URL()` 与 `urljoin` 在**同一批**样本上不等价，而且**ASCII 样本上也差**
         （空格→`%20`、`%2e%2e` 被当点段折叠）⇒ 所以"ASCII 比字节"这半是真承重的，
         放宽只给非 ASCII，不是遮羞布；
      ② 出厂实现（手写 join）在这些样本上与 Python **逐字节相等** ⇒ 放宽通道今天用量为 0；
      ③ 放宽方向唯一：`unquote(js) == py` 成立，反向 `js == quote(py)` 不成立
         —— 想靠"把 Python 侧改成 quote 一下"对齐，等于把 ① 里那些真实差值放大成出厂变形。
    """
    differ = [(BASE, "/图/a.png"), (BASE, "图/a b.png"), (DIRBASE, "…/x.png"),
              (BASE, "/i/a b.png"), (BASE, "%2e%2e/b")]
    nu = _js_newurl(tmp_path, differ)
    for (b, v), g in zip(differ, nu):
        assert g != urllib.parse.urljoin(b, v), \
            "样本 %r 上 new URL 与 urljoin 竟然字节相等 ⇒ 这条判据在空跑" % v
    # 反例登记：制表/回车/换行这一类**两边都吃**，所以它抓不到 `new URL` ——
    # 真正抓住它的是"空格 / `%2e` 点段折叠 / 非 ASCII"这三类，上面必须各有一条。
    tab_v = "a" + TAB + "b.png"
    assert _js_newurl(tmp_path, [(BASE, tab_v)])[0] == urllib.parse.urljoin(BASE, tab_v)
    assert any(_is_ascii(v) for _b, v in differ), "ASCII 那一半必须有承重样本"
    pairs = differ + [(BASE, tab_v)]
    # ② 出厂实现逐字节相等（与 test_normalize 同一入口，这里只针对这批绝对化样本）
    items = [['<a href="%s">t</a>' % v, b] for b, v in pairs]
    js = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml", "items": items})
    for (h, b), g in zip(items, js):
        assert g == mod._normalize_body_html(h, b), "出厂实现必须字节相等：%r" % h
    # ③ 放宽的方向唯一：`unquote(js) == py` 成立，反向 `js == quote(py)` 不成立
    assert unquote("https://e.com/%E5%9B%BE/a.png") == "https://e.com/图/a.png"
    assert urllib.parse.quote("https://e.com/图/a.png") != "https://e.com/%E5%9B%BE/a.png"
    # 而"把 Python 侧改成 quote 一下"并不等于放宽的另一半：它把 ① 里那些真实差值
    # 放大成出厂变形（浏览器请求层两种形式是同一个资源，出厂字段却从此不一样）。
    assert urllib.parse.quote(urllib.parse.urljoin(BASE, "/图/a.png"), safe="") != \
        mod._normalize_body_html('<a href="/图/a.png">', BASE)[len('<a href="'):-2]


def test_urljoin_fuzz_matches_python(tmp_path):
    """把绝对化这一步单独 fuzz（700 条）：ASCII 比字节，非 ASCII 才允许放宽。

    手写 join 的承重墙在这儿：`.`/`..`/`;params`/`?`/`#`/前导控制字符/制表/反斜杠
    每一条分支都有随机组合覆盖到，比手写 60 条样例强得多。
    """
    rnd = random.Random(20261004)
    cases = []
    for _ in range(FUZZ_CASES):
        v = "".join(rnd.choice(FUZZ_CHARS) for _ in range(rnd.randint(1, 14)))
        cases.append((rnd.choice(FUZZ_BASES), v))
    items = [['<a href="%s">t</a>' % v, b] for b, v in cases]
    js = _js(tmp_path, {"kind": "call", "fn": "normalizeBodyHtml", "items": items})
    bad = []
    relaxed = []
    for (h, b), g in zip(items, js):
        w = mod._normalize_body_html(h, b)
        if w == g:
            continue
        if not _is_ascii(w) and unquote(g) == w:
            relaxed.append(h)
            continue
        bad.append((h, b, w, g))
    assert not bad, "绝对化 fuzz 分叉 %d 条，前 6 条：\n%s" % (
        len(bad), "\n".join("  in=%r base=%r\n    py=%r\n   js=%r" % x for x in bad[:6]))
    assert relaxed == [], "fuzz 里出厂实现也要放宽（%d 条）：%s" % (len(relaxed), relaxed[:4])


def test_cap_tail_invariants(tmp_path):
    """两条不变量（账本 R25 的 ①a/①b）跑在 CAP_SAMPLES + 500 条随机截断上，两侧同判。

      · 未截断者（码点数 ≤ limit）必须逐字节原样返回，一律不许动尾部；
      · ①a 截断过的出口绝不挂 `&$` / `&#数字$` / `&#x十六进制$` 这三条尾巴；
      · ①b 名段那一刀级联有界：差分里的实体名段至多 1 段（>1 就是在吃合法文字）。
    """
    unambig = re.compile(r"&(?:#[0-9]*|#x[0-9a-fA-F]*)?$")
    # 名段那一刀"一生只许一次"：数被剥掉的尾部里有几个**独立**的 `&名字` 起点
    # （前置必须是空白/串首，`&&&` 连排属于无歧义形态，不计名段）。NEW-1 的回归形状
    # 是 `A&B &am `→`A`，尾部差分里就会出现两个独立名段起点。
    name_seg = re.compile(r"(?<![0-9A-Za-z#])&(?!#)[0-9A-Za-z]")
    rnd = random.Random(4242)
    alphabet = list("ab&;#xX09 \n") + ["🐪", "中", "<", ">", "/", FS, NBSP]
    texts = [t for t, _ in CAP_SAMPLES] + [
        "".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 40))) for _ in range(500)]
    for lim in (7, 12):
        js = _js(tmp_path, {"kind": "call", "fn": "capBody", "items": [[t, lim] for t in texts]})
        n_untrunc = 0
        for t, g in zip(texts, js):
            w = mod._cap_body(t, lim)
            assert w == g, "cap(…, %d) 分叉 %r：py=%r js=%r" % (lim, t, w, g)
            if len(t) <= lim:
                n_untrunc += 1
                assert w == t and g == t, "未截断者必须逐字原样：%r -> %r" % (t, w)
                continue
            assert not unambig.search(w), "①a 违约：出口挂无歧义尾巴 %r -> %r" % (t, w)
            # ①b 只数**实体刀**吃掉的那一段。刀一吃的是残缺标签（`<b<#` 这种里面本来
            # 就可以有多个 `&名字`），把它算进来就是判据自己造出来的假阳性。
            window = t[:lim]
            m_tag = mod._DANGLING_TAG_RE.search(window)
            head = window if m_tag is None else window[:m_tag.start()]
            removed = head[len(w):]
            assert len(name_seg.findall(removed)) <= 1, "①b 违约：名段级联吃了合法文字 %r -> %r" % (t, w)
        assert n_untrunc > 100, "这批随机截断里没覆盖到「未截断」那一支 ⇒ 第 1 条不变量在空跑"


def test_cap_body_is_linear_on_degenerate_inputs(tmp_path):
    """退化输入的耗时闸（账本 M1/R21）：`&` 连排、`<` 连排都不许退化成二次方。"""
    cases = ["&" * 50001, "<" * 50001, "a&#" + "0" * 49998, "y&nbsp" * 8400,
             "y&nbsp" + FS * 49996 + "&m"]
    t0 = time.time()
    js = _js(tmp_path, {"kind": "call", "fn": "capBody", "items": [[t, 50000] for t in cases]})
    js_dt = time.time() - t0
    t0 = time.time()
    py = [mod._cap_body(t, 50000) for t in cases]
    py_dt = time.time() - t0
    for w, g, t in zip(py, js, cases):
        assert w == g, "退化输入结果分叉（输入 %d 字符）" % len(t)
    assert js_dt < max(15.0, py_dt * 8 + 5), "JS 侧退化输入太慢：%.2fs（Python %.2fs）" % (js_dt, py_dt)


def test_attr_table_is_not_a_bare_object(tmp_path):
    """属性名来自不可信 HTML ⇒ 映射表必须 `Object.create(null)`/`Map`（账本 R22 ③）。"""
    js = _js(tmp_path, {"kind": "call", "fn": "parseImgAttrs", "items": [
        ['<img __proto__="p" toString="t" data-src="y.png">'],
        ['<img>'],
    ]})
    assert js[1] in ({}, [], None), "空标签应无属性：%r" % js[1]
    got = js[0]
    assert isinstance(got, dict)
    assert got.get("__proto__") == "p", "`__proto__` 被当原型吞掉了 ⇒ 表是裸对象：%r" % got
    # 键两侧都按小写存（Python 侧 `name.lower()`），所以查的是 `tostring`
    assert "tostring" in got, "属性名映射被原型链污染：%r" % got
    assert got.get("data-src") == "y.png", "真属性没进表：%r" % got


def test_feature_tables_are_not_empty(tmp_path):
    """空表 = 判定永不命中 = 接口"看起来有挑战页检测"而实际全放过。这就是假绿。"""
    for name in ("CHALLENGE_MARKERS", "PAYWALL_MARKERS"):
        table = _js(tmp_path, {"kind": "exports", "name": name})
        assert isinstance(table, list) and table, "%s 为空，判定形同虚设" % name
        upper = [t for t in table if t != t.lower()]
        assert not upper, "%s 里有大写项（比对的是 lower() 后的原文，写错就永不命中）：%s" % (name, upper)


def test_js_lib_has_zero_requires_and_no_new_url(tmp_path):
    r"""进闸的 JS 必须零依赖，且不许用 `new URL()`/`\s`/`trimEnd()` 产出出厂值。

    CI 没有 `npm ci`、runner 上没有 `node_modules` ⇒ 一个 `require('jsdom')` 就让整条
    判据在闸里当场崩，等于没有判据。`new URL()`/`\s`/`trimEnd()` 三条是 R26/R24 的字面
    防线，行为判据（test_absolutization_* / test_js_whitespace_table_*）之外的第二道。
    只扫非注释行，免得"注释里提了一句"就红。
    """
    src = open(LIB, encoding="utf-8").read()
    assert "require(" not in src, "lib/body_rules.js 里出现 require ⇒ 判据在 CI 上会直接崩"
    for banned in ("jsdom", "cheerio", "axios", "node-fetch"):
        assert banned not in src, "%s 出现在零依赖文件里" % banned
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith(("*", "//", "/*")))
    assert "new URL(" not in code, "出厂值用了 new URL()：它会百分号编码，与 urljoin 不等价"
    for banned in ("trimEnd(", "trimRight(", "trimStart(", "trimLeft(", ".trim()"):
        assert banned not in code, "%s 的空白集与 Python 不同（账本 R24）" % banned
    assert r"\s" not in code, "JS 的 \\s 与 Python isspace 差 6 个码位，必须用显式表"


def test_js_self_test_suite_passes():
    """node 用例集（tests/rss_js/test_body_rules.js）必须有个 pytest 入口来跑它。

    没有这一条，那几十条 JS 用例在 CI 里就是"写着但从不跑"——`tests/rss_js/` 里全是
    `.js`，pytest 根本不收集，`test_gate_wiring.py` 的 UNWIRED 判据也只看含 `test_*.py`
    的目录。同形状先例：tests/rss_cover/test_realtime_cover_js.py:82 用退出码承接
    tests/rss_js/test_realtime_cover.js。变异电池的 M9（挑战页判定退化成只看长度）
    就是靠这条变红的。
    """
    r = subprocess.run([_node(), JS_TEST], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300, cwd=ROOT)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, "node 用例集变红（rc=%d）：\n%s" % (r.returncode, out[-3000:])
    assert "ALL PASS" in out, "node 用例集没报 ALL PASS（退出码 0 但结论没打印）：\n%s" % out[-800:]
    assert out.count("\nok ") >= 45, "node 用例集疑似空跑（ok 行 <45）：\n%s" % out[-1500:]


# ================================================================ R43：三把刀的逐条对账
# 这三把刀（`_rewrite_hn_summary` / `_strip_glued_url` / `_delink_nav_links`）原本只接在
# 构建期；实时通道 `api/rss.js` 的 `?source=`/`?batch=` 自己抓 RSS，没有它们 ⇒ 线上走实时
# 出口的用户仍会看到 HN 那四行模板与 NodeSeek 粘连 URL。R43 补了 JS 端口并接上出口，
# 这一节就是"两份实现必须给逐字相同答案"的那笔账（口径与上面完全一致：
# ASCII 样本比字节相等；含非 ASCII 才允许 `unquote(js) == py`；数字一律 ASCII `[0-9]`；
# 空白一律显式码位表 —— 语料里专门放了 1C-1F / 85 / A0 / FEFF 四种"两侧会分叉"的空白）。
FULL = chr(0xFF1A)          # 全角冒号 ：
FW_2 = chr(0xFF12)          # 全角数字２（钉 ASCII [0-9] 口径：两侧都**不许**当模板行）
KANA = chr(0x3042)           # あ（假名也算"紧跟正文"）

HN_SAMPLES = [
    # ── 中英变体（两边都会真的执行到的形态）──
    ("Article URL: https://ex.com/a\nComments URL: https://news.ycombinator.com/item?id=1\n"
     "Points: 254\n# Comments: 162", "https://ex.com/a"),
    ("文章网址" + FULL + "https://ex.com/a\n评论网址" + FULL +
     "https://news.ycombinator.com/item?id=2\n积分" + FULL + "3\n# 评论数" + FULL + "0", ""),
    ("文章网址: https://ex.com/a\n评论网址: https://ex.com/b\n积分: 7\n# 评论数: 9", ""),
    # ── 正文 + 模板混排：正文一个字不许动 ──
    ("这是一段正文。\nArticle URL: https://ex.com/a\nPoints: 5\n# Comments: 6", "https://ex.com/a"),
    ("Article URL: https://ex.com/a\nPoints: 5\n\n第二段落\n", ""),
    # ── 四条反例（门槛：至少两行且必须含 Points 或 Comments URL）──
    ("评分说明\nPoints: 254", ""),
    ("reports Points: 254 as the best score, and Comments URL: https://x/1 is not a line", ""),
    ("Comments URL: https://news.ycombinator.com/item?id=3", ""),
    ("# Comments: 12\nPoints: 0", ""),
    # ── ASCII [0-9] 口径：全角数字两侧都**不**当模板行 ──
    ("Article URL: https://ex.com/a\nPoints: " + FW_2 + "54\n# Comments: 162", ""),
    # ── 空白码位表：Python 认 / JS \s 不认的那几个必须同判 ──
    (FS + "Points: 3" + FS + NEL + "\n" + NBSP + "# Comments: 4" + NBSP, ""),
    (BOM + "Points: 3\n" + BOM + "# Comments: 4", ""),
    ("\tPoints: 3\r\n# Comments: 4\r\n", ""),
    ("ARTICLE URL: HTTPS://EX.COM/A\nPOINTS: 12", ""),
    ("文章网址：https://ex.com/a\n积分：2", ""),
    ("评论网址：https://ex.com/b\n# 评论数：4\n积分：9", ""),
    ("Article URL: https://ex.com/a\nComments URL: https://ex.com/b", ""),
    ("", ""),
    (None, ""),
    ("正文里提到 100 分 与 20 评论，但它不是模板行", "https://ex.com/c"),
    # ── R45：真语料清点的中文同族词（`# 评论: 0` 是实测最大缺口，551 行）──
    # 每一行的形状都是从 rss_history.json 里数出来的，不是编的；两侧必须给同一个答案。
    (u"文章网址" + FULL + u"https://ex.com/a\n评论网址" + FULL +
     u"https://news.ycombinator.com/item?id=1\n积分" + FULL + u"2\n# 评论: 0", ""),
    (u"文章链接: https://ex.com/a\n评论区链接: https://ex.com/b\n得分: 3\n# 评论: 4", ""),
    (u"文章URL" + FULL + u"https://ex.com/a\n讨论区链接" + FULL +
     u"https://ex.com/item?id=3\n点赞数" + FULL + u"9\n# 评论" + FULL + u"11", ""),
    (u"文章地址" + FULL + u"https://ex.com/a\n评论页面" + FULL +
     u"https://ex.com/b\n热度值" + FULL + u"7\n评论数量" + FULL + u"3", ""),
    (u"文章网址" + FULL + u"https://ex.com/a\n评论URL" + FULL +
     u"https://ex.com/b\n关注度" + FULL + u"1\n#评论" + FULL + u" 2", ""),
    ("Article URL: https://ex.com/a\nComments URL: https://ex.com/b\n"
     "Points: 12\n# 评论: 30", ""),
    (u"文章网址" + FULL + u"https://ex.com/a\n讨论链接" + FULL +
     u"https://ex.com/b\n当前得分" + FULL + u"4\n分数" + FULL + u"2", ""),
    # 新词 × 显式空白码位表：两条轴必须同时成立（只用 ASCII 词钉空白、
    # 只用标准空白钉词表，都留得出"单边补词把另一条轴带歪"的盲区）。
    (NBSP + u"得分" + FULL + u"3" + NBSP + "\n" + FS + u"# 评论" + FULL + u"4", ""),
    # ── R47：上游翻译层把 `Article URL:` / `Comments URL:` 的**标签整个丢掉** ──
    # 于是那两行 URL 以"正文行"的身份进来：四槽刀照旧开火（积分 + 评论两行就够门槛），
    # 刀却必须在门槛过后把它们剥掉。两侧同判，漏一侧就是"HN 里全是链接"没清干净。
    ("https://ex.com/a\nhttps://news.ycombinator.com/item?id=1\n" +
     u"积分" + FULL + u"2\n# 评论: 0", "https://ex.com/a"),
    (u"正文一句。\nhttps://ex.com/a\nhttps://ex.com/b\nPoints: 5\n# Comments: 6",
     u"https://ex.com/a"),
    (u"正文一段。\n\nhttps://ex.com/last\n" + u"积分" + FULL + u"4\n# 评论: 2", ""),
    ("HTTPS://EX.COM/A\n" + u"积分" + FULL + u"1\n" + u"评论" + FULL + u"2", ""),
    (u"正文 https://ex.com/inline 在句中\n" + u"积分" + FULL + u"9\n# 评论: 1", ""),
    # 整行是 **URL+正文粘连**（不是"整行裸 URL"）⇒ 这把刀不许动它，剥它是 `_strip_glued_url`
    # 的活。值段写成 `\\S`/反向空白表而不是 ASCII 可打印类时这一行会被整行吃掉，两侧同判才看得见。
    (u"积分" + FULL + u"5\n# 评论: 3\nhttps://ex.com/a" + u"看了大佬的文章", ""),
    ("Points: 5\n# Comments: 3\nhttps://ex.com/a" + u"看了大佬的文章马上干", "https://ex.com/a"),
    # ── R47 反例（**派工点名不许放宽成通用规则**）：门槛没过 ⇒ 一行裸 URL 原样保留。
    # 很多源的正常摘要就是单独一行链接，把它做成"通用剥 URL 行"就是在吃正文。
    ("https://ex.com/only", "https://ex.com/only"),
    (u"本周更新\nhttps://ex.com/changelog", ""),
    ("See also\nhttps://a.test/x\nhttps://b.test/y", ""),
    # ── R45 反例：正文里的中文句子，一条不许吃（门槛与整行锚定都要顶住）──
    (u"评论数" + FULL + u"10 条，值得讨论\n这篇文章的得分" + FULL + u"9.5 分\n评论", ""),
    (u"文章网址" + FULL + u"https://ex.com/a\n评论数" + FULL + u"0", ""),
    (u"得分" + FULL + u"2", ""),
    (u"评论\n积分说明\n热度：本季度上升 3 倍", ""),
]

GLUED_SAMPLES = [
    # ── 正例（实测形状）──
    ("https://www.nodeseek.com/post-957723-1看了大佬的IX文章必须有行动力，马上干",),
    ("http://www.nodeseek.com/post-1-1看了",),
    ("https://a.test/p/1" + KANA + "見た",),
    (FS + "https://a.test/p/1看了",),                     # 1C：Python 的空白类认
    (NEL + "https://a.test/p/1看了",),                    # 85：同上
    (NBSP + "https://a.test/p/1看了",),                   # A0：同上
    ("https://a.test:8080/p?q=1#z看了大佬",),
    # ── 四条反例（派工点名）：空格分隔 / 整条就是 URL / URL 后换行 / URL 后全角标点 ──
    ("https://a.test/p/1 看了文章",),
    ("https://a.test/p/1",),
    ("https://a.test/p/1\n看了文章",),
    ("https://a.test/p/1，这是正文",),
    ("https://a.test/p/1。",),
    # ── 其余不许动的形状 ──
    ("BOM" + BOM + "https://a.test/p/1看了",),            # FEFF 不是空白 ⇒ 不剥（两侧同判）
    ("句中 https://a.test/p/1看了 不该动",),
    ("HTTPS://A.TEST/P/1看了",),                          # scheme 大小写：两侧都不剥
    ("ftp://a.test/p/1看了",),
    ("https://a.test/p/1" + FW_2, ),                      # 全角数字结尾：不是 URL 字符
    ("",),
    (None,),
    ("https://a.test/xhttps://b.test/y看了",),
]

DELINK_SAMPLES = (
    ["<p>我们用 <a href=\"https://blog.example/tag/kubernetes\">Kubernetes</a> 部署</p>",
     "<a href=\"https://blog.example/tags/x\">t</a>",
     "<a href=\"https://blog.example/category/dev\">dev</a>",
     "<a href=\"https://blog.example/categories/dev\">dev</a>",
     "<a href=\"https://blog.example/author/anna\">anna</a>",
     "<a href=\"https://blog.example/authors/anna\">anna</a>",
     "<a href=\"https://blog.example/about/x\">about</a>",
     "<a href=\"https://blog.example/subscribe/x\">sub</a>",
     "<a href=\"https://blog.example/donate/x\">pay</a>",
     "<a href=\"https://blog.example/archive/x\">arch</a>",
     # 外部正文链接：一条不许动
     "<a href=\"https://openai.com/blog/x\">原始公告</a>",
     "<a href=\"https://about.fb.com/news/2026/01/x\">Meta</a>",
     "<a href=\"https://lists.gnu.org/archive/html/bug-x/2026/msg00001.html\">list</a>",
     "<a href=\"https://code.example/repo/blob/main/docs/author/style.md\">指南</a>",
     # 形状边界
     "<a href=\"tag/x\">相对无斜杠</a>",
     "<a href=\"mailto:me@x.com\">邮件</a>",
     "<a href=\"#sec-2\">见下节</a>",
     "<a href=\"/tag/x\">斜杠开头</a>",
     "<a href=\"https://blog.example//tag/x\">双斜杠</a>",
     "<a href=\"https://blog.example/tag\">只有一段</a>",
     "<a href=\"https://blog.example/tag/x?q=1#frag\">带 query</a>",
     "<a href=\"https://blog.example/TAG/x\">大写段</a>",
     "<A HREF=\"https://blog.example/tag/x\">大写标签</A>",
     "<a href=\"https://blog.example/关于/x\">中文段</a>",
     "<p>看 <a href=\"https://blog.example/tags/kubernetes\"><strong>Kubernetes</strong></a> 吧</p>",
     # 不可信文本：JS 的 replace 模板串炸点（`$&`/`$1`/`` $` ``）与 Python 的反斜杠
     "<a href=\"https://blog.example/tag/x\">$& 与 $1 与 `` $` \"</a>",
     "<a href=\"https://blog.example/tag/x\">" + BS + "1 与 " + BS + "g<href>test</a>",
     "<a href=\"https://blog.example/外/链\">链</a> 后跟 <a href=\"/author/李\">李</a>",
     "<a href=\"https://blog.example/tag/x\">多</a><a href=\"https://ext.example/y\">行</a>",
     "",
     ]
)

# 逐条对账的读数（报告要用：条数与不一致数；不一致一旦 >0 上面的比较就抛了）
_TALLY = {"hn": 0, "glued": 0, "delink": 0, "mismatch": 0}


def _compare_hard(py, js, where):
    """与 `_compare_norm` 同一口径，但**不许**用放宽通道：这三把刀不做任何百分号编码，
    出现 `unquote(js) == py` 就说明有人在 JS 侧偷偷 encode 了。"""
    if py == js:
        return
    if not _is_ascii(py) and unquote(js) == py:
        _RELAX.append(where)
    raise AssertionError("%s 分叉：\n  py: %r\n js: %r" % (where, py, js))


def test_hn_summary_rewrite_matches_python(tmp_path):
    """`_rewrite_hn_summary` vs `rewriteHnSummary`：同批样本逐条比输出。"""
    got = _js(tmp_path, {"kind": "call", "fn": "rewriteHnSummary", "items": HN_SAMPLES})
    assert len(got) == len(HN_SAMPLES), "JS 返回条数与样本不等，判据没逐条对齐"
    # 幂等再过一遍（一次 node 进程跑完整批，别每条起一个进程）
    again = _js(tmp_path, {"kind": "call", "fn": "rewriteHnSummary",
                           "items": [[g, HN_SAMPLES[i][1]] for i, g in enumerate(got)]})
    del _RELAX[:]
    for i, ((d, lk), g) in enumerate(zip(HN_SAMPLES, got)):
        w = mod._rewrite_hn_summary(d, lk)
        if w != g:
            _compare_hard(w, g, "HN #%d 输入 %r" % (i, d))
        assert mod._rewrite_hn_summary(w, lk) == w, "Python 侧不幂等 #%d" % i
        assert again[i] == g, "JS 侧不幂等 #%d：%r 过第二遍变成了 %r" % (i, g, again[i])
    _TALLY["hn"] = len(HN_SAMPLES)
    assert _RELAX == [], "这三把刀不许走放宽通道（没人该在 JS 侧做百分号编码）：%s" % _RELAX[:4]
    # 反空转：这批语料里必须既有"真的重写了"的，也有"顶住门槛没动"的
    changed = [i for i, ((d, lk), g) in enumerate(zip(HN_SAMPLES, got)) if g != (d or "")]
    assert len(changed) >= 5, "重写正例太少（%s），整条判据可能只是走过场" % changed
    assert len(HN_SAMPLES) - len(changed) >= 5, "反例太少，门槛（≥2 行且含 Points/Cmt）没被钉住"


def test_glued_url_strip_matches_python(tmp_path):
    """`_strip_glued_url` vs `stripGluedUrl`：正例 + 派工点名的四条反例逐条比。"""
    got = _js(tmp_path, {"kind": "call", "fn": "stripGluedUrl",
                         "items": [[t] for (t,) in GLUED_SAMPLES]})
    assert len(got) == len(GLUED_SAMPLES)
    del _RELAX[:]
    for i, ((t,), g) in enumerate(zip(GLUED_SAMPLES, got)):
        w = mod._strip_glued_url(t)
        if w != g:
            _compare_hard(w, g, "粘连 #%d 输入 %r" % (i, t))
        assert mod._strip_glued_url(w) == w, "Python 侧粘连刀不幂等 #%d" % i
    _TALLY["glued"] = len(GLUED_SAMPLES)
    assert _RELAX == [], "粘连刀不许走放宽通道：%s" % _RELAX[:4]
    stripped = [i for i, ((t,), g) in enumerate(zip(GLUED_SAMPLES, got)) if g != (t or "")]
    kept = [i for i, ((t,), g) in enumerate(zip(GLUED_SAMPLES, got)) if g == (t or "")]
    assert len(stripped) >= 3 and len(kept) >= 6, (
        "正例 %s / 反例 %s 太少，剥多了与剥不动都看不见" % (stripped, kept))
    # 派工点名的四条反例必须在语料里（少一条就等于那条反例没被对账）
    for needle in (" 看了文章", "https://a.test/p/1", "\n看了文章", "，这是正文"):
        assert any(needle in (t or "") for (t,) in GLUED_SAMPLES), needle


def test_nav_delink_matches_python(tmp_path):
    """`_delink_nav_links` vs `delinkNavLinks`：站内脱、外部不动，逐条比字节。"""
    got = _js(tmp_path, {"kind": "call", "fn": "delinkNavLinks",
                         "items": [[h] for h in DELINK_SAMPLES]})
    assert len(got) == len(DELINK_SAMPLES)
    del _RELAX[:]
    for i, (h, g) in enumerate(zip(DELINK_SAMPLES, got)):
        w = mod._delink_nav_links(h)
        if w != g:
            _compare_hard(w, g, "去链接 #%d 输入 %r" % (i, h))
    _TALLY["delink"] = len(DELINK_SAMPLES)
    assert _RELAX == [], "去链接不许走放宽通道：%s" % _RELAX[:4]
    # 反空转 + 红线：外部正文链接一条不许被脱
    assert any("blog.example/tag" in h and "blog.example/tag" not in g
               for h, g in zip(DELINK_SAMPLES, got)), "这批样本里一次都没脱过链接"
    # 红线名单里**不含** `lists.gnu.org/archive/html/…`：`archive` 作为**第一段**会命中，
    # 那是构建期已经裁定并钉住代价的已知形状（test_first_segment_archive_is_a_known_and_bounded_cost），
    # 两侧一致地脱掉才是对的 —— 把这条写进"不许动"反而会把两侧一起钉歪。
    for h, g in zip(DELINK_SAMPLES, got):
        for ext in ("openai.com/blog", "about.fb.com/news", "code.example/repo/blob",
                    "blog.example/关于", "blog.example//tag"):
            if ext in h:
                assert ext in g, "外部正文链接被脱掉了：%r -> %r" % (h, g)


def test_nav_segment_table_is_the_same_ordered_list(tmp_path):
    """词表两侧同值同序（改一边必须改另一边）；空表 = 判定永不命中 = 假绿。"""
    got = _js(tmp_path, {"kind": "exports", "name": "NAV_LINK_SEGMENTS"})
    assert tuple(got) == mod._NAV_LINK_SEGMENTS, "导航词表分叉：py=%r js=%r" % (
        mod._NAV_LINK_SEGMENTS, got)
    assert len(got) >= 10, "词表短到不可能覆盖实测形状：%s" % got


# R45：HN 模板四槽位的中文同族词表。这两条是"只改 Python 不改 JS"那类分叉的**直接**闸：
# 输出对账（test_hn_summary_rewrite_matches_python）要两条链路都跑完才比得出来，
# 而这里是把两份表本身按序对死 —— 少一个词、多一个词、换了序、只补了一边，当场红。
HN_WORD_TABLES = (
    ("HN_ART_WORDS", "_HN_ART_WORDS", u"Article URL 槽"),
    ("HN_CMT_WORDS", "_HN_CMT_WORDS", u"Comments URL 槽"),
    ("HN_PTS_WORDS", "_HN_PTS_WORDS", u"Points 槽"),
    ("HN_CMTS_WORDS", "_HN_CMTS_WORDS", u"Comments 计数槽"),
)

# 第 1 步真语料清点的形态清单（词 → 实测出现的槽位）。写进判据而不是写进注释：
# 补词表时漏掉哪个词，这条会直接点出**缺的是哪个词**，不必回头再数一遍语料。
HN_COUNTED_WORDS = {
    u"Article URL 槽": (u"article url", u"文章网址", u"文章链接", u"文章URL", u"文章地址"),
    u"Comments URL 槽": (u"comments url", u"评论网址", u"评论链接", u"评论区链接",
                      u"评论区网址", u"评论URL", u"评论地址", u"评论页面",
                      u"讨论区链接", u"讨论链接"),
    u"Points 槽": (u"points", u"积分", u"得分", u"评分", u"点赞数", u"热度",
                u"热度值", u"分数", u"点数", u"分值", u"关注度", u"当前得分"),
    u"Comments 计数槽": (u"comments", u"评论数", u"评论数量", u"评论"),
}


def test_hn_word_tables_are_the_same_ordered_list(tmp_path):
    """四张 HN 词表两侧同值同序；空表与"只剩一个词"都判失败（R45 的缺口就是这么来的）。"""
    for js_name, py_attr, slot in HN_WORD_TABLES:
        got = tuple(_js(tmp_path, {"kind": "exports", "name": js_name}))
        want = tuple(getattr(mod, py_attr))
        assert got == want, "%s 词表分叉（改一边必须改另一边）：\n  py=%r\n js=%r" % (slot, want, got)
        assert len(got) >= 2, "%s 词表只剩 %d 个词 —— R45 的缺口正是单词表造成的" % (slot, len(got))
        # 每个槽位都必须同时有英文词与中文词：只补英文 = 实时出口对中文译文照样漏。
        has_cjk = [w for w in got if any(u"\u4e00" <= c <= u"\u9fff" for c in w)]
        assert has_cjk, "%s 词表里一个中文词都没有，译文形态必漏" % slot


def test_hn_word_list_covers_the_counted_real_forms(tmp_path):
    """词表必须盖住真语料清点出的每个实际形态（含 `评论` 这个 551 行的最大缺口）。"""
    for js_name, py_attr, slot in HN_WORD_TABLES:
        py_words = tuple(getattr(mod, py_attr))
        js_words = tuple(_js(tmp_path, {"kind": "exports", "name": js_name}))
        missing = [w for w in HN_COUNTED_WORDS[slot] if w not in py_words]
        assert not missing, "%s 的 Python 词表缺实测词：%r" % (slot, missing)
        missing_js = [w for w in HN_COUNTED_WORDS[slot] if w not in js_words]
        assert not missing_js, "%s 的 JS 词表缺实测词：%r" % (slot, missing_js)


def test_r43_parity_corpus_is_big_enough_to_be_a_reconciliation():
    """这条只报读数与下限：**逐条比了几条**、其中多少条两边真的动了手。

    报告要写的"对账条数与不一致数"从这里出。下限写在**样本清单本身**上（不依赖
    别的判据先跑过），否则单独 `-k` 跑这一条会假绿；不一致数只要出现就直接抛异常，
    所以这里能读到的一定是 0。
    """
    assert len(HN_SAMPLES) >= 15, "HN 对账语料被裁小：%d" % len(HN_SAMPLES)
    assert len(GLUED_SAMPLES) >= 15, "粘连对账语料被裁小：%d" % len(GLUED_SAMPLES)
    assert len(DELINK_SAMPLES) >= 25, "去链接对账语料被裁小：%d" % len(DELINK_SAMPLES)
    total = len(HN_SAMPLES) + len(GLUED_SAMPLES) + len(DELINK_SAMPLES)
    assert total >= 55, total
    assert _TALLY["mismatch"] == 0, "对账不一致：%r" % _TALLY
    print("[R43 对账] HN=%d 粘连=%d 去链接=%d 合计=%d 不一致=%d 放宽通道=0"
          % (_TALLY["hn"], _TALLY["glued"], _TALLY["delink"], total, _TALLY["mismatch"]))


# ================================================================ 审查③：实体解码（裁定 R50 最小集合）
# 参照物只有一个：**CPython 3.11 的 `html.unescape`** —— 构建期 `_strip_html`（:1146）、快照 `s`
# 出口、历史清扫三条链路用的都是它。修前 `api/rss.js` 摘要那一格是**顺序级联**（`&amp;` 先解
# ⇒ `&amp;lt;` 被二次解成真 `<`）+ `&[a-z]+;`→空串 + `&#\d+;`→空串，四条实测受害形状
# （同一条 `<description>` 喂两侧，2026-10-05）：
#   `价格 A &amp;amp; B 折扣`        py `价格 A &amp; B 折扣`   / 旧 js `价格 A  B 折扣`（多解一层）
#   `&copy; 2026 版权所有`           py `© 2026 版权所有`       / 旧 js ` 2026 版权所有`（名字被吃掉）
#   `&amp;lt;script&amp;gt;alert(1)` py `&lt;script&gt;alert(1)` / 旧 js 一路解成标签、整条摘要没了
#   `&#20998;&#25968;`              py `分数`                  / 旧 js 空（汉字被整枚吃掉）
# 裁定 R50：**不许为一条缺陷搬进一套新机制** ⇒ 运行时只对齐「真语料证明有暴露的那一圈」：
# 预定义 5 个（`&amp; &lt; &gt; &quot; &#39;`，含「可省分号」与大写两种 legacy 形态）
# + 数字/十六进制引用，**单趟不级联**；表外的命名实体**整枚留字面量**。判据因此分四格，
# 谁也不许替谁（少了任一格都留得出盲区）：
#   §同面 —— 两侧逐字节相等：受害形状/反例/数字 + 预定义 5 的全部形态 + 码位穷举 + 900 条随机；
#   §穷举 —— `test_entity_unescape_gold_values_are_the_python_side` /
#            `test_entity_port_matches_python_on_every_known_form`：金标准与每一种已知形态；
#   §分叉 —— 表外命名实体必须**逐字节等于输入**（旧实现在这里吃名字、置空，正是本批修的缺陷）；
#   §合成 —— `test_runtime_entity_exit_gate_runs_without_any_corpus`（复评 ③ 新增）：现造形状
#            喂**运行时出口**，不读任何语料 ⇒ **CI 每场必跑**的那道闸；
#   §哨兵 —— **本地可选度量**：扫 `rss_history.json` 断言「**已解码**的入库文本里不再引入
#            新的可解命名实体」。它没有本地大语料就 skip ⇒ CI 上从不生效，
#            也因此**从来不是**那道暴露面闸（raw feed 里的命名实体在它数的字段里早已是字符，
#            结构上数不到；账算在下面 §哨兵 那块的注释里）。
# 比较口径：这一格不涉及百分号编码 ⇒ 一律 `_compare_hard`，放宽通道用量必须为 0。
_ENT_PARITY_SAMPLES = [
    # ── 派工点名的受害形状里「两侧同源」的那两条 ──
    u"价格 A &amp;amp; B 折扣",
    u"&amp;lt;script&amp;gt;alert(1)",
    # ── 反例：正文里合法存在的「要展示的代码字面量」，解一层之后仍然是字面量 ──
    u"正文里合法存在的 &amp;lt;img&amp;gt; 是要展示的代码字面量",
    u"示例写法：&amp;lt;p&amp;gt;x&amp;lt;/p&amp;gt;",
    u"教程 &amp;lt;a href=&quot;#&quot;&amp;gt;链接&amp;lt;/a&amp;gt; 演示",
    # ── 数字/十六进制（旧实现 `&#\d+;`→'' 整枚吃掉的那一格）──
    u"&#20998;&#25968; 分数", u"&#x2014; 破折号", u"a&#39;b&#x27;c", u"&#38; &amp;",
    u"&#0; &#13; &#128; &#159; &#149;", u"&#xD800;&#xDBFF;&#xDC00;",
    u"&#65534; &#65535;", u"&#1114112; &#x110000; &#x10FFFF;", u"&#x10FFFE;",
    u"&#0000000000000009;", u"&#99999999999999999999;", u"&#;", u"&#x;", u"&#X26;", u"#38;",
    u"&#39", u"&#x26", u"&#1234;",
    # ── 预定义 5：带分号 / 省分号 / 大写 / 混排 / 相邻 ──
    u"&amp", u"&amp;", u"&AMP;", u"&AMP", u"&lt", u"&LT;", u"&GT;", u"&gt;",
    u"&quot;", u"&QUOT;", u'&quot;引号&quot;', u"a&amp;b", u"&amp;&amp; 双与",
    u"&amp;amp;amp;", u"&amp;lt;amp;", u"&ampc;", u"&amp;#", u"&amp;#38;",
    # ── 两侧都该原样留着的 junk（URL 查询串是这里的主要真实形状）──
    u"&unknownthing;", u"&auto=webp", u"&format=png", u"AT&T &R&D", u"a&b&c", u"&&&&",
    u"&", u"&;", u"& ;", u"&a", u"&ab", u"&Quot;", u"&Amp;", u"A&B&C",
    u"&copltx;", u"&ltn;", u"&ltip;",
    # ── 码点/非 ASCII：Python 按码点量长度，JS 数 UTF-16 单元就会给不同答案 ──
    u"\U0001F600&amp;\U0001F600", u"&\U0001F600amp;", u"中文&amp;正文",
    u"&lt;" + chr(0xA0) + chr(0x2028) + u"x",
    u"&gt" + chr(0xFF1B),                                   # 真语料实测到的「全角分号手误」形状
    # ── 与真标签混排（去标签那一格在端口之外，这里只喂实体层）──
    u"<p>价格 &amp;&amp; 双与</p>", u'<a href="?a=1&amp;b=2">t</a>', u"", u"中文",
]

# 金标准：派工点名的受害形状 + 反例 + 「不许吃内容」，期望值 = **构建期那一个答案**（Python）。
# 只对账看不见「两侧一起改成第三种行为」，所以这里写死期望值：顺序级联会多解一层、名字刀会吃掉
# `&copy;`、数字刀会把 `&#20998;`（汉字「分」）整枚吃掉 —— 三种坏实现都落不到这些值上。
_ENT_GOLD = {
    u"价格 A &amp;amp; B 折扣": u"价格 A &amp; B 折扣",
    u"&amp;lt;script&amp;gt;alert(1)": u"&lt;script&gt;alert(1)",
    u"正文里合法存在的 &amp;lt;img&amp;gt; 是要展示的代码字面量":
        u"正文里合法存在的 &lt;img&gt; 是要展示的代码字面量",
    u"&#20998;&#25968; 分数": u"分数 分数",
    u"a&#39;b&#x27;c": u"a'b'c",
    u"&amp;amp;amp;": u"&amp;amp;",
    u"&auto=webp": u"&auto=webp",
    u"AT&T &R&D": u"AT&T &R&D",
}

# §分叉 声明：表外的命名实体。R50 的裁定是「未知命名实体保持字面量（绝不删除、绝不置空）」，
# 所以每条的期望值就是**输入本身**；同时断言参照物在这里给的是**别的**答案（否则这条声明是空的、
# 判据会在「两侧本来就同形」的输入上假装抓到了分叉）。
_ENT_DIVERGENT = [
    u"&copy; 2026 版权所有",
    u"版权所有 &copy; 与 &reg;",
    u"&nbsp;占位空白",
    u"&hellip; 省略号",
    u"&rdquo;引号&ldquo;",
    u"&notin; 数学符号",
    u"结尾裸名字 &nbsp占位",
]
# 混合条单独写死：同面的那一格照 Python 解，表外那一格留字面量。
_ENT_MIXED = [(u"版权 &copy; 与 &amp;amp; 折扣", u"版权 &copy; 与 &amp; 折扣")]
# 名字必须**逐字**留着（错误信息要能指到具体哪一格被吃了）
_ENT_NAME_INTACT = [(u"&copy; 2026 版权所有", [u"&copy;", u"2026", u"版权所有"]),
                    (u"&hellip; 省略号", [u"&hellip;", u"省略号"])]

# 随机串的字母表按**片段**抽（而不是按字符）：按字符凑 900 条也碰不出几个 `&amp;`，
# 那条判据就会退化成"随机串都落在谁都不解的一格"，绿得很假。
_ENT_FRAGMENTS = [
    u"&amp;", u"&amp", u"&AMP;", u"&AMP", u"&lt;", u"&lt", u"&LT;", u"&gt;", u"&gt", u"&gt" + chr(0xFF1B),
    u"&quot;", u"&QUOT", u"&#39;", u"&#39", u"&#x27;", u"&#X27", u"&#20998;", u"&#13;", u"&#0;",
    u"&#xD800;", u"&#65534;", u"&#x110000;", u"&#;", u"&#x;", u"&#0000000009;", u"&#99999999999999;",
    u"&copy;", u"&copy", u"&nbsp;", u"&hellip;", u"&notin;", u"&unknownthing;", u"&Amp;", u"&Quot;",
    u"&", u";", u"#", u"&#", u"&;", u"&ampamp;", u"&&", u"<p>", u"</p>", u'"', u"'", u"=", u"/",
    u" ", u"\t", u"\n", u"中文", u"价格", u"x", u"A", u"0", u"9", u"webp", u"=", chr(0xA0), chr(0x1F600),
]
_ENT_FUZZ_N = 900

# 实时出口对账用的样本：只放「两侧同源」的形状（表外命名实体在出口那条判据里单独断言，
# 混在一起就等于让一条判据同时回答两个问题，红了不知道是哪一边）。
_ENT_EXIT_SAMPLES = [
    u"价格 A &amp;amp; B 折扣",
    u"&amp;lt;script&amp;gt;alert(1)",
    u"正文里合法存在的 &amp;lt;img&amp;gt; 是要展示的代码字面量",
    u"&#20998;&#25968; 分数",
    u"&unknownthing;",
    u"AT&T &R&D",
    u"5 &lt;sup&gt;10&lt;/sup&gt; 与 100 &amp; 200",
    u'<a href="?a=1&amp;b=2">链接</a>',
]

# `lib/body_rules.js` 最小集合在 Python 侧的**镜像**：只把 R50 那一圈（预定义 5 + 数字，单趟）
# 交给参照物自己回答。它不是第二份出厂实现（出厂只有 JS 那一份），存在的唯一理由是「随机串整条
# 比 Python」会把 §分叉 那一格混进 §同面 当噪声。它与 Python 同形由 §同面/§穷举/§哨兵 单独钉，
# JS 与它在**任何**输入上同形由 §同面 钉 —— 两头都在，中间就没有静默的缝。
_ENT_NARROW_RE = re.compile(r"&#(?:[0-9]+|[xX][0-9a-fA-F]+);?"
                            r"|&(?:amp|AMP|lt|LT|gt|GT|quot|QUOT);?")


def _ent_port_mirror(s):
    return _ENT_NARROW_RE.sub(lambda m: mod.html_mod.unescape(m.group(0)), s)


def _ent_fuzz():
    rnd = random.Random(20261005)
    return ["".join(rnd.choice(_ENT_FRAGMENTS) for _ in range(rnd.randint(1, 9)))
            for _ in range(_ENT_FUZZ_N)]


def test_entity_unescape_matches_python(tmp_path):
    """§同面：样本 + 900 条随机，JS 必须与镜像逐字节同形；同面样本还必须与参照物同形。"""
    src = _ENT_PARITY_SAMPLES + _ent_fuzz()
    got = _js(tmp_path, {"kind": "call", "fn": "decodeEntities", "items": [[s] for s in src]})
    assert len(got) == len(src), "JS 返回条数与样本不等，判据没逐条对齐"
    del _RELAX[:]
    off_surface = 0
    narrow_hits = 0
    for s, g in zip(src, got):
        mirror = _ent_port_mirror(s)
        if g != mirror:
            _compare_hard(mirror, g, "实体解码 %r" % s)
        narrow_hits += len(_ENT_NARROW_RE.findall(s))
        if mirror != mod.html_mod.unescape(s):
            off_surface += 1                       # 越面那一格由 §分叉 单独解释，这里只计数
        else:
            assert g == mod.html_mod.unescape(s), "同面样本与参照物分叉 %r" % s
    assert _RELAX == [], "实体这一层不许走放宽通道（JS 侧没人该做百分号编码）：%s" % _RELAX[:4]
    # 反空转：语料里必须**既有**真被解开的、**也有**两侧都原样留着的，否则这条判据可以在
    # 「谁都不解」的实现下照样绿。
    decoded = [s for s in _ENT_PARITY_SAMPLES if mod.html_mod.unescape(s) != s]
    intact = [s for s in _ENT_PARITY_SAMPLES if mod.html_mod.unescape(s) == s]
    assert len(decoded) >= 20 and len(intact) >= 8, (
        "语料退化：真解开的 %d 条 / 原样留着的 %d 条" % (len(decoded), len(intact)))
    assert narrow_hits >= 1500, (
        "随机串里几乎不再出现窄 token（%d 次命中）⇒ 在测空气" % narrow_hits)
    assert 150 <= off_surface <= len(src) - 100, (
        "随机串越面比例变了（%d 条含表外 token / %d 条）⇒ 片段表被裁过，混合形状不再被覆盖"
        % (off_surface, len(src)))
    print("[③ 同面] 逐条比 %d 条（样本 %d + 随机 %d）：窄 token 命中 %d 次、含表外 token 的混合串 "
          "%d 条，分叉=0 放宽通道=0"
          % (len(src), len(_ENT_PARITY_SAMPLES), _ENT_FUZZ_N, narrow_hits, off_surface))


def test_entity_unescape_gold_values_are_the_python_side(tmp_path):
    """§金标准：JS 与 Python 都必须等于**构建期那一个答案**（钉「以 Python 为参照物」）。"""
    keys = sorted(_ENT_GOLD)
    got = _js(tmp_path, {"kind": "call", "fn": "decodeEntities", "items": [[k] for k in keys]})
    for k, g in zip(keys, got):
        assert g == _ENT_GOLD[k], "JS 侧金标准不等 %r：\n  期望 %r\n  实得 %r" % (k, _ENT_GOLD[k], g)
        assert mod.html_mod.unescape(k) == _ENT_GOLD[k], (
            "参照物自己被改了：%r → %r（要改契约必须先改这张表并说明理由）"
            % (k, mod.html_mod.unescape(k)))
    # 反例那一格的**激活**检查：解一层之后仍然是字面量，产物里不许出现真标签
    for k, v in _ENT_GOLD.items():
        if "&amp;lt;" in k:
            assert "<img" not in v and "<p" not in v and "<a" not in v, "%r 被激活成标签了：%r" % (k, v)
            assert "&lt;" in v and "&gt;" in v, "%r 多解了一层：%r" % (k, v)
    print("[③ 金标准] %d 条两侧同值，代码字面量未被激活" % len(keys))


def test_entity_port_matches_python_on_every_known_form(tmp_path):
    """§穷举：预定义 5 的**每种写法**（带/省分号、大写、后面紧跟杂字符）+ 数字码位（十进制、
    十六进制、大写 X、补零、无分号）逐条对 Python。

    数字为什么必须穷举而不抽样：三张坏码表在 JS 侧被压成了**范围式**（`_isBadCodePoint`），
    范围边界写错一格、或把「规范映射 → 代理区/超范围 → 坏码位」的分支顺序写反，抽样很可能
    正好错过（`&#13;` 变空串、`&#x10FFFF;` 变 U+FFFD 都是这类错）。码位清单在这里由 Python
    自己的 `_invalid_codepoints` / `_invalid_charrefs` **生成** ⇒ 参照物换表这条跟着变，
    不需要有人记得。
    """
    import html as _html_self
    forms = []
    for n in ("amp", "AMP", "lt", "LT", "gt", "GT", "quot", "QUOT"):
        for tail in ("", ";", "x", "c;", "="):
            forms.append("&" + n + tail)
            forms.append(u"前&" + n + tail + u"后")
    cps = (set(range(0, 0x130)) | set(range(0xD7F0, 0xE010)) | set(range(0xFF90, 0x10020))
           | set(range(0x1FFF0, 0x20010)) | set(range(0xFDE0, 0xFDF0))
           | set(range(0x10FFD0, 0x110010)) | set(_html_self._invalid_codepoints)
           | set(_html_self._invalid_charrefs)
           | {0xD7FF, 0xD800, 0xDBFF, 0xDC00, 0xDFFF, 0xFFFD, 0xFFFE, 0xFFFF,
              0x10FFFD, 0x10FFFE, 0x10FFFF, 0x110000, 0x1FFFFF, 0x20000, 0x2FFFD})
    for cp in sorted(cps):
        forms.append("&#%d;" % cp)
        forms.append("&#x%x;" % cp)
        forms.append("&#X%X;" % cp)
        forms.append("&#%020d;" % cp)
        forms.append("&#%d" % cp)
    got = _js(tmp_path, {"kind": "call", "fn": "decodeEntities", "items": [[f] for f in forms]})
    bad = [(f, mod.html_mod.unescape(f), g) for f, g in zip(forms, got)
           if mod.html_mod.unescape(f) != g]
    assert not bad, "穷举对账分叉 %d 条，前 8 条：\n%s" % (
        len(bad), "\n".join("  in=%r\n    py=%r\n   js=%r" % x for x in bad[:8]))
    assert len(forms) > 3000, "穷举样本数掉了（%d）⇒ 码位清单被裁小，这条判据已经名不副实" % len(forms)
    print("[③ 穷举] %d 个形态（码位 %d 个）与 Python 逐字节同形，分叉=0" % (len(forms), len(cps)))


def test_entity_named_divergence_is_declared_and_eats_nothing(tmp_path):
    """§分叉：表外的命名实体必须**整枚原样留着**，且参照物在这里确实给别的答案。

    这一格是 R50 唯一让出来的面，两头都要钉：
      · 钉「不许吃内容」—— 旧实现把 `&copy; 2026` 变成 ` 2026`（名字没了）、把整条摘要变成
        空串；这里期望值就是输入本身，一个字符都不许少。
      · 钉「声明不是空的」—— 样本若被换成两侧本来就同形的输入，这条会在「py == 输入」上红，
        免得判据退化成一堆无意义的自等。
    """
    keys = _ENT_DIVERGENT + [m[0] for m in _ENT_MIXED]
    got = _js(tmp_path, {"kind": "call", "fn": "decodeEntities", "items": [[k] for k in keys]})
    mixed = dict(_ENT_MIXED)
    for k, g in zip(keys, got):
        want = mixed.get(k, k)
        assert g == want, "表外实体那一格动了内容：\n  输入 %r\n  期望 %r\n  实得 %r" % (k, want, g)
        assert g != "", "整条被吃成空串：%r" % k
        if k in mixed:
            continue
        assert mod.html_mod.unescape(k) != k, (
            "%r 在两侧本来就同形 ⇒ 这条分叉声明是空的，样本要换" % k)
        assert mod.html_mod.unescape(k) != g, "%r 的期望值与参照物相同 ⇒ 该并进 §同面，从这张表删掉" % k
    for probe, needles in _ENT_NAME_INTACT:
        one = _js(tmp_path, {"kind": "call", "fn": "decodeEntities", "items": [[probe]]})[0]
        for nd in needles:
            assert nd in one, "实体名或正文被吃掉了：%r → %r（缺 %r）" % (probe, one, nd)
    print("[③ 分叉] %d 条表外命名实体整枚留字面量（旧实现在这里吃名字/置空），另有 %d 条混排写死"
          % (len(_ENT_DIVERGENT), len(_ENT_MIXED)))


# ── §哨兵：**本地可选度量**（复评 ③ 把它说清楚）──────────────────────────────
# 它实际能证明的东西，一句话：**已解码文本里不再引入新的可解命名实体**。
# 它**证明不了**"raw feed 里没有命名实体"—— 数的是 `rss_history.json` 的
# `summary/summary_zh/title/title_zh/full_content`，而这些字段进历史之前就已经过了
# `html.unescape`（构建期 `_strip_html` :1146 与 `_sanitize_html` 的第一句都是它）
# ⇒ raw 里的 `&copy; / &ldquo; / &nbsp; / &#20998;` 到这里早已是 `© “ ” U+00A0 分`，
# **结构上不可能被这条正则数到**。同语料实测（2026-10-05，18,037 条 / 62,661 个非空字段）：
#   raw 形态的命名 token 只有 `&amp;` 41,373 次、`&gt`（全角分号手误）7 次，
#   其余 62 种全是 URL 查询串（`&auto` / `&format` / `&CEO`…，Python 本来就不解）；
#   而**已解码**的字符到处都是 —— 5,402 条含 “ 、5,382 条含 ” 、2,018 条含 U+00A0、
#   70 条含 © ⇒ "语料里没有命名实体"这句从来就不成立，成立的只有"入库文本里没有
#   **新的、还会被解开的**命名 token"。
# 另外它是 **skip 型**判据：没有本地大语料就 skip（实测 31 passed / 1 skipped）⇒
# **CI 上这道暴露面度量从不生效**。所以 CI 上真正生效的那道闸是下面这条合成判据
# `test_runtime_entity_exit_gate_runs_without_any_corpus`，本条只是它之上的可选度量。
HISTORY = os.environ.get("STARHUB_RSS_HISTORY") or os.path.join(ROOT, "rss_history.json")
CORPUS_FIELDS = ("summary", "summary_zh", "full_content", "title", "title_zh")
SENTINEL_FIELDS = ("summary", "summary_zh", "title", "title_zh")
# 与 CPython `html._charref` 同一条正则（写在判据里而不是取私有变量：参照物哪天换了分词，
# 这条要在「我数的是什么」上红，而不是静默数出另一批东西）。
_PY_CHARREF = re.compile(r"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)")
# 白名单 = Python 会解开、且最小集合也认得的命名 token。只能变**长**，且每加一项都要同步
# `lib/body_rules.js` 的 `_ENT_MIN`，否则加了也解不开。
SENTINEL_NAMED_WHITELIST = {u"&amp;", u"&gt" + chr(0xFF1B)}


def _corpus_history():
    if not os.path.exists(HISTORY):
        pytest.skip("没有 rss_history.json ⇒ 这条**本地可选度量**没有语料可数；"
                    "CI 必跑的那道闸是 §合成的 `test_runtime_entity_exit_gate_runs_without_any_corpus`")
    with open(HISTORY, encoding="utf-8") as f:
        return json.load(f)


def test_corpus_named_entity_sentinel(tmp_path):
    """本地可选度量：**已解码**的入库文本里不再引入新的可解命名实体。

    数的是历史里的字段值，而字段值进历史前已过一次 `html.unescape` ⇒
    本条**不**断言"raw feed 里没有命名实体"（那句从来没人证明过，见上面 §哨兵 的账）。
    它断言的是三件都在入库文本这一层成立的事：
      (1) 入库文本里每个 `&`-token，两侧解法逐字节相同；
      (2) 入库的摘要/标题整条喂端口，镜像与参照物同形；
      (3) 还会被 Python 解开的命名 token 只许是白名单那几种（`&amp;`、`&gt；`）。
    语料缺失时 skip ⇒ CI 上不作为闸；闸在下一条合成判据。
    """

    history = _corpus_history()
    assert len(history) >= 10000, "语料退化到 %d 条 ⇒ 这个暴露面已经不代表真货" % len(history)
    tokens = {}
    strings = []
    for rec in history.values():
        for field in CORPUS_FIELDS:
            s = rec.get(field) or ""
            if not isinstance(s, str) or "&" not in s:
                continue
            for m in _PY_CHARREF.finditer(s):
                tokens[m.group(0)] = tokens.get(m.group(0), 0) + 1
            if field in SENTINEL_FIELDS:
                strings.append(s)
    assert tokens, "语料里一个 `&` token 都没有 ⇒ 哨兵在数空气，先确认语料还是不是那份"
    distinct = sorted(tokens)
    got = _js(tmp_path, {"kind": "call", "fn": "decodeEntities",
                         "items": [[t] for t in distinct]})
    # (1) token 级：真语料的每一个 token 两侧必须逐字节同形
    tok_bad = [(t, mod.html_mod.unescape(t), g) for t, g in zip(distinct, got)
               if mod.html_mod.unescape(t) != g]
    assert not tok_bad, "真语料 token 在两侧分叉 %d 种，前 20 种：\n%s" % (
        len(tok_bad), "\n".join("  tok=%r py=%r js=%r" % x for x in tok_bad[:20]))
    # (2) 整条级：真语料的摘要/标题逐条喂端口，镜像与参照物也必须同形
    #     （full_content 只进 token 口径 —— 它走 `sanitizeHtml` 那一格，本批已知挂起）
    sgot = _js(tmp_path, {"kind": "call", "fn": "decodeEntities",
                          "items": [[s] for s in strings]})
    str_bad = []
    for s, g in zip(strings, sgot):
        mirror = _ent_port_mirror(s)
        assert g == mirror, "出口端口与镜像分叉：%r" % s[:80]
        if mirror != mod.html_mod.unescape(s):
            str_bad.append(s)
    assert not str_bad, (
        "**已解码**的入库摘要/标题里又出现了还会被 Python 解开的命名 token（py 解开、我们留字面量）"
        "共 %d 条，样例：\n%s"
        % (len(str_bad), "\n".join(repr(x[:120]) for x in str_bad[:5])))
    # (3) 种类口径：Python 会解开的命名 token 只许是白名单那几种
    named = set(t for t in distinct if t[1:2].isalpha() and mod.html_mod.unescape(t) != t)
    numeric = set(t for t in distinct if t[1:2] == "#")
    newkinds = sorted(named - SENTINEL_NAMED_WHITELIST)
    assert not newkinds, (
        "入库文本里出现了白名单外的**仍可被 Python 解开**的命名实体：%s（条数 %s）。"
        "R50 的最小集合在这一格不再同解："
        "要么把它们加进 `lib/body_rules.js` 的 `_ENT_MIN` 并同步这张白名单，"
        "要么改契约并说明理由。" % (newkinds[:12], [(t, tokens[t]) for t in newkinds[:12]]))
    amp = tokens.get(u"&amp;", 0)
    print("[③ 哨兵｜本地可选度量] 入库（已解码）文本 %d 条 / token %d 个（%d 种）："
          "仍会被 Python 解开的命名 token %s（`&amp;` %d 次）、数字 token %d 种 "
          "⇒ 在**这一层**整条级与 token 级分叉都是 0（raw feed 那一层的账见上方注释，"
          "本条不覆盖；CI 上的闸在下一条合成判据）"
          % (len(history), sum(tokens.values()), len(distinct), sorted(named), amp, len(numeric)))
    assert amp > 1000, "`&amp;` 只剩 %d 次 ⇒ 语料换血了，上面那句「这一层零分叉」要重测" % amp


# ── §合成：CI 每场必跑的那道闸（复评 ③ 第 2 条）──────────────────────────────
# 上面 §哨兵 是 skip 型度量（无大语料 ⇒ `1 skipped`），所以 R50 让出来的那一格
# 「表外命名实体留字面量」在 CI 上**从来没有闸**。这条就是那道闸：现造形状直接喂
# **运行时出口** `api/rss.js` 的 `cleanSummary`（出厂 `s` 那一格），零语料、零网络、零 npm 依赖，
# 只要 runner 上有 node 就每场跑。断言两件事：
#   · 已知预定义与数字引用（`&amp;lt;script&amp;gt;`、`&#20998;`、`&amp;`…）与 Python **逐字节同解**；
#   · 未知/表外命名实体（`&copy; &ldquo; &rdquo; &nbsp; &hellip; &unknownthing;`）**整枚保持字面量**，
#     正文一个字符不许少（修前的顺序级联在这里吃名字、把整条摘要置空，那才是本批修的缺陷）。
# 为什么喂 `cleanSummary` 而不是 `sanitizeHtml`：后者是**正文**那一格，仍是顺序级联，
# `api/rss.js:390` 明写为已知挂起、由 §实体那三条单独管 —— 在这儿一起红就是把挂起当本批的活。
# 丢的那半是**度量**（生产 raw 层的暴露面在本地语料上数不到），不是契约：
# 契约由 §同面 / §穷举 / §分叉 三条钉着，且这三条**都不读语料**
# （实测同一文件 `31 passed / 1 skipped`，skip 的只有哨兵那一条）。
_SYN_TWIN = [
    u"价格 A &amp;amp; B 折扣",
    u"&amp;lt;script&amp;gt;alert(1)",
    u"&#20998;&#25968; 分数",
    u"&#x2014; 破折号",
    u"版权 &amp; 备注",
    u"正文里合法存在的 &amp;lt;img&amp;gt; 是要展示的代码字面量",
]
# (输入, [(JS 该留的字面量, Python 解出来的字符), ...])
_SYN_OFFTABLE = [
    (u"&copy; 2026 版权所有", [(u"&copy;", u"©")]),
    (u"他说&nbsp;好", [(u"&nbsp;", u"\u00a0")]),
    (u"&ldquo;引号&rdquo;", [(u"&ldquo;", u"“"), (u"&rdquo;", u"”")]),
    (u"结尾 &hellip; 省略号", [(u"&hellip;", u"…")]),
]
# 两侧**都**认不得的 token：谁都不许把它吃成空串（旧 `&[a-z]+;`→'' 那格）
_SYN_LITERAL_BOTH = [u"&unknownthing; 与正文", u"AT&T &R&D", u"&copltx; 记号"]
# 形状选择说明：`&ltn;` 那一类（JS 按 HTML5 的 legacy 无分号规则解成 `<`、CPython 整枚留着）
# 归 §同面 的**镜像**口径管，不进这条"与 Python 逐字节同解"，否则合成闸一开跑就红在一条
# 早已声明的分叉上 —— 那是"两条判据互相顶"的形状，不是本条要回答的问题。


def _exit_summary_products(tmp_path, samples):
    """把原始 `<description>`/`<summary>` 形态喂**真**运行时出口 `cleanSummary`，逐条给产物。"""
    api = open(API_RSS, encoding="utf-8").read()
    a = api.find("function extractTag(")
    b = api.find("async function fetchOne(")
    assert 0 < a < b, "api/rss.js 里找不到 extractTag..fetchOne 区段，helper 结构变了"
    seg = api[a:b]
    assert "function cleanSummary(" in seg, "区段里没有 cleanSummary ⇒ 出口形状变了，判据要跟着改"
    spec_p = tmp_path / "syn_ent_spec.json"
    spec_p.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8", newline="\n")
    runner = tmp_path / "syn_ent_exit.js"
    runner.write_text(
        "const COVER = require(%s);\nconst BODY = require(%s);\nconst src = %s;\neval(src);\n"
        "const S = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify("
        "S.map(function (p) { return cleanSummary(p[0], p[1]); })));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB.replace("\\", "/")),
           json.dumps(seg)),
        encoding="utf-8", newline="\n")
    r = subprocess.run([_node(), str(runner), str(spec_p)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300, cwd=ROOT)
    assert r.returncode == 0, "运行时出口跑崩：\n%s\n%s" % (
        (r.stdout or "")[-300:], (r.stderr or "")[-900:])
    got = json.loads(r.stdout)
    assert len(got) == len(samples), "出口返回条数与样本不等（%d vs %d）" % (len(got), len(samples))
    return got


def test_runtime_entity_exit_gate_runs_without_any_corpus(tmp_path):
    """合成闸：不读任何语料的实体判据，钉住"表外留字面量 + 已知与 Python 逐字节同解"。

    与 §哨兵 的分工写死在这儿：**这条是 CI 上的闸**，哨兵只是本地可选度量。
    """
    # 反 skip 自证：这条判据一旦去读大语料就失去存在意义（CI 上没有 64 MB 的 rss_history.json）。
    # 查的是**代码对象里的名字表**而不是源码字符串 —— 查字符串的话这条断言自己就会命中。
    co = test_runtime_entity_exit_gate_runs_without_any_corpus.__code__
    refs = set(co.co_names) | set(co.co_varnames)
    assert "HISTORY" not in refs and "_corpus_history" not in refs, (
        "合成闸又去读大语料了（引用了 %s）⇒ 它会在 CI 上 skip，又变回那道从不生效的度量"
        % sorted(r for r in refs if r in ("HISTORY", "_corpus_history")))
    for s in _SYN_OFFTABLE:
        assert s[1], "%r 没配替换表，断言会是空的" % s[0]
    link = u"https://ex.test/a"
    inputs = ([([s, link]) for s in _SYN_TWIN]
              + [([s[0], link]) for s in _SYN_OFFTABLE]
              + [([s, link]) for s in _SYN_LITERAL_BOTH])
    got = _exit_summary_products(tmp_path, inputs)
    n, i = 0, 0
    # (1) 已知预定义与数字引用：与参照物 `html.unescape` + 去标签**逐字节**同解
    for s, g in zip(_SYN_TWIN, got[i:]):
        i += 1
        w = mod._strip_html(s)
        assert g == w, "同解那一格分叉 %r\n  py: %r\n js: %r" % (s, w, g)
        n += 1
    # (2) 表外命名实体：JS 侧**逐字等于输入**，且差的那一格只可能是被点名的 token
    for (s, pairs), g in zip(_SYN_OFFTABLE, got[i:]):
        i += 1
        assert g == s, "表外实体被动了：%r → %r（契约是整枚留字面量）" % (s, g)
        w = mod._strip_html(s)
        assert w != s, "%r 在参照物那里也不解 ⇒ 这条分叉声明是空的，样本要换" % s
        as_py = g
        for js_tok, py_tok in pairs:
            assert js_tok in as_py, "实体名被吃掉了：%r（缺 %r）" % (g, js_tok)
            as_py = as_py.replace(js_tok, py_tok)
        assert as_py == w, ("分叉只许在实体名那一格：%r\n  把字面量换成 Python 的答案后 %r\n"
                            "  参照物给的却是 %r" % (s, as_py, w))
        n += 1
    # (3) 两侧都不认得的 token：谁都不许吃（修前 `&[a-z]+;`→'' 就是在这儿把正文吃没的）
    for s, g in zip(_SYN_LITERAL_BOTH, got[i:]):
        i += 1
        assert g == s, "未知 token 被吃了：%r → %r" % (s, g)
        assert g == mod._strip_html(s), "两侧在未知 token 上分叉：%r py=%r js=%r" % (s, mod._strip_html(s), g)
        n += 1
    print("[③ 合成闸] 零语料、CI 必跑：同解 %d 条 / 表外留字面量 %d 条 / 两侧都原样 %d 条，"
          "合计 %d 条走**真出口** cleanSummary" % (len(_SYN_TWIN), len(_SYN_OFFTABLE),
                                                  len(_SYN_LITERAL_BOTH), n))


def test_realtime_summary_exit_shares_the_python_entity_port(tmp_path):
    """接线判据：实时出口（`api/rss.js` 的 `cleanSummary`）必须走同一格实体口径。

    端口存在但**没接上出口**等于没修（本仓点名的「定义了不调用」形状，账本 R31 同一格），
    所以这里切 `extractTag..fetchOne` 那段**真代码**跑真函数，拿出厂的 `s` 与构建期
    `_strip_html` 逐条比字节 —— 比的是出口产物，不是 lib 里一个孤立函数。
    """
    api = open(API_RSS, encoding="utf-8").read()
    a = api.find("function extractTag(")
    b = api.find("async function fetchOne(")
    assert 0 < a < b, "api/rss.js 里找不到 extractTag..fetchOne 区段，helper 结构变了"
    seg = api[a:b]
    assert "function stripHtmlKeepLines(" in seg and "function cleanSummary(" in seg, (
        "区段里没有 stripHtmlKeepLines/cleanSummary，出口形状变了")
    runner = tmp_path / "ent_exit.js"
    runner.write_text(
        # COVER/BODY 必须先注进同一作用域：切片切不到文件顶部的 require
        "const COVER = require(%s);\n"
        "const BODY = require(%s);\n"
        "const src = %s;\n"
        "eval(src);\n"
        "const S = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify(S.map((p) => cleanSummary(p[0], p[1]))));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB.replace("\\", "/")),
           json.dumps(seg)),
        encoding="utf-8", newline="\n")
    spec = tmp_path / "ent_exit_spec.json"
    cases = [[s, "https://ex.test/a"] for s in _ENT_EXIT_SAMPLES]
    spec.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([_node(), str(runner), str(spec)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300, cwd=ROOT)
    assert r.returncode == 0, "实时出口跑崩：\n%s\n%s" % ((r.stdout or "")[-300:], (r.stderr or "")[-900:])
    got = json.loads(r.stdout)
    assert len(got) == len(cases), "出口返回条数与样本不等"
    for (raw, _lk), g in zip(cases, got):
        w = mod._strip_html(raw)
        assert g == w, "实时出口的 `s` 与构建期分叉 %r\n  py: %r\n js: %r" % (raw, w, g)
    # 反例那一格在出口层同样不许被激活成真标签（`fc`/`s` 都直接进阅读器 innerHTML）
    for raw, g in zip(cases, got):
        if "&amp;lt;" in raw:
            assert "<img" not in g and "<p" not in g and "<a" not in g, "出口把代码字面量激活成标签了：%r" % g
    # §出口分叉：表外命名实体在出口层的形状也钉死 —— 两侧**都**不许吃掉 `2026`，
    # 差别只有 `&copy;` 解不解成 `©`（R50 让出来的那一格，由 §哨兵 证明语料里今天没有）。
    probe = tmp_path / "ent_div.js"
    probe.write_text(
        "const COVER = require(%s);\nconst BODY = require(%s);\nconst src = %s;\neval(src);\n"
        "process.stdout.write(JSON.stringify(cleanSummary(process.argv[2], 'https://ex.test/a')));\n"
        % (json.dumps(LIB_COVER.replace("\\", "/")), json.dumps(LIB.replace("\\", "/")),
           json.dumps(seg)),
        encoding="utf-8", newline="\n")
    js_out = subprocess.run([_node(), str(probe), u"&copy; 2026 版权所有"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120, cwd=ROOT)
    assert js_out.returncode == 0, "出口分叉探针跑崩：\n%s" % (js_out.stderr or "")[-800:]
    div = json.loads(js_out.stdout)
    assert div == u"&copy; 2026 版权所有", "出口在表外实体上动了内容：%r" % div
    assert mod._strip_html(u"&copy; 2026 版权所有") == u"© 2026 版权所有", (
        "构建期参照物变了：这条分叉声明与 §哨兵 的白名单要一起改")
    # 修前那两条「替成空串」的写法必须真的从**摘要出口那一格**里消失。
    # 范围只取 `stripHtmlKeepLines` 的函数体：`sanitizeHtml`（正文那一格）里同样的级联
    # 是**已知挂起**（派工只点名了摘要侧），在这儿一起红就是把挂起当成本批的活。
    fn_body = seg[seg.index("function stripHtmlKeepLines("):]
    fn_body = fn_body[:fn_body.index("\n}")]
    code = "\n".join(ln for ln in fn_body.splitlines()
                     if not ln.strip().startswith(("*", "//", "/*")))
    assert "BODY.decodeEntities" in code, "摘要出口没接 `BODY.decodeEntities`（端口在但没调用）"
    assert "&[a-z]+;" not in code, "摘要出口还在把 `&[a-z]+;` 替成空串（吃实体名）"
    assert "&#\\d+;" not in code, "摘要出口还在把数字实体替成空串（吃内容）"
    assert not re.search(r"""replace\(/&amp;/g,\s*'&'\)\.replace\(/&lt;/""", code), (
        "摘要出口又写回顺序级联了（`&amp;` 先解 ⇒ `&amp;lt;` 二次解成真标签）")
    print("[③ 出口] 真出口 `s` 与构建期 `_strip_html` 逐条同形 %d 条；表外实体在出口层留字面量"
          % len(cases))
