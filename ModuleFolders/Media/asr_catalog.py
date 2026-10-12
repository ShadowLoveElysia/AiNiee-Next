"""Independent local recognition choices; weights are fetched from ModelScope."""

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class RecognitionModel:
    key: str
    name: str
    repo: str
    revision: str
    download_gb: float
    backend: str = 'transformers'
    filename: str = ''
    projector: str = ''

    @property
    def directory(self):
        return self.repo.split('/')[-1]


RECOGNITION_MODELS = (
    RecognitionModel('sensevoice', 'SenseVoiceSmall', 'iic/SenseVoiceSmall', '7bf452403abd7353a300cd760f7adae7701c92c1', .94),
    RecognitionModel('qwen-gguf-0.6b', 'Qwen3-ASR-0.6B · Q8_0 (GGUF)', 'ggml-org/Qwen3-ASR-0.6B-GGUF', '86222636b790fae434fb24c03c46fc817dfb27b2', 1.02,
                     'gguf', 'Qwen3-ASR-0.6B-Q8_0.gguf', 'mmproj-Qwen3-ASR-0.6B-Q8_0.gguf'),
    RecognitionModel('qwen-gguf-1.7b', 'Qwen3-ASR-1.7B · Q8_0 (GGUF)', 'ggml-org/Qwen3-ASR-1.7B-GGUF', 'fd6f16ded582f5b0789ef4aea7401707ce49746b', 2.52,
                     'gguf', 'Qwen3-ASR-1.7B-Q8_0.gguf', 'mmproj-Qwen3-ASR-1.7B-Q8_0.gguf'),
    RecognitionModel('qwen-vllm-0.6b', 'Qwen3-ASR-0.6B (vLLM)', 'Qwen/Qwen3-ASR-0.6B', '4ce9cc728b473a5aedbe7b6e1ea45646316824dc', 1.88, 'vllm'),
    RecognitionModel('qwen-vllm-1.7b', 'Qwen3-ASR-1.7B (vLLM)', 'Qwen/Qwen3-ASR-1.7B', 'a04930dbe5419bfee073f7cade734f572689a3a8', 4.70, 'vllm'),
)


def get_recognizer(value):
    for model in RECOGNITION_MODELS:
        if value in {model.key, model.name}:
            return model
    raise ValueError('Unknown recognition model: ' + str(value))


def recognition_files_present(root, key):
    model = get_recognizer(key)
    directory = Path(root).expanduser() / model.directory
    if model.backend == 'gguf':
        return all((directory / name).is_file() and (directory / name).stat().st_size > 0
                   for name in (model.filename, model.projector))
    required = ('model.pt', 'config.yaml') if key == 'sensevoice' else (
        ('config.json', 'tokenizer_config.json', 'preprocessor_config.json', 'vocab.json', 'merges.txt', 'chat_template.json')
        if model.backend == 'vllm' else ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'processor_config.json', 'chat_template.jinja'))
    if not all((directory / name).is_file() for name in required):
        return False
    if key == 'sensevoice':
        return True
    single = directory / 'model.safetensors'
    if single.is_file() and single.stat().st_size > 0:
        return True
    try:
        names = set(json.loads((directory / 'model.safetensors.index.json').read_text())['weight_map'].values())
        return bool(names) and all(isinstance(name, str) and Path(name).name == name and (directory / name).is_file() and
                                   (directory / name).stat().st_size > 0 for name in names)
    except (OSError, ValueError, KeyError, TypeError):
        return False
