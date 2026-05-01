from __future__ import annotations

import zipfile
from pathlib import Path

from ModuleFolders.MangaCore.pipeline.qualityGate import page_blocked_from_final
from ModuleFolders.MangaCore.project.session import MangaProjectSession


def iter_rendered_pages(session: MangaProjectSession, *, include_blocked: bool = False) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for page_ref in session.scene.pages:
        page = session.pages[page_ref.page_id]
        blocked, _reasons = page_blocked_from_final(session, page)
        if blocked and not include_blocked:
            continue
        rendered_path = session.project_path / page.layers.rendered
        files.append((f"{page.index:04d}.png", rendered_path))
    return files


def write_zip_archive(output_path: Path, files: list[tuple[str, Path]]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, file_path in files:
            archive.write(file_path, arcname=archive_name)
    return output_path
