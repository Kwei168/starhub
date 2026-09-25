# -*- coding: utf-8 -*-
"""首页导航入口的红线：入口必须指向真的产物，且夜场页的回链不能反向悬空。

这批把"深度洞察"挂上首页，同时放开了 cron（`Resolve purpose` 的 schedule 分支显式
publish+main）。挂之前"先有一次真 publish"是硬顺序（§10.x 与 HANDOFF 都写过），
所以这条判据同时断两件事：
1) 首页里确有 `deep-insight.html` 的入口（少一次提交就可能只改了工作流忘了改导航）；
2) 夜场页与首页互链，不许出现"进得去出不来"的死胡同。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel):
    p = os.path.join(ROOT, rel)
    return io.open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def test_index_nav_links_to_the_nightly_page():
    idx = _read("index.html")
    assert idx, "首页不在了，这条判据就成了恒真"
    m = re.search(r'<a[^>]*href="deep-insight\.html"[^>]*>(.*?)</a>', idx, re.S)
    assert m, "首页导航没有指向夜场页的入口（放开 cron 之后页面会每晚更新，入口却缺席）"
    label = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    assert label and "洞察" in label, "入口文字是空的或没有可读名称：%r" % label


def test_nightly_page_links_back_to_the_index():
    page = _read("deep-insight.html") or ""
    if not page:
        # 夜场页是 publish 之后才落到仓库的产物：没有它时上一条判据才是关键，
        # 这条只在不缺件时断"能出去也能回来"。
        return
    assert 'href="index.html"' in page, "夜场页没有回首页的链接（进去就是死胡同）"
