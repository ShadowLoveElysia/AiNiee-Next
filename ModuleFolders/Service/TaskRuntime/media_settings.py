"""Media preferences and catalogs shared with the existing desktop/TUI."""
from dataclasses import asdict

from ModuleFolders.Infrastructure.ApiSecurity import (
    contains_redacted_secret, restore_redacted_secrets,
    sanitize_data_for_mcp,
)
from ModuleFolders.Media import preferences as settings


def preferences() -> dict:
    for _ in range(3):
        revision = settings.preferences_revision()
        values = settings.read_preferences(settings.SETTINGS_PATH)
        if revision == settings.preferences_revision():
            break
    else:
        raise settings.PreferenceConflict("Media settings changed while reading")
    schema = {}
    for key, value in {**settings.DEFAULTS, "model_root": settings.default_model_root()}.items():
        kind = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "object" if isinstance(value, dict) else "string"
        schema[key] = {"type": kind}
        if key in settings.CHOICES:
            schema[key]["enum"] = list(settings.CHOICES[key])
        if key in settings.RANGES:
            schema[key].update(minimum=settings.RANGES[key][0], maximum=settings.RANGES[key][1])
    schema["cache_ram_mib"].update(minimum=0, maximum=settings.max_cache_ram_mib())
    return {"values": sanitize_data_for_mcp(values, path="/api/media/settings"),
            "revision": revision, "schema": schema}


def validate_changes(changes, current):
    from ModuleFolders.Media.glossary import validate_profiles
    from ModuleFolders.Media.vllm_asr import service_url

    allowed = set(settings.DEFAULTS) | {"model_root"}
    if set(changes) - allowed:
        raise ValueError("Unknown media preference")
    values = restore_redacted_secrets(changes, current)
    if contains_redacted_secret(values):
        raise ValueError("Cannot use an unresolved secret placeholder")
    normalized = {}
    for key, value in values.items():
        if key == "glossary_profiles":
            normalized[key] = validate_profiles(value)
        elif key == "glossary_profile":
            if not isinstance(value, str):
                raise ValueError("Invalid glossary profile")
            normalized[key] = value
        elif key == "runtime_python" and value == "":
            normalized[key] = value
        elif key == "asr_endpoint":
            normalized[key] = service_url(value)
        else:
            normalized[key] = settings.validate_preference(key, value)
    merged = {**current, **normalized}
    if merged["glossary_profile"] and merged["glossary_profile"] not in merged["glossary_profiles"]:
        raise ValueError("Selected glossary profile does not exist")
    return normalized


def update_preferences(changes, expected_revision):
    from .manager import TaskManager
    from .media import MediaConflict
    from .activities import auxiliary_active
    manager = TaskManager()
    with manager._lock:
        if auxiliary_active():
            raise MediaConflict("Stop media processing before changing its settings")
        current = settings.read_preferences(settings.SETTINGS_PATH)
        values = validate_changes(changes, current)
        revision = settings.save_preferences(values, settings.SETTINGS_PATH, expected_revision=expected_revision)
        return {"success": True, "revision": revision}


def model_catalog():
    from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS, model_files_present
    from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS, recognition_files_present
    data = settings.read_preferences(settings.SETTINGS_PATH)
    root = data["model_root"]
    return {"model_root": root,
            "translation": [{**asdict(row), "directory": row.directory, "present": model_files_present(root, row.key)} for row in TRANSLATION_MODELS],
            "recognition": [{**asdict(row), "directory": row.directory, "present": recognition_files_present(root, row.key)} for row in RECOGNITION_MODELS]}


def runtime_status():
    from ModuleFolders.Media.runtime import runtime_python, selected_python
    from ModuleFolders.Media.video_pipeline import _configured_tool, VIDEO_EXTENSIONS
    from ModuleFolders.Media.windows_audio import supported
    data = settings.read_preferences(settings.SETTINGS_PATH)
    return {"python": selected_python(data["runtime_python"]), "managed_python": str(runtime_python()),
            "managed_installed": runtime_python().is_file(), "ffmpeg": _configured_tool("ffmpeg"),
            "ffprobe": _configured_tool("ffprobe"), "application_audio_supported": supported(),
            "video_extensions": list(VIDEO_EXTENSIONS), "probe_required": True}
