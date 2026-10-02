# -*- coding: utf-8 -*-
"""Pages 制品面收窄的变异电池：少一道过滤要红，过度收窄也要红。

被测正文来自 `STARHUB_UPDATE_YML` 指向的**副本**（判据自己支持这个口子，就地改 update.yml
会与推送互斥）。每个变异只动一行管道，然后跑 tests/site_nav_drift/test_pages_artifact_scope.py。
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
COPY = os.path.join(ROOT, ".deploy-tmp", "_mut_scope.yml")
TEST = os.path.join("tests", "site_nav_drift", "test_pages_artifact_scope.py")

DIRS = "            | grep -zvE '(^|/)(tests|tools|build_logs|docs|api|lib)/' \\\n"
API = "(tests|tools|build_logs|docs|api|lib)/"
PYS = "            | grep -zv '\\.py$' \\\n"
MDS = "            | grep -zv '\\.md$' \\\n"
HTML = "            | grep -zv '^template\\.html$' \\\n"

MUTS = [
    ("S1 少掉非站点目录过滤（tests/tools/build_logs 又公开）", DIRS, "",
     "test_non_site_files_are_not_published"),
    ("S2 少掉 .py 过滤（源码又公开）", PYS, "",
     "test_non_site_files_are_not_published"),
    ("S2b 少掉 .md 过滤（手册/README 又公开）", MDS, "",
     "test_non_site_files_are_not_published"),
    ("S3 过滤过头：把根目录 json 也剔掉（= 砍站点数据源）", HTML,
     HTML + "            | grep -zv '\\.json$' \\\n",
     "test_site_files_are_still_published"),
    # 批 11 的专属防线：只漏掉 api/ 时，其余过滤全在、站点也完好，只有 api 重新公开。
    # 没有这一条，S1（整行删掉）挡不住"把 api 从名单里摘掉"这种最小回退。
    ("S4 只把 api/ 放回公开面", API, API.replace("|api", ""),
     "test_non_site_files_are_not_published"),
    # 16:00 现取：旧场清单里 lib/ 有 4 项 —— 判据名单比现实窄时的典型形状。
    # 锚点若跟不上正文（少 `|lib`），本电池会直接报 INVALID 而不是假装覆盖到了。
    ("S6 只把 lib/ 放回公开面", API, API.replace("|lib", ""),
     "test_non_site_files_are_not_published"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run(k=None):
    cmd = [sys.executable, "-m", "pytest", TEST, "-q", "--no-header", "-p", "no:cacheprovider"]
    if k:
        cmd += ["-k", k]
    env = dict(os.environ, STARHUB_UPDATE_YML=COPY, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=900)
    lines = (p.stdout or "").strip().splitlines()
    failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
    return p.returncode != 0, (lines[-1] if lines else "?"), failed


src = open(WF, encoding="utf-8").read()
open(COPY, "w", encoding="utf-8", newline="").write(src)
red, tail, failed = run()
print("基线（未变异副本）：%s" % tail)
if red:
    print("基线不绿 ⇒ 不声称覆盖率；失败：%s" % failed)
    sys.exit(1)

bad = []
for label, a, b, target in MUTS:
    n = src.count(a)
    if n != 1:
        bad.append("%s INVALID（锚点 %d 次）" % (label, n))
        continue
    open(COPY, "w", encoding="utf-8", newline="").write(src.replace(a, b, 1))
    red, tail, failed = run()
    print("%-46s %s %s%s" % (label, "RED  " if red else "GREEN(判据漏了!)", tail[:22],
                            ("  <- " + ", ".join(failed)) if failed else ""))
    if not red:
        bad.append(label + "（没挡住）")
    elif target not in failed:
        bad.append("%s 红了但不是自己的靶（%s）" % (label, failed))
os.remove(COPY)

# 批 11 的另一半：`api/` 关出制品之后，页面里出现**同源** `/api/x` 调用就是 Pages 域 404。
# 这条前提判据（test_client_sources_make_no_same_origin_api_calls）也得能被变异打到，
# 否则它和红测输入之间又只剩下"我本地跑过一次"这种证据。
CLIENT = os.path.join(ROOT, ".deploy-tmp", "_mut_template.html")
SRC_TMPL = open(os.path.join(ROOT, "template.html"), encoding="utf-8", errors="replace").read()
OTHER = os.path.join(ROOT, "build_rss_aggregator.py")
K = "test_client_sources_make_no_same_origin_api_calls"

CASES2 = [
    ("C1 页面新增同源 /api/rss 调用（必须红）", SRC_TMPL + "\nfetch('/api/rss')\n", True),
    ("C2 外部域名的 /api/ 引用不该管（必须绿）",
     SRC_TMPL + "\nfetch('https://other.example/api/rss')\n", False),
]
for label, content, want_red in CASES2:
    open(CLIENT, "w", encoding="utf-8", newline="").write(content)
    env_backup = os.environ.get("STARHUB_CLIENT_SOURCES")
    os.environ["STARHUB_CLIENT_SOURCES"] = CLIENT + os.pathsep + OTHER
    try:
        red, tail, failed = run(k=K)
    finally:
        if env_backup is None:
            os.environ.pop("STARHUB_CLIENT_SOURCES", None)
        else:
            os.environ["STARHUB_CLIENT_SOURCES"] = env_backup
    ok = (red == want_red)
    print("%-46s %s %s%s" % (label, "RED  " if red else "GREEN", tail[:22],
                            "" if ok else "  <- 期望%s，判据识别有问题" % ("红" if want_red else "绿")))
    if not ok:
        bad.append(label + ("（没挡住）" if want_red else "（误伤：外部域名也被判红）"))
os.remove(CLIENT)
print("问题条目：%s" % (bad if bad else "无"))
sys.exit(1 if bad else 0)
