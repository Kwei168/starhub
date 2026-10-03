# -*- coding: utf-8 -*-
"""推下一批之前必须先跑的生产验证：判据只判"读数→结论"这一层（不发网络请求）。

为什么要有这道门槛（2026-10-03 用户的定性批评，我认）：
Vercel 部署**连续 6 场没落地**（现取步级 conclusion：1584 success，1585–1589 cancelled，1590 skipped），
而我照样一批接一批往下推 —— 等于把"CI 绿"当成"改动生效"。日志和线上读数一直拿得到，
我没有把它们变成**阻塞条件**，所以事故是你发现的、不是我发现的。

门槛的形状（`tools/prod_verify.py:verdict()`）：
  · blocking —— 站点或 API 现在是坏的（四页任一非 200、或 Vercel 函数端点非 200）⇒ 拒绝推送；
  · warn     —— 站点活着但上一场没发布 / Vercel 长期没落地 / 该关的公开面还没关 ⇒ 允许推送，
                但必须把话写在推送日志里（已知未修的问题不该永久卡住进度，那只会逼人绕过门槛）；
  · ok       —— 都没问题。
本文件还钉两条反向控制：**取不到读数绝不等于 ok**（空读数必须判 blocking），
以及"站点全绿 + 公开面仍开着"不许被读成 ok ⇒ 它至少是 warn。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 必须走 STARHUB_TOOLS_DIR：这一层写死真实 tools/ 的话，电池改的是副本、判据读的是原件，
# 于是"站点 404 降级成 warn"这种致命变异永远不会红（2026-10-03 由 mut_prod_gate 的 P3/P4 当场抓到）
sys.path.insert(0, os.environ.get("STARHUB_TOOLS_DIR") or os.path.join(ROOT, "tools"))
import prod_verify as V  # noqa: E402


def _readings(pages=None, api=None, last_runs=None, public=(), fingerprint_gap=None):
    return {
        "pages": pages if pages is not None else {"index.html": 200, "ai-daily.html": 200,
                                                  "rss-aggregator.html": 200,
                                                  "daily-insight-history.html": 200},
        "api": api if api is not None else {"api/rss": 200, "api/news": 200},
        "last_runs": last_runs if last_runs is not None else [
            {"num": 1591, "pages": "success", "vercel": "success"}],
        "public_internal": list(public),
        "fingerprint_gap_hours": fingerprint_gap if fingerprint_gap is not None else 0.0,
    }


def test_healthy_production_is_ok():
    level, why = V.verdict(_readings())
    assert level == "ok", "一切正常却被判成 %s（%s）⇒ 门槛会误伤，明天就有人想绕过它" % (level, why)


def test_dead_page_is_blocking():
    r = _readings(pages={"index.html": 404, "ai-daily.html": 200,
                         "rss-aggregator.html": 200, "daily-insight-history.html": 200})
    level, why = V.verdict(r)
    assert level == "blocking" and "index.html" in why, (
        "首页 404 还不是 blocking ⇒ 这门槛拦不住任何东西")


def test_dead_api_function_is_blocking():
    level, why = V.verdict(_readings(api={"api/rss": 500, "api/news": 200}))
    assert level == "blocking" and "api/rss" in why, (
        "Vercel 函数已经 500 还不 blocking ⇒ 站点半坏时我们还往生产推东西")


def test_last_run_not_published_is_warn_not_ok():
    """站点这一小时没更新（1590 那种被掐掉的形状）：可以推，但必须把话说出来。"""
    level, why = V.verdict(_readings(last_runs=[{"num": 1590, "pages": "skipped", "vercel": "skipped"}]))
    assert level == "warn", "Pages 上一场没发却读成 ok ⇒ 这正好是我们 6 小时没发现 Vercel 停更的形状"
    assert "1590" in why


def test_vercel_landing_stall_is_warn_with_evidence():
    runs = [{"num": n, "pages": "success", "vercel": "cancelled"} for n in range(1585, 1591)]
    level, why = V.verdict(_readings(last_runs=runs))
    assert level == "warn", "Vercel 连 6 场没落地还读成 ok ⇒ 就是这次的事故"
    assert "6" in why or "1585" in why, "warn 里必须带场次证据（%s），不然只是一句形容词" % why


def test_open_public_surface_is_not_ok():
    """四页都 200、上一场也发了，但该关的还开着 ⇒ 不能算 ok（这是本批未完成的验收）。"""
    level, why = V.verdict(_readings(public=["HANDOFF.md", ".github/workflows/update.yml"]))
    assert level == "warn" and "HANDOFF.md" in why, (
        "公开面还开着却读成 ok ⇒ 验收会把『平台自带排除』当成我们的功劳")


def test_empty_readings_are_blocking_not_ok():
    """取不到数 ≠ 没问题。这条是门槛自己的反向控制（本仓反复栽在空读数冒充绿）。"""
    level, why = V.verdict({"pages": {}, "api": {}, "last_runs": [], "public_internal": [],
                            "fingerprint_gap_hours": None})
    assert level == "blocking", "空读数被读成 ok ⇒ 网络一抖门槛就放行"
    assert "取不到" in why or "取数" in why


def test_stamp_shape_and_freshness():
    """门槛靠时间戳生效：过期的验证不算验证。"""
    assert V.stamp_is_fresh({"ts": 1000}, now=1000 + 60), "60 秒前刚验过却判过期"
    assert not V.stamp_is_fresh({"ts": 1000}, now=1000 + V.MAX_AGE_S + 1), (
        "过期戳还算新鲜 ⇒ 门槛可以一次性做完然后永久复用")
    assert not V.stamp_is_fresh({}, now=2000), "没有 ts 字段也算新鲜是空转"


# ── 门槛必须接在推送器上，否则它只是另一个"我会记得跑的"东西 ──────────────────────
import subprocess
sys.path.insert(0, os.environ.get("STARHUB_TOOLS_DIR") or os.path.join(ROOT, "tools"))
import data_api_push as D  # noqa: E402


def _drive_push(tmp_path, monkeypatch, stamp_body=None):
    """只驱动到"过没过门槛"这一步：--check-only 会在写完结论后立刻返回。

    必须把 ROOT 也钉回真仓库根：电池是**从副本目录导入模块**的，
    而推送器的 ROOT = 自己文件的上上级 ⇒ 在 `.deploy-tmp/_mut_*/` 里会变成 `.deploy-tmp`，
    于是 `HANDOFF.md` 被当成"不存在且被 gitignore"，在走到门槛之前就先退了（读数会像门槛失效）。
    """
    stamp = tmp_path / "_prod_verify.json"
    if stamp_body is not None:
        stamp.write_text(json.dumps(stamp_body), encoding="utf-8")
    monkeypatch.setattr(D, "ROOT", ROOT)
    monkeypatch.setattr(D, "PROD_STAMP", str(stamp))
    monkeypatch.setattr(D, "gate", lambda: (True, "测试守门通过"))
    monkeypatch.setattr(D, "runs", lambda per_page=10: [])
    monkeypatch.setattr(sys, "argv", ["data_api_push.py", "--check-only", "HANDOFF.md"])
    return D.main()


def test_pusher_refuses_when_no_prod_stamp(tmp_path, monkeypatch, capsys):
    assert _drive_push(tmp_path, monkeypatch, None) == 1
    assert "prod_verify" in capsys.readouterr().out, (
        "拒绝得说清去做什么：没提示跑 tools/prod_verify.py 的话，下次只会加一个 --skip")


def test_pusher_refuses_when_production_is_blocking(tmp_path, monkeypatch, capsys):
    assert _drive_push(tmp_path, monkeypatch, {"ts": 9 ** 10, "level": "blocking",
                                                "why": "index.html 是 404"}) == 1
    assert "index.html" in capsys.readouterr().out, "blocking 的理由必须原样传给推送者看"


def test_pusher_refuses_on_stale_stamp(tmp_path, monkeypatch):
    assert _drive_push(tmp_path, monkeypatch, {"ts": time.time() - D.MAX_AGE_S - 10,
                                                "level": "ok"}) == 1


def test_pusher_allows_warn_but_shows_the_reason(tmp_path, monkeypatch, capsys):
    """已知未修的问题不该永久卡住进度（那只会逼人绕门槛），但必须把话说在日志里。"""
    rc = _drive_push(tmp_path, monkeypatch, {"ts": time.time(), "level": "warn",
                                             "why": "Vercel 连续 6 场（1585–1590）未落地"})
    assert rc == 0, "warn 被判成拒绝 ⇒ 门槛在 #27 修好之前会一直挡路，明天就有人加 --skip"
    assert "1585" in capsys.readouterr().out, "放行时没带上 warn 的原文 ⇒ 推送日志里没有生产状态"
