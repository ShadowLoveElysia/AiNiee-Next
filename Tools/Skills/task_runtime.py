"""可恢复的 Skills 子任务生命周期管理。

Skills 的 HTTP 请求线程不能阻塞在翻译子进程上。本模块只管理子进程的
生命周期和脱敏状态，不参与翻译器内部逻辑，也不把 API Key 写入状态文件。
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import signal
import subprocess
import copy
import contextlib
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX has no msvcrt
    msvcrt = None


ACTIVE_STATUSES = frozenset({"starting", "running", "stopping"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "stopped", "orphaned"})
_MAX_OUTPUT_CHARS = 4000
_MAX_RECORDS = 128
_DEFAULT_TIMEOUT_SECONDS = 3600
_REMOTE_STOP_GRACE_SECONDS = 10.0
_REDACTED_KEYS = {
    "api_key",
    "access_key",
    "secret_key",
    "password",
    "token",
    "auth_token",
}

class TaskAlreadyRunningError(RuntimeError):
    """Raised when an exclusive Skills task already has an active instance."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"A task of this type is already running: {task_id}")


def _looks_sensitive_key(name: Any) -> bool:
    normalized = str(name or "").strip().lower().replace("-", "_")
    return normalized in _REDACTED_KEYS or any(
        marker in normalized for marker in ("api_key", "access_key", "secret", "password", "auth_token")
    )


def _utc_timestamp() -> str:
    now = time.time()
    whole = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
    return f"{whole}.{int((now % 1) * 1000):03d}Z"


def _state_path() -> Path:
    configured = str(os.environ.get("AINIEE_SKILLS_TASK_STATE", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[2]
    # Keep runtime-only state under the existing ignored automation directory;
    # a normal source checkout must not become dirty just by starting Skills.
    return project_root / "Resource" / "automation_progress" / "skills_tasks.json"


def _tail(value: str | None) -> str:
    text = str(value or "")
    return text[-_MAX_OUTPUT_CHARS:]


def _state_lock_path(path: Path) -> Path:
    """Use a stable runtime lock directory so state folders stay clean."""
    normalized = str(path.expanduser().resolve())
    key = hashlib.sha256(
        os.path.normcase(normalized).encode("utf-8")
    ).hexdigest()
    try:
        root = Path(tempfile.gettempdir()) / "ainiee-skills-locks"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{key}.lock"
    except (OSError, RuntimeError):
        # Packaged/sandboxed environments may not expose a usable temp root;
        # retain a same-directory fallback rather than disabling locking.
        return path.with_name(f".{path.name}.lock")


@contextlib.contextmanager
def _state_file_lock(path: Path):
    """Serialize state-file read/merge/replace operations across processes."""
    lock_path = _state_lock_path(path)
    handle = None
    locked = False
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
        elif msvcrt is not None:
            # msvcrt.locking locks from the current file position. Ensure the
            # lock file has one byte so every process locks the same range.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            locked = True
        yield
    finally:
        if handle is not None:
            if locked:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    elif msvcrt is not None:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            handle.close()


class SkillTaskManager:
    """Thread-safe task registry backed by a small, credential-free JSON file."""

    def __init__(self, state_path: str | os.PathLike[str] | None = None) -> None:
        self.state_path = Path(state_path).expanduser().resolve() if state_path else _state_path()
        self._lock = threading.RLock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._processes: Dict[str, subprocess.Popen[str]] = {}
        self._events: Dict[str, threading.Event] = {}
        self._secrets: Dict[str, tuple[str, ...]] = {}
        self._reservations: set[str] = set()
        self._remote_reapers: Dict[str, threading.Thread] = {}
        self._load()

    def submit(
        self,
        command: Iterable[str],
        *,
        env: Mapping[str, str] | None = None,
        task_type: str = "translate",
        request: Mapping[str, Any] | None = None,
        timeout: int | float | None = _DEFAULT_TIMEOUT_SECONDS,
        exclusive_task_type: str | None = None,
    ) -> Dict[str, Any]:
        """Start a child process and return its stable task record immediately."""
        task_id = str(uuid.uuid4())
        execution_timeout = self._coerce_timeout(timeout)
        created_at = _utc_timestamp()
        record = {
            "task_id": task_id,
            "task_type": str(task_type),
            "status": "starting",
            "running": True,
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "exit_code": None,
            "cancel_requested": False,
            "error": None,
            "stdout": "",
            "stderr": "",
            "request": self._safe_request(request),
            "timeout_seconds": execution_timeout,
        }

        argv = [str(item) for item in command]
        child_env = dict(os.environ if env is None else env)
        secret_values = self._collect_secret_values(child_env, request)
        reservation_key = str(exclusive_task_type or "").strip()
        # Keep one lock order for every persistence path: manager lock first,
        # state-file lock second.  In particular, do not acquire ``self._lock``
        # from inside a state-file lock; the watcher snapshots under the
        # reverse order otherwise and concurrent starts/stops can deadlock.
        with self._lock:
            if reservation_key:
                active = next(
                    (
                        item
                        for item in self._records.values()
                        if item.get("task_type") == reservation_key
                        and item.get("status") in ACTIVE_STATUSES
                    ),
                    None,
                )
                if active is not None or reservation_key in self._reservations:
                    raise TaskAlreadyRunningError(
                        str((active or {}).get("task_id") or "reserved")
                    )
                self._reservations.add(reservation_key)

            # A credential may be needed by the child, but it must never enter
            # the persisted record or the public task response.  The state
            # lock is nested inside the manager lock to match ``_persist_locked``.
            reservation_lock = (
                _state_file_lock(self.state_path)
                if reservation_key
                else contextlib.nullcontext()
            )
            with reservation_lock:
                if reservation_key:
                    # The in-memory reservation closes the race within one
                    # process; this locked read closes it between server processes.
                    try:
                        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError):
                        persisted = {}
                    persisted_tasks = persisted.get("tasks", []) if isinstance(persisted, dict) else []
                    active = next(
                        (
                            item
                            for item in persisted_tasks
                            if isinstance(item, dict)
                            and item.get("task_type") == reservation_key
                            and item.get("status") in ACTIVE_STATUSES
                        ),
                        None,
                    )
                    if active is not None:
                        self._reservations.discard(reservation_key)
                        raise TaskAlreadyRunningError(str(active.get("task_id") or "reserved"))
                try:
                    popen_options: Dict[str, Any] = {}
                    if os.name == "nt":
                        creation_flags = int(
                            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        )
                        if creation_flags:
                            popen_options["creationflags"] = creation_flags
                    else:
                        popen_options["start_new_session"] = True
                    process = subprocess.Popen(
                        argv,
                        cwd=str(Path(__file__).resolve().parents[2]),
                        env=child_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        **popen_options,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    if reservation_key:
                        self._reservations.discard(reservation_key)
                    record.update(
                        status="failed",
                        running=False,
                        finished_at=_utc_timestamp(),
                        error=f"Failed to start task: {exc}",
                    )
                    self._touch(record)
                    self._records[task_id] = record
                    self._persist_locked(file_lock_held=bool(reservation_key))
                    return self._public_record(record)

                if reservation_key:
                    self._reservations.discard(reservation_key)
                record.update(
                    status="running",
                    started_at=_utc_timestamp(),
                    pid=process.pid,
                )
                self._touch(record)
                self._records[task_id] = record
                self._processes[task_id] = process
                self._events[task_id] = threading.Event()
                self._secrets[task_id] = secret_values
                self._trim_locked()
                self._persist_locked(file_lock_held=bool(reservation_key))

        watcher = threading.Thread(
            target=self._watch,
            args=(task_id, process),
            name=f"ainiee-skills-task-{task_id[:8]}",
            daemon=True,
        )
        try:
            watcher.start()
        except Exception as exc:
            # A worker must never be left unowned if the monitor thread could
            # not be created (for example during interpreter shutdown).
            self._terminate_process(process)
            with self._lock:
                failed = self._records.get(task_id, record)
                failed.update(
                    status="failed",
                    running=False,
                    finished_at=_utc_timestamp(),
                    error=f"Failed to start task monitor: {exc}",
                )
                self._touch(failed)
                self._processes.pop(task_id, None)
                self._events.setdefault(task_id, threading.Event()).set()
            self._persist_locked()
        return self._public_record(record)

    def get(self, task_id: str) -> Dict[str, Any] | None:
        with self._lock:
            record = self._records.get(str(task_id or ""))
            return self._public_record(record) if record else None

    def list(self, *, task_type: str | None = None) -> list[Dict[str, Any]]:
        with self._lock:
            records = list(self._records.values())
            if task_type:
                records = [item for item in records if item.get("task_type") == task_type]
            ordered = [
                item
                for _index, item in sorted(
                    enumerate(records),
                    key=lambda pair: (pair[1].get("created_at") or "", pair[0]),
                    reverse=True,
                )
            ]
            return [self._public_record(item) for item in ordered]

    def latest(self, *, task_type: str | None = None) -> Dict[str, Any] | None:
        """Return the newest known task without exposing internal process state."""
        records = self.list(task_type=task_type)
        return records[0] if records else None

    def has_active(self, *, task_type: str | None = None) -> bool:
        with self._lock:
            return any(
                item.get("status") in ACTIVE_STATUSES
                and (task_type is None or item.get("task_type") == task_type)
                for item in self._records.values()
            )

    def wait(self, task_id: str, timeout: int | float | None = None) -> Dict[str, Any] | None:
        """Wait for one task to reach a terminal state, then return its record."""
        key = str(task_id or "")
        wait_timeout = self._coerce_wait_timeout(timeout)
        with self._lock:
            if key not in self._records:
                return None
            event = self._events.setdefault(key, threading.Event())
            if self._records[key].get("status") in TERMINAL_STATUSES:
                return self._public_record(self._records[key])

        event.wait(timeout=wait_timeout)
        return self.get(key)

    def cancel(self, task_id: str) -> Dict[str, Any] | None:
        """Request cancellation; the watcher owns the final stopped state."""
        key = str(task_id or "")
        with self._lock:
            record = self._records.get(key)
            process = self._processes.get(key)
            if record is None:
                return None
            if record.get("status") in TERMINAL_STATUSES:
                return self._public_record(record)
            record["cancel_requested"] = True
            record["status"] = "stopping"
            self._touch(record)

        # Persist only after releasing the manager lock.  The persistence
        # helper takes a consistent snapshot first and acquires the state-file
        # lock afterwards, avoiding a watcher/submit lock inversion.
        self._persist_locked()

        if process is not None:
            self._terminate_process(process)
        else:
            # A status/stop request may be handled by another Skills process.
            # The persisted PID is the only process handle available there.
            pid = record.get("pid")
            pid_was_alive = self._pid_is_alive(pid)
            self._terminate_pid(pid)
            if pid_was_alive:
                self._start_remote_reaper(key, pid)
        return self.get(key)

    def _start_remote_reaper(self, task_id: str, pid: Any) -> None:
        """Finalize a cross-process stop when the original watcher is gone."""
        with self._lock:
            current = self._remote_reapers.get(task_id)
            if current is not None and current.is_alive():
                return
            worker = threading.Thread(
                target=self._reap_remote_task,
                args=(task_id, pid),
                name=f"ainiee-skills-reaper-{str(task_id)[:8]}",
                daemon=True,
            )
            self._remote_reapers[task_id] = worker
            worker.start()

    def _reap_remote_task(self, task_id: str, pid: Any) -> None:
        # Preserve the public ``stopping`` acknowledgement for a short turn so
        # callers can observe the same two-phase lifecycle as local stops.
        time.sleep(0.25)
        # Test/packaged workspaces can disappear while a detached manager is
        # shutting down.  Do not recreate a deleted state directory from a
        # best-effort reaper thread.
        if not self.state_path.parent.exists():
            with self._lock:
                self._remote_reapers.pop(task_id, None)
            return
        deadline = time.monotonic() + _REMOTE_STOP_GRACE_SECONDS
        while self._pid_is_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if self._pid_is_alive(pid):
            # Do not claim a terminal stop while the remote child is still
            # alive.  A later status/stop request can retry termination; this
            # avoids silently misreporting a PID-reuse or stubborn-child case.
            with self._lock:
                record = self._records.get(task_id)
                if record is not None and record.get("status") == "stopping":
                    record["error"] = "Task stop requested; remote process is still alive."
                    self._touch(record)
                self._remote_reapers.pop(task_id, None)
            self._persist_locked()
            return
        self._finish_remote_stop(task_id)

    def _finish_remote_stop(self, task_id: str) -> None:
        # If another service already wrote a terminal state, mirror it locally
        # instead of replacing a successful completion with ``stopped``.
        persisted = self._read_persisted_record(task_id)
        if persisted and persisted.get("status") in TERMINAL_STATUSES:
            with self._lock:
                local = self._records.get(task_id)
                if local is not None and local.get("status") in ACTIVE_STATUSES:
                    self._records[task_id] = persisted
                    self._events.setdefault(task_id, threading.Event()).set()
                self._remote_reapers.pop(task_id, None)
            return

        with self._lock:
            record = self._records.get(task_id)
            if record is None or record.get("status") in TERMINAL_STATUSES:
                self._remote_reapers.pop(task_id, None)
                return
            record.update(
                status="stopped",
                running=False,
                finished_at=_utc_timestamp(),
                error=record.get("error") or "Task stopped by a remote Skills server.",
            )
            self._touch(record)
            self._remote_reapers.pop(task_id, None)
            event = self._events.setdefault(task_id, threading.Event())
        self._persist_locked()
        event.set()

    def _read_persisted_record(self, task_id: str) -> Dict[str, Any] | None:
        try:
            with _state_file_lock(self.state_path):
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
            return None
        for item in payload["tasks"]:
            if isinstance(item, dict) and str(item.get("task_id") or "") == task_id:
                return self._sanitize_loaded_record(item)
        return None

    def _watch(self, task_id: str, process: subprocess.Popen[str]) -> None:
        try:
            with self._lock:
                timeout = self._records.get(task_id, {}).get("timeout_seconds")
            stdout, stderr = process.communicate(
                timeout=None if timeout is None else float(timeout)
            )
            exit_code = process.returncode
        except Exception as exc:
            if isinstance(exc, (subprocess.TimeoutExpired, TimeoutError)):
                try:
                    self._terminate_process(process)
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except Exception:
                    stdout, stderr = "", ""
                exit_code = process.returncode
                error = "Task exceeded its execution timeout."
            else:
                stdout, stderr = "", ""
                exit_code = None
                error = f"Task monitor failed: {type(exc).__name__}: {exc}"
        else:
            error = None

        persisted_cancel = self._persisted_cancel_requested(task_id)
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                self._processes.pop(task_id, None)
                return
            cancelled = bool(record.get("cancel_requested")) or persisted_cancel
            if persisted_cancel:
                record["cancel_requested"] = True
            record.update(
                status=("stopped" if cancelled else "completed" if exit_code == 0 else "failed"),
                running=False,
                finished_at=_utc_timestamp(),
                exit_code=exit_code,
                stdout=_tail(stdout),
                stderr=_tail(stderr),
                error=error or (None if exit_code == 0 or cancelled else f"Task exited with code {exit_code}."),
            )
            self._touch(record)
            self._processes.pop(task_id, None)
            secret_values = self._secrets.pop(task_id, ())
            record["stdout"] = self._redact_output(record["stdout"], secret_values)
            record["stderr"] = self._redact_output(record["stderr"], secret_values)
            record["error"] = self._redact_output(record.get("error"), secret_values) or None
            event = self._events.setdefault(task_id, threading.Event())
        self._persist_locked()
        event.set()

    def _load(self) -> None:
        try:
            with _state_file_lock(self.state_path):
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self._quarantine_corrupt_state()
            return
        if not isinstance(payload, dict):
            self._quarantine_corrupt_state()
            return
        records = payload.get("tasks")
        if not isinstance(records, list):
            self._quarantine_corrupt_state()
            return
        needs_persist = False
        with self._lock:
            changed = False
            for item in records:
                if not isinstance(item, dict) or not item.get("task_id"):
                    continue
                original = dict(item)
                record = self._sanitize_loaded_record(item)
                if record.get("status") in ACTIVE_STATUSES:
                    if self._pid_is_alive(record.get("pid")):
                        # A different Skills server may still own this child.
                        # Keep it active so status/stop can operate by PID.
                        record["running"] = True
                    else:
                        record.update(
                            status="orphaned",
                            running=False,
                            finished_at=record.get("finished_at") or _utc_timestamp(),
                            error="Skills server restarted before this task finished.",
                        )
                        self._touch(record)
                    changed = changed or record != original
                self._records[str(record["task_id"])] = record
                changed = changed or record != original
            self._trim_locked()
            needs_persist = changed
        if needs_persist:
            self._persist_locked()

    def _quarantine_corrupt_state(self) -> None:
        """Move an unreadable state file aside so a new run can recover cleanly."""
        if not self.state_path.exists():
            return
        backup = self.state_path.with_name(
            f"{self.state_path.name}.corrupt.{time.time_ns()}.{os.getpid()}.bak"
        )
        try:
            with _state_file_lock(self.state_path):
                try:
                    current = json.loads(self.state_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    current = None
                still_corrupt = not (
                    isinstance(current, dict)
                    and isinstance(current.get("tasks"), list)
                )
                if still_corrupt and self.state_path.exists():
                    os.replace(self.state_path, backup)
        except OSError:
            pass

    @staticmethod
    def _pid_is_alive(value: Any) -> bool:
        """Check whether a persisted task PID still exists."""
        if isinstance(value, bool):
            return False
        try:
            pid = int(value)
        except (TypeError, ValueError, OverflowError):
            return False
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _persisted_cancel_requested(self, task_id: str) -> bool:
        """Read a cross-process stop request before finalizing a child."""
        try:
            with _state_file_lock(self.state_path):
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return False
        if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
            return False
        for item in payload["tasks"]:
            if isinstance(item, dict) and str(item.get("task_id") or "") == task_id:
                return bool(item.get("cancel_requested"))
        return False

    def _persist_locked(self, *, file_lock_held: bool = False) -> None:
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )

        # Callers normally hold ``self._lock`` already, but cancellation and
        # watcher finalization intentionally persist after releasing it. Take
        # a consistent snapshot so JSON serialization never iterates a dict
        # while another thread is changing the in-memory registry.
        with self._lock:
            local_records = copy.deepcopy(self._records)

        def write_state() -> None:
            # Merge records written by another Skills process while this
            # manager was alive; replacing the file alone would lose them.
            merged = dict(local_records)
            try:
                existing = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                existing = {}
            if isinstance(existing, dict) and isinstance(existing.get("tasks"), list):
                for item in existing["tasks"]:
                    if isinstance(item, dict) and item.get("task_id"):
                        task_id = str(item["task_id"])
                        incoming = merged.get(task_id)
                        persisted = self._sanitize_loaded_record(item)
                        if incoming is None:
                            merged[task_id] = persisted
                        else:
                            merged[task_id] = self._merge_records(incoming, persisted)
            ordered = sorted(
                merged.values(),
                key=lambda item: item.get("created_at") or "",
            )[-_MAX_RECORDS:]
            payload = {"version": 1, "tasks": ordered}
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as writer:
                json.dump(payload, writer, ensure_ascii=False, indent=2, allow_nan=False)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, self.state_path)

        try:
            if file_lock_held:
                write_state()
            else:
                with _state_file_lock(self.state_path):
                    write_state()
        except (OSError, TypeError, ValueError):
            # A read-only packaged runtime must still be able to execute Skills;
            # status remains available in memory when persistence is unavailable.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _trim_locked(self) -> None:
        if len(self._records) <= _MAX_RECORDS:
            return
        ordered = sorted(self._records.items(), key=lambda pair: pair[1].get("created_at") or "")
        self._records = dict(ordered[-_MAX_RECORDS:])
        retained = set(self._records)
        for task_id in list(self._events):
            if task_id not in retained:
                self._events.pop(task_id, None)
                self._secrets.pop(task_id, None)

    @classmethod
    def _merge_records(
        cls,
        local: Mapping[str, Any],
        persisted: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Merge one task ID without allowing stale active data to regress it."""
        local_record = dict(local)
        persisted_record = dict(persisted)
        local_terminal = local_record.get("status") in TERMINAL_STATUSES
        persisted_terminal = persisted_record.get("status") in TERMINAL_STATUSES
        if local_terminal and not persisted_terminal:
            return local_record
        if persisted_terminal and not local_terminal:
            return persisted_record

        local_updated = cls._record_updated_at(local_record)
        persisted_updated = cls._record_updated_at(persisted_record)
        if persisted_updated > local_updated:
            return persisted_record
        return local_record

    @staticmethod
    def _record_updated_at(record: Mapping[str, Any]) -> str:
        """Return the sortable revision timestamp, including legacy records."""
        return str(record.get("updated_at") or record.get("finished_at") or record.get("created_at") or "")

    @staticmethod
    def _touch(record: Dict[str, Any]) -> None:
        record["updated_at"] = _utc_timestamp()

    @staticmethod
    def _safe_request(request: Mapping[str, Any] | None) -> Dict[str, Any]:
        """Copy request metadata while recursively removing credential fields."""
        def clean(value: Any, key: str | None = None) -> Any:
            if key and _looks_sensitive_key(key):
                return "[REDACTED]"
            if isinstance(value, Mapping):
                return {str(name): clean(item, str(name)) for name, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [clean(item) for item in value]
            if isinstance(value, float) and not math.isfinite(value):
                return str(value)
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)

        if not isinstance(request, Mapping):
            return {}
        return clean(request)

    @staticmethod
    def _coerce_timeout(value: int | float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("timeout must be a finite positive number or None")
        try:
            timeout = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("timeout must be a finite positive number or None")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number or None")
        return timeout

    @staticmethod
    def _coerce_wait_timeout(value: int | float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("wait timeout must be a finite non-negative number or None")
        try:
            timeout = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("wait timeout must be a finite non-negative number or None")
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("wait timeout must be a finite non-negative number or None")
        return timeout

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        """Terminate a child and its process group where the platform supports it."""
        pid = getattr(process, "pid", None)
        if SkillTaskManager._terminate_pid(pid, process=process):
            return
        try:
            process.terminate()
        except (AttributeError, OSError):
            pass

    @staticmethod
    def _terminate_pid(
        value: Any,
        *,
        process: subprocess.Popen[str] | None = None,
    ) -> bool:
        """Terminate a task by persisted PID when no local Popen exists."""
        if isinstance(value, bool):
            return False
        try:
            pid = int(value)
        except (TypeError, ValueError, OverflowError):
            return False
        if pid <= 0:
            return False

        if os.name != "nt":
            if process is not None:
                try:
                    os.killpg(pid, signal.SIGTERM)
                    return True
                except (OSError, ValueError):
                    pass
            try:
                os.kill(pid, signal.SIGTERM)
                return True
            except (OSError, ValueError):
                return False

        if process is not None:
            try:
                process.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM))
                # CTRL_BREAK is cooperative; fall through to taskkill when the
                # child ignores it instead of reporting a successful stop too
                # early.  A short probe keeps normal graceful shutdown cheap.
                try:
                    if process.poll() is not None:
                        return True
                except (AttributeError, OSError):
                    return True
            except (AttributeError, OSError, ValueError):
                pass
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
        return result.returncode == 0

    @classmethod
    def _collect_secret_values(
        cls,
        environment: Mapping[str, str],
        request: Mapping[str, Any] | None,
    ) -> tuple[str, ...]:
        values: set[str] = set()

        for key, value in environment.items():
            if _looks_sensitive_key(key) and value:
                values.add(str(value))

        def collect(value: Any, key: str | None = None) -> None:
            if key and _looks_sensitive_key(key) and isinstance(value, str) and value:
                values.add(value)
                return
            if isinstance(value, Mapping):
                for name, child in value.items():
                    collect(child, str(name))
            elif isinstance(value, (list, tuple)):
                for child in value:
                    collect(child)

        collect(request)
        return tuple(sorted((item for item in values if len(item) >= 3), key=len, reverse=True))

    @classmethod
    def _add_secret_values(
        cls,
        existing: tuple[str, ...],
        value: Any,
    ) -> tuple[str, ...]:
        values = set(existing)
        if isinstance(value, Mapping):
            values.update(cls._collect_secret_values(value, None))
        elif isinstance(value, (list, tuple)):
            for child in value:
                values.update(cls._add_secret_values(tuple(values), child))
        elif value:
            values.add(str(value))
        return tuple(sorted((item for item in values if len(item) >= 3), key=len, reverse=True))

    @staticmethod
    def _collect_command_secrets(command: Any) -> tuple[str, ...]:
        """Extract values following credential flags from legacy argv records."""
        if not isinstance(command, (list, tuple)):
            return ()
        values: set[str] = set()
        credential_flags = {
            "--api-key",
            "--access-key",
            "--secret-key",
            "--password",
            "--token",
            "--auth-token",
        }
        items = [str(item) for item in command]
        for index, item in enumerate(items):
            flag, separator, inline_value = item.partition("=")
            if flag.lower() not in credential_flags:
                continue
            value = inline_value if separator else (items[index + 1] if index + 1 < len(items) else "")
            if value and len(value) >= 3:
                values.add(value)
        return tuple(sorted(values, key=len, reverse=True))

    @classmethod
    def _sanitize_loaded_record(cls, item: Mapping[str, Any]) -> Dict[str, Any]:
        record = cls._sanitize_json_value(dict(item))
        secret_values = cls._collect_secret_values({}, record.get("request"))
        record["request"] = cls._safe_request(record.get("request"))
        secret_values = cls._add_secret_values(secret_values, record.pop("env", None))
        secret_values = cls._add_secret_values(
            secret_values,
            cls._collect_command_secrets(record.get("command")),
        )
        secret_values = cls._add_secret_values(
            secret_values,
            cls._collect_command_secrets(record.get("argv")),
        )
        record.pop("command", None)
        record.pop("argv", None)
        for field in ("api_key", "access_key", "secret_key"):
            secret_values = cls._add_secret_values(secret_values, record.pop(field, None))
        for field in ("stdout", "stderr", "error"):
            if field in record:
                record[field] = cls._redact_output(record[field], secret_values)
        return record

    @classmethod
    def _sanitize_json_value(cls, value: Any) -> Any:
        """Normalize permissive JSON parser values before strict persistence."""
        if isinstance(value, Mapping):
            return {
                str(key): cls._sanitize_json_value(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [cls._sanitize_json_value(child) for child in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    @staticmethod
    def _redact_output(value: Any, secrets: tuple[str, ...]) -> str:
        text = str(value or "")
        for secret in secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    @staticmethod
    def _public_record(record: Mapping[str, Any] | None) -> Dict[str, Any]:
        if record is None:
            return {}
        result = copy.deepcopy(dict(record))
        # Keep response fields intentionally explicit and avoid leaking env/argv.
        return result


_TASK_MANAGER: SkillTaskManager | None = None
_TASK_MANAGER_LOCK = threading.Lock()


def get_task_manager() -> SkillTaskManager:
    global _TASK_MANAGER
    with _TASK_MANAGER_LOCK:
        if _TASK_MANAGER is None:
            _TASK_MANAGER = SkillTaskManager()
        return _TASK_MANAGER


__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "SkillTaskManager",
    "TaskAlreadyRunningError",
    "get_task_manager",
]
