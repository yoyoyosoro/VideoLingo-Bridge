# VideoLingo Custom

本仓库是基于 [Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo) 的个人自定义版，日常使用 **`custom` 分支**。原项目说明保留在下方；自定义版的使用方法和更新摘要以本节为准。

## 自定义功能

- **官方 SRT 翻译**：上传视频和官方 SRT，跳过 ASR，保留原字幕编号、时间轴、顺序和原文，生成译文及双语字幕。由于不运行 ASR，请明确选择源语言。
- **视频背景 / 翻译风格**：处理前输入背景、术语和语气要求，传入摘要与翻译；任务开始后固定本次输入。
- **灵活下载**：选择原文、译文、原文 + 译文、译文 + 原文。单选直接下载 SRT，多选下载 ZIP，空选禁用；选择保存在本机，文件名保留原始视频名称。
- **多种 LLM 接入**：支持 OpenAI Compatible、Claude Messages API，以及 CC Switch 的 Claude Code 本地路由。Direct API 按模型家族提供推理选项，涵盖 GPT、Claude、DeepSeek、Gemini、MiMo；具体可用性取决于所选协议和上游支持。
- **独立路由配置与缓存**：CC Switch 模型、推理档位与 Direct API 分开保存；本地答案缓存区分模型、协议、推理档位、Provider 和映射。路由状态不明、自动 failover 或请求期间切换时，不复用不确定的缓存。

## 快速使用

1. 获取 `custom` 分支源码，在项目目录运行 `python setup_env.py` 安装环境和依赖。
2. Windows 双击 `OneKeyStart_uv.bat` 启动。已有环境可先运行 `OneKeyStart_uv.bat --check-only` 检查。
3. 在侧栏选择 API 接入方式并配置自己的服务。上传媒体；有官方 SRT 时一并上传，填写可选的翻译风格后开始处理。
4. 完成后选择字幕类型并下载。源码 ZIP 不包含本机环境、模型、真实 API 配置或运行产物。

**使用 CC Switch：** 在其 Claude Code 页面启用 Local Routing，管理 Provider、真实 Key 和模型映射。在 VideoLingo 选择 CC Switch，默认入口为 `http://127.0.0.1:15721`，下拉选择 `sonnet`、`opus` 或 `haiku`；它们是逻辑角色，实际模型由 CC Switch 映射。VideoLingo 不调用 Claude Code CLI。

推理档位为自动 / 默认、低、中、高、极高、最大。建议从自动档开始；显式档位表达请求意图，是否生效由 CC Switch 和上游决定。Prompt Cache 开关不保证上游命中或免除输出计费。

## 更新摘要（2026-10-19）

- 新增 Messages / CC Switch 接入、按模型能力显示的推理设置和中英文界面文案。
- 增加六档 CC Switch 推理选择及独立逻辑模型下拉，支持由 Provider 映射到不同品牌模型。
- 修正 Provider 或模型映射变化后的缓存隔离；记录 usage / stop reason，对截断、拒绝、空响应等明确错误停止无意义重试。
- 纳入此前已提交的 PyAV 兼容、NLTK 数据放入虚拟环境，以及 uv 基础 Python 路径消失或含空格时的环境修复。
- 保留官方 SRT、视频风格、字幕选择和下载命名功能。

**验证边界：** 本次交付运行本地隔离回归，不额外请求付费 Provider。既有验收记录包含短字幕请求；不代表完整视频或多线程长任务验收。既有 CC Switch 4.0.9 验收记录显示，Gemini Native 会省略显式推理档位，特定 GPT 模型的最大档会降为 `xhigh`；这些限制由转换链决定。

分支与后续官方同步见 [CUSTOM_UPDATE.md](CUSTOM_UPDATE.md)。本机配置和个人路由验收报告不上传。

---

<div align="center">

<img src="/docs/logo.png" alt="VideoLingo Logo" height="140">

# Connect the World, Frame by Frame

<a href="https://trendshift.io/repositories/12200" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12200" alt="Huanshere%2FVideoLingo | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[**English**](/README.md)｜[**简体中文**](/translations/README.zh.md)｜[**繁體中文**](/translations/README.zh-TW.md)｜[**日本語**](/translations/README.ja.md)｜[**Español**](/translations/README.es.md)｜[**Русский**](/translations/README.ru.md)｜[**Français**](/translations/README.fr.md)

</div>

## 🌟 Overview ([Try VL Now!](https://videolingo.io))

VideoLingo combines speech recognition, subtitle translation, segmentation and dubbing in a Streamlit interface. It produces subtitle files and optionally subtitled or dubbed videos. Translation quality depends on the source audio, language and chosen models.

Key features:
- 🎥 YouTube video download via yt-dlp

- Word-level speech recognition and alignment with WhisperX

- **📝 NLP and AI-powered subtitle segmentation**

- **📚 Custom + AI-generated terminology for coherent translation**

- Direct translation with optional reflection and natural rewriting

- Subtitle segmentation with configurable length limits

- **🗣️ Dubbing with GPT-SoVITS, Azure, OpenAI, and more**

- 🚀 One-click startup and processing in Streamlit

- 🌍 Multi-language support in Streamlit UI

- 📝 Detailed logging with progress resumption

- 🔍 Model searchbox with API auto-fetch — search and filter from your provider's full model list

- ⏯️ Task control — pause, resume, or stop processing at any step

The workflow combines transcription, translation, subtitle layout and dubbing in one project.

## 🎥 Demo

<table>
<tr>
<td width="33%">

### Dual Subtitles
---
https://github.com/user-attachments/assets/a5c3d8d1-2b29-4ba9-b0d0-25896829d951

</td>
<td width="33%">

### Cosy2 Voice Clone
---
https://github.com/user-attachments/assets/e065fe4c-3694-477f-b4d6-316917df7c0a

</td>
<td width="33%">

### GPT-SoVITS with my voice
---
https://github.com/user-attachments/assets/47d965b2-b4ab-4a0b-9d08-b49a7bf3508c

</td>
</tr>
</table>

### Language Support

**Input Language Support(more to come):**

🇺🇸 English 🤩 | 🇷🇺 Russian 😊 | 🇫🇷 French 🤩 | 🇩🇪 German 🤩 | 🇮🇹 Italian 🤩 | 🇪🇸 Spanish 🤩 | 🇯🇵 Japanese 😐 | 🇨🇳 Chinese* 😊

> *For local Chinese recognition, explicitly select Chinese to use the punctuation-enhanced Belle Whisper model.

Translation languages depend on the selected LLM; dubbing languages depend on the selected TTS method.

## Installation

Meet any problem? Chat with our free online AI agent [**here**](https://share.fastgpt.in/chat/share?shareId=066w11n3r9aq6879r4z0v9rh) to help you.

Install [Git](https://git-scm.com/downloads), [uv](https://docs.astral.sh/uv/getting-started/installation/) and [FFmpeg](https://ffmpeg.org/download.html) first. Reopen your terminal after installation and check `git --version`, `uv --version` and `ffmpeg -version`.

For NVIDIA acceleration, install a driver compatible with your GPU. The host installer selects PyTorch `cu128` when `nvidia-smi` reports CUDA >=12.8, otherwise `cu126`; without NVIDIA it selects CPU packages. This selects Python packages, not a system CUDA Toolkit. Local WhisperX GPU recognition also needs CUDA 12 cuBLAS and cuDNN 9 libraries available to the process; see [GPU prerequisites](docs/pages/docs/start.en-US.md#gpu-runtime).

> **Note:** FFmpeg is required. Please install it via package managers:
> - Windows: choose a **shared-library build** from the Windows builds linked on the [FFmpeg download page](https://ffmpeg.org/download.html), then add its `bin` directory to PATH.
> - macOS: ```brew install ffmpeg``` (via [Homebrew](https://brew.sh/))
> - Linux: ```sudo apt install ffmpeg``` (Debian/Ubuntu)

### Install with uv

uv downloads Python 3.13 and creates an isolated `.venv`. No preinstalled Python is needed for the command below. The application supports Python 3.10–3.13. Use **FFmpeg 7 shared libraries** for the pinned TorchCodec 0.7; FFmpeg 8/9 alone is not compatible. See the [verified Windows build](docs/pages/docs/start.en-US.md#ffmpeg-runtime).

1. Clone the repository

```bash
git clone https://github.com/Huanshere/VideoLingo.git
cd VideoLingo
```

2. Create the environment and install dependencies

```bash
uv run --no-project --python 3.13 setup_env.py
```

3. Start the application

```bash
.venv\Scripts\streamlit run st.py        # Windows
.venv/bin/streamlit run st.py            # macOS / Linux
```

Or double-click `OneKeyStart.bat` on Windows. It prefers `~/.venvs/videolingo` when present, then the project `.venv`. Open `http://localhost:8501` and enter your API URL, key and model in the sidebar.

### Docker
For a Linux NVIDIA container deployment, install Docker, a compatible GPU driver and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). The image uses the same Python 3.13 setup and application dependencies, with CUDA 12.8.1/cu128 by default. See [Docker docs](/docs/pages/docs/docker.en-US.md) for the matched CUDA 12.6 alternative and persistence settings.

```bash
docker build -t videolingo .
docker run -d -p 8501:8501 --gpus all videolingo
```

## APIs
VideoLingo supports OpenAI-Like API format and various TTS interfaces:
- LLM: choose an OpenAI-compatible Chat Completions provider and model that can return the structured JSON required by the workflow. [OpenLux](https://www.openlux.ai/register?aff=wKYu) is recommended; set the API URL to `https://api.openlux.ai/v1`. Prefer GPT-6 Luna with model ID `gpt-6-luna` for best value, GPT-6 Sol with `gpt-6-sol` for better quality, or Claude Opus 5.5 with `claude-opus-5-5` for best quality. OpenLux relay rates are in the install docs. Configure the API URL, key and model in the sidebar.
- Speech recognition: run WhisperX locally or use the ElevenLabs API.
- TTS: Azure, OpenAI, Fish TTS, SiliconFlow Fish/CosyVoice2, GPT-SoVITS, Edge TTS, F5-TTS and a custom adapter in `core/tts_backend/custom_tts.py`.

For detailed installation, API configuration, and batch mode instructions, please refer to the documentation: [English](/docs/pages/docs/start.en-US.md) | [中文](/docs/pages/docs/start.zh-CN.md)

## Current Limitations

1. Background noise and language-specific alignment models affect recognition and word timestamps. Vocal separation may help. Numbers and symbols may lack reliable word timings; inspect the resulting subtitles.

2. LLM output must satisfy the workflow's JSON structure. For failures, inspect `output/gpt_log/error.json`. Existing successful response caches and completed outputs can be reused on retry; changing the model alone does not regenerate every completed stage. Do not delete all output as the first troubleshooting step.

3. Dubbing quality and timing depend on translation, the TTS service and speech rate. Speed adjustment does not guarantee natural delivery or perfect synchronization.

4. Local WhisperX uses one recognition/alignment language per segment. Mixed-language speech is not guaranteed to retain accurate text and timing in every language.

5. The dubbing workflow does not automatically assign a separate voice to each speaker.

## 📄 License

This project is licensed under the Apache 2.0 License. Special thanks to the following open source projects for their contributions:

[whisperX](https://github.com/m-bain/whisperX), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [json_repair](https://github.com/mangiucugna/json_repair), [BELLE](https://github.com/LianjiaTech/BELLE)

## 📬 Contact Me

- Submit [Issues](https://github.com/Huanshere/VideoLingo/issues) or [Pull Requests](https://github.com/Huanshere/VideoLingo/pulls) on GitHub
- DM me on Twitter: [@Huanshere](https://twitter.com/Huanshere)
- Email me at: team@videolingo.io

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Huanshere/VideoLingo&type=Timeline)](https://star-history.com/#Huanshere/VideoLingo&Timeline)

---

<p align="center">If you find VideoLingo helpful, please give me a ⭐️!</p>
