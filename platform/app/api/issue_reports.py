from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import user_is_system_admin
from app.database import get_db
from app.models.issue_report import IssueReport
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.issue_report import IssueReportCreate, IssueReportOut, IssueReportUpdate

router = APIRouter(prefix="/issue-reports", tags=["issue-reports"])


def _display_name(user: User | None) -> str:
    if not user:
        return ""
    name = (user.display_name or "").strip()
    if name:
        return name
    username = (user.username or "").strip()
    if username:
        return username
    return str(user.phone or user.id)


def _to_out(row: IssueReport, reporter: User, fixed_by: User | None) -> IssueReportOut:
    return IssueReportOut(
        id=row.id,
        description=row.description,
        status=row.status,
        reporter_id=row.reporter_id,
        reporter_name=_display_name(reporter),
        fixed_at=row.fixed_at,
        fixed_by_id=row.fixed_by_id,
        fixed_by_name=_display_name(fixed_by) if fixed_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _load_rows(
    db: Session, status: str | None
) -> list[tuple[IssueReport, User, User | None]]:
    stmt = (
        select(IssueReport, User)
        .join(User, IssueReport.reporter_id == User.id)
        .order_by(IssueReport.created_at.desc())
    )
    if status in ("open", "fixed"):
        stmt = stmt.where(IssueReport.status == status)
    rows = db.execute(stmt).all()
    fixed_ids = {r.fixed_by_id for r, _ in rows if r.fixed_by_id}
    fixed_users: dict[uuid.UUID, User] = {}
    if fixed_ids:
        fixed_users = {
            u.id: u for u in db.scalars(select(User).where(User.id.in_(fixed_ids))).all()
        }
    return [(r, reporter, fixed_users.get(r.fixed_by_id) if r.fixed_by_id else None) for r, reporter in rows]


@router.get("", response_model=ApiResponse[list[IssueReportOut]])
def list_issue_reports(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = Query(default=None, pattern="^(open|fixed)$"),
) -> ApiResponse[list[IssueReportOut]]:
    _ = user
    rows = _load_rows(db, status)
    return ApiResponse(data=[_to_out(r, reporter, fixed_by) for r, reporter, fixed_by in rows])


@router.post("", response_model=ApiResponse[IssueReportOut])
def create_issue_report(
    body: IssueReportCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[IssueReportOut]:
    description = body.description.strip()
    if not description:
        raise bad_request("问题描述不能为空")
    row = IssueReport(
        reporter_id=user.id,
        description=description,
        status="open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_out(row, user, None))


@router.patch("/{issue_id}", response_model=ApiResponse[IssueReportOut])
def update_issue_report(
    issue_id: uuid.UUID,
    body: IssueReportUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[IssueReportOut]:
    if not user_is_system_admin(db, user):
        raise forbidden("仅系统管理员可更新问题状态")
    row = db.get(IssueReport, issue_id)
    if not row:
        raise not_found("问题不存在")
    if body.status not in ("open", "fixed"):
        raise bad_request("无效状态")
    if body.status == row.status:
        reporter = db.get(User, row.reporter_id)
        fixed_by = db.get(User, row.fixed_by_id) if row.fixed_by_id else None
        return ApiResponse(data=_to_out(row, reporter, fixed_by))
    row.status = body.status
    if body.status == "fixed":
        row.fixed_at = datetime.now(timezone.utc)
        row.fixed_by_id = user.id
    else:
        row.fixed_at = None
        row.fixed_by_id = None
    db.commit()
    db.refresh(row)
    reporter = db.get(User, row.reporter_id)
    fixed_by = db.get(User, row.fixed_by_id) if row.fixed_by_id else None
    return ApiResponse(data=_to_out(row, reporter, fixed_by))


@router.delete("/{issue_id}", response_model=ApiResponse[dict])
def delete_issue_report(
    issue_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    if not user_is_system_admin(db, user):
        raise forbidden("仅系统管理员可删除问题")
    row = db.get(IssueReport, issue_id)
    if not row:
        raise not_found("问题不存在")
    db.delete(row)
    db.commit()
    return ApiResponse(data={"deleted": True, "id": str(issue_id)})
