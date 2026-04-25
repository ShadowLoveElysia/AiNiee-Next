from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter

DEFAULT_INPAINT_ENGINE_ID = "aot-inpainting"
ALTERNATIVE_INPAINT_ENGINE_IDS = ("lama-manga",)

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime import
    cv2 = None


def _load_mask(path: str | Path | None, size: tuple[int, int]) -> Image.Image:
    if not path:
        return Image.new("L", size, 0)

    candidate = Path(path)
    if not candidate.exists():
        return Image.new("L", size, 0)

    with Image.open(candidate) as mask_image:
        mask = mask_image.convert("L")
    if mask.size != size:
        mask = mask.resize(size, resample=Image.Resampling.NEAREST)
    return mask


def _pil_fallback_inpaint(source: Image.Image, mask: Image.Image) -> Image.Image:
    softened = source.filter(ImageFilter.MedianFilter(size=7)).filter(ImageFilter.MedianFilter(size=7))
    blurred_mask = mask.filter(ImageFilter.GaussianBlur(radius=1.5))
    return Image.composite(softened, source, blurred_mask)


@dataclass(slots=True)
class InpaintResult:
    ok: bool = True
    configured_engine_id: str = DEFAULT_INPAINT_ENGINE_ID
    runtime_engine_id: str = "opencv-telea"
    mask_pixels: int = 0
    error_message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "configured_engine_id": self.configured_engine_id,
            "runtime_engine_id": self.runtime_engine_id,
            "mask_pixels": self.mask_pixels,
            "error_message": self.error_message,
        }


class InpaintEngine:
    stage = "inpaint"

    def __init__(self, engine_id: str | None = None) -> None:
        self.engine_id = str(engine_id or DEFAULT_INPAINT_ENGINE_ID)

    def configure(self, engine_id: str | None = None) -> None:
        if engine_id:
            self.engine_id = str(engine_id)

    def describe(self) -> dict[str, object]:
        runtime_engine_id = "opencv-telea" if cv2 is not None else "pil-median-fallback"
        if self.engine_id == "lama-manga":
            runtime_engine_id = "opencv-ns" if cv2 is not None else "pil-median-fallback"
        return {
            "configured_engine_id": self.engine_id,
            "runtime_engine_id": runtime_engine_id,
            "supported_engine_ids": [DEFAULT_INPAINT_ENGINE_ID, *ALTERNATIVE_INPAINT_ENGINE_IDS],
        }

    def run(
        self,
        *,
        source_path: str | Path,
        segment_mask_path: str | Path,
        output_path: str | Path,
        brush_mask_path: str | Path | None = None,
    ) -> InpaintResult:
        source_path = Path(source_path)
        output_path = Path(output_path)

        with Image.open(source_path) as source_image:
            source = source_image.convert("RGB")

        segment_mask = _load_mask(segment_mask_path, source.size)
        brush_mask = _load_mask(brush_mask_path, source.size)
        cleanup_mask = ImageChops.lighter(segment_mask, brush_mask).filter(ImageFilter.MaxFilter(size=5))
        mask_pixels = int(np.count_nonzero(np.array(cleanup_mask)))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if mask_pixels == 0:
            source.save(output_path, format="PNG")
            return InpaintResult(
                ok=True,
                configured_engine_id=self.engine_id,
                runtime_engine_id="copy-source",
                mask_pixels=0,
            )

        if cv2 is not None:
            mask_array = np.array(cleanup_mask, dtype=np.uint8)
            source_array = np.array(source, dtype=np.uint8)
            source_bgr = cv2.cvtColor(source_array, cv2.COLOR_RGB2BGR)
            if self.engine_id == "lama-manga":
                inpaint_radius = 5
                inpaint_flags = cv2.INPAINT_NS
                runtime_engine_id = "opencv-ns"
            else:
                inpaint_radius = 3
                inpaint_flags = cv2.INPAINT_TELEA
                runtime_engine_id = "opencv-telea"
            result_bgr = cv2.inpaint(source_bgr, mask_array, inpaint_radius, inpaint_flags)
            result_image = Image.fromarray(cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB))
        else:
            runtime_engine_id = "pil-median-fallback"
            result_image = _pil_fallback_inpaint(source, cleanup_mask)

        result_image.save(output_path, format="PNG")
        return InpaintResult(
            ok=True,
            configured_engine_id=self.engine_id,
            runtime_engine_id=runtime_engine_id,
            mask_pixels=mask_pixels,
        )
