"""轻量进程级 TTL 缓存 — 针对频繁查询、极少变更的 DB 数据。"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def ttl_cache(ttl: float = 3.0) -> Callable[[F], F]:
    """装饰器：对函数结果做进程级 TTL 缓存，key 由 args+k 生成。

    用法:
        @ttl_cache(ttl=5.0)
        def expensive_query(db, user_id):
            ...

    注意: 第一个参数 db 会被忽略（不作为 cache key 的一部分），
          因为同一次调用内 session 对象不同但结果应相同。
    """

    def decorator(func: F) -> F:
        cache: dict[str, tuple[float, Any]] = {}

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 忽略第一个参数（db session），构建 cache key
            key_parts: list[str] = []
            for i, a in enumerate(args):
                if i == 0:
                    continue  # skip db
                key_parts.append(f"{type(a).__name__}:{a!r}")
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={type(v).__name__}:{v!r}")
            key = "#".join(key_parts)

            now = time.monotonic()
            cached = cache.get(key)
            if cached is not None and now - cached[0] < ttl:
                return cached[1]

            result = func(*args, **kwargs)
            cache[key] = (now, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
