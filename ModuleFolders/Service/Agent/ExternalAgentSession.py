"""Thread-safe runtime registry for external Agent MCP sessions.

The registry deliberately has no transport dependency.  MCP/Skills adapters can
translate their request body to :meth:`register`, :meth:`heartbeat` and
:meth:`unregister`; the registry owns only identity validation and short-lived
leases.  Configuration/profile state must not be inferred from this registry.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import secrets
import threading
from collections.abc import Callable, Mapping
from typing import Any


PROTOCOL_VERSION = "1"
DEFAULT_LEASE_SECONDS = 120
MAX_LEASE_SECONDS = 600
MIN_LEASE_SECONDS = 5


class ExternalAgentSessionError(ValueError):
    """A rejected session operation with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "INVALID_SESSION") -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": str(self)}


SessionError = ExternalAgentSessionError


class ExternalAgentSessionRegistry:
    """In-memory external Agent registration and lease manager.

    ``clock`` is injectable for deterministic tests and must return a timezone
    aware ``datetime`` (a naive datetime is treated as UTC).  Session records
    are retained after expiration/unregister so callers can inspect the reason;
    a new registration using the same instance id is still allowed once the
    previous record is terminal.
    """

    def __init__(
        self,
        *,
        protocol_version: str | int = PROTOCOL_VERSION,
        default_lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_lease_seconds: int = MAX_LEASE_SECONDS,
        min_lease_seconds: int = MIN_LEASE_SECONDS,
        clock: Callable[[], datetime] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.protocol_version = self._normalise_protocol(protocol_version)
        if not isinstance(max_lease_seconds, int) or isinstance(max_lease_seconds, bool):
            raise ValueError("max_lease_seconds must be an integer")
        if not isinstance(min_lease_seconds, int) or isinstance(min_lease_seconds, bool):
            raise ValueError("min_lease_seconds must be an integer")
        if min_lease_seconds < 1 or max_lease_seconds < min_lease_seconds:
            raise ValueError("invalid lease bounds")
        if not isinstance(default_lease_seconds, int) or isinstance(default_lease_seconds, bool):
            raise ValueError("default_lease_seconds must be an integer")
        if not min_lease_seconds <= default_lease_seconds <= max_lease_seconds:
            raise ValueError("default_lease_seconds is outside lease bounds")
        self.default_lease_seconds = default_lease_seconds
        self.max_lease_seconds = max_lease_seconds
        self.min_lease_seconds = min_lease_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._session_id_factory = session_id_factory or (
            lambda: "sess_" + secrets.token_urlsafe(18)
        )
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, datetime] = {}

    @staticmethod
    def _normalise_protocol(value: Any) -> str:
        if isinstance(value, bool) or value is None:
            raise ExternalAgentSessionError(
                "protocol_version is required", "UNSUPPORTED_PROTOCOL_VERSION"
            )
        value = str(value).strip()
        if not value:
            raise ExternalAgentSessionError(
                "protocol_version is required", "UNSUPPORTED_PROTOCOL_VERSION"
            )
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = datetime.fromtimestamp(value, timezone.utc)
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime or Unix timestamp")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _payload(payload: Mapping[str, Any] | None, values: Mapping[str, Any]) -> dict[str, Any]:
        if payload is not None and not isinstance(payload, Mapping):
            raise ExternalAgentSessionError("session request must be an object", "INVALID_ARGUMENTS")
        result = dict(payload or {})
        result.update(values)
        return result

    def _lease(self, value: Any) -> int:
        if value is None:
            return self.default_lease_seconds
        if isinstance(value, bool):
            raise ExternalAgentSessionError("requested_lease_seconds must be an integer", "INVALID_LEASE")
        if not isinstance(value, int):
            raise ExternalAgentSessionError("requested_lease_seconds must be an integer", "INVALID_LEASE") from None
        lease = value
        if lease < self.min_lease_seconds:
            raise ExternalAgentSessionError(
                f"requested lease must be at least {self.min_lease_seconds} seconds", "INVALID_LEASE"
            )
        if lease > self.max_lease_seconds:
            raise ExternalAgentSessionError(
                f"requested lease exceeds maximum of {self.max_lease_seconds} seconds", "LEASE_TOO_LONG"
            )
        return lease

    def _copy(self, record: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(record)

    def _find(self, session_id: Any) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ExternalAgentSessionError("session_id is required", "SESSION_NOT_FOUND")
        record = self._sessions.get(session_id)
        if record is None:
            raise ExternalAgentSessionError("session does not exist", "SESSION_NOT_FOUND")
        return record

    def _expire_due(self, now: datetime) -> list[dict[str, Any]]:
        expired: list[dict[str, Any]] = []
        for session_id, record in self._sessions.items():
            if record["state"] == "registered" and now >= self._expiry[session_id]:
                record["state"] = "expired"
                record["expired_at"] = self._format_time(now)
                record["server_directive"] = "re_register"
                expired.append(self._copy(record))
        return expired

    def register(
        self,
        payload: Mapping[str, Any] | str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Register an Agent and create a short-lived writer/session lease."""
        # A small positional compatibility form is useful to Skills adapters:
        # ``register(agent_id, capabilities, metadata, lease_seconds)``.  The
        # protocol-facing mapping form remains the canonical interface.
        if isinstance(payload, str):
            if len(args) > 3:
                raise ExternalAgentSessionError("too many register arguments", "INVALID_ARGUMENTS")
            capabilities = args[0] if args else kwargs.pop("capabilities", [])
            metadata = args[1] if len(args) > 1 else kwargs.pop("metadata", {})
            lease_seconds = args[2] if len(args) > 2 else kwargs.pop("lease_seconds", None)
            if not isinstance(metadata, Mapping):
                raise ExternalAgentSessionError("metadata must be an object", "INVALID_ARGUMENTS")
            payload = {
                **dict(metadata),
                "agent_instance_id": payload,
                "capabilities": capabilities,
                "requested_lease_seconds": lease_seconds,
            }
        elif args:
            raise ExternalAgentSessionError("positional arguments require agent id form", "INVALID_ARGUMENTS")
        data = self._payload(payload, kwargs)
        if "agent_id" in data and "agent_instance_id" not in data:
            data["agent_instance_id"] = data["agent_id"]
        protocol = self._normalise_protocol(data.get("protocol_version", self.protocol_version))
        if protocol != self.protocol_version:
            raise ExternalAgentSessionError(
                f"unsupported protocol_version: {protocol}", "UNSUPPORTED_PROTOCOL_VERSION"
            )
        instance_id = data.get("agent_instance_id")
        if not isinstance(instance_id, str) or not instance_id.strip() or len(instance_id) > 256:
            raise ExternalAgentSessionError("agent_instance_id is required", "INVALID_AGENT_INSTANCE_ID")
        if data.get("user_confirmed_external_processing") is not True:
            raise ExternalAgentSessionError(
                "external processing must be confirmed by the user", "EXTERNAL_PROCESSING_NOT_CONFIRMED"
            )
        capabilities = data.get("capabilities", [])
        if not isinstance(capabilities, (list, tuple)) or any(not isinstance(item, str) or not item for item in capabilities):
            raise ExternalAgentSessionError("capabilities must be a list of strings", "INVALID_CAPABILITIES")
        modes = data.get("supported_modes", [])
        if modes and (not isinstance(modes, (list, tuple)) or any(not isinstance(item, str) for item in modes)):
            raise ExternalAgentSessionError("supported_modes must be a list of strings", "INVALID_MODES")
        if modes and "external_agent" not in modes:
            raise ExternalAgentSessionError("external_agent mode is not supported", "AGENT_MODE_UNSUPPORTED")
        lease = self._lease(data.get("requested_lease_seconds"))
        now = self._now()
        with self._lock:
            self._expire_due(now)
            for existing in self._sessions.values():
                if existing.get("agent_instance_id") == instance_id and existing.get("state") == "registered":
                    raise ExternalAgentSessionError("agent instance is already registered", "AGENT_ALREADY_REGISTERED")
            session_id = str(self._session_id_factory())
            if not session_id or session_id in self._sessions:
                raise ExternalAgentSessionError("session id factory returned a duplicate id", "SESSION_ID_CONFLICT")
            expires = now.timestamp() + lease
            expires_at = datetime.fromtimestamp(expires, timezone.utc)
            record = {
                "session_id": session_id,
                "protocol_version": self.protocol_version,
                "state": "registered",
                "agent_instance_id": instance_id,
                "client_name": str(data.get("client_name", "")),
                "client_version": str(data.get("client_version", "")),
                "capabilities": list(capabilities),
                "supported_modes": list(modes),
                "transport": str(data.get("transport", "")),
                "lease_seconds": lease,
                "heartbeat_interval_seconds": max(1, lease // 3),
                "accepted_at": self._format_time(now),
                "last_heartbeat_at": self._format_time(now),
                "expires_at": self._format_time(expires_at),
                "server_directive": "continue",
            }
            self._sessions[session_id] = record
            self._expiry[session_id] = expires_at
            return self._copy(record)

    def heartbeat(
        self,
        session_id: str | Mapping[str, Any],
        agent_instance_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Renew a lease after validating both session and stable instance id."""
        if isinstance(session_id, Mapping):
            data = dict(session_id)
            session_id = data.get("session_id")
            agent_instance_id = data.get("agent_instance_id", agent_instance_id)
            kwargs = {**data, **kwargs}
        with self._lock:
            now = self._now()
            record = self._find(session_id)
            if record.get("state") != "registered" or now >= self._expiry[session_id]:
                self._expire_due(now)
                raise ExternalAgentSessionError("session lease has expired", "SESSION_EXPIRED")
            if agent_instance_id != record.get("agent_instance_id"):
                raise ExternalAgentSessionError("agent instance does not match session", "AGENT_INSTANCE_MISMATCH")
            expires = now.timestamp() + int(record["lease_seconds"])
            expires_at = datetime.fromtimestamp(expires, timezone.utc)
            record["last_heartbeat_at"] = self._format_time(now)
            record["expires_at"] = self._format_time(expires_at)
            for field in ("last_task_id", "active_batch_id"):
                if field in kwargs and kwargs[field] is not None:
                    record[field] = str(kwargs[field])
            self._expiry[session_id] = expires_at
            return self._copy(record)

    def unregister(
        self,
        session_id: str | Mapping[str, Any],
        agent_instance_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """End a session explicitly while retaining a terminal audit snapshot."""
        if isinstance(session_id, Mapping):
            data = dict(session_id)
            session_id = data.get("session_id")
            agent_instance_id = data.get("agent_instance_id", agent_instance_id)
            kwargs = {**data, **kwargs}
        with self._lock:
            record = self._find(session_id)
            if agent_instance_id is not None and agent_instance_id != record.get("agent_instance_id"):
                raise ExternalAgentSessionError("agent instance does not match session", "AGENT_INSTANCE_MISMATCH")
            if record.get("state") == "registered":
                now = self._now()
                record["state"] = "disconnected"
                record["disconnected_at"] = self._format_time(now)
                record["server_directive"] = "stop"
                record["disconnect_reason"] = str(kwargs.get("reason", "client_shutdown"))
            return self._copy(record)

    def get(self, session_id: str, *, active_only: bool = False) -> dict[str, Any] | None:
        """Return a copy of a session, marking an elapsed lease as expired."""
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            self._expire_due(self._now())
            if active_only and record.get("state") != "registered":
                return None
            return self._copy(record)

    def expire(self, now: datetime | float | int | None = None) -> list[dict[str, Any]]:
        """Mark all elapsed registered leases as expired and return snapshots."""
        with self._lock:
            if now is None:
                current = self._now()
            elif isinstance(now, datetime):
                current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
                current = current.astimezone(timezone.utc)
            else:
                current = datetime.fromtimestamp(float(now), timezone.utc)
            return self._expire_due(current)

    def status(self, session_id: str | None = None) -> dict[str, Any] | None:
        """Return one session or an active-session listing for adapters."""
        if session_id is not None:
            return self.get(session_id)
        with self._lock:
            self._expire_due(self._now())
            sessions = [self._copy(item) for item in self._sessions.values()]
            return {
                "sessions": sessions,
                "count": len(sessions),
                "active_count": sum(item.get("state") == "registered" for item in sessions),
            }

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for item in self._sessions.values() if item.get("state") == "registered")


__all__ = [
    "PROTOCOL_VERSION",
    "DEFAULT_LEASE_SECONDS",
    "MAX_LEASE_SECONDS",
    "MIN_LEASE_SECONDS",
    "ExternalAgentSessionError",
    "SessionError",
    "ExternalAgentSessionRegistry",
]


_DEFAULT_REGISTRY: ExternalAgentSessionRegistry | None = None
_DEFAULT_REGISTRY_LOCK = threading.Lock()


def get_external_agent_session_registry() -> ExternalAgentSessionRegistry:
    """Return the process-local registry shared by MCP and Skills adapters."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _DEFAULT_REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = ExternalAgentSessionRegistry()
    return _DEFAULT_REGISTRY


__all__.append("get_external_agent_session_registry")
