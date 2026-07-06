"""Pluggable platform features (routes, permissions, system catalog)."""

from app.features.base import FeaturePlugin
from app.features.registry import all_plugins, ensure_plugins_loaded, register

__all__ = ["FeaturePlugin", "all_plugins", "ensure_plugins_loaded", "register"]
