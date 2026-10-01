"""批 1 判据的变异测试：每个变异都必须让至少一条 starhub-state 接线判据变红。

用法：py -3.11 tools/mut_state_cache.py
约定：只改副本，靠 STARHUB_UPDATE_YML 注进判据（本仓既有约定，与 RSS_BUILD_SRC 同族），
     绝不就地改 .github/workflows/update.yml。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
TMP = os.path.join(ROOT, ".deploy-tmp")
TEST = os.path.join("tests", "rss_history", "test_state_cache_wiring.py")

RESTORE_MARK = "      - name: Restore cross-build state cache"
DIAGNOSE_MARK = "      - name: Diagnose cross-build state cache restore"
SAVE_MARK = "      - name: Save cross-build state cache (before prune deletes build_logs)"
CLEANUP_MARK = "      - name: Cleanup old build logs"
STAGE_MARK = "      - name: Stage Pages site for Actions deployment"
WORKTREE_MARK = "      - name: Restore worktree after insight tests"


def block(text, start_mark, end_mark):
    """按步骤名切出整块（含结尾换行），end_mark 是下一块的起始名。"""
    i = text.index(start_mark)
    j = text.index(end_mark, i)
    return text[i:j]


def main():
    src = open(WF, encoding="utf-8").read()
    restore_blk = block(src, RESTORE_MARK, DIAGNOSE_MARK)
    diagnose_blk = block(src, DIAGNOSE_MARK, "      - name: Fetch stars & build")
    save_blk = block(src, SAVE_MARK, STAGE_MARK)

    MUTS = [
        ("S1 删掉 Restore 步", src.replace(restore_blk, "", 1)),
        ("S2 删掉 Save 步", src.replace(save_blk, "", 1)),
        ("S3 Save 的 key 去掉 run_attempt（同 run 重跑就静默不保存）",
         save_blk_keyless(src)),
        ("S4 restore-keys 写成别的族名（前缀回退失效）",
         src.replace("starhub-state-${{ runner.os }}-\n", "starhub-stateX-${{ runner.os }}-\n", 1)),
        ("S5 path 名单少一个文件", src.replace("            rss_trend_history.json\n", "", 2)),
        ("S6 Restore 挪到 git clean 之前（还原当场被删掉）",
         src.replace(restore_blk, "", 1).replace(WORKTREE_MARK, restore_blk + WORKTREE_MARK, 1)),
        ("S7 Save 挪到 Cleanup 之前（过期日志被存进缓存）",
         src.replace(save_blk, "", 1).replace(CLEANUP_MARK, save_blk + CLEANUP_MARK, 1)),
        ("S8 trim 不给这个族配 --keep（新无界增长点）",
         src.replace(" --keep starhub-state=3", "", 1)),
        ("S9 --keep starhub-state=1（只剩一条预算）",
         src.replace("--keep starhub-state=3", "--keep starhub-state=1", 1)),
        ("S10 族名改成下划线（trim 按前缀认不出这个族）",
         src.replace("--keep starhub-state=3", "--keep starhub_state=3", 1)),
        ("S11 诊断不打字节数（只剩不可信的 cache-hit）",
         src.replace('echo "  OK $f ($(wc -c < "$f") B)"', 'echo "  OK $f"', 1)),
        ("S12 冷启动不出声（静默退化）",
         src.replace('echo "::warning title=跨场状态冷启动::$f 不在盘上，本场按冷启动跑（代价：重译/重跑重分析）"',
                     'echo "  note: $f absent"', 1)),
        ("S13 批 1 就提前把 hot_history 从提交清单删掉（断档风险）",
         src.replace("git add hot_history.json;", "git add _nothing.json;")),
    ]

    def run(mutated, label):
        if mutated is None or mutated == src:
            return "%-52s SKIP（变异无效/锚点没找到）" % label, True
        out = os.path.join(TMP, "_mut_update.yml")
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(mutated)
        env = dict(os.environ, STARHUB_UPDATE_YML=out, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        os.remove(out)
        lines = (p.stdout or "").strip().splitlines()
        tail = lines[-1] if lines else "?"
        failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
        red = p.returncode != 0
        return "%-52s %s %s%s" % (label, "RED  " if red else "GREEN(判据漏了!)", tail,
                                  ("  <- " + ", ".join(failed[:3])) if failed else ""), red

    base = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    print("基线（未变异）：%s  rc=%d" % ((base.stdout.strip().splitlines() or ["?"])[-1],
                                        base.returncode))
    if base.returncode != 0:
        print(base.stdout[-2500:])
        return 1

    escapes = 0
    for label, mutated in MUTS:
        line, red = run(mutated, label)
        print(line)
        if not red:
            escapes += 1
    print("\n未被任何判据挡住的变异/无效变异：%d" % escapes)
    return 1 if escapes else 0


def save_blk_keyless(src):
    """把 Save 的 key 改成不含 run_attempt（与 Restore 不再逐字相同）。"""
    return src.replace(
        "          key: starhub-state-${{ runner.os }}-${{ github.run_id }}-${{ github.run_attempt }}\n\n"
        "      - name: Stage Pages site",
        "          key: starhub-state-${{ runner.os }}-${{ github.run_id }}\n\n"
        "      - name: Stage Pages site", 1)


if __name__ == "__main__":
    sys.exit(main())
