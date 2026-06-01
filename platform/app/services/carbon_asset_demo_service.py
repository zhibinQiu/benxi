"""碳资产管理与交易 — 内存 demo（按用户隔离）。"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.schemas.carbon_asset import (
    AssetCode,
    CarbonAssetOverview,
    CarbonHolding,
    CarbonMarketSnapshot,
    CarbonTradeCreate,
    CarbonTradeCreateResult,
    CarbonTradeRecord,
    TradeSide,
)
from app.services.carbon_market_live_service import get_live_price, get_market_snapshot

_ASSET_NAMES: dict[AssetCode, str] = {
    "CEA": "全国碳排放配额（CEA）",
    "CCER": "国家核证自愿减排量（CCER）",
}

_store_lock = Lock()
_user_state: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_holdings() -> dict[AssetCode, dict[str, float]]:
    return {
        "CEA": {"qty": 12_500.0, "avail": 10_200.0, "cost": 68.2},
        "CCER": {"qty": 3_200.0, "avail": 3_200.0, "cost": 52.5},
    }


def _ensure_user(user_id: str) -> dict[str, Any]:
    with _store_lock:
        if user_id not in _user_state:
            _user_state[user_id] = {
                "holdings": _default_holdings(),
                "trades": [],
            }
        else:
            defaults = _default_holdings()
            cur = _user_state[user_id]["holdings"]
            _user_state[user_id]["holdings"] = {
                k: cur[k] if k in cur else defaults[k] for k in defaults
            }
        return _user_state[user_id]


def get_market() -> CarbonMarketSnapshot:
    snap = get_market_snapshot()
    return CarbonMarketSnapshot(
        quotes=snap.quotes,
        live_count=snap.live_count,
        fetched_at=snap.fetched_at,
        hint=snap.hint,
    )


def _price_for(asset_code: AssetCode) -> float:
    return get_live_price(asset_code)


def get_overview(user_id: str) -> CarbonAssetOverview:
    state = _ensure_user(user_id)
    holdings = state["holdings"]
    quotes = {q.asset_code: q.last_price_cny for q in get_market_snapshot().quotes}
    total_qty = sum(h["qty"] for h in holdings.values())
    avail = sum(h["avail"] for h in holdings.values())
    frozen = max(0.0, total_qty - avail)
    market_value = sum(holdings[c]["qty"] * quotes[c] for c in holdings)
    trades: list[CarbonTradeRecord] = state["trades"]
    ytd_vol = sum(t.quantity_tco2 for t in trades)
    return CarbonAssetOverview(
        total_market_value=round(market_value, 2),
        total_quota_tco2=round(total_qty, 2),
        available_quota_tco2=round(avail, 2),
        frozen_quota_tco2=round(frozen, 2),
        ytd_trade_count=len(trades),
        ytd_trade_volume_tco2=round(ytd_vol, 2),
        demo=True,
    )


def list_holdings(user_id: str) -> list[CarbonHolding]:
    state = _ensure_user(user_id)
    out: list[CarbonHolding] = []
    for code, h in state["holdings"].items():
        mp = _price_for(code)
        mv = h["qty"] * mp
        cost_basis = h["qty"] * h["cost"]
        pnl = mv - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0
        out.append(
            CarbonHolding(
                asset_code=code,
                asset_name=_ASSET_NAMES[code],
                quantity_tco2=round(h["qty"], 2),
                available_tco2=round(h["avail"], 2),
                avg_cost_cny=round(h["cost"], 2),
                market_price_cny=mp,
                market_value_cny=round(mv, 2),
                pnl_cny=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
            )
        )
    return out


def list_market() -> CarbonMarketSnapshot:
    return get_market()


def list_trades(user_id: str, *, limit: int = 50) -> list[CarbonTradeRecord]:
    state = _ensure_user(user_id)
    trades: list[CarbonTradeRecord] = state["trades"]
    return list(reversed(trades[-limit:]))


def create_trade(user_id: str, body: CarbonTradeCreate) -> CarbonTradeCreateResult:
    state = _ensure_user(user_id)
    holdings = state["holdings"]
    code = body.asset_code
    qty = round(body.quantity_tco2, 2)
    price = round(body.price_cny if body.price_cny is not None else _price_for(code), 2)
    amount = round(qty * price, 2)
    h = holdings[code]

    if body.side == "sell":
        if qty > h["avail"] + 1e-6:
            raise ValueError(f"可卖数量不足，当前可用 {h['avail']:.2f} tCO₂e")
        h["qty"] = round(h["qty"] - qty, 2)
        h["avail"] = round(h["avail"] - qty, 2)
        msg = f"卖出 {qty} tCO₂e {_ASSET_NAMES[code]}，成交价 ¥{price}/t"
    else:
        new_qty = h["qty"] + qty
        if new_qty > 1e-6:
            h["cost"] = round((h["qty"] * h["cost"] + qty * price) / new_qty, 2)
        else:
            h["cost"] = price
        h["qty"] = round(new_qty, 2)
        h["avail"] = round(h["avail"] + qty, 2)
        msg = f"买入 {qty} tCO₂e {_ASSET_NAMES[code]}，成交价 ¥{price}/t"

    trade = CarbonTradeRecord(
        id=str(uuid.uuid4()),
        side=body.side,
        asset_code=code,
        asset_name=_ASSET_NAMES[code],
        quantity_tco2=qty,
        price_cny=price,
        amount_cny=amount,
        status="filled",
        created_at=_now(),
    )
    state["trades"].append(trade)
    return CarbonTradeCreateResult(trade=trade, message=msg)


def reset_demo(user_id: str) -> None:
    with _store_lock:
        _user_state[user_id] = {
            "holdings": _default_holdings(),
            "trades": [],
        }
