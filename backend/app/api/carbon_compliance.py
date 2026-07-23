"""控排企业履约策略 REST（挂载于 carbon-assistant 前缀下）。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.carbon_compliance import (
    CcerHoldingIn,
    CeaHoldingIn,
    EmissionYearIn,
    EnterpriseCreate,
    EnterpriseUpdate,
    ForecastIn,
    GreenCertIn,
    GreenPowerIn,
    MarketCcerIn,
    MarketCeaIn,
    MarketEnergyIn,
    SettingsUpdate,
    StrategyRunIn,
    TradeIn,
)
from app.schemas.common import ApiResponse
from app.services import carbon_compliance_service as ccs
from app.services.carbon_compliance.defaults import INDUSTRIES, INDUSTRY_LABELS, RISK_PROFILE_LABELS

router = APIRouter(tags=["carbon-compliance"])


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/meta", response_model=ApiResponse)
def compliance_meta(_: Annotated[User, Depends(get_current_user)]) -> ApiResponse:
    return ApiResponse(
        data={
            "industries": [
                {"value": k, "label": INDUSTRY_LABELS[k]} for k in INDUSTRIES
            ],
            "risk_profiles": [
                {"value": k, "label": RISK_PROFILE_LABELS[k]}
                for k in RISK_PROFILE_LABELS
            ],
        }
    )


@router.get("/settings", response_model=ApiResponse)
def get_settings(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    return ApiResponse(data=ccs.get_settings(db))


@router.put("/settings", response_model=ApiResponse)
def put_settings(
    body: SettingsUpdate,
    _: Annotated[User, Depends(require_permission("admin.user"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    return ApiResponse(data=ccs.update_settings(db, body.payload))


@router.get("/enterprises", response_model=ApiResponse)
def list_enterprises(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    rows = ccs.list_enterprises(db, user.id)
    return ApiResponse(data=[ccs.enterprise_to_dict(e) for e in rows])


@router.post("/enterprises", response_model=ApiResponse)
def create_enterprise(
    body: EnterpriseCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ent = ccs.create_enterprise(db, user.id, body.model_dump())
    except ValueError as exc:
        raise _err(exc) from exc
    return ApiResponse(data=ccs.enterprise_to_dict(ent))


@router.get("/enterprises/{enterprise_id}", response_model=ApiResponse)
def get_enterprise(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    ent = ccs.get_enterprise(db, user.id, enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="enterprise not found")
    return ApiResponse(data=ccs.enterprise_to_dict(ent))


@router.put("/enterprises/{enterprise_id}", response_model=ApiResponse)
def update_enterprise(
    enterprise_id: uuid.UUID,
    body: EnterpriseUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ent = ccs.update_enterprise(
            db, user.id, enterprise_id, body.model_dump(exclude_unset=True)
        )
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return ApiResponse(data=ccs.enterprise_to_dict(ent))


@router.delete("/enterprises/{enterprise_id}", response_model=ApiResponse)
def delete_enterprise(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ccs.delete_enterprise(db, user.id, enterprise_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"ok": True})


@router.get("/enterprises/{enterprise_id}/emissions", response_model=ApiResponse)
def list_emissions(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_emission_years(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year": r.year,
                "verified_total": r.verified_total,
                "scope1_combustion": r.scope1_combustion,
                "scope1_process": r.scope1_process,
                "scope2_power": r.scope2_power,
                "purchased_mwh": r.purchased_mwh,
                "monthly_detail": r.monthly_detail,
                "historical_gap": r.historical_gap,
                "ccer_used": r.ccer_used,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/emissions", response_model=ApiResponse)
def upsert_emission(
    enterprise_id: uuid.UUID,
    body: EmissionYearIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_emission_year(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id), "year": row.year})


@router.delete(
    "/enterprises/{enterprise_id}/emissions/{year}",
    response_model=ApiResponse,
)
def delete_emission(
    enterprise_id: uuid.UUID,
    year: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ccs.delete_emission_year(db, user.id, enterprise_id, year)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"ok": True, "year": year})


@router.get("/enterprises/{enterprise_id}/forecasts", response_model=ApiResponse)
def list_forecasts(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_forecasts(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year": r.year,
                "forecast_total": r.forecast_total,
                "capacity_plan": r.capacity_plan,
                "abatement_projects": r.abatement_projects,
                "production_plan": r.production_plan,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/forecasts", response_model=ApiResponse)
def upsert_forecast(
    enterprise_id: uuid.UUID,
    body: ForecastIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_forecast(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id), "year": row.year})


@router.get("/enterprises/{enterprise_id}/cea", response_model=ApiResponse)
def list_cea(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_cea_holdings(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "vintage_year": r.vintage_year,
                "free_quota": r.free_quota,
                "carry_forward_qty": r.carry_forward_qty,
                "net_sell_qty": r.net_sell_qty,
                "avg_cost": r.avg_cost,
                "estimated_free_quota": r.estimated_free_quota,
                "sellable_cap": r.sellable_cap,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/cea", response_model=ApiResponse)
def upsert_cea(
    enterprise_id: uuid.UUID,
    body: CeaHoldingIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_cea_holding(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id), "vintage_year": row.vintage_year})


@router.delete(
    "/enterprises/{enterprise_id}/cea/{vintage_year}",
    response_model=ApiResponse,
)
def delete_cea(
    enterprise_id: uuid.UUID,
    vintage_year: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ccs.delete_cea_holding(db, user.id, enterprise_id, vintage_year)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"ok": True, "vintage_year": vintage_year})


@router.post("/enterprises/{enterprise_id}/cea/trades", response_model=ApiResponse)
def add_cea_trade(
    enterprise_id: uuid.UUID,
    body: TradeIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.add_cea_trade(db, user.id, enterprise_id, body.model_dump())
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id)})


@router.get("/enterprises/{enterprise_id}/ccer", response_model=ApiResponse)
def list_ccer(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_ccer_holdings(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "project_type": r.project_type,
                "issue_year": r.issue_year,
                "expire_at": r.expire_at.isoformat() if r.expire_at else None,
                "qty": r.qty,
                "cost": r.cost,
                "eligible_qty": r.eligible_qty,
                "linked_green_cert": r.linked_green_cert,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/ccer", response_model=ApiResponse)
def upsert_ccer(
    enterprise_id: uuid.UUID,
    body: CcerHoldingIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_ccer_holding(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id)})


@router.delete(
    "/enterprises/{enterprise_id}/ccer/{holding_id}",
    response_model=ApiResponse,
)
def delete_ccer(
    enterprise_id: uuid.UUID,
    holding_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        ccs.delete_ccer_holding(db, user.id, enterprise_id, holding_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"ok": True, "id": str(holding_id)})


@router.post("/enterprises/{enterprise_id}/ccer/trades", response_model=ApiResponse)
def add_ccer_trade(
    enterprise_id: uuid.UUID,
    body: TradeIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.add_ccer_trade(db, user.id, enterprise_id, body.model_dump())
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id)})


@router.get("/enterprises/{enterprise_id}/green-power", response_model=ApiResponse)
def list_green_power(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_green_power(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year": r.year,
                "market_green_mwh": r.market_green_mwh,
                "self_gen_mwh": r.self_gen_mwh,
                "premium_per_mwh": r.premium_per_mwh,
                "contract_ref": r.contract_ref,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/green-power", response_model=ApiResponse)
def upsert_green_power(
    enterprise_id: uuid.UUID,
    body: GreenPowerIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_green_power(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id), "year": row.year})


@router.get("/enterprises/{enterprise_id}/green-certs", response_model=ApiResponse)
def list_green_certs(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_green_certs(db, enterprise_id)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year": r.year,
                "qty": r.qty,
                "unit_price": r.unit_price,
                "retired": r.retired,
                "ren_weight_target": r.ren_weight_target,
            }
            for r in rows
        ]
    )


@router.post("/enterprises/{enterprise_id}/green-certs", response_model=ApiResponse)
def upsert_green_cert(
    enterprise_id: uuid.UUID,
    body: GreenCertIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.upsert_green_cert(db, user.id, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data={"id": str(row.id)})


@router.get("/market/cea", response_model=ApiResponse)
def market_cea_list(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    rows = ccs.list_market_cea(db)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year_month": r.year_month,
                "avg_price": r.avg_price,
                "high": r.high,
                "low": r.low,
                "period_tag": r.period_tag,
            }
            for r in rows
        ]
    )


@router.post("/market/cea", response_model=ApiResponse)
def market_cea_upsert(
    body: MarketCeaIn,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    row = ccs.upsert_market_cea(db, body.model_dump())
    return ApiResponse(data={"id": str(row.id), "year_month": row.year_month})


@router.get("/market/ccer", response_model=ApiResponse)
def market_ccer_list(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    rows = ccs.list_market_ccer(db)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year_month": r.year_month,
                "project_type": r.project_type,
                "avg_price": r.avg_price,
            }
            for r in rows
        ]
    )


@router.post("/market/ccer", response_model=ApiResponse)
def market_ccer_upsert(
    body: MarketCcerIn,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    row = ccs.upsert_market_ccer(db, body.model_dump())
    return ApiResponse(data={"id": str(row.id)})


@router.get("/market/energy", response_model=ApiResponse)
def market_energy_list(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    rows = ccs.list_market_energy(db)
    return ApiResponse(
        data=[
            {
                "id": str(r.id),
                "year_month": r.year_month,
                "region": r.region,
                "green_premium": r.green_premium,
                "grec_price": r.grec_price,
                "coal_price": r.coal_price,
            }
            for r in rows
        ]
    )


@router.post("/market/energy", response_model=ApiResponse)
def market_energy_upsert(
    body: MarketEnergyIn,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    row = ccs.upsert_market_energy(db, body.model_dump())
    return ApiResponse(data={"id": str(row.id)})


@router.get("/market/cea/kline", response_model=ApiResponse)
async def market_cea_kline(
    _: Annotated[User, Depends(get_current_user)],
    kind: str = Query("daily", description="daily|forecast"),
    method: str = Query("rule", description="forecast only: rule|ets|sarimax|prophet"),
) -> ApiResponse:
    """CEA 图表序列：日线 / 至年底日度预测。"""
    from app.services.carbon_compliance.market_sync import fetch_cea_chart_series

    data = await fetch_cea_chart_series(kind, method=method)
    return ApiResponse(data=data)


@router.get("/market/ccer/kline", response_model=ApiResponse)
async def market_ccer_kline(
    _: Annotated[User, Depends(get_current_user)],
    kind: str = Query("daily", description="daily|forecast"),
    method: str = Query("rule", description="forecast only: rule|ets|sarimax|prophet"),
) -> ApiResponse:
    """CCER 折线图：日线 / 至年底日度预测。"""
    from app.services.carbon_compliance.market_sync import fetch_ccer_chart_series

    data = await fetch_ccer_chart_series(kind, method=method)
    return ApiResponse(data=data)


@router.get("/market/cea/forecast", response_model=ApiResponse)
async def market_cea_forecast(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """CEA 从当前到年底的日度预测（策略用）。"""
    from app.services.carbon_compliance.market_sync import fetch_cea_forecast_to_year_end

    data = await fetch_cea_forecast_to_year_end()
    return ApiResponse(data=data)


@router.post("/market/sync", response_model=ApiResponse)
async def market_sync(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    """从外站拉取 CEA/CCER 行情并写入月度库表。"""
    data = await ccs.sync_market_quotes(db)
    return ApiResponse(data=data)


@router.post("/enterprises/{enterprise_id}/strategy/run", response_model=ApiResponse)
def run_strategy(
    enterprise_id: uuid.UUID,
    body: StrategyRunIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        run = ccs.run_strategy(db, user.id, enterprise_id, body.compliance_year)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data=ccs.run_to_dict(run))


@router.get("/enterprises/{enterprise_id}/strategy/runs", response_model=ApiResponse)
def list_runs(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        rows = ccs.list_strategy_runs(db, user.id, enterprise_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data=[ccs.run_to_dict(r) for r in rows])


@router.get(
    "/enterprises/{enterprise_id}/strategy/runs/{run_id}/download",
)
def download_run(
    enterprise_id: uuid.UUID,
    run_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    from app.models.carbon_compliance import CarbonStrategyRun

    run = db.get(CarbonStrategyRun, run_id)
    if not run or run.enterprise_id != enterprise_id or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")
    if not run.report_md:
        raise HTTPException(status_code=400, detail="report empty")
    return Response(
        content=run.report_md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="strategy_{run.compliance_year}.md"'
        },
    )


@router.get("/alerts", response_model=ApiResponse)
def list_alerts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    enterprise_id: uuid.UUID | None = Query(None),
    unacked_only: bool = Query(False),
) -> ApiResponse:
    rows = ccs.list_alerts(
        db, user.id, enterprise_id=enterprise_id, unacked_only=unacked_only
    )
    return ApiResponse(data=[ccs.alert_to_dict(a) for a in rows])


@router.post("/alerts/{alert_id}/ack", response_model=ApiResponse)
def ack_alert(
    alert_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        row = ccs.ack_alert(db, user.id, alert_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return ApiResponse(data=ccs.alert_to_dict(row))


@router.get("/enterprises/{enterprise_id}/import/template")
def import_template(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not ccs.get_enterprise(db, user.id, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    try:
        content = ccs.build_import_template_bytes()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="carbon_import_template.xlsx"'},
    )


@router.post("/enterprises/{enterprise_id}/import", response_model=ApiResponse)
async def import_excel(
    enterprise_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> ApiResponse:
    raw = await file.read()
    try:
        counts = ccs.import_enterprise_excel(db, user.id, enterprise_id, raw)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise _err(exc) from exc
    return ApiResponse(data=counts)
