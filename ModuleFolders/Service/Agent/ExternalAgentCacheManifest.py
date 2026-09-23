"""Build a stable, opaque manifest for external-Agent cache batches.

The manifest is a read-only snapshot.  It gives a later writer enough
information to resolve an item against the currently loaded cache without
allowing an Agent to turn a protocol storage key into an arbitrary filesystem
path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus


class ExternalAgentCacheManifestError(ValueError):
    def __init__(self, message: str, code: str = "MANIFEST_INVALID") -> None:
        super().__init__(message)
        self.code = code


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ExternalAgentCacheManifestError("storage_path is invalid", "INVALID_STORAGE_PATH")
    value = value.replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value) or any(part in ("", ".", "..") for part in value.split("/")):
        raise ExternalAgentCacheManifestError("storage_path must be relative", "INVALID_STORAGE_PATH")
    return value


class ExternalAgentCacheManifestService:
    def __init__(self, project_root: str | Path | None = None, *, allowed_cache_roots: Sequence[str | Path] | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).expanduser().resolve()
        roots = allowed_cache_roots if allowed_cache_roots is not None else (self.project_root,)
        self.allowed_cache_roots = tuple(Path(root).expanduser().resolve() for root in roots)

    def _resolve(self, cache_path: str | Path) -> Path:
        try:
            path = Path(cache_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ExternalAgentCacheManifestError("cache file does not exist", "CACHE_NOT_FOUND") from exc
        if path.name != "AinieeCacheData.json" or not path.is_file():
            raise ExternalAgentCacheManifestError("cache_path must be AinieeCacheData.json", "INVALID_CACHE_PATH")
        if not any(path == root or root in path.parents for root in self.allowed_cache_roots):
            raise ExternalAgentCacheManifestError("cache_path is outside controlled roots", "CACHE_PATH_OUTSIDE_PROJECT")
        return path

    def build(self, cache_path: str | Path) -> dict[str, Any]:
        path = self._resolve(cache_path)
        try:
            raw = path.read_bytes(); document = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ExternalAgentCacheManifestError("cache document is unreadable", "CACHE_SCHEMA_INVALID") from exc
        return self.build_document(
            document, raw=raw, cache_path_name=path.name, project_identity=str(path)
        )

    def build_runtime_project(self, project: Any) -> dict[str, Any]:
        """Build a manifest from a live ``CacheProject`` snapshot.

        CacheManager can use this while a task is running, before a cache file
        has been flushed.  msgspec encoding is used for the revision so the
        value is identical to the bytes written by CacheManager.save_to_file.
        """
        try:
            import msgspec

            raw = msgspec.json.encode(project)
            document = json.loads(raw.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ExternalAgentCacheManifestError("runtime cache project is invalid", "CACHE_SCHEMA_INVALID") from exc
        project_identity = getattr(project, "project_id", None) or document.get("project_id")
        return self.build_document(
            document,
            raw=raw,
            cache_path_name="AinieeCacheData.json",
            project_identity=str(project_identity or "runtime-cache"),
        )

    def build_document(
        self,
        document: Mapping[str, Any],
        *,
        raw: bytes,
        cache_path_name: str,
        project_identity: str | None = None,
    ) -> dict[str, Any]:
        """Build a manifest from a decoded cache document and its raw bytes."""
        if not isinstance(document, Mapping) or not isinstance(document.get("files"), Mapping):
            raise ExternalAgentCacheManifestError("cache files are invalid", "CACHE_SCHEMA_INVALID")
        project_id = str(
            document.get("project_id")
            or _digest({"cache": project_identity or cache_path_name})[:32]
        )
        files: list[dict[str, Any]] = []
        manifest_items: list[dict[str, Any]] = []
        for raw_key, file_record in document["files"].items():
            storage_path = _key(raw_key)
            if not isinstance(file_record, Mapping) or not isinstance(file_record.get("items"), list):
                raise ExternalAgentCacheManifestError("cache file items are invalid", "CACHE_SCHEMA_INVALID")
            file_id = _digest({"project_id": project_id, "storage_path": storage_path})[:32]
            entries: list[dict[str, Any]] = []
            seen: set[int] = set()
            for item in file_record["items"]:
                if not isinstance(item, Mapping) or isinstance(item.get("text_index"), bool) or not isinstance(item.get("text_index"), int):
                    raise ExternalAgentCacheManifestError("cache text_index is invalid", "CACHE_SCHEMA_INVALID")
                # Excluded, already translated, and proofread cache rows are
                # owned by the deterministic cache workflow and must not be
                # offered to an external Agent for translation writeback.
                translation_status = item.get("translation_status", TranslationStatus.UNTRANSLATED)
                if translation_status != TranslationStatus.UNTRANSLATED:
                    continue
                text_index = item["text_index"]
                if text_index in seen:
                    raise ExternalAgentCacheManifestError("duplicate text_index in cache file", "CACHE_SCHEMA_INVALID")
                seen.add(text_index)
                source_text = item.get("source_text", "")
                if not isinstance(source_text, str):
                    raise ExternalAgentCacheManifestError("source_text is invalid", "CACHE_SCHEMA_INVALID")
                item_id = _digest({"project_id": project_id, "storage_path": storage_path, "text_index": text_index})[:32]
                line_hash = _digest({
                    "source_text": source_text,
                    "translated_text": item.get("translated_text", ""),
                    "polished_text": item.get("polished_text", ""),
                    "translation_status": translation_status,
                })
                entry = {
                    "item_id": item_id, "file_id": file_id, "storage_path": storage_path,
                    "text_index": text_index, "source_text": source_text,
                    "source_hash": _text_hash(source_text), "current_line_hash": line_hash,
                    # Keep the snapshot revision on each opaque locator.  A
                    # later batch commit can then bind its staged result to
                    # the exact cache revision it was prepared against.
                    "cache_revision": None,
                    "translation_status": item.get("translation_status", TranslationStatus.UNTRANSLATED),
                }
                entries.append(entry); manifest_items.append(entry)
            files.append({"file_id": file_id, "storage_path": storage_path, "items": entries})
        cache_revision = hashlib.sha256(raw).hexdigest()
        manifest = {
            "schema": "ainiee.external_agent.cache_manifest.v1", "project_id": project_id,
            "cache_path_name": cache_path_name, "cache_revision": cache_revision,
            "files": files, "item_count": len(manifest_items),
        }
        for item in manifest_items:
            item["cache_revision"] = cache_revision
        manifest["manifest_hash"] = _digest({"project_id": project_id, "cache_revision": cache_revision, "files": files})
        return manifest


__all__ = ["ExternalAgentCacheManifestService", "ExternalAgentCacheManifestError"]
