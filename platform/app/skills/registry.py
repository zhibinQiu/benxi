"""Skill 注册表 — 内置 + 上传双源聚合。"""

from __future__ import annotations

from app.skills.types import SkillDefinition

_REGISTRY: dict[str, SkillDefinition] = {}
_LOADED = False


def register_skill(defn: SkillDefinition) -> None:
    if defn.name in _REGISTRY:
        raise ValueError(f"Duplicate skill name: {defn.name}")
    _REGISTRY[defn.name] = defn


def get_skill(name: str) -> SkillDefinition | None:
    _ensure_loaded()
    return _REGISTRY.get(name)


def all_builtin_skills() -> list[SkillDefinition]:
    _ensure_loaded()
    from app.skills.types import SkillSource

    return sorted(
        [s for s in _REGISTRY.values() if s.source == SkillSource.BUILTIN],
        key=lambda s: s.name,
    )


def all_registered_skills() -> list[SkillDefinition]:
    _ensure_loaded()
    return sorted(_REGISTRY.values(), key=lambda s: s.name)


def _ensure_loaded() -> None:
    global _LOADED
    if not _LOADED:
        from app.skills.builtin import register_builtin_skills

        register_builtin_skills()
        _LOADED = True


def ensure_skills_loaded() -> None:
    _ensure_loaded()
