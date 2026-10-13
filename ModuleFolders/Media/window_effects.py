"""Native window input policy for independent subtitle and background layers."""

import os
import sys


def set_rounded_corners(window, radius: int = 18) -> None:
    if sys.platform == "darwin":
        from ModuleFolders.Media.macos_window import set_rounded_corners as cocoa_round
        cocoa_round(window, radius)
        return
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    width, height = window.winfo_width(), window.winfo_height()
    if width <= 1 or height <= 1:
        return
    size = (width, height, radius)
    if getattr(window, "_rounded_size", None) == size:
        return
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, 2 * radius, 2 * radius)
    if not region:
        raise ctypes.WinError(ctypes.get_last_error())
    hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
    # SetWindowRgn transfers region ownership to Windows only on success.
    if not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)
        raise ctypes.WinError(ctypes.get_last_error())
    window._rounded_size = size


def set_mouse_passthrough(window, enabled: bool) -> None:
    if sys.platform == "darwin":
        from ModuleFolders.Media.macos_window import configure_window
        configure_window(window, passthrough=enabled)
        return
    if os.name != "nt":
        if enabled:
            raise RuntimeError("Mouse passthrough is currently supported on Windows only")
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    getter = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
    setter = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
    getter.argtypes = [wintypes.HWND, ctypes.c_int]
    getter.restype = ctypes.c_ssize_t
    setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    setter.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    hwnds = {user32.GetParent(window.winfo_id()) or window.winfo_id()}
    for hwnd in hwnds:
        style = getter(hwnd, -20)
        flags = 0x20 | 0x08000000  # WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        style = (style | flags | 0x80000) if enabled else (style & ~flags)
        ctypes.set_last_error(0)
        previous = setter(hwnd, -20, style)
        if not previous and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020):
            raise ctypes.WinError(ctypes.get_last_error())
