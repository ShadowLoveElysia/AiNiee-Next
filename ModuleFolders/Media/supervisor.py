"""A modal TUI session; EOF on the control pipe couples the desktop to its core."""

import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_managed_desktop(arguments=(), *, interpreter=None) -> int:
    process = subprocess.Popen(
        [interpreter or sys.executable, "-m", "ModuleFolders.Media", "--managed", *arguments],
        cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def start_core_watchdog(on_core_exit) -> None:
    import threading

    def watch():
        # Parent death closes its only write handle, including abnormal termination.
        try:
            while sys.stdin.buffer.read(1):
                pass
        except (OSError, ValueError):
            pass
        on_core_exit()

    threading.Thread(target=watch, name="media-core-watch", daemon=True).start()
