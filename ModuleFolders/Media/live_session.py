"""Isolated live-audio session shared by desktop and future output clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import multiprocessing
from pathlib import Path
import queue
import threading
import time
import uuid


@dataclass(frozen=True)
class LiveConfig:
    model_root: str
    family: str = "index"
    source_lang: str = "ja"
    target_lang: str = "zh"
    speaker: str = ""
    device: str = "cuda:0"
    asr_device: str = "cuda:0"
    endpoint_silence_ms: int = 450
    target_segment_ms: int = 3000
    max_segment_ms: int = 8000

    @property
    def translation_dir(self) -> Path:
        name = "Index-Translate-2B" if self.family == "index" else "Hy-MT2-1.8B"
        return Path(self.model_root) / name

    def validate(self) -> None:
        if self.family not in {"index", "hymt"}:
            raise ValueError("Unsupported translation model")
        if self.source_lang not in {"auto", "ja", "en", "ko", "zh", "yue"}:
            raise ValueError("Unsupported recognition language")
        if self.target_lang not in {"zh", "en", "ja", "ko"}:
            raise ValueError("Unsupported translation language")
        if not 0 < self.target_segment_ms <= self.max_segment_ms <= 28000:
            raise ValueError("Invalid segment duration")
        if self.endpoint_silence_ms <= 0:
            raise ValueError("Invalid endpoint duration")
        root = Path(self.model_root).expanduser()
        required = [root / "SenseVoiceSmall/model.pt", root / "SenseVoiceSmall/config.yaml",
                    self.translation_dir / "config.json", self.translation_dir / "tokenizer_config.json"]
        for path in required:
            if not path.is_file():
                raise ValueError(f"Model file is missing: {path}")
        if not any(self.translation_dir.glob("*.safetensors")):
            raise ValueError(f"Translation weights are missing: {self.translation_dir}")


class LiveSession:
    """The GUI owns this controller; model and capture imports stay in a child."""

    def __init__(self) -> None:
        self._context = multiprocessing.get_context("spawn")
        self._process = None
        self._receiver = None
        self._stop = None
        self._stop_deadline = None

    @property
    def active(self) -> bool:
        return self._process is not None

    def start(self, config: LiveConfig) -> None:
        if self.active:
            raise RuntimeError("A live session is already active")
        config.validate()
        config = LiveConfig(**{**asdict(config), "model_root": str(Path(config.model_root).expanduser().resolve())})
        receiver, sender = self._context.Pipe(duplex=False)
        stop = self._context.Event()
        process = self._context.Process(
            target=_run_worker, args=(config, sender, stop), name="AiNiee-Live", daemon=True,
        )
        try:
            process.start()
        except Exception:
            receiver.close()
            sender.close()
            raise
        sender.close()
        self._receiver, self._stop, self._process = receiver, stop, process
        self._stop_deadline = None

    def stop(self) -> None:
        if self.active and self._stop_deadline is None:
            self._stop.set()
            self._stop_deadline = time.monotonic() + 5

    def poll(self) -> list[dict]:
        events = []
        if not self.active:
            return events
        try:
            for _ in range(100):
                if not self._receiver.poll():
                    break
                events.append(self._receiver.recv())
        except (EOFError, OSError):
            pass
        if self._stop_deadline and time.monotonic() >= self._stop_deadline:
            if self._process.is_alive():
                self._process.terminate()
        if not self._process.is_alive():
            code = self._process.exitcode
            stopping = self._stop_deadline is not None
            self._process.join(timeout=0)
            self._process.close()
            self._receiver.close()
            self._process = self._receiver = self._stop = None
            self._stop_deadline = None
            events.append({"type": "stopped", "exit_code": code, "requested": stopping})
        return events

    def close(self) -> None:
        if self.active:
            self._stop.set()
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1)
            self._receiver.close()
            self._process.close()
            self._process = self._receiver = self._stop = None


def _run_worker(config: LiveConfig, sender, stop) -> None:
    send_lock = threading.Lock()

    def emit(payload: dict) -> None:
        with send_lock:
            sender.send(payload)

    try:
        _capture_and_translate(config, emit, stop)
    except Exception as exc:
        if not stop.is_set():
            emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        sender.close()


def _capture_and_translate(config: LiveConfig, emit, stop) -> None:
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
    translator = LocalTextTranslator(config.translation_dir, family=config.family, device=config.device)
    if stop.is_set():
        return
    emit({"type": "status", "message": "loading_asr"})
    recognizer = SenseVoiceRecognizer(Path(config.model_root) / "SenseVoiceSmall", device=config.asr_device)
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
        emit({"type": "transcript", "source_text": transcript.text})

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
        session_id=uuid.uuid4().hex, context_segments=1, context_chars=600, on_transcript=on_transcript,
    )
    endpoint = PcmEndpointDetector(
        endpoint_silence_ms=config.endpoint_silence_ms, target_segment_ms=config.target_segment_ms,
        max_segment_ms=config.max_segment_ms, pause_silence_ms=192,
    )
    speakers = sc.all_speakers()
    speaker = next((s for s in speakers if s.name == config.speaker), None) if config.speaker else sc.default_speaker()
    if speaker is None:
        raise RuntimeError("Selected audio output device is unavailable")
    loopback = sc.get_microphone(id=speaker.id, include_loopback=True)
    channels = loopback.channels
    if channels < 2:
        raise RuntimeError("Select a stereo audio output; WASAPI mono capture is unreliable")

    pending = queue.Queue(maxsize=4)
    failures = queue.Queue()
    started = time.monotonic()
    dropped = 0

    def infer() -> None:
        try:
            while not stop.is_set():
                try:
                    segment, queued = pending.get(timeout=0.1)
                except queue.Empty:
                    continue
                if stop.is_set():
                    break
                began = time.monotonic()
                event = processor.process(segment)
                if event:
                    payload = asdict(event)
                    payload["type"] = "caption"
                    payload["metadata"].update(
                        queue_wait_ms=round((began - queued) * 1000),
                        translation_first_text_ms=current["first_ms"],
                        latency_from_segment_end_ms=round((time.monotonic() - started) * 1000 - segment.end_ms),
                    )
                    emit(payload)
        except Exception as exc:
            failures.put(exc)

    worker = threading.Thread(target=infer, name="media-inference", daemon=True)
    try:
        with loopback.recorder(samplerate=16000, channels=channels) as recorder:
            started = time.monotonic()
            worker.start()
            emit({"type": "ready", "speaker": speaker.name})
            while not stop.is_set():
                if not failures.empty():
                    raise failures.get()
                samples = recorder.record(numframes=512).mean(axis=1)
                pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
                for segment in endpoint.push(pcm, vad.probability(pcm)):
                    try:
                        pending.put_nowait((segment, time.monotonic()))
                    except queue.Full:
                        try:
                            pending.get_nowait()
                        except queue.Empty:
                            pass
                        else:
                            dropped += 1
                            emit({"type": "backlog", "dropped_segments": dropped})
                        pending.put_nowait((segment, time.monotonic()))
    finally:
        stop.set()
        if worker.ident is not None:
            worker.join(timeout=2)
