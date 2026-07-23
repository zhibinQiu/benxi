"""控排企业履约策略 API schemas。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnterpriseCreate(BaseModel):
    # 名称可选：策略不依赖企业名，未填时由服务端按行业生成占位名
    name: str = ""
    uscc: str = ""
    industry: str
    market_start_year: int
    compliance_cycle: str = "annual"
    risk_profile: str = "balanced"
    annual_budget_cap: float = 0
    single_trade_limit: float = 0
    enterprise_attrs: dict[str, Any] = Field(default_factory=dict)


class EnterpriseUpdate(BaseModel):
    name: str | None = None
    uscc: str | None = None
    industry: str | None = None
    market_start_year: int | None = None
    compliance_cycle: str | None = None
    risk_profile: str | None = None
    annual_budget_cap: float | None = None
    single_trade_limit: float | None = None
    enterprise_attrs: dict[str, Any] | None = None


class EmissionYearIn(BaseModel):
    year: int
    verified_total: float | None = None
    scope1_combustion: float = 0
    scope1_process: float = 0
    scope2_power: float = 0
    purchased_mwh: float = 0
    monthly_detail: dict[str, Any] = Field(default_factory=dict)
    historical_gap: float | None = None
    ccer_used: float = 0


class ForecastIn(BaseModel):
    year: int
    forecast_total: float = 0
    capacity_plan: str = ""
    abatement_projects: list[Any] = Field(default_factory=list)
    production_plan: str = ""


class CeaHoldingIn(BaseModel):
    vintage_year: int
    free_quota: float = 0
    carry_forward_qty: float = 0
    net_sell_qty: float = 0
    avg_cost: float = 0
    estimated_free_quota: float = 0
    sellable_cap: float | None = None


class TradeIn(BaseModel):
    side: str
    qty: float
    price: float = 0
    note: str = ""


class CcerHoldingIn(BaseModel):
    id: str | None = None
    project_type: str = ""
    issue_year: int
    expire_at: str | None = None
    qty: float = 0
    cost: float = 0
    eligible_qty: float | None = None
    linked_green_cert: bool = False


class GreenPowerIn(BaseModel):
    year: int
    market_green_mwh: float = 0
    self_gen_mwh: float = 0
    premium_per_mwh: float = 0
    contract_ref: str = ""


class GreenCertIn(BaseModel):
    id: str | None = None
    year: int
    qty: float = 0
    unit_price: float = 0
    retired: bool = False
    ren_weight_target: float | None = None


class MarketCeaIn(BaseModel):
    year_month: str
    avg_price: float
    high: float | None = None
    low: float | None = None
    period_tag: str = ""


class MarketCcerIn(BaseModel):
    year_month: str
    project_type: str = "general"
    avg_price: float


class MarketEnergyIn(BaseModel):
    year_month: str
    region: str = "national"
    green_premium: float | None = None
    grec_price: float | None = None
    coal_price: float | None = None


class StrategyRunIn(BaseModel):
    compliance_year: int


class SettingsUpdate(BaseModel):
    payload: dict[str, Any]
