"""文档知识库同步与解析 — 后台任务（可追踪进度）。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.knowledge.gateway import knowledge
from app.models.document import Document
from app.models.job import Job, JobStatus, JobType
from app.models.org import User
from app.services.document_service import get_document
from app.services.job_service import create_job, update_job_status
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

_PARSE_DONE = {"3", "DONE", "done"}
_PARSE_FAILED = {"2", "4", "FAIL", "fail", "CANCEL", "cancel"}
_PARSE_RUNNING = {"1", "RUNNING", "running"}

_parse_watch_lock = threading.Lock()
_active_parse_watches: set[uuid.UUID] = set()

_INDEX_JOB_TERMINAL = frozenset(
    {
        JobStatus.done.value,
        JobStatus.failed.value,
        JobStatus.cancelled.value,
    }
)


def _index_target_exists(
    db: Session,
    document_id: uuid.UUID | None,
    version_id: uuid.UUID | None = None,
) -> bool:
    """文档/版本仍存在且未软删时，索引任务才可继续。"""
    if not document_id:
        return False
    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at is not None:
        return False
    if version_id is None:
        return True
    from app.models.document import DocumentVersion

    ver = db.get(DocumentVersion, version_id)
    return ver is not None and ver.document_id == document_id


def _collect_document_index_jobs(
    db: Session,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> list[Job]:
    from app.services.ragflow_version_link_service import get_version_link_by_version_id

    doc_str = str(document_id)
    version_str = str(version_id) if version_id else None
    ragflow_ids: set[str] = set()
    if version_id is not None:
        vl = get_version_link_by_version_id(db, version_id)
        if vl and (vl.ragflow_document_id or "").strip():
            ragflow_ids.add(vl.ragflow_document_id.strip())

    matched: list[Job] = []
    for job in db.scalars(
        select(Job).where(Job.type == JobType.document_index.value)
    ).all():
        payload = job.payload or {}
        payload_doc = (payload.get("document_id") or "").strip()
        if job.document_id != document_id and payload_doc != doc_str:
            continue
        if version_id is None:
            matched.append(job)
            continue
        job_version = (payload.get("version_id") or "").strip()
        job_rid = (payload.get("ragflow_document_id") or "").strip()
        if job_version == version_str or job_rid in ragflow_ids:
            matched.append(job)
    return matched


def stop_document_index_work(
    db: Session,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> int:
    """终止与文档/版本关联的后台索引与解析续跑（用户删除文件时调用）。"""
    stopped = 0
    for job in _collect_document_index_jobs(db, document_id, version_id=version_id):
        payload = dict(job.payload or {})
        had_watch = bool(payload.get("awaiting_parse"))
        payload.pop("awaiting_parse", None)
        payload.pop("parse_watch_started_at", None)
        job.payload = payload
        if job.status in (JobStatus.pending.value, JobStatus.running.value):
            update_job_status(
                db,
                job.id,
                JobStatus.cancelled.value,
                error_message="文档或版本已删除",
            )
            stopped += 1
        elif had_watch:
            db.add(job)
            db.flush()
            stopped += 1
        with _parse_watch_lock:
            _active_parse_watches.discard(job.id)
    if stopped:
        logger.info(
            "已终止文档索引任务 doc=%s version=%s count=%s",
            document_id,
            version_id,
            stopped,
        )
    return stopped


def cancel_document_index_job(
    db: Session, job: Job, *, reason: str = "用户已终止"
) -> Job:
    """用户从后台任务面板终止文档索引/解析（含解析续跑）。"""
    from app.core.exceptions import bad_request

    payload = dict(job.payload or {})
    awaiting_parse = bool(payload.get("awaiting_parse"))
    if job.status not in (JobStatus.pending.value, JobStatus.running.value) and not awaiting_parse:
        raise bad_request("仅「等待中」或「运行中」的任务可终止")

    payload.pop("awaiting_parse", None)
    payload.pop("parse_watch_started_at", None)
    job.payload = payload
    with _parse_watch_lock:
        _active_parse_watches.discard(job.id)

    return update_job_status(
        db,
        job.id,
        JobStatus.cancelled.value,
        error_message=reason,
    )


def _index_job_should_abort(db: Session, job: Job) -> bool:
    fresh = db.get(Job, job.id)
    if fresh is None:
        return True
    job.status = fresh.status
    if fresh.status == JobStatus.cancelled.value:
        return True
    payload = fresh.payload or {}
    doc_id = fresh.document_id
    if doc_id is None and payload.get("document_id"):
        try:
            doc_id = uuid.UUID(str(payload["document_id"]))
        except (TypeError, ValueError):
            doc_id = None
    version_id: uuid.UUID | None = None
    if payload.get("version_id"):
        try:
            version_id = uuid.UUID(str(payload["version_id"]))
        except (TypeError, ValueError):
            version_id = None
    if not _index_target_exists(db, doc_id, version_id):
        return True
    return False


_ACTIVE_INDEX_JOB_STATUSES = (JobStatus.pending.value, JobStatus.running.value)


def _clear_parse_watch_payload(payload: dict) -> dict:
    out = dict(payload)
    out.pop("awaiting_parse", None)
    out.pop("parse_watch_started_at", None)
    return out


def _try_claim_index_job_terminal(
    db: Session,
    job: Job,
    *,
    status: str,
    progress: int | None = None,
    error_message: str | None = None,
    clear_parse_watch: bool = True,
) -> Job | None:
    """将索引任务从 pending/running 迁入终态；仅一个并发执行者能成功（用于避免重复通知）。"""
    locked = db.scalar(select(Job).where(Job.id == job.id).with_for_update())
    if not locked or locked.status not in _ACTIVE_INDEX_JOB_STATUSES:
        return None
    if _index_job_should_abort(db, locked):
        return None

    payload = dict(locked.payload or {})
    if clear_parse_watch:
        payload = _clear_parse_watch_payload(payload)
    locked.payload = payload
    locked.status = status
    locked.finished_at = datetime.now(timezone.utc)
    if status == JobStatus.done.value:
        locked.progress = 100
    elif progress is not None:
        locked.progress = progress
    if error_message is not None:
        locked.error_message = error_message
    db.add(locked)
    db.flush()
    job.status = locked.status
    job.payload = locked.payload
    job.progress = locked.progress
    job.error_message = locked.error_message
    return locked


def _index_job_still_awaiting_parse(job: Job) -> bool:
    return bool((job.payload or {}).get("awaiting_parse"))


@dataclass(frozen=True)
class KnowledgeIndexResumeResult:
    ragflow_document_id: str
    dataset_id: str
    already_completed: bool


def try_resume_incomplete_knowledge_index(
    db: Session,
    user: User,
    document: Document,
    *,
    version_id: uuid.UUID | None,
) -> KnowledgeIndexResumeResult | None:
    """版本已同步 KnowFlow 但索引未完成时，跳过重复上传并继续或重试解析。"""
    from app.models.document import DocumentVersion
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import (
        bind_document_to_indexed_version,
        get_version_link_by_version_id,
        mark_version_index_completed,
    )

    version = (
        db.get(DocumentVersion, version_id)
        if version_id
        else resolve_current_version(db, document)
    )
    if not version:
        return None

    vl = get_version_link_by_version_id(db, version.id)
    rid = (vl.ragflow_document_id if vl else "") or ""
    ds = (vl.dataset_id if vl else "") or ""
    if not rid or not ds:
        return None

    if vl and vl.index_completed_at is not None:
        return KnowledgeIndexResumeResult(rid, ds, already_completed=True)

    status, _chunks, _progress, _detail = _parse_run_status(
        db,
        user,
        dataset_id=ds,
        ragflow_document_id=rid,
        document=document,
        background=True,
    )
    run_done = status in ("已完成", "已索引") or (
        status and str(status).lower() in _PARSE_DONE
    )
    if run_done:
        marked = mark_version_index_completed(db, version.id)
        if marked:
            bind_document_to_indexed_version(
                db, document=document, version=version, version_link=marked
            )
        db.flush()
        return KnowledgeIndexResumeResult(rid, ds, already_completed=True)

    if status == "解析中" or (status and str(status).upper() in _PARSE_RUNNING):
        return KnowledgeIndexResumeResult(rid, ds, already_completed=False)

    if _is_parse_failed(status):
        logger.info(
            "KnowFlow 已有失败解析记录，不自动重试 doc=%s version=%s ragflow=%s status=%s",
            document.id,
            version.id,
            rid,
            status or "unknown",
        )
    return KnowledgeIndexResumeResult(rid, ds, already_completed=False)


def _background_actor(db: Session, document: Document, fallback: User) -> User:
    if document.owner_id:
        owner = db.get(User, document.owner_id)
        if owner and owner.status == "active":
            return owner
    return fallback


def _retrigger_ragflow_parse(
    db: Session,
    actor: User,
    document: Document,
    version_id: uuid.UUID | None,
    *,
    parser_id: str | None = None,
    layout_recognize: str | None = None,
    file_content: bytes | None = None,
    force_parse: bool = False,
) -> bool:
    """已上传文档仅重新提交解析，不重复上传文件。"""
    from app.models.document import DocumentVersion
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_sync_service import (
        _configure_and_parse_uploaded_document,
        _sync_context_for_document,
    )
    from app.services.ragflow_version_link_service import get_version_link_by_version_id
    from app.storage.object_store import get_object_store

    version = (
        db.get(DocumentVersion, version_id)
        if version_id
        else resolve_current_version(db, document)
    )
    if not version:
        return False
    vl = get_version_link_by_version_id(db, version.id)
    if not vl or not vl.ragflow_document_id or not vl.dataset_id:
        return False
    from app.services.knowflow_parse_guard import should_submit_parse

    ok, reason = should_submit_parse(
        db, vl.ragflow_document_id, force=force_parse
    )
    if not ok:
        logger.info(
            "KnowFlow 跳过重复解析 doc=%s version=%s reason=%s",
            document.id,
            version.id,
            reason,
        )
        return False
    from app.services.ragflow_version_link_service import clear_version_index_completed

    clear_version_index_completed(db, version.id)
    from app.core.platform_cache import invalidate_ragflow_doc_meta_cache

    invalidate_ragflow_doc_meta_cache(vl.dataset_id)
    _, kf = _sync_context_for_document(db, actor, document)
    upload_name = vl.file_name or version.file_name or "document"
    content = file_content
    if content is None and version.file_key:
        try:
            content = get_object_store().get_object_bytes(version.file_key)
        except Exception:
            content = None
    _configure_and_parse_uploaded_document(
        kf,
        dataset_id=vl.dataset_id,
        ragflow_document_id=vl.ragflow_document_id,
        file_name=upload_name,
        mime_type=version.mime_type or "",
        file_content=content,
        parser_id=parser_id,
        layout_recognize=layout_recognize,
        db=db,
        force_parse=force_parse,
    )
    return True


def _maybe_fallback_plain_text_parse(
    db: Session,
    job: Job,
    actor: User,
    document: Document,
    version_id: uuid.UUID | None,
    *,
    detail: str | None,
) -> bool:
    """PaddleOCR 等版面识别失败时，先尝试 DeepDOC，最后才 Plain Text（Plain Text 无引用截图）。"""
    from app.services.knowledge_parser_service import resolve_job_parser_id

    if _index_job_should_abort(db, job):
        return False
    payload = dict(job.payload or {})
    if payload.get("parse_plain_text_fallback"):
        return False
    if not _is_ocr_layout_failure(detail):
        return False

    settings = get_settings()
    layout = (payload.get("layout_recognize") or settings.knowledge_default_layout_recognize or "").strip()
    modern_ocr = frozenset({"PaddleOCR", "MinerU", "DOTS"})

    if layout in modern_ocr and not payload.get("parse_deepdoc_fallback"):
        if _retrigger_ragflow_parse(
            db,
            actor,
            document,
            version_id,
            parser_id=resolve_job_parser_id(payload),
            layout_recognize="DeepDOC",
        ):
            payload["parse_deepdoc_fallback"] = True
            payload["layout_recognize"] = "DeepDOC"
            payload["parse_retry_count"] = int(payload.get("parse_retry_count") or 0)
            payload["last_parse_retry_at"] = time.time()
            job.payload = payload
            update_job_status(
                db,
                job.id,
                JobStatus.running.value,
                progress=max(68, min(job.progress or 0, 84)),
                error_message=None,
            )
            logger.info(
                "知识库解析 %s 失败，已切换 DeepDOC 重试 doc=%s job=%s",
                layout,
                document.id,
                job.id,
            )
            return True

    if _retrigger_ragflow_parse(
        db,
        actor,
        document,
        version_id,
        parser_id="naive",
        layout_recognize="Plain Text",
    ):
        payload["parse_plain_text_fallback"] = True
        payload["parse_retry_count"] = int(payload.get("parse_retry_count") or 0)
        payload["last_parse_retry_at"] = time.time()
        job.payload = payload
        update_job_status(
            db,
            job.id,
            JobStatus.running.value,
            progress=max(68, min(job.progress or 0, 84)),
            error_message=None,
        )
        logger.info(
            "知识库解析 OCR 失败，已切换 Plain Text 重试（无页级引用截图）doc=%s job=%s",
            document.id,
            job.id,
        )
        return True
    return False


def _parse_run_status_from_item(item: dict) -> tuple[str | None, int | None, int | None, str | None]:
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
    from app.services.knowledge_library_service import summarize_ragflow_progress_msg

    detail = summarize_ragflow_progress_msg(msg) if msg else None
    return label, chunks, progress_pct, detail


def _parse_run_status(
    db: Session,
    user: User,
    *,
    dataset_id: str,
    ragflow_document_id: str,
    document: Document | None = None,
    background: bool = False,
) -> tuple[str | None, int | None, int | None, str | None]:
    from app.services.knowledge_library_service import (
        _fetch_document_run_map_from_mysql,
        fetch_ragflow_doc_meta_map,
    )

    rid = str(ragflow_document_id)
    if background and document is not None:
        mysql_map = _fetch_document_run_map_from_mysql(db, [rid])
        mysql_item = mysql_map.get(rid)
        if mysql_item:
            return _parse_run_status_from_item(mysql_item)

    meta_by_id, fetch_ok = fetch_ragflow_doc_meta_map(
        db,
        user,
        dataset_id,
        [rid],
        document=document,
        background=background or document is not None,
    )
    if not fetch_ok:
        return None, None, None, None
    item = meta_by_id.get(rid)
    if not item:
        return None, None, None, None
    return _parse_run_status_from_item(item)


def _is_ragflow_queue_backlog(detail: str | None) -> bool:
    text = (detail or "").lower()
    return "tasks are ahead in the queue" in text or "排队" in text


def _subscription_has_html_fallback(payload: dict | None) -> bool:
    data = payload or {}
    html = str(data.get("article_html_body") or "").strip()
    summary = str(data.get("article_summary") or "").strip()
    return bool(html) or bool(summary)


def _should_skip_deepdoc_for_subscription(
    payload: dict | None,
    *,
    status: str | None,
    rag_progress: int | None,
    detail: str | None,
) -> bool:
    """资讯导入已有 HTML 正文时，KnowFlow 排队过久则直接用原文走 PageIndex。"""
    if not _subscription_has_html_fallback(payload):
        return False
    if _is_parse_done(status):
        return False
    if rag_progress is not None and rag_progress > 0:
        return False
    return _is_ragflow_queue_backlog(detail)


def _advance_parse_job_progress(
    progress: int,
    *,
    status: str | None,
    rag_progress: int | None,
    stagnant_polls: int,
) -> tuple[int, int]:
    """在等待 KnowFlow 解析时推进任务进度，避免长时间停在 68%。"""
    prev = progress
    if rag_progress is not None and rag_progress >= 0:
        mapped = 68 + round(rag_progress * 26 / 100)
        progress = max(progress, min(94, mapped))
    elif _is_parse_running(status):
        progress = min(94, progress + 1)
    elif status in (None, "未解析"):
        progress = min(84, progress + 1)

    if progress <= prev and (
        _is_parse_running(status) or status in (None, "未解析")
    ):
        stagnant_polls += 1
        if stagnant_polls >= 2:
            progress = min(93, progress + 1)
            stagnant_polls = 0
    else:
        stagnant_polls = 0
    return progress, stagnant_polls


def _maybe_bootstrap_ragflow_parse(
    db: Session,
    job: Job,
    actor: User,
    document: Document,
    version_id: uuid.UUID | None,
    *,
    status: str | None,
    unparsed_polls: int,
) -> int:
    """解析长时间未启动（未解析/拉取失败）时重新提交 KnowFlow 解析。"""
    if _is_parse_done(status) or _is_parse_failed(status) or _is_parse_running(status):
        return 0
    if status not in (None, "未解析"):
        return 0
    if unparsed_polls < 4:
        return unparsed_polls + 1
    payload = dict(job.payload or {})
    if payload.get("parse_bootstrapped"):
        return 0
    if not _retrigger_ragflow_parse(db, actor, document, version_id):
        payload["parse_bootstrapped"] = True
        job.payload = payload
        return 0
    payload["parse_bootstrapped"] = True
    job.payload = payload
    db.commit()
    logger.info(
        "KnowFlow 解析未启动，已重新提交 doc=%s job=%s status=%s",
        document.id,
        job.id,
        status or "unknown",
    )
    return 0


def _format_parse_failure(status: str | None, detail: str | None) -> str:
    base = status or "解析失败"
    if detail and detail not in base:
        return f"{base}：{detail}"
    return base


def _is_parse_done(status: str | None) -> bool:
    return status in ("已完成", "已索引") or (
        status and str(status).lower() in _PARSE_DONE
    )


def _is_parse_failed(status: str | None) -> bool:
    return status in ("解析失败", "已取消") or (
        status and str(status).upper() in _PARSE_FAILED
    )


def _is_parse_running(status: str | None) -> bool:
    return status == "解析中" or (
        status and str(status).upper() in _PARSE_RUNNING
    )


def _is_ocr_layout_failure(detail: str | None) -> bool:
    text = (detail or "").lower()
    if not text:
        return False
    markers = (
        "paddleocr",
        "failed to recognize pdf",
        "ocr api error",
        "layout recognize",
        "layout_recognize",
        "ocr failed",
        "recognize pdf",
    )
    return any(m in text for m in markers)


def _is_retriable_parse_failure(detail: str | None) -> bool:
    text = (detail or "").lower()
    if not text:
        return True
    non_retriable = (
        "model disabled",
        "invalid api",
        "unauthorized",
        "未配置",
        "api key",
        "permission denied",
    )
    if any(m in text for m in non_retriable):
        return False
    if "403" in text and ("disabled" in text or "forbidden" in text):
        return False
    retriable = (
        "timeout",
        "timed out",
        "time out",
        "busy",
        "429",
        "503",
        "502",
        "504",
        "connection",
        "temporarily",
        "network",
        "unavailable",
        "ocr timeout",
        "rate limit",
        "overloaded",
        "服务繁忙",
        "超时",
        "繁忙",
    )
    return any(m in text for m in retriable)


def _record_parse_progress(job: Job, *, progress_pct: int | None, detail: str | None) -> None:
    payload = dict(job.payload or {})
    if progress_pct is not None and progress_pct >= 0:
        payload["last_parse_progress"] = progress_pct
    if detail:
        payload["last_parse_detail"] = str(detail)[:500]
    job.payload = payload


def _maybe_retry_parse_failure(
    db: Session,
    job: Job,
    actor: User,
    document: Document,
    version_id: uuid.UUID | None,
    *,
    detail: str | None,
) -> bool:
    from app.config import get_settings

    if _index_job_should_abort(db, job):
        return False

    settings = get_settings()
    payload = dict(job.payload or {})
    retries = int(payload.get("parse_retry_count") or 0)
    max_retries = max(1, int(settings.knowledge_parse_max_retries))
    if retries >= max_retries or not _is_retriable_parse_failure(detail):
        return False
    if not _retrigger_ragflow_parse(db, actor, document, version_id):
        return False
    payload["parse_retry_count"] = retries + 1
    payload["last_parse_retry_at"] = time.time()
    job.payload = payload
    db.commit()
    delay = max(15, int(settings.knowledge_parse_retry_delay_sec))
    logger.info(
        "知识库解析自动重试 doc=%s job=%s attempt=%s detail=%s",
        document.id,
        job.id,
        payload["parse_retry_count"],
        (detail or "")[:120],
    )
    time.sleep(delay)
    return True


def _wait_for_parse(
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    dataset_id: str,
    ragflow_document_id: str,
    version_id: uuid.UUID | None = None,
    max_wait_sec: int | None = None,
    update_progress: bool = True,
) -> bool:
    """等待 RAGFlow 解析完成。每轮轮询使用独立 DB 会话，sleep 期间不占用连接。"""
    from app.config import get_settings
    from app.database import SessionLocal

    settings = get_settings()
    interval = max(2, int(settings.knowledge_parse_poll_interval_sec))
    soft_extend = max(60, int(settings.knowledge_parse_soft_extend_sec))
    if max_wait_sec is None:
        max_wait_sec = int(settings.knowledge_parse_initial_wait_sec)
    absolute_deadline = time.time() + max(1, int(max_wait_sec))
    soft_deadline = min(
        absolute_deadline,
        time.time() + min(soft_extend, int(max_wait_sec)),
    )
    progress = 68
    last_status: str | None = None
    stagnant_polls = 0
    queue_backlog_polls = 0

    while time.time() < absolute_deadline:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            user = db.get(User, user_id)
            document = get_document(db, document_id)
            if not job or not user or not document:
                return False
            if _index_job_should_abort(db, job):
                return False

            now = time.time()
            if now > soft_deadline:
                if _is_parse_running(last_status) or last_status is None:
                    soft_deadline = min(now + soft_extend, absolute_deadline)
                    if update_progress:
                        update_job_status(
                            db,
                            job.id,
                            JobStatus.running.value,
                            progress=min(progress, 84),
                        )
                else:
                    soft_deadline = min(now + 60, absolute_deadline)

            actor = _background_actor(db, document, user)
            status, _chunks, rag_progress, detail = _parse_run_status(
                db,
                actor,
                dataset_id=dataset_id,
                ragflow_document_id=ragflow_document_id,
                document=document,
                background=True,
            )
            last_status = status
            _record_parse_progress(job, progress_pct=rag_progress, detail=detail)
            if (
                _is_ragflow_queue_backlog(detail)
                and (rag_progress is None or rag_progress <= 0)
            ):
                queue_backlog_polls += 1
                if queue_backlog_polls >= 3:
                    db.commit()
                    return False
            else:
                queue_backlog_polls = 0
            if _is_parse_done(status):
                if _index_job_should_abort(db, job):
                    db.commit()
                    return False
                if update_progress:
                    update_job_status(db, job.id, JobStatus.running.value, progress=95)
                db.commit()
                return True
            if _is_parse_failed(status):
                db.commit()
                raise RuntimeError(_format_parse_failure(status, detail))
            if status == "索引失效":
                db.commit()
                raise RuntimeError("文档解析失败：索引失效")
            progress, stagnant_polls = _advance_parse_job_progress(
                progress,
                status=status,
                rag_progress=rag_progress,
                stagnant_polls=stagnant_polls,
            )
            if update_progress:
                update_job_status(db, job.id, JobStatus.running.value, progress=progress)
            db.commit()
        finally:
            db.close()

        time.sleep(interval)

    if _is_parse_done(last_status):
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job and _index_job_should_abort(db, job):
                return False
        finally:
            db.close()
        return True
    if _is_parse_failed(last_status):
        raise RuntimeError(_format_parse_failure(last_status, None))
    if _is_parse_running(last_status) or last_status is None:
        return False
    return False


def _fail_parse_job(
    db: Session,
    job: Job,
    user: User,
    doc: Document,
    error_text: str,
    *,
    mode: str,
) -> None:
    if _index_job_should_abort(db, job):
        return
    claimed = _try_claim_index_job_terminal(
        db,
        job,
        status=JobStatus.failed.value,
        error_message=error_text[:500],
    )
    if not claimed:
        return
    fail_title = "文档重新索引失败" if mode == "reindex" else "文档索引未完成"
    if mode == "reindex":
        fail_body = (
            f"「{doc.title or '未命名文档'}」重新索引未完成：{error_text}"
        )
    else:
        fail_body = (
            f"「{doc.title or '未命名文档'}」知识库解析失败：{error_text}。"
            "可在文档详情 → 知识索引中重试。"
        )
    create_notification(
        db,
        user_id=user.id,
        title=fail_title,
        body=fail_body,
        link=f"/documents/{doc.id}",
    )
    dataset_id = str((job.payload or {}).get("dataset_id") or "").strip() or None
    try:
        from app.services.knowledge_scope_tree_service import (
            notify_knowledge_index_state_changed,
        )

        notify_knowledge_index_state_changed(
            user_id=user.id,
            dataset_id=dataset_id,
        )
    except Exception as exc:
        logger.debug("解析失败后刷新索引缓存跳过 job=%s: %s", job.id, exc)


SUBSCRIPTION_PIPELINE_MODE = "subscription_pipeline"


def _is_subscription_pipeline_mode(mode: str | None) -> bool:
    return str(mode or "").strip() == SUBSCRIPTION_PIPELINE_MODE


def _finish_index_job_after_parse(
    db: Session,
    job: Job,
    user: User,
    doc: Document,
    *,
    dataset_id: str | None,
    version_id_raw: str | None,
    mode: str,
) -> None:
    """DeepDOC 解析完成后：资讯导入走 PageIndex + 后台 KG；其它走 KnowFlow 索引完成。"""
    if _is_subscription_pipeline_mode(mode):
        _complete_subscription_pipeline_after_deepdoc(
            db,
            job,
            user,
            doc,
            version_id_raw=version_id_raw,
        )
        return
    _complete_knowledge_index_job(
        db,
        job,
        user,
        doc,
        dataset_id=dataset_id,
        version_id_raw=version_id_raw,
        mode=mode,
    )


def _complete_subscription_pipeline_after_deepdoc(
    db: Session,
    job: Job,
    user: User,
    doc: Document,
    *,
    version_id_raw: str | None,
) -> None:
    """资讯导入：DeepDOC 解析完成后建立 PageIndex，并后台触发知识图谱抽取。"""
    from app.services.knowledge_parser_service import PARSER_PAGEINDEX, index_stack_block_reason
    from app.services.pageindex_service import (
        execute_pageindex_reindex,
        resolve_pageindex_markdown_for_subscription,
    )

    if _index_job_should_abort(db, job):
        return

    version_id = uuid.UUID(str(version_id_raw)) if version_id_raw else None
    pi_reason = index_stack_block_reason(PARSER_PAGEINDEX, reindex=True)
    if pi_reason:
        claimed = _try_claim_index_job_terminal(
            db,
            job,
            status=JobStatus.failed.value,
            error_message=pi_reason,
        )
        if claimed:
            create_notification(
                db,
                user_id=user.id,
                title="文档索引失败",
                body=f"「{doc.title or '未命名文档'}」DeepDOC 解析已完成，但 PageIndex 不可用：{pi_reason}",
                link=f"/documents/{doc.id}",
            )
        return

    payload = _clear_parse_watch_payload(dict(job.payload or {}))
    job.payload = payload
    update_job_status(db, job.id, JobStatus.running.value, progress=82)

    markdown_text = resolve_pageindex_markdown_for_subscription(
        db,
        user,
        doc,
        version_id=version_id,
        job_payload=payload,
    )
    update_job_status(db, job.id, JobStatus.running.value, progress=88)

    try:
        execute_pageindex_reindex(
            db,
            user,
            doc.id,
            version_id=version_id,
            markdown_text=markdown_text,
        )
    except Exception as exc:
        from app.core.user_messages import background_job_error_message

        err_text = background_job_error_message(exc, fallback="PageIndex 索引失败")
        claimed = _try_claim_index_job_terminal(
            db,
            job,
            status=JobStatus.failed.value,
            error_message=err_text[:500],
        )
        if claimed:
            create_notification(
                db,
                user_id=user.id,
                title="文档索引失败",
                body=f"「{doc.title or '未命名文档'}」PageIndex 索引未完成：{err_text}",
                link=f"/documents/{doc.id}",
            )
        try:
            from app.services.knowledge_scope_tree_service import (
                notify_knowledge_index_state_changed,
            )

            notify_knowledge_index_state_changed(user_id=user.id)
        except Exception as notify_exc:
            logger.debug(
                "资讯导入 PageIndex 失败后刷新缓存跳过 job=%s: %s",
                job.id,
                notify_exc,
            )
        return

    claimed = _try_claim_index_job_terminal(db, job, status=JobStatus.done.value)
    if not claimed:
        return
    create_notification(
        db,
        user_id=user.id,
        title="文档索引完成",
        body=(
            f"「{doc.title or '未命名文档'}」已完成 DeepDOC 解析与 PageIndex 索引，"
            "可用于知识检索。"
        ),
        link=f"/documents/{doc.id}",
    )
    try:
        from app.services.knowledge_scope_tree_service import (
            notify_knowledge_index_state_changed,
        )

        notify_knowledge_index_state_changed(user_id=user.id)
    except Exception as exc:
        logger.debug("资讯导入索引完成后刷新缓存跳过 job=%s: %s", job.id, exc)


def _complete_knowledge_index_job(
    db: Session,
    job: Job,
    user: User,
    doc: Document,
    *,
    dataset_id: str | None,
    version_id_raw: str | None,
    mode: str,
    notify_title: str | None = None,
    notify_body: str | None = None,
    notify_link: str | None = None,
) -> None:
    from app.models.document import DocumentVersion
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import (
        bind_document_to_indexed_version,
        mark_version_index_completed,
    )

    if _index_job_should_abort(db, job):
        return

    version_id = uuid.UUID(str(version_id_raw)) if version_id_raw else None
    current = resolve_current_version(db, doc)
    indexed_version_id = version_id or (current.id if current else None)
    if indexed_version_id:
        vl = mark_version_index_completed(db, indexed_version_id)
        ver = db.get(DocumentVersion, indexed_version_id)
        if vl and ver:
            bind_document_to_indexed_version(
                db, document=doc, version=ver, version_link=vl
            )

    claimed = _try_claim_index_job_terminal(db, job, status=JobStatus.done.value)
    if not claimed:
        return

    done_title = notify_title or (
        "文档重新索引完成" if mode == "reindex" else "文档索引完成"
    )
    done_body = notify_body or (
        f"「{doc.title or '未命名文档'}」已应用新解析配置并完成索引，可用于问答检索。"
        if mode == "reindex"
        else f"「{doc.title or '未命名文档'}」已同步到知识库并完成解析，可用于问答检索。"
    )
    create_notification(
        db,
        user_id=user.id,
        title=done_title,
        body=done_body,
        link=notify_link or f"/documents/{doc.id}",
    )
    try:
        from app.services.knowledge_scope_tree_service import (
            notify_knowledge_index_state_changed,
        )

        notify_knowledge_index_state_changed(
            user_id=user.id,
            dataset_id=str(dataset_id) if dataset_id else None,
        )
    except Exception as exc:
        logger.debug("知识检索树缓存刷新跳过 job=%s: %s", job.id, exc)


def _schedule_parse_watch(job_id: uuid.UUID) -> None:
    with _parse_watch_lock:
        if job_id in _active_parse_watches:
            return
        _active_parse_watches.add(job_id)
    from app.services.background_job_dispatch import dispatch_parse_watch

    dispatch_parse_watch(job_id)


def _run_parse_watch(job_id: uuid.UUID) -> None:
    from app.config import get_settings
    from app.database import SessionLocal

    watch_ctx: dict | None = None
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        if _index_job_should_abort(db, job):
            return
        payload = dict(job.payload or {})
        if not payload.get("awaiting_parse"):
            return
        user = db.get(User, job.created_by)
        doc = get_document(db, job.document_id) if job.document_id else None
        if not user or not doc:
            return

        dataset_id = str(payload.get("dataset_id") or "")
        rid = str(payload.get("ragflow_document_id") or "")
        if not dataset_id or not rid:
            return

        settings = get_settings()
        max_total = int(settings.knowledge_parse_max_wait_sec)
        started_raw = payload.get("parse_watch_started_at")
        started_at = time.time()
        if started_raw is not None:
            try:
                started_at = float(started_raw)
            except (TypeError, ValueError):
                started_at = time.time()
        remaining = max(60, int(max_total - (time.time() - started_at)))
        mode = str(payload.get("mode") or "index")
        version_id_raw = payload.get("version_id")
        version_uuid = uuid.UUID(str(version_id_raw)) if version_id_raw else None

        watch_ctx = {
            "user_id": user.id,
            "document_id": doc.id,
            "dataset_id": dataset_id,
            "rid": rid,
            "remaining": remaining,
            "mode": mode,
            "version_id_raw": version_id_raw,
            "version_uuid": version_uuid,
            "started_at": started_at,
            "max_total": max_total,
        }
    finally:
        db.close()

    if not watch_ctx:
        return

    completed = False
    parse_exc: RuntimeError | None = None
    try:
        # _wait_for_parse 每轮轮询独立会话；此处须先释放外层连接，避免占满连接池
        completed = _wait_for_parse(
            job_id=job_id,
            user_id=watch_ctx["user_id"],
            document_id=watch_ctx["document_id"],
            dataset_id=watch_ctx["dataset_id"],
            ragflow_document_id=watch_ctx["rid"],
            version_id=watch_ctx["version_uuid"],
            max_wait_sec=watch_ctx["remaining"],
            update_progress=False,
        )
    except RuntimeError as exc:
        parse_exc = exc

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        user = db.get(User, watch_ctx["user_id"])
        doc = get_document(db, watch_ctx["document_id"])
        if not user or not doc:
            return

        if parse_exc is not None:
            _fail_parse_job(db, job, user, doc, str(parse_exc), mode=watch_ctx["mode"])
            db.commit()
            return

        if completed:
            db.refresh(job)
            if not _index_job_still_awaiting_parse(job):
                return
            if not _index_job_should_abort(db, job):
                _finish_index_job_after_parse(
                    db,
                    job,
                    user,
                    doc,
                    dataset_id=watch_ctx["dataset_id"],
                    version_id_raw=watch_ctx["version_id_raw"],
                    mode=watch_ctx["mode"],
                )
                db.commit()
            return

        if _index_job_should_abort(db, job):
            return

        elapsed = time.time() - watch_ctx["started_at"]
        if elapsed < watch_ctx["max_total"] - 60:
            payload = dict(job.payload or {})
            payload["parse_watch_started_at"] = watch_ctx["started_at"]
            payload["awaiting_parse"] = True
            job.payload = payload
            update_job_status(db, job.id, JobStatus.running.value, progress=90)
            db.commit()
            settings = get_settings()
            delay = max(60, int(settings.knowledge_parse_poll_interval_sec) * 6)
            from app.services.background_job_dispatch import dispatch_parse_watch

            dispatch_parse_watch(job_id, countdown=delay)
            return

        db.commit()
    except Exception:
        logger.exception("知识库解析后台续跑失败 job=%s", job_id)
    finally:
        with _parse_watch_lock:
            _active_parse_watches.discard(job_id)
        db.close()


def _defer_parse_watch(
    db: Session,
    job: Job,
    user: User,
    doc: Document,
    *,
    dataset_id: str,
    ragflow_document_id: str,
    mode: str,
    version_id_raw: str | None,
) -> None:
    if _index_job_should_abort(db, job):
        return
    payload = dict(job.payload or {})
    payload["awaiting_parse"] = True
    payload["dataset_id"] = dataset_id
    payload["ragflow_document_id"] = ragflow_document_id
    payload["mode"] = mode
    if version_id_raw:
        payload["version_id"] = version_id_raw
    if not payload.get("parse_watch_started_at"):
        payload["parse_watch_started_at"] = time.time()
    job.payload = payload
    update_job_status(db, job.id, JobStatus.running.value, progress=90, error_message=None)
    _schedule_parse_watch(job.id)


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
        version_id_raw = payload.get("version_id")
        version_id = uuid.UUID(str(version_id_raw)) if version_id_raw else None
        doc = get_document(db, job.document_id) if job.document_id else None
        if (
            not user
            or not doc
            or not _index_target_exists(db, job.document_id, version_id)
        ):
            update_job_status(
                db,
                job_id,
                JobStatus.cancelled.value,
                progress=0,
                error_message="文档或版本已删除",
            )
            db.commit()
            return
        force = bool(payload.get("force", True))
        mode = str(payload.get("mode") or "index")
        from app.services.knowledge_parser_service import (
            index_stack_block_reason,
            is_pageindex_reindex,
            resolve_job_parser_id,
        )

        resolved_parser = resolve_job_parser_id(payload)
        pageindex_mode = is_pageindex_reindex(mode=mode, parser_id=resolved_parser)

        update_job_status(db, job_id, JobStatus.running.value, progress=8)

        if _is_subscription_pipeline_mode(mode):
            from app.services.knowledge_parser_service import PARSER_PAGEINDEX

            stack_reason = index_stack_block_reason(
                payload.get("parser_id"),
                reindex=False,
            ) or index_stack_block_reason(PARSER_PAGEINDEX, reindex=True)
        else:
            stack_reason = index_stack_block_reason(
                payload.get("parser_id"),
                reindex=(mode == "reindex"),
            )
        if stack_reason:
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=stack_reason,
            )
            return

        if not pageindex_mode:
            update_job_status(db, job_id, JobStatus.running.value, progress=18)
            try:
                knowledge.user_auth(db, user)
                knowledge.reconcile_catalog(db, user, sync_documents=False)
            except Exception as e:
                logger.warning("知识库任务目录对齐跳过 job=%s: %s", job_id, e)
        else:
            update_job_status(db, job_id, JobStatus.running.value, progress=18)

        if mode == "reindex":
            from app.services.knowledge_library_service import execute_document_reindex

            update_job_status(db, job_id, JobStatus.running.value, progress=32)
            try:
                result = execute_document_reindex(
                    db,
                    user,
                    doc.id,
                    version_id=version_id,
                    parser_id=resolved_parser,
                    layout_recognize=payload.get("layout_recognize"),
                    resync=bool(payload.get("resync")),
                )
                db.commit()
            except Exception as e:
                from app.core.user_messages import background_job_error_message

                err_text = background_job_error_message(e, fallback="重新索引失败")
                _fail_parse_job(db, job, user, doc, err_text, mode=mode)
                try:
                    from app.services.knowledge_scope_tree_service import (
                        notify_knowledge_index_state_changed,
                    )

                    notify_knowledge_index_state_changed(user_id=user.id)
                except Exception as exc:
                    logger.debug(
                        "重新索引失败后刷新索引缓存跳过 job=%s: %s", job_id, exc
                    )
                db.commit()
                return

            if result.get("index_engine") == "pageindex":
                _complete_knowledge_index_job(
                    db,
                    job,
                    user,
                    doc,
                    dataset_id=None,
                    version_id_raw=version_id_raw,
                    mode=mode,
                    notify_title="文档索引完成",
                    notify_body=(
                        f"「{doc.title or '未命名文档'}」已完成索引，"
                        "可在「知识检索」中使用。"
                    ),
                    notify_link="/knowledge/search",
                )
                db.commit()
                return

            dataset_id = result.get("dataset_id")
            rid = result.get("ragflow_document_id")
        else:
            update_job_status(db, job_id, JobStatus.running.value, progress=32)
            resume = try_resume_incomplete_knowledge_index(
                db, user, doc, version_id=version_id
            )
            if resume:
                rid = resume.ragflow_document_id
                dataset_id = resume.dataset_id
                db.commit()
                if resume.already_completed:
                    if _is_subscription_pipeline_mode(mode):
                        _finish_index_job_after_parse(
                            db,
                            db.get(Job, job_id) or job,
                            user,
                            doc,
                            dataset_id=dataset_id,
                            version_id_raw=version_id_raw,
                            mode=mode,
                        )
                        db.commit()
                        return

                    _complete_knowledge_index_job(
                        db,
                        db.get(Job, job_id) or job,
                        user,
                        doc,
                        dataset_id=dataset_id,
                        version_id_raw=version_id_raw,
                        mode=mode,
                    )
                    db.commit()
                    return

                if _is_subscription_pipeline_mode(mode):
                    actor = _background_actor(db, doc, user)
                    parse_status, _chunks, rag_progress, detail = _parse_run_status(
                        db,
                        actor,
                        dataset_id=str(dataset_id),
                        ragflow_document_id=str(rid),
                        document=doc,
                        background=True,
                    )
                    if _should_skip_deepdoc_for_subscription(
                        payload,
                        status=parse_status,
                        rag_progress=rag_progress,
                        detail=detail,
                    ):
                        logger.info(
                            "资讯导入续跑：KnowFlow 排队，跳过 DeepDOC doc=%s job=%s detail=%s",
                            doc.id,
                            job_id,
                            (detail or parse_status or "")[:120],
                        )
                        update_job_status(
                            db, job_id, JobStatus.running.value, progress=82
                        )
                        _finish_index_job_after_parse(
                            db,
                            db.get(Job, job_id) or job,
                            user,
                            doc,
                            dataset_id=str(dataset_id),
                            version_id_raw=version_id_raw,
                            mode=mode,
                        )
                        db.commit()
                        return
            else:
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
            user_id = user.id
            doc_id = doc.id
            ds = str(dataset_id)
            rflow_id = str(rid)
            skip_deepdoc = False
            if _is_subscription_pipeline_mode(mode):
                actor = _background_actor(db, doc, user)
                parse_status, _chunks, rag_progress, detail = _parse_run_status(
                    db,
                    actor,
                    dataset_id=ds,
                    ragflow_document_id=rflow_id,
                    document=doc,
                    background=True,
                )
                skip_deepdoc = _should_skip_deepdoc_for_subscription(
                    payload,
                    status=parse_status,
                    rag_progress=rag_progress,
                    detail=detail,
                )
                if skip_deepdoc:
                    logger.info(
                        "资讯导入 KnowFlow 排队或未启动，跳过 DeepDOC 等待 doc=%s job=%s detail=%s",
                        doc.id,
                        job_id,
                        (detail or parse_status or "")[:120],
                    )
            db.commit()
            db.close()
            db = None

            if skip_deepdoc:
                db = SessionLocal()
                try:
                    job = db.get(Job, job_id)
                    user = db.get(User, user_id) if user_id else None
                    doc = get_document(db, doc_id) if doc_id else None
                    if job and user and doc and not _index_job_should_abort(db, job):
                        update_job_status(
                            db, job_id, JobStatus.running.value, progress=82
                        )
                        db.commit()
                        _finish_index_job_after_parse(
                            db,
                            job,
                            user,
                            doc,
                            dataset_id=ds,
                            version_id_raw=version_id_raw,
                            mode=mode,
                        )
                        db.commit()
                finally:
                    db.close()
                return

            parse_done = False
            try:
                parse_done = _wait_for_parse(
                    job_id=job_id,
                    user_id=user_id,
                    document_id=doc_id,
                    dataset_id=ds,
                    ragflow_document_id=rflow_id,
                    version_id=version_id,
                )
            except RuntimeError as e:
                db = SessionLocal()
                job = db.get(Job, job_id)
                user = db.get(User, user_id) if user_id else None
                doc = get_document(db, doc_id) if doc_id else None
                if job and user and doc:
                    _fail_parse_job(db, job, user, doc, str(e), mode=mode)
                    db.commit()
                return

            db = SessionLocal()
            job = db.get(Job, job_id)
            user = db.get(User, user_id) if user_id else None
            doc = get_document(db, doc_id) if doc_id else None
            if not job or not user or not doc:
                return

            if not parse_done:
                if _index_job_should_abort(db, job):
                    db.commit()
                    return
                _defer_parse_watch(
                    db,
                    job,
                    user,
                    doc,
                    dataset_id=ds,
                    ragflow_document_id=rflow_id,
                    mode=mode,
                    version_id_raw=version_id_raw,
                )
                db.commit()
                return

        if not _index_job_should_abort(db, job):
            _finish_index_job_after_parse(
                db,
                job,
                user,
                doc,
                dataset_id=str(dataset_id) if dataset_id else None,
                version_id_raw=version_id_raw,
                mode=mode,
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
    from app.services.background_job_dispatch import dispatch_document_index_job

    dispatch_document_index_job(job_id)


def find_active_document_index_job(
    db: Session,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> Job | None:
    """同一文档/版本已有进行中的索引或解析续跑任务时不再新建。"""
    for job in _collect_document_index_jobs(db, document_id, version_id=version_id):
        payload = job.payload or {}
        if job.status in (JobStatus.pending.value, JobStatus.running.value):
            return job
        if payload.get("awaiting_parse"):
            return job
    return None


def _cancel_active_document_index_jobs(
    db: Session,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    reason: str = "已提交新的索引任务",
) -> int:
    """取消同一文档/版本进行中的平台索引任务，避免重复解析。"""
    cancelled = 0
    for job in _collect_document_index_jobs(db, document_id, version_id=version_id):
        payload = dict(job.payload or {})
        had_watch = bool(payload.get("awaiting_parse"))
        payload.pop("awaiting_parse", None)
        payload.pop("parse_watch_started_at", None)
        job.payload = payload
        if job.status in (JobStatus.pending.value, JobStatus.running.value):
            update_job_status(
                db,
                job.id,
                JobStatus.cancelled.value,
                error_message=reason,
            )
            cancelled += 1
        elif had_watch:
            db.add(job)
            db.flush()
            cancelled += 1
        with _parse_watch_lock:
            _active_parse_watches.discard(job.id)
    if cancelled:
        logger.info(
            "已取消文档旧索引任务 doc=%s version=%s count=%s",
            document_id,
            version_id,
            cancelled,
        )
    return cancelled


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

    existing = find_active_document_index_job(
        db, document_id, version_id=version_id
    )
    if existing:
        logger.info(
            "文档索引任务已存在，取消旧任务并重新创建 doc=%s version=%s job=%s",
            document_id,
            version_id,
            existing.id,
        )
        _cancel_active_document_index_jobs(
            db,
            document_id,
            version_id=version_id,
            reason="已提交新的索引任务",
        )

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


def create_subscription_pipeline_index_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    document_title: str | None = None,
    article_html_body: str = "",
    article_summary: str = "",
    article_link: str = "",
    article_source_label: str = "",
    article_title: str = "",
) -> Job | None:
    """资讯导入默认索引链：MinIO PDF → DeepDOC 解析 → PageIndex → 后台 KG 抽取。"""
    from app.config import get_settings
    from app.services.knowledge_parser_service import (
        index_stack_block_reason,
        normalize_layout_recognize,
        normalize_parser_id,
    )

    if not knowledge.enabled():
        return None
    # 资讯链先走 KnowFlow DeepDOC；PageIndex 在解析完成后单独检查（见
    # _complete_subscription_pipeline_after_deepdoc），勿在此拦截否则导入后不会解析。
    if index_stack_block_reason(None, reindex=False):
        return None

    existing = find_active_document_index_job(
        db, document_id, version_id=version_id
    )
    if existing:
        return existing

    settings = get_settings()
    doc = get_document(db, document_id)
    title = (document_title or (doc.title if doc else "") or "").strip()
    article_title_text = (article_title or title or "").strip()
    parser_id = normalize_parser_id(settings.knowledge_default_parser_id)
    layout = normalize_layout_recognize("DeepDOC")

    return create_job(
        db,
        job_type=JobType.document_index.value,
        created_by=user_id,
        document_id=document_id,
        payload={
            "mode": SUBSCRIPTION_PIPELINE_MODE,
            "document_id": str(document_id),
            "version_id": str(version_id) if version_id else None,
            "document_title": title or "未命名文档",
            "article_title": article_title_text,
            "article_html_body": (article_html_body or "").strip(),
            "article_summary": (article_summary or "").strip(),
            "article_link": (article_link or "").strip(),
            "article_source_label": (article_source_label or "").strip(),
            "parser_id": parser_id,
            "layout_recognize": layout,
            "force": True,
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
    from app.services.knowledge_data_reconcile_service import (
        should_force_knowledge_index_after_upload,
    )

    force = should_force_knowledge_index_after_upload(
        db, document_id=document_id, version_id=version_id
    )
    return enqueue_document_knowledge_index(
        db,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        force=force,
    )


def create_document_reindex_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    parser_id: str | None = None,
    layout_recognize: str | None = None,
    resync: bool = False,
    document_title: str | None = None,
) -> Job | None:
    from app.services.knowledge_parser_service import (
        index_stack_block_reason,
        reindex_parser_id_raw,
    )

    if index_stack_block_reason(parser_id, reindex=True):
        return None

    resolved_parser = reindex_parser_id_raw(parser_id)

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
            "parser_id": resolved_parser,
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
    parser_id: str | None = None,
    layout_recognize: str | None = None,
    resync: bool = False,
    document_title: str | None = None,
) -> Job | None:
    """创建后台任务：切换解析器并重新索引。"""
    _cancel_active_document_index_jobs(
        db,
        document_id,
        version_id=version_id,
        reason="已提交新的重新索引任务",
    )
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


def recover_interrupted_document_index_jobs() -> int:
    """服务启动时恢复中断的文档索引任务（pending / running）。"""
    from app.config import get_settings
    from app.database import SessionLocal
    from app.services.job_watchdog_service import is_job_stale

    if not get_settings().knowflow_enabled:
        return 0

    db = SessionLocal()
    recovered = 0
    try:
        jobs = db.scalars(
            select(Job).where(
                Job.type == JobType.document_index.value,
                Job.status.in_(
                    (JobStatus.pending.value, JobStatus.running.value)
                ),
            )
        ).all()
        for job in jobs:
            if is_job_stale(
                job, stale_minutes=int(get_settings().background_job_stale_minutes)
            ):
                continue
            payload = job.payload or {}
            if payload.get("awaiting_parse"):
                if _index_job_should_abort(db, job):
                    continue
                _schedule_parse_watch(job.id)
                recovered += 1
                continue
            if job.status == JobStatus.running.value:
                update_job_status(
                    db,
                    job.id,
                    JobStatus.pending.value,
                    progress=max(0, min(job.progress or 0, 67)),
                )
            if _index_job_should_abort(db, job):
                continue
            _start_job_thread(job.id)
            recovered += 1

        done_jobs = db.scalars(
            select(Job).where(
                Job.type == JobType.document_index.value,
                Job.status == JobStatus.done.value,
            )
        ).all()
        for job in done_jobs:
            if (job.payload or {}).get("awaiting_parse"):
                if _index_job_should_abort(db, job):
                    continue
                _schedule_parse_watch(job.id)
                recovered += 1

        db.commit()
        if recovered:
            logger.info("已恢复 %s 个文档索引/解析续跑任务", recovered)
    except Exception:
        logger.exception("恢复文档索引任务失败")
    finally:
        db.close()
    return recovered
