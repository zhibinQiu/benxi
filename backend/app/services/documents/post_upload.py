"""上传完成后的后台处理（分块、Git、版本预对比、KG 本体/实体抽取）— 不阻塞 upload API。"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def run_post_upload_processing(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from app.database import SessionLocal
    from app.models.document import Document, DocumentVersion
    from app.models.org import User
    from app.services.documents.crud import _try_sync_version_git
    from app.services.version_compare_service import schedule_precompare_for_version

    db = SessionLocal()
    try:
        version = db.get(DocumentVersion, version_id)
        doc = db.get(Document, document_id)
        user = db.get(User, user_id)
        if not version or not doc or version.document_id != document_id:
            return
        _try_sync_version_git(db, version)
        try:
            schedule_precompare_for_version(db, document_id, version_id)
        except Exception:
            logger.exception(
                "版本预对比调度失败 doc=%s version=%s", document_id, version_id
            )
        if user:
            _try_kg_extract_after_upload(db, user, doc, version)
    except Exception:
        logger.exception(
            "上传后处理失败 doc=%s version=%s", document_id, version_id
        )
    finally:
        db.close()


def _try_kg_extract_after_upload(
    db,
    user,
    doc,
    version,
    *,
    force: bool = True,
) -> None:
    """上传后自动：发现本体 + 约束抽取实体/关系（失败不影响上传主流程）。"""
    try:
        from app.config import get_settings

        if not get_settings().kg_extraction_enabled:
            return
        from app.services.kg_extraction_service import extract_kg_for_document_upload

        extract_kg_for_document_upload(
            db,
            user,
            doc,
            version,
            force=force,
            discover_ontology=True,
        )
    except Exception:
        logger.exception(
            "上传后 KG 抽取异常 doc=%s version=%s", doc.id, version.id
        )


def schedule_post_upload_processing(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from app.services.background_job_dispatch import dispatch_post_upload_processing

    dispatch_post_upload_processing(document_id, version_id, user_id)
