# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[简体中文](../README.md) | [English](../README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

**AiNiee-Next**는 [AiNiee](https://github.com/NEKOparapa/AiNiee)의 핵심 로직을 명령줄 환경에 맞게 재구성한 프로젝트입니다. 장시간 실행, 서버 배포, 자동화 워크플로, 안정적인 TUI 사용 경험을 중점으로 합니다.

이 프로젝트는 Python 패키지 관리에 **uv**를 사용하며, IO 스트림, 예외 처리, 작업 복구, 오류 진단, Web 제어 패널을 강화했습니다.

> 매우 죄송합니다. 개발자는 한국어를 이해하지 못하므로 일부 시스템 프롬프트는 사용자가 직접 작성해야 할 수 있습니다. 개발자가 여러 언어의 프롬프트를 지속적으로 유지보수할 여력이 아직 없습니다. 도움을 주실 의향이 있다면 프로젝트에 PR을 보내 주시면 환영합니다.

---

## 주요 기능

- **안정적인 CLI / TUI 실행 환경**: 표준 출력과 오류 출력을 제어하여 의존성 라이브러리 로그로 인한 화면 깨짐을 줄입니다.
- **스마트 오류 진단**: traceback, 실행 환경, 플랫폼, 모델, 최근 작업 흐름을 수집하여 API, 네트워크, 설정, 환경, 코드 문제를 구분하는 데 도움을 줍니다.
- **다양한 형식 지원**: Epub, Docx, Txt, Srt, Ass, Vtt, Lrc, Json, Po, Paratranz 등 20개 이상의 형식을 지원합니다.
- **전자책 변환 흐름**: Calibre와 연동하여 `.mobi`, `.azw3`, `.kepub`, `.fb2` 같은 복잡한 전자책 형식을 처리할 수 있습니다.
- **고동시성 번역**: 실행 중 스레드 수 조정, API Key 전환, 비동기 요청, Provider 기능 감지를 지원합니다.
- **다중 Profile 시스템**: 빠른 번역, 정밀 교정 등 용도별 설정을 만들고 전환할 수 있습니다.
- **Web 대시보드**: 작업 진행률, Profile, 용어집, 큐, 플러그인, 일부 MangaCore 기능을 브라우저에서 관리할 수 있습니다.
- **MCP 서비스**: MCP를 지원하는 LLM 클라이언트가 제어된 도구를 통해 AiNiee-Next 기능을 사용할 수 있습니다.
- **플러그인 구조**: RAG, 번역 검사 등 확장 기능을 사용할 수 있습니다.
- **MangaCore**: 만화 번역 자동 배치 처리와 Web 기반 편집 흐름을 제공합니다.

---

## 빠른 시작

새 사용자는 먼저 영어 또는 중국어 문서를 참고하는 것을 권장합니다.

- [Quick Start Guide](README_QUICK_START_EN.md)
- [DeepSeek API Key Guide](DEEPSEEK_API_KEY_EN.md)
- [Prompt, Glossary, Polishing, and Advanced Settings Guide](TRANSLATION_WORKFLOW_GUIDE_EN.md)

### 방법 1: 원클릭 실행

**1. 코드 받기**

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. 최초 환경 준비**

Windows:

```batch
prepare.bat 더블 클릭
```

Linux / macOS:

```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. 실행**

Windows:

```batch
Launch.bat 더블 클릭
```

Linux / macOS:

```bash
./Launch.sh
```

### 방법 2: 수동 실행

uv 설치:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

코드 받기 및 실행:

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## 명령줄 예시

번역 작업:

```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

큐 작업:

```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

MCP 서버:

```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

주요 인자:

- `translate` / `polish` / `export` / `queue` / `mcp`: 작업 유형
- `-o, --output`: 출력 경로
- `-p, --profile`: Profile 이름
- `-s, --source`: 원문 언어
- `-t, --target`: 대상 언어
- `--type`: Txt, Epub, MTool, RenPy 등 프로젝트 유형
- `--resume`: 캐시된 작업 자동 재개
- `--yes`: 비대화형 모드
- `--threads`: 동시 스레드 수
- `--platform`: API 플랫폼
- `--model`: 모델 이름
- `--api-url`: API URL
- `--api-key`: API Key
- `--mcp-transport`: `stdio` / `streamable-http` / `sse`

---

## Web 대시보드

실행 방법:

1. `uv run ainiee_cli.py`로 메인 메뉴를 엽니다
2. **15. Start Web Server**를 선택합니다
3. 기본 포트 `8000`에서 서비스가 시작되고 브라우저가 열립니다

Web 대시보드에서는 작업 진행률, Profile, 용어집, 큐, 플러그인, 일부 MangaCore 기능을 관리할 수 있습니다.

---

## MCP 서비스

AiNiee-Next는 선택 기능으로 MCP 서버를 제공합니다. MCP 지원 LLM 클라이언트가 프로젝트 기능을 안전하게 조작할 수 있습니다.

실행 예시:

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

연결 주소:

```text
로컬: http://127.0.0.1:8765/mcp
LAN: http://<your-lan-ip>:8765/mcp
```

자세한 문서:

- [MCP Client Guide](../Tools/MCPServer/MCP_CLIENT_GUIDE.md)

---

## 만화 처리 참고

MangaCore의 자동 만화 번역 흐름은 주로 다음 프로젝트를 참고합니다.

- [hgmzhn / manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)

수동 보정 및 만화 편집기 설계는 주로 다음 프로젝트를 참고합니다.

- [mayocream / Koharu](https://github.com/mayocream/koharu)

향후 관련 모듈을 참조, 통합 또는 재사용하는 경우에도 출처와 감사 표시를 유지하고 해당 오픈소스 라이선스를 준수합니다.

---

## 면책 조항

- 이 프로젝트는 AiNiee의 비공식 최적화 브랜치입니다.
- 핵심 번역 로직은 원본 프로젝트와 같은 방향을 유지합니다. 원본 프로젝트의 사용 조건도 확인해 주세요.
- 이 도구는 개인 학습 및 합법적인 용도로만 제공됩니다.

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
