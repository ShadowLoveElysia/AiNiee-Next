"""Isolated live-audio session shared by desktop and future output clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import queue
import threading
import time
import uuid
import subprocess
import sys
import json
import os
import signal


def terminate_worker(process, *, force: bool = False) -> None:
    if os.name == "nt":
        process.kill() if force else process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


@dataclass(frozen=True)
class LiveConfig:
    model_root: str
    family: str = "index"
    source_lang: str = "ja"
    target_lang: str = "zh"
    speaker: str = ""
    device: str = "auto"
    asr_device: str = "auto"
    endpoint_silence_ms: int = 450
    target_segment_ms: int = 3000
    max_segment_ms: int = 8000
    context_segments: int = 0
    recognizer: str = "sensevoice"
    asr_endpoint: str = 'http://127.0.0.1:8001/v1'
    application_pid: int = 0
    application_started: str = ""
    application_name: str = ""
    glossary: tuple = ()

    @property
    def translation_dir(self) -> Path:
        from ModuleFolders.Media.model_catalog import get_model
        return Path(self.model_root) / get_model(self.family).directory

    def validate(self) -> None:
        from ModuleFolders.Media.model_catalog import get_model, model_files_present
        get_model(self.family)
        from ModuleFolders.Media.glossary import validate_entries
        validate_entries(self.glossary)
        if self.application_pid:
            from ModuleFolders.Media.windows_audio import validate_target
            validate_target(self.application_pid, self.application_started)
        if self.device not in {"auto", "cuda:0", "vulkan", "cpu", "mlx", "metal", "mps"} or self.asr_device not in {"auto", "cuda:0", "cpu", "mps", "vulkan", "metal"}:
            raise ValueError("Unsupported compute device")
        if self.source_lang not in {"auto", "ja", "en", "ko", "zh", "yue"}:
            raise ValueError("Unsupported recognition language")
        if self.target_lang not in {"zh", "en", "ja", "ko"}:
            raise ValueError("Unsupported translation language")
        if not 0 < self.target_segment_ms <= self.max_segment_ms <= 28000:
            raise ValueError("Invalid segment duration")
        if self.endpoint_silence_ms <= 0:
            raise ValueError("Invalid endpoint duration")
        if self.context_segments not in {0, 1, 2, 3}:
            raise ValueError("Context must contain 0 to 3 segments (0 disables context)")
        root = Path(self.model_root).expanduser()
        from ModuleFolders.Media.asr_catalog import recognition_files_present, get_recognizer
        model = get_recognizer(self.recognizer)
        if model.backend == 'vllm':
            from ModuleFolders.Media.vllm_asr import service_url
            service_url(self.asr_endpoint)
        elif not recognition_files_present(root, self.recognizer):
            raise ValueError(f"Recognition model files are missing: {root / get_recognizer(self.recognizer).directory}")
        if not model_files_present(root, self.family):
            raise ValueError(f"Translation model files are missing or incomplete: {self.translation_dir}")


class LiveSession:
    """The GUI owns this controller; model and capture imports stay in a child."""

    def __init__(self) -> None:
        self._process = None
        self._events = queue.Queue()
        self._stop_deadline = None
        self._startup_deadline = None
        self._worker_started = False
        self.ready = False
        self.config = None
        self._text_request_id = None

    @property
    def active(self) -> bool:
        return self._process is not None

    def start(self, config: LiveConfig, *, interpreter: str | None = None) -> None:
        if self.active:
            raise RuntimeError("A live session is already active")
        config.validate()
        config = LiveConfig(**{**asdict(config), "model_root": str(Path(config.model_root).expanduser().resolve())})
        from ModuleFolders.Media.runtime import subprocess_environment
        self._events = queue.Queue()
        process = subprocess.Popen(
            [interpreter or sys.executable, "-u", "-m", "ModuleFolders.Media.worker"],
            cwd=Path(__file__).resolve().parents[2], env=subprocess_environment(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            start_new_session=os.name != "nt",
        )
        try:
            process.stdin.write(json.dumps(asdict(config)) + "\n")
            process.stdin.flush()
        except Exception:
            terminate_worker(process)
            process.wait(timeout=3)
            raise
        self._process = process
        events = self._events
        def receive():
            try:
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and "type" in event:
                        events.put(event)
            finally:
                process.stdout.close()
        threading.Thread(target=receive, name="media-events", daemon=True).start()
        self._stop_deadline = None
        self._startup_deadline = time.monotonic() + 60
        self._worker_started = False
        self.ready = False
        self.config = config
        self._text_request_id = None

    def _send_command(self, command):
        if not self.active or self._stop_deadline is not None:
            raise RuntimeError("The live model is not running")
        try:
            self._process.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            raise RuntimeError("The live model connection is closed") from None

    def translate_text(self, text, *, source_lang, target_lang, max_characters=0):
        from ModuleFolders.Media.inference_queue import TextTranslationRequest
        if not self.ready or self._text_request_id is not None:
            raise RuntimeError("The live model is not ready or a text request is pending")
        request = TextTranslationRequest(uuid.uuid4().hex, text, source_lang, target_lang, max_characters)
        request.validate()
        self._send_command({"type": "mutual_translate", **asdict(request)})
        self._text_request_id = request.request_id
        return request.request_id

    def cancel_text(self, request_id):
        if request_id != self._text_request_id:
            return
        try:
            self._send_command({"type": "mutual_cancel", "request_id": request_id})
        except RuntimeError:
            pass
        self._text_request_id = None

    def stop(self) -> None:
        self.ready = False
        self._text_request_id = None
        if self.active and self._stop_deadline is None:
            self._process.stdin.close()
            self._stop_deadline = time.monotonic() + 5

    def poll(self) -> list[dict]:
        events = []
        if not self.active:
            return events
        for _ in range(100):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            events.append(event)
            self._worker_started = True
            if event.get("type") == "ready" and self._stop_deadline is None:
                self.ready = True
            elif event.get("type") in {"mutual_result", "mutual_error"}:
                if event.get("request_id") == self._text_request_id:
                    self._text_request_id = None
            elif event.get("type") == "error":
                self.ready = False
        if not self._worker_started and self._stop_deadline is None and time.monotonic() >= self._startup_deadline:
            events.append({"type": "error", "message": "ModelWorkerStartupTimeout"})
            self.stop()
        if self._stop_deadline and time.monotonic() >= self._stop_deadline:
            if self._process.poll() is None:
                terminate_worker(self._process)
        if self._process.poll() is not None:
            code = self._process.returncode
            stopping = self._stop_deadline is not None
            if not self._process.stdin.closed:
                self._process.stdin.close()
            self._process = None
            self.ready = False
            self.config = None
            self._text_request_id = None
            self._stop_deadline = None
            events.append({"type": "stopped", "exit_code": code, "requested": stopping})
        return events

    def close(self) -> None:
        if self.active:
            self.stop()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                terminate_worker(self._process, force=True)
                self._process.wait(timeout=3)
            self._process = None
        self.ready = False
        self.config = None
        self._text_request_id = None


def _capture_and_translate(config: LiveConfig, emit, stop, *, pending=None) -> None:
    emit({"type": "status", "message": "importing_runtime"})
    import numpy as np
    import soundcard as sc
    import torch

    from ModuleFolders.Media.cascade import CascadeProcessor, PcmEndpointDetector
    from ModuleFolders.Media.contracts import AudioSegment
    from ModuleFolders.Media.local_backends import (
        LocalTextTranslator, SenseVoiceRecognizer, SileroSpeechDetector,
    )

    torch.set_num_threads(4)
    emit({"type": "status", "message": "loading_translation"})
    from ModuleFolders.Media.model_catalog import get_model
    checkpoint = get_model(config.family)
    from ModuleFolders.Media.compute import detect_adapters, select_compute, selected_cuda_adapters
    compute = select_compute(config.device, gguf=checkpoint.backend == "gguf",
                             cuda_available=torch.cuda.is_available(), adapters=selected_cuda_adapters(torch, detect_adapters()),
                             mlx_compatible=checkpoint.family == "index", mps_available=torch.backends.mps.is_available())
    device = compute["translation_device"]
    if device == "cuda:0":
        from ModuleFolders.Media.runtime import cuda_execution_check
        cuda_execution_check(torch)
    from ModuleFolders.Media.qwen_asr import recognition_device
    from ModuleFolders.Media.asr_catalog import get_recognizer
    asr_device = (compute['asr_device'] if config.recognizer == 'sensevoice' and config.asr_device == 'auto' else
                  recognition_device(config.asr_device, config.recognizer, torch))
    if get_recognizer(config.recognizer).backend == 'vllm':
        asr_device = 'vllm-service'
    if get_recognizer(config.recognizer).backend == 'gguf':
        from ModuleFolders.Media.gguf_asr import select_asr_compute
        asr_compute = select_asr_compute(config.asr_device, cuda_available=torch.cuda.is_available(),
                                         adapters=selected_cuda_adapters(torch, detect_adapters()))
        asr_device = asr_compute['translation_device']
    if asr_device == 'cuda:0' and device != 'cuda:0':
        from ModuleFolders.Media.runtime import cuda_execution_check
        cuda_execution_check(torch)
    if checkpoint.backend == "gguf":
        from ModuleFolders.Media.gguf_backend import GgufTranslator
        translator = GgufTranslator(config.translation_dir / checkpoint.filename, family=config.family, device=device)
    elif device == "mlx":
        from ModuleFolders.Media.mlx_backend import MlxTextTranslator
        translator = MlxTextTranslator(config.translation_dir, family=config.family)
    else:
        translator = LocalTextTranslator(config.translation_dir, family=config.family, device=device)
    emit({"type": "status", "message": "translation_loaded"})
    from ModuleFolders.Media.glossary import validate_entries
    translator.glossary = tuple(validate_entries(config.glossary))
    if stop.is_set():
        return
    emit({"type": "status", "message": "loading_asr"})
    from ModuleFolders.Media.asr_catalog import get_recognizer
    recognition_model = get_recognizer(config.recognizer)
    if config.recognizer == 'sensevoice':
        recognizer = SenseVoiceRecognizer(Path(config.model_root) / recognition_model.directory, device=asr_device)
    elif recognition_model.backend == 'gguf':
        from ModuleFolders.Media.gguf_asr import GgufSpeechRecognizer
        recognizer = GgufSpeechRecognizer(Path(config.model_root) / recognition_model.directory,
                                         recognizer=config.recognizer, device=asr_device)
    elif recognition_model.backend == 'vllm':
        from ModuleFolders.Media.vllm_asr import VllmSpeechRecognizer
        recognizer = VllmSpeechRecognizer(model=recognition_model.repo, endpoint=config.asr_endpoint)
        asr_device = 'vllm-service'
    torch.set_num_threads(4)
    vad = SileroSpeechDetector()
    if stop.is_set():
        return
    emit({"type": "status", "message": "warming_up"})
    translator.translate("こんにちは。", source_lang="ja", target_lang=config.target_lang, context=())
    recognizer.transcribe(AudioSegment(bytes(16000), 0, 500), language=config.source_lang)
    if stop.is_set():
        return

    current = {"source": "", "started": 0.0, "first_ms": None, "last_sent": 0.0}

    def on_transcript(transcript) -> None:
        current.update(source=transcript.text, started=time.monotonic(), first_ms=None, last_sent=0.0)
        emit({"type": "transcript", "source_text": transcript.text,
              "source_lang": transcript.language})
        emit({"type": "status", "message": "translating"})

    def on_partial(text: str) -> None:
        now = time.monotonic()
        if current["first_ms"] is None:
            current["first_ms"] = round((now - current["started"]) * 1000)
        if now - current["last_sent"] >= 0.06:
            emit({"type": "partial", "source_text": current["source"], "translated_text": text})
            current["last_sent"] = now

    translator.on_partial = on_partial
    processor = CascadeProcessor(
        recognizer, translator, source_lang=config.source_lang, target_lang=config.target_lang,
        session_id=uuid.uuid4().hex, context_segments=config.context_segments,
        context_chars=1600, on_transcript=on_transcript,
    )
    endpoint = PcmEndpointDetector(
        endpoint_silence_ms=config.endpoint_silence_ms, target_segment_ms=config.target_segment_ms,
        max_segment_ms=config.max_segment_ms, pause_silence_ms=192,
    )
    from ModuleFolders.Media.audio_capture import capture_device
    loopback = capture_device(sc, config.speaker, application_pid=config.application_pid,
                              application_started=config.application_started, application_name=config.application_name)
    channels = loopback.channels

    from ModuleFolders.Media.inference_queue import LiveInferenceQueue, TextTranslationRequest, translate_private
    if pending is None:
        pending = LiveInferenceQueue()
    failures = queue.Queue()
    started = time.monotonic()
    dropped = 0

    def infer() -> None:
        try:
            while not stop.is_set():
                try:
                    item = pending.get(timeout=0.1)
                except queue.Empty:
                    continue
                if stop.is_set():
                    break
                if isinstance(item, TextTranslationRequest):
                    translate_private(item, translator, emit)
                    continue
                segment, queued, endpoint_wait_ms = item
                began = time.monotonic()
                emit({"type": "status", "message": "recognizing",
                      "audio_duration_ms": segment.end_ms - segment.start_ms,
                      "queue_wait_ms": round((began - queued) * 1000)})
                event = processor.process(segment)
                if event:
                    payload = asdict(event)
                    payload["type"] = "caption"
                    payload["metadata"].update(
                        recognizer=config.recognizer, asr_device=asr_device,
                        audio_duration_ms=segment.end_ms - segment.start_ms,
                        endpoint_wait_ms=endpoint_wait_ms,
                        queue_depth=pending.qsize(), dropped_segments=dropped,
                        queue_wait_ms=round((began - queued) * 1000),
                        translation_first_text_ms=current["first_ms"],
                        latency_from_segment_end_ms=round((time.monotonic() - started) * 1000 - segment.end_ms),
                    )
                    emit(payload)
        except Exception as exc:
            failures.put(exc)

    worker = threading.Thread(target=infer, name="media-inference", daemon=True)
    try:
        emit({"type": "status", "message": "opening_audio"})
        with loopback.recorder(samplerate=16000, channels=channels) as recorder:
            started = time.monotonic()
            worker.start()
            emit({"type": "ready", "speaker": loopback.name, "audio_backend": getattr(recorder, "backend", "soundcard")})
            frame_count = 0
            capture_ms = vad_ms = 0.0
            frame_samples = 0
            last_telemetry = time.monotonic()
            while not stop.is_set():
                if not failures.empty():
                    raise failures.get()
                capture_began = time.perf_counter()
                samples = recorder.record(numframes=512).mean(axis=1)
                capture_ms += (time.perf_counter() - capture_began) * 1000
                pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
                vad_began = time.perf_counter()
                probability = vad.probability(pcm)
                vad_ms += (time.perf_counter() - vad_began) * 1000
                frame_count += 1
                frame_samples += len(samples)
                audio_position_ms = frame_samples * 1000 // 16000
                for segment in endpoint.push(pcm, probability):
                    endpoint_wait_ms = max(0, audio_position_ms - segment.end_ms)
                    emit({"type": "segment", "start_ms": segment.start_ms, "end_ms": segment.end_ms,
                          "audio_duration_ms": segment.end_ms - segment.start_ms,
                          "endpoint_wait_ms": endpoint_wait_ms, "queue_depth": pending.qsize()})
                    if pending.put_audio((segment, time.monotonic(), endpoint_wait_ms)):
                        dropped += 1
                        emit({"type": "backlog", "dropped_segments": dropped})
                if time.monotonic() - last_telemetry >= 1:
                    emit({"type": "capture", "audio_position_ms": audio_position_ms,
                          "capture_ms": round(capture_ms / frame_count, 2),
                          "vad_ms": round(vad_ms / frame_count, 2),
                          "queue_depth": pending.qsize(), "dropped_segments": dropped})
                    last_telemetry = time.monotonic()
                    frame_count = 0
                    capture_ms = vad_ms = 0.0
    finally:
        stop.set()
        if worker.ident is not None:
            worker.join(timeout=2)
        if hasattr(translator, "close"):
            translator.close()
        if hasattr(recognizer, 'close'):
            recognizer.close()
