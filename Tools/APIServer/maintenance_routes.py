"""Authenticated maintenance adapters; long work is owned by the shared job manager."""
import subprocess

from fastapi import APIRouter, HTTPException

from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import ConfigConflictError
from ModuleFolders.Service.TaskRuntime.jobs import JobConflict, get_job_manager
from Tools.APIServer.job_contracts import JobResponse
from Tools.APIServer.maintenance_contracts import (
    MangaDefaultsRequest, MangaInstallRequest, MangaRuntimeResponse,
    MaintenanceResult, UpdateInfoResponse, UpdateRequest,
)
from Tools.APIServer.responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


def _maintenance():
    try:
        from ModuleFolders.Service.TaskRuntime import maintenance
        return maintenance
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Maintenance runtime dependencies are unavailable") from exc


def _confirmed(request):
    if request.confirmed is not True:
        raise HTTPException(status_code=409, detail="Explicit maintenance confirmation is required")


def _start(kind, work):
    try:
        return get_job_manager().start(kind, work)
    except JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/updates", response_model=UpdateInfoResponse, responses=ERROR_RESPONSES)
def get_update_info():
    return _maintenance().update_info()


@router.post("/updates/start", response_model=JobResponse, responses=ERROR_RESPONSES)
def start_update(request: UpdateRequest):
    _confirmed(request)
    if request.target == "application" and request.channel == "build":
        raise HTTPException(status_code=422, detail="Only Web assets support local build")
    if request.target == "web" and request.channel == "main":
        raise HTTPException(status_code=422, detail="Web assets support stable or preview releases")
    maintenance = _maintenance()
    return _start("maintenance-update", lambda cancel: maintenance.apply_update(request, cancel))


@router.get("/manga/runtime", response_model=MangaRuntimeResponse, responses=ERROR_RESPONSES)
def get_manga_runtime(probe: bool = False):
    try:
        return _maintenance().manga_runtime(probe=probe)
    except (ImportError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail="Project runtime is unavailable") from exc


@router.post("/manga/runtime/install", response_model=JobResponse, responses=ERROR_RESPONSES)
def install_manga_runtime(request: MangaInstallRequest):
    _confirmed(request)
    maintenance = _maintenance()
    return _start("maintenance-manga-runtime", lambda cancel: maintenance.install_manga_runtime(request.backend, cancel))


@router.put("/manga/defaults", response_model=MaintenanceResult, responses=ERROR_RESPONSES)
def set_manga_defaults(request: MangaDefaultsRequest):
    _confirmed(request)
    maintenance = _maintenance()
    from ModuleFolders.Service.TaskRuntime.manager import TaskManager
    from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
    manager = TaskManager()
    with manager._lock:
        if manager.task_conflict_detail() or QueueManager(read_only=True).is_running:
            raise HTTPException(status_code=409, detail="Wait for active work to finish before changing Manga defaults")
        try:
            return maintenance.set_manga_defaults(request)
        except ConfigConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Manga model management dependencies are unavailable") from exc
