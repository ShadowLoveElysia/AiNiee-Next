"""Shared configuration and consent checks for Agent batch acquisition."""
from typing import Any

AGENT_MAX_BATCHES_KEY = "external_agent_max_batches"
DEFAULT_AGENT_MAX_BATCHES = 8


def validate_agent_max_batches(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("external_agent_max_batches must be a positive integer")
    return value


def load_agent_max_batches() -> int:
    from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config

    config = load_effective_config(create_missing=False)
    return validate_agent_max_batches(config.get(AGENT_MAX_BATCHES_KEY, DEFAULT_AGENT_MAX_BATCHES))


def ensure_agent_batch_change_confirmed(body: Any, confirmed: bool) -> None:
    if not isinstance(body, dict) or AGENT_MAX_BATCHES_KEY not in body:
        return
    if confirmed is not True:
        raise PermissionError(
            "AGENT_BATCH_CHANGE_CONFIRMATION_REQUIRED: obtain explicit user consent for "
            "the new external_agent_max_batches value, then set confirm_agent_batch_change=true"
        )
    validate_agent_max_batches(body[AGENT_MAX_BATCHES_KEY])
