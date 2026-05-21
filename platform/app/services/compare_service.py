"""Document compare orchestration."""

from __future__ import annotations

import difflib
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.integrations.text_extract import (
    ParsedDocument,
    extract_text_from_bytes,
    local_search,
    split_paragraphs,
)
from app.models.compare import CompareDiffItem, CompareJob, CompareSearchHit, CompareStatus
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.services.document_service import get_document
from app.storage.object_store import get_object_store


def _parse_uuid_list(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in ids]


def validate_document_scope(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
    *,
    min_count: int = 1,
    max_count: int = 4,
) -> list[Document]:
    if len(document_ids) < min_count or len(document_ids) > max_count:
        from app.core.exceptions import bad_request

        raise bad_request(f"请选择 {min_count}–{max_count} 份文档")
    docs: list[Document] = []
    for did in document_ids:
        doc = get_document(db, did)
        if not doc or doc.deleted_at:
            from app.core.exceptions import bad_request

            raise bad_request(f"文档不存在: {did}")
        if not can_access_document(db, user, doc, PermissionLevel.use.value):
            from app.core.exceptions import forbidden

            raise forbidden(f"无权使用文档: {doc.title}")
        if not doc.current_version_id:
            from app.core.exceptions import bad_request

            raise bad_request(f"文档未上传文件: {doc.title}")
        docs.append(doc)
    return docs


def validate_compare_documents(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
) -> list[Document]:
    return validate_document_scope(
        db, user, document_ids, min_count=2, max_count=4
    )


def list_compare_documents(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    from app.services.document_service import list_translatable_documents

    rows, total = list_translatable_documents(
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


def load_parsed_documents(db: Session, docs: list[Document]) -> list[ParsedDocument]:
    store = get_object_store()
    parsed: list[ParsedDocument] = []
    for doc in docs:
        version = db.get(DocumentVersion, doc.current_version_id)
        if not version:
            continue
        data = store.get_object_bytes(version.file_key)
        parsed.append(
            extract_text_from_bytes(
                data,
                document_id=doc.id,
                file_name=version.file_name,
                mime_type=version.mime_type,
            )
        )
    return parsed


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


def run_compare_job(db: Session, job_id: uuid.UUID) -> CompareJob:
    job = db.get(CompareJob, job_id)
    if not job:
        raise ValueError("Compare job not found")

    job.status = CompareStatus.running.value
    job.started_at = datetime.now(timezone.utc)
    job.progress = 10
    db.commit()

    try:
        doc_ids = _parse_uuid_list(job.document_ids)
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
            ]
        }
        job.progress = 40
        db.commit()

        db.query(CompareDiffItem).filter(CompareDiffItem.job_id == job.id).delete()
        base_parsed = by_id.get(base_id)
        if not base_parsed:
            raise ValueError("Base document parse failed")

        for did in doc_ids:
            if did == base_id:
                continue
            other = by_id.get(did)
            if not other:
                continue
            pair_key = f"{base_id}:{did}"
            for item in _diff_pair(base_parsed, other):
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


def search_compare_job(
    db: Session,
    job: CompareJob,
    query: str,
    *,
    limit: int = 20,
) -> list[CompareSearchHit]:
    user = db.get(User, job.created_by)
    if not user:
        return []
    doc_ids = _parse_uuid_list(job.document_ids)
    docs = validate_compare_documents(db, user, doc_ids)
    parsed = load_parsed_documents(db, docs)
    hits = local_search(parsed, query, limit=limit)

    db.query(CompareSearchHit).filter(
        CompareSearchHit.job_id == job.id,
        CompareSearchHit.query == query,
    ).delete()

    rows: list[CompareSearchHit] = []
    for h in hits:
        row = CompareSearchHit(
            job_id=job.id,
            query=query,
            document_id=uuid.UUID(h["document_id"]),
            snippet=h["snippet"],
            score=h["score"],
            anchor_json=h.get("anchor_json"),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


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
    for did in _parse_uuid_list(job.document_ids):
        d = get_document(db, did)
        if d:
            doc_titles[str(did)] = d.title

    return {
        "id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "base_document_id": str(job.base_document_id),
        "document_ids": job.document_ids,
        "document_titles": doc_titles,
        "options": job.options or {},
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
