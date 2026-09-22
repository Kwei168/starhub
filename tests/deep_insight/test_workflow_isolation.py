# tests/deep_insight/test_workflow_isolation.py
# -*- coding: utf-8 -*-
"""夜场工作流的隔离性与"绿勾不等于成功"守卫。

为什么单独一片：spec §4 的全部承诺都落在 YAML 里，而 YAML 没有单测就会漂。
现网每一条教训都对应下面一条断言 ——
1) update.yml 的 `cancel-in-progress: true`（:24）就是过去深度洞察被下一场砍掉的元凶；
   夜场若写错这一行，等于把同一个坑再挖一次，而且只在凌晨 4 点暴露。
2) update.yml:215/236 的 `git add` 清单里没有我们的路径 ⇒ 白天构建不会提交夜场产物，
   这是"纯新增"的正向证据；反过来若哪天有人把 daily-deep-* 加进那个清单，
   白天场的 checkout→build→add 就会用旧内容覆盖夜场的新内容。
3) Actions 默认 shell 是 `bash -e {0}`，没有 pipefail：`python ... | tee log` 的退出码
   是 tee 的（0），脚本崩了这场仍然绿。这正是 fetch_and_build 吞异常那个坑的 YAML 版。
4) `permissions: contents: read` 下 Data API 建 commit 必 403 —— 那是"只在上夜跑失败"的错。
"""
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NIGHT = os.path.join(ROOT, ".github", "workflows", "deep-insight.yml")
DAY = os.path.join(ROOT, ".github", "workflows", "update.yml")


def _raw(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _night():
    with open(NIGHT, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    # YAML 1.1 把裸 `on:` 解析成布尔 True，PyYAML 照做。两种键都要试，
    # 否则这个测试会因为读不到 triggers 而静默空跑（假绿）。
    trig = doc.get("on", doc.get(True))
    assert trig, "没读到 on/workflow_dispatch 段，判据本身失效"
    return doc, trig


def test_night_workflow_concurrency_is_its_own_group_and_never_cancels():
    doc, _ = _night()
    assert doc["concurrency"]["group"] == "deep-insight"
    assert doc["concurrency"]["cancel-in-progress"] is False, \
        "夜场必须排队而不是砍人：这是本次改造的立项目的"
    assert "cancel-in-progress: true" not in _raw(NIGHT)


def test_night_group_does_not_collide_with_daytime_group():
    """同名组 = 两条链互相取消，隔离承诺直接作废。"""
    doc, _ = _night()
    night_group = doc["concurrency"]["group"]
    day = yaml.safe_load(_raw(DAY))
    assert night_group != day["concurrency"]["group"]


def test_night_run_step_cannot_hide_script_failure_behind_tee():
    doc, _ = _night()
    step = [s for s in doc["jobs"]["deep"]["steps"] if s.get("name") == "Night deep insight run"][0]
    assert re.search(r"set -e[o]*p", step["run"]) or "pipefail" in step["run"], \
        "`python ... | tee` 无 pipefail 时退出码来自 tee，脚本崩了也是绿勾"


def test_night_publish_has_write_permission():
    """Data API 提交需要 contents:write；read 令牌只在凌晨失败，白天看不出来。"""
    doc, _ = _night()
    assert doc["permissions"]["contents"] == "write"


def test_daytime_commit_list_never_covers_nightly_artifacts():
    """阶段 1 纯新增：白天场的 git add 清单不许含夜场路径（含通配命中）。
    夜场现在有三个自己的路径；`predictions.jsonl` 尤其要紧 —— 白天场若把它按旧内容
    add 回去，对账历史会被一夜夜回滚。"""
    day = _raw(DAY)
    nightly = ("daily-deep-2026-09-23.json", "deep-insight.html", "predictions.jsonl")
    add_lines = [l for l in day.splitlines() if re.search(r"git add", l)]
    assert add_lines, "没读到 git add 清单，判据本身失效了"
    for line in add_lines:
        for glob in re.findall(r"[\w./-]*\*[\w./-]*", line):
            pat = glob.replace(".", r"\.").replace("*", ".*")
            for name in nightly:
                assert not re.fullmatch(pat, name), \
                    "白天场通配 %s 会覆盖夜场产物 %s" % (glob, name)
        for name in nightly:
            assert name not in line


def test_nightly_pipeline_absent_from_daytime_workflow():
    """夜场不许被挂进白天构建 —— 那正是被取消的那条老路。"""
    day = _raw(DAY)
    assert "build_deep_insight" not in day
    assert "deep-insight.yml" not in day


def test_nightly_purpose_defaults_to_test_not_publish():
    """手动 dispatch 忘了选 = 只出 artifact。误发布比漏发布贵得多。"""
    _, trig = _night()
    inputs = trig["workflow_dispatch"]["inputs"]
    assert inputs["purpose"]["default"] == "test"
    assert inputs["purpose"]["required"] is True


def test_missing_night_check_uses_beijing_date():
    """产物名是北京时间日期（night_run 里 UTC+8），按 UTC 减 20 小时会检查错的一天，
    于是"昨夜漏跑"永远报不出来 —— 一个恒绿的哨兵比没有哨兵更糟。"""
    raw = _raw(NIGHT)
    assert "20 hours ago" not in raw, "UTC 减 20h 落在前天，检的是错的日期"
    assert re.search(r"TZ=Asia/Shanghai date -d 'yesterday'", raw), \
        "缺夜哨兵必须按北京日取昨天"


def test_nightly_pulls_no_llamaindex_runtime_stack():
    """夜场读的是现网产物 + 标准库 HTTP，不碰 LlamaIndex/faiss/fastembed：
    那套依赖在 update.yml 里装失败过，而它那次是 continue-on-error 静默降级。
    装测试依赖（pytest/pyyaml）允许 —— 装不上就让夜场红，不许静默跳判据。"""
    doc, _ = _night()
    banned = ("llama-index", "llama_index", "faiss", "fastembed", "rank-bm25", "numpy")
    inst = " ".join((s.get("run") or "") for s in doc["jobs"]["deep"]["steps"] if s.get("run"))
    for b in banned:
        assert b not in inst, "夜场不该装 %s：那会把静默降级链引回来" % b


def test_nightly_preflights_its_own_judgements():
    """用户要求"单独测试和运行"：判据必须在花钱之前跑，且红就挡下整场。
    continue-on-error 会让这步变成装饰 —— 现网 Gate B 就是那样废掉的。"""
    doc, _ = _night()
    steps = doc["jobs"]["deep"]["steps"]
    test_steps = [s for s in steps if "tests/deep_insight" in (s.get("run") or "")]
    assert test_steps, "夜场没有跑自己的判据"
    assert not any(s.get("continue-on-error") for s in test_steps)
    run_idx = [i for i, s in enumerate(steps) if s.get("name") == "Night deep insight run"][0]
    assert min(i for i, s in enumerate(steps) if s in test_steps) < run_idx, \
        "判据跑在花钱之后 = 白跑"


def test_every_nightly_python_step_survives_the_pipe():
    """pipefail 只写在一个步骤上 = 另一个步骤照样能吞掉崩溃。"""
    doc, _ = _night()
    py = [s for s in doc["jobs"]["deep"]["steps"]
          if "build_deep_insight.py" in (s.get("run") or "")]
    assert py, "夜场没跑主脚本"
    for s in py:
        assert "pipefail" in s["run"], "%s 缺 pipefail" % s.get("name")


def test_nightly_retries_in_place_once():
    """spec §4 失败策略：当夜原地重试 1 次、不做白天补跑。
    checkpoint 存在的意义就在这儿 —— 重试不能把已完成的条目再烧一遍。"""
    doc, _ = _night()
    steps = doc["jobs"]["deep"]["steps"]
    run_idx = [i for i, s in enumerate(steps) if s.get("name") == "Night deep insight run"][0]
    retries = [s for i, s in enumerate(steps)
               if i > run_idx and "build_deep_insight.py" in (s.get("run") or "")]
    assert len(retries) == 1, "当夜原地重试应为 1 次，实为 %d" % len(retries)
    assert retries[0].get("if") == "failure()", "重试步必须只在上一次失败后跑"


def test_nightly_does_not_borrow_daytime_modules():
    """夜场不许 import 白天的洞察模块：那一串 import 会把 5000 行模块级副作用与
    llama-index 依赖引上夜路，正是 §4 隔离与"不装重依赖"要防的。
    （spec §3 原文要求复用 _SYS_ANALYST_PROMPT 等，已在 §3 修订说明里改判。）
    只看 import 语句：注释里大量引用白天代码的行号是有意留的证据链，不是依赖。"""
    src = _raw(os.path.join(ROOT, "build_deep_insight.py"))
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    for mod in ("build_daily_insight", "insight_engine", "build_rss_aggregator",
                "llama_index", "llama_index_core", "faiss", "numpy"):
        assert not any(i.split(".")[0] == mod for i in imports), \
            "夜场引了白天/重依赖模块 %s（现有 import：%s）" % (mod, imports)
    assert "importlib" not in imports, "用 importlib 绕过判据等于没有判据"


def test_no_raw_dispatch_input_reaches_the_shell():
    """本工作流带 contents:write，dispatch 输入是自由文本 ——
    把 `${{ github.event.inputs.* }}` 裸插值进 run 就是远程命令执行
    （`events_limit` 填 `12"; curl … | sh; #` 即可）。只允许经 env: 传值。"""
    doc, _ = _night()
    for s in doc["jobs"]["deep"]["steps"]:
        run = s.get("run") or ""
        if not run:
            continue
        for bad in ("github.event.inputs", "github.event_name"):
            assert bad not in run, "%s 把 %s 裸插值进了 shell" % (s.get("name"), bad)


def test_run_shell_blocks_actually_parse():
    """YAML 能解析不代表 shell 能跑：case 模式里写 `(*[!0-9]*)` 这种 zsh 习惯，
    bash 会当成两个分支，只有 CI 上才炸。这里对每段带 `set -` 的 run 直接跑 bash -n。"""
    import shutil
    import subprocess
    import tempfile

    bash = shutil.which("bash")
    assert bash, "本机没有 bash，本判据会空跑"
    doc, _ = _night()
    checked = 0
    for s in doc["jobs"]["deep"]["steps"]:
        run = s.get("run") or ""
        if "set -" not in run:
            continue
        checked += 1
        fd, path = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(run)
        r = subprocess.run([bash, "-n", path], capture_output=True, text=True)
        os.remove(path)
        assert r.returncode == 0, "%s 的 shell 语法不过：%s" % (s.get("name"), r.stderr[:200])
    assert checked >= 2, "只检查了 %d 段脚本，判据形同虚设" % checked
