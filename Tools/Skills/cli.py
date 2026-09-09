"""
Skills CLI Runner

Allows executing skills directly from the command line without starting the HTTP server.
This is the foundation for the "混合模式" — skills can be invoked via CLI, HTTP, or direct API.

Usage:
    python Tools/Skills/cli.py list
    python Tools/Skills/cli.py describe system
    python Tools/Skills/cli.py run system '{"action": "ping"}'
    python Tools/Skills/cli.py run config '{"action": "get", "key": "model"}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_cli(args: List[str]) -> int:
    """Entry point for the 'skills' subcommand."""
    parser = argparse.ArgumentParser(
        prog="python Tools/Skills/cli.py",
        description="Execute or manage AiNiee skills.",
    )
    sub = parser.add_subparsers(dest="command")

    # skills list
    list_parser = sub.add_parser("list", help="List all available skills.")

    # skills check
    sub.add_parser(
        "check",
        help="Check Skills files and production dependencies without opening a socket.",
    )

    # skills describe <name>
    describe_parser = sub.add_parser("describe", help="Describe a skill and its parameters.")
    describe_parser.add_argument("name", help="Skill name (e.g., system, config, translate)")

    # skills run <name> [args]
    run_parser = sub.add_parser("run", help="Execute a skill.")
    run_parser.add_argument("name", help="Skill name to execute.")
    run_parser.add_argument("args_json", nargs="?", default="{}", help="JSON string of arguments.")

    # skills server
    server_parser = sub.add_parser("server", help="Start the Skills HTTP server.")
    server_parser.add_argument(
        "--host", "--skills-host", dest="host", default="127.0.0.1",
        help="Host address (also accepted as --skills-host).",
    )
    server_parser.add_argument(
        "--port", "--skills-port", dest="port", type=int, default=8766,
        help="Port number (also accepted as --skills-port).",
    )
    server_parser.add_argument(
        "--auth-token", "--skills-auth-token", dest="auth_token", default=None,
        help="HTTP auth token (also accepted as --skills-auth-token).",
    )
    server_parser.add_argument(
        "--skills",
        action="store_true",
        help="Compatibility flag for invoking this server like the main CLI.",
    )
    server_parser.add_argument(
        "--no-auth", "--skills-no-auth", dest="no_auth",
        action="store_true",
        help="Disable HTTP auth. Only use on trusted local machines.",
    )
    server_parser.add_argument(
        "--allow-origin", "--skills-allow-origin", dest="allow_origin",
        default="",
        help="Optional CORS Access-Control-Allow-Origin value.",
    )
    server_parser.add_argument(
        "--allow-remote-access", "--skills-allow-remote-access",
        dest="allow_remote_access",
        action="store_true",
        help="Explicitly allow non-loopback binding; authentication remains required.",
    )

    parsed = parser.parse_args(args)

    if parsed.command == "list":
        return _cmd_list()
    elif parsed.command == "check":
        return _cmd_check()
    elif parsed.command == "describe":
        return _cmd_describe(parsed.name)
    elif parsed.command == "run":
        return _cmd_run(parsed.name, parsed.args_json)
    elif parsed.command == "server":
        return _cmd_server(
            parsed.host,
            parsed.port,
            auth_token=parsed.auth_token,
            require_auth=not parsed.no_auth,
            allow_origin=parsed.allow_origin,
            allow_remote_access=parsed.allow_remote_access,
        )
    else:
        parser.print_help()
        return 1


def _get_registry():
    """Lazy-import the registry to avoid circular imports at module level."""
    from Tools.Skills.skills import build_registry  # noqa: PLC0415
    return build_registry()


def _cmd_list() -> int:
    try:
        registry = _get_registry()
        skills = registry.list_skills()
        print(f"Available skills ({len(skills)}):")
        for s in skills:
            print(f"  {s['name']:25s}  {s['description']}")
        return 0
    except Exception as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1


def _cmd_check() -> int:
    """Run the dependency/readiness probe without importing the HTTP listener."""
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


def _cmd_describe(name: str) -> int:
    try:
        registry = _get_registry()
        meta = registry.get_skill_meta(name)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_run(name: str, args_json: str) -> int:
    try:
        skill_args: Any = json.loads(args_json)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON arguments: {e}", file=sys.stderr)
        return 1

    try:
        registry = _get_registry()
        result = registry.execute(name, skill_args)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1
    except Exception as exc:
        from Tools.Skills.skill_base import SkillError, SkillResult

        if isinstance(exc, SkillError):
            print(
                json.dumps(
                    SkillResult.fail(str(exc), exc.code).to_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1


def _cmd_server(
    host: str,
    port: int,
    *,
    auth_token: str | None = None,
    require_auth: bool = True,
    allow_origin: str = "",
    allow_remote_access: bool = False,
) -> int:
    print(f"Starting Skills HTTP server on http://{host}:{port}")
    try:
        from Tools.Skills.server import run_server  # noqa: PLC0415

        run_server(
            host=host,
            port=port,
            auth_token=auth_token,
            require_auth=require_auth,
            allow_origin=allow_origin,
            allow_remote_access=allow_remote_access,
        )
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Skills server error: {exc}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
