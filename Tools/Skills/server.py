"""
AiNiee Skills HTTP Server

A lightweight REST server that exposes the Skills framework over HTTP.
No MCP, no FastAPI, no uvicorn — just the Python standard library.

Endpoints:
    GET  /skills              — List all skills with metadata
    GET  /skills/<name>       — Describe a specific skill
    POST /skills/<name>       — Execute a skill with arguments
    GET  /health              — Health check

Usage:
    python Tools/Skills/server.py [--port PORT] [--host HOST]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict
from urllib.parse import urlparse


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ModuleFolders.Infrastructure.RemoteAccessPolicy import (
    ensure_bind_allowed,
    is_loopback_bind_host,
)
from Tools.Skills.skill_base import (
    SkillError,
    normalize_skill_payload,
)


SKILLS_AUTH_HEADER = "X-AiNiee-Skills-Auth"
MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024


class SkillsHTTPServer(ThreadingHTTPServer):
    """Threaded server with safe restart and shutdown defaults."""

    allow_reuse_address = True
    daemon_threads = True


def _build_registry():
    """Load production Skills only when a server is actually started."""
    from Tools.Skills.skills import build_registry

    return build_registry()


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


class SkillsHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Skills server."""

    # Shared across all instances
    registry = None
    auth_token: str = ""
    require_auth: bool = True
    allow_origin: str = ""

    @classmethod
    def ensure_registry(cls):
        if cls.registry is None:
            cls.registry = _build_registry()
        return cls.registry

    def _registry(self):
        return type(self).ensure_registry()

    def log_message(self, format: str, *args: Any) -> None:
        """Log to stderr so stdout stays clean for potential JSONL consumers."""
        sys.stderr.write(f"[Skills] {args[0]} {args[1]} {args[2]}\n")

    def _send_cors_headers(self) -> None:
        if not self.allow_origin:
            return
        self.send_header("Access-Control-Allow-Origin", self.allow_origin)
        self.send_header("Vary", "Origin")

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, code: str = "") -> None:
        self._send_json({"error": message, "error_code": code}, status)

    def _read_body(self) -> Any:
        """Read one bounded JSON value and leave shape validation to the protocol layer."""
        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise ValueError("Content-Length must be a valid integer") from exc
        if content_length < 0:
            raise ValueError("Content-Length cannot be negative")
        if content_length > MAX_REQUEST_BODY_BYTES:
            raise ValueError(
                f"Request body exceeds the {MAX_REQUEST_BODY_BYTES} byte limit"
            )
        if content_length == 0:
            return {}

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Request body must be valid UTF-8 JSON") from exc
        return payload

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            f"Content-Type, {SKILLS_AUTH_HEADER}",
        )
        self.end_headers()

    def _is_authorized(self) -> bool:
        if not self.require_auth:
            return True
        token = str(self.auth_token or "")
        provided = self.headers.get(SKILLS_AUTH_HEADER, "")
        return bool(token) and secrets.compare_digest(str(provided), token)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            self._send_json({
                "status": "ok",
                "service": "ainiee-skills",
                "skills_count": self._registry().count,
            })
            return

        if path == "/skills":
            self._send_json({
                "skills": self._registry().list_skills(),
                "count": self._registry().count,
            })
            return

        if path.startswith("/skills/"):
            name = path[len("/skills/"):]
            try:
                meta = self._registry().get_skill_meta(name)
                self._send_json(meta)
            except SkillError as exc:
                status = 404 if exc.code == "UNKNOWN_SKILL" else 400
                self._send_error(status, str(exc), exc.code)
            except Exception as exc:
                self._send_error(500, str(exc), "SKILL_METADATA_ERROR")
            return

        if path == "/tasks" or path.startswith("/tasks/"):
            # Task metadata contains user paths and logs; status reads are
            # protected by the same token as task execution.
            if not self._is_authorized():
                self._send_error(401, "Missing or invalid Skills auth token.", "UNAUTHORIZED")
                return
            try:
                from Tools.Skills.task_runtime import get_task_manager

                manager = get_task_manager()
                if path == "/tasks":
                    records = manager.list()
                    self._send_json({"tasks": records, "count": len(records)})
                else:
                    task_id = path[len("/tasks/"):]
                    record = manager.get(task_id)
                    if record is None:
                        self._send_error(404, f"Unknown task_id: {task_id}", "TASK_NOT_FOUND")
                    else:
                        self._send_json(record)
            except Exception as exc:
                self._send_error(500, str(exc), "TASK_STATUS_ERROR")
            return

        self._send_error(404, f"Not found: {path}", "NOT_FOUND")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/skills/"):
            if not self._is_authorized():
                self._send_error(401, "Missing or invalid Skills auth token.", "UNAUTHORIZED")
                return
            name = path[len("/skills/"):]
            try:
                body = self._read_body()
                body = normalize_skill_payload(body)
                if "action" in body and not isinstance(body["action"], str):
                    self._send_error(400, "action must be a string.", "INVALID_ACTION")
                    return
                result = self._registry().execute(name, body)
                self._send_json(result.to_dict())
            except SkillError as exc:
                status = 404 if exc.code == "UNKNOWN_SKILL" else 400
                self._send_error(status, str(exc), exc.code)
            except ValueError as exc:
                self._send_error(400, str(exc), "INVALID_REQUEST")
            except Exception as e:
                self._send_error(500, str(e), "EXECUTION_ERROR")
            return

        if path.startswith("/tasks/"):
            if not self._is_authorized():
                self._send_error(401, "Missing or invalid Skills auth token.", "UNAUTHORIZED")
                return
            task_id = path[len("/tasks/"):]
            try:
                body = self._read_body()
                try:
                    body = normalize_skill_payload(body)
                except SkillError as exc:
                    self._send_error(400, str(exc), exc.code)
                    return
                action = body.get("action", "stop")
                if not isinstance(action, str):
                    self._send_error(400, "action must be a string.", "INVALID_ACTION")
                    return
                if action.strip().lower() != "stop":
                    self._send_error(400, "Only action=stop is supported on /tasks/{id}.", "INVALID_ACTION")
                    return
                from Tools.Skills.task_runtime import get_task_manager

                record = get_task_manager().cancel(task_id)
                if record is None:
                    self._send_error(404, f"Unknown task_id: {task_id}", "TASK_NOT_FOUND")
                else:
                    self._send_json(record)
            except ValueError as exc:
                self._send_error(400, str(exc), "INVALID_REQUEST")
            except Exception as exc:
                self._send_error(500, str(exc), "TASK_STOP_ERROR")
            return

        self._send_error(404, f"Not found: {path}", "NOT_FOUND")


def _configured_handler(
    *,
    auth_token: str,
    require_auth: bool,
    allow_origin: str,
) -> type[SkillsHTTPHandler]:
    """Create an isolated handler class for one listener's security settings."""
    handler_class = type(
        "ConfiguredSkillsHTTPHandler",
        (SkillsHTTPHandler,),
        {
            "auth_token": auth_token,
            "require_auth": require_auth,
            "allow_origin": allow_origin,
            "registry": SkillsHTTPHandler.ensure_registry(),
        },
    )
    return handler_class


def _run_runtime_check() -> int:
    """Print dependency/readiness JSON without constructing a listening socket."""
    try:
        from Tools.Skills.runtime import inspect_skills_runtime, runtime_check_exit_code

        status = inspect_skills_runtime()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return runtime_check_exit_code(status)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "available": False,
                    "component_ready": False,
                    "business_ready": False,
                    "probe_error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


def run_server(
    host: str = "127.0.0.1",
    port: int = 8766,
    *,
    auth_token: str | None = None,
    require_auth: bool = True,
    allow_origin: str = "",
    allow_remote_access: bool = False,
) -> None:
    """Start the Skills HTTP server."""
    ensure_bind_allowed(host, allow_remote_access, "Skills")
    if not is_loopback_bind_host(host) and not require_auth:
        raise ValueError("Remote Skills binding requires HTTP authentication.")
    if require_auth and not auth_token:
        auth_token = os.environ.get("AINIEE_SKILLS_AUTH_TOKEN") or secrets.token_urlsafe(24)
    auth_token = str(auth_token or "")
    allow_origin = str(allow_origin or "")
    handler_class = _configured_handler(
        auth_token=auth_token or "",
        require_auth=require_auth,
        allow_origin=allow_origin,
    )
    server = SkillsHTTPServer((host, port), handler_class)
    sys.stderr.write(
        f"[Skills] Server starting on http://{host}:{port}\n"
        f"[Skills] Endpoints:\n"
        f"[Skills]   GET  /health       — Health check\n"
        f"[Skills]   GET  /skills       — List all skills\n"
        f"[Skills]   GET  /skills/<name> — Describe a skill\n"
        f"[Skills]   POST /skills/<name> — Execute a skill\n"
    )
    if require_auth:
        sys.stderr.write(
            f"[Skills] POST auth header: {SKILLS_AUTH_HEADER}: {handler_class.auth_token}\n"
        )
    else:
        sys.stderr.write("[Skills] WARNING: HTTP auth is disabled.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("[Skills] Shutting down...\n")
    finally:
        server.server_close()


def run_server_detached(
    host: str = "127.0.0.1",
    port: int = 8766,
    *,
    auth_token: str | None = None,
    require_auth: bool = True,
    allow_origin: str = "",
    allow_remote_access: bool = False,
) -> SkillsHTTPServer:
    """Start server in a way that can be stopped programmatically."""
    ensure_bind_allowed(host, allow_remote_access, "Skills")
    if not is_loopback_bind_host(host) and not require_auth:
        raise ValueError("Remote Skills binding requires HTTP authentication.")
    if require_auth and not auth_token:
        auth_token = os.environ.get("AINIEE_SKILLS_AUTH_TOKEN") or secrets.token_urlsafe(24)
    auth_token = str(auth_token or "")
    allow_origin = str(allow_origin or "")
    handler_class = _configured_handler(
        auth_token=auth_token or "",
        require_auth=require_auth,
        allow_origin=allow_origin,
    )
    server = SkillsHTTPServer((host, port), handler_class)
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_host, actual_port = server.server_address
    sys.stderr.write(f"[Skills] Server started (detached) on http://{actual_host}:{actual_port}\n")
    return server


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AiNiee Skills HTTP Server")
    parser.add_argument(
        "--host", "--skills-host", dest="host", default="127.0.0.1",
        help="Host address (also accepted as --skills-host).",
    )
    parser.add_argument(
        "--port", "--skills-port", dest="port", type=int, default=8766,
        help="Port number (also accepted as --skills-port).",
    )
    parser.add_argument(
        "--auth-token", "--skills-auth-token", dest="auth_token", default=None,
        help="HTTP auth token (also accepted as --skills-auth-token).",
    )
    parser.add_argument(
        "--skills",
        action="store_true",
        help="Compatibility flag for invoking this server like the main CLI.",
    )
    parser.add_argument(
        "--no-auth", "--skills-no-auth", dest="no_auth",
        action="store_true",
        help="Disable HTTP auth. Only use on trusted local machines.",
    )
    parser.add_argument(
        "--allow-origin", "--skills-allow-origin", dest="allow_origin",
        default="",
        help="Optional CORS Access-Control-Allow-Origin value.",
    )
    parser.add_argument(
        "--allow-remote-access", "--skills-allow-remote-access",
        dest="allow_remote_access",
        action="store_true",
        help="Explicitly allow non-loopback binding; authentication remains required.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print Skills readiness/dependency JSON and exit without opening a socket.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.check:
        return _run_runtime_check()
    try:
        run_server(
            host=args.host,
            port=args.port,
            auth_token=args.auth_token,
            require_auth=not args.no_auth,
            allow_origin=args.allow_origin,
            allow_remote_access=args.allow_remote_access,
        )
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Skills server error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
