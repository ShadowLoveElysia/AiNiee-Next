"""Session captions with explicitly opt-in transcript recording."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


class SessionHistory:
    def __init__(self):
        self.captions = deque()
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

    def accept(self, event: dict):
        kind = event.get("type")
        if kind == "caption":
            self.captions.append({key: event.get(key) for key in
                                  ("source_text", "translated_text", "start_ms", "end_ms", "sequence")})
        if self.recording and kind in {"transcript", "caption"}:
            row = {**event, "recorded_at": datetime.now(timezone.utc).isoformat()}
            self._record.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._record.flush()

    def clear(self):
        self.captions.clear()
