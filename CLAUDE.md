# StarHub 项目 AI 代理规范

## Git 与推送规范（强制，2026-09-19 按实测重写）

### 0. 先认清仓库现状（照抄旧流程会出事的两条理由）

1. **`git push` / `git fetch` 直连是死的**：主仓 `.git` 已膨胀到 6.8GB 且含断链对象，任何走协议的传输都会失败。
   唯一实测可用的通道是 **GitHub Data API**：`blobs → tree(base_tree) → commit(parents) → PATCH ref(force:false)`，
   写前必须把 CRLF 归一成 LF（否则 blob 对不上）。仓库里已封装成 `tools/data_api_push.py`。
2. **Data API 不回写本地工作树** → 本地 `main` 与远端 `main` 是**两条并行历史**。
   本地看不出来"我的提交是否已推达"，只有 blob 比对才知道。

### 禁止事项

1. **禁止 `2>&1` 重定向**（PowerShell 沙箱对 git 子进程 stderr 拦截不稳定，命令会静默不执行）。多条命令用 `;` 分隔，
   不用 `&&`，也不用 `2>&1`。
2. **禁止 `git rebase`**、**禁止 `git commit --amend`**：并发 auto-commit 环境下会产生不可恢复的损坏。
3. **禁止在未做漂移核查前 `git reset --hard origin/main` / `git checkout -- .` / `git clean`**：
   这些动作会抹掉"尚未推达的本地提交内容"和未提交的源码改动（本会话曾因此丢掉过源码），
   而且旧文档里"本地未推送提交可丢弃，因为 CI 只涉及数据文件"这句**是错的** —— 构建产物、docs、
   `update.yml` 都在同一场提交里。
4. **禁止 `git add -A` / `git add .`**：本仓工作树常年带着他人/CI 的在途改动（`update.yml`、`build_rss_aggregator.py`、
   `rss_fetch_state` 属禁改禁提清单），只按具体路径 add。
5. **禁止在"有构建未结束"时推送**（包括 Data API）：`update.yml` 的 Commit 步骤会把它**检出时刻**的
   docs/源码按文件名写回，构建约 15 分钟，中途推的东西会在几分钟后被静默回滚。
   2026-09-19 晚实测两次吞档：22:06:06Z 推的文档被 22:00:28Z 起跑、22:16:00Z 提交的构建回滚
   （计划文档 blob `109b82f328`→`8f438e7bc0`，HANDOFF `3b516438c3`→`07b90b06e8`）。
6. **别把"推送窗口"算成"整点之后"**：除 `HH:00:2xZ` 的整点场，一天里还有大量中途 `dynamic`/`schedule`/`workflow_dispatch`
   （实测 20:16、21:19、22:06、22:16、22:32、22:36、22:40 都有场）。唯一判据是"当前无未完成的 run"，不是"离整点还早"。

### 正确做法：推送四步（顺序不可变，也不可省第 4 步）

```bash
# 1) 本地按具体路径提交（提交默认留本地）
git add <文件…> ; git commit -m "…"

# 2) 守门：确认没有任何未完成的 run（脚本内置该判据）
py -3.11 tools/data_api_push.py --check-only

# 3) 推送（写前自动 CRLF→LF，ref 用 force:false，别人抢先提交会直接报错而不是覆盖）
py -3.11 tools/data_api_push.py --msg "提交信息" <文件…>

# 4) 推完立刻自查 blob：看末行 `内容不同=0`；对全仓口径用
py -3.11 tools/remote_drift_check.py <路径…>
```

- 第 2 步报"有 N 场构建未结束"就**等它结束再推**（等约 15 分钟），不要为了赶时间用 `--allow-running`。
- 第 4 步是今天抓到问题的唯一手段（它抓到过"推送脚本被自己挪走导致推送静默没执行"和一次 docs 被吞）。
- 下一场构建结束之后，**再复查一次**漂移：只有那时的 blob 仍等于我们推的 sha，才算真正落住。

### 门禁与验证约定

- 门禁 B（CI 里的 pytest）是 `continue-on-error: true` **且会清空六个 API key** → 该步骤永远显示"绿"。
  只认日志里的 `[0-9]+ failed` / `[0-9]+ passed` 汇总行；本地同构复跑要照抄 CI 的环境（可选依赖开关是差异高发点）。
- 本地跑 pytest 必须加 `-s` 且用 `--junitxml` 读结果（Git Bash 的 capture 冲突 + 被测脚本重挂载 stdout 会吞输出）。
- 新增可选产物在 CI 里必须 `if [ -f ]` 守卫；`bash -e` 下 `git add` 缺文件会 128 退出连坐整场部署。
- 声称"修好了"之前要验证**最终产物里该字段真的生效**（拉线上产物/页面，不是看步骤结论），
  并且新测试要用变异体证明它能失败。

## 构建与 CI

- GitHub Actions 每小时自动 commit 数据文件（`chore: auto update stars`），并发 `cancel-in-progress: true`。
- **推完代码不要手动触发验证构建**：手动 dispatch 会被整点任务按 `cancel-in-progress` 挤掉（实测被挤三次），
  正确做法是**等下一个整点的 run 携带这次改动**，再按上面的判据核。
- 需要立刻部署时：`gh workflow run "Update Star Hub"`；但验收仍以整点 run 的产物为准。
- 统计口径数据一律拉**远端** `daily_insight_tracking_history.jsonl`：CI 只写远端，本地副本会陈旧。
