"""Small Cocoa bridge for Tk subtitle windows; called only on the GUI thread."""

import ctypes
from functools import lru_cache


@lru_cache(maxsize=1)
def _objc():
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    library = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    library.objc_getClass.argtypes = [ctypes.c_char_p]
    library.objc_getClass.restype = ctypes.c_void_p
    library.sel_registerName.argtypes = [ctypes.c_char_p]
    library.sel_registerName.restype = ctypes.c_void_p
    return library


def _send(receiver, selector, result=ctypes.c_void_p, arguments=(), values=()):
    library = _objc()
    signature = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *arguments)
    call = signature(("objc_msgSend", library))
    return call(receiver, library.sel_registerName(selector.encode("ascii")), *values)


def native_window(window):
    app = _send(_objc().objc_getClass(b"NSApplication"), "sharedApplication")
    windows = _send(app, "windows")
    count = _send(windows, "count", ctypes.c_ulong)
    for index in range(count):
        candidate = _send(windows, "objectAtIndex:", arguments=(ctypes.c_ulong,), values=(index,))
        title = _send(_send(candidate, "title"), "UTF8String", ctypes.c_char_p)
        if title and title.decode("utf-8") == window.title():
            return candidate
    raise RuntimeError("macOS subtitle window is not available")


def configure_window(window, *, passthrough: bool) -> None:
    native = native_window(window)
    _send(native, "setIgnoresMouseEvents:", None, (ctypes.c_bool,), (passthrough,))
    _send(native, "setHasShadow:", None, (ctypes.c_bool,), (False,))
    # Join Spaces and allow the floating subtitle beside full-screen apps.
    behavior = _send(native, "collectionBehavior", ctypes.c_ulong)
    _send(native, "setCollectionBehavior:", None, (ctypes.c_ulong,), (behavior | 1 | 256,))
