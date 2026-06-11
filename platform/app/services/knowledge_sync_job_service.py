"""文档知识库同步与解析 — 后台任务（可追踪进度）。"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from sqlalchemy.orm import Session

from app.domains.knowledge.gateway import knowledge
from app.models.job import Job, JobStatus, JobType
from app.models.org import User
from app.services.document_service import get_document
from app.services.job_service import create_job, update_job_status
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

_PARSE_DONE = {"3", "DONE", "done"}
_PARSE_FAILED = {"2", "4", "FAIL", "fail", "CANCEL", "cancel"}


def _parse_run_status(
    db: Session, user: User, *, dataset_id: str, ragflow_document_id: str
) -> tuple[str | None, int | None, int | None, str | None]:
    from app.services.knowledge_library_service import fetch_ragflow_doc_meta_map

    meta_by_id, fetch_ok = fetch_ragflow_doc_meta_map(
        db, user, dataset_id, [ragflow_document_id]
    )
    if not fetch_ok:
        return None, None, None, None
    item = meta_by_id.get(str(ragflow_document_id))
    if not item:
        return None, None, None, None
    run = str(item.get("run", ""))
    from app.services.knowledge_library_service import _RUN_STATUS_LABELS

    label = _RUN_STATUS_LABELS.get(run, run or None)
    chunk_num = item.get("chunk_num")
    try:
        chunks = int(chunk_num) if chunk_num is not None else None
    except (TypeError, ValueError):
        chunks = None
    progress_raw = item.get("progress")
    progress_pct: int | None = None
    if progress_raw is not None:
        try:
            pct = float(progress_raw)
            progress_pct = int(pct * 100) if 0 <= pct <= 1 else int(pct)
            progress_pct = max(0, min(100, progress_pct))
        except (TypeError, ValueError):
            progress_pct = None
    msg = (
        item.get("progress_msg")
        or item.get("process_msg")
        or item.get("message")
        or ""
    )
    detail = str(msg).strip()[:500] if msg else None
    return label, chunks, progress_pct, detail


def _format_parse_failure(status: str | None, detail: str | None) -> str:
    base = status or "解析失败"
    if detail and detail not in base:
        return f"{base}：{detail}"
    return base


def _wait_for_parse(
    db: Session,
    user: User,
    job: Job,
    *,
    dataset_id: str,
    ragflow_document_id: str,
    timeout_sec: int = 600,
) -> None:
    deadline = time.time() + timeout_sec
    progress = 68
    while time.time() < deadline:
        status, _chunks, rag_progress, detail = _parse_run_status(
            db,
            user,
            dataset_id=dataset_id,
            ragflow_document_id=ragflow_document_id,
        )
        if status in ("已完成", "已索引") or (
            status and str(status).lower() in _PARSE_DONE
        ):
            update_job_status(db, job.id, JobStatus.running.value, progress=95)
            return
        if status in ("解析失败", "已取消") or (
            status and str(status).upper() in _PARSE_FAILED
        ):
            raise RuntimeError(_format_parse_failure(status, detail))
        if status == "索引失效":
            raise RuntimeError("文档解析失败：索引失效")
        if status is None:
            # 无法读取状态时略等后重试，不虚增到 90%
            update_job_status(db, job.id, JobStatus.running.value, progress=min(progress, 75))
            time.sleep(3)
            continue
        if rag_progress is not None and rag_progress >= 0:
            progress = max(68, min(94, rag_progress))
        elif status == "解析中":
            progress = min(94, progress + 1)
        update_job_status(db, job.id, JobStatus.running.value, progress=progress)
        time.sleep(2)
    raise RuntimeError(
        "文档解析等待超时（可能文件较大或解析服务繁忙），请稍后在文档详情查看索引状态"
    )


def run_document_knowledge_index_job(job_id: uuid.UUID) -> None:
    from app.database import SessionLocal
    from app.services.ragflow_sync_service import KnowflowSyncError, sync_document_to_knowflow

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        if job.status not in (JobStatus.pending.value, JobStatus.running.value):
            return

        payload = job.payload or {}
        user = db.get(User, job.created_by)
        doc = get_document(db, job.document_id) if job.document_id else None
        if not user or not doc or doc.deleted_at is not None:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                progress=0,
                error_message="文档或用户不存在",
            )
            return

        version_id_raw = payload.get("version_id")
        version_id = uuid.UUID(str(version_id_raw)) if version_id_raw else None
        force = bool(payload.get("force", True))
        mode = str(payload.get("mode") or "index")

        update_job_status(db, job_id, JobStatus.running.value, progress=8)

        if not knowledge.enabled():
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message="知识库同步未启用",
            )
            return

        if not knowledge.stack_reachable():
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message="知识服务不可用，请稍后重试",
            )
            return

        update_job_status(db, job_id, JobStatus.running.value, progress=18)
        try:
            knowledge.user_auth(db, user)
            knowledge.reconcile_catalog(db, user, sync_documents=False)
        except Exception as e:
            logger.warning("知识库任务目录对齐跳过 job=%s: %s", job_id, e)

        if mode == "reindex":
            from app.services.knowledge_library_service import execute_document_reindex

            update_job_status(db, job_id, JobStatus.running.value, progress=32)
            try:
                result = execute_document_reindex(
                    db,
                    user,
                    doc.id,
                    version_id=version_id,
                    parser_id=str(payload.get("parser_id") or "naive"),
                    layout_recognize=payload.get("layout_recognize"),
                    resync=bool(payload.get("resync")),
                )
                db.commit()
            except Exception as e:
                from app.core.user_messages import sanitize_user_message

                err_text = sanitize_user_message(str(e), fallback="重新索引失败")
                update_job_status(
                    db,
                    job_id,
                    JobStatus.failed.value,
                    error_message=err_text[:500],
                )
                create_notification(
                    db,
                    user_id=user.id,
                    title="文档重新索引失败",
                    body=(
                        f"「{doc.title or '未命名文档'}」重新索引未完成：{err_text}"
                    ),
                    link=f"/documents/{doc.id}",
                )
                db.commit()
                return

            dataset_id = result.get("dataset_id")
            rid = result.get("ragflow_document_id")
        else:
            update_job_status(db, job_id, JobStatus.running.value, progress=32)
            rid = sync_document_to_knowflow(
                db,
                user,
                doc,
                force=force,
                version_id=version_id,
            )
            db.commit()

            if not rid:
                update_job_status(
                    db,
                    job_id,
                    JobStatus.failed.value,
                    error_message="知识库同步失败（文档已保存，可在详情页重新索引）",
                )
                return

            from app.services.ragflow_version_link_service import (
                get_version_link_by_version_id,
            )

            vl = (
                get_version_link_by_version_id(db, version_id)
                if version_id
                else None
            )
            link = knowledge.document_link(db, doc.id)
            dataset_id = (
                (vl.dataset_id if vl else None)
                or (link.dataset_id if link else None)
                or payload.get("dataset_id")
            )

        update_job_status(db, job_id, JobStatus.running.value, progress=68)

        if dataset_id and rid:
            try:
                _wait_for_parse(
                    db,
                    user,
                    job,
                    dataset_id=str(dataset_id),
                    ragflow_document_id=str(rid),
                )
            except RuntimeError as e:
                update_job_status(
                    db,
                    job_id,
                    JobStatus.failed.value,
                    error_message=str(e),
                )
                fail_title = (
                    "文档重新索引失败" if mode == "reindex" else "文档索引未完成"
                )
                create_notification(
                    db,
                    user_id=user.id,
                    title=fail_title,
                    body=(
                        f"「{doc.title or '未命名文档'}」已上传保存，但知识库解析未完成：{e}。"
                        "可在文档详情 → 知识索引中重试。"
                    ),
                    link=f"/documents/{doc.id}",
                )
                db.commit()
                return

        update_job_status(db, job_id, JobStatus.done.value, progress=100)
        from app.models.document import DocumentVersion
        from app.services.document_service import resolve_current_version
        from app.services.ragflow_version_link_service import (
            bind_document_to_indexed_version,
            mark_version_index_completed,
        )

        current = resolve_current_version(db, doc)
        indexed_version_id = version_id or (current.id if current else None)
        if indexed_version_id:
            vl = mark_version_index_completed(db, indexed_version_id)
            ver = db.get(DocumentVersion, indexed_version_id)
            if vl and ver:
                bind_document_to_indexed_version(
                    db, document=doc, version=ver, version_link=vl
                )
        done_title = "文档重新索引完成" if mode == "reindex" else "文档索引完成"
        done_body = (
            f"「{doc.title or '未命名文档'}」已应用新解析配置并完成索引，可用于问答检索。"
            if mode == "reindex"
            else f"「{doc.title or '未命名文档'}」已同步到知识库并完成解析，可用于问答检索。"
        )
        create_notification(
            db,
            user_id=user.id,
            title=done_title,
            body=done_body,
            link=f"/documents/{doc.id}",
        )
        db.commit()
    except KnowflowSyncError as e:
        db.rollback()
        try:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=e.message,
            )
            db.commit()
        except Exception:
            pass
    except Exception as e:
        logger.exception("知识库索引任务失败 job=%s", job_id)
        db.rollback()
        try:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=str(e)[:500],
            )
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _start_job_thread(job_id: uuid.UUID) -> None:
    threading.Thread(
        target=run_document_knowledge_index_job,
        args=(job_id,),
        daemon=True,
        name=f"knowledge-index-{job_id}",
    ).start()


def create_document_knowledge_index_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    force: bool = True,
    document_title: str | None = None,
) -> Job | None:
    if not knowledge.enabled():
        return None

    doc = get_document(db, document_id)
    title = (document_title or (doc.title if doc else "") or "").strip()

    return create_job(
        db,
        job_type=JobType.document_index.value,
        created_by=user_id,
        document_id=document_id,
        payload={
            "document_id": str(document_id),
            "version_id": str(version_id) if version_id else None,
            "document_title": title or "未命名文档",
            "force": force,
        },
    )


def enqueue_document_knowledge_index(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    force: bool = True,
    document_title: str | None = None,
) -> Job | None:
    """创建后台任务并异步执行同步+解析。"""
    job = create_document_knowledge_index_job(
        db,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        force=force,
        document_title=document_title,
    )
    if job:
        _start_job_thread(job.id)
    return job


def schedule_knowledge_index_after_upload(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> Job | None:
    return enqueue_document_knowledge_index(
        db,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        force=True,
    )


def create_document_reindex_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    parser_id: str = "naive",
    layout_recognize: str | None = None,
    resync: bool = False,
    document_title: str | None = None,
) -> Job | None:
    if not knowledge.enabled():
        return None

    doc = get_document(db, document_id)
    title = (document_title or (doc.title if doc else "") or "").strip()

    return create_job(
        db,
        job_type=JobType.document_index.value,
        created_by=user_id,
        document_id=document_id,
        payload={
            "mode": "reindex",
            "document_id": str(document_id),
            "version_id": str(version_id) if version_id else None,
            "document_title": title or "未命名文档",
            "parser_id": parser_id,
            "layout_recognize": layout_recognize,
            "resync": resync,
        },
    )


def enqueue_document_reindex(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    parser_id: str = "naive",
    layout_recognize: str | None = None,
    resync: bool = False,
    document_title: str | None = None,
) -> Job | None:
    """创建后台任务：切换解析器并重新索引。"""
    job = create_document_reindex_job(
        db,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        parser_id=parser_id,
        layout_recognize=layout_recognize,
        resync=resync,
        document_title=document_title,
    )
    if job:
        _start_job_thread(job.id)
    return job
