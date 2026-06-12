"""上传完成后的后台处理（分块、Git、版本预对比）— 不阻塞 upload API。"""

from __future__ import annotations

import logging
import threading
import uuid

logger = logging.getLogger(__name__)


def run_post_upload_processing(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from app.database import SessionLocal
    from app.models.document import Document, DocumentVersion
    from app.services.documents.crud import _try_sync_version_git
    from app.services.version_compare_service import schedule_precompare_for_version

    db = SessionLocal()
    try:
        version = db.get(DocumentVersion, version_id)
        doc = db.get(Document, document_id)
        if not version or not doc or version.document_id != document_id:
            return
        _try_sync_version_git(db, version)
        try:
            schedule_precompare_for_version(db, document_id, version_id)
        except Exception:
            logger.exception(
                "版本预对比调度失败 doc=%s version=%s", document_id, version_id
            )
    except Exception:
        logger.exception(
            "上传后处理失败 doc=%s version=%s", document_id, version_id
        )
    finally:
        db.close()


def schedule_post_upload_processing(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    threading.Thread(
        target=run_post_upload_processing,
        args=(document_id, version_id, user_id),
        daemon=True,
        name=f"post-upload-{version_id}",
    ).start()
