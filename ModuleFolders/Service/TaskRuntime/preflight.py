"""Resolve task profiles and overrides once for preview and launch validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ModuleFolders.Infrastructure.TaskContract import TaskSpec, build_cli_args
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config
from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import (
    apply_runtime_overrides, merge_runtime_overrides, runtime_parameter_schema, task_runtime_overrides,
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
    declared = spec.workflow_steps or [
        {"id": role, "type": role} for role in
        (["translate", "polish"] if spec.task_type == "all_in_one" else [spec.task_type])
    ]
    expanded = []
    for step in declared:
        if step["type"] == "all_in_one":
            expanded.extend([{**step, "type": role, "id": f"{step['id']}.{role}"} for role in ("translate", "polish")])
        else:
            expanded.append(step)
    known_ids = {step["id"] for step in expanded} | {step["id"] for step in declared}
    if spec.workflow_steps and set(spec.step_overrides) - known_ids:
        raise ValueError("step_overrides contains unknown workflow step IDs")
    overrides = task_runtime_overrides(spec.to_mapping())
    missing = []
    steps = {}
    fields = {item["key"] for item in runtime_parameter_schema()}
    for declaration in expanded:
        role, step_id = declaration["type"], declaration["id"]
        parent_id = step_id.rsplit(".", 1)[0]
        parent = spec.step_overrides.get(parent_id, {}) if parent_id != step_id else {}
        step = {**parent, **spec.step_overrides.get(step_id, {})}
        if step.get("enabled", declaration.get("enabled", True)) is False:
            continue
        step_config = config
        if declaration.get("profile") or declaration.get("rules_profile"):
            step_config = load_effective_config(
                active_profile_name=declaration.get("profile") or spec.profile,
                active_rules_profile_name=declaration.get("rules_profile") or spec.rules_profile,
                create_missing=False,
            )
        # TaskSpec already validates legacy fields with their established ranges.
        effective = apply_runtime_overrides(step_config, overrides, role)
        effective = apply_runtime_overrides(effective, task_runtime_overrides(declaration), role)
        effective = apply_runtime_overrides(effective, merge_runtime_overrides(parent.get("runtime_overrides"), step.get("runtime_overrides")), role)
        if role == "translate" and not spec.manga and not _prompt_selected(effective.get("translation_prompt_selection"), {100, 200, 300}):
            missing.append("translation")
        if role == "polish" and not _prompt_selected(effective.get("polishing_prompt_selection"), {10001}):
            missing.append("polishing")
        steps[step_id] = {
            "values": {key: effective[key] for key in fields if key in effective},
            "runtime_parameters_fingerprint": hashlib.sha256(json.dumps(
                {key: effective[key] for key in fields if key in effective},
                ensure_ascii=False, sort_keys=True,
            ).encode()).hexdigest(),
        }
    request = spec.to_mapping(include_api_key=False)
    output = spec.output_path
    if spec.input_path and spec.task_type in {"translate", "polish", "all_in_one"} and not spec.manga:
        from ModuleFolders.UserInterface.ConfigExperience import calculate_output_path
        path_config = dict(config)
        if output:
            path_config.update(label_output_path=output, auto_set_output_path=False)
        output = calculate_output_path(path_config, spec.input_path)
    output_exists = bool(output and Path(output).exists())
    cache_exists = bool(output and (Path(output) / "cache/AinieeCacheData.json").is_file())
    return {
        "valid": not missing,
        "missing_prompts": missing,
        "task_type": spec.task_type,
        "profile": config.get("active_profile", spec.profile),
        "rules_profile": config.get("active_rules_profile", spec.rules_profile),
        "argv": build_cli_args(spec, non_interactive=True, web_mode=True),
        "steps": steps,
        "resolved_output_path": output,
        "output_exists": output_exists,
        "cache_exists": cache_exists,
        "output_policy": spec.output_policy or ("resume" if cache_exists else "create"),
        "fingerprint_scope": "normalized_request_and_runtime_parameters",
        "request_fingerprint": hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }
