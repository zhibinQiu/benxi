"""Skill 注册表 — 进程内插件注册，无 DB 依赖。"""

from __future__ import annotations

from collections.abc import Callable

from agentkit_skills.types import SkillDefinition, SkillSource


class SkillRegistry:
    """可实例化的 Skill 注册表（支持测试隔离或多租户场景）。"""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def _ensure_loaded(self) -> None:
        """子类可覆盖实现延迟加载；基类为空操作。"""

    def register(self, defn: SkillDefinition) -> None:
        if defn.name in self._skills:
            raise ValueError(f"Duplicate skill name: {defn.name}")
        self._skills[defn.name] = defn

    def get(self, name: str) -> SkillDefinition | None:
        self._ensure_loaded()
        return self._skills.get(name)

    def all(self) -> list[SkillDefinition]:
        self._ensure_loaded()
        return sorted(self._skills.values(), key=lambda s: s.name)

    def builtins(self) -> list[SkillDefinition]:
        self._ensure_loaded()
        return sorted(
            [s for s in self._skills.values() if s.source == SkillSource.BUILTIN],
            key=lambda s: s.name,
        )

    def values(self) -> list[SkillDefinition]:
        self._ensure_loaded()
        return list(self._skills.values())


class LazySkillRegistry(SkillRegistry):
    """带 lazy loader 的注册表（宿主注册 builtin 时使用）。"""

    def __init__(self, loader: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._loader = loader
        self._loaded = False

    def set_loader(self, loader: Callable[[], None]) -> None:
        """设置延迟加载器（替代直接设置私有属性）。"""
        self._loader = loader

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            if self._loader is not None:
                self._loader()


_default_registry = LazySkillRegistry()


def register_skill(defn: SkillDefinition, *, registry: SkillRegistry | None = None) -> None:
    (registry or _default_registry).register(defn)


def get_skill(name: str, *, registry: SkillRegistry | None = None) -> SkillDefinition | None:
    return (registry or _default_registry).get(name)


def all_registered_skills(*, registry: SkillRegistry | None = None) -> list[SkillDefinition]:
    return (registry or _default_registry).all()


def get_default_registry() -> LazySkillRegistry:
    return _default_registry


def set_registry_loader(loader: Callable[[], None]) -> None:
    _default_registry.set_loader(loader)
