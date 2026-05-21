"""Built-in feature plugins; add new modules here and import in register_builtin_plugins."""

from __future__ import annotations


def register_builtin_plugins() -> None:
    # Side-effect registration on import
    from app.features.builtin import stubs  # noqa: F401
    from app.features.builtin import translate  # noqa: F401
