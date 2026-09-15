# 对抗性审查：「发现」长尾源筛选功能

**审查范围：** commit `8cbda3a` — feat: add discover filter for long-tail high-quality sources
**审查日期：** 2026-09-15

---

## 审查结论：**通过，无 Critical/Important 问题**

---

## 1. 逻辑正确性

### `_discoverKeys()` 函数
- `srcCnt[sk] <= 5`：统计 ART 中每个 source_key 的条目数，≤5 入选。✅ 正确
- `(qm[sk] || 0) >= 60`：缺失 quality 的源默认为 0，不入选。✅ 正确
- `for...in` 遍历 `srcCnt`（纯 `{}` 对象），无原型链污染风险。✅ 安全

### 筛选交互
- `filter.type === 'discover'` 与 `filterBm`（收藏）可叠加：显示已收藏的长尾文章。✅ 正确
- `filter.type === 'discover'` 与 `unreadOnly` 可叠加：显示未读的长尾文章。✅ 正确
- `globalSearch` 在 discover 模式下正常过滤。✅ 正确
- 从 discover 模式点击分类 chip：正确退出 discover，进入 cat 模式。✅ 正确

### 边界条件
| 场景 | 行为 | 评估 |
|---|---|---|
| ART 为空 | `_discoverKeys()` 返回 `{}`，chip 不渲染 | ✅ |
| ANALYSIS_DATA 缺失 | `qm = {}`，所有源 quality=0，无源入选 | ✅ |
| 所有源 >5 条 | `_discoverKeys()` 返回 `{}`，chip 不渲染 | ✅ |
| quality 值为字符串 "80" | `"80" >= 60` → true（JS 隐式转换） | ✅ 正确 |
| quality 值为 NaN | `NaN \|\| 0` → 0，不入选 | ✅ |
| quality 值为 null | `null \|\| 0` → 0，不入选 | ✅ |

---

## 2. 性能

- `_discoverKeys()` 在 `renderChips()` 和 `visibleArts()` 中各调用一次
- 每次调用遍历 ART（~12,000 条），共 ~24,000 次迭代
- **评估**：JavaScript 引擎处理 24K 次简单迭代 <1ms，**不构成性能问题**
- **建议**：当前规模无需缓存。若 ART 增长到 100K+，可考虑在 `buildArt()` 后缓存 `_discoverKeys` 结果

**严重性：P3（信息性）**

---

## 3. 安全

### XSS 攻击面
- chip 文本为硬编码 `\u{1f50d} \u53d1\u73b0`，无用户输入注入点。✅ 安全
- hash 路由：`p.view === 'discover'` 为字符串等值比较，无 eval/innerHTML 注入。✅ 安全
- `_discoverKeys()` 遍历的 `srcCnt` 键来自构建期数据，非用户可控。✅ 安全

### Hash 路由注入
- `restoreFromHash()` 使用 `decodeURIComponent` 解析，但 `p.view === 'discover'` 是精确匹配，不接受任意值。✅ 安全

---

## 4. CSS 兼容性

- `.chip.disc-chip` 使用 `border-style: dashed` 与实线边框的分类 chip 视觉区分。✅
- 暗色模式通过 `@media(prefers-color-scheme:dark)` 覆盖。✅
- cyan 色系 (#0891b2 / #22d3ee) 与品牌色 (#2563eb) 有明显区分。✅

---

## 5. 与现有机制兼容性

| 机制 | 兼容性 | 说明 |
|---|---|---|
| `weightedShuffle` | ✅ | discover 模式不调用 weightedShuffle，ART 保持构建期排序（时间降序） |
| `_applyRunCap` | ✅ | discover 模式不调用 runCap，长尾源不需要打散 |
| `tierInterleave` | ✅ | discover 模式下 `sortMode !== 'diverse'`，会走 tierInterleave。但长尾源通常 tier=3，本身就在交织的"低频"位 |
| OPML 导出 | ✅ | discover 不影响 SOURCES 数据 |
| 信源面板 | ✅ | discover 不影响 renderPanel |

---

## 6. 发现的问题

### P2 — `_discoverKeys()` 重复计算
- **位置**：`renderChips()` L2703 和 `visibleArts()` L2874 各调用一次
- **影响**：每次渲染 2x 计算开销（当前 <1ms，可忽略）
- **建议**：若未来优化，可在 `buildArt()` 后缓存 `window._discCache = _discoverKeys()`，在 `renderChips` / `visibleArts` 中直接读取

### P3 — discover 模式无独立排序
- **位置**：discover 模式使用 ART 的默认顺序（构建期时间降序）
- **影响**：长尾源的文章按时间降序展示，这是合理行为
- **建议**：无需改动。用户如需其他排序，可切换模式后再切回

### P3 — quality 阈值 60 为硬编码
- **位置**：`_discoverKeys()` 中 `(qm[sk]||0) >= 60`
- **影响**：阈值不可配置
- **建议**：当前 60 是合理默认值。若未来需要调整，可提取为常量 `DISCOVER_QUALITY_MIN`

---

## 7. 总结

| 级别 | 数量 | 详情 |
|---|---|---|
| Critical | 0 | — |
| Important | 0 | — |
| Minor (P2) | 1 | _discoverKeys 重复计算 |
| Info (P3) | 2 | 无独立排序；阈值硬编码 |

**评估：功能实现正确、安全、与现有机制兼容。可以合并。**
