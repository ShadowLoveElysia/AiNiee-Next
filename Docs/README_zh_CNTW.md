# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[簡體中文](../README.md) | [English](../README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

**AiNiee-Next** 是針對 [AiNiee](https://github.com/NEKOparapa/AiNiee) 核心邏輯進行工程化重構的命令列版本，重點是長時間執行、伺服器部署、自動化流程，以及更穩定的 TUI 操作體驗。

本專案使用現代 Python 套件管理工具 **uv** 管理執行環境，並對 IO 串流、例外處理、任務恢復、錯誤診斷與 Web 控制面板做了大量穩定性強化。

---

## 主要特色

- **穩定的 CLI / TUI 執行環境**：接管標準輸出與錯誤輸出，降低第三方套件雜訊造成的介面錯亂。
- **智慧錯誤診斷**：收集 traceback、平台、模型、最近操作等資訊，協助判斷問題來自 API、網路、設定、環境或程式本身。
- **多格式翻譯**：支援 Epub、Docx、Txt、Srt、Ass、Vtt、Lrc、Json、Po、Paratranz 等多種格式。
- **電子書轉換流程**：可搭配 Calibre 處理 `.mobi`、`.azw3`、`.kepub`、`.fb2` 等格式。
- **高併發翻譯**：支援即時調整執行緒數、API Key 輪換、非同步請求模式與 Provider 能力偵測。
- **多設定檔系統**：可建立、複製、切換不同 Profile，分別管理快速翻譯、精修潤色等場景。
- **Web 控制面板**：提供任務監看、設定管理、佇列管理、術語表、外掛管理等功能。
- **MCP 服務**：可讓支援 MCP 的 LLM 客戶端透過受控工具操作 AiNiee-Next，而不是直接呼叫 Web API。
- **外掛架構**：支援 RAG、翻譯檢查等功能擴充。
- **漫畫處理流程**：提供 MangaCore 自動跑批與 Web 編輯流程，用於漫畫翻譯預處理與成品輸出。

---

## 快速開始

新使用者建議先閱讀：

- [圖文快速上手教程](README_QUICK_START.md)
- [DeepSeek API Key 申請教程](DEEPSEEK_API_KEY.md)
- [提示詞、術語表、潤色與軟體設定教程](TRANSLATION_WORKFLOW_GUIDE.md)

### 方式一：一鍵啟動

**1. 取得程式碼**

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. 首次準備環境**

Windows：

```batch
雙擊 prepare.bat
```

Linux / macOS：

```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. 啟動**

Windows：

```batch
雙擊 Launch.bat
```

Linux / macOS：

```bash
./Launch.sh
```

### 方式二：手動啟動

安裝 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell 可使用：

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

取得程式碼並啟動：

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## 命令列範例

翻譯任務：

```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

佇列任務：

```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

MCP 服務：

```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

常用參數：

- `translate` / `polish` / `export` / `queue` / `mcp`：任務類型
- `-o, --output`：輸出路徑
- `-p, --profile`：設定檔名稱
- `-s, --source`：來源語言
- `-t, --target`：目標語言
- `--type`：專案類型，例如 Txt、Epub、MTool、RenPy
- `--resume`：自動恢復快取任務
- `--yes`：非互動模式
- `--threads`：併發執行緒數
- `--platform`：API 平台
- `--model`：模型名稱
- `--api-url`：API 位址
- `--api-key`：API 金鑰
- `--mcp-transport`：MCP 傳輸模式，可選 `stdio` / `streamable-http` / `sse`

---

## Web 控制面板

啟動方式：

1. 執行 `uv run ainiee_cli.py` 進入主選單
2. 選擇 **15. Start Web Server**
3. 程式會啟動服務，預設連接埠為 `8000`，並自動開啟瀏覽器

Web 控制面板可用於查看任務進度、管理 Profile、編輯術語表、管理佇列、控制外掛，以及操作部分 MangaCore 功能。

---

## MCP 服務

AiNiee-Next 提供可選 MCP 服務，讓支援 MCP 的 LLM 客戶端透過受控工具操作專案能力。

啟動範例：

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

連線位址：

```text
本機位址: http://127.0.0.1:8765/mcp
區域網路位址: http://<你的區域網路 IP>:8765/mcp
```

完整說明請參考：

- [MCP 客戶端指南](../Tools/MCPServer/MCP_CLIENT_GUIDE.md)

---

## 漫畫處理參考

MangaCore 的自動漫畫翻譯流程主要參考：

- [hgmzhn / manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)

人工精修與漫畫編輯器思路主要參考：

- [mayocream / Koharu](https://github.com/mayocream/koharu)

後續若接入或復用相關核心模組，專案會持續保留來源說明與致謝資訊，並遵守對應開源協議。

---

## 免責聲明

- 本專案是 AiNiee 的非官方最佳化分支，重點在執行體驗與工程穩定性。
- 核心翻譯邏輯與原版保持一致，請遵守原版使用協議。
- 本工具僅供個人學習與合法用途使用。

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
