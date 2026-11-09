"""Isolated local-ASR subprocess used by cloud-translation video jobs."""

import json
import sys
import threading
from pathlib import Path


def main():
    line = sys.stdin.readline()
    if not line:
        return 1
    from ModuleFolders.Media.video_pipeline import VideoConfig, recognize_wav
    from ModuleFolders.Media.video_backends import compute_devices, load_recognizer
    from ModuleFolders.Media.local_backends import SileroSpeechDetector

    config = VideoConfig(**json.loads(line))
    stop = threading.Event()

    def emit_progress(stage, completed=0, total=0, *, detail=None):
        payload = {"type": "progress", "stage": stage, "completed": completed, "total": total}
        if detail:
            payload["detail"] = detail
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    try:
        devices = compute_devices(config)
        recognizer = load_recognizer(config, devices[1])
        detector = SileroSpeechDetector()
        try:
            cues = recognize_wav(config.input_path, recognizer, detector, config, stop, emit_progress)
        finally:
            if hasattr(recognizer, "close"):
                recognizer.close()
        print(json.dumps({"type": "result", "cues": [cue.__dict__ for cue in cues]}, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
