# -*- coding: utf-8 -*-
"""侧栏快照判据：快车道不得把首页的排行榜/关注动态覆盖成空态。

线上实锤（2026-10-04 18:01，Pages 域）：`const TRENDING = {};`、`let FEED = [];`，
而同一天的 17:00 小时场日志是 `[AI摘要] enabled, rising=20` ⇒ 数据本来有。
根因：fast_refresh.py 调 build_index_html 时只传 out/CATS，不传 trending/feed/ai_summary，
而渲染函数对缺省值的行为就是"渲染空态"。快车道每 15 分钟一场，只要那一场有新星就会把
小时场的完整首页覆盖成空态版，直到下一个整点才自愈。它一直存在，只是快车道今天才第一次
真正发布过（无新星崩溃路径修好之后），所以今天才显形。

修法用一份跨场侧栏快照（sidebar_snapshot.json）走**独立缓存族**：
  · 不能塞进 starhub-state 的 path 清单——改 path 清单＝换族＝当场冷启动，
    translations.json 丢了要重译 ~8400 条、analysis_snapshot.json 丢了每场重跑 LLM 分析；
  · trending_snapshot.json 不能复用——它是 {全名: 今日星数} 的基线，不是榜单结果。

本文件钉五条：小时场写全三键、快车道 restore 到就回填、restore 不到就**别发空态**
（不写 index.html，让 Stage 现成的 publish=false 干净跳过——但状态表照写，新星不丢）、
这一族必须被 trim 管住只留 1 份（GitHub 的 cache/save 对已存在键是跳过不是覆盖，
所以键随场变化 + 修剪保留 1 才是"新覆盖旧"）、以及这个每场重写件既不进 git 也不上线。
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF_FAST = os.path.join(ROOT, ".github", "workflows", "star-fast.yml")
WF_UPDATE = os.path.join(ROOT, ".github", "workflows", "update.yml")
SNAP = "sidebar_snapshot.json"


def _fab():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import fetch_and_build as fab
    return fab


def _text(path):
    return io.open(path, encoding="utf-8").read()


# ── 1. 小时场必须把三键写全 ─────────────────────────────────────────────────
def test_sidebar_payload_carries_all_three_sections():
    """快照必须同时带 trending / feed / ai_summary_html——少一个就还有一栏会空。"""
    fab = _fab()
    payload = fab.sidebar_payload(
        {"rising": [{"full_name": "a/b"}], "total": [], "new": []},
        [{"full_name": "c/d"}],
        '<div class="ai-summary">摘要</div>')
    assert set(payload) >= {"trending", "feed", "ai_summary_html"}, \
        "快照缺键，实得 %s" % sorted(payload)
    assert payload["trending"]["rising"][0]["full_name"] == "a/b"
    assert payload["feed"][0]["full_name"] == "c/d"
    assert "摘要" in payload["ai_summary_html"]


def test_hourly_build_persists_sidebar_snapshot():
    """主链要把快照落盘（只在 stars_ok 分支里写：拉取失败那版数据不可信，不能污染下一场）。"""
    src = _text(os.path.join(ROOT, "fetch_and_build.py"))
    assert SNAP in src, "主链没写 %s，快车道永远 restore 不到东西" % SNAP


# ── 2/3. 快车道的两条路径（真跑，不读文本）────────────────────────────────────
def _drive(tmp_path, with_snapshot):
    """在临时目录里真跑 fast_refresh.main()：复制代码与表，网络与 LLM 全部替换掉。

    为什么必须实跑：这条链的失败形状是"页面照样发布、内容却是空的"——文本判据看不见，
    只有跑一遍看生成的 index.html 才知道回填有没有生效。
    """
    import shutil
    if shutil.which("git") is None:
        sys.path.insert(0, os.path.join(ROOT, "tests"))  # noqa: E402
        import pytest
        pytest.skip("本机没有 git")
    for rel in ("fast_refresh.py", "fetch_and_build.py", "template.html",
                "known_categories.json", "known_notes.json"):
        shutil.copyfile(os.path.join(ROOT, rel), os.path.join(str(tmp_path), rel))
    if with_snapshot:
        json.dump({"trending": {"rising": [{"full_name": "x/one", "stars": 12}],
                                "total": [], "new": []},
                   "feed": [{"full_name": "y/two"}],
                   "ai_summary_html": '<div class="ai-summary">摘要</div>'},
                  io.open(os.path.join(str(tmp_path), SNAP), "w", encoding="utf-8"),
                  ensure_ascii=False)
    driver = tmp_path / "_driver.py"
    driver.write_text(
        "import json, os, sys\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "sys.path.insert(0, here)\n"
        "import fast_refresh as fr\n"
        "fr.fab.fetch_stars = lambda token: [\n"
        "  {'full_name': 'n/newstar', 'description': 'new repo', 'language': 'Go', 'topics': []},\n"
        "  {'full_name': 'x/one', 'description': 'old', 'language': 'Python', 'topics': []},\n"
        "]\n"
        "fr.fab.classify_repo = lambda fn, d, l, t, k: ('agent', '一句话点评')\n"
        "fr.fab.translate_to_zh = lambda s: s\n"
        "fr.fab.fetch_readme_summary = lambda fn, token: ''\n"
        "os.environ['GITHUB_TOKEN'] = 'fake'\n"
        "print('RC', fr.main())\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(driver)], cwd=str(tmp_path),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, "driver 崩了：%s%s" % ((r.stdout or "")[-400:], (r.stderr or "")[-500:])
    return r.stdout or ""


def test_fast_lane_backfills_trending_and_feed(tmp_path):
    """restore 到快照 ⇒ 生成的首页里 TRENDING/FEED 必须带内容，且新星也在页面上。"""
    _drive(tmp_path, with_snapshot=True)
    page = tmp_path / "index.html"
    assert page.exists(), "有新星却没生成 index.html"
    h = page.read_text(encoding="utf-8")
    # 不钉 const/let：TRENDING 已改成 let（注入化要能替换它），抓手只认赋值本身。
    m = re.search(r"(?:const|let) TRENDING = (.{0,60})", h)
    assert m and m.group(1).strip().startswith('{"'), "TRENDING 仍是空对象：%s" % (m and m.group(1))
    assert "x/one" in h, "快照里的排行榜条目没进页面"
    assert re.search(r"let FEED = \[\{", h), "FEED 没回填（关注动态仍会空）"
    assert "n/newstar" in h, "新星本身要上线，这是快车道的存在意义"
    assert "data-attention" not in h or "attn-row" in h  # 提醒块与侧栏互不影响


def test_fast_lane_does_not_publish_empty_sidebar(tmp_path):
    """restore 不到快照 ⇒ 不写 index.html（让 Stage 现成的 publish=false 干净跳过），
    但状态表必须照写：新星要入库，否则下一场又当新星重烧一次 LLM。"""
    out = _drive(tmp_path, with_snapshot=False)
    page = tmp_path / "index.html"
    assert not page.exists(), (
        "没有侧栏快照却生成了 index.html ⇒ 快车道会把首页覆盖成空态（18:01 的线上事故形状）")
    assert ("侧栏" in out) or ("sidebar" in out.lower()), (
        "没发布页面必须留一行说明原因的话，否则日志里分不清「没新星」和「有新星但缺快照」")
    kc = json.loads((tmp_path / "known_categories.json").read_text(encoding="utf-8"))
    assert "n/newstar" in kc, "不发布页面可以，但新星必须进表——否则下场重新 diff 再烧 LLM"


# ── 4. 这一族必须被 trim 管住（用户明确要求：新的覆盖旧的，不许无限攒）──────────
def test_sidebar_cache_family_is_trimmed_to_one():
    src = _text(WF_UPDATE)
    m = re.search(r"--keep\s+starhub-sidebar=(\d+)", src)
    assert m, "starhub-sidebar 族没进 trim 清单 ⇒ 每小时攒一个键，无限增长"
    assert m.group(1) == "1", (
        "这一族只服务「取上一场那份」，保留 %s 份没意义；GitHub 的 cache/save 对已存在键"
        "是跳过不是覆盖，所以只能靠键随场变化 + 修剪保留 1 来实现「新覆盖旧」" % m.group(1))
    # 反向：族名不许写成会同时吃掉两族的公共前缀
    assert "--keep starhub=" not in src and "--keep starhub " not in src, \
        "族名写成 starhub 会连 starhub-state 一起匹配（_family_of 取最长匹配），一删就冷启动"


def test_fast_lane_restores_sidebar_before_generating_page():
    fast = _text(WF_FAST)
    assert SNAP in fast, "快车道没有 restore/读取 %s 的接线" % SNAP
    i_restore = fast.find("starhub-sidebar")
    i_fast = fast.find("name: Fast refresh")
    assert 0 <= i_restore < i_fast, "restore 必须在生成页面之前，否则读不到快照"
    # 必须靠前缀命中：快车道的完全键含自己的 run_id，而它不 save ⇒ 完全键必然 miss。
    # 少了 restore-keys，这一步就永远取不到小时场那份 ⇒ 快车道永远不发布首页，
    # 而 continue-on-error 会让这件事全程静默（变异 V2 实测：删掉它原判据照样绿）。
    m = re.search(r"restore-keys:\s*\|\s*\n\s*(starhub-sidebar-\$\{\{\s*runner\.os\s*\}\}-)", fast)
    assert m, "restore 步缺 restore-keys 前缀 ⇒ 快车道永远命中不到小时场那份快照"


# ── 5. 每场重写件：既不进 git 也不上线 ────────────────────────────────────────
def test_sidebar_snapshot_stays_out_of_git_and_site():
    ign = _text(os.path.join(ROOT, ".gitignore"))
    assert SNAP in ign, "%s 每场重写，进 git 就是把历史膨胀写回仓库" % SNAP
    for path in (os.path.join(ROOT, "tests", "rss_history", "test_pages_deploy_wiring.py"),
                 os.path.join(ROOT, "tests", "site_nav_drift", "test_noncode_not_tracked.py")):
        if os.path.exists(path):
            assert SNAP not in _text(path), \
                "%s 不该出现在发布白名单里（它是构建期中间件，不是站点件）" % SNAP
