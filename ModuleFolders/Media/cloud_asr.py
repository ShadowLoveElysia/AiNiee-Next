"""Explicitly selected HTTPS ASR; credentials and audio stay out of diagnostics."""

import io
import json
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlparse
import wave

from ModuleFolders.Media.contracts import Transcript
from ModuleFolders.Media.qwen_asr import LANGUAGES


def validate_cloud_settings(endpoint, model, api_key):
    parsed = urlparse(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("Cloud ASR requires an HTTPS API base URL without credentials or query parameters")
    if not model.strip() or not api_key.strip() or any(char in api_key for char in "\r\n"):
        raise ValueError("Enter a cloud ASR model and API key")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Cloud ASR redirects are not permitted")


class CloudSpeechRecognizer:
    name = "cloud-asr"

    def __init__(self, *, endpoint, model, api_key):
        validate_cloud_settings(endpoint, model, api_key)
        self.endpoint, self.model, self._api_key = endpoint.rstrip("/"), model, api_key
        self.opener = urllib.request.build_opener(NoRedirect())

    def transcribe(self, segment, *, language):
        if segment.sample_rate != 16000 or language not in LANGUAGES:
            raise ValueError("Cloud ASR expects 16 kHz mono PCM and a supported language")
        audio = io.BytesIO()
        with wave.open(audio, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(segment.pcm_s16le)
        boundary = "ainiee-" + secrets.token_hex(16)
        body = bytearray()
        fields = {"model": self.model, "response_format": "json"}
        if language != "auto":
            fields["language"] = language
        for key, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="segment.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        body.extend(audio.getvalue())
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(self.endpoint + "/audio/transcriptions", data=bytes(body), headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary, "Authorization": "Bearer " + self._api_key})
        try:
            with self.opener.open(request, timeout=120) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Cloud ASR HTTP {exc.code}") from None
        except (OSError, ValueError):
            raise RuntimeError("Cloud ASR connection failed or returned invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise RuntimeError("Cloud ASR response has no transcript text")
        detected = str(payload.get("language", language))
        detected = next((code for code, name in LANGUAGES.items() if name and name.casefold() == detected.casefold()), detected)
        return Transcript(payload["text"].strip(), detected)
