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
WF = os.path.join(ROOT, ".github", "workflows", "star-fast.yml")


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
    yml = _wf_text()
    stage = yml.split("Stage star page over live site", 1)[1]
    assert "index.html 缺失" in stage and "exit 1" in stage, "index.html 缺失必须硬失败"
    # 带回文件失败是 warning（下架容忍），不是 error
    assert re.search(r'::warning::线上无 \$f', stage), "带回失败必须走 warning（下架不拖死车道）"
    for f in ("ai-daily.html", "rss-aggregator.html", "daily-insight-history.html"):
        assert f in stage, "入口页带回清单缺 %s（下架语义覆盖不了它了）" % f


def test_fast_refresh_called_with_token():
    yml = _wf_text()
    assert "python fast_refresh.py" in yml
    m = re.search(r"Fast refresh.*?env:.*?GITHUB_TOKEN: \$\{\{ secrets\.GITHUB_TOKEN \}\}", yml, re.S)
    assert m, "fast_refresh 必须带 GITHUB_TOKEN（匿名限流=旧页静默上线的雷）"


def test_timeout_cap_present():
    yml = _wf_text()
    assert re.search(r"timeout-minutes:\s*12", yml), "快车道超 12 分钟即无意义，必须封顶"
