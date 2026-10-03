# -*- coding: utf-8 -*-
"""A3（advisory）：Pages 三步的位置与守卫条件——把一次被挡回来的提案钉成知识。

2026-10-02 我提过一版"把 `Upload Pages artifact` / `Deploy to GitHub Pages` 挪到
`Deploy to Vercel` 之前"，动机是现取的：13:00 那场构建 13:22 就完成了，而 Vercel 步
（5 次重试 + `npx vercel` 上传）从 13:22 一直卡到 13:49 之后，Pages 两步全程 pending
⇒ 站点内容早生成好，却要等一个与 Pages 无关的第三方部署重试完才上线。

**这个提案被既有 A2 判据挡回来了**（在副本上彩排时当场报红，不是靠推理否掉的）：
`tests/rss_history/test_pages_deploy_wiring.py::test_pages_steps_present_and_cannot_block_vercel`
钉的是"Pages 必须排在 Vercel 之后"，理由是 Pages 两步没有 continue-on-error，
挪到前面的话**它们任何一次失败就会终止 job，把 Vercel 部署整个跳过**。
所以"改顺序"不是免费午餐：它把"Pages 被 Vercel 拖慢"换成"Vercel 被 Pages 挡掉"。

要治那条延迟，可行的方向是**给 Vercel 步本身封顶**（`timeout-minutes`，再让末步把 Vercel 的
未成功也标红），**不是**加 `continue-on-error` —— 本文件自己的 `test_vercel_step_is_not_silenced`
就禁止静默，而静默恰恰是本项目最怕的形态（写这段时我先把"封顶 + continue-on-error"当成可行方向，
是读了那条判据才发现二者互斥；改形后的方案见下面两条新判据）。
本文件因此钉的是**现状不变量**（顺序 + 两道 if 守卫 + Vercel 不许被静默），
这样将来谁要动这两步，会先看到这里的理由，而不是把不变量悄悄改掉。
"""
import ast
import os
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.environ.get("STARHUB_UPDATE_YML") or os.path.join(ROOT, ".github", "workflows", "update.yml")

UPLOAD = "Upload Pages artifact"
DEPLOY = "Deploy to GitHub Pages"
VERCEL = "Deploy to Vercel"
STAGE = "Stage Pages site"


def _steps():
    with open(WF, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["jobs"]["update"]["steps"]


def _idx(steps, want):
    hits = [i for i, s in enumerate(steps) if (s.get("name") or "").startswith(want)]
    assert len(hits) == 1, "步骤 %r 出现 %d 次（应为 1）⇒ 本文件的定序判据不作数" % (want, len(hits))
    return hits[0]


def test_pages_pair_sits_after_vercel_on_purpose():
    """现状：Stage → Save state cache → Prune → Vercel → Log → Upload → Deploy → 标红步。

    Stage 排在 Save 之前是 2026-10-02 搬的：缺件落痕（`pages_missing` 写进 build_logs）必须
    赶在缓存保存之前，否则同场 prune 一删就查不到（判据：test_pages_missing_lifecycle.py）。
    Vercel 与 Pages 两步的相对顺序是**有意**的，理由见文件头。
    """
    steps = _steps()
    si, ui, di, vi = (_idx(steps, w) for w in (STAGE, UPLOAD, DEPLOY, VERCEL))
    assert si < ui < di, "Pages 两步必须在 Stage 之后、且 Upload 早于 Deploy（否则发的是旧制品）"
    assert vi < ui, ("Vercel 步跑到了 Pages 之后 —— 这是另一条 A2 判据禁止的形状吗？"
                     "先读 tests/rss_history/test_pages_deploy_wiring.py::"
                     "test_pages_steps_present_and_cannot_block_vercel 再动")


def test_pages_steps_keep_their_guard_conditions():
    """两道守卫不许在改顺序时被顺手改掉：残缺制品不许发布。"""
    steps = _steps()
    up = steps[_idx(steps, UPLOAD)]
    dep = steps[_idx(steps, DEPLOY)]
    assert "steps.stage.outcome" in (up.get("if") or ""), \
        "Upload 不再要求 stage 成功 ⇒ 残缺 _pages 会被当有效制品发布：%r" % (up.get("if") or "")
    cond = dep.get("if") or ""
    assert "always()" in cond and "steps.pages_upload.outcome" in cond, \
        "Deploy 的 if 被改动：%r" % cond
    assert (up.get("with") or {}).get("if-no-files-found") == "error", \
        "空制品的 warn 默认值会把站点抹平"


def test_vercel_step_is_not_silenced():
    """Vercel 失败必须让整场可见（它没有 continue-on-error）。

    这条同时是"改顺序方案"的前提检查：哪天有人给 Vercel 加上 continue-on-error，
    文件头那段权衡就失效了，本文件与 A2 那条判据都要跟着重新讨论。
    """
    steps = _steps()
    ver = steps[_idx(steps, VERCEL)]
    assert ver.get("continue-on-error") is not True, \
        "Vercel 被改成 continue-on-error ⇒ 失败会被遮成 success，Pages 与 Vercel 的耦合判断要重做"
    assert "5" in (ver.get("run") or ""), "Vercel 的 5 次重试循环不见了？确认一下再改本文件的结论"


RED_FLAG = "Mark the run red"


def test_vercel_step_has_a_timeout_cap_and_id():
    """Vercel 步必须自己封顶，并有 id 让后面那步引用它的结果。

    现取的依据（2026-10-02）：正常场这一步只用 **0.5–0.7 分钟**，而 1578 跑了 38.8 分钟被并发掐掉、
    1585 跑了约 42 分钟同样被掐、1586 也被掐 ⇒ 从 18:00 场（1584）之后连续三场 Vercel 部署没落地。
    没有封顶时，这一步的挂起会把整场撑到被并发取消，而门禁与告警都不会说"Vercel 没部署成功"。
    上限取 12 分钟：是正常用时的 ~20 倍，给足 5 次退避重试（15+30+45+60=150s 的 sleep 加四次上传），
    又远小于整场被掐的时间。下限 3 分钟是防手滑写成 1 分钟把正常场全打死。
    """
    ver = _steps()[_idx(_steps(), VERCEL)]
    cap = ver.get("timeout-minutes")
    assert isinstance(cap, int) and 3 <= cap <= 12, (
        "Vercel 步没有合理的 timeout-minutes（实得 %r）⇒ 挂起时整场只会被并发掐掉，"
        "而 Pages 之后的标红步也拿不到它的结果" % cap)
    assert ver.get("id"), "Vercel 步没有 id ⇒ 末步无法用 steps.<id>.outcome 引用它，标红判不了"


def test_unsuccessful_vercel_is_marked_red_at_the_end():
    """Vercel 未成功（failure / cancelled）必须让整场标红，且不许靠 continue-on-error 静默。

    与上一条是一对：封顶负责"别拖垮整场"，这条负责"别悄悄算过"。
    现状是末步只看 Stage 的 outcome（`steps.stage.outcome == 'failure'`），
    所以 Vercel 被掐时整场显示 cancelled 却没有任何一步说明"是 Vercel 没部署成"。
    """
    steps = _steps()
    ver = steps[_idx(steps, VERCEL)]
    hits = [i for i, s in enumerate(steps) if (s.get("name") or "").startswith(RED_FLAG)]
    assert len(hits) == 1, "标红步骤应只有 1 个，实得 %d ⇒ 引用关系判不出" % len(hits)
    mark = steps[hits[0]]
    cond = (mark.get("if") or "")
    assert "steps.%s" % (ver.get("id") or "?") in cond, (
        "末步的 if 没引用 Vercel 的 outcome（实得 %r）⇒ Vercel 未成功时整场仍是绿的" % cond)
    assert "failure" in cond or "!= 'success'" in cond, (
        "末步只判断一种失败形态不够：超时被掐时 outcome 是 cancelled，实得 %r" % cond)
    assert "exit 1" in (mark.get("run") or ""), "标红步没真的 exit 1，写了 if 也不会红"
    assert ver.get("continue-on-error") is not True, (
        "Vercel 又被加了 continue-on-error ⇒ 与 test_vercel_step_is_not_silenced 冲突，二选一")


# ── 2026-10-03 新增：整场被取消那种"Pages 没发"也得出声 ──────────────────────────
# 实证（现取 run 1590，2026-10-03 00:06）：GitHub 把一个迟到的 `schedule` 事件补发，
# 撞上正在跑的 dispatch 场，concurrency.cancel-in-progress 把它掐掉 ⇒
# 第 18 步 cancelled，21–34 步（含 Commit / Stage / Upload Pages / Deploy Pages）**全 skipped**，
# 站点整整一小时没更新，而末步的 if 只认 `stage.outcome == 'failure'`，
# 于是它自己也是 skipped —— 没有一行 ::error:: 说"本场未发布"。
# 只看 run 结论是 cancelled 也不算"出声"：没人会把每小时的颜色当告警读。
_IF_TEST = re.compile(r"steps\.(\w+)\.outcome\s*(==|!=)\s*'(\w+)'")
_BODY_TEST = re.compile(r"\[\s*\"\$\{\{\s*steps\.(\w+)\.outcome\s*\}\}\"\s*(=|!=)\s*\"(\w+)\"\s*\]")


def _eval(cond, outcomes):
    """按 outcome 组合求真值：先把每个 `steps.X.outcome == 'v'` 换成布尔，
    再交给**只认布尔代数的小求值器**（不用 eval —— 一行 yml 不该拿到执行任意表达式的权限）。

    这条判据要的是"组合实跑"，不是 grep 文本：grep 看得见 skipped 这个词，
    看不见它是不是绑在 stage 上、也看不见正常那场会不会被误红。
    """
    expr = _IF_TEST.sub(lambda m: str(_one(m.group(1), m.group(2), m.group(3), outcomes)), cond)
    expr = expr.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    return _bool_tree(ast.parse(expr, mode="eval").body)


def _bool_tree(node):
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, bool):
            raise AssertionError("末步 if 里出现非布尔字面量 %r ⇒ 判据拒绝求值" % (node.value,))
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _bool_tree(node.operand)
    if isinstance(node, ast.BoolOp):
        vals = [_bool_tree(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    raise AssertionError("末步 if 里出现布尔代数之外的写法（%s），判据不敢替你求值" % type(node).__name__)


def _one(sid, op, val, outcomes):
    got = outcomes.get(sid)
    assert got is not None, "末步 if 引用了 steps.%s，但测试没给这一步的 outcome" % sid
    # shell 的相等写作 `=`、表达式里是 `==` —— 两种都要认。
    # 这里原本只判 `==`，于是所有 `=` 分支都掉进"不等"那一支 ⇒ 判据自己算反，
    # 而且"上次它通过"是撞对的（假绿）。2026-10-03 复现并修，配 _body_reds 的自测。
    return (got == val) if op in ("==", "=") else (got != val)


def test_body_evaluator_is_not_backwards():
    """求值器自身的自测：`=` 与 `!=` 两个方向各打一次，正反都要有。

    末步的判断是按 outcome 组合真算的，那么"算"这一步也必须有判据 ——
    否则它算反时，所有下游断言都会因为"两边都错"而静默通过。
    """
    body = ('if [ "${{ steps.stage.outcome }}" = "skipped" ]; then\n  exit 1\nfi\n'
            'if [ "${{ steps.vercel.outcome }}" != "success" ]; then\n  exit 1\nfi\n')
    hit = lambda o: sorted(m.split("=")[0].split("!")[0] for m in _body_reds(body, o))
    assert hit({"stage": "skipped", "vercel": "success"}) == ["stage"], "`=` 方向算反了"
    assert hit({"stage": "success", "vercel": "success"}) == [], "都成功时不该有任何命中"
    assert hit({"stage": "success", "vercel": "cancelled"}) == ["vercel"], "`!=` 方向算反了"
    assert hit({"stage": "success", "vercel": "skipped"}) == ["vercel"], (
        "vercel=skipped 会让 body 那半出声（这是 run 结论那半刻意不红的形状，两者口径本就不一样）")


def _body_reds(mark_run, outcomes):
    """run 体里哪几条 shell 判断会命中（命中即 ::error:: + exit 1）。"""
    hits = []
    for m in _BODY_TEST.finditer(mark_run):
        if _one(m.group(1), "=" if m.group(2) == "=" else "!=", m.group(3), outcomes):
            hits.append(m.group(1) + m.group(2) + m.group(3))
    return hits


def test_cancelled_run_also_marks_pages_unpublished():
    """整场被取消时 Stage 是 skipped 而不是 failure —— 那种"Pages 没发"也必须出声。

    覆盖面（说准，别当成"发布链的总闸"）：按 stage / pages_upload / vercel 三个 outcome 组合真算。
    已覆盖：Stage 缺件(failure)、整场被取消或前置判红(stage skipped)、
    Stage 成了但上传没跑(pages_upload skipped，17:00 那场静默失败就是它)、Vercel failure/cancelled。
    **仍未覆盖**：`Upload Pages artifact` 成功、但 `Deploy to GitHub Pages` 自己失败 ——
    那一步没有 id，引用不到（`tools/prod_verify.py` 从站点侧能看到"页面没更新"，是另一条路径）。
    """
    steps = _steps()
    mark = steps[_idx(steps, RED_FLAG)]
    cond = (mark.get("if") or "")
    body = mark.get("run") or ""
    ok = {"stage": "success", "vercel": "success", "pages_upload": "success"}
    # 反向那半与正向同权重：正常发布的那场绝不许红
    assert not _eval(cond, ok), "正常成功的一场末步就红了 ⇒ 条件写成了无条件，末步在制造假失败"
    # 1590 的真实形状：整场被取消，Stage 没跑成
    cancelled = {"stage": "skipped", "vercel": "skipped", "pages_upload": "skipped"}
    assert _eval(cond, cancelled), (
        "Stage 被跳过（整场取消、或前置 blocking 判红）时末步不执行 ⇒ Pages 未发布继续静默；"
        "实得条件 %r" % cond)
    assert _eval(cond, {"stage": "failure", "vercel": "success", "pages_upload": "success"}), (
        "缺件那半被改丢了：Stage 判 failure 必须仍然红")
    assert _eval(cond, {"stage": "success", "vercel": "cancelled", "pages_upload": "success"}), (
        "封顶那半被改丢了：Vercel 被掐（cancelled）必须仍然红")
    # 出声的**内容**也要对：被取消那场得说"Pages 未发布"，不能只报 Vercel
    hits = _body_reds(body, cancelled)
    assert any(h.startswith("stage") for h in hits), (
        "末步跑了但没有 Pages 那半的 ::error::（实得命中 %s）⇒ 读日志的人只知道 Vercel 没成，"
        "不知道站点这一小时没更新" % hits)

    # 第三种"没发布"的形状：Stage 成了，但 Upload Pages artifact 没执行
    # （17:00 那场静默失败正是靠 upload/deploy 的 skipped 揪出来的 —— Stage 成功 ≠ 制品上线）
    half = {"stage": "success", "vercel": "success", "pages_upload": "skipped"}
    assert _eval(cond, half), (
        "Stage 完成但上传被跳过时末步不红 ⇒ 半拉子发布继续是绿的（实得条件 %r）" % cond)
    assert any(h.startswith("pages_upload") for h in _body_reds(body, half)), (
        "这种形状只说 Vercel/缺件，读日志的人不知道是上传没跑")

    # 反向那半：Vercel 被**跳过**不该算红（封顶只在 failure/cancelled 时出声），
    # 否则这条改动会把"上游判红所以 Vercel 没跑"重复报成 Vercel 的失败
    assert not _eval(cond, {"stage": "success", "vercel": "skipped", "pages_upload": "success"}), (
        "Vercel 的 skipped 被当成未部署 ⇒ 条件被写成了 != 'success'，会在别的失败上重复报红")


def test_vercel_step_does_not_wait_for_the_server_build():
    """CI 不许站在原地等 Vercel 构建完成 —— 那是"连续 6 场部署失败"的直接原因。

    现取读数（2026-10-03 00:22，最近 8 场的步级 conclusion）：只有 18:00 那场 Vercel=success，
    1585–1589 全是 `cancelled`、1590 `skipped`；两域指纹也证实
    （Pages 已发到 07:08=1589，Vercel 停在 02:07=1584 ⇒ API 主机在生产上已停更 6 小时）。
    机制：`vercel --prod` 会**等部署构建完成**才退出，而构建要 40 分钟（实测上传只用 1.5 秒），
    workflow 每小时一次且 `cancel-in-progress: true` ⇒ 每一场都在等待途中被下一场掐掉，
    于是"永远等不到终点"。官方口径就是那条 `--no-wait`：
    "does not wait for a deployment to finish before exiting from the deploy command"。

    代价与配套（必须一起读，否则这条改动会把失败遮起来）：加了 --no-wait 之后 CI **当场看不出部署成没成**，
    落地与否改由生产侧判 —— `tools/prod_verify.py` 取 Vercel 域首页的每场必变指纹 + 各场步级结论，
    把"Vercel 连续 N 场未落地"报成 warn/blocking，并且它就是推送闸（判据
    tests/tools/test_prod_verify_verdict.py::test_vercel_landing_stall_is_warn_with_evidence）。
    也就是说：这条改动与那条门槛是**一对**，只做前半截会让 Vercel 失败重新变静默。
    """
    ver = _steps()[_idx(_steps(), VERCEL)]
    run = ver.get("run") or ""
    assert "--no-wait" in run, (
        "Vercel 步仍在等部署构建完成 ⇒ 它一定会被下一场的 cancel-in-progress 掐掉，"
        "生产上的表现就是 API 主机长期停在旧版而 CI 每场看着都'快成功了'")
    assert "--prod" in run, "--no-wait 不该顺手把生产发布也去掉"
