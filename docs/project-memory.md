# 项目记忆

## 开发位置与仓库
- 当前开发目录：`C:\Users\85472\VideoLingo-dev`；旧目录 `C:\Users\85472\VideoLingo` 保持不动。
- GitHub：`https://github.com/yoyoyosoro/VideoLingo-Custom`，分支 `custom`。
- 仅修改明确要求的范围；本地 API 配置不随功能提交上传。

## 字幕功能约定
- 官方 SRT 的编号、时间、顺序和源文本保持原样；翻译使用稳定 cue ID，官方模式跳过 ASR、重新切分和配音。
- 视频风格在任务开始时固定；始终生成四种字幕，下载选择只影响导出。
- 单选直接下载 SRT；多选下载仅含选中字幕的 ZIP；空选禁用下载。
- 选择写入本地 `config.yaml` 的 `subtitle_download_selection`，下次使用恢复；缺少配置时首次默认全选并自动初始化。
- 下载名称为 `类型丨原始视频名（去扩展名）.srt`；类型为 `src`、`tran`、`src_trans`、`trans_src`。
- ZIP 名为 `subtitles丨原始视频名（去扩展名）.zip`；包内字幕遵循相同规则。
- 上传时在现有输入清单中保存 `original_name`，保留空格和符号；旧任务缺少原名时回退当前媒体文件名。内部工作字幕文件名不变。
