# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[簡体中文](../README.md) | [English](../README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

**AiNiee-Next** は、[AiNiee](https://github.com/NEKOparapa/AiNiee) のコアロジックをコマンドライン環境向けに再設計した派生プロジェクトです。長時間実行、サーバー運用、自動化ワークフロー、安定した TUI 操作を重視しています。

本プロジェクトは Python パッケージ管理に **uv** を採用し、IO ストリーム、例外処理、タスク復旧、エラー診断、Web コントロールパネルなどを強化しています。

---

## 主な特徴

- **安定した CLI / TUI 実行環境**：標準出力と標準エラーを制御し、依存ライブラリの余計なログによる表示崩れを抑えます。
- **スマート診断**：traceback、実行環境、使用中のプラットフォームとモデル、直近の操作を収集し、API、ネットワーク、設定、環境、コード不具合の切り分けを支援します。
- **多形式対応**：Epub、Docx、Txt、Srt、Ass、Vtt、Lrc、Json、Po、Paratranz など、20 種類以上の形式を扱えます。
- **電子書変換**：Calibre と連携し、`.mobi`、`.azw3`、`.kepub`、`.fb2` などの変換処理を支援します。
- **高並行翻訳**：実行中のスレッド数調整、API Key ローテーション、非同期リクエスト、Provider 機能検出に対応します。
- **複数 Profile**：用途別の設定を作成、複製、切り替えできます。
- **Web ダッシュボード**：タスク監視、設定管理、キュー管理、用語集、プラグイン管理などをブラウザから操作できます。
- **MCP サービス**：MCP 対応 LLM クライアントから、制御されたツール経由で AiNiee-Next を操作できます。
- **プラグイン構成**：RAG、翻訳チェックなどの拡張機能に対応します。
- **MangaCore**：漫画翻訳の自動バッチ処理と Web 編集ワークフローを提供します。

---

## クイックスタート

新規ユーザーは、まず次の英語または中国語ドキュメントを参照してください。

- [Quick Start Guide](README_QUICK_START_EN.md)
- [DeepSeek API Key Guide](DEEPSEEK_API_KEY_EN.md)
- [Prompt, Glossary, Polishing, and Advanced Settings Guide](TRANSLATION_WORKFLOW_GUIDE_EN.md)

### 方法 1：ワンクリック起動

**1. コードを取得**

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. 初回環境セットアップ**

Windows：

```batch
prepare.bat をダブルクリック
```

Linux / macOS：

```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. 起動**

Windows：

```batch
Launch.bat をダブルクリック
```

Linux / macOS：

```bash
./Launch.sh
```

### 方法 2：手動起動

uv をインストール：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

起動：

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## コマンドライン例

翻訳タスク：

```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

キュータスク：

```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

MCP サーバー：

```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

主な引数：

- `translate` / `polish` / `export` / `queue` / `mcp`：タスク種別
- `-o, --output`：出力先
- `-p, --profile`：Profile 名
- `-s, --source`：翻訳元言語
- `-t, --target`：翻訳先言語
- `--type`：Txt、Epub、MTool、RenPy などのプロジェクト種別
- `--resume`：キャッシュから自動再開
- `--yes`：非対話モード
- `--threads`：並行スレッド数
- `--platform`：API プラットフォーム
- `--model`：モデル名
- `--api-url`：API URL
- `--api-key`：API Key
- `--mcp-transport`：`stdio` / `streamable-http` / `sse`

---

## Web ダッシュボード

起動手順：

1. `uv run ainiee_cli.py` を実行してメインメニューを開く
2. **15. Start Web Server** を選択
3. 既定ではポート `8000` でサービスが起動し、ブラウザが開きます

Web ダッシュボードでは、タスク進捗、Profile、用語集、キュー、プラグイン、一部の MangaCore 機能を管理できます。

---

## MCP サービス

AiNiee-Next は任意機能として MCP サーバーを提供します。MCP 対応 LLM クライアントから、プロジェクト機能を安全に操作できます。

起動例：

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

接続先：

```text
ローカル: http://127.0.0.1:8765/mcp
LAN: http://<your-lan-ip>:8765/mcp
```

詳細：

- [MCP Client Guide](../Tools/MCPServer/MCP_CLIENT_GUIDE.md)

---

## 漫画処理の参考元

MangaCore の自動漫画翻訳フローは、主に次のプロジェクトを参考にしています。

- [hgmzhn / manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)

手動修正と漫画エディタの設計は、主に次のプロジェクトを参考にしています。

- [mayocream / Koharu](https://github.com/mayocream/koharu)

今後関連モジュールを参照、統合、再利用する場合も、出典と謝辞を保持し、対応するオープンソースライセンスを遵守します。

---

## 免責事項

- 本プロジェクトは AiNiee の非公式最適化ブランチです。
- コア翻訳ロジックは原版と同じ方針を保っています。原版の利用規約も確認してください。
- 本ツールは個人学習および合法的な用途のために提供されています。

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
