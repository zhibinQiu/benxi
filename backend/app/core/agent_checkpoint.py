"""Agent 执行状态 Checkpoint — 对 agentkit-interrupt 的 Redis 后端适配层。

保留向后兼容的 API，底层委托给 agentkit-interrupt + RedisInterruptStore。
"""

from __future__ import annotations

from typing import Any

from agentkit_interrupt import (
    clear_interrupt as _clear_interrupt,
    list_user_interrupts as _list_user_interrupts,
    load_interrupt as _load_interrupt,
    save_interrupt_before_wait as _save_interrupt,
)

# 单例 store
_store: Any = None


def _get_store():
    global _store
    if _store is None:
        from app.core.agent_interrupt_store import RedisInterruptStore

        _store = RedisInterruptStore()
    return _store


def save_checkpoint(
    checkpoint_id: str,
    *,
    user_id: str,
    phase: str,
    loop_state: dict[str, Any],
    working: list[dict[str, Any]],
    pending_data: dict[str, Any],
    **extra: Any,
) -> bool:
    """保存 checkpoint。"""
    store = _get_store()
    result = _save_interrupt(
        store,
        checkpoint_id=checkpoint_id,
        user_id=user_id,
        phase=phase,
        loop_state=loop_state,
        working=working,
        pending_data=pending_data,
        tool_call=extra.pop("tool_call", None),
        **extra,
    )
    return result is not None


def load_checkpoint(checkpoint_id: str) -> dict[str, Any] | None:
    """加载 checkpoint，返回 dict 格式（向后兼容）。"""
    store = _get_store()
    state = _load_interrupt(store, checkpoint_id)
    if state is None:
        return None
    return {
        "user_id": state.user_id,
        "phase": state.phase,
        "loop_state": state.loop_state,
        "working": state.working,
        "pending_data": state.pending_data,
        "tool_call": state.tool_call,
    }


def clear_checkpoint(checkpoint_id: str) -> bool:
    """清除 checkpoint。"""
    store = _get_store()
    return _clear_interrupt(store, checkpoint_id)


def generate_checkpoint_id() -> str:
    """生成 checkpoint ID。"""
    from agentkit_interrupt import generate_checkpoint_id as _gen

    return _gen()


def get_pending_checkpoints_for_user(user_id: str) -> list[dict[str, Any]]:
    """列出用户的待处理 checkpoint。"""
    store = _get_store()
    return _list_user_interrupts(store, user_id)
