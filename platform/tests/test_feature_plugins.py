"""Feature plugin registry tests."""

from __future__ import annotations

from app.features.registry import all_plugins, ensure_plugins_loaded, get_plugin


def test_builtin_plugins_registered():
    ensure_plugins_loaded()
    plugins = all_plugins()
    ids = {p.id for p in plugins}
    assert "pdf_translate" in ids
    assert "speech_to_text" in ids
    assert "text_to_speech" in ids
    assert "ocr" in ids
    assert "doc_compare" in ids
    assert "ai_tools" in ids
    assert "smart_data_query" in ids
    assert "carbon_qa" in ids
    assert "smart_forecast" in ids
    assert "ai_home" in ids
    assert "carbon_platform" in ids
    assert "carbon_ai_v1" in ids
    assert "emission_reduction_strategy" not in ids


def test_translate_plugin_has_router_and_permission():
    p = get_plugin("pdf_translate")
    assert p is not None
    assert p.permission_code == "feature.translate"
    assert p.category == "document"
    assert p.router is not None
    assert p.route == "/system/translate"


def test_speech_plugin_has_router_and_permission():
    p = get_plugin("speech_to_text")
    assert p is not None
    assert p.permission_code == "feature.speech_to_text"
    assert p.category == "tools"
    assert p.router is not None
    assert p.route == "/system/speech"


def test_text_to_speech_plugin_has_router_and_permission():
    p = get_plugin("text_to_speech")
    assert p is not None
    assert p.permission_code == "feature.text_to_speech"
    assert p.category == "tools"
    assert p.router is not None
    assert p.route == "/system/text-to-speech"


def test_compare_plugin_has_router():
    p = get_plugin("doc_compare")
    assert p is not None
    assert p.enabled is True
    assert p.category == "document"
    assert p.route == "/system/compare"
    assert p.router is not None


def test_ocr_plugin_has_router_and_permission():
    p = get_plugin("ocr")
    assert p is not None
    assert p.title == "文件内容提取"
    assert p.permission_code == "feature.ocr"
    assert p.category == "tools"
    assert p.router is not None
    assert p.route == "/system/ocr"
    assert p.enabled is True


def test_ai_tools_category():
    p = get_plugin("ai_tools")
    assert p is not None
    assert p.category == "tools"


def test_smart_data_query_plugin():
    p = get_plugin("smart_data_query")
    assert p is not None
    assert p.title == "智能问数"
    assert p.permission_code == "feature.smart_data_query"
    assert p.category == "ai"
    assert p.enabled is True
    assert p.route == "/system/smart-data-query"
    assert p.router is not None


def test_smart_forecast_plugin():
    p = get_plugin("smart_forecast")
    assert p is not None
    assert p.title == "智能预测"
    assert p.category == "ai"
    assert p.enabled is True
    assert p.route == "/system/smart-forecast"


def test_ai_home_plugin():
    p = get_plugin("ai_home")
    assert p is not None
    assert p.title == "本析智能"
    assert p.category == "tools"
    assert p.route == "/ai-home"

