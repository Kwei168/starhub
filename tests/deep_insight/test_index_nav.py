# -*- coding: utf-8 -*-
"""首页导航入口的红线：入口必须钉在**生成端**，且夜场页的回链不能反向悬空。

为什么判据读 `template.html` 而不是 `index.html`（2026-09-25 实测教训，台账 §10.68）：
`index.html` 是 `fetch_and_build.py` 每场构建从 `template.html` 重写的产物
（:792 读模板、:811 写产物）。上一批把入口手改进 `index.html`，这条判据当时照样绿，
而远端 main 与 verify 的 `index.html` 里"深度洞察"都是 0 次命中 —— 判据钉在可重建的产物上
等于没有判据。现在断的是源头那一份，另加一条单向同源检查专门抓"只改产物没改模板"。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENTRY_RE = r'<a[^>]*href="deep-insight\.html"[^>]*>(.*?)</a>'


def _read(rel):
    p = os.path.join(ROOT, rel)
    return io.open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def test_the_nav_entry_lives_in_the_generator():
    tpl = _read("template.html")
    assert tpl, "template.html 不在了，这条判据就成了恒真"
    m = re.search(ENTRY_RE, tpl, re.S)
    assert m, ("首页入口不在生成端 template.html 里：下一场白天构建就会从模板重写 index.html，"
               "入口消失、夜场页变成有产物没入口的孤儿")
    label = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    assert "洞察" in label, "模板里入口文字不可读：%r" % label


def test_the_product_never_outruns_the_generator():
    """单向同源：产物有的入口，模板必须有。反过来（模板有、产物还没重建）是合法中间态。"""
    idx = _read("index.html")
    if not idx:
        return
    if re.search(ENTRY_RE, idx, re.S):
        assert re.search(ENTRY_RE, _read("template.html"), re.S), \
            "入口只被手改进产物 index.html：下一场构建就从模板被抹掉（§10.68 那次就是这么丢的）"


def test_nightly_page_links_back_to_the_index():
    page = _read("deep-insight.html") or ""
    if not page:
        # 夜场页是 publish 之后才落到仓库的产物：没有它时上面两条判据才是关键，
        # 这条只在不缺件时断"能出去也能回来"。
        return
    assert 'href="index.html"' in page, "夜场页没有回首页的链接（进去就是死胡同）"
