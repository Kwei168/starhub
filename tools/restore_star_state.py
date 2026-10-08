# -*- coding: utf-8 -*-
"""P1 分支解耦的**读端**：把 star 状态从它自己的 orphan 分支 `star-state` 并集回工作树。

为什么要有这一步：`star-fast.yml` 每 15 分钟往 `main` 提交一次 `known_categories.json` /
`known_notes.json`，而 `update.yml` 单场构建要 ~35 分钟 ⇒ 小时场的 `git push` 必然撞上它，
重试只有一次且重试本身要 5 分钟，第二次再被拒就整场红、Pages 整场不发（2026-10-07 04:00 实锤）。
让 star 状态改推 `star-state`（本车道是唯一写者 ⇒ 不需要 merge、不需要重试链），`main` 的
自动写者就只剩 update.yml 一个；小时场在构建前把状态读回来，功能上等价、时序上不再争抢。

三条不可让的约束（都对应真实事故形状）：
① **并集，绝不缩小**：star-state 的值覆盖同名键，main 独有的键一律保留。
   于是"star-state 被误清空/写坏"最坏只退化成"没拿到新分类"，不会退化成"分类表被抹掉"。
② **地板值闸门**：合并后 `known_categories` 的键数必须 ≥ FLOOR_KEYS。
   `fast_refresh.py` 是按"不在 known 表里"对全表做 diff 来决定烧多少 LLM，
   空表 = 293 条全量重烧（现取 main 上 293 键）；地板取 200 留余量。不达标就**一个字节都不写**。
③ **读不到只降级、绝不挡发布**：分支不存在 / fetch 失败 / 解析失败 ⇒ 保持 main 那份 + 报
   warning + 退出 0。本仓有"A2 blocking + Deploy 无 if"的连坐教训，新链路不许成为新的单点。

用法（update.yml 在 Sync to latest remote 之后调用）：
    python tools/restore_star_state.py || echo "::warning::..."
退出码恒为 0（真异常也只报 warning），除 --strict 模式外。
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = "star-state"
FILES = ("known_categories.json", "known_notes.json")
FLOOR_KEYS = 200          # 见②：现取 main 上 known_categories 有 293 键
BJT = timezone(timedelta(hours=8))


def _sh(*args):
    """跑 git，返回 (rc, stdout+stderr)。不抛异常——本步的任何失败都只该降级。"""
    try:
        r = subprocess.run(("git", "-C", ROOT) + args, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 124, "launcher error: %s" % exc


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _show(rev, name):
    """从某个 rev 取文件内容（走 git show，不动工作树）。"""
    rc, out = _sh("show", "%s:%s" % (rev, name))
    return out if rc == 0 else None


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _stamp(kind, detail):
    """落痕到 build_logs/（形状与 update.yml:511-514 的 pages_missing 一致，便于同一套读法）。"""
    try:
        d = os.path.join(ROOT, "build_logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, datetime.now(BJT).strftime("%Y-%m-%d") + ".jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(BJT).isoformat(),
                                "type": "star_state_readback", "kind": kind,
                                "detail": detail}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 —— 落痕失败不该影响主流程，但也不能静默到查不到
        sys.stderr.write("[star-state] 落痕失败（build_logs 不可写）\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strict = "--strict" in argv       # --strict：任何降级都非零退出（判据用，CI 不用）

    rc, out = _sh("ls-remote", "--exit-code", "--heads", "origin", BRANCH)
    if rc != 0:
        print("::warning::[star-state] 远端无 %s 分支（还没启用或已删）——本场用 main 上的副本" % BRANCH)
        _stamp("branch_absent", "keep main copy")
        return 1 if strict else 0

    tip = out.split()[0]
    rc, err = _sh("fetch", "-q", "origin", "+refs/heads/%s:refs/remotes/origin/%s" % (BRANCH, BRANCH))
    if rc != 0:
        print("::warning::[star-state] fetch 失败：%s——本场用 main 上的副本" % err.strip()[:160])
        _stamp("fetch_failed", err.strip()[:160])
        return 1 if strict else 0

    merged_any = {}
    for name in FILES:
        base = _load(os.path.join(ROOT, name))
        if base is None:
            print("::warning::[star-state] 工作树 %s 读不出可解析的 JSON——跳过该文件（不动它）" % name)
            _stamp("base_unreadable", name)
            continue
        raw = _show("refs/remotes/%s/%s" % ("origin", BRANCH), name)
        if raw is None:
            print("::warning::[star-state] %s 不在 %s 上——保留 main 那份" % (name, BRANCH))
            merged_any[name] = ("kept", len(base))
            continue
        try:
            incoming = json.loads(raw)
        except Exception:  # noqa: BLE001
            print("::warning::[star-state] %s 在 %s 上不是合法 JSON——保留 main 那份" % (name, BRANCH))
            _stamp("incoming_unparseable", name)
            merged_any[name] = ("kept", len(base))
            continue
        if not isinstance(incoming, dict):
            print("::warning::[star-state] %s 形状不是对象（%s）——保留 main 那份" % (name, BRANCH, type(incoming).__name__))
            _stamp("incoming_bad_shape", name)
            merged_any[name] = ("kept", len(base))
            continue
        # ① 并集：incoming 覆盖同名键，base 独有的键一律保留 ⇒ 合并结果只会 ≥ 两边
        merged = dict(base)
        added = 0
        for k, v in incoming.items():
            if k not in merged:
                added += 1
            merged[k] = v
        merged_any[name] = ("merged", len(merged), added, len(base), len(incoming))

    # ② 地板值闸门：以 known_categories 的键数为准（它决定烧多少 LLM）
    kc = merged_any.get("known_categories.json")
    if kc and kc[0] == "merged" and kc[1] < FLOOR_KEYS:
        print("::error::[star-state] 合并后 known_categories 只有 %d 键（地板 %d）——"
              "判定为异常状态，一个文件都不写，本场退回 main 副本" % (kc[1], FLOOR_KEYS))
        _stamp("floor_rejected", "merged=%d floor=%d" % (kc[1], FLOOR_KEYS))
        return 1 if strict else 0

    for name, info in merged_any.items():
        if info[0] != "merged":
            continue
        # 重新读一次 base 做写回（上面只算了计数，值在 incoming/base 里；重读保证幂等与单一来源）
        base = _load(os.path.join(ROOT, name))
        raw = _show("origin/%s" % BRANCH, name)
        incoming = json.loads(raw)
        merged = dict(base)
        merged.update(incoming)
        _atomic_write(os.path.join(ROOT, name), merged)
        print("[star-state] %s：main %d 键 + 分支 %d 键 → 并集 %d 键（本场新增 %d）"
              % (name, info[3], info[4], info[1], info[2]))
        _stamp("merged", "%s base=%d branch=%d union=%d added=%d tip=%s"
               % (name, info[3], info[4], info[1], info[2], tip[:10]))

    if not merged_any:
        print("::warning::[star-state] 两个文件都没能合并（见上面的 warning）——本场用 main 副本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
