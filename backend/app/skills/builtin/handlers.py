"""内置 Skill 工具 handler — 委托现有平台服务。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.skills.types import SkillHandler, SkillInvocationContext, SkillInvocationResult


async def handle_web_search(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.core.tool_skill_taxonomy import SKILL_WEB_SEARCH
    from app.tool_center.skill_bridge import invoke_atomic_tool

    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    return await invoke_atomic_tool(
        ctx,
        tool_id="web_search",
        params=params,
        skill_id=SKILL_WEB_SEARCH,
        success_summary=f"联网检索「{query[:40]}」完成",
    )


async def handle_knowledge_retrieve(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.core.tool_skill_taxonomy import SKILL_KNOWLEDGE_SEARCH
    from app.tool_center.skill_bridge import invoke_atomic_tool

    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    merged = dict(params)
    doc_ids = _resolve_doc_ids(ctx, params)
    if doc_ids:
        merged["doc_ids"] = [str(x) for x in doc_ids]
    elif not params.get("doc_ids"):
        return SkillInvocationResult(
            False,
            "未指定 doc_ids，且用户权限内暂无可检索文档",
            error="no_documents",
        )
    return await invoke_atomic_tool(
        ctx,
        tool_id="knowledge_retrieve",
        params=merged,
        skill_id=SKILL_KNOWLEDGE_SEARCH,
        success_summary=f"知识库检索「{query[:40]}」完成",
    )


async def handle_kg_query(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.tool_center.skill_bridge import invoke_atomic_tool

    question = str(params.get("question") or params.get("query") or "").strip()
    if not question:
        return SkillInvocationResult(False, "缺少 question", error="missing_question")
    return await invoke_atomic_tool(
        ctx,
        tool_id="kg_query",
        params={"question": question},
        skill_id="kg",
    )


async def handle_deep_research(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """深度研究：委托子 Agent 执行多轮联网检索与交叉验证，返回含引用链接的研究报告。"""
    task = str(params.get("task") or params.get("query") or "").strip()
    if not task:
        return SkillInvocationResult(False, "缺少研究课题", error="missing_task")

    from app.core.agent.subagent import execute_context_subagent

    loop_state = ctx.loop_state or {}
    result_json = await execute_context_subagent(
        db=ctx.db,
        user=ctx.user,
        kind="search",
        task=task,
        conversation_id=ctx.conversation_id,
        attachment_session_id=ctx.attachment_session_id,
        loop_state=loop_state,
    )
    try:
        payload = json.loads(result_json)
    except json.JSONDecodeError:
        payload = {}

    ok = payload.get("ok", False)
    summary = str(payload.get("summary") or "")
    full_result = (payload.get("data") or {}).get("result") or ""

    # 从完整报告文本中提取引用链接
    citations = _extract_deep_research_citations(full_result)
    return SkillInvocationResult(
        ok=ok,
        summary=summary[:200] if ok else f"深度研究失败：{summary[:200]}",
        data={"summary": summary, "citations": citations},
    )


_DE_CITATION_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')


def _extract_deep_research_citations(text: str) -> list[dict]:
    """从 deep_research 报告文本中提取 markdown 链接作为结构化引用。"""
    seen: set[str] = set()
    citations: list[dict] = []
    for match in _DE_CITATION_RE.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).strip().rstrip(".,;")
        if url not in seen and not url.endswith((".png", ".jpg", ".gif", ".svg")):
            seen.add(url)
            citations.append({
                "index": len(citations) + 1,
                "title": title or url,
                "url": url,
                "source": "web",
            })
    return citations


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


async def handle_free_web_ai_chat(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 文本对话。"""
    prompt = str(params.get("prompt") or params.get("query") or "").strip()
    if not prompt:
        return SkillInvocationResult(False, "缺少 prompt", error="missing_prompt")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(
                False, "免费网页 AI 功能未启用，请配置 FREE_WEB_AI_ENABLED=true",
                error="disabled",
            )
        mgr = get_free_web_ai_manager()
        result = await mgr.chat(prompt, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"AI 回复（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False,
            f"AI 回复失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"免费网页 AI 调用异常: {exc}", error=str(exc))


async def handle_free_web_ai_image_gen(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 文字生图。"""
    prompt = str(params.get("prompt") or params.get("query") or "").strip()
    if not prompt:
        return SkillInvocationResult(False, "缺少生图描述", error="missing_prompt")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(False, "免费网页 AI 功能未启用", error="disabled")
        mgr = get_free_web_ai_manager()
        result = await mgr.generate_image(prompt, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"图片已生成（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False, f"生图失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"生图异常: {exc}", error=str(exc))


async def handle_free_web_ai_image_ask(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 识图问答。"""
    question = str(params.get("question") or params.get("query") or "").strip()
    if not question:
        return SkillInvocationResult(False, "缺少问题", error="missing_question")
    image_path = str(params.get("image_path") or "").strip()
    if not image_path:
        return SkillInvocationResult(False, "缺少图片路径", error="missing_image_path")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(False, "免费网页 AI 功能未启用", error="disabled")
        mgr = get_free_web_ai_manager()
        result = await mgr.ask_with_image(question, image_path, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"识图回复（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False, f"识图问答失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"识图问答异常: {exc}", error=str(exc))


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
