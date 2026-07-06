"""Central feature plugin registry."""

from __future__ import annotations

from fastapi import FastAPI

from app.features.base import FeaturePlugin

_REGISTRY: dict[str, FeaturePlugin] = {}
_LOADED = False


def register(plugin: FeaturePlugin) -> None:
    if plugin.id in _REGISTRY:
        raise ValueError(f"Duplicate feature plugin id: {plugin.id}")
    _REGISTRY[plugin.id] = plugin


def get_plugin(feature_id: str) -> FeaturePlugin | None:
    return _REGISTRY.get(feature_id)


def all_plugins() -> list[FeaturePlugin]:
    return sorted(_REGISTRY.values(), key=lambda p: (p.sort_order, p.id))


def feature_permission_codes() -> list[tuple[str, str]]:
    """(code, display_name) for RBAC seed."""
    return [(p.permission_code, p.permission_name) for p in all_plugins()]


def default_role_feature_permissions(role_code: str) -> list[str]:
    return [
        p.permission_code
        for p in all_plugins()
        if role_code in p.grant_to_roles
    ]


def mount_routers(app: FastAPI, api_prefix: str) -> None:
    for plugin in all_plugins():
        if plugin.router is not None and plugin.enabled:
            app.include_router(plugin.router, prefix=api_prefix)


def _load_builtin() -> None:
    from app.features.builtin import register_builtin_plugins

    register_builtin_plugins()


def ensure_plugins_loaded() -> None:
    global _LOADED
    if not _LOADED:
        _load_builtin()
        _LOADED = True
