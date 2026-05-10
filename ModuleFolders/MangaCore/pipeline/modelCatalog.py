from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_OCR_MODEL_ID = "mit48px-ocr"

MANGA_MODEL_ALIASES: dict[str, str] = {
    "48px": "mit48px-ocr",
    "mocr": "manga-ocr",
    "manga_ocr": "manga-ocr",
    "48px-ctc": "48px_ctc",
    "paddleocr-vl": "paddleocr-vl-1.5",
    "paddleocr_vl": "paddleocr-vl-1.5",
}


@dataclass(frozen=True, slots=True)
class MangaModelPackage:
    model_id: str
    stage: str
    display_name: str
    repo_id: str
    repo_url: str
    source_url: str = ""
    description: str = ""
    runtime_notes: list[str] = field(default_factory=list)
    aliases: tuple[str, ...] = ()
    hardware_tier: str = ""
    quality_tier: str = ""
    recommended_for: tuple[str, ...] = ()
    cautions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "stage": self.stage,
            "display_name": self.display_name,
            "repo_id": self.repo_id,
            "repo_url": self.repo_url,
            "source_url": self.source_url,
            "description": self.description,
            "runtime_notes": list(self.runtime_notes),
            "aliases": list(self.aliases),
            "hardware_tier": self.hardware_tier,
            "quality_tier": self.quality_tier,
            "recommended_for": list(self.recommended_for),
            "cautions": list(self.cautions),
        }


@dataclass(frozen=True, slots=True)
class MangaModelPreset:
    preset_id: str
    display_name: str
    description: str
    hardware_tier: str
    quality_tier: str
    effect_label: str
    model_ids: tuple[str, ...]
    config_overrides: dict[str, str] = field(default_factory=dict)
    recommended_for: tuple[str, ...] = ()
    cautions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "description": self.description,
            "hardware_tier": self.hardware_tier,
            "quality_tier": self.quality_tier,
            "effect_label": self.effect_label,
            "model_ids": list(self.model_ids),
            "config_overrides": dict(self.config_overrides),
            "recommended_for": list(self.recommended_for),
            "cautions": list(self.cautions),
        }


MANGA_MODEL_CATALOG: dict[str, MangaModelPackage] = {
    "comic-text-bubble-detector": MangaModelPackage(
        model_id="comic-text-bubble-detector",
        stage="detect",
        display_name="comic-text-bubble-detector",
        repo_id="ogkalu/comic-text-and-bubble-detector",
        repo_url="https://huggingface.co/ogkalu/comic-text-and-bubble-detector",
        description="Default Koharu detector for text blocks and speech bubble regions.",
        runtime_notes=["Koharu treats this as the default page-level detector."],
        hardware_tier="medium",
        quality_tier="standard",
        recommended_for=("first-pass detection", "bubble/text region detection"),
    ),
    "comic-text-detector": MangaModelPackage(
        model_id="comic-text-detector",
        stage="segment",
        display_name="comic-text-detector",
        repo_id="mayocream/comic-text-detector",
        repo_url="https://huggingface.co/mayocream/comic-text-detector",
        source_url="https://github.com/dmMaze/comic-text-detector",
        description="Koharu's default text segmentation mask package.",
        runtime_notes=["Docs point to a mayocream bundle; the original project is dmMaze/comic-text-detector."],
        hardware_tier="medium",
        quality_tier="standard",
        recommended_for=("text mask generation", "inpaint mask preparation"),
    ),
    "pp-doclayoutv3": MangaModelPackage(
        model_id="pp-doclayoutv3",
        stage="detect",
        display_name="PP-DocLayoutV3",
        repo_id="PaddlePaddle/PP-DocLayoutV3_safetensors",
        repo_url="https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors",
        source_url="https://huggingface.co/PaddlePaddle/PP-DocLayoutV3",
        description="Alternative layout-oriented detector package listed by Koharu.",
        hardware_tier="medium_high",
        quality_tier="experimental",
        recommended_for=("layout-oriented detection experiments",),
    ),
    "speech-bubble-segmentation": MangaModelPackage(
        model_id="speech-bubble-segmentation",
        stage="detect",
        display_name="speech-bubble-segmentation",
        repo_id="mayocream/speech-bubble-segmentation",
        repo_url="https://huggingface.co/mayocream/speech-bubble-segmentation",
        description="Alternative dedicated speech bubble detector.",
        hardware_tier="medium",
        quality_tier="experimental",
        recommended_for=("dedicated bubble segmentation experiments",),
    ),
    "32px": MangaModelPackage(
        model_id="32px",
        stage="ocr",
        display_name="32px OCR",
        repo_id="zyddnys/manga-image-translator",
        repo_url="https://github.com/zyddnys/manga-image-translator/releases/tag/beta-0.3",
        description="Legacy lightweight OCR model from manga-image-translator; useful as a compatibility fallback.",
        hardware_tier="low",
        quality_tier="basic",
        recommended_for=("very low resource fallback", "compatibility checks"),
        cautions=("Older lightweight OCR baseline; prefer 48px/mit48px-ocr when possible.",),
    ),
    "48px_ctc": MangaModelPackage(
        model_id="48px_ctc",
        stage="ocr",
        display_name="48px CTC OCR",
        repo_id="zyddnys/manga-image-translator",
        repo_url="https://github.com/zyddnys/manga-image-translator/releases/tag/beta-0.3",
        description="CTC variant of the 48px OCR model; useful for comparison when the default 48px model struggles.",
        aliases=("48px-ctc",),
        hardware_tier="low",
        quality_tier="comparison",
        recommended_for=("OCR comparison", "fallback testing"),
        cautions=("Comparison variant; not guaranteed to outperform the default 48px model.",),
    ),
    "paddleocr-vl-1.5": MangaModelPackage(
        model_id="paddleocr-vl-1.5",
        stage="ocr",
        display_name="PaddleOCR-VL-For-Manga",
        repo_id="jzhang533/PaddleOCR-VL-For-Manga",
        repo_url="https://huggingface.co/jzhang533/PaddleOCR-VL-For-Manga",
        source_url="https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5",
        description="Manga-finetuned PaddleOCR-VL weights for high-quality OCR; optional and resource-intensive.",
        runtime_notes=[
            "Engine id stays paddleocr-vl-1.5 for config/runtime compatibility.",
            "Upstream aliases paddleocr_vl and paddleocr-vl resolve to this package.",
            "Local runtime directory remains ocr/PaddleOCR-VL-1.5.",
        ],
        aliases=("paddleocr_vl", "paddleocr-vl"),
        hardware_tier="high",
        quality_tier="best",
        recommended_for=("high-accuracy OCR on difficult pages", "heavy GPU/large-memory setups"),
        cautions=("Most resource-intensive OCR option; not suitable as the ordinary default.",),
    ),
    "manga-ocr": MangaModelPackage(
        model_id="manga-ocr",
        stage="ocr",
        display_name="Manga OCR",
        repo_id="mayocream/manga-ocr",
        repo_url="https://huggingface.co/mayocream/manga-ocr",
        source_url="https://huggingface.co/kha-white/manga-ocr-base",
        description="Manga-specific OCR engine; upstream UI exposes this as mocr.",
        aliases=("mocr", "manga_ocr"),
        hardware_tier="medium_high",
        quality_tier="good",
        recommended_for=("Japanese manga OCR", "secondary OCR comparison"),
        cautions=("Transformer-based OCR; heavier than 48px and better used after the lightweight default is working.",),
    ),
    "mit48px-ocr": MangaModelPackage(
        model_id="mit48px-ocr",
        stage="ocr",
        display_name="MIT 48px OCR",
        repo_id="mayocream/mit48px-ocr",
        repo_url="https://huggingface.co/mayocream/mit48px-ocr",
        source_url="https://huggingface.co/zyddnys/manga-image-translator",
        description="Lightweight OCR engine and MangaCore's default OCR choice; upstream UI exposes this as 48px.",
        runtime_notes=[
            "Chosen as the default OCR engine because it has a much lower hardware requirement than PaddleOCR-VL.",
            "Upstream alias 48px resolves to this package.",
        ],
        aliases=("48px",),
        hardware_tier="low",
        quality_tier="standard",
        recommended_for=("ordinary users", "default first-pass OCR", "balanced speed and accuracy"),
    ),
    "paddleocr": MangaModelPackage(
        model_id="paddleocr",
        stage="ocr",
        display_name="PP-OCRv5 ONNX",
        repo_id="hgmzhn/manga-translator-ui",
        repo_url="https://github.com/hgmzhn/manga-translator-ui/releases/tag/v1.7.1",
        description="General Chinese/Japanese/English PP-OCRv5 ONNX recognizer with 48px color estimation.",
        hardware_tier="medium",
        quality_tier="good",
        recommended_for=("Chinese/Japanese/English OCR", "ONNX runtime workflows"),
    ),
    "paddleocr_korean": MangaModelPackage(
        model_id="paddleocr_korean",
        stage="ocr",
        display_name="PP-OCRv5 Korean ONNX",
        repo_id="hgmzhn/manga-translator-ui",
        repo_url="https://github.com/hgmzhn/manga-translator-ui/releases/tag/v1.7.1",
        description="Korean/English PP-OCRv5 ONNX recognizer with 48px color estimation.",
        hardware_tier="medium",
        quality_tier="good",
        recommended_for=("Korean manga/webtoon OCR", "Korean/English OCR"),
    ),
    "paddleocr_latin": MangaModelPackage(
        model_id="paddleocr_latin",
        stage="ocr",
        display_name="PP-OCRv5 Latin ONNX",
        repo_id="hgmzhn/manga-translator-ui",
        repo_url="https://github.com/hgmzhn/manga-translator-ui/releases/tag/v1.8.0",
        description="Latin-script PP-OCRv5 ONNX recognizer; recommended for English and other Latin text.",
        hardware_tier="medium",
        quality_tier="good",
        recommended_for=("English OCR", "Latin-script OCR"),
    ),
    "paddleocr_thai": MangaModelPackage(
        model_id="paddleocr_thai",
        stage="ocr",
        display_name="PP-OCRv5 Thai ONNX",
        repo_id="hgmzhn/manga-translator-ui",
        repo_url="https://www.modelscope.cn/models/hgmzhn/manga-translator-ui",
        description="Thai PP-OCRv5 ONNX recognizer with 48px color estimation.",
        hardware_tier="medium",
        quality_tier="good",
        recommended_for=("Thai OCR",),
    ),
    "aot-inpainting": MangaModelPackage(
        model_id="aot-inpainting",
        stage="inpaint",
        display_name="aot-inpainting",
        repo_id="mayocream/aot-inpainting",
        repo_url="https://huggingface.co/mayocream/aot-inpainting",
        source_url="https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/inpainting.ckpt",
        description="Koharu's default inpainting package.",
        runtime_notes=["Local Koharu scripts also reference a converted bundle named mayocream/manga-image-translator-inpainting-aot."],
        hardware_tier="medium",
        quality_tier="standard",
        recommended_for=("default text removal", "first-pass cleanup"),
    ),
    "lama-manga": MangaModelPackage(
        model_id="lama-manga",
        stage="inpaint",
        display_name="lama-manga",
        repo_id="mayocream/lama-manga",
        repo_url="https://huggingface.co/mayocream/lama-manga",
        source_url="https://github.com/advimman/lama",
        description="Alternative inpainting engine listed by Koharu.",
        hardware_tier="medium_high",
        quality_tier="good",
        recommended_for=("alternative inpainting quality checks",),
    ),
    "yuzumarker-font-detection": MangaModelPackage(
        model_id="yuzumarker-font-detection",
        stage="font",
        display_name="YuzuMarker.FontDetection",
        repo_id="fffonion/yuzumarker-font-detection",
        repo_url="https://huggingface.co/fffonion/yuzumarker-font-detection",
        description="Koharu font and color hint model.",
        hardware_tier="medium",
        quality_tier="experimental",
        recommended_for=("future font/style hinting",),
    ),
}

MANGA_MODEL_PRESETS: dict[str, MangaModelPreset] = {
    "low_resource": MangaModelPreset(
        preset_id="low_resource",
        display_name="低配置 / 勉强可用",
        description="面向低配置机器的最小可用组合，优先降低 OCR 负担；适合先跑通流程和兼容性检查。",
        hardware_tier="low",
        quality_tier="basic",
        effect_label="勉强",
        model_ids=("comic-text-bubble-detector", "comic-text-detector", "32px", "aot-inpainting"),
        config_overrides={"manga_ocr_engine": "32px"},
        recommended_for=("old CPU-only machines", "compatibility smoke tests"),
        cautions=("OCR 质量低于 48px，不建议作为长期默认方案。",),
    ),
    "balanced": MangaModelPreset(
        preset_id="balanced",
        display_name="普通推荐 / 中规中矩",
        description="默认推荐组合：检测、分割、48px OCR、AOT 修补。相比 PaddleOCR-VL 更适合普通用户首轮使用。",
        hardware_tier="low",
        quality_tier="standard",
        effect_label="中规中矩",
        model_ids=("comic-text-bubble-detector", "comic-text-detector", "mit48px-ocr", "aot-inpainting"),
        config_overrides={"manga_ocr_engine": "mit48px-ocr"},
        recommended_for=("ordinary users", "default first-pass pipeline"),
    ),
    "japanese_quality": MangaModelPreset(
        preset_id="japanese_quality",
        display_name="日漫增强 / 较好",
        description="在默认组合基础上加入 Manga OCR，适合日漫 OCR 质量对比和较难字体页面。",
        hardware_tier="medium_high",
        quality_tier="good",
        effect_label="较好",
        model_ids=("comic-text-bubble-detector", "comic-text-detector", "mit48px-ocr", "manga-ocr", "aot-inpainting"),
        config_overrides={"manga_ocr_engine": "manga-ocr"},
        recommended_for=("Japanese manga", "OCR comparison on difficult fonts"),
        cautions=("manga-ocr 比 48px 更重；低配置机器建议先使用普通推荐组合。",),
    ),
    "high_accuracy": MangaModelPreset(
        preset_id="high_accuracy",
        display_name="高配置 / 最好但重",
        description="包含 PaddleOCR-VL 漫画微调权重，优先追求困难页面识别质量，不适合作为普通默认下载。",
        hardware_tier="high",
        quality_tier="best",
        effect_label="最好",
        model_ids=("comic-text-bubble-detector", "comic-text-detector", "mit48px-ocr", "paddleocr-vl-1.5", "aot-inpainting"),
        config_overrides={"manga_ocr_engine": "paddleocr-vl-1.5"},
        recommended_for=("high-memory GPU setups", "difficult OCR pages"),
        cautions=("PaddleOCR-VL 资源需求最高，下载和加载成本都明显高于 48px。",),
    ),
}


def normalize_model_id(model_id: str | None) -> str:
    key = str(model_id or "").strip()
    if not key:
        return key
    return MANGA_MODEL_ALIASES.get(key, key)


def get_model_preset(preset_id: str) -> MangaModelPreset:
    key = str(preset_id).strip()
    if key not in MANGA_MODEL_PRESETS:
        raise KeyError(f"Unknown manga model preset: {preset_id}")
    return MANGA_MODEL_PRESETS[key]


def list_model_presets() -> list[MangaModelPreset]:
    return list(MANGA_MODEL_PRESETS.values())


def get_model_package(model_id: str) -> MangaModelPackage:
    key = normalize_model_id(model_id)
    if key not in MANGA_MODEL_CATALOG:
        raise KeyError(f"Unknown manga model package: {model_id}")
    return MANGA_MODEL_CATALOG[key]


def list_model_packages() -> list[MangaModelPackage]:
    return list(MANGA_MODEL_CATALOG.values())
