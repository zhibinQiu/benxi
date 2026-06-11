"""知识检索左侧文档树：与文档中心分级/组织/文件夹结构对齐。"""

from __future__ import annotations

import json
import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.models.document import DocumentLibraryFolder
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.services.document_library_align_service import (
    collect_aligned_library_documents,
    dataset_id_for_library_unit,
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

_SCOPE_TREE_CACHE_TTL_SEC = 120
_SCOPE_TREE_CACHE_VERSION = 2
_local_scope_tree_cache: dict[str, tuple[float, dict]] = {}

_ORG_UNIT_LOADERS = {
    "company": library_companies_for_user,
    "department": library_departments_for_user,
    "team": library_teams_for_user,
}

KNOWLEDGE_SCOPE_LABELS = SCOPE_LABELS


def _scope_tree_cache_key(user_id: uuid.UUID) -> str:
    return f"knowledge:scope-tree:v{_SCOPE_TREE_CACHE_VERSION}:{user_id}"


def _read_scope_tree_cache(user_id: uuid.UUID) -> dict | None:
    key = _scope_tree_cache_key(user_id)
    client = None
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        if client:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
    except Exception as exc:
        logger.debug("读取知识检索树缓存失败 key=%s: %s", key, exc)

    hit = _local_scope_tree_cache.get(key)
    if hit and time.monotonic() - hit[0] < _SCOPE_TREE_CACHE_TTL_SEC:
        return hit[1]
    return None


def _write_scope_tree_cache(user_id: uuid.UUID, data: dict) -> None:
    key = _scope_tree_cache_key(user_id)
    _local_scope_tree_cache[key] = (time.monotonic(), data)
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        if client:
            client.setex(
                key,
                _SCOPE_TREE_CACHE_TTL_SEC,
                json.dumps(data, ensure_ascii=False),
            )
    except Exception as exc:
        logger.debug("写入知识检索树缓存失败 key=%s: %s", key, exc)


def invalidate_scope_tree_cache(user_id: uuid.UUID | None = None) -> None:
    """文档同步/索引变更后可调用；user_id 为空时仅清本地兜底缓存。"""
    if user_id is not None:
        key = _scope_tree_cache_key(user_id)
        _local_scope_tree_cache.pop(key, None)
        try:
            from app.core.redis_client import get_redis_client

            client = get_redis_client()
            if client:
                client.delete(key)
        except Exception as exc:
            logger.debug("删除知识检索树缓存失败 key=%s: %s", key, exc)
        return
    _local_scope_tree_cache.clear()


def _sum_folder_stats(folder_nodes: list[dict]) -> tuple[int, int]:
    total = 0
    ready = 0
    for folder in folder_nodes:
        total += int(folder.get("document_count") or 0)
        ready += int(folder.get("index_ready_count") or 0)
    return total, ready


def _ragflow_row_for_document(
    db: Session, document_id: uuid.UUID, dataset_id: str | None
) -> dict | None:
    if not dataset_id:
        return None
    link = db.scalar(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.platform_document_id == document_id,
            RagflowDocumentLink.dataset_id == dataset_id,
        )
    )
    if not link or not (link.ragflow_document_id or "").strip():
        return None
    return {
        "document_id": str(document_id),
        "ragflow_document_id": link.ragflow_document_id,
        "knowledge_synced": True,
        "parse_status": None,
    }


def _enrich_doc_rows_meta(
    db: Session, user: User, dataset_id: str | None, rows: list[dict]
) -> None:
    if not dataset_id or not rows:
        return
    from app.services.knowledge_library_service import _enrich_ragflow_doc_meta

    _enrich_ragflow_doc_meta(db, user, dataset_id, rows)


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


def _build_folder_nodes_for_unit(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    dataset_id: str | None,
) -> list[dict]:
    docs = collect_aligned_library_documents(
        db,
        user,
        scope=scope,
        dept_id=dept_id,
        owner_id=owner_id,
    )
    shared_doc_ids = (
        _shared_document_ids_for_user(db, user)
        if scope == SCOPE_PERSONAL and owner_id == user.id
        else set()
    )

    rows: list[dict] = []
    for doc in docs:
        rag_row = _ragflow_row_for_document(db, doc.id, dataset_id)
        if not rag_row:
            continue
        folder_id_str: str | None = None
        if doc.folder_id:
            folder = db.get(DocumentLibraryFolder, doc.folder_id)
            if folder_matches_document(db, folder, doc):
                folder_id_str = str(doc.folder_id)
        rag_row.update(
            {
                "title": (doc.title or "").strip() or "未命名文档",
                "scope": doc.scope,
                "file_name": "",
                "folder_id": folder_id_str,
            }
        )
        rows.append(rag_row)
    _enrich_doc_rows_meta(db, user, dataset_id, rows)

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = _folder_group_key(
            row["document_id"],
            row.get("folder_id"),
            shared_doc_ids=shared_doc_ids,
        )
        grouped.setdefault(key, []).append(row)

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

    stmt = select(DocumentLibraryFolder).where(DocumentLibraryFolder.scope == scope)
    if scope == SCOPE_PERSONAL and owner_id:
        stmt = stmt.where(DocumentLibraryFolder.owner_id == owner_id)
    elif scope in ORG_SCOPES and dept_id:
        stmt = stmt.where(DocumentLibraryFolder.dept_id == dept_id)

    for folder in db.scalars(
        stmt.order_by(
            DocumentLibraryFolder.sort_order.asc(),
            DocumentLibraryFolder.created_at.asc(),
        )
    ).all():
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
        children = [
            _map_document_tree_node(doc, dataset_id or "") for doc in doc_rows
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
    from app.services.knowledge_library_service import _knowflow_ready

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
        "knowflow_enabled": _knowflow_ready(),
    }


def build_knowledge_scope_tree(db: Session, user: User) -> dict:
    cached = _read_scope_tree_cache(user_id=user.id)
    if cached is not None:
        return cached
    data = _build_knowledge_scope_tree(db, user)
    _write_scope_tree_cache(user.id, data)
    return data
