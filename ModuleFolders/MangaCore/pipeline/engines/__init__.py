"""Pipeline engine skeleton exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .detect import DetectEngine
    from .inpaint import InpaintEngine
    from .ocr import OcrEngine
    from .render import RenderEngine
    from .translate import TranslateEngine

__all__ = [
    "DetectEngine",
    "InpaintEngine",
    "OcrEngine",
    "RenderEngine",
    "TranslateEngine",
]


def __getattr__(name: str) -> Any:
    if name == "DetectEngine":
        return getattr(import_module(".detect", __name__), name)
    if name == "InpaintEngine":
        return getattr(import_module(".inpaint", __name__), name)
    if name == "OcrEngine":
        return getattr(import_module(".ocr", __name__), name)
    if name == "RenderEngine":
        return getattr(import_module(".render", __name__), name)
    if name == "TranslateEngine":
        return getattr(import_module(".translate", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
