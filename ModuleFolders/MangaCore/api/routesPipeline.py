from __future__ import annotations

import json
import shutil
import threading

from fastapi import APIRouter, HTTPException

from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.MangaCore.api.schemas import BatchTranslateRequest, PageTranslateRequest
from ModuleFolders.MangaCore.pipeline.progress import JobRegistry
from ModuleFolders.MangaCore.pipeline.runtimeValidation import MangaRuntimeValidator, RuntimeValidationCancelled
from ModuleFolders.MangaCore.pipeline.runnerPage import MangaPageRunner
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])

_runtime_validation_lock = threading.Lock()
_active_runtime_validation_jobs: dict[str, str] = {}
_RUNTIME_VALIDATION_RETRY_STAGES = {"detect", "ocr", "inpaint"}


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
        require_models=False,
    )
    if not status.available:
        raise HTTPException(status_code=503, detail=status.user_message())


def _validate_runtime_run_id(run_id: str) -> None:
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid runtime validation run id.")


def _runtime_validation_root(session: MangaProjectSession, page_id: str):
    page = session.get_page(page_id)
    page_key = f"{page.index:04d}"
    return session.project_path / "pages" / page_key / "runtimeValidation"


def _runtime_validation_report_path(session: MangaProjectSession, page_id: str, run_id: str):
    _validate_runtime_run_id(run_id)
    return _runtime_validation_root(session, page_id) / run_id / "report.json"


def _load_runtime_validation_report(session: MangaProjectSession, page_id: str, run_id: str) -> dict[str, object]:
    report_path = _runtime_validation_report_path(session, page_id, run_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Runtime validation report not found: {run_id}")
    with open(report_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Invalid runtime validation report: {run_id}")
    return payload


def _summary_value(report: dict[str, object], key: str) -> object:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if key == "ok":
        return bool(report.get("ok"))
    return summary.get(key)


def _stage_map(report: dict[str, object]) -> dict[str, dict[str, object]]:
    stages = report.get("stages")
    if not isinstance(stages, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage") or "")
        if stage_id:
            result[stage_id] = stage
    return result


def _metric_value(stage: dict[str, object], key: str) -> object:
    metrics = stage.get("metrics") if isinstance(stage.get("metrics"), dict) else {}
    return metrics.get(key)


def _append_change(changes: list[dict[str, object]], key: str, before: object, after: object) -> None:
    if before != after:
        changes.append({"key": key, "before": before, "after": after})


def _diff_runtime_validation_reports(
    before_run_id: str,
    after_run_id: str,
    before_report: dict[str, object],
    after_report: dict[str, object],
) -> dict[str, object]:
    summary_keys = [
        "ok",
        "runtime_stage_count",
        "fallback_stage_count",
        "configured_runtime_stage_count",
        "fallback_runtime_stage_count",
        "heuristic_fallback_stage_count",
        "failed_stage_count",
        "seed_count",
    ]
    summary_changes: list[dict[str, object]] = []
    for key in summary_keys:
        _append_change(summary_changes, key, _summary_value(before_report, key), _summary_value(after_report, key))

    before_stages = _stage_map(before_report)
    after_stages = _stage_map(after_report)
    stage_changes: list[dict[str, object]] = []
    stage_keys = sorted(set(before_stages) | set(after_stages))
    field_keys = [
        "ok",
        "execution_mode",
        "runtime_engine_id",
        "used_runtime",
        "warning_message",
        "error_message",
        "fallback_reason",
    ]
    metric_keys = ["seed_count", "text_region_count", "bubble_region_count", "assignment_count", "mask_pixels"]
    for stage_id in stage_keys:
        before_stage = before_stages.get(stage_id, {})
        after_stage = after_stages.get(stage_id, {})
        changes: list[dict[str, object]] = []
        for key in field_keys:
            _append_change(changes, key, before_stage.get(key), after_stage.get(key))
        for key in metric_keys:
            _append_change(changes, f"metrics.{key}", _metric_value(before_stage, key), _metric_value(after_stage, key))
        before_artifacts = before_stage.get("artifacts") if isinstance(before_stage.get("artifacts"), dict) else {}
        after_artifacts = after_stage.get("artifacts") if isinstance(after_stage.get("artifacts"), dict) else {}
        _append_change(changes, "artifact_keys", sorted(before_artifacts.keys()), sorted(after_artifacts.keys()))
        if changes:
            stage_changes.append({"stage": stage_id, "changes": changes})

    return {
        "before_run_id": before_run_id,
        "after_run_id": after_run_id,
        "before_created_at": str(before_report.get("created_at") or ""),
        "after_created_at": str(after_report.get("created_at") or ""),
        "summary_changes": summary_changes,
        "stage_changes": stage_changes,
    }


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


def _runtime_job_key(project_id: str, page_id: str) -> str:
    return f"{project_id}:{page_id}"


def _run_runtime_validation_job(job_id: str, project_id: str, page_id: str, retry_stage: str = "") -> None:
    job_key = _runtime_job_key(project_id, page_id)
    try:
        session = SessionRegistry.get(project_id)
        if session is None:
            raise RuntimeError(f"Manga project is not open: {project_id}")
        if page_id not in session.pages:
            raise RuntimeError(f"Page not found: {page_id}")

        JobRegistry.update(
            job_id,
            stage="runtime_validation_retry_running" if retry_stage else "runtime_validation_running",
            status="running",
            progress=20,
            message=(
                f"Retrying MangaCore runtime validation stage: {retry_stage}."
                if retry_stage
                else "Validating MangaCore runtime stages."
            ),
        )
        page = session.get_page(page_id)
        validator = MangaRuntimeValidator()

        def should_cancel() -> bool:
            return JobRegistry.is_cancel_requested(job_id)

        result = (
            validator.retry_stage(session, page, retry_stage, should_cancel=should_cancel)
            if retry_stage
            else validator.run_page_validation(session, page, should_cancel=should_cancel)
        ).to_dict()
        fallback_count = int(result.get("summary", {}).get("fallback_stage_count", 0)) if isinstance(result.get("summary"), dict) else 0
        JobRegistry.update(
            job_id,
            stage="runtime_validation_retry_completed" if retry_stage else "runtime_validation_completed",
            status="completed",
            progress=100,
            message=(
                f"Runtime validation stage retry completed for {retry_stage} with {fallback_count} fallback stage(s)."
                if retry_stage
                else f"Runtime validation completed with {fallback_count} fallback stage(s)."
            ),
            result=result,
        )
    except RuntimeValidationCancelled:
        JobRegistry.update(
            job_id,
            stage="runtime_validation_cancelled",
            status="cancelled",
            progress=0,
            message="Runtime validation cancelled.",
        )
    except Exception as exc:
        JobRegistry.update(
            job_id,
            stage="runtime_validation_retry_failed" if retry_stage else "runtime_validation_failed",
            status="failed",
            progress=0,
            message=(
                f"Runtime validation stage retry failed for {retry_stage}."
                if retry_stage
                else "Runtime validation failed."
            ),
            error_message=str(exc),
        )
    finally:
        with _runtime_validation_lock:
            if _active_runtime_validation_jobs.get(job_key) == job_id:
                _active_runtime_validation_jobs.pop(job_key, None)


@router.post("/projects/{project_id}/pages/{page_id}/runtime-validation/start")
def start_page_runtime_validation(project_id: str, page_id: str) -> dict[str, object]:
    _ensure_project_and_page(project_id, page_id)
    job_key = _runtime_job_key(project_id, page_id)
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


@router.post("/projects/{project_id}/pages/{page_id}/runtime-validation/stop")
def stop_page_runtime_validation(project_id: str, page_id: str) -> dict[str, object]:
    _ensure_project_and_page(project_id, page_id)
    job_key = _runtime_job_key(project_id, page_id)
    with _runtime_validation_lock:
        job_id = _active_runtime_validation_jobs.get(job_key)
        job = JobRegistry.get(job_id) if job_id else None
        if job is None or job.status != "running":
            raise HTTPException(status_code=404, detail="No active runtime validation job for this page.")
        updated = JobRegistry.request_cancel(
            job.job_id,
            stage="runtime_validation_cancelling",
            message="Cancelling MangaCore runtime validation.",
        )
    return (updated or job).to_dict()


@router.post("/projects/{project_id}/pages/{page_id}/runtime-validation/stages/{stage}/retry/start")
def start_page_runtime_validation_stage_retry(project_id: str, page_id: str, stage: str) -> dict[str, object]:
    _ensure_project_and_page(project_id, page_id)
    retry_stage = stage.strip().lower()
    if retry_stage not in _RUNTIME_VALIDATION_RETRY_STAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported runtime validation stage retry: {stage}")

    job_key = _runtime_job_key(project_id, page_id)
    with _runtime_validation_lock:
        existing_job_id = _active_runtime_validation_jobs.get(job_key)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        job = JobRegistry.create(
            stage="runtime_validation_retry_queued",
            status="running",
            project_id=project_id,
            page_id=page_id,
            progress=1,
            message=f"Queued MangaCore runtime validation stage retry: {retry_stage}.",
        )
        _active_runtime_validation_jobs[job_key] = job.job_id

    thread = threading.Thread(target=_run_runtime_validation_job, args=(job.job_id, project_id, page_id, retry_stage), daemon=True)
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
    history_root = _runtime_validation_root(session, page_id)
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


@router.get("/projects/{project_id}/pages/{page_id}/runtime-validation/history/{before_run_id}/diff/{after_run_id}")
def diff_page_runtime_validation_history(
    project_id: str,
    page_id: str,
    before_run_id: str,
    after_run_id: str,
) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    before_report = _load_runtime_validation_report(session, page_id, before_run_id)
    after_report = _load_runtime_validation_report(session, page_id, after_run_id)
    return _diff_runtime_validation_reports(before_run_id, after_run_id, before_report, after_report)


@router.get("/projects/{project_id}/pages/{page_id}/runtime-validation/history/{run_id}")
def get_page_runtime_validation_history_item(project_id: str, page_id: str, run_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    return _load_runtime_validation_report(session, page_id, run_id)


@router.delete("/projects/{project_id}/pages/{page_id}/runtime-validation/history/{run_id}")
def delete_page_runtime_validation_history_item(project_id: str, page_id: str, run_id: str) -> dict[str, object]:
    session = _ensure_project_and_page(project_id, page_id)
    report_path = _runtime_validation_report_path(session, page_id, run_id)
    run_dir = report_path.parent
    if not report_path.exists() or not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Runtime validation report not found: {run_id}")

    latest_path = session.project_path / "pages" / f"{session.get_page(page_id).index:04d}" / "runtimeValidationLatest.json"
    latest_output_dir = ""
    if latest_path.exists():
        try:
            with open(latest_path, encoding="utf-8") as handle:
                latest_payload = json.load(handle)
            if isinstance(latest_payload, dict):
                latest_output_dir = str(latest_payload.get("output_dir") or "")
        except Exception:
            latest_output_dir = ""

    shutil.rmtree(run_dir)
    if latest_output_dir.replace("\\", "/").rstrip("/").endswith(f"/{run_id}") and latest_path.exists():
        latest_path.unlink()

    return {"ok": True, "deleted": run_id}


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
    if request.auto_export and job.status == "completed":
        from ModuleFolders.MangaCore.export.packageExporter import PackageExporter

        export_result = PackageExporter().export(session)
        payload["exports"] = dict(export_result.exported_paths)
        payload["export_warnings"] = list(export_result.warnings)
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
