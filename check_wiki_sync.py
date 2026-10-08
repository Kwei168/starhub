#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 Wiki 是否覆盖**当前**架构。

口径（2026-10-03 重写）：期望值一律从仓库现读，不把历史数字当事实钉住。
旧版写着 "711 源 / T1=23 / T2=20 / T3=668 / 恰好 7 个函数 / 禁止出现 710"，
源一删、端点一加，它就反过来把新架构判成错（201 条红里大多数是这种"拿错尺子"）。

现版三类断言：
  A. 覆盖类：仓库里真实存在的端点/脚本/workflow/schedule，Wiki 全套里必须有人提到。
     期望集合随代码漂移，不写死成员。
  B. 一致类：Wiki **以现状口吻**写了数字，就必须等于现测；没写不算错，写历史读数要带墓碑词。
     workflow 个数、known_*/descriptions 的"条"数、rss_sources 的"项"数也在现测范围
     （后两类只认紧跟在文件名后 80 字内的量词，避免一行长段落里跨主题误伤）。
  C. 失效引用：Wiki 提到的仓库路径必须存在；同一行带墓碑词（已删/不存在/退役…）则放过，
     否则"某某已终止"这类必要的历史交代会被判成缺陷，判据就会被人当噪音关掉。
     已知局限：`file.py:123` 这类**行号引用**只查文件存在、不查行号语义（锚点内容无法
     机器判定），大范围代码移动会留下"文件在、行号漂"的引用——抽查行号仍靠人/审查代理。

归档免检：文件头 5 行内带 `repowiki-archive` 标记的（2026-09-13 那批平台产物已打标）
按"历史快照"处理——跳过 B/C 与 file:// 链接检查，围栏平衡与令牌扫描仍然全量。
活体口径：workflow 集合取 `git ls-files`（工作树里的未跟踪残留不算数）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / ".qoder" / "repowiki"
ERRORS: list[str] = []

# 墓碑/历史口径的词。命中的行不参与 B/C 两类判据（A 类覆盖仍全量要求）。
TOMBSTONE = re.compile(
    r"已删|已移除|已从|不再|不存在|无写方|无页面引用|退役|终止|作废|历史|曾|旧|原口径|"
    r"残留|遗留|墓碑|摘除|关在|退回|停更|上一版|曾经|排除|忽略")

# 只认 ASCII 起头的文件名：Python 的 \\w 含中文，会把"修复了build_rss_aggregator.py"
# 整串当一个路径去查。每个扩展名都要带 (?![\\w]) 边界，否则 `package.json` 会被
# `\\.js` 那一支截成 `package.js` 再判"不存在"。
PATH_RE = re.compile(
    r"(?<![\w./-])((?:api|lib|tools|tests|docs|\.github/workflows)/[A-Za-z0-9_.+-]+?"
    r"\.(?:js|py|yml|json|md)(?![\w])|[a-z0-9_][A-Za-z0-9_.+-]*?\.(?:py|js|json|html|ya?ml|md)(?![\w]))")

BUILD_SCRIPTS = ("fetch_and_build.py", "build_rss_aggregator.py", "build_ai_daily.py",
                 "build_daily_insight.py", "build_logger.py", "insight_engine.py")


def fail(message: str) -> None:
    if message not in ERRORS:          # 同一句话在几十份文件里重复不额外提供信息
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


def wiki_files() -> list[Path]:
    return sorted(list(WIKI.rglob("*.md")) + list(WIKI.rglob("*.yaml")))


# --------------------------------------------------------------------------
# 现读：期望值全部来自仓库当前内容
# --------------------------------------------------------------------------

def live_endpoints() -> list[str]:
    return sorted(p.name for p in (ROOT / "api").glob("*.js"))


def live_scripts() -> list[str]:
    return [n for n in BUILD_SCRIPTS if (ROOT / n).is_file()]


def live_workflows() -> list[str]:
    """活体 = git 跟踪的 workflow。工作树里的未跟踪残留（如退役后复又出现的
    build-log-summary.yml 副本）不会在远端跑，把它当活体会逼 Wiki 给墓碑写现状口吻。"""
    try:
        out = subprocess.run(["git", "ls-files", ".github/workflows"],
                             capture_output=True, text=True, cwd=ROOT, timeout=15)
        if out.returncode == 0:
            names = sorted(p.name for p in
                           (Path(n) for n in out.stdout.splitlines())
                           if p.suffix == ".yml")
            if names:
                return names
    except (OSError, subprocess.SubprocessError):
        # 无 git 环境的兜底：此时"活体"口径退化为文件系统，可能把未跟踪残留当成
        # 活体——与 git 口径相反，调用方（无 .git 的源码 drop）只能接受这个近似。
        pass
    return sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml"))


def live_crons() -> list[str]:
    crons: list[str] = []
    for name in live_workflows():
        workflow = read(ROOT / ".github" / "workflows" / name)
        crons.extend(re.findall(r'-\s*cron:\s*"([^"]+)"', workflow))
    return crons


def live_cancel_in_progress() -> str | None:
    workflow = read(ROOT / ".github" / "workflows" / "update.yml")
    match = re.search(r"cancel-in-progress:\s*(\S+)", workflow)
    return match.group(1) if match else None


def live_rss_counts() -> tuple[int, dict[str, int]]:
    try:
        data = json.loads(read(ROOT / "rss_sources.json"))
    except json.JSONDecodeError as exc:
        fail(f"rss_sources.json 不是有效 JSON: {exc}")
        return 0, {}
    sources = data.get("sources", []) if isinstance(data, dict) else data
    tiers: dict[str, int] = {}
    for source in sources:
        raw = str(source.get("tier", ""))
        tier = f"T{raw}" if raw.isdigit() else raw.upper()
        tiers[tier] = tiers.get(tier, 0) + 1
    return len(sources), tiers


def live_function_count() -> int | None:
    try:
        vercel = json.loads(read(ROOT / "vercel.json"))
    except json.JSONDecodeError as exc:
        fail(f"vercel.json 不是有效 JSON: {exc}")
        return None
    return len(vercel.get("functions", {}))


def live_json_count(name: str) -> int | None:
    """dict/list 皆可：known_*/descriptions 是查表 dict，条数就是键数。"""
    path = ROOT / name
    if not path.is_file():
        return None
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError:
        return None
    if isinstance(data, (list, dict)):
        return len(data)
    return None


def live_update_step_count() -> int | None:
    """update.yml 的 job 步数（jobs: 下 6 空格缩进的条目）。"""
    path = ROOT / ".github" / "workflows" / "update.yml"
    if not path.is_file():
        return None
    in_jobs = False
    steps = 0
    for line in read(path).splitlines():
        if re.match(r"^jobs:", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^      - ", line):
            steps += 1
    return steps


# 只认"紧跟/紧邻文件名 ±80 字内"的量词：知识卡常把整节写成一行，
# 无窗口的全文扫描会把"RETENTION 点名 5 条"误当成 known_* 的条数。
SCOPED_COUNTS = (
    ("known_categories.json", "条"),
    ("descriptions_zh.json", "条"),
    ("known_notes.json", "条"),
    ("rss_sources.json", "项"),
)
SCOPED_WINDOW = 80
TOMBSTONE_WINDOW = 40

ZH_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _zh_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return ZH_NUM.get(token)


def _near_tombstone(line: str, start: int, end: int) -> bool:
    """墓碑词只豁免它**附近**的声明：整行豁免会让"④ 墓碑与残留……"这样的
    单词把同一行里所有现状数字都放走（行级豁免的真实漏洞，2026-10-06 收窄）。"""
    lo = max(0, start - TOMBSTONE_WINDOW)
    hi = min(len(line), end + TOMBSTONE_WINDOW)
    return bool(TOMBSTONE.search(line[lo:hi]))


def repo_basenames() -> set[str]:
    """裸文件名先按全仓索引解析：写判据时常常只留 basename（`test_x.py`）。

    只走源码目录，不 rglob 整个仓库根——本仓工作区有百 MB 级分块产物与 6.8GB 的 .git，
    全量遍历既慢又会把临时副本（.deploy-tmp/_scratch）当成"存在"。
    """
    names: set[str] = set()
    for path in ROOT.glob("*.*"):
        if path.is_file():
            names.add(path.name)
    for sub in ("api", "lib", "tools", "tests", "docs", ".github", "public", "static"):
        base = ROOT / sub
        if base.is_dir():
            names.update(path.name for path in base.rglob("*") if path.is_file())
    return names


# --------------------------------------------------------------------------
# A. 覆盖类：仓库里有的东西，Wiki 全套不许漏
# --------------------------------------------------------------------------

def check_coverage(text: str) -> None:
    for name in live_endpoints():
        require(name in text, f"[覆盖] Wiki 全套未提到现存端点: api/{name}")
    for name in live_scripts():
        require(name in text, f"[覆盖] Wiki 全套未提到现存构建脚本: {name}")
    for name in live_workflows():
        require(name.replace(".yml", "") in text, f"[覆盖] Wiki 全套未提到现存 workflow: {name}")
    for cron in live_crons():
        require(cron in text, f"[覆盖] Wiki 全套未记录现存 schedule: cron \"{cron}\"")
    cip = live_cancel_in_progress()
    if cip is not None:
        require(f"cancel-in-progress: {cip}" in text,
                f"[覆盖] Wiki 全套未记录主构建并发口径 cancel-in-progress: {cip}")


# --------------------------------------------------------------------------
# B. 一致类：以现状口吻写的数字必须等于现测
# --------------------------------------------------------------------------

def check_numbers(where: str, text: str) -> None:
    total, tiers = live_rss_counts()
    functions = live_function_count()
    workflows = len(live_workflows())
    endpoints = len(live_endpoints())
    steps = live_update_step_count()
    # 中文数词与 ASCII 一律认：知识卡行文两种都写（"9 个函数"/"九个端点"）
    NUM = r"([0-9]{1,3}|[一二三四五六七八九十])"
    for line in text.splitlines():
        for match in re.finditer(r"(\d{2,5})\s*个[\s*]*(?:RSS\s*)?源", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            require(int(match.group(1)) == total,
                    f"[数字:{where}] 写「{match.group(0).strip()}」，现测 {total} 个源")
        for match in re.finditer(r"T([1234])\s*[=＝:：为]\s*(\d{1,4})\b", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            tier, claimed = f"T{match.group(1)}", int(match.group(2))
            if tier in tiers:
                require(claimed == tiers[tier],
                        f"[数字:{where}] 写 {tier}={claimed}，现测 {tier}={tiers[tier]}")
        for match in re.finditer(NUM + r"\s*个[\s*]*(?:Vercel\s*)?函数", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            claimed = _zh_int(match.group(1))
            if functions is not None and claimed is not None:
                require(claimed == functions,
                        f"[数字:{where}] 写「{match.group(0).strip()}」，"
                        f"现测 vercel.json 有 {functions} 个函数")
        for match in re.finditer(NUM + r"\s*个\s*workflow", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            claimed = _zh_int(match.group(1))
            if claimed is not None:
                require(claimed == workflows,
                        f"[数字:{where}] 写「{match.group(0).strip()}」，"
                        f"现测 git 跟踪 {workflows} 个 workflow")
        for match in re.finditer(NUM + r"\s*个\s*端点", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            claimed = _zh_int(match.group(1))
            if claimed is not None:
                require(claimed == endpoints,
                        f"[数字:{where}] 写「{match.group(0).strip()}」，"
                        f"现测 api/ 有 {endpoints} 个端点")
        for match in re.finditer(r"(\d{1,3})\s*步(?![\w])", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            if steps is not None:
                require(int(match.group(1)) == steps,
                        f"[数字:{where}] 写「{match.group(0).strip()}」，"
                        f"现测 update.yml 有 {steps} 步")
        # 抄来的 schedule 也一样：写了就必须是仓库里真有的那条
        crons = live_crons()
        for match in re.finditer(r"cron\s*[\"']([^\"']+)[\"']", line):
            if _near_tombstone(line, match.start(), match.end()):
                continue
            require(match.group(1) in crons,
                    f"[数字:{where}] 写 cron \"{match.group(1)}\"，"
                    f"现测被跟踪 workflows 只有 {crons}")


def check_scoped_counts(where: str, text: str) -> None:
    """known_*/descriptions/rss_sources 的条目数：量词必须落在最近一次文件名
    提及的 ±80 字内（按最近提及归属，避免"（293 条…）与 descriptions（518 条…）"
    这种并列结构被错误归到前一个文件名头上），墓碑词邻域内的放过。"""
    fnames = [f for f, _ in SCOPED_COUNTS]
    units = dict(SCOPED_COUNTS)
    lives = {f: live_json_count(f) for f in fnames}
    quant = re.compile(r"([0-9]{1,6})\s*(条|项)")
    for line in text.splitlines():
        if not any(f in line for f in fnames):
            continue
        mentions = [(m.start(), m.end(), f) for f in fnames
                    for m in re.finditer(re.escape(f), line)]
        for m in quant.finditer(line):
            center = (m.start() + m.end()) / 2
            best = min(mentions, key=lambda t: min(abs(t[0] - center), abs(t[1] - center)))
            dist = min(abs(best[0] - center), abs(best[1] - center))
            if dist > SCOPED_WINDOW:
                continue
            fname = best[2]
            if units[fname] != m.group(2):
                continue
            if _near_tombstone(line, m.start(), m.end()):
                continue
            live = lives[fname]
            if live is None:
                continue
            require(int(m.group(1)) == live,
                    f"[数字:{where}] 写 {fname} 「{m.group(0).strip()}」，现测 {live}")


# --------------------------------------------------------------------------
# C. 失效引用：提到的仓库路径必须存在（防把墓碑当现状，也防只写 basename 查错地方）
# --------------------------------------------------------------------------

def check_dead_paths(where: str, text: str, basenames: set[str]) -> None:
    seen: set[str] = set()
    for line in text.splitlines():
        if TOMBSTONE.search(line):
            continue
        for match in PATH_RE.finditer(line):
            relative = match.group(1)
            if relative in seen or "*" in relative:
                continue
            seen.add(relative)
            exists = (ROOT / relative).exists() or Path(relative).name in basenames
            require(exists, f"[引用:{where}] 提到仓库里不存在的路径: {relative}")


# 归档标记：文件头 5 行内出现即视为历史快照（2026-09-13 平台产物已统一打标）
ARCHIVE_MARKER = "repowiki-archive"
ARCHIVE_HEADER_LINES = 5


def is_archive(content: str) -> bool:
    return ARCHIVE_MARKER in "\n".join(content.splitlines()[:ARCHIVE_HEADER_LINES])


def check_markdown_and_links() -> None:
    for path in wiki_files():
        if path.suffix != ".md":
            continue
        content = read(path)
        require(content.count("```") % 2 == 0,
                f"[围栏] 代码围栏未闭合: {path.relative_to(ROOT)}")
        if is_archive(content):
            continue  # 历史快照的 file:// 引用停在当年，不作现状要求
        # 必须紧跟非空白且不含反引号：否则正文里那句"`file://` 链接存在性"会一路吃到下一个右括号
        for target in re.findall(r"file://([^\s)`]+)", content):
            target = unquote(target.split("#", 1)[0]).strip()
            if not target or target.startswith(("http:", "https:")):
                continue
            require((ROOT / target).exists(),
                    f"[引用] 失效 file:// 链接: {path.relative_to(ROOT)} -> {target}")


def check_no_secrets(text: str) -> None:
    for pattern in (r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                    r"xox[baprs]-[A-Za-z0-9-]{20,}", r"vcp_[A-Za-z0-9]{20,}"):
        require(re.search(pattern, text) is None, f"[令牌] Wiki 疑似包含敏感令牌: {pattern}")


def main() -> int:
    # Windows 控制台默认 cp936，中文判据会被吞成乱码；只在脚本态重挂载，避免与 pytest 捕获冲突
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not WIKI.is_dir():
        print(f"Wiki sync check FAILED: 找不到 {WIKI.relative_to(ROOT)}")
        return 1
    files = wiki_files()
    require(bool(files), "[覆盖] Wiki 目录里没有任何 md/yaml 文件")
    text = "\n".join(read(path) for path in files)
    require(bool(text.strip()), "[覆盖] Wiki 内容为空")
    check_coverage(text)
    basenames = repo_basenames()
    archived = 0
    for path in files:
        where = str(path.relative_to(ROOT))
        body = read(path)
        if is_archive(body):
            archived += 1  # 历史快照：B/C 两类不判，围栏与令牌仍全量
            continue
        check_numbers(where, body)
        check_scoped_counts(where, body)
        check_dead_paths(where, body, basenames)
    check_markdown_and_links()
    check_no_secrets(text)
    if ERRORS:
        by_kind: dict[str, int] = {}
        by_layer: dict[str, int] = {}
        for error in ERRORS:
            kind = (re.match(r"\[([^:\]]+)", error) or [None, "其它"])[1]
            by_kind[kind] = by_kind.get(kind, 0) + 1
            layer = "知识卡" if "repowiki\\knowledge" in error or "repowiki/knowledge" in error \
                else "旧 content 页" if "repowiki\\zh\\content" in error or "repowiki/zh/content" in error \
                else "其它"
            by_layer[layer] = by_layer.get(layer, 0) + 1
        kinds = "｜".join(f"{k} {v}" for k, v in sorted(by_kind.items()))
        layers = "｜".join(f"{k} {v}" for k, v in sorted(by_layer.items()))
        print(f"Wiki sync check FAILED ({len(ERRORS)} errors)")
        print(f"- 按判据：{kinds}")
        print(f"- 按层：{layers}（旧 content 页是 2026-09-13 平台产物；"
              f"已在文件头打 repowiki-archive 标记的按历史快照免检，"
              f"仍报红的旧页要补标记或在 Qoder 里重新生成）")
        for error in ERRORS:
            print(f"- {error}")
        return 1
    total, tiers = live_rss_counts()
    print("Wiki sync check PASS")
    print(f"- 覆盖：{len(live_endpoints())} 个端点 / {len(live_scripts())} 个构建脚本 / "
          f"{len(live_workflows())} 个 workflow / {len(live_crons())} 条 schedule 全部提到")
    print(f"- 一致：现测 {total} 个源 {tiers}、{live_function_count()} 个 Vercel 函数、"
          f"{len(live_workflows())} 个 workflow，"
          f"Wiki 里凡以现状口吻写到的数字都与之一致")
    print(f"- 引用：不存在的路径、失效 file:// 链接、未闭合围栏、令牌泄露均无"
          f"（{archived} 份带 repowiki-archive 标记的历史快照按墓碑免检）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
