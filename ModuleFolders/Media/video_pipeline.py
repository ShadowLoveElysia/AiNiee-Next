"""Offline video → denoised speech → timed SRT → translated video pipeline."""

from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import time
import wave

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
        if self.asr_mode == "cloud":
            from ModuleFolders.Media.cloud_asr import validate_cloud_settings
            validate_cloud_settings(self.cloud_asr_endpoint, self.cloud_asr_model, self.cloud_asr_api_key)
        LiveConfig.validate(replace(self, glossary=() if self.glossary_mode == "temporary" else self.glossary),
                            require_recognition=self.asr_mode == "local")
        validate_video_input(self.input_path, self.subtitle_mode)
        if not self.output_directory.strip():
            raise ValueError("Select an output directory")
        if self.application_pid:
            raise ValueError("File translation cannot capture application audio")


class VideoSession(LiveSession):
    worker_module = "ModuleFolders.Media.video_worker"
    worker_creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

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


def validate_video_input(path, mode):
    if mode not in {"soft", "hard"}:
        raise ValueError("Choose switchable subtitles or burned-in subtitles")
    source = Path(path).expanduser()
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("Select a supported video file")


def find_tool(name):
    configured = os.environ.get("AINIEE_" + name.upper(), "")
    candidates = [configured] if configured else []
    executable = name + (".exe" if os.name == "nt" else "")
    candidates += [str(PROJECT_ROOT / "Resource/MediaRuntime/ffmpeg/bin" / executable),
                   str(PROJECT_ROOT / "Resource/MediaRuntime/ffmpeg" / executable),
                   shutil.which(name) or ""]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise FileNotFoundError(f"{name} not found; install FFmpeg and add its bin directory to PATH, "
                            f"or set AINIEE_{name.upper()}")


def _check_cancel(stop):
    if stop.is_set():
        raise VideoCancelled()


def run_tool(arguments, stop, *, cwd=None):
    _check_cancel(stop)
    process = subprocess.Popen(arguments, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        while True:
            try:
                output, error = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                _check_cancel(stop)
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
            text = "\n".join(line.strip() for line in cue.text.splitlines() if line.strip())
            stream.write(f"{index}\n{_timestamp(cue.start_ms)} --> {_timestamp(cue.end_ms)}\n{text}\n\n")


def recognize_wav(path, recognizer, detector, config, stop, progress):
    from ModuleFolders.Media.cascade import PcmEndpointDetector
    endpoint = PcmEndpointDetector(endpoint_silence_ms=config.endpoint_silence_ms,
                                    target_segment_ms=config.target_segment_ms,
                                    max_segment_ms=config.max_segment_ms, pause_silence_ms=192)
    cues = []

    def transcribe(segment):
        _check_cancel(stop)
        transcript = recognizer.transcribe(segment, language=config.source_lang)
        _check_cancel(stop)
        if transcript.text.strip():
            cues.append(SubtitleCue(segment.start_ms, segment.end_ms, transcript.text.strip(), transcript.language))

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
    return cues


def translate_cues(cues, translator, config, stop, progress):
    from ModuleFolders.Media.contracts import TranslationContext
    history = deque(maxlen=config.context_segments)
    translated = []
    for index, cue in enumerate(cues, 1):
        _check_cancel(stop)
        context = list(history)
        while context and sum(len(item.source_text) + len(item.translated_text) for item in context) > 1600:
            context.pop(0)
        text = translator.translate(cue.text, source_lang=cue.language, target_lang=config.target_lang,
                                    context=tuple(context)).strip()
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
    return arguments + ["-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
                        "-vf", "subtitles=translated.srt", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destination)]


def run_video(config, emit, stop, *, recognizer_factory=None, translator_factory=None, detector_factory=None):
    """Run each stage serially; publish a finished video only after FFmpeg succeeds."""
    validate_video_input(config.input_path, config.subtitle_mode)
    if config.glossary_mode == "temporary":
        config = replace(config, glossary=())
    elif config.glossary_mode != "manual" or not config.glossary:
        raise ValueError("Select a non-empty manual glossary for this video")
    source = Path(config.input_path).expanduser().resolve()
    output = Path(config.output_directory).expanduser().resolve()
    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")

    def progress(stage, completed=0, total=0):
        emit({"type": "video_progress", "stage": stage, "completed": completed, "total": total})

    progress("probing")
    probe = json.loads(run_tool([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(source)], stop))
    kinds = {stream.get("codec_type") for stream in probe.get("streams", [])}
    if not {"audio", "video"} <= kinds:
        raise ValueError("The selected video must contain a video stream and an audio stream")
    if config.subtitle_mode == "hard":
        filters = run_tool([ffmpeg, "-hide_banner", "-filters"], stop)
        encoders = run_tool([ffmpeg, "-hide_banner", "-encoders"], stop)
        if b" subtitles " not in filters or b"libx264" not in encoders:
            raise RuntimeError("Hard subtitles require an FFmpeg build with libass (subtitles) and libx264")
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
        run_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source),
                  "-map", "0:a:0", "-vn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "16000",
                  "-c:a", "pcm_s16le", str(extracted)], stop)
        progress("denoising")
        run_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(extracted),
                  "-af", "afftdn=nf=-25:tn=1", "-c:a", "pcm_s16le", str(cleaned)], stop)
        extracted.unlink()
        _check_cancel(stop)
        from ModuleFolders.Media.video_backends import compute_devices, load_recognizer, load_translator
        progress("loading_asr")
        devices = compute_devices(config) if recognizer_factory is None or translator_factory is None else ("cpu", "cpu")
        recognizer = (recognizer_factory or (lambda: load_recognizer(config, devices[1])))()
        detector = None
        try:
            if detector_factory is None:
                from ModuleFolders.Media.local_backends import SileroSpeechDetector
                detector_factory = SileroSpeechDetector
            detector = detector_factory()
            cues = recognize_wav(cleaned, recognizer, detector, config, stop, progress)
            write_srt(source_srt, cues)
        finally:
            if hasattr(recognizer, "close"):
                recognizer.close()
            del recognizer, detector
        # ASR and translation weights do not need to occupy GPU memory together.
        if recognizer_factory is None:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        _check_cancel(stop)
        progress("loading_translation")
        translator = (translator_factory or (lambda: load_translator(config, devices[0])))()
        try:
            from ModuleFolders.Media.video_glossary import extract_video_glossary
            glossary = extract_video_glossary(cues, translator, config, stop, progress)
            emit({"type": "video_glossary", "count": len(glossary)})
            translated = translate_cues(cues, translator, config, stop, progress)
            write_srt(translated_srt, translated)
        finally:
            if hasattr(translator, "close"):
                translator.close()
            del translator
        shutil.copyfile(translated_srt, work / "translated.srt")
        progress("muxing" if config.subtitle_mode == "soft" else "burning")
        suffix = ".mkv" if config.subtitle_mode == "soft" else ".mp4"
        pending = work / ("video" + suffix)
        run_tool(mux_arguments(ffmpeg, source, work / "translated.srt", pending,
                               config.subtitle_mode, config.target_lang), stop, cwd=work)
        _check_cancel(stop)
        destination = job / (source.stem + f".{config.target_lang}" + suffix)
        pending.rename(destination)
    result = {"video": str(destination), "source_srt": str(source_srt), "translated_srt": str(translated_srt),
              "directory": str(job), "subtitle_mode": config.subtitle_mode, "cue_count": len(cues)}
    emit({"type": "video_complete", **result})
    return result
