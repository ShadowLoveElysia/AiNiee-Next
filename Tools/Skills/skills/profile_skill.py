from __future__ import annotations

import os
from typing import Any, Dict, List

from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    normalize_skill_action,
    reject_unknown_skill_fields,
)
from Tools.Skills.skills.common import (
    PROFILES_PATH,
    atomic_write_json,
    list_profile_names,
    load_dict_json,
    load_root_config,
    resolve_profile_path,
    save_root_config,
)
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    PROFILE_ORIGIN_KEY,
    load_effective_config,
    profile_origin_for_new_profile,
)


class ProfileSkill(Skill):
    @staticmethod
    def _profile_argument(
        args: Dict[str, Any], name: str, *, default: str | None = None
    ) -> str | SkillResult:
        value = args.get(name)
        if value is None or value == "":
            if default is not None:
                return default
            return SkillResult.fail(
                f"Missing required parameter: {name}", "MISSING_PARAM"
            )
        if not isinstance(value, str):
            return SkillResult.fail(f"{name} must be a string.", "INVALID_ARGUMENTS")
        value = value.strip()
        if not value:
            if default is not None:
                return default
            return SkillResult.fail(
                f"Missing required parameter: {name}", "MISSING_PARAM"
            )
        return value

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="profile",
            description="Manage AiNiee configuration profiles.",
            category="config",
            parameters=[
                SkillParameter(
                    name="action",
                    description="Operation: list, switch, create, delete, current.",
                    type="string",
                    required=True,
                    enum=["list", "switch", "create", "delete", "current"],
                ),
                SkillParameter(
                    name="name",
                    description="Profile name (for switch/create/delete).",
                    type="string",
                    required=False,
                ),
                SkillParameter(
                    name="base",
                    description="Base profile to copy from (for create).",
                    type="string",
                    required=False,
                ),
            ],
            examples=[
                {"action": "list"},
                {"action": "current"},
                {"action": "switch", "name": "my-profile"},
                {"action": "create", "name": "new-profile", "base": "default"},
                {"action": "delete", "name": "old-profile"},
            ],
        )

    def _list_profiles(self) -> List[str]:
        return list_profile_names(PROFILES_PATH)

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        invalid = reject_unknown_skill_fields(
            args, {"action", "name", "base"}, skill_name="profile"
        )
        if invalid:
            return invalid
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        if action == "list":
            profiles = self._list_profiles()
            root = load_root_config()
            active = root.get("active_profile", "default")
            return SkillResult.ok({
                "profiles": profiles,
                "active": active,
                "count": len(profiles),
            })

        if action == "current":
            root = load_root_config()
            active = root.get("active_profile", "default")
            rules_active = root.get("active_rules_profile", "default")
            return SkillResult.ok({
                "active_profile": active,
                "active_rules_profile": rules_active,
            })

        if action == "switch":
            name = self._profile_argument(args, "name")
            if isinstance(name, SkillResult):
                return name
            try:
                _, name = resolve_profile_path(PROFILES_PATH, name)
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")
            profiles = self._list_profiles()
            if name not in profiles:
                return SkillResult.fail(
                    f"Profile '{name}' not found. Available: {', '.join(profiles)}",
                    "NOT_FOUND",
                )
            root = load_root_config()
            previous = root.get("active_profile", "default")
            root["active_profile"] = name
            try:
                save_root_config(root)
                return SkillResult.ok({
                    "switched": True,
                    "profile": name,
                    "previous": previous,
                })
            except Exception as e:
                return SkillResult.fail(f"Failed to save config: {e}", "WRITE_ERROR")

        if action == "create":
            name = self._profile_argument(args, "name")
            if isinstance(name, SkillResult):
                return name
            try:
                profile_path, name = resolve_profile_path(PROFILES_PATH, name)
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")
            if os.path.exists(profile_path):
                return SkillResult.fail(f"Profile '{name}' already exists.", "ALREADY_EXISTS")

            base = self._profile_argument(args, "base", default="default")
            if isinstance(base, SkillResult):
                return base
            try:
                base_path, base = resolve_profile_path(PROFILES_PATH, base)
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")
            if os.path.isfile(base_path):
                try:
                    base_data = load_dict_json(base_path)
                    base_data[PROFILE_ORIGIN_KEY] = profile_origin_for_new_profile(
                        load_effective_config(create_missing=False)
                    )
                    atomic_write_json(profile_path, base_data or {})
                except Exception as e:
                    return SkillResult.fail(f"Failed to create profile: {e}", "CREATE_ERROR")
            else:
                try:
                    profile_data = {
                        PROFILE_ORIGIN_KEY: profile_origin_for_new_profile(
                            load_effective_config(create_missing=False)
                        )
                    }
                    atomic_write_json(profile_path, profile_data)
                except Exception as e:
                    return SkillResult.fail(f"Failed to create profile: {e}", "CREATE_ERROR")

            return SkillResult.ok({
                "created": True,
                "profile": name,
                "based_on": base if os.path.isfile(base_path) else None,
            })

        if action == "delete":
            name = self._profile_argument(args, "name")
            if isinstance(name, SkillResult):
                return name
            try:
                profile_path, name = resolve_profile_path(PROFILES_PATH, name)
            except ValueError as e:
                return SkillResult.fail(str(e), "INVALID_PROFILE")
            if name == "default":
                return SkillResult.fail("Cannot delete the default profile.", "PROTECTED")

            if not os.path.isfile(profile_path):
                return SkillResult.fail(f"Profile '{name}' not found.", "NOT_FOUND")

            root = load_root_config()
            if root.get("active_profile") == name:
                root["active_profile"] = "default"
                try:
                    save_root_config(root)
                except Exception as e:
                    return SkillResult.fail(f"Failed to save config: {e}", "WRITE_ERROR")

            try:
                os.remove(profile_path)
                return SkillResult.ok({"deleted": True, "profile": name})
            except OSError as e:
                return SkillResult.fail(f"Failed to delete profile: {e}", "DELETE_ERROR")

        return SkillResult.fail(f"Unknown profile action: {action}", "INVALID_ACTION")
