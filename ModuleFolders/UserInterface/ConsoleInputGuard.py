from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class _ConsoleModeSnapshot:
    handle: int
    mode: int


@contextlib.contextmanager
def suppress_console_mouse_input() -> Iterator[None]:
    snapshot = _disable_windows_console_mouse_input()
    try:
        yield
    finally:
        _restore_windows_console_mode(snapshot)


def _disable_windows_console_mouse_input() -> _ConsoleModeSnapshot | None:
    if sys.platform != "win32":
        return None

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetConsoleMode.restype = wintypes.BOOL

    std_input_handle = -10
    invalid_handle_value = ctypes.c_void_p(-1).value
    handle = kernel32.GetStdHandle(std_input_handle)
    if handle in (None, 0, invalid_handle_value):
        return None

    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return None

    original_mode = int(mode.value)
    enable_mouse_input = 0x0010
    enable_quick_edit_mode = 0x0040
    enable_extended_flags = 0x0080
    guarded_mode = (original_mode | enable_extended_flags) & ~enable_mouse_input & ~enable_quick_edit_mode
    if guarded_mode == original_mode:
        return None

    if not kernel32.SetConsoleMode(handle, guarded_mode):
        return None
    return _ConsoleModeSnapshot(handle=int(handle), mode=original_mode)


def _restore_windows_console_mode(snapshot: _ConsoleModeSnapshot | None) -> None:
    if snapshot is None or sys.platform != "win32":
        return

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return

    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetConsoleMode.restype = wintypes.BOOL
    kernel32.SetConsoleMode(wintypes.HANDLE(snapshot.handle), wintypes.DWORD(snapshot.mode))
