from __future__ import annotations

from collections import defaultdict

from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock
from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, TextSeed


def _sort_grouped_seeds(seeds: list[TextSeed], direction: str) -> list[TextSeed]:
    if direction == "vertical":
        return sorted(seeds, key=lambda seed: (seed.bbox[0], seed.bbox[1]), reverse=True)
    return sorted(seeds, key=lambda seed: (seed.bbox[1], seed.bbox[0]))


def plan_text_blocks(page_id: str, seeds: list[TextSeed], assignments: list[BubbleAssignment]) -> list[MangaTextBlock]:
    if not seeds or not assignments:
        return []

    seed_by_id = {seed.seed_id: seed for seed in seeds}
    assignment_groups: dict[str, list[BubbleAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignment_groups[assignment.bubble_id].append(assignment)

    blocks: list[MangaTextBlock] = []
    for index, (bubble_id, group_assignments) in enumerate(sorted(assignment_groups.items()), start=1):
        bubble_seeds = [seed_by_id[item.seed_id] for item in group_assignments if item.seed_id in seed_by_id]
        if not bubble_seeds:
            continue

        component_bbox = group_assignments[0].component_bbox
        inner_bbox = group_assignments[0].inner_bbox
        width = max(1, inner_bbox[2] - inner_bbox[0])
        height = max(1, inner_bbox[3] - inner_bbox[1])
        direction = "vertical" if height > width * 1.2 else "horizontal"
        ordered_seeds = _sort_grouped_seeds(bubble_seeds, direction)
        source_text = "\n".join(seed.source_text for seed in ordered_seeds if seed.source_text.strip())
        confidence = min(seed.confidence for seed in bubble_seeds)
        blocks.append(
            MangaTextBlock(
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
                    f"seed_count:{len(bubble_seeds)}",
                ],
            )
        )

    return blocks
