from __future__ import annotations

import argparse
import atexit
import inspect
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Tools.MCPServer.runtime import inspect_mcp_runtime
from Tools.MCPServer.docs import (
    build_security_policy,
    build_tool_catalog,
    build_validation_checklist,
    load_mcp_manual,
)
from Tools.MCPServer.security import (
    MCP_CALLER_HEADER,
    MCP_CALLER_VALUE,
    sanitize_data_for_mcp,
)


DEFAULT_MCP_HOST = os.environ.get("AINIEE_MCP_HOST", "0.0.0.0")
DEFAULT_MCP_PORT = int(os.environ.get("AINIEE_MCP_PORT", "8765"))
DEFAULT_MCP_PATH = os.environ.get("AINIEE_MCP_PATH", "/mcp")
DEFAULT_BACKEND_HOST = os.environ.get("AINIEE_MCP_BACKEND_HOST", "127.0.0.1")
DEFAULT_BACKEND_PORT = int(os.environ.get("AINIEE_MCP_BACKEND_PORT", "18000"))


class EmbeddedWebServerController:
    def __init__(
        self,
        host: str,
        port: int,
        host_cli: Any = None,
        startup_timeout: float = 8.0,
        log_level: str = "info",
    ):
        self.host = host
        self.port = port
        self.host_cli = host_cli
        self.startup_timeout = startup_timeout
        self.log_level = log_level
        self.started_by_self = False
        self.thread = None
        self.ws_module = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
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
            f"Embedded WebServer failed to start on {self.host}:{self.port}."
        )

    def stop(self) -> None:
        if not self.started_by_self or self.ws_module is None:
            return
        try:
            self.ws_module.stop_server()
        except Exception:
            pass


class AiNieeAPIClient:
    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
            headers={MCP_CALLER_HEADER: MCP_CALLER_VALUE},
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
):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Missing Python module 'mcp'. Install it with: uv add mcp") from exc

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
                headers={MCP_CALLER_HEADER: MCP_CALLER_VALUE},
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
            f"MCP runtime is not ready. Suggested install: {primary_install}"
        )

    transport = _normalize_transport(transport)
    backend = EmbeddedWebServerController(
        host=backend_host,
        port=backend_port,
        host_cli=host_cli,
        log_level="critical" if transport == "stdio" else "info",
    )
    # MCP 复用现有 WebServer 作为后端宿主，避免再维护一套平行业务层。
    backend.start()
    atexit.register(backend.stop)

    api = AiNieeAPIClient(backend.base_url)
    mcp_app = _build_mcp_app(api, backend.ws_module, host, port, path)

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
