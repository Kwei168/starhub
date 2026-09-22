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
import urllib.error
import urllib.request

# 只在作为脚本跑时改挂载 stdout：pytest 捕获态下重挂载会吞掉测试输出
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.github.com"
REPO = "repos/Kwei168/starhub"
WF = ".github/workflows/update.yml"
# 所有路径都相对仓库根解析（本文件在 <root>/tools/ 下），不依赖调用时的 CWD
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 就地变异 harness 的持锁标记：见 gate() 里的说明
MUTATION_LOCK = os.path.join(ROOT, "_scratch", ".mutation-lock")


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
    if os.path.exists(MUTATION_LOCK):
        # 就地变异 harness 正在往真实文件里写变异体。这个循环会等构建窗口等上半小时，
        # 而 09-22 两次就是它在持锁窗口里读了盘：main 上先后出现过
        # `over_time -> return False` 和 `_article_from 的 "source_key": ""`。
        # 判在 runs() 之前：守门本身要联网，判锁不该联网。
        try:
            with io.open(MUTATION_LOCK, encoding="utf-8") as f:
                who = f.read().strip()[:120]
        except Exception:
            who = "?"
        return False, "有就地变异 harness 在持锁（%s），此刻读盘会把变异体推上线" % who
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


def _abs(p):
    """一律相对仓库根解析 —— 原实现用 CWD 相对路径，从别的目录调用会误判"本地不存在"。"""
    return p if os.path.isabs(p) else os.path.join(ROOT, p.replace("/", os.sep))


def norm_path(p):
    return re.sub(r"^\./", "", p.replace("\\", "/"))


def is_binary_bytes(b):
    return b"\x00" in b[:8000]


def _rel(full):
    """ROOT 相对化；跨盘符（Windows 临时目录在 C:）时 relpath 会抛 ValueError，退回绝对路径。"""
    try:
        return os.path.relpath(full, ROOT).replace(os.sep, "/")
    except ValueError:
        return full.replace(os.sep, "/")


def list_files(rel):
    """列出一个路径（文件或目录）下的文件；排除 __pycache__ 与 .pyc。"""
    ap = _abs(rel)
    if os.path.isfile(ap):
        return [rel]
    out = []
    for root, dirs, files in os.walk(ap):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith((".pyc", ".pyo")):
                continue
            out.append(_rel(os.path.join(root, fn)))
    return out


def expand_paths(paths):
    """目录参数展开成其中的文件（原子推送要靠一次列出全部路径，逐个数文件正是漏项的来源）。"""
    out = []
    for p in paths:
        p = norm_path(p)
        if os.path.isdir(_abs(p)):
            out.extend(list_files(p))
        else:
            out.append(p)
    return out


def _git_blob_sha(rel):
    """用 git hash-object 取本地 blob sha：会套用与提交时相同的转换（含 CRLF 归一），可直接与远端比。"""
    try:
        return subprocess.check_output(
            ["git", "hash-object", "--", rel], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def _head_blob_sha(rel):
    """HEAD 里该路径的 blob（拿不到=未跟踪，视为脏）。"""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD:%s" % rel],
                                       cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def local_is_clean(rel):
    """工作树该文件与 HEAD 一致 ⇒ 本地没动过它：与远端的差异属于"别人推得更新"，不是本次的事。"""
    h, w = _head_blob_sha(rel), _git_blob_sha(rel)
    return bool(h) and h == w


def remote_matches_local(rel):
    """远端该路径是否存在（目录要看能不能列出条目）。

    只判"存在与否"才是门禁的硬条件：`pytest tests/x/` 目录不存在才退出码 4；
    目录在、但缺几个**只在本地**的文件（另一会话的在途用例），门禁照样能跑完 ——
    那种情况降级为提示，不该把别人的未推文件裹进这次推送，也不该因此挡住这次发布。
    返回 (ok, 提示)。
    """
    files = list_files(rel)
    if not files:
        return False, "%s —— 本地拿不到可枚举的文件" % rel
    missing_local_only, notes = [], []
    for f in files:
        try:
            got = req("GET", "%s/contents/%s" % (REPO, f), tries=2)
        except Exception:
            missing_local_only.append(f)
            continue
        want = _git_blob_sha(f)
        if want and got.get("sha") != want:
            if local_is_clean(f):
                # 本仓常态：Data API 不回写 ⇒ 本地干净却落后远端。这时远端那份是更新的内容，
                # base_tree 会原样保留它，把它判成阻塞就等于每次发布都被别人的进度卡住。
                notes.append("%s —— 本地干净但落后远端（远端是更新的一版，本次不推它）" % f)
                continue
            return False, "%s —— 本地有未提交改动且与远端不一致（这次会把旧内容推回去）：%s" % (rel, f)
    if len(missing_local_only) == len(files):
        return False, "%s —— 远端不存在（门禁会退出码 4，连 Commit 带 Vercel 部署一起停摆）" % rel
    if notes:
        return True, "；".join(notes)
    if missing_local_only:
        return True, "%s —— 远端缺 %d 个仅本地文件 %s：门禁仍能跑，但那些用例不会在 CI 里执行" % (
            rel, len(missing_local_only), ", ".join(os.path.basename(x) for x in missing_local_only[:3]))
    return True, ""


# 这类写法不是字面路径，交给解析器判红会误报；单列出来要人看一眼
UNPARSED_HINTS = ("*", "$", "{", "<", ">")


def ci_atomic_deps(push_paths, wf):
    """推 workflow 时的原子性检查：它引用的每条测试路径必须"同批推送"或"远端已有且与本地一致"。

    实测依据（09-20 07:1x 核实）：门禁 A2 `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`
    没有 `continue-on-error`（是 blocking），而 `Deploy to Vercel` 也没有 `if:` → 默认 success()。
    pytest 找不到目录会退出码 4，于是**提交步骤与部署一起被跳过**，站点整小时冻住。
    """
    try:
        with open(_abs(wf), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return [wf + " 本地读不到"], []
    refs, odd, advisory = set(), set(), set()
    # 按步骤分块解析：advisory（带 continue-on-error，如门禁 B）引用的路径缺了不会红掉作业，
    # 拿它去阻塞发布是误伤（审查 P1-4）。
    blocks = re.split("\n      - name:", text)
    for block in blocks:
        is_adv = "continue-on-error: true" in block
        for line in block.splitlines():
            for m in re.finditer(r"(?:python3?|bash|sh)\s+((?:[\w./-]+/)?[\w.-]+\.(?:py|sh))", line):
                tok = norm_path(m.group(1))
                if any(h in tok for h in UNPARSED_HINTS):
                    odd.add("%s —— 通配/matrix 模板写法，无法机器判定，请人工确认已同批推送" % tok)
                elif is_adv:
                    advisory.add(tok)
                else:
                    refs.add(tok)
            if "pytest" not in line and not re.search(r"python[^\n]*test_[\w/]+\.py", line):
                continue
            line = re.sub(r"--[\w-]+=\S+", " ", line)
            for tok in re.findall(r"[\w./$*{}<>-]*(?:tests/[\w./$*{}<>-]+|test_[\w.$*{}<>-]+\.py)", line):
                tok = tok.rstrip("/")
                if tok.startswith("-"):
                    continue
                if any(h in tok for h in UNPARSED_HINTS):
                    odd.add("%s —— 通配/matrix 模板写法，无法机器判定，请人工确认已同批推送" % tok)
                elif is_adv:
                    advisory.add(norm_path(tok))
                else:
                    refs.add(norm_path(tok))
    refs -= advisory          # 只要有一个 blocking 步引用它，才需要强制
    problems = []
    for p in sorted(refs):
        if not os.path.exists(_abs(p)):
            problems.append("%s —— 本地不存在，推上去该门禁必红" % p)
            continue
        if p in push_paths or any(x.startswith(p + "/") for x in push_paths):
            continue
        ok, note = remote_matches_local(p)
        if not ok:
            problems.append(note)
        elif note:
            odd.add(note)
    for p in sorted(advisory - refs):
        if not os.path.exists(_abs(p)):
            odd.add("%s —— 仅 advisory 步引用且本地不存在（不阻塞发布，但该步会红）" % p)
    return problems, sorted(odd)


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
    # 任一 workflow 被推都要过原子性检查（原实现只认 update.yml 这一个字符串）
    wfs = [p for p in a.paths if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))]
    for wf in wfs:
        problems, odd = ci_atomic_deps(a.paths, wf)
        for o in odd:
            print("  [?] %s：%s" % (wf, o))
        if problems:
            print("原子性检查未通过（%s）：" % wf)
            for b in problems:
                print("  [NG] " + b)
            return 1
        print("原子性检查通过：%s 引用的测试路径都已随本次推送，或远端已有且与本地逐文件一致" % wf)

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
        with open(_abs(p), "rb") as fh:
            raw = fh.read()
        # 无条件 CRLF→LF 会毁掉被跟踪的二进制（仓库里有 4 个 .png）；只对文本做归一
        if not is_binary_bytes(raw):
            raw = raw.replace(b"\r\n", b"\n")
        blob = req("POST", REPO + "/git/blobs",
                   {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        expect[p] = blob["sha"]
        print("blob  %-56s %7d -> %s" % (p, len(raw), blob["sha"][:10]))
        items.append({"path": p, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree_sha = None
    for attempt in range(1, 5):
        # 422 的意思是"父提交已落后"：白天那场随时可能把 main 往前推。
        # req() 里那 6 次重试是同一份请求重发，对 422 完全无效 —— 必须重读 head、
        # 用新 base_tree 重建 tree+commit 再 PATCH，否则一定 6 次同样失败（今天实撞过）。
        if attempt > 1:
            head = req("GET", REPO + "/git/ref/heads/main")["object"]["sha"]
        try:
            tree = req("POST", REPO + "/git/trees", {"base_tree": head, "tree": items})
            commit = req("POST", REPO + "/git/commits",
                         {"message": a.msg, "tree": tree["sha"], "parents": [head]})
            ref = req("PATCH", REPO + "/git/refs/heads/main",
                      {"sha": commit["sha"], "force": False})
            break
        except urllib.error.HTTPError as e:
            if e.code != 422 or attempt == 4:
                raise
            print("  ref 被推进过（422），重读 head 重建提交：%d/4" % attempt)
            time.sleep(2 * attempt)
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
