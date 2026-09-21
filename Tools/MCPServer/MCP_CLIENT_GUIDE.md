# AiNiee CLI MCP Client Guide

## Overview

AiNiee CLI MCP 会把大部分 WebServer `/api/*` 能力通过少量 MCP tools 暴露出来，让不支持读项目文件的 LLM 客户端也能直接操作项目，同时避免在 MCP 工具发现阶段一次性注入全部端点。

推荐任意 LLM 客户端在首次连接后按下面顺序执行：

1. 调用 `get_mcp_usage_manual`
2. 调用 `get_mcp_security_policy`
3. 调用 `get_mcp_tool_categories`
4. 按任务需要调用 `get_mcp_tool_catalog(category="...")`
5. 再通过 `call_web_api` 或 `upload_file` 调用具体能力

外部 Agent 接入后，应先调用 `agent_register` 获取连接租约，并在租约到期前调用
`agent_heartbeat`。断开时调用 `agent_unregister`；可用 `agent_status` 查询单个或全部连接。
这些工具只管理进程内连接状态，不授予 Agent 直接修改缓存、队列、源文件或输出文件的权限。

如果客户端只展示工具名和工具说明，不展示仓库文件，也应优先使用上面的说明工具，而不是猜参数结构或一次性读取全量端点目录。

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

推荐调用顺序：`agent_register` → 业务 MCP 工具 → 周期性 `agent_heartbeat` → `agent_unregister`。

外部 Agent 翻译原型顺序：`agent_register` → `agent_prepare_project` →
`agent_claim_batch` → `agent_submit_translation_batch`。提交只写入受控批次账本，
不会直接写入 AiNiee 缓存或最终输出；断线时使用 `agent_release_batch`，不要重用过期 session。
如果要基于已有 AiNiee 缓存继续翻译，使用 `agent_prepare_cache_project`；它会返回服务端生成的
opaque item locator 和 cache revision，Agent 不得自行构造 storage_path 或 text_index。
正式写回还必须先调用 `agent_acquire_writer_lease`，再调用 `agent_commit_cache_batch`。
提交时只需传任务、批次和 writer lease；缓存路径与 staged 结果由 AiNiee 服务端绑定和读取。
没有 writer lease、cache revision 或 opaque locator 时，结果只能停留在 staging，不能写入正式缓存。

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
