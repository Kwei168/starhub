# -*- coding: utf-8 -*-
"""批 6 冷启动判据的变异电池：破坏生产读取端的缺失分支，判据必须转红。

就地改的只有本地工作副本，且 finally 里逐字节还原（sha256 必须回到初始值）；
这些文件本身不在本次推送清单里，还原失败会立刻抛错而不是静默留下脏副本。
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST = os.path.join("tests", "rss_history", "test_cold_start_readers.py")
AGG = os.path.join(ROOT, "build_rss_aggregator.py")
INS = os.path.join(ROOT, "build_daily_insight.py")

MUTS = [
    ("K1 _load_prev_analysis 缺失时返回 {} 而不是 None", AGG,
     "    if not os.path.exists(ANALYSIS_SNAPSHOT_FILE):\n        return None",
     "    if not os.path.exists(ANALYSIS_SNAPSHOT_FILE):\n        return {}"),
    ("K2 _trans_cache 初始值改成 None（首场 `in` 直接抛）", AGG,
     '_trans_cache = {}  # {text_hash: translated_text}',
     "_trans_cache = None"),
    ("K3 _load_caches 缺失分支覆写全局（契约变成会清空）", AGG,
     "    if os.path.exists(TRANS_CACHE_FILE):",
     "    if True:\n        _trans_cache = {}\n    if os.path.exists(TRANS_CACHE_FILE):"),
    ("K4 _load_history 缺失时返回 None（30 天历史页会炸在下游）", INS,
     "    if not os.path.exists(HISTORY_FILE):\n        return {\"days\": []}",
     "    if not os.path.exists(HISTORY_FILE):\n        return None"),
]


def run(label):
    p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                        "-p", "no:cacheprovider"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    lines = (p.stdout or "").strip().splitlines()
    failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
    return p.returncode != 0, (lines[-1] if lines else "?"), failed


orig = {f: open(f, "rb").read() for f in (AGG, INS)}
h0 = {f: hashlib.sha256(v).hexdigest() for f, v in orig.items()}
base_red, base_tail, _ = run("baseline")
print("基线（未变异）：%s  rc_expected=green" % base_tail)
if base_red:
    print("基线不绿 ⇒ 不声称任何覆盖率")
    sys.exit(1)
escapes = 0
try:
    for label, path, a, b in MUTS:
        src = orig[path].decode("utf-8")
        # 生产文件的行尾不统一（build_rss_aggregator.py 是 CRLF、build_daily_insight.py 是 LF），
        # 锚点必须按目标文件自己的行尾来拼，否则多行锚点一处也命中不了 = 静默 INVALID。
        nl = "\r\n" if "\r\n" in src else "\n"
        aa = a.replace("\n", nl)
        bb = b.replace("\n", nl)
        if src.count(aa) != 1:
            print("%-58s INVALID（锚点命中 %d 次）" % (label, src.count(aa)))
            escapes += 1
            continue
        open(path, "w", encoding="utf-8", newline="").write(src.replace(aa, bb, 1))
        red, tail, failed = run(label)
        print("%-58s %s %s%s" % (label, "RED  " if red else "GREEN(判据漏了!)", tail[:44],
                                 ("  <- " + ", ".join(failed[:2])) if failed else ""))
        if not red:
            escapes += 1
finally:
    for path, blob in orig.items():
        open(path, "wb").write(blob)
bad = [p for p in orig if hashlib.sha256(open(p, "rb").read()).hexdigest() != h0[p]]
print("还原校验：%s" % ("两份生产文件逐字节回到初始值" if not bad else "失败 %s" % bad))
print("未被挡住的变异/无效变异：%d" % escapes)
sys.exit(1 if escapes or bad else 0)
