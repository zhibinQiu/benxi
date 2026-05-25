"""Embed proxy URL resolver tests."""

from __future__ import annotations

from app.services.embed_proxy import resolve_proxy_embed_url
from app.services.feature_embed_urls import (
    resolve_carbon_qa_embed_url,
    resolve_smart_data_query_embed_url,
    resolve_smart_forecast_embed_url,
)


def test_resolve_proxy_embed_url_with_prefix():
    url = resolve_proxy_embed_url(
        proxy_prefix="/design-system-ui",
        upstream_url="http://172.19.134.45:40001",
        path="/ai/smart-data-query",
    )
    assert url == "/design-system-ui/ai/smart-data-query"


def test_feature_embed_urls_path_mode_defaults():
    assert resolve_smart_data_query_embed_url() == "/ai/smart-data-query"
    assert resolve_carbon_qa_embed_url() == "/ai/retrieval"
    assert resolve_smart_forecast_embed_url() == "http://127.0.0.1:8501/"
