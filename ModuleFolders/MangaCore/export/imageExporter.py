from __future__ import annotations

import shutil
from pathlib import Path

from ModuleFolders.MangaCore.project.session import MangaProjectSession


class ImageExporter:
    def export(self, session: MangaProjectSession) -> Path:
        target_dir = session.output_root / "final" / "pages"
        target_dir.mkdir(parents=True, exist_ok=True)
        for page in session.pages.values():
            rendered_path = session.project_path / page.layers.rendered
            output_path = target_dir / f"{page.index:04d}.png"
            shutil.copy2(rendered_path, output_path)
        return target_dir
