from __future__ import annotations

import json
import threading

from fastapi import APIRouter, HTTPException

from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.MangaCore.api.schemas import BatchTranslateRequest, PageTranslateRequest
from ModuleFolders.MangaCore.pipeline.progress import JobRegistry
from ModuleFolders.MangaCore.pipeline.runtimeValidation import MangaRuntimeValidator
from ModuleFolders.MangaCore.pipeline.runnerPage import MangaPageRunner
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])

_runtime_validation_lock = threading.Lock()
_active_runtime_validation_jobs: dict[str, str] = {}


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


def _run_runtime_validation_job(job_id: str, project_id: str, page_id: str) -> None:
    job_key = f"{project_id}:{page_id}"
    try:
        session = SessionRegistry.get(project_id)
        if session is None:
            raise RuntimeError(f"Manga project is not open: {project_id}")
        if page_id not in session.pages:
            raise RuntimeError(f"Page not found: {page_id}")

        JobRegistry.update(
            job_id,
            stage="runtime_validation_running",
            status="running",
            progress=20,
            message="Validating MangaCore runtime stages.",
        )
        page = session.get_page(page_id)
        result = MangaRuntimeValidator().run_page_validation(session, page).to_dict()
        fallback_count = int(result.get("summary", {}).get("fallback_stage_count", 0)) if isinstance(result.get("summary"), dict) else 0
        JobRegistry.update(
            job_id,
            stage="runtime_validation_completed",
            status="completed",
            progress=100,
            message=f"Runtime validation completed with {fallback_count} fallback stage(s).",
            result=result,
        )
    except Exception as exc:
        JobRegistry.update(
            job_id,
            stage="runtime_validation_failed",
            status="failed",
            progress=0,
            message="Runtime validation failed.",
            error_message=str(exc),
        )
    finally:
        with _runtime_validation_lock:
            if _active_runtime_validation_jobs.get(job_key) == job_id:
                _active_runtime_validation_jobs.pop(job_key, None)


@router.post("/projects/{project_id}/pages/{page_id}/runtime-validation/start")
def start_page_runtime_validation(project_id: str, page_id: str) -> dict[str, object]:
    _ensure_project_and_page(project_id, page_id)
    job_key = f"{project_id}:{page_id}"
    with _runtime_validation_lock:
        existing_job_id = _active_runtime_validation_jobs.get(job_key)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        job = JobRegistry.create(
            stage="runtime_validation_queued",
            status="running",
            project_id=project_id,
            page_id=page_id,
            progress=1,
            message="Queued MangaCore runtime validation.",
        )
        _active_runtime_validation_jobs[job_key] = job.job_id

    thread = threading.Thread(target=_run_runtime_validation_job, args=(job.job_id, project_id, page_id), daemon=True)
    thread.start()
    return job.to_dict()


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


@router.get("/projects/{project_id}/pages/{page_id}/runtime-validation/history")
def list_page_runtime_validation_history(project_id: str, page_id: str) -> list[dict[str, object]]:
    session = _ensure_project_and_page(project_id, page_id)
    page = session.get_page(page_id)
    page_key = f"{page.index:04d}"
    history_root = session.project_path / "pages" / page_key / "runtimeValidation"
    if not history_root.exists():
        return []

    items: list[dict[str, object]] = []
    for report_path in sorted(history_root.glob("*/report.json"), reverse=True):
        try:
            with open(report_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        run_id = report_path.parent.name
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        items.append(
            {
                "run_id": run_id,
                "created_at": str(payload.get("created_at") or ""),
                "ok": bool(payload.get("ok")),
                "output_dir": str(payload.get("output_dir") or ""),
                "runtime_stage_count": int(summary.get("runtime_stage_count") or 0),
                "fallback_stage_count": int(summary.get("fallback_stage_count") or 0),
                "seed_count": int(summary.get("seed_count") or 0),
            }
        )
    return items


@router.get("/projects/{project_id}/pages/{page_id}/runtime-validation/history/{run_id}")
def get_page_runtime_validation_history_item(project_id: str, page_id: str, run_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    page = session.get_page(page_id)
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid runtime validation run id.")
    page_key = f"{page.index:04d}"
    report_path = session.project_path / "pages" / page_key / "runtimeValidation" / run_id / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Runtime validation report not found: {run_id}")
    with open(report_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Invalid runtime validation report: {run_id}")
    return payload


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
