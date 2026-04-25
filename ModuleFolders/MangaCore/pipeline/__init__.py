"""Pipeline entrypoints for MangaCore."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .progress import JobRegistry, PipelineJob
    from .runnerBatch import MangaBatchRunResult, MangaBatchRunner
    from .runnerPage import MangaPageRunner

__all__ = [
    "JobRegistry",
    "MangaBatchRunResult",
    "MangaBatchRunner",
    "MangaPageRunner",
    "PipelineJob",
]


def __getattr__(name: str) -> Any:
    if name in {"JobRegistry", "PipelineJob"}:
        return getattr(import_module(".progress", __name__), name)
    if name in {"MangaBatchRunResult", "MangaBatchRunner"}:
        return getattr(import_module(".runnerBatch", __name__), name)
    if name == "MangaPageRunner":
        return getattr(import_module(".runnerPage", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
