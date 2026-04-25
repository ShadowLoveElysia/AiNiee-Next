from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.MangaCore.export.cbzExporter import CbzExporter
from ModuleFolders.MangaCore.export.epubExporter import EpubExporter
from ModuleFolders.MangaCore.export.imageExporter import ImageExporter
from ModuleFolders.MangaCore.export.pdfExporter import PdfExporter
from ModuleFolders.MangaCore.export.rarExporter import RarExporter
from ModuleFolders.MangaCore.export.zipExporter import ZipExporter
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.painter import MangaRenderer


@dataclass(slots=True)
class PackageExportResult:
    exported_paths: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class PackageExporter:
    def __init__(self) -> None:
        self.image_exporter = ImageExporter()
        self.pdf_exporter = PdfExporter()
        self.epub_exporter = EpubExporter()
        self.cbz_exporter = CbzExporter()
        self.zip_exporter = ZipExporter()
        self.rar_exporter = RarExporter()

    def export(self, session: MangaProjectSession) -> PackageExportResult:
        result = PackageExportResult()
        MangaRenderer().render_session(session)
        pages_dir = self.image_exporter.export(session)
        result.exported_paths["pages"] = str(pages_dir)

        pdf_path = self.pdf_exporter.export(session)
        if pdf_path:
            result.exported_paths["pdf"] = str(pdf_path)

        for key, exporter in (
            ("cbz", self.cbz_exporter),
            ("zip", self.zip_exporter),
            ("rar", self.rar_exporter),
            ("epub", self.epub_exporter),
        ):
            try:
                output_path = exporter.export(session)
                if output_path:
                    result.exported_paths[key] = str(output_path)
            except NotImplementedError as exc:
                result.warnings.append(str(exc))

        return result
