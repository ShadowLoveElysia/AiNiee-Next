# AiNiee-Next

[简体中文](README.md) | [English](Docs/README_EN.md) | [繁體中文](Docs/README_zh_CNTW.md) | [日本語](Docs/README_JA.md) | [한국어](Docs/README_KO.md) | [Русский](Docs/README_RU.md) | [Español](Docs/README_ES.md)

AiNiee-Next 是一个基于大语言模型的批量翻译工具，支持小说、电子书、文档、字幕、游戏文本、漫画以及实时音视频字幕的处理。

程序核心运行在命令行与终端交互菜单（CLI/TUI）中，同时提供网页控制台、桌面端窗口，以及供外部 AI 客户端调用的 MCP 和 Skills 接口，既可以拿来快速翻单本文件，也适合长篇系列和批量任务的长期处理。

[点击下载最新源码 ZIP](https://github.com/ShadowLoveElysia/AiNiee-Next/archive/HEAD.zip) — 下载默认分支当前最新提交的完整源码副本。下载后先解压，Windows 用户进入解压后的项目目录，依次运行 `Windows prepare.bat` 和 `Windows launch.bat`。

---

## 快速开始

### 1. 安装基础环境

项目依赖 Python 3.12 和 `uv` 包管理器。仓库根目录自带了各平台的准备脚本，首次使用直接运行对应脚本即可自动配置好基础环境：

- **Windows**：双击运行 `Windows prepare.bat`
- **Linux**：在终端运行 `bash "Linux prepare.sh"`
- **macOS**：双击运行 `Mac prepare.command`

如果你只需要翻译文本、电子书、字幕或游戏脚本，完成这一步就可以直接开始使用了。漫画、实时同传和视频翻译需要额外的视觉或语音模型环境，用到时再按后面的第 5 步单独安装即可。

### 2. 启动与首次配置

基础环境就绪后，运行对应平台的启动脚本打开主程序：

- **Windows**：双击运行 `Windows launch.bat`
- **Linux**：运行 `bash "Linux launch.sh"`
- **macOS**：双击运行 `Mac launch.command`

也可以在项目根目录直接用命令行启动：`uv run ainiee_cli.py`。

第一次启动会进入引导向导，按提示完成两步设置即可：

1. 选择界面语言（支持简中、繁中、英、日、韩、俄、西 7 种语言）。
2. 选择翻译方式：

   - **API 模式（最常用）**：在接口管理里选择平台（支持 OpenAI 兼容接口、Anthropic、Google、DeepSeek 以及 Sakura / LocalLLM 等本地模型接口），填写接口地址、API Key 和模型名称，测试连通后保存。
   - **外部 Agent 模式**：如果你希望直接调用外部 AI 助手或编程客户端的额度来翻译，可按向导开启 MCP 或外部接入引导。

### 3. 开始第一个文本或电子书任务

1. 在主菜单中选择输入文件或整个文件夹，设置源语言、目标语言和输出路径。
2. 如需使用术语表、角色设定或自定义提示词，可在规则和提示词菜单中配置并启用。运行参数和作品规则是分开保存的，切换不同作品时不用重复改接口设置。
3. 确认配置后开始翻译。运行过程中随时可以暂停、调整并发或切换备用 Key。
4. 如果中途断网或手动停止，下次选择同一个项目并选择恢复缓存即可断点续传，已经翻好的部分不会重复请求。
5. 翻译完成后，可以直接导出成品，也可以先用内置的终端编辑器或校对功能检查一遍再导出。

### 4. 启动网页控制台或桌面端

如果你更习惯用浏览器操作（尤其是查看统计图表、分页编辑缓存，或使用漫画编辑器），可以在终端主菜单里直接启动 Web 控制台，或在命令行使用桌面端启动脚本：

- **Windows**：运行 `Tools\TauriShell\LaunchGUI.bat`
- **Linux / macOS**：运行 `Tools/TauriShell/LaunchGUI.sh`

### 5. 使用漫画、实时同传与离线视频功能

这三个模块的推理依赖和模型体积较大，首次使用前需先运行对应的扩展准备脚本：

- **漫画翻译**：

  - 准备环境：Windows 运行 `Windows comic prepare.bat`，Linux/macOS 运行 `Unix comic prepare.sh`。
  - 使用方式：在网页控制台进入漫画编辑器进行可视化编辑和导出，或通过命令行 `uv run ainiee_cli.py manga <输入路径>` 批量运行。

- **实时同传与离线视频**：

  - 准备环境：Windows 运行 `Windows media prepare.bat`，macOS 运行 `Mac media prepare.command`。如果是在 Linux/WSL 下使用独立的 vLLM 语音识别服务，另行运行 `Linux qwen vllm prepare.sh`。
  - 使用方式：可通过主菜单进入，或直接运行 `uv run ainiee_cli.py live`（实时字幕，macOS 也可双击 `Mac live launch.command`）与 `uv run ainiee_cli.py video`（离线视频）。

---

## 文档与 Wiki

| 主题 | 文档 |
| :--- | :--- |
| 入门 | [图文快速上手](Docs/README_QUICK_START.md) · [DeepSeek API Key 申请](Docs/DEEPSEEK_API_KEY.md) |
| 翻译设置 | [提示词、术语表、润色与软件设置](Docs/TRANSLATION_WORKFLOW_GUIDE.md) |
| 自动化 | [工作流运行参数与继承规则](Docs/WORKFLOW_RUNTIME_PARAMETERS.md) |
| 同传与视频 | [媒体功能与模型说明](ModuleFolders/Media/README.md) · [macOS 同传测试指南](Docs/MACOS_LIVE_TRANSLATION_TEST.md) |
| MCP | [服务接入](Tools/MCPServer/README.md) · [客户端使用指南](Tools/MCPServer/MCP_CLIENT_GUIDE.md) |
| Skills | [HTTP、CLI 与 Python 调用](Tools/Skills/README.md) |
| Agent | [Headless Agent 使用说明](Tools/Agent/README.md) |
| 桌面端 | [Tauri 启动与构建](Tools/TauriShell/README.md) |
| 扩展开发 | [插件编写](PluginScripts/README.md) · [Reader / Writer 编写](ModuleFolders/Domain/FileAccessor/README.md) |
| 游戏文本 | [StevExtraction 使用说明](Tools/StevExtraction/使用说明.md) |
| 更新 | [更新日志](Docs/update_log.md) |
| 其他语言 | [English](Docs/README_EN.md) · [繁體中文](Docs/README_zh_CNTW.md) · [日本語](Docs/README_JA.md) · [한국어](Docs/README_KO.md) · [Русский](Docs/README_RU.md) · [Español](Docs/README_ES.md) |

---

## 主要功能

### 文本、电子书与游戏本地化

- **按需注入设定**：发送请求时只匹配当前片段里真正用到的术语和禁翻词，支持英文词形变化和词边界判断，减少无关信息对模型的干扰。
- **角色召回与分卷时间线**：根据前后几行的名字、别名、敬称、人称和口癖自动带出当前在场角色；多卷本小说可以按卷号记录角色和设定变化，翻前几卷时不会误用后几卷才出现的新译名。
- **多种一致性参考（可选）**：支持同项目重复长句的翻译记忆参考、基于本地关键词匹配的历史译文参考，以及基于工具调用的剧情摘要与人物记忆（开启记忆模式后为了保证前后顺序，会自动切为单线程运行）。
- **容错与补译**：自动保护代码块、占位符、换行和首尾空白；收到回复后校验行数、编号和外文残留。一批里如果只漏译了少数几行，会单独补译缺失行并拼回原位，不用整批重翻。
- **润色与校对审阅**：支持独立润色流程、基于规则的符号/占位符检查，以及 AI 校对建议。校对建议记录了原文指纹，可以在终端或网页端逐条接受、拒绝或撤销，不会误覆盖你手动改过的译文。
- **电子书整理工具**：支持异常 EPUB 保守读取（含正文噪声与日文注音过滤）、嵌套文本提取与原书结构内回写、编码与声明同步、译后目录及章节标题同步、横竖排切换、解除强制字体与字号、正文段落预设、局部链接修复、图片压缩与 WebP 转换及引用同步、双语 EPUB、语言与书名元数据整理、系列卷号识别与统一命名、系列元数据写入及批量自动合订、TXT 自动分章转 EPUB，以及日译中引号规范化；支持利用翻译缓存调整导出设置后重新导出。另附有系列电子书批量整合脚本（`Tools/Ebook/批量电子书整合.py`）和游戏文本提取工具（`Tools/StevExtraction`）。

### 漫画翻译与网页编辑器

- 支持图片、文件夹、ZIP/CBZ、RAR/CBR 和 PDF 导入，串联气泡与文本检测、OCR、批量翻译、底图修补和自动排版渲染。
- 内置质量拦截检查，如果某页出现模型异常降级、缺字或文字溢出，会标记为待人工复查并阻止直接作为成品导出。
- 网页端提供完整的图层编辑器，支持调整文本框位置与样式、用画笔重绘修复蒙版、单独重跑某一页的某个阶段，以及撤销/重做。支持导出图片、PDF、CBZ、ZIP、EPUB，以及带图层的 PSD 文件（或 JSX 脚本）。

### 实时同传与离线视频

- **实时同传**：采集系统声音或指定应用进程树音频（Windows 支持只抓指定软件或游戏进程，不混入其他软件声音；macOS 通过原生 Helper 采集），经过语音分段和本地模型识别翻译后，以悬浮字幕窗展示。附带主播术语表和独立的私密双向文字互译窗口。
- **离线视频**：自动抽音降噪、语音识别并整理字幕时间轴，支持本地模型与云端 API 组合使用，最终通过 FFmpeg 封装 MKV 软字幕或压制 MP4 硬字幕。

### 自动化与外部接入

- **队列、定时与目录监听**：支持任务队列（执行中仍可修改未开始的排队项）、Cron 定时任务，以及文件夹自动监听（检测到新文件写入稳定后自动入队，支持识别系列卷号顺序）。
- **MCP / Skills / Docker**：支持启动 MCP Server（stdio / streamable-http / SSE）与 Skills HTTP/CLI 服务，可将翻译推理交给外部 AI 客户端，由 AiNiee 统一处理文件读取、校验和原子写回。容器部署可参考 `Tools/Docker/Dockerfile`。

---

## 命令行常用操作

除了交互式菜单，所有核心任务也可以直接通过命令行运行，方便写进脚本或配合自动化使用：

```bash
# 翻译文件或目录，指定输出目录、语言并自动恢复断点
uv run ainiee_cli.py translate INPUT_PATH -o OUTPUT_PATH -s Japanese -t Chinese --resume --yes

# 仅润色 / 翻译+润色一体 / 仅从缓存导出成品（不调用模型）
uv run ainiee_cli.py polish INPUT_PATH --yes
uv run ainiee_cli.py all_in_one INPUT_PATH --yes
uv run ainiee_cli.py export INPUT_PATH --yes

# 漫画批量处理（先检查本地模型和设备状态）
uv run ainiee_cli.py manga INPUT_PATH --manga-runtime-check
uv run ainiee_cli.py manga INPUT_PATH --yes

# 直接进入实时同传或离线视频翻译
uv run ainiee_cli.py live
uv run ainiee_cli.py video

# 启动 MCP Server 或 Skills 服务
uv run ainiee_cli.py mcp --mcp-transport stdio
uv run ainiee_cli.py --skills
python Tools/Skills/cli.py list
```

查看全部命令行参数可执行 `uv run ainiee_cli.py --help`。

---

## 支持的文件格式

| 类别 | 格式 | 说明 |
| :--- | :--- | :--- |
| 纯文本 | `.txt`, `.md` | 逐行提取与回写，Markdown 会自动跳过纯图片行和引用定义 |
| 电子书 | `.epub` | 解析内部结构与目录并回写 |
| 办公文档 | `.docx`, `.pptx` | 提取文本节点或文本框段落回写；PPTX 不识别图片内文字，部分段内混合样式会被简化 |
| 表格 | `.csv`, `.xlsx` | CSV 直接读写；XLSX 是拆成 CSV 翻完再拼回去的，复杂公式和样式保不住，纯文字表够用就行 |
| 字幕与歌词 | `.srt`, `.vtt`, `.ass`, `.lrc` | 保留时间轴和样式标记，只替换正文内容 |
| 本地化工程 | `.po`, `.json` | PO 目前处理单数条目；JSON 自动识别 i18next、Paratranz、MTool 等结构 |
| 游戏工程 | Ren'Py, Translator++, VNText | 专用格式提取与回写 |
| PDF | `.pdf` | 依赖 BabelDOC 提取段落与回填排版，扫描件效果取决于 OCR 条件 |
| 旧版 Office | `.doc`, `.ppt` 等 | 仅支持 Windows，需要本机装有 Microsoft Word |
| 其他电子书 | `.mobi`, `.azw3`, `.fb2` 等 | 需开启并安装 Calibre，转换后再处理和回转 |

---

## 注意事项

1. **视频翻译范围**：离线视频流程目前只处理音轨语音，不识别视频画面里的内嵌文字；另外长视频的自动提词目前会把整段转录一次发给模型（还没来得及做分段预算切分），片子很长时建议手动填词表或使用长上下文模型。
2. **外部工具依赖**：漫画导出分层 PSD 需要本机装有 Photoshop（否则只能导出 JSX 脚本）；压缩与解压 RAR/CBR 格式需要系统环境中存在对应的外部命令行工具。
3. **远程访问安全**：Web 控制台默认只监听本机回环地址，内置的会话校验主要用于防止本地接口被跨站乱调，不是多用户账号权限系统。如需在远程访问，请务必在受信任内网使用，或前置反向代理和访问认证。

---

## 项目参考与鸣谢

- [AiNiee](https://github.com/NEKOparapa/AiNiee)：本项目基于其核心翻译逻辑开发，感谢原作者 NEKOparapa 及贡献者。
- [manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)（[Gitee 备份](https://gitee.com/hgmzhn/manga-translator-ui)）：漫画自动处理流程、阶段拆分与运行时资产组织参考。
- [Koharu](https://github.com/mayocream/koharu)：漫画工程、图层、文本块编辑和人工精修流程参考。

相关来源说明与鸣谢会持续保留，引用与复用遵循各项目的开源协议。

---

## 开源协议

本项目基于 GNU Affero General Public License v3.0 (AGPL-3.0) 开源，详情请参阅根目录下的 `LICENSE` 文件。

---

## 支持 AiNiee-Next

如果 AiNiee-Next 对你有帮助，欢迎通过[爱发电](https://ifdian.net/a/Next_ZhiXie)或下方赞赏码支持持续开发与维护。支持者会加入项目鸣谢列表，感谢每一份支持。

<div align="center">
  <img src="Docs/Images/赞赏码.png" alt="赞赏码" width="320">
</div>

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
