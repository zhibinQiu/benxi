"""Redis 实现的 InterruptStore 和 HitlResponseStore。

本模块不是 agentkit-interrupt 包的一部分，因为它依赖
平台特定的 ``app.core.redis_client.get_redis_client()``。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agentkit_interrupt import HitlRequest, HitlResponseStore, InterruptState

logger = logging.getLogger(__name__)

# ── 通用 Redis 辅助 ──────────────────────────────


def _client():
    from app.core.redis_client import get_redis_client

    return get_redis_client()


def _serialize(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ── Checkpoint (InterruptStore) ──────────────────

_CKPT_PREFIX = "hitl:ckpt:"
_CKPT_TTL = 86400


def _checkpoint_key(cp_id: str) -> str:
    return f"{_CKPT_PREFIX}{cp_id}"


class RedisInterruptStore:
    """InterruptStore 协议的 Redis 后端实现。"""

    def save(self, state: InterruptState, ttl_seconds: int = _CKPT_TTL) -> bool:
        client = _client()
        if not client:
            logger.warning("Redis 不可用，无法保存中断状态")
            return False
        key = _checkpoint_key(state.checkpoint_id)
        try:
            payload = {
                "user_id": state.user_id,
                "phase": state.phase,
                "loop_state": _serialize(state.loop_state),
                "working": _serialize(state.working),
                "pending_data": _serialize(state.pending_data),
                "tool_call": _serialize(state.tool_call) if state.tool_call else "null",
            }
            for k, v in state.extra.items():
                payload[f"extra:{k}"] = _serialize(v) if not isinstance(v, str) else v

            pipe = client.pipeline()
            pipe.hset(key, mapping=payload)
            pipe.expire(key, ttl_seconds)
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning("保存中断状态失败: %s", exc)
            return False

    def load(self, checkpoint_id: str) -> InterruptState | None:
        client = _client()
        if not client:
            return None
        key = _checkpoint_key(checkpoint_id)
        try:
            raw = client.hgetall(key)
            if not raw:
                return None
            tool_call_raw = raw.get("tool_call", "null")
            return InterruptState(
                checkpoint_id=checkpoint_id,
                user_id=str(raw.get("user_id", "")),
                phase=str(raw.get("phase", "")),  # type: ignore
                loop_state=_deserialize(raw.get("loop_state")) or {},
                working=_deserialize(raw.get("working")) or [],
                pending_data=_deserialize(raw.get("pending_data")) or {},
                tool_call=_deserialize(tool_call_raw) if tool_call_raw != "null" else None,
            )
        except Exception as exc:
            logger.warning("加载中断状态失败: %s", exc)
            return None

    def clear(self, checkpoint_id: str) -> bool:
        client = _client()
        if not client:
            return False
        try:
            return bool(client.delete(_checkpoint_key(checkpoint_id)))
        except Exception:
            return False

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        client = _client()
        if not client:
            return []
        try:
            cursor = 0
            results: list[dict[str, Any]] = []
            while True:
                cursor, keys = client.scan(cursor=cursor, match=f"{_CKPT_PREFIX}*", count=100)
                for key in keys:
                    raw = client.hgetall(key)
                    if not raw:
                        continue
                    if str(raw.get("user_id", "")) != user_id:
                        continue
                    cp_id = key.replace(_CKPT_PREFIX, "", 1)
                    results.append({
                        "checkpoint_id": cp_id,
                        "phase": str(raw.get("phase", "")),
                        "pending_data": _deserialize(raw.get("pending_data")) or {},
                    })
                if cursor == 0:
                    break
            return results
        except Exception as exc:
            logger.warning("扫描中断状态失败: %s", exc)
            return []


# ── HITL 响应 (HitlResponseStore) ────────────────

_HITL_PREFIX = "hitl:confirm:"  # confirmation/choice 共用前缀


def _hitl_key(request_id: str) -> str:
    return f"{_HITL_PREFIX}{request_id}"


class RedisHitlResponseStore:
    """HitlResponseStore 协议的 Redis 后端实现。

    统一管理 confirmation 和 choice 两种 HITL 响应模式。
    """

    def __init__(self, ttl_seconds: int = 86400):
        self._ttl = ttl_seconds

    def save_request(self, request: HitlRequest, ttl_seconds: int = 0) -> bool:
        client = _client()
        if not client:
            logger.warning("Redis 不可用，无法保存 HITL 请求")
            return False
        ttl = ttl_seconds or self._ttl
        key = _hitl_key(request.request_id)
        try:
            mapping: dict[str, Any] = {
                "user_id": request.user_id,
                "type": request.type,
            }
            if request.title:
                mapping["title"] = request.title
            if request.detail:
                mapping["detail"] = request.detail
            if request.question:
                mapping["question"] = request.question
            if request.options:
                mapping["options"] = _serialize(list(request.options))
            mapping.update({f"ext:{k}": _serialize(v) for k, v in request.extra.items()})
            pipe = client.pipeline()
            pipe.hset(key, mapping={k: v if isinstance(v, str) else _serialize(v) for k, v in mapping.items()})
            pipe.expire(key, ttl)
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning("Redis 写入 HITL 请求失败: %s", exc)
            return False

    def get_request(self, request_id: str) -> HitlRequest | None:
        client = _client()
        if not client:
            return None
        try:
            raw = client.hgetall(_hitl_key(request_id))
            if not raw:
                return None
            return HitlRequest(
                request_id=request_id,
                user_id=str(raw.get("user_id", "")),
                type=str(raw.get("type", "confirmation")),
                title=str(raw.get("title", "")),
                detail=str(raw.get("detail", "")),
                question=str(raw.get("question", "")),
                options=_deserialize(raw.get("options")) or [],
            )
        except Exception:
            return None

    def get_response(self, request_id: str) -> str | None:
        client = _client()
        if not client:
            return None
        try:
            return client.hget(_hitl_key(request_id), "response")
        except Exception:
            return None

    def set_response(self, request_id: str, response: str) -> bool:
        client = _client()
        if not client:
            return False
        try:
            return bool(client.hset(_hitl_key(request_id), "response", response))
        except Exception as exc:
            logger.warning("Redis 写入 HITL 响应失败: %s", exc)
            return False

    def clear(self, request_id: str) -> bool:
        client = _client()
        if not client:
            return False
        try:
            return bool(client.delete(_hitl_key(request_id)))
        except Exception:
            return False

    def validate_response(self, request_id: str, response: str) -> bool:
        """验证 choice 响应是否在 options 列表中。"""
        req = self.get_request(request_id)
        if req is None:
            return False
        if req.type == "choice" and req.options:
            return response in req.options
        # confirmation — 任何非空字符串都有效
        return bool(response)


# ── 单例工厂 ────────────────────────────────────

_INTERRUPT_STORE: RedisInterruptStore | None = None
_HITL_STORE: RedisHitlResponseStore | None = None


def get_interrupt_store() -> RedisInterruptStore:
    global _INTERRUPT_STORE
    if _INTERRUPT_STORE is None:
        _INTERRUPT_STORE = RedisInterruptStore()
    return _INTERRUPT_STORE


def get_hitl_store() -> RedisHitlResponseStore:
    global _HITL_STORE
    if _HITL_STORE is None:
        _HITL_STORE = RedisHitlResponseStore()
    return _HITL_STORE
