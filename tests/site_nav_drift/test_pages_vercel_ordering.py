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

要治那条延迟，可行的方向是**给 Vercel 步本身封顶**（`timeout-minutes` + `continue-on-error`，
再在 Pages 两步之后补一步把 Vercel 的失败重新标红），而不是移动步骤。
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
