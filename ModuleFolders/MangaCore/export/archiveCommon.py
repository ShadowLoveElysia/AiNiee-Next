from __future__ import annotations

import zipfile
from pathlib import Path

from ModuleFolders.MangaCore.project.session import MangaProjectSession


def iter_rendered_pages(session: MangaProjectSession) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for page_ref in session.scene.pages:
        page = session.pages[page_ref.page_id]
        rendered_path = session.project_path / page.layers.rendered
        files.append((f"{page.index:04d}.png", rendered_path))
    return files


def write_zip_archive(output_path: Path, files: list[tuple[str, Path]]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, file_path in files:
            archive.write(file_path, arcname=archive_name)
    return output_path
