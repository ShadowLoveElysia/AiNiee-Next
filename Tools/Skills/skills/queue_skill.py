from __future__ import annotations

import os
import sys
import threading
from typing import Any, Dict

from ModuleFolders.Infrastructure.TaskContract import (
    TaskContractError,
    normalize_task_name,
)
from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager, QueueTaskItem
from Tools.Skills.skill_base import Skill, SkillMeta, SkillParameter, SkillResult, normalize_skill_action
from Tools.Skills.skills.common import (
    QUEUE_SECURITY_PATH,
    SkillPathError,
    sanitize_payload,
    task_skill_parameters,
    task_spec_from_skill_args,
    task_subprocess_invocation,
    validate_wait_options,
    validate_skill_path,
)
from Tools.Skills.task_runtime import TaskAlreadyRunningError, get_task_manager


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

# ``QueueManager`` is intentionally shared by the TUI/Web integrations.  The
# Skills HTTP server is threaded, so serialize one complete queue read/modify/
# write transaction here; the manager's file lock alone cannot protect its
# in-memory ``queue_file`` and ``tasks`` fields when requests target different
# queue paths.
_QUEUE_SKILL_TRANSACTION_LOCK = threading.RLock()


def _queue_manager() -> QueueManager:
    manager = QueueManager()
    manager.load_tasks()
    return manager


def _queue_manager_for(path: Any = None) -> QueueManager:
    manager = QueueManager()
    if path is not None and path != "":
        manager.load_tasks(validate_skill_path(path, field_name="queue_file"))
    else:
        manager.load_tasks(manager.default_queue_file)
    return manager


def _task_type_label(value: Any) -> str:
    try:
        return normalize_task_name(value)
    except TaskContractError:
        return str(value)


def _task_to_public_dict(index: int, task: QueueTaskItem) -> Dict[str, Any]:
    item = task.to_dict()
    item["index"] = index
    item["task_type"] = _task_type_label(item.get("task_type"))
    return sanitize_payload(item, path=QUEUE_SECURITY_PATH)


def _coerce_index(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("index must be an integer") from exc


class QueueSkill(Skill):
    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="queue",
            description="Manage the translation task queue.",
            category="queue",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: list, add, remove, clear, run, status, stop.",
                    type="string",
                    required=True,
                    enum=["list", "add", "remove", "clear", "run", "status", "stop"],
                ),
                SkillParameter(
                    name="task_id",
                    description="Stable task ID returned by run (for status/stop).",
                    type="string",
                    required=False,
                ),
                SkillParameter(
                    name="wait",
                    description="Wait for completion before returning (default false).",
                    type="boolean",
                    required=False,
                    default=False,
                ),
                SkillParameter(
                    name="wait_timeout",
                    description="Maximum seconds to wait when wait=true.",
                    type="integer",
                    required=False,
                ),
                SkillParameter(
                    name="task_type",
                    description="Task type for new queue items (translate/polish/all_in_one).",
                    type="string",
                    required=False,
                ),
                *task_skill_parameters(),
                SkillParameter(
                    name="index",
                    description="Index of the queue item to remove.",
                    type="integer",
                    required=False,
                ),
                SkillParameter(
                    name="queue_file",
                    description="Optional queue JSON path used by all queue actions.",
                    type="string",
                    required=False,
                ),
            ],
            examples=[
                {"action": "list"},
                {
                    "action": "add",
                    "input_path": "/path/to/file.txt",
                    "task_type": "translate",
                    "profile": "default",
                },
                {"action": "remove", "index": 0},
                {"action": "clear"},
            ],
        )

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        action = normalize_skill_action(args)
        if action in {"list", "add", "remove", "clear"}:
            with _QUEUE_SKILL_TRANSACTION_LOCK:
                return self._execute(args)
        return self._execute(args)

    def _execute(self, args: Dict[str, Any]) -> SkillResult:
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        if action == "status":
            unexpected = sorted(set(args) - {"action", "task_id"})
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue status fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            manager = get_task_manager()
            task_id_value = args.get("task_id")
            if task_id_value is not None and not isinstance(task_id_value, str):
                return SkillResult.fail("task_id must be a string.", "INVALID_ARGUMENTS")
            task_id = str(task_id_value or "").strip()
            if task_id:
                record = manager.get(task_id)
                if record is None:
                    return SkillResult.fail(
                        f"Unknown task_id: {task_id}", "TASK_NOT_FOUND"
                    )
            else:
                record = manager.latest(task_type="queue")
                if record is None:
                    return SkillResult.ok(
                        {"task_id": None, "running": False, "status": "idle"}
                    )
            record = dict(record)
            record["running"] = record.get("status") in {
                "starting",
                "running",
                "stopping",
            }
            return SkillResult.ok(record)

        if action == "stop":
            unexpected = sorted(set(args) - {"action", "task_id"})
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue stop fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            manager = get_task_manager()
            task_id_value = args.get("task_id")
            if task_id_value is not None and not isinstance(task_id_value, str):
                return SkillResult.fail("task_id must be a string.", "INVALID_ARGUMENTS")
            task_id = str(task_id_value or "").strip()
            if not task_id:
                latest = manager.latest(task_type="queue")
                task_id = str((latest or {}).get("task_id") or "")
            if not task_id:
                return SkillResult.fail(
                    "task_id is required when no queue task exists.",
                    "TASK_NOT_FOUND",
                )
            record = manager.cancel(task_id)
            if record is None:
                return SkillResult.fail(
                    f"Unknown task_id: {task_id}", "TASK_NOT_FOUND"
                )
            return SkillResult.ok(record)

        if action == "list":
            unexpected = sorted(set(args) - {"action", "queue_file"})
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue list fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            try:
                manager = _queue_manager_for(args.get("queue_file"))
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            return SkillResult.ok({
                "queue_file": manager.queue_file,
                "count": len(manager.tasks),
                "items": [
                    _task_to_public_dict(i, task)
                    for i, task in enumerate(manager.tasks)
                ],
            })

        if action == "add":
            try:
                payload = dict(args)
                queue_file = payload.pop("queue_file", None)
                spec = task_spec_from_skill_args(payload)
                if spec.api_key:
                    return SkillResult.fail(
                        "api_key cannot be stored in a queue file. Use a profile or run the task directly.",
                        "INVALID_TASK",
                    )
                task_fields = spec.to_queue_fields()
            except SkillPathError as e:
                return SkillResult.fail(str(e), e.code)
            except TaskContractError as e:
                return SkillResult.fail(str(e), "INVALID_TASK")

            try:
                manager = _queue_manager_for(queue_file)
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            if getattr(manager, "last_save_error", "") == "conflict":
                return SkillResult.fail(
                    "Queue changed since it was loaded; reload and retry.",
                    "QUEUE_CONFLICT",
                )
            item = QueueTaskItem(**task_fields)
            try:
                if not manager.add_task(item):
                    conflict = getattr(manager, "last_save_error", "") == "conflict"
                    return SkillResult.fail(
                        "Queue changed since it was loaded; reload and retry."
                        if conflict else "Failed to write queue file.",
                        "QUEUE_CONFLICT" if conflict else "WRITE_ERROR",
                    )
            except Exception as e:
                return SkillResult.fail(f"Failed to write queue file: {e}", "WRITE_ERROR")

            index = len(manager.tasks) - 1
            return SkillResult.ok({
                "added": True,
                "queue_file": manager.queue_file,
                "index": index,
                "total": len(manager.tasks),
                "item": _task_to_public_dict(index, item),
            })

        if action == "remove":
            unexpected = sorted(set(args) - {"action", "index", "queue_file"})
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue remove fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            if args.get("index") is None:
                return SkillResult.fail("index is required for remove.", "MISSING_PARAM")
            try:
                index = _coerce_index(args.get("index"))
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_INDEX")

            try:
                manager = _queue_manager_for(args.get("queue_file"))
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            if index < 0 or index >= len(manager.tasks):
                return SkillResult.fail(
                    f"Index {index} out of range (0-{len(manager.tasks) - 1}).", "INVALID_INDEX"
                )
            if not manager.can_modify_task(index):
                return SkillResult.fail(
                    f"Queue item {index} is locked and cannot be removed.", "LOCKED"
                )
            removed = _task_to_public_dict(index, manager.tasks[index])
            if manager.remove_task(index):
                return SkillResult.ok({
                    "removed": True,
                    "item": removed,
                    "total": len(manager.tasks),
                })
            conflict = getattr(manager, "last_save_error", "") == "conflict"
            return SkillResult.fail(
                "Queue changed since it was loaded; reload and retry."
                if conflict else "Failed to write queue file.",
                "QUEUE_CONFLICT" if conflict else "WRITE_ERROR",
            )

        if action == "clear":
            unexpected = sorted(set(args) - {"action", "queue_file"})
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue clear fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            try:
                manager = _queue_manager_for(args.get("queue_file"))
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            locked = [
                index
                for index, _task in enumerate(manager.tasks)
                if not manager.can_modify_task(index)
            ]
            if locked:
                return SkillResult.fail(
                    f"Cannot clear queue while locked items exist: {locked}",
                    "LOCKED",
                )
            try:
                if not manager.clear_tasks():
                    conflict = getattr(manager, "last_save_error", "") == "conflict"
                    return SkillResult.fail(
                        "Queue changed since it was loaded; reload and retry."
                        if conflict else "Failed to write queue file.",
                        "QUEUE_CONFLICT" if conflict else "WRITE_ERROR",
                    )
                return SkillResult.ok({"cleared": True, "queue_file": manager.queue_file})
            except Exception as e:
                return SkillResult.fail(f"Failed to clear queue: {e}", "WRITE_ERROR")

        if action == "run":
            unexpected = sorted(
                set(args) - {"action", "queue_file", "wait", "wait_timeout"}
            )
            if unexpected:
                return SkillResult.fail(
                    f"Unknown queue run fields: {', '.join(unexpected)}",
                    "INVALID_TASK",
                )
            try:
                spec = task_spec_from_skill_args(
                    {
                        "task_type": "queue",
                        "queue_file": args.get("queue_file"),
                    }
                )
                cli_args, env = task_subprocess_invocation(spec)
                command = [sys.executable, *cli_args]
                wait_options = validate_wait_options(args)
                if isinstance(wait_options, SkillResult):
                    return wait_options
                wait_value, wait_timeout = wait_options
                manager = get_task_manager()
                record = manager.submit(
                    command,
                    env=env,
                    task_type="queue",
                    request=args,
                    timeout=3600,
                    exclusive_task_type="queue",
                )
            except TaskContractError as exc:
                return SkillResult.fail(str(exc), "INVALID_TASK")
            except SkillPathError as exc:
                return SkillResult.fail(str(exc), exc.code)
            except TaskAlreadyRunningError as exc:
                return SkillResult.fail(
                    str(exc),
                    "TASK_ALREADY_RUNNING",
                    data={"task_id": exc.task_id},
                )
            except OSError as exc:
                return SkillResult.fail(f"Failed to start queue: {exc}", "RUNTIME_ERROR")

            if record.get("status") == "failed":
                return SkillResult.fail(
                    str(record.get("error") or "Queue task failed to start."),
                    "RUNTIME_ERROR",
                    data=record,
                )
            if wait_value:
                final = manager.wait(record["task_id"], timeout=wait_timeout)
                return SkillResult.ok(final or record)
            return SkillResult.ok(record)

        return SkillResult.fail(f"Unknown queue action: {action}", "INVALID_ACTION")
