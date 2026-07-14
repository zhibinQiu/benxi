"""路由信号检测 — 宿主注入的意图检测契约。

本包只定义 *Protocol 接口*，不包含任何语言/平台绑定正则。
宿主应用按需实现 ``SignalDetector`` 并注入 ``infer_route_mode``。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class SignalDetector(Protocol):
    """信号检测契约：输入用户消息，输出 bool 判定。"""

    def __call__(self, message: str, /) -> bool: ...


CompoundDetector = SignalDetector
"""复合任务检测（顺序/并行）的类型别名。"""


def never_detected(_message: str) -> bool:
    """默认检测器 —— 永不命中（宿主未注入时回退）。"""
    return False


__all__ = [
    "CompoundDetector",
    "SignalDetector",
    "never_detected",
]
