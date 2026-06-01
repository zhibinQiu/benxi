"""CCER 日行情解析。"""

from __future__ import annotations

from app.services.carbon_market_ccer_service import (
    ccer_rows_to_history_points,
    parse_ccer_daily_text,
    parse_ccer_article,
)

TRADE_TEXT = (
    "2026年5月25日，核证自愿减排量成交量250吨，成交额21,450.00元，成交均价85.80元/吨。"
    "截至2026年5月25日，全国温室气体自愿减排交易市场累计成交量12,658,522吨。"
)

NO_TRADE_TEXT = "2026年5月26日，核证自愿减排量无成交。"

SAMPLE_HTML = f'<div id="zoom" class="cont"><p>{TRADE_TEXT}</p></div>'


def test_parse_ccer_trade_day():
    row = parse_ccer_daily_text(TRADE_TEXT, "2026-05-25")
    assert row is not None
    assert row["traded"] is True
    assert row["volume"] == 250.0
    assert row["close"] == 85.80
    assert row["amount_cny"] == 21450.0


def test_parse_ccer_no_trade_day():
    row = parse_ccer_daily_text(NO_TRADE_TEXT, "2026-05-26")
    assert row is not None
    assert row["traded"] is False
    assert row["volume"] == 0.0
    assert row["close"] is None


def test_parse_ccer_article_html():
    row = parse_ccer_article(SAMPLE_HTML, "2026-05-25")
    assert row is not None
    assert row["close"] == 85.80


def test_get_history_ccer_from_db():
    from datetime import date, timedelta

    from app.database import SessionLocal
    from app.services.carbon_market_ccer_service import upsert_ccer_quote
    from app.services.carbon_market_history_service import get_history_series

    db = SessionLocal()
    try:
        d1 = date.today() - timedelta(days=2)
        d2 = date.today() - timedelta(days=1)
        upsert_ccer_quote(
            db,
            {
                "trade_date": d1.isoformat(),
                "traded": True,
                "close": 85.8,
                "volume": 250.0,
            },
        )
        upsert_ccer_quote(
            db,
            {
                "trade_date": d2.isoformat(),
                "traded": False,
                "close": None,
                "volume": 0.0,
            },
        )
        db.commit()
    finally:
        db.close()

    series = get_history_series("CCER", days=30)
    assert series.source == "ccer.com.cn"
    assert len(series.points) >= 2
    assert series.points[-1].close_cny == 85.8


def test_ccer_history_points_carry_forward():
    from datetime import date, timedelta

    d1 = (date.today() - timedelta(days=2)).isoformat()
    d2 = (date.today() - timedelta(days=1)).isoformat()
    data = {
        d1: {
            "trade_date": d1,
            "traded": True,
            "close": 85.8,
            "volume": 250.0,
        },
        d2: {
            "trade_date": d2,
            "traded": False,
            "close": None,
            "volume": 0.0,
        },
    }
    pts = ccer_rows_to_history_points(data, days=5)
    assert len(pts) >= 3
    by_date = {p["trade_date"]: p for p in pts}
    assert by_date[d2]["close"] == 85.8
    assert by_date[d2]["volume"] == 0.0
