"""A modal TUI session; EOF on the control pipe couples the desktop to its core."""

import os
from pathlib import Path
import subprocess
import sys
import json
import queue
import threading
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_managed_desktop(arguments=(), *, interpreter=None) -> int:
    if not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from ModuleFolders.Media.runtime import subprocess_environment
    # Keep GUI dependencies in the core environment; inference selects its own Python.
    interpreter = interpreter or sys.executable
    if any(argument in {"-h", "--help"} for argument in arguments):
        return subprocess.call([interpreter or sys.executable, "-m", "ModuleFolders.Media", *arguments], cwd=PROJECT_ROOT)
    process = subprocess.Popen(
        [interpreter or sys.executable, "-m", "ModuleFolders.Media", "--managed", *arguments],
        cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=None,
        text=True, encoding="utf-8", errors="replace",
        env=subprocess_environment(),
    )
    from ModuleFolders.Media.diagnostics import PREFIX, DiagnosticState
    from ModuleFolders.UserInterface.AppI18N import initialize_i18n
    from rich.console import Console
    from rich.live import Live
    _, locale = initialize_i18n(str(PROJECT_ROOT))
    updates = queue.Queue(maxsize=256)
    state = DiagnosticState()
    def read_events():
        try:
            for line in process.stdout:
                if not line.startswith(PREFIX):
                    continue
                try:
                    event = json.loads(line[len(PREFIX):])
                except ValueError:
                    continue
                try:
                    updates.put_nowait(event)
                except queue.Full:
                    try:
                        updates.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        updates.put_nowait(event)
                    except queue.Full:
                        pass
        finally:
            process.stdout.close()
    reader = threading.Thread(target=read_events, name="media-tui-diagnostics", daemon=True)
    reader.start()
    try:
        # No TUI prompts run until the desktop process has exited.
        console = Console()
        with Live(state.render(locale.get, width=console.width), console=console, refresh_per_second=4, transient=False,
                  auto_refresh=False) as display:
            while True:
                while True:
                    try:
                        state.accept(updates.get_nowait())
                    except queue.Empty:
                        break
                display.update(state.render(locale.get, width=console.width), refresh=True)
                code = process.poll()
                if code is not None:
                    reader.join(timeout=.5)
                    while True:
                        try:
                            state.accept(updates.get_nowait())
                        except queue.Empty:
                            break
                    display.update(state.render(locale.get, width=console.width), refresh=True)
                    return code
                time.sleep(.25)
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


def start_core_watchdog(on_core_exit, *, on_data=None) -> None:
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
                    data = os.read(sys.stdin.fileno(), min(available.value, 4096))
                    if on_data is not None:
                        on_data(data)
                time.sleep(.1)
            on_core_exit()
            return
        try:
            # Raw OS reads avoid holding BufferedReader's lock during shutdown.
            while data := os.read(sys.stdin.fileno(), 4096):
                if on_data is not None:
                    on_data(data)
        except (OSError, ValueError):
            pass
        on_core_exit()

    threading.Thread(target=watch, name="media-core-watch", daemon=True).start()
