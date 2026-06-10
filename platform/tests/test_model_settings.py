"""系统资源配置。"""

from __future__ import annotations

from app.config import Settings
from app.integrations.paddleocr_client import (
    knowflow_paddleocr_settings_url,
    normalize_paddleocr_service_url,
    paddleocr_request_url,
    recognize_bytes,
)
from app.services.model_settings_service import (
    get_model_settings,
    get_pdf2zh_api_url,
    get_platform_api_base_url,
    get_speech_service_url,
    mask_secret,
)


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("short") == "••••••••"
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a••••mnop"


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
        frontend_app_title="智碳平台",
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
    assert out.frontend_app_title == "智碳平台"
    assert out.frontend_default_theme == "light"
    assert get_frontend_app_title(None) == "智碳平台"


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
