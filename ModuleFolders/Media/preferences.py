"""Shared project preferences for TUI and desktop live translation."""

import json
import os
from pathlib import Path
import re
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = PROJECT_ROOT / "Resource/media_overlay.json"
DEFAULTS = {
    "opacity": 88, "font_size": 26, "font_family": "Microsoft YaHei UI", "font_bold": True,
    "translation_color": "#ffffff", "source_color": "#c8d4e5", "background_color": "#101827",
    "stroke_width": 2, "stroke_color": "#000000", "show_source": True, "topmost": True,
    "locked": False, "width": 900, "height": 240, "family": "index", "source": "ja",
    "target": "zh", "device": "cuda:0", "runtime_python": "",
    "context_segments": 0, "history_segments": 3, "recording": False,
    "record_directory": str(PROJECT_ROOT / "Resource/MediaRecords"),
}
RANGES = {"opacity": (0, 100), "font_size": (16, 48), "stroke_width": (0, 6),
          "width": (360, 2400), "height": (120, 1000),
          "context_segments": (0, 3), "history_segments": (2, 3)}
from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS

CHOICES = {"family": tuple(model.key for model in TRANSLATION_MODELS), "source": ("auto", "ja", "en", "ko", "zh", "yue"),
           "target": ("zh", "en", "ja", "ko"), "device": ("cuda:0", "cpu")}


def default_model_root() -> str:
    if os.environ.get("AINIEE_MEDIA_MODEL_ROOT"):
        return os.environ["AINIEE_MEDIA_MODEL_ROOT"]
    ssd = Path("G:/AiNiee-Models")
    return str(ssd if os.name == "nt" and ssd.is_dir() else PROJECT_ROOT / "tmp/models")


def read_preferences(path=SETTINGS_PATH) -> dict:
    data = {**DEFAULTS, "model_root": default_model_root()}
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            data.update(saved)
    except (OSError, ValueError):
        pass
    return data


def validate_preference(key: str, value):
    if key in RANGES:
        value = int(value)
        low, high = RANGES[key]
        if not low <= value <= high:
            raise ValueError(f"{low}–{high}")
    elif key in CHOICES:
        if value not in CHOICES[key]:
            raise ValueError(" / ".join(CHOICES[key]))
    elif key.endswith("color"):
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("#RRGGBB")
    elif key in DEFAULTS and isinstance(DEFAULTS[key], bool):
        if not isinstance(value, bool):
            raise ValueError("bool")
    elif not isinstance(value, str) or not value.strip():
        raise ValueError("empty")
    return value


def save_preferences(changes: dict, path=SETTINGS_PATH) -> None:
    path = Path(path)
    data = read_preferences(path)
    data.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
