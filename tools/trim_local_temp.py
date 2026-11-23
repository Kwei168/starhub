# -*- coding: utf-8 -*-
"""本地临时目录轮换：防 _scratch / .deploy-tmp 无界膨胀（保守档）。

为什么需要：这两个目录已 gitignore（_scratch 未跟踪），CI 每场 `rm -rf .deploy-tmp`，
但**本地**会 accumulate 历次诊断/审查的子目录与探针快照。2026-11-23 实测两目录合计 2.9G，
其中 2.3G 是 0 运行时引用的历史残留（已一次性清入回收站）。本脚本是悬崖前的预防性轮换。

保守档边界（用户 2026-11-23 裁定）：
  * 只动**子目录**与**可再生缓存**，顶层散文件一律不碰（里面混着在用 .cjs 部署脚本与证据链）。
  * 可再生缓存（__pycache__ / mut / _mut* 工作区 / 空目录）：两目录都清，测试每次重建。
  * _scratch 子目录：按"目录内最新文件 mtime"保留最近 K 个（默认 5），其余超过 --days（默认 30）天者清。
  * .deploy-tmp 子目录：只清可再生缓存，不做年龄淘汰（含 local-fixtures/serve-* 等在用夹具）。

安全（照 tools/trim_actions_cache.py 的守卫思路）：
  * 默认 --dry-run，不动手；--apply 才执行。
  * 硬白名单：推送锁 .mutation-lock、测试夹具、回退基线、在用脚本——命中即永不列。
  * --keep <=0 拒绝（打错一个数字就会清空整族）。
  * 执行走回收站（SHFileOperationW + FOF_ALLOWUNDO），可恢复；非固定盘拒绝（无回收站会直删）。
  * 删后复核原位残留，汇总回收量；"有计划却一条没删成"留告警（防空转）。

用法：
  py -3.11 tools/trim_local_temp.py                 # dry-run 预览
  py -3.11 tools/trim_local_temp.py --apply         # 执行（入回收站）
  py -3.11 tools/trim_local_temp.py --keep 5 --days 30 --apply
  py -3.11 tools/trim_local_temp.py --self-test     # 用临时文件验证回收站机制
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import io
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = 1048576

# 硬白名单（相对 ROOT）：命中即永不列为目标。
RETAIN_REL = {
    os.path.join("_scratch", ".mutation-lock"),
    os.path.join(".deploy-tmp", "live-api-rss.json"),
    os.path.join(".deploy-tmp", "_full_sort_harness.js"),
    os.path.join(".deploy-tmp", "_rollback_baseline.json"),
    os.path.join(".deploy-tmp", "_update_yml.bak"),
    os.path.join(".deploy-tmp", "star_live_names.json"),
    os.path.join(".deploy-tmp", "restore_state_index.sh"),
}


def is_retained(rel):
    if rel in RETAIN_REL:
        return True
    # 在用部署/验证脚本（.cjs）整类保护
    if rel.startswith(".deploy-tmp" + os.sep) and rel.endswith(".cjs"):
        return True
    return False


def dir_size(p):
    t = 0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return t


def newest_mtime(p):
    """目录内最新文件 mtime；空目录返回 0。"""
    newest = 0.0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                m = os.path.getmtime(os.path.join(r, f))
                if m > newest:
                    newest = m
            except OSError:
                pass
    return newest


def is_regenerable(name):
    return name == "__pycache__" or name == "mut" or name.startswith("_mut")


def plan(base, keep, days, now):
    """返回 (targets, kept_recent)。targets 为绝对路径列表。"""
    bp = os.path.join(ROOT, base)
    if not os.path.isdir(bp):
        return [], []
    targets = []
    subdirs = []
    for name in os.listdir(bp):
        p = os.path.join(bp, name)
        if not os.path.isdir(p) or os.path.islink(p):
            continue
        rel = os.path.join(base, name)
        if is_retained(rel):
            continue
        sz = dir_size(p)
        if is_regenerable(name) or sz == 0:
            targets.append(p)              # 可再生缓存 / 空目录：直接清
        elif base == "_scratch":
            subdirs.append((newest_mtime(p), p))
    # _scratch 非再生子目录：保留最近 K 个，其余超龄者清
    kept_recent = []
    if base == "_scratch":
        subdirs.sort(key=lambda x: x[0], reverse=True)
        cutoff = now - days * 86400
        for idx, (mt, p) in enumerate(subdirs):
            if idx < keep:
                kept_recent.append(p)
            elif mt < cutoff:
                targets.append(p)
    return targets, kept_recent


# ---- 回收站（SHFileOperationW + FOF_ALLOWUNDO，可恢复）----
FO_DELETE = 3
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("wFunc", wt.UINT),
        ("pFrom", wt.LPCWSTR),
        ("pTo", wt.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wt.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wt.LPCWSTR),
    ]


def recycle(paths):
    """批量入回收站。返回 (ok, fail)。非固定盘拒绝（无回收站会永久删）。"""
    if not paths:
        return 0, 0
    drive = os.path.splitdrive(os.path.abspath(paths[0]))[0] + "\\"
    if ctypes.windll.kernel32.GetDriveTypeW(drive) != 3:  # DRIVE_FIXED
        print("  [NG] 非固定盘 %s，无回收站会永久删，拒绝执行" % drive, file=sys.stderr)
        return 0, len(paths)
    buf = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = buf
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0 or op.fAnyOperationsAborted:
        print("  [NG] SHFileOperationW rc=%s aborted=%s" % (rc, op.fAnyOperationsAborted),
              file=sys.stderr)
        return 0, len(paths)
    ok = sum(1 for p in paths if not os.path.exists(p))
    return ok, len(paths) - ok


def self_test():
    """造一个临时文件再回收，验证机制可用（验完即可，文件入回收站）。"""
    fd, p = tempfile.mkstemp(prefix="trim_local_selftest_", suffix=".txt")
    os.write(fd, b"self-test")
    os.close(fd)
    ok, fail = recycle([p])
    gone = not os.path.exists(p)
    print("self-test: 造=%s 回收ok=%d fail=%d 原位消失=%s" % (p, ok, fail, gone))
    return 0 if (ok == 1 and gone) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=5, help="_scratch 保留最近 K 个子目录（默认 5）")
    ap.add_argument("--days", type=int, default=30, help="_scratch 子目录超龄天数（默认 30）")
    ap.add_argument("--apply", action="store_true", help="执行（默认 dry-run）")
    ap.add_argument("--self-test", action="store_true", help="用临时文件验证回收站机制")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.keep <= 0:
        print("[NG] --keep 必须 >0（保留 0 个会清空整族）", file=sys.stderr)
        return 1
    if a.days <= 0:
        print("[NG] --days 必须 >0", file=sys.stderr)
        return 1

    now = time.time()
    all_targets = []
    for base in ("_scratch", ".deploy-tmp"):
        targets, kept = plan(base, a.keep, a.days, now)
        freed = sum(dir_size(p) for p in targets)
        print("== %s：待清 %d 项 / %.0fM；保留最近子目录 %d 个 ==" %
              (base, len(targets), freed / M, len(kept)))
        for p in sorted(targets, key=lambda x: -dir_size(x))[:20]:
            print("  %6.0fM  %s" % (dir_size(p) / M, os.path.relpath(p, ROOT)))
        if len(targets) > 20:
            print("  … 共 %d 项" % len(targets))
        all_targets.extend(targets)

    total = sum(dir_size(p) for p in all_targets)
    if not a.apply:
        print("dry-run：合计待清 %d 项 / %.0fM（加 --apply 执行，入回收站可恢复）" %
              (len(all_targets), total / M))
        return 0

    ok, fail = recycle(all_targets)
    residue = [os.path.relpath(p, ROOT) for p in all_targets if os.path.exists(p)]
    print("已回收 %d 项 / 失败 %d 项 / 原位残留 %d 项；回收约 %.0fM" %
          (ok, fail, len(residue), total / M))
    if residue:
        print("  残留：%s" % residue, file=sys.stderr)
    if all_targets and ok == 0:
        print("::warning title=本地轮换空转::有计划却一条没回收成，检查盘类型/权限" , file=sys.stderr)
        return 1
    return 1 if fail else 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())