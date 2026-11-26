# Public HTTP API adapters; browser static hosting lives in Tools.WebServer.
import os
import sys
import json
import re
import secrets
import shutil
import threading
import time
from pathlib import Path
import uuid
import hashlib
import asyncio
import weakref
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Any, Optional

# --- Pre-emptive Import for FastAPI & Pydantic ---
try:
    from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Response, BackgroundTasks, Query, Request, APIRouter
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
except ImportError:
    # This error will be caught and handled in ainiee_cli.py
    raise ImportError("Required packages are missing. Please run 'uv add fastapi uvicorn[standard] pydantic python-multipart'.,Or run 'uv sync'")

# --- Add Project Root to Python Path ---
# This ensures that we can import modules from the main project (e.g., ainiee_cli)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPDATETEMP_PATH = os.path.join(PROJECT_ROOT, "updatetemp") # Define upload directory
TEMP_EDIT_PATH = os.path.join(PROJECT_ROOT, "output", "temp_edit") # Define draft directory

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.Infrastructure.TaskContract import (
    TASK_API_KEY_ENV,
    TaskContractError,
    TaskSpec,
    normalize_task_name,
)
from ModuleFolders.Infrastructure.LLMRequester.SdkRequestMode import sync_sdk_request_mode_config
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.RemoteAccessPolicy import (
    REMOTE_ACCESS_CONFIG_KEY,
    ensure_bind_allowed,
    is_loopback_bind_host,
)
from ModuleFolders.Infrastructure.ApiSecurity import (
    AUTH_REQUIRED_HEADER,
    INTERNAL_AUTH_ENV,
    INTERNAL_AUTH_HEADER,
    MCP_AUTH_HEADER,
    MCP_SECRET_PLACEHOLDER,
    WEB_SESSION_AUTH_REQUIRED,
    WEB_SESSION_COOKIE_NAME,
    contains_redacted_secret,
    is_mcp_request,
    restore_redacted_json_text,
    restore_redacted_secrets,
    sanitize_data_for_mcp,
    sanitize_json_text_for_mcp,
    strip_mcp_security_metadata,
)
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    ConfigConflictError,
    RULE_PROFILE_KEYS,
    atomic_write_json,
    config_revision,
    config_transaction,
    deep_merge,
    list_profile_names,
    load_effective_config,
    load_json_file,
    load_master_preset,
    load_root_config,
    normalize_rules_payload,
    PROFILE_ORIGIN_KEY,
    profile_origin_for_new_profile,
    resolve_profile_path,
    save_effective_config,
    save_root_config,
    save_rule_value,
    save_setting_value,
    sanitize_profile_name,
    split_effective_config,
)

_MANGA_OPTIONAL_HINT = "主程序其它功能不受影响；只有在使用漫画翻译时才需要补齐漫画模块。"

try:
    from ModuleFolders.MangaCore.api import router as manga_router
    _MANGA_ROUTER_IMPORT_ERROR = None
except Exception as exc:
    _MANGA_ROUTER_IMPORT_ERROR = exc
    manga_router = APIRouter(prefix="/api/manga", tags=["manga"])

    @manga_router.api_route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def manga_api_unavailable_root():
        raise HTTPException(
            status_code=503,
            detail=f"漫画模块当前不可用。{_MANGA_OPTIONAL_HINT} 导入错误: {_MANGA_ROUTER_IMPORT_ERROR}",
        )

    @manga_router.api_route("/{asset_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def manga_api_unavailable(asset_path: str):
        _ = asset_path
        raise HTTPException(
            status_code=503,
            detail=f"漫画模块当前不可用。{_MANGA_OPTIONAL_HINT} 导入错误: {_MANGA_ROUTER_IMPORT_ERROR}",
        )

# --- Global State & Task Management ---

from ModuleFolders.Service.TaskRuntime.manager import (
    EXTERNAL_AGENT_STATUS_TRANSITIONS,
    TASK_ACTIVE_STATUSES,
    TASK_EXTERNAL_STATUSES,
    WEB_TASK_API_KEY_ENV,
    WEB_TASK_ID_ENV,
    TaskManager,
    resolve_task_worker_python,
)

task_manager = TaskManager()

# --- Global System Mode ---
# monitor: Only monitoring is allowed
# full: Full control (default)
SYSTEM_MODE = "full"

# --- Simple In-Memory Caches for API Endpoints ---
_version_cache: Dict[str, Any] = {}
_config_cache: Dict[str, Any] = {}
_web_i18n_cache: Dict[str, Dict[str, str]] = {}
_profiles_cache: Optional[List[str]] = None

# --- Profile Handlers (Dependency Injection) ---
# Allows the host application (ainiee_cli.py) to override logic
profile_handlers: Dict[str, Any] = {
    "create": None,
    "rename": None,
    "delete": None
}

# --- Queue Handlers (Dependency Injection) ---
# Retained for legacy host integrations; HTTP queue execution uses the task owner.
queue_handlers: Dict[str, Any] = {
    "run": None
}

from Tools.APIServer.contracts import (
    GlossaryAnalysisRequest,
    GlossaryAnalysisPreflightRequest,
    GlossaryAnalysisStatus,
    SaveAnalysisRequest,
    PlatformCreateRequest,
    InternalComparisonPayload,
    CacheItem,
    CacheUpdateRequest,
    CacheLoadRequest,
    CacheRestoreRequest,
    ProofreadStartRequest,
    ProofreadSuggestionActionRequest,
    ProofreadReviewStateRequest,
    CacheUpdateRequestWithPath,
    ProofreadSingleRequest,
    InternalLogPayload,
    AppConfig,
    ProfileSwitchRequest,
    RulesProfileSwitchRequest,
    RulesProfileDeleteRequest,
    ProfileCreateRequest,
    ProfileRenameRequest,
    ProfileDeleteRequest,
    GlossaryItem,
    TermOption,
    TermRetryRequest,
    ExclusionItem,
    ReplacementRuleItem,
    CharacterizationItem,
    TranslationExampleItem,
    StringContent,
    PluginEnableRequest,
    DeleteFileRequest,
    QueueTaskItem,
    QueueTaskUpdate,
    QueueMoveRequest,
    QueueReorderRequest,
    QueueRawRequest,
    TaskPayload,
    ExternalAgentTaskPayload,
    TaskControlPayload,
    ExternalAgentStatusPayload,
    RuntimeIdentity,
    TaskStartResponse,
    TaskStatusResponse,
    TaskPreviewResponse,
)

from Tools.APIServer.responses import (
    ERROR_RESPONSES,
    PROOFREAD_REVIEW_RESPONSES,
    AnalysisPreflightResponse,
    AnalysisSaveResponse,
    AnalysisStateResponse,
    CacheBackupsResponse,
    CacheItemsResponse,
    CacheLoadResponse,
    CacheRestoreResponse,
    CacheSearchResponse,
    CacheStatusResponse,
    CacheUpdateResponse,
    ConfigResponse, ConfigSaveResponse,
    ExternalTaskStatusResponse,
    FileDeleteResponse,
    MessageResponse,
    ModeResponse,
    PlatformCreateResponse,
    PluginResponse,
    ProofreadAcceptResponse,
    ProofreadLocateResponse,
    ProofreadReportResponse,
    ProofreadReportsResponse,
    ProofreadReviewResponse,
    ProofreadReviewStateResponse,
    ProofreadSingleResponse,
    ProofreadStateResponse,
    QueueItemResponse,
    QueueRawResponse,
    QueueRunResponse,
    RuleMutationResponse,
    RuleRecord,
    RuntimeParametersResponse,
    StatusResponse,
    SuccessResponse,
    TemporaryFileResponse,
    TermTranslationResponse,
    UploadLimitResponse,
    UploadedFileResponse,
    VersionResponse,
)

# --- FastAPI Application ---

app = FastAPI(title="AiNiee CLI Backend API")
app.include_router(manga_router)


@app.exception_handler(Exception)
async def handle_unexpected_api_error(request: Request, error: Exception):
    import logging
    logging.getLogger(__name__).error("API operation failed (%s).", type(error).__name__)
    return JSONResponse(status_code=500, content={"detail": "API operation failed. Check the server logs."})

# --- Paths to Resources ---
RESOURCE_PATH = os.path.join(PROJECT_ROOT, "Resource")
VERSION_FILE = os.path.join(RESOURCE_PATH, "Version", "version.json")
PROFILES_PATH = os.path.join(RESOURCE_PATH, "profiles")
RULES_PROFILES_PATH = os.path.join(RESOURCE_PATH, "rules_profiles")
ROOT_CONFIG_FILE = os.path.join(RESOURCE_PATH, "config.json")
PRESET_PATH = os.path.join(RESOURCE_PATH, "platforms", "preset.json")
WEB_SESSION_TOKEN = os.environ.get("AINIEE_WEB_SESSION_TOKEN", "") or secrets.token_urlsafe(32)
MCP_AUTH_TOKEN = os.environ.get("AINIEE_MCP_AUTH_TOKEN", "")
INTERNAL_API_TOKEN = os.environ.get(INTERNAL_AUTH_ENV, "") or secrets.token_urlsafe(32)
RUNTIME_ID = str(uuid.uuid4())
WORKSPACE_ID = hashlib.sha256(os.path.normcase(os.path.realpath(PROJECT_ROOT)).encode()).hexdigest()
REMOTE_ACCESS_ENABLED = False
# Explicit origins are useful when the Web UI is published behind a TLS
# reverse proxy.  They are intentionally opt-in; an empty value keeps the
# strict same-origin check below.
WEB_ALLOWED_ORIGINS_ENV = "AINIEE_WEB_ALLOWED_ORIGINS"
PUBLIC_API_ROUTES = {
    ("POST", "/api/session/bootstrap"),
    ("GET", "/api/version"),
    ("GET", "/api/system/mode"),
}

# --- Helper Functions ---


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _is_loopback_bind_host(host: str) -> bool:
    return is_loopback_bind_host(host)


def _is_internal_api_path(path: str) -> bool:
    return path == "/api/internal" or path.startswith("/api/internal/")


def _is_public_api_request(request: Request) -> bool:
    if request.method.upper() == "OPTIONS":
        return True
    return (request.method.upper(), request.url.path) in PUBLIC_API_ROUTES


def _has_valid_web_session(request: Request) -> bool:
    token = request.cookies.get(WEB_SESSION_COOKIE_NAME, "")
    return bool(token) and secrets.compare_digest(token, WEB_SESSION_TOKEN)


def _has_valid_mcp_auth(request: Request) -> bool:
    if not is_mcp_request(request):
        return False
    if not MCP_AUTH_TOKEN:
        return False
    token = request.headers.get(MCP_AUTH_HEADER, "")
    return bool(token) and secrets.compare_digest(token, MCP_AUTH_TOKEN)


def _has_valid_internal_auth(request: Request) -> bool:
    token = request.headers.get(INTERNAL_AUTH_HEADER, "")
    return bool(token) and secrets.compare_digest(token, INTERNAL_API_TOKEN)


def _normalise_origin(value: str) -> str:
    """Normalise an origin for exact, scheme/host/port comparisons."""
    return str(value or "").strip().rstrip("/").lower()


def _configured_web_origins() -> set[str]:
    """Return explicitly trusted Web UI origins from env/configuration."""
    values = os.environ.get(WEB_ALLOWED_ORIGINS_ENV, "")
    try:
        # The setting is stored with the rest of the WebServer options.  Do
        # not make bootstrap depend on a valid config file: an empty set
        # simply falls back to the strict same-origin path.
        configured = load_effective_config(create_missing=False)
        values = values or configured.get("webserver_allowed_origins", "")
    except Exception:
        pass
    if isinstance(values, (list, tuple, set)):
        candidates = values
    else:
        candidates = re.split(r"[,\n]", str(values or ""))
    return {_normalise_origin(item) for item in candidates if _normalise_origin(item)}


def _trusted_proxy_request(request: Request) -> bool:
    """Trust forwarded host/scheme only from a local proxy or explicit opt-in."""
    flag = os.environ.get("AINIEE_TRUST_PROXY_HEADERS", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    client_host = (request.client.host if request.client else "") or ""
    return _is_loopback_bind_host(client_host)


def _request_public_origin(request: Request) -> str:
    """Build the browser-visible origin, honoring trusted proxy headers."""
    scheme = request.url.scheme
    host = request.headers.get("host", "")
    if _trusted_proxy_request(request):
        forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        if forwarded_scheme in {"http", "https"}:
            scheme = forwarded_scheme
        if forwarded_host and " " not in forwarded_host and "\t" not in forwarded_host:
            host = forwarded_host
    if not host or any(char in host for char in "\r\n"):
        return ""
    return _normalise_origin(f"{scheme}://{host}")


def _request_public_scheme(request: Request) -> str:
    origin = _request_public_origin(request)
    return origin.split(":", 1)[0] if ":" in origin else request.url.scheme


def _request_bind_host(request: Request) -> str:
    """Return the address the ASGI server received the connection on."""
    server = request.scope.get("server")
    if isinstance(server, (tuple, list)) and server:
        return str(server[0] or "")
    return request.url.hostname or ""


def _ensure_api_access(request: Request) -> None:
    """Require an authenticated browser session or MCP bridge for protected APIs."""
    if _has_valid_web_session(request) or _has_valid_mcp_auth(request):
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "API access requires a valid Web UI session or MCP bridge token. "
            "Direct unauthenticated HTTP bypass is not allowed."
        ),
    )


@app.middleware("http")
async def web_session_middleware(request: Request, call_next):
    """Guard APIs by default and leave only explicitly public routes unauthenticated."""
    path = request.url.path
    if _is_api_path(path) and not _is_public_api_request(request):
        if _is_internal_api_path(path):
            if not _has_valid_internal_auth(request):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Internal API access requires a valid worker token."},
                )
        else:
            try:
                _ensure_api_access(request)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers={AUTH_REQUIRED_HEADER: WEB_SESSION_AUTH_REQUIRED},
                )
            if SYSTEM_MODE == "monitor" and (
                request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
                or path == "/api/queue/edit_file"
            ):
                return JSONResponse(status_code=403, content={"detail": "Monitor mode is read-only."})

    runtime_header = "X-AiNiee-Runtime-Id"
    mcp_access = _is_api_path(path) and _has_valid_mcp_auth(request)
    expected_runtime = request.headers.get(runtime_header)
    if mcp_access and expected_runtime is not None and expected_runtime != RUNTIME_ID:
        return JSONResponse(status_code=409, content={"detail": "API owner changed; reconnect before continuing."})

    response = await call_next(request)
    if mcp_access and path == "/api/system/runtime" and request.method == "GET":
        response.headers[runtime_header] = RUNTIME_ID

    if not _is_api_path(path):
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            # WebView may reuse a cached SPA document without contacting the restarted backend.
            response.headers["Cache-Control"] = "no-cache"

    return response


@app.post("/api/session/bootstrap", status_code=204, responses=ERROR_RESPONSES)
async def bootstrap_web_session(request: Request, response: Response):
    """Establish the short-lived browser channel before accessing sensitive APIs."""
    origin = _normalise_origin(request.headers.get("origin", ""))
    expected_origin = _request_public_origin(request)
    allowed_origins = _configured_web_origins()
    origin_is_allowed = bool(origin) and (origin == expected_origin or origin in allowed_origins)
    if (
        (not REMOTE_ACCESS_ENABLED and not _is_loopback_bind_host(_request_bind_host(request)))
        or not origin_is_allowed
    ):
        raise HTTPException(status_code=403, detail="Web UI session bootstrap requires a same-origin request.")
    response.set_cookie(
        key=WEB_SESSION_COOKIE_NAME,
        value=WEB_SESSION_TOKEN,
        httponly=True,
        samesite="strict",
        secure=_request_public_scheme(request) == "https",
        path="/",
    )

def get_config_mode():
    """Checks if the config is in 'profile' mode or 'legacy' single-file mode."""
    return "profile", load_root_config()

def get_active_profile_path() -> str:
    """Gets the full path to the active profile JSON file."""
    _, config = get_config_mode()
    profile_name = config.get("active_profile", "default")
    profile_path, _ = resolve_profile_path(PROFILES_PATH, profile_name)
    return profile_path

def _load_web_i18n_data(lang: str) -> Dict[str, str]:
    normalized = lang or "zh_CN"
    if normalized not in ("zh_CN", "zh_CNTW", "en", "ja", "ko", "ru", "es"):
        normalized = "zh_CN" if str(normalized).lower().startswith("zh") else "en"
    if normalized in _web_i18n_cache:
        return _web_i18n_cache[normalized]

    path = os.path.join(PROJECT_ROOT, "I18N", f"{normalized}.json")
    data: Dict[str, str] = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
        except Exception:
            data = {}
    if not data and normalized != "en":
        return _load_web_i18n_data("en")

    _web_i18n_cache[normalized] = data
    return data

def _get_web_i18n_lang(config: Optional[Dict[str, Any]] = None) -> str:
    if config and config.get("interface_language"):
        return config.get("interface_language")

    mode, root_config = get_config_mode()
    if root_config.get("interface_language"):
        return root_config.get("interface_language")

    profile_path = get_active_profile_path()
    if os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                profile_config = json.load(f)
            if profile_config.get("interface_language"):
                return profile_config.get("interface_language")
        except Exception:
            pass
    return "zh_CN"

def _web_tr(key: str, default: Optional[str] = None, *args, lang: Optional[str] = None,
            config: Optional[Dict[str, Any]] = None) -> str:
    resolved_lang = lang or _get_web_i18n_lang(config)
    data = _load_web_i18n_data(resolved_lang)
    value = data.get(key)
    if (not value or value == key) and resolved_lang != "en":
        value = _load_web_i18n_data("en").get(key)
    if not value or value == key:
        value = default if default is not None else key
    if args:
        try:
            return value.format(*args)
        except Exception:
            return value
    return value

def get_active_rules_profile_path() -> str:
    """Gets the full path to the active rules profile JSON file."""
    _, root_config = get_config_mode()
    rules_profile = root_config.get("active_rules_profile", "default")
    os.makedirs(RULES_PROFILES_PATH, exist_ok=True)
    rules_path, _ = resolve_profile_path(RULES_PROFILES_PATH, rules_profile, allow_none=True)
    return rules_path


def _ensure_no_mcp_secret_placeholder(data: Any, context: str):
    """Reject writes that still contain unresolved MCP redacted placeholders."""
    if contains_redacted_secret(data):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{context} still contains MCP redacted secret placeholders. "
                "Ask the user to provide a new secret explicitly before saving."
            ),
        )

def save_rule_generic(key: str, value: Any):
    """Helper to save a specific rule key to the active RULES profile."""
    global _config_cache
    try:
        if key not in RULE_PROFILE_KEYS:
            raise ValueError(f"{key} is not a rules profile key")
        save_rule_value(key, value)
        _config_cache.clear()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rule {key}: {e}")

def save_config_generic(key: str, value: Any):
    """Helper to save a specific key to the active SETTINGS profile."""
    global _config_cache
    try:
        if key in RULE_PROFILE_KEYS:
            save_rule_value(key, value)
        else:
            save_setting_value(key, value)
        _config_cache.clear()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save setting {key}: {e}")

def _new_replacement_rule_id() -> str:
    return f"rr_{secrets.token_urlsafe(12)}"

def _normalize_replacement_rule_items(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        next_item.pop("_serverIndex", None)
        item_id = str(next_item.get("_id") or "").strip()
        if not item_id or item_id in seen_ids:
            item_id = _new_replacement_rule_id()
            while item_id in seen_ids:
                item_id = _new_replacement_rule_id()
        next_item["_id"] = item_id
        seen_ids.add(item_id)
        normalized.append(next_item)
    return normalized

@config_transaction()
def delete_rule_item_generic(key: str, index: int):
    config = _load_active_config_payload()
    items = config.get(key, [])
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail=f"{key} is not a list rule")
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Rule item not found")
    next_items = list(items)
    deleted = next_items.pop(index)
    save_rule_generic(key, next_items)
    return {"message": "Rule item deleted.", "deleted": deleted, "deleted_index": index, "items": next_items}

@config_transaction()
def delete_rule_item_by_id_generic(key: str, item_id: str):
    config = _load_active_config_payload()
    items = config.get(key, [])
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail=f"{key} is not a list rule")

    for index, item in enumerate(items):
        if isinstance(item, dict) and str(item.get("_id") or "") == item_id:
            next_items = list(items)
            deleted = next_items.pop(index)
            save_rule_generic(key, next_items)
            return {
                "message": "Rule item deleted.",
                "deleted": deleted,
                "deleted_index": index,
                "items": next_items,
            }

    raise HTTPException(status_code=404, detail="Rule item not found")

# --- API Endpoints ---

@app.get("/api/system/mode", response_model=ModeResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_system_mode():
    return {"mode": SYSTEM_MODE}


@app.get("/api/system/runtime", response_model=RuntimeIdentity, responses=ERROR_RESPONSES)
async def get_runtime_identity():
    return {"runtime_id": RUNTIME_ID, "workspace_id": WORKSPACE_ID, "api_version": "1"}

@app.get("/api/version", response_model=VersionResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_version():
    global _version_cache
    if "version" in _version_cache:
        return _version_cache["version"]

    if not os.path.exists(VERSION_FILE):
        # Fallback to a default if file is missing
        return {"version": "V0.0.0 (Version file not found)"}
        
    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
            _version_cache["version"] = version_data
            return version_data
    except:
        return {"version": "V0.0.0 (Read Error)"}

def _caller_context(request: Request):
    from ModuleFolders.Service.TaskRuntime.configuration import CallerContext
    if _has_valid_mcp_auth(request):
        return CallerContext(
            "mcp",
            confirm_advanced_change=request.headers.get("X-AiNiee-Confirm-Advanced") == "true",
            confirm_agent_batch_change=request.headers.get("X-AiNiee-Confirm-Agent-Batch") == "true",
        )
    if _has_valid_web_session(request):
        return CallerContext("web")
    raise HTTPException(status_code=403, detail="Authenticated API caller required.")


@app.post("/api/config", response_model=ConfigSaveResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_config(config: AppConfig, request: Request):
    from ModuleFolders.Service.TaskRuntime.configuration import update_configuration
    try:
        revision = update_configuration(config.model_dump(exclude_unset=True), _caller_context(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _config_cache.clear()
    return {"message": "Config saved successfully.", "revision": revision}


@config_transaction()
def _load_active_config_payload() -> Dict[str, Any]:
    """
    Load the active settings profile and rules profile into one merged payload.

    This helper is intentionally request-agnostic so internal Web handlers can
    reuse the merged config without needing to fake an HTTP Request object.
    """
    global _config_cache

    _, root_config = get_config_mode()
    cache_key = config_revision(root_config)
    if cache_key in _config_cache:
        return _config_cache[cache_key]
    loaded_config = load_effective_config(root_config=root_config, create_missing=False)

    # 防护：确保 response_check_switch 是正确的 dict 类型
    default_check_switch = {
        "newline_character_count_check": False, "return_to_original_text_check": False,
        "residual_original_text_check": False, "reply_format_check": False
    }
    if "response_check_switch" not in loaded_config or not isinstance(loaded_config.get("response_check_switch"), dict):
        loaded_config["response_check_switch"] = default_check_switch

    _config_cache.clear()
    _config_cache[cache_key] = loaded_config
    return loaded_config


@app.get("/api/task/runtime-parameters", response_model=RuntimeParametersResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_runtime_parameters():
    from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import runtime_parameter_schema
    return {"parameters": runtime_parameter_schema()}


@app.get("/api/config", response_model=ConfigResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_config(request: Request):
    from ModuleFolders.Service.TaskRuntime.configuration import read_configuration
    return read_configuration(_caller_context(request))

@app.get("/api/glossary", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_glossary():
    config = _load_active_config_payload()
    return config.get("prompt_dictionary_data", [])

@app.post("/api/glossary", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_glossary(items: List[Dict[str, Any]]):
    save_rule_generic("prompt_dictionary_data", items)
    return {"message": "Glossary saved successfully."}

@app.post("/api/glossary/add", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def add_glossary_item(item: GlossaryItem):
    with config_transaction():
        current = list(_load_active_config_payload().get("prompt_dictionary_data", []))
        for index, existing in enumerate(current):
            if existing.get("src", "") == item.src:
                current[index] = item.model_dump()
                break
        else:
            current.append(item.model_dump())
        save_rule_generic("prompt_dictionary_data", current)
    return {"message": "Term added to glossary."}

@app.post("/api/glossary/batch-add", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def batch_add_glossary_items(request: Dict[str, List[GlossaryItem]]):
    items = request.get("terms", [])
    with config_transaction():
        current = _load_active_config_payload().get("prompt_dictionary_data", [])
        current_map = {entry.get("src", ""): entry for entry in current}
        current_map.update((item.src, item.model_dump()) for item in items)
        save_rule_generic("prompt_dictionary_data", list(current_map.values()))
    return {"message": f"Successfully added {len(items)} terms."}

@app.post("/api/term/retry", response_model=TermTranslationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def retry_term_translation(request: TermRetryRequest):
    try:
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType

        # 1. Load configuration
        config = _load_active_config_payload()
        task_config = TaskConfig()
        task_config.load_config_from_dict(config)
        
        # 2. Handle temporary overrides if provided
        if request.temp_config:
            platform_name = request.temp_config.get("platform")
            if platform_name:
                # Ensure the platform exists in config
                if platform_name not in task_config.platforms:
                    # Create a default structure if it's a new platform tag
                    task_config.platforms[platform_name] = {
                        "tag": platform_name,
                        "name": platform_name,
                        "group": "custom",
                        "api_format": "OpenAI"
                    }
                
                # Update specific fields
                plat_ref = task_config.platforms[platform_name]
                if request.temp_config.get("api_key"): plat_ref["api_key"] = request.temp_config["api_key"]
                if request.temp_config.get("api_url"): plat_ref["api_url"] = request.temp_config["api_url"]
                if request.temp_config.get("model"): plat_ref["model"] = request.temp_config["model"]
                
                # Set as active platform for this request
                task_config.api_settings["translate"] = platform_name

        # 3. Prepare task config (this handles model normalization, URL completion, API key rotation)
        task_config.prepare_for_translation(TaskType.TRANSLATION)
        platform_config = task_config.get_platform_configuration("translationReq")
        target_language = task_config.target_language
        
        # 4. Construct Prompt (Match ainiee_cli.py logic)
        term_type = request.type or "专有名词"
        analysis_info = request.analysis_info or "null"
        avoid_hint = ""
        if request.avoid:
            avoid_list = ", ".join(request.avoid[:5])
            avoid_hint = f"\nPlease provide a different translation from: {avoid_list}"

        system_prompt = f"""You are a terminology translator. Translate the term into "{target_language}".
Term type: {term_type}
Known context: {analysis_info}
{avoid_hint}

Translation is the exact replacement value that may be inserted into translated text. It must contain only the final translated surface form.
Never output "translation (note)", "translation / note", "translation: note", "translation - note", or any other "translation + explanation" form in Translation.
Never put identity, role labels, character relationships, context notes, disambiguation, jokes, or reader-facing hints in Translation; put them in Note.
Qualifiers such as left/right/front/back or numbers may appear in Translation only when explicitly present in the source term. If no pure replacement-safe translation is certain, leave Translation empty.

Output format (use | as separator):
Translation|Note"""

        messages = [{"role": "user", "content": request.src}]

        # 5. Execute Request
        requester = LLMRequester()
        skip, _, response, _, _ = requester.sent_request(messages, system_prompt, platform_config)
        
        if skip or not response:
            raise HTTPException(status_code=500, detail="LLM request failed or was skipped")
            
        # 6. Parse Response (Match ainiee_cli.py logic)
        response_text = response.strip()
        if '|' in response_text:
            parts = response_text.split('|', 1)
            dst = parts[0].strip()
            info = parts[1].strip() if len(parts) > 1 else ""
        else:
            dst = response_text
            info = ""
            
        # Post-process dst
        if dst.startswith(("Translation:", "译文:", "译文：")):
            dst = dst.split(":", 1)[-1].split("：", 1)[-1].strip()
        dst = dst.strip('"').strip("'")
            
        return {"dst": dst, "info": info}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/exclusion", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_exclusion():
    config = _load_active_config_payload()
    return config.get("exclusion_list_data", [])

@app.post("/api/exclusion", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_exclusion(items: List[Dict[str, Any]]):
    save_rule_generic("exclusion_list_data", items)
    return {"message": "Exclusion list saved successfully."}

@app.get("/api/pre_translation", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_pre_translation():
    config = _load_active_config_payload()
    items = _normalize_replacement_rule_items(config.get("pre_translation_data", []))
    return items

@app.post("/api/pre_translation", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_pre_translation(items: List[Dict[str, Any]]):
    normalized = _normalize_replacement_rule_items(items)
    save_rule_generic("pre_translation_data", normalized)
    return {"message": "Pre-translation rules saved.", "items": normalized}

@app.delete("/api/pre_translation/by-id/{item_id}", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_pre_translation_item_by_id(item_id: str):
    return delete_rule_item_by_id_generic("pre_translation_data", item_id)

@app.delete("/api/pre_translation/{index}", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_pre_translation_item(index: int):
    return delete_rule_item_generic("pre_translation_data", index)

@app.get("/api/post_translation", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_post_translation():
    config = _load_active_config_payload()
    items = _normalize_replacement_rule_items(config.get("post_translation_data", []))
    return items

@app.post("/api/post_translation", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_post_translation(items: List[Dict[str, Any]]):
    normalized = _normalize_replacement_rule_items(items)
    save_rule_generic("post_translation_data", normalized)
    return {"message": "Post-translation rules saved.", "items": normalized}

@app.delete("/api/post_translation/by-id/{item_id}", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_post_translation_item_by_id(item_id: str):
    return delete_rule_item_by_id_generic("post_translation_data", item_id)

@app.delete("/api/post_translation/{index}", response_model=RuleMutationResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_post_translation_item(index: int):
    return delete_rule_item_generic("post_translation_data", index)

# --- New Features Endpoints ---

@app.get("/api/characterization", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_characterization():
    config = _load_active_config_payload()
    return config.get("characterization_data", [])

@app.post("/api/characterization", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_characterization(items: List[Dict[str, Any]]):
    save_rule_generic("characterization_data", items)
    return {"message": "Characterization saved."}

@app.get("/api/world_building", response_model=StringContent, responses=ERROR_RESPONSES)
async def get_world_building():
    config = _load_active_config_payload()
    return {"content": config.get("world_building_content", "")}

@app.post("/api/world_building", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_world_building(data: StringContent):
    save_rule_generic("world_building_content", data.content)
    return {"message": "World building saved."}

@app.get("/api/writing_style", response_model=StringContent, responses=ERROR_RESPONSES)
async def get_writing_style():
    config = _load_active_config_payload()
    return {"content": config.get("writing_style_content", "")}

@app.post("/api/writing_style", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_writing_style(data: StringContent):
    save_rule_generic("writing_style_content", data.content)
    return {"message": "Writing style saved."}

@app.get("/api/translation_example", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_translation_example():
    config = _load_active_config_payload()
    return config.get("translation_example_data", [])

@app.post("/api/translation_example", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_translation_example(items: List[Dict[str, Any]]):
    save_rule_generic("translation_example_data", items)
    return {"message": "Translation examples saved."}

# --- AI Glossary Analysis Endpoints ---
DEFAULT_GLOSSARY_TOKEN_WARNING_THRESHOLD = 256_000
DEFAULT_INCREMENTAL_SPLIT_TARGET_TOKENS = 200_000
MAX_INCREMENTAL_SPLIT_TARGET_TOKENS = 256_000


class _BackgroundRun:
    def __init__(self, state):
        self.state = state
        self.cancelled = threading.Event()

    def check_stop_owner(self, run_id):
        if run_id is not None and run_id != self.state.get("run_id"):
            raise HTTPException(status_code=409, detail="Background run has changed")

    def invoke(self, function, *args):
        from ModuleFolders.Base.Base import Base

        with Base.independent_request_scope(self.cancelled):
            if not self.cancelled.is_set():
                return function(*args)


_analysis_lock = threading.RLock()
_analysis_run = _BackgroundRun({
    "status": "idle",
    "progress": 0,
    "total": 0,
    "message": "",
    "results": [],
    "logs": [],
    "estimated_tokens": 0,
    "analysis_mode": "full",
    "structured_analysis": {},
})

@app.get("/api/glossary/analysis/status", response_model=AnalysisStateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_analysis_status():
    with _analysis_lock:
        return {**_analysis_run.state, "logs": list(_analysis_run.state["logs"])}

@app.post("/api/glossary/analysis/preflight", response_model=AnalysisPreflightResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def preflight_glossary_analysis(request: GlossaryAnalysisPreflightRequest):
    try:
        config = _load_active_config_payload()
        return _build_glossary_analysis_preflight(
            request.input_path,
            request.analysis_percent,
            request.analysis_lines,
            config,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/glossary/analysis/start", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def start_glossary_analysis(request: GlossaryAnalysisRequest):
    from copy import deepcopy

    global _analysis_run

    config = deepcopy(_load_active_config_payload())
    lang = _get_web_i18n_lang(config)

    run = _BackgroundRun({
        "run_id": uuid.uuid4().hex,
        "status": "running",
        "progress": 0,
        "total": 0,
        "message": _web_tr("glossary_log_initializing", "初始化中...", lang=lang),
        "results": [],
        "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] {_web_tr('glossary_log_start_analysis', '开始分析', lang=lang)}: {request.input_path}"],
        "estimated_tokens": 0,
        "analysis_mode": request.analysis_mode,
        "structured_analysis": {},
        "translate_during_analysis": request.translate_during_analysis,
        "lang": lang,
    })

    # Start analysis in background thread
    thread = threading.Thread(
        target=_run_glossary_analysis,
        args=(run, config, request),
        daemon=True,
    )
    with _analysis_lock:
        if _analysis_run.state["status"] == "running":
            raise HTTPException(status_code=400, detail="Analysis already running")
        previous = _analysis_run
        _analysis_run = run
        try:
            thread.start()
        except Exception:
            _analysis_run = previous
            raise
    return {"message": "Analysis started", "run_id": run.state["run_id"]}

def _estimate_glossary_tokens(text: str) -> int:
    try:
        from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem
        return CacheItem.get_token_count(text)
    except Exception:
        if not text:
            return 0
        ascii_count = sum(1 for c in text if ord(c) < 128)
        non_ascii_count = len(text) - ascii_count
        return max(1, int(ascii_count / 4 + non_ascii_count / 1.5))

def _get_glossary_token_warning_threshold(config: Dict[str, Any]) -> int:
    try:
        threshold = int(config.get("glossary_analysis_token_warning_threshold") or 0)
    except (TypeError, ValueError):
        threshold = 0
    return threshold if threshold > 0 else DEFAULT_GLOSSARY_TOKEN_WARNING_THRESHOLD

def _get_incremental_split_target_tokens(config: Dict[str, Any], requested: Optional[int] = None) -> int:
    value = requested if requested is not None else config.get("glossary_analysis_incremental_split_target_tokens")
    try:
        target = int(value or 0)
    except (TypeError, ValueError):
        target = 0
    if target <= 0:
        target = DEFAULT_INCREMENTAL_SPLIT_TARGET_TOKENS
    return min(target, MAX_INCREMENTAL_SPLIT_TARGET_TOKENS)

def _normalize_glossary_analysis_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    return normalized if normalized in {"full", "split", "incremental_split"} else "full"

def _build_glossary_analysis_preflight(input_path: str, analysis_percent: int, analysis_lines: Optional[int], config: Dict[str, Any]) -> Dict[str, Any]:
    from ModuleFolders.Domain.FileReader.FileReader import FileReader

    file_reader = FileReader()
    project_type = config.get("translation_project", "auto")
    cache_data = file_reader.read_files(project_type, input_path, "")
    if not cache_data:
        raise HTTPException(status_code=400, detail="Unable to read file content")

    all_items = list(cache_data.items_iter())
    total_lines = len(all_items)
    if total_lines == 0:
        raise HTTPException(status_code=400, detail="No analyzable text found")

    if analysis_lines:
        lines_to_analyze = min(analysis_lines, total_lines)
    else:
        lines_to_analyze = int(total_lines * analysis_percent / 100)
    lines_to_analyze = max(1, lines_to_analyze)

    selected_text = "\n".join([item.source_text for item in all_items[:lines_to_analyze]])
    estimated_tokens = _estimate_glossary_tokens(selected_text)
    warning_threshold = _get_glossary_token_warning_threshold(config)
    recommended_split_target_tokens = _get_incremental_split_target_tokens(config)
    return {
        "total_lines": total_lines,
        "lines_to_analyze": lines_to_analyze,
        "estimated_tokens": estimated_tokens,
        "warning_threshold": warning_threshold,
        "recommended_split_target_tokens": recommended_split_target_tokens,
        "max_split_target_tokens": MAX_INCREMENTAL_SPLIT_TARGET_TOKENS,
        "exceeds_warning": estimated_tokens > warning_threshold,
    }

def _split_glossary_items_by_tokens(items: list, target_tokens: int) -> list:
    batches = []
    current = []
    current_tokens = 0
    target_tokens = max(1, min(int(target_tokens or DEFAULT_INCREMENTAL_SPLIT_TARGET_TOKENS), MAX_INCREMENTAL_SPLIT_TARGET_TOKENS))
    for item in items or []:
        text = getattr(item, "source_text", "")
        item_tokens = max(1, _estimate_glossary_tokens(text))
        if item_tokens > target_tokens:
            if current:
                batches.append(current)
                current = []
                current_tokens = 0
            sentence_chunks = _split_glossary_text_by_sentence_boundaries(text, target_tokens)
            if len(sentence_chunks) > 1:
                for chunk in sentence_chunks:
                    batches.append([_clone_glossary_item_with_text(item, chunk)])
                continue
        if current and current_tokens + item_tokens > target_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(item)
        current_tokens += item_tokens
    if current:
        batches.append(current)
    return batches or [items]

def _split_glossary_text_by_sentence_boundaries(text: str, target_tokens: int) -> list:
    text = _normalize_glossary_text(text)
    if not text:
        return []

    sentences = re.findall(r".+?(?:[。！？!?\.]+[”’\"']?|\n+|$)", text, flags=re.S)
    sentences = [sentence for sentence in (s.strip() for s in sentences) if sentence]
    if len(sentences) <= 1:
        return [text]

    chunks = []
    current = []
    current_tokens = 0
    target_tokens = max(1, min(int(target_tokens or DEFAULT_INCREMENTAL_SPLIT_TARGET_TOKENS), MAX_INCREMENTAL_SPLIT_TARGET_TOKENS))

    for sentence in sentences:
        sentence_tokens = max(1, _estimate_glossary_tokens(sentence))
        if current and current_tokens + sentence_tokens > target_tokens:
            chunks.append("\n".join(current))
            current = []
            current_tokens = 0
        current.append(sentence)
        current_tokens += sentence_tokens

    if current:
        chunks.append("\n".join(current))
    return chunks or [text]

def _clone_glossary_item_with_text(item, text: str):
    class TextOnlyItem:
        def __init__(self, source_text):
            self.source_text = source_text

    try:
        clone = item.__class__.__new__(item.__class__)
        if hasattr(item, "__dict__"):
            clone.__dict__.update(item.__dict__)
        setattr(clone, "source_text", text)
        return clone
    except Exception:
        return TextOnlyItem(text)

def _resolve_glossary_prompt_file(prompt_file: str = None, lang: str = None) -> str:
    if prompt_file and os.path.exists(prompt_file):
        return prompt_file

    lang = lang or _get_web_i18n_lang()
    default_prompt = "glossary_extract_zh.txt" if str(lang).startswith("zh") else "glossary_extract_en.txt"
    prompt_file = os.path.join(PROJECT_ROOT, "Resource", "Prompt", "System", default_prompt)
    if not os.path.exists(prompt_file):
        fallback_prompt = "glossary_extract_en.txt" if default_prompt != "glossary_extract_en.txt" else "glossary_extract_zh.txt"
        prompt_file = os.path.join(PROJECT_ROOT, "Resource", "Prompt", "System", fallback_prompt)
    return prompt_file

def _count_glossary_term_occurrences(text: str, term: str) -> int:
    if not text or not term:
        return 0
    return text.count(term)

def _run_glossary_analysis(run: _BackgroundRun, config: dict, options: GlossaryAnalysisRequest):
    state = run.state
    lang = state["lang"]

    def publish(**fields):
        with _analysis_lock:
            if run is _analysis_run and not run.cancelled.is_set():
                state.update(fields)

    def log(key, default, *args):
        message = _web_tr(key, default, *args, lang=lang)
        with _analysis_lock:
            if run is _analysis_run and not run.cancelled.is_set():
                state["logs"].append(f"[{datetime.now():%H:%M:%S}] {message}")

    try:
        if run.cancelled.is_set():
            return
        from ModuleFolders.Domain.FileReader.FileReader import FileReader
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        import concurrent.futures

        def request(messages, prompt, platform):
            result = run.invoke(LLMRequester().sent_request, messages, prompt, platform)
            return result if result is not None else (True, "STOPPED", "", 0, 0)

        # Read file
        publish(message=_web_tr("msg_reading_file", "正在读取文件...", lang=lang))
        log("msg_reading_file", "正在读取文件...")
        file_reader = FileReader()
        project_type = config.get("translation_project", "auto")
        cache_data = file_reader.read_files(project_type, options.input_path, "")

        if run.cancelled.is_set():
            return
        if not cache_data:
            publish(status="error", message=_web_tr("msg_no_content", "无法读取文件内容", lang=lang))
            log("glossary_log_error_message", "错误: {}", _web_tr("msg_no_content", "无法读取文件内容", lang=lang))
            return

        all_items = list(cache_data.items_iter())
        total_lines = len(all_items)

        if total_lines == 0:
            publish(status="error", message=_web_tr("msg_no_text_found", "未找到可分析的文本", lang=lang))
            log("glossary_log_error_message", "错误: {}", _web_tr("msg_no_text_found", "未找到可分析的文本", lang=lang))
            return

        # Calculate lines to analyze
        if options.analysis_lines:
            lines_to_analyze = min(options.analysis_lines, total_lines)
        else:
            lines_to_analyze = int(total_lines * options.analysis_percent / 100)
        lines_to_analyze = max(1, lines_to_analyze)

        log("glossary_log_line_count", "总行数: {}, 将分析: {} 行", total_lines, lines_to_analyze)

        items_to_analyze = all_items[:lines_to_analyze]
        selected_text = "\n".join([item.source_text for item in items_to_analyze])
        estimated_tokens = _estimate_glossary_tokens(selected_text)
        normalized_mode = _normalize_glossary_analysis_mode(options.analysis_mode)
        publish(estimated_tokens=estimated_tokens, analysis_mode=normalized_mode)
        log("glossary_log_estimated_tokens_note", "预估Token: {}（仅供参考，实际仍按行数/比例截取）", estimated_tokens)

        # Load prompt
        prompt_file = _resolve_glossary_prompt_file(options.prompt_file, lang)
        log("glossary_log_prompt_file_value", "提示词文件: {}", prompt_file)

        with open(prompt_file, 'r', encoding='utf-8') as f:
            system_prompt = f.read()

        # Configure request
        task_config = TaskConfig()
        task_config.load_config_from_dict(config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        # Use temp config or current config
        if options.use_temp_config and options.temp_platform:
            platform_config = {
                "target_platform": options.temp_platform,
                "api_key": options.temp_api_key or "",
                "api_url": options.temp_api_url or "",
                "model": options.temp_model or ""
            }
            publish(message=f"{_web_tr('msg_using_temp_config', '使用临时API配置', lang=lang)}: {options.temp_platform}")
            log(
                "glossary_log_using_temp_config",
                "使用临时API配置: {}, 模型: {}",
                options.temp_platform,
                options.temp_model or _web_tr("glossary_log_default_prompt", "默认", lang=lang)
            )
        else:
            platform_config = task_config.get_platform_configuration("translationReq")
            log("glossary_log_using_current_config", "使用当前配置: {}", platform_config.get('target_platform', 'unknown'))

        target_language = getattr(task_config, "target_language", config.get("target_language", "Chinese"))
        if options.translate_during_analysis:
            system_prompt = _append_glossary_analysis_translation_instruction(system_prompt, target_language)
            publish(translate_during_analysis=True)
            log(
                "msg_glossary_analysis_translate_enabled",
                "已启用分析阶段直译：LLM 将同时输出译名和注释。"
            )

        all_terms = []
        structured_analysis = _empty_glossary_analysis_payload()

        if normalized_mode == "full":
            publish(total=1)
            publish(message=_web_tr("glossary_log_full_prepare", "全本/按比例提取：准备一次性分析 {} 行文本", lines_to_analyze, lang=lang))
            log("glossary_log_full_mode_detail", "分析模式: 全本/按比例提取（推荐），将所选文本一次性发送给LLM")
            messages = [{"role": "user", "content": selected_text}]
            try:
                skip, _, response, prompt_tokens, completion_tokens = request(messages, system_prompt, platform_config)
                if run.cancelled.is_set():
                    return

                if not skip and response:
                    parsed = _parse_glossary_response(response)
                    terms = parsed.get("terms", [])
                    all_terms.extend(terms)
                    _merge_glossary_analysis_payload(structured_analysis, parsed)
                    publish(progress=1)
                    publish(message=_web_tr("glossary_log_analysis_done_tokens", "分析完成，Token: {}", f"{prompt_tokens}+{completion_tokens}", lang=lang))
                    log(
                        "glossary_log_single_done",
                        "单次分析完成，发现 {} 个候选术语，Token: {}",
                        len(terms),
                        f"{prompt_tokens}+{completion_tokens}"
                    )
                else:
                    publish(progress=1)
                    log("glossary_log_single_empty", "单次分析失败或返回为空")
            except Exception as e:
                publish(progress=1)
                log("glossary_log_single_error", "单次分析错误: {}", str(e))
        elif normalized_mode == "split":
            batch_size = int(config.get("glossary_analysis_split_lines") or config.get("lines_limit", 20) or 20)
            batch_size = max(1, batch_size)
            batches = [items_to_analyze[i:i+batch_size] for i in range(0, len(items_to_analyze), batch_size)]

            publish(total=len(batches))
            publish(message=_web_tr("glossary_log_split_prepare", "拆分提取：准备分析 {} 行文本，共 {} 批次", lines_to_analyze, len(batches), lang=lang))
            log("glossary_log_split_mode_detail", "分析模式: 拆分提取（不推荐），共 {} 批次，每批 {} 行", len(batches), batch_size)

            terms_lock = threading.Lock()
            # 只有在使用临时配置时才使用 temp_threads，否则使用当前配置的线程数
            if options.use_temp_config and options.temp_threads and options.temp_threads > 0:
                thread_count = options.temp_threads
            else:
                thread_count = task_config.actual_thread_counts
            log("glossary_log_thread_count", "并发线程数: {}", thread_count)

            def analyze_batch(batch_info):
                if run.cancelled.is_set():
                    return
                batch_idx, batch = batch_info
                text_content = "\n".join([item.source_text for item in batch])
                messages = [{"role": "user", "content": text_content}]

                try:
                    skip, _, response, _, _ = request(messages, system_prompt, platform_config)
                    if run.cancelled.is_set():
                        return

                    if not skip and response:
                        parsed = _parse_glossary_response(response)
                        terms = parsed.get("terms", [])
                        with terms_lock:
                            all_terms.extend(terms)
                            _merge_glossary_analysis_payload(structured_analysis, parsed)
                            publish(progress=state["progress"] + 1)
                            publish(message=_web_tr(
                                "glossary_log_batch_progress",
                                "已完成 {}/{} 批次",
                                state["progress"],
                                state["total"],
                                lang=lang
                            ))
                    else:
                        with terms_lock:
                            publish(progress=state["progress"] + 1)
                except Exception:
                    with terms_lock:
                        publish(progress=state["progress"] + 1)

            # Run analysis
            publish(message=_web_tr("msg_starting_concurrent", "开始并发分析...", lang=lang))
            log("msg_starting_concurrent", "开始并发分析...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                batch_infos = list(enumerate(batches))
                list(executor.map(analyze_batch, batch_infos))
        else:
            target_tokens = _get_incremental_split_target_tokens(config, options.incremental_split_target_tokens)
            batches = _split_glossary_items_by_tokens(items_to_analyze, target_tokens)
            publish(total=len(batches))
            publish(message=_web_tr("glossary_log_incremental_split_prepare", "超长增量分批：准备分析 {} 行文本，共 {} 批次", lines_to_analyze, len(batches), lang=lang))
            log(
                "glossary_log_incremental_split_mode_detail",
                "分析模式: 超长增量分批，共 {} 批次，目标每批约 {} Token（单批最大 256000）；后一批参考前面累计结果，只输出新增或变化。",
                len(batches),
                target_tokens,
            )

            for batch_idx, batch in enumerate(batches):
                if run.cancelled.is_set():
                    return
                text_content = "\n".join([item.source_text for item in batch])
                batch_context = _build_incremental_split_context(structured_analysis, all_terms)
                batch_system_prompt = _append_incremental_split_instruction(system_prompt, batch_context, batch_idx, len(batches))
                messages = [{"role": "user", "content": text_content}]
                terms = []
                try:
                    skip, _, response, _, _ = request(messages, batch_system_prompt, platform_config)
                    if run.cancelled.is_set():
                        return
                    if not skip and response:
                        parsed = _parse_glossary_response(response)
                        terms = parsed.get("terms", [])
                        all_terms.extend(terms)
                        _merge_glossary_analysis_payload(
                            structured_analysis,
                            parsed,
                            fill_existing=True,
                            replace_existing=True,
                        )
                    publish(progress=state["progress"] + 1)
                    publish(message=_web_tr(
                        "glossary_log_batch_progress",
                        "已完成 {}/{} 批次",
                        state["progress"],
                        state["total"],
                        lang=lang,
                    ))
                    log(
                        "glossary_log_incremental_batch_done",
                        "增量分批 {}/{} 完成，新增/变化候选术语 {} 个",
                        batch_idx + 1,
                        len(batches),
                        len(terms),
                    )
                except Exception as e:
                    publish(progress=state["progress"] + 1)
                    log("glossary_log_single_error", "单次分析错误: {}", str(e))

        if run.cancelled.is_set():
            return
        if normalized_mode == "incremental_split":
            all_terms = _dedupe_glossary_terms(all_terms)
        structured_analysis = _finalize_glossary_analysis_payload(structured_analysis, all_terms)

        # Calculate frequency
        term_freq = _calculate_term_frequency(all_terms, selected_text)

        # Convert to list format
        results = []
        for term, data in term_freq.items():
            results.append({
                "src": term,
                "type": data["type"],
                "dst": data.get("dst", ""),
                "info": data.get("info", "null"),
                "count": data["count"]
            })

        log("glossary_log_analysis_completed_terms", "分析完成，发现 {} 个专有名词", len(results))
        publish(status="completed", results=results, structured_analysis=structured_analysis,
                message=_web_tr("glossary_log_analysis_completed_terms", "分析完成，发现 {} 个专有名词", len(results), lang=lang))

    except Exception as e:
        publish(status="error", message=_web_tr("glossary_log_analysis_error_detail", "分析出错: {}", str(e)))
        log("glossary_log_error_message", "错误: {}", str(e))

def _empty_glossary_analysis_payload() -> dict:
    return {
        "terms": [],
        "exclusion_list_data": [],
        "characterization_data": [],
        "world_building_content": "",
        "writing_style_content": "",
        "translation_example_data": [],
    }

def _merge_glossary_analysis_payload(target: dict, source: dict, fill_existing: bool = False, replace_existing: bool = False) -> dict:
    if not source:
        return target
    target.setdefault("terms", []).extend(source.get("terms", []))
    _extend_unique_dicts(target.setdefault("exclusion_list_data", []), source.get("exclusion_list_data", []), ("markers", "regex"))
    _merge_character_lists(
        target.setdefault("characterization_data", []),
        source.get("characterization_data", []),
        fill_existing=fill_existing,
        replace_existing=replace_existing,
    )
    _extend_unique_dicts(target.setdefault("translation_example_data", []), source.get("translation_example_data", []), ("src", "dst"))
    target["world_building_content"] = _append_text_block(target.get("world_building_content", ""), source.get("world_building_content", ""))
    target["writing_style_content"] = _append_text_block(target.get("writing_style_content", ""), source.get("writing_style_content", ""))
    return target

def _finalize_glossary_analysis_payload(payload: dict, terms: list) -> dict:
    _merge_character_lists(payload.setdefault("characterization_data", []), _derive_characters_from_terms(terms))
    if not _normalize_glossary_text(payload.get("world_building_content")):
        payload["world_building_content"] = _derive_world_building_from_terms(terms)
    return payload

def _append_incremental_split_instruction(system_prompt: str, accumulated_context: dict, batch_index: int, total_batches: int) -> str:
    context_json = json.dumps(accumulated_context or {}, ensure_ascii=False, indent=2)
    instruction = f"""

## 超长文本增量分批模式
当前文本因预估 Token 过高被顺序拆分分析。你正在分析第 {batch_index + 1}/{total_batches} 批。

请遵守以下规则：
- 先阅读“已累计规则快照”，再阅读当前批文本。
- 当前批只输出新增项，或相对已累计快照有明确变化、补充、纠错价值的条目。
- 如果某个术语、角色、世界观或文风信息已经存在且当前批没有提供新证据，不要重复输出。
- 如果当前批揭示了同一术语/角色/设定的新含义、身份反转、称呼变化、语气变化、用途变化或更准确描述，可以输出更新后的条目，程序会按当前最新结果合并。
- 这是同一文件内部的分批，不是系列卷号增量；不要输出 Vol_2、Vol_3、第2卷、第3卷、volume、updated_volume、history 等卷号/时间线标识，除非原文本身明确出现这些内容且它们是需要提取的术语。
- 如果当前批没有新增或变化，对应字段返回空数组或空字符串。

### 已累计规则快照
{context_json}
"""
    return f"{system_prompt.rstrip()}\n{instruction.strip()}\n"

def _build_incremental_split_context(structured_analysis: dict, terms: list) -> dict:
    return {
        "prompt_dictionary_data": _trim_glossary_context_value(_dedupe_glossary_terms(terms), max_items=200, max_chars=12000),
        "exclusion_list_data": _trim_glossary_context_value((structured_analysis or {}).get("exclusion_list_data", []), max_items=120, max_chars=8000),
        "characterization_data": _trim_glossary_context_value((structured_analysis or {}).get("characterization_data", []), max_items=120, max_chars=12000),
        "world_building_content": _trim_glossary_context_value((structured_analysis or {}).get("world_building_content", ""), max_items=0, max_chars=10000),
        "writing_style_content": _trim_glossary_context_value((structured_analysis or {}).get("writing_style_content", ""), max_items=0, max_chars=6000),
        "translation_example_data": _trim_glossary_context_value((structured_analysis or {}).get("translation_example_data", []), max_items=80, max_chars=8000),
    }

def _trim_glossary_context_value(value, max_items: int = 300, max_chars: int = 12000):
    if isinstance(value, list):
        trimmed = value[:max_items]
        if len(value) > max_items:
            trimmed = [*trimmed, {"_truncated": f"{len(value) - max_items} more items omitted"}]
        return trimmed
    text = _normalize_glossary_text(value)
    if len(text) > max_chars:
        return text[:max_chars] + f"\n...({len(text) - max_chars} chars omitted)"
    return text

def _dedupe_glossary_terms(terms: list) -> list:
    result = []
    by_src = {}
    for term in terms or []:
        if not isinstance(term, dict):
            continue
        src = _normalize_glossary_text(term.get("src"))
        if not src:
            continue
        if src not in by_src:
            item = dict(term)
            by_src[src] = item
            result.append(item)
            continue
        existing = by_src[src]
        for key, value in term.items():
            if key == "src":
                continue
            if _rule_field_has_content(value):
                existing[key] = value
    return result

def _parse_glossary_response(response: str) -> dict:
    import re
    payload = _empty_glossary_analysis_payload()
    parsed = _load_json_from_glossary_response(response, re)

    if isinstance(parsed, list):
        payload["terms"] = _normalize_term_items(parsed)
        return payload

    if not isinstance(parsed, dict):
        return payload

    payload["terms"] = _normalize_term_items(_first_present(parsed, ("glossary", "terms", "terminology", "term_list", "prompt_dictionary_data"), []))
    payload["exclusion_list_data"] = _normalize_exclusion_items(_first_present(parsed, ("exclusion_list", "non_translation_list", "no_translate", "ntl", "exclusion_list_data"), []))
    payload["characterization_data"] = _normalize_character_items(_first_present(parsed, ("characterization", "characters", "character_profiles", "characterization_data"), []))
    payload["world_building_content"] = _format_analysis_sections(_first_present(parsed, ("world_building", "worldview", "world_settings", "setting", "world_building_content"), ""))
    payload["writing_style_content"] = _format_analysis_sections(_first_present(parsed, ("writing_style", "style", "translation_style", "writing_style_content"), ""))
    payload["translation_example_data"] = _normalize_translation_examples(_first_present(parsed, ("translation_examples", "translation_example", "translation_example_data"), []))
    return payload

def _load_json_from_glossary_response(response: str, re_module):
    if not response:
        return None
    text = response.strip()
    candidates = []
    fence_match = re_module.search(r"```(?:json)?\s*([\s\S]*?)```", text, re_module.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    candidates.append(text)
    object_match = re_module.search(r"\{[\s\S]*\}", text)
    if object_match:
        candidates.append(object_match.group())
    array_match = re_module.search(r"\[[\s\S]*\]", text)
    if array_match:
        candidates.append(array_match.group())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None

def _first_present(data: dict, keys: tuple, default):
    for key in keys:
        if key in data:
            value = data.get(key)
            return default if value is None else value
    return default

def _normalize_term_items(items) -> list:
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if not isinstance(items, list):
        return []
    terms = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = _normalize_glossary_text(item.get("src") or item.get("term") or item.get("name") or item.get("original"))
        if not src:
            continue
        category = _normalize_glossary_text(item.get("category"))
        term_type = _normalize_glossary_text(item.get("type") or category, "专有名词")
        raw_info = _normalize_glossary_info(item)
        terms.append({
            "src": src,
            "dst": _normalize_glossary_text(item.get("dst") or item.get("target") or item.get("translation") or item.get("translated_name")),
            "type": term_type,
            "category": category,
            "info": _clean_glossary_analysis_info(raw_info, term_type, category),
        })
    return terms

def _normalize_exclusion_items(items) -> list:
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if isinstance(items, str):
        items = [{"markers": line.strip()} for line in items.splitlines() if line.strip()]
    if not isinstance(items, list):
        return []
    result = []
    seen = set()
    for item in items:
        if isinstance(item, str):
            item = {"markers": item}
        if not isinstance(item, dict):
            continue
        markers = _normalize_glossary_text(item.get("markers") or item.get("marker") or item.get("src") or item.get("text"))
        regex = _normalize_glossary_text(item.get("regex"))
        info = _normalize_glossary_text(item.get("info") or item.get("description") or item.get("desc"))
        key = (markers, regex)
        if (not markers and not regex) or key in seen:
            continue
        seen.add(key)
        result.append({"markers": markers, "info": info, "regex": regex})
    return result

def _normalize_character_items(items) -> list:
    import re
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        original_name = _normalize_glossary_text(item.get("original_name") or item.get("src") or item.get("name") or item.get("original"))
        if not original_name:
            continue
        additional_parts = []
        for key in ("identity", "role", "relationship", "relationships", "info", "description", "desc", "note", "annotation"):
            value = _normalize_glossary_text(item.get(key))
            if value:
                additional_parts.append(value)
        result.append({
            "original_name": original_name,
            "translated_name": _normalize_glossary_text(item.get("translated_name") or item.get("dst") or item.get("translation")),
            "aliases": _normalize_aliases(
                item.get("aliases")
                or item.get("alias")
                or item.get("nicknames")
                or item.get("other_names")
                or item.get("别名")
                or item.get("昵称")
                or item.get("称呼")
                or item.get("其他称呼"),
                re,
            ),
            "gender": _normalize_glossary_text(item.get("gender")),
            "age": _normalize_glossary_text(item.get("age")),
            "personality": _normalize_glossary_text(item.get("personality")),
            "speech_style": _normalize_glossary_text(item.get("speech_style") or item.get("speaking_style") or item.get("tone")),
            "pronouns": _normalize_glossary_text(item.get("pronouns") or item.get("first_second_person") or item.get("person_pronouns")),
            "speech_quirks": _normalize_glossary_text(item.get("speech_quirks") or item.get("verbal_quirks") or item.get("catchphrase") or item.get("ending_particles")),
            "additional_info": _normalize_glossary_text(item.get("additional_info"), "；".join(dict.fromkeys(additional_parts))),
        })
    return result

def _normalize_aliases(value, re_module) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        text = _normalize_glossary_text(value)
        if not text:
            return []
        raw_items = re_module.split(r"[,;|/，、；／\n]+", text.replace("[Separator]", "\n"))

    aliases = []
    seen = set()
    for item in raw_items:
        alias = _normalize_glossary_text(item)
        if not alias:
            continue
        marker = alias.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        aliases.append(alias)
    return aliases

def _normalize_translation_examples(items) -> list:
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if not isinstance(items, list):
        return []
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        src = _normalize_glossary_text(item.get("src") or item.get("source") or item.get("original"))
        dst = _normalize_glossary_text(item.get("dst") or item.get("target") or item.get("translation"))
        key = (src, dst)
        if not src or key in seen:
            continue
        seen.add(key)
        result.append({"src": src, "dst": dst})
    return result

def _format_analysis_sections(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n\n".join(block for block in (_format_analysis_sections(item) for item in value) if block)
    if isinstance(value, dict):
        title = _normalize_glossary_text(value.get("title") or value.get("name") or value.get("category"))
        content = value.get("content")
        if content is None:
            content = value.get("description") or value.get("info") or value.get("summary")
        content_text = _format_analysis_sections(content) if isinstance(content, (list, dict)) else _normalize_glossary_text(content)
        if not content_text:
            parts = []
            for key, item_value in value.items():
                if key in ("title", "name", "category"):
                    continue
                item_text = _format_analysis_sections(item_value)
                if item_text:
                    parts.append(f"{key}: {item_text}")
            content_text = "\n".join(parts)
        return f"## {title}\n{content_text}" if title and content_text else content_text
    return str(value).strip()

def _append_text_block(existing: str, addition: str) -> str:
    existing = _normalize_glossary_text(existing)
    addition = _normalize_glossary_text(addition)
    if not addition:
        return existing
    if addition in existing:
        return existing
    return f"{existing.rstrip()}\n\n{addition}" if existing else addition

def _extend_unique_dicts(target: list, incoming: list, key_fields: tuple) -> list:
    seen = {
        tuple(_normalize_glossary_text(item.get(field)) for field in key_fields)
        for item in target
        if isinstance(item, dict)
    }
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        key = tuple(_normalize_glossary_text(item.get(field)) for field in key_fields)
        if not any(key) or key in seen:
            continue
        target.append(item)
        seen.add(key)
    return target

def _merge_character_lists(target: list, incoming: list, fill_existing: bool = False, replace_existing: bool = False) -> list:
    by_name = {
        _normalize_glossary_text(item.get("original_name")): item
        for item in target
        if isinstance(item, dict) and _normalize_glossary_text(item.get("original_name"))
    }
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_glossary_text(item.get("original_name"))
        if not name:
            continue
        existing = by_name.get(name)
        if existing:
            if fill_existing or replace_existing:
                for key, value in item.items():
                    if not _rule_field_has_content(value):
                        continue
                    if replace_existing or not _rule_field_has_content(existing.get(key)):
                        existing[key] = value
            continue
        target.append(item)
        by_name[name] = item
    return target

def _derive_characters_from_terms(terms: list) -> list:
    result = []
    for term in terms:
        term_type = _normalize_glossary_text(term.get("type")).lower()
        category = _normalize_glossary_text(term.get("category")).lower()
        if not any(key in term_type or key in category for key in ("人名", "人物", "角色", "character", "person")):
            continue
        src = _normalize_glossary_text(term.get("src"))
        if not src:
            continue
        info = _normalize_glossary_text(term.get("info"))
        result.append({
            "original_name": src,
            "translated_name": "",
            "aliases": [],
            "gender": "",
            "age": "",
            "personality": "",
            "speech_style": "",
            "pronouns": "",
            "speech_quirks": "",
            "additional_info": "" if info.lower() in ("null", "none") else info,
        })
    return result

def _derive_world_building_from_terms(terms: list) -> str:
    lines = []
    for term in terms:
        term_type = _normalize_glossary_text(term.get("type"))
        category = _normalize_glossary_text(term.get("category"))
        type_text = f"{category}/{term_type}" if category and category != term_type else term_type
        type_lower = type_text.lower()
        if any(key in type_lower for key in ("人名", "人物", "角色", "character", "person")):
            continue
        if not any(key in type_lower for key in (
            "世界", "设定", "地名", "地点", "组织", "势力", "技能", "能力", "系统",
            "术语", "place", "location", "organization", "faction", "skill", "ability",
            "system", "world", "setting", "term",
        )):
            continue
        src = _normalize_glossary_text(term.get("src"))
        if not src:
            continue
        info = _normalize_glossary_text(term.get("info"))
        suffix = "" if info.lower() in ("", "null", "none") else f"：{info}"
        lines.append(f"- {src}（{type_text or '设定'}）{suffix}")
    title = _web_tr("glossary_world_building_clues_title", "世界观与设定线索")
    return f"## {title}\n" + "\n".join(dict.fromkeys(lines)) if lines else ""

def _normalize_glossary_text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default

def _build_analysis_glossary_item(row: dict) -> dict:
    src = _normalize_glossary_text((row or {}).get("src"))
    info = _clean_glossary_analysis_info(
        (row or {}).get("info"),
        (row or {}).get("type"),
        (row or {}).get("category"),
    )
    return {
        "src": src,
        "dst": _normalize_glossary_text((row or {}).get("dst")),
        "info": _normalize_glossary_text(info, "null"),
    }

def _rule_field_has_content(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_normalize_glossary_text(item) for item in value)
    return bool(_normalize_glossary_text(value))

def _normalize_glossary_info(item: dict) -> str:
    for key in ("info", "description", "desc"):
        if key in item:
            value = item.get(key)
            if value is None:
                return "null"
            text = str(value).strip()
            return text if text else "null"
    return "null"

def _append_glossary_analysis_translation_instruction(system_prompt: str, target_language: str) -> str:
    instruction = f"""

Additional output requirement:
- Translate extracted terms into "{target_language}" during analysis. Put the translation in the glossary item field "dst".
- "src" is the source-text matching key; "dst" is the replacement value that may be inserted verbatim into translated text.
- "dst" must contain only the final translated surface form. Never output "translation (note)", "translation / note", "translation: note", "translation - note", or any other "translation + explanation" form.
- Never put identity, role labels, character relationships, context notes, disambiguation, jokes, memes, or reader-facing hints in "dst"; put them in "info" or "characterization".
- Qualifiers such as left/right/front/back or numbers may appear in "dst" only when explicitly present in "src". If no pure replacement-safe translation is certain, leave "dst" empty.
- Keep "src" as the original text. Do not put category/type labels into "info".
- "type" is only the category, such as character, place, organization, skill, world setting, item, or term.
- "info" must be a short note/annotation in "{target_language}" that explains the term's role, context, or usage.
- For character profiles, fill "translated_name" and write gender, personality, speech_style, and additional_info in "{target_language}" when known.
- For world_building_content, writing_style_content, and translation_example_data.dst, output "{target_language}" content.
- For exclusion_list_data.markers, keep the original text that must not be translated; write its "info" in "{target_language}".
"""
    return f"{system_prompt.rstrip()}\n{instruction.strip()}\n"

def _clean_glossary_analysis_info(info, term_type: str = "", category: str = "") -> str:
    info = _normalize_glossary_text(info, "null")
    if info.lower() in ("", "null", "none"):
        return "null"

    labels = {
        _normalize_glossary_text(term_type).lower(),
        _normalize_glossary_text(category).lower(),
        "专有名词", "人名", "人物", "角色", "地名", "地点", "组织", "势力",
        "技能", "能力", "物品", "道具", "世界观", "设定", "术语",
        "character", "person", "place", "location", "organization", "faction",
        "skill", "ability", "item", "world", "setting", "term",
    }
    labels = {label for label in labels if label}
    for splitter in ("|", "｜", ":", "："):
        if splitter not in info:
            continue
        left, right = info.split(splitter, 1)
        if left.strip().lower() in labels:
            cleaned = right.strip()
            return cleaned if cleaned else "null"
    return info

def _format_glossary_info(term_type, info) -> str:
    term_type = _normalize_glossary_text(term_type, "专有名词")
    info = _normalize_glossary_text(info, "null")
    if info.lower() in ("null", "none"):
        return f"{term_type} | null"
    return f"{term_type} | {info}"

def _calculate_term_frequency(terms: list, source_text: str = "") -> dict:
    freq = {}
    for term in terms:
        src = term.get('src', '').strip()
        if not src:
            continue
        count = max(1, _count_glossary_term_occurrences(source_text, src) if source_text else 1)
        if src in freq:
            freq[src]['count'] = max(freq[src]['count'], count)
            if not freq[src].get('dst') and term.get('dst'):
                freq[src]['dst'] = term.get('dst')
            if freq[src].get('info') in ("", "null") and term.get('info') not in ("", None, "null"):
                freq[src]['info'] = term.get('info')
        else:
            freq[src] = {
                'count': count,
                'type': term.get('type', '专有名词'),
                'category': term.get('category', ''),
                'dst': term.get('dst', ''),
                'info': term.get('info', 'null')
            }
    return dict(sorted(freq.items(), key=lambda x: x[1]['count'], reverse=True))

def _has_non_glossary_analysis(payload: dict) -> bool:
    if not payload:
        return False
    return any([
        bool(payload.get("exclusion_list_data")),
        bool(payload.get("characterization_data")),
        bool(_normalize_glossary_text(payload.get("world_building_content"))),
        bool(_normalize_glossary_text(payload.get("writing_style_content"))),
        bool(payload.get("translation_example_data")),
    ])

def _build_analysis_rules_config(glossary_data: list, structured_analysis: dict) -> dict:
    return normalize_rules_payload({
        "prompt_dictionary_data": glossary_data,
        "exclusion_list_data": structured_analysis.get("exclusion_list_data", []),
        "characterization_data": structured_analysis.get("characterization_data", []),
        "world_building_content": _normalize_glossary_text(structured_analysis.get("world_building_content")),
        "writing_style_content": _normalize_glossary_text(structured_analysis.get("writing_style_content")),
        "translation_example_data": structured_analysis.get("translation_example_data", []),
    })

def _sanitize_rules_profile_name(profile_name: str) -> str:
    try:
        return sanitize_profile_name(profile_name, allow_none=True)
    except ValueError:
        return ""

@app.post("/api/glossary/analysis/stop", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def stop_glossary_analysis(run_id: Optional[str] = None):
    with _analysis_lock:
        run = _analysis_run
        run.check_stop_owner(run_id)
        if run.state["status"] == "running":
            run.cancelled.set()
            run.state.update(status="idle", message=_web_tr("msg_task_stopped", "已停止", lang=run.state["lang"]))
    return {"message": "Analysis stopped"}


@app.post("/api/glossary/analysis/save", response_model=AnalysisSaveResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_analysis_results(request: SaveAnalysisRequest):
    """保存分析结果为新的rules_profile并自动切换"""
    global _config_cache
    _analysis_state = await get_analysis_status()

    if _analysis_state["status"] != "completed":
        raise HTTPException(status_code=400, detail="No completed analysis to save")
    lang = _analysis_state.get("lang") or _get_web_i18n_lang()

    # Filter by frequency
    filtered = [r for r in _analysis_state["results"] if r["count"] >= request.min_frequency]
    structured_analysis = _analysis_state.get("structured_analysis") or _empty_glossary_analysis_payload()

    if not filtered and not _has_non_glossary_analysis(structured_analysis):
        raise HTTPException(status_code=400, detail="No terms or structured rules after filtering")

    # Convert to glossary format
    glossary_data = [
        _build_analysis_glossary_item(r)
        for r in filtered
    ]

    # 新建一个 rules profile 文件
    new_profile_name = _sanitize_rules_profile_name(request.filename)
    if not new_profile_name:
        raise HTTPException(status_code=400, detail=_web_tr("msg_rules_profile_name_required", "规则配置名不能为空", lang=lang))
    if new_profile_name == "None":
        raise HTTPException(status_code=400, detail=_web_tr("msg_rules_profile_reserved", "规则配置名不能使用保留名称 None", lang=lang))
    new_profile_path, new_profile_name = resolve_profile_path(
        RULES_PROFILES_PATH,
        new_profile_name,
        allow_none=True,
    )

    # 确保目录存在
    os.makedirs(RULES_PROFILES_PATH, exist_ok=True)
    if os.path.exists(new_profile_path):
        raise HTTPException(status_code=400, detail=_web_tr("msg_rules_profile_exists", "规则配置已存在: {}", new_profile_name, lang=lang))

    # 创建新的 rules profile，包含本次分析出的全部分类内容
    new_rules_config = _build_analysis_rules_config(glossary_data, structured_analysis)

    atomic_write_json(new_profile_path, new_rules_config)

    # 自动切换到新创建的 rules profile
    root_config = load_root_config()
    root_config["active_rules_profile"] = new_profile_name
    save_root_config(root_config)

    # 清除缓存以便前端获取最新数据
    _config_cache.clear()

    return {
        "message": _web_tr(
            "msg_analysis_saved_to_new_rules_profile",
            "已保存到新规则配置 '{}' 并自动切换：术语 {}，禁翻 {}，角色 {}",
            new_profile_name,
            len(glossary_data),
            len(new_rules_config.get('exclusion_list_data', [])),
            len(new_rules_config.get('characterization_data', [])),
            lang=lang,
        ),
        "file": new_profile_path,
        "profile": new_profile_name,
        "count": len(glossary_data),
        "rules": new_rules_config
    }

# --- Plugin Management Endpoints ---

@app.get("/api/plugins", response_model=list[PluginResponse], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_plugins():
    """
    Returns a list of all loaded plugins and their enable status.
    """
    try:
        # We need an instance of PluginManager to get the loaded plugins
        from ModuleFolders.Base.PluginManager import PluginManager
        pm = PluginManager()
        pm.load_plugins_from_directory(os.path.join(PROJECT_ROOT, "PluginScripts"))
        
        plugins = pm.get_plugins()
        
        # Load enable status from root config
        root_config = load_root_config()
        plugin_enables = root_config.get("plugin_enables", {})
        
        result = []
        for name, plugin in plugins.items():
            result.append({
                "name": name,
                "description": plugin.description,
                "enabled": plugin_enables.get(name, plugin.default_enable),
                "default_enable": plugin.default_enable
            })
            
        return sorted(result, key=lambda x: x["name"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get plugins: {e}")

@app.post("/api/plugins/toggle", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def toggle_plugin(request: PluginEnableRequest):
    """
    Toggles a plugin's enable status and saves it to root config.
    """
    try:
        root_config = load_root_config()
        plugin_enables = root_config.get("plugin_enables", {})
        plugin_enables[request.name] = request.enabled
        root_config["plugin_enables"] = plugin_enables
        save_root_config(root_config)
            
        return {"message": f"Plugin '{request.name}' {'enabled' if request.enabled else 'disabled'}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle plugin: {e}")

@app.get("/api/profiles", response_model=List[str], responses=ERROR_RESPONSES)
async def get_profiles():
    """
    Returns a list of available profile filenames, utilizing cache.
    """
    global _profiles_cache

    if _profiles_cache is not None:
        return _profiles_cache

    _profiles_cache = list_profile_names(PROFILES_PATH)
    return _profiles_cache

@app.get("/api/rules_profiles", response_model=List[str], responses=ERROR_RESPONSES)
async def get_rules_profiles():
    return list_profile_names(RULES_PROFILES_PATH, include_none=True)

# --- Prompt Management Endpoints ---

def _prompt_path(category: str, filename: str | None = None) -> Path:
    root = (Path(PROJECT_ROOT) / "Resource" / "Prompt").resolve()
    parts = [category] + ([filename] if filename is not None else [])
    if any(not part or part in {".", ".."} or any(c in part for c in ("/", "\\", "\0", ":")) for part in parts):
        raise HTTPException(status_code=400, detail="Invalid prompt path.")
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Prompt path must remain inside the prompt directory.")
    return path

@app.get("/api/prompts", response_model=list[str], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def list_prompt_categories():
    root = (Path(PROJECT_ROOT) / "Resource" / "Prompt").resolve()
    if not root.exists(): return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and path.resolve().is_relative_to(root))

@app.get("/api/prompts/{category}", response_model=list[str], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def list_prompts(category: str):
    # category: "Translate", "Polishing", "Local", "Sakura", "System"
    prompt_dir = _prompt_path(category)
    if not prompt_dir.exists():
        return []
    # Support both .txt and .json (for error_analysis.json)
    root = (Path(PROJECT_ROOT) / "Resource" / "Prompt").resolve()
    files = [path.name for path in prompt_dir.iterdir() if path.is_file() and path.suffix in {".txt", ".json"} and path.resolve().is_relative_to(root)]
    return sorted(files)

@app.get("/api/prompts/{category}/{filename}", response_model=StringContent, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_prompt_content(category: str, filename: str):
    # Try literal match first, then fallback to .txt
    file_path = _prompt_path(category, filename)
    if not file_path.exists():
        if not filename.endswith(".txt"):
            file_path = _prompt_path(category, filename + ".txt")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Prompt file not found")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read prompt: {e}")

@app.post("/api/prompts/{category}/{filename}", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_prompt_content(category: str, filename: str, data: Dict[str, str] = Body(...)):
    file_path = _prompt_path(category, filename)
    # Check if we should append .txt (only if it doesn't exist and doesn't have an extension)
    if not os.path.exists(file_path) and "." not in filename:
        file_path = _prompt_path(category, filename + ".txt")
        
    content = data.get("content", "")
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"message": "Prompt saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save prompt: {e}")

@app.post("/api/rules_profiles/switch", response_model=ConfigResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def switch_rules_profile(request: RulesProfileSwitchRequest, http_request: Request):
    global _config_cache
    try:
        profile_name = sanitize_profile_name(request.profile, allow_none=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if profile_name != "None":
        profile_path, profile_name = resolve_profile_path(RULES_PROFILES_PATH, profile_name, allow_none=True)
        if not os.path.exists(profile_path):
            raise HTTPException(status_code=404, detail="Rules profile not found")

    try:
        root_config = load_root_config()
        root_config["active_rules_profile"] = profile_name
        save_root_config(root_config)

        _config_cache.clear()
        return await get_config(http_request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rules_profiles/delete", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_rules_profile(request: RulesProfileDeleteRequest):
    global _config_cache
    try:
        profile_name = sanitize_profile_name(request.profile, allow_none=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if profile_name == "None":
        raise HTTPException(status_code=400, detail="Cannot delete the None rules profile")

    root_config = load_root_config()
    if root_config.get("active_rules_profile", "default") == profile_name:
        raise HTTPException(status_code=400, detail="Cannot delete the active rules profile")

    profile_path, profile_name = resolve_profile_path(RULES_PROFILES_PATH, profile_name, allow_none=True)
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail="Rules profile not found")

    try:
        os.remove(profile_path)
        _config_cache.clear()
        return {"message": f"Rules profile '{profile_name}' deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rules profile: {e}")

@app.post("/api/profiles/switch", response_model=ConfigResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def switch_profile(request: ProfileSwitchRequest, http_request: Request):
    """
    Switches the active profile, returns the new active config, and invalidates caches.
    """
    global _config_cache, _profiles_cache # Need to clear these caches

    try:
        profile_path, profile_name = resolve_profile_path(PROFILES_PATH, request.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found.")

    try:
        # Update the root config to point to the new profile
        root_config = load_root_config()
        root_config["active_profile"] = profile_name
        save_root_config(root_config)

        # Invalidate all config caches and profiles cache
        _config_cache.clear()
        _profiles_cache = None

        return await get_config(http_request)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch profile: {e}")

@app.post("/api/profiles/create", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def create_profile(request: ProfileCreateRequest):
    global _profiles_cache

    try:
        new_path, new_name = resolve_profile_path(PROFILES_PATH, request.name)
        base_name = sanitize_profile_name(request.base) if request.base else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Use injected handler if available
    if profile_handlers["create"]:
        try:
            profile_handlers["create"](new_name, base_name)
            _profiles_cache = None
            return {"message": f"Profile '{new_name}' created successfully (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="Profile already exists")

    # Determine base profile to copy from
    if not base_name:
        # Use active profile as base
        _, config = get_config_mode()
        base_name = config.get("active_profile", "default")

    base_path, _ = resolve_profile_path(PROFILES_PATH, base_name)

    try:
        # Robust Creation Logic: Preset + Base -> New
        final_config = load_master_preset()
        if os.path.exists(base_path):
            final_config = deep_merge(final_config, load_json_file(base_path, {}))
        settings_only, _, _ = split_effective_config(final_config)
        settings_only[PROFILE_ORIGIN_KEY] = profile_origin_for_new_profile(
            load_effective_config(create_missing=False)
        )
        atomic_write_json(new_path, settings_only)

        _profiles_cache = None # Invalidate cache
        return {"message": f"Profile '{new_name}' created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {e}")

@app.post("/api/profiles/rename", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def rename_profile(request: ProfileRenameRequest):
    global _profiles_cache, _config_cache
    try:
        old_path, old_name = resolve_profile_path(PROFILES_PATH, request.old_name)
        new_path, new_name = resolve_profile_path(PROFILES_PATH, request.new_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Use injected handler
    if profile_handlers["rename"]:
        try:
            profile_handlers["rename"](old_name, new_name)
            _profiles_cache = None
            _config_cache.clear()
            return {"message": f"Renamed '{old_name}' to '{new_name}' (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source profile not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="Destination profile name already exists")
        
    try:
        os.rename(old_path, new_path)
        
        # Check if we renamed the active profile
        _, config = get_config_mode()
        current_active = config.get("active_profile")

        if current_active == old_name:
            # Update root config to point to new name
            config["active_profile"] = new_name
            save_root_config(config)

            # Clear config cache as the key changed
            _config_cache.clear()

        _profiles_cache = None
        return {"message": f"Renamed '{old_name}' to '{new_name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename profile: {e}")

@app.post("/api/profiles/delete", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_profile(request: ProfileDeleteRequest):
    global _profiles_cache
    try:
        target_path, profile_name = resolve_profile_path(PROFILES_PATH, request.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Use injected handler
    if profile_handlers["delete"]:
        try:
            profile_handlers["delete"](profile_name)
            _profiles_cache = None
            return {"message": f"Profile '{profile_name}' deleted (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check if active
    _, config = get_config_mode()
    if config.get("active_profile") == profile_name:
        raise HTTPException(status_code=400, detail="Cannot delete the currently active profile. Please switch to another profile first.")

    # Check if it's the last one (optional safety, though frontend should handle)
    profiles = [f for f in os.listdir(PROFILES_PATH) if f.endswith(".json")]
    if len(profiles) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only remaining profile.")

    try:
        os.remove(target_path)
        _profiles_cache = None
        return {"message": f"Profile '{profile_name}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {e}")

# --- Task API Endpoints ---


@app.post("/api/platforms/create", response_model=PlatformCreateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def create_platform(request: PlatformCreateRequest):
    global _config_cache
    new_name = request.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Platform name cannot be empty")

    try:
        with config_transaction():
            config = load_effective_config()
            platforms = config.setdefault("platforms", {})
            if new_name in platforms:
                raise HTTPException(status_code=409, detail="Platform already exists")
            template = platforms.get("custom", {
                "tag": "custom", "group": "custom", "name": "Custom API",
                "api_url": "", "api_key": "", "api_format": "OpenAI",
                "model": "gpt-4o", "key_in_settings": ["api_url", "api_key", "model"]
            }).copy()
            template.update(tag=new_name, name=new_name)
            template.update(request.base_config or {})
            platforms[new_name] = template
            save_effective_config(config)

        _config_cache.clear()
        return {"message": f"Platform '{new_name}' created", "config": template}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

def _flush_pending_task_cache(spec: TaskSpec) -> None:
    cache = get_cache_manager()
    if getattr(cache, "project", None) and getattr(cache, "save_to_file_require_flag", False):
        if not getattr(cache, "save_to_file_require_path", ""):
            raise ValueError("Pending cache has no project destination")
        cache.flush_pending_save()


def _task_operations():
    from ModuleFolders.Service.TaskRuntime.operations import TaskOperations
    return TaskOperations(
        task_manager, flush_pending_cache=_flush_pending_task_cache,
        queue_is_running=lambda: get_queue_manager().is_running,
    )


def _task_call(method: str, *args, **kwargs):
    from ModuleFolders.Service.TaskRuntime.operations import TaskOperationError
    try:
        return getattr(_task_operations(), method)(*args, **kwargs)
    except TaskOperationError as exc:
        statuses = {
            "INVALID_TASK": 422, "PROMPT_NOT_SELECTED": 422, "TASK_NOT_FOUND": 404,
            "FEATURE_UNAVAILABLE": 503, "TASK_START_FAILED": 500,
            "EXTERNAL_CHANNEL_REQUIRED": 403,
        }
        raise HTTPException(status_code=statuses.get(exc.code, 409), detail=str(exc)) from exc


@app.post("/api/task/run", response_model=TaskStartResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def run_task(payload: TaskPayload):
    if payload.to_task_spec().execution_mode == "external_agent":
        raise HTTPException(status_code=409, detail="Use the task-scoped external-agent-mode endpoint with explicit approval.")
    return _task_call("start", payload.to_task_spec())


@app.post("/api/task/preview", response_model=TaskPreviewResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def preview_task_request(payload: TaskPayload):
    return _task_call("preview", payload.to_task_spec())


@app.post("/api/task/external-agent/status", openapi_extra={"x-allowed-channels": ["mcp"]}, response_model=ExternalTaskStatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def update_external_agent_status(payload: ExternalAgentStatusPayload, request: Request):
    if not _has_valid_mcp_auth(request):
        raise HTTPException(status_code=403, detail="Authenticated MCP channel required.")
    return _task_call("external_status", payload.task_id, payload.status, payload.message)


@app.post("/api/task/external-agent-mode", response_model=TaskStartResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def request_external_agent_mode(payload: ExternalAgentTaskPayload, request: Request):
    """Start one MCP-scoped task in external-Agent mode.

    The mode is applied to this task snapshot only.  This endpoint is exposed
    for MCP clients and deliberately does not write ``translation_execution_mode``
    or any other profile setting.
    """
    if not _has_valid_mcp_auth(request):
        raise HTTPException(
            status_code=403,
            detail="External-Agent mode must be requested through the authenticated MCP bridge.",
        )

    if payload.user_confirmed_external_processing is not True:
        raise HTTPException(
            status_code=409,
            detail="EXTERNAL_PROCESSING_NOT_CONFIRMED: ask the user to approve this task, "
            "then pass user_confirmed_external_processing=true. TUI onboarding is not required.",
        )

    # Pydantic's model copy keeps the caller's payload intact while forcing the
    # backend choice on this request.  The normal task endpoint then performs
    # all prompt, feature, conflict, and lifecycle checks.
    forced_payload = payload.model_copy(update={"execution_mode": "external_agent"})
    result = _task_call(
        "start", forced_payload.to_task_spec(), caller=_caller_context(request),
        user_confirmed_external_processing=payload.user_confirmed_external_processing,
    )
    result["execution_mode"] = "external_agent"
    result["mode_scope"] = "task"
    result["config_changed"] = False
    return result

@app.post("/api/task/stop", response_model=TaskStartResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def stop_task(payload: Optional[TaskControlPayload] = None):
    return _task_call("stop", payload.task_id if payload else None)


@app.get("/api/task/status", response_model=TaskStatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_task_status(
    response: Response,
    task_id: Optional[str] = Query(None),
    log_cursor: int = Query(0, ge=0),
    chart_cursor: int = Query(0, ge=0),
    comparison_cursor: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "no-store"
    return _task_call("status", task_id, log_cursor, chart_cursor, comparison_cursor)


@app.post("/api/internal/update_comparison", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def internal_update_comparison(payload: InternalComparisonPayload):
    """Internal endpoint for subprocesses to push comparison data."""
    with task_manager._lock:
        if payload.task_id is not None and payload.task_id != task_manager.task_id:
            raise HTTPException(status_code=409, detail="Worker task no longer owns the comparison channel.")
        task_manager.push_comparison(payload.source, payload.translation)
    return {"status": "ok"}


def _validate_worker_task(task_id: str | None) -> None:
    if task_id is not None and task_id != task_manager.task_id:
        raise HTTPException(status_code=409, detail="Worker task no longer owns this channel.")


@app.post("/api/internal/update_stats", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def internal_update_stats(payload: Dict[str, Any] = Body(...)):
    allowed = set(task_manager._get_initial_stats()) - {"status"}
    with task_manager._lock:
        _validate_worker_task(payload.get("task_id"))
        task_manager.push_stats({key: value for key, value in payload.items() if key in allowed})
    return {"status": "ok"}


@app.post("/api/internal/push_log", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def internal_push_log(payload: InternalLogPayload):
    with task_manager._lock:
        _validate_worker_task(payload.task_id)
        task_manager.push_log(payload.message, payload.type)
    return {"status": "ok"}

# --- File Management Endpoints ---

_upload_locks = weakref.WeakKeyDictionary()


def _upload_lock():
    loop = asyncio.get_running_loop()
    lock = _upload_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _upload_locks[loop] = lock
    return lock


def _files_in_use():
    return task_manager._is_task_active_locked() or get_queue_manager().is_running

@app.post("/api/files/upload", response_model=UploadedFileResponse | UploadLimitResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def upload_file(file: UploadFile = File(...), policy: str = "default"):
    """Stage an upload without overwriting names or deleting before a successful save."""
    if policy not in {"default", "buffer", "overwrite"}:
        raise HTTPException(status_code=422, detail="Unknown upload policy.")
    filename = Path((file.filename or "").replace("\\", "/")).name
    if not filename or filename in {".", ".."} or any(c in filename for c in ("\0", ":")):
        raise HTTPException(status_code=400, detail="Invalid file name.")
    config = _load_active_config_payload()
    try:
        limit = max(1, int(config.get("temp_file_limit", 10)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid temporary file limit.")
    async with _upload_lock():
        root = Path(UPDATETEMP_PATH).resolve()
        root.mkdir(parents=True, exist_ok=True)
        files = sorted((p for p in root.iterdir() if p.is_file() and not p.is_symlink()), key=lambda p: p.stat().st_mtime)
        victim = None
        if len(files) >= limit:
            if policy == "buffer" and len(files) < limit + 1:
                pass
            elif policy == "overwrite":
                with task_manager._lock:
                    if _files_in_use():
                        raise HTTPException(status_code=409, detail="Temporary files cannot be replaced while a task is active.")
                victim = files[0]
            else:
                return {"status": "limit_reached", "limit": limit, "oldest": files[0].name,
                        "buffer_available": len(files) < limit + 1}
        destination = root / filename
        if destination.exists() or destination.is_symlink():
            destination = root / f"{Path(filename).stem}-{uuid.uuid4().hex[:12]}{Path(filename).suffix}"
        staging = tempfile.TemporaryDirectory(prefix=".upload-", dir=root)
        staged_path = Path(staging.name) / "content"
        try:
            with staged_path.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            from ModuleFolders.Service.Agent.ExternalAgentWriterLease import _interprocess_lock
            # Staging and publication share a filesystem. Serialize publishers
            # across loops/processes without requiring hard-link support.
            with _interprocess_lock(root / ".upload-state" / "publication"):
                if destination.exists() or destination.is_symlink():
                    destination = root / f"{Path(filename).stem}-{uuid.uuid4().hex}{Path(filename).suffix}"
                os.replace(staged_path, destination)
            result = {"info": f"file '{filename}' saved", "path": str(destination)}
            if victim is not None:
                with task_manager._lock:
                    if _files_in_use():
                        result["warning"] = "Replacement deferred because a task became active; both files were retained."
                    else:
                        try:
                            victim.unlink()
                            result["deleted"] = victim.name
                        except OSError:
                            result["warning"] = "New file saved; the previous file could not be removed."
            return result
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Failed to save uploaded file.") from exc
        finally:
            staging.cleanup()

@app.get("/api/files/temp", response_model=list[TemporaryFileResponse], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def list_temp_files():
    """
    Lists files in the 'updatetemp' directory.
    """
    if not os.path.exists(UPDATETEMP_PATH):
        return []
    
    files = []
    for f in os.listdir(UPDATETEMP_PATH):
        full_path = os.path.join(UPDATETEMP_PATH, f)
        if os.path.isfile(full_path) and not os.path.islink(full_path):
            files.append({
                "name": f,
                "path": full_path,
                "size": os.path.getsize(full_path)
            })
    return files

@app.delete("/api/files/temp", response_model=FileDeleteResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def delete_temp_files(request: DeleteFileRequest):
    async with _upload_lock():
        with task_manager._lock:
            if _files_in_use():
                raise HTTPException(status_code=409, detail="Temporary files cannot be deleted while a task is active.")
            root = Path(UPDATETEMP_PATH).resolve()
            deleted, failed = [], []
            for filename in request.files:
                if not filename or Path(filename).name != filename or "\\" in filename or filename in {".", ".."}:
                    failed.append({"file": filename, "error": "Invalid file name"})
                    continue
                path = root / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        failed.append({"file": filename, "error": "File not found"})
                        continue
                    path.unlink()
                    deleted.append(filename)
                except OSError:
                    failed.append({"file": filename, "error": "File could not be deleted"})
            return {"deleted": deleted, "failed": failed}

# --- Draft Management Endpoints ---

def save_draft_generic(filename: str, data: Any):
    try:
        os.makedirs(TEMP_EDIT_PATH, exist_ok=True)
        draft_path = os.path.join(TEMP_EDIT_PATH, filename)
        with open(draft_path, 'w', encoding='utf-8') as f:
            # If data is list of models, convert to list of dicts
            if isinstance(data, list) and len(data) > 0 and hasattr(data[0], 'dict'):
                json.dump([item.dict() for item in data], f, indent=4, ensure_ascii=False)
            # If data is simple dict/list/str
            elif hasattr(data, 'dict'):
                json.dump(data.dict(), f, indent=4, ensure_ascii=False)
            else:
                json.dump(data, f, indent=4, ensure_ascii=False)
        return {"message": "Draft saved."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save draft: {e}")

def get_draft_generic(filename: str):
    draft_path = os.path.join(TEMP_EDIT_PATH, filename)
    if not os.path.exists(draft_path):
        return None # Return None to indicate no draft
    try:
        with open(draft_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

@app.post("/api/draft/glossary", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_glossary_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("glossary_draft.json", items)

@app.get("/api/draft/glossary", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_glossary_draft():
    return get_draft_generic("glossary_draft.json") or []

@app.post("/api/draft/exclusion", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_exclusion_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("exclusion_draft.json", items)

@app.get("/api/draft/exclusion", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_exclusion_draft():
    return get_draft_generic("exclusion_draft.json") or []

@app.post("/api/draft/pre_translation", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_pre_translation_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("pre_translation_draft.json", items)

@app.get("/api/draft/pre_translation", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_pre_translation_draft():
    return get_draft_generic("pre_translation_draft.json") or []

@app.post("/api/draft/post_translation", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_post_translation_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("post_translation_draft.json", items)

@app.get("/api/draft/post_translation", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_post_translation_draft():
    return get_draft_generic("post_translation_draft.json") or []

@app.post("/api/draft/characterization", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_characterization_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("characterization_draft.json", items)

@app.get("/api/draft/characterization", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_characterization_draft():
    return get_draft_generic("characterization_draft.json") or []

@app.post("/api/draft/translation_example", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_translation_example_draft(items: List[Dict[str, Any]]):
    return save_draft_generic("translation_example_draft.json", items)

@app.get("/api/draft/translation_example", response_model=list[RuleRecord], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_translation_example_draft():
    return get_draft_generic("translation_example_draft.json") or []

@app.post("/api/draft/world_building", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_world_building_draft(data: StringContent):
    return save_draft_generic("world_building_draft.json", data.content)

@app.get("/api/draft/world_building", response_model=StringContent, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_world_building_draft():
    res = get_draft_generic("world_building_draft.json")
    if res is None: return {"content": ""}
    return {"content": res}

@app.post("/api/draft/writing_style", response_model=MessageResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_writing_style_draft(data: StringContent):
    return save_draft_generic("writing_style_draft.json", data.content)

@app.get("/api/draft/writing_style", response_model=StringContent, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_writing_style_draft():
    res = get_draft_generic("writing_style_draft.json")
    if res is None: return {"content": ""}
    return {"content": res}

# --- Cache Management API ---








# Global cache manager instance
_cache_manager_instance = None
_cache_output_path = None

def get_cache_manager():
    """Get CacheManager singleton instance"""
    global _cache_manager_instance
    try:
        if _cache_manager_instance is None:
            from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
            _cache_manager_instance = CacheManager()
        return _cache_manager_instance
    except ImportError:
        raise HTTPException(status_code=500, detail="CacheManager not available")

def resolve_cache_output_path(project_path: str) -> str:
    from ModuleFolders.Service.TaskRuntime.cache_editing import resolve_output_path
    try:
        return str(resolve_output_path(project_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_cache_snapshot(output_path):
    from ModuleFolders.Service.TaskRuntime.cache_editing import CacheEditConflict, read_snapshot
    try:
        return read_snapshot(output_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache file not found") from exc
    except CacheEditConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@contextmanager
def _edit_cache_project(output_path, *, expected_revision=None, replacement=None):
    from ModuleFolders.Service.TaskRuntime.cache_editing import CacheEditConflict, edit_project
    from ModuleFolders.Infrastructure.Cache.CachePersistence import CacheWriteConflict
    # Keep an API worker from starting while its output is being edited.
    with task_manager._lock, _proofread_lock:
        if _files_in_use():
            raise HTTPException(status_code=409, detail="Cache cannot be edited while a task is active")
        _require_proofread_report_idle(output_path)
        try:
            with edit_project(output_path, expected_revision=expected_revision, replacement=replacement) as transaction:
                yield transaction
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Cache file not found") from exc
        except (CacheEditConflict, CacheWriteConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.get("/api/cache/status", response_model=CacheStatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_cache_status(project_path: Optional[str] = None):
    output_path = resolve_cache_output_path(project_path) if project_path else _cache_output_path
    if not output_path:
        return {"loaded": False, "file_count": 0, "total_items": 0, "project_name": None}
    project, revision = _read_cache_snapshot(output_path)
    return {
        "loaded": bool(project.files), "file_count": len(project.files),
        "total_items": sum(len(file.items) for file in project.files.values()),
        "project_name": project.project_name, "project_path": output_path,
        "project_id": project.project_id, "revision": revision,
    }

@app.post("/api/cache/load", response_model=CacheLoadResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def load_cache(request: CacheLoadRequest):
    """Load cache data from project path"""
    global _cache_output_path
    try:
        cache_manager = get_cache_manager()

        output_path = resolve_cache_output_path(request.project_path)
        cache_file_to_check = os.path.join(output_path, "cache", "AinieeCacheData.json")

        if not os.path.exists(cache_file_to_check):
            # Try to provide more helpful error information
            cache_dir = os.path.dirname(cache_file_to_check)
            if not os.path.exists(cache_dir):
                raise HTTPException(
                    status_code=404,
                    detail=f"Cache directory not found: {cache_dir}. Please check if the project path is correct."
                )
            else:
                # List files in cache directory to help debug
                try:
                    files_in_cache = os.listdir(cache_dir)
                    raise HTTPException(
                        status_code=404,
                        detail=f"Cache file 'AinieeCacheData.json' not found in {cache_dir}. Found files: {files_in_cache}"
                    )
                except PermissionError:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Cache file not found: {cache_file_to_check}. Permission denied accessing cache directory."
                    )

        # Load the main cache directly. Web users choose backups in the UI; the load
        # endpoint must not auto-heal because that would overwrite the user's choice.
        try:
            project = cache_manager.read_from_file(cache_file_to_check)
        except Exception as cache_error:
            candidates = cache_manager._collect_valid_backup_caches(output_path)
            if candidates:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Cache file is corrupted. Select a backup to restore.",
                        "backups": [
                            {
                                "file": os.path.basename(candidate["path"]),
                                "modified_time": candidate["modified_time"],
                                "size": candidate["size"],
                                "size_label": candidate["size_label"],
                                "project_name": candidate["project_name"],
                                "item_count": candidate["item_count"],
                                "translated_count": candidate["translated_count"],
                                "total_count": candidate["total_count"],
                                "completion_rate": candidate["completion_rate"],
                                "completion_label": candidate["completion_label"],
                            }
                            for candidate in candidates
                        ],
                    },
                ) from cache_error
            raise
        if not project.files:
            raise HTTPException(status_code=400, detail="Cache contains no files")
        _cache_output_path = output_path
        file_count = len(project.files)
        total_items = sum(len(file.items) for file in project.files.values())

        return {
            "success": True,
            "message": f"Cache loaded successfully. Found {file_count} files with {total_items} items.",
            "file_count": file_count,
            "total_items": total_items
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load cache: {e}")

@app.get("/api/cache/backups", response_model=CacheBackupsResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def list_cache_backups(project_path: str):
    try:
        output_path = resolve_cache_output_path(project_path)
        cache_manager = get_cache_manager()
        candidates = cache_manager._collect_valid_backup_caches(output_path)
        return {
            "backups": [
                {
                    "file": os.path.basename(candidate["path"]),
                    "modified_time": candidate["modified_time"],
                    "size": candidate["size"],
                    "size_label": candidate["size_label"],
                    "project_name": candidate["project_name"],
                    "item_count": candidate["item_count"],
                    "translated_count": candidate["translated_count"],
                    "total_count": candidate["total_count"],
                    "completion_rate": candidate["completion_rate"],
                    "completion_label": candidate["completion_label"],
                }
                for candidate in candidates
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list cache backups: {e}")

@app.post("/api/cache/restore", response_model=CacheRestoreResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def restore_cache_backup(request: CacheRestoreRequest):
    try:
        output_path = resolve_cache_output_path(request.project_path)
        backup_file = os.path.basename(request.backup_file)
        backup_dir = os.path.join(output_path, "cache", "backups")
        backup_path = os.path.realpath(os.path.join(backup_dir, backup_file))
        backup_dir_real = os.path.realpath(backup_dir)
        if os.path.commonpath([backup_dir_real, backup_path]) != backup_dir_real:
            raise HTTPException(status_code=400, detail="Invalid backup file")
        if not os.path.isfile(backup_path):
            raise HTTPException(status_code=404, detail="Backup file not found")

        cache_manager = get_cache_manager()
        project = cache_manager.read_from_file(backup_path)
        with _edit_cache_project(output_path, replacement=project) as (cache_manager, _):
            cache_manager.save_to_file()
        global _cache_output_path
        _cache_output_path = output_path

        return {
            "success": True,
            "message": "Cache backup restored successfully",
            "file": backup_file,
            "file_count": len(cache_manager.project.files),
            "total_items": cache_manager.get_item_count(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore cache backup: {e}")

@app.get("/api/cache/items", response_model=CacheItemsResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_cache_items(page: int = Query(1, ge=1), page_size: Optional[int] = Query(None, ge=1, le=1000), search: str = None, project_path: Optional[str] = None):
    """Get paginated cache items"""
    try:
        output_path = resolve_cache_output_path(project_path or _cache_output_path or "")
        project, revision = _read_cache_snapshot(output_path)

        # Get page size from config if not provided
        if page_size is None:
            try:
                config = get_config_data()
                page_size = max(1, min(1000, int(config.get('cache_editor_page_size', 15))))
            except:
                page_size = 15

        # Extract items (similar to TUI's _extract_cache_items)
        items = []
        for file_path, cache_file in project.files.items():
            for idx, item in enumerate(cache_file.items):
                if item.source_text and item.source_text.strip():
                    translation = ""
                    if item.polished_text:
                        translation = item.polished_text
                    elif item.translated_text:
                        translation = item.translated_text

                    # Include all items with source text (translated or not)
                    items.append({
                        'id': len(items),
                        'project_path': output_path,
                        'project_id': project.project_id,
                        'revision': revision,
                        'file_path': file_path,
                        'text_index': item.text_index,
                        'source': item.source_text,
                        'translation': translation,
                        'original_translation': translation,
                        'translation_status': item.translation_status,
                        'modified': item.translation_status == TranslationStatus.USER_PROOFREAD
                    })

        # Apply search filter
        if search and search.strip():
            search_lower = search.lower()
            items = [
                item for item in items
                if search_lower in item['source'].lower() or search_lower in item['translation'].lower()
            ]

        # Apply pagination
        total_items = len(items)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = items[start_idx:end_idx]

        total_pages = (total_items + page_size - 1) // page_size

        return {
            "items": paginated_items,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache items: {e}")


@app.put("/api/cache/items/{item_id}", response_model=CacheUpdateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def update_cache_item(item_id: int, request: CacheUpdateRequestWithPath):
    if request.item_id != item_id:
        raise HTTPException(status_code=422, detail="Item id does not match the route")
    if any(value is None for value in (
        request.project_id, request.file_path, request.text_index, request.expected_revision,
    )):
        raise HTTPException(status_code=409, detail="Reload cache items to obtain project identity and revision")
    output_path = resolve_cache_output_path(request.project_path)
    with _edit_cache_project(output_path, expected_revision=request.expected_revision) as (cache, _):
        if cache.project.project_id != request.project_id:
            raise HTTPException(status_code=409, detail="Cache project has changed")
        items = [(path, item) for path, file in cache.project.files.items()
                 for item in file.items if item.source_text and item.source_text.strip()]
        if not 0 <= item_id < len(items):
            raise HTTPException(status_code=404, detail="Cache item not found")
        file_path, item = items[item_id]
        if file_path != request.file_path or item.text_index != request.text_index:
            raise HTTPException(status_code=409, detail="Cache item has changed; reload and retry")
        _, store = _load_proofread_store(output_path, request.report_file)
        if item.polished_text:
            item.polished_text = request.translation
        else:
            item.translated_text = request.translation
        item.translation_status = TranslationStatus.USER_PROOFREAD
        if item.extra is None:
            item.extra = {}
        accepted = item.extra.get("proofread_suggestion")
        if isinstance(accepted, dict):
            accepted["superseded_by_manual_edit"] = True
        item.extra["proofread_manual_edit"] = {
            "client": "web", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        cache.save_to_file()
        store.complete_manually_edited_lines(
            cache.project, file_path=file_path, text_index=item.text_index, client="web",
        )
        from ModuleFolders.Service.TaskRuntime.cache_editing import cache_revision
        return {
            "success": True, "message": "Cache item updated successfully",
            "revision": cache_revision(output_path),
            "report": _proofread_report_payload(store) if store.has_report_content() else None,
        }

@app.post("/api/cache/search", response_model=CacheSearchResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def search_cache_items(query: str, scope: str = "all", is_regex: bool = False, project_path: Optional[str] = None):
    """Search cache items with advanced options"""
    try:
        from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
        project, _ = _read_cache_snapshot(resolve_cache_output_path(project_path or _cache_output_path or ""))
        cache_manager = CacheManager(subscribe_events=False)
        cache_manager.load_from_project(project)

        # Use cache manager's search functionality
        results = cache_manager.search_items(query, scope, is_regex, False)

        # Convert results to web format
        search_results = []
        for file_path, line_num, cache_item in results:
            translation = cache_item.polished_text or cache_item.translated_text or ""
            search_results.append({
                "file_path": file_path,
                "line_number": line_num,
                "source": cache_item.source_text,
                "translation": translation,
                "text_index": cache_item.text_index,
                "translation_status": cache_item.translation_status
            })

        return {
            "results": search_results,
            "total_found": len(search_results),
            "query": query,
            "scope": scope
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search cache: {e}")

# --- AI Proofread API ---

_proofread_lock = threading.RLock()
_proofread_run = _BackgroundRun({
    "running": False,
    "progress": 0,
    "total": 0,
    "issues": [],
    "tokens_used": 0,
    "error": None,
    "completed": False,
    "output_path": None,
})


def _require_proofread_report_idle(output_path):
    active = _proofread_run.state
    if active["running"] and active.get("output_path") and (
        resolve_cache_output_path(active["output_path"]) == output_path
    ):
        raise HTTPException(status_code=409, detail="Wait for proofread generation to finish before editing this project")

def _load_proofread_store(project_path: str, report_file: str | None = None):
    from ModuleFolders.Service.Proofreader import ProofreadSuggestionStore

    output_path = resolve_cache_output_path(project_path)
    store = ProofreadSuggestionStore(output_path)
    if report_file:
        archive_name = str(report_file).strip()
        if (
            not archive_name
            or archive_name != os.path.basename(archive_name)
            or "/" in archive_name
            or "\\" in archive_name
        ):
            raise HTTPException(status_code=400, detail="Invalid proofread report file")
        try:
            store.load_archive(store.archive_dir / archive_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid proofread report file") from exc
    else:
        store.load()
    return output_path, store

def _proofread_report_payload(store) -> Dict[str, Any]:
    return {
        "report_file": store.storage_path.name,
        "is_archive": store.is_archive,
        "run": store.run,
        "review_state": store.review_state,
        "summary": store._build_summary(),
        "suggestions": [item.to_dict() for item in store.suggestions],
    }

@app.get("/api/proofread/reports", response_model=ProofreadReportsResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def list_proofread_reports(project_path: str):
    output_path, store = _load_proofread_store(project_path)
    current = None
    if store.path.exists() or store.has_report_content():
        current = {
            "file": store.path.name,
            "is_archive": False,
            "run": store.run,
            "summary": store._build_summary(),
        }
    return {
        "project_path": output_path,
        "current": current,
        "archives": store.archive_summaries(),
    }

@app.get("/api/proofread/suggestions", response_model=ProofreadReportResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_proofread_suggestions(project_path: str, report_file: Optional[str] = None):
    output_path, store = _load_proofread_store(project_path, report_file)
    project, _ = _read_cache_snapshot(output_path)
    store.refresh_conflicts(project, save=False)
    return _proofread_report_payload(store)

@app.get("/api/proofread/locate", response_model=ProofreadLocateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def locate_proofread_item(
    project_path: str,
    file_path: str,
    text_index: int,
    page_size: int = Query(15, ge=1, le=1000),
):
    output_path = resolve_cache_output_path(project_path)
    project, _ = _read_cache_snapshot(output_path)
    normalized_page_size = min(max(int(page_size or 15), 1), 500)
    position = 0
    for current_file_path, cache_file in project.files.items():
        for item in cache_file.items:
            if not item.source_text or not item.source_text.strip():
                continue
            if current_file_path == file_path and int(item.text_index) == int(text_index):
                return {
                    "global_index": position,
                    "page": position // normalized_page_size + 1,
                    "row_index": position % normalized_page_size,
                    "file_path": file_path,
                    "text_index": text_index,
                }
            position += 1
    raise HTTPException(status_code=404, detail="Cache item not found")

def _run_proofread_review_action(
    suggestion_id: str,
    action: str,
    request: ProofreadSuggestionActionRequest,
):
    from ModuleFolders.Service.Proofreader import ProofreadReviewService

    output_path = resolve_cache_output_path(request.project_path)
    with _edit_cache_project(output_path) as (cache_manager, _):
        output_path, store = _load_proofread_store(request.project_path, request.report_file)
        service = ProofreadReviewService(
            store,
            cache_manager.project,
            save_project=cache_manager.save_to_file,
        )
        actions = {
            "reject": service.reject,
            "ignore": service.ignore,
            "restore": service.restore,
            "delete": service.delete,
        }
        if action != "accept" and action not in actions:
            raise HTTPException(status_code=400, detail="Unsupported proofread action")
        try:
            if action == "accept":
                result = service.accept(
                    suggestion_id,
                    client="web",
                    allow_manual_edit_override=request.allow_manual_edit_override,
                )
            else:
                result = actions[action](suggestion_id, client="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        status_code = 200 if result.success else 409
        return JSONResponse(
            status_code=status_code,
            content={
                "success": result.success,
                "suggestion_id": result.suggestion_id,
                "status": str(result.status) if result.status else None,
                "message": result.message,
                "report": _proofread_report_payload(store),
            },
        )

@app.post("/api/proofread/suggestions/{suggestion_id}/{action}", response_model=ProofreadReviewResponse, response_model_exclude_unset=True, responses=PROOFREAD_REVIEW_RESPONSES)
async def review_proofread_suggestion(
    suggestion_id: str,
    action: str,
    request: ProofreadSuggestionActionRequest,
):
    return _run_proofread_review_action(suggestion_id, action, request)

@app.post("/api/proofread/undo", response_model=ProofreadReviewResponse, response_model_exclude_unset=True, responses=PROOFREAD_REVIEW_RESPONSES)
async def undo_proofread_action(request: ProofreadSuggestionActionRequest):
    from ModuleFolders.Service.Proofreader import ProofreadReviewService

    output_path = resolve_cache_output_path(request.project_path)
    with _edit_cache_project(output_path) as (cache_manager, _):
        output_path, store = _load_proofread_store(request.project_path, request.report_file)
        service = ProofreadReviewService(
            store,
            cache_manager.project,
            save_project=cache_manager.save_to_file,
        )
        result = service.undo_last(client="web")
        return JSONResponse(
            status_code=200 if result.success else 409,
            content={
                "success": result.success,
                "suggestion_id": result.suggestion_id,
                "status": str(result.status) if result.status else None,
                "message": result.message,
                "report": _proofread_report_payload(store),
            },
        )

@app.put("/api/proofread/review-state", response_model=ProofreadReviewStateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def update_proofread_review_state(request: ProofreadReviewStateRequest):
    output_path = resolve_cache_output_path(request.project_path)
    with _proofread_lock:
        _require_proofread_report_idle(output_path)
        _, store = _load_proofread_store(request.project_path, request.report_file)
        if request.current_suggestion_id is not None:
            if request.current_suggestion_id and not any(
                item.suggestion_id == request.current_suggestion_id
                for item in store.suggestions
            ):
                raise HTTPException(status_code=400, detail="Unknown proofread suggestion")
            store.review_state["current_suggestion_id"] = request.current_suggestion_id
        if request.active_filter is not None:
            if request.active_filter not in {
                "pending", "ignored", "conflict", "accepted", "rejected", "completed", "all"
            }:
                raise HTTPException(status_code=400, detail="Invalid proofread review filter")
            store.review_state["active_filter"] = request.active_filter
        store.review_state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        store.review_state["updated_by"] = "web"
        store.save()
        return {"success": True, "review_state": store.review_state}

@app.get("/api/proofread/status", response_model=ProofreadStateResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_proofread_status():
    """Get AI proofread task status"""
    with _proofread_lock:
        return dict(_proofread_run.state)

@app.post("/api/proofread/start", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def start_proofread(request: ProofreadStartRequest, background_tasks: BackgroundTasks):
    """Start AI proofread task"""
    with _proofread_lock:
        if _proofread_run.state["running"]:
            raise HTTPException(status_code=400, detail="Proofread task already running")
        return _prepare_proofread_run(request, background_tasks)

def _prepare_proofread_run(request, background_tasks):
    from copy import deepcopy
    from ModuleFolders.Service.Proofreader import ProofreadSuggestionStore, collect_suggestion_items, normalize_suggestion_mode

    global _proofread_run
    output_path = resolve_cache_output_path(request.project_path)
    project, revision = _read_cache_snapshot(output_path)
    if not project.files:
        raise HTTPException(status_code=400, detail="No cache data loaded")
    items = collect_suggestion_items(project)

    config = deepcopy(load_config_sync())
    report_mode = str(request.report_mode or config.get("proofread_report_mode", "archive"))
    try:
        suggestion_mode = normalize_suggestion_mode(
            request.suggestion_mode or config.get("proofread_suggestion_mode", "proofread")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store = ProofreadSuggestionStore(output_path)
    store.load()
    if report_mode == "overwrite" and store.has_report_content() and not request.overwrite_confirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "proofread_overwrite_confirmation_required",
                "summary": store._build_summary(),
            },
        )
    try:
        archive_limit = max(0, int(config.get("proofread_archive_limit", 20)))
    except (TypeError, ValueError):
        archive_limit = 20
    archive_path = store.prepare_new_run(
        mode=report_mode,
        provider=str(config.get("platform", "") or ""),
        model=str(config.get("model", "") or ""),
        archive_limit=archive_limit,
        suggestion_mode=suggestion_mode,
        source_cache_hash=revision,
    )

    run = _BackgroundRun({
        "run_id": store.run["run_id"],
        "source_cache_hash": revision,
        "running": True,
        "progress": 0,
        "total": 0,
        "issues": [],
        "tokens_used": 0,
        "error": None,
        "completed": False,
        "output_path": output_path,
        "report_file": store.path.name,
        "archive_path": str(archive_path) if archive_path else None,
        "suggestion_mode": suggestion_mode,
    })
    background_tasks.add_task(run_proofread_task, run, items, config, store)
    _proofread_run = run
    return {"status": "started", "run_id": run.state["run_id"]}

@app.post("/api/proofread/stop", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def stop_proofread(run_id: Optional[str] = None):
    """Stop AI proofread task"""
    with _proofread_lock:
        run = _proofread_run
        run.check_stop_owner(run_id)
        if run.state["running"]:
            run.cancelled.set()
            run.state["running"] = False
        if run.cancelled.is_set():
            _, store = _load_proofread_store(run.state["output_path"])
            if store.run["run_id"] == run.state["run_id"] and store.run.get("generation_status") == "running":
                store.mark_generation_finished("stopped")
    return {"status": "stopped"}

@app.post("/api/proofread/accept", response_model=ProofreadAcceptResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def accept_proofread_issue(issue_id: str):
    """Accept a persistent suggestion through the shared review service."""
    from ModuleFolders.Service.Proofreader import ProofreadReviewService

    _proofread_state = await get_proofread_status()
    issue = next(
        (
            item
            for item in _proofread_state.get("issues", [])
            if str(item.get("id", "")) == str(issue_id)
            or str(item.get("suggestion_id", "")) == str(issue_id)
        ),
        None,
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    suggestion_id = str(issue.get("suggestion_id") or issue.get("id") or "")
    output_path = str(_proofread_state.get("output_path") or "")
    if not suggestion_id or not output_path:
        raise HTTPException(status_code=400, detail="Persistent proofread report is unavailable")

    report_file = str(_proofread_state.get("report_file") or "")
    if report_file == "ProofreadSuggestions.json":
        report_file = ""
    resolved_output_path = resolve_cache_output_path(output_path)
    with _edit_cache_project(resolved_output_path) as (cache_manager, _):
        resolved_output_path, store = _load_proofread_store(output_path, report_file or None)
        service = ProofreadReviewService(
            store,
            cache_manager.project,
            save_project=cache_manager.save_to_file,
        )
        try:
            result = service.accept(suggestion_id, client="web-legacy")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not result.success:
            raise HTTPException(status_code=409, detail=result.message)

        issue["accepted"] = True
        issue["status"] = str(result.status)
        return {
            "status": "accepted",
            "suggestion_id": suggestion_id,
            "report": _proofread_report_payload(store),
        }


@app.post("/api/proofread/single_check", response_model=ProofreadSingleResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def check_single_line(request: ProofreadSingleRequest):
    """
    On-demand check for a single line with context.
    Used when user clicks 'AI Analyze' on a specific line in editor.
    """
    try:
        from ModuleFolders.Service.Proofreader.AIProofreader import AIProofreader
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

        project, _ = _read_cache_snapshot(resolve_cache_output_path(request.project_path))
        cache_file = project.get_file(request.file_path)
        if not cache_file:
            raise HTTPException(status_code=404, detail="File not found in cache")
        
        item = cache_file.get_item(request.text_index)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Determine target translation: prefer the one sent from web UI (editing state)
        target_translation = request.translation
        if target_translation is None:
            target_translation = item.translated_text or item.polished_text

        # Get context (5 lines before and after)
        list_idx = -1
        for idx, it in enumerate(cache_file.items):
            if it.text_index == request.text_index:
                list_idx = idx
                break
        
        if list_idx == -1:
             raise HTTPException(status_code=404, detail="Item index error")

        context_lines = 5
        start = max(0, list_idx - context_lines)
        end = min(len(cache_file.items), list_idx + context_lines + 1)
        
        context_parts = []
        for i in range(start, end):
            if i != list_idx:
                ctx_item = cache_file.items[i]
                if ctx_item.source_text:
                    # Provide original translation as context if available
                    ctx_trans = ctx_item.translated_text or ctx_item.polished_text or ""
                    context_parts.append(f"[{i}] {ctx_item.source_text[:60]} -> {ctx_trans[:40]}")
        
        context_str = "\n".join(context_parts)
        
        # Load Config
        config = load_config_sync()
        ai_proofreader = AIProofreader(config)
        
        # Run Check
        result = ai_proofreader.proofread_single(
            source=item.source_text,
            translation=target_translation,
            glossary=config.get("prompt_dictionary_data", []),
            context=context_str,
            world_building=config.get("world_building_content", ""),
            writing_style=config.get("writing_style_content", ""),
            characterization=config.get("characterization_data", [])
        )
        
        if not result.has_issues:
            return {"has_issues": False, "message": "AI分析后发现此行并无问题"}
        
        return {
            "has_issues": True,
            "issues": [
                {
                    "type": iss.type,
                    "severity": iss.severity,
                    "description": iss.description,
                    "suggestion": iss.suggestion,
                    "corrected_translation": result.corrected_translation
                } for iss in result.issues
            ],
            "corrected_translation": result.corrected_translation
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

@app.post("/api/proofread/clear", response_model=StatusResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def clear_proofread_issues():
    """Clear all proofread issues"""
    with _proofread_lock:
        _proofread_run.state.update(issues=[], completed=False)
    return {"status": "cleared"}

def load_config_sync() -> Dict[str, Any]:
    """Synchronously load the merged configuration."""
    return _load_active_config_payload()

def run_proofread_task(run: _BackgroundRun, items, config, store):
    """Generate persistent proofread suggestions using the shared CLI pipeline."""
    state = run.state
    try:
        if run.cancelled.is_set():
            return
        import concurrent.futures

        from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        from ModuleFolders.Service.Proofreader import (
            ProofreadRawResponseStore,
            build_proofread_batch,
        )
        from ModuleFolders.Service.Proofreader.ProofreadSuggestionTask import ProofreadSuggestionTask

        output_path = state["output_path"]
        raw_response_store = (
            ProofreadRawResponseStore(output_path)
            if bool(config.get("proofread_save_raw_responses", False))
            else None
        )
        suggestion_mode = state["suggestion_mode"]
        if not items:
            _complete_proofread_run(run, store)
            return

        task_config = TaskConfig()
        task_config.load_config_from_dict(config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)
        limiter = RequestLimiter()
        limiter.set_limit(
            config.get("tpm_limit", getattr(task_config, "tpm_limit", 100000)),
            config.get("rpm_limit", getattr(task_config, "rpm_limit", 60)),
        )
        try:
            batch_size = max(1, int(config.get("proofread_batch_size", config.get("lines_limit", 20))))
        except (TypeError, ValueError):
            batch_size = 20
        try:
            context_count = max(0, int(config.get("proofread_context_lines", 5)))
        except (TypeError, ValueError):
            context_count = 5

        batches = [
            build_proofread_batch(items, index, batch_size)
            for index in range((len(items) + batch_size - 1) // batch_size)
        ]
        with _proofread_lock:
            if run is not _proofread_run or run.cancelled.is_set():
                return
            state["total"] = len(batches)
        glossary = config.get("prompt_dictionary_data", []) or []

        def context_for(index: int) -> list[dict]:
            start = max(0, index * batch_size - context_count)
            end = index * batch_size
            return [
                {
                    "source": item.get("source_text", ""),
                    "translation": item.get("translation", ""),
                }
                for item in items[start:end]
            ]

        def run_batch(index: int):
            task = ProofreadSuggestionTask(
                task_config,
                limiter,
                batches[index],
                glossary=glossary,
                context_lines=context_for(index),
                suggestion_mode=suggestion_mode,
            )
            return task.run()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, int(task_config.actual_thread_counts or 1)),
            thread_name_prefix="web-proofread-suggestion",
        ) as executor:
            futures = [executor.submit(run.invoke, run_batch, index) for index in range(len(batches))]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                with _proofread_lock:
                    if run is not _proofread_run or run.cancelled.is_set():
                        return
                    parsed = result.get("result")
                    if not result.get("skip", True) and parsed is not None:
                        store.add_batch_result(parsed)
                    raw_response = result.get("raw_response")
                    if raw_response_store is not None and isinstance(raw_response, dict):
                        try:
                            raw_response_store.append(
                                {
                                    **raw_response,
                                    "run_id": store.run.get("run_id", ""),
                                    "provider": store.run.get("provider", ""),
                                    "model": store.run.get("model", ""),
                                }
                            )
                        except Exception as exc:
                            print(f"Failed to save proofread raw response: {exc}")
                    state["progress"] += 1
                    state["tokens_used"] += int(result.get("prompt_tokens", 0) or 0)
                    state["tokens_used"] += int(result.get("completion_tokens", 0) or 0)
                    state["issues"] = [
                        {
                            "id": item.suggestion_id,
                            "suggestion_id": item.suggestion_id,
                            "text_index": item.text_index,
                            "file_path": item.file_path,
                            "source": item.source_text,
                            "original_translation": item.current_translation,
                            "corrected_translation": item.suggested_translation,
                            "issue_type": item.issue_type,
                            "severity": item.severity,
                            "description": item.reason,
                            "accepted": str(item.status) == "accepted",
                            "status": str(item.status),
                        }
                        for item in store.suggestions
                    ]

        _complete_proofread_run(run, store)

    except Exception as e:
        with _proofread_lock:
            if run is _proofread_run and not run.cancelled.is_set():
                state.update(running=False, error=str(e))
                store.mark_generation_finished("failed")

def _complete_proofread_run(run, store):
    with _proofread_lock:
        if run is _proofread_run and not run.cancelled.is_set():
            store.mark_generation_completed()
            run.state.update(running=False, completed=True)

# --- Queue Management API ---

def get_queue_manager():
    """Get QueueManager instance"""
    try:
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        return QueueManager(read_only=True)
    except ImportError:
        raise HTTPException(status_code=500, detail="QueueManager not available")

def _refresh_queue(qm, expected_revision=None, *, writing=False):
    if writing and expected_revision is None:
        raise HTTPException(status_code=428, detail="Supply expected_revision from GET /api/queue or /api/queue/raw.")
    if not qm.is_running:
        if os.path.exists(qm.queue_file):
            if not qm.hot_reload_queue(quiet=True, preserve_local_locks=False):
                raise HTTPException(status_code=503, detail="Failed to refresh the task queue.")
        elif qm.revision != "missing":
            qm.load_tasks(qm.queue_file)
    if expected_revision is not None and expected_revision != qm.revision:
        raise HTTPException(status_code=409, detail="Queue changed; reload before retrying.")
    qm.last_save_error = None


def _queue_write_result(qm, saved):
    if saved:
        return {"success": True}
    if qm.last_save_error in ("locked", "conflict"):
        raise HTTPException(status_code=409, detail="Queue changed or contains a protected task; reload before retrying.")
    if qm.last_save_error:
        raise HTTPException(status_code=500, detail="Failed to write queue file")
    raise HTTPException(status_code=400, detail="Invalid queue operation")


def _queue_index(qm, target):
    index = qm.resolve_index(target)
    if index < 0:
        raise HTTPException(status_code=404, detail="Queue task not found")
    return index


@app.get("/api/queue", response_model=list[QueueItemResponse], response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_queue(request: Request, response: Response = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm)
        if response is not None:
            response.headers["X-Queue-Revision"] = qm.revision
        return _queue_rows(qm, request)


def _queue_rows(qm, request):
    try:
        tasks = []

        for idx, task in enumerate(qm.tasks):
            # 获取准确的处理状态
            is_actually_processing = False
            if hasattr(qm, 'is_task_actually_processing'):
                is_actually_processing = qm.is_task_actually_processing(idx)

            try:
                if hasattr(task, "to_task_spec"):
                    public_task_type = task.to_task_spec().task_type
                else:
                    public_task_type = normalize_task_name(getattr(task, "task_type", None))
                task_contract_error = None
            except (AttributeError, TaskContractError, TypeError, ValueError) as exc:
                public_task_type = "invalid"
                task_contract_error = str(exc)

            serialized = task.to_dict()
            task_dict = {
                "task_id": serialized.get("task_id"),
                "revision": qm.revision,
                "protected": not qm.can_modify_task(idx),
                "task_type": public_task_type,
                "execution_mode": serialized.get("execution_mode", "default_api"),
                "runtime_overrides": serialized.get("runtime_overrides", {}),
                "step_overrides": serialized.get("step_overrides", {}),
                "input_path": task.input_path,
                "output_path": getattr(task, "output_path", ""),
                "profile": getattr(task, "profile", ""),
                "rules_profile": getattr(task, "rules_profile", ""),
                "source_lang": getattr(task, "source_lang", ""),
                "target_lang": getattr(task, "target_lang", ""),
                "project_type": getattr(task, "project_type", ""),
                "platform": getattr(task, "platform", ""),
                "api_url": getattr(task, "api_url", ""),
                "api_key": "",
                "api_key_configured": bool(getattr(task, "api_key", "")),
                "model": getattr(task, "model", ""),
                "threads": getattr(task, "threads", None),
                "retry": getattr(task, "retry", None),
                "timeout": getattr(task, "timeout", None),
                "rounds": getattr(task, "rounds", None),
                "pre_lines": getattr(task, "pre_lines", None),
                "lines_limit": getattr(task, "lines_limit", None),
                "tokens_limit": getattr(task, "tokens_limit", None),
                "think_depth": getattr(task, "think_depth", ""),
                "thinking_budget": getattr(task, "thinking_budget", None),
                "failover": getattr(task, "failover", None),
                "resume": getattr(task, "resume", False),
                "polish_mode": getattr(task, "polish_mode", None),
                "status": getattr(task, "status", "waiting"),
                "locked": getattr(task, "locked", False),

                # 新增：准确的处理状态信息
                "is_actually_processing": is_actually_processing,
                "is_processing": getattr(task, "is_processing", False),
                "process_start_time": getattr(task, "process_start_time", None),
                "last_activity_time": getattr(task, "last_activity_time", None)
            }
            if task_contract_error:
                task_dict["task_contract_error"] = task_contract_error
            tasks.append(task_dict)
        if is_mcp_request(request):
            return sanitize_data_for_mcp(tasks, path="/api/queue")

        return tasks
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def add_to_queue(item: QueueTaskItem, request: Request):
    """Add a new task to the queue"""
    try:
        if is_mcp_request(request) and item.api_key == MCP_SECRET_PLACEHOLDER:
            raise HTTPException(
                status_code=400,
                detail="A redacted MCP secret placeholder cannot be used as a new queue API key.",
            )
        if item.api_key:
            raise HTTPException(
                status_code=422,
                detail=(
                    "api_key cannot be stored in a queue file. "
                    "Use a profile or run the task directly."
                ),
            )

        qm = get_queue_manager()
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueTaskItem as QueueTaskItemImpl

        task = QueueTaskItemImpl(**item.to_task_spec().to_queue_fields())

        # Ensure the task has proper defaults
        task.status = "waiting"
        task.locked = False

        if not qm.add_task(task):
            if getattr(qm, "last_save_error", "") == "conflict":
                raise HTTPException(
                    status_code=409,
                    detail="Queue changed since it was loaded; reload and retry.",
                )
            raise HTTPException(status_code=500, detail="Failed to write queue file")
        return {"success": True}
    except TaskContractError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/queue/{index}", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def remove_from_queue(index: int | uuid.UUID, expected_revision: str | None = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        return _queue_write_result(qm, qm.remove_task(_queue_index(qm, index)))

@app.put("/api/queue/{index}", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def update_queue_item(index: int | uuid.UUID, item: QueueTaskUpdate, request: Request, expected_revision: str | None = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        return _update_queue_fields(qm, _queue_index(qm, index), item, request)


def _update_queue_fields(qm, index, item, request):
    from copy import deepcopy

    try:
        task = deepcopy(qm.tasks[index])

        fields_to_update = set(item.model_fields_set)
        preserve_api_key = item.api_key == "" or (
            is_mcp_request(request) and item.api_key == MCP_SECRET_PLACEHOLDER
        )
        if preserve_api_key:
            fields_to_update.discard("api_key")
        elif "api_key" in fields_to_update and item.api_key:
            raise HTTPException(
                status_code=422,
                detail=(
                    "api_key cannot be stored in a queue file. "
                    "Use a profile or run the task directly."
                ),
            )

        existing_payload = task.to_task_spec().to_mapping(
            include_none=True,
            include_api_key=True,
        )
        queue_payload = dict(existing_payload)
        for field_name in fields_to_update:
            queue_payload[field_name] = getattr(item, field_name)
        if "lines" in fields_to_update:
            legacy_lines = queue_payload.pop("lines")
            if "lines_limit" in fields_to_update and queue_payload.get("lines_limit") != legacy_lines:
                raise TaskContractError("Conflicting values for lines and lines_limit")
            queue_payload["lines_limit"] = legacy_lines
            fields_to_update.discard("lines")
            fields_to_update.add("lines_limit")
        if "tokens" in fields_to_update:
            legacy_tokens = queue_payload.pop("tokens")
            if "tokens_limit" in fields_to_update and queue_payload.get("tokens_limit") != legacy_tokens:
                raise TaskContractError("Conflicting values for tokens and tokens_limit")
            queue_payload["tokens_limit"] = legacy_tokens
            fields_to_update.discard("tokens")
            fields_to_update.add("tokens_limit")
        if (
            "task_type" in fields_to_update
            and "polish_mode" not in fields_to_update
            and normalize_task_name(item.task_type) == "translate"
        ):
            queue_payload["polish_mode"] = None
            fields_to_update.add("polish_mode")
        if "lines_limit" in fields_to_update and queue_payload.get("lines_limit") is not None:
            queue_payload["tokens_limit"] = None
            fields_to_update.add("tokens_limit")
        if "tokens_limit" in fields_to_update and queue_payload.get("tokens_limit") is not None:
            queue_payload["lines_limit"] = None
            fields_to_update.add("lines_limit")
        if preserve_api_key:
            queue_payload["api_key"] = existing_payload.get("api_key")
        # TaskSpec 用 None 表示无覆盖，而 model_fields_set 保留显式 null 的清空语义。
        queue_fields = TaskSpec.from_mapping(queue_payload).to_queue_fields(
            include_api_key=True
        )
        for field_name, value in queue_fields.items():
            if field_name not in fields_to_update:
                continue
            setattr(task, field_name, value)
        if "resume" in fields_to_update:
            # 自动化工作流需要区分“未设置”与显式 false；null 用于恢复默认语义。
            task.resume_explicit = item.resume is not None

        return _queue_write_result(qm, qm.update_task(index, task))
    except TaskContractError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue/clear", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def clear_queue(expected_revision: str | None = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        return _queue_write_result(qm, qm.clear_tasks())

@app.post("/api/queue/run", response_model=QueueRunResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def run_queue():
    """Run the queue through the same worker owner as ordinary API tasks."""
    try:
        qm = get_queue_manager()
        if qm.is_running:
            raise HTTPException(status_code=409, detail="The host task queue is already running.")
        conflict_detail = task_manager.task_conflict_detail()
        if conflict_detail:
            raise HTTPException(status_code=409, detail=conflict_detail)

        with qm.state_lock:
            _refresh_queue(qm)
            if not qm.tasks:
                raise HTTPException(status_code=400, detail="Task queue is empty.")
            if any(not qm.can_modify_task(index) for index in range(len(qm.tasks))):
                raise HTTPException(status_code=409, detail="Queue contains a protected task.")

        spec = TaskSpec.from_mapping({"task_type": "queue", "queue_file": qm.queue_file})
        task_id = task_manager.start_task(spec)
        if not task_id:
            conflict_detail = task_manager.task_conflict_detail()
            if conflict_detail:
                raise HTTPException(status_code=409, detail=conflict_detail)
            raise HTTPException(status_code=500, detail="Failed to start queue worker.")
        return {
            "success": True,
            "task_id": task_id,
            "status": task_manager.lifecycle_status,
            "running": task_manager._task_contract()["running"],
        }
    except TaskContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queue/edit_file", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def edit_queue_file():
    raise HTTPException(status_code=410, detail="Use GET and POST /api/queue/raw for validated queue editing.")

@app.get("/api/queue/raw", response_model=QueueRawResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def get_queue_raw(request: Request, response: Response):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm)
        revision = qm.revision
        response.headers["X-Queue-Revision"] = revision
        content = qm.get_queue_json()
    return {"content": sanitize_json_text_for_mcp(content) if is_mcp_request(request) else content, "revision": revision}

@app.post("/api/queue/raw", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def save_queue_raw(request: QueueRawRequest, http_request: Request, expected_revision: str | None = None):
    content = request.content
    try:
        parsed = json.loads(content)
    except (ValueError, RecursionError):
        raise HTTPException(status_code=400, detail="Invalid queue JSON")
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise HTTPException(status_code=400, detail="Queue JSON must be an array of task objects")
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        if is_mcp_request(http_request):
            content = restore_redacted_json_text(content, qm.get_queue_json())
            _ensure_no_mcp_secret_placeholder(json.loads(content), "Queue raw content")
        try:
            return _queue_write_result(qm, qm.load_from_json(content))
        except (ValueError, RecursionError):
            raise HTTPException(status_code=400, detail="Invalid queue JSON or task fields")

@app.put("/api/queue/{from_index}/move", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def move_queue_item(from_index: int | uuid.UUID, request: QueueMoveRequest, expected_revision: str | None = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        return _queue_write_result(qm, qm.move_task(_queue_index(qm, from_index), request.to_index))

@app.post("/api/queue/reorder", response_model=SuccessResponse, response_model_exclude_unset=True, responses=ERROR_RESPONSES)
async def reorder_queue(request: QueueReorderRequest, expected_revision: str | None = None):
    qm = get_queue_manager()
    with qm.state_lock:
        _refresh_queue(qm, expected_revision, writing=True)
        order = [_queue_index(qm, target) for target in request.new_order]
        return _queue_write_result(qm, qm.reorder_tasks(order))

