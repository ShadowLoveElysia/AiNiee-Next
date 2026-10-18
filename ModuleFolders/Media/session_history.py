"""Temporary disk-backed caption history and explicitly opt-in recordings."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import struct
import tempfile
import uuid
import weakref


MAX_IN_MEMORY_CAPTIONS = 32
CAPTION_FIELDS = ("source_text", "translated_text", "start_ms", "end_ms", "sequence")
_OFFSET = struct.Struct("<Q")


class HistoryStorageError(OSError):
    pass


def _remove_history(history, index, directory):
    try:
        history.close()
    finally:
        try:
            index.close()
        finally:
            shutil.rmtree(directory, ignore_errors=True)


class SessionHistory:
    def __init__(self, *, max_captions: int = MAX_IN_MEMORY_CAPTIONS, temp_dir: str | Path | None = None):
        if isinstance(max_captions, bool) or not isinstance(max_captions, int) or max_captions <= 0:
            raise ValueError("Maximum caption count must be a positive integer")
        self.captions = deque(maxlen=max_captions)
        self._temp_dir = temp_dir
        self._history_cleanup = None
        self._history = self._index = None
        self.history_path = None
        self.count = 0
        self.generation = 0
        self._record = None
        self.record_path = None

    @property
    def recording(self):
        return self._record is not None

    def begin_recording(self, directory: str):
        if self.recording:
            return
        root = Path(directory).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        name = f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.jsonl"
        path = root / name
        stream = path.open("x", encoding="utf-8")
        self._record, self.record_path = stream, path

    def end_recording(self):
        if self._record is not None:
            self._record.close()
            self._record = None

    def _open_history(self):
        if self._history is not None:
            return
        directory = tempfile.mkdtemp(prefix="ainiee-live-history-", dir=self._temp_dir)
        path = Path(directory) / "captions.jsonl"
        history = None
        try:
            history = path.open("w+b")
            index = path.with_suffix(".idx").open("w+b")
        except OSError:
            if history is not None:
                history.close()
            shutil.rmtree(directory, ignore_errors=True)
            raise
        self.history_path = path
        self._history, self._index = history, index
        # One finalizer owns both handles and deletion. Independent temporary
        # directory finalization can race open handles during cyclic GC on Windows.
        self._history_cleanup = weakref.finalize(self, _remove_history, history, index, directory)

    def _append_history(self, caption):
        self._open_history()
        self._history.seek(0, 2)
        offset = self._history.tell()
        self._index.seek(self.count * _OFFSET.size)
        try:
            self._history.write((json.dumps(caption, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            self._history.flush()
            self._index.write(_OFFSET.pack(offset))
            self._index.flush()
        except OSError:
            self._history.truncate(offset)
            self._index.truncate(self.count * _OFFSET.size)
            raise
        self.count += 1

    def accept(self, event: dict):
        kind = event.get("type")
        history_error = None
        if kind == "caption":
            caption = {key: event.get(key) for key in CAPTION_FIELDS}
            self.captions.append(caption)
            try:
                self._append_history(caption)
            except OSError as error:
                history_error = error
        if self.recording and kind in {"transcript", "caption"}:
            row = {**event, "recorded_at": datetime.now(timezone.utc).isoformat()}
            self._record.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._record.flush()
        if history_error is not None:
            raise HistoryStorageError("Could not save temporary caption history") from history_error

    def read_page(self, start: int, limit: int = MAX_IN_MEMORY_CAPTIONS):
        """Read a bounded page using an on-disk offset index, independent of session length."""
        if start < 0 or limit <= 0:
            raise ValueError("Invalid caption page")
        if self._history is None or start >= self.count:
            return []
        self._index.seek(start * _OFFSET.size)
        entry = self._index.read(_OFFSET.size)
        if len(entry) != _OFFSET.size:
            raise HistoryStorageError("Incomplete temporary caption index")
        offset = _OFFSET.unpack(entry)[0]
        self._history.seek(offset)
        try:
            return [json.loads(self._history.readline()) for _ in range(min(limit, self.count - start))]
        except ValueError as error:
            raise HistoryStorageError("Invalid temporary caption history") from error

    def iter_captions(self, *, limit: int | None = None):
        if limit is not None and limit <= 0:
            raise ValueError("History limit must be positive")
        start = 0 if limit is None else max(0, self.count - limit)
        while start < self.count:
            rows = self.read_page(start)
            yield from rows
            start += len(rows)

    def clear(self):
        self.captions.clear()
        self.count = 0
        self.generation += 1
        if self._history_cleanup is not None:
            self._history_cleanup()
            self._history_cleanup = None
        self._index = self._history = None
        self.history_path = None

    def close(self):
        self.end_recording()
        self.clear()

    def __del__(self):
        try:
            self.close()
        except (OSError, AttributeError):
            pass
