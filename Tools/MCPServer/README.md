# AiNiee MCPServer

这是为 `AiNiee-Next` 准备的可选 MCP 服务模块。

当前设计原则：

- 放在 `Tools/MCPServer` 下，和主流程解耦
- 复用 `Tools/WebServer/web_server.py` 现有 HTTP API，避免重复实现业务逻辑
- 缺少组件或依赖时，只在尝试启动 MCP 时提示，不影响主程序其他功能

当前入口文件：

- `Tools/MCPServer/runtime.py`
  负责检查组件文件和必要 Python 依赖，并生成可直接执行的完整安装命令
- `Tools/MCPServer/docs.py`
  负责生成 MCP 内置使用手册、工具目录、安全策略与验证清单
- `Tools/MCPServer/server.py`
  启动 MCP 服务，并自动拉起一个内嵌的 `WebServer` 后端作为桥接层
- `Tools/MCPServer/MCP_CLIENT_GUIDE.md`
  面向 LLM 客户端的 MCP 使用文档源文件

推荐安装命令：

```bash
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win" && uv --directory "%CD%" add "mcp"
```

如果本地缺少 WebServer 运行依赖，也可以一起补齐：

```bash
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win" && uv --directory "%CD%" add "mcp" "fastapi" "uvicorn[standard]" "requests"
```

Linux / macOS 可使用：

```bash
UV_PROJECT_ENVIRONMENT="$(pwd)/.venv" uv --directory "$(pwd)" add 'mcp' 'fastapi' 'uvicorn[standard]' 'requests'
```

客户端接入示例：

1. Codex `stdio` 接入，推荐使用项目内置 launcher

```bash
codex mcp add ainiee-cli -- /path/to/AiNiee-CLI/Tools/MCPServer/codex_stdio_launcher.sh
```

首次启动若依赖尚未缓存，建议在 `~/.codex/config.toml` 中为该 MCP 配置较大的 `startup_timeout_sec`，例如 `90`。

2. 若需要原始命令，优先复用项目现有 `.venv` 环境

```bash
uv run --directory /path/to/AiNiee-CLI --python /path/to/AiNiee-CLI/.venv/bin/python python Tools/MCPServer/server.py --transport stdio
```

Windows 使用项目环境时，将解释器改为
`H:\\小说\\AiNiee-CLI\\.venv-win\\Scripts\\python.exe`。只有项目环境不存在或明确需要隔离时，才使用
`uv run --python 3.12 --isolated --no-project --with mcp --with fastapi --with 'uvicorn[standard]' --with requests ...`。

补充说明：

- 部分 LLM 客户端会在自身启动时自动拉起配置好的 `stdio` MCP 进程
- AiNiee-Next 要求 Python `3.12.*`；不要把 `python3`、Python 3.11 或更低版本传给 `uv --python`。如果 stdio 日志出现 `SyntaxError` 或 `BrokenPipe/Invalid argument`，先检查解释器版本；后者通常只是 MCP 进程已退出后的管道次生错误。
- 现在如果 AiNiee 的 `streamable-http` MCP 已经在运行，新的 `stdio` 进程会先探测该端点，探测成功后直接复用已有服务，不再重复启动一套 MCP
- 复用命中时，`stderr` 会打印一行提示：`AiNiee MCP reusing running service: http://127.0.0.1:端口/mcp`
- 如果你确实需要禁用这层复用逻辑，可设置环境变量 `AINIEE_MCP_DISABLE_RUNNING_REUSE=1`

3. `streamable-http` 路由接入

```text
本机地址: http://127.0.0.1:8765/mcp
局域网地址: http://<你的局域网IP>:8765/mcp
```

如果修改了 `mcp_server_port`，请同步更新客户端中的 MCP 路由配置。
Windows 下如果项目目录中的 `.venv` 混用了 Windows / WSL 两侧创建的环境，上面的命令会直接改用 `.venv-win`，避免 `.venv\lib64` 冲突。

LLM 客户端接入后，推荐先调用以下 MCP 说明工具，而不是猜测参数结构：

- `get_mcp_usage_manual`
- `get_mcp_security_policy`
- `get_mcp_tool_categories`
- `get_mcp_tool_catalog(category="需要的分类")`
- `get_mcp_validation_checklist`

默认情况下，MCP 不会把每个 Web API 路由都注册成独立 `api_*` 工具，避免一百多个端点在工具发现阶段占用大量上下文。LLM 应先读取 `get_mcp_tool_categories`，再按需读取单个分类的 `get_mcp_tool_catalog(category="...")`，最后用 `call_web_api` 调用目录里的 `/api/*` 路由。

如需兼容旧版每路由独立工具，可设置 `AINIEE_MCP_REGISTER_ROUTE_TOOLS=1` 或启动时添加 `--register-route-tools`。

安全要求：

- LLM 驱动的 AiNiee 操作只能通过 MCP 工具完成，不要和直连 WebUI / localhost / 局域网端口的 HTTP 请求混用
- 敏感 Web API 路由要求有效的 Web UI 会话 cookie 或 MCP bridge token，裸 HTTP 直连会被拒绝
- MCP 返回的 `api_key` / `access_key` / `secret_key` 会被脱敏，不能尝试恢复或复用
- MCP 读取敏感配置时会额外返回 `_mcp_security_notice`，说明通道鉴权限制和脱敏行为
- 如果 MCP 返回了脱敏占位符，不能把该占位符当真实密钥保存回配置或队列

推荐验证场景：

1. 读取配置，确认密钥字段被脱敏
2. 读取队列和队列原始 JSON，确认密钥字段被脱敏
3. 修改非敏感配置并保存，确认原有真实密钥被保留
4. 尝试把脱敏占位符作为新队列密钥保存，确认服务端拒绝

暂定支持的 MCP 工具能力：

- 读取版本与系统模式
- 读取/保存当前配置
- 管理 profiles / rules profiles
- 管理 plugins
- 管理 glossary / prompts
- 管理 queue
- 启动/停止任务并读取任务状态
