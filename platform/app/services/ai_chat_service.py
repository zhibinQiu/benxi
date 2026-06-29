"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.permissions import user_has_permission
from app.core.workflow_events import (
    next_workflow_step_id,
    workflow_event_json,
)
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.kg_service import KgQaContext

from app.core.async_db import release_db, run_db_task
from app.core.agent_resident import build_ai_home_resident_prompt
from app.core.prompt_budget import build_bounded_chat_messages
from app.core.session_chat_history import resolve_session_chat_history
from app.services.agent_intent import (
    AgentToolPlan,
    _PREFETCH_RETRIEVAL_INSTRUCTION,
    plan_agent_tools,
    should_prefetch_knowledge_context,
)


def _kg_enabled_for_user(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.kg_palantir")


def _knowledge_search_enabled(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.knowledge_search")


def _web_search_enabled(db: Session | None) -> bool:
    from app.services.searxng_service import is_enabled

    return is_enabled(db)


def _user_retrieval_flags(db: Session, user: User) -> dict[str, bool]:
    return {
        "kb_enabled": _knowledge_search_enabled(db, user),
        "kg_enabled": _kg_enabled_for_user(db, user),
        "web_enabled": _web_search_enabled(db),
    }


def _resolve_ai_home_history(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    client_history: list[AiChatMessage],
) -> list[AiChatMessage]:
    return resolve_session_chat_history(
        db,
        user_id=user.id,
        scope="ai-home",
        conversation_id=conversation_id,
        client_history=client_history,
    )


def _attachment_file_count(
    db: Session | None,
    user: uuid.UUID | User | None,
    attachment_session_id: str | None,
) -> int:
    if db is None or user is None or not (attachment_session_id or "").strip():
        return 0
    from app.core.async_db import resolve_db_user
    from app.services.ai_chat_attachment_service import get_owned_session

    user = resolve_db_user(db, user)

    try:
        manifest = get_owned_session(user.id, attachment_session_id)
    except Exception:
        return 0
    return len(manifest.get("files") or [])


def _resolve_attachment_context(
    db: Session | None,
    user: uuid.UUID | User | None,
    attachment_session_id: str | None,
) -> tuple[str, int]:
    if db is None or user is None or not (attachment_session_id or "").strip():
        return "", 0
    from app.core.async_db import resolve_db_user
    from app.services.ai_chat_attachment_service import (
        build_attachment_context,
        get_owned_session,
    )

    user = resolve_db_user(db, user)

    try:
        manifest = get_owned_session(user.id, attachment_session_id)
    except Exception:
        return "", 0
    files = manifest.get("files") or []
    return build_attachment_context(files), len(files)


_DOC_CITATION_SOURCES = frozenset({"local", "local_filename", "knowflow"})
_WEB_CITATION_SOURCES = frozenset({"web", "searxng", "internet"})


def _merge_attachment_and_research_context(
    attachment_context: str,
    research_context: str,
) -> str:
    parts = [p.strip() for p in (attachment_context, research_context) if p.strip()]
    return "\n\n".join(parts)


def _prefetch_knowledge_research(
    db: Session | None,
    user: User | None,
    message: str,
    history: list[AiChatMessage] | None,
    *,
    kb_enabled: bool,
    kg_enabled: bool,
) -> tuple[str, list[dict], KgQaContext | None, dict[str, bool]]:
    if db is None or user is None:
        return "", [], None, {"kb": False, "kg": False, "web": False}
    from app.core.async_db import resolve_db_user
    from app.services.skill_chat_service import resolve_combined_research_sync

    resolved = resolve_db_user(db, user)
    merged, citations, kg_context, channels = resolve_combined_research_sync(
        db,
        resolved,
        message,
        use_kb=kb_enabled,
        use_kg=kg_enabled,
        use_web=False,
    )
    return merged, citations, kg_context, channels


def build_ai_home_source_footer(
    *,
    channels: dict[str, bool] | None,
    citations: list[dict] | None,
    kg_context: KgQaContext | None,
    tool_citations: list[dict] | None = None,
) -> str:
    """在结论末尾追加紧凑的来源说明（本析不展示引用卡片）。"""
    all_citations = list(citations or []) + list(tool_citations or [])
    doc_count = sum(
        1 for c in all_citations if str(c.get("source") or "") in _DOC_CITATION_SOURCES
    )
    web_count = sum(
        1 for c in all_citations if str(c.get("source") or "") in _WEB_CITATION_SOURCES
    )
    ch = channels or {}
    parts: list[str] = []
    if kg_context and (
        kg_context.entity_count
        or kg_context.relation_count
        or kg_context.matched_entity_ids
        or (kg_context.context_text or "").strip()
    ):
        ec = kg_context.entity_count or len(kg_context.matched_entity_ids or [])
        rc = kg_context.relation_count or 0
        label = f"本体图谱（{ec} 实体"
        if rc:
            label += f" / {rc} 关系"
        label += "）"
        parts.append(label)
    elif ch.get("kg"):
        parts.append("本体图谱")
    if doc_count:
        parts.append(f"知识库（{doc_count} 条片段）")
    elif ch.get("kb"):
        parts.append("知识库")
    if web_count:
        parts.append(f"联网检索（{web_count} 条）")
    elif ch.get("web"):
        parts.append("联网检索")
    if not parts:
        return ""
    return "\n\n---\n**参考来源**：" + " · ".join(parts)


def _append_ai_home_source_footer(
    reply: str,
    *,
    channels: dict[str, bool] | None,
    citations: list[dict] | None,
    kg_context: KgQaContext | None,
    tool_citations: list[dict] | None = None,
) -> str:
    body = (reply or "").strip()
    footer = build_ai_home_source_footer(
        channels=channels,
        citations=citations,
        kg_context=kg_context,
        tool_citations=tool_citations,
    )
    if not footer or footer in body:
        return body
    return f"{body}{footer}"


def _resolve_answer_context(
    db: Session | None,
    user: User | None,
    message: str,
    attachment_session_id: str | None = None,
    history: list[AiChatMessage] | None = None,
) -> tuple[str, list[dict], KgQaContext | None, int, AgentToolPlan, str, dict[str, bool]]:
    attach_count = _attachment_file_count(db, user, attachment_session_id)
    flags = (
        _user_retrieval_flags(db, user)
        if db is not None and user is not None
        else {"kb_enabled": False, "kg_enabled": False, "web_enabled": _web_search_enabled(db)}
    )
    plan = plan_agent_tools(
        message,
        attach_count=attach_count,
        history=history,
        **flags,
    )

    attachment_context = ""
    if plan.use_attachment:
        attachment_context, attach_count = _resolve_attachment_context(
            db, user, attachment_session_id
        )

    merged_context = attachment_context.strip()
    citations: list[dict] = []
    kg_context: KgQaContext | None = None
    research_channels: dict[str, bool] = {"kb": False, "kg": False, "web": False}
    context_instruction = plan.context_instruction or ""

    if should_prefetch_knowledge_context(message, history, plan):
        research_context, citations, kg_context, research_channels = (
            _prefetch_knowledge_research(
                db,
                user,
                message,
                history,
                kb_enabled=flags["kb_enabled"],
                kg_enabled=flags["kg_enabled"],
            )
        )
        merged_context = _merge_attachment_and_research_context(
            attachment_context,
            research_context,
        )
        if research_context.strip():
            if context_instruction.strip():
                context_instruction = f"{context_instruction}\n\n{_PREFETCH_RETRIEVAL_INSTRUCTION}"
            else:
                context_instruction = _PREFETCH_RETRIEVAL_INSTRUCTION

    return (
        merged_context,
        citations,
        kg_context,
        attach_count,
        plan,
        context_instruction,
        research_channels,
    )


def _resolve_prompt_layers(
    db: Session | None,
    user: User | None,
    message: str,
    *,
    conversation_id: str | None = None,
) -> "AgentPromptLayers":
    from app.core.async_db import resolve_db_user
    from app.services.agent_context_service import (
        AgentPromptLayers,
        resolve_agent_prompt_layers,
    )

    if db is None or user is None:
        return AgentPromptLayers()
    user = resolve_db_user(db, user)
    return resolve_agent_prompt_layers(
        db,
        user,
        message,
        channel="ai-home",
        conversation_id=conversation_id,
    )


def _maybe_write_user_memory(
    db: Session | None,
    user: User | uuid.UUID | None,
    message: str,
) -> None:
    if db is None or user is None:
        return
    from app.core.async_db import resolve_db_user
    from app.services.agent_context_service import maybe_write_user_memory

    resolved = resolve_db_user(db, user)
    maybe_write_user_memory(resolved.id, message)


def _prepare_ai_chat_stream_plan(
    db: Session,
    user_id: uuid.UUID,
    message: str,
    attachment_session_id: str | None,
    history: list[AiChatMessage] | None,
) -> dict[str, Any]:
    """单次 DB 会话：读取开关并生成 Agent 工具计划。"""
    from app.core.async_db import resolve_db_user

    user = resolve_db_user(db, user_id)
    attach_count = _attachment_file_count(db, user, attachment_session_id)
    flags = _user_retrieval_flags(db, user)
    plan = plan_agent_tools(
        message,
        attach_count=attach_count,
        history=history,
        **flags,
    )
    return {
        "plan": plan,
        **flags,
        "attach_count": attach_count,
    }


def _build_chat_messages(
    *,
    message: str,
    history: list[AiChatMessage],
    retrieval_context: str = "",
    layers: "AgentPromptLayers | None" = None,
    context_instruction: str = "",
) -> list[dict]:
    from app.services.agent_context_service import AgentPromptLayers

    layers = layers or AgentPromptLayers()
    return build_bounded_chat_messages(
        system=build_ai_home_resident_prompt(),
        history=history,
        user_message=message,
        retrieval_context=retrieval_context,
        platform_knowledge=layers.platform_knowledge,
        skill_catalog=layers.skill_catalog,
        activated_skills=layers.activated_skills,
        runtime_context=layers.runtime_context,
        memory_context=layers.memory_context,
        context_instruction=context_instruction or "",
    )


_FOLLOW_UP_SKIP_MARKERS = ("未能生成", "无法回复", "未配置", "暂时无法")


def generate_follow_up_questions(
    *,
    user_message: str,
    assistant_answer: str,
    history: list[AiChatMessage] | None = None,
) -> list[str]:
    """根据本轮问答生成 2～3 条可继续追问的短问题。"""
    from app.core.llm_parse import parse_llm_json
    from app.integrations.deepseek_client import chat_completion_sync, is_configured

    answer = (assistant_answer or "").strip()
    if not answer or len(answer) < 16:
        return []
    if any(marker in answer for marker in _FOLLOW_UP_SKIP_MARKERS):
        return []
    if not is_configured():
        return []

    hist_lines: list[str] = []
    for msg in (history or [])[-4:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:200]
        if text:
            hist_lines.append(f"{role}：{text}")
    hist_block = "\n".join(hist_lines)

    system = (
        "你是企业知识助手「小析」。根据本轮问答，生成用户可能继续追问的短问题。"
        '仅返回 JSON：{"questions":["问题1","问题2"]}。'
        "要求：2～3 条；每条 8～40 字；具体、可独立作答；不要重复用户刚问过的问题；"
        "不要编号、不要解释。"
    )
    user = f"用户问题：{user_message.strip()[:500]}\n助手回答：{answer[:2000]}"
    if hist_block:
        user = f"近期对话：\n{hist_block}\n\n{user}"

    try:
        raw = chat_completion_sync(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            timeout=25.0,
        )
    except Exception:
        return []

    data = parse_llm_json(raw)
    if not data:
        return []
    raw_q = data.get("questions") or data.get("follow_up_questions") or []
    if not isinstance(raw_q, list):
        return []

    seen: set[str] = set()
    out: list[str] = []
    user_norm = user_message.strip().lower()
    for item in raw_q:
        q = str(item or "").strip().strip("？?").strip()
        if not q:
            continue
        if not q.endswith("？") and not q.endswith("?"):
            q += "？"
        key = q.lower()
        if key in seen or key == user_norm:
            continue
        seen.add(key)
        out.append(q[:80])
        if len(out) >= 3:
            break
    return out


async def _resolve_follow_up_questions(
    *,
    user_message: str,
    assistant_answer: str,
    history: list[AiChatMessage] | None = None,
) -> list[str]:
    return await asyncio.to_thread(
        generate_follow_up_questions,
        user_message=user_message,
        assistant_answer=assistant_answer,
        history=history,
    )


def _normalize_ai_home_reply(text: str, tool_citations: list[dict] | None) -> str:
    """本析智能不展示引用卡片，仅去除正文中的引用角标与内部调试内容。"""
    from app.core.agent_message_parse import (
        extract_embedded_tool_calls,
        sanitize_agent_user_reply,
    )

    raw = (text or "").strip()
    clean = sanitize_agent_user_reply(raw)
    if clean:
        body = clean
    elif extract_embedded_tool_calls(raw)[1]:
        body = ""
    else:
        body = raw
    if not body or not tool_citations:
        return body
    from app.services.knowledge_qa_service import collapse_answer_citation_refs

    normalized, _ = collapse_answer_citation_refs(body, tool_citations)
    return normalized


def _merge_stream_attachments(
    reply: str | None,
    attachments: list[dict] | None,
) -> list[dict]:
    """合并流式 attachment 与回复正文中的截图引用。"""
    from app.services.agent_orchestrator import extract_image_attachments_from_markdown

    seen: set[str] = set()
    merged: list[dict] = []
    for item in list(attachments or []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(dict(item))
    for item in extract_image_attachments_from_markdown(reply):
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(dict(item))
    return merged


async def _iter_stream_turn_tail(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
    conversation_id: str | None,
    normalized_reply: str,
    display_citations: list[dict],
    kg_context: KgQaContext | None,
    streamed_content: bool = False,
    tool_loop: bool = False,
    model: str | None = None,
    stream_attachments: list[dict] | None = None,
) -> AsyncIterator[str]:
    """先结束 workflow，再下发正文与 done；写库与追问建议延后，避免阻塞首屏。"""
    async for payload in _emit_workflow("workflow_finished", title="完成"):
        yield payload

    if normalized_reply and not streamed_content:
        yield json.dumps({"replace": normalized_reply}, ensure_ascii=False)

    if display_citations:
        yield json.dumps({"citations": display_citations}, ensure_ascii=False)

    done_payload: dict[str, Any] = {
        "done": True,
        "reply": normalized_reply,
        "conversation_id": conversation_id,
        "tool_loop": tool_loop,
        **_kg_meta_payload(kg_context),
    }
    if model:
        done_payload["model"] = model
    if display_citations:
        done_payload["citations"] = display_citations
    merged_attachments = _merge_stream_attachments(normalized_reply, stream_attachments)
    if merged_attachments:
        done_payload["attachments"] = merged_attachments
        yield json.dumps({"attachments": merged_attachments}, ensure_ascii=False)
    yield json.dumps(done_payload, ensure_ascii=False)

    out_conv_id = await run_db_task(
        _persist_turn,
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        reply=normalized_reply,
    )
    if out_conv_id and str(out_conv_id) != str(conversation_id or ""):
        yield json.dumps({"conversation_id": out_conv_id}, ensure_ascii=False)

    follow_ups = await _resolve_follow_up_questions(
        user_message=message,
        assistant_answer=normalized_reply,
        history=history,
    )
    if follow_ups:
        yield json.dumps({"follow_up_questions": follow_ups}, ensure_ascii=False)


def _kg_meta_payload(kg_context: KgQaContext | None) -> dict[str, Any]:
    if not kg_context:
        return {}
    return {
        "kg_matched_entities": len(kg_context.matched_entity_ids),
        "kg_entity_count": kg_context.entity_count,
        "kg_relation_count": kg_context.relation_count,
    }


async def _emit_workflow(phase: str, **kwargs: Any) -> AsyncIterator[str]:
    yield workflow_event_json(phase, **kwargs)
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


def _resolve_ai_home_history_for_user(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: str | None,
    client_history: list[AiChatMessage],
) -> list[AiChatMessage]:
    from app.core.async_db import resolve_db_user

    user = resolve_db_user(db, user_id)
    return _resolve_ai_home_history(
        db,
        user,
        conversation_id=conversation_id,
        client_history=client_history,
    )


async def iter_chat_with_ai_agent_stream(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    if not is_configured():
        yield json.dumps({"error": "AI 对话未配置，请联系管理员配置 DeepSeek API"}, ensure_ascii=False)
        return

    history = await run_db_task(
        _resolve_ai_home_history_for_user,
        user_id,
        conversation_id,
        history,
    )

    async for payload in _emit_workflow("workflow_started", title="开始处理问题"):
        yield payload

    prep_plan_id = next_workflow_step_id("ai-p")
    async for payload in _emit_workflow(
        "agent_thinking",
        title="正在规划方案",
        tool="planner",
        step_id=prep_plan_id,
    ):
        yield payload

    prep = await run_db_task(
        _prepare_ai_chat_stream_plan,
        user_id,
        message,
        attachment_session_id,
        history,
    )
    plan: AgentToolPlan = prep["plan"]

    from app.core.conversation_turn_context import follow_up_thinking_hint

    prep_detail = (plan.context_instruction or plan.intent_label or "已分析请求").strip()
    context_hint = follow_up_thinking_hint(message, history)
    if context_hint:
        prep_detail = f"{context_hint}；{prep_detail}" if prep_detail else context_hint
    prep_title = f"规划方案：{plan.intent_label or '已分析请求'}"
    async for payload in _emit_workflow(
        "agent_thought",
        title=prep_title,
        detail=prep_detail[:240],
        tool="planner",
        status="done",
        step_id=prep_plan_id,
    ):
        yield payload

    doc_context = ""
    doc_citations: list[dict] = []
    attachment_context = ""
    attach_count = int(prep.get("attach_count") or 0)

    attach_id = next_workflow_step_id("ai-s")
    if plan.use_attachment:
        async for payload in _emit_workflow(
            "tool_call",
            title="读取临时附件",
            tool="attachments",
            detail=message.strip()[:120],
            step_id=attach_id,
        ):
            yield payload
        attachment_context, attach_count = await run_db_task(
            _resolve_attachment_context, user_id, attachment_session_id
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

    kg_context: KgQaContext | None = None
    prefetched_citations: list[dict] = []
    research_channels: dict[str, bool] = {"kb": False, "kg": False, "web": False}
    merged_context = attachment_context.strip()
    context_instruction = plan.context_instruction or ""

    if should_prefetch_knowledge_context(message, history, plan):
        prefetch_id = next_workflow_step_id("ai-k")
        async for payload in _emit_workflow(
            "tool_call",
            title="检索知识库与本体图谱",
            tool="knowledge_prefetch",
            detail=message.strip()[:120],
            step_id=prefetch_id,
        ):
            yield payload
        research_context, prefetched_citations, kg_context, research_channels = (
            await run_db_task(
                _prefetch_knowledge_research,
                user_id,
                message,
                history,
                kb_enabled=bool(prep.get("kb_enabled")),
                kg_enabled=bool(prep.get("kg_enabled")),
            )
        )
        merged_context = _merge_attachment_and_research_context(
            attachment_context,
            research_context,
        )
        if research_context.strip():
            if context_instruction.strip():
                context_instruction = (
                    f"{context_instruction}\n\n{_PREFETCH_RETRIEVAL_INSTRUCTION}"
                )
            else:
                context_instruction = _PREFETCH_RETRIEVAL_INSTRUCTION
        doc_hits = sum(
            1
            for c in prefetched_citations
            if str(c.get("source") or "") in _DOC_CITATION_SOURCES
        )
        if kg_context and kg_context.matched_entity_ids:
            prefetch_detail = (
                f"知识库 {doc_hits} 条片段；"
                f"图谱匹配 {len(kg_context.matched_entity_ids)} 个实体"
            )
        elif doc_hits:
            prefetch_detail = f"知识库命中 {doc_hits} 条片段"
        elif kg_context and (kg_context.context_text or "").strip():
            prefetch_detail = "已加载本体图谱关联"
        else:
            prefetch_detail = "未命中相关知识库片段或图谱实体"
        async for payload in _emit_workflow(
            "tool_result",
            title="预检索完成",
            tool="knowledge_prefetch",
            detail=prefetch_detail,
            step_id=prefetch_id,
            status="done",
        ):
            yield payload

    await run_db_task(_maybe_write_user_memory, user_id, message)

    layers = await run_db_task(
        _resolve_prompt_layers,
        user_id,
        message,
        conversation_id=conversation_id,
    )

    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=merged_context,
        layers=layers,
        context_instruction=context_instruction,
    )

    from app.services.agent_supervisor import iter_supervised_agent_loop

    tool_reply: str | None = None
    tool_citations: list[dict] = []
    tool_reply_streamed = False
    tool_reply_replaced = False
    tool_stream_attachments: list[dict] = []
    async for event in iter_supervised_agent_loop(
        user_id,
        messages,
        conversation_id=conversation_id,
        user_message=message,
        attachment_session_id=attachment_session_id,
        intent_plan=plan,
        chat_history=history,
        retrieval_context=merged_context,
        context_instruction=context_instruction,
    ):
        if event.get("type") == "workflow":
            yield json.dumps({"workflow": event["data"]}, ensure_ascii=False)
            await asyncio.sleep(0)
        elif event.get("type") == "attachment":
            data = event.get("data")
            if isinstance(data, dict):
                tool_stream_attachments.append(data)
            yield json.dumps({"attachments": [event["data"]]}, ensure_ascii=False)
            await asyncio.sleep(0)
        elif event.get("type") == "delta" and event.get("text"):
            tool_reply_streamed = True
            tool_reply = f"{tool_reply or ''}{event['text']}"
            yield json.dumps({"delta": event["text"]}, ensure_ascii=False)
            await asyncio.sleep(0)
        elif event.get("type") == "replace" and event.get("text") is not None:
            tool_reply = str(event["text"])
            tool_reply_replaced = True
            await asyncio.sleep(0)
        elif event.get("type") == "complete":
            messages = event.get("messages") or messages
            tool_reply = event.get("reply")
            tool_citations = list(event.get("citations") or [])
            if event.get("kg_context") is not None:
                kg_context = event.get("kg_context")

    merged_attachments = _merge_stream_attachments(tool_reply, tool_stream_attachments)
    if (tool_reply or "").strip() or merged_attachments:
        normalized_reply = _normalize_ai_home_reply(tool_reply or "", tool_citations)
        if not (normalized_reply or "").strip() and merged_attachments:
            normalized_reply = "已完成您要求的浏览器操作，页面截图如下。"
        if merged_attachments:
            from app.services.agent_orchestrator import append_screenshot_markdown_to_reply

            normalized_reply = (
                append_screenshot_markdown_to_reply(normalized_reply, merged_attachments)
                or normalized_reply
            )
        normalized_reply = _append_ai_home_source_footer(
            normalized_reply,
            channels=research_channels,
            citations=prefetched_citations,
            kg_context=kg_context,
            tool_citations=tool_citations,
        )
        if tool_reply_streamed and normalized_reply and normalized_reply != tool_reply:
            yield json.dumps({"replace": normalized_reply}, ensure_ascii=False)
        async for payload in _iter_stream_turn_tail(
            user_id=user_id,
            message=message,
            history=history,
            conversation_id=conversation_id,
            normalized_reply=normalized_reply,
            display_citations=[],
            kg_context=kg_context,
            streamed_content=tool_reply_streamed or tool_reply_replaced,
            tool_loop=True,
            stream_attachments=merged_attachments,
        ):
            yield payload
        return

    async for payload in _emit_workflow(
        "workflow_finished", title="处理失败", status="failed"
    ):
        yield payload
    yield json.dumps(
        {"error": "智能体未能生成有效回复，请稍后重试"},
        ensure_ascii=False,
    )


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

    if db is not None and user is not None:
        from app.core.async_db import resolve_db_user

        history = _resolve_ai_home_history(
            db,
            resolve_db_user(db, user),
            conversation_id=conversation_id,
            client_history=history,
        )

    release_db(db)
    (
        retrieval_context,
        citations,
        kg_context,
        _attach_count,
        plan,
        context_instruction,
        research_channels,
    ) = await run_db_task(
        _resolve_answer_context,
        user,
        message,
        attachment_session_id,
        history=history,
    )
    await run_db_task(_maybe_write_user_memory, user, message)
    layers = await run_db_task(
        _resolve_prompt_layers,
        user,
        message,
        conversation_id=conversation_id,
    )

    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=retrieval_context,
        layers=layers,
        context_instruction=context_instruction,
    )

    from app.core.agent_loop_session import coerce_user_id
    from app.services.agent_supervisor import iter_supervised_agent_loop

    if user is None:
        raise bad_request("缺少用户信息")

    tool_reply: str | None = None
    tool_citations: list[dict] = []
    kg_context_from_tools: KgQaContext | None = None
    async for event in iter_supervised_agent_loop(
        coerce_user_id(user),
        messages,
        conversation_id=conversation_id,
        user_message=message,
        attachment_session_id=attachment_session_id,
        intent_plan=plan,
        chat_history=history,
        retrieval_context=retrieval_context,
        context_instruction=context_instruction,
    ):
        if event.get("type") == "complete":
            messages = event.get("messages") or messages
            tool_reply = event.get("reply")
            tool_citations = list(event.get("citations") or [])
            kg_context_from_tools = event.get("kg_context")

    if tool_reply:
        merged_kg = kg_context_from_tools or kg_context
        normalized_reply = _normalize_ai_home_reply(tool_reply, tool_citations)
        normalized_reply = _append_ai_home_source_footer(
            normalized_reply,
            channels=research_channels,
            citations=citations,
            kg_context=merged_kg,
            tool_citations=tool_citations,
        )
        out_conv_id = await run_db_task(
            _persist_turn,
            user_id=coerce_user_id(user),
            conversation_id=conversation_id,
            message=message,
            reply=normalized_reply,
        )
        follow_ups = await _resolve_follow_up_questions(
            user_message=message,
            assistant_answer=normalized_reply,
            history=history,
        )
        result: dict[str, Any] = {
            "reply": normalized_reply,
            "conversation_id": out_conv_id,
            "model": resolve_credentials()[2],
            "tool_loop": True,
            **_kg_meta_payload(merged_kg),
        }
        if follow_ups:
            result["follow_up_questions"] = follow_ups
        return result
    raise bad_request("智能体未能生成有效回复，请稍后重试")
