"""Own the HTTP listener independently of browser assets and MCP transport."""
from __future__ import annotations

import argparse
import logging
import threading
import uuid
import time
from pathlib import Path

from ModuleFolders.Infrastructure.RemoteAccessPolicy import ensure_bind_allowed

_server = None
_thread = None
_options = None
_shutdown_pending = False
_lock = threading.RLock()
_web_enabled = False
_web_dist = None


def web_status():
    dist = _web_dist or Path(__file__).resolve().parents[1] / "WebServer" / "dist"
    return {"enabled": _web_enabled, "available": (dist / "index.html").is_file(),
            "running": _server is not None and bool(_server.is_running)}


def configure_web(enabled: bool):
    global _web_enabled, _options
    with _lock:
        if _server is None or not _server.is_running or _shutdown_pending:
            raise RuntimeError("API owner is not available")
        if enabled and not web_status()["available"]:
            raise FileNotFoundError("Web assets not found")
        _web_enabled = enabled
        if _options is not None:
            _options = (*_options[:2], enabled, _options[3])
        return web_status()


def get_application():
    from Tools.APIServer import application
    return application


def get_server():
    return _server


def get_active_owner() -> dict | None:
    """Return private connection details to adapters in this process only."""
    with _lock:
        if _server is None or not _server.is_running:
            return None
        return {
            "host": _server.config.host,
            "port": _server.config.port,
            "mcp_auth_token": get_application().MCP_AUTH_TOKEN,
        }


def bind_mcp_auth_token_if_unset(token: str) -> str:
    """Bind an unconfigured local owner without invalidating existing clients."""
    if not isinstance(token, str) or not token:
        raise ValueError("A nonempty MCP bridge token is required.")
    with _lock:
        if _server is None or not _server.is_running:
            raise RuntimeError("The local API owner is no longer running.")
        application = get_application()
        if not application.MCP_AUTH_TOKEN:
            application.MCP_AUTH_TOKEN = token
        return application.MCP_AUTH_TOKEN


def set_mcp_auth_token(token: str) -> None:
    with _lock:
        if _server is not None:
            raise RuntimeError("Configure bridge authentication before starting the API owner.")
        get_application().MCP_AUTH_TOKEN = token


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    monitor_mode: bool = False,
    log_level: str = "info",
    allow_remote_access: bool = False,
    *,
    serve_web: bool = False,
    web_dist: str | None = None,
):
    import uvicorn
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from ModuleFolders.Infrastructure.ApiSecurity import INTERNAL_AUTH_ENV

    ensure_bind_allowed(host, allow_remote_access, "API server")
    global _server, _thread, _options, _web_enabled, _web_dist
    with _lock:
        if _shutdown_pending:
            raise RuntimeError("API owner shutdown is pending; retry stopping it before restarting.")
        if _thread is not None and _thread.is_alive():
            if (_server.config.host, _server.config.port) != (host, port):
                raise RuntimeError("This process already owns an API listener on another address.")
            requested = (monitor_mode, allow_remote_access, serve_web, web_dist)
            if requested != _options:
                raise RuntimeError("The API listener is already running with different capabilities; stop its owner before changing them.")
            return _thread
        application = get_application()
        application.RUNTIME_ID = str(uuid.uuid4())
        application.SYSTEM_MODE = "monitor" if monitor_mode else "full"
        application.REMOTE_ACCESS_ENABLED = allow_remote_access is True
        callback_host = "[::1]" if ":" in host else "127.0.0.1"
        internal_url = f"http://{callback_host}:{port}"
        application.task_manager.configure(
            internal_auth_token=application.INTERNAL_API_TOKEN,
            internal_api_url=internal_url,
        )
        application.task_manager.api_url = internal_url
        # Legacy in-process CLI workers still discover the callback through these variables.
        import os
        os.environ["AINIEE_INTERNAL_API_URL"] = internal_url
        os.environ[INTERNAL_AUTH_ENV] = application.INTERNAL_API_TOKEN

        _web_dist = Path(web_dist) if web_dist else Path(application.PROJECT_ROOT) / "Tools/WebServer/dist"
        _web_enabled = serve_web
        static = StaticFiles(directory=str(_web_dist), html=True, check_dir=False)

        async def api_app(scope, receive, send):
            path = scope.get("path", "")
            if scope["type"] == "http" and _web_enabled and not (path == "/api" or path.startswith("/api/")):
                if path in {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}:
                    return await application.app(scope, receive, send)
                async def static_send(message):
                    if message["type"] == "http.response.start":
                        message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-cache")]
                    await send(message)
                if (_web_dist / "index.html").is_file():
                    from starlette.exceptions import HTTPException as StaticHTTPException
                    from starlette.responses import PlainTextResponse
                    try:
                        return await static(scope, receive, static_send)
                    except StaticHTTPException as exc:
                        return await PlainTextResponse(exc.detail, status_code=exc.status_code)(scope, receive, static_send)
            return await application.app(scope, receive, send)

        class OwnedServer(uvicorn.Server):
            def install_signal_handlers(self):
                pass

            @property
            def is_running(self):
                return self.started and not self.should_exit

        owned = OwnedServer(uvicorn.Config(
            api_app, host=host, port=port, log_level=log_level,
            access_log=log_level.lower() != "critical",
        ))
        _server = owned
        _options = (monitor_mode, allow_remote_access, serve_web, web_dist)
        _thread = threading.Thread(target=owned.run, name="ainiee-api", daemon=True)
        application.task_manager.set_task_admission(True)
        _thread.start()
        return _thread


def stop_server(*, cancel_tasks: bool = True) -> bool:
    """True when closed; False retains ownership for a subsequent shutdown attempt."""
    global _server, _thread, _options, _shutdown_pending
    with _lock:
        if _server is None:
            return True
        _shutdown_pending = True
        manager = get_application().task_manager
        idle = manager.set_task_admission(False)
        try:
            from ModuleFolders.Service.TaskRuntime.activities import auxiliary_active, stop_auxiliaries
            from ModuleFolders.Service.TaskRuntime.jobs import get_job_manager
            if not cancel_tasks and (not idle or auxiliary_active() or get_job_manager().any_running()):
                return False
            auxiliaries_stopped = stop_auxiliaries()
            ready = manager.stop_task() if cancel_tasks else idle
        except Exception:
            logging.getLogger(__name__).error("Task shutdown failed; retaining API ownership for retry.")
            return False
        if not ready or not auxiliaries_stopped:
            return False
        _server.should_exit = True
        thread = _thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=5)
    with _lock:
        if _thread is not thread:
            return True
        if thread is not None and thread.is_alive():
            return False
        _server = None
        _thread = None
        _options = None
        _shutdown_pending = False
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AiNiee API server (Web UI assets are optional)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allow-remote-access", action="store_true")
    parser.add_argument("--serve-web", action="store_true")
    args = parser.parse_args()
    thread = run_server(
        args.host, args.port, allow_remote_access=args.allow_remote_access,
        serve_web=args.serve_web,
    )
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if not stop_server():
            logging.getLogger(__name__).warning("API shutdown incomplete; retaining the owner and retrying.")
            while True:
                time.sleep(0.5)
                if stop_server():
                    break


if __name__ == "__main__":
    main()
