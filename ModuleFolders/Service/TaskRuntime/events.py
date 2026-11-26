"""Bounded event storage with cursors independent of retained buffer length."""
from __future__ import annotations

from collections import deque
import threading
from typing import Any


class SequencedBuffer(deque):
    def __init__(self, maxlen: int, *, lock=None):
        super().__init__(maxlen=maxlen)
        self.sequence = 0
        self._cleared_at: int | None = None
        self._lock = lock if lock is not None else threading.RLock()

    def append(self, value: dict[str, Any]) -> None:
        with self._lock:
            self.sequence += 1
            super().append({**value, "seq": self.sequence})

    def extend(self, values) -> None:
        with self._lock:
            for value in values:
                self.append(value)

    def clear(self) -> None:
        with self._lock:
            super().clear()
            self._cleared_at = self.sequence

    def snapshot(self, cursor: int) -> tuple[list[dict[str, Any]], int, bool]:
        with self._lock:
            earliest = self[0]["seq"] if self else self.sequence + 1
            reset = (
                cursor < earliest - 1
                or cursor > self.sequence
                or cursor < 0
                or (self._cleared_at is not None and cursor <= self._cleared_at)
            )
            items = [dict(item) for item in self if reset or item["seq"] > cursor]
            return items, self.sequence, reset
