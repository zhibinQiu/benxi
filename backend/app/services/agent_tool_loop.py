"""AI 智能体 tool-calling 多轮循环 — Loop Engineering 主实现。

六相循环：
  1 输入捕获     — user_message / intent_plan / resolve_execution_plan
  2 上下文组装   — inject_retrieval_context_message / build_plan_context_instruction
  3 模型推理     — chat_completion_message_async
  4 动作执行     — execute_agent_tool（含本轮去重缓存）
  5 观测校验     — execution_goal_satisfied / request_fulfilled
  6 记忆更新     — loop_state + resolve_adaptive_replan → 回到 2
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_loop_session import AgentLoopSession
from app.core.aip.handoff import build_specialist_assist_handoff
from app.agentkit.aip.messaging import attach_handoff_to_complete
from app.integrations.deepseek_client import chat_completion_stream_choice
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_reply_synth import (
    finalize_specialist_handoff,
    iter_synthesize_tool_loop_user_reply_events,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
)
from app.services.agent_intent import AgentToolPlan
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    AgentExecutionPlan,
    build_plan_context_instruction,
    filter_tool_specs_by_plan,
    resolve_execution_plan,
    resolve_kg_planning_context,
)
from app.core.agent_message_parse import (
    assistant_content_is_deliverable,
    normalize_llm_assistant_message,
    strip_dsml_markup,
)
from app.core.agent_tool_context import (
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    lookup_cached_tool_result,
    record_executed_tool_call,
    trim_agent_loop_messages,
)
from app.services.agent_skill_router import is_skill_management_message
from app.services.agent_tools import (
    build_agent_tool_specs,
    execute_agent_tool,
    maybe_inject_skill_dev_playbook,
    maybe_inject_skill_md,
    record_stream_screenshot_attachment,
    tool_workflow_meta,
)
from app.services.agent_skill_runtime import build_agent_runtime_tool_specs
from app.services.agent_profile_service import resolve_effective_runtime_tool_names
from app.core.agent_checkpoint import (
    clear_checkpoint,
    generate_checkpoint_id,
    save_checkpoint,
)
from app.core.agent_loop_state import LoopState
from app.core.human_in_the_loop import (
    build_confirmation_summary,
    clear_pending_choice,
    clear_pending_confirmation,
    generate_choice_id,
    generate_confirmation_id,
    get_choice_response,
    get_confirm_response,
    is_confirmation_required,
    set_pending_choice,
    set_pending_confirmation,
)

_logger = logging.getLogger(__name__)


def _default_max_rounds() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "agent_max_tool_rounds", 40) or 40))


def _parse_tool_summary(result_text: str) -> tuple[bool, str]:
    try:
        body = json.loads(result_text)
        if isinstance(body, dict):
            return bool(body.get("ok")), str(body.get("summary") or "")
    except json.JSONDecodeError:
        pass
    return False, result_text[:200]


def _tool_timeout() -> int:
    from app.config import get_settings

    return max(10, int(get_settings().agent_tool_timeout_sec or 60))


def _is_retryable_error(result_text: str) -> bool:
    """判断工具错误是否可能是临时故障（超时/网络/数据库），值得自动重试一次。"""
    try:
        body = json.loads(result_text)
        summary = str(body.get("summary", "")).lower()
    except (json.JSONDecodeError, TypeError):
        return False
    retryable_keywords = [
        "timeout", "timed out", "超时",
        "connection", "connect", "网络",
        "database error", "数据库",
        "temporary", "temporarily",
        "too many requests", "rate limit",
    ]
    return any(kw in summary for kw in retryable_keywords)


def _workflow_result_title(meta: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return str(meta.get("result_title") or meta.get("title") or "完成")
    failure = meta.get("failure_title")
    if failure:
        return str(failure)
    base = str(meta.get("title") or meta.get("result_title") or "操作")
    return f"{base}（失败）"


def _finalize_loop_reply(reply: str | None, loop_state: LoopState) -> str | None:
    from app.services.agent_orchestrator import append_screenshot_markdown_to_reply

    attachments = list(loop_state.get("collected_attachments") or [])
    if not attachments:
        return reply
    return append_screenshot_markdown_to_reply(reply, attachments)


def _streamed_attachment_urls(loop_state: LoopState) -> set[str]:
    return {
        str(url).strip()
        for url in (loop_state.get("streamed_attachment_urls") or [])
        if str(url).strip()
    }


def _mark_streamed_attachment(loop_state: LoopState, att: dict[str, Any]) -> None:
    url = str(att.get("url") or "").strip()
    if not url:
        return
    seen = _streamed_attachment_urls(loop_state)
    seen.add(url)
    loop_state["streamed_attachment_urls"] = sorted(seen)


def _pending_screenshot_attachments(loop_state: LoopState) -> list[dict[str, Any]]:
    """尚未通过 SSE attachment 下发的截图。"""
    streamed = _streamed_attachment_urls(loop_state)
    pending: list[dict[str, Any]] = []
    for att in list(loop_state.get("collected_attachments") or []):
        if not isinstance(att, dict):
            continue
        url = str(att.get("url") or "").strip()
        if not url or url in streamed:
            continue
        pending.append(dict(att))
        streamed.add(url)
    loop_state["streamed_attachment_urls"] = sorted(streamed)
    return pending


async def _maybe_auto_browser_screenshot(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    loop_state: LoopState,
    user_message: str,
) -> None:
    """用户要求截图且已操作浏览器但未截图时，补拍一张。"""
    from app.services.agent_skill_router import user_wants_browser_screenshot

    if not user_wants_browser_screenshot(user_message):
        return
    if not loop_state.get("browser_session_used"):
        return
    if loop_state.get("collected_attachments"):
        return
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config
    from app.services import browser_rpa_service as rpa

    if not get_browser_rpa_config(db).enabled:
        return
    try:
        data = await rpa.browser_screenshot(db, user, conversation_id=conversation_id)
        record_stream_screenshot_attachment(loop_state, data)
    except Exception as exc:
        _logger.warning("自动浏览器截图失败: %s", exc)


def _available_atomic_from_specs(specs: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for spec in specs:
        name = str((spec.get("function") or {}).get("name") or "")
        if name in RETRIEVAL_ATOMIC_TOOLS:
            names.add(name)
    return names


def _narrow_execution_plan_for_specialist(
    plan: AgentExecutionPlan,
    *,
    agent_id: str | None,
    allowed_skill_names: set[str] | None,
    user_message: str = "",
) -> AgentExecutionPlan:
    """专精智能体边界收窄：仅做 skill 白名单校验 + 无能力时安全回退。

    planner（_build_specialist_domain_plan）已为各专精构建正确计划；
    本函数仅做两层安全兜底：
      1. 如果 plan 引用了不在 allowed_skill_names 中的 skill → 剥离
      2. 如果专精没有任何可用 skill 却需执行 → 转为直接回答，
         防止 LLM 在无边界约束下调用跨域工具

    例外：规则生成的 plan 已经过 explicit skill 匹配，且 uploaded_skill 由
    _rule_plan_for_uploaded_skill_followup 精确匹配产生，应予以信任，
    不在 allowed_skill_names 中时不剥离。
    """
    if (
        allowed_skill_names is not None
        and plan.uploaded_skill
        and plan.source != "rule"
    ):
        if plan.uploaded_skill not in allowed_skill_names:
            plan = replace(plan, uploaded_skill=None)

    aid = (agent_id or "").strip()
    if (
        aid
        and not plan.direct_answer
        and allowed_skill_names is not None
        and not allowed_skill_names
    ):
        # 当前专精没有任何可用 Skill 时强制直接回答，
        # 避免 LLM 调用不属于本域的全局 Tool
        # 例外：plan 有 uploaded_skill 且由规则生成时信任该计划
        if plan.uploaded_skill and plan.source == "rule":
            return plan
        return replace(
            plan,
            intent=plan.intent or f"{aid} 专精",
            direct_answer=True,
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            builtin_orchestration=None,
            steps=(),
        )
    return plan


def _emit_report_reply_deltas(text: str, *, chunk_size: int = 600) -> list[dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return []
    return [
        {"type": "delta", "text": body[i : i + chunk_size]}
        for i in range(0, len(body), chunk_size)
    ]


def _messages_have_prefetched_research(messages: list[dict[str, Any]]) -> bool:
    """首页 prefetch 已注入参考材料时，跳过规划前重复的图谱查询。"""
    marker = "预先检索到的参考材料"
    for row in messages:
        if row.get("role") != "system":
            continue
        if marker in str(row.get("content") or ""):
            return True
    return False


# ─── nudge 消息预构建缓存 ────────────────────────────────────


def _build_nudge_cache(
    user_message: str,
    execution_plan: AgentExecutionPlan,
    plan_has_script: bool | None,
) -> dict[str, str]:
    """预构建 nudge 消息缓存（避免热循环中重复字符串构造）。"""
    from app.services.agent_skill_router import is_platform_system_data_message

    nudges: dict[str, str] = {
        "dsml": (
            "【系统】禁止在正文输出 DSML / tool_calls 标记。"
            "必须通过 API tool_calls 调用 knowledge_retrieve、web_search、"
            "load_uploaded_skill；content 留空即可。"
        ),
        "instruction": (
            "【系统】必须通过 tool_calls 执行操作并拿到真实结果后再回答。"
            "如果你写了「我来搜索」「已安排通知」等文字而没有实际调用工具，"
            "请立即调用 web_search 等工具获取真实数据后再回答。"
            "若工具/Skill 调用返回了失败信息，**必须**如实告知用户错误详情，"
            "禁止编造数据来掩盖调用失败。宁可说「无法执行」也不可伪造结果。"
        ),
    }
    if is_platform_system_data_message(user_message):
        nudges["platform"] = (
            "【系统】必须先调用工具获取真实数据（如 search_documents_by_name / list_todos / send_notification 等）；"
            "禁止编造数据或仅用文字描述来假装已完成操作。"
        )
    if execution_plan.uploaded_skill and plan_has_script:
        nudges["script"] = (
            f"【系统】必须调用 run_skill_script(skill_name="
            f"\"{execution_plan.uploaded_skill}\", args=...) 获取真实数据；"
            "禁止在正文作答或让用户自行执行命令。"
        )
    if execution_plan.uploaded_skill and plan_has_script is False:
        nudges["instruction_only_skill"] = (
            f"【系统】用户明确指定使用技能 `{execution_plan.uploaded_skill}`。"
            f"请严格按照该技能 SKILL.md 中的角色设定和回答方式来回复用户，"
            "禁止使用你默认的助手身份或你自身的知识来回答。"
        )
    return nudges


# ─── HITL Checkpoint 辅助函数 ─────────────────────────────

_HITL_POLL_TIMEOUT_SEC = 30  # 活跃轮询超时（秒），超时后进入 suspended 状态
_HITL_POLL_INTERVAL = 0.5  # 轮询间隔


async def _hitl_poll(
    get_response: Callable[[], str | None],
    *,
    timeout: int = _HITL_POLL_TIMEOUT_SEC,
) -> str | None:
    """通用 HITL 轮询：持续检查 ``get_response()``，超时返回 None。"""
    import time

    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        response = get_response()
        if response is not None:
            return response
        await asyncio.sleep(_HITL_POLL_INTERVAL)


def _build_checkpoint_pending_tool(
    tool_name: str,
    tool_id: str,
    raw_args: str,
    step_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_id": tool_id,
        "raw_args": raw_args,
        "step_id": step_id,
        "meta": meta,
    }


# ─── 异步生成器：各退出路径（以 yield complete 结束） ──────────────


async def _emit_direct_reply_complete(
    loop_id: str,
    deliverable_reply: str,
    working: list[dict[str, Any]],
    loop_state: LoopState,
) -> AsyncIterator[dict[str, Any]]:
    """直接可交付回答：仅 yield complete。"""
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "回答完成",
            "detail": "已按技能说明生成内容",
            "tool": "agent.direct",
            "step_id": loop_id,
            "status": "done",
        },
    }
    yield {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(deliverable_reply, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }


async def _emit_task_handoff_complete(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    loop_id: str,
    loop_state: LoopState,
    working: list[dict[str, Any]],
    *,
    user_message: str,
    conversation_id: str | None,
    task_id: str | None,
    agent_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """子任务调度（handoff/assist）完成路径。"""
    assist_req = loop_state.get("orchestrator_assist_request")
    if isinstance(assist_req, dict) and assist_req.get("reason"):
        handoff = build_specialist_assist_handoff(
            loop_state,
            agent_id=(agent_id or "").strip(),
            session_id=(conversation_id or "").strip() or f"session-{loop_id}",
            task_id=(task_id or "").strip() or f"task-{loop_id}",
            assist=assist_req,
            citations=list(loop_state.get("citations") or []),
            kg_context=loop_state.get("kg_context"),
        )
    else:
        sess.release_before_io()
        handoff = await finalize_specialist_handoff(
            loop_state,
            user_message,
            agent_id=(agent_id or "").strip(),
            session_id=(conversation_id or "").strip() or f"session-{loop_id}",
            task_id=(task_id or "").strip() or f"task-{loop_id}",
            citations=list(loop_state.get("citations") or []),
            kg_context=loop_state.get("kg_context"),
        )
        sess.release_before_io()
        db, user = sess.open()
        loop_state["task_deliverable"] = (
            handoff.text if handoff.ok else loop_state.get("task_deliverable")
        )
    final_reply = handoff.text if handoff.ok else None
    is_assist = isinstance(assist_req, dict) and bool(assist_req.get("reason"))
    if final_reply:
        working.append({"role": "assistant", "content": final_reply})
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": (
                "已请求调度协助"
                if is_assist
                else ("子任务完成" if handoff.ok else "子任务未完成")
            ),
            "detail": (assist_req or {}).get("reason", "")[:120] if is_assist else "",
            "tool": "agent.orchestrator.assist" if is_assist else "agent.handoff",
            "step_id": loop_id,
            "status": "done" if handoff.ok else "failed",
        },
    }
    complete_payload: dict[str, Any] = {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(final_reply, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }
    yield attach_handoff_to_complete(complete_payload, handoff.message)


async def _emit_synthesized_complete(
    sess: AgentLoopSession,
    uid: uuid.UUID,
    loop_id: str,
    user_message: str,
    working: list[dict[str, Any]],
    loop_state: LoopState,
    *,
    chat_history: list[AiChatMessage] | None,
) -> AsyncIterator[dict[str, Any]]:
    """六相循环 阶段 2→6：综合工具结果生成最终回答。"""
    synth_id = f"agent-synth-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "根据工具执行结果汇总回答",
            "detail": "",
            "tool": "agent.synthesize",
            "step_id": synth_id,
        },
    }
    from app.services.agent_memory_service import build_memory_prompt_context

    sess.release_before_io()
    _synth_t0 = time.monotonic()
    synth_reply_parts: list[str] = []
    synth_failed = False
    async for ev in iter_synthesize_tool_loop_user_reply_events(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=build_memory_prompt_context(uid),
        chat_history=chat_history,
        step_id=synth_id,
    ):
        if ev.get("type") == "workflow":
            yield {"type": "workflow", "data": ev["data"]}
        elif ev.get("type") == "delta" and ev.get("text"):
            synth_reply_parts.append(str(ev["text"]))
            yield {"type": "delta", "text": ev["text"]}
        elif ev.get("type") == "complete_text":
            text = str(ev.get("text") or "").strip()
            if text:
                for chunk in _emit_report_reply_deltas(text):
                    synth_reply_parts.append(str(chunk["text"]))
                    yield chunk
        elif ev.get("type") == "error":
            synth_failed = True
            yield {"type": "error", "message": ev.get("message", "回答合成失败")}
    if synth_failed:
        _logger.warning("synthesis LLM failed after %.1fs", time.monotonic() - _synth_t0)
        # 合成失败时用 fallback 回复兜底
        from app.services.agent_reply_synth import fallback_tool_loop_reply

        fallback = fallback_tool_loop_reply(user_message, loop_state)
        if fallback:
            yield {"type": "delta", "text": fallback}
            synth_reply_parts.append(fallback)
    _synth_elapsed = time.monotonic() - _synth_t0
    _logger.info("synthesis LLM done in %.1fs", _synth_elapsed)
    final_reply = "".join(synth_reply_parts).strip() or None
    if final_reply:
        working.append({"role": "assistant", "content": final_reply})
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "执行完成",
            "detail": "已根据工具结果生成结论",
            "tool": "agent.execute",
            "step_id": loop_id,
            "status": "done",
        },
    }
    yield {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(final_reply or None, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }


# ─── 入口 ─────────────────────────────────────────────


async def iter_agent_tool_loop(
    user: User | uuid.UUID,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None = None,
    max_rounds: int | None = None,
    user_message: str = "",
    attachment_session_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
    agent_id: str | None = None,
    allowed_tool_names: set[str] | None = None,
    allowed_skill_names: set[str] | None = None,
    scoped_doc_ids: list[str] | None = None,
    local_kb_disabled: bool = False,
    task_mode: bool = False,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow 事件；结束时 yield type=complete。内部按轮次管理 DB 会话。"""
    from app.core.agent_loop_session import coerce_user_id

    user_id = coerce_user_id(user)
    sess = AgentLoopSession(user_id)
    try:
        db, user = sess.open()
        async for event in _iter_agent_tool_loop_body(
            sess,
            db,
            user,
            messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            agent_id=agent_id,
            allowed_tool_names=allowed_tool_names,
            allowed_skill_names=allowed_skill_names,
            scoped_doc_ids=scoped_doc_ids,
            local_kb_disabled=local_kb_disabled,
            task_mode=task_mode,
            task_id=task_id,
        ):
            yield event
    finally:
        sess.close()


async def _iter_agent_tool_loop_body(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    agent_id: str | None,
    allowed_tool_names: set[str] | None,
    allowed_skill_names: set[str] | None,
    scoped_doc_ids: list[str] | None,
    local_kb_disabled: bool,
    task_mode: bool,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    uid = user.id
    working: list[dict[str, Any]] = [dict(m) for m in messages]
    loop_id = f"agent-tools-{uuid.uuid4().hex[:8]}"
    if tools is not None:
        all_tool_specs = tools
    elif agent_id and agent_id != "orchestrator":
        tool_names = resolve_effective_runtime_tool_names(db, agent_id)
        all_tool_specs = build_agent_runtime_tool_specs(
            db,
            user,
            agent_id=agent_id,
            allowed_skill_names=list(allowed_skill_names) if allowed_skill_names else None,
            runtime_tool_names=tool_names,
        )
    elif allowed_tool_names is not None:
        all_tool_specs = build_agent_tool_specs(
            db, user, allowed_names=allowed_tool_names, agent_id=agent_id
        )
    else:
        all_tool_specs = build_agent_tool_specs(db, user, agent_id=agent_id)
    # Agent 有知识库挂载且未显式传入 scoped_doc_ids 时自动注入
    if scoped_doc_ids is None and agent_id:
        try:
            from app.services.agent_knowledge_mount_service import (
                list_mounts,
                resolve_mounts_to_doc_ids,
            )
            mounts = list_mounts(db, agent_id)
            if mounts:
                resolved = resolve_mounts_to_doc_ids(db, user, mounts)
                if resolved:
                    scoped_doc_ids = resolved
        except Exception:
            pass  # 静默失败，不阻塞工具循环
    rounds = max_rounds if max_rounds is not None else _default_max_rounds()
    loop_state: LoopState = {
        "citations": [],
        "kg_context": None,
        "allowed_skill_names": allowed_skill_names,
        "_all_tool_specs": all_tool_specs,
        "scoped_doc_ids": list(scoped_doc_ids) if scoped_doc_ids is not None else None,
        "local_kb_disabled": local_kb_disabled,
        "task_mode": task_mode,
        "agent_id": (agent_id or "").strip() or None,
        "auto_skill_creation": user_message.startswith("【调度自动补能力】"),
        "_tool_failure_counts": {},
    }

    from app.services.kg_service import try_department_members_deterministic_reply

    dept_reply = try_department_members_deterministic_reply(db, user, user_message)
    if dept_reply:
        loop_state["deterministic_reply"] = dept_reply
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "已从知识图谱读取部门成员",
                "detail": "",
                "tool": "kg.org_members",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": dept_reply,
            "citations": [],
            "kg_context": loop_state.get("kg_context"),
        }
        return

    kg_plan_text = ""
    from app.services.agent_intent import is_chitchat_message
    from app.services.agent_skill_router import is_trivial_direct_question

    skip_kg_plan = is_chitchat_message(user_message, chat_history) or is_trivial_direct_question(
        user_message
    )
    if not skip_kg_plan and not _messages_have_prefetched_research(working):
        sess.release_before_io()
        db, user = sess.open()
        kg_plan_text = await resolve_kg_planning_context(
            db, user, user_message, history=chat_history
        )

    plan_step_id = f"agent-plan-{uuid.uuid4().hex[:8]}"
    plan_detail = "分析意图，拆解执行计划…"
    # 如果已有 KG 规划上下文则附带提示
    if kg_plan_text and len(kg_plan_text) > 10:
        plan_detail = f"参考知识图谱上下文进行规划…"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "正在规划执行步骤",
            "detail": plan_detail,
            "tool": "planner",
            "step_id": plan_step_id,
        },
    }
    sess.release_before_io()
    db, user = sess.open()
    _plan_t0 = time.monotonic()
    execution_plan = await resolve_execution_plan(
        db,
        user,
        message=user_message,
        history=chat_history,
        intent_plan=intent_plan,
        available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
        kg_planning_context=kg_plan_text or None,
        agent_id=agent_id,
    )
    _plan_elapsed = time.monotonic() - _plan_t0
    _logger.info(
        "execution_plan resolved in %.1fs agent=%s source=%s intent=%s",
        _plan_elapsed, agent_id, execution_plan.source, execution_plan.intent,
    )
    loop_state["_execution_plan"] = execution_plan
    sess.release_before_io()
    db, user = sess.open()
    plan_summary = execution_plan.summary_for_ui()
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": f"规划方案：{execution_plan.intent or '执行步骤'}",
            "detail": plan_summary,
            "tool": "planner",
            "step_id": plan_step_id,
            "status": "done",
        },
    }

    execution_plan = _narrow_execution_plan_for_specialist(
        execution_plan,
        agent_id=agent_id,
        allowed_skill_names=allowed_skill_names,
        user_message=user_message,
    )

    if (
        allowed_tool_names is not None
        and not allowed_tool_names
        and not execution_plan.direct_answer
        and (
            execution_plan.atomic_tools
            or any(
                token in " ".join(execution_plan.steps).lower()
                for token in ("web_search", "knowledge_retrieve", "kg_query", "invoke_skill")
            )
        )
    ):
        execution_plan = replace(
            execution_plan,
            direct_answer=True,
            reasoning=(execution_plan.reasoning or "") + "（当前智能体无检索工具，改为直接作答）",
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            steps=(),
        )

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill

    plan_has_script = None
    if execution_plan.uploaded_skill:
        from app.services.agent_skill_service import uploaded_skill_has_script

        try:
            plan_has_script = uploaded_skill_has_script(db, execution_plan.uploaded_skill)
        except Exception:
            plan_has_script = None

    from app.services.agent_execution_closure import execution_plan_needs_skill_data

    if execution_plan_needs_skill_data(
        execution_plan, user_message, plan_has_script=plan_has_script
    ):
        loop_state["expects_skill_data"] = True

    from app.services.agent_planner import SKILL_MGMT_INTENT
    from app.services.agent_tool_search import register_unlocked_tools

    unlock_names: list[str] = []
    if execution_plan.uploaded_skill:
        unlock_names.append("run_skill_script")
    if execution_plan.intent == SKILL_MGMT_INTENT:
        unlock_names.append("invoke_skill")
    if unlock_names:
        register_unlocked_tools(loop_state, unlock_names)

    # 执行阶段的标题根据执行计划调整，包含更具体的意图
    exec_title = execution_plan.intent[:60] if (execution_plan.intent or "").strip() else "正在执行任务"
    if execution_plan.uploaded_skill:
        exec_title = f"按「{execution_plan.uploaded_skill}」技能执行"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": exec_title,
            "detail": execution_plan.summary_for_ui(),
            "tool": "agent.execute",
            "step_id": loop_id,
        },
    }

    if execution_plan.direct_answer:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        direct_reply_parts: list[str] = []
        sess.release_before_io()
        async for ev in iter_llm_answer_events(
            messages=working,
            temperature=0.5,
            think_title="生成回答",
            think_detail=execution_plan.intent or "直接作答",
            step_id=loop_id,
        ):
            if ev.get("type") == "workflow":
                yield {"type": "workflow", "data": ev["data"]}
            elif ev.get("type") == "delta" and ev.get("text"):
                direct_reply_parts.append(ev["text"])
                yield {"type": "delta", "text": ev["text"]}
        final_reply = "".join(direct_reply_parts).strip() or None
        if final_reply:
            working.append({"role": "assistant", "content": final_reply})
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "执行完成",
                "detail": execution_plan.intent or "已生成回复",
                "tool": "agent.execute",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": final_reply,
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        return

    plan_instruction = build_plan_context_instruction(
        execution_plan,
        uploaded_skill_has_script=plan_has_script,
    )
    if plan_instruction:
        working = [dict(m) for m in working]
        working.append({"role": "system", "content": plan_instruction})
    working = maybe_inject_skill_dev_playbook(
        loop_state,
        working,
        agent_id=agent_id,
        skill_mgmt=execution_plan.intent == SKILL_MGMT_INTENT,
    )
    initial_skill = (
        str(execution_plan.uploaded_skill or "").strip()
        or str(loop_state.get("planned_uploaded_skill") or "").strip()
    )
    allowed_skills = loop_state.get("allowed_skill_names")
    # 规则生成的 plan 已通过 explicit skill 匹配，trust it
    is_rule_plan = execution_plan.source == "rule" and bool(execution_plan.uploaded_skill)
    if (
        initial_skill
        and allowed_skills is not None
        and initial_skill not in allowed_skills
        and not is_rule_plan
    ):
        initial_skill = ""
    if initial_skill:
        working = maybe_inject_skill_md(db, user, loop_state, working, initial_skill)

    from app.services.agent_execution_closure import (
        apply_execution_plan_unlocks,
        auto_execute_uploaded_skill,
        build_skill_management_continue_nudge,
        execution_goal_satisfied,
        execution_plan_needs_skill_data,
        max_adaptive_execution_passes,
        resolve_adaptive_replan,
        resolve_target_uploaded_skill,
        tool_rounds_for_adaptive_pass,
    )
    from app.services.agent_planner import _skill_name_sets

    all_skill_names = _skill_name_sets(db, user)
    max_adaptive = max_adaptive_execution_passes()
    deliverable_reply: str | None = None
    instruction_only_skill = plan_has_script is False and bool(
        execution_plan.uploaded_skill or loop_state.get("planned_uploaded_skill")
    )

    for adaptive_pass in range(max_adaptive):
        if adaptive_pass > 0:
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break
            prior_plan = execution_plan
            sess.release_before_io()
            _replan_t0 = time.monotonic()
            execution_plan = await resolve_adaptive_replan(
                db,
                user,
                message=user_message,
                history=chat_history,
                intent_plan=intent_plan,
                available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
                kg_planning_context=kg_plan_text or None,
                prior_plan=prior_plan,
                loop_state=loop_state,
                uploaded_names=all_skill_names,
            )
            _replan_elapsed = time.monotonic() - _replan_t0
            _logger.info(
                "adaptive replan in %.1fs pass=%d agent=%s", _replan_elapsed, adaptive_pass, agent_id,
            )
            loop_state["_execution_plan"] = execution_plan
            execution_plan = _narrow_execution_plan_for_specialist(
                execution_plan,
                agent_id=agent_id,
                allowed_skill_names=allowed_skill_names,
                user_message=user_message,
            )
            sess.release_before_io()
            db, user = sess.open()
            if execution_plan.uploaded_skill:
                from app.services.agent_skill_service import uploaded_skill_has_script

                try:
                    plan_has_script = uploaded_skill_has_script(
                        db, execution_plan.uploaded_skill
                    )
                except Exception:
                    plan_has_script = None
            apply_execution_plan_unlocks(execution_plan, loop_state)
            if execution_plan_needs_skill_data(
                execution_plan, user_message, plan_has_script=plan_has_script
            ):
                loop_state["expects_skill_data"] = True
            replan_instruction = build_plan_context_instruction(
                execution_plan,
                uploaded_skill_has_script=plan_has_script,
            )
            if replan_instruction:
                working = [dict(m) for m in working]
                working.append({"role": "system", "content": replan_instruction})
            skill_for_md = str(execution_plan.uploaded_skill or "").strip()
            if skill_for_md:
                working = maybe_inject_skill_md(
                    db, user, loop_state, working, skill_for_md
                )
            instruction_only_skill = plan_has_script is False and bool(skill_for_md)
            loop_state["content_only_nudges"] = 0

        nudge_cache = _build_nudge_cache(user_message, execution_plan, plan_has_script)
        rounds_this_pass = tool_rounds_for_adaptive_pass(rounds, adaptive_pass)
        for _ in range(max(1, rounds_this_pass)):
            pending_skill = str(loop_state.get("pending_skill_md_inject") or "").strip()
            allowed_skills = loop_state.get("allowed_skill_names")
            if pending_skill and allowed_skills is not None and pending_skill not in allowed_skills:
                loop_state.pop("pending_skill_md_inject", None)
                pending_skill = ""
            if pending_skill:
                working = maybe_inject_skill_md(db, user, loop_state, working, pending_skill)
                loop_state.pop("pending_skill_md_inject", None)

            planned_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
            if allowed_tool_names is None:
                from app.services.agent_tool_search import select_visible_tool_specs

                unlocked = loop_state.get("unlocked_tools") or set()
                agent_id = str(loop_state.get("agent_id") or "").strip() or None
                tool_specs = select_visible_tool_specs(
                    planned_specs, unlocked, agent_id=agent_id
                )
            else:
                tool_specs = planned_specs
            llm_messages = trim_agent_loop_messages(
                inject_retrieval_context_message(working, loop_state),
                keep_full_tool_results=(
                    2 if is_skill_management_message(user_message) else 1
                ),
            )
            sess.release_before_io()
            choice = None
            _llm_t0 = time.monotonic()
            async for ev in chat_completion_stream_choice(
                messages=llm_messages,
                tools=tool_specs or None,
                temperature=0.3,
            ):
                if ev["type"] == "delta":
                    yield {
                        "type": "workflow",
                        "data": {"phase": "thinking_delta", "delta": ev["text"]},
                    }
                elif ev["type"] == "choice":
                    choice = ev
            _llm_elapsed = time.monotonic() - _llm_t0
            db, user = sess.open()
            if not choice:
                _logger.info("LLM call empty choice in %.1fs agent=%s", _llm_elapsed, agent_id)
                break
            message = normalize_llm_assistant_message(choice.get("message") or {})
            tool_calls = message.get("tool_calls") or []
            content = strip_dsml_markup(str(message.get("content") or "")).strip()

            if tool_calls:
                working.append(message)
                for tc in tool_calls:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    tool_name = str(fn.get("name") or "")
                    tool_id = str(tc.get("id") or uuid.uuid4())
                    raw_args = fn.get("arguments") or "{}"
                    step_id = f"agent-tool-{uuid.uuid4().hex[:8]}"
                    try:
                        meta = tool_workflow_meta(tool_name, raw_args)
                    except Exception:
                        meta = {
                            "title": tool_name, "result_title": tool_name,
                            "failure_title": f"{tool_name}（失败）",
                            "detail": "", "tool": tool_name,
                        }

                    # ── Human-in-the-Loop: 用户确认检查 ──
                    if is_confirmation_required(tool_name) and not loop_state.get("_hitl_confirmed"):
                        confirmation_id = generate_confirmation_id()
                        raw_params = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip().startswith("{") else (raw_args or {})
                        checkpoint_id = generate_checkpoint_id()

                        # 保存完整 checkpoint 到 Redis（24h TTL）
                        ckpt_saved = save_checkpoint(
                            checkpoint_id,
                            user_id=str(user.id),
                            phase="awaiting_confirmation",
                            loop_state=loop_state,
                            working=working,
                            pending_data={
                                "confirmation_id": confirmation_id,
                                "tool_name": tool_name,
                                "params_json": json.dumps(raw_params, ensure_ascii=False) if raw_params else "{}",
                                "title": meta.get("title") or tool_name,
                            },
                            tool_call=_build_checkpoint_pending_tool(tool_name, tool_id, raw_args, step_id, meta),
                        )
                        stored = set_pending_confirmation(confirmation_id, {
                            "user_id": str(user.id),
                            "tool_name": tool_name,
                            "params_json": json.dumps(raw_params, ensure_ascii=False) if raw_params else "{}",
                            "checkpoint_id": checkpoint_id,
                        })
                        if stored and ckpt_saved:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "confirmation_required",
                                    "confirmation_id": confirmation_id,
                                    "checkpoint_id": checkpoint_id,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "title": meta.get("title") or tool_name,
                                    "detail": build_confirmation_summary(tool_name, raw_params),
                                    "step_id": step_id,
                                },
                            }
                            sess.release_before_io()
                            accepted_resp = await _hitl_poll(lambda: get_confirm_response(confirmation_id))

                            if accepted_resp is None:
                                # 超时 → 进入 suspended 状态，checkpoint 保留在 Redis
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "workflow_finished",
                                        "status": "suspended",
                                        "checkpoint_id": checkpoint_id,
                                        "title": "等待用户确认",
                                    },
                                }
                                loop_state["_checkpoint_suspended"] = checkpoint_id
                                return  # 退出生成器，SSE 流正常结束

                            clear_pending_confirmation(confirmation_id)
                            clear_checkpoint(checkpoint_id)

                            accepted = accepted_resp == "accepted"
                            if not accepted:
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "tool_result",
                                        "title": f"已取消：{meta.get('title') or tool_name}",
                                        "detail": "用户已拒绝此操作",
                                        "tool": meta.get("tool") or tool_name,
                                        "tool_name": tool_name,
                                        "step_id": step_id,
                                        "status": "rejected",
                                    },
                                }
                                continue
                            loop_state["_hitl_confirmed"] = True

                    # ── Human-in-the-Loop: 方案选择 ──
                    if tool_name == "ask_user_choice":
                        raw_params = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip().startswith("{") else (raw_args or {})
                        question = str(raw_params.get("question") or "")
                        options = raw_params.get("options") or []
                        choice_id = generate_choice_id()
                        checkpoint_id = generate_checkpoint_id()

                        ckpt_saved = save_checkpoint(
                            checkpoint_id,
                            user_id=str(user.id),
                            phase="awaiting_choice",
                            loop_state=loop_state,
                            working=working,
                            pending_data={
                                "choice_id": choice_id,
                                "question": question,
                                "options": json.dumps(options, ensure_ascii=False),
                                "title": meta.get("title") or tool_name,
                            },
                            tool_call=_build_checkpoint_pending_tool(tool_name, tool_id, raw_args, step_id, meta),
                        )
                        stored = set_pending_choice(choice_id, {
                            "user_id": str(user.id),
                            "question": question,
                            "options": json.dumps(options, ensure_ascii=False),
                            "checkpoint_id": checkpoint_id,
                        })
                        if stored and ckpt_saved:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "choice_required",
                                    "choice_id": choice_id,
                                    "checkpoint_id": checkpoint_id,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "title": meta.get("title") or tool_name,
                                    "question": question,
                                    "options": options,
                                    "step_id": step_id,
                                },
                            }
                            sess.release_before_io()
                            chosen_option = await _hitl_poll(lambda: get_choice_response(choice_id))

                            if chosen_option is None:
                                # 超时 → 进入 suspended 状态
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "workflow_finished",
                                        "status": "suspended",
                                        "checkpoint_id": checkpoint_id,
                                        "title": "等待用户选择",
                                    },
                                }
                                loop_state["_checkpoint_suspended"] = checkpoint_id
                                return

                            clear_pending_choice(choice_id)
                            clear_checkpoint(checkpoint_id)

                            result_text = json.dumps({
                                "ok": True,
                                "summary": f"用户选择了：{chosen_option}",
                                "data": {"choice": chosen_option},
                            }, ensure_ascii=False)
                            ok = True
                            summary = f"用户选择了：{chosen_option}"
                        else:
                            result_text = json.dumps({
                                "ok": False,
                                "summary": "方案选择服务不可用",
                            }, ensure_ascii=False)
                            ok = False
                            summary = "方案选择服务不可用"
                        record_executed_tool_call(
                            loop_state,
                            tool_name=tool_name,
                            raw_args=raw_args,
                            result_text=result_text,
                            summary=summary or ("完成" if ok else "失败"),
                            step_id=step_id,
                        )
                        yield {
                            "type": "workflow",
                            "data": {
                                "phase": "tool_result",
                                "title": _workflow_result_title(meta, ok=ok),
                                "detail": summary or ("完成" if ok else "失败"),
                                "tool": meta.get("tool") or tool_name,
                                "tool_name": tool_name,
                                "step_id": step_id,
                                "status": "done" if ok else "failed",
                            },
                        }
                        working.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": compress_tool_result_for_loop(result_text),
                            }
                        )
                        continue

                    cached_result = lookup_cached_tool_result(loop_state, tool_name, raw_args)
                    # 解析参数用于 callDetail 展示
                    try:
                        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        call_detail_str = json.dumps(parsed_args, ensure_ascii=False, default=str)[:300]
                    except Exception:
                        call_detail_str = str(raw_args or "")[:300]

                    if cached_result is not None:
                        result_text = cached_result
                        ok, summary = _parse_tool_summary(result_text)
                        summary = summary or "复用本轮已执行结果"
                        original_detail = meta.get("detail") or ""
                        cached_detail = f"{original_detail}（使用缓存结果）" if original_detail else "复用本轮对话已有结果"
                        yield {
                            "type": "workflow",
                            "data": {
                                "phase": "tool_call",
                                "title": meta["title"],
                                "detail": cached_detail,
                                "callDetail": call_detail_str,
                                "tool": meta.get("tool") or tool_name,
                                "tool_name": tool_name,
                                "step_id": step_id,
                            },
                        }
                    else:
                        yield {
                            "type": "workflow",
                            "data": {
                                "phase": "tool_call",
                                "title": meta["title"],
                                "detail": meta.get("detail") or "",
                                "callDetail": call_detail_str,
                                "tool": meta.get("tool") or tool_name,
                                "tool_name": tool_name,
                                "step_id": step_id,
                            },
                        }
                        # ── 断路器：同一工具连续失败 N 次后在本轮对话中禁用 ──
                        tool_fails: dict[str, int] = loop_state.get("_tool_failure_counts") or {}
                        if tool_fails.get(tool_name, 0) >= 3:
                            result_text = json.dumps({
                                "ok": False,
                                "summary": f"工具 {tool_name} 连续失败 3 次，"
                                           "本次对话中已禁用。请尝试换用其他工具或直接回答。",
                            }, ensure_ascii=False)
                        else:
                            timeout = _tool_timeout()
                            try:
                                result_text = await asyncio.wait_for(
                                    execute_agent_tool(
                                        db,
                                        user,
                                        tool_name=tool_name,
                                        arguments=raw_args,
                                        conversation_id=conversation_id,
                                        attachment_session_id=attachment_session_id,
                                        user_message=user_message,
                                        loop_state=loop_state,
                                    ),
                                    timeout=timeout,
                                )
                            except asyncio.TimeoutError:
                                _logger.warning(
                                    "工具执行超时 tool=%s timeout=%ss",
                                    tool_name, timeout,
                                )
                                result_text = json.dumps(
                                    {"ok": False, "summary": f"工具执行超时（{timeout} 秒）"},
                                    ensure_ascii=False,
                                )
                            except Exception as exc:
                                _logger.exception("工具执行异常 tool=%s", tool_name)
                                result_text = json.dumps(
                                    {"ok": False, "summary": f"工具执行异常：{exc}"},
                                    ensure_ascii=False,
                                )
                            ok, summary = _parse_tool_summary(result_text)
                            # ── 自动重试：临时故障（超时/网络/数据库）立即重试一次 ──
                            if not ok and _is_retryable_error(result_text):
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "tool_call",
                                        "title": f"{meta['title']}（重试）",
                                        "detail": "临时故障，自动重试一次",
                                        "tool": meta.get("tool") or tool_name,
                                        "tool_name": tool_name,
                                        "step_id": f"{step_id}-retry",
                                    },
                                }
                                try:
                                    result_text = await asyncio.wait_for(
                                        execute_agent_tool(
                                            db,
                                            user,
                                            tool_name=tool_name,
                                            arguments=raw_args,
                                            conversation_id=conversation_id,
                                            attachment_session_id=attachment_session_id,
                                            user_message=user_message,
                                            loop_state=loop_state,
                                        ),
                                        timeout=timeout,
                                    )
                                except asyncio.TimeoutError:
                                    result_text = json.dumps(
                                        {"ok": False, "summary": f"工具执行超时（{timeout} 秒）"},
                                        ensure_ascii=False,
                                    )
                                except Exception as exc:
                                    result_text = json.dumps(
                                        {"ok": False, "summary": f"工具执行异常：{exc}"},
                                        ensure_ascii=False,
                                    )
                            # ── 追踪失败计数（仅对本次实际执行计数） ──
                            ok2, _ = _parse_tool_summary(result_text)
                            if not ok2:
                                tool_fails[tool_name] = tool_fails.get(tool_name, 0) + 1
                                loop_state["_tool_failure_counts"] = tool_fails
                            else:
                                # 成功后重置计数，允许工具继续使用
                                tool_fails.pop(tool_name, None)
                        ok, summary = _parse_tool_summary(result_text)
                        record_executed_tool_call(
                            loop_state,
                            tool_name=tool_name,
                            raw_args=raw_args,
                            result_text=result_text,
                            summary=summary or ("完成" if ok else "失败"),
                            step_id=step_id,
                        )
                    from app.services.agent_admin_reply import (
                        capture_admin_list_deterministic_reply,
                    )

                    capture_admin_list_deterministic_reply(
                        db,
                        tool_name=tool_name,
                        result_text=result_text,
                        loop_state=loop_state,
                    )
                    if (
                        ok
                        and tool_name == ATOMIC_TOOL_KG_QUERY
                        and loop_state.get("kg_context")
                    ):
                        from app.services.kg_service import (
                            try_department_members_deterministic_reply,
                        )

                        if not loop_state.get("deterministic_reply"):
                            dept_reply = try_department_members_deterministic_reply(
                                db, user, user_message
                            )
                            if dept_reply:
                                loop_state["deterministic_reply"] = dept_reply
                            else:
                                kg_ctx = loop_state["kg_context"]
                                ctx_text = str(
                                    getattr(kg_ctx, "context_text", None)
                                    or (
                                        kg_ctx.get("context_text")
                                        if isinstance(kg_ctx, dict)
                                        else ""
                                    )
                                    or ""
                                ).strip()
                                if ctx_text:
                                    loop_state["deterministic_reply"] = ctx_text
                    outcome_lines = list(loop_state.get("tool_outcome_lines") or [])
                    if cached_result is None:
                        outcome_lines.append(
                            f"{meta.get('title') or tool_name}：{summary or ('完成' if ok else '失败')}"
                        )
                        loop_state["tool_outcome_lines"] = outcome_lines[-12:]
                    try:
                        result_text_parsed = json.loads(result_text) if isinstance(result_text, str) else {}
                        result_detail_str = str(result_text_parsed.get("summary") or "")[:400]
                    except Exception:
                        result_detail_str = str(result_text or "")[:400]
                    result_data = {
                        "phase": "tool_result",
                        "title": _workflow_result_title(meta, ok=ok),
                        "detail": summary or ("完成" if ok else "失败"),
                        "resultDetail": result_detail_str,
                        "tool": meta.get("tool") or tool_name,
                        "tool_name": tool_name,
                        "step_id": step_id,
                        "status": "done" if ok else "failed",
                    }
                    boost_seconds = meta.get("boost_seconds")
                    if boost_seconds is None and ok and result_text:
                        try:
                            body = json.loads(result_text)
                            if isinstance(body, dict):
                                outer = body.get("data")
                                if isinstance(outer, dict):
                                    inner = outer.get("data") if isinstance(outer.get("data"), dict) else outer
                                    bs = inner.get("boost_seconds")
                                    if bs is not None:
                                        boost_seconds = str(int(bs))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                    if boost_seconds is not None:
                        result_data["boost_seconds"] = str(int(boost_seconds))
                    yield {
                        "type": "workflow",
                        "data": result_data,
                    }
                    working.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": compress_tool_result_for_loop(result_text),
                        }
                    )
                    for att in list(loop_state.get("stream_attachments") or []):
                        _mark_streamed_attachment(loop_state, att)
                        yield {"type": "attachment", "data": att}
                    loop_state["stream_attachments"] = []
                if loop_state.get("orchestrator_assist_request"):
                    break
                if not execution_goal_satisfied(
                    execution_plan,
                    loop_state,
                    user_message,
                    plan_has_script=plan_has_script,
                ):
                    working.append(
                        {
                            "role": "system",
                            "content": build_skill_management_continue_nudge(
                                user_message, loop_state
                            ),
                        }
                    )
                    continue
                break

            if content:
                working.append({"role": "assistant", "content": content})
            if content and assistant_content_is_deliverable(
                content, instruction_only_skill=instruction_only_skill
            ):
                deliverable_reply = content.strip()
                # 立即流式输出内容：让用户看到阶段性文字结果，
                # 后续自适应重规划可能追加更多内容（如文字答案后的图表）
                for ev in _emit_report_reply_deltas(deliverable_reply):
                    yield ev
                delivered = list(loop_state.get("delivered_parts") or [])
                delivered.append(deliverable_reply)
                loop_state["delivered_parts"] = delivered
                break

            # 无 tool_calls 的纯文本输出 — 使用缓存的 nudge 提醒使用工具
            _raw_content = str((choice.get("message") or {}).get("content") or "")
            if not _raw_content:
                break
            has_outcomes = bool(
                loop_state.get("tool_outcome_lines")
                or loop_state.get("last_skill_conclusion")
            )
            nudges_left = 2 - int(loop_state.get("content_only_nudges") or 0)
            if has_outcomes or nudges_left <= 0:
                break
            loop_state["content_only_nudges"] = (loop_state.get("content_only_nudges") or 0) + 1

            if instruction_only_skill:
                nudge = nudge_cache.get("instruction_only_skill") or nudge_cache["instruction"]
            elif "platform" in nudge_cache:
                nudge = nudge_cache["platform"]
            elif "script" in nudge_cache:
                nudge = nudge_cache["script"]
            else:
                nudge = nudge_cache["instruction"]
            working.append({"role": "system", "content": nudge})
            continue

        if deliverable_reply:
            if instruction_only_skill:
                # 指令型技能（如 mermaid-diagram）的正文输出即为完整交付
                break
            # LLM 在本次推理中选择了输出正文而不调用任何工具，
            # 这意味着 LLM 认为答复已完整。无需自适应重规划。
            break

        if execution_goal_satisfied(
            execution_plan,
            loop_state,
            user_message,
            plan_has_script=plan_has_script,
        ):
            break

        skill = resolve_target_uploaded_skill(
            execution_plan=execution_plan,
            loop_state=loop_state,
            user_message=user_message,
            chat_history=chat_history,
            uploaded_names=all_skill_names,
        )
        if skill and plan_has_script is not False:
            closure_step = f"agent-closure-{uuid.uuid4().hex[:8]}"
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": "自动执行技能",
                    "detail": skill,
                    "tool": "agent.closure",
                    "step_id": closure_step,
                },
            }
            sess.release_before_io()
            _ok, _summary = await auto_execute_uploaded_skill(
                db,
                user,
                skill_name=skill,
                user_message=user_message,
                chat_history=chat_history,
                loop_state=loop_state,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
            )
            db, user = sess.open()
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "技能执行完成" if _ok else "技能执行未获有效数据",
                    "detail": _summary[:200] if _summary else "",
                    "tool": "agent.closure",
                    "step_id": closure_step,
                    "status": "done" if _ok else "failed",
                },
            }
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break

    sess.release_before_io()
    db, user = sess.open()
    await _maybe_auto_browser_screenshot(
        db,
        user,
        conversation_id=conversation_id,
        loop_state=loop_state,
        user_message=user_message,
    )
    for att in _pending_screenshot_attachments(loop_state):
        yield {"type": "attachment", "data": att}

    if deliverable_reply or loop_state.get("delivered_parts"):
        parts = list(loop_state.get("delivered_parts") or [])
        if deliverable_reply and (
            not parts or parts[-1] != deliverable_reply
        ):
            parts.append(deliverable_reply)
        combined = "\n\n".join(p.strip() for p in parts if p.strip())
        if combined:
            async for ev in _emit_direct_reply_complete(
                loop_id, combined, working, loop_state,
            ):
                yield ev
            return

    if task_mode:
        async for ev in _emit_task_handoff_complete(
            sess, db, user, loop_id, loop_state, working,
            user_message=user_message, conversation_id=conversation_id,
            task_id=task_id, agent_id=agent_id,
        ):
            yield ev
        return

    # 六相循环 — 阶段 2→6：记忆更新 + 最终回复综合
    async for ev in _emit_synthesized_complete(
        sess, uid, loop_id, user_message, working, loop_state,
        chat_history=chat_history,
    ):
        yield ev
