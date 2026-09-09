from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class SkillError(Exception):
    """Raised when a skill execution fails for a known reason."""

    def __init__(self, message: str, code: str = "SKILL_ERROR") -> None:
        self.code = code
        super().__init__(message)


class SkillResult:
    """Wrapper for skill execution results."""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
        error_code: str = "",
    ) -> None:
        self.success = success
        self.data = data
        self.error = error
        self.error_code = error_code

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"success": self.success}
        if self.data is not None:
            d["data"] = self.data
        if self.error:
            d["error"] = self.error
            d["error_code"] = self.error_code
        return d

    @classmethod
    def ok(cls, data: Any = None) -> SkillResult:
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        message: str,
        code: str = "SKILL_ERROR",
        data: Any = None,
    ) -> SkillResult:
        return cls(success=False, data=data, error=message, error_code=code)


def normalize_skill_payload(payload: Any) -> Dict[str, Any]:
    """Normalize the shared bare/wrapped JSON request shape.

    Both the HTTP and standalone CLI entry points accept either a bare object
    (``{"action": "ping"}``) or an explicit ``{"args": {...}}`` wrapper.
    Mixing wrapper and sibling fields is rejected so callers cannot receive
    different semantics depending on which entry point they use.
    """
    if not isinstance(payload, dict):
        raise SkillError("Skill arguments must be a JSON object.", "INVALID_ARGUMENTS")
    if "args" not in payload:
        return dict(payload)
    if set(payload) != {"args"} or not isinstance(payload["args"], dict):
        raise SkillError(
            "The wrapped skill request must contain only an object-valued 'args' field.",
            "INVALID_ARGUMENTS",
        )
    return dict(payload["args"])


def normalize_skill_action(args: Dict[str, Any], *, default: str = "") -> str | None:
    """Return a normalized action or ``None`` when the caller sent a bad type."""
    value = default if "action" not in args else args["action"]
    if not isinstance(value, str):
        return None
    return value.strip().lower()


def reject_unknown_skill_fields(
    args: Dict[str, Any],
    allowed: set[str],
    *,
    skill_name: str,
) -> SkillResult | None:
    """Keep a Skill action strict without importing business dependencies."""
    unexpected = sorted(set(args) - allowed)
    if unexpected:
        return SkillResult.fail(
            f"Unknown {skill_name} fields: {', '.join(unexpected)}",
            "INVALID_ARGUMENTS",
        )
    return None


@dataclass
class SkillParameter:
    """Describes a single input parameter for a skill."""

    name: str
    description: str = ""
    type: str = "string"  # string / integer / boolean / object / array
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class SkillMeta:
    """Metadata describing a skill."""

    name: str
    description: str
    category: str = "general"
    parameters: List[SkillParameter] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in self.parameters
            ],
            "examples": self.examples,
        }


class Skill(abc.ABC):
    """Base class for all skills."""

    def __init__(self) -> None:
        self._meta: Optional[SkillMeta] = None

    @property
    @abc.abstractmethod
    def meta(self) -> SkillMeta:
        ...

    @abc.abstractmethod
    def execute(self, args: Dict[str, Any]) -> SkillResult:
        ...


class SkillRegistry:
    """Registry of all available skills."""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        name = skill.meta.name
        if name in self._skills:
            raise SkillError(f"Duplicate skill registration: {name}", "DUPLICATE_SKILL")
        self._skills[name] = skill

    def get(self, name: str) -> Skill:
        skill = self._skills.get(name)
        if skill is None:
            raise SkillError(f"Unknown skill: {name}", "UNKNOWN_SKILL")
        return skill

    def list_skills(self) -> List[Dict[str, Any]]:
        return [s.meta.to_dict() for s in self._skills.values()]

    def get_skill_meta(self, name: str) -> Dict[str, Any]:
        return self.get(name).meta.to_dict()

    def execute(self, name: str, args: Dict[str, Any]) -> SkillResult:
        try:
            normalized_args = normalize_skill_payload(args)
        except SkillError as exc:
            return SkillResult.fail(str(exc), exc.code)
        if "action" in normalized_args and not isinstance(normalized_args["action"], str):
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")
        try:
            skill = self.get(name)
            return skill.execute(normalized_args)
        except SkillError as exc:
            # Skills may raise a structured validation error from a shared
            # helper (for example, the workspace path policy). Keep HTTP, CLI,
            # and direct registry callers on the same result contract.
            return SkillResult.fail(str(exc), exc.code)

    @property
    def count(self) -> int:
        return len(self._skills)
