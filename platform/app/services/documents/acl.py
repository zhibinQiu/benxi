from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPermission
from app.models.org import User


def grant_permission(
    db: Session,
    user: User,
    document: Document,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    level: str,
    expires_at,
) -> DocumentPermission:
    from app.core.document_scope import can_grant_document_permissions

    if not can_grant_document_permissions(db, user, document):
        from app.core.exceptions import forbidden

        raise forbidden("仅文档创建人、系统管理员或被授予可修改权限的用户可授权")

    from app.core.exceptions import bad_request
    from app.core.permissions import LEVEL_ORDER, normalize_permission_level

    norm = normalize_permission_level(level)
    if norm not in LEVEL_ORDER:
        raise bad_request(
            "无效的授权级别，可选：visible、query、modify"
        )
    if subject_type != "user":
        raise bad_request("文档分享仅支持按用户授权，请勾选具体用户")

    existing = db.scalar(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == subject_type,
            DocumentPermission.subject_id == subject_id,
        )
    )
    if existing:
        existing.level = norm
        existing.granted_by = user.id
        existing.expires_at = expires_at
        db.commit()
        db.refresh(existing)
        _invalidate_share_caches(user, subject_id)
        return existing

    perm = DocumentPermission(
        document_id=document.id,
        subject_type=subject_type,
        subject_id=subject_id,
        level=norm,
        granted_by=user.id,
        expires_at=expires_at,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    _invalidate_share_caches(user, subject_id)
    return perm


def _invalidate_share_caches(granter: User, grantee_id: uuid.UUID) -> None:
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(granter.id))
    if grantee_id != granter.id:
        invalidate_document_caches(str(grantee_id))
def list_acl_user_candidates(db: Session, document: Document) -> list[dict]:
    """授权/禁止访问时可选的用户列表（不含文档创建人）。"""
    from app.core.document_scope import DEPT_SCOPES, SCOPE_COMPANY
    from app.core.permissions import user_has_permission
    from app.models.org import Department, User, UserDepartment

    stmt = select(User).where(User.status == "active", User.id != document.owner_id)
    if document.scope in DEPT_SCOPES and document.dept_id:
        stmt = stmt.join(
            UserDepartment, UserDepartment.user_id == User.id
        ).where(UserDepartment.dept_id == document.dept_id)
    users = list(db.scalars(stmt.order_by(User.display_name, User.username).limit(500)).all())
    if document.scope == SCOPE_COMPANY:
        users = [u for u in users if user_has_permission(db, u, "doc.read")]
    if not users:
        return []

    user_ids = [u.id for u in users]
    dept_rows = db.execute(
        select(UserDepartment.user_id, UserDepartment.dept_id, Department.name)
        .join(Department, Department.id == UserDepartment.dept_id)
        .where(UserDepartment.user_id.in_(user_ids))
        .order_by(UserDepartment.is_primary.desc())
    ).all()
    dept_name_map: dict[uuid.UUID, list[str]] = {}
    dept_id_map: dict[uuid.UUID, list[uuid.UUID]] = {}
    for uid, did, name in dept_rows:
        if uid in dept_id_map:
            continue
        dept_name_map[uid] = [name]
        dept_id_map[uid] = [did]

    return [
        {
            "id": u.id,
            "username": u.display_name or u.username,
            "display_name": u.display_name or u.username,
            "department_id": (dept_id_map.get(u.id) or [None])[0],
            "department_names": dept_name_map.get(u.id, []),
            "department_ids": dept_id_map.get(u.id, []),
        }
        for u in users
    ]
def list_acl_picker_data(db: Session, document: Document) -> dict:
    """授权/禁止弹窗：公司—部门树 + 可选用户。"""
    from app.models.org import Department

    users = list_acl_user_candidates(db, document)
    depts = list(
        db.scalars(
            select(Department).order_by(Department.name)
        ).all()
    )
    return {
        "company_label": "公司",
        "departments": [
            {
                "id": d.id,
                "name": d.name,
                "parent_id": d.parent_id,
            }
            for d in depts
        ],
        "users": users,
    }
def _dedupe_user_permissions(
    db: Session, document_id: uuid.UUID
) -> dict[uuid.UUID, DocumentPermission]:
    """同一用户仅保留最高级别一条（清理历史重复）。"""
    from app.core.permissions import LEVEL_ORDER, normalize_permission_level

    rows = list(
        db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document_id,
                DocumentPermission.subject_type == "user",
            )
        ).all()
    )
    best_by_user: dict[uuid.UUID, DocumentPermission] = {}
    dup_ids: list[uuid.UUID] = []
    for p in rows:
        uid = p.subject_id
        prev = best_by_user.get(uid)
        if not prev:
            best_by_user[uid] = p
            continue
        if LEVEL_ORDER.get(normalize_permission_level(p.level), 0) > LEVEL_ORDER.get(
            normalize_permission_level(prev.level), 0
        ):
            dup_ids.append(prev.id)
            best_by_user[uid] = p
        else:
            dup_ids.append(p.id)
    if dup_ids:
        for dup in db.scalars(
            select(DocumentPermission).where(DocumentPermission.id.in_(dup_ids))
        ).all():
            db.delete(dup)
        db.commit()
    return best_by_user
def list_document_shares(db: Session, document_id: uuid.UUID) -> list[dict]:
    """当前文档分享给谁、授予何种权限（每人至多一项）。"""
    from app.models.org import User as UserModel

    best = _dedupe_user_permissions(db, document_id)
    if not best:
        return []
    user_ids = list(best.keys())
    from app.core.user_display import user_display_name

    names = {
        u.id: user_display_name(u)
        for u in db.scalars(select(UserModel).where(UserModel.id.in_(user_ids))).all()
    }
    out: list[dict] = []
    for uid, perm in best.items():
        out.append(
            {
                "user_id": uid,
                "user_name": names.get(uid, user_display_name(None)),
                "level": perm.level,
            }
        )
    out.sort(key=lambda x: (x.get("user_name") or "", str(x["user_id"])))
    return out
def list_document_permissions(
    db: Session, document_id: uuid.UUID
) -> list[DocumentPermission]:
    """兼容：返回去重后的 user 型 DocumentPermission。"""
    return list(_dedupe_user_permissions(db, document_id).values())
def set_document_shares(
    db: Session,
    actor: User,
    document: Document,
    *,
    user_ids: list[uuid.UUID],
    level: str,
) -> list[dict]:
    """批量设置分享权限（每人当前仅一种级别）。"""
    seen: set[uuid.UUID] = set()
    for uid in user_ids:
        if uid in seen:
            continue
        seen.add(uid)
        grant_permission(
            db,
            actor,
            document,
            subject_type="user",
            subject_id=uid,
            level=level,
            expires_at=None,
        )
    return list_document_shares(db, document.id)
def revoke_document_share(
    db: Session, actor: User, document: Document, user_id: uuid.UUID
) -> None:
    """取消对某用户的分享（删除其全部 user 型授权）。"""
    from app.core.document_scope import can_grant_document_permissions
    from app.core.exceptions import forbidden

    if not can_grant_document_permissions(db, actor, document):
        raise forbidden("仅文档创建人或系统管理员可撤销授权")
    for perm in db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == "user",
            DocumentPermission.subject_id == user_id,
        )
    ).all():
        db.delete(perm)
    db.commit()
    _invalidate_share_caches(actor, user_id)
def revoke_permission(
    db: Session, actor: User, document: Document, perm_id: uuid.UUID
) -> None:
    from app.core.document_scope import can_grant_document_permissions
    from app.core.exceptions import forbidden, not_found

    if not can_grant_document_permissions(db, actor, document):
        raise forbidden("仅文档创建人或系统管理员可撤销授权")
    perm = db.get(DocumentPermission, perm_id)
    if not perm or perm.document_id != document.id:
        raise not_found("授权不存在")
    if perm.subject_type == "user":
        revoke_document_share(db, actor, document, perm.subject_id)
        return
    db.delete(perm)
    db.commit()
def _subject_user_label(db: Session, user_id: uuid.UUID) -> str:
    from app.core.user_display import user_display_name

    return user_display_name(db.get(User, user_id))
