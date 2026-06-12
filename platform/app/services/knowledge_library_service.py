"""平台原生切片库管理：列举分级库、库内文档与切片（不嵌入 KnowFlow UI）。"""

from __future__ import annotations

import json
import logging
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.document_scope import can_query_document
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import user_is_superuser
from app.integrations.knowflow_client import get_knowflow_client_for_user, knowflow_stack_reachable
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.core.document_scope import ORG_SCOPES
from app.models.document import Document, DocumentLibraryFolder
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
from app.models.ragflow_scope_dataset import (
    RagflowScopeDataset,
)
from app.services.document_service import get_document
from app.services.ragflow_naming import (
    dataset_display_label_company,
    dataset_display_label_dept,
    dataset_display_label_personal,
)
from app.services.library_folder_service import (
    FOLDER_KIND_SHARED,
    FOLDER_KIND_UNCATEGORIZED,
    VIRTUAL_SHARED_ID,
    VIRTUAL_UNCATEGORIZED_ID,
)
from app.services.document_library_align_service import document_matches_dataset_link
from app.services.ragflow_scope_service import (
    _registry_for_dataset_id,
    _scope_registries_for_user,
    allowed_dataset_ids_for_user,
)

logger = logging.getLogger(__name__)

_SCOPE_OUT = {
    REG_PERSONAL: "personal",
    REG_COMPANY: "company",
    REG_DEPARTMENT: "department",
    REG_TEAM: "team",
}


def _knowflow_ready() -> bool:
    settings = get_settings()
    return bool(settings.knowflow_enabled and knowflow_stack_reachable())


def _require_dataset_access(db: Session, user: User, dataset_id: str) -> None:
    ds_id = (dataset_id or "").strip()
    if not ds_id:
        raise bad_request("缺少知识库 id")
    if user_is_superuser(db, user):
        return
    if ds_id not in allowed_dataset_ids_for_user(db, user):
        raise forbidden("无权访问该知识库")


def _label_for_registry(db: Session, reg: RagflowScopeDataset) -> str:
    key = (reg.scope_key or "").strip()
    if reg.scope == REG_PERSONAL and key:
        return dataset_display_label_personal(db, key)
    if reg.scope in (REG_DEPARTMENT, REG_TEAM) and key:
        return dataset_display_label_dept(db, key)
    if reg.scope == REG_COMPANY:
        return dataset_display_label_company()
    return key or reg.ragflow_dataset_id or "知识库"


def _label_for_dataset(db: Session, dataset_id: str) -> str:
    reg = _registry_for_dataset_id(db, dataset_id)
    if reg:
        return _label_for_registry(db, reg)
    return dataset_id


def _scope_for_dataset(db: Session, dataset_id: str) -> str | None:
    reg = _registry_for_dataset_id(db, dataset_id)
    if not reg:
        return None
    return _SCOPE_OUT.get(reg.scope)


def _resolve_dataset_scope_context(db: Session, dataset_id: str) -> dict | None:
    reg = _registry_for_dataset_id(db, dataset_id)
    if not reg:
        return None
    scope = _SCOPE_OUT.get(reg.scope)
    owner_id: uuid.UUID | None = None
    dept_id: uuid.UUID | None = None
    if reg.scope == REG_PERSONAL:
        try:
            owner_id = uuid.UUID(reg.scope_key)
        except ValueError:
            return None
    elif reg.scope in (REG_DEPARTMENT, REG_TEAM):
        try:
            dept_id = uuid.UUID(reg.scope_key)
        except ValueError:
            return None
    return {
        "scope": scope,
        "owner_id": owner_id,
        "dept_id": dept_id,
        "registry": reg,
    }


def _shared_document_ids_for_user(db: Session, user: User) -> set[str]:
    from app.services.documents import listing as document_listing

    rows, _total = document_listing.list_shared_documents(
        db, user, page=1, page_size=10_000, keyword=None
    )
    return {str(doc.id) for doc, _meta in rows}


def _row_index_ready(row: dict) -> bool:
    from app.services.document_index_service import is_index_ready_meta

    return is_index_ready_meta(row)


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


def _map_document_tree_node(doc: dict, dataset_id: str) -> dict:
    ready = _row_index_ready(doc)
    return {
        "key": f"doc:{doc['document_id']}",
        "label": doc.get("title") or doc.get("file_name") or "未命名文档",
        "type": "document",
        "document_id": doc["document_id"],
        "dataset_id": dataset_id,
        "scope": doc.get("scope"),
        "knowledge_synced": bool(doc.get("knowledge_synced")),
        "parse_status": doc.get("parse_status"),
        "index_ready": ready,
        "is_leaf": True,
        "children": [],
    }


def _collect_dataset_document_rows(
    db: Session,
    user: User,
    dataset_id: str,
    *,
    shared_doc_ids: set[str] | None = None,
) -> list[dict]:
    """单次拉取知识库内全部文档行（批量补充解析状态）。"""
    if shared_doc_ids is None:
        shared_doc_ids = set()

    links = list(
        db.scalars(
            select(RagflowDocumentLink).where(RagflowDocumentLink.dataset_id == dataset_id)
        ).all()
    )
    rows: list[dict] = []
    for link in links:
        doc = get_document(db, link.platform_document_id)
        if not doc or doc.deleted_at:
            continue
        if not document_matches_dataset_link(db, doc, dataset_id):
            continue
        if not can_query_document(db, user, doc):
            continue
        title = (doc.title or "").strip() or "未命名文档"
        rows.append(
            {
                "document_id": str(doc.id),
                "title": title,
                "scope": doc.scope or "personal",
                "file_name": link.file_name or doc.file_name or "",
                "folder_id": str(doc.folder_id) if doc.folder_id else None,
                "ragflow_document_id": link.ragflow_document_id,
                "knowledge_synced": bool(link.ragflow_document_id),
                "synced_at": (
                    link.updated_at.isoformat() if link.updated_at else None
                ),
                "chunk_count": None,
                "parse_status": None,
            }
        )

    _apply_unified_index_meta_to_rows(db, user, rows)
    rows.sort(key=lambda r: (r.get("synced_at") or ""), reverse=True)
    return rows


def _document_matches_folder_filter(
    doc: Document,
    *,
    folder_id: uuid.UUID | None,
    virtual_folder: str | None,
    shared_doc_ids: set[str],
) -> bool:
    vf = (virtual_folder or "").strip()
    doc_id = str(doc.id)
    if vf == VIRTUAL_SHARED_ID:
        return doc_id in shared_doc_ids
    if vf == VIRTUAL_UNCATEGORIZED_ID:
        return doc.folder_id is None and doc_id not in shared_doc_ids
    if folder_id is not None:
        return doc.folder_id == folder_id
    return True


def _attach_folder_documents(
    folder_node: dict,
    grouped: dict[str, list[dict]],
    dataset_id: str,
) -> None:
    group_key = folder_node.get("virtual_folder_id") or folder_node.get("folder_id")
    docs = grouped.get(group_key or "", [])
    children = [_map_document_tree_node(doc, dataset_id) for doc in docs]
    folder_node["children"] = children
    folder_node["document_count"] = len(docs)
    folder_node["index_ready_count"] = sum(1 for doc in docs if _row_index_ready(doc))
    folder_node["is_leaf"] = len(children) == 0


def list_library_folders_for_tree(
    db: Session, user: User, dataset_id: str
) -> list[dict]:
    """知识检索树：文件夹节点下直接挂载文档子节点及可检索统计。"""
    _require_dataset_access(db, user, dataset_id)
    ctx = _resolve_dataset_scope_context(db, dataset_id)
    if not ctx:
        return []

    scope = ctx["scope"] or "personal"
    owner_id = ctx["owner_id"]
    dept_id = ctx["dept_id"]
    shared_doc_ids = (
        _shared_document_ids_for_user(db, user)
        if scope == REG_PERSONAL and owner_id == user.id
        else set()
    )

    all_docs = _collect_dataset_document_rows(
        db, user, dataset_id, shared_doc_ids=shared_doc_ids
    )
    grouped: dict[str, list[dict]] = {}
    for doc in all_docs:
        key = _folder_group_key(
            doc["document_id"],
            doc.get("folder_id"),
            shared_doc_ids=shared_doc_ids,
        )
        grouped.setdefault(key, []).append(doc)

    items: list[dict] = [
        {
            "key": f"folder:{dataset_id}:{VIRTUAL_UNCATEGORIZED_ID}",
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

    if scope == REG_PERSONAL and owner_id == user.id:
        items.append(
            {
                "key": f"folder:{dataset_id}:{VIRTUAL_SHARED_ID}",
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
    if scope == REG_PERSONAL and owner_id:
        stmt = stmt.where(DocumentLibraryFolder.owner_id == owner_id)
    elif scope in ORG_SCOPES and dept_id:
        stmt = stmt.where(DocumentLibraryFolder.dept_id == dept_id)

    folders = list(
        db.scalars(
            stmt.order_by(
                DocumentLibraryFolder.sort_order.asc(),
                DocumentLibraryFolder.created_at.asc(),
            )
        ).all()
    )
    for folder in folders:
        fid = str(folder.id)
        items.append(
            {
                "key": f"folder:{dataset_id}:{fid}",
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
        _attach_folder_documents(folder_node, grouped, dataset_id)

    return items


def _document_counts(db: Session, dataset_ids: set[str]) -> dict[str, int]:
    if not dataset_ids:
        return {}
    out: dict[str, int] = {str(ds_id): 0 for ds_id in dataset_ids}
    for link in db.scalars(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.dataset_id.in_(dataset_ids)
        )
    ).all():
        doc = get_document(db, link.platform_document_id)
        if not doc or doc.deleted_at:
            continue
        if not document_matches_dataset_link(db, doc, link.dataset_id):
            continue
        ds = str(link.dataset_id)
        out[ds] = out.get(ds, 0) + 1
    return out


def list_knowledge_libraries(db: Session, user: User) -> dict:
    allowed = allowed_dataset_ids_for_user(db, user)
    counts = _document_counts(db, allowed)
    items: list[dict] = []
    seen: set[str] = set()

    for reg in _scope_registries_for_user(db, user):
        ds_id = (reg.ragflow_dataset_id or "").strip()
        if not ds_id or ds_id not in allowed or ds_id in seen:
            continue
        seen.add(ds_id)
        items.append(
            {
                "dataset_id": ds_id,
                "label": _label_for_registry(db, reg),
                "scope": _SCOPE_OUT.get(reg.scope),
                "document_count": counts.get(ds_id, 0),
            }
        )

    for ds_id in sorted(allowed):
        if ds_id in seen:
            continue
        reg = _registry_for_dataset_id(db, ds_id)
        items.append(
            {
                "dataset_id": ds_id,
                "label": _label_for_registry(db, reg) if reg else _label_for_dataset(db, ds_id),
                "scope": _scope_for_dataset(db, ds_id),
                "document_count": counts.get(ds_id, 0),
            }
        )

    return {
        "items": items,
        "knowflow_enabled": _knowflow_ready(),
    }


def list_library_documents(
    db: Session,
    user: User,
    dataset_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    folder_id: uuid.UUID | None = None,
    virtual_folder: str | None = None,
    shared_doc_ids: set[str] | None = None,
) -> tuple[list[dict], int]:
    _require_dataset_access(db, user, dataset_id)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    kw = (keyword or "").strip().lower()
    vf = (virtual_folder or "").strip()
    if shared_doc_ids is None and vf in (VIRTUAL_SHARED_ID, VIRTUAL_UNCATEGORIZED_ID):
        shared_doc_ids = _shared_document_ids_for_user(db, user)
    elif shared_doc_ids is None:
        shared_doc_ids = set()

    links = list(
        db.scalars(
            select(RagflowDocumentLink).where(RagflowDocumentLink.dataset_id == dataset_id)
        ).all()
    )
    rows: list[dict] = []
    for link in links:
        doc = get_document(db, link.platform_document_id)
        if not doc or doc.deleted_at:
            continue
        if not document_matches_dataset_link(db, doc, dataset_id):
            continue
        if not can_query_document(db, user, doc):
            continue
        if folder_id is not None or vf:
            if not _document_matches_folder_filter(
                doc,
                folder_id=folder_id,
                virtual_folder=vf or None,
                shared_doc_ids=shared_doc_ids,
            ):
                continue
        title = (doc.title or "").strip() or "未命名文档"
        if kw and kw not in title.lower() and kw not in (link.file_name or "").lower():
            continue
        rows.append(
            {
                "document_id": str(doc.id),
                "title": title,
                "scope": doc.scope or "personal",
                "file_name": link.file_name or doc.file_name or "",
                "folder_id": str(doc.folder_id) if doc.folder_id else None,
                "ragflow_document_id": link.ragflow_document_id,
                "knowledge_synced": bool(link.ragflow_document_id),
                "synced_at": (
                    link.updated_at.isoformat() if link.updated_at else None
                ),
                "chunk_count": None,
                "parse_status": None,
            }
        )

    _apply_unified_index_meta_to_rows(db, user, rows)

    rows.sort(key=lambda r: (r.get("synced_at") or ""), reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return page_rows, total


def _apply_unified_index_meta_to_rows(
    db: Session, user: User, rows: list[dict]
) -> None:
    """库列表与检索树共用 document_index_service 读取层。"""
    if not rows:
        return
    from app.services.document_index_service import enrich_knowledge_document_rows
    from app.services.document_service import get_document

    documents = []
    for row in rows:
        raw_id = row.get("document_id")
        if not raw_id:
            continue
        try:
            doc = get_document(db, uuid.UUID(str(raw_id)))
        except (TypeError, ValueError):
            continue
        if doc and doc.deleted_at is None:
            documents.append(doc)
    enrich_knowledge_document_rows(db, user, rows, documents)


def _enrich_ragflow_doc_meta(
    db: Session, user: User, dataset_id: str, rows: list[dict]
) -> None:
    """从 KnowFlow 补充解析状态（run/chunk_num），便于判断是否需要重新解析。"""
    if not rows or not _knowflow_ready():
        return
    rag_ids = [str(r.get("ragflow_document_id") or "") for r in rows]
    rag_ids = [x for x in rag_ids if x]
    if not rag_ids:
        return

    meta_by_id, fetch_ok = fetch_ragflow_doc_meta_map(
        db, user, dataset_id, rag_ids
    )
    for row in rows:
        rid = str(row.get("ragflow_document_id") or "")
        _apply_row_ragflow_meta(row, meta_by_id.get(rid), fetch_ok=fetch_ok)


_RUN_STATUS_LABELS = {
    "0": "未解析",
    "1": "解析中",
    "2": "已取消",
    "3": "已完成",
    "4": "解析失败",
}


def summarize_ragflow_progress_msg(msg: str | None, *, max_len: int = 500) -> str | None:
    """从 RAGFlow 累积 progress_msg 中提取可读失败原因（优先 ERROR 行）。"""
    raw = str(msg or "").strip()
    if not raw:
        return None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    error_lines = [
        ln
        for ln in lines
        if "[ERROR]" in ln
        or "Visual model error" in ln
        or "Model disabled" in ln
    ]
    if error_lines:
        detail = error_lines[-1]
        if "Model disabled" in detail or (
            "403" in detail and "Error code" in detail
        ):
            return (
                "图表增强（视觉模型 IMAGE2TEXT）调用失败：API 返回 403，"
                "模型已停用或未开通（Model disabled）。"
                "请在「资源管理」配置视觉模型（IMAGE2TEXT）并保存同步，"
                "或在 KnowFlow 模型配置中更换可用的视觉模型。"
            )[:max_len]
        return detail[:max_len]
    tail = "\n".join(lines[-3:])
    if len(tail) <= max_len:
        return tail
    return tail[-max_len:]


def _rag_clients_for_user(db: Session, user: User) -> list[RagflowClient]:
    from app.services.ragflow_identity_service import get_user_ragflow_auth
    from app.services.ragflow_scope_service import _privileged_rag_client

    rags: list[RagflowClient] = []
    priv = _privileged_rag_client(db)
    if priv:
        rags.append(priv)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        rags.append(RagflowClient(session_auth=auth))
    return rags


def _ragflow_meta_cache_key(dataset_id: str, ragflow_id: str) -> str:
    from app.core.platform_cache import ragflow_doc_meta_cache_key

    return ragflow_doc_meta_cache_key(dataset_id, ragflow_id)


def _is_transient_ragflow_run(run: str | int | None) -> bool:
    """解析中（run=1）状态会变化，不可长期缓存。"""
    return str(run or "").strip() == "1"


def _read_ragflow_meta_cache(dataset_id: str, ragflow_id: str) -> dict | None:
    from app.config import get_settings
    from app.core.platform_cache import cache_get_json

    ttl = max(5, int(get_settings().knowledge_ragflow_meta_cache_ttl_sec))
    key = _ragflow_meta_cache_key(dataset_id, ragflow_id)
    hit = cache_get_json(key, ttl=ttl)
    if not isinstance(hit, dict):
        return None
    if _is_transient_ragflow_run(hit.get("run")):
        return None
    return hit


def _write_ragflow_meta_cache(dataset_id: str, ragflow_id: str, meta: dict) -> None:
    if _is_transient_ragflow_run(meta.get("run")):
        return
    from app.config import get_settings
    from app.core.platform_cache import cache_set_json

    ttl = max(5, int(get_settings().knowledge_ragflow_meta_cache_ttl_sec))
    key = _ragflow_meta_cache_key(dataset_id, ragflow_id)
    cache_set_json(key, meta, ttl=ttl)


def _fetch_document_run_map_from_mysql(
    db: Session | None, ragflow_ids: list[str]
) -> dict[str, dict]:
    """从 RAGFlow MySQL document 表批量读取 run/progress（比 API 缓存更权威）。"""
    ids = list({str(x).strip() for x in ragflow_ids if str(x or "").strip()})
    if not ids:
        return {}
    from app.services.model_settings_service import get_ragflow_mysql_settings

    _, password, db_name, host, port = get_ragflow_mysql_settings(db)
    if not password or not host:
        return {}
    try:
        import pymysql

        from app.config import get_settings

        settings = get_settings()
        conn = pymysql.connect(
            host=host,
            port=port,
            user="root",
            password=password,
            database=db_name,
            charset="utf8mb4",
            connect_timeout=settings.ragflow_mysql_connect_timeout,
            read_timeout=settings.ragflow_mysql_read_timeout,
            write_timeout=settings.ragflow_mysql_write_timeout,
        )
        placeholders = ",".join(["%s"] * len(ids))
        sql = (
            f"SELECT id, run, progress, progress_msg, chunk_num "
            f"FROM document WHERE id IN ({placeholders})"
        )
        with conn.cursor() as cur:
            cur.execute(sql, ids)
            rows = cur.fetchall()
        conn.close()
        out: dict[str, dict] = {}
        for rid, run, progress, msg, chunk_num in rows:
            out[str(rid)] = {
                "run": str(run) if run is not None else "",
                "progress": progress,
                "progress_msg": msg or "",
                "chunk_num": chunk_num,
            }
        return out
    except Exception as exc:
        logger.debug("RAGFlow MySQL document.run 批量查询失败: %s", exc)
        return {}


def _overlay_mysql_document_run_meta(
    db: Session | None,
    dataset_id: str,
    meta: dict[str, dict],
    ragflow_ids: list[str],
) -> None:
    """用 MySQL 中的 run 覆盖 API/缓存元数据，避免「解析中」陈旧缓存。"""
    mysql_map = _fetch_document_run_map_from_mysql(db, ragflow_ids)
    if not mysql_map:
        return
    for rid, row in mysql_map.items():
        merged = {**(meta.get(rid) or {}), **row}
        meta[rid] = merged
        if not _is_transient_ragflow_run(merged.get("run")):
            _write_ragflow_meta_cache(dataset_id, rid, merged)


_ragflow_health_cache: dict[str, tuple[float, bool]] = {}
_RAGFLOW_HEALTH_TTL_SEC = 30.0


def _ragflow_health_ok_cached(rag: RagflowClient) -> bool:
    base = str(getattr(rag, "base_url", "") or id(rag))
    now = time.monotonic()
    hit = _ragflow_health_cache.get(base)
    if hit and now - hit[0] < _RAGFLOW_HEALTH_TTL_SEC:
        return hit[1]
    ok = bool(rag.health_ok())
    _ragflow_health_cache[base] = (now, ok)
    return ok


def _rag_clients_for_background(db: Session, document: Document) -> list[RagflowClient]:
    """后台任务用：优先特权/管理员会话，不依赖用户是否仍在线登录。"""
    from app.services.ragflow_scope_service import _admin_rag_client, _privileged_rag_client

    rags: list[RagflowClient] = []
    seen: set[str] = set()

    def _add(client: RagflowClient | None) -> None:
        if client is None:
            return
        key = (client.session_auth or "") + "|" + (client.api_key or "")
        if key in seen:
            return
        seen.add(key)
        rags.append(client)

    _add(_privileged_rag_client(db))
    _add(_admin_rag_client())
    owner_id = document.owner_id
    if owner_id:
        owner = db.get(User, owner_id)
        if owner and owner.status == "active":
            for rag in _rag_clients_for_user(db, owner):
                _add(rag)
    return rags


def fetch_ragflow_doc_meta_map(
    db: Session,
    user: User,
    dataset_id: str,
    ragflow_ids: list[str],
    *,
    document: Document | None = None,
    background: bool = False,
) -> tuple[dict[str, dict], bool]:
    """按 ragflow 文档 id 拉取 run/chunk 元数据（按 id 直查 + 短 TTL 缓存）。"""
    wanted = {str(x).strip() for x in ragflow_ids if x}
    if not wanted or not _knowflow_ready():
        return {}, False

    meta: dict[str, dict] = {}
    missing = set(wanted)

    for rid in list(missing):
        cached = _read_ragflow_meta_cache(dataset_id, rid)
        if cached is not None:
            meta[rid] = cached
            missing.discard(rid)
    if not missing:
        _overlay_mysql_document_run_meta(db, dataset_id, meta, list(wanted))
        return meta, True

    if background and document is not None:
        rag_iter = _rag_clients_for_background(db, document)
    else:
        rag_iter = _rag_clients_for_user(db, user)

    for rag in rag_iter:
        if not _ragflow_health_ok_cached(rag) or not _dataset_visible(rag, dataset_id):
            continue
        fetched: dict[str, dict] = {}
        for rid in list(missing):
            try:
                doc_meta = rag.get_document_meta(dataset_id, rid)
                if doc_meta:
                    fetched[rid] = doc_meta
                    _write_ragflow_meta_cache(dataset_id, rid, doc_meta)
            except RagflowError:
                continue
            except Exception as exc:
                logger.debug(
                    "拉取 RAGFlow 元数据失败 doc=%s dataset=%s: %s",
                    rid,
                    dataset_id,
                    exc,
                )
        if fetched:
            meta.update(fetched)
            missing -= set(fetched.keys())
        if not missing:
            _overlay_mysql_document_run_meta(db, dataset_id, meta, list(wanted))
            return meta, True
    _overlay_mysql_document_run_meta(db, dataset_id, meta, list(wanted))
    return meta, bool(meta)


def _apply_row_ragflow_meta(row: dict, item: dict | None, *, fetch_ok: bool) -> None:
    row["_meta_fetch_ok"] = fetch_ok
    if not item:
        return
    run = str(item.get("run", ""))
    msg = (
        item.get("progress_msg")
        or item.get("process_msg")
        or item.get("message")
        or ""
    )
    if _is_transient_ragflow_run(run) and msg and (
        "[ERROR]" in str(msg)
        or "Model disabled" in str(msg)
        or "Visual model error" in str(msg)
    ):
        run = "4"
    row["parse_status"] = _RUN_STATUS_LABELS.get(run, run or None)
    chunk_num = item.get("chunk_num")
    try:
        row["chunk_count"] = int(chunk_num) if chunk_num is not None else None
    except (TypeError, ValueError):
        row["chunk_count"] = None
    progress_raw = item.get("progress")
    if progress_raw is not None:
        try:
            pct = float(progress_raw)
            row["parse_progress"] = (
                int(pct * 100) if 0 <= pct <= 1 else int(pct)
            )
        except (TypeError, ValueError):
            row["parse_progress"] = None
    if msg and str(msg).strip():
        row["parse_message"] = summarize_ragflow_progress_msg(msg) or str(msg).strip()[:500]


def _rag_clients_for_chunks(
    db: Session, user: User, doc: Document
) -> list[RagflowClient]:
    """列举切片时依次尝试：文档相关租户会话 → 当前用户 → 特权/bootstrap 会话。"""
    from app.services.ragflow_identity_service import get_user_ragflow_auth
    from app.services.ragflow_sync_service import _ragflow_clients_for_document

    clients: list[RagflowClient] = []
    seen: set[str] = set()

    def _add(client: RagflowClient | None) -> None:
        if client is None:
            return
        key = (client.session_auth or "") + "|" + (client.api_key or "")
        if key in seen:
            return
        seen.add(key)
        clients.append(client)

    for client in _ragflow_clients_for_document(db, doc):
        _add(client)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        _add(RagflowClient(session_auth=auth))
    kf = get_knowflow_client_for_user(db, user)
    if hasattr(kf, "_rag"):
        _add(kf._rag)
    return clients


def _dataset_visible(rag: RagflowClient, dataset_id: str) -> bool:
    try:
        for ds in rag.list_datasets():
            if str(ds.get("id")) == str(dataset_id):
                return True
    except RagflowError:
        return False
    return False


def _chunk_list_error_message(err: RagflowError, *, dataset_missing: bool) -> str:
    msg = str(err).strip()
    if dataset_missing:
        return (
            "知识库在 KnowFlow 中已不存在（索引失效），"
            "请在文档详情或本页点击「重新解析」重新同步。"
        )
    if "Tenant not found" in msg:
        return (
            "无法定位文档所属租户（多为历史索引与当前知识库不一致），"
            "请点击「重新解析」重新同步文档。"
        )
    return f"无法读取切片：{msg}"


def _normalize_chunk(raw: dict) -> dict:
    content = (
        raw.get("content_with_weight")
        or raw.get("content")
        or raw.get("text")
        or ""
    )
    page = raw.get("page_num") or raw.get("page")
    try:
        page_int = int(page) if page is not None else None
    except (TypeError, ValueError):
        page_int = None
    chunk_id = str(raw.get("chunk_id") or raw.get("id") or "")
    score = raw.get("similarity") or raw.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    return {
        "id": chunk_id,
        "content": str(content),
        "page": page_int,
        "score": score_f,
    }


def list_document_chunks(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 30,
    keywords: str | None = None,
) -> dict:
    from app.services.ragflow_version_link_service import resolve_index_link

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_query_document(db, user, doc):
        raise forbidden()

    link, version = resolve_index_link(db, doc, version_id=version_id)
    if not link or not link.ragflow_document_id:
        raise bad_request("该版本尚未同步到知识库，请先在文档详情中同步或重新索引")

    _require_dataset_access(db, user, link.dataset_id)

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    version_id_str = str(version.id) if version else None
    version_no = version.version_no if version else link.version_no

    if not _knowflow_ready():
        return {
            "document_id": str(document_id),
            "version_id": version_id_str,
            "version_no": version_no,
            "title": doc.title or "未命名文档",
            "dataset_id": link.dataset_id,
            "ragflow_document_id": link.ragflow_document_id,
            "chunk_count": 0,
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    clients = _rag_clients_for_chunks(db, user, doc)
    if not clients:
        return {
            "document_id": str(document_id),
            "version_id": version_id_str,
            "version_no": version_no,
            "title": doc.title or "未命名文档",
            "dataset_id": link.dataset_id,
            "ragflow_document_id": link.ragflow_document_id,
            "chunk_count": 0,
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    dataset_missing = all(
        not _dataset_visible(rag, link.dataset_id) for rag in clients if rag.health_ok()
    )
    last_err: RagflowError | None = None
    chunks: list[dict] = []
    total = 0
    doc_meta: dict | None = None

    for rag in clients:
        if not rag.health_ok():
            continue
        try:
            chunks, total, doc_meta = rag.list_document_chunks(
                link.dataset_id,
                link.ragflow_document_id,
                page=page,
                page_size=page_size,
                keywords=keywords,
            )
            last_err = None
            break
        except RagflowError as e:
            last_err = e
            logger.debug(
                "列举切片重试 doc=%s dataset=%s: %s",
                document_id,
                link.dataset_id,
                e,
            )

    if last_err is not None:
        logger.warning("列举切片失败 doc=%s: %s", document_id, last_err)
        raise bad_request(
            _chunk_list_error_message(last_err, dataset_missing=dataset_missing)
        ) from last_err

    chunk_count = 0
    if isinstance(doc_meta, dict):
        try:
            chunk_count = int(doc_meta.get("chunk_count") or 0)
        except (TypeError, ValueError):
            chunk_count = 0

    return {
        "document_id": str(document_id),
        "version_id": version_id_str,
        "version_no": version_no,
        "title": doc.title or "未命名文档",
        "dataset_id": link.dataset_id,
        "ragflow_document_id": link.ragflow_document_id,
        "chunk_count": chunk_count or total,
        "items": [_normalize_chunk(c) for c in chunks if isinstance(c, dict)],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def execute_document_reindex(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    parser_id: str = "naive",
    layout_recognize: str | None = None,
    resync: bool = False,
) -> dict:
    """切换切片方法并提交重新解析（后台任务或同步 API 共用）。"""
    from app.services.ragflow_sync_service import sync_document_to_knowflow
    from app.services.ragflow_version_link_service import (
        get_version_link_by_version_id,
        resolve_index_link,
        upsert_version_link,
    )

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()

    version_link, version = resolve_index_link(db, doc, version_id=version_id)
    if not version:
        raise bad_request("未找到可索引的文档版本")

    from app.services.knowledge_parser_service import build_parser_config

    parser, parser_config = build_parser_config(parser_id, layout_recognize)

    dataset_missing = False
    if version_link:
        from app.services.ragflow_scope_service import _dataset_exists_in_knowflow

        dataset_missing = not _dataset_exists_in_knowflow(
            db, version_link.dataset_id
        )

    if resync or not version_link or dataset_missing:
        from app.services.ragflow_sync_service import KnowflowSyncError

        try:
            rid = sync_document_to_knowflow(
                db, user, doc, force=True, version_id=version.id
            )
        except KnowflowSyncError as e:
            raise bad_request(str(e)) from e
        db.flush()
        if not rid:
            raise bad_request("重新同步知识库失败，请检查文件与知识服务状态")
        version_link = get_version_link_by_version_id(db, version.id)

    if not version_link or not version_link.ragflow_document_id:
        raise bad_request("该版本尚未同步到知识库")

    from app.services.ragflow_version_link_service import clear_version_index_completed

    clear_version_index_completed(db, version.id)

    _require_dataset_access(db, user, version_link.dataset_id)

    from app.services.ragflow_scope_service import prepare_dataset_for_upload
    from app.services.ragflow_sync_service import (
        _sync_context_for_document,
        _upload_rag_clients,
    )

    provision_user, kf_ctx = _sync_context_for_document(db, user, doc)
    prepare_dataset_for_upload(
        db,
        doc,
        version_link.dataset_id,
        actor=user,
        provision_user=provision_user,
    )
    parser_clients = _upload_rag_clients(
        db, actor=provision_user, document=doc, kf=kf_ctx
    )

    last_err: RagflowError | None = None
    for rag in parser_clients:
        if not rag.health_ok():
            continue
        try:
            rag.change_document_parser(
                version_link.ragflow_document_id,
                parser,
                parser_config=parser_config,
            )
            from app.core.platform_cache import invalidate_ragflow_doc_meta_cache

            invalidate_ragflow_doc_meta_cache(version_link.dataset_id)
            rag.parse_documents(
                version_link.dataset_id, [version_link.ragflow_document_id]
            )
            upsert_version_link(
                db,
                document=doc,
                version=version,
                ragflow_document_id=version_link.ragflow_document_id,
                dataset_id=version_link.dataset_id,
                file_name=version_link.file_name,
                platform_user_id=version_link.platform_user_id,
                parser_id=parser,
            )
            return {
                "document_id": str(document_id),
                "version_id": str(version.id),
                "version_no": version.version_no,
                "parser_id": parser,
                "layout_recognize": parser_config.get("layout_recognize"),
                "ragflow_document_id": version_link.ragflow_document_id,
                "dataset_id": version_link.dataset_id,
                "message": "已切换切片与 PDF 解析器并提交重新解析",
            }
        except RagflowError as e:
            last_err = e
            logger.debug("reindex 重试 doc=%s: %s", document_id, e)

    if last_err:
        raise bad_request(f"重新解析失败：{last_err}") from last_err
    raise bad_request("知识服务未就绪，无法重新解析")


def reindex_document(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    parser_id: str = "naive",
    layout_recognize: str | None = None,
    resync: bool = False,
) -> dict:
    """切换切片方法并重新解析；提交后台任务，进度在「后台任务」查看。"""
    from app.domains.knowledge.gateway import knowledge
    from app.services.knowledge_sync_job_service import enqueue_document_reindex
    from app.services.ragflow_version_link_service import resolve_index_link

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_query_document(db, user, doc):
        raise forbidden()
    if not knowledge.enabled():
        raise bad_request("知识库同步未启用")
    if not knowledge.stack_reachable():
        raise bad_request("知识服务不可用，请稍后重试")

    _version_link, version = resolve_index_link(db, doc, version_id=version_id)
    if not version:
        raise bad_request("未找到可索引的文档版本")

    job = enqueue_document_reindex(
        db,
        user_id=user.id,
        document_id=document_id,
        version_id=version.id,
        parser_id=parser_id,
        layout_recognize=layout_recognize,
        resync=resync,
        document_title=doc.title,
    )
    if not job:
        raise bad_request("无法创建索引任务，请稍后重试")

    return {
        "document_id": str(document_id),
        "version_id": str(version.id),
        "version_no": version.version_no,
        "parser_id": parser_id,
        "layout_recognize": layout_recognize,
        "queued": True,
        "knowledge_job_id": str(job.id),
        "message": "已加入后台任务，正在重新索引，请在「后台任务」查看进度。",
    }
