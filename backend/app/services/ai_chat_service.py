"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.workflow_events import (
    next_workflow_step_id,
    sse_attachment,
    sse_citations,
    sse_delta,
    sse_done,
    sse_error,
    sse_follow_up,
    sse_replace,
    sse_workflow,
    workflow_event_json,
)
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.kg_service import KgQaContext

from app.core.async_db import release_db, run_db_task
from app.core.prompt_budget import build_bounded_chat_messages
from app.core.session_chat_history import resolve_session_chat_history
from app.core.agent_profiles import resolve_agent_title
from app.services.agent_intent import AgentToolPlan, plan_agent_tools

_logger = logging.getLogger(__name__)


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




def build_ai_home_source_footer(
    *,
    channels: dict[str, bool] | None,
    citations: list[dict] | None,
    kg_context: KgQaContext | None,
    tool_citations: list[dict] | None = None,
) -> str:
    """在结论末尾追加紧凑的来源说明，仅显示引用总数。"""
    all_citations = list(citations or []) + list(tool_citations or [])
    total = len(all_citations)
    return ""


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
) -> tuple[str, list[dict], KgQaContext | None, int, AgentToolPlan, str]:
    attach_count = _attachment_file_count(db, user, attachment_session_id)
    plan = plan_agent_tools(
        message,
        attach_count=attach_count,
        history=history,
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
    reply: str | None = None,
) -> None:
    if db is None or user is None:
        return
    from app.core.async_db import resolve_db_user
    from app.services.agent_context_service import maybe_write_user_memory

    resolved = resolve_db_user(db, user)
    maybe_write_user_memory(resolved.id, message, reply)


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
    plan = plan_agent_tools(
        message,
        attach_count=attach_count,
        history=history,
    )
    return {
        "plan": plan,
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
    """多智能体会话骨架：专精 system 由各 hop 的 build_specialist_chat_messages 注入。"""
    from app.services.agent_context_service import AgentPromptLayers

    layers = layers or AgentPromptLayers()
    return build_bounded_chat_messages(
        system="",
        history=history,
        user_message=message,
        retrieval_context=retrieval_context,
        memory_context=layers.memory_context,
        runtime_context=layers.runtime_context,
        context_instruction=context_instruction or "",
    )


_FOLLOW_UP_SKIP_MARKERS = ("未能生成", "无法回复", "未配置", "暂时无法")

# 空泛推荐：出现则丢弃，宁缺毋滥
_FOLLOW_UP_GENERIC_RE = re.compile(
    r"^(还有什么|具体(是|怎么|如何)|怎么理解|如何看待|详细说说|"
    r"能不能再|可以再|有没有其他|除此之外|下一步怎么办|"
    r"请(再)?(详细|具体)|告诉我更多).{0,8}$"
)


def _should_skip_follow_up(user_message: str, answer: str) -> bool:
    """寒暄、过短或失败回复不生成推荐追问。"""
    from app.services.agent_intent import is_chitchat_message

    msg = (user_message or "").strip()
    ans = (answer or "").strip()
    if not msg or not ans or len(ans) < 40:
        return True
    if is_chitchat_message(msg):
        return True
    if any(marker in ans for marker in _FOLLOW_UP_SKIP_MARKERS):
        return True
    return False


def _normalize_follow_up_question(raw: str) -> str:
    """清洗为纯文本疑问句（去掉 Markdown 与多余标记）。"""
    q = str(raw or "").strip()
    q = re.sub(r"```[\s\S]*?```", " ", q)
    q = re.sub(r"`([^`]+)`", r"\1", q)
    q = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", q)
    q = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", q)
    q = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", q)
    q = re.sub(r"[*_~]+", "", q)
    q = re.sub(r"^\d+[\.\)、]\s*", "", q)
    q = q.strip().strip("？?").strip("。.!！").strip()
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _is_low_quality_follow_up(q: str, *, user_message: str, answer: str) -> bool:
    """过滤复述原问、照抄回答、空泛套话。"""
    if not q or len(q) < 8 or len(q) > 36:
        return True
    ql = q.lower()
    user_l = (user_message or "").strip().lower().rstrip("？?")
    if ql == user_l or ql in user_l or user_l in ql:
        return True
    # 回答中大段照抄（去掉问号后仍是陈述句片段）
    stem = q.rstrip("？?")
    if stem and stem in (answer or ""):
        return True
    if _FOLLOW_UP_GENERIC_RE.match(stem):
        return True
    return False


def generate_follow_up_questions(
    *,
    user_message: str,
    assistant_answer: str,
    history: list[AiChatMessage] | None = None,
) -> list[str]:
    """根据本轮问答快速生成 2 条高价值追问；失败则返回空（不展示劣质兜底）。"""
    from app.core.llm_parse import parse_llm_json
    from app.integrations.deepseek_client import chat_completion_sync, is_configured

    _ = history  # 保留签名兼容；为速度不再塞入长历史
    answer = (assistant_answer or "").strip()
    if _should_skip_follow_up(user_message, answer):
        return []
    if not is_configured():
        return []

    # 截断：只取回答前中段，加快首 token
    answer_snip = re.sub(r"\s+", " ", answer)[:700].strip()
    system = (
        "你是对话助手。根据本轮问答，生成用户最可能继续追问的 2 条短问题。\n"
        '仅返回 JSON：{"questions":["问题1","问题2"]}。\n'
        "质量要求：\n"
        "1. 深挖回答里未展开的要点：对比、数字依据、适用条件、例外、下一步行动；\n"
        "2. 每条 10～28 字，必须是可独立作答的疑问句；纯文本，禁止 Markdown；\n"
        "3. 禁止复述用户原问；禁止把回答原句改成问句；\n"
        "4. 禁止空泛套话（如「还有什么」「详细说说」「具体是什么」）；\n"
        "5. 不要编号、不要解释。"
    )
    user = (
        f"用户：{user_message.strip()[:240]}\n"
        f"助手：{answer_snip}"
    )

    try:
        raw = chat_completion_sync(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.25,
            timeout=3.5,
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
    for item in raw_q:
        q = _normalize_follow_up_question(str(item or ""))
        if not q:
            continue
        if not q.endswith("？") and not q.endswith("?"):
            q += "？"
        if _is_low_quality_follow_up(q, user_message=user_message, answer=answer):
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 2:
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


def _build_display_citations(
    tool_citations: list[dict],
    kg_context: KgQaContext | None,
) -> list[dict]:
    """合并所有来源的引用：工具循环引用 + 知识图谱/本体引用，按 index 去重。"""
    seen: set[int] = set()
    merged: list[dict] = []

    for c in tool_citations:
        idx = c.get("index")
        if idx is not None:
            seen.add(int(idx))
        merged.append(c)

    if kg_context:
        for c in (kg_context.citations or []):
            idx = c.get("index")
            if idx is not None and int(idx) in seen:
                continue
            if idx is not None:
                seen.add(int(idx))
            merged.append(c)

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
    follow_up_task: asyncio.Task | None = None,
) -> AsyncIterator[str]:
    """先结束 workflow，再下发正文与 done；写库与追问建议延后，避免阻塞首屏。"""
    async for payload in _emit_workflow("workflow_finished", title="完成"):
        yield payload

    if normalized_reply and not streamed_content:
        yield sse_replace(normalized_reply)

    if display_citations:
        yield sse_citations(display_citations)

    # 先落库再发 done，避免客户端收到 done 后断开导致会话未写入、历史一直为空
    out_conv_id = await run_db_task(
        _persist_turn,
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        reply=normalized_reply,
    )

    done_payload: dict[str, Any] = {
        "done": True,
        "reply": normalized_reply,
        "conversation_id": out_conv_id or conversation_id,
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
        for att in merged_attachments:
            yield sse_attachment(att)
    yield json.dumps(done_payload, ensure_ascii=False)

    # 回复完成后异步写入本轮对话摘要（不阻塞 SSE）
    asyncio.create_task(
        _defer_maybe_write_user_memory(user_id, message, normalized_reply)
    )

    follow_ups: list[str] = []
    if follow_up_task is not None:
        try:
            # 短等待：生成已与写库并行；超时宁可不展示，避免劣质兜底拖慢收尾
            done_set, pending = await asyncio.wait(
                [follow_up_task], timeout=0.6
            )
            if done_set:
                follow_ups = follow_up_task.result() or []
            for task in pending:
                task.cancel()
        except Exception:
            follow_ups = []
    if follow_ups:
        yield sse_follow_up(follow_ups)


def _kg_meta_payload(kg_context: KgQaContext | None) -> dict[str, Any]:
    if not kg_context:
        return {}
    return {
        "kg_matched_entities": len(kg_context.matched_entity_ids),
        "kg_entity_count": kg_context.entity_count,
        "kg_relation_count": kg_context.relation_count,
    }


async def _emit_workflow(phase: str, **kwargs: Any) -> AsyncIterator[str]:
    yield workflow_event_json(
        phase,
        agent_id="orchestrator",
        agent_title=resolve_agent_title("orchestrator"),
        **kwargs,
    )
    await asyncio.sleep(0)


async def _defer_maybe_write_user_memory(
    user_id: uuid.UUID,
    message: str,
    reply: str | None = None,
) -> None:
    """非关键路径：不阻塞 SSE 收尾；写入本轮对话摘要。"""
    try:
        await run_db_task(_maybe_write_user_memory, user_id, message, reply)
    except Exception:
        pass


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
    model_provider_id: str | None = None,
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    from app.integrations.deepseek_client import set_current_provider_id

    set_current_provider_id(model_provider_id)

    if not is_configured():
        yield sse_error("AI 对话未配置，请联系管理员配置 DeepSeek API")
        return

    msg = (message or "").strip()

    # 普通 Agent：历史加载与开场 workflow 并行，缩短首包等待
    _request_t0 = time.monotonic()
    _logger.info("Agent stream start user=%s msg=%s", user_id, msg[:60])
    history_task = asyncio.create_task(
        run_db_task(
            _resolve_ai_home_history_for_user,
            user_id,
            conversation_id,
            history,
        )
    )
    async for payload in _emit_workflow(
        "workflow_started", title="小析已经收到您的请求，正在规划方案"
    ):
        yield payload
    history = await history_task

    prep = await run_db_task(
        _prepare_ai_chat_stream_plan,
        user_id,
        message,
        attachment_session_id,
        history,
    )
    plan: AgentToolPlan = prep["plan"]

    from app.core.conversation_turn_context import follow_up_thinking_hint

    # 有附件才展示二次规划仪式；普通问答尽快进入 supervisor
    if plan.use_attachment:
        prep_plan_id = next_workflow_step_id("ai-p")
        async for payload in _emit_workflow(
            "agent_thinking",
            title="正在规划方案",
            tool="planner",
            step_id=prep_plan_id,
        ):
            yield payload
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

    # 上下文准备
    attachment_context = ""
    attach_count = int(prep.get("attach_count") or 0)

    kg_context: KgQaContext | None = None
    merged_context = ""
    context_instruction = plan.context_instruction or ""

    attach_id = next_workflow_step_id("ai-s")
    attach_task: asyncio.Task | None = None
    if plan.use_attachment:
        async for payload in _emit_workflow(
            "tool_call",
            title="读取临时附件",
            tool="attachments",
            detail=message.strip()[:120],
            step_id=attach_id,
        ):
            yield payload
        attach_task = asyncio.create_task(
            run_db_task(_resolve_attachment_context, user_id, attachment_session_id)
        )

    if attach_task is not None:
        attachment_context, attach_count = await attach_task
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

    merged_context = attachment_context.strip()
    # 不再预取 prompt layers（memory/runtime 由各专精 hop 的 build_specialist_chat_messages 自行构建）
    messages = [{"role": "user", "content": message}]
    if history:
        for item in history:
            messages.insert(0, {"role": str(item.role), "content": str(item.content or "")})

    from app.services.agent_supervisor import iter_supervised_agent_loop

    tool_reply: str | None = None
    tool_citations: list[dict] = []
    tool_reply_streamed = False
    tool_reply_replaced = False
    tool_stream_attachments: list[dict] = []
    _was_suspended = False
    _suspended_checkpoint_id: str | None = None
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
        skip_route_plan_ui=True,
    ):
        if event.get("type") == "workflow":
            data = event["data"]
            # 检测 checkpoint 暂停事件
            if data.get("phase") == "workflow_finished" and data.get("status") == "suspended":
                _was_suspended = True
                _suspended_checkpoint_id = data.get("checkpoint_id")
            yield sse_workflow(data)
            await asyncio.sleep(0)
        elif event.get("type") == "attachment":
            data = event.get("data")
            if isinstance(data, dict):
                tool_stream_attachments.append(data)
            yield sse_attachment(data)
            await asyncio.sleep(0)
        elif event.get("type") == "delta" and event.get("text"):
            tool_reply_streamed = True
            tool_reply = f"{tool_reply or ''}{event['text']}"
            yield sse_delta(event["text"])
            await asyncio.sleep(0)
        elif event.get("type") == "replace" and event.get("text") is not None:
            tool_reply = str(event["text"])
            tool_reply_replaced = True
            # 立刻推送正文（图谱直答等），不等 turn_tail
            yield sse_replace(tool_reply)
            await asyncio.sleep(0)
        elif event.get("type") == "complete":
            messages = event.get("messages") or messages
            tool_reply = event.get("reply") if event.get("reply") is not None else tool_reply
            tool_citations = list(event.get("citations") or [])
            if event.get("kg_context") is not None:
                kg_context = event.get("kg_context")
            # 未提前出字时，complete 立刻推送，避免等收尾仪式
            if (
                (tool_reply or "").strip()
                and not tool_reply_streamed
                and not tool_reply_replaced
            ):
                tool_reply_replaced = True
                yield sse_replace(str(tool_reply))
                await asyncio.sleep(0)

    if _was_suspended:
        # 正常暂停，不等同于错误
        yield sse_done(suspended=True, checkpoint_id=_suspended_checkpoint_id)
        return

    _elapsed = time.monotonic() - _request_t0
    _logger.info("Agent stream done in %.1fs user=%s msg=%s", _elapsed, user_id, msg[:60])

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
            channels=None,
            citations=[],
            kg_context=kg_context,
            tool_citations=tool_citations,
        )
        # 提前启动 follow-up 生成任务，与 workflow 结尾事件并行执行
        follow_up_task = asyncio.create_task(
            _resolve_follow_up_questions(
                user_message=message,
                assistant_answer=normalized_reply,
                history=history,
            )
        )
        if tool_reply_streamed and normalized_reply and normalized_reply != tool_reply:
            yield sse_replace(normalized_reply)
        display_citations = _build_display_citations(tool_citations, kg_context)
        async for payload in _iter_stream_turn_tail(
            user_id=user_id,
            message=message,
            history=history,
            conversation_id=conversation_id,
            normalized_reply=normalized_reply,
            display_citations=display_citations,
            kg_context=kg_context,
            streamed_content=tool_reply_streamed or tool_reply_replaced,
            tool_loop=True,
            stream_attachments=merged_attachments,
            follow_up_task=follow_up_task,
        ):
            yield payload
        return

    async for payload in _emit_workflow(
        "workflow_finished", title="处理失败", status="failed"
    ):
        yield payload
    yield sse_error("智能体未能生成有效回复，请稍后重试")


async def chat_with_ai_agent(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | uuid.UUID | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    model_provider_id: str | None = None,
    persist_conversation: bool = True,
    write_memory: bool = True,
) -> dict:
    from app.integrations.deepseek_client import set_current_provider_id

    set_current_provider_id(model_provider_id)

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
    ) = await run_db_task(
        _resolve_answer_context,
        user,
        message,
        attachment_session_id,
        history=history,
    )
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
        skip_route_plan_ui=True,
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
            channels=None,
            citations=citations,
            kg_context=merged_kg,
            tool_citations=tool_citations,
        )
        out_conv_id = conversation_id
        if persist_conversation:
            out_conv_id = await run_db_task(
                _persist_turn,
                user_id=coerce_user_id(user),
                conversation_id=conversation_id,
                message=message,
                reply=normalized_reply,
            )
        if write_memory:
            await run_db_task(
                _maybe_write_user_memory,
                user,
                message,
                normalized_reply,
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
