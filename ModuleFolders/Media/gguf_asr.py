"""Resident native Qwen GGUF recognizer with a separate audio encoder."""

import base64
import io
import json
from pathlib import Path
import re
import time
import wave

from ModuleFolders.Media.contracts import Transcript
from ModuleFolders.Media.gguf_backend import GgufTranslator
from ModuleFolders.Media.qwen_asr import LANGUAGES


def select_asr_compute(requested, *, cuda_available, adapters):
    from ModuleFolders.Media.compute import select_compute
    if requested == 'mps':
        raise RuntimeError('GGUF ASR uses Metal, not MPS; choose auto or metal')
    return select_compute(requested, gguf=True, cuda_available=cuda_available, adapters=adapters)


def asr_device_choices(recognizer):
    import sys
    from ModuleFolders.Media.asr_catalog import get_recognizer
    if get_recognizer(recognizer).backend == 'gguf':
        return ('auto', 'metal', 'cpu') if sys.platform == 'darwin' else ('auto', 'cuda:0', 'vulkan', 'cpu')
    return ('auto', 'cpu', 'mps') if sys.platform == 'darwin' else ('auto', 'cpu', 'cuda:0')


class GgufSpeechRecognizer(GgufTranslator):
    def __init__(self, model_dir, *, recognizer='qwen-gguf-0.6b', device='cpu', max_new_tokens=256):
        from ModuleFolders.Media.asr_catalog import get_recognizer
        model = get_recognizer(recognizer)
        if model.backend != 'gguf':
            raise ValueError('Select a GGUF recognition model')
        root = Path(model_dir).expanduser()
        super().__init__(root / model.filename, family='qwen-asr', model_name=model.name,
                         projector=root / model.projector, device=device, max_new_tokens=max_new_tokens)

    def transcribe(self, segment, *, language):
        if segment.sample_rate != 16000 or language not in LANGUAGES:
            raise ValueError('GGUF ASR expects 16 kHz mono PCM and a supported language')
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(segment.pcm_s16le)
        messages = []
        if language != 'auto':
            messages.append({'role': 'system', 'content': LANGUAGES[language]})
        messages.append({'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {
            'data': base64.b64encode(audio.getvalue()).decode('ascii'), 'format': 'wav'}}]})
        started = time.perf_counter()
        with self._request('/v1/chat/completions', {'messages': messages, 'temperature': 0,
                                                  'max_tokens': self.max_new_tokens, 'stream': False,
                                                  'cache_prompt': False}, timeout=60) as response:
            payload = json.load(response)
        choices = payload.get('choices', [])
        if not choices or payload.get('error'):
            raise RuntimeError('GGUF ASR returned an inference error')
        if choices[0].get('finish_reason') == 'length':
            raise RuntimeError('ASR reached its token limit; shorten the audio segment')
        raw = str(choices[0].get('message', {}).get('content') or '').strip()
        detected = language
        if '<asr_text>' in raw:
            header, raw = raw.split('<asr_text>', 1)
            match = re.search(r'language\s+(.+)', header, re.I)
            if match:
                label = match[1].strip()
                detected = next((code for code, name in LANGUAGES.items() if name and name.casefold() == label.casefold()), language)
        text = re.sub(r'<\|(?:im_end|endoftext)\|>', '', raw).strip()
        self.last_metrics = dict(payload.get('timings') or {})
        self.last_metrics['asr_final_ms'] = round((time.perf_counter() - started) * 1000, 2)
        return Transcript(text, detected)
