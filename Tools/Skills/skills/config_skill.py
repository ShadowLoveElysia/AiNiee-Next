from __future__ import annotations

from typing import Any, Dict

from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    normalize_skill_action,
    reject_unknown_skill_fields,
)
from Tools.Skills.skills.common import (
    active_profile_name,
    atomic_write_json,
    load_dict_json,
    load_root_config,
    prepare_config_value_for_save,
    resolve_config_profile_path,
    sanitize_config_value,
)


_MISSING = object()


class ConfigSkill(Skill):
    @staticmethod
    def _string_argument(args: Dict[str, Any], name: str, *, required: bool = False) -> str | None | SkillResult:
        value = args.get(name)
        if value is None or value == "":
            if required:
                return SkillResult.fail(
                    f"Missing required parameter: {name}", "MISSING_PARAM"
                )
            return None
        if not isinstance(value, str):
            return SkillResult.fail(f"{name} must be a string.", "INVALID_ARGUMENTS")
        value = value.strip()
        if required and not value:
            return SkillResult.fail(
                f"Missing required parameter: {name}", "MISSING_PARAM"
            )
        return value

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="config",
            description="Read and write AiNiee profile configuration.",
            category="config",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: get, set, list_keys.",
                    type="string",
                    required=True,
                    enum=["get", "set", "list_keys"],
                ),
                SkillParameter(
                    name="key",
                    description="Configuration key to read or write.",
                    type="string",
                    required=False,
                ),
                SkillParameter(
                    name="value",
                    description="Value to set (for set action).",
                    type="object",
                    required=False,
                ),
                SkillParameter(
                    name="profile",
                    description="Profile name (defaults to active profile).",
                    type="string",
                    required=False,
                ),
            ],
            examples=[
                {"action": "get", "key": "model"},
                {"action": "get", "key": "target_platform"},
                {"action": "list_keys"},
                {"action": "set", "key": "model", "value": "gpt-4o-mini"},
            ],
        )

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        invalid = reject_unknown_skill_fields(
            args, {"action", "key", "value", "profile"}, skill_name="config"
        )
        if invalid:
            return invalid
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        if action == "list_keys":
            try:
                path, profile = resolve_config_profile_path(args.get("profile"))
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")
            cfg = load_dict_json(path)
            return SkillResult.ok({
                "profile": profile,
                "keys": sorted(cfg.keys()),
            })

        if action == "get":
            key = self._string_argument(args, "key", required=True)
            if isinstance(key, SkillResult):
                return key
            try:
                path, profile = resolve_config_profile_path(args.get("profile"))
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")

            cfg = load_dict_json(path)
            value = cfg.get(key, _MISSING)
            source = "profile"
            if value is _MISSING:
                root = load_root_config()
                value = root.get(key, _MISSING)
                source = "root"

            found = value is not _MISSING
            exposed_value = None if not found else sanitize_config_value(value, key)
            return SkillResult.ok({
                "profile": profile,
                "key": key,
                "value": exposed_value,
                "found": found,
                "source": source if found else None,
            })

        if action == "set":
            key = self._string_argument(args, "key", required=True)
            if isinstance(key, SkillResult):
                return key
            if "value" not in args:
                return SkillResult.fail("Missing required parameter: value", "MISSING_PARAM")
            try:
                profile_arg = (
                    args.get("profile")
                    if "profile" in args
                    else active_profile_name()
                )
                path, profile = resolve_config_profile_path(profile_arg)
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")

            cfg = load_dict_json(path)
            try:
                value = prepare_config_value_for_save(args["value"], cfg.get(key), key)
            except ValueError as e:
                return SkillResult.fail(str(e), "REDACTED_SECRET")

            cfg[key] = value
            try:
                atomic_write_json(path, cfg)
                return SkillResult.ok({
                    "profile": profile,
                    "key": key,
                    "value": sanitize_config_value(value, key),
                    "saved": True,
                })
            except Exception as e:
                return SkillResult.fail(f"Failed to write config: {e}", "WRITE_ERROR")

        return SkillResult.fail(f"Unknown config action: {action}", "INVALID_ACTION")
