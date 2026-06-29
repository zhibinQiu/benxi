"""Document compare orchestration."""

from __future__ import annotations

import difflib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import PermissionLevel, can_access_document
from app.core.uuid_utils import parse_uuid_list
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.integrations.text_extract import (
    ParsedDocument,
    extract_text_from_bytes,
    local_search,
    split_paragraphs,
)
from app.models.compare import CompareDiffItem, CompareJob, CompareSearchHit, CompareStatus
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.services.document_service import get_document, list_compareable_documents
from app.storage.object_store import get_object_store

logger = logging.getLogger(__name__)


def _document_retrieval_ready(
    db: Session,
    doc: Document,
    *,
    index_ready_ids: set[str],
    allow_index_only: bool,
) -> bool:
    from app.services.document_service import resolve_current_version

    if resolve_current_version(db, doc, repair=True):
        return True
    return allow_index_only and str(doc.id) in index_ready_ids


def validate_document_scope(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
    *,
    min_count: int = 1,
    max_count: int = 4,
    required_level: str | None = None,
    allow_index_only: bool = False,
    omit_unready: bool = False,
) -> list[Document]:
    if len(document_ids) < min_count or len(document_ids) > max_count:
        from app.core.exceptions import bad_request

        raise bad_request(f"请选择 {min_count}–{max_count} 份文档")

    from app.core.user_messages import (
        DOCUMENT_COMPARE_NO_FILE,
        KNOWLEDGE_QA_DOC_UNAVAILABLE,
    )
    from app.services.document_index_service import (
        enrich_document_index_meta,
        is_index_ready_meta,
    )

    index_ready_ids: set[str] = set()
    if allow_index_only:
        candidates: list[Document] = []
        for did in document_ids:
            doc = get_document(db, did)
            if doc and not doc.deleted_at:
                candidates.append(doc)
        if candidates:
            meta_by_doc = enrich_document_index_meta(
                db, user, candidates, live_ragflow=False
            )
            index_ready_ids = {
                did
                for did, meta in meta_by_doc.items()
                if is_index_ready_meta(meta)
            }

    docs: list[Document] = []
    skipped_titles: list[str] = []
    for did in document_ids:
        doc = get_document(db, did)
        if not doc or doc.deleted_at:
            from app.core.exceptions import bad_request

            raise bad_request(f"文档不存在: {did}")
        level = required_level or PermissionLevel.query.value
        if not can_access_document(db, user, doc, level):
            from app.core.exceptions import forbidden

            raise forbidden(f"无权使用文档: {doc.title}")
        title = (doc.title or "未命名文档").strip() or "未命名文档"
        if _document_retrieval_ready(
            db,
            doc,
            index_ready_ids=index_ready_ids,
            allow_index_only=allow_index_only,
        ):
            docs.append(doc)
            continue
        if omit_unready:
            skipped_titles.append(title)
            logger.debug("知识检索跳过未就绪文档: %s (%s)", title, doc.id)
            continue
        from app.core.exceptions import bad_request

        message = (
            KNOWLEDGE_QA_DOC_UNAVAILABLE.format(title=title)
            if allow_index_only
            else DOCUMENT_COMPARE_NO_FILE.format(title=title)
        )
        raise bad_request(message)
    if len(docs) < min_count:
        from app.core.exceptions import bad_request

        if skipped_titles and len(document_ids) > 1:
            raise bad_request(
                "所选文档均暂不可检索，请确认已上传文件并完成知识库索引。"
                f"（已跳过：{'、'.join(skipped_titles[:5])}"
                f"{'…' if len(skipped_titles) > 5 else ''}）"
            )
        title = skipped_titles[0] if skipped_titles else "文档"
        message = (
            KNOWLEDGE_QA_DOC_UNAVAILABLE.format(title=title)
            if allow_index_only
            else DOCUMENT_COMPARE_NO_FILE.format(title=title)
        )
        raise bad_request(message)
    return docs


def validate_compare_documents(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
) -> list[Document]:
    return validate_document_scope(
        db,
        user,
        document_ids,
        min_count=2,
        max_count=4,
        required_level=PermissionLevel.query.value,
    )


def get_document_file_bytes(
    db: Session, user: User, document_id: uuid.UUID
) -> tuple[bytes, str, str]:
    """返回文档原始字节，供对比页内嵌预览（同源 + Bearer）。"""
    from app.services.document_service import resolve_current_version

    docs = validate_document_scope(db, user, [document_id], min_count=1, max_count=1)
    doc = docs[0]
    version = resolve_current_version(db, doc)
    if not version:
        from app.core.exceptions import bad_request

        raise bad_request("文档版本不存在")
    data = get_object_store().get_object_bytes(version.file_key)
    mime = version.mime_type or "application/octet-stream"
    return data, mime, version.file_name


def get_document_content(
    db: Session, user: User, document_id: uuid.UUID
) -> dict:
    """解析单份文档，供对比页预览（无需先创建比对任务）。"""
    docs = validate_document_scope(db, user, [document_id], min_count=1, max_count=1)
    parsed = load_parsed_documents(db, docs)[0]
    return {
        "document_id": str(parsed.document_id),
        "file_name": parsed.file_name,
        "full_text": parsed.full_text,
        "pages": parsed.pages,
        "parse_quality": parsed.parse_quality,
        "warning": parsed.warning,
        "char_count": len(parsed.full_text),
    }


def list_compare_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    rows, total = list_compareable_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        {
            "id": str(doc.id),
            "title": doc.title,
            "file_name": ver.file_name,
            "file_size": ver.file_size,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
        for doc, ver in rows
    ]
    return items, total


def compute_paragraph_diffs(
    base: ParsedDocument,
    other: ParsedDocument,
) -> list[dict]:
    """段落级 diff（左=base，右=other）。"""
    return _diff_pair(base, other)


def _parsed_document_from_blocks(
    version: DocumentVersion, payload: dict
) -> ParsedDocument:
    return ParsedDocument(
        document_id=version.document_id,
        file_name=version.file_name,
        full_text=(payload.get("full_text") or "").strip(),
        pages=payload.get("pages") or [],
        parse_quality=payload.get("parse_quality") or "blocks",
        warning=None,
    )


def _load_cached_parsed_version(
    db: Session, version: DocumentVersion
) -> ParsedDocument | None:
    """仅读 DB 已缓存分块，不触发 OCR / MinIO。"""
    from app.services.document_version_block_service import (
        blocks_to_content_dict,
        load_version_blocks,
    )

    blocks = load_version_blocks(db, version.id)
    if not blocks:
        return None
    payload = blocks_to_content_dict(blocks)
    if not (payload.get("full_text") or "").strip():
        return None
    return _parsed_document_from_blocks(version, payload)


def load_parsed_version(db: Session, version: DocumentVersion) -> ParsedDocument:
    """优先复用已缓存分块（含 OCR）；缺失时再解析并落库。"""
    cached = _load_cached_parsed_version(db, version)
    if cached:
        return cached

    from app.services.document_version_block_service import (
        blocks_to_content_dict,
        ensure_version_blocks,
        parse_version_document,
    )

    try:
        blocks = ensure_version_blocks(db, version)
        if blocks:
            return _parsed_document_from_blocks(
                version, blocks_to_content_dict(blocks)
            )
    except Exception:
        logger.warning(
            "版本分块落库失败，回退现场解析 doc=%s version=%s",
            version.document_id,
            version.id,
            exc_info=True,
        )
        db.rollback()
        try:
            return parse_version_document(db, version)
        except Exception:
            logger.warning(
                "现场解析失败，回退文本层提取 doc=%s version=%s",
                version.document_id,
                version.id,
                exc_info=True,
            )

    store = get_object_store()
    data = store.get_object_bytes(version.file_key)
    return extract_text_from_bytes(
        data,
        document_id=version.document_id,
        file_name=version.file_name,
        mime_type=version.mime_type,
    )


def get_document_content_for_version(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> dict:
    docs = validate_document_scope(db, user, [document_id], min_count=1, max_count=1)
    doc = docs[0]
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != doc.id or version.file_size <= 0:
        from app.core.exceptions import bad_request

        raise bad_request("版本不存在或未上传")

    from app.services.document_version_block_service import (
        blocks_to_content_dict,
        ensure_version_blocks,
    )

    blocks = ensure_version_blocks(db, version)
    if blocks:
        payload = blocks_to_content_dict(blocks)
    else:
        parsed = load_parsed_version(db, version)
        payload = {
            "pages": parsed.pages,
            "full_text": parsed.full_text,
            "parse_quality": parsed.parse_quality,
            "blocks": [],
        }

    return {
        "document_id": str(document_id),
        "version_id": str(version_id),
        "version_no": version.version_no,
        "file_name": version.file_name,
        "full_text": payload["full_text"],
        "pages": payload["pages"],
        "blocks": payload.get("blocks") or [],
        "parse_quality": payload.get("parse_quality"),
        "warning": None,
        "char_count": len(payload.get("full_text") or ""),
    }


def load_parsed_documents(db: Session, docs: list[Document]) -> list[ParsedDocument]:
    from app.services.document_service import resolve_current_version

    if not docs:
        return []

    def _load_one(session: Session, doc: Document) -> ParsedDocument | None:
        version = resolve_current_version(session, doc)
        if not version:
            return None
        try:
            return load_parsed_version(session, version)
        except Exception:
            logger.warning(
                "文档解析失败 doc=%s version=%s",
                doc.id,
                version.id,
                exc_info=True,
            )
            return None

    if len(docs) == 1:
        one = _load_one(db, docs[0])
        return [one] if one else []

    from concurrent.futures import ThreadPoolExecutor

    from app.database import SessionLocal

    def _load_one_thread(doc: Document) -> ParsedDocument | None:
        session = SessionLocal()
        try:
            return _load_one(session, doc)
        finally:
            session.close()

    workers = min(4, len(docs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [p for p in pool.map(_load_one_thread, docs) if p is not None]


def _diff_pair(
    base: ParsedDocument,
    other: ParsedDocument,
) -> list[dict]:
    base_paras = split_paragraphs(base.full_text)
    other_paras = split_paragraphs(other.full_text)
    matcher = difflib.SequenceMatcher(None, base_paras, other_paras)
    items: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left = "\n\n".join(base_paras[i1:i2]) if i1 < i2 else None
        right = "\n\n".join(other_paras[j1:j2]) if j1 < j2 else None
        if tag == "delete":
            dtype = "delete"
        elif tag == "insert":
            dtype = "add"
        else:
            dtype = "modify"
        items.append(
            {
                "diff_type": dtype,
                "text_left": left,
                "text_right": right,
                "anchor_json": {
                    "page": 1,
                    "bbox": None,
                    "kind": "paragraph",
                },
            }
        )
    return items


def _diff_pair_git_style(
    base: ParsedDocument,
    other: ParsedDocument,
) -> list[dict]:
    """跨文档全文 unified diff（与单文档 Git diff 解析一致）。"""
    from app.services.document_git_service import parse_git_unified_diff

    left_lines = (base.full_text or "").splitlines()
    right_lines = (other.full_text or "").splitlines()
    diff_lines = difflib.unified_diff(
        left_lines,
        right_lines,
        fromfile=base.file_name or "参照",
        tofile=other.file_name or "对比",
        lineterm="",
    )
    items = parse_git_unified_diff("\n".join(diff_lines))
    if items:
        return [
            {
                "diff_type": it["diff_type"],
                "text_left": it.get("text_left"),
                "text_right": it.get("text_right"),
                "anchor_json": {
                    **(it.get("anchor_json") or {}),
                    "kind": "git_hunk",
                },
            }
            for it in items
        ]
    return _diff_pair(base, other)


def run_compare_job(db: Session, job_id: uuid.UUID) -> CompareJob:
    job = db.get(CompareJob, job_id)
    if not job:
        raise ValueError("Compare job not found")

    job.status = CompareStatus.running.value
    job.started_at = datetime.now(timezone.utc)
    job.progress = 10
    db.commit()

    try:
        doc_ids = parse_uuid_list(job.document_ids)
        user = db.get(User, job.created_by)
        if not user:
            raise ValueError("User not found")
        docs = validate_compare_documents(db, user, doc_ids)
        base_id = job.base_document_id
        parsed_list = load_parsed_documents(db, docs)
        by_id = {p.document_id: p for p in parsed_list}

        job.payload = {
            "parsed": [
                {
                    "document_id": str(p.document_id),
                    "file_name": p.file_name,
                    "parse_quality": p.parse_quality,
                    "warning": p.warning,
                    "char_count": len(p.full_text),
                }
                for p in parsed_list
            ],
            "documents": {
                str(p.document_id): {
                    "file_name": p.file_name,
                    "pages": p.pages,
                    "full_text": p.full_text,
                }
                for p in parsed_list
            },
            "knowflow": {},
        }
        job.progress = 40
        db.commit()

        db.query(CompareDiffItem).filter(CompareDiffItem.job_id == job.id).delete()
        base_parsed = by_id.get(base_id)
        if not base_parsed:
            raise ValueError("Base document parse failed")

        from app.services.compare_llm_service import compare_documents_with_llm

        llm_summary = ""
        for did in doc_ids:
            if did == base_id:
                continue
            other = by_id.get(did)
            if not other:
                continue
            pair_key = f"{base_id}:{did}"
            diff_items, pair_summary = compare_documents_with_llm(base_parsed, other)
            if pair_summary:
                llm_summary = pair_summary
            for item in diff_items:
                db.add(
                    CompareDiffItem(
                        job_id=job.id,
                        pair_key=pair_key,
                        doc_a_id=base_id,
                        doc_b_id=did,
                        diff_type=item["diff_type"],
                        text_left=item.get("text_left"),
                        text_right=item.get("text_right"),
                        anchor_json=item.get("anchor_json"),
                    )
                )

        payload = dict(job.payload or {})
        payload["llm_summary"] = llm_summary
        payload["compare_engine"] = "llm"
        job.payload = payload

        job.progress = 90
        job.status = CompareStatus.done.value
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 100
        db.commit()
        db.refresh(job)
        return job
    except Exception as e:
        job.status = CompareStatus.failed.value
        job.error_message = str(e)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        raise


def _existing_ragflow_doc_map(
    db: Session,
    user: User,
    docs: list[Document],
) -> dict[str, str]:
    """返回文档库已有索引映射；对比功能不触发建索引（文档须先入文档库并完成解析）。"""
    from app.services.ragflow_sync_service import allowed_ragflow_doc_map

    ids = [str(d.id) for d in docs]
    return allowed_ragflow_doc_map(db, user, ids)


def _retrieve_compare_hits(
    db: Session,
    user: User,
    *,
    parsed: list[ParsedDocument],
    scope_ids: list[str],
    query: str,
    ragflow_map: dict[str, str],
    limit: int = 20,
    field_match: bool = True,
) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    kf = get_knowflow_client_for_user(db, user)
    if hasattr(kf, "_doc_map"):
        kf._doc_map.update(ragflow_map)

    scoped_parsed = [p for p in parsed if str(p.document_id) in scope_ids]
    hits: list[dict] = []
    if kf.enabled() and get_settings().knowflow_enabled:
        hits = kf.retrieve(
            parsed,
            q,
            document_ids=scope_ids,
            limit=limit,
        )
        for h in hits:
            h.setdefault("source", "knowflow")
    if not hits:
        hits = local_search(
            scoped_parsed or parsed,
            q,
            limit=limit,
            field_match=field_match,
        )
    return hits


def search_compare_documents(
    db: Session,
    user: User,
    *,
    right_document_id: uuid.UUID,
    query: str,
    field_match: bool = True,
    limit: int = 20,
) -> list[dict]:
    """在右侧目标文档内检索；左侧仅作参照，不要求与右侧一致。"""
    docs = validate_document_scope(
        db, user, [right_document_id], min_count=1, max_count=1
    )
    parsed = load_parsed_documents(db, docs)
    scope_ids = [str(right_document_id)]
    ragflow_map = _existing_ragflow_doc_map(db, user, docs)
    hits = _retrieve_compare_hits(
        db,
        user,
        parsed=parsed,
        scope_ids=scope_ids,
        query=query,
        ragflow_map=ragflow_map,
        limit=limit,
        field_match=field_match,
    )
    return [
        {
            "document_id": str(right_document_id),
            "snippet": h["snippet"],
            "score": float(h.get("score") or 0),
            "anchor_json": h.get("anchor_json"),
            "source": h.get("source", "local"),
            "side": "right",
        }
        for h in hits
    ]


def search_compare_job(
    db: Session,
    job: CompareJob,
    query: str,
    *,
    limit: int = 20,
    scope: str = "right",
    field_match: bool = True,
) -> list[dict]:
    user = db.get(User, job.created_by)
    if not user:
        return []
    doc_ids = parse_uuid_list(job.document_ids)
    docs = validate_compare_documents(db, user, doc_ids)
    parsed = load_parsed_documents(db, docs)

    right_id = str(job.options.get("right_document_id", "")) if job.options else ""
    if not right_id and len(doc_ids) >= 2:
        right_id = str(doc_ids[1])

    scope_ids: list[str]
    if scope == "both":
        scope_ids = [str(d) for d in doc_ids]
    else:
        scope_ids = [right_id] if right_id else [str(d) for d in doc_ids]

    ragflow_map = (job.payload or {}).get("knowflow", {}).get("ragflow_doc_map") or {}
    if not ragflow_map:
        sync_docs = docs
        if scope == "right" and right_id:
            sync_docs = [d for d in docs if str(d.id) == right_id] or docs
        ragflow_map = _existing_ragflow_doc_map(db, user, sync_docs)

    hits = _retrieve_compare_hits(
        db,
        user,
        parsed=parsed,
        scope_ids=scope_ids,
        query=query,
        ragflow_map=ragflow_map,
        limit=limit,
        field_match=field_match,
    )

    db.query(CompareSearchHit).filter(
        CompareSearchHit.job_id == job.id,
        CompareSearchHit.query == query.strip(),
    ).delete()

    rows: list[CompareSearchHit] = []
    out: list[dict] = []
    for h in hits:
        did = uuid.UUID(h["document_id"])
        row = CompareSearchHit(
            job_id=job.id,
            query=query.strip(),
            document_id=did,
            snippet=h["snippet"],
            score=float(h.get("score") or 0),
            anchor_json=h.get("anchor_json"),
        )
        db.add(row)
        rows.append(row)
        out.append(
            {
                "document_id": str(did),
                "snippet": h["snippet"],
                "score": float(h.get("score") or 0),
                "anchor_json": h.get("anchor_json"),
                "source": h.get("source", "local"),
                "side": "right" if str(did) == right_id else "left",
            }
        )
    db.commit()
    for i, row in enumerate(rows):
        out[i]["id"] = str(row.id)
    return out


def create_compare_job(
    db: Session,
    user: User,
    *,
    left_document_id: uuid.UUID,
    right_document_id: uuid.UUID,
) -> CompareJob:
    if left_document_id == right_document_id:
        from app.core.exceptions import bad_request

        raise bad_request("左右两侧请选择不同文档")
    docs = validate_compare_documents(
        db, user, [left_document_id, right_document_id]
    )
    job = CompareJob(
        created_by=user.id,
        base_document_id=left_document_id,
        document_ids=[str(left_document_id), str(right_document_id)],
        status=CompareStatus.pending.value,
        options={
            "left_document_id": str(left_document_id),
            "right_document_id": str(right_document_id),
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_user_compare_job(
    db: Session, job_id: uuid.UUID, user_id: uuid.UUID
) -> CompareJob | None:
    job = db.get(CompareJob, job_id)
    if not job or job.created_by != user_id:
        return None
    return job


def list_user_compare_jobs(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
) -> tuple[list[CompareJob], int]:
    base = select(CompareJob).where(CompareJob.created_by == user_id)
    total = db.scalar(select(func.count()).select_from(base)) or 0
    items = db.scalars(
        base.order_by(CompareJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def job_to_dict(db: Session, job: CompareJob) -> dict:
    diffs = db.scalars(
        select(CompareDiffItem)
        .where(CompareDiffItem.job_id == job.id)
        .order_by(CompareDiffItem.pair_key)
    ).all()
    doc_titles: dict[str, str] = {}
    for did in parse_uuid_list(job.document_ids):
        d = get_document(db, did)
        if d:
            doc_titles[str(did)] = d.title

    opts = job.options or {}
    left_id = opts.get("left_document_id") or str(job.base_document_id)
    right_id = opts.get("right_document_id") or (
        str(job.document_ids[1])
        if job.document_ids and len(job.document_ids) > 1
        else ""
    )

    return {
        "id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "left_document_id": left_id,
        "right_document_id": right_id,
        "base_document_id": str(job.base_document_id),
        "document_ids": job.document_ids,
        "document_titles": doc_titles,
        "options": opts,
        "payload": job.payload or {},
        "diff_items": [
            {
                "id": str(d.id),
                "pair_key": d.pair_key,
                "doc_a_id": str(d.doc_a_id),
                "doc_b_id": str(d.doc_b_id),
                "diff_type": d.diff_type,
                "text_left": d.text_left,
                "text_right": d.text_right,
                "anchor_json": d.anchor_json,
            }
            for d in diffs
        ],
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
