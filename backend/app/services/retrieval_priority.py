"""默认检索优先级 — 提速：直答 > 本体查询 > 图谱查询 > 联网 > 文档库；用户显式指定时不走级联。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.kg import KgQaContext
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_ONTOLOGY_QUERY,
)

# 执行顺序（快→慢）；事实引用优先级与 platform_assistant 保持一致
DEFAULT_RETRIEVAL_TOOL_ORDER: tuple[str, ...] = (
    ATOMIC_TOOL_ONTOLOGY_QUERY,  # 第 0 优先 — 先查本体理解领域语义
    ATOMIC_TOOL_KG_QUERY,        # 第 1 优先 — 再查图谱实例
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
)

_DOC_CITATION_SOURCES = frozenset({"local", "local_filename", "knowflow"})
_WEB_CITATION_SOURCES = frozenset({"web", "searxng", "internet"})


@dataclass(frozen=True, slots=True)
class RetrievalChannelPlan:
    run_kg: bool
    run_web: bool
    run_kb: bool
    explicit: bool
    """用户显式指定渠道时为 True，不按级联短路。"""


def parse_explicit_retrieval_channels(message: str) -> dict[str, bool] | None:
    """用户明确要求某检索渠道时返回 {kb, kg, web}；否则 None。"""
    from app.services.agent_intent import (
        _EXPLICIT_KB_RE,
        _EXPLICIT_KG_RE,
        _EXPLICIT_WEB_RE,
    )

    text = (message or "").strip()
    if not text:
        return None
    kb = bool(_EXPLICIT_KB_RE.search(text))
    kg = bool(_EXPLICIT_KG_RE.search(text))
    web = bool(_EXPLICIT_WEB_RE.search(text))
    if not (kb or kg or web):
        return None
    return {"kb": kb, "kg": kg, "web": web}


def resolve_retrieval_channel_plan(
    message: str,
    *,
    kb_allowed: bool,
    kg_allowed: bool,
    web_allowed: bool,
    use_kb: bool | None = None,
    use_kg: bool | None = None,
    use_web: bool | None = None,
) -> RetrievalChannelPlan:
    """解析本轮应启用的检索渠道与是否显式覆盖默认级联。"""
    text = (message or "").strip()
    explicit_map = parse_explicit_retrieval_channels(text)

    if explicit_map is not None:
        run_kb = explicit_map["kb"] and kb_allowed
        run_kg = explicit_map["kg"] and kg_allowed
        run_web = explicit_map["web"] and web_allowed
        if use_kb is not None:
            run_kb = bool(use_kb) and kb_allowed
        if use_kg is not None:
            run_kg = bool(use_kg) and kg_allowed
        if use_web is not None:
            run_web = bool(use_web) and web_allowed
        return RetrievalChannelPlan(
            run_kg=run_kg,
            run_web=run_web,
            run_kb=run_kb,
            explicit=True,
        )

    if use_kb is not None:
        run_kb = bool(use_kb) and kb_allowed
    else:
        run_kb = kb_allowed
    if use_kg is not None:
        run_kg = bool(use_kg) and kg_allowed
    else:
        run_kg = kg_allowed
    if use_web is not None:
        run_web = bool(use_web) and web_allowed
    else:
        run_web = web_allowed

    return RetrievalChannelPlan(
        run_kg=run_kg,
        run_web=run_web,
        run_kb=run_kb,
        explicit=False,
    )


def kg_has_material(kg_context: KgQaContext | None) -> bool:
    if kg_context is None:
        return False
    return bool(
        (kg_context.context_text or "").strip()
        or kg_context.entity_count
        or kg_context.relation_count
        or kg_context.matched_entity_ids
    )


def citations_have_sources(
    citations: list[dict[str, Any]] | None,
    sources: frozenset[str],
) -> bool:
    if not citations:
        return False
    return any(str(c.get("source") or "") in sources for c in citations)


def context_text_sufficient(text: str, *, min_chars: int = 48) -> bool:
    return len((text or "").strip()) >= min_chars
