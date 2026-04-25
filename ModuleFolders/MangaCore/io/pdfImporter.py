from __future__ import annotations

from pathlib import Path

from ModuleFolders.MangaCore.errors import UnsupportedInputError
from ModuleFolders.MangaCore.io.importerCommon import ImportedInput, create_temp_root


class PdfImporter:
    def import_file(self, path: Path) -> ImportedInput:
        try:
            import fitz
        except ImportError as exc:
            raise UnsupportedInputError("PDF import requires PyMuPDF/fitz to be installed.") from exc

        temp_root = create_temp_root("mangacore_pdf_")
        images: list[Path] = []

        with fitz.open(path) as document:
            if document.page_count == 0:
                raise UnsupportedInputError(f"PDF contains no pages: {path}")

            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_path = temp_root / f"{index:04d}.png"
                pixmap.save(image_path)
                images.append(image_path)

        return ImportedInput(source_type="pdf", images=images, temp_root=temp_root)
