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

    @property
    def directory(self):
        return self.repo.split('/')[-1]


RECOGNITION_MODELS = (
    RecognitionModel('sensevoice', 'SenseVoiceSmall', 'iic/SenseVoiceSmall', '7bf452403abd7353a300cd760f7adae7701c92c1', .94),
    RecognitionModel('qwen-asr-0.6b', 'Qwen3-ASR-0.6B (HF)', 'Qwen/Qwen3-ASR-0.6B-hf', '005b749cd1566dc579fe0238316087e2fc1945c0', 1.58),
    RecognitionModel('qwen-asr-1.7b', 'Qwen3-ASR-1.7B (HF)', 'Qwen/Qwen3-ASR-1.7B-hf', 'fbdf079ca130130ace97d61dde535b3bebada633', 4.09),
)


def get_recognizer(value):
    for model in RECOGNITION_MODELS:
        if value in {model.key, model.name}:
            return model
    raise ValueError('Unknown recognition model: ' + str(value))


def recognition_files_present(root, key):
    model = get_recognizer(key)
    directory = Path(root).expanduser() / model.directory
    required = ('model.pt', 'config.yaml') if key == 'sensevoice' else (
        'config.json', 'tokenizer.json', 'tokenizer_config.json', 'processor_config.json', 'chat_template.jinja')
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
