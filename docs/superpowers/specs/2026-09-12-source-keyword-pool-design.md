# 分源关键词池设计

> **目标**：去噪、准趋势、抓热点

## 问题

当前 `run_analysis` 对所有数据源（热榜 + RSS + Trending）的合并文本做一次 LLM 调用提取全局关键词，然后将这些关键词传给 `generate_deep_insights`。但洞察生成的检索上下文仅来自 RSS，导致：

- 热榜关键词（如"中国GT"、"娱乐热点"）在 RSS 上下文中找不到 → **relevance 低（0.6）**
- LLM 试图解释"数据不匹配"而非生成洞察 → **叙事脉络输出异常**
- RSS 和热榜关键词基本不重叠，混合后互相稀释 → **洞察质量下降**

## 设计

### 分源提取

```
doc_texts（全部）
    ├── rss_texts（[RSS/...]） → extract_keywords_llm → rss_keywords
    └── hot_texts（[热榜/...]） → extract_keywords_llm → hot_keywords

global_keywords = rss_keywords + hot_keywords（合并去重，用于展示和 rising）
```

### 关键词使用分配

| 消费方 | 当前 | 改后 |
|--------|------|------|
| `generate_deep_insights` | global keywords | **rss_keywords** |
| `_evaluate_and_correct` | global keywords | **rss_keywords** |
| rising 检测 | global keywords | global_keywords（不变） |
| 前端关键词展示 | global keywords | global_keywords（不变） |
| 输出 JSON `keywords.global` | global keywords | rss + hot 合并 |
| 输出 JSON `keywords.rss` | 不存在 | **新增** |
| 输出 JSON `keywords.hot` | 不存在 | **新增** |

### 数据流对比

```
改前：
  doc_texts → extract_keywords → keywords → 用于所有地方
                                ↑
                          热榜词+RSS词混合，噪音大

改后：
  rss_texts → extract_keywords → rss_keywords → 洞察生成（去噪）
  hot_texts → extract_keywords → hot_keywords → 舆情展示（抓热点）
  两者合并                  → global_keywords → rising + 展示
```

## 改动范围

### insight_engine.py

1. **`run_analysis`**（L1269-1271）：
   - 现有 `keywords = extract_keywords_llm(llm, doc_texts, top_n=top_kw)` 改为两次调用
   - 新增 `rss_keywords = extract_keywords_llm(llm, rss_texts, top_n=top_kw)`
   - 新增 `hot_keywords = extract_keywords_llm(llm, hot_texts, top_n=top_kw)`
   - `keywords`（global）= 合并 rss_keywords + hot_keywords（去重，rss 优先；无 LLM 调用）

2. **`generate_deep_insights` 调用**（L1316-1321）：
   - `keywords=keywords` → `keywords=rss_keywords`

3. **`_evaluate_and_correct` 调用**（L1324-1327）：
   - `keywords` → `rss_keywords`

4. **输出 JSON**（L1352-1355）：
   - `keywords.global` 保持现有格式
   - 新增 `keywords.rss` 和 `keywords.hot`

### test_insight_engine.py

- 更新 `test_run_analysis` 相关测试以验证分源关键词
- 新增测试：验证 `rss_keywords` 和 `hot_keywords` 分别提取

## 成本

- 多 1 次 LLM 调用（原来 1 次全局 → 现在 2 次分源，净增 1 次）
- 构建时间 +1-2s
- 无前端改动

## 预期效果

- **relevance**：0.6 → 0.8+（关键词和检索上下文完全对齐）
- **overall**：0.78 → 0.85+（relevance 提升带动）
- **叙事质量**：不再出现"数据不匹配"解释
- **前端**：可展示分源关键词，后续 UI 可按需使用

## 验证

- 本地 pytest 全部通过
- 线上构建日志验证：
  - `rss_keywords` 包含技术/AI 相关词
  - `hot_keywords` 包含舆情/热点词
  - `relevance` 评分 ≥ 0.7
  - 叙事脉络不含"数据不足"或"不匹配"
