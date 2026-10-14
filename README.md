# Kypetz

Kypetz 是一个基于 Python (PySide6) 和 Live2D 的开源桌面 AI 伴侣软件。项目集成了大语言模型对话、离线语音识别、语音合成 (TTS) 以及 Live2D 动作表情联动，旨在为用户提供轻量、可高度自定义的虚拟桌面助手。

---

## 核心功能

### 1. 桌面交互与渲染
- 基于 `PySide6.QtWebEngineWidgets` 与 Pixi.js (Cubism 2/3) 渲染透明无边框窗口。
- 支持鼠标全局拖拽、滚轮无级缩放角色比例及 1:1 居中复位。
- 窗口置顶显示，支持托盘或底部控制栏管理。

### 2. 大语言模型接入与指令控制
- 兼容标准 OpenAI 协议接口，支持 DeepSeek、Qwen、Ollama、OpenAI 等主流大语言模型服务。
- **动作协议支持**：启动时自动解析当前 Live2D 模型的描述文件（`index.json` 或 `model.json`），动态自省模型支持的动作与表情列表，并注入系统 Prompt。
- 大模型可通过 `[action: 动作名, 表情名]` 标签直接控制桌面形象表演；亦支持对自然语言动作描述进行词根模糊适配。
- 文本过滤算法自动从回复中剥离控制标签，确保输入给语音合成引擎的台词纯净。

### 3. 语音合成 (TTS) 与双语支持
- **双模合成**：
  - 支持连接本地 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 服务输出定制音色。
  - 未配置本地服务时，自动降级为微软 Edge-TTS 在线合成。
- **双语发音模式**：
  - 中文发音模式：直接朗读回复文本。
  - 日语发音模式：当启用 SoVITS 时，后台自动调度 LLM 将回复翻译为口语化日语后进行合成，同时桌面上**保持显示原始中文对话卡片**。
- **音频流处理**：使用 `scipy.signal` 与 `numpy` 对音频进行 44.1kHz sinc 重采样与双声道转换，结合淡入淡出算法消除爆音，实现音频、口型与动作的毫秒级同步触发。

### 4. 离线语音识别 (ASR)
- 基于轻量级离线识别引擎 [Vosk](https://alphacephei.com/vosk/)，无需联网即可完成语音转文字。
- 默认支持按住 `Ctrl` 键进行对讲机式（Push-to-Talk）录音。
- 内置音频自适应动态增益（AGC），提升弱音量环境下的识别准确率。

### 5. 闲置主动交互机制
- 当检测到用户连续无交互超过 60 秒时，后台守护线程会在设定的随机冷却时间后，主动向大语言模型请求生成符合当前人设的问候或话题，并触发对应的动作演出。

### 6. 控制中心 (Dashboard)
- 提供独立配置面板，支持热更新 API 密钥、端点、模型参数、提示词 (Prompt)、角色名称及用户称呼。
- 支持内置角色皮肤快速切换，以及从本地任意目录导入 Live2D 模型文件夹。
- 内置标准输出日志流重定向显示，便于开发者排查异常。

---

## 系统架构

```text
Kypetz/
├── core/                       # 核心业务逻辑层 (纯逻辑无 GUI 强耦合)
│   ├── config.py              # 配置管理、Prompt 动态组装、全局常量
│   ├── llm.py                 # 大模型通信、模型拉取、实时口语翻译
│   ├── action.py              # 模型能力自省、动作指令解析与台词清洗
│   └── server.py              # 内置守护静态 HTTP Server (避免 WebEngine 跨域安全限制)
│
├── audio/                      # 音频流水线层
│   ├── speech.py              # GPT-SoVITS / Edge-TTS 双模语音合成调度
│   ├── player.py              # 内存音频重采样、音画毫秒级同步信号
│   ├── recognizer.py          # Vosk 离线识别与麦克风 AGC 增益
│   └── chimes.py              # 正弦波按键提示音生成器
│
├── ui/                         # 界面与交互层
│   ├── splash.py              # Tkinter 轻量启动与依赖环境自检
│   ├── widgets.py             # 矢量 SVG 渲染与控制底座基础控件
│   ├── bridge.py              # QWebChannel 与前端 JavaScript 桥接通信
│   └── dashboard.py           # 控制中心弹窗与模型导入界面
│
├── Live2D/                     # 前端引擎与静态资源
│   ├── index.html             # Live2D 渲染画布容器
│   ├── js/                    # Pixi.js 与 Cubism 运行时核心
│   └── live2d-model/          # 本地模型资源存放目录
│
├── main.py                     # 应用程序入口与事件主循环
├── requirements.txt            # Python 依赖清单
├── start.vbs                   # 无黑框静默启动脚本
└── start.bat                   # 命令行调试启动脚本
```

---

## 运行环境

- **操作系统**：Windows 10 / Windows 11 (64-bit)
- **Python 版本**：Python 3.10 ~ 3.12 (推荐 64-bit)
- **可选系统依赖**：[FFmpeg](https://ffmpeg.org/)（若使用 Edge-TTS 兜底，需确保 `ffmpeg` 命令在系统 PATH 中）

---

## 快速上手

### 1. 克隆代码库并安装依赖

```bash
git clone https://github.com/zongton/Kypetz.git
cd Kypetz
pip install -r requirements.txt
```

### 2. 准备语音识别模型 (可选但推荐)

如需使用离线语音输入功能：
1. 前往 [Vosk 官方模型库](https://alphacephei.com/vosk/models) 下载轻量中文模型（如 `vosk-model-small-cn-0.22`）。
2. 解压并将文件夹放置在 `Kypetz/models/` 目录下（或直接放在项目根目录）。

### 3. 启动程序

- **常规使用**：直接双击运行 `start.vbs`（后台静默运行，无控制台黑色窗口）。
- **开发调试**：在终端执行 `python main.py` 或运行 `start.bat`。

---

## 配置说明

首次启动时，程序会在根目录生成 `config.json`。你可以在控制中心内修改，也可以直接编辑该文件：

| 字段 | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `pet_name` | string | 桌宠角色名称 | `"要乐奈"` / `"小助手"` |
| `user_call` | string | 桌宠对用户的称呼 | `"主人"` / `"你"` |
| `llm_base` | string | 兼容 OpenAI 协议的 API 端点地址 | `"https://api.deepseek.com"` |
| `llm_key` | string | API 访问密钥 | `"sk-xxxxxxxx"` |
| `llm_model` | string | 当前调用的模型名称 | `"deepseek-chat"` |
| `voice_lang` | string | 发音语言模式 (`zh` 或 `ja`) | `"zh"` |
| `tts_url` | string | 本地 GPT-SoVITS 服务地址 (留空则使用 Edge-TTS) | `"http://127.0.0.1:9880"` |
| `ref_wav` | string | SoVITS 参考音频绝对路径 | `"D:/audio/ref.wav"` |
| `prompt_text` | string | SoVITS 参考音频对应的台词文字 | `"你好"` |
| `prompt_lang` | string | SoVITS 参考音频语言 (`zh` / `ja` / `en`) | `"zh"` |
| `live2d_model`| string | 当前加载的 Live2D 模型标识或文件夹路径 | `"038_collabo_a_ur"` |
| `system_prompt`| string | 自定义人设 Prompt（支持 `{pet_name}` 和 `{user_call}` 占位符） | `""` |

---

## 自定义 Live2D 模型导入规范

Kypetz 支持导入标准的 Cubism 2 (`.moc`) 或 Cubism 3/4 (`.moc3`) 模型文件夹：

1. 确保模型文件夹内包含标准的配置描述文件：
   - Cubism 2: `model.json` 或 `index.json`
   - Cubism 3/4: `xxx.model3.json` 或包含对应映射的 `index.json`
2. 打开程序底座的「控制中心」按钮 -> 切换至「Live2D 角色形象」-> 点击「导入本地 Live2D 文件夹」，选取包含配置文件的目录即可完成加载。
3. 加载完成后，系统会自动提取该模型包含的所有可用动作名，大模型即可直接调用。

---

## 快捷键一览

- **按住 `Ctrl` 键**：麦克风开始录音，松开即发送并识别。
- **`Ctrl + Shift + Q`**：安全退出程序。
- **鼠标滚轮**：在角色身上滚动可直接无级缩放大小。

---

## 许可证与免责声明

1. 本软件源代码遵循 [MIT License](LICENSE) 许可协议开源。
2. 项目中包含的部分 Live2D 测试模型资产版权归原版权方所有，仅供个人技术研究与学习交流使用。使用者在公开发布、商用或分发时，应自行确保所使用模型与音频资产的合法授权，严禁用于任何商业侵权行为。
