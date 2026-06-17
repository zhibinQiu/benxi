"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.permissions import user_has_permission
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.kg_service import KgQaContext, merge_kg_qa_into_context, retrieve_kg_context_for_question

_MAX_HISTORY = 20
_MAX_QUERYABLE_DOCS = 20

_SYSTEM_PROMPT = """你是「AI 智能体」，企业 AI 知识库平台的内置智能助手。

你的能力包括：
- 解答文档管理、权限分享、PDF 翻译、知识检索等平台使用问题
- 结合权限内文档检索片段与本体图谱实体关系，回答业务相关问题
- 协助梳理办公场景下的信息整理、写作润色与数据分析思路

回答要求：
- 使用简体中文，结构清晰，可使用简短 Markdown
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


def _resolve_answer_context(
    db: Session | None,
    user: User | None,
    message: str,
) -> tuple[str, list[dict], KgQaContext | None]:
    doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)
    kg_context = _resolve_kg_context(db, user, message)
    merged_context, citations = merge_kg_qa_into_context(
        doc_context, doc_citations, kg_context
    )
    return merged_context, citations, kg_context


def _build_chat_messages(
    *,
    message: str,
    history: list[AiChatMessage],
    retrieval_context: str = "",
) -> list[dict]:
    system = _SYSTEM_PROMPT
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
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    if not is_configured():
        yield json.dumps({"error": "AI 对话未配置，请联系管理员配置 DeepSeek API"}, ensure_ascii=False)
        return

    retrieval_context, citations, kg_context = _resolve_answer_context(db, user, message)
    if citations:
        yield json.dumps({"citations": citations}, ensure_ascii=False)

    accumulated = ""
    messages = _build_chat_messages(
        message=message, history=history, retrieval_context=retrieval_context
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
    except httpx.HTTPError as e:
        yield json.dumps({"error": f"无法连接 AI 服务: {e}"}, ensure_ascii=False)


async def chat_with_ai_agent(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | None = None,
    conversation_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("AI 对话未配置，请联系管理员配置 DeepSeek API")

    retrieval_context, citations, kg_context = _resolve_answer_context(db, user, message)
    messages = _build_chat_messages(
        message=message, history=history, retrieval_context=retrieval_context
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
