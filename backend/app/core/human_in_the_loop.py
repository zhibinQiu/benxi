"""Human-in-the-Loop: AI 工具执行前的用户确认/选择机制。

职责范围：
  - 工具确认规则（哪些工具需要确认、摘要文案）
  - 通过 ``RedisHitlResponseStore`` 与 Redis 通信（读写确认/选择响应）

整个模块面向 agent_tool_loop.py（HITL 主循环）和 ai_chat_checkpoint.py（恢复）使用
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agentkit_interrupt import HitlRequest, generate_hitl_request_id

logger = logging.getLogger(__name__)

# ── 工具确认规则 ──────────────────────────────────

CONFIRMATION_REQUIRED_TOOLS: set[str] = {
    "delete_document",
    "delete_kb_folder",
    "delete_user",
    "delete_department",
    "delete_uploaded_skill",
    "browser_run_task",
    "run_skill_script",
    "create_skill",
}


def _get_effective_confirm_tools() -> set[str]:
    """返回生效的需要确认的工具集。"""
    from app.config import get_settings

    override = get_settings().hitl_confirm_tools
    if not override:
        return CONFIRMATION_REQUIRED_TOOLS
    tools = {t.strip() for t in override.split(",") if t.strip()}
    return tools if tools else CONFIRMATION_REQUIRED_TOOLS


def is_confirmation_required(tool_name: str) -> bool:
    """判断工具是否需要用户确认。"""
    return tool_name in _get_effective_confirm_tools()


def build_confirmation_summary(tool_name: str, params: dict[str, Any]) -> str:
    """构建人可读的工具调用摘要。"""
    summaries = {
        "delete_document": lambda p: f"删除文档「{p.get('document_id', '?')}」",
        "delete_kb_folder": lambda p: f"删除文件夹「{p.get('folder_name') or p.get('folder_id', '?')}」",
        "delete_user": lambda p: f"删除用户「{p.get('user_name') or p.get('user_id', '?')}」",
        "delete_department": lambda p: f"删除部门「{p.get('department_name') or p.get('department_id', '?')}」",
        "delete_uploaded_skill": lambda p: f"删除技能「{p.get('skill_name', '?')}」",
        "browser_run_task": lambda p: (p.get("task") or "?")[:200],
        "run_skill_script": lambda p: f"执行脚本「{p.get('skill_name', '?')}/{p.get('entry', '?')}」",
        "create_skill": lambda p: f"创建技能「{p.get('name', '?')}」",
    }
    builder = summaries.get(tool_name)
    if builder:
        return builder(params)
    return f"执行工具 {tool_name}"


# ── HITL 响应管理（委托 RedisHitlResponseStore） ──


def _store():
    from app.core.agent_interrupt_store import get_hitl_store

    return get_hitl_store()


def generate_confirmation_id() -> str:
    return generate_hitl_request_id("hitl")


def generate_choice_id() -> str:
    return generate_hitl_request_id("choice")


def set_pending_confirmation(
    confirmation_id: str,
    data: dict[str, Any],
    ttl: int = 86400,
) -> bool:
    """存储待确认状态。"""
    return _store().save_request(
        HitlRequest(
            request_id=confirmation_id,
            user_id=str(data.get("user_id", "")),
            type="confirmation",
            title=data.get("title", ""),
            detail=data.get("detail", ""),
            extra={k: v for k, v in data.items() if k not in ("user_id", "title", "detail")},
        ),
        ttl_seconds=ttl,
    )


def get_confirm_response(confirmation_id: str) -> str | None:
    """获取用户确认响应：「accepted」「rejected」或 None。"""
    return _store().get_response(confirmation_id)


def set_confirm_response(confirmation_id: str, response: str) -> bool:
    """写入用户确认/拒绝响应。"""
    return _store().set_response(confirmation_id, response)


def clear_pending_confirmation(confirmation_id: str) -> bool:
    """清除确认状态。"""
    return _store().clear(confirmation_id)


# ── 方案选择 ──


def set_pending_choice(choice_id: str, data: dict[str, Any], ttl: int = 86400) -> bool:
    """存储待用户选择的方案。"""
    return _store().save_request(
        HitlRequest(
            request_id=choice_id,
            user_id=str(data.get("user_id", "")),
            type="choice",
            question=str(data.get("question", "")),
            options=json.loads(data.get("options", "[]")),
            extra={k: v for k, v in data.items() if k not in ("user_id", "question", "options")},
        ),
        ttl_seconds=ttl,
    )


def get_choice_response(choice_id: str) -> str | None:
    """获取用户选择的选项；None 表示尚未选择。"""
    return _store().get_response(choice_id)


def get_choice_options(choice_id: str) -> list[str] | None:
    """获取等待中的方案选项列表。"""
    req = _store().get_request(choice_id)
    if req is None:
        return None
    return list(req.options) if req.options else None


def set_choice_response(choice_id: str, choice: str) -> bool:
    """写入用户选择的选项（含有效性校验）。"""
    if not _store().validate_response(choice_id, choice):
        logger.warning("选择的选项不在有效列表中: %s", choice)
        return False
    return _store().set_response(choice_id, choice)


def clear_pending_choice(choice_id: str) -> bool:
    """清除方案选择状态。"""
    return _store().clear(choice_id)
