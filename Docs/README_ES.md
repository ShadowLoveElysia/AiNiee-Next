# AiNiee-Next

[简体中文](../README.md) | [English](README_EN.md) | [繁體中文](README_zh_CNTW.md) | [日本語](README_JA.md) | [한국어](README_KO.md) | [Русский](README_RU.md) | [Español](README_ES.md)

AiNiee-Next es una herramienta de traducción por lotes basada en grandes modelos de lenguaje. Permite procesar novelas, libros electrónicos, documentos, subtítulos, textos de juegos, manga y subtítulos de audio y vídeo en tiempo real.

Su núcleo funciona mediante la línea de comandos y menús interactivos de terminal (CLI/TUI). También ofrece un panel web, una ventana de escritorio e interfaces MCP y Skills para clientes de IA externos. Sirve tanto para traducir rápidamente un solo archivo como para procesar series extensas y tareas por lotes de forma continuada.

[Descargar el ZIP con el código fuente más reciente](https://github.com/ShadowLoveElysia/AiNiee-Next/archive/HEAD.zip) — Descarga una copia completa del código fuente del último commit de la rama predeterminada. Descomprime el archivo primero; en Windows, abre la carpeta del proyecto extraído y ejecuta `Windows prepare.bat` y después `Windows launch.bat`.

---

## Inicio rápido

### 1. Instalar el entorno básico

El proyecto requiere Python 3.12 y el gestor de paquetes `uv`. La raíz del repositorio incluye scripts de preparación para cada plataforma. La primera vez, ejecuta el script correspondiente para configurar automáticamente el entorno básico:

- **Windows**: haz doble clic en `Windows prepare.bat`.
- **Linux**: ejecuta `bash "Linux prepare.sh"` en una terminal.
- **macOS**: haz doble clic en `Mac prepare.command`.

Si solo necesitas traducir textos, libros electrónicos, subtítulos o guiones de juegos, puedes empezar a usar el programa tras este paso. El manga, la interpretación en tiempo real y la traducción de vídeo requieren entornos adicionales para modelos de visión o voz; instálalos por separado siguiendo el paso 5 cuando los necesites.

### 2. Iniciar y configurar por primera vez

Una vez preparado el entorno básico, abre el programa con el script de inicio de tu plataforma:

- **Windows**: haz doble clic en `Windows launch.bat`.
- **Linux**: ejecuta `bash "Linux launch.sh"`.
- **macOS**: haz doble clic en `Mac launch.command`.

También puedes iniciarlo desde la línea de comandos en la raíz del proyecto: `uv run ainiee_cli.py`.

En el primer inicio se abrirá el asistente de configuración. Sigue sus indicaciones para completar dos pasos:

1. Selecciona el idioma de la interfaz (se admiten siete: chino simplificado, chino tradicional, inglés, japonés, coreano, ruso y español).
2. Selecciona el método de traducción:

   - **Modo API (el más habitual)**: selecciona una plataforma en la gestión de API. Se admiten API compatibles con OpenAI, Anthropic, Google, DeepSeek e interfaces de modelos locales como Sakura / LocalLLM. Introduce la dirección de la API, la clave y el nombre del modelo, prueba la conexión y guarda los ajustes.
   - **Modo Agent externo**: si quieres traducir utilizando la cuota de un asistente de IA externo o de un cliente de programación, sigue el asistente para activar MCP o la guía de integración externa.

### 3. Iniciar la primera tarea de texto o libro electrónico

1. Selecciona un archivo de entrada o una carpeta completa en el menú principal y configura el idioma de origen, el de destino y la ruta de salida.
2. Si necesitas un glosario, descripciones de personajes o prompts personalizados, configúralos y actívalos en los menús de reglas y prompts. Los parámetros de ejecución y las reglas de cada obra se guardan por separado, por lo que no necesitas volver a configurar la API al cambiar de obra.
3. Confirma la configuración e inicia la traducción. Durante la ejecución puedes pausar, ajustar la concurrencia o cambiar a una clave de reserva en cualquier momento.
4. Si se interrumpe la conexión o detienes la tarea manualmente, la próxima vez selecciona el mismo proyecto y restaura su caché para continuar desde donde se quedó. Las partes ya traducidas no se volverán a solicitar.
5. Al terminar, puedes exportar el resultado directamente o revisarlo primero con el editor de terminal integrado o las funciones de corrección.

### 4. Abrir el panel web o la aplicación de escritorio

Si prefieres trabajar en el navegador, especialmente para consultar gráficos estadísticos, editar la caché por páginas o utilizar el editor de manga, puedes iniciar el panel web desde el menú principal de la terminal. También puedes usar los scripts de inicio de escritorio desde la línea de comandos:

- **Windows**: ejecuta `Tools\TauriShell\LaunchGUI.bat`.
- **Linux / macOS**: ejecuta `Tools/TauriShell/LaunchGUI.sh`.

### 5. Usar manga, interpretación en tiempo real y vídeo sin conexión

Estos tres módulos tienen dependencias de inferencia y modelos de mayor tamaño. Antes de utilizarlos por primera vez, ejecuta el script de preparación de la extensión correspondiente:

- **Traducción de manga**:

  - Preparar el entorno: en Windows, ejecuta `Windows comic prepare.bat`; en Linux/macOS, `Unix comic prepare.sh`.
  - Uso: abre el editor de manga en el panel web para editar y exportar visualmente, o ejecuta el procesamiento por lotes con `uv run ainiee_cli.py manga <INPUT_PATH>`.

- **Interpretación en tiempo real y vídeo sin conexión**:

  - Preparar el entorno: en Windows, ejecuta `Windows media prepare.bat`; en macOS, `Mac media prepare.command`. Si utilizas un servicio independiente de reconocimiento de voz vLLM en Linux/WSL, ejecuta también `Linux qwen vllm prepare.sh`.
  - Uso: accede desde el menú principal o ejecuta directamente `uv run ainiee_cli.py live` (subtítulos en tiempo real; en macOS también puedes hacer doble clic en `Mac live launch.command`) y `uv run ainiee_cli.py video` (vídeo sin conexión).

---

## Documentación y Wiki

| Tema | Documentación |
| :--- | :--- |
| Primeros pasos | [Guía rápida ilustrada](README_QUICK_START_EN.md) · [Obtener una clave de API de DeepSeek](DEEPSEEK_API_KEY_EN.md) |
| Ajustes de traducción | [Prompts, glosarios, pulido y ajustes del programa](TRANSLATION_WORKFLOW_GUIDE_EN.md) |
| Automatización | [Parámetros de ejecución de flujos de trabajo y reglas de herencia](WORKFLOW_RUNTIME_PARAMETERS.md) |
| Interpretación y vídeo | [Funciones multimedia y modelos](../ModuleFolders/Media/README.md) · [Guía de pruebas de interpretación en macOS](MACOS_LIVE_TRANSLATION_TEST.md) |
| MCP | [Integración del servicio](../Tools/MCPServer/README.md) · [Guía del cliente](../Tools/MCPServer/MCP_CLIENT_GUIDE.md) |
| Skills | [Llamadas HTTP, CLI y Python](../Tools/Skills/README.md) |
| Agent | [Guía de Headless Agent](../Tools/Agent/README.md) |
| Escritorio | [Inicio y compilación de Tauri](../Tools/TauriShell/README.md) |
| Desarrollo de extensiones | [Crear plugins](../PluginScripts/README.md) · [Crear Readers / Writers](../ModuleFolders/Domain/FileAccessor/README.md) |
| Textos de juegos | [Guía de StevExtraction](../Tools/StevExtraction/使用说明.md) |
| Actualizaciones | [Registro de cambios](update_log.md) |
| Otros idiomas | [简体中文](../README.md) · [English](README_EN.md) · [繁體中文](README_zh_CNTW.md) · [日本語](README_JA.md) · [한국어](README_KO.md) · [Русский](README_RU.md) |

---

## Funciones principales

### Texto, libros electrónicos y localización de juegos

- **Inyección de información según sea necesaria**: las solicitudes solo incluyen los términos del glosario y las palabras que no deben traducirse que coinciden con el fragmento actual. Admite variaciones morfológicas del inglés y detección de límites de palabra para reducir la interferencia de información irrelevante en el modelo.
- **Recuperación de personajes y cronología por volúmenes**: los nombres, alias, tratamientos, pronombres personales y expresiones habituales de las líneas cercanas permiten recuperar automáticamente a los personajes presentes. En novelas de varios volúmenes, los cambios de personajes y del contexto pueden registrarse por número de volumen, evitando aplicar en los primeros volúmenes nombres traducidos que solo aparecen más adelante.
- **Varias referencias de coherencia (opcional)**: admite memoria de traducción para frases largas repetidas en el mismo proyecto, consulta de traducciones anteriores mediante coincidencia local de palabras clave y resúmenes de la trama y recuerdos sobre personajes mediante llamadas a herramientas. Al activar el modo de memoria, la ejecución pasa automáticamente a un solo hilo para conservar el orden.
- **Recuperación ante errores y traducción de omisiones**: protege automáticamente bloques de código, marcadores de posición, saltos de línea y espacios iniciales y finales. Comprueba el número de líneas, los identificadores y los restos de texto en otro idioma de las respuestas. Si solo faltan unas pocas líneas en un lote, las traduce por separado y las devuelve a su posición sin repetir todo el lote.
- **Pulido y revisión de correcciones**: admite un flujo independiente de pulido, comprobaciones de símbolos y marcadores de posición basadas en reglas y sugerencias de corrección con IA. Las sugerencias registran una huella del texto original y pueden aceptarse, rechazarse o deshacerse individualmente desde la terminal o la web, evitando sobrescribir por error traducciones editadas a mano.
- **Herramientas para libros electrónicos**: lectura conservadora de EPUB irregulares (con filtrado de ruido del texto y anotaciones ruby japonesas), extracción de texto anidado y escritura de las traducciones en la estructura original del libro, sincronización de codificación y declaraciones, sincronización del índice y los títulos de capítulos traducidos, cambio entre disposición horizontal y vertical, eliminación de fuentes y tamaños forzados, preajustes de párrafos, reparación de enlaces locales, compresión de imágenes y conversión a WebP con actualización de referencias, EPUB bilingüe, gestión de metadatos de idioma y título, reconocimiento de números de volumen y nombres uniformes, metadatos de series y creación automática de recopilaciones por lotes, división automática de TXT en capítulos y conversión a EPUB, y normalización de comillas al traducir del japonés al chino. También permite cambiar los ajustes de exportación y volver a exportar desde la caché de traducción. Incluye un script para combinar series de libros electrónicos por lotes (`Tools/Ebook/批量电子书整合.py`) y herramientas de extracción de textos de juegos (`Tools/StevExtraction`).

### Traducción de manga y editor web

- Admite la importación de imágenes, carpetas, ZIP/CBZ, RAR/CBR y PDF, y encadena la detección de bocadillos y texto, OCR, traducción por lotes, reconstrucción del fondo y composición y renderizado automáticos.
- Los controles de calidad integrados marcan para revisión manual las páginas con una degradación anómala del modelo, caracteres ausentes o texto desbordado, e impiden exportarlas directamente como resultado terminado.
- La web ofrece un editor completo de capas para ajustar la posición y el estilo de los cuadros de texto, redibujar máscaras de reconstrucción con un pincel, repetir una etapa concreta de una sola página y deshacer o rehacer cambios. Exporta imágenes, PDF, CBZ, ZIP, EPUB y archivos PSD con capas (o scripts JSX).

### Interpretación en tiempo real y vídeo sin conexión

- **Interpretación en tiempo real**: captura el sonido del sistema o del árbol de procesos de una aplicación seleccionada. Windows permite capturar solo el programa o juego elegido sin mezclar el audio de otras aplicaciones; macOS utiliza un Helper nativo. Tras segmentar el habla y reconocerla y traducirla con modelos locales, muestra subtítulos en una ventana flotante. Incluye un glosario para streamers y una ventana privada e independiente de traducción bidireccional de texto.
- **Vídeo sin conexión**: extrae el audio y reduce el ruido automáticamente, reconoce el habla y organiza la línea de tiempo de los subtítulos. Permite combinar modelos locales y API en la nube; al final, FFmpeg genera MKV con subtítulos seleccionables o MP4 con subtítulos incrustados en la imagen.

### Automatización e integración externa

- **Colas, programación y vigilancia de carpetas**: admite colas de tareas (las pendientes pueden editarse mientras la cola está en ejecución), programación Cron y vigilancia automática de carpetas. Los archivos nuevos se añaden a la cola cuando su escritura se estabiliza, con reconocimiento del orden de los volúmenes de una serie.
- **MCP / Skills / Docker**: permite iniciar MCP Server (stdio / streamable-http / SSE) y servicios Skills HTTP/CLI. La inferencia de traducción puede delegarse en clientes de IA externos, mientras AiNiee se encarga de la lectura de archivos, la validación y la escritura atómica. Para el despliegue en contenedores, consulta `Tools/Docker/Dockerfile`.

---

## Operaciones habituales por línea de comandos

Además de los menús interactivos, todas las tareas principales pueden ejecutarse directamente desde la línea de comandos para usarlas en scripts o automatizaciones:

```bash
# Traducir un archivo o carpeta, indicar salida e idiomas y reanudar automáticamente
uv run ainiee_cli.py translate INPUT_PATH -o OUTPUT_PATH -s Japanese -t Chinese --resume --yes

# Solo pulido / traducción y pulido / solo exportar desde la caché (sin llamar al modelo)
uv run ainiee_cli.py polish INPUT_PATH --yes
uv run ainiee_cli.py all_in_one INPUT_PATH --yes
uv run ainiee_cli.py export INPUT_PATH --yes

# Procesar manga por lotes (comprobar primero los modelos locales y el dispositivo)
uv run ainiee_cli.py manga INPUT_PATH --manga-runtime-check
uv run ainiee_cli.py manga INPUT_PATH --yes

# Abrir directamente la interpretación en tiempo real o la traducción de vídeo sin conexión
uv run ainiee_cli.py live
uv run ainiee_cli.py video

# Iniciar MCP Server o un servicio Skills
uv run ainiee_cli.py mcp --mcp-transport stdio
uv run ainiee_cli.py --skills
python Tools/Skills/cli.py list
```

Ejecuta `uv run ainiee_cli.py --help` para ver todos los parámetros de línea de comandos.

---

## Formatos de archivo compatibles

| Categoría | Formatos | Descripción |
| :--- | :--- | :--- |
| Texto sin formato | `.txt`, `.md` | Extrae y reescribe línea por línea; Markdown omite automáticamente las líneas que solo contienen imágenes y las definiciones de referencias |
| Libros electrónicos | `.epub` | Analiza la estructura interna y el índice y escribe las traducciones en el archivo |
| Documentos de Office | `.docx`, `.pptx` | Extrae y reescribe nodos de texto o párrafos de cuadros de texto; PPTX no reconoce texto dentro de imágenes y simplifica parte del formato mixto dentro de los párrafos |
| Hojas de cálculo | `.csv`, `.xlsx` | CSV se lee y escribe directamente; XLSX se divide en CSV para traducirlo y luego se reconstruye. No conserva fórmulas ni formatos complejos; es adecuado para tablas de texto sencillas |
| Subtítulos y letras | `.srt`, `.vtt`, `.ass`, `.lrc` | Mantiene la línea de tiempo y las etiquetas de estilo, sustituyendo solo el texto |
| Proyectos de localización | `.po`, `.json` | PO procesa actualmente entradas en singular; JSON reconoce automáticamente estructuras como i18next, Paratranz y MTool |
| Proyectos de juegos | Ren'Py, Translator++, VNText | Extracción y escritura específicas del formato |
| PDF | `.pdf` | Utiliza BabelDOC para extraer párrafos y reinsertarlos en la maquetación; el resultado en documentos escaneados depende de las condiciones del OCR |
| Office antiguo | `.doc`, `.ppt`, etc. | Solo Windows; requiere Microsoft Word instalado localmente |
| Otros libros electrónicos | `.mobi`, `.azw3`, `.fb2`, etc. | Requiere instalar y activar Calibre; los archivos se convierten para procesarlos y después se convierten de nuevo al formato original |

---

## Notas

1. **Alcance de la traducción de vídeo**: el flujo de vídeo sin conexión solo procesa actualmente el habla de la pista de audio; no reconoce texto incrustado en los fotogramas. Además, la extracción automática de términos para vídeos largos envía ahora toda la transcripción al modelo en una sola solicitud (la división según el presupuesto aún no está implementada). Para vídeos muy largos, introduce el glosario manualmente o utiliza un modelo con una ventana de contexto larga.
2. **Dependencias de herramientas externas**: exportar manga a PSD con capas requiere Photoshop instalado localmente; de lo contrario, solo se pueden exportar scripts JSX. Comprimir y extraer archivos RAR/CBR requiere las herramientas externas de línea de comandos correspondientes en el sistema.
3. **Seguridad del acceso remoto**: el panel web escucha por defecto solo en la dirección de bucle local. La validación de sesión integrada sirve principalmente para evitar el uso indebido entre sitios de los endpoints locales; no es un sistema multiusuario de cuentas y permisos. Para el acceso remoto, utiliza una red privada de confianza o un proxy inverso con autenticación de acceso delante del servicio.

---

## Referencias y agradecimientos

- [AiNiee](https://github.com/NEKOparapa/AiNiee): este proyecto se ha desarrollado a partir de su lógica central de traducción. Gracias al autor original NEKOparapa y a sus colaboradores.
- [manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui) ([copia en Gitee](https://gitee.com/hgmzhn/manga-translator-ui)): referencia para el flujo automático de manga, la separación de etapas y la organización de recursos de ejecución.
- [Koharu](https://github.com/mayocream/koharu): referencia para proyectos de manga, capas, edición de bloques de texto y procesos de retoque manual.

Se conservarán las atribuciones de las fuentes y los agradecimientos. Las referencias y la reutilización respetan las licencias de código abierto de cada proyecto.

---

## Licencia

Este proyecto es de código abierto bajo la GNU Affero General Public License v3.0 (AGPL-3.0). Consulta el archivo `LICENSE` en la raíz del repositorio para obtener más información.

---

## Apoyar AiNiee-Next

Si AiNiee-Next te ha resultado útil, puedes apoyar su desarrollo y mantenimiento continuos a través de [Afdian](https://ifdian.net/a/Next_ZhiXie) o del código QR de donación que aparece abajo. Quienes apoyen el proyecto se incluirán en la lista de agradecimientos. Gracias por cada aportación.

<div align="center">
  <img src="Images/赞赏码.png" alt="Código QR de donación" width="320">
</div>

---

<div align="center">
  Made by ShadowLoveElysia
  <br>
  Based on the original work by NEKOparapa
</div>
