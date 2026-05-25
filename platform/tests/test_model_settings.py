"""系统模型配置（只读）。"""

from __future__ import annotations

from app.config import Settings
from app.services.model_settings_service import get_model_settings, mask_secret


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
    out = get_model_settings()
    assert out.editable is False
    assert out.llm.base_url == "https://api.deepseek.com/v1"
    assert out.llm.model_name == "deepseek-chat"
    assert out.llm.api_key_configured is True
    assert "sk-t" in out.llm.api_key_masked
