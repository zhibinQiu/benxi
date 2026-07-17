"""Interrupt 模式核心类型。

定义中断状态、checkpoint 数据模型、以及中断-恢复生命周期中的枚举阶段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agentkit.loop.state import LoopState

InterruptPhase = Literal[
    "awaiting_confirmation",  # 等待用户确认
    "awaiting_choice",  # 等待用户从多方案中选择
]

InterruptResponse = Literal["accepted", "rejected"] | str


@dataclass(frozen=True, slots=True)
class InterruptState:
    """Checkpoint 保存的完整中断状态。

    ``loop_state`` 和 ``working`` 由宿主负责序列化/反序列化，
    本库仅做透传，不假设其内部结构。
    """

    checkpoint_id: str
    user_id: str
    phase: InterruptPhase
    loop_state: LoopState  # 宿主 loop 上下文
    working: list[dict[str, Any]]  # LLM 消息列表
    pending_data: dict[str, Any]  # 待处理的确认/选择数据
    tool_call: dict[str, Any] | None = None  # 待执行的 tool_call
    extra: dict[str, Any] = field(default_factory=dict)  # 宿主扩展字段


@dataclass(frozen=True, slots=True)
class InterruptInfo:
    """中断信息 — 用于 SSE 事件 Payload 和前端展示。"""

    checkpoint_id: str
    phase: InterruptPhase
    title: str
    detail: str
    confirmation_id: str = ""
    choice_id: str = ""
    question: str = ""
    options: list[str] = field(default_factory=list)


def generate_checkpoint_id() -> str:
    """生成全局唯一的 checkpoint ID。"""
    import uuid

    return f"ckpt-{uuid.uuid4().hex[:16]}"
