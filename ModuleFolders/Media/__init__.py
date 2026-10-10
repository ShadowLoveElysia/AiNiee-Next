"""Optional audio and video translation runtime integrations."""

from ModuleFolders.Media.index_echo_streaming import (
    CaptionEvent,
    IndexEchoStreamingAdapter,
    parse_index_echo_output,
)
from ModuleFolders.Media.contracts import (
    AudioSegment,
    CaptionSink,
    SpeechRecognizer,
    TextTranslator,
    Transcript,
    TranslationContext,
)
from ModuleFolders.Media.cascade import CascadeProcessor, PcmEndpointDetector

__all__ = [
    "CaptionEvent",
    "IndexEchoStreamingAdapter",
    "parse_index_echo_output",
    "AudioSegment",
    "Transcript",
    "TranslationContext",
    "SpeechRecognizer",
    "TextTranslator",
    "CaptionSink",
    "CascadeProcessor",
    "PcmEndpointDetector",
]
