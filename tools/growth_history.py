# -*- coding: utf-8 -*-
"""Read the per-build growth events back out of build_logs (offline first, remote fallback).

Companion to history_growth.py: that one measures a single build and appends a `growth` line;
this one answers "is it still growing" from the repository itself instead of scraping Actions logs
(which expire). Read-only.

Timeliness caveat (measured, not guessed): the growth step runs AFTER the commit step, so a build's
own line can only reach git at the next day-boundary commit -- build_logs is committed once a day,
while the appended lines do ride along in the starhub-state cache. So `--dir build_logs` inside CI
sees today, while the remote fallback is T+1. Print it, don't silently average it.
"""
import argparse
import json
import os
import statistics
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/Kwei168/starhub/main/build_logs/%s.jsonl"


def fetch_remote(day):
    """取远端某天日志的原文；失败返回空串（读数缺失不该让工具变红）。"""
    try:
        with urllib.request.urlopen(RAW % day, timeout=60) as fh:
            return fh.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _events_from_text(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue                      # 半截行：跳过，不让一行坏数据毁掉整份读数
        if isinstance(rec, dict) and rec.get("type") == "growth":
            out.append(rec)
    return out


def iter_growth_events(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return iter(())
    return iter(_events_from_text(text))


def growth_events_for_day(day, local_dir="build_logs", fetch=None):
    """本地优先：有 `<local_dir>/<day>.jsonl` 就不联网；缺才回落远端。"""
    p = os.path.join(local_dir or "", "%s.jsonl" % day)
    if local_dir and os.path.exists(p):
        return list(iter_growth_events(p))
    text = (fetch or fetch_remote)(day)
    return _events_from_text(text)


def summarize(events):
    events = list(events)
    if not events:
        return {"total_builds": 0, "days": [], "max_bytes": None, "median_bytes": None,
                "note": "没有 growth 事件 —— 这不代表曲线是平的，只代表还没测到"}
    by_day = {}
    for e in events:
        day = str(e.get("ts", ""))[:10]
        by_day.setdefault(day, []).append(int(e.get("new_bytes") or 0))
    sizes = [int(e.get("new_bytes") or 0) for e in events]
    days = [{"date": d, "builds": len(v), "sum_bytes": sum(v), "max_bytes": max(v),
             "mean_bytes": int(round(sum(v) / len(v)))} for d, v in sorted(by_day.items())]
    return {"total_builds": len(events),
            "total_bytes": sum(sizes),
            "max_bytes": max(sizes),
            "median_bytes": int(statistics.median(sizes)),
            "mean_bytes": int(round(sum(sizes) / len(sizes))),
            "days": days}


def recent_days(n=7):
    from datetime import date, timedelta
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="build_logs")
    ap.add_argument("--days", type=int, default=7, help="回看几天（本地缺的日期走远端）")
    a = ap.parse_args()
    events = []
    for day in recent_days(a.days):
        events.extend(growth_events_for_day(day, local_dir=a.dir))
    s = summarize(events)
    if not s["total_builds"]:
        print(s.get("note", "没有 growth 事件"))
        return 0
    print("growth 事件 %d 场｜中位 %.3f MiB｜均值 %.3f MiB｜最坏 %.3f MiB" % (
        s["total_builds"], s["median_bytes"] / 1048576, s["mean_bytes"] / 1048576,
        s["max_bytes"] / 1048576))
    print("最坏那一场通常是日界那次日志入库，不是每场重写")
    for d in s["days"]:
        print("  %-12s builds=%-3d 合计 %8.3f MiB  最大单场 %8.3f MiB" % (
            d["date"], d["builds"], d["sum_bytes"] / 1048576, d["max_bytes"] / 1048576))
    print("口径提醒：从 git 读是 T+1（growth 步跑在 Commit 之后，当天的行要等下一次日界提交）；"
          "在 CI 里直接读 build_logs/ 才是当天。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
