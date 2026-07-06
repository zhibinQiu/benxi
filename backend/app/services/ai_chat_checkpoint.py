"""Checkpoint 恢复执行 — 从中断点恢复 Agent 工具循环。

从 Redis checkpoint 恢复 loop_state 和 working messages。
用户确认/选择后，注入相应的 tool result 并继续执行。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.agent_checkpoint import clear_checkpoint, load_checkpoint
from app.core.agent_loop_session import AgentLoopSession, coerce_user_id
from app.core.agent_tool_context import compress_tool_result_for_loop, record_executed_tool_call
from app.core.human_in_the_loop import (
    clear_pending_choice,
    clear_pending_confirmation,
    get_choice_response,
    get_confirm_response,
)
from app.core.workflow_events import (
    sse_attachment,
    sse_delta,
    sse_done,
    sse_error,
    sse_workflow,
    workflow_event_json,
)
from app.services.agent_tools import execute_agent_tool, tool_workflow_meta

_logger = __import__("logging").getLogger(__name__)


async def iter_resumed_agent_stream(
    *,
    user_id: uuid.UUID | str,
    checkpoint_id: str,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    """从 checkpoint 恢复 Agent 执行，产出 SSE data 行。"""
    # ── 1. 加载 checkpoint ──
    cp = load_checkpoint(checkpoint_id)
    if not cp:
        yield sse_error("Checkpoint 已过期或不存在，请重新发送消息")
        return

    if str(cp.get("user_id", "")) != str(user_id):
        yield sse_error("无权操作此 checkpoint")
        return

    loop_state: dict[str, Any] = cp.get("loop_state") or {}
    working: list[dict[str, Any]] = cp.get("working") or []
    pending_data: dict[str, Any] = cp.get("pending_data") or {}
    phase: str = cp.get("phase", "")

    # ── 2. 获取用户响应 ──
    response: str | None = None
    accepted: bool | None = None
    if phase == "awaiting_confirmation":
        cid = pending_data.get("confirmation_id", "")
        response = get_confirm_response(cid) if cid else None
        if response == "accepted":
            accepted = True
        elif response == "rejected":
            accepted = False
    elif phase == "awaiting_choice":
        cid = pending_data.get("choice_id", "")
        response = get_choice_response(cid) if cid else None

    if response is None:
        yield sse_error("用户尚未确认，无法恢复执行")
        return

    # ── 3. 发射 workflow_resumed 事件 ──
    yield workflow_event_json(
        "workflow_resumed",
        title="已收到确认，继续执行",
        detail=pending_data.get("title") or "恢复执行",
        checkpoint_id=checkpoint_id,
    )

    # ── 4. 标记已确认，避免二次 HITL ──
    loop_state["_hitl_confirmed"] = True
    loop_state.pop("_checkpoint_suspended", None)

    uid = coerce_user_id(user_id)
    sess = AgentLoopSession(uid)

    try:
        db, user = sess.open()

        # ── 5. 获取待执行的 tool_call 信息 ──
        tool_call = cp.get("tool_call")
        if tool_call:
            tool_name = tool_call.get("tool_name", "")
            tool_id = tool_call.get("tool_id", "")
            raw_args = tool_call.get("raw_args", "{}")
            step_id = tool_call.get("step_id", f"agent-tool-resume-{uuid.uuid4().hex[:8]}")
            meta = tool_workflow_meta(tool_name, raw_args)

            yield sse_workflow({
                "phase": "tool_call",
                "title": meta.get("title") or tool_name,
                "detail": meta.get("detail") or "（从 checkpoint 恢复）",
                "tool": meta.get("tool") or tool_name,
                "tool_name": tool_name,
                "step_id": step_id,
            })

            if accepted is False or accepted is None:
                result_text = json.dumps({
                    "ok": False,
                    "summary": "用户已拒绝此操作",
                }, ensure_ascii=False)
                ok = False
                summary = "用户已拒绝此操作"
            else:
                sess.release_before_io()
                result_text = await execute_agent_tool(
                    db, user,
                    tool_name=tool_name,
                    arguments=raw_args,
                    conversation_id=conversation_id,
                    loop_state=loop_state,
                )
                db, user = sess.open()
                ok, summary = _parse_tool_summary(result_text)

            record_executed_tool_call(
                loop_state, tool_name=tool_name, raw_args=raw_args,
                result_text=result_text,
                summary=summary or ("完成" if ok else "失败"),
                step_id=step_id,
            )

            yield sse_workflow({
                "phase": "tool_result",
                "title": f"{'完成' if ok else '失败'}：{meta.get('title') or tool_name}",
                "detail": summary or ("完成" if ok else "失败"),
                "tool": meta.get("tool") or tool_name,
                "tool_name": tool_name,
                "step_id": step_id,
                "status": "done" if ok else "failed",
            })

            working.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": compress_tool_result_for_loop(result_text),
            })

        # ── 6. 重新进入 tool loop ──
        from app.services.agent_tool_loop import _iter_agent_tool_loop_body

        async for event in _iter_agent_tool_loop_body(
            sess, db, user, working,
            conversation_id=conversation_id,
            max_rounds=None,
            user_message=str(loop_state.get("task_deliverable") or ""),
            attachment_session_id=loop_state.get("_attachment_session_id"),
            tools=loop_state.get("_all_tool_specs"),
            intent_plan=loop_state.get("_intent_plan"),
            chat_history=None,
            agent_id=str(loop_state.get("agent_id") or "").strip() or None,
            allowed_tool_names=loop_state.get("_allowed_tool_names"),
            allowed_skill_names=loop_state.get("allowed_skill_names"),
            scoped_doc_ids=loop_state.get("scoped_doc_ids"),
            local_kb_disabled=bool(loop_state.get("local_kb_disabled")),
            task_mode=bool(loop_state.get("task_mode")),
            task_id=loop_state.get("_task_id"),
        ):
            if event.get("type") == "workflow":
                yield sse_workflow(event["data"])
            elif event.get("type") == "delta":
                yield sse_delta(event.get("text", ""))
            elif event.get("type") == "attachment":
                yield sse_attachment(event["data"])
            elif event.get("type") == "complete":
                yield sse_done(
                    reply=event.get("reply"),
                    citations=event.get("citations"),
                )
                return

    except Exception as exc:
        _logger.error("Checkpoint 恢复失败: %s", exc, exc_info=True)
        yield sse_error(f"恢复执行失败：{exc}")
    finally:
        sess.close()
        clear_checkpoint(checkpoint_id)
        clear_pending_confirmation(pending_data.get("confirmation_id", ""))
        clear_pending_choice(pending_data.get("choice_id", ""))


def _parse_tool_summary(result_text: str) -> tuple[bool, str]:
    try:
        body = json.loads(result_text)
        if isinstance(body, dict):
            return bool(body.get("ok")), str(body.get("summary") or "")
    except json.JSONDecodeError:
        pass
    return False, result_text[:200]
