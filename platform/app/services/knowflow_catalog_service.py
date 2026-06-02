"""KnowFlow 分级知识库与平台文档的全量对齐（修复后对用户调用）。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.integrations.ragflow_rbac import ensure_ragflow_global_admin
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_scope_dataset import RagflowScopeDataset
from app.services.ragflow_identity_service import get_or_create_link, get_user_ragflow_auth
from app.services.ragflow_scope_service import (
    _visible_dataset_ids,
    dedupe_orphan_scope_datasets,
    ensure_user_scope_datasets,
    repair_stale_scope_registries,
    sync_all_kb_display_names,
    sync_user_kb_grants,
)
from app.services.ragflow_sync_service import sync_accessible_documents

logger = logging.getLogger(__name__)


def _ensure_ragflow_kb_admin(db: Session, user: User) -> None:
    settings = get_settings()
    if not settings.knowflow_enabled:
        return
    link = get_or_create_link(db, user)
    get_user_ragflow_auth(db, user)
    db.flush()
    db.refresh(link)
    if link.ragflow_user_id and (
        settings.ragflow_grant_global_admin
        or (settings.ragflow_account_mode or "").strip().lower() == "shared"
        or settings.knowflow_enabled
    ):
        ensure_ragflow_global_admin(link.ragflow_user_id)


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
    kf = get_knowflow_client_for_user(db, user)
    if not kf.enabled():
        return {"ok": False, "reason": "client_disabled"}

    ensure_user_scope_datasets(db, user, kf)
    renamed_kb = sync_all_kb_display_names(db, kf)
    orphan_datasets = dedupe_orphan_scope_datasets(db, user, kf)
    grants = sync_user_kb_grants(db, user)
    repaired_scopes = repair_stale_scope_registries(db, kf)
    orphan_links = _drop_orphan_document_links(db, kf)

    synced_count = 0
    if sync_documents:
        limit = sync_limit if sync_limit is not None else settings.ragflow_sync_doc_limit
        synced_map = sync_accessible_documents(db, user, limit=limit)
        synced_count = len(synced_map)

    return {
        "ok": True,
        "repaired_scopes": repaired_scopes,
        "orphan_links": orphan_links,
        "kb_grants": grants,
        "synced_documents": synced_count,
        "catalog_prepared": True,
        "visible_datasets": len(_visible_dataset_ids(kf)),
        "renamed_kb": renamed_kb,
        "orphan_datasets": orphan_datasets,
    }
