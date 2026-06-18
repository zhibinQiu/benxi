"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.permissions import user_has_permission
from app.core.platform_assistant import assistant_ai_home_persona
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.kg_service import KgQaContext, merge_kg_qa_into_context, retrieve_kg_context_for_question

_MAX_HISTORY = 20
_MAX_QUERYABLE_DOCS = 20

_SYSTEM_PROMPT = f"""{assistant_ai_home_persona()}。

你的能力包括：
- 以「小析」身份解答文档管理、权限分享、PDF 翻译、知识检索等平台使用问题
- 结合权限内文档检索片段与本体图谱实体关系，回答业务相关问题
- 协助梳理办公场景下的信息整理、写作润色与数据分析思路

回答要求：
- 使用简体中文，结构清晰，可使用简短 Markdown
- 自我介绍或提及助手时统一使用名称「小析」
- 对不确定的政策或数据应说明需以官方来源为准，勿编造具体数值或文号
- 引用文档片段或图谱事实时在句末标注编号，格式为 [1]、[2]
- 超出平台或办公场景的问题可简要回应并引导回相关能力"""

_RETRIEVAL_CONTEXT_INSTRUCTION = """以下是从用户权限内文档检索到的相关片段，以及（若有）从本体图谱解析出的实体与关系上下文。
请在回答中优先参考这些材料；引用时在句末标注编号 [1]、[2]。若材料未覆盖问题，可结合专业知识补充并说明缺口。"""


def _kg_enabled_for_user(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.kg_palantir")


def _knowledge_search_enabled(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.knowledge_search")


def _resolve_kg_context(
    db: Session | None,
    user: User | None,
    message: str,
) -> KgQaContext | None:
    if db is None or user is None or not _kg_enabled_for_user(db, user):
        return None
    return retrieve_kg_context_for_question(db, user, message)


def _resolve_doc_retrieval(
    db: Session | None,
    user: User | None,
    message: str,
) -> tuple[str, list[dict]]:
    if db is None or user is None or not _knowledge_search_enabled(db, user):
        return "", []
    from app.services.document_service import list_queryable_documents
    from app.services.knowledge_qa_service import (
        _doc_citation_meta,
        _doc_titles,
        build_aligned_qa_context_and_citations,
        retrieve_hits_for_qa,
    )

    docs, _ = list_queryable_documents(
        db, user, page=1, page_size=_MAX_QUERYABLE_DOCS
    )
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return "", []
    hits, _mode = retrieve_hits_for_qa(db, user, doc_ids, message)
    if not hits:
        return "", []
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    return build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=message,
        doc_meta=doc_meta,
    )


def _resolve_attachment_context(
    db: Session | None,
    user: User | None,
    attachment_session_id: str | None,
) -> tuple[str, int]:
    if db is None or user is None or not (attachment_session_id or "").strip():
        return "", 0
    from app.services.ai_chat_attachment_service import (
        build_attachment_context,
        get_owned_session,
    )

    try:
        manifest = get_owned_session(user.id, attachment_session_id)
    except Exception:
        return "", 0
    files = manifest.get("files") or []
    return build_attachment_context(files), len(files)


def _merge_retrieval_context(
    *,
    attachment_context: str,
    doc_context: str,
    doc_citations: list[dict],
    kg_context: KgQaContext | None,
) -> tuple[str, list[dict]]:
    merged_context, citations = merge_kg_qa_into_context(
        doc_context, doc_citations, kg_context
    )
    parts = [p.strip() for p in (attachment_context, merged_context) if (p or "").strip()]
    return "\n\n".join(parts), citations


def _resolve_answer_context(
    db: Session | None,
    user: User | None,
    message: str,
    attachment_session_id: str | None = None,
) -> tuple[str, list[dict], KgQaContext | None, int]:
    attachment_context, attach_count = _resolve_attachment_context(
        db, user, attachment_session_id
    )
    doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)
    kg_context = _resolve_kg_context(db, user, message)
    merged_context, citations = _merge_retrieval_context(
        attachment_context=attachment_context,
        doc_context=doc_context,
        doc_citations=doc_citations,
        kg_context=kg_context,
    )
    return merged_context, citations, kg_context, attach_count


def _resolve_platform_knowledge(
    db: Session | None,
    user: User | None,
) -> str:
    if db is None or user is None:
        return ""
    from app.services.assistant_knowledge import build_platform_knowledge

    return build_platform_knowledge(db, user)


def _build_chat_messages(
    *,
    message: str,
    history: list[AiChatMessage],
    retrieval_context: str = "",
    platform_knowledge: str = "",
) -> list[dict]:
    system = _SYSTEM_PROMPT
    if platform_knowledge.strip():
        system = f"{system}\n\n【平台操作知识库】\n{platform_knowledge.strip()}"
    if retrieval_context.strip():
        system = (
            f"{system}\n\n{_RETRIEVAL_CONTEXT_INSTRUCTION}\n\n{retrieval_context.strip()}"
        )
    messages: list[dict] = [{"role": "system", "content": system}]
    tail = history[-_MAX_HISTORY:] if history else []
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message.strip()})
    return messages


def _kg_meta_payload(kg_context: KgQaContext | None) -> dict[str, Any]:
    if not kg_context:
        return {}
    return {
        "kg_matched_entities": len(kg_context.matched_entity_ids),
        "kg_entity_count": kg_context.entity_count,
        "kg_relation_count": kg_context.relation_count,
    }


_step_seq = 0


def _next_step_id() -> str:
    global _step_seq
    _step_seq += 1
    return f"ai-s{_step_seq}"


def _workflow_event(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
) -> str:
    ev: dict[str, Any] = {"phase": phase, "title": title, "status": status}
    if detail:
        ev["detail"] = detail
    if tool:
        ev["tool"] = tool
    if step_id:
        ev["step_id"] = step_id
    return json.dumps({"workflow": ev}, ensure_ascii=False)


async def _emit_workflow(phase: str, **kwargs: Any) -> AsyncIterator[str]:
    yield _workflow_event(phase, **kwargs)
    await asyncio.sleep(0)


def _persist_turn(
    db: Session | None,
    *,
    user_id: uuid.UUID | None,
    conversation_id: str | None,
    message: str,
    reply: str,
) -> str | None:
    if db is None or user_id is None:
        return conversation_id
    conv = platform_chat_store.get_or_create_conversation(
        db,
        user_id=user_id,
        scope="ai-home",
        conversation_id=conversation_id,
    )
    platform_chat_store.append_turn(
        db,
        conversation=conv,
        user_message=message,
        assistant_message=reply,
    )
    db.commit()
    return str(conv.id)


async def iter_chat_with_ai_agent_stream(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    if not is_configured():
        yield json.dumps({"error": "AI 对话未配置，请联系管理员配置 DeepSeek API"}, ensure_ascii=False)
        return

    async for payload in _emit_workflow("workflow_started", title="开始处理问题"):
        yield payload

    think_id = _next_step_id()
    async for payload in _emit_workflow(
        "agent_thinking",
        title="分析问题意图",
        detail=message.strip()[:160],
        step_id=think_id,
    ):
        yield payload
    async for payload in _emit_workflow(
        "agent_thought",
        title="已理解问题",
        detail="准备检索权限内文档与本体图谱",
        step_id=think_id,
        status="done",
    ):
        yield payload

    doc_context = ""
    doc_citations: list[dict] = []
    attachment_context = ""
    attach_count = 0
    attach_id = _next_step_id()
    if (attachment_session_id or "").strip() and db is not None and user is not None:
        async for payload in _emit_workflow(
            "tool_call",
            title="读取临时附件",
            tool="attachments",
            detail=message.strip()[:120],
            step_id=attach_id,
        ):
            yield payload
        attachment_context, attach_count = _resolve_attachment_context(
            db, user, attachment_session_id
        )
        attach_detail = (
            f"已加载 {attach_count} 个附件"
            if attach_count
            else "未找到有效附件"
        )
        async for payload in _emit_workflow(
            "tool_result",
            title="临时附件就绪",
            tool="attachments",
            detail=attach_detail,
            step_id=attach_id,
            status="done",
        ):
            yield payload

    retrieve_id = _next_step_id()
    if db is not None and user is not None and _knowledge_search_enabled(db, user):
        async for payload in _emit_workflow(
            "tool_call",
            title="检索权限内文档",
            tool="retrieve",
            detail=message.strip()[:120],
            step_id=retrieve_id,
        ):
            yield payload
        doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)
        retrieve_detail = (
            f"命中 {len(doc_citations)} 条相关片段"
            if doc_citations
            else "未命中相关文档片段"
        )
        async for payload in _emit_workflow(
            "tool_result",
            title="文档检索完成",
            tool="retrieve",
            detail=retrieve_detail,
            step_id=retrieve_id,
            status="done",
        ):
            yield payload
    elif db is not None and user is not None:
        doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)

    kg_context: KgQaContext | None = None
    kg_id = _next_step_id()
    if db is not None and user is not None and _kg_enabled_for_user(db, user):
        async for payload in _emit_workflow(
            "tool_call",
            title="解析本体图谱关联",
            tool="kg_context",
            detail=message.strip()[:120],
            step_id=kg_id,
        ):
            yield payload
        kg_context = _resolve_kg_context(db, user, message)
        if kg_context and kg_context.context_text.strip():
            kg_detail = (
                f"匹配 {len(kg_context.matched_entity_ids)} 个实体，"
                f"{kg_context.relation_count} 条关系"
            )
        else:
            kg_detail = "未匹配到相关实体"
        async for payload in _emit_workflow(
            "tool_result",
            title="本体图谱上下文",
            tool="kg_context",
            detail=kg_detail,
            step_id=kg_id,
            status="done",
        ):
            yield payload

    merged_context, citations = _merge_retrieval_context(
        attachment_context=attachment_context,
        doc_context=doc_context,
        doc_citations=doc_citations,
        kg_context=kg_context,
    )
    if citations:
        yield json.dumps({"citations": citations}, ensure_ascii=False)

    async for payload in _emit_workflow("node_started", title="正在生成回答"):
        yield payload

    accumulated = ""
    platform_knowledge = _resolve_platform_knowledge(db, user)
    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=merged_context,
        platform_knowledge=platform_knowledge,
    )
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "stream": True,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread())[:500].decode("utf-8", errors="replace")
                    yield json.dumps(
                        {"error": f"AI 对话暂时不可用: {body}"},
                        ensure_ascii=False,
                    )
                    async for payload in _emit_workflow(
                        "workflow_finished", title="处理失败", status="failed"
                    ):
                        yield payload
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        accumulated += text
                        yield json.dumps({"delta": text}, ensure_ascii=False)
        out_conv_id = _persist_turn(
            db,
            user_id=user.id if user else None,
            conversation_id=conversation_id,
            message=message,
            reply=accumulated,
        )
        done_payload: dict[str, Any] = {
            "done": True,
            "model": model,
            "reply": accumulated,
            "conversation_id": out_conv_id,
            **_kg_meta_payload(kg_context),
        }
        if citations:
            done_payload["citations"] = citations
        yield json.dumps(done_payload, ensure_ascii=False)
        async for payload in _emit_workflow("workflow_finished", title="完成"):
            yield payload
    except httpx.HTTPError as e:
        yield json.dumps({"error": f"无法连接 AI 服务: {e}"}, ensure_ascii=False)
        async for payload in _emit_workflow(
            "workflow_finished", title="处理失败", status="failed"
        ):
            yield payload


async def chat_with_ai_agent(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("AI 对话未配置，请联系管理员配置 DeepSeek API")

    retrieval_context, citations, kg_context, _attach_count = _resolve_answer_context(
        db, user, message, attachment_session_id
    )
    platform_knowledge = _resolve_platform_knowledge(db, user)
    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=retrieval_context,
        platform_knowledge=platform_knowledge,
    )
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"AI 对话暂时不可用: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    reply = (choices[0].get("message", {}) or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        raise bad_request("AI 返回为空")
    out_conv_id = _persist_turn(
        db,
        user_id=user.id if user else None,
        conversation_id=conversation_id,
        message=message,
        reply=reply,
    )
    result: dict[str, Any] = {
        "reply": reply,
        "model": model,
        "conversation_id": out_conv_id,
        **_kg_meta_payload(kg_context),
    }
    if citations:
        result["citations"] = citations
    return result
