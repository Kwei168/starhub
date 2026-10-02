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
import os

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
