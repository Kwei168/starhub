# -*- coding: utf-8 -*-
"""T4 快车道 workflow 判据（A3 advisory）。

架构原则（用户裁决 2026-10-03 解耦；2026-10-07 P0 把裁决执行到底）：star 车道只做
"拉 star → 分类 → 提交状态"，**不持有任何 Pages 发布能力**。本文件钉住：
- 独立 concurrency 组（绝不取消小时场 starhub-update）；
- */15 schedule（cron-job.org mode=star 为主力的兜底）；
- 发布权为零：permissions 与 uses 两个正向闭集都不许出现发布通道（见
  test_fast_lane_has_no_publish_authority 的注释——为什么不用负字面量清单）；
- fast_refresh 被 GITHUB_TOKEN 注入调用；
- 撞车重试的**行为**判据（实跑 shell，见文件后半）。

2026-10-07 删掉的三条：test_upload_rejects_empty_artifact、
test_index_html_is_the_only_hard_requirement、test_upload_depends_on_publish_flag，
以及共犯判据 test_decoupling_no_retired_rss_chunks——它们钉的 Stage/Upload/Deploy 三步
与那份"带回清单"已整体不存在。其中最后一条尤其要记：它明令 rss-data-1.js 不得出现在
本车道，把"退出 git 提交"误当成"退出站点分发"，于是任何人想给闭集清单加回 chunk 都会
被打红——事故的认知根源被它固化了整整四天。
文本断言（不引 YAML 依赖：本仓 tests/ 下无 conftest，且 gate A 的 compileall 会先于
依赖安装崩在收集阶段）。"""
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


def _code_only(txt):
    """剔掉整行注释——判据要读行为，不能读关键词。

    就地写而不是从 test_trending_board_injection 复用：本仓 tests/ 下没有 conftest，
    跨模块 import 在 tools/mut_push_retry.py 的临时副本里会 ImportError（它只 copy
    yml + 本文件），而电池会把 ImportError 误报成"判据不合格"。
    """
    return "\n".join(l for l in txt.splitlines() if not l.strip().startswith("#"))


# permissions: / uses: 的**两种 YAML 写法**都要能被数出来。flow 风格（`permissions: {a: write}`、
# `- {name: Publish, uses: actions/deploy-pages@v4}`）不会展开成块，下面那些 block 正则一条都抓不到
# ⇒ 键集合退化成空集或合法子集，判据"全绿"而发布权已经回来了（2026-10-07 对抗审查实测命中）。
# 所以判据第一步是钉"声明数 == 抓取数"，把解析形状本身也变成被检对象。
_PERM_BLOCK = re.compile(r"^([ \t]*)permissions:[ \t]*\n((?:[ \t]+\w+:[^\n]*\n?)+)", re.M)
_PERM_DECL = re.compile(r"^[ \t]*permissions:", re.M)
_USES_BLOCK = re.compile(r"^[ \t]*uses:[ \t]*([^\s#]+)", re.M)
_USES_DECL = re.compile(r"\buses:", re.M)


def _perm_keys(txt):
    keys = set()
    for _indent, body in _PERM_BLOCK.findall(txt):
        for line in body.splitlines():
            m = re.match(r"[ \t]*([A-Za-z_-]+):", line)
            if m:
                keys.add(m.group(1))
    return keys


def _action_names(txt):
    """所有**块风格** `uses:` 引用的 action 名（去掉 @版本后缀）。"""
    return {u.split("@")[0] for u in _USES_BLOCK.findall(txt)}


def test_fast_lane_has_no_publish_authority():
    """P0 红线：本车道不得持有任何发布能力。钉两个**正向闭集**，不钉负字面量。

    为什么不写"不含 upload-pages-artifact / deploy-pages / _pages / publish=" 四条：
    换成别的 action（peaceiris/actions-gh-pages）或改走 curl 打 Pages 部署 API，负断言全部
    照样绿，而站点照样被整棵替换抹掉。本仓已经在"用闭集表达开集"这条路上摔过三次
    （lib/+api/ 10-02、trending_board 10-05、rss-data-1+ 10-07），不再第四次。
    ① permissions 键集合恰好 == {contents}：没有 pages / id-token，连调部署 API 的
       凭据通道都不存在（workflow/job/step 三级都收，防"缩进一层躲过检查"）；
    ② uses: 引用的 action 集合 ⊆ {checkout, setup-python}，且**必须非空**——
       空集配闭集判据等于恒真，那是本仓点名过的假绿形状；
    ③ 先钉形状：permissions / uses 的声明数必须等于块正则抓取数，否则 flow 风格写法正在
       绕过上面两个闭集（②的洞实测能塞进一整条 deploy-pages 步而全绿）。
    """
    code = _code_only(_wf_text())
    n_perm, got_perm = len(_PERM_DECL.findall(code)), len(_PERM_BLOCK.findall(code))
    assert n_perm == got_perm, \
        "%d 处 permissions 声明只解析到 %d 处 ⇒ 有 flow 风格写法绕过了闭集检查" % (n_perm, got_perm)
    n_uses, got_uses = len(_USES_DECL.findall(code)), len(_USES_BLOCK.findall(code))
    assert n_uses == got_uses, \
        "%d 处 uses: 只解析到 %d 处 ⇒ 有 flow 风格条目（- {name: …, uses: …}）绕过了闭集检查" % (n_uses, got_uses)
    keys = _perm_keys(code)
    assert keys == {"contents"}, \
        "star-fast 的 permissions 键集合不是 {{contents}} 而是 %s ⇒ 多出来的每一项都可能是一条发布通道" % sorted(keys)
    used = _action_names(code)
    assert used, "一个 uses: 都没抓到 ⇒ 本判据在空转（锚点或缩进形状变了）"
    allowed = {"actions/checkout", "actions/setup-python"}
    assert used <= allowed, \
        "star-fast 引用了发布类 action：%s（本车道只许用 checkout/setup-python）" % sorted(used - allowed)
    assert "rss-data" not in code, \
        "star-fast.yml 的代码区出现 rss-data 引用：阅读器分块由 update.yml 的工作树 glob 发布，本车道碰它就等于重新绑回双写者"


def test_fast_refresh_called_with_token():
    yml = _wf_text()
    assert "python fast_refresh.py" in yml
    m = re.search(r"Fast refresh.*?env:.*?GITHUB_TOKEN: \$\{\{ secrets\.GITHUB_TOKEN \}\}", yml, re.S)
    assert m, "fast_refresh 必须带 GITHUB_TOKEN（匿名限流=拉不全新星，本场分类结果直接丢）"


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
    2026-10-04 03:0x 实锤。钉法用**集合相等**而不是"必须包含 + 不许包含"两条：后者是开集写法，
    实测把 add 改成 `git add -A` 之后 all_added 只剩一个 "-A"、违规项为空 ⇒ 判据全绿，
    而手册的"禁 add -A"这条硬规恰恰是它该拦的形态。闭集（相等）一次覆盖三种越界。"""
    yml = _wf_text()
    commit = _step_body(yml, COMMIT_STEP_MARK)
    added = set()
    for line in re.findall(r"git add (.+)", commit):
        added.update(line.split())
    assert added == {"known_categories.json", "known_notes.json"}, \
        "star-fast 的 add 面必须恰好是这两个状态文件，实际是 %s（出现 -A / . / 第三个名字都算越界）" % sorted(added)


# ── 撞车重试的**行为**判据：读文本只证明"写了"，跑一遍才证明"跑得通" ──────────
# 为什么必须实跑：Commit 步的放弃分支是 `|| echo warning`（放弃优于挡住本步提交），所以它坏成
# "从没重试过"或"撞车即崩"都不会让整场变红——文本对了不代表 fetch 的 refspec、merge 的 --no-edit、
# 二次 push 的目标分支任何一处写错都能让"重试"形同不存在而全程静默。
# 这里在临时目录里建本地裸仓当远端，全程不碰网络、不碰 GitHub。
COMMIT_STEP_MARK = "Commit star state if changed"
_BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
_ME = ("Kwei168", "83650072+Kwei168@users.noreply.github.com")


def _step_body(txt, step_mark):
    """取某步骤从名字起、到**下一个** `- name:` 之前的正文。

    旧写法是 split(右锚步骤名)，右锚写死成 "Stage star page"——2026-10-07 P0 删掉 Stage 步之后，
    三条行为判据会一起 IndexError，看起来像"判据挂了"其实是锚点没了。改用"下一个 - name:"
    当边界，相邻步骤增删都不炸；找不到边界时明确报"边界没了"，不静默返回全文。
    """
    i = txt.index(step_mark)
    j = txt.find("\n      - name:", i + len(step_mark))
    assert j > i, "找不到 %r 之后的下一个步骤边界：本判据的右锚失效了" % step_mark
    return txt[i:j]


def _commit_shell(tmp_path):
    """抽出 Commit 步的 run 正文，去掉 YAML block scalar 的公共缩进后落成可执行脚本。"""
    seg = _step_body(_wf_text(), COMMIT_STEP_MARK)
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
    assert "changed=" in gh, "$GITHUB_OUTPUT 必须写 changed 信号：workflow 内已无下游（Stage 步随 P0 删除），它是本步「提交/放弃」唯一的可观测出口，也是这三条行为判据的断言目标"


def test_star_fast_survives_a_merge_conflict(tmp_path):
    """别人改的是同一个 known_categories.json ⇒ 合并必冲突：这一步必须零退出并留下可读警告。
    放弃优于挡住本步提交，但绝不能把每 15 分钟一场变成连片红（§8.24 那类吓人的红错正是这么长出来的）。"""
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
