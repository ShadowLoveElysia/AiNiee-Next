from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, TextSeed


BUBBLE_INDEX_ARTIFACT = "bubbleIndex.json"


@dataclass(slots=True)
class BubbleSeedLink:
    seed_id: str
    bubble_id: str
    overlap_ratio: float
    status: str
    confidence: float
    shared_bubble_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class BubbleIndexEntry:
    bubble_id: str
    component_bbox: list[int]
    inner_bbox: list[int]
    seed_ids: list[str] = field(default_factory=list)
    seed_count: int = 0
    area: int = 0
    confidence: float = 0.0
    source: str = "assignment"
    status: str = "assigned"
    visual_mode: str = ""
    text_color: str = ""
    background_color: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = {
            "bubble_id": self.bubble_id,
            "component_bbox": list(self.component_bbox),
            "inner_bbox": list(self.inner_bbox),
            "seed_ids": list(self.seed_ids),
            "seed_count": self.seed_count,
            "area": self.area,
            "confidence": self.confidence,
            "source": self.source,
            "status": self.status,
        }
        if self.visual_mode:
            payload["visual_mode"] = self.visual_mode
        if self.text_color:
            payload["text_color"] = self.text_color
        if self.background_color:
            payload["background_color"] = self.background_color
        return payload


@dataclass(slots=True)
class BubbleIndex:
    page_width: int
    page_height: int
    bubbles: list[BubbleIndexEntry] = field(default_factory=list)
    seed_links: list[BubbleSeedLink] = field(default_factory=list)
    unassigned_seed_ids: list[str] = field(default_factory=list)
    weak_seed_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "bubble_count": len(self.bubbles),
            "seed_link_count": len(self.seed_links),
            "unassigned_seed_count": len(self.unassigned_seed_ids),
            "weak_seed_count": len(self.weak_seed_ids),
            "bubbles": [bubble.to_dict() for bubble in self.bubbles],
            "seed_links": [link.to_dict() for link in self.seed_links],
            "unassigned_seed_ids": list(self.unassigned_seed_ids),
            "weak_seed_ids": list(self.weak_seed_ids),
        }


def _bbox_area(bbox: list[int]) -> int:
    if len(bbox) < 4:
        return 0
    x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
    return max(0, x2 - x1) * max(0, y2 - y1)


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _assignment_confidence(assignment: BubbleAssignment) -> float:
    overlap = _clamp_confidence(float(assignment.overlap_ratio or 0.0))
    if assignment.status == "shared_bubble":
        return min(1.0, max(overlap, 0.5))
    if assignment.status == "assigned":
        return overlap
    return 0.0


def build_bubble_index(
    seeds: list[TextSeed],
    assignments: list[BubbleAssignment],
    *,
    page_width: int,
    page_height: int,
) -> BubbleIndex:
    seed_by_id = {seed.seed_id: seed for seed in seeds}
    grouped: dict[str, list[BubbleAssignment]] = {}
    seed_links: list[BubbleSeedLink] = []
    unassigned_seed_ids: list[str] = []
    weak_seed_ids: list[str] = []

    for assignment in assignments:
        seed = seed_by_id.get(assignment.seed_id)
        seed_confidence = float(seed.confidence) if seed is not None else 0.0
        confidence = _clamp_confidence(min(seed_confidence or 1.0, _assignment_confidence(assignment)))
        link = BubbleSeedLink(
            seed_id=assignment.seed_id,
            bubble_id=assignment.bubble_id,
            overlap_ratio=float(assignment.overlap_ratio or 0.0),
            status=assignment.status,
            confidence=confidence,
            shared_bubble_count=int(assignment.shared_bubble_count or 0),
        )
        seed_links.append(link)

        if not assignment.bubble_id or assignment.status not in {"assigned", "shared_bubble"}:
            unassigned_seed_ids.append(assignment.seed_id)
            continue
        if float(assignment.overlap_ratio or 0.0) <= 0.0:
            weak_seed_ids.append(assignment.seed_id)
        grouped.setdefault(assignment.bubble_id, []).append(assignment)

    bubbles: list[BubbleIndexEntry] = []
    for bubble_id in sorted(grouped):
        group = grouped[bubble_id]
        seed_ids = [assignment.seed_id for assignment in group]
        confidences = [_assignment_confidence(assignment) for assignment in group]
        first = group[0]
        bubbles.append(
            BubbleIndexEntry(
                bubble_id=bubble_id,
                component_bbox=list(first.component_bbox),
                inner_bbox=list(first.inner_bbox),
                seed_ids=seed_ids,
                seed_count=len(seed_ids),
                area=_bbox_area(list(first.component_bbox)),
                confidence=_clamp_confidence(sum(confidences) / max(1, len(confidences))),
                source="assignment",
                status="shared_bubble" if len(seed_ids) > 1 else "assigned",
                visual_mode=first.visual_mode,
                text_color=first.text_color,
                background_color=first.background_color,
            )
        )

    assigned_seed_ids = {link.seed_id for link in seed_links}
    missing_assignment_seed_ids = [seed.seed_id for seed in seeds if seed.seed_id not in assigned_seed_ids]
    unassigned_seed_ids.extend(missing_assignment_seed_ids)

    return BubbleIndex(
        page_width=int(page_width),
        page_height=int(page_height),
        bubbles=bubbles,
        seed_links=seed_links,
        unassigned_seed_ids=sorted(set(unassigned_seed_ids)),
        weak_seed_ids=sorted(set(weak_seed_ids)),
    )
