from __future__ import annotations

from pathlib import Path
from typing import Any

from ModuleFolders.MangaCore.bridge.providerAdapter import (
    get_runtime_asset_status,
    get_runtime_device_status,
    run_region_ocr_runtime,
)
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

    def __init__(self, engine_id: str | None = None, device: str | None = None) -> None:
        self.engine_id = str(engine_id or DEFAULT_OCR_ENGINE_ID)
        self.device = str(device or "auto")
        self.last_runtime_engine_id = RUNTIME_OCR_ENGINE_ID
        self.last_warning_message = ""
        self.last_used_runtime = False

    def configure(self, engine_id: str | None = None, device: str | None = None) -> None:
        if engine_id:
            self.engine_id = str(engine_id)
        if device is not None and str(device).strip():
            self.device = str(device).strip()

    def describe(self) -> dict[str, object]:
        runtime_status = get_runtime_asset_status(self.engine_id)
        device_status = get_runtime_device_status(self.device)
        return {
            "configured_engine_id": self.engine_id,
            "configured_device": device_status.configured,
            "resolved_device": device_status.resolved,
            "device": device_status.to_dict(),
            "runtime_engine_id": runtime_status.runtime_engine_id if runtime_status.available else RUNTIME_OCR_ENGINE_ID,
            "supported_engine_ids": [DEFAULT_OCR_ENGINE_ID, *ALTERNATIVE_OCR_ENGINE_IDS],
        }

    def requires_detect_regions(self) -> bool:
        runtime_status = get_runtime_asset_status(self.engine_id)
        return runtime_status.available

    def describe_last_run(self) -> dict[str, object]:
        return {
            "configured_engine_id": self.engine_id,
            "runtime_engine_id": self.last_runtime_engine_id,
            "used_runtime": self.last_used_runtime,
            "warning_message": self.last_warning_message,
        }

    @classmethod
    def _get_runtime(cls):
        if cls._ocr_instance is None:
            from rapidocr_onnxruntime import RapidOCR

            cls._ocr_instance = RapidOCR()
        return cls._ocr_instance

    def run(self, image_path: str | Path, *, regions: list[Any] | None = None) -> list[TextSeed]:
        self.last_runtime_engine_id = RUNTIME_OCR_ENGINE_ID
        self.last_warning_message = ""
        self.last_used_runtime = False
        runtime_status = get_runtime_asset_status(self.engine_id)
        if runtime_status.available and regions:
            try:
                runtime_output = run_region_ocr_runtime(image_path, self.engine_id, regions, device=self.device)
                if runtime_output is not None:
                    self.last_runtime_engine_id = runtime_output.runtime_engine_id
                    self.last_used_runtime = True
                    return runtime_output.seeds
                self.last_warning_message = (
                    f"Runtime OCR returned no output; fell back to {RUNTIME_OCR_ENGINE_ID}."
                )
            except Exception as exc:
                self.last_warning_message = (
                    f"Runtime OCR failed and fell back to {RUNTIME_OCR_ENGINE_ID}: {exc}"
                )
        elif runtime_status.available and not regions:
            self.last_warning_message = (
                f"Runtime OCR requires detect regions; fell back to {RUNTIME_OCR_ENGINE_ID}."
            )

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
