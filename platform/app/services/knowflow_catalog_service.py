"""KnowFlow 分级知识库与平台文档的全量对齐（修复后对用户调用）。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.knowflow_client import (
    get_knowflow_client_for_catalog,
    get_knowflow_client_for_user,
)
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_scope_dataset import RagflowScopeDataset
from app.services.ragflow_identity_service import get_or_create_link, get_user_ragflow_auth
from app.services.ragflow_scope_service import (
    _visible_dataset_ids,
    dedupe_orphan_scope_datasets,
    enforce_all_registered_personal_kbs_private,
    ensure_user_kb_create_permission,
    ensure_user_scope_datasets,
    purge_orphan_kbs_for_user_tenant,
    purge_unregistered_knowledge_bases,
    repair_orphan_scope_registries,
    repair_stale_scope_registries,
    sync_all_kb_display_names,
    sync_user_kb_grants,
)
from app.services.ragflow_sync_service import sync_accessible_documents

logger = logging.getLogger(__name__)


def _ensure_ragflow_kb_admin(db: Session, user: User) -> None:
    """确保 RAGFlow 账号已开户；全局 admin 由 sync_user_kb_grants 按平台角色同步。"""
    settings = get_settings()
    if not settings.knowflow_enabled:
        return
    get_or_create_link(db, user)
    get_user_ragflow_auth(db, user)
    db.flush()
    link = get_or_create_link(db, user)
    if (link.ragflow_access_token or "").strip():
        from app.integrations.ragflow_provision import finalize_ragflow_link

        finalize_ragflow_link(link, link.ragflow_access_token, user, db=db)
        db.flush()
    ensure_user_kb_create_permission(db, user)


def _drop_orphan_document_links(db: Session, kf) -> int:
    """仅删除指向已不存在、且平台未登记的分级库映射（授权滞后时保留链接）。"""
    visible = _visible_dataset_ids(kf)
    if not visible:
        return 0
    registered = {
        reg.ragflow_dataset_id
        for reg in db.scalars(select(RagflowScopeDataset)).all()
        if reg.ragflow_dataset_id
    }
    removed = 0
    for link in list(db.scalars(select(RagflowDocumentLink)).all()):
        ds = link.dataset_id
        if not ds or ds in visible or ds in registered:
            continue
        db.delete(link)
        removed += 1
    if removed:
        db.flush()
    return removed


def reconcile_user_knowflow_catalog(
    db: Session,
    user: User,
    *,
    sync_limit: int | None = None,
    sync_documents: bool = True,
) -> dict[str, int | bool]:
    """建分级知识库、刷新 ACL；sync_documents=False 时仅建库不拉文档（iframe 首屏）。"""
    settings = get_settings()
    if not settings.knowflow_enabled:
        return {"ok": False, "reason": "disabled"}

    _ensure_ragflow_kb_admin(db, user)
    kf = get_knowflow_client_for_catalog(db, user)
    if not kf.enabled():
        return {"ok": False, "reason": "client_disabled"}

    ensure_user_scope_datasets(db, user, kf)
    renamed_kb = sync_all_kb_display_names(db, kf)
    orphan_datasets = dedupe_orphan_scope_datasets(db, user, kf)
    unregistered_kbs = purge_unregistered_knowledge_bases(db, kf)
    user_tenant_orphans = purge_orphan_kbs_for_user_tenant(db, user)
    locked_personal = enforce_all_registered_personal_kbs_private(db)
    grants = sync_user_kb_grants(db, user, kf=kf)
    repaired_scopes = repair_stale_scope_registries(db, kf)
    orphan_registries = repair_orphan_scope_registries(db, kf)
    orphan_links = _drop_orphan_document_links(db, kf)

    synced_count = 0
    if sync_documents:
        limit = sync_limit if sync_limit is not None else settings.ragflow_sync_doc_limit
        synced_map = sync_accessible_documents(db, user, limit=limit)
        synced_count = len(synced_map)

    return {
        "ok": True,
        "repaired_scopes": repaired_scopes,
        "orphan_registries": orphan_registries,
        "orphan_links": orphan_links,
        "kb_grants": grants,
        "synced_documents": synced_count,
        "catalog_prepared": True,
        "visible_datasets": len(_visible_dataset_ids(kf)),
        "renamed_kb": renamed_kb,
        "orphan_datasets": orphan_datasets,
        "unregistered_kbs": unregistered_kbs,
        "user_tenant_orphans": user_tenant_orphans,
        "locked_personal_kbs": locked_personal,
    }


def reconcile_user_knowflow_kb_acl(db: Session, user: User) -> dict[str, int | bool]:
    """仅对齐 KnowFlow 知识库 ACL（不拉文档），用于登录/embed 快路径。"""
    settings = get_settings()
    if not settings.knowflow_enabled:
        return {"ok": False, "reason": "disabled"}

    _ensure_ragflow_kb_admin(db, user)
    from app.core.permissions import user_is_system_admin

    kf = (
        get_knowflow_client_for_catalog(db, user)
        if user_is_system_admin(db, user)
        else get_knowflow_client_for_user(db, user)
    )
    if not kf.enabled():
        return {"ok": False, "reason": "client_disabled"}

    locked_personal = enforce_all_registered_personal_kbs_private(db)
    user_tenant_orphans = purge_orphan_kbs_for_user_tenant(db, user)
    grants = sync_user_kb_grants(db, user, kf=kf)
    return {
        "ok": True,
        "kb_grants": grants,
        "locked_personal_kbs": locked_personal,
        "user_tenant_orphans": user_tenant_orphans,
        "synced_documents": 0,
        "visible_datasets": len(_visible_dataset_ids(kf)),
    }


def provision_knowflow_catalog_for_admin(db: Session, admin: User) -> dict[str, int | bool]:
    """系统管理员进入切片管理前：对全部已有知识库授予 ACL（可见所有用户文档）。"""
    from app.core.permissions import user_is_superuser
    from app.services.ragflow_scope_service import (
        _all_knowflow_dataset_ids,
        sync_user_kb_grants,
    )

    settings = get_settings()
    if not settings.knowflow_enabled or not user_is_superuser(db, admin):
        return {"ok": False, "reason": "not_admin"}

    _ensure_ragflow_kb_admin(db, admin)
    kf = get_knowflow_client_for_catalog(db, admin)
    if not kf.enabled():
        return {"ok": False, "reason": "client_disabled"}

    ensure_user_scope_datasets(db, admin, kf)
    grants = sync_user_kb_grants(db, admin, kf=kf)
    unregistered_kbs = purge_unregistered_knowledge_bases(db, kf)
    return {
        "ok": True,
        "kb_grants": grants,
        "visible_datasets": len(_visible_dataset_ids(kf)),
        "catalog_ids": len(_all_knowflow_dataset_ids(db)),
        "unregistered_kbs": unregistered_kbs,
    }
