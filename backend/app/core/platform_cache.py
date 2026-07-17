"""平台级缓存：L1 进程热缓存 → L2 Redis 分布式缓存，读写穿透双写。"""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from datetime import date, datetime
from typing import Any, Callable, TypeVar

import orjson

from app.config import get_settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

_local_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_LOCAL_CACHE_MAX_ENTRIES = 512
# 缓存失效后仍在执行的 factory 不应写回旧值
_cache_factory_epoch: dict[str, int] = {}


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _orjson_dumps(obj: Any) -> str:
    return orjson.dumps(obj, default=_json_default).decode("utf-8")


_orjson_loads = orjson.loads


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
        return _orjson_loads(raw)
    except orjson.JSONDecodeError:
        return None


def _local_set(key: str, value: Any) -> None:
    _local_cache[key] = (
        time.monotonic(),
        _orjson_dumps(value),
    )
    _local_cache.move_to_end(key)
    if len(_local_cache) > _LOCAL_CACHE_MAX_ENTRIES:
        _local_cache.popitem(last=False)


def cache_get_json(key: str, *, ttl: int | None = None) -> Any | None:
    """读缓存：L1 进程热缓存 → L2 Redis。

    先查 L1（零网络开销），命中则直接返回；L1 未命中时查 L2 Redis，命中后回填 L1。
    Redis 不可用或未命中时返回 None（由上层 factory 或调用方自行兜底）。
    """
    if not cache_enabled():
        return None
    seconds = ttl if ttl is not None else get_settings().platform_cache_ttl_sec
    seconds = max(1, int(seconds))

    # L1 热缓存：零网络开销，高频数据加速
    local_val = _local_get(key, seconds)
    if local_val is not None:
        return local_val

    # L2 分布式缓存
    client = get_redis_client()
    if client:
        try:
            raw = client.get(key)
            if raw is not None:
                val = _orjson_loads(raw)
                _local_set(key, val)  # 从 L2 回填 L1
                return val
        except Exception as exc:
            logger.debug("Redis cache get 失败 key=%s: %s", key, exc)

    return None


def cache_set_json(key: str, value: Any, *, ttl: int | None = None) -> None:
    """写缓存：双写到 L2 Redis（TTL 持久化）+ L1 进程缓存。"""
    if not cache_enabled():
        return
    seconds = ttl if ttl is not None else get_settings().platform_cache_ttl_sec
    seconds = max(1, int(seconds))
    raw = _orjson_dumps(value)
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
    for key in list(_cache_factory_epoch):
        if key.startswith(prefix):
            _cache_factory_epoch[key] = _cache_factory_epoch.get(key, 0) + 1


def cache_get_or_set(
    key: str,
    factory: Callable[[], T],
    *,
    ttl: int | None = None,
) -> T:
    epoch_start = _cache_factory_epoch.get(key, 0)
    cached = cache_get_json(key, ttl=ttl)
    if cached is not None:
        return cached
    value = factory()
    if _cache_factory_epoch.get(key, 0) != epoch_start:
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


_SCOPE_TREE_CACHE_VERSION = 3


def scope_tree_cache_key(user_id: str) -> str:
    """知识检索 / 报告生成左侧文档树。"""
    return f"knowledge:scope-tree:v{_SCOPE_TREE_CACHE_VERSION}:{user_id}"


def invalidate_scope_tree_cache(user_id: str | uuid.UUID | None = None) -> None:
    if user_id is not None:
        cache_delete_prefix(scope_tree_cache_key(str(user_id)))
    else:
        cache_delete_prefix("knowledge:scope-tree:")


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


def client_config_cache_key() -> str:
    return "sys:client-config"


def dashboard_stats_cache_key() -> str:
    return "sys:dashboard-stats:v2"


def features_cache_key(user_id: str) -> str:
    return f"sys:features:{user_id}"


def document_detail_cache_key(document_id: str, user_id: str) -> str:
    return f"doc:detail:{document_id}:{user_id}"


def invalidate_system_config_cache() -> None:
    cache_delete_prefix(client_config_cache_key())


def invalidate_dashboard_cache() -> None:
    cache_delete_prefix(dashboard_stats_cache_key())


def invalidate_features_cache(user_id: str | uuid.UUID | None = None) -> None:
    if user_id:
        cache_delete_prefix(features_cache_key(str(user_id)))
    else:
        cache_delete_prefix("sys:features:")


def invalidate_document_detail_cache(
    document_id: str | uuid.UUID | None = None,
    user_id: str | uuid.UUID | None = None,
) -> None:
    if document_id and user_id:
        cache_delete_prefix(
            document_detail_cache_key(str(document_id), str(user_id))
        )
    elif document_id:
        cache_delete_prefix(f"doc:detail:{document_id}:")
    else:
        cache_delete_prefix("doc:detail:")


def invalidate_document_caches(user_id: str | None = None) -> None:
    """文档/文件夹变更后清理相关缓存。"""
    invalidate_document_library_cache(user_id)
    invalidate_kb_folders_cache(user_id)
    invalidate_document_detail_cache(user_id=user_id)
    invalidate_scope_tree_cache(user_id)


_KG_GRAPH_CACHE_VERSION = 1


def kg_graph_cache_key(
    user_id: str,
    focus_entity_id: str | None,
    depth: int,
) -> str:
    focus = focus_entity_id or "_"
    return f"kg:graph:v{_KG_GRAPH_CACHE_VERSION}:{user_id}:{focus}:{depth}"


def kg_meta_cache_key(user_id: str, sync_system: bool) -> str:
    flag = "sync" if sync_system else "nosync"
    return f"kg:meta:v{_KG_GRAPH_CACHE_VERSION}:{user_id}:{flag}"


def kg_entities_cache_key(
    user_id: str,
    type_id: str | None,
    q: str | None,
) -> str:
    import hashlib

    type_part = type_id or "_"
    q_norm = (q or "").strip()
    q_part = q_norm if q_norm else "_"
    if len(q_part) > 48:
        q_part = hashlib.sha256(q_part.encode("utf-8")).hexdigest()[:16]
    return f"kg:entities:v{_KG_GRAPH_CACHE_VERSION}:{user_id}:{type_part}:{q_part}"


def kg_relations_cache_key(
    user_id: str,
    entity_id: str | None,
    relation_type_id: str | None,
) -> str:
    entity_part = entity_id or "_"
    type_part = relation_type_id or "_"
    return f"kg:relations:v{_KG_GRAPH_CACHE_VERSION}:{user_id}:{entity_part}:{type_part}"


def invalidate_kg_cache(user_id: str | uuid.UUID | None = None) -> None:
    """知识图谱子图/元数据/列表变更后清理缓存。"""
    prefixes = (
        f"kg:graph:v{_KG_GRAPH_CACHE_VERSION}:",
        f"kg:meta:v{_KG_GRAPH_CACHE_VERSION}:",
        f"kg:entities:v{_KG_GRAPH_CACHE_VERSION}:",
        f"kg:relations:v{_KG_GRAPH_CACHE_VERSION}:",
    )
    if user_id:
        uid = str(user_id)
        for prefix in prefixes:
            cache_delete_prefix(f"{prefix}{uid}:")
    else:
        for prefix in prefixes:
            cache_delete_prefix(prefix)
