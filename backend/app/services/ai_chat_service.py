"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import asyncio
import json
import logging
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
    sse_conversation_id,
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


def _fallback_follow_up_questions(answer: str, user_message: str) -> list[str]:
    """LLM 超时或失败时，从回答中提取关键句作为追问候选。"""
    import re

    # 按句号、问号、感叹号、换行分割
    parts = re.split(r"[。！？\n]+", answer)
    candidates: list[str] = []
    seen: set[str] = set()
    user_lower = user_message.strip().lower()

    for p in parts:
        p = p.strip()
        if not p or len(p) < 6:
            continue
        # 跳过与用户问题高度相似的内容
        if p.lower().startswith(user_lower) or user_lower.startswith(p.lower()):
            continue
        key = p[:20].lower()
        if key in seen:
            continue
        seen.add(key)
        # 截取前 30 字作为追问提示
        q = p[:30].strip()
        if not q.endswith("？") and not q.endswith("?"):
            q += "？"
        candidates.append(q)
        if len(candidates) >= 3:
            break

    return candidates


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
            timeout=8.0,
        )
    except Exception:
        return _fallback_follow_up_questions(answer, user_message)

    data = parse_llm_json(raw)
    if not data:
        return _fallback_follow_up_questions(answer, user_message)
    raw_q = data.get("questions") or data.get("follow_up_questions") or []
    if not isinstance(raw_q, list):
        return _fallback_follow_up_questions(answer, user_message)

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
    return out or _fallback_follow_up_questions(answer, user_message)


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
        for att in merged_attachments:
            yield sse_attachment(att)
    yield json.dumps(done_payload, ensure_ascii=False)

    out_conv_id = await run_db_task(
        _persist_turn,
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        reply=normalized_reply,
    )
    if out_conv_id and str(out_conv_id) != str(conversation_id or ""):
        yield sse_conversation_id(out_conv_id)

    follow_ups: list[str] = []
    if follow_up_task is not None:
        try:
            done_set, _ = await asyncio.wait(
                [follow_up_task], timeout=3.0
            )
            if done_set:
                follow_ups = follow_up_task.result()
        except Exception:
            follow_ups = []
    if not follow_ups:
        # 超时或未启动：使用快速文本兜底（不调 LLM），不阻塞 SSE 流
        follow_ups = _fallback_follow_up_questions(normalized_reply, message)
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


async def _defer_maybe_write_user_memory(user_id: uuid.UUID, message: str) -> None:
    """非关键路径：不阻塞首 token。"""
    try:
        await run_db_task(_maybe_write_user_memory, user_id, message)
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

    history = await run_db_task(
        _resolve_ai_home_history_for_user,
        user_id,
        conversation_id,
        history,
    )

    msg = (message or "").strip()

    # ──────────────────────────────────────────────
    # 🟢 THIRD-PARTY AI PREFIX：用户以 #豆包/#千问/#DeepSeek 开头，
    #    直接走免费网页 AI skill，不经过调度智能体。
    # ──────────────────────────────────────────────
    _THIRD_PARTY_AI_PREFIXES: dict[str, str] = {
        "#豆包": "doubao",
        "#千问": "qwen",
        "#DeepSeek": "deepseek",
    }
    _IMAGE_GEN_KEYWORDS = ("画", "生成", "绘制", "图片", "图", "插画", "海报")
    third_party_provider: str | None = None
    third_party_prompt: str = msg
    for prefix, provider_key in _THIRD_PARTY_AI_PREFIXES.items():
        if msg.startswith(prefix):
            third_party_provider = provider_key
            third_party_prompt = msg[len(prefix):].strip()
            break
    if third_party_provider:
        _PROVIDER_LABEL = dict(zip(_THIRD_PARTY_AI_PREFIXES.values(), _THIRD_PARTY_AI_PREFIXES.keys())).get(third_party_provider, third_party_provider)
        if not third_party_prompt:
            reply = f"请在 `{_PROVIDER_LABEL}` 后面输入你的问题"
            async for payload in _iter_stream_turn_tail(
                user_id=user_id, message=message, history=history,
                conversation_id=conversation_id, normalized_reply=reply,
                display_citations=[], kg_context=None,
                streamed_content=False, tool_loop=False,
            ):
                yield payload
            return

        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            reply = "免费网页 AI 功能未启用，请在 .env 中配置 `FREE_WEB_AI_ENABLED=true`"
            async for payload in _iter_stream_turn_tail(
                user_id=user_id, message=message, history=history,
                conversation_id=conversation_id, normalized_reply=reply,
                display_citations=[], kg_context=None,
                streamed_content=False, tool_loop=False,
            ):
                yield payload
            return

        mgr = get_free_web_ai_manager()
        is_image_gen = any(kw in third_party_prompt for kw in _IMAGE_GEN_KEYWORDS)

        provider_label = _PROVIDER_LABEL
        accumulated = ""
        pending_images: list[str] = []
        reply = ""
        result_provider = ""

        try:
            stream_gen = (
                mgr.stream_generate_image(third_party_prompt, provider=third_party_provider)
                if is_image_gen
                else mgr.stream_chat(third_party_prompt, provider=third_party_provider)
            )
            async for chunk in stream_gen:
                ctype = chunk.get("type", "")
                if ctype == "status":
                    # 立即给用户反馈（连接中、生成中…）
                    prefix = f"> 由 **{provider_label}**（免费网页 AI）生成\n\n"
                    yield sse_replace(f"{prefix}*{chunk['message']}*")
                elif ctype == "text":
                    accumulated = chunk["content"]
                    prefix = f"> 由 **{provider_label}**（免费网页 AI）生成\n\n"
                    yield sse_replace(f"{prefix}{accumulated}")
                elif ctype == "images":
                    pending_images = chunk.get("images", [])
                elif ctype == "done":
                    result_provider = chunk.get("provider", provider_label)
                    reply = chunk.get("response", accumulated)
                    # 生图模式追加图片 markdown
                    if is_image_gen and pending_images:
                        image_md = "\n\n" + "\n\n".join(
                            f"![生成图片 {i+1}]({url})" for i, url in enumerate(pending_images)
                        )
                        reply = f"{reply}{image_md}"
                elif ctype == "error":
                    reason = chunk.get("reason", "unknown")
                    reply = f"免费网页 AI 回复失败（{result_provider or provider_label}）：{reason}"
        except Exception as exc:
            reply = f"免费网页 AI 调用异常：{exc}"
            async for payload in _iter_stream_turn_tail(
                user_id=user_id, message=message, history=history,
                conversation_id=conversation_id, normalized_reply=reply,
                display_citations=[], kg_context=None,
                streamed_content=False, tool_loop=False,
            ):
                yield payload
            return

        normalized = f"> 由 **{result_provider or provider_label}**（免费网页 AI）生成\n\n{reply}"
        async for payload in _iter_stream_turn_tail(
            user_id=user_id, message=message, history=history,
            conversation_id=conversation_id, normalized_reply=normalized,
            display_citations=[], kg_context=None,
            streamed_content=True, tool_loop=False,
        ):
            yield payload
        return

    # 初始化前端 workflow（探针的工具调用需要状态容器）
    # 初始化前端 workflow
    _request_t0 = time.monotonic()
    _logger.info("Agent stream start user=%s msg=%s", user_id, msg[:60])
    async for payload in _emit_workflow("workflow_started", title="小析已经收到您的请求，正在规划方案"):
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

    # 上下文准备
    attachment_context = ""
    attach_count = int(prep.get("attach_count") or 0)

    kg_context: KgQaContext | None = None
    merged_context = ""
    context_instruction = plan.context_instruction or ""

    asyncio.create_task(_defer_maybe_write_user_memory(user_id, message))

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
            await asyncio.sleep(0)
        elif event.get("type") == "complete":
            messages = event.get("messages") or messages
            tool_reply = event.get("reply")
            tool_citations = list(event.get("citations") or [])
            if event.get("kg_context") is not None:
                kg_context = event.get("kg_context")

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
    user: User | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    model_provider_id: str | None = None,
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
