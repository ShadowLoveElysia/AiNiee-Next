# AiNiee-Next：通用 LLM 客户端接入说明

本文面向能调用工具、MCP 或本地命令的通用 LLM 客户端。项目根目录是当前文件所在目录。客户端可以在获得用户明确许可后，自动启动服务、安装缺失依赖并写入自己的 MCP/SKILL 配置；没有许可时只能读取说明和给出命令，不能启动进程、修改配置或发起翻译。

## 项目能做什么

AiNiee-Next 是一个跨平台的批量翻译与文本处理工具，CLI/TUI 是主要界面，同时提供 Web 控制面板、任务队列、插件系统、MCP 服务和轻量 Skills 服务。

- 翻译、润色和一体化任务：支持文本逐行处理、上下文、术语表、翻译记忆、RAG 参考、提示词和质量检查。
- 文件处理：支持 Epub、Docx、Txt、Srt、Ass、Vtt、Lrc、Json、Po、Paratranz 等格式；可结合 Calibre 处理部分电子书格式。
- 漫画流水线：导入图片或压缩包，执行文本检测、OCR、翻译、修补、嵌字渲染和导出；入口包括 `--manga`、Web Manga Mode 和 MangaCore。
- 长任务运行：异步高并发、重试、限流、API 故障转移、断点续传、缓存恢复、失败分段重跑和任务进度跟踪。
- 配置与自动化：多 Profile、规则 Profile、Glossary、Prompt、插件、可排序任务队列、费用/时间估算、Web 监控和诊断报告。
- 模型与平台：兼容多种在线 API、中转服务和本地模型；具体平台、模型、API 地址和密钥由用户在 Profile 或运行参数中配置。

核心数据面仍由 AiNiee 的确定性翻译引擎负责：分块、并发、缓存、限流、重试、恢复、格式检查和输出写入。MCP 与 `Tools/Skills/` 服务只是外部控制层；根目录 `SKILL.md` 是使用规则文件，不是工具或服务。LLM 不应直接改写缓存、队列内部状态或已有输出文件。

## 可用入口

| 入口 | 用途 | 启动示例 |
|---|---|---|
| CLI/TUI | 本地交互或脚本批量翻译 | `uv run ainiee_cli.py translate INPUT -o OUTPUT -s Japanese -t Chinese --resume --yes` |
| Web | 浏览器监控、配置、队列和插件管理 | `uv run ainiee_cli.py`，在菜单选择 Web Server（默认 `127.0.0.1:8000`） |
| MCP | 标准 MCP 工具协议，供支持 MCP 的 LLM 客户端调用 | `uv run ainiee_cli.py mcp --mcp-transport stdio` |
| Tools/Skills 服务 | 精选 REST/JSON 接口，也可 CLI 或 Python 直调 | `python Tools/Skills/server.py --port 8766` |

## MCP 接入

MCP 位于 `Tools/MCPServer/`，支持 `stdio`、`streamable-http` 和 `sse`。默认 HTTP 地址是 `http://127.0.0.1:8765/mcp`；如修改端口或路径，客户端必须同步修改。HTTP/SSE 的非回环监听需要用户在 TUI 高级设置中允许远程访问；stdio 不受该网络开关影响。

### stdio（推荐本地接入）

优先使用项目内置 launcher，它会用隔离的 uv 环境启动 MCP，避免混用 WSL/Windows 的 `.venv`：

```bash
codex mcp add ainiee-cli -- /path/to/AiNiee-CLI/Tools/MCPServer/codex_stdio_launcher.sh
```

如果客户端使用 `command`/`args` JSON 配置，通用形式如下（将路径替换为实际绝对路径）：

```json
{
  "mcpServers": {
    "ainiee-cli": {
      "command": "uv",
      "args": [
        "run", "--directory", "/path/to/AiNiee-CLI",
        "--isolated", "--no-project", "--quiet",
        "--with", "mcp", "--with", "fastapi",
        "--with", "uvicorn[standard]", "--with", "requests",
        "python", "Tools/MCPServer/server.py", "--transport", "stdio"
      ]
    }
  }
}
```

Windows 客户端可把目录改为 `H:\\小说\\AiNiee-CLI`，或直接把 `command` 设为 `Tools\\MCPServer\\codex_stdio_launcher.bat`（若客户端允许脚本作为 stdio 命令）。首次下载依赖可能需要把 MCP 启动超时调到约 90 秒。

### streamable-http / SSE

先在项目目录启动：

```bash
uv run ainiee_cli.py mcp --mcp-transport streamable-http
```

然后在客户端填写：

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

MCP 启动时会生成或读取 `AINIEE_MCP_AUTH_TOKEN`。客户端应让服务端和桥接后端使用同一个令牌，但绝不能把令牌、API key 或配置密钥写入对话、日志、仓库或提交记录。

### MCP 首轮调用顺序

连接成功后不要猜参数，也不要一次性展开全部 Web 路由。依次调用：

1. `get_mcp_usage_manual(section="overview")`
2. `get_mcp_security_policy()`
3. `get_mcp_tool_categories()`
4. `get_mcp_tool_catalog(category="config|queue|task|...")`
5. 按目录使用 `call_web_api(method, path, path_params, query, body)` 或 `upload_file`

可用的辅助工具还有 `list_web_api_routes` 和 `get_mcp_validation_checklist`。只有在确有兼容性需求时，才通过 `AINIEE_MCP_REGISTER_ROUTE_TOOLS=1` 或 `--register-route-tools` 注册旧式的逐路由 `api_*` 工具。

## Skills 接入

Skills 不依赖 MCP，使用 Python 标准库提供 REST/JSON 服务，默认监听 `127.0.0.1:8766`：

```bash
python Tools/Skills/server.py --port 8766
# 或
bash Tools/Skills/launcher.sh --port 8766
```

默认需要请求头 `X-AiNiee-Skills-Auth`。服务启动时会显示本次令牌，也可通过 `AINIEE_SKILLS_AUTH_TOKEN` 固定令牌；仅可信本机临时调试才使用 `--no-auth`。远程绑定必须显式加 `--allow-remote-access`，并保留鉴权。

当前注册的六个 Skill：

| Skill | 作用 |
|---|---|
| `system` | 健康、版本和系统信息 |
| `config` | 读取或设置 Profile 配置项 |
| `translate` | 启动、查询、停止翻译/润色任务 |
| `queue` | 列出、添加、删除、清空、运行和查询队列 |
| `profile` | 列出、切换、创建和删除 Profile |
| `file` | 安全地发现文件、读取信息和暂存上传路径 |

协议端点：`GET /health`、`GET /skills`、`GET /skills/{name}`、`POST /skills/{name}`。例如：

```bash
curl http://127.0.0.1:8766/skills
curl -X POST http://127.0.0.1:8766/skills/system \
  -H 'Content-Type: application/json' \
  -H 'X-AiNiee-Skills-Auth: <token>' \
  -d '{"action":"ping"}'
```

也可以不启动 HTTP 服务，直接执行：

```bash
python Tools/Skills/cli.py list
python Tools/Skills/cli.py describe translate
python Tools/Skills/cli.py run system '{"action":"ping"}'
python Tools/Skills/cli.py check
```

`translate.run` 和 `queue.run` 返回稳定 `task_id`，随后用 `status`/`stop` 查询或停止。Skills 会启动隔离的 CLI 子进程，不让 LLM 直接写翻译缓存。

## 用户许可下的自动接入流程

当用户说“接入 AiNiee”“把这个项目加到我的 MCP 或 Tools/Skills 服务客户端”或给出等价许可时，LLM 可以按以下流程自动完成：

1. 确认当前客户端支持 MCP stdio、MCP HTTP、Skills HTTP 或本地命令中的哪一种，并解析项目绝对路径。
2. 向用户说明将要启动的命令、需要安装的依赖、监听地址和可能修改的客户端配置；等待明确许可后再执行安装、启动或写配置。
3. 优先选择原生 MCP stdio launcher；若客户端只支持 URL，则启动 streamable-http；只有原生 MCP 确实不可用且用户明确允许备用服务时，才使用 `Tools/Skills/` HTTP 或 CLI。
4. 运行 `--check`/健康检查，连接后先读取 MCP 手册与安全策略，或先请求 `GET /skills` 获取技能元数据。
5. 将连接名称、命令、参数、URL、令牌来源和启动超时写入客户端原生配置。令牌使用环境变量或客户端密钥存储，不写进仓库文件。
6. 仅在用户另行确认具体操作后启动翻译、润色、队列任务、配置写入或 Profile 删除；完成后返回 task_id、状态和输出路径。

如果客户端没有可写配置接口，LLM 应输出可复制的配置片段，不应猜测配置文件位置。依赖安装失败时，报告非敏感错误摘要和可执行命令，保留用户现有配置不变。

## 安全与操作边界

- 所有由 LLM 驱动的 AiNiee 操作都通过 MCP 工具或 Skills 接口完成，不要混用直连 WebUI、localhost Web API、局域网端口或内部 `/api/internal/*`。
- 原文获取边界覆盖术语抽取、词频分析和其他预处理，也适用于 SubAgent。外部文件先 `upload_file`，再通过 `agent_read_file` 或 `agent_prepare_read_batches` / `agent_claim_read_batch` 获取原文；正式翻译只处理领取工具返回的 `items`。禁止自行解包 EPUB、编写提取脚本或生成替代 TXT；工具缺失或失败时报告问题并停止相关处理。用户明确改选 Skills 后才可用其受控读取接口。规则与提示词文件可以阅读，但不能以此替代 MCP 原文读取。
- MCP 会脱敏 `api_key`、`access_key`、`secret_key`，占位符 `[MCP_SECRET_REDACTED]` 不是可用密钥，不能恢复、推断或写回。
- 读取敏感配置时应保留 `_mcp_security_notice`，并向用户说明通道鉴权限制。
- 配置高级项（例如 `mcp_server_port`、`mcp_server_host`）前先说明影响并再次确认。
- 翻译、润色和队列任务是异步的；不要因收到 `running` 就宣称已经完成，应轮询状态并报告失败原因。
- 保留原文件和已有输出；通过 Skills/MCP 启动的任务必须使用项目返回的 task_id 跟踪状态，不得覆盖已有输出。
- 不要把 API key、MCP/Skills token、用户原文或译文写入本文件、日志、提交信息或客户端公开配置。

更详细的协议目录和验证清单见 `Tools/MCPServer/MCP_CLIENT_GUIDE.md` 与 `Tools/Skills/README.md`。
