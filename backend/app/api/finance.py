"""理财助手 API — A股/基金/虚拟币行情接口。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.finance_report import FinanceReport
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.finance import (
    ReportImportLibraryOut,
    ReportOut,
    ReportSubmit,
    WatchlistItemCreate,
    WatchlistItemOut,
)
from app.services import finance_service as svc

router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(require_feature("finance_assistant"))],
)

# 公开分享路由：无登录、无功能权限依赖
public_router = APIRouter(prefix="/share/finance", tags=["finance-share"])


def _report_title(r: FinanceReport) -> str:
    title = f"「{r.stock_name} ({r.stock_code})」"
    if r.report_type == "roundtable":
        direction = "基本面" if r.research_direction == "fundamental" else "短线"
        kind = "辩论版" if r.roundtable_type == "debate" else "专业研究"
        title = f"「{r.stock_name} ({r.stock_code})」{direction}圆桌 · {kind}"
    elif r.report_type == "ai":
        title = f"「{r.stock_name} ({r.stock_code})」AI 深度解读"
    elif r.report_type == "vpa":
        title = f"「{r.stock_name} ({r.stock_code})」量价会诊"
    return title


def _render_completed_report(db: Session, r: FinanceReport) -> HTMLResponse:
    from app.services.finance_report_render import render_report_html

    try:
        r.view_count = int(r.view_count or 0) + 1
        db.commit()
        db.refresh(r)
    except Exception:
        db.rollback()

    html = render_report_html(
        r.content or "",
        title=_report_title(r),
        created_at=r.created_at,
        completed_at=r.completed_at,
        view_count=int(r.view_count or 0),
    )
    return HTMLResponse(content=html)


# ── A 股 ───────────────────────────────────────────────────────


@router.get("/market-indices", response_model=ApiResponse)
async def market_indices(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """主要市场指数行情（上证、深证、创业板等）。"""
    data = await svc.get_market_indices()
    return ApiResponse(data=data)


@router.get("/stock/search", response_model=ApiResponse)
async def stock_search(
    _: Annotated[User, Depends(get_current_user)],
    q: str = Query("", description="搜索关键词"),
) -> ApiResponse:
    """搜索 A 股（代码或名称）。"""
    data = await svc.search_stocks(q)
    return ApiResponse(data=data)


@router.get("/stock/quote", response_model=ApiResponse)
async def stock_quote(
    _: Annotated[User, Depends(get_current_user)],
    codes: str = Query("", description="股票代码，逗号分隔"),
) -> ApiResponse:
    """批量获取 A 股实时行情。"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    data = await svc.get_stock_quotes(code_list)
    return ApiResponse(data=data)


@router.get("/stock/kline", response_model=ApiResponse)
async def stock_kline(
    _: Annotated[User, Depends(get_current_user)],
    code: str = Query(..., description="股票代码"),
    ktype: str = Query("day", description="K 线类型: day/week/month"),
) -> ApiResponse:
    """获取 A 股 K 线数据。"""
    data = await svc.get_stock_kline(code, ktype)
    return ApiResponse(data=data)


# ── 基金 ───────────────────────────────────────────────────────


@router.get("/fund/search", response_model=ApiResponse)
async def fund_search(
    _: Annotated[User, Depends(get_current_user)],
    q: str = Query("", description="搜索关键词"),
) -> ApiResponse:
    """搜索基金（代码或名称）。"""
    data = await svc.search_funds(q)
    return ApiResponse(data=data)


@router.get("/fund/quote", response_model=ApiResponse)
async def fund_quote(
    _: Annotated[User, Depends(get_current_user)],
    code: str = Query(..., description="基金代码"),
) -> ApiResponse:
    """获取基金实时估值 / 最新净值。"""
    data = await svc.get_fund_quote(code)
    return ApiResponse(data=data)


@router.get("/fund/history", response_model=ApiResponse)
async def fund_history(
    _: Annotated[User, Depends(get_current_user)],
    code: str = Query(..., description="基金代码"),
    period: str = Query("3m", description="周期: 1m/3m/6m/1y/all"),
) -> ApiResponse:
    """获取基金历史净值。"""
    data = await svc.get_fund_history(code, period)
    return ApiResponse(data=data)


# ── 虚拟币 ─────────────────────────────────────────────────────


@router.get("/crypto/list", response_model=ApiResponse)
async def crypto_list(
    _: Annotated[User, Depends(get_current_user)],
    per_page: int = Query(50, description="数量"),
) -> ApiResponse:
    """Top 虚拟币行情。"""
    data = await svc.list_crypto(per_page)
    return ApiResponse(data=data)


@router.get("/crypto/quote", response_model=ApiResponse)
async def crypto_quote(
    _: Annotated[User, Depends(get_current_user)],
    coin_id: str = Query(..., description="CoinGecko coin id"),
) -> ApiResponse:
    """获取单个虚拟币详情。"""
    data = await svc.get_crypto_quote(coin_id)
    return ApiResponse(data=data)


@router.get("/crypto/history", response_model=ApiResponse)
async def crypto_history(
    _: Annotated[User, Depends(get_current_user)],
    coin_id: str = Query(..., description="CoinGecko coin id"),
    days: int = Query(7, description="天数: 1/7/30/365"),
) -> ApiResponse:
    """获取虚拟币历史价格。"""
    data = await svc.get_crypto_history(coin_id, days)
    return ApiResponse(data=data)


# ── 自选清单 ─────────────────────────────────────────────────────


@router.get("/watchlist", response_model=ApiResponse)
def list_watchlist(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """获取用户的理财自选清单。"""
    items = svc.list_watchlist(db, user.id)
    return ApiResponse(data=[WatchlistItemOut.model_validate(i) for i in items])


@router.post("/watchlist", response_model=ApiResponse[WatchlistItemOut])
def add_watchlist(
    body: WatchlistItemCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[WatchlistItemOut]:
    """添加自选。"""
    item = svc.add_watchlist(
        db,
        user.id,
        asset_type=body.asset_type,
        asset_code=body.asset_code,
        asset_name=body.asset_name,
    )
    return ApiResponse(data=WatchlistItemOut.model_validate(item))


@router.delete("/watchlist/{item_id}", response_model=ApiResponse)
def remove_watchlist(
    item_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """删除自选。"""
    ok = svc.remove_watchlist(db, user.id, item_id)
    return ApiResponse(data={"deleted": ok})


# ── 报告任务 ─────────────────────────────────────────────────────


@router.post("/report", response_model=ApiResponse[ReportOut])
async def submit_report(
    body: ReportSubmit,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportOut]:
    """提交理财报告生成任务（异步执行）。"""
    report = svc.create_report(
        db,
        user.id,
        stock_code=body.stock_code,
        stock_name=body.stock_name,
        report_type=body.report_type,
        roundtable_type=body.roundtable_type,
        research_direction=body.research_direction,
        ai_context=body.ai_context,
    )
    await svc.submit_report_task(report)
    return ApiResponse(data=ReportOut.model_validate(report))


@router.get("/reports", response_model=ApiResponse[list[ReportOut]])
def list_reports(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str = Query("", description="过滤状态: pending/running/completed/failed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ApiResponse[list[ReportOut]]:
    """获取用户报告列表。"""
    q = status.strip() or None
    items = svc.get_user_reports(db, user.id, status=q, limit=limit, offset=offset)
    return ApiResponse(data=[ReportOut.model_validate(i) for i in items])


@router.get("/report/{report_id}", response_model=ApiResponse[ReportOut])
def get_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportOut]:
    """获取单个报告详情。"""
    r = svc.get_report(db, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ApiResponse(data=ReportOut.model_validate(r))


@router.post("/report/{report_id}/cancel", response_model=ApiResponse[ReportOut])
def cancel_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportOut]:
    """取消报告生成任务。"""
    try:
        report = svc.cancel_report_task(db, user.id, report_id)
        return ApiResponse(data=ReportOut.model_validate(report))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/report/{report_id}/view")
def view_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """登录态查看：跳转到公开分享链接（可单独打开、可转发）。"""
    r = svc.get_report(db, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    if r.status != "completed" or not r.content:
        raise HTTPException(status_code=400, detail="报告尚未完成")
    token = svc.ensure_share_token(db, r)
    return RedirectResponse(url=f"/api/v1/share/finance/{token}", status_code=302)


@router.post("/report/{report_id}/share", response_model=ApiResponse[ReportOut])
def share_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    regenerate: bool = Query(True, description="是否重新生成令牌（覆盖旧链接）"),
) -> ApiResponse[ReportOut]:
    """生成/覆盖报告公开分享令牌。"""
    r = svc.get_report(db, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    if r.status != "completed" or not r.content:
        raise HTTPException(status_code=400, detail="报告尚未完成")
    if regenerate or not r.share_token:
        svc.regenerate_share_token(db, r)
    else:
        svc.ensure_share_token(db, r)
    return ApiResponse(data=ReportOut.model_validate(r))


@router.delete("/report/{report_id}/share", response_model=ApiResponse[ReportOut])
def unshare_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportOut]:
    """撤销报告公开分享链接。"""
    r = svc.get_report(db, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    svc.revoke_share_token(db, r)
    return ApiResponse(data=ReportOut.model_validate(r))


@public_router.get("/{share_token}", response_class=HTMLResponse)
def view_shared_report(
    share_token: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """公开分享页：无需登录即可查看已完成报告。"""
    r = svc.get_report_by_share_token(db, share_token)
    if not r or r.status != "completed" or not r.content:
        raise HTTPException(status_code=404, detail="报告不存在或尚未完成")
    return _render_completed_report(db, r)


@router.get("/report/{report_id}/download")
def download_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    fmt: str = Query("md", description="格式: md/pdf/docx"),
) -> PlainTextResponse:
    """下载报告内容。

    fmt 支持:
      - md:   Markdown 原文（默认）
      - pdf:  暂不支持（返回 md 占位）
      - docx: 暂不支持（返回 md 占位）
    """
    r = svc.get_report(db, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    if r.status != "completed" or not r.content:
        raise HTTPException(status_code=400, detail="报告尚未完成")

    content = r.content
    filename = f"{r.stock_code}_{r.report_type}_{r.created_at.strftime('%Y%m%d')}"

    if fmt == "pdf":
        # TODO: 接入 PDF 渲染引擎
        return PlainTextResponse(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.md"',
            },
        )
    if fmt == "docx":
        # TODO: 接入 DOCX 渲染引擎
        return PlainTextResponse(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.md"',
            },
        )

    # 默认 Markdown
    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.md"',
        },
    )


@router.post(
    "/report/{report_id}/import-library",
    response_model=ApiResponse[ReportImportLibraryOut],
)
def import_report_to_library(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportImportLibraryOut]:
    """将已完成报告加入个人级文档库（默认未分类）。"""
    data = svc.import_report_to_library(db, user, report_id)
    return ApiResponse(data=ReportImportLibraryOut.model_validate(data))


@router.delete("/report/{report_id}", response_model=ApiResponse)
def delete_report(
    report_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """删除报告。"""
    ok = svc.delete_report(db, user.id, report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ApiResponse(data={"deleted": True})
