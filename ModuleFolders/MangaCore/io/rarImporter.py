from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ModuleFolders.MangaCore.errors import UnsupportedInputError
from ModuleFolders.MangaCore.io.importerCommon import ImportedInput, collect_images, create_temp_root


def find_rar_extractor() -> list[str] | None:
    for command in ("unrar", "UnRAR.exe", "rar", "Rar.exe", "WinRAR.exe", "7z", "7z.exe", "7zz", "7zz.exe", "bsdtar", "bsdtar.exe"):
        resolved = shutil.which(command)
        if resolved:
            return [resolved]
    return None


class RarImporter:
    def import_file(self, path: Path) -> ImportedInput:
        extractor = find_rar_extractor()
        if extractor is None:
            raise UnsupportedInputError(
                "RAR/CBR import requires an external extractor (unrar, rar, 7z, 7zz, or bsdtar) on PATH."
            )

        temp_root = create_temp_root("mangacore_rar_")
        command = self._build_extract_command(extractor[0], path, temp_root)
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() or exc.stdout.strip()
            raise UnsupportedInputError(f"Failed to extract RAR/CBR archive: {stderr or path}") from exc

        images = collect_images(temp_root)
        if not images:
            raise UnsupportedInputError(f"No supported image files found in rar archive: {path}")

        return ImportedInput(source_type=path.suffix.lower().lstrip("."), images=images, temp_root=temp_root)

    @staticmethod
    def _build_extract_command(executable: str, archive_path: Path, temp_root: Path) -> list[str]:
        executable_name = Path(executable).name.lower()
        if executable_name in {"unrar", "unrar.exe", "rar", "rar.exe", "winrar.exe"}:
            return [executable, "x", "-o+", str(archive_path), str(temp_root)]
        if executable_name in {"7z", "7z.exe", "7zz", "7zz.exe"}:
            return [executable, "x", "-y", f"-o{temp_root}", str(archive_path)]
        if executable_name in {"bsdtar", "bsdtar.exe"}:
            return [executable, "-xf", str(archive_path), "-C", str(temp_root)]
        return [executable, str(archive_path), str(temp_root)]
