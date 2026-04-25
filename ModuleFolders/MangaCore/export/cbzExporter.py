from __future__ import annotations

from pathlib import Path

from ModuleFolders.MangaCore.export.archiveCommon import iter_rendered_pages, write_zip_archive
from ModuleFolders.MangaCore.project.session import MangaProjectSession


class CbzExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        files = iter_rendered_pages(session)
        if not files:
            return None
        output_path = session.output_root / "final" / "cbz" / f"{session.manifest.name}.cbz"
        return write_zip_archive(output_path, files)
