"""资讯/收藏导入文档库：入库即为 PDF，后台任务负责知识库索引。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.models.org import User
from app.services.documents.crud import get_document
from app.services.job_service import create_job, update_job_status

logger = logging.getLogger(__name__)


def replace_version_file_content(
    db: Session,
    version,
    *,
    file_name: str,
    mime_type: str,
    content: bytes,
) -> None:
    from app.storage.object_store import compute_md5_hex, get_object_store

    store = get_object_store()
    new_key = store.build_file_key(version.document_id, version.version_no, file_name)
    store.put_object_bytes(new_key, content, mime_type)
    old_key = version.file_key
    version.file_key = new_key
    version.file_name = file_name
    version.mime_type = mime_type or "application/octet-stream"
    version.file_size = len(content)
    version.checksum = compute_md5_hex(content)
    db.flush()
    if old_key and old_key != new_key:
        try:
            store.delete_object(old_key)
        except Exception as exc:
            logger.debug("删除旧版本对象跳过 key=%s: %s", old_key, exc)


def enqueue_subscription_import_finalize(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    sync_knowflow: bool = True,
    source: str,
    source_id: uuid.UUID,
    title: str = "",
    link: str = "",
    source_label: str = "",
    html_body: str = "",
    summary: str = "",
    fallback_stem: str = "subscription-article",
) -> Job:
    from app.models.job import JobType

    job = create_job(
        db,
        job_type=JobType.subscription_import.value,
        created_by=user.id,
        document_id=document_id,
        payload={
            "document_id": str(document_id),
            "sync_knowflow": sync_knowflow,
            "source": source,
            "source_id": str(source_id),
            "title": title,
            "link": link,
            "source_label": source_label,
            "html_body": html_body,
            "summary": summary,
            "fallback_stem": fallback_stem,
        },
        commit=False,
    )
    from app.core.db_after_commit import run_after_commit

    run_after_commit(db, lambda: _start_subscription_import_thread(job.id))
    return job


def _start_subscription_import_thread(job_id: uuid.UUID) -> None:
    from app.services.background_job_dispatch import dispatch_subscription_import_job

    dispatch_subscription_import_job(job_id)


def run_subscription_import_job(job_id: uuid.UUID) -> None:
    import time

    from app.database import SessionLocal
    from app.integrations.html_document_export import html_body_to_pdf_bytes
    from app.models.document import DocumentVersion

    work: dict | None = None
    db = SessionLocal()
    try:
        job = None
        for attempt in range(8):
            job = db.get(Job, job_id)
            if job:
                break
            if attempt < 7:
                db.close()
                time.sleep(0.25 * (attempt + 1))
                db = SessionLocal()
        if not job:
            logger.warning("资讯导入任务不存在（可能事务尚未提交） job=%s", job_id)
            return
        if job.status not in (JobStatus.pending.value, JobStatus.running.value):
            return

        payload = job.payload or {}
        user = db.get(User, job.created_by)
        doc = get_document(db, job.document_id) if job.document_id else None
        if not user or not doc or doc.deleted_at:
            update_job_status(
                db,
                job_id,
                JobStatus.cancelled.value,
                error_message="文档已删除",
            )
            db.commit()
            return

        update_job_status(db, job_id, JobStatus.running.value, progress=10)
        version = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
        if not version:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message="文档无可用版本",
            )
            db.commit()
            return

        work = {
            "job_id": job_id,
            "user_id": user.id,
            "document_id": doc.id,
            "version_id": version.id,
            "document_title": doc.title,
            "title": (payload.get("title") or doc.title or "article").strip(),
            "link": (payload.get("link") or "").strip(),
            "source_label": (payload.get("source_label") or "").strip(),
            "html_body": (payload.get("html_body") or "").strip(),
            "summary": (payload.get("summary") or "").strip(),
            "fallback_stem": (payload.get("fallback_stem") or "subscription-article").strip(),
            "sync_knowflow": bool(payload.get("sync_knowflow", True)),
        }
        update_job_status(db, job_id, JobStatus.running.value, progress=20)
        db.commit()
    except Exception as exc:
        logger.exception("资讯导入任务初始化失败 job=%s", job_id)
        try:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=str(exc)[:500],
            )
            db.commit()
        except Exception:
            pass
        return
    finally:
        db.close()

    if not work:
        return

    db = SessionLocal()
    index_job_id: uuid.UUID | None = None
    try:
        from app.storage.object_store import get_object_store

        version = db.get(DocumentVersion, work["version_id"])
        if not version:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message="文档版本不存在",
            )
            db.commit()
            return

        store = get_object_store()
        try:
            stored = store.get_object_bytes(version.file_key)
        except Exception as exc:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=f"读取文档文件失败：{exc}"[:500],
            )
            db.commit()
            return

        if not stored.startswith(b"%PDF"):
            try:
                file_name, pdf_bytes, mime_type = html_body_to_pdf_bytes(
                    work["title"],
                    work["html_body"] or f"<p>{work['summary']}</p>",
                    summary=work["summary"],
                    link=work["link"],
                    source_label=work["source_label"],
                    fallback_stem=work["fallback_stem"],
                    allow_refetch=False,
                )
            except Exception as exc:
                logger.exception("资讯导入 PDF 生成失败 job=%s", job_id)
                update_job_status(
                    db,
                    job_id,
                    JobStatus.failed.value,
                    error_message=f"PDF 生成失败：{exc}"[:500],
                )
                db.commit()
                return
            replace_version_file_content(
                db,
                version,
                file_name=file_name,
                mime_type=mime_type,
                content=pdf_bytes,
            )

        update_job_status(db, job_id, JobStatus.running.value, progress=70)
        db.commit()

        if work["sync_knowflow"]:
            from app.domains.knowledge.gateway import knowledge

            if knowledge.enabled():
                from app.services.knowledge_sync_job_service import (
                    create_document_knowledge_index_job,
                )

                index_job = create_document_knowledge_index_job(
                    db,
                    user_id=work["user_id"],
                    document_id=work["document_id"],
                    version_id=work["version_id"],
                    force=True,
                    document_title=work["document_title"],
                )
                if index_job:
                    index_job_id = index_job.id
                    db.commit()
    except Exception as exc:
        logger.exception("资讯导入后台任务失败 job=%s", job_id)
        try:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=str(exc)[:500],
            )
            db.commit()
        except Exception:
            pass
        return
    finally:
        db.close()

    knowflow_synced = False
    if index_job_id:
        from app.services.background_job_dispatch import dispatch_document_index_job

        dispatch_document_index_job(index_job_id)
        knowflow_synced = True

    db = SessionLocal()
    try:
        from app.core.platform_cache import invalidate_document_caches

        invalidate_document_caches(str(work["user_id"]))
        update_job_status(
            db,
            job_id,
            JobStatus.done.value,
            progress=100,
            error_message=None,
        )
        db.commit()
        logger.info(
            "资讯导入后台完成 doc=%s job=%s knowflow=%s",
            work["document_id"],
            job_id,
            knowflow_synced,
        )
    except Exception as exc:
        logger.exception("资讯导入任务收尾失败 job=%s", job_id)
        try:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=str(exc)[:500],
            )
            db.commit()
        except Exception:
            pass
    finally:
        db.close()
