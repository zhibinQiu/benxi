"""默认检索优先级 — 实例证据优先于 Schema：图谱 → 联网 → 文档库；本体查询不参与级联短路。"""

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

# 执行顺序（快→慢）：先实例后 Schema；ontology_query 仅作辅助理解，不短路后续检索
DEFAULT_RETRIEVAL_TOOL_ORDER: tuple[str, ...] = (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_ONTOLOGY_QUERY,
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


_KG_EMPTY_MARKERS = (
    "未匹配到",
    "未从问题中识别",
    "当前图谱为空",
)


def kg_has_material(kg_context: KgQaContext | None) -> bool:
    """是否有可用于作答的图谱推理材料（排除空匹配兜底文案）。"""
    if kg_context is None:
        return False
    text = (kg_context.context_text or "").strip()
    if not text:
        return False
    if any(marker in text for marker in _KG_EMPTY_MARKERS):
        return False
    if kg_context.matched_entity_ids and (
        kg_context.relation_count > 0 or "【知识图谱推理上下文】" in text
    ):
        return True
    return kg_context.relation_count > 0


def citations_have_sources(
    citations: list[dict[str, Any]] | None,
    sources: frozenset[str],
) -> bool:
    if not citations:
        return False
    return any(str(c.get("source") or "") in sources for c in citations)


def context_text_sufficient(text: str, *, min_chars: int = 48) -> bool:
    return len((text or "").strip()) >= min_chars
