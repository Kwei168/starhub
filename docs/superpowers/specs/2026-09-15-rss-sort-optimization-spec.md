# Spec：RSS 聚合页排序功能全面优化（Phase 2）

日期：2026-09-15
状态：待确认
上游证据：线上页面实测（11,890 条 / 539 源）+ 代码级分析 + 对抗性审查
影响文件：`build_rss_aggregator.py`（主要）、`rss-aggregator.html`（前端渲染）
关联 spec：`2026-09-14-rss-default-sort-fix.md`（Phase 1 已交付）
关联 plan：`2026-09-15-rss-sort-optimization.md`（实施计划）

---

## 1. 问题陈述

Phase 1 修复了默认排序反转缺陷后，用户反馈排序功能仍存在以下问题：

### 1.1 同源扎堆（active / newest 模式）

| 指标 | active 模式 | newest 模式 | diverse 模式 |
|------|------------|------------|-------------|
| 最大同源连续 | **24** | 13 | 0 |
| 前 60 条独立源数 | 1 | 3 | 18 |
| 前 60 条首屏时间跨度 | 2.5h | 1.8h | 11h |

active 模式首屏被单一信源完全垄断，用户体验接近"单源订阅"。

### 1.2 tier 权重机制失效

`_srcWeight()` 当前只返回 quality 分，完全忽略 tier 字段。T1 核心源（6 个）与 T3 长尾源（801 个）在 diverse 打散中获得同等权重。

### 1.3 diverse 模式被 tierInterleave 扰动

`tierInterleave()` 在 `applySort()` 之后执行，每 4 篇高频源穿插 1 篇低频源，部分抵消 weightedShuffle 的打散效果。

### 1.4 远程刷新路径存在性能与正确性问题

- `_mergeRemoteSources` 逐个 `unshift` 导致 O(n²) 复杂度
- 远程刷新路径缺少时区安全钳制，可能引入未来日期

### 1.5 quality 评分体系缺陷

- **50% 的源 quality=0**（505/1014），近半信源在排序/打散中被视为"最低质量"
- `reliability` 维度为二元 0/1，无鉴别力
- RAGAS 洞察质量评估结果被信源质量分覆盖，从未生效

### 1.6 前端渲染缺陷

- tags 字段穿透到前端但从未渲染
- 远程刷新后 `window.ART` 未同步，刷新后操作（收藏/隐藏）数据不一致

---

## 2. 根因分析（已证实）

| 编号 | 根因 | 证据 | 严重度 |
|------|------|------|--------|
| R1 | `_applyRunCap` 交换逻辑缺少 `arr[j].sk !== arr[j-1].sk` 守卫 | 代码审查 L2407-2440 | P0 |
| R2 | `_srcWeight()` 无 tier 乘子 | 代码审查 L2443-2445 | P1 |
| R3 | `tierInterleave()` 在 diverse 模式下仍执行 | 代码审查 L2522-2532 | P1 |
| R4 | `applySort()` diverse 分支冗余预排序 | 代码审查 L2381-2382 | P2 |
| R5 | `_mergeRemoteSources` 逐个 unshift | 代码审查 L3521-3556 | P1 |
| R6 | `_score_sources()` 对 72h 无数据源直接给 0 分 | 代码审查 L5372-5373 | P1 |
| R7 | `renderWall()` 不渲染 tags | 代码审查 L2808-2853 | P2 |
| R8 | 远程刷新路径缺时区钳制 | 代码审查 L3521-3556 | P1 |
| R9 | quality 模式独立 if 与 else-if 链不一致 | 代码审查 L2384-2405 | P2 |

---

## 3. 需求

### 3.1 功能需求

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR1 | active / newest 模式前 60 条同源连续 ≤ 3 | P0 |
| FR2 | diverse 模式前 60 条同源连续 = 0 | P1 |
| FR3 | T1 源在 diverse 打散中获得 1.5x 权重，T2 获得 1.2x | P1 |
| FR4 | diverse 模式跳过 tierInterleave | P1 |
| FR5 | quality=0 的源获得 tier 推断默认分（T1=60, T2=40, T3=25） | P1 |
| FR6 | 远程刷新路径时区安全（无未来日期） | P1 |
| FR7 | 前端渲染 tags（最多显示 3 个） | P2 |
| FR8 | 远程刷新后 `window.ART` 与 `ART` 同步 | P1 |

### 3.2 非功能需求

| 编号 | 需求 | 约束 |
|------|------|------|
| NFR1 | 排序性能 | 12,000 条 applySort < 50ms |
| NFR2 | 向后兼容 | 旧版 analysis_snapshot.json 仍可加载 |
| NFR3 | 测试覆盖 | 现有回归测试全绿 + 新增断言 |
| NFR4 | 变异测试 | 关键守卫变异全 CAUGHT |

---

## 4. 设计

### 4.1 同源抑制：共享 `_applyRunCap()` 函数

**设计意图：** 为 active / newest / quality 三种模式提供统一的轻量同源抑制机制，替代各自独立的 cap 逻辑。

**算法：** 贪心交换 — 扫描序列，发现同源连续 > cap 时，向后寻找不同源且满足位置守卫的条目交换。

**关键约束：**
- 交换目标必须满足 `arr[j].sk !== arr[i].sk`（不同源）
- 交换目标必须满足 `arr[j].sk !== arr[j-1].sk`（不制造新连出）
- 搜索窗口 15 条（O(n) 复杂度，非全量扫描）

**Cap 值：**

| 模式 | cap | 理由 |
|------|-----|------|
| active | 3 | 首屏多样性优先，实测 24→3 |
| newest | 3 | 同上 |
| quality | 5 | 质量模式允许适度聚集 |
| diverse | N/A | 由 weightedShuffle 内部 SRC_GAP=2 处理 |
| oldest | N/A | 纯时间序，不干预 |

### 4.2 tier 权重乘子

**设计意图：** 在 `_srcWeight()` 中叠加 tier 乘子，使 T1/T2 源在 diverse 打散中获得更高权重。

**公式：** `weight = quality_score * tier_multiplier`

| Tier | 乘子 | 效果 |
|------|------|------|
| T1 | 1.5 | 核心源权重提升 50% |
| T2 | 1.2 | 优质源权重提升 20% |
| T3 | 1.0 | 长尾源基准 |

**quality=0 处理：** 回落默认值 50，再乘 tier 乘子。T1 未评分源：50 * 1.5 = 75。

### 4.3 diverse 模式跳过 tierInterleave

**设计意图：** tierInterleave 的固定穿插模式与 weightedShuffle 的随机打散冲突，diverse 模式应完全跳过。

**实现：** 在 `tierInterleave()` 入口和 `applySort()` 调用处增加 `if (mode === 'diverse') return;`。

### 4.4 quality 评分优化（方案 A：tier 默认分）

**设计意图：** 从根源消除 0 分，使信源健康度总览和徽章显示正确分数。

**改动：** `_score_sources()` 对 72h 无数据源赋 tier 推断默认分：

```python
if n == 0:
    _tier = src.get('tier', 3)
    _default = {1: 60, 2: 40}.get(_tier, 25)
    result[sk] = {
        'score': _default,
        'metrics': {},
        'article_count': 0,
        'inferred': True,  # 标记推断分，后续有数据自动覆盖
    }
```

**默认分设计：**

| Tier | 默认分 | 区间 | 理由 |
|------|--------|------|------|
| T1 | 60 | 警告 | 核心源即使暂时无数据也应有基础分，但不过高 |
| T2 | 40 | 警告 | 优质源中等保底 |
| T3 | 25 | 异常 | 长尾源低保底，仍显著低于有数据的源 |

**与前端改动 #4 的协同：**
- Python 端赋默认分后，`analysis_snapshot.json` 中不再有 0 值
- 前端 `_srcWeight` 的 `qm[x.sk] > 0` 判断对所有源都为真
- 信源健康度总览和徽章自动显示正确分数

### 4.5 远程刷新路径优化

**unshift → concat：**

```javascript
// 改动前：逐个 unshift，O(n²)
for (var k = 0; k < added.length; k++) {
  var item = added[k];
  if (!seen.has(item.id)) { ART.unshift(item); seen.add(item.id); }
}

// 改动后：批量 concat + 去重，O(n)
var newBatch = added.filter(function(item) { return !seen.has(item.id); });
newBatch.forEach(function(item) { seen.add(item.id); });
ART = newBatch.concat(ART);
```

**时区钳制：** 在 `_mergeRemoteSources` 中对所有日期执行安全钳制（同 `buildArt` 逻辑）。

**`window.ART` 同步：** 刷新完成后 `window.ART = ART;`。

### 4.6 前端 tags 渲染

**设计意图：** 穿透的 tags 字段应在卡片中可见，帮助用户快速识别文章主题。

**实现：** 在 `renderWall()` 卡片模板中新增 tags 区域，最多显示 3 个，溢出显示 `+N`。

**样式：** 小圆角标签，背景色 `var(--tag-bg)`，文字色 `var(--tag-color)`，字号 12px。

---

## 5. 明确不在本轮范围

| 项 | 原因 |
|---|---|
| **_mergeChunk 全量重建** | 增量合并复杂度高，当前规模 <50ms，性能无感知 |
| **visibleArts 缓存** | 11,890 条 filter 约 1-2ms，无优化必要 |
| **RAGAS 评估结果接入** | 需改数据结构（嵌套 quality），影响前端 4 处消费点，列为下一轮 |
| **reliability 维度改造** | 需扩大历史窗口至 7 天，属架构级改动，列为长期 |
| **afItems 时区盲缺陷** | 属 AI 动态流独立面板，不在 RSS 排序范围 |
| **first_seen 兜底排序键** | 需与同源配额同时上线，属新功能 |

---

## 6. 验收标准

以 `/api/rss` 实取载荷（11,890 条 / 539 源）为固定输入，复刻 `buildArt()` → `applySort()`：

| 编号 | 断言 | 基线（修复前） | 目标 |
|------|------|---------------|------|
| A1 | active 模式前 60 条最大同源连续 | 24 | **≤ 3** |
| A2 | newest 模式前 60 条最大同源连续 | 13 | **≤ 3** |
| A3 | diverse 模式前 60 条最大同源连续 | 0 | **= 0** |
| A4 | diverse 模式前 60 条独立源数 | 18 | **≥ 18**（不退化） |
| A5 | T1 源在 diverse 模式前 120 条占比 | ~0.8% | **≥ 2%**（提升但不垄断） |
| A6 | quality=0 的源数 | 505 | **0** |
| A7 | 远程刷新后无未来日期 | 可能有 | **0** |
| A8 | 远程刷新后 window.ART 长度 | 可能不同步 | **= ART 长度** |
| A9 | tags 字段在卡片中可见 | 不可见 | **渲染** |
| A10 | 逆序对变化（diverse 模式） | — | **≤ 5%**（与纯 weightedShuffle 相比） |
| A11 | 所有现有测试通过 | — | **全绿** |
| A12 | 变异测试全 CAUGHT | — | **全 CAUGHT** |

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `_applyRunCap` 两源极端场景交换失败 | 极低 | 低 | 双重守卫 `arr[j].sk !== arr[j-1].sk`；539 源数据下概率趋零 |
| tier 默认分给已失效源过高分 | 低 | 低 | T1=60 落在"警告"区间；`inferred` 标记可追溯 |
| 移除 diverse 预排序后行为变化 | 低 | 低 | weightedShuffle 内部 L2455 已做相同排序 |
| quality=0 回落 50 使低质量源排名偏高 | 低 | 低 | 50 * 1.0 = 50 仍低于大多数有评分源 |
| 变异体锚点因改动漂移 | 中 | 中 | 每阶段结束时运行 mutation_check.py 验证 |

---

## 8. 非目标

- 不改变 diverse 模式的核心算法（weightedShuffle）
- 不改变 T1 跳过机制
- 不扩大 rss_history.json 历史窗口（72h → 7d）
- 不接入 RAGAS 评估结果
- 不修复 afItems 时区盲缺陷
- 不改构建期切块逻辑与 `.github/workflows`

---

## 9. 实施阶段

| 阶段 | 优先级 | 改动项 | 目标 |
|------|--------|--------|------|
| Phase 2.1 | P0 | #1 _applyRunCap 双重守卫 | 修复 active/newest 同源扎堆 |
| Phase 2.2 | P1 | #4 tier 乘子 + #4P 默认分 + #5 跳过 tierInterleave | 恢复 tier 权重 + 修复 quality=0 |
| Phase 2.3 | P1 | #7 concat + #8 quality cap + #12 时区钳制 | 性能 + 正确性 |
| Phase 2.4 | P2 | #9 tags 渲染 | 前端完善 |
| Phase 2.5 | P2 | #10 splice→swap（可选）+ #11 else-if 链 | 代码质量 |

详细实施计划见 `2026-09-15-rss-sort-optimization.md`。

---

## 10. 对抗性审查与修订记录

（待实施后补充）
