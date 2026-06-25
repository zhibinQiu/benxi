"""本析智能 — 用户与部门管理工具（复用 user_service / department_service）。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import user_has_permission
from app.models.org import Department, User
from app.schemas.org import UserCreate, UserUpdate
from app.services import department_service, user_service


def _require_admin_user(db: Session, actor: User) -> None:
    if not user_has_permission(db, actor, "admin.user"):
        raise forbidden("无权管理用户")


def _require_admin_dept(db: Session, actor: User) -> None:
    if not user_has_permission(db, actor, "admin.dept"):
        raise forbidden("无权管理部门")


def _resolve_user_id(
    db: Session,
    *,
    user_id: uuid.UUID | None = None,
    user_name: str | None = None,
) -> uuid.UUID:
    if user_id is not None:
        return user_id
    ident = (user_name or "").strip()
    if not ident:
        raise bad_request("请提供 user_id 或 user_name")
    key = ident.casefold()
    rows = list(
        db.scalars(
            select(User).where(
                or_(
                    User.username.ilike(ident),
                    User.display_name.ilike(ident),
                    User.phone == ident,
                )
            )
        ).all()
    )
    if not rows:
        raise bad_request(f"未找到用户：{ident}")
    if len(rows) > 1:
        raise bad_request(f"用户「{ident}」匹配到多条记录，请提供 user_id")
    return rows[0].id


def _resolve_department_id(
    db: Session,
    *,
    department_id: uuid.UUID | None = None,
    department_name: str | None = None,
) -> uuid.UUID:
    if department_id is not None:
        return department_id
    name = (department_name or "").strip()
    if not name:
        raise bad_request("请提供 department_id 或 department_name")
    rows = list(
        db.scalars(select(Department).where(Department.name == name)).all()
    )
    if not rows:
        if department_service.find_user_with_org_label(db, name):
            raise bad_request(
                f"「{name}」是用户姓名而非部门，请提供 department_id 或选择正确的部门名称"
            )
        raise bad_request(f"未找到部门：{name}")
    if len(rows) > 1:
        raise bad_request(f"部门「{name}」匹配到多条记录，请提供 department_id")
    return rows[0].id


def list_users_for_agent(
    db: Session,
    actor: User,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict[str, Any]:
    _require_admin_user(db, actor)
    users, total = user_service.list_users_page(db, page=page, page_size=page_size)
    kw = (keyword or "").strip().casefold()
    items = []
    for user in users:
        out = user_service.serialize_user_out(db, user)
        if kw:
            hay = " ".join(
                [
                    out.display_name or "",
                    out.username or "",
                    out.phone or "",
                    out.email or "",
                ]
            ).casefold()
            if kw not in hay:
                continue
        items.append(out.model_dump(mode="json"))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def create_user_for_agent(
    db: Session,
    actor: User,
    *,
    phone: str,
    email: str,
    display_name: str,
    password: str,
    status: str = "active",
    department_id: uuid.UUID | None = None,
    department_name: str | None = None,
) -> dict[str, Any]:
    _require_admin_user(db, actor)
    dept_ids: list[uuid.UUID] = []
    if department_id or department_name:
        dept_ids = [
            _resolve_department_id(
                db,
                department_id=department_id,
                department_name=department_name,
            )
        ]
    body = UserCreate(
        phone=phone,
        email=email,
        display_name=display_name,
        password=password,
        status=status,
        department_ids=dept_ids,
    )
    user = user_service.create_user_account(db, body)
    db.commit()
    db.refresh(user)
    out = user_service.serialize_user_out(db, user)
    return {
        "message": f"已创建用户「{out.display_name}」",
        "user": out.model_dump(mode="json"),
    }


def update_user_for_agent(
    db: Session,
    actor: User,
    *,
    user_id: uuid.UUID | None = None,
    user_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
    password: str | None = None,
    status: str | None = None,
    department_id: uuid.UUID | None = None,
    department_name: str | None = None,
    clear_department: bool = False,
) -> dict[str, Any]:
    _require_admin_user(db, actor)
    target_id = _resolve_user_id(db, user_id=user_id, user_name=user_name)
    user = db.get(User, target_id)
    if not user:
        raise not_found("用户不存在")
    dept_ids: list[uuid.UUID] | None = None
    if clear_department:
        dept_ids = []
    elif department_id is not None or department_name:
        dept_ids = [
            _resolve_department_id(
                db,
                department_id=department_id,
                department_name=department_name,
            )
        ]
    body = UserUpdate(
        phone=phone,
        email=email,
        display_name=display_name,
        password=password,
        status=status,
        department_ids=dept_ids,
    )
    user = user_service.update_user_account(db, user, body)
    db.commit()
    db.refresh(user)
    out = user_service.serialize_user_out(db, user)
    return {
        "message": f"已更新用户「{out.display_name}」",
        "user": out.model_dump(mode="json"),
    }


def delete_user_for_agent(
    db: Session,
    actor: User,
    *,
    user_id: uuid.UUID | None = None,
    user_name: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    _require_admin_user(db, actor)
    if not confirm:
        raise bad_request("删除用户需显式设置 confirm=true")
    target_id = _resolve_user_id(db, user_id=user_id, user_name=user_name)
    result = user_service.delete_user_by_admin(
        db, actor=actor, target_user_id=target_id
    )
    db.commit()
    return {"message": "已删除用户", **result}


def list_departments_for_agent(db: Session, actor: User) -> list[dict[str, Any]]:
    if not (
        user_has_permission(db, actor, "admin.dept")
        or user_has_permission(db, actor, "admin.user")
    ):
        raise forbidden("无权查看部门")
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "parent_id": str(d.parent_id) if d.parent_id else None,
        }
        for d in department_service.list_departments(db)
    ]


def create_department_for_agent(
    db: Session,
    actor: User,
    *,
    name: str,
    parent_id: uuid.UUID | None = None,
    parent_name: str | None = None,
) -> dict[str, Any]:
    _require_admin_dept(db, actor)
    parent = parent_id
    if parent is None and parent_name:
        parent = _resolve_department_id(db, department_name=parent_name)
    dept = department_service.create_department(db, name=name, parent_id=parent)
    db.commit()
    db.refresh(dept)
    return {
        "message": f"已创建部门「{dept.name}」",
        "id": str(dept.id),
        "name": dept.name,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
    }


def update_department_for_agent(
    db: Session,
    actor: User,
    *,
    department_id: uuid.UUID | None = None,
    department_name: str | None = None,
    name: str | None = None,
    parent_id: uuid.UUID | None = None,
    parent_name: str | None = None,
    clear_parent: bool = False,
) -> dict[str, Any]:
    _require_admin_dept(db, actor)
    dept_id = _resolve_department_id(
        db, department_id=department_id, department_name=department_name
    )
    parent = parent_id
    parent_set = False
    if clear_parent:
        parent = None
        parent_set = True
    elif parent_name:
        parent = _resolve_department_id(db, department_name=parent_name)
        parent_set = True
    elif parent_id is not None:
        parent_set = True
    dept = department_service.update_department(
        db,
        dept_id,
        name=name,
        parent_id=parent,
        parent_id_set=parent_set,
    )
    db.commit()
    db.refresh(dept)
    return {
        "message": f"已更新部门「{dept.name}」",
        "id": str(dept.id),
        "name": dept.name,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
    }


def delete_department_for_agent(
    db: Session,
    actor: User,
    *,
    department_id: uuid.UUID | None = None,
    department_name: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    _require_admin_dept(db, actor)
    if not confirm:
        raise bad_request("删除部门需显式设置 confirm=true")
    dept_id = _resolve_department_id(
        db, department_id=department_id, department_name=department_name
    )
    department_service.delete_department(db, dept_id)
    db.commit()
    return {"message": "已删除部门", "id": str(dept_id)}
