from __future__ import annotations

from pathlib import Path

from ModuleFolders.MangaCore.errors import UnsupportedInputError
from ModuleFolders.MangaCore.io.importerCommon import ImportedInput, collect_images
from ModuleFolders.MangaCore.io.pdfImporter import PdfImporter
from ModuleFolders.MangaCore.io.rarImporter import RarImporter
from ModuleFolders.MangaCore.io.zipImporter import ZipImporter
from ModuleFolders.MangaCore.constants import IMAGE_SUFFIXES


def discover_input_images(input_path: str | Path) -> ImportedInput:
    path = Path(input_path)
    if not path.exists():
        raise UnsupportedInputError(f"Input path not found: {path}")

    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
        return ImportedInput(source_type="single_image", images=[path])

    if path.is_dir():
        images = collect_images(path)
        if not images:
            raise UnsupportedInputError(f"No supported image files found under: {path}")
        return ImportedInput(source_type="directory", images=images)

    if path.is_file() and path.suffix.lower() == ".pdf":
        return PdfImporter().import_file(path)

    if path.is_file() and path.suffix.lower() in {".zip", ".cbz"}:
        return ZipImporter().import_file(path)

    if path.is_file() and path.suffix.lower() in {".rar", ".cbr"}:
        return RarImporter().import_file(path)

    raise UnsupportedInputError(f"Unsupported manga input source: {path}")
