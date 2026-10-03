# -*- coding: utf-8 -*-
"""推下一批之前的生产验证门槛（判据：tests/tools/test_prod_verify_verdict.py）。

存在的理由是一条真实事故：Vercel 部署连续 6 场没落地，而我照样一批批往下推 ——
把"CI 绿"当成了"改动生效"。从此远端写入前必须先跑本工具，产出时间戳；
`tools/data_api_push.py` 见不到新鲜的时间戳就拒绝推送。

用法：
  py -3.11 tools/prod_verify.py            # 现取读数 → 写 .deploy-tmp/_prod_verify.json
  py -3.11 tools/prod_verify.py --print    # 只打印，不落时间戳（不给推送用）
分三级：blocking（站点/API 现在是坏的，拒绝推）/ warn（能推，但把未闭环的话写进推送日志）/ ok。
已知未修的问题不该永久卡住进度 —— 那只会逼人绕门槛，所以它判 warn 并把证据带上。
"""
import io
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = os.path.join(ROOT, ".deploy-tmp", "_prod_verify.json")
MAX_AGE_S = 90 * 60          # 过期戳不算验证过
PAGES_BASE = "https://kwei168.github.io/starhub/"
VERCEL_BASE = "https://starhub-refresh.vercel.app/"
PAGES = ("index.html", "ai-daily.html", "rss-aggregator.html", "daily-insight-history.html")
API = ("api/rss", "api/news")
REPO = "Kwei168/starhub"


def verdict(r):
    """读数 → (level, why)。纯函数，不发网络，判据钉的就是这张表。"""
    for name, code in sorted((r.get("pages") or {}).items()):
        if code != 200:
            return "blocking", "站点页面 %s 是 %s（站点现在是坏的，先修它再谈推送）" % (name, code)
    for name, code in sorted((r.get("api") or {}).items()):
        if code not in (200, 400):        # api/rss 无参时按 400 也算活着
            return "blocking", "Vercel 函数 %s 是 %s（API 主机坏了）" % (name, code)
    if not (r.get("pages") and r.get("api")):
        return "blocking", "取数失败：页面或 API 一条读数都没有 ⇒ 取不到不等于没问题"
    runs = r.get("last_runs") or []
    if not runs:
        return "blocking", "取数失败：读不到任何构建场次"
    latest = runs[-1]
    warns = []
    if latest.get("pages") != "success":
        warns.append("上一场 %s 未发布 Pages（=%s）⇒ 站点停在更早的产物" % (
            latest.get("num"), latest.get("pages")))
    stuck = [x for x in runs if x.get("vercel") != "success"]
    if len(stuck) >= 3 and stuck == runs[-len(stuck):]:
        warns.append("Vercel 连续 %d 场（%s–%s）未落地 ⇒ 依赖 Vercel 部署的改动在生产上还没生效" % (
            len(stuck), stuck[0].get("num"), stuck[-1].get("num")))
    if r.get("public_internal"):
        warns.append("Vercel 域仍公开 %d 个内部项：%s" % (
            len(r["public_internal"]), ", ".join(r["public_internal"][:6])))
    return ("warn", "；".join(warns)) if warns else ("ok", "站点与 API 都活着，上一场已发布，公开面已关")


def stamp_is_fresh(stamp, now=None):
    now = time.time() if now is None else now
    ts = stamp.get("ts") if isinstance(stamp, dict) else None
    return isinstance(ts, (int, float)) and (now - ts) < MAX_AGE_S


# ── 取数（真跑时才会用到；判据不碰这一层）──────────────────────────────────────
def _http(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=45) as f:
                body = f.read()
            return body, 200
        except Exception as exc:
            last = exc
    return str(last), 0


def _code(url):
    body, code = _http(url)
    if code != 200:
        try:
            import subprocess
            return int(subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                       "--max-time", "25", url],
                                      capture_output=True, text=True).stdout.strip() or 0)
        except Exception:
            return 0
    return 200


def read_public_internal():
    """改前基线里那些"要靠 Vercel 部署才关掉"的名字，现在有几个还开着。"""
    base = os.path.join(ROOT, ".deploy-tmp", "_vercel_pre_baseline.json")
    if not os.path.exists(base):
        return []
    keep = PAGES + API + ("rss_sources.json", "vendor_qrcode.min.js")
    names = [k for k, v in json.load(io.open(base, encoding="utf-8")).items()
             if v == "200" and not k.startswith(keep) and not k.startswith(("api/", "lib/"))]
    return [n for n in names if _code(VERCEL_BASE + n) == 200]


def read_runs(n=8):
    import subprocess
    p = subprocess.run(["gh", "api", "repos/%s/actions/runs?per_page=%d" % (REPO, n)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        return []
    out = []
    for r in reversed(json.loads(p.stdout).get("workflow_runs", [])):
        j = subprocess.run(["gh", "api", "repos/%s/actions/runs/%s/jobs" % (REPO, r["id"])],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        con = {}
        if not j.returncode:
            for s in (json.loads(j.stdout).get("jobs") or [{}])[0].get("steps", []):
                con[s["name"]] = s["conclusion"]
        out.append({"num": r["run_number"],
                    "pages": next((v for k, v in con.items() if k.startswith("Deploy to GitHub Pages")), None),
                    "vercel": next((v for k, v in con.items() if k.startswith("Deploy to Vercel")), None)})
    return out


def main(argv=None):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    readings = {
        "pages": {p: _code(PAGES_BASE + p) for p in PAGES},
        "api": {a: _code(VERCEL_BASE + a) for a in API},
        "last_runs": read_runs(),
        "public_internal": read_public_internal(),
        "fingerprint_gap_hours": None,
    }
    level, why = verdict(readings)
    stamp = {"ts": time.time(), "level": level, "why": why, "readings": readings}
    print("[prod-verify] %s — %s" % (level.upper(), why))
    if "--print" in argv:
        return 0 if level != "blocking" else 1
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    json.dump(stamp, io.open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("时间戳已写入 %s（有效期 %d 分钟）" % (STAMP, MAX_AGE_S // 60))
    return 0 if level != "blocking" else 1


if __name__ == "__main__":
    sys.exit(main())
