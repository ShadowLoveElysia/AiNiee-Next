"""Runtime checks for the Skills framework."""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
SKILLS_ROOT = os.path.join(PROJECT_ROOT, "Tools", "Skills")

REQUIRED_SKILL_FILES = (
    "__init__.py",
    "skill_base.py",
    "server.py",
    "task_runtime.py",
    "skills/__init__.py",
    "skills/common.py",
    "skills/system_skill.py",
    "skills/config_skill.py",
    "skills/translate_skill.py",
    "skills/queue_skill.py",
    "skills/profile_skill.py",
    "skills/file_skill.py",
)


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def inspect_skills_runtime(project_root: str | None = None) -> Dict[str, Any]:
    """Check if the Skills framework is ready to run."""
    resolved_root = os.path.abspath(project_root or PROJECT_ROOT)
    component_root = os.path.join(resolved_root, "Tools", "Skills")

    missing_files = [
        os.path.join(component_root, filename)
        for filename in REQUIRED_SKILL_FILES
        if not os.path.exists(os.path.join(component_root, filename))
    ]

    # The HTTP layer has no extra server dependencies; business logic reuses project modules.
    required_modules = ("json", "http.server", "urllib.parse")
    missing_modules = [
        name for name in required_modules if not _module_exists(name)
    ]

    import_errors: Dict[str, str] = {}
    if not missing_files:
        # Keep the component check independent from optional project packages.
        # The HTTP process imports the registry when it starts and will report a
        # precise import error there; this check must remain usable for install
        # diagnostics in a minimal environment.
        try:
            from Tools.Skills.skills import build_registry

            registry = build_registry()
            registry_count = registry.count
        except Exception as exc:
            registry_count = 0
            import_errors["skills_registry"] = f"{type(exc).__name__}: {exc}"
    else:
        registry_count = 0

    component_ready = not missing_files and not missing_modules
    business_ready = component_ready and not import_errors

    return {
        # ``available`` means the Skills component and HTTP stdlib are present;
        # ``business_ready`` additionally proves all registered Skills import.
        "available": component_ready,
        "component_ready": component_ready,
        "business_ready": business_ready,
        "project_root": resolved_root,
        "component_root": component_root,
        "missing_files": missing_files,
        "missing_modules": missing_modules,
        "import_errors": import_errors,
        "skills_count": registry_count,
        "note": "The Skills HTTP layer has no server package dependencies beyond the standard library.",
    }


def format_runtime_status_lines(status: Dict[str, Any]) -> List[str]:
    """Format runtime status into human-readable lines."""
    lines: List[str] = []
    missing_files = status.get("missing_files", [])
    missing_modules = status.get("missing_modules", [])
    import_errors = status.get("import_errors", {})

    if missing_files:
        lines.append("Missing Skills component files:")
        lines.extend(f"  - {path}" for path in missing_files)

    if missing_modules:
        lines.append("Missing standard library modules (unexpected):")
        lines.extend(f"  - {name}" for name in missing_modules)

    if import_errors:
        lines.append("Skills registry import failed:")
        lines.extend(f"  - {name}: {error}" for name, error in import_errors.items())

    if not lines and not status.get("business_ready", True):
        lines.append("Skills HTTP component is ready, but one or more production Skills cannot be imported.")

    if not lines:
        lines.append("AiNiee Skills runtime is ready (no extra server dependencies required).")

    return lines


def runtime_check_exit_code(status: Dict[str, Any]) -> int:
    """Return the stable exit code used by no-socket Skills preflight commands.

    ``0`` means every registered production Skill imported successfully.  ``2``
    means the probe ran, but files, standard-library support, or business
    dependencies are incomplete.  A probe implementation error is reserved for
    the caller and should use exit code ``1``.
    """
    return 0 if status.get("business_ready", False) else 2
