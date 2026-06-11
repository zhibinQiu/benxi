"""Platform-side PDF translation jobs (backed by pdf2zh worker)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.document_scope import content_subscription_import_scope
from app.core.exceptions import bad_request
from app.integrations.pdf2zh_client import pdf2zh_base_url
from app.models.job import Job, JobStatus, JobType
from app.models.org import User
from app.services.job_service import create_job, update_job_status
from app.services.notification_service import create_notification

_LANG_LABELS = {
    "en": "英语",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "ja": "日语",
    "ko": "韩语",
    "de": "德语",
    "fr": "法语",
    "es": "西班牙语",
    "ru": "俄语",
}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=pdf2zh_base_url(), timeout=httpx.Timeout(60.0))


def pdf2zh_job_id(job: Job) -> str | None:
    if not job.payload:
        return None
    return job.payload.get("pdf2zh_job_id")


def job_to_dict(job: Job) -> dict[str, Any]:
    p = job.payload or {}
    files = p.get("files") or {}
    return {
        "platform_job_id": str(job.id),
        "pdf2zh_job_id": p.get("pdf2zh_job_id"),
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "stage": p.get("stage"),
        "error_message": job.error_message,
        "file_name": p.get("file_name"),
        "lang_in": p.get("lang_in"),
        "lang_out": p.get("lang_out"),
        "service": p.get("service"),
        "files": files,
        "imported_document_id": p.get("imported_document_id"),
        "imported_variant": p.get("imported_variant"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def get_user_job(db: Session, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
    job = db.get(Job, job_id)
    if not job or job.created_by != user_id:
        return None
    if job.type != JobType.pdf_translate.value:
        return None
    return job


def list_translate_jobs(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
) -> tuple[list[Job], int]:
    base = select(Job).where(
        Job.created_by == user_id,
        Job.type == JobType.pdf_translate.value,
    )
    total = db.scalar(select(func.count()).select_from(base)) or 0
    items = db.scalars(
        base.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def create_translate_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    pdf2zh_job_id_str: str,
    file_name: str,
    lang_in: str,
    lang_out: str,
    service: str,
    document_id: uuid.UUID | None = None,
) -> Job:
    payload: dict[str, Any] = {
        "pdf2zh_job_id": pdf2zh_job_id_str,
        "file_name": file_name,
        "lang_in": lang_in,
        "lang_out": lang_out,
        "service": service,
        "stage": "",
        "files": {},
    }
    if document_id is not None:
        payload["document_id"] = str(document_id)
    job = create_job(
        db,
        job_type=JobType.pdf_translate.value,
        created_by=user_id,
        payload=payload,
    )
    update_job_status(db, job.id, JobStatus.running.value, progress=0)
    from workers.tasks.translate import monitor_translate_job

    monitor_translate_job.delay(str(job.id))
    return job


def sync_job_from_pdf2zh(db: Session, job: Job) -> Job:
    zid = pdf2zh_job_id(job)
    if not zid:
        return job
    try:
        with httpx.Client(base_url=pdf2zh_base_url(), timeout=30.0) as client:
            r = client.get(f"/api/jobs/{zid}")
            r.raise_for_status()
            remote = r.json()
    except Exception as e:
        job.error_message = str(e)
        db.commit()
        return job

    progress = remote.get("progress") or {}
    overall = int(progress.get("overall_progress") or 0)
    stage = progress.get("stage") or ""
    status = remote.get("status") or job.status
    files = remote.get("files") or {}

    payload = dict(job.payload or {})
    payload["stage"] = stage
    payload["files"] = files
    job.payload = payload
    job.progress = overall

    terminal = (
        JobStatus.done.value,
        JobStatus.failed.value,
        JobStatus.cancelled.value,
    )
    if status in terminal and job.status not in terminal:
        update_job_status(
            db,
            job.id,
            status,
            progress=100 if status == JobStatus.done.value else overall,
            error_message=remote.get("error"),
        )
        db.refresh(job)
        if status == JobStatus.done.value:
            title = payload.get("file_name") or "文档"
            create_notification(
                db,
                user_id=job.created_by,
                title="PDF 翻译完成",
                body=f"《{title}》已翻译完成，点击查看结果。",
                link=f"/system/translate?job={job.id}",
            )
    else:
        if status == "running":
            job.status = JobStatus.running.value
        job.progress = overall
        db.commit()
        db.refresh(job)
    return job


def _lang_label(code: str | None) -> str:
    key = (code or "").strip()
    return _LANG_LABELS.get(key, key or "译文")


def _import_title(job: Job, *, variant: str) -> str:
    p = job.payload or {}
    stem = Path(p.get("file_name") or "document.pdf").stem
    lang_out = _lang_label(p.get("lang_out"))
    if variant == "dual":
        return f"{stem}（双语 {lang_out}）"[:500]
    return f"{stem}（译文 {lang_out}）"[:500]


def _fetch_translate_output_bytes(job: Job, variant: str) -> tuple[bytes, str]:
    kind = (variant or "mono").strip().lower()
    if kind not in ("mono", "dual"):
        raise bad_request("variant 仅支持 mono 或 dual")
    zid = pdf2zh_job_id(job)
    if not zid:
        raise bad_request("翻译任务缺少远程 ID")
    try:
        with httpx.Client(base_url=pdf2zh_base_url(), timeout=120.0) as client:
            r = client.get(f"/api/jobs/{zid}/download/{kind}")
            r.raise_for_status()
            content = r.content
            disp = r.headers.get("content-disposition") or ""
    except httpx.HTTPError as e:
        raise bad_request(f"读取翻译结果失败：{e}") from e
    if not content:
        raise bad_request("翻译结果文件为空")
    match = re.search(r'filename="?([^";]+)"?', disp)
    file_name = match.group(1) if match else f"{kind}.pdf"
    if not file_name.lower().endswith(".pdf"):
        file_name = f"{file_name}.pdf"
    return content, file_name


def _enqueue_knowledge_sync(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    from app.domains.knowledge.gateway import knowledge
    from app.models.document import Document
    from app.models.org import User
    from app.services.document_service import resolve_current_version

    if not knowledge.enabled():
        return False
    doc = db.get(Document, document_id)
    user = db.get(User, user_id)
    if not doc or not user:
        return False
    if not resolve_current_version(db, doc):
        return False
    knowledge.enqueue_sync_after_ingest(document_id, user_id)
    return True


def import_job_to_library(
    db: Session,
    user: User,
    job: Job,
    *,
    variant: str = "mono",
    sync_knowflow: bool = True,
) -> dict:
    """将已完成翻译任务的 PDF 结果导入「个人级」文档库并可选同步知识库。"""
    if job.status != JobStatus.done.value:
        raise bad_request("翻译尚未完成，无法入库")
    kind = (variant or "mono").strip().lower()
    if kind not in ("mono", "dual"):
        raise bad_request("variant 仅支持 mono 或 dual")

    payload = dict(job.payload or {})
    existing_id = payload.get("imported_document_id")
    if existing_id:
        try:
            doc_uuid = uuid.UUID(str(existing_id))
        except ValueError as e:
            raise bad_request("入库记录无效") from e
        from app.services.document_service import get_document

        doc = get_document(db, doc_uuid)
        if doc and not doc.deleted_at:
            synced = (
                _enqueue_knowledge_sync(db, user.id, doc.id) if sync_knowflow else False
            )
            return {
                "document_id": doc.id,
                "title": doc.title,
                "knowflow_synced": synced,
                "variant": payload.get("imported_variant") or kind,
                "message": "该翻译结果已入库",
                "already_imported": True,
            }

    content, file_name = _fetch_translate_output_bytes(job, kind)
    title = _import_title(job, variant=kind)
    scope = content_subscription_import_scope()

    from app.services.document_service import create_document, create_initial_uploaded_version

    doc = create_document(
        db,
        user,
        title=title,
        description=(
            f"由 PDF 翻译任务导入（{kind}）\n"
            f"原文件：{payload.get('file_name') or ''}\n"
            f"语言：{payload.get('lang_in') or ''} → {payload.get('lang_out') or ''}"
        ).strip(),
        scope=scope,
    )
    create_initial_uploaded_version(
        db,
        doc,
        user,
        file_name=file_name,
        mime_type="application/pdf",
        content=content,
    )
    db.refresh(doc)

    payload["imported_document_id"] = str(doc.id)
    payload["imported_variant"] = kind
    job.payload = payload
    db.commit()
    db.refresh(job)

    synced = _enqueue_knowledge_sync(db, user.id, doc.id) if sync_knowflow else False
    return {
        "document_id": doc.id,
        "title": doc.title,
        "knowflow_synced": synced,
        "variant": kind,
        "message": "已添加到个人级文档库，正在后台同步知识库索引",
        "already_imported": False,
    }
