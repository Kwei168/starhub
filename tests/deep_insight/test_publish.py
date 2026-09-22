# tests/deep_insight/test_publish.py
# -*- coding: utf-8 -*-
"""并发提交协议（CAS + 祖先链终检）与独立页渲染。

为什么单独测这套而不是直接复用 tools/data_api_push.py：它的默认是
"有 in_progress 构建就拒绝推送"（本会话被它挡过两次，日志原文"大概率几分钟后被回滚"）。
夜场必须**在白天场还在跑时照样提交成功**，所以走"只覆盖自己路径 + CAS + 终检自愈"，
而不是等一个不会来的窗口。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_deep_insight as D


class FakeApi:
    """语义对齐真 API：update_ref 是 CAS（父不符即失败），不静默覆盖。"""

    def __init__(self, head="h0"):
        self.head = head
        self.commits = {head: {"parent": None, "tree": "t_base"}}
        self.blobs = 0
        self.trees = []
        self.update_calls = []
        self.advance_by_other = 0      # 前 N 次 update_ref 时别人抢先推进
        self.ancestor_ok = True

    def head_info(self):
        return self.head, self.commits[self.head]["tree"]

    def create_blob(self, content):
        self.blobs += 1
        return "b%d" % self.blobs

    def create_tree(self, base_tree, entries):
        sha = "t%d" % len(self.trees)
        self.trees.append({"base": base_tree, "entries": entries, "sha": sha})
        return sha

    def create_commit(self, parent, tree, msg):
        sha = "c%d" % len(self.commits)
        self.commits[sha] = {"parent": parent, "tree": tree}
        self._pending = sha
        self._expected_parent = parent
        return sha

    def update_ref(self, sha, force=False):
        self.update_calls.append({"sha": sha, "force": force})
        if self.advance_by_other > 0:
            self.advance_by_other -= 1
            other = "o%d" % self.advance_by_other
            self.commits[other] = {"parent": self.head, "tree": "t_other"}
            self.head = other
            return False
        if self.commits[sha]["parent"] != self.head:
            return False
        self.head = sha
        return True

    def is_ancestor(self, sha):
        return bool(self.ancestor_ok) and sha in self.commits


# ── 并发提交协议 ──────────────────────────────────────────────────────────

def test_only_own_paths_are_touched():
    """tree 只许含本次给的路径 —— 这是"不可能回滚白天产物"的结构保证。"""
    api = FakeApi()
    res = D.publish(api, {"daily-deep-2026-09-23.json": b"{}", "deep-insight.html": b"<p/>"},
                    msg="night run")
    assert res["status"] == "published", res
    paths = sorted(p["path"] for t in api.trees for p in t["entries"])
    assert paths == ["daily-deep-2026-09-23.json", "deep-insight.html"], paths
    assert all(p["mode"] == "100644" for t in api.trees for p in t["entries"])


def test_cas_conflict_is_retried_against_fresh_head():
    api = FakeApi()
    api.advance_by_other = 1
    res = D.publish(api, {"daily-deep-x.json": b"{}"}, msg="m")
    assert res["status"] == "published", res
    assert res["attempts"] == 2
    assert api.trees[1]["base"] != api.trees[0]["base"], "重试时没基于新 head 重建树"


def test_never_forces_when_conflicts_persist():
    api = FakeApi()
    api.advance_by_other = 99
    res = D.publish(api, {"daily-deep-x.json": b"{}"}, msg="m", max_attempts=4)
    assert res["status"] == "failed", res
    assert res["attempts"] == 4
    assert api.update_calls and all(c["force"] is False for c in api.update_calls), \
        "冲突后改用 force —— 那就是把别人的提交覆盖掉"


def test_idempotent_when_previous_sha_already_landed():
    api = FakeApi()
    api.commits["prev"] = {"parent": "h0", "tree": "t_prev"}
    api.head = "prev"
    res = D.publish(api, {"daily-deep-x.json": b"{}"}, msg="m", last_sha="prev")
    assert res["status"] == "skipped", res
    assert api.blobs == 0, "已落地还重传，等于白烧一次 API 调用"


def test_reverted_after_publish_is_reported_not_swallowed():
    """update 成功但事后掉出祖先链（白天的 reset --soft 前科）⇒ 必须显式告警。"""
    api = FakeApi()
    api.ancestor_ok = False
    logs = []
    res = D.publish(api, {"daily-deep-x.json": b"{}"}, msg="m", log=logs.append)
    assert res["status"] == "reverted", res
    assert any("::warning" in l for l in logs), logs


def test_empty_payload_touches_nothing():
    api = FakeApi()
    res = D.publish(api, {}, msg="m")
    assert res["status"] == "noop" and api.blobs == 0 and api.update_calls == []


def test_files_are_uploaded_once_per_attempt_not_per_file_replay():
    api = FakeApi()
    api.advance_by_other = 1
    D.publish(api, {"daily-deep-x.json": b"{}", "deep-insight.html": b"<p/>"}, msg="m")
    assert api.blobs == 2, "blob 按内容寻址，重试时该复用；实为 %d" % api.blobs


# ── 独立页渲染：不许长出死链与空卡片 ──────────────────────────────────────

def _payload():
    return {
        "date": "2026-09-23", "generated_at": "2026-09-23T04:31:00+08:00",
        "engine": D.SCHEMA_VERSION,
        "budget": {"llm_calls": 30, "elapsed_s": 2100, "key_count": 3},
        "anchor_diff": [], "predictions_reconciled": {"due": 0, "hit": 0, "miss": 0},
        "events": [{
            "id": "evt1", "topic": "ai", "title": "腾讯混元下调定价 <script>alert(1)</script>",
            "narrative": "第一段论证。\n\n第二段论证。\n\n第三段还带限制条件。",
            "claims": [], "causal_chains": [],
            "forecasts": [{"claim": "三个月内出现跟随者", "horizon_days": 7,
                           "check_metric": "同类发布数>=3", "status": "pending"}],
            "quality": {"verdict": "一手", "score": 82, "why": "有原始参数", "basis": ["source_quality.json"]},
            "citations": [{"id": "c1", "url": "https://mp.test/a", "source": "公众号:A",
                           "chars_used": 5706, "full_len": 5706}],
            "rubric": {"mean": 0.83},
        }],
    }


def test_xss_in_title_is_escaped():
    html = D.render_page(_payload())
    assert "<script>alert(1)</script>" not in html, "上游标题可注入脚本"
    assert "&lt;script&gt;" in html


def test_paragraphs_survive_rendering():
    html = D.render_page(_payload())
    assert html.count("<p>") >= 3, "段落在渲染时被并成一块，可读性判据在页面上失效"


def test_citations_render_as_absolute_links_with_rel():
    html = D.render_page(_payload())
    assert 'href="https://mp.test/a"' in html
    assert 'rel="noopener' in html


def test_relative_or_empty_link_is_not_rendered_as_a_link():
    p = _payload()
    p["events"][0]["citations"].append({"id": "c9", "url": "/x.html", "source": "坏源"})
    p["events"][0]["citations"].append({"id": "c8", "url": "", "source": "空源"})
    html = D.render_page(p)
    assert 'href="/x.html"' not in html and "坏源" not in html, "相对链接上屏＝点开 404"


def test_degraded_event_shows_reason_and_no_forecast_card():
    p = _payload()
    e = p["events"][0]
    e["narrative"] = "证据不足，按快讯处理。"
    e["degraded_reason"] = "去重后仅 1 独立源"
    html = D.render_page(p)
    assert "证据不足" in html or "快讯" in html, "降级没在页面上露出来"
    assert "去重后仅 1 独立源" in html
    assert "三个月内出现跟随者" not in html, "degraded 条目仍展示预测卡"


def test_forecast_card_shows_horizon_and_state():
    html = D.render_page(_payload())
    assert "7 天" in html and "待验证" in html


def test_empty_narrative_event_is_not_rendered():
    """空正文不许长出空卡片（spec 禁空转产物）。"""
    p = _payload()
    p["events"][0]["narrative"] = "   "
    p["events"][0]["degraded_reason"] = ""
    html = D.render_page(p)
    assert "腾讯混元下调定价" not in html, "正文为空的条目仍上屏 ⇒ 空卡片"


def test_freshness_label_is_visible():
    html = D.render_page(_payload())
    assert "2026-09-23" in html and "深度" in html
