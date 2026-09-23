from __future__ import annotations

import copy
import os
import shutil
import tempfile
import uuid
from typing import Any, Dict, Mapping, Tuple

from ModuleFolders.Infrastructure.TaskContract import (
    QUEUE_TASK_OVERRIDE_FIELDS,
    TASK_API_KEY_ENV,
    TaskSpec,
    build_cli_args,
)
from Tools.Skills.skill_base import SkillError, SkillParameter, SkillResult

from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    PROFILES_PATH,
    atomic_write_json,
    get_active_profile_name,
    list_profile_names,
    load_json_file,
    load_root_config,
    resolve_profile_path,
    save_root_config,
)
from Tools.MCPServer.security import (
    contains_redacted_secret,
    restore_redacted_secrets,
    sanitize_data_for_mcp,
    strip_mcp_security_metadata,
)


CONFIG_SECURITY_PATH = "/api/config"
QUEUE_SECURITY_PATH = "/api/queue/raw"

# Skills can be reached through an authenticated HTTP listener, so paths sent
# by a client must not implicitly become arbitrary local file access.  The
# project directory remains usable by default; additional user workspaces can
# be opted in with ``AINIEE_SKILLS_ALLOWED_PATHS``.  A fully open policy is
# available only through the explicit ``AINIEE_SKILLS_ALLOW_EXTERNAL_PATHS``
# switch for trusted local automation.
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SKILLS_ALLOWED_PATHS_ENV = "AINIEE_SKILLS_ALLOWED_PATHS"
SKILLS_ALLOW_EXTERNAL_PATHS_ENV = "AINIEE_SKILLS_ALLOW_EXTERNAL_PATHS"
EXTERNAL_INPUT_STAGING_DIR = os.path.join("Resource", "automation_progress", "external_inputs")


class SkillPathError(SkillError):
    """Raised when a Skills path is outside the configured workspace roots."""

    def __init__(self, message: str, code: str = "PATH_NOT_ALLOWED") -> None:
        super().__init__(message, code)


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def skill_allowed_roots() -> tuple[str, ...]:
    """Return real workspace roots allowed for Skills file operations.

    The project root is always retained so the built-in Resource files and
    relative paths continue to work.  The environment value is deliberately
    additive and uses the native path separator for each operating system.
    """
    roots = [os.path.realpath(PROJECT_ROOT)]
    # The OS temporary directory is a conventional staging location and keeps
    # isolated automation/test runs usable without granting access to the whole
    # filesystem.  Callers needing another workspace must opt in explicitly.
    try:
        temporary_root = os.path.realpath(tempfile.gettempdir())
    except OSError:
        temporary_root = ""
    if temporary_root and temporary_root not in roots:
        roots.append(temporary_root)
    configured = os.environ.get(SKILLS_ALLOWED_PATHS_ENV, "")
    for raw_root in configured.split(os.pathsep):
        raw_root = raw_root.strip().strip('"').strip("'")
        if raw_root:
            candidate = os.path.realpath(os.path.abspath(os.path.expanduser(raw_root)))
            if candidate not in roots:
                roots.append(candidate)
    return tuple(roots)


def external_input_staging_root(*, create: bool = False) -> str:
    """Return the project-owned staging directory for user supplied files.

    A Skills client may select a file outside the AiNiee workspace, but the
    batch service must never consume that path directly.  ``stage_external``
    copies the explicitly confirmed file here; the resulting path is inside
    ``PROJECT_ROOT`` and therefore accepted by the normal batch boundary.  A
    project-owned directory also works when the MCP and Skills processes use
    different temporary-directory implementations or run under Windows.
    """
    root = os.path.realpath(os.path.join(PROJECT_ROOT, EXTERNAL_INPUT_STAGING_DIR))
    if create:
        os.makedirs(root, exist_ok=True)
    return root


def stage_external_input(path: Any, *, confirmed: bool) -> dict[str, str]:
    """Copy one user-confirmed external file into the controlled workspace.

    The source is intentionally resolved without applying the workspace policy:
    this is the one operation that accepts a user-selected external path.  The
    destination is randomized and always checked to remain under the staging
    root before copying.  Callers should pass the returned ``local_path`` to
    translation or Agent batch Skills; they must not forward the source path.
    """
    if not confirmed:
        raise SkillPathError(
            "stage_external requires explicit confirmation for a user-supplied file.",
            "EXTERNAL_PATH_CONFIRMATION_REQUIRED",
        )
    if not isinstance(path, str) or not path.strip():
        raise SkillPathError("path must be a non-empty path.", "INVALID_PATH")
    raw_path = path.strip().strip('"').strip("'")
    source = os.path.realpath(os.path.abspath(os.path.expanduser(raw_path)))
    if not os.path.isfile(source):
        raise SkillPathError("The supplied external path is not a file.", "INVALID_PATH")

    root = external_input_staging_root(create=True)
    destination = os.path.realpath(
        os.path.join(root, f"{uuid.uuid4().hex}_{os.path.basename(source)}")
    )
    try:
        if os.path.commonpath((root, destination)) != root:
            raise SkillPathError("staging destination escapes the project staging root.", "PATH_NOT_ALLOWED")
    except ValueError as exc:
        raise SkillPathError("staging destination is on an unrelated filesystem.", "PATH_NOT_ALLOWED") from exc
    try:
        shutil.copy2(source, destination)
    except OSError as exc:
        raise SkillPathError(f"Unable to stage external file: {exc}", "IO_ERROR") from exc
    return {
        "local_path": destination,
        "source_name": os.path.basename(source),
        "staging_root": root,
    }


def validate_skill_path(
    path: Any,
    *,
    field_name: str = "path",
    must_exist: bool = False,
    expect_file: bool | None = None,
    expect_dir: bool | None = None,
) -> str:
    """Normalize and authorize a path supplied to a production Skill.

    ``realpath`` makes the check apply to symlinks as well as ``..`` traversal.
    Missing output/queue files are accepted after their real parent path has
    been checked, allowing callers to create new files inside an allowed root.
    """
    if not isinstance(path, str) or not path.strip():
        raise SkillPathError(f"{field_name} must be a non-empty path.")
    raw_path = path.strip().strip('"').strip("'")
    candidate = os.path.realpath(os.path.abspath(os.path.expanduser(raw_path)))

    if not _is_truthy(os.environ.get(SKILLS_ALLOW_EXTERNAL_PATHS_ENV)):
        normalized_candidate = os.path.normcase(candidate)
        allowed = False
        for root in skill_allowed_roots():
            normalized_root = os.path.normcase(os.path.realpath(root))
            try:
                if os.path.commonpath((normalized_root, normalized_candidate)) == normalized_root:
                    allowed = True
                    break
            except ValueError:
                # Windows drives (or otherwise incomparable path forms) are
                # not allowed to pass the boundary accidentally.
                continue
        if not allowed:
            raise SkillPathError(
                f"{field_name} is outside the configured Skills workspace roots."
            )

    if must_exist and not os.path.exists(candidate):
        raise SkillPathError(f"{field_name} does not exist.", "NOT_FOUND")
    if expect_file is True and os.path.exists(candidate) and not os.path.isfile(candidate):
        raise SkillPathError(f"{field_name} must be a file.", "INVALID_PATH")
    if expect_dir is True and os.path.exists(candidate) and not os.path.isdir(candidate):
        raise SkillPathError(f"{field_name} must be a directory.", "INVALID_PATH")
    return candidate


def validate_skill_glob_pattern(pattern: Any) -> str:
    """Reject absolute/traversing glob patterns before joining them to a root."""
    if pattern is None or pattern == "":
        return "*"
    if not isinstance(pattern, str):
        raise SkillPathError("pattern must be a string.", "INVALID_PATTERN")
    normalized = pattern.strip()
    if not normalized:
        return "*"
    if (
        os.path.isabs(normalized)
        or normalized.startswith(("/", "\\"))
        or os.path.splitdrive(normalized)[0]
        or ".." in normalized.replace("\\", "/").split("/")
    ):
        raise SkillPathError(
            "pattern must be relative and cannot traverse parent directories.",
            "INVALID_PATTERN",
        )
    return normalized


def validate_task_spec_paths(spec: TaskSpec) -> TaskSpec:
    """Apply the Skills path policy to shared task input/output overrides."""
    for field_name in ("input_path", "output_path", "queue_file"):
        value = getattr(spec, field_name, None)
        if value:
            validate_skill_path(value, field_name=field_name)
    return spec


def validate_wait_options(
    args: Mapping[str, Any],
    *,
    error_code: str = "INVALID_ARGUMENTS",
) -> tuple[bool, int | None] | SkillResult:
    """Normalize the lifecycle wait controls shared by task Skills.

    The public protocol documents ``wait_timeout`` as an integer.  Rejecting
    strings, booleans, negative values and non-finite numbers here keeps HTTP,
    CLI and direct registry calls from silently changing wait semantics.
    """
    wait = args.get("wait", False)
    if not isinstance(wait, bool):
        return SkillResult.fail("wait must be a boolean.", error_code)

    timeout = args.get("wait_timeout")
    if timeout is None:
        return wait, None
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        return SkillResult.fail("wait_timeout must be a non-negative integer.", error_code)
    if timeout < 0:
        return SkillResult.fail("wait_timeout must be a non-negative integer.", error_code)
    return wait, timeout


_PARAMETER_DESCRIPTIONS = {
    "input_path": "Path to the input file or directory.",
    "execution_mode": "Task execution backend: default_api or external_agent.",
    "output_path": "Output directory path.",
    "profile": "Configuration profile name.",
    "rules_profile": "Rules profile name.",
    "source_lang": "Source language.",
    "target_lang": "Target language.",
    "project_type": "Project type (Txt, Epub, MTool, RenPy, etc.).",
    "resume": "Resume from cache if available.",
    "platform": "API platform override.",
    "model": "Model name override.",
    "api_url": "API base URL override.",
    "api_key": "Temporary API key override; never added to process argv.",
    "failover": "Enable or disable API failover for this task.",
    "threads": "Concurrent thread count.",
    "retry": "Maximum retry count.",
    "timeout": "Request timeout in seconds.",
    "rounds": "Maximum execution rounds.",
    "pre_lines": "Context lines included before each segment.",
    "lines_limit": "Lines per request; mutually exclusive with tokens_limit.",
    "tokens_limit": "Tokens per request; mutually exclusive with lines_limit.",
    "think_depth": "Reasoning depth name or integer from 0 to 10000.",
    "thinking_budget": "Thinking token budget.",
    "polish_mode": "Polishing mode for polish or all-in-one tasks.",
    "runtime_overrides": "Per-run settings object; omitted fields inherit, false and zero are preserved.",
    "step_overrides": "Settings keyed by stable workflow step ID (translate/polish for built-in tasks).",
}
_INTEGER_PARAMETERS = {
    "threads",
    "retry",
    "timeout",
    "rounds",
    "pre_lines",
    "lines_limit",
    "tokens_limit",
    "thinking_budget",
}
_BOOLEAN_PARAMETERS = {"resume", "failover"}
_TASK_FIELD_ORDER = tuple(
    field for field in QUEUE_TASK_OVERRIDE_FIELDS if field != "input_path"
)


def task_skill_parameters(
    *,
    include_manga: bool = False,
    require_input: bool = False,
) -> list[SkillParameter]:
    """由共享协议生成 Translate/Queue Skills 的公共字段目录。"""
    parameters = []
    for name in ("input_path", *_TASK_FIELD_ORDER):
        param_type = "integer" if name in _INTEGER_PARAMETERS else "boolean" if name in _BOOLEAN_PARAMETERS else "string"
        if name in {"runtime_overrides", "step_overrides"}:
            param_type = "object"
        parameters.append(
            SkillParameter(
                name=name,
                description=_PARAMETER_DESCRIPTIONS[name],
                type=param_type,
                required=name == "input_path" and require_input,
            )
        )
    parameters.extend(
        [
            SkillParameter(
                name="lines",
                description="Legacy alias of lines_limit.",
                type="integer",
                required=False,
            ),
            SkillParameter(
                name="tokens",
                description="Legacy alias of tokens_limit.",
                type="integer",
                required=False,
            ),
        ]
    )
    if include_manga:
        parameters.append(
            SkillParameter(
                name="manga",
                description="Run the translate task through MangaCore.",
                type="boolean",
                required=False,
            )
        )
    return parameters


def task_spec_from_skill_args(args: Dict[str, Any]) -> TaskSpec:
    payload = dict(args)
    # Skill control fields are transport metadata, not part of TaskContract.
    # Strip them centrally so HTTP, standalone CLI and direct registry calls
    # cannot drift on which lifecycle fields are accepted.
    for control_field in ("action", "index", "task_id", "wait", "wait_timeout"):
        payload.pop(control_field, None)
    if "task" not in payload and "task_type" not in payload:
        payload["task_type"] = "translate"
    return validate_task_spec_paths(TaskSpec.from_mapping(payload))


def task_subprocess_invocation(spec: TaskSpec) -> tuple[list[str], Dict[str, str]]:
    """生成 Skill 子进程 argv/env，确保临时密钥不出现在命令行。"""
    command = ["-m", "ainiee_cli", *build_cli_args(spec, non_interactive=True)]
    env = os.environ.copy()
    env.pop(TASK_API_KEY_ENV, None)
    if spec.api_key:
        env[TASK_API_KEY_ENV] = spec.api_key
    if spec.runtime_overrides or spec.step_overrides:
        from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import RUNTIME_SNAPSHOT_ENV, write_worker_snapshot
        env[RUNTIME_SNAPSHOT_ENV] = write_worker_snapshot(spec.to_mapping())
    return command, env


def load_dict_json(path: str) -> Dict[str, Any]:
    """Load a JSON object from disk and return an empty dict on invalid data."""
    try:
        data = load_json_file(path, {})
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def active_profile_name() -> str:
    return get_active_profile_name(load_root_config())


def resolve_config_profile_path(profile: Any = None) -> Tuple[str, str]:
    """Resolve a profile file path without allowing path traversal."""
    if profile is not None and not isinstance(profile, str):
        raise ValueError("profile must be a string")
    profile_name = profile or active_profile_name()
    return resolve_profile_path(PROFILES_PATH, profile_name)


def sanitize_config_value(value: Any, key: str) -> Any:
    """Redact a config value when exposing it to Skills clients."""
    return sanitize_data_for_mcp(
        value,
        path=CONFIG_SECURITY_PATH,
        field_name=key,
    )


def sanitize_payload(data: Any, *, path: str = CONFIG_SECURITY_PATH) -> Any:
    return sanitize_data_for_mcp(data, path=path)


def prepare_config_value_for_save(value: Any, current_value: Any, key: str) -> Any:
    """
    Restore redacted secret placeholders before saving.

    This lets a client round-trip sanitized data without overwriting an existing
    API key with "[MCP_SECRET_REDACTED]".
    """
    clean_value = strip_mcp_security_metadata(copy.deepcopy(value))
    restored = restore_redacted_secrets(clean_value, current_value, field_name=key)
    if contains_redacted_secret(restored, field_name=key):
        raise ValueError(
            f"Refusing to save redacted placeholder for sensitive config key: {key}"
        )
    return restored
