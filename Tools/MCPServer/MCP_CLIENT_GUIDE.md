# AiNiee CLI MCP Client Guide

## Overview

AiNiee CLI MCP 会把大部分 WebServer `/api/*` 能力暴露成 MCP tools，让不支持读项目文件的 LLM 客户端也能直接操作项目。

推荐任意 LLM 客户端在首次连接后按下面顺序执行：

1. 调用 `get_mcp_usage_manual`
2. 调用 `get_mcp_security_policy`
3. 调用 `get_mcp_tool_catalog`
4. 再开始调用具体的 `api_*` 工具或 `upload_file`

如果客户端只展示工具名和工具说明，不展示仓库文件，也应优先使用上面 3 个说明工具，而不是猜参数结构。

## First Steps

推荐的首轮对话流程：

1. 先读取 `get_mcp_usage_manual(section="overview")`
2. 再读取 `get_mcp_security_policy()`
3. 再读取 `get_mcp_tool_catalog(category="config")` 或 `get_mcp_tool_catalog(category="queue")`
4. 然后按需要调用具体工具

如果要修改高级设置，例如 `mcp_server_port` 或 `mcp_server_host`：

1. 先向用户说明影响
2. 再次询问用户是否确认修改
3. 只有得到二次确认后，才在写配置时传 `confirm_advanced_change=true`

## Security Policy

以下规则对所有通过 MCP 接入的 LLM 客户端都成立：

- 严禁绕过 MCP，直接向 Web UI、localhost、局域网 WebServer 端口或 MCP HTTP 端口发送 HTTP 请求取数
- 必须只使用 MCP 暴露的工具
- `api_key`、`access_key`、`secret_key` 会被 MCP 侧主动脱敏
- 脱敏占位符不是可用密钥，不能当成真实值继续保存或复用
- 如果 MCP 返回了占位符，LLM 不得尝试推断、恢复、拼接或绕过读取真实密钥
- `/api/internal/*` 属于内部回调接口，不应被 LLM 客户端调用

当前 MCP 脱敏占位符：

```text
[MCP_SECRET_REDACTED]
```

## Core Tools

建议优先了解这些核心工具：

- `get_mcp_usage_manual`: 返回内置使用手册，适合首次接入时调用
- `get_mcp_security_policy`: 返回安全政策，明确禁止绕过 MCP 直连 WebUI
- `get_mcp_tool_catalog`: 返回按分类整理的工具目录、调用方式和示例参数
- `get_mcp_validation_checklist`: 返回 4 个安全验证场景
- `list_web_api_routes`: 返回轻量级路由索引
- `call_web_api`: 原始 MCP 代理调用入口，仅在命名工具不够用时使用
- `upload_file`: 通过 MCP 上传本地文件到 WebServer

## Calling Patterns

AiNiee CLI MCP 的绝大多数 `api_*` 工具遵循相同参数模式：

- `path_params`: 用于填充路径中的 `{index}`、`{name}` 之类占位参数
- `query`: URL 查询参数
- `body`: JSON 请求体
- `confirm_advanced_change`: 仅配置高级 MCP 设定时才需要

典型示例：

```json
{
  "body": {
    "target_platform": "openai",
    "model": "gpt-4o-mini"
  }
}
```

如果工具对应的是 `GET /api/...`，通常不需要 `body`。

## Validation Checklist

建议在接入新的 MCP 客户端后验证下面 4 个场景：

1. Config Redaction
调用 `api_get_api_config`，确认 `api_key` / `access_key` / `secret_key` 都是脱敏占位符，而不是明文。

2. Queue Redaction
调用 `api_get_api_queue` 和 `api_get_api_queue_raw`，确认队列任务中的密钥字段不会明文返回。

3. Non-Secret Save
先读取配置，再只修改一个非敏感字段，例如 `model` 或 `target_platform`，然后保存；确认原有真实密钥仍被保留，没有被占位符覆盖。

4. Placeholder Rejection
尝试把 `[MCP_SECRET_REDACTED]` 当作新建队列任务的 `api_key` 保存，确认服务端会拒绝。
