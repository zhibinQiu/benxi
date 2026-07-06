"""系统配置与文档详情缓存测试。"""

from __future__ import annotations

import pytest

from app.core.platform_cache import (
    client_config_cache_key,
    document_detail_cache_key,
    invalidate_scope_tree_cache,
    invalidate_system_config_cache,
    scope_tree_cache_key,
)


@pytest.fixture(autouse=True)
def _enable_cache(monkeypatch):
    monkeypatch.setattr(
        "app.core.platform_cache.get_settings",
        lambda: type(
            "S",
            (),
            {
                "platform_cache_enabled": True,
                "platform_cache_ttl_sec": 60,
                "platform_cache_client_config_ttl_sec": 300,
                "platform_cache_document_detail_ttl_sec": 90,
            },
        )(),
    )
    from app.core import platform_cache as pc

    pc._local_cache.clear()


def test_client_config_cache_key_stable():
    assert client_config_cache_key() == "sys:client-config"


def test_document_detail_cache_key_includes_user():
    key = document_detail_cache_key("doc-1", "user-2")
    assert key == "doc:detail:doc-1:user-2"


def test_scope_tree_cache_key_includes_user():
    key = scope_tree_cache_key("user-2")
    assert key == "knowledge:scope-tree:v3:user-2"


def test_invalidate_scope_tree_cache():
    from app.core import platform_cache as pc

    key = scope_tree_cache_key("user-x")
    pc.cache_set_json(key, {"items": []})
    assert pc.cache_get_json(key) is not None
    invalidate_scope_tree_cache("user-x")
    assert pc.cache_get_json(key) is None


def test_invalidate_system_config_cache():
    from app.core import platform_cache as pc

    pc.cache_set_json(client_config_cache_key(), {"api_base": "http://x"})
    assert pc.cache_get_json(client_config_cache_key()) is not None
    invalidate_system_config_cache()
    assert pc.cache_get_json(client_config_cache_key()) is None
