"""控排企业履约策略域模型。

数量类字段（排放、配额、持仓、成交量、单笔限额等）统一为万吨；
单价/均价类字段仍为元/吨；金额类为元。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SETTINGS_SINGLETON_ID = 1


class PlatformCarbonStrategySettings(Base):
    __tablename__ = "platform_carbon_strategy_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SETTINGS_SINGLETON_ID)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CarbonEnterprise(Base):
    __tablename__ = "carbon_enterprises"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    uscc: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(32), nullable=False)
    market_start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    compliance_cycle: Mapped[str] = mapped_column(String(64), nullable=False, default="annual")
    risk_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="balanced")
    annual_budget_cap: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    single_trade_limit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    enterprise_attrs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CarbonEmissionYear(Base):
    __tablename__ = "carbon_emission_years"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "year", name="uq_carbon_emission_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    scope1_combustion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope1_process: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope2_power: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    purchased_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    monthly_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    historical_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    ccer_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonEmissionForecast(Base):
    __tablename__ = "carbon_emission_forecasts"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "year", name="uq_carbon_emission_forecast"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    capacity_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    abatement_projects: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    production_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonCeaHolding(Base):
    __tablename__ = "carbon_cea_holdings"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "vintage_year", name="uq_carbon_cea_holding"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    vintage_year: Mapped[int] = mapped_column(Integer, nullable=False)
    free_quota: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 往年结转至本年度可用的配额（万吨）；当年可用 = free_quota + carry_forward_qty
    carry_forward_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 当前净卖出（万吨）= 累计卖出 − 买入；用于最大可结转测算
    net_sell_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_free_quota: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sellable_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonCeaTrade(Base):
    __tablename__ = "carbon_cea_trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    traded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")


class CarbonCcerHolding(Base):
    __tablename__ = "carbon_ccer_holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    project_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    issue_year: Mapped[int] = mapped_column(Integer, nullable=False)
    expire_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eligible_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    linked_green_cert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonCcerTrade(Base):
    __tablename__ = "carbon_ccer_trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    traded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")


class CarbonGreenPower(Base):
    __tablename__ = "carbon_green_power"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "year", name="uq_carbon_green_power"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    market_green_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    self_gen_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    premium_per_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contract_ref: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonGreenCert(Base):
    __tablename__ = "carbon_green_certs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ren_weight_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonMarketCeaMonthly(Base):
    __tablename__ = "carbon_market_cea_monthly"
    __table_args__ = (
        UniqueConstraint("year_month", name="uq_carbon_market_cea_ym"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_tag: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonMarketCcerMonthly(Base):
    __tablename__ = "carbon_market_ccer_monthly"
    __table_args__ = (
        UniqueConstraint("year_month", "project_type", name="uq_carbon_market_ccer_ym_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    project_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonMarketEnergyMonthly(Base):
    __tablename__ = "carbon_market_energy_monthly"
    __table_args__ = (
        UniqueConstraint(
            "year_month", "region", name="uq_carbon_market_energy_ym_region"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="national")
    green_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    grec_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    coal_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonStrategyRun(Base):
    __tablename__ = "carbon_strategy_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    compliance_year: Mapped[int] = mapped_column(Integer, nullable=False)
    accounting_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    market_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    plans: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarbonAlert(Base):
    __tablename__ = "carbon_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carbon_enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
