"""
build_logger.py - StarHub 构建日志系统
JSONL 格式，每日一个文件，追加写入
存储路径: build_logs/YYYY-MM-DD.jsonl
"""

import json
import os
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
LOG_DIR = "build_logs"


def _log_file():
    """返回今天的日志文件路径"""
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{today}.jsonl")


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def append(entry: dict):
    """追加一条日志记录"""
    _ensure_dir()
    if "ts" not in entry:
        entry["ts"] = datetime.now(BJT).isoformat()
    with open(_log_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read(date_str=None, event_type=None, limit=100, offset=0):
    """读取日志，支持按日期、类型过滤，分页返回"""
    _ensure_dir()
    if date_str:
        files = [os.path.join(LOG_DIR, f"{date_str}.jsonl")]
    else:
        # 默认读最近 7 天
        files = []
        for i in range(7):
            d = (datetime.now(BJT) - timedelta(days=i)).strftime("%Y-%m-%d")
            p = os.path.join(LOG_DIR, f"{d}.jsonl")
            if os.path.exists(p):
                files.append(p)

    entries = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and entry.get("type") != event_type:
                    continue
                entries.append(entry)

    # 按时间倒序
    entries.sort(key=lambda x: x.get("ts", ""), reverse=True)
    total = len(entries)
    page = entries[offset:offset + limit]
    return {"total": total, "entries": page, "limit": limit, "offset": offset}


def summary(date_str=None):
    """生成指定日期的构建摘要"""
    data = read(date_str=date_str, limit=1000)
    entries = data["entries"]

    builds = [e for e in entries if e.get("type") == "build"]
    triggers = [e for e in entries if e.get("type") == "trigger"]
    deploys = [e for e in entries if e.get("type") == "deploy"]
    refreshes = [e for e in entries if e.get("type") == "refresh"]

    return {
        "date": date_str or datetime.now(BJT).strftime("%Y-%m-%d"),
        "builds": len(builds),
        "triggers": len(triggers),
        "deploys": len(deploys),
        "refreshes": len(refreshes),
        "last_build": builds[0] if builds else None,
        "last_deploy": deploys[0] if deploys else None,
        "total_items_latest": builds[0].get("items_snapshot", 0) if builds else 0,
        "total_items_oldest": builds[-1].get("items_snapshot", 0) if builds else 0,
        "items_delta": (
            builds[0].get("items_snapshot", 0) - builds[-1].get("items_snapshot", 0)
            if len(builds) >= 2 else 0
        ),
    }
