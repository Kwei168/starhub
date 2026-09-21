# -*- coding: utf-8 -*-
"""抽屉刷新映射必须保留「收录」标记（任务 #30，门禁 A2）。

现场：点开信源抽屉时页面会打 `/api/rss?source=KEY` 并用一段内联映射把压缩条目
(t/s/u/d) 还原成 `src.items` 形状，再交给 `buildArt()`。该内联映射只列了 8 个字段，
`date_fallback` 不在其中 ⇒ `buildArt` 里 `dfb:!!it.date_fallback` 恒 false ⇒
卡片墙（走快照，带标记）显示「收录 …」，抽屉（走实时）同一篇显示成普通发布时间。
出口 `api/rss.js` 补了标记也会被这里再丢一次，所以两处都得钉。

判据不用文本子串（"date_fallback" 在模板里出现几十次，锁不住任何东西）：
把映射函数从模板里**原样抠出来交给 node 真跑**，检查返回对象。
"""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TPL = os.path.join(ROOT, "build_rss_aggregator.py")
FN = "function _apiItToSrc(it){"


def _node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=20)
        return True
    except Exception:
        return False


def _extract():
    """按大括号配平抠出函数源码；锚点找不到就报错（不许静默跳过）。"""
    text = open(TPL, encoding="utf-8").read()
    i = text.index(FN)
    depth = 0
    for j in range(i + len(FN) - 1, len(text)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise AssertionError("_apiItToSrc 大括号没配平，模板被改坏了")


def _run_js(body, tmp_path):
    drv = tmp_path / "drawer_map.cjs"
    drv.write_text(body + "\n", encoding="utf-8")
    r = subprocess.run(["node", str(drv)], capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120, cwd=str(tmp_path))
    assert r.returncode == 0, "node 跑挂: %s %s" % (r.stdout[-400:], r.stderr[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not _node(), reason="本机没有 node（CI 上有）")
def test_drawer_map_preserves_capture_marker(tmp_path):
    out = _run_js(
        _extract() + "\nprocess.stdout.write(JSON.stringify("
        "_apiItToSrc({t:'标题',u:'http://e/x',d:'2026-09-21T10:00:00Z',date_fallback:1})));",
        tmp_path)
    assert out.get("link") == "http://e/x", out
    assert out.get("pub_date") == "2026-09-21T10:00:00Z", out
    assert out.get("date_fallback") is True, (
        "抽屉映射没把 date_fallback 带进 src.items ⇒ buildArt 的 dfb 恒 false，"
        "同一篇文章在抽屉里丢掉「收录」前缀：%s" % out)


@pytest.mark.skipif(not _node(), reason="本机没有 node（CI 上有）")
def test_drawer_map_keeps_dated_item_plain(tmp_path):
    out = _run_js(
        _extract() + "\nprocess.stdout.write(JSON.stringify("
        "_apiItToSrc({t:'标题',u:'http://e/y',d:'2026-09-21T09:00:00Z'})));",
        tmp_path)
    assert not out.get("date_fallback"), "带真实发布时间的条目被误标成收录：%s" % out


def test_call_site_uses_the_shared_map():
    """接线：调用点必须走这个函数，且不许退回内联映射（退回就会再丢字段）。"""
    text = open(TPL, encoding="utf-8").read()
    assert "var newItems=data.items.map(_apiItToSrc);" in text, (
        "抽屉调用点没走 _apiItToSrc ⇒ 映射可能有第二份内联实现，字段又会被丢掉")
    assert not re.search(r"data\.items\.map\(function\s*\(it\)", text), (
        "模板里又出现了内联的 data.items.map(function(it){...})，"
        "它会绕过 _apiItToSrc 并再次丢 date_fallback")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
