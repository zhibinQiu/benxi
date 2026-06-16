"""系统资源配置。"""

from __future__ import annotations

from app.config import Settings
from app.integrations.paddleocr_client import (
    knowflow_paddleocr_settings_url,
    normalize_paddleocr_service_url,
    paddleocr_request_url,
    recognize_bytes,
)
from app.integrations.ragflow_model_apply import normalize_ragflow_embedding_api_base
from app.services.model_settings_service import (
    _endpoint_fields,
    get_llm_credentials,
    get_model_settings,
    get_pdf2zh_api_url,
    get_platform_api_base_url,
    get_searxng_timeout_seconds,
    get_searxng_url,
    get_speech_service_url,
    mask_secret,
)


def test_get_llm_credentials_reads_merged_config(monkeypatch):
    settings = Settings(
        platform_llm_base_url="http://local-llm/v1",
        platform_llm_api_key="sk-platform",
        platform_llm_model="local-chat",
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-chat",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    base, key, model = get_llm_credentials(None)
    assert base == "http://local-llm/v1"
    assert key == "sk-platform"
    assert model == "local-chat"


def test_endpoint_fields_reads_explicit_config():
    merged = {
        "vl_base_url": "https://api.siliconflow.cn/v1",
        "vl_api_key": "sk-test1234567890",
        "vl_model": "Qwen/Qwen3-VL-8B-Instruct",
        "embedding_base_url": "https://api.siliconflow.cn/v1",
        "embedding_api_key": "other-key",
    }
    base, key, model = _endpoint_fields(merged, "vl")
    assert base == "https://api.siliconflow.cn/v1"
    assert key == "sk-test1234567890"
    assert model == "Qwen/Qwen3-VL-8B-Instruct"


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("short") == "••••••••"
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a••••mnop"


def test_paddleocr_falls_back_to_vl(monkeypatch):
    settings = Settings(
        platform_paddleocr_base_url="",
        platform_paddleocr_api_key="",
        platform_paddleocr_model="",
        platform_paddleocr_url="",
        platform_vl_base_url="https://api.siliconflow.cn/v1",
        platform_vl_api_key="sk-vl-key",
        platform_vl_model="Qwen/Qwen3-VL-8B-Instruct",
        platform_embedding_base_url="https://api.siliconflow.cn/v1",
        platform_embedding_api_key="sk-emb-key",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    from app.services.model_settings_service import get_paddleocr_credentials

    base, key, model = get_paddleocr_credentials(None)
    assert base == "https://api.siliconflow.cn/v1"
    assert key == "sk-vl-key"
    assert model == "PaddlePaddle/PaddleOCR-VL-1.5"


def test_llm_falls_back_to_deepseek(monkeypatch):
    settings = Settings(
        platform_llm_base_url="",
        platform_llm_api_key="",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_api_key="sk-test1234567890",
        deepseek_model="deepseek-chat",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    out = get_model_settings(None)
    assert out.editable is True
    assert out.llm.base_url == "https://api.deepseek.com/v1"
    assert out.llm.model_name == "deepseek-chat"
    assert out.llm.api_key_configured is True
    assert "sk-t" in out.llm.api_key_masked


def test_paddleocr_url_normalization():
    assert normalize_paddleocr_service_url("http://172.20.32.127:7071/ocr") == (
        "http://172.20.32.127:7071"
    )
    assert paddleocr_request_url("http://172.20.32.127:7071/ocr") == (
        "http://172.20.32.127:7071/ocr"
    )
    assert knowflow_paddleocr_settings_url("http://172.20.32.127:7071/ocr") == (
        "http://172.20.32.127:7071/ocr"
    )
    assert knowflow_paddleocr_settings_url("http://localhost:8888") == (
        "http://localhost:8888"
    )


def test_recognize_bytes_uses_multipart_for_ocr_endpoint(monkeypatch):
    calls: list[tuple[str, dict | None, dict | None]] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"rec_texts": ["hello"], "rec_boxes": []}]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, files=None):
            calls.append((url, json, files))
            return FakeResponse()

    monkeypatch.setattr("app.integrations.paddleocr_client.httpx.Client", FakeClient)
    out = recognize_bytes(
        b"abc",
        service_url="http://172.20.32.127:7071/ocr",
        file_name="demo.png",
        mime_type="image/png",
    )
    assert out["text"] == "hello"
    assert calls[0][0] == "http://172.20.32.127:7071/ocr"
    assert calls[0][1] is None
    assert calls[0][2] is not None


def test_service_urls_from_env_defaults(monkeypatch):
    settings = Settings(
        speech_service_url="http://speech:8765",
        pdf2zh_api_url="http://pdf2zh:7861",
        searxng_url="http://172.19.134.45:40000",
        searxng_timeout_seconds=12.0,
        ragflow_api_url="http://127.0.0.1:9380",
        knowflow_backend_url="http://127.0.0.1:5001",
        knowflow_ui_url="http://127.0.0.1:9380",
        knowflow_ui_public_url="http://127.0.0.1:40005/ragflow-ui",
        knowflow_ui_proxy_prefix="/ragflow-ui",
        ragflow_mysql_host="127.0.0.1",
        ragflow_mysql_password="secret-pass",
        ragflow_mysql_db="rag_flow",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    out = get_model_settings(None)
    assert out.speech_service_url == "http://speech:8765"
    assert out.pdf2zh_api_url == "http://pdf2zh:7861"
    assert out.searxng_url == "http://172.19.134.45:40000"
    assert out.searxng_timeout_seconds == 12.0
    assert out.knowledge.ragflow_api_url == "http://127.0.0.1:9380"
    assert out.knowledge.knowflow_backend_url == "http://127.0.0.1:5001"
    assert out.knowledge.knowflow_ui_url == "http://127.0.0.1:9380"
    assert out.knowledge.knowflow_ui_public_url == "http://127.0.0.1:40005/ragflow-ui"
    assert out.knowledge.knowflow_ui_proxy_prefix == "/ragflow-ui"
    assert out.knowledge.ragflow_mysql_host == "127.0.0.1"
    assert out.knowledge.ragflow_mysql_db == "rag_flow"
    assert out.knowledge.ragflow_mysql_password_configured is True
    assert get_speech_service_url(None) == "http://speech:8765"
    assert get_pdf2zh_api_url(None) == "http://pdf2zh:7861"
    assert get_searxng_url(None) == "http://172.19.134.45:40000"
    assert get_searxng_timeout_seconds(None) == 12.0


def test_platform_api_base_url_defaults_to_public_prefix(monkeypatch):
    settings = Settings(api_public_path_prefix="/ai", platform_api_base_url="")
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    out = get_model_settings(None)
    assert out.platform_api_base_url == "/ai"
    assert get_platform_api_base_url(None) == "/ai"


def test_platform_api_base_url_from_env(monkeypatch):
    settings = Settings(
        api_public_path_prefix="/ai",
        platform_api_base_url="http://172.19.134.45:40005/ai",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    out = get_model_settings(None)
    assert out.platform_api_base_url == "http://172.19.134.45:40005/ai"
    assert get_platform_api_base_url(None) == "http://172.19.134.45:40005/ai"


def test_frontend_client_config_from_env(monkeypatch):
    from app.services.model_settings_service import (
        get_frontend_app_title,
        get_frontend_default_theme,
    )

    settings = Settings(
        app_name="默认系统名",
        frontend_app_title="企业 AI 知识库平台",
        frontend_default_theme="light",
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    out = get_model_settings(None)
    assert out.frontend_app_title == "企业 AI 知识库平台"
    assert out.frontend_default_theme == "light"
    assert get_frontend_app_title(None) == "企业 AI 知识库平台"


def test_frontend_app_title_falls_back_to_app_name(monkeypatch):
    from app.services.model_settings_service import get_frontend_app_title

    settings = Settings(app_name="环境系统名", frontend_app_title="")
    monkeypatch.setattr(
        "app.services.model_settings_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.model_settings_service.fetch_template_embedding_defaults",
        lambda _db: {},
    )
    assert get_frontend_app_title(None) == "环境系统名"


def test_resolve_ragflow_api_base_docker(monkeypatch):
    from app.services.model_settings_service import resolve_ragflow_api_base

    assert resolve_ragflow_api_base("http://ragflow:9380", knowflow_enabled=True) == (
        "http://ragflow:80"
    )
    assert resolve_ragflow_api_base("http://127.0.0.1:9380", knowflow_enabled=True) == (
        "http://127.0.0.1:9380"
    )


def test_searxng_health_test_supported(client, admin_token, monkeypatch):
    from app.services.resource_health_service import TESTABLE_RESOURCE_IDS

    assert "searxng" in TESTABLE_RESOURCE_IDS

    def fake_probe(url: str, timeout: float | None = None) -> tuple[bool, str]:
        assert url == "http://searxng.test"
        return True, "连接正常"

    monkeypatch.setattr(
        "app.services.resource_health_service._probe_searxng_url",
        fake_probe,
    )
    r = client.post(
        "/api/v1/admin/model-settings/health/test",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "resource_id": "searxng",
            "draft": {"searxng_url": "http://searxng.test"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["healthy"] is True


def test_vl_health_test_supported(client, admin_token, monkeypatch):
    from app.services.resource_health_service import TESTABLE_RESOURCE_IDS

    assert "vl" in TESTABLE_RESOURCE_IDS

    def fake_probe(base_url: str, api_key: str, model_name: str) -> tuple[bool, str]:
        assert base_url == "https://api.siliconflow.cn/v1"
        assert api_key == "sk-test"
        assert model_name == "Qwen/Qwen3-VL-8B-Instruct"
        return True, "连接正常"

    monkeypatch.setattr(
        "app.services.resource_health_service._probe_vl",
        fake_probe,
    )
    r = client.post(
        "/api/v1/admin/model-settings/health/test",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "resource_id": "vl",
            "draft": {
                "vl_base_url": "https://api.siliconflow.cn/v1",
                "vl_api_key": "sk-test",
                "vl_model": "Qwen/Qwen3-VL-8B-Instruct",
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["healthy"] is True


def test_normalize_ragflow_embedding_api_base_for_siliconflow():
    assert (
        normalize_ragflow_embedding_api_base("https://api.siliconflow.cn/v1", "SILICONFLOW")
        == "https://api.siliconflow.cn/v1/embeddings"
    )
    assert (
        normalize_ragflow_embedding_api_base("https://api.siliconflow.cn/v1/embeddings", "SILICONFLOW")
        == "https://api.siliconflow.cn/v1/embeddings"
    )


def test_normalize_ragflow_embedding_api_base_strips_v1_for_openai_compatible():
    assert (
        normalize_ragflow_embedding_api_base("https://example.com/v1", "OpenAI-API-Compatible")
        == "https://example.com"
    )
