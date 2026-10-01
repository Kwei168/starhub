# -*- coding: utf-8 -*-
"""播种步（冷启动回灌）的变异电池：把它的每条自我约束逐条捅掉，看判据抓不抓得住。

用法：py -3.11 tools/mut_state_seed.py
约定同其它电池：只改临时副本（STARHUB_UPDATE_YML 注入），基线不绿就拒绝自评；
每个变异都声明它应落地的锚点与命中次数，命中数不符直接抛错 —— 绝不允许"半落地"的变异
被报成"已挡住"（第一版 R1/R5 就是这么假绿的）。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
TEST = os.path.join("tests", "rss_history", "test_state_seed.py")
TMP = os.path.join(ROOT, ".deploy-tmp")
STEP_MARK = "      - name: Seed cross-build state from history (cold-start repair)\n"
RESTORE_MARK = "      - name: Restore cross-build state cache"
SHA = "8a48fa78787e45557ede69f69b22c89f49c26609"
EARLY_EXIT = [
    '          if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$SEED_SHA" ]; then\n',
    '            echo "  seed 已对 $SEED_SHA 做过，跳过"\n',
    "            exit 0\n",
    "          fi\n",
]
WRITE_MARKER = '          echo "$SEED_SHA" > "$MARKER"\n'


def block_of(text):
    i = text.index(STEP_MARK)
    j = text.index("      - name: Diagnose cross-build state cache restore", i)
    return text[i:j]


def must(text, needle, expect):
    n = text.count(needle)
    assert n == expect, "锚点命中 %d 次（应为 %d）：%r" % (n, expect, needle[:60])
    return needle


def main():
    src = open(WF, encoding="utf-8").read()
    blk = block_of(src)
    must(src, STEP_MARK, 1)
    must(src, "            if [ -f \"$f\" ]; then L=$(wc -c < \"$f\"); fi", 1)
    early = "".join(EARLY_EXIT)
    assert early in blk, "早退分支的形状变了，先更新电池而不是让判据空转"

    def repl(old, new, count=1):
        assert blk.count(old) == count, "块内锚点 %r 命中 %d" % (old[:40], blk.count(old))
        return src.replace(blk, blk.replace(old, new), 1)

    MUTS = [
        ("N1 删掉整个回灌步（塌了也没人补）", src.replace(blk, "", 1)),
        ("N2 去掉 continue-on-error（取不到就冻两次部署）",
         src.replace(blk, blk.replace("        continue-on-error: true\n", "", 1), 1)),
        ("N3 去掉体积比较、改成无条件覆盖（每场拿旧副本盖新数据）",
         repl('            if [ -n "$H" ] && [ "$L" -lt "$H" ]; then',
              "            if [ -n \"$H\" ]; then")),
        ("N4 RAW 地址改成 main（批 3 之后 main 上已无这些路径 = 永远 404）",
         repl("/" + SHA, "/main")),
        ("N5 挪到 Restore 之前（会被缓存盖掉）",
         src.replace(blk, "", 1).replace(RESTORE_MARK, blk + RESTORE_MARK, 1)),
        ("N6 for 名单少一个文件（名单与状态族清单漂移）",
         repl(" insight_tracking_history.jsonl", "")),
        ("N7 顺手加一句 git add（把冻结副本请回库里）",
         repl("          mkdir -p build_logs",
              "          mkdir -p build_logs\n          git add hot_history.json")),
        ("N8 删掉早退分支（每次都重跑 7 次 HEAD + 可能重复覆盖）",
         src.replace(blk, blk.replace(early, "", 1), 1)),
        ("N9 回灌后不写 marker（下一场还会再盖一次）",
         src.replace(blk, blk.replace(WRITE_MARKER, "", 1), 1)),
        ("N10 marker 挪出 build_logs（跨不了场 = 等于没有 marker）",
         repl("MARKER=build_logs/.state_seed.done", "MARKER=zz_seed_done.txt")),
    ]

    def run(mut, label):
        if mut == src:
            return "%-56s INVALID（变异没落到字节上）" % label, False
        os.makedirs(TMP, exist_ok=True)
        wp = os.path.join(TMP, "_mut_seed_update.yml")
        open(wp, "w", encoding="utf-8", newline="\n").write(mut)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", STARHUB_UPDATE_YML=wp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        lines = (p.stdout or "").strip().splitlines()
        failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
        return "%-56s %s %s" % (label, "RED  " if p.returncode else "GREEN(判据漏了!)",
                                ", ".join(x.split(".")[-1] for x in failed)[:70]
                                or (lines[-1] if lines else "?")[:60]), p.returncode != 0

    base = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    print("基线（未变异）：%s rc=%d" % ((base.stdout.strip().splitlines() or ["?"])[-1], base.returncode))
    if base.returncode != 0:
        print(base.stdout[-1200:])
        print("基线不绿 ⇒ 不声称覆盖率")
        return 1
    escapes = 0
    for label, mut in MUTS:
        out, caught = run(mut, label)
        print(out)
        if not caught:
            escapes += 1
    print("\n未被挡住的变异/无效变异：%d" % escapes)
    return 1 if escapes else 0


if __name__ == "__main__":
    sys.exit(main())
