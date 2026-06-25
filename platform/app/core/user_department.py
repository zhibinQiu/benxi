"""用户部门归属：全局规则为每人至多一个部门。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.models.org import UserDepartment
from app.services import department_service

SINGLE_DEPARTMENT_MESSAGE = "每个用户只能归属一个部门"


def validate_department_id_list(
    ids: list[uuid.UUID] | None,
) -> list[uuid.UUID]:
    """API / 服务层入参：0 或 1 个部门 id。"""
    if ids is None:
        return []
    if len(ids) > 1:
        raise ValueError(SINGLE_DEPARTMENT_MESSAGE)
    return list(ids)


def user_department_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    """用户所属部门（至多一个）。"""
    rows = list(
        db.scalars(
            select(UserDepartment.dept_id)
            .where(UserDepartment.user_id == user_id)
            .order_by(UserDepartment.is_primary.desc(), UserDepartment.dept_id)
            .limit(2)
        ).all()
    )
    if len(rows) > 1:
        # 历史脏数据：取主部门/第一条，写入路径应通过 set_user_departments 修复
        return rows[0]
    return rows[0] if rows else None


def user_dept_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    """兼容旧接口：返回 0 或 1 个部门 id 的列表。"""
    did = user_department_id(db, user_id)
    return [did] if did else []


def set_user_departments(
    db: Session,
    user_id: uuid.UUID,
    department_ids: list[uuid.UUID] | None,
) -> None:
    """替换用户部门归属（删除旧记录后写入 0 或 1 条）。"""
    ids = validate_department_id_list(department_ids)
    db.query(UserDepartment).filter(UserDepartment.user_id == user_id).delete()
    if ids:
        department_service.assert_department_exists(db, ids[0])
        db.add(
            UserDepartment(
                user_id=user_id,
                dept_id=ids[0],
                is_primary=True,
            )
        )


def set_user_departments_or_bad_request(
    db: Session,
    user_id: uuid.UUID,
    department_ids: list[uuid.UUID] | None,
) -> None:
    try:
        set_user_departments(db, user_id, department_ids)
    except ValueError as e:
        raise bad_request(str(e)) from e
