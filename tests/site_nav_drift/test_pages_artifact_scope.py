# -*- coding: utf-8 -*-
"""A3（advisory）：Pages 制品里不许有非站点文件——在合成树上**真跑** Stage 正文。

为什么要真跑而不是 grep 文本：本仓反复栽在"读配置当读行为"（`git check-ignore` 不带 --no-index、
`ls-files` 不带 -z、门禁 B 恒红却报绿……都是口径与行为不一致）。制品面这条同理：
只有把 update.yml 里那段 shell 拿出来在合成目录跑一遍，数出来的"制品里有什么"才是它真正的行为。

现状（2026-10-02 实测）：Stage 步用 `git ls-files -z | grep -zv -E '(^|/)[._]'` 全量 rsync，
除了 `.`/`_` 前缀之外不设限 ⇒ tests/ 144 个、tools/ 26 个、根目录 .py、build_logs/ 14.3 MiB
都随站点公开（`curl` 现取：`build_logs/2026-10-02.jsonl` 线上 200 / 237 KB、`fetch_and_build.py` 200）。
用户批准的收窄范围＝tests/tools/根目录 .py/build_logs/；**`api/` 单独等点头**
（见 memory: vercel-pages-hosting-split，用户定案是入口就是 Pages、Vercel 只当 API 主机，
所以现在不能擅自把 api/ 关掉）。

判据是双向的：既要求非站点件不在制品里，也要求站点自身的东西一个都不能少 ——
只关不留会把"收窄"做成"砍站点"。
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.environ.get("STARHUB_UPDATE_YML") or os.path.join(ROOT, ".github", "workflows", "update.yml")

SITE = ["index.html", "ai-daily.html", "rss-aggregator.html", "daily-insight-history.html",
        "rss-data-0.js", "rss-data-1.js", "hot_snapshot.json",
        "rss_sources.json", "known_categories.json"]
NON_SITE = ["build_rss_aggregator.py", "fetch_and_build.py", "insight_engine.py",
            "tests/rss_history/test_pages_deploy_wiring.py",
            "tools/data_api_push.py",
            "build_logs/2026-10-02.jsonl",
            "docs/insight-pipeline-flow.md"]
# api/ 刻意不在任何一侧：它的处置等用户点头，判据不替用户做决定


def _stage_body():
    with open(WF, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            name = step.get("name", "")
            if name.startswith("Stage Pages site") and step.get("run"):
                return step["run"]
    raise AssertionError("找不到 Stage Pages site 步骤（workflow 改名了？判据要跟着改）")


def _tree(tmp):
    """造一个能跑的合成仓：站点件 + 非站点件 + 生成端会补的新鲜产物。"""
    subprocess.run(["git", "init", "-q", "."], cwd=tmp, check=True)
    for k, v in (("user.name", "gate"), ("user.email", "gate@example.invalid"),
                 ("commit.gpgsign", "false")):
        subprocess.run(["git", "config", k, v], cwd=tmp, check=True)
    for rel in SITE + NON_SITE:
        p = os.path.join(tmp, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x" * 64)
    subprocess.run(["git", "add", "-f", "--", "."], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=tmp, check=True)
    return tmp


def _needs_rsync(body):
    """正文是否**真的调用** rsync（只看非注释行）。

    第一版直接 "rsync" in body —— 结果被自己新写的注释（"换成 cp 而不是继续 rsync"）骗过去，
    两条主判据在收窄已经落地之后仍然报 skip。判据读的是行为，不能读关键词。
    """
    for ln in body.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if re.search(r"\brsync\b", s):
            return True
    return False


def _run_stage(tmp):
    body = _stage_body()
    if _needs_rsync(body) and shutil.which("rsync") is None:
        pytest.skip("正文还在调用 rsync 而这台机器没有 rsync ⇒ 这条只能到 CI 验；"
                    "不能把'工具缺失'读成'没有泄漏'")
    r = subprocess.run(["bash", "-e", "-c", body], cwd=tmp, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, "Stage 正文在合成树上就没跑通：%s\n%s" % (
        r.stdout[-400:], r.stderr[-400:])
    out = []
    for base, _dirs, files in os.walk(os.path.join(tmp, "_pages")):
        for f in files:
            out.append(os.path.relpath(os.path.join(base, f), os.path.join(tmp, "_pages"))
                       .replace(os.sep, "/"))
    return set(out)


@pytest.fixture()
def staged(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("没有 git，无法造合成仓")
    return _run_stage(_tree(str(tmp_path)))


def test_non_site_files_are_not_published(staged):
    leaks = sorted(p for p in staged
                   if p.endswith(".py") or p.startswith(("tests/", "tools/", "build_logs/", "docs/")))
    assert not leaks, "这些非站点文件随制品公开了：%s" % leaks[:8]


def test_site_files_are_still_published(staged):
    missing = [p for p in SITE if p not in staged]
    assert not missing, "收窄把站点自己的文件也砍掉了：%s" % missing
    assert any(p.startswith("rss-data-") for p in staged), "分块没进制品，首页会没数据"


def test_needs_rsync_reads_invocations_not_comments():
    """上面那个启发式自己的判据：注释里提 rsync 不许触发 skip（我第一版就是这么被骗的）。"""
    assert _needs_rsync("git ls-files -z | rsync -a --files-from=- ./ _pages/\n") is True
    assert _needs_rsync("# 换成 cp 而不是继续 rsync\ncp -f x _pages/\n") is False
    assert _needs_rsync("echo rsyncless\n") is False


def test_the_probe_bites_on_a_blanket_copy(tmp_path):
    """反空转（也是实现前的红）：把正文换成"跟踪文件整拷"，同一套断言必须判红。

    少了这条，`test_non_site_files_are_not_published` 有可能只是因为合成树里根本没建那些文件
    而"绿"——那是空集自证。这里用 `cp --parents` 而不是 rsync，好让没有 rsync 的机器也能验。
    """
    d = _tree(str(tmp_path))
    body = ("mkdir -p _pages\n"
            "git ls-files -z | grep -zv -E '(^|/)[._]' | xargs -0 -r cp --parents -t _pages/\n")
    r = subprocess.run(["bash", "-e", "-c", body], cwd=d, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, "对照组正文自己就没跑通：%s" % r.stderr[-200:]
    got = set()
    for base, _dirs, files in os.walk(os.path.join(d, "_pages")):
        for f in files:
            got.add(os.path.relpath(os.path.join(base, f), os.path.join(d, "_pages"))
                    .replace(os.sep, "/"))
    leaks = sorted(p for p in got
                   if p.endswith(".py") or p.startswith(("tests/", "tools/", "build_logs/")))
    assert leaks, "对照组居然没泄漏 ⇒ 合成树没建非站点文件，主判据是在空集上跑"
    assert {"build_rss_aggregator.py", "tools/data_api_push.py",
            "build_logs/2026-10-02.jsonl"} <= set(leaks), leaks
