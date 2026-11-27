"""Bounded, cancellable auxiliary jobs owned by the API runtime."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import threading
import uuid

from ModuleFolders.Infrastructure.SensitiveData import split_sensitive_data
from .activities import register_activity


class JobConflict(RuntimeError):
    pass


class CancelledJob(RuntimeError):
    pass


class CommittedResult:
    """An irreversible final publication completed despite a late cancel request."""
    def __init__(self, value):
        self.value = value


class JobManager:
    def __init__(self, *, history_limit: int = 100):
        self._lock = threading.RLock()
        self._records = OrderedDict()
        self._history_limit = history_limit

    def active(self):
        with self._lock:
            return any(record["state"]["running"] and record["exclusive"] for record in self._records.values())

    def any_running(self):
        with self._lock:
            return any(record["state"]["running"] for record in self._records.values())

    def start(self, kind, work, *, metadata=None, exclusive=True):
        from .manager import TaskManager
        manager = TaskManager()
        with manager._lock, self._lock:
            if not manager._accepting_tasks:
                raise JobConflict("The API owner is shutting down")
            if exclusive:
                conflict = manager.task_conflict_detail()
                if conflict:
                    raise JobConflict(conflict)
                from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
                if QueueManager(read_only=True).is_running:
                    raise JobConflict("A queue is already running in the host")
            if any(row["state"]["running"] and row["state"]["kind"] == kind for row in self._records.values()):
                raise JobConflict("An operation of this kind is already running")
            while len(self._records) >= self._history_limit:
                completed = next((key for key, value in self._records.items() if not value["state"]["running"]), None)
                if completed is None:
                    raise JobConflict("The background operation limit has been reached")
                self._records.pop(completed)
            job_id = uuid.uuid4().hex
            state = {
                "job_id": job_id, "kind": kind, "status": "running", "running": True,
                "created_at": self._now(), "finished_at": None, "result": None, "error": None,
                "metadata": split_sensitive_data(metadata or {})[0], "cancel_requested": False,
            }
            record = {"state": state, "cancel": threading.Event(), "exclusive": exclusive}
            self._records[job_id] = record
            thread = threading.Thread(target=self._run, args=(record, work), daemon=True, name=f"api-{kind}")
            record["thread"] = thread
            try:
                thread.start()
            except BaseException:
                self._records.pop(job_id)
                raise
            return deepcopy(state)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _run(self, record, work):
        result, error, status, committed = None, None, "completed", False
        try:
            if record["cancel"].is_set():
                raise CancelledJob()
            value = work(record["cancel"])
            committed = isinstance(value, CommittedResult)
            result = split_sensitive_data(value.value if committed else value)[0]
        except CancelledJob:
            status = "stopped"
        except Exception as exc:
            status, error = "failed", {"code": type(exc).__name__, "message": "Operation failed; inspect the local diagnostic report."}
        with self._lock:
            if record["cancel"].is_set() and not committed:
                status, result = "stopped", None
            record["state"].update(status=status, running=False, finished_at=self._now(), result=result, error=error)

    def status(self, job_id):
        with self._lock:
            if job_id not in self._records:
                raise KeyError("Unknown job id")
            return deepcopy(self._records[job_id]["state"])

    def list(self):
        with self._lock:
            return [deepcopy(row["state"]) for row in reversed(self._records.values())]

    def cancel(self, job_id):
        with self._lock:
            if job_id not in self._records:
                raise KeyError("Unknown job id")
            record = self._records[job_id]
            if record["state"]["running"]:
                record["cancel"].set()
                record["state"]["status"] = "stopping"
                record["state"]["cancel_requested"] = True
            return deepcopy(record["state"])

    def shutdown(self):
        with self._lock:
            records = list(self._records.values())
            for record in records:
                if record["state"]["running"]:
                    record["cancel"].set()
                    record["state"]["status"] = "stopping"
                    record["state"]["cancel_requested"] = True
            return not any(row["state"]["running"] for row in records)


_manager = JobManager()
register_activity("auxiliary_jobs", _manager.active, _manager.shutdown)


def get_job_manager():
    return _manager
