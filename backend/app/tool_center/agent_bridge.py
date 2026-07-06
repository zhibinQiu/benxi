"""LLM tool loop ↔ ToolCenter 桥接 — 全局原子 Tool 统一收口。"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent_tool_context import append_retrieval_context
from app.core.tool_skill_taxonomy import GLOBAL_ATOMIC_TOOL_NAMES, skill_id_for_tool
from app.models.org import User
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
    kb_result_to_context,
    kg_result_to_context,
    web_result_to_context,
)
from app.skills.types import SkillInvocationContext, SkillInvocationResult
from app.tool_center.context import ToolRuntimeContext
from app.tool_center.errors import business_message
from app.tool_center.executor import execute_tool_call, new_call_id
from app.tool_center.schemas import SkillMeta, ToolCallRequest, ToolResponse
from app.tool_center.skill_bridge import invoke_atomic_tool

_RETRIEVAL_TOOLS = frozenset(
    {ATOMIC_TOOL_WEB_SEARCH, ATOMIC_TOOL_KNOWLEDGE_RETRIEVE, ATOMIC_TOOL_KG_QUERY}
)


def _tool_result(ok: bool, summary: str, data: Any = None) -> str:
    payload: dict[str, Any] = {"ok": ok, "summary": summary}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False)


def _citation_start(loop_state: dict[str, Any] | None) -> int:
    if not loop_state:
        return 1
    return len(loop_state.get("citations") or []) + 1


def _offset_context_citations(
    context: str,
    citations: list[dict],
    *,
    start: int,
) -> tuple[str, list[dict]]:
    if start <= 1 or not citations:
        return context, citations
    offset = start - 1
    shifted = [{**c, "index": int(c.get("index") or 0) + offset} for c in citations]

    def _repl(match: re.Match[str]) -> str:
        return f"[{int(match.group(1)) + offset}]"

    return re.sub(r"\[(\d+)\]", _repl, context or ""), shifted


def _record_retrieval(
    loop_state: dict[str, Any] | None,
    *,
    context: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    if not context and not citations:
        return "", []
    start = _citation_start(loop_state)
    context, citations = _offset_context_citations(context, citations, start=start)
    if loop_state is not None and citations:
        loop_state.setdefault("citations", []).extend(citations)
    append_retrieval_context(loop_state, context)
    return context, citations


def _prepare_retrieval_params(
    tool_name: str,
    params: dict[str, Any],
    *,
    user_message: str,
    loop_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], str] | None:
    query = str(
        params.get("query") or params.get("question") or user_message or ""
    ).strip()
    if not query:
        return None
    merged = dict(params)
    if tool_name == ATOMIC_TOOL_WEB_SEARCH:
        merged.setdefault("query", query)
    elif tool_name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        merged.setdefault("query", query)
        if loop_state and loop_state.get("local_kb_disabled"):
            return merged, query
        scoped = loop_state.get("scoped_doc_ids") if loop_state else None
        if scoped is not None and not merged.get("doc_ids"):
            merged["doc_ids"] = [str(x) for x in scoped]
    elif tool_name == ATOMIC_TOOL_KG_QUERY:
        merged.setdefault("question", query)
    return merged, query


def _format_retrieval_json(
    tool_name: str,
    *,
    result: SkillInvocationResult,
    query: str,
    loop_state: dict[str, Any] | None,
    db: Session,
) -> str:
    if tool_name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE and loop_state and loop_state.get(
        "local_kb_disabled"
    ):
        return _tool_result(True, "未选择本地文档，已跳过知识库检索", {"context": "", "skipped": True})

    citation_start = _citation_start(loop_state)
    if tool_name == ATOMIC_TOOL_WEB_SEARCH:
        context, citations = web_result_to_context(result, citation_start=citation_start)
    elif tool_name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        context, citations = kb_result_to_context(db, query, result)
    else:
        kg_ctx = kg_result_to_context(result)
        context, citations = "", []
        if kg_ctx and loop_state is not None:
            loop_state["kg_context"] = kg_ctx
        if kg_ctx and kg_ctx.context_text:
            context = kg_ctx.context_text
            citations = list(kg_ctx.citations or [])
    context, citations = _record_retrieval(loop_state, context=context, citations=citations)
    return _tool_result(
        True,
        result.summary,
        {"context": context, "hit_count": len(citations), "tool": tool_name},
    )


def _response_to_legacy_json(response: ToolResponse) -> str:
    if response.success:
        return _tool_result(True, response.msg or "execute success", response.data)
    msg = business_message(response.code, response.msg)
    return _tool_result(False, msg)


async def execute_global_atomic_tool_json(
    db: Session,
    user: User,
    tool_name: str,
    params: dict[str, Any],
    *,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
) -> str:
    """全局原子 Tool 经 ToolCenter 执行，返回 legacy JSON。"""
    name = (tool_name or "").strip()
    if name not in GLOBAL_ATOMIC_TOOL_NAMES:
        return _tool_result(False, f"非全局原子工具: {name}")

    belong_agent = ""
    if loop_state:
        belong_agent = str(loop_state.get("agent_id") or "").strip()

    if name in _RETRIEVAL_TOOLS:
        prepared = _prepare_retrieval_params(
            name, params, user_message=user_message, loop_state=loop_state
        )
        if prepared is None:
            return _tool_result(False, "缺少 query / question")
        merged, query = prepared
        cache_key = f"{name}:{query.casefold()}"
        if loop_state is not None:
            done = loop_state.setdefault("atomic_retrieval_queries", set())
            if cache_key in done:
                return _tool_result(
                    True,
                    "本回合已执行相同检索，请复用先前工具结果",
                    {"context": "", "deduplicated": True},
                )
        ctx = SkillInvocationContext(
            db=db,
            user=user,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            belong_agent=belong_agent or None,
        )
        result = await invoke_atomic_tool(
            ctx,
            tool_id=name,
            params=merged,
            skill_id=skill_id_for_tool(name),
            belong_agent=belong_agent,
            user_message=user_message,
            loop_state=loop_state,
        )
        if not result.ok:
            return _tool_result(False, result.summary or "检索失败")
        if loop_state is not None:
            loop_state.setdefault("atomic_retrieval_queries", set()).add(cache_key)
        return _format_retrieval_json(
            name, result=result, query=query, loop_state=loop_state, db=db
        )

    request = ToolCallRequest(
        call_id=new_call_id(),
        tool_id=name,
        params=dict(params or {}),
        trace_id=(conversation_id or "")[:128],
        skill_meta=SkillMeta(
            skill_id=skill_id_for_tool(name),
            belong_agent=belong_agent,
        ),
    )
    runtime = ToolRuntimeContext(
        db=db,
        user=user,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        user_message=user_message,
        loop_state=loop_state,
    )
    response = await execute_tool_call(request, runtime)
    return _response_to_legacy_json(response)


def is_global_atomic_tool_name(name: str) -> bool:
    return (name or "").strip() in GLOBAL_ATOMIC_TOOL_NAMES
