# -*- coding: utf-8 -*-
"""T4 快车道 workflow 判据（A3 advisory）。

架构原则（用户裁决 2026-10-03）：功能解耦——star 车道是独立功能单元，
不与 RSS 深度捆绑，不引入新的无限膨胀源。本文件钉住：
- 独立 concurrency 组（绝不取消小时场 starhub-update）；
- */15 schedule（cron-job.org mode=star 为主力的兜底）；
- if-no-files-found: error（§8.15 空制品绿发布教训）；
- 解耦红线：不引用 rss-data-1.js（已退役的 55MB 分块机制）；
- 制品不变量：index.html 是唯一硬必在项，其余入口带回 404 容忍（下架不拖死车道）；
- fast_refresh 被 GITHUB_TOKEN 注入调用；deploy 依赖 upload outcome（残缺制品防线）。
文本断言（不引 YAML 依赖）。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 变异电池（tools/mut_push_retry.py）在临时副本上跑，靠这个注入点指向被变异的 yml；
# 不设就用真实文件，判据平时读的就是它。
WF = os.environ.get("STAR_FAST_YML") or os.path.join(ROOT, ".github", "workflows", "star-fast.yml")


def _wf_text():
    with open(WF, encoding="utf-8") as f:
        return f.read()


def test_workflow_exists_with_dispatch_and_schedule():
    yml = _wf_text()
    assert "workflow_dispatch" in yml
    assert re.search(r'cron:\s*"\*/15 \* \* \* \*"', yml), "15 分钟兜底 schedule 必须在"


def test_concurrency_group_is_independent():
    yml = _wf_text()
    m = re.search(r"concurrency:\s*\n\s*group:\s*(\S+)", yml)
    assert m and m.group(1) == "starhub-fast", "concurrency 组必须是独立的 starhub-fast"
    # 反向：concurrency 组名绝不许是小时场的组（互取消 = RSS 断供）
    assert m.group(1) != "starhub-update"


def test_upload_rejects_empty_artifact():
    yml = _wf_text()
    assert "if-no-files-found: error" in yml
    assert re.search(r"steps\.pages_upload\.outcome == 'success'", yml), "deploy 必须依赖 upload outcome"


def test_decoupling_no_retired_rss_chunks():
    yml = _wf_text()
    assert "rss-data-1.js" not in yml, "rss-data-1.js（55MB 分块）已退役，快车道不得引用"
    # rss-data-0.js 只允许出现在"带回清单"（404 容忍语义），不许是必点名硬失败
    must_lines = [l for l in yml.splitlines() if "for must in" in l or "硬必在" in l]
    for line in must_lines:
        assert "rss-data" not in line, "带回清单之外的 rss-data 引用都会把退役机制重新绑回 star 车道"


def test_index_html_is_the_only_hard_requirement():
    """无新星 = fast_refresh 零写入 = 工作区无 index.html——这是【正常路径】，
    必须以 publish=false 干净跳过发布（线上保持上一版制品），而不是 cp 报错 +
    continue-on-error 吞一场红字（2026-10-04 用户在 Actions 看到的每 15 分钟噪音）。"""
    yml = _wf_text()
    stage = yml.split("Stage star page over live site", 1)[1]
    # 缺 index.html 的路径：先存在性检查（不许 cp 先炸）、notice 语义、置 publish=false、exit 0
    assert re.search(r"\[ ! -s index.html \]", stage), "必须先做存在性检查，不许让 cp 当探测员（set -e 下 cp 先炸）"
    assert "::notice::" in stage and "publish=false" in stage, "无新星必须 notice + publish=false 干净跳过"
    assert "continue-on-error: true" not in stage, "不再需要兜底吞错——缺文件走正常 false 路径，真缺陷应当场红"
    # 带回文件失败是 warning（下架容忍），不是 error
    assert re.search(r'::warning::线上无 \$f', stage), "带回失败必须走 warning（下架不拖死车道）"
    for f in ("ai-daily.html", "rss-aggregator.html", "daily-insight-history.html"):
        assert f in stage, "入口页带回清单缺 %s（下架语义覆盖不了它了）" % f


def test_upload_depends_on_publish_flag():
    """upload 只在 stage 真产出时跑（publish=true 门），deploy 依旧依赖 upload outcome——
    双闸保住 §8.15「空制品绿发布抹平站点」的红线。"""
    yml = _wf_text()
    upload = yml.split("Upload Pages artifact", 1)[1].split("Deploy to GitHub Pages", 1)[0]
    assert "steps.stage.outputs.publish == 'true'" in upload, "upload 必须被 publish 标志门住"
    assert "if-no-files-found: error" in yml, "空制品防线不撤"
    deploy = yml.split("Deploy to GitHub Pages", 1)[1].split("Mark the run red", 1)[0]
    assert "steps.pages_upload.outcome == 'success'" in deploy, "deploy 必须依赖 upload outcome"


def test_fast_refresh_called_with_token():
    yml = _wf_text()
    assert "python fast_refresh.py" in yml
    m = re.search(r"Fast refresh.*?env:.*?GITHUB_TOKEN: \$\{\{ secrets\.GITHUB_TOKEN \}\}", yml, re.S)
    assert m, "fast_refresh 必须带 GITHUB_TOKEN（匿名限流=旧页静默上线的雷）"


def test_timeout_cap_present():
    yml = _wf_text()
    assert re.search(r"timeout-minutes:\s*12", yml), "快车道超 12 分钟即无意义，必须封顶"


def test_refresh_js_star_mode_dispatch():
    """T5：api/refresh.js 的 ?mode=star 分流——白名单映射（防任意 workflow 注入）、
    star → star-fast.yml、默认 → update.yml。"""
    src = open(os.path.join(ROOT, "api", "refresh.js"), encoding="utf-8").read()
    assert "WORKFLOW_BY_MODE" in src
    assert re.search(r"star:\s*'star-fast\.yml'", src)
    assert re.search(r"''\s*:\s*'update\.yml'", src)
    assert "workflows/' + workflow" in src, "dispatch URL 必须用映射出的 workflow 名"
    assert "未知 mode" in src, "未知 mode 必须 400 拒绝"


def test_commit_step_adds_only_tracked_state_files():
    """descriptions_zh.json 已进 starhub-state 缓存家族（.gitignore + 出 git 树）——
    star-fast 的 git add 还按旧"三件套"清单 ⇒ set -e 下当场红，且新星场的分类结果
    提交不出去 ⇒ 每 15 分钟循环炸（下一场重新检测同一新星再炸，白烧 LLM）。
    2026-10-04 03:0x 实锤。钉：add 清单只许仍被跟踪的两个状态文件，
    且任何 .gitignore 排除的名字不得出现（泛化守卫，防下一批摘名再犯）。"""
    yml = _wf_text()
    ign = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    commit = yml.split("Commit star state if changed", 1)[1].split("- name: Stage star page", 1)[0]
    all_added = " ".join(re.findall(r"git add (.+)", commit))
    assert "known_categories.json" in all_added and "known_notes.json" in all_added, \
        "两个仍被跟踪的状态文件必须在 add 清单"
    assert "descriptions_zh.json" not in all_added, "descriptions_zh.json 已出 git 树，add 它必红"
    ignored = {l.strip() for l in ign.splitlines() if l.strip() and not l.strip().startswith("#")}
    for path in re.findall(r"[\w./-]+\.\w+", all_added):
        assert path not in ignored, "%s 在 .gitignore 里，不得出现在 star-fast 的 add 清单" % path


# ── 撞车重试的**行为**判据：读文本只证明"写了"，跑一遍才证明"跑得通" ──────────
# 为什么必须实跑：Commit 步的放弃分支是 `|| echo warning`（放弃优于挡发布），所以它坏成
# "从没重试过"或"撞车即崩"都不会让整场变红——文本对了不代表 fetch 的 refspec、merge 的 --no-edit、
# 二次 push 的目标分支任何一处写错都能让"重试"形同不存在而全程静默。
# 这里在临时目录里建本地裸仓当远端，全程不碰网络、不碰 GitHub。
COMMIT_STEP_MARK = "Commit star state if changed"
_BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
_ME = ("Kwei168", "83650072+Kwei168@users.noreply.github.com")


def _commit_shell(tmp_path):
    """抽出 Commit 步的 run 正文，去掉 YAML block scalar 的公共缩进后落成可执行脚本。"""
    yml = _wf_text()
    seg = yml.split(COMMIT_STEP_MARK, 1)[1].split("- name: Stage star page", 1)[0]
    lines = seg.split("run: |", 1)[1].rstrip("\n").splitlines()
    ind = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    sh = tmp_path / "commit_step.sh"
    sh.write_text("\n".join(l[ind:] if l.strip() else "" for l in lines) + "\n", encoding="utf-8")
    return str(sh)


def _g(repo, *args):
    import subprocess
    r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, " ".join(args) + " 失败：" + ((r.stderr or "") + (r.stdout or ""))[:400]
    return (r.stdout or "").strip()


def _clone(url, here, who):
    import subprocess
    subprocess.run(["git", "clone", "-q", url, here], check=True)
    _g(here, "config", "user.name", who[0])
    _g(here, "config", "user.email", who[1])


def _stage(tmp_path, other_file=None, other_content=None):
    """origin 裸仓 → seed 建 main → work（本场，新星已写进 known_categories）
    → 可选 other（别人抢先推一个提交）。返回 work 路径。"""
    import subprocess
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    # 裸仓的 HEAD 默认指 master，而 CI 的远端默认分支是 main：不改的话 clone 出来是空工作树
    # （git 会报 "remote HEAD refers to nonexistent ref"），后面的 git add 就找不到文件。
    _g(str(origin), "symbolic-ref", "HEAD", "refs/heads/main")

    seed = str(tmp_path / "seed")
    _clone(str(origin), seed, _ME)
    # 分支必须对齐 CI：actions/checkout 出来就是 main 且跟踪 origin/main，而 clone 空裸仓
    # 得到的是 init.defaultBranch（本机常是 master）⇒ 无参数 git push 会推去 master 被拒。
    _g(seed, "checkout", "-q", "-b", "main")
    (tmp_path / "seed" / "known_categories.json").write_text('{"a/one": "agent"}\n', encoding="utf-8")
    (tmp_path / "seed" / "known_notes.json").write_text('{"a/one": "一句话"}\n', encoding="utf-8")
    (tmp_path / "seed" / "other.json").write_text('{"x": 1}\n', encoding="utf-8")
    _g(seed, "add", "known_categories.json", "known_notes.json", "other.json")
    _g(seed, "commit", "-qm", "seed")
    _g(seed, "push", "-q", "-u", "origin", "main")

    work = str(tmp_path / "work")
    _clone(str(origin), work, _BOT)
    (tmp_path / "work" / "known_categories.json").write_text(
        '{"a/one": "agent", "b/new": "tools"}\n', encoding="utf-8")
    (tmp_path / "work" / "fast.log").write_text("[fast] 新星 1 条：b/new\n", encoding="utf-8")

    if other_file:
        other = str(tmp_path / "other")
        _clone(str(origin), other, _ME)
        (tmp_path / "other" / other_file).write_text(other_content, encoding="utf-8")
        _g(other, "add", other_file)
        _g(other, "commit", "-qm", "chore: auto update stars")
        _g(other, "push", "-q", "origin", "main")
    return work


def _run_commit(work, sh, tmp_path):
    import subprocess
    out = tmp_path / "gh_output"
    out.write_text("", encoding="utf-8")
    r = subprocess.run(["bash", "-e", sh], cwd=work, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, "GITHUB_OUTPUT": str(out)})
    return r, out.read_text(encoding="utf-8")


def _need_bash():
    import shutil
    import pytest
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("本机缺 bash/git：这段 shell 的行为只能到 CI 的 ubuntu 上验")


def test_star_fast_lands_after_a_clean_collision(tmp_path):
    """别人先推了一个不冲突的提交 ⇒ 重试必须把本场提交真的送上去，而且不许报警。"""
    _need_bash()
    sh = _commit_shell(tmp_path)
    work = _stage(tmp_path, "other.json", '{"x": 2}\n')
    r, gh = _run_commit(work, sh, tmp_path)
    assert r.returncode == 0, "撞车场整步非零退出：%s%s" % ((r.stdout or "")[-500:], (r.stderr or "")[-500:])
    assert "被拒" not in (r.stdout or ""), "干净撞车却走了放弃分支 ⇒ 重试链没打通"
    log = _g(work, "log", "--oneline", "-10", "origin/main")
    assert "fast refresh stars" in log, "本场提交没进远端 ⇒ 所谓重试形同不存在"
    assert "auto update stars" in log, "别人的提交被覆盖掉了 ⇒ 重试不该丢别人的东西"
    _g(work, "fetch", "-q", "origin", "main", "--depth=50")
    assert "b/new" in _g(work, "show", "origin/main:known_categories.json"), (
        "远端分类表里没有本场新星 ⇒ 结果没落库，下一场会重新 diff 出来再烧一次 LLM")
    assert "changed=" in gh, "$GITHUB_OUTPUT 必须写 changed 信号，否则 Stage 步只能靠猜"


def test_star_fast_survives_a_merge_conflict(tmp_path):
    """别人改的是同一个 known_categories.json ⇒ 合并必冲突：这一步必须零退出并留下可读警告。
    放弃优于挡发布，但绝不能把每 15 分钟一场变成连片红（§8.24 那类吓人的红错正是这么长出来的）。"""
    _need_bash()
    sh = _commit_shell(tmp_path)
    work = _stage(tmp_path, "known_categories.json", '{"a/one": "agent", "c/other": "info"}\n')
    r, gh = _run_commit(work, sh, tmp_path)
    assert r.returncode == 0, "merge 冲突把整步炸了：%s%s" % ((r.stdout or "")[-500:], (r.stderr or "")[-500:])
    assert "被拒" in (r.stdout or ""), (
        "放弃提交却没打警告 ⇒ 日志里分不清「没撞车」和「撞了但放弃」，等于静默漏发")
    log = _g(work, "log", "--oneline", "-10", "origin/main")
    assert "fast refresh stars" not in log, "冲突没解决却把提交推了上去 ⇒ 会覆盖别人的分类结果"
    assert "changed=" in gh


def test_star_fast_clean_push_skips_the_retry(tmp_path):
    """没人抢推时一次 push 就走完：不许走重试分支、不许多出一个 merge 提交
    （反向那半——防止"永远重试"把每场白涨一个提交的历史膨胀带回来）。"""
    _need_bash()
    sh = _commit_shell(tmp_path)
    work = _stage(tmp_path)
    r, gh = _run_commit(work, sh, tmp_path)
    assert r.returncode == 0, "无撞车却非零退出：%s%s" % ((r.stdout or "")[-500:], (r.stderr or "")[-500:])
    assert "被拒" not in (r.stdout or ""), "没人抢推却报了放弃"
    log = _g(work, "log", "--oneline", "-10", "origin/main")
    assert "fast refresh stars" in log and "auto update stars" not in log
    assert _g(work, "log", "--merges", "--oneline", "origin/main") == "", (
        "干净推送却出现 merge 提交 ⇒ 走了重试分支，每场会白涨历史")
    assert "changed=true" in gh
