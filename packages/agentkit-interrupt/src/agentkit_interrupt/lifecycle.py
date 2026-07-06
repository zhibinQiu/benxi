"""中断生命周期 — save / load / clear / resume 原子操作。

这里的函数是对 ``InterruptStore`` 协议的高阶封装，
宿主可以在 tool loop 中直接调用 ``save_interrupt_before_wait()``
和 ``resume_from_interrupt()``。
"""

from __future__ import annotations

import logging
from typing import Any

from agentkit_interrupt.model import (
    InterruptState,
    generate_checkpoint_id,
)
from agentkit_interrupt.store import InterruptStore

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24h


def save_interrupt_before_wait(
    store: InterruptStore,
    *,
    user_id: str,
    phase: str,
    loop_state: dict[str, Any],
    working: list[dict[str, Any]],
    pending_data: dict[str, Any],
    checkpoint_id: str | None = None,
    tool_call: dict[str, Any] | None = None,
    ttl: int = DEFAULT_TTL_SECONDS,
    **extra: Any,
) -> str | None:
    """进入等待前保存中断状态。

    返回 checkpoint_id（成功时）或 None（失败时）。
    宿主应在返回 None 时降级为直接报错。

    如果未传入 ``checkpoint_id``，会自动生成一个。
    """
    cp_id = checkpoint_id or generate_checkpoint_id()
    state = InterruptState(
        checkpoint_id=cp_id,
        user_id=user_id,
        phase=phase,  # type: ignore
        loop_state=loop_state,
        working=working,
        pending_data=pending_data,
        tool_call=tool_call,
        extra=extra,
    )
    ok = store.save(state, ttl_seconds=ttl)
    if not ok:
        logger.warning("保存中断状态失败: phase=%s user=%s", phase, user_id)
        return None
    logger.info("中断状态已保存: id=%s phase=%s", cp_id, phase)
    return cp_id


def load_interrupt(
    store: InterruptStore,
    checkpoint_id: str,
) -> InterruptState | None:
    """加载中断状态。"""
    return store.load(checkpoint_id)


def clear_interrupt(
    store: InterruptStore,
    checkpoint_id: str,
) -> bool:
    """清除中断状态。"""
    return store.clear(checkpoint_id)


def list_user_interrupts(
    store: InterruptStore,
    user_id: str,
) -> list[dict[str, Any]]:
    """列出用户的待处理中断。"""
    return store.list_for_user(user_id)
