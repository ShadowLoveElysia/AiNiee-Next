from __future__ import annotations

from dataclasses import dataclass


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
    prepared_lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            prepared_lines.append("")
            continue
        prepared_lines.extend(list(paragraph))
    return "\n".join(prepared_lines)


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
    x1, y1, x2, y2 = [int(value) for value in bbox]
    available_width = max(1, x2 - x1)
    available_height = max(1, y2 - y1)

    normalized_text = text.strip()
    if not normalized_text:
        return []

    if direction == "vertical":
        normalized_text = _prepare_text_for_vertical(normalized_text)

    raw_lines = _wrap_horizontal(draw, normalized_text, available_width, font, stroke_width)
    sample_height = max(1, _measure_text(draw, "Ag", font, stroke_width)[1] or int(getattr(font, "size", 20)))
    line_gap = max(0, int(sample_height * max(0.0, float(line_spacing) - 1.0)))
    line_height = sample_height + line_gap
    max_lines = max(1, available_height // max(1, line_height))
    if len(raw_lines) > max_lines and not allow_truncate:
        return []

    lines = list(raw_lines[:max_lines])
    if raw_lines and len(raw_lines) > max_lines:
        lines[-1] = _truncate_line(draw, lines[-1], available_width, font, stroke_width)

    measured_lines: list[tuple[str, int, int]] = []
    for line in lines:
        width, height = _measure_text(draw, line or " ", font, stroke_width)
        measured_lines.append((line, width, max(sample_height, height)))

    total_height = sum(height for _line, _width, height in measured_lines) + max(0, len(measured_lines) - 1) * line_gap
    current_y = y1 + max(0, int((available_height - total_height) / 2))

    positioned: list[PositionedTextLine] = []
    for line, width, height in measured_lines:
        current_x = x1 + max(0, int((available_width - width) / 2))
        positioned.append(PositionedTextLine(text=line, x=current_x, y=current_y))
        current_y += height + line_gap
    return positioned
