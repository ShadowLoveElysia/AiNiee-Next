---
name: ainiee-next-translation
description: 在用户要求翻译小说、文档、字幕或其他文件内容时，按 AiNiee-Next 的输入优先、长文本询问和 MCP 边界执行；进入 AiNiee 工作流后，原文获取与术语预分析也必须走受控读取工具，禁止自行解包解析。
---

# AiNiee-Next 翻译协作规则

这份技能规则约束外部 Agent 选择 AiNiee-Next 后的完整文件处理流程，包括原文获取、术语抽取、预分析、翻译与结果提交。项目默认仍使用自身配置的 API；外部 Agent 不能通过修改 Profile、项目配置或本地缓存来切换模式。

## 名称和层级

- 根目录 `SKILL.md` 是外部 Agent 必须遵循的使用规则和说明书，不是工具、服务、传输协议或翻译执行入口，不能与 MCP 或 `Tools/Skills/` 服务互相降级。
- `Tools/MCPServer/` 提供原生 MCP 执行通道，优先使用当前客户端已经挂载的 MCP 工具。
- `Tools/Skills/` 提供独立的 REST/JSON 或 CLI 服务。只有原生 MCP 确实无法挂载/重载，且用户明确选择或允许备用服务时，才使用它。

## 任务判断

- 用户直接传入的文件、文本或压缩包是本次任务的首要输入。先识别并处理这些输入，不要把 `Profile`、规则 Profile、缓存、历史输出或项目中的其他文件当作待翻译内容。
- 项目快照中的输入路径、输出路径和历史任务路径只能作为参考，不能在任务开始时直接读取。若当前消息没有提供新的文件、上传内容或明确路径，先询问用户是继续上次翻译，还是改为处理新文件；用户确认前不要打开快照路径。
- 如果用户在当前消息直接给出文件路径或上传了文件，必须以该路径和上传文件为本次任务的主要输入；不能用项目快照中的旧路径、Profile 输入路径或历史输出替换它。只有在 MCP 或 `Tools/Skills/` 服务接入完成、并完成输入选择后，才读取用户指定的受控文件。
- 用户没有明确要求时，不主动读取、翻译或重写 Profile 内容。Profile 只作为 AiNiee 运行时的服务端配置来源，不作为外部 Agent 的工作输入。
- 不需要向用户确认源语言；根据受控读取工具返回的原文或语言统计判断。只向用户询问目标语言（以及用户没有说明时的输出格式），不要用 Profile 中的语言字段覆盖用户要求。

## 文件格式和超过 500 行时的询问

- 只有用户直接传入的单个 TXT，且不超过 500 行，才可以走 Agent 自身的普通翻译流程。
- 单个 TXT 超过 500 行时，在启动 AiNiee 翻译前询问用户，必须使用下面这句话：

> 当前您的环境存在AiNiee-Next环境，是否需要我使用其MCP为您翻译此次任务？

- EPUB、DOCX、SRT、ASS、VTT、LRC、JSON、PO、Paratranz、游戏脚本以及其他带专用结构的格式，必须通过 AiNiee-Next MCP 获取原文和执行任务，不走自行解析后的普通文本直译。备用服务仍须遵循下文的明确选择规则。
- 在用户明确同意前，不要启动超过 500 行 TXT 的 AiNiee MCP 翻译；可对该 TXT 做判断是否需要 MCP 的行数统计。这不授权自行解析结构化文件，也不授权进入 MCP 工作流后再绕过读取工具。

## 原文获取：术语与预处理同样必须走 MCP

- 进入 AiNiee 工作流后，主 Agent 和所有 SubAgent 都必须通过受控工具获取原文；术语抽取、词频分析、章节预读、语言判断和正式翻译均在此范围内。“只是预处理”“只读不写”不能作为绕过 MCP 的理由。上文不超过 500 行单个 TXT 的普通翻译例外仅适用于未选择 AiNiee 的任务。
- 外部源文件先调用 `upload_file` 上传原文件，再使用返回的受控路径。分析/术语阶段用 `agent_read_file(path, start_line, max_lines)`，按 `next_start_line` 继续，或在注册会话后使用 `agent_prepare_read_batches` → `agent_claim_read_batch` → `agent_complete_read_batch`；每次最多 1000 个逻辑原文条目。语言统计可用 `agent_detect_file_language`，不能替代实际原文读取。
- 正式翻译只处理 `agent_claim_batch` / `agent_claim_batches` 返回的 `items`；分析阶段读到的文本不能被自行拼装成翻译批次。主 Agent 可以把工具返回的对应批次和必要上下文交给 SubAgent，SubAgent 不得另行打开源文件或提取全文。
- 禁止创建或运行 `extract_src.py` 一类替代提取脚本，禁止用 Python、Shell、`zipfile`、正则、HTML/XML 解析器或本地导入 AiNiee 内部模块绕过 MCP 读取源文件；不得自行列举 XHTML、剥离 ruby、生成 `source_blocks.txt` 或替代 TXT 后再声称走了 AiNiee。格式解析、条目划分和读取顺序由 AiNiee 负责。Agent 可基于工具已返回的原文分析术语和词频。
- 工具未挂载、路径不受控、读取超时、返回 `FILE_PARSE_FAILED` 或其他错误时，停止依赖该原文的处理，报告工具名、非敏感错误和所需的连接/路径/依赖修复；不得静默改用自写脚本、直接读缓存或解析器。只有用户明确改选 Skills 备用服务后，才可使用其受控读取批次接口；仍不得自行解析源文件。
- 此边界针对待处理原文。阅读 `SKILL.md`、客户端指南和 `Resource/Prompt/System/glossary_extract_zh.txt` 等操作说明与提示词不属于自行提取原文；读取这些说明也不等于已通过 MCP 取得书籍内容。

## MCP 模式和配置边界

- 用户同意使用 AiNiee-Next MCP 后，先阅读根目录 `Agents.md`、本规则文件和 `Tools/MCPServer/MCP_CLIENT_GUIDE.md`；若需要启动或接入服务，再阅读 `Tools/MCPServer/README.md`。本规则文件只是使用说明，不是待挂载的 Skill 服务。
- MCP 接入按以下优先级执行：当前会话已经挂载的原生 MCP 工具 → 配置或重载 stdio MCP → 仅支持 URL 时挂载 `streamable-http` MCP（默认 `http://127.0.0.1:8765/mcp`）→ 原生 MCP 确实无法挂载或重载、且当前客户端只能使用本地 HTTP 时，才使用已鉴权的 HTTP 备用入口。HTTP 备用入口不是原生 MCP 的等价替代，不能因为 URL 更方便就跳过原生 MCP。
- Agent 可以按当前客户端能力自行配置并拉起 AiNiee MCP 进程，在获得必要的用户许可后完成依赖安装、服务启动和客户端 MCP 注册。不要要求用户代为执行这些步骤。该安装只针对当前 Agent 自己的技能目录和 MCP 客户端，不要替其他 Agent 框架或客户端安装、修改配置。
- 先检查当前会话是否已有 AiNiee MCP 工具并完成 initialize/工具发现；如果已经连接，直接继续，跳过 `Launch.bat`。
- 如果当前 Agent 无法自动启动或重载原生 MCP，再指导用户双击项目根目录的 `Launch.bat`；进入 AiNiee 主菜单后选择“启动 MCP 服务”，保持该窗口运行。菜单启动的是 `streamable-http`，默认连接地址为 `http://127.0.0.1:8765/mcp`；用户完成后，当前 Agent 再探测该地址并验证工具列表。`Launch.bat` 本身不是 MCP 端点，不能只看到主菜单就宣称服务已连接。
- 如果当前 Agent 具备启动本地程序的能力，可以尝试启动项目根目录的 `Launch.bat`；启动动作完成后必须立即停止后续 MCP、Skills 和翻译工具调用，等待用户明确回复“已开启”“开启了”“可以了”等肯定语句。收到肯定回复后才重新探测 MCP URL、执行 initialize 握手并确认工具列表；未收到肯定回复时不得继续，也不能把启动进程当作连接成功。
- MCP 启动优先复用项目现有环境：Linux/WSL 使用 `{project_root}/.venv/bin/python`，Windows 使用 `{project_root}\\.venv-win\\Scripts\\python.exe`。对应命令为 `uv run --directory <project_root> --python <project_root>/.venv/bin/python python Tools/MCPServer/server.py --transport stdio`；只有现有环境不存在或用户明确要求隔离环境时，才使用 `uv run --python 3.12 --isolated --no-project --with mcp --with fastapi --with uvicorn[standard] --with requests python Tools/MCPServer/server.py --transport stdio`。
- 写入当前 Agent 自己的 MCP 配置后，必须让当前 Agent 客户端重新加载或重启 MCP 连接，并确认 AiNiee 工具已经出现在当前会话的工具列表中；仅仅写入配置文件、看到进程启动或读取到配置，不等于 MCP 已接入。若当前客户端无法热重载，明确报告需要重启当前 Agent 会话后再继续，不能退回普通 Skills 并声称 MCP 已可用。
- 如果用户已经明确选择使用 AiNiee-Next MCP，当前会话看不到 AiNiee MCP 工具时必须停止在“等待当前 Agent 重载/重启”状态；不要把根目录 `SKILL.md` 当成替代工具，也不要自动切换到 `Tools/Skills/` 服务。只有用户明确选择 `Tools/Skills/` 作为备用服务时，才可以使用它。
- 原生 MCP 多次无法挂载或重载时，不得静默改走普通翻译。若当前客户端确实只能使用本地 HTTP，先用当前对话语言说明正在使用 HTTP 备用入口及原因，再按受控的已鉴权 HTTP 路由继续；若客户端连 HTTP 也不支持，则停止并报告需要重载/重启原生 MCP。此时也不能把根目录 `SKILL.md` 当成执行入口。
- AiNiee 项目默认 API 模式不会被永久切换。注册 Agent session 后，只能通过已鉴权 MCP 端口的 `agent_request_external_mode` 工具（底层任务端点为 `POST /api/task/external-agent-mode`；Skills 端口对应 `request_external_mode`）请求 `execution_mode=external_agent`，并限定到当前任务。
- 用户直接提供的外部路径（例如 `H:\Downloads\ManualTransFile.json`）不能直接加入服务白名单，也不能直接传给 `prepare_project`。先通过原生 MCP 的 `upload_file`，或仅在用户明确选择 `Tools/Skills/` 服务时使用 `file.stage_external` 将文件复制到 AiNiee 受控暂存目录，再使用返回的受控路径准备批次。
- 禁止通过文件编辑、`/api/config`、Profile、规则 Profile、`translation_execution_mode`、`mcp_server_host`、`mcp_server_port` 或远程访问设置切换模式。不要直接写入缓存、队列、源文件或最终输出。
- MCP 连接成功后依次读取 `get_mcp_usage_manual(section="overview")`、`get_mcp_security_policy`、`get_mcp_tool_categories`、目标 `get_mcp_tool_catalog`，再注册 Agent 会话、请求任务模式并使用受控批次工具。默认速度优先：普通源文件使用 `agent_prepare_project` → `agent_claim_batches`（省略 `max_batches` 时读取当前 Profile 配置，默认 8 批，可由用户设为更大值）→ 多个 SubAgent 分别翻译 → `agent_submit_translation_batch`；也可用 `agent_claim_batch(batch_id=...)` 跳批次领取。已有缓存使用 `agent_prepare_cache_project` → `agent_claim_batches` → `agent_submit_translation_batch` → `agent_acquire_writer_lease` → `agent_commit_cache_batch`，领取和 staging 可以乱序，正式写回仍逐批经过 writer lease、cache revision、source hash 和 current line hash 校验。只有用户表达“质量优先”“精翻”“保持上下文/文风”等明确意图时，才切换为逐批串行翻译；此时仍可为当前批次启用 SubAgent 以减少主 Agent 上下文负担。若客户端不支持 SubAgent，退回有界并行或串行，不把 SubAgent 当作服务端必备能力。全部批次 committed 但自动导出未发生时，使用 `agent_export_task`，它只读取已提交缓存并调用格式感知导出器，不重新翻译。断线使用 `agent_release_batch`，恢复使用新的 session 调用 `agent_resume_task`。API key、MCP token 和用户原文不写入提示词、日志或配置。
- 单次领取批次数由 TUI“设置 → 项目通用设置 → Agent 单次领取批次数”（`external_agent_max_batches`）控制，默认 8，允许任意正整数，8 不是固定上限。只读查询无需额外同意；Agent 修改持久设置前必须说明新值并获得用户明确同意（已有明确授权无需重复询问），不得自行填写同意标记。MCP 写入 `/api/config` 时使用 `confirm_agent_batch_change=true`；Skills `config.set` 使用同名字段。领取时可请求更少批次以适应客户端能力或质量优先；不要通过更大的 `max_batches` 或连续领取来绕过用户设定的并行规模。
- MCP 工具调用必须直接传入结构化参数，不要先把参数写入临时 JSON/TXT 再上传或转交。例如查询缓存状态时直接调用 `call_web_api(method="GET", path="/api/cache/status")`；`path_params`、`query`、`body`、批次 `items` 和 Skills 的 JSON `action` 也都直接作为调用参数传入。`upload_file` 只用于端点明确要求的用户文件本体，不能用来传递普通工具参数或包装后的请求 JSON。
- 以 `agent_claim_batch` 或 `agent_claim_batches` 返回的 `items` 为唯一处理清单；提交必须完整覆盖对应批次全部条目，并保留 index、item_id、source_hash、current_line_hash、cache_revision 等服务端字段，不得自行添加、删除、重排或伪造条目。并行批次共享准备阶段的源 revision；单批提交不会阻塞其他批次领取或 staging。新 manifest 会过滤 EXCLUDED/已翻译/校对条目；旧账本若仍包含 EXCLUDED，提交仍按 claim 清单完整返回原样占位，writer 会保留源行并跳过写入。正式缓存写回仍由 writer lease 保护；遇到 `ITEM_CONFLICT`、`REVISION_CONFLICT`、`SOURCE_MISMATCH`、`CACHE_REVISION_CONFLICT` 时停止当前批次并报告具体错误，不覆盖缓存。
- `agent_register` 默认会话租约为 120 秒；长任务可以传入 `requested_lease_seconds: 3600` 将租约延长到 60 分钟。必须按响应中的 `heartbeat_interval_seconds` 调用 `agent_heartbeat`，超过 3600 秒的请求会被拒绝。这个会话租约与独立的 writer lease 分开管理。
- 用户传入的文件若位于 AiNiee 项目根目录之外（例如 `Downloads`、桌面或其他盘符），不能直接把该路径传给 `agent_prepare_project`；批次服务只接受受控项目路径。应先使用当前 MCP 的 `upload_file` 将原文件上传到 AiNiee 的暂存目录，再使用上传结果返回的项目内 `path` 创建批次。上传后保留原文件，不要把 `Downloads` 等外部目录加入 AiNiee 服务的允许根目录，也不要把上传路径当作任意写入授权。若当前客户端没有可用的 `upload_file`，应报告需要 MCP 连接或由用户明确选择 Skills 文件入口后再继续。
- HTTP 备用入口同样必须直接发送结构化请求参数；不要先生成参数 JSON/TXT 文件再通过 HTTP 上传。只有端点明确要求用户文件本体时，才使用原始路径或受控上传结果；HTTP 备用入口仍不得调用 `/api/internal/*`，也不得绕过鉴权。
- 输出目录必须位于 AiNiee 项目受控根内，不能覆盖输入目录；已有输出或 cache 需要先由受控任务/工具备份后再处理。

## 引导式学习与 TUI 建议

- 当用户要求精细修改配置、提示词、术语表、规则、并发、输出格式、Profile 或其他需要多项选项的设置时，先用通俗语言主动引导用户了解 TUI：说明“我可以通过 MCP 帮你完成配置，不过这个功能在 TUI 中更方便探索；如果你希望更精细地调整设置并提升翻译质量，可以点击 `Launch.bat` 启动 TUI，自己查看和学习这些选项”。
- 这是建议和学习入口，不是阻止条件。用户已经明确要求 Agent 直接代办时，继续通过 MCP/受控接口完成，不要反复劝阻，也不要要求用户必须打开 TUI。
- 对只需一次明确动作的任务（例如开始翻译、查询状态、手动导出、领取批次），直接执行并说明结果，不要为了“学习”强行插入 TUI 教程。
- 引导内容应帮助用户理解 AiNiee 的作用，例如 TUI 适合细致调整 API、提示词、术语表、规则、并发和输出设置，Agent/MCP 适合通过结构化工具执行已经确定的任务。不要把 TUI 说成唯一正确入口，也不要暗示 Agent 模式不可用。

## 任务开始前的统一决策

- 新任务先判断用户直接传入的文件或文件夹是否属于同一系列作品。若是独立作品，或用户没有提供其他同系列卷本，使用普通术语抽取；若确认是系列作品且有可用的前卷术语表，使用增量术语抽取。
- 术语抽取必须读取并遵循 `Resource/Prompt/System/glossary_extract_zh.txt`。原文必须按“原文获取”一节经 `agent_read_file` 或只读批次工具获取，再按该 JSON 结构生成术语、禁翻表、角色设定、世界观、文风和示例；不得先自写 EPUB 提取脚本。
- 必须联网搜索官方角色译名和术语译名；对原文中的角色原名、地名和专有名词，必须搜索目标语言的官方译名。若互联网没有找到其存在官方译名，才由 Agent 自行翻译，并必须符合从原文判断出的文本风格（例如日本轻小说名字风格、欧美名字风格等）。世界观、关系和文风仅根据原文判断，不用网络内容扩展或推测。
- 术语抽取完成后，如果 MCP 查询到 AiNiee 当前确实配置了可用 API，询问用户本阶段由外部 Agent 通过 MCP 处理还是由 AiNiee API 处理；如果没有可用 API，不询问，默认使用外部 Agent MCP。不要读取或改写 Profile 来制造 API 配置。
- 翻译完成后，润色和校对都是可选阶段。若 MCP 查询到可用 API，询问用户选择外部 Agent 或 API；若没有可用 API，默认使用外部 Agent MCP。询问可以在任务开始前一次确定，也可以在各阶段完成后再问，优先在任务开始前一次确定。

## 处理优先级

1. 识别用户直接传入的输入和格式；只对普通 TXT 进行上述本地行数判断，不自行解析结构化文件。
2. 确定目标语言和输出要求。超过 500 行的单个 TXT 按上文询问并等待回答；结构化格式按 MCP 流程接入。
3. 确认 MCP 工具已挂载，将外部文件上传到受控路径，通过原文读取工具判断源语言和进行术语分析。
4. 通过 MCP 请求当前任务的外部 Agent 模式，领取翻译批次并按协议提交结果。
5. 保留用户原始输入和既有输出，使用任务返回的状态和输出路径确认完成。
