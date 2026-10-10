"""Backend-neutral contracts shared by live and offline media processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from ModuleFolders.Media.index_echo_streaming import CaptionEvent


@dataclass(frozen=True)
class AudioSegment:
    pcm_s16le: bytes
    start_ms: int
    end_ms: int
    sample_rate: int = 16_000

    def __post_init__(self) -> None:
        if not self.pcm_s16le or len(self.pcm_s16le) % 2:
            raise ValueError("Audio must contain aligned mono s16le samples")
        if self.sample_rate <= 0 or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Invalid audio segment timeline")


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str


@dataclass(frozen=True)
class TranslationContext:
    source_text: str
    translated_text: str


class SpeechRecognizer(Protocol):
    name: str

    def transcribe(self, segment: AudioSegment, *, language: str) -> Transcript: ...


class TextTranslator(Protocol):
    name: str

    def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        context: Sequence[TranslationContext],
    ) -> str: ...


class CaptionSink(Protocol):
    def emit(self, event: CaptionEvent) -> None: ...
