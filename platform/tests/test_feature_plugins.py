"""Feature plugin registry tests."""

from __future__ import annotations

from app.features.registry import all_plugins, ensure_plugins_loaded, get_plugin


def test_builtin_plugins_registered():
    ensure_plugins_loaded()
    plugins = all_plugins()
    ids = {p.id for p in plugins}
    assert "pdf_translate" in ids
    assert "speech_to_text" in ids
    assert "ocr" in ids
    assert "doc_compare" in ids
    assert "ai_tools" in ids
    assert "smart_data_query" in ids
    assert "carbon_qa" in ids
    assert "smart_forecast" in ids
    assert "carbon_platform" in ids
    assert "carbon_ai_v1" in ids
    assert "ai_digital_robot" in ids
    assert "emission_reduction_strategy" in ids
    assert "carbon_reduction_strategy" not in ids


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


def test_compare_plugin_has_router():
    p = get_plugin("doc_compare")
    assert p is not None
    assert p.enabled is True
    assert p.category == "document"
    assert p.route == "/system/compare"
    assert p.router is not None


def test_ocr_plugin_ui_only():
    p = get_plugin("ocr")
    assert p is not None
    assert p.permission_code == "feature.ocr"
    assert p.category == "tools"
    assert p.router is None
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
    assert p.category == "carbon"
    assert p.enabled is True
    assert p.route == "/system/smart-data-query"
    assert p.router is not None


def test_smart_forecast_plugin():
    p = get_plugin("smart_forecast")
    assert p is not None
    assert p.title == "智能预测"
    assert p.category == "carbon"
    assert p.enabled is True
    assert p.route == "/system/smart-forecast"


def test_carbon_platform_v3_in_carbon_category():
    p = get_plugin("carbon_platform")
    assert p is not None
    assert p.title == "智碳平台V3"
    assert p.category == "carbon"
    assert p.external_url
    assert "carbon3.hy.05351757.xyz" in p.external_url
    assert p.tag == "外链"


def test_carbon_qa_plugin():
    p = get_plugin("carbon_qa")
    assert p is not None
    assert p.enabled is True
    assert p.route == "/system/carbon-qa"


def test_carbon_ai_v1_external_link():
    p = get_plugin("carbon_ai_v1")
    assert p is not None
    assert p.title == "智碳 AI平台v1"
    assert p.enabled is True
    assert p.route is None
    assert p.external_url
    assert "/ai" in p.external_url
    assert p.category == "carbon"
    assert p.tag == "外链"


def test_ai_digital_robot_stub():
    p = get_plugin("ai_digital_robot")
    assert p is not None
    assert p.title == "AI数字机器人"
    assert p.category == "carbon"
    assert p.enabled is False
    assert p.tag == "待集成"


def test_emission_reduction_strategy_stub():
    p = get_plugin("emission_reduction_strategy")
    assert p is not None
    assert p.title == "智慧减排"
    assert p.category == "carbon"
    assert p.enabled is False
    assert p.tag == "待集成"
