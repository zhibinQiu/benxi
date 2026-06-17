"""辅助写作 — 预设与权限挂载。"""

from __future__ import annotations

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.services.assist_writing_service import PRESET_PROMPTS, list_presets


def test_assist_writing_plugin_registered():
    ensure_plugins_loaded()
    plugin = get_plugin("assist_writing")
    assert plugin is not None
    assert plugin.route == "/system/assist-writing"
    assert plugin.permission_code == "feature.assist_writing"
    assert plugin.category == "tools"


def test_list_presets_covers_all_keys():
    ids = {p["id"] for p in list_presets()}
    assert ids == set(PRESET_PROMPTS.keys())
    for p in list_presets():
        assert p["label"]
        assert "description" in p
