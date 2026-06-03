"""上传完成后 KnowFlow 后台同步。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.domains.knowledge.background_sync import (
    enqueue_sync_after_ingest,
    run_sync_after_ingest,
    schedule_sync_after_ingest,
)


def test_run_sync_after_ingest_delegates_to_gateway():
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = MagicMock()
    user = MagicMock()
    doc = MagicMock(deleted_at=None)

    with patch(
        "app.database.SessionLocal",
        return_value=db,
    ), patch(
        "app.services.document_service.get_document",
        return_value=doc,
    ), patch(
        "app.domains.knowledge.gateway.knowledge.sync_document_after_ingest",
        return_value="rag-1",
    ) as sync_after_ingest:
        db.get.return_value = user
        rid = run_sync_after_ingest(doc_id, user_id)

    assert rid == "rag-1"
    sync_after_ingest.assert_called_once()
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_schedule_sync_after_ingest_uses_background_tasks():
    tasks = MagicMock()
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()

    schedule_sync_after_ingest(tasks, doc_id, user_id)

    tasks.add_task.assert_called_once_with(run_sync_after_ingest, doc_id, user_id)


def test_enqueue_sync_after_ingest_starts_thread_when_enabled():
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with patch(
        "app.domains.knowledge.background_sync._should_enqueue",
        return_value=True,
    ), patch(
        "app.domains.knowledge.background_sync.threading.Thread"
    ) as thread_cls:
        enqueue_sync_after_ingest(doc_id, user_id)

    thread_cls.assert_called_once()
    thread_cls.return_value.start.assert_called_once()


def test_enqueue_catalog_reconcile_starts_thread():
    user_id = uuid.uuid4()

    with patch(
        "app.domains.knowledge.background_sync._should_enqueue",
        return_value=True,
    ), patch(
        "app.domains.knowledge.background_sync.threading.Thread"
    ) as thread_cls:
        from app.domains.knowledge.background_sync import enqueue_catalog_reconcile_after_login

        enqueue_catalog_reconcile_after_login(user_id)

    thread_cls.assert_called_once()
    thread_cls.return_value.start.assert_called_once()
