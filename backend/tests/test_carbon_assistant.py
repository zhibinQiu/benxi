"""双碳助手功能注册与服务冒烟测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.services import carbon_assistant_service as svc


def test_carbon_assistant_plugin():
    ensure_plugins_loaded()
    p = get_plugin("carbon_assistant")
    assert p is not None
    assert p.route == "/system/carbon-assistant"
    assert p.permission_code == "feature.carbon_assistant"
    assert p.router is not None


def test_report_title():
    class _R:
        subject = "全国碳市场"
        report_type = "market_brief"

    assert "碳交易简报" in svc.report_title(_R())


def test_trading_snapshot_uses_carbon_service():
    async def _run():
        fake = {
            "ok": True,
            "summary_md": "mock",
            "sources": [],
            "failed_urls": [],
            "queried_at": "t",
            "query_type": "price",
            "keyword": "CEA",
            "error": None,
        }
        with (
            patch(
                "app.services.carbon_service.fetch_carbon_price",
                new=AsyncMock(return_value=fake),
            ),
            patch(
                "app.services.carbon_service.fetch_carbon_data",
                new=AsyncMock(return_value=fake),
            ),
            patch(
                "app.services.carbon_service.fetch_carbon_policy",
                new=AsyncMock(return_value=fake),
            ),
        ):
            data = await svc.trading_snapshot(keyword="CEA")
            assert data["keyword"] == "CEA"
            assert data["price"]["summary_md"] == "mock"
            assert data["ccer"]["summary_md"] == "mock"
            assert data["policy"]["summary_md"] == "mock"

    asyncio.run(_run())
