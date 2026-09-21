"""Deterministic writer for results returned by an external Agent.

The MCP/Skills boundary only stages structured results.  This service is the
separate, trusted writer which resolves opaque cache locations, verifies the
source and cache revision, and commits a complete cache document atomically.
It intentionally accepts a cache file path only when that path is inside an
explicitly controlled root and never accepts a path supplied by an item as a
filesystem path.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Mapping, Sequence

from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus


class ExternalAgentBatchWriterError(ValueError):
    """A staged result was rejected before the cache could be mutated."""

    def __init__(self, message: str, code: str = "CACHE_WRITE_REJECTED") -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": str(self)}


BatchWriterError = ExternalAgentBatchWriterError
_SHA256_RE = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_SAFE_RELATIVE = re.compile(r"^[^\x00]+\Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _normal_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ExternalAgentBatchWriterError(f"{field} must be a SHA-256 digest", "INVALID_HASH")
    return value.removeprefix("sha256:")


def _canonical_line_hash(item: Mapping[str, Any]) -> str:
    payload = {
        "source_text": item.get("source_text", ""),
        "translated_text": item.get("translated_text", ""),
        "polished_text": item.get("polished_text", ""),
        "translation_status": item.get("translation_status", TranslationStatus.UNTRANSLATED),
    }
    return _sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _safe_storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value or not _SAFE_RELATIVE.fullmatch(value):
        raise ExternalAgentBatchWriterError("storage_path is invalid", "INVALID_STORAGE_PATH")
    # Protocol keys are cache keys, never host filesystem paths.
    key = value.replace("\\", "/")
    if key.startswith("/") or re.match(r"^[A-Za-z]:", key) or any(part in ("", ".", "..") for part in key.split("/")):
        raise ExternalAgentBatchWriterError("storage_path must be a controlled relative key", "INVALID_STORAGE_PATH")
    return key


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExternalAgentBatchWriterError("JSON document is unreadable", "DOCUMENT_INVALID") from exc


class ExternalAgentBatchWriter:
    """Apply a complete Agent batch to one controlled cache document.

    ``writer_lease_validator`` is deliberately injectable.  Production code
    should bind it to the task writer-lease registry; tests can provide a
    deterministic validator without starting MCP or Skills.
    """

    def __init__(
        self,
        project_root: str | Path | None = None,
        *,
        allowed_cache_roots: Sequence[str | Path] | None = None,
        backup_root: str | Path | None = None,
        writer_lease_validator: Callable[[Mapping[str, Any], str], bool] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).expanduser().resolve()
        roots = allowed_cache_roots if allowed_cache_roots is not None else (self.project_root,)
        self.allowed_cache_roots = tuple(Path(root).expanduser().resolve() for root in roots)
        self.backup_root = Path(backup_root).expanduser().resolve() if backup_root is not None else None
        self.writer_lease_validator = writer_lease_validator
        self._clock = clock or (lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"))
        self._lock = threading.RLock()

    def _resolve_cache_path(self, cache_path: str | Path) -> Path:
        if not isinstance(cache_path, (str, Path)) or not str(cache_path).strip():
            raise ExternalAgentBatchWriterError("cache_path is required", "INVALID_CACHE_PATH")
        try:
            path = Path(cache_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ExternalAgentBatchWriterError("cache file does not exist", "CACHE_NOT_FOUND") from exc
        if not path.is_file() or path.name != "AinieeCacheData.json":
            raise ExternalAgentBatchWriterError("cache_path must be AinieeCacheData.json", "INVALID_CACHE_PATH")
        if not any(path == root or root in path.parents for root in self.allowed_cache_roots):
            raise ExternalAgentBatchWriterError("cache_path is outside controlled roots", "CACHE_PATH_OUTSIDE_PROJECT")
        return path

    @staticmethod
    def _document_files(document: Mapping[str, Any]) -> dict[str, Any]:
        files = document.get("files")
        if not isinstance(files, dict):
            raise ExternalAgentBatchWriterError("cache files are invalid", "CACHE_SCHEMA_INVALID")
        return files

    @staticmethod
    def _staged_records(staged: Mapping[str, Any], batch_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(staged, Mapping):
            raise ExternalAgentBatchWriterError("staged result must be an object", "STAGED_RESULT_INVALID")
        records = staged.get("results")
        if isinstance(records, list):
            candidates = [record for record in records if isinstance(record, Mapping)]
            if batch_id is not None:
                candidates = [record for record in candidates if record.get("batch_id") == batch_id]
            if not candidates:
                raise ExternalAgentBatchWriterError("staged batch does not exist", "BATCH_NOT_FOUND")
            record = candidates[-1]
        else:
            record = staged
        if record.get("status") not in (None, "accepted"):
            raise ExternalAgentBatchWriterError("staged result is not accepted", "STAGED_RESULT_INVALID")
        raw_items = record.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ExternalAgentBatchWriterError("staged result has no items", "STAGED_RESULT_INVALID")
        return dict(record), [dict(item) if isinstance(item, Mapping) else item for item in raw_items]

    @staticmethod
    def _cache_revision(document: Mapping[str, Any], raw: bytes) -> str | int:
        for key in ("cache_snapshot_hash", "cache_revision", "revision"):
            value = document.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return value
        extra = document.get("extra")
        if isinstance(extra, Mapping):
            for key in ("cache_snapshot_hash", "cache_revision", "revision"):
                value = extra.get(key)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    return value
        return _sha256_bytes(raw)

    @staticmethod
    def _staged_revision(record: Mapping[str, Any]) -> Any:
        for key in ("cache_snapshot_hash", "cache_revision", "current_revision"):
            if key in record:
                return record[key]
        # A numeric ``revision`` is accepted only when the cache document also
        # carries a numeric revision.  Batch/task revision must not silently
        # masquerade as cache revision.
        return record.get("revision")

    @staticmethod
    def _find_item(file_record: Any, text_index: int) -> tuple[Any, Any]:
        if not isinstance(file_record, Mapping):
            raise ExternalAgentBatchWriterError("cache file record is invalid", "CACHE_SCHEMA_INVALID")
        items = file_record.get("items")
        if isinstance(items, list):
            matches = [(index, item) for index, item in enumerate(items) if isinstance(item, Mapping) and item.get("text_index") == text_index]
            if len(matches) != 1:
                raise ExternalAgentBatchWriterError("text_index is missing or ambiguous", "ITEM_NOT_FOUND")
            return matches[0]
        if isinstance(items, dict):
            matches = [(key, item) for key, item in items.items() if isinstance(item, Mapping) and item.get("text_index", key) == text_index]
            if len(matches) != 1:
                raise ExternalAgentBatchWriterError("text_index is missing or ambiguous", "ITEM_NOT_FOUND")
            return matches[0]
        raise ExternalAgentBatchWriterError("cache items are invalid", "CACHE_SCHEMA_INVALID")

    @staticmethod
    def _set_item(file_record: Mapping[str, Any], item_key: Any, item: Mapping[str, Any], translation: str) -> None:
        # ``item`` is a mutable child of the copied JSON document.
        item["translated_text"] = translation  # type: ignore[index]
        item["translation_status"] = TranslationStatus.TRANSLATED  # type: ignore[index]

    def _validate_and_apply(self, document: dict[str, Any], record: Mapping[str, Any], items: list[dict[str, Any]], raw: bytes, writer_lease_id: str) -> None:
        if not isinstance(writer_lease_id, str) or not writer_lease_id:
            raise ExternalAgentBatchWriterError("writer lease is required", "WRITER_LEASE_REQUIRED")
        if self.writer_lease_validator is not None and not self.writer_lease_validator(record, writer_lease_id):
            raise ExternalAgentBatchWriterError("writer lease is not authorized", "WRITER_LEASE_UNAUTHORIZED")
        expected_revision = self._staged_revision(record)
        current_revision = self._cache_revision(document, raw)
        if expected_revision is None:
            raise ExternalAgentBatchWriterError("cache revision is required", "REVISION_REQUIRED")
        if isinstance(expected_revision, str) and expected_revision.startswith("sha256:"):
            expected_revision = expected_revision.removeprefix("sha256:")
        if expected_revision != current_revision:
            raise ExternalAgentBatchWriterError("cache revision is stale", "REVISION_CONFLICT")

        files = self._document_files(document)
        seen: set[tuple[str, int]] = set()
        for entry in items:
            if not isinstance(entry, Mapping):
                raise ExternalAgentBatchWriterError("batch item is invalid", "ITEM_INVALID")
            storage = entry.get("storage_path", entry.get("file_key"))
            key = _safe_storage_key(storage)
            if "storage_path" in entry and "file_key" in entry and entry["storage_path"] != entry["file_key"]:
                raise ExternalAgentBatchWriterError("storage_path and file_key differ", "ITEM_UNAUTHORIZED")
            if key not in files:
                raise ExternalAgentBatchWriterError("item file is outside the cache manifest", "ITEM_UNAUTHORIZED")
            text_index = entry.get("text_index")
            if isinstance(text_index, bool) or not isinstance(text_index, int):
                raise ExternalAgentBatchWriterError("text_index is invalid", "ITEM_INVALID")
            identity = (key, text_index)
            if identity in seen:
                raise ExternalAgentBatchWriterError("batch contains duplicate item", "ITEM_INVALID")
            seen.add(identity)
            _, current = self._find_item(files[key], text_index)
            if not isinstance(current, Mapping):
                raise ExternalAgentBatchWriterError("cache item is invalid", "CACHE_SCHEMA_INVALID")
            source = current.get("source_text", "")
            if entry.get("source_text") != source:
                raise ExternalAgentBatchWriterError("source_text does not match cache", "SOURCE_MISMATCH")
            source_hash = _normal_hash(entry.get("source_hash"), "source_hash")
            if source_hash != _sha256_text(source):
                raise ExternalAgentBatchWriterError("source_hash does not match cache", "SOURCE_HASH_MISMATCH")
            if "current_line_hash" in entry and entry["current_line_hash"] != _canonical_line_hash(current):
                raise ExternalAgentBatchWriterError("cache item has changed", "ITEM_CONFLICT")
            translation = entry.get("translation", entry.get("translated_text"))
            if not isinstance(translation, str) or not translation:
                raise ExternalAgentBatchWriterError("translation must be a non-empty string", "ITEM_INVALID")
            status = current.get("translation_status", TranslationStatus.UNTRANSLATED)
            existing = current.get("translated_text", "")
            if status != TranslationStatus.UNTRANSLATED or existing:
                if existing == translation and status == TranslationStatus.TRANSLATED:
                    continue
                raise ExternalAgentBatchWriterError("cache item was already changed", "ITEM_CONFLICT")
            self._set_item(files[key], _, current, translation)

    def _backup(self, cache_path: Path, raw: bytes) -> Path:
        root = self.backup_root or cache_path.parent / "backups"
        root.mkdir(parents=True, exist_ok=True)
        digest = _sha256_bytes(raw)
        target = root / f"AinieeCacheData_agent_{self._clock()}_{digest}.json"
        temporary = target.with_name(target.name + f".{os.getpid()}.tmp")
        try:
            with open(temporary, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return target

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
        try:
            with open(temporary, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def apply_staged_result(self, cache_path: str | Path, staged: Mapping[str, Any] | str | Path, *, writer_lease_id: str, batch_id: str | None = None) -> dict[str, Any]:
        path = self._resolve_cache_path(cache_path)
        with self._lock:
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise ExternalAgentBatchWriterError("cache file cannot be read", "CACHE_READ_FAILED") from exc
            try:
                document = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ExternalAgentBatchWriterError("cache document is invalid", "CACHE_SCHEMA_INVALID") from exc
            if not isinstance(document, dict):
                raise ExternalAgentBatchWriterError("cache document is invalid", "CACHE_SCHEMA_INVALID")
            if isinstance(staged, (str, Path)):
                staged_value = _load_json(Path(staged).expanduser().resolve(strict=True))
            else:
                staged_value = staged
            record, items = self._staged_records(staged_value, batch_id)
            candidate = deepcopy(document)
            self._validate_and_apply(candidate, record, items, raw, writer_lease_id)
            encoded = json.dumps(candidate, ensure_ascii=False, indent=2).encode("utf-8")
            backup = self._backup(path, raw)
            try:
                self._atomic_write(path, encoded)
            except Exception:
                # The pre-commit backup remains available and the old cache is
                # still intact when os.replace itself fails.
                raise
            return {
                "status": "persisted", "task_id": record.get("task_id"),
                "batch_id": record.get("batch_id"), "writer_lease_id": writer_lease_id,
                "backup_path": str(backup), "item_count": len(items),
                "cache_revision": _sha256_bytes(encoded),
            }


__all__ = ["ExternalAgentBatchWriter", "ExternalAgentBatchWriterError", "BatchWriterError"]
