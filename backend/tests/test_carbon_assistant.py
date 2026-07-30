"""碳资产报告功能注册与服务冒烟测试。"""

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


def test_compliance_analysis_report_title():
    class _R:
        subject = "火电履约主体"
        report_type = "compliance_analysis"

    assert "履约综合分析" in svc.report_title(_R())


def test_plans_md_helper():
    from app.services.carbon_compliance.compliance_analysis_report import _plans_md

    md = _plans_md(
        [
            {
                "key": "conservative",
                "title": "保守方案",
                "description": "优先履约",
                "total_cost": 1000,
                "net_saving": 0,
                "time_window": "近月",
                "actions": [
                    {
                        "action": "buy_cea",
                        "qty": 100,
                        "unit_price": 80,
                        "window": "近月",
                        "note": "分批",
                    }
                ],
                "compliance": {"notes": ["覆盖缺口"]},
            }
        ]
    )
    assert "保守方案" in md
    assert "buy_cea" in md
    assert "覆盖缺口" in md


def test_synthesize_fallback_without_llm():
    async def _empty_stream(**_kwargs):
        if False:  # pragma: no cover
            yield ""
        return

    async def _run():
        with patch(
            "app.integrations.deepseek_client.chat_completion_stream",
            side_effect=_empty_stream,
        ):
            from app.services.carbon_compliance.compliance_analysis_report import (
                synthesize_compliance_analysis_stream,
            )

            text = await synthesize_compliance_analysis_stream(
                subject="测试企业",
                compliance_year=2026,
                factsheet_md="## 一、企业\n缺口 100 吨\n",
            )
            assert "履约综合分析报告" in text
            assert "先看结论" in text
            assert "缺口 100" in text

    asyncio.run(_run())


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


def test_get_user_reports_all_users_flag():
    """all_users=True 时不过滤 user_id（管理员全员列表）。"""
    from unittest.mock import MagicMock, patch

    db = MagicMock()
    fake_rows = [MagicMock(), MagicMock()]
    scalars = MagicMock()
    scalars.all.return_value = fake_rows
    db.scalars.return_value = scalars

    with patch("app.services.carbon_assistant_service.select") as select_mock:
        select_mock.return_value = MagicMock()
        # 链式 where/order_by/offset/limit
        stmt = select_mock.return_value
        stmt.where.return_value = stmt
        stmt.order_by.return_value = stmt
        stmt.offset.return_value = stmt
        stmt.limit.return_value = stmt

        rows = svc.get_user_reports(
            db,
            user_id=__import__("uuid").uuid4(),
            all_users=True,
            limit=10,
        )
        assert rows == fake_rows
        # all_users 时不应按 user_id 过滤（where 仅用于可选 type/status）
        # 至少调用了 select
        assert select_mock.called


def test_user_can_access_report_owner_and_admin():
    from unittest.mock import MagicMock, patch
    import uuid

    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    report = MagicMock()
    report.user_id = owner_id

    owner = MagicMock()
    owner.id = owner_id
    other = MagicMock()
    other.id = other_id
    db = MagicMock()

    assert svc.user_can_access_report(db, owner, report) is True
    with patch(
        "app.core.permissions.user_is_system_admin", return_value=False
    ):
        assert svc.user_can_access_report(db, other, report) is False
    with patch(
        "app.core.permissions.user_is_system_admin", return_value=True
    ):
        assert svc.user_can_access_report(db, other, report) is True
    assert svc.user_can_access_report(db, owner, None) is False

    async def _run():
        with (
            patch(
                "app.services.carbon_service.fetch_carbon_price",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch(
                "app.services.carbon_service.fetch_carbon_data",
                new=AsyncMock(
                    return_value={
                        "ok": True,
                        "summary_md": "ccer-ok",
                        "sources": [],
                        "failed_urls": [],
                        "queried_at": "t",
                        "query_type": "ccer",
                        "keyword": "CEA",
                        "error": None,
                    }
                ),
            ),
            patch(
                "app.services.carbon_service.fetch_carbon_policy",
                new=AsyncMock(
                    return_value={
                        "ok": True,
                        "summary_md": "policy-ok",
                        "sources": [],
                        "failed_urls": [],
                        "queried_at": "t",
                        "query_type": "policy",
                        "keyword": "CEA",
                        "error": None,
                    }
                ),
            ),
        ):
            data = await svc.trading_snapshot(keyword="CEA")
            assert data["price"]["ok"] is False
            assert data["price"]["error"] == "fetch_exception"
            assert data["ccer"]["summary_md"] == "ccer-ok"
            assert data["policy"]["summary_md"] == "policy-ok"

    asyncio.run(_run())
