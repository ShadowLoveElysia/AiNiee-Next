from __future__ import annotations

import shutil
from pathlib import Path

from ModuleFolders.MangaCore.pipeline.qualityGate import page_blocked_from_final
from ModuleFolders.MangaCore.project.session import MangaProjectSession


class ImageExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        target_dir = session.output_root / "final" / "pages"
        target_dir.mkdir(parents=True, exist_ok=True)
        exported = 0
        for page in session.pages.values():
            blocked, _reasons = page_blocked_from_final(session, page)
            if blocked:
                output_path = target_dir / f"{page.index:04d}.png"
                if output_path.exists():
                    output_path.unlink()
                continue
            rendered_path = session.project_path / page.layers.rendered
            output_path = target_dir / f"{page.index:04d}.png"
            shutil.copy2(rendered_path, output_path)
            exported += 1
        return target_dir if exported else None
