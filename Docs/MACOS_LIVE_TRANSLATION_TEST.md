# macOS 实时同传测试

当前版本是源码测试版，MLX 需要 macOS 14 以上及 Apple M 系列。
需要 macOS 的 Python 3.12（带 Tk）；M 系列请用
原生 arm64 Python。可安装 python.org 的 macOS 版本；Homebrew 用户需要
`python@3.12` 与 `python-tk@3.12`。未提供签名／公证的 `.app` 安装包。

## 启动与配置

主项目环境可双击根目录 `Prepare.command` 自动检测与配置，之后双击
`Launch.command` 打开主程序。仅使用同传时，也可直接运行下面的独立入口。

若窗口提示环境未安装，可双击 `PrepareMedia.command`，或在项目目录运行
`bash prepare_media.sh`，直接通过 uv 安装同传扩展并显示完整错误。
脚本验证成功后保存同传 Python 路径，重开窗口即可检查环境。
可显式指定 `bash prepare_media.sh cpu`，或 `bash prepare_media.sh auto index-q4`。

1. 下载完整项目，双击根目录 `LaunchLive.command`。
   若下载工具移除了执行权限，在项目目录运行 `bash LaunchLive.command`。
2. 首次启动自动准备小型桌面环境；打开后选择“自动配置推理环境”。
   同传依赖与主项目隔离，下载可能占用数 GB。
3. 保持计算设备为 `auto`，选模型并下载。Index 原始模型走 Apple MLX，
   GGUF 走 Metal；HY-MT 原始模型走 MPS。语音识别使用 CPU。
   8 GB 统一内存机器建议先试 Index Q4 GGUF。
4. 确认环境状态显示实际后端。若失败，记录窗口错误；可以手动换后端，
   程序不会静默回退或按翻译质量切换模型。

## 采集电脑声音

默认可直接使用原生内录，不需要 BlackHole：

1. 首次需要 Xcode 15.3 以上版本的 Command Line Tools。在终端运行
   `xcode-select --install`，完成系统安装后在同传窗口点击“自动配置推理环境”。
2. 音频选择“系统声音（原生内录）”，开始后允许系统音频录制权限。
   macOS 14.2+ 使用 Process Tap；13～14.1 使用 ScreenCaptureKit。
3. 播放讲话音频，检查仍能听到原音，并出现原文／译文。
4. 若权限被拒绝，进入“系统设置 → 隐私与安全性 → 屏幕与系统音频录制”
   允许 AiNiee Audio Capture 或 Terminal（名称取决于启动方式），重新启动。
5. 若原生默认路径报错，可手动选择“系统声音（ScreenCaptureKit）”再试。
   程序不会静默改录麦克风。

原生助手是本地编译、临时签名的测试版，当前开发环境没有 Mac SDK，尚未
完成 Swift 真机编译与权限验证。请保留窗口显示的构建错误和系统权限结果。

也可先绕过翻译模型单独测试内录。在项目目录使用同传环境的 Python：

```bash
Resource/MediaRuntime/macos-arm64/bin/python -m ModuleFolders.Media.macos_audio --check
Resource/MediaRuntime/macos-arm64/bin/python -m ModuleFolders.Media.macos_audio --seconds 10
Resource/MediaRuntime/macos-arm64/bin/python -m ModuleFolders.Media.macos_audio --screen --seconds 10
```

播放讲话期间测试，输出实际后端、样本数和峰值；不保存录音。峰值为 0
不能证明录制成功，需检查权限、音源和后端。此命令默认使用 M 系列环境路径。

如果希望使用已有虚拟声卡，可采用下面的兼容方式：

1. 安装 [BlackHole 2ch](https://existential.audio/blackhole/)，或使用 Loopback。
2. 在“音频 MIDI 设置”创建多输出设备，勾选扬声器／耳机及 BlackHole；
   根据主时钟设置为其他设备启用漂移校正。
3. 把 macOS 系统输出改为该多输出设备；在同传窗口刷新，选 BlackHole 输入。
   请明确选择虚拟声卡；默认“系统声音”走原生 API。
4. 系统询问时允许 Terminal／Python 的麦克风权限。若此前拒绝，在
   “系统设置 → 隐私与安全性 → 麦克风”打开后重新启动。
5. 选择源／目标语言，开始同传，然后播放讲话音频。

没有虚拟设备时，请显式选择麦克风测试现场讲话。程序不会自动把系统音频
测试变成麦克风采集，也不会安装驱动或修改 macOS 声音路由。

## 请反馈的结果

- Mac 型号、M 系列芯片、统一内存、macOS 版本与 Python 架构。
- 所选模型、实际推理后端，自动配置／模型下载是否成功。
- 能否同时听到原音并出现原文／译文；英文→中文与日文→中文分别测试。
- 一分钟连续讲话的识别／翻译耗时、字幕延迟及积压／丢段情况。
- 字幕字体与描边、背景透明度、拖动、锁定后点击穿透、解锁、Esc 隐藏。
- 全屏视频、切换桌面、蓝牙耳机切换后字幕与音频是否正常。
- 停止、再次开始、关闭窗口后有无残留的 worker／llama-server 进程。

本地回归覆盖环境分流、安装参数、设备选择、流式输出与进程清理。当前开发
环境无法证明 Mac 实机的音频、渲染、加速或实时性能，上述项目需实机确认。
