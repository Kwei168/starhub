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
    """无新星 = fast_refresh 零写入 = 工作区无 index.html——这是【正常路径】，
    必须以 publish=false 干净跳过发布（线上保持上一版制品），而不是 cp 报错 +
    continue-on-error 吞一场红字（2026-10-04 用户在 Actions 看到的每 15 分钟噪音）。"""
    yml = _wf_text()
    stage = yml.split("Stage star page over live site", 1)[1]
    # 缺 index.html 的路径：先存在性检查（不许 cp 先炸）、notice 语义、置 publish=false、exit 0
    assert re.search(r"\[ ! -s index.html \]", stage), "必须先做存在性检查，不许让 cp 当探测员（set -e 下 cp 先炸）"
    assert "::notice::" in stage and "publish=false" in stage, "无新星必须 notice + publish=false 干净跳过"
    assert "continue-on-error: true" not in stage, "不再需要兜底吞错——缺文件走正常 false 路径，真缺陷应当场红"
    # 带回文件失败是 warning（下架容忍），不是 error
    assert re.search(r'::warning::线上无 \$f', stage), "带回失败必须走 warning（下架不拖死车道）"
    for f in ("ai-daily.html", "rss-aggregator.html", "daily-insight-history.html"):
        assert f in stage, "入口页带回清单缺 %s（下架语义覆盖不了它了）" % f


def test_upload_depends_on_publish_flag():
    """upload 只在 stage 真产出时跑（publish=true 门），deploy 依旧依赖 upload outcome——
    双闸保住 §8.15「空制品绿发布抹平站点」的红线。"""
    yml = _wf_text()
    upload = yml.split("Upload Pages artifact", 1)[1].split("Deploy to GitHub Pages", 1)[0]
    assert "steps.stage.outputs.publish == 'true'" in upload, "upload 必须被 publish 标志门住"
    assert "if-no-files-found: error" in yml, "空制品防线不撤"
    deploy = yml.split("Deploy to GitHub Pages", 1)[1].split("Mark the run red", 1)[0]
    assert "steps.pages_upload.outcome == 'success'" in deploy, "deploy 必须依赖 upload outcome"


def test_fast_refresh_called_with_token():
    yml = _wf_text()
    assert "python fast_refresh.py" in yml
    m = re.search(r"Fast refresh.*?env:.*?GITHUB_TOKEN: \$\{\{ secrets\.GITHUB_TOKEN \}\}", yml, re.S)
    assert m, "fast_refresh 必须带 GITHUB_TOKEN（匿名限流=旧页静默上线的雷）"


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
    2026-10-04 03:0x 实锤。钉：add 清单只许仍被跟踪的两个状态文件，
    且任何 .gitignore 排除的名字不得出现（泛化守卫，防下一批摘名再犯）。"""
    yml = _wf_text()
    ign = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    commit = yml.split("Commit star state if changed", 1)[1].split("- name: Stage star page", 1)[0]
    all_added = " ".join(re.findall(r"git add (.+)", commit))
    assert "known_categories.json" in all_added and "known_notes.json" in all_added, \
        "两个仍被跟踪的状态文件必须在 add 清单"
    assert "descriptions_zh.json" not in all_added, "descriptions_zh.json 已出 git 树，add 它必红"
    ignored = {l.strip() for l in ign.splitlines() if l.strip() and not l.strip().startswith("#")}
    for path in re.findall(r"[\w./-]+\.\w+", all_added):
        assert path not in ignored, "%s 在 .gitignore 里，不得出现在 star-fast 的 add 清单" % path
