# AiNiee-Next

<div align="center">
  <img src="https://img.shields.io/badge/Interface-CLI%20%2F%20TUI-0078D4?style=for-the-badge&logo=windows-terminal&logoColor=white" alt="CLI">
  <img src="https://img.shields.io/badge/Runtime-uv-purple?style=for-the-badge&logo=python&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge" alt="Status">
</div>

<br/>

[简体中文](../README.md) | [English](../README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

**AiNiee-Next** es una versión de línea de comandos basada en una refactorización de ingeniería de la lógica central de [AiNiee](https://github.com/NEKOparapa/AiNiee). Está pensada para tareas largas, servidores, flujos automatizados y una experiencia TUI más estable.

El proyecto usa **uv** como gestor moderno de paquetes de Python y refuerza el manejo de flujos IO, excepciones, recuperación de tareas, diagnóstico de errores y panel Web.

> Lo sentimos mucho: el desarrollador no habla español, por lo que algunos prompts del sistema pueden requerir que los escriba o ajuste usted mismo. El desarrollador no tiene por ahora capacidad para mantener prompts en varios idiomas. Si desea colaborar, los PR al proyecto son bienvenidos.

---

## Funciones principales

- **Entorno CLI / TUI estable**: controla stdout y stderr para reducir problemas visuales causados por logs de dependencias.
- **Diagnóstico inteligente de errores**: recopila traceback, entorno, plataforma, modelo y acciones recientes para distinguir problemas de API, red, configuración, entorno o código.
- **Soporte multiformato**: Epub, Docx, Txt, Srt, Ass, Vtt, Lrc, Json, Po, Paratranz y más de 20 formatos.
- **Flujo para ebooks**: integración con Calibre para manejar `.mobi`, `.azw3`, `.kepub`, `.fb2` y otros formatos complejos.
- **Alto rendimiento concurrente**: ajuste de hilos durante la ejecución, rotación de API Key, modo asíncrono y detección de capacidades del Provider.
- **Sistema de Profile**: permite crear, clonar y cambiar configuraciones para distintos escenarios.
- **Panel Web**: gestión de progreso, Profile, glosario, cola, plugins y parte de las funciones de MangaCore.
- **Servicio MCP**: clientes LLM compatibles con MCP pueden usar AiNiee-Next mediante herramientas controladas.
- **Arquitectura de plugins**: soporte para RAG, revisión de traducción y otras extensiones.
- **MangaCore**: flujo automático por lotes y edición Web para traducción de manga.

---

## Inicio rápido

Se recomienda a los usuarios nuevos empezar con la documentación en inglés o chino:

- [Quick Start Guide](README_QUICK_START_EN.md)
- [DeepSeek API Key Guide](DEEPSEEK_API_KEY_EN.md)
- [Prompt, Glossary, Polishing, and Advanced Settings Guide](TRANSLATION_WORKFLOW_GUIDE_EN.md)

### Método 1: inicio con un clic

**1. Obtener el código**

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
```

**2. Preparar el entorno por primera vez**

Windows:

```batch
Doble clic en prepare.bat
```

Linux / macOS:

```bash
chmod +x prepare.sh && ./prepare.sh
```

**3. Iniciar**

Windows:

```batch
Doble clic en Launch.bat
```

Linux / macOS:

```bash
./Launch.sh
```

### Método 2: configuración manual

Instale uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Obtenga el código e inicie:

```bash
git clone https://github.com/ShadowLoveElysia/AiNiee-Next.git
cd AiNiee-Next
uv run ainiee_cli.py
```

---

## Ejemplos de línea de comandos

Tarea de traducción:

```bash
uv run ainiee_cli.py translate input.txt -o output_dir -p MyProfile -s Japanese -t Chinese --resume --yes
```

Tarea de cola:

```bash
uv run ainiee_cli.py queue --queue-file my_queue.json --yes
```

Servidor MCP:

```bash
uv run ainiee_cli.py mcp --mcp-transport stdio
```

Argumentos principales:

- `translate` / `polish` / `export` / `queue` / `mcp`: tipo de tarea
- `-o, --output`: ruta de salida
- `-p, --profile`: nombre del Profile
- `-s, --source`: idioma de origen
- `-t, --target`: idioma destino
- `--type`: tipo de proyecto, como Txt, Epub, MTool o RenPy
- `--resume`: reanudar automáticamente desde caché
- `--yes`: modo no interactivo
- `--threads`: número de hilos concurrentes
- `--platform`: plataforma API
- `--model`: nombre del modelo
- `--api-url`: URL de API
- `--api-key`: API Key
- `--mcp-transport`: `stdio` / `streamable-http` / `sse`

---

## Panel Web

Cómo iniciarlo:

1. Ejecute `uv run ainiee_cli.py` para abrir el menú principal
2. Seleccione **15. Start Web Server**
3. El servicio se iniciará en el puerto `8000` por defecto y abrirá el navegador

El panel Web permite revisar el progreso de tareas, administrar Profile, glosario, cola, plugins y algunas funciones de MangaCore.

---

## Servicio MCP

AiNiee-Next ofrece un servidor MCP opcional. Los clientes LLM compatibles con MCP pueden usar funciones del proyecto mediante herramientas controladas.

Ejemplo:

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

Direcciones:

```text
Local: http://127.0.0.1:8765/mcp
LAN: http://<your-lan-ip>:8765/mcp
```

Más información:

- [MCP Client Guide](../Tools/MCPServer/MCP_CLIENT_GUIDE.md)

---

## Referencias de MangaCore

El flujo automático de traducción de manga se basa principalmente en:

- [hgmzhn / manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)

La lógica de edición manual y refinamiento de manga se basa principalmente en:

- [mayocream / Koharu](https://github.com/mayocream/koharu)

Si en el futuro se referencian, integran o reutilizan módulos relacionados, el proyecto mantendrá la atribución y cumplirá las licencias correspondientes.

---

## Aviso legal

- Este proyecto es una rama no oficial optimizada de AiNiee.
- La lógica central de traducción se mantiene alineada con el proyecto original. Respete también las condiciones de uso del proyecto original.
- Esta herramienta se ofrece solo para aprendizaje personal y usos legales.

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
