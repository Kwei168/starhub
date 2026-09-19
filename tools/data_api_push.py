# -*- coding: utf-8 -*-
"""StarHub 唯一可用的推送通道：GitHub Data API + 推送前守门 + 推完自查。

为什么不用 `git push`：主仓 `.git` 已膨胀到 6.8GB 且含断链对象，`fetch/push` 直连一律失败（2026-09-19 实测）。
为什么要守门：`update.yml` 的 auto-commit 会把它检出时刻的 docs/源码按文件名写回，
  在构建进行中推送 = 几分钟后被回滚（2026-09-19 晚吞掉两次文档推送）。
为什么推完要自查：Data API 不回写本地工作树，本地与远端是两条并行历史，只有 blob 比对才知道有没有落住。

用法：
  py -3.11 tools/data_api_push.py --msg "提交信息" HANDOFF.md docs/xxx.md
  py -3.11 tools/data_api_push.py --check-only                 # 只跑守门
  py -3.11 tools/data_api_push.py --allow-running --msg ... p   # 明知有构建在跑仍要推（大概率被回滚）
"""
import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

# 只在作为脚本跑时改挂载 stdout：pytest 捕获态下重挂载会吞掉测试输出
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.github.com"
REPO = "repos/Kwei168/starhub"
WF = ".github/workflows/update.yml"


def req(method, path, body=None, tries=6):
    """该端点频繁 TLS EOF；半程失败只会留下孤儿 blob 而不动 ref，所以每步都要重试。"""
    token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
    last = None
    for k in range(tries):
        try:
            r = urllib.request.Request(API + "/" + path, method=method,
                                       headers={"Authorization": "Bearer " + token,
                                                "Accept": "application/vnd.github+json",
                                                "Content-Type": "application/json"})
            data = json.dumps(body).encode() if body is not None else None
            with urllib.request.urlopen(r, data, timeout=90) as f:
                return json.loads(f.read().decode())
        except Exception as exc:
            last = exc
            print("  重试 %d/%d %s %s: %s" % (k + 1, tries, method, path.split("/")[-1], exc),
                  file=sys.stderr)
            time.sleep(3 + 3 * k)
    raise last


def runs(per_page=10):
    return req("GET", "%s/actions/runs?per_page=%d" % (REPO, per_page))["workflow_runs"]


def gate():
    """返回 (ok, 说明)。判据只有一条：当前没有任何未完成的 run（未跑完的那场随时会按文件名回滚 docs）。"""
    rs = runs()
    busy = [r for r in rs if r["status"] != "completed"]
    if busy:
        return False, "有 %d 场构建未结束，现在推会被它的 Commit 步骤回滚：%s" % (
            len(busy), ["%s created=%s status=%s" % (r["id"], r["created_at"][11:19], r["status"])
                        for r in busy])
    newest = max(rs, key=lambda r: r["created_at"])
    return True, "守门通过：无在跑 run；最近一场 %s created=%s 已 completed" % (
        newest["id"], newest["created_at"][11:19])


def verify(expect, tag):
    bad = 0
    for p, want in expect.items():
        got = req("GET", "%s/contents/%s" % (REPO, p))
        if got["sha"] != want:
            bad += 1
            print("  [NG] %s %s 远端=%s 期望=%s" % (tag, p, got["sha"][:10], want[:10]))
        else:
            print("  [OK] %s %s %s" % (tag, p, want[:10]))
    return bad


def risky_runs(push_ts):
    """检出时刻早于本次推送、且还没提交的 run —— 它结束后会用旧 index 覆盖我们刚推的内容。"""
    return [r for r in runs(10) if r["created_at"] < push_ts and r["status"] != "completed"]


def expand_paths(paths):
    """目录参数展开成其中的文件（原子推送要靠一次列出全部路径，逐个数文件正是漏项的来源）。"""
    out = []
    for p in paths:
        lp = p.replace("/", os.sep)
        if os.path.isdir(lp):
            for root, dirs, files in os.walk(lp):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in sorted(files):
                    if fn.endswith((".pyc", ".pyo")):
                        continue
                    out.append(os.path.join(root, fn).replace(os.sep, "/"))
        else:
            out.append(p)
    return out


def ci_atomic_deps(push_paths):
    """推 `.github/workflows/update.yml` 时的原子性检查：它引用的每条测试路径必须"这次一起推"或"远端已有"。

    实测依据（09-20 07:1x 核实）：门禁 A2 `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`
    没有 `continue-on-error`（是 blocking），而 `Deploy to Vercel` 也没有 `if:` → 默认 success()。
    pytest 找不到目录会退出码 4，于是**提交步骤与部署一起被跳过**，站点整小时冻住。
    """
def ci_atomic_deps(push_paths, wf=WF):
    """推 workflow 时的原子性检查：它引用的每条测试路径必须"这次一起推"或"远端已有"。

    实测依据（09-20 07:1x 核实）：门禁 A2 `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`
    没有 `continue-on-error`（是 blocking），而 `Deploy to Vercel` 也没有 `if:` → 默认 success()。
    pytest 找不到目录会退出码 4，于是**提交步骤与部署一起被跳过**，站点整小时冻住。
    调用方负责只在推送集含 workflow 时才调它（wf 参数可指向 fixture，供测试用）。
    """
    try:
        text = open(wf.replace("/", os.sep), encoding="utf-8").read()
    except OSError:
        return [wf + " 本地读不到"]
    refs = set()
    for line in text.splitlines():
        if "pytest" in line or re.search(r"python[^\n]*test_[\w/]+\.py", line):
            for tok in re.findall(r"[\w./-]*(?:tests/[\w./-]+|test_[\w.-]+\.py)", line):
                refs.add(tok.rstrip("/"))
    problems = []
    for p in sorted(refs):
        if not os.path.exists(p.replace("/", os.sep)):
            problems.append("%s —— 本地不存在，推上去 A2 必红" % p)
            continue
        if p in push_paths or any(x.startswith(p + "/") for x in push_paths):
            continue
        try:
            req("GET", "%s/contents/%s" % (REPO, p), tries=2)
        except Exception:
            problems.append("%s —— 本地有但远端没有，且不在本次推送里 → A2 会退出码 4，"
                            "连 Commit 带 Vercel 部署一起停摆。把它加进同一次推送" % p)
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--msg", default="")
    ap.add_argument("--msg-file", default="", help="从 UTF-8 文件读提交信息（CJK 走 argv 容易被 shell 吃掉）")
    ap.add_argument("--wait-window", action="store_true", help="守门不过就每 60s 重试，最多 30 分钟")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只做守门+原子性检查并列出将要推的路径，不写远端")
    ap.add_argument("--allow-running", action="store_true")
    a = ap.parse_args()
    if a.msg_file:
        a.msg = open(a.msg_file, encoding="utf-8").read().strip()

    a.paths = expand_paths(a.paths or [])
    if a.paths and WF in a.paths:
        bad_set = ci_atomic_deps(a.paths)
        if bad_set:
            print("原子性检查未通过：")
            for b in bad_set:
                print("  [NG] " + b)
            return 1
        print("原子性检查通过：update.yml 引用的测试路径都已随本次推送或已在远端")

    ok, why = gate()
    print(why)
    if a.wait_window:
        for _ in range(30):
            if ok:
                break
            time.sleep(60)
            ok, why = gate()
            print(why)
    if a.check_only:
        return 0 if ok else 1
    if a.dry_run:
        print("dry-run：将推 %d 个路径：%s" % (len(a.paths), ", ".join(a.paths)))
        return 0
    if not ok and not a.allow_running:
        print("拒绝推送（加 --allow-running 可强行推，但大概率几分钟后被回滚）")
        return 1
    if not a.paths or not a.msg:
        print("缺参数：需要 --msg 与至少一个文件路径")
        return 1

    push_t = time.time()
    head = req("GET", REPO + "/git/ref/heads/main")["object"]["sha"]
    items, expect = [], {}
    for p in a.paths:
        raw = open(p.replace("/", os.sep), "rb").read().replace(b"\r\n", b"\n")
        blob = req("POST", REPO + "/git/blobs",
                   {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        expect[p] = blob["sha"]
        print("blob  %-56s %7d -> %s" % (p, len(raw), blob["sha"][:10]))
        items.append({"path": p, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = req("POST", REPO + "/git/trees", {"base_tree": head, "tree": items})
    commit = req("POST", REPO + "/git/commits", {"message": a.msg, "tree": tree["sha"], "parents": [head]})
    ref = req("PATCH", REPO + "/git/refs/heads/main", {"sha": commit["sha"], "force": False})
    print("parent %s -> commit %s -> ref %s" % (head[:10], commit["sha"][:10], ref["object"]["sha"][:10]))

    bad = verify(expect, "即时复查")
    # Actions 的 run 列表有 10~20s 延迟：守门通过≠真的没有在跑的场，推后必须再看一次
    # 减 120s 是为了抵消本机与 GitHub 时钟的偏差（判据方向是"更保守"，不会漏判）
    push_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(push_t - 120))
    print("等待 90s 让 run 列表落定，再确认没有『检出早于本次推送』的构建…")
    time.sleep(90)
    risky = risky_runs(push_ts)
    if risky:
        print("  [风险] 有 %d 场在本推送之前检出、尚未提交：%s" % (
            len(risky), ["%s created=%s %s" % (r["id"], r["created_at"][11:19], r["status"]) for r in risky]))
        for _ in range(40):
            if not risky_runs(push_ts):
                break
            time.sleep(30)
        print("那批构建已结束，复查是否被回滚：")
        bad = verify(expect, "构建后复查")
    else:
        print("  [OK] 无早于本次推送且未提交的 run")
    print("最终：内容不同=%d" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
