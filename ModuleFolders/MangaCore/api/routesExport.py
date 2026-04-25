from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.export.cbzExporter import CbzExporter
from ModuleFolders.MangaCore.export.epubExporter import EpubExporter
from ModuleFolders.MangaCore.export.pdfExporter import PdfExporter
from ModuleFolders.MangaCore.export.rarExporter import RarExporter
from ModuleFolders.MangaCore.export.zipExporter import ZipExporter
from ModuleFolders.MangaCore.project.session import SessionRegistry
from ModuleFolders.MangaCore.render.painter import MangaRenderer

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _get_session_or_404(project_id: str):
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


@router.post("/projects/{project_id}/export/pdf")
def export_pdf(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    MangaRenderer().render_session(session)
    output_path = PdfExporter().export(session)
    return {"ok": output_path is not None, "path": str(output_path) if output_path else None}


@router.post("/projects/{project_id}/export/epub")
def export_epub(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    MangaRenderer().render_session(session)
    try:
        output_path = EpubExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"ok": output_path is not None, "path": str(output_path) if output_path else None}


@router.post("/projects/{project_id}/export/cbz")
def export_cbz(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    MangaRenderer().render_session(session)
    try:
        output_path = CbzExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"ok": output_path is not None, "path": str(output_path) if output_path else None}


@router.post("/projects/{project_id}/export/zip")
def export_zip(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    MangaRenderer().render_session(session)
    output_path = ZipExporter().export(session)
    return {"ok": output_path is not None, "path": str(output_path) if output_path else None}


@router.post("/projects/{project_id}/export/rar")
def export_rar(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    MangaRenderer().render_session(session)
    try:
        output_path = RarExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"ok": output_path is not None, "path": str(output_path) if output_path else None}
