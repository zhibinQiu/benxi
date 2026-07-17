"""agentkit-interrupt — Agent 执行中断、Checkpoint 与恢复。

宿主通过实现 ``InterruptStore`` 协议接入存储后端（Redis、内存等），
然后使用 ``save_interrupt_before_wait()`` 和 ``load_interrupt()`` 管理中断生命周期。

HITL 响应管理通过 ``HitlResponseStore`` 协议完成确认/选择的"响应盒"模式。
"""

from app.agentkit import __version__  # noqa: F401

from app.agentkit.interrupt.hitl import (
    HitlRequest,
    HitlResponseStore,
    generate_hitl_request_id,
)
from app.agentkit.interrupt.lifecycle import (
    clear_interrupt,
    list_user_interrupts,
    load_interrupt,
    save_interrupt_before_wait,
)
from app.agentkit.interrupt.memory import InMemoryInterruptStore
from app.agentkit.interrupt.model import (
    InterruptInfo,
    InterruptState,
    generate_checkpoint_id,
)
from app.agentkit.interrupt.store import InterruptStore

__all__ = [
    "HitlRequest",
    "HitlResponseStore",
    "InMemoryInterruptStore",
    "InterruptInfo",
    "InterruptState",
    "InterruptStore",
    "clear_interrupt",
    "generate_checkpoint_id",
    "generate_hitl_request_id",
    "list_user_interrupts",
    "load_interrupt",
    "save_interrupt_before_wait",
]
