"""Controlled batch hand-off between AiNiee and an external Agent.

The service owns a durable task ledger and never writes translated files or
AiNiee caches. Translation results are returned as structured records for the
normal deterministic writer to validate and persist later.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "ainiee.external_agent.batch.v1"
DEFAULT_BATCH_SIZE = 50
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
    ) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).expanduser().resolve()
        self.state_root = Path(state_root or self.project_root / "Resource" / "automation_progress" / "external_agent_batches").expanduser().resolve()
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be an integer between 1 and 1000")
        self.batch_size = batch_size
        self._clock = clock or _utc_now
        roots = allowed_input_roots if allowed_input_roots is not None else (self.project_root,)
        self.allowed_input_roots = tuple(Path(root).expanduser().resolve() for root in roots)
        self._lock = threading.RLock()
        self.state_root.mkdir(parents=True, exist_ok=True)

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
        temporary.write_text(json.dumps(dict(state), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _validate_session(state: Mapping[str, Any], session_id: Any) -> str:
        session_id = _safe_id(session_id, "session_id")
        if session_id != state.get("session_id"):
            raise ExternalAgentBatchError("session does not own this task", "SESSION_MISMATCH")
        return session_id

    def _resolve_input(self, input_path: str | Path) -> Path:
        if not isinstance(input_path, (str, Path)) or not str(input_path).strip():
            raise ExternalAgentBatchError("input_path is required", "INVALID_INPUT_PATH")
        try:
            path = Path(input_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ExternalAgentBatchError("input file does not exist", "INPUT_NOT_FOUND") from exc
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

    def prepare_project(self, input_path: str | Path, task_id: str, session_id: str, execution_mode: str) -> dict[str, Any]:
        task_id = _safe_id(task_id, "task_id")
        session_id = _safe_id(session_id, "session_id")
        if execution_mode != "external_agent":
            raise ExternalAgentBatchError("external Agent batches require external_agent mode", "EXECUTION_MODE_REQUIRED")
        path = self._resolve_input(input_path)
        raw, items = self._source_items(path)
        batches = []
        for start in range(0, len(items), self.batch_size):
            source_items = items[start : start + self.batch_size]
            batches.append({
                "batch_id": f"batch_{len(batches) + 1:06d}", "index": len(batches), "status": "pending",
                "revision": None, "source_hash": self._batch_hash(source_items), "items": source_items,
            })
        with self._lock:
            if self._task_path(task_id).exists():
                raise ExternalAgentBatchError("task already exists", "TASK_ALREADY_EXISTS")
            now = self._clock()
            state = {
                "schema": SCHEMA, "task_id": task_id, "session_id": session_id,
                "execution_mode": execution_mode, "input_path": str(path), "source_hash": _sha256(raw),
                "source_size": len(raw), "revision": 1, "status": "ready" if batches else "completed",
                "batch_size": self.batch_size, "total_batches": len(batches), "created_at": now,
                "updated_at": now, "batches": batches,
            }
            self._write(state)
            return self._project_view(state)

    def prepare_cache_project(self, cache_path: str | Path, task_id: str, session_id: str, execution_mode: str) -> dict[str, Any]:
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
                "revision": None, "source_hash": self._batch_hash(batch_items), "items": batch_items,
            })
        with self._lock:
            if self._task_path(task_id).exists():
                raise ExternalAgentBatchError("task already exists", "TASK_ALREADY_EXISTS")
            now = self._clock()
            state = {
                "schema": SCHEMA, "task_id": task_id, "session_id": session_id,
                "execution_mode": execution_mode, "cache_path_name": manifest["cache_path_name"],
                "cache_path": str(Path(cache_path).expanduser().resolve()),
                "cache_revision": manifest["cache_revision"], "manifest_hash": manifest["manifest_hash"],
                "source_hash": manifest["manifest_hash"], "source_size": manifest["item_count"],
                "revision": 1, "status": "ready" if batches else "completed",
                "batch_size": self.batch_size, "total_batches": len(batches), "created_at": now,
                "updated_at": now, "batches": batches,
            }
            self._write(state)
            return self._project_view(state)

    def cache_path_for_writer(self, task_id: str, session_id: str) -> str:
        with self._lock:
            state = self._read(task_id)
            self._validate_session(state, session_id)
            cache_path = state.get("cache_path")
            if not isinstance(cache_path, str) or not cache_path:
                raise ExternalAgentBatchError("task is not cache-backed", "CACHE_MANIFEST_REQUIRED")
            return cache_path

    @staticmethod
    def _project_view(state: Mapping[str, Any]) -> dict[str, Any]:
        submitted_batches = sum(x.get("status") in {"submitted", "committed"} for x in state["batches"])
        committed_batches = sum(x.get("status") == "committed" for x in state["batches"])
        return {
            "schema": state["schema"], "task_id": state["task_id"], "execution_mode": state["execution_mode"],
            "source_hash": state["source_hash"], "source_size": state["source_size"], "revision": state["revision"],
            "status": state["status"], "total_batches": state["total_batches"],
            # ``submitted`` means only that the result passed validation and
            # was staged.  A project is complete only after the deterministic
            # writer has committed every batch.
            "submitted_batches": submitted_batches,
            "committed_batches": committed_batches,
            "completed_batches": committed_batches,
        }

    @staticmethod
    def _batch_view(batch: Mapping[str, Any]) -> dict[str, Any]:
        return {"batch_id": batch["batch_id"], "index": batch["index"], "status": batch["status"],
                "revision": batch["revision"], "source_hash": batch["source_hash"], "items": deepcopy(batch["items"]),
                "writer_lease_id": batch.get("writer_lease_id"), "cache_revision": batch.get("cache_revision")}

    def claim_batch(self, task_id: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._read(task_id)
            self._validate_session(state, session_id)
            if state["status"] == "completed":
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            for batch in state["batches"]:
                if batch["status"] == "claimed":
                    if batch.get("claimed_session_id") == session_id:
                        return {"status": "claimed", "task": self._project_view(state), "batch": self._batch_view(batch)}
                    raise ExternalAgentBatchError("another batch is currently claimed", "BATCH_IN_USE")
            batch = next((x for x in state["batches"] if x["status"] == "pending"), None)
            if batch is None:
                raise ExternalAgentBatchError("project has no remaining batches", "NO_BATCH_AVAILABLE")
            batch.update({"status": "claimed", "revision": state["revision"], "claimed_session_id": session_id, "claimed_at": self._clock()})
            state.update({"status": "translating", "updated_at": self._clock()})
            self._write(state)
            return {"status": "claimed", "task": self._project_view(state), "batch": self._batch_view(batch)}

    def release_batch(self, task_id: str, session_id: str, batch_id: str) -> dict[str, Any]:
        """Release a claimed batch after a disconnect without accepting results."""
        with self._lock:
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
            state.update({"status": "ready", "updated_at": self._clock()})
            self._write(state)
            return {"status": "released", "task": self._project_view(state), "batch": self._batch_view(batch)}

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
            if index is None and item.get("item_id") in expected_by_item_id:
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
                                 revision: int, idempotency_key: str, items: Any) -> dict[str, Any]:
        with self._lock:
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
            if batch["status"] == "submitted":
                if batch.get("idempotency_key") != idempotency_key:
                    raise ExternalAgentBatchError("batch has already been submitted", "BATCH_ALREADY_SUBMITTED")
                if batch.get("result_fingerprint") != fingerprint:
                    raise ExternalAgentBatchError("idempotency key reused with different data", "IDEMPOTENCY_CONFLICT")
                response = deepcopy(batch["submission"]); response["replayed"] = True; return response
            if batch["status"] != "claimed":
                raise ExternalAgentBatchError("batch is not currently claimed", "BATCH_NOT_CLAIMED")
            if batch.get("claimed_session_id") != session_id:
                raise ExternalAgentBatchError("session does not own this batch", "SESSION_MISMATCH")
            if batch.get("source_hash") != source_hash:
                raise ExternalAgentBatchError("source hash does not match claimed batch", "SOURCE_HASH_MISMATCH")
            if batch.get("revision") != revision or state.get("revision") != revision:
                raise ExternalAgentBatchError("task revision is stale", "REVISION_CONFLICT")
            submission = {"status": "accepted", "task_id": task_id, "batch_id": batch_id, "revision": revision,
                          "next_revision": revision + 1, "result_hash": _sha256(_canonical(result_items)),
                          "items": deepcopy(result_items), "replayed": False}
            batch.update({"status": "submitted", "idempotency_key": idempotency_key, "result_fingerprint": fingerprint,
                          "submitted_at": self._clock(), "submission": submission})
            state["revision"] = revision + 1
            state["status"] = "awaiting_commit" if all(x["status"] == "submitted" for x in state["batches"]) else "ready"
            state["updated_at"] = self._clock(); self._write(state)
            return deepcopy(submission)

    def get_project(self, task_id: str, session_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._read(task_id)
            if session_id is not None: self._validate_session(state, session_id)
            return self._project_view(state)

    def get_ledger(self, task_id: str, session_id: str | None = None) -> dict[str, Any]:
        """Return a session-authorized ledger snapshot for result staging."""
        with self._lock:
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
        with self._lock:
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
            state["status"] = "completed" if all(item.get("status") == "committed" for item in state["batches"]) else "ready"
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


def claim_batch(task_id: str, session_id: str) -> dict[str, Any]:
    return get_external_agent_batch_service().claim_batch(task_id, session_id)


def submit_translation_batch(task_id: str, session_id: str, batch_id: str, source_hash: str, revision: int, idempotency_key: str, items: Any) -> dict[str, Any]:
    return get_external_agent_batch_service().submit_translation_batch(task_id, session_id, batch_id, source_hash, revision, idempotency_key, items)


__all__ = ["SCHEMA", "DEFAULT_BATCH_SIZE", "ExternalAgentBatchError", "BatchError", "ExternalAgentBatchService", "get_external_agent_batch_service", "prepare_project", "claim_batch", "submit_translation_batch"]
