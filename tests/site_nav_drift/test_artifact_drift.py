# -*- coding: utf-8 -*-
"""产物与生成端的漂移观测（advisory，不参与 blocking）。

`index.html` 每场构建都由 `fetch_and_build.py` 从 `template.html` 重写，所以"两者不一致"
下一场就会自愈，为它冻住整站部署不成比例；但这条漂移要让人看见 —— 2026-09-25 那次就是
模板坏了而当晚产物还是好的，线上要到次日才暴露。

结构配平的正身在 `tests/site_nav/`（blocking，只断生成端）：模板配平 + 本条相等，
已蕴含产物 header 同样配平，所以这里不重复写一遍失衡判据。
"""
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _header(name):
    path = os.path.join(REPO_ROOT, name)
    assert os.path.isfile(path), "%s 不在了，这条判据就成了恒真" % name
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("<header>")
    assert start >= 0, "%s 里找不到 <header>" % name
    end = text.find("</header>", start)
    assert end > start, "%s 的 <header> 没有闭合" % name
    return text[start:end + len("</header>")].splitlines()


def test_index_header_matches_template():
    """header 内不含任何占位符，所以这条是恒等式而非近似。"""
    tpl = _header("template.html")
    idx = _header("index.html")
    assert tpl == idx, (
        "index.html 的 header 与 template.html 不一致（模板 %d 行 / 产物 %d 行）："
        "手改产物会被下一场构建抹掉，要改就改 template.html（§10.68 那次就是这么丢的）"
        % (len(tpl), len(idx)))
