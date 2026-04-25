"""MangaCore entrypoints."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .io.persistence import MangaProjectPersistence
    from .pipeline.runnerBatch import MangaBatchRunResult, MangaBatchRunner
    from .project.session import MangaProjectSession, SessionRegistry

__all__ = [
    "MangaBatchRunResult",
    "MangaBatchRunner",
    "MangaProjectPersistence",
    "MangaProjectSession",
    "SessionRegistry",
]


def __getattr__(name: str) -> Any:
    if name == "MangaProjectPersistence":
        return getattr(import_module(".io.persistence", __name__), name)
    if name in {"MangaBatchRunResult", "MangaBatchRunner"}:
        return getattr(import_module(".pipeline.runnerBatch", __name__), name)
    if name in {"MangaProjectSession", "SessionRegistry"}:
        return getattr(import_module(".project.session", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
