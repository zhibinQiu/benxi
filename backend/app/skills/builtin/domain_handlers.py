"""领域 Skill handler — 经 ToolCenter 调用全局原子 Tool，对外仅返回业务结果。"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_tool_args import (
    ADMIN_DEPT_TOOL_NAMES,
    ADMIN_USER_TOOL_NAMES,
    BROWSER_TOOL_NAMES,
    DOCUMENT_TOOL_NAMES,
    PLATFORM_TOOL_NAMES,
)
from app.core.tool_skill_taxonomy import (
    NOTIFICATION_TOOL_NAMES,
    SKILL_BROWSER_AUTOMATION,
    SKILL_DEPT_ADMIN,
    SKILL_DOCUMENT_LIBRARY,
    SKILL_MGMT_TOOL_NAMES,
    SKILL_NOTIFICATION,
    SKILL_PLATFORM_OPS,
    SKILL_SKILL_DEV,
    SKILL_USER_ADMIN,
    normalize_skill_mgmt_operation,
    skill_mgmt_operations_hint,
)
from app.skills.types import SkillHandler, SkillInvocationContext, SkillInvocationResult
from app.tool_center.skill_bridge import invoke_atomic_tool


def make_domain_call_handler(
    allowed_operations: frozenset[str],
    *,
    skill_id: str,
    operation_param: str = "operation",
) -> SkillHandler:
    async def handler(
        ctx: SkillInvocationContext, params: dict[str, Any]
    ) -> SkillInvocationResult:
        operation = str(params.get(operation_param) or "").strip()
        if not operation:
            return SkillInvocationResult(False, f"缺少 {operation_param}", error="missing_operation")
        if operation not in allowed_operations:
            return SkillInvocationResult(
                False,
                "不支持的操作；请确认请求范围后重试",
                error="invalid_operation",
            )
        tool_params = params.get("params")
        if not isinstance(tool_params, dict):
            tool_params = {k: v for k, v in params.items() if k != operation_param}
        return await invoke_atomic_tool(
            ctx,
            tool_id=operation,
            params=tool_params,
            skill_id=skill_id,
            belong_agent=ctx.belong_agent or "",
            user_message=ctx.user_message or "",
            loop_state=ctx.loop_state,
        )

    return handler


async def handle_skill_development_call(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """技能管理操作 — 经 execute_agent_tool 执行（非 ToolCenter 全局原子 Tool）。"""
    operation = normalize_skill_mgmt_operation(str(params.get("operation") or ""))
    if not operation:
        return SkillInvocationResult(False, "缺少 operation", error="missing_operation")
    allowed = frozenset(SKILL_MGMT_TOOL_NAMES)
    if operation not in allowed:
        return SkillInvocationResult(
            False,
            f"不支持的操作 `{operation}`；可用 operation：{skill_mgmt_operations_hint()}",
            error="invalid_operation",
        )
    tool_params = params.get("params")
    if not isinstance(tool_params, dict):
        tool_params = {k: v for k, v in params.items() if k not in ("operation", "params")}

    from app.services.agent_tools import execute_agent_tool

    # 传递 skill_name，确保 invoke_skill 递归调用时上下文完整
    skill_dev_skill_name = ctx.skill_name or "skill-development"
    raw = await execute_agent_tool(
        ctx.db,
        ctx.user,
        tool_name=operation,
        arguments=tool_params,
        conversation_id=ctx.conversation_id,
        attachment_session_id=ctx.attachment_session_id,
        user_message=ctx.user_message or "",
        loop_state=ctx.loop_state,
        skill_name=skill_dev_skill_name,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return SkillInvocationResult(False, raw[:500], error="bad_response")
    ok = bool(payload.get("ok"))
    summary = str(payload.get("summary") or "")
    data = payload.get("data")
    return SkillInvocationResult(
        ok,
        summary,
        data=data,
        error=None if ok else summary,
    )


handle_document_library_call = make_domain_call_handler(
    frozenset(DOCUMENT_TOOL_NAMES), skill_id=SKILL_DOCUMENT_LIBRARY
)
_PLATFORM_TOOL_NAMES_EXCL_NOTIFICATION = tuple(
    t for t in PLATFORM_TOOL_NAMES if t not in NOTIFICATION_TOOL_NAMES
)
handle_platform_ops_call = make_domain_call_handler(
    frozenset(_PLATFORM_TOOL_NAMES_EXCL_NOTIFICATION), skill_id=SKILL_PLATFORM_OPS
)
handle_notification_call = make_domain_call_handler(
    frozenset(NOTIFICATION_TOOL_NAMES), skill_id=SKILL_NOTIFICATION
)
handle_browser_automation_call = make_domain_call_handler(
    frozenset(BROWSER_TOOL_NAMES), skill_id=SKILL_BROWSER_AUTOMATION
)
handle_user_admin_call = make_domain_call_handler(
    frozenset(ADMIN_USER_TOOL_NAMES), skill_id=SKILL_USER_ADMIN
)
handle_dept_admin_call = make_domain_call_handler(
    frozenset(ADMIN_DEPT_TOOL_NAMES), skill_id=SKILL_DEPT_ADMIN
)
