# 排序质量修复 v3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复日期伪造（知乎日报等 38 条同时间戳霸屏）和源族群噪音（V2EX+NodeSeek 占前 500 位 17.8%），使前 50 位覆盖 ≥8 个独立源。

**Architecture:** Python 构建期新增「同日期伪造检测」（bad_date 模式 C），标记 pub_date 全部相同的源为不可信；JavaScript 前端 `_applyRunCap` 升级为 family-aware 模式，对 V2EX 等族群施加合计配额。

**Tech Stack:** Python 3.11 / Node.js (test harness) / GitHub Actions CI

**Spec:** `docs/superpowers/specs/2026-09-15-sort-quality-v3-spec.md`

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| Modify | `build_rss_aggregator.py` L400-444 区域 | 新增 bad_date 模式 C（同日期伪造检测） |
| Modify | `build_rss_aggregator.py` L2445-2477 `_applyRunCap` | 升级为 family-aware 双级 cap |
| Modify | `build_rss_aggregator.py` JS 常量区 | 新增 `SOURCE_FAMILIES` 定义 |
| Modify | `tests/rss_composite/cases_diverse.js` | 新增 F 段（family cap）+ G 段（bad_date 排序降级）测试 |
| Create | `tests/rss_composite/test_date_uniform.py` | 同日期伪造检测的 Python 单元测试 |
| Modify | `tests/rss_composite/mutation_check.py` | 新增 4 个变异体 |

---

### Task 1: RED — 同日期伪造检测 Python 测试

**Files:**
- Create: `tests/rss_composite/test_date_uniform.py`

- [ ] **Step 1: 创建测试文件**

```python
# tests/rss_composite/test_date_uniform.py
# -*- coding: utf-8 -*-
"""同日期伪造检测（bad_date 模式 C）单元测试。

验证：当同一源的所有条目 pub_date 完全相同时，该源被标记为 bad_date。
"""
import collections
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.environ.get("RSS_BUILD_SRC", os.path.join(ROOT, "build_rss_aggregator.py"))

# 从 build_rss_aggregator.py 提取 _detect_uniform_dates 函数
src_text = open(SRC, encoding='utf-8').read()

# 提取函数体
import re
_func_match = re.search(
    r'(def _detect_uniform_dates\(.*?)(?=\ndef |\nclass |\Z)',
    src_text, re.DOTALL
)
if not _func_match:
    print("[FAIL] _detect_uniform_dates 函数未找到")
    sys.exit(1)

exec(_func_match.group(1), globals())

PASS = 0
FAIL = 0

def eq(got, want, msg):
    global PASS, FAIL
    if got == want:
        PASS += 1; print(f"  ok   {msg}")
    else:
        FAIL += 1; print(f"  FAIL {msg}\n    got  = {got!r}\n    want = {want!r}")

def ok(cond, msg):
    eq(bool(cond), True, msg)

# DU-1: 同日期源被标记
print("DU-1 同日期源（≥5 条）被标记为 bad_date")
items = [
    {"source_key": "sk_a", "pub_date": "2026-09-15T10:00:00+08:00", "link": f"l{i}"}
    for i in range(10)
]
result = _detect_uniform_dates(items, min_items=5)
ok("sk_a" in result, "DU-1a sk_a 被检出")

# DU-2: 不同日期的源不被标记
print("DU-2 不同日期的源不标记")
items2 = [
    {"source_key": "sk_b", "pub_date": f"2026-09-15T10:{i:02d}:00+08:00", "link": f"l{i}"}
    for i in range(10)
]
result2 = _detect_uniform_dates(items2, min_items=5)
ok("sk_b" not in result2, "DU-2a sk_b 不被标记")

# DU-3: 条目不足 min_items 不标记
print("DU-3 条目不足 min_items 不标记")
items3 = [
    {"source_key": "sk_c", "pub_date": "2026-09-15T10:00:00+08:00", "link": f"l{i}"}
    for i in range(3)
]
result3 = _detect_uniform_dates(items3, min_items=5)
ok("sk_c" not in result3, "DU-3a sk_c 条目不足不标记")

# DU-4: 混合源——只有同日期源被标记
print("DU-4 混合源只标记同日期源")
items4 = items + items2  # sk_a 同日期 + sk_b 不同日期
result4 = _detect_uniform_dates(items4, min_items=5)
ok("sk_a" in result4, "DU-4a sk_a 被标记")
ok("sk_b" not in result4, "DU-4b sk_b 不被标记")

# DU-5: 阈值边界——恰好 min_items 条同日期 → 标记
print("DU-5 阈值边界")
items5 = [
    {"source_key": "sk_d", "pub_date": "2026-09-15T10:00:00+08:00", "link": f"l{i}"}
    for i in range(5)
]
result5 = _detect_uniform_dates(items5, min_items=5)
ok("sk_d" in result5, "DU-5a 恰好 5 条同日期 → 标记")

# DU-6: 4 条同日期不标记（低于阈值）
items6 = items5[:4]
result6 = _detect_uniform_dates(items6, min_items=5)
ok("sk_d" not in result6, "DU-6 4 条同日期不标记")

# DU-7: 80% 同日期（非 100%）也应标记
print("DU-7 80% 同日期也标记")
items7 = [
    {"source_key": "sk_e", "pub_date": "2026-09-15T10:00:00+08:00", "link": f"l{i}"}
    for i in range(8)
] + [
    {"source_key": "sk_e", "pub_date": "2026-09-15T09:00:00+08:00", "link": "lx"}
]
result7 = _detect_uniform_dates(items7, min_items=5)
ok("sk_e" in result7, "DU-7 80% 同日期 → 标记")

print(f"\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python tests/rss_composite/test_date_uniform.py`
Expected: FAIL — `_detect_uniform_dates` 函数不存在（`re.search` 返回 None → exit(1)）

- [ ] **Step 3: Commit RED**

```bash
git add tests/rss_composite/test_date_uniform.py
git commit -m "test(date): add RED tests for uniform date detection (mode C)"
```

---

### Task 2: GREEN — 实现 `_detect_uniform_dates()` 并集成

**Files:**
- Modify: `build_rss_aggregator.py` L437 之后（现有 bad_date 审计之后）

- [ ] **Step 1: 添加 `_detect_uniform_dates` 函数**

在 `build_rss_aggregator.py` 中 `_audit_bad_dates` 函数定义之前（约 L395），插入：

```python
def _detect_uniform_dates(items, min_items=5, threshold=0.8):
    """检测同日期伪造（bad_date 模式 C）。

    同一源 ≥min_items 条条目中，超过 threshold 比例共享完全相同的 pub_date 字符串
    → 判定为日期伪造，返回该源 key 集合。

    典型场景：知乎日报 anyfeeder feed 无 pubDate，_fallback_date_iso 用 first_seen
    填充 → 同批次所有条目获得完全相同的时间戳。
    """
    from collections import Counter, defaultdict
    src_dates = defaultdict(list)
    for item in items:
        sk = item.get("source_key", "")
        pd = item.get("pub_date", "")
        if sk and pd:
            src_dates[sk].append(pd)
    
    flagged = set()
    for sk, dates in src_dates.items():
        if len(dates) < min_items:
            continue
        cnt = Counter(dates)
        most_common_date, most_common_count = cnt.most_common(1)[0]
        ratio = most_common_count / len(dates)
        if ratio >= threshold:
            flagged.add(sk)
    return flagged
```

- [ ] **Step 2: 在 bad_date 审计管线中调用**

在 `build_rss_aggregator.py` 约 L444（`_LAST_UNRELIABLE_SRCS = set(_unreliable_srcs)` 之后），插入：

```python
    # 模式 C：同日期伪造检测（知乎日报/愆伏/梅之夏等）
    _uniform_flagged = _detect_uniform_dates(
        [_rss_history[k] for k in _rss_history],
        min_items=5, threshold=0.8
    )
    if _uniform_flagged:
        _unreliable_srcs |= _uniform_flagged
        _LAST_UNRELIABLE_SRCS = set(_unreliable_srcs)
        _names = [src_map[sk]["name"] for sk in _uniform_flagged if sk in src_map][:5]
        print("[bad_date-C] 同日期伪造源 %d 个: %s" % (
            len(_uniform_flagged), ", ".join(_names)))
        # 立即标记条目
        for item in _rss_history.values():
            if item.get("source_key") in _uniform_flagged:
                item["bad_date"] = True
```

- [ ] **Step 3: 运行测试验证通过**

Run: `python tests/rss_composite/test_date_uniform.py`
Expected: PASS（DU-1 到 DU-7 全绿）

- [ ] **Step 4: 运行全量回归**

```bash
python tests/rss_composite/test_diverse_js.py
python tests/rss_composite/test_diverse_realdata.py
python tests/rss_composite/regression_composite.py
```

Expected: 全绿

- [ ] **Step 5: Commit GREEN**

```bash
git add build_rss_aggregator.py tests/rss_composite/test_date_uniform.py
git commit -m "feat(date): add uniform date detection (bad_date mode C)

Detects sources where ≥80% of items share identical pub_date strings,
flagging them as bad_date. Fixes 知乎日报/愆伏/梅之夏 fabricated dates."
```

---

### Task 3: RED — Family-aware `_applyRunCap` JS 测试

**Files:**
- Modify: `tests/rss_composite/cases_diverse.js` L557 之前（`console.log` 之前）

- [ ] **Step 1: 追加 F 段测试用例**

在 `tests/rss_composite/cases_diverse.js` 的 D25 测试之后、`console.log` 之前追加：

```javascript
/* ── F 段：族群配额（source family cap）────────────────────────────────── */

/* F1: SOURCE_FAMILIES 存在且为对象 */
it('F1 SOURCE_FAMILIES 定义', function () {
  ok(typeof SOURCE_FAMILIES === 'object', 'F1 SOURCE_FAMILIES 是对象');
  eq(SOURCE_FAMILIES['v2ex_all_50'], 'v2ex', 'F1b v2ex_all_50 → v2ex');
  eq(SOURCE_FAMILIES['nodeseek_54'], 'nodeseek', 'F1c nodeseek_54 → nodeseek');
});

/* F2: _applyRunCap 族级 cap — V2EX 4 子源合计 ≤ familyCap */
it('F2 V2EX 族群合计 cap', function () {
  ART.length = 0;
  // 构造 V2EX 4 子源各 5 条 + 异源 5 条 = 25 条
  var v2exSrcs = ['v2ex_all_50', 'v2ex_creative_52', 'v2ex_play_53', 'v2ex技术_44'];
  for (var s = 0; s < v2exSrcs.length; s++)
    for (var i = 0; i < 5; i++)
      ART.push({ t: 'V' + s + '_' + i, sk: v2exSrcs[s], date: '2026-09-14T12:0' + (s * 5 + i % 5) + ':00+08:00', ti: 2 });
  for (var i = 0; i < 5; i++)
    ART.push({ t: 'O' + i, sk: 'OTHER_' + i, date: '2026-09-14T11:0' + i + ':00+08:00', ti: 2 });
  _applyRunCap(ART, 3, SOURCE_FAMILIES);
  // 检查：V2EX 族群连续条目不超过 familyCap（默认 6）
  var famRun = 0, famMax = 0;
  for (var i = 0; i < ART.length; i++) {
    var gk = SOURCE_FAMILIES[ART[i].sk] || ART[i].sk;
    if (gk === 'v2ex') { famRun++; if (famRun > famMax) famMax = famRun; }
    else famRun = 0;
  }
  ok(famMax <= 6, 'F2 V2EX 族群最长连续 ≤6（实得 ' + famMax + '）');
  eq(ART.length, 25, 'F2b 条目守恒');
});

/* F3: 无 family 定义的源退化为单源 cap（向后兼容） */
it('F3 无 family 退化为单源 cap', function () {
  ART.length = 0;
  for (var i = 0; i < 10; i++)
    ART.push({ t: 'A' + i, sk: 'SA', date: '2026-09-14T12:0' + (i % 10) + ':00+08:00', ti: 2 });
  for (var i = 0; i < 5; i++)
    ART.push({ t: 'B' + i, sk: 'SB', date: '2026-09-14T11:0' + (i % 10) + ':00+08:00', ti: 2 });
  _applyRunCap(ART, 3, SOURCE_FAMILIES);
  var st = skRun(ART);
  ok(st.maxRun <= 3, 'F3 非 family 源 maxRun ≤3（实得 ' + st.maxRun + '）');
  eq(ART.length, 15, 'F3b 条目守恒');
});

/* F4: _applyRunCap 第三参数缺省时向后兼容 */
it('F4 _applyRunCap 缺省 families 参数', function () {
  ART.length = 0;
  for (var i = 0; i < 10; i++)
    ART.push({ t: 'X' + i, sk: 'SX', date: '2026-09-14T12:0' + (i % 10) + ':00+08:00', ti: 2 });
  _applyRunCap(ART, 3);  // 不传 families
  var st = skRun(ART);
  ok(st.maxRun <= 3, 'F4 缺省 families 仍正常 cap（实得 ' + st.maxRun + '）');
});

/* F5: NodeSeek 单源族 cap ≤ 4 */
it('F5 NodeSeek 族群 cap', function () {
  ART.length = 0;
  for (var i = 0; i < 10; i++)
    ART.push({ t: 'N' + i, sk: 'nodeseek_54', date: '2026-09-14T12:0' + (i % 10) + ':00+08:00', ti: 2 });
  for (var i = 0; i < 5; i++)
    ART.push({ t: 'M' + i, sk: 'OTHER_' + i, date: '2026-09-14T11:0' + i + ':00+08:00', ti: 2 });
  _applyRunCap(ART, 3, SOURCE_FAMILIES);
  // NodeSeek 是单源族，familyCap 应 ≤ 4
  var nsRun = 0, nsMax = 0;
  for (var i = 0; i < ART.length; i++) {
    if (ART[i].sk === 'nodeseek_54') { nsRun++; if (nsRun > nsMax) nsMax = nsRun; }
    else nsRun = 0;
  }
  ok(nsMax <= 4, 'F5 NodeSeek 连续 ≤4（实得 ' + nsMax + '）');
  eq(ART.length, 15, 'F5b 条目守恒');
});

/* F6: 条目守恒 + 集合守恒（族群 cap 不得丢篇或复制） */
it('F6 族群 cap 条目守恒', function () {
  ART.length = 0;
  var v2exSrcs = ['v2ex_all_50', 'v2ex_creative_52', 'v2ex_play_53', 'v2ex技术_44'];
  for (var s = 0; s < v2exSrcs.length; s++)
    for (var i = 0; i < 8; i++)
      ART.push({ t: 'V' + s + '_' + i, sk: v2exSrcs[s], date: '2026-09-14T12:0' + ((s * 8 + i) % 60) + ':00+08:00', ti: 2 });
  for (var i = 0; i < 10; i++)
    ART.push({ t: 'O' + i, sk: 'OTHER_' + (i % 5), date: '2026-09-14T11:0' + i + ':00+08:00', ti: 2 });
  var before = ART.map(function(a){ return a.t; }).sort().join(',');
  _applyRunCap(ART, 3, SOURCE_FAMILIES);
  var after = ART.map(function(a){ return a.t; }).sort().join(',');
  eq(ART.length, 42, 'F6a 42 条进 42 条出');
  eq(before, after, 'F6b 条目集合完全一致');
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python tests/rss_composite/test_diverse_js.py`
Expected: FAIL — `SOURCE_FAMILIES` 未定义（F1 红），`_applyRunCap` 不接受第三参数（F2-F6 红）

- [ ] **Step 3: Commit RED**

```bash
git add tests/rss_composite/cases_diverse.js
git commit -m "test(family): add RED tests for family-aware _applyRunCap"
```

---

### Task 4: GREEN — 实现 family-aware `_applyRunCap` + `SOURCE_FAMILIES`

**Files:**
- Modify: `build_rss_aggregator.py` JS 常量区（`_applyRunCap` 之前，约 L2440）
- Modify: `build_rss_aggregator.py` L2445-2477（`_applyRunCap` 函数体）

- [ ] **Step 1: 添加 `SOURCE_FAMILIES` 常量**

在 `_applyRunCap` 函数定义之前（约 L2443），插入：

```javascript
  /* 源族群定义：同族源共享打散配额，防止 V2EX 4 子源交替出现霸屏。
     key = source_key, value = family_key。未列出的源不参与族群 cap。 */
  var SOURCE_FAMILIES = {
    'v2ex_all_50': 'v2ex', 'v2ex_creative_52': 'v2ex',
    'v2ex_play_53': 'v2ex', 'v2ex技术_44': 'v2ex',
    'nodeseek_54': 'nodeseek'
  };
  /* 族群级 cap：family_key → 最大连续条数。未列出的族用单源 cap 值。 */
  var FAMILY_CAPS = { 'v2ex': 6, 'nodeseek': 4 };
```

- [ ] **Step 2: 重写 `_applyRunCap` 为 family-aware**

替换现有 `_applyRunCap` 函数（L2445-2477）为：

```javascript
  function _applyRunCap(arr, cap, families) {
    if (!arr || arr.length <= cap) return;
    families = families || {};
    var _gk = function(sk) { return families[sk] || sk; };
    var n = arr.length;
    for (var pass = 0; pass < 3; pass++) {
      var improved = false;
      for (var i = cap; i < n; i++) {
        var sk = arr[i].sk;
        var gk = _gk(sk);

        // ── Level 1: 单源 cap（原有逻辑）──
        if (arr[i].sk === arr[i-1].sk) {
          var runStart = i - 1;
          while (runStart > 0 && arr[runStart-1].sk === sk) runStart--;
          var runLen = i - runStart + 1;
          if (runLen > cap) {
            var swapped = false;
            for (var j = i + 1; j < Math.min(i + 15, n); j++) {
              if (_gk(arr[j].sk) !== gk && (j === 0 || _gk(arr[j].sk) !== _gk(arr[j-1].sk))) {
                var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                swapped = true; improved = true; break;
              }
            }
            if (!swapped) {
              for (var j = i - 1; j >= 0; j--) {
                if (_gk(arr[j].sk) !== gk) {
                  var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                  improved = true; break;
                }
              }
            }
            continue;
          }
        }

        // ── Level 2: 族群 cap ──
        if (families[sk]) {
          var famCap = (typeof FAMILY_CAPS !== 'undefined' && FAMILY_CAPS[gk]) || cap;
          if (families[arr[i-1].sk] === gk || arr[i-1].sk === gk) {
            var fStart = i - 1;
            while (fStart > 0 && _gk(arr[fStart-1].sk) === gk) fStart--;
            var fLen = i - fStart + 1;
            if (fLen > famCap) {
              var fSwapped = false;
              for (var j = i + 1; j < Math.min(i + 20, n); j++) {
                if (_gk(arr[j].sk) !== gk) {
                  var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                  fSwapped = true; improved = true; break;
                }
              }
              if (!fSwapped) {
                for (var j = i - 1; j >= 0; j--) {
                  if (_gk(arr[j].sk) !== gk) {
                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                    improved = true; break;
                  }
                }
              }
            }
          }
        }
      }
      if (!improved) break;
    }
  }
```

- [ ] **Step 3: 更新所有 `_applyRunCap` 调用点传入 `SOURCE_FAMILIES`**

搜索所有 `_applyRunCap(ART,` 调用（约 3 处），将：
```javascript
_applyRunCap(ART, 3);
```
改为：
```javascript
_applyRunCap(ART, 3, SOURCE_FAMILIES);
```

同样将 `_applyRunCap(ART, 5);`（quality 模式）改为：
```javascript
_applyRunCap(ART, 5, SOURCE_FAMILIES);
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python tests/rss_composite/test_diverse_js.py`
Expected: PASS（F1-F6 全绿，D18/D24/D25 仍绿）

- [ ] **Step 5: 运行全量回归**

```bash
python tests/rss_composite/test_diverse_js.py
python tests/rss_composite/test_diverse_realdata.py
python tests/rss_composite/test_run_cap.py
python tests/rss_composite/regression_composite.py
```

Expected: 全绿

- [ ] **Step 6: Commit GREEN**

```bash
git add build_rss_aggregator.py tests/rss_composite/cases_diverse.js
git commit -m "feat(sort): family-aware _applyRunCap for V2EX/NodeSeek dedup

- Add SOURCE_FAMILIES mapping (v2ex → 4 sub-sources, nodeseek)
- Add FAMILY_CAPS (v2ex: 6, nodeseek: 4)
- _applyRunCap now checks both source-level and family-level runs
- Backward compatible: third param defaults to empty object"
```

---

### Task 5: 变异测试更新 + 全量回归

**Files:**
- Modify: `tests/rss_composite/mutation_check.py`

- [ ] **Step 1: 新增变异体**

在 `mutation_check.py` 的 `MUTATIONS` 列表末尾追加：

```python
    # ── DU：同日期伪造检测（Phase 3）────────────────────────────────────
    ("DU-a 同日期检测阈值被放宽到 100%（80% 源漏检）",
     [("        if ratio >= threshold:",
       "        if ratio >= 1.0001:")],
     "tests/rss_composite/test_date_uniform.py",
     ["DU-7"], "[FAIL] "),

    # ── FC：族群配额（Phase 3）──────────────────────────────────────────
    ("FC-a SOURCE_FAMILIES 为空对象（族群 cap 失效）",
     [("  var SOURCE_FAMILIES = {\n    'v2ex_all_50': 'v2ex',",
       "  var SOURCE_FAMILIES = {\n    /* removed */")],
     JS_DIVERSE, ["F1"], "FAIL "),

    ("FC-b _applyRunCap 不接收 families 参数",
     [("  function _applyRunCap(arr, cap, families) {",
       "  function _applyRunCap(arr, cap) {")],
     JS_DIVERSE, ["F2"], "FAIL "),
```

- [ ] **Step 2: 运行变异测试**

Run: `python tests/rss_composite/mutation_check.py`
Expected: 全部 CAUGHT（包括新增的 DU-a, FC-a, FC-b）

- [ ] **Step 3: 全量回归**

```bash
python tests/rss_composite/mutation_check.py
python tests/rss_composite/regression_composite.py
python tests/rss_composite/test_diverse_js.py
python tests/rss_composite/test_diverse_realdata.py
python tests/rss_composite/test_run_cap.py
python tests/rss_composite/test_score_sources_default.py
python tests/rss_composite/test_date_uniform.py
```

Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add tests/rss_composite/mutation_check.py
git commit -m "test(mutation): add 3 new mutation targets for date-uniform + family cap"
```

---

### Task 6: 构建验证 + 线上分析

- [ ] **Step 1: 本地构建**

```bash
python build_rss_aggregator.py
```

Expected: 输出含 `[bad_date-C] 同日期伪造源 N 个: 知乎日报anyfeeder, ...`

- [ ] **Step 2: 验证分析脚本**

Run: `python .deploy-tmp/_sort_quality_analysis.py`
Expected:
- 知乎日报在前 50 位占比从 34% 降至 ≤ 4%
- 前 200 位覆盖源数 ≥ 30

- [ ] **Step 3: 触发 GitHub Actions 构建**

```bash
git push
gh workflow run update.yml
gh run watch
```

- [ ] **Step 4: 线上验证**

构建成功后，重新拉取 rss-data 文件，运行分析脚本验证线上指标达标。

---

## 完成后：对抗性审查

全部实施完毕后，按 `requesting-code-review` 技能模板执行红队验证：

**审查重点：**
1. `_detect_uniform_dates` 是否误伤正常源（如 arXiv 日级粒度）
2. `_applyRunCap` 的 family-aware 升级是否破坏现有单源 cap 不变量
3. `SOURCE_FAMILIES` 注入是否影响首屏加载体积
4. 族群 cap 的交换逻辑是否可能制造新的单源 cap 违例
5. 向后兼容性：`_applyRunCap(arr, cap)` 不传 families 时行为不变

**输出格式：** 按 Critical / Important / Minor 分级，写入 `docs/superpowers/reviews/2026-09-15-sort-quality-v3-review.md`

---

## 不变量守卫清单（任何改动后必须为真）

| # | 不变量 | 验证方式 |
|---|--------|---------|
| 1 | 条目守恒：ART.length 不变 | D10, E2, RC-3, RC-6, F6 |
| 2 | 集合守恒：sk 多重集一致 | E2b, RC-6, F6b |
| 3 | 确定性：同输入同输出 | D8 |
| 4 | 单源 maxRun ≤ 3（newest/active） | D18, D24 |
| 5 | 单源 maxRun ≤ 5（quality） | D25 |
| 6 | 族群 maxRun ≤ FAMILY_CAPS[fam] | F2, F5 |
| 7 | _applyRunCap 向后兼容（2 参数） | F4 |
| 8 | 同日期源被标记 bad_date | DU-1, DU-5, DU-7 |
| 9 | 不同日期源不被误标记 | DU-2, DU-3 |
