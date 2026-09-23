"""Short-lived writer leases for deterministic external-Agent cache commits.

The registry is used by both MCP and Skills workers. A process-local lock is
not sufficient when those adapters run in separate processes, so the default
registry stores leases in a small JSON ledger and protects each transaction
with a sidecar OS file lock. Tests and embedders may pass ``state_path=None``
to retain an in-memory registry.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Callable, Iterator


SCHEMA = "ainiee.external_agent.writer_leases.v1"
DEFAULT_LEASE_SECONDS = 120
MIN_LEASE_SECONDS = 5
MAX_LEASE_SECONDS = 600


class ExternalAgentWriterLeaseError(ValueError):
    def __init__(self, message: str, code: str = "WRITER_LEASE_INVALID") -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": str(self)}


def _default_state_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "Resource" / "automation_progress" / "external_agent_writer_leases.json"


def _lock_windows_file(lock_file: Any) -> None:
    """Acquire a one-byte Windows lock, retrying while another process owns it."""
    import msvcrt

    while True:
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN) and getattr(error, "winerror", None) not in (33, 36):
                raise
            time.sleep(0.05)


@contextmanager
def _interprocess_lock(path: Path) -> Iterator[None]:
    """Serialize state-file transactions on POSIX and Windows."""
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        if os.name == "nt":
            import msvcrt

            _lock_windows_file(lock_file)
            try:
                yield
            finally:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class ExternalAgentWriterLeaseRegistry:
    """Thread/process-safe registry for short-lived task writer leases.

    ``state_path`` is the durable lease ledger. Every operation reloads it
    while holding the sidecar lock, so a newly started service observes leases
    created by another process. Expired leases are removed in the same
    transaction before a new lease can be acquired.
    """

    def __init__(
        self,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        state_path: str | Path | None = None,
        clock: Callable[[], float | int | datetime] | None = None,
        lease_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
            raise ValueError("lease_seconds must be an integer")
        self.lease_seconds = max(MIN_LEASE_SECONDS, min(lease_seconds, MAX_LEASE_SECONDS))
        self.state_path = Path(state_path).expanduser().resolve(strict=False) if state_path is not None else None
        self._clock = clock or (lambda: datetime.now(timezone.utc).timestamp())
        self._lease_id_factory = lease_id_factory or (lambda: "wlease_" + secrets.token_urlsafe(18))
        self._leases: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _now(self) -> float:
        value = self._clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        raise TypeError("clock must return datetime or Unix timestamp")

    @contextmanager
    def _transaction(self) -> Iterator[dict[str, dict[str, Any]]]:
        with self._lock:
            if self.state_path is None:
                yield self._leases
                return
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with _interprocess_lock(self.state_path):
                self._leases = self._load()
                before = deepcopy(self._leases)
                try:
                    yield self._leases
                finally:
                    # Expiry cleanup must survive a rejected operation too;
                    # otherwise another process could keep seeing a lease
                    # that this process already reclaimed.
                    self._leases = self._normalise_leases(self._leases)
                    if self._leases != before:
                        self._save(self._leases)

    @staticmethod
    def _normalise_leases(value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            raise ExternalAgentWriterLeaseError("writer lease state is invalid", "WRITER_LEASE_STATE_INVALID")
        result: dict[str, dict[str, Any]] = {}
        for lease_id, record in value.items():
            if not isinstance(lease_id, str) or not isinstance(record, dict):
                raise ExternalAgentWriterLeaseError("writer lease state is invalid", "WRITER_LEASE_STATE_INVALID")
            task_id, session_id, expires_at = record.get("task_id"), record.get("session_id"), record.get("expires_at")
            if not isinstance(task_id, str) or not task_id or not isinstance(session_id, str) or not session_id:
                raise ExternalAgentWriterLeaseError("writer lease state is invalid", "WRITER_LEASE_STATE_INVALID")
            if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
                raise ExternalAgentWriterLeaseError("writer lease state is invalid", "WRITER_LEASE_STATE_INVALID")
            result[lease_id] = {
                "writer_lease_id": lease_id,
                "task_id": task_id,
                "session_id": session_id,
                "expires_at": float(expires_at),
            }
        return result

    def _load(self) -> dict[str, dict[str, Any]]:
        if self.state_path is None or not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExternalAgentWriterLeaseError("writer lease state is unreadable", "WRITER_LEASE_STATE_INVALID") from exc
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            raise ExternalAgentWriterLeaseError("writer lease state schema is invalid", "WRITER_LEASE_STATE_INVALID")
        return self._normalise_leases(payload.get("leases", {}))

    def _save(self, leases: dict[str, dict[str, Any]]) -> None:
        if self.state_path is None:
            return
        payload = {"schema": SCHEMA, "leases": leases}
        temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _expire(leases: dict[str, dict[str, Any]], now: float) -> list[dict[str, Any]]:
        expired = [dict(lease) for lease in leases.values() if lease["expires_at"] <= now]
        for lease in expired:
            leases.pop(lease["writer_lease_id"], None)
        return expired

    def acquire(self, task_id: str, session_id: str) -> dict[str, Any]:
        if not isinstance(task_id, str) or not task_id or not isinstance(session_id, str) or not session_id:
            raise ExternalAgentWriterLeaseError("task_id and session_id are required", "INVALID_ARGUMENTS")
        with self._transaction() as leases:
            now = self._now()
            self._expire(leases, now)
            for lease in leases.values():
                if lease["task_id"] == task_id:
                    if lease["session_id"] == session_id:
                        return dict(lease)
                    raise ExternalAgentWriterLeaseError("task already has a writer lease", "WRITER_LEASE_IN_USE")
            lease_id = str(self._lease_id_factory())
            if not lease_id or lease_id in leases:
                raise ExternalAgentWriterLeaseError("lease id factory returned a duplicate id", "LEASE_ID_CONFLICT")
            lease = {"writer_lease_id": lease_id, "task_id": task_id, "session_id": session_id, "expires_at": now + self.lease_seconds}
            leases[lease_id] = lease
            return dict(lease)

    def validate(self, writer_lease_id: str, task_id: str, session_id: str) -> bool:
        with self._transaction() as leases:
            self._expire(leases, self._now())
            lease = leases.get(writer_lease_id)
            return bool(lease and lease["task_id"] == task_id and lease["session_id"] == session_id)

    def release(self, writer_lease_id: str, task_id: str, session_id: str) -> bool:
        with self._transaction() as leases:
            self._expire(leases, self._now())
            lease = leases.get(writer_lease_id)
            if not lease or lease["task_id"] != task_id or lease["session_id"] != session_id:
                return False
            leases.pop(writer_lease_id, None)
            return True

    def release_task(self, task_id: str, session_id: str) -> int:
        """Release all leases held by a terminal Agent session for one task."""
        if not isinstance(task_id, str) or not task_id or not isinstance(session_id, str) or not session_id:
            raise ExternalAgentWriterLeaseError("task_id and session_id are required", "INVALID_ARGUMENTS")
        with self._transaction() as leases:
            self._expire(leases, self._now())
            removed = [
                lease_id
                for lease_id, lease in leases.items()
                if lease.get("task_id") == task_id and lease.get("session_id") == session_id
            ]
            for lease_id in removed:
                leases.pop(lease_id, None)
            return len(removed)

    def expire(self, now: float | int | datetime | None = None) -> list[dict[str, Any]]:
        """Remove elapsed leases and return the snapshots that were reclaimed."""
        current = self._now() if now is None else self._coerce_time(now)
        with self._transaction() as leases:
            return self._expire(leases, current)

    def status(self) -> list[dict[str, Any]]:
        """Return active lease snapshots after reclaiming elapsed records."""
        with self._transaction() as leases:
            self._expire(leases, self._now())
            return [dict(item) for item in leases.values()]

    @staticmethod
    def _coerce_time(value: float | int | datetime) -> float:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        raise TypeError("now must be datetime or Unix timestamp")

    def _expire_due(self, now: float) -> None:
        """Compatibility helper retained for callers of the original registry."""
        self._expire(self._leases, now)


_DEFAULT_WRITER_LEASES = ExternalAgentWriterLeaseRegistry(state_path=_default_state_path())


def get_external_agent_writer_lease_registry() -> ExternalAgentWriterLeaseRegistry:
    return _DEFAULT_WRITER_LEASES


__all__ = [
    "SCHEMA",
    "ExternalAgentWriterLeaseError",
    "ExternalAgentWriterLeaseRegistry",
    "get_external_agent_writer_lease_registry",
]
