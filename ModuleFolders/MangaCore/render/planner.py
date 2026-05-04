from __future__ import annotations

from collections import defaultdict
import unicodedata

from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock
from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, TextSeed
from ModuleFolders.MangaCore.render.readingOrder import sort_by_reading_order
from ModuleFolders.MangaCore.render.textNormalize import normalize_manga_dialogue_for_translation

LAYOUT_ASSIGNMENT_STATUSES = {"assigned", "shared_bubble"}


def _sort_grouped_seeds(seeds: list[TextSeed], direction: str) -> list[TextSeed]:
    return sort_by_reading_order(
        [(tuple(seed.bbox), seed) for seed in seeds],
        direction=direction,
    )


def _sort_grouped_assignments(groups: dict[str, list[BubbleAssignment]]) -> list[tuple[str, list[BubbleAssignment]]]:
    sortable: list[tuple[tuple[int, int, int, int], tuple[str, list[BubbleAssignment]]]] = []
    for bubble_id, group in groups.items():
        if not group:
            continue
        bbox = tuple(int(value) for value in group[0].component_bbox)
        sortable.append((bbox, (bubble_id, group)))  # type: ignore[arg-type]
    return sort_by_reading_order(sortable, direction="vertical")


def _infer_direction(inner_bbox: list[int], seeds: list[TextSeed]) -> str:
    seed_directions = [seed.direction for seed in seeds if str(seed.direction or "").strip()]
    if seed_directions:
        vertical_votes = sum(1 for direction in seed_directions if direction == "vertical")
        horizontal_votes = sum(1 for direction in seed_directions if direction == "horizontal")
        if vertical_votes != horizontal_votes:
            return "vertical" if vertical_votes > horizontal_votes else "horizontal"

    width = max(1, inner_bbox[2] - inner_bbox[0])
    height = max(1, inner_bbox[3] - inner_bbox[1])
    return "vertical" if height > width * 1.2 else "horizontal"


def _estimate_font_size(inner_bbox: list[int], seeds: list[TextSeed], direction: str) -> int:
    width = max(1, inner_bbox[2] - inner_bbox[0])
    height = max(1, inner_bbox[3] - inner_bbox[1])
    if seeds:
        if direction == "vertical":
            seed_sizes = [max(10, int(seed.bbox[2] - seed.bbox[0])) for seed in seeds]
        else:
            seed_sizes = [max(10, int(seed.bbox[3] - seed.bbox[1])) for seed in seeds]
        average_seed_size = sum(seed_sizes) / max(1, len(seed_sizes))
        return max(12, min(72, int(average_seed_size * 0.95)))
    return max(14, min(48, int(min(width, height) * 0.34)))


def _meaningful_character_count(text: str) -> int:
    count = 0
    for character in text:
        category = unicodedata.category(character)
        if category[0] in {"L", "N"}:
            count += 1
    return count


def _has_meaningful_text(text: str) -> bool:
    normalized = "".join(line.strip() for line in text.splitlines()).strip()
    if not normalized:
        return False
    return _meaningful_character_count(normalized) >= 2


def plan_text_blocks(page_id: str, seeds: list[TextSeed], assignments: list[BubbleAssignment]) -> list[MangaTextBlock]:
    if not seeds or not assignments:
        return []

    seed_by_id = {seed.seed_id: seed for seed in seeds}
    assignment_groups: dict[str, list[BubbleAssignment]] = defaultdict(list)
    for assignment in assignments:
        if assignment.status not in LAYOUT_ASSIGNMENT_STATUSES:
            continue
        if not assignment.bubble_id:
            continue
        assignment_groups[assignment.bubble_id].append(assignment)

    blocks: list[MangaTextBlock] = []
    for index, (bubble_id, group_assignments) in enumerate(_sort_grouped_assignments(assignment_groups), start=1):
        bubble_seeds = [seed_by_id[item.seed_id] for item in group_assignments if item.seed_id in seed_by_id]
        if not bubble_seeds:
            continue

        inner_bbox = group_assignments[0].inner_bbox
        direction = _infer_direction(inner_bbox, bubble_seeds)
        ordered_seeds = _sort_grouped_seeds(bubble_seeds, direction)
        source_text = normalize_manga_dialogue_for_translation(
            "\n".join(seed.source_text for seed in ordered_seeds if seed.source_text.strip())
        )
        if not _has_meaningful_text(source_text):
            continue
        confidence = min(seed.confidence for seed in bubble_seeds)
        block = MangaTextBlock(
            block_id=f"blk_{page_id}_{index:03d}",
            bbox=tuple(inner_bbox),  # type: ignore[arg-type]
            source_text=source_text,
            translation="",
            ocr_confidence=confidence,
            source_direction=direction,
            rendered_direction=direction,
            origin="auto_planned",
            placement_mode="bubble_auto",
            flags=[
                "ocr_detected",
                "needs_translation",
                f"bubble:{bubble_id}",
                f"reading_order:{index:03d}",
                f"source_direction:{direction}",
                f"render_direction:auto_{direction}",
                f"seed_count:{len(bubble_seeds)}",
                *[f"seed:{seed.seed_id}" for seed in ordered_seeds],
            ],
        )
        block.style.font_size = _estimate_font_size(inner_bbox, ordered_seeds, direction)
        blocks.append(block)

    return blocks
