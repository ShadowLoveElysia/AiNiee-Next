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

**Main Arguments:**
- `translate` / `polish` / `export` / `queue`: Task type
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

## Architecture

This project utilizes a Wrapper / Adapter pattern:

- **Core**: Original AiNiee core business logic unchanged
- **Adapter Layer**: `ainiee_cli.py` handles environment isolation and exception interception
- **Runtime**: Managed by uv for dependency consistency

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
