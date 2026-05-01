from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.Base.Base import Base
from ModuleFolders.MangaCore.export.cbzExporter import CbzExporter
from ModuleFolders.MangaCore.export.epubExporter import EpubExporter
from ModuleFolders.MangaCore.export.imageExporter import ImageExporter
from ModuleFolders.MangaCore.export.pdfExporter import PdfExporter
from ModuleFolders.MangaCore.export.rarExporter import RarExporter
from ModuleFolders.MangaCore.export.zipExporter import ZipExporter
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine
from ModuleFolders.MangaCore.pipeline.qualityGate import page_blocked_from_final
from ModuleFolders.MangaCore.project.session import MangaProjectSession


def _i18n_format(key: str, fallback: str, *args: object) -> str:
    template = fallback
    i18n = getattr(Base, "i18n", None)
    if i18n is not None and hasattr(i18n, "get"):
        value = i18n.get(key)
        if value and value != key:
            template = str(value)
    try:
        return template.format(*args)
    except Exception:
        result = template
        for arg in args:
            result = result.replace("{}", str(arg), 1)
        return result


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
        blocked_pages: list[str] = []
        for page_ref in session.scene.pages:
            page = session.pages[page_ref.page_id]
            blocked, reasons = page_blocked_from_final(session, page)
            if blocked:
                suffix = f": {'; '.join(reasons)}" if reasons else ""
                blocked_pages.append(f"{page.index:04d}{suffix}")
        if blocked_pages:
            result.warnings.append(
                _i18n_format(
                    "manga_warning_final_export_skipped_blocked_pages",
                    "Skipped final export for page(s) blocked by MangaCore quality gates: {}",
                    ", ".join(blocked_pages),
                )
            )

        RenderEngine().run_session(session, write_final=False)
        pages_dir = self.image_exporter.export(session)
        if pages_dir:
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
