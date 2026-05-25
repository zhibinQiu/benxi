"""Built-in feature plugins; add new modules here and import in register_builtin_plugins."""

from __future__ import annotations


def register_builtin_plugins() -> None:
    # Side-effect registration on import
    from app.features.builtin import ai_tools  # noqa: F401
    from app.features.builtin import assist_writing  # noqa: F401
    from app.features.builtin import carbon_ai_v1  # noqa: F401
    from app.features.builtin import carbon_platform_v3  # noqa: F401
    from app.features.builtin import carbon_qa  # noqa: F401
    from app.features.builtin import compare  # noqa: F401
    from app.features.builtin import external_links  # noqa: F401
    from app.features.builtin import ocr  # noqa: F401
    from app.features.builtin import rag  # noqa: F401
    from app.features.builtin import smart_data_query  # noqa: F401
    from app.features.builtin import smart_forecast  # noqa: F401
    from app.features.builtin import speech  # noqa: F401
    from app.features.builtin import stubs  # noqa: F401
    from app.features.builtin import translate  # noqa: F401
