"""知识检索左侧文档树：与文档中心分级/组织/文件夹结构对齐。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.platform_cache import invalidate_scope_tree_cache  # noqa: F401

from app.core.document_scope import (
    LIBRARY_TAB_SCOPES,
    ORG_SCOPES,
    SCOPE_LABELS,
    SCOPE_PERSONAL,
    library_companies_for_user,
    library_departments_for_user,
    library_teams_for_user,
)
from app.core.permissions import user_is_superuser
from app.models.document import Document, DocumentLibraryFolder
from app.models.org import User
from app.services.document_library_align_service import (
    collect_aligned_library_documents,
    dataset_id_for_library_unit,
    document_matches_dataset_link,
    folder_matches_document,
)
from app.services.knowledge_library_service import (
    _map_document_tree_node,
    _row_index_ready,
    _shared_document_ids_for_user,
)
from app.services.library_folder_service import (
    FOLDER_KIND_SHARED,
    FOLDER_KIND_UNCATEGORIZED,
    VIRTUAL_SHARED_ID,
    VIRTUAL_UNCATEGORIZED_ID,
)

logger = logging.getLogger(__name__)

_ORG_UNIT_LOADERS = {
    "company": library_companies_for_user,
    "department": library_departments_for_user,
    "team": library_teams_for_user,
}

KNOWLEDGE_SCOPE_LABELS = SCOPE_LABELS


def notify_knowledge_index_state_changed(
    *,
    user_id: uuid.UUID,
    dataset_id: str | None = None,
) -> None:
    """索引任务完成或重新解析后，使知识检索树与文档中心状态一致。"""
    from app.core.platform_cache import (
        invalidate_document_library_cache,
        invalidate_ragflow_doc_meta_cache,
        invalidate_scope_tree_cache,
    )

    invalidate_scope_tree_cache(user_id)
    invalidate_ragflow_doc_meta_cache(dataset_id)
    invalidate_document_library_cache(str(user_id))


def _sum_folder_stats(folder_nodes: list[dict]) -> tuple[int, int]:
    total = 0
    ready = 0
    for folder in folder_nodes:
        total += int(folder.get("document_count") or 0)
        ready += int(folder.get("index_ready_count") or 0)
    return total, ready


def _ragflow_row_for_document(
    db: Session, document: Document, dataset_id: str | None
) -> dict | None:
    """按文档中心同一套分级规则 + canonical 索引映射解析行。"""
    if not dataset_id:
        return None
    if not document_matches_dataset_link(db, document, dataset_id):
        return None
    from app.services.ragflow_sync_service import get_document_link
    from app.services.ragflow_version_link_service import resolve_index_link

    link = get_document_link(db, document.id)
    version_link, _ = resolve_index_link(db, document)
    ragflow_id = ""
    if version_link and (version_link.ragflow_document_id or "").strip():
        ragflow_id = str(version_link.ragflow_document_id).strip()
    elif link and (link.ragflow_document_id or "").strip():
        ragflow_id = str(link.ragflow_document_id).strip()
    if not ragflow_id:
        return None
    return {
        "document_id": str(document.id),
        "ragflow_document_id": ragflow_id,
        "knowledge_synced": True,
        "parse_status": None,
    }


def _enrich_doc_rows_meta(
    db: Session,
    user: User,
    dataset_id: str | None,
    rows: list[dict],
    *,
    documents: list[Document] | None = None,
) -> None:
    if not rows or not documents:
        return
    from app.services.document_index_service import enrich_knowledge_document_rows

    enrich_knowledge_document_rows(
        db, user, rows, documents, live_ragflow=False
    )


def _base_scope_document_row(document: Document) -> dict:
    """建树占位行；索引元数据由 enrich_knowledge_document_rows 批量填充。"""
    return {
        "document_id": str(document.id),
        "ragflow_document_id": None,
        "knowledge_synced": False,
        "parse_status": "未同步",
        "chunk_count": None,
    }


def _folder_matches_document_fast(
    db: Session,
    folder: DocumentLibraryFolder | None,
    document: Document,
) -> bool:
    if folder is None:
        return document.folder_id is None
    doc_scope = (getattr(document, "scope", None) or "").strip()
    folder_scope = (getattr(folder, "scope", None) or "").strip()
    if doc_scope and folder_scope and doc_scope == folder_scope:
        if doc_scope in ORG_SCOPES:
            return bool(document.dept_id and folder.dept_id == document.dept_id)
        if doc_scope == SCOPE_PERSONAL:
            return folder.owner_id == document.owner_id
        return True
    return folder_matches_document(db, folder, document)


def _map_scope_document_tree_node(
    doc: dict, dataset_id: str, *, folder_key: str
) -> dict:
    from app.services.knowledge_library_service import _map_document_tree_node

    node = _map_document_tree_node(doc, dataset_id)
    node["key"] = f"doc:{folder_key}:{doc['document_id']}"
    return node


def _folder_group_key(
    doc_id: str,
    folder_id: str | None,
    *,
    shared_doc_ids: set[str],
) -> str:
    if doc_id in shared_doc_ids:
        return VIRTUAL_SHARED_ID
    if not folder_id:
        return VIRTUAL_UNCATEGORIZED_ID
    return folder_id


def _library_folders_for_unit(
    db: Session,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> list[DocumentLibraryFolder]:
    stmt = select(DocumentLibraryFolder).where(DocumentLibraryFolder.scope == scope)
    if scope == SCOPE_PERSONAL and owner_id:
        stmt = stmt.where(DocumentLibraryFolder.owner_id == owner_id)
    elif scope in ORG_SCOPES and dept_id:
        stmt = stmt.where(DocumentLibraryFolder.dept_id == dept_id)
    return list(
        db.scalars(
            stmt.order_by(
                DocumentLibraryFolder.sort_order.asc(),
                DocumentLibraryFolder.created_at.asc(),
            )
        ).all()
    )


def _build_folder_nodes_for_unit(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    dataset_id: str | None,
    shared_doc_ids: set[str] | None = None,
) -> list[dict]:
    docs = collect_aligned_library_documents(
        db,
        user,
        scope=scope,
        dept_id=dept_id,
        owner_id=owner_id,
    )
    if shared_doc_ids is None:
        shared_doc_ids = (
            _shared_document_ids_for_user(db, user)
            if scope == SCOPE_PERSONAL and owner_id == user.id
            else set()
        )

    unit_folders = _library_folders_for_unit(
        db, scope=scope, dept_id=dept_id, owner_id=owner_id
    )
    folder_by_id = {str(folder.id): folder for folder in unit_folders}

    rows: list[dict] = []
    doc_by_id: dict[str, Document] = {}
    seen_doc_ids: set[str] = set()
    for doc in docs:
        did = str(doc.id)
        if did in seen_doc_ids:
            continue
        seen_doc_ids.add(did)
        doc_by_id[did] = doc
        folder_id_str: str | None = None
        if doc.folder_id:
            folder = folder_by_id.get(str(doc.folder_id))
            if folder and _folder_matches_document_fast(db, folder, doc):
                folder_id_str = str(doc.folder_id)
        row = _base_scope_document_row(doc)
        row.update(
            {
                "title": (doc.title or "").strip() or "未命名文档",
                "scope": doc.scope,
                "file_name": "",
                "folder_id": folder_id_str,
            }
        )
        rows.append(row)
    _enrich_doc_rows_meta(
        db,
        user,
        dataset_id,
        rows,
        documents=list(doc_by_id.values()),
    )

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = _folder_group_key(
            row["document_id"],
            row.get("folder_id"),
            shared_doc_ids=shared_doc_ids,
        )
        bucket = grouped.setdefault(key, [])
        if any(existing["document_id"] == row["document_id"] for existing in bucket):
            continue
        bucket.append(row)

    ds_key = dataset_id or f"scope:{scope}"
    items: list[dict] = [
        {
            "key": f"folder:{ds_key}:{VIRTUAL_UNCATEGORIZED_ID}",
            "label": "未分类",
            "type": "folder",
            "scope": scope,
            "dataset_id": dataset_id,
            "folder_id": None,
            "virtual_folder_id": VIRTUAL_UNCATEGORIZED_ID,
            "kind": FOLDER_KIND_UNCATEGORIZED,
            "document_count": 0,
            "index_ready_count": 0,
            "is_leaf": True,
            "children": [],
        }
    ]

    if scope == SCOPE_PERSONAL and owner_id == user.id:
        items.append(
            {
                "key": f"folder:{ds_key}:{VIRTUAL_SHARED_ID}",
                "label": "分享",
                "type": "folder",
                "scope": scope,
                "dataset_id": dataset_id,
                "folder_id": None,
                "virtual_folder_id": VIRTUAL_SHARED_ID,
                "kind": FOLDER_KIND_SHARED,
                "document_count": 0,
                "index_ready_count": 0,
                "is_leaf": True,
                "children": [],
            }
        )

    for folder in unit_folders:
        fid = str(folder.id)
        items.append(
            {
                "key": f"folder:{ds_key}:{fid}",
                "label": folder.name,
                "type": "folder",
                "scope": scope,
                "dataset_id": dataset_id,
                "folder_id": fid,
                "virtual_folder_id": None,
                "kind": "normal",
                "document_count": 0,
                "index_ready_count": 0,
                "is_leaf": True,
                "children": [],
            }
        )

    for folder_node in items:
        group_key = folder_node.get("virtual_folder_id") or folder_node.get("folder_id")
        doc_rows = grouped.get(group_key or "", [])
        folder_key = f"{ds_key}:{group_key or 'root'}"
        children = [
            _map_scope_document_tree_node(
                doc, dataset_id or "", folder_key=folder_key
            )
            for doc in doc_rows
        ]
        folder_node["children"] = children
        folder_node["document_count"] = len(children)
        folder_node["index_ready_count"] = sum(
            1 for doc in doc_rows if _row_index_ready(doc)
        )
        folder_node["is_leaf"] = len(children) == 0

    return items


def _build_org_scope_node(db: Session, user: User, scope: str) -> dict | None:
    loader = _ORG_UNIT_LOADERS.get(scope)
    if not loader:
        return None
    units = loader(db, user)
    if not units:
        return None

    children: list[dict] = []
    scope_doc_total = 0
    scope_ready_total = 0
    for unit in units:
        dept_id = unit["id"]
        dataset_id = dataset_id_for_library_unit(db, scope=scope, dept_id=dept_id)
        folder_nodes = _build_folder_nodes_for_unit(
            db,
            user,
            scope=scope,
            dept_id=dept_id,
            owner_id=None,
            dataset_id=dataset_id,
        )
        doc_total, ready_total = _sum_folder_stats(folder_nodes)
        scope_doc_total += doc_total
        scope_ready_total += ready_total
        children.append(
            {
                "key": f"org:{scope}:{dept_id}",
                "label": unit["name"],
                "type": "library",
                "scope": scope,
                "dept_id": str(dept_id),
                "dataset_id": dataset_id,
                "document_count": doc_total,
                "index_ready_count": ready_total,
                "is_leaf": False,
                "children": folder_nodes,
            }
        )

    if not children or scope_doc_total == 0 and not any(
        c.get("document_count") for c in children
    ):
        # 仍展示空组织节点，与文档中心 Tab 一致
        pass

    return {
        "key": f"scope:{scope}",
        "label": KNOWLEDGE_SCOPE_LABELS.get(scope, scope),
        "type": "scope",
        "scope": scope,
        "document_count": scope_doc_total,
        "index_ready_count": scope_ready_total,
        "is_leaf": False,
        "children": children,
    }


def _build_personal_scope_node(db: Session, user: User) -> dict | None:
    from app.models.ragflow_scope_dataset import SCOPE_PERSONAL as REG_PERSONAL
    from app.services.ragflow_scope_service import _scope_registries_for_user

    children: list[dict] = []
    scope_doc_total = 0
    scope_ready_total = 0
    is_super = user_is_superuser(db, user)
    shared_doc_ids = _shared_document_ids_for_user(db, user)

    if is_super:
        owner_ids = {
            doc.owner_id
            for doc in collect_aligned_library_documents(db, user, scope=SCOPE_PERSONAL)
        }
        owner_ids.add(user.id)
        reg_by_owner: dict[uuid.UUID, str | None] = {}
        for reg in _scope_registries_for_user(db, user):
            if reg.scope != REG_PERSONAL:
                continue
            try:
                oid = uuid.UUID(reg.scope_key)
            except ValueError:
                continue
            reg_by_owner[oid] = (reg.ragflow_dataset_id or "").strip() or None
        targets = sorted(owner_ids, key=str)
    else:
        targets = [user.id]
        reg_by_owner = {
            user.id: dataset_id_for_library_unit(
                db, scope=SCOPE_PERSONAL, owner_id=user.id
            )
        }

    for owner_id in targets:
        from app.core.user_display import user_display_name

        owner = db.get(User, owner_id)
        label = user_display_name(owner) if owner else str(owner_id)
        dataset_id = reg_by_owner.get(owner_id) or dataset_id_for_library_unit(
            db, scope=SCOPE_PERSONAL, owner_id=owner_id
        )
        folder_nodes = _build_folder_nodes_for_unit(
            db,
            user,
            scope=SCOPE_PERSONAL,
            dept_id=None,
            owner_id=owner_id,
            dataset_id=dataset_id,
            shared_doc_ids=shared_doc_ids if owner_id == user.id else set(),
        )
        doc_total, ready_total = _sum_folder_stats(folder_nodes)
        # 当前用户个人库始终展示（即使尚无已同步索引文档）；超管跳过他人空库
        if doc_total == 0 and is_super and owner_id != user.id:
            continue
        scope_doc_total += doc_total
        scope_ready_total += ready_total
        children.append(
            {
                "key": f"personal:{owner_id}",
                "label": label,
                "type": "library",
                "scope": SCOPE_PERSONAL,
                "owner_id": str(owner_id),
                "dataset_id": dataset_id,
                "document_count": doc_total,
                "index_ready_count": ready_total,
                "is_leaf": False,
                "children": folder_nodes,
            }
        )

    if not children:
        # 兜底：至少展示当前用户个人库
        dataset_id = dataset_id_for_library_unit(
            db, scope=SCOPE_PERSONAL, owner_id=user.id
        )
        folder_nodes = _build_folder_nodes_for_unit(
            db,
            user,
            scope=SCOPE_PERSONAL,
            dept_id=None,
            owner_id=user.id,
            dataset_id=dataset_id,
            shared_doc_ids=shared_doc_ids,
        )
        doc_total, ready_total = _sum_folder_stats(folder_nodes)
        from app.core.user_display import user_display_name

        children.append(
            {
                "key": f"personal:{user.id}",
                "label": user_display_name(user),
                "type": "library",
                "scope": SCOPE_PERSONAL,
                "owner_id": str(user.id),
                "dataset_id": dataset_id,
                "document_count": doc_total,
                "index_ready_count": ready_total,
                "is_leaf": False,
                "children": folder_nodes,
            }
        )
        scope_doc_total = doc_total
        scope_ready_total = ready_total

    if not children:
        return None

    return {
        "key": f"scope:{SCOPE_PERSONAL}",
        "label": KNOWLEDGE_SCOPE_LABELS[SCOPE_PERSONAL],
        "type": "scope",
        "scope": SCOPE_PERSONAL,
        "document_count": scope_doc_total,
        "index_ready_count": scope_ready_total,
        "is_leaf": False,
        "children": children,
    }


def _build_knowledge_scope_tree(db: Session, user: User) -> dict:
    from app.domains.knowledge import knowledge

    nodes: list[dict] = []
    for scope in LIBRARY_TAB_SCOPES:
        if scope == SCOPE_PERSONAL:
            node = _build_personal_scope_node(db, user)
        elif scope in ORG_SCOPES:
            node = _build_org_scope_node(db, user, scope)
        else:
            node = None
        if node:
            nodes.append(node)

    return {
        "items": nodes,
        "knowflow_enabled": knowledge.stack_reachable(),
    }


def build_knowledge_scope_tree(
    db: Session, user: User, *, force_refresh: bool = False
) -> dict:
    from app.config import get_settings
    from app.core.platform_cache import (
        cache_get_or_set,
        invalidate_scope_tree_cache,
        scope_tree_cache_key,
    )

    cache_key = scope_tree_cache_key(str(user.id))
    ttl = max(30, int(get_settings().scope_tree_cache_ttl_sec))
    if force_refresh:
        invalidate_scope_tree_cache(user.id)
    return cache_get_or_set(
        cache_key,
        lambda: _build_knowledge_scope_tree(db, user),
        ttl=ttl,
    )
