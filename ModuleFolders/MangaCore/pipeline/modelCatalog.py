from __future__ import annotations

from dataclasses import dataclass, field


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
    ),
    "pp-doclayoutv3": MangaModelPackage(
        model_id="pp-doclayoutv3",
        stage="detect",
        display_name="PP-DocLayoutV3",
        repo_id="PaddlePaddle/PP-DocLayoutV3_safetensors",
        repo_url="https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors",
        source_url="https://huggingface.co/PaddlePaddle/PP-DocLayoutV3",
        description="Alternative layout-oriented detector package listed by Koharu.",
    ),
    "speech-bubble-segmentation": MangaModelPackage(
        model_id="speech-bubble-segmentation",
        stage="detect",
        display_name="speech-bubble-segmentation",
        repo_id="mayocream/speech-bubble-segmentation",
        repo_url="https://huggingface.co/mayocream/speech-bubble-segmentation",
        description="Alternative dedicated speech bubble detector.",
    ),
    "paddleocr-vl-1.5": MangaModelPackage(
        model_id="paddleocr-vl-1.5",
        stage="ocr",
        display_name="PaddleOCR-VL-1.5",
        repo_id="PaddlePaddle/PaddleOCR-VL-1.5",
        repo_url="https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5",
        source_url="https://huggingface.co/docs/transformers/en/model_doc/paddleocr_vl",
        description="Koharu's default OCR model card and architecture docs.",
        runtime_notes=["Koharu uses the GGUF/mmproj path; this repo is the documented upstream model card."],
    ),
    "manga-ocr": MangaModelPackage(
        model_id="manga-ocr",
        stage="ocr",
        display_name="Manga OCR",
        repo_id="mayocream/manga-ocr",
        repo_url="https://huggingface.co/mayocream/manga-ocr",
        source_url="https://huggingface.co/kha-white/manga-ocr-base",
        description="Alternative OCR engine listed by Koharu.",
    ),
    "mit48px-ocr": MangaModelPackage(
        model_id="mit48px-ocr",
        stage="ocr",
        display_name="MIT 48px OCR",
        repo_id="mayocream/mit48px-ocr",
        repo_url="https://huggingface.co/mayocream/mit48px-ocr",
        source_url="https://huggingface.co/zyddnys/manga-image-translator",
        description="Alternative OCR engine listed by Koharu.",
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
    ),
    "lama-manga": MangaModelPackage(
        model_id="lama-manga",
        stage="inpaint",
        display_name="lama-manga",
        repo_id="mayocream/lama-manga",
        repo_url="https://huggingface.co/mayocream/lama-manga",
        source_url="https://github.com/advimman/lama",
        description="Alternative inpainting engine listed by Koharu.",
    ),
    "yuzumarker-font-detection": MangaModelPackage(
        model_id="yuzumarker-font-detection",
        stage="font",
        display_name="YuzuMarker.FontDetection",
        repo_id="fffonion/yuzumarker-font-detection",
        repo_url="https://huggingface.co/fffonion/yuzumarker-font-detection",
        description="Koharu font and color hint model.",
    ),
}


def get_model_package(model_id: str) -> MangaModelPackage:
    key = str(model_id)
    if key not in MANGA_MODEL_CATALOG:
        raise KeyError(f"Unknown manga model package: {model_id}")
    return MANGA_MODEL_CATALOG[key]


def list_model_packages() -> list[MangaModelPackage]:
    return list(MANGA_MODEL_CATALOG.values())
