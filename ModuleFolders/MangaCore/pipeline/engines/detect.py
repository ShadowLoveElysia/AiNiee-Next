from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock
from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, TextSeed

DEFAULT_DETECT_ENGINE_ID = "comic-text-bubble-detector"
DEFAULT_SEGMENT_ENGINE_ID = "comic-text-detector"
ALTERNATIVE_DETECT_ENGINE_IDS = ("pp-doclayoutv3", "speech-bubble-segmentation")


def _bbox_to_polygon(bbox: list[int]) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    return [
        [float(x1), float(y1)],
        [float(x2), float(y1)],
        [float(x2), float(y2)],
        [float(x1), float(y2)],
    ]


def _pad_bbox(bbox: list[int], page_width: int, page_height: int, pad_x: int, pad_y: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    return [
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(page_width, x2 + pad_x),
        min(page_height, y2 + pad_y),
    ]


def build_seed_from_block(block: MangaTextBlock, index: int) -> TextSeed:
    bbox = [int(value) for value in block.bbox]
    polygon = _bbox_to_polygon(bbox)
    source_text = str(block.source_text or block.translation or f"block_{index}")
    return TextSeed(
        seed_id=f"seed_block_{index:04d}",
        bbox=bbox,
        polygon=polygon,
        source_text=source_text,
        confidence=float(block.ocr_confidence or 1.0),
        direction=str(block.source_direction or block.rendered_direction or "vertical"),
    )


@dataclass(slots=True)
class DetectRegion:
    region_id: str
    kind: str
    bbox: list[int]
    polygon: list[list[float]]
    score: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "region_id": self.region_id,
            "kind": self.kind,
            "bbox": list(self.bbox),
            "polygon": [list(point) for point in self.polygon],
            "score": self.score,
        }


@dataclass(slots=True)
class DetectResult:
    ok: bool = True
    configured_detector_id: str = DEFAULT_DETECT_ENGINE_ID
    configured_segmenter_id: str = DEFAULT_SEGMENT_ENGINE_ID
    runtime_detector_id: str = "heuristic-grouping"
    runtime_segmenter_id: str = "pil-mask-rasterizer"
    text_regions: list[DetectRegion] = field(default_factory=list)
    bubble_regions: list[DetectRegion] = field(default_factory=list)
    warning_message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "configured_detector_id": self.configured_detector_id,
            "configured_segmenter_id": self.configured_segmenter_id,
            "runtime_detector_id": self.runtime_detector_id,
            "runtime_segmenter_id": self.runtime_segmenter_id,
            "text_region_count": len(self.text_regions),
            "bubble_region_count": len(self.bubble_regions),
            "warning_message": self.warning_message,
            "text_regions": [region.to_dict() for region in self.text_regions],
            "bubble_regions": [region.to_dict() for region in self.bubble_regions],
        }


class DetectEngine:
    stage = "detect"

    def __init__(
        self,
        detector_id: str | None = None,
        segmenter_id: str | None = None,
    ) -> None:
        self.detector_id = str(detector_id or DEFAULT_DETECT_ENGINE_ID)
        self.segmenter_id = str(segmenter_id or DEFAULT_SEGMENT_ENGINE_ID)

    def configure(
        self,
        detector_id: str | None = None,
        segmenter_id: str | None = None,
    ) -> None:
        if detector_id:
            self.detector_id = str(detector_id)
        if segmenter_id:
            self.segmenter_id = str(segmenter_id)

    def describe(self) -> dict[str, object]:
        return {
            "configured_detector_id": self.detector_id,
            "configured_segmenter_id": self.segmenter_id,
            "runtime_detector_id": "heuristic-grouping",
            "runtime_segmenter_id": "pil-mask-rasterizer",
            "supported_detector_ids": [DEFAULT_DETECT_ENGINE_ID, *ALTERNATIVE_DETECT_ENGINE_IDS],
            "supported_segmenter_ids": [DEFAULT_SEGMENT_ENGINE_ID],
        }

    def run(
        self,
        image_path: str | Path,
        page_width: int,
        page_height: int,
        *,
        seeds: list[TextSeed] | None = None,
        assignments: list[BubbleAssignment] | None = None,
        blocks: list[MangaTextBlock] | None = None,
    ) -> DetectResult:
        _ = Path(image_path)
        text_seeds = list(seeds or [])
        if not text_seeds and blocks:
            text_seeds = [build_seed_from_block(block, index) for index, block in enumerate(blocks, start=1)]

        text_regions = [
            DetectRegion(
                region_id=seed.seed_id,
                kind="text",
                bbox=list(seed.bbox),
                polygon=[list(point) for point in seed.polygon],
                score=float(seed.confidence),
            )
            for seed in text_seeds
        ]

        bubble_regions: list[DetectRegion] = []
        bubble_lookup: dict[str, DetectRegion] = {}
        for assignment in assignments or []:
            if assignment.bubble_id in bubble_lookup:
                continue
            bubble_bbox = _pad_bbox(
                list(assignment.component_bbox),
                page_width,
                page_height,
                pad_x=10,
                pad_y=10,
            )
            region = DetectRegion(
                region_id=assignment.bubble_id,
                kind="bubble",
                bbox=bubble_bbox,
                polygon=_bbox_to_polygon(bubble_bbox),
                score=max(0.0, min(1.0, float(assignment.overlap_ratio))),
            )
            bubble_lookup[assignment.bubble_id] = region
            bubble_regions.append(region)

        if not bubble_regions:
            for index, seed in enumerate(text_seeds, start=1):
                bubble_bbox = _pad_bbox(seed.bbox, page_width, page_height, pad_x=24, pad_y=24)
                bubble_regions.append(
                    DetectRegion(
                        region_id=f"bubble_{index:04d}",
                        kind="bubble",
                        bbox=bubble_bbox,
                        polygon=_bbox_to_polygon(bubble_bbox),
                        score=float(seed.confidence),
                    )
                )

        warning_message = ""
        if not text_regions:
            warning_message = "No text regions were available for detection."

        return DetectResult(
            ok=bool(text_regions),
            configured_detector_id=self.detector_id,
            configured_segmenter_id=self.segmenter_id,
            runtime_detector_id="heuristic-grouping",
            runtime_segmenter_id="pil-mask-rasterizer",
            text_regions=text_regions,
            bubble_regions=bubble_regions,
            warning_message=warning_message,
        )

    def write_masks(
        self,
        result: DetectResult,
        *,
        size: tuple[int, int],
        segment_path: str | Path,
        bubble_path: str | Path,
    ) -> None:
        segment_path = Path(segment_path)
        bubble_path = Path(bubble_path)
        segment_path.parent.mkdir(parents=True, exist_ok=True)
        bubble_path.parent.mkdir(parents=True, exist_ok=True)

        segment_mask = Image.new("L", size, 0)
        bubble_mask = Image.new("L", size, 0)
        segment_draw = ImageDraw.Draw(segment_mask)
        bubble_draw = ImageDraw.Draw(bubble_mask)

        for region in result.text_regions:
            segment_draw.polygon([(point[0], point[1]) for point in region.polygon], fill=255)
        for region in result.bubble_regions:
            bubble_draw.polygon([(point[0], point[1]) for point in region.polygon], fill=255)

        if result.text_regions:
            segment_mask = segment_mask.filter(ImageFilter.MaxFilter(size=5))
        if result.bubble_regions:
            bubble_mask = bubble_mask.filter(ImageFilter.MaxFilter(size=9))

        segment_mask.save(segment_path, format="PNG")
        bubble_mask.save(bubble_path, format="PNG")
