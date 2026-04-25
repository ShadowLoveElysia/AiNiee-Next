"""Common type aliases used by MangaCore."""

from __future__ import annotations

from typing import Any, Literal

BBox = tuple[int, int, int, int]
JsonDict = dict[str, Any]
PageStatus = Literal["idle", "prepared", "translated", "edited", "failed", "needs_review"]
ProjectStatus = Literal["editable", "running", "failed", "completed"]
