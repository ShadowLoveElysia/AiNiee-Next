"""JSONL 命令和事件协议的最小实现，供 Rich、CLI 和 sidecar 共用。"""
from __future__ import annotations

import json
from typing import Any, Iterable

COMMANDS = frozenset({"prompt", "steer", "follow_up", "abort", "get_state", "new_session"})
# ``plan_ready`` is emitted before a run is confirmed and is part of the
# public lifecycle stream consumed by CLI/TUI clients.
EVENTS = frozenset({"agent_start", "turn_start", "message_update", "tool_call", "tool_result", "confirmation_required", "plan_ready", "task_start", "task_end", "agent_end", "error"})


def encode_message(message: dict[str, Any]) -> str:
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise ValueError("JSONL message requires a string type")
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode_messages(lines: Iterable[str]) -> list[dict[str, Any]]:
    result = []
    for line in lines:
        if not line or not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("JSONL message requires an object with string type")
        result.append(value)
    return result


def validate_command(command: dict[str, Any]) -> dict[str, Any]:
    if command.get("type") not in COMMANDS:
        raise ValueError(f"Unsupported Agent command: {command.get('type')!r}")
    request_id = command.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ValueError("request_id must be a string")
    return command
