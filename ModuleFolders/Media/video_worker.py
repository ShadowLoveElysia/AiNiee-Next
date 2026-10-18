"""Isolated file inference worker with a cancellable parent control pipe."""

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
            return 0
        if char == b"\n":
            break
        data.extend(char)
    stop = threading.Event()
    commands = bytearray()

    def receive(chunk):
        commands.extend(chunk)
        while b"\n" in commands:
            line, _, tail = commands.partition(b"\n")
            commands[:] = tail
            try:
                if json.loads(line).get("type") == "cancel":
                    stop.set()
            except (ValueError, AttributeError):
                pass

    def parent_gone():
        stop.set()

        def terminate():
            if os.name != "nt" and os.getpgrp() == os.getpid():
                import signal
                os.killpg(os.getpgrp(), signal.SIGKILL)
            os._exit(0)

        timer = threading.Timer(5, terminate)
        timer.daemon = True
        timer.start()

    from ModuleFolders.Media.supervisor import start_core_watchdog
    start_core_watchdog(parent_gone, on_data=receive)
    sys.stdout = sys.stderr
    from ModuleFolders.Media.video_pipeline import VideoConfig, VideoCancelled, run_video
    try:
        config = VideoConfig(**json.loads(data))
        config.validate()
        run_video(config, emit, stop)
    except VideoCancelled:
        emit({"type": "video_cancelled"})
    except Exception as exc:
        emit({"type": "video_error", "message": f"{type(exc).__name__}: {exc}"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
