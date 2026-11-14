# AiNiee-Next

[简体中文](../README.md) | [English](README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

AiNiee-Next는 대규모 언어 모델을 기반으로 하는 일괄 번역 도구로, 소설, 전자책, 문서, 자막, 게임 텍스트, 만화 및 실시간 오디오·비디오 자막을 처리할 수 있습니다.

명령줄과 대화형 터미널 메뉴(CLI/TUI)를 중심으로 실행되며, 웹 대시보드, 데스크톱 창, 외부 AI 클라이언트가 호출할 수 있는 MCP 및 Skills 인터페이스도 제공합니다. 단일 파일을 빠르게 번역하는 데에도, 장편 시리즈와 일괄 작업을 장기간 처리하는 데에도 사용할 수 있습니다.

[최신 소스 코드 ZIP 다운로드](https://github.com/ShadowLoveElysia/AiNiee-Next/archive/HEAD.zip) — 기본 브랜치의 최신 커밋에 해당하는 전체 소스 코드를 다운로드합니다. 먼저 압축을 푼 뒤, Windows 사용자는 압축을 푼 프로젝트 폴더에서 `Windows prepare.bat`, `Windows launch.bat` 순서로 실행하세요.

---

## 빠른 시작

### 1. 기본 환경 설치

이 프로젝트에는 Python 3.12와 `uv` 패키지 관리자가 필요합니다. 저장소 루트에 플랫폼별 준비 스크립트가 포함되어 있으므로 처음 사용할 때 해당 스크립트를 실행하면 기본 환경이 자동으로 구성됩니다.

- **Windows**: `Windows prepare.bat`를 더블 클릭합니다.
- **Linux**: 터미널에서 `bash "Linux prepare.sh"`를 실행합니다.
- **macOS**: `Mac prepare.command`를 더블 클릭합니다.

텍스트, 전자책, 자막 또는 게임 스크립트만 번역한다면 이 단계가 끝난 후 바로 사용할 수 있습니다. 만화, 실시간 통역, 동영상 번역에는 추가적인 비전 또는 음성 모델 환경이 필요하므로, 사용할 때 아래 5단계에 따라 별도로 설치하면 됩니다.

### 2. 실행 및 초기 설정

기본 환경이 준비되면 플랫폼에 맞는 실행 스크립트로 프로그램을 엽니다.

- **Windows**: `Windows launch.bat`를 더블 클릭합니다.
- **Linux**: `bash "Linux launch.sh"`를 실행합니다.
- **macOS**: `Mac launch.command`를 더블 클릭합니다.

프로젝트 루트에서 명령줄로 `uv run ainiee_cli.py`를 실행해도 됩니다.

처음 실행하면 설정 마법사가 열립니다. 안내에 따라 두 단계를 완료하세요.

1. 인터페이스 언어를 선택합니다(중국어 간체·번체, 영어, 일본어, 한국어, 러시아어, 스페인어의 7개 언어 지원).
2. 번역 방식을 선택합니다.

   - **API 모드(가장 일반적)**: API 관리에서 플랫폼을 선택합니다. OpenAI 호환 API, Anthropic, Google, DeepSeek 및 Sakura / LocalLLM 등의 로컬 모델 인터페이스를 지원합니다. API 주소, API 키, 모델 이름을 입력하고 연결을 테스트한 뒤 저장합니다.
   - **외부 Agent 모드**: 외부 AI 어시스턴트나 코딩 클라이언트의 사용 한도로 번역하려면 마법사 안내에 따라 MCP 또는 외부 연동 안내를 활성화하세요.

### 3. 첫 텍스트 또는 전자책 작업 시작

1. 메인 메뉴에서 입력 파일 또는 전체 폴더를 선택하고 원문 언어, 대상 언어, 출력 경로를 설정합니다.
2. 용어집, 캐릭터 설정 또는 사용자 지정 프롬프트가 필요하면 규칙 및 프롬프트 메뉴에서 설정하고 활성화합니다. 실행 매개변수와 작품별 규칙은 별도로 저장되므로 작품을 바꿀 때 API 설정을 다시 변경할 필요가 없습니다.
3. 설정을 확인한 뒤 번역을 시작합니다. 실행 중에도 언제든지 일시 중지하거나 동시 실행 수를 조정하고 예비 키로 전환할 수 있습니다.
4. 연결이 끊기거나 수동으로 중지한 경우, 다음에 같은 프로젝트를 선택하고 캐시를 복원하면 중단한 지점부터 재개할 수 있습니다. 이미 번역된 부분은 다시 요청하지 않습니다.
5. 번역이 완료되면 바로 내보내거나, 내장 터미널 편집기 또는 교정 기능으로 확인한 후 내보낼 수 있습니다.

### 4. 웹 대시보드 또는 데스크톱 앱 실행

브라우저 사용이 더 익숙하다면, 특히 통계 차트 확인, 페이지별 캐시 편집, 만화 편집기 사용 시 터미널 메인 메뉴에서 웹 대시보드를 바로 실행할 수 있습니다. 명령줄에서 데스크톱 실행 스크립트를 사용해도 됩니다.

- **Windows**: `Tools\TauriShell\LaunchGUI.bat`를 실행합니다.
- **Linux / macOS**: `Tools/TauriShell/LaunchGUI.sh`를 실행합니다.

### 5. 만화, 실시간 통역 및 오프라인 동영상 기능 사용

이 세 모듈은 추론 의존성과 모델의 용량이 크므로 처음 사용하기 전에 해당 확장 환경 준비 스크립트를 실행해야 합니다.

- **만화 번역**:

  - 환경 준비: Windows에서는 `Windows comic prepare.bat`, Linux/macOS에서는 `Unix comic prepare.sh`를 실행합니다.
  - 사용 방법: 웹 대시보드에서 만화 편집기를 열어 시각적으로 편집하고 내보내거나, `uv run ainiee_cli.py manga <INPUT_PATH>` 명령으로 일괄 처리합니다.

- **실시간 통역 및 오프라인 동영상**:

  - 환경 준비: Windows에서는 `Windows media prepare.bat`, macOS에서는 `Mac media prepare.command`를 실행합니다. Linux/WSL에서 독립형 vLLM 음성 인식 서비스를 사용한다면 `Linux qwen vllm prepare.sh`도 별도로 실행합니다.
  - 사용 방법: 메인 메뉴에서 열거나, `uv run ainiee_cli.py live`(실시간 자막, macOS에서는 `Mac live launch.command`를 더블 클릭해도 실행 가능)와 `uv run ainiee_cli.py video`(오프라인 동영상)를 직접 실행합니다.

---

## 문서 및 Wiki

| 주제 | 문서 |
| :--- | :--- |
| 입문 | [이미지로 보는 빠른 시작](README_QUICK_START_EN.md) · [DeepSeek API 키 발급](DEEPSEEK_API_KEY_EN.md) |
| 번역 설정 | [프롬프트, 용어집, 윤문 및 소프트웨어 설정](TRANSLATION_WORKFLOW_GUIDE_EN.md) |
| 자동화 | [워크플로 실행 매개변수 및 상속 규칙](WORKFLOW_RUNTIME_PARAMETERS.md) |
| 실시간 통역 및 동영상 | [미디어 기능 및 모델 안내](../ModuleFolders/Media/README.md) · [macOS 실시간 통역 테스트 가이드](MACOS_LIVE_TRANSLATION_TEST.md) |
| MCP | [서비스 연동](../Tools/MCPServer/README.md) · [클라이언트 사용 가이드](../Tools/MCPServer/MCP_CLIENT_GUIDE.md) |
| Skills | [HTTP, CLI 및 Python 호출](../Tools/Skills/README.md) |
| Agent | [Headless Agent 사용 안내](../Tools/Agent/README.md) |
| 데스크톱 | [Tauri 실행 및 빌드](../Tools/TauriShell/README.md) |
| 확장 개발 | [플러그인 작성](../PluginScripts/README.md) · [Reader / Writer 작성](../ModuleFolders/Domain/FileAccessor/README.md) |
| 게임 텍스트 | [StevExtraction 사용 안내](../Tools/StevExtraction/使用说明.md) |
| 업데이트 | [변경 이력](update_log.md) |
| 다른 언어 | [简体中文](../README.md) · [English](README_EN.md) · [繁體中文](README_zh_CNTW.md) · [日本語](README_JA.md) · [Русский](README_RU.md) · [Español](README_ES.md) |

---

## 주요 기능

### 텍스트, 전자책 및 게임 현지화

- **필요한 설정만 주입**: 요청을 보낼 때 현재 구간에 실제로 등장하는 용어와 번역 금지어만 매칭합니다. 영어 어형 변화와 단어 경계 판정을 지원해 무관한 정보가 모델에 주는 간섭을 줄입니다.
- **캐릭터 정보 검색 및 권별 타임라인**: 앞뒤 몇 줄의 이름, 별명, 경칭, 인칭, 말버릇을 바탕으로 현재 등장하는 캐릭터 정보를 자동으로 불러옵니다. 여러 권으로 된 소설은 권 번호별로 캐릭터와 설정의 변화를 기록할 수 있어, 앞 권 번역에 뒷 권에서 처음 등장하는 번역명이 잘못 적용되는 것을 방지합니다.
- **다양한 일관성 참조(선택 사항)**: 같은 프로젝트에서 반복되는 긴 문장의 번역 메모리, 로컬 키워드 매칭을 통한 과거 번역 참조, 도구 호출을 통한 줄거리 요약과 인물 기억을 지원합니다. 기억 모드를 활성화하면 앞뒤 순서를 유지하기 위해 자동으로 단일 스레드 실행으로 전환됩니다.
- **오류 대응 및 누락 번역 보완**: 코드 블록, 자리표시자, 줄바꿈, 앞뒤 공백을 자동으로 보호하며, 응답을 받은 뒤 줄 수, 번호, 외국어 잔존 여부를 검사합니다. 한 배치에서 몇 줄만 누락되었다면 해당 줄만 별도로 번역해 원래 위치에 넣으므로 전체 배치를 다시 번역할 필요가 없습니다.
- **윤문 및 교정 검토**: 독립적인 윤문 흐름, 규칙 기반 기호·자리표시자 검사, AI 교정 제안을 지원합니다. 교정 제안에는 원문 지문이 기록되며, 터미널이나 웹에서 하나씩 수락, 거부, 취소할 수 있어 수동으로 수정한 번역을 잘못 덮어쓰지 않습니다.
- **전자책 정리 도구**: 비정상 EPUB의 보수적 읽기(본문 노이즈 및 일본어 루비 주석 필터링 포함), 중첩 텍스트 추출 및 원래 책 구조에 번역 쓰기, 인코딩과 선언 동기화, 번역 후 목차·장 제목 동기화, 가로쓰기·세로쓰기 전환, 강제 글꼴·글자 크기 해제, 본문 문단 프리셋, 로컬 링크 복구, 이미지 압축 및 WebP 변환과 참조 동기화, 이중 언어 EPUB, 언어·책 제목 메타데이터 정리, 시리즈 권 번호 인식 및 이름 통일, 시리즈 메타데이터 기록 및 일괄 자동 합본, TXT 자동 장 구분 및 EPUB 변환, 일본어→중국어 번역의 인용 부호 정규화를 지원합니다. 번역 캐시를 이용해 내보내기 설정을 바꾼 뒤 다시 내보낼 수도 있습니다. 전자책 시리즈 일괄 통합 스크립트(`Tools/Ebook/批量电子书整合.py`)와 게임 텍스트 추출 도구(`Tools/StevExtraction`)도 포함되어 있습니다.

### 만화 번역 및 웹 편집기

- 이미지, 폴더, ZIP/CBZ, RAR/CBR 및 PDF 가져오기를 지원하며, 말풍선·텍스트 감지, OCR, 일괄 번역, 배경 복원, 자동 조판·렌더링을 연결합니다.
- 내장 품질 검사에서 모델의 비정상적인 성능 저하, 글자 누락, 텍스트 넘침이 발견된 페이지는 수동 검토 대상으로 표시하고 완성본으로 바로 내보내지 못하게 합니다.
- 웹에서는 텍스트 상자 위치·스타일 조정, 브러시로 복원 마스크 다시 그리기, 특정 페이지의 특정 단계만 재실행, 실행 취소·다시 실행이 가능한 레이어 편집기를 제공합니다. 이미지, PDF, CBZ, ZIP, EPUB 및 레이어가 있는 PSD 파일(또는 JSX 스크립트)로 내보낼 수 있습니다.

### 실시간 통역 및 오프라인 동영상

- **실시간 통역**: 시스템 오디오 또는 지정한 애플리케이션 프로세스 트리의 오디오를 캡처합니다. Windows에서는 다른 프로그램 소리를 섞지 않고 특정 소프트웨어나 게임 프로세스만 캡처할 수 있으며, macOS에서는 네이티브 Helper로 캡처합니다. 음성 분할과 로컬 모델의 인식·번역을 거쳐 플로팅 자막 창에 표시합니다. 스트리머 용어집과 독립된 비공개 양방향 텍스트 번역 창도 제공합니다.
- **오프라인 동영상**: 오디오 자동 추출과 잡음 제거, 음성 인식, 자막 타임라인 정리를 수행합니다. 로컬 모델과 클라우드 API를 조합할 수 있으며, 최종적으로 FFmpeg를 통해 소프트 자막이 있는 MKV 또는 자막을 영상에 입힌 MP4를 만듭니다.

### 자동화 및 외부 연동

- **큐, 예약 실행 및 폴더 감시**: 작업 큐(실행 중에도 아직 시작하지 않은 대기 항목 수정 가능), Cron 예약 작업, 폴더 자동 감시를 지원합니다. 새 파일의 쓰기가 안정되면 자동으로 큐에 추가하며, 시리즈 권 번호 순서도 인식합니다.
- **MCP / Skills / Docker**: MCP Server(stdio / streamable-http / SSE)와 Skills HTTP/CLI 서비스를 실행할 수 있습니다. 번역 추론은 외부 AI 클라이언트에 맡기고, 파일 읽기, 검증, 원자적 쓰기는 AiNiee가 통합 처리합니다. 컨테이너 배포는 `Tools/Docker/Dockerfile`을 참고하세요.

---

## 자주 사용하는 명령줄 작업

대화형 메뉴 외에도 모든 핵심 작업을 명령줄에서 직접 실행할 수 있어 스크립트 작성이나 자동화에 활용하기 편리합니다.

```bash
# 파일 또는 폴더 번역, 출력 경로와 언어 지정 및 자동 재개
uv run ainiee_cli.py translate INPUT_PATH -o OUTPUT_PATH -s Japanese -t Chinese --resume --yes

# 윤문만 / 번역과 윤문 / 캐시에서 내보내기만(모델 호출 없음)
uv run ainiee_cli.py polish INPUT_PATH --yes
uv run ainiee_cli.py all_in_one INPUT_PATH --yes
uv run ainiee_cli.py export INPUT_PATH --yes

# 만화 일괄 처리(먼저 로컬 모델과 장치 상태 확인)
uv run ainiee_cli.py manga INPUT_PATH --manga-runtime-check
uv run ainiee_cli.py manga INPUT_PATH --yes

# 실시간 통역 또는 오프라인 동영상 번역 바로 열기
uv run ainiee_cli.py live
uv run ainiee_cli.py video

# MCP Server 또는 Skills 서비스 실행
uv run ainiee_cli.py mcp --mcp-transport stdio
uv run ainiee_cli.py --skills
python Tools/Skills/cli.py list
```

모든 명령줄 매개변수는 `uv run ainiee_cli.py --help`로 확인할 수 있습니다.

---

## 지원 파일 형식

| 분류 | 형식 | 설명 |
| :--- | :--- | :--- |
| 일반 텍스트 | `.txt`, `.md` | 줄별로 추출하고 다시 기록하며, Markdown은 이미지만 있는 줄과 참조 정의를 자동으로 건너뜁니다 |
| 전자책 | `.epub` | 내부 구조와 목차를 분석한 뒤 번역을 기록합니다 |
| Office 문서 | `.docx`, `.pptx` | 텍스트 노드나 텍스트 상자의 문단을 추출해 기록합니다. PPTX의 이미지 속 텍스트는 인식하지 않으며, 문단 내 일부 혼합 서식은 단순화됩니다 |
| 스프레드시트 | `.csv`, `.xlsx` | CSV는 직접 읽고 씁니다. XLSX는 CSV로 나누어 번역한 뒤 다시 조합하므로 복잡한 수식과 서식은 보존되지 않습니다. 단순 텍스트 표에 적합합니다 |
| 자막 및 가사 | `.srt`, `.vtt`, `.ass`, `.lrc` | 타임라인과 스타일 태그를 유지하고 본문만 바꿉니다 |
| 현지화 프로젝트 | `.po`, `.json` | PO는 현재 단수 항목을 처리하며, JSON은 i18next, Paratranz, MTool 등의 구조를 자동으로 인식합니다 |
| 게임 프로젝트 | Ren'Py, Translator++, VNText | 전용 형식 추출 및 쓰기 |
| PDF | `.pdf` | BabelDOC으로 문단을 추출하고 레이아웃에 다시 기록합니다. 스캔 문서의 결과는 OCR 조건에 따라 달라집니다 |
| 구형 Office | `.doc`, `.ppt` 등 | Windows만 지원하며 로컬에 Microsoft Word가 설치되어 있어야 합니다 |
| 기타 전자책 | `.mobi`, `.azw3`, `.fb2` 등 | Calibre를 설치하고 활성화해야 하며, 변환 후 처리하고 다시 원래 형식으로 변환합니다 |

---

## 참고 사항

1. **동영상 번역 범위**: 오프라인 동영상 흐름은 현재 오디오 트랙의 음성만 처리하며, 영상에 포함된 텍스트는 인식하지 않습니다. 또한 긴 동영상의 자동 용어 추출은 현재 전체 전사문을 한 번에 모델로 전송합니다(예산에 따른 분할 처리는 아직 구현되지 않음). 매우 긴 영상은 용어집을 직접 입력하거나 긴 컨텍스트를 지원하는 모델을 사용하는 것이 좋습니다.
2. **외부 도구 의존성**: 만화를 레이어가 있는 PSD로 내보내려면 로컬에 Photoshop이 설치되어 있어야 하며, 없으면 JSX 스크립트만 내보낼 수 있습니다. RAR/CBR 압축과 압축 해제에는 해당 외부 명령줄 도구가 시스템에 있어야 합니다.
3. **원격 접근 보안**: 웹 대시보드는 기본적으로 로컬 루프백 주소에서만 수신합니다. 내장 세션 검증은 주로 로컬 API의 교차 사이트 악용을 방지하기 위한 것으로, 다중 사용자 계정·권한 시스템이 아닙니다. 원격 접근 시에는 신뢰할 수 있는 내부망에서 사용하거나, 앞단에 리버스 프록시와 접근 인증을 설정하세요.

---

## 참고 프로젝트 및 감사의 말

- [AiNiee](https://github.com/NEKOparapa/AiNiee): 이 프로젝트는 AiNiee의 핵심 번역 로직을 기반으로 개발했습니다. 원작자 NEKOparapa와 기여자 여러분께 감사드립니다.
- [manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)([Gitee 미러](https://gitee.com/hgmzhn/manga-translator-ui)): 만화 자동 처리 흐름, 단계 분리, 런타임 리소스 구성을 참고했습니다.
- [Koharu](https://github.com/mayocream/koharu): 만화 프로젝트, 레이어, 텍스트 블록 편집 및 수동 보정 흐름을 참고했습니다.

관련 출처 설명과 감사 표기는 계속 유지하며, 인용과 재사용은 각 프로젝트의 오픈 소스 라이선스를 따릅니다.

---

## 라이선스

이 프로젝트는 GNU Affero General Public License v3.0(AGPL-3.0)에 따라 공개됩니다. 자세한 내용은 루트 디렉터리의 `LICENSE` 파일을 참고하세요.

---

## AiNiee-Next 후원

AiNiee-Next가 도움이 되었다면 [Afdian](https://ifdian.net/a/Next_ZhiXie) 또는 아래 후원 QR 코드를 통해 지속적인 개발과 유지보수를 지원할 수 있습니다. 후원자는 프로젝트 감사 목록에 추가됩니다. 모든 후원에 감사드립니다.

<div align="center">
  <img src="Images/赞赏码.png" alt="후원 QR 코드" width="320">
</div>

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
