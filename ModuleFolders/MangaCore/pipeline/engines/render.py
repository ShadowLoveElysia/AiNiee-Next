from __future__ import annotations

from dataclasses import dataclass

from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.painter import MangaRenderer
from ModuleFolders.MangaCore.render.templates import get_render_template

DEFAULT_RENDER_ENGINE_ID = "mangacore-pil-renderer"
RUNTIME_RENDER_ENGINE_ID = "pil-image-draw"


@dataclass(slots=True)
class RenderResult:
    ok: bool = True
    configured_engine_id: str = DEFAULT_RENDER_ENGINE_ID
    runtime_engine_id: str = RUNTIME_RENDER_ENGINE_ID
    page_id: str = ""
    rendered_path: str = ""
    final_path: str = ""
    rendered_blocks: int = 0
    skipped_blocks: int = 0
    layout_fit_failed_blocks: int = 0
    layout_warnings: list[dict[str, object]] | None = None
    layout_plans: list[dict[str, object]] | None = None
    final_written: bool = True
    error_message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "configured_engine_id": self.configured_engine_id,
            "runtime_engine_id": self.runtime_engine_id,
            "page_id": self.page_id,
            "rendered_path": self.rendered_path,
            "final_path": self.final_path,
            "rendered_blocks": self.rendered_blocks,
            "skipped_blocks": self.skipped_blocks,
            "layout_fit_failed_blocks": self.layout_fit_failed_blocks,
            "layout_warnings": list(self.layout_warnings or []),
            "layout_plans": list(self.layout_plans or []),
            "final_written": self.final_written,
            "error_message": self.error_message,
        }


class RenderEngine:
    stage = "render"

    def __init__(
        self,
        engine_id: str | None = None,
        renderer: MangaRenderer | None = None,
    ) -> None:
        self.engine_id = str(engine_id or DEFAULT_RENDER_ENGINE_ID)
        self.renderer = renderer or MangaRenderer()

    def configure(self, engine_id: str | None = None) -> None:
        if engine_id:
            self.engine_id = str(engine_id)

    def describe(self) -> dict[str, object]:
        return {
            "configured_engine_id": self.engine_id,
            "runtime_engine_id": RUNTIME_RENDER_ENGINE_ID,
            "supported_engine_ids": [DEFAULT_RENDER_ENGINE_ID],
        }

    def run_page(self, session: MangaProjectSession, page: MangaPage, *, write_final: bool = True) -> RenderResult:
        rendered_path = self.renderer.render_page(session, page, write_final=write_final)
        final_path = session.output_root / "final" / "pages" / f"{page.index:04d}.png"
        rendered_blocks, skipped_blocks = self._count_rendered_blocks(session, page)
        layout_plans = [plan.to_dict() for plan in self.renderer.last_layout_plans]
        layout_warnings = [
            {
                "block_id": plan.block_id,
                "warnings": list(plan.warnings),
                "fit_ok": plan.fit_ok,
                "font_size": plan.font_size,
                "direction": plan.direction,
            }
            for plan in self.renderer.last_layout_plans
            if plan.warnings or not plan.fit_ok
        ]
        return RenderResult(
            ok=True,
            configured_engine_id=self.engine_id,
            runtime_engine_id=RUNTIME_RENDER_ENGINE_ID,
            page_id=page.page_id,
            rendered_path=str(rendered_path),
            final_path=str(final_path),
            rendered_blocks=rendered_blocks,
            skipped_blocks=skipped_blocks,
            layout_fit_failed_blocks=sum(1 for plan in self.renderer.last_layout_plans if not plan.fit_ok),
            layout_warnings=layout_warnings,
            layout_plans=layout_plans,
            final_written=write_final,
        )

    def run_session(self, session: MangaProjectSession, *, write_final: bool = True) -> list[RenderResult]:
        results: list[RenderResult] = []
        for page_ref in session.scene.pages:
            page = session.pages[page_ref.page_id]
            results.append(self.run_page(session, page, write_final=write_final))
        return results

    def _count_rendered_blocks(self, session: MangaProjectSession, page: MangaPage) -> tuple[int, int]:
        template = get_render_template(session.scene.render_preset)
        use_source_text_fallback = self.renderer.use_source_text_fallback or bool(
            template.get("use_source_text_fallback", False)
        )
        rendered_blocks = 0
        skipped_blocks = 0
        for block in page.text_blocks:
            text = str(block.translation or "").strip()
            if not text and use_source_text_fallback:
                text = str(block.source_text or "").strip()
            if text:
                rendered_blocks += 1
            else:
                skipped_blocks += 1
        return rendered_blocks, skipped_blocks
