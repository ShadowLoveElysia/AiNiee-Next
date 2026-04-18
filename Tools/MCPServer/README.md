# AiNiee MCPServer

这是为 `AiNiee-Next` 准备的可选 MCP 服务模块。

当前设计原则：

- 放在 `Tools/MCPServer` 下，和主流程解耦
- 复用 `Tools/WebServer/web_server.py` 现有 HTTP API，避免重复实现业务逻辑
- 缺少组件或依赖时，只在尝试启动 MCP 时提示，不影响主程序其他功能

当前入口文件：

- `Tools/MCPServer/runtime.py`
  负责检查组件文件和必要 Python 依赖，并生成 `uv add ...` 安装建议
- `Tools/MCPServer/server.py`
  启动 MCP 服务，并自动拉起一个内嵌的 `WebServer` 后端作为桥接层

推荐安装命令：

```bash
uv add mcp
```

如果本地缺少 WebServer 运行依赖，也可以一起补齐：

```bash
uv add mcp fastapi uvicorn[standard] requests
```

暂定支持的 MCP 工具能力：

- 读取版本与系统模式
- 读取/保存当前配置
- 管理 profiles / rules profiles
- 管理 plugins
- 管理 glossary / prompts
- 管理 queue
- 启动/停止任务并读取任务状态
