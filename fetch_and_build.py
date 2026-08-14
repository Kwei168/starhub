#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Star 收藏台 —— 自动更新脚本
在 GitHub Actions 中每天运行：拉取 Kwei168 的 star 列表 → 智能分类 → 重新生成 index.html。
仅依赖 Python 标准库，无需安装第三方包。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

USER = "Kwei168"

CATS = [
    {"key": "agent",     "label": "AI Agent & Skills",      "color": "#0969da"},
    {"key": "distill",   "label": "思维蒸馏 & 认知",        "color": "#8250df"},
    {"key": "video",     "label": "AI 视频创作",            "color": "#cf222e"},
    {"key": "coding",    "label": "AI 编程 & 工具链",       "color": "#1a7f37"},
    {"key": "content",   "label": "内容创作 & 排版",        "color": "#bf3989"},
    {"key": "learning",  "label": "AI 学习 & 教程",         "color": "#9a6700"},
    {"key": "assistant", "label": "AI 助手 & 应用",         "color": "#1b7c83"},
    {"key": "tools",     "label": "实用工具 & 资源",        "color": "#57606a"},
    {"key": "finance",   "label": "金融 & 交易",            "color": "#bc4c00"},
    {"key": "business",  "label": "商业 · 一人公司与知产",  "color": "#953800"},
    {"key": "frontend",  "label": "前端 & 设计系统",        "color": "#316dca"},
]

LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "HTML": "#e34c26", "Shell": "#89e051", "Go": "#00ADD8", "Java": "#b07219",
    "Jupyter Notebook": "#DA5B0B", "Vue": "#41b883", "PowerShell": "#012456",
    "CSS": "#563d7c", "C#": "#178600", "C++": "#f34b7d",
}

DEFAULT_FAVS = ["react/react", "github/spec-kit", "521xueweihan/HelloGitHub"]

# 已知的空描述项目，补充一句中文说明
FALLBACK_DESC = {
    "llazyl/TVBox": "TVBox 影视聚合播放器",
    "q215613905/TVBoxOS": "TVBoxOS 影视播放系统",
    "FongMi/TV": "基于 media3/ffmpeg/mpv 的开源影视播放器",
}


def has_cn(s):
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def translate_to_zh(text):
    """把英文简介翻译成中文；全部端点失败返回 None（保留原文）。"""
    if not text:
        return None
    # 端点 1：Google 翻译非官方接口
    try:
        params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
        req = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + params,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        result = "".join(seg[0] for seg in data[0] if seg[0]).strip()
        if result and has_cn(result):
            return result
    except Exception:  # noqa: BLE001
        pass
    # 端点 2：MyMemory 免费接口
    try:
        params = urllib.parse.urlencode({"q": text, "langpair": "en|zh-CN"})
        req = urllib.request.Request(
            "https://api.mymemory.translated.net/get?" + params,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        result = (data.get("responseData", {}).get("translatedText") or "").strip()
        if result and has_cn(result) and "MYMEMORY WARNING" not in result:
            return result
    except Exception:  # noqa: BLE001
        pass
    return None


def classify_new(fn, desc, lang, topics):
    """对未知新项目做关键词规则分类（已有项目走 known_categories.json 保持稳定）。"""
    text = (fn + " " + (desc or "") + " " + " ".join(topics or [])).lower()
    if any(k in text for k in ["trading", "finance", "fincept", "quant", "金融", "交易", "bloomberg"]):
        return "finance"
    if any(k in text for k in ["tvbox", "iptv", "直播", "电视", "crawler", "爬虫", "download", "下载",
                               "translator", "翻译", "汉化", "网盘", "pan", "mpv", "ffmpeg", "userscript"]):
        return "tools"
    if any(k in text for k in ["open-design", "baoyu-design", "awesome-design", "design.md",
                               "design-system", "design system", "frontend", "react"]):
        return "frontend"
    if any(k in text for k in ["ppt", "powerpoint", "排版", "公众号", "wechat", "写作", "write",
                               "typeset", "editor", "design"]):
        return "content"
    if any(k in text for k in ["video", "短剧", "drama", "film", "anime", "动漫", "movie", "montage",
                               "hyperframe", "影视", "shot"]):
        return "video"
    if any(k in text for k in ["book", "书籍", "教程", "guide", "指南", "from-scratch", "llms",
                               "learning", "入门", "weekly", "hellogithub", "实践", "tutorial",
                               "dive-into", "deep"]):
        return "learning"
    if any(k in text for k in ["distill", "蒸馏", "认知", "思维", "nuwa", "女娲", "cangjie", "仓颉",
                               "first-principles", "第一性", "perspective", "文风", "methodology"]):
        return "distill"
    if any(k in text for k in ["code-review", "officecli", "reasonix", "sub2api", "freellmapi",
                               "2api", "中转", "mimo", "cc-connect", "coding", "编程"]):
        return "coding"
    if any(k in text for k in ["chat", "assistant", "助手", "chatbot", "librechat", "astrbot",
                               "qwenpaw", "nuwax", "opensquilla", "workspace", "desktop", "agent-os"]):
        return "assistant"
    if any(k in text for k in ["opc", "one-person", "一人公司", "创业", "startup", "growth", "增长",
                               "fde", "business", "软著", "copyright", "专利", "patent", "合规",
                               "compliance", "legal"]):
        return "business"
    return "agent"


def fetch_stars():
    repos = []
    page = 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "starhub-auto-update"}
    while True:
        url = "https://api.github.com/users/%s/starred?per_page=100&page=%d" % (USER, page)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print("拉取失败: %s" % e, file=sys.stderr)
            return None
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.5)
    return repos


def main():
    known = {}
    try:
        known = json.load(open("known_categories.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass

    desc_zh = {}
    try:
        desc_zh = json.load(open("descriptions_zh.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass

    repos = fetch_stars()
    if repos is None:
        print("拉取 star 失败，保持现有 index.html 不变")
        return

    cat_label = {c["key"]: c["label"] for c in CATS}
    out = []
    for r in repos:
        fn = r.get("full_name")
        if not fn:
            continue
        cat = known.get(fn) or classify_new(fn, r.get("description"), r.get("language"), r.get("topics"))
        known[fn] = cat
        desc = (desc_zh.get(fn) or r.get("description") or FALLBACK_DESC.get(fn, "")).strip()
        if desc:
            desc = " ".join(desc.split())
        # 新项目英文简介自动翻译为中文，并持久化到 desc_zh 避免重复翻译
        if desc and not has_cn(desc) and fn not in desc_zh:
            translated = translate_to_zh(desc)
            if translated:
                desc = translated
                desc_zh[fn] = translated
                print("[翻译] %s -> %s" % (fn, translated[:60]))
            else:
                print("[翻译失败-保留原文] %s" % fn)
        out.append({
            "id": fn,
            "name": r.get("name"),
            "owner": fn.split("/")[0],
            "full_name": fn,
            "html_url": r.get("html_url"),
            "desc": desc,
            "language": r.get("language"),
            "stars": r.get("stargazers_count"),
            "topics": r.get("topics", []),
            "pushed_at": (r.get("pushed_at") or "")[:10],
            "category": cat,
            "categoryLabel": cat_label[cat],
        })

    template = open("template.html", encoding="utf-8").read()
    html = (template
            .replace("__DATA__", json.dumps(out, ensure_ascii=False, separators=(",", ":")))
            .replace("__CATS__", json.dumps(CATS, ensure_ascii=False, separators=(",", ":")))
            .replace("__LANGS__", json.dumps(LANG_COLORS, ensure_ascii=False, separators=(",", ":")))
            .replace("__FAVS__", json.dumps(DEFAULT_FAVS, ensure_ascii=False, separators=(",", ":"))))

    open("index.html", "w", encoding="utf-8").write(html)
    json.dump(known, open("known_categories.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(desc_zh, open("descriptions_zh.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("更新完成：共 %d 个项目" % len(out))


if __name__ == "__main__":
    main()
