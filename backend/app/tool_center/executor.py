"""ToolCenter 执行器 — schema、限流、底层适配；Tool 不感知 Skill/Agent/LLM。"""

from __future__ import annotations

import logging
import time
import uuid

from pydantic import ValidationError

from app.tool_center.context import ToolRuntimeContext
from app.tool_center.errors import ToolErrorCode, is_retryable
from app.tool_center.rate_limit import check_rate_limit
from app.tool_center.registry import get_tool_center
from app.tool_center.schemas import ToolCallRequest, ToolResponse
from app.tool_center.adapters import run_global_atomic_tool

_logger = logging.getLogger(__name__)


def _fail(
    code: ToolErrorCode,
    msg: str,
    *,
    detail: str | None = None,
    cost_ms: int = 0,
) -> ToolResponse:
    return ToolResponse(
        success=False,
        code=int(code),
        msg=msg,
        detail=detail,
        meta={
            "cost_ms": cost_ms,
            "retryable": is_retryable(int(code)),
        },
    )


def _validate_params(tool_id: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, ToolResponse | None]:
    center = get_tool_center()
    model_cls = center.input_model(tool_id)
    if model_cls is None:
        return None, _fail(ToolErrorCode.NOT_FOUND, f"unknown tool_id: {tool_id}")
    try:
        model = model_cls.model_validate(params)
        return model.model_dump(exclude_none=True), None
    except ValidationError as exc:
        missing = any(e.get("type") == "missing" for e in exc.errors())
        code = ToolErrorCode.PARAM_MISSING if missing else ToolErrorCode.SCHEMA_MISMATCH
        parts = []
        for err in exc.errors()[:4]:
            loc = ".".join(str(x) for x in err.get("loc") or ())
            parts.append(f"{loc}: {err.get('msg')}")
        detail = "; ".join(parts)
        _logger.warning("tool %s param validation failed: %s | params=%s", tool_id, detail, params)
        return None, _fail(
            code,
            "parameter validation failed",
            detail=detail,
        )


async def _execute_legacy(
    ctx: ToolRuntimeContext,
    tool_id: str,
    params: dict[str, Any],
) -> tuple[bool, str, dict[str, Any] | None]:
    return await run_global_atomic_tool(ctx, tool_id, params)


async def execute_tool_call(
    request: ToolCallRequest,
    ctx: ToolRuntimeContext,
) -> ToolResponse:
    """Skill 发起 Tool 请求的唯一入口。"""
    started = time.monotonic()
    tool_id = request.tool_id.strip()
    center = get_tool_center()
    descriptor = center.get(tool_id)
    if descriptor is None:
        return _fail(
            ToolErrorCode.NOT_FOUND,
            f"tool not registered: {tool_id}",
            cost_ms=0,
        )

    if not check_rate_limit(tool_id, qps=descriptor.rate_limit.qps):
        return _fail(
            ToolErrorCode.RATE_LIMITED,
            "rate limit exceeded",
            detail=f"qps={descriptor.rate_limit.qps}",
            cost_ms=int((time.monotonic() - started) * 1000),
        )

    validated, param_err = _validate_params(tool_id, dict(request.params or {}))
    if param_err is not None:
        param_err.meta["cost_ms"] = int((time.monotonic() - started) * 1000)
        return param_err

    try:
        ok, summary, data = await run_global_atomic_tool(ctx, tool_id, validated or {})
    except Exception as exc:
        _logger.warning("tool_center execute %s failed: %s", tool_id, exc)
        return _fail(
            ToolErrorCode.SYSTEM_ERROR,
            "internal execution error",
            detail=str(exc)[:500],
            cost_ms=int((time.monotonic() - started) * 1000),
        )

    cost_ms = int((time.monotonic() - started) * 1000)
    if not ok:
        return ToolResponse(
            success=False,
            code=int(ToolErrorCode.EXEC_FAILED),
            msg=summary or "execute failed",
            detail=summary[:500] if summary else None,
            meta={
                "cost_ms": cost_ms,
                "retryable": False,
                "tool_version": descriptor.tool_version,
            },
        )

    return ToolResponse(
        success=True,
        code=int(ToolErrorCode.OK),
        msg=summary or "execute success",
        data=data or {},
        meta={
            "cost_ms": cost_ms,
            "tool_version": descriptor.tool_version,
            "call_id": request.call_id,
        },
    )


def new_call_id(prefix: str = "skill_subtask") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
