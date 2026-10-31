"""Windows process-tree capture with explicit identity and no system fallback."""

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading

from ModuleFolders.Media.macos_audio import NativeRecorder

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("native") / "ProcessAudio.cs"
HELPER_ROOT = ROOT / "Resource/MediaRuntime/native-audio/windows"
_HELPER_LOCK = threading.Lock()


def _compact_detail(value, limit=1200):
    text = " ".join(str(value or "").split())
    return text[-limit:]


def _format_hresult(status):
    try:
        value = int(status)
    except (TypeError, ValueError):
        return str(status)
    unsigned = value & 0xFFFFFFFF
    known = {
        0x80004005: "Unspecified failure",
        0x80070005: "Access denied",
        0x80070057: "Invalid argument",
        0x80070490: "Element not found",
        0x8007007E: "Required module not found",
        0x8001010E: "Wrong COM apartment/thread",
        0x88890004: "Audio device invalidated",
        0x88890008: "Unsupported audio format",
        0x8889000A: "Audio service not running",
    }
    detail = known.get(unsigned, "")
    if not detail and sys.platform == "win32":
        try:
            detail = _compact_detail(ctypes.FormatError(unsigned), 240)
        except (AttributeError, OSError, ValueError):
            detail = ""
    suffix = f" ({detail})" if detail else ""
    return f"0x{unsigned:08X}{suffix}"


def format_native_diagnostic(payload):
    stage = str(payload.get("stage", "capture"))
    status = payload.get("status")
    if status is None:
        return stage
    return f"{stage}: HRESULT {_format_hresult(status)}"


def supported():
    return sys.platform == "win32" and sys.getwindowsversion().build >= 20348 and platform.machine().lower() in {"amd64", "x86_64"}


def prepare_helper():
    if not supported():
        raise RuntimeError("Application audio capture requires 64-bit Windows build 20348 or newer")
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    directory = HELPER_ROOT / digest[:16]
    executable = directory / "ProcessAudio.exe"
    with _HELPER_LOCK:
        if executable.is_file():
            return executable
        compiler = Path(os.environ.get("WINDIR", "C:/Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        if not compiler.is_file():
            raise RuntimeError("Windows .NET Framework csc.exe is unavailable")
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Application audio helper directory is not writable: {_compact_detail(exc)}") from None
        temporary = directory / f"ProcessAudio.{os.getpid()}.tmp.exe"
        try:
            from ModuleFolders.Media.runtime import subprocess_environment
            result = subprocess.run([str(compiler), "/nologo", "/optimize+", "/platform:x64", "/target:exe",
                                     "/out:" + str(temporary), str(SOURCE)],
                                    cwd=ROOT, env=subprocess_environment(), capture_output=True, timeout=30)
            stderr = _compact_detail(result.stderr.decode("utf-8", errors="replace")
                                     if isinstance(result.stderr, bytes) else result.stderr)
            if result.returncode or not temporary.is_file():
                detail = f": {stderr}" if stderr else ""
                raise RuntimeError("Application audio helper compilation failed" + detail)
            os.replace(temporary, executable)
            return executable
        except subprocess.TimeoutExpired:
            raise RuntimeError("Application audio helper compilation timed out after 30 seconds") from None
        except OSError as exc:
            raise RuntimeError(f"Application audio helper could not be created: {_compact_detail(exc)}") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


@dataclass(frozen=True)
class AudioApplication:
    pid: int
    name: str
    started: str

    @property
    def selection(self):
        return f"{self.name} (PID {self.pid})"


def applications():
    from ModuleFolders.Media.runtime import subprocess_environment
    executable = prepare_helper()
    result = subprocess.run([str(executable), "list"], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8-sig", errors="replace", timeout=10,
                            env=subprocess_environment(), stdin=subprocess.DEVNULL)
    if result.returncode:
        detail = _compact_detail(result.stderr.decode("utf-8", errors="replace")
                                 if isinstance(result.stderr, bytes) else result.stderr)
        raise RuntimeError("Application audio list failed" + (f": {detail}" if detail else ""))
    try:
        rows = json.loads(result.stdout)
        return sorted([AudioApplication(**row) for row in rows], key=lambda app: (app.name.casefold(), app.pid))
    except (ValueError, TypeError):
        raise RuntimeError("Invalid application audio list") from None


def validate_target(pid, started):
    if not supported():
        raise RuntimeError("Application audio capture requires 64-bit Windows build 20348 or newer")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or not isinstance(started, str) or not started.isdigit():
        raise ValueError("Select an application before starting capture")


def _target_started(pid):
    if sys.platform != "win32":
        raise RuntimeError("Application audio capture requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = ctypes.c_int
    handle = kernel.OpenProcess(0x1000, 0, pid)
    if not handle:
        raise RuntimeError("Selected application is no longer running or is not queryable")
    values = [wintypes.FILETIME() for _ in range(4)]
    try:
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
            raise RuntimeError("Selected application creation time could not be read")
    finally:
        kernel.CloseHandle(handle)
    created = values[0].dwLowDateTime + (values[0].dwHighDateTime << 32)
    return str(created + 504911232000000000)


def preflight_application(pid, started):
    """Compile the bridge and verify the selected process before model startup."""
    validate_target(pid, started)
    if not SOURCE.is_file():
        raise RuntimeError(f"Application audio helper source is missing: {SOURCE}")
    try:
        actual = _target_started(pid)
    except RuntimeError:
        raise
    except (AttributeError, OSError) as exc:
        raise RuntimeError(f"Selected application identity check failed: {_compact_detail(exc)}") from None
    if actual != started:
        raise RuntimeError("Selected application has restarted; refresh the list and select it again")
    return prepare_helper()


class WindowsApplicationAudio:
    channels = 1

    def __init__(self, pid, started, name=""):
        validate_target(pid, started)
        self.pid, self.started = pid, started
        self.name = f"{name or 'Application'} (PID {pid})"

    def recorder(self, *, samplerate, channels):
        if samplerate != 16000 or channels != 1:
            raise ValueError("Application capture produces 16 kHz mono PCM")
        return ProcessRecorder(self.pid, self.started)


class ProcessRecorder(NativeRecorder):
    def __init__(self, pid, started):
        super().__init__()
        self.pid, self.started = pid, started

    def _launch(self):
        from ModuleFolders.Media.runtime import subprocess_environment
        return subprocess.Popen([str(prepare_helper()), str(self.pid), self.started],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=ROOT, env=subprocess_environment(), bufsize=0)

    def initialization_timeout_message(self):
        return "Application audio initialization timed out; reselect the application and retry"

    def format_diagnostic(self, payload):
        return format_native_diagnostic(payload)

    def error_message(self):
        self.wait_for_diagnostics()
        if self.process is not None and self.process.poll() is not None:
            self.process_exit_code = self.process.returncode
        detail = "; ".join(self.errors) or str(self.failure or "process audio disconnected")
        exit_code = ""
        if self.process_exit_code not in (None, 0):
            exit_code = f"; helper exit {self.process_exit_code}"
        return ("Application audio capture stopped (" + detail + exit_code +
                "). Reselect the running application and restart capture.")
