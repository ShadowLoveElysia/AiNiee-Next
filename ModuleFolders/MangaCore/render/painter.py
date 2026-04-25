from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.font import load_font
from ModuleFolders.MangaCore.render.layout import plan_text_lines
from ModuleFolders.MangaCore.render.templates import get_render_template


def _resolve_base_layer(session: MangaProjectSession, page: MangaPage, preset: str) -> Path:
    template = get_render_template(preset)
    base_layer_name = str(template.get("base_layer", "inpainted"))
    relative_path = getattr(page.layers, base_layer_name, "") or page.layers.source
    base_path = session.project_path / relative_path
    if not base_path.exists():
        base_path = session.project_path / page.layers.source
    return base_path


class MangaRenderer:
    def __init__(self, *, use_source_text_fallback: bool = False) -> None:
        self.use_source_text_fallback = use_source_text_fallback

    def render_page(self, session: MangaProjectSession, page: MangaPage) -> Path:
        template = get_render_template(session.scene.render_preset)
        base_path = _resolve_base_layer(session, page, session.scene.render_preset)
        rendered_path = session.project_path / page.layers.rendered
        rendered_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(base_path) as source_image:
            canvas = source_image.convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        for block in sorted(page.text_blocks, key=lambda current: (current.bbox[1], current.bbox[0])):
            text = str(block.translation or "").strip()
            if not text and (self.use_source_text_fallback or bool(template.get("use_source_text_fallback", False))):
                text = str(block.source_text or "").strip()
            if not text:
                continue

            font = load_font(
                size=block.style.font_size,
                font_family=block.style.font_family,
                font_prediction=block.font_prediction,
            )
            lines = plan_text_lines(
                draw=draw,
                text=text,
                bbox=block.bbox,
                font=font,
                line_spacing=block.style.line_spacing,
                stroke_width=block.style.stroke_width,
                direction=block.rendered_direction,
            )
            for line in lines:
                draw.text(
                    (line.x, line.y),
                    line.text,
                    font=font,
                    fill=block.style.fill,
                    stroke_fill=block.style.stroke_color,
                    stroke_width=block.style.stroke_width,
                )

        canvas.save(rendered_path, format="PNG")

        final_path = session.output_root / "final" / "pages" / f"{page.index:04d}.png"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_path, final_path)
        return rendered_path

    def render_session(self, session: MangaProjectSession) -> list[Path]:
        rendered: list[Path] = []
        for page_ref in session.scene.pages:
            rendered.append(self.render_page(session, session.pages[page_ref.page_id]))
        return rendered
