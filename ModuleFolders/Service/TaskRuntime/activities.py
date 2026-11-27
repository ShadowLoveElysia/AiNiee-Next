"""Lifecycle hooks for auxiliary services sharing the API process owner."""
from __future__ import annotations

from collections.abc import Callable
import threading

_lock = threading.RLock()
_activities: dict[str, tuple[Callable[[], bool], Callable[[], bool]]] = {}


def register_activity(name: str, active: Callable[[], bool], stop: Callable[[], bool]) -> None:
    with _lock:
        _activities[name] = (active, stop)


def auxiliary_active() -> bool:
    with _lock:
        callbacks = tuple(_activities.values())
    return any(active() for active, _ in callbacks)


def stop_auxiliaries() -> bool:
    with _lock:
        callbacks = tuple(_activities.values())
    stopped = True
    for _, stop in callbacks:
        try:
            stopped = (stop() is True) and stopped
        except Exception:
            stopped = False
    return stopped
