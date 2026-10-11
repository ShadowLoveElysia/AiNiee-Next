"""Concrete translation checkpoints shared by UI, downloader and inference."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranslationModel:
    key: str
    name: str
    family: str
    repo: str
    revision: str
    download_gb: float
    vram_gib: str
    tier: str

    @property
    def directory(self) -> str:
        return self.repo.split("/")[-1]


TRANSLATION_MODELS = (
    TranslationModel("index", "Index-Translate-2B", "index", "IndexTeam/Index-Translate-2B",
                     "a516854233b170140b57d36b48d7148c0edebabb", 4.57, "6–8", "compact"),
    TranslationModel("hymt", "HY-MT2-1.8B", "hymt", "tencent/Hy-MT2-1.8B",
                     "9a341cd1b679d3efd23b46e847b01745a71ed792", 4.09, "5–7", "compact"),
    TranslationModel("index-9b", "Index-Translate-9B", "index", "IndexTeam/Index-Translate-9B",
                     "4e06279e62352dab96bbeb6fa0579bca5e822d75", 19.33, "24–28", "quality"),
    TranslationModel("hymt-7b", "HY-MT2-7B", "hymt", "tencent/Hy-MT2-7B",
                     "9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223", 16.07, "20–24", "quality"),
)


def get_model(value: str) -> TranslationModel:
    for model in TRANSLATION_MODELS:
        if value in {model.key, model.name, model.repo, model.directory}:
            return model
    raise ValueError(f"Unknown translation model: {value}")


def describe_model(value: str, translate) -> str:
    model = get_model(value)
    return "\n".join([
        model.name,
        translate("media_model_resources").format(gb=f"{model.download_gb:.2f}", vram=model.vram_gib),
        translate("media_model_domain_" + model.family),
        translate("media_model_tier_" + model.tier),
    ])


def model_files_present(root: str | Path, value: str) -> bool:
    import json
    directory = Path(root).expanduser() / get_model(value).directory
    for name in ("config.json", "tokenizer_config.json", "tokenizer.json"):
        if not (directory / name).is_file():
            return False
    single = directory / "model.safetensors"
    if single.is_file() and single.stat().st_size > 0:
        return True
    try:
        index = json.loads((directory / "model.safetensors.index.json").read_text(encoding="utf-8"))
        shards = set(index["weight_map"].values())
        return bool(shards) and all(
            isinstance(name, str) and Path(name).name == name and
            (directory / name).is_file() and (directory / name).stat().st_size > 0 for name in shards
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False
