# tests/deep_insight/test_daytime_untouched.py
# -*- coding: utf-8 -*-
"""阶段 1 的"纯新增"必须可核对，而不是靠人说"我没改白天的文件"。

spec §6.1 把这条列为阶段 1 必过的判据（白天零影响守卫：三份白天产物逐字节不变）。
它不是形式主义：本会话里我只是为了"跑一遍全仓回归"就把
`daily-insight.json` 与 `daily_insight_history.json` 改写了 —— 白天产物被夜场
或夜场跑出来的测试顺手改掉，是这个改造最容易伪装的回归形态。
"""
import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D  # noqa: E402

# 白天管线的三份代表产物：锚点、LlamaIndex 侧快照、源清单。
# 选这三份的理由：它们分别由 build_daily_insight.py / insight_engine.py /
# build_rss_aggregator.py 写，覆盖了"夜场若引错模块就会碰到"的三条线。
DAY_PRODUCTS = ("daily-insight.json", "analysis_snapshot.json", "rss_sources.json")


def _digests():
    out = {}
    for p in DAY_PRODUCTS:
        full = os.path.join(ROOT, p)
        if os.path.exists(full):
            with open(full, "rb") as f:
                out[p] = hashlib.sha256(f.read()).hexdigest()
    return out


def _article(url, source, body):
    return {"url": url, "source": source, "title": "T-" + source, "text": body,
            "has_full": True}


def _fixture():
    links = []
    pool = {}
    for i in range(3):
        for s in ("srcA", "srcB", "srcC"):
            u = "https://%s.test/%d" % (s, i)
            links.append(u)
            pool[u] = _article(u, s, "证据正文。" * 1500)
    anchor = json.dumps({"date": "2026-09-22", "events": [
        {"id": "e1", "title": "某事件", "topic": "ai", "summary": "摘要",
         "key_links": links[:3]}]}, ensure_ascii=False)
    return pool, anchor


def test_day_products_exist_otherwise_this_guard_is_vacuous():
    """恒真的守卫比没有守卫更糟：先确认三份产物真在仓库里。"""
    got = _digests()
    assert len(got) == len(DAY_PRODUCTS), "缺样本产物，本判据空跑：%s" % sorted(got)


def test_night_run_leaves_daytime_products_byte_identical(tmp_path):
    pool, anchor = _fixture()
    before = _digests()
    D.night_run(purpose="test", client=D.FakeClient(), out_dir=str(tmp_path / "ns"),
                keys=["k1", "k2", "k3"], anchor_raw=anchor, pool=pool,
                date_str="2026-09-23", pred_raw="", quality_raw={}, log=lambda s: None,
                sleep=lambda s: None)
    after = _digests()
    assert before == after, "夜场改写了白天产物：%s" % [
        (k, before.get(k) != after.get(k)) for k in sorted(set(before) | set(after))]


def test_night_run_writes_nothing_outside_its_own_out_dir(tmp_path):
    """产物只许落在 out_dir：写到仓库根就等于和白天产物抢地盘。

    判据写成"运行前后仓库根没有新增夜场文件"，而不是"这些文件不许存在于仓库根" ——
    后者在首次发布之后就会恒红（那时 `predictions.jsonl` 本该在仓库根，是夜场自己提交的）。
    """
    out_dir = tmp_path / "ns"
    pool, anchor = _fixture()
    names = ("daily-deep-2026-09-23.json", "deep-insight.html", D.PREDICTIONS_NAME)
    before = {n: os.path.exists(os.path.join(ROOT, n)) for n in names}
    D.night_run(purpose="test", client=D.FakeClient(), out_dir=str(out_dir),
                keys=["k1", "k2", "k3"], anchor_raw=anchor, pool=pool,
                date_str="2026-09-23", pred_raw="", quality_raw={}, log=lambda s: None,
                sleep=lambda s: None)
    after = {n: os.path.exists(os.path.join(ROOT, n)) for n in names}
    assert before == after, "夜场往仓库根写了东西：%s -> %s" % (before, after)
    assert sorted(os.listdir(str(out_dir))) == sorted(
        ["daily-deep-2026-09-23.json", "deep-insight.html", D.PREDICTIONS_NAME,
         "deep-2026-09-23.jsonl"]), os.listdir(str(out_dir))


def test_nightly_ledger_shape_is_its_own_when_present():
    """仓库里真出现 `predictions.jsonl` 时，它必须整份都是夜场账本形状。

    这里刻意**不**写"夜场文件名不许出现在仓库里"那种判据：`deep-insight.html` 与
    `predictions.jsonl` 一旦首次发布就正该在仓库根（夜场自己提交的），
    那样写会让第二次夜场起 preflight 恒红、夜场永远跑不到调模型那一步（对抗审查抓到我就是这个坑）。
    "会不会覆盖白天产物"这个真问题由
    `test_workflow_isolation.py::test_daytime_commit_list_never_covers_nightly_artifacts`
    按 update.yml 的 git add 清单来判，那才是可长期成立的不变量。
    """
    p = os.path.join(ROOT, D.PREDICTIONS_NAME)
    if not os.path.exists(p):
        return  # 首次发布之前本来就没有
    with open(p, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    for line in lines:
        row = json.loads(line)  # 解析不了 = 这文件不是夜场独占的，判据该红
        assert {"claim", "event_id", "horizon_days", "made_on", "status"} <= set(row), \
            "仓库里的 %s 不是夜场账本形状：%s" % (D.PREDICTIONS_NAME, sorted(row))
