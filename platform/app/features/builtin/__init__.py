"""Built-in feature plugins; add new modules here and import in register_builtin_plugins."""

from __future__ import annotations


def register_builtin_plugins() -> None:
    # Side-effect registration on import
    from app.features.builtin import (
        agent_skills,  # noqa: F401
        ai_home,  # noqa: F401
        ai_tools,  # noqa: F401
        assist_writing,  # noqa: F401
        carbon_ai_v1,  # noqa: F401
        carbon_asset_trading,  # noqa: F401
        carbon_platform_v3,  # noqa: F401
        carbon_qa_v2,  # noqa: F401 — 注册 id=carbon_qa
        external_links,  # noqa: F401
        compare,  # noqa: F401
        data_analysis,  # noqa: F401
        knowledge_search,  # noqa: F401
        kg_palantir,  # noqa: F401
        ocr,  # noqa: F401
        report_generation,  # noqa: F401
        smart_data_query_v2,  # noqa: F401 — 注册 id=smart_data_query
        smart_forecast,  # noqa: F401
        speech,  # noqa: F401
        text_to_speech,  # noqa: F401
        stubs,  # noqa: F401
        subscriptions,  # noqa: F401
        translate,  # noqa: F401
        wechat_mp_feed,  # noqa: F401
    )
