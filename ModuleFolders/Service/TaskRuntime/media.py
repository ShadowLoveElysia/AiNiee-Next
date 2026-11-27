"""API-owned media sessions using the existing isolated live/video workers."""
from dataclasses import asdict, fields, replace
from pathlib import Path
import threading
import time
import uuid

from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
from ModuleFolders.Infrastructure.SensitiveData import sanitize_sensitive_data
from ModuleFolders.Media import preferences as settings
from ModuleFolders.Media.live_session import LiveConfig, LiveSession
from ModuleFolders.Media.session_history import SessionHistory
from ModuleFolders.Media.video_pipeline import VideoConfig, VideoSession
from .activities import register_activity
from .events import SequencedBuffer
from .media_settings import preferences, update_preferences, model_catalog, runtime_status
from .media_runtime import runtime_action, runtime_job


class MediaConflict(RuntimeError):
    pass


class MediaNotFound(ValueError):
    pass


def _session_config(mode, options):
    from ModuleFolders.Media.runtime import selected_python
    from ModuleFolders.Media.glossary import validate_entries
    from ModuleFolders.Media.vllm_asr import service_url
    from .manager import resolve_task_worker_python
    from ModuleFolders.Infrastructure.ApiSecurity import contains_redacted_secret, restore_redacted_secrets

    saved = settings.read_preferences(settings.SETTINGS_PATH)
    if mode not in {"live", "video"}:
        raise ValueError("Unknown media session mode")
    config_type = VideoConfig if mode == "video" else LiveConfig
    allowed = {item.name for item in fields(config_type)} | {"recording", "record_directory", "glossary_profile"}
    allowed.discard("asr_interpreter")
    if set(options) - allowed:
        raise ValueError("Unknown media session option")
    values = {"model_root": saved["model_root"], "family": saved["family"],
              "source_lang": saved["source"], "target_lang": saved["target"], "device": saved["device"],
              "asr_device": saved["recognition_device"], "recognizer": saved["recognizer"],
              "asr_endpoint": saved["asr_endpoint"], "context_segments": saved["context_segments"],
              "cache_ram_mib": saved["cache_ram_mib"]}
    if mode == "video":
        values.update(family=saved["video_translation_family"], recognizer=saved["video_recognizer"],
                      subtitle_mode=saved["video_subtitle_mode"], asr_mode=saved["video_asr_mode"],
                      translation_mode=saved["video_translation_mode"], video_encoder=saved["video_encoder"],
                      **{key: saved[key] for key in ("cloud_asr_endpoint", "cloud_asr_model", "cloud_asr_api_key")})
    for key, value in options.items():
        if key not in {"recording", "record_directory", "glossary_profile"}:
            values[key] = value
    profile = options.get("glossary_profile", saved["glossary_profile"])
    if profile and profile not in saved["glossary_profiles"]:
        raise ValueError("Unknown glossary profile")
    values["glossary"] = tuple(validate_entries(values.get("glossary", saved["glossary_profiles"].get(profile, []))))
    service_url(values["asr_endpoint"])
    interpreter = selected_python(saved["runtime_python"])
    config = config_type(**values)
    if mode == "video":
        values = restore_redacted_secrets(values, saved)
        if contains_redacted_secret(values):
            raise ValueError("Cannot use an unresolved secret placeholder")
        config = config_type(**values)
    if mode == "video" and config.translation_mode == "cloud":
        if config.asr_mode == "local":
            config = replace(config, asr_interpreter=interpreter)
        interpreter = resolve_task_worker_python(str(settings.PROJECT_ROOT))
    config.validate()
    recording = options.get("recording", saved["recording"])
    if type(recording) is not bool:
        raise ValueError("Recording must be boolean")
    directory = options.get("record_directory", saved["record_directory"])
    settings.validate_preference("record_directory", directory)
    return config, interpreter, recording, directory


class MediaController:
    def __init__(self):
        self._lock = threading.RLock()
        self._session = None
        self._history = SessionHistory()
        self._events = SequencedBuffer(512, lock=self._lock)
        self._state = {"session_id": None, "mode": None, "status": "idle", "running": False,
                       "ready": False, "result": None, "error": None}
        self._secrets = ()

    def active(self):
        return self._session is not None and self._session.active

    def _check_identity(self, session_id):
        if not session_id or session_id != self._state["session_id"]:
            raise MediaNotFound("Media session was not found or has been replaced")

    def start(self, mode, options, confirmed=False):
        from .manager import TaskManager
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        if not confirmed:
            raise PermissionError("Confirm media processing before starting the session")
        manager = TaskManager()
        with manager._lock, self._lock:
            if manager.task_conflict_detail() or self.active() or QueueManager(read_only=True).is_running:
                raise MediaConflict("Another task or media operation is active")
            config, interpreter, recording, directory = _session_config(mode, options)
            session = (VideoSession if mode == "video" else LiveSession)(own_process_tree=True)
            self._history.close()
            self._history = SessionHistory()
            self._events.clear()
            self._secrets = tuple(value for key, value in asdict(config).items() if key.endswith("api_key") and value)
            self._state = {"session_id": uuid.uuid4().hex, "mode": mode, "status": "starting", "running": True,
                           "ready": False, "result": None, "error": None}
            self._session = session
            try:
                session.start(config, interpreter=interpreter)
                if recording:
                    self._history.begin_recording(directory)
            except Exception:
                try:
                    session.close()
                finally:
                    self._state.update(status="stopping" if session.active else "failed", running=session.active,
                                       error={"code": "MEDIA_START_FAILED", "message": "Media session could not start"})
                raise
            thread = threading.Thread(target=self._monitor, args=(session,), daemon=True, name="api-media-session")
            thread.start()
            return self.status()

    def _safe_event(self, event):
        value = sanitize_sensitive_data(event)
        def clean(item):
            if isinstance(item, str):
                for secret in self._secrets:
                    item = item.replace(secret, "[redacted]")
                return item
            if isinstance(item, list):
                return [clean(child) for child in item]
            if isinstance(item, dict):
                return {key: clean(child) for key, child in item.items()}
            return item
        value = clean(value)
        if value.get("type") in {"video_error", "error"}:
            value["message"] = "Media worker failed; inspect the local runtime diagnostics"
        elif value.get("type") == "video_log":
            value["message"] = safe_installer_line(value.get("message", ""))
        return value

    def _monitor(self, session):
        while True:
            with self._lock:
                if self._session is not session:
                    return
                try:
                    for event in session.poll():
                        self._accept_event(event)
                except Exception:
                    self._state.update(status="stopping", error={"code": "MEDIA_POLL_FAILED", "message": "Media event processing failed"})
                    try:
                        session.close()
                    except Exception:
                        pass
                self._state["ready"] = session.ready
                self._state["running"] = session.active
                if not session.active:
                    self._history.end_recording()
                    if self._state["status"] not in {"completed", "failed", "stopped"}:
                        self._state["status"] = "failed" if self._state["error"] else "stopped"
                    self._secrets = ()
                    return
            time.sleep(.05)

    def _accept_event(self, event):
        safe = self._safe_event(event)
        self._events.append(safe)
        self._history.accept(safe)
        kind = event.get("type")
        if kind == "ready":
            self._state["status"] = "running"
        elif kind == "video_complete":
            self._state.update(status="completed", result=safe)
        elif kind in {"video_error", "error"}:
            self._state.update(status="failed", error={"code": "MEDIA_WORKER_FAILED", "message": safe["message"]})
        elif kind == "video_cancelled":
            self._state["status"] = "stopping"
        elif kind == "stopped" and self._state["status"] not in {"completed", "failed"}:
            requested = event.get("requested") or self._state["status"] == "stopping"
            self._state["status"] = "stopped" if requested or self._state["mode"] == "live" else "failed"

    def status(self, session_id=None, cursor=0):
        with self._lock:
            if session_id:
                self._check_identity(session_id)
            rows, cursor, reset = self._events.snapshot(cursor)
            return {**self._state, "events": rows, "cursor": cursor, "cursor_reset": reset,
                    "recording": self._history.recording, "record_path": str(self._history.record_path) if self._history.record_path else None}

    def stop(self, session_id):
        with self._lock:
            self._check_identity(session_id)
            if self.active():
                self._state["status"] = "stopping"
                self._session.stop()
            return self.status()

    def close(self):
        with self._lock:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    self._state.update(status="stopping", running=True)
                    return False
            self._state.update(status="stopped", running=False, ready=False)
            self._history.end_recording()
            self._secrets = ()
            return True

    def history(self, session_id, start=0, limit=100):
        with self._lock:
            self._check_identity(session_id)
            return {"session_id": session_id, "generation": self._history.generation, "total": self._history.count,
                    "start": start, "items": self._history.read_page(start, min(limit, 1000))}

    def diagnostics(self, session_id=None, cursor=0):
        from ModuleFolders.Media.diagnostics import diagnostic_event
        with self._lock:
            state = self.status(session_id, cursor)
            rows = []
            for event in state["events"]:
                diagnostic = diagnostic_event(event)
                if diagnostic is not None:
                    rows.append({**diagnostic, "seq": event["seq"]})
            return {"session_id": state["session_id"], "mode": state["mode"], "status": state["status"],
                    "running": state["running"], "ready": state["ready"], "events": rows,
                    "cursor": state["cursor"], "cursor_reset": state["cursor_reset"]}

    def clear_history(self, session_id):
        with self._lock:
            self._check_identity(session_id)
            self._history.clear()
            return {"success": True, "generation": self._history.generation}

    def recording(self, session_id, enabled, directory=None):
        with self._lock:
            self._check_identity(session_id)
            if enabled:
                if not self.active():
                    raise MediaConflict("Media session is not active")
                directory = directory or settings.read_preferences(settings.SETTINGS_PATH)["record_directory"]
                self._history.begin_recording(directory)
            else:
                self._history.end_recording()
            return self.status()

    def translate_text(self, session_id, text, source_lang, target_lang, max_characters=0):
        with self._lock:
            self._check_identity(session_id)
            if self._state["mode"] != "live" or not self.active():
                raise MediaConflict("A live session is required")
            try:
                request_id = self._session.translate_text(text, source_lang=source_lang, target_lang=target_lang, max_characters=max_characters)
            except RuntimeError as exc:
                raise MediaConflict("Live model is not ready or has a pending text request") from exc
            return {"session_id": session_id, "request_id": request_id}

    def cancel_text(self, session_id, request_id):
        with self._lock:
            self._check_identity(session_id)
            if self._session is not None:
                self._session.cancel_text(request_id)
            return {"success": True}

    def output_file(self, session_id, artifact):
        with self._lock:
            self._check_identity(session_id)
            if artifact == "record":
                path = self._history.record_path
                if self._history.recording:
                    raise MediaConflict("Stop recording before downloading its file")
            elif artifact in {"video", "source_srt", "translated_srt"}:
                path = (self._state["result"] or {}).get(artifact)
            else:
                raise MediaNotFound("Unknown media artifact")
            if not path or not Path(path).is_file() or Path(path).is_symlink():
                raise MediaNotFound("Media artifact is not available")
            return Path(path)


_controller = MediaController()
register_activity("media", _controller.active, _controller.close)


def get_media_controller():
    return _controller
