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
from app.core.prompt_budget import build_bounded_chat_messages, llm_completion_extras
from app.services.agent_intent import AgentToolPlan, plan_agent_tools


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


def _resolve_answer_context(
    db: Session | None,
    user: User | None,
    message: str,
    attachment_session_id: str | None = None,
    history: list[AiChatMessage] | None = None,
) -> tuple[str, list[dict], KgQaContext | None, int, AgentToolPlan, str]:
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
    context_instruction = plan.context_instruction or ""
    return (
        merged_context,
        citations,
        kg_context,
        attach_count,
        plan,
        context_instruction,
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


def _try_auto_schedule_reminder(
    db: Session,
    user_id: uuid.UUID,
    message: str,
) -> dict[str, Any] | None:
    """用户消息为明确定时提醒时，服务端直接创建 scheduled_notification。"""
    from app.core.async_db import resolve_db_user
    from app.services import agent_platform_service as plat
    from app.services.agent_intent import parse_scheduled_reminder_request

    parsed = parse_scheduled_reminder_request(message)
    if not parsed:
        return None
    user = resolve_db_user(db, user_id)
    try:
        data = plat.schedule_notification_for_agent(
            db,
            user,
            title=str(parsed["title"]),
            body=str(parsed.get("body") or ""),
            delay_seconds=parsed.get("delay_seconds"),
            delay_minutes=parsed.get("delay_minutes"),
        )
    except ValueError:
        return None
    from app.services.notification_service import preview_scheduled_display

    scheduled_at_display, boost_seconds = preview_scheduled_display(
        delay_seconds=parsed.get("delay_seconds"),
        delay_minutes=parsed.get("delay_minutes"),
    )
    return {
        "message": str(data.get("message") or "已设置定时通知"),
        "boost_seconds": boost_seconds,
        "scheduled_at_display": scheduled_at_display,
        "title": str(parsed["title"]),
    }


async def _reply_after_auto_reminder(
    *,
    message: str,
    history: list[AiChatMessage],
    reminder_result: dict[str, Any],
    layers: Any,
) -> str:
    from app.integrations.deepseek_client import chat_completion_message_async

    when = str(reminder_result.get("scheduled_at_display") or "").strip()
    when_hint = f"具体提醒时间为 {when}。" if when else ""
    confirm_instruction = (
        f"【系统已代为设置定时通知】{reminder_result['message']}。"
        f"{when_hint}"
        "请用一两句简体中文向用户确认提醒已安排好，说明提醒事项与上述具体日期时间，"
        "勿使用「N 分钟后/秒后」等相对倒计时表述，语气自然亲切。"
    )
    messages = _build_chat_messages(
        message=message,
        history=history,
        layers=layers,
        context_instruction=confirm_instruction,
    )
    choice = await chat_completion_message_async(
        messages=messages,
        tools=None,
        temperature=0.4,
    )
    reply = (
        (((choice or {}).get("message") or {}).get("content") or "").strip()
        or f"好的，{reminder_result['message']}"
    )
    return reply


async def _emit_reminder_scheduled_workflow(
    reminder_result: dict[str, Any],
) -> AsyncIterator[str]:
    step_id = next_workflow_step_id("ai-s")
    title = str(reminder_result.get("title") or "")
    when = str(reminder_result.get("scheduled_at_display") or "").strip()
    detail = f"{title} · {when}" if when else title
    boost = reminder_result.get("boost_seconds")
    for phase, title, status in (
        ("tool_call", "设置定时通知", "running"),
        ("tool_result", "定时通知已设置", "done"),
    ):
        ev: dict[str, Any] = {
            "phase": phase,
            "title": title,
            "detail": detail,
            "tool": "platform.notification",
            "tool_name": "schedule_notification",
            "step_id": step_id,
            "status": status,
        }
        if boost is not None:
            ev["boost_seconds"] = int(boost)
        yield json.dumps({"workflow": ev}, ensure_ascii=False)
        await asyncio.sleep(0)


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
    """本析智能不展示引用卡片，仅去除正文中的引用角标。"""
    if not text or not tool_citations:
        return text or ""
    from app.services.knowledge_qa_service import collapse_answer_citation_refs

    normalized, _ = collapse_answer_citation_refs(text, tool_citations)
    return normalized


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

    async for payload in _emit_workflow("workflow_started", title="开始处理问题"):
        yield payload

    think_id = next_workflow_step_id("ai-s")
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
        detail="准备处理用户问题",
        step_id=think_id,
        status="done",
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

    async for payload in _emit_workflow(
        "agent_thought",
        title="已选择处理方式",
        detail=plan.intent_label,
        step_id=think_id,
        status="done",
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
    merged_context = attachment_context.strip()
    context_instruction = plan.context_instruction or ""

    async for payload in _emit_workflow("node_started", title="正在整理上下文"):
        yield payload

    await run_db_task(_maybe_write_user_memory, user_id, message)

    layers = await run_db_task(
        _resolve_prompt_layers,
        user_id,
        message,
        conversation_id=conversation_id,
    )

    auto_reminder = await run_db_task(_try_auto_schedule_reminder, user_id, message)
    if auto_reminder:
        async for payload in _emit_reminder_scheduled_workflow(auto_reminder):
            yield payload
        reply = await _reply_after_auto_reminder(
            message=message,
            history=history,
            reminder_result=auto_reminder,
            layers=layers,
        )
        out_conv_id = await run_db_task(
            _persist_turn,
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            reply=reply,
        )
        done_payload: dict[str, Any] = {
            "done": True,
            "reply": reply,
            "conversation_id": out_conv_id,
            "tool_loop": True,
            "auto_reminder": True,
        }
        yield json.dumps(done_payload, ensure_ascii=False)
        async for payload in _emit_workflow("workflow_finished", title="完成"):
            yield payload
        return

    accumulated = ""
    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=merged_context,
        layers=layers,
        context_instruction=context_instruction,
    )

    from app.core.async_db import resolve_db_user
    from app.database import SessionLocal
    from app.services.agent_supervisor import iter_supervised_agent_loop

    tool_reply: str | None = None
    tool_citations: list[dict] = []
    tool_reply_streamed = False
    tool_reply_replaced = False
    db = SessionLocal()
    try:
        agent_user = resolve_db_user(db, user_id)
        async for event in iter_supervised_agent_loop(
            db,
            agent_user,
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
                kg_context = event.get("kg_context")
    finally:
        db.close()

    if tool_reply:
        normalized_reply = _normalize_ai_home_reply(tool_reply, tool_citations)
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
        ):
            yield payload
        return

    from app.services.llm_workflow_stream import iter_llm_answer_events

    answer_think_id = next_workflow_step_id("ai-s")
    _, _, model = resolve_credentials()
    try:
        async for ev in iter_llm_answer_events(
            messages=messages,
            temperature=0.6,
            think_title="正在生成回答",
            think_detail="综合工具结果并生成回复…",
            step_id=answer_think_id,
        ):
            if ev.get("type") == "workflow":
                yield json.dumps({"workflow": ev["data"]}, ensure_ascii=False)
                await asyncio.sleep(0)
            elif ev.get("type") == "delta" and ev.get("text"):
                accumulated += ev["text"]
                yield json.dumps({"delta": ev["text"]}, ensure_ascii=False)
        normalized_answer = _normalize_ai_home_reply(accumulated, tool_citations)
        if normalized_answer and normalized_answer != accumulated:
            yield json.dumps({"replace": normalized_answer}, ensure_ascii=False)
        async for payload in _iter_stream_turn_tail(
            user_id=user_id,
            message=message,
            history=history,
            conversation_id=conversation_id,
            normalized_reply=normalized_answer,
            display_citations=[],
            kg_context=kg_context,
            streamed_content=bool(accumulated.strip()),
            tool_loop=False,
            model=model,
        ):
            yield payload
    except Exception as e:
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

    release_db(db)
    (
        retrieval_context,
        citations,
        kg_context,
        _attach_count,
        plan,
        context_instruction,
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

    auto_reminder = await run_db_task(_try_auto_schedule_reminder, user.id, message)
    if auto_reminder:
        reply = await _reply_after_auto_reminder(
            message=message,
            history=history,
            reminder_result=auto_reminder,
            layers=layers,
        )
        out_conv_id = await run_db_task(
            _persist_turn,
            user_id=user.id,
            conversation_id=conversation_id,
            message=message,
            reply=reply,
        )
        return {
            "reply": reply,
            "conversation_id": out_conv_id,
            "model": resolve_credentials()[2],
            "tool_loop": True,
            "auto_reminder": True,
        }

    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=retrieval_context,
        layers=layers,
        context_instruction=context_instruction,
    )

    from app.core.async_db import resolve_db_user
    from app.database import SessionLocal
    from app.services.agent_supervisor import iter_supervised_agent_loop

    tool_reply: str | None = None
    tool_citations: list[dict] = []
    kg_context_from_tools: KgQaContext | None = None
    db_session = SessionLocal()
    try:
        agent_user = resolve_db_user(db_session, user)
        async for event in iter_supervised_agent_loop(
            db_session,
            agent_user,
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
    finally:
        db_session.close()

    if tool_reply:
        normalized_reply = _normalize_ai_home_reply(tool_reply, tool_citations)
        out_conv_id = await run_db_task(
            _persist_turn,
            user_id=user.id,
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
            **_kg_meta_payload(kg_context_from_tools),
        }
        if follow_ups:
            result["follow_up_questions"] = follow_ups
        return result
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        **llm_completion_extras(),
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
    normalized_reply = _normalize_ai_home_reply(reply, tool_citations)
    out_conv_id = await run_db_task(
        _persist_turn,
        user_id=user.id if user else None,
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
        "model": model,
        "conversation_id": out_conv_id,
        **_kg_meta_payload(kg_context_from_tools or kg_context),
    }
    if follow_ups:
        result["follow_up_questions"] = follow_ups
    return result
