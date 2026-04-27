from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.MangaCore.api.schemas import BatchTranslateRequest, PageTranslateRequest
from ModuleFolders.MangaCore.pipeline.runtimeValidation import MangaRuntimeValidator
from ModuleFolders.MangaCore.pipeline.runnerPage import MangaPageRunner
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _ensure_project_and_page(project_id: str, page_id: str | None = None) -> MangaProjectSession:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    if page_id and page_id not in session.pages:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return session


def _ensure_manga_translation_ready(session: MangaProjectSession) -> None:
    status = get_manga_feature_status(
        config_snapshot=session.config_snapshot,
        require_models=True,
    )
    if not status.available:
        raise HTTPException(status_code=503, detail=status.user_message())


@router.post("/projects/{project_id}/pages/{page_id}/translate")
def translate_page(project_id: str, page_id: str, request: PageTranslateRequest) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    _ensure_manga_translation_ready(session)
    job = MangaPageRunner().translate_current_page(
        session,
        page_id=page_id,
        save_after_run=request.save_after_run,
        refresh_render=request.refresh_render,
    )
    payload = job.to_dict()
    payload["page_id"] = page_id
    return payload


@router.post("/projects/{project_id}/pages/{page_id}/detect")
def detect_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    _ensure_manga_translation_ready(session)
    job = MangaPageRunner().detect_current_page(
        session,
        page_id=page_id,
        save_after_run=True,
    )
    payload = job.to_dict()
    payload["page_id"] = page_id
    return payload


@router.post("/projects/{project_id}/pages/{page_id}/ocr")
def ocr_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    _ensure_manga_translation_ready(session)
    job = MangaPageRunner().ocr_current_page(
        session,
        page_id=page_id,
        save_after_run=True,
    )
    payload = job.to_dict()
    payload["page_id"] = page_id
    payload["stage"] = "page_ocr"
    return payload


@router.post("/projects/{project_id}/pages/{page_id}/inpaint")
def inpaint_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    _ensure_manga_translation_ready(session)
    job = MangaPageRunner().inpaint_current_page(
        session,
        page_id=page_id,
        save_after_run=True,
    )
    payload = job.to_dict()
    payload["page_id"] = page_id
    return payload


@router.post("/projects/{project_id}/pages/{page_id}/render")
def render_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    job = MangaPageRunner().render_current_page(
        session,
        page_id=page_id,
        save_after_run=True,
    )
    payload = job.to_dict()
    payload["page_id"] = page_id
    return payload


@router.post("/projects/{project_id}/pages/{page_id}/runtime-validation")
def validate_page_runtime(project_id: str, page_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    page = session.get_page(page_id)
    return MangaRuntimeValidator().run_page_validation(session, page).to_dict()


@router.get("/projects/{project_id}/pages/{page_id}/runtime-validation/latest")
def get_latest_page_runtime_validation(project_id: str, page_id: str) -> dict[str, object] | None:
    session = _ensure_project_and_page(project_id, page_id)
    page = session.get_page(page_id)
    page_key = f"{page.index:04d}"
    report_path = session.project_path / "pages" / page_key / "runtimeValidationLatest.json"
    if not report_path.exists():
        return None
    with open(report_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


@router.post("/projects/{project_id}/batch/translate")
def translate_selected_pages(project_id: str, request: BatchTranslateRequest) -> dict[str, object]:
    session = _ensure_project_and_page(project_id)
    _ensure_manga_translation_ready(session)
    for page_id in request.page_ids:
        _ensure_project_and_page(project_id, page_id)
    job = MangaPageRunner().translate_selected_pages(
        session,
        page_ids=request.page_ids,
        generate_text_blocks=request.generate_text_blocks,
        auto_inpaint=request.auto_inpaint,
        auto_render=request.auto_render,
    )
    payload = job.to_dict()
    payload["page_count"] = len(request.page_ids)
    return payload


@router.post("/projects/{project_id}/batch/typesetting-plan")
def plan_selected_pages(project_id: str, request: BatchTranslateRequest) -> dict[str, object]:
    session = _ensure_project_and_page(project_id)
    _ensure_manga_translation_ready(session)
    for page_id in request.page_ids:
        _ensure_project_and_page(project_id, page_id)
    job = MangaPageRunner().plan_selected_pages(
        session,
        page_ids=request.page_ids,
        generate_text_blocks=True,
    )
    payload = job.to_dict()
    payload["page_count"] = len(request.page_ids)
    payload["stage"] = "batch_typesetting_planning" if payload.get("status") == "completed" else payload.get("stage")
    return payload
