"""Resolve task profiles and overrides once for preview and launch validation."""
from __future__ import annotations

import hashlib
import json

from ModuleFolders.Infrastructure.TaskContract import TaskSpec, build_cli_args
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config
from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import (
    apply_runtime_overrides, runtime_parameter_schema, task_runtime_overrides,
)


def _prompt_selected(selection, builtin_ids: set[int]) -> bool:
    if not isinstance(selection, dict):
        return False
    selected = selection.get("last_selected_id")
    return selected in builtin_ids or (
        selected not in (None, "") and isinstance(selection.get("prompt_content"), str)
        and bool(selection["prompt_content"].strip())
    )


def preview_task(spec: TaskSpec) -> dict:
    config = load_effective_config(
        active_profile_name=spec.profile, active_rules_profile_name=spec.rules_profile,
        create_missing=False,
    )
    roles = ["translate", "polish"] if spec.task_type == "all_in_one" else [spec.task_type]
    overrides = task_runtime_overrides(spec.to_mapping())
    missing = []
    steps = {}
    fields = {item["key"] for item in runtime_parameter_schema()}
    for role in roles:
        step = spec.step_overrides.get(role, {})
        if step.get("enabled") is False:
            continue
        # TaskSpec already validates legacy fields with their established ranges.
        effective = apply_runtime_overrides(config, overrides, role)
        effective = apply_runtime_overrides(effective, step.get("runtime_overrides", {}), role)
        if role == "translate" and not _prompt_selected(effective.get("translation_prompt_selection"), {100, 200, 300}):
            missing.append("translation")
        if role == "polish" and not _prompt_selected(effective.get("polishing_prompt_selection"), {10001}):
            missing.append("polishing")
        steps[role] = {
            "values": {key: effective[key] for key in fields if key in effective},
            "runtime_parameters_fingerprint": hashlib.sha256(json.dumps(
                {key: effective[key] for key in fields if key in effective},
                ensure_ascii=False, sort_keys=True,
            ).encode()).hexdigest(),
        }
    request = spec.to_mapping(include_api_key=False)
    return {
        "valid": not missing,
        "missing_prompts": missing,
        "task_type": spec.task_type,
        "profile": config.get("active_profile", spec.profile),
        "rules_profile": config.get("active_rules_profile", spec.rules_profile),
        "argv": build_cli_args(spec, non_interactive=True, web_mode=True),
        "steps": steps,
        "fingerprint_scope": "normalized_request_and_runtime_parameters",
        "request_fingerprint": hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }
