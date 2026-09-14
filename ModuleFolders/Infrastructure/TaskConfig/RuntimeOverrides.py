"""任务运行参数的定义、校验和配置映射；缺省值继承，False 和 0 保留。"""

from __future__ import annotations

import copy
import json
import math
import os
from typing import Any, Mapping

from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import CONFIG_REGISTRY


class RuntimeOverrideError(ValueError):
    pass


_GROUPS = {
    "execution": "user_thread_counts enable_async_mode enable_rate_limit custom_rpm_limit custom_tpm_limit request_timeout enable_stream_api",
    "batch": "tokens_limit_switch lines_limit tokens_limit chunk_soft_limit_extra_lines line_split_optimization_mode retry_split_min_lines",
    "context": "pre_line_counts polishing_pre_line_counts enable_context_enhancement character_recall_switch character_recall_context_lines character_recall_lookahead_lines sparse_completion_previous_lines sparse_completion_lookahead_lines translation_consistency_enhancement",
    "references": "prompt_dictionary_switch dynamic_glossary_switch translation_memory_switch rag_enabled rag_top_k characterization_switch world_building_switch writing_style_switch translation_example_switch few_shot_and_example_switch",
    "generation": "think_switch think_depth thinking_budget temperature top_p max_output_tokens structured_output_mode enable_prompt_caching",
    "checks": "newline_character_count_check return_to_original_text_check residual_original_text_check reply_format_check retry_count round_limit enable_smart_round_limit smart_round_max_limit untranslated_retry_limit untranslated_reduction_rate enable_retry_backoff enable_api_failover api_failover_threshold",
    "proofread": "enable_auto_proofread proofread_context_lines proofread_batch_size proofread_confidence_threshold",
    "text": "pre_translation_switch post_translation_switch exclusion_list_switch auto_process_text_code_segment language_filter_minority_ratio_threshold",
    "connection": "platform model",
    "prompt": "translation_prompt_id polishing_prompt_id",
}

_EXTRA = {
    "platform": ("string", None, None, None),
    "model": ("string", None, None, None),
    "translation_prompt_id": ("string", None, None, None),
    "polishing_prompt_id": ("string", None, None, None),
    "dynamic_glossary_switch": ("bool", False, None, None),
    "translation_consistency_enhancement": ("bool", False, None, None),
    "polishing_pre_line_counts": ("int", 2, 0, 200),
    "rag_enabled": ("bool", None, None, None),
    "rag_top_k": ("int", 5, 1, 100),
    "temperature": ("float", None, 0, 2),
    "top_p": ("float", None, 0, 1),
    "max_output_tokens": ("int", None, 1, None),
    "structured_output_mode": ("int", 0, 0, 2),
    "user_thread_counts": ("int", 0, 0, None),
    "smart_round_max_limit": ("int", 10, 1, 100),
}

LEGACY_ALIASES = {
    "threads": "user_thread_counts", "retry": "retry_count", "timeout": "request_timeout",
    "rounds": "round_limit", "pre_lines": "pre_line_counts", "failover": "enable_api_failover",
    "lines": "lines_limit", "tokens": "tokens_limit",
}
INTERFACE_KEYS = frozenset({
    "model", "think_switch", "think_depth", "thinking_budget", "temperature", "top_p",
    "max_output_tokens", "structured_output_mode",
})
CHECK_KEYS = frozenset(_GROUPS["checks"].split()[:4])


def runtime_parameter_schema() -> list[dict]:
    fields = []
    for group, names in _GROUPS.items():
        for key in names.split():
            item = CONFIG_REGISTRY.get(key)
            if key in _EXTRA:
                kind, default, minimum, maximum = _EXTRA[key]
            elif item:
                kind, default = item.config_type.value, item.default
                minimum, maximum = item.min_value, item.max_value
            else:
                raise RuntimeError(f"Missing runtime parameter definition: {key}")
            fields.append({
                "key": key, "group": group, "type": kind, "default": default,
                "minimum": minimum, "maximum": maximum,
                "choices": list(item.choices) if item and kind == "choice" else [],
                "label": item.i18n_key if item else f"runtime_{key}",
                "description": item.i18n_desc_key if item else "",
                "depends_on": item.depends_on if item else None,
                "steps": ["translate"] if key in {"translation_consistency_enhancement", "translation_memory_switch", "rag_enabled", "rag_top_k", "character_recall_switch", "character_recall_context_lines", "character_recall_lookahead_lines", "enable_context_enhancement", "translation_prompt_id", "enable_auto_proofread"} else ["polish"] if key in {"polishing_prompt_id", "polishing_pre_line_counts"} else ["translate", "polish", "extract_glossary", "proofread"],
            })
    return fields


def normalize_runtime_overrides(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise RuntimeOverrideError("runtime_overrides must be a JSON object") from exc
    if not isinstance(value, Mapping):
        raise RuntimeOverrideError("runtime_overrides must be an object")
    schema = {field["key"]: field for field in runtime_parameter_schema()}
    result = {}
    for name, entry in value.items():
        key = LEGACY_ALIASES.get(name, name)
        if key not in schema:
            raise RuntimeOverrideError(f"Unknown runtime parameter: {name}")
        if entry is None:
            continue
        spec = schema[key]
        kind = spec["type"]
        if kind == "bool":
            valid = isinstance(entry, bool)
        elif kind in {"int", "float"}:
            valid = isinstance(entry, (int, float)) and not isinstance(entry, bool) and math.isfinite(entry)
            if kind == "int":
                valid = valid and isinstance(entry, int)
            if valid:
                valid = (spec["minimum"] is None or entry >= spec["minimum"]) and (spec["maximum"] is None or entry <= spec["maximum"])
        elif key == "think_depth" and isinstance(entry, int) and not isinstance(entry, bool):
            valid = 0 <= entry <= 10000
        else:
            valid = isinstance(entry, str) and bool(entry.strip())
            if valid:
                entry = entry.strip()
            if kind == "choice":
                valid = valid and entry in spec["choices"]
        if not valid:
            raise RuntimeOverrideError(f"Invalid value for runtime parameter {key} ({kind})")
        if key in result and result[key] != entry:
            raise RuntimeOverrideError(f"Conflicting values for runtime parameter: {key}")
        result[key] = entry
    return result


def normalize_step_overrides(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise RuntimeOverrideError("step_overrides must be a JSON object") from exc
    if not isinstance(value, Mapping):
        raise RuntimeOverrideError("step_overrides must be an object")
    result = {}
    for step_id, settings in value.items():
        if not isinstance(step_id, str) or not step_id.strip() or not isinstance(settings, Mapping):
            raise RuntimeOverrideError("Each step override requires an ID and an object")
        if set(settings) - {"enabled", "runtime_overrides"}:
            raise RuntimeOverrideError(f"Unknown step override fields: {step_id}")
        prepared = {"runtime_overrides": normalize_runtime_overrides(settings.get("runtime_overrides"))}
        if "enabled" in settings:
            if not isinstance(settings["enabled"], bool):
                raise RuntimeOverrideError(f"Step enabled must be boolean: {step_id}")
            prepared["enabled"] = settings["enabled"]
        result[step_id] = prepared
    return result


def merge_runtime_overrides(*layers: Mapping | None) -> dict:
    result = {}
    for layer in layers:
        prepared = normalize_runtime_overrides(layer)
        # 切换接口时采用新接口默认模型，防止旧接口的模型绑定残留。
        if "platform" in prepared and prepared["platform"] != result.get("platform") and "model" not in prepared:
            result.pop("model", None)
        result.update(prepared)
    return result


def task_runtime_overrides(payload: Mapping) -> dict:
    explicit = normalize_runtime_overrides(payload.get("runtime_overrides"))
    legacy = {}
    for key in (*LEGACY_ALIASES, "platform", "model", "think_depth", "thinking_budget", "lines_limit", "tokens_limit"):
        value = payload.get(key)
        if value is None:
            continue
        target = LEGACY_ALIASES.get(key, key)
        if target == "enable_api_failover" and isinstance(value, str):
            value = value.lower() == "on"
        elif target in {"user_thread_counts", "retry_count", "request_timeout", "round_limit", "pre_line_counts", "lines_limit", "tokens_limit", "thinking_budget"} and isinstance(value, str):
            try:
                value = int(value)
            except ValueError as exc:
                raise RuntimeOverrideError(f"Invalid integer task parameter: {key}") from exc
        if target in explicit and value != explicit[target]:
            raise RuntimeOverrideError(f"Conflicting task and runtime parameter: {target}")
        legacy[target] = value
    if payload.get("lines_limit") is not None or payload.get("lines") is not None:
        if explicit.get("tokens_limit_switch") is True:
            raise RuntimeOverrideError("Line limit conflicts with Token batch mode")
        legacy["tokens_limit_switch"] = False
    if payload.get("tokens_limit") is not None or payload.get("tokens") is not None:
        if explicit.get("tokens_limit_switch") is False:
            raise RuntimeOverrideError("Token limit conflicts with line batch mode")
        legacy["tokens_limit_switch"] = True
    # 旧入口的校验范围保持兼容，新增结构使用注册表范围。
    legacy.update(explicit)
    return legacy


def apply_runtime_overrides(config: Mapping, overrides: Mapping, step_type: str = "translate") -> dict:
    """返回独立配置；调用方在所有资源/规则重载完成后应用显式覆盖。"""
    result = copy.deepcopy(dict(config))
    overrides = dict(overrides)
    inherited_runtime = result.get("_task_runtime_overrides", {})
    role = "polish" if step_type == "polish" else "translate"
    platforms = result.setdefault("platforms", {})
    selected = overrides.get("platform") or result.get("api_settings", {}).get(role) or result.get("target_platform")
    if "platform" in overrides:
        if selected not in platforms:
            raise RuntimeOverrideError(f"Unknown configured interface: {selected}")
        result.setdefault("api_settings", {})[role] = selected
        result["target_platform"] = selected
        if result.get("_runtime_selected_interface") != selected:
            for key in ("model", "base_url", "api_key"):
                result[key] = ""
        result["_runtime_selected_interface"] = selected
    for key, value in overrides.items():
        if key == "platform":
            continue
        if key in CHECK_KEYS:
            result.setdefault("response_check_switch", {})[key] = value
        elif key in INTERFACE_KEYS:
            if selected not in platforms:
                raise RuntimeOverrideError(f"No configured interface for {step_type}")
            platforms[selected][key] = copy.deepcopy(value)
            result[key] = copy.deepcopy(value)
        elif key in {"translation_prompt_id", "polishing_prompt_id"}:
            selection_key = key.replace("_id", "_selection")
            old = result.get(selection_key, {})
            selected_id = int(value) if str(value).isdigit() else value
            if old.get("last_selected_id") == selected_id:
                result[selection_key] = copy.deepcopy(old)
            elif selected_id in (100, 200, 300, 10001):
                result[selection_key] = {"last_selected_id": selected_id, "prompt_content": ""}
            else:
                if os.path.basename(value) != value or "/" in value or "\\" in value:
                    raise RuntimeOverrideError("Prompt must reference an existing prompt filename")
                folder = "Translate" if key.startswith("translation") else "Polishing"
                root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "Resource", "Prompt", folder))
                filename = value if value.endswith((".txt", ".json")) else value + ".txt"
                with open(os.path.join(root, filename), encoding="utf-8-sig") as reader:
                    content = reader.read()
                result[selection_key] = {"last_selected_id": value.removesuffix(".txt"), "prompt_content": content}
        else:
            result[key] = copy.deepcopy(value)
    if "pre_line_counts" in overrides and role == "polish" and "polishing_pre_line_counts" not in overrides:
        result["polishing_pre_line_counts"] = overrides["pre_line_counts"]
    if selected in platforms and overrides.get("translation_consistency_enhancement") and platforms[selected].get("api_format") != "OpenAI":
        raise RuntimeOverrideError("Translation consistency enhancement requires an OpenAI-compatible Tool Calls interface")
    if selected in platforms and overrides.get("structured_output_mode", 0) and platforms[selected].get("api_format") != "OpenAI":
        raise RuntimeOverrideError("Structured output override requires an OpenAI-compatible interface")
    if selected in platforms and overrides.get("think_switch") is False:
        extra = platforms[selected].get("extra_body")
        if isinstance(extra, dict):
            for parameter in ("thinking", "reasoning", "reasoning_effort", "thinking_budget"):
                extra.pop(parameter, None)
    if overrides:
        result["_task_runtime_overrides"] = {**copy.deepcopy(inherited_runtime), **copy.deepcopy(overrides)}
    return result


def apply_host_runtime(host, payload: Mapping, step_type: str = "translate") -> dict:
    overrides = task_runtime_overrides(payload)
    host.config = apply_runtime_overrides(host.config, overrides, step_type)
    return overrides


def apply_openai_runtime_request(request: dict, platform_config: Mapping) -> None:
    """在接口扩展字段合并之后应用用户明确指定的生成参数。"""
    runtime = platform_config.get("runtime_overrides", {})
    for key in ("temperature", "top_p"):
        if key in runtime:
            request[key] = runtime[key]
    mode = runtime.get("structured_output_mode")
    if mode == 0:
        request.pop("response_format", None)
    elif mode == 1:
        request["response_format"] = {"type": "json_object"}
    elif mode == 2 and request.get("response_format", {}).get("type") != "json_schema":
        raise RuntimeOverrideError("JSON Schema output requires response_format.json_schema in the interface settings")
    if runtime.get("think_switch") is False:
        request.pop("reasoning_effort", None)
        if "deepseek" not in str(platform_config.get("model_name", "")).lower():
            request["reasoning_effort"] = "none"
    maximum = runtime.get("max_output_tokens")
    if maximum is not None:
        if "max_completion_tokens" in request:
            request["max_completion_tokens"] = maximum
            request.pop("max_tokens", None)
        else:
            request["max_tokens"] = maximum
