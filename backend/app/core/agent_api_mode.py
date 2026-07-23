"""OpenAI 兼容 API 调用时的 Agent 运行模式（跳过 HITL 等待）。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_api_mode: ContextVar[bool] = ContextVar("agent_api_mode", default=False)


def is_api_mode() -> bool:
    return bool(_api_mode.get())


def set_api_mode(enabled: bool) -> Token:
    return _api_mode.set(bool(enabled))


def reset_api_mode(token: Token) -> None:
    try:
        _api_mode.reset(token)
    except ValueError:
        # StreamingResponse / async generator 可能在不同 Context 中关闭
        _api_mode.set(False)


@contextmanager
def agent_api_mode(enabled: bool = True) -> Iterator[None]:
    token = set_api_mode(enabled)
    try:
        yield
    finally:
        reset_api_mode(token)
