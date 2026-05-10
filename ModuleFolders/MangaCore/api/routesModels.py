from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.pipeline.modelCatalog import normalize_model_id
from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore
from ModuleFolders.MangaCore.pipeline.progress import JobRegistry
from ModuleFolders.MangaCore.pipeline.runtimeReadiness import build_manga_runtime_readiness
from ModuleFolders.MangaCore.project.session import SessionRegistry
from ModuleFolders.MangaCore.render.font import list_font_catalog

router = APIRouter(prefix="/api/manga", tags=["manga"])

_download_lock = threading.Lock()
_active_download_jobs: dict[str, str] = {}
_active_preset_download_jobs: dict[str, str] = {}


def _active_job_key(item_id: str, project_id: str = "") -> str:
    return f"{project_id}:{item_id}" if project_id else item_id


def _model_display_name(status: dict[str, object], model_id: str) -> str:
    return str(status.get("display_name") or status.get("model_id") or model_id)


def _run_download_job(job_id: str, model_id: str, active_key: str) -> None:
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
            if _active_download_jobs.get(active_key) == job_id:
                _active_download_jobs.pop(active_key, None)


def _run_preset_download_job(job_id: str, preset_id: str, active_key: str) -> None:
    store = MangaModelStore()
    try:
        manifest = store.build_manager_manifest()
        preset_payload = next(
            (
                preset
                for preset in manifest.get("presets", [])
                if isinstance(preset, dict) and preset.get("preset_id") == preset_id
            ),
            None,
        )
        if not isinstance(preset_payload, dict):
            raise KeyError(f"Unknown manga model preset: {preset_id}")

        display_name = str(preset_payload.get("display_name") or preset_id)
        model_ids = [str(model_id) for model_id in preset_payload.get("model_ids", [])]
        if not model_ids:
            raise RuntimeError(f"Manga model preset has no models: {preset_id}")

        prepared: list[dict[str, object]] = []
        for index, model_id in enumerate(model_ids, start=1):
            JobRegistry.update(
                job_id,
                stage="model_preset_download_running",
                status="running",
                progress=max(5, int((index - 1) / len(model_ids) * 95)),
                message=f"Preparing manga model preset {display_name}: {model_id} ({index}/{len(model_ids)})",
            )
            status = store.get_status(model_id)
            if not status.get("available"):
                status = store.download(model_id)
            prepared.append(status)

        refreshed = store.build_manager_manifest()
        refreshed_preset = next(
            (
                preset
                for preset in refreshed.get("presets", [])
                if isinstance(preset, dict) and preset.get("preset_id") == preset_id
            ),
            preset_payload,
        )
        JobRegistry.update(
            job_id,
            stage="model_preset_download_completed",
            status="completed",
            progress=100,
            message=f"Prepared manga model preset: {display_name}",
            result={
                "preset": refreshed_preset,
                "models": prepared,
                "config_overrides": dict(preset_payload.get("config_overrides") or {}),
            },
        )
    except Exception as exc:
        JobRegistry.update(
            job_id,
            stage="model_preset_download_failed",
            status="failed",
            progress=0,
            message=f"Failed to prepare manga model preset: {preset_id}",
            error_message=str(exc),
        )
    finally:
        with _download_lock:
            if _active_preset_download_jobs.get(active_key) == job_id:
                _active_preset_download_jobs.pop(active_key, None)


def _start_download_model_job(model_id: str, *, project_id: str = "") -> dict[str, object]:
    model_id = normalize_model_id(model_id)
    try:
        status = MangaModelStore().get_status(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    active_key = _active_job_key(model_id, project_id)
    with _download_lock:
        existing_job_id = _active_download_jobs.get(active_key)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        display_name = _model_display_name(status, model_id)
        if status.get("available"):
            job = JobRegistry.create(
                stage="model_download_completed",
                status="completed",
                project_id=project_id,
                progress=100,
                message=f"Manga model package is already prepared: {display_name}",
            )
            JobRegistry.update(job.job_id, result=status)
            return (JobRegistry.get(job.job_id) or job).to_dict()

        job = JobRegistry.create(
            stage="model_download_queued",
            status="running",
            project_id=project_id,
            progress=1,
            message=f"Queued manga model package preparation: {display_name}",
        )
        _active_download_jobs[active_key] = job.job_id

    thread = threading.Thread(target=_run_download_job, args=(job.job_id, model_id, active_key), daemon=True)
    thread.start()
    return job.to_dict()


def _start_download_model_preset_job(preset_id: str, *, project_id: str = "") -> dict[str, object]:
    try:
        manifest = MangaModelStore().build_manager_manifest()
        preset = next(
            (
                item
                for item in manifest.get("presets", [])
                if isinstance(item, dict) and item.get("preset_id") == preset_id
            ),
            None,
        )
        if not isinstance(preset, dict):
            raise KeyError(f"Unknown manga model preset: {preset_id}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    active_key = _active_job_key(preset_id, project_id)
    with _download_lock:
        existing_job_id = _active_preset_download_jobs.get(active_key)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        display_name = str(preset.get("display_name") or preset_id)
        if bool(preset.get("available")):
            job = JobRegistry.create(
                stage="model_preset_download_completed",
                status="completed",
                project_id=project_id,
                progress=100,
                message=f"Manga model preset is already prepared: {display_name}",
            )
            JobRegistry.update(
                job.job_id,
                result={
                    "preset": preset,
                    "models": list(preset.get("models", []) or []),
                    "config_overrides": dict(preset.get("config_overrides") or {}),
                },
            )
            return (JobRegistry.get(job.job_id) or job).to_dict()

        job = JobRegistry.create(
            stage="model_preset_download_queued",
            status="running",
            project_id=project_id,
            progress=1,
            message=f"Queued manga model preset preparation: {display_name}",
        )
        _active_preset_download_jobs[active_key] = job.job_id

    thread = threading.Thread(target=_run_preset_download_job, args=(job.job_id, preset_id, active_key), daemon=True)
    thread.start()
    return job.to_dict()


@router.get("/models")
def list_models() -> list[dict[str, object]]:
    return MangaModelStore().list_statuses()


@router.get("/models/manager")
def get_model_manager_manifest() -> dict[str, object]:
    return MangaModelStore().build_manager_manifest()


@router.get("/fonts")
def list_fonts() -> list[dict[str, object]]:
    return [entry.to_dict() for entry in list_font_catalog()]


@router.get("/projects/{project_id}/fonts")
def list_project_fonts(project_id: str) -> list[dict[str, object]]:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return [entry.to_dict() for entry in list_font_catalog(session.project_path)]


@router.get("/models/{model_id}")
def get_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().get_status(normalize_model_id(model_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/readiness")
def get_runtime_readiness(
    manga_ocr_engine: str = "",
    manga_detect_engine: str = "",
    manga_segment_engine: str = "",
    manga_inpaint_engine: str = "",
    manga_runtime_device: str = "",
    manga_detect_device: str = "",
    manga_ocr_device: str = "",
    manga_inpaint_device: str = "",
) -> dict[str, object]:
    config_snapshot = {
        key: value
        for key, value in {
            "manga_ocr_engine": manga_ocr_engine,
            "manga_detect_engine": manga_detect_engine,
            "manga_segment_engine": manga_segment_engine,
            "manga_inpaint_engine": manga_inpaint_engine,
            "manga_runtime_device": manga_runtime_device,
            "manga_detect_device": manga_detect_device,
            "manga_ocr_device": manga_ocr_device,
            "manga_inpaint_device": manga_inpaint_device,
        }.items()
        if value
    }
    return build_manga_runtime_readiness(config_snapshot=config_snapshot).to_dict()


@router.post("/models/{model_id}/download")
def download_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().download(normalize_model_id(model_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download manga model package: {exc}") from exc


@router.post("/models/{model_id}/download/start")
def start_download_model(model_id: str) -> dict[str, object]:
    return _start_download_model_job(model_id)


@router.post("/projects/{project_id}/models/{model_id}/download/start")
def start_project_download_model(project_id: str, model_id: str) -> dict[str, object]:
    return _start_download_model_job(model_id, project_id=project_id)


@router.post("/model-presets/{preset_id}/download/start")
def start_download_model_preset(preset_id: str) -> dict[str, object]:
    return _start_download_model_preset_job(preset_id)


@router.post("/projects/{project_id}/model-presets/{preset_id}/download/start")
def start_project_download_model_preset(project_id: str, preset_id: str) -> dict[str, object]:
    return _start_download_model_preset_job(preset_id, project_id=project_id)
