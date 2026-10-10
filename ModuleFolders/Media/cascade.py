"""PCM endpointing and ASR/translation composition without model dependencies.

Live callers capture and segment on one thread and process queued segments on
another. Offline callers can supply their own segments, recognizer, translator
and output sink; live queue/drop policy is deliberately outside the processor.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Callable

from ModuleFolders.Media.contracts import (
    AudioSegment,
    SpeechRecognizer,
    TextTranslator,
    Transcript,
    TranslationContext,
)
from ModuleFolders.Media.index_echo_streaming import CaptionEvent


class PcmEndpointDetector:
    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        threshold: float = 0.5,
        endpoint_silence_ms: int = 450,
        max_segment_ms: int = 6000,
        min_speech_ms: int = 160,
        pre_roll_ms: int = 256,
        tail_ms: int = 160,
        target_segment_ms: int = 0,
        pause_silence_ms: int = 160,
    ) -> None:
        if sample_rate != 16_000:
            raise ValueError("The live PCM interface expects 16 kHz mono s16le")
        if not 0 <= threshold <= 1:
            raise ValueError("VAD threshold must be between 0 and 1")
        if not 0 < min_speech_ms <= max_segment_ms or endpoint_silence_ms <= 0:
            raise ValueError("Invalid endpoint durations")
        if pre_roll_ms < 0 or tail_ms < 0 or pre_roll_ms >= max_segment_ms:
            raise ValueError("Invalid pre-roll or tail duration")
        if not 0 <= target_segment_ms <= max_segment_ms or pause_silence_ms <= 0:
            raise ValueError("Invalid preferred segment or pause duration")
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._silence_samples = endpoint_silence_ms * sample_rate // 1000
        self._max_samples = max_segment_ms * sample_rate // 1000
        self._min_samples = min_speech_ms * sample_rate // 1000
        self._pre_roll_bytes = pre_roll_ms * sample_rate // 1000 * 2
        self._tail_samples = tail_ms * sample_rate // 1000
        self._target_samples = target_segment_ms * sample_rate // 1000
        self._pause_samples = pause_silence_ms * sample_rate // 1000
        self._position = 0
        self._pre_roll = bytearray()
        self._audio = bytearray()
        self._start: int | None = None
        self._last_speech = 0
        self._speech_samples = 0

    def push(self, pcm_s16le: bytes, speech_probability: float) -> list[AudioSegment]:
        if not pcm_s16le or len(pcm_s16le) % 2:
            raise ValueError("Expected non-empty, aligned mono s16le PCM")
        if not math.isfinite(speech_probability) or not 0 <= speech_probability <= 1:
            raise ValueError("Invalid VAD probability")
        samples = len(pcm_s16le) // 2
        if samples > self._max_samples:
            raise ValueError("PCM chunk exceeds maximum segment duration")
        start = self._position
        self._position += samples
        speech = speech_probability >= self.threshold
        if self._start is None and speech:
            self._start = start - len(self._pre_roll) // 2
            self._audio.extend(self._pre_roll)
        if self._start is not None:
            self._audio.extend(pcm_s16le)
            if speech:
                self._last_speech = self._position
                self._speech_samples += samples
        self._pre_roll.extend(pcm_s16le)
        if len(self._pre_roll) > self._pre_roll_bytes:
            del self._pre_roll[:len(self._pre_roll) - self._pre_roll_bytes]
        if self._start is None:
            return []
        if self._position - self._last_speech >= self._silence_samples:
            return self._finish(hard_cut=False)
        if (self._target_samples and len(self._audio) // 2 >= self._target_samples
                and self._position - self._last_speech >= self._pause_samples):
            return self._finish(hard_cut=False)
        if len(self._audio) // 2 >= self._max_samples:
            return self._finish(hard_cut=True)
        return []

    def flush(self) -> list[AudioSegment]:
        return self._finish(hard_cut=False) if self._start is not None else []

    def _finish(self, *, hard_cut: bool) -> list[AudioSegment]:
        assert self._start is not None
        start = self._start
        end = self._position if hard_cut else min(
            self._position, self._last_speech + self._tail_samples
        )
        audio = bytes(self._audio[:(end - start) * 2])
        enough_speech = self._speech_samples >= self._min_samples
        self._audio.clear()
        self._start = None
        self._speech_samples = 0
        # Already submitted samples must not become the next segment's pre-roll.
        remaining = max(0, self._position - end) * 2
        self._pre_roll = self._pre_roll[-remaining:] if remaining else bytearray()
        if not enough_speech:
            return []
        return [AudioSegment(
            audio, start * 1000 // self.sample_rate,
            end * 1000 // self.sample_rate, self.sample_rate,
        )]


class CascadeProcessor:
    """Process final speech segments serially, preserving bounded context."""

    def __init__(
        self,
        recognizer: SpeechRecognizer,
        translator: TextTranslator,
        *,
        source_lang: str = "ja",
        target_lang: str = "zh",
        session_id: str = "media-cascade",
        context_segments: int = 2,
        context_chars: int = 1600,
        now: Callable[[], float] = time.monotonic,
        on_transcript: Callable[[Transcript], None] | None = None,
    ) -> None:
        if context_segments < 0 or context_chars < 0:
            raise ValueError("Context budgets must be non-negative")
        self.recognizer = recognizer
        self.translator = translator
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.session_id = session_id
        self._history: deque[TranslationContext] = deque(maxlen=context_segments)
        self._context_chars = context_chars
        self._sequence = 0
        self._now = now
        self._on_transcript = on_transcript

    def process(self, segment: AudioSegment) -> CaptionEvent | None:
        started = self._now()
        transcript = self.recognizer.transcribe(segment, language=self.source_lang)
        recognized = self._now()
        source = transcript.text.strip()
        if not source:
            return None
        if self._on_transcript:
            self._on_transcript(transcript)
        translated = self.translator.translate(
            source, source_lang=transcript.language, target_lang=self.target_lang,
            context=tuple(self._history),
        ).strip()
        if not translated:
            raise RuntimeError("Translation model returned an empty translation")
        completed = self._now()
        event = CaptionEvent(
            session_id=self.session_id, sequence=self._sequence,
            start_ms=segment.start_ms, end_ms=segment.end_ms,
            source_text=source, translated_text=translated,
            engine=f"{self.recognizer.name}+{self.translator.name}",
            metadata={
                "source_lang": transcript.language, "target_lang": self.target_lang,
                "asr_ms": round((recognized - started) * 1000),
                "translation_ms": round((completed - recognized) * 1000),
                "inference_ms": round((completed - started) * 1000),
                "timestamp_precision": "vad-segment",
            },
        )
        self._sequence += 1
        self._history.append(TranslationContext(source, translated))
        while self._history and sum(
            len(x.source_text) + len(x.translated_text) for x in self._history
        ) > self._context_chars:
            self._history.popleft()
        return event
