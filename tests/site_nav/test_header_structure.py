# -*- coding: utf-8 -*-
"""首页 header 结构判据。

来历（台账 §10.74）：2026-09-25 终止深夜洞察时，`template.html` 摘除"深度洞察"入口行
连带删掉了紧邻其下的 `<div class="nav-drop">` 开标签。多出来的那个 `</div>` 在浏览器里
提前闭合了 `div.hd`（header 的 flex 行容器），于是"资讯平台""AI 工具""导出/导入/刷新"
降级成 header 的块级兄弟，纵向堆叠成错位。当晚 index.html 只删了入口行所以没露馅，
下一场白天构建从坏模板重写产物后才在线上看见。
"""
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

DROP_OPEN = '<div class="nav-drop">'
DROP_BTN = 'class="nav-drop-btn"'


def _read(name):
    path = os.path.join(REPO_ROOT, name)
    assert os.path.isfile(path), "%s 不在了，这条判据就成了恒真" % name
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _header(text):
    start = text.find("<header>")
    assert start >= 0, "找不到 <header>，判据锚点已失效"
    end = text.find("</header>", start)
    assert end > start, "<header> 没有闭合"
    return text[start:end + len("</header>")]


def _div_walk(header_html):
    """返回 (收尾深度, 过程中出现过的最浅深度)。svg 内部无 div，整段剔掉免干扰。"""
    depth = 0
    shallowest = 0
    for line in re.sub(r"<svg\b.*?</svg>", "", header_html, flags=re.S).splitlines():
        for slash in re.findall(r"<(/?)div\b", line):
            depth += 1 if slash == "" else -1
            shallowest = min(shallowest, depth)
    return depth, shallowest


def test_template_header_div_balance():
    """开闭配平：既不能少闭（吞掉后续兄弟），也不能多闭（提前闭合 div.hd）。"""
    depth, shallowest = _div_walk(_header(_read("template.html")))
    assert depth == 0, "template.html 的 header 里 div 少闭合 %d 个" % depth
    assert shallowest == 0, (
        "template.html 的 header 里有 %d 个无主 </div>，浏览器会拿它去闭合外层容器"
        % -shallowest)


def test_template_dropdown_buttons_are_wrapped():
    """每个下拉按钮都要有 nav-drop 包裹：CSS 的 position:relative 挂在这个容器上。"""
    header = _header(_read("template.html"))
    wrappers = header.count(DROP_OPEN)
    buttons = header.count(DROP_BTN)
    assert buttons >= 1, "header 里已经没有下拉按钮了，这条判据失去意义"
    assert wrappers == buttons, (
        "下拉按钮 %d 个但容器只有 %d 个：有按钮裸在 nav 下，flex 布局会散"
        % (buttons, wrappers))


def test_index_header_matches_template():
    """产物 header 必须与生成端逐行一致 —— header 里没有任何占位符。"""
    tpl = _header(_read("template.html")).splitlines()
    idx = _header(_read("index.html")).splitlines()
    assert tpl == idx, (
        "index.html 的 header 与 template.html 不一致：index.html 每场构建都由模板重写，"
        "手改产物会被抹掉，改模板才对（差异行数 %d/%d）" % (len(tpl), len(idx)))
