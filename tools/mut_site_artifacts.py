# -*- coding: utf-8 -*-
"""批 5b 变异电池：站点产物"退出 git、按名发布、各有 test -s"这三条接缝能不能被捅穿。

用法：python tools/mut_site_artifacts.py
判据文件读 STARHUB_UPDATE_YML，所以变异体写在临时副本上，绝不就地改 update.yml
（就地改会与推送互斥，见 feedback-mutation-push-mutex）。

约定与 mut_state_cache.py 一致：
  · 基线（未变异）不绿 ⇒ 直接退出，绝不声称覆盖率（一条恒红的判据会让任何变异"看起来被挡住"）；
  · 变异没落到字节上 = INVALID，计入未覆盖，不当"已挡住"。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
TEST = os.path.join("tests", "rss_history", "test_pages_deploy_wiring.py")
TMP = os.path.join(ROOT, ".deploy-tmp")

ADD_MAIN = ("git add known_categories.json rss_sources.json build_rss_aggregator.py "
            "insight_engine.py build_daily_insight.py test_daily_insight.py")
PUBLISH = "          for f in hot_snapshot.json; do\n"
TEST_S = "          test -s _pages/hot_snapshot.json\n"


def sub_nth(text, old, new, nth):
    """只替换第 nth 处（1 起）：主路径与重试分支的清单逐字相同，必须能分别下手。"""
    i, seen = -1, 0
    while True:
        i = text.find(old, i + 1)
        if i < 0:
            raise AssertionError("锚点不足 %d 处" % nth)
        seen += 1
        if seen == nth:
            return text[:i] + new + text[i + len(old):]


def main():
    src = open(WF, encoding="utf-8").read()
    assert src.count(ADD_MAIN) == 2, "两条 add 清单未逐字同一（实测 %d 处）" % src.count(ADD_MAIN)
    withchunk0 = ADD_MAIN.replace("git add ", "git add rss-data-0.js ", 1)
    withhot = ADD_MAIN.replace("git add ", "git add hot_snapshot.json ", 1)
    MUTS = [
        ("B1 把 rss-data-0.js 加回主路径清单（0.6 MiB/场 复活）",
         sub_nth(src, ADD_MAIN, withchunk0, 1), None),
        ("B2 只摘主路径、重试分支仍提交 hot_snapshot",
         sub_nth(src, ADD_MAIN, withhot, 2), None),
        ("B3 发布名单漏掉 hot_snapshot.json（首页侧栏空数据）",
         src.replace(PUBLISH, "", 1), None),
        ("B4 hot_snapshot 的 test -s 被删（空文件会被当成功发布）",
         src.replace(TEST_S, "", 1), None),
        ("B5 把纯跨场态 descriptions_zh.json 塞进发布名单（扩大公开面）",
         src.replace(PUBLISH, "          for f in hot_snapshot.json descriptions_zh.json; do\n", 1), None),
    ]

    def run(mut, label):
        if mut == src:
            return "%-56s INVALID（变异没落到字节上）" % label, False
        os.makedirs(TMP, exist_ok=True)
        wfp = os.path.join(TMP, "_mut_site_update.yml")
        with open(wfp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(mut)
        env = dict(os.environ, STARHUB_UPDATE_YML=wfp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        lines = (p.stdout or "").strip().splitlines()
        failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
        tail = lines[-1] if lines else "?"
        return "%-56s %s %s%s" % (label, "RED  " if p.returncode else "GREEN(判据漏了!)", tail,
                                  ("  <- " + ", ".join(failed[:2])) if failed else ""), p.returncode != 0

    base = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    print("基线（未变异）：%s  rc=%d" % ((base.stdout.strip().splitlines() or ["?"])[-1], base.returncode))
    if base.returncode != 0:
        print(base.stdout[-1800:])
        print("基线不绿 ⇒ 本次不声称任何覆盖率")
        return 1
    escapes = 0
    for label, mut in [(m[0], m[1]) for m in MUTS]:
        out, caught = run(mut, label)
        print(out)
        if not caught:
            escapes += 1
    print("\n未被挡住的变异/无效变异：%d" % escapes)
    return 1 if escapes else 0


if __name__ == "__main__":
    sys.exit(main())
