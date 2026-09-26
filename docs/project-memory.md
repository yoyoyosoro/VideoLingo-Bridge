# 项目记忆

## 开发位置与仓库
- 当前开发目录：`C:\Users\85472\VideoLingo-dev`；旧目录 `C:\Users\85472\VideoLingo` 保持不动。
- GitHub：`https://github.com/yoyoyosoro/VideoLingo-Custom`，分支 `custom`。
- 仅修改明确要求的范围；本地 API 配置不随功能提交上传。

## 下载、分享与恢复
- 修改版从 `custom` 分支下载：`https://github.com/yoyoyosoro/VideoLingo-Custom/archive/refs/heads/custom.zip`；也可打开仓库，选择 `custom`，点击 `Code → Download ZIP`。
- 分支 ZIP 随后续推送更新；需要复现固定版本时使用对应提交。
- 源码下载不依赖 Releases。源码 ZIP 不是免安装包，新电脑仍需安装运行环境、依赖并填写自己的 API 配置。
- GitHub 可恢复已提交的源码与项目文档，不包含未上传的个人配置、视频、字幕输出或本地运行环境。
- 分享仓库链接或源码 ZIP 即可交付源码；私有仓库链接需要接收者拥有访问权限。

## 字幕功能约定
- 官方 SRT 的编号、时间、顺序和源文本保持原样；翻译使用稳定 cue ID，官方模式跳过 ASR、重新切分和配音。
- 视频风格在任务开始时固定；始终生成四种字幕，下载选择只影响导出。
- 单选直接下载 SRT；多选下载仅含选中字幕的 ZIP；空选禁用下载。
- 选择写入本地 `config.yaml` 的 `subtitle_download_selection`，下次使用恢复；缺少配置时首次默认全选并自动初始化。
- 下载名称为 `类型丨原始视频名（去扩展名）.srt`；类型为 `src`、`tran`、`src_trans`、`trans_src`。
- ZIP 名为 `subtitles丨原始视频名（去扩展名）.zip`；包内字幕遵循相同规则。
- 上传时在现有输入清单中保存 `original_name`，保留空格和符号；旧任务缺少原名时回退当前媒体文件名。内部工作字幕文件名不变。
