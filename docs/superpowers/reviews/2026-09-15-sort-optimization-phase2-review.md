# 对抗性审查报告：RSS 排序优化 Phase 2

日期：2026-09-15
审查范围：983ce4e → 0c4b057（6 commits, 8 files, +648/-15 lines）
审查方法：按 `requesting-code-review` 技能模板执行
Spec: `docs/superpowers/specs/2026-09-15-rss-sort-optimization-spec.md`

---

### Strengths

1. **TDD 纪律严格**：每个功能都遵循 RED→GREEN→COMMIT 循环，测试先于实现。新增 4 个测试文件（cases_run_cap.js, test_run_cap.py, test_score_sources_default.py）共 36 个新断言，覆盖核心行为。

2. **变异测试覆盖率高**：16/16 变异体全部 CAUGHT（从 12/12 扩展到 16/16），证明新增守卫均有测试鉴别力。`mutation_check.py:107-164` 的锚点缺失检测机制（显式跳过而非静默半变异）是优秀的工程实践。

3. **_applyRunCap 算法设计合理**：多 pass 迭代（硬限 3 次）+ 早期终止（`if (!improved) break`）+ 向前/向后双向搜索回退。`build_rss_aggregator.py:2444-2475` 边界条件完备，无越界风险。

4. **else-if 链重构干净**：`build_rss_aggregator.py:2399-2409` 将 quality 从独立 if 改为 else-if 链的一部分，消除了分支穿透。ANALYSIS_DATA 缺失时正确降级到 newest 模式。

5. **远程刷新三处修复形成闭环**：concat 替换 unshift（O(n²)→O(n)）+ 日期钳制 + window.ART 同步。`build_rss_aggregator.py:3610-3616` 的引用同步逻辑正确。

6. **CSS 样式与主题系统集成**：`.ctag` 使用 `color:var(--brand)` + `color-mix(in srgb, var(--brand) 10%, transparent)`，dark mode 自动适配，无硬编码颜色。

---

### Issues

#### Critical (Must Fix)

无。

#### Important (Should Fix)

1. **`_applyRunCap` 注释声称 O(n) 但实际最坏 O(n²)**
   - File: `build_rss_aggregator.py:2441`
   - Issue: 注释写"O(n) 时间"，但向后搜索回退（L2464-2470）在内层循环中可扫描 O(n) 个元素，外层 3-pass × 内层 O(n) = O(n²) 最坏情况。
   - Why it matters: 注释给出错误的复杂度保证，误导后续维护者。
   - Fix: 将注释改为"O(n) 典型 / O(n²) 最坏（3-pass 有界）"。

2. **D24 夹具从 2 源改为 3 源——2 源场景无测试覆盖**
   - File: `tests/rss_composite/cases_diverse.js:480-493`
   - Issue: 原始 D24 用 2 源 50/50 夹具，因 _applyRunCap 无法解决 2 源场景而改为 3 源。2 源极端场景现在完全没有集成测试。
   - Why it matters: 虽然 539 源数据下 2 源场景概率极低，但这是算法已知限制的盲区，应有显式测试记录行为（即使断言的是"尽力而为"而非"达标"）。
   - Fix: 添加 D24-2src 测试，断言 maxRun 从 15 降低到 ≤10（不要求 ≤3，但验证算法确实有改善）。

#### Minor (Nice to Have)

1. **`_applyRunCap` 向后搜索可加注释说明为何不检查双重守卫**
   - File: `build_rss_aggregator.py:2463`
   - Issue: 注释"不检查双重守卫，2 源场景必需"是正确的，但缺少解释为什么这样做是安全的（因为多 pass 迭代会逐步消解新产生的相邻对）。
   - Fix: 补充注释："多 pass 迭代会逐步消解此处可能制造的新相邻对"。

2. **`TIER_MULT` 可加 `const` 或 `Object.freeze` 防止意外修改**
   - File: `build_rss_aggregator.py:2486`
   - Issue: `var TIER_MULT = { 1: 1.5, 2: 1.2 }` 是可变对象，后续代码可能意外修改。
   - Fix: 在 ES5 环境下无法用 const，但可加注释 `/* @const */` 表明意图。低优先级。

3. **`_score_sources` 的 `inferred: True` 字段在前端无消费**
   - File: `build_rss_aggregator.py:5443`
   - Issue: Python 端写入 `inferred: True` 标记，但前端 `renderWall` 和 `renderPanel` 均未读取该字段，用户无法区分"实测分"和"推断分"。
   - Fix: 可在信源健康度总览中用不同图标/颜色标记推断分。归入未来改进。

4. **远程日期钳制用 `new Date(Date.now()).toISOString()` 格式与原始日期格式不一致**
   - File: `build_rss_aggregator.py:3591`
   - Issue: 原始日期可能是 `2026-09-15T10:00:00+08:00`（带时区偏移），钳制后变为 UTC ISO 格式。虽然排序正确，但显示时可能因时区差异产生微小偏移。
   - Fix: 低优先级，当前行为可接受。若需改进，可用 `a.date` 的原始格式替换日期部分。

---

### Recommendations

1. **构建验证**：修改后应运行 `python build_rss_aggregator.py` 生成新的 `rss-aggregator.html`，确认无 Python→JS 嵌入错误。当前 CI 应在部署时自动完成此步骤。

2. **性能基准**：建议在 `applySort` 后添加 `performance.now()` 计时日志（仅 debug 模式），验证 NFR1（12,000 条 < 50ms）在实际数据上成立。

3. **tierInterleave 守卫的集成测试**：当前 tierInterleave 的 diverse 守卫只在合并/刷新路径生效，单元测试 harness 不可达。建议未来考虑在 `cases_refresh_tags.js` 中添加模拟合并流程的集成测试。

---

### Assessment

**Ready to merge: Yes**

**Reasoning:** 核心实现逻辑正确，测试覆盖充分（145 tests + 16/16 mutations），所有 Critical/High 问题均不存在。2 条 Important 级别问题（注释复杂度不准确、2 源场景测试缺失）不影响功能正确性，可后续修复。代码质量高，设计决策有据可查。
