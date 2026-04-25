from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class TextSeed:
    seed_id: str
    bbox: list[int]
    polygon: list[list[float]]
    source_text: str
    confidence: float
    direction: str

    def to_dict(self) -> dict[str, object]:
        return {
            "seed_id": self.seed_id,
            "bbox": list(self.bbox),
            "polygon": [list(point) for point in self.polygon],
            "source_text": self.source_text,
            "confidence": self.confidence,
            "direction": self.direction,
        }


@dataclass(slots=True)
class BubbleAssignment:
    seed_id: str
    bubble_id: str
    overlap_ratio: float
    component_bbox: list[int]
    inner_bbox: list[int]
    shared_bubble_count: int
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "seed_id": self.seed_id,
            "bubble_id": self.bubble_id,
            "overlap_ratio": self.overlap_ratio,
            "component_bbox": list(self.component_bbox),
            "inner_bbox": list(self.inner_bbox),
            "shared_bubble_count": self.shared_bubble_count,
            "status": self.status,
        }


def _pad_bbox(bbox: list[int], page_width: int, page_height: int, pad_x: int, pad_y: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    return [
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(page_width, x2 + pad_x),
        min(page_height, y2 + pad_y),
    ]


def _union_bbox(boxes: Iterable[list[int]]) -> list[int]:
    box_list = list(boxes)
    x1 = min(box[0] for box in box_list)
    y1 = min(box[1] for box in box_list)
    x2 = max(box[2] for box in box_list)
    y2 = max(box[3] for box in box_list)
    return [x1, y1, x2, y2]


def _boxes_touch(a: list[int], b: list[int], margin: int = 0) -> bool:
    return not (
        a[2] + margin < b[0]
        or b[2] + margin < a[0]
        or a[3] + margin < b[1]
        or b[3] + margin < a[1]
    )


def assign_bubbles(seeds: list[TextSeed], page_width: int, page_height: int) -> list[BubbleAssignment]:
    if not seeds:
        return []

    groups: list[dict[str, object]] = []
    for seed in seeds:
        padded = _pad_bbox(seed.bbox, page_width, page_height, pad_x=max(16, (seed.bbox[2] - seed.bbox[0]) // 3), pad_y=max(16, (seed.bbox[3] - seed.bbox[1]) // 4))
        matched_group: dict[str, object] | None = None
        for group in groups:
            if _boxes_touch(group["component_bbox"], padded, margin=24):  # type: ignore[arg-type]
                matched_group = group
                break

        if matched_group is None:
            groups.append(
                {
                    "bubble_id": f"bubble_{len(groups) + 1:04d}",
                    "seeds": [seed],
                    "component_bbox": padded,
                }
            )
            continue

        group_seeds = matched_group["seeds"]  # type: ignore[assignment]
        group_seeds.append(seed)
        matched_group["component_bbox"] = _union_bbox([matched_group["component_bbox"], padded])  # type: ignore[list-item]

    assignments: list[BubbleAssignment] = []
    for group in groups:
        group_seeds: list[TextSeed] = group["seeds"]  # type: ignore[assignment]
        union_bbox = _union_bbox([seed.bbox for seed in group_seeds])
        inner_bbox = _pad_bbox(union_bbox, page_width, page_height, pad_x=8, pad_y=8)
        component_bbox = _pad_bbox(union_bbox, page_width, page_height, pad_x=28, pad_y=28)
        shared_count = len(group_seeds)
        for seed in group_seeds:
            assignments.append(
                BubbleAssignment(
                    seed_id=seed.seed_id,
                    bubble_id=group["bubble_id"],  # type: ignore[arg-type]
                    overlap_ratio=1.0,
                    component_bbox=component_bbox,
                    inner_bbox=inner_bbox,
                    shared_bubble_count=shared_count,
                    status="assigned",
                )
            )

    return assignments
