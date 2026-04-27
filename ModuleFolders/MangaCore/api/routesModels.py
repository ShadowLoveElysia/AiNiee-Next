from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore
from ModuleFolders.MangaCore.pipeline.progress import JobRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])

_download_lock = threading.Lock()
_active_download_jobs: dict[str, str] = {}


def _model_display_name(status: dict[str, object], model_id: str) -> str:
    return str(status.get("display_name") or status.get("model_id") or model_id)


def _run_download_job(job_id: str, model_id: str) -> None:
    store = MangaModelStore()
    try:
        status = store.get_status(model_id)
        display_name = _model_display_name(status, model_id)
        if status.get("available"):
            JobRegistry.update(
                job_id,
                stage="model_download_completed",
                status="completed",
                progress=100,
                message=f"Manga model package is already prepared: {display_name}",
                result=status,
            )
            return

        JobRegistry.update(
            job_id,
            stage="model_download_running",
            status="running",
            progress=15,
            message=f"Preparing manga model package: {display_name}",
        )
        result = store.download(model_id)
        JobRegistry.update(
            job_id,
            stage="model_download_completed",
            status="completed",
            progress=100,
            message=f"Prepared manga model package: {_model_display_name(result, model_id)}",
            result=result,
        )
    except Exception as exc:
        JobRegistry.update(
            job_id,
            stage="model_download_failed",
            status="failed",
            progress=0,
            message=f"Failed to prepare manga model package: {model_id}",
            error_message=str(exc),
        )
    finally:
        with _download_lock:
            if _active_download_jobs.get(model_id) == job_id:
                _active_download_jobs.pop(model_id, None)


@router.get("/models")
def list_models() -> list[dict[str, object]]:
    return MangaModelStore().list_statuses()


@router.get("/models/{model_id}")
def get_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().get_status(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/models/{model_id}/download")
def download_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().download(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download manga model package: {exc}") from exc


@router.post("/models/{model_id}/download/start")
def start_download_model(model_id: str) -> dict[str, object]:
    try:
        status = MangaModelStore().get_status(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with _download_lock:
        existing_job_id = _active_download_jobs.get(model_id)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        display_name = _model_display_name(status, model_id)
        if status.get("available"):
            job = JobRegistry.create(
                stage="model_download_completed",
                status="completed",
                progress=100,
                message=f"Manga model package is already prepared: {display_name}",
            )
            JobRegistry.update(job.job_id, result=status)
            return (JobRegistry.get(job.job_id) or job).to_dict()

        job = JobRegistry.create(
            stage="model_download_queued",
            status="running",
            progress=1,
            message=f"Queued manga model package preparation: {display_name}",
        )
        _active_download_jobs[model_id] = job.job_id

    thread = threading.Thread(target=_run_download_job, args=(job.job_id, model_id), daemon=True)
    thread.start()
    return job.to_dict()
