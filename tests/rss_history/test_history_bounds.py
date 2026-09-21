# tests/rss_history/test_history_bounds.py
# -*- coding: utf-8 -*-
"""缓存侧的体积口径：**只有 72h 时间窗是约束，窗内内容不许按条数淘汰**。

为什么把"每源上限 400 条"撤掉（这是生产实测推翻设计，不是我觉得不好）：
1. 时间窗自己就把体积框住了。淘汰上线前的 93 场构建里，历史是
   16,069 → 11,756 条，平均斜率 **-46.9 条/场**（在往下走），根本没有单调爬升。
   我之前看到的 +230/场 只是窗口填装期的暂态，拿它当趋势是错的。
2. 条数上限不省体积，只是持续丢弃窗内内容。淘汰上线后 10 场斜率反而变成
   **+65.7 条/场**（被腾空的名额又填回来了），同期累计淘汰 2,231 条 ——
   也就是说这道刀切掉的量最后又被补回来，换来的是窗内条目被永久换掉。
3. 上限切掉的几乎全是窗内条目。淘汰首落地那场切 1,547 条，而同一场真正的过期裁剪只有 21 条。

所以本文件的判据转向两件事：**窗内的必须留下、过期的必须出去**，
体积则改为"只报警不动手"（深度警戒线 + 最老保留条目的龄期），让"撑爆"在发生前可见。
"""
import ast
import datetime
import io
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _loader import load_build  # noqa: E402

mod = load_build()
SRC = os.path.join(ROOT, "build_rss_aggregator.py")
# 已被撤销的"按条数淘汰"机制的符号清单：删就要删干净（py_compile 查不出 NameError）
REMOVED_SYMBOLS = ("HISTORY_MAX_PER_SOURCE", "_bound_history_per_source",
                   "_hist_recency_key", "_RECENCY_FLOOR", "_LAST_HISTORY_BOUND",
                   "history_evicted_per_source")


@pytest.fixture
def clean(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    mod._rss_history = {}
    mod._LAST_HISTORY_ACCOUNT.clear()
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


def _accumulate(hist, key="bulk", items=None):
    mod._rss_history = dict(hist)
    res, _total = mod._accumulate_history(
        [{"key": key, "name": key, "cat": "ai", "color": "#fff", "tier": 1,
          "items": list(items or [])}])
    return res


def _source_hist(key, n, base_age=1.0, step=0.04):
    return {"http://%s/%04d" % (key, i): _hist_entry("http://%s/%04d" % (key, i), key,
                                                     base_age + i * step)
            for i in range(n)}


def test_in_window_entries_are_never_cut_by_count(clean):
    """根因判据：一个源在 72h 窗内堆到警戒线以上（2400 条），也必须 2400 条全留。

    这条正是被撤销的那道"每源上限 400"打红的形态。造数必须**越过警戒线**：
    不越线的话，"哨兵顺手把超出部分删掉"这种实现照样能骗过全部断言
    （变异体 W1 第一版就这么活了下来 —— 计数在删除之前算，报出来的深度还是真的）。
    """
    hist = _source_hist("heavy", 2400, step=0.02)      # 龄期 1h .. 49h，全在窗内
    _accumulate(hist, key="heavy")
    left = len(mod._rss_history)
    assert left == 2400, "窗内条目被按条数淘汰了（%d < 2400）：时间窗才是唯一体积约束" % left


def test_stale_entries_still_leave_even_when_a_source_is_huge(clean):
    """撤掉条数上限不等于撤掉清理：900 条里 300 条已过 72h，那 300 条必须出去。"""
    hist = {}
    for i in range(300):
        l = "http://mix/old%03d" % i
        hist[l] = _hist_entry(l, "mix", 80.0 + i * 0.1)
    for i in range(600):
        l = "http://mix/new%04d" % i
        hist[l] = _hist_entry(l, "mix", 1.0 + i * 0.05)
    _accumulate(hist, key="mix")
    left = set(mod._rss_history)
    assert not [k for k in left if "/old" in k], "过期条目留下了（%d 条）—— 清理被撤掉了" % (
        len([k for k in left if '/old' in k]))
    assert len(left) == 600


def test_watch_publishes_depth_and_oldest_age(clean):
    """哨兵要报的是"往哪儿涨 + 窗口守没守住"两个事实，不是淘汰数。"""
    hist = _source_hist("deep", 2600, step=0.02)
    _accumulate(hist, key="deep")
    acc = mod._LAST_HISTORY_ACCOUNT
    assert acc.get("max_per_source") == 2600, "最深源没被报出来（%r）" % acc
    assert acc.get("over_watch") == 1, "越过警戒线的源数不对（%r）" % acc
    oldest = acc.get("oldest_age_h")
    # 造数年龄 1.0h .. 52.98h（2600 条 × 0.02h 步长），所以"最老保留条目"必须≈53h：
    # 只断言 0<=x<=72.5 会被"取最小龄/取平均"这类实现混过去（哨兵就白装了）。
    assert 52.0 <= oldest <= 53.6, (
        "保留最老龄期 %r 不在预期区间 52.0..53.6（造数最老 52.98h）：龄期哨兵算错了" % oldest)


def test_watch_alarms_only_when_over_the_line(clean, capsys):
    """过警戒线必须打 ::warning（"撑爆"要在发生前可见）；没过时不许瞎报。"""
    capsys.readouterr()
    _accumulate(_source_hist("ok", 50), key="ok")
    out = capsys.readouterr().out
    assert "每源深度" in out, "没到警戒线也要有深度这一行，否则 0 与没跑到不可区分：%r" % out[-200:]
    assert "::warning" not in out, "50 条就报警，警戒线形同虚设"
    capsys.readouterr()
    _accumulate(_source_hist("big", mod.HISTORY_WATCH_PER_SOURCE + 10, step=0.02),
              key="big")
    out = capsys.readouterr().out
    assert "::warning" in out and "超警戒" in out, "越线却没报警：%r" % out[-300:]


def test_watch_never_deletes_anything(clean):
    """哨兵只许看不许动手 —— 一旦它顺手删东西，就等于把上限换了个名字放回来。

    造数同样要越过警戒线（低于线时"删超出部分"根本不会触发，等于没测）。
    """
    n = mod.HISTORY_WATCH_PER_SOURCE + 100
    hist = _source_hist("ro", n, step=0.01)            # 龄期 1h..21h，全在窗内
    before = set(hist)
    got = dict(hist)
    out = mod._history_depth_watch(got, report=False)
    assert set(got) == before, "哨兵删了条目（%d → %d）" % (len(before), len(got))
    assert out["over_watch"] == 1 and out["max_per_source"] == n, (
        "越线了却没报（%r）" % out)


def test_expired_account_counts_only_stale_entries(clean, capsys):
    """"过期账"只统计真过期的条目，且必须非负。

    生产实测旧口径 `history_before - history_after` 全天 12 场恒为负数（-264/-201/…），
    因为每场新抓进来的比删掉的多 —— 那本账从来没存在过。
    """
    hist = {}
    for i in range(120):
        l = "http://exp/old%03d" % i
        hist[l] = _hist_entry(l, "exp", 80.0 + i * 0.1)
    hist.update(_source_hist("exp", 500, base_age=1.0, step=0.05))
    mod._LAST_HISTORY_ACCOUNT.clear()
    _accumulate(hist, key="exp")
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if "篇过期" in l]
    assert line, "没打印过期裁剪数：%r" % out[-300:]
    n = int(line[0].split("裁剪 ")[1].split(" 篇过期")[0])
    assert n == 120, "「过期裁剪」数不对（%d ≠ 120）：%s" % (n, line[0])
    assert mod._LAST_HISTORY_ACCOUNT.get("expired") == 120


def test_gate_and_watch_are_both_wired(clean):
    """清理/闸门/哨兵必须都在同一条路径上且写在 return 之前。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    fn = _fn(tree, "_accumulate_history")
    assert fn is not None
    called = {c.func.id for c in ast.walk(fn)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    for n in ("_history_depth_watch", "_apply_retention"):
        assert n in called, "%s 没被调用（死函数）" % n
    ret = min(r.lineno for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value)
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and getattr(c.func, "id", "") in (
                "_history_depth_watch", "_apply_retention"):
            assert c.lineno < ret, "%s 写在 return 之后，永远不会执行" % c.func.id


def test_removed_count_cap_leaves_no_dangling_symbols(clean):
    """撤销机制要按符号清单在**入库文件**里断言清除：留半个引用就是运行时 NameError。

    只查 git ls-files：一次性变异脚本（_mut_*.py）不入库，不该算残留；
    本文件自己带着符号清单（REMOVED_SYMBOLS），也要跳过。台账（docs/）保留历史叙述。
    """
    import subprocess
    raw = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT,
                         capture_output=True).stdout
    hits = []
    names = [n for n in raw.split(bytes([0])) if n]
    assert names, "git ls-files 返回空 ⇒ 本用例是空跑（隔离树里没有 index 就会这样）"
    assert len(names) > 50, "扫到的入库文件只有 %d 个，不像真仓库，判据视为无效" % len(names)
    for name in raw.split(bytes([0])):
        if not name:
            continue
        rel = name.decode('utf-8', 'replace').replace(chr(92), '/')
        if rel.startswith('docs/') or rel == 'tests/rss_history/test_history_bounds.py':
            continue
        if not rel.endswith(('.py', '.js', '.html', '.yml', '.yaml')):
            continue
        text = io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()
        for sym in REMOVED_SYMBOLS:
            if sym in text:
                hits.append('%s::%s' % (rel, sym))
    assert not hits, "还有入库文件引用被撤销的条数上限机制：%s" % hits[:8]


def test_build_log_reports_depth_not_eviction(clean):
    """日志字段与哨兵同名同 key，且不许 0 兜底、不许再留淘汰字段。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    main = _fn(tree, "main")
    assert main is not None
    pairs = {}
    for node in ast.walk(main):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and \
                    k.value.startswith("history_"):
                pairs[k.value] = v
    assert "history_evicted_per_source" not in pairs, "条数淘汰字段还在，机制没撤干净"
    for want in ("history_expired", "history_max_per_source", "history_over_watch"):
        assert want in pairs, "日志缺 %s（现有 %s）" % (want, sorted(pairs))
    fn = _fn(tree, "_accumulate_history")
    written = set()
    for st in ast.walk(fn):
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Subscript) and \
                        getattr(t.value, "id", "") == "_LAST_HISTORY_ACCOUNT" and \
                        isinstance(t.slice, ast.Constant):
                    written.add(t.slice.value)
    for want in ("history_expired", "history_max_per_source", "history_over_watch"):
        keys = {c.value for c in ast.walk(pairs[want])
                if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        assert keys & written, "%s 读的 key %s 与写入侧 %s 对不上" % (
            want, sorted(keys), sorted(written))
        defaults = [c.value for c in ast.walk(pairs[want])
                    if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "get"
                    for a in c.args[1:] if isinstance(a, ast.Constant)]
        assert not defaults, "%s 用 %r 兜底：没跑到与跑出了 0 不可区分" % (want, defaults)


def test_falsified_future_dates_leave_the_cache_at_72h(clean):
    """判过期必须和出口闸门用同一只表。

    造一条 pub_date 在未来、first_seen 已在 100h 前的条目（上游时钟错乱 + 我方按收录
    降级判伪的那种）：旧口径只看 pub_date ⇒ 它"还年轻"永远留在缓存里，而闸门每次都丢它
    —— 真实重放实测缓存里留着的最老条目真龄 140.1h。
    """
    now = mod._now_bj()
    l = "http://clk/falsified"
    e = _hist_entry(l, "clk", 100.0)
    e["pub_date"] = (now + datetime.timedelta(hours=50)).isoformat()   # 不可能的未来日期
    e["first_seen"] = (now - datetime.timedelta(hours=100)).isoformat()
    hist = {l: e}
    hist.update(_source_hist("clk", 5, step=0.5))
    _accumulate(hist, key="clk")
    assert l not in mod._rss_history, (
        "被证伪的未来日期条目靠假日期赖在缓存里（真龄 100h > 72h）")
    assert len(mod._rss_history) == 5


def test_prune_and_gate_share_one_clock(clean):
    """缓存里不该留着"闸门一定会丢"的条目：两个口径的差集必须为空。

    混合三类：真龄 10h 正常、真龄 80h 正常（超 72h 应出缓存）、真龄 100h 且 pub_date 是
    未来假日期（旧口径会留在缓存）。断言只剩第一条，且出厂集合与缓存集合一致。
    """
    now = mod._now_bj()
    hist = {}
    for name, age, fake in (("fresh", 10.0, False), ("stale", 80.0, False),
                            ("falsified", 100.0, True)):
        l = "http://two/%s" % name
        e = _hist_entry(l, "two", age)
        if fake:
            e["pub_date"] = (now + datetime.timedelta(hours=40)).isoformat()
            e["first_seen"] = (now - datetime.timedelta(hours=age)).isoformat()
        hist[l] = e
    res = _accumulate(hist, key="two")
    assert set(mod._rss_history) == {"http://two/fresh"}, (
        "缓存留下了闸门会丢的条目：%s" % sorted(mod._rss_history))
    shipped = {i["link"] for i in res[0]["items"]}
    assert shipped == {"http://two/fresh"}, "出厂与缓存不同一份数据：%s" % sorted(shipped)


def test_oldest_age_follows_publish_clock(clean):
    """龄期哨兵必须用判龄那一只表（发布时间），不是 first_seen（到达时刻）。

    审查独立造的变异体 F4 证明：把 `_retention_ref_dt` 换成 `_parse_hist_dt(first_seen)`，
    原有全部判据照绿 —— 因为造数里 first_seen 与 pub_date 同一个值，两只钟永远同数。
    这里刻意把两者拉开（发布很久、刚被抓到），F4 那种换表实现当场露馅。
    """
    hist = {}
    for i in range(3):
        l = "http://clock/late%d" % i
        # 真实发布龄 60h+，但 first_seen 只有 2h（刚被这个 feed 重新列出）
        hist[l] = _hist_entry(l, "clk", 60.0 + i, first_seen_ago=2.0)
    _accumulate(hist, key="clk")
    oldest = mod._LAST_HISTORY_ACCOUNT.get("oldest_age_h")
    assert oldest is not None and oldest >= 59.0, (
        "最老龄期报的是 %r：贴着 first_seen（2h）而不是发布龄（60h），换表实现没被抓到" % oldest)


def test_depth_report_names_the_deepest_source_among_many(clean):
    """多源时"最深"必须真的指向最深那个源。

    审查变异体 F2：把分组键 `source_key` 塌成一个桶 ⇒ max_per_source 变成全库条数，
    生产量级下会每场无脑报警（实测 5,579 > 2,000），而全部造数只有 1 个源，抓不到。
    """
    watch = mod.HISTORY_WATCH_PER_SOURCE
    deep = _source_hist("deep", watch + 50, step=0.01)          # 越线
    shallow = _source_hist("shallow", watch + 400, step=0.01)   # 更多条但另一源
    # 让 shallow 实际条数比 deep 少，deep 才是最深源
    shallow = {k: v for k, v in list(shallow.items())[:watch - 5]}
    hist = dict(deep)
    hist.update(shallow)
    mod._rss_history = dict(hist)
    mod.RSS_SOURCES = []
    srcs = [{"key": "deep", "name": "deep", "cat": "ai", "color": "#fff", "tier": 1, "items": []},
            {"key": "shallow", "name": "shallow", "cat": "ai", "color": "#fff", "tier": 1,
             "items": []}]
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod._accumulate_history(srcs)
    printed = buf.getvalue()
    acc = mod._LAST_HISTORY_ACCOUNT
    assert acc.get("max_per_source") == len(deep), (
        "最深源统计错（%r vs %d）：像是把所有源并成了一个桶" % (
            acc.get("max_per_source"), len(deep)))
    assert acc.get("over_watch") == 1, "越警戒线的源数不对：%r" % acc.get("over_watch")
    # 播报里必须点出"是哪个源"越线 —— 审查变异体 F3 把源名恒写成 "-"，
    # 数字全对但唯一可行动的信息没了（报警却不知道该看谁）。
    deep_names = [ln for ln in printed.splitlines() if "每源深度" in ln]
    assert deep_names, "没播报每源深度这一行"
    assert "deep" in deep_names[0], (
        "播报没点出最深的那个源：%s" % deep_names[0][:160])


def test_watch_threshold_is_exact(clean):
    """警戒线要按 `>` 判：正好等于线不报，多一条才报。

    审查变异体 F1（`> watch` 改成 `>= watch`）此前无人守 —— 它不会造成错删，
    但会让"刚好贴着线"的健康源每场都挨一次假报警，报久了就没人看报警了。

    捕获用进程内 redirect_stdout，不用 capsys：本模块会重挂 sys.stdout，
    capsys 会漏掉部分打印（这个坑在 F3 那一轮已经把判据骗过去一次）。
    """
    import contextlib
    watch = mod.HISTORY_WATCH_PER_SOURCE

    def run(n):
        hist = _source_hist("thr", n, step=0.005)
        assert len(hist) == n
        mod._rss_history = dict(hist)
        mod.RSS_SOURCES = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod._accumulate_history([{"key": "thr", "name": "thr", "cat": "ai",
                                      "color": "#fff", "tier": 1, "items": []}])
        out = buf.getvalue()
        line = [l for l in out.splitlines() if "每源深度" in l]
        assert line, "没播报深度行"
        return mod._LAST_HISTORY_ACCOUNT.get("over_watch"), out.count("::warning"), line[0]

    n_over, w_over, l_over = run(watch + 1)
    assert (n_over, w_over) == (1, 1), "多一条就该报（over_watch=%r warning=%d）" % (n_over, w_over)
    n_eq, w_eq, l_eq = run(watch)
    assert (n_eq, w_eq) == (0, 0), \
        "正好等于警戒线却报了（over_watch=%r warning=%d）：%s" % (n_eq, w_eq, l_eq[:150])


def test_watch_does_not_mutate_entry_fields(clean):
    """哨兵只读：连"给条目加个键"都不许（加键会随历史进缓存、再随 dict(item) 进出厂 payload）。

    审查变异体 F8：`item["watch_seen"] = 1` 在只比 key 集合的判据下全绿。
    这里比完整条目，覆盖撤销上限时被删掉的那条全 payload 判据。
    """
    import copy
    hist = _source_hist("ro2", 300)
    before = copy.deepcopy(hist)
    got = dict(hist)
    mod._history_depth_watch(got, report=False)
    assert got == before, "哨兵改动了条目内容（新增/改写字段）：它只许看"


def test_all_depth_log_fields_are_accounted(clean):
    """四条账都要在日志里，且都不许 0 兜底 —— 审查 F5/F6 就是钻这两个空子。

    F5：`history_oldest_age_h` 整行从日志删掉，原判据的 want 元组里没有它 ⇒ 无人红。
    F6：`.get(k) or 0` 形式的兜底能躲过只看 `.get(k, 0)` 第二实参的检查。
    """
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    main = _fn(tree, "main")
    pairs = {}
    for node in ast.walk(main):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and \
                    k.value.startswith("history_"):
                pairs[k.value] = v
    want = ("history_expired", "history_max_per_source", "history_over_watch",
            "history_oldest_age_h")
    for key in want:
        assert key in pairs, "日志缺 %s（现有 %s）" % (key, sorted(pairs))
    names = {n.id for key in want for n in ast.walk(pairs[key]) if isinstance(n, ast.Name)}
    assert "_LAST_HISTORY_ACCOUNT" in names, "深度账没读 _LAST_HISTORY_ACCOUNT：%s" % sorted(names)
    for key in want:
        for call in ast.walk(pairs[key]):
            if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "get":
                assert len(call.args) == 1, "%s 用 .get(key, 默认值) 兜底" % key
            if isinstance(call, ast.BoolOp) and isinstance(call.op, ast.Or):
                bad = any(isinstance(v, ast.Constant) and v.value == 0 for v in call.values)
                assert not bad, "%s 用 `or 0` 兜底：没跑到与跑出了 0 又不可区分" % key
