from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.document_scope import can_read_document
from app.core.exceptions import forbidden, not_found
from app.database import get_db
from app.domains.knowledge import knowledge
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import DocumentKnowflowSyncOut
from app.services import document_service

router = APIRouter()

@router.post(
    "/{document_id}/sync-knowflow",
    response_model=ApiResponse[DocumentKnowflowSyncOut],
)
def sync_document_knowflow(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentKnowflowSyncOut]:
    """将当前文档强制同步到分级 KnowFlow 知识库（个人/部门/公司）。"""
    from app.core.user_messages import (
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        KNOWLEDGE_SYNC_DISABLED,
        KNOWLEDGE_SYNC_FAILED,
    )
    from app.services.document_service import resolve_current_version

    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    if not can_read_document(db, user, doc):
        raise forbidden()
    if not resolve_current_version(db, doc):
        raise forbidden("文档尚未上传文件，无法同步知识库")

    if not knowledge.enabled():
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                message=KNOWLEDGE_SYNC_DISABLED,
            )
        )

    if not knowledge.stack_reachable():
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                message=KNOWLEDGE_SERVICE_UNAVAILABLE,
            )
        )

    from app.services.knowledge_sync_job_service import enqueue_document_knowledge_index

    job = enqueue_document_knowledge_index(
        db,
        user_id=user.id,
        document_id=doc.id,
        version_id=doc.current_version_id,
        force=True,
        document_title=doc.title,
    )
    if job:
        return ApiResponse(
            data=DocumentKnowflowSyncOut(
                knowflow_synced=False,
                queued=True,
                knowledge_job_id=job.id,
                message="已加入后台任务，正在同步并解析知识库，请在「后台任务」查看进度。",
            )
        )
    return ApiResponse(
        data=DocumentKnowflowSyncOut(
            knowflow_synced=False,
            message=KNOWLEDGE_SYNC_FAILED,
        )
    )
