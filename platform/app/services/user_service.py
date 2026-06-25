"""用户生命周期（删除时级联清理关联数据）。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.core.permissions import user_dept_ids
from app.core.phone import is_bootstrap_login_id
from app.core.platform_admin import (
    SYSTEM_ADMIN_ROLE_CODE,
    ensure_bootstrap_has_system_admin_role,
    is_bootstrap_admin,
)
from app.core.security import hash_password
from app.core.user_department import set_user_departments_or_bad_request, user_department_id
from app.core.user_identity import email_taken, phone_taken, user_display_name, username_taken
from app.models.audit import AuditLog
from app.models.compare import CompareJob
from app.models.document import Document, DocumentPermission, DocumentVersion, SubjectType
from app.models.document_workflow import DocumentAccessDenial, DocumentPublishRequest
from app.models.job import Job, JobEvent
from app.models.meeting_record import MeetingRecord
from app.models.notification import Notification
from app.models.org import User, UserDepartment, UserRole
from app.models.rag import RagMessage, RagSession
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_link import RagflowAccountLink
from app.schemas.org import UserCreate, UserOut, UserUpdate

logger = logging.getLogger(__name__)


def _display_name(user: User) -> str:
    return user_display_name(user)


def try_provision_ragflow_account(db: Session, user: User) -> None:
    from app.domains.knowledge import knowledge

    if not knowledge.enabled():
        return
    try:
        knowledge.ensure_account(db, user)
    except Exception as e:
        logger.warning(
            "RAGFlow 开户失败（平台用户已保存）%s: %s",
            _display_name(user),
            e,
        )


def serialize_user_out(db: Session, user: User) -> UserOut:
    from app.models.org import Role

    pid = user_department_id(db, user.id)
    dept_ids = [pid] if pid else []
    role_rows = list(
        db.execute(
            select(UserRole.role_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    role_ids = [rid for rid, _ in role_rows]
    role_names = [rname for _, rname in role_rows]
    if is_bootstrap_admin(user) and "系统管理员" not in role_names:
        role_names = ["系统管理员", *role_names]
    name = _display_name(user)
    uname = (user.username or "").strip() or name
    return UserOut(
        id=user.id,
        phone=user.phone,
        display_name=name,
        username=uname,
        email=user.email,
        status=user.status,
        created_at=user.created_at,
        department_id=pid,
        department_ids=dept_ids,
        role_ids=role_ids,
        role_names=role_names,
    )


def list_users_page(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = list(
        db.scalars(
            select(User)
            .order_by(User.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return users, int(total)


def create_user_account(db: Session, body: UserCreate) -> User:
    from app.models.org import Role

    if is_bootstrap_login_id(body.phone):
        raise bad_request("该登录号为系统保留")
    if phone_taken(db, body.phone):
        raise bad_request("该手机号已存在")
    if email_taken(db, body.email):
        raise bad_request("该邮箱已存在")
    name = body.display_name.strip()
    if username_taken(db, name):
        raise bad_request("该姓名已被使用")
    from app.services.department_service import find_department_by_name

    if find_department_by_name(db, name):
        raise bad_request("该姓名与已有部门名称重复，请使用不同姓名")
    user = User(
        phone=body.phone,
        username=name,
        display_name=name,
        email=body.email,
        password_hash=hash_password(body.password),
        status=body.status,
    )
    db.add(user)
    db.flush()
    set_user_departments_or_bad_request(db, user.id, body.department_ids)
    member_role = db.scalar(select(Role).where(Role.code == "member"))
    role_ids = list(body.role_ids)
    if not role_ids and member_role:
        role_ids = [member_role.id]
    for role_id in role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))
    try_provision_ragflow_account(db, user)
    db.flush()
    return user


def update_user_account(db: Session, user: User, body: UserUpdate) -> User:
    from app.models.org import Role

    if body.phone is not None:
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的手机号")
        if phone_taken(db, body.phone, exclude_user_id=user.id):
            raise bad_request("该手机号已被使用")
        user.phone = body.phone
    if body.display_name is not None:
        name = body.display_name.strip()
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的姓名")
        if username_taken(db, name, exclude_user_id=user.id):
            raise bad_request("该姓名已被使用")
        from app.services.department_service import find_department_by_name

        if find_department_by_name(db, name):
            raise bad_request("该姓名与已有部门名称重复，请使用不同姓名")
        user.display_name = name
        user.username = name
    elif body.username is not None:
        name = body.username.strip()
        if is_bootstrap_admin(user):
            raise bad_request("不能修改系统管理员的姓名")
        if username_taken(db, name, exclude_user_id=user.id):
            raise bad_request("该姓名已被使用")
        from app.services.department_service import find_department_by_name

        if find_department_by_name(db, name):
            raise bad_request("该姓名与已有部门名称重复，请使用不同姓名")
        user.username = name
        user.display_name = name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.email is not None:
        if email_taken(db, body.email, exclude_user_id=user.id):
            raise bad_request("该邮箱已被使用")
        user.email = body.email
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise bad_request("Invalid status")
        if is_bootstrap_admin(user) and body.status != "active":
            raise bad_request("不能禁用系统默认管理员")
        user.status = body.status
    previous_dept_ids: list | None = None
    if body.department_ids is not None:
        if is_bootstrap_admin(user) and body.department_ids:
            raise bad_request("系统默认管理员不归属任何部门")
        previous_dept_ids = user_dept_ids(db, user.id)
        set_user_departments_or_bad_request(db, user.id, body.department_ids)
    if body.role_ids is not None:
        role_ids = list(body.role_ids)
        sys_role = db.scalar(select(Role).where(Role.code == SYSTEM_ADMIN_ROLE_CODE))
        member_role = db.scalar(select(Role).where(Role.code == "member"))
        if sys_role and is_bootstrap_admin(user):
            if sys_role.id not in role_ids:
                role_ids.append(sys_role.id)
        if not role_ids and member_role:
            role_ids = [member_role.id]
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role_id in role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
        if is_bootstrap_admin(user):
            ensure_bootstrap_has_system_admin_role(db, user)
    db.flush()
    if previous_dept_ids is not None:
        from app.domains.knowledge import knowledge

        if knowledge.enabled():
            try:
                knowledge.reconcile_dept_membership_kb(
                    db, user, previous_dept_ids=previous_dept_ids
                )
            except Exception as e:
                logger.warning(
                    "部门变动 KnowFlow 授权同步失败 %s: %s", _display_name(user), e
                )
    return user


def delete_user_by_admin(
    db: Session,
    *,
    actor: User,
    target_user_id: uuid.UUID,
) -> dict[str, Any]:
    user = db.get(User, target_user_id)
    if not user:
        raise not_found("User not found")
    if user.id == actor.id:
        raise bad_request("不能删除当前登录用户")
    if is_bootstrap_admin(user):
        raise bad_request("不能删除系统默认管理员")
    delete_user_account(db, user)
    return {"deleted": True, "id": str(target_user_id)}


def delete_user_account(db: Session, user: User) -> None:
    """删除用户及其关联记录，避免外键约束失败。"""
    from app.services.user_knowflow_purge import purge_user_knowledge_resources

    uid = user.id

    try:
        purge_user_knowledge_resources(db, user)
    except Exception as e:
        logger.warning("删除用户资源清理失败 %s: %s", user.username, e)

    # 知识问答 / 对比 / 任务 / 通知
    session_ids = list(
        db.scalars(select(RagSession.id).where(RagSession.created_by == uid)).all()
    )
    if session_ids:
        db.execute(delete(RagMessage).where(RagMessage.session_id.in_(session_ids)))
        db.execute(delete(RagSession).where(RagSession.id.in_(session_ids)))

    job_ids = list(db.scalars(select(Job.id).where(Job.created_by == uid)).all())
    if job_ids:
        db.execute(delete(JobEvent).where(JobEvent.job_id.in_(job_ids)))
        db.execute(delete(Job).where(Job.id.in_(job_ids)))

    db.execute(delete(CompareJob).where(CompareJob.created_by == uid))
    db.execute(delete(Notification).where(Notification.user_id == uid))
    db.execute(delete(MeetingRecord).where(MeetingRecord.user_id == uid))

    # RAGFlow 映射
    db.execute(delete(RagflowDocumentLink).where(RagflowDocumentLink.platform_user_id == uid))
    db.execute(
        delete(RagflowDocumentMirrorLink).where(
            RagflowDocumentMirrorLink.platform_user_id == uid
        )
    )
    db.execute(delete(RagflowAccountLink).where(RagflowAccountLink.platform_user_id == uid))

    # 文档协作记录（非 owner）
    db.execute(delete(DocumentAccessDenial).where(DocumentAccessDenial.user_id == uid))
    db.execute(
        delete(DocumentAccessDenial).where(DocumentAccessDenial.created_by == uid)
    )
    db.execute(
        update(DocumentPublishRequest)
        .where(DocumentPublishRequest.reviewed_by == uid)
        .values(reviewed_by=None)
    )
    db.execute(
        delete(DocumentPublishRequest).where(DocumentPublishRequest.requested_by == uid)
    )
    db.execute(
        delete(DocumentPermission).where(
            DocumentPermission.subject_type == SubjectType.user.value,
            DocumentPermission.subject_id == uid,
        )
    )
    db.execute(delete(DocumentPermission).where(DocumentPermission.granted_by == uid))

    db.execute(
        update(Document).where(Document.deleted_by == uid).values(deleted_by=None)
    )
    from app.core.platform_admin import normalize_bootstrap_login_id

    admin = db.scalar(
        select(User).where(User.phone == normalize_bootstrap_login_id()).limit(1)
    )
    if admin and admin.id != uid:
        db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.created_by == uid)
            .values(created_by=admin.id)
        )

    db.execute(update(AuditLog).where(AuditLog.user_id == uid).values(user_id=None))

    db.execute(delete(UserDepartment).where(UserDepartment.user_id == uid))
    db.execute(delete(UserRole).where(UserRole.user_id == uid))
    db.delete(user)
