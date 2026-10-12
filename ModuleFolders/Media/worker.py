"""Explicit interpreter worker; stdout carries events and stdin owns lifetime."""

import json
import os
import sys
import threading


def main():
    output = sys.stdout
    lock = threading.Lock()
    def emit(event):
        with lock:
            output.write(json.dumps(event, ensure_ascii=False) + "\n")
            output.flush()
    emit({"type": "status", "message": "worker_started", "pid": os.getpid()})
    data = bytearray()
    while True:
        char = os.read(sys.stdin.fileno(), 1)
        if not char:
            return
        if char == b"\n":
            break
        data.extend(char)
    from ModuleFolders.Media.live_session import LiveConfig, _capture_and_translate
    config = LiveConfig(**json.loads(data))
    stop = threading.Event()
    def parent_gone():
        stop.set()
        if os.name != "nt" and os.getpgrp() == os.getpid():
            import signal
            os.killpg(os.getpgrp(), signal.SIGTERM)
        # EOF means the GUI stopped or died; free audio/CUDA even during imports.
        os._exit(0)
    from ModuleFolders.Media.supervisor import start_core_watchdog
    start_core_watchdog(parent_gone)
    sys.stdout = sys.stderr
    try:
        _capture_and_translate(config, emit, stop)
    except Exception as exc:
        emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        return 1
    finally:
        if os.name != "nt" and os.getpgrp() == os.getpid():
            import signal
            os.killpg(os.getpgrp(), signal.SIGTERM)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
