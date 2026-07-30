"""HITL 响应管理类型 — 确认/选择的"响应盒"模式。

HITL (Human-in-the-Loop) 的确认和选择本质上是一个"响应盒"模式：
1. Agent 设置一个待处理请求（存 question + options）
2. 前端展示给用户
3. 用户回应后写入响应
4. Agent 读取响应后继续

这个协议将确认(confirmation)和选择(choice)统一为同一个接口。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HitlRequest:
    """HITL 请求 — 向用户展示的信息。"""

    request_id: str
    user_id: str
    type: str  # "confirmation" | "choice"
    title: str = ""
    detail: str = ""
    question: str = ""
    options: Sequence[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class HitlResponseStore(Protocol):
    """HITL 用户响应存储协议。

    宿主实现此协议以提供对用户响应消息的读写能力。
    典型后端：Redis / 内存 / DB。
    """

    def save_request(self, request: HitlRequest, ttl_seconds: int = 86400) -> bool:
        """保存一个待响应的 HITL 请求。"""
        ...

    def get_response(self, request_id: str) -> str | None:
        """获取用户响应值。返回 None 表示尚未响应。"""
        ...

    def get_request(self, request_id: str) -> HitlRequest | None:
        """获取请求的原始内容。"""
        ...

    def set_response(self, request_id: str, response: str) -> bool:
        """写入用户的响应值。返回是否成功。"""
        ...

    def clear(self, request_id: str) -> bool:
        """清除 HITL 请求（无论是否已响应）。"""
        ...

    def validate_response(self, request_id: str, response: str) -> bool:
        """验证响应值对请求是否有效（例如 choice 必须在 options 中）。"""
        ...


def generate_hitl_request_id(prefix: str = "hitl") -> str:
    """生成全局唯一的 HITL 请求 ID。"""
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:12]}"
