#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 Wiki 是否覆盖当前 StarHub 双主线架构，并拒绝已知过时事实。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / ".qoder" / "repowiki"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"无法读取 {path.relative_to(ROOT)}: {exc}")
        return ""


def check_files() -> None:
    paths = [
        "HANDOFF.md",
        "fetch_and_build.py",
        "build_rss_aggregator.py",
        "template.html",
        "index.html",
        "rss-aggregator.html",
        "rss_sources.json",
        "rss_history.json",
        "rss_api_snapshot.json",
        ".github/workflows/update.yml",
        "vercel.json",
        "api/rss.js",
        "api/article.js",
        "known_categories.json",
        "descriptions_zh.json",
        "trending_snapshot.json",
    ]
    for relative in paths:
        require((ROOT / relative).is_file(), f"核心文件不存在: {relative}")


def check_source_facts() -> None:
    workflow = read(ROOT / ".github/workflows/update.yml")
    require('cron: "0 21 * * *"' in workflow, "workflow 缺少 UTC 21:00 full 调度")
    require('cron: "0 2,6,10,14 * * *"' in workflow, "workflow 缺少 UTC 2/6/10/14 incremental 调度")
    require("cancel-in-progress: true" in workflow, "workflow 未启用 cancel-in-progress: true")
    require("python fetch_and_build.py $MODE" in workflow, "workflow 构建入口不一致")

    try:
        vercel = json.loads(read(ROOT / "vercel.json"))
        functions = set(vercel.get("functions", {}))
    except json.JSONDecodeError as exc:
        fail(f"vercel.json 不是有效 JSON: {exc}")
        functions = set()
    expected = {
        "api/refresh.js", "api/search.js", "api/events.js", "api/news.js",
        "api/rss.js", "api/article.js", "api/agihunt.js",
    }
    require(functions == expected, f"Vercel 函数清单不一致: {sorted(functions)}")

    try:
        sources = json.loads(read(ROOT / "rss_sources.json"))
        if isinstance(sources, dict):
            sources = sources.get("sources", [])
        tiers: dict[str, int] = {}
        for source in sources:
            raw_tier = source.get("tier", "")
            tier = f"T{raw_tier}" if str(raw_tier).isdigit() else str(raw_tier).upper()
            tiers[tier] = tiers.get(tier, 0) + 1
        require(len(sources) == 711, f"RSS 源数量为 {len(sources)}，预期 711")
        require(tiers.get("T1") == 23, f"RSS T1 数量为 {tiers.get('T1')}，预期 23")
        require(tiers.get("T2") == 20, f"RSS T2 数量为 {tiers.get('T2')}，预期 20")
        require(tiers.get("T3") == 668, f"RSS T3 数量为 {tiers.get('T3')}，预期 668")
    except (json.JSONDecodeError, TypeError) as exc:
        fail(f"rss_sources.json 无法解析: {exc}")

    build = read(ROOT / "build_rss_aggregator.py")
    template = read(ROOT / "template.html")
    article = read(ROOT / "api/article.js")
    star = read(ROOT / "fetch_and_build.py")
    require("full_content" in build and "fc" in build, "RSS 构建器缺少 full_content/fc 字段链路")
    require("def fetch_stars" in star, "Star 主线缺少 starred repos 拉取入口")
    require("following" in star and "events" in star, "Star 主线缺少 following/events 能力")
    require("known_categories.json" in star and "descriptions_zh.json" in star, "Star 主线缺少分类/翻译缓存")
    require("trending_snapshot.json" in star, "Star 主线缺少 Trending 快照")
    require("wb_starhub_favs_v1" in template, "Star 主站缺少收藏 localStorage 契约")
    require("Access-Control-Allow-Origin" in article, "全文 API 缺少 CORS")
    require("Access-Control-Allow-Methods" in article and "GET, OPTIONS" in article, "全文 API 缺少 GET/OPTIONS CORS")
    require("status(204)" in article, "全文 API 缺少 OPTIONS 204")


def wiki_text() -> str:
    files = list(WIKI.rglob("*.md")) + list(WIKI.rglob("*.yaml"))
    return "\n".join(read(path) for path in files)


def check_wiki_content() -> None:
    text = wiki_text()
    groups = {
        "Star 主线": [
            "starred", "search", "following", "events", "known_categories.json",
            "descriptions_zh.json", "trending_snapshot.json", "收藏", "筛选", "排序",
            "主题", "导入", "导出", "置顶", "index.html",
        ],
        "RSS 主线": [
            "711", "T1", "T2", "T3", "72 小时", "rss_history.json",
            "rss_api_snapshot.json", "rss-aggregator.html",
        ],
        "全文与侧栏": [
            "full_content", "fc", "/api/article", "Access-Control-Allow-Origin",
            "ai-feed-panel", "1280px", "verify_ai_sidebar_e2e.cjs",
        ],
        "部署": [
            "UTC 21:00", "UTC 2/6/10/14", "cancel-in-progress: true",
            "workflow_dispatch", "dynamic", "7 个函数",
        ],
    }
    for name, needles in groups.items():
        missing = [needle for needle in needles if needle not in text]
        require(not missing, f"Wiki 缺少 {name} 事实: {', '.join(missing)}")

    forbidden = [
        r"AGENT_HANDOVER\.md",
        r"(?<!\d)710(?!\d)",
        r"10 \* \* \* \*",
        r"cancel-in-progress\s*[:=]\s*false",
        r"starhub_rss_read_urls",
        r"每小时 UTC\s*:10",
        r"分层Cron\(UTC",
    ]
    for pattern in forbidden:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        require(match is None, f"Wiki 含已废弃事实: {match.group(0) if match else pattern}")

    for path in list(WIKI.rglob("*.md")) + list(WIKI.rglob("*.yaml")):
        content = read(path)
        require(content.count("```") % 2 == 0, f"Markdown 代码围栏未闭合: {path.relative_to(ROOT)}")
        for target in re.findall(r"file://([^)]*)", content):
            target = unquote(target.split("#", 1)[0]).strip()
            if not target or target.startswith(("http:", "https:")):
                continue
            require((ROOT / target).exists(), f"失效 Wiki 文件引用: {path.relative_to(ROOT)} -> {target}")

    secrets = [r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"xox[baprs]-[A-Za-z0-9-]{20,}"]
    for pattern in secrets:
        require(re.search(pattern, text) is None, f"Wiki 疑似包含敏感令牌: {pattern}")


def main() -> int:
    check_files()
    check_source_facts()
    check_wiki_content()
    if ERRORS:
        print(f"Wiki sync check FAILED ({len(ERRORS)} errors)")
        for error in ERRORS:
            print(f"- {error}")
        return 1
    print("Wiki sync check PASS")
    print("- Star 主线：starred/search/following/events、分类、翻译、Trending、收藏")
    print("- RSS 主线：711 源、T1/T2/T3、72 小时历史、chunk、AI 侧栏、全文 API")
    print("- 部署：双 schedule、7 个函数、并发控制、动态 run 验证")
    print("- Wiki：过时引用、失效文件链接、代码围栏和敏感令牌检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
