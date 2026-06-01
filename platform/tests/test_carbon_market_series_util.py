"""历史序列补全。"""

from __future__ import annotations

from datetime import date, timedelta

from app.schemas.carbon_asset import CarbonHistoryPoint
from app.services.carbon_market_series_util import fill_history_continuous


def test_fill_history_continuous_carries_forward():
    today = date.today()
    d0 = (today - timedelta(days=4)).isoformat()
    d2 = (today - timedelta(days=2)).isoformat()
    sparse = [
        CarbonHistoryPoint(
            trade_date=d0,
            close_cny=70.0,
            open_cny=69.0,
            high_cny=71.0,
            low_cny=68.0,
            change_pct=1.0,
            volume_tco2=1000.0,
        ),
        CarbonHistoryPoint(
            trade_date=d2,
            close_cny=72.0,
            open_cny=71.0,
            high_cny=73.0,
            low_cny=70.0,
            change_pct=2.0,
            volume_tco2=2000.0,
        ),
    ]
    filled = fill_history_continuous(sparse, days=5, end=today)
    dates = [p.trade_date for p in filled]
    assert len(dates) == 5
    gap = (today - timedelta(days=3)).isoformat()
    gap_pt = next(p for p in filled if p.trade_date == gap)
    assert gap_pt.close_cny == 70.0
    assert gap_pt.volume_tco2 == 0.0
    assert filled[-1].close_cny == 72.0
