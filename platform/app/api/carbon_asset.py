"""碳资产管理与交易 demo API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, require_feature
from app.models.org import User
from app.schemas.carbon_asset import (
    AssetCode,
    CarbonAssetOverview,
    CarbonHolding,
    CarbonHistorySeries,
    CarbonMarketSnapshot,
    CarbonTradeCreate,
    CarbonTradeCreateResult,
    CarbonTradeRecord,
)
from app.services.carbon_market_history_service import get_history_series
from app.services.carbon_market_live_service import get_market_snapshot
from app.schemas.common import ApiResponse
from app.services import carbon_asset_demo_service as svc

router = APIRouter(
    prefix="/carbon-assets",
    tags=["carbon-assets"],
    dependencies=[Depends(require_feature("carbon_asset_trading"))],
)


@router.get("/overview", response_model=ApiResponse[CarbonAssetOverview])
async def carbon_assets_overview(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CarbonAssetOverview]:
    return ApiResponse(data=svc.get_overview(str(user.id)))


@router.get("/holdings", response_model=ApiResponse[list[CarbonHolding]])
async def carbon_assets_holdings(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[CarbonHolding]]:
    return ApiResponse(data=svc.list_holdings(str(user.id)))


@router.get("/market", response_model=ApiResponse[CarbonMarketSnapshot])
async def carbon_assets_market(
    _: Annotated[User, Depends(get_current_user)],
    refresh: bool = Query(False, description="跳过缓存重新抓取行情"),
) -> ApiResponse[CarbonMarketSnapshot]:
    if refresh:
        snap = get_market_snapshot(force_refresh=True)
        return ApiResponse(
            data=CarbonMarketSnapshot(
                quotes=snap.quotes,
                live_count=snap.live_count,
                fetched_at=snap.fetched_at,
                hint=snap.hint,
            )
        )
    return ApiResponse(data=svc.list_market())


@router.get("/market/{asset_code}/history", response_model=ApiResponse[CarbonHistorySeries])
async def carbon_assets_market_history(
    asset_code: AssetCode,
    _: Annotated[User, Depends(get_current_user)],
    days: int = Query(90, ge=7, le=365, description="回溯自然日范围"),
) -> ApiResponse[CarbonHistorySeries]:
    return ApiResponse(data=get_history_series(asset_code, days=days))


@router.get("/trades", response_model=ApiResponse[list[CarbonTradeRecord]])
async def carbon_assets_trades(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[CarbonTradeRecord]]:
    return ApiResponse(data=svc.list_trades(str(user.id)))


@router.post("/trades", response_model=ApiResponse[CarbonTradeCreateResult])
async def carbon_assets_create_trade(
    body: CarbonTradeCreate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CarbonTradeCreateResult]:
    try:
        result = svc.create_trade(str(user.id), body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(data=result)


@router.post("/demo/reset", response_model=ApiResponse[dict])
async def carbon_assets_reset_demo(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    svc.reset_demo(str(user.id))
    return ApiResponse(data={"ok": True})
