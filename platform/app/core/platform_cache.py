"""平台级缓存：优先 Redis，不可用时进程内 TTL 降级。"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, datetime
from typing import Any, Callable, TypeVar

from app.config import get_settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

_local_cache: dict[str, tuple[float, str]] = {}


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def cache_enabled() -> bool:
    return bool(get_settings().platform_cache_enabled)


def _local_get(key: str, ttl: int) -> Any | None:
    hit = _local_cache.get(key)
    if not hit:
        return None
    ts, raw = hit
    if time.monotonic() - ts >= ttl:
        _local_cache.pop(key, None)
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _local_set(key: str, value: Any) -> None:
    _local_cache[key] = (
        time.monotonic(),
        json.dumps(value, ensure_ascii=False, default=_json_default),
    )


def cache_get_json(key: str, *, ttl: int | None = None) -> Any | None:
    if not cache_enabled():
        return None
    seconds = ttl if ttl is not None else get_settings().platform_cache_ttl_sec
    seconds = max(1, int(seconds))
    client = get_redis_client()
    if client:
        try:
            raw = client.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis cache get 失败 key=%s: %s", key, exc)
    return _local_get(key, seconds)


def cache_set_json(key: str, value: Any, *, ttl: int | None = None) -> None:
    if not cache_enabled():
        return
    seconds = ttl if ttl is not None else get_settings().platform_cache_ttl_sec
    seconds = max(1, int(seconds))
    raw = json.dumps(value, ensure_ascii=False, default=_json_default)
    client = get_redis_client()
    if client:
        try:
            client.setex(key, seconds, raw)
        except Exception as exc:
            logger.debug("Redis cache set 失败 key=%s: %s", key, exc)
    _local_set(key, value)


def cache_delete_prefix(prefix: str) -> None:
    if not prefix:
        return
    client = get_redis_client()
    if client:
        try:
            cursor = 0
            pattern = f"{prefix}*"
            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.debug("Redis cache delete 失败 prefix=%s: %s", prefix, exc)
    doomed = [k for k in _local_cache if k.startswith(prefix)]
    for key in doomed:
        _local_cache.pop(key, None)


def cache_get_or_set(
    key: str,
    factory: Callable[[], T],
    *,
    ttl: int | None = None,
) -> T:
    cached = cache_get_json(key, ttl=ttl)
    if cached is not None:
        return cached
    value = factory()
    cache_set_json(key, value, ttl=ttl)
    return value


def ragflow_doc_meta_cache_key(dataset_id: str, ragflow_id: str) -> str:
    return f"rag:docmeta:{dataset_id}:{ragflow_id}"


def document_library_cache_key(user_id: str) -> str:
    return f"doc:library:{user_id}"


def kb_folders_cache_key(
    user_id: str,
    scope: str,
    dept_id: str | None,
    owner_id: str | None = None,
) -> str:
    dept = dept_id or "_"
    owner = owner_id or "_"
    return f"doc:kb-folders:{user_id}:{scope}:{dept}:{owner}"


def invalidate_document_library_cache(user_id: str | None = None) -> None:
    if user_id:
        cache_delete_prefix(document_library_cache_key(str(user_id)))
    else:
        cache_delete_prefix("doc:library:")


def invalidate_kb_folders_cache(user_id: str | None = None) -> None:
    if user_id:
        cache_delete_prefix(f"doc:kb-folders:{user_id}:")
    else:
        cache_delete_prefix("doc:kb-folders:")


def invalidate_ragflow_doc_meta_cache(dataset_id: str | None = None) -> None:
    if dataset_id:
        cache_delete_prefix(f"rag:docmeta:{dataset_id}:")
    else:
        cache_delete_prefix("rag:docmeta:")


def invalidate_document_caches(user_id: str | None = None) -> None:
    """文档/文件夹变更后清理相关缓存。"""
    invalidate_document_library_cache(user_id)
    invalidate_kb_folders_cache(user_id)
