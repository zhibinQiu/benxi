"""碳市场行情解析与接口。"""

from __future__ import annotations

from datetime import date, timedelta

from app.database import SessionLocal
from app.services.carbon_market_history_service import get_history_series, upsert_cea_quote
from app.services.carbon_market_live_service import (
    _parse_cea_article,
    fetch_cneeex_cea,
    get_market_snapshot,
)


SAMPLE_HTML = """
今日全国碳市场综合价格行情为: 开盘价72.82元/吨，最高价73.68元/吨，最低价72.82元/吨，收盘价73.01元/吨，收盘价较前一日下跌0.59%。
今日全国碳排放配额总成交量832,898吨，总成交额60,884,883.30元。
"""


def test_parse_cea_article():
    row = _parse_cea_article(SAMPLE_HTML, "2025-06-20")
    assert row is not None
    assert row["close"] == 73.01
    assert row["change_pct"] == -0.59
    assert row["volume"] == 832898.0


def test_market_snapshot_demo_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.services.carbon_market_live_service.fetch_cneeex_cea",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.services.carbon_market_live_service.fetch_ccer_latest",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.services.carbon_market_live_service.get_last_cea_quote_row",
        lambda: None,
    )
    snap = get_market_snapshot(force_refresh=True)
    assert len(snap.quotes) == 2
    assert snap.live_count == 0
    cea = next(q for q in snap.quotes if q.asset_code == "CEA")
    assert cea.source == "demo"


def _seed_cea_rows(count: int = 10) -> None:
    db = SessionLocal()
    try:
        today = date.today()
        for i in range(count):
            d = today - timedelta(days=count - i)
            upsert_cea_quote(
                db,
                d,
                {
                    "open": 70.0 + i * 0.1,
                    "high": 71.0 + i * 0.1,
                    "low": 69.0 + i * 0.1,
                    "close": 70.5 + i * 0.1,
                    "change_pct": 0.5,
                    "volume": 100_000.0,
                },
            )
        db.commit()
    finally:
        db.close()


def test_market_history_api_unavailable_when_feature_disabled(client, admin_token):
    _seed_cea_rows(12)
    r = client.get(
        "/api/v1/carbon-assets/market/CEA/history?days=30",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404


def test_get_history_series_no_network(monkeypatch):
    monkeypatch.setattr(
        "app.services.carbon_market_history_service.sync_cea_history_from_cneeex",
        lambda **_: 0,
    )
    _seed_cea_rows(15)
    series = get_history_series("CEA", days=30)
    assert series.points
    assert series.source == "cneeex"


def test_market_api_unavailable_when_feature_disabled(client, admin_token):
    r = client.get("/api/v1/carbon-assets/market", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404
