from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.font import load_font
from ModuleFolders.MangaCore.render.layout import build_layout_plan
from ModuleFolders.MangaCore.render.layoutPlan import LayoutPlan
from ModuleFolders.MangaCore.render.templates import get_render_template
from ModuleFolders.MangaCore.render.textNormalize import normalize_manga_dialogue_for_layout

ROTATE_CLOCKWISE_VERTICAL_CHARS = frozenset("-‐‑‒–—―~～〜…·・ー")
SOURCE_FONT_SCALE_TOO_SMALL = 0.65
SOURCE_FONT_SCALE_TOO_LARGE = 1.35


def _resolve_base_layer(session: MangaProjectSession, page: MangaPage, preset: str) -> Path:
    template = get_render_template(preset)
    base_layer_name = str(template.get("base_layer", "inpainted"))
    relative_path = getattr(page.layers, base_layer_name, "") or page.layers.source
    base_path = session.project_path / relative_path
    if not base_path.exists():
        base_path = session.project_path / page.layers.source
    return base_path


def _apply_restore_mask(session: MangaProjectSession, page: MangaPage, canvas: Image.Image) -> Image.Image:
    restore_relative_path = getattr(page.masks, "restore", "")
    if not restore_relative_path:
        return canvas
    restore_path = session.project_path / restore_relative_path
    source_path = session.project_path / page.layers.source
    if not restore_path.exists() or not source_path.exists():
        return canvas
    with Image.open(restore_path) as mask_image:
        restore_mask = mask_image.convert("L")
        if restore_mask.size != canvas.size:
            restore_mask = restore_mask.resize(canvas.size, resample=Image.Resampling.NEAREST)
    if not restore_mask.getbbox():
        return canvas
    with Image.open(source_path) as source_image:
        source = source_image.convert("RGBA")
        if source.size != canvas.size:
            source = source.resize(canvas.size, resample=Image.Resampling.BICUBIC)
    return Image.composite(source, canvas, restore_mask)


class MangaRenderer:
    def __init__(self, *, use_source_text_fallback: bool = False) -> None:
        self.use_source_text_fallback = use_source_text_fallback
        self.last_layout_plans: list[LayoutPlan] = []

    def render_page(self, session: MangaProjectSession, page: MangaPage, *, write_final: bool = True) -> Path:
        template = get_render_template(session.scene.render_preset)
        base_path = _resolve_base_layer(session, page, session.scene.render_preset)
        rendered_path = session.project_path / page.layers.rendered
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_layout_plans = []

        with Image.open(base_path) as source_image:
            canvas = source_image.convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        for block in sorted(page.text_blocks, key=lambda current: (current.bbox[1], current.bbox[0])):
            text = str(block.translation or "").strip()
            if not text and (self.use_source_text_fallback or bool(template.get("use_source_text_fallback", False))):
                text = str(block.source_text or "").strip()
            if not text:
                continue

            text = normalize_manga_dialogue_for_layout(text, direction=block.rendered_direction)
            if not text:
                continue

            font, plan = self._fit_block_text(draw, block, text)
            self._apply_source_font_diagnostics(block, plan)
            self.last_layout_plans.append(plan)
            block.style.font_size = plan.font_size
            block.rendered_direction = plan.direction
            block.flags = _merge_layout_flags(block.flags, plan)
            for line in plan.runs:
                line.rotate_clockwise = _should_rotate_clockwise(plan.direction, line.text)
                if line.rotate_clockwise:
                    _draw_rotated_text(
                        canvas,
                        line.text,
                        line.x,
                        line.y,
                        font=font,
                        fill=block.style.fill,
                        stroke_fill=block.style.stroke_color,
                        stroke_width=block.style.stroke_width,
                    )
                else:
                    draw.text(
                        (line.x, line.y),
                        line.text,
                        font=font,
                        fill=block.style.fill,
                        stroke_fill=block.style.stroke_color,
                        stroke_width=block.style.stroke_width,
                    )

        canvas = _apply_restore_mask(session, page, canvas)
        canvas.save(rendered_path, format="PNG")

        if write_final:
            final_path = session.output_root / "final" / "pages" / f"{page.index:04d}.png"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered_path, final_path)
        return rendered_path

    def _fit_block_text(self, draw, block, text: str):
        x1, y1, x2, y2 = [int(value) for value in block.bbox]
        box_width = max(1, x2 - x1)
        box_height = max(1, y2 - y1)
        base_size = self._estimate_base_font_size(block, text, box_width, box_height)
        initial_size = max(10, int(block.style.font_size))
        min_size = max(10, min(22, int(base_size * 0.58)))

        last_font = load_font(
            size=base_size,
            font_family=block.style.font_family,
            font_prediction=block.font_prediction,
        )
        last_plan: LayoutPlan | None = None
        for size in range(base_size, min_size - 1, -2):
            font = load_font(
                size=size,
                font_family=block.style.font_family,
                font_prediction=block.font_prediction,
            )
            plan = build_layout_plan(
                draw=draw,
                block_id=block.block_id,
                text=text,
                bbox=block.bbox,
                font=font,
                font_family=block.style.font_family,
                font_size=size,
                line_spacing=block.style.line_spacing,
                stroke_width=block.style.stroke_width,
                direction=block.rendered_direction,
                allow_truncate=False,
            )
            if plan.fit_ok:
                plan.initial_font_size = initial_size
                return font, plan
            last_font = font
            last_plan = plan

        fallback_plan = build_layout_plan(
            draw=draw,
            block_id=block.block_id,
            text=text,
            bbox=block.bbox,
            font=last_font,
            font_family=block.style.font_family,
            font_size=max(min_size, int(getattr(last_font, "size", min_size))),
            line_spacing=block.style.line_spacing,
            stroke_width=block.style.stroke_width,
            direction=block.rendered_direction,
            allow_truncate=block.rendered_direction != "vertical",
        )
        if not fallback_plan.runs and last_plan is not None:
            fallback_plan = last_plan
        if fallback_plan.font_size <= min_size:
            fallback_plan.warnings = sorted({*fallback_plan.warnings, "font_too_small"})
            fallback_plan.fit_ok = False
        fallback_plan.initial_font_size = initial_size
        return last_font, fallback_plan

    @staticmethod
    def _estimate_base_font_size(block, text: str, box_width: int, box_height: int) -> int:
        configured_size = max(10, int(block.style.font_size))
        source_char_size = _source_char_size_from_block(block)
        if block.rendered_direction == "vertical":
            length = max(1, len("".join(text.split())))
            rough_columns = max(1, min(4, int((length + 9) / 10)))
            by_width = int(box_width / max(1.0, rough_columns * 1.15))
            by_height = int(box_height / max(1.0, min(length, 10) * 1.15))
            geometric = max(12, min(by_width, by_height, int(min(box_width, box_height) * 0.72)))
            if source_char_size > 0:
                source_target = int(source_char_size * 0.95)
                source_limited = min(max(source_target, geometric), int(source_char_size * 1.18))
                return max(12, min(72, max(configured_size, source_limited)))
            return max(12, min(72, max(configured_size, geometric)))

        length = max(1, len(text.replace("\n", "")))
        rough_lines = max(1, min(4, int((length + 8) / 9)))
        by_height = int(box_height / max(1.0, rough_lines * 1.25))
        geometric = max(12, min(by_height, int(min(box_width, box_height) * 0.58)))
        if source_char_size > 0:
            source_target = int(source_char_size * 0.92)
            source_limited = min(max(source_target, geometric), int(source_char_size * 1.16))
            return max(12, min(72, max(configured_size, source_limited)))
        return max(12, min(72, max(configured_size, geometric)))

    def render_session(self, session: MangaProjectSession) -> list[Path]:
        rendered: list[Path] = []
        for page_ref in session.scene.pages:
            rendered.append(self.render_page(session, session.pages[page_ref.page_id]))
        return rendered

    @staticmethod
    def _apply_source_font_diagnostics(block, plan: LayoutPlan) -> None:
        source_char_size = _source_char_size_from_block(block)
        plan.source_char_size_px = source_char_size
        plan.source_char_size_confidence = _source_char_size_confidence_from_block(block)
        if not plan.initial_font_size:
            plan.initial_font_size = max(10, int(block.style.font_size))
        if source_char_size <= 0:
            return

        plan.font_scale_ratio = round(float(plan.font_size) / max(1.0, float(source_char_size)), 4)
        warnings = set(plan.warnings)
        if plan.source_char_size_confidence and plan.source_char_size_confidence < 0.5:
            warnings.add("source_char_size_unreliable")
        if plan.font_scale_ratio < SOURCE_FONT_SCALE_TOO_SMALL:
            warnings.add("font_scaled_too_small")
            warnings.add("font_scaled_down_from_source")
        elif plan.font_scale_ratio > SOURCE_FONT_SCALE_TOO_LARGE:
            warnings.add("font_scaled_too_large")
        plan.warnings = sorted(warnings)
        if "font_scaled_too_small" in warnings or "font_scaled_too_large" in warnings:
            plan.fit_ok = False


def _merge_layout_flags(flags: list[str], plan: LayoutPlan) -> list[str]:
    preserved = [
        flag
        for flag in flags
        if not (
            flag.startswith("layout_")
            or flag.startswith("fit_ok:")
            or flag.startswith("rendered_font_size:")
            or flag.startswith("font_scale_ratio:")
            or flag in {"font_too_small", "empty_text"}
        )
    ]
    preserved.append(f"fit_ok:{str(plan.fit_ok).lower()}")
    preserved.append(f"rendered_font_size:{plan.font_size}")
    if plan.font_scale_ratio:
        preserved.append(f"font_scale_ratio:{plan.font_scale_ratio:.2f}")
    for warning in plan.warnings:
        if warning not in preserved:
            preserved.append(warning)
    return preserved


def _source_char_size_from_block(block) -> int:
    metrics = getattr(block, "source_metrics", {})
    if not isinstance(metrics, dict):
        return 0
    try:
        return max(0, int(metrics.get("source_char_size_px", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _source_char_size_confidence_from_block(block) -> float:
    metrics = getattr(block, "source_metrics", {})
    if not isinstance(metrics, dict):
        return 0.0
    try:
        return max(0.0, min(1.0, float(metrics.get("source_char_size_confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _should_rotate_clockwise(direction: str, text: str) -> bool:
    return direction == "vertical" and len(text) == 1 and text in ROTATE_CLOCKWISE_VERTICAL_CHARS


def _draw_rotated_text(
    canvas: Image.Image,
    text: str,
    x: int,
    y: int,
    *,
    font,
    fill: str,
    stroke_fill: str,
    stroke_width: int,
) -> None:
    scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    scratch_draw = ImageDraw.Draw(scratch)
    left, top, right, bottom = scratch_draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    width = max(1, right - left)
    height = max(1, bottom - top)
    glyph = Image.new("RGBA", (width + stroke_width * 4, height + stroke_width * 4), (0, 0, 0, 0))
    glyph_draw = ImageDraw.Draw(glyph)
    glyph_draw.text(
        (stroke_width * 2 - left, stroke_width * 2 - top),
        text,
        font=font,
        fill=fill,
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )
    rotated = glyph.rotate(-90, expand=True, resample=Image.Resampling.BICUBIC)
    paste_x = int(x - max(0, (rotated.width - width) / 2))
    paste_y = int(y + max(0, (height - rotated.height) / 2))
    canvas.alpha_composite(rotated, dest=(paste_x, paste_y))
