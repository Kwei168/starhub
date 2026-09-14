# tests/rss_composite/regression_composite.py
# -*- coding: utf-8 -*-
"""复合排序全量回归

验收标准：
  V1: _tag_articles() 为真实快照文章生成标签，覆盖率 ≥50%
  V2: weightedShuffle 窗口=0 与纯时间降序逐条一致（跑 JS 套件，含 D13）
  V3: diverse 模式不破坏现有排序测试（跑 rss_sort 套件）
  V4: 分块产物包含 tags 字段（离线构造 chunk0 后 dump 检查）
  V5: 配置键存在；diverse_enabled=false 时 sort-select 不含 diverse option
  V6: 确定性 — 同一输入两次打标+分块产物一致
"""
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _loader import load_build

B = load_build()
PY = sys.executable

FAIL = 0
PASS = 0
failures = []


def eq(actual, expected, label):
    global FAIL, PASS
    if actual == expected:
        PASS += 1
        print("  [PASS] %s" % label)
    else:
        FAIL += 1
        failures.append(label)
        print("  [FAIL] %s\n         期望 %r\n         实得 %r" % (label, expected, actual))


def ok(cond, label):
    eq(bool(cond), True, label)


def run(name, script):
    p = subprocess.run([PY, script], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


print("=" * 74)
print("V1: _tag_articles 覆盖率（真实 rss_api_snapshot.json）")
print("=" * 74)

snapshot_path = os.path.join(ROOT, "rss_api_snapshot.json")
if os.path.exists(snapshot_path):
    with io.open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    sources = snapshot.get("sources", [])
    ok(len(sources) > 0, "V1a 快照含源（%d 个）" % len(sources))
    test_sources = sources[:20]
    B._tag_articles(test_sources)
    total = 0
    tagged = 0
    bad_format = 0
    for s in test_sources:
        for it in s.get("items", []):
            total += 1
            tags = it.get("tags") or []
            if tags:
                tagged += 1
            if not all(isinstance(t, str) and len(t) >= 2 for t in tags):
                bad_format += 1
    rate = tagged / total if total else 0
    eq(bad_format, 0, "V1b 标签格式全部合法（长度≥2 的字符串）")
    ok(rate >= 0.5, "V1c 标签覆盖率 ≥50%%（实际 %.1f%%，%d/%d）" % (rate * 100, tagged, total))
else:
    print("  [SKIP] rss_api_snapshot.json 不存在，跳过 V1")

print()
print("=" * 74)
print("V2/V3: 跨套件回归")
print("=" * 74)

rc, out = run("diverse", os.path.join(HERE, "test_diverse_js.py"))
ok(rc == 0, "V2 weightedShuffle JS 套件全绿（含 D13 窗口=0 等价性）")
rc2, out2 = run("rss_sort", os.path.join(ROOT, "tests", "rss_sort", "test_rss_sort.py"))
ok(rc2 == 0, "V3 rss_sort 套件全绿（diverse 未破坏现有排序）")
rc3, out3 = run("rss_date", os.path.join(ROOT, "tests", "rss_date", "test_split_chunks.py"))
ok(rc3 == 0, "V3b rss_date 分块套件全绿")

print()
print("=" * 74)
print("V4: 分块产物包含 tags")
print("=" * 74)

if os.path.exists(snapshot_path):
    src_for_chunk = [{"key": s.get("key"), "name": s.get("name"), "cat": s.get("cat"),
                      "color": s.get("color"), "tier": s.get("tier", 3),
                      "items": list(s.get("items", []))} for s in sources[:5]]
    B._tag_articles(src_for_chunk)
    c0, c1 = B._split_data_chunks(src_for_chunk, chunk0_size=50)
    dump0 = json.dumps({"sources": c0}, ensure_ascii=False, separators=(",", ":"))
    ok('"tags"' in dump0, "V4a chunk0 序列化后含 tags 字段")
    n_items = sum(len(s.get("items", [])) for s in c0)
    n_tag = sum(1 for s in c0 for it in s.get("items", []) if "tags" in it)
    eq(n_tag, n_items, "V4b chunk0 每篇都带 tags（%d/%d）" % (n_tag, n_items))
else:
    print("  [SKIP] 无快照，跳过 V4")

print()
print("=" * 74)
print("V5: diverse 配置")
print("=" * 74)

config_path = os.path.join(ROOT, "build_config.json")
with io.open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)
ok("diverse_enabled" in cfg, "V5a build_config 含 diverse_enabled")
ok("diverse_window_minutes" in cfg, "V5b build_config 含 diverse_window_minutes")
eq(cfg.get("diverse_window_minutes", 0), 120, "V5c 默认窗口 = 120 分钟")

# 配置缺失时回落到默认值（不崩溃）
ok(B._load_diverse_config()["window_minutes"] == cfg.get("diverse_window_minutes", 120),
   "V5d _load_diverse_config() 读到配置窗口")

# diverse_enabled=false → 不渲染 diverse option
try:
    html_off = B.build_html([], "2026-09-14 15:00", 0, 0, analysis_data=None,
                            diverse_window_minutes=120, diverse_enabled=False)
    html_on = B.build_html([], "2026-09-14 15:00", 0, 0, analysis_data=None,
                           diverse_window_minutes=120, diverse_enabled=True)
    ok('value="diverse"' not in html_off, "V5e diverse_enabled=false 时不渲染 diverse option")
    ok('value="diverse"' in html_on, "V5f diverse_enabled=true 时渲染 diverse option")
    ok("var DIVERSE_WINDOW = 120;" in html_on, "V5g DIVERSE_WINDOW 注入正确")
except Exception as e:
    eq(True, False, "V5 build_html 调用异常: %s" % e)

print()
print("=" * 74)
print("V6: 确定性")
print("=" * 74)

if os.path.exists(snapshot_path):
    def build_twice():
        s1 = [{"key": s.get("key"), "name": s.get("name"), "items": list(s.get("items", []))}
              for s in sources[:5]]
        B._tag_articles(s1)
        return json.dumps(s1, ensure_ascii=False, sort_keys=True)
    eq(build_twice(), build_twice(), "V6 同一输入两次打标结果完全一致")
else:
    print("  [SKIP] 无快照，跳过 V6")

print()
print("=" * 74)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if failures:
    for f in failures:
        print("  - %s" % f)
sys.exit(1 if FAIL else 0)
