"""Windows process-tree capture with explicit identity and no system fallback."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from ModuleFolders.Media.macos_audio import NativeRecorder

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("native") / "ProcessAudio.cs"
HELPER_ROOT = ROOT / "Resource/MediaRuntime/native-audio/windows"


def supported():
    return sys.platform == "win32" and sys.getwindowsversion().build >= 20348 and platform.machine().lower() in {"amd64", "x86_64"}


def prepare_helper():
    if not supported():
        raise RuntimeError("Application audio capture requires 64-bit Windows build 20348 or newer")
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    directory = HELPER_ROOT / digest[:16]
    executable = directory / "ProcessAudio.exe"
    if executable.is_file():
        return executable
    compiler = Path(os.environ.get("WINDIR", "C:/Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        raise RuntimeError("Windows .NET Framework C# compiler is unavailable")
    directory.mkdir(parents=True, exist_ok=True)
    from ModuleFolders.Media.runtime import subprocess_environment
    result = subprocess.run([str(compiler), "/nologo", "/optimize+", "/platform:x64", "/target:exe",
                             "/out:" + str(executable), str(SOURCE)],
                            cwd=ROOT, env=subprocess_environment(), capture_output=True, timeout=30)
    if result.returncode or not executable.is_file():
        raise RuntimeError("Application audio capture helper compilation failed")
    return executable


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
        raise RuntimeError("Application audio list failed")
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

    def error_message(self):
        detail = "; ".join(self.errors) or "process audio disconnected"
        return "Application audio capture stopped (" + detail + "). Reselect the running application and restart capture."
