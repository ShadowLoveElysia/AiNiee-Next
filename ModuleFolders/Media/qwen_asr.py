"""Finalized short-segment Qwen3-ASR recognition via native Transformers."""

from pathlib import Path
from ModuleFolders.Media.contracts import Transcript

LANGUAGES = {'auto': None, 'zh': 'Chinese', 'en': 'English', 'ja': 'Japanese',
             'ko': 'Korean', 'yue': 'Cantonese'}


def recognition_device(requested, model, torch):
    if requested != 'auto':
        return requested
    if model == 'sensevoice':
        return 'cpu'
    if torch.cuda.is_available():
        return 'cuda:0'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


class QwenSpeechRecognizer:
    def __init__(self, model_dir, *, device='cpu', max_new_tokens=256):
        if device not in {'cpu', 'cuda:0', 'mps'} or max_new_tokens <= 0:
            raise ValueError('Invalid ASR device or output budget')
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        import json
        root = Path(model_dir).expanduser().resolve()
        config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
        if config.get('model_type') != 'qwen3_asr':
            raise ValueError('Select the Qwen3-ASR -hf checkpoint, including processor/tokenizer files')
        dtype = torch.float32 if device == 'cpu' else torch.float16
        self.processor = AutoProcessor.from_pretrained(str(root), local_files_only=True)
        if not callable(getattr(self.processor, 'apply_transcription_request', None)):
            raise RuntimeError('Qwen ASR processor requires Transformers 5.13+ and the -hf processor files')
        self.model = AutoModelForMultimodalLM.from_pretrained(
            str(root), local_files_only=True, dtype=dtype, device_map={'': device},
            attn_implementation='sdpa').eval()
        self.name = root.name.lower()
        self.max_new_tokens = max_new_tokens
        self.device = device

    def transcribe(self, segment, *, language):
        import numpy as np
        import torch
        if segment.sample_rate != 16000 or language not in LANGUAGES:
            raise ValueError('Qwen ASR expects 16 kHz mono PCM and a supported language')
        samples = np.frombuffer(segment.pcm_s16le, dtype='<i2').astype(np.float32) / 32768.0
        inputs = self.processor.apply_transcription_request(audio=samples, language=LANGUAGES[language], return_tensors='pt')
        inputs = inputs.to(self.model.device, self.model.dtype)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        tokens = output[:, inputs['input_ids'].shape[1]:]
        if tokens.shape[-1] >= self.max_new_tokens:
            raise RuntimeError('ASR reached its token limit; shorten the audio segment')
        parsed = self.processor.decode(tokens[0], return_format='parsed')
        detected = next((code for code, name in LANGUAGES.items() if name and
                         name.casefold() == str(parsed.get('language', '')).casefold()), language)
        return Transcript(str(parsed.get('transcription', '')).strip(), detected)
