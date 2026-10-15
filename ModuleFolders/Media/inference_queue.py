"""Bounded audio backlog and private text requests for one inference thread."""

from collections import deque
from dataclasses import dataclass
import queue
import threading


LANGUAGES = ("zh", "en", "ja", "ko", "yue", "zh-Hant", "fr", "de", "es", "ru")
MAX_TEXT_CHARS = 2000


@dataclass(frozen=True, repr=False)
class TextTranslationRequest:
    request_id: str
    text: str
    source_lang: str
    target_lang: str

    def validate(self):
        if not isinstance(self.request_id, str) or not 0 < len(self.request_id) <= 64:
            raise ValueError("Invalid request ID")
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > MAX_TEXT_CHARS:
            raise ValueError("Invalid text length")
        if self.source_lang not in (*LANGUAGES, "auto") or self.target_lang not in LANGUAGES:
            raise ValueError("Unsupported translation language")
        if self.source_lang == self.target_lang:
            raise ValueError("Choose different translation languages")


class LiveInferenceQueue:
    def __init__(self, audio_limit=4):
        self._audio = deque(maxlen=audio_limit)
        self._text = None
        self._condition = threading.Condition()

    def put_audio(self, item):
        with self._condition:
            dropped = len(self._audio) == self._audio.maxlen
            self._audio.append(item)
            self._condition.notify()
            return dropped

    def put_text(self, request):
        request.validate()
        with self._condition:
            if self._text is not None:
                raise queue.Full
            self._text = request
            self._condition.notify()

    def cancel_text(self, request_id):
        with self._condition:
            if self._text is not None and self._text.request_id == request_id:
                self._text = None

    def get(self, timeout=0.1):
        with self._condition:
            if not self._condition.wait_for(lambda: self._text is not None or self._audio, timeout):
                raise queue.Empty
            # Finish the current inference first, then service private text before audio backlog.
            if self._text is not None:
                request, self._text = self._text, None
                return request
            return self._audio.popleft()

    def qsize(self):
        with self._condition:
            return len(self._audio)


def translate_private(request, translator, emit):
    """Reuse the loaded translator without caption callbacks or context history."""
    callback = translator.on_partial
    translator.on_partial = None
    try:
        emit({"type": "mutual_started", "request_id": request.request_id})
        result = translator.translate(
            request.text, source_lang=request.source_lang,
            target_lang=request.target_lang, context=(),
        ).strip()
        if not result:
            raise RuntimeError("Empty translation")
        emit({"type": "mutual_result", "request_id": request.request_id, "translated_text": result})
    except Exception:
        # Backend exception messages may contain the user's text or generated output.
        emit({"type": "mutual_error", "request_id": request.request_id, "code": "inference_failed"})
    finally:
        translator.on_partial = callback
