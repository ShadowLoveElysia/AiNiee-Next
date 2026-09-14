"""持久保存任务有效参数和规则内容，凭证仅在运行时从原接口读取。"""

from __future__ import annotations

import copy
import hashlib
import json
import os

from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import runtime_parameter_schema


RUNTIME_SNAPSHOT_ENV = "AINIEE_RUNTIME_SNAPSHOT_FILE"
_RESOURCE_KEYS = {
    "pre_translation_data", "post_translation_data", "prompt_dictionary_data", "exclusion_list_data",
    "characterization_data", "world_building_content", "writing_style_content", "translation_example_data",
    "translation_prompt_selection", "polishing_prompt_selection", "plugin_enables",
    "source_language", "target_language", "polishing_mode_selection", "api_settings",
    "dynamic_glossary_series", "dynamic_glossary_volume", "dynamic_glossary_volume_map",
    "backup_apis", "sdk_request_mode", "use_openai_sdk", "response_check_switch", "model", "base_url",
}
_INTERFACE_KEYS = {
    "tag", "model", "api_url", "api_format", "auto_complete", "rpm_limit", "tpm_limit",
    "temperature", "top_p", "presence_penalty", "frequency_penalty", "think_switch", "think_depth",
    "thinking_budget", "max_output_tokens", "structured_output_mode", "region",
}
_CREDENTIAL_KEYS = {"api_key", "access_key", "secret_key"}


def capture_runtime_snapshot(config: dict) -> dict:
    keys = {field["key"] for field in runtime_parameter_schema()} | _RESOURCE_KEYS
    from ModuleFolders.Infrastructure.SensitiveData import sanitize_sensitive_data
    defaults = {field["key"]: field["default"] for field in runtime_parameter_schema() if field["default"] is not None and field["key"] not in {"think_switch", "think_depth", "thinking_budget", "structured_output_mode"}}
    values = sanitize_sensitive_data({key: copy.deepcopy(config.get(key, defaults.get(key))) for key in keys if (key in config or key in defaults) and key != "platform"})
    interfaces = {
        name: {key: copy.deepcopy(value) for key, value in settings.items() if key in _INTERFACE_KEYS}
        for name, settings in config.get("platforms", {}).items() if isinstance(settings, dict)
    }
    payload = {"version": 1, "values": values, "interfaces": interfaces}
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return payload


def restore_runtime_snapshot(config: dict, snapshot: dict) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise ValueError("Unsupported runtime snapshot version")
    result = copy.deepcopy(config)
    allowed = {field["key"] for field in runtime_parameter_schema()} | _RESOURCE_KEYS
    values = snapshot.get("values", {})
    if not isinstance(values, dict) or set(values) - allowed:
        raise ValueError("Invalid runtime snapshot settings")
    result.update(copy.deepcopy(values))
    for name, settings in snapshot.get("interfaces", {}).items():
        if not isinstance(settings, dict) or set(settings) - _INTERFACE_KEYS:
            raise ValueError("Invalid runtime snapshot interface")
        current = config.get("platforms", {}).get(name)
        if current is None:
            raise ValueError(f"Configured interface no longer exists: {name}")
        result.setdefault("platforms", {})[name] = {
            **copy.deepcopy(settings),
            **{key: copy.deepcopy(current[key]) for key in _CREDENTIAL_KEYS if key in current},
            # 接口扩展参数可能包含凭证，沿用当前接口管理，不写入快照。
            "extra_body": copy.deepcopy(current.get("extra_body", {})),
        }
    for key in ("model", "base_url"):
        result[key] = values.get(key, "")
    result["api_key"] = config.get("api_key", "")
    return result


def snapshot_for_task(payload: dict) -> dict:
    from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config
    config = load_effective_config(
        active_profile_name=payload.get("profile"), active_rules_profile_name=payload.get("rules_profile"),
        create_missing=False,
    )
    from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import apply_runtime_overrides
    prompt_values = {key: value for key, value in (payload.get("runtime_overrides") or {}).items() if key.endswith("_prompt_id")}
    if prompt_values:
        config = apply_runtime_overrides(config, prompt_values)
    snapshot = capture_runtime_snapshot(config)
    step_snapshots = {}
    step_configs = {}
    steps = list(payload.get("workflow_steps") or [])
    for step_id, settings in (payload.get("step_overrides") or {}).items():
        steps.append({"id": step_id, **settings})
    for step in steps:
        if step.get("profile") or step.get("rules_profile"):
            step_configs[step.get("id", f"{step.get('type', 'step')}-{steps.index(step) + 1}")] = capture_runtime_snapshot(load_effective_config(
                active_profile_name=step.get("profile") or payload.get("profile"),
                active_rules_profile_name=step.get("rules_profile") or payload.get("rules_profile"),
                create_missing=False,
            ))
        values = {key: value for key, value in (step.get("runtime_overrides") or {}).items() if key.endswith("_prompt_id")}
        if not values:
            continue
        prepared = apply_runtime_overrides(config, values)
        step_snapshots[step.get("id", f"{step.get('type', 'step')}-{steps.index(step) + 1}")] = {
            key: prepared[key] for key in ("translation_prompt_selection", "polishing_prompt_selection") if key in prepared
        }
    if step_snapshots:
        snapshot["step_prompts"] = step_snapshots
    if step_configs:
        snapshot["step_configs"] = step_configs
    return snapshot


def write_worker_snapshot(payload: dict) -> str:
    import tempfile
    from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import RESOURCE_PATH
    folder = os.path.join(RESOURCE_PATH, "automation_progress")
    os.makedirs(folder, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="runtime-", suffix=".json", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as writer:
            json.dump(snapshot_for_task(payload), writer, ensure_ascii=False)
    except BaseException:
        os.unlink(path)
        raise
    return path
