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
    try:
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.debug("Redis 不可用，将降级: %s", exc)
        return None
