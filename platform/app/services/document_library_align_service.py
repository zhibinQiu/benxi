"""文档中心与知识检索树对齐：校验规则与历史数据修复。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.document_scope import (
    ORG_SCOPES,
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    SCOPE_TEAM,
    scope_for_department,
    _document_scope,
)
from app.core.permissions import user_is_superuser
from app.models.document import Document, DocumentLibraryFolder, DocumentStatus
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
)
from app.models.ragflow_scope_dataset import (
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
)
from app.models.ragflow_scope_dataset import (
    SCOPE_PERSONAL as REG_PERSONAL,
)
from app.models.ragflow_scope_dataset import (
    SCOPE_TEAM as REG_TEAM,
)
from app.models.ragflow_scope_dataset import RagflowScopeDataset
from app.services.ragflow_scope_service import COMPANY_SCOPE_KEY, _get_registry

logger = logging.getLogger(__name__)

_SCOPE_TO_REG = {
    SCOPE_PERSONAL: REG_PERSONAL,
    SCOPE_COMPANY: REG_COMPANY,
    SCOPE_DEPARTMENT: REG_DEPARTMENT,
    SCOPE_TEAM: REG_TEAM,
}


def expected_scope_for_document(db: Session, document: Document) -> str:
    """文档分级：有组织节点时按树深度，否则保留显式 scope。"""
    if document.dept_id:
        return scope_for_department(db, document.dept_id)
    return _document_scope(db, document)


def expected_scope_for_folder(db: Session, folder: DocumentLibraryFolder) -> str:
    if folder.dept_id:
        return scope_for_department(db, folder.dept_id)
    return folder.scope or SCOPE_PERSONAL


def scope_registry_key(scope: str, *, dept_id: uuid.UUID | None, owner_id: uuid.UUID | None) -> str:
    if scope == SCOPE_PERSONAL:
        if not owner_id:
            raise ValueError("personal scope requires owner_id")
        return str(owner_id)
    if scope in ORG_SCOPES:
        if not dept_id:
            raise ValueError(f"{scope} scope requires dept_id")
        return str(dept_id)
    if scope == SCOPE_COMPANY:
        return str(dept_id) if dept_id else COMPANY_SCOPE_KEY
    raise ValueError(f"invalid scope: {scope}")


def dataset_id_for_library_unit(
    db: Session,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> str | None:
    reg_scope = _SCOPE_TO_REG.get(scope)
    if not reg_scope:
        return None
    try:
        key = scope_registry_key(scope, dept_id=dept_id, owner_id=owner_id)
    except ValueError:
        return None
    reg = _get_registry(db, reg_scope, key)
    if not reg:
        return None
    return (reg.ragflow_dataset_id or "").strip() or None


def folder_matches_document(
    db: Session, folder: DocumentLibraryFolder | None, document: Document
) -> bool:
    if folder is None:
        return document.folder_id is None
    doc_scope = expected_scope_for_document(db, document)
    folder_scope = expected_scope_for_folder(db, folder)
    if folder_scope != doc_scope:
        return False
    if doc_scope in ORG_SCOPES:
        return bool(document.dept_id and folder.dept_id == document.dept_id)
    if doc_scope == SCOPE_PERSONAL:
        return folder.owner_id == document.owner_id
    return True


def document_matches_library_unit(
    db: Session,
    document: Document,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> bool:
    if document.deleted_at is not None:
        return False
    if document.status != DocumentStatus.active.value:
        return False
    doc_scope = expected_scope_for_document(db, document)
    if doc_scope != scope:
        return False
    if scope in ORG_SCOPES:
        return bool(dept_id and document.dept_id == dept_id)
    if scope == SCOPE_PERSONAL:
        if owner_id is None:
            return True
        return document.owner_id == owner_id
    return True


def document_matches_dataset_link(
    db: Session,
    document: Document,
    dataset_id: str,
) -> bool:
    from app.services.ragflow_scope_service import _registry_for_dataset_id

    reg = _registry_for_dataset_id(db, dataset_id)
    if not reg:
        return False
    out_scope = {
        REG_PERSONAL: SCOPE_PERSONAL,
        REG_COMPANY: SCOPE_COMPANY,
        REG_DEPARTMENT: SCOPE_DEPARTMENT,
        REG_TEAM: SCOPE_TEAM,
    }.get(reg.scope)
    if not out_scope:
        return False
    owner_id: uuid.UUID | None = None
    dept_id: uuid.UUID | None = None
    if reg.scope == REG_PERSONAL:
        try:
            owner_id = uuid.UUID(reg.scope_key)
        except ValueError:
            return False
    elif reg.scope in (REG_DEPARTMENT, REG_TEAM, REG_COMPANY):
        try:
            dept_id = uuid.UUID(reg.scope_key)
        except ValueError:
            if reg.scope != REG_COMPANY or reg.scope_key != COMPANY_SCOPE_KEY:
                return False
    return document_matches_library_unit(
        db,
        document,
        scope=out_scope,
        dept_id=dept_id,
        owner_id=owner_id,
    )


def _find_or_create_folder(
    db: Session,
    *,
    name: str,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    created_by: uuid.UUID,
) -> DocumentLibraryFolder:
    stmt = select(DocumentLibraryFolder).where(DocumentLibraryFolder.name == name)
    if dept_id is None:
        stmt = stmt.where(DocumentLibraryFolder.dept_id.is_(None))
    else:
        stmt = stmt.where(DocumentLibraryFolder.dept_id == dept_id)
    if owner_id is None:
        stmt = stmt.where(DocumentLibraryFolder.owner_id.is_(None))
    else:
        stmt = stmt.where(DocumentLibraryFolder.owner_id == owner_id)
    folder = db.scalar(stmt.where(DocumentLibraryFolder.scope == scope))
    if folder:
        folder.scope = scope
        return folder
    folder = DocumentLibraryFolder(
        name=name,
        description="",
        scope=scope,
        dept_id=dept_id,
        owner_id=owner_id,
        created_by=created_by,
    )
    db.add(folder)
    db.flush()
    return folder


def repair_platform_library_data(db: Session) -> dict[str, Any]:
    """修复平台 documents / folders 与组织分级不一致的历史数据。"""
    report: dict[str, Any] = {
        "documents_scope_fixed": 0,
        "folders_scope_fixed": 0,
        "documents_folder_cleared": 0,
        "documents_folder_reassigned": 0,
        "folder_migrations": [],
    }
    from app.models.org import Role, UserRole

    admin = db.scalar(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == "sys_admin")
        .limit(1)
    )
    created_by = admin.id if admin else None

    for folder in db.scalars(select(DocumentLibraryFolder)).all():
        expected = expected_scope_for_folder(db, folder)
        if folder.scope != expected:
            folder.scope = expected
            report["folders_scope_fixed"] += 1

    folder_by_id = {
        f.id: f for f in db.scalars(select(DocumentLibraryFolder)).all()
    }
    pending_folder_moves: list[tuple[Document, DocumentLibraryFolder | None, str]] = []

    for doc in db.scalars(
        select(Document).where(Document.deleted_at.is_(None))
    ).all():
        expected = expected_scope_for_document(db, doc)
        if doc.scope != expected:
            doc.scope = expected
            report["documents_scope_fixed"] += 1

        folder = folder_by_id.get(doc.folder_id) if doc.folder_id else None
        if not folder_matches_document(db, folder, doc):
            if folder and created_by and doc.dept_id and doc.scope in ORG_SCOPES:
                pending_folder_moves.append((doc, folder, folder.name))
            doc.folder_id = None
            report["documents_folder_cleared"] += 1

    for doc, old_folder, folder_name in pending_folder_moves:
        if doc.folder_id is not None:
            continue
        if not created_by:
            continue
        target = _find_or_create_folder(
            db,
            name=folder_name,
            scope=doc.scope,
            dept_id=doc.dept_id,
            owner_id=None,
            created_by=created_by,
        )
        doc.folder_id = target.id
        report["documents_folder_reassigned"] += 1
        report["folder_migrations"].append(
            {
                "document_id": str(doc.id),
                "from_folder_scope": old_folder.scope if old_folder else None,
                "to_folder_id": str(target.id),
                "to_scope": doc.scope,
            }
        )

    db.flush()
    return report


def list_misaligned_ragflow_links(db: Session) -> list[tuple[RagflowDocumentLink, Document]]:
    rows: list[tuple[RagflowDocumentLink, Document]] = []
    for link in db.scalars(select(RagflowDocumentLink)).all():
        doc = db.get(Document, link.platform_document_id)
        if not doc or doc.deleted_at is not None:
            continue
        if not document_matches_dataset_link(db, doc, link.dataset_id):
            rows.append((link, doc))
    return rows


def repair_ragflow_link_targets(db: Session) -> dict[str, Any]:
    """将 ragflow_document_links.dataset_id 纠正为与文档分级一致的目标库（仅 DB）。"""
    report = {"links_updated": 0, "links_removed": 0, "details": []}
    for link, doc in list_misaligned_ragflow_links(db):
        target = dataset_id_for_library_unit(
            db,
            scope=expected_scope_for_document(db, doc),
            dept_id=doc.dept_id,
            owner_id=doc.owner_id if expected_scope_for_document(db, doc) == SCOPE_PERSONAL else None,
        )
        if not target:
            db.delete(link)
            report["links_removed"] += 1
            report["details"].append(
                {"document_id": str(doc.id), "action": "removed", "reason": "no_target_dataset"}
            )
            continue
        if link.dataset_id != target:
            report["details"].append(
                {
                    "document_id": str(doc.id),
                    "action": "updated",
                    "from_dataset": link.dataset_id,
                    "to_dataset": target,
                }
            )
            link.dataset_id = target
            report["links_updated"] += 1
    db.flush()
    return report


def repair_ragflow_links_with_resync(db: Session, user: User | None) -> dict[str, Any]:
    """将错位索引迁回正确分级知识库；KnowFlow 不可用时仅修正 DB 映射。"""
    from app.domains.knowledge import knowledge

    misaligned = list_misaligned_ragflow_links(db)
    report: dict[str, Any] = {
        "misaligned": len(misaligned),
        "resynced": 0,
        "failed": 0,
        "db_only": 0,
        "details": [],
    }
    if not misaligned:
        return report

    can_resync = bool(user and knowledge.stack_reachable())
    if can_resync:
        from app.services.ragflow_sync_service import KnowflowSyncError, sync_document_to_knowflow

        for _link, doc in misaligned:
            try:
                rid = sync_document_to_knowflow(db, user, doc, force=True)
                if rid:
                    report["resynced"] += 1
                    report["details"].append(
                        {"document_id": str(doc.id), "action": "resynced", "ragflow_id": rid}
                    )
                else:
                    report["failed"] += 1
            except KnowflowSyncError as exc:
                report["failed"] += 1
                report["details"].append(
                    {"document_id": str(doc.id), "action": "failed", "error": str(exc)}
                )
        remaining = list_misaligned_ragflow_links(db)
        if remaining:
            db_fix = repair_ragflow_link_targets(db)
            report["db_only"] = db_fix["links_updated"] + db_fix["links_removed"]
            report["db_fix"] = db_fix
    else:
        db_fix = repair_ragflow_link_targets(db)
        report["db_only"] = db_fix["links_updated"] + db_fix["links_removed"]
        report["db_fix"] = db_fix
    return report


def repair_document_library_alignment(db: Session, *, actor: User | None = None) -> dict[str, Any]:
    """一次性修复平台文库与知识库映射错位。"""
    platform = repair_platform_library_data(db)
    ragflow = repair_ragflow_links_with_resync(db, actor)
    db.commit()
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(None)
    return {"platform": platform, "ragflow": ragflow}


def _document_matches_library_unit_fast(
    db: Session,
    document: Document,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> bool:
    """对齐数据走内存比较，历史错位数据回退完整校验。"""
    if document.deleted_at is not None:
        return False
    if document.status != DocumentStatus.active.value:
        return False
    doc_scope = (getattr(document, "scope", None) or "").strip()
    if scope in ORG_SCOPES:
        if not dept_id or document.dept_id != dept_id:
            return False
        if doc_scope == scope:
            return True
    elif scope == SCOPE_PERSONAL:
        if owner_id is not None and document.owner_id != owner_id:
            return False
        if doc_scope == SCOPE_PERSONAL:
            return True
    elif doc_scope == scope:
        return True
    return document_matches_library_unit(
        db,
        document,
        scope=scope,
        dept_id=dept_id,
        owner_id=owner_id,
    )


def collect_aligned_library_documents(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> list[Document]:
    """与文档中心相同分级筛选，且仅保留已上传文件的启用文档。"""
    from app.core.permissions import PermissionLevel
    from app.services.documents.access_batch import filter_documents_for_list
    from app.services.documents.listing import _has_uploaded_version_exists

    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.status == DocumentStatus.active.value,
        _has_uploaded_version_exists(),
    )
    if scope in ORG_SCOPES and dept_id is not None:
        stmt = stmt.where(Document.scope == scope, Document.dept_id == dept_id)
    elif scope == SCOPE_PERSONAL:
        stmt = stmt.where(Document.scope == SCOPE_PERSONAL)
        if not user_is_superuser(db, user):
            stmt = stmt.where(Document.owner_id == user.id)
        elif owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)
    else:
        stmt = stmt.where(Document.scope == scope)

    candidates = list(db.scalars(stmt.order_by(Document.updated_at.desc())).all())
    matched = [
        doc
        for doc in candidates
        if _document_matches_library_unit_fast(
            db, doc, scope=scope, dept_id=dept_id, owner_id=owner_id
        )
    ]
    return filter_documents_for_list(
        db,
        user,
        matched,
        required_level=PermissionLevel.query.value,
    )
