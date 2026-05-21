"""Feature plugin registry tests."""

from __future__ import annotations

from app.features.registry import all_plugins, ensure_plugins_loaded, get_plugin


def test_builtin_plugins_registered():
    ensure_plugins_loaded()
    plugins = all_plugins()
    ids = {p.id for p in plugins}
    assert "pdf_translate" in ids
    assert "rag_qa" in ids


def test_translate_plugin_has_router_and_permission():
    p = get_plugin("pdf_translate")
    assert p is not None
    assert p.permission_code == "feature.translate"
    assert p.router is not None
    assert p.route == "/system/translate"
