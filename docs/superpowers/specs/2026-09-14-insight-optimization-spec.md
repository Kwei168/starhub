# 洞察模块优化 Spec（TDD）

- 日期：2026-09-14
- 状态：待实施
- 关联：今晚构建体系修复系列（并行抓取/翻译账本/chunk 守卫），本 spec 只覆盖**洞察模块**
- 实测基线（commit 03d869e 场，34766667931）：洞察阶段全程 **87 秒**；嵌入调用 14 次，其中 **10 次为单条调用**；每次构建对 72h 窗口内约 700 条文本**全量重嵌入**（95% 与上一场相同）；RAGAS 每场运行

## 1. 目标

1. 洞察阶段耗时 87s → **≤25s**（缓存热场）
2. SiliconFlow 嵌入 API 调用次数：14 次/场 → **≤4 次/场**（3 个大批次 + ≤1 次增量批）
3. 重分析（聚类/深度洞察/RAGAS）移出小时级构建，按可配置间隔运行，前端诚实标注新鲜度
4. rising/趋势计算对不可信日期源（bad_date，今晚实测 266 个）降权

## 2. 非目标

- 洞察算法本身的重写（聚类阈值/提示词调优另立 spec）
- 洞察→时间线点击联动（前端交互改动，另立 spec）
- embedding 模型更换（bge-m3 保持）

## 3. 现状与代码事实

```
run_analysis()（insight_engine.py:1516）
 ├─ extract_keywords_llm(rss/hot)          # LLM 关键词，2 组调用
 ├─ _get_embeddings(rss_texts)             # 批量 ✓（~140 条，1 次 API）
 ├─ _build_hierarchical_index(...)
 │    └─ _get_embeddings(child_texts)      # 批量 ✓（~160 条，1 次 API）
 ├─ cluster_topics_embedding(...)          # 批量 ✓（~140 条）
 ├─ cross_platform_semantic(hot_snapshot)
 │    └─ _get_embeddings(all_titles)       # 批量 ✓（~400 条，1 次 API）
 ├─ generate_deep_insights(...)
 │    └─ for cluster: _get_embeddings([query_text])   # ✗ 单条 ×≤15（每簇一次检索查询）
 ├─ RAGAS 评估
 │    └─ for cluster[:5]: _get_embeddings([query_text])  # ✗ 单条 ×≤5
 └─ _self_correct_insights(...)            # 低分时 LLM 修正
```

- `_get_embeddings(texts)`（:555）：SiliconFlow 批量 API → 本地 fastembed 兜底。**无缓存层**。
- 批大小 `_SF_BATCH=32`，实测 400 条一次通过（SiliconFlow 单请求上限宽松）。
- `run_analysis` 输入 `rss_history`（72h 窗口全量 dict）、输出 analysis dict → analysis_snapshot.json。
- 每场构建 `analysis_enabled=true` 时无条件全量运行（build_rss_aggregator.py `_run_analysis`）。
- 前端：洞察按钮 + 抽屉面板，消费 analysis_snapshot.json；无新鲜度标注。

## 4. 设计

### D1 嵌入缓存（第一档）

**数据结构**：新文件 `emb_cache.json`

```json
{ "model": "BAAI/bge-m3", "vectors": { "<md5(text)>": [1024 个 float], ... } }
```

**接口变更**：`_get_embeddings(texts)` 内部前置缓存层（签名不变，调用方零改动）：

```
未命中 texts → 调 API（仅未命中部分，保持批量）→ 写缓存
全命中 → 零 API 调用
返回顺序与输入严格一致（调用方按序消费向量）
```

- 键 = `hashlib.md5(text.encode("utf-8")).hexdigest()`（与翻译缓存同一惯例）
- 模型不匹配保护：缓存记录 model，加载时若 `_SF_EMBED_MODEL` 变化则整体失效重建
- 持久化：每场结束写一次（run_analysis 尾部），写入用原子写（tmp + replace，沿用仓库惯例）
- 容量：72h 窗口 ~2000 文本 × 1024 维 ≈ 8MB JSON，可接受；超 5000 条按最旧淘汰
- 失败语义：缓存文件损坏 → 忽略缓存全量重算（与 rss_cache 同惯例）

### D2 深度洞察/RAGAS 查询批化（第一档）

`generate_deep_insights` 与 RAGAS 上下文收集改为两阶段：

```
阶段一：for cluster → 收集 query_text 列表（不变：label + items[:2] + top_kw）
阶段二：一次 _get_embeddings(query_texts) → 按序分发做检索
```

消灭 ≤15 + ≤5 的单条调用，合并为 ≤2 次批量调用。

### D3 轻/重分析分级（第二档）

**config 新增**：`insight_heavy_interval_hours`（默认 6）。

`_run_analysis` 调度逻辑：

```
prev = _load_prev_analysis()
heavy_due = prev 为空
          or (now - prev.generated_at) ≥ insight_heavy_interval_hours
          or mode == "full"
if heavy_due: 全量 run_analysis（现路径）
else:         轻量路径：
              - keywords/trending/quality/trajectories 照算（统计法，秒级）
              - topics/deep_insights/ragas 沿用 prev 的旧值
              - 输出 dict 增加 "generated_at" 与 "stale": true 标记
```

- `analysis_snapshot.json` 增加 `generated_at` 字段（ISO8601 北京时间）
- 前端洞察面板头部追加生成时间（"洞察生成于 X 小时前"）， stale 时降透明度显示

### D4 bad_date 源降权（第三批）

- 累积阶段已算出 `_unreliable_srcs`（bad_date 审计）→ 写入 trend_history 快照：`snapshot["bad_date_sources"] = [...]`
- insight_engine 的 rising/关键词统计：来自 `_unreliable_srcs` 的条目在频次统计中权重 ×0.3（微信源日期本就是抓取时间，会伪造"同时爆发"）
- 回退统计路径（build_rss_aggregator `_extract_keywords`）同款降权

## 5. TDD 测试清单（先红后绿；全部 mock urlopen/LLM，零网络）

### D1 嵌入缓存

| ID | 测试 | 断言 |
|---|---|---|
| T-D1-1 | 同文本连续两次 `_get_embeddings` | API 调用恰 1 次；两次返回向量一致 |
| T-D1-2 | 50% 命中的混合批 | 只对未命中文本发起 1 次批量调用；返回顺序=输入顺序 |
| T-D1-3 | 缓存持久化→新进程加载 | 零 API 调用直接命中 |
| T-D1-4 | 缓存文件损坏（非法 JSON） | 忽略缓存全量重算，不抛异常 |
| T-D1-5 | 模型名变更 | 旧缓存整体失效重算 |
| T-D1-6 | 超 5000 条 | LRU 淘汰最旧，容量受控 |

### D2 查询批化

| ID | 测试 | 断言 |
|---|---|---|
| T-D2-1 | 15 个簇的深度洞察 | 检索嵌入 API 调用 = 1 次（原 ≤15 次）；每个簇拿到自己的查询向量 |
| T-D2-2 | RAGAS 5 簇上下文 | 嵌入调用 = 1 次 |

### D3 轻/重分级

| ID | 测试 | 断言 |
|---|---|---|
| T-D3-1 | light 场（prev 新鲜） | 聚类/深度洞察嵌入调用 = 0；keywords/trending/quality 字段仍产出 |
| T-D3-2 | full 模式 | 无条件重分析 |
| T-D3-3 | prev 距今 ≥ interval | 触发重分析 |
| T-D3-4 | 输出含 generated_at + stale 标记 | 前端可读 |

### D4 bad_date 降权

| ID | 测试 | 断言 |
|---|---|---|
| T-D4-1 | 3 源同词爆发，其中 1 个在 bad_date 名单 | 该源该词频次按 0.3 权重计入 |
| T-D4-2 | 无 bad_date 名单（向后兼容） | 行为与现状一致 |

## 6. 验收标准

1. 全部测试绿；`_rev*/_rev2../_adv*` 系列既有测试无回归
2. 子agent 对抗性审查（并发/缓存一致性/降级路径）无 P0/P1
3. 线上：验证场 duration ≤30min 且洞察阶段 ≤25s（构建日志时间戳）；洞察面板显示生成时间标注
4. analysis_snapshot.json 主题/关键词数据不回退（前端面板不空）

## 7. 风险与回滚

| 风险 | 缓解/回滚 |
|---|---|
| 缓存向量与模型版本错配 | 缓存记录 model 字段，变更即失效 |
| emb_cache.json 增长 | 5000 条 LRU 封顶 |
| light 场面板数据陈旧误导 | 前端"生成于 X 小时前"标注 + stale 降透明度 |
| 整体回滚 | 全部改动在 insight_engine.py + build_rss_aggregator.py 的 `_run_analysis`，revert 单提交即可 |

## 8. 实施顺序

1. spec 提交（本文件）
2. TDD 第一批：D1 缓存测试（红）→ 实现（绿）
3. TDD 第一批：D2 批化测试（红）→ 实现（绿）
4. TDD 第二批：D3 分级测试（红）→ 实现（绿）
5. TDD 第三批：D4 降权测试（红）→ 实现（绿）
6. 子agent 对抗性审查 → 修复发现项
7. 推送 + 触发构建 + 线上验收（时长 + 洞察面板截图）
