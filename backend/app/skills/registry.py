"""Skill 注册表 — agentkit LazySkillRegistry 适配。"""

from __future__ import annotations

from app.agentkit.skills.registry import get_default_registry, set_registry_loader

from app.skills.types import SkillDefinition, SkillSource

_registry = get_default_registry()


def register_skill(defn: SkillDefinition) -> None:
    _registry.register(defn)


def get_skill(name: str) -> SkillDefinition | None:
    return _registry.get(name)


def all_builtin_skills() -> list[SkillDefinition]:
    return sorted(
        [s for s in _registry.builtins() if s.source == SkillSource.BUILTIN],
        key=lambda s: s.name,
    )


def all_registered_skills() -> list[SkillDefinition]:
    return _registry.all()


def ensure_skills_loaded() -> None:
    _registry.all()


def _load_builtin_skills() -> None:
    from app.skills.builtin import register_builtin_skills

    register_builtin_skills()


set_registry_loader(_load_builtin_skills)
