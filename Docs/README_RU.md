# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[简体中文](../README.md) | [English](../README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

**AiNiee-Next** — это инженерно переработанная версия [AiNiee](https://github.com/NEKOparapa/AiNiee), ориентированная на командную строку, длительные задачи, серверное использование, автоматизацию и стабильный TUI-интерфейс.

Проект использует современный менеджер Python-пакетов **uv** и усиливает обработку IO-потоков, исключений, восстановления задач, диагностики ошибок и Web-панели управления.

> Приносим извинения: разработчик не владеет русским языком, поэтому часть системных промптов может потребовать самостоятельной настройки. У разработчика пока нет возможности полноценно поддерживать промпты на нескольких языках. Если вы готовы помочь, PR в проект будет очень приветствоваться.

---

## Основные возможности

- **Стабильная среда CLI / TUI**: управление stdout и stderr снижает риск поломки интерфейса из-за лишних логов зависимостей.
- **Умная диагностика ошибок**: собирает traceback, окружение, платформу, модель и последние действия, помогая отличать проблемы API, сети, конфигурации, окружения и кода.
- **Множество форматов**: поддерживаются Epub, Docx, Txt, Srt, Ass, Vtt, Lrc, Json, Po, Paratranz и более 20 других форматов.
- **Обработка электронных книг**: интеграция с Calibre помогает работать с `.mobi`, `.azw3`, `.kepub`, `.fb2` и другими сложными форматами.
- **Высокая параллельность**: поддерживаются изменение числа потоков во время работы, ротация API Key, асинхронные запросы и определение возможностей Provider.
- **Система Profile**: можно создавать, копировать и переключать наборы настроек для разных сценариев.
- **Web-панель**: управление прогрессом задач, Profile, глоссарием, очередью, плагинами и частью функций MangaCore.
- **MCP-сервис**: LLM-клиенты с поддержкой MCP могут управлять AiNiee-Next через контролируемые инструменты.
- **Плагины**: поддерживаются RAG, проверка перевода и другие расширения.
- **MangaCore**: автоматическая пакетная обработка манги и Web-процесс для редактирования.

---

## Быстрый старт

Новым пользователям рекомендуется начать с английской или китайской документации:

- [Quick Start Guide](README_QUICK_START_EN.md)
- [DeepSeek API Key Guide](DEEPSEEK_API_KEY_EN.md)
- [Prompt, Glossary, Polishing, and Advanced Settings Guide](TRANSLATION_WORKFLOW_GUIDE_EN.md)

### Способ 1: запуск в один клик

**1. Получить код**

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. Подготовить окружение при первом запуске**

Windows:

```batch
Дважды щелкните prepare.bat
```

Linux / macOS:

```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. Запустить**

Windows:

```batch
Дважды щелкните Launch.bat
```

Linux / macOS:

```bash
./Launch.sh
```

### Способ 2: ручной запуск

Установите uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Получите код и запустите:

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## Примеры командной строки

Задача перевода:

```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

Задача очереди:

```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

MCP-сервер:

```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

Основные параметры:

- `translate` / `polish` / `export` / `queue` / `mcp`: тип задачи
- `-o, --output`: путь вывода
- `-p, --profile`: имя Profile
- `-s, --source`: исходный язык
- `-t, --target`: целевой язык
- `--type`: тип проекта, например Txt, Epub, MTool, RenPy
- `--resume`: автоматическое продолжение из кеша
- `--yes`: неинтерактивный режим
- `--threads`: число параллельных потоков
- `--platform`: API-платформа
- `--model`: имя модели
- `--api-url`: API URL
- `--api-key`: API Key
- `--mcp-transport`: `stdio` / `streamable-http` / `sse`

---

## Web-панель

Как запустить:

1. Выполните `uv run ainiee_cli.py`, чтобы открыть главное меню
2. Выберите **15. Start Web Server**
3. Сервис запустится на порту `8000` по умолчанию и откроет браузер

Web-панель позволяет отслеживать прогресс задач, управлять Profile, глоссарием, очередью, плагинами и частью функций MangaCore.

---

## MCP-сервис

AiNiee-Next предоставляет дополнительный MCP-сервер. LLM-клиенты с поддержкой MCP могут безопасно использовать возможности проекта через инструменты.

Пример запуска:

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

Адреса подключения:

```text
Локально: http://127.0.0.1:8765/mcp
LAN: http://<your-lan-ip>:8765/mcp
```

Подробности:

- [MCP Client Guide](../Tools/MCPServer/MCP_CLIENT_GUIDE.md)

---

## Источники для MangaCore

Автоматический процесс перевода манги в MangaCore в основном опирается на:

- [hgmzhn / manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)

Идеи ручной доработки и редактора манги в основном опираются на:

- [mayocream / Koharu](https://github.com/mayocream/koharu)

Если в будущем проект будет ссылаться, интегрировать или повторно использовать связанные модули, указание источников и соблюдение лицензий будут сохранены.

---

## Отказ от ответственности

- Этот проект является неофициальной оптимизированной веткой AiNiee.
- Основная логика перевода остается согласованной с оригинальным проектом. Пожалуйста, соблюдайте условия использования оригинального проекта.
- Инструмент предназначен только для личного обучения и законного использования.

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
