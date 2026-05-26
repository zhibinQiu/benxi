from app.features.registry import get_plugin
from app.integrations.dify_chat_client import is_dify_configured


def test_smart_data_query_plugin():
    p = get_plugin("smart_data_query")
    assert p is not None
    assert p.title == "智能问数"
    assert p.route == "/system/smart-data-query"
    assert p.permission_code == "feature.smart_data_query"
    assert p.router is not None
    assert p.enabled is True


def test_dify_configured_flag():
    assert isinstance(is_dify_configured(), bool)
