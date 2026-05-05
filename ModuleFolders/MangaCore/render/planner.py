from __future__ import annotations

from collections import defaultdict
from statistics import median
import unicodedata

from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock
from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, INVERTED_MONOLOGUE_VISUAL_MODE, TextSeed
from ModuleFolders.MangaCore.render.readingOrder import sort_by_reading_order
from ModuleFolders.MangaCore.render.textNormalize import normalize_manga_dialogue_for_translation

LAYOUT_ASSIGNMENT_STATUSES = {"assigned", "shared_bubble"}
SOURCE_CHAR_SIZE_MIN = 10
SOURCE_CHAR_SIZE_MAX = 96
SOURCE_SIZE_SPLIT_RATIO = 1.6


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


def _clamp_font_size(value: float | int, *, minimum: int = 12, maximum: int = 72) -> int:
    return max(minimum, min(maximum, int(round(float(value)))))


def _source_char_size_for_seed(seed: TextSeed, direction: str) -> int:
    width = max(1, int(seed.bbox[2] - seed.bbox[0]))
    height = max(1, int(seed.bbox[3] - seed.bbox[1]))
    raw_size = width if direction == "vertical" else height
    return max(SOURCE_CHAR_SIZE_MIN, min(SOURCE_CHAR_SIZE_MAX, int(raw_size)))


def _source_char_sizes(seeds: list[TextSeed], direction: str) -> list[int]:
    return [_source_char_size_for_seed(seed, direction) for seed in seeds]


def _filtered_source_char_sizes(sizes: list[int]) -> list[int]:
    if len(sizes) < 3:
        return list(sizes)
    midpoint = float(median(sizes))
    if midpoint <= 0:
        return list(sizes)
    filtered = [
        size
        for size in sizes
        if size >= midpoint * 0.55 and size <= midpoint * 1.75
    ]
    return filtered or list(sizes)


def _seed_union_bbox(seeds: list[TextSeed]) -> list[int]:
    return [
        min(int(seed.bbox[0]) for seed in seeds),
        min(int(seed.bbox[1]) for seed in seeds),
        max(int(seed.bbox[2]) for seed in seeds),
        max(int(seed.bbox[3]) for seed in seeds),
    ]


def _layout_bbox_for_seed_group(
    inner_bbox: list[int],
    seeds: list[TextSeed],
    direction: str,
    *,
    split: bool,
) -> list[int]:
    if not split or not seeds:
        return list(inner_bbox)

    source_bbox = _seed_union_bbox(seeds)
    char_size = int(median(_source_char_sizes(seeds, direction)))
    pad_x = max(6, int(char_size * (0.85 if direction == "vertical" else 1.2)))
    pad_y = max(6, int(char_size * (1.2 if direction == "vertical" else 0.85)))
    x1, y1, x2, y2 = source_bbox
    candidate = [
        max(int(inner_bbox[0]), x1 - pad_x),
        max(int(inner_bbox[1]), y1 - pad_y),
        min(int(inner_bbox[2]), x2 + pad_x),
        min(int(inner_bbox[3]), y2 + pad_y),
    ]
    if candidate[2] - candidate[0] < char_size or candidate[3] - candidate[1] < char_size:
        return list(inner_bbox)
    return candidate


def _source_size_confidence(seeds: list[TextSeed], sizes: list[int]) -> float:
    if not seeds or not sizes:
        return 0.0
    average_ocr_confidence = sum(max(0.0, min(1.0, float(seed.confidence))) for seed in seeds) / len(seeds)
    if len(sizes) == 1:
        consistency = 0.72
    else:
        midpoint = max(1.0, float(median(sizes)))
        spread_ratio = (max(sizes) - min(sizes)) / midpoint
        consistency = max(0.35, min(1.0, 1.0 - spread_ratio * 0.45))
    return round(max(0.0, min(1.0, average_ocr_confidence * consistency)), 4)


def _estimate_source_metrics(
    *,
    source_text: str,
    seeds: list[TextSeed],
    direction: str,
    layout_bbox: list[int],
) -> dict[str, object]:
    sizes = _source_char_sizes(seeds, direction)
    filtered_sizes = _filtered_source_char_sizes(sizes)
    source_char_size = int(round(float(median(filtered_sizes)))) if filtered_sizes else 0
    source_bbox = _seed_union_bbox(seeds) if seeds else list(layout_bbox)
    confidence = _source_size_confidence(seeds, filtered_sizes)
    return {
        "source_char_size_px": source_char_size,
        "source_char_size_confidence": confidence,
        "source_char_size_method": "ocr_seed_bbox_median",
        "source_direction": direction,
        "source_seed_count": len(seeds),
        "source_seed_ids": [seed.seed_id for seed in seeds],
        "source_bbox": source_bbox,
        "source_layout_bbox": list(layout_bbox),
        "seed_char_sizes": sizes,
        "source_text_char_count": _meaningful_character_count(source_text),
    }


def _first_text_color(seeds: list[TextSeed], assignments: list[BubbleAssignment]) -> str:
    for assignment in assignments:
        if str(assignment.text_color or "").strip():
            return str(assignment.text_color).strip()
    for seed in seeds:
        if str(seed.text_color or "").strip():
            return str(seed.text_color).strip()
    return ""


def _first_background_color(seeds: list[TextSeed], assignments: list[BubbleAssignment]) -> str:
    for assignment in assignments:
        if str(assignment.background_color or "").strip():
            return str(assignment.background_color).strip()
    for seed in seeds:
        if str(seed.background_color or "").strip():
            return str(seed.background_color).strip()
    return ""


def _visual_mode(seeds: list[TextSeed], assignments: list[BubbleAssignment]) -> str:
    for assignment in assignments:
        if str(assignment.visual_mode or "").strip():
            return str(assignment.visual_mode).strip()
    if any(seed.color_mode == "light_text_on_dark" for seed in seeds):
        return INVERTED_MONOLOGUE_VISUAL_MODE
    return ""


def _initial_font_size_from_metrics(
    inner_bbox: list[int],
    seeds: list[TextSeed],
    direction: str,
    metrics: dict[str, object] | None = None,
) -> int:
    width = max(1, inner_bbox[2] - inner_bbox[0])
    height = max(1, inner_bbox[3] - inner_bbox[1])
    source_char_size = 0
    if metrics:
        try:
            source_char_size = int(metrics.get("source_char_size_px", 0) or 0)
        except (TypeError, ValueError):
            source_char_size = 0
    if source_char_size > 0:
        visual_scale = 0.95 if direction == "vertical" else 0.92
        geometric_limit = min(
            72,
            max(12, int(min(width, height) * (0.86 if direction == "vertical" else 0.66))),
        )
        return _clamp_font_size(min(source_char_size * visual_scale, geometric_limit))
    if seeds:
        seed_sizes = _filtered_source_char_sizes(_source_char_sizes(seeds, direction))
        average_seed_size = sum(seed_sizes) / max(1, len(seed_sizes))
        return _clamp_font_size(average_seed_size * (0.95 if direction == "vertical" else 0.92))
    return max(14, min(48, int(min(width, height) * 0.34)))


def _seed_direction(seed: TextSeed) -> str:
    return str(seed.direction or "").strip().lower()


def _should_split_seed_group(current_group: list[TextSeed], next_seed: TextSeed, direction: str) -> bool:
    if not current_group:
        return False

    next_direction = _seed_direction(next_seed)
    current_directions = {_seed_direction(seed) for seed in current_group}
    if next_direction in {"vertical", "horizontal"}:
        comparable_directions = {item for item in current_directions if item in {"vertical", "horizontal"}}
        if comparable_directions and next_direction not in comparable_directions:
            return True

    current_size = float(median(_source_char_sizes(current_group, direction)))
    next_size = float(_source_char_size_for_seed(next_seed, direction))
    ratio = max(current_size, next_size) / max(1.0, min(current_size, next_size))
    return ratio > SOURCE_SIZE_SPLIT_RATIO


def _split_ordered_seeds_by_source_size(ordered_seeds: list[TextSeed], direction: str) -> list[list[TextSeed]]:
    groups: list[list[TextSeed]] = []
    for seed in ordered_seeds:
        if not groups or _should_split_seed_group(groups[-1], seed, direction):
            groups.append([seed])
        else:
            groups[-1].append(seed)
    return groups


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
    block_index = 0
    for _bubble_index, (bubble_id, group_assignments) in enumerate(
        _sort_grouped_assignments(assignment_groups),
        start=1,
    ):
        bubble_seeds = [seed_by_id[item.seed_id] for item in group_assignments if item.seed_id in seed_by_id]
        if not bubble_seeds:
            continue

        inner_bbox = group_assignments[0].inner_bbox
        direction = _infer_direction(inner_bbox, bubble_seeds)
        ordered_seeds = _sort_grouped_seeds(bubble_seeds, direction)
        seed_groups = _split_ordered_seeds_by_source_size(ordered_seeds, direction)
        split_by_size = len(seed_groups) > 1
        for group_index, seed_group in enumerate(seed_groups, start=1):
            source_text = normalize_manga_dialogue_for_translation(
                "\n".join(seed.source_text for seed in seed_group if seed.source_text.strip())
            )
            if not _has_meaningful_text(source_text):
                continue

            layout_bbox = _layout_bbox_for_seed_group(
                inner_bbox,
                seed_group,
                direction,
                split=split_by_size,
            )
            metrics = _estimate_source_metrics(
                source_text=source_text,
                seeds=seed_group,
                direction=direction,
                layout_bbox=layout_bbox,
            )
            initial_font_size = _initial_font_size_from_metrics(layout_bbox, seed_group, direction, metrics)
            metrics["initial_font_size"] = initial_font_size
            metrics["source_size_group_index"] = group_index
            metrics["source_size_group_count"] = len(seed_groups)
            visual_mode = _visual_mode(seed_group, group_assignments)
            text_color = _first_text_color(seed_group, group_assignments)
            background_color = _first_background_color(seed_group, group_assignments)
            if visual_mode:
                metrics["visual_mode"] = visual_mode
            if text_color:
                metrics["source_text_color"] = text_color
            if background_color:
                metrics["source_background_color"] = background_color

            block_index += 1
            confidence = min(seed.confidence for seed in seed_group)
            source_char_size = int(metrics.get("source_char_size_px", 0) or 0)
            source_size_confidence = float(metrics.get("source_char_size_confidence", 0.0) or 0.0)
            flags = [
                "ocr_detected",
                "needs_translation",
                f"bubble:{bubble_id}",
                f"reading_order:{block_index:03d}",
                f"source_direction:{direction}",
                f"render_direction:auto_{direction}",
                f"seed_count:{len(seed_group)}",
                f"source_char_size:{source_char_size}",
                f"source_char_size_confidence:{source_size_confidence:.2f}",
                *[f"seed:{seed.seed_id}" for seed in seed_group],
            ]
            if split_by_size:
                flags.append("source_size_split")
            if visual_mode:
                flags.append(f"visual_mode:{visual_mode}")

            block = MangaTextBlock(
                block_id=f"blk_{page_id}_{block_index:03d}",
                bbox=tuple(layout_bbox),  # type: ignore[arg-type]
                source_text=source_text,
                translation="",
                ocr_confidence=confidence,
                source_direction=direction,
                rendered_direction=direction,
                source_metrics=metrics,
                origin="auto_planned",
                placement_mode="bubble_auto",
                flags=flags,
            )
            block.style.font_size = initial_font_size
            if visual_mode == INVERTED_MONOLOGUE_VISUAL_MODE and text_color:
                block.style.fill = text_color
                block.style.stroke_width = 0
            blocks.append(block)

    return blocks
