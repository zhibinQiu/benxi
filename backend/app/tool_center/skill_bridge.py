"""Skill ↔ ToolCenter 桥接 — 标准请求、自动重试、业务化结果。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.skills.types import SkillInvocationContext, SkillInvocationResult
from app.tool_center.context import ToolRuntimeContext
from app.tool_center.errors import ToolErrorCode, business_message, is_retryable
from app.tool_center.executor import execute_tool_call, new_call_id
from app.tool_center.schemas import SkillMeta, ToolCallRequest, ToolResponse

_logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS_SEC = (0.35, 0.9, 1.8)


def _runtime_ctx(
    ctx: SkillInvocationContext,
    *,
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        db=ctx.db,
        user=ctx.user,
        conversation_id=ctx.conversation_id,
        attachment_session_id=ctx.attachment_session_id,
        user_message=user_message,
        loop_state=loop_state,
    )


def tool_response_to_skill_result(
    response: ToolResponse,
    *,
    success_summary: str | None = None,
) -> SkillInvocationResult:
    if response.success:
        summary = success_summary or response.msg or business_message(response.code)
        return SkillInvocationResult(True, summary, data=response.data)

    public_msg = business_message(response.code, response.msg)
    _logger.debug(
        "tool_call failed code=%s detail=%s",
        response.code,
        (response.detail or "")[:200],
    )
    return SkillInvocationResult(
        False,
        public_msg,
        data={"retryable": response.retryable},
        error=public_msg,
    )


async def invoke_atomic_tool(
    ctx: SkillInvocationContext,
    *,
    tool_id: str,
    params: dict[str, Any],
    skill_id: str,
    belong_agent: str = "",
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
    trace_id: str | None = None,
    call_id: str | None = None,
    success_summary: str | None = None,
) -> SkillInvocationResult:
    """Skill 内部调用全局 Tool；可重试错误自动退避重试。"""
    request = ToolCallRequest(
        call_id=call_id or new_call_id(),
        tool_id=tool_id.strip(),
        params=dict(params or {}),
        trace_id=(trace_id or ctx.trace_id or ctx.conversation_id or "")[:128],
        skill_meta=SkillMeta(
            skill_id=skill_id.strip(),
            belong_agent=(belong_agent or ctx.belong_agent or "").strip(),
        ),
    )
    runtime = _runtime_ctx(ctx, user_message=user_message, loop_state=loop_state)
    response: ToolResponse | None = None

    for attempt in range(_MAX_RETRIES):
        response = await execute_tool_call(request, runtime)
        if response.success:
            return tool_response_to_skill_result(response, success_summary=success_summary)
        if not is_retryable(response.code) or attempt >= _MAX_RETRIES - 1:
            break
        delay = _RETRY_DELAYS_SEC[min(attempt, len(_RETRY_DELAYS_SEC) - 1)]
        _logger.info(
            "tool %s retry %s/%s code=%s delay=%.2fs",
            tool_id,
            attempt + 2,
            _MAX_RETRIES,
            response.code,
            delay,
        )
        await asyncio.sleep(delay)

    assert response is not None
    return tool_response_to_skill_result(response, success_summary=success_summary)
