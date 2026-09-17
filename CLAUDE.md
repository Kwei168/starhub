# StarHub 项目 AI 代理规范

## Git 操作规范（强制）

本项目有 CI 定时任务（每小时 auto-commit 数据文件），本地开发必须遵守以下规则以避免仓库损坏：

### 禁止事项

1. **禁止 `2>&1` 重定向**：PowerShell 沙箱对 git 子进程的 stderr 拦截不稳定，`2>&1` 会触发 `StandardErrorEncoding is only supported when standard error is redirected` 报错且命令不执行。用分号 `;` 分隔命令，不要用 `2>&1`。
2. **禁止 `git rebase`**：在并发写入环境下 rebase 容易产生悬挂对象导致 pack 文件损坏。
3. **禁止 `git commit --amend`**：amend 在已有并发提交的分支上会产生不可恢复的损坏。

### 正确做法

1. **同步远程**：`git fetch origin` → `git reset --hard origin/main`（丢弃本地未推送的修改，对齐远程）
2. **推送前检查**：`git status --short --branch` 确认无 ahead/behind
3. **推送流程**：
   - 先 `git fetch origin` 拉取最新
   - 若远程有新提交，`git reset --hard origin/main` 对齐（本地未推送提交可丢弃，因为 CI 的 auto-commit 只涉及数据文件）
   - 重新应用修改 → `git add` → `git commit` → `git push origin main`
4. **多条 git 命令用分号分隔**，不用 `&&` 或 `2>&1`

### 损坏修复

如果仓库出现 `Could not read` / `could not parse commit` 错误：
1. `git fetch origin`
2. `git reset --hard origin/main`
3. 重新应用修改（建议先 `git diff > patch.txt` 保存）

## 构建与 CI

- GitHub Actions 定时任务每小时自动 commit 数据文件（`chore: auto update stars`）
- 本地修改代码后推送，不要与 CI 的数据提交竞争
- 手动触发构建：`gh workflow run "Update Star Hub"`
