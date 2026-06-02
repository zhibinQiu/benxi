"""分级知识库：公司/部门/个人单库共享，平台 ACL → KnowFlow RBAC 授权。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_TEAM,
    SCOPE_PERSONAL,
    _document_scope,
    can_delete_document,
    can_edit_document,
    can_edit_in_scope,
    can_query_document,
    can_read_document,
)
from app.core.permissions import PermissionLevel, user_dept_ids, user_has_permission, user_is_superuser
from app.config import get_settings
from app.integrations.ragflow_client import RagflowClient
from app.integrations.ragflow_kb_acl import grant_kb_user_permission, revoke_kb_user_permission
from app.integrations.ragflow_rbac import ensure_ragflow_global_admin
from app.models.document import Document
from app.models.org import User, UserDepartment
from app.models.ragflow_link import RagflowAccountLink
from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
    SCOPE_TEAM as REG_TEAM,
    SCOPE_PERSONAL as REG_PERSONAL,
    RagflowScopeDataset,
)
from app.services.ragflow_identity_service import get_or_create_link
from app.services.ragflow_naming import (
    _id_suffix,
    dataset_display_label_company,
    dataset_display_label_dept,
    dataset_display_label_personal,
    dataset_name_for_company,
    dataset_name_for_dept,
    dataset_name_for_personal,
    dept_id_from_dataset_name,
    legacy_dataset_name_for_company,
    legacy_dataset_name_for_dept,
    legacy_dataset_name_for_personal,
    legacy_dataset_name_for_platform_user,
    legacy_scope_dataset_names,
)

logger = logging.getLogger(__name__)

COMPANY_SCOPE_KEY = "global"


def scope_key_for_document(document: Document) -> str:
    scope = _document_scope(db, document)
    if scope == SCOPE_COMPANY:
        if document.dept_id:
            return str(document.dept_id)
        return COMPANY_SCOPE_KEY
    if scope in (SCOPE_DEPARTMENT, SCOPE_TEAM):
        if document.dept_id:
            return str(document.dept_id)
        return str(document.owner_id)
    return str(document.owner_id)


def _get_registry(
    db: Session, scope: str, scope_key: str
) -> RagflowScopeDataset | None:
    return db.scalar(
        select(RagflowScopeDataset).where(
            RagflowScopeDataset.scope == scope,
            RagflowScopeDataset.scope_key == scope_key,
        )
    )


def _can_create_scope_dataset(db: Session, user: User, scope: str) -> bool:
    if user_is_superuser(db, user):
        return True
    if scope == SCOPE_PERSONAL:
        return True
    return can_edit_in_scope(db, user, scope)


def _admin_rag_client() -> RagflowClient | None:
    """跨租户建库仅支持 RAGFLOW_API_KEY；mapped 模式应为用户授予 KnowFlow admin 后自建库。"""
    key = (get_settings().ragflow_api_key or "").strip()
    if not key:
        return None
    return RagflowClient(api_key=key)


def _kb_permission_denied(exc: BaseException) -> bool:
    msg = str(exc)
    return "没有创建知识库" in msg or "permission" in msg.lower()


def _visible_dataset_ids(kf) -> set[str]:
    try:
        return {
            str(k.get("id"))
            for k in kf._rag.list_datasets()
            if k.get("id")
        }
    except Exception:
        return set()


def _append_kb_label(
    labels: list[dict[str, str]],
    seen: set[str],
    technical: str,
    label: str,
) -> None:
    tech = (technical or "").strip()
    disp = (label or "").strip()
    if not tech or not disp or tech in seen:
        return
    seen.add(tech)
    labels.append({"name": tech, "label": disp})


def _align_dataset_display_name(rag: RagflowClient, dataset_id: str, target_name: str) -> None:
    current = rag.get_dataset_name(dataset_id)
    if not current or current == target_name:
        return
    try:
        rag.update_dataset_name(dataset_id, target_name)
        logger.info("知识库已重命名: %s → %s", current, target_name)
    except Exception as e:
        logger.warning("知识库重命名 %s → %s 失败: %s", current, target_name, e)


def repair_stale_scope_registries(db: Session, kf) -> int:
    """删除 RAGFlow 中已不存在、但注册表仍指向的旧知识库记录。"""
    visible = _visible_dataset_ids(kf)
    if not visible:
        return 0
    removed = 0
    for reg in list(db.scalars(select(RagflowScopeDataset)).all()):
        if reg.ragflow_dataset_id in visible:
            continue
        db.delete(reg)
        removed += 1
    if removed:
        db.flush()
    return removed


def ensure_scope_dataset(
    db: Session,
    actor: User,
    scope: str,
    scope_key: str,
    kf,
) -> str | None:
    """确保分级知识库存在（全局唯一），返回 ragflow dataset id。"""
    reg_scope = {
        SCOPE_COMPANY: REG_COMPANY,
        SCOPE_DEPARTMENT: REG_DEPARTMENT,
        SCOPE_TEAM: REG_TEAM,
        SCOPE_PERSONAL: REG_PERSONAL,
    }.get(scope, REG_PERSONAL)

    if scope == SCOPE_COMPANY:
        if scope_key == COMPANY_SCOPE_KEY:
            name = dataset_name_for_company()
        else:
            name = dataset_name_for_dept(uuid.UUID(scope_key), db)
    elif scope in (SCOPE_DEPARTMENT, SCOPE_TEAM):
        name = dataset_name_for_dept(uuid.UUID(scope_key), db)
    else:
        name = dataset_name_for_personal(uuid.UUID(scope_key), db)

    lookup_names = [name, *legacy_scope_dataset_names(scope, scope_key)]
    lookup_names = list(dict.fromkeys(n for n in lookup_names if n))

    existing = _get_registry(db, reg_scope, scope_key)
    rag = kf._rag
    if existing:
        visible = _visible_dataset_ids(kf)
        if visible and existing.ragflow_dataset_id in visible:
            _align_dataset_display_name(rag, existing.ragflow_dataset_id, name)
            return existing.ragflow_dataset_id
        db.delete(existing)
        db.flush()
    owner_ragflow_user_id: str | None = None
    if not _can_create_scope_dataset(db, actor, scope):
        admin_rag = _admin_rag_client()
        if not admin_rag:
            logger.info(
                "用户 %s 无权创建 %s 知识库，且未配置 RAGFLOW_API_KEY",
                actor.username,
                scope,
            )
            return None
        rag = admin_rag
        bootstrap = db.scalar(
            select(RagflowAccountLink).where(
                RagflowAccountLink.platform_user_id == actor.id
            )
        )
        owner_ragflow_user_id = (
            (bootstrap.ragflow_user_id or "").strip() if bootstrap else None
        ) or None
    else:
        link = get_or_create_link(db, actor)
        owner_ragflow_user_id = link.ragflow_user_id

    found = rag.find_dataset_by_names(lookup_names)
    if found and found.get("id"):
        ds_id = str(found["id"])
        _align_dataset_display_name(rag, ds_id, name)
        reg = RagflowScopeDataset(
            scope=reg_scope,
            scope_key=scope_key,
            ragflow_dataset_id=ds_id,
            owner_ragflow_user_id=owner_ragflow_user_id,
        )
        db.add(reg)
        db.flush()
        return ds_id

    try:
        ds_id = rag.ensure_dataset(name)
    except Exception as e:
        if _kb_permission_denied(e) and owner_ragflow_user_id:
            if ensure_ragflow_global_admin(owner_ragflow_user_id):
                try:
                    ds_id = rag.ensure_dataset(name)
                except Exception as e2:
                    logger.warning("创建知识库 %s 失败（已授予 admin）: %s", name, e2)
                    return None
            else:
                logger.warning("创建知识库 %s 失败: %s", name, e)
                return None
        else:
            logger.warning("创建知识库 %s 失败: %s", name, e)
            return None

    reg = RagflowScopeDataset(
        scope=reg_scope,
        scope_key=scope_key,
        ragflow_dataset_id=ds_id,
        owner_ragflow_user_id=owner_ragflow_user_id,
    )
    db.add(reg)
    db.flush()
    return ds_id


def resolve_dataset_for_document(db: Session, actor: User, document: Document, kf) -> str | None:
    scope = _document_scope(db, document)
    key = scope_key_for_document(document)
    return ensure_scope_dataset(db, actor, scope, key, kf)


def _user_has_queryable_doc_in_scope(
    db: Session,
    user: User,
    scope: str,
    *,
    dept_id: uuid.UUID | None = None,
) -> bool:
    """用户在某分级下是否至少有一份可查询的启用文档。"""
    from app.models.document import DocumentStatus

    stmt = select(Document.id).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        Document.scope == scope,
    )
    if scope in (SCOPE_DEPARTMENT, SCOPE_TEAM) and dept_id:
        stmt = stmt.where(Document.dept_id == dept_id)
    for doc_id in db.scalars(stmt.limit(300)):
        doc = db.get(Document, doc_id)
        if doc and can_query_document(db, user, doc):
            return True
    return False


def kb_level_for_user_on_document(db: Session, user: User, document: Document) -> str | None:
    """平台文档权限 → KnowFlow 知识库权限（仅「可查询」及以上可检索）。"""
    if not can_query_document(db, user, document):
        return None
    if can_delete_document(db, user, document):
        return "admin"
    if can_edit_document(db, user, document):
        return "write"
    return "read"


def _ragflow_user_id(db: Session, platform_user_id: uuid.UUID) -> str | None:
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == platform_user_id
        )
    )
    return (link.ragflow_user_id or "").strip() or None if link else None


def _grant_explicit_user_permissions(
    db: Session, document: Document, dataset_id: str
) -> int:
    """为文档的显式用户授权同步 KnowFlow 知识库权限（含跨部门分享）。"""
    from app.models.document import DocumentPermission

    granted = 0
    perms = db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == "user",
        )
    ).all()
    seen: set[uuid.UUID] = set()
    for perm in perms:
        uid = perm.subject_id
        if uid in seen:
            continue
        seen.add(uid)
        user = db.get(User, uid)
        if not user or user.status != "active":
            continue
        level = kb_level_for_user_on_document(db, user, document)
        rid = _ragflow_user_id(db, uid)
        if level and rid and grant_kb_user_permission(dataset_id, rid, level):
            granted += 1
    return granted


def sync_document_kb_grants(db: Session, document: Document) -> int:
    """按平台文档 ACL 同步该文档所在知识库的 KnowFlow 授权（不复制文档）。"""
    from app.models.ragflow_document_link import RagflowDocumentLink

    link = db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document.id
        )
    )
    if not link or not link.dataset_id:
        return 0

    scope = _document_scope(db, document)
    granted = 0
    if scope == SCOPE_PERSONAL:
        candidates = [document.owner_id]
        from app.models.document import DocumentPermission

        perms = db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id,
                DocumentPermission.subject_type == "user",
            )
        ).all()
        for p in perms:
            candidates.append(p.subject_id)
        seen: set[uuid.UUID] = set()
        for uid in candidates:
            if uid in seen:
                continue
            seen.add(uid)
            user = db.get(User, uid)
            if not user:
                continue
            level = kb_level_for_user_on_document(db, user, document)
            rid = _ragflow_user_id(db, uid)
            if level and rid and grant_kb_user_permission(link.dataset_id, rid, level):
                granted += 1
        return granted

    granted += _grant_explicit_user_permissions(db, document, link.dataset_id)

    if scope in (SCOPE_DEPARTMENT, SCOPE_TEAM) and document.dept_id:
        granted += _sync_dept_kb_grants(
            db, document.dept_id, link.dataset_id, doc_scope=scope
        )
        return granted

    if scope == SCOPE_COMPANY:
        granted += _sync_company_kb_grants(db, link.dataset_id)

    return granted


def _sync_dept_kb_grants(
    db: Session,
    dept_id: uuid.UUID,
    dataset_id: str,
    *,
    doc_scope: str = SCOPE_DEPARTMENT,
) -> int:
    """部门/小组库授权：授予对应组织单元成员。"""
    granted = 0
    rows = db.scalars(
        select(UserDepartment.user_id).where(UserDepartment.dept_id == dept_id)
    ).all()
    for uid in rows:
        user = db.get(User, uid)
        if not user or user.status != "active":
            continue
        level = _dept_kb_level(db, user, dept_id, scope=doc_scope)
        if not level:
            continue
        rid = _ragflow_user_id(db, uid)
        if rid and grant_kb_user_permission(dataset_id, rid, level):
            granted += 1
    return granted


def _sync_company_kb_grants(db: Session, dataset_id: str) -> int:
    granted = 0
    users = db.scalars(select(User).where(User.status == "active")).all()
    for user in users:
        level = _company_kb_level(db, user)
        if not level:
            continue
        rid = _ragflow_user_id(db, user.id)
        if rid and grant_kb_user_permission(dataset_id, rid, level):
            granted += 1
    return granted


def _dept_kb_level(
    db: Session, user: User, dept_id: uuid.UUID, *, scope: str = SCOPE_DEPARTMENT
) -> str | None:
    if can_edit_in_scope(db, user, scope):
        return "write"
    if _user_has_queryable_doc_in_scope(db, user, scope, dept_id=dept_id):
        return "read"
    return None


def _company_kb_level(db: Session, user: User) -> str | None:
    if user_is_superuser(db, user):
        return "admin"
    if can_edit_in_scope(db, user, SCOPE_COMPANY):
        return "write"
    if _user_has_queryable_doc_in_scope(db, user, SCOPE_COMPANY):
        return "read"
    return None


def revoke_all_dept_kb_grants(db: Session, user: User) -> int:
    """删除用户或清空部门时：撤销其全部部门知识库授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0
    revoked = 0
    for reg in db.scalars(
        select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_DEPARTMENT)
    ).all():
        if revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1
    return revoked


def revoke_stale_dept_kb_grants(db: Session, user: User) -> int:
    """回收已不在所属部门的 KnowFlow 部门库授权（仅保留 user_dept_ids）。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0
    allowed = {str(d) for d in user_dept_ids(db, user.id)}
    revoked = 0
    for reg in db.scalars(select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_DEPARTMENT)).all():
        if reg.scope_key in allowed:
            continue
        if revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1
    return revoked


def reconcile_dept_membership_kb(
    db: Session,
    user: User,
    *,
    previous_dept_ids: list[uuid.UUID] | None = None,
) -> int:
    """部门成员变动：撤销离开部门的库权限，并刷新当前所属部门授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0

    current = {str(d) for d in user_dept_ids(db, user.id)}
    removed = set()
    if previous_dept_ids is not None:
        removed = {str(d) for d in previous_dept_ids} - current

    revoked = 0
    for dept_key in removed:
        reg = _get_registry(db, REG_DEPARTMENT, dept_key)
        if reg and revoke_kb_user_permission(reg.ragflow_dataset_id, link.ragflow_user_id):
            revoked += 1

    granted = 0
    for dept_id in user_dept_ids(db, user.id):
        reg = _get_registry(db, REG_DEPARTMENT, str(dept_id))
        if not reg:
            continue
        level = _dept_kb_level(db, user, dept_id)
        if level and grant_kb_user_permission(
            reg.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            granted += 1
    return revoked + granted


def sync_user_kb_grants(db: Session, user: User) -> int:
    """登录/进入知识问答：仅对本人所属部门/有公司权限的知识库授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0

    count = revoke_stale_dept_kb_grants(db, user)

    personal = _get_registry(db, REG_PERSONAL, str(user.id))
    if personal and grant_kb_user_permission(
        personal.ragflow_dataset_id, link.ragflow_user_id, "admin"
    ):
        count += 1

    from app.core.document_scope import scope_for_department

    for dept_id in user_dept_ids(db, user.id):
        tier = scope_for_department(db, dept_id)
        reg_scope = {
            SCOPE_TEAM: REG_TEAM,
            SCOPE_DEPARTMENT: REG_DEPARTMENT,
            SCOPE_COMPANY: REG_COMPANY,
        }.get(tier, REG_DEPARTMENT)
        reg = _get_registry(db, reg_scope, str(dept_id))
        if not reg:
            continue
        level = _dept_kb_level(db, user, dept_id, scope=tier)
        if level and grant_kb_user_permission(
            reg.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            count += 1

    from app.core.document_scope import library_companies_for_user

    for row in library_companies_for_user(db, user):
        company = _get_registry(db, REG_COMPANY, str(row["id"]))
        if not company:
            continue
        level = _company_kb_level(db, user)
        if level and grant_kb_user_permission(
            company.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            count += 1

    return count


def ensure_user_scope_datasets(db: Session, user: User, kf) -> None:
    """预创建用户相关的分级知识库（个人 + 部门/小组 + 公司）。"""
    from app.core.document_scope import (
        library_companies_for_user,
        scope_for_department,
    )

    ensure_scope_dataset(db, user, SCOPE_PERSONAL, str(user.id), kf)
    for dept_id in _dept_ids_for_kb_labels(db, user):
        ensure_scope_dataset(
            db, user, scope_for_department(db, dept_id), str(dept_id), kf
        )
    for row in library_companies_for_user(db, user):
        ensure_scope_dataset(db, user, SCOPE_COMPANY, str(row["id"]), kf)


def _dept_ids_for_kb_labels(db: Session, user: User) -> list[uuid.UUID]:
    """标签与重命名覆盖的部门范围（含公司级可见时的全部部门）。"""
    from app.models.org import Department

    ids = list(user_dept_ids(db, user.id))
    seen = set(ids)
    if user_is_superuser(db, user) or user_has_permission(db, user, "doc.read"):
        for dept_id in db.scalars(select(Department.id)).all():
            if dept_id not in seen:
                seen.add(dept_id)
                ids.append(dept_id)
    return ids


def dept_suffix_labels_for_theme(db: Session, user: User) -> dict[str, str]:
    """zt-dept-xxxxxx 后缀 → 部门展示名（供 KnowFlow 主题脚本兜底）。"""
    out: dict[str, str] = {}
    for dept_id in _dept_ids_for_kb_labels(db, user):
        suf = _id_suffix(dept_id)
        label = dataset_display_label_dept(db, dept_id)
        if label:
            out[suf] = label
    return out


def sync_all_kb_display_names(db: Session, kf) -> int:
    """将 RAGFlow 中仍显示 zt-dept-* 等旧名的知识库改为部门/公司展示名。"""
    rag = kf._rag
    try:
        datasets = rag.list_datasets()
    except Exception as e:
        logger.warning("列出知识库失败，跳过重命名: %s", e)
        return 0

    reg_by_id = {
        reg.ragflow_dataset_id: reg
        for reg in db.scalars(select(RagflowScopeDataset)).all()
    }
    renamed = 0
    for ds in datasets:
        ds_id = str(ds.get("id") or "")
        name = (ds.get("name") or "").strip()
        if not ds_id or not name:
            continue
        target: str | None = None
        reg = reg_by_id.get(ds_id)
        if reg:
            try:
                key = uuid.UUID(reg.scope_key)
            except ValueError:
                key = None
            if reg.scope in (REG_DEPARTMENT, REG_TEAM) and key:
                target = dataset_name_for_dept(key, db)
            elif reg.scope == REG_PERSONAL and key:
                target = dataset_name_for_personal(key, db)
            elif reg.scope == REG_COMPANY:
                target = dataset_name_for_company()
        else:
            dept_id = dept_id_from_dataset_name(db, name)
            if dept_id:
                target = dataset_name_for_dept(dept_id, db)
        if target and name != target:
            _align_dataset_display_name(rag, ds_id, target)
            renamed += 1
    return renamed


def knowflow_kb_labels_for_user(db: Session, user: User) -> list[dict[str, str]]:
    """供前端 / KnowFlow 主题展示：技术库名 → 部门名/用户名（查询仍用 scope_key UUID）。"""
    labels: list[dict[str, str]] = []
    seen_names: set[str] = set()

    company_label = dataset_display_label_company()
    company_name = dataset_name_for_company()
    _append_kb_label(labels, seen_names, company_name, company_label)
    _append_kb_label(labels, seen_names, legacy_dataset_name_for_company(), company_label)

    for dept_id in _dept_ids_for_kb_labels(db, user):
        dept_label = dataset_display_label_dept(db, dept_id)
        _append_kb_label(
            labels, seen_names, dataset_name_for_dept(dept_id, db), dept_label
        )
        _append_kb_label(
            labels, seen_names, legacy_dataset_name_for_dept(dept_id), dept_label
        )

    try:
        from app.integrations.knowflow_client import get_knowflow_client_for_user

        kf = get_knowflow_client_for_user(db, user)
        if kf.enabled():
            for ds in kf._rag.list_datasets():
                technical = (ds.get("name") or "").strip()
                ds_id = str(ds.get("id") or "")
                if not technical:
                    continue
                reg = None
                if ds_id:
                    reg = db.scalar(
                        select(RagflowScopeDataset).where(
                            RagflowScopeDataset.ragflow_dataset_id == ds_id
                        )
                    )
                label: str | None = None
                if reg:
                    try:
                        key = uuid.UUID(reg.scope_key)
                    except ValueError:
                        key = None
                    if reg.scope == REG_DEPARTMENT and key:
                        label = dataset_display_label_dept(db, key)
                    elif reg.scope == REG_PERSONAL and key:
                        label = dataset_display_label_personal(db, key)
                    elif reg.scope == REG_COMPANY:
                        label = dataset_display_label_company()
                if not label:
                    dept_id = dept_id_from_dataset_name(db, technical)
                    if dept_id:
                        label = dataset_display_label_dept(db, dept_id)
                if label:
                    _append_kb_label(labels, seen_names, technical, label)
    except Exception as e:
        logger.debug("从 KnowFlow 列出知识库标签跳过: %s", e)

    personal_label = dataset_display_label_personal(db, user.id)
    _append_kb_label(
        labels, seen_names, dataset_name_for_personal(user.id, db), personal_label
    )
    _append_kb_label(
        labels, seen_names, legacy_dataset_name_for_personal(user.id), personal_label
    )
    _append_kb_label(
        labels,
        seen_names,
        legacy_dataset_name_for_platform_user(user.id),
        personal_label,
    )

    return labels
