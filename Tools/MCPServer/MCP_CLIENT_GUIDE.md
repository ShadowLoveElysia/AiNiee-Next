# AiNiee CLI MCP Client Guide

## Overview

AiNiee CLI MCP 会把大部分 WebServer `/api/*` 能力通过少量 MCP tools 暴露出来，让不支持读项目文件的 LLM 客户端也能直接操作项目，同时避免在 MCP 工具发现阶段一次性注入全部端点。根目录 `SKILL.md` 只是必须遵循的使用规则文件，不是 MCP 或 `Tools/Skills/` 服务，不能作为执行通道或降级选项。

推荐任意 LLM 客户端在首次连接后按下面顺序执行：

1. 调用 `get_mcp_usage_manual`
2. 调用 `get_mcp_security_policy`
3. 调用 `get_mcp_tool_categories`
4. 按任务需要调用 `get_mcp_tool_catalog(category="...")`
5. 再通过 `call_web_api` 或 `upload_file` 调用具体能力

外部 Agent 接入后，应先调用 `agent_register` 获取连接租约，并在租约到期前调用
`agent_heartbeat`。默认连接租约为 120 秒；长任务可在注册时传入
`requested_lease_seconds: 3600`，服务端允许的最大会话租约为 3600 秒（60 分钟）。
超过上限的请求会被拒绝；无论租约长短，客户端都应按返回的
`heartbeat_interval_seconds` 定期续租。断开时调用 `agent_unregister`；可用 `agent_status`
查询单个或全部连接。
这些工具只管理进程内连接状态，不授予 Agent 直接修改缓存、队列、源文件或输出文件的权限。

Agent session 租约最长 3600 秒（60 分钟）；建议长任务仍按返回的 `heartbeat_interval_seconds`
定期调用 `agent_heartbeat`。writer lease 是独立的短期写回租约，不随 session 租约延长。

项目默认继续使用已配置的 API。若要让某一次任务由外部 Agent 处理，使用已鉴权的
MCP 代理调用 `POST /api/task/external-agent-mode`；它只覆盖这一次任务的快照，
不会修改 `translation_execution_mode`、Profile 或其他项目设置。不要通过 `/api/config`
把全局模式改成外部 Agent 来启动任务。

如果客户端只展示工具名和工具说明，不展示仓库文件，也应优先使用上面的说明工具，而不是猜参数结构或一次性读取全量端点目录。原生 MCP 工具是首选执行通道；`Tools/Skills/` 是独立的 REST/JSON 备用服务，只有用户明确选择或原生 MCP 确实无法挂载时才使用。

## First Steps

推荐的首轮对话流程：

1. 先读取 `get_mcp_usage_manual(section="overview")`
2. 再读取 `get_mcp_security_policy()`
3. 再读取 `get_mcp_tool_categories()`
4. 根据目标读取单个分类，例如 `get_mcp_tool_catalog(category="config")` 或 `get_mcp_tool_catalog(category="queue")`
5. 然后用 `call_web_api(method="GET", path="/api/config")` 这类调用访问端点

如果要修改高级设置，例如 `mcp_server_port` 或 `mcp_server_host`：

1. 先向用户说明影响
2. 再次询问用户是否确认修改
3. 只有得到二次确认后，才在写配置时传 `confirm_advanced_change=true`

外部 Agent 不得为了连接方便自行修改 `mcp_server_host`、`mcp_server_port` 或
`enable_remote_access`。先读取并探测当前服务，复用现有端口；默认保持 loopback
监听和远程访问关闭。若用户确实要求改变服务端高级设置，必须先完成上面的二次确认，
再通过 MCP 配置端点写入并传 `confirm_advanced_change=true`，同时让客户端 URL 与实际
host、port、path 保持一致。客户端自己的 MCP 配置只能通过客户端原生配置接口写入，
且仍需先取得用户许可；这不等于允许直接编辑 AiNiee 项目配置文件。

## Security Policy

以下规则对所有通过 MCP 接入的 LLM 客户端都成立：

- LLM 驱动的 AiNiee 操作必须只使用 MCP 暴露的工具，不要把 MCP 工具调用和直连 Web UI、localhost、局域网 WebServer 端口或 MCP HTTP 端口混用
- 敏感 Web API 路由要求有效的 Web UI 会话 cookie 或 MCP bridge token；裸 HTTP 直连会被服务端拒绝
- `api_key`、`access_key`、`secret_key` 会被 MCP 侧主动脱敏
- 读取 `/api/config` 这类包含敏感配置的 MCP 响应时，服务端还会附带 `_mcp_security_notice`，说明通道鉴权限制和脱敏行为
- 脱敏占位符不是可用密钥，不能当成真实值继续保存或复用
- 如果 MCP 返回了占位符，LLM 不得尝试推断、恢复或拼接真实密钥
- `/api/internal/*` 属于内部回调接口，不应被 LLM 客户端调用

当前 MCP 脱敏占位符：

```text
[MCP_SECRET_REDACTED]
```

当前 MCP 配置读取提示字段：

```text
_mcp_security_notice
```

## Core Tools

建议优先了解这些核心工具：

- `get_mcp_usage_manual`: 返回内置使用手册，适合首次接入时调用
- `get_mcp_security_policy`: 返回通道鉴权和敏感字段脱敏政策
- `get_mcp_tool_categories`: 返回轻量级端点分类索引，不展开每个端点详情
- `get_mcp_tool_catalog`: 按分类返回端点目录、调用方式和示例参数；默认只返回分类索引
- `get_mcp_validation_checklist`: 返回 4 个安全验证场景
- `list_web_api_routes`: 返回轻量级路由索引，可传 `category` 只看单类路由
- `call_web_api`: 受控 MCP 代理调用入口，用于调用分类目录里的 `/api/*` 端点
- `upload_file`: 通过 MCP 上传本地文件到 WebServer

外部 Agent 连接工具：

- `agent_register`: 注册 Agent，返回 `session_id` 和租约到期时间
- `agent_heartbeat`: 使用 `session_id` 续租
- `agent_unregister`: 主动释放连接租约
- `agent_status`: 查询连接状态
- `agent_request_external_mode`: 通过已鉴权的 MCP 端口请求当前 session 使用外部 Agent 模式；仅写入运行时 session 状态，不修改 Profile、`Resource/config.json` 或 `translation_execution_mode`

推荐调用顺序：`agent_register` → `agent_request_external_mode` → 业务 MCP 工具 → 周期性 `agent_heartbeat` → `agent_unregister`。

外部 Agent 翻译原型顺序：`agent_register` → `agent_request_external_mode` → `agent_prepare_project` →
`agent_claim_batch` → `agent_submit_translation_batch`。提交只写入受控批次账本，
不会直接写入 AiNiee 缓存或最终输出；断线时使用 `agent_release_batch`，不要重用过期 session。
如果要基于已有 AiNiee 缓存继续翻译，使用 `agent_prepare_cache_project`；它会返回服务端生成的
opaque item locator 和 cache revision，Agent 不得自行构造 storage_path 或 text_index。
正式写回还必须先调用 `agent_acquire_writer_lease`，再调用 `agent_commit_cache_batch`。
提交时只需传任务、批次和 writer lease；缓存路径与 staged 结果由 AiNiee 服务端绑定和读取。
没有 writer lease、cache revision 或 opaque locator 时，结果只能停留在 staging，不能写入正式缓存。

`agent_prepare_project` 的返回值包含 `next_batch_id`、`batch_ids` 和不含正文的 `batches` 摘要；
如果客户端丢失了准备或领取响应，可用 `agent_project_status` 恢复这些字段，再调用
`agent_claim_batch` 获取该批次的正文。`agent_claim_batch` 的完整响应仍以 `batch.batch_id`
为提交时的权威批次 ID。

术语表提取可以由外部 Agent 执行：先调用 `agent_detect_file_language` 了解源语言，
再用 `agent_read_file` 分段读取原文。每次最多返回 1000 行，响应中的 `next_start_line`
用于继续读取。读取工具只提供受控文本，不会自动改写术语表；术语结果若要保存，必须另行
使用明确的 glossary 写入操作。

需要和翻译批次一样可靠领取时，使用 `agent_prepare_read_batches` →
`agent_claim_read_batch`。每个读取批次最多 1000 行，并返回独立的 `batch_id`、
`source_hash` 和任务 `revision`；客户端丢失响应时用 `agent_read_batch_status` 恢复批次 ID。
处理完一批后调用 `agent_complete_read_batch`，再领取下一批；所有读取批次均为只读，
不会直接写入术语表。
如果 Agent 在一批处理中断，调用 `agent_release_read_batch` 后可以重新领取该批次。

对于由 `POST /api/task/external-agent-mode` 创建的全新 EPUB/DOCX 等结构化任务，Web
端会先执行无 API 的解析预热并生成受控 `AinieeCacheData.json`，随后首次调用
`agent_prepare_project`、`agent_project_status` 或 `agent_claim_batch` 会自动建立缓存账本，
不再需要先跑一次普通翻译。全部缓存批次提交并写回后，MCP 会自动触发最终格式导出；提交接口
返回的 `export` 字段包含输出目录。若只完成 staging 或没有 writer lease，则不会导出。

直接使用 `agent_prepare_project` 创建新账本时仍只适用于普通逐行 TXT。EPUB、DOCX、SRT、ASS、VTT、LRC、JSON、PO、Paratranz 等结构化格式会返回稳定错误码
`STRUCTURED_FORMAT_REQUIRES_MCP_TASK`；但由 Web 的 `external-agent-mode` 任务预热生成的结构化缓存，会由同名工具自动恢复账本（见上文），不需要把结构化文件当作二进制文本切批。

会话断线后不要复用过期的 `session_id`。先用新的 Agent 实例调用 `agent_register`，再调用
`agent_resume_task(task_id, session_id, previous_session_id)`。旧会话必须已经断开或过期；任务账本
会把仍在领取中的批次绑定到新会话，保留已经 staging 的结果，并释放旧 writer lease。恢复后必须
重新调用 `agent_acquire_writer_lease`，然后才能提交写回。

## Calling Patterns

AiNiee CLI MCP 默认不再把每个 Web API 路由都注册成独立 `api_*` 工具，以减少 LLM 工具发现上下文。默认调用流程是：

1. `get_mcp_tool_categories()`
2. `get_mcp_tool_catalog(category="目标分类")`
3. `call_web_api(method="GET", path="/api/...")`

`call_web_api` 参数模式：

- `path_params`: 用于填充路径中的 `{index}`、`{name}` 之类占位参数
- `query`: URL 查询参数
- `body`: JSON 请求体
- `confirm_advanced_change`: 仅配置高级 MCP 设定时才需要

典型示例：

```json
{
  "method": "POST",
  "path": "/api/config",
  "body": {
    "target_platform": "openai",
    "model": "gpt-4o-mini"
  }
}
```

如果端点对应的是 `GET /api/...`，通常不需要 `body`。

如果确实需要兼容旧版每路由独立 `api_*` 工具，可以用环境变量 `AINIEE_MCP_REGISTER_ROUTE_TOOLS=1` 或启动参数 `--register-route-tools` 打开；默认建议保持关闭。

## Validation Checklist

建议在接入新的 MCP 客户端后验证下面 4 个场景：

1. Config Redaction
调用 `call_web_api(method="GET", path="/api/config")`，确认 `api_key` / `access_key` / `secret_key` 都是脱敏占位符，而不是明文。

2. Queue Redaction
调用 `call_web_api(method="GET", path="/api/queue")` 和 `call_web_api(method="GET", path="/api/queue/raw")`，确认队列任务中的密钥字段不会明文返回。

3. Non-Secret Save
先读取配置，再只修改一个非敏感字段，例如 `model` 或 `target_platform`，然后保存；确认原有真实密钥仍被保留，没有被占位符覆盖。

4. Placeholder Rejection
尝试把 `[MCP_SECRET_REDACTED]` 当作新建队列任务的 `api_key` 保存，确认服务端会拒绝。
