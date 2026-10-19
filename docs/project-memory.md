# 项目记忆

## 开发位置与仓库
- 当前开发目录：`D:\VideoLingo-dev`；旧目录保持不动。
- GitHub：`https://github.com/yoyoyosoro/VideoLingo-Custom`，分支 `custom`。
- 仅修改明确要求的范围；本地 API 配置不随功能提交上传。
- 仓库首页包含自定义功能与使用说明；`CUSTOM_UPDATE.md` 说明分支维护。部分克隆仅有 `custom`，同步官方前核对并按需补齐 `upstream` / `main`。

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

## LLM 与路由约定
- API 接入为 `openai`、`anthropic`、`cc_switch`；缺少协议字段时保持 OpenAI Compatible。Direct 模型能力逻辑与 CC Switch 逻辑档位分开。
- CC Switch 使用 Claude Code namespace 的 localhost `/v1/messages`，不调用 CLI；真实 Key 和实际模型映射由 CC Switch 管理。逻辑模型下拉为 `opus` / `sonnet` / `haiku`。
- CC Switch 独立保存模型与六档推理意图；自动档省略显式意图，最大档发送 API `max`。转换后的实际档位取决于 Provider 与 CC Switch。
- 本地答案缓存包含模型、协议、档位及无凭据的路由身份；Provider / 映射变化失效，路由不明、failover 或请求期间切换时停用不确定缓存。
- 个人路由审计与验收报告仅留本机；对外说明不得把短字幕、mock 或离线验证扩展为完整视频验收。
