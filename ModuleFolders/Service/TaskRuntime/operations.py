"""Task use cases shared by authenticated transport adapters."""
from __future__ import annotations

import logging
from typing import Callable

from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.Infrastructure.TaskContract import TaskSpec
from .manager import TaskManager
from .preflight import preview_task
from .configuration import CallerContext


logger = logging.getLogger(__name__)


class TaskOperationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TaskOperations:
    def __init__(
        self,
        manager: TaskManager,
        flush_pending_cache: Callable[[TaskSpec], None] | None = None,
        queue_is_running: Callable[[], bool] | None = None,
    ):
        self.manager = manager
        self.flush_pending_cache = flush_pending_cache
        self.queue_is_running = queue_is_running

    def preview(self, spec: TaskSpec) -> dict:
        try:
            return preview_task(spec)
        except (ValueError, OSError) as exc:
            raise TaskOperationError("INVALID_TASK", str(exc)) from exc

    def _check_conflict(self) -> None:
        detail = self.manager.task_conflict_detail()
        if detail:
            raise TaskOperationError("TASK_CONFLICT", detail)
        if self.queue_is_running is not None and self.queue_is_running():
            raise TaskOperationError("QUEUE_CONFLICT", "A queue is already running in the host.")

    def start(
        self, spec: TaskSpec, *, caller: CallerContext | None = None,
        user_confirmed_external_processing: bool = False,
    ) -> dict:
        if spec.execution_mode == "external_agent":
            if caller is None or caller.channel != "mcp":
                raise TaskOperationError("EXTERNAL_CHANNEL_REQUIRED", "External-Agent tasks require the authenticated MCP channel.")
            if user_confirmed_external_processing is not True:
                raise TaskOperationError("EXTERNAL_PROCESSING_NOT_CONFIRMED", "Approve this task before preparing external-Agent input.")
        self._check_conflict()
        preview = self.preview(spec)
        if not preview["valid"]:
            raise TaskOperationError(
                "PROMPT_NOT_SELECTED",
                "Prompt is not selected: " + ", ".join(preview["missing_prompts"]),
            )
        if spec.manga:
            status = get_manga_feature_status(require_models=False)
            if not status.available:
                raise TaskOperationError("FEATURE_UNAVAILABLE", status.user_message())
        with self.manager._lock:
            self._check_conflict()
            if self.flush_pending_cache is not None:
                try:
                    self.flush_pending_cache(spec)
                except Exception:
                    # Preserve legacy launch semantics while omitting potentially sensitive errors.
                    logger.warning("Pending cache could not be flushed before task start.")
            task_id = self.manager.start_task(spec)
            if not task_id:
                self._check_conflict()
                raise TaskOperationError("TASK_START_FAILED", "Failed to start task process.")
            prepared = self.manager.lifecycle_status != "failed"
            result = {
                "success": prepared,
                "message": "Task started successfully." if prepared else "Task preparation failed.",
                "task_id": task_id,
                "status": self.manager.lifecycle_status,
                "running": self.manager._task_contract()["running"],
            }
            if spec.execution_mode == "external_agent":
                result.update({
                    "external_agent_cache_path": self.manager.external_agent_cache_path,
                    "external_agent_output_path": self.manager.external_agent_output_path,
                    "external_agent_bootstrap_status": self.manager.stats.get("external_agent_bootstrap_status"),
                })
            return result

    def stop(self, task_id: str | None = None) -> dict:
        if task_id is not None and not task_id.strip():
            raise TaskOperationError("INVALID_TASK", "task_id must not be empty.")
        with self.manager._lock:
            if not self.manager.stop_task(task_id):
                if task_id and task_id != self.manager.task_id:
                    raise TaskOperationError("TASK_NOT_FOUND", "Task not found.")
                raise TaskOperationError(
                    "STOP_PENDING", "Task process is still stopping; retry after it exits.",
                )
            return {
                "success": True,
                "message": "Stop signal sent.",
                **self.manager._task_contract(),
            }

    def status(
        self,
        task_id: str | None = None,
        log_cursor: int = 0,
        chart_cursor: int = 0,
        comparison_cursor: int = 0,
    ) -> dict:
        with self.manager._lock:
            if task_id is not None and task_id != self.manager.task_id:
                raise TaskOperationError("TASK_NOT_FOUND", "Task not found.")
            return self.manager.snapshot_status(log_cursor, chart_cursor, comparison_cursor)

    def external_status(self, task_id: str, status: str, message: str | None = None) -> dict:
        with self.manager._lock:
            if task_id != self.manager.task_id:
                raise TaskOperationError("TASK_NOT_FOUND", "Task not found.")
            applied = self.manager.update_external_agent_status(status, task_id, message)
            if not applied:
                raise TaskOperationError(
                    "EXTERNAL_TRANSITION_REJECTED", "External-Agent lifecycle transition rejected.",
                )
            return {"applied": True, **self.manager._task_contract()}
