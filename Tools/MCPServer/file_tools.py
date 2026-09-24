"""Controlled file reads shared by the MCP bridge and WebServer endpoints."""

from __future__ import annotations

import os
import tempfile
import hashlib
import json
import threading
import uuid
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_READ_LINES = 1000
LANGUAGE_SCAN_TIMEOUT_SECONDS = 180
READ_SCHEMA = "ainiee.external_agent.read.v1"


class FileToolError(ValueError):
    """A user-correctable file tool request error."""

    def __init__(self, message: str, code: str = "INVALID_FILE_REQUEST") -> None:
        super().__init__(message)
        self.code = code


def _allowed_roots() -> tuple[Path, ...]:
    roots = [PROJECT_ROOT.resolve()]
    try:
        roots.append(Path(tempfile.gettempdir()).resolve())
    except OSError:
        pass
    configured = os.environ.get("AINIEE_MCP_ALLOWED_PATHS", "")
    for raw in configured.split(os.pathsep):
        raw = raw.strip().strip('"').strip("'")
        if raw:
            roots.append(Path(raw).expanduser().resolve())
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def resolve_file_path(path: Any) -> Path:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise FileToolError("path must be a non-empty file path.", "INVALID_PATH")
    try:
        raw_path = str(path).strip().strip('"').strip("'")
        candidate = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FileToolError("file does not exist.", "FILE_NOT_FOUND") from exc
    if not candidate.is_file():
        raise FileToolError("path must point to a file.", "INVALID_PATH")
    if not any(candidate == root or root in candidate.parents for root in _allowed_roots()):
        raise FileToolError(
            "path is outside the configured MCP file workspace roots.",
            "PATH_NOT_ALLOWED",
        )
    return candidate


def _validate_window(start_line: Any, max_lines: Any) -> tuple[int, int]:
    if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 0:
        raise FileToolError("start_line must be a non-negative integer.", "INVALID_ARGUMENTS")
    if isinstance(max_lines, bool) or not isinstance(max_lines, int):
        raise FileToolError("max_lines must be an integer between 1 and 1000.", "INVALID_ARGUMENTS")
    if not 1 <= max_lines <= MAX_READ_LINES:
        raise FileToolError(
            f"max_lines must be between 1 and {MAX_READ_LINES}.",
            "READ_LIMIT_EXCEEDED",
        )
    return start_line, max_lines


def _raw_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        raise FileToolError("file cannot be read.", "FILE_READ_FAILED") from exc


def _source_items(path: Path, project_type: str = "auto") -> tuple[list[str], dict[str, Any]]:
    """Read logical source items for supported formats, with a text fallback."""
    try:
        from ModuleFolders.Domain.FileReader.FileReader import FileReader

        cache = FileReader().read_files(project_type or "auto", str(path), "")
        items = list(cache.items_iter()) if cache else []
        if items:
            return (
                [str(getattr(item, "source_text", "") or "") for item in items],
                {
                    "project_type": str(getattr(cache, "project_type", "") or project_type or "auto"),
                    "language_stats": _language_stats(cache),
                },
            )
        if path.suffix.lower() not in {".txt", ".md"}:
            return [], {"project_type": project_type or "auto", "language_stats": []}
    except Exception as exc:
        # Never reinterpret a failed EPUB/DOCX parser's ZIP bytes as text.
        if path.suffix.lower() not in {".txt", ".md"}:
            raise FileToolError(
                "The source reader failed; check the format and installed reader dependencies.",
                "FILE_PARSE_FAILED",
            ) from exc
    return _raw_lines(path), {"project_type": project_type or "auto", "language_stats": []}


def _language_stats(cache: Any) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, float]] = {}
    for file_data in getattr(cache, "files", {}).values():
        for entry in getattr(file_data, "language_stats", []) or []:
            if not isinstance(entry, (tuple, list)) or len(entry) < 2:
                continue
            code = str(entry[0] or "un")
            count = int(entry[1] or 0)
            confidence = float(entry[2]) if len(entry) > 2 else 0.0
            row = counts.setdefault(code, {"count": 0, "confidence": 0.0})
            row["count"] += count
            row["confidence"] += confidence * count
    total = sum(int(row["count"]) for row in counts.values())
    ranked = []
    for code, row in counts.items():
        count = int(row["count"])
        ranked.append(
            {
                "language": code,
                "count": count,
                "ratio": count / total if total else 0.0,
                "confidence": row["confidence"] / count if count else 0.0,
            }
        )
    return sorted(ranked, key=lambda item: (-item["count"], -item["confidence"], item["language"]))


def _fallback_language(lines: list[str]) -> list[dict[str, Any]]:
    import re

    text = "\n".join(lines)
    counters = {
        "ja": len(re.findall(r"[\u3040-\u30ff]", text)),
        "ko": len(re.findall(r"[\uac00-\ud7af]", text)),
        "zh": len(re.findall(r"[\u3400-\u9fff]", text)),
        "en": len(re.findall(r"[A-Za-z]", text)),
        "ru": len(re.findall(r"[\u0400-\u04ff]", text)),
    }
    counters = {code: count for code, count in counters.items() if count}
    total = sum(counters.values())
    return [
        {"language": code, "count": count, "ratio": count / total if total else 0.0, "confidence": 0.0}
        for code, count in sorted(counters.items(), key=lambda item: (-item[1], item[0]))
    ]


def read_file_lines(
    path: Any,
    *,
    start_line: Any = 0,
    max_lines: Any = MAX_READ_LINES,
    project_type: str = "auto",
) -> dict[str, Any]:
    start_line, max_lines = _validate_window(start_line, max_lines)
    resolved = resolve_file_path(path)
    lines, metadata = _source_items(resolved, project_type)
    language_stats = metadata.get("language_stats") or _fallback_language(lines)
    selected = lines[start_line : start_line + max_lines]
    return {
        "path": str(resolved),
        "project_type": metadata.get("project_type", project_type or "auto"),
        "start_line": start_line,
        "line_count": len(selected),
        "total_lines": len(lines),
        "next_start_line": start_line + len(selected) if start_line + len(selected) < len(lines) else None,
        "has_more": start_line + len(selected) < len(lines),
        "max_lines": MAX_READ_LINES,
        "language": language_stats[0]["language"] if language_stats else "un",
        "language_stats": language_stats,
        "lines": [
            {"index": start_line + index, "text": text}
            for index, text in enumerate(selected)
        ],
    }


def detect_file_language(path: Any, *, project_type: str = "auto") -> dict[str, Any]:
    """Detect language across the entire file, independently of transfer limits."""
    resolved = resolve_file_path(path)
    lines, metadata = _source_items(resolved, project_type)
    language_stats = metadata.get("language_stats") or _fallback_language(lines)
    return {
        "path": str(resolved),
        "project_type": metadata.get("project_type", project_type or "auto"),
        "scan_scope": "full_file",
        "total_lines": len(lines),
        "scanned_lines": len(lines),
        "language": language_stats[0]["language"] if language_stats else "un",
        "language_stats": language_stats,
    }


async def detect_file_language_isolated(path: str, *, project_type: str = "auto") -> dict[str, Any]:
    """Keep native reader imports away from the live MCP stdio reader thread."""
    import asyncio
    import sys

    resolved = resolve_file_path(path)
    request = json.dumps({"path": str(resolved), "project_type": project_type}).encode("utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(Path(__file__).with_name("language_worker.py")),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
    except OSError as exc:
        raise FileToolError("Unable to start the language scan worker.", "LANGUAGE_SCAN_START_FAILED") from exc
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(request), timeout=LANGUAGE_SCAN_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError as exc:
        raise FileToolError(
            f"Full-file language detection exceeded {LANGUAGE_SCAN_TIMEOUT_SECONDS} seconds.",
            "LANGUAGE_SCAN_TIMEOUT",
        ) from exc
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
    if process.returncode != 0:
        raise FileToolError("The language scan worker exited unexpectedly.", "LANGUAGE_SCAN_FAILED")
    try:
        payload = json.loads(stdout)
        if payload["ok"] is True and isinstance(payload["result"], dict):
            return payload["result"]
        if payload["ok"] is False:
            raise FileToolError(payload["error"], payload["error_code"])
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, FileToolError):
            raise
        raise FileToolError("Invalid language scan worker response.", "LANGUAGE_SCAN_FAILED") from exc
    raise FileToolError("Invalid language scan worker response.", "LANGUAGE_SCAN_FAILED")


class AgentReadBatchService:
    """Durable, read-only source batches for Agent-side analysis.

    The service mirrors the claim protocol used by translation batches. A
    prepare call creates all opaque batch IDs, and each claim returns at most
    ``MAX_READ_LINES`` source items. No cache, source, or glossary is written.
    """

    def __init__(self, state_root: str | Path | None = None):
        self.state_root = Path(state_root or PROJECT_ROOT / "Resource" / "automation_progress" / "external_agent_reads").resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _safe_id(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise FileToolError(f"{name} must be a non-empty string.", "INVALID_ARGUMENTS")
        return value.strip()

    def _path(self, task_id: str) -> Path:
        safe = self._safe_id(task_id, "task_id")
        if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in safe):
            raise FileToolError("task_id contains unsupported characters.", "INVALID_ARGUMENTS")
        return self.state_root / f"{safe}.json"

    def _read(self, task_id: str) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.is_file():
            raise FileToolError("read task does not exist.", "READ_TASK_NOT_FOUND")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FileToolError("read task state is invalid.", "READ_TASK_INVALID") from exc
        if not isinstance(value, dict) or value.get("schema") != READ_SCHEMA:
            raise FileToolError("read task state is invalid.", "READ_TASK_INVALID")
        return value

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def prepare(self, path: Any, task_id: Any, session_id: Any, *, project_type: str = "auto") -> dict[str, Any]:
        task_id = self._safe_id(task_id, "task_id")
        session_id = self._safe_id(session_id, "session_id")
        resolved = resolve_file_path(path)
        lines, metadata = _source_items(resolved, project_type)
        source_hash = self._hash(lines)
        batches = []
        for start in range(0, len(lines), MAX_READ_LINES):
            items = [{"index": start + index, "source": text} for index, text in enumerate(lines[start:start + MAX_READ_LINES])]
            batches.append({
                "batch_id": f"read_{uuid.uuid4().hex[:20]}",
                "index": len(batches),
                "status": "pending",
                "revision": 1,
                "source_hash": self._hash(items),
                "items": items,
            })
        state = {
            "schema": READ_SCHEMA,
            "task_id": task_id,
            "session_id": session_id,
            "path": str(resolved),
            "project_type": metadata.get("project_type", project_type or "auto"),
            "source_hash": source_hash,
            "revision": 1,
            "total_lines": len(lines),
            "batch_size": MAX_READ_LINES,
            "batches": batches,
        }
        with self._lock:
            if self._path(task_id).exists():
                raise FileToolError("read task already exists.", "READ_TASK_ALREADY_EXISTS")
            self._path(task_id).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._project_view(state)

    @staticmethod
    def _project_view(state: dict[str, Any]) -> dict[str, Any]:
        summaries = [
            {
                "batch_id": item["batch_id"],
                "index": item["index"],
                "status": item["status"],
                "source_hash": item["source_hash"],
                "revision": item.get("revision", state.get("revision", 1)),
                "item_count": len(item.get("items") or []),
            }
            for item in state.get("batches", [])
        ]
        next_batch = next((item for item in summaries if item["status"] in {"pending", "claimed"}), None)
        return {
            "schema": READ_SCHEMA,
            "task_id": state["task_id"],
            "path": state["path"],
            "project_type": state.get("project_type", "auto"),
            "source_hash": state["source_hash"],
            "revision": state["revision"],
            "total_lines": state["total_lines"],
            "batch_size": MAX_READ_LINES,
            "total_batches": len(summaries),
            "batches": summaries,
            "batch_ids": [item["batch_id"] for item in summaries],
            "next_batch_id": next_batch["batch_id"] if next_batch else None,
        }

    def status(self, task_id: Any, session_id: Any) -> dict[str, Any]:
        session_id = self._safe_id(session_id, "session_id")
        with self._lock:
            state = self._read(task_id)
            if state.get("session_id") != session_id:
                raise FileToolError("session does not own this read task.", "SESSION_MISMATCH")
            return self._project_view(state)

    def claim(self, task_id: Any, session_id: Any, batch_id: Any = None) -> dict[str, Any]:
        session_id = self._safe_id(session_id, "session_id")
        with self._lock:
            state = self._read(task_id)
            if state.get("session_id") != session_id:
                raise FileToolError("session does not own this read task.", "SESSION_MISMATCH")
            claimed = next((item for item in state["batches"] if item["status"] == "claimed"), None)
            if claimed and claimed.get("claimed_session_id") != session_id:
                raise FileToolError("another read batch is currently claimed.", "READ_BATCH_IN_USE")
            if claimed:
                return {"status": "claimed", "task": self._project_view(state), "batch": claimed}
            if batch_id is not None:
                batch = next((item for item in state["batches"] if item["batch_id"] == batch_id), None)
            else:
                batch = next((item for item in state["batches"] if item["status"] == "pending"), None)
            if batch is None:
                raise FileToolError("read task has no remaining batches.", "NO_READ_BATCH_AVAILABLE")
            if batch.get("status") != "pending":
                raise FileToolError("requested read batch is not pending.", "READ_BATCH_NOT_PENDING")
            batch["status"] = "claimed"
            batch["claimed_session_id"] = session_id
            state["revision"] += 1
            batch["revision"] = state["revision"]
            self._path(str(task_id)).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"status": "claimed", "task": self._project_view(state), "batch": batch}

    def complete(self, task_id: Any, session_id: Any, batch_id: Any) -> dict[str, Any]:
        session_id = self._safe_id(session_id, "session_id")
        batch_id = self._safe_id(batch_id, "batch_id")
        with self._lock:
            state = self._read(task_id)
            if state.get("session_id") != session_id:
                raise FileToolError("session does not own this read task.", "SESSION_MISMATCH")
            batch = next((item for item in state["batches"] if item.get("batch_id") == batch_id), None)
            if batch is None:
                raise FileToolError("read batch does not exist.", "READ_BATCH_NOT_FOUND")
            if batch.get("status") == "completed":
                return {"status": "completed", "task": self._project_view(state), "batch": batch}
            if batch.get("status") != "claimed" or batch.get("claimed_session_id") != session_id:
                raise FileToolError("read batch is not claimed by this session.", "READ_BATCH_NOT_CLAIMED")
            batch["status"] = "completed"
            batch.pop("claimed_session_id", None)
            state["revision"] += 1
            self._path(str(task_id)).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"status": "completed", "task": self._project_view(state), "batch": batch}

    def release(self, task_id: Any, session_id: Any, batch_id: Any) -> dict[str, Any]:
        session_id = self._safe_id(session_id, "session_id")
        batch_id = self._safe_id(batch_id, "batch_id")
        with self._lock:
            state = self._read(task_id)
            if state.get("session_id") != session_id:
                raise FileToolError("session does not own this read task.", "SESSION_MISMATCH")
            batch = next((item for item in state["batches"] if item.get("batch_id") == batch_id), None)
            if batch is None:
                raise FileToolError("read batch does not exist.", "READ_BATCH_NOT_FOUND")
            if batch.get("status") == "completed":
                return {"status": "completed", "task": self._project_view(state), "batch": batch}
            if batch.get("status") != "claimed" or batch.get("claimed_session_id") != session_id:
                raise FileToolError("read batch is not claimed by this session.", "READ_BATCH_NOT_CLAIMED")
            batch["status"] = "pending"
            batch.pop("claimed_session_id", None)
            state["revision"] += 1
            self._path(str(task_id)).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"status": "released", "task": self._project_view(state), "batch": batch}


_READ_BATCH_SERVICE: AgentReadBatchService | None = None
_READ_BATCH_LOCK = threading.Lock()


def get_agent_read_batch_service() -> AgentReadBatchService:
    global _READ_BATCH_SERVICE
    if _READ_BATCH_SERVICE is None:
        with _READ_BATCH_LOCK:
            if _READ_BATCH_SERVICE is None:
                _READ_BATCH_SERVICE = AgentReadBatchService()
    return _READ_BATCH_SERVICE


__all__ = [
    "FileToolError",
    "MAX_READ_LINES",
    "detect_file_language",
    "detect_file_language_isolated",
    "read_file_lines",
    "resolve_file_path",
    "AgentReadBatchService",
    "get_agent_read_batch_service",
]
