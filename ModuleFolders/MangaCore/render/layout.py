from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from ModuleFolders.MangaCore.render.layoutPlan import LayoutPlan, PositionedTextRun


_HORIZONTAL_FORBID_LINE_START = frozenset(
    "!),.:;?]}¢°·"
    "、。，．，：；？！"
    "）］｝〕〉》」』】〙〗〟"
    "’”"
    "…"
)
_HORIZONTAL_FORBID_LINE_END = frozenset("([{£¥‘“（［｛〔〈《「『【〘〖")
_LATIN_WORD_CONNECTORS = frozenset("'_-")
_NUMERIC_CONNECTORS = frozenset(".,")
_CJK_NUMERIC_PREFIXES = frozenset("第约共")
_CJK_NUMERIC_SUFFIXES = frozenset(
    "%％页章话卷集回部季年年月日号点分秒元角岁个张次人倍米厘米毫米公里千克克"
)
_VERTICAL_CENTERED_PUNCTUATION = frozenset("，。、｡､．.：；！？!?…·・")
_VERTICAL_ROTATE_CLOCKWISE_CHARS = frozenset("-‐‑‒–—―~～〜…·・ー")


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


def _is_latin_word_core(character: str) -> bool:
    if character.isascii():
        return character.isalnum()
    if character.isdigit():
        return True
    return "LATIN" in unicodedata.name(character, "")


def _is_cjk_text_character(character: str) -> bool:
    if not character:
        return False
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2A6DF
        or 0x2A700 <= codepoint <= 0x2B73F
        or 0x2B740 <= codepoint <= 0x2B81F
        or 0x2B820 <= codepoint <= 0x2CEAF
        or 0x2CEB0 <= codepoint <= 0x2EBEF
        or 0x30000 <= codepoint <= 0x3134F
    )


def _consume_latin_word(paragraph: str, index: int) -> int:
    index += 1
    while index < len(paragraph):
        current = paragraph[index]
        previous = paragraph[index - 1]
        if _is_latin_word_core(current):
            index += 1
            continue
        if (
            current in _LATIN_WORD_CONNECTORS
            and index + 1 < len(paragraph)
            and _is_latin_word_core(paragraph[index + 1])
        ):
            index += 1
            continue
        if (
            current in _NUMERIC_CONNECTORS
            and previous.isdigit()
            and index + 1 < len(paragraph)
            and paragraph[index + 1].isdigit()
        ):
            index += 1
            continue
        break
    return index


def _consume_numeric_suffix(paragraph: str, index: int) -> int:
    while index < len(paragraph) and paragraph[index] in _CJK_NUMERIC_SUFFIXES:
        index += 1
    return index


def _tokenize_horizontal_paragraph(paragraph: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(paragraph):
        character = paragraph[index]
        if character.isspace():
            while index < len(paragraph) and paragraph[index].isspace():
                index += 1
            tokens.append(" ")
            continue

        if (
            character in _CJK_NUMERIC_PREFIXES
            and index + 1 < len(paragraph)
            and _is_latin_word_core(paragraph[index + 1])
        ):
            start = index
            index = _consume_latin_word(paragraph, index + 1)
            index = _consume_numeric_suffix(paragraph, index)
            tokens.append(paragraph[start:index])
            continue

        if _is_latin_word_core(character):
            start = index
            index = _consume_latin_word(paragraph, index)
            if any(character.isdigit() for character in paragraph[start:index]):
                index = _consume_numeric_suffix(paragraph, index)
            tokens.append(paragraph[start:index])
            continue

        tokens.append(character)
        index += 1
    return tokens


def _split_overlong_token(draw, token: str, max_width: int, font, stroke_width: int) -> list[str]:
    if not token or _measure_text(draw, token, font, stroke_width)[0] <= max_width:
        return [token]

    chunks: list[str] = []
    current = ""
    for character in token:
        candidate = f"{current}{character}"
        if current and _measure_text(draw, candidate, font, stroke_width)[0] > max_width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [token]


def _split_forbidden_line_end_suffix(line: str) -> tuple[str, str]:
    stripped = line.rstrip()
    suffix_start = len(stripped)
    while suffix_start > 0 and stripped[suffix_start - 1] in _HORIZONTAL_FORBID_LINE_END:
        suffix_start -= 1
    if suffix_start == len(stripped):
        return stripped, ""
    return stripped[:suffix_start], stripped[suffix_start:]


def _append_horizontal_line(lines: list[str], line: str) -> None:
    stripped = line.rstrip()
    if stripped:
        lines.append(stripped)


def _horizontal_line_text(tokens: list[str], start: int, end: int) -> str:
    return "".join(tokens[start:end]).strip()


def _trailing_forbidden_start_width(draw, line: str, font, stroke_width: int) -> int:
    suffix_start = len(line)
    while suffix_start > 0 and line[suffix_start - 1] in _HORIZONTAL_FORBID_LINE_START:
        suffix_start -= 1
    if suffix_start == len(line):
        return 0
    return _measure_text(draw, line[suffix_start:], font, stroke_width)[0]


def _line_width_allowed(draw, line: str, max_width: int, font, stroke_width: int) -> int:
    return max_width + _trailing_forbidden_start_width(draw, line, font, stroke_width)


def _cjk_core_count(line: str) -> int:
    return sum(1 for character in line if _is_cjk_text_character(character))


def _horizontal_line_break_cost(
    line: str,
    width: int,
    max_width: int,
    *,
    is_last: bool,
    paragraph_cjk_count: int,
    can_fit_two_cjk: bool,
) -> float:
    visible_count = sum(1 for character in line if not character.isspace())
    cjk_count = _cjk_core_count(line)
    effective_width = min(width, max_width)
    unused_ratio = max(0.0, (max_width - effective_width) / max(1, max_width))
    cost = 2000.0
    cost += unused_ratio * unused_ratio * (18.0 if is_last else 90.0)

    if can_fit_two_cjk and paragraph_cjk_count > 1 and cjk_count == 1:
        cost += 9000.0 if is_last else 5500.0
    if can_fit_two_cjk and paragraph_cjk_count > 2 and visible_count == 1:
        cost += 4000.0
    if line[:1] in _HORIZONTAL_FORBID_LINE_END and len(line) == 1:
        cost += 1500.0
    return cost


def _wrap_horizontal_paragraph(
    draw,
    paragraph: str,
    max_width: int,
    font,
    stroke_width: int,
) -> list[str]:
    tokens = [
        split_token
        for token in _tokenize_horizontal_paragraph(paragraph)
        for split_token in _split_overlong_token(draw, token, max_width, font, stroke_width)
    ]
    tokens = [token for token in tokens if token]
    if not tokens:
        return []

    paragraph_cjk_count = sum(_cjk_core_count(token) for token in tokens)
    can_fit_two_cjk = _measure_text(draw, "漢漢", font, stroke_width)[0] <= max_width
    line_cache: dict[tuple[int, int], str] = {}
    width_cache: dict[str, int] = {}

    def line_text(start: int, end: int) -> str:
        key = (start, end)
        if key not in line_cache:
            line_cache[key] = _horizontal_line_text(tokens, start, end)
        return line_cache[key]

    def line_width(line: str) -> int:
        if line not in width_cache:
            width_cache[line] = _measure_text(draw, line, font, stroke_width)[0]
        return width_cache[line]

    token_count = len(tokens)
    best_cost = [float("inf")] * (token_count + 1)
    best_next: list[int | None] = [None] * (token_count + 1)
    best_cost[token_count] = 0.0

    for start in range(token_count - 1, -1, -1):
        for end in range(start + 1, token_count + 1):
            line = line_text(start, end)
            if not line:
                continue
            is_last = end == token_count
            if start > 0 and line[:1] in _HORIZONTAL_FORBID_LINE_START:
                continue
            if not is_last and line[-1:] in _HORIZONTAL_FORBID_LINE_END:
                continue

            width = line_width(line)
            if width > _line_width_allowed(draw, line, max_width, font, stroke_width):
                break
            if best_next[end] is None and end != token_count:
                continue

            candidate_cost = best_cost[end] + _horizontal_line_break_cost(
                line,
                width,
                max_width,
                is_last=is_last,
                paragraph_cjk_count=paragraph_cjk_count,
                can_fit_two_cjk=can_fit_two_cjk,
            )
            if candidate_cost < best_cost[start]:
                best_cost[start] = candidate_cost
                best_next[start] = end

    if best_next[0] is None:
        return _wrap_horizontal_paragraph_greedy(draw, tokens, max_width, font, stroke_width)

    wrapped_lines: list[str] = []
    start = 0
    while start < token_count:
        end = best_next[start]
        if end is None:
            return _wrap_horizontal_paragraph_greedy(draw, tokens, max_width, font, stroke_width)
        _append_horizontal_line(wrapped_lines, line_text(start, end))
        start = end
    return wrapped_lines


def _wrap_horizontal_paragraph_greedy(
    draw,
    paragraph_tokens: list[str],
    max_width: int,
    font,
    stroke_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in paragraph_tokens:
        if token == " " and not current:
            continue

        candidate = f"{current}{token}"
        if current and _measure_text(draw, candidate, font, stroke_width)[0] > max_width:
            if token[:1] in _HORIZONTAL_FORBID_LINE_START:
                current = candidate
                continue

            prefix, suffix = _split_forbidden_line_end_suffix(current)
            if suffix:
                if prefix:
                    _append_horizontal_line(lines, prefix)
                    current = f"{suffix}{token.lstrip()}"
                else:
                    current = candidate
                continue

            _append_horizontal_line(lines, current)
            current = token.lstrip()
        else:
            current = candidate
    if current:
        _append_horizontal_line(lines, current)
    return lines


def _wrap_horizontal(draw, text: str, max_width: int, font, stroke_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue

        lines.extend(_wrap_horizontal_paragraph(draw, paragraph, max_width, font, stroke_width))
    return lines or [text]


def _prepare_text_for_vertical(text: str) -> str:
    prepared = []
    for paragraph in text.splitlines() or [""]:
        prepared.extend(character for character in paragraph.strip() if not character.isspace())
    return "".join(prepared)


def _is_vertical_ascii_unit_character(character: str) -> bool:
    return character.isascii() and character.isalnum()


def _split_vertical_ascii_sequence(
    draw,
    sequence: str,
    max_inline_width: int,
    font,
    stroke_width: int,
) -> list[str]:
    if len(sequence) <= 2 and _measure_text(draw, sequence, font, stroke_width)[0] <= max_inline_width:
        return [sequence]

    units: list[str] = []
    index = 0
    while index < len(sequence):
        chunk = sequence[index : index + 2]
        if len(chunk) == 2 and _measure_text(draw, chunk, font, stroke_width)[0] <= max_inline_width:
            units.append(chunk)
            index += 2
        else:
            units.append(sequence[index])
            index += 1
    return units


def _vertical_text_units(
    draw,
    prepared_text: str,
    max_inline_width: int,
    font,
    stroke_width: int,
) -> list[str]:
    units: list[str] = []
    index = 0
    while index < len(prepared_text):
        character = prepared_text[index]
        if _is_vertical_ascii_unit_character(character):
            start = index
            index += 1
            while index < len(prepared_text) and _is_vertical_ascii_unit_character(prepared_text[index]):
                index += 1
            units.extend(
                _split_vertical_ascii_sequence(
                    draw,
                    prepared_text[start:index],
                    max_inline_width,
                    font,
                    stroke_width,
                )
            )
            continue
        units.append(character)
        index += 1
    return units


def _vertical_character_draw_position(
    draw,
    text: str,
    cell_x: int,
    cell_y: int,
    sample_width: int,
    sample_height: int,
    font,
    stroke_width: int,
) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    char_width = max(1, right - left)
    char_height = max(1, bottom - top)

    if len(text) > 1:
        return (
            int(cell_x + (sample_width - char_width) / 2 - left),
            int(cell_y + (sample_height - char_height) / 2 - top),
        )

    if text in _VERTICAL_ROTATE_CLOCKWISE_CHARS:
        rotated_width = char_height
        rotated_height = char_width
        return (
            int(cell_x + max(0, (sample_width - rotated_width) / 2)),
            int(cell_y + (sample_height - rotated_height) / 2),
        )

    x = int(cell_x + max(0, (sample_width - char_width) / 2))
    if text in _VERTICAL_CENTERED_PUNCTUATION:
        return x, int(cell_y + (sample_height - char_height) / 2 - top)
    return x, int(cell_y)


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
    prepared_text = _prepare_text_for_vertical(text)
    if not prepared_text:
        return [], 0, []

    sample_width, sample_height = _measure_text(draw, "漢", font, stroke_width)
    sample_width = max(1, sample_width or int(getattr(font, "size", 20)))
    sample_height = max(1, sample_height or int(getattr(font, "size", 20)))
    row_gap = max(0, int(sample_height * max(0.0, float(line_spacing) - 1.0)))
    column_gap = max(2, int(sample_width * 0.22))
    row_pitch = sample_height + row_gap
    column_pitch = sample_width + column_gap
    characters = _vertical_text_units(draw, prepared_text, column_pitch, font, stroke_width)
    if not characters:
        return [], column_gap, []
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
        cell_x = int(start_x - column_index * column_pitch)
        cell_y = int(y1 + row_index * row_pitch)
        char_x, char_y = _vertical_character_draw_position(
            draw,
            character,
            cell_x,
            cell_y,
            sample_width,
            sample_height,
            font,
            stroke_width,
        )
        positioned.append(PositionedTextLine(text=character, x=char_x, y=char_y))

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
