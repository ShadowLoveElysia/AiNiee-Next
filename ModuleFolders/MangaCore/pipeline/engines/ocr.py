from __future__ import annotations

from pathlib import Path

from ModuleFolders.MangaCore.render.bubbleAssign import TextSeed

DEFAULT_OCR_ENGINE_ID = "paddleocr-vl-1.5"
ALTERNATIVE_OCR_ENGINE_IDS = ("manga-ocr", "mit48px-ocr")
RUNTIME_OCR_ENGINE_ID = "rapidocr-onnxruntime"


def _polygon_to_bbox(polygon: list[list[float]]) -> list[int]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _infer_direction(bbox: list[int]) -> str:
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    return "vertical" if height > width * 1.2 else "horizontal"


class OcrEngine:
    stage = "ocr"
    _ocr_instance = None

    def __init__(self, engine_id: str | None = None) -> None:
        self.engine_id = str(engine_id or DEFAULT_OCR_ENGINE_ID)

    def configure(self, engine_id: str | None = None) -> None:
        if engine_id:
            self.engine_id = str(engine_id)

    def describe(self) -> dict[str, object]:
        return {
            "configured_engine_id": self.engine_id,
            "runtime_engine_id": RUNTIME_OCR_ENGINE_ID,
            "supported_engine_ids": [DEFAULT_OCR_ENGINE_ID, *ALTERNATIVE_OCR_ENGINE_IDS],
        }

    @classmethod
    def _get_runtime(cls):
        if cls._ocr_instance is None:
            from rapidocr_onnxruntime import RapidOCR

            cls._ocr_instance = RapidOCR()
        return cls._ocr_instance

    def run(self, image_path: str | Path) -> list[TextSeed]:
        runtime = self._get_runtime()
        result, _timings = runtime(str(image_path))
        if not result:
            return []

        seeds: list[TextSeed] = []
        for index, item in enumerate(result, start=1):
            if not item or len(item) < 3:
                continue
            polygon_raw, source_text, confidence = item[0], item[1], item[2]
            if not isinstance(source_text, str):
                continue
            source_text = source_text.strip()
            if not source_text:
                continue

            polygon = [[float(point[0]), float(point[1])] for point in polygon_raw]
            bbox = _polygon_to_bbox(polygon)
            seeds.append(
                TextSeed(
                    seed_id=f"seed_{index:04d}",
                    bbox=bbox,
                    polygon=polygon,
                    source_text=source_text,
                    confidence=float(confidence),
                    direction=_infer_direction(bbox),
                )
            )
        return seeds
