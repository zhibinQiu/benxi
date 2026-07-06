"""ToolCenter 底层适配 — 直连原子实现，不经 Skill 路由（避免循环）。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.tool_skill_taxonomy import GLOBAL_ATOMIC_TOOL_NAMES
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.tool_center.context import ToolRuntimeContext


def _tool_result(ok: bool, summary: str, data: Any = None) -> tuple[bool, str, dict[str, Any] | None]:
    if isinstance(data, dict):
        return ok, summary, data
    if data is not None:
        return ok, summary, {"payload": data}
    return ok, summary, {}


async def _run_web_search(ctx: ToolRuntimeContext, params: dict[str, Any]) -> tuple[bool, str, dict | None]:
    query = str(params.get("query") or "").strip()
    max_items = int(params.get("max_items") or 8)
    from app.services.searxng_service import (
        SearxngNotConfiguredError,
        SearxngSearchError,
        search_web,
    )

    try:
        items, _ = search_web(query, page_size=max_items, db=ctx.db)
        return _tool_result(True, f"联网检索返回 {len(items)} 条", {"query": query, "items": items})
    except (SearxngNotConfiguredError, SearxngSearchError) as exc:
        return _tool_result(False, str(exc))
    except Exception as exc:
        return _tool_result(False, f"联网检索失败：{exc}")


def _queryable_doc_ids(ctx: ToolRuntimeContext) -> list[uuid.UUID]:
    from app.services.document_service import list_queryable_documents

    docs, _ = list_queryable_documents(ctx.db, ctx.user, page=1, page_size=100)
    return [d.id for d in docs]


async def _run_knowledge_retrieve(
    ctx: ToolRuntimeContext, params: dict[str, Any]
) -> tuple[bool, str, dict | None]:
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 8)
    raw_ids = params.get("doc_ids")
    doc_ids: list[uuid.UUID] = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            try:
                doc_ids.append(uuid.UUID(str(item)))
            except ValueError:
                continue
    if not doc_ids:
        doc_ids = _queryable_doc_ids(ctx)
    if not doc_ids:
        return _tool_result(False, "未指定 doc_ids，且用户权限内暂无可检索文档")
    from app.services.knowledge_qa_service import retrieve_hits_for_qa

    hits, mode = retrieve_hits_for_qa(
        ctx.db, ctx.user, doc_ids, query, limit=limit, merge_nearby=True
    )
    return _tool_result(
        True,
        f"知识库检索命中 {len(hits)} 段",
        {"query": query, "hits": hits, "mode": mode, "doc_ids": [str(x) for x in doc_ids]},
    )


async def _run_kg_query(ctx: ToolRuntimeContext, params: dict[str, Any]) -> tuple[bool, str, dict | None]:
    question = str(params.get("question") or params.get("query") or "").strip()
    from app.core.permissions import user_has_permission
    from app.services.kg_service import retrieve_kg_context_for_question

    if not user_has_permission(ctx.db, ctx.user, "feature.kg_palantir"):
        return _tool_result(False, "无本体图谱权限")
    kg_ctx = retrieve_kg_context_for_question(ctx.db, ctx.user, question)
    if not kg_ctx or not kg_ctx.context_text:
        return _tool_result(True, "未匹配到图谱实体", {})
    return _tool_result(
        True,
        f"图谱上下文 {kg_ctx.entity_count} 个实体",
        {
            "context_text": kg_ctx.context_text,
            "entity_count": kg_ctx.entity_count,
            "relation_count": kg_ctx.relation_count,
            "matched_entity_ids": [str(x) for x in kg_ctx.matched_entity_ids],
            "citations": kg_ctx.citations,
        },
    )


async def run_global_atomic_tool(
    ctx: ToolRuntimeContext,
    tool_id: str,
    params: dict[str, Any],
) -> tuple[bool, str, dict[str, Any] | None]:
    """全局原子 Tool 执行 — Tool 层不感知 Skill / Agent / LLM。"""
    name = (tool_id or "").strip()

    if name == ATOMIC_TOOL_WEB_SEARCH:
        return await _run_web_search(ctx, params)
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        if ctx.loop_state and ctx.loop_state.get("local_kb_disabled"):
            return _tool_result(True, "已跳过知识库检索", {"context": "", "skipped": True})
        if ctx.loop_state:
            scoped = ctx.loop_state.get("scoped_doc_ids")
            if scoped is not None and not params.get("doc_ids"):
                params = {**params, "doc_ids": [str(x) for x in scoped]}
        return await _run_knowledge_retrieve(ctx, params)
    if name == ATOMIC_TOOL_KG_QUERY:
        return await _run_kg_query(ctx, params)

    from app.services.agent_tools import (
        _execute_admin_tool,
        _execute_browser_tool,
        _execute_document_tool,
        _execute_platform_tool,
    )
    from app.services.agent_memory_service import append_user_memory, read_user_memory
    from app.services.agent_skill_router import extract_memory_note

    if name == "read_agent_memory":
        body = read_user_memory(ctx.user.id)
        if not body:
            from app.services.agent_memory_service import MEMORY_TEMPLATE

            body = MEMORY_TEMPLATE
        return _tool_result(True, "已读取记忆", {"memory": body})
    if name == "append_agent_memory":
        note = str(params.get("note") or "").strip()
        if not note:
            return _tool_result(False, "note 不能为空")
        ok = append_user_memory(ctx.user.id, extract_memory_note(note, max_len=500))
        return _tool_result(ok, "已写入记忆" if ok else "写入失败")

    doc_raw = _execute_document_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if doc_raw is not None:
        if name == "read_document_content" and ctx.loop_state is not None:
            try:
                body = json.loads(doc_raw)
                data = body.get("data") if isinstance(body, dict) else None
                if body.get("ok") and isinstance(data, dict):
                    full_text = str(data.get("full_text") or "").strip()
                    if full_text:
                        ctx.loop_state["agent_document_context"] = {
                            "title": str(data.get("title") or "").strip(),
                            "full_text": full_text[:40000],
                            "char_count": int(data.get("char_count") or len(full_text)),
                        }
            except json.JSONDecodeError:
                pass
        try:
            body = json.loads(doc_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, doc_raw[:300], None

    plat_raw = _execute_platform_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if plat_raw is not None:
        try:
            body = json.loads(plat_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, plat_raw[:300], None

    admin_raw = _execute_admin_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if admin_raw is not None:
        try:
            body = json.loads(admin_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, admin_raw[:300], None

    browser_raw = await _execute_browser_tool(
        ctx.db,
        ctx.user,
        tool_name=name,
        params=params,
        conversation_id=ctx.conversation_id,
        loop_state=ctx.loop_state,
        user_message=ctx.user_message,
    )
    if browser_raw is not None:
        try:
            body = json.loads(browser_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, browser_raw[:300], None

    return False, f"unknown global atomic tool: {name}", None
