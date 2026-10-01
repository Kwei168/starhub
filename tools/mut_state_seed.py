# -*- coding: utf-8 -*-
"""播种步（冷启动回灌）的变异电池：把它的四条自我约束逐条捅掉，看判据是否抓得住。

用法：py -3.11 tools/mut_state_seed.py
约定同其它电池：只改临时副本（STARHUB_UPDATE_YML 注入），基线不绿就拒绝自评，
锚点命中数不符直接抛错（绝不让变异"半落地"却报成挡住）。
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
PIN = "https://raw.githubusercontent.com/Kwei168/starhub/8a48fa78787e45557ede69f69b22c89f49c26609/$f"


def block_of(text):
    i = text.index(STEP_MARK)
    j = text.index("      - name: Diagnose cross-build state cache restore", i)
    return text[i:j]


def main():
    src = open(WF, encoding="utf-8").read()
    assert src.count(STEP_MARK) == 1 and src.count(PIN) == 1, "锚点自检失败"
    blk = block_of(src)

    MUTS = [
        ("N1 删掉整个回灌步（缺失就没人补）", src.replace(blk, "", 1)),
        ("N2 去掉 continue-on-error（取不到就冻两次部署）",
         src.replace(STEP_MARK + "        # ", STEP_MARK + "        # ", 1)
            .replace(blk, blk.replace("        continue-on-error: true\n", "", 1), 1)),
        ("N3 去掉「缺失才取」的守卫（每场无条件重拉 17 MB）",
         src.replace(blk, blk.replace('            if [ ! -f "$f" ]; then\n', "", 1)
                     .replace("            fi\n", "", 1), 1)),
        ("N4 回灌地址改成 main（批 3 之后 main 上已无这些路径 = 永远 404）",
         src.replace(blk, blk.replace("/8a48fa78787e45557ede69f69b22c89f49c26609/", "/main/"), 1)),
        ("N5 把回灌挪到 Restore 之前（会被缓存盖掉）",
         src.replace(blk, "", 1).replace(RESTORE_MARK, blk + RESTORE_MARK, 1)),
        ("N6 for 名单少一个文件（名单与状态族清单漂移）",
         src.replace(blk, blk.replace(" insight_tracking_history.jsonl", ""), 1)),
        ("N7 回灌里顺手加一句 git add（把冻结副本请回库里）",
         src.replace(blk, blk.replace("          for f in hot_history.json translations.json",
                                      "          git add hot_history.json\n"
                                      "          for f in hot_history.json translations.json"), 1)),
    ]

    def run(mut, label):
        if mut == src:
            return "%-52s INVALID（变异没落到字节上）" % label, False
        os.makedirs(TMP, exist_ok=True)
        wp = os.path.join(TMP, "_mut_seed_update.yml")
        open(wp, "w", encoding="utf-8", newline="\n").write(mut)
        env = dict(os.environ, STARHUB_UPDATE_YML=wp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        lines = (p.stdout or "").strip().splitlines()
        failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
        return "%-52s %s %s" % (label, "RED  " if p.returncode else "GREEN(判据漏了!)",
                                ", ".join(x.split(".")[-1] for x in failed)[:76]
                                or (lines[-1] if lines else "?")[:70]), p.returncode != 0

    base = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    print("基线（未变异）：%s rc=%d" % ((base.stdout.strip().splitlines() or ["?"])[-1], base.returncode))
    if base.returncode != 0:
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
