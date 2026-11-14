# AiNiee-Next

[简体中文](../README.md) | [English](README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

AiNiee-Next is a large language model–based batch translation tool for novels, ebooks, documents, subtitles, game text, manga, and real-time audio and video subtitles.

Its core runs through the command line and interactive terminal menus (CLI/TUI). It also provides a web dashboard, a desktop window, and MCP and Skills interfaces for external AI clients. It works for quickly translating a single file as well as ongoing work on long series and batch tasks.

[Download the latest source ZIP](https://github.com/ShadowLoveElysia/AiNiee-Next/archive/HEAD.zip) — Download a complete source snapshot of the default branch's latest commit. Extract it first; Windows users should open the extracted project folder and run `Windows prepare.bat`, followed by `Windows launch.bat`.

---

## Quick Start

### 1. Set Up the Base Environment

The project requires Python 3.12 and the `uv` package manager. The repository root includes setup scripts for each platform. On first use, run the appropriate script to configure the base environment automatically:

- **Windows**: Double-click `Windows prepare.bat`.
- **Linux**: Run `bash "Linux prepare.sh"` in a terminal.
- **macOS**: Double-click `Mac prepare.command`.

If you only need to translate text, ebooks, subtitles, or game scripts, you can start using the program after this step. Manga, live translation, and video translation require additional vision or speech model environments; install those separately using step 5 when needed.

### 2. Launch and Initial Configuration

Once the base environment is ready, open the program using the launch script for your platform:

- **Windows**: Double-click `Windows launch.bat`.
- **Linux**: Run `bash "Linux launch.sh"`.
- **macOS**: Double-click `Mac launch.command`.

You can also launch it from the command line in the project root: `uv run ainiee_cli.py`.

On the first launch, the setup wizard guides you through two steps:

1. Select the interface language (seven languages are supported: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, Russian, and Spanish).
2. Select a translation method:

   - **API Mode (most common)**: Select a provider in API management (OpenAI-compatible APIs, Anthropic, Google, DeepSeek, and local model interfaces such as Sakura / LocalLLM are supported). Enter the API URL, API key, and model name, test the connection, and save.
   - **External Agent Mode**: To translate using the quota of an external AI assistant or coding client, follow the wizard to enable MCP or the external integration guide.

### 3. Start Your First Text or Ebook Task

1. Select an input file or an entire folder in the main menu, then set the source language, target language, and output path.
2. If you need a glossary, character settings, or custom prompts, configure and enable them in the rules and prompts menus. Runtime parameters and work-specific rules are saved separately, so switching works does not require reconfiguring your API settings.
3. Confirm the configuration and start translating. You can pause, adjust concurrency, or switch to a backup key at any time during the task.
4. If the connection drops or you stop the task manually, select the same project next time and restore its cache to resume. Already translated content will not be requested again.
5. When translation finishes, export the result directly or review it first using the built-in terminal editor or proofreading tools.

### 4. Open the Web Dashboard or Desktop App

If you prefer working in a browser—especially for viewing statistics, editing paginated cache entries, or using the manga editor—you can start the web dashboard from the terminal main menu, or use the desktop launch scripts from the command line:

- **Windows**: Run `Tools\TauriShell\LaunchGUI.bat`.
- **Linux / macOS**: Run `Tools/TauriShell/LaunchGUI.sh`.

### 5. Use Manga, Live Translation, and Offline Video Features

These three modules have larger inference dependencies and models. Before first use, run the corresponding extension setup script:

- **Manga Translation**:

  - Environment setup: On Windows, run `Windows comic prepare.bat`; on Linux/macOS, run `Unix comic prepare.sh`.
  - Usage: Open the manga editor in the web dashboard for visual editing and export, or process batches with `uv run ainiee_cli.py manga <INPUT_PATH>`.

- **Live Translation and Offline Video**:

  - Environment setup: On Windows, run `Windows media prepare.bat`; on macOS, run `Mac media prepare.command`. For a standalone vLLM speech recognition service on Linux/WSL, also run `Linux qwen vllm prepare.sh`.
  - Usage: Enter through the main menu, or run `uv run ainiee_cli.py live` (live subtitles; on macOS, you can also double-click `Mac live launch.command`) and `uv run ainiee_cli.py video` (offline video).

---

## Documentation and Wiki

| Topic | Documentation |
| :--- | :--- |
| Getting started | [Illustrated Quick Start](README_QUICK_START_EN.md) · [Getting a DeepSeek API Key](DEEPSEEK_API_KEY_EN.md) |
| Translation settings | [Prompts, Glossaries, Polishing, and Application Settings](TRANSLATION_WORKFLOW_GUIDE_EN.md) |
| Automation | [Workflow Runtime Parameters and Inheritance Rules](WORKFLOW_RUNTIME_PARAMETERS.md) |
| Live translation and video | [Media Features and Models](../ModuleFolders/Media/README.md) · [macOS Live Translation Testing Guide](MACOS_LIVE_TRANSLATION_TEST.md) |
| MCP | [Service Integration](../Tools/MCPServer/README.md) · [Client Guide](../Tools/MCPServer/MCP_CLIENT_GUIDE.md) |
| Skills | [HTTP, CLI, and Python Calls](../Tools/Skills/README.md) |
| Agent | [Headless Agent Guide](../Tools/Agent/README.md) |
| Desktop | [Tauri Launch and Build](../Tools/TauriShell/README.md) |
| Extension development | [Writing Plugins](../PluginScripts/README.md) · [Writing Readers / Writers](../ModuleFolders/Domain/FileAccessor/README.md) |
| Game text | [StevExtraction Guide](../Tools/StevExtraction/使用说明.md) |
| Updates | [Changelog](update_log.md) |
| Other languages | [简体中文](../README.md) · [繁體中文](README_zh_CNTW.md) · [日本語](README_JA.md) · [한국어](README_KO.md) · [Русский](README_RU.md) · [Español](README_ES.md) |

---

## Main Features

### Text, Ebooks, and Game Localization

- **On-demand context injection**: Only glossary entries and do-not-translate terms that match the current passage are included in requests. English inflections and word boundaries are supported, reducing interference from irrelevant information.
- **Character recall and volume timelines**: Names, aliases, honorifics, personal pronouns, and speech habits in nearby lines are used to recall the characters currently present. For multi-volume novels, character and setting changes can be recorded by volume, preventing later names or translations from being applied to earlier volumes.
- **Multiple consistency references (optional)**: Supports translation memory for repeated long sentences within a project, historical translations retrieved through local keyword matching, and plot summaries and character memories accessed through tool calls. Enabling memory mode automatically switches processing to a single thread to preserve order.
- **Error recovery and missing-line translation**: Automatically protects code blocks, placeholders, line breaks, and leading/trailing whitespace, then checks response line counts, IDs, and remaining foreign-language text. If only a few lines are missing from a batch, those lines are translated separately and put back in place without retranslating the whole batch.
- **Polishing and proofreading review**: Supports a standalone polishing workflow, rule-based punctuation/placeholder checks, and AI proofreading suggestions. Suggestions record fingerprints of the original text and can be accepted, rejected, or undone individually in the terminal or web dashboard, protecting translations you have edited manually from being overwritten.
- **Ebook utilities**: Supports conservative reading of irregular EPUBs (including filtering text noise and Japanese ruby annotations), nested text extraction and writing translations back into the original book structure, synchronization of encodings and declarations, translated table-of-contents and chapter-title synchronization, horizontal/vertical layout switching, removal of forced fonts and font sizes, body paragraph presets, local link repair, image compression and WebP conversion with reference updates, bilingual EPUBs, language and book-title metadata management, series volume recognition and consistent naming, series metadata and automatic batch compilation, automatic TXT chapter detection and EPUB conversion, and Japanese-to-Chinese quotation mark normalization. Export settings can be adjusted and the book re-exported from the translation cache. Also included are a batch ebook series compilation script (`Tools/Ebook/批量电子书整合.py`) and game text extraction tools (`Tools/StevExtraction`).

### Manga Translation and Web Editor

- Imports images, folders, ZIP/CBZ, RAR/CBR, and PDF files, combining speech bubble and text detection, OCR, batch translation, background inpainting, and automatic typesetting and rendering.
- Built-in quality gates mark pages for manual review if a model unexpectedly falls back to a degraded mode, characters are missing, or text overflows, and prevent those pages from being exported directly as finished output.
- The web interface provides a full layer editor for adjusting text box positions and styles, repainting inpainting masks with a brush, rerunning an individual stage on a single page, and undo/redo. Export formats include images, PDF, CBZ, ZIP, EPUB, and layered PSD files (or JSX scripts).

### Live Translation and Offline Video

- **Live translation**: Captures system audio or audio from a selected application's process tree (Windows can capture only the chosen application or game without audio from other programs; macOS uses a native helper). After speech segmentation and local model recognition and translation, subtitles appear in a floating window. Includes a streamer glossary and a separate private two-way text translation window.
- **Offline video**: Automatically extracts and denoises audio, recognizes speech, and organizes subtitle timing. Local models and cloud APIs can be combined, with FFmpeg producing MKV files with soft subtitles or MP4 files with burned-in subtitles.

### Automation and External Integration

- **Queues, scheduling, and folder watching**: Supports task queues (pending tasks can still be edited while the queue is running), Cron schedules, and automatic folder watching. New files are queued once writes have stabilized, with series volume ordering supported.
- **MCP / Skills / Docker**: Supports an MCP Server (stdio / streamable-http / SSE) and Skills HTTP/CLI services. Translation inference can be delegated to external AI clients while AiNiee handles file reading, validation, and atomic write-back. For container deployment, see `Tools/Docker/Dockerfile`.

---

## Common Command-Line Operations

In addition to the interactive menus, all core tasks can be run directly from the command line for scripting and automation:

```bash
# Translate a file or folder, specify output and languages, and resume automatically
uv run ainiee_cli.py translate INPUT_PATH -o OUTPUT_PATH -s Japanese -t Chinese --resume --yes

# Polish only / translate and polish / export only from cache (no model calls)
uv run ainiee_cli.py polish INPUT_PATH --yes
uv run ainiee_cli.py all_in_one INPUT_PATH --yes
uv run ainiee_cli.py export INPUT_PATH --yes

# Batch manga processing (check local models and device status first)
uv run ainiee_cli.py manga INPUT_PATH --manga-runtime-check
uv run ainiee_cli.py manga INPUT_PATH --yes

# Open live translation or offline video translation directly
uv run ainiee_cli.py live
uv run ainiee_cli.py video

# Start an MCP Server or Skills service
uv run ainiee_cli.py mcp --mcp-transport stdio
uv run ainiee_cli.py --skills
python Tools/Skills/cli.py list
```

Run `uv run ainiee_cli.py --help` to view all command-line options.

---

## Supported File Formats

| Category | Formats | Notes |
| :--- | :--- | :--- |
| Plain text | `.txt`, `.md` | Extracts and writes back line by line; Markdown automatically skips image-only lines and reference definitions |
| Ebooks | `.epub` | Parses internal structure and navigation, then writes translations back |
| Office documents | `.docx`, `.pptx` | Extracts and writes back text nodes or text-box paragraphs; PPTX does not recognize text inside images, and some mixed formatting within paragraphs is simplified |
| Spreadsheets | `.csv`, `.xlsx` | CSV is read and written directly; XLSX is split into CSV files for translation and then reassembled. Complex formulas and formatting are not preserved; use it for simple text tables |
| Subtitles and lyrics | `.srt`, `.vtt`, `.ass`, `.lrc` | Preserves timing and style tags, replacing only the text |
| Localization projects | `.po`, `.json` | PO currently handles singular entries; JSON automatically recognizes structures such as i18next, Paratranz, and MTool |
| Game projects | Ren'Py, Translator++, VNText | Format-specific extraction and write-back |
| PDF | `.pdf` | Uses BabelDOC for paragraph extraction and layout write-back; results for scanned documents depend on OCR conditions |
| Legacy Office | `.doc`, `.ppt`, etc. | Windows only; requires Microsoft Word installed locally |
| Other ebooks | `.mobi`, `.azw3`, `.fb2`, etc. | Requires Calibre to be installed and enabled; files are converted for processing and converted back afterward |

---

## Notes

1. **Video translation scope**: The offline video workflow currently processes speech in the audio track only; it does not recognize text embedded in video frames. Automatic term extraction for long videos currently sends the entire transcript to the model in one request (budget-based splitting has not yet been implemented). For very long videos, supply a glossary manually or use a model with a long context window.
2. **External tool dependencies**: Exporting layered PSD files from manga requires Photoshop installed locally; otherwise, only JSX scripts can be exported. Compressing and extracting RAR/CBR files requires the corresponding external command-line tools on the system.
3. **Remote access security**: The web dashboard listens on the local loopback address by default. Its built-in session checks mainly prevent cross-site misuse of local endpoints; they are not a multi-user account and permissions system. For remote access, use a trusted private network or place a reverse proxy with access authentication in front of it.

---

## References and Acknowledgments

- [AiNiee](https://github.com/NEKOparapa/AiNiee): This project is built on its core translation logic. Thanks to the original author NEKOparapa and all contributors.
- [manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui) ([Gitee mirror](https://gitee.com/hgmzhn/manga-translator-ui)): A reference for the automated manga pipeline, stage separation, and runtime asset organization.
- [Koharu](https://github.com/mayocream/koharu): A reference for manga projects, layers, text block editing, and manual refinement workflows.

Source attribution and acknowledgments will continue to be retained. References and reuse follow the respective projects' open-source licenses.

---

## License

This project is open source under the GNU Affero General Public License v3.0 (AGPL-3.0). See the `LICENSE` file in the repository root for details.

---

## Support AiNiee-Next

If AiNiee-Next has been useful to you, you can support its continued development and maintenance through [Afdian](https://ifdian.net/a/Next_ZhiXie) or the donation QR code below. Supporters will be added to the project acknowledgments. Thank you for every contribution.

<div align="center">
  <img src="Images/赞赏码.png" alt="Donation QR code" width="320">
</div>

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
