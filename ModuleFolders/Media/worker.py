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
    from ModuleFolders.Media.inference_queue import LiveInferenceQueue, TextTranslationRequest
    pending = LiveInferenceQueue()
    commands = bytearray()
    def receive_commands(chunk):
        commands.extend(chunk)
        while b"\n" in commands:
            line, _, tail = commands.partition(b"\n")
            commands[:] = tail
            request_id = ""
            try:
                command = json.loads(line)
                request_id = command.get("request_id", "")
                if not isinstance(request_id, str) or len(request_id) > 64:
                    request_id = ""
                if command.get("type") == "mutual_translate":
                    pending.put_text(TextTranslationRequest(
                        request_id, command.get("text"), command.get("source_lang"), command.get("target_lang"),
                        command.get("max_characters", 0),
                    ))
                elif command.get("type") == "mutual_cancel":
                    pending.cancel_text(request_id)
            except Exception:
                emit({"type": "mutual_error", "request_id": request_id, "code": "request_rejected"})
        if len(commands) > 16384:
            commands.clear()
    def parent_gone():
        stop.set()
        if os.name != "nt" and os.getpgrp() == os.getpid():
            import signal
            os.killpg(os.getpgrp(), signal.SIGTERM)
        # EOF means the GUI stopped or died; free audio/CUDA even during imports.
        os._exit(0)
    from ModuleFolders.Media.supervisor import start_core_watchdog
    start_core_watchdog(parent_gone, on_data=receive_commands)
    sys.stdout = sys.stderr
    try:
        _capture_and_translate(config, emit, stop, pending=pending)
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
