"""Authenticated HTTP adapters for media capabilities shared with the TUI."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from Tools.APIServer.media_contracts import (
    MediaDiagnosticsResponse, MediaHistoryResponse, MediaJobResponse, MediaModelsResponse, MediaPreferencesResponse,
    MediaPreferencesSaved, MediaPreferencesUpdate, MediaRecordingRequest, MediaRuntimeRequest,
    MediaRuntimeResponse, MediaSessionRequest, MediaSessionResponse, MediaSuccess,
    MediaTextRequest, MediaTextResponse,
)
from Tools.APIServer.responses import ERROR_RESPONSES
from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request

router = APIRouter(prefix="/api/media", tags=["media"])


def _approve_external(request, confirmed, *, session_id=None, require_session=False):
    if is_mcp_request(request):
        if not confirmed:
            raise HTTPException(409, "Approve external processing of this media session before accessing its content")
        if require_session and not session_id:
            raise HTTPException(422, "A specific media session_id is required for external content access")


def _control_result(request, state):
    if is_mcp_request(request):
        return {**state, "events": [], "result": None, "record_path": None}
    return state


def _call(operation, *args, **kwargs):
    from ModuleFolders.Service.TaskRuntime.media import MediaConflict, MediaNotFound
    from ModuleFolders.Service.TaskRuntime.jobs import JobConflict
    from ModuleFolders.Media.preferences import PreferenceConflict
    try:
        return operation(*args, **kwargs)
    except (MediaConflict, JobConflict, PreferenceConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (MediaNotFound, KeyError) as exc:
        raise HTTPException(status_code=404, detail="Media session or job not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid media settings or unavailable input/model files") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Media runtime is not ready for this operation") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Media filesystem or process operation failed") from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Media dependencies are not installed in this runtime") from exc


@router.get("/settings", response_model=MediaPreferencesResponse, responses=ERROR_RESPONSES)
def get_media_settings():
    from ModuleFolders.Service.TaskRuntime.media import preferences
    return _call(preferences)


@router.put("/settings", response_model=MediaPreferencesSaved, responses=ERROR_RESPONSES)
def put_media_settings(payload: MediaPreferencesUpdate):
    from ModuleFolders.Service.TaskRuntime.media import update_preferences
    return _call(update_preferences, payload.changes, payload.expected_revision)


@router.get("/models", response_model=MediaModelsResponse, responses=ERROR_RESPONSES)
def get_media_models():
    from ModuleFolders.Service.TaskRuntime.media import model_catalog
    return _call(model_catalog)


@router.get("/runtime", response_model=MediaRuntimeResponse, responses=ERROR_RESPONSES)
def get_media_runtime():
    from ModuleFolders.Service.TaskRuntime.media import runtime_status
    return _call(runtime_status)


@router.post("/runtime/{action}", response_model=MediaJobResponse, responses=ERROR_RESPONSES)
def prepare_media_runtime(action: Literal["probe", "devices", "applications", "install", "configure", "download", "ffmpeg"], payload: MediaRuntimeRequest):
    from ModuleFolders.Service.TaskRuntime.media import runtime_action
    return _call(runtime_action, action, payload.options.model_dump(exclude_none=True), payload.confirmed)


@router.get("/runtime/jobs/{job_id}", response_model=MediaJobResponse, responses=ERROR_RESPONSES)
def get_media_runtime_job(job_id: str, cursor: int = Query(default=0, ge=0)):
    from ModuleFolders.Service.TaskRuntime.media import runtime_job
    return _call(runtime_job, job_id, cursor)


@router.post("/runtime/jobs/{job_id}/stop", response_model=MediaJobResponse, responses=ERROR_RESPONSES)
def stop_media_runtime_job(job_id: str):
    from ModuleFolders.Service.TaskRuntime.media import runtime_job
    from ModuleFolders.Service.TaskRuntime.jobs import get_job_manager
    _call(runtime_job, job_id)
    return _call(get_job_manager().cancel, job_id)


@router.post("/sessions/{mode}", response_model=MediaSessionResponse, responses=ERROR_RESPONSES)
def start_media_session(mode: Literal["live", "video"], payload: MediaSessionRequest, request: Request):
    _approve_external(request, payload.user_confirmed_external_processing)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    state = _call(get_media_controller().start, mode, payload.options.model_dump(exclude_none=True), payload.confirmed)
    return _control_result(request, state)


@router.get("/sessions/status", response_model=MediaSessionResponse, responses=ERROR_RESPONSES)
def get_media_session_status(request: Request, session_id: str | None = None, cursor: int = Query(default=0, ge=0), user_confirmed_external_processing: bool = False):
    _approve_external(request, user_confirmed_external_processing, session_id=session_id, require_session=True)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().status, session_id, cursor)


@router.get("/sessions/diagnostics", response_model=MediaDiagnosticsResponse, responses=ERROR_RESPONSES)
def get_media_diagnostics(session_id: str | None = None, cursor: int = Query(default=0, ge=0)):
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().diagnostics, session_id, cursor)


@router.post("/sessions/{session_id}/stop", response_model=MediaSessionResponse, responses=ERROR_RESPONSES)
def stop_media_session(session_id: str, request: Request):
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _control_result(request, _call(get_media_controller().stop, session_id))


@router.get("/sessions/{session_id}/history", response_model=MediaHistoryResponse, responses=ERROR_RESPONSES)
def get_media_history(session_id: str, request: Request, start: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), user_confirmed_external_processing: bool = False):
    _approve_external(request, user_confirmed_external_processing)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().history, session_id, start, limit)


@router.delete("/sessions/{session_id}/history", response_model=MediaSuccess, responses=ERROR_RESPONSES)
def clear_media_history(session_id: str):
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().clear_history, session_id)


@router.put("/sessions/{session_id}/recording", response_model=MediaSessionResponse, responses=ERROR_RESPONSES)
def set_media_recording(session_id: str, payload: MediaRecordingRequest, request: Request):
    if payload.enabled:
        _approve_external(request, payload.user_confirmed_external_processing)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _control_result(request, _call(get_media_controller().recording, session_id, payload.enabled, payload.directory))


@router.post("/sessions/{session_id}/translate", response_model=MediaTextResponse, responses=ERROR_RESPONSES)
def translate_media_text(session_id: str, payload: MediaTextRequest, request: Request):
    _approve_external(request, payload.user_confirmed_external_processing)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().translate_text, session_id, **payload.model_dump(exclude={"user_confirmed_external_processing"}))


@router.delete("/sessions/{session_id}/translate/{request_id}", response_model=MediaSuccess, responses=ERROR_RESPONSES)
def cancel_media_text(session_id: str, request_id: str):
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    return _call(get_media_controller().cancel_text, session_id, request_id)


@router.get("/sessions/{session_id}/files/{artifact}", responses=ERROR_RESPONSES)
def download_media_artifact(session_id: str, artifact: Literal["video", "source_srt", "translated_srt", "record"], request: Request, user_confirmed_external_processing: bool = False) -> FileResponse:
    _approve_external(request, user_confirmed_external_processing)
    from ModuleFolders.Service.TaskRuntime.media import get_media_controller
    path = _call(get_media_controller().output_file, session_id, artifact)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
