# 每日洞察流水线 · 泳道流程图（Mermaid）

节点与行号取自 `build_daily_insight.py`、`.github/workflows/update.yml`、`api/rss.js`（2026-09-22 状态）。
图例：`⊕` 本轮（run 1282/1288）改动过的节点 · 虚线边 = 降级或兜底路径 · `⚠` 已知缺口。

```mermaid
flowchart TD

  subgraph L0["泳道 0 · CI 调度与门禁 update.yml"]
    direction LR
    C1["cron 21:00 全量 / 2,6,10,14 增量"]
    C2["workflow_dispatch 每小时刷新"]
    G1["Gate A 语法 blocking"]
    G2["Gate A2 rss_history + source_coverage blocking · 红即不提交不部署"]
    G3["Gate B 洞察测试 advisory · 红不挡部署"]
    G4["还原脏工作区 + 建/取缓存"]
    C1 --> G1
    C2 --> G1
    G1 --> G2 --> G3 --> G4
  end

  subgraph L1["泳道 1 · 输入层"]
    direction LR
    I1["RSS 历史缓存分块 · 72h 基线 / 按源放宽至 168h · MAX_ITEMS 120 每源 · ⊕ X-Rss-Retention on"]
    I2["热榜 实时 · 不做硬过滤"]
    I3["AIHOT 168h 内"]
    I4["AGI Hunt tier 分级"]
    I6["⚠ api/rss.js 运行时旁路 ?source= 与 ?batch= · 上游 429 时出厂 200 加空数组"]
    SUM["汇总计数 print RSS 热榜 AIHOT AGI"]
    I1 --> SUM
    I2 --> SUM
    I3 --> SUM
    I4 --> SUM
    I6 -. "不进洞察主链 · 只喂页面抽屉" .-> I1
  end

  subgraph L2["泳道 2 · 切片与向量缓存"]
    direction LR
    S1["切片 chunks + content_hash · main 5380"]
    V1["⊕ _merge_vector_cache · 5397-5413"]
    V2["合并 → 去重 → 判龄淘汰 其他源 48h → 封顶 30000 → 预算 3000 · RSS 保底 10%"]
    V3["守恒式 池 = 留存 + 超龄 + 判不了龄 + 超上限 + 预算外 · 实测 1282 池 31447 留存 30000"]
    EMPTYDIA["无 chunks 则跳过生成 · 只记基础统计"]
    S1 --> V1 --> V2 --> V3
    S1 -. "空集" .-> EMPTYDIA
  end

  subgraph L3["泳道 3 · 嵌入与检索"]
    direction LR
    E1["仅新增 hash 调 embedding · SiliconFlow bge-m3 与本地 fastembed 双通道"]
    E2["存向量 → 重建 FAISS"]
    E3["混合查询构建 → 混合检索 → rerank"]
    E4["_assemble_events 事件簇"]
    NODIA["无结果或无簇则跳过生成"]
    E1 --> E2 --> E3 --> E4
    E3 -. "检索无结果" .-> NODIA
    E4 -. "无事件簇" .-> NODIA
  end

  subgraph L4["泳道 4 · 打分与 LLM 主链"]
    direction LR
    P0["事件四维打分 信号深度40 科技相关30 事实密度20 新颖度10 · 2359-2379"]
    GATE["快筛门槛 editor_score 低于 55"]
    P1["_llm_phase1 事件归纳"]
    P1b["丢弃 信息不足 → 事实核查 → 自审 → 非AI 过滤 → _llm_consolidate_events 合并"]
    P2["_llm_phase2 逐事件深度解读 · 引用证据包"]
    DEGRADE["降级为仅聚类结果 · LLM 不可用"]
    P0 --> GATE --> P1 --> P1b --> P2
    P0 -. "门槛未过 · 跳过深度分析" .-> DEGRADE
    P1 -. "LLM 失败" .-> DEGRADE
    P2 -. "单事件失败则降级解读" .-> DEGRADE
  end

  subgraph L5["泳道 5 · 评估与收口"]
    direction LR
    R1["RAGAS 风格评估 · 未达标 0.70 触发自我修正"]
    R2["judge LLM 终版复评"]
    R3["主题对齐 · 裁掉无事件承载的从句"]
    RJ["judge 不可用或异常 → 沿用草稿分"]
    R1 --> R2 --> R3
    R2 -. "异常" .-> RJ
  end

  subgraph L6["泳道 6 · 破茧旁路 与主链并行"]
    direction LR
    B1["_select_bubble_events · 3362-3493"]
    B2["非科技候选池 → 热度排序 7 天窗 半衰期 72h → 三条路径"]
    B3["兜底路径必须排除全部主报告类别"]
    V3 -. "只读同一批 chunks" .-> B1
    B1 --> B2 --> B3
  end

  subgraph L7["泳道 7 · 产出与入库部署"]
    direction LR
    O1["daily-insight.json 含 bubble_breaker · 4513"]
    O2["daily-insight-history.html · 4583"]
    O3["index.html 的 daily-insight-start 到 end 区段 · 5030"]
    O4["tracking.jsonl 追踪读数"]
    D1["Commit and push · bot 提交产物入库"]
    D2["Deploy to Vercel · 只发布 api 目录"]
    D3["静态产物只在 kwei168.github.io · Vercel 域对产物故意 404 属域名分工不是断链"]
    O1 --> D1 --> D2
    O2 --> D1
    O3 --> D1
    O4 --> D1
    D2 --> D3
  end

  G4 --> SUM
  SUM --> S1
  V3 --> E1
  E4 --> P0
  P2 --> R1
  R3 --> O1
  B3 --> O1
  DEGRADE -. "仍出产物 · 只含聚类" .-> O1
  RJ -. "草稿分即终版" .-> O1

  classDef warn fill:#fff3cd,stroke:#b8860b,color:#333
  classDef degen fill:#f5f5f5,stroke:#888,color:#555
  class I6 warn
  class EMPTYDIA,NODIA,DEGRADE,RJ degen
```

## 读这张图的两条注意

1. `api/rss.js`（图右上角那条 ⚠ 旁路）**不在洞察主链上**。洞察吃的是构建期落盘的 RSS 历史缓存，运行时出口只服务页面抽屉的实时刷新 —— 本轮 4 处改动（`cleanLink`、超范围码点钳位、剥 fragment、媒体 url）全在旁路，影响抽屉显示，不影响洞察计算。
2. 图里的虚线边（降级/兜底）大多是**静默**的：Gate B advisory、embedding 双通道回退、judge 沿用草稿分、LLM 挂掉仍出聚类产物。所以判断"这场构建到底有没有真跑出洞察"要看 `build_logs` 与产物时间戳，不能只看 Actions 的绿勾。
