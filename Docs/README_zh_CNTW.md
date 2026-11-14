# AiNiee-Next

[简体中文](../README.md) | [English](README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

AiNiee-Next 是一個基於大型語言模型的批次翻譯工具，支援小說、電子書、文件、字幕、遊戲文字、漫畫以及即時音視訊字幕的處理。

程式核心執行於命令列與終端互動選單（CLI/TUI）中，同時提供網頁控制台、桌面端視窗，以及供外部 AI 用戶端呼叫的 MCP 和 Skills 介面，既可以拿來快速翻譯單本檔案，也適合長篇系列和批次任務的長期處理。

[點此下載最新原始碼 ZIP](https://github.com/ShadowLoveElysia/AiNiee-Next/archive/HEAD.zip) — 下載預設分支目前最新提交的完整原始碼副本。下載後先解壓縮，Windows 使用者進入解壓縮後的專案目錄，依序執行 `Windows prepare.bat` 和 `Windows launch.bat`。

---

## 快速開始

### 1. 安裝基礎環境

專案依賴 Python 3.12 和 `uv` 套件管理器。儲存庫根目錄附有各平台的準備指令碼，首次使用直接執行對應指令碼即可自動設定好基礎環境：

- **Windows**：按兩下執行 `Windows prepare.bat`
- **Linux**：在終端執行 `bash "Linux prepare.sh"`
- **macOS**：按兩下執行 `Mac prepare.command`

如果你只需要翻譯文字、電子書、字幕或遊戲腳本，完成這一步就可以直接開始使用了。漫畫、即時口譯和影片翻譯需要額外的視覺或語音模型環境，用到時再按後面的第 5 步單獨安裝即可。

### 2. 啟動與首次設定

基礎環境就緒後，執行對應平台的啟動指令碼開啟主程式：

- **Windows**：按兩下執行 `Windows launch.bat`
- **Linux**：執行 `bash "Linux launch.sh"`
- **macOS**：按兩下執行 `Mac launch.command`

也可以在專案根目錄直接用命令列啟動：`uv run ainiee_cli.py`。

第一次啟動會進入引導精靈，按提示完成兩步設定即可：

1. 選擇介面語言（支援簡中、繁中、英、日、韓、俄、西 7 種語言）。
2. 選擇翻譯方式：

   - **API 模式（最常用）**：在介面管理裡選擇平台（支援 OpenAI 相容介面、Anthropic、Google、DeepSeek 以及 Sakura / LocalLLM 等本機模型介面），填寫介面位址、API Key 和模型名稱，測試連線成功後儲存。
   - **外部 Agent 模式**：如果你希望直接呼叫外部 AI 助手或程式開發用戶端的額度來翻譯，可按精靈開啟 MCP 或外部接入引導。

### 3. 開始第一個文字或電子書任務

1. 在主選單中選擇輸入檔案或整個資料夾，設定來源語言、目標語言和輸出路徑。
2. 如需使用術語表、角色設定或自訂提示詞，可在規則和提示詞選單中設定並啟用。執行參數和作品規則是分開儲存的，切換不同作品時不用重複修改介面設定。
3. 確認設定後開始翻譯。執行過程中隨時可以暫停、調整並行數或切換備用 Key。
4. 如果中途斷線或手動停止，下次選擇同一個專案並選擇還原快取即可接續處理，已經翻好的部分不會重複請求。
5. 翻譯完成後，可以直接匯出成品，也可以先用內建的終端編輯器或校對功能檢查一遍再匯出。

### 4. 啟動網頁控制台或桌面端

如果你更習慣用瀏覽器操作（尤其是查看統計圖表、分頁編輯快取，或使用漫畫編輯器），可以在終端主選單裡直接啟動 Web 控制台，或在命令列使用桌面端啟動指令碼：

- **Windows**：執行 `Tools\TauriShell\LaunchGUI.bat`
- **Linux / macOS**：執行 `Tools/TauriShell/LaunchGUI.sh`

### 5. 使用漫畫、即時口譯與離線影片功能

這三個模組的推論依賴和模型體積較大，首次使用前需先執行對應的擴充準備指令碼：

- **漫畫翻譯**：

  - 準備環境：Windows 執行 `Windows comic prepare.bat`，Linux/macOS 執行 `Unix comic prepare.sh`。
  - 使用方式：在網頁控制台進入漫畫編輯器進行視覺化編輯和匯出，或透過命令列 `uv run ainiee_cli.py manga <輸入路徑>` 批次執行。

- **即時口譯與離線影片**：

  - 準備環境：Windows 執行 `Windows media prepare.bat`，macOS 執行 `Mac media prepare.command`。如果是在 Linux/WSL 下使用獨立的 vLLM 語音辨識服務，另行執行 `Linux qwen vllm prepare.sh`。
  - 使用方式：可透過主選單進入，或直接執行 `uv run ainiee_cli.py live`（即時字幕，macOS 也可按兩下 `Mac live launch.command`）與 `uv run ainiee_cli.py video`（離線影片）。

---

## 文件與 Wiki

| 主題 | 文件 |
| :--- | :--- |
| 入門 | [圖文快速上手](README_QUICK_START.md) · [DeepSeek API Key 申請](DEEPSEEK_API_KEY.md) |
| 翻譯設定 | [提示詞、術語表、潤飾與軟體設定](TRANSLATION_WORKFLOW_GUIDE.md) |
| 自動化 | [工作流程執行參數與繼承規則](WORKFLOW_RUNTIME_PARAMETERS.md) |
| 即時口譯與影片 | [媒體功能與模型說明](../ModuleFolders/Media/README.md) · [macOS 即時口譯測試指南](MACOS_LIVE_TRANSLATION_TEST.md) |
| MCP | [服務接入](../Tools/MCPServer/README.md) · [用戶端使用指南](../Tools/MCPServer/MCP_CLIENT_GUIDE.md) |
| Skills | [HTTP、CLI 與 Python 呼叫](../Tools/Skills/README.md) |
| Agent | [Headless Agent 使用說明](../Tools/Agent/README.md) |
| 桌面端 | [Tauri 啟動與建置](../Tools/TauriShell/README.md) |
| 擴充開發 | [外掛編寫](../PluginScripts/README.md) · [Reader / Writer 編寫](../ModuleFolders/Domain/FileAccessor/README.md) |
| 遊戲文字 | [StevExtraction 使用說明](../Tools/StevExtraction/使用说明.md) |
| 更新 | [更新日誌](update_log.md) |
| 其他語言 | [简体中文](../README.md) · [English](README_EN.md) · [日本語](README_JA.md) · [한국어](README_KO.md) · [Русский](README_RU.md) · [Español](README_ES.md) |

---

## 主要功能

### 文字、電子書與遊戲在地化

- **按需注入設定**：傳送請求時只比對目前片段裡真正用到的術語和禁翻詞，支援英文詞形變化和詞邊界判斷，減少無關資訊對模型的干擾。
- **角色召回與分卷時間線**：根據前後幾行的名字、別名、敬稱、人稱和口頭禪自動帶出目前在場角色；多卷本小說可以按卷號記錄角色和設定變化，翻譯前幾卷時不會誤用後幾卷才出現的新譯名。
- **多種一致性參考（可選）**：支援同專案重複長句的翻譯記憶參考、基於本機關鍵字比對的歷史譯文參考，以及基於工具呼叫的劇情摘要與人物記憶（開啟記憶模式後為了確保前後順序，會自動切換為單執行緒執行）。
- **容錯與補譯**：自動保護程式碼區塊、佔位符號、換行和首尾空白；收到回覆後檢查行數、編號和外文殘留。一批裡如果只漏譯了少數幾行，會單獨補譯缺失行並放回原位，不用整批重翻。
- **潤飾與校對審閱**：支援獨立潤飾流程、基於規則的符號／佔位符號檢查，以及 AI 校對建議。校對建議記錄了原文指紋，可以在終端或網頁端逐條接受、拒絕或復原，不會誤覆寫你手動改過的譯文。
- **電子書整理工具**：支援異常 EPUB 保守讀取（含正文雜訊與日文注音過濾）、巢狀文字擷取與原書結構內回寫、編碼與宣告同步、譯後目錄及章節標題同步、橫直排切換、解除強制字型與字級、正文段落預設、局部連結修復、圖片壓縮與 WebP 轉換及引用同步、雙語 EPUB、語言與書名中繼資料整理、系列卷號辨識與統一命名、系列中繼資料寫入及批次自動合訂、TXT 自動分章轉 EPUB，以及日譯中引號規範化；支援利用翻譯快取調整匯出設定後重新匯出。另附有系列電子書批次整合指令碼（`Tools/Ebook/批量电子书整合.py`）和遊戲文字擷取工具（`Tools/StevExtraction`）。

### 漫畫翻譯與網頁編輯器

- 支援圖片、資料夾、ZIP/CBZ、RAR/CBR 和 PDF 匯入，串聯對話框與文字偵測、OCR、批次翻譯、底圖修補和自動排版渲染。
- 內建品質攔截檢查，如果某頁出現模型異常降級、缺字或文字溢出，會標記為待人工複查並阻止直接作為成品匯出。
- 網頁端提供完整的圖層編輯器，支援調整文字框位置與樣式、用筆刷重繪修補遮罩、單獨重跑某一頁的某個階段，以及復原／重做。支援匯出圖片、PDF、CBZ、ZIP、EPUB，以及帶圖層的 PSD 檔案（或 JSX 指令碼）。

### 即時口譯與離線影片

- **即時口譯**：擷取系統聲音或指定應用程式處理序樹音訊（Windows 支援只擷取指定軟體或遊戲處理序，不混入其他軟體聲音；macOS 透過原生 Helper 擷取），經過語音分段和本機模型辨識翻譯後，以浮動字幕視窗顯示。附帶實況主術語表和獨立的私密雙向文字互譯視窗。
- **離線影片**：自動擷取音訊並降噪、語音辨識並整理字幕時間軸，支援本機模型與雲端 API 組合使用，最終透過 FFmpeg 封裝 MKV 軟字幕或壓製 MP4 硬字幕。

### 自動化與外部接入

- **佇列、排程與目錄監看**：支援任務佇列（執行中仍可修改尚未開始的排隊項目）、Cron 排程任務，以及資料夾自動監看（偵測到新檔案寫入穩定後自動加入佇列，支援辨識系列卷號順序）。
- **MCP / Skills / Docker**：支援啟動 MCP Server（stdio / streamable-http / SSE）與 Skills HTTP/CLI 服務，可將翻譯推論交給外部 AI 用戶端，由 AiNiee 統一處理檔案讀取、驗證和原子性回寫。容器部署可參考 `Tools/Docker/Dockerfile`。

---

## 命令列常用操作

除了互動式選單，所有核心任務也可以直接透過命令列執行，方便寫進指令碼或配合自動化使用：

```bash
# 翻譯檔案或目錄，指定輸出目錄、語言並自動接續處理
uv run ainiee_cli.py translate INPUT_PATH -o OUTPUT_PATH -s Japanese -t Chinese --resume --yes

# 僅潤飾／翻譯＋潤飾一體／僅從快取匯出成品（不呼叫模型）
uv run ainiee_cli.py polish INPUT_PATH --yes
uv run ainiee_cli.py all_in_one INPUT_PATH --yes
uv run ainiee_cli.py export INPUT_PATH --yes

# 漫畫批次處理（先檢查本機模型和裝置狀態）
uv run ainiee_cli.py manga INPUT_PATH --manga-runtime-check
uv run ainiee_cli.py manga INPUT_PATH --yes

# 直接進入即時口譯或離線影片翻譯
uv run ainiee_cli.py live
uv run ainiee_cli.py video

# 啟動 MCP Server 或 Skills 服務
uv run ainiee_cli.py mcp --mcp-transport stdio
uv run ainiee_cli.py --skills
python Tools/Skills/cli.py list
```

查看全部命令列參數可執行 `uv run ainiee_cli.py --help`。

---

## 支援的檔案格式

| 類別 | 格式 | 說明 |
| :--- | :--- | :--- |
| 純文字 | `.txt`, `.md` | 逐行擷取與回寫，Markdown 會自動跳過純圖片行和參照定義 |
| 電子書 | `.epub` | 解析內部結構與目錄並回寫 |
| 辦公文件 | `.docx`, `.pptx` | 擷取文字節點或文字框段落回寫；PPTX 不辨識圖片內文字，部分段內混合樣式會被簡化 |
| 試算表 | `.csv`, `.xlsx` | CSV 直接讀寫；XLSX 是拆成 CSV 翻完再組合回去的，複雜公式和樣式無法保留，適合純文字表格 |
| 字幕與歌詞 | `.srt`, `.vtt`, `.ass`, `.lrc` | 保留時間軸和樣式標記，只替換正文內容 |
| 在地化專案 | `.po`, `.json` | PO 目前處理單數項目；JSON 自動辨識 i18next、Paratranz、MTool 等結構 |
| 遊戲專案 | Ren'Py, Translator++, VNText | 專用格式擷取與回寫 |
| PDF | `.pdf` | 依賴 BabelDOC 擷取段落與回填排版，掃描文件的效果取決於 OCR 條件 |
| 舊版 Office | `.doc`, `.ppt` 等 | 僅支援 Windows，需要本機安裝 Microsoft Word |
| 其他電子書 | `.mobi`, `.azw3`, `.fb2` 等 | 需啟用並安裝 Calibre，轉換後再處理和轉回 |

---

## 注意事項

1. **影片翻譯範圍**：離線影片流程目前只處理音軌語音，不辨識影片畫面裡的內嵌文字；另外長影片的自動術語擷取目前會把整段轉錄一次傳給模型（尚未實作按預算分段），影片很長時建議手動填寫詞表或使用長上下文模型。
2. **外部工具依賴**：漫畫匯出分層 PSD 需要本機安裝 Photoshop（否則只能匯出 JSX 指令碼）；壓縮與解壓縮 RAR/CBR 格式需要系統環境中存在對應的外部命令列工具。
3. **遠端存取安全**：Web 控制台預設只監聽本機回送位址，內建的工作階段驗證主要用於防止本機介面被跨網站濫用，並非多使用者帳號權限系統。如需遠端存取，請務必在受信任內網使用，或在前端設定反向代理和存取驗證。

---

## 專案參考與鳴謝

- [AiNiee](https://github.com/NEKOparapa/AiNiee)：本專案基於其核心翻譯邏輯開發，感謝原作者 NEKOparapa 及貢獻者。
- [manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)（[Gitee 備份](https://gitee.com/hgmzhn/manga-translator-ui)）：漫畫自動處理流程、階段拆分與執行時資產組織參考。
- [Koharu](https://github.com/mayocream/koharu)：漫畫專案、圖層、文字區塊編輯和人工精修流程參考。

相關來源說明與鳴謝會持續保留，引用與重用遵循各專案的開源授權條款。

---

## 開源授權

本專案基於 GNU Affero General Public License v3.0 (AGPL-3.0) 開源，詳情請參閱根目錄下的 `LICENSE` 檔案。

---

## 支持 AiNiee-Next

如果 AiNiee-Next 對你有幫助，歡迎透過[愛發電](https://ifdian.net/a/Next_ZhiXie)或下方贊助碼支持持續開發與維護。支持者會加入專案鳴謝名單，感謝每一份支持。

<div align="center">
  <img src="Images/赞赏码.png" alt="贊助碼" width="320">
</div>

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
