# -*- coding: utf-8 -*-
"""批 6（daily-insight.json 退出每场提交）判据的变异电池。

被测 workflow 走 `STARHUB_UPDATE_YML` 指向的**副本**：就地改 update.yml 会与推送互斥
（本仓判据文件头就写了这条约束），而 D4 需要同时改测试本体，只能就地、逐轮还原 + sha256 对账。

四条各自回答一个问题：
  D1 把条件式 add 加回去 ⇒ 必须红（这是本轮真正摘掉的那一行）
  D2 把它塞进发布名单    ⇒ 必须红（没有前端读方，进名单只是扩大公开面）
  D3 少一条 `test -s`    ⇒ 必须红（同一个循环还得守住老几件，别改成只守新名字）
  D4 旧行首口径 + D1 的 workflow ⇒ **必须绿**（这才是"判据此前空跑"的证据：
     `if [ -f X ]; then git add X; fi` 整行以 if 开头，行首匹配读不到 ⇒ 旧判据对 D1 视而不见）
所以 D4 的期望是 green，不是 escape；把它当"未挡住"计就把它读反了。
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
MUT_WF = os.path.join(ROOT, ".deploy-tmp", "_mut_update.yml")
TESTF = os.path.join(ROOT, "tests", "rss_history", "test_pages_deploy_wiring.py")
TARGET = "test_site_artifacts_are_published_not_committed"

PUB_BLOCK = ('          for f in hot_snapshot.json; do\n'
             '            [ -f "$f" ] && cp -f "$f" _pages/\n'
             '          done')
CHECK = "          test -s _pages/rss-data-0.js\n"
# D1/D4 的锚点是**当前**文本（变异=把已删除的那行加回去），别把 old/new 写反
D1_ANCHOR = ("          fi\n"
             "          if ! python3 tools/size_tripwire.py; then")
D1_NEW = ("          fi\n"
          "          if [ -f daily-insight.json ]; then git add daily-insight.json; fi\n"
          "          if ! python3 tools/size_tripwire.py; then")

D5_ANCHOR = ("（不许回 add、也不许进发布名单）。\n"
             "          git add known_categories.json rss_sources.json build_rss_aggregator.py "
             "insight_engine.py build_daily_insight.py test_daily_insight.py")
D5_NEW = ("（不许回 add、也不许进发布名单）。\n"
          "          if [ -f rss_sources.json ]; then git add known_categories.json rss_sources.json; fi")

# (标签, 锚点, 变异体, 期望, 靶判据, -k 选择)
# D4 原来是"就地改测试文件的解析口径"来证明旧口径看不见条件式；那条与 pytest 的
# assertion-rewrite 缓存打架（同一轮里 D1 报绿、D4 报红，读数互换），已改成把口径本身
# 钉成判据：test_pages_deploy_wiring.py::test_add_names_parser_catches_the_conditional_form。
CASES = [
    ("D1 条件式 add 回到清单", D1_ANCHOR, D1_NEW, "red", "又回到提交清单",
     "test_site_artifacts_are_published_not_committed"),
    ("D2 无读方的它被塞进发布名单", PUB_BLOCK,
     PUB_BLOCK + "\n          for f in daily-insight.json; do\n"
     "            [ -f \"$f\" ] && cp -f \"$f\" _pages/\n          done",
     "red", "被放进发布名单", "test_site_artifacts_are_published_not_committed"),
    ("D3 少一条 test -s（空制品会被当成功发布）", CHECK, "", "red", "缺 test -s 硬断言",
     "test_site_artifacts_are_published_not_committed"),
    ("D5 fetch 名改成条件式 add（统一口径后不该误报）", D5_ANCHOR, D5_NEW, "green", "",
     "test_frontend_fetched_names_are_served"),
]

PARSER_A = '            if re.search(r"\\bgit add\\b", line):'
PARSER_B = '            if re.match(r"\\s*git add\\b", line):'


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run(env_wf, test_src=None, k=None):
    env = dict(os.environ)
    if env_wf:
        env["STARHUB_UPDATE_YML"] = env_wf
    if test_src is not None:
        open(TESTF, "w", encoding="utf-8", newline="").write(test_src)
    cmd = [sys.executable, "-m", "pytest", os.path.relpath(TESTF, ROOT), "-q", "--no-header",
           "-p", "no:cacheprovider"]
    if k:
        cmd += ["-k", k]
    p = subprocess.run(cmd,
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=300)
    lines = (p.stdout or "").strip().splitlines()
    return p.returncode != 0, (lines[-1] if lines else "?"), "\n".join(lines)


orig_test = open(TESTF, "rb").read()
h0_test = sha(TESTF)
test_src = orig_test.decode("utf-8")
wf_src = open(WF, encoding="utf-8").read()

# 进场自检：磁盘态必须与本电池预期一致。上一轮若中断会留下变异体，
# 那时 orig_test 就是错的"基线"，还原会还原到坏版本（本轮 D1/D4 读数互换即为此形）。
if test_src.count(PARSER_A) != 1 or PARSER_B in test_src:
    print("[NG] 测试文件磁盘态与电池预期不符（search 出现 %d 次 / match 残留 %s）"
          % (test_src.count(PARSER_A), PARSER_B in test_src))
    sys.exit(1)

# 基线：真 workflow 上必须绿
red, tail, _ = run(None)
print("基线（未变异）：%s" % tail)
if red:
    print("基线不绿 ⇒ 不声称覆盖率")
    sys.exit(1)

bad = []
for label, a, b, want, needle, k in CASES:
    n = wf_src.count(a)
    if n != 1:
        bad.append("%s INVALID（workflow 锚点命中 %d 次）" % (label, n))
        continue
    mutated = wf_src.replace(a, b, 1)
    open(MUT_WF, "w", encoding="utf-8", newline="").write(mutated)
    try:
        on_disk = open(MUT_WF, encoding="utf-8").read()
        print("   [诊断] 副本含条件式 add=%s  k=%s"
              % ("]; then git add" in on_disk, k))
        red, tail, out = run(MUT_WF, None, k)
    finally:
        open(TESTF, "wb").write(orig_test)
    got = "red" if red else "green"
    ok = got == want and (not needle or needle in out)
    print("%-44s 期望 %-5s 实得 %-5s %s %s" % (label, want, got, "OK" if ok else "NG", tail[:34]))
    if not ok:
        if got != want:
            bad.append("%s（期望 %s 实得 %s）" % (label, want, got))
            for l in out.splitlines():
                if l.startswith("E "):
                    print("        %s" % l[:150])
        else:
            bad.append("%s 红了但不是自己的靶（输出里找不到 %r）⇒ 记为未挡住" % (label, needle))
    if sha(TESTF) != h0_test:
        bad.append("%s 之后测试文件没还原" % label)

if os.path.isfile(MUT_WF):
    os.remove(MUT_WF)
print("测试文件还原：%s" % ("sha256 一致" if sha(TESTF) == h0_test else "失败"))
print("问题条目：%s" % (bad if bad else "无"))
sys.exit(1 if bad or sha(TESTF) != h0_test else 0)
