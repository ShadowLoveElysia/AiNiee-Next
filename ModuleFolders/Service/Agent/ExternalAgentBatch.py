"""Controlled batch hand-off between AiNiee and an external Agent.

The service owns a durable task ledger and never writes translated files or
AiNiee caches. Translation results are returned as structured records for the
normal deterministic writer to validate and persist later.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Mapping, Sequence

from ModuleFolders.Infrastructure.TaskConfig.AgentBatchSettings import (
    load_agent_max_batches,
    validate_agent_max_batches,
)
from ModuleFolders.Service.Agent.ExternalAgentWriterLease import _interprocess_lock

SCHEMA = "ainiee.external_agent.batch.v1"
DEFAULT_BATCH_SIZE = 50
LINE_BATCH_INPUT_SUFFIXES = frozenset({".txt"})
_TASK_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")


class ExternalAgentBatchError(ValueError):
    """Rejected operation with a stable machine-readable error code."""

    def __init__(self, message: str, code: str = "INVALID_BATCH") -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": str(self)}


BatchError = ExternalAgentBatchError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _safe_id(value: Any, kind: str) -> str:
    if kind == "task_id":
        valid = isinstance(value, str) and bool(_TASK_ID_RE.fullmatch(value))
    else:
        valid = isinstance(value, str) and bool(_SESSION_ID_RE.fullmatch(value))
    if not valid:
        raise ExternalAgentBatchError(f"{kind} is invalid", f"INVALID_{kind.upper()}")
    return value


class ExternalAgentBatchService:
    """Thread-safe project/batch ledger for external Agent execution."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        *,
        state_root: str | Path | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        clock: Callable[[], str] | None = None,
        allowed_input_roots: Sequence[str | Path] | None = None,
        batch_limit_provider: Callable[[], int] | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).expanduser().resolve()
        self.state_root = Path(state_root or self.project_root / "Resource" / "automation_progress" / "external_agent_batches").expanduser().resolve()
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be an integer between 1 and 1000")
        self.batch_size = batch_size
        self._clock = clock or _utc_now
        self._batch_limit_provider = batch_limit_provider or load_agent_max_batches
        roots = allowed_input_roots if allowed_input_roots is not None else (self.project_root,)
        self.allowed_input_roots = tuple(Path(root).expanduser().resolve() for root in roots)
        self._lock = threading.RLock()
        self._transactions = threading.local()
        self.state_root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def transaction(self, task_id: str):
        """Serialize a complete task operation, including nested workflow calls."""
        path = self._task_path(task_id)
        with self._lock:
            active = getattr(self._transactions, "active", set())
            if task_id in active:
                yield
                return
            with _interprocess_lock(path):
                self._transactions.active = active | {task_id}
                try:
                    yield
                finally:
                    self._transactions.active = active

    @staticmethod
    def _refresh_status(state: dict[str, Any]) -> None:
        statuses = [b.get("status") for b in state["batches"]]
        if all(s == "committed" for s in statuses):
            state["status"] = "completed"
        elif any(s == "claimed" for s in statuses):
            state["status"] = "translating"
        elif any(s in {"repair_required", "needs_review"} for s in statuses):
            state["status"] = "needs_attention"
        elif all(s in {"submitted", "committed"} for s in statuses):
            state["status"] = "awaiting_commit"
        else:
            state["status"] = "ready"

    def _task_path(self, task_id: str) -> Path:
        task_id = _safe_id(task_id, "task_id")
        path = (self.state_root / f"{task_id}.json").resolve()
        try:
            path.relative_to(self.state_root)
        except ValueError as exc:
            raise ExternalAgentBatchError("task state path escapes state root", "INVALID_TASK_ID") from exc
        return path

    def _read(self, task_id: str) -> dict[str, Any]:
        path = self._task_path(task_id)
        if not path.exists():
            raise ExternalAgentBatchError("task does not exist", "TASK_NOT_FOUND")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExternalAgentBatchError("task state is unreadable", "TASK_STATE_INVALID") from exc
        if not isinstance(state, dict) or state.get("schema") != SCHEMA:
            raise ExternalAgentBatchError("task state schema is invalid", "TASK_STATE_INVALID")
        return state

    def _write(self, state: Mapping[str, Any]) -> None:
        path = self._task_path(str(state["task_id"]))
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(dict(state), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    @staticmethod
    def _validate_session(state: Mapping[str, Any], session_id: Any) -> str:
        session_id = _safe_id(session_id, "session_id")
        if session_id != state.get("session_id"):
            raise ExternalAgentBatchError("session does not own this task", "SESSION_MISMATCH")
        return session_id

    def _resolve_input(self, input_path: str | Path, *, allow_directory: bool = False) -> Path:
        if not isinstance(input_path, (str, Path)) or not str(input_path).strip():
            raise ExternalAgentBatchError("input_path is required", "INVALID_INPUT_PATH")
        try:
            path = Path(input_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ExternalAgentBatchError("input file does not exist", "INPUT_NOT_FOUND") from exc
        if path.is_dir() and allow_directory:
            if not any(path == root or root in path.parents for root in self.allowed_input_roots):
                raise ExternalAgentBatchError("input_path is outside controlled project roots", "INPUT_PATH_OUTSIDE_PROJECT")
            return path
        if not path.is_file():
            raise ExternalAgentBatchError("input_path must be a file", "INVALID_INPUT_PATH")
        if not any(path == root or root in path.parents for root in self.allowed_input_roots):
            raise ExternalAgentBatchError("input_path is outside controlled project roots", "INPUT_PATH_OUTSIDE_PROJECT")
        return path

    @staticmethod
    def _source_items(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ExternalAgentBatchError("input file cannot be read", "INPUT_READ_FAILED") from exc
        text = raw.decode("utf-8", errors="replace")
        return raw, [{"index": i, "source": line} for i, line in enumerate(text.splitlines())]

    @staticmethod
    def _batch_hash(items: Sequence[Mapping[str, Any]]) -> str:
        return _sha256(_canonical([{"index": int(x["index"]), "source": str(x.get("source", x.get("source_text", "")))} for x in items]))

    def prepare_project(
        self,
        input_path: str | Path,
        task_id: str,
        session_id: str,
        execution_mode: str,
        *,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        task_id = _safe_id(task_id, "task_id")
        session_id = _safe_id(session_id, "session_id")
        if execution_mode != "external_agent":
            raise ExternalAgentBatchError("external Agent batches require external_agent mode", "EXECUTION_MODE_REQUIRED")
        path = self._resolve_input(input_path, allow_directory=True)
        if path.is_dir() or path.suffix.lower() not in LINE_BATCH_INPUT_SUFFIXES:
            raise ExternalAgentBatchError(
                "only ordinary TXT files may use line batches; structured or other formats must use the format-aware MCP task route",
                "STRUCTURED_FORMAT_REQUIRES_MCP_TASK",
            )
        raw, items = self._source_items(path)
        batches = []
        for start in range(0, len(items), self.batch_size):
            source_items = items[start : start + self.batch_size]
            batches.append({
                "batch_id": f"batch_{len(batches) + 1:06d}", "index": len(batches), "status": "pending",
                "revision": None, "source_hash": self._batch_hash(source_items), "items": source_items,
            })
        with self.transaction(task_id):
            if self._task_path(task_id).exists():
                raise ExternalAgentBatchError("task already exists", "TASK_ALREADY_EXISTS")
            now = self._clock()
            state = {
                "schema": SCHEMA, "task_id": task_id, "session_id": session_id,
                "execution_mode": execution_mode, "input_path": str(path), "source_hash": _sha256(raw),
                "output_path": str(Path(output_path).expanduser().resolve()) if output_path else str(path.parent / f"{path.stem}_AiNiee_Output"),
                "source_size": len(raw), "revision": 1, "parallel_batches": True,
                "status": "ready" if batches else "completed",
                "batch_size": self.batch_size, "total_batches": len(batches), "created_at": now,
                "updated_at": now, "batches": batches,
            }
            self._write(state)
            return self._project_view(state)

    def prepare_cache_project(
        self,
        cache_path: str | Path,
        task_id: str,
        session_id: str,
        execution_mode: str,
        *,
        input_path: str | Path | None = None,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Prepare batches from a host-generated cache manifest.

        Cache locators remain opaque to the Agent; the manifest service owns
        path validation and cache revision calculation.
        """
        from ModuleFolders.Service.Agent.ExternalAgentCacheManifest import ExternalAgentCacheManifestService

        task_id = _safe_id(task_id, "task_id")
        session_id = _safe_id(session_id, "session_id")
        if execution_mode != "external_agent":
            raise ExternalAgentBatchError("external Agent batches require external_agent mode", "EXECUTION_MODE_REQUIRED")
        manifest = ExternalAgentCacheManifestService(self.project_root).build(cache_path)
        manifest_items = []
        for index, item in enumerate(item for file in manifest["files"] for item in file["items"]):
            entry = dict(item)
            entry["index"] = index
            manifest_items.append(entry)
        batches = []
        for start in range(0, len(manifest_items), self.batch_size):
            batch_items = manifest_items[start : start + self.batch_size]
            batches.append({
                "batch_id": f"batch_{len(batches) + 1:06d}", "index": len(batches), "status": "pending",
                "revision": None, "source_hash": self._batch_hash(batch_items),
                "cache_revision": manifest["cache_revision"], "items": batch_items,
            })
        with self.transaction(task_id):
            if self._task_path(task_id).exists():
                raise ExternalAgentBatchError("task already exists", "TASK_ALREADY_EXISTS")
            now = self._clock()
            state = {
                "schema": SCHEMA, "task_id": task_id, "session_id": session_id,
                "execution_mode": execution_mode, "cache_path_name": manifest["cache_path_name"],
                "cache_path": str(Path(cache_path).expanduser().resolve()),
                "input_path": str(Path(input_path).expanduser().resolve()) if input_path else None,
                "output_path": str(Path(output_path).expanduser().resolve()) if output_path else None,
                "cache_revision": manifest["cache_revision"], "manifest_hash": manifest["manifest_hash"],
                "source_hash": manifest["manifest_hash"], "source_size": manifest["item_count"],
                "revision": 1, "parallel_batches": True,
                "status": "ready" if batches else "completed",
                "batch_size": self.batch_size, "total_batches": len(batches), "created_at": now,
                "updated_at": now, "batches": batches,
            }
            self._write(state)
            return self._project_view(state)

    def cache_path_for_writer(self, task_id: str, session_id: str) -> str:
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            cache_path = state.get("cache_path")
            if not isinstance(cache_path, str) or not cache_path:
                raise ExternalAgentBatchError("task is not cache-backed", "CACHE_MANIFEST_REQUIRED")
            return cache_path

    def export_metadata(self, task_id: str, session_id: str) -> dict[str, Any]:
        """Return persisted paths and completion state for a manual export."""
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            return {
                "task_id": state["task_id"],
                "status": state.get("status"),
                "input_path": state.get("input_path"),
                "output_path": state.get("output_path"),
                "cache_path": state.get("cache_path"),
                "batches": [
                    {"batch_id": item.get("batch_id"), "status": item.get("status")}
                    for item in state.get("batches", [])
                ],
            }

    def _max_batches_limit(self) -> int:
        try:
            return validate_agent_max_batches(self._batch_limit_provider())
        except ValueError as exc:
            raise ExternalAgentBatchError(str(exc), "INVALID_BATCH_LIMIT_CONFIG") from exc

    def _project_view(self, state: Mapping[str, Any], *, include_batches: bool = True) -> dict[str, Any]:
        submitted_batches = sum(x.get("status") in {"submitted", "committed"} for x in state["batches"])
        committed_batches = sum(x.get("status") == "committed" for x in state["batches"])
        batch_summaries = [
            {
                "batch_id": item.get("batch_id"),
                "index": item.get("index"),
                "status": item.get("status"),
                "revision": item.get("revision"),
                "source_hash": item.get("source_hash"),
                "item_count": len(item.get("items") or []),
                "cache_revision": item.get("cache_revision"),
                "issue_count": len(item.get("issues", [])),
                "write_error": item.get("write_error"),
            }
            for item in state.get("batches", [])
        ]
        next_batch = next(
            (item for item in batch_summaries if item.get("status") in {"pending", "claimed"}),
            None,
        )
        return {
            "schema": state["schema"], "task_id": state["task_id"], "execution_mode": state["execution_mode"],
            "source_hash": state["source_hash"], "source_size": state["source_size"], "revision": state["revision"],
            "status": state["status"], "total_batches": state["total_batches"],
            "max_batches": self._max_batches_limit(),
            # ``submitted`` means only that the result passed validation and
            # was staged.  A project is complete only after the deterministic
            # writer has committed every batch.
            "submitted_batches": submitted_batches,
            "committed_batches": committed_batches,
            "completed_batches": committed_batches,
            "pending_batches": sum(b.get("status") == "pending" for b in state["batches"]),
            "claimed_batches": sum(b.get("status") == "claimed" for b in state["batches"]),
            "repair_required_batches": sum(b.get("status") == "repair_required" for b in state["batches"]),
            "needs_review_batches": sum(b.get("status") == "needs_review" for b in state["batches"]),
            "awaiting_commit_batches": sum(b.get("status") == "submitted" for b in state["batches"]),
            # Keep batch identifiers available immediately after prepare and
            # through project_status. Source items remain on claim_batch so
            # discovery responses stay small enough for LLM clients.
            **({"batches": batch_summaries,
                "batch_ids": [item["batch_id"] for item in batch_summaries if item.get("batch_id")]}
               if include_batches else {}),
            "next_batch_id": next_batch.get("batch_id") if next_batch else None,
        }

    @staticmethod
    def _batch_view(batch: Mapping[str, Any]) -> dict[str, Any]:
        return {"batch_id": batch["batch_id"], "index": batch["index"], "status": batch["status"],
                "revision": batch["revision"], "source_hash": batch["source_hash"], "items": deepcopy(batch["items"]),
                "writer_lease_id": batch.get("writer_lease_id"), "cache_revision": batch.get("cache_revision")}

    def claim_batch(
        self, task_id: str, session_id: str, batch_id: str | None = None
    ) -> dict[str, Any]:
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            if state["status"] == "completed":
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            if batch_id is not None:
                if not isinstance(batch_id, str) or not batch_id.strip():
                    raise ExternalAgentBatchError("batch_id is invalid", "INVALID_BATCH_ID")
                batch = next((x for x in state["batches"] if x.get("batch_id") == batch_id), None)
                if batch is None:
                    raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
                if batch.get("status") in {"submitted", "committed"}:
                    raise ExternalAgentBatchError("batch has already been completed", "BATCH_NOT_AVAILABLE")
                if batch.get("status") == "claimed":
                    if batch.get("claimed_session_id") == session_id:
                        return {"status": "claimed", "task": self._project_view(state, include_batches=False), "batch": self._batch_view(batch)}
                    raise ExternalAgentBatchError("batch is claimed by another session", "BATCH_IN_USE")
            else:
                # A resumed session must regain its in-flight claim before it
                # takes additional work; this preserves retry/recovery semantics.
                batch = next(
                    (x for x in state["batches"]
                     if x.get("status") == "claimed" and x.get("claimed_session_id") == session_id),
                    None,
                )
                if batch is not None:
                    return {"status": "claimed", "task": self._project_view(state, include_batches=False), "batch": self._batch_view(batch)}
                batch = next((x for x in state["batches"] if x["status"] == "pending"), None)
            if batch is None:
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            if batch.get("status") != "pending":
                raise ExternalAgentBatchError("use repair tools for this batch", "BATCH_REPAIR_REQUIRED")
            batch.update({"status": "claimed", "revision": state["revision"], "claimed_session_id": session_id, "claimed_at": self._clock()})
            state.update({"status": "translating", "updated_at": self._clock()})
            self._write(state)
            return {"status": "claimed", "task": self._project_view(state, include_batches=False), "batch": self._batch_view(batch)}

    def claim_batches(
        self,
        task_id: str,
        session_id: str,
        batch_ids: Sequence[str] | None = None,
        *,
        max_batches: int | None = None,
    ) -> dict[str, Any]:
        """Claim independent batches for fan-out to parallel Agent workers."""
        configured_limit = self._max_batches_limit()
        if max_batches is None:
            max_batches = configured_limit
        if isinstance(max_batches, bool) or not isinstance(max_batches, int) or max_batches < 1:
            raise ExternalAgentBatchError("max_batches must be a positive integer", "INVALID_MAX_BATCHES")
        if max_batches > configured_limit:
            raise ExternalAgentBatchError(
                "max_batches exceeds external_agent_max_batches; obtain explicit user consent "
                "before changing the configured limit", "BATCH_LIMIT_EXCEEDED"
            )
        if batch_ids is not None:
            if not isinstance(batch_ids, Sequence) or isinstance(batch_ids, (str, bytes)):
                raise ExternalAgentBatchError("batch_ids must be an array", "INVALID_BATCH_IDS")
            requested = list(batch_ids)
            if not requested or len(requested) > max_batches:
                raise ExternalAgentBatchError("batch_ids exceeds max_batches", "INVALID_BATCH_IDS")
        else:
            requested = []
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            if state["status"] == "completed":
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            if requested:
                batches = []
                seen: set[str] = set()
                for requested_id in requested:
                    if not isinstance(requested_id, str) or not requested_id.strip() or requested_id in seen:
                        raise ExternalAgentBatchError("batch_ids contains an invalid or duplicate id", "INVALID_BATCH_IDS")
                    seen.add(requested_id)
                    batch = next((x for x in state["batches"] if x.get("batch_id") == requested_id), None)
                    if batch is None:
                        raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
                    if batch.get("status") in {"submitted", "committed"}:
                        raise ExternalAgentBatchError("batch has already been completed", "BATCH_NOT_AVAILABLE")
                    if batch.get("status") in {"repair_required", "needs_review"}:
                        raise ExternalAgentBatchError("use repair tools for this batch", "BATCH_REPAIR_REQUIRED")
                    if batch.get("status") == "claimed" and batch.get("claimed_session_id") != session_id:
                        raise ExternalAgentBatchError("batch is claimed by another session", "BATCH_IN_USE")
                    batches.append(batch)
            else:
                batches = [x for x in state["batches"] if x.get("status") == "pending"][:max_batches]
            if not batches:
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            now = self._clock()
            for batch in batches:
                if batch.get("status") != "claimed":
                    batch.update({
                        "status": "claimed", "revision": state["revision"],
                        "claimed_session_id": session_id, "claimed_at": now,
                    })
            state.update({"status": "translating", "updated_at": now})
            self._write(state)
            return {
                "status": "claimed", "task": self._project_view(state, include_batches=False),
                "batches": [self._batch_view(batch) for batch in batches],
            }

    def release_batch(self, task_id: str, session_id: str, batch_id: str) -> dict[str, Any]:
        """Release a claimed batch after a disconnect without accepting results."""
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            batch = next((item for item in state["batches"] if item.get("batch_id") == batch_id), None)
            if batch is None:
                raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
            if batch.get("status") == "submitted":
                return {"status": "submitted", "task": self._project_view(state), "batch": self._batch_view(batch)}
            if batch.get("status") != "claimed":
                raise ExternalAgentBatchError("batch is not currently claimed", "BATCH_NOT_CLAIMED")
            if batch.get("claimed_session_id") != session_id:
                raise ExternalAgentBatchError("session does not own this batch", "SESSION_MISMATCH")
            batch.update({"status": "pending", "claimed_session_id": None, "claimed_at": None})
            self._refresh_status(state)
            state["updated_at"] = self._clock()
            self._write(state)
            return {"status": "released", "task": self._project_view(state), "batch": self._batch_view(batch)}

    def resume_task(
        self,
        task_id: str,
        previous_session_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Rebind an interrupted task to a newly registered Agent session.

        The task ledger is the durable source of ownership.  A resumed
        session inherits an in-flight claim, while submitted batches remain
        staged until the new session obtains a fresh writer lease and commits
        them.  The old session is no longer accepted by any task operation.
        The caller is responsible for proving that the old connection is
        terminal before invoking this method.
        """
        task_id = _safe_id(task_id, "task_id")
        previous_session_id = _safe_id(previous_session_id, "session_id")
        session_id = _safe_id(session_id, "session_id")
        if previous_session_id == session_id:
            raise ExternalAgentBatchError(
                "a resumed task requires a different session", "SESSION_ALREADY_ACTIVE"
            )
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, previous_session_id)
            if state.get("status") == "completed":
                raise ExternalAgentBatchError("project is already completed", "TASK_COMPLETED")

            history = state.get("session_history")
            if not isinstance(history, list):
                history = []
            history.append({"session_id": previous_session_id, "ended_at": self._clock()})
            state["session_history"] = history[-32:]
            state["session_id"] = session_id
            state["resumed_from_session_id"] = previous_session_id
            state["resumed_at"] = self._clock()

            for batch in state.get("batches", []):
                if batch.get("claimed_session_id") == previous_session_id:
                    batch["claimed_session_id"] = session_id

            self._refresh_status(state)
            state["updated_at"] = self._clock()
            self._write(state)
            return {
                "status": "resumed",
                "task": self._project_view(state),
                "previous_session_id": previous_session_id,
                "session_id": session_id,
            }

    @staticmethod
    def _validate_result_items(expected: Sequence[Mapping[str, Any]], items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise ExternalAgentBatchError("items must be an array", "INVALID_RESULT_ITEMS")
        expected_by_index = {x["index"]: x for x in expected}
        expected_by_item_id = {x.get("item_id"): x for x in expected if x.get("item_id")}
        seen: set[int] = set(); result = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ExternalAgentBatchError("each item must be an object", "INVALID_RESULT_ITEMS")
            index = item.get("index")
            if index is None and isinstance(item.get("item_id"), str) and item["item_id"] in expected_by_item_id:
                index = expected_by_item_id[item["item_id"]]["index"]
            if isinstance(index, bool) or not isinstance(index, int) or index not in expected_by_index or index in seen:
                raise ExternalAgentBatchError("result item index does not match claimed batch", "INVALID_RESULT_ITEMS")
            if not isinstance(item.get("translation"), str):
                raise ExternalAgentBatchError("translation must be a string", "INVALID_RESULT_ITEMS")
            expected_source = expected_by_index[index].get("source", expected_by_index[index].get("source_text", ""))
            if "source" in item and item["source"] != expected_source:
                raise ExternalAgentBatchError("result source does not match claimed batch", "SOURCE_MISMATCH")
            expected_item = expected_by_index[index]
            if item.get("item_id") and item.get("item_id") != expected_item.get("item_id"):
                raise ExternalAgentBatchError("result item_id does not match claimed batch", "ITEM_ID_MISMATCH")
            result_item = {"index": index, "translation": item["translation"]}
            for key in ("item_id", "storage_path", "file_id", "text_index", "source_text", "source_hash", "current_line_hash", "cache_revision"):
                if key in expected_item:
                    result_item[key] = expected_item[key]
            seen.add(index); result.append(result_item)
        if seen != set(expected_by_index):
            raise ExternalAgentBatchError("result does not contain every claimed item", "INVALID_RESULT_ITEMS")
        return sorted(result, key=lambda x: x["index"])

    def submit_translation_batch(self, task_id: str, session_id: str, batch_id: str, source_hash: str,
                                 revision: int, idempotency_key: str, items: Any, *,
                                 request_fingerprint: str | None = None) -> dict[str, Any]:
        with self.transaction(task_id):
            state = self._read(task_id); self._validate_session(state, session_id)
            if not isinstance(batch_id, str) or not batch_id:
                raise ExternalAgentBatchError("batch_id is required", "INVALID_BATCH_ID")
            if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
                raise ExternalAgentBatchError("source_hash must be a SHA-256 hex digest", "INVALID_SOURCE_HASH")
            if isinstance(revision, bool) or not isinstance(revision, int):
                raise ExternalAgentBatchError("revision must be an integer", "INVALID_REVISION")
            if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 256:
                raise ExternalAgentBatchError("idempotency_key is required", "INVALID_IDEMPOTENCY_KEY")
            batch = next((x for x in state["batches"] if x.get("batch_id") == batch_id), None)
            if batch is None:
                raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
            result_items = self._validate_result_items(batch["items"], items)
            fingerprint = _sha256(_canonical({"source_hash": source_hash, "revision": revision, "items": result_items}))
            if batch["status"] in {"submitted", "committed"}:
                if batch.get("idempotency_key") != idempotency_key:
                    raise ExternalAgentBatchError("batch has already been submitted", "BATCH_ALREADY_SUBMITTED")
                if batch.get("result_fingerprint") != fingerprint:
                    raise ExternalAgentBatchError("idempotency key reused with different data", "IDEMPOTENCY_CONFLICT")
                response = deepcopy(batch["submission"]); response["replayed"] = True; return response
            if batch["status"] not in {"claimed", "repair_required", "needs_review"}:
                raise ExternalAgentBatchError("batch is not currently claimed", "BATCH_NOT_CLAIMED")
            if batch.get("claimed_session_id") != session_id:
                raise ExternalAgentBatchError("session does not own this batch", "SESSION_MISMATCH")
            if batch.get("source_hash") != source_hash:
                raise ExternalAgentBatchError("source hash does not match claimed batch", "SOURCE_HASH_MISMATCH")
            if batch.get("revision") != revision:
                raise ExternalAgentBatchError("task revision is stale", "REVISION_CONFLICT")
            from ModuleFolders.Service.Agent.ExternalAgentBatchResult import ExternalAgentBatchResultService

            # Reject invalid translations before consuming the accepted-result key.
            expected = ExternalAgentBatchResultService._expected_items(batch)
            ExternalAgentBatchResultService._validate_items(expected, result_items)
            submission = {"status": "accepted", "task_id": task_id, "batch_id": batch_id, "revision": revision,
                          "next_revision": revision, "result_hash": _sha256(_canonical(result_items)),
                          "items": deepcopy(result_items), "replayed": False}
            if state.get("cache_path"):
                submission["cache_revision"] = batch.get("cache_revision") or state.get("cache_revision")
                submission["manifest_hash"] = state.get("manifest_hash")
                submission["allow_cache_rebase"] = bool(state.get("parallel_batches"))
            batch.update({"status": "submitted", "idempotency_key": idempotency_key, "result_fingerprint": fingerprint,
                          "submitted_at": self._clock(), "submission": submission})
            if request_fingerprint is not None:
                batch["accepted_request"] = request_fingerprint
            for key in ("candidate_items", "issues", "failed_request", "write_error"):
                batch.pop(key, None)
            self._refresh_status(state)
            state["updated_at"] = self._clock(); self._write(state)
            return deepcopy(submission)

    def get_project(self, task_id: str, session_id: str | None = None) -> dict[str, Any]:
        with self.transaction(task_id):
            state = self._read(task_id)
            if session_id is not None: self._validate_session(state, session_id)
            return self._project_view(state)

    def get_ledger(self, task_id: str, session_id: str | None = None) -> dict[str, Any]:
        """Return a session-authorized ledger snapshot for result staging."""
        with self.transaction(task_id):
            state = self._read(task_id)
            if session_id is not None:
                self._validate_session(state, session_id)
            return deepcopy(state)

    def mark_batch_committed(
        self,
        task_id: str,
        session_id: str,
        batch_id: str,
        writer_lease_id: str,
        commit_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Finalize ledger state only after the deterministic writer succeeds."""
        with self.transaction(task_id):
            state = self._read(task_id)
            self._validate_session(state, session_id)
            batch = next((item for item in state["batches"] if item.get("batch_id") == batch_id), None)
            if batch is None:
                raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
            if batch.get("status") == "committed":
                return {"status": "committed", "task": self._project_view(state), "batch": self._batch_view(batch)}
            if batch.get("status") != "submitted":
                raise ExternalAgentBatchError("batch is not submitted", "BATCH_NOT_SUBMITTED")
            if not isinstance(writer_lease_id, str) or not writer_lease_id:
                raise ExternalAgentBatchError("writer lease is required", "WRITER_LEASE_REQUIRED")
            if not isinstance(commit_result, Mapping) or commit_result.get("status") != "persisted":
                raise ExternalAgentBatchError("writer commit result is invalid", "WRITER_COMMIT_INVALID")
            batch.update({
                "status": "committed",
                "writer_lease_id": writer_lease_id,
                "cache_revision": commit_result.get("cache_revision"),
                "backup_path_recorded": bool(commit_result.get("backup_path")),
                "committed_at": self._clock(),
            })
            batch.pop("write_error", None)
            if state.get("cache_path") and commit_result.get("cache_revision"):
                state["cache_revision"] = commit_result["cache_revision"]
                # Claimed/staged batches retain immutable fingerprints for retries.
                for pending in state["batches"]:
                    if pending.get("status") == "pending":
                        pending["cache_revision"] = commit_result["cache_revision"]
                        for item in pending.get("items", []):
                            if isinstance(item, dict):
                                item["cache_revision"] = commit_result["cache_revision"]
            self._refresh_status(state)
            state["updated_at"] = self._clock()
            self._write(state)
            return {"status": "committed", "task": self._project_view(state), "batch": self._batch_view(batch)}


_DEFAULT_SERVICE: ExternalAgentBatchService | None = None
_DEFAULT_LOCK = threading.Lock()


def get_external_agent_batch_service() -> ExternalAgentBatchService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_SERVICE is None: _DEFAULT_SERVICE = ExternalAgentBatchService()
    return _DEFAULT_SERVICE


def prepare_project(input_path: str | Path, task_id: str, session_id: str, execution_mode: str) -> dict[str, Any]:
    return get_external_agent_batch_service().prepare_project(input_path, task_id, session_id, execution_mode)


def claim_batch(task_id: str, session_id: str, batch_id: str | None = None) -> dict[str, Any]:
    return get_external_agent_batch_service().claim_batch(task_id, session_id, batch_id)


def claim_batches(
    task_id: str,
    session_id: str,
    batch_ids: Sequence[str] | None = None,
    *,
    max_batches: int | None = None,
) -> dict[str, Any]:
    return get_external_agent_batch_service().claim_batches(
        task_id, session_id, batch_ids, max_batches=max_batches
    )


def resume_task(task_id: str, previous_session_id: str, session_id: str) -> dict[str, Any]:
    return get_external_agent_batch_service().resume_task(task_id, previous_session_id, session_id)


def submit_translation_batch(task_id: str, session_id: str, batch_id: str, source_hash: str, revision: int, idempotency_key: str, items: Any) -> dict[str, Any]:
    return get_external_agent_batch_service().submit_translation_batch(task_id, session_id, batch_id, source_hash, revision, idempotency_key, items)


__all__ = ["SCHEMA", "DEFAULT_BATCH_SIZE", "ExternalAgentBatchError", "BatchError", "ExternalAgentBatchService", "get_external_agent_batch_service", "prepare_project", "claim_batch", "claim_batches", "resume_task", "submit_translation_batch"]
