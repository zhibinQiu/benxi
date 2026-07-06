"""请求级用户上下文缓存：同一请求内复用权限/部门/角色查询结果。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_cache: ContextVar[dict[str, Any] | None] = ContextVar("request_user_cache", default=None)


def clear_request_user_cache() -> None:
    _cache.set(None)


def cached_per_request(key: str, factory: Callable[[], T]) -> T:
    store = _cache.get()
    if store is None:
        store = {}
        _cache.set(store)
    if key not in store:
        store[key] = factory()
    return store[key]
