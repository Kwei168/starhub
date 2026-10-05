# -*- coding: utf-8 -*-
"""症状③最后一格：全文与摘要逐字同段时，阅读器不许再把摘要单列一遍。

为什么量**产物**而不是源文件：`build_rss_aggregator.py` 里的 JS 活在非 raw 的 Python 三引号串中，
源码写的转义要先被 Python 解一道才成为 JS（本仓 2026-10-01/10-05 各踩过一次），
所以只有生成出来的内联脚本才算被测对象。

为什么是**真跑**而不是 grep：本仓点名过"定义了不调用 = 等于没修"，也点名过
"接线判据只 grep 函数名 ⇒ 子匹配变异不红"。这里把渲染那一段连同辅助函数一起喂给 node，
问的是"这段跑完 `h` 里到底有没有 `r2-summary`"。
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "rss_composite"))

from _loader import load_build  # noqa: E402

SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
BLOCK_START = "    if(a.s){"
BLOCK_END = "h+='<div class=\"r2-foot-hint\">"


def _node():
    n = shutil.which("node")
    if not n:
        pytest.skip("本机没有 node（CI 的 ubuntu runner 一定有）")
    return n


def _artifact_script():
    mod = load_build()
    html = mod.build_html([], "2026-10-05 06:00", 0, 0, analysis_data=None,
                          diverse_window_minutes=120, diverse_enabled=True)
    for m in SCRIPT_RE.finditer(html):
        body = m.group(1)
        if "_summaryDuplicatedByFulltext" in body:
            return body
    raise AssertionError("产物里没有 _summaryDuplicatedByFulltext ⇒ 去重的刀没进页面")


def _slice_block(script):
    """取 `if(a.s){...} else {...}` 这一整段（含新加的 _dupFt 守卫），到页脚提示之前为止。"""
    i = script.find(BLOCK_START)
    assert i >= 0, "渲染段起点没找到：`if(a.s){` 形状变了 ⇒ 这条判据会空跑"
    j = script.find(BLOCK_END, i)
    assert j > i, "渲染段终点没找到"
    helper_i = script.find("function _summaryDuplicatedByFulltext")
    assert helper_i >= 0
    helper_j = script.find("\n  }", helper_i)
    assert helper_j > helper_i
    helper = script[helper_i:helper_j + len("\n  }")]
    return helper, script[i:j]


def _run(tmp_path, script, cases, helper=None, block=None):
    """把真产物里的辅助函数 + 渲染段装进一个可调用外壳，逐条喂样本，取回 h。"""
    helper = helper if helper is not None else _slice_block(script)[0]
    block = block if block is not None else _slice_block(script)[1]
    driver = "\n".join([
        helper,
        "module.exports = function (a) {",
        "  var h = '';",
        "  function esc(x){ return String(x == null ? '' : x); }",
        "  function formatSummary(x){ return String(x); }",
        "  function isMostlyZh(){ return true; }",
        "  " + block,
        "  return h;",
        "};",
    ])
    f = os.path.join(str(tmp_path), "driver.js")
    with open(f, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver)
    runner = os.path.join(str(tmp_path), "run.js")
    with open(runner, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("const f = require(%r);\nprocess.stdout.write(JSON.stringify(%s.map(f)));\n"
                 % (f, repr(cases)))
    p = subprocess.run([_node(), runner], capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    assert p.returncode == 0, "node 跑崩：\n%s\n%s" % (out[:400], p.stderr.decode("utf-8", "replace")[:600])
    return __import__("json").loads(out)


LONG = "这是一段足够长的摘要文字，用来判断它是否与内嵌全文逐字相同。"
LONGER = LONG + "而全文在后面还有别的内容，所以两者不该被当成重复。"


def test_reader_hides_summary_when_fulltext_repeats_it(tmp_path):
    """同段 ⇒ 不出现 r2-summary；其余形状必须照旧出现（反向那半与正向同权重）。"""
    script = _artifact_script()
    helper, block = _slice_block(script)
    assert "if(!_dupFt){" in block, "渲染段里没有 _dupFt 守卫 ⇒ 刀没接上"
    cases = [
        {"s": LONG, "fc": "<p>" + LONG + "</p>"},                       # 逐字重复 ⇒ 隐藏
        {"s": LONG, "fc": "<p>" + LONG + "</p><img src=x>"},            # 重复但正文带图 ⇒ 仍隐藏（图在正文里）
        {"s": LONG, "fc": "<p>" + LONGER + "</p>"},                     # 正文更长 ⇒ 摘要照旧出现
        {"s": LONG, "fc": ""},                                          # 无内嵌全文 ⇒ 摘要出现
        {"s": "短句。", "fc": "<p>短句。</p>"},                            # ≤24 字 ⇒ 不隐藏（宁少剥）
    ]
    got = _run(tmp_path, script, cases, helper, block)
    has = [("r2-summary" in g) for g in got]
    assert has == [False, False, True, True, True], (
        "摘要去重的开火形状不对：%s\n%s" % (has, "\n".join(g[:120] for g in got)))
    # fallback-card（无摘要那一支）不许被守卫挪走
    assert "fallback-card" in block, "无摘要分支被卷进守卫 ⇒ 空摘要条目会丢掉兜底卡"
    print("[去重] 5 形状读数 has(r2-summary)=%s" % has)


def test_reader_dedupe_helper_truth_table(tmp_path):
    """辅助函数单独真跑：等值/前缀/短摘要/缺参四种形状各给一个答案。"""
    script = _artifact_script()
    helper = _slice_block(script)[0]
    f = os.path.join(str(tmp_path), "helper.js")
    with open(f, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(helper + "\nmodule.exports = _summaryDuplicatedByFulltext;\n")
    runner = os.path.join(str(tmp_path), "hrun.js")
    cases = [[LONG, LONG], [LONG, LONGER], ["短句。", "短句。"], [LONG, ""], ["", LONG],
             [LONG, "<div  >\n" + LONG + "\n</div>"]]
    with open(runner, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("const f = require(%r);\nprocess.stdout.write(JSON.stringify(%s.map(c => f(c[0], c[1]))));\n"
                 % (f, repr(cases)))
    p = subprocess.run([_node(), runner], capture_output=True)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[:500]
    got = __import__("json").loads(p.stdout.decode("utf-8", "replace"))
    assert got == [True, False, False, False, False, True], (
        "真值表不对（等值=True、正文更长=False、≤24 字=False、缺一半=False、只差标签/空白=True）：%s" % got)


def test_dedupe_guard_is_not_vacuous(tmp_path):
    """反空转：把守卫硬写成"永不重复"，第一条用例就必须重新出现 r2-summary。

    没有这一格，上面那条"隐藏"断言可以在 `return false` 的实现上照样绿。
    """
    script = _artifact_script()
    helper, block = _slice_block(script)
    neutered = helper.replace("return a.length > 24 && vis(fc) === a;", "return false;")
    assert neutered != helper, "辅助函数体形状变了 ⇒ 这条反证是空的"
    got = _run(tmp_path, script, [{"s": LONG, "fc": "<p>" + LONG + "</p>"}], neutered, block)
    assert "r2-summary" in got[0], (
        "把去重判据写死成 false 之后摘要仍然不出现 ⇒ 隐藏动作不是这个判据在管的")
    print("[反空转] 写死 false ⇒ r2-summary 回到页面（判据有牙）")
