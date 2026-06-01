"""碳资产与交易 demo 数据结构。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetCode = Literal["CEA", "CCER"]
TradeSide = Literal["buy", "sell"]


class CarbonAssetOverview(BaseModel):
    total_market_value: float = Field(description="持仓市值（元）")
    total_quota_tco2: float = Field(description="碳资产总量（tCO₂e）")
    available_quota_tco2: float = Field(description="可交易余额（tCO₂e）")
    frozen_quota_tco2: float = Field(description="冻结/履约预留（tCO₂e）")
    ytd_trade_count: int
    ytd_trade_volume_tco2: float
    demo: bool = True


class CarbonHolding(BaseModel):
    asset_code: AssetCode
    asset_name: str
    quantity_tco2: float
    available_tco2: float
    avg_cost_cny: float
    market_price_cny: float
    market_value_cny: float
    pnl_cny: float
    pnl_pct: float


class CarbonMarketQuote(BaseModel):
    asset_code: AssetCode
    asset_name: str
    last_price_cny: float
    change_pct: float
    high_cny: float
    low_cny: float
    volume_tco2: float
    updated_at: datetime
    source: str = Field(
        default="demo",
        description="cneeex=上证环交所 | custom=自定义 JSON | estimated=估算 | demo=演示",
    )
    trade_date: str | None = Field(default=None, description="行情交易日 YYYY-MM-DD")
    live: bool = Field(default=False, description="是否为实时/官方抓取")


class CarbonMarketSnapshot(BaseModel):
    quotes: list[CarbonMarketQuote]
    live_count: int = 0
    fetched_at: datetime
    hint: str | None = None


class CarbonHistoryPoint(BaseModel):
    trade_date: str
    close_cny: float
    open_cny: float | None = None
    high_cny: float | None = None
    low_cny: float | None = None
    change_pct: float | None = None
    volume_tco2: float | None = None


class CarbonHistorySeries(BaseModel):
    asset_code: AssetCode
    asset_name: str
    source: str
    points: list[CarbonHistoryPoint]
    hint: str | None = None
    data_through: str | None = Field(
        default=None, description="库中最新交易日 YYYY-MM-DD"
    )
    last_synced_at: datetime | None = Field(
        default=None, description="最近一次写入数据库的时间"
    )


class CarbonTradeRecord(BaseModel):
    id: str
    side: TradeSide
    asset_code: AssetCode
    asset_name: str
    quantity_tco2: float
    price_cny: float
    amount_cny: float
    status: str
    created_at: datetime


class CarbonTradeCreate(BaseModel):
    side: TradeSide
    asset_code: AssetCode
    quantity_tco2: float = Field(gt=0, le=100_000)
    price_cny: float | None = Field(default=None, gt=0, description="限价；空则按市价")


class CarbonTradeCreateResult(BaseModel):
    trade: CarbonTradeRecord
    message: str
