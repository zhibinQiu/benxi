"""用户生命周期（删除时级联清理关联数据）。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.compare import CompareJob
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.document_workflow import DocumentAccessDenial, DocumentPublishRequest
from app.models.job import Job, JobEvent
from app.models.meeting_record import MeetingRecord
from app.models.notification import Notification
from app.models.org import User, UserDepartment, UserRole
from app.models.rag import RagMessage, RagSession
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_link import RagflowAccountLink
from app.models.document import SubjectType
from app.config import get_settings

logger = logging.getLogger(__name__)


def delete_user_account(db: Session, user: User) -> None:
    """删除用户及其关联记录，避免外键约束失败。"""
    from app.services.user_knowflow_purge import purge_user_knowledge_resources

    uid = user.id

    try:
        purge_user_knowledge_resources(db, user)
    except Exception as e:
        logger.warning("删除用户资源清理失败 %s: %s", user.username, e)

    # 知识问答 / 对比 / 任务 / 通知
    session_ids = list(
        db.scalars(select(RagSession.id).where(RagSession.created_by == uid)).all()
    )
    if session_ids:
        db.execute(delete(RagMessage).where(RagMessage.session_id.in_(session_ids)))
        db.execute(delete(RagSession).where(RagSession.id.in_(session_ids)))

    job_ids = list(db.scalars(select(Job.id).where(Job.created_by == uid)).all())
    if job_ids:
        db.execute(delete(JobEvent).where(JobEvent.job_id.in_(job_ids)))
        db.execute(delete(Job).where(Job.id.in_(job_ids)))

    db.execute(delete(CompareJob).where(CompareJob.created_by == uid))
    db.execute(delete(Notification).where(Notification.user_id == uid))
    db.execute(delete(MeetingRecord).where(MeetingRecord.user_id == uid))

    # RAGFlow 映射
    db.execute(delete(RagflowDocumentLink).where(RagflowDocumentLink.platform_user_id == uid))
    db.execute(
        delete(RagflowDocumentMirrorLink).where(
            RagflowDocumentMirrorLink.platform_user_id == uid
        )
    )
    db.execute(delete(RagflowAccountLink).where(RagflowAccountLink.platform_user_id == uid))

    # 文档协作记录（非 owner）
    db.execute(delete(DocumentAccessDenial).where(DocumentAccessDenial.user_id == uid))
    db.execute(
        delete(DocumentAccessDenial).where(DocumentAccessDenial.created_by == uid)
    )
    db.execute(
        update(DocumentPublishRequest)
        .where(DocumentPublishRequest.reviewed_by == uid)
        .values(reviewed_by=None)
    )
    db.execute(
        delete(DocumentPublishRequest).where(DocumentPublishRequest.requested_by == uid)
    )
    db.execute(
        delete(DocumentPermission).where(
            DocumentPermission.subject_type == SubjectType.user.value,
            DocumentPermission.subject_id == uid,
        )
    )
    db.execute(delete(DocumentPermission).where(DocumentPermission.granted_by == uid))

    db.execute(
        update(Document).where(Document.deleted_by == uid).values(deleted_by=None)
    )
    from app.core.platform_admin import normalize_bootstrap_login_id

    admin = db.scalar(
        select(User).where(User.phone == normalize_bootstrap_login_id()).limit(1)
    )
    if admin and admin.id != uid:
        db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.created_by == uid)
            .values(created_by=admin.id)
        )

    db.execute(update(AuditLog).where(AuditLog.user_id == uid).values(user_id=None))

    db.execute(delete(UserDepartment).where(UserDepartment.user_id == uid))
    db.execute(delete(UserRole).where(UserRole.user_id == uid))
    db.delete(user)
