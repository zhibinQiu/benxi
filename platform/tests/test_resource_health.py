"""资源配置健康检查。"""

from __future__ import annotations

from app.services.resource_health_service import (
    _normalize_openai_base,
    _normalize_resource_id,
    _probe_embedding,
    _probe_searxng_url,
    _probe_vl,
    _searxng_timeout_from_cfg,
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
            "paddleocr_base_url": "",
            "paddleocr_model": "",
            "vl_base_url": "",
            "vl_model": "",
            "vl_api_key": "",
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
            "paddleocr_base_url": "",
            "paddleocr_model": "",
            "vl_base_url": "",
            "vl_model": "",
            "vl_api_key": "",
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


def test_openai_compatible_inference_base_detection():
    from app.services.resource_health_service import _is_openai_compatible_inference_base

    assert _is_openai_compatible_inference_base("https://api.siliconflow.cn/v1")
    assert _is_openai_compatible_inference_base("http://127.0.0.1:8000/v1")
    assert not _is_openai_compatible_inference_base("http://127.0.0.1:8080/layout-parsing")
    assert not _is_openai_compatible_inference_base("http://127.0.0.1:7071/ocr")


def test_normalize_openai_base_strips_embeddings_suffix():
    assert _normalize_openai_base("https://api.siliconflow.cn/v1/embeddings") == (
        "https://api.siliconflow.cn/v1"
    )


def test_vl_resource_id_alias():
    assert _normalize_resource_id("vision") == "vl"
    assert _normalize_resource_id("Vision") == "vl"
    assert _normalize_resource_id("vl") == "vl"
    assert _normalize_resource_id("VL") == "vl"


def test_vl_probe_uses_post_chat_completions(monkeypatch):
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
            assert json["model"] == "Qwen/Qwen3-VL-8B-Instruct"
            return FakeResponse()

        def get(self, url, headers=None):
            calls.append(("get", url))
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    ok, msg = _probe_vl(
        "https://api.siliconflow.cn/v1",
        "sk-test",
        "Qwen/Qwen3-VL-8B-Instruct",
    )
    assert ok is True
    assert msg == "连接正常"
    assert calls == [
        ("post", "https://api.siliconflow.cn/v1/chat/completions"),
    ]


def test_vl_health_via_check(monkeypatch):
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
    cfg = {
        "vl_base_url": "https://api.siliconflow.cn/v1",
        "vl_api_key": "sk-test",
        "vl_model": "Qwen/Qwen3-VL-8B-Instruct",
    }
    out = check_single_resource_health("vision", cfg, None)
    assert out["configured"] is True
    assert out["healthy"] is True


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
            "paddleocr_base_url": "",
            "paddleocr_model": "",
            "vl_base_url": "",
            "vl_model": "",
            "vl_api_key": "",
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


def test_searxng_timeout_from_cfg_prefers_draft():
    cfg = {"searxng_timeout_seconds": "20"}
    assert _searxng_timeout_from_cfg(cfg, None) == 20.0


def test_probe_searxng_uses_configured_timeout(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"results": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("app.services.resource_health_service.httpx.Client", FakeClient)
    ok, msg = _probe_searxng_url("http://searxng.test", timeout=18)
    assert ok is True
    assert msg == "连接正常"
    assert captured["timeout"] == 18
    assert captured["url"] == "http://searxng.test/search"
    assert captured["params"]["format"] == "json"
    assert captured["headers"]["User-Agent"] == "pdf-trans-platform/1.0"


def test_check_single_resource_searxng_passes_timeout(monkeypatch):
    captured: dict = {}

    def fake_probe(url: str, *, timeout: float | None = None):
        captured["url"] = url
        captured["timeout"] = timeout
        return True, "连接正常"

    monkeypatch.setattr(
        "app.services.resource_health_service._probe_searxng_url",
        fake_probe,
    )
    cfg = {
        "searxng_url": "http://172.19.134.45:40000",
        "searxng_timeout_seconds": "15",
    }
    out = check_single_resource_health("searxng", cfg, None)
    assert out["healthy"] is True
    assert captured["timeout"] == 15.0
