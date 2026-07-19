"""双碳助手 API — 碳交易看板 / 碳报告 / 减碳策略。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.carbon_report import CarbonReport
from app.models.org import User
from app.schemas.carbon_assistant import CarbonReportOut, CarbonReportSubmit
from app.schemas.common import ApiResponse
from app.services import carbon_assistant_service as svc
from app.services import carbon_service as carbon_svc

router = APIRouter(
    prefix="/carbon-assistant",
    tags=["carbon-assistant"],
    dependencies=[Depends(require_feature("carbon_assistant"))],
)

public_router = APIRouter(prefix="/share/carbon", tags=["carbon-share"])


def _render_completed_report(db: Session, r: CarbonReport) -> HTMLResponse:
    from app.services.finance_report_render import render_report_html

    try:
        r.view_count = int(r.view_count or 0) + 1
        db.commit()
        db.refresh(r)
    except Exception:
        db.rollback()

    html = render_report_html(
        r.content or "",
        title=svc.report_title(r),
        created_at=r.created_at,
        completed_at=r.completed_at,
        view_count=int(r.view_count or 0),
    )
    return HTMLResponse(content=html)


# ── 碳交易（复用 carbon_service）────────────────────────────


@router.get("/trading/snapshot", response_model=ApiResponse)
async def trading_snapshot(
    _: Annotated[User, Depends(get_current_user)],
    keyword: str = Query("", description="关键词，默认全国碳市场"),
) -> ApiResponse:
    data = await svc.trading_snapshot(keyword=keyword)
    return ApiResponse(data=data)


@router.get("/trading/price", response_model=ApiResponse)
async def trading_price(
    _: Annotated[User, Depends(get_current_user)],
    keyword: str = Query(""),
    url: str = Query(""),
) -> ApiResponse:
    data = await carbon_svc.fetch_carbon_price(keyword=keyword, url=url)
    return ApiResponse(data=data)


@router.get("/trading/policy", response_model=ApiResponse)
async def trading_policy(
    _: Annotated[User, Depends(get_current_user)],
    keyword: str = Query(""),
    url: str = Query(""),
) -> ApiResponse:
    data = await carbon_svc.fetch_carbon_policy(keyword=keyword, url=url)
    return ApiResponse(data=data)


@router.get("/trading/data", response_model=ApiResponse)
async def trading_data(
    _: Annotated[User, Depends(get_current_user)],
    topic: str = Query(..., description="emission|ccer|international|local"),
    keyword: str = Query(""),
    url: str = Query(""),
) -> ApiResponse:
    data = await carbon_svc.fetch_carbon_data(topic, keyword=keyword, url=url)
    return ApiResponse(data=data)


# ── 报告 / 策略 ─────────────────────────────────────────────


@router.post("/report", response_model=ApiResponse)
async def submit_report(
    body: CarbonReportSubmit,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    report = svc.create_report(
        db,
        user.id,
        subject=body.subject,
        report_type=body.report_type,
        industry=body.industry,
        region=body.region,
        target_year=body.target_year,
        ai_context=body.ai_context,
    )
    await svc.submit_report_task(report)
    return ApiResponse(data=CarbonReportOut.model_validate(report).model_dump(mode="json"))


@router.get("/reports", response_model=ApiResponse)
async def list_reports(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    report_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    rows = svc.get_user_reports(
        db,
        user.id,
        report_type=report_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(
        data=[CarbonReportOut.model_validate(r).model_dump(mode="json") for r in rows]
    )


@router.get("/report/{report_id}", response_model=ApiResponse)
async def get_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    report = svc.get_report(db, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ApiResponse(data=CarbonReportOut.model_validate(report).model_dump(mode="json"))


@router.post("/report/{report_id}/cancel", response_model=ApiResponse)
async def cancel_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        report = svc.cancel_report_task(db, user.id, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=CarbonReportOut.model_validate(report).model_dump(mode="json"))


@router.delete("/report/{report_id}", response_model=ApiResponse)
async def delete_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    try:
        svc.delete_report(db, user.id, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data={"ok": True})


@router.get("/report/{report_id}/view")
async def view_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    report = svc.get_report(db, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.status != "completed" or not report.content:
        raise HTTPException(status_code=400, detail="报告尚未完成")
    token = report.share_token or ""
    if not token:
        raise HTTPException(status_code=400, detail="分享令牌缺失")
    return RedirectResponse(url=f"/api/v1/share/carbon/{token}", status_code=302)


@router.get("/report/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    report = svc.get_report(db, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.status != "completed" or not report.content:
        raise HTTPException(status_code=400, detail="报告尚未完成")
    filename = f"{report.subject}_{report.report_type}.md".replace("/", "_")
    return PlainTextResponse(
        content=report.content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@public_router.get("/{share_token}")
async def public_share(
    share_token: str,
    db: Annotated[Session, Depends(get_db)],
):
    report = svc.get_report_by_share_token(db, share_token)
    if not report or report.status != "completed" or not report.content:
        raise HTTPException(status_code=404, detail="分享不存在或已失效")
    return _render_completed_report(db, report)
