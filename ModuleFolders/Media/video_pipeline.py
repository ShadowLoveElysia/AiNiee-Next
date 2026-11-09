"""Offline video → denoised speech → timed SRT → translated video pipeline."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import wave
import zipfile
from contextlib import contextmanager

from ModuleFolders.Media.live_session import LiveConfig, LiveSession

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".mts", ".m2ts", ".wmv", ".flv")


class VideoCancelled(Exception):
    pass


@dataclass(frozen=True)
class VideoConfig(LiveConfig):
    input_path: str = ""
    output_directory: str = ""
    subtitle_mode: str = ""
    glossary_mode: str = "temporary"
    asr_mode: str = "local"
    translation_mode: str = "local"
    video_encoder: str = "auto"
    asr_interpreter: str = ""
    cloud_asr_endpoint: str = ""
    cloud_asr_model: str = ""
    cloud_asr_api_key: str = field(default="", repr=False)

    def validate(self):
        if self.glossary_mode not in {"temporary", "manual"}:
            raise ValueError("Choose automatic temporary terms or a manual glossary")
        if self.glossary_mode == "manual" and not self.glossary:
            raise ValueError("Select a non-empty manual glossary for this video")
        if self.asr_mode not in {"local", "cloud"}:
            raise ValueError("Choose local or cloud ASR")
        if self.translation_mode not in {"local", "cloud"}:
            raise ValueError("Choose local or cloud translation")
        if self.video_encoder not in {"auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"}:
            raise ValueError("Choose a supported video encoder")
        if self.asr_mode == "cloud":
            from ModuleFolders.Media.cloud_asr import validate_cloud_settings
            validate_cloud_settings(self.cloud_asr_endpoint, self.cloud_asr_model, self.cloud_asr_api_key)
        LiveConfig.validate(
            replace(self, glossary=() if self.glossary_mode == "temporary" else self.glossary),
            require_recognition=self.asr_mode == "local" and not self.asr_interpreter,
            require_translation=self.translation_mode == "local",
        )
        validate_video_input(self.input_path, self.subtitle_mode)
        if not self.output_directory.strip():
            raise ValueError("Select an output directory")
        if self.application_pid:
            raise ValueError("File translation cannot capture application audio")


class VideoSession(LiveSession):
    worker_module = "ModuleFolders.Media.video_worker"
    worker_creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    capture_worker_stderr = True

    def start(self, config, *, interpreter=None):
        if self.active:
            raise RuntimeError("A video session is already active")
        from ModuleFolders.Media.video_process import ProcessJob
        job = ProcessJob()
        try:
            super().start(config, interpreter=interpreter)
            job.attach(self._process)
        except Exception:
            self.close()
            job.close()
            raise
        self._job = job

    def poll(self):
        events = super().poll()
        if not self.active:
            self._close_job()
        return events

    def _close_job(self):
        job = getattr(self, "_job", None)
        if job is not None:
            job.close()
            self._job = None

    def close(self):
        try:
            super().close()
        finally:
            self._close_job()

    def stop(self):
        if self.active and self._stop_deadline is None:
            try:
                self._send_command({"type": "cancel"})
            except RuntimeError:
                pass
            self._stop_deadline = time.monotonic() + 5


@dataclass(frozen=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str
    language: str = "auto"


_ASR_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|]*\|>|</?asr_text>", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?。！？…]+[」』）》）】〉》\"'”’]*$")
_TRAILING_SUBTITLE_PUNCTUATION = frozenset(
    " \\t.,!?;:，。！？；：、…~～"
)


def normalize_subtitle_text(text, *, strip_terminal_punctuation=True):
    """Flatten model line breaks and remove sentence-final subtitle clutter."""
    value = _ASR_SPECIAL_TOKEN_RE.sub(" ", str(text or ""))
    value = " ".join(value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").split())
    if strip_terminal_punctuation:
        while value and value[-1] in _TRAILING_SUBTITLE_PUNCTUATION:
            value = value[:-1].rstrip()
    return value
    value = ""
    for line in (line for line in cleaned if line):
        value = _join_plain_text(value, line)
    return value


def _has_sentence_ending(text):
    value = normalize_subtitle_text(text, strip_terminal_punctuation=False)
    return bool(_SENTENCE_END_RE.search(value) or re.search(r"[.!?。！？…]+\s", value))


def _join_plain_text(left, right):
    if not left:
        return right
    if left[-1].isascii() and right[0].isascii() and left[-1].isalnum() and right[0].isalnum():
        return left + " " + right
    return left + right


def _join_subtitle_text(left, right):
    left = normalize_subtitle_text(left, strip_terminal_punctuation=False)
    right = normalize_subtitle_text(right, strip_terminal_punctuation=False)
    if not left:
        return right
    if not right:
        return left
    return _join_plain_text(left, right)


def merge_subtitle_cues(cues, *, max_gap_ms=900, max_duration_ms=12000, max_chars=120):
    """Join VAD fragments that belong to one sentence before writing SRT."""
    merged = []
    pending = None
    for cue in cues:
        text = normalize_subtitle_text(cue.text, strip_terminal_punctuation=False)
        if not text:
            continue
        current = SubtitleCue(cue.start_ms, cue.end_ms, text, cue.language)
        if pending is not None:
            gap = current.start_ms - pending.end_ms
            combined = _join_subtitle_text(pending.text, current.text)
            should_merge = (
                -100 <= gap <= max_gap_ms
                and current.end_ms - pending.start_ms <= max_duration_ms
                and len(combined) <= max_chars
                and not _has_sentence_ending(pending.text)
            )
            if should_merge:
                language = pending.language if pending.language != "auto" else current.language
                pending = SubtitleCue(pending.start_ms, max(pending.end_ms, current.end_ms), combined, language)
                continue
            merged.append(pending)
        pending = current
    if pending is not None:
        merged.append(pending)
    return [
        replace(cue, text=normalize_subtitle_text(cue.text))
        for cue in merged
        if normalize_subtitle_text(cue.text)
    ]


def _prepare_video_cues(cues):
    """Apply the same cue cleanup before terminology and translation stages."""
    return merge_subtitle_cues(cues)


def validate_video_input(path, mode):
    if mode not in {"soft", "hard"}:
        raise ValueError("Choose switchable subtitles or burned-in subtitles")
    source = Path(path).expanduser()
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("Select a supported video file")


FFMPEG_DOWNLOAD_URLS = {
    # Keep the project default on a China-accessible GitHub proxy. The official
    # Gyan archive remains a fallback because proxy availability can vary.
    "win32": (
        "https://gh-proxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    ),
}
_TOOL_PROGRESS = None


@contextmanager
def tool_progress(callback):
    """Temporarily receive automatic media-tool preparation progress."""
    global _TOOL_PROGRESS
    previous = _TOOL_PROGRESS
    _TOOL_PROGRESS = callback
    try:
        yield
    finally:
        _TOOL_PROGRESS = previous


def _report_tool_progress(stage, completed=0, total=0):
    callback = _TOOL_PROGRESS
    if callback is not None:
        callback(stage, completed, total)


def _configured_tool(name):
    configured = os.environ.get("AINIEE_" + name.upper(), "")
    candidates = [configured] if configured else []
    executable = name + (".exe" if os.name == "nt" else "")
    candidates += [str(PROJECT_ROOT / "Resource/MediaRuntime/ffmpeg/bin" / executable),
                   str(PROJECT_ROOT / "Resource/MediaRuntime/ffmpeg" / executable),
                   shutil.which(name) or ""]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


def _safe_extract_ffmpeg_zip(archive: Path, destination: Path) -> None:
    _report_tool_progress("extracting", 0, 1)
    with zipfile.ZipFile(archive) as source:
        selected = {}
        for member in source.infolist():
            normalized = member.filename.replace("\\", "/")
            if member.is_dir() or "/bin/" not in normalized:
                continue
            basename = Path(normalized).name.lower()
            if basename in {"ffmpeg.exe", "ffprobe.exe"}:
                selected[basename] = member
        if set(selected) != {"ffmpeg.exe", "ffprobe.exe"}:
            raise RuntimeError("Downloaded FFmpeg archive does not contain ffmpeg.exe and ffprobe.exe")
        destination.mkdir(parents=True, exist_ok=True)
        for basename, member in selected.items():
            target = (destination / basename).resolve()
            if target.parent != destination.resolve():
                raise RuntimeError("Invalid FFmpeg archive path")
            with source.open(member) as reader, target.open("wb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
    _report_tool_progress("extracting", 1, 1)


def _download_ffmpeg_windows() -> None:
    root = PROJECT_ROOT / "Resource/MediaRuntime/ffmpeg/bin"
    archive = PROJECT_ROOT / "tmp/ffmpeg-release-essentials.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    urls = FFMPEG_DOWNLOAD_URLS["win32"]
    failures = []
    for index, url in enumerate(urls, 1):
        source_name = "China mirror" if index == 1 else "official fallback"
        _report_tool_progress(f"connecting ({source_name})", 0, 0)
        request = urllib.request.Request(url, headers={"User-Agent": "AiNiee-Next media runtime"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                total = int(response.headers.get("Content-Length", "0") or 0) or int(getattr(response, "length", 0) or 0)
                if total > 250 * 1024 * 1024:
                    raise RuntimeError("FFmpeg download is unexpectedly large")
                downloaded = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > 250 * 1024 * 1024:
                        raise RuntimeError("FFmpeg download is unexpectedly large")
                    output.write(block)
                    _report_tool_progress(f"downloading ({source_name})", downloaded, total)
            _safe_extract_ffmpeg_zip(archive, root)
            return
        except Exception as exc:
            failures.append(f"{source_name}: {exc}")
            archive.unlink(missing_ok=True)
            _report_tool_progress(f"failed ({source_name})", 0, 0)
    detail = " | ".join(failures)
    raise RuntimeError(f"Automatic FFmpeg download failed ({detail}). Set AINIEE_FFMPEG and AINIEE_FFPROBE to local executables.") from None


def ensure_tools() -> tuple[str, str]:
    ffmpeg = _configured_tool("ffmpeg")
    ffprobe = _configured_tool("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    if os.environ.get("AINIEE_FFMPEG") or os.environ.get("AINIEE_FFPROBE"):
        missing = "ffmpeg" if not ffmpeg else "ffprobe"
        raise FileNotFoundError(f"Configured {missing} executable was not found")
    if os.name != "nt":
        raise FileNotFoundError("FFmpeg is not installed. Automatic download is currently supported on Windows; install ffmpeg and ffprobe or set AINIEE_FFMPEG/AINIEE_FFPROBE.")
    _download_ffmpeg_windows()
    ffmpeg, ffprobe = _configured_tool("ffmpeg"), _configured_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FileNotFoundError("FFmpeg download completed without both ffmpeg.exe and ffprobe.exe")
    return ffmpeg, ffprobe


def find_tool(name):
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError("Unsupported media tool")
    tools = ensure_tools()
    return tools[0 if name == "ffmpeg" else 1]


def _check_cancel(stop):
    if stop.is_set():
        raise VideoCancelled()


def run_tool(arguments, stop, *, cwd=None, heartbeat=None, heartbeat_interval=1.0):
    _check_cancel(stop)
    process = subprocess.Popen(arguments, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    last_heartbeat = time.monotonic()
    try:
        while True:
            try:
                output, error = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                _check_cancel(stop)
                now = time.monotonic()
                if heartbeat is not None and now - last_heartbeat >= heartbeat_interval:
                    heartbeat(now - last_heartbeat)
                    last_heartbeat = now
        _check_cancel(stop)
        if process.returncode:
            detail = error.decode("utf-8", errors="replace")[-1800:]
            raise RuntimeError(f"{Path(arguments[0]).name} exited with {process.returncode}: {detail}")
        return output
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def _timestamp(milliseconds):
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def write_srt(path, cues):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        for index, cue in enumerate(cues, 1):
            if cue.start_ms < 0 or cue.end_ms <= cue.start_ms or not cue.text.strip():
                raise ValueError("Invalid subtitle cue")
            text = normalize_subtitle_text(cue.text)
            if not text:
                raise ValueError("Invalid subtitle cue text")
            stream.write(f"{index}\n{_timestamp(cue.start_ms)} --> {_timestamp(cue.end_ms)}\n{text}\n\n")


def recognize_wav(path, recognizer, detector, config, stop, progress):
    from ModuleFolders.Media.cascade import PcmEndpointDetector
    # Offline recognition can wait for a natural pause. The live defaults are
    # intentionally shorter for latency and tend to split one subtitle sentence.
    endpoint = PcmEndpointDetector(
        endpoint_silence_ms=max(config.endpoint_silence_ms, 650),
        target_segment_ms=0,
        max_segment_ms=max(config.max_segment_ms, 12000),
        pause_silence_ms=192,
    )
    cues = []

    def transcribe(segment):
        _check_cancel(stop)
        transcript = recognizer.transcribe(segment, language=config.source_lang)
        _check_cancel(stop)
        if transcript.text.strip():
            cues.append(SubtitleCue(segment.start_ms, segment.end_ms, transcript.text.strip(), transcript.language))
            progress("recognizing", segment.end_ms * 16, 0,
                     detail=f"ASR 已识别第 {len(cues)} 段，时间 {segment.start_ms}–{segment.end_ms} ms")

    with wave.open(str(path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise ValueError("Expected 16 kHz mono s16le WAV")
        total = audio.getnframes()
        position = 0
        last_report = 0
        while frame := audio.readframes(512):
            _check_cancel(stop)
            position += len(frame) // 2
            # Silero needs a full frame; the endpoint timeline uses actual samples.
            probability = detector.probability(frame.ljust(1024, b"\0"))
            for segment in endpoint.push(frame, probability):
                transcribe(segment)
            if position - last_report >= 16000 or position == total:
                progress("recognizing", position, total)
                last_report = position
        for segment in endpoint.flush():
            transcribe(segment)
    if not cues:
        raise RuntimeError("No speech was recognized in the video")
    return _prepare_video_cues(cues)


def recognize_wav_isolated(path, config, interpreter, stop, progress):
    """Run local ASR in the media runtime while the parent keeps cloud SDKs native."""
    payload = asdict(config)
    payload["input_path"] = str(path)
    payload["output_directory"] = str(Path(path).parent)
    payload["subtitle_mode"] = "soft"
    payload["translation_mode"] = "cloud"
    payload["asr_mode"] = "local"
    process = subprocess.Popen(
        [interpreter, "-u", "-m", "ModuleFolders.Media.video_asr_worker"],
        cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    process.stdin.flush()
    process.stdin.close()
    events = deque()
    reader_done = threading.Event()

    def receive():
        try:
            for line in process.stdout:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        finally:
            reader_done.set()

    reader = threading.Thread(target=receive, name="video-asr-events", daemon=True)
    reader.start()
    try:
        while process.poll() is None or not reader_done.is_set() or events:
            if stop.is_set():
                process.kill()
                raise VideoCancelled()
            while events:
                event = events.popleft()
                if event.get("type") == "progress":
                    progress(event.get("stage", "recognizing"), event.get("completed", 0),
                             event.get("total", 0), detail=event.get("detail"))
                elif event.get("type") == "result":
                    return _prepare_video_cues(SubtitleCue(**cue) for cue in event["cues"])
                elif event.get("type") == "error":
                    raise RuntimeError(event.get("message", "Isolated ASR failed"))
            time.sleep(0.05)
        if process.returncode:
            raise RuntimeError(f"Isolated ASR exited with {process.returncode}")
        raise RuntimeError("Isolated ASR returned no result")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=1)


def translate_cues(cues, translator, config, stop, progress):
    cues = [replace(cue, text=normalize_subtitle_text(cue.text)) for cue in cues]
    cues = [cue for cue in cues if cue.text]
    if not cues:
        raise RuntimeError("No subtitle text is available for translation")
    if getattr(translator, "uses_shared_task_core", False) is True and callable(getattr(translator, "translate_all", None)):
        texts = translator.translate_all(cues, stop=stop, progress=progress)
        if len(texts) != len(cues):
            raise RuntimeError(f"Cloud translation returned {len(texts)} lines for {len(cues)} subtitles")
        translated = [SubtitleCue(cue.start_ms, cue.end_ms, normalize_subtitle_text(text), config.target_lang)
                      for cue, text in zip(cues, texts)]
        if any(not cue.text for cue in translated):
            raise RuntimeError("Translation returned an empty subtitle")
        return translated
    if callable(getattr(translator, "translate_batch", None)) and isinstance(getattr(translator, "batch_size", None), int):
        translated = []
        context = []
        for start in range(0, len(cues), translator.batch_size):
            _check_cancel(stop)
            batch = cues[start:start + translator.batch_size]
            texts = translator.translate_batch(batch, context=context, stop=stop)
            if len(texts) != len(batch):
                raise RuntimeError(f"Cloud translation returned {len(texts)} lines for {len(batch)} subtitles")
            for cue, text in zip(batch, texts):
                text = normalize_subtitle_text(text)
                if not text:
                    raise RuntimeError(f"Translation returned an empty subtitle at cue {start + len(translated) + 1}")
                translated.append(SubtitleCue(cue.start_ms, cue.end_ms, text, config.target_lang))
                context.append((cue.text, text))
                context = context[-max(0, config.context_segments):]
            progress("translating", len(translated), len(cues))
        return translated
    from ModuleFolders.Media.contracts import TranslationContext
    history = deque(maxlen=config.context_segments)
    translated = []
    for index, cue in enumerate(cues, 1):
        _check_cancel(stop)
        context = list(history)
        while context and sum(len(item.source_text) + len(item.translated_text) for item in context) > 1600:
            context.pop(0)
        text = normalize_subtitle_text(translator.translate(
            cue.text, source_lang=cue.language, target_lang=config.target_lang,
            context=tuple(context),
        ))
        _check_cancel(stop)
        if not text:
            raise RuntimeError(f"Translation returned an empty subtitle at cue {index}")
        translated.append(SubtitleCue(cue.start_ms, cue.end_ms, text, config.target_lang))
        history.append(TranslationContext(cue.text, text))
        progress("translating", index, len(cues))
    return translated


def mux_arguments(ffmpeg, source, subtitle, destination, mode, language):
    arguments = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source)]
    if mode == "soft":
        code = {"zh": "zho", "en": "eng", "ja": "jpn", "ko": "kor"}.get(language, "und")
        return arguments + ["-i", str(subtitle), "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
                            "-map_metadata", "0", "-map_chapters", "0", "-c", "copy", "-c:s", "srt",
                            "-metadata:s:s:0", f"language={code}", "-disposition:s:0", "default", str(destination)]
    if mode != "hard":
        raise ValueError("Invalid subtitle mode")
    # A fixed ASCII name relative to cwd avoids Windows drive/filter escaping.
    return mux_arguments_with_encoder(ffmpeg, source, subtitle, destination, "libx264")


def mux_arguments_with_encoder(ffmpeg, source, subtitle, destination, encoder):
    """Build the hard-subtitle command for a selected H.264 encoder."""
    arguments = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source)]
    video_options = {
        "libx264": ["-c:v", "libx264", "-crf", "18", "-preset", "medium"],
        "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"],
        "h264_qsv": ["-c:v", "h264_qsv", "-global_quality", "23", "-look_ahead", "0"],
        "h264_amf": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"],
        "h264_videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "8M"],
    }
    if encoder not in video_options:
        raise ValueError("Unsupported video encoder")
    return arguments + ["-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
                        "-vf", "subtitles=translated.srt", *video_options[encoder],
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destination)]


def choose_video_encoder(available, requested="auto", system=None):
    """Choose the fastest advertised H.264 encoder with a deterministic fallback."""
    available = set(available or ())
    if requested != "auto":
        return requested if requested in available or requested == "libx264" else "libx264"
    system = (system or os.uname().sysname if hasattr(os, "uname") else os.name).lower()
    preferred = ["h264_nvenc", "h264_qsv", "h264_amf"]
    if system == "darwin":
        preferred.insert(0, "h264_videotoolbox")
    return next((encoder for encoder in preferred if encoder in available), "libx264")


def run_video(config, emit, stop, *, recognizer_factory=None, translator_factory=None, detector_factory=None):
    """Run each stage serially; publish a finished video only after FFmpeg succeeds."""
    validate_video_input(config.input_path, config.subtitle_mode)
    if config.glossary_mode == "temporary":
        config = replace(config, glossary=())
    elif config.glossary_mode != "manual" or not config.glossary:
        raise ValueError("Select a non-empty manual glossary for this video")
    source = Path(config.input_path).expanduser().resolve()
    output = Path(config.output_directory).expanduser().resolve()
    # Keep the overridable lookup as the single entry point; on Windows it
    # transparently prepares the bundled media-runtime tools when absent.
    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")

    progress_started = time.monotonic()
    current_translator = None
    current_progress = {
        "stage": "probing", "completed": 0, "total": 0,
        "request_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
    }

    def progress(stage, completed=0, total=0, *, heartbeat=False, detail=None):
        current_progress.update(stage=stage, completed=completed, total=total)
        if current_translator is not None:
            def numeric(name):
                value = getattr(current_translator, name, 0)
                return value if isinstance(value, (int, float)) else 0
            current_progress.update(request_count=numeric("request_count"),
                                    prompt_tokens=numeric("prompt_tokens"),
                                    completion_tokens=numeric("completion_tokens"))
        emit({"type": "video_progress", **current_progress,
              "elapsed_seconds": round(time.monotonic() - progress_started, 1),
              "heartbeat": heartbeat})
        if detail:
            emit({"type": "video_log", "message": detail})

    def run_stage_tool(arguments, *, cwd=None):
        return run_tool(
            arguments,
            stop,
            cwd=cwd,
            heartbeat=lambda _elapsed: progress(
                current_progress["stage"], current_progress["completed"], current_progress["total"], heartbeat=True
            ),
        )

    progress("probing")
    probe = json.loads(run_stage_tool([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(source)]))
    kinds = {stream.get("codec_type") for stream in probe.get("streams", [])}
    if not {"audio", "video"} <= kinds:
        raise ValueError("The selected video must contain a video stream and an audio stream")
    available_encoders = set()
    if config.subtitle_mode == "hard":
        filters = run_stage_tool([ffmpeg, "-hide_banner", "-filters"])
        encoders = run_stage_tool([ffmpeg, "-hide_banner", "-encoders"])
        if b" subtitles " not in filters:
            raise RuntimeError("Hard subtitles require an FFmpeg build with libass (subtitles)")
        available_encoders = {
            name for name in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox")
            if name.encode("ascii") in encoders
        }
        if not available_encoders:
            raise RuntimeError("Hard subtitles require an FFmpeg H.264 encoder")
    _check_cancel(stop)
    output.mkdir(parents=True, exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix=source.stem + "-translated-", dir=output))
    emit({"type": "video_output", "directory": str(job)})
    source_srt = job / (source.stem + ".source.srt")
    translated_srt = job / (source.stem + f".{config.target_lang}.srt")
    with tempfile.TemporaryDirectory(prefix=".work-", dir=job) as temporary:
        work = Path(temporary)
        extracted, cleaned = work / "audio.wav", work / "clean.wav"
        progress("extracting")
        run_stage_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source),
                        "-map", "0:a:0", "-vn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(extracted)])
        progress("denoising")
        run_stage_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(extracted),
                        "-af", "afftdn=nf=-25:tn=1", "-c:a", "pcm_s16le", str(cleaned)])
        extracted.unlink()
        _check_cancel(stop)
        from ModuleFolders.Media.video_backends import compute_devices, load_recognizer, load_translator
        progress("loading_asr")
        isolated_asr = bool(config.asr_interpreter and config.asr_mode == "local" and config.translation_mode == "cloud")
        devices = ("cloud", "cloud") if isolated_asr else (
            compute_devices(config) if recognizer_factory is None or translator_factory is None else ("cpu", "cpu")
        )
        recognizer = None
        if not isolated_asr:
            recognizer = (recognizer_factory or (lambda: load_recognizer(config, devices[1])))()
        detector = None
        try:
            if isolated_asr:
                emit({"type": "video_log", "message": f"ASR：使用隔离环境 {config.asr_interpreter}"})
                cues = recognize_wav_isolated(cleaned, config, config.asr_interpreter, stop, progress)
            else:
                if detector_factory is None:
                    from ModuleFolders.Media.local_backends import SileroSpeechDetector
                    detector_factory = SileroSpeechDetector
                detector = detector_factory()
                cues = recognize_wav(cleaned, recognizer, detector, config, stop, progress)
            cues = _prepare_video_cues(cues)
            write_srt(source_srt, cues)
        finally:
            if recognizer is not None and hasattr(recognizer, "close"):
                recognizer.close()
            del recognizer, detector
        # ASR and translation weights do not need to occupy GPU memory together.
        if recognizer_factory is None and config.asr_mode == "local" and not isolated_asr:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        _check_cancel(stop)
        progress("loading_translation")
        translator = (translator_factory or (lambda: load_translator(config, devices[0])))()
        current_translator = translator
        try:
            emit({"type": "video_log", "message": "术语表：提交完整 ASR 文本，开始提取临时术语"})
            from ModuleFolders.Media.video_glossary import extract_video_glossary
            glossary = extract_video_glossary(cues, translator, config, stop, progress)
            emit({"type": "video_glossary", "count": len(glossary)})
            translated = translate_cues(cues, translator, config, stop, progress)
            write_srt(translated_srt, translated)
        finally:
            if hasattr(translator, "close"):
                translator.close()
            del translator
            current_translator = None
        shutil.copyfile(translated_srt, work / "translated.srt")
        progress("muxing" if config.subtitle_mode == "soft" else "burning")
        suffix = ".mkv" if config.subtitle_mode == "soft" else ".mp4"
        pending = work / ("video" + suffix)
        encoder = choose_video_encoder(available_encoders, config.video_encoder)
        emit({"type": "video_log", "message": f"FFmpeg：硬字幕编码器 {encoder}" if config.subtitle_mode == "hard" else "FFmpeg：封装软字幕，不重编码"})
        mux = mux_arguments(ffmpeg, source, work / "translated.srt", pending,
                            config.subtitle_mode, config.target_lang)
        if config.subtitle_mode == "hard":
            mux = mux_arguments_with_encoder(ffmpeg, source, work / "translated.srt", pending, encoder)
        try:
            run_stage_tool(mux, cwd=work)
        except RuntimeError:
            if config.subtitle_mode != "hard" or encoder == "libx264":
                raise
            pending.unlink(missing_ok=True)
            run_stage_tool(mux_arguments_with_encoder(ffmpeg, source, work / "translated.srt", pending, "libx264"), cwd=work)
        _check_cancel(stop)
        destination = job / (source.stem + f".{config.target_lang}" + suffix)
        pending.rename(destination)
    result = {"video": str(destination), "source_srt": str(source_srt), "translated_srt": str(translated_srt),
              "directory": str(job), "subtitle_mode": config.subtitle_mode, "cue_count": len(cues)}
    emit({"type": "video_complete", **result})
    return result
