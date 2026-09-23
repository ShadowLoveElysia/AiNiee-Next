---
name: ainiee-next-translation
description: 在用户要求翻译小说、文档、字幕或其他文件内容时，按 AiNiee-Next 的输入优先、长文本询问和 MCP 端口边界执行。
---

# AiNiee-Next 翻译协作规则

这份技能规则只约束外部 Agent 如何判断是否使用 AiNiee-Next。项目默认仍使用自身配置的 API；外部 Agent 不能通过修改 Profile、项目配置或本地缓存来切换模式。

## 任务判断

- 用户直接传入的文件、文本或压缩包是本次任务的首要输入。先识别并处理这些输入，不要把 `Profile`、规则 Profile、缓存、历史输出或项目中的其他文件当作待翻译内容。
- 用户没有明确要求时，不主动读取、翻译或重写 Profile 内容。Profile 只作为 AiNiee 运行时的服务端配置来源，不作为外部 Agent 的工作输入。
- 不需要自行确认源语言；读取用户传入内容即可。只向用户询问目标语言（以及用户没有说明时的输出格式），不要用 Profile 中的语言字段覆盖用户要求。

## 文件格式和超过 500 行时的询问

- 只有用户直接传入的单个 TXT，且不超过 500 行，才可以走 Agent 自身的普通翻译流程。
- 单个 TXT 超过 500 行时，在启动 AiNiee 翻译前询问用户，必须使用下面这句话：

> 当前您的环境存在AiNiee-Next环境，是否需要我使用其MCP为您翻译此次任务？

- EPUB、DOCX、SRT、ASS、VTT、LRC、JSON、PO、Paratranz、游戏脚本以及其他带专用结构的格式，直接优先使用 AiNiee-Next MCP，不走普通文本直译。
- 在用户明确同意前，不要启动超过 500 行 TXT 的 AiNiee MCP 翻译；可以继续进行文件识别、行数统计和语言判断。

## MCP 模式和配置边界

- 用户同意使用 AiNiee-Next MCP 后，先阅读根目录 `Agents.md`、本文件和 `Tools/MCPServer/MCP_CLIENT_GUIDE.md`；若需要启动或接入服务，再阅读 `Tools/MCPServer/README.md`。
- Agent 可以按当前客户端能力自行配置并拉起 AiNiee MCP 进程，在获得必要的用户许可后完成依赖安装、服务启动和客户端 MCP 注册。不要要求用户代为执行这些步骤。该安装只针对当前 Agent 自己的技能目录和 MCP 客户端，不要替其他 Agent 框架或客户端安装、修改配置。
- 先检查当前会话是否已有 AiNiee MCP 工具并完成 initialize/工具发现；如果已经连接，直接继续，跳过 `Launch.bat`。
- 如果当前 Agent 无法自动启动或重载 MCP，再指导用户双击项目根目录的 `Launch.bat`；进入 AiNiee 主菜单后选择“启动 MCP 服务”，保持该窗口运行。菜单启动的是 `streamable-http`，默认连接地址为 `http://127.0.0.1:8765/mcp`；用户完成后，当前 Agent 再探测该地址并验证工具列表。`Launch.bat` 本身不是 MCP 端点，不能只看到主菜单就宣称服务已连接。
- 如果当前 Agent 具备启动本地程序的能力，可以尝试启动项目根目录的 `Launch.bat`；启动动作完成后必须立即停止后续 MCP、Skills 和翻译工具调用，等待用户明确回复“已开启”“开启了”“可以了”等肯定语句。收到肯定回复后才重新探测 MCP URL、执行 initialize 握手并确认工具列表；未收到肯定回复时不得继续，也不能把启动进程当作连接成功。
- MCP 启动优先复用项目现有环境：Linux/WSL 使用 `{project_root}/.venv/bin/python`，Windows 使用 `{project_root}\\.venv-win\\Scripts\\python.exe`。对应命令为 `uv run --directory <project_root> --python <project_root>/.venv/bin/python python Tools/MCPServer/server.py --transport stdio`；只有现有环境不存在或用户明确要求隔离环境时，才使用 `uv run --python 3.12 --isolated --no-project --with mcp --with fastapi --with uvicorn[standard] --with requests python Tools/MCPServer/server.py --transport stdio`。
- 写入当前 Agent 自己的 MCP 配置后，必须让当前 Agent 客户端重新加载或重启 MCP 连接，并确认 AiNiee 工具已经出现在当前会话的工具列表中；仅仅写入配置文件、看到进程启动或读取到配置，不等于 MCP 已接入。若当前客户端无法热重载，明确报告需要重启当前 Agent 会话后再继续，不能退回普通 Skills 并声称 MCP 已可用。
- 如果用户已经明确选择使用 AiNiee-Next MCP，当前会话看不到 AiNiee MCP 工具时必须停止在“等待当前 Agent 重载/重启”状态；Skills 只能在用户明确改选 Skills 作为备用入口时使用，不能自动降级。
- 硬性停止规则：凡本文件判定为必须使用 AiNiee-Next MCP 的任务（包括结构化格式，以及用户同意使用 MCP 的超长 TXT），只要当前会话工具列表没有 AiNiee MCP，就必须停止并报告“需要重载/重启当前 Agent 的 MCP 连接”。不得改用 Skills、Skills REST/CLI 或普通翻译来绕过连接失败；只有用户明确改选 Skills 作为备用入口后，才可以使用 Skills。
- AiNiee 项目默认 API 模式不会被永久切换。注册 Agent session 后，只能通过已鉴权 MCP 端口的 `agent_request_external_mode` 工具（底层任务端点为 `POST /api/task/external-agent-mode`；Skills 端口对应 `request_external_mode`）请求 `execution_mode=external_agent`，并限定到当前任务。
- 用户直接提供的外部路径（例如 `H:\Downloads\ManualTransFile.json`）不能直接加入服务白名单，也不能直接传给 `prepare_project`。先通过 MCP 的 `upload_file`，或在用户明确选择 Skills 时使用 `file.stage_external` 将文件复制到 AiNiee 受控暂存目录，再使用返回的受控路径准备批次。
- 禁止通过文件编辑、`/api/config`、Profile、规则 Profile、`translation_execution_mode`、`mcp_server_host`、`mcp_server_port` 或远程访问设置切换模式。不要直接写入缓存、队列、源文件或最终输出。
- MCP 连接成功后依次读取 `get_mcp_usage_manual(section="overview")`、`get_mcp_security_policy`、`get_mcp_tool_categories`、目标 `get_mcp_tool_catalog`，再注册 Agent 会话、请求任务模式并使用受控批次工具。普通源文件使用 `agent_prepare_project` → `agent_claim_batch` → `agent_submit_translation_batch`；已有缓存使用 `agent_prepare_cache_project` → `agent_claim_batch` → `agent_submit_translation_batch` → `agent_acquire_writer_lease` → `agent_commit_cache_batch`。断线使用 `agent_release_batch`，恢复使用新的 session 调用 `agent_resume_task`。API key、MCP token 和用户原文不写入提示词、日志或配置。
- 以 `agent_claim_batch` 返回的 `items` 为唯一处理清单；提交必须完整覆盖该批全部条目，并保留 index、item_id、source_hash、current_line_hash、cache_revision 等服务端字段，不得自行添加、删除、重排或伪造条目。新 manifest 会过滤 EXCLUDED/已翻译/校对条目；旧账本若仍包含 EXCLUDED，提交仍按 claim 清单完整返回原样占位，writer 会保留源行并跳过写入。遇到 `ITEM_CONFLICT`、`REVISION_CONFLICT`、`SOURCE_MISMATCH` 时停止当前批次并报告具体错误，不覆盖缓存。
- `agent_register` 默认会话租约为 120 秒；长任务可以传入 `requested_lease_seconds: 3600` 将租约延长到 60 分钟。必须按响应中的 `heartbeat_interval_seconds` 调用 `agent_heartbeat`，超过 3600 秒的请求会被拒绝。这个会话租约与独立的 writer lease 分开管理。
- 用户传入的文件若位于 AiNiee 项目根目录之外（例如 `Downloads`、桌面或其他盘符），不能直接把该路径传给 `agent_prepare_project`；批次服务只接受受控项目路径。应先使用当前 MCP 的 `upload_file` 将原文件上传到 AiNiee 的暂存目录，再使用上传结果返回的项目内 `path` 创建批次。上传后保留原文件，不要把 `Downloads` 等外部目录加入 AiNiee 服务的允许根目录，也不要把上传路径当作任意写入授权。若当前客户端没有可用的 `upload_file`，应报告需要 MCP 连接或由用户明确选择 Skills 文件入口后再继续。
- 输出目录必须位于 AiNiee 项目受控根内，不能覆盖输入目录；已有输出或 cache 需要先由受控任务/工具备份后再处理。

## 任务开始前的统一决策

- 新任务先判断用户直接传入的文件或文件夹是否属于同一系列作品。若是独立作品，或用户没有提供其他同系列卷本，使用普通术语抽取；若确认是系列作品且有可用的前卷术语表，使用增量术语抽取。
- 术语抽取必须读取并遵循 `Resource/Prompt/System/glossary_extract_zh.txt`。先读取用户传入的原文，再按该 JSON 结构生成术语、禁翻表、角色设定、世界观、文风和示例。
- 必须联网搜索官方角色译名和术语译名；对原文中的角色原名、地名和专有名词，必须搜索目标语言的官方译名。若互联网没有找到其存在官方译名，才由 Agent 自行翻译，并必须符合从原文判断出的文本风格（例如日本轻小说名字风格、欧美名字风格等）。世界观、关系和文风仅根据原文判断，不用网络内容扩展或推测。
- 术语抽取完成后，如果 MCP 查询到 AiNiee 当前确实配置了可用 API，询问用户本阶段由外部 Agent 通过 MCP 处理还是由 AiNiee API 处理；如果没有可用 API，不询问，默认使用外部 Agent MCP。不要读取或改写 Profile 来制造 API 配置。
- 翻译完成后，润色和校对都是可选阶段。若 MCP 查询到可用 API，询问用户选择外部 Agent 或 API；若没有可用 API，默认使用外部 Agent MCP。询问可以在任务开始前一次确定，也可以在各阶段完成后再问，优先在任务开始前一次确定。

## 处理优先级

1. 识别用户直接传入的输入和实际行数。
2. 判断源语言、目标语言和输出要求。
3. 仅在超过 500 行时询问是否使用 AiNiee-Next MCP，并等待用户回答。
4. 用户同意后，通过 MCP 端口请求当前任务的外部 Agent 模式，按批次协议提交结果。
5. 保留用户原始输入和既有输出，使用任务返回的状态和输出路径确认完成。
