"""在线用户计数（Redis ZSET + TTL 窗口，Dashboard 读 Redis，失败时回退 DB）。"""

from __future__ import annotations

import logging
import time
import uuid

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

ONLINE_ZSET_KEY = "platform:users:online"
ONLINE_WINDOW_MINUTES = 15


def mark_user_online(user_id: uuid.UUID) -> None:
    client = get_redis_client()
    if not client:
        return
    try:
        client.zadd(ONLINE_ZSET_KEY, {str(user_id): time.time()})
    except Exception as exc:
        logger.debug("标记在线失败 user=%s: %s", user_id, exc)


def _prune_online_zset(client) -> None:
    cutoff = time.time() - ONLINE_WINDOW_MINUTES * 60
    client.zremrangebyscore(ONLINE_ZSET_KEY, 0, cutoff)


def list_online_user_ids() -> list[uuid.UUID] | None:
    """返回 Redis 窗口内的在线用户 ID；Redis 不可用时返回 None 由调用方回退 DB。"""
    client = get_redis_client()
    if not client:
        return None
    try:
        _prune_online_zset(client)
        members = client.zrange(ONLINE_ZSET_KEY, 0, -1)
        return [uuid.UUID(member) for member in members]
    except Exception as exc:
        logger.debug("读取在线用户 ID 失败: %s", exc)
        return None


def count_users_online() -> int | None:
    """返回 Redis 统计的在线人数；Redis 不可用时返回 None 由调用方回退 DB。"""
    online_ids = list_online_user_ids()
    if online_ids is None:
        return None
    return len(online_ids)
