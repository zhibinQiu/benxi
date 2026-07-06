"""部门管理 — 供 API 与智能体工具共用。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.models.org import Department, User, UserDepartment


def would_create_parent_cycle(
    db: Session, dept_id: uuid.UUID, parent_id: uuid.UUID
) -> bool:
    """上级不能为自己或自己的下级。"""
    if parent_id == dept_id:
        return True
    seen: set[uuid.UUID] = set()
    current = db.get(Department, parent_id)
    while current and current.parent_id:
        if current.id in seen:
            break
        seen.add(current.id)
        if current.id == dept_id:
            return True
        current = db.get(Department, current.parent_id)
    return False


def list_departments(db: Session) -> list[Department]:
    return list(db.scalars(select(Department).order_by(Department.name)).all())


def find_user_with_org_label(db: Session, name: str) -> User | None:
    """按姓名/用户名查找用户（组织标签冲突检测）。"""
    label = (name or "").strip()
    if not label:
        return None
    key = label.casefold()
    return db.scalar(
        select(User).where(
            or_(
                func.lower(User.display_name) == key,
                func.lower(User.username) == key,
            )
        ).limit(1)
    )


def find_department_by_name(db: Session, name: str) -> Department | None:
    label = (name or "").strip()
    if not label:
        return None
    return db.scalar(select(Department).where(Department.name == label).limit(1))


def assert_department_label_not_user(db: Session, name: str) -> None:
    user = find_user_with_org_label(db, name)
    if user:
        raise bad_request(
            f"「{(name or '').strip()}」已是用户姓名，不能作为部门名称；"
            "请为用户分配已有部门，而非以人名新建部门"
        )


def assert_department_exists(db: Session, dept_id: uuid.UUID) -> Department:
    dept = db.get(Department, dept_id)
    if not dept:
        raise bad_request("部门不存在")
    return dept


def create_department(
    db: Session,
    *,
    name: str,
    parent_id: uuid.UUID | None = None,
) -> Department:
    label = (name or "").strip()
    if not label:
        raise bad_request("部门名称不能为空")
    assert_department_label_not_user(db, label)
    if parent_id is not None:
        parent = db.get(Department, parent_id)
        if not parent:
            raise bad_request("上级部门不存在")
    dept = Department(name=label, parent_id=parent_id)
    db.add(dept)
    db.flush()
    return dept


def update_department(
    db: Session,
    dept_id: uuid.UUID,
    *,
    name: str | None = None,
    parent_id: uuid.UUID | None = None,
    parent_id_set: bool = False,
) -> Department:
    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("部门不存在")
    if name is not None:
        label = name.strip()
        if not label:
            raise bad_request("部门名称不能为空")
        assert_department_label_not_user(db, label)
        dept.name = label
    if parent_id_set:
        if parent_id is not None:
            parent = db.get(Department, parent_id)
            if not parent:
                raise bad_request("上级部门不存在")
            if would_create_parent_cycle(db, dept_id, parent_id):
                raise bad_request("上级部门不能为自己或下级部门")
        dept.parent_id = parent_id
    db.flush()
    return dept


def delete_department(db: Session, dept_id: uuid.UUID) -> None:
    dept = db.get(Department, dept_id)
    if not dept:
        raise not_found("部门不存在")
    child = db.scalar(
        select(Department.id).where(Department.parent_id == dept_id).limit(1)
    )
    if child:
        raise bad_request("请先删除或移走下级部门")
    member_count = db.scalar(
        select(UserDepartment.id).where(UserDepartment.dept_id == dept_id).limit(1)
    )
    if member_count:
        raise bad_request("部门下仍有用户，请先在用户管理中调整所属部门")
    db.query(UserDepartment).filter(UserDepartment.dept_id == dept_id).delete()
    db.delete(dept)
    db.flush()
