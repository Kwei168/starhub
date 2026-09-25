# -*- coding: utf-8 -*-
"""批 0：把"独立"钉成机制 —— 夜场提交不看任何人的脸色，但 ref 必须显式。

来历（2026-09-23 现网事故 + 用户当场纠正）：
  · 我上一轮的设计是"夜场写 main 前先查有无在途构建，有则让位"。用户直接否掉：
    「仍旧要执行 白天跑时必须照样提交成功，这是独立的」。理由成立且已定过一次 ——
    白天场每小时都有，让位等于夜场永远等不到窗口，就是 §10.16 那句「停更比快讯更糟」。
    所以本文件里**有一条判据专门用来拦住以后任何人（包括我）再把让位闸加回来**。
  · 真缺的是另一半：我说"验证走分支，main 一个字节都不动"是假的。夜场不走
    `tools/data_api_push.py`，自带一套 CAS，`head_info`/`update_ref` 里 `heads/main`
    是硬编码，`deep-insight.yml` 的 `--ref` 出现 0 次 ⇒ 三场"验证"全打在 main 上
    （06:08:08 / 06:26:32 / 06:37:26Z），白天场 06:30:50 第二次 push 被拒、整场红。

于是这一批只立三条：① ref 必须显式给，忘传就是异常而不是"悄悄打到主干"；
② 给的 ref 必须真的落到每一个请求路径上；③ 提交通道里不许出现"探测别人在不在跑"。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402


def _api(ref="insight-verify", capture=None):
    """真 GithubDataApi，但把 _req 换成记录器：判"ref 传没传下去"必须看真实请求路径。

    记录器要**带 payload**，否则判不了 tree 里到底写了谁的路径；并且第一次
    PATCH ref 要回 422，才真的走得到 publish 的 CAS 重试分支（不然那条分支从没被碰过）。
    """
    api = D.GithubDataApi(token="t", ref=ref)
    calls = capture if capture is not None else []
    state = {"n": 0, "patch": 0}

    def fake_req(method, path, payload=None):
        calls.append((method, path, payload))
        if "/git/ref/heads/" in path:
            return {"object": {"sha": "h0"}}
        if "/git/commits/" in path:
            return {"tree": {"sha": "t_base"}}
        if path.endswith("/git/blobs"):
            state["n"] += 1
            return {"sha": "b%d" % state["n"]}
        if path.endswith("/git/trees"):
            return {"sha": "tr%s" % payload["base_tree"]}
        if path.endswith("/git/commits"):
            return {"sha": "c%d" % state["n"]}
        if path.endswith("/git/refs/heads/" + ref):
            state["patch"] += 1
            if state["patch"] == 1 and getattr(api, "advance_by_other", 0):
                import urllib.error
                raise urllib.error.HTTPError(path, 422, "non-fast-forward", {}, None)
            return {}
        if "/compare/" in path:
            return {"status": "ahead"}
        raise AssertionError("未预期的请求 %s %s" % (method, path))

    api._req = fake_req
    return api


def _tree_paths(calls):
    out = []
    for m, p, payload in calls:
        if m == "POST" and p.endswith("/git/trees"):
            out.append(sorted(e["path"] for e in payload["tree"]))
    return out


def _fn_body(fn):
    """函数/方法体，剥掉 docstring。

    两处坑都踩过：① `inspect.getsource(方法)` 带着缩进，不 dedent 则 ast.parse 直接炸；
    ② getsource(函数) 解析出来是 Module→FunctionDef，docstring 在**函数节点的
    body[0]**，不是模块 body[0] —— 判错层就会连解释这条约束的注释文字一起算成违规。
    """
    import ast
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        stmts = list(node.body)
        if stmts and isinstance(stmts[0], ast.Expr) \
                and isinstance(getattr(stmts[0].value, "value", None), str):
            stmts = stmts[1:]
        return stmts
    return list(tree.body)


def _code_strings(fn):
    """fn 代码里的字符串常量（docstring 整段排除）。"""
    import ast
    out = []
    for stmt in _fn_body(fn):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    return out


def _calls_and_strings(fn):
    import ast
    strs, names = [], []
    for stmt in _fn_body(fn):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                strs.append(node.value)
            elif isinstance(node, ast.Call):
                names.append(getattr(node.func, "attr", None) or getattr(node.func, "id", ""))
    return strs, names


# ───────────── ① ②：ref 显式，且真的传到每个请求 ─────────────

def test_api_requires_an_explicit_ref():
    """默认值写 main 就是这次的事故形态：忘传等于打到主干，而且一声不响。"""
    try:
        D.GithubDataApi(token="t")
    except (TypeError, ValueError, RuntimeError) as e:
        assert "ref" in str(e).lower(), e
    else:
        raise AssertionError("无 ref 也能构造 ⇒ 硬编码主干还活着")


def test_ref_reaches_every_request():
    calls = []
    api = _api("insight-verify", calls)
    res = D.publish(api, {"a.json": b"{}"}, "m")
    assert res["status"] == "published", res
    touched = [p for _, p, _ in calls if "heads/" in p or "/compare/" in p]
    assert touched, "一次 ref 相关请求都没发 ⇒ 这条判据在空转"
    for p in touched:
        assert "heads/main" not in p, "指定了分支却仍打到 main：%s" % p
        assert "insight-verify" in p, "ref 没传下去：%s" % p


def test_main_is_a_name_not_a_forgotten_default():
    """主干必须只有一个可写的名字，且 cron 那条路径显式用它 —— 打主干是决定，不是漏参数。"""
    assert D.MAIN_REF == "main"
    calls = []
    api = _api(D.MAIN_REF, calls)
    assert D.publish(api, {"a.json": b"{}"}, "m")["status"] == "published"
    assert any("/git/refs/heads/main" in p for _, p, _ in calls), calls


def test_no_request_path_embeds_a_literal_ref():
    """代码里的请求路径必须拼 self.ref，不许出现字面量主干。

    扫 AST 的字符串常量而不是全文：全文会把"以前 heads/main 硬编码"这类注释
    也算成命中，判据就成了自我干扰；而真正该拦的是代码字面量。
    """
    for fn in (D.GithubDataApi.head_info, D.GithubDataApi.update_ref,
               D.GithubDataApi.is_ancestor):
        for s in _code_strings(fn):
            assert "heads/main" not in s and "...main" not in s, \
                "%s 里还写着字面量主干：%r" % (fn.__name__, s)


# ───────────── ③ 独立：不许探测别人在不在跑 ─────────────

def test_publish_channel_never_probes_for_running_workflows():
    """用户点名的独立要求，钉成判据防回归。

    我上一轮的设计是"夜场写 main 前先查有无在途构建，有则让位"，被当场否掉：
    白天场每小时都有，让位=夜场永远发不出去，与已定的「停更比快讯更糟」同错。
    所以"探测别的 workflow 在不在跑"这个动作本身不许出现在提交通道里。
    """
    import inspect
    targets = [D.publish, D.GithubDataApi.head_info, D.GithubDataApi.update_ref,
               D.GithubDataApi.is_ancestor]
    for fn in targets:
        strs, names = _calls_and_strings(fn)
        for s in strs:
            for probe in ("actions/runs", "in_progress"):
                assert probe not in s, \
                    "%s 的代码里出现探测串 %r：那是把夜场重新绑回白天窗口" % (fn.__name__, probe)
        for nm in names:
            assert nm not in ("gate", "push_gate", "runs"), \
                "%s 调用了 %s()：提交通道不许看别人在不在跑" % (fn.__name__, nm)
    assert "gate" not in inspect.signature(D.publish).parameters, \
        "publish 又长出一个守门参数：让位闸被以另一种形状加回来了"


def test_publish_survives_a_concurrent_advance_without_force():
    """白天场在跑 ⇒ CAS 会撞车。撞车必须重读 head 重试，而不是 force 覆盖别人的产物。"""
    calls = []
    api = _api(D.MAIN_REF, calls)
    api.advance_by_other = 1        # 第一次 PATCH ref 时白天场抢先推进 → 422
    res = D.publish(api, {"a.json": b"{}"}, "m", max_attempts=3)
    assert res["status"] == "published", res
    assert res["attempts"] >= 2, "CAS 撞车却没重试：那这条重试分支从没被执行过 %s" % res
    patches = [p for m, p, _ in calls if m == "PATCH"]
    assert len(patches) >= 2, patches
    assert all(b.get("force") is False for m, _, b in calls if m == "PATCH"), \
        "force 覆盖 = 回滚别人刚推的东西"


def test_only_own_paths_are_committed_under_contention():
    """撞车重试时也不许把别人的路径带进 tree —— 这是"夜场不可能回滚白天产物"的结构保证。"""
    calls = []
    api = _api(D.MAIN_REF, calls)
    api.advance_by_other = 1
    D.publish(api, {"deep-insight.html": b"<p/>", "predictions.jsonl": b""}, "m",
              max_attempts=3)
    trees = _tree_paths(calls)
    assert trees, "一次 tree 都没建 ⇒ 这条判据在空转"
    for t in trees:
        assert t == ["deep-insight.html", "predictions.jsonl"], t


# ───────────── CLI：打主干要人点名，但不看别人脸色 ─────────────

def test_manual_publish_must_name_its_ref():
    """手滑保护，不是让位闸：不点名就拒绝（而不是"默认打 main"），点名了就照打。"""
    ok, why = D.publish_ref_guard("publish", "", "workflow_dispatch")
    assert not ok and "ref" in why.lower(), (ok, why)
    assert D.publish_ref_guard("publish", "insight-verify", "workflow_dispatch")[0]
    assert D.publish_ref_guard("publish", D.MAIN_REF, "workflow_dispatch")[0]
    assert D.publish_ref_guard("publish", D.MAIN_REF, "schedule")[0]


def test_test_purpose_never_commits_regardless_of_ref():
    """test 的含义就是"不入库"，与 ref 无关；这里不许长出"test 也能提交"的旁路。"""
    ok, why = D.publish_ref_guard("test", D.MAIN_REF, "workflow_dispatch")
    assert not ok and "test" in why, (ok, why)


# ───────────── 工作流必须真的把 ref 接下去 ─────────────

def _wf():
    return open(os.path.join(ROOT, ".github", "workflows", "deep-insight.yml"),
                encoding="utf-8").read()


def test_workflow_forwards_ref_without_a_main_default():
    wf = _wf()
    assert "--ref" in wf, "工作流没把 ref 传给脚本：`--ref` 出现 0 次就是这次的事故"
    assert "RUN_REF" in wf, "ref 未走 env 传值（dispatch 输入裸插值进 run 是命令注入面）"
    # 真去读 ref 这个输入的 default，而不是 grep 字面量：YAML 里带引号就躲过去了
    # （变异体 C11 把 default 写成 'main' 时，旧写法仍然全绿 —— 判据本身是瞎的）。
    import re
    m = re.search(r"\n      ref:\n(?:.*\n)*?        default:[ \t]*(.*)", wf)
    assert m, "dispatch 输入里没有 ref 这一项"
    val = m.group(1).strip().strip("'\"")
    assert val == "", "ref 的 default 是 %r；默认主干等于手动验证必然打到线上" % val


def _step(wf, name, nxt):
    """按**步骤边界**切出一段，不能用 wf[index:]：右边界不设，下一步骤的同名文本会替它过关。
    变异体 C10 把主跑步骤的 --ref 删掉却"全绿"，就是因为切片把重试步骤含进来了。"""
    seg = wf[wf.index(name):]
    cut = seg.index(nxt)
    return seg[:cut]


def test_workflow_run_step_passes_ref_to_the_script():
    wf = _wf()
    seg = _step(wf, "Night deep insight run", "Night retry")
    assert '--ref "$RUN_REF"' in seg, seg[:400]


def test_retry_step_also_passes_ref():
    """补跑漏 ref 的话，purpose=publish 那一趟会被自己的守卫当场拒掉 —— 一夜只有一次重试。"""
    wf = _wf()
    seg = _step(wf, "Night retry", "上一夜是否漏跑")
    assert '--ref "$RUN_REF"' in seg, seg[:400]


def test_cli_refuses_publish_without_ref_before_any_work(monkeypatch):
    """守卫必须坐在"出网/花钱"之前，而且要真的接在 main 上。

    只在函数层测 publish_ref_guard 不够：本仓出过一次"函数写了没人调用"的空函数事故
    （spec §8 第 3 行那条 predictions 对账）。这里让 night_run 一被调用就炸。
    """
    def boom(*a, **k):
        raise AssertionError("ref 未点名就已经开始跑了：会先读几十 MB 再报错")
    monkeypatch.setattr(D, "night_run", boom)
    try:
        D.main(["--purpose", "publish", "--events-limit", "3"])
    except SystemExit as e:
        assert e.code, "拒绝却给了退出码 0，CI 会当成功"
    else:
        raise AssertionError("purpose=publish 不点名 ref 竟然跑下去了")


def test_cli_test_mode_does_not_need_a_ref(monkeypatch):
    """test 不入库，就不该被 ref 守卫挡在门外 —— 否则每次本地验证都要编一个分支名。"""
    seen = {}

    def fake(*a, **k):
        seen["ref"] = k.get("ref")
        # 形状必须跟真 night_run 一致：main 的收尾播报要读 payload.budget 与 budget，
        # 给个半成品 dict 会让这条判据测成 KeyError 而不是它想测的东西。
        return {"budget": {"llm_calls": 0, "wait_s": 0.0, "c429": 0, "elapsed_s": 0.0,
                           "truncated": 0},
                "published": {"status": "noop"},
                "payload": {"events": [], "budget": {"qualified": 0, "degraded": 0},
                            "not_run": [], "predictions_reconciled": {}}}
    monkeypatch.setattr(D, "night_run", fake)
    assert D.main(["--purpose", "test", "--events-limit", "1"]) == 0
    assert seen.get("ref") == "", seen


def test_schedule_path_targets_main_explicitly():
    """cron 那一档必须**显式**写 main：它是生产本身，不该由"忘了传"来达成。"""
    wf = _wf()
    assert "RUN_REF" in wf and "main" in wf
    seg = wf[:wf.index("Night deep insight run")]
    assert '"$GH_EVENT" = "schedule"' in seg, "schedule 分支不见了，cron 会走到『不点名就拒』那条路"
    assert "ref=main" in seg, "cron 没有显式给出主干 ref"
    """cron 那一档必须**显式**写 main：它是生产本身，不该由"忘了传"来达成。"""
    wf = _wf()
    assert "RUN_REF" in wf and "main" in wf
    seg = wf[:wf.index("Night deep insight run")]
    assert '"$GH_EVENT" = "schedule"' in seg, "schedule 分支不见了，cron 会走到『不点名就拒』那条路"
