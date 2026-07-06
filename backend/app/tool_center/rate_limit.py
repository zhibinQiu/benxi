"""ToolCenter 内存 QPS 限流 — Tool 无实例状态，按 tool_id 滑动窗口计数。"""

from __future__ import annotations

import threading
import time
from collections import deque


class ToolRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}

    def allow(self, tool_id: str, *, qps: int) -> bool:
        if qps <= 0:
            return True
        now = time.monotonic()
        window_sec = 1.0
        with self._lock:
            bucket = self._windows.setdefault(tool_id, deque())
            while bucket and now - bucket[0] > window_sec:
                bucket.popleft()
            if len(bucket) >= qps:
                return False
            bucket.append(now)
            return True


_limiter = ToolRateLimiter()


def check_rate_limit(tool_id: str, *, qps: int) -> bool:
    return _limiter.allow(tool_id, qps=qps)
