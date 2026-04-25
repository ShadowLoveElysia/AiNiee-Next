from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ModuleFolders.MangaCore.export.archiveCommon import iter_rendered_pages
from ModuleFolders.MangaCore.project.session import MangaProjectSession


def find_rar_creator() -> str | None:
    for command in ("rar", "Rar.exe", "WinRAR.exe"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    return None


class RarExporter:
    def export(self, session: MangaProjectSession) -> Path | None:
        files = iter_rendered_pages(session)
        if not files:
            return None

        rar_command = find_rar_creator()
        if rar_command is None:
            raise NotImplementedError("RAR export requires the external `rar` command on PATH.")

        output_path = session.output_root / "final" / "rar" / f"{session.manifest.name}.rar"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()

        command = [rar_command, "a", "-ep1", str(output_path)]
        command.extend(str(file_path) for _, file_path in files)
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() or exc.stdout.strip()
            raise NotImplementedError(f"RAR export failed: {stderr or output_path}") from exc

        return output_path
