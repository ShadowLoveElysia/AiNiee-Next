from __future__ import annotations

from pathlib import Path

from PIL import Image

from ModuleFolders.MangaCore.export.archiveCommon import iter_rendered_pages
from ModuleFolders.MangaCore.project.session import MangaProjectSession


class PdfExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        rendered_paths = [path for _archive_name, path in iter_rendered_pages(session)]
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
