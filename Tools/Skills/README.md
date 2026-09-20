# AiNiee Skills — 轻量级 AI 工具调用框架

一套轻量的、**不依赖 MCP** 的 AiNiee 交互框架。Skills 通过简洁的 REST/JSON 接口暴露核心功能，无需 MCP 协议、FastAPI 或 uvicorn。

## 为什么用 Skills 而不是 MCP？

MCP 服务器（`Tools/MCPServer/`）是一套完整的 [Model Context Protocol](https://modelcontextprotocol.io) 实现，需要：
- `mcp` Python 包（FastMCP）
- `fastapi` + `uvicorn` 提供 HTTP 传输
- JSON-RPC 2.0 消息格式
- 从 WebServer 自动发现路由

Skills 则完全不同：
- **零额外服务依赖** — HTTP 层仅用 Python 标准库（`http.server`、`json`），业务层复用项目现有模块
- **简洁 REST/JSON** — 不是 JSON-RPC，就是 HTTP + JSON
- **精选操作** — 预定义的 skill 覆盖核心工作流，不自动暴露所有路由
- **多种执行模式** — 可通过 HTTP 服务、CLI、或直接 Python 调用
- **可组合** — skill 可串联调用，适合脚本自动化

## 快速开始

### 启动 Skills Server

命令行启动（默认仅监听本机）：
```bash
python Tools/Skills/server.py --port 8766
```

需要局域网监听时，必须显式允许远程绑定，并保持鉴权：
```bash
AINIEE_SKILLS_AUTH_TOKEN="your-token" \
python Tools/Skills/server.py --host 0.0.0.0 --allow-remote-access --port 8766
```

默认情况下，`POST /skills/{name}` 需要鉴权。服务启动时会在终端输出本次运行的
`X-AiNiee-Skills-Auth` token；也可以用环境变量固定 token：

```bash
AINIEE_SKILLS_AUTH_TOKEN="your-token" python Tools/Skills/server.py --port 8766
```

只在可信本机调试时，可以用 `--no-auth` 临时关闭 HTTP 鉴权。

或用启动脚本：
```bash
bash Tools/Skills/launcher.sh --port 8766
```

Windows 可直接运行：
```bat
Tools\Skills\launcher.bat --port 8766
```

Skills 也会随 Python wheel 一起安装，并提供 `ainiee-skills` 与
`ainiee-skills-cli` 两个命令；源码环境优先使用项目中的 `uv`，没有 `uv`
时启动脚本会回退到 Python 解释器。

Docker 镜像默认仍启动 CLI。要启动 Skills API（容器分支显式允许容器端口监听，仍建议设置令牌）：
```bash
docker run --rm -p 8766:8766 \
  -e AINIEE_SERVICE=skills \
  -e AINIEE_SKILLS_AUTH_TOKEN="your-token" \
  ghcr.io/<owner>/<repo>:<tag>
```

### 检查服务是否运行

```bash
curl http://127.0.0.1:8766/health
```

返回：
```json
{"status": "ok", "service": "ainiee-skills", "skills_count": 7}
```

### 不启动服务检查运行环境

在完整依赖尚未安装、或当前环境禁止监听端口时，可以先运行无 socket
探测。它会检查 Skills 文件、标准库 HTTP 支持和七个生产 Skill 的导入状态，
并输出 JSON：

```bash
python Tools/Skills/cli.py check
# 或
python Tools/Skills/server.py --check
```

退出码约定：`0` 表示生产 Skill 全部可导入；`2` 表示探测成功但文件、标准库
或业务依赖不完整；`1` 仅表示探测器自身异常。该命令不会启动 HTTP listener。

### 查看可用 Skills

```bash
curl http://127.0.0.1:8766/skills
```

## 内置 Skills

| Skill | 分类 | 说明 |
|-------|------|------|
| `system` | system | 系统信息与健康检查 |
| `config` | config | 读写配置文件的设置项 |
| `translate` | task | 执行翻译任务 |
| `queue` | queue | 管理项目内置任务队列（`Resource/queue_tasks.json`） |
| `profile` | config | 管理配置方案（新建/切换/删除，自动限制在 profiles 目录内） |
| `file` | files | 文件发现与暂存 |
| `agent_session` | agent | 外部 Agent 会话注册、心跳、状态和断开 |

### 外部 Agent 会话

`agent_session` 管理外部 Agent 的短期租约，且与 `X-AiNiee-Skills-Auth`
鉴权令牌完全分离。注册必须携带用户确认字段；会话过期后应重新注册。
Skills 只保存会话元数据，不接收 API key、MCP token 或其他提供商密钥。

```bash
curl -X POST http://127.0.0.1:8766/skills/agent_session \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action":"register","agent_instance_id":"desktop-1", "client_name":"WorkBuddy", "supported_modes":["external_agent"], "capabilities":["translation","proofread"], "user_confirmed_external_processing":true}'
```

随后使用返回的 `session_id` 和 `agent_instance_id` 调用 `heartbeat`；任务运行期间应定期续租。`status` 可查询单个会话或返回当前进程中的会话摘要，`unregister` 会结束租约并保留脱敏审计快照。

## API 参考

### `GET /health`
健康检查端点。

### `GET /skills`
列出所有可用的 skill，包含说明、参数和示例。

### `GET /skills/{name}`
获取指定 skill 的详细信息。

**示例：**
```bash
curl http://127.0.0.1:8766/skills/system
```

### `POST /skills/{name}`
执行一个 skill，传入参数。

**Ping：**
```bash
curl -X POST http://127.0.0.1:8766/skills/system \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action": "ping"}'
```
返回：
```json
{"success": true, "data": {"pong": true}}
```

**读取配置：**
```bash
curl -X POST http://127.0.0.1:8766/skills/config \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action": "get", "key": "target_platform"}'
```

**列出配置方案：**
```bash
curl -X POST http://127.0.0.1:8766/skills/profile \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action": "list"}'
```

**启动翻译：**
```bash
curl -X POST http://127.0.0.1:8766/skills/translate \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{
    "action": "run",
    "task_type": "translate",
    "input_path": "/path/to/file.txt",
    "source_lang": "Japanese",
    "target_lang": "Chinese",
    "profile": "default"
  }'
```

## CLI 模式

不启动 HTTP 服务也能直接调用 skill：

```bash
# 列出所有 skill
python Tools/Skills/cli.py list

# 查看 skill 详情
python Tools/Skills/cli.py describe config

# 执行 skill
python Tools/Skills/cli.py run system '{"action": "ping"}'

# 启动 HTTP 服务
python Tools/Skills/cli.py server --port 8766

# 无 socket 依赖探测
python Tools/Skills/cli.py check
```

## 目录结构

```
Tools/Skills/
├── README.md              # 本文档
├── __init__.py            # 包导出
├── skill_base.py          # Skill、SkillRegistry、SkillResult 基类
├── server.py              # HTTP 服务（基于 stdlib http.server）
├── cli.py                 # CLI 运行器
├── runtime.py             # 运行环境检查
├── launcher.sh            # Linux/macOS Shell 启动脚本
├── launcher.bat           # Windows 启动脚本
├── task_runtime.py        # 异步任务 ID、状态、停止与恢复记录
└── skills/
    ├── __init__.py        # 注册中心（注册所有 skill）
    ├── system_skill.py    # 系统信息与健康检查
    ├── config_skill.py    # 配置管理
    ├── translate_skill.py # 翻译任务执行
    ├── queue_skill.py     # 任务队列管理
    ├── profile_skill.py   # 配置方案管理
    ├── file_skill.py      # 文件操作
    └── agent_skill.py     # 外部 Agent 会话租约
```

## 执行模式与任务生命周期

`system`、`config`、`profile`、`file` 在当前进程内执行；`translate.run` 和
`queue.run` 使用共享 `TaskSpec/TaskContract` 生成参数，并通过统一任务管理器启动隔离的 CLI 子进程。
Skills 不会让 Agent 直接写翻译缓存，也不会自动代理 WebServer 路由。

`translate.run` 默认立即返回稳定的 `task_id`：

```json
{"success": true, "data": {"task_id": "...", "status": "running", "running": true}}
```

**查询与停止翻译：**
```bash
curl -X POST http://127.0.0.1:8766/skills/translate \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action":"status", "task_id":"<task-id>"}'

curl -X POST http://127.0.0.1:8766/skills/translate \
  -H "Content-Type: application/json" \
  -H "X-AiNiee-Skills-Auth: your-token" \
  -d '{"action":"stop", "task_id":"<task-id>"}'
```

随后使用 `{"action":"status","task_id":"..."}` 查询，或使用
`{"action":"stop","task_id":"..."}` 请求停止。状态可能为
`starting`、`running`、`stopping`、`completed`、`failed`、`stopped`、`orphaned`；
最近任务记录保存在 `Resource/automation_progress/skills_tasks.json`（只保存脱敏
元数据，写入失败时仍可使用内存状态）。需要同步等待时可在请求中传入 `"wait": true`。

`queue.run` 与 `translate.run` 使用相同的 `task_id`、`status`、`stop` 和 `wait` 协议；
队列任务类型为 `queue`，进程内同类任务同时只能运行一个。

文件、队列和任务输入路径默认限制在项目目录与系统临时目录；需要访问其他工作区时，
可通过 `AINIEE_SKILLS_ALLOWED_PATHS`（按系统路径分隔符列出多个根目录）显式加入。仅在
完全可信的本机自动化中使用 `AINIEE_SKILLS_ALLOW_EXTERNAL_PATHS=1` 放开路径边界。

HTTP 与独立 CLI 的 Skill 参数都支持裸对象和 `{"args": {...}}` 包装对象；包装对象
不得再混入同级字段，非对象 JSON 统一返回 `INVALID_ARGUMENTS`。

## MCP 与 Skills 对比

| 特性 | MCP Server | Skills Server |
|------|-----------|---------------|
| 协议 | JSON-RPC 2.0 | REST/JSON |
| 依赖 | mcp、fastapi、uvicorn | 仅标准库 |
| 传输层 | stdio / streamable-http / SSE | HTTP |
| 路由发现 | 自动（全部 /api/*） | 手动精选 |
| 执行模式 | WebServer 代理 | 进程内 Skill / CLI 子进程 |
| 默认端口 | 8765 | 8766 |

## 扩展：添加新的 Skill

1. 在 `Tools/Skills/skills/` 下新建文件（如 `my_skill.py`）
2. 继承 `Skill` 基类，实现 `meta` 和 `execute`
3. 在 `Tools/Skills/skills/__init__.py` 中注册

示例：

```python
from Tools.Skills.skill_base import Skill, SkillMeta, SkillParameter, SkillResult

class MySkill(Skill):
    @property
    def meta(self):
        return SkillMeta(
            name="my_skill",
            description="做些有用的事。",
            category="custom",
            parameters=[SkillParameter(name="input", type="string", required=True)],
        )

    def execute(self, args):
        return SkillResult.ok({"processed": args.get("input", "")})
```
