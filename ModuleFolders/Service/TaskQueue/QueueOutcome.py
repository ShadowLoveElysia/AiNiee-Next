"""Credential-free queue completion summaries shared by CLI and API workers."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


QUEUE_RESULT_PREFIX = "[QUEUE_RESULT] "
QUEUE_EXIT_CODES = {"completed": 0, "failed": 1, "partial": 3, "stopped": 130, "waiting_for_agent": 4}


def _queue_result(counts, stopped, error):
    total = sum(counts.values())
    completed = counts["completed"] + counts["enqueued"]
    failed = counts["error"] + counts["failed"] + counts["invalid"]
    partial = counts["partial"]
    pending = total - completed - failed - partial - counts["stopped"]
    if stopped or counts["stopped"]:
        outcome = "stopped"
    elif error or not total:
        outcome = "failed"
    elif completed == total:
        outcome = "completed"
    elif partial or (completed and (failed or pending)):
        outcome = "partial"
    elif counts["waiting_for_agent"] + counts["agent_disconnected"] == total:
        outcome = "waiting_for_agent"
    else:
        outcome = "failed"
    return {
        "outcome": outcome,
        "total": total,
        "counts": dict(counts),
        "error_code": error,
        "exit_code": QUEUE_EXIT_CODES[outcome],
        **({"stop_requested": True} if stopped else {}),
    }


def summarize_queue(tasks: Iterable, *, stopped: bool = False, error: str | None = None) -> dict:
    return _queue_result(Counter(str(getattr(task, "status", "unknown")) for task in tasks), stopped, error)


def validate_queue_result(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    counts = value.get("counts")
    total = value.get("total")
    if not isinstance(counts, dict) or not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return None
    if any(not isinstance(key, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0 for key, count in counts.items()):
        return None
    stopped = value.get("stop_requested", False)
    error = value.get("error_code")
    if type(stopped) is not bool or type(value.get("exit_code")) is not int:
        return None
    if error not in (None, "QUEUE_EMPTY", "QUEUE_LOAD_FAILED", "QUEUE_SAVE_FAILED", "QUEUE_EXECUTION_FAILED") or (error == "QUEUE_EMPTY" and total):
        return None
    expected = _queue_result(Counter(counts), stopped, error)
    if any(value.get(key) != expected[key] for key in ("total", "outcome", "exit_code")):
        return None
    return expected
