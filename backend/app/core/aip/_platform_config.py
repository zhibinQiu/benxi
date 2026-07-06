"""AIP 平台配置 — 将 get_settings() 注入 agentkit HandoffBuilder / AidConfig。"""

from __future__ import annotations

from typing import Any

from agentkit_aip import AidConfig, AipDataItem, HandoffBuilder

from app.config import get_settings


def platform_aid_config() -> AidConfig:
    s = get_settings()
    return AidConfig(
        country=s.aip_country,
        org_type=s.aip_org_type,
        org_id=s.aip_org_id,
        serial=s.aip_agent_serial,
    )


def _extract_document_context(state: dict[str, Any]) -> AipDataItem | None:
    doc_ctx = state.get("agent_document_context")
    if isinstance(doc_ctx, dict) and str(doc_ctx.get("full_text") or "").strip():
        return AipDataItem(
            dataType="application/json",
            content=doc_ctx,
            label="document_context",
        )
    return None


def platform_handoff_builder() -> HandoffBuilder:
    return HandoffBuilder(
        aid_config=platform_aid_config(),
        loop_state_extractors=(_extract_document_context,),
    )
