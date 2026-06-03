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
from app.core.permissions import PermissionLevel, user_dept_ids, user_is_superuser
from app.config import get_settings
from app.core.user_department import user_department_id
from app.integrations.ragflow_client import RagflowClient
from app.integrations.ragflow_kb_acl import grant_kb_user_permission, revoke_kb_user_permission
from app.integrations.ragflow_rbac import sync_ragflow_global_admin_role
from app.models.document import Document
from app.models.org import Department, User, UserDepartment
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


def scope_key_for_document(db: Session, document: Document) -> str:
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


def _user_has_personal_kb(db: Session, user: User) -> bool:
    """用户是否已在平台登记且位于其 mapped 租户内的个人知识库。"""
    reg = _get_registry(db, REG_PERSONAL, str(user.id))
    if not reg or not (reg.ragflow_dataset_id or "").strip():
        return False
    return _personal_dataset_in_user_tenant(db, user, reg.ragflow_dataset_id)


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


def _privileged_rag_client(db: Session) -> RagflowClient | None:
    """列举/匹配全员知识库：优先 API Key，否则 bootstrap 管理员 RAGFlow 会话。"""
    client = _admin_rag_client()
    if client:
        return client
    from app.core.phone import bootstrap_login_id
    from app.services.ragflow_identity_service import get_user_ragflow_auth

    bootstrap = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    if not bootstrap:
        return None
    get_or_create_link(db, bootstrap)
    auth = get_user_ragflow_auth(db, bootstrap)
    if not auth:
        return None
    return RagflowClient(session_auth=auth)


def _all_knowflow_dataset_ids(db: Session) -> set[str]:
    """KnowFlow 侧已存在的全部知识库 id（注册表 + 特权列举）。"""
    ids = _all_registered_dataset_ids(db)
    priv = _privileged_rag_client(db)
    if not priv:
        return ids
    try:
        for ds in priv.list_datasets():
            ds_id = str(ds.get("id") or "").strip()
            if ds_id:
                ids.add(ds_id)
    except Exception as e:
        logger.warning("特权列举 KnowFlow 知识库失败: %s", e)
    return ids


def _user_knowflow_client(db: Session, user: User):
    from app.integrations.knowflow_client import get_knowflow_client_for_user

    return get_knowflow_client_for_user(db, user)


def _personal_dataset_in_user_tenant(db: Session, user: User, ds_id: str) -> bool:
    """个人库对该用户可访问（mapped 下为 bootstrap 租户 + ACL 授权）。"""
    ds = (ds_id or "").strip()
    if not ds:
        return False
    user_kf = _user_knowflow_client(db, user)
    if not user_kf.enabled():
        return False
    return ds in _visible_dataset_ids(user_kf)


def _resolve_personal_dataset_id(db: Session, user: User, kf=None) -> str | None:
    """个人库 id：注册表 → 按名匹配（mapped 下在 bootstrap 租户）。"""
    user_kf = _user_knowflow_client(db, user)

    reg = _get_registry(db, REG_PERSONAL, str(user.id))
    if reg and (reg.ragflow_dataset_id or "").strip():
        ds_id = reg.ragflow_dataset_id.strip()
        if _personal_dataset_in_user_tenant(db, user, ds_id):
            return ds_id
        db.delete(reg)
        db.flush()

    names = list(
        dict.fromkeys(
            n
            for n in (
                dataset_name_for_personal(user.id, db),
                legacy_dataset_name_for_personal(user.id),
                legacy_dataset_name_for_platform_user(user.id),
                dataset_display_label_personal(db, user.id),
            )
            if n
        )
    )
    found = None
    search_rag = None
    if _is_mapped_account_mode():
        search_rag = _privileged_rag_client(db)
    elif user_kf.enabled():
        search_rag = user_kf._rag
    if search_rag:
        found = search_rag.find_dataset_by_names(names)
    if not found or not found.get("id"):
        return None

    ds_id = str(found["id"]).strip()
    owner_rid = _ragflow_user_id(db, user.id)
    if owner_rid:
        grant_kb_user_permission(ds_id, owner_rid, "admin")
    if not _personal_dataset_in_user_tenant(db, user, ds_id):
        return None

    db.add(
        RagflowScopeDataset(
            scope=REG_PERSONAL,
            scope_key=str(user.id),
            ragflow_dataset_id=ds_id,
            owner_ragflow_user_id=owner_rid,
        )
    )
    db.flush()
    return ds_id


def _finalize_personal_dataset_acl(
    db: Session,
    user: User,
    dataset_id: str,
    owner_ragflow_user_id: str | None,
    rag: RagflowClient | None,
) -> None:
    ds_id = (dataset_id or "").strip()
    rid = (owner_ragflow_user_id or _ragflow_user_id(db, user.id) or "").strip()
    if not ds_id or not rid:
        return
    if rag is not None:
        try:
            perm = "team" if _is_mapped_account_mode() else "me"
            rag.update_dataset_permission(ds_id, perm)
        except Exception as e:
            logger.debug("个人库 permission 设置跳过: %s", e)
    grant_kb_user_permission(ds_id, rid, "admin")


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


def _dept_ids_for_kb_access(db: Session, user: User) -> list[uuid.UUID]:
    """用户可见的部门链：所属部门及其上级（不含同级/下级其他部门）。"""
    if user_is_superuser(db, user):
        return list(db.scalars(select(Department.id)).all())

    dept_id = user_department_id(db, user.id)
    if not dept_id:
        return []

    ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    current = db.get(Department, dept_id)
    while current:
        if current.id not in seen:
            seen.add(current.id)
            ids.append(current.id)
        if not current.parent_id:
            break
        current = db.get(Department, current.parent_id)
    return ids


def _registry_scope_for_dept(db: Session, dept_id: uuid.UUID) -> str:
    from app.core.document_scope import scope_for_department

    tier = scope_for_department(db, dept_id)
    return {
        SCOPE_TEAM: REG_TEAM,
        SCOPE_DEPARTMENT: REG_DEPARTMENT,
        SCOPE_COMPANY: REG_COMPANY,
    }.get(tier, REG_DEPARTMENT)


def _registry_for_dataset_id(
    db: Session, dataset_id: str
) -> RagflowScopeDataset | None:
    ds = (dataset_id or "").strip()
    if not ds:
        return None
    return db.scalar(
        select(RagflowScopeDataset).where(
            RagflowScopeDataset.ragflow_dataset_id == ds
        )
    )


def _is_other_users_personal_dataset(db: Session, user: User, dataset_id: str) -> bool:
    reg = _registry_for_dataset_id(db, dataset_id)
    if not reg or reg.scope != REG_PERSONAL:
        return False
    return reg.scope_key != str(user.id)


def _dataset_ids_for_explicit_shares(db: Session, user: User) -> set[str]:
    """显式分享给当前用户、且已同步到 KnowFlow 的文档所在知识库。"""
    from app.models.document import Document, DocumentPermission, DocumentStatus
    from app.models.ragflow_document_link import RagflowDocumentLink

    if user_is_superuser(db, user):
        return set()

    rows = db.execute(
        select(
            RagflowDocumentLink.dataset_id,
            RagflowDocumentLink.platform_document_id,
        )
        .join(Document, RagflowDocumentLink.platform_document_id == Document.id)
        .join(
            DocumentPermission,
            (DocumentPermission.document_id == Document.id)
            & (DocumentPermission.subject_type == "user")
            & (DocumentPermission.subject_id == user.id),
        )
        .where(
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.active.value,
            RagflowDocumentLink.dataset_id.isnot(None),
        )
    ).all()
    out: set[str] = set()
    for ds_id, platform_doc_id in rows:
        ds = (ds_id or "").strip()
        if not ds:
            continue
        doc = db.get(Document, platform_doc_id)
        if doc and can_query_document(db, user, doc):
            out.add(ds)
    return out


def _dataset_ids_for_explicit_non_personal_shares(
    db: Session, user: User
) -> set[str]:
    """兼容旧名：显式分享库（不含他人个人库）。"""
    return {
        ds_id
        for ds_id in _dataset_ids_for_explicit_shares(db, user)
        if not _is_other_users_personal_dataset(db, user, ds_id)
    }


def _user_has_queryable_share_in_personal_kb(
    db: Session, user: User, owner_user_id: uuid.UUID
) -> bool:
    """当前用户是否被显式分享了该用户个人库中的至少一篇文档。"""
    from app.models.document import Document, DocumentPermission, DocumentStatus

    row = db.scalar(
        select(Document.id)
        .join(
            DocumentPermission,
            (DocumentPermission.document_id == Document.id)
            & (DocumentPermission.subject_type == "user")
            & (DocumentPermission.subject_id == user.id),
        )
        .where(
            Document.owner_id == owner_user_id,
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.active.value,
        )
        .limit(1)
    )
    if not row:
        return False
    doc = db.get(Document, row)
    return bool(doc and can_query_document(db, user, doc))


def _all_registered_dataset_ids(db: Session) -> set[str]:
    return {
        (reg.ragflow_dataset_id or "").strip()
        for reg in db.scalars(select(RagflowScopeDataset)).all()
        if (reg.ragflow_dataset_id or "").strip()
    }


def allowed_dataset_ids_for_user(db: Session, user: User) -> set[str]:
    """平台规则下用户应能访问的分级知识库 id。

    普通用户：个人库 + 所属部门链（本部门及上级至根节点）+ 显式分享；
    不含他人个人库、不含部门链外的公司/部门库。
    """
    if user_is_superuser(db, user):
        return _all_registered_dataset_ids(db)

    allowed: set[str] = set()

    if _user_has_personal_kb(db, user):
        personal = _get_registry(db, REG_PERSONAL, str(user.id))
        if personal and personal.ragflow_dataset_id:
            allowed.add(personal.ragflow_dataset_id)

    for dept_id in _dept_ids_for_kb_access(db, user):
        reg = _get_registry(db, _registry_scope_for_dept(db, dept_id), str(dept_id))
        if reg and reg.ragflow_dataset_id:
            allowed.add(reg.ragflow_dataset_id)

    allowed.update(_dataset_ids_for_explicit_non_personal_shares(db, user))
    return allowed


def _revoke_candidate_dataset_ids(db: Session, user: User, kf) -> set[str]:
    """待检查撤销的知识库：注册表 + 该用户在 RAGFlow 侧仍可见的库。"""
    candidates: set[str] = set()
    for reg in db.scalars(select(RagflowScopeDataset)).all():
        ds_id = (reg.ragflow_dataset_id or "").strip()
        if ds_id:
            candidates.add(ds_id)
    if kf is not None and kf.enabled():
        candidates.update(_visible_dataset_ids(kf))
    return candidates


def visible_dataset_ids_for_user(db: Session, user: User, kf) -> set[str]:
    """RAGFlow 列表与平台 ACL 交集，防止全局 admin 泄露他人知识库。"""
    allowed = allowed_dataset_ids_for_user(db, user)
    if user_is_superuser(db, user):
        listed = _visible_dataset_ids(kf)
        return listed if listed else allowed
    listed = _visible_dataset_ids(kf)
    if not listed:
        return allowed
    return listed & allowed


def revoke_other_users_personal_kb_grants(db: Session, user: User) -> int:
    """强制撤销对他人个人知识库的授权（个人库不可整库共享）。"""
    if user_is_superuser(db, user):
        return 0
    link = get_or_create_link(db, user)
    rid = (link.ragflow_user_id or "").strip()
    if not rid:
        return 0
    revoked = 0
    for reg in db.scalars(
        select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_PERSONAL)
    ).all():
        if reg.scope_key == str(user.id):
            continue
        ds_id = (reg.ragflow_dataset_id or "").strip()
        if not ds_id:
            continue
        if revoke_kb_user_permission(ds_id, rid):
            revoked += 1
            logger.info(
                "已撤销用户 %s 对他人个人库 %s 的 KnowFlow 授权",
                user.username,
                ds_id,
            )
    return revoked


def revoke_unauthorized_kb_grants(
    db: Session, user: User, kf=None
) -> int:
    """撤销用户对他人个人库/非所属部门库的 KnowFlow 授权。"""
    if user_is_superuser(db, user):
        return 0
    link = get_or_create_link(db, user)
    rid = (link.ragflow_user_id or "").strip()
    if not rid:
        return 0

    allowed = allowed_dataset_ids_for_user(db, user)
    revoked = 0
    for ds_id in _revoke_candidate_dataset_ids(db, user, kf):
        if ds_id in allowed:
            continue
        if revoke_kb_user_permission(ds_id, rid):
            revoked += 1
    return revoked


def _should_grant_ragflow_global_admin(db: Session, user: User) -> bool:
    """mapped 下普通用户需租户内 admin 才能创建个人库；可见性仍由租户隔离 + KB ACL 约束。"""
    settings = get_settings()
    mode = (settings.ragflow_account_mode or "").strip().lower()
    if user_is_superuser(db, user):
        return True
    if mode == "mapped":
        return True
    if mode == "shared" and settings.ragflow_grant_global_admin:
        return True
    return False


def ensure_user_kb_create_permission(db: Session, user: User) -> bool:
    """确保用户在自有租户内可创建个人知识库。"""
    if not _should_grant_ragflow_global_admin(db, user):
        return False
    link = get_or_create_link(db, user)
    rid = (link.ragflow_user_id or "").strip()
    if not rid:
        return False
    from app.integrations.ragflow_rbac import ensure_ragflow_global_admin

    return ensure_ragflow_global_admin(rid)


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


def _is_mapped_account_mode() -> bool:
    return (get_settings().ragflow_account_mode or "").strip().lower() == "mapped"


def _provision_rag_for_scope(db: Session, actor: User, scope: str, kf) -> RagflowClient | None:
    """分级库建库/匹配：mapped 下个人/部门/公司库均在 bootstrap 租户，再对用户 ACL 授权。"""
    if _is_mapped_account_mode():
        priv = _privileged_rag_client(db)
        if priv:
            return priv
    if scope == SCOPE_PERSONAL:
        user_kf = _user_knowflow_client(db, actor)
        return user_kf._rag if user_kf.enabled() else None
    if scope != SCOPE_PERSONAL and _is_mapped_account_mode():
        priv = _privileged_rag_client(db)
        if priv:
            return priv
    user_rag = kf._rag if kf is not None and kf.enabled() else None
    if not _can_create_scope_dataset(db, actor, scope):
        return _privileged_rag_client(db)
    return user_rag


def repair_stale_scope_registries(db: Session, kf) -> int:
    """删除 KnowFlow 中已不存在、但注册表仍指向的旧知识库记录。"""
    existing_ids = _all_knowflow_dataset_ids(db)
    if not existing_ids:
        return 0
    removed = 0
    for reg in list(db.scalars(select(RagflowScopeDataset)).all()):
        if reg.ragflow_dataset_id in existing_ids:
            continue
        db.delete(reg)
        removed += 1
    if removed:
        db.flush()
    return removed


def repair_orphan_scope_registries(db: Session, kf) -> int:
    """清理指向已删除组织/用户、或 KnowFlow 侧名为「部门」等占位符的脏注册表。"""
    from app.models.org import Department, User

    names_by_id: dict[str, str] = {}
    rag = kf._rag if kf is not None and kf.enabled() else None
    if rag:
        try:
            for ds in rag.list_datasets():
                ds_id = str(ds.get("id") or "").strip()
                if ds_id:
                    names_by_id[ds_id] = (ds.get("name") or "").strip()
        except Exception as e:
            logger.warning("列举知识库失败，跳过 orphan registry 清理: %s", e)

    removed = 0
    for reg in list(db.scalars(select(RagflowScopeDataset)).all()):
        stale = False
        try:
            key = uuid.UUID(reg.scope_key)
        except ValueError:
            key = None
        if reg.scope in (REG_DEPARTMENT, REG_TEAM) and key and not db.get(Department, key):
            stale = True
        if reg.scope == REG_PERSONAL and key and not db.get(User, key):
            stale = True
        ds_id = (reg.ragflow_dataset_id or "").strip()
        if ds_id and names_by_id.get(ds_id, "") in GENERIC_ORPHAN_KB_NAMES:
            stale = True
        if not stale:
            continue
        db.delete(reg)
        removed += 1
        if ds_id and rag:
            try:
                rag.delete_dataset(ds_id)
            except Exception as e:
                logger.debug("删除 orphan 知识库 %s 跳过: %s", ds_id, e)
                _delete_knowledgebase_mysql(ds_id)
    if removed:
        db.flush()
    return removed


def _alias_names_for_registry(db: Session, reg: RagflowScopeDataset) -> set[str]:
    names: set[str] = set()
    scope_map = {
        REG_PERSONAL: SCOPE_PERSONAL,
        REG_DEPARTMENT: SCOPE_DEPARTMENT,
        REG_TEAM: SCOPE_TEAM,
        REG_COMPANY: SCOPE_COMPANY,
    }
    doc_scope = scope_map.get(reg.scope, SCOPE_PERSONAL)
    names.update(legacy_scope_dataset_names(doc_scope, reg.scope_key))
    try:
        key_uuid = uuid.UUID(reg.scope_key)
    except ValueError:
        key_uuid = None
    if reg.scope == REG_PERSONAL and key_uuid:
        names.add(dataset_name_for_personal(key_uuid, db))
        names.add(dataset_display_label_personal(db, key_uuid))
        names.add(legacy_dataset_name_for_platform_user(key_uuid))
    elif reg.scope in (REG_DEPARTMENT, REG_TEAM) and key_uuid:
        names.add(dataset_name_for_dept(key_uuid, db))
        names.add(dataset_display_label_dept(db, key_uuid))
    elif reg.scope == REG_COMPANY:
        names.add(dataset_name_for_company())
        names.add(dataset_display_label_company())
        names.add(legacy_dataset_name_for_company())
    return {n for n in names if n}


def _scope_registries_for_user(db: Session, user: User) -> list[RagflowScopeDataset]:
    if user_is_superuser(db, user):
        return list(db.scalars(select(RagflowScopeDataset)).all())

    regs: list[RagflowScopeDataset] = []
    personal = _get_registry(db, REG_PERSONAL, str(user.id))
    if personal and (personal.ragflow_dataset_id or "").strip():
        if _personal_dataset_in_user_tenant(db, user, personal.ragflow_dataset_id):
            regs.append(personal)
    for dept_id in _dept_ids_for_kb_access(db, user):
        reg = _get_registry(db, _registry_scope_for_dept(db, dept_id), str(dept_id))
        if reg:
            regs.append(reg)
    return regs


def dedupe_orphan_scope_datasets(db: Session, user: User, kf) -> int:
    """删除重复/历史分级知识库（同名文件夹、旧账号遗留库）。"""
    if not kf.enabled():
        return 0
    rag = kf._rag
    try:
        datasets = rag.list_datasets()
    except Exception as e:
        logger.warning("列出知识库失败，跳过重复库清理: %s", e)
        return 0

    regs = _scope_registries_for_user(db, user)
    registered_ids = {
        (reg.ragflow_dataset_id or "").strip()
        for reg in regs
        if reg.ragflow_dataset_id
    }
    alias_names: set[str] = set()
    for reg in regs:
        alias_names.update(_alias_names_for_registry(db, reg))

    by_name: dict[str, list[str]] = {}
    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip()
        name = (ds.get("name") or "").strip()
        if not ds_id or not name:
            continue
        by_name.setdefault(name, []).append(ds_id)

    to_delete: set[str] = set()
    for name, ids in by_name.items():
        if len(ids) <= 1:
            continue
        keep = next((ds_id for ds_id in ids if ds_id in registered_ids), None)
        if keep:
            for ds_id in ids:
                if ds_id != keep:
                    to_delete.add(ds_id)

    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip()
        name = (ds.get("name") or "").strip()
        if not ds_id or ds_id in registered_ids or ds_id in to_delete:
            continue
        if name in alias_names:
            to_delete.add(ds_id)

    removed = 0
    for ds_id in to_delete:
        try:
            rag.delete_dataset(ds_id)
            removed += 1
            logger.info("已清理重复知识库 user=%s id=%s", user.username, ds_id)
        except Exception as e:
            logger.warning("清理重复知识库失败 user=%s id=%s: %s", user.username, ds_id, e)
    if removed:
        db.flush()
    return removed


GENERIC_ORPHAN_KB_NAMES = frozenset({"部门", "分享对象"})


def _list_knowledgebases_mysql() -> list[tuple[str, str]]:
    from app.integrations.ragflow_llm_template import _mysql_query

    try:
        raw = _mysql_query("SELECT CONCAT(id, '\t', IFNULL(name,'')) FROM knowledgebase")
    except Exception as e:
        logger.warning("MySQL 列举 knowledgebase 失败: %s", e)
        return []
    out: list[tuple[str, str]] = []
    for line in raw:
        parts = line.split("\t", 1)
        if parts and parts[0]:
            out.append((parts[0].strip(), (parts[1] if len(parts) > 1 else "").strip()))
    return out


def _delete_knowledgebase_mysql(kb_id: str) -> bool:
    from app.integrations.ragflow_llm_template import _mysql_exec, _sql_literal

    safe = _sql_literal(kb_id.strip())
    sql = f"""
DELETE cc FROM child_chunk cc
INNER JOIN document d ON cc.doc_id = d.id
WHERE d.kb_id = '{safe}';
DELETE pc FROM parent_chunk pc
INNER JOIN document d ON pc.doc_id = d.id
WHERE d.kb_id = '{safe}';
DELETE fd FROM file2document fd
INNER JOIN document d ON fd.document_id = d.id
WHERE d.kb_id = '{safe}';
DELETE FROM document WHERE kb_id = '{safe}';
DELETE FROM knowledgebase WHERE id = '{safe}';
"""
    ok = _mysql_exec(sql)
    if ok:
        logger.info("已通过 MySQL 删除知识库 id=%s", kb_id)
    return ok


def purge_unregistered_knowledge_bases(db: Session, kf=None) -> int:
    """删除 KnowFlow 中未在平台登记的分级库（重复个人库、误建「部门」库等）。"""
    if kf is None or not kf.enabled():
        from app.core.phone import bootstrap_login_id
        from app.integrations.knowflow_client import get_knowflow_client_for_catalog
        from app.models.org import User

        bootstrap = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
        if not bootstrap:
            return 0
        kf = get_knowflow_client_for_catalog(db, bootstrap)
    if not kf.enabled():
        return 0

    registered_ids = {
        (reg.ragflow_dataset_id or "").strip()
        for reg in db.scalars(select(RagflowScopeDataset)).all()
        if reg.ragflow_dataset_id
    }
    registered_names: set[str] = set()
    for reg in db.scalars(select(RagflowScopeDataset)).all():
        registered_names.update(_alias_names_for_registry(db, reg))

    rag = kf._rag
    api_datasets: list[dict] = []
    try:
        api_datasets = rag.list_datasets()
    except Exception as e:
        logger.warning("API 列举知识库失败，将使用 MySQL 对账: %s", e)

    mysql_kbs = _list_knowledgebases_mysql()
    if not api_datasets and not mysql_kbs:
        return 0

    names_by_id: dict[str, str] = {}
    for ds in api_datasets:
        ds_id = str(ds.get("id") or "").strip()
        if ds_id:
            names_by_id[ds_id] = (ds.get("name") or "").strip()
    for ds_id, name in mysql_kbs:
        names_by_id.setdefault(ds_id, name)

    to_delete: set[str] = set()
    for ds_id, name in names_by_id.items():
        if not ds_id or ds_id in registered_ids:
            continue
        if name in GENERIC_ORPHAN_KB_NAMES or name in registered_names:
            to_delete.add(ds_id)
            continue
        to_delete.add(ds_id)

    removed = 0
    for ds_id in to_delete:
        name = names_by_id.get(ds_id, ds_id)
        deleted = False
        try:
            rag.delete_dataset(ds_id)
            deleted = True
        except Exception as e:
            logger.warning("API 删除未登记知识库失败 id=%s: %s", ds_id, e)
            deleted = _delete_knowledgebase_mysql(ds_id)
        if deleted:
            removed += 1
            logger.info("已清理未登记知识库 name=%s id=%s", name, ds_id)
    if removed:
        db.flush()
    return removed


def purge_orphan_kbs_for_user_tenant(db: Session, user: User) -> int:
    """清理用户 mapped 租户内未登记、误建的「部门」等孤立知识库。"""
    user_kf = _user_knowflow_client(db, user)
    if not user_kf.enabled():
        return 0

    registered_ids = _all_registered_dataset_ids(db)
    rag = user_kf._rag
    try:
        datasets = rag.list_datasets()
    except Exception as e:
        logger.warning("列举用户租户知识库失败 user=%s: %s", user.username, e)
        return 0

    to_delete: set[str] = set()
    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip()
        name = (ds.get("name") or "").strip()
        if not ds_id or ds_id in registered_ids:
            continue
        if name in GENERIC_ORPHAN_KB_NAMES:
            to_delete.add(ds_id)

    removed = 0
    for ds_id in to_delete:
        name = next(
            (str(ds.get("name") or "") for ds in datasets if str(ds.get("id")) == ds_id),
            ds_id,
        )
        try:
            rag.delete_dataset(ds_id)
            removed += 1
            logger.info(
                "已清理用户租户孤立知识库 user=%s name=%s id=%s",
                user.username,
                name,
                ds_id,
            )
        except Exception as e:
            logger.warning(
                "清理用户租户孤立知识库失败 user=%s id=%s: %s",
                user.username,
                ds_id,
                e,
            )
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

    owner_ragflow_user_id: str | None = None
    if scope == SCOPE_PERSONAL:
        try:
            owner_uid = uuid.UUID(scope_key)
            owner_user = db.get(User, owner_uid)
            if owner_user:
                owner_link = get_or_create_link(db, owner_user)
                owner_ragflow_user_id = (owner_link.ragflow_user_id or "").strip() or None
        except ValueError:
            pass

    existing = _get_registry(db, reg_scope, scope_key)
    if existing and (existing.ragflow_dataset_id or "").strip():
        ds_id = existing.ragflow_dataset_id.strip()
        if scope == SCOPE_PERSONAL:
            if not _personal_dataset_in_user_tenant(db, actor, ds_id):
                db.delete(existing)
                db.flush()
            else:
                rag = _provision_rag_for_scope(db, actor, scope, kf)
                if rag:
                    _align_dataset_display_name(rag, ds_id, name)
                    _finalize_personal_dataset_acl(
                        db, actor, ds_id, owner_ragflow_user_id, rag
                    )
                return ds_id
        elif ds_id in _all_knowflow_dataset_ids(db):
            rag = _provision_rag_for_scope(db, actor, scope, kf) or kf._rag
            _align_dataset_display_name(rag, ds_id, name)
            return ds_id
        else:
            db.delete(existing)
            db.flush()
    if scope == SCOPE_PERSONAL and not owner_ragflow_user_id:
        link = get_or_create_link(db, actor)
        owner_ragflow_user_id = (link.ragflow_user_id or "").strip() or None
    rag = _provision_rag_for_scope(db, actor, scope, kf)
    if not rag:
        logger.info(
            "用户 %s 无法为 %s 知识库获取 KnowFlow 会话",
            actor.username,
            scope,
        )
        return None
    if not owner_ragflow_user_id:
        link = get_or_create_link(db, actor)
        owner_ragflow_user_id = (link.ragflow_user_id or "").strip() or None

    found = rag.find_dataset_by_names(lookup_names)
    if found and found.get("id"):
        ds_id = str(found["id"])
        _align_dataset_display_name(rag, ds_id, name)
        if scope == SCOPE_PERSONAL:
            _finalize_personal_dataset_acl(
                db, actor, ds_id, owner_ragflow_user_id, rag
            )
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
        perm = "team" if scope == SCOPE_PERSONAL and _is_mapped_account_mode() else (
            "me" if scope == SCOPE_PERSONAL else "team"
        )
        ds_id = rag.ensure_dataset(name, permission=perm)
    except Exception as e:
        if _kb_permission_denied(e):
            if scope == SCOPE_PERSONAL:
                fallback = _privileged_rag_client(db)
                if fallback and fallback is not rag:
                    try:
                        perm = "team" if _is_mapped_account_mode() else "me"
                        ds_id = fallback.ensure_dataset(name, permission=perm)
                        rag = fallback
                    except Exception as e2:
                        logger.warning("创建个人知识库 %s 失败（特权会话）: %s", name, e2)
                        return None
                else:
                    logger.warning("创建个人知识库 %s 失败: %s", name, e)
                    return None
            else:
                fallback = _privileged_rag_client(db)
                if fallback and fallback is not rag:
                    try:
                        ds_id = fallback.ensure_dataset(name, permission=perm)
                        rag = fallback
                    except Exception as e2:
                        logger.warning("创建知识库 %s 失败（特权会话）: %s", name, e2)
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
    if scope == SCOPE_PERSONAL:
        _finalize_personal_dataset_acl(
            db, actor, ds_id, owner_ragflow_user_id, rag
        )
    return ds_id


def resolve_dataset_for_document(db: Session, actor: User, document: Document, kf) -> str | None:
    scope = _document_scope(db, document)
    key = scope_key_for_document(db, document)
    provision = actor
    if scope == SCOPE_PERSONAL:
        owner = db.get(User, document.owner_id)
        if owner:
            provision = owner
            from app.integrations.knowflow_client import get_knowflow_client_for_user

            kf = get_knowflow_client_for_user(db, owner)
    return ensure_scope_dataset(db, provision, scope, key, kf)


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


def _revoke_explicit_share_kb_grants_on_canonical(
    db: Session, document: Document, dataset_id: str
) -> int:
    """显式分享走接收者个人库镜像，撤销对 canonical 库的整库误授权。"""
    from app.models.document import DocumentPermission

    revoked = 0
    for uid in db.scalars(
        select(DocumentPermission.subject_id).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.subject_type == "user",
        )
    ).all():
        if uid == document.owner_id:
            continue
        rid = _ragflow_user_id(db, uid)
        if rid and revoke_kb_user_permission(dataset_id, rid):
            revoked += 1
    return revoked


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
        owner = db.get(User, document.owner_id)
        if not owner:
            return 0
        level = kb_level_for_user_on_document(db, owner, document)
        rid = _ragflow_user_id(db, owner.id)
        if level and rid and grant_kb_user_permission(link.dataset_id, rid, level):
            granted += 1
        granted += _revoke_explicit_share_kb_grants_on_canonical(
            db, document, link.dataset_id
        )
        from app.services.ragflow_sync_service import sync_document_mirrors_for_shares

        granted += sync_document_mirrors_for_shares(db, document)
        return granted

    granted += _revoke_explicit_share_kb_grants_on_canonical(
        db, document, link.dataset_id
    )

    if scope in (SCOPE_DEPARTMENT, SCOPE_TEAM) and document.dept_id:
        granted += _sync_dept_kb_grants(
            db, document.dept_id, link.dataset_id, doc_scope=scope
        )
        from app.services.ragflow_sync_service import sync_document_mirrors_for_shares

        granted += sync_document_mirrors_for_shares(db, document)
        return granted

    if scope == SCOPE_COMPANY:
        granted += _sync_company_kb_grants(db, link.dataset_id)

    from app.services.ragflow_sync_service import sync_document_mirrors_for_shares

    granted += sync_document_mirrors_for_shares(db, document)
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
    allowed = {str(d) for d in _dept_ids_for_kb_access(db, user)}
    revoked = 0
    for reg in db.scalars(
        select(RagflowScopeDataset).where(
            RagflowScopeDataset.scope.in_((REG_DEPARTMENT, REG_TEAM))
        )
    ).all():
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


def enforce_personal_kb_private_for_user(db: Session, user: User, kf) -> int:
    """个人库强制 permission=me，避免同团队租户内全员可见。"""
    reg = _get_registry(db, REG_PERSONAL, str(user.id))
    if not reg or not reg.ragflow_dataset_id or not kf.enabled():
        return 0
    try:
        kf._rag.update_dataset_permission(reg.ragflow_dataset_id, "me")
        return 1
    except Exception as e:
        logger.warning(
            "个人库设为 private 失败 user=%s kb=%s: %s",
            user.username,
            reg.ragflow_dataset_id,
            e,
        )
        return 0


def enforce_all_registered_personal_kbs_private(db: Session) -> int:
    """管理员 API：将所有已登记的个人库改为 me（修复历史 team 可见）。"""
    admin = _admin_rag_client()
    if not admin:
        return 0
    updated = 0
    for reg in db.scalars(
        select(RagflowScopeDataset).where(RagflowScopeDataset.scope == REG_PERSONAL)
    ).all():
        ds_id = (reg.ragflow_dataset_id or "").strip()
        if not ds_id:
            continue
        try:
            admin.update_dataset_permission(ds_id, "me")
            updated += 1
        except Exception as e:
            logger.warning("管理员锁定个人库 %s 失败: %s", ds_id, e)
    return updated


def sync_user_kb_grants(db: Session, user: User, kf=None) -> int:
    """登录/进入知识问答：仅对本人个人库、所属部门链与公司权限库授权。"""
    link = get_or_create_link(db, user)
    if not link.ragflow_user_id:
        return 0

    user_kf = _user_knowflow_client(db, user)
    acl_kf = user_kf if user_kf.enabled() else kf

    sync_ragflow_global_admin_role(
        link.ragflow_user_id,
        grant=_should_grant_ragflow_global_admin(db, user),
    )

    if user_kf.enabled():
        enforce_personal_kb_private_for_user(db, user, user_kf)

    count = revoke_unauthorized_kb_grants(db, user, kf=acl_kf)
    count += revoke_stale_dept_kb_grants(db, user)
    count += revoke_other_users_personal_kb_grants(db, user)

    if user_is_superuser(db, user):
        for ds_id in _all_knowflow_dataset_ids(db):
            if grant_kb_user_permission(ds_id, link.ragflow_user_id, "admin"):
                count += 1
        return count

    personal_ds = _resolve_personal_dataset_id(db, user)
    if personal_ds and grant_kb_user_permission(
        personal_ds, link.ragflow_user_id, "admin"
    ):
        count += 1

    from app.core.document_scope import scope_for_department

    for dept_id in _dept_ids_for_kb_access(db, user):
        tier = scope_for_department(db, dept_id)
        reg_scope = _registry_scope_for_dept(db, dept_id)
        reg = _get_registry(db, reg_scope, str(dept_id))
        if not reg:
            continue
        level = _dept_kb_level(db, user, dept_id, scope=tier) or "read"
        if grant_kb_user_permission(
            reg.ragflow_dataset_id, link.ragflow_user_id, level
        ):
            count += 1

    return count


def ensure_user_scope_datasets(db: Session, user: User, kf) -> None:
    """预创建用户相关的分级知识库（个人库在用户租户，部门链在 bootstrap）。"""
    from app.core.document_scope import scope_for_department

    user_kf = _user_knowflow_client(db, user)
    ensure_scope_dataset(db, user, SCOPE_PERSONAL, str(user.id), user_kf)
    for dept_id in _dept_ids_for_kb_access(db, user):
        ensure_scope_dataset(
            db, user, scope_for_department(db, dept_id), str(dept_id), kf
        )


def _dept_ids_for_kb_labels(db: Session, user: User) -> list[uuid.UUID]:
    """标签与重命名覆盖的部门范围（所属部门及其上级）。"""
    return _dept_ids_for_kb_access(db, user)


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


def _append_registry_kb_labels(
    db: Session,
    labels: list[dict[str, str]],
    seen_names: set[str],
    reg: RagflowScopeDataset,
) -> None:
    try:
        key = uuid.UUID(reg.scope_key)
    except ValueError:
        key = None
    if reg.scope == REG_PERSONAL and key:
        label = dataset_display_label_personal(db, key)
        technical = dataset_name_for_personal(key, db)
        _append_kb_label(labels, seen_names, technical, label)
        for legacy in legacy_scope_dataset_names(SCOPE_PERSONAL, reg.scope_key):
            _append_kb_label(labels, seen_names, legacy, label)
    elif reg.scope in (REG_DEPARTMENT, REG_TEAM) and key:
        label = dataset_display_label_dept(db, key)
        technical = dataset_name_for_dept(key, db)
        _append_kb_label(labels, seen_names, technical, label)
        for legacy in legacy_scope_dataset_names(
            SCOPE_DEPARTMENT if reg.scope == REG_DEPARTMENT else SCOPE_TEAM,
            reg.scope_key,
        ):
            _append_kb_label(labels, seen_names, legacy, label)
    elif reg.scope == REG_COMPANY:
        label = dataset_display_label_company()
        technical = dataset_name_for_company()
        _append_kb_label(labels, seen_names, technical, label)
        _append_kb_label(labels, seen_names, legacy_dataset_name_for_company(), label)


def knowflow_kb_labels_for_user(db: Session, user: User) -> list[dict[str, str]]:
    """供前端 / KnowFlow 主题展示：仅包含当前用户有权访问的分级库。"""
    labels: list[dict[str, str]] = []
    seen_names: set[str] = set()

    if user_is_superuser(db, user):
        admin = _admin_rag_client()
        if admin:
            try:
                for ds in admin.list_datasets():
                    ds_id = str(ds.get("id") or "").strip()
                    name = (ds.get("name") or "").strip()
                    if not ds_id or not name:
                        continue
                    reg = _registry_for_dataset_id(db, ds_id)
                    if reg:
                        _append_registry_kb_labels(db, labels, seen_names, reg)
                    else:
                        _append_kb_label(labels, seen_names, name, name)
            except Exception as e:
                logger.warning("系统管理员列举 KnowFlow 知识库失败: %s", e)
        else:
            priv = _privileged_rag_client(db)
            if priv:
                try:
                    for ds in priv.list_datasets():
                        ds_id = str(ds.get("id") or "").strip()
                        name = (ds.get("name") or "").strip()
                        if not ds_id or not name:
                            continue
                        reg = _registry_for_dataset_id(db, ds_id)
                        if reg:
                            _append_registry_kb_labels(db, labels, seen_names, reg)
                        else:
                            _append_kb_label(labels, seen_names, name, name)
                except Exception as e:
                    logger.warning("系统管理员列举 KnowFlow 知识库失败: %s", e)

    allowed_ids = allowed_dataset_ids_for_user(db, user)

    scope_regs = _scope_registries_for_user(db, user)
    covered_ids: set[str] = set()
    for reg in scope_regs:
        if reg.ragflow_dataset_id not in allowed_ids:
            continue
        covered_ids.add(reg.ragflow_dataset_id)
        _append_registry_kb_labels(db, labels, seen_names, reg)

    for ds_id in allowed_ids:
        if ds_id in covered_ids:
            continue
        reg = _registry_for_dataset_id(db, ds_id)
        if reg:
            _append_registry_kb_labels(db, labels, seen_names, reg)

    return labels
