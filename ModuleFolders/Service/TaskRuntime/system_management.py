"""System management use cases shared by non-interactive adapters."""
from dataclasses import asdict
import hashlib
from pathlib import Path

from ModuleFolders.Infrastructure.TaskConfig import ConfigProfileService as profiles
from ModuleFolders.Infrastructure.ApiSecurity import (
    contains_redacted_secret, restore_redacted_secrets, sanitize_data_for_mcp,
)
from ModuleFolders.Infrastructure.SensitiveData import is_sensitive_field, sanitize_sensitive_data, split_sensitive_data
from ModuleFolders.Service.TaskRuntime.configuration import authorize_configuration_changes, update_configuration


def settings_schema():
    from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import get_user_visible_configs
    return [{"key": item.key, "default": sanitize_sensitive_data(item.default), "level": item.level.name.lower(),
             "type": item.config_type.value, "category": item.category, "label_key": item.i18n_key,
             "description_key": item.i18n_desc_key, "choices": item.choices,
             "minimum": item.min_value, "maximum": item.max_value,
             "depends_on": item.depends_on, "submenu": item.submenu, "online_only": item.online_only}
            for item in get_user_visible_configs() if not is_sensitive_field(item.key)]


def validate_settings(values):
    from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import get_config_item, validate_config_value
    errors = {}
    for key, value in values.items():
        item = get_config_item(key)
        if item is not None:
            kind = item.config_type.value
            valid_type = {
                "int": lambda: type(value) is int,
                "float": lambda: type(value) in (int, float),
                "bool": lambda: type(value) is bool,
                "string": lambda: isinstance(value, str),
                "path": lambda: isinstance(value, str),
                "list": lambda: isinstance(value, list),
                "dict": lambda: value is None or isinstance(value, dict),
            }.get(kind)
            if valid_type and not valid_type():
                errors[key] = f"Expected {kind}"
                continue
        valid, message = validate_config_value(key, value)
        if not valid:
            errors[key] = message
        elif key == "ebook_name_template":
            from ModuleFolders.Domain.FileOutputer.EbookNaming import EbookIdentity, render_ebook_name
            try:
                render_ebook_name(value, EbookIdentity(str(values.get("ebook_series_name") or "Example"), "1"))
            except ValueError as exc:
                errors[key] = str(exc)
    return {"valid": not errors, "errors": errors}


def platform_summaries():
    config = profiles.load_effective_config(create_missing=False)
    selected = config.get("api_settings", {})
    return [{"name": name, "local": name.lower() in {"localllm", "sakura", "murasaki"},
             "group": str(data.get("group", "")), "api_format": str(data.get("api_format", "")),
             "model": str(data.get("model", "")),
             "selected_for": [kind for kind, value in selected.items() if value == name]}
            for name, data in config.get("platforms", {}).items() if isinstance(data, dict)]


def select_platform(name, task, model, revision, caller):
    with profiles.config_transaction():
        config = profiles.load_effective_config(create_missing=False)
        if name not in config.get("platforms", {}):
            raise KeyError("Unknown platform")
        platform = dict(config["platforms"][name])
        if model is not None:
            platform["model"] = model
        selected = dict(config.get("api_settings", {}))
        selected.update({kind: name for kind in (("translate", "polish") if task == "both" else (task,))})
        changes = {"api_settings": selected, "platforms": {name: platform}}
        if task in {"translate", "both"}:
            changes.update(target_platform=name, model=platform.get("model", ""),
                           base_url=platform.get("api_url", ""), api_key=platform.get("api_key", ""))
        if revision is not None:
            changes["_config_revision"] = revision
        return update_configuration(changes, caller)


def import_platform_keys(name, text, revision, caller):
    from ModuleFolders.UserInterface.APIManager import parse_api_keys_from_text, serialize_api_keys_for_config
    keys = parse_api_keys_from_text(text)
    if not keys or any(contains_redacted_secret({"api_key": key}) for key in keys):
        raise ValueError("Provide one or more actual API keys")
    with profiles.config_transaction():
        current = profiles.load_effective_config(create_missing=False)
        if name not in current.get("platforms", {}):
            raise KeyError("Unknown platform")
        changes = {"platforms": {name: {"api_key": serialize_api_keys_for_config(keys)}}}
        if current.get("target_platform") == name:
            changes["api_key"] = serialize_api_keys_for_config(keys)
        if revision is not None:
            changes["_config_revision"] = revision
        return update_configuration(changes, caller)


def _platform_config(name):
    from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
    from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
    config = profiles.load_effective_config(create_missing=False)
    if name is not None:
        if name not in config.get("platforms", {}):
            raise KeyError("Unknown platform")
        config["target_platform"] = name
        config["api_settings"] = {"translate": name, "polish": name}
        selected = config["platforms"][name]
        config.update(model=selected.get("model", ""), api_key=selected.get("api_key", ""),
                      base_url=selected.get("api_url", ""))
    config["user_thread_counts"] = 1
    task = TaskConfig()
    task.initialize(config)
    task.prepare_for_translation(TaskType.TRANSLATION)
    platform = task.get_platform_configuration("translationReq")
    platform["max_tokens"] = 100
    platform["request_timeout"] = min(float(platform.get("request_timeout") or 20), 20)
    platform["runtime_overrides"] = {"retry_count": 1, "enable_retry_backoff": False}
    return platform


def validate_platform(name, cancel):
    from ModuleFolders.Base.Base import Base
    from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
    from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob
    if cancel.is_set():
        raise CancelledJob()
    with Base.independent_request_scope(cancel):
        skip, _, content, input_tokens, output_tokens = LLMRequester().sent_request(
            [{"role": "user", "content": "Reply with OK."}], "", _platform_config(name),
        )
    if skip:
        raise RuntimeError("The configured platform validation request failed")
    return {"success": bool(content), "input_tokens": input_tokens, "output_tokens": output_tokens}


def platform_models(name, cancel):
    from ModuleFolders.Infrastructure.LLMRequester.ModelDiscovery import discover_models
    from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob
    if cancel.is_set():
        raise CancelledJob()
    platform = _platform_config(name)
    return {"models": discover_models(platform, platform.get("api_format", "OpenAI"))}


def knowledge_base(language):
    from ModuleFolders.Diagnostic.KnowledgeBase import KnowledgeBase
    return KnowledgeBase(base_path=str(Path(profiles.RESOURCE_PATH) / "Diagnostic"), lang=language, read_only=True)


def diagnostic_knowledge(language, query, category, limit):
    knowledge = knowledge_base(language)
    matches = knowledge.search_by_keywords(query, top_k=limit) if query else [
        (item, None) for item in knowledge.knowledge_items.values()
    ]
    return [{key: value for key, value in {**asdict(item), "score": score}.items() if key != "hit_count"}
            for item, score in matches if category is None or item.category == category][:limit]


def diagnose(error_text, language, allow_llm, cancel):
    from ModuleFolders.Base.Base import Base
    from ModuleFolders.Diagnostic.SmartDiagnostic import DiagnosticConfig, SmartDiagnostic
    from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob
    if cancel.is_set():
        raise CancelledJob()
    config = profiles.load_effective_config(create_missing=False)
    _, secret_values = split_sensitive_data(config)
    def redact(value):
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if not isinstance(value, str):
            return value
        pending = [secret_values]
        while pending:
            secret = pending.pop()
            if isinstance(secret, dict):
                pending.extend(secret.values())
            elif isinstance(secret, (list, tuple)):
                pending.extend(secret)
            elif isinstance(secret, str) and len(secret) >= 4:
                value = value.replace(secret, "[REDACTED]")
        return value
    engine = SmartDiagnostic(DiagnosticConfig(enable_llm=allow_llm, cache_llm_results=False),
                             lang=language, knowledge_base=knowledge_base(language))
    with Base.independent_request_scope(cancel):
        return redact(asdict(engine.diagnose(redact(error_text), {"allow_llm": allow_llm, "config": config})))


def _recent_payload(config):
    from ModuleFolders.UserInterface.RecentProjectsMenu import normalize_recent_item
    return {"projects": [normalize_recent_item(item) for item in config.get("recent_projects", [])],
            "revision": profiles.config_revision(config)}


def recent_projects():
    with profiles.config_transaction():
        return _recent_payload(profiles.load_effective_config(create_missing=False))


def save_recent_projects(items, revision, caller):
    with profiles.config_transaction():
        for item in items:
            if not item["path"].strip():
                raise ValueError("Recent project path cannot be empty")
            profiles.resolve_profile_path(profiles.PROFILES_PATH, item["profile"])
            profiles.resolve_profile_path(profiles.RULES_PROFILES_PATH, item["rules_profile"], allow_none=True)
        pinned = [item for item in items if item["pinned"]]
        normal = [item for item in items if not item["pinned"]]
        update_configuration({"recent_projects": pinned + normal[:max(0, 10 - len(pinned))],
                              "_config_revision": revision}, caller)
        return recent_projects()


def clean_recent_projects(revision, caller):
    with profiles.config_transaction():
        items = recent_projects()["projects"]
        return save_recent_projects([item for item in items if item["pinned"] or Path(item["path"]).exists()], revision, caller)


def recent_project_task(path, revision):
    with profiles.config_transaction():
        snapshot = recent_projects()
        if revision != snapshot["revision"]:
            raise profiles.ConfigConflictError()
        item = next((item for item in snapshot["projects"] if item["path"] == path), None)
        if item is None:
            raise KeyError("Recent project no longer exists")
        if not Path(path).exists():
            raise FileNotFoundError("Recent project input is missing")
        return {"input_path": path, "profile": item["profile"], "rules_profile": item["rules_profile"]}


def _profile_path(name):
    path, name = profiles.resolve_profile_path(profiles.PROFILES_PATH, name)
    root = Path(profiles.PROFILES_PATH).resolve()
    if Path(path).is_symlink() or Path(path).resolve().parent != root:
        raise ValueError("Profile must be a regular file in the settings profile directory")
    return Path(path), name


def _document_revision(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def profile_document(name, caller):
    with profiles.config_transaction():
        path, name = _profile_path(name)
        if not path.is_file():
            raise FileNotFoundError("Profile not found")
        content = profiles.load_json_file(str(path), {})
        if caller.channel == "mcp":
            content = sanitize_data_for_mcp(content, path="/api/config")
        return {"kind": "settings", "name": name, "content": content, "revision": _document_revision(path)}


def save_profile_document(name, content, revision, caller):
    from ModuleFolders.Infrastructure.TaskConfig.AgentBatchSettings import (
        AGENT_MAX_BATCHES_KEY, DEFAULT_AGENT_MAX_BATCHES, validate_agent_max_batches,
    )
    from ModuleFolders.Infrastructure.ApiSecurity import strip_mcp_security_metadata
    with profiles.config_transaction():
        path, name = _profile_path(name)
        if revision != _document_revision(path):
            raise profiles.ConfigConflictError()
        current = profiles.load_json_file(str(path), {})
        content = strip_mcp_security_metadata(content)
        policy_changes = dict(content)
        for key in ("mcp_server_host", "mcp_server_port"):
            if content.get(key) == current.get(key):
                policy_changes.pop(key, None)
            elif key not in content:
                policy_changes[key] = None
        if AGENT_MAX_BATCHES_KEY in current and AGENT_MAX_BATCHES_KEY not in content:
            policy_changes[AGENT_MAX_BATCHES_KEY] = DEFAULT_AGENT_MAX_BATCHES
        authorize_configuration_changes(policy_changes, caller)
        if AGENT_MAX_BATCHES_KEY in content:
            validate_agent_max_batches(content[AGENT_MAX_BATCHES_KEY])
        if caller.channel == "mcp":
            content = restore_redacted_secrets(content, current)
        if contains_redacted_secret(content):
            raise ValueError("Unresolved secret placeholder")
        # Raw settings documents cannot change root policy or another rules profile.
        content = {key: value for key, value in content.items()
                   if key not in profiles.ROOT_ONLY_KEYS and key not in profiles.RULE_PROFILE_KEYS and key != "_config_revision"}
        if "enable_remote_access" in current:
            content["enable_remote_access"] = current["enable_remote_access"]
        else:
            content.pop("enable_remote_access", None)
        content[profiles.PROFILE_ORIGIN_KEY] = current.get(
            profiles.PROFILE_ORIGIN_KEY, profiles.profile_origin_for_new_profile(profiles.load_root_config()),
        )
        profiles.atomic_write_json(str(path), content)
        return profile_document(name, caller)
