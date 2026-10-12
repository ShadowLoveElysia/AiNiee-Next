"""Local vLLM transcription service adapter; audio stays in an in-memory WAV."""

import io
import json
import secrets
import urllib.request
from urllib.parse import urlparse
import wave

from ModuleFolders.Media.contracts import Transcript
from ModuleFolders.Media.qwen_asr import LANGUAGES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Local ASR service redirects are not permitted')


def local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def service_url(value):
    parsed = urlparse(value)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('vLLM ASR endpoint must be a local HTTP URL, e.g. http://127.0.0.1:8001/v1')
    return value.rstrip('/')


def available_models(endpoint):
    url = service_url(endpoint)
    opener = local_opener()
    with opener.open(url + '/models', timeout=5) as response:
        return [row['id'] for row in json.load(response).get('data', [])]


class VllmSpeechRecognizer:
    def __init__(self, *, model, endpoint='http://127.0.0.1:8001/v1'):
        self.endpoint = service_url(endpoint)
        self.model = model
        self.name = model.lower().split('/')[-1] + '-vllm'
        self.opener = local_opener()
        if model not in available_models(endpoint):
            raise RuntimeError('Start the matching local Qwen vLLM model service before capture')

    def transcribe(self, segment, *, language):
        if segment.sample_rate != 16000 or language not in LANGUAGES:
            raise ValueError('vLLM ASR expects 16 kHz mono PCM and a supported language')
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(segment.pcm_s16le)
        boundary = 'ainiee-' + secrets.token_hex(16)
        body = bytearray()
        fields = {'model': self.model, 'response_format': 'json', 'temperature': '0'}
        if language != 'auto':
            fields['language'] = language
        for key, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="segment.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        body.extend(buffer.getvalue())
        body.extend(f'\r\n--{boundary}--\r\n'.encode())
        request = urllib.request.Request(self.endpoint + '/audio/transcriptions', data=bytes(body),
                                         headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        with self.opener.open(request, timeout=60) as response:
            payload = json.load(response)
        text = str(payload.get('text', '')).strip()
        if '<asr_text>' in text:
            text = text.split('<asr_text>', 1)[1].strip()
        detected = str(payload.get('language', language))
        detected = next((code for code, name in LANGUAGES.items() if name and name.casefold() == detected.casefold()), detected)
        return Transcript(text, detected)
