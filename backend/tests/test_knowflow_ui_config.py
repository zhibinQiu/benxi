"""KnowFlow UI 配置：浏览器基址与静态资源前缀一致。"""

from __future__ import annotations

from app.config import Settings


def test_asset_prefix_derived_from_public_url():
    s = Settings(
        knowflow_ui_public_url="http://127.0.0.1:18000/api/v1/embed-proxy/knowflow",
        knowflow_ui_proxy_prefix="",
    )
    assert s.knowflow_ui_asset_prefix == "/api/v1/embed-proxy/knowflow"
    assert (
        s.knowflow_ui_browser_base
        == "http://127.0.0.1:18000/api/v1/embed-proxy/knowflow"
    )


def test_asset_prefix_public_url_wins_over_default_proxy_prefix():
    s = Settings(
        knowflow_ui_public_url="http://127.0.0.1:18000/api/v1/embed-proxy/knowflow",
        knowflow_ui_proxy_prefix="/ragflow-ui",
    )
    assert s.knowflow_ui_asset_prefix == "/api/v1/embed-proxy/knowflow"


def test_asset_prefix_matches_when_public_and_proxy_aligned():
    s = Settings(
        knowflow_ui_public_url="http://127.0.0.1:40005/ragflow-ui",
        knowflow_ui_proxy_prefix="/ragflow-ui",
    )
    assert s.knowflow_ui_asset_prefix == "/ragflow-ui"


def test_asset_prefix_empty_when_public_url_has_no_path():
    s = Settings(
        knowflow_ui_public_url="http://127.0.0.1:18000",
        knowflow_ui_proxy_prefix="",
    )
    assert s.knowflow_ui_asset_prefix == ""
    assert s.knowflow_ui_browser_base == "http://127.0.0.1:18000"


def test_asset_prefix_defaults_empty_without_public_or_proxy():
    s = Settings(knowflow_ui_public_url="", knowflow_ui_proxy_prefix="")
    assert s.knowflow_ui_asset_prefix == ""
