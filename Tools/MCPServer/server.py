from __future__ import annotations

import argparse
import atexit
import inspect
import json
import os
import re
import secrets
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

RESOURCE_ROOT = os.path.join(PROJECT_ROOT, "Resource")
ROOT_CONFIG_FILE = os.path.join(RESOURCE_ROOT, "config.json")
PROFILES_PATH = os.path.join(RESOURCE_ROOT, "profiles")

from Tools.MCPServer.runtime import inspect_mcp_runtime
from ModuleFolders.Infrastructure.TaskConfig.AgentBatchSettings import ensure_agent_batch_change_confirmed
from Tools.MCPServer.agent_session import get_external_agent_session_registry
from ModuleFolders.Service.Agent.ExternalAgentBatch import (
    ExternalAgentBatchError,
    get_external_agent_batch_service,
)
from ModuleFolders.Service.Agent.ExternalAgentBatchResult import get_external_agent_batch_result_service
from ModuleFolders.Service.Agent.ExternalAgentBatchWriter import ExternalAgentBatchWriter, ExternalAgentBatchWriterError
from ModuleFolders.Service.Agent.ExternalAgentWriterLease import get_external_agent_writer_lease_registry
from Tools.MCPServer.docs import (
    build_security_policy,
    build_tool_category_index,
    build_tool_catalog,
    build_validation_checklist,
    get_server_instructions_text,
    load_mcp_manual,
)
from Tools.MCPServer.security import (
    MCP_AUTH_HEADER,
    MCP_CALLER_HEADER,
    MCP_CALLER_VALUE,
    sanitize_data_for_mcp,
)
from Tools.MCPServer.file_tools import (
    FileToolError,
    detect_file_language_isolated,
    get_agent_read_batch_service,
    read_file_lines,
)
from ModuleFolders.Infrastructure.RemoteAccessPolicy import (
    ensure_bind_allowed,
    is_loopback_bind_host,
    remote_access_enabled,
    resolve_bind_host,
)


def _safe_load_json(path: str) -> Dict[str, Any]:
    """Load a JSON file when it exists, otherwise return an empty dict."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_project_mcp_defaults() -> Dict[str, Any]:
    """
    Resolve MCP defaults from the active project profile when available.

    This matters for stdio launchers: if the user changed `mcp_server_port` in
    project settings, the launcher should probe that same running MCP service
    instead of assuming the hard-coded default port.
    """
    root_config = _safe_load_json(ROOT_CONFIG_FILE)
    active_profile = str(root_config.get("active_profile", "default") or "default")
    profile_path = os.path.join(PROFILES_PATH, f"{active_profile}.json")
    profile_config = _safe_load_json(profile_path)

    merged = {}
    merged.update(root_config)
    merged.update(profile_config)
    return merged


def _resolve_int_setting(config: Dict[str, Any], key: str, fallback: int) -> int:
    try:
        value = config.get(key, fallback)
        return int(value if value not in (None, "") else fallback)
    except Exception:
        return fallback


PROJECT_MCP_DEFAULTS = _load_project_mcp_defaults()

DEFAULT_MCP_HOST = os.environ.get(
    "AINIEE_MCP_HOST",
    resolve_bind_host(PROJECT_MCP_DEFAULTS),
)
DEFAULT_MCP_PORT = int(
    os.environ.get(
        "AINIEE_MCP_PORT",
        str(_resolve_int_setting(PROJECT_MCP_DEFAULTS, "mcp_server_port", 8765)),
    )
)
DEFAULT_MCP_PATH = os.environ.get(
    "AINIEE_MCP_PATH",
    str(PROJECT_MCP_DEFAULTS.get("mcp_server_path", "/mcp") or "/mcp"),
)
DEFAULT_BACKEND_HOST = os.environ.get(
    "AINIEE_MCP_BACKEND_HOST",
    str(PROJECT_MCP_DEFAULTS.get("mcp_backend_host", "127.0.0.1") or "127.0.0.1"),
)
DEFAULT_BACKEND_PORT = int(
    os.environ.get(
        "AINIEE_MCP_BACKEND_PORT",
        str(_resolve_int_setting(PROJECT_MCP_DEFAULTS, "mcp_backend_port", 18000)),
    )
)
DEFAULT_MCP_AUTH_TOKEN = os.environ.get("AINIEE_MCP_AUTH_TOKEN", "")
DEFAULT_REGISTER_ROUTE_TOOLS = (
    os.environ.get("AINIEE_MCP_REGISTER_ROUTE_TOOLS", "").strip().lower()
    in {"1", "true", "yes", "on"}
)

# Connection leases are process-local by design.  They describe which external
# Agent is connected; they never contain project data, task state, or secrets.
AGENT_SESSION_REGISTRY = get_external_agent_session_registry()


def _external_agent_onboarding_accepted() -> bool:
    """Require an explicit project-level acceptance before registering an Agent."""
    root = _safe_load_json(ROOT_CONFIG_FILE)
    return root.get("external_agent_onboarding_status") == "accepted"


def _is_loopback_bind_host(host: str) -> bool:
    return is_loopback_bind_host(host)


def _mcp_tool_doc(summary: str, details: str = "") -> str:
    parts = [summary.strip(), get_server_instructions_text().strip()]
    if details.strip():
        parts.append(details.strip())
    return "\n\n".join(parts)


def _mcp_tool(mcp, summary: str, details: str = ""):
    def decorator(func):
        func.__doc__ = _mcp_tool_doc(summary, details)
        return mcp.tool()(func)

    return decorator


def _t_from_host(host_cli: Any, key: str, default: str) -> str:
    """Read an i18n string from the host CLI when available."""
    i18n = getattr(host_cli, "i18n", None)
    if i18n is None:
        return default

    try:
        value = i18n.get(key)
    except Exception:
        return default

    return default if not value or value == key else value


def _tf_from_host(host_cli: Any, key: str, default: str, **kwargs: Any) -> str:
    """Format a translated string with named placeholders."""
    template = _t_from_host(host_cli, key, default)
    try:
        return template.format(**kwargs)
    except Exception:
        return default.format(**kwargs)


class EmbeddedWebServerController:
    def __init__(
        self,
        host: str,
        port: int,
        host_cli: Any = None,
        startup_timeout: float = 8.0,
        log_level: str = "info",
        mcp_auth_token: str = "",
        allow_remote_access: bool = False,
    ):
        self.host = host
        self.port = port
        self.host_cli = host_cli
        self.startup_timeout = startup_timeout
        self.log_level = log_level
        self.mcp_auth_token = mcp_auth_token
        self.allow_remote_access = allow_remote_access
        self.started_by_self = False
        self.thread = None
        self.ws_module = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self.mcp_auth_token:
            os.environ["AINIEE_MCP_AUTH_TOKEN"] = self.mcp_auth_token

        import Tools.WebServer.web_server as ws_module

        self.ws_module = ws_module
        if self.mcp_auth_token:
            # WebServer may have been imported before MCP generated its bridge token.
            ws_module.MCP_AUTH_TOKEN = self.mcp_auth_token
        if self.host_cli is not None:
            try:
                self.host_cli.web_runtime_bridge._configure_web_handlers(ws_module)
            except Exception:
                pass

        if _is_port_open(self.host, self.port):
            self._verify_reused_backend_access()
            return

        self.thread = ws_module.run_server(
            host=self.host,
            port=self.port,
            monitor_mode=False,
            log_level=self.log_level,
            allow_remote_access=self.allow_remote_access,
        )
        self.started_by_self = self.thread is not None

        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if _is_port_open(self.host, self.port):
                return
            current_server = getattr(self.ws_module, "_current_server", None)
            if current_server is not None and getattr(current_server, "is_running", False):
                return
            if self.thread is not None and not self.thread.is_alive():
                break
            time.sleep(0.2)

        raise RuntimeError(
            _tf_from_host(
                self.host_cli,
                "msg_mcp_embedded_web_start_failed",
                "Embedded WebServer failed to start on {host}:{port}.",
                host=self.host,
                port=self.port,
            )
        )

    def _verify_reused_backend_access(self) -> None:
        """Verify that an already-running backend accepts this MCP bridge token."""
        import requests

        try:
            response = requests.get(
                f"{self.base_url}/api/config",
                headers={
                    MCP_CALLER_HEADER: MCP_CALLER_VALUE,
                    MCP_AUTH_HEADER: self.mcp_auth_token,
                },
                timeout=min(max(self.startup_timeout, 0.5), 5.0),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Unable to verify the existing WebServer MCP bridge token at {self.base_url}."
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                "The existing WebServer rejected the MCP bridge token. "
                "Start both processes with the same AINIEE_MCP_AUTH_TOKEN or use a free backend port."
            )

    def stop(self) -> None:
        if not self.started_by_self or self.ws_module is None:
            return
        try:
            self.ws_module.stop_server()
        except Exception:
            pass


class AiNieeAPIClient:
    def __init__(self, base_url: str, timeout: float = 20.0, mcp_auth_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.mcp_auth_token = mcp_auth_token

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Any] = None,
    ) -> Any:
        import requests

        response = requests.request(
            method=method.upper(),
            url=f"{self.base_url}{path}",
            params=params,
            json=payload,
            headers={
                MCP_CALLER_HEADER: MCP_CALLER_VALUE,
                MCP_AUTH_HEADER: self.mcp_auth_token,
            },
            timeout=self.timeout,
        )

        try:
            data = response.json()
        except Exception:
            data = response.text

        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} {path}: {data}")

        # 再做一层兜底脱敏，避免未来新增接口忘记在 WebServer 里声明 MCP 侧限制。
        return sanitize_data_for_mcp(data, path=path)


def _patch_streamable_http_shutdown_for_windows() -> None:
    """
    Reduce noisy ASGI shutdown errors for active MCP SSE streams on Windows.

    When the operator stops the streamable-http MCP server while a client still
    has an active GET/POST stream pair, uvicorn can log
    "ASGI callable returned without completing response" during teardown. We
    patch the session manager at runtime so active transports are explicitly
    terminated before the upstream task group is cancelled.
    """
    if os.name != "nt":
        return

    import contextlib

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    if getattr(StreamableHTTPSessionManager.run, "__ainiee_shutdown_patch__", False):
        return

    original_run = StreamableHTTPSessionManager.run

    @contextlib.asynccontextmanager
    async def patched_run(self):
        async with original_run(self):
            try:
                yield
            finally:
                for transport in list(getattr(self, "_server_instances", {}).values()):
                    with contextlib.suppress(Exception):
                        await transport.terminate()

    patched_run.__ainiee_shutdown_patch__ = True
    StreamableHTTPSessionManager.run = patched_run


def _normalize_transport(transport: str) -> str:
    value = (transport or "stdio").strip().lower()
    aliases = {
        "http": "streamable-http",
        "streamable_http": "streamable-http",
        "streamable-http": "streamable-http",
        "sse": "sse",
        "stdio": "stdio",
    }
    return aliases.get(value, value)


def _normalize_client_probe_host(host: str) -> str:
    """Convert wildcard listen hosts into a concrete loopback address for client probes."""
    value = (host or "").strip()
    if value in {"", "0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return value


def _normalize_http_path(path: str) -> str:
    value = (path or "/mcp").strip()
    return value if value.startswith("/") else f"/{value}"


def _build_mcp_service_url(host: str, port: int, path: str) -> str:
    probe_host = _normalize_client_probe_host(host)
    return f"http://{probe_host}:{port}{_normalize_http_path(path)}"


def _write_startup_notice(message: str) -> None:
    """Emit lightweight startup diagnostics to stderr without polluting MCP stdout."""
    try:
        print(message, file=sys.stderr, flush=True)
    except Exception:
        pass


def _extract_probe_response_payload(response_text: str, content_type: str) -> Any:
    """Decode either JSON or single-message SSE probe responses into a Python object."""
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type == "application/json":
        return json.loads(response_text)

    if normalized_type == "text/event-stream":
        data_lines = []
        for line in response_text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            return json.loads("\n".join(data_lines))

    raise ValueError(f"Unsupported MCP probe response content type: {content_type}")


async def _probe_streamable_http_mcp(url: str) -> bool:
    """
    Verify that an existing HTTP endpoint is actually an MCP server.

    We do a lightweight initialize round-trip instead of trusting only "port is
    open", so unrelated services on the same port do not get treated as MCP.
    This probe intentionally stays at raw HTTP level and skips the follow-up
    `notifications/initialized` exchange, which avoids noisy SSE teardown logs
    on the already-running MCP service.
    """
    import contextlib
    import httpx
    from mcp.types import LATEST_PROTOCOL_VERSION

    client = httpx.AsyncClient(timeout=httpx.Timeout(2.0, read=2.0))
    session_id = ""
    try:
        response = await client.post(
            url,
            headers={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": "ainiee-cli-reuse-probe",
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "ainiee-cli-reuse-probe",
                        "version": "1.0.0",
                    },
                },
            },
        )
        session_id = response.headers.get("mcp-session-id", "")
        if response.status_code >= 400:
            return False

        data = _extract_probe_response_payload(
            response.text,
            response.headers.get("content-type", ""),
        )
        if not isinstance(data, dict):
            return False

        result = data.get("result")
        if not isinstance(result, dict):
            return False

        protocol_version = result.get("protocolVersion")
        server_info = result.get("serverInfo")
        return bool(protocol_version and isinstance(server_info, dict) and server_info.get("name"))
    except Exception:
        return False
    finally:
        if session_id:
            with contextlib.suppress(Exception):
                await client.delete(url, headers={"mcp-session-id": session_id})
        await client.aclose()


def _is_expected_proxy_disconnect(exc: BaseException) -> bool:
    """
    Treat common transport teardown errors as a normal client disconnect.

    On Windows, short-lived MCP clients may close their stdio pipe or HTTP
    stream before every async task has fully unwound. Those disconnects are
    expected during tool discovery and should not become noisy tracebacks.
    """
    if exc.__class__.__name__ in {"ClosedResourceError", "BrokenResourceError", "EndOfStream"}:
        return True

    if isinstance(exc, (BrokenPipeError, ConnectionResetError, EOFError)):
        return True

    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, BaseException) and _is_expected_proxy_disconnect(cause)


async def _close_stream_safely(stream) -> None:
    """Close an anyio stream without surfacing teardown noise during proxy shutdown."""
    try:
        await stream.aclose()
    except Exception:
        pass


async def _pipe_session_messages(source, sink, direction: str) -> None:
    """Forward MCP SessionMessage objects between stdio and streamable-http transports."""
    async for item in source:
        if isinstance(item, Exception):
            if _is_expected_proxy_disconnect(item):
                return
            raise RuntimeError(f"MCP proxy stream error ({direction}): {item}") from item
        await sink.send(item)


async def _run_stdio_proxy_to_existing_mcp(url: str) -> None:
    """
    Bridge a stdio MCP client to an already running streamable-http MCP service.

    Some LLM clients eagerly spawn the configured MCP process on startup. When an
    AiNiee MCP HTTP service is already running, reusing it avoids duplicate
    backend startup and keeps all clients attached to the same MCP runtime.
    """
    import anyio
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (local_read, local_write):
        async with streamable_http_client(url, terminate_on_close=True) as (
            remote_read,
            remote_write,
            _,
        ):
            async def bridge_local_to_remote() -> None:
                try:
                    await _pipe_session_messages(local_read, remote_write, "stdio -> http")
                except Exception as exc:
                    if not _is_expected_proxy_disconnect(exc):
                        raise
                finally:
                    # Let the HTTP transport unwind naturally so terminate_on_close
                    # can send DELETE /mcp instead of forcing a TCP reset.
                    await _close_stream_safely(remote_write)

            async def bridge_remote_to_local(cancel_scope) -> None:
                try:
                    await _pipe_session_messages(remote_read, local_write, "http -> stdio")
                except Exception as exc:
                    if not _is_expected_proxy_disconnect(exc):
                        raise
                finally:
                    await _close_stream_safely(local_write)
                    await _close_stream_safely(remote_write)
                    cancel_scope.cancel()

            async with anyio.create_task_group() as tg:
                tg.start_soon(bridge_local_to_remote)
                tg.start_soon(bridge_remote_to_local, tg.cancel_scope)


def is_reusable_mcp_service_running(host: str, port: int, path: str) -> bool:
    """
    Check whether a reusable streamable-http MCP service is already serving this route.

    This is shared by the stdio launcher and the menu runtime bridge so both code
    paths make the same decision about "already running" state.
    """
    reuse_url = _build_mcp_service_url(host, port, path)
    probe_host = _normalize_client_probe_host(host)
    if not _is_port_open(probe_host, port):
        return False

    import anyio

    return bool(anyio.run(_probe_streamable_http_mcp, reuse_url))


def _try_get_reusable_mcp_service_url(transport: str, host: str, port: int, path: str) -> str | None:
    """
    Return a reusable MCP HTTP endpoint for stdio launchers when one is already running.

    Only stdio launchers reuse an existing MCP service. HTTP/SSE launches are
    the service itself and should continue following their normal startup path.
    """
    if _normalize_transport(transport) != "stdio":
        return None

    if os.environ.get("AINIEE_MCP_DISABLE_RUNNING_REUSE", "").strip().lower() in {"1", "true", "yes"}:
        return None

    return _build_mcp_service_url(host, port, path)


def _render_path_template(path_template: str, path_params: Optional[Dict[str, Any]] = None) -> str:
    rendered_path = path_template
    path_params = path_params or {}

    required_params = re.findall(r"{([^}]+)}", path_template)
    missing = [name for name in required_params if name not in path_params]
    if missing:
        raise ValueError(
            f"Missing path parameter(s) for {path_template}: {', '.join(missing)}"
        )

    for key, value in path_params.items():
        rendered_path = rendered_path.replace(f"{{{key}}}", str(value))

    return rendered_path


def _sanitize_tool_name(method: str, path: str) -> str:
    normalized = path.strip("/")
    normalized = re.sub(r"{([^}]+)}", r"by_\1", normalized)
    normalized = normalized.replace("/", "_")
    normalized = normalized.replace("-", "_")
    normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = "root"
    return f"api_{method.lower()}_{normalized}"


def _is_public_api_route(path: str) -> bool:
    return path.startswith("/api/") and not (
        path == "/api/internal" or path.startswith("/api/internal/")
    )


def _extract_api_routes(ws_module) -> List[Dict[str, str]]:
    routes: List[Dict[str, str]] = []
    seen = set()

    for route in ws_module.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)

        if not _is_public_api_route(path) or not methods:
            continue

        for method in sorted(methods):
            if method not in {"GET", "POST", "PUT", "DELETE"}:
                continue

            route_key = (method, path)
            if route_key in seen:
                continue
            seen.add(route_key)

            routes.append(
                {
                    "method": method,
                    "path": path,
                    "tool_name": _sanitize_tool_name(method, path),
                }
            )

    routes.sort(key=lambda item: (item["path"], item["method"]))
    return routes


def _route_category(path: str) -> str:
    stripped = path.strip("/")
    parts = stripped.split("/")
    if len(parts) < 2:
        return "misc"
    return parts[1]


def _filter_routes_by_category(
    routes: List[Dict[str, str]],
    category: str = "all",
) -> List[Dict[str, str]]:
    normalized = (category or "all").strip().lower().replace(" ", "_")
    if normalized in {"all", "*"}:
        return routes
    return [route for route in routes if _route_category(route["path"]) == normalized]


def _build_route_index(
    routes: List[Dict[str, str]],
    *,
    route_tools_exposed: bool,
) -> List[Dict[str, str]]:
    route_index = []
    for route in routes:
        item = {
            "method": route["method"],
            "path": route["path"],
            "category": _route_category(route["path"]),
        }
        if route_tools_exposed:
            item["route_tool_name"] = route["tool_name"]
        route_index.append(item)
    return route_index


def _normalize_public_api_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if not _is_public_api_route(normalized):
        raise ValueError(
            "Only public /api/* routes are available through MCP. "
            "Internal routes and non-MCP Web UI paths are not available through this tool."
        )
    return normalized


def _register_route_proxy_tools(mcp, api: AiNieeAPIClient, routes: List[Dict[str, str]]) -> None:
    # 自动把 WebServer 的 JSON API 映射成 MCP tools，尽量保持 Web 与 MCP 能力面对齐。
    for route_meta in routes:
        if route_meta["path"] == "/api/files/upload":
            continue

        method = route_meta["method"]
        path = route_meta["path"]
        tool_name = route_meta["tool_name"]
        route_category = _route_category(path)

        def make_route_tool(route_method: str, route_path: str, route_tool_name: str):
            def route_tool(
                path_params: Optional[Dict[str, Any]] = None,
                query: Optional[Dict[str, Any]] = None,
                body: Optional[Any] = None,
                confirm_advanced_change: bool = False,
                confirm_agent_batch_change: bool = False,
            ) -> Any:
                """
                Proxy one WebServer API route through MCP.

                path_params fills placeholders in the original FastAPI path.
                query maps to URL query params.
                body maps to the JSON request body.
                confirm_advanced_change must be true before changing MCP advanced settings.
                confirm_agent_batch_change requires explicit user consent for batch limit changes.
                """
                _ensure_advanced_change_confirmed(route_path, body, confirm_advanced_change)
                if route_path == "/api/config":
                    ensure_agent_batch_change_confirmed(body, confirm_agent_batch_change)
                rendered_path = _render_path_template(route_path, path_params)
                return api.request(route_method, rendered_path, params=query, payload=body)

            route_tool.__name__ = route_tool_name
            route_tool.__doc__ = _mcp_tool_doc(
                f"Proxy WebServer route {_method_display(route_method)} {route_path}. Category: {route_category}.",
                (
                    "Use path_params for templated segments, query for URL params, body for JSON payload. "
                    "Call get_mcp_tool_categories first, then get_mcp_tool_catalog(category='<needed-category>') "
                    "for structured examples. Do not guess API paths."
                ),
            )
            return route_tool

        route_tool = make_route_tool(method, path, tool_name)
        mcp.tool()(route_tool)


def _method_display(method: str) -> str:
    return method.upper()


def _needs_advanced_change_confirmation(path: str, body: Any) -> bool:
    if path != "/api/config" or not isinstance(body, dict):
        return False
    return any(key in body for key in ("mcp_server_port", "mcp_server_host"))


def _ensure_advanced_change_confirmed(path: str, body: Any, confirmed: bool) -> None:
    if _needs_advanced_change_confirmation(path, body) and not confirmed:
        raise RuntimeError(
            "Changing MCP advanced settings requires a second confirmation. "
            "Ask the user again, then retry with confirm_advanced_change=true. "
            "The MCP client route may also need to be updated after the change."
        )


def _finalize_external_agent_output(ws_module: Any, task_id: str, cache_path: str) -> Dict[str, Any] | None:
    """Export a completed cache-backed external task once all batches commit."""
    manager = getattr(ws_module, "task_manager", None)
    if manager is None or getattr(manager, "task_id", None) != task_id:
        return None
    if getattr(manager, "stats", {}).get("execution_mode") != "external_agent":
        return None
    input_path = getattr(manager, "external_agent_input_path", None)
    output_path = getattr(manager, "external_agent_output_path", None)
    if not input_path or not output_path:
        return None
    from ModuleFolders.Domain.FileOutputer.FileOutputer import FileOutputer
    from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

    cache_manager = ws_module.get_cache_manager()
    cache_root = str(Path(cache_path).resolve().parent.parent)
    cache_manager.load_from_file(cache_root, interactive_recovery=False)
    config = ws_module._load_active_config_payload()
    task_config = TaskConfig()
    task_config.initialize(config)
    output_config = {
        "translated_suffix": config.get("output_filename_suffix", "_translated"),
        "bilingual_suffix": "_bilingual",
        "bilingual_order": config.get("bilingual_text_order", "source_first"),
        "enable_bilingual_output": config.get("enable_bilingual_output", False),
        "epub_layout_mode": config.get("epub_layout_mode", "off"),
        "sync_metadata_title": config.get("sync_output_metadata_title", False),
    }
    FileOutputer().output_translated_content(
        cache_manager.project,
        output_path,
        input_path,
        output_config,
        task_config,
    )
    manager.external_agent_cache_path = str(Path(cache_path).resolve())
    manager.update_external_agent_status(
        "committed",
        task_id,
        "All external-Agent batches committed; exporting final output.",
    )
    manager.update_external_agent_status(
        "completed",
        task_id,
        "External-Agent cache committed and final output exported.",
    )
    return {
        "status": "exported",
        "output_path": output_path,
        "cache_path": str(Path(cache_path).resolve()),
    }


def _export_external_agent_task(
    task_id: str,
    session_id: str,
    *,
    input_path: str | None = None,
    output_path: str | None = None,
) -> Dict[str, Any]:
    """Export a completed cache-backed task without relying on Web process state."""
    batch_service = get_external_agent_batch_service()
    metadata = batch_service.export_metadata(task_id, session_id)
    if not metadata.get("cache_path"):
        raise ExternalAgentBatchError("task is not cache-backed", "CACHE_MANIFEST_REQUIRED")
    batches = metadata.get("batches") or []
    if not batches or any(item.get("status") != "committed" for item in batches):
        raise ExternalAgentBatchError(
            "all translation batches must be committed before export",
            "BATCH_COMMIT_REQUIRED",
        )
    input_path = input_path or metadata.get("input_path")
    selected_output = output_path or metadata.get("output_path")
    if not input_path or not selected_output:
        raise ExternalAgentBatchError(
            "export requires the persisted input_path and output_path",
            "EXPORT_PATHS_REQUIRED",
        )
    input_path = str(Path(input_path).expanduser().resolve(strict=True))
    selected_output = str(Path(selected_output).expanduser().resolve())
    cache_path = str(Path(metadata["cache_path"]).expanduser().resolve(strict=True))
    if Path(input_path).resolve() == Path(selected_output).resolve():
        raise ExternalAgentBatchError("output_path must differ from input_path", "EXPORT_PATH_CONFLICT")

    from ModuleFolders.Domain.FileOutputer.FileOutputer import FileOutputer
    from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

    try:
        from Tools.WebServer.web_server import _load_active_config_payload

        config = _load_active_config_payload()
    except Exception:
        config = {}
    cache_manager = get_external_agent_batch_service()
    from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager

    loaded_cache = CacheManager()
    loaded_cache.load_from_file(str(Path(cache_path).parent.parent), interactive_recovery=False)
    task_config = TaskConfig()
    task_config.initialize(config)
    output_config = {
        "translated_suffix": config.get("output_filename_suffix", "_translated"),
        "bilingual_suffix": "_bilingual",
        "bilingual_order": config.get("bilingual_text_order", "source_first"),
        "enable_bilingual_output": config.get("enable_bilingual_output", False),
        "epub_layout_mode": config.get("epub_layout_mode", "off"),
        "sync_metadata_title": config.get("sync_output_metadata_title", False),
    }
    artifacts = FileOutputer().output_translated_content(
        loaded_cache.project,
        selected_output,
        input_path,
        output_config,
        task_config,
    )
    return {
        "status": "exported",
        "task_id": task_id,
        "input_path": input_path,
        "output_path": selected_output,
        "cache_path": cache_path,
        "artifacts": [str(item[0]) for item in (artifacts or [])],
    }


def _build_mcp_app(
    api: AiNieeAPIClient,
    ws_module,
    host: str,
    port: int,
    path: str,
    host_cli: Any = None,
    register_route_tools: bool = DEFAULT_REGISTER_ROUTE_TOOLS,
):
    try:
        _patch_streamable_http_shutdown_for_windows()
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        status = inspect_mcp_runtime(PROJECT_ROOT)
        primary_install = status.get("primary_install_command") or "uv add mcp"
        raise RuntimeError(
            _tf_from_host(
                host_cli,
                "msg_mcp_missing_python_module_install",
                "Missing Python module '{module_name}'. Suggested install: {command}",
                module_name="mcp",
                command=primary_install,
            )
        ) from exc

    mcp = FastMCP(
        "AiNiee CLI MCP",
        instructions=get_server_instructions_text(),
        host=host,
        port=port,
        streamable_http_path=path,
    )

    routes = _extract_api_routes(ws_module)

    @_mcp_tool(
        mcp,
        "Read the built-in MCP usage manual.",
        (
            "Call this first when the MCP client cannot inspect repository files. "
            "It also states that LLM-driven operations should use MCP tools instead of direct Web UI HTTP requests."
        ),
    )
    def get_mcp_usage_manual(section: str = "all") -> str:
        return load_mcp_manual(section)

    @_mcp_tool(
        mcp,
        "Read the MCP security policy.",
        (
            "This explains Web UI session cookie / MCP bridge token channel gates "
            "and how secret redaction behaves."
        ),
    )
    def get_mcp_security_policy() -> Dict[str, Any]:
        return build_security_policy()

    @_mcp_tool(
        mcp,
        "Read the lightweight MCP category index.",
        (
            "Use this before get_mcp_tool_catalog(category=...) so the client only loads "
            "the endpoint category it actually needs."
        ),
    )
    def get_mcp_tool_categories() -> Dict[str, Any]:
        return build_tool_category_index(
            routes,
            route_tools_exposed=register_route_tools,
        )

    @_mcp_tool(
        mcp,
        "Read the structured MCP endpoint catalog for one category.",
        (
            "Defaults to a lightweight category index. Pass category='config', category='queue', "
            "or another category from get_mcp_tool_categories to avoid loading the full catalog."
        ),
    )
    def get_mcp_tool_catalog(category: str = "index", include_examples: bool = True) -> Dict[str, Any]:
        return build_tool_catalog(
            routes,
            category=category,
            include_examples=include_examples,
            route_tools_exposed=register_route_tools,
        )

    @_mcp_tool(
        mcp,
        "Read the four MCP security validation scenarios.",
        "Use this to validate config/queue redaction and placeholder writeback protection.",
    )
    def get_mcp_validation_checklist() -> Dict[str, Any]:
        return build_validation_checklist()

    @_mcp_tool(
        mcp,
        "Register an external Agent connection and receive a renewable session lease.",
        (
            "Call this when an external Agent begins using AiNiee. The returned session_id "
            "is required for heartbeat and unregister. Registration records connection metadata only. "
            "The default lease is 120 seconds; requested_lease_seconds may be set up to 3600 "
            "seconds (60 minutes)."
        ),
    )
    def agent_register(
        agent_instance_id: str,
        protocol_version: str = "1",
        client_name: str = "",
        client_version: str = "",
        capabilities: Optional[List[str]] = None,
        supported_modes: Optional[List[str]] = None,
        transport: str = "mcp",
        requested_lease_seconds: Optional[int] = None,
        user_confirmed_external_processing: bool = False,
    ) -> Dict[str, Any]:
        if not _external_agent_onboarding_accepted():
            raise ValueError(
                "External Agent onboarding has not been accepted by the user. "
                "Complete the AiNiee onboarding flow before registering a session."
            )
        return AGENT_SESSION_REGISTRY.register(
            {
                "protocol_version": protocol_version,
                "agent_instance_id": agent_instance_id,
                "client_name": client_name,
                "client_version": client_version,
                "capabilities": capabilities or [],
                "supported_modes": supported_modes or [],
                "transport": transport,
                "requested_lease_seconds": requested_lease_seconds,
                "user_confirmed_external_processing": user_confirmed_external_processing,
            }
        )

    @_mcp_tool(
        mcp,
        "Renew an external Agent connection lease.",
        "Send the session_id and agent_instance_id returned by agent_register.",
    )
    def agent_heartbeat(session_id: str, agent_instance_id: str) -> Dict[str, Any]:
        return AGENT_SESSION_REGISTRY.heartbeat(
            session_id,
            agent_instance_id=agent_instance_id,
        )

    @_mcp_tool(
        mcp,
        "End an external Agent connection lease.",
        "Use the session_id and agent_instance_id returned by agent_register.",
    )
    def agent_unregister(
        session_id: str,
        agent_instance_id: str,
        reason: str = "client_shutdown",
    ) -> Dict[str, Any]:
        return AGENT_SESSION_REGISTRY.unregister(
            session_id,
            agent_instance_id=agent_instance_id,
            reason=reason,
        )

    @_mcp_tool(
        mcp,
        "Read connected external Agent session status.",
        "Pass session_id for one lease, or omit it to list all active leases.",
    )
    def agent_status(session_id: Optional[str] = None) -> Dict[str, Any]:
        result = AGENT_SESSION_REGISTRY.status(session_id)
        return result if isinstance(result, dict) else {"session_id": session_id, "state": "missing"}

    @_mcp_tool(
        mcp,
        "Request the runtime MCP external-Agent mode for a registered session.",
        (
            "This is a port-only runtime request. It does not edit Profile/config.json or change "
            "AiNiee's default API mode. Registration must already include onboarding and explicit "
            "user confirmation; pass task_id to scope the grant to one task when available."
        ),
    )
    def agent_request_external_mode(
        session_id: str,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not _external_agent_onboarding_accepted():
            raise ValueError(
                "ONBOARDING_NOT_ACCEPTED: external Agent onboarding has not been accepted by the user"
            )
        _require_external_agent_session(session_id)
        try:
            return AGENT_SESSION_REGISTRY.request_external_mode(session_id, task_id=task_id)
        except Exception as exc:
            code = getattr(exc, "code", "EXTERNAL_MODE_REJECTED")
            raise ValueError(f"{code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Read a bounded window of source items for an external Agent.",
        (
            "Use this for terminology extraction or other Agent-side analysis. "
            "Each call returns at most 1000 logical source lines; use next_start_line "
            "to continue. Paths must be inside the MCP workspace or the controlled "
            "temporary directory. This tool never writes source files, glossary data, "
            "cache, or output."
        ),
    )
    def agent_read_file(
        path: str,
        start_line: int = 0,
        max_lines: int = 1000,
        project_type: str = "auto",
    ) -> Dict[str, Any]:
        try:
            return read_file_lines(
                path,
                start_line=start_line,
                max_lines=max_lines,
                project_type=project_type,
            )
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Detect the main language of a selected file.",
        (
            "Returns a ranked language profile and the dominant ISO language code. "
            "Scans the entire file and returns statistics without source text. "
            "The 1000-line transfer limit applies only to source-reading batches, "
            "not language detection. Paths follow the agent_read_file workspace boundary."
        ),
    )
    async def agent_detect_file_language(
        path: str,
        project_type: str = "auto",
    ) -> Dict[str, Any]:
        try:
            return await detect_file_language_isolated(path, project_type=project_type)
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Prepare a read-only source file into 1000-line Agent analysis batches.",
        "Use agent_claim_read_batch after this call. This protocol is intended for terminology extraction and does not write glossary or translation output.",
    )
    def agent_prepare_read_batches(
        path: str,
        task_id: str,
        session_id: str,
        project_type: str = "auto",
    ) -> Dict[str, Any]:
        _require_external_agent_session(session_id)
        try:
            return get_agent_read_batch_service().prepare(
                path, task_id, session_id, project_type=project_type
            )
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Claim one read-only source batch for Agent analysis.",
        "Each returned batch contains at most 1000 source lines and includes batch_id, source_hash, and task revision. Omit batch_id to claim the next pending batch.",
    )
    def agent_claim_read_batch(
        task_id: str,
        session_id: str,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        _require_external_agent_session(session_id)
        try:
            return get_agent_read_batch_service().claim(task_id, session_id, batch_id)
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Mark one read-only source batch complete and release the read cursor.",
        "Call this after the Agent has extracted terminology from the claimed batch, then claim the next batch.",
    )
    def agent_complete_read_batch(
        task_id: str,
        session_id: str,
        batch_id: str,
    ) -> Dict[str, Any]:
        _require_external_agent_session(session_id)
        try:
            return get_agent_read_batch_service().complete(task_id, session_id, batch_id)
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Release a claimed read-only source batch after a disconnect.",
        "Releases the read cursor without changing source text or terminology data.",
    )
    def agent_release_read_batch(
        task_id: str,
        session_id: str,
        batch_id: str,
    ) -> Dict[str, Any]:
        _require_external_agent_session(session_id)
        try:
            return get_agent_read_batch_service().release(task_id, session_id, batch_id)
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Recover read-batch identifiers after a lost prepare or claim response.",
        "Returns compact read-task state without source text.",
    )
    def agent_read_batch_status(task_id: str, session_id: str) -> Dict[str, Any]:
        _require_external_agent_session(session_id)
        try:
            return get_agent_read_batch_service().status(task_id, session_id)
        except FileToolError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    def _require_external_agent_session(session_id: str) -> None:
        record = AGENT_SESSION_REGISTRY.status(session_id)
        if not isinstance(record, dict) or record.get("state") != "registered":
            raise ValueError("Agent session is not registered or has expired.")

    def _require_external_agent_mode(session_id: str, task_id: str | None = None) -> None:
        _require_external_agent_session(session_id)
        try:
            granted = AGENT_SESSION_REGISTRY.has_external_mode(session_id, task_id=task_id)
        except Exception as exc:
            raise ValueError(f"EXTERNAL_MODE_REQUIRED: {exc}") from exc
        if not granted:
            raise ValueError(
                "EXTERNAL_MODE_REQUIRED: call agent_request_external_mode through MCP before task operations"
            )

    def _bind_external_agent_context(
        session_id: str,
        *,
        task_id: str | None = None,
        batch_id: str | None = None,
    ) -> None:
        try:
            AGENT_SESSION_REGISTRY.update_context(
                session_id, task_id=task_id, batch_id=batch_id
            )
        except Exception:
            # The domain operation is already durable. A status-only metadata
            # update must never turn a successful batch operation into a retry.
            return

    def _prepare_web_task_ledger_if_needed(task_id: str, session_id: str) -> Dict[str, Any] | None:
        """Create the cache-backed ledger for a prewarmed Web external task."""
        manager = getattr(ws_module, "task_manager", None)
        if manager is None or getattr(manager, "task_id", None) != task_id:
            return None
        cache_path = getattr(manager, "external_agent_cache_path", None)
        if not isinstance(cache_path, str) or not cache_path:
            return None
        batch_service = get_external_agent_batch_service()
        try:
            return batch_service.get_project(task_id, session_id)
        except ExternalAgentBatchError as exc:
            if exc.code != "TASK_NOT_FOUND":
                raise
        try:
            prepared = batch_service.prepare_cache_project(
                cache_path,
                task_id,
                session_id,
                "external_agent",
                input_path=getattr(manager, "external_agent_input_path", None),
                output_path=getattr(manager, "external_agent_output_path", None),
            )
            _bind_external_agent_context(session_id, task_id=task_id)
            return prepared
        except (ExternalAgentBatchError, ValueError) as exc:
            code = getattr(exc, "code", "CACHE_MANIFEST_INVALID")
            raise ValueError(f"{code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Prepare a controlled external-Agent translation project.",
        "Reads only the selected input file and creates a durable batch ledger; it never writes the cache or final output.",
    )
    def agent_prepare_project(
        input_path: str,
        task_id: str,
        session_id: str,
        execution_mode: str = "external_agent",
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            result = _prepare_web_task_ledger_if_needed(task_id, session_id)
            if result is None:
                result = get_external_agent_batch_service().prepare_project(
                    input_path,
                    task_id,
                    session_id,
                    execution_mode,
                )
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Read the compact status and batch identifiers for an external-Agent task.",
        "Use this recovery tool when the client lost the prepare or claim response. Full source items are returned only by agent_claim_batch or agent_claim_batches.",
    )
    def agent_project_status(task_id: str, session_id: str) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            result = _prepare_web_task_ledger_if_needed(task_id, session_id)
            if result is None:
                result = get_external_agent_batch_service().get_project(task_id, session_id)
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Prepare external-Agent batches from a controlled AiNiee cache manifest.",
        "Use this only when a real AinieeCacheData.json exists; returned items contain opaque cache locators and cache revision.",
    )
    def agent_prepare_cache_project(
        cache_path: str,
        task_id: str,
        session_id: str,
        execution_mode: str = "external_agent",
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            result = _prepare_web_task_ledger_if_needed(task_id, session_id)
            if result is None:
                result = get_external_agent_batch_service().prepare_cache_project(
                    cache_path,
                    task_id,
                    session_id,
                    execution_mode,
                )
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except (ExternalAgentBatchError, ValueError) as exc:
            code = getattr(exc, "code", "CACHE_MANIFEST_INVALID")
            raise ValueError(f"{code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Export a completed external-Agent task from its committed cache.",
        (
            "Use this when all batches are committed but automatic export did not run, "
            "for example after a WebServer restart or task status reset. It never calls "
            "an API or translates text; it only loads the committed cache and writes the "
            "format-aware final output through AiNiee's FileOutputer."
        ),
    )
    def agent_export_task(
        task_id: str,
        session_id: str,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            result = _export_external_agent_task(
                task_id,
                session_id,
                input_path=input_path,
                output_path=output_path,
            )
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except (ExternalAgentBatchError, ExternalAgentBatchWriterError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "EXPORT_FAILED")
            raise ValueError(f"{code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Claim one external-Agent translation batch.",
        "A session may hold multiple claims; pass batch_id to select a pending batch out of order.",
    )
    def agent_claim_batch(task_id: str, session_id: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            _prepare_web_task_ledger_if_needed(task_id, session_id)
            result = get_external_agent_batch_service().claim_batch(task_id, session_id, batch_id)
            manager = getattr(ws_module, "task_manager", None)
            if manager is not None and getattr(manager, "task_id", None) == task_id:
                manager.update_external_agent_status(
                    "running", task_id, "External Agent claimed a translation batch."
                )
            _bind_external_agent_context(
                session_id, task_id=task_id, batch_id=result.get("batch", {}).get("batch_id")
            )
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Claim multiple independent external-Agent translation batches.",
        "Omit max_batches to follow the TUI external_agent_max_batches setting (default 8, user-configurable above 8). A smaller request is allowed; raising the setting requires explicit user consent. Claims may be selected out of order.",
    )
    def agent_claim_batches(
        task_id: str,
        session_id: str,
        batch_ids: Optional[List[str]] = None,
        max_batches: Optional[int] = None,
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            _prepare_web_task_ledger_if_needed(task_id, session_id)
            result = get_external_agent_batch_service().claim_batches(
                task_id, session_id, batch_ids, max_batches=max_batches
            )
            manager = getattr(ws_module, "task_manager", None)
            if manager is not None and getattr(manager, "task_id", None) == task_id:
                manager.update_external_agent_status(
                    "running", task_id, "External Agent claimed parallel translation batches."
                )
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Submit one structured external-Agent translation batch.",
        "Validates source hash, revision, item indices and idempotency; it does not write AiNiee cache or output files.",
    )
    def agent_submit_translation_batch(
        task_id: str,
        session_id: str,
        batch_id: str,
        source_hash: str,
        revision: int,
        idempotency_key: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            batch_service = get_external_agent_batch_service()
            result = batch_service.submit_translation_batch(
                task_id, session_id, batch_id, source_hash, revision, idempotency_key, items
            )
            _bind_external_agent_context(session_id, task_id=task_id, batch_id=batch_id)
            ledger = batch_service.get_ledger(task_id, session_id)
            staged = get_external_agent_batch_result_service().validate_and_stage(
                ledger,
                result,
                idempotency_key=idempotency_key,
            )
            result["staging_status"] = "replayed" if staged.get("replayed") else "staged"
            result["staged_result_hash"] = staged.get("result_hash")
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @_mcp_tool(
        mcp,
        "Release a claimed external-Agent batch after a disconnect.",
        "Releases the claim without accepting translations.",
    )
    def agent_release_batch(task_id: str, session_id: str, batch_id: str) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            result = get_external_agent_batch_service().release_batch(task_id, session_id, batch_id)
            _bind_external_agent_context(session_id, task_id=task_id)
            return result
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Resume a durable external-Agent task after the previous session disconnected.",
        (
            "Register the new Agent session first. Pass the previous session_id; it must be expired or "
            "disconnected (or no longer visible after a service restart). The task claim is rebound, "
            "old writer leases are released, and the new session must acquire a writer lease again."
        ),
    )
    def agent_resume_task(
        task_id: str,
        session_id: str,
        previous_session_id: str,
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        if not isinstance(previous_session_id, str) or not previous_session_id.strip():
            raise ValueError("PREVIOUS_SESSION_REQUIRED: previous_session_id is required")
        if previous_session_id == session_id:
            raise ValueError("SESSION_ALREADY_ACTIVE: a resumed task requires a different session")
        previous = AGENT_SESSION_REGISTRY.status(previous_session_id)
        if isinstance(previous, dict) and previous.get("state") == "registered":
            raise ValueError("SESSION_STILL_ACTIVE: previous session must be disconnected or expired")
        try:
            batch_service = get_external_agent_batch_service()
            resumed = batch_service.resume_task(task_id, previous_session_id, session_id)
            released = get_external_agent_writer_lease_registry().release_task(
                task_id, previous_session_id
            )
            resumed["released_writer_leases"] = released
            resumed["writer_lease_required"] = True
            _bind_external_agent_context(session_id, task_id=task_id)
            return resumed
        except ExternalAgentBatchError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc

    @_mcp_tool(
        mcp,
        "Acquire a short-lived writer lease for a cache-backed Agent task.",
        "A task has at most one writer lease; the lease is separate from the MCP and Agent session IDs.",
    )
    def agent_acquire_writer_lease(task_id: str, session_id: str) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        try:
            return get_external_agent_writer_lease_registry().acquire(task_id, session_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @_mcp_tool(
        mcp,
        "Commit one staged cache-backed Agent batch through the deterministic writer.",
        "Requires a valid writer lease and staged items containing opaque cache locators and cache revision.",
    )
    def agent_commit_cache_batch(
        task_id: str,
        session_id: str,
        writer_lease_id: str,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        _require_external_agent_mode(session_id, task_id)
        if not isinstance(batch_id, str) or not batch_id.strip():
            raise ValueError("BATCH_ID_REQUIRED: batch_id is required for commit")
        leases = get_external_agent_writer_lease_registry()
        if not leases.validate(writer_lease_id, task_id, session_id):
            raise ValueError("WRITER_LEASE_UNAUTHORIZED: writer lease is invalid or expired")
        try:
            batch_service = get_external_agent_batch_service()
            ledger = batch_service.get_ledger(task_id, session_id)
            batch = next(
                (item for item in ledger.get("batches", []) if item.get("batch_id") == batch_id),
                None,
            )
            if batch is None:
                raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
            if batch.get("status") != "submitted":
                raise ExternalAgentBatchError("batch is not submitted", "BATCH_NOT_SUBMITTED")
            cache_path = batch_service.cache_path_for_writer(task_id, session_id)
            staged_result = get_external_agent_batch_result_service().read_staged(task_id)
            writer = ExternalAgentBatchWriter(
                PROJECT_ROOT,
                writer_lease_validator=lambda record, lease: leases.validate(lease, task_id, session_id),
            )
            result = writer.apply_staged_result(
                cache_path,
                staged_result,
                writer_lease_id=writer_lease_id,
                batch_id=batch_id,
            )
            ledger_result = batch_service.mark_batch_committed(
                task_id, session_id, batch_id, writer_lease_id, result
            )
            leases.release(writer_lease_id, task_id, session_id)
            _bind_external_agent_context(session_id, task_id=task_id, batch_id=batch_id)
            result["ledger"] = ledger_result
            if ledger_result.get("task", {}).get("status") == "completed":
                try:
                    exported = _finalize_external_agent_output(
                        ws_module,
                        task_id,
                        cache_path,
                    )
                    if exported:
                        result["export"] = exported
                except Exception as exc:
                    manager = getattr(ws_module, "task_manager", None)
                    if manager is not None:
                        manager.update_external_agent_status(
                            "failed",
                            task_id,
                            f"Cache committed but final export failed: {exc}",
                        )
                    result["export"] = {
                        "status": "failed",
                        "error": str(exc),
                        "cache_path": cache_path,
                    }
            return result
        except ExternalAgentBatchWriterError as exc:
            raise ValueError(f"{exc.code}: {exc}") from exc
        except ValueError as exc:
            code = getattr(exc, "code", None)
            raise ValueError(f"{code}: {exc}" if code else str(exc)) from exc

    # Keep the remaining Web/API tools below this point.
    @_mcp_tool(
        mcp,
        "List public WebServer API routes exposed through MCP. Pass category for a compact group.",
        (
            "Prefer get_mcp_tool_categories() and "
            "get_mcp_tool_catalog(category='<needed-category>') before calling API routes, "
            "so you do not guess endpoint paths."
        ),
    )
    def list_web_api_routes(category: str = "all") -> List[Dict[str, str]]:
        filtered_routes = _filter_routes_by_category(routes, category)
        return _build_route_index(
            filtered_routes,
            route_tools_exposed=register_route_tools,
        )

    @_mcp_tool(
        mcp,
        "Call one public /api/* route through MCP.",
        (
            "Use get_mcp_tool_categories and get_mcp_tool_catalog(category=...) to choose "
            "the route. Do not guess endpoint paths or mix this MCP proxy with direct Web UI HTTP calls. "
            "Internal routes are blocked. Changing external_agent_max_batches via /api/config "
            "requires explicit user consent and confirm_agent_batch_change=true."
        ),
    )
    def call_web_api(
        method: str,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        confirm_advanced_change: bool = False,
        confirm_agent_batch_change: bool = False,
    ) -> Any:
        normalized_path = _normalize_public_api_path(path)
        _ensure_advanced_change_confirmed(normalized_path, body, confirm_advanced_change)
        if normalized_path == "/api/config":
            ensure_agent_batch_change_confirmed(body, confirm_agent_batch_change)
        rendered_path = _render_path_template(normalized_path, path_params)
        return api.request(method.upper(), rendered_path, params=query, payload=body)

    @_mcp_tool(
        mcp,
        "Upload a local file through the WebServer multipart endpoint.",
    )
    def upload_file(file_path: str, policy: str = "default") -> Dict[str, Any]:
        import requests

        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"File not found: {source}")

        # 这个接口在 WebServer 里是 multipart/form-data，不能走统一 JSON 代理。
        with source.open("rb") as handle:
            response = requests.post(
                f"{api.base_url}/api/files/upload",
                params={"policy": policy},
                files={"file": (source.name, handle)},
                headers={
                    MCP_CALLER_HEADER: MCP_CALLER_VALUE,
                    MCP_AUTH_HEADER: api.mcp_auth_token,
                },
                timeout=api.timeout,
            )

        try:
            data = response.json()
        except Exception:
            data = response.text

        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} /api/files/upload: {data}")

        return sanitize_data_for_mcp(data, path="/api/files/upload")

    if register_route_tools:
        _register_route_proxy_tools(mcp, api, routes)

    return mcp


def _invoke_fastmcp_run(app: Any, transport: str, host: str, port: int, path: str) -> Any:
    os.environ.setdefault("FASTMCP_HOST", host)
    os.environ.setdefault("FASTMCP_PORT", str(port))
    os.environ.setdefault("FASTMCP_PATH", path)

    candidate_kwargs = [
        {"transport": transport, "host": host, "port": port, "mount_path": path, "path": path},
        {"transport": transport, "mount_path": path},
        {"transport": transport, "host": host, "port": port},
        {"transport": transport},
        {},
    ]

    signature = inspect.signature(app.run)
    last_error: Optional[Exception] = None

    for kwargs in candidate_kwargs:
        filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
        try:
            return app.run(**filtered)
        except TypeError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error

    return app.run()


def run_mcp_server(
    *,
    host_cli: Any = None,
    transport: str = "stdio",
    host: str = DEFAULT_MCP_HOST,
    port: int = DEFAULT_MCP_PORT,
    path: str = DEFAULT_MCP_PATH,
    backend_host: str = DEFAULT_BACKEND_HOST,
    backend_port: int = DEFAULT_BACKEND_PORT,
    register_route_tools: bool = DEFAULT_REGISTER_ROUTE_TOOLS,
    allow_remote_access: bool | None = None,
) -> Any:
    status = inspect_mcp_runtime(PROJECT_ROOT)
    if not status.get("available"):
        primary_install = status.get("primary_install_command") or "uv add mcp"
        raise RuntimeError(
            _tf_from_host(
                host_cli,
                "msg_mcp_runtime_not_ready_install",
                "MCP runtime is not ready. Suggested install: {command}",
                command=primary_install,
            )
        )

    transport = _normalize_transport(transport)
    if allow_remote_access is None:
        allow_remote_access = remote_access_enabled(PROJECT_MCP_DEFAULTS)
    if transport != "stdio":
        ensure_bind_allowed(host, allow_remote_access, "MCP")
    reusable_url = _try_get_reusable_mcp_service_url(transport, host, port, path)
    if reusable_url is not None:
        if is_reusable_mcp_service_running(host, port, path):
            import anyio

            _write_startup_notice(f"AiNiee MCP reusing running service: {reusable_url}")
            return anyio.run(_run_stdio_proxy_to_existing_mcp, reusable_url)

    mcp_auth_token = DEFAULT_MCP_AUTH_TOKEN or secrets.token_urlsafe(32)
    backend = EmbeddedWebServerController(
        host=backend_host,
        port=backend_port,
        host_cli=host_cli,
        log_level="critical" if transport == "stdio" else "info",
        mcp_auth_token=mcp_auth_token,
        allow_remote_access=allow_remote_access,
    )
    # MCP 复用现有 WebServer 作为后端宿主，避免再维护一套平行业务层。
    backend.start()
    atexit.register(backend.stop)

    api = AiNieeAPIClient(backend.base_url, mcp_auth_token=mcp_auth_token)
    mcp_app = _build_mcp_app(
        api,
        backend.ws_module,
        host,
        port,
        path,
        host_cli=host_cli,
        register_route_tools=register_route_tools,
    )

    try:
        return _invoke_fastmcp_run(mcp_app, transport, host, port, path)
    finally:
        backend.stop()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AiNiee MCP server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http", "streamable_http", "http", "sse"],
        help="MCP transport mode.",
    )
    parser.add_argument("--host", default=DEFAULT_MCP_HOST, help="MCP host address.")
    parser.add_argument("--port", type=int, default=DEFAULT_MCP_PORT, help="MCP port.")
    parser.add_argument("--path", default=DEFAULT_MCP_PATH, help="HTTP MCP path.")
    parser.add_argument(
        "--backend-host",
        default=DEFAULT_BACKEND_HOST,
        help="Embedded AiNiee WebServer host.",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=DEFAULT_BACKEND_PORT,
        help="Embedded AiNiee WebServer port.",
    )
    parser.add_argument(
        "--register-route-tools",
        action="store_true",
        default=DEFAULT_REGISTER_ROUTE_TOOLS,
        help=(
            "Compatibility mode: register one named api_* MCP tool per public WebServer route. "
            "Disabled by default to keep MCP tool discovery small."
        ),
    )
    return parser


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    run_mcp_server(
        transport=args.transport,
        host=args.host,
        port=args.port,
        path=args.path,
        backend_host=args.backend_host,
        backend_port=args.backend_port,
        register_route_tools=args.register_route_tools,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
