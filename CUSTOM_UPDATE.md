# 自定义版维护

- `upstream`：官方 https://github.com/Huanshere/VideoLingo.git
- `origin`：自己的公开仓库 https://github.com/yoyoyosoro/VideoLingo-Bridge.git（以 `git remote -v` 为准）。
- `main`：只跟随官方；`custom`：日常使用的自定义版。
- 当前开发目录：`D:\VideoLingo-dev`。旧目录与旧分支不参与日常开发。
- 三项改造：上传官方 SRT、跳过 ASR 并保留时间轴；视频背景 / 翻译风格输入；ZIP 多选原文、译文、原文 + 译文、译文 + 原文。
- 后续能力：单选直接下载 SRT、下载选择记忆及原始名称；Direct API / Messages / CC Switch 接入、推理档位和 Provider / 映射缓存隔离。使用与更新摘要见 `README.md`。

## 更新交给 Codex

请 Codex 获取官方更新并保留以上三项功能：

部分克隆只有 `custom`；若缺少远程或本地分支，先由 Codex 将 `upstream` 指向官方、获取分支，再从 `origin/main` 建立本地 `main`。仅上传本地更新时不必同步官方或 rebase。

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

仓库内 `config.yaml` 保留安全模板，本机真实配置不提交。新增可选 API 配置由代码默认值兼容，侧栏修改后保存到本机。不要将真实 Key、个人地址或 CC Switch 数据库复制进模板。

本机可能设置 `skip-worktree`；它仅隐藏工作区差异，不是防泄漏措施。切换分支或更新前，Codex 先把真实配置按原始字节安全暂存到仓库外，取消该标记并提供安全模板；更新后恢复或合并本地配置，核对后重新保护。不要将真实配置暂存为提交。提交前检查暂存区；运行数据、缓存与个人 Provider 验收报告不上传。
