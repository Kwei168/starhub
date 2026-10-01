# -*- coding: utf-8 -*-
"""不许出现"写着但从不跑"的孤儿测试目录。

为什么钉这条（2026-10-01 实测）：`tests/rss_translate/` 里有运行时翻译守卫与翻译引擎判据，
但 `grep -rl rss_translate .github/workflows/` 是 **0 命中** —— 也就是说翻译链的回归
可以完全静默落地，而我一直以为"有测试挡着"。同形状的孤儿还有 rss_composite / rss_date /
rss_sort / tools / trim_guard，共 6 个目录。

判据分两层，缺一层都会假绿：
  ① 必须挡住的目录，要真的出现在 A2（blocking）那条 pytest 命令里；
  ② 其余含 `test_*.py` 的目录必须在 UNWIRED 里点名并写原因 ——
     新增目录却忘了接线时，这条会红，而不是又多一个静默孤儿。
"""
import os
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.environ.get("STARHUB_UPDATE_YML") or os.path.join(ROOT, ".github", "workflows", "update.yml")

# 必须进 blocking 闸的目录（都是"回归会静默上线"的那类）。
# 不含 trim_guard：它排练的是 repo-trim.yml（真跑 git-filter-repo），ubuntu 行为未验证，
# 放进每场构建的 blocking 闸就是我上次"自己把整场冻掉"的形状 —— 它已挂到 repo-trim.yml 里。
MUST_BLOCK = ["tests/rss_history/", "tests/rss_source_coverage/", "tests/site_nav/",
              "tests/rss_translate/"]

# 已知未接线的目录 + 原因。别顺手往里加：每一条都意味着一类无人监督的判据。
# 原因必须自立——写"同上"的人（我）过不了 test_unwired_entries_are_explained。
UNWIRED = {
    "rss_composite": "脚本风格（模块级 sys.exit），pytest 收集即 INTERNALERROR；要接先得改造成 test 函数",
    "rss_date": "脚本风格：文件末尾 sys.exit(0)，被 pytest 当测试模块导入会打崩整场收集",
    "rss_sort": "单文件脚本风格，同样是 import 期执行 + sys.exit；改造前不进闸",
    "tools": "本地推送工具判据（CI 不调用 data_api_push），本机 182s —— 不值得每场构建都跑",
}


def _a2_cmd():
    with open(WF, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    for st in doc["jobs"]["update"]["steps"]:
        name = st.get("name") or ""
        if name.startswith("Quality gate A2"):
            return st.get("run") or ""
    pytest.fail("update.yml 里找不到 Quality gate A2 步骤：%s" % WF)


def _referenced_dirs():
    """任何 workflow 文本里出现过的 `tests/<dir>` 都算"已接线"。

    不能只盯 A2：daily_insight 归 B 闸、site_nav_drift 归 A3，它们不是孤儿。
    """
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    refs = set()
    for fn in os.listdir(wf_dir):
        if not fn.endswith((".yml", ".yaml")):
            continue
        text = open(os.path.join(wf_dir, fn), encoding="utf-8").read()
        refs |= set(re.findall(r"tests/([A-Za-z0-9_]+)", text))
    return refs


def test_required_dirs_are_actually_run_by_the_blocking_gate():
    cmd = _a2_cmd()
    missing = [d for d in MUST_BLOCK if d not in cmd]
    assert not missing, (
        "这些目录的判据不在 blocking 闸里，回归会静默上线：%s（A2 命令：%s）" % (missing, cmd))


def test_no_new_orphan_test_directory():
    """含 test_*.py 的目录要么被某个 workflow 引用，要么在 UNWIRED 里点名并给原因。"""
    tests_dir = os.path.join(ROOT, "tests")
    present = set()
    for d in os.listdir(tests_dir):
        p = os.path.join(tests_dir, d)
        if not os.path.isdir(p):
            continue
        if any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(p)):
            present.add(d)
    unknown = sorted(present - _referenced_dirs() - set(UNWIRED))
    assert not unknown, (
        "这些测试目录既没被任何 workflow 引用、也没在 UNWIRED 里说明原因（= 新的静默孤儿）：%s" % unknown)


def test_unwired_entries_are_explained():
    bad = [d for d, why in UNWIRED.items() if len(why) < 12]
    assert not bad, "UNWIRED 里这些条目没有像样的原因：%s" % bad
