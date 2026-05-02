from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.export.cbzExporter import CbzExporter
from ModuleFolders.MangaCore.export.epubExporter import EpubExporter
from ModuleFolders.MangaCore.export.pdfExporter import PdfExporter
from ModuleFolders.MangaCore.export.rarExporter import RarExporter
from ModuleFolders.MangaCore.export.zipExporter import ZipExporter
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine
from ModuleFolders.MangaCore.pipeline.qualityGate import load_quality_gate, page_blocked_from_final, quality_gate_path
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _get_session_or_404(project_id: str):
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


def _blocked_pages_payload(session: MangaProjectSession) -> list[dict[str, object]]:
    blocked_pages: list[dict[str, object]] = []
    for page_ref in session.scene.pages:
        page = session.pages[page_ref.page_id]
        blocked, _reasons = page_blocked_from_final(session, page)
        if not blocked:
            continue
        gate = load_quality_gate(session, page)
        issues = [issue for issue in gate.issues if issue.blocks_final] if gate else []
        report_path = quality_gate_path(session, page)
        blocked_pages.append(
            {
                "page_id": page.page_id,
                "index": page.index,
                "status": page.status,
                "issue_count": len(issues),
                "issues": [issue.to_dict() for issue in issues],
                "draft_rendered_path": page.layers.rendered,
                "quality_gate_path": (
                    str(report_path.relative_to(session.project_path)).replace("\\", "/")
                    if report_path.exists()
                    else ""
                ),
            }
        )
    return blocked_pages


def _export_payload(output_path, session: MangaProjectSession) -> dict[str, object]:
    blocked_pages = _blocked_pages_payload(session)
    payload: dict[str, object] = {
        "ok": output_path is not None,
        "path": str(output_path) if output_path else None,
        "blocked_pages": blocked_pages,
    }
    if blocked_pages:
        if output_path is None:
            payload.update(
                {
                    "message_key": "manga_export_blocked_by_quality_gate",
                    "message_args": [len(blocked_pages)],
                }
            )
        else:
            payload.update(
                {
                    "message_key": "manga_export_partially_blocked_by_quality_gate",
                    "message_args": [len(blocked_pages)],
                }
            )
    return payload


@router.post("/projects/{project_id}/export/pdf")
def export_pdf(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    RenderEngine().run_session(session, write_final=False)
    output_path = PdfExporter().export(session)
    return _export_payload(output_path, session)


@router.post("/projects/{project_id}/export/epub")
def export_epub(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    RenderEngine().run_session(session, write_final=False)
    try:
        output_path = EpubExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return _export_payload(output_path, session)


@router.post("/projects/{project_id}/export/cbz")
def export_cbz(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    RenderEngine().run_session(session, write_final=False)
    try:
        output_path = CbzExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return _export_payload(output_path, session)


@router.post("/projects/{project_id}/export/zip")
def export_zip(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    RenderEngine().run_session(session, write_final=False)
    output_path = ZipExporter().export(session)
    return _export_payload(output_path, session)


@router.post("/projects/{project_id}/export/rar")
def export_rar(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    RenderEngine().run_session(session, write_final=False)
    try:
        output_path = RarExporter().export(session)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return _export_payload(output_path, session)
