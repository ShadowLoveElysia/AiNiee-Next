"""Shared constants for the MangaCore subsystem."""

from __future__ import annotations

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PROJECT_DIR_NAME = "mangaProject"
FINAL_DIR_NAME = "final"
LOGS_DIR_NAME = "logs"
THUMBNAIL_SIZE = (240, 360)

PAGE_STATUS_IDLE = "idle"
PAGE_STATUS_PREPARED = "prepared"
PAGE_STATUS_EDITED = "edited"
PROJECT_STATUS_EDITABLE = "editable"

DEFAULT_LAYER_PATHS = {
    "source": "source.png",
    "overlay_text": "overlayText.json",
    "inpainted": "inpainted.png",
    "rendered": "rendered.png",
}

DEFAULT_MASK_PATHS = {
    "segment": "segmentMask.png",
    "bubble": "bubbleMask.png",
    "brush": "brushMask.png",
    "restore": "restoreMask.png",
}

DEFAULT_TEXT_STYLE = {
    "font_family": "Source Han Sans SC",
    "font_size": 42,
    "line_spacing": 1.2,
    "fill": "#111111",
    "stroke_color": "#ffffff",
    "stroke_width": 0,
}
