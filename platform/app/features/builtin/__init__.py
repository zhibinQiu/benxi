"""Built-in feature plugins; add new modules here and import in register_builtin_plugins."""

from __future__ import annotations


def register_builtin_plugins() -> None:
    # Side-effect registration on import
    from app.features.builtin import ai_home  # noqa: F401
    from app.features.builtin import ai_tools  # noqa: F401
    from app.features.builtin import assist_writing  # noqa: F401
    from app.features.builtin import carbon_ai_v1  # noqa: F401
    from app.features.builtin import carbon_platform_v3  # noqa: F401
    from app.features.builtin import carbon_asset_trading  # noqa: F401
    from app.features.builtin import carbon_qa_v2  # noqa: F401 — 注册 id=carbon_qa
    from app.features.builtin import compare  # noqa: F401
    from app.features.builtin import data_analysis  # noqa: F401
    from app.features.builtin import external_links  # noqa: F401
    from app.features.builtin import ocr  # noqa: F401
    from app.features.builtin import rag  # noqa: F401
    from app.features.builtin import knowledge_search  # noqa: F401
    from app.features.builtin import smart_data_query_v2  # noqa: F401 — 注册 id=smart_data_query
    from app.features.builtin import smart_forecast  # noqa: F401
    from app.features.builtin import speech  # noqa: F401
    from app.features.builtin import stubs  # noqa: F401
    from app.features.builtin import subscriptions  # noqa: F401
    from app.features.builtin import wechat_mp_feed  # noqa: F401
    from app.features.builtin import feed_subscriptions  # noqa: F401
    from app.features.builtin import translate  # noqa: F401
