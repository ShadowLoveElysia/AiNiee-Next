"""Project-level onboarding state and prompt for external Agent clients."""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Mapping


_PROJECT_GUIDES = (
    ("项目规则", "AGENTS.md", "项目级操作边界和安全规则；必须先阅读"),
    ("项目规则", "Agents.md", "项目能力和客户端接入说明；必须先阅读"),
    ("项目规则", "SKILL.md", "AiNiee-Next 专用技能规则；处理用户文件前必须阅读"),
    ("项目总览", "README.md", "功能和常用入口概览；按需阅读"),
    ("项目总览", "README_EN.md", "英文功能和入口概览；按需阅读"),
    ("MCP 说明", "Tools/MCPServer/MCP_CLIENT_GUIDE.md", "MCP 首轮调用、安全边界和批次协议；连接 MCP 前必须阅读"),
    ("Skills 说明", "Tools/Skills/README.md", "Skills REST/CLI 协议；不使用 MCP 时阅读"),
    ("CLI 入口", "ainiee_cli.py", "本地 TUI/CLI 入口；只读源码，不能作为写入接口"),
    ("运行依赖", "pyproject.toml", "Python 项目依赖和工具配置；按需阅读"),
    ("运行依赖", "requirements.txt", "Python 依赖列表；按需阅读"),
)

_PROJECT_DIRECTORIES = (
    ("源码", "ModuleFolders", "核心业务源码；只能通过 MCP/Skills 执行受控操作"),
    ("MCP 服务", "Tools/MCPServer", "MCP 服务实现和说明；先阅读 MCP_CLIENT_GUIDE.md"),
    ("Skills 服务", "Tools/Skills", "Skills 服务实现和说明；先阅读 README.md"),
    ("资源", "Resource", "提示词、配置和运行资源；禁止 Agent 直接写入"),
    ("文档", "Docs", "用户教程和工作流文档；按任务选择阅读"),
    ("插件", "PluginScripts", "插件目录；未经用户明确许可不要启用或修改"),
    ("临时记录", "tmp", "本次任务记录和临时文件；只按需读取"),
    ("输出", "output", "AiNiee 输出目录；禁止覆盖已有输出"),
)

_RUNTIME_PATHS = (
    ("项目根配置", "Resource/config.json", "项目设置，可能关联凭证；禁止 Agent 直接读取内容或修改"),
    ("Profile 配置", "Resource/profiles", "Profile 来源；通过 MCP/Skills 读取和修改"),
    ("规则 Profile", "Resource/rules_profiles", "规则和术语配置；通过 MCP/Skills 读取和修改"),
    ("任务运行状态", "Resource/automation_progress", "任务账本、staging 和 writer lease；禁止手工改写"),
    ("缓存目录", "cache", "输入项目缓存；仅使用 MCP 返回的受控批次和 opaque locator"),
)

ONBOARDING_PENDING = "pending"
ONBOARDING_DECLINED = "declined"
ONBOARDING_ACCEPTED = "accepted"


def apply_onboarding_decision(root_config: dict, *, accepted: bool) -> dict:
    """Apply a user decision without changing the active Profile or task mode."""
    if not isinstance(root_config, dict):
        raise TypeError("root_config must be a dictionary")
    root_config["external_agent_onboarding"] = False
    root_config["external_agent_onboarding_status"] = (
        ONBOARDING_ACCEPTED if accepted else ONBOARDING_DECLINED
    )
    return root_config


def _display_path(value: Any) -> str:
    if value is None or not str(value).strip():
        return "未选择/未创建"
    try:
        return str(Path(str(value)).expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return str(value)


def _path_state(value: Any) -> str:
    if value is None or not str(value).strip():
        return "不存在"
    try:
        path = Path(str(value)).expanduser().resolve(strict=False)
        if not path.exists():
            return "不存在"
        if path.is_file():
            return f"文件，{path.stat().st_size} bytes"
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        names = [item.name + ("/" if item.is_dir() else "") for item in children[:20]]
        suffix = "；更多项目省略" if len(children) > 20 else ""
        return f"目录，{len(children)} 项；内容：{', '.join(names) or '空目录'}{suffix}"
    except (OSError, RuntimeError, ValueError):
        return "无法读取状态"


def _context_lines(context: Mapping[str, Any]) -> list[str]:
    fields = (
        ("终端当前路径", context.get("cwd"), "用于判断相对路径从哪里解析"),
        ("AiNiee 项目根目录", context.get("project_root"), "程序源码、MCP 和 Skills 的根目录"),
        ("本次源码输入", context.get("input_path"), "外部 Agent 只能通过受控工具读取和分批处理"),
        ("本次输出目录", context.get("output_path"), "AiNiee 负责生成的输出位置，不能直接写入"),
        ("当前 Profile", context.get("profile_path"), "配置来源；不要读取或传播密钥"),
        ("当前规则 Profile", context.get("rules_profile_path"), "术语和规则配置来源"),
    )
    lines = []
    for label, value, purpose in fields:
        display = _display_path(value)
        lines.append(f"- {label}：{display}（{_path_state(value)}；{purpose}）")
    for label, value, purpose in context.get("known_files", ()):
        display = _display_path(value)
        lines.append(f"- {label}：{display}（{_path_state(value)}；{purpose}）")
    return lines


def _layout_lines(project_root: Path) -> list[str]:
    """Describe known project files and directories from a fresh existence scan."""
    lines = ["- 项目说明和入口（仅列出当前实际存在的路径）："]
    seen_categories: set[str] = set()
    for category, relative, purpose in _PROJECT_GUIDES:
        if (project_root / relative).exists():
            if category not in seen_categories:
                lines.append(f"  [{category}]")
                seen_categories.add(category)
            lines.append(f"  - {relative}：{purpose}")
    if not seen_categories:
        lines.append("  - 未找到预设说明文件；先确认项目根目录")

    lines.append("- 项目目录分类（仅列出当前实际存在的目录）：")
    found_directory = False
    for category, relative, purpose in _PROJECT_DIRECTORIES:
        if (project_root / relative).is_dir():
            found_directory = True
            lines.append(f"  - {relative}/：{category}；{purpose}")
    if not found_directory:
        lines.append("  - 未找到预设项目目录；不要臆测路径")

    lines.append("- 运行时文件和目录（当前实际存在的路径）：")
    found_runtime = False
    for category, relative, purpose in _RUNTIME_PATHS:
        if (project_root / relative).exists():
            found_runtime = True
            lines.append(f"  - {relative}：{category}；{purpose}")
    if not found_runtime:
        lines.append("  - 未找到预设运行时路径")
    return lines


def external_agent_prompt(context: Mapping[str, Any] | None = None) -> str:
    """Build a provider-neutral prompt from the current project-path snapshot.

    The paths are discovery hints only. They never grant an Agent permission to
    read or write files outside the MCP/Skills contracts.
    """
    supplied = dict(context or {})
    project_root = Path(str(supplied.get("project_root") or Path(__file__).resolve().parents[3])).resolve()
    supplied.setdefault("cwd", os.getcwd())
    supplied.setdefault("project_root", str(project_root))
    supplied.setdefault("known_files", (
        ("MCP 客户端说明", project_root / "Tools" / "MCPServer" / "MCP_CLIENT_GUIDE.md", "首轮接入和安全边界"),
        ("Skills 说明", project_root / "Tools" / "Skills" / "README.md", "不使用 MCP 时的 REST/CLI 入口"),
        ("项目根配置", project_root / "Resource" / "config.json", "项目级设置；不要传播密钥"),
        ("批次与运行时状态", project_root / "Resource" / "automation_progress", "任务账本、staging 和恢复状态"),
    ))
    lines = _context_lines(supplied)
    # The prose lives in I18N so the copied Agent handoff follows the UI language.
    language = str(supplied.get("interface_language") or "zh_CN")
    template = _load_prompt_template(project_root, language)
    return template.format(
        context_lines="\n".join(lines),
        layout_lines="\n".join(_layout_lines(project_root)),
    )


def _load_prompt_template(project_root: Path, language: str) -> str:
    """Load the localized Agent prompt template without embedding its prose in Python."""
    source_root = Path(__file__).resolve().parents[3]
    candidates = [project_root / "I18N" / f"{language}.json"]
    if language != "zh_CN":
        candidates.append(project_root / "I18N" / "zh_CN.json")
    if project_root != source_root:
        candidates.extend((source_root / "I18N" / f"{language}.json", source_root / "I18N" / "zh_CN.json"))
    for path in candidates:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle).get("external_agent_prompt_template")
            if isinstance(value, str) and value.strip():
                return value
        except (OSError, ValueError, TypeError):
            continue
    raise RuntimeError("external_agent_prompt_template is missing from I18N")
