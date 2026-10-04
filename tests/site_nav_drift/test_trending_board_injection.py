# -*- coding: utf-8 -*-
"""排行榜注入化判据：让 TRENDING 有一个自己的数据出口，快车道重建整页就再也伤不到它。

为什么只做排行榜、不做关注动态（2026-10-04 复核，修正了我上一轮的诊断范围）：
`FEED` 早就有运行时路径——`refreshFeed()` 拉 `/api/events`，成功替换、失败静默保留内联，
所以内联那份被覆盖成 [] 并不会真的空；而 `TRENDING` 全文只有"内联 + 三处渲染读取"，
**没有任何运行时路径** ⇒ 它才是唯一被快车道覆盖坏掉的一栏（外加 AI 摘要那句也是内联）。

四条判据，第二条和第三条是一对（既要能刷新，又不许把首屏兜底删了）：
① 小时场把**已经算好的**榜单与摘要写成站点件，不重算 ⇒ 零 GitHub 配额；
② 页面有 fetch 该件的注入路径，且失败时退回内联值；
③ 反向：`__TRENDING__` 内联占位符必须还在——删了它首屏就变空，观感退步，
   这类"为了架构干净牺牲首屏"的取舍没经过用户同意；
④ 该件必须同时出现在 update.yml 的 save path 清单与 star-fast.yml 的 restore path 清单，
   只有一边就等于跨场传不到（这个不对称本仓犯过一次，判据是事后补的）。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOARD = "trending_board.json"
TPL = os.path.join(ROOT, "template.html")
FAB = os.path.join(ROOT, "fetch_and_build.py")
WF_UPDATE = os.path.join(ROOT, ".github", "workflows", "update.yml")
WF_FAST = os.path.join(ROOT, ".github", "workflows", "star-fast.yml")


def _t(p):
    return io.open(p, encoding="utf-8").read()


def test_hourly_build_emits_trending_board():
    """小时场要把榜单 + AI 摘要落成一个站点件（数据是 build_trending 现算好的，不重算）。"""
    src = _t(FAB)
    assert BOARD in src, "主链没写 %s ⇒ 前端没东西可注入" % BOARD
    fn = _t(os.path.join(ROOT, "fetch_and_build.py"))
    i = fn.find("def trending_board_payload")
    assert i >= 0, "缺 trending_board_payload()：出口的形状要有单一出处，不能两处各拼一份"


def test_page_fetches_board_and_falls_back_to_inline():
    """注入路径 + 失败退回内联（与 refreshFeed 同构）。"""
    tpl = _t(TPL)
    assert BOARD in tpl, "页面里没有 %s 的 fetch ⇒ 排行榜仍只靠内联，覆盖问题没根治" % BOARD
    i = tpl.find(BOARD)
    window = tpl[max(0, i - 700):i + 900]
    assert "catch" in window or "if(!" in window or "r.ok" in window, \
        "取不到数据时必须退回内联兜底，不许把榜单清空"


def test_inline_trending_fallback_is_not_removed():
    """反向那半：内联占位符不许被删。删了它，首屏在 JSON 回来之前是空的。"""
    tpl = _t(TPL)
    assert "__TRENDING__" in tpl, \
        "__TRENDING__ 内联兜底被删了：注入是加一层，不是换掉首屏（这个取舍没经用户同意）"
    # 只钉"内联赋值还在"，不钉 const/let——注入要能替换它就得是 let（FEED 同理）。
    assert "TRENDING = __TRENDING__" in tpl, "内联赋值语句本身要在"


def test_board_is_published_not_just_cached():
    """它是**站点件**：浏览器同源 fetch ⇒ 必须进 Stage 发布白名单，三处清单逐个一致。

    （我第一版把这条写成"要进跨场缓存族的 save/restore 两侧"，前提错了：快车道根本不该拿它，
    是浏览器拿它。放进缓存只会多一个没人读的文件。）
    """
    files = (("update.yml 的 Stage 清单", WF_UPDATE),
             ("A2 STAGE_ALLOWLIST", os.path.join(ROOT, "tests", "rss_history", "test_pages_deploy_wiring.py")),
             ("A3 PUBLISH", os.path.join(ROOT, "tests", "site_nav_drift", "test_pages_artifact_scope.py")))
    for name, path in files:
        assert BOARD in _t(path), "%s 里没有 %s ⇒ 前端 fetch 会 404" % (name, BOARD)


def test_fast_lane_reuses_the_same_board_file_as_inline_value():
    """快车道重建整页时，内联那份排行榜要取自**同一个出口件**。

    为什么不能省：删掉回填、只留"浏览器 fetch"的话，trending_board.json 万一取不到就是空榜——
    等于把兜底从"有数据"降级成"空对象"。让 CI 与浏览器读同一份文件才是单一真相。
    """
    fr = _t(os.path.join(ROOT, "fast_refresh.py"))
    assert "TRENDING_BOARD" in fr or BOARD in fr, \
        "快车道没把 %s 当回填源 ⇒ 内联兜底会退化成空榜" % BOARD
    fast = _t(WF_FAST)
    assert BOARD in fast, "star-fast.yml 没在生成页面之前把 %s 取回工作目录" % BOARD


def _code_only(txt):
    """剔掉注释行——判据要读行为，不能读关键词。

    本仓第三次踩这个坑了：`_needs_rsync` 被注释里那句"换成 cp 而不是继续 rsync"骗过，
    这次又被我自己写的"这里原本是 starhub-sidebar 族"骗成"没拆干净"。
    """
    return "\n".join(l for l in txt.splitlines() if not l.strip().startswith("#"))


def test_sidebar_snapshot_transition_is_gone():
    """防回潮：过渡态整条链必须消失（只看代码行，注释里讲历史不算残留）。"""
    for name, path in (("star-fast.yml", WF_FAST), ("update.yml", WF_UPDATE),
                       ("fetch_and_build.py", FAB),
                       ("fast_refresh.py", os.path.join(ROOT, "fast_refresh.py"))):
        txt = _code_only(_t(path))
        assert "sidebar_snapshot" not in txt, "%s 里还留着 sidebar_snapshot（过渡态没拆干净）" % name
        assert "starhub-sidebar" not in txt, "%s 里还留着 starhub-sidebar 缓存族" % name
        # 中文名也要钉：前两条只搜英文字面，结果 fast_refresh 拆掉之后 star-fast.yml 的
        # ::notice:: 还在写"或有新星但缺侧栏快照"，判据全绿而日志在讲一个已经不存在的分支
        # ⇒ 读日志的人（包括下一轮的 agent）会以为"有新星也可能不发页面"。
        assert "侧栏快照" not in txt, "%s 的可见内容还写着已删掉的『侧栏快照』分支" % name
    assert not os.path.exists(os.path.join(ROOT, "tests", "site_nav_drift",
                                           "test_sidebar_snapshot_wiring.py")), \
        "旧过渡态判据还在 A3 里，会跟着已删的机制一起变成噪音"
