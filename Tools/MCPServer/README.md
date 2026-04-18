# AiNiee MCPServer

这是为 `AiNiee-Next` 准备的可选 MCP 服务模块。

当前设计原则：

- 放在 `Tools/MCPServer` 下，和主流程解耦
- 复用 `Tools/WebServer/web_server.py` 现有 HTTP API，避免重复实现业务逻辑
- 缺少组件或依赖时，只在尝试启动 MCP 时提示，不影响主程序其他功能

当前入口文件：

- `Tools/MCPServer/runtime.py`
  负责检查组件文件和必要 Python 依赖，并生成 `uv add ...` 安装建议
- `Tools/MCPServer/docs.py`
  负责生成 MCP 内置使用手册、工具目录、安全策略与验证清单
- `Tools/MCPServer/server.py`
  启动 MCP 服务，并自动拉起一个内嵌的 `WebServer` 后端作为桥接层
- `Tools/MCPServer/MCP_CLIENT_GUIDE.md`
  面向 LLM 客户端的 MCP 使用文档源文件

推荐安装命令：

```bash
uv add mcp
```

如果本地缺少 WebServer 运行依赖，也可以一起补齐：

```bash
uv add mcp fastapi uvicorn[standard] requests
```

客户端接入示例：

1. Codex `stdio` 接入，推荐使用项目内置 launcher

```bash
codex mcp add ainiee-cli -- /path/to/AiNiee-CLI/Tools/MCPServer/codex_stdio_launcher.sh
```

首次启动若依赖尚未缓存，建议在 `~/.codex/config.toml` 中为该 MCP 配置较大的 `startup_timeout_sec`，例如 `90`。

2. 若需要原始命令，推荐使用隔离模式，避免项目 `.venv` 干扰

```bash
uv run --python /usr/bin/python3 --isolated --no-project --quiet --with mcp --with fastapi --with 'uvicorn[standard]' --with requests python /path/to/AiNiee-CLI/Tools/MCPServer/server.py --transport stdio
```

3. `streamable-http` 路由接入

```text
本机地址: http://127.0.0.1:8765/mcp
局域网地址: http://<你的局域网IP>:8765/mcp
```

如果修改了 `mcp_server_port`，请同步更新客户端中的 MCP 路由配置。
如果项目目录中的 `.venv` 混用了 Windows / WSL 两侧创建的环境，执行 `uv add` 前建议先重建 `.venv`。

LLM 客户端接入后，推荐先调用以下 MCP 说明工具，而不是猜测参数结构：

- `get_mcp_usage_manual`
- `get_mcp_security_policy`
- `get_mcp_tool_catalog`
- `get_mcp_validation_checklist`

安全要求：

- 严禁让 LLM 绕过 MCP，直接向 WebUI / localhost / 局域网端口发送 HTTP 请求
- LLM 只能通过 MCP 工具访问 AiNiee 能力
- MCP 返回的 `api_key` / `access_key` / `secret_key` 会被脱敏，不能尝试恢复或复用
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
