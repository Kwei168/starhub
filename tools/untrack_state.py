# -*- coding: utf-8 -*-
"""批 3 的本地索引对齐：把已退出远端 git 树的 7 个跨场状态从**本地索引**里摘掉。

为什么需要：本仓的远端写入走 `tools/data_api_push.py`（Git Data API），本地 `.git` 从不随之前进，
所以远端已删除的路径在本地仍是"被跟踪"。这让 `test_state_files_are_not_tracked` 在本地恒红，
而一条恒红的判据会**污染整个变异电池**（任何变异都"看起来被挡住了"）——
`mut_state_cache.py` 的基线守卫正是为此而存在：基线不绿就不许声称覆盖率。

只动索引、不动磁盘（`--cached`），且第一步就落一个可逆命令文件，撤销=执行它：

    python tools/untrack_state.py --restore

用法：
    python tools/untrack_state.py            # 列出将要摘的路径并执行，写回滚命令
    python tools/untrack_state.py --dry-run  # 只看不动
    python tools/untrack_state.py --restore  # 用 git restore --staged 把索引还原
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILES = (
    "hot_history.json",
    "analysis_snapshot.json",
    "translations.json",
    "rss_trend_history.json",
    "insight_tracking_history.jsonl",
    "daily_insight_tracking_history.jsonl",
    "daily_insight_history.json",
)
ROLLBACK = os.path.join(ROOT, ".deploy-tmp", "restore_state_index.sh")


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)


def tracked():
    r = git("ls-files", "--", *STATE_FILES)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def do_restore():
    if not os.path.isfile(ROLLBACK):
        print("没有回滚文件 %s（本地索引此刻是干净的或从未对齐过）" % ROLLBACK)
        return 1
    names = [l for l in open(ROLLBACK, encoding="utf-8").read().splitlines()
             if l.startswith("git restore")][0].split()[3:]
    r = git("restore", "--staged", "--", *names)
    print((r.stdout.strip() + " " + r.stderr.strip()).strip())
    print("还原后本地仍跟踪：%d 个" % len(tracked()))
    return 0 if r.returncode == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    if a.restore:
        return do_restore()

    before = tracked()
    print("本地索引里被跟踪的状态文件：%d / %d" % (len(before), len(STATE_FILES)))
    if not before:
        print("已经是干净的（远端已删除，本地索引也已对齐）")
        return 0
    if a.dry_run:
        print("dry-run：将执行 git rm --cached -- %s" % " ".join(before))
        return 0

    os.makedirs(os.path.dirname(ROLLBACK), exist_ok=True)
    with open(ROLLBACK, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/bin/sh\n# 撤销 tools/untrack_state.py 的索引对齐（把 %d 个路径放回索引）\n"
                  "git restore --staged %s\n" % (len(before), " ".join(before)))
    print("回滚命令已写入：%s" % ROLLBACK)

    for p in before:
        r = git("rm", "--cached", "--quiet", "--", p)
        if r.returncode != 0:
            print("  [NG] %s：%s" % (p, (r.stderr or r.stdout).strip()[:160]))
            return 1
        print("  [OK] 从索引摘除 %s（文件仍在磁盘上）" % p)
    print("对齐后本地仍跟踪：%d 个" % len(tracked()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
