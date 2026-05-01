from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


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


@dataclass(slots=True)
class _BubbleComponent:
    component_id: str
    bbox: list[int]
    area: int
    label_id: int


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


def _inner_component_bbox(bbox: list[int], page_width: int, page_height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    pad_x = max(8, min(28, width // 12))
    pad_y = max(8, min(28, height // 12))
    if width <= pad_x * 2 + 8 or height <= pad_y * 2 + 8:
        return _pad_bbox(bbox, page_width, page_height, pad_x=0, pad_y=0)
    return [x1 + pad_x, y1 + pad_y, x2 - pad_x, y2 - pad_y]


def _extract_white_components(
    source_path: str | Path,
    page_width: int,
    page_height: int,
) -> tuple[np.ndarray | None, dict[int, _BubbleComponent]]:
    try:
        import cv2
    except Exception:
        return None, {}

    try:
        with Image.open(source_path) as image:
            gray = np.asarray(image.convert("L"), dtype=np.uint8)
    except Exception:
        return None, {}

    if gray.size == 0:
        return None, {}
    if gray.shape[1] != page_width or gray.shape[0] != page_height:
        with Image.open(source_path) as image:
            resized = image.convert("L").resize((page_width, page_height), resample=Image.Resampling.BICUBIC)
            gray = np.asarray(resized, dtype=np.uint8)

    white_mask = (gray >= 245).astype(np.uint8)
    label_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(white_mask, 8)
    total_pixels = max(1, page_width * page_height)
    min_area = max(1200, int(total_pixels * 0.0007))
    max_area = max(min_area + 1, int(total_pixels * 0.12))
    min_dimension = max(28, int(min(page_width, page_height) * 0.018))
    edge_margin = max(2, int(min(page_width, page_height) * 0.002))

    components: dict[int, _BubbleComponent] = {}
    for label_id in range(1, label_count):
        x, y, width, height, area = [int(value) for value in stats[label_id]]
        if area < min_area or area > max_area:
            continue
        if width < min_dimension or height < min_dimension:
            continue
        if width > page_width * 0.55 or height > page_height * 0.45:
            continue

        touches_page_edge = (
            x <= edge_margin
            or y <= edge_margin
            or x + width >= page_width - edge_margin
            or y + height >= page_height - edge_margin
        )
        if touches_page_edge:
            continue

        fill_ratio = area / max(1, width * height)
        if fill_ratio < 0.12:
            continue

        component_id = f"bubble_{len(components) + 1:04d}"
        components[label_id] = _BubbleComponent(
            component_id=component_id,
            bbox=[x, y, x + width, y + height],
            area=area,
            label_id=label_id,
        )

    return labels, components


def _overlap_ratio_for_label(labels: np.ndarray, bbox: list[int], label_id: int, page_width: int, page_height: int) -> float:
    x1, y1, x2, y2 = [
        max(0, min(limit, int(value)))
        for value, limit in zip(bbox, (page_width, page_height, page_width, page_height), strict=False)
    ]
    if x2 <= x1 or y2 <= y1:
        return 0.0
    crop = labels[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    return float(np.count_nonzero(crop == label_id) / crop.size)


def _cluster_seed_matches(
    matches: list[tuple[TextSeed, float]],
    page_width: int,
    page_height: int,
) -> list[list[tuple[TextSeed, float]]]:
    if len(matches) <= 1:
        return [matches]

    margin = max(10, min(18, min(page_width, page_height) // 96))
    clusters: list[dict[str, object]] = []
    for seed, overlap in matches:
        seed_width = max(1, seed.bbox[2] - seed.bbox[0])
        seed_height = max(1, seed.bbox[3] - seed.bbox[1])
        padded = _pad_bbox(
            seed.bbox,
            page_width,
            page_height,
            pad_x=max(12, seed_width // 3),
            pad_y=max(8, min(18, seed_height // 16)),
        )
        matched_cluster: dict[str, object] | None = None
        for cluster in clusters:
            if _boxes_touch(cluster["bbox"], padded, margin=margin):  # type: ignore[arg-type]
                matched_cluster = cluster
                break
        if matched_cluster is None:
            clusters.append({"bbox": padded, "matches": [(seed, overlap)]})
            continue

        cluster_matches = matched_cluster["matches"]  # type: ignore[assignment]
        cluster_matches.append((seed, overlap))
        matched_cluster["bbox"] = _union_bbox([matched_cluster["bbox"], padded])  # type: ignore[list-item]

    return [cluster["matches"] for cluster in clusters]  # type: ignore[misc]


def _cluster_bbox(matches: list[tuple[TextSeed, float]]) -> list[int]:
    return _union_bbox([seed.bbox for seed, _overlap in matches])


def _inner_cluster_bbox(bbox: list[int], page_width: int, page_height: int) -> list[int]:
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    return _pad_bbox(
        bbox,
        page_width,
        page_height,
        pad_x=max(16, min(44, width // 4)),
        pad_y=max(18, min(52, height // 8)),
    )


def _outer_cluster_bbox(bbox: list[int], page_width: int, page_height: int) -> list[int]:
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    return _pad_bbox(
        bbox,
        page_width,
        page_height,
        pad_x=max(24, min(64, width // 3)),
        pad_y=max(24, min(64, height // 6)),
    )


def _assign_from_white_components(
    seeds: list[TextSeed],
    page_width: int,
    page_height: int,
    source_path: str | Path,
) -> list[BubbleAssignment]:
    labels, components = _extract_white_components(source_path, page_width, page_height)
    if labels is None or not components:
        return []

    matched_by_label: dict[int, list[tuple[TextSeed, float]]] = {label_id: [] for label_id in components}
    assignment_by_seed: dict[str, BubbleAssignment] = {}
    for seed in seeds:
        x1, y1, x2, y2 = seed.bbox
        center_x = max(0, min(page_width - 1, int((x1 + x2) / 2)))
        center_y = max(0, min(page_height - 1, int((y1 + y2) / 2)))
        center_label = int(labels[center_y, center_x])

        best_label: int | None = center_label if center_label in components else None
        best_overlap = _overlap_ratio_for_label(labels, seed.bbox, best_label, page_width, page_height) if best_label else 0.0
        for label_id in components:
            overlap = _overlap_ratio_for_label(labels, seed.bbox, label_id, page_width, page_height)
            if overlap > best_overlap:
                best_label = label_id
                best_overlap = overlap

        if best_label is not None and (best_overlap >= 0.35 or center_label == best_label):
            matched_by_label[best_label].append((seed, best_overlap))
        else:
            component_bbox = _pad_bbox(seed.bbox, page_width, page_height, pad_x=12, pad_y=12)
            assignment_by_seed[seed.seed_id] = BubbleAssignment(
                seed_id=seed.seed_id,
                bubble_id="",
                overlap_ratio=0.0,
                component_bbox=component_bbox,
                inner_bbox=list(seed.bbox),
                shared_bubble_count=0,
                status="unassigned",
            )

    for label_id, matches in matched_by_label.items():
        if not matches:
            continue
        component = components[label_id]
        clusters = _cluster_seed_matches(matches, page_width, page_height)
        for cluster_index, cluster in enumerate(clusters, start=1):
            split_component = len(clusters) > 1
            if split_component:
                current_component_bbox = _outer_cluster_bbox(_cluster_bbox(cluster), page_width, page_height)
                current_inner_bbox = _inner_cluster_bbox(_cluster_bbox(cluster), page_width, page_height)
                bubble_id = f"{component.component_id}_part_{cluster_index:02d}"
            else:
                current_component_bbox = list(component.bbox)
                current_inner_bbox = _inner_component_bbox(component.bbox, page_width, page_height)
                bubble_id = component.component_id

            shared_count = len(cluster)
            for seed, overlap in cluster:
                assignment_by_seed[seed.seed_id] = BubbleAssignment(
                    seed_id=seed.seed_id,
                    bubble_id=bubble_id,
                    overlap_ratio=overlap,
                    component_bbox=list(current_component_bbox),
                    inner_bbox=list(current_inner_bbox),
                    shared_bubble_count=shared_count,
                    status="shared_bubble" if shared_count > 1 else "assigned",
                )

    assignments: list[BubbleAssignment] = []
    for seed in seeds:
        assignment = assignment_by_seed.get(seed.seed_id)
        if assignment is not None:
            assignments.append(assignment)
        else:
            component_bbox = _pad_bbox(seed.bbox, page_width, page_height, pad_x=12, pad_y=12)
            assignments.append(
                BubbleAssignment(
                    seed_id=seed.seed_id,
                    bubble_id="",
                    overlap_ratio=0.0,
                    component_bbox=component_bbox,
                    inner_bbox=list(seed.bbox),
                    shared_bubble_count=0,
                    status="unassigned",
                )
            )
    return assignments


def _assign_from_seed_groups(seeds: list[TextSeed], page_width: int, page_height: int) -> list[BubbleAssignment]:
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


def assign_bubbles(
    seeds: list[TextSeed],
    page_width: int,
    page_height: int,
    source_path: str | Path | None = None,
) -> list[BubbleAssignment]:
    if not seeds:
        return []
    if source_path is not None:
        component_assignments = _assign_from_white_components(seeds, page_width, page_height, source_path)
        if component_assignments:
            return component_assignments
    return _assign_from_seed_groups(seeds, page_width, page_height)
