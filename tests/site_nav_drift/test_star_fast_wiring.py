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
# 变异电池（tools/mut_star_state.py）在临时副本上跑，靠这个注入点指向被变异的 yml；
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
    跨模块 import 在 tools/mut_star_state.py 的临时副本里会 ImportError（它只 copy
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


def test_star_state_content_surface_is_exactly_two_files():
    """star-state 上只许装这两个状态文件，一个不多。

    三段来历，都要保住：
    ① 2026-10-04 03:0x：descriptions_zh.json 已进 starhub-state 缓存家族（.gitignore + 出 git 树），
       把它 add 进去必被拒 ⇒ 新星场的分类结果提交不出去，每 15 分钟循环炸（下场重新烧 LLM）。
    ② 钉法用**集合相等**而不是"必须包含 + 不许包含"：后者是开集写法，实测 `git add -A` 时
       违规项为空 ⇒ 全绿，而"禁 add -A"恰恰是它该拦的形态。
    ③ 2026-10-08 P1：本步改用 plumbing（read-tree / update-index / commit-tree）构造提交，
       所以断言跟着翻——**不许再有 `git add`**（它会污染 actions/checkout 的主工作树索引），
       改钉 `--cacheinfo` 的文件集合恰好是这两个。分支里混进源码 = 读端 fetch 到
       "停在旧流程的过期副本"，正是 10-07 事故里库里那份 rss-data-1.js 的坑。
    """
    yml = _wf_text()
    ign = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    # 只看代码行：本步的注释里合法地写着"不走 add/commit""descriptions_zh 不在清单里"这类历史
    # 叙述，裸搜字面量会把它们当成行为（本仓为这个坑写过 _code_only，这里是第四次用到）。
    commit = _code_only(_step_body(yml, COMMIT_STEP_MARK))
    assert not re.search(r"^\s*git add ", commit, re.M), \
        "P1 之后本步用 plumbing 构造提交，git add 会污染主工作树索引 ⇒ 不许回来"
    # 内容面写在 `for f in … do` 的循环头里，`--cacheinfo` 那一行的文件名是变量 $f，
    # 所以钉循环列表而不是钉 cacheinfo 实参（钉实参会永远匹配不到 ⇒ 空集恒真）。
    m = re.search(r"for f in ([^;]+);?\s*do\b", commit)
    assert m, "找不到 `for f in … do` 的内容面清单 ⇒ 本判据的锚点失效了"
    cached = set(m.group(1).split())
    assert cached == {"known_categories.json", "known_notes.json"}, \
        "star-state 的内容面必须恰好是这两个状态文件，实际是 %s（多一个名字或写成 -A 都算越界）" % sorted(cached)
    ignored = {l.strip() for l in ign.splitlines() if l.strip() and not l.strip().startswith("#")}
    for path in cached:
        assert path not in ignored, "%s 在 .gitignore 里，不该进 star-state" % path


# ── star-state 的**行为**判据：读文本只证明"写了"，跑一遍才证明"跑得通" ──────
# 为什么必须实跑：这一步的失败模式全是静默的——分支名拼错会凭空造出一条没人读的分支、
# plumbing 的索引没隔离会污染 actions/checkout 的主工作树、把源码一起写进分支会让读端
# fetch 到"停在旧流程的过期副本"（正是 10-07 事故里库里那份 rss-data-1.js 的坑）。
# 文本断言一条都抓不到这些，所以在这里建本地裸仓当 origin 全程实跑，不碰网络、不碰 GitHub。
#
# 2026-10-08 P1 换血：原来这三条（test_star_fast_lands_after_a_clean_collision /
# survives_a_merge_conflict / clean_push_skips_the_retry）钉的是"撞 main ⇒ merge 重试一次"
# 那条链。本车道不再写 main 之后，单写者不需要 merge ⇒ 那条链整体消失，三条判据连同
# tools/mut_push_retry.py 一起退役（留着它们＝钉一个不存在的机制，是另一种空转）。
COMMIT_STEP_MARK = "Commit star state to its own branch"
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


def _state_shell(tmp_path):
    """抽出 star 状态提交步的 run 正文，去掉 YAML block scalar 的公共缩进后落成可执行脚本。"""
    seg = _step_body(_wf_text(), COMMIT_STEP_MARK)
    lines = seg.split("run: |", 1)[1].rstrip("\n").splitlines()
    ind = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    sh = tmp_path / "state_step.sh"
    sh.write_text("\n".join(l[ind:] if l.strip() else "" for l in lines) + "\n", encoding="utf-8")
    return str(sh)


def _g(repo, *args):
    import subprocess
    r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, " ".join(args) + " 失败：" + ((r.stderr or "") + (r.stdout or ""))[:400]
    return (r.stdout or "").strip()


def _clone(url, here, who, ci_checkout=False):
    """ci_checkout=True 复刻 actions/checkout 的默认形态：浅 + 单分支 ⇒ **别的分支一个对象都没有**。

    这个开关是 10-08 09:45/10:00 两场 "not a valid object" 换来的：全量 clone 会把 star-state
    的对象也带回本地，于是"拿远端 sha 直接当父提交"在测试里永远成立，在 CI 里永远炸。
    """
    import subprocess
    cmd = ["git", "clone", "-q"]
    if ci_checkout:
        cmd += ["--depth=1", "--single-branch", "--branch", "main"]
    subprocess.run(cmd + [url, here], check=True)
    _g(here, "config", "user.name", who[0])
    _g(here, "config", "user.email", who[1])


def _push_star_state(here, payload, msg):
    """用 plumbing 在 origin 上造/追加一个只含状态文件的 star-state 提交（模拟"上一场"）。"""
    import subprocess
    idx = os.path.join(here, ".seedidx")
    env = {**os.environ, "GIT_INDEX_FILE": idx}
    if os.path.exists(idx):
        os.remove(idx)
    p = os.path.join(here, ".seed_kc")
    with open(p, "w", encoding="utf-8") as f:
        f.write(payload)
    sha = subprocess.run(("git", "-C", here, "hash-object", "-w", p),
                         capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(("git", "-C", here, "read-tree", "--empty"), env=env, check=True)
    subprocess.run(("git", "-C", here, "update-index", "--add", "--cacheinfo",
                    "100644,%s,known_categories.json" % sha), env=env, check=True)
    tree = subprocess.run(("git", "-C", here, "write-tree"), env=env,
                          capture_output=True, text=True, check=True).stdout.strip()
    have = _g(here, "ls-remote", "origin", "refs/heads/star-state")
    args = ("git", "-C", here, "commit-tree", tree)
    if have:
        args += ("-p", have.split()[0])
    args += ("-m", msg)
    commit = subprocess.run(args, env=env, capture_output=True, text=True, check=True).stdout.strip()
    _g(here, "push", "-q", "origin", "%s:refs/heads/star-state" % commit)
    os.remove(idx)


def _stage(tmp_path, prior_state=None, new_star=True):
    """origin 裸仓 → seed 建 main → work（本场工作树，新星已写进 known_categories）。
    prior_state 给定时先在 star-state 上放一个"上一场"的提交；new_star=False 走无新星分支。
    返回 work 路径。"""
    import subprocess
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    # 裸仓的 HEAD 默认指 master，而 CI 的远端默认分支是 main：不改的话 clone 出来是空工作树。
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
    if prior_state:
        # 「上一场」必须由**另一份工作树**造（CI 里它是另一台 runner 的前一场），再从 work 里
        # 看不见那枚对象。早前借 work 自己提交 ⇒ 判据以为在测"追加"，实际从没测过
        # "父提交不在本地"这一条真实条件（checkout 只取 main），于是它在本地一直绿、CI 连红两场。
        prev = str(tmp_path / "prev")
        _clone(str(origin), prev, _BOT)
        _push_star_state(prev, prior_state, "chore: star state prior")
    # work 对齐 CI：单分支浅检出，别的分支的对象一个都没有。
    # 必须走 file:// 而不是裸路径——本地路径 clone 会硬链整个 objects/ 并打印
    # "--depth is ignored in local clones"，那样浅检出形同没浅，父提交永远在场（10-08 踩过）。
    _clone(origin.as_uri(), work, _BOT, ci_checkout=True)
    if new_star:
        (tmp_path / "work" / "known_categories.json").write_text(
            '{"a/one": "agent", "b/new": "tools"}\n', encoding="utf-8")
        (tmp_path / "work" / "fast.log").write_text("[fast] 新星 1 条：b/new\n", encoding="utf-8")
    else:
        (tmp_path / "work" / "known_categories.json").write_text('{"a/one": "agent"}\n', encoding="utf-8")
        (tmp_path / "work" / "fast.log").write_text(
            "[fast] no change, skip write（1 条，无新星）\n", encoding="utf-8")
    return work


def _run_state(work, sh, tmp_path):
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


def test_star_state_lands_on_its_branch_and_main_stays_untouched(tmp_path):
    """P1 的全部意义：状态进 star-state，而 main 的提交数**一个都不许多**。

    后半那条断言才是这次解耦真正的判据——只要本车道还能往 main 推，小时场的 push 就还会
    non-fast-forward（10-07 04:00 实锤：远端三次 fast 提交夹掉它两次 push ⇒ 整场红、Pages 不发）。
    """
    _need_bash()
    work = _stage(tmp_path)
    main_before = _g(work, "rev-list", "--count", "origin/main")
    r, gh = _run_state(work, _state_shell(tmp_path), tmp_path)
    assert r.returncode == 0, "整步非零退出：%s%s" % ((r.stdout or "")[-400:], (r.stderr or "")[-400:])
    _g(work, "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*")
    assert "b/new" in _g(work, "show", "origin/star-state:known_categories.json"), \
        "新星没进 star-state ⇒ 分类结果没落库，下一场会重新 diff 出来再烧一次 LLM"
    assert _g(work, "rev-list", "--count", "origin/main") == main_before, \
        "main 的提交数变了 ⇒ 本车道还在写 main，P1 没生效"
    assert "changed=true" in gh


def test_star_state_branch_carries_only_the_two_state_files(tmp_path):
    """分支 tree 必须恰好是那两个状态文件。

    混进源码不是"多几个文件"的小事：读端 fetch 回来做并集时以分支那份为准，而它是
    actions/checkout 那一刻的**过期副本**——正是 10-07 事故里"库里那份 rss-data-1.js 停在
    旧流程"的同一个坑，换个分支重演一遍。
    """
    _need_bash()
    work = _stage(tmp_path)
    r, _ = _run_state(work, _state_shell(tmp_path), tmp_path)
    assert r.returncode == 0
    _g(work, "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*")
    names = sorted(_g(work, "ls-tree", "-r", "--name-only", "origin/star-state").splitlines())
    assert names == ["known_categories.json", "known_notes.json"], \
        "star-state 上出现了别的文件（读端会把它当权威）：%s" % names


def test_star_state_appends_and_never_uses_bare_force(tmp_path):
    """已有分支时必须 fast-forward 追加，且这一步全文不许出现裸 `--force`。

    单写者用 --force-with-lease 的意义就在"真冒出第二个写者时会被拒"。一旦有人图省事改成
    --force，被拒就变成静默覆盖别人的分类结果——而这条链上没有任何人会注意到（它不发布
    任何东西，红了也没人看见），所以必须靠租约而不是靠人盯。
    """
    _need_bash()
    work = _stage(tmp_path, prior_state='{"a/one": "agent", "c/prior": "video"}\n')
    r, gh = _run_state(work, _state_shell(tmp_path), tmp_path)
    assert r.returncode == 0, "追加提交却非零退出：%s%s" % ((r.stdout or "")[-300:], (r.stderr or "")[-300:])
    _g(work, "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*")
    log = _g(work, "log", "--oneline", "origin/star-state")
    assert "star state prior" in log, "本场提交把上一场覆盖了 ⇒ 不是追加，是替换"
    assert "b/new" in _g(work, "show", "origin/star-state:known_categories.json")
    assert not re.search(r"--force(?!-with-lease)", _code_only(_step_body(_wf_text(), COMMIT_STEP_MARK))), \
        "star-state 的推送里出现裸 --force ⇒ 租约保护失效"


def test_no_new_star_pushes_nothing_at_all(tmp_path):
    """无新星 ⇒ 零推送、零分支创建。实测 96% 的场次走这条，别让它凭空造分支或空提交。"""
    _need_bash()
    work = _stage(tmp_path, new_star=False)
    r, gh = _run_state(work, _state_shell(tmp_path), tmp_path)
    assert r.returncode == 0
    assert _g(work, "ls-remote", "origin", "refs/heads/star-state") == "", \
        "无新星却创建了分支 ⇒ 每 15 分钟白涨一次提交"
    assert "changed=false" in gh
