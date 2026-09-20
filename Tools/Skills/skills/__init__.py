"""Skill implementations for AiNiee Skills."""

from Tools.Skills.skill_base import SkillRegistry
from Tools.Skills.skills.system_skill import SystemSkill
from Tools.Skills.skills.config_skill import ConfigSkill
from Tools.Skills.skills.translate_skill import TranslateSkill
from Tools.Skills.skills.queue_skill import QueueSkill
from Tools.Skills.skills.profile_skill import ProfileSkill
from Tools.Skills.skills.file_skill import FileSkill
from Tools.Skills.skills.agent_skill import AgentSkill


def build_registry() -> SkillRegistry:
    """Create and populate the global skill registry."""
    registry = SkillRegistry()
    registry.register(SystemSkill())
    registry.register(ConfigSkill())
    registry.register(TranslateSkill())
    registry.register(QueueSkill())
    registry.register(ProfileSkill())
    registry.register(FileSkill())
    registry.register(AgentSkill())
    return registry
