from __future__ import annotations

import importlib.util
import os
from typing import Dict, List


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
    "runtime.py",
    "server.py",
)


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _build_install_commands(missing_modules: List[str]) -> List[str]:
    commands: List[str] = []
    combined_specs: List[str] = []

    for module_name in missing_modules:
        package_spec = REQUIRED_MODULE_SPECS.get(module_name, module_name)
        combined_specs.append(package_spec)
        commands.append(f"uv add {package_spec}")

    if len(combined_specs) > 1:
        commands.insert(0, "uv add " + " ".join(combined_specs))

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

    install_commands = _build_install_commands(missing_modules)
    available = not missing_files and not missing_modules

    return {
        "available": available,
        "component_root": component_root,
        "missing_files": missing_files,
        "missing_modules": missing_modules,
        "install_commands": install_commands,
        "primary_install_command": install_commands[0] if install_commands else "",
    }


def format_runtime_status_lines(status: Dict[str, object]) -> List[str]:
    lines: List[str] = []

    missing_files = list(status.get("missing_files", []))
    missing_modules = list(status.get("missing_modules", []))
    install_commands = list(status.get("install_commands", []))

    if missing_files:
        lines.append("Missing MCP component files:")
        lines.extend(f"- {path}" for path in missing_files)

    if missing_modules:
        lines.append("Missing Python modules:")
        lines.extend(f"- {name}" for name in missing_modules)

    if install_commands:
        lines.append("Suggested install command(s):")
        lines.extend(f"- {cmd}" for cmd in install_commands)

    if not lines:
        lines.append("AiNiee MCP runtime is ready.")

    return lines
