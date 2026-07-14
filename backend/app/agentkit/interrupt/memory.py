"""内存实现的 InterruptStore — 用于测试和开发环境。"""

from __future__ import annotations

import time
from typing import Any

from app.agentkit.interrupt.model import InterruptState

DEFAULT_TTL_SECONDS = 86400


class InMemoryInterruptStore:
    """内存版 InterruptStore — 不依赖外部存储，适合单元测试。

    用法:
        store = InMemoryInterruptStore()
        store.save(state)
        loaded = store.load(cp_id)
    """

    def __init__(self):
        self._data: dict[str, tuple[InterruptState, float]] = {}  # checkpoint_id → (state, expiry)

    def _is_expired(self, expiry: float) -> bool:
        return time.monotonic() > expiry

    def save(self, state: InterruptState, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        expiry = time.monotonic() + ttl_seconds
        self._data[state.checkpoint_id] = (state, expiry)
        return True

    def load(self, checkpoint_id: str) -> InterruptState | None:
        entry = self._data.get(checkpoint_id)
        if entry is None:
            return None
        state, expiry = entry
        if self._is_expired(expiry):
            del self._data[checkpoint_id]
            return None
        return state

    def clear(self, checkpoint_id: str) -> bool:
        return self._data.pop(checkpoint_id, None) is not None

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        now = time.monotonic()
        results: list[dict[str, Any]] = []
        expired_keys: list[str] = []
        for cp_id, (state, expiry) in self._data.items():
            if self._is_expired(expiry):
                expired_keys.append(cp_id)
                continue
            if state.user_id == user_id:
                results.append({
                    "checkpoint_id": cp_id,
                    "phase": state.phase,
                    "pending_data": state.pending_data,
                })
        for k in expired_keys:
            del self._data[k]
        return results
