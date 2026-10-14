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

## 🎨 Live2D 角色模型更换与导入全指南

Kypetz 内置了**全通用 Live2D 渲染引擎**（支持 Cubism 2.1、Cubism 3.0、Cubism 4.0 及最新规范），支持无缝载入市面上绝大多数二次元 Live2D 角色模型（包括手游拆包模型、VTuber 模型及自制模型）。

---

### 一、 支持的模型规范与文件格式

你的模型文件夹只需符合以下任意一种主流标准规范即可被自动识别与渲染：

| 规范标准 | 核心二进制模型 | 描述配置文件 (必需包含其一) | 物理与姿态支持 |
| :--- | :--- | :--- | :--- |
| **Cubism 2.1** | `.moc` | `model.json` 或 `index.json` | 支持 `.physics.json` 与 `.pose.json` |
| **Cubism 3.0 / 4.0 / 5.0** | `.moc3` | `xxx.model3.json` | 支持 `.physics3.json` 与 `.pose3.json` |

#### 标准模型文件夹目录结构示例：
```text
my_character/                         # 模型文件夹名称 (自定义)
├── character.model3.json             # 模型核心配置文件 (或 model.json / index.json)
├── character.moc3                    # Live2D 物理模型网格 (或 .moc)
├── character.physics3.json           # 头发与衣物物理晃动配置 (可选)
├── character.pose3.json              # 姿态互斥配置 (可选)
├── textures/                         # 贴图纹理目录 (包含 texture_00.png 等)
├── motions/                          # 动作组目录 (.motion3.json 或 .mtn 动作文件)
└── expressions/                      # 表情目录 (.exp3.json 或 .exp.json)
```

---

### 二、 两种更换模型的便捷方法

#### 方法 A：通过控制中心图形化一键导入（最推荐）
1. 双击运行 `start.vbs` 启动 Kypetz；
2. 点击桌宠底部控制底座最左侧的 **「设置齿轮」** 图标，打开 **Kypetz 控制中心**；
3. 在左侧菜单或下拉区域找到 **「Live2D 角色形象 / 皮肤外观」** 卡片；
4. 点击右侧的 **「导入本地 Live2D 文件夹」** 按钮；
5. 在弹出的系统文件夹选择窗口中，直接选中包含配置文件的模型文件夹并点击“选择文件夹”；
6. 程序会自动完成资产规范校验并将其拷贝至项目目录，同时**舞台上的桌宠会立刻刷新为你新导入的角色形象**！

#### 方法 B：手动放置模型文件（适合批量管理）
1. 解压你下载的 Live2D 模型压缩包；
2. 将模型文件夹整体复制并粘贴至本项目的 `Live2D/live2d-model/` 目录下：
   - 路径示例：`Kypetz/Live2D/live2d-model/my_character/`
3. 打开控制面板的「Live2D 角色形象」下拉选单；
4. 系统内置的动态自省引擎会自动列出所有新放进去的模型（会自动统计包含的动作数量，例如 `my_character [18动作]`）；
5. 选中它并点击 **「立即切换」** 即可实时换装！

---

### 三、 换装后大模型身体动作与人设联动

1. **动作与表情自适应**：
   切换角色模型后，系统后台会自动自省该模型真实拥有的所有动作组（Motions）和表情（Expressions）名，并实时更新至大模型的 System Prompt 中。
2. **大模型自动学会操控身体**：
   在后续对话中，大模型会自动利用 `[action: 动作名, 表情名]` 驱动新角色的独特姿态（如摸头、微笑、害羞、待机等），无需人工干预或手动配置动作映射表！
3. **搭配自定义人设**：
   更换形象后，推荐在控制中心的 **「Prompt 与 人设定制」** 中修改角色名称（`pet_name`）、对你的称呼（`user_call`）以及专属人设台词，让性格与立绘完美契合。

---

### 四、 常见问题与排错提示

- **Q: 导入模型后舞台是空白的或不显示？**
  - 请检查模型文件夹内是否直接包含 `.model.json` 或 `.model3.json`，确保没有发生两层文件夹嵌套（例如 `my_char/my_char/xxx.model3.json`）；
  - 请使用文本编辑器打开配置文件，确认内部引用的贴图路径（Textures）与实际图片文件名大小写一致。
- **Q: 模型出现重叠肢体（例如四只手）？**
  - 说明该模型包含了多套互斥手臂姿势。请确保文件夹内包含对应的 `pose.json` 或 `pose3.json` 文件并在主配置文件中正确声明了 `"pose"` 字段。

---

## 快捷键一览

- **按住 `Ctrl` 键**：麦克风开始录音，松开即发送并识别。
- **`Ctrl + Shift + Q`**：安全退出程序。
- **鼠标滚轮**：在角色身上滚动可直接无级缩放大小。

---

## 许可证与免责声明

1. 本软件源代码遵循 [MIT License](LICENSE) 许可协议开源。
2. 项目中包含的部分 Live2D 测试模型资产版权归原版权方所有，仅供个人技术研究与学习交流使用。使用者在公开发布、商用或分发时，应自行确保所使用模型与音频资产的合法授权，严禁用于任何商业侵权行为。
