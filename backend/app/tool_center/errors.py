"""ToolCenter 全局统一错误码。"""

from __future__ import annotations

from enum import IntEnum


class ToolErrorCode(IntEnum):
    """0 成功；1xxx 参数；2xxx 权限；3xxx 资源限制；4xxx 业务；5xxx 系统。"""

    OK = 0

    PARAM_INVALID = 1001
    PARAM_MISSING = 1002
    SCHEMA_MISMATCH = 1003

    PERMISSION_DENIED = 2002

    RATE_LIMITED = 3001
    TIMEOUT = 3002
    RESOURCE_EXHAUSTED = 3003

    EXEC_FAILED = 4001
    NOT_FOUND = 4002
    CONFLICT = 4003

    SYSTEM_ERROR = 5001
    UNAVAILABLE = 5002


def is_retryable(code: int) -> bool:
    return code in {
        ToolErrorCode.RATE_LIMITED,
        ToolErrorCode.TIMEOUT,
        ToolErrorCode.RESOURCE_EXHAUSTED,
        ToolErrorCode.UNAVAILABLE,
    }


def business_message(code: int, fallback: str = "") -> str:
    """Skill 层对外业务化文案 — 不透传 Tool 技术细节。"""
    mapping = {
        ToolErrorCode.OK: "执行成功",
        ToolErrorCode.PARAM_INVALID: "请求参数无效，请检查后重试",
        ToolErrorCode.PARAM_MISSING: "缺少必要参数",
        ToolErrorCode.SCHEMA_MISMATCH: "参数格式不符合要求",
        ToolErrorCode.PERMISSION_DENIED: "无权限执行该操作",
        ToolErrorCode.RATE_LIMITED: "操作过于频繁，请稍后重试",
        ToolErrorCode.TIMEOUT: "操作超时，可重试",
        ToolErrorCode.RESOURCE_EXHAUSTED: "系统资源繁忙，请稍后重试",
        ToolErrorCode.EXEC_FAILED: "未能完成操作",
        ToolErrorCode.NOT_FOUND: "目标不存在或不可访问",
        ToolErrorCode.CONFLICT: "操作冲突，请确认后重试",
        ToolErrorCode.SYSTEM_ERROR: "系统暂时不可用，请稍后重试",
        ToolErrorCode.UNAVAILABLE: "依赖服务不可用，请稍后重试",
    }
    return mapping.get(ToolErrorCode(code), fallback or "操作未能完成")
