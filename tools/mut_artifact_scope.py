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

DIRS = "            | grep -zvE '(^|/)(tests|tools|build_logs|docs)/' \\\n"
PYS = "            | grep -zv '\\.py$' \\\n"
HTML = "            | grep -zv '^template\\.html$' \\\n"

MUTS = [
    ("S1 少掉非站点目录过滤（tests/tools/build_logs 又公开）", DIRS, "",
     "test_non_site_files_are_not_published"),
    ("S2 少掉 .py 过滤（源码又公开）", PYS, "",
     "test_non_site_files_are_not_published"),
    ("S3 过滤过头：把根目录 json 也剔掉（= 砍站点数据源）", HTML,
     HTML + "            | grep -zv '\\.json$' \\\n",
     "test_site_files_are_still_published"),
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
print("问题条目：%s" % (bad if bad else "无"))
sys.exit(1 if bad else 0)
