"""InterruptStore 协议 — 解耦存储后端。

宿主实现 ``InterruptStore`` 协议即可接入任意后端（Redis、内存、DB 等），
本库不依赖任何特定的存储实现。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.agentkit.interrupt.model import InterruptState


@runtime_checkable
class InterruptStore(Protocol):
    """中断状态存储协议 —— 宿主必须实现此接口。"""

    def save(self, state: InterruptState, ttl_seconds: int = 86400) -> bool:
        """保存中断状态。返回是否成功。"""
        ...

    def load(self, checkpoint_id: str) -> InterruptState | None:
        """加载中断状态。返回 None 表示不存在或已过期。"""
        ...

    def clear(self, checkpoint_id: str) -> bool:
        """清除中断状态。"""
        ...

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """列出某个用户的全部待处理中断。返回轻量摘要列表。"""
        ...
