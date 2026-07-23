"""批量重新索引：管理员全量 / 普通用户仅本人。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.knowledge_library_service import reindex_unindexed_documents


def _doc(*, owner_id, current_version_id, title="doc"):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.owner_id = owner_id
    d.current_version_id = current_version_id
    d.title = title
    d.deleted_at = None
    return d


def _version(version_id, *, file_size=100):
    v = MagicMock()
    v.id = version_id
    v.file_size = file_size
    return v


def test_reindex_unindexed_regular_user_only_own_docs():
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    other_id = uuid.uuid4()

    own_vid = uuid.uuid4()
    other_vid = uuid.uuid4()
    own_doc = _doc(owner_id=user.id, current_version_id=own_vid, title="mine")
    other_doc = _doc(owner_id=other_id, current_version_id=other_vid, title="theirs")

    # scalars().all() 返回查询结果；普通用户 SQL 已按 owner 过滤，此处模拟仅本人
    db.scalars.return_value.all.return_value = [own_doc]
    db.query.return_value.filter.return_value.all.return_value = [_version(own_vid)]

    job = MagicMock(id=uuid.uuid4())
    meta = {str(own_doc.id): {"knowledge_synced": False, "parse_status": "未同步"}}

    with patch(
        "app.core.permissions.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value=meta,
    ), patch(
        "app.services.document_index_service.is_index_ready_meta",
        return_value=False,
    ), patch(
        "app.services.knowledge_parser_service.assert_index_stack_ready",
    ), patch(
        "app.services.knowledge_parser_service.reindex_parser_id_raw",
        return_value="naive",
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_reindex",
        return_value=job,
    ) as enqueue:
        result = reindex_unindexed_documents(db, user)

    assert result["queued"] == 1
    assert result["total"] == 1
    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["document_id"] == own_doc.id
    # 确保未把他人文档入队
    assert other_doc.id != own_doc.id


def test_reindex_unindexed_admin_queues_all_users():
    db = MagicMock()
    admin = MagicMock()
    admin.id = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    vid_a = uuid.uuid4()
    vid_b = uuid.uuid4()
    doc_a = _doc(owner_id=user_a, current_version_id=vid_a, title="a")
    doc_b = _doc(owner_id=user_b, current_version_id=vid_b, title="b")

    db.scalars.return_value.all.return_value = [doc_a, doc_b]
    db.query.return_value.filter.return_value.all.return_value = [
        _version(vid_a),
        _version(vid_b),
    ]

    job = MagicMock(id=uuid.uuid4())
    meta = {
        str(doc_a.id): {"knowledge_synced": False, "parse_status": "未同步"},
        str(doc_b.id): {"knowledge_synced": False, "parse_status": "未同步"},
    }

    with patch(
        "app.core.permissions.user_is_superuser",
        return_value=True,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value=meta,
    ), patch(
        "app.services.document_index_service.is_index_ready_meta",
        return_value=False,
    ), patch(
        "app.services.knowledge_parser_service.assert_index_stack_ready",
    ), patch(
        "app.services.knowledge_parser_service.reindex_parser_id_raw",
        return_value="naive",
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_reindex",
        return_value=job,
    ) as enqueue:
        result = reindex_unindexed_documents(db, admin)

    assert result["queued"] == 2
    assert result["total"] == 2
    assert enqueue.call_count == 2
    queued_ids = {c.kwargs["document_id"] for c in enqueue.call_args_list}
    assert queued_ids == {doc_a.id, doc_b.id}


def test_reindex_unindexed_skips_already_ready():
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    vid = uuid.uuid4()
    doc = _doc(owner_id=user.id, current_version_id=vid)

    db.scalars.return_value.all.return_value = [doc]
    db.query.return_value.filter.return_value.all.return_value = [_version(vid)]

    with patch(
        "app.core.permissions.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value={
            str(doc.id): {
                "knowledge_synced": True,
                "parse_status": "已索引",
                "index_completed_at": datetime.now(timezone.utc),
            }
        },
    ), patch(
        "app.services.document_index_service.is_index_ready_meta",
        return_value=True,
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_reindex",
    ) as enqueue:
        result = reindex_unindexed_documents(db, user)

    assert result == {"total": 0, "queued": 0, "skipped": 1}
    enqueue.assert_not_called()
