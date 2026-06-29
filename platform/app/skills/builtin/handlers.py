"""内置 Skill 工具 handler — 委托现有平台服务。"""

from __future__ import annotations

import uuid
from typing import Any

from app.skills.types import SkillHandler, SkillInvocationContext, SkillInvocationResult


async def handle_web_search(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    max_items = int(params.get("max_items") or 8)
    try:
        from app.services.searxng_service import (
            SearxngNotConfiguredError,
            SearxngSearchError,
            search_web,
        )

        items, _ = search_web(query, page_size=max_items, db=ctx.db)
        return SkillInvocationResult(
            True,
            f"联网检索「{query[:40]}」返回 {len(items)} 条",
            data={"query": query, "items": items},
        )
    except (SearxngNotConfiguredError, SearxngSearchError) as exc:
        return SkillInvocationResult(False, str(exc), error=str(exc))
    except Exception as exc:
        return SkillInvocationResult(False, f"联网检索失败：{exc}", error=str(exc))


async def handle_knowledge_retrieve(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    limit = int(params.get("limit") or 8)
    doc_ids = _resolve_doc_ids(ctx, params)
    if not doc_ids:
        return SkillInvocationResult(
            False,
            "未指定 doc_ids，且用户权限内暂无可检索文档",
            error="no_documents",
        )
    try:
        from app.services.knowledge_qa_service import retrieve_hits_for_qa

        hits, mode = retrieve_hits_for_qa(
            ctx.db, ctx.user, doc_ids, query, limit=limit, merge_nearby=True
        )
        return SkillInvocationResult(
            True,
            f"知识库检索「{query[:40]}」命中 {len(hits)} 段（{mode}）",
            data={"query": query, "hits": hits, "mode": mode, "doc_ids": doc_ids},
        )
    except Exception as exc:
        from app.core.user_messages import http_exception_message

        msg = http_exception_message(exc, fallback="知识库检索失败，请稍后重试")
        return SkillInvocationResult(False, f"知识库检索失败：{msg}", error=str(exc))


async def handle_kg_query(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    question = str(params.get("question") or params.get("query") or "").strip()
    if not question:
        return SkillInvocationResult(False, "缺少 question", error="missing_question")
    try:
        from app.core.permissions import user_has_permission
        from app.services.kg_service import retrieve_kg_context_for_question

        if not user_has_permission(ctx.db, ctx.user, "feature.kg_palantir"):
            return SkillInvocationResult(False, "无本体图谱权限", error="forbidden")
        kg_ctx = retrieve_kg_context_for_question(ctx.db, ctx.user, question)
        if not kg_ctx or not kg_ctx.context_text:
            return SkillInvocationResult(True, "未匹配到图谱实体", data=None)
        return SkillInvocationResult(
            True,
            f"图谱上下文 {kg_ctx.entity_count} 个实体",
            data={
                "context_text": kg_ctx.context_text,
                "entity_count": kg_ctx.entity_count,
                "relation_count": kg_ctx.relation_count,
                "matched_entity_ids": [str(x) for x in kg_ctx.matched_entity_ids],
                "citations": kg_ctx.citations,
            },
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"图谱查询失败：{exc}", error=str(exc))


async def handle_knowledge_research(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """综合知识库、本体图谱与联网检索（按需通道，复用 skill_chat_service）。"""
    query = str(params.get("query") or params.get("question") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    use_kb = params.get("use_kb")
    use_kg = params.get("use_kg")
    use_web = params.get("use_web")
    if use_kb is not None:
        use_kb = bool(use_kb)
    if use_kg is not None:
        use_kg = bool(use_kg)
    if use_web is not None:
        use_web = bool(use_web)
    citation_start = int(params.get("citation_start") or 1)
    try:
        from app.services.skill_chat_service import resolve_combined_research_async

        context, citations, kg_ctx, channels = await resolve_combined_research_async(
            ctx.db,
            ctx.user,
            query,
            use_kb=use_kb,
            use_kg=use_kg,
            use_web=use_web,
            citation_start=citation_start,
        )
        parts: list[str] = []
        if channels.get("kb"):
            parts.append("知识库")
        if channels.get("kg"):
            parts.append("图谱")
        if channels.get("web"):
            parts.append("联网")
        label = "、".join(parts) if parts else "未启用检索通道"
        summary = f"综合检索「{query[:40]}」({label})"
        if citations:
            summary += f"，共 {len(citations)} 条引用"
        else:
            summary += "，未命中有效材料"
        return SkillInvocationResult(
            True,
            summary,
            data={
                "query": query,
                "context": context,
                "citations": citations,
                "channels": channels,
                "kg_context_text": kg_ctx.context_text if kg_ctx else "",
                "kg_matched_entities": len(kg_ctx.matched_entity_ids)
                if kg_ctx
                else 0,
                "kg_relation_count": kg_ctx.relation_count if kg_ctx else 0,
            },
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"综合检索失败：{exc}", error=str(exc))


async def handle_stub_feature(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
    *,
    feature_title: str = "平台功能",
    route: str = "",
    hint: str = "",
) -> SkillInvocationResult:
    """占位 handler：返回功能说明与后续接入提示。"""
    _ = ctx
    msg = f"「{feature_title}」Skill 已注册，智能体循环接入中。"
    if route:
        msg += f" 用户也可在 {route} 使用完整界面。"
    if hint:
        msg += f" {hint}"
    return SkillInvocationResult(
        True,
        msg,
        data={"status": "stub", "params_received": params, "route": route or None},
    )


def make_stub_handler(
    *, feature_title: str, route: str, hint: str = ""
) -> SkillHandler:
    async def _handler(
        ctx: SkillInvocationContext, params: dict[str, Any]
    ) -> SkillInvocationResult:
        return await handle_stub_feature(
            ctx, params, feature_title=feature_title, route=route, hint=hint
        )

    return _handler


def _resolve_doc_ids(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> list[uuid.UUID]:
    from app.services.skill_guard import filter_doc_ids_for_user

    raw = params.get("doc_ids")
    if isinstance(raw, list) and raw:
        parsed: list[uuid.UUID] = []
        for item in raw:
            try:
                parsed.append(uuid.UUID(str(item)))
            except ValueError:
                continue
        if parsed:
            return filter_doc_ids_for_user(ctx.db, ctx.user, parsed)
    if ctx.doc_ids:
        return filter_doc_ids_for_user(ctx.db, ctx.user, list(ctx.doc_ids))
    return _default_searchable_doc_ids(ctx)


def _default_searchable_doc_ids(ctx: SkillInvocationContext) -> list[uuid.UUID]:
    """无显式 doc_ids 时，取用户权限内少量已索引/有文件的文档。"""
    try:
        from sqlalchemy import select

        from app.core.permissions import PermissionLevel, can_access_document
        from app.models.document import Document
        from app.services.compare_service import _document_retrieval_ready
        from app.services.document_index_service import (
            enrich_document_index_meta,
            is_index_ready_meta,
        )

        rows = ctx.db.scalars(
            select(Document.id)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc())
            .limit(50)
        ).all()
        candidates: list[Document] = []
        for doc_id in rows:
            doc = ctx.db.get(Document, doc_id)
            if doc and can_access_document(
                ctx.db, ctx.user, doc, PermissionLevel.query.value
            ):
                candidates.append(doc)
        if not candidates:
            return []
        meta_by_doc = enrich_document_index_meta(
            ctx.db, ctx.user, candidates, live_ragflow=False
        )
        index_ready_ids = {
            did for did, meta in meta_by_doc.items() if is_index_ready_meta(meta)
        }
        out: list[uuid.UUID] = []
        for doc in candidates:
            if _document_retrieval_ready(
                ctx.db,
                doc,
                index_ready_ids=index_ready_ids,
                allow_index_only=True,
            ):
                out.append(doc.id)
            if len(out) >= 10:
                break
        return out
    except Exception:
        return []
