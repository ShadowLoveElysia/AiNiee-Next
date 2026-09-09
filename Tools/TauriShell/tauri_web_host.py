#!/usr/bin/env python3
"""Host process for Tauri PoC.

Starts AiNiee FastAPI web server and keeps it alive until terminated.
"""

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start AiNiee WebServer for Tauri shell.")
    parser.add_argument("--host", default="127.0.0.1", help="WebServer host address.")
    parser.add_argument("--port", type=int, default=18000, help="WebServer port.")
    parser.add_argument(
        "--allow-remote-access",
        action="store_true",
        help="Allow non-loopback WebServer binding for this process only.",
    )
    parser.add_argument(
        "--monitor-mode",
        action="store_true",
        help="Start backend in monitor mode.",
    )
    parser.add_argument(
        "--skills",
        action="store_true",
        default=_env_flag("AINIEE_GUI_SKILLS"),
        help="Start the optional Skills HTTP server alongside WebServer.",
    )
    parser.add_argument(
        "--skills-host", "--host-skills", dest="skills_host",
        default=os.environ.get("AINIEE_SKILLS_HOST", "127.0.0.1"),
        help="Skills HTTP bind host (defaults to loopback).",
    )
    parser.add_argument(
        "--skills-port", dest="skills_port", type=int,
        default=_env_int("AINIEE_SKILLS_PORT", 8766),
        help="Skills HTTP port.",
    )
    parser.add_argument(
        "--skills-auth-token", dest="skills_auth_token",
        default=os.environ.get("AINIEE_SKILLS_AUTH_TOKEN"),
        help="Skills HTTP auth token; when omitted the server generates one.",
    )
    parser.add_argument(
        "--skills-allow-remote-access", action="store_true",
        default=_env_flag("AINIEE_SKILLS_ALLOW_REMOTE_ACCESS"),
        help="Allow a non-loopback Skills bind; authentication remains required.",
    )
    parser.add_argument(
        "--skills-no-auth", action="store_true",
        default=_env_flag("AINIEE_SKILLS_NO_AUTH"),
        help="Disable Skills auth for a trusted loopback-only run.",
    )
    parser.add_argument(
        "--skills-allow-origin", dest="skills_allow_origin",
        default=os.environ.get("AINIEE_SKILLS_ALLOW_ORIGIN", ""),
        help="Optional Skills CORS origin.",
    )
    return parser


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default
    return value


def main() -> int:
    args = build_parser().parse_args()
    if args.allow_remote_access and args.host == "127.0.0.1":
        args.host = "0.0.0.0"

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    dist_index = project_root / "Tools" / "WebServer" / "dist" / "index.html"
    if not dist_index.exists():
        print(
            "WebServer dist assets were not found. Build or install Tools/WebServer/dist first.",
            file=sys.stderr,
        )
        return 2

    try:
        from Tools.WebServer.web_server import run_server, stop_server
        from ModuleFolders.UserInterface.AppI18N import initialize_i18n
    except Exception as exc:
        print(f"Failed to import WebServer runtime: {exc}", file=sys.stderr)
        return 3

    stop_event = threading.Event()

    _, i18n = initialize_i18n(str(project_root))
    if not args.allow_remote_access:
        from rich.console import Console

        Console().print(f"[yellow]{i18n.get('warning_remote_access_disabled')}[/yellow]")

    def _request_stop(_sig, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    server_thread = run_server(
        host=args.host,
        port=args.port,
        monitor_mode=args.monitor_mode,
        allow_remote_access=args.allow_remote_access,
    )
    if server_thread is None:
        print("WebServer failed to start.", file=sys.stderr)
        return 4

    skills_server = None
    if args.skills:
        try:
            from Tools.Skills.server import run_server_detached

            skills_server = run_server_detached(
                host=args.skills_host,
                port=args.skills_port,
                auth_token=args.skills_auth_token,
                require_auth=not args.skills_no_auth,
                allow_origin=args.skills_allow_origin,
                allow_remote_access=args.skills_allow_remote_access,
            )
            # A generated token is otherwise only printed by the blocking
            # server entry point; expose it to the Tauri host without ever
            # writing it to task state or argv.
            configured_token = args.skills_auth_token or os.environ.get("AINIEE_SKILLS_AUTH_TOKEN")
            if not configured_token:
                configured_token = getattr(
                    getattr(skills_server, "RequestHandlerClass", None),
                    "auth_token",
                    "",
                )
            if configured_token:
                print(f"AiNiee Skills auth token: {configured_token}", file=sys.stderr)
        except Exception as exc:
            print(f"Skills server failed to start: {exc}", file=sys.stderr)
            try:
                stop_server()
            except Exception:
                pass
            return 5

    print(f"AiNiee WebServer started at http://{args.host}:{args.port}")
    if skills_server is not None:
        actual_host, actual_port = skills_server.server_address[:2]
        print(f"AiNiee Skills started at http://{actual_host}:{actual_port}")

    try:
        while not stop_event.is_set() and server_thread.is_alive():
            time.sleep(0.2)
    finally:
        if skills_server is not None:
            try:
                skills_server.shutdown()
            except Exception:
                pass
            try:
                skills_server.server_close()
            except Exception:
                pass
        try:
            stop_server()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
