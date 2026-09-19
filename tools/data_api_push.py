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
import subprocess
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.github.com"
REPO = "repos/Kwei168/starhub"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--msg", default="")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--allow-running", action="store_true")
    a = ap.parse_args()

    ok, why = gate()
    print(why)
    if a.check_only:
        return 0 if ok else 1
    if not ok and not a.allow_running:
        print("拒绝推送（加 --allow-running 可强行推，但大概率几分钟后被回滚）")
        return 1
    if not a.paths or not a.msg:
        print("缺参数：需要 --msg 与至少一个文件路径")
        return 1

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

    bad = 0
    for p, want in expect.items():
        got = req("GET", "%s/contents/%s" % (REPO, p))
        if got["sha"] != want:
            bad += 1
            print("  [NG] 复查不符 %s 远端=%s 期望=%s" % (p, got["sha"][:10], want[:10]))
        else:
            print("  [OK] 复查一致 %s %s" % (p, want[:10]))
    print("推完自查：内容不同=%d" % bad)
    return 0 if bad == 0 else 1


sys.exit(main())
