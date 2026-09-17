# 每日洞察系统 TDD 修复实施 Spec

> 日期: 2026-09-17
> 依赖: [问题分析文档](2026-09-17-daily-insight-problem-analysis.md)
> 状态: 待执行

---

## 关键约束

1. **insight_engine.py 零修改** — RSS 洞察面板完全不动
2. **向后兼容** — `daily-insight.json` 的 schema 不变（events/theme/deep_analysis 等字段保持）
3. **不推送构建** — 全部本地验证通过后再提交
4. **TDD** — 每个 Task 先写测试，再实现，最后验证

## 可复用资产

| 资产 | 来源 | 复用方式 |
|------|------|----------|
| `_embed_chunks()` | `build_daily_insight.py` L545 | 已有，直接用于语义聚类 |
| FAISS 索引 | `build_daily_insight.py` L617-662 | 已有，直接用于向量检索 |
| `_parse_json()` | `build_daily_insight.py` L1084 | 已有，增强鲁棒性 |
| `_MultiKeyLLM` | `build_daily_insight.py` L1015 | 已有，直接使用 |
| `_filter_noise()` | `build_daily_insight.py` | 已有，直接使用 |
| `_content_hash()` | `build_daily_insight.py` | 已有，直接使用 |
| `_atomic_write_text/json` | `build_daily_insight.py` | 已有，直接使用 |
| `_SYS_ANALYST_PROMPT` | `insight_engine.py` | 参考设计，不直接导入（避免耦合） |

## 新增逻辑清单

| 功能 | 替换/新增 | 解决问题 |
|------|----------|----------|
| 语义事件聚类 | 替换 Jaccard | A1 |
| 混合查询构建 | 替换硬编码查询 | A2 |
| 热榜热度加权 | 修复 signal.heat | A3 |
| COSTAR Phase 1 提示词 | 替换裸提示词 | B1, B2, B7 |
| COSTAR Phase 2 提示词 | 替换裸提示词 | B3, B4, B7 |
| Platform DNA | 新增 | B5 |
| 自审-修正环节 | 新增 | B6 |
| RAGAS 解析增强 | 增强 | C1 |
| Phase 2 降级标记 | 新增 | C2 |
| 报纸风格 CSS | 替换 SaaS 风格 | D1, D2 |

---

## Phase 1: 事件聚合层修复

### Task 1.1 — 语义事件聚类：测试

**文件**: `tests/daily_insight/test_semantic_clustering.py`
**解决问题**: A1

```
测试用例:
1. test_semantic_merge_semantic_similar — "GPT-6 发布" 和 "OpenAI 发布 GPT-6" 应合并（Jaccard 可能漏掉）
2. test_semantic_keep_distinct — "GPT-6 发布" 和 "苹果 WWDC" 不应合并
3. test_semantic_cluster_chain — A≈B, B≈C → {A,B,C} 同一簇
4. test_semantic_fallback_to_jaccard — 无 embedding 时降级为 Jaccard
5. test_semantic_empty_input — 空输入返回空列表
6. test_semantic_single_chunk — 单个 chunk 直接返回一个事件

验收标准: pytest tests/daily_insight/test_semantic_clustering.py 全部 PASS
```

### Task 1.2 — 语义事件聚类：实现

**文件**: `build_daily_insight.py` — 修改 `_assemble_events()`
**方法**:
- 复用 `_embed_chunks()` 对所有 chunk 的 title+text 做 embedding
- 用 FAISS 或 numpy 余弦相似度替代 Jaccard 做贪心合并
- 阈值: `SEMANTIC_CLUSTER_THRESHOLD = 0.75`（余弦相似度）
- 降级: embedding 失败时回退到 Jaccard
- 保持输出格式不变（`{id, label, items, source_types, category, best_score}`）

**验收**: Task 1.1 测试 PASS + 现有 `test_daily_insight.py` 测试 PASS

---

### Task 1.3 — 混合查询构建：测试

**文件**: `tests/daily_insight/test_query_builder.py`
**解决问题**: A2

```
测试用例:
1. test_query_includes_hot_titles — 热榜标题出现在查询中
2. test_query_includes_rss_keywords — RSS 关键词出现在查询中
3. test_query_includes_pseudo_queries — 已检索 chunk 生成伪查询
4. test_query_no_duplication — 查询无重复
5. test_query_fallback_when_no_sources — 无 AGI Hunt/AIHOT 时降级到热榜
6. test_query_max_limit — 查询总数不超过上限

验收标准: pytest tests/daily_insight/test_query_builder.py 全部 PASS
```

### Task 1.4 — 混合查询构建：实现

**文件**: `build_daily_insight.py` — 修改查询构建段（L2313-2323）
**方法**:
- 热榜标题 Top15（降量，避免过度偏向热榜）
- RSS 关键词 Top10（从 `known_categories.json` 或 RSS 高频词提取）
- 伪查询 Top10（从已检索 chunks 的 title 截取前 50 字符）
- 去重（content_hash 或简单字符串去重）
- 总数上限: 40

**验收**: Task 1.3 测试 PASS

---

### Task 1.5 — 热榜热度信号修复：测试 + 实现

**文件**: `tests/daily_insight/test_heat_signal.py` + `build_daily_insight.py`
**解决问题**: A3

```
测试用例:
1. test_heat_nonzero_with_hot_items — 包含热榜 items 的事件 heat > 0
2. test_heat_scales_with_platforms — 3 个平台 > 1 个平台
3. test_heat_t1_boost — Tier 1 平台（微博/知乎/B站）有额外加权
4. test_heat_zero_without_hot — 无热榜 items 时 heat = 0

实现:
- 修复 signal.heat 计算：不仅计算 hot_platforms 数量，还加权平台 Tier
- 公式: heat = sum(tier_weight[p] for p in hot_platforms)，Tier1=3, Tier2=2, Tier3=1
- 上限: min(10, heat)

验收标准: 测试 PASS + daily-insight.json 中 heat 不再全为 0
```

---

## Phase 2: LLM 提示词工程

### Task 2.1 — COSTAR Phase 1 提示词重写：测试

**文件**: `tests/daily_insight/test_prompt_structure.py`
**解决问题**: B1, B2, B7

```
测试用例:
1. test_system_prompt_has_costar — system prompt 包含 Context/Objective/Style/Tone/Audience/Response
2. test_system_prompt_has_writing_framework — 包含写法框架（【宏观主线】+【微观佐证】或类似结构）
3. test_system_prompt_has_fewshot_example — 包含至少一个完整的 JSON 示例
4. test_system_prompt_has_banned_phrases — 包含禁用词列表（"值得关注"/"未来可期"等）
5. test_phase1_prompt_has_date — user prompt 包含日期
6. test_phase1_prompt_has_event_count — user prompt 包含事件数量

验收标准: pytest tests/daily_insight/test_prompt_structure.py 全部 PASS
```

### Task 2.2 — COSTAR Phase 1 提示词重写：实现

**文件**: `build_daily_insight.py` — 重写 `_SYSTEM_PROMPT_P1` 和 `_llm_phase1()`
**方法**:

```python
_SYSTEM_PROMPT_P1 = """
(C) Context: 你是一位 AI 行业资深分析师，为科技媒体撰写每日深度报告。
你的读者是 AI 从业者和科技决策者，他们需要在 5 分钟内掌握今日 AI 领域最重要的动态。

(O) Objective: 为每个事件生成结构化摘要，并用一句话概括今日主线。
你的输出将直接展示在 AI 日报页面上，面向数万读者。

(S) Style: 报纸编辑风格——简洁、有力、信息密度高。
写法要求：
1. 第一句话定性（使用'主导'/'分化'/'拐点'/'加速'等判断词）
2. 用【宏观主线】+【微观佐证】结构串联
3. 每个论点必须引用素材中的具体事实和数据
4. 禁止平铺直叙罗列事件

(T) Tone: 事实驱动、数据具体、观点有据。禁止空泛描述。

(A) Audience: AI 从业者、科技媒体编辑、技术决策者。

(R) Response: 严格输出 JSON，格式如下：
{...}

## 正确示例
{
  "theme": "从 Agent 评估标准之争，到可观测性工具涌现，再到企业级审计需求爆发，判断 AI 工程化进入系统化阶段",
  "events": [{
    "event_num": 1,
    "label": "三大平台同步发布企业级 Agent 评估服务",
    "category": "ai-products",
    "summary": "OpenAI、Google、Anthropic 在同一天发布企业级 Agent 评估服务。OpenAI 的 Agent Analytics 支持 Trace 级别追踪，Google 的 AgentBench Enterprise 提供标准化评测集，Anthropic 的 Claude Observability 集成 OpenTelemetry。",
    "significance": "标志 Agent 从'能用'到'可观测'的拐点，企业级部署的核心障碍从功能转向可评估性。",
    "key_links": ["https://..."]
  }]
}

## 禁用表达
"值得关注"、"引发讨论"、"未来可期"、"拭目以待"、"不难预见"
每句话必须有信息增量，不允许空话。

所有陈述必须严格基于提供的素材。禁止使用你自己的知识补充。
如果素材中缺少某个关键数据，在 summary 中标注[信息不足]。
只输出严格 JSON，不要输出任何思考过程或解释。
"""
```

**验收**: Task 2.1 测试 PASS + 人工检查生成的 JSON 质量

---

### Task 2.3 — COSTAR Phase 2 提示词重写：测试

**文件**: `tests/daily_insight/test_prompt_structure.py`（追加）
**解决问题**: B3, B4, B7

```
测试用例:
1. test_p2_system_has_costar — Phase 2 system prompt 包含 COSTAR 六要素
2. test_p2_system_has_writing_framework — 包含时间线叙事 + 影响分层写法
3. test_p2_system_has_fewshot_example — 包含至少一个完整的深度解读 JSON 示例
4. test_p2_prompt_has_material — user prompt 包含素材
5. test_p2_prompt_has_phase1_summary — user prompt 包含 Phase 1 摘要
6. test_p2_prompt_has_history_hook — 有历史追踪时包含历史上下文

验收标准: 测试 PASS
```

### Task 2.4 — COSTAR Phase 2 提示词重写：实现

**文件**: `build_daily_insight.py` — 重写 `_SYSTEM_PROMPT_P2` 和 `_llm_phase2()`
**方法**: 类似 Task 2.2，加入时间线叙事写法 + 影响分层写法 + 完整 JSON 示例

**验收**: Task 2.3 测试 PASS

---

### Task 2.5 — Platform DNA 嵌入

**文件**: `tests/daily_insight/test_prompt_structure.py`（追加）+ `build_daily_insight.py`
**解决问题**: B5

```
测试用例:
1. test_platform_dna_in_prompt — system prompt 中包含至少 5 个平台的 DNA 描述
2. test_platform_dna_has_character — 每个 DNA 描述包含该平台的独特视角/性格

实现:
在 _SYSTEM_PROMPT_P1 或 _SYSTEM_PROMPT_P2 中嵌入：
## 核心信源 DNA
- 36氪: 产业视角，关注商业模式和融资
- 虎嗅: 商业评论，偏批判性分析
- 微博热搜: 舆论风向，反映公众情绪
- 知乎: 深度讨论，技术社区视角
- B站: 年轻用户视角，关注消费级应用
- Hacker News: 技术极客视角，关注底层创新
- Product Hunt: 产品视角，关注用户体验
- arXiv: 学术视角，关注方法论突破

验收标准: 测试 PASS
```

---

## Phase 3: 质量闭环

### Task 3.1 — RAGAS 解析增强：测试 + 实现

**文件**: `tests/daily_insight/test_ragas_parsing.py` + `build_daily_insight.py`
**解决问题**: C1

```
测试用例:
1. test_ragas_parse_valid_json — 正常 JSON 正确解析
2. test_ragas_parse_markdown_codeblock — ```json ... ``` 代码块正确提取
3. test_ragas_parse_embedded_json — 文本中嵌入的 JSON 正确提取
4. test_ragas_parse_malformed — 格式错误的 JSON 返回默认值而非崩溃
5. test_ragas_parse_missing_fields — 缺失字段使用默认值填充
6. test_ragas_parse_non_numeric_scores — 非数字 score 回退到 0.5

验收标准: 测试 PASS
```

### Task 3.2 — Phase 2 降级标记：测试 + 实现

**文件**: `tests/daily_insight/test_phase2_degradation.py` + `build_daily_insight.py`
**解决问题**: C2

```
测试用例:
1. test_phase2_success — 正常输出包含所有字段
2. test_phase2_parse_failure — 解析失败时 deep_analysis 包含降级标记
3. test_phase2_llm_failure — LLM 不可用时 deep_analysis 包含降级标记
4. test_phase2_degradation_has_reason — 降级标记包含失败原因

降级标记格式:
{
  "status": "degraded",
  "reason": "llm_parse_failed" | "llm_unavailable" | "timeout",
  "event_reconstruction": "",
  "impact_analysis": "",
  ...
}

验收标准: 测试 PASS + daily-insight.json 中 deep_analysis 不再为 null
```

---

### Task 3.3 — 自审-修正环节：测试 + 实现

**文件**: `tests/daily_insight/test_self_review.py` + `build_daily_insight.py`
**解决问题**: B6

```
测试用例:
1. test_self_review_detects_empty_summary — 空泛 summary 被标记
2. test_self_review_detects_missing_data — 缺少具体数据的 summary 被标记
3. test_self_review_correction_applied — 修正后的 summary 质量提升
4. test_self_review_skips_good_output — 高质量输出不被过度修改
5. test_self_review_max_iterations — 最多 1 次自审（避免无限循环）

实现:
在 Phase 1 之后、Phase 2 之前，增加一次 LLM 自审调用：
- 输入: Phase 1 输出 + 原始素材
- 检查维度: 数据具体性/空话检测/素材忠实度
- 输出: 修正后的 events（仅修改有问题的字段）
- 约束: 最多修改 30% 的字段，保留原始结构

验收标准: 测试 PASS
```

---

## Phase 4: 前端呈现

### Task 4.1 — 报纸风格 CSS 重写：测试 + 实现

**文件**: `tests/daily_insight/test_inject_css.py` + `build_daily_insight.py`
**解决问题**: D1, D2

```
测试用例:
1. test_no_border_radius — 子板块不使用 border-radius（报纸无圆角）
2. test_serif_display_font — 标题使用衬线字体（Georgia/serif）
3. test_double_rule_divider — 使用双线分隔（3px double）
4. test_paper_color_palette — 使用报纸色调（--bg/#faf8f4, --ink/#1f1c17）
5. test_no_emoji_icons — 不使用 emoji 作为图标
6. test_no_colored_badges — 不使用彩色状态徽章
7. test_dark_mode_support — 支持暗色模式（使用 CSS 变量）
8. test_inject_anchor_correct — 注入位置在 <footer> 之前

实现:
重写 _inject_into_ai_daily() 中的 CSS，对齐 ai-daily.html 的设计语言：
- 标题: font-family: var(--display)（Georgia 衬线）
- 分隔: border-top: 3px double var(--line-strong)
- 卡片: 无 border-radius，用 1px solid var(--line) 边框
- 色彩: 使用 ai-daily.html 的 CSS 变量（--bg, --card, --ink, --muted, --accent）
- 状态: 不用彩色徽章，用文字标签（如「新」「持续」）
- 深度解读: 不用 <details> 折叠，改为缩进式排版

验收标准: 测试 PASS + 人工检查 ai-daily.html 渲染效果
```

---

### Task 4.2 — 破茧栏：测试 + 实现

**文件**: `tests/daily_insight/test_echo_chamber_breaker.py` + `build_daily_insight.py`
**解决问题**: E1

```
测试用例:
1. test_read_profile_from_history — 从 daily_insight_history.json 过去 7 天统计用户常读 category
2. test_read_profile_empty_history — 无历史数据时返回空画像（不崩溃）
3. test_bubble_events_selected — 选取与常读 category 交集最小的事件
4. test_bubble_events_max_5 — 破茧栏最多 5 个事件
5. test_bubble_events_fallback — 全部事件都在常读分类内时，选取最低频分类的事件
6. test_bubble_in_json_output — daily-insight.json 中包含 bubble_breaker 字段
7. test_bubble_in_inject_html — AI 日报子板块中包含破茧栏 HTML

实现:
1. _build_read_profile(history) → {category: count} 从过去 7 天历史中统计
2. _select_bubble_events(clusters, read_profile, top_n=5):
   - 计算每个事件的 category 与 read_profile 的交集度
   - 选取交集最小的 top_n 个事件
   - 若全部事件都在常读分类内，选取最低频分类的事件
3. 输出字段: bubble_breaker: [{label, summary, category, reason}]
4. 在 _inject_into_ai_daily() 中增加破茧栏 HTML 段
5. 在 _write_insight_json() 中增加 bubble_breaker 字段

验收标准: 测试 PASS + daily-insight.json 包含 bubble_breaker 字段
```

---

## Phase 5: 集成验证

### Task 5.1 — 全管线集成测试

**文件**: `tests/daily_insight/test_integration.py`

```
测试用例:
1. test_full_pipeline_no_crash — 完整管线（mock LLM）不崩溃
2. test_output_schema_unchanged — 输出 JSON schema 与现有 schema 一致
3. test_events_have_heat — 事件 signal.heat 不再全为 0
4. test_deep_analysis_not_null — deep_analysis 不为 null（至少有降级标记）
5. test_inject_html_valid — 注入的 HTML 格式正确
6. test_rss_insight_untouched — insight_engine.py 未被修改（文件 hash 检查）
7. test_bubble_breaker_present — daily-insight.json 包含 bubble_breaker 字段

验收标准: pytest tests/daily_insight/ 全部 PASS
```

### Task 5.2 — 对抗性审查

**检查清单**:
- [ ] 事件聚合是否真正用语义相似度合并（而非仅靠 Jaccard 标题匹配）
- [ ] 热榜热度信号是否正确计算（不再全为 0）
- [ ] LLM 提示词是否符合 COSTAR 框架且有正确示例
- [ ] 注入 ai-daily.html 的子板块是否与报纸风格一致
- [ ] RSS 洞察面板功能未受影响（insight_engine.py 零修改）
- [ ] daily-insight.json schema 向后兼容
- [ ] 破茧栏是否从历史数据中统计常读分类并选取低交集事件
- [ ] 所有测试 PASS

---

## 执行顺序

```
Phase 1 (事件聚合)
  T1.1 → T1.2 → T1.3 → T1.4 → T1.5
  ↓
Phase 2 (提示词工程) — 可与 Phase 1 并行
  T2.1 → T2.2 → T2.3 → T2.4 → T2.5
  ↓
Phase 3 (质量闭环) — 依赖 Phase 2
  T3.1 → T3.2 → T3.3
  ↓
Phase 4 (前端 + 破茧栏) — 可与 Phase 2/3 并行
  T4.1 → T4.2
  ↓
Phase 5 (集成验证)
  T5.1 → T5.2
```

## 预估工作量

| Phase | Task 数 | 预估时间 |
|-------|---------|----------|
| Phase 1: 事件聚合 | 5 | ~2h |
| Phase 2: 提示词工程 | 5 | ~2h |
| Phase 3: 质量闭环 | 3 | ~1.5h |
| Phase 4: 前端 + 破茧栏 | 2 | ~1.5h |
| Phase 5: 集成验证 | 2 | ~1h |
| **合计** | **17** | **~8h** |
