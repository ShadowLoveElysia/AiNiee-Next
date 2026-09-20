"""External Agent session lifecycle Skill.

This adapter exposes only the short-lived registration lease.  It does not
share the Skills authentication token with an Agent session and never accepts
or persists provider credentials.  The session registry remains transport
agnostic so MCP and Skills can use the same runtime state.
"""
from __future__ import annotations

from typing import Any, Dict

from ModuleFolders.Service.Agent.ExternalAgentSession import (
    ExternalAgentSessionError,
    ExternalAgentSessionRegistry,
)
from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    normalize_skill_action,
    reject_unknown_skill_fields,
)


class AgentSkill(Skill):
    """Register and inspect an external Agent connection lease."""

    def __init__(self, registry: ExternalAgentSessionRegistry | None = None) -> None:
        super().__init__()
        self._registry = registry

    @property
    def registry(self) -> ExternalAgentSessionRegistry:
        if self._registry is None:
            # Import lazily so listing the Skills remains usable in minimal
            # environments and both MCP and Skills resolve one shared registry.
            from ModuleFolders.Service.Agent.ExternalAgentSession import (
                get_external_agent_session_registry,
            )

            self._registry = get_external_agent_session_registry()
        return self._registry

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="agent_session",
            description=(
                "Register, renew, inspect, or disconnect an external Agent session. "
                "The lease is separate from the Skills HTTP authentication token."
            ),
            category="agent",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: register, heartbeat, status, or unregister.",
                    type="string",
                    required=True,
                    enum=["register", "heartbeat", "status", "unregister"],
                ),
                SkillParameter(name="session_id", description="Session lease id.", type="string"),
                SkillParameter(name="agent_instance_id", description="Stable external Agent instance id.", type="string"),
                SkillParameter(name="protocol_version", description="Agent session protocol version.", type="string"),
                SkillParameter(name="client_name", description="External client name.", type="string"),
                SkillParameter(name="client_version", description="External client version.", type="string"),
                SkillParameter(name="capabilities", description="Declared capabilities.", type="array"),
                SkillParameter(name="supported_modes", description="Supported AiNiee execution modes.", type="array"),
                SkillParameter(name="transport", description="Transport label (for diagnostics only).", type="string"),
                SkillParameter(name="requested_lease_seconds", description="Requested lease duration.", type="integer"),
                SkillParameter(name="user_confirmed_external_processing", description="User confirmed sending work to the external Agent.", type="boolean"),
                SkillParameter(name="active_only", description="Only return a live session for status.", type="boolean"),
                SkillParameter(name="last_task_id", description="Optional task id carried by heartbeat.", type="string"),
                SkillParameter(name="active_batch_id", description="Optional batch id carried by heartbeat.", type="string"),
                SkillParameter(name="reason", description="Disconnect reason.", type="string"),
            ],
            examples=[
                {
                    "action": "register",
                    "agent_instance_id": "workbuddy-desktop-1",
                    "client_name": "WorkBuddy",
                    "supported_modes": ["external_agent"],
                    "capabilities": ["translation", "proofread"],
                    "user_confirmed_external_processing": True,
                },
                {"action": "heartbeat", "session_id": "sess_example", "agent_instance_id": "workbuddy-desktop-1"},
                {"action": "status"},
                {"action": "unregister", "session_id": "sess_example", "agent_instance_id": "workbuddy-desktop-1"},
            ],
        )

    @staticmethod
    def _error(exc: ExternalAgentSessionError) -> SkillResult:
        return SkillResult.fail(str(exc), exc.code)

    @staticmethod
    def _onboarding_accepted() -> bool:
        try:
            from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_root_config

            return load_root_config().get("external_agent_onboarding_status") == "accepted"
        except Exception:
            return False

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        invalid = reject_unknown_skill_fields(
            args,
            {
                "action", "session_id", "agent_instance_id", "protocol_version",
                "client_name", "client_version", "capabilities", "supported_modes",
                "transport", "requested_lease_seconds", "user_confirmed_external_processing",
                "active_only", "last_task_id", "active_batch_id", "reason",
            },
            skill_name="agent_session",
        )
        if invalid:
            return invalid
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        try:
            if action == "register":
                if not self._onboarding_accepted():
                    return SkillResult.fail(
                        "External Agent onboarding has not been accepted by the user.",
                        "ONBOARDING_NOT_ACCEPTED",
                    )
                # Pass only the documented protocol fields; this prevents a
                # future registry extension from accidentally accepting secrets.
                fields = {
                    key: args[key]
                    for key in (
                        "agent_instance_id", "protocol_version", "client_name", "client_version",
                        "capabilities", "supported_modes", "transport", "requested_lease_seconds",
                        "user_confirmed_external_processing",
                    )
                    if key in args
                }
                return SkillResult.ok(self.registry.register(fields))

            session_id = args.get("session_id")
            if action == "heartbeat":
                if "agent_instance_id" not in args:
                    return SkillResult.fail("Missing required parameter: agent_instance_id", "MISSING_PARAM")
                fields = {
                    key: args[key]
                    for key in ("last_task_id", "active_batch_id")
                    if key in args
                }
                return SkillResult.ok(
                    self.registry.heartbeat(
                        session_id,
                        agent_instance_id=args.get("agent_instance_id"),
                        **fields,
                    )
                )

            if action == "unregister":
                return SkillResult.ok(
                    self.registry.unregister(
                        session_id,
                        agent_instance_id=args.get("agent_instance_id"),
                        reason=args.get("reason", "client_shutdown"),
                    )
                )

            if action == "status":
                active_only = args.get("active_only", False)
                if not isinstance(active_only, bool):
                    return SkillResult.fail("active_only must be a boolean.", "INVALID_ARGUMENTS")
                if session_id is not None:
                    if not isinstance(session_id, str) or not session_id.strip():
                        return SkillResult.fail("session_id must be a non-empty string.", "INVALID_ARGUMENTS")
                    # ``status(id)`` returns the audit snapshot; ``get`` is
                    # used for the optional active-only filter.
                    result = self.registry.get(session_id, active_only=active_only)
                    if result is None:
                        return SkillResult.fail("session does not exist", "SESSION_NOT_FOUND")
                    return SkillResult.ok(result)
                if hasattr(self.registry, "status"):
                    return SkillResult.ok(self.registry.status())
                # Compatibility fallback for an older injected registry.
                return SkillResult.ok({"sessions": [], "count": 0, "active_count": len(self.registry)})

            return SkillResult.fail(f"Unknown agent_session action: {action}", "INVALID_ACTION")
        except ExternalAgentSessionError as exc:
            return self._error(exc)
        except (TypeError, ValueError) as exc:
            return SkillResult.fail(str(exc), "INVALID_ARGUMENTS")


__all__ = ["AgentSkill"]
