"""Shared project preferences for TUI and desktop live translation."""

import json
import os
from pathlib import Path
import re
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = PROJECT_ROOT / "Resource/media_overlay.json"
DEFAULTS = {
    "opacity": 88, "font_size": 26, "font_family": "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI", "font_bold": True,
    "translation_color": "#ffffff", "source_color": "#c8d4e5", "background_color": "#101827",
    "stroke_width": 2, "stroke_color": "#000000", "show_source": True, "topmost": True,
    "locked": False, "width": 900, "height": 240, "family": "index", "source": "ja",
    "target": "zh", "device": "auto", "runtime_python": "",
    "package_source": "nju",
    "recognizer": "sensevoice", "recognition_device": "auto",
    "asr_endpoint": "http://127.0.0.1:8001/v1",
    "context_segments": 0, "recording": False,
    "record_directory": str(PROJECT_ROOT / "Resource/MediaRecords"),
    "glossary_profiles": {}, "glossary_profile": "", "chat_character_limit": 0,
}
RANGES = {"opacity": (0, 100), "font_size": (16, 48), "stroke_width": (0, 6),
          "width": (360, 2400), "height": (120, 1000),
          "context_segments": (0, 3), "chat_character_limit": (0, 1000)}
from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS
from ModuleFolders.Media.compute import device_choices, model_device_choices
from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS

CHOICES = {"family": tuple(model.key for model in TRANSLATION_MODELS), "source": ("auto", "ja", "en", "ko", "zh", "yue"),
           "target": ("zh", "en", "ja", "ko"), "device": device_choices(), "package_source": ("nju", "official"),
           "recognizer": tuple(model.key for model in RECOGNITION_MODELS),
           "recognition_device": ("auto", "cpu", "mps", "metal") if sys.platform == 'darwin' else ("auto", "cpu", "cuda:0", "vulkan")}


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
    data.pop("history_segments", None)
    from ModuleFolders.Media.glossary import validate_profiles
    try:
        data["glossary_profiles"] = validate_profiles(data.get("glossary_profiles", {}))
    except ValueError:
        data["glossary_profiles"] = {}
    if data.get("glossary_profile") not in data["glossary_profiles"]:
        data["glossary_profile"] = ""
    try:
        data["chat_character_limit"] = validate_preference("chat_character_limit", data.get("chat_character_limit", 0))
    except (ValueError, TypeError):
        data["chat_character_limit"] = 0
    if data.get("package_source") not in CHOICES["package_source"]:
        data["package_source"] = DEFAULTS["package_source"]
    for key in ('recognizer', 'recognition_device'):
        if data.get(key) not in CHOICES[key]:
            data[key] = DEFAULTS[key]
    try:
        from ModuleFolders.Media.gguf_asr import asr_device_choices
        if data['recognition_device'] not in asr_device_choices(data['recognizer']):
            data['recognition_device'] = 'auto'
    except (ImportError, ModuleNotFoundError):
        pass
    if data.get("device") not in device_choices():
        data["device"] = "auto"
    try:
        if data["device"] not in model_device_choices(data.get("family", "index")):
            data["device"] = "auto"
    except ValueError:
        pass
    if sys.platform == "darwin":
        if data.get("font_family") in {"Microsoft YaHei UI", "Segoe UI"}:
            data["font_family"] = "PingFang SC"
        if re.match(r"^[A-Za-z]:[\\/]", str(data.get("model_root", ""))):
            data["model_root"] = default_model_root()
        if re.match(r"^[A-Za-z]:[\\/]", str(data.get("record_directory", ""))):
            data["record_directory"] = DEFAULTS["record_directory"]
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
    data.pop("history_segments", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
