"""语音合成功能测试。"""

from __future__ import annotations

import pytest

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.integrations.siliconflow_tts_client import (
    build_input_text,
    build_speech_api_url,
    is_configured,
    resolve_tts_settings,
    voice_param,
)


def test_text_to_speech_plugin_registered():
    ensure_plugins_loaded()
    p = get_plugin("text_to_speech")
    assert p is not None
    assert p.title == "语音合成"
    assert p.permission_code == "feature.text_to_speech"
    assert p.category == "tools"
    assert p.route == "/system/text-to-speech"
    assert p.router is not None
    assert p.enabled is True


def test_voice_param():
    assert voice_param("alex") == "FunAudioLLM/CosyVoice2-0.5B:alex"


def test_build_speech_api_url():
    assert (
        build_speech_api_url("https://api.siliconflow.cn/v1")
        == "https://api.siliconflow.cn/v1/audio/speech"
    )
    assert (
        build_speech_api_url("https://api.siliconflow.cn")
        == "https://api.siliconflow.cn/v1/audio/speech"
    )
    assert (
        build_speech_api_url("https://api.siliconflow.cn/v1/chat/completions")
        == "https://api.siliconflow.cn/v1/audio/speech"
    )


def test_build_input_text_with_emotion():
    out = build_input_text(text="你好", emotion="happy")
    assert "<|endofprompt|>" in out
    assert out.endswith("你好")


def test_build_input_text_rejects_empty():
    from app.core.exceptions import AppError

    with pytest.raises(AppError):
        build_input_text(text="  ")


def test_resolve_tts_settings_empty(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.siliconflow_tts_client.get_tts_credentials",
        lambda db: ("", "", ""),
    )
    assert resolve_tts_settings() == ("", "", "FunAudioLLM/CosyVoice2-0.5B")
    assert is_configured() is False


def test_tts_fallback_skips_deepseek_uses_embedding():
    from app.services.model_settings_service import get_tts_credentials

    merged = {
        "tts_base_url": "",
        "tts_api_key": "",
        "tts_model": "",
        "llm_base_url": "https://api.deepseek.com/v1",
        "llm_api_key": "sk-deepseek",
        "llm_model": "deepseek-chat",
        "embedding_base_url": "https://api.siliconflow.cn/v1",
        "embedding_api_key": "sk-sf",
        "embedding_model": "BAAI/bge-m3",
    }

    def fake_merge(*_args, **_kwargs):
        return merged

    import app.services.model_settings_service as svc

    orig = svc._merge_effective
    svc._merge_effective = fake_merge
    try:
        base, key, model = get_tts_credentials(None)
    finally:
        svc._merge_effective = orig

    assert base == "https://api.siliconflow.cn/v1"
    assert key == "sk-sf"
    assert model == "FunAudioLLM/CosyVoice2-0.5B"


def test_get_model_settings_tts_uses_effective_credentials(monkeypatch):
    from app.services import model_settings_service as svc

    monkeypatch.setattr(
        svc,
        "_merge_effective",
        lambda *a, **k: {
            "tts_base_url": "",
            "tts_api_key": "",
            "tts_model": "",
            "llm_base_url": "https://api.deepseek.com/v1",
            "llm_api_key": "sk-ds",
            "llm_model": "deepseek-chat",
            "embedding_base_url": "https://api.siliconflow.cn/v1",
            "embedding_api_key": "sk-sf",
            "embedding_model": "BAAI/bge-m3",
            "rerank_base_url": "",
            "rerank_api_key": "",
            "rerank_model": "",
            "ragflow_api_url": "",
            "ragflow_api_key": "",
            "ragflow_mysql_password": "",
            "ragflow_mysql_port": "3306",
        },
    )
    monkeypatch.setattr(
        svc,
        "get_tts_credentials",
        lambda db: ("https://api.siliconflow.cn/v1", "sk-sf", "FunAudioLLM/CosyVoice2-0.5B"),
    )
    monkeypatch.setattr(
        svc,
        "get_platform_api_base_url",
        lambda db: "http://localhost/ai",
    )
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: type("S", (), {"app_name": "测试", "knowflow_enabled": False})(),
    )

    out = svc.get_model_settings(None)
    assert out.tts.base_url == "https://api.siliconflow.cn/v1"
    assert out.tts.model_name == "FunAudioLLM/CosyVoice2-0.5B"
    assert out.tts.api_key_configured is True


def test_synthesize_speech_success(monkeypatch):
    import asyncio

    from app.integrations import siliconflow_tts_client as client

    monkeypatch.setattr(
        client,
        "resolve_tts_settings",
        lambda db: ("https://api.siliconflow.cn/v1", "sk-test", "FunAudioLLM/CosyVoice2-0.5B"),
    )

    class FakeResponse:
        status_code = 200
        content = b"fake-audio"
        text = ""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            assert url == "https://api.siliconflow.cn/v1/audio/speech"
            assert json["model"] == "FunAudioLLM/CosyVoice2-0.5B"
            assert json["voice"] == "FunAudioLLM/CosyVoice2-0.5B:claire"
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    audio, media = asyncio.run(
        client.synthesize_speech(
            db=None,
            text="测试",
            voice_id="claire",
            response_format="mp3",
        )
    )
    assert audio == b"fake-audio"
    assert media == "audio/mpeg"
