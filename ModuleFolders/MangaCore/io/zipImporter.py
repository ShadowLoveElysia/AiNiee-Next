from __future__ import annotations

import zipfile
from pathlib import Path

from ModuleFolders.MangaCore.errors import UnsupportedInputError
from ModuleFolders.MangaCore.io.importerCommon import ImportedInput, collect_images, create_temp_root


class ZipImporter:
    def import_file(self, path: Path) -> ImportedInput:
        temp_root = create_temp_root("mangacore_zip_")
        with zipfile.ZipFile(path) as archive:
            archive.extractall(temp_root)

        images = collect_images(temp_root)
        if not images:
            raise UnsupportedInputError(f"No supported image files found in zip archive: {path}")

        return ImportedInput(source_type=path.suffix.lower().lstrip("."), images=images, temp_root=temp_root)
