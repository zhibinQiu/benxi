"""文档入库后的 KnowFlow 后台同步（不阻塞上传 API）。"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def run_sync_after_ingest(document_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    """同步执行（无新线程）：用于测试或必须等待结果的场景。"""
    from app.database import SessionLocal
    from app.services.knowledge_sync_job_service import (
        create_document_knowledge_index_job,
        run_document_knowledge_index_job,
    )

    db = SessionLocal()
    try:
        job = create_document_knowledge_index_job(
            db,
            user_id=user_id,
            document_id=document_id,
            force=True,
        )
        if not job:
            return None
        run_document_knowledge_index_job(job.id)
        from app.domains.knowledge.gateway import knowledge

        link = knowledge.document_link(db, document_id)
        return link.ragflow_document_id if link else None
    except Exception:
        logger.exception(
            "KnowFlow 后台入库同步异常 doc=%s user=%s",
            document_id,
            user_id,
        )
        return None
    finally:
        db.close()


def enqueue_sync_after_ingest(document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """服务层/导入场景：创建后台任务（daemon 线程）。"""
    from app.database import SessionLocal
    from app.services.document_service import get_document, resolve_current_version
    from app.services.knowledge_sync_job_service import enqueue_document_knowledge_index

    if not _should_enqueue():
        run_sync_after_ingest(document_id, user_id)
        return

    db = SessionLocal()
    try:
        version_id = None
        doc = get_document(db, document_id)
        if doc:
            version = resolve_current_version(db, doc)
            if version:
                version_id = version.id
        enqueue_document_knowledge_index(
            db,
            user_id=user_id,
            document_id=document_id,
            version_id=version_id,
            force=True,
        )
    finally:
        db.close()


def schedule_sync_after_ingest(
    background_tasks,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """HTTP 上传完成：创建后台任务并立即返回（不阻塞响应）。"""
    from app.database import SessionLocal
    from app.services.knowledge_sync_job_service import schedule_knowledge_index_after_upload

    _ = background_tasks  # 保留参数以兼容 API 签名
    db = SessionLocal()
    try:
        job = schedule_knowledge_index_after_upload(
            db,
            user_id=user_id,
            document_id=document_id,
            version_id=version_id,
        )
        return job.id if job else None
    finally:
        db.close()


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
            sync_documents=settings.ragflow_sync_on_login,
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
    from app.services.background_job_dispatch import submit_light_background

    submit_light_background(
        f"knowflow-catalog-{user_id}",
        run_catalog_reconcile_for_user,
        user_id,
    )


def run_warm_on_login(user_id: uuid.UUID) -> None:
    """登录后后台：SSO 开户、ACL 对齐与文档目录同步（不阻塞登录响应）。"""
    from app.database import SessionLocal
    from app.models.org import User
    from app.services.ragflow_identity_service import warm_ragflow_on_login

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return
        warm_ragflow_on_login(db, user)
        db.commit()
        logger.info("KnowFlow 登录预热完成 user=%s", user.username)
    except Exception:
        logger.exception("KnowFlow 登录预热失败 user=%s", user_id)
        db.rollback()
    finally:
        db.close()


def enqueue_warm_on_login(user_id: uuid.UUID) -> None:
    """登录成功后异步预热 KnowFlow（与切片管理跳转解耦）。"""
    if not _should_enqueue():
        run_warm_on_login(user_id)
        return
    from app.services.background_job_dispatch import submit_light_background

    submit_light_background(
        f"knowflow-warm-{user_id}",
        run_warm_on_login,
        user_id,
    )
