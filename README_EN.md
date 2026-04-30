# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[English](README_EN.md) | [简体中文](README.md)

**AiNiee-Next** is an engineering-focused refactor of the [AiNiee](https://github.com/NEKOparapa/AiNiee) core logic, designed for command-line environments.

This project introduces **uv**, a modern Python package manager, and implements significant stability optimizations for the underlying runtime. By taking control of IO streams and exception handling, we have built a robust TUI environment perfect for long-running tasks, headless server deployments, and automated workflows.

---

## Performance Showcase

**Built for ultimate performance and stability.**

The screenshot below demonstrates a ~20,000 line file being translated in approximately 4 minutes with 50 concurrent threads:

<div align="center">
  <img src="README_IMG/50并发deepseek测试.png" alt="50 Concurrency Performance Test" width="90%">
  <br>
  <em>50 Threads + DeepSeek API | 20k Lines | ~4 min | 99.6% Success Rate | 397k TPM</em>
</div>

---

## Key Features

### Runtime Stability
- **IO Stream Cleaning**: Refactored Stdout/Stderr capture logic, blocking redundant noise from dependencies, preventing TUI tearing or crashes
- **Smart Error Recovery**: Built-in exception interception and auto-retry mechanism with checkpoint resume, ideal for long-running tasks
- **Cross-Platform Compatible**: Supports Windows / Linux / macOS / Android (Termux), headless server friendly

### Intelligent Format Processing
- **Fully Automated Conversion**: Supports "Identify - Convert - Translate - Restore" workflow for .mobi / .azw3 / .kepub / .fb2 formats
- **Native Multi-Format Support**: Epub, Docx, Txt, Srt, Ass, Vtt, Lrc, Json, Po, Paratranz and 20+ formats
- **Calibre Middleware Integration**: Automatically invokes Calibre for complex ebook formats

### Live Mission Control Center
- **Dynamic Concurrency**: Adjust concurrent threads in real-time via `+` / `-` keys
- **API Key Hot-Swap**: Force API Key rotation via `K` key to handle rate limits
- **Mid-Task Monitoring**: Launch WebServer and auto-open browser via `M` key
- **System Status Monitoring**: Real-time status bar with color-coded border indicators
- **Cost & Time Estimation**: Auto-estimate token consumption, API costs, and completion time before task start

### Multi-Profile System
- **Profile Isolation**: Create, clone, and switch between multiple configuration sets
- **Scenario-Based Configs**: Separate "Quick Translation" and "Fine Polish" workflows
- **Hot Reload**: Configuration changes take effect without restart

### Plugin Architecture
- **Modular Extensions**: Safely extend functionality without modifying core code
- **Built-in RAG Plugin**: Auto-retrieve historical translations for context reference, improving terminology and style consistency
- **Translation Checker Plugin**: Auto-detect missing translations, errors, and format anomalies
- **Centralized Management**: Plugin management available in both CLI menu and Web UI

### Intelligent Task Queue
- **Batch Task Configuration**: Pre-configure multiple tasks with different files or translation strategies
- **Dynamic Queue Scheduling**: Drag-and-drop ordering (Web) and keyboard reordering (TUI)
- **Hot Task Modification**: Edit pending task parameters while queue is running
- **Auto Sequential Execution**: Optimized for large-scale translation workflows

### Context Caching
- **Multi-Platform Support**: Anthropic / Google / Amazon Bedrock context caching
- **Cost Optimization**: Cache system prompts and glossaries to significantly reduce API costs
- **Smart Fallback**: Auto-detect API compatibility, disable and notify when unsupported

### Thinking Mode Enhancement
- **Full Platform Compatibility**: Supports all major online API platforms and third-party proxies
- **Smart Parameter Configuration**: Different compatibility hints for online APIs and local models
- **Deep Reasoning Support**: Supports deep thinking mode for DeepSeek R1, Claude 3.5, and similar models

### API Failover
- **Multi-API Pool Management**: Configure multiple backup APIs
- **Auto Switching**: Automatically switch to backup API when primary fails
- **Threshold Control**: Configurable failover trigger threshold

### High Concurrency Performance
- **Async Request Mode**: aiohttp-based async I/O, breaks thread pool bottleneck, supports 100+ concurrency
- **Smart Error Classification**: Distinguishes "hard errors" (format/auth issues) from "soft errors" (rate limit/timeout) - hard errors don't retry, soft errors wait smartly
- **Provider Fingerprinting**: Auto-detects and records API feature support, silent degradation on next startup
- **Semaphore Protection**: Protects local system resources (file descriptors, ports) under high concurrency
- **Auto Suggestion**: Automatically suggests enabling async mode when concurrency ≥15 for better performance

---

## Quick Start

### Method 1: One-Click Launch (Recommended)

**1. Get the Code**
```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. Environment Setup (First Run)**

Windows:
```batch
Double-click prepare.bat
```

Linux / macOS:
```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. Launch Application**

Windows:
```batch
Double-click Launch.bat
```

Linux / macOS:
```bash
./Launch.sh
```

---

### Method 2: Manual Configuration

**1. Install uv**

Windows (PowerShell):
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Linux / macOS:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Android (Termux):
```bash
pkg update && pkg upgrade
pkg install python
pip install uv
```

**2. Get the Code and Launch**
```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## Command-Line Arguments

Supports launching tasks directly via command-line arguments for script integration and automation.

**Translation Task Example:**
```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

**Queue Task Example:**
```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

**MCP Server Example:**
```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

**Main Arguments:**
- `translate` / `polish` / `export` / `queue` / `mcp`: Task type
- `-o, --output`: Output path
- `-p, --profile`: Configuration profile name
- `-s, --source`: Source language
- `-t, --target`: Target language
- `--type`: Project type (Txt, Epub, MTool, RenPy etc.)
- `--resume`: Auto-resume cached tasks
- `--yes`: Non-interactive mode
- `--threads`: Concurrent thread count
- `--platform`: Target platform
- `--model`: Model name
- `--api-url`: API URL
- `--api-key`: API Key
- `--mcp-transport`: MCP transport mode, supports `stdio` / `streamable-http` / `sse`

---

## Web Dashboard

This project includes a React-based Web Dashboard, now in stable release.

**How to Start:**
1. Run `uv run ainiee_cli.py` to enter the main menu
2. Select **15. Start Web Server**
3. The program will start the service (default port 8000) and open your browser

**Features:**
- Visual Dashboard: Real-time RPM, TPM, and task progress charts
- Network Access: Remote monitoring via LAN IP
- Profile Management: Create and switch profiles from web UI
- Queue Management: Drag-and-drop task reordering
- Plugin Center: Enable/disable RAG and other features

> **Development Note**: The Web Dashboard is now stable, but has fewer features compared to TUI mode. This project focuses on CLI/TUI interaction as the core development direction. Web features will be gradually updated in future releases.

---

## MCP Server

This project provides an optional MCP server module that reuses the existing WebServer backend and aims to cover the full Web API surface, so MCP clients can get an experience close to the Web dashboard.
Any LLM client that supports MCP over `stdio` or `streamable-http` can connect to this project directly, without reading repository files or manually assembling Web API calls.

**Startup Options:**
1. Direct CLI: `uv run ainiee_cli.py mcp --mcp-transport stdio`
2. Main menu: open the main menu and select **16. Start MCP Server**

**Notes:**
- The MCP server is optional and does not affect the main process when missing
- Required components and Python dependencies are checked on every MCP startup
- If dependencies are missing, the program shows complete install commands for the current system
- Menu startup uses background `streamable-http` mode and returns to the menu after 3 seconds
- If you change `mcp_server_port`, update the MCP route in your client as well

**Direct LLM client integration:**
1. MCP clients that support `stdio` can launch AiNiee CLI as a local MCP server.
If your client uses a `command + args` configuration format, this generic template can be used as a reference:

```json
{
  "mcpServers": {
    "ainiee-cli": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "H:\\小说\\AiNiee-CLI",
        "--isolated",
        "--no-project",
        "--quiet",
        "--with",
        "mcp",
        "--with",
        "fastapi",
        "--with",
        "uvicorn[standard]",
        "--with",
        "requests",
        "python",
        "Tools/MCPServer/server.py",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

Different clients may use slightly different field names, but the core idea is the same: `command=uv` plus the `args` shown above.
Replace the path with your own project directory. On Linux / macOS, replace `H:\\小说\\AiNiee-CLI` with `/path/to/AiNiee-CLI`.

2. If your client only accepts a raw command, use:

```bash
uv run --directory /path/to/AiNiee-CLI --isolated --no-project --quiet --with mcp --with fastapi --with uvicorn[standard] --with requests python Tools/MCPServer/server.py --transport stdio
```

3. Codex over `stdio`, preferably via the bundled launcher:

```bash
codex mcp add ainiee-cli -- /path/to/AiNiee-CLI/Tools/MCPServer/codex_stdio_launcher.sh
```

If this is the first startup and dependencies are not cached yet, add a larger timeout in `~/.codex/config.toml`, for example:

```toml
[mcp_servers.ainiee-cli]
startup_timeout_sec = 90
```

4. MCP clients that support `streamable-http` can connect directly to the MCP HTTP route exposed by AiNiee CLI.
Start it first with:

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

or from the main menu with **16. Start MCP Server**.

If the client uses a URL-style configuration, this is a valid reference:

```json
{
  "mcpServers": {
    "ainiee-cli": {
      "transport": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Endpoints:

```text
Local endpoint: http://127.0.0.1:8765/mcp
LAN endpoint: http://<your-lan-ip>:8765/mcp
```

5. If MCP startup reports missing dependencies, run this from the project root:

```bash
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win" && uv --directory "%CD%" add "mcp" "fastapi" "uvicorn[standard]" "requests"
```

On Linux / macOS, use:

```bash
UV_PROJECT_ENVIRONMENT="$(pwd)/.venv" uv --directory "$(pwd)" add 'mcp' 'fastapi' 'uvicorn[standard]' 'requests'
```

If you change `mcp_server_port`, replace `8765` in the route above with the new port.
If the project `.venv` was created under another OS first, for example in WSL and then reused from Windows, recreate `.venv` before running `uv add` to avoid `lib64` / symlink related errors.

**Recommended first MCP calls for LLM clients:**
- `get_mcp_usage_manual`
- `get_mcp_security_policy`
- `get_mcp_tool_catalog`
- `get_mcp_validation_checklist`

These four tools tell the LLM what MCP capabilities are available, how tool parameters are structured, which routes are restricted, and why bypassing MCP is forbidden.

**MCP security requirements:**
- The LLM must not bypass MCP by sending direct HTTP requests to the Web UI, localhost, or LAN ports
- The LLM must use MCP tools only for AiNiee operations
- `api_key` / `access_key` / `secret_key` are redacted on MCP reads
- MCP reads of sensitive config also return `_mcp_security_notice`, explicitly stating that the restriction is permission-based and that bypassing through any other channel is forbidden
- A redacted placeholder is not a usable secret and must not be written back as if it were real
- Sensitive Web API routes require a valid Web UI session cookie or MCP bridge token, so bare unauthenticated HTTP bypass requests are rejected

Full client-facing guide:
- `Tools/MCPServer/MCP_CLIENT_GUIDE.md`

---

## Architecture

This project utilizes a Wrapper / Adapter pattern:

- **Core**: Original AiNiee core business logic unchanged
- **Adapter Layer**: `ainiee_cli.py` handles environment isolation and exception interception
- **Runtime**: Managed by uv for dependency consistency

---

## Manga Reference

The MangaCore subsystem uses a layered design: fully automatic batch translation and manual page refinement are treated as separate workflows instead of being merged into one entry point.

**The fully automatic manga translation workflow** primarily references the workflow represented by `manga-translator-ui-main` and its upstream project **hgmzhn / manga-translator-ui**:

- GitHub: https://github.com/hgmzhn/manga-translator-ui
- Gitee mirror: https://gitee.com/hgmzhn/manga-translator-ui

This part mainly references its staged workflow and runtime asset organization: image/archive import, text detection, OCR, translation, inpainting, text rendering, and final export. In AiNiee-Next, this low-interaction batch workflow is carried by `translate ... --manga`, the Web task page Manga Mode, and the `MangaCore` batch pipeline.

**Manual refinement and manga editor logic** primarily references **mayocream / Koharu**:

- GitHub: https://github.com/mayocream/koharu

This part mainly references Koharu's manual refinement ideas, including project/page/text-block models, layered page states, current-page reruns, text block position and style adjustments, inpaint result inspection, and editable final exports.

If related core modules are referenced, integrated, or reused in later stages, this project will continue to preserve source attribution and acknowledgement, and will comply with the corresponding open-source license terms.

---

## Disclaimer

- This project is an unofficial optimized branch of AiNiee
- Core translation algorithms remain consistent with the original version
- This tool is intended for personal learning and legal use only

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
