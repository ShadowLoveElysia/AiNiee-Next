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
from Tools.MCPServer.docs import (
    build_security_policy,
    build_tool_catalog,
    build_validation_checklist,
    load_mcp_manual,
)
from Tools.MCPServer.security import (
    MCP_AUTH_HEADER,
    MCP_CALLER_HEADER,
    MCP_CALLER_VALUE,
    sanitize_data_for_mcp,
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
    str(PROJECT_MCP_DEFAULTS.get("mcp_server_host", "0.0.0.0") or "0.0.0.0"),
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
    ):
        self.host = host
        self.port = port
        self.host_cli = host_cli
        self.startup_timeout = startup_timeout
        self.log_level = log_level
        self.mcp_auth_token = mcp_auth_token
        self.started_by_self = False
        self.thread = None
        self.ws_module = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self.mcp_auth_token:
            os.environ["AINIEE_MCP_AUTH_TOKEN"] = self.mcp_auth_token

        if _is_port_open(self.host, self.port):
            return

        import Tools.WebServer.web_server as ws_module

        self.ws_module = ws_module
        if self.host_cli is not None:
            try:
                self.host_cli.web_runtime_bridge._configure_web_handlers(ws_module)
            except Exception:
                pass

        self.thread = ws_module.run_server(
            host=self.host,
            port=self.port,
            monitor_mode=False,
            log_level=self.log_level,
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


async def _pipe_session_messages(source, sink, direction: str) -> None:
    """Forward MCP SessionMessage objects between stdio and streamable-http transports."""
    async for item in source:
        if isinstance(item, Exception):
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
            async def bridge_with_cancel(source, sink, direction: str, cancel_scope) -> None:
                try:
                    await _pipe_session_messages(source, sink, direction)
                finally:
                    cancel_scope.cancel()

            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    bridge_with_cancel,
                    local_read,
                    remote_write,
                    "stdio -> http",
                    tg.cancel_scope,
                )
                tg.start_soon(
                    bridge_with_cancel,
                    remote_read,
                    local_write,
                    "http -> stdio",
                    tg.cancel_scope,
                )


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
    return path.startswith("/api/") and not path.startswith("/api/internal/")


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


def _normalize_public_api_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if not _is_public_api_route(normalized):
        raise ValueError(
            "Only public /api/* routes are available through MCP. "
            "Internal routes and direct WebUI bypass paths are not allowed."
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
        route_category = path.strip("/").split("/")[1] if "/" in path.strip("/") else "misc"

        def make_route_tool(route_method: str, route_path: str, route_tool_name: str):
            def route_tool(
                path_params: Optional[Dict[str, Any]] = None,
                query: Optional[Dict[str, Any]] = None,
                body: Optional[Any] = None,
                confirm_advanced_change: bool = False,
            ) -> Any:
                """
                Proxy one WebServer API route through MCP.

                path_params fills placeholders in the original FastAPI path.
                query maps to URL query params.
                body maps to the JSON request body.
                confirm_advanced_change must be true before changing MCP advanced settings.
                """
                _ensure_advanced_change_confirmed(route_path, body, confirm_advanced_change)
                rendered_path = _render_path_template(route_path, path_params)
                return api.request(route_method, rendered_path, params=query, payload=body)

            route_tool.__name__ = route_tool_name
            route_tool.__doc__ = (
                f"Proxy WebServer route {_method_display(route_method)} {route_path}. "
                f"Category: {route_category}. "
                "Use path_params for templated segments, query for URL params, body for JSON payload. "
                "Call get_mcp_tool_catalog for structured examples. "
                "Do not bypass MCP by making direct WebUI or localhost HTTP requests."
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


def _build_mcp_app(
    api: AiNieeAPIClient,
    ws_module,
    host: str,
    port: int,
    path: str,
    host_cli: Any = None,
):
    try:
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
        host=host,
        port=port,
        streamable_http_path=path,
    )

    routes = _extract_api_routes(ws_module)

    @mcp.tool()
    def get_mcp_usage_manual(section: str = "all") -> str:
        """
        Read the built-in MCP usage manual.

        Call this first when the MCP client cannot inspect repository files.
        It also states that the model must not bypass MCP by sending direct WebUI HTTP requests.
        """
        return load_mcp_manual(section)

    @mcp.tool()
    def get_mcp_security_policy() -> Dict[str, Any]:
        """
        Read the MCP security policy.

        This explicitly forbids bypassing MCP with direct WebUI / localhost / LAN HTTP requests
        and explains how secret redaction behaves.
        """
        return build_security_policy()

    @mcp.tool()
    def get_mcp_tool_catalog(category: str = "all", include_examples: bool = True) -> Dict[str, Any]:
        """
        Read the structured MCP tool catalog with route groups, call patterns, and examples.

        Recommended before using many tools in clients that do not support source inspection.
        """
        return build_tool_catalog(routes, category=category, include_examples=include_examples)

    @mcp.tool()
    def get_mcp_validation_checklist() -> Dict[str, Any]:
        """
        Read the four MCP security validation scenarios.

        Use this to validate config/queue redaction and placeholder writeback protection.
        """
        return build_validation_checklist()

    @mcp.tool()
    def list_web_api_routes() -> List[Dict[str, str]]:
        """List all public WebServer API routes exposed through MCP. Use get_mcp_tool_catalog for detailed usage."""
        return routes

    @mcp.tool()
    def call_web_api(
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        confirm_advanced_change: bool = False,
    ) -> Any:
        """
        Raw escape hatch for a public /api/* route when no named MCP tool is enough.

        Never use external direct HTTP requests to bypass MCP protections. Internal routes are blocked.
        """
        normalized_path = _normalize_public_api_path(path)
        _ensure_advanced_change_confirmed(normalized_path, body, confirm_advanced_change)
        return api.request(method.upper(), normalized_path, params=query, payload=body)

    @mcp.tool()
    def upload_file(file_path: str, policy: str = "default") -> Dict[str, Any]:
        """Upload a local file through the WebServer multipart endpoint."""
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
    )
    # MCP 复用现有 WebServer 作为后端宿主，避免再维护一套平行业务层。
    backend.start()
    atexit.register(backend.stop)

    api = AiNieeAPIClient(backend.base_url, mcp_auth_token=mcp_auth_token)
    mcp_app = _build_mcp_app(api, backend.ws_module, host, port, path, host_cli=host_cli)

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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
