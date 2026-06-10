"""平台原生切片库管理：列举分级库、库内文档与切片（不嵌入 KnowFlow UI）。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.document_scope import can_query_document
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import user_is_superuser
from app.integrations.knowflow_client import get_knowflow_client_for_user, knowflow_stack_reachable
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.models.document import Document
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
    SCOPE_TEAM as REG_TEAM,
    SCOPE_PERSONAL as REG_PERSONAL,
    RagflowScopeDataset,
)
from app.services.document_service import get_document
from app.services.ragflow_naming import (
    dataset_display_label_company,
    dataset_display_label_dept,
    dataset_display_label_personal,
)
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


def _document_counts(db: Session, dataset_ids: set[str]) -> dict[str, int]:
    if not dataset_ids:
        return {}
    rows = db.execute(
        select(RagflowDocumentLink.dataset_id, func.count())
        .where(RagflowDocumentLink.dataset_id.in_(dataset_ids))
        .group_by(RagflowDocumentLink.dataset_id)
    ).all()
    return {str(ds_id): int(cnt) for ds_id, cnt in rows}


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
) -> tuple[list[dict], int]:
    _require_dataset_access(db, user, dataset_id)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    kw = (keyword or "").strip().lower()

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
        if not can_query_document(db, user, doc):
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
                "ragflow_document_id": link.ragflow_document_id,
                "synced_at": link.updated_at,
                "chunk_count": None,
                "parse_status": None,
            }
        )

    _enrich_ragflow_doc_meta(db, user, dataset_id, rows)

    rows.sort(key=lambda r: (r.get("synced_at") or ""), reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return page_rows, total


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

    from app.services.ragflow_identity_service import get_user_ragflow_auth
    from app.services.ragflow_scope_service import _privileged_rag_client

    rags: list[RagflowClient] = []
    priv = _privileged_rag_client(db)
    if priv:
        rags.append(priv)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        rags.append(RagflowClient(session_auth=auth))

    meta_by_id: dict[str, dict] = {}
    for rag in rags:
        if not rag.health_ok() or not _dataset_visible(rag, dataset_id):
            continue
        try:
            docs, _ = rag.list_dataset_documents(
                dataset_id, page=1, page_size=max(len(rag_ids), 30)
            )
            for item in docs:
                rid = str(item.get("id") or item.get("doc_id") or "")
                if rid:
                    meta_by_id[rid] = item
            if meta_by_id:
                break
        except RagflowError:
            continue
        except Exception as exc:
            logger.warning(
                "补充索引元数据失败 dataset=%s: %s", dataset_id, exc
            )
            continue

    for row in rows:
        rid = str(row.get("ragflow_document_id") or "")
        item = meta_by_id.get(rid)
        if not item:
            if not meta_by_id:
                row["parse_status"] = "索引失效"
            continue
        run = str(item.get("run", ""))
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
        msg = (
            item.get("progress_msg")
            or item.get("process_msg")
            or item.get("message")
            or ""
        )
        if msg and str(msg).strip():
            row["parse_message"] = str(msg).strip()[:500]


_RUN_STATUS_LABELS = {
    "0": "未解析",
    "1": "解析中",
    "2": "已取消",
    "3": "已完成",
    "4": "解析失败",
}


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
    parser_id: str = "smart",
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
        clients = _rag_clients_for_chunks(db, user, doc)
        dataset_missing = bool(clients) and all(
            not _dataset_visible(rag, version_link.dataset_id)
            for rag in clients
            if rag.health_ok()
        )

    if resync or not version_link or dataset_missing:
        rid = sync_document_to_knowflow(
            db, user, doc, force=True, version_id=version.id
        )
        db.flush()
        if not rid:
            raise bad_request("重新同步知识库失败，请检查文件与知识服务状态")
        version_link = get_version_link_by_version_id(db, version.id)

    if not version_link or not version_link.ragflow_document_id:
        raise bad_request("该版本尚未同步到知识库")

    _require_dataset_access(db, user, version_link.dataset_id)

    last_err: RagflowError | None = None
    for rag in _rag_clients_for_chunks(db, user, doc):
        if not rag.health_ok():
            continue
        try:
            rag.change_document_parser(
                version_link.ragflow_document_id,
                parser,
                parser_config=parser_config,
            )
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
    parser_id: str = "smart",
    layout_recognize: str | None = None,
    resync: bool = False,
) -> dict:
    """切换切片方法并重新解析；索引失效时可先 resync 全量同步。"""
    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_query_document(db, user, doc):
        raise forbidden()
    return execute_document_reindex(
        db,
        user,
        document_id,
        version_id=version_id,
        parser_id=parser_id,
        layout_recognize=layout_recognize,
        resync=resync,
    )
