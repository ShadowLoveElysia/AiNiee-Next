"""Cancellable media setup reusing the existing runtime command implementation."""
from collections import OrderedDict
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
from ModuleFolders.Infrastructure.SensitiveData import sanitize_sensitive_data
from ModuleFolders.Media import preferences as settings
from ModuleFolders.Media.runtime import AUDIO_PROBE_TIMEOUT, RUNTIME_PROBE_TIMEOUT, selected_python, subprocess_environment
from .events import SequencedBuffer
from .processes import OwnedProcessTree, launch_options, mark_worker_environment

_lock = threading.RLock()
_events = OrderedDict()
_ACTIONS = {"probe", "devices", "applications", "install", "configure", "download", "ffmpeg"}


def _command(action, options):
    from ModuleFolders.Media.model_catalog import get_model
    from ModuleFolders.Media.asr_catalog import get_recognizer
    from ModuleFolders.Media.vllm_asr import service_url

    saved = settings.read_preferences(settings.SETTINGS_PATH)
    allowed = {"device", "family", "recognizer", "asr_device", "asr_endpoint", "model_root", "download_scope", "package_source"}
    if set(options) - allowed:
        raise ValueError("Unknown runtime option")
    data = {"device": saved["device"], "family": saved["family"], "recognizer": saved["recognizer"],
            "asr_device": saved["recognition_device"], "asr_endpoint": saved["asr_endpoint"],
            "model_root": saved["model_root"], "download_scope": "all", "package_source": saved["package_source"], **options}
    data["family"] = get_model(data["family"]).key
    data["recognizer"] = get_recognizer(data["recognizer"]).key
    settings.validate_preference("device", data["device"])
    settings.validate_preference("recognition_device", data["asr_device"])
    settings.validate_preference("package_source", data["package_source"])
    service_url(data["asr_endpoint"])
    if data["download_scope"] not in {"all", "asr", "llm"}:
        raise ValueError("Unknown download scope")
    interpreter = selected_python(saved["runtime_python"])
    if action in {"applications", "ffmpeg"}:
        args = [sys.executable, "-u", "-m", "ModuleFolders.Media.api_runtime", action]
    else:
        interpreter = sys.executable if action in {"install", "configure"} else interpreter
        args = [interpreter, "-u", "-m", "ModuleFolders.Media.runtime", action,
                "--device", data["device"], "--family", data["family"],
                "--recognizer", data["recognizer"], "--asr-device", data["asr_device"],
                "--asr-endpoint", data["asr_endpoint"]]
        if action == "download":
            args += ["--model-root", str(Path(data["model_root"]).expanduser().resolve()),
                     "--download-scope", data["download_scope"]]
    environment = subprocess_environment()
    environment.update(AINIEE_MEDIA_PACKAGE_SOURCE=data["package_source"], AINIEE_DOWNLOAD_JSON="1", UV_NO_PROGRESS="false")
    if action in {"install", "configure", "download"}:
        environment.pop("HF_HUB_OFFLINE", None)
        environment.pop("TRANSFORMERS_OFFLINE", None)
    return args, environment


def _execute(action, args, environment, events, cancel):
    from .jobs import CancelledJob

    marker = mark_worker_environment(environment, nested=True)
    started = time.time()
    process = subprocess.Popen(args, cwd=settings.PROJECT_ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               text=True, encoding="utf-8", errors="replace", **launch_options())
    tree = OwnedProcessTree(process, owner_id=marker, launched_at=started)
    result = {}
    output_error = []
    def read_output():
        nonlocal result
        try:
            with process.stdout:
                for line in process.stdout:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        message = safe_installer_line(line)
                        if message:
                            events.append({"type": "log", "message": message})
                        continue
                    if isinstance(row, dict):
                        row = sanitize_sensitive_data(row)
                        events.append(row)
                        result = row
        except Exception:
            output_error.append(True)
    reader = threading.Thread(target=read_output, daemon=True, name="api-media-setup-output")
    reader.start()
    timeout = RUNTIME_PROBE_TIMEOUT if action == "probe" else AUDIO_PROBE_TIMEOUT if action == "devices" else 6 * 3600
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while process.poll() is None:
            if cancel.wait(.1) or time.monotonic() >= deadline:
                timed_out = not cancel.is_set()
                break
    finally:
        # Keep the job active while cancellation has not cleaned its own tree.
        while not tree.terminate(timeout=2):
            time.sleep(.2)
        reader.join()
    if cancel.is_set():
        raise CancelledJob()
    if timed_out:
        raise TimeoutError("Media operation timed out")
    if process.returncode or output_error:
        raise RuntimeError("Media runtime operation failed")
    if action == "probe":
        result["ready"] = not result.get("missing") and not result.get("compute_error")
    return result


def runtime_action(action, options, confirmed=False):
    from .jobs import get_job_manager
    if action not in _ACTIONS:
        raise ValueError("Unknown media runtime action")
    if action in {"install", "configure", "download", "ffmpeg", "applications"} and not confirmed:
        raise PermissionError("Confirm this runtime preparation before starting it")
    args, environment = _command(action, options)
    events = SequencedBuffer(256)
    job = get_job_manager().start("media_runtime", lambda cancel: _execute(action, args, environment, events, cancel),
                                  metadata={"action": action})
    with _lock:
        _events[job["job_id"]] = events
        while len(_events) > 100:
            _events.popitem(last=False)
    return job


def runtime_job(job_id, cursor=0):
    from .jobs import get_job_manager
    state = get_job_manager().status(job_id)
    if state["kind"] != "media_runtime":
        raise KeyError("Unknown media runtime job")
    with _lock:
        events = _events.get(job_id)
    rows, cursor, reset = events.snapshot(cursor) if events is not None else ([], 0, True)
    return {**state, "events": rows, "cursor": cursor, "cursor_reset": reset}
