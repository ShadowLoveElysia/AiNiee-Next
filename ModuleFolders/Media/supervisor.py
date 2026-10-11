"""A modal TUI session; EOF on the control pipe couples the desktop to its core."""

import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_managed_desktop(arguments=(), *, interpreter=None) -> int:
    from ModuleFolders.Media.runtime import subprocess_environment, selected_python
    from ModuleFolders.Media.preferences import read_preferences
    interpreter = interpreter or selected_python(read_preferences().get("runtime_python", ""))
    if any(argument in {"-h", "--help"} for argument in arguments):
        return subprocess.call([interpreter or sys.executable, "-m", "ModuleFolders.Media", *arguments], cwd=PROJECT_ROOT)
    process = subprocess.Popen(
        [interpreter or sys.executable, "-m", "ModuleFolders.Media", "--managed", *arguments],
        cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=subprocess_environment(),
    )
    try:
        # No TUI prompts run until the desktop process has exited.
        while True:
            try:
                return process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=7)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)
        # Keystrokes entered while the TUI was suspended must not select a menu.
        if os.name == "nt":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        elif sys.stdin.isatty():
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)


def start_core_watchdog(on_core_exit) -> None:
    import threading

    def watch():
        # Parent death closes its only write handle, including abnormal termination.
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            import time
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                             wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPDWORD]
            kernel.PeekNamedPipe.restype = wintypes.BOOL
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
            available = wintypes.DWORD()
            while True:
                if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                    break
                if available.value:
                    # A blocking CRT read can deadlock native DLL imports on Windows.
                    os.read(sys.stdin.fileno(), available.value)
                time.sleep(.1)
            on_core_exit()
            return
        try:
            # Raw OS reads avoid holding BufferedReader's lock during shutdown.
            while os.read(sys.stdin.fileno(), 1):
                pass
        except (OSError, ValueError):
            pass
        on_core_exit()

    threading.Thread(target=watch, name="media-core-watch", daemon=True).start()
