from __future__ import annotations

from dataclasses import dataclass

from ModuleFolders.MangaCore.render.layoutPlan import LayoutPlan, PositionedTextRun


@dataclass(slots=True)
class PositionedTextLine:
    text: str
    x: int
    y: int


def _measure_text(draw, text: str, font, stroke_width: int) -> tuple[int, int]:
    if not text:
        return 0, 0
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return max(0, right - left), max(0, bottom - top)


def _truncate_line(draw, text: str, max_width: int, font, stroke_width: int) -> str:
    if not text:
        return ""
    if _measure_text(draw, text, font, stroke_width)[0] <= max_width:
        return text

    ellipsis = "..."
    candidate = text
    while candidate:
        candidate = candidate[:-1]
        preview = candidate + ellipsis
        if _measure_text(draw, preview, font, stroke_width)[0] <= max_width:
            return preview
    return ellipsis


def _wrap_horizontal(draw, text: str, max_width: int, font, stroke_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue

        current = ""
        for character in paragraph:
            candidate = f"{current}{character}"
            if current and _measure_text(draw, candidate, font, stroke_width)[0] > max_width:
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines or [text]


def _prepare_text_for_vertical(text: str) -> str:
    prepared = []
    for paragraph in text.splitlines() or [""]:
        prepared.extend(character for character in paragraph.strip() if not character.isspace())
    return "".join(prepared)


def _vertical_text_runs(
    draw,
    text: str,
    bbox: tuple[int, int, int, int] | list[int],
    font,
    line_spacing: float,
    stroke_width: int,
) -> tuple[list[PositionedTextLine], int, list[str]]:
    x1, y1, x2, y2 = [int(value) for value in bbox]
    available_width = max(1, x2 - x1)
    available_height = max(1, y2 - y1)
    characters = list(_prepare_text_for_vertical(text))
    if not characters:
        return [], 0, []

    sample_width, sample_height = _measure_text(draw, "漢", font, stroke_width)
    sample_width = max(1, sample_width or int(getattr(font, "size", 20)))
    sample_height = max(1, sample_height or int(getattr(font, "size", 20)))
    row_gap = max(0, int(sample_height * max(0.0, float(line_spacing) - 1.0)))
    column_gap = max(2, int(sample_width * 0.22))
    row_pitch = sample_height + row_gap
    column_pitch = sample_width + column_gap
    max_rows = max(1, (available_height + row_gap) // max(1, row_pitch))
    required_columns = max(1, (len(characters) + max_rows - 1) // max_rows)
    max_columns = max(1, (available_width + column_gap) // max(1, column_pitch))

    warnings: list[str] = []
    if required_columns > max_columns:
        return [], column_gap, ["layout_overflow"]

    used_width = required_columns * sample_width + max(0, required_columns - 1) * column_gap
    start_x = x1 + max(0, int((available_width - used_width) / 2)) + (required_columns - 1) * column_pitch

    positioned: list[PositionedTextLine] = []
    for index, character in enumerate(characters):
        column_index = index // max_rows
        row_index = index % max_rows
        char_width, char_height = _measure_text(draw, character, font, stroke_width)
        char_width = max(1, char_width)
        char_height = max(1, char_height)
        column_x = int(start_x - column_index * column_pitch + max(0, (sample_width - char_width) / 2))
        y = y1 + row_index * row_pitch
        positioned.append(PositionedTextLine(text=character, x=column_x, y=int(y)))

    used_height = min(max_rows, len(characters)) * sample_height + max(0, min(max_rows, len(characters)) - 1) * row_gap
    y_offset = max(0, int((available_height - used_height) / 2))
    if y_offset:
        positioned = [
            PositionedTextLine(text=run.text, x=run.x, y=run.y + y_offset)
            for run in positioned
        ]
    return positioned, column_gap, warnings


def _horizontal_text_runs(
    draw,
    text: str,
    bbox: tuple[int, int, int, int] | list[int],
    font,
    line_spacing: float,
    stroke_width: int,
    allow_truncate: bool,
) -> tuple[list[PositionedTextLine], list[str]]:
    x1, y1, x2, y2 = [int(value) for value in bbox]
    available_width = max(1, x2 - x1)
    available_height = max(1, y2 - y1)

    raw_lines = _wrap_horizontal(draw, text, available_width, font, stroke_width)
    sample_height = max(1, _measure_text(draw, "Ag", font, stroke_width)[1] or int(getattr(font, "size", 20)))
    line_gap = max(0, int(sample_height * max(0.0, float(line_spacing) - 1.0)))
    line_height = sample_height + line_gap
    max_lines = max(1, available_height // max(1, line_height))
    if len(raw_lines) > max_lines and not allow_truncate:
        return [], ["layout_overflow"]

    warnings: list[str] = []
    lines = list(raw_lines[:max_lines])
    if raw_lines and len(raw_lines) > max_lines:
        lines[-1] = _truncate_line(draw, lines[-1], available_width, font, stroke_width)
        warnings.append("layout_truncated")

    measured_lines: list[tuple[str, int, int]] = []
    for line in lines:
        width, height = _measure_text(draw, line or " ", font, stroke_width)
        measured_lines.append((line, width, max(sample_height, height)))

    total_height = sum(height for _line, _width, height in measured_lines) + max(0, len(measured_lines) - 1) * line_gap
    current_y = y1 + max(0, int((available_height - total_height) / 2))
    max_line_width = max((width for _line, width, _height in measured_lines), default=0)
    common_x = x1 + max(0, int((available_width - max_line_width) / 2))

    positioned: list[PositionedTextLine] = []
    for line, width, height in measured_lines:
        positioned.append(PositionedTextLine(text=line, x=common_x, y=current_y))
        current_y += height + line_gap
    return positioned, warnings


def plan_text_lines(
    draw,
    text: str,
    bbox: tuple[int, int, int, int] | list[int],
    font,
    line_spacing: float,
    stroke_width: int,
    direction: str = "horizontal",
    allow_truncate: bool = True,
) -> list[PositionedTextLine]:
    normalized_text = text.strip()
    if not normalized_text:
        return []

    if direction == "vertical":
        lines, _column_gap, _warnings = _vertical_text_runs(
            draw,
            normalized_text,
            bbox,
            font,
            line_spacing,
            stroke_width,
        )
        return lines

    lines, _warnings = _horizontal_text_runs(
        draw,
        normalized_text,
        bbox,
        font,
        line_spacing,
        stroke_width,
        allow_truncate,
    )
    return lines


def build_layout_plan(
    *,
    draw,
    block_id: str,
    text: str,
    bbox: tuple[int, int, int, int] | list[int],
    font,
    font_family: str,
    font_size: int,
    line_spacing: float,
    stroke_width: int,
    direction: str = "horizontal",
    allow_truncate: bool = False,
) -> LayoutPlan:
    normalized_text = text.strip()
    normalized_bbox = tuple(int(value) for value in bbox)
    if not normalized_text:
        return LayoutPlan(
            block_id=block_id,
            direction=direction,
            bbox=normalized_bbox,  # type: ignore[arg-type]
            font_family=font_family,
            font_size=font_size,
            line_spacing=line_spacing,
            fit_ok=False,
            warnings=["empty_text"],
        )

    if direction == "vertical":
        lines, column_gap, warnings = _vertical_text_runs(
            draw,
            normalized_text,
            normalized_bbox,
            font,
            line_spacing,
            stroke_width,
        )
    else:
        lines, warnings = _horizontal_text_runs(
            draw,
            normalized_text,
            normalized_bbox,
            font,
            line_spacing,
            stroke_width,
            allow_truncate,
        )
        column_gap = 0

    fit_ok = bool(lines) and "layout_overflow" not in warnings and "layout_truncated" not in warnings
    score = float(len(lines))
    if fit_ok:
        score += float(font_size)
    return LayoutPlan(
        block_id=block_id,
        direction=direction,
        bbox=normalized_bbox,  # type: ignore[arg-type]
        font_family=font_family,
        font_size=font_size,
        line_spacing=line_spacing,
        column_spacing=column_gap,
        runs=[PositionedTextRun(text=line.text, x=line.x, y=line.y) for line in lines],
        fit_ok=fit_ok,
        score=score,
        warnings=warnings,
    )
