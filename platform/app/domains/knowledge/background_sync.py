"""文档入库后的 KnowFlow 后台同步（不阻塞上传 API）。"""

from __future__ import annotations

import logging
import threading
import uuid

logger = logging.getLogger(__name__)


def run_sync_after_ingest(document_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    """在新 DB 会话中同步单篇文档到 KnowFlow。"""
    from app.database import SessionLocal
    from app.domains.knowledge.gateway import knowledge
    from app.models.org import User
    from app.services.document_service import get_document

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        doc = get_document(db, document_id)
        if not user or not doc or doc.deleted_at is not None:
            return None
        rid = knowledge.sync_document_after_ingest(db, user, doc)
        db.commit()
        return rid
    except Exception:
        logger.exception(
            "KnowFlow 后台入库同步异常 doc=%s user=%s",
            document_id,
            user_id,
        )
        db.rollback()
        return None
    finally:
        db.close()


def enqueue_sync_after_ingest(document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """服务层/导入场景：异步触发同步（daemon 线程）。"""
    if not _should_enqueue():
        run_sync_after_ingest(document_id, user_id)
        return
    threading.Thread(
        target=run_sync_after_ingest,
        args=(document_id, user_id),
        daemon=True,
        name=f"knowflow-sync-{document_id}",
    ).start()


def schedule_sync_after_ingest(
    background_tasks,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """HTTP 上传完成：由 FastAPI BackgroundTasks 触发同步。"""
    background_tasks.add_task(run_sync_after_ingest, document_id, user_id)


def _should_enqueue() -> bool:
    from app.domains.knowledge.gateway import knowledge

    return knowledge.enabled()


def run_catalog_reconcile_for_user(user_id: uuid.UUID) -> None:
    """登录后后台：建分级库、对齐 ACL、同步文档（不阻塞登录/切片管理入口）。"""
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models.org import User
    from app.services.knowflow_catalog_service import reconcile_user_knowflow_catalog
    from app.services.ragflow_sync_service import purge_stale_knowflow_links

    if not get_settings().knowflow_enabled:
        return

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return
        settings = get_settings()
        reconcile_user_knowflow_catalog(
            db,
            user,
            sync_limit=settings.ragflow_sync_on_login_limit,
            sync_documents=True,
        )
        try:
            purge_stale_knowflow_links(db)
        except Exception as e:
            logger.warning("KnowFlow 残留索引清理跳过 user=%s: %s", user_id, e)
        db.commit()
        logger.info("KnowFlow 登录后台目录同步完成 user=%s", user.username)
    except Exception:
        logger.exception("KnowFlow 登录后台目录同步失败 user=%s", user_id)
        db.rollback()
    finally:
        db.close()


def enqueue_catalog_reconcile_after_login(user_id: uuid.UUID) -> None:
    """登录后异步触发 KnowFlow 分级库与文档同步。"""
    if not _should_enqueue():
        run_catalog_reconcile_for_user(user_id)
        return
    threading.Thread(
        target=run_catalog_reconcile_for_user,
        args=(user_id,),
        daemon=True,
        name=f"knowflow-catalog-{user_id}",
    ).start()
