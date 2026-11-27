"""System-level TUI capabilities exposed without constructing an interactive host."""
import os
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ModuleFolders.Infrastructure.TaskConfig import ConfigProfileService as profiles
from ModuleFolders.Service.TaskRuntime import system_management as service
from ModuleFolders.Service.TaskRuntime.activities import register_activity
from ModuleFolders.Service.TaskRuntime.jobs import JobConflict, get_job_manager
from ModuleFolders.Service.TaskRuntime import system_services
from Tools.APIServer.job_contracts import JobResponse
from Tools.APIServer.responses import ERROR_RESPONSES, ConfigResponse
from Tools.APIServer.system_contracts import (
    AcknowledgementsResponse,
    EbookPreviewRequest, EbookPreviewResponse,
    DiagnosticRequest, DiagnosticResponse, KnowledgeEntry, PlatformCallRequest,
    PlatformKeysRequest, PlatformSelectRequest, PlatformSummary, ProfileDocumentRequest,
    ProfileDocumentResponse, RecentActivateRequest, RecentCleanRequest, RecentProjectsRequest,
    RecentProjectsResponse, RevisionResponse, ServiceListResponse, ServiceReadinessResponse,
    ServiceStartRequest, ServiceStatus, ServiceStopRequest, SettingDescription,
    SettingsValidationRequest, SettingsValidationResponse,
)

router = APIRouter(prefix="/api/system", tags=["system"])
register_activity("system-services", lambda: False, system_services.shutdown_services)


def _caller(request):
    from Tools.APIServer.application import _caller_context
    return _caller_context(request)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except profiles.ConfigConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except JobConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(404, "Requested system resource does not exist") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _confirmed(value):
    if value is not True:
        raise HTTPException(409, "Explicit confirmation is required for this operation")


@router.get("/acknowledgements", response_model=AcknowledgementsResponse, responses=ERROR_RESPONSES)
def acknowledgements(language: Literal["zh_CN", "zh_CNTW", "en", "ja", "ko", "ru", "es"] = "en"):
    from ModuleFolders.Infrastructure.ProjectInfo import SPONSOR_IDS
    from ModuleFolders.UserInterface.AppI18N import I18NLoader
    i18n = I18NLoader(profiles.PROJECT_ROOT, language)
    return {"title": i18n.get("acknowledgements_title"), "introduction": i18n.get("acknowledgements_intro"),
            "sponsors": list(SPONSOR_IDS)}


@router.get("/settings-schema", response_model=list[SettingDescription], responses=ERROR_RESPONSES)
def get_settings_schema():
    return service.settings_schema()


@router.post("/settings/validate", response_model=SettingsValidationResponse, responses=ERROR_RESPONSES)
def validate_settings(payload: SettingsValidationRequest):
    return service.validate_settings(payload.values)


@router.post("/settings/ebook-preview", response_model=EbookPreviewResponse, responses=ERROR_RESPONSES)
def ebook_preview(payload: EbookPreviewRequest):
    from ModuleFolders.Domain.FileOutputer.EbookNaming import EbookIdentity, render_ebook_name
    return {"single": _call(render_ebook_name, payload.template, EbookIdentity(payload.series, "1")),
            "merged": _call(render_ebook_name, payload.template, EbookIdentity(payload.series, "1-7"))}


@router.get("/platforms", response_model=list[PlatformSummary], responses=ERROR_RESPONSES)
def list_platforms():
    return service.platform_summaries()


@router.post("/platforms/select", response_model=RevisionResponse, responses=ERROR_RESPONSES)
def select_platform(payload: PlatformSelectRequest, request: Request):
    revision = _call(service.select_platform, payload.platform, payload.task, payload.model,
                     payload.expected_revision, _caller(request))
    return {"revision": revision}


@router.post("/platforms/keys", response_model=RevisionResponse, responses=ERROR_RESPONSES)
def import_platform_keys(payload: PlatformKeysRequest, request: Request):
    revision = _call(service.import_platform_keys, payload.platform, payload.keys_text.get_secret_value(),
                     payload.expected_revision, _caller(request))
    return {"revision": revision}


@router.post("/platforms/validate", response_model=JobResponse, responses=ERROR_RESPONSES)
def validate_platform(payload: PlatformCallRequest):
    _confirmed(payload.confirmed)
    return _call(get_job_manager().start, "platform-validation",
                 lambda cancel: service.validate_platform(payload.platform, cancel))


@router.post("/platforms/models", response_model=JobResponse, responses=ERROR_RESPONSES)
def discover_platform_models(payload: PlatformCallRequest):
    _confirmed(payload.confirmed)
    return _call(get_job_manager().start, "platform-model-discovery",
                 lambda cancel: service.platform_models(payload.platform, cancel))


@router.get("/diagnostics/knowledge", response_model=list[KnowledgeEntry], responses=ERROR_RESPONSES)
def diagnostic_knowledge(language: str = "zh_CN", query: str = "", category: str | None = None,
                         limit: int = Query(50, ge=1, le=500)):
    return service.diagnostic_knowledge(language, query, category, limit)


@router.post("/diagnostics/run", response_model=DiagnosticResponse | JobResponse, responses=ERROR_RESPONSES)
def diagnose(payload: DiagnosticRequest):
    if payload.allow_llm:
        _confirmed(payload.confirmed)
        return _call(get_job_manager().start, "diagnostic-analysis",
                     lambda cancel: service.diagnose(payload.error_text, payload.language, True, cancel))
    return service.diagnose(payload.error_text, payload.language, False, threading.Event())


@router.get("/recent-projects", response_model=RecentProjectsResponse, responses=ERROR_RESPONSES)
def recent_projects():
    return service.recent_projects()


@router.put("/recent-projects", response_model=RecentProjectsResponse, responses=ERROR_RESPONSES)
def save_recent_projects(payload: RecentProjectsRequest, request: Request):
    return _call(service.save_recent_projects, [item.model_dump() for item in payload.projects],
                 payload.expected_revision, _caller(request))


@router.post("/recent-projects/clean", response_model=RecentProjectsResponse, responses=ERROR_RESPONSES)
def clean_recent_projects(payload: RecentCleanRequest, request: Request):
    return _call(service.clean_recent_projects, payload.expected_revision, _caller(request))


@router.post("/recent-projects/activate", response_model=ConfigResponse, responses=ERROR_RESPONSES)
def activate_recent_project(payload: RecentActivateRequest, request: Request):
    from ModuleFolders.Service.TaskRuntime.configuration import read_configuration
    with profiles.config_transaction():
        item = _call(service.recent_project_task, payload.path, payload.expected_revision)
        for field, directory, allow_none in (("profile", profiles.PROFILES_PATH, False),
                                              ("rules_profile", profiles.RULES_PROFILES_PATH, True)):
            path, name = _call(profiles.resolve_profile_path, directory, item[field], allow_none=allow_none)
            if name != "None" and not os.path.isfile(path):
                raise HTTPException(404, "Bound project profile no longer exists")
        root = profiles.load_root_config()
        root.update(active_profile=item["profile"], active_rules_profile=item["rules_profile"])
        profiles.save_root_config(root)
        profiles.save_setting_value("label_input_path", item["input_path"])
        return read_configuration(_caller(request))


@router.get("/profile-documents/{name}", response_model=ProfileDocumentResponse, responses=ERROR_RESPONSES)
def get_profile_document(name: str, request: Request):
    return _call(service.profile_document, name, _caller(request))


@router.put("/profile-documents/{name}", response_model=ProfileDocumentResponse, responses=ERROR_RESPONSES)
def save_profile_document(name: str, payload: ProfileDocumentRequest, request: Request):
    return _call(service.save_profile_document, name, payload.content, payload.expected_revision, _caller(request))


@router.get("/services/readiness", response_model=ServiceReadinessResponse, responses=ERROR_RESPONSES)
def service_readiness():
    from Tools.MCPServer.runtime import inspect_mcp_runtime
    from Tools.Skills.runtime import inspect_skills_runtime
    return {"mcp": inspect_mcp_runtime(), "skills": inspect_skills_runtime()}


@router.get("/services", response_model=ServiceListResponse, responses=ERROR_RESPONSES)
def list_services():
    return {"services": system_services.list_services()}


@router.post("/services/{name}/start", response_model=JobResponse, responses=ERROR_RESPONSES)
def start_service(name: Literal["mcp", "skills"], payload: ServiceStartRequest):
    from Tools.APIServer import server
    from Tools.APIServer import application
    from ModuleFolders.Infrastructure.RemoteAccessPolicy import ensure_bind_allowed
    _confirmed(payload.confirmed)
    config = profiles.load_effective_config(create_missing=False)
    _call(ensure_bind_allowed, payload.host, config.get("enable_remote_access") is True, name)
    backend = server.get_active_owner()
    if name == "mcp" and backend is None:
        raise HTTPException(409, "An active API listener is required before starting MCP")
    env_name = "AINIEE_MCP_AUTH_TOKEN" if name == "mcp" else "AINIEE_SKILLS_AUTH_TOKEN"
    token = payload.auth_token.get_secret_value() if payload.auth_token else os.environ.get(env_name, "")
    if name == "mcp":
        if backend.get("mcp_auth_token"):
            if token and token != backend["mcp_auth_token"]:
                raise HTTPException(409, "The MCP service must use the API owner's existing token")
            token = backend["mcp_auth_token"]
        elif token:
            token = server.bind_mcp_auth_token_if_unset(token)
    if not token:
        raise HTTPException(422, "Supply an authentication token; it will only be passed to the service environment")

    def launch(cancel):
        from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob, CommittedResult
        if cancel.is_set():
            raise CancelledJob()
        result = system_services.start_service(
            name, host=payload.host, port=payload.port, transport=payload.transport, path=payload.path,
            auth_token=token, backend=backend, config=config, project_root=application.PROJECT_ROOT, cancel=cancel,
        )
        if cancel.is_set():
            stopped = system_services.stop_service(name, result["service_id"])
            if stopped["status"] != "stopped":
                raise RuntimeError("Service cancellation cleanup is pending")
            raise CancelledJob()
        return CommittedResult(result)
    return _call(get_job_manager().start, "service-start-" + name, launch, exclusive=False)


@router.post("/services/{name}/stop", response_model=ServiceStatus, responses=ERROR_RESPONSES)
def stop_service(name: Literal["mcp", "skills"], payload: ServiceStopRequest):
    _confirmed(payload.confirmed)
    return _call(system_services.stop_service, name, payload.service_id)
