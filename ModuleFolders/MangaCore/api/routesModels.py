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
_active_all_download_jobs: dict[str, str] = {}

_MODEL_DOWNLOAD_STAGE_PROGRESS: dict[str, int] = {
    "queued": 1,
    "started": 3,
    "model_started": 5,
    "asset": 8,
    "status": 10,
    "downloading": 20,
    "snapshot": 25,
    "wrapper_download": 25,
    "asset_completed": 92,
    "registering": 96,
    "summary": 98,
    "completed": 99,
    "model_completed": 99,
}


def _active_job_key(item_id: str, project_id: str = "") -> str:
    return f"{project_id}:{item_id}" if project_id else item_id


def _model_display_name(status: dict[str, object], model_id: str) -> str:
    return str(status.get("display_name") or status.get("model_id") or model_id)


def _clamp_progress(value: int) -> int:
    return max(0, min(100, int(value)))


def _download_event_progress(event: dict[str, object]) -> int:
    stage = str(event.get("stage") or "")
    base = _MODEL_DOWNLOAD_STAGE_PROGRESS.get(stage, 10)
    item_index = int(event.get("item_index") or 0)
    item_count = max(1, int(event.get("item_count") or 1))
    item_offset = max(0, item_index - 1) / item_count
    item_span = 1 / item_count

    bytes_total = int(event.get("bytes_total") or 0)
    bytes_downloaded = int(event.get("bytes_downloaded") or 0)
    if bytes_total > 0:
        byte_ratio = max(0.0, min(1.0, bytes_downloaded / bytes_total))
        return _clamp_progress(int((item_offset + item_span * byte_ratio) * 90) + 5)

    if stage in {"asset", "status", "downloading", "snapshot", "wrapper_download"}:
        return _clamp_progress(int(item_offset * 90) + base)
    if stage in {"asset_completed", "registering", "summary", "completed", "model_completed"}:
        return _clamp_progress(int((item_offset + item_span) * 90) + min(base, 9))
    return _clamp_progress(base)


def _merge_download_progress(
    *,
    outer_index: int,
    outer_count: int,
    inner_progress: int,
) -> int:
    outer_count = max(1, int(outer_count or 1))
    outer_index = max(1, int(outer_index or 1))
    inner_ratio = max(0.0, min(1.0, inner_progress / 100))
    return _clamp_progress(int((((outer_index - 1) + inner_ratio) / outer_count) * 95) + 3)


def _download_progress_callback(
    job_id: str,
    *,
    stage: str,
    model_id: str,
    display_name: str = "",
    outer_index: int = 1,
    outer_count: int = 1,
):
    def handle(event: dict[str, object]) -> None:
        payload = dict(event)
        payload.setdefault("kind", "manga_model_download")
        payload.setdefault("model_id", model_id)
        if display_name:
            payload.setdefault("display_name", display_name)
        payload["model_index"] = outer_index
        payload["model_count"] = outer_count
        inner_progress = _download_event_progress(payload)
        payload["inner_progress"] = inner_progress
        progress = _merge_download_progress(
            outer_index=outer_index,
            outer_count=outer_count,
            inner_progress=inner_progress,
        )
        message = str(payload.get("message") or f"Preparing manga model package: {display_name or model_id}")
        JobRegistry.update(
            job_id,
            stage=stage,
            status="running",
            progress=progress,
            message=message,
            result={"progress": payload},
        )

    return handle


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
        result = store.download(
            model_id,
            quiet=True,
            progress_callback=_download_progress_callback(
                job_id,
                stage="model_download_running",
                model_id=model_id,
                display_name=display_name,
            ),
        )
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
            model_status = store.get_status(model_id)
            model_display_name = _model_display_name(model_status, model_id)
            JobRegistry.update(
                job_id,
                stage="model_preset_download_running",
                status="running",
                progress=max(5, int((index - 1) / len(model_ids) * 95)),
                message=f"Preparing manga model preset {display_name}: {model_display_name} ({index}/{len(model_ids)})",
                result={
                    "progress": {
                        "kind": "manga_model_download",
                        "stage": "model_started",
                        "model_id": model_id,
                        "display_name": model_display_name,
                        "model_index": index,
                        "model_count": len(model_ids),
                    }
                },
            )
            status = model_status
            if not status.get("available"):
                status = store.download(
                    model_id,
                    quiet=True,
                    progress_callback=_download_progress_callback(
                        job_id,
                        stage="model_preset_download_running",
                        model_id=model_id,
                        display_name=model_display_name,
                        outer_index=index,
                        outer_count=len(model_ids),
                    ),
                )
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


def _run_all_models_download_job(job_id: str, active_key: str) -> None:
    store = MangaModelStore()
    try:
        manifest = store.build_manager_manifest()
        model_ids = [str(model_id) for model_id in manifest.get("model_ids", []) if str(model_id)]
        if not model_ids:
            raise RuntimeError("Manga model catalog is empty.")

        prepared: list[dict[str, object]] = []
        for index, model_id in enumerate(model_ids, start=1):
            model_status = store.get_status(model_id)
            model_display_name = _model_display_name(model_status, model_id)
            JobRegistry.update(
                job_id,
                stage="model_all_download_running",
                status="running",
                progress=max(5, int((index - 1) / len(model_ids) * 95)),
                message=f"Preparing all manga model packages: {model_display_name} ({index}/{len(model_ids)})",
                result={
                    "progress": {
                        "kind": "manga_model_download",
                        "stage": "model_started",
                        "model_id": model_id,
                        "display_name": model_display_name,
                        "model_index": index,
                        "model_count": len(model_ids),
                    }
                },
            )
            status = model_status
            if not status.get("available"):
                status = store.download(
                    model_id,
                    quiet=True,
                    progress_callback=_download_progress_callback(
                        job_id,
                        stage="model_all_download_running",
                        model_id=model_id,
                        display_name=model_display_name,
                        outer_index=index,
                        outer_count=len(model_ids),
                    ),
                )
            prepared.append(status)

        refreshed = store.build_manager_manifest()
        JobRegistry.update(
            job_id,
            stage="model_all_download_completed",
            status="completed",
            progress=100,
            message="Prepared all manga model packages.",
            result={
                "models": prepared,
                "manifest": refreshed,
                "model_ids": list(refreshed.get("model_ids", []) or []),
                "available_model_ids": list(refreshed.get("available_model_ids", []) or []),
                "missing_model_ids": list(refreshed.get("missing_model_ids", []) or []),
                "missing_count": int(refreshed.get("missing_count") or 0),
                "model_count": int(refreshed.get("model_count") or 0),
                "config_overrides": {},
            },
        )
    except Exception as exc:
        JobRegistry.update(
            job_id,
            stage="model_all_download_failed",
            status="failed",
            progress=0,
            message="Failed to prepare all manga model packages.",
            error_message=str(exc),
        )
    finally:
        with _download_lock:
            if _active_all_download_jobs.get(active_key) == job_id:
                _active_all_download_jobs.pop(active_key, None)


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


def _start_download_all_models_job(*, project_id: str = "") -> dict[str, object]:
    manifest = MangaModelStore().build_manager_manifest()
    active_key = _active_job_key("all", project_id)
    with _download_lock:
        existing_job_id = _active_all_download_jobs.get(active_key)
        existing_job = JobRegistry.get(existing_job_id) if existing_job_id else None
        if existing_job is not None and existing_job.status == "running":
            return existing_job.to_dict()

        if bool(manifest.get("available")):
            job = JobRegistry.create(
                stage="model_all_download_completed",
                status="completed",
                project_id=project_id,
                progress=100,
                message="All manga model packages are already prepared.",
            )
            JobRegistry.update(
                job.job_id,
                result={
                    "models": list(manifest.get("models", []) or []),
                    "manifest": manifest,
                    "model_ids": list(manifest.get("model_ids", []) or []),
                    "available_model_ids": list(manifest.get("available_model_ids", []) or []),
                    "missing_model_ids": list(manifest.get("missing_model_ids", []) or []),
                    "missing_count": int(manifest.get("missing_count") or 0),
                    "model_count": int(manifest.get("model_count") or 0),
                    "config_overrides": {},
                },
            )
            return (JobRegistry.get(job.job_id) or job).to_dict()

        job = JobRegistry.create(
            stage="model_all_download_queued",
            status="running",
            project_id=project_id,
            progress=1,
            message="Queued all manga model package preparation.",
        )
        _active_all_download_jobs[active_key] = job.job_id

    thread = threading.Thread(target=_run_all_models_download_job, args=(job.job_id, active_key), daemon=True)
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
        return MangaModelStore().download(normalize_model_id(model_id), quiet=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download manga model package: {exc}") from exc


@router.post("/models/download-all")
def download_all_models() -> dict[str, object]:
    try:
        return MangaModelStore().download_all(quiet=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download all manga model packages: {exc}") from exc


@router.post("/models/{model_id}/download/start")
def start_download_model(model_id: str) -> dict[str, object]:
    return _start_download_model_job(model_id)


@router.post("/projects/{project_id}/models/{model_id}/download/start")
def start_project_download_model(project_id: str, model_id: str) -> dict[str, object]:
    return _start_download_model_job(model_id, project_id=project_id)


@router.post("/models/download-all/start")
def start_download_all_models() -> dict[str, object]:
    return _start_download_all_models_job()


@router.post("/projects/{project_id}/models/download-all/start")
def start_project_download_all_models(project_id: str) -> dict[str, object]:
    return _start_download_all_models_job(project_id=project_id)


@router.post("/model-presets/{preset_id}/download/start")
def start_download_model_preset(preset_id: str) -> dict[str, object]:
    return _start_download_model_preset_job(preset_id)


@router.post("/projects/{project_id}/model-presets/{preset_id}/download/start")
def start_project_download_model_preset(project_id: str, preset_id: str) -> dict[str, object]:
    return _start_download_model_preset_job(preset_id, project_id=project_id)
