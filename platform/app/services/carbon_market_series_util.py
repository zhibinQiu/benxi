"""碳市场历史序列补全（缺失日沿用最近有效收盘价）。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models.carbon_market import CeaDailyQuote
from app.schemas.carbon_asset import CarbonHistoryPoint


def get_last_cea_quote_row() -> dict[str, Any] | None:
    """库中最近一条 CEA 日行情（实时抓取失败时回退）。"""
    db = SessionLocal()
    try:
        row = db.scalars(
            select(CeaDailyQuote).order_by(CeaDailyQuote.trade_date.desc()).limit(1)
        ).first()
        if not row:
            return None
        return {
            "trade_date": row.trade_date.isoformat(),
            "open": row.open_cny,
            "high": row.high_cny,
            "low": row.low_cny,
            "close": row.close_cny,
            "change_pct": row.change_pct,
            "volume": row.volume_tco2,
            "source": "cneeex",
        }
    finally:
        db.close()


def fill_history_continuous(
    points: list[CarbonHistoryPoint],
    *,
    days: int,
    end: date | None = None,
) -> list[CarbonHistoryPoint]:
    """自区间内首个有效交易日至 end，按自然日补全；无数据日沿用上一有效收盘价。"""
    if not points:
        return []
    end = end or date.today()
    start = end - timedelta(days=days)

    by_date = {p.trade_date: p for p in points}
    all_sorted = sorted(points, key=lambda p: p.trade_date)

    last: CarbonHistoryPoint | None = None
    for p in all_sorted:
        if p.trade_date < start.isoformat():
            last = p
        else:
            break

    out: list[CarbonHistoryPoint] = []
    d = start
    while d <= end:
        key = d.isoformat()
        if key in by_date:
            last = by_date[key]
            out.append(last)
        elif last is not None:
            close = last.close_cny
            out.append(
                CarbonHistoryPoint(
                    trade_date=key,
                    close_cny=close,
                    open_cny=last.open_cny if last.open_cny is not None else close,
                    high_cny=last.high_cny if last.high_cny is not None else close,
                    low_cny=last.low_cny if last.low_cny is not None else close,
                    change_pct=None,
                    volume_tco2=0.0,
                )
            )
        d += timedelta(days=1)
    return out


def ccer_sparse_history_points(
    data: dict[str, dict[str, Any]], *, days: int
) -> list[CarbonHistoryPoint]:
    """CCER 稀疏日行情：无成交日沿用上一笔有效收盘价。"""
    from app.services.carbon_market_ccer_service import _last_close_before

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    dates = sorted(d for d in data.keys() if d >= cutoff)
    points: list[CarbonHistoryPoint] = []
    last_close: float | None = None
    for d in dates:
        row = data[d]
        close = row.get("close")
        if close is not None:
            last_close = float(close)
        elif last_close is None:
            last_close = _last_close_before(data, d)
        if last_close is None:
            continue
        vol = float(row.get("volume") or 0)
        prev_close = points[-1].close_cny if points else None
        chg: float | None = None
        if prev_close and prev_close > 0 and row.get("traded"):
            chg = round((last_close - prev_close) / prev_close * 100, 2)
        close_r = round(last_close, 2)
        points.append(
            CarbonHistoryPoint(
                trade_date=d,
                close_cny=close_r,
                open_cny=close_r,
                high_cny=close_r,
                low_cny=close_r,
                change_pct=chg,
                volume_tco2=vol,
            )
        )
    return points
