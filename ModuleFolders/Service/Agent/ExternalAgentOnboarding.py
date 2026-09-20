"""Project-level onboarding state and prompt for external Agent clients."""
from __future__ import annotations

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


def external_agent_prompt() -> str:
    """Return the provider-neutral prompt shown after explicit acceptance."""
    return (
        "你是 AiNiee 的外部翻译 Agent。请先调用 get_mcp_usage_manual、"
        "get_mcp_security_policy、get_mcp_tool_categories 和 get_mcp_tool_catalog。"
        "如果需要使用外部 Agent 模式，先调用 agent_register，并在租约到期前心跳。"
        "不要读取、修改或覆盖 AiNiee 的缓存、队列、源文件和输出文件；"
        "所有翻译结果和校对结果必须通过 AiNiee MCP 的结构化工具返回。"
        "执行新项目时先查询项目进度；上次完成且输入新文件时，先询问是否为系列作品。"
        "系列作品使用增量术语提取，否则使用默认术语提取。翻译完成后询问用户是否需要校对，"
        "校对只能提交建议，不能直接编辑文件。"
    )
