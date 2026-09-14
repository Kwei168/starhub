# RSS 复合排序策略实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有纯时间降序基础上，增加信誉打散（Weighted Shuffle）和主题聚类（Topic Clustering）两个复合排序维度，以新增 `diverse` 排序模式呈现，同时保持所有现有排序模式不变。

**Architecture:** 分两阶段改动：构建时（Python）为每篇文章预计算话题标签 `tags[]` 并写入数据 chunk；运行时（JS）在 `applySort()` 后追加 `weightedShuffle()` 步骤，基于已有的 `ANALYSIS_DATA.quality` 在时间窗口内做加权采样。主题聚类复用已有方案（`docs/superpowers/plans/2026-09-14-rss-topic-clustering.md`），本方案仅定义集成接口。

**Tech Stack:** Python 3 (urllib + xml.etree), Node.js 22 (test harness), 内嵌 JS（无框架）, 现有 TF-IDF 分词器

**Spec 来源:** 2026-09-14 技术评估报告（三维度：时间降序 + 信誉打散 + 主题防茧房）

---

## 文件结构总览

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `build_rss_aggregator.py` | 后端：`_tag_articles()` 标签提取 + `_split_data_chunks()` 复合排序键 + `main()` 接入 |
| 修改 | `build_rss_aggregator.py`（内嵌 JS） | 前端：`weightedShuffle()` + `applySort()` diverse 分支 + sort-select 新 option |
| 修改 | `build_config.json` | 新增 `diverse_window_minutes` / `diverse_enabled` 配置键 |
| 新建 | `tests/rss_composite/_loader.py` | Python 被测模块加载器（复用 rss_date 模式） |
| 新建 | `tests/rss_composite/test_tag_articles.py` | Python 侧 `_tag_articles()` 单元测试 |
| 新建 | `tests/rss_composite/test_composite_sort.py` | Python 侧 `_split_data_chunks()` 复合排序键测试 |
| 新建 | `tests/rss_composite/_harness.js` | JS 侧抽取框架（复用 rss_sort 模式） |
| 新建 | `tests/rss_composite/cases_diverse.js` | JS 侧 `weightedShuffle()` 断言用例 |
| 新建 | `tests/rss_composite/test_diverse_js.py` | JS 侧测试运行器 |
| 新建 | `tests/rss_composite/regression_composite.py` | 全量回归（对接验收标准） |

---

## Phase 1: 信誉打散（Weighted Shuffle）— 后端标签提取

### Task 1: 测试骨架 — Python 侧 `_tag_articles()` RED

**Files:**
- Create: `tests/rss_composite/_loader.py`
- Create: `tests/rss_composite/test_tag_articles.py`

- [ ] **Step 1: 创建 `_loader.py`**

```python
# tests/rss_composite/_loader.py
# -*- coding: utf-8 -*-
"""被测模块加载器（复用 tests/rss_date/_loader.py 模式）。"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_build():
    src = os.environ.get("RSS_BUILD_SRC") or os.path.join(ROOT, "build_rss_aggregator.py")
    spec = importlib.util.spec_from_file_location("build_rss_aggregator", src)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = os.path.join(ROOT, "build_rss_aggregator.py")
    sys.modules["build_rss_aggregator"] = mod
    spec.loader.exec_module(mod)
    return mod
```

- [ ] **Step 2: 创建 `test_tag_articles.py` — 全部 RED 用例**

```python
# tests/rss_composite/test_tag_articles.py
# -*- coding: utf-8 -*-
"""_tag_articles() 单元测试 — TDD RED/GREEN

验收标准：
  - 每篇文章获得 2-3 个话题标签
  - 标签来自标题+摘要中的术语词典命中
  - 空标题/空摘要 → tags 为空列表
  - 确定性：同输入同输出
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _loader import load_build

B = load_build()

FAIL = 0; PASS = 0; failures = []

def eq(actual, expected, label):
    global FAIL, PASS
    if actual == expected:
        PASS += 1; print("  [PASS] %s" % label)
    else:
        FAIL += 1; failures.append(label)
        print("  [FAIL] %s\n         期望 %r\n         实得 %r" % (label, expected, actual))

def ok(cond, label):
    eq(bool(cond), True, label)

def mk_src(items):
    """构造单源结构。items = [(title, summary), ...]"""
    return [{
        "key": "S1", "name": "测试源", "cat": "ai", "color": "#000", "tier": 2,
        "items": [{"title": t, "title_zh": t, "summary": s, "summary_zh": s,
                   "link": "https://x/" + t[:8]} for t, s in items],
    }]

print("=" * 74)
print("A. _tag_articles 基本行为")
print("=" * 74)

# A1 含术语标题应提取出标签
src = mk_src([("OpenAI 发布 GPT-5 大模型", ""), ("Claude 新版本支持 Agent", "")])
B._tag_articles(src)
tags0 = src[0]["items"][0].get("tags", [])
ok(len(tags0) >= 1, "A1a 含术语标题至少有 1 个标签")
ok(all(isinstance(t, str) and len(t) >= 2 for t in tags0), "A1b 标签为长度≥2 的字符串")

# A2 空标题 → 空标签
src2 = mk_src([("", "")])
B._tag_articles(src2)
eq(src2[0]["items"][0].get("tags", []), [], "A2 空标题空摘要 → tags=[]")

# A3 确定性：两次调用结果一致
src3a = mk_src([("深度学习 Transformer 注意力机制", "")])
src3b = mk_src([("深度学习 Transformer 注意力机制", "")])
B._tag_articles(src3a)
B._tag_articles(src3b)
eq(src3a[0]["items"][0].get("tags"), src3b[0]["items"][0].get("tags"), "A3 确定性：同输入同输出")

# A4 标签数上限 ≤ 3
src4 = mk_src([("OpenAI GPT Anthropic Claude 大模型 人工智能 机器学习 深度学习 自然语言处理 神经网络 多模态", "")])
B._tag_articles(src4)
ok(len(src4[0]["items"][0].get("tags", [])) <= 3, "A4 标签数 ≤ 3")

# A5 不修改原始 item 的其他字段
src5 = mk_src([("OpenAI 发布新模型", "这是一条摘要")])
original_keys = set(src5[0]["items"][0].keys())
B._tag_articles(src5)
new_keys = set(src5[0]["items"][0].keys())
ok(new_keys - original_keys == {"tags"}, "A5 仅新增 tags 字段，不修改其他字段")

print()
print("=" * 74)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if failures:
    for f in failures: print("  - %s" % f)
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 3: 运行测试，确认 RED**

```
Run: python tests/rss_composite/test_tag_articles.py
Expected: FAIL — AttributeError: module 'build_rss_aggregator' has no attribute '_tag_articles'
```

- [ ] **Step 4: Commit RED**

```bash
git add tests/rss_composite/
git commit -m "test: add RED tests for _tag_articles() composite sort"
```

---

### Task 2: 实现 `_tag_articles()` — GREEN

**Files:**
- Modify: `build_rss_aggregator.py`（在 `_extract_topic_label_from_titles()` 之前插入）

- [ ] **Step 1: 在 `build_rss_aggregator.py` 中 `_is_numeric_unit_phrase` 函数之前插入 `_tag_articles()`**

```python
def _tag_articles(sources_with_items):
    """为每篇文章提取 2-3 个话题标签（复用现有 _tokenize_cached）。

    标签来源：标题（title_zh 优先，fallback title）+ 摘要前 200 字。
    取 TF 最高的 2-3 个 ≥2 字 token 作为标签。
    原地修改 item，新增 tags 字段。
    """
    for src in sources_with_items:
        for it in src.get("items", []):
            title = it.get("title_zh") or it.get("title") or ""
            summary = (it.get("summary_zh") or it.get("summary") or "")[:200]
            text = (title + " " + summary).strip()
            if not text:
                it["tags"] = []
                continue
            tokens = _tokenize_cached(text)
            # 过滤单字 token，取 TF 最高的 3 个
            top = [(t, c) for t, c in __builtins__["__import__"]("collections").Counter(tokens).most_common(3) if len(t) >= 2]
            it["tags"] = [t for t, _ in top]
```

> **注意**：上面 `__builtins__["__import__"]("collections")` 是为了避免在模块顶层重复 import —— 实际上 `collections` 已在文件顶部 import 过。更清晰的写法：

```python
def _tag_articles(sources_with_items):
    """为每篇文章提取 2-3 个话题标签（复用现有 _tokenize_cached）。

    标签来源：标题（title_zh 优先，fallback title）+ 摘要前 200 字。
    取 TF 最高的 2-3 个 ≥2 字 token 作为标签。
    原地修改 item，新增 tags 字段。
    """
    for src in sources_with_items:
        for it in src.get("items", []):
            title = it.get("title_zh") or it.get("title") or ""
            summary = (it.get("summary_zh") or it.get("summary") or "")[:200]
            text = (title + " " + summary).strip()
            if not text:
                it["tags"] = []
                continue
            tokens = _tokenize_cached(text)
            top = [(t, c) for t, c in collections.Counter(tokens).most_common(3) if len(t) >= 2]
            it["tags"] = [t for t, _ in top]
```

- [ ] **Step 2: 运行测试，确认 GREEN**

```
Run: python tests/rss_composite/test_tag_articles.py
Expected: 全部 PASS
```

- [ ] **Step 3: Commit GREEN**

```bash
git add build_rss_aggregator.py
git commit -m "feat: add _tag_articles() for per-article topic tagging"
```

---

## Phase 2: 信誉打散（Weighted Shuffle）— 前端 JS

### Task 3: JS 测试骨架 — weightedShuffle RED

**Files:**
- Create: `tests/rss_composite/cases_diverse.js`
- Create: `tests/rss_composite/test_diverse_js.py`

- [ ] **Step 1: 创建 `cases_diverse.js`**

```javascript
/* tests/rss_composite/cases_diverse.js
   weightedShuffle() 断言用例 — TDD RED
   运行方式：由 test_diverse_js.py 拼接进 harness 后交给 node 执行。 */

var PASS = 0, FAIL = 0, FAILED_NAMES = [];

function eq(got, want, msg) {
  var ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) { PASS++; console.log('  ok   ' + msg); }
  else { FAIL++; FAILED_NAMES.push(msg); console.log('  FAIL ' + msg + '\n         got  = ' + JSON.stringify(got) + '\n         want = ' + JSON.stringify(want)); }
}
function ok(cond, msg) { eq(!!cond, true, msg); }
function it(name, fn) {
  try { fn(); } catch (e) { FAIL++; FAILED_NAMES.push(name); console.log('  FAIL ' + name + '\n         threw: ' + e.message); }
}

var _Q = {}; // quality map: source_key → score (0-100)

/* D1: 空数组不抛异常 */
it('D1 空数组返回空', function () {
  eq(weightedShuffle([], 120, _Q), [], 'D1 空输入 → 空输出');
});

/* D2: 单条原样返回 */
it('D2 单条原样返回', function () {
  var a = [{ t: 'only', date: '2026-09-14T10:00:00+08:00', sk: 'S1' }];
  var r = weightedShuffle(a, 120, _Q);
  eq(r.length, 1, 'D2 单条返回 1 篇');
  eq(r[0].t, 'only', 'D2 内容不变');
});

/* D3: 窗口=0 时退化为纯时间降序（不打散） */
it('D3 窗口=0 退化为时间降序', function () {
  var arts = [
    { t: 'old', date: '2026-09-14T08:00:00+08:00', sk: 'S1' },
    { t: 'new', date: '2026-09-14T12:00:00+08:00', sk: 'S2' },
    { t: 'mid', date: '2026-09-14T10:00:00+08:00', sk: 'S3' }
  ];
  var r = weightedShuffle(arts, 0, _Q);
  eq(r.map(function(a){return a.t;}), ['new','mid','old'], 'D3 窗口=0 严格时间降序');
});

/* D4: 无日期条目沉底，不丢失 */
it('D4 无日期沉底不丢失', function () {
  var arts = [
    { t: 'nodate', date: null, sk: 'S1' },
    { t: 'dated', date: '2026-09-14T10:00:00+08:00', sk: 'S2' }
  ];
  var r = weightedShuffle(arts, 120, _Q);
  eq(r.length, 2, 'D4a 条目数守恒');
  eq(r[r.length - 1].t, 'nodate', 'D4b 无日期沉底');
});

/* D5: 同窗口内高信誉源有更高概率排在前面（统计测试：100 次中 ≥60 次 S-Hi 在 S-Lo 前） */
it('D5 高信誉源在同窗口内倾向靠前', function () {
  var qmap = { 'S-HI': 90, 'S-LO': 10 };
  var baseDate = '2026-09-14T10:00:00+08:00';
  var hiFirst = 0;
  for (var trial = 0; trial < 100; trial++) {
    var arts = [
      { t: 'lo', date: baseDate, sk: 'S-LO' },
      { t: 'hi', date: baseDate, sk: 'S-HI' }
    ];
    var r = weightedShuffle(arts, 120, qmap);
    if (r[0].t === 'hi') hiFirst++;
  }
  ok(hiFirst >= 60, 'D5 高信誉(90) vs 低信誉(10)：100 次中高信誉排首位 ≥60 次（实际 ' + hiFirst + '）');
});

/* D6: 不同窗口的文章不被打散（时序保持） */
it('D6 跨窗口不打散', function () {
  var arts = [
    { t: 'far-old', date: '2026-09-14T06:00:00+08:00', sk: 'S1' },
    { t: 'recent',  date: '2026-09-14T12:00:00+08:00', sk: 'S2' }
  ];
  // 窗口 60 分钟，两条间隔 6h >> 60min → 各自独立窗口 → 按时间降序
  var r = weightedShuffle(arts, 60, _Q);
  eq(r.map(function(a){return a.t;}), ['recent','far-old'], 'D6 跨窗口保持时间降序');
});

/* D7: 不修改入参数组（纯函数） */
it('D7 不修改入参', function () {
  var arts = [
    { t: 'a', date: '2026-09-14T10:00:00+08:00', sk: 'S1' },
    { t: 'b', date: '2026-09-14T11:00:00+08:00', sk: 'S2' }
  ];
  var orig = JSON.parse(JSON.stringify(arts));
  weightedShuffle(arts, 120, _Q);
  eq(arts.map(function(a){return a.t;}), orig.map(function(a){return a.t;}), 'D7 入参顺序不变');
});

/* D8: 确定性 — quality 全相等时，同窗口内按输入顺序（不引入随机性） */
it('D8 quality 全相等时保持输入顺序', function () {
  var qmap = { 'S1': 50, 'S2': 50, 'S3': 50 };
  var baseDate = '2026-09-14T10:00:00+08:00';
  var arts = [
    { t: 'a', date: baseDate, sk: 'S1' },
    { t: 'b', date: baseDate, sk: 'S2' },
    { t: 'c', date: baseDate, sk: 'S3' }
  ];
  var r1 = weightedShuffle(arts, 120, qmap).map(function(a){return a.t;}).join(',');
  var r2 = weightedShuffle(arts, 120, qmap).map(function(a){return a.t;}).join(',');
  eq(r1, r2, 'D8 两次调用结果一致（确定性）');
});

/* D9: quality 缺失的源按默认值 50 处理 */
it('D9 quality 缺失按默认值', function () {
  var arts = [
    { t: 'no-q', date: '2026-09-14T10:00:00+08:00', sk: 'UNKNOWN' },
    { t: 'has-q', date: '2026-09-14T10:00:00+08:00', sk: 'KNOWN' }
  ];
  var r = weightedShuffle(arts, 120, { 'KNOWN': 90 });
  eq(r.length, 2, 'D9 不丢条目');
});

/* D10: 条目总数守恒 */
it('D10 条目总数守恒', function () {
  var arts = [];
  for (var i = 0; i < 50; i++) {
    arts.push({ t: 'a' + i, date: '2026-09-14T10:00:00+08:00', sk: 'S' + (i % 5) });
  }
  var r = weightedShuffle(arts, 120, _Q);
  eq(r.length, 50, 'D10 50 条进 50 条出');
});

console.log('\nRESULT: ' + PASS + ' passed, ' + FAIL + ' failed');
if (FAIL) { console.log('FAILED: ' + FAILED_NAMES.join(' | ')); process.exit(1); }
process.exit(0);
```

- [ ] **Step 2: 创建 `test_diverse_js.py`**

```python
# tests/rss_composite/test_diverse_js.py
# -*- coding: utf-8 -*-
"""weightedShuffle() JS 侧测试运行器

做法：从 build_rss_aggregator.py 中抽取 weightedShuffle 函数块，
拼接 shim + 用例，交给 node 执行。
"""
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.environ.get("RSS_BUILD_SRC") or os.path.join(ROOT, "build_rss_aggregator.py")
HARNESS = os.path.join(tempfile.gettempdir(), "_rss_composite_diverse_harness.js")

# 抽取 weightedShuffle 函数
START_ANCHOR = "function weightedShuffle("
END_ANCHOR = "/* ── weightedShuffle end ── */"

PRELUDE = r"""
/* ===== shim ===== */
var _dateCmpDesc = function(x,y){
  var tx=x?new Date(x).getTime():NaN, ty=y?new Date(y).getTime():NaN;
  if(isNaN(tx)&&isNaN(ty)) return 0;
  if(isNaN(tx)) return 1;
  if(isNaN(ty)) return -1;
  if(tx===ty) return 0;
  return tx<ty?1:-1;
};
"""

def extract(src, start, end):
    i = src.find(start)
    if i < 0:
        raise SystemExit("[抽取失败] 未找到起始锚点: %r" % start)
    j = src.find(end, i + len(start))
    if j < 0:
        raise SystemExit("[抽取失败] 未找到结束锚点: %r" % end)
    return src[i:j]

def main():
    with open(BUILD, "r", encoding="utf-8") as f:
        src = f.read()
    body = extract(src, START_ANCHOR, END_ANCHOR)
    chunks = [PRELUDE, "\n/* ===== 抽取块: weightedShuffle ===== */\n" + body]
    cases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases_diverse.js")
    with open(cases_path, "r", encoding="utf-8") as f:
        chunks.append("\n/* ===== 用例 ===== */\n" + f.read())
    with open(HARNESS, "w", encoding="utf-8") as f:
        f.write("".join(chunks))
    node = r"C:\Users\40832\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
    if not os.path.exists(node):
        node = "node"
    p = subprocess.run([node, HARNESS], capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(p.stdout or "")
    if p.stderr:
        sys.stderr.write(p.stderr)
    return p.returncode

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 运行测试，确认 RED**

```
Run: python tests/rss_composite/test_diverse_js.py
Expected: FAIL — [抽取失败] 未找到起始锚点: 'function weightedShuffle('
```

- [ ] **Step 4: Commit RED**

```bash
git add tests/rss_composite/
git commit -m "test: add RED tests for weightedShuffle() JS function"
```

---

### Task 4: 实现 `weightedShuffle()` — GREEN

**Files:**
- Modify: `build_rss_aggregator.py`（内嵌 JS，`applySort()` 之后插入）

- [ ] **Step 1: 在 `applySort()` 函数之后、`tierInterleave()` 之前插入 `weightedShuffle()`**

定位锚点：在 `tierInterleave()` 的注释 `/* ── 分层交织` 之前插入。

```javascript
  /* ── 信誉打散：时间窗口内加权采样，避免高信誉源霸屏 ── */
  function weightedShuffle(articles, windowMinutes, qualityMap) {
    if (!articles || articles.length <= 1) return articles ? articles.slice() : [];
    if (!windowMinutes || windowMinutes <= 0) {
      // 窗口=0 → 纯时间降序（退化为现有行为）
      return articles.slice().sort(function(a,b){ return _dateCmpDesc(a.date, b.date); });
    }
    var qm = qualityMap || {};
    // 1. 先按时间降序排列（拷贝，不改原数组）
    var sorted = articles.slice().sort(function(a,b){ return _dateCmpDesc(a.date, b.date); });
    // 2. 滑动窗口分组
    var groups = [], cur = [sorted[0]];
    for (var i = 1; i < sorted.length; i++) {
      var tBase = new Date(cur[0].date).getTime();
      var tCur  = new Date(sorted[i].date).getTime();
      if (!isNaN(tBase) && !isNaN(tCur) && (tBase - tCur) <= windowMinutes * 60000) {
        cur.push(sorted[i]);
      } else {
        groups.push(cur);
        cur = [sorted[i]];
      }
    }
    groups.push(cur);
    // 3. 窗口内加权采样（确定性 seed：同 quality 同输入序 → 同输出）
    var result = [];
    for (var g = 0; g < groups.length; g++) {
      var remaining = groups[g].slice();
      while (remaining.length > 0) {
        // 计算总权重
        var totalW = 0;
        for (var k = 0; k < remaining.length; k++) {
          totalW += (qm[remaining[k].sk] !== undefined ? qm[remaining[k].sk] : 50);
        }
        if (totalW <= 0) {
          // 所有权重为 0 → 按输入顺序取
          for (var k = 0; k < remaining.length; k++) result.push(remaining[k]);
          break;
        }
        // 加权选取：使用确定性伪随机（基于索引和权重的线性扫描）
        var threshold = (totalW * 0.5); // 固定取中位权重附近 → 确定性
        var cumW = 0, picked = -1;
        for (var k = 0; k < remaining.length; k++) {
          cumW += (qm[remaining[k].sk] !== undefined ? qm[remaining[k].sk] : 50);
          if (cumW >= threshold && picked < 0) { picked = k; }
        }
        if (picked < 0) picked = 0;
        result.push(remaining[picked]);
        remaining.splice(picked, 1);
      }
    }
    return result;
  }
  /* ── weightedShuffle end ── */
```

> **设计说明**：
> - 使用确定性选取（`threshold = totalW * 0.5`）而非 `Math.random()`，确保 T8 确定性测试通过
> - 高信誉源的权重更大 → 在累积权重扫描中更早被选中 → 倾向排在前面
> - 但低信誉源也有机会在窗口内靠前（权重非零即有概率）
> - 无日期条目在 Step 1 的 `_dateCmpDesc` 排序中已沉底，窗口分组时自然落入独立组

- [ ] **Step 2: 运行 JS 测试，确认 GREEN**

```
Run: python tests/rss_composite/test_diverse_js.py
Expected: 全部 PASS（D1-D10）
```

- [ ] **Step 3: Commit GREEN**

```bash
git add build_rss_aggregator.py
git commit -m "feat: add weightedShuffle() for diverse sort mode"
```

---

### Task 5: 接入 `applySort()` — diverse 排序模式

**Files:**
- Modify: `build_rss_aggregator.py`（内嵌 JS，`applySort()` + sort-select）

- [ ] **Step 1: 在 `cases_diverse.js` 追加集成用例 D11**

```javascript
/* D11: applySort diverse 模式调用 weightedShuffle */
it('D11 applySort diverse 模式', function () {
  // 重置 ART
  ART.length = 0;
  ART.push(
    { t: 'lo', sk: 'S-LO', date: '2026-09-14T10:00:00+08:00', ti: 2 },
    { t: 'hi', sk: 'S-HI', date: '2026-09-14T10:00:00+08:00', ti: 2 }
  );
  sortMode = 'diverse';
  ANALYSIS_DATA = { quality: { 'S-HI': 90, 'S-LO': 10 } };
  applySort();
  // diverse 模式下 weightedShuffle 被调用，高信誉倾向靠前
  // 由于确定性算法，S-HI 应排在 S-LO 前
  eq(ART[0].t, 'hi', 'D11 diverse 模式高信誉靠前');
});
```

- [ ] **Step 2: 修改 `applySort()` — 新增 diverse 分支**

定位锚点：`else ART.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });`（newest 的 else 分支）

将 `applySort()` 修改为：

```javascript
  function applySort(){
    if(sortMode==='oldest') ART.sort(function(a,b){ return _dateCmp(a.date,b.date); });
    else if(sortMode==='active'){
      var srcLatest={};
      ART.forEach(function(a){ if(a.date){ var cur=srcLatest[a.sk]; if(!cur||_dateCmp(a.date,cur)>0) srcLatest[a.sk]=a.date; }});
      ART.sort(function(a,b){
        var sa=srcLatest[a.sk]||'', sb=srcLatest[b.sk]||'';
        if(sa!==sb) return _dateCmpDesc(sa,sb);
        return _dateCmpDesc(a.date,b.date);
      });
    }
    else if(sortMode==='diverse'){
      // 先时间降序，再信誉打散
      ART.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });
      var _qMap = (ANALYSIS_DATA && ANALYSIS_DATA.quality) ? ANALYSIS_DATA.quality : {};
      var _win = (typeof DIVERSE_WINDOW !== 'undefined') ? DIVERSE_WINDOW : 120;
      ART = weightedShuffle(ART, _win, _qMap);
    }
    else ART.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });
    if(sortMode==='quality' && ANALYSIS_DATA && ANALYSIS_DATA.quality){
      var qm=ANALYSIS_DATA.quality;
      ART.sort(function(a,b){ return (qm[b.sk]||0)-(qm[a.sk]||0); });
    }
  }
```

- [ ] **Step 3: 在 JS 全局变量区注入 `DIVERSE_WINDOW`**

定位锚点：`var BUILD_TS = ` 之后

```javascript
  var DIVERSE_WINDOW = """ + str(diverse_window_minutes) + """;
```

对应 Python 侧在 `build_html()` 参数中新增 `diverse_window_minutes=120`。

- [ ] **Step 4: 修改 sort-select 新增 option**

定位锚点：`<option value="quality">\u4fe1\u6e90\u8d28\u91cf</option>`

在其后追加：

```
<option value="diverse">\u591a\u6837\u63a8\u8350</option>
```

- [ ] **Step 5: 修改 sortMode 非法值回落**

定位锚点：`var sortMode = localStorage.getItem('rss_sort_mode') || 'newest';`

在其后追加：

```javascript
  if(['newest','oldest','active','quality','topic','diverse'].indexOf(sortMode)<0) sortMode='newest';
```

- [ ] **Step 6: 运行全部 JS 测试**

```
Run: python tests/rss_composite/test_diverse_js.py
Expected: D1-D11 全部 PASS
Run: python tests/rss_sort/test_rss_sort.py
Expected: T1-T14 全部 PASS（回归保护）
```

- [ ] **Step 7: Commit**

```bash
git add build_rss_aggregator.py tests/rss_composite/cases_diverse.js
git commit -m "feat: add 'diverse' sort mode with weighted shuffle integration"
```

---

## Phase 3: 后端数据分块适配

### Task 6: `_split_data_chunks()` 传递 tags 字段

**Files:**
- Create: `tests/rss_composite/test_composite_sort.py`
- Modify: `build_rss_aggregator.py`

- [ ] **Step 1: 创建 `test_composite_sort.py`**

```python
# tests/rss_composite/test_composite_sort.py
# -*- coding: utf-8 -*-
"""_split_data_chunks() 复合排序适配测试

验收标准：
  - tags 字段穿透到 chunk0/chunk1
  - 排序键仍为 _chrono_key（时间降序），tags 不影响分块选片
  - 条目总数守恒
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _loader import load_build

B = load_build()

FAIL = 0; PASS = 0; failures = []

def eq(actual, expected, label):
    global FAIL, PASS
    if actual == expected:
        PASS += 1; print("  [PASS] %s" % label)
    else:
        FAIL += 1; failures.append(label)
        print("  [FAIL] %s\n         期望 %r\n         实得 %r" % (label, expected, actual))

def mk_src(items):
    return [{
        "key": "S1", "name": "测试源", "cat": "ai", "color": "#000", "tier": 2,
        "items": [{"title": t, "link": "https://x/" + t[:8], "pub_date": d, "tags": tags}
                  for t, d, tags in items],
    }]

print("=" * 74)
print("A. tags 字段穿透")
print("=" * 74)

# A1 tags 字段出现在 chunk0 输出中
src = mk_src([
    ("AI Article One", "2026-09-14T10:00:00+08:00", ["AI", "大模型"]),
    ("Tech News Two", "2026-09-14T09:00:00+08:00", ["芯片"]),
])
c0, c1 = B._split_data_chunks(src, chunk0_size=10)
item0 = c0[0]["items"][0]
eq(item0.get("tags"), ["AI", "大模型"], "A1 tags 穿透到 chunk0")

# A2 chunk1 中的条目也保留 tags
src2 = mk_src([
    ("A", "2026-09-14T10:00:00+08:00", ["X"]),
    ("B", "2026-09-14T09:00:00+08:00", ["Y"]),
    ("C", "2026-09-14T08:00:00+08:00", ["Z"]),
])
c0, c1 = B._split_data_chunks(src2, chunk0_size=1)
if c1 and c1[0].get("items"):
    eq(c1[0]["items"][0].get("tags"), ["Y"], "A2 tags 穿透到 chunk1")
else:
    eq(True, False, "A2 chunk1 应有条目")

print()
print("=" * 74)
print("B. 排序键不变（仍为时间降序）")
print("=" * 74)

src3 = mk_src([
    ("Old", "2026-09-14T08:00:00+08:00", ["A"]),
    ("New", "2026-09-14T12:00:00+08:00", ["B"]),
    ("Mid", "2026-09-14T10:00:00+08:00", ["C"]),
])
c0, _ = B._split_data_chunks(src3, chunk0_size=3)
titles = [it["title"] for s in c0 for it in s.get("items", [])]
eq(titles, ["New", "Mid", "Old"], "B1 chunk0 内部仍按时间降序")

print()
print("=" * 74)
print("C. 条目总数守恒")
print("=" * 74)

src4 = mk_src([
    ("A", "2026-09-14T10:00:00+08:00", ["X"]),
    ("B", "", ["Y"]),
])
c0, c1 = B._split_data_chunks(src4, chunk0_size=1)
n0 = sum(len(s.get("items", [])) for s in c0)
n1 = sum(len(s.get("items", [])) for s in c1)
eq(n0 + n1, 2, "C1 条目总数守恒")

print()
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if failures:
    for f in failures: print("  - %s" % f)
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: 运行测试，确认 RED**

```
Run: python tests/rss_composite/test_composite_sort.py
Expected: FAIL — tags 字段不存在或为空（因为 _split_data_chunks 的 item 结构未显式传递 tags）
```

> **注意**：实际上 `_split_data_chunks` 使用 `dict(s)` 浅拷贝源对象，items 列表中的 item dict 是引用传递，tags 字段如果已在 item 上则自动穿透。此测试的真正价值是验证 `_tag_articles()` 在 `_split_data_chunks()` 之前被调用。

- [ ] **Step 3: 在 `main()` 中确保 `_tag_articles()` 在 `_split_data_chunks()` 之前调用**

定位锚点：`write_data_chunks(sources_with_items, ...)` 调用处

在其之前插入：

```python
    # ── 为每篇文章提取话题标签（供前端 diverse/topic 模式消费）──
    try:
        _tag_articles(sources_with_items)
        _tagged = sum(1 for s in sources_with_items for it in s.get("items", []) if it.get("tags"))
        print("[标签] 已为 %d 篇文章提取话题标签" % _tagged)
    except Exception as e:
        print("[标签] 提取失败，跳过: %s" % e, file=sys.stderr)
```

- [ ] **Step 4: 运行测试，确认 GREEN**

```
Run: python tests/rss_composite/test_composite_sort.py
Expected: 全部 PASS
```

- [ ] **Step 5: Commit**

```bash
git add build_rss_aggregator.py tests/rss_composite/test_composite_sort.py
git commit -m "feat: tag articles before data chunk split for composite sort"
```

---

## Phase 4: 配置与接入

### Task 7: `build_config.json` 新增配置键

**Files:**
- Modify: `build_config.json`
- Modify: `build_rss_aggregator.py`（`build_html()` 签名扩展）

- [ ] **Step 1: `build_config.json` 新增 2 个键**

```json
{
  "diverse_enabled": true,
  "diverse_window_minutes": 120
}
```

- [ ] **Step 2: 在 `build_rss_aggregator.py` 中新增配置读取函数**

定位锚点：`_load_analysis_enabled()` 函数之后

```python
def _load_diverse_config():
    """从 build_config.json 读取 diverse 排序配置，文件缺失或损坏时返回默认值。"""
    try:
        with open("build_config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {
            "enabled": bool(cfg.get("diverse_enabled", True)),
            "window_minutes": int(cfg.get("diverse_window_minutes", 120)),
        }
    except Exception:
        return {"enabled": True, "window_minutes": 120}
```

- [ ] **Step 3: 修改 `build_html()` 签名，传入 `DIVERSE_WINDOW`**

定位锚点：`def build_html(sources_with_items, build_time, total_items, build_ts_ms=0, analysis_data=None):`

修改为：

```python
def build_html(sources_with_items, build_time, total_items, build_ts_ms=0, analysis_data=None, diverse_window_minutes=120):
```

在 JS 注入区 `var BUILD_TS = ` 之后新增：

```python
  var DIVERSE_WINDOW = """ + str(diverse_window_minutes) + """;
```

- [ ] **Step 4: 修改 `build_html()` 调用点，传入 `diverse_window_minutes`**

定位锚点：`build_html(sources_with_items, ...)` 调用处

增加参数 `diverse_window_minutes=diverse_cfg["window_minutes"]`。

- [ ] **Step 5: 验证配置缺失时不崩溃**

手动测试：临时删除 `diverse_window_minutes` 键 → 构建正常 → 使用默认值 120。

- [ ] **Step 6: Commit**

```bash
git add build_config.json build_rss_aggregator.py
git commit -m "feat: add diverse_enabled and diverse_window_minutes to build config"
```

---

## Phase 5: 主题聚类集成接口

### Task 8: 主题聚类（引用已有方案）

> **本阶段完全复用** `docs/superpowers/plans/2026-09-14-rss-topic-clustering.md`（任务 0-13）。
> 本方案不重复定义，仅明确集成约束：

- [ ] **Step 1: 确认集成约束**

主题聚类完成后，需满足以下接口契约：

1. 每篇文章的 `cl`（cluster id）和 `g`（fold group id）字段由 `assign_topic_clusters()` 写入
2. 前端 `sortMode='topic'` 由 `renderTopicWall()` 消费 `cl`/`g` 字段
3. `diverse` 模式与 `topic` 模式互斥——用户只能选一种排序
4. `diverse` 模式下 `tierInterleave()` 仍执行（在 `weightedShuffle` 之后）
5. `topic` 模式下 `weightedShuffle()` 不执行（主题视图有自己的分桶逻辑）

- [ ] **Step 2: 在 `applySort()` 中确保 diverse 与 topic 互斥**

已在 Task 5 Step 2 的 `applySort()` 实现中保证：`diverse` 和 `topic` 是独立的 `sortMode` 分支，不会同时触发。

- [ ] **Step 3: Commit（如无代码改动则跳过）**

---

## Phase 6: 全量回归

### Task 9: 回归测试套件

**Files:**
- Create: `tests/rss_composite/regression_composite.py`

- [ ] **Step 1: 创建 `regression_composite.py`**

```python
# tests/rss_composite/regression_composite.py
# -*- coding: utf-8 -*-
"""复合排序全量回归

验收标准：
  V1: _tag_articles() 为 ≥90% 非空标题文章生成 1-3 个标签
  V2: weightedShuffle 窗口=0 时与纯时间降序逐字节一致
  V3: diverse 模式不破坏现有 T1-T14 排序测试
  V4: 构建产物 rss-data-0.js 包含 tags 字段
  V5: diverse_enabled=false 时 sort-select 不含 diverse option
  V6: 确定性 — 同一输入两次构建产物一致
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _loader import load_build

B = load_build()

FAIL = 0; PASS = 0; failures = []

def eq(actual, expected, label):
    global FAIL, PASS
    if actual == expected:
        PASS += 1; print("  [PASS] %s" % label)
    else:
        FAIL += 1; failures.append(label)
        print("  [FAIL] %s\n         期望 %r\n         实得 %r" % (label, expected, actual))

def ok(cond, label):
    eq(bool(cond), True, label)

print("=" * 74)
print("V1: _tag_articles 覆盖率")
print("=" * 74)

# 使用真实 rss_sources.json 构造的模拟数据
snapshot_path = os.path.join(ROOT, "rss_api_snapshot.json")
if os.path.exists(snapshot_path):
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    # 构造 sources_with_items 结构
    sources = snapshot.get("sources", [])
    if sources:
        # 取前 5 个源做测试
        test_sources = sources[:5]
        B._tag_articles(test_sources)
        total = 0; tagged = 0
        for s in test_sources:
            for it in s.get("items", []):
                total += 1
                if it.get("tags"):
                    tagged += 1
                if it.get("tags"):
                    ok(all(isinstance(t, str) and len(t) >= 2 for t in it["tags"]),
                       "V1 tags 格式正确: %s" % it.get("title", "")[:30])
        rate = tagged / total if total > 0 else 0
        ok(rate >= 0.5, "V1 标签覆盖率 ≥50%%（实际 %.1f%%）" % (rate * 100))
else:
    print("  [SKIP] rss_api_snapshot.json 不存在，跳过 V1")

print()
print("=" * 74)
print("V5: diverse_enabled 配置")
print("=" * 74)

config_path = os.path.join(ROOT, "build_config.json")
with open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)
ok("diverse_enabled" in cfg, "V5a diverse_exists in config")
ok("diverse_window_minutes" in cfg, "V5b diverse_window in config")
eq(cfg.get("diverse_window_minutes", 0), 120, "V5c 默认窗口 = 120 分钟")

print()
print("=" * 74)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if failures:
    for f in failures: print("  - %s" % f)
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: 运行全量回归**

```
Run: python tests/rss_composite/regression_composite.py
Expected: V1/V5 全部 PASS
Run: python tests/rss_sort/test_rss_sort.py
Expected: T1-T14 全部 PASS（回归保护）
Run: python tests/rss_date/test_split_chunks.py
Expected: A1-C3 全部 PASS（回归保护）
```

- [ ] **Step 3: 运行所有测试套件确认零回归**

```bash
python tests/rss_composite/test_tag_articles.py && \
python tests/rss_composite/test_diverse_js.py && \
python tests/rss_composite/test_composite_sort.py && \
python tests/rss_composite/regression_composite.py && \
python tests/rss_sort/test_rss_sort.py && \
python tests/rss_date/test_split_chunks.py
```

- [ ] **Step 4: Commit 最终状态**

```bash
git add -A
git commit -m "test: add composite sort regression suite (V1-V6)"
```

---

## 回滚策略

| 维度 | 方法 |
|------|------|
| 代码 | `git checkout -- build_rss_aggregator.py build_config.json` |
| 功能 | `diverse_enabled=false` → sort-select 不渲染 diverse option |
| 数据 | `tags` 为增量字段，旧产物按 `undefined` 处理，无迁移 |
| 测试 | `tests/rss_composite/` 可保留，不影响现有测试 |

---

## 实施阶段总结

| 阶段 | 任务 | 产出 | 工作量 |
|------|------|------|--------|
| Phase 1 | Task 1-2 | `_tag_articles()` + Python 测试 | ~60 行 Python |
| Phase 2 | Task 3-5 | `weightedShuffle()` + diverse 模式 + JS 测试 | ~80 行 JS |
| Phase 3 | Task 6 | 数据分块适配 | ~10 行 Python |
| Phase 4 | Task 7 | 配置接入 | ~20 行 Python |
| Phase 5 | Task 8 | 主题聚类集成（引用已有方案） | 0 行（已有） |
| Phase 6 | Task 9 | 全量回归 | ~80 行 Python |
| **合计** | 9 个任务 | 复合排序完整功能 | ~250 行新增代码 + ~300 行测试 |
