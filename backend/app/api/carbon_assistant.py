"""碳资产报告 API — 履约策略工作台 / 市场摘要 / 资讯报告。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.carbon_compliance import router as compliance_router
from app.api.deps import get_current_user, require_feature
from app.core.permissions import user_is_system_admin
from app.database import get_db
from app.models.carbon_report import CarbonReport
from app.models.org import User
from app.schemas.carbon_assistant import CarbonReportOut, CarbonReportSubmit
from app.schemas.common import ApiResponse
from app.services import carbon_assistant_service as svc
from app.services import carbon_service as carbon_svc


def _report_out(db: Session, report: CarbonReport, *, with_owner: bool = False) -> dict:
    data = CarbonReportOut.model_validate(report).model_dump(mode="json")
    if with_owner:
        data["owner_name"] = svc.resolve_owner_name(db, report.user_id)
    return data

router = APIRouter(
    prefix="/carbon-assistant",
    tags=["carbon-assistant"],
    dependencies=[Depends(require_feature("carbon_assistant"))],
)
router.include_router(compliance_router)

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
    # strategy 类型已由履约综合分析替换
    if body.report_type == "strategy":
        raise HTTPException(
            status_code=400,
            detail="减碳策略报告已下线，请使用履约综合分析 compliance_analysis",
        )
    if body.report_type == "compliance_analysis":
        ctx = (body.ai_context or "").strip()
        if '"enterprise_id"' not in ctx and "'enterprise_id'" not in ctx:
            raise HTTPException(
                status_code=400,
                detail="履约综合分析需在 ai_context 中提供 enterprise_id",
            )
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
    is_admin = user_is_system_admin(db, user)
    rows = svc.get_user_reports(
        db,
        user.id,
        report_type=report_type,
        status=status,
        limit=limit,
        offset=offset,
        all_users=is_admin,
    )
    return ApiResponse(
        data=[_report_out(db, r, with_owner=is_admin) for r in rows]
    )


@router.get("/report/{report_id}", response_model=ApiResponse)
async def get_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    report = svc.get_report(db, report_id)
    if not svc.user_can_access_report(db, user, report):
        raise HTTPException(status_code=404, detail="报告不存在")
    assert report is not None
    is_admin = user_is_system_admin(db, user)
    return ApiResponse(data=_report_out(db, report, with_owner=is_admin))


@router.post("/report/{report_id}/cancel", response_model=ApiResponse)
async def cancel_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    is_admin = user_is_system_admin(db, user)
    try:
        report = svc.cancel_report_task(db, user.id, report_id, as_admin=is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=_report_out(db, report, with_owner=is_admin))


@router.delete("/report/{report_id}", response_model=ApiResponse)
async def delete_report(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    is_admin = user_is_system_admin(db, user)
    try:
        svc.delete_report(db, user.id, report_id, as_admin=is_admin)
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
    if not svc.user_can_access_report(db, user, report):
        raise HTTPException(status_code=404, detail="报告不存在")
    assert report is not None
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
    if not svc.user_can_access_report(db, user, report):
        raise HTTPException(status_code=404, detail="报告不存在")
    assert report is not None
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
