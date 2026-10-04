# -*- coding: utf-8 -*-
"""star 提醒条判据：表里有条目而收藏里没有 ⇒ 报「旧名待人工判定」，绝不报成「收藏丢了」。

来由（2026-10-04 实测）：`known_categories.json` 有 304 个键，而 GitHub 公开 starred 全集与
线上 DATA 都是 293 条、**双向零差** ⇒ 多出的 11 个名字是旧名残留，不是内容缺失：
8 条仓库改名/转移后真身 id 仍在收藏里（`Accio-org/RealReplicaBench`→`CommerceAgentBench` 等）、
2 条旧路径已 404（`Sliverkiss/workbuddy2api`、`Vincentwei1021/video-shotcraft`）、1 条未定案。
用户一句「同名仓库不等于就是一样的仓库」把口径钉死：**判同一性只能用 repository id，名字只能当线索**。

所以这块的本领是把这件事变成页面上可见、可点开的待办，同时不越两界：
  界一 不自动定性 —— 不在 CI 里逐场探测 301/404（那要再存一份结论，等于新造状态）；
  界二 不表述成收藏丢失 —— 把「名字过期」渲染成「数据没了」是假警，比无警更糟。
另外三条是防我自己犯老毛病：容器不许在无待办时留永久痕迹；名字要转义（仓库名会原样进 HTML）；
主链与快车道共用 `build_index_html`，只给一边注入的话，有新星那版页面会静默缺这块。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 页面上提醒块的唯一标识：实现换标签/换样式都行，但这个标记在「有待办」时必须出现、
# 「无待办」时必须完全不出现 —— 它是"空则无痕"这条判据的抓手。
ATTENTION_NODE = "data-attention"

# 禁止出现在提醒文案里的措辞：这些会把"旧名过期"说成"收藏丢失"，而收藏实际一条没少。
LOST_WORDS = ("丢失", "漏拉", "少了", "已删除", "缺失收藏")

LIVE = [{"full_name": "a/keep"}, {"full_name": "b/keep2"}]
TABLE = {"a/keep": "agent", "b/keep2": "tools", "c/gone": "coding",
         "danny-avila/LibreChat": "assistant"}


def _fab():
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import fetch_and_build as fab
    return fab


def test_attention_lists_table_names_missing_from_current_stars():
    """孤儿集合 = 表键集 − 当前收藏 full_name 集（不多不少）。"""
    items = _fab().star_attention_items(LIVE, TABLE, {}, {})
    got = {i["item"] for i in items}
    assert got == {"c/gone", "danny-avila/LibreChat"}, \
        "提醒集合必须是「表−收藏」，实得 %s" % sorted(got)


def test_attention_entry_carries_kind_so_other_sources_can_join():
    """并入口：每条必须带 kind。本期只有 star_orphan，以后 RSS 超龄等只加 kind 值、不改形状。"""
    items = _fab().star_attention_items(LIVE, TABLE, {}, {})
    assert items, "给定有孤儿却返回空集 ⇒ 判据会空转"
    assert all(i.get("kind") == "star_orphan" for i in items), \
        "每条要标 kind，否则前端无法分类展示、以后也没法并入别的来源"


def test_new_star_absent_from_table_is_never_an_attention_item():
    """反向那半：收藏里有、表里还没记 = 正常新进场，绝不能进提醒（否则每场都报新仓库）。"""
    live = [{"full_name": "a/keep"}, {"full_name": "brand/new-star"}]
    items = _fab().star_attention_items(live, {"a/keep": "agent"}, {}, {})
    assert items == [], "新进场仓库不是待人工处理项，实得 %s" % items


def test_rendered_text_never_claims_stars_are_missing():
    """文案口径：只说"旧名待判定"，不说"收藏少了/丢了"。"""
    fab = _fab()
    html = fab.render_star_attention(fab.star_attention_items(LIVE, TABLE, {}, {}))
    assert html, "有孤儿却渲染出空串 ⇒ 提醒条根本不会上线"
    for w in LOST_WORDS:
        assert w not in html, "提醒文案用了「%s」：收藏实测一条没少，这是假警" % w


def test_same_base_name_candidate_is_hint_not_verdict():
    """同名候选只能当线索（用户明确否证过"同名即同仓库"），不许写成"已改名为"的定论。"""
    fab = _fab()
    live = [{"full_name": "LibreChat-AI/LibreChat"}, {"full_name": "a/keep"}]
    table = {"a/keep": "agent", "danny-avila/LibreChat": "assistant"}
    items = fab.star_attention_items(live, table, {}, {})
    hit = [i for i in items if i["item"] == "danny-avila/LibreChat"]
    assert hit, "旧名 danny-avila/LibreChat 应进提醒，实得 %s" % items
    cand = hit[0]["hint"].get("same_base_name_live") or []
    assert cand == ["LibreChat-AI/LibreChat"], "同名候选要作为线索带出来，实得 %s" % cand
    html = fab.render_star_attention(items)
    assert ("参考" in html) or ("线索" in html), "同名候选必须标明是参考，不是判定"
    assert "已改名为" not in html, "不许把同名候选写成「已改名为」这种定论"


def test_empty_attention_renders_nothing():
    """无待办时必须返回空串——不是空 div、不是占位注释。"""
    fab = _fab()
    assert fab.render_star_attention([]) == "", "空清单要渲染成空串，实得 %r" % \
        fab.render_star_attention([])


def test_page_has_no_attention_node_when_empty():
    """空清单时整页不许留下提醒节点：留了就是永久痕迹，页面永远挂着个空壳。"""
    fab = _fab()
    html = fab.build_index_html([], fab.CATS,
                                attention_html=fab.render_star_attention([]))
    assert ATTENTION_NODE not in html, \
        "无待办却仍在页面留 %s 节点 ⇒ 要求空则无痕" % ATTENTION_NODE


def test_page_shows_attention_node_when_pending():
    """有待办时该节点必须真的出现在整页里（与上一条配对，防"只写不接"）。"""
    fab = _fab()
    block = fab.render_star_attention(fab.star_attention_items(LIVE, TABLE, {}, {}))
    html = fab.build_index_html([], fab.CATS, attention_html=block)
    assert ATTENTION_NODE in html, "有待办却没把块注进页面 ⇒ 占位符没接上"
    assert "c/gone" in html, "提醒里要看得见具体旧名"


def test_orphan_names_are_html_escaped():
    """仓库名原样进 HTML：含标签或引号时必须转义（提醒块是把数据写进页面的唯一新出口）。"""
    fab = _fab()
    live = [{"full_name": "a/keep"}]
    table = {"x/<script>alert(1)</script>": "agent", 'y/"quoted"': "tools"}
    html = fab.render_star_attention(fab.star_attention_items(live, table, {}, {}))
    assert "<script>alert(1)</script>" not in html, "名字里的标签必须被转义，不许成可执行片段"
    assert "alert(1)" in html, "转义是改写法不是删内容：文案本身还得看得见"
    assert "&quot;" in html or "&#34;" in html, "名字里的双引号必须实体化，否则能闭掉属性"


def test_both_render_exits_inject_attention():
    """主链与快车道共用 build_index_html ⇒ 两边都必须传 attention，缺一边就静默不一致。"""
    src = io.open(os.path.join(ROOT, "fetch_and_build.py"), encoding="utf-8").read()
    fast = io.open(os.path.join(ROOT, "fast_refresh.py"), encoding="utf-8").read()
    tpl = io.open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
    assert "__ATTENTION__" in tpl, "模板里要有 __ATTENTION__ 占位符"
    assert re.search(r"build_index_html\([^)]*attention_html", src, re.S), \
        "主链调用 build_index_html 没传 attention_html"
    # 注释里提一次不算传参：先剔掉 # 开头行再找调用点
    fast_code = "\n".join(l for l in fast.splitlines() if not l.strip().startswith("#"))
    assert re.search(r"build_index_html\([^)]*attention_html", fast_code, re.S), \
        "快车道没传 attention_html ⇒ 有新星那场生成的页面会缺提醒条"


def test_empty_live_set_renders_nothing():
    """收藏被拉成空集时不许渲染提醒：那时「表−收藏」= 整张表，会把 300 多个名字全报成待办。
    空收藏是拉取异常的信号，不是「用户取消了所有收藏」的证据 —— 报出来就是假警。"""
    fab = _fab()
    items = fab.star_attention_items([], TABLE, {}, {})
    assert items == [], "live 为空却把整张表报成孤儿（假警风暴）：%s" % len(items)
    assert fab.render_star_attention(items) == ""


def test_attention_block_is_capped():
    """条数上限：index.html 每场重写，无上限的清单会把体积增长写进 git 历史。
    超限必须截断并如实报剩余数，不能静默丢。"""
    fab = _fab()
    live = [{"full_name": "o%d/keep" % i} for i in range(3)]
    table = {"o%d/keep" % i: "agent" for i in range(3)}
    table.update({"z/orphan%03d" % i: "tools" for i in range(60)})
    items = fab.star_attention_items(live, table, {}, {})
    assert len(items) == 60, "条目层要如实给出全部 60 条，实得 %d" % len(items)
    html = fab.render_star_attention(items)
    n = html.count('class="attn-row"')
    assert n < 60, "页面层没截断：60 条全渲染进每场重写的 index.html"
    assert n == fab.ATTENTION_MAX_ROWS, "应当正好截到实现声明的档位，实得 %d" % n
    assert ("另有" in html) and ("60" in html or "%d" % (60 - n) in html), \
        "截断必须如实报剩余，不许静默丢条目"
