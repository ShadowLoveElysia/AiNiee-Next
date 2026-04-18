from __future__ import annotations

import importlib.util
import os
import shlex
from typing import Callable, Dict, List, Optional


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MCP_SERVER_ROOT = os.path.join(PROJECT_ROOT, "Tools", "MCPServer")

REQUIRED_MODULE_SPECS = {
    "mcp": "mcp",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "requests": "requests",
}

REQUIRED_COMPONENT_FILES = (
    "__init__.py",
    "docs.py",
    "runtime.py",
    "security.py",
    "server.py",
)


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _quote_cmd_arg(value: str) -> str:
    """Quote a single argument for display in a Windows cmd.exe command."""
    return f'"{value}"'


def _quote_posix_arg(value: str) -> str:
    """Quote a single argument for display in a POSIX shell command."""
    return shlex.quote(value)


def _get_windows_project_environment(project_root: str) -> str:
    """Windows uses a separate venv to avoid mixed WSL/Linux .venv issues."""
    return os.path.join(project_root, ".venv-win")


def _build_windows_install_commands(project_root: str, package_specs: List[str]) -> List[str]:
    project_root = os.path.abspath(project_root)
    env_path = _get_windows_project_environment(project_root)
    quoted_specs = " ".join(_quote_cmd_arg(spec) for spec in package_specs)
    command_prefix = (
        f'set "UV_PROJECT_ENVIRONMENT={env_path}" && '
        f'uv --directory {_quote_cmd_arg(project_root)} add '
    )

    commands = [command_prefix + quoted_specs]
    commands.extend(command_prefix + _quote_cmd_arg(spec) for spec in package_specs)
    return commands


def _build_powershell_install_commands(project_root: str, package_specs: List[str]) -> List[str]:
    project_root = os.path.abspath(project_root)
    env_path = _get_windows_project_environment(project_root)
    quoted_specs = " ".join(f"'{spec}'" for spec in package_specs)
    command_prefix = (
        f"$env:UV_PROJECT_ENVIRONMENT='{env_path}'; "
        f"uv --directory '{project_root}' add "
    )

    commands = [command_prefix + quoted_specs]
    commands.extend(command_prefix + f"'{spec}'" for spec in package_specs)
    return commands


def _build_posix_install_commands(project_root: str, package_specs: List[str]) -> List[str]:
    project_root = os.path.abspath(project_root)
    env_path = os.path.join(project_root, ".venv")
    quoted_specs = " ".join(_quote_posix_arg(spec) for spec in package_specs)
    command_prefix = (
        f"UV_PROJECT_ENVIRONMENT={_quote_posix_arg(env_path)} "
        f"uv --directory {_quote_posix_arg(project_root)} add "
    )

    commands = [command_prefix + quoted_specs]
    commands.extend(command_prefix + _quote_posix_arg(spec) for spec in package_specs)
    return commands


def _build_install_commands(missing_modules: List[str], project_root: str) -> List[str]:
    commands: List[str] = []
    combined_specs: List[str] = []

    for module_name in missing_modules:
        package_spec = REQUIRED_MODULE_SPECS.get(module_name, module_name)
        combined_specs.append(package_spec)

    if not combined_specs:
        return commands

    if os.name == "nt":
        commands.extend(_build_windows_install_commands(project_root, combined_specs))
        commands.extend(_build_powershell_install_commands(project_root, combined_specs))
    else:
        commands.extend(_build_posix_install_commands(project_root, combined_specs))

    return commands


def inspect_mcp_runtime(project_root: str | None = None) -> Dict[str, object]:
    resolved_root = os.path.abspath(project_root or PROJECT_ROOT)
    component_root = os.path.join(resolved_root, "Tools", "MCPServer")

    missing_files = [
        os.path.join(component_root, filename)
        for filename in REQUIRED_COMPONENT_FILES
        if not os.path.exists(os.path.join(component_root, filename))
    ]

    missing_modules = [
        module_name
        for module_name in REQUIRED_MODULE_SPECS
        if not _module_exists(module_name)
    ]

    install_commands = _build_install_commands(missing_modules, resolved_root)
    available = not missing_files and not missing_modules

    return {
        "available": available,
        "project_root": resolved_root,
        "component_root": component_root,
        "missing_files": missing_files,
        "missing_modules": missing_modules,
        "install_commands": install_commands,
        "primary_install_command": install_commands[0] if install_commands else "",
    }


def _tr(
    translate: Optional[Callable[[str, str], str]],
    key: str,
    default: str,
) -> str:
    """Translate a runtime status string when an i18n callback is available."""
    if translate is None:
        return default

    try:
        value = translate(key, default)
    except TypeError:
        value = translate(key)  # type: ignore[misc]
    except Exception:
        return default

    return default if not value or value == key else value


def format_runtime_status_lines(
    status: Dict[str, object],
    translate: Optional[Callable[[str, str], str]] = None,
) -> List[str]:
    lines: List[str] = []

    missing_files = list(status.get("missing_files", []))
    missing_modules = list(status.get("missing_modules", []))
    install_commands = list(status.get("install_commands", []))

    if missing_files:
        lines.append(
            _tr(
                translate,
                "msg_mcp_missing_component_files",
                "Missing MCP component files:",
            )
        )
        lines.extend(f"- {path}" for path in missing_files)

    if missing_modules:
        lines.append(
            _tr(
                translate,
                "msg_mcp_missing_python_modules",
                "Missing Python modules:",
            )
        )
        lines.extend(f"- {name}" for name in missing_modules)

    if install_commands:
        if os.name == "nt":
            lines.append(
                _tr(
                    translate,
                    "msg_mcp_suggested_install_commands_windows",
                    "Suggested install command(s) for Windows:",
                )
            )
            lines.append(
                "- "
                + _tr(
                    translate,
                    "msg_mcp_windows_install_hint_primary",
                    "The first command is for cmd.exe and uses .venv-win to avoid .venv\\lib64 conflicts.",
                )
            )
            lines.append(
                "- "
                + _tr(
                    translate,
                    "msg_mcp_windows_install_hint_fallback",
                    "The later commands are PowerShell alternatives and per-package fallbacks.",
                )
            )
        else:
            lines.append(
                _tr(
                    translate,
                    "msg_mcp_suggested_install_commands",
                    "Suggested install command(s):",
                )
            )
        lines.extend(f"- {cmd}" for cmd in install_commands)

    if not lines:
        lines.append(
            _tr(
                translate,
                "msg_mcp_runtime_ready",
                "AiNiee MCP runtime is ready.",
            )
        )

    return lines
