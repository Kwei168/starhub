# 实施计划：RSS 主题聚类（外层主题 / 内层时间倒序）

Spec：`docs/superpowers/specs/2026-09-14-rss-topic-clustering-design.md`
改动文件：`build_rss_aggregator.py`、`build_config.json`、新增 `tests/rss_topic/`

> 行号是**改动前**的当前行号，仅用于定位。编辑一律用 anchor 字符串匹配，不要按行号改。

---

## 任务 0：建立测试骨架（RED）

- 文件：
  - `tests/rss_topic/_loader.py`（复制 `tests/rss_date/_loader.py`，加载 `build_rss_aggregator.py`）
  - `tests/rss_topic/_harness.js`（shim + 抽取块 `topic`，抽取 `_bucketTopics`/`_expandFold`/`_dateCmpDesc`）
  - `tests/rss_topic/cases.js`（断言用例 T1–T14）
  - `tests/rss_topic/test_rss_topic.py`（拼接 + 调 node）
  - `tests/rss_topic/regression_full.py`（对接 A1–A10）
- 抽取块内容（`_harness.js` 内，**先手写占位实现**，任务 9 落地后替换为真实抽取）：

```js
/* ===== 抽取块: topic ===== */
function _topicKey(x){ return (x.sk||'')+'|'+(x.u&&x.u!=='#'?x.u:(x.t||'')); }
function _expandFold(items){
  var byG={}, out=[], singles=[];
  items.forEach(function(a){
    var g=(typeof a.g==='number')?a.g:-2;
    if(g<0){ singles.push(a); return; }
    (byG[g]||(byG[g]=[])).push(a);
  });
  singles.forEach(function(a){ out.push({main:a, members:[a]}); });
  Object.keys(byG).forEach(function(g){
    var grp=byG[g].slice();
    grp.sort(function(a,b){ return _dateCmpDesc(a.date,b.date)||(_topicKey(a)<_topicKey(b)?-1:1); });
    out.push({main:grp[0], members:grp});
  });
  return out;
}
function _bucketTopics(list){
  var byCl={};
  list.forEach(function(a){
    var cl=(typeof a.cl==='number')?a.cl:-1;
    (byCl[cl]||(byCl[cl]=[])).push(a);
  });
  var groups=Object.keys(byCl).map(function(k){
    var cl=parseInt(k,10), ent=_expandFold(byCl[k]);
    ent.sort(function(a,b){
      return _dateCmpDesc(a.main.date,b.main.date)||(_topicKey(a.main)<_topicKey(b.main)?-1:1);
    });
    var meta=(CLUSTERS_BY_ID[cl])||null;
    return { cl:cl, kind:cl<0?'unclustered':((meta&&meta.kind)||'domain'),
             label:(meta&&meta.label)||'\u672a\u5f52\u7c7b', n:ent.length, entries:ent,
             latest:ent.length?ent[0].main.date:'' };
  });
  groups.sort(function(x,y){
    if(x.cl<0&&y.cl>=0) return 1;
    if(y.cl<0&&x.cl>=0) return -1;
    return _dateCmpDesc(x.latest,y.latest)||(x.cl<y.cl?-1:1);
  });
  return groups;
}
```

- 用例覆盖（对应 A1–A10 的可单元化部分）：
  - T1 组内严格时间降序；T2 `date` 为空者沉底且不破坏顺序
  - T3 组间按 `latest` 降序；T4 `cl=-1` 强制末位
  - T5 缺 `cl` 字段按 `-1` 处理（旧产物兼容）
  - T6 折叠：同 `g` 合并、主卡取最新、`members.length` 正确
  - T7 折叠：`g<0` 不合并；T8 折叠后组内顺序仍严格时间降序
  - T9 同 `latest` 时按 `cl` 升序兜底（**确定性**，连跑两次结果相同）
  - T10 空列表返回 `[]`；T11 全无日期不抛异常且不改变组内相对顺序
  - T12 `_bucketTopics` 不得修改入参 list（无副作用）
  - T13 `cl` 为 `undefined`/`null`/`NaN` 全部按 `-1`
  - T14 单条折叠组成员数 = 1 时不产生额外卡片
- 验证：`python tests/rss_topic/test_rss_topic.py` **必须失败**，且失败原因是 `_bucketTopics is not defined` 或 `CLUSTERS_BY_ID is not defined` —— 而不是语法/抽取错误。

## 任务 1：新增样板剥离与题名归一化

- 位置：`build_rss_aggregator.py`，`_has_repeated_chars()`（`:5012`）之前
- 新增：

```python
# 出版社样板：后缀（媒体名）/ 栏目前缀（IT早报 0914：）/ 抓取失败占位 / 纯链接
_BOILER_SUFFIX = re.compile(
    r"(?:\s*[-–—|]\s*(?:RFI|法国国际广播电台|BBC|CNN|FT中文网|金融时报|纽约时报|路透社?|联合早报|澎湃新闻)\s*)+$",
    re.I)
_BOILER_PREFIX = re.compile(r"^\s*(?:IT早报|早报|晚报|快讯|日报|午报)\s*\d{0,6}\s*[：:]\s*")
_TITLE_REJECT = re.compile(r"^\s*(?:源|来源)\s*[：:]|^https?://|^FetchError|^\s*\[[^\]]{0,4}\]\s*$")


def _strip_boilerplate(title):
    """剥离出版社样板前后缀 + 题名方括号前缀。幂等。"""
    if not title:
        return ""
    t = title
    for _ in range(3):  # 幂等收敛：允许前缀/后缀叠加
        prev = t
        t = _BOILER_SUFFIX.sub("", t)
        t = _BOILER_PREFIX.sub("", t)
        t = re.sub(r"^\[[^\]]{1,10}\]\s*", "", t)
        t = t.strip()
        if t == prev:
            break
    return t


def _norm_title(title):
    """折叠组键：剥离样板 → 去空白标点 → 小写 → 截断 48。"""
    t = _strip_boilerplate(title)
    t = re.sub(r"\s+", "", t).lower()
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t[:48]
```

- 验证：`tests/rss_topic/test_rss_topic.py` 的 `test_strip_boilerplate` / `test_norm_title`（新增子用例）转绿：法广后缀、IT早报前缀、`FetchError` 整条拒绝、`[北京]` 前缀、幂等性。

## 任务 2：主题域词典与分类

- 位置：紧跟任务 1 新增块之后
- 新增 `TOPIC_DOMAINS`（17 域，`(名称, 权重, 关键词表)`）与：

```python
def _topic_domain(title, summary=""):
    """词典打分取最高分域；0 分返回 None。确定性：同分按域顺序取先者。"""
    low = (title + " " + (summary or "")[:120]).lower()
    best, best_score = None, 0.0
    for name, weight, kws in TOPIC_DOMAINS:
        hit = 0
        for kw in kws:
            if kw in low:
                hit += 1
        if hit:
            score = hit * weight
            if score > best_score:
                best, best_score = name, score
    return best
```

- 关键词表初值取自 2026-09-14 探测脚本（17 域，实测覆盖 50.2%、抽检精度约 70-80%）：AI模型与产品 / AI应用与Agent / 芯片与硬件 / 融资并购IPO / 政策与监管 / 开源与开发 / 网络安全 / 互联网产品 / 学术与研究 / 科学发现 / 汽车出行 / 财经宏观 / 地缘国际 / 体育 / 娱乐游戏 / 社会民生 / 健康生物。
- 验证：`test_topic_domain` 转绿：已知标题命中预期域、无命中返回 `None`、同分确定性。

## 任务 3：事件簇聚类

- 位置：紧跟任务 2 之后
- 新增（**必须复用现有分词**，不得另写一套）：

```python
def _cluster_events(entries, threshold=0.20, min_size=3, max_clusters=12, df_cap=0.05):
    """标题 token Jaccard 贪心聚类 + 倒排索引候选。返回 [[entry_idx, ...], ...]

    确定性：候选按 (命中数 desc, cluster_id asc) 取前 12；同分不依赖 set 顺序。
    """
    if not entries:
        return []
    toks = [set(_tokenize_cached(e["tokens_src"])) for e in entries]
    df = collections.Counter()
    for ts in toks:
        df.update(ts)
    n = len(toks)
    drop = {w for w, c in df.items() if c > n * df_cap}
    filt = [ts - drop for ts in toks]
    inv = collections.defaultdict(list)
    clusters = []          # {'cent': set, 'cnt': Counter, 'members': [idx]}
    for i, ts in enumerate(filt):
        if len(ts) < 2:
            continue
        cand = collections.Counter()
        for w in ts:
            for ci in inv.get(w, ()):
                cand[ci] += 1
        ranked = sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        best, best_sim = -1, 0.0
        for ci, _h in ranked:
            cent = clusters[ci]["cent"]
            union = len(ts | cent)
            sim = len(ts & cent) / union if union else 0.0
            if sim > best_sim:
                best, best_sim = ci, sim
        if best >= 0 and best_sim >= threshold:
            clusters[best]["members"].append(i)
            clusters[best]["cnt"].update(ts)
            clusters[best]["cent"] = set(w for w, _ in clusters[best]["cnt"].most_common(20))
            for w in (ts & clusters[best]["cent"]):
                if best not in inv[w]:
                    inv[w].append(best)
        else:
            ci = len(clusters)
            clusters.append({"cent": set(ts), "cnt": collections.Counter(ts), "members": [i]})
            for w in ts:
                inv[w].append(ci)
    big = [c for c in clusters if len(c["members"]) >= min_size]
    big.sort(key=lambda c: (-len(c["members"]), entries[c["members"][0]]["tokens_src"]))
    return [c["members"] for c in big[:max_clusters]]
```

- 注：`e["tokens_src"]` = `_strip_boilerplate(title)`，**只喂标题，不喂摘要**——实测摘要并入令牌会使最大簇从 9 涨到 31（样板串味）。
- 验证：`test_cluster_events` 转绿：同题不同源必同簇；无关标题不同簇；簇数 ≤ max_clusters；连续两次调用结果一致。

## 任务 4：标签与主入口

- 位置：紧跟任务 3 之后
- 新增 `_topic_label(members, centroid)`：

```python
def _topic_label(members, centroid):
    """事件簇标签：质心 Jaccard 最高的题名（medoid），按标点截断 ≤18 字。
    纯 TF-IDF 回退——实测纯 TF-IDF 产出 '出席金/砖国家' 类碎片，故仅兜底。"""
    best, best_sim = "", -1.0
    for e in members:
        ts = set(_tokenize_cached(e["tokens_src"]))
        union = len(ts | centroid)
        sim = len(ts & centroid) / union if union else 0.0
        if sim > best_sim or (sim == best_sim and e["tokens_src"] < best):
            best, best_sim = e["tokens_src"], sim
    label = best[:18].rstrip()
    for sep in ("，", "。", "：", "！", "？", ",", ".", " ", "·", "|"):
        idx = label.find(sep)
        if 2 < idx < len(label):
            label = label[:idx]
            break
    if not label:
        kws = [w for w, _ in _tfidf_keywords([e["tokens_src"] for e in members], top_n=3)]
        label = " ".join(kws[:3])
    return label.strip()
```

- 新增主入口 `assign_topic_clusters(sources_with_items, config)`，返回 `clusters_meta`：
  1. 遍历 sources × items 建 entry 表（`title` / `tokens_src` / `norm` / `src_key` / `link` / `date` / `summary` / `cat`）
  2. 质量闸门：`_TITLE_REJECT` 命中或 `len(_strip_boilerplate(t)) < 4` 或 `_has_repeated_chars(strip, 2, 2)` → 跳过（该 item 最终 `cl=-1`）
  3. 折叠组：`_norm_title` 分组 → 组 id 按首次出现顺序；组内 ≥2 时写 `item["g"]`
  4. 事件簇：每组代表（组内 `tokens_src` 最长者）→ `_cluster_events()`
  5. 落位：`cl` = 代表所属事件簇 > `_topic_domain()`（域 id = `E + 域序号`）> `-1`；**同折叠组共享 `cl`**
  6. 元数据：`kind` / `label` / `n` / `t0` / `t1` / `cats` / `titles`（归一化代表题名 top 5）/ `kb`（质心字符二元组 top 40）
  7. 排序：按组内最新一篇时间降序；`cl=-1` 末位
- 配置读取：新增 `_load_topic_config()`（复刻 `_load_analysis_enabled()` 的容错风格），缺键填默认。
- 验证：`test_assign_topic_clusters` 转绿：断言每个被聚类 item 的 `cl` 与其折叠组同伴一致；`-1` 条目不被赋 `g`；同一输入两次调用 `clusters_meta` 逐字节相同。

## 任务 5：接入 `main()`

- 位置：`build_rss_aggregator.py:6551`（`_history_after = len(_rss_history)`）之后、`:6553` 分析流水线之前
- 插入（**失败必须降级为非致命**，不写 `cl` 即回落到现有平铺行为）：

```python
    # ── 主题聚类（外层主题 / 内层时间倒序）──
    topic_clusters_meta = []
    try:
        topic_clusters_meta = assign_topic_clusters(sources_with_items, _load_topic_config())
        _cl_on = sum(1 for s in sources_with_items for it in s.get("items", []) if it.get("cl", -1) >= 0)
        print("[主题聚类] %d 个组 / 已归类 %d 篇 / 未归类 %d 篇" % (
            len(topic_clusters_meta), _cl_on, total_items - _cl_on))
    except Exception as e:
        print("[主题聚类] 失败，回落到平铺时间线: %s" % e, file=sys.stderr)
        topic_clusters_meta = []
```

- 同时把 `build_html()` 的签名扩为 `build_html(..., topic_clusters=None)`，调用点 `:6591` 传入 `topic_clusters=topic_clusters_meta`。
- 验证：本地构建打印分组统计；`topic_cluster_enabled=false` 时不打印且 `rss_api_snapshot.json` 无 `cl` 键（A6）。

## 任务 6：注入 `window.CLUSTERS` 与 `CLUSTERS_BY_ID`

- 位置：`build_html()` 内，`ANALYSIS_DATA` 注入点（`:2256`）之后
- 新增：

```python
  var CLUSTERS = """ + (json.dumps(topic_clusters, ensure_ascii=False, separators=(",", ":")) if topic_clusters else '[]') + """;
  var CLUSTERS_BY_ID = (function(){ var m={}; for(var i=0;i<CLUSTERS.length;i++) m[CLUSTERS[i].id]=CLUSTERS[i]; return m; })();
```

- 验证：产物 HTML 含 `var CLUSTERS = [` 且 `topic_cluster_enabled=false` 时为 `[]`（A6）。

## 任务 7：CSS

- 位置：`.wall { columns:4 300px; column-gap:14px; }`（`:1663`）之后
- 新增：`.wall.topic`、`.tgroup`、`.tg-head`（`position:sticky; top:var(--hdr-h,0px)`）、`.tg-kind`、`.tg-meta`、`.fold-btn`、`.mini-row`、`.tg-more`。
- 关键：`.wall.topic { columns: unset; }` → `.wall.topic .tgroup .tg-body { columns:4 300px; }`（组内保留多列卡片，组间改块级流，否则 sticky 组头在多列容器内不可靠）。
- 响应式：`@media (max-width:900px)` 与 `(max-width:700px)` 各补一条 `.tg-body` 列数降级，与现有 `.wall` 断点一致。
- 验证：产物 HTML 出现 `.wall.topic` 规则；主题视图下用浏览器实测组头吸顶位置 = header 高度。

## 任务 8：排序控件加主题入口

- 替换 `:4899`：

```
'<select class="sort-select" id="sortSelect" title="\u6392\u5e8f\u65b9\u5f0f"><option value="newest">\u6700\u65b0\u53d1\u5e03</option><option value="oldest">\u6700\u65e9\u53d1\u5e03</option><option value="active">\u6700\u8fd1\u6d3b\u8dc3</option><option value="quality">\u4fe1\u6e90\u8d28\u91cf</option></select>\n'
```
→ 在 `quality` 之后追加：

```
<option value="topic">\u4e3b\u9898\u805a\u7c7b</option>
```

- 同时 `sortMode`（`:2308`）加非法值回落：`['newest','oldest','active','quality','topic'].indexOf(sortMode)<0 && (sortMode='newest')`。
- 验证：切换到 `topic` 后刷新页面仍为 `topic`（localStorage 持久化）；将被污染的值改回 `newest`。

## 任务 9：前端分桶与渲染

- 位置：`renderWall()`（`:2641`）内新增分支 + 其后新增 `_topicKey` / `_expandFold` / `_bucketTopics` / `renderTopicWall`
- 要点：
  1. `renderWall()` 首行按 `sortMode==='topic'` 分流到 `renderTopicWall(list)`；**其余分支一行不动**
  2. `_bucketTopics(list)` 为纯函数（与任务 0 的 harness 实现逐字一致），`renderTopicWall` 只做 DOM 拼装
  3. 组头：`<header class="tg-head">标签 + kind 徽标 + N 篇 · 时间跨度</header>`，**不得带 `.card`**
  4. `.tgroup` 加 `role="presentation"`（`#wall` 是 `role="feed"`，插入 `section` 会破坏 ARIA 契约）
  5. 卡片模板调用现有 `artKey` / `_dynTime` / `estRead` / `highlightEsc`，不新写
  6. 组内首屏上限 `GROUP_CAP=20`，超出渲染 `<button class="tg-more" onclick="expandGroup(...)">展开本组</button>`
  7. 折叠主卡底部渲染 `<button class="fold-btn" data-g="N">另有 N 源报道</button>`；点击展开 `.mini-row`（`hidden` 切换，不重建墙）
  8. `loadMore()`（`:2722`）在主题模式改为 `groupLimit += TOPIC_GROUP_STEP` 后重渲染
  9. `--hdr-h` 实测：`load`/`resize` 时写 `document.documentElement.style.setProperty('--hdr-h', header.getBoundingClientRect().height+'px')`
- 验证：T1–T14 全绿；浏览器实测 A1/A2/A3/A4。

## 任务 10：刷新通道归簇

- 替换 `_mergeRemoteSources()`（`:3364`）构造 `a` 的对象字面量，追加两个字段：

```js
cl:(typeof it.cl==='number')?it.cl:_runtimeCluster(it.t), g:(typeof it.g==='number')?it.g:-2,
```

- 新增 `_runtimeCluster(title)`：`_normTitleJs(title)` 后与 `CLUSTERS[*].titles` 精确比对，命中返回该簇 id，否则 `-1`。
- 新增 `_normTitleJs(title)`：与 Python 侧 `_norm_title` **同口径**（剥样板 → 去空白标点 → 小写 → 截 48）。
- 已知限制（写入 spec 第 6.6 节）：T1 实时源的新事件在下次构建前落「未归类」。
- 验证：`_mergeRemoteSources` 单测（harness 抽取 `merge` 块）断言：带 `cl` 的透传、无 `cl` 且题名命中时归簇、无命中时 `-1`、`g` 缺省为 `-2`。

## 任务 11：配置

- `build_config.json` 新增 7 个键（值见 spec 第 7 节）。
- 验证：删掉某个键后构建仍正常（走默认值）。

## 任务 12：全量回归（对接 A1–A10）

- `tests/rss_topic/regression_full.py`：用真实 `rss_api_snapshot.json` 走 `assign_topic_clusters()`，输出 A1–A3、A7、A8 实测值；用 `git show HEAD:build_rss_aggregator.py` 产基线对比 A6、A10。
- 验证：A1 ∈ [15,40]、A2 ≤ 55%、A3 零违例、A5 ≤ 5s、A6 逐字节一致、A7 一致、A8 428 组全覆盖、A9 12 组合通过、A10 一致。

## 任务 13：对抗性审查

- 派独立子代理扮演反方，输入 spec + diff，要求举证反驳。重点：
  - `_bucketTopics` 的确定性（同 `latest`/同 `cl` 的 tie-break）
  - 折叠是否影响 `visited`/`_bookmarks`（`artKey` 键冲突、收藏条目被折掉）
  - `wallLimit` 与 `groupLimit` 双分页的状态串味（切视图后残留）
  - `tierInterleave()` 与主题视图的顺序耦合
  - `.wall.topic` 换布局对 `#wall` 事件委托 / `updateCardStates` / `querySelector('.wall .card')` 的影响
  - `cl`/`g` 注入对 `rss_history.json`、`api/rss.js` 体积与 `rss-api` 快照 schema 的副作用
- 指令硬约束：**子代理禁止执行 `git checkout` / `git restore` / `git reset` 等破坏性命令**（2026-09-14 曾发生审查子代理误丢未提交修复的事故）。
- 验证：所有 Critical 级问题闭环或明确记录为已知限制。

---

## 回滚

- 代码：`git checkout -- build_rss_aggregator.py build_config.json`（新增 `tests/rss_topic/` 可保留）
- 功能：`topic_cluster_enabled=false` → 产物与基线一致（A6）
- 数据：`cl`/`g` 为增量字段，旧产物按缺省值解析，无迁移
- 本地产物 `rss-aggregator.html` 为旧版，不要用本地构建验证线上；以测试 + CI 产物为准
