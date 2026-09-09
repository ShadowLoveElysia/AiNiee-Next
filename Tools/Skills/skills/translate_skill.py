from __future__ import annotations

import sys
from typing import Any, Dict

from ModuleFolders.Infrastructure.TaskContract import TaskContractError
from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    reject_unknown_skill_fields,
)
from Tools.Skills.skills.common import (
    SkillPathError,
    task_skill_parameters,
    task_spec_from_skill_args,
    task_subprocess_invocation,
    validate_wait_options,
)
from Tools.Skills.task_runtime import TaskAlreadyRunningError, get_task_manager


class TranslateSkill(Skill):
    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="translate",
            description="Execute translation, polishing, and all-in-one tasks.",
            category="task",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: run, status, stop.",
                    type="string",
                    required=True,
                    enum=["run", "status", "stop"],
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
                    description="Maximum seconds to wait when wait=true; omitted means no extra wait limit.",
                    type="integer",
                    required=False,
                ),
                SkillParameter(
                    name="task_type",
                    description="Type of task: translate, polish, or all_in_one.",
                    type="string",
                    required=False,
                    default="translate",
                    enum=["translate", "polish", "all_in_one"],
                ),
                *task_skill_parameters(include_manga=True),
            ],
            examples=[
                {
                    "action": "run",
                    "task_type": "translate",
                    "input_path": "/path/to/file.txt",
                    "source_lang": "Japanese",
                    "target_lang": "Chinese",
                    "profile": "default",
                },
                {"action": "status"},
                {"action": "stop", "task_id": "<task-id>"},
            ],
        )

    def _status(self, task_id: Any = None) -> SkillResult:
        manager = get_task_manager()
        if task_id is not None and task_id != "":
            if not isinstance(task_id, str):
                return SkillResult.fail("task_id must be a string.", "INVALID_ARGUMENTS")
            record = manager.get(str(task_id))
            if record is None:
                return SkillResult.fail(f"Unknown task_id: {task_id}", "TASK_NOT_FOUND")
        else:
            record = manager.latest(task_type="translate")
            if record is None:
                return SkillResult.ok({"task_id": None, "running": False, "status": "idle"})
        record = dict(record)
        record["running"] = record.get("status") in {"starting", "running", "stopping"}
        return SkillResult.ok(record)

    def _stop(self, task_id: Any = None) -> SkillResult:
        manager = get_task_manager()
        if task_id is not None and not isinstance(task_id, str):
            return SkillResult.fail("task_id must be a string.", "INVALID_ARGUMENTS")
        selected = str(task_id or "").strip()
        if not selected:
            latest = manager.latest(task_type="translate")
            selected = str((latest or {}).get("task_id") or "")
        if not selected:
            return SkillResult.fail("task_id is required when no translation task exists.", "TASK_NOT_FOUND")
        record = manager.cancel(selected)
        if record is None:
            return SkillResult.fail(f"Unknown task_id: {selected}", "TASK_NOT_FOUND")
        return SkillResult.ok(record)

    def _submit_translate(self, args: Dict[str, Any]) -> SkillResult:
        invalid = reject_unknown_skill_fields(
            args,
            {
                "action", "task_type", "input_path", "output_path", "profile",
                "rules_profile", "source_lang", "target_lang", "project_type",
                "resume", "queue_file", "platform", "model", "api_url", "api_key",
                "failover", "threads", "retry", "timeout", "rounds", "pre_lines",
                "lines_limit", "tokens_limit", "lines", "tokens", "think_depth",
                "thinking_budget", "polish_mode", "manga", "wait", "wait_timeout",
                "task", "run_all_in_one",
            },
            skill_name="translate",
        )
        if invalid:
            return invalid
        wait_options = validate_wait_options(args)
        if isinstance(wait_options, SkillResult):
            return wait_options
        wait, wait_timeout = wait_options

        try:
            spec = task_spec_from_skill_args(args)
            cli_args, env = task_subprocess_invocation(spec)
        except SkillPathError as exc:
            return SkillResult.fail(str(exc), exc.code)
        except TaskContractError as exc:
            return SkillResult.fail(str(exc), "INVALID_TASK")

        manager = get_task_manager()

        # The child receives the exact shared TaskContract argv; credentials stay in
        # its environment and are removed from the persisted/public task record.
        command = [sys.executable, *cli_args]
        try:
            record = manager.submit(
                command,
                env=env,
                task_type="translate",
                request=args,
                exclusive_task_type="translate",
            )
        except TaskAlreadyRunningError as exc:
            return SkillResult.fail(str(exc), "TASK_ALREADY_RUNNING", data={"task_id": exc.task_id})
        if record.get("status") == "failed":
            return SkillResult.fail(
                str(record.get("error") or "Translation task failed to start."),
                "RUNTIME_ERROR",
                data=record,
            )

        if wait:
            final = manager.wait(record["task_id"], timeout=wait_timeout) or record
            return SkillResult.ok(final)
        return SkillResult.ok(record)

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        action_value = args.get("action")
        if not isinstance(action_value, str):
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")
        action = action_value.strip().lower()

        if action == "status":
            invalid = reject_unknown_skill_fields(
                args, {"action", "task_id"}, skill_name="translate status"
            )
            if invalid:
                return invalid
            return self._status(args.get("task_id"))
        if action == "stop":
            invalid = reject_unknown_skill_fields(
                args, {"action", "task_id"}, skill_name="translate stop"
            )
            if invalid:
                return invalid
            return self._stop(args.get("task_id"))
        if action == "run":
            return self._submit_translate(args)

        return SkillResult.fail(f"Unknown translate action: {action}", "INVALID_ACTION")
