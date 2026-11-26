"""Configuration access policies shared by API adapters and task use cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ModuleFolders.Infrastructure.ApiSecurity import (
    contains_redacted_secret, restore_redacted_secrets, sanitize_data_for_mcp,
    strip_mcp_security_metadata,
)
from ModuleFolders.Infrastructure.RemoteAccessPolicy import REMOTE_ACCESS_CONFIG_KEY
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    ConfigConflictError, config_revision, config_transaction, load_effective_config, patch_effective_config,
)
from ModuleFolders.Infrastructure.TaskConfig.AgentBatchSettings import ensure_agent_batch_change_confirmed


@dataclass(frozen=True)
class CallerContext:
    """Created by an authenticated adapter, never populated from the request body."""
    channel: Literal["web", "mcp", "worker"]
    confirm_advanced_change: bool = False
    confirm_agent_batch_change: bool = False


@config_transaction()
def read_configuration(caller: CallerContext) -> dict:
    config = load_effective_config(create_missing=False)
    config["_config_revision"] = config_revision(config)
    checks = {
        "newline_character_count_check": False, "return_to_original_text_check": False,
        "residual_original_text_check": False, "reply_format_check": False,
    }
    if not isinstance(config.get("response_check_switch"), dict):
        config["response_check_switch"] = checks
    return project_configuration(dict(config), caller)


def project_configuration(config: dict, caller: CallerContext) -> dict:
    if caller.channel == "mcp":
        return sanitize_data_for_mcp(config, path="/api/config")
    if caller.channel != "web":
        raise PermissionError("This channel cannot manage configuration.")
    return config


@config_transaction()
def update_configuration(changes: dict, caller: CallerContext) -> str:
    if caller.channel not in {"web", "mcp"}:
        raise PermissionError("This channel cannot manage configuration.")
    changes = strip_mcp_security_metadata(changes)
    revision = changes.pop("_config_revision", None)
    if revision is not None and not isinstance(revision, str):
        raise ValueError("Invalid configuration revision.")
    if caller.channel == "mcp":
        if any(key in changes for key in ("mcp_server_port", "mcp_server_host")) and not caller.confirm_advanced_change:
            raise PermissionError("Advanced MCP settings require explicit change confirmation.")
        ensure_agent_batch_change_confirmed(changes, caller.confirm_agent_batch_change)

    full_snapshot = {"active_profile", "active_rules_profile", "platforms"} <= changes.keys()

    def prepare(current, incoming):
        if any(key in incoming and incoming[key] != current[key] for key in ("active_profile", "active_rules_profile")):
            raise ConfigConflictError()
        if revision is None and full_snapshot:
            raise ConfigConflictError()
        if caller.channel == "mcp":
            incoming = restore_redacted_secrets(incoming, current)
            if contains_redacted_secret(incoming):
                raise ValueError("Configuration contains an unresolved redacted secret placeholder.")
        incoming.pop(REMOTE_ACCESS_CONFIG_KEY, None)
        return incoming

    updated = patch_effective_config(changes, expected_revision=revision, prepare=prepare, merge_nested=not full_snapshot)
    return config_revision(updated)
