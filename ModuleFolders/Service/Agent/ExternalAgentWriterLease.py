"""Short-lived writer leases for deterministic external-Agent cache commits."""
from __future__ import annotations

from datetime import datetime, timezone
import secrets
import threading
from typing import Any


class ExternalAgentWriterLeaseError(ValueError):
    def __init__(self, message: str, code: str = "WRITER_LEASE_INVALID") -> None:
        super().__init__(message)
        self.code = code


class ExternalAgentWriterLeaseRegistry:
    def __init__(self, *, lease_seconds: int = 120) -> None:
        self.lease_seconds = max(5, min(int(lease_seconds), 600))
        self._leases: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> float:
        return datetime.now(timezone.utc).timestamp()

    def acquire(self, task_id: str, session_id: str) -> dict[str, Any]:
        if not isinstance(task_id, str) or not task_id or not isinstance(session_id, str) or not session_id:
            raise ExternalAgentWriterLeaseError("task_id and session_id are required", "INVALID_ARGUMENTS")
        now = self._now()
        with self._lock:
            self._expire(now)
            for lease in self._leases.values():
                if lease["task_id"] == task_id:
                    if lease["session_id"] == session_id:
                        return dict(lease)
                    raise ExternalAgentWriterLeaseError("task already has a writer lease", "WRITER_LEASE_IN_USE")
            lease_id = "wlease_" + secrets.token_urlsafe(18)
            lease = {
                "writer_lease_id": lease_id,
                "task_id": task_id,
                "session_id": session_id,
                "expires_at": now + self.lease_seconds,
            }
            self._leases[lease_id] = lease
            return dict(lease)

    def validate(self, writer_lease_id: str, task_id: str, session_id: str) -> bool:
        with self._lock:
            self._expire(self._now())
            lease = self._leases.get(writer_lease_id)
            return bool(lease and lease["task_id"] == task_id and lease["session_id"] == session_id)

    def release(self, writer_lease_id: str, task_id: str, session_id: str) -> bool:
        with self._lock:
            lease = self._leases.get(writer_lease_id)
            if not lease or lease["task_id"] != task_id or lease["session_id"] != session_id:
                return False
            self._leases.pop(writer_lease_id, None)
            return True

    def _expire(self, now: float) -> None:
        for key, lease in list(self._leases.items()):
            if lease["expires_at"] <= now:
                self._leases.pop(key, None)


_DEFAULT_WRITER_LEASES = ExternalAgentWriterLeaseRegistry()


def get_external_agent_writer_lease_registry() -> ExternalAgentWriterLeaseRegistry:
    return _DEFAULT_WRITER_LEASES


__all__ = [
    "ExternalAgentWriterLeaseError",
    "ExternalAgentWriterLeaseRegistry",
    "get_external_agent_writer_lease_registry",
]
