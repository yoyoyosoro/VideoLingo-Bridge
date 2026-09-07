# 自定义版维护

- `upstream`：官方 https://github.com/Huanshere/VideoLingo.git
- `origin`：自己的 GitHub 私有仓库（以 `git remote -v` 为准）。
- `main`：只跟随官方；`custom`：日常使用的自定义版。
- 当前使用目录：`C:\Users\85472\VideoLingo-dev`。原 `VideoLingo` 工作副本保留在 `local/legacy-main`，未上传。
- 三项改造：上传官方 SRT、跳过 ASR 并保留时间轴；视频背景 / 翻译风格输入；ZIP 多选原文、译文、原文 + 译文、译文 + 原文。

## 更新交给 Codex

请 Codex 获取官方更新并保留以上三项功能：

```bash
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
git switch custom
git rebase main
git push origin custom
```

有冲突时交给 Codex 同时保留官方更新和自定义功能，不要直接覆盖或统一选择 ours/theirs。验证后再上传；rebase 后如需强推，只能使用 `git push --force-with-lease origin custom`。

## 本机配置

仓库内 `config.yaml` 保留官方默认模板，本机真实配置未提交，当前用 `skip-worktree` 保留。此标记不是安全扫描：不要强制添加配置。切换分支或更新前，Codex 必须先把真实配置安全暂存到仓库外、取消该标记并使工作文件恢复为安全模板；更新后再合并本地配置并重新设置标记，禁止覆盖或提交真实密钥。提交前检查暂存区；运行数据和缓存不上传。
