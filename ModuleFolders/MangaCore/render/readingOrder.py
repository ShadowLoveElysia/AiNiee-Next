from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, TypeVar

from ModuleFolders.MangaCore.types import BBox

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ReadingBox:
    bbox: BBox
    payload: object

    @property
    def x1(self) -> int:
        return int(self.bbox[0])

    @property
    def y1(self) -> int:
        return int(self.bbox[1])

    @property
    def x2(self) -> int:
        return int(self.bbox[2])

    @property
    def y2(self) -> int:
        return int(self.bbox[3])

    @property
    def width(self) -> int:
        return max(1, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(1, self.y2 - self.y1)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2


def normalize_direction(direction: str) -> str:
    token = str(direction or "").strip().lower()
    if token in {"vertical", "v", "tbrl", "rtl_vertical"}:
        return "vertical"
    if token in {"horizontal", "h", "ltr", "rtl"}:
        return "horizontal"
    return "vertical"


def sort_by_reading_order(
    items: Iterable[tuple[BBox | list[int], T]],
    *,
    direction: str = "vertical",
) -> list[T]:
    boxes = [
        ReadingBox(
            bbox=tuple(int(value) for value in bbox),  # type: ignore[arg-type]
            payload=payload,
        )
        for bbox, payload in items
    ]
    if not boxes:
        return []

    direction = normalize_direction(direction)
    if direction == "vertical":
        ordered = _sort_vertical(boxes)
    else:
        ordered = _sort_horizontal(boxes)
    return [box.payload for box in ordered]  # type: ignore[misc]


def _sort_vertical(boxes: list[ReadingBox]) -> list[ReadingBox]:
    threshold = _cluster_threshold([box.width for box in boxes])
    columns: list[list[ReadingBox]] = []
    for box in sorted(boxes, key=lambda item: (-item.center_x, item.y1)):
        column = _find_axis_cluster(columns, box.center_x, threshold, axis="x")
        if column is None:
            columns.append([box])
        else:
            column.append(box)

    columns.sort(key=lambda column: -_cluster_center(column, axis="x"))
    ordered: list[ReadingBox] = []
    for column in columns:
        ordered.extend(sorted(column, key=lambda item: (item.y1, -item.center_x)))
    return ordered


def _sort_horizontal(boxes: list[ReadingBox]) -> list[ReadingBox]:
    threshold = _cluster_threshold([box.height for box in boxes])
    rows: list[list[ReadingBox]] = []
    for box in sorted(boxes, key=lambda item: (item.center_y, item.x1)):
        row = _find_axis_cluster(rows, box.center_y, threshold, axis="y")
        if row is None:
            rows.append([box])
        else:
            row.append(box)

    rows.sort(key=lambda row: _cluster_center(row, axis="y"))
    ordered: list[ReadingBox] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda item: (item.x1, item.center_y)))
    return ordered


def _cluster_threshold(values: list[int]) -> float:
    if not values:
        return 12.0
    typical = float(median(max(1, value) for value in values))
    return max(12.0, typical * 0.85)


def _find_axis_cluster(
    clusters: list[list[ReadingBox]],
    center: float,
    threshold: float,
    *,
    axis: str,
) -> list[ReadingBox] | None:
    best_cluster: list[ReadingBox] | None = None
    best_distance = threshold
    for cluster in clusters:
        distance = abs(_cluster_center(cluster, axis=axis) - center)
        if distance <= best_distance:
            best_distance = distance
            best_cluster = cluster
    return best_cluster


def _cluster_center(cluster: list[ReadingBox], *, axis: str) -> float:
    if not cluster:
        return 0.0
    if axis == "x":
        return sum(box.center_x for box in cluster) / len(cluster)
    return sum(box.center_y for box in cluster) / len(cluster)
