# -*- coding: utf-8 -*-
"""手机端导航下拉的可点性判据（blocking 门禁 A2，只断生成端）。

来历（2026-09-26 实测）：`@media (max-width:640px)` 给 `.nav-links` 加了 `overflow-x:auto`
让窄屏能横向滚动导航条。CSS 规范规定：一个轴不是 visible 时，另一轴的**使用值**会被强制成
auto —— 作者从没写过 `overflow-y`，它照样变成 auto。于是 `.nav-links` 成了纵向裁剪容器
（实测 clientHeight 31 / scrollHeight 278），绝对定位的下拉面板虽然 `opacity:1 visibility:visible`，
却被裁到只剩 12px，面板里的链接 `elementFromPoint` 根本打不到 —— 用户看到的就是"点了没反应"。

修法是在窄屏分支把面板改成 `position:fixed`（脱离该滚动容器），并用 `top:auto` 取静态位置，
天然贴在按钮下方 6px（`margin-top`），不需要 JS 写 inline top —— 实测跨断点缩放不会留下残值。
"""
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MEDIA_OPEN = "@media (max-width:640px){"


def _mobile_block():
    path = os.path.join(REPO_ROOT, "template.html")
    assert os.path.isfile(path), "template.html 不在了，这条判据就成了恒真"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find(MEDIA_OPEN)
    assert start >= 0, "窄屏媒体查询不在了，这条判据已失效"
    depth, i = 0, start + len(MEDIA_OPEN) - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise AssertionError("窄屏媒体查询的括号没闭合")


def _decl_for(block, selector):
    m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", block)
    return m.group(1) if m else ""


def test_mobile_dropdown_panel_escapes_the_scroll_container():
    block = _mobile_block()
    nav = _decl_for(block, ".nav-links")
    panel = _decl_for(block, ".nav-drop-panel")
    assert panel, "窄屏分支里没有 .nav-drop-panel 规则，判据锚点已失效"
    assert "overflow-x:auto" in nav.replace(" ", ""), (
        "窄屏 .nav-links 已不再 overflow-x:auto：若确实去掉了横向滚动，"
        "本判据可随之退役（面板不再被裁剪），但要先重测手机端")
    assert "position:fixed" in panel.replace(" ", ""), (
        "窄屏下拉面板必须是 position:fixed：绝对定位会被 .nav-links 的滚动容器裁掉"
        "（overflow-x:auto 会连带把 overflow-y 的使用值变成 auto），"
        "面板可见却点不到")


def test_mobile_panel_still_anchored_by_static_position():
    """top:auto + margin-top 撑起 6px 间距；写死 top 会在 header 换行时错位。"""
    panel = _decl_for(_mobile_block(), ".nav-drop-panel").replace(" ", "")
    assert "top:auto" in panel, "窄屏面板丢了 top:auto，会退回硬写坐标"
    assert "margin-top:6px" in panel, "窄屏面板与按钮之间要有 6px 间距"
