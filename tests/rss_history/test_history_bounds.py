# tests/rss_history/test_history_bounds.py
# -*- coding: utf-8 -*-
"""缓存侧的体积上界：72h 窗口对**单个高频源**不封顶，历史就会随上游放量线性膨胀。

为什么要单独一道"每源上限"而不只是 72h：
出厂侧每源已封顶 120 条（RETENTION_MAX_ITEMS），但历史里一个源可以堆几千条 ——
实测本地快照最大源 agihunt_0 有 1,366 条（3 天内）。72h 一删挡不住它，因为聚合站
每天就倒几千条进来，"72 小时的工作集"本身就是线性增长的量。
生产日志实测：history 9,622 → 11,017（跨 6 场 +14.5%），仍在爬坡。

这道上限的两条硬约束（都是 2026-09-20 两轮对抗审查实测出来的，不是假设）：
1. **对出厂内容结构不可见** —— 靠的是调用点在 src_map 回填与日期审计**之后**，
   不靠"400 比 120 大"这种数据巧合。审查用真实快照证过反例：上限先跑会让某源异常率
   跨过 30% 阈值 ⇒ 120 条出厂条目凭空多出 bad_date、21 条出厂 pub_date 被回拉。
2. **淘汰序必须与判龄同源**（发布序，不是到达序） —— 两套序一旦反向，上限就会删掉
   闸门本来要发的条目（审查实测 120 个槽位里 50 个被换掉）。
"""
import ast
import datetime
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _loader import load_build  # noqa: E402

mod = load_build()
SRC = os.path.join(ROOT, "build_rss_aggregator.py")


@pytest.fixture
def clean(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    mod._rss_history = {}
    mod._LAST_HISTORY_BOUND.clear()
    mod._LAST_UNRELIABLE_SRCS = set()
    monkeypatch.setattr(mod, "RSS_SOURCES", [])
    return monkeypatch


def _hist_entry(link, key, hours_ago, first_seen_ago=None, pub_date=None):
    now = mod._now_bj()
    fs = first_seen_ago if first_seen_ago is not None else hours_ago
    return {
        "link": link, "source": key, "source_key": key, "cat": "ai", "color": "#fff",
        "title": "t " + link, "summary": "s", "title_zh": "", "summary_zh": "",
        "full_content": "", "image": "", "media_url": "", "media_type": "",
        "pub_date": pub_date if pub_date is not None
        else (now - datetime.timedelta(hours=hours_ago)).isoformat(),
        "first_seen": (now - datetime.timedelta(hours=fs)).isoformat(),
    }


def _fn(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_lines(fn, name):
    return [c.lineno for c in ast.walk(fn)
            if isinstance(c, ast.Call) and getattr(c.func, "id", None) == name]


def _accumulate(hist, key="bulk", items=None):
    """跑一遍真实的 _accumulate_history，返回出厂源。"""
    mod._rss_history = dict(hist)
    res, _total = mod._accumulate_history(
        [{"key": key, "name": key, "cat": "ai", "color": "#fff", "tier": 1,
          "items": list(items or [])}])
    return res


def _payload(items):
    """出厂条目的**完整可观测形态**：只比 link 集合会漏掉字段级回归（bad_date / 日期回拉）。"""
    return [(i.get("link"), i.get("pub_date"), bool(i.get("bad_date")),
             bool(i.get("date_fallback")), i.get("time_str")) for i in items]


def test_heavy_source_is_capped_and_small_sources_untouched(clean):
    """高频源压到上限，小源一条都不能动（否则就是把内容删没了）。"""
    heavy = {"http://h/%04d" % i: _hist_entry("http://h/%04d" % i, "heavy", 1.0 + i * 0.05)
             for i in range(900)}
    small = {"http://s/%d" % i: _hist_entry("http://s/%d" % i, "small", 2.0 + i)
             for i in range(50)}
    mod._rss_history = dict(heavy, **small)
    n = mod._bound_history_per_source(mod._rss_history)
    assert len([k for k, v in mod._rss_history.items() if v["source_key"] == "heavy"]) \
        == mod.HISTORY_MAX_PER_SOURCE
    assert len([k for k, v in mod._rss_history.items() if v["source_key"] == "small"]) == 50
    assert n == 900 - mod.HISTORY_MAX_PER_SOURCE


def test_kept_entries_are_the_newest(clean):
    """淘汰必须从最老的开始：留着最新的那批，页面才会变旧而不是变空。"""
    cap = mod.HISTORY_MAX_PER_SOURCE
    links = ["http://n/%04d" % i for i in range(cap + 20)]
    mod._rss_history = {l: _hist_entry(l, "newest", 1.0) for l in links}
    for i, l in enumerate(links):
        mod._rss_history[l] = _hist_entry(l, "newest", 1.0 + i)
    mod._bound_history_per_source(mod._rss_history)
    left = set(mod._rss_history)
    assert links[0] in left, "最新的条目被淘汰了（排序方向反了？）"
    assert links[-1] not in left, "最老的条目还在，等于没淘汰"


def test_eviction_follows_publish_age_not_arrival_order(clean):
    """淘汰序必须与判龄同一只表（发布序）。

    按 first_seen（到达序）裁、按 pub_date（发布序）发，是两套序 —— 审查构造的反例里
    120 个出厂槽位有 50 个被换掉。本例把两套序做成完全反向：晚到但早发布。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    hist = {}
    # 前 30 条：pub_date 很老（60h，仍在 72h 内）但刚刚才到（first_seen 1h）
    for i in range(30):
        l = "http://inv/late%d" % i
        hist[l] = _hist_entry(l, "inv", 60.0 + i * 0.1, first_seen_ago=1.0)
    # 其余：pub_date 新（2h 起）但早就到了（first_seen 50h 起）
    for i in range(cap):
        l = "http://inv/early%04d" % i
        hist[l] = _hist_entry(l, "inv", 2.0 + i * 0.01, first_seen_ago=50.0)
    assert len(hist) == cap + 30
    n = mod._bound_history_per_source(hist, offsets={})
    assert n == 30
    left = set(hist)
    assert not [l for l in left if "/late" in l], \
        "被淘汰的是早到的那批 ⇒ 排序键还在用到达序，上限会删掉闸门要发的内容"


def test_first_seen_only_entries_rank_by_their_own_clock(clean):
    """没有 pub_date 但抓到过 first_seen 的条目，按 first_seen 排 —— 不许一律当"最老"踢掉。

    这类条目的判龄基准就是 first_seen（_retention_ref_dt 的降级分支），排序若把它们
    全部沉底，等于把"唯一的时间锚"变成"优先淘汰"，下一场被 feed 重新抓到还会满血复活。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    hist = {}
    for i in range(cap):                      # 配额占满：pub_date 正常
        l = "http://mix/dated%04d" % i
        hist[l] = _hist_entry(l, "mix", 2.0 + i * 0.01)
    fresh_undated = "http://mix/void_fresh"   # 无 pub_date，但 3h 前才收录
    old_undated = "http://mix/void_old"       # 无 pub_date，60h 前收录
    hist[fresh_undated] = _hist_entry(fresh_undated, "mix", 3.0, pub_date="")
    hist[old_undated] = _hist_entry(old_undated, "mix", 60.0, pub_date="")
    mod._bound_history_per_source(hist, offsets={})
    assert fresh_undated in hist, "刚收录的无 pub_date 条目被最早淘汰（降级键没参与排序）"


def test_undatable_entries_are_evicted_first(clean):
    """两条时间线索都没有 = 判不了龄，排最后 = 最先淘汰，不许赖着不走。"""
    cap = mod.HISTORY_MAX_PER_SOURCE
    mod._rss_history = {}
    for i in range(cap):
        l = "http://u/%04d" % i
        mod._rss_history[l] = _hist_entry(l, "und", 1.0 + i)
    for j in range(30):
        l = "http://u/void%d" % j
        mod._rss_history[l] = _hist_entry(l, "und", 1.0, pub_date="")
        mod._rss_history[l]["first_seen"] = ""
    mod._bound_history_per_source(mod._rss_history, offsets={})
    assert not [k for k in mod._rss_history if k.startswith("http://u/void")], \
        "判不了龄的条目反而挤掉了有日期的"


def test_eviction_tie_is_deterministic(clean):
    """平票必须按 link 定序：同源同批抓到的条目时间戳逐字节相同（实测切分点上并列 12–30 条），
    落在 dict 插入序上会让同一批链接逐场抖动 —— 用户看到的是卡片天天换，不是内容在更新。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    links = ["http://tie/%04d" % i for i in range(cap + 40)]
    hist1 = {l: _hist_entry(l, "tie", 5.0) for l in links}      # 全部同一时刻
    hist2 = {l: hist1[l] for l in reversed(links)}              # 插入序相反
    mod._bound_history_per_source(hist1, offsets={})
    mod._bound_history_per_source(hist2, offsets={})
    assert set(hist1) == set(hist2), "同一份数据换个插入序，淘汰结果就变了（平票靠 dict 序裁决）"


def test_eviction_is_reported(clean, capsys):
    """淘汰必须出声：静默删数据是本项目反复付过代价的形态。"""
    cap = mod.HISTORY_MAX_PER_SOURCE
    mod._rss_history = {("http://r/%04d" % i): _hist_entry("http://r/%04d" % i, "rep", 1.0 + i)
                        for i in range(cap + 7)}
    n = mod._bound_history_per_source(mod._rss_history, report=True, offsets={})
    out = capsys.readouterr().out
    assert n == 7
    assert "每源上限" in out and str(n) in out, "淘汰了却没播报：%r" % out[-200:]


def test_report_prints_even_when_nothing_evicted(clean, capsys):
    """0 淘汰也必须播报。生产实测单场单源最多抓 30 条，上线头几场大概率真是 0；
    "静默"和"这一步压根没跑到"在日志里长得一样，退化就永远没人看得见。
    """
    mod._rss_history = {"http://q/%d" % i: _hist_entry("http://q/%d" % i, "q", 1.0 + i)
                        for i in range(50)}
    n = mod._bound_history_per_source(mod._rss_history, report=True, offsets={})
    out = capsys.readouterr().out
    assert n == 0
    assert "每源上限" in out and "淘汰 0 条" in out, "没淘汰就一个字都不印：%r" % out[-200:]


def test_bound_does_not_change_shipped_payload(clean):
    """反向锚点（必须一直绿）：上限对出厂内容**结构**不可见。

    两条设计缺陷曾被这条用例放过（对抗审查 P0-1）：
    - 造数最老 300h ⇒ 72h 裁剪先删光尾部，上限一场都没动手，evicted=0，比的是"两份空"。
      现在全部条目压在 72h 内，并自证 evicted > 0。
    - 只比 link 列表 ⇒ 字段级回归（bad_date、pub_date 回拉）看不见。现在比完整 payload，
      连"不可信源"集合一起比。
    用 keep=1 而不是"抬到无穷"：抬到无穷只是不去裁，把上限压到 1 才真能证明位置正确。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    links = ["http://b/%04d" % i for i in range(cap + 200)]
    hist = {}
    for i, l in enumerate(links):
        # 全部落在 72h 窗口内（1h .. 21h），裁剪循环不许替上限做筛选
        hist[l] = _hist_entry(l, "bulk", 1.0 + i * 0.033)

    cut_run = _accumulate(hist)
    evicted_at_cap = mod._LAST_HISTORY_BOUND.get("evicted")
    unreliable_at_cap = set(mod._LAST_UNRELIABLE_SRCS)

    old = mod.HISTORY_MAX_PER_SOURCE
    mod.HISTORY_MAX_PER_SOURCE = 10 ** 9
    try:
        full_run = _accumulate(hist)
        evicted_at_full = mod._LAST_HISTORY_BOUND.get("evicted")
        unreliable_at_full = set(mod._LAST_UNRELIABLE_SRCS)
    finally:
        mod.HISTORY_MAX_PER_SOURCE = old

    assert evicted_at_cap > 0, "上限在这份数据上根本没生效（evicted=%r），本用例是空跑" % (
        evicted_at_cap,)
    assert evicted_at_full == 0
    a = _payload(cut_run[0]["items"])
    b = _payload(full_run[0]["items"])
    assert a == b, "上限改变了出厂内容（%d vs %d 条），已构成回归" % (len(a), len(b))
    assert unreliable_at_cap == unreliable_at_full, \
        "上限改动了「不可信源」判定（%s vs %s）：统计样本被裁 ⇒ 前端日期显示与关键词权重跟着变"


def test_bound_extreme_keep_still_ships_same(clean):
    """把上限压到 1 条，出厂内容照旧一字不差 —— 位置正确就不该有任何敏感度。

    这条是上一条的加强版：上一条用真实常量 400，若有人把调用点挪回日期审计之前，
    400 在多数数据上仍"碰巧"不可见；keep=1 一定暴露。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    links = ["http://x/%04d" % i for i in range(cap + 50)]
    hist = {l: _hist_entry(l, "ext", 1.0 + i * 0.05) for i, l in enumerate(links)}
    ref = _payload(_accumulate(hist)[0]["items"])
    old = mod.HISTORY_MAX_PER_SOURCE
    mod.HISTORY_MAX_PER_SOURCE = 1
    try:
        got_run = _accumulate(hist)
    finally:
        mod.HISTORY_MAX_PER_SOURCE = old
    assert mod._LAST_HISTORY_BOUND.get("evicted") >= cap, "keep=1 却几乎没淘汰，上限是死代码"
    assert len(mod._rss_history) == 1, "keep=1 后历史没被压到 1 条"
    assert _payload(got_run[0]["items"]) == ref, "keep=1 改变了出厂内容"


def test_bound_wired_and_state_written_in_accumulate(clean, capsys):
    """接线必须是**行为级**的：AST 只证明"写了这行"，证明不了它跑通并把结果交出来。

    审查实测过三个全绿的变异体：`if False:` 包住调用、调用后不写回 `_LAST_HISTORY_BOUND`、
    日志读错 key —— 三种都能骗过纯 AST 检查，本用例三种都红。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    links = ["http://w/%04d" % i for i in range(cap + 3)]
    hist = {l: _hist_entry(l, "wired", 1.0 + i * 0.05) for i, l in enumerate(links)}
    mod._LAST_HISTORY_BOUND.clear()
    _accumulate(hist)
    out = capsys.readouterr().out
    assert len(mod._rss_history) == cap, "跑完 _accumulate_history 历史没被压到上限"
    assert mod._LAST_HISTORY_BOUND.get("evicted") == 3, (
        "_LAST_HISTORY_BOUND 没收到本场淘汰数（实为 %r）" % mod._LAST_HISTORY_BOUND)
    assert "每源上限" in out, "上限跑完没播报"


def test_bound_runs_after_backfill_and_before_gate(clean):
    """调用点顺序锁：回填 → 上限 → 出口闸门 → return。

    上限若跑到日期审计/回填之前，就会改变统计样本与被回填进 src_map 的条目（P0-2 实测
    120 条被贴 bad_date）；若跑到闸门之后，则本场的缓存与产物不再是同一份约束。
    """
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    fn = _fn(tree, "_accumulate_history")
    assert fn is not None
    bound = _call_lines(fn, "_bound_history_per_source")
    gate = _call_lines(fn, "_apply_retention")
    assert bound and gate, "上限或闸门没被调用"
    ret = min(r.lineno for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value)
    appends = [n.lineno for n in ast.walk(fn)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "append"
               and isinstance(n.func.value, ast.Subscript)
               and getattr(getattr(n.func.value, "slice", None), "value", None) is not None]
    assert appends, "没找到 src_map[...] 的回填 append 语句，本用例的锁失效了"
    assert min(bound) > max(appends), \
        "上限跑在历史回填之前：%d < %d（会改到出厂内容）" % (min(bound), max(appends))
    assert min(bound) < min(gate) < ret, "上限/闸门顺序或位置不对"


def test_gate_and_bound_are_both_wired(clean):
    """两道限必须在同一条路径上：绑定在 return 之前，闸门也在（防止其中一道变死代码）。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    fn = _fn(tree, "_accumulate_history")
    assert fn is not None
    called = {c.func.id for c in ast.walk(fn)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    for n in ("_bound_history_per_source", "_apply_retention"):
        assert n in called, "%s 没被调用（死函数）" % n
    ret = min(r.lineno for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value)
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and getattr(c.func, "id", None) in (
                "_bound_history_per_source", "_apply_retention"):
            assert c.lineno < ret, "%s 写在 return 之后，永远不会执行" % c.func.id


def test_eviction_count_reaches_build_log(clean):
    """淘汰数必须进构建日志，且读的就是上限写回的那个 key。

    只查"键存在"会被两种改动骗过：值写死成 0（变异体 N5 活过一次）、写回与读取用不同
    key（`_LAST_HISTORY_BOUND["evicted"] = ...` 对上 `.get("dropped", 0)` ⇒ 永远 0）。
    """
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    main = _fn(tree, "main")
    assert main is not None
    value_exprs = []
    for node in ast.walk(main):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == "history_evicted_per_source":
                value_exprs.append(v)
    assert value_exprs, "history_evicted_per_source 没进 build_logger"
    names = {n.id for v in value_exprs for n in ast.walk(v) if isinstance(n, ast.Name)}
    assert "_LAST_HISTORY_BOUND" in names, "值没读 _LAST_HISTORY_BOUND：等于恒报 0"
    str_keys = {c.value for v in value_exprs for c in ast.walk(v)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    written = set()
    fn = _fn(tree, "_accumulate_history")
    for st in ast.walk(fn):
        if isinstance(st, ast.Assign) and isinstance(st.value, ast.Call) and \
                getattr(st.value.func, "id", "") == "_bound_history_per_source":
            for t in st.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant):
                    written.add(t.slice.value)
    assert written & str_keys, (
        "日志读的 key（%s）与上限写回的 key（%s）对不上" % (sorted(str_keys), sorted(written)))
    # 不许 0 兜底：与本文件 §可观测性那条规矩同源（"没跑到"与"没东西可淘汰"必须可区分）
    defaults = [c.value for v in value_exprs for kw in ast.walk(v)
                if isinstance(kw, ast.Call) and getattr(kw.func, "attr", "") == "get"
                for c in kw.args[1:] if isinstance(c, ast.Constant)]
    assert 0 not in defaults, "history_evicted_per_source 用 0 兜底：闸门没跑到时会被读成 0 淘汰"


def test_history_margin_covers_shipped_cap(clean):
    """缓存余量必须容得下出厂配额：某源当场抓取失败时产物全靠历史回填，
    上限若 ≤120，那次失败就直接把整源内容抹掉（空卡片 = 用户看到的断链形态）。
    """
    assert mod.HISTORY_MAX_PER_SOURCE > mod.RETENTION_MAX_ITEMS, (
        "缓存每源上限 %d 已低于出厂每源配额 %d：抓取失败场会整源空掉" % (
            mod.HISTORY_MAX_PER_SOURCE, mod.RETENTION_MAX_ITEMS))


def test_eviction_cannot_change_date_audit(clean):
    """位置不变量的行为锁：上限不许改变日期审计的样本。

    审查实测（真实快照）：上限若在 `bad_date` 统计之前跑，某源异常率会跨过 30% 阈值
    ⇒ 120 条出厂条目凭空多出 bad_date（前端改显绝对日期 + 关键词降权）。
    造数：异常条目（pub_date == first_seen，模式 A）集中在发布序最老的那 200 条，
    全量样本异常率 40% ⇒ 该源应被判不可信；keep=100 时若位置错了，审计只剩最新的
    正常条目 ⇒ 异常率 0% ⇒ 整源不判不可信 ⇒ 出厂 120 条的 bad_date 全部翻转。
    这条把 test_bound_runs_after_backfill_and_before_gate 的 AST 锁升级为行为锁。
    """
    hist = {}
    for i in range(300):          # 最新的一批：正常（pub_date 早于 first_seen 1h）
        l = "http://aud/norm%03d" % i
        hist[l] = _hist_entry(l, "aud", 0.1 + i * 0.09, first_seen_ago=1.1 + i * 0.09)
    for i in range(200):          # 最老的一批：模式 A 异常
        l = "http://aud/anom%03d" % i
        e = _hist_entry(l, "aud", 30.0 + i * 0.05)
        e["first_seen"] = e["pub_date"]
        hist[l] = e
    old = mod.HISTORY_MAX_PER_SOURCE
    mod.HISTORY_MAX_PER_SOURCE = 100
    try:
        capped = _payload(_accumulate(hist, key="aud")[0]["items"])
        flagged_capped = set(mod._LAST_UNRELIABLE_SRCS)
        evicted_capped = mod._LAST_HISTORY_BOUND.get("evicted")
    finally:
        mod.HISTORY_MAX_PER_SOURCE = old
    mod.HISTORY_MAX_PER_SOURCE = 10 ** 9
    try:
        full = _payload(_accumulate(hist, key="aud")[0]["items"])
        flagged_full = set(mod._LAST_UNRELIABLE_SRCS)
    finally:
        mod.HISTORY_MAX_PER_SOURCE = old
    assert evicted_capped == 400, "本用例的空跑自证失败（evicted=%r）" % evicted_capped
    assert any(b for _l, _p, b, _f, _t in full), \
        "造数没能让该源被判定不可信，本用例是空跑"
    assert capped == full, "上限改动了出厂字段（bad_date / 日期回拉）：审计样本被裁"
    assert flagged_capped == flagged_full


def test_prune_count_is_published_for_the_log(clean):
    """`history_expired` 必须是"被判定过期而删除的条数"，不能是历史首尾差。

    生产日志实测：`history_before - history_after` 在场场都在**负数**
    （-264 / -201 / -174 / ... / -235，2026-09-20 全天 12 场无一例外）—— 因为新抓进来的
    比删掉的多。也就是说"过期到底删了多少"这个用户点名要的账，在日志里从来没有过。
    本用例把口径钉死：只要 prune 删了 N 条，发布的 expired 就必须是 N，且永不为负。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    hist = {}
    for i in range(120):                       # 真过期（>72h）
        l = "http://exp/old%03d" % i
        hist[l] = _hist_entry(l, "exp", 80.0 + i * 0.1)
    for i in range(cap):                       # 窗内，且把上限撑出淘汰
        l = "http://exp/new%04d" % i
        hist[l] = _hist_entry(l, "exp", 1.0 + i * 0.05)
    mod._LAST_HISTORY_BOUND.clear()
    _accumulate(hist, key="exp")
    assert mod._LAST_HISTORY_BOUND.get("expired") == 120, (
        "过期删除数没发布（实为 %r）：日志里的 history_expired 只能是首尾差" % (
            mod._LAST_HISTORY_BOUND,))
    assert mod._LAST_HISTORY_BOUND.get("expired") >= 0


def test_build_log_expired_field_reads_prune_count(clean):
    """日志字段必须接上那个数，且不许再用首尾差（首尾差在生产恒为负）。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    main = _fn(tree, "main")
    assert main is not None
    vals = {}
    for node in ast.walk(main):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value in (
                    "history_expired", "history_evicted_per_source"):
                vals[k.value] = v
    assert "history_expired" in vals, "history_expired 没进 build_logger"
    expr = ast.dump(vals["history_expired"])
    names = {n.id for n in ast.walk(vals["history_expired"]) if isinstance(n, ast.Name)}
    assert "_history_before" not in expr and "_history_after" not in expr, (
        "history_expired 仍是首尾差 %s：生产实测恒为负数" % sorted(names))
    assert "_LAST_HISTORY_BOUND" in names, "history_expired 没读 prune 计数的发布点"
    # 两个字段读的是同一份 dict 的不同 key，key 名必须与写入侧一致（拼错就恒为 None）
    fn = _fn(tree, "_accumulate_history")
    written = set()
    for st in ast.walk(fn):
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Subscript) and \
                        getattr(t.value, "id", "") == "_LAST_HISTORY_BOUND" and \
                        isinstance(t.slice, ast.Constant):
                    written.add(t.slice.value)
    read = set()
    for key in ("history_expired", "history_evicted_per_source"):
        for c in ast.walk(vals[key]):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                read.add(c.value)
    assert read and read <= written, (
        "日志读的 key %s 与写入的 key %s 对不上" % (sorted(read), sorted(written)))


def test_expired_log_excludes_cap_evictions(clean, capsys):
    """"裁剪 N 篇过期"只许统计真过期的条目。

    上限也删条目，两个数混成一个的话，生产日志的 history_expired 会被体积约束顶高，
    §待验 那条"爬坡是否停下"就读的假数（审查实测：上限开→"裁剪 2764 篇过期"，
    关→"裁剪 0 篇过期"，而那 2764 条全在 72h 窗内）。
    """
    cap = mod.HISTORY_MAX_PER_SOURCE
    hist = {}
    for i in range(100):                                  # 真过期
        l = "http://mix/old%03d" % i
        hist[l] = _hist_entry(l, "mix", 100.0 + i)
    for i in range(cap + 50):                             # 窗内，只被体积上限裁
        l = "http://mix/new%04d" % i
        hist[l] = _hist_entry(l, "mix", 1.0 + i * 0.05)
    _accumulate(hist)
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if "篇过期" in l]
    assert line, "没打印过期裁剪数：%r" % out[-300:]
    n = int(line[0].split("裁剪 ")[1].split(" 篇过期")[0])
    assert n == 100, "「过期裁剪」把体积淘汰也算进去了（%d ≠ 100）：%s" % (n, line[0])
