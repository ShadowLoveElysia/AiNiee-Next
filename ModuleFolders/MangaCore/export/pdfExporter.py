from __future__ import annotations

from pathlib import Path

from PIL import Image

from ModuleFolders.MangaCore.project.session import MangaProjectSession


class PdfExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        rendered_paths = [session.project_path / session.pages[page_ref.page_id].layers.rendered for page_ref in session.scene.pages]
        if not rendered_paths:
            return None

        images = [Image.open(path).convert("RGB") for path in rendered_paths]
        try:
            output_path = session.output_root / "final" / "pdf" / f"{session.manifest.name}.pdf"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            first, rest = images[0], images[1:]
            first.save(output_path, save_all=True, append_images=rest)
            return output_path
        finally:
            for image in images:
                image.close()
