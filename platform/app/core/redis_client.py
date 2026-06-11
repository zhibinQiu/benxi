"""Redis 连接（可选；不可用时上层应降级）。"""

from __future__ import annotations

import logging
from functools import lru_cache

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis_client() -> redis.Redis | None:
    settings = get_settings()
    if not settings.platform_cache_enabled:
        return None
    timeout = max(0.1, float(settings.redis_socket_timeout_sec))
    try:
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.debug("Redis 不可用，将降级: %s", exc)
        return None
