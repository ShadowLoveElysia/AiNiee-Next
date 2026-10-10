"""Windowed streaming adapter for the official Index-Echo-S2TT package.

Index-Echo currently exposes file/window inference rather than a PCM streaming
API. This adapter keeps model loading optional and turns incoming 16 kHz
mono PCM into bounded utterance windows. The VAD implementation remains
external: callers pass one speech probability per audio chunk, which keeps
capture, VAD, and model inference independently replaceable.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Iterable, Protocol


_TIMESTAMP_RE = re.compile(
    r"^\s*\[(\d+):(\d+(?:\.\d+)?)-(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$"
)


@dataclass(frozen=True)
class CaptionEvent:
    """A final subtitle event emitted by a media session."""

    session_id: str
    sequence: int
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str
    final: bool = True
    revision: int = 0
    engine: str = "index-echo-s2tt"
    metadata: dict[str, Any] = field(default_factory=dict)


class IndexEchoWindowModel(Protocol):
    def translate_window(
        self,
        wav16k_path: str,
        ctx_parts: list[str],
        terms: Iterable[str] = (),
        lang: str = "en",
        max_new_tokens: int = 2000,
        temperature: float = 0.0,
    ) -> tuple[str, str]:
        """Translate one 16 kHz mono WAV window."""


def _source_language_label(source_lang: str) -> str:
    labels = {
        "auto": "the source language detected from the audio",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
    }
    return labels.get(str(source_lang).strip().lower(), str(source_lang).strip() or labels["auto"])


def _index_echo_direction_supported(source_lang: str, target_lang: str) -> bool:
    source = str(source_lang or "auto").strip().lower()
    target = str(target_lang or "").strip().lower()
    return (source == "zh" and target in {"en", "ja", "es"}) or (
        source == "en" and target == "zh"
    )


def _index_echo_direction_mode(source_lang: str, target_lang: str) -> str:
    source = str(source_lang or "auto").strip().lower()
    target = str(target_lang or "").strip().lower()
    if _index_echo_direction_supported(source, target):
        return "official"
    return "experimental"


def _index_echo_instruction(source_lang: str, target_lang: str) -> str:
    source_label = _source_language_label(source_lang)
    target_labels = {"zh": "Chinese", "en": "English", "ja": "Japanese", "es": "Spanish"}
    target_label = target_labels.get(str(target_lang).strip().lower(), str(target_lang).strip())
    return (
        f"The source audio is in {source_label}. For each sentence, output three lines: "
        "the [MM:SS.CC-MM:SS.CC] timestamp, the source transcript, "
        f"then the {target_label} translation."
    )


def parse_index_echo_output(raw_output: str) -> list[dict[str, Any]]:
    """Parse the three-line timestamp/transcript/translation format."""

    cues: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in (raw_output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _TIMESTAMP_RE.match(line)
        if match:
            if current and current.get("source_text"):
                cues.append(current)
            current = {
                "start_s": int(match.group(1)) * 60 + float(match.group(2)),
                "end_s": int(match.group(3)) * 60 + float(match.group(4)),
                "source_text": match.group(5).strip(),
                "translated_text": "",
            }
            continue
        if current is None:
            continue
        if not current["source_text"]:
            current["source_text"] = line
        elif not current["translated_text"]:
            current["translated_text"] = line

    if current and current.get("source_text"):
        cues.append(current)
    return cues


def _write_pcm_wav(path: Path, pcm_s16le: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm_s16le)


class IndexEchoStreamingAdapter:
    """Adapt Index-Echo's window API to bounded PCM input.

    ``speech_probability`` is supplied by the selected VAD. A value below
    ``vad_threshold`` starts the endpoint silence timer after speech has
    started. If no probability is supplied, only the maximum window limit is
    used, which is useful for testing and for upstream endpointing engines.
    """

    def __init__(
        self,
        model: IndexEchoWindowModel,
        *,
        target_lang: str = "zh",
        source_lang: str = "auto",
        session_id: str = "index-echo-session",
        sample_rate: int = 16_000,
        max_window_ms: int = 12_000,
        endpoint_silence_ms: int = 550,
        min_utterance_ms: int = 250,
        pre_roll_ms: int = 250,
        vad_threshold: float = 0.5,
        context_windows: int = 5,
        glossary: Iterable[str] = (),
        max_new_tokens: int = 2000,
        temperature: float = 0.0,
        allow_unsupported_direction: bool = False,
        temp_dir: str | Path | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if sample_rate != 16_000:
            raise ValueError("Index-Echo-S2TT expects 16 kHz PCM input")
        if max_window_ms <= 0 or endpoint_silence_ms <= 0:
            raise ValueError("window and endpoint durations must be positive")
        self.model = model
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.max_window_ms = max_window_ms
        self.endpoint_silence_ms = endpoint_silence_ms
        self.min_utterance_ms = min_utterance_ms
        self.pre_roll_ms = pre_roll_ms
        self.vad_threshold = vad_threshold
        self.context_windows = max(0, context_windows)
        self.glossary = tuple(glossary)
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.temp_dir = Path(temp_dir) if temp_dir else None
        self._now = now

        self._utterance = bytearray()
        self._utterance_start_ms: int | None = None
        self._last_speech_ms: int | None = None
        self._pre_roll: Deque[bytes] = deque()
        self._pre_roll_bytes = self._ms_to_bytes(pre_roll_ms)
        self._history: Deque[str] = deque(maxlen=self.context_windows or 1)
        self._sequence = 0
        self._closed = False
        self._received_ms = 0

    @classmethod
    def from_model_dir(cls, model_dir: str | Path, **kwargs: Any) -> "IndexEchoStreamingAdapter":
        """Load ``AudioTransModel`` from an official Index-Echo package."""

        root = Path(model_dir).expanduser().resolve()
        source_lang = str(kwargs.pop("source_lang", "auto") or "auto").strip().lower()
        target_lang = str(kwargs.get("target_lang", "zh") or "zh").strip().lower()
        allow_unsupported = bool(kwargs.get("allow_unsupported_direction", False))
        direction_mode = _index_echo_direction_mode(source_lang, target_lang)
        if not allow_unsupported and direction_mode != "official":
            raise ValueError(
                "Index-Echo-S2TT packaged/validated directions are zh->en/ja/es and en->zh; "
                f"requested {source_lang}->{target_lang}. "
                "Use a supported direction or explicitly pass allow_unsupported_direction=True for research."
            )
        infer_path = root / "infer.py"
        if not infer_path.is_file():
            raise FileNotFoundError(f"Index-Echo package has no infer.py: {root}")
        spec = importlib.util.spec_from_file_location("ainiee_index_echo_infer", infer_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load Index-Echo inference module: {infer_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # The released package exposes zh only in its broader evaluation
        # matrix, while its public wrapper currently registers en/ja/es.
        # Adding the instruction here keeps the package untouched and makes
        # the experimental foreign-language-to-Chinese path selectable.
        instructions = getattr(module, "INSTR", None)
        if isinstance(instructions, dict):
            instructions.setdefault("zh", _index_echo_instruction(source_lang, "zh"))
        model = module.AudioTransModel(root=str(root), **kwargs.pop("model_kwargs", {}))

        original_translate_window = model.translate_window

        def translate_window_with_source_language(
            wav16k_path: str,
            ctx_parts: list[str],
            terms: Iterable[str] = (),
            lang: str = "en",
            max_new_tokens: int = 2000,
            temperature: float = 0.0,
        ) -> tuple[str, str]:
            if isinstance(instructions, dict):
                instructions[lang] = _index_echo_instruction(source_lang, lang)
            return original_translate_window(
                wav16k_path, ctx_parts, terms, lang, max_new_tokens, temperature
            )

        model.translate_window = translate_window_with_source_language
        kwargs["source_lang"] = source_lang
        kwargs["target_lang"] = target_lang
        kwargs["allow_unsupported_direction"] = allow_unsupported
        return cls(model, **kwargs)

    @property
    def received_ms(self) -> int:
        return self._received_ms

    def push_pcm(
        self,
        pcm_s16le: bytes,
        *,
        speech_probability: float | None = None,
        timestamp_ms: int | None = None,
    ) -> list[CaptionEvent]:
        """Push mono signed-16 PCM and return any completed caption events."""

        self._ensure_open()
        if not pcm_s16le or len(pcm_s16le) % 2:
            raise ValueError("pcm_s16le must be non-empty, aligned mono s16le bytes")
        chunk_ms = len(pcm_s16le) * 1000 // (2 * self.sample_rate)
        start_ms = timestamp_ms if timestamp_ms is not None else self._received_ms
        self._received_ms = max(self._received_ms, start_ms + chunk_ms)

        is_speech = speech_probability is None or speech_probability >= self.vad_threshold
        if is_speech and self._utterance_start_ms is None:
            self._utterance_start_ms = max(0, start_ms - self._pre_roll_duration_ms())
            self._utterance.extend(b"".join(self._pre_roll))
        self._utterance.extend(pcm_s16le)

        if is_speech:
            self._last_speech_ms = start_ms + chunk_ms
        self._remember_pre_roll(pcm_s16le)

        if self._utterance_start_ms is None:
            return []
        utterance_ms = self._received_ms - self._utterance_start_ms
        silence_ms = (
            self._received_ms - self._last_speech_ms
            if self._last_speech_ms is not None
            else 0
        )
        should_flush = utterance_ms >= self.max_window_ms
        should_flush = should_flush or (
            self._last_speech_ms is not None
            and silence_ms >= self.endpoint_silence_ms
            and utterance_ms >= self.min_utterance_ms
        )
        return self._flush_window() if should_flush else []

    def flush(self) -> list[CaptionEvent]:
        """Flush a pending utterance at stream end."""

        self._ensure_open()
        if self._utterance_start_ms is None:
            return []
        return self._flush_window()

    def close(self) -> list[CaptionEvent]:
        if self._closed:
            return []
        events = self.flush()
        self._closed = True
        return events

    def _flush_window(self) -> list[CaptionEvent]:
        pcm = bytes(self._utterance)
        start_ms = self._utterance_start_ms or 0
        end_ms = start_ms + len(pcm) * 1000 // (2 * self.sample_rate)
        self._utterance = bytearray()
        self._utterance_start_ms = None
        self._last_speech_ms = None

        if len(pcm) < self._ms_to_bytes(self.min_utterance_ms):
            return []

        with tempfile.TemporaryDirectory(dir=str(self.temp_dir) if self.temp_dir else None) as temp:
            wav_path = Path(temp) / "window.wav"
            _write_pcm_wav(wav_path, pcm, self.sample_rate)
            started = self._now()
            context = list(self._history)
            raw_output, _ = self.model.translate_window(
                str(wav_path),
                context,
                self.glossary,
                self.target_lang,
                self.max_new_tokens,
                self.temperature,
            )
            inference_ms = int((self._now() - started) * 1000)

            cues = parse_index_echo_output(raw_output)

        events: list[CaptionEvent] = []
        history_lines: list[str] = []
        for cue in cues:
            cue_start = start_ms + int(round(cue["start_s"] * 1000))
            cue_end = start_ms + int(round(cue["end_s"] * 1000))
            source = cue["source_text"].strip()
            translated = cue["translated_text"].strip()
            if not source:
                continue
            history_lines.extend([source, translated])
            events.append(
                CaptionEvent(
                    session_id=self.session_id,
                    sequence=self._sequence,
                    start_ms=max(start_ms, cue_start),
                    end_ms=max(max(start_ms, cue_start), cue_end),
                    source_text=source,
                    translated_text=translated,
                    metadata={
                        "window_start_ms": start_ms,
                        "window_end_ms": end_ms,
                        "inference_ms": inference_ms,
                        "target_lang": self.target_lang,
                    },
                )
            )
            self._sequence += 1
        if history_lines and self.context_windows:
            self._history.append("\n".join(history_lines))
        return events

    def _remember_pre_roll(self, pcm: bytes) -> None:
        self._pre_roll.append(pcm)
        total = sum(len(chunk) for chunk in self._pre_roll)
        while total > self._pre_roll_bytes and self._pre_roll:
            total -= len(self._pre_roll.popleft())

    def _pre_roll_duration_ms(self) -> int:
        return min(self.pre_roll_ms, self._received_ms)

    def _ms_to_bytes(self, duration_ms: int) -> int:
        return max(0, duration_ms * self.sample_rate * 2 // 1000)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Index-Echo streaming session is closed")
