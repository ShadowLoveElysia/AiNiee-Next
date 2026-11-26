# AiNiee API

本目录提供独立 HTTP 入口，不要求 Web 前端构建产物。任务生命周期、预检和配置访问策略复用 `ModuleFolders/Service/TaskRuntime`；任务参数继续使用 `TaskSpec`。原有 `/api/*` 路径保留。

在项目 Python 环境中启动：

```bash
python -m Tools.APIServer.server --host 127.0.0.1 --port 8000
```

需要同时托管已有 Web 前端时加 `--serve-web`。原 CLI/TUI 的 Web 启动入口仍可使用。服务运行期间不能在同一个进程悄悄更换监听地址、模式或静态托管能力。

浏览器继续使用同源 session cookie，MCP 使用 bridge token，内部 worker 使用独立 token。跨进程 MCP 与已有 API 共用时设置相同的 `AINIEE_MCP_AUTH_TOKEN`；同进程启动时自动复用实际端口与已有 token，尚未设置时仅绑定一次。不要将 token 写进仓库、命令参数或日志。绑定非回环地址需要显式 `--allow-remote-access`。

`GET /api/system/runtime` 返回受保护的运行实例、工作区与协议身份。MCP 附加已有实例时验证身份；不会把远端 HTTP 任务与本地导入的 TaskManager 混用。MCP 自己启动的内嵌 API 仍与 MCP 进程同寿命，关闭该 owner 会清理它的任务；附加其他 owner 的 MCP 不会关闭该实例。

`POST /api/task/preview` 复用任务契约、指定 Profile 和运行参数校验，返回提示词检查、无独立 API key 参数的 argv 以及参数指纹。指纹仅描述规范请求与运行参数，不是执行快照锁，也不保证运行前配置不会变化。已有 `RuntimeSnapshot` 执行语义保持。

状态接口沿用 `cursors` 字段，值改为单调序号；`cursors_reset` 指示历史过期／任务清空后应替换快照。旧前端源码已适配，分发时需同时发布重新构建的 `Tools/WebServer`。HTTP 队列启动通过同一 TaskManager 的 CLI worker，不再要求 TUI 注入执行回调；队列 GET 使用只读观察模式，不清理或写回其他进程的锁／任务状态。

队列运行按条目汇总确认终态；部分完成、失败和待 Agent 不会伪报完成，具体结果位于 `stats.queue_summary`。取消会等待本次受控运行的后代退出，未确认清理时保留 `stopping`。运行归属通过继承环境中的随机标记及进程身份追踪，不等同于操作系统沙箱；Windows 进程树分支仍需原生验证。

队列行编辑优先使用 `task_id`，修改、删除、重排、清空和 raw 替换须传 `expected_revision` 查询参数，取自此前 GET 返回的行、`X-Queue-Revision` 响应头或 raw 的 `revision`。缺失版本返回 428，版本过期或活动行受保护返回 409。不要自动刷新版本后重放旧编辑。`/api/queue/edit_file` 已停用并返回 410，使用 `/api/queue/raw` 读取、编辑和提交草稿。

`/api/task/run` 不接受直接创建 `external_agent`；这类任务必须使用 `/api/task/external-agent-mode`，提供有效 MCP token 和本次任务的明确确认。底层共享用例重复检查可信调用上下文。monitor 模式在后端拒绝公开写操作，内部 worker 状态上报仍需独立 token。

提示词读写限制在 `Resource/Prompt` 内；上传同名文件生成独立名称，超出缓冲容量返回 `limit_reached`，不隐式删除。仅显式 `overwrite` 可在新文件保存成功后清理旧文件，活动任务期间拒绝替换。API worker 的本次参数和 Profile 选择保持内存作用域，不覆盖用户持久配置。

缓存列表和搜索接受 `project_path`，校对查询读取独立项目快照。编辑前先读取 `/api/cache/items`，将返回条目的 `project_path`、`project_id`、`file_path`、`text_index` 和 `revision`（作为 `expected_revision`）随 PUT 提交。缺失身份、条目移位或版本过期返回 409；成功响应返回新 `revision`。旧客户端需更新这些字段，并同步更新 Web 构建产物。缓存保存复用跨进程文件锁，已从磁盘加载的陈旧快照不能覆盖其它入口的新修改；这不提供两个进程同时翻译同一输出目录的任务调度支持。

上传先写入不可见暂存目录，完成后原子发布；取消或失败会清理本次暂存文件。API 任务或宿主队列运行期间拒绝临时输入删除和缓存编辑。临时文件发布锁位于上传目录内的 `.upload-state/`，文件列表不包含该目录。

配置 GET 返回 `_config_revision`；完整配置回写须保留该值，陈旧版本返回 409。成功保存返回新的 `revision`，客户端应更新自己的 `_config_revision` 后再继续编辑。小范围配置 patch 复用事务内读改写，不修改请求未包含的字段；高级 MCP 设置确认和远程访问开关限制保持生效。

`catalog.load_api_catalog()` 从路由源码和纯 DTO 获取分类、参数与 Schema，不启动 API、读取用户配置或导入可选漫画运行模块。未完整声明的 Schema 与可选运行能力明确标注为未确认。目录是声明能力，实际可用性由运行时接口决定。

主公开接口均提供请求、响应和错误声明；开放配置及规则扩展字段标记为动态结构，不宣称字段枚举完整。MCP 文件上传用 `upload_file`，二进制输出用 `download_file`；后者只接受目录声明的文件 GET，最多 32 MiB，保存到项目 `tmp/mcp-downloads` 的唯一文件，不覆盖旧文件。

当前迁出重点是任务、配置策略、运行管理和 MCP 桥接。其余规则、缓存、校对等旧 HTTP 实现暂留 `application.py`，后续按领域拆分；此版本没有新增多任务并发、SSE、全量任务历史或统一独立 Skills 运行实例。
