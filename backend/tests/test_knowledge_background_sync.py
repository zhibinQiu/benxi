"""上传完成后 KnowFlow 后台同步。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.domains.knowledge.background_sync import (
    enqueue_sync_after_ingest,
    run_sync_after_ingest,
    schedule_sync_after_ingest,
)


def test_run_sync_after_ingest_runs_job():
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch(
        "app.services.knowledge_sync_job_service.create_document_knowledge_index_job",
        return_value=MagicMock(id=job_id),
    ) as create_job, patch(
        "app.services.knowledge_sync_job_service.run_document_knowledge_index_job"
    ) as run_job, patch(
        "app.domains.knowledge.gateway.knowledge.document_link",
        return_value=MagicMock(ragflow_document_id="rag-1"),
    ):
        rid = run_sync_after_ingest(doc_id, user_id)

    assert rid == "rag-1"
    create_job.assert_called_once()
    run_job.assert_called_once_with(job_id)


def test_schedule_sync_after_ingest_creates_job():
    tasks = MagicMock()
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch(
        "app.services.knowledge_sync_job_service.schedule_knowledge_index_after_upload",
        return_value=MagicMock(id=job_id),
    ) as schedule:
        out = schedule_sync_after_ingest(
            tasks, doc_id, user_id, version_id=version_id
        )

    assert out == job_id
    schedule.assert_called_once()
    tasks.add_task.assert_not_called()


def test_enqueue_sync_after_ingest_starts_thread_when_enabled():
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with patch(
        "app.domains.knowledge.background_sync._should_enqueue",
        return_value=True,
    ), patch(
        "app.services.knowledge_sync_job_service.enqueue_document_knowledge_index",
        return_value=MagicMock(id=uuid.uuid4()),
    ) as enqueue:
        enqueue_sync_after_ingest(doc_id, user_id)

    enqueue.assert_called_once()


def test_enqueue_catalog_reconcile_starts_thread():
    user_id = uuid.uuid4()

    with patch(
        "app.domains.knowledge.background_sync._should_enqueue",
        return_value=True,
    ), patch(
        "app.services.background_job_dispatch.submit_light_background"
    ) as submit:
        from app.domains.knowledge.background_sync import enqueue_catalog_reconcile_after_login

        enqueue_catalog_reconcile_after_login(user_id)

    submit.assert_called_once()


def test_enqueue_warm_on_login_starts_thread():
    user_id = uuid.uuid4()

    with patch(
        "app.domains.knowledge.background_sync._should_enqueue",
        return_value=True,
    ), patch(
        "app.services.background_job_dispatch.submit_light_background"
    ) as submit:
        from app.domains.knowledge.background_sync import enqueue_warm_on_login

        enqueue_warm_on_login(user_id)

    submit.assert_called_once()


def test_catalog_reconcile_respects_sync_on_login_flag():
    user_id = uuid.uuid4()
    user = MagicMock()
    user.username = "u1"

    db = MagicMock()
    db.get.return_value = user

    with patch(
        "app.database.SessionLocal",
        return_value=db,
    ), patch(
        "app.config.get_settings",
        return_value=MagicMock(
            knowflow_enabled=True,
            ragflow_sync_on_login=False,
            ragflow_sync_on_login_limit=50,
        ),
    ), patch(
        "app.services.knowflow_catalog_service.reconcile_user_knowflow_catalog",
    ) as reconcile, patch(
        "app.services.ragflow_sync_service.purge_stale_knowflow_links",
    ):
        from app.domains.knowledge.background_sync import run_catalog_reconcile_for_user

        run_catalog_reconcile_for_user(user_id)

    reconcile.assert_called_once()
    assert reconcile.call_args.kwargs["sync_documents"] is False
