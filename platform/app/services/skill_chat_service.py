"""AI 对话与 Agent Skills 桥接 — 调用内置 Skill 并合并检索结果。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.models.org import User
from app.schemas.agent_skill import AgentSkillCatalogItemOut
from app.services.kg_service import KgQaContext
from app.skills.executor import invoke_skill_tool
from app.skills.types import SkillInvocationContext, SkillInvocationResult

SKILL_WEB = "web-search"
TOOL_WEB = "search"
SKILL_KB = "knowledge-search"
TOOL_KB = "retrieve"
SKILL_KG = "kg-palantir"
TOOL_KG = "query_entities"
SKILL_RESEARCH = "knowledge-research"

# 暴露给模型的原子 Agent 工具名
ATOMIC_TOOL_WEB_SEARCH = "web_search"
ATOMIC_TOOL_KNOWLEDGE_RETRIEVE = "knowledge_retrieve"
ATOMIC_TOOL_KG_QUERY = "kg_query"

ATOMIC_TOOL_SKILL_MAP: dict[str, tuple[str, str]] = {
    ATOMIC_TOOL_WEB_SEARCH: (SKILL_WEB, TOOL_WEB),
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE: (SKILL_KB, TOOL_KB),
    ATOMIC_TOOL_KG_QUERY: (SKILL_KG, TOOL_KG),
}

_MAX_QUERYABLE_DOCS = 100

T = TypeVar("T")


def skill_tool_label(skill_name: str, tool_name: str) -> str:
    return f"{skill_name}.{tool_name}"


def get_user_skill_catalog(db: Session, user: User) -> list[AgentSkillCatalogItemOut]:
    from app.services import agent_skill_service as svc

    return svc.get_skill_catalog(db, user=user, admin_view=False)


def _make_ctx(db: Session, user: User, **kwargs: Any) -> SkillInvocationContext:
    return SkillInvocationContext(db=db, user=user, **kwargs)


async def invoke_chat_skill(
    db: Session,
    user: User,
    *,
    skill_name: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
    **ctx_kwargs: Any,
) -> SkillInvocationResult:
    return await invoke_skill_tool(
        _make_ctx(db, user, **ctx_kwargs),
        skill_name=skill_name,
        tool_name=tool_name,
        params=params,
        admin_invoke=False,
    )


def _run_sync(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)


def _queryable_doc_ids(db: Session, user: User) -> list[uuid.UUID]:
    from app.services.document_service import list_queryable_documents

    docs, _ = list_queryable_documents(
        db, user, page=1, page_size=_MAX_QUERYABLE_DOCS
    )
    return [d.id for d in docs]


def web_result_to_context(
    result: SkillInvocationResult,
    *,
    citation_start: int = 1,
) -> tuple[str, list[dict]]:
    if not result.ok or not result.data:
        return "", []
    items = result.data.get("items") or []
    if not items:
        return "", []
    from app.services.report_generation_service import (
        _format_web_context,
        build_web_citations,
    )

    return (
        _format_web_context(items, start_index=citation_start),
        build_web_citations(items, start_index=citation_start),
    )


def kb_result_to_context(
    db: Session,
    message: str,
    result: SkillInvocationResult,
) -> tuple[str, list[dict]]:
    if not result.ok or not result.data:
        return "", []
    hits = result.data.get("hits") or []
    if not hits:
        return "", []
    doc_ids = _parse_doc_ids(result.data.get("doc_ids") or [], hits)
    from app.services.knowledge_qa_service import (
        _doc_citation_meta,
        _doc_titles,
        build_aligned_qa_context_and_citations,
    )

    return build_aligned_qa_context_and_citations(
        hits,
        _doc_titles(db, doc_ids),
        question=message,
        doc_meta=_doc_citation_meta(db, doc_ids),
    )


def _parse_doc_ids(raw_ids: list[Any], hits: list[dict]) -> list[uuid.UUID]:
    doc_ids: list[uuid.UUID] = []
    for item in raw_ids:
        try:
            doc_ids.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    if doc_ids:
        return doc_ids
    seen: set[uuid.UUID] = set()
    for hit in hits:
        raw_id = hit.get("document_id")
        if not raw_id:
            continue
        try:
            seen.add(uuid.UUID(str(raw_id)))
        except ValueError:
            continue
    return list(seen)


def kg_result_to_context(result: SkillInvocationResult) -> KgQaContext | None:
    if not result.ok or not result.data:
        return None
    data = result.data
    context_text = (data.get("context_text") or "").strip()
    if not context_text:
        return None
    matched: list[uuid.UUID] = []
    for item in data.get("matched_entity_ids") or []:
        try:
            matched.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    return KgQaContext(
        context_text=context_text,
        citations=list(data.get("citations") or []),
        matched_entity_ids=matched,
        entity_count=int(data.get("entity_count") or 0),
        relation_count=int(data.get("relation_count") or 0),
    )


async def _invoke_builtin(
    db: Session,
    user: User,
    *,
    skill_name: str,
    tool_name: str,
    params: dict[str, Any],
    to_context: Callable[[SkillInvocationResult], Any],
) -> Any:
    result = await invoke_chat_skill(
        db, user, skill_name=skill_name, tool_name=tool_name, params=params
    )
    return to_context(result)


async def resolve_web_search_via_skill(
    db: Session,
    user: User,
    message: str,
    *,
    citation_start: int = 1,
) -> tuple[str, list[dict]]:
    return await _invoke_builtin(
        db,
        user,
        skill_name=SKILL_WEB,
        tool_name=TOOL_WEB,
        params={"query": message, "max_items": 8},
        to_context=lambda r: web_result_to_context(r, citation_start=citation_start),
    )


async def resolve_doc_retrieval_via_skill(
    db: Session,
    user: User,
    message: str,
) -> tuple[str, list[dict]]:
    doc_ids = _queryable_doc_ids(db, user)
    if not doc_ids:
        return "", []
    return await _invoke_builtin(
        db,
        user,
        skill_name=SKILL_KB,
        tool_name=TOOL_KB,
        params={"query": message, "doc_ids": [str(d) for d in doc_ids]},
        to_context=lambda r: kb_result_to_context(db, message, r),
    )


async def resolve_kg_context_via_skill(
    db: Session,
    user: User,
    message: str,
) -> KgQaContext | None:
    return await _invoke_builtin(
        db,
        user,
        skill_name=SKILL_KG,
        tool_name=TOOL_KG,
        params={"question": message},
        to_context=kg_result_to_context,
    )


def resolve_kg_context_via_skill_sync(
    db: Session,
    user: User,
    message: str,
) -> KgQaContext | None:
    """同步入口，供测试或非 async 上下文使用。"""
    return _run_sync(resolve_kg_context_via_skill(db, user, message))


async def resolve_combined_research_async(
    db: Session,
    user: User,
    query: str,
    *,
    use_kb: bool | None = None,
    use_kg: bool | None = None,
    use_web: bool | None = None,
    citation_start: int = 1,
) -> tuple[str, list[dict], KgQaContext | None, dict[str, Any]]:
    """综合知识库、本体图谱与联网检索，合并为一段可注入模型的上下文。"""
    from app.core.permissions import user_has_permission
    from app.services.agent_intent import needs_knowledge_retrieval, needs_web_search
    from app.services.kg_service import merge_kg_qa_into_context
    from app.services.searxng_service import is_enabled as web_search_enabled

    text = (query or "").strip()
    if not text:
        return "", [], None, {"kb": False, "kg": False, "web": False}

    kb_allowed = user_has_permission(db, user, "feature.knowledge_search")
    kg_allowed = user_has_permission(db, user, "feature.kg_palantir")
    web_allowed = web_search_enabled(db)

    if use_kb is None or use_kg is None or use_web is None:
        inferred_kb = needs_knowledge_retrieval(text)
        inferred_web = needs_web_search(text)
        if use_kb is None:
            use_kb = inferred_kb and kb_allowed
        if use_kg is None:
            use_kg = inferred_kb and kg_allowed
        if use_web is None:
            use_web = inferred_web and web_allowed

    run_kb = bool(use_kb and kb_allowed)
    run_kg = bool(use_kg and kg_allowed)
    run_web = bool(use_web and web_allowed)

    doc_context, doc_citations = "", []
    if run_kb:
        doc_context, doc_citations = await resolve_doc_retrieval_via_skill(
            db, user, text
        )

    kg_context: KgQaContext | None = None
    if run_kg:
        kg_context = await resolve_kg_context_via_skill(db, user, text)

    merged_context, citations = merge_kg_qa_into_context(
        doc_context, doc_citations, kg_context
    )

    if run_web and (not run_kb or not citations):
        web_context, web_citations = await resolve_web_search_via_skill(
            db,
            user,
            text,
            citation_start=max(citation_start, len(citations) + 1),
        )
        if web_context.strip():
            parts = [p.strip() for p in (merged_context, web_context) if p.strip()]
            merged_context = "\n\n".join(parts)
            citations = list(citations) + list(web_citations)

    return merged_context, citations, kg_context, {
        "kb": run_kb,
        "kg": run_kg,
        "web": run_web,
    }
