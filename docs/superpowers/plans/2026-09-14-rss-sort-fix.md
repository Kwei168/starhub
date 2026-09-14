# 实施计划：RSS 默认排序缺陷修复（Phase 1）

Spec：`docs/superpowers/specs/2026-09-14-rss-default-sort-fix.md`
唯一改动文件：`build_rss_aggregator.py`

> 行号是**改动前**的当前行号，仅用于定位。编辑一律用 anchor 字符串匹配，不要按行号改。

---

## 任务 0：建立测试骨架（RED）

- 文件：
  - `tests/rss_sort/test_rss_sort.py`（抽取 build 脚本内嵌 JS → 生成 harness → 调 node）
  - `tests/rss_sort/cases.js`（断言用例）
- 要做的：见这两个文件的实现。
- 验证：`python tests/rss_sort/test_rss_sort.py` **必须失败**，且失败原因是 `_dateCmpDesc is not defined` / 无日期条目置顶 —— 而不是语法或抽取错误。

## 任务 1：新增方向明确的降序比较器，替换 `newest` 分支

- 位置：`build_rss_aggregator.py`，紧跟 `_dateCmp` 结束后（`:2005` 之后、`/* F1 修复` 注释之前）
- 插入：

```js
  /* 时区安全降序比较：无日期一律沉底，与调用方向无关（修复 NaN 分支在降序下反转） */
  function _dateCmpDesc(x,y){
    var tx=x?new Date(x).getTime():NaN, ty=y?new Date(y).getTime():NaN;
    if(isNaN(tx)&&isNaN(ty)) return 0;
    if(isNaN(tx)) return 1;
    if(isNaN(ty)) return -1;
    if(tx===ty) return 0;
    return tx<ty?1:-1;
  }
```

- 替换 `:2018`：

```
      else ART.sort(function(a,b){ return _dateCmp(b.date,a.date); });
```
→
```
      else ART.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });
```

- 验证：`tests` 中 T1 / T2 / T3 转绿，T5 仍红。

## 任务 2：修正 `active` 分支的同款反转

- 替换 `:2013-2015`：

```
        var sa=srcLatest[a.sk]||'', sb=srcLatest[b.sk]||'';
        if(sa!==sb) return _dateCmp(sb,sa);
        return _dateCmp(b.date,a.date);
```
→
```
        var sa=srcLatest[a.sk]||'', sb=srcLatest[b.sk]||'';
        if(sa!==sb) return _dateCmpDesc(sb,sa);
        return _dateCmpDesc(b.date,a.date);
```

- 验证：T5 转绿。

## 任务 3：统一刷新路径的排序口径

- 替换 `:3041`：

```
      added.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
```
→
```
      added.sort(function(a,b){ return _dateCmpDesc(a.date,b.date); });
```

- 替换 `:3043`：

```
      ART.sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); });
```
→
```
      applySort();
```

- 验证：T7 转绿。

## 任务 4：让刷新路径具备纠错职责

- 替换 `:3040` 的 `if(!added.length) return 0;`
- 同时把 `:3042` 的 `for(var i=added.length-1;...)` 保持原样（`added` 未变）
- 改为：

```js
      if(!added.length){
        /* 无新增也要纠错：若可见首屏混入无日期条目（NaN 置顶缺陷的指纹），
           重新规范化；健康状态下该分支不触发，不会造成可见跳变 */
        var _head=Math.min(ART.length, wallLimit||0), _bad=0;
        for(var h=0;h<_head;h++){ var _d=ART[h].date; if(!_d||isNaN(new Date(_d).getTime())) _bad++; }
        if(_head>0 && _bad*2>_head){ applySort(); renderChips(); renderWall(); renderPanel(); }
        return 0;
      }
```

- 验证：T6 转绿；T1–T5、T7 保持绿。

## 任务 5：全量回归（对接验收标准 A1–A4）

- 复用 `.deploy-tmp/_ablation2.py` 的装载逻辑，输出修复后 A1–A4 实测值。
- 验证：A1=0、A2≥8353、A3≥18、A4≤1h。

## 任务 6：对抗性审查

- 派独立子代理扮演反方，输入 spec + diff，要求举证反驳（重点：稳定性、幂等性、`active` 模式、刷新抖动、`_head` 边界、`wallLimit||0`）。
- 验证：所有 Critical 级问题已闭环或记录为已知限制。

---

## 回滚

改动集中在单一文件、无配置与数据格式变更。回滚 = `git checkout -- build_rss_aggregator.py`。
本地产物 `rss-aggregator.html` 为旧版，不要在本地构建验证；以测试 + CI 产物为准。

---

## 执行结果与偏离（2026-09-14 完成）

| 任务 | 状态 | 说明 |
|---|---|---|
| 0 测试骨架 | 完成 | 10 个用例，首次运行 3 绿 7 红（RED 正确） |
| 1 `_dateCmpDesc` + newest | 完成 | — |
| 2 `active` 分支 | **偏离计划** | 计划写"改用它"，实际必须**同时移除原有的参数反转**（`_dateCmpDesc(sb,sa)` → `_dateCmpDesc(sa,sb)`）。反转技巧只对"语义与方向无关"的比较器成立，漏掉会让无日期源置顶。由 T5 抓出。 |
| 3 刷新路径口径 | 完成 | 第二处排序改为 `applySort()`；其前的 `added.sort()` 变为死代码，**已删**（审查 M5） |
| 4 刷新纠错 | **偏离计划** | 追加 `sortMode!=='quality'` 例外（审查 H1） |
| 5 全量回归 | 完成 | 基线取自 `git show HEAD:` 的原始代码，非人工复刻 |
| 6 对抗性审查 | 完成 | 红队提出 2 必改 + 4 记录项，全部闭环 |

最终：单元 14/14 绿、变异检出 5/5、全量回归 A1–A4 达标。

**过程事故（已修复并验证）**：审查子代理在执行过程中误用 `git checkout -- build_rss_aggregator.py`，一度丢弃未提交的修复，随后用会话内 diff 通过 `git apply` 恢复。主代理事后独立验证：5 处 `_dateCmpDesc` 位点齐全、`localeCompare` 日期比较已清零、14/14 测试绿 —— 工作区确认完好。教训：给子代理的指令必须显式禁止 `git checkout`/`git restore` 类破坏性命令，详见下。

