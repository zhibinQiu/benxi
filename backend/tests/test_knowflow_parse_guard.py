"""KnowFlow 解析提交守卫。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.knowflow_parse_guard import (
    KnowflowDocParseState,
    should_submit_parse,
)


def test_should_submit_parse_skips_when_pending_tasks_exist():
    state = KnowflowDocParseState(
        ragflow_document_id="doc-1",
        run="0",
        progress=0.0,
        pending_tasks=3,
        running_tasks=0,
    )
    with patch(
        "app.services.knowflow_parse_guard.fetch_document_parse_state",
        return_value=state,
    ):
        ok, reason = should_submit_parse(None, "doc-1", force=False)
    assert ok is False
    assert reason == "解析任务进行中"


def test_should_submit_parse_skips_when_parsing():
    state = KnowflowDocParseState(
        ragflow_document_id="doc-2",
        run="1",
        progress=0.2,
        pending_tasks=0,
        running_tasks=1,
    )
    with patch(
        "app.services.knowflow_parse_guard.fetch_document_parse_state",
        return_value=state,
    ):
        ok, reason = should_submit_parse(None, "doc-2", force=False)
    assert ok is False
    assert reason == "解析任务进行中"


def test_should_submit_parse_force_cancels_when_already_queued():
    state = KnowflowDocParseState(
        ragflow_document_id="doc-3",
        run="0",
        progress=0.0,
        pending_tasks=2,
        running_tasks=0,
    )
    with patch(
        "app.services.knowflow_parse_guard.fetch_document_parse_state",
        return_value=state,
    ):
        ok, reason = should_submit_parse(None, "doc-3", force=True)
    assert ok is True
    assert reason == "cancel_and_submit"


def test_safe_parse_documents_skips_in_progress():
    rag = MagicMock()
    with patch(
        "app.services.knowflow_parse_guard.should_submit_parse",
        side_effect=[(False, "解析任务进行中"), (True, "submit")],
    ), patch(
        "app.services.knowflow_parse_guard.cancel_document_parse_work",
    ) as cancel:
        from app.services.knowflow_parse_guard import safe_parse_documents

        skipped = safe_parse_documents(rag, "ds-1", ["a", "b"])
    cancel.assert_not_called()
    rag.parse_documents.assert_called_once_with("ds-1", ["b"])
    assert skipped == {"a": "解析任务进行中"}


def test_recover_knowflow_stuck_queue_clears_tasks_and_resets_documents():
    from app.services.knowflow_parse_guard import recover_knowflow_stuck_queue

    with (
        patch(
            "app.services.knowflow_parse_guard.clear_stuck_queue_tasks",
            return_value={"removed": 3},
        ) as clear_tasks,
        patch(
            "app.services.knowflow_parse_guard.reset_stuck_parsing_documents",
            return_value={"reset": 2},
        ) as reset_docs,
        patch(
            "app.services.knowflow_parse_guard.clear_redis_parse_queues",
            return_value={"cleared": 1},
        ) as clear_redis,
    ):
        out = recover_knowflow_stuck_queue()

    clear_tasks.assert_called_once_with(None)
    reset_docs.assert_called_once_with(None)
    clear_redis.assert_called_once_with()
    assert out == {
        "tasks_cleared": 3,
        "documents_reset": 2,
        "redis_queues_cleared": 1,
    }


def test_find_active_document_index_job_dedupes():
    import uuid
    from unittest.mock import MagicMock

    from app.models.job import JobStatus
    from app.services.knowledge_sync_job_service import (
        find_active_document_index_job,
    )

    doc_id = uuid.uuid4()
    job = MagicMock()
    job.status = JobStatus.running.value
    job.payload = {}
    db = MagicMock()
    with patch(
        "app.services.knowledge_sync_job_service._collect_document_index_jobs",
        return_value=[job],
    ):
        assert find_active_document_index_job(db, doc_id) is job
