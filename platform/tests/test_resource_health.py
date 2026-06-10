"""资源配置健康检查。"""

from __future__ import annotations

from app.services.resource_health_service import (
    _normalize_openai_base,
    _probe_embedding,
    check_resource_health,
    check_single_resource_health,
    merge_health_test_config,
)


def test_llm_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_health_service.get_effective_model_config",
        lambda _db: {
            "llm_base_url": "",
            "llm_api_key": "",
            "llm_model": "",
            "embedding_base_url": "",
            "embedding_api_key": "",
            "embedding_model": "",
            "rerank_base_url": "",
            "rerank_api_key": "",
            "rerank_model": "",
            "paddleocr_url": "",
            "speech_service_url": "",
            "pdf2zh_api_url": "",
        },
    )
    out = check_resource_health(None)
    assert out["llm"]["configured"] is False
    assert out["llm"]["healthy"] is False


def test_rerank_optional_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_health_service.get_effective_model_config",
        lambda _db: {
            "llm_base_url": "https://api.example.com/v1",
            "llm_api_key": "sk-test",
            "llm_model": "gpt-test",
            "embedding_base_url": "",
            "embedding_api_key": "",
            "embedding_model": "",
            "rerank_base_url": "",
            "rerank_api_key": "",
            "rerank_model": "",
            "paddleocr_url": "",
            "speech_service_url": "",
            "pdf2zh_api_url": "",
        },
    )

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    out = check_resource_health(None)
    assert out["rerank"]["healthy"] is None
    assert out["llm"]["healthy"] is True


def test_normalize_openai_base_strips_embeddings_suffix():
    assert _normalize_openai_base("https://api.siliconflow.cn/v1/embeddings") == (
        "https://api.siliconflow.cn/v1"
    )


def test_embedding_probe_uses_post_embeddings(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            calls.append(("post", url))
            return FakeResponse()

        def get(self, url, headers=None):
            calls.append(("get", url))
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    ok, msg = _probe_embedding(
        "https://api.siliconflow.cn/v1",
        "sk-test",
        "Pro/BAAI/bge-m3",
    )
    assert ok is True
    assert msg == "连接正常"
    assert calls == [("post", "https://api.siliconflow.cn/v1/embeddings")]


def test_embedding_health_via_check(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_health_service.get_effective_model_config",
        lambda _db: {
            "llm_base_url": "",
            "llm_api_key": "",
            "llm_model": "",
            "embedding_base_url": "https://api.siliconflow.cn/v1",
            "embedding_api_key": "sk-test",
            "embedding_model": "Pro/BAAI/bge-m3",
            "rerank_base_url": "",
            "rerank_api_key": "",
            "rerank_model": "",
            "paddleocr_url": "",
            "speech_service_url": "",
            "pdf2zh_api_url": "",
        },
    )

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            return FakeResponse()

        def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    out = check_resource_health(None)
    assert out["embedding"]["healthy"] is True


def test_merge_health_test_config_keeps_masked_secret(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_health_service.get_effective_model_config",
        lambda _db: {
            "llm_base_url": "https://api.example.com/v1",
            "llm_api_key": "sk-real-secret-key",
            "llm_model": "gpt-test",
        },
    )
    merged = merge_health_test_config(
        None,
        {
            "llm_base_url": "https://api.new.com/v1",
            "llm_api_key": "sk-re••••-key",
            "llm_model": "gpt-new",
        },
    )
    assert merged["llm_base_url"] == "https://api.new.com/v1"
    assert merged["llm_api_key"] == "sk-real-secret-key"
    assert merged["llm_model"] == "gpt-new"


def test_check_single_resource_llm(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_health_service.get_effective_model_config",
        lambda _db: {},
    )

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    cfg = {
        "llm_base_url": "https://api.example.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "gpt-test",
    }
    out = check_single_resource_health("llm", cfg, None)
    assert out["healthy"] is True
